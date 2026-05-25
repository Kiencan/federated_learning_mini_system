# Kế hoạch triển khai dự án Federated Learning Mini System

> Dự án: Thiết kế và đánh giá hệ thống Federated Learning hai node với giao tiếp gRPC
> Tham khảo: [ytuong.md](ytuong.md)

---

## Nguyên tắc triển khai (MVP-first)

- **Build theo milestone nhỏ, mỗi milestone phải chạy được end-to-end** trước khi thêm tính năng mới
- **Tránh scope creep**: ưu tiên bán tự động hơn là tự động hoàn toàn; ưu tiên cấu hình tập trung hơn là tham số rải rác
- **Acceptance criteria mềm**: kiểm tra hành vi (loss giảm, không stuck) thay vì con số cứng

---

## Milestone triển khai (làm tuần tự)

1. **Centralized baseline chạy được** (1 máy, không gRPC)
2. **gRPC hello world qua 2 máy** (verify network boundary)
3. **Server/client chạy 1 round IID** (chưa cần timeout, chưa cần aggregation phức tạp)
4. **Chạy 5 round IID và log CSV** (verify loop + logging)
5. **Thêm Non-IID partition**
6. **Thêm timeout + stale update rejection**
7. **Straggler + failure experiments** (cuối cùng — phụ thuộc vào 1-6)

---

## Tổng quan timeline

| Giai đoạn | Nội dung | Thời lượng ước tính |
|---|---|---|
| 0 | Chuẩn bị môi trường | 0.5 ngày |
| 1 | Foundation: Model + Data | 1 ngày |
| 2 | gRPC Communication Layer | 1 ngày |
| 3 | Server với FedAvg + Sync logic | 1.5 ngày |
| 3.5 | Config tập trung (song song với 3-4) | 0.5 ngày |
| 4 | Client | 1 ngày |
| 5 | Integration test 2 máy | 0.5 ngày |
| 6 | Experiments (4 kịch bản) | 2-3 ngày |
| 7 | Analysis & Report | 1-2 ngày |
| **Tổng** | | **~8-11 ngày** |

---

## Giai đoạn 0 — Chuẩn bị môi trường (0.5 ngày)

**Trên cả 2 máy:**

- Cài Python 3.10+, CUDA toolkit cho RTX 2000 Ada
- Tạo `requirements.txt`:
  ```
  torch, torchvision         # ML
  grpcio, grpcio-tools       # Communication
  protobuf
  numpy, pandas, matplotlib  # Data + viz
  ```
- Kiểm tra LAN: ping giữa 2 máy, mở firewall port (mặc định gRPC dùng 50051)
- Verify GPU: `torch.cuda.is_available()` trả về True

**Acceptance:** Cả 2 máy ping được nhau, `torch.cuda.is_available() == True` trên cả hai.

---

## Giai đoạn 1 — Foundation: Model + Data (1 ngày)

| File | Mục đích |
|---|---|
| `model.py` | CNN nhỏ: 2 conv (32, 64 filters) + 2 FC + dropout. Hàm `get_weights()`, `set_weights()` để serialize |
| `data_partition.py` | 2 hàm: `partition_iid(num_clients)` và `partition_noniid_pathological()` (Client 1: 0-4, Client 2: 5-9). Tải MNIST qua torchvision |

**Kiểm chứng:** Train centralized 5 epochs → đạt >98% accuracy. Đây cũng là **baseline cho Experiment 1**.

---

## Giai đoạn 2 — gRPC Communication Layer (1 ngày)

1. Viết `proto/federated.proto` với 3 RPC + các message:
   - `ModelWeights { round_id, bytes serialized_weights }`
   - `ClientUpdate { client_id, round_id, weights, num_samples, train_loss, timing_info }`
   - `RoundStatus { current_round, state (WAITING/TRAINING/AGGREGATING) }`
2. Generate code: `python -m grpc_tools.protoc ...`
3. Serialization helper: dùng `torch.save(model.state_dict(), buffer)` vào `io.BytesIO` rồi nhét vào `bytes` field của protobuf.
   - **CHỈ serialize `state_dict`**, KHÔNG serialize toàn bộ `nn.Module` — tránh lỗi dependency/class mismatch khi 2 máy có Python path khác nhau
   - Phía nhận: `model.load_state_dict(torch.load(buffer))`
