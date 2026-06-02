# M7 Plan — Straggler Simulation + Crash/Reconnect

> Plan chi tiết cho Milestone 7 (cuối cùng về implementation). Tham khảo: [plan.md](../plan.md), [m6_plan.md](m6_plan.md), [milestone_report.md](milestone_report.md).

---

## 1. Mục tiêu

Tận dụng infrastructure timeout/partial của M6 để **chạy 2 thí nghiệm thực tế**:

- **Straggler simulation** (Exp 3 trong báo cáo): client chậm cố ý, đo impact lên round time + accuracy
- **Crash + reconnect** (Exp 4): client bị "crash" (Ctrl+C) giữa run, server tiếp tục với 1 client; sau đó client restart và tham gia tiếp

M7 là **milestone hẹp nhất** từ M3 — code change tối thiểu (~5 dòng client). Phần lớn là test scenarios + analysis.

Sau M7, **toàn bộ implementation done** → chuyển phase Experiments.

## 2. Scope

**IN — phải có:**
- Client thêm CLI flag `--straggler-delay N` (float, giây) — sleep N giây trước khi `SubmitUpdate`
- 2 straggler scenarios (S1 no effective timeout, S2 timeout fires)
- 1 crash/reconnect scenario (F1) — thao tác manual với Ctrl+C
- Verify events.csv ghi đủ `partial_aggregation` cho các round client-1 vắng mặt
- Log timing impact của straggler vào round_log

**OUT — KHÔNG làm ở M7:**
- Server code change — M6 infrastructure đã đủ
- Tự động hoá crash/reconnect (manual Ctrl+C đủ)
- Multi-straggler (chỉ test 1 client làm straggler)
- Async retry RPC khi reject (giữ `sys.exit(3)`)
- Network partition / network delay (chỉ test compute delay)

## 3. Cấu hình cho M7

Mở rộng `config.yaml` (đã có sẵn key `straggler_delay`):

```yaml
straggler_delay: 0        # giây — sleep trước SubmitUpdate. Default 0 = no-op.
                          # Override --straggler-delay 5 cho test S1
                          # Override --straggler-delay 20 cho test S2
```

CLI override (đã có pattern `--data-split`). Validation: `straggler_delay >= 0`.

## 4. Design decisions

| Quyết định | Lựa chọn | Lý do |
|---|---|---|
| Vị trí sleep | SAU `t_ul = time.perf_counter()` (bên trong upload phase đo) | Delay được tính vào `upload_ms` tự nhiên — semantically đúng (server thấy client slow từ góc upload). Cũng phản ánh trong `round_wallclock_sec`. |
| Type của `straggler_delay` | `float` | Cho phép subsecond delays (vd 0.5s) nếu cần fine-tune |
| `straggler_delay < 0` | Argparse `type=float` KHÔNG tự reject âm — **client `main()` validate** + exit 4 | Argparse chỉ reject non-number, không reject âm |
| `straggler_delay = 0` | No-op, không print, không sleep | Default behavior, không log noise |
| `straggler_delay > 0` | Print "STRAGGLER simulating: sleep Ns" | Observability; KHÔNG có field riêng trong update message |
| Logging timing impact | **`round_log.csv.round_wallclock_sec`** là nguồn chính; `upload_ms` của client cũng bao gồm sleep | events.csv không log timing breakdown — không sửa server để giữ scope hẹp |
| Server validation `--straggler-delay` | KHÔNG validate (kể cả âm) — chỉ snapshot config | Server data-agnostic; negative value chỉ là bad metadata, không ảnh hưởng runtime. Validation âm chỉ bắt buộc client-side. |
| CLI flag scope | Đưa vào `build_cli_parser()` chung để server cũng nhận (snapshot config) | Đồng nhất pattern `--data-split` từ M5 |
| Crash test timing | Manual Ctrl+C, acceptance flexible (không cứng pattern N+M+K rounds) | Cửa sổ kill rất hẹp với client loop tự động — không thể guarantee exact pattern |

## 5. Subtask breakdown

