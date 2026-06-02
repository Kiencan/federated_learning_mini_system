# Báo cáo tổng kết — Federated Learning Mini System

> Tài liệu này tổng kết toàn bộ những gì đã hoàn thành từ M1 đến M6 (~6/7 milestones, cộng phase Experiments + báo cáo cuối kỳ còn lại).
>
> Cập nhật: 2026-05-27 sau khi merge M6 vào `dev`.

## Mục lục

1. [Tóm tắt điều hành](#1-tóm-tắt-điều-hành)
2. [Mục tiêu & phạm vi dự án](#2-mục-tiêu--phạm-vi-dự-án)
3. [Hệ thống đã triển khai](#3-hệ-thống-đã-triển-khai)
4. [Tiến độ milestones](#4-tiến-độ-milestones)
5. [Kết quả thực nghiệm tổng hợp](#5-kết-quả-thực-nghiệm-tổng-hợp)
6. [5 vấn đề distributed systems — đã giải quyết những gì](#6-5-vấn-đề-distributed-systems--đã-giải-quyết-những-gì)
7. [Workflow & collaboration stats](#7-workflow--collaboration-stats)
8. [Còn lại để làm](#8-còn-lại-để-làm)
9. [Reference — tài liệu chi tiết](#9-reference--tài-liệu-chi-tiết)

---

## 1. Tóm tắt điều hành

Dự án triển khai thành công một hệ thống Federated Learning hai node với giao tiếp gRPC trên MNIST + CNN nhỏ. **Đã hoàn thành 6/7 milestones** thiết kế trong [plan.md](../plan.md), với toàn bộ infrastructure phục vụ 4 experiments của báo cáo cuối kỳ.

**Kết quả nổi bật:**

- **Centralized baseline (M1):** 98.94% accuracy sau 2 epoch MNIST trên RTX 2000 Ada.
- **Federated IID 5 round (M4):** **99.27% localhost / 99.24% cross-machine** — gần ngang centralized, chứng minh FedAvg hiệu quả với 2 client IID.
- **Federated Non-IID pathological 5 round (M5):** **98.13% localhost / 98.21% cross-machine** — vẫn hội tụ tốt; phát hiện **finding chính cho Exp 2**: round 1 class 5 chỉ 51.2% (vs IID 98.4%), thể hiện rõ "client drift" → recover sau 5 round.
- **Fault tolerance (M6):** server không stuck khi 1 client crash/chậm; verified 4 path types (ok / partial / skipped) trên cả localhost lẫn cross-machine. Server refactor từ sync aggregation (trong RPC handler) sang background thread với 3-phase lock design.

**Còn lại:**
- M7 (straggler simulation + crash/reconnect experiments) — scope hẹp nhất (~1.5h)
- Phase Experiments (4 experiments theo plan.md §6, dùng infrastructure M1-M7)
- Báo cáo cuối kỳ với phân tích 5 vấn đề distributed systems

**Phương pháp triển khai:** Plan-first, milestone-incremental, code review qua PR + Pull Request, 2 dev cộng tác (Máy 1 + Máy 2), workflow chuẩn gitflow.

---

## 2. Mục tiêu & phạm vi dự án

### 2.1 Bài toán

| Thành phần | Lựa chọn |
|---|---|
| Dataset | MNIST (10 lớp chữ số 0-9, 60k train + 10k test) |
| Model | CNN nhỏ (2 conv 32+64 filters, 2 FC 128+10, dropout 0.25) — ~1.65 MB state_dict |
| Số client | 2 (thật, chạy trên 2 máy vật lý riêng) |
| Algorithm | FedAvg weighted by num_samples |
| Communication | gRPC + Protocol Buffers, port 50051 LAN |
| Sync model | Bounded synchronous với WAIT_TIMEOUT (M6) |

### 2.2 Hardware

| | Máy 1 | Máy 2 |
|---|---|---|
| GPU | NVIDIA RTX 2000 Ada Generation | NVIDIA RTX 2000 Ada Generation |
| CUDA | 12.1 | 12.6 |
| Vai trò | Server (CPU eval) + Client 0 (GPU) | Client 1 (GPU) |
| LAN IP | 192.168.2.30 | (động) |
| OS | Windows 11 | Windows 11 |

### 2.3 Phạm vi distributed systems (§7 ytuong.md)

Báo cáo cuối kỳ sẽ phân tích 5 vấn đề:

1. **Communication overhead** — đo bytes truyền/round, so sánh gRPC vs HTTP
2. **Synchronization model** — bounded sync với timeout (M6)
3. **Straggler problem** — sẽ test ở M7 + Exp 3
4. **Fault tolerance** — M6 thực hiện, M7 + Exp 4 sẽ test stress
5. **Data heterogeneity** — IID vs Non-IID (M5 đã có data + finding)

---

## 3. Hệ thống đã triển khai

### 3.1 Kiến trúc

```text
              ┌────────────── Máy 1 (192.168.2.30) ──────────────┐
              │                                                  │
              │  ┌──────────────────┐    ┌──────────────────┐  │
              │  │  Server          │    │  Client 0 (GPU)  │  │
              │  │  (CPU eval)      │←───┤                  │  │
              │  │  Port 0.0.0.0:   │    │  Shard 0         │  │
              │  │  50051           │    │  (IID half       │  │
              │  │                  │    │   hoặc 0-4 NonIID)  │
              │  │  - Background    │    └──────────────────┘  │
              │  │    aggregation   │                            │
              │  │    thread (M6)   │                            │
              │  └────────┬─────────┘                            │
              │           │                                      │
              └───────────┼──────────────────────────────────────┘
                          │ gRPC LAN
              ┌───────────┼──────────────────────────────────────┐
              │           ▼                                      │
              │  ┌──────────────────┐                            │
              │  │  Client 1 (GPU)  │                            │
              │  │  Shard 1         │                            │
              │  │  (IID half       │                            │
              │  │   hoặc 5-9 NonIID)                            │
              │  └──────────────────┘                            │
              │             Máy 2                                │
              └──────────────────────────────────────────────────┘

Per-round flow (M6):
   client poll status → pull global model → train local
   → submit update → server background thread aggregate → advance round
```

### 3.2 Tech stack

| Layer | Tool/Library |
|---|---|
| ML framework | PyTorch 2.5.1+cu121 (Máy 1) / 2.12.0+cu126 (Máy 2), torchvision 0.20.1 |
| Communication | grpcio 1.80.0, grpcio-tools 1.80.0, protobuf 6.33.6 |
| Data + viz | numpy 2.4.4, pandas 3.0.3, matplotlib 3.10.9, pyyaml 6.0.3 |
| Env | conda env `fedml`, Python 3.11.15 |
| OS | Windows 11 |

### 3.3 Cấu trúc dự án

```text
.
├── proto/
│   ├── federated.proto              # gRPC service definition (locked từ M2)
│   ├── federated_pb2.py             # generated bindings (committed)
│   └── federated_pb2_grpc.py
├── server.py                        # FL server (M2 → M6 refactor lớn)
├── client.py                        # FL client (M2 → M5 with --data-split)
├── aggregation.py                   # FedAvg + evaluate (M3, shared)
├── model.py                         # MnistCNN + serialize/deserialize state_dict
├── data_partition.py                # IID / Non-IID pathological split
├── centralized_train.py             # M1 baseline
├── run_context.py                   # CLI parser, config snapshot, run_meta (M5 fix)
├── gen_proto.py                     # Regenerate pb2 từ .proto
├── config.yaml                      # Config tập trung
├── requirements.txt / .lock         # Pip deps
├── environment.yml                  # Conda env
├── tests/
│   ├── _smoke_server.py             # 9-case smoke test M3 + M6
│   ├── test_stale_update.py         # 4-case stale validation (M3.8)
│   └── __init__.py
├── results/                         # Per-run output (gitignored, except .gitkeep)
│   ├── exp_centralized/<run_id>/    # M1
│   ├── exp_federated_iid_smoke/     # M3-M4
│   └── exp_federated_noniid_smoke/  # M5
├── Report/
│   ├── milestone_report.md          # Per-milestone báo cáo chi tiết
│   ├── m3_plan.md, m4_plan.md, ...  # Per-milestone plans
│   └── bao_cao_tong_ket.md          # ← TÀI LIỆU NÀY
├── ytuong.md                        # Spec gốc
├── plan.md                          # Kế hoạch tổng
└── README.md                        # Setup + run instructions
```

### 3.4 Protocol Buffers schema (proto/federated.proto)

Locked từ M2, không churn qua M3-M6:

```protobuf
service FederatedLearning {
  rpc GetGlobalModel (RoundRequest) returns (ModelWeights);
  rpc SubmitUpdate   (ClientUpdate) returns (AckResponse);
  rpc GetRoundStatus (Empty)        returns (RoundStatus);
}

message ClientUpdate {
  string client_id = 1;
  int32  round_id = 2;
  bytes  serialized_state_dict = 3;     // torch.save(state_dict)
  int32  num_samples = 4;
  double train_loss = 5;
  TimingInfo timing = 6;                // download/train/upload ms
  // Metadata gửi 1 lần (round đầu) cho run_meta.json:
  string hostname = 7;
  string gpu_name = 8;
  string torch_version = 9;
  string cuda_version = 10;
}

message RoundStatus {
  enum State { UNKNOWN, WAITING, TRAINING, AGGREGATING, EVALUATING, DONE }
  int32 current_round = 1;
  State state = 2;
  int32 num_rounds_total = 3;
}
```

### 3.5 Logging structured (per run_id)

Mỗi run output 4 file vào `results/{experiment_name}/{run_id}/`:

- **`config.yaml`** — snapshot resolved config (sau CLI overrides, M5 fix)
- **`run_meta.json`** — server + per-client metadata (hostname, GPU, torch/CUDA version, git commit)
- **`round_log.csv`** — per-round metrics: accuracy, test_loss, per-class accuracy, agg_ms, eval_ms, round_wallclock_sec, per-client train_loss + num_samples, **round_status (M6)**
- **`events.csv`** — timestamped events: client_registered, model_pulled (kèm state name từ M6), update_received, update_rejected (kèm reason), aggregation_start/done, evaluation_done, round_done, **round_timeout / partial_aggregation / round_skipped / commit_aborted (M6)**

---

## 4. Tiến độ milestones

### 4.1 Bảng tổng quan

| # | Milestone | Owner chính | Trạng thái | Merge commit |
|---|---|---|---|---|
| **M1** | Centralized baseline (1 máy, không gRPC) | Máy 1 | ✅ Done | `49734cb` |
| **M2** | gRPC hello world qua 2 máy | Máy 1 | ✅ Done | `ada1e41` → `b2bd2fe` |
| **M3** | Server/client chạy 1 round IID end-to-end | Máy 1 + Máy 2 | ✅ Done | `a99cab0` → `c05a049` → `3eef9ec` |
| **M4** | Multi-round IID (5 round) | Máy 2 (client) + Máy 1 | ✅ Done | `38c66fe` |
| **M5** | Non-IID pathological split | Máy 1 + Máy 2 | ✅ Done | `5857aa9` → `c0dd3a9` |
| **M6** | WAIT_TIMEOUT + dynamic min_clients (fault tolerance) | Máy 1 | ✅ Done | `370b4af` |
| **M7** | Straggler + crash/reconnect scenarios | — | ⏳ Pending | — |

### 4.2 Tóm tắt từng milestone

#### M1 — Centralized Baseline (1 buổi)

Train CNN trên toàn bộ MNIST trên 1 máy, không gRPC. Mục tiêu: verify environment + baseline accuracy + dựng shared code cho M3+.

**Kết quả:** 98.94% accuracy sau 2 epoch (smoke). Per-class ≥ 95%.

**File mới:** `model.py`, `data_partition.py`, `run_context.py`, `centralized_train.py`, `config.yaml`, `requirements.{txt,lock}`, `environment.yml`.

#### M2 — gRPC Hello World (1 buổi)

Verify network boundary thật giữa 2 máy. Schema proto đầy đủ ngay từ đầu (3 RPC + 6 messages) để M3+ không cần churn.

**Kết quả:** Cross-machine LAN RTT trung bình **4.9 ms** (vs localhost 1.5 ms). Network boundary thực sự tồn tại.

**File mới:** `proto/federated.proto`, `proto/federated_pb2*.py`, `server.py` (M2 hello), `client.py` (M2 hello), `gen_proto.py`.

#### M3 — 1 Round Federated IID End-to-End (3 PR)

Milestone lớn nhất về scope. Workflow lần đầu với 2 dev: 3 feature branch song song.

**Phân chia:**

| Branch | Owner | Subtasks |
|---|---|---|
| `feature/m3-server` | Máy 1 | M3.1 ServerState, M3.2 GetGlobalModel, M3.3 SubmitUpdate 4-layer validation, M3.4 _aggregate_and_evaluate |
| `feature/m3-client-loop` | Máy 2 | M3.5 client training loop, M3.6 shard pick + metadata + B1 Windows UTF-8 fix |
| `feature/m3-stale-test` | Máy 2 | M3.8 4-case stale validation test |

**Issues caught via review:** R1 (events.csv write race → fixed với `_log_lock`), R5 (refactor comment), B1 (Windows cp1252 encoding crash → fixed với `sys.stdout.reconfigure`).

**Kết quả:**
- M3.7 localhost smoke: **98.52% accuracy** sau 1 round
- M3.8 stale test: 4/4 case pass (stale_round / unknown_client / valid / duplicate)
- M3.9 cross-machine: **98.45%** v2 (sau khi fix Máy 2 PyTorch CPU → CUDA)

**Phát hiện:** Máy 2 PyTorch ban đầu là build `+cpu` only (qua `run_meta.json`) → train chậm 7x. Sau reinstall `+cu126` train được như Máy 1.

#### M4 — Multi-round IID (1 PR)

Scope hẹp hơn nhiều so với M3. Server không cần code change (nhánh advance round đã có trong M3 code). Máy 2 chỉ cần refactor client.py thành outer loop.

**Phân chia:**

| Branch | Owner | Subtasks |
|---|---|---|
| `feature/m4-client-multiround` | Máy 2 | M4.2 outer round loop với last_completed_round tracker + 3 helpers (train_local, wait_for_new_round_or_done, do_one_round) |

**Bonus của Máy 2:** Self-detected missing `grpc.RpcError` handling → fix trong commit thứ 2.

**Kết quả 5 round IID:**

| | M4.3 Localhost | M4.4 Cross-machine |
|---|---|---|
| Accuracy curve | 98.52 → 99.02 → 99.17 → 99.33 → **99.27%** | 98.44 → 99.14 → 99.13 → 99.29 → **99.24%** |
| Round wallclock steady-state | 8-9 s | 12.6-12.8 s |
| Train loss client-0 cuối | 0.018 | 0.019 |

#### M5 — Non-IID Pathological Split (2 PR sequential)

Workflow phức tạp vì cả 2 PR đều sửa `run_context.py`. Phải merge M5.0 trước M5.2.

**Phân chia:**

| Branch | Owner | Subtasks |
|---|---|---|
| `feature/m5-resolved-config-snapshot` | Máy 1 | M5.0 fix tech debt: snapshot resolved config thay vì copy file gốc |
| `feature/m5-client-noniid` | Máy 2 | M5.2 --data-split flag vào parser chung + client dispatch 3-step + class_distribution print |

**M5.0 phát hiện trong review M5.2:** `create_run_dir` dùng `shutil.copyfile(config_path, snapshot)` → snapshot mất CLI overrides → `data_split: noniid` không xuất hiện trong snapshot. Fix bằng `yaml.safe_dump(config, ...)`.

**Bonus của Máy 2:** Setup data + validate moved TRƯỚC `grpc.insecure_channel()` (fail-fast pattern). Class distribution print dùng `Counter` thực tế thay vì hardcoded label.

**Kết quả 5 round Non-IID cross-machine:**

| Round | Accuracy | Test loss | (so IID M4.4) |
|---|---|---|---|
| 1 | 0.9160 | 0.549 | -6.84 pp |
| 2 | 0.9471 | 0.167 | -4.43 pp |
| 3 | 0.9740 | 0.092 | -1.73 pp |
| 4 | 0.9767 | 0.070 | -1.62 pp |
| 5 | **0.9821** | 0.054 | **-1.03 pp** |

**Finding lớn nhất cho Exp 2 — per-class accuracy round 1:**

| Class | IID | Non-IID | Gap |
|---|---|---|---|
| 5 | 0.984 | **0.512** | **-0.472** ← anomaly |
| 9 | 0.970 | 0.874 | -0.096 |

Class 5 (lớp đầu tiên của client-1) chỉ 51.2% round 1 vs IID 98.4% — thể hiện rõ "client drift" early-round penalty. Recover về ≥96.8% sau 5 round.

#### M6 — WAIT_TIMEOUT + Fault Tolerance (1 PR lớn nhất)

Milestone phức tạp nhất về threading. Server refactor từ sync aggregation (trong RPC handler) → background thread với 3-phase lock design.

**Phân chia:**

| Branch | Owner | Subtasks |
|---|---|---|
| `feature/m6-server-async-agg` | Máy 1 | M6.1 CLI flags + M6.2 server refactor + M6.3 docstring smoke test |

**Refactor chính:**

- **3-phase design tránh giữ lock suốt eval (~1s):**
  - Phase 1 (hold lock): wait condition (threshold OR timeout), snapshot
  - Phase 2 (**NO lock**): FedAvg + evaluate + CSV write
  - Phase 3 (hold lock <10ms): guarded commit + advance round
- **3 paths** qua condition.wait:
  - **A "ok"** = received >= expected_count (early)
  - **B "partial"** = timeout + received >= min_clients (drop slow)
  - **C "skipped"** = timeout + received < min_clients (skip round)
- **Pure functions:** `_do_fedavg`, `_do_evaluate`, `_write_round_log_row`, `_write_skipped_round_row`
- **4 events mới:** `round_timeout`, `partial_aggregation`, `round_skipped`, `commit_aborted`
- **round_log.csv schema:** thêm cột `round_status` (ok/partial/skipped)
- **Config validation fail-fast:** `1 <= min_clients <= expected_count`, `wait_timeout > 0`
- **Observability:** `model_pulled` event kèm `state=<NAME>` cho post-mortem race analysis

**Bug timing phát hiện trong test:** `round_start_time` set trong `ServerState.__init__` (trước `server.start()` + Python client startup ~10s) → round 1 timeout trước khi client kịp submit. Fix: refresh `round_start_time = time.time()` sau `server.start()`. Cũng đẩy default `wait_timeout` 15→30s.

**Verification — 4 path types × 2 setups:**

| Path | Localhost | Cross-machine |
|---|---|---|
| A "ok" | ✅ M6 early-test (acc 99.17%) | ✅ m65_debug round 3 (acc 98.59%) |
| B "partial" | ✅ M6.4 round 3 (acc 98.31%) | ✅ run 1 m65_scenario_a |
| C "skipped" (received=0) | ✅ M6.4 Scenario C | — |
| C "skipped" (received<min) | — | ✅ m65_debug + v4 |

**Shutdown timing đo bằng Stop-Process:** 1.03s ✓

---

## 5. Kết quả thực nghiệm tổng hợp

### 5.1 Accuracy comparison (cross-machine 5 round)

| Run | Setup | Round 1 | Round 5 | Notes |
|---|---|---|---|---|
| M1 centralized | 1 máy, full MNIST | — | 98.94% (2 epoch) | Baseline cho Exp 1 |
| M4.4 IID | 2 clients × half data | 0.9844 | **0.9924** | Federated near-centralized |
| M5.4 Non-IID | Client-0: digits 0-4, Client-1: 5-9 | 0.9160 | **0.9821** | -1pp vs IID round 5; class 5 round 1 only 51.2% |

### 5.2 Timing breakdown (steady state, GPU)

| Phase | M4.4 IID | M5.4 NonIID | Note |
|---|---|---|---|
| Server FedAvg | ~2-4 ms | ~1-3 ms | Data-agnostic |
| Server eval (CPU) | ~970-990 ms | ~970-1180 ms | 10000 test samples |
| Client download | 7-10 ms | 7-10 ms | 1.65 MB LAN |
| Client train (2 epochs × ~30k samples) | ~6-7 s | ~6-7 s | RTX 2000 Ada GPU |
| Client upload | 10-1000 ms | 10-1000 ms | Cao nếu là client cuối (chờ server agg+eval) |
| **Round wallclock** | **12-13 s** | **11-12 s** | Cross-machine, steady state |

### 5.3 Communication overhead

| Metric | Value |
|---|---|
| Model state_dict (PyTorch save bytes) | **1.65 MB** |
| Per-round bytes transfer (mỗi client) | ~3.3 MB (1 download + 1 upload) |
| gRPC default MAX_MESSAGE_LENGTH | 4 MB (within limit, không tweak) |
| Server max_message_length cấu hình | 16 MB (dự phòng) |
| Cross-machine RTT trung bình (GetRoundStatus) | 4.9 ms |
| Cross-machine RTT localhost loopback | 1.5 ms |
| LAN overhead per RPC | ~3-4 ms |

### 5.4 M6 fault tolerance verified scenarios

| Scenario | wait_timeout | min_clients | Result |
|---|---|---|---|
| A "ok" all clients submit fast | 30s | 1 | Early aggregation, no timeout event |
| B "partial" 1 client only | 10s | 1 | timeout + partial_aggregation, acc 98.31% với 1 client IID half data |
| C "skipped" 0 clients | 5s | 1 | 3 round skip, state→DONE, metrics empty |
| C "skipped" received<min | 60s | 2 | Skip với received=1<min=2 |

---

## 6. 5 vấn đề distributed systems — đã giải quyết những gì

### 6.1 Communication Overhead (§7.1 ytuong.md)

**Đã có:**
- Đo được bytes transfer per round (3.3 MB × 5 round = ~16.5 MB total)
- So sánh localhost (~1.5 ms RTT) vs LAN (~4.9 ms RTT)
- Serialize state_dict bằng torch.save (KHÔNG serialize nguyên `nn.Module`) để cross-platform

**Còn lại:**
- Exp 1 sẽ tổng hợp full communication cost vs centralized
- Phân tích serialization time riêng (hiện chưa đo tách bạch)

### 6.2 Synchronization Model (§7.2)

**Đã có:**
- Bounded synchronous demonstrated từ M3 (sync aggregation in handler)
- M6 chuyển sang background thread + WAIT_TIMEOUT (15-30s default)
- 3 paths rõ ràng: early (all done) vs partial (timeout + ≥min) vs skip (timeout + <min)
- Validate config fail-fast (`1 <= min_clients <= expected_count`)

**Còn lại:** chỉ phân tích trong báo cáo cuối kỳ.

### 6.3 Straggler Problem (§7.3)

**Đã có:**
- M6 background thread + WAIT_TIMEOUT infrastructure
- Path B "partial" demonstrated cả localhost lẫn cross-machine

**Còn lại (M7):**
- Thêm flag `--straggler-delay N` cho client để simulate slow client cố ý
- Exp 3 với 2 cases: timeout=15s + delay=5s (all good) vs timeout=15s + delay=20s (drop straggler)
- Đo round completion time, final accuracy, throughput

### 6.4 Fault Tolerance (§7.4)

**Đã có:**
- M6 path B (partial) và path C (skip) verified
- Client `sys.exit(3)` nếu gặp reject → exit clean
- Server không stuck khi 1 client miss timeout

**Còn lại (M7):**
- Test scenario kill client-2 mid-round → server tiếp tục
- Test client-2 reconnect → tham gia round mới
- Log events đầy đủ cho Exp 4 analysis

### 6.5 Data Heterogeneity (§7.5)

**Đã giải quyết HOÀN TOÀN (M5):**
- IID partition + Non-IID pathological (Client-0: 0-4, Client-1: 5-9)
- 5 finding cho báo cáo Exp 2:

| # | Finding | Bằng chứng |
|---|---|---|
| 1 | Non-IID hội tụ chậm hơn ~1 round, vẫn đạt > 98% sau 5 round | Gap 6.84pp round 1 → 1.03pp round 5 |
| 2 | Round 1 class 5: client drift early penalty cực rõ | 51.2% Non-IID vs 98.4% IID (-47pp) |
| 3 | Test loss higher (less confident) dù acc ngang | 2.6x round 5 (0.054 vs 0.021) |
| 4 | Train_loss client-side Non-IID thấp giả tạo do overfit local | client-0: 0.006 NonIID vs 0.019 IID |
| 5 | Compute time không khác biệt giữa IID/Non-IID | Steady state ~11-12s/round cả hai |

---

## 7. Workflow & collaboration stats

### 7.1 Git workflow

- **Mô hình:** main / dev / feature/* — Pull Request review trước khi merge dev
- **Quy ước branch:** `feature/<milestone>-<scope>` (vd `feature/m3-server`)
- **PR review:** code review qua diff GitHub + integration test local trước khi approve
- **Branch cleanup:** xóa cả remote + local sau merge (giữ git log gọn)

### 7.2 Số liệu commit / branch (đến 2026-05-27)

| Metric | Value |
|---|---|
| Total commits trên dev | ~80+ (bao gồm docs + merges) |
| Feature branches merged | 6 (M3 × 3 + M4 × 1 + M5 × 2 + M6 × 1) |
| Sub-feature branches deleted | 6 (tất cả đã clean) |
| Báo cáo plans + reports | 7 markdown (5 plans + milestone_report + this) |
| Total Python files | 9 (server, client, aggregation, model, data_partition, run_context, centralized_train, gen_proto, smoke tests) |
| Total lines of Python (excluding tests) | ~1800 |

### 7.3 Collaboration với Máy 2 (cộng tác viên)

Máy 2 đã participate trong:
- **M3.5+M3.6** (client training loop + shard pick): branch `feature/m3-client-loop`
- **M3.8** (stale update test): branch `feature/m3-stale-test`
- **M4.2** (client multi-round refactor): branch `feature/m4-client-multiround`
- **M5.2** (--data-split flag + client dispatch): branch `feature/m5-client-noniid`
- Cross-machine testing cho M3.9, M4.4, M5.4, M6.5

**Issues caught qua code review:**
- B1: Windows cp1252 encoding crash → Máy 2 self-fix với `sys.stdout.reconfigure`
- Self-detected `grpc.RpcError` missing handlers (M4.2) → Máy 2 fix luôn trong commit thứ 2
- 4 minor issues N1-N6 trong M4.2 review → defer cho M5+, không block

### 7.4 Code review issues defer

Tổng các minor issues phát hiện trong reviews nhưng defer cho milestone sau:

| Issue | Phát hiện ở | Defer |
|---|---|---|
| `gpu_name` populate khi device fallback CPU | M4 | M7 |
| `rounds_done` count với mid-experiment join | M4 | M7 |
| Print prefix `[client]` vs `[client {id}]` không nhất quán | M4 | Cosmetic |
| Path C ghi CSV inside lock | M6 | Acceptable scope hẹp |
| `GetRoundStatus` compound read without lock | M3+ | Tolerated (per-thread atomic) |
| `notify_all()` Phase 3 có thể redundant | M6 | Belt-and-suspenders |
| `round_timeout` event không log duration | M6 | Minor |
| GetGlobalModel state validation | M6 | Giữ scope hẹp, safe-by-chain |

---

## 8. Còn lại để làm

### 8.1 M7 — Straggler + Crash/Reconnect (~1.5h, scope hẹp nhất)

**Code changes:**
- Client thêm CLI `--straggler-delay N` (sleep N giây trước SubmitUpdate)
- Không cần server changes (infrastructure M6 đã đủ)

**Test scenarios:**
1. Straggler fast: `--wait-timeout 15 --straggler-delay 5` → server vẫn early aggregate Path A
2. Straggler slow: `--wait-timeout 15 --straggler-delay 20` → server timeout + partial aggregate, drop straggler
3. Kill client-2 round 3 → server Path B (partial), tiếp tục
4. Restart client-2 round 5 → tham gia round mới

### 8.2 Phase Experiments (4 experiments theo plan.md §6)

Sau M7, chạy 4 experiments với dataset đã có:

| Exp | Setup | Data đã có | Cần thêm |
|---|---|---|---|
| **1. Centralized vs Federated** | Centralized 30 epoch vs Federated IID 30 round | M1 smoke (2 epoch) + M4.4 (5 round) | Chạy thêm centralized 30 epoch + federated IID 30 round |
| **2. IID vs Non-IID** | 5+ round mỗi setup | M4.4 (IID 5 round) + M5.4 (NonIID 5 round) | ✓ Đủ data |
| **3. Straggler** | timeout=15s × delay=5s vs delay=20s | — | Cần M7 |
| **4. Fault tolerance** | Kill round 3, restart round 5 | — | Cần M7 |

### 8.3 Báo cáo cuối kỳ

**Cấu trúc kỳ vọng:**
1. Giới thiệu + ý tưởng (từ ytuong.md)
2. Kiến trúc hệ thống (từ tài liệu này §3)
3. Thuật toán FedAvg + cài đặt
4. 4 Experiments + phân tích (Exp 1-4)
5. 5 vấn đề distributed systems (§7 ytuong.md, từ tài liệu này §6)
6. Limitations + Future Work
7. Kết luận

**Visualization cần làm:**
- Accuracy curve per round (IID + Non-IID + Centralized) — Exp 1, 2
- Per-class accuracy bar chart (IID vs Non-IID round 5) — Exp 2 finding chính
- Round wallclock breakdown stacked bar (download/train/upload/eval) — Exp 3
- Throughput (rounds/minute) so sánh các setups — Exp 3, 4

---

## 9. Reference — tài liệu chi tiết

| Tài liệu | Nội dung |
|---|---|
| [ytuong.md](../ytuong.md) | Spec gốc dự án (16 sections) |
| [plan.md](../plan.md) | Kế hoạch triển khai tổng (8 phases, 7 milestones) |
| [README.md](../README.md) | Setup conda env + run commands |
| **[milestone_report.md](milestone_report.md)** | **Báo cáo per-milestone chi tiết M1-M6** |
| [m3_plan.md](m3_plan.md) | Plan M3 + collaboration workflow chi tiết cho 2 dev |
| [m4_plan.md](m4_plan.md) | Plan M4 multi-round |
| [m5_plan.md](m5_plan.md) | Plan M5 Non-IID + comparison method |
| [m6_plan.md](m6_plan.md) | Plan M6 fault tolerance (3-phase design) |

**GitHub repo:** https://github.com/Kiencan/federated_learning_mini_system
**Default branch:** `dev` (sau khi M7 + experiments sẽ merge `dev` → `main`)

---

## Phụ lục — Snapshot cấu hình hiện tại (config.yaml)

```yaml
# Training
num_rounds: 30
local_epochs: 2
batch_size: 32
lr: 0.01
seed: 42

# Hardware
device: cuda

# Distributed
wait_timeout: 30          # M6+ default (was 15)
min_clients: 1            # M6+ default cho fault tolerance (was 2)
expected_client_ids:
  - client-0
  - client-1
server_addr: 127.0.0.1:50051  # đổi sang 192.168.2.30:50051 cho LAN

# Experiment
data_split: iid           # iid | noniid (M5+)
straggler_delay: 0        # giây (M7 sẽ dùng)
experiment_name: exp_centralized  # default cho centralized; override per script
results_root: results
run_id: null              # null = auto timestamp
```

---

*Tài liệu này được tạo sau khi M6 merge thành công vào `dev` (commit `d7f8a63`). Cập nhật lại khi M7 + experiments hoàn thành.*