4. **Smoke test**: server "hello world" trên Máy 1, client gọi RPC từ Máy 2 — verify network boundary thật sự hoạt động

---

## Giai đoạn 3 — Server với FedAvg + Sync logic (1.5 ngày)

`server.py`:

- State machine: `WAITING → TRAINING → AGGREGATING → EVALUATING → next round`
- `GetGlobalModel`: validate `round_id`, trả model hiện tại
- `SubmitUpdate`: reject stale (`round_id != current_round`), unknown client, hoặc `num_samples = 0` — log mọi reject
- Background thread: chờ tối đa `WAIT_TIMEOUT=15s`, aggregate khi đủ `MIN_CLIENTS=1`
- FedAvg: weighted average bằng `num_samples`; nếu chỉ 1 client → dùng nguyên weights đó
- Evaluate global model trên MNIST test set → log accuracy, per-class accuracy, loss
  - **Server evaluation chạy trên CPU** để không tranh GPU với Client 1 (cùng Máy 1). Nếu cần GPU để eval nhanh hơn → phải ghi rõ trong báo cáo là có thể ảnh hưởng timing measurements
- Structured logging ra **2 file**:
  - `round_log.csv`: per-round metrics (round_id, num_clients_received, accuracy, per_class_acc, loss, round_time, comm_size, ...)
  - `events.log` (hoặc `events.csv`): sự kiện rời rạc (stale update reject, client timeout, client reconnect, unknown client reject) với timestamp. Tách riêng để Exp 3 (straggler) và Exp 4 (fault tolerance) dễ phân tích

---

## Giai đoạn 3.5 — Config tập trung (0.5 ngày, làm song song với Giai đoạn 3-4)

Tránh để tham số rải rác giữa server, client, experiments. Tạo `config.yaml` (hoặc class `Config` với argparse) gồm:

```yaml
# Training
num_rounds: 30
local_epochs: 2
batch_size: 32
lr: 0.01
seed: 42                    # set cho random, numpy, torch — giảm dao động giữa các lần chạy

# Hardware
device: "cuda"              # cuda | cpu — client mặc định cuda, server có thể "cpu" để không tranh GPU với Client 1

# Distributed
wait_timeout: 15
min_clients: 1
server_addr: "192.168.x.x:50051"

# Experiment
data_split: "iid"           # iid | noniid
straggler_delay: 0          # giây, 0 = no delay
experiment_name: "exp_federated_iid"
results_root: "results"
run_id: null                # null = auto timestamp (YYYY-MM-DD_HHMM); code tạo {results_root}/{experiment_name}/{run_id}/
```

CLI override: `python server.py --config config.yaml --num-rounds 20`. Lợi ích: chạy lại experiment dễ, viết báo cáo có cấu hình tham chiếu rõ ràng, không cần đổi code khi đổi setup.

**Reproducibility:** Mỗi khi chạy experiment, **copy `config.yaml` snapshot vào `output_dir`** trước khi training bắt đầu. Sau này nhìn vào folder kết quả là biết ngay tham số nào tạo ra biểu đồ nào. Không cần CUDA fully-deterministic — chỉ cần set seed để giảm noise.

**Thêm `run_meta.json` per run** — ghi metadata thực tế lúc chạy (không phải config). Vì federated chạy trên 2 máy, tách rõ server và clients:

```json
{
  "start_time": "2026-05-25T14:30:00",
  "git_commit": "abc123",
  "server": {
    "hostname": "machine-1",
    "torch_version": "2.x.x",
    "device": "cpu"
  },
  "clients": [
    {"client_id": "client-1", "hostname": "machine-1", "gpu_name": "RTX 2000 Ada", "cuda_version": "12.x", "torch_version": "2.x.x"},
    {"client_id": "client-2", "hostname": "machine-2", "gpu_name": "RTX 2000 Ada", "cuda_version": "12.x", "torch_version": "2.x.x"}
  ]
}
```

