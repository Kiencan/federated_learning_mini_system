# M6 Plan — WAIT_TIMEOUT + Dynamic min_clients (Fault Tolerance)

> Plan chi tiết cho Milestone 6. Tham khảo: [plan.md](../plan.md), [m5_plan.md](m5_plan.md), [milestone_report.md](milestone_report.md).

---

## 1. Mục tiêu

Server không bị stuck khi 1 client chậm/crash. Thêm cơ chế `WAIT_TIMEOUT` để server tự aggregate sau khoảng thời gian, kết hợp `min_clients=1` cho phép aggregate với 1 client còn lại. Đây là **milestone phức tạp nhất** từ M3 — refactor server từ sync aggregation (trong handler) sang **background thread**.

Sau M6, M7 (Straggler + Fault tolerance experiments) chỉ là test scenarios, không thêm code mới.

## 2. Scope

**IN — phải có:**
- Server refactor: aggregation chuyển từ sync (trong `SubmitUpdate` handler) → **background thread** với `threading.Condition`
- Logic timeout: 3 nhánh
  - Path A: tất cả client submit nhanh → aggregate ngay
  - Path B: hết timeout, ≥`min_clients` submitted → aggregate với những gì có (drop slow clients)
  - Path C: hết timeout, <`min_clients` submitted → skip round, log `round_skipped`
- `min_clients=1` (default) cho phép aggregate fault-tolerant
- CLI flags `--min-clients`, `--wait-timeout` cho test linh hoạt
- Events mới: `round_timeout`, `round_skipped`, `partial_aggregation`
- Update `_smoke_server.py` cho default mới (`min_clients=1`)
- Test 3 scenarios A/B/C trên localhost + cross-machine

**OUT — KHÔNG làm ở M6:**
- Straggler simulation code (`--straggler-delay` cho client) — M7
- Fault tolerance experiments (kill/restart client) — M7
- Server validation `data_split` mismatch — defer
- Async retry RPC client-side — không cần

## 3. Cấu hình cho M6

Update `config.yaml`:

```yaml
# Distributed
wait_timeout: 15          # giây - giữ 15s default, có thể override --wait-timeout
min_clients: 1            # ĐỔI từ 2 → 1 cho fault tolerance
expected_client_ids:      # vẫn 2 client
  - "client-0"
  - "client-1"
```

**Backward compat:** `tests/_smoke_server.py` (M3) cần `min_clients=2` để case 4 duplicate test work. Sau M6, smoke test sẽ explicit pass `--min-clients 2` qua CLI khi chạy server.

## 4. Design decisions

| Quyết định | Lựa chọn | Lý do |
|---|---|---|
| Aggregation runtime | Background thread riêng (`threading.Thread`) chạy aggregation_loop() | Không block `SubmitUpdate` handler; chuẩn pattern producer-consumer |
| Sync primitive | `threading.Condition` (wrap `self.lock`) | Cleaner than Event for "wait until X or timeout" |
| Khi nào aggregate? | (a) `received >= len(expected_client_ids)` (early, all done) HOẶC (b) timeout + `received >= min_clients` | 2 path rõ ràng; reject path C riêng |
| 0 client by timeout → ? | Skip round (`round_skipped` event), advance round counter, KHÔNG aggregate | Tránh aggregate model rỗng; vẫn tiến tiếp |
| Server giữ model cũ khi skip | Có (next round dùng model cũ) | Hợp lý: skip = "không có data để cập nhật" |
| Round_start_time | Cập nhật khi state chuyển vào TRAINING (sau aggregation/skip) | Định mốc cho timeout deadline |
| Background thread shutdown | Set `self.shutdown=True` + `condition.notify_all()` | Graceful exit khi Ctrl+C |
| `min_clients=1` vs `expected=2`: aggregate ngay khi 1 client xong? | KHÔNG — vẫn chờ timeout hoặc đủ expected | Tránh aggregate quá sớm khi 2 client đều fast nhưng client A chỉ sớm hơn vài ms; chỉ timeout mới fallback xuống min |
| New events | `round_timeout` (deadline hit), `round_skipped` (0 clients), `partial_aggregation` (<expected nhưng >=min) | Phân biệt 3 path cho phân tích Exp 3/4 |
| CLI flags mới | `--min-clients`, `--wait-timeout` ở `build_cli_parser` | Cho M3/M5 backward smoke tests + linh hoạt experiment |

## 5. Subtask breakdown

