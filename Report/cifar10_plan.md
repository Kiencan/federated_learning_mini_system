# Kế hoạch Phase CIFAR-10 — mở rộng dataset + benchmark 1 máy vs 2 máy

Mục tiêu: mở rộng từ MNIST sang **CIFAR-10** (ảnh màu 3×32×32, khó hơn nhiều),
dùng **model lớn hơn**, và **đo communication time** để báo cáo so sánh:
**thời gian train 1 máy vs 2 máy, accuracy, communication time**.

## 1. Thay đổi code (đã xong — dataset-agnostic)

Toàn bộ pipeline chuyển sang chọn dataset qua factory, không hardcode MNIST nữa:

| Thành phần | Mô tả |
|------------|-------|
| `build_model(dataset)` ([model.py](../model.py)) | `mnist` → `MnistCNN` (2 conv, 421K params) · `cifar10` → `CifarCNN` (3 conv + BatchNorm, 620K params) |
| `load_dataset(name)` ([data_partition.py](../data_partition.py)) | `load_mnist()` / `load_cifar10()`; CIFAR-10 mean/std chuẩn |
| `config.yaml` | thêm `dataset: mnist\|cifar10` |
| CLI `--dataset` ([run_context.py](../run_context.py)) | override config trên mọi script |
| round_log.csv ([server.py](../server.py)) | thêm `model_bytes`, `client_{0,1}_download_ms` (=communication), `client_{0,1}_train_ms` (=compute) |

`partition_iid` / `partition_noniid_pathological` dùng chung cho cả 2 dataset
(CIFAR-10 Non-IID: client-0 lớp 0–4, client-1 lớp 5–9). Cả 2 đều 10 lớp nên
`aggregation.evaluate()` và `fedavg()` không cần đổi.

## 2. Setup mạng 2 máy (Ethernet trực tiếp)

- Máy 1 = `10.0.0.1`, Máy 2 = `10.0.0.2`, prefix /24 (gán bằng `New-NetIPAddress` qua PowerShell Admin)
- Ping steady-state **< 1ms** (round đầu spike do ARP — bình thường)
- Firewall: cho phép port `50051` inbound trên Máy 1, đặt profile Ethernet là **Private**

## 3. Kịch bản benchmark (CIFAR-10, đề xuất `num_rounds=30`, `local_epochs=2`)

> Activate env trước: `conda activate fedml`. Dataset tự download lần đầu (~170MB).

### B1 — 1 máy, Centralized (baseline tốc độ train thuần)
Chạy trên **Máy 1**:
```powershell
python centralized_train.py --dataset cifar10 --experiment-name exp_cifar_centralized --run-id m1
```

### B2 — 1 máy, Federated (server + 2 client cùng localhost)
Đo overhead gRPC khi KHÔNG qua mạng vật lý. 3 terminal trên **Máy 1**:
```powershell
# Terminal 1 — server
python server.py --dataset cifar10 --experiment-name exp_cifar_fed_1machine --run-id m1 --bind 127.0.0.1:50051
# Terminal 2 — client-0
python client.py --dataset cifar10 --client-id client-0 --shard-id 0 --num-shards 2 --server-addr 127.0.0.1:50051 --experiment-name exp_cifar_fed_1machine --run-id m1
# Terminal 3 — client-1
python client.py --dataset cifar10 --client-id client-1 --shard-id 1 --num-shards 2 --server-addr 127.0.0.1:50051 --experiment-name exp_cifar_fed_1machine --run-id m1
```

### B3 — 2 máy, Federated (qua Ethernet — đo communication thật)
- **Máy 1** (server + client-0):
```powershell
# Terminal 1 — server (bind LAN)
python server.py --dataset cifar10 --experiment-name exp_cifar_fed_2machine --run-id m1 --bind 0.0.0.0:50051
# Terminal 2 — client-0
python client.py --dataset cifar10 --client-id client-0 --shard-id 0 --num-shards 2 --server-addr 10.0.0.1:50051 --experiment-name exp_cifar_fed_2machine --run-id m1
```
- **Máy 2** (client-1):
```powershell
python client.py --dataset cifar10 --client-id client-1 --shard-id 1 --num-shards 2 --server-addr 10.0.0.1:50051 --experiment-name exp_cifar_fed_2machine --run-id m2
```

> Lưu ý timing: Máy 2 cold start (Python+torch+CIFAR+GPU) có thể lâu → nếu cần,
> tăng `--wait-timeout` (vd 90) ở server cho round đầu.

## 4. Tiêu chí báo cáo (từ round_log.csv + run_meta.json)

| Tiêu chí | Lấy từ |
|----------|--------|
| Thời gian train 1 máy vs 2 máy | `round_wallclock_sec` (tổng), `client_*_train_ms` (compute thuần) |
| Accuracy | `accuracy` cuối + đường cong theo round |
| Communication time | `client_*_download_ms` (download); upload ≈ download vì payload `model_bytes` đối xứng |
| Kích thước model | `model_bytes` (~2.4MB CIFAR vs ~1.6MB MNIST) |

So sánh: B1 (train thuần) < B2 (+ overhead gRPC localhost) < B3 (+ communication mạng).
Phân tích communication overhead chiếm bao nhiêu % round time khi scale ra 2 máy.

## 5. Trạng thái

- [x] Refactor dataset-agnostic + CifarCNN + cột communication timing
- [x] Smoke test e2e CIFAR-10 PASS (2 round, acc 57%→66%, cột timing ghi đúng)
- [x] Regression MNIST OK
- [x] Chạy benchmark B1/B2/B3 trên 2 máy (30 round mỗi bộ, data ở `Report/data/`)
- [x] Đo throughput thô link Ethernet: **2.36 Gbps** (`tools/throughput_test.py`, 1GB)
- [x] Sinh 3 hình so sánh (`analyze_cifar.py` → `Report/figures/cifar_*.png`)
- [x] **Rendezvous barrier**: fix đo round-1 (89.6s → 10.96s), chạy lại B3 sạch (run `m1_rv2`)
- [x] **opt-A tăng tốc**: eval off critical path + poll 0.5s → B3 round 14.5s→10.7s (26%),
      chênh phân tán giảm 72% (3.2s→0.9s). Runs `m1_opt` (B2), `m1_opt5` (B3).
- [x] **opt-B cân bằng shard**: `--shard-weights 0.45,0.55` (Máy 1 ít data hơn) → B3 10.7s→9.8s
      ≈ B2 9.7s. Chênh phân tán 3.2s→0.1s (triệt tiêu). Run `m1_optB`.
- [x] Viết báo cáo so sánh: [bao_cao_cifar10.md](bao_cao_cifar10.md)

**Kết quả cuối** (bộ 3 anchor Máy 1, federated có rendezvous): B1 80.26% · B2 81.97% · B3 81.73%
accuracy. Communication chỉ chiếm
~0.3% round time; nút cổ chai là compute + đồng bộ, không phải mạng. Phân tán 2 máy KHÔNG
tăng tốc với workload nhẹ này (round bị gate bởi node kiêm server). Rendezvous barrier loại
boot time khỏi round-1 (89.6s→10.96s). Fault tolerance verified (client chết → partial aggregate).
Chi tiết trong báo cáo §3.4.
