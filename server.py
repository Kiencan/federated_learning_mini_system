"""Federated Learning server - Milestone 6.

State machine: TRAINING -> AGGREGATING -> TRAINING (next round) -> ... -> DONE.

M6 changes vs M3-M5:
- Aggregation chuyển từ SYNC (trong SubmitUpdate handler) -> BACKGROUND THREAD
- 3-phase lock design:
    Phase 1: hold lock, wait condition (threshold OR timeout), snapshot updates
    Phase 2: NO lock, FedAvg + evaluate + CSV write (~1s)
    Phase 3: hold lock briefly, guarded commit + advance round (<10ms)
- 3 paths (qua condition.wait):
    A "ok"      = received >= expected_count (early aggregation)
    B "partial" = timeout + received >= min_clients (drop slow clients)
    C "skipped" = timeout + received < min_clients (skip round, no aggregation)
- New events: round_timeout, partial_aggregation, round_skipped, commit_aborted
- round_log.csv schema: thêm cột `round_status` (ok/partial/skipped)
- Validate config fail-fast: 1 <= min_clients <= expected_count, wait_timeout > 0
- model_pulled event message kèm `state=<NAME>` cho observability race
"""
from __future__ import annotations

import csv
import io
import sys
import threading
import time
from concurrent import futures
from datetime import datetime

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import grpc
import torch

from aggregation import evaluate, fedavg
from data_partition import load_dataset, make_loader
from model import build_model, serialize_state_dict
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
# Pure functions (KHÔNG chạm state, gọi outside lock được)
# ============================================================


def _do_fedavg(updates_snapshot):
    """Decode state_dicts + weighted FedAvg. Returns (new_state_dict, agg_ms).

    updates_snapshot: list of (client_id, ClientUpdate) tuples.
    """
    decoded: list[tuple[dict[str, torch.Tensor], int]] = []
    for _, update in updates_snapshot:
        sd = torch.load(
            io.BytesIO(update.serialized_state_dict),
            map_location="cpu",
            weights_only=True,
        )
        decoded.append((sd, update.num_samples))
    t0 = time.perf_counter()
    new_state_dict = fedavg(decoded)
    agg_ms = (time.perf_counter() - t0) * 1000
    return new_state_dict, agg_ms


def _do_evaluate(state_dict, test_loader, device, dataset):
    """Eval state_dict trên test loader (temp model — KHÔNG chạm s.model).

    Returns (test_loss, accuracy, per_class, eval_ms).
    """
    temp_model = build_model(dataset)
    temp_model.load_state_dict(state_dict)
    t0 = time.perf_counter()
    test_loss, accuracy, per_class = evaluate(temp_model, test_loader, device)
    eval_ms = (time.perf_counter() - t0) * 1000
    return test_loss, accuracy, per_class, eval_ms


# ============================================================
# Server state
# ============================================================


