"""Federated Learning client — Milestone 3: full training loop.

Flow per round:
  1. Poll GetRoundStatus cho đến state=TRAINING
  2. GetGlobalModel  → load weights vào model
  3. Train local_epochs trên IID shard
  4. SubmitUpdate với timing breakdown + metadata (hostname, GPU, torch ver)
  5. Poll GetRoundStatus cho đến state=DONE → exit sạch

Shard selection (M3.6):
  --shard-id / --num-shards → partition_iid(seed=42, num_clients=num_shards)[shard_id]
  Cả 2 client dùng cùng seed → shard giống nhau, mỗi client tự lấy phần của mình.

M2 compat:
  Truyền --poll N để chạy chế độ cũ (chỉ poll GetRoundStatus, không train).
"""
from __future__ import annotations

import socket
import sys
import time

import grpc
import torch
import torch.nn.functional as F

from data_partition import load_mnist, make_loader, partition_iid
from model import MnistCNN, load_state_dict_from_bytes, serialize_state_dict
from proto import federated_pb2, federated_pb2_grpc
from run_context import build_cli_parser, cli_overrides, load_config, set_seed

POLL_INTERVAL_SEC = 2.0


# ============================================================
# Training
# ============================================================


def train_local(
    model: torch.nn.Module,
    loader,
    optimizer: torch.optim.Optimizer,
    device: torch.device,
    local_epochs: int,
    client_id: str,
) -> tuple[float, int]:
    """Train local_epochs trên shard. Returns (avg_loss_last_epoch, total_samples)."""
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
            f"[client {client_id}] epoch {epoch + 1}/{local_epochs} "
            f"loss={last_loss:.4f}"
        )

    return last_loss, num_samples


# ============================================================
# Main loop (M3 full training)
# ============================================================