| # | Subtask | File | Owner | Branch | Estimate |
|---|---|---|---|---|---|
| M6.1 | CLI flags `--min-clients` (int), `--wait-timeout` (float) vào `build_cli_parser` + map cả 2 trong `cli_overrides` | `run_context.py` | **Máy 1** | `feature/m6-server-async-agg` (cùng branch với M6.2) | 10 min |
| M6.2 | Server refactor: background thread + 3-phase lock design (snapshot → heavy work no-lock → commit) + 3 paths + new events + `round_status` cột mới | `server.py` | **Máy 1** | `feature/m6-server-async-agg` | 90 min |
| M6.3 | Update docstring `tests/_smoke_server.py` ghi rõ prereq: "server phải start với `--min-clients 2` để case 4 (duplicate) không bị aggregate sớm". KHÔNG sửa logic script — script không tự start server | `tests/_smoke_server.py` (docstring only) | **Máy 1** | (cùng branch) | 5 min |
| M6.4 | Test Scenario A (both fast, no timeout), B (1 client only, hit timeout), C (0 clients, skip round) localhost | (run) | **Máy 1** | — | 25 min |
| M6.5 | Cross-machine test Scenario A + B | (run) | **Cả 2** | — | 15 min |
| M6.6 | Update `Report/milestone_report.md` với M6 section + 3 scenarios | report | **Máy 1** | direct commit dev | 25 min |

**Tổng:** ~3 giờ. M6 phức tạp hơn M4/M5 vì server-side refactor lớn.

## 6. Implementation (M6.2) — pseudocode

> **NGUYÊN TẮC LOCK QUAN TRỌNG:** KHÔNG giữ `state.lock` trong khi chạy FedAvg/evaluate/CSV write (~1-2s). Lock chỉ dùng cho **state transition + snapshot data**. Aggregation/eval chạy trên **local variables** (snapshot copy), sau đó reacquire lock để commit kết quả vào `s.model` và advance round. Tránh block mọi RPC + Ctrl+C trong vài giây.

### 6.1 `ServerState` thêm aggregation thread

```python
class ServerState:
    def __init__(self, cfg, ctx):
        # ... existing fields ...
        self.lock = threading.Lock()
        self.condition = threading.Condition(self.lock)  # NEW
        self.shutdown = False                             # NEW
        self.wait_timeout = float(cfg["wait_timeout"])    # NEW
        self.expected_count = len(self.expected_client_ids)  # typically 2
        # min_clients đã có từ M3, vẫn dùng (int)

        # M6: validate config invariants — fail-fast nếu sai
        if not (1 <= self.min_clients <= self.expected_count):
            raise ValueError(
                f"min_clients={self.min_clients} phải trong [1, {self.expected_count}]"
            )
        if self.wait_timeout <= 0:
            raise ValueError(f"wait_timeout={self.wait_timeout} phải > 0")
```

### 6.2 Background aggregation thread (NEW) — **lock-aware design**

```python
def run_aggregation_loop(state: ServerState, servicer: FederatedServicer):
    """Background thread: drive 1 round at a time. Release lock during heavy work."""
    while not state.shutdown:
        # ── Phase 1: wait for trigger (lock held) ────────────────────────────
        with state.condition:
            # Chờ vào state TRAINING (sau init hoặc sau advance round)
            while not state.shutdown and state.state != federated_pb2.RoundStatus.TRAINING:
                state.condition.wait(timeout=1)
            if state.shutdown:
                return

            deadline = state.round_start_time + state.wait_timeout
            round_id = state.current_round

            # Chờ: đủ expected HOẶC hết timeout
            while not state.shutdown:
                now = time.time()
                remaining = deadline - now
                if len(state.received_updates) >= state.expected_count:
                    break  # path A: early aggregation
                if remaining <= 0:
                    state.log_event(
                        "round_timeout",
                        message=f"received={len(state.received_updates)}/{state.expected_count}",
                    )
                    break  # path B hoặc C
                state.condition.wait(timeout=remaining)

            if state.shutdown:
                return

            # ── Snapshot & decide path (vẫn trong lock) ────────────────────
            received_count = len(state.received_updates)
            if received_count >= state.min_clients:
                # Path A hoặc B: chuẩn bị aggregate
                state.state = federated_pb2.RoundStatus.AGGREGATING
                updates_snapshot = list(state.received_updates.items())  # immutable snapshot
                is_partial = received_count < state.expected_count
            else:
                # Path C: skip
                state.log_event(
                    "round_skipped",
                    message=f"received=0/{state.expected_count}",
                )
                # Ghi round_log row "skipped" trước khi advance (xem §6.7)
                servicer._write_skipped_round_row(round_id, received_count)
                _advance_to_next_round_locked(state)
                state.condition.notify_all()
                continue

        # ── Phase 2: heavy work OUTSIDE lock ─────────────────────────────────
        if is_partial:
            state.log_event(
                "partial_aggregation",
                message=f"received={received_count}/{state.expected_count}",
            )

        # FedAvg + evaluate trên LOCAL variables — không chạm s.model
        new_state_dict, agg_ms = _do_fedavg(updates_snapshot)
        test_loss, accuracy, per_class, eval_ms = _do_evaluate(
            new_state_dict, state.test_loader, state.eval_device
        )
        # CSV write — events.csv có _log_lock riêng, round_log.csv chỉ thread này ghi
        servicer._write_round_log_row(
            round_id, updates_snapshot, accuracy, test_loss,
            per_class, agg_ms, eval_ms, status="ok" if not is_partial else "partial",
        )

        # ── Phase 3: commit + advance (lock held, nhanh) ─────────────────────
        with state.condition:
            state.model.load_state_dict(new_state_dict)
            state.log_event("aggregation_done", message=f"duration_ms={agg_ms:.1f}")
            state.log_event("evaluation_done", message=f"accuracy={accuracy:.4f}")
            _advance_to_next_round_locked(state)
            state.condition.notify_all()
```