class ServerState:
    """State tập trung.

    Khái niệm (M6):
      - expected_count = len(expected_client_ids) — số client whitelist (config)
      - received_count = len(received_updates)   — đã submit hợp lệ trong round
      - min_clients    = ngưỡng tối thiểu để aggregate (1 <= min_clients <= expected_count)
    """

    ROUND_LOG_FIELDS = [
        "round_id",
        "num_clients_received",
        "round_status",                        # M6 NEW: ok | partial | skipped
        "accuracy",
        "test_loss",
        *(f"acc_class_{c}" for c in range(10)),
        "aggregation_time_ms",
        "eval_time_ms",
        "round_wallclock_sec",
        "model_bytes",                         # CIFAR phase: payload model (download≈upload)
        "client_0_train_loss",
        "client_0_num_samples",
        "client_0_download_ms",                # CIFAR phase: comm (pull global model)
        "client_0_train_ms",                   # CIFAR phase: compute (train local)
        "client_1_train_loss",
        "client_1_num_samples",
        "client_1_download_ms",
        "client_1_train_ms",
    ]

    EVENT_LOG_FIELDS = ["timestamp", "round_id", "event", "client_id", "message", "num_samples"]

    def __init__(self, cfg: dict, ctx: RunContext) -> None:
        self.cfg = cfg
        self.ctx = ctx
        self.lock = threading.Lock()             # state + received_updates
        self._log_lock = threading.Lock()        # events.csv (independent)
        self.condition = threading.Condition(self.lock)  # M6: aggregation thread signal
        self.shutdown = False                    # M6: graceful exit flag

        # Global model — kiến trúc theo dataset (mnist=MnistCNN, cifar10=CifarCNN)
        self.dataset = cfg.get("dataset", "mnist")
        self.model = build_model(self.dataset)
        self.eval_device = "cpu"

        # Round state
        self.current_round = 1
        self.state = federated_pb2.RoundStatus.TRAINING
        self.num_rounds_total = cfg["num_rounds"]
        self.min_clients = int(cfg["min_clients"])
        self.wait_timeout = float(cfg["wait_timeout"])      # M6
        self.startup_timeout = float(cfg.get("startup_timeout", 180))  # CIFAR: rendezvous
        self.expected_client_ids: set[str] = set(cfg["expected_client_ids"])
        self.expected_count = len(self.expected_client_ids)  # M6

        # M6: validate config fail-fast — tránh skip mọi round vì cấu hình sai
        if not (1 <= self.min_clients <= self.expected_count):
            raise ValueError(
                f"min_clients={self.min_clients} phải trong [1, {self.expected_count}]"
            )
        if self.wait_timeout <= 0:
            raise ValueError(f"wait_timeout={self.wait_timeout} phải > 0")

        # Per-round buffer
        self.received_updates: dict[str, federated_pb2.ClientUpdate] = {}
        self.round_start_time = time.time()

        # Client visibility tracking
        self._seen_clients: set[str] = set()
        self._metadata_written: set[str] = set()

        # Test data cho server eval
        _, test_set = load_dataset(self.dataset)
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

    def log_event(self, event, client_id="", message="", num_samples=""):
        """Thread-safe append events.csv."""
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

    def mark_client_seen_locked(self, client_id):
        if client_id not in self._seen_clients:
            self._seen_clients.add(client_id)
            self.log_event("client_registered", client_id=client_id)

    def write_client_metadata_if_new(self, update):
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
# Locked helpers (module-level — caller giữ state.lock)
# ============================================================


def _advance_to_next_round_locked(state: ServerState) -> None:
    """Chuyển sang round tiếp theo HOẶC set DONE."""
    if state.current_round >= state.num_rounds_total:
        state.state = federated_pb2.RoundStatus.DONE
        state.log_event("round_done", message="final state DONE")
    else:
        state.current_round += 1
        state.received_updates = {}
        state.round_start_time = time.time()
        state.state = federated_pb2.RoundStatus.TRAINING
        state.log_event(
            "round_done",
            message=f"advancing_to_round={state.current_round}",
        )


# ============================================================
# CSV writers (single-writer = aggregation thread → no lock needed)
# ============================================================


def _write_round_log_row(state, round_id, updates_snapshot, accuracy, test_loss,
                          per_class, agg_ms, eval_ms, wallclock, status):
    """Ghi 1 row cho path A ('ok') hoặc B ('partial').

    `wallclock` được caller chốt lúc commit (trước advance) vì eval giờ chạy SAU
    khi advance round (off critical path) → không tự tính được từ round_start_time.
    """
    # M3: hardcoded 2 clients per m3_plan §6 (refactor note khi num_clients > 2)
    # CIFAR phase: kèm timing (download_ms = comm, train_ms = compute) + payload size.
    client_info = {
        cid: (u.train_loss, u.num_samples, u.timing.download_ms, u.timing.train_ms)
        for cid, u in updates_snapshot
    }
    c0_loss, c0_n, c0_dl, c0_tr = client_info.get("client-0", (0.0, 0, 0.0, 0.0))
    c1_loss, c1_n, c1_dl, c1_tr = client_info.get("client-1", (0.0, 0, 0.0, 0.0))
    # Payload model: lấy từ update bất kỳ (download≈upload vì cùng state_dict).
    model_bytes = len(updates_snapshot[0][1].serialized_state_dict) if updates_snapshot else 0
    row = {
        "round_id": round_id,
        "num_clients_received": len(updates_snapshot),
        "round_status": status,
        "accuracy": round(accuracy, 6),
        "test_loss": round(test_loss, 6),
        **{f"acc_class_{c}": round(per_class[c], 6) for c in range(10)},
        "aggregation_time_ms": round(agg_ms, 2),
        "eval_time_ms": round(eval_ms, 2),
        "round_wallclock_sec": round(wallclock, 2),
        "model_bytes": model_bytes,
        "client_0_train_loss": round(c0_loss, 6),
        "client_0_num_samples": c0_n,
        "client_0_download_ms": round(c0_dl, 2),
        "client_0_train_ms": round(c0_tr, 2),
        "client_1_train_loss": round(c1_loss, 6),
        "client_1_num_samples": c1_n,
        "client_1_download_ms": round(c1_dl, 2),
        "client_1_train_ms": round(c1_tr, 2),
    }
    with state.round_log_path.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=ServerState.ROUND_LOG_FIELDS).writerow(row)