| # | Subtask | File | Owner | Branch | Estimate |
|---|---|---|---|---|---|
| M7.1 | CLI `--straggler-delay` vào `build_cli_parser()` chung + `cli_overrides()` | `run_context.py` | **Máy 1** | `feature/m7-straggler` | 5 min |
| M7.2 | Client `straggler_delay` injection: print + `time.sleep(N)` trước SubmitUpdate; validate ≥ 0 | `client.py` | **Máy 1** | (cùng branch) | 10 min |
| M7.3 | Smoke verify: `--straggler-delay 0` không break Scenario A; `--straggler-delay 5` localhost work | (run) | **Máy 1** | — (sau push) | 10 min |
| M7.4 | Scenario S1 localhost (no effective timeout): server `--wait-timeout 60`, client-1 delay 5s | (run) | **Máy 1** | — | 10 min |
| M7.5 | Scenario S2 localhost (timeout fires): server `--wait-timeout 15`, client-1 delay 20s → expect partial + reject | (run) | **Máy 1** | — | 10 min |
| M7.6 | Scenario F1 cross-machine (crash + reconnect): **12 round**, manual Ctrl+C/restart Máy 2; **target flexible** ≥3 ok đầu + ≥2 partial giữa + ≥1 ok recovery | (run) | **Cả 2** | — | 20 min |
| M7.7 | Update `Report/milestone_report.md` với M7 section + Exp 3/4 data preview | report | **Máy 1** | direct commit dev | 20 min |

**Tổng ước tính:** ~1.5 giờ (scope hẹp nhất).

## 6. Implementation (M7.1 + M7.2) — pseudocode

### 6.1 `run_context.py` — thêm `--straggler-delay`

```python
# Trong build_cli_parser():
p.add_argument(
    "--straggler-delay",
    type=float,
    default=None,
    help="M7: sleep N giây trước SubmitUpdate (client only). "
         "Server: chỉ snapshot vào config; Client: simulate slow client.",
)

# Trong cli_overrides():
"straggler_delay": args.straggler_delay,
```

### 6.2 `client.py` — inject sleep trong `do_one_round()` hoặc trước

Thêm validation ở `main()` SAU `cfg = load_config(...)`:

```python
straggler_delay = float(cfg.get("straggler_delay", 0))
if straggler_delay < 0:
    print(f"[client {args.client_id}] ERROR: straggler_delay phải >= 0, got {straggler_delay}")
    sys.exit(4)
```

Trong `do_one_round()` SAU `train_local()` + log "train done", **bên trong upload phase đo** (sau `t_ul = time.perf_counter()`), TRƯỚC `stub.SubmitUpdate`:

```python
# Buoc 4: Submit update
t_ul = time.perf_counter()

# M7: straggler simulation — sleep INSIDE upload measurement window
# → delay được tính vào upload_ms tự nhiên (server thấy client slow từ network)
straggler_delay = float(cfg.get("straggler_delay", 0))
if straggler_delay > 0:
    print(
        f"[client {client_id}] round={round_id} STRAGGLER simulating: "
        f"sleep {straggler_delay}s"
    )
    time.sleep(straggler_delay)

try:
    ack = stub.SubmitUpdate(...)
except grpc.RpcError as e:
    ...
upload_ms = (time.perf_counter() - t_ul) * 1000  # bao gồm straggler delay
```

`straggler_delay` đọc từ `cfg` bên trong `do_one_round()` để không phải sửa signature.

### 6.3 Hệ quả timing measurement

- **`upload_ms` (client-side)**: bao gồm `straggler_delay` + `serialize_state_dict` (gọi inside `ClientUpdate(...)` constructor sau `t_ul`) + network upload + server response wait.
  - **Quan trọng khi implement:** giữ `serialize_state_dict(model)` **bên trong** `ClientUpdate(...)` constructor sau `t_ul = perf_counter()`. Nếu refactor để serialize trước `t_ul`, breakdown này không còn đúng.
- **`round_wallclock_sec` (server-side, round_log.csv)**: phản ánh full impact của straggler từ góc server (timeout-driven hoặc wait-for-all)
- **events.csv `update_received`**: KHÔNG có timing breakdown — chỉ ghi `num_samples`. Source of truth cho impact là `round_log.csv`