def run_federated(args, cfg: dict, server_addr: str) -> None:
    client_id = args.client_id
    print(f"[client {client_id}] connecting to {server_addr}")
    print(f"[client {client_id}] shard={args.shard_id}/{args.num_shards}")

    options = [
        ("grpc.max_send_message_length", 16 * 1024 * 1024),
        ("grpc.max_receive_message_length", 16 * 1024 * 1024),
    ]
    with grpc.insecure_channel(server_addr, options=options) as channel:
        try:
            grpc.channel_ready_future(channel).result(timeout=5)
        except grpc.FutureTimeoutError:
            print(f"[client] ERROR: khong connect duoc {server_addr} sau 5s")
            print("[client] Kiem tra: server da chay chua? Firewall port 50051? LAN IP dung?")
            sys.exit(1)

        stub = federated_pb2_grpc.FederatedLearningStub(channel)

        # ── Bước 1: Chờ state=TRAINING ──────────────────────────────────────
        print(f"[client {client_id}] waiting for server state=TRAINING ...")
        while True:
            try:
                status = stub.GetRoundStatus(federated_pb2.Empty(), timeout=10)
            except grpc.RpcError as e:
                print(f"[client {client_id}] GetRoundStatus error: {e.code()} {e.details()}")
                sys.exit(2)
            state_name = federated_pb2.RoundStatus.State.Name(status.state)
            if status.state == federated_pb2.RoundStatus.TRAINING:
                break
            if status.state == federated_pb2.RoundStatus.DONE:
                print(f"[client {client_id}] server already DONE, nothing to do")
                print(f"[client {client_id}] done")
                return
            print(
                f"[client {client_id}] state={state_name} round={status.current_round}/"
                f"{status.num_rounds_total}, retrying in {POLL_INTERVAL_SEC}s ..."
            )
            time.sleep(POLL_INTERVAL_SEC)

        current_round = status.current_round
        print(
            f"[client {client_id}] round={current_round}/{status.num_rounds_total} "
            f"state=TRAINING"
        )

        # ── Bước 2: Download global model ───────────────────────────────────
        t_dl = time.perf_counter()
        try:
            model_resp = stub.GetGlobalModel(
                federated_pb2.RoundRequest(round_id=current_round, client_id=client_id),
                timeout=30,
            )
        except grpc.RpcError as e:
            print(f"[client] GetGlobalModel RPC error: {e.code()} {e.details()}")
            sys.exit(2)
        download_ms = (time.perf_counter() - t_dl) * 1000
        print(
            f"[client {client_id}] model downloaded "
            f"{len(model_resp.serialized_state_dict) / 1024:.0f} KB "
            f"in {download_ms:.1f}ms"
        )

        # ── Bước 3: Setup model + data ───────────────────────────────────────
        device_str = cfg.get("device", "cpu")
        device = torch.device(device_str)
        if device.type == "cuda" and not torch.cuda.is_available():
            print(f"[client {client_id}] WARN: CUDA not available, fallback to CPU")
            device = torch.device("cpu")

        model = MnistCNN()
        load_state_dict_from_bytes(model, model_resp.serialized_state_dict)
        model.to(device)

        # Shard IID — cùng seed với server/client khác (M3.6)
        train_set, _ = load_mnist(data_root=cfg.get("data_root", "./data"))
        shards = partition_iid(train_set, num_clients=args.num_shards, seed=cfg["seed"])
        shard = shards[args.shard_id]
        loader = make_loader(shard, batch_size=cfg["batch_size"], shuffle=True)
        print(
            f"[client {client_id}] shard size={len(shard)} samples "
            f"device={device}"
        )

        # ── Bước 4: Train local ──────────────────────────────────────────────
        optimizer = torch.optim.SGD(
            model.parameters(), lr=cfg["lr"], momentum=0.9
        )
        t_train = time.perf_counter()
        last_loss, num_samples = train_local(
            model, loader, optimizer, device,
            local_epochs=cfg["local_epochs"],
            client_id=client_id,
        )
        train_ms = (time.perf_counter() - t_train) * 1000
        print(
            f"[client {client_id}] training done "
            f"{train_ms:.0f}ms  loss={last_loss:.4f}"
        )

        # ── Bước 5: Submit update ────────────────────────────────────────────
        gpu_name = (
            torch.cuda.get_device_name(0) if torch.cuda.is_available() else ""
        )
        cuda_ver = torch.version.cuda or ""

        update = federated_pb2.ClientUpdate(
            client_id=client_id,
            round_id=current_round,
            serialized_state_dict=serialize_state_dict(model),
            num_samples=num_samples,
            train_loss=last_loss,
            timing=federated_pb2.TimingInfo(
                download_ms=download_ms,
                train_ms=train_ms,
                upload_ms=0.0,  # không đo được trước khi RPC gửi đi; giá trị thực ở console print
            ),
            hostname=socket.gethostname(),
            gpu_name=gpu_name,
            torch_version=torch.__version__,
            cuda_version=cuda_ver,
        )

        t_ul = time.perf_counter()
        try:
            ack = stub.SubmitUpdate(update, timeout=120)  # server agg sync ~10s
        except grpc.RpcError as e:
            print(f"[client] SubmitUpdate RPC error: {e.code()} {e.details()}")
            sys.exit(2)
        upload_ms = (time.perf_counter() - t_ul) * 1000

        if not ack.accepted:
            print(
                f"[client {client_id}] ERROR: server rejected update: {ack.message}"
            )
            sys.exit(3)
        print(
            f"[client {client_id}] update accepted "
            f"upload={upload_ms:.0f}ms (incl. server agg wait)"
        )

        # ── Bước 6: Poll đến DONE ────────────────────────────────────────────
        print(f"[client {client_id}] waiting for server state=DONE ...")
        while True:
            try:
                status = stub.GetRoundStatus(federated_pb2.Empty(), timeout=10)
            except grpc.RpcError as e:
                print(f"[client {client_id}] GetRoundStatus error: {e.code()} {e.details()}")
                sys.exit(2)
            state_name = federated_pb2.RoundStatus.State.Name(status.state)
            if status.state == federated_pb2.RoundStatus.DONE:
                print(f"[client {client_id}] server state=DONE ✓")
                break
            # Server đang AGGREGATING / EVALUATING — bình thường
            print(
                f"[client {client_id}] state={state_name}, "
                f"waiting {POLL_INTERVAL_SEC}s ..."
            )
            time.sleep(POLL_INTERVAL_SEC)

    # ── Summary ──────────────────────────────────────────────────────────────
    total_ms = download_ms + train_ms + upload_ms
    print(
        f"[client {client_id}] timing  "
        f"download={download_ms:.0f}ms  "
        f"train={train_ms:.0f}ms  "
        f"upload={upload_ms:.0f}ms  "
        f"total={total_ms:.0f}ms"
    )
    print(f"[client {client_id}] done")


# ============================================================
# M2 compat: --poll mode (chỉ GetRoundStatus)
# ============================================================


def run_poll_only(args, cfg: dict, server_addr: str) -> None:
    """M2 compat — chỉ poll GetRoundStatus N lần rồi thoát."""
    print(f"[client {args.client_id}] connecting to {server_addr}")
    options = [
        ("grpc.max_send_message_length", 16 * 1024 * 1024),
        ("grpc.max_receive_message_length", 16 * 1024 * 1024),
    ]
    with grpc.insecure_channel(server_addr, options=options) as channel:
        try:
            grpc.channel_ready_future(channel).result(timeout=5)
        except grpc.FutureTimeoutError:
            print(
                f"[client] ERROR: khong connect duoc den {server_addr} sau 5s"
            )
            print(
                "[client] Kiem tra: server da chay chua? Firewall port 50051? LAN IP dung?"
            )
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
    parser = build_cli_parser("Federated Learning client (M3)")
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
    args = parser.parse_args()

    cfg = load_config(args.config, overrides=cli_overrides(args))
    set_seed(cfg["seed"])
    server_addr = args.server_addr or cfg["server_addr"]

    if args.poll is not None:
        # M2 compat mode
        run_poll_only(args, cfg, server_addr)
    else:
        run_federated(args, cfg, server_addr)


if __name__ == "__main__":
    main()
