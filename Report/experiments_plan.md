# Phase Experiments + Báo cáo cuối kỳ — Kế hoạch

> Phase cuối cùng. Toàn bộ implementation M1–M7 đã DONE. Phase này = **chạy nốt baseline còn thiếu + analyze + plot + viết báo cáo cuối kỳ** theo cấu trúc 5 vấn đề distributed systems của `ytuong.md` §7.

## 1. Mục tiêu

Sản xuất **4 experiments** + **báo cáo cuối kỳ** phân tích 5 vấn đề distributed systems. Trọng tâm là **hệ phân tán** (communication, sync, straggler, fault tolerance, data heterogeneity), KHÔNG đua accuracy.

## 2. Scope

**IN — làm trong phase này:**
- E0: Chạy lại bộ baseline **đồng bộ 20-round localhost** (Centralized 20 epoch + Fed IID 20 round + Fed Non-IID 20 round) cho accuracy/convergence curves
- E1: Script `analyze.py` đọc `round_log.csv` (xử lý cả 2 schema M4/M6) + tạo 4 plots + in metrics
- E2: Tính communication overhead (§7.1) từ model_size + công thức
- E3: Viết báo cáo cuối kỳ `Report/bao_cao_cuoi_ky.md` theo cấu trúc §7

**OUT — KHÔNG làm:**
- Code change server/client (đã đủ) — trừ `analyze.py` mới
- Thêm cột timing download/train/upload vào round_log (đã chốt: dùng CSV coarse)
- Chạy lại Straggler/Fault (đã có S1/S2/F1 đủ)
- Tự động hoá cross-machine (bán tự động, manual đủ)
- Gradient compression / quantization / weight delta → Future Work (định tính trong báo cáo)

## 3. Decisions đã chốt (user)

| QĐ | Lựa chọn |
|---|---|
| **Baseline Exp 1&2** | Chạy lại đồng bộ **20 round localhost** (Máy 1, server + 2 client cùng máy). KHÔNG cần Máy 2 vì Exp 1&2 chỉ cần accuracy/convergence, network không ảnh hưởng accuracy. |
| **Timing breakdown** | Dùng **CSV sẵn có (coarse)**: `aggregation_time_ms + eval_time_ms + round_wallclock_sec` từ round_log. Phần residual đặt tên **trung tính** (`other_round_time_ms`), KHÔNG khẳng định là "compute+wait". KHÔNG thêm code logging. |

## 4. Hiện trạng data (đã khảo sát)

| Experiment | §7 | Data sẵn có | Cần thêm |
|---|---|---|---|
| **1. Centralized vs Federated** | — | Fed IID `m44_cross` (5r, cross-machine) | ❌ Centralized đầy đủ → **E0** |
| **2. IID vs Non-IID** | §7.5 | Non-IID `m54_cross` curve đẹp (91.6%→98.2%) vs IID (98.4%→99.2%) | Curve dài hơn → **E0** |
| **3. Straggler** | §7.3 | S1 `m74_s1_localhost` (3r ok) + S2 `m75_s2_v3` (3r partial) | ✅ Đủ |
| **4. Fault tolerance** | §7.4 | F1 `m76_f1_v3` (16r, 4-phase crash/recovery) | ✅ Đủ |
| **Comm overhead** | §7.1 | model_size = **1,689,280 bytes (1.611 MiB)** | Tính thuần |
| **Sync model** | §7.2 | M6 timeout/partial + S2 data | ✅ Đủ |

**Hằng số đồng nhất mọi run:** `local_epochs=2, batch_size=32, lr=0.01, seed=42`.

**Schema note:** `round_log.csv` có 2 phiên bản — M4 cũ (không cột `round_status`) vs M6+ (có `round_status` sau `num_clients_received`). `analyze.py` phải detect header. Còn lại các cột giống hệt: `accuracy, test_loss, acc_class_0..9, aggregation_time_ms, eval_time_ms, round_wallclock_sec`.

## 5. E0 — Baseline đồng bộ 20 round (localhost, Máy 1)

Naming: experiment_name riêng cho official runs (tách khỏi `*_smoke`), `--num-rounds 20`.

| Task | Command | run-id / exp_name | Acceptance |
|---|---|---|---|
| **E0.1 Centralized 20 epoch** | `python centralized_train.py --num-rounds 20 --run-id baseline_20ep` | `exp_centralized/baseline_20ep` | round_log 20 epoch, acc ≥ 98%, monotonic-ish tăng |
| **E0.2 Fed IID 20 round** | Server: `python server.py --num-rounds 20 --min-clients 2 --wait-timeout 60 --experiment-name exp_federated_iid --run-id baseline_20r`<br>Client-0: `--client-id client-0 --shard-id 0 --num-shards 2 --server-addr 127.0.0.1:50051`<br>Client-1: `--client-id client-1 --shard-id 1 --num-shards 2 --server-addr 127.0.0.1:50051` | `exp_federated_iid/baseline_20r` | 20 round, mọi round `ok` (received=2), acc ≥ 98% |
| **E0.3 Fed Non-IID 20 round** | Như E0.2 nhưng `--data-split noniid` (server snapshot) + 2 client `--data-split noniid`, `--experiment-name exp_federated_noniid --run-id baseline_20r` | `exp_federated_noniid/baseline_20r` | 20 round `ok`, acc curve hội tụ chậm hơn IID rõ rệt (round 1 ~91%) |

