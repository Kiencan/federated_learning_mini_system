"""Federated Learning client — Milestone 4: multi-round loop.

Flow (outer round loop):
  Setup 1 lan: MNIST shard + DataLoader + device (khong lap lai moi round)
  Per round:
    1. wait_for_new_round_or_done() → TRAINING (round moi) | DONE
    2. do_one_round(): GetGlobalModel → train local → SubmitUpdate
    last_completed_round = round_id
  Break khi DONE, print summary tong tat ca round.

Thay doi so voi M3:
  - DataLoader tao 1 lan truoc loop, reuse qua cac round (shuffle=True tu rotate)
  - Model + Optimizer tao MOI moi round (pull global model fresh — yeu cau FedAvg)
  - wait_for_new_round_or_done() detect server advance sang round moi
  - do_one_round() tach rieng (M4.2 per m4_plan §5)
  - Summary timing tong hop cuoi (all rounds)
  - Reject bat ky ly do → sys.exit(3) ngay, khong retry (per m4_plan §6)

M2 compat: --poll N van hoat dong.
"""
from __future__ import annotations

import socket
import sys
import time
from collections import Counter

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import grpc
import torch
import torch.nn.functional as F

from data_partition import load_dataset, make_loader, partition_iid, partition_noniid_pathological
from model import build_model, load_state_dict_from_bytes, serialize_state_dict
from proto import federated_pb2, federated_pb2_grpc
from run_context import build_cli_parser, cli_overrides, load_config, set_seed

POLL_INTERVAL_SEC = 0.5  # CIFAR opt-A: giảm từ 2.0 → phát hiện round mới nhanh hơn,
                         # cắt ~1-1.5s dead time/round giữa lúc server advance và client pull


# ============================================================
# Training helper
# ============================================================


def train_local(
    model: torch.nn.Module,
    loader,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    local_epochs: int,
    client_id: str,
    round_id: int,
) -> tuple[float, int]:
    """Train local_epochs tren shard. Returns (loss_epoch_cuoi, total_samples)."""
    model.train()
    last_loss = 0.0
    num_samples = len(loader.dataset)

    for epoch in range(local_epochs):
        running_loss = 0.0
        n = 0
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad()
            loss = F.cross_entropy(model(x), y)
            loss.backward()
            optimizer.step()
            running_loss += loss.item() * len(y)
            n += len(y)
        last_loss = running_loss / n
        print(
            f"[client {client_id}] round={round_id} "
            f"epoch {epoch + 1}/{local_epochs} loss={last_loss:.4f}"
        )

    return last_loss, num_samples


# ============================================================
# Poll helper (M4: detect round advance)
# ============================================================


def wait_for_new_round_or_done(
    stub,
    last_completed_round: int,
    client_id: str,
) -> "federated_pb2.RoundStatus":
    """Poll cho den khi server o round moi hoac DONE.

    Dieu kien tra ve:
      - state == DONE                                       → server xong
      - state == TRAINING va current_round > last_completed_round → round moi

    Tiep tuc cho khi:
      - AGGREGATING / EVALUATING (dang xu ly giua 2 round)
      - TRAINING nhung current_round == last_completed_round (da submit round nay roi)
    """
    while True:
        try:
            status = stub.GetRoundStatus(federated_pb2.Empty(), timeout=10)
        except grpc.RpcError as e:
            print(f"[client {client_id}] GetRoundStatus error: {e.code()} {e.details()}")
            sys.exit(2)

        if status.state == federated_pb2.RoundStatus.DONE:
            return status

        if (
            status.state == federated_pb2.RoundStatus.TRAINING
            and status.current_round > last_completed_round
        ):
            return status

        state_name = federated_pb2.RoundStatus.State.Name(status.state)
        print(
            f"[client {client_id}] state={state_name} "
            f"round={status.current_round}/{status.num_rounds_total}, "
            f"waiting {POLL_INTERVAL_SEC}s ..."
        )
        time.sleep(POLL_INTERVAL_SEC)


# ============================================================
# Per-round helper (M4.2: tach rieng per m4_plan §5)
# ============================================================