### 6.4 Server `straggler_delay` field trong run_meta

Khi server nhận update có client với `straggler_delay > 0`, có thể log vào events.csv. Nhưng client không gửi giá trị này — chỉ chính delay nó. Không cần thêm logic server. **Skip.**

## 7. Test plan

### 7.1 M7.3 — Smoke verify (15 phút)

```powershell
# Server defaults (min_clients=1, wait_timeout=30)
python server.py --num-rounds 2 --run-id m7_smoke

# Client-0 KHÔNG có straggler — verify backward compat
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --server-addr 127.0.0.1:50051

# Client-1 với delay 5s
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --server-addr 127.0.0.1:50051 --straggler-delay 5
```

Kỳ vọng:
- Client-1 in `STRAGGLER simulating: sleep 5s` mỗi round
- 2 round hoàn thành, accuracy ~99% (giống M6 Scenario A bình thường)
- Round wallclock tăng ~5s (do client-1 chậm)

### 7.2 Scenario S1 — No effective timeout (M7.4)

**Setup:** wait_timeout RỘNG, đủ chỗ cho straggler đến deadline.

```powershell
# Server: pass --straggler-delay 5 để snapshot config phản ánh scenario
# (server không dùng giá trị này runtime)
python server.py --num-rounds 3 --wait-timeout 60 --min-clients 2 --straggler-delay 5 --run-id m7_s1_no_timeout

python client.py --client-id client-0 --shard-id 0 --num-shards 2 --server-addr 127.0.0.1:50051

python client.py --client-id client-1 --shard-id 1 --num-shards 2 --server-addr 127.0.0.1:50051 --straggler-delay 5
```

Kỳ vọng:
- 3 round all `round_status=ok` (cả 2 client submit trong 60s window)
- Accuracy curve giống M4.4 IID (~99%)
- Round wallclock ≈ 6s train + 5s straggler + 1s eval = ~12-15s (tăng so với baseline ~9s)
- events.csv: KHÔNG có `round_timeout` event

### 7.3 Scenario S2 — Timeout fires, straggler dropped (M7.5)

**Setup:** wait_timeout NGẮN hơn straggler delay → server timeout, partial aggregate, straggler reject sau.

```powershell
# Server: pass --straggler-delay 20 để snapshot config phản ánh scenario
python server.py --num-rounds 3 --wait-timeout 15 --min-clients 1 --straggler-delay 20 --run-id m7_s2_timeout_drop

python client.py --client-id client-0 --shard-id 0 --num-shards 2 --server-addr 127.0.0.1:50051

python client.py --client-id client-1 --shard-id 1 --num-shards 2 --server-addr 127.0.0.1:50051 --straggler-delay 20
```

Kỳ vọng:
- Client-0 train ~6s + submit ~7s → in window 15s
- Client-1 train ~6s + sleep 20s = ~26s → MISS deadline
- Server: round_timeout @15s → partial_aggregation với client-0 only
- Client-1 sau khi sleep xong submit → server đã sang round 2, reject `stale_round` → **exit 3** (round 1 expected behavior, không cần restart)
- **3 round `round_status=partial` server-side phụ thuộc CLIENT-0 vẫn chạy đến DONE.** Client-1 exit ở round 1 không ảnh hưởng — Path B với 1 client là expected.
- Accuracy curve: client-0 IID half data (~98-99%)
- `round_wallclock_sec` ≈ 7 s + 8 s wait = 15s (= wait_timeout, vì timeout fire)

**Lưu ý:** Sau round 1 client-1 exit, các round 2-3 server vẫn timeout 15s rồi partial với client-0 → 3 row `partial` đầy đủ. KHÔNG cần restart client-1 — đây là test "drop straggler".

### 7.4 Scenario F1 — Crash + Reconnect (M7.6, cross-machine)

**Setup:** num_rounds=12 (dư cửa sổ reconnect timing), manual Ctrl+C.