**Min_clients=2 ở E0.2/E0.3:** ép server chờ đủ 2 client mỗi round → mọi round `ok` (clean baseline, không partial). wait_timeout=60 đủ rộng cho localhost cold start.

### Phân vai trò data — accuracy vs timing (quan trọng, tránh kết luận sai)

- **E0 (localhost) CHỈ dùng cho accuracy/convergence** (Exp 1 & 2). 2 client cùng 1 GPU → train tuần tự, tranh GPU → wall-clock KHÔNG phản ánh hệ thật.
- **Timing federated "bình thường"** lấy từ cross-machine **`m44_cross` (Fed IID)** và/hoặc **`m54_cross` (Non-IID)**. KHÔNG trộn `m76_f1_v3` vào biểu đồ timing chung — đó là fault-tolerance scenario, timing bị méo bởi crash/recovery (round timeout ~46s). `m76_f1_v3` timing chỉ dùng trong phần **Experiment 4 / fault tolerance**.
- **KHÔNG** so sánh trực tiếp total wall-clock của Centralized localhost vs Federated localhost như một kết luận performance chính. Exp 1 so accuracy + thảo luận cost định tính; nếu cần số wall-clock federated thì trích từ cross-machine run + note.

### Vận hành E0 (3 lưu ý thủ tục)

1. **Dừng server giữa các run:** server dùng `server.wait_for_termination()` (server.py:532) — **KHÔNG tự thoát sau DONE**. Sau khi đủ 20 round và 2 client exit, **Ctrl+C server** trước khi chạy E0 tiếp theo, nếu không sẽ đụng port `50051`.
2. **Tránh overwrite run dir:** run chính thức dùng `run-id baseline_20r` (giữ duy nhất). Nếu rerun để debug → dùng `baseline_20r_debugN` (N=1,2,...). Chỉ giữ `baseline_20r` cho kết quả cuối đưa vào báo cáo.
3. **Thứ tự an toàn:** chạy E0.1 (centralized, không cần server) → E0.2 (start server IID, 2 client, Ctrl+C server) → E0.3 (start server Non-IID, 2 client, Ctrl+C server).

## 6. E1 — Analysis script `analyze.py`

Một script đọc các run, tạo plots vào `Report/figures/`, in bảng metrics.

**Input:** đường dẫn các run_dir (hardcode map hoặc CLI). **Output:** 4 PNG + stdout metrics table.

**Hàm cốt lõi:**
- `load_round_log(path)` → pandas DataFrame, detect schema (có/không `round_status`), chuẩn hoá cột
- `plot_accuracy_per_round(...)` → `accuracy_per_round.png`: 3 đường (Fed IID, Fed Non-IID, Centralized baseline). Trục x = round/epoch; chú thích Centralized là baseline gom data (không tách IID/Non-IID)
- `plot_round_time_breakdown(...)` → `round_time_breakdown.png`: stacked bar coarse = `aggregation_time_ms + eval_time_ms + other_round_time_ms`, với `other_round_time_ms = round_wallclock_sec×1000 − agg − eval`. **Tên trung tính `other_round_time_ms`** (gồm client train + download/upload + polling + timeout wait — KHÔNG khẳng định thuần compute/wait). Dùng cross-machine run **`m44_cross`/`m54_cross`** cho realistic. **Biểu đồ này chỉ mô tả _normal federated timing_; fault-timeout (round ~46s) được phân tích riêng trong Experiment 4, KHÔNG dùng `m76_f1_v3` ở đây.**
- `plot_communication_overhead(...)` → `communication_overhead.png`: **MiB** cumulative = `round × model_size_bytes × 2 × num_clients / 1024²`
- `plot_per_class_iid_vs_noniid(...)` → `per_class_accuracy_iid_vs_noniid.png`: grouped bar `acc_class_0..9` ở **round cuối** cho IID vs Non-IID — minh chứng mạnh cho §7.5 (Non-IID lệch per-class rõ hơn final acc tổng)
- `print_metrics_table(...)` → bảng mỗi setup: `final_acc`, `avg_acc_first_5_rounds` (phân biệt tốc độ hội tụ sớm IID vs Non-IID), `rounds_to_98%` (thay `rounds_to_95%` — MNIST vượt 95% quá sớm, không phân biệt được), `avg round_wallclock`, `total comm MiB`

**Acceptance E1:** 4 PNG sinh ra không lỗi; số liệu spot-check khớp round_log thủ công 1-2 giá trị; `avg_acc_first_5_rounds` của Non-IID thấp hơn IID rõ rệt.

## 7. E2 — Communication overhead (§7.1)