def do_one_round(
    stub,
    round_id: int,
    loader,
    device: torch.device,
    cfg: dict,
    client_id: str,
    gpu_name: str,
    cuda_ver: str,
) -> tuple[float, float, float]:
    """Thuc hien 1 round: download global model → train local → submit update.

    Returns (download_ms, train_ms, upload_ms).
    Thoat qua sys.exit() khi gap RPC error hoac server reject.
    """
    # Buoc 1: Download global model (fresh moi round — yeu cau FedAvg)
    t_dl = time.perf_counter()
    try:
        model_resp = stub.GetGlobalModel(
            federated_pb2.RoundRequest(round_id=round_id, client_id=client_id),
            timeout=30,
        )
    except grpc.RpcError as e:
        print(f"[client {client_id}] GetGlobalModel error: {e.code()} {e.details()}")
        sys.exit(2)
    download_ms = (time.perf_counter() - t_dl) * 1000
    print(
        f"[client {client_id}] round={round_id} model downloaded "
        f"{len(model_resp.serialized_state_dict) / 1024:.0f} KB "
        f"in {download_ms:.1f}ms"
    )

    # Buoc 2: Tao model MOI tu global weights + optimizer MOI (moi round)
    model = build_model(cfg.get("dataset", "mnist"), arch=cfg.get("model", "cnn"))
    load_state_dict_from_bytes(model, model_resp.serialized_state_dict)
    model.to(device)
    optimizer = torch.optim.SGD(
        model.parameters(), lr=cfg["lr"], momentum=0.9
    )

    # Buoc 3: Train local (DataLoader reuse, shuffle tu rotate)
    t_train = time.perf_counter()
    last_loss, num_samples = train_local(
        model, loader, optimizer, device,
        local_epochs=cfg["local_epochs"],
        client_id=client_id,
        round_id=round_id,
    )
    train_ms = (time.perf_counter() - t_train) * 1000
    print(
        f"[client {client_id}] round={round_id} train done "
        f"{train_ms:.0f}ms loss={last_loss:.4f}"
    )

    # Buoc 4: Submit update
    t_ul = time.perf_counter()

    # M7: straggler injection — sleep INSIDE upload measurement so
    # round_log.csv.round_wallclock_sec captures delay as source of truth.
    # serialize_state_dict(model) stays inside ClientUpdate(...) below.
    straggler_delay = cfg.get("straggler_delay", 0) or 0
    if straggler_delay > 0:
        print(
            f"[client {client_id}] round={round_id} straggler sleep "
            f"{straggler_delay:.1f}s before SubmitUpdate ..."
        )
        time.sleep(straggler_delay)

    try:
        ack = stub.SubmitUpdate(
            federated_pb2.ClientUpdate(
                client_id=client_id,
                round_id=round_id,
                serialized_state_dict=serialize_state_dict(model),
                num_samples=num_samples,
                train_loss=last_loss,
                timing=federated_pb2.TimingInfo(
                    download_ms=download_ms,
                    train_ms=train_ms,
                    upload_ms=0.0,  # khong do duoc truoc khi gui; gia tri thuc o console
                ),
                hostname=socket.gethostname(),
                gpu_name=gpu_name,
                torch_version=torch.__version__,
                cuda_version=cuda_ver,
            ),
            timeout=120,
        )
    except grpc.RpcError as e:
        print(f"[client {client_id}] SubmitUpdate error: {e.code()} {e.details()}")
        sys.exit(2)
    upload_ms = (time.perf_counter() - t_ul) * 1000

    # Reject → exit ngay, khong retry (per m4_plan §6)
    if not ack.accepted:
        print(
            f"[client {client_id}] ERROR: server rejected round={round_id}: "
            f"{ack.message} (server_round={ack.server_round})"
        )
        sys.exit(3)

    print(
        f"[client {client_id}] round={round_id} update accepted "
        f"upload={upload_ms:.0f}ms"
    )

    return download_ms, train_ms, upload_ms


# ============================================================
# Main federated loop (M4: multi-round)
# ============================================================


