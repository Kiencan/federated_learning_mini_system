# Federated Learning Mini System

Hệ thống Federated Learning hai node với giao tiếp gRPC trên MNIST + CNN nhỏ. Dự án phân tích **5 vấn đề distributed systems**: communication overhead, bounded synchronization, straggler problem, fault tolerance, data heterogeneity — trọng tâm là **hệ phân tán**, không phải tối ưu accuracy.

Đã hoàn thành đầy đủ 7 milestone + 4 experiments. Kết quả và phân tích chi tiết nằm trong **báo cáo cuối kỳ**:

- [Report/bao_cao_cuoi_ky.md](Report/bao_cao_cuoi_ky.md) · [bản DOCX](Report/bao_cao_cuoi_ky.docx)
- Chi tiết milestone: [Report/milestone_report.md](Report/milestone_report.md)
- Spec gốc: [ytuong.md](ytuong.md) · Kế hoạch: [plan.md](plan.md)

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

Verify GPU: `python -c "import torch; print(torch.cuda.is_available())"`

## Chạy

Cross-machine: Máy 1 chạy server + client-0, Máy 2 chạy client-1 (đổi `--server-addr` thành IP Máy 1). Localhost: cả 3 trên một máy với `127.0.0.1`.

### Centralized baseline

```powershell
python centralized_train.py --num-rounds 20 --run-id baseline_20ep
```

### Federated — IID

```powershell
python server.py --num-rounds 20 --min-clients 2 --wait-timeout 60 `
    --experiment-name exp_federated_iid --run-id baseline_20r
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --server-addr 127.0.0.1:50051
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --server-addr 127.0.0.1:50051
```

> Server dùng `wait_for_termination()` — sau khi DONE phải **Ctrl+C** để giải phóng cổng 50051 trước run kế tiếp.

### Federated — Non-IID

Thêm `--data-split noniid` cho **cả server và 2 client** (đổi `--experiment-name exp_federated_noniid`).

### Straggler

Thêm `--straggler-delay <giây>` cho client (sleep trước SubmitUpdate). Ví dụ S2 (timeout drop):

```powershell
python server.py --num-rounds 3 --wait-timeout 20 --min-clients 1 --straggler-delay 20 --run-id s2
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --straggler-delay 20 --server-addr 127.0.0.1:50051
```

### Fault tolerance

Chạy nhiều round, **Ctrl+C client-1 giữa run** rồi khởi động lại — server tiếp tục với 1 client (partial aggregation) rồi nhận lại client khi reconnect.

## Cấu trúc dự án

```text
.
├── proto/federated.proto        # 3 RPC: GetGlobalModel, SubmitUpdate, GetRoundStatus
├── server.py                    # FedAvg + state machine + bounded-sync aggregation
├── client.py                    # multi-round loop + straggler injection
├── model.py                     # MnistCNN + serialize state_dict
├── data_partition.py            # partition_iid / partition_noniid_pathological
├── aggregation.py               # FedAvg weighted average
├── centralized_train.py         # baseline tập trung
├── run_context.py               # config + CLI parser dùng chung
├── analyze.py                   # round_log.csv → 4 plots + metrics
├── generate_docx.js             # sinh báo cáo DOCX
├── config.yaml                  # config tập trung
├── Report/                      # báo cáo, milestone_report, figures/, data/
├── tests/                       # smoke + validation tests
└── results/                     # run outputs (gitignored)
```

## Cross-machine: firewall

Lần đầu, nếu Windows Firewall chặn, mở PowerShell Admin trên Máy 1:

```powershell
New-NetFirewallRule -DisplayName "FedML gRPC 50051" -Direction Inbound -Protocol TCP -LocalPort 50051 -Action Allow
```

`Test-NetConnection <ip-may-1> -Port 50051` từ Máy 2 chỉ `True` khi server đang listening.
