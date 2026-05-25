# Federated Learning Mini System

Hệ thống Federated Learning hai node với giao tiếp gRPC trên MNIST + CNN nhỏ. Dự án phân tích các vấn đề distributed systems: communication overhead, bounded synchronization, straggler problem, fault tolerance, data heterogeneity.

- Spec gốc: [ytuong.md](ytuong.md)
- Kế hoạch triển khai: [plan.md](plan.md)

## Hardware mục tiêu

| | Máy 1 | Máy 2 |
|---|---|---|
| GPU | RTX 2000 Ada | RTX 2000 Ada |
| Vai trò | Server (CPU) + Client 1 | Client 2 |
| Kết nối | LAN | LAN |

## Git workflow

- `main`: trạng thái stable, đã verify chạy được trên 2 máy
- `dev`: nhánh phát triển, mọi milestone implement ở đây trước
- Khi milestone ổn → merge `dev` vào `main` qua PR

## Tiến độ milestone

- [x] **M1** — Centralized baseline (1 máy, không gRPC) — verified 98.94% acc sau 2 epoch
- [x] **M2** — gRPC hello world qua 2 máy — verified LAN RTT 3.5-6ms
- [ ] **M3** — Server/client chạy 1 round IID
- [ ] **M4** — Chạy 5 round IID + log CSV
- [ ] **M5** — Thêm Non-IID partition
- [ ] **M6** — Timeout + stale update rejection
- [ ] **M7** — Straggler + failure experiments

## Cấu trúc dự án

Xem chi tiết trong [plan.md](plan.md). Cấu trúc đích:

```text
.
├── proto/federated.proto
├── server.py
├── client.py
├── model.py
├── data_partition.py
├── experiments.py
├── config.yaml
├── requirements.txt
├── requirements.lock
└── results/
    └── exp_*/<run_id>/
        ├── config.yaml
        ├── run_meta.json
        ├── round_log.csv
        └── events.log
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

### Milestone 1 — Centralized baseline

```powershell
python centralized_train.py --num-rounds 10
```

Output: `results/exp_centralized/<run_id>/{config.yaml, run_meta.json, round_log.csv}`

### Milestone 2 — gRPC hello world

**Máy 1** (server):
```powershell
python server.py --bind 0.0.0.0:50051
```

**Máy 2** (client):
```powershell
python client.py --client-id client-2 --server-addr <ip-may-1>:50051 --poll 5
```

Lần đầu: nếu Windows Firewall chặn, mở PowerShell Admin trên Máy 1 chạy:
```powershell
New-NetFirewallRule -DisplayName "FedML gRPC 50051" -Direction Inbound -Protocol TCP -LocalPort 50051 -Action Allow
```
