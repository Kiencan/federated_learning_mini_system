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
| Vị trí sleep | TRƯỚC `SubmitUpdate`, SAU `train_local` + `serialize_state_dict` | Khớp ytuong.md §8 Exp 3: "time.sleep(N) trước khi gửi weights". Train timing measurement không bị ảnh hưởng. |
| Type của `straggler_delay` | `float` | Cho phép subsecond delays (vd 0.5s) nếu cần fine-tune |
| `straggler_delay < 0` | Argparse reject với rõ error | Defensive |
| `straggler_delay = 0` | No-op, không print | Default behavior, không log noise |
| `straggler_delay > 0` | Print thông báo "straggler simulating: sleep Ns" + log timing trong update.timing | Observability |
| Server validation `--straggler-delay` | KHÔNG validate | Server data-agnostic about client behavior; chỉ snapshot config nếu user pass |
| CLI flag scope | Đưa vào `build_cli_parser()` chung để server cũng nhận (snapshot config) | Đồng nhất pattern `--data-split` từ M5 |
| Crash test | Manual Ctrl+C trên Máy 2 (M3.8 đã có precedent) | Tự động hoá phức tạp, M7 scope hẹp |

## 5. Subtask breakdown

| # | Subtask | File | Owner | Branch | Estimate |
|---|---|---|---|---|---|
| M7.1 | CLI `--straggler-delay` vào `build_cli_parser()` chung + `cli_overrides()` | `run_context.py` | **Máy 1** | `feature/m7-straggler` | 5 min |
| M7.2 | Client `straggler_delay` injection: print + `time.sleep(N)` trước SubmitUpdate; validate ≥ 0 | `client.py` | **Máy 1** | (cùng branch) | 10 min |
| M7.3 | Smoke verify: `--straggler-delay 0` không break Scenario A; `--straggler-delay 5` localhost work | (run) | **Máy 1** | — (sau push) | 10 min |
| M7.4 | Scenario S1 localhost (no effective timeout): server `--wait-timeout 60`, client-1 delay 5s | (run) | **Máy 1** | — | 10 min |
| M7.5 | Scenario S2 localhost (timeout fires): server `--wait-timeout 15`, client-1 delay 20s → expect partial + reject | (run) | **Máy 1** | — | 10 min |
| M7.6 | Scenario F1 cross-machine (crash + reconnect): 8 round, Ctrl+C Máy 2 sau round 4, restart sau round 7 | (run) | **Cả 2** | — | 20 min |
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

Trong `do_one_round()` SAU `train_local()` + log "train done", TRƯỚC build `ClientUpdate`:

```python
# M7: straggler simulation (no-op nếu delay=0)
if straggler_delay > 0:
    print(
        f"[client {client_id}] round={round_id} STRAGGLER simulating: "
        f"sleep {straggler_delay}s"
    )
    time.sleep(straggler_delay)
```

`straggler_delay` cần truyền vào `do_one_round()` — thêm vào signature. Hoặc lấy từ `cfg["straggler_delay"]` bên trong `do_one_round()` (cfg đã được pass).

→ **Khuyến nghị:** đọc từ `cfg` bên trong `do_one_round` để không phải sửa signature. Đơn giản hơn.

### 6.3 Server `straggler_delay` field trong run_meta

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
python server.py --num-rounds 3 --wait-timeout 60 --min-clients 2 --run-id m7_s1_no_timeout

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
python server.py --num-rounds 3 --wait-timeout 15 --min-clients 1 --run-id m7_s2_timeout_drop

python client.py --client-id client-0 --shard-id 0 --num-shards 2 --server-addr 127.0.0.1:50051