```powershell
# Máy 1: server (12 round để có dư cửa sổ)
python server.py --bind 0.0.0.0:50051 --num-rounds 12 --wait-timeout 30 --min-clients 1 --run-id m7_f1_crash

# Máy 1: client-0
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --server-addr 127.0.0.1:50051

# Máy 2: client-1 (chạy bình thường)
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --server-addr 192.168.2.30:50051
```

**Quy trình manual (targets, không phải pattern cứng):**

| Phase | Action | Target |
|---|---|---|
| **Phase 1 — Healthy** | Cả 2 client chạy bình thường | ≥ 3 round liên tiếp `ok` |
| **Phase 2 — Crash** | **Ctrl+C client-1 trên Máy 2** sau khi thấy ≥ 3 round done | Catch client-1 BEFORE next round submit (cửa sổ ~vài giây giữa rounds) |
| **Phase 3 — Degraded** | Chỉ client-0 submit | ≥ 2 round liên tiếp `partial` |
| **Phase 4 — Recovery** | **Restart client-1 trên Máy 2** với cùng command | ≥ 1 round `ok` sau restart |

**Acceptance flexible (không pattern cứng):**

- [ ] Có **đoạn liên tiếp** `round_status=ok` ở đầu (≥3 round)
- [ ] Có **đoạn liên tiếp** `round_status=partial` ở giữa (≥2 round)
- [ ] Có **ít nhất 1 round** `round_status=ok` sau restart
- [ ] Server không stuck, set DONE sau round 12
- [ ] events.csv ghi các transitions: `update_received` cho client-0 mọi round; `update_received` cho client-1 chỉ ở rounds healthy + recovery

**Tại sao flexible:** Client loop tự động bắt round mới gần như ngay khi server chuyển TRAINING. "Kill sau round N done, trước round N+1 start" có cửa sổ ~1-2s polling interval — rất khó canh chính xác. Pattern lý tưởng (vd `4 ok + 4 partial + 4 ok`) chỉ là TARGET, không yêu cầu.

**Nếu lệch:** rerun F1 hoặc tăng `num_rounds` lên 16/20 để có thêm cơ hội.

**Phân tích cho Exp 4:**
- Accuracy degradation khi 1 client crashed (so sánh acc của partial rounds vs ok rounds)
- Recovery time: bao nhiêu round sau restart accuracy quay lại trước crash?

## 8. Acceptance criteria

- [ ] M7.1+M7.2 syntax + import OK
- [ ] `--straggler-delay 0` không phá Scenario A (backward compat)
- [ ] `--straggler-delay -1` → client `main()` validate + exit code 4 (argparse type=float không tự reject âm)
- [ ] **Server config snapshot** ghi đúng `straggler_delay` khi server được chạy với `--straggler-delay` CLI. (Client KHÔNG tạo `run_dir` riêng — không có snapshot client-side.) **Khuyến nghị:** S1/S2 pass `--straggler-delay` cho server để snapshot phản ánh scenario; F1 có thể để default 0 (không phải straggler scenario).
- [ ] **Scenario S1:** 3 round `round_status=ok`, accuracy ~99%, **`round_wallclock_sec` tăng ~5s/round** so với baseline M4
- [ ] **Scenario S2:** 3 round server `round_status=partial`; client-1 exit code 3 sau round 1 (expected, không cần restart). Client-0 hoàn thành đến DONE.
- [ ] **Scenario F1:** flexible pattern — ≥3 ok đầu, ≥2 partial giữa, ≥1 ok sau restart (xem §7.4)
- [ ] Cross-machine F1: client-1 reconnect được sau Ctrl+C
- [ ] **Round wallclock impact của straggler đo qua `round_log.csv.round_wallclock_sec`** (KHÔNG qua events.csv — server không log timing breakdown)
- [ ] M7 section trong milestone_report.md có data preview cho Exp 3 + Exp 4

## 9. Rủi ro & lưu ý

1. **Backward compat:** `straggler_delay` default 0 → no-op. Tất cả test M3-M6 vẫn pass.