Tính thuần, không cần run mới. **Dùng MiB nhất quán** (`1,689,280 / 1024² = 1.611 MiB`, không phải MB decimal):
```
model_size = 1,689,280 bytes = 1.611 MiB
comm/round = 1.611 × 2 (down+up) × 2 client = 6.44 MiB
20 rounds  = 128.9 MiB
```
- Phân tích: gRPC/protobuf binary vs HTTP+JSON (JSON base64 ~+33% overhead + text parsing) — **định tính** theo spec, không benchmark.
- Future Work: weight delta / top-k sparsification / int8 quantization (giảm ~4×) — chỉ thảo luận.

## 8. Mapping §7 (5 vấn đề) → data nguồn cho báo cáo

| § | Vấn đề | Experiment / data | Điểm phân tích chính |
|---|---|---|---|
| 7.1 | Communication Overhead | E2 tính toán + model_size | MiB/round, scaling theo #client, gRPC vs JSON |
| 7.2 | Synchronization Model | M6 + S2 (`m75_s2_v3`) | bounded-sync, timeout=drop straggler, tradeoff acc vs round time |
| 7.3 | Straggler | Exp 3: S1 (`m74_s1_localhost`) vs S2 (`m75_s2_v3`) | S1 ok nhưng `round_wallclock +5s`; S2 timeout → drop, partial. So sánh latency vs accuracy |
| 7.4 | Fault Tolerance | Exp 4: F1 (`m76_f1_v3`) | 4-phase: healthy→degraded(crash)→recovery; events.csv gap round 7→12; acc không degrade |
| 7.5 | Data Heterogeneity | Exp 2: E0.2 IID vs E0.3 Non-IID + `per_class_accuracy_iid_vs_noniid.png` | Non-IID hội tụ chậm (`avg_acc_first_5_rounds` thấp hơn) + lệch per-class rõ ở round cuối; gap thu hẹp theo round |

## 9. E3 — Báo cáo cuối kỳ `Report/bao_cao_cuoi_ky.md`

Cấu trúc:
1. **Tổng quan hệ thống** — kiến trúc 2-node, gRPC 3 RPC, state machine, FedAvg (tóm tắt, trỏ `milestone_report.md` cho chi tiết)
2. **Thiết lập thí nghiệm** — hardware, hyperparams đồng nhất, cách chạy
3. **Experiment 1** — Centralized vs Federated (accuracy/convergence + cost định tính; wall-clock chỉ tham khảo từ cross-machine run, không phải kết luận performance chính)
4. **Experiment 2** — IID vs Non-IID (accuracy curve + per-class) → §7.5
5. **Experiment 3** — Straggler S1/S2 → §7.3
6. **Experiment 4** — Fault tolerance F1 → §7.4
7. **Phân tích 5 vấn đề distributed systems** (§7.1–7.5) — phần trọng tâm
8. **Future Work** — compression, async FL, secure aggregation, scale >2 client
9. **Kết luận**

Nhúng **4 plots** từ `Report/figures/` (accuracy curve, time breakdown, comm overhead, per-class IID vs Non-IID). Tiếng Việt, có thể sinh kèm bản tổng kết.

## 10. Thứ tự thực hiện + ước tính

| Bước | Nội dung | Owner | Thời lượng |
|---|---|---|---|
| E0.1 | Centralized 20 epoch | Máy 1 | 5 phút |
| E0.2 | Fed IID 20 round localhost | Máy 1 | 8 phút |
| E0.3 | Fed Non-IID 20 round localhost | Máy 1 | 8 phút |
| E1 | `analyze.py` + 4 plots + metrics table | Máy 1 | 45 phút |
| E2 | Comm overhead (tính + ghi) | Máy 1 | 10 phút |
| E3 | Báo cáo cuối kỳ | Máy 1 | 60–90 phút |
| **Tổng** | | | **~2.5 giờ** |

Toàn bộ phase **chạy mới trên Máy 1**; không cần chạy thêm Máy 2. Các phân tích timing dùng **cross-machine runs đã thu sẵn** (`m44_cross`, `m54_cross`, `m76_f1_v3` cho fault).

## 11. Acceptance criteria (toàn phase)

- [ ] E0: 3 run baseline 20-round/epoch sinh đủ `round_log.csv`, hyperparams khớp (`local_epochs=2, batch=32, lr=0.01, seed=42`)
- [ ] Fed Non-IID convergence chậm hơn IID rõ rệt: `avg_acc_first_5_rounds` thấp hơn + per-class lệch hơn (minh chứng §7.5)
- [ ] `analyze.py` sinh **4 PNG** không lỗi, số liệu spot-check khớp CSV
- [ ] Comm overhead tính đúng theo **MiB** (6.44 MiB/round, 2 client)
- [ ] Báo cáo cuối kỳ đủ 5 phần §7 + nhúng **4 plots** + Future Work
- [ ] Workflow git: feature branch (vd `feature/experiments`) → PR → dev

## 12. Git workflow

- Branch `feature/experiments` từ `dev` latest
- Commit tách: E0 runs (results gitignored — chỉ commit nếu cần), `analyze.py`, `figures/`, báo cáo
- PR review trước khi merge dev; sau đó dev → main đồng bộ
