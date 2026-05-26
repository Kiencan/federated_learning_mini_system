"""Federated Learning server -Milestone 3.

State machine: TRAINING -> AGGREGATING -> EVALUATING -> DONE (M3 = 1 round).

Validation cho SubmitUpdate (theo m3_plan.md §5, đúng thứ tự):
  1. Unknown client (whitelist expected_client_ids)
  2. State != TRAINING
  3. Round mismatch (stale)
  4. Duplicate update

Aggregation chạy SYNC bên trong SubmitUpdate của client cuối -M6 sẽ refactor
sang background thread khi thêm WAIT_TIMEOUT.

Eval chạy trên CPU để không tranh GPU với Client 1 (cùng Máy 1).
"""
from __future__ import annotations

import argparse
import csv
import io
import threading
import time
from concurrent import futures
from datetime import datetime
from pathlib import Path

import grpc
import torch

from aggregation import evaluate, fedavg
from data_partition import load_mnist, make_loader
from model import MnistCNN, serialize_state_dict
from proto import federated_pb2, federated_pb2_grpc
from run_context import (
    RunContext,
    build_cli_parser,
    cli_overrides,
    create_run_dir,
    load_config,
    set_seed,
    write_run_meta,
)


# ============================================================
# Server state
# ============================================================


class ServerState:
    """State tập trung -mọi truy cập phải thông qua self.lock."""

    ROUND_LOG_FIELDS = [
        "round_id",
        "num_clients_received",
        "accuracy",
        "test_loss",
        *(f"acc_class_{c}" for c in range(10)),
        "aggregation_time_ms",
        "eval_time_ms",
        "round_wallclock_sec",
        "client_0_train_loss",
        "client_0_num_samples",
        "client_1_train_loss",
        "client_1_num_samples",
    ]

    EVENT_LOG_FIELDS = ["timestamp", "round_id", "event", "client_id", "message", "num_samples"]

    def __init__(self, cfg: dict, ctx: RunContext) -> None:
        self.cfg = cfg
        self.ctx = ctx
        self.lock = threading.Lock()           # state + received_updates
        self._log_lock = threading.Lock()      # events.csv writes (independent)

        # Global model -khởi tạo có seed để reproducibility
        self.model = MnistCNN()  # CPU
        self.eval_device = "cpu"  # Server eval CPU theo m3_plan §4

        # Round state
        self.current_round = 1  # bắt đầu round 1, không phải 0
        self.state = federated_pb2.RoundStatus.TRAINING
        self.num_rounds_total = cfg["num_rounds"]
        self.min_clients = cfg["min_clients"]
        self.expected_client_ids: set[str] = set(cfg["expected_client_ids"])

        # Per-round buffer
        self.received_updates: dict[str, federated_pb2.ClientUpdate] = {}
        self.round_start_time = time.time()

        # Track client visibility cho events + metadata
        self._seen_clients: set[str] = set()
        self._metadata_written: set[str] = set()

        # Test data cho server eval
        _, test_set = load_mnist()
        self.test_loader = make_loader(
            test_set, batch_size=cfg["batch_size"] * 4, shuffle=False
        )

        # Log files
        self.events_path = ctx.run_dir / "events.csv"
        self.round_log_path = ctx.run_dir / "round_log.csv"
        self._init_log_files()

    def _init_log_files(self) -> None:
        with self.events_path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(self.EVENT_LOG_FIELDS)
        with self.round_log_path.open("w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=self.ROUND_LOG_FIELDS).writeheader()

    def log_event(
        self,
        event: str,
        client_id: str = "",
        message: str = "",
        num_samples: int | str = "",
    ) -> None:
        """Append 1 row vào events.csv. Thread-safe qua self._log_lock.

        Tách lock riêng (không dùng self.lock) để GetGlobalModel không phải
        giữ main lock chỉ để log - main lock dành cho state mutation.
        """
        with self._log_lock:
            with self.events_path.open("a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    datetime.now().isoformat(timespec="seconds"),
                    self.current_round,
                    event,
                    client_id,
                    message,
                    num_samples,
                ])

    def mark_client_seen_locked(self, client_id: str) -> None:
        """Phải được gọi khi đã giữ self.lock."""
        if client_id not in self._seen_clients:
            self._seen_clients.add(client_id)
            # Log out of lock would be cleaner, but events.csv I/O is short
            self.log_event("client_registered", client_id=client_id)

    def write_client_metadata_if_new(self, update: federated_pb2.ClientUpdate) -> None:
        """Lần đầu nhận metadata của 1 client → append vào run_meta.json."""
        if not update.hostname or update.client_id in self._metadata_written:
            return
        self._metadata_written.add(update.client_id)
        write_run_meta(
            self.ctx,
            role=f"client/{update.client_id}",
            extra={
                "hostname": update.hostname,
                "gpu_name": update.gpu_name,
                "torch_version": update.torch_version,
                "cuda_version": update.cuda_version,
                "cuda_available": bool(update.gpu_name),
            },
        )