**Lock duration analysis:**
- Phase 1 lock: ~timeout seconds (mostly waiting via `condition.wait`, releases lock internally)
- Phase 2 (no lock): FedAvg ~3ms + eval ~1000ms + CSV ~10ms ≈ **1s of zero lock contention**
- Phase 3 lock: state mutation + log events ≈ **<10ms**

Trong Phase 2, mọi RPC khác (SubmitUpdate, GetGlobalModel, GetRoundStatus) đều có thể chạy. SubmitUpdate sẽ thấy `state=AGGREGATING` → reject `state_not_training`. GetGlobalModel returns OLD model (chưa load_state_dict mới) — đúng cho round đã đóng.

### 6.3 `SubmitUpdate` handler — chỉ snapshot + notify

```python
def SubmitUpdate(self, request, context):
    with self.s.lock:
        # ... 4-layer validation as before ...
        self.s.received_updates[request.client_id] = request
        self.s.log_event("update_received", ...)
        self.s.write_client_metadata_if_new(request)
        self.s.condition.notify_all()  # wake aggregation thread
    return federated_pb2.AckResponse(accepted=True, ...)
```

### 6.4 `_advance_to_next_round_locked` (NEW helper) — caller giữ lock

```python
def _advance_to_next_round_locked(state):
    """Chuyển sang round tiếp theo HOẶC set DONE."""
    if state.current_round >= state.num_rounds_total:
        state.state = federated_pb2.RoundStatus.DONE
        state.log_event("round_done", message="final state DONE")
    else:
        state.current_round += 1
        state.received_updates = {}
        state.round_start_time = time.time()
        state.state = federated_pb2.RoundStatus.TRAINING
        state.log_event("round_done", message=f"advancing_to_round={state.current_round}")
```

### 6.5 Server `main()` start/stop thread

```python
def main():
    # ... existing setup ...
    agg_thread = threading.Thread(target=run_aggregation_loop, args=(state, servicer), daemon=True)
    agg_thread.start()
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        with state.condition:
            state.shutdown = True
            state.condition.notify_all()
        agg_thread.join(timeout=2)
        server.stop(grace=2).wait()
```

Vì heavy work (Phase 2) **không giữ lock**, set `shutdown=True` luôn được lock ngay → thread thoát trong Phase 1 hoặc Phase 3 sau ≤1 iter của `condition.wait(timeout=1)`. **Acceptance "thread join < 2s" được đảm bảo.**

### 6.6 Remove cũ `_aggregate_and_evaluate_locked` — tách thành 2 hàm pure

Hàm cũ trong server.py M5 vừa làm logic (read state) vừa làm work (FedAvg/eval/write). M6 tách:

- `_do_fedavg(updates_snapshot) -> (new_state_dict, agg_ms)` — pure, không chạm state
- `_do_evaluate(state_dict, loader, device) -> (loss, acc, per_class, eval_ms)` — pure
- `_write_round_log_row(round_id, updates_snapshot, ...)` — chỉ aggregation thread gọi → không cần lock (single writer)
- `_write_skipped_round_row(round_id, received_count)` — tương tự