def run_federated(args, cfg: dict, server_addr: str) -> None:
    client_id = args.client_id
    print(f"[client {client_id}] shard={args.shard_id}/{args.num_shards}")

    # ── Setup truoc ket noi (fail-fast: validate config truoc khi mo channel) ──
    # Device
    device_str = cfg.get("device", "cpu")
    device = torch.device(device_str)
    if device.type == "cuda" and not torch.cuda.is_available():
        print(f"[client {client_id}] WARN: CUDA not available, fallback to CPU")
        device = torch.device("cpu")

    # Dataset shard + DataLoader — tao 1 lan, reuse qua cac round
    dataset = cfg.get("dataset", "mnist")
    train_set, _ = load_dataset(dataset, data_root=cfg.get("data_root", "./data"))
    print(f"[client {client_id}] dataset={dataset}")

    data_split = cfg.get("data_split", "iid")

    # Step 1: Dispatch partition (chua in shard-specific info)
    if data_split == "noniid":
        if args.num_shards != 2:
            print(
                f"[client {client_id}] ERROR: noniid requires --num-shards 2, "
                f"got {args.num_shards}"
            )
            sys.exit(4)
        shards = partition_noniid_pathological(train_set, num_clients=2)
        print(f"[client {client_id}] split=noniid (pathological)")
    elif data_split == "iid":
        weights = None
        if getattr(args, "shard_weights", None):
            weights = [float(x) for x in args.shard_weights.split(",")]
        shards = partition_iid(
            train_set, num_clients=args.num_shards, seed=cfg["seed"], weights=weights
        )
        print(
            f"[client {client_id}] split=iid (num_shards={args.num_shards}"
            f"{f', weights={weights}' if weights else ', đều'})"
        )
    else:
        print(
            f"[client {client_id}] ERROR: unknown data_split={data_split!r}, "
            f"expected iid|noniid"
        )
        sys.exit(4)

    # Step 2: Validate shard_id TRUOC khi in shard-specific info (tranh in label sai)
    if not (0 <= args.shard_id < len(shards)):
        print(
            f"[client {client_id}] ERROR: --shard-id {args.shard_id} out of range "
            f"[0, {len(shards) - 1}] (split={data_split}, num_shards={args.num_shards})"
        )
        sys.exit(4)

    shard = shards[args.shard_id]

    # Step 3: In class distribution THUC TE — source of truth cho debug Non-IID
    labels = [int(train_set.targets[i]) for i in shard.indices]
    dist = dict(sorted(Counter(labels).items()))
    print(
        f"[client {client_id}] shard {args.shard_id} "
        f"size={len(shard)} class_distribution={dist}"
    )

    loader = make_loader(shard, batch_size=cfg["batch_size"], shuffle=True)
    print(f"[client {client_id}] device={device}")

    # Metadata co dinh (khong doi qua cac round)
    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else ""
    cuda_ver = torch.version.cuda or ""

    # ── Ket noi server sau khi da validate xong ───────────────────────────────
    print(f"[client {client_id}] connecting to {server_addr}")
    options = [
        ("grpc.max_send_message_length", 16 * 1024 * 1024),
        ("grpc.max_receive_message_length", 16 * 1024 * 1024),
    ]
    with grpc.insecure_channel(server_addr, options=options) as channel:
        try:
            grpc.channel_ready_future(channel).result(timeout=5)
        except grpc.FutureTimeoutError:
            print(f"[client {client_id}] ERROR: khong connect duoc {server_addr} sau 5s")
            print("[client] Kiem tra: server da chay chua? Firewall port 50051? LAN IP dung?")
            sys.exit(1)

        stub = federated_pb2_grpc.FederatedLearningStub(channel)

        # ── Outer multi-round loop ────────────────────────────────────────────
        last_completed_round = 0
        total_download_ms = 0.0
        total_train_ms = 0.0
        total_upload_ms = 0.0

        while True:
            # Cho den khi co round moi hoac server DONE
            status = wait_for_new_round_or_done(stub, last_completed_round, client_id)

            if status.state == federated_pb2.RoundStatus.DONE:
                print(f"[client {client_id}] server state=DONE")
                break

            round_id = status.current_round
            print(
                f"[client {client_id}] >>> round {round_id}/{status.num_rounds_total} bat dau"
            )

            download_ms, train_ms, upload_ms = do_one_round(
                stub, round_id, loader, device, cfg, client_id, gpu_name, cuda_ver
            )

            # Cap nhat tong hop
            total_download_ms += download_ms
            total_train_ms += train_ms
            total_upload_ms += upload_ms
            last_completed_round = round_id

            print(
                f"[client {client_id}] <<< round {round_id} done  "
                f"download={download_ms:.0f}ms  "
                f"train={train_ms:.0f}ms  "
                f"upload={upload_ms:.0f}ms"
            )

    # ── Summary tong tat ca round ────────────────────────────────────────────
    rounds_done = last_completed_round
    if rounds_done > 0:
        avg_dl = total_download_ms / rounds_done
        avg_tr = total_train_ms / rounds_done
        avg_ul = total_upload_ms / rounds_done
        print(
            f"\n[client {client_id}] === {rounds_done} round(s) completed ==="
        )
        print(
            f"[client {client_id}] total   "
            f"download={total_download_ms:.0f}ms  "
            f"train={total_train_ms:.0f}ms  "
            f"upload={total_upload_ms:.0f}ms"
        )
        print(
            f"[client {client_id}] avg/round  "
            f"download={avg_dl:.0f}ms  "
            f"train={avg_tr:.0f}ms  "
            f"upload={avg_ul:.0f}ms"
        )
    print(f"[client {client_id}] done")