Mỗi client tự gửi metadata của mình lên server qua một RPC nhỏ khi đăng ký (hoặc gắn vào `ClientUpdate` đầu tiên). Hữu ích khi 2 máy chạy với driver/version khác nhau — giải thích được dao động kết quả.

**Lock môi trường:** Sau khi cài xong dependencies, chạy `pip freeze > requirements.lock` và commit. Báo cáo sẽ tham chiếu được version chính xác.

---

## Giai đoạn 4 — Client (1 ngày)

`client.py`:

- Args: `--client-id`, `--server-addr`, `--data-split (iid|noniid)`
- Loop: poll `GetRoundStatus` mỗi 1s → khi server vào round mới → `GetGlobalModel(round_id)` → train local (E=1-5 epochs, batch 32) → `SubmitUpdate`
- Đo timing 4 phase: download, train, upload, idle
- Gửi cả `train_loss`, `num_samples` thật

---

## Giai đoạn 5 — Integration test 2 máy (0.5 ngày)

- Chạy server + client 1 trên Máy 1, client 2 trên Máy 2
- Chạy 5 round IID — verify accuracy tăng đều, không có stale update
- Fix bugs về network, serialization, sync

**Acceptance:** 5 round IID chạy end-to-end không stuck, loss giảm hoặc accuracy có xu hướng tăng đều. Nếu cấu hình (lr, local epochs, batch size) hợp lý thì accuracy kỳ vọng >80-90%, nhưng không đạt mốc này không có nghĩa là lỗi hệ thống — cần phân biệt lỗi phân tán vs hyperparameter chưa tối ưu.

---

## Giai đoạn 6 — Experiments (2-3 ngày)

**Mức độ tự động hóa:** Bán tự động. Tự động hóa toàn phần đòi hỏi SSH/PowerShell remoting để start/stop process trên máy 2 → scope phình to.

Mô hình bán tự động:

```text
- experiments.py trên server ghi config cho experiment hiện tại (file hoặc qua RPC riêng).
- Client đọc flags khi khởi động hoặc poll config từ server.
- Các kịch bản như crash/reconnect: thao tác thủ công, ghi lại timestamp để map vào log CSV.
```

`experiments.py` orchestrate từng kịch bản, output CSV vào `results/`:

| Exp | Cần thêm gì |
|---|---|
| **1. Centralized vs Federated** | Script centralized riêng — train trên Máy 1 với toàn bộ data. So sánh accuracy + wall-clock time. <br>**Trục x khi vẽ chung**: dùng wall-clock time là chính (centralized đo theo epoch, federated theo round — không cùng đơn vị). Có thể vẽ thêm biểu đồ phụ accuracy vs round/epoch để quan sát xu hướng |
| **2. IID vs Non-IID** | Chỉ đổi flag `--data-split`. Chạy 20-30 round mỗi setup. Vẽ accuracy curve + per-class accuracy. <br>**Tái sử dụng run**: Federated IID dùng cho cả Exp 1 và Exp 2 nếu cùng `num_rounds`, `local_epochs`, `lr`, `seed` — không chạy trùng |
| **3. Straggler** | Thêm `--straggler-delay` cho client 2. Chạy 2 lần: <br>• Case A — No effective timeout: `WAIT_TIMEOUT = straggler_delay + 30s` (đủ lớn để client chậm kịp gửi) <br>• Case B — Timeout: `WAIT_TIMEOUT = 15s` (server bỏ client chậm) <br>**Không dùng `∞` thật** — dễ treo experiment nếu client crash thầm lặng |
| **4. Fault tolerance** | Thao tác **bán thủ công**: tự `Ctrl+C` client 2 ở round 5, restart ở round 8. Ghi lại timestamp các sự kiện vào notes để map với log CSV. Verify server vẫn aggregate với 1 client |

---

## Giai đoạn 7 — Analysis & Report (1-2 ngày)

- Notebook hoặc script tạo plots:
  - `accuracy_per_round.png` (3 đường: Federated IID, Federated Non-IID, Centralized baseline). Centralized chỉ là 1 baseline — không tách IID/Non-IID vì dữ liệu đã gom về 1 máy
  - `round_time_breakdown.png` (stacked bar: download/train/upload/wait)
  - `communication_overhead.png` (MB cumulative)