python client.py --client-id client-1 --shard-id 1 --num-shards 2 --server-addr 127.0.0.1:50051 --straggler-delay 20
```

Kỳ vọng:
- Client-0 train ~6s + submit ~7s → in window 15s
- Client-1 train ~6s + sleep 20s = ~26s → MISS deadline
- Server: round_timeout @15s → partial_aggregation với client-0 only
- Client-1 sau khi sleep xong submit → server đã sang round 2, reject `stale_round` → **exit 3**
- 3 round với `round_status=partial` server-side, nhưng client-1 chỉ submit được round 1 trước khi exit 3
- Accuracy curve: client-0 IID half data (~98-99%)

**Lưu ý:** Sau round 1 client-1 exit, các round 2-3 server vẫn timeout 15s rồi partial với client-0 → 3 row `partial` đầy đủ.

### 7.4 Scenario F1 — Crash + Reconnect (M7.6, cross-machine)

**Setup:** dài hơi, manual Ctrl+C.

```powershell
# Máy 1: server
python server.py --bind 0.0.0.0:50051 --num-rounds 8 --wait-timeout 30 --min-clients 1 --run-id m7_f1_crash

# Máy 1: client-0
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --server-addr 127.0.0.1:50051

# Máy 2: client-1 (chạy bình thường)
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --server-addr 192.168.2.30:50051
```

**Quy trình manual:**

| Time | Action |
|---|---|
| Round 1-4 | Cả 2 client chạy bình thường — verify `round_status=ok` cho 4 round |
| **Sau round 4 done** | **Ctrl+C client-1 trên Máy 2** (simulate crash) |
| Round 5-7 | Chỉ client-0 submit → server timeout 30s mỗi round → `round_status=partial` (3 round) |
| **Trước round 8** | **Restart client-1 trên Máy 2** với cùng command |
| Round 8 | Cả 2 client submit lại → `round_status=ok` |

Kỳ vọng round_log.csv 8 row:
- Row 1-4: `round_status=ok`, num_clients_received=2
- Row 5-7: `round_status=partial`, num_clients_received=1
- Row 8: `round_status=ok`, num_clients_received=2

Events.csv:
- 4× `round_done advancing_to_round=...` (rounds 1-4)
- 3× `round_timeout` + `partial_aggregation` (rounds 5-7)
- Khi client-1 restart: 1× `client_registered` lần 2 (hoặc đã có từ round 1, không re-log)
- Round 8 normal

**Phân tích cho Exp 4:**
- Accuracy degradation khi 1 client crashed (round 5-7 acc thấp hơn dự kiến nếu 2 client?)
- Recovery time round 8: sau khi client-1 reconnect, accuracy quay lại như trước crash?

## 8. Acceptance criteria

- [ ] M7.1+M7.2 syntax + import OK
- [ ] `--straggler-delay 0` không phá Scenario A (backward compat)
- [ ] `--straggler-delay < 0` → exit code 4 với error message
- [ ] Config snapshot ghi đúng `straggler_delay` value khi user pass CLI
- [ ] **Scenario S1:** 3 round `round_status=ok`, accuracy ~99%, wallclock tăng ~5s/round
- [ ] **Scenario S2:** 3 round server `round_status=partial`; client-1 exit code 3 sau round 1
- [ ] **Scenario F1:** 4 ok + 3 partial + 1 ok (round 1-8), events.csv ghi đủ transitions
- [ ] Cross-machine F1 work: client-1 reconnect được sau Ctrl+C
- [ ] Round wallclock impact của straggler được log rõ trong events.csv `update_received` timing
- [ ] M7 section trong milestone_report.md có data preview cho Exp 3 + Exp 4

## 9. Rủi ro & lưu ý

1. **Backward compat:** `straggler_delay` default 0 → no-op. Tất cả test M3-M6 vẫn pass.

2. **Crash test phụ thuộc thao tác user:** Máy 2 user phải Ctrl+C đúng thời điểm (sau round 4 done, trước round 5 start). Có thể quan sát qua client-1 console — khi nó in `>>> round 5/8 bat dau` thì có thể vẫn ổn để kill (nhưng straggler sẽ miss round 5).

   **Recommendation:** kill sau khi client-1 in `<<< round 4 done` và TRƯỚC khi nó in `>>> round 5/8 bat dau`. Window ~2-3s polling interval.

3. **Reconnect timing:** Restart client-1 phải làm KHI server đang TRAINING round mới (sau round 7 done, trước round 8 timeout). Nếu khởi động chậm, client-1 sẽ join round 9+ hoặc lỡ hoàn toàn.

   **Mitigation:** wait_timeout 30s đủ rộng. Nếu thất bại, retry F1 với num_rounds = 10+ để có thêm cơ hội.

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