# ============================================================
# gRPC servicer
# ============================================================


class FederatedServicer(federated_pb2_grpc.FederatedLearningServicer):
    def __init__(self, state: ServerState) -> None:
        self.s = state

    def GetRoundStatus(self, request, context):
        # No validation -public status
        return federated_pb2.RoundStatus(
            current_round=self.s.current_round,
            state=self.s.state,
            num_rounds_total=self.s.num_rounds_total,
        )

    def GetGlobalModel(self, request, context):
        with self.s.lock:
            self.s.mark_client_seen_locked(request.client_id)
            payload = serialize_state_dict(self.s.model)
            round_id = self.s.current_round
        self.s.log_event(
            "model_pulled",
            client_id=request.client_id,
            message=f"bytes={len(payload)}",
        )
        return federated_pb2.ModelWeights(
            round_id=round_id,
            serialized_state_dict=payload,
        )

    def SubmitUpdate(self, request, context):
        # 4-layer validation (m3_plan §5) -giữ lock toàn bộ để tránh race
        with self.s.lock:
            reject = self._validate_update_locked(request)
            if reject is not None:
                msg, _ = reject
                self.s.log_event(
                    "update_rejected",
                    client_id=request.client_id,
                    message=msg,
                    num_samples=request.num_samples,
                )
                return federated_pb2.AckResponse(
                    accepted=False,
                    message=msg,
                    server_round=self.s.current_round,
                )

            # Accept
            self.s.received_updates[request.client_id] = request
            self.s.log_event(
                "update_received",
                client_id=request.client_id,
                num_samples=request.num_samples,
            )
            self.s.write_client_metadata_if_new(request)

            should_aggregate = len(self.s.received_updates) >= self.s.min_clients
            if should_aggregate:
                self.s.state = federated_pb2.RoundStatus.AGGREGATING
                # M3: sync trong handler. M6 sẽ chuyển sang background thread.
                self._aggregate_and_evaluate_locked()

        return federated_pb2.AckResponse(
            accepted=True,
            message="ok",
            server_round=self.s.current_round,
        )

    # ----- internals -----

    def _validate_update_locked(
        self, request: federated_pb2.ClientUpdate
    ) -> tuple[str, str] | None:
        """Trả về (reason, detail) nếu reject, None nếu accept. Caller giữ lock."""
        # 1. Unknown client
        if request.client_id not in self.s.expected_client_ids:
            return ("unknown_client", request.client_id)

        # 2. State must be TRAINING
        if self.s.state != federated_pb2.RoundStatus.TRAINING:
            state_name = federated_pb2.RoundStatus.State.Name(self.s.state)
            return (f"state_not_training (is {state_name})", state_name)

        # 3. Round mismatch
        if request.round_id != self.s.current_round:
            return (
                f"stale_round (got {request.round_id}, expected {self.s.current_round})",
                str(request.round_id),
            )

        # 4. Duplicate
        if request.client_id in self.s.received_updates:
            return ("duplicate_update", request.client_id)

        return None

    def _aggregate_and_evaluate_locked(self) -> None:
        """FedAvg + eval + log. Caller phải giữ self.s.lock."""
        s = self.s
        round_id = s.current_round
        updates = s.received_updates

        s.log_event("aggregation_start", message=f"clients={len(updates)}")

        # Decode mọi state_dict
        decoded: list[tuple[dict[str, torch.Tensor], int]] = []
        client_info: dict[str, tuple[float, int]] = {}
        for cid, update in updates.items():
            sd = torch.load(
                io.BytesIO(update.serialized_state_dict),
                map_location="cpu",
                weights_only=True,
            )
            decoded.append((sd, update.num_samples))
            client_info[cid] = (update.train_loss, update.num_samples)

        # FedAvg
        agg_t0 = time.perf_counter()
        new_state = fedavg(decoded)
        agg_ms = (time.perf_counter() - agg_t0) * 1000
        s.model.load_state_dict(new_state)
        s.log_event("aggregation_done", message=f"duration_ms={agg_ms:.1f}")

        # Evaluate
        s.state = federated_pb2.RoundStatus.EVALUATING
        eval_t0 = time.perf_counter()
        test_loss, accuracy, per_class = evaluate(s.model, s.test_loader, s.eval_device)
        eval_ms = (time.perf_counter() - eval_t0) * 1000
        s.log_event("evaluation_done", message=f"accuracy={accuracy:.4f}")

        # M3: hardcoded 2 clients per m3_plan.md §6 (per-client log columns).
        # Refactor when scaling to num_clients > 2 (long format CSV hoặc JSON column).
        wallclock = time.time() - s.round_start_time
        c0_loss, c0_n = client_info.get("client-0", (0.0, 0))
        c1_loss, c1_n = client_info.get("client-1", (0.0, 0))
        row = {
            "round_id": round_id,
            "num_clients_received": len(updates),
            "accuracy": round(accuracy, 6),
            "test_loss": round(test_loss, 6),
            **{f"acc_class_{c}": round(per_class[c], 6) for c in range(10)},
            "aggregation_time_ms": round(agg_ms, 2),
            "eval_time_ms": round(eval_ms, 2),
            "round_wallclock_sec": round(wallclock, 2),
            "client_0_train_loss": round(c0_loss, 6),
            "client_0_num_samples": c0_n,
            "client_1_train_loss": round(c1_loss, 6),
            "client_1_num_samples": c1_n,
        }
        with s.round_log_path.open("a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=ServerState.ROUND_LOG_FIELDS).writerow(row)

        # Advance state -M3: 1 round là DONE
        if round_id >= s.num_rounds_total:
            s.state = federated_pb2.RoundStatus.DONE
            s.log_event("round_done", message=f"final_accuracy={accuracy:.4f}")
            print(
                f"[server] round {round_id} DONE acc={accuracy:.4f} "
                f"loss={test_loss:.4f} agg={agg_ms:.1f}ms eval={eval_ms:.1f}ms"
            )
        else:
            # M4+: chuẩn bị round mới
            s.current_round += 1
            s.received_updates = {}
            s.round_start_time = time.time()
            s.state = federated_pb2.RoundStatus.TRAINING
            s.log_event(
                "round_done",
                message=f"accuracy={accuracy:.4f}, advancing_to_round={s.current_round}",
            )
            print(
                f"[server] round {round_id} done acc={accuracy:.4f}, "
                f"advancing to round {s.current_round}"
            )


# ============================================================
# Entry point
# ============================================================


def main() -> None:
    parser = build_cli_parser("Federated Learning server (M3)")
    parser.add_argument(
        "--bind",
        default="0.0.0.0:50051",
        help="bind address -mac dinh 0.0.0.0 cho LAN",
    )
    args = parser.parse_args()

    cfg = load_config(args.config, overrides=cli_overrides(args))
    # Mỗi script tự chọn experiment_name mặc định nếu CLI không override.
    # (cfg.setdefault không hoạt động vì config.yaml đã có giá trị cho centralized.)
    if not args.experiment_name:
        cfg["experiment_name"] = "exp_federated_iid_smoke"
    set_seed(cfg["seed"])

    ctx = create_run_dir(cfg, args.config)
    write_run_meta(ctx, role="server")

    state = ServerState(cfg, ctx)
    servicer = FederatedServicer(state)

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=8),
        options=[
            ("grpc.max_send_message_length", 16 * 1024 * 1024),
            ("grpc.max_receive_message_length", 16 * 1024 * 1024),
        ],
    )
    federated_pb2_grpc.add_FederatedLearningServicer_to_server(servicer, server)
    port = server.add_insecure_port(args.bind)
    if port == 0:
        raise RuntimeError(f"Khong bind duoc {args.bind}")
    server.start()

    print(f"[server] listening on {args.bind}")
    print(f"[server] run_dir={ctx.run_dir}")
    print(
        f"[server] num_rounds={cfg['num_rounds']} min_clients={cfg['min_clients']} "
        f"expected={sorted(state.expected_client_ids)}"
    )
    print("[server] state=TRAINING round=1 -waiting for clients")
    print("[server] Ctrl+C de dung")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\n[server] stopping (grace 2s)...")
        server.stop(grace=2).wait()
        print("[server] stopped")


if __name__ == "__main__":
    main()