- Báo cáo theo cấu trúc section 7 của file ý tưởng (5 vấn đề distributed systems):
  1. Communication Overhead
  2. Synchronization Model
  3. Straggler Problem
  4. Fault Tolerance
  5. Data Heterogeneity (Non-IID)

---

## Thứ tự nên làm ngay

1. **Tạo skeleton project + `requirements.txt`** trên Máy 1
2. **Verify GPU + LAN connectivity** giữa 2 máy trước khi viết code
3. Build theo thứ tự: `model.py` → `data_partition.py` → proto → server stub → client stub → integration

---

## Rủi ro cần lưu ý

- **Windows firewall** thường chặn gRPC — mở port 50051 trước
- **Serialization size**: `torch.save` một model CNN nhỏ ≈ 200-400KB, ổn cho gRPC default `MAX_MESSAGE_LENGTH=4MB`, không cần tweak
- **Non-IID pathological** có thể không hội tụ — đây là kết quả mong muốn để phân tích, đừng tưởng là bug
- **Stale update**: client 2 chậm có thể gửi update của round cũ — server PHẢI reject (đã có trong design)
- **GPU driver mismatch** giữa 2 máy có thể gây sai lệch nhỏ về numerical — không ảnh hưởng kết quả nhưng cần ghi lại trong báo cáo

---

## Cấu trúc thư mục mục tiêu

```text
federated-learning-mini/
│
├── proto/
│   └── federated.proto
│
├── server.py
├── client.py
├── model.py
├── data_partition.py
├── experiments.py
│
├── requirements.txt
├── requirements.lock           # pip freeze sau khi cài, commit để báo cáo có version chính xác
├── README.md
│
└── results/
    ├── exp_centralized/                  # dùng cho Exp 1
    │   └── 2026-05-25_1430/              # 1 run = 1 subfolder timestamp
    │       ├── config.yaml
    │       ├── run_meta.json
    │       ├── round_log.csv
    │       └── events.log
    ├── exp_federated_iid/                # dùng cho cả Exp 1 và Exp 2
    │   └── 2026-05-25_1500/
    ├── exp_federated_noniid/             # dùng cho Exp 2
    ├── exp_straggler_no_effective_timeout/  # Exp 3 case A
    ├── exp_straggler_timeout_15s/        # Exp 3 case B
    ├── exp_fault_tolerance/              # Exp 4
    └── plots/
        ├── accuracy_per_round.png
        ├── round_time_comparison.png
        └── communication_overhead.png
```

**Quy ước:** Mỗi `exp_*/` chứa các subfolder theo `run_id` (timestamp `YYYY-MM-DD_HHMM`). Mỗi run subfolder gồm 4 file: `config.yaml`, `run_meta.json`, `round_log.csv`, `events.log`. Chạy lại experiment → tạo subfolder mới, không overwrite. Khi vẽ plot, chọn run mới nhất hoặc chỉ định run cụ thể.

**Mapping run → experiment:**

| Experiment | Runs sử dụng |
|---|---|
| Exp 1: Centralized vs Federated | `exp_centralized` vs `exp_federated_iid` |
| Exp 2: IID vs Non-IID | `exp_federated_iid` vs `exp_federated_noniid` |
| Exp 3: Straggler | `exp_straggler_no_effective_timeout` vs `exp_straggler_timeout_15s` |
| Exp 4: Fault tolerance | `exp_fault_tolerance` |

`exp_federated_iid` được dùng cho cả Exp 1 và Exp 2 — chỉ chạy 1 lần.

---

## Checklist deliverables cuối dự án

- [ ] Source code chạy được trên 2 máy vật lý
- [ ] Log kết quả cho toàn bộ experiments — mỗi run có `config.yaml`, `round_log.csv`, `events.log`, `run_meta.json`
- [ ] 3+ biểu đồ phân tích (accuracy, round time, communication)
- [ ] Báo cáo phân tích tradeoff:
  - [ ] Parallel training vs distributed overhead (Exp 1)
  - [ ] IID vs Non-IID convergence (Exp 2)
  - [ ] Straggler impact (Exp 3)
  - [ ] Fault tolerance behavior (Exp 4)
- [ ] README hướng dẫn chạy lại experiments
