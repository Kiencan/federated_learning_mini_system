"""All-reduce baselines để so với parameter-server FedAvg (B2/B3).

Kiểu A (--mode A):  train local_epochs trên shard -> all_reduce trung bình model 1 lần/round.
                    Cấu trúc == federated, chỉ thay server-aggregate bằng all-reduce ngang hàng.
Kiểu B (--mode B):  all_reduce gradient MỖI mini-batch (DDP-style), N epoch data-parallel.

Chạy 2 process (rank 0/1) qua torch.distributed gloo — 1 máy (loopback) hoặc 2 máy (LAN).
Rank 0 eval + log. Chạy từ thư mục gốc repo (import model/data_partition/aggregation).

1 MÁY (2 rank cùng máy):
  RANK 0: python allreduce_train.py --mode A --rank 0 --world-size 2 --master-addr 127.0.0.1 --master-port 29555 --run-id local
  RANK 1: python allreduce_train.py --mode A --rank 1 --world-size 2 --master-addr 127.0.0.1 --master-port 29555 --run-id local

2 MÁY (Máy 1 = rank 0 = MASTER 10.0.0.1, Máy 2 = rank 1):
  MÁY 1: python allreduce_train.py --mode A --rank 0 --world-size 2 --master-addr 10.0.0.1 --master-port 29555 --run-id 2m
  MÁY 2: python allreduce_train.py --mode A --rank 1 --world-size 2 --master-addr 10.0.0.1 --master-port 29555 --run-id 2m
"""
import os, sys, time, csv, argparse, statistics
from pathlib import Path

import torch
import torch.nn.functional as F
import torch.distributed as dist

from model import build_model
from data_partition import load_dataset, partition_iid, make_loader
from aggregation import evaluate

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def all_reduce_mean_state(model, ws):
    """Trung bình toàn bộ state_dict (param + buffer) qua all_reduce SUM / ws — Kiểu A, 1 lần/round."""
    for v in model.state_dict().values():
        t = v.detach().to("cpu", torch.float32)
        dist.all_reduce(t, op=dist.ReduceOp.SUM)
        t /= ws
        v.copy_(t.to(v.device, v.dtype))


def broadcast_state(model, src=0):
    for v in model.state_dict().values():
        t = v.detach().to("cpu", torch.float32)
        dist.broadcast(t, src=src)
        v.copy_(t.to(v.device, v.dtype))


def all_reduce_mean_grads(model, ws):
    """Trung bình gradient mỗi param qua all_reduce SUM / ws — Kiểu B, gọi MỖI batch."""
    for p in model.parameters():
        if p.grad is None:
            continue
        g = p.grad.detach().to("cpu", torch.float32)
        dist.all_reduce(g, op=dist.ReduceOp.SUM)
        g /= ws
        p.grad.copy_(g.to(p.device, p.dtype))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["A", "B"], required=True)
    ap.add_argument("--rank", type=int, default=int(os.environ.get("RANK", 0)))
    ap.add_argument("--world-size", type=int, default=int(os.environ.get("WORLD_SIZE", 2)))
    ap.add_argument("--master-addr", default=os.environ.get("MASTER_ADDR", "127.0.0.1"))
    ap.add_argument("--master-port", type=int, default=int(os.environ.get("MASTER_PORT", 29555)))
    ap.add_argument("--rounds", type=int, default=30)        # Kiểu A
    ap.add_argument("--local-epochs", type=int, default=2)   # Kiểu A
    ap.add_argument("--epochs", type=int, default=60)        # Kiểu B (cân FLOPs)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--run-id", default="ar_run")
    args = ap.parse_args()

    # Windows: PyTorch build không có libuv -> tắt để TCPStore chạy được.
    os.environ.setdefault("USE_LIBUV", "0")
    os.environ["MASTER_ADDR"] = args.master_addr
    os.environ["MASTER_PORT"] = str(args.master_port)

    print(f"[rank {args.rank}/{args.world_size}] mode={args.mode} "
          f"rendezvous @ {args.master_addr}:{args.master_port} — chờ đủ {args.world_size} rank...",
          flush=True)
    dist.init_process_group("gloo", init_method="env://",
                            rank=args.rank, world_size=args.world_size)
    print(f"[rank {args.rank}] ✓ CONNECTED — bắt đầu", flush=True)

    torch.manual_seed(args.seed)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    ws = args.world_size
    rank = args.rank

    train, test = load_dataset("cifar10")
    shards = partition_iid(train, ws, seed=args.seed)
    my_loader = make_loader(shards[rank], 32, shuffle=True)
    test_loader = make_loader(test, 128, shuffle=False) if rank == 0 else None

    model = build_model("cifar10", arch="cnn").to(device)
    broadcast_state(model, src=0)  # cả 2 rank khởi đầu giống hệt
    opt = torch.optim.SGD(model.parameters(), lr=0.01, momentum=0.9)

    if rank == 0:
        outdir = Path("results") / "exp_cifar_allreduce" / f"{args.mode}_{args.run_id}"
        outdir.mkdir(parents=True, exist_ok=True)
        f = open(outdir / "round_log.csv", "w", newline="", encoding="utf-8")
        w = csv.DictWriter(f, fieldnames=["round_id", "accuracy", "round_wallclock_sec", "cumulative_sec"])
        w.writeheader()

    def log(rid, acc, rt, cum):
        if rank == 0:
            w.writerow({"round_id": rid, "accuracy": round(acc, 6),
                        "round_wallclock_sec": round(rt, 3), "cumulative_sec": round(cum, 3)})
            f.flush()
            print(f"[{args.mode} rank0] round {rid:02d} acc={acc:.4f} time={rt:.2f}s", flush=True)

    t0 = time.perf_counter()

    if args.mode == "A":
        for r in range(1, args.rounds + 1):
            rs = time.perf_counter()
            model.train()
            for _ in range(args.local_epochs):
                for x, y in my_loader:
                    x, y = x.to(device), y.to(device)
                    opt.zero_grad(); loss = F.cross_entropy(model(x), y)
                    loss.backward(); opt.step()
            all_reduce_mean_state(model, ws)   # 1 all-reduce / round
            dist.barrier()
            rt = time.perf_counter() - rs
            if rank == 0:
                _, acc, _ = evaluate(model, test_loader, device)
                log(r, acc, rt, time.perf_counter() - t0)
    else:  # B — sync data-parallel, all-reduce grads mỗi batch
        for e in range(1, args.epochs + 1):
            es = time.perf_counter()
            model.train()
            for x, y in my_loader:
                x, y = x.to(device), y.to(device)
                opt.zero_grad(); loss = F.cross_entropy(model(x), y)
                loss.backward()
                all_reduce_mean_grads(model, ws)   # all-reduce MỖI batch
                opt.step()
            dist.barrier()
            et = time.perf_counter() - es
            if rank == 0:
                _, acc, _ = evaluate(model, test_loader, device)
                log(e, acc, et, time.perf_counter() - t0)

    total = time.perf_counter() - t0
    if rank == 0:
        f.close()
        rows = list(csv.DictReader(open(outdir / "round_log.csv", encoding="utf-8")))
        accs = [float(r["accuracy"]) for r in rows]
        rts = [float(r["round_wallclock_sec"]) for r in rows]
        print(f"[{args.mode} DONE] total={total:.1f}s  n={len(rows)}  "
              f"best_acc={max(accs)*100:.2f}%  final={accs[-1]*100:.2f}%  "
              f"crit_path={sum(rts):.1f}s  mean_round={statistics.mean(rts):.2f}s", flush=True)
    dist.barrier()
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