### 6.7 `round_log.csv` schema — thêm cột `round_status` (M6 mới)

Thêm 1 cột ở vị trí phù hợp (sau `num_clients_received`):

```text
round_id, num_clients_received, round_status, accuracy, test_loss, ..., client_X_*
```

Giá trị `round_status`:
- `"ok"` — Path A (aggregate với đủ expected clients)
- `"partial"` — Path B (timeout + ≥min_clients)
- `"skipped"` — Path C (timeout + 0 clients)

Row "skipped" có `num_clients_received=0`, `accuracy`/`test_loss`/per-class/timings để **trống string** (`""`), `client_0_*`/`client_1_*` cũng trống. Server eval gần nhất giữ `s.model` cũ; KHÔNG eval lại trong skip path (không có model mới để đánh giá).

**Backward compat:** schema mới có thêm 1 cột so với M3-M5. Centralized run không bị ảnh hưởng vì dùng schema khác (epoch-based). Analysis scripts cho M3-M5 data sẽ vẫn parse được nếu dùng `csv.DictReader` (cột thiếu = None).

## 7. Test plan (M6.4 + M6.5)

### 7.1 Scenario A — Both clients fast (no timeout)

```powershell
# Server với defaults M6 (min_clients=1, wait_timeout=15s)
python server.py --num-rounds 3 --run-id m6_scenario_a
# 2 client như bình thường
python client.py --client-id client-0 --shard-id 0 --num-shards 2
python client.py --client-id client-1 --shard-id 1 --num-shards 2
```

**Kỳ vọng:**
- 3 round chạy bình thường
- Mỗi round: 2 client submit trước 15s → aggregate ngay (path early)
- KHÔNG có `round_timeout`/`partial_aggregation`/`round_skipped` events
- Accuracy ~99% như M4

### 7.2 Scenario B — 1 client present (fast enough), hit timeout, partial aggregation

**Điều kiện rõ:** Client-0 hoàn thành training + submit **TRƯỚC** `wait_timeout`. Client-1 KHÔNG được start. Đây KHÔNG phải "slow client" scenario (M7 sẽ test bằng `--straggler-delay`).

```powershell
# Server: wait_timeout=10s đủ cho client-0 train (~7s) + buffer
python server.py --num-rounds 3 --wait-timeout 10 --min-clients 1 --run-id m6_scenario_b
# CHỈ client-0 (train ~7s, submit trước deadline 10s)
python client.py --client-id client-0 --shard-id 0 --num-shards 2
# KHÔNG start client-1
```

**Kỳ vọng:**
- Mỗi round: client-0 submit @~7s → server đợi client-1 đến deadline (10s)
- Sau 10s: log `round_timeout received=1/2` → log `partial_aggregation received=1/2` → aggregate với chỉ client-0 weights → advance
- 3 round chạy được (~30s tổng, dominated bởi timeout)
- events.csv có 3 `partial_aggregation` events
- round_log.csv: 3 row với `round_status=partial`, `num_clients_received=1`
- Accuracy có thể không cao (chỉ 1 nửa data MNIST IID — kỳ vọng ~95-97%)

**Note về timing:** nếu `wait_timeout` < train_time của client (vd `--wait-timeout 5`), client-0 sẽ miss deadline → sau khi train xong, submit gặp `state_not_training` reject (server đã skip round) → exit 3. Đây là trường hợp riêng (test "slow client"), không phải Scenario B chính.

### 7.3 Scenario C — 0 clients (skip round)

```powershell
# Server với wait_timeout=5s cho test nhanh
python server.py --num-rounds 3 --wait-timeout 5 --min-clients 1 --run-id m6_scenario_c
# KHÔNG start client nào
```

**Kỳ vọng:**
- Mỗi round: 0 client submit, hết 5s → log `round_timeout received=0/2` → log `round_skipped` → advance KHÔNG aggregate
- 3 round chạy được (~15s tổng)
- events.csv có 3 `round_skipped` events
- round_log.csv: có thể có row hoặc bỏ qua — quyết định trong implementation (recommend: vẫn 1 row với `num_clients_received=0`, accuracy/loss giữ giá trị eval cuối cùng hoặc 0)

### 7.4 Smoke test backward compat (`_smoke_server.py`)

```powershell
# Smoke test M3 cần min_clients=2 cho case 4 (duplicate)
python server.py --num-rounds 1 --min-clients 2 --run-id m6_smoke_backward
python tests\_smoke_server.py
# Phải pass 9/9 case như trước
```

