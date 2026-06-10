# Federated Learning Mini System

Hệ thống Federated Learning hai node với giao tiếp gRPC trên MNIST + CNN nhỏ. Dự án phân tích **5 vấn đề distributed systems**: communication overhead, bounded synchronization, straggler problem, fault tolerance, data heterogeneity — trọng tâm là **hệ phân tán**, không phải tối ưu accuracy.

> **Trạng thái: HOÀN THÀNH.** Toàn bộ 7 milestone + 4 experiments + báo cáo cuối kỳ đã xong.

- Spec gốc: [ytuong.md](ytuong.md) · Kế hoạch: [plan.md](plan.md)
- **Báo cáo cuối kỳ**: [Report/bao_cao_cuoi_ky.md](Report/bao_cao_cuoi_ky.md) · [bản DOCX](Report/bao_cao_cuoi_ky.docx)
- Chi tiết 7 milestone: [Report/milestone_report.md](Report/milestone_report.md)
- Kế hoạch thí nghiệm: [Report/experiments_plan.md](Report/experiments_plan.md)

## Hardware mục tiêu

| | Máy 1 | Máy 2 |
|---|---|---|
| GPU | RTX 2000 Ada | RTX 2000 Ada |
| Vai trò | Server + Client-0 | Client-1 |
| Kết nối | LAN | LAN |

## Kết quả chính

| Experiment | Kết quả | Vấn đề DS |
|---|---|---|
| **1. Centralized vs Federated** | Fed IID 99.38% ≈ Centralized 99.29% — phân tán không giảm accuracy với IID | — |
| **2. IID vs Non-IID** | Non-IID hội tụ chậm (avg 5 round đầu 96.04% vs 99.06%), lệch per-class (class 3: 95%, class 9: 96.3%) | §7.5 Heterogeneity |
| **3. Straggler** | S1 chờ (round +5s, acc cao) vs S2 drop straggler (timeout, partial, acc giảm) | §7.3 Straggler |
| **4. Fault tolerance** | 4-phase crash/recovery, server không sập, acc đỉnh 99.41% | §7.4 Fault tolerance |
| **Communication** | 6.44 MiB/round; round time chi phối bởi client compute+comm, aggregation ~2ms | §7.1, §7.2 |

## Tiến độ milestone

- [x] **M1** — Centralized baseline (1 máy, không gRPC)
- [x] **M2** — gRPC hello world qua 2 máy (LAN RTT 3.5–6ms)
- [x] **M3** — Server/client chạy 1 round IID + 4 lớp validation
- [x] **M4** — Multi-round IID + log CSV
- [x] **M5** — Non-IID pathological partition (0–4 vs 5–9)
- [x] **M6** — WAIT_TIMEOUT + dynamic MIN_CLIENTS (fault tolerance, async aggregation)
- [x] **M7** — Straggler injection + crash/reconnect experiments
- [x] **Experiments** — 4 thí nghiệm + 4 biểu đồ + báo cáo cuối kỳ

## Cấu trúc dự án

```text
.
├── proto/federated.proto        # 3 RPC: GetGlobalModel, SubmitUpdate, GetRoundStatus
├── server.py                    # FedAvg + state machine + bounded-sync aggregation
├── client.py                    # multi-round loop + straggler injection
├── model.py                     # MnistCNN + serialize state_dict
├── data_partition.py            # partition_iid / partition_noniid_pathological
├── aggregation.py               # FedAvg weighted average
├── centralized_train.py         # baseline tập trung (Exp 1)
├── run_context.py               # config + CLI parser dùng chung
├── gen_proto.py                 # generate protobuf code
├── analyze.py                   # E1: đọc round_log.csv → 4 plots + metrics
├── generate_docx.js             # sinh báo cáo DOCX (docx-js)
├── config.yaml                  # config tập trung
├── environment.yml / requirements.txt
├── Report/
│   ├── bao_cao_cuoi_ky.md / .docx   # báo cáo cuối kỳ
│   ├── milestone_report.md          # chi tiết M1–M7
│   ├── experiments_plan.md
│   ├── figures/*.png                # 4 biểu đồ
│   └── data/                        # CSV inputs cho analyze.py (tracked, reproducible)
├── tests/                       # smoke + validation tests
└── results/                     # run outputs (gitignored)
    └── exp_*/<run_id>/{config.yaml, run_meta.json, round_log.csv, events.csv}
```

## Setup môi trường

**Conda (khuyến nghị)** — Python 3.11 + PyTorch CUDA 12.1:

```powershell
conda env create -f environment.yml
conda activate fedml
```

**Hoặc venv + pip:**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Verify GPU:

```powershell
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

## Chạy

### Centralized baseline (Exp 1)

```powershell
python centralized_train.py --num-rounds 20 --run-id baseline_20ep
```

### Federated — IID (localhost hoặc cross-machine)

**Server** (Máy 1):
```powershell
python server.py --num-rounds 20 --min-clients 2 --wait-timeout 60 `
    --experiment-name exp_federated_iid --run-id baseline_20r
```

**Client-0** (Máy 1) + **Client-1** (Máy 2, đổi server-addr thành IP Máy 1):
```powershell
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --server-addr 127.0.0.1:50051
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --server-addr 127.0.0.1:50051
```

> Server dùng `wait_for_termination()` — sau khi DONE phải **Ctrl+C** để giải phóng cổng 50051 trước run kế tiếp.

### Federated — Non-IID (Exp 2)

Thêm `--data-split noniid` cho **cả server và 2 client**:
```powershell
python server.py --num-rounds 20 --min-clients 2 --wait-timeout 60 --data-split noniid `
    --experiment-name exp_federated_noniid --run-id baseline_20r
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --data-split noniid --server-addr 127.0.0.1:50051
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --data-split noniid --server-addr 127.0.0.1:50051
```

### Straggler (Exp 3)

Thêm `--straggler-delay <giây>` cho client (sleep trước SubmitUpdate). Ví dụ S2 (timeout drop):
```powershell
python server.py --num-rounds 3 --wait-timeout 20 --min-clients 1 --straggler-delay 20 --run-id s2
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --server-addr 127.0.0.1:50051
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --straggler-delay 20 --server-addr 127.0.0.1:50051
```

### Fault tolerance (Exp 4)

Chạy nhiều round, **Ctrl+C client-1 giữa run** rồi khởi động lại — server tiếp tục với 1 client (partial aggregation) rồi nhận lại client khi reconnect.

### Phân tích + biểu đồ (E1)

```powershell
python analyze.py                       # đọc Report/data/ (tracked) → Report/figures/*.png + metrics
python analyze.py --data-root results   # hoặc chạy trên run outputs gốc
```

### Sinh báo cáo DOCX

```powershell
$env:NODE_PATH = (npm root -g); node generate_docx.js   # → Report/bao_cao_cuoi_ky.docx
```

## Cross-machine: firewall

Lần đầu, nếu Windows Firewall chặn, mở PowerShell Admin trên Máy 1:
```powershell
New-NetFirewallRule -DisplayName "FedML gRPC 50051" -Direction Inbound -Protocol TCP -LocalPort 50051 -Action Allow
```

`Test-NetConnection <ip-may-1> -Port 50051` từ Máy 2 chỉ `True` khi server đang listening.

## Git workflow

- `main`: trạng thái stable, đã verify
- `dev`: nhánh phát triển — mọi milestone/feature implement ở đây trước (qua feature branch + PR)
- Khi ổn → merge `dev` vào `main`