2. **Crash test phụ thuộc thao tác user:** Máy 2 user phải Ctrl+C đúng thời điểm — **sau khi thấy ≥3 round ok**, ngay trong cửa sổ giữa 2 round (sau client-1 in `<<< round N done`, trước `>>> round N+1 bat dau`). Window ~1-2s polling interval, hẹp.

   **Recommendation:** đợi client-1 in `<<< round N done` rồi Ctrl+C ngay. Nếu trễ, client-1 đã pull/train round N+1 → kill giữa training → khi server timeout vẫn skip → 1 round mất nhưng kết quả vẫn quy về Phase 3 partial.

3. **Reconnect timing:** Restart client-1 phải khi server **còn đủ round phía sau** (≥1 round) và đang TRAINING. Nếu khởi động chậm hoặc dồn đến cuối, client-1 có thể chỉ join 1 round recovery hoặc không kịp.

   **Mitigation:** `num_rounds=12` cho dư cửa sổ. Nếu thất bại (vd không có round ok nào sau restart), **rerun F1 với `num_rounds=16` hoặc `20`** để có thêm cơ hội.

4. **`time.sleep()` block thread:** Client đang sleep không phản hồi gì. Nếu Ctrl+C trong khi sleep, exception propagates → client exit. Acceptable.

5. **S2 client-1 exit 3 → events.csv ghi `update_rejected`:** server log đúng `stale_round`. Bằng chứng cho Exp 3 finding.

6. **Round 1 cold start vẫn ảnh hưởng:** Máy 2 first round có Python startup ~10s. Để S1/S2 work đúng nghĩa, cần round 1 có thể bị skewed. Acceptable — focus phân tích round 2+ steady-state.

## 10. Sau M7 xong — Phase Experiments

Toàn bộ implementation hoàn thành. Chuyển sang phase **Experiments + Báo cáo cuối kỳ**.

### 10.1 Experiments cần chạy (sau M7)

| Exp | Mục tiêu | Data đã có | Cần thêm |
|---|---|---|---|
| **Exp 1** Centralized vs Federated | So sánh wall-clock + accuracy 30 epoch/round | M1 smoke (2 epoch) + M4 IID 5 round | Centralized 30 epoch + Federated IID 30 round (~15-20 phút mỗi run) |
| **Exp 2** IID vs Non-IID | Convergence + per-class accuracy comparison | M4.4 IID + M5.4 Non-IID (đủ) | (optional) chạy lại với 30 round để rõ hội tụ hơn |
| **Exp 3** Straggler | Round time + accuracy với delay khác nhau | — | Chạy S1 + S2 với multi-rounds (10-20 round) để có curve rõ |
| **Exp 4** Fault tolerance | Recovery behavior + accuracy degradation | — | F1 với phân tích recovery time |

### 10.2 Visualization cần làm

- `accuracy_per_round.png`: 3 đường (Federated IID, Federated Non-IID, Centralized baseline)
- `per_class_accuracy_iid_vs_noniid.png`: bar chart 10 class × 2 setup, round 5
- `round_time_breakdown.png`: stacked bar (download/train/upload/wait) per scenario
- `communication_overhead.png`: cumulative MB transferred
- `straggler_impact.png`: round time vs straggler_delay
- `fault_tolerance_recovery.png`: accuracy curve với crash/reconnect

### 10.3 Báo cáo cuối kỳ

Tổng hợp 5 vấn đề distributed systems (§7 ytuong.md):

1. Communication overhead (Exp 1 data)
2. Synchronization model (M6 design + Exp 3 data)
3. Straggler problem (Exp 3)
4. Fault tolerance (Exp 4)
5. Data heterogeneity (Exp 2 + M5 findings)

---

## 11. Workflow

```text
dev
  └── feature/m7-straggler (Máy 1, M7.1+M7.2)
       → PR review → merge dev → M7.3 + M7.4 + M7.5 localhost
       → M7.6 cross-machine (cả 2 máy)
       → M7.7 update report
```

Scope hẹp → 1 PR nhỏ + multiple test scenarios. Branch xóa sau merge như các milestone trước.

**Lưu ý reviewer:** focus vào (a) validation `straggler_delay >= 0`, (b) vị trí sleep đúng trước SubmitUpdate, (c) backward compat khi `delay=0`.