### 7.5 Cross-machine Scenario A + B (M6.5)

- A: cả 2 máy chạy bình thường — verify timeout không trigger
- B: chỉ Máy 1 chạy client-0, Máy 2 không chạy → server timeout, aggregate với 1

## 8. Acceptance criteria

- [ ] Server start có background aggregation thread, Ctrl+C shutdown sạch (thread join < 2s)
- [ ] Scenario A: 3 round chạy không stuck, **không có** event timeout/skip/partial
- [ ] Scenario B: 3 round chạy, **mỗi round có** `partial_aggregation` event, accuracy hợp lý (>50% với 1 client IID half data)
- [ ] Scenario C: 3 round chạy, **mỗi round có** `round_skipped` event, server vẫn advance và set DONE cuối cùng
- [ ] `tests/_smoke_server.py` vẫn pass 9/9 case khi gọi với `--min-clients 2`
- [ ] Config snapshot có `wait_timeout` và `min_clients` đúng giá trị runtime
- [ ] Cross-machine Scenario A pass (acc tương đương M4.4 IID hoặc M5.4 Non-IID)
- [ ] Cross-machine Scenario B pass

## 9. Rủi ro & lưu ý

1. **Race condition giữa aggregation thread và SubmitUpdate**: Cả 2 cùng giữ `self.lock` qua `Condition`. Đảm bảo state transition (TRAINING ↔ AGGREGATING ↔ TRAINING) luôn trong lock. Test bằng cách dùng thread sanitizer hoặc nhìn log.

2. **Deadlock risk khi shutdown**: Aggregation thread phải check `state.shutdown` thường xuyên. `condition.wait(timeout=X)` đảm bảo không block vô tận.

3. **`_aggregate_and_evaluate_locked` đang gọi `_advance_to_next_round_locked`**: cần đảm bảo lock vẫn được giữ qua cả 2 hàm (caller đã giữ). Document rõ.

4. **Round counter có nhảy đúng không?** Khi skip round vẫn advance counter. Nếu num_rounds=3 và 3 round đều skip → state=DONE, round_log có thể empty hoặc 3 row "skip". Tùy thiết kế.

5. **Client polling stale_round**: Nếu client A submit chậm sau khi server đã timeout + advance, ack sẽ là `stale_round` → exit 3. Đây là behavior đã có từ M3, không cần đổi.

6. **`min_clients=1` impact lên M3-M5 tests**: tất cả test trước M6 ngầm assume `min_clients=2`. M6.3 cần update _smoke_server.py invocation docs (CLI override) hoặc tách test có/không min_clients.

7. **`expected_count = len(expected_client_ids)`**: cần làm rõ khái niệm "expected" (config whitelist) vs "received" (đã submit) vs "min" (threshold aggregate). Comment trong code.

8. **Eval CPU bottleneck**: aggregation thread sẽ chạy eval ~1s. Trong thời gian này, `condition.wait()` của thread khác vẫn block? Không, vì `_aggregate_and_evaluate_locked` đang giữ lock — đúng. Aggregation thread đơn — không có race.

## 10. Sau M6 xong

Update `Report/milestone_report.md`:
- Overview: M6 → ✅ Done
- Section M6 với:
  - Mô tả refactor (sync → async aggregation thread)
  - 3 scenarios A/B/C kết quả
  - events.csv samples cho mỗi scenario
  - Round wallclock impact (kỳ vọng tương đương M4/M5 cho Scenario A)
  - Discussion: ý nghĩa cho **Experiment 3 (Straggler)** và **Experiment 4 (Fault tolerance)**
- Bước tiếp theo → M7 (Straggler simulation + crash/reconnect scenarios)

**Sau M6, infrastructure đã sẵn sàng cho M7** — M7 chỉ thêm `--straggler-delay` cho client và chạy 4 scenarios trong plan.md.

---

## 11. Workflow

```text
dev
  └── feature/m6-server-async-agg (Máy 1, M6.1+M6.2+M6.3)
       → PR review (chú ý threading correctness)
       → merge dev → M6.4 + M6.5 (test) → M6.6 (report)
```

Đây là 1 PR lớn (~90 min code + 15 min test refactor). Có thể split nếu Máy 1 muốn (vd M6.1 CLI flags riêng), nhưng ghép gọn hơn.

**Lưu ý cho reviewer:** focus vào (a) lock semantics quanh Condition, (b) shutdown path, (c) 3 path logic đúng spec.