# ============================================================
# M2 compat: --poll mode
# ============================================================


def run_poll_only(args, cfg: dict, server_addr: str) -> None:
    """M2 compat — chi poll GetRoundStatus N lan roi thoat."""
    print(f"[client {args.client_id}] connecting to {server_addr}")
    options = [
        ("grpc.max_send_message_length", 16 * 1024 * 1024),
        ("grpc.max_receive_message_length", 16 * 1024 * 1024),
    ]
    with grpc.insecure_channel(server_addr, options=options) as channel:
        try:
            grpc.channel_ready_future(channel).result(timeout=5)
        except grpc.FutureTimeoutError:
            print(f"[client] ERROR: khong connect duoc den {server_addr} sau 5s")
            print("[client] Kiem tra: server da chay chua? Firewall port 50051? LAN IP dung?")
            sys.exit(1)

        stub = federated_pb2_grpc.FederatedLearningStub(channel)
        for i in range(args.poll):
            t0 = time.perf_counter()
            try:
                status = stub.GetRoundStatus(federated_pb2.Empty(), timeout=10)
            except grpc.RpcError as e:
                print(f"[client] RPC error: code={e.code()} details={e.details()}")
                sys.exit(2)
            rtt_ms = (time.perf_counter() - t0) * 1000
            state_name = federated_pb2.RoundStatus.State.Name(status.state)
            print(
                f"[client] poll {i + 1}/{args.poll}: "
                f"round={status.current_round}/{status.num_rounds_total} "
                f"state={state_name} rtt={rtt_ms:.1f}ms"
            )
            if i + 1 < args.poll:
                time.sleep(0.5)

    print(f"[client {args.client_id}] done")


# ============================================================
# Entry point
# ============================================================


def main() -> None:
    parser = build_cli_parser("Federated Learning client (M4: multi-round)")
    parser.add_argument(
        "--client-id", default="client-0", help="dinh danh client (vd client-0)"
    )
    parser.add_argument(
        "--server-addr",
        default=None,
        help="dia chi server host:port (override config.server_addr)",
    )
    parser.add_argument(
        "--poll",
        type=int,
        default=None,
        help="M2 compat: so lan poll GetRoundStatus roi thoat (khong train)",
    )
    parser.add_argument(
        "--shard-id",
        type=int,
        default=0,
        help="index shard IID 0-based (default=0)",
    )
    parser.add_argument(
        "--num-shards",
        type=int,
        default=2,
        help="tong so shards = so client (default=2)",
    )
    parser.add_argument(
        "--shard-weights",
        default=None,
        help="opt-B: ty le chia shard IID, vd '0.45,0.55' (Máy 1 ít hơn để cân bằng "
             "tải với node kiêm server). Bỏ trống = chia đều. Phải giống nhau mọi client.",
    )
    args = parser.parse_args()

    cfg = load_config(args.config, overrides=cli_overrides(args))
    set_seed(cfg["seed"])
    server_addr = args.server_addr or cfg["server_addr"]

    # M7: validate straggler_delay (resolved from CLI or config.yaml)
    straggler_delay = cfg.get("straggler_delay", 0) or 0
    if straggler_delay < 0:
        print(
            f"[client {args.client_id}] ERROR: straggler_delay must be >= 0, "
            f"got {straggler_delay}"
        )
        sys.exit(4)

    if args.poll is not None:
        run_poll_only(args, cfg, server_addr)
    else:
        run_federated(args, cfg, server_addr)


if __name__ == "__main__":
    main()