def _write_skipped_round_row(state, round_id, received_count):
    """Ghi 1 row cho path C ('skipped'): metric columns = empty string."""
    row = {
        "round_id": round_id,
        "num_clients_received": received_count,
        "round_status": "skipped",
        "accuracy": "",
        "test_loss": "",
        **{f"acc_class_{c}": "" for c in range(10)},
        "aggregation_time_ms": "",
        "eval_time_ms": "",
        "round_wallclock_sec": round(time.time() - state.round_start_time, 2),
        "model_bytes": "",
        "client_0_train_loss": "",
        "client_0_num_samples": "",
        "client_0_download_ms": "",
        "client_0_train_ms": "",
        "client_1_train_loss": "",
        "client_1_num_samples": "",
        "client_1_download_ms": "",
        "client_1_train_ms": "",
    }
    with state.round_log_path.open("a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=ServerState.ROUND_LOG_FIELDS).writerow(row)


# ============================================================
# Background aggregation thread (M6 core)
# ============================================================


def _rendezvous_wait_for_clients(state: ServerState) -> None:
    """CIFAR phase: chờ đủ expected client register TRƯỚC khi đếm round 1.

    Client register khi gọi GetGlobalModel lần đầu (pull model). Trước đây
    round_start_time đặt ngay khi server bật → round-1 wallclock cộng luôn thời
    gian client boot/join (nặng nhất là client máy khác qua mạng: import torch +
    init CUDA + load data + độ trễ launch). Pha này chờ tất cả client lên rồi mới
    reset round_start_time, để round-1 đo đúng thời gian round thật.

    Bounded bởi startup_timeout: nếu 1 client không lên (vd crash/máy tắt), sau
    timeout vẫn tiếp tục với số client hiện có (đúng ngữ nghĩa min_clients).
    """
    print(
        f"[server] RENDEZVOUS: ĐỨNG IM ở round 0, chờ đủ {state.expected_count} client "
        f"register (tối đa {state.startup_timeout:.0f}s) trước khi bắt đầu round 1...",
        flush=True,
    )
    with state.condition:
        start = time.time()
        deadline = start + state.startup_timeout
        last_n = -1
        last_beat = start
        while not state.shutdown and len(state._seen_clients) < state.expected_count:
            n = len(state._seen_clients)
            now = time.time()
            if n != last_n:
                print(
                    f"[server] RENDEZVOUS: {n}/{state.expected_count} registered "
                    f"{sorted(state._seen_clients)} — CHỜ TIẾP (chưa start round 1)...",
                    flush=True,
                )
                last_n, last_beat = n, now
            elif now - last_beat >= 10:
                print(
                    f"[server] RENDEZVOUS: vẫn chờ {n}/{state.expected_count} "
                    f"({now - start:.0f}s / {state.startup_timeout:.0f}s)...",
                    flush=True,
                )
                last_beat = now
            remaining = deadline - now
            if remaining <= 0:
                state.log_event(
                    "rendezvous_timeout",
                    message=f"registered={len(state._seen_clients)}/{state.expected_count}",
                )
                print(
                    f"[server] ⚠ RENDEZVOUS TIMEOUT sau {state.startup_timeout:.0f}s — "
                    f"chỉ {len(state._seen_clients)}/{state.expected_count} client, chạy với client hiện có",
                    flush=True,
                )
                break
            state.condition.wait(timeout=min(remaining, 5.0))  # wake ≤5s để in heartbeat
        if state.shutdown:
            return
        # Reset đồng hồ round 1: từ đây mới tính, sau khi client đã sẵn sàng
        state.round_start_time = time.time()
        n_final = len(state._seen_clients)
        state.log_event(
            "rendezvous_done",
            message=f"registered={n_final}/{state.expected_count}",
        )
    print(
        f"[server] ✓ RENDEZVOUS DONE: {n_final}/{state.expected_count} client — bắt đầu round 1",
        flush=True,
    )


def run_aggregation_loop(state: ServerState) -> None:
    """3-phase loop per round (see module docstring).

    CIFAR phase: chạy pha rendezvous 1 lần trước round 1 (xem
    _rendezvous_wait_for_clients) để loại boot/join time khỏi round-1 wallclock.
    """
    _rendezvous_wait_for_clients(state)

    while not state.shutdown:
        # ── Phase 1: wait + snapshot (lock held) ────────────────────────────
        with state.condition:
            # Chờ vào state TRAINING (sau init hoặc sau advance round)
            while not state.shutdown and state.state != federated_pb2.RoundStatus.TRAINING:
                state.condition.wait(timeout=1.0)
            if state.shutdown:
                return

            deadline = state.round_start_time + state.wait_timeout
            round_id = state.current_round

            # Chờ: đủ expected HOẶC hết timeout
            while not state.shutdown:
                now = time.time()
                remaining = deadline - now
                if len(state.received_updates) >= state.expected_count:
                    break  # Path A: early
                if remaining <= 0:
                    state.log_event(
                        "round_timeout",
                        message=f"received={len(state.received_updates)}/{state.expected_count}",
                    )
                    break  # Path B hoặc C
                state.condition.wait(timeout=remaining)

            if state.shutdown:
                return

            # Decide path
            received_count = len(state.received_updates)
            if received_count >= state.min_clients:
                # Path A hoặc B: prepare aggregate
                state.state = federated_pb2.RoundStatus.AGGREGATING
                updates_snapshot = list(state.received_updates.items())
                is_partial = received_count < state.expected_count
            else:
                # Path C: skip round
                state.log_event(
                    "round_skipped",
                    message=f"received={received_count}/{state.expected_count}",
                )
                _write_skipped_round_row(state, round_id, received_count)
                _advance_to_next_round_locked(state)
                state.condition.notify_all()
                print(f"[server] round {round_id} SKIPPED (received={received_count})")
                continue

        # ── Phase 2: aggregate (NO lock, chỉ FedAvg ~ms) ─────────────────────
        if is_partial:
            state.log_event(
                "partial_aggregation",
                message=f"received={received_count}/{state.expected_count}",
            )
        state.log_event("aggregation_start", message=f"clients={received_count}")
        new_state_dict, agg_ms = _do_fedavg(updates_snapshot)

        # ── Phase 3: commit + advance (lock, fast <10ms) — client ĐƯỢC GIẢI PHÓNG ─
        # CIFAR opt-A: advance NGAY sau FedAvg để client pull model round sau + train,
        # KHÔNG chờ eval. Eval (~3s CPU) chuyển xuống Phase 4 chạy off critical path.
        with state.condition:
            # Guard 1: shutdown → return im lặng (KHÔNG log commit_aborted)
            if state.shutdown:
                return
            # Guard 2: state/round lệch → log commit_aborted (bug thật, self-defensive)
            if (state.current_round != round_id
                    or state.state != federated_pb2.RoundStatus.AGGREGATING):
                state_name = federated_pb2.RoundStatus.State.Name(state.state)
                state.log_event(
                    "commit_aborted",
                    message=f"unexpected (round={state.current_round}, state={state_name})",
                )
                continue

            # Chốt wallclock TRƯỚC advance (advance reset round_start_time cho round sau)
            round_wallclock = time.time() - state.round_start_time
            state.model.load_state_dict(new_state_dict)
            state.log_event("aggregation_done", message=f"duration_ms={agg_ms:.1f}")
            _advance_to_next_round_locked(state)
            state.condition.notify_all()

        # ── Phase 4: eval + log (NO lock) — chạy SONG SONG client train round sau ─
        # Eval trên state_dict của round vừa xong (temp model, không chạm state.model),
        # nên an toàn khi round sau đang chạy. train round sau (~8-10s) >> eval (~3s).
        test_loss, accuracy, per_class, eval_ms = _do_evaluate(
            new_state_dict, state.test_loader, state.eval_device, state.dataset
        )
        _write_round_log_row(
            state, round_id, updates_snapshot, accuracy, test_loss,
            per_class, agg_ms, eval_ms, round_wallclock,
            status="partial" if is_partial else "ok",
        )
        state.log_event("evaluation_done", message=f"round={round_id} accuracy={accuracy:.4f}")

        status_str = "partial" if is_partial else "done"
        print(
            f"[server] round {round_id} {status_str} acc={accuracy:.4f} "
            f"loss={test_loss:.4f} agg={agg_ms:.1f}ms eval={eval_ms:.1f}ms(off-path)"
        )


# ============================================================
# gRPC servicer
# ============================================================


class FederatedServicer(federated_pb2_grpc.FederatedLearningServicer):
    def __init__(self, state: ServerState) -> None:
        self.s = state

    def GetRoundStatus(self, request, context):
        return federated_pb2.RoundStatus(
            current_round=self.s.current_round,
            state=self.s.state,
            num_rounds_total=self.s.num_rounds_total,
        )

    def GetGlobalModel(self, request, context):
        with self.s.condition:
            newly_seen = request.client_id not in self.s._seen_clients
            self.s.mark_client_seen_locked(request.client_id)
            if newly_seen:
                self.s.condition.notify_all()  # đánh thức pha rendezvous
            payload = serialize_state_dict(self.s.model)
            round_id = self.s.current_round
            current_state = self.s.state  # snapshot cho observability
        state_name = federated_pb2.RoundStatus.State.Name(current_state)
        # M6: kèm state vào message để post-mortem biết client pull lúc nào
        self.s.log_event(
            "model_pulled",
            client_id=request.client_id,
            message=f"bytes={len(payload)} state={state_name}",
        )
        return federated_pb2.ModelWeights(
            round_id=round_id,
            serialized_state_dict=payload,
        )

    def SubmitUpdate(self, request, context):
        with self.s.condition:
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

            # Accept + notify aggregation thread (M6: KHÔNG aggregate inline)
            self.s.received_updates[request.client_id] = request
            self.s.log_event(
                "update_received",
                client_id=request.client_id,
                num_samples=request.num_samples,
            )
            self.s.write_client_metadata_if_new(request)
            self.s.condition.notify_all()

        return federated_pb2.AckResponse(
            accepted=True,
            message="ok",
            server_round=self.s.current_round,
        )

    def _validate_update_locked(self, request):
        """4-layer validation per m3_plan.md §5. Caller giữ state.lock."""
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


# ============================================================
# Entry point
# ============================================================


def main() -> None:
    parser = build_cli_parser("Federated Learning server (M6)")
    parser.add_argument(
        "--bind",
        default="0.0.0.0:50051",
        help="bind address [host:port] - 0.0.0.0 cho LAN",
    )
    args = parser.parse_args()

    cfg = load_config(args.config, overrides=cli_overrides(args))
    if not args.experiment_name:
        cfg["experiment_name"] = "exp_federated_iid_smoke"
    set_seed(cfg["seed"])

    ctx = create_run_dir(cfg, args.config)
    write_run_meta(ctx, role="server")

    state = ServerState(cfg, ctx)  # M6: validate config trong __init__
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

    # M6: refresh round_start_time SAU server.start() để timeout window bắt đầu
    # từ lúc server thực sự ready, không phải lúc init. Tránh edge case round 1
    # timeout vì client startup (Python + torch + MNIST) mất vài giây.
    state.round_start_time = time.time()

    # M6: start background aggregation thread (state đã sẵn TRAINING + start_time mới)
    agg_thread = threading.Thread(
        target=run_aggregation_loop,
        args=(state,),
        daemon=True,
        name="aggregation-loop",
    )
    agg_thread.start()
    print(f"[server] listening on {args.bind}")
    print(f"[server] run_dir={ctx.run_dir}")
    print(
        f"[server] dataset={state.dataset} "
        f"num_rounds={state.num_rounds_total} "
        f"min_clients={state.min_clients}/{state.expected_count} "
        f"wait_timeout={state.wait_timeout}s "
        f"startup_timeout={state.startup_timeout}s "
        f"expected={sorted(state.expected_client_ids)}"
    )
    print("[server] state=TRAINING round=1 - waiting for clients")
    print("[server] Ctrl+C de dung")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\n[server] signal shutdown to aggregation thread...")
        with state.condition:
            state.shutdown = True
            state.condition.notify_all()
        agg_thread.join(timeout=2)
        if agg_thread.is_alive():
            print("[server] WARN: aggregation thread did not exit within 2s")
        server.stop(grace=2).wait()
        print("[server] stopped")


if __name__ == "__main__":
    main()
