# Báo cáo tiến độ — Federated Learning Mini System

Tài liệu này theo dõi kết quả thực hiện từng milestone của dự án. Mỗi milestone gồm: mục tiêu, công việc đã làm, kết quả verified, file đã thêm/sửa, và các vấn đề gặp phải.

> Liên kết: [Spec gốc (ytuong.md)](../ytuong.md) · [Kế hoạch triển khai (plan.md)](../plan.md) · [GitHub repo](https://github.com/Kiencan/federated_learning_mini_system)

---

## Tổng quan tiến độ

| Milestone | Mục tiêu | Trạng thái | Commit |
|---|---|---|---|
| M1 | Centralized baseline (1 máy, không gRPC) | ✅ Done | `49734cb` |
| M2 | gRPC hello world qua 2 máy | ✅ Done | `ada1e41` → `b2bd2fe` |
| M3 | Server/client chạy 1 round IID | ⏳ Pending | — |
| M4 | Chạy 5 round IID + log CSV | ⏳ Pending | — |
| M5 | Thêm Non-IID partition | ⏳ Pending | — |
| M6 | Timeout + stale update rejection | ⏳ Pending | — |
| M7 | Straggler + failure experiments | ⏳ Pending | — |

**Hardware đang dùng:**
- Máy 1: Windows, NVIDIA RTX 2000 Ada Generation, CUDA 12.1, LAN IP `192.168.2.30`
- Máy 2: Windows, NVIDIA RTX 2000 Ada Generation, CUDA 12.1
- Kết nối: LAN

**Môi trường:**
- Conda env `fedml` Python 3.11.15
- PyTorch 2.5.1+cu121 · torchvision 0.20.1+cu121
- grpcio 1.80.0 · protobuf 6.33.6
- numpy 2.4.4 · pandas 3.0.3 · matplotlib 3.10.9 · pyyaml 6.0.3

---

## Milestone 1 — Centralized Baseline

### Mục tiêu

Train CNN nhỏ trên toàn bộ MNIST trên một máy đơn (không có federated, không có gRPC) để:

1. Verify environment (CUDA, PyTorch, GPU) hoạt động
2. Có **baseline accuracy + wall-clock time** để so sánh với federated runs trong Experiment 1 sau này
3. Dựng sẵn cấu trúc shared code (model, data loader, run context, config) cho các milestone sau

### Công việc đã làm

**Cấu trúc project skeleton:**

```text
.
├── config.yaml             # Cấu hình chung centralized + federated
├── model.py                # CNN + serialization helpers
├── data_partition.py       # MNIST loaders + IID/Non-IID split
├── run_context.py          # CLI parser, seed, run_dir, run_meta
├── centralized_train.py    # M1 baseline
├── requirements.txt        # Pin tối thiểu
├── requirements.lock       # Snapshot từ pip freeze
├── environment.yml         # Conda env reproducible
├── .gitignore              # Python + data/ + results/
└── results/
    └── exp_centralized/<run_id>/
        ├── config.yaml     # Snapshot tham số
        ├── run_meta.json   # Hostname, torch/cuda version, GPU, git commit
        └── round_log.csv   # Per-epoch metrics
```

**Thiết kế quan trọng:**

- **Model** (`model.py`): CNN gồm 2 conv (32, 64 filters) + max-pool + dropout 0.25 + 2 FC. Tổng state_dict ≈ **1.65 MB** (dưới gRPC default `4 MB` nên không cần tweak).
- **Serialize/deserialize** state_dict bằng `torch.save` vào `io.BytesIO` — **chỉ state_dict, không serialize toàn bộ `nn.Module`** để tránh class/dependency mismatch giữa máy.
- **Data partition** (`data_partition.py`): Đã viết sẵn `partition_iid` và `partition_noniid_pathological` để dùng cho M3+. Centralized chỉ cần `load_mnist` full set.
- **Run context** (`run_context.py`): Tập trung mọi tiện ích chung:
  - `load_config` đọc YAML + override từ CLI args
  - `set_seed` cho `random`, `numpy`, `torch.manual_seed`
  - `create_run_dir` tạo `results/{experiment_name}/{run_id}/` và snapshot `config.yaml` vào đó
  - `write_run_meta` ghi `run_meta.json` (hostname, torch version, CUDA version, GPU name, git commit)
- **CSV log** per-epoch: `train_loss, test_loss, accuracy, epoch_time_sec, cumulative_time_sec, acc_class_0..9`. Per-class accuracy phục vụ phân tích Non-IID sau này.

### Kết quả verified (smoke test)

Lệnh: `python centralized_train.py --num-rounds 2 --run-id smoke_test`

| Epoch | train_loss | test_loss | accuracy | time (s) |
|---|---|---|---|---|
| 1 | 0.1617 | 0.0576 | 98.23% | 6.58 |
| 2 | 0.0495 | 0.0327 | 98.94% | 9.06 |

Per-class accuracy sau 2 epoch: tất cả lớp ≥ 98%, không có lớp nào tụt rõ.

`run_meta.json` ghi nhận đầy đủ:
```json
{
  "start_time": "2026-05-25T12:51:22",
  "git_commit": "49734cb",
  "nodes": [{
    "role": "centralized_trainer",
    "hostname": "admin",
    "torch_version": "2.5.1+cu121",
    "device": "cuda",
    "cuda_available": true,
    "gpu_name": "NVIDIA RTX 2000 Ada Generation",
    "cuda_version": "12.1"
  }]
}
```

### Acceptance criteria

- [x] End-to-end chạy không stuck
- [x] Loss giảm rõ (0.162 → 0.050) và accuracy tăng (98.23 → 98.94%)
- [x] `config.yaml` snapshot + `run_meta.json` + `round_log.csv` được tạo đúng cấu trúc folder
- [x] Per-class accuracy được log đầy đủ

> **Lưu ý:** Đây mới là smoke test 2 epoch. Để có baseline thật cho Experiment 1 cần chạy 30 epoch (~3-5 phút trên GPU), sẽ làm ở giai đoạn experiments.

### Vấn đề gặp phải

- **Conda env `phantan` cũ (Python 3.8.20)** không phù hợp — đã tạo env mới `fedml` Python 3.11.
- **MNIST download từ `yann.lecun.com` bị 404** — torchvision tự fallback sang S3 mirror `ossci-datasets.s3.amazonaws.com`, không cần can thiệp.
- **Windows console encoding cp1252** không in được tiếng Việt có dấu trong `gen_proto.py` — đã đổi text print sang ASCII.

---

## Milestone 2 — gRPC Hello World qua 2 máy

### Mục tiêu

Verify network boundary thật sự hoạt động giữa Máy 1 và Máy 2 qua gRPC + protobuf:

1. Định nghĩa **toàn bộ proto schema** ngay từ đầu để M3+ không cần churn
2. Build server tối thiểu trên Máy 1 và client trên Máy 2 chạy được 1 RPC end-to-end
3. Đo RTT thật trên LAN

### Công việc đã làm

**Proto schema đầy đủ** (`proto/federated.proto`):

```protobuf
service FederatedLearning {
  rpc GetGlobalModel (RoundRequest) returns (ModelWeights);
  rpc SubmitUpdate   (ClientUpdate) returns (AckResponse);
  rpc GetRoundStatus (Empty)        returns (RoundStatus);
}
```

Messages chính:
- `RoundRequest { round_id, client_id }`
- `ModelWeights { round_id, serialized_state_dict }` — bytes là `torch.save` của state_dict
- `ClientUpdate { client_id, round_id, serialized_state_dict, num_samples, train_loss, timing, hostname, gpu_name, torch_version, cuda_version }` — metadata gửi 1 lần đầu để server ghi `run_meta.json`
- `AckResponse { accepted, message, server_round }` — `message` chứa lý do reject khi `accepted=false` (stale round, unknown client...)
- `RoundStatus { current_round, state, num_rounds_total }` với enum State: `UNKNOWN, WAITING, TRAINING, AGGREGATING, EVALUATING, DONE`

**Server tối thiểu** (`server.py`):
- Bind `0.0.0.0:50051` để chấp nhận cả localhost lẫn LAN
- Chỉ implement `GetRoundStatus` (trả mock data: round=0, state=WAITING)
- `GetGlobalModel` + `SubmitUpdate` trả `UNIMPLEMENTED` (sẽ làm ở M3)
- Cấu hình `grpc.max_{send,receive}_message_length = 16 MB` để dự phòng model size lớn hơn sau này
- Graceful shutdown với Ctrl+C (stop grace 2s)

**Client tối thiểu** (`client.py`):
- Đọc `server_addr` từ config.yaml (mặc định `127.0.0.1:50051`), có thể override bằng `--server-addr`
- `grpc.channel_ready_future(timeout=5s)` — bắt lỗi network sớm, không treo vô hạn
- `--poll N` để gọi `GetRoundStatus` N lần liên tiếp, đo RTT từng lần

**Tooling:**
- `gen_proto.py`: chạy `grpc_tools.protoc` để regenerate `federated_pb2.py` + `federated_pb2_grpc.py`. **Commit cả file generated** để máy khác chạy được mà không cần cài `grpcio-tools`.
- `proto/__init__.py`: biến proto thành Python package, import bằng `from proto import federated_pb2`.

### Kết quả verified

**Localhost test (Máy 1):**
```
[client client-localhost] connecting to 127.0.0.1:50051
[client] poll 1/3: round=0/30 state=WAITING rtt=1.3ms
[client] poll 2/3: round=0/30 state=WAITING rtt=1.2ms
[client] poll 3/3: round=0/30 state=WAITING rtt=2.0ms
```

**Self-loopback qua LAN IP (Máy 1 → 192.168.2.30):**
```
[client] poll 1/2: round=0/30 state=WAITING rtt=1.1ms
[client] poll 2/2: round=0/30 state=WAITING rtt=0.9ms
```

**Cross-machine LAN test (Máy 2 → 192.168.2.30):**
```
[client client-2] connecting to 192.168.2.30:50051
[client] poll 1/5: round=0/30 state=WAITING rtt=6.1ms
[client] poll 2/5: round=0/30 state=WAITING rtt=4.4ms
[client] poll 3/5: round=0/30 state=WAITING rtt=3.5ms
[client] poll 4/5: round=0/30 state=WAITING rtt=5.6ms
[client] poll 5/5: round=0/30 state=WAITING rtt=5.0ms
```

**Tóm tắt timing:**

| Setup | RTT min | RTT max | RTT avg |
|---|---|---|---|
| Localhost (Máy 1) | 1.2 ms | 2.0 ms | ~1.5 ms |
| LAN cross-machine (Máy 1 ↔ Máy 2) | 3.5 ms | 6.1 ms | ~4.9 ms |

LAN overhead so với localhost: ~3-4 ms — phù hợp mạng nội bộ Windows. Đây là **độ trễ baseline** sẽ cộng vào communication time của mỗi `GetGlobalModel`/`SubmitUpdate` ở M3+.

### Acceptance criteria

- [x] Proto schema compile thành công, `federated_pb2{,_grpc}.py` import được
- [x] Server bind LAN interface, client connect qua LAN IP
- [x] RPC round-trip thành công, response đúng schema
- [x] Đo được RTT thật, network boundary tồn tại

### Vấn đề gặp phải

- **Windows Firewall**: Lần đầu server bind `0.0.0.0:50051` Windows có thể prompt "Allow access". Nếu Máy 2 không kết nối được, mở PowerShell Admin trên Máy 1:
  ```powershell
  New-NetFirewallRule -DisplayName "FedML gRPC 50051" -Direction Inbound -Protocol TCP -LocalPort 50051 -Action Allow
  ```
  Trong thực tế, sau khi user click Allow trên prompt thì test hoạt động ngay.
- **Phân biệt LAN IP vs vEthernet**: Máy 1 có 4 IPv4 (`192.168.2.30`, `172.27.64.1`, `192.168.144.1`, `169.254.83.107`). Chỉ `192.168.2.30` là LAN thật — các IP còn lại thuộc WSL/Hyper-V vEthernet, không reach được từ máy khác.
- **Output buffering của background server** trên PowerShell: cần set `$env:PYTHONUNBUFFERED=1` để in log realtime ra file output.

---

## Git workflow đang dùng

- `main`: trạng thái stable (chỉ docs đến hiện tại) — commit `c2d85bd`
- `dev`: nhánh phát triển — commit hiện tại `b2bd2fe`
- Phát triển trên `dev` qua nhiều commit, khi milestone ổn sẽ merge vào `main`

Đến cuối M2:
```
b2bd2fe (HEAD -> dev, origin/dev)  M2 verified: cross-machine RTT 3.5-6ms over LAN
ada1e41                            M2: gRPC hello world — server + client skeleton
49734cb                            M1: centralized baseline + project skeleton
c2d85bd (origin/main, main)        Initial commit: project spec and implementation plan
```

---

## Bước tiếp theo (M3)

Implement 1 round federated end-to-end:

1. Server state machine (`WAITING → TRAINING → AGGREGATING → EVALUATING → DONE`)
2. `GetGlobalModel`: trả state_dict hiện tại, validate `round_id`
3. `SubmitUpdate`: nhận weights, validate `round_id`/`client_id`, lưu vào buffer
4. FedAvg aggregate khi đủ `MIN_CLIENTS`
5. Server evaluate trên test set (CPU, không tranh GPU với Client 1)
6. Client training loop: poll status → pull model → train local 1-2 epoch → submit update
7. `round_log.csv` per-round: accuracy, loss, timing breakdown (download/train/upload/wait)

Sau M3, 80% logic federated đã có; M4-M7 chỉ thêm tính năng (multi-round, Non-IID, timeout/stale, fault tolerance).
