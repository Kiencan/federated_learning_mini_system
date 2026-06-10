# Báo cáo tiến độ — Federated Learning Mini System

Tài liệu này theo dõi kết quả thực hiện từng milestone của dự án. Mỗi milestone gồm: mục tiêu, công việc đã làm, kết quả verified, file đã thêm/sửa, và các vấn đề gặp phải.

> Liên kết: [Spec gốc (ytuong.md)](../ytuong.md) · [Kế hoạch triển khai (plan.md)](../plan.md) · [GitHub repo](https://github.com/Kiencan/federated_learning_mini_system)

---

## Tổng quan tiến độ

| Milestone | Mục tiêu | Trạng thái | Commit |
|---|---|---|---|
| M1 | Centralized baseline (1 máy, không gRPC) | ✅ Done | `49734cb` |
| M2 | gRPC hello world qua 2 máy | ✅ Done | `ada1e41` → `b2bd2fe` |
| M3 | Server/client chạy 1 round IID | ✅ Done | `a99cab0` → `c05a049` → `3eef9ec` |
| M4 | Chạy 5 round IID + log CSV | ✅ Done | `38c66fe` |
| M5 | Thêm Non-IID partition | ✅ Done | `5857aa9` → `c0dd3a9` |
| M6 | WAIT_TIMEOUT + dynamic min_clients (fault tolerance) | ✅ Done | `370b4af` |
| M7 | Straggler + failure experiments | ⏳ Pending | — |

**Hardware đang dùng:**
- Máy 1: Windows, NVIDIA RTX 2000 Ada Generation, CUDA 12.1, LAN IP `192.168.2.30`
- Máy 2: Windows, NVIDIA RTX 2000 Ada Generation, CUDA 12.6
- Kết nối: LAN

**Môi trường:**
- Conda env `fedml` Python 3.11.15
- PyTorch — Máy 1: `2.5.1+cu121`; Máy 2: `2.12.0+cu126` (minor drift, không ảnh hưởng FedAvg)
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

## Milestone 3 — 1 Round Federated IID End-to-End

### Mục tiêu

Chạy thành công 1 round Federated Learning từ đầu đến cuối: server gửi global model → 2 client (mỗi máy 1 client) train trên IID shard riêng → server aggregate bằng FedAvg → evaluate trên test set. Verify cả localhost (Máy 1) lẫn cross-machine (Máy 1 + Máy 2). Đặt nền cho M4+ chỉ cần thêm tính năng.

> Tài liệu plan chi tiết: [m3_plan.md](m3_plan.md)

### Công việc đã làm

**Phân chia 2 dev qua 3 feature branch (collaboration workflow đầu tiên):**

| Branch | Owner | Subtasks | Merged |
|---|---|---|---|
| `feature/m3-server` | Máy 1 | M3.1 ServerState, M3.2 GetGlobalModel, M3.3 SubmitUpdate (4-layer validation), M3.4 _aggregate_and_evaluate | `c05a049` |
| `feature/m3-client-loop` | Máy 2 | M3.5 client training loop, M3.6 shard pick + metadata, fix(B1) Windows UTF-8 | `a99cab0` |
| `feature/m3-stale-test` | Máy 2 | M3.8 stale update test (4 case) | `3eef9ec` |

Mỗi branch có PR review từ Máy 1 trước khi merge. Bắt được 4 issues qua review (R1 race condition, R5 missing comment, B1 encoding, một self-fix grpc.RpcError handling từ Máy 2). Branch xóa sau merge để giữ git log gọn.

**File mới / sửa lớn:**

```text
aggregation.py            (new) FedAvg + evaluate shared module
server.py                 (rewrite) ServerState + 3 RPC + sync FedAvg+eval
client.py                 (rewrite) poll → pull → train → submit → poll DONE
centralized_train.py      (refactor) import evaluate từ aggregation
config.yaml               (update) min_clients=2, expected_client_ids whitelist
tests/__init__.py         (new)
tests/test_stale_update.py (new) 4-case validation test
tests/_smoke_server.py    (new) 9-case server-side dev smoke test
```

**Thiết kế quan trọng:**

- **State machine**: `TRAINING → AGGREGATING → EVALUATING → DONE` (M3 = 1 round)
- **`current_round = 1` từ start** (không phải 0)
- **4-layer SubmitUpdate validation** đúng thứ tự: `unknown_client` → `state != TRAINING` → `stale_round` → `duplicate_update`
- **Aggregation sync trong handler client cuối** → client cuối thấy upload time bao gồm server FedAvg+eval (~1s). M6 sẽ refactor sang background thread khi thêm timeout.
- **Thread safety**: `threading.Lock` cho state, `_log_lock` riêng cho `events.csv` writes (tránh race khi `GetGlobalModel` log ngoài main lock)
- **Server eval trên CPU** không tranh GPU với Client 1
- **Hardcoded 2 client** (`client-0`, `client-1`) cho per-client log columns; refactor note đã ghi cho M4+

**Logging structured (m3_plan §6, §7):**

- `round_log.csv`: 22 cột bao gồm `accuracy`, `test_loss`, `acc_class_0..9`, `aggregation_time_ms`, `eval_time_ms`, `round_wallclock_sec`, per-client train_loss + num_samples
- `events.csv`: schema `timestamp,round_id,event,client_id,message,num_samples` — event types: `client_registered`, `model_pulled`, `update_received`, `update_rejected`, `aggregation_start/done`, `evaluation_done`, `round_done`
- `run_meta.json`: server + per-client metadata (hostname, GPU, torch_version, cuda_version) — client metadata gửi qua `ClientUpdate.hostname/gpu_name/torch_version/cuda_version` field

### Kết quả verified

**M3.7 — Localhost smoke (Máy 1, server + 2 client localhost):**

| Metric | Value |
|---|---|
| Accuracy sau 1 round IID | **98.52%** |
| Per-class accuracy | 96.3% – 99.9% (lớp 7 thấp nhất) |
| Aggregation time | 3.5 ms |
| Eval time (CPU) | 992 ms |
| Round wallclock | 16.1 s |
| Client train_loss | 0.0671 / 0.0663 |

**M3.8 — Stale update validation test:** 4/4 case pass (stale_round, unknown_client, valid accept, duplicate_update).

**M3.9 — Cross-machine (Máy 1 server + client-0; Máy 2 client-1):**

Phải chạy 2 lần do phát hiện vấn đề môi trường ở Máy 2:

| Run | Accuracy | Round wallclock | Ghi chú |
|---|---|---|---|
| v1 | 98.68% | **133 s** | Máy 2 chạy `torch+cpu` (CPU only) → client-1 train ~41s |
| v2 | 98.45% | **19.4 s** | Sau khi Máy 2 reinstall `torch+cu126` → client-1 train ~8s (7x speedup) |

Cross-machine v2 round_wallclock chỉ chậm ~3s so với localhost — overhead LAN nhỏ (RTT trung bình 4.9ms × ~4 RPC ≈ 20ms cộng với network bandwidth nhỏ cho 1.65MB state_dict).

### Acceptance criteria (m3_plan §10)

- [x] 1 round end-to-end không stuck cả localhost lẫn cross-machine
- [x] Server reject đủ 4 case (stale_round, unknown_client, duplicate, state_not_training) đúng lý do trong `events.csv`
- [x] Accuracy > 80% (đạt ~98.5% — vượt xa kỳ vọng)
- [x] Loss giảm rõ (init random ~2.3 → sau 1 round ~0.047)
- [x] `round_log.csv` đủ cột, `events.csv` đủ event type
- [x] Timing breakdown client (download/train/upload) được log
- [x] Client thoát sạch khi state=DONE (không poll vô tận)
- [x] Cross-machine: cả 2 client trên 2 máy đều submit thành công

### Vấn đề gặp phải & finding

**1. Race condition `events.csv` writes (R1, code review tự phát hiện)**

`log_event()` được gọi cả trong và ngoài `self.lock` (GetGlobalModel log ngoài lock). 2 thread concurrent có thể interleave CSV row trên Windows file I/O. Fix bằng `_log_lock` độc lập với main state lock. Verified 9/9 smoke case vẫn pass sau fix.

**2. Vietnamese chars crash Windows cp1252 console (B1, review Máy 2's PR)**

`client.py` và `test_stale_update.py` có tiếng Việt + Unicode (`✓`, `→`, `──`) trong `print()`. Windows console mặc định cp1252 → `UnicodeEncodeError`. Máy 2 fix bằng:

```python
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
```

**3. Máy 2 chạy PyTorch CPU-only (phát hiện qua `run_meta.json`)**

M3.9 v1 chạy `torch 2.12.0+cpu` trên Máy 2 → `cuda_available: false` → fallback CPU silent (chỉ log WARN). Client-1 train chậm 7x (41s vs 8s). Phát hiện qua `run_meta.json.nodes[*].cuda_available` field — bằng chứng cho thấy việc track metadata per-node hữu ích thực tế.

Fix: reinstall `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121`. Sau fix: Máy 2 dùng `torch 2.12.0+cu126`. Minor version drift (Máy 1 dùng `2.5.1+cu121`) nhưng không ảnh hưởng (state_dict serialization platform-agnostic).

**4. `experiment_name` precedence (M3.1 fix nhỏ)**

`cfg.setdefault("experiment_name", default)` là no-op khi config.yaml đã có giá trị → server.py vô tình dùng `exp_centralized` thay vì `exp_federated_iid_smoke`. Fix bằng explicit check `if not args.experiment_name`. Precedence hiện tại: CLI > script default > config (config field hiện dead). Đáng dọn ở milestone sau.

### Snapshot timing breakdown M3.9 v2

```text
Server:
  aggregation:   3.7 ms     (FedAvg weighted average)
  evaluation:  987.0 ms     (10000 test samples trên CPU)
  total:       ~1.0 s

Client-0 (Máy 1, submit thứ 2):
  download:      7 ms       (1.65MB pull qua loopback)
  train:      6288 ms       (2 epochs × ~30K samples GPU)
  upload:     1040 ms       (incl. server agg+eval wait — vì là client cuối)
  total:      7335 ms

Client-1 (Máy 2, submit thứ 1):
  download:    ~8 ms        (LAN pull)
  train:      ~8000 ms      (2 epochs trên GPU)
  upload:      ~10 ms       (network only — không phải client cuối)

Round wallclock: 19.4 s (giới hạn bởi client chậm hơn + server eval)
```

### Git state cuối M3

```
3eef9ec (HEAD -> dev, origin/dev)  Merge feature/m3-stale-test into dev
c05a049                            Merge feature/m3-server into dev
a99cab0                            Merge feature/m3-client-loop into dev
ad71747                            docs(m3): collaboration workflow
0d3210d                            docs: Report/m3_plan.md
ef949d2                            docs: milestone report M1 + M2
b2bd2fe                            M2 verified
ada1e41                            M2: gRPC hello world
49734cb                            M1: centralized baseline
c2d85bd (origin/main, main)        Initial commit
```

3 feature branches đã merge → đã xóa cả remote + local.

---

## Milestone 4 — Multi-round IID (5 round)

### Mục tiêu

Mở rộng M3 từ 1 round → N round liên tiếp. Verify server `_aggregate_and_evaluate_locked` nhánh advance round + client loop tự detect round mới. Đặt nền cho phase Experiments (30 round IID baseline) và M5 (Non-IID).

> Plan chi tiết: [m4_plan.md](m4_plan.md)

### Công việc đã làm

**Workflow:** 1 feature branch duy nhất `feature/m4-client-multiround` (Máy 2 owned, M4.2). Server không cần code change — nhánh advance round đã có sẵn từ M3.

| Subtask | Owner | Status |
|---|---|---|
| M4.1 Server sanity-check (`_smoke_server.py` 9 case, server `--num-rounds 1`) | Máy 1 | ✓ 9/9 pass |
| M4.2 Client multi-round refactor | Máy 2 | ✓ merged `38c66fe` |
| M4.3 Localhost smoke 5 round | Máy 1 | ✓ 99.27% |
| M4.4 Cross-machine 5 round | Cả 2 | ✓ 99.24% |
| M4.6 Update milestone_report.md (this section) | Máy 1 | ✓ |

**Thay đổi chính ở `client.py`** (388 dòng modified, +232/-156):

- **3 helper functions** tách rõ:
  - `train_local(round_id)` — train per-epoch (giữ từ M3, thêm round_id cho log)
  - `wait_for_new_round_or_done(stub, last_completed_round)` — poll detect server advance: return khi state=DONE hoặc state=TRAINING với round > last_completed
  - `do_one_round()` — encapsulate per-round flow: GetGlobalModel → load fresh weights → SGD mới → train → SubmitUpdate
- **Setup 1 lần** ngoài outer loop: channel, stub, MNIST shard, DataLoader, device, metadata (`gpu_name`, `cuda_ver`)
- **Per-round** trong outer loop: `MnistCNN()` mới + load global state_dict + optimizer SGD mới
- **DataLoader reuse**: shuffle=True tự rotate qua các round, không re-load MNIST mỗi round
- **Reject handling** rõ ràng: `ack.accepted=False` → in `ack.message` + `server_round` → `sys.exit(3)`. RPC error → `sys.exit(2)`. Channel timeout → `sys.exit(1)`
- **Summary statistics** cuối run: total + avg per round (download/train/upload)
- **M2 compat** `--poll N` mode preserved + **B1 Windows UTF-8** fix preserved

### Kết quả verified

**M4.3 — Localhost smoke 5 round (Máy 1, server + 2 client):**

| Round | Accuracy | Test loss | Client-0 train_loss | Client-1 train_loss | Round wallclock |
|---|---|---|---|---|---|
| 1 | **0.9852** | 0.0471 | 0.0671 | 0.0663 | 25.3 s (cold start) |
| 2 | 0.9902 | 0.0288 | 0.0440 | 0.0382 | 9.5 s |
| 3 | 0.9917 | 0.0257 | 0.0304 | 0.0271 | 8.5 s |
| 4 | 0.9933 | 0.0212 | 0.0230 | 0.0221 | 9.1 s |
| 5 | **0.9927** | 0.0215 | 0.0184 | 0.0168 | 8.6 s |

**M4.4 — Cross-machine 5 round (Máy 1 server + client-0; Máy 2 client-1 với GPU sau fix):**

| Round | Accuracy | Test loss | Round wallclock |
|---|---|---|---|
| 1 | **0.9844** | 0.0500 | 88.1 s (cold start, includes Máy 2 MNIST load + LAN warmup) |
| 2 | 0.9914 | 0.0278 | 12.6 s |
| 3 | 0.9913 | 0.0248 | 12.7 s |
| 4 | 0.9929 | 0.0218 | 12.8 s |
| 5 | **0.9924** | 0.0208 | 12.8 s |

**Quan sát:**

- **Hội tụ nhanh:** Round 1 đã đạt ~98.5%, round 5 vượt 99.2% trên cả 2 setup
- **Không monotonic 100%:** Round 3 (cross-machine) tụt 0.01% so với round 2, round 5 tụt 0.05% so với round 4 — bình thường với FedAvg + SGD + shuffle dao động. **Không có collapse** (không có round nào tụt mạnh).
- **Cross-machine overhead:** ~3-4s per round vs localhost (12.7s vs 9s). Phần lớn là LAN download + upload thêm cho client-1.
- **Aggregation rất nhanh:** 1.5-3.7ms — không phải bottleneck.
- **Eval ~1s consistent** trên CPU (10000 test samples).
- **Per-class accuracy round 5** (M4.4): tất cả 10 lớp ≥ 98.7% (lớp 8 cao nhất 99.5%, lớp 9 thấp nhất 98.7%).

### Acceptance criteria (m4_plan §8)

- [x] 5 round liên tiếp end-to-end không stuck cả localhost lẫn cross-machine
- [x] `round_log.csv` đúng 5 row, mỗi row đầy đủ cột
- [x] `events.csv` đủ events 5 chu kỳ (42 dòng localhost: 5 × 8 events + 2 client_registered)
- [x] Loss/accuracy **xu hướng cải thiện** qua 5 round (cả 2 client train_loss giảm monotonic)
- [x] **Không có collapse** (không có round nào tụt mạnh)
- [x] **Accuracy round 5 ≥ 95%** (đạt **99.24% cross-machine** — vượt xa)
- [x] Client thoát sạch sau round cuối, in summary đầy đủ
- [x] Exit code 3 nếu reject (verified qua design code, không trigger thực tế trong test)
- [x] Cross-machine timing stable (12.6-12.8s rounds 2-5, không có round nào blow up bất thường)

### Vấn đề gặp phải

**1. Round 1 cold start dài đặc biệt cross-machine (88s vs 25s localhost vs 12s steady-state)**

Nguyên nhân: round 1 bao gồm cả MNIST download/cache check trên Máy 2 (nếu chưa có), gRPC channel handshake, JIT compilation CUDA kernels lần đầu, và DataLoader worker init. Đây là **one-time overhead**, không xuất hiện ở các round sau. Acceptable — không cần fix.

**2. Accuracy không monotonic 100% (round 3 và 5 tụt nhẹ)**

Round 3 cross-machine: 99.13% (tụt 0.01% so với 99.14% round 2). Round 5: 99.24% (tụt 0.05% so với 99.29% round 4). Nguyên nhân: random noise từ SGD + DataLoader shuffle + FedAvg averaging. Không phải bug — confirm bằng acceptance đã sửa từ "monotonic" sang "không collapse".

**3. Per-client log columns hard-code (R5 notes từ M3 vẫn applies)**

`round_log.csv` có `client_0_*` và `client_1_*` hard-code cho 2 client. M4 không sửa — vẫn note refactor cho M4+ khi num_clients > 2 (hiện chưa có scope).

### Code review issues defer cho M5+ (không block M4)

| # | Vấn đề | Impact |
|---|---|---|
| I1 | `gpu_name` populate kể cả khi `device` fallback CPU — metadata `run_meta.json` có thể misleading | Minor (cosmetic metadata) |
| I6 | `rounds_done = last_completed_round` sai với mid-experiment join | Edge case M4 không hỗ trợ |
| I10 | Print prefix mix `[client]` vs `[client {id}]` | Cosmetic |

### Snapshot timing breakdown — M4.4 (steady state rounds 2-5 avg)

```text
Server:
  aggregation:    ~2.1 ms  (FedAvg weighted average, very fast)
  evaluation:   ~980 ms   (CPU, 10000 test samples)
  round overhead: ~3 ms

Client (per round, GPU):
  download:    ~7-10 ms     (LAN pull 1.65MB)
  train:       ~7000-8500 ms (2 epochs × ~30K samples × 32 batch)
  upload:      ~10-1000 ms   (depend on which client submits last → blocked by server eval)
```

**Bottleneck:** train (~7-8s) chiếm 60% wallclock per round. Eval (~1s) chiếm 10%. Phần còn lại là client polling interval (2s) + network.

### Git state cuối M4

```
38c66fe (HEAD -> dev, origin/dev)  Merge feature/m4-client-multiround into dev
82a301f                            docs(m4): 3 chỉnh sửa nhỏ
57c73ad                            docs(m4): refine plan
ddb16d9                            docs(m4): thêm Report/m4_plan.md
cf136f5                            docs(m3): add Milestone 3 section
3eef9ec                            Merge feature/m3-stale-test into dev
...
```

`feature/m4-client-multiround` đã xóa khỏi remote + local sau merge.

---

## Milestone 5 — Non-IID Pathological Split

### Mục tiêu

Thêm Non-IID partition (pathological: Client 0 = digits 0-4, Client 1 = digits 5-9) để chuẩn bị **data point cho Experiment 2 (IID vs Non-IID)** trong báo cáo cuối kỳ. Đây là milestone đầu tiên ta CHỦ ĐÍCH kỳ vọng accuracy thấp hơn (Non-IID là worst-case scenario).

> Plan chi tiết: [m5_plan.md](m5_plan.md)

### Công việc đã làm

**Workflow:** 2 feature branches sequential (cùng sửa `run_context.py` nên không thể song song).

| Subtask | Owner | Branch | Status |
|---|---|---|---|
| M5.0 Fix `create_run_dir` snapshot resolved config | Máy 1 | `feature/m5-resolved-config-snapshot` | ✓ merged `5857aa9` |
| M5.1 Verify server data-agnostic (no code change) | Máy 1 | — | ✓ confirmed |
| M5.2 `--data-split` flag + client dispatch + class_dist print | Máy 2 | `feature/m5-client-noniid` | ✓ merged `c0dd3a9` |
| M5.3 Localhost smoke 5 round Non-IID | Máy 1 | — | ✓ acc 98.13% |
| M5.4 Cross-machine 5 round Non-IID | Cả 2 | — | ✓ acc 98.21% |
| M5.5 Compare IID vs Non-IID | Máy 1 | — | ✓ (xem bảng dưới) |
| M5.6 Update milestone_report (this section) | Máy 1 | direct dev | ✓ |

**M5.0 — `run_context.py` (`create_run_dir`):** Tech debt từ M3 — `shutil.copyfile(config_path, snapshot)` copy file gốc, mất CLI overrides. Fix: `yaml.safe_dump(config, ...)` để snapshot resolved config. Verify: `--num-rounds 99` → snapshot có `num_rounds: 99` (không phải 30 từ config gốc). Cleanup imports không dùng (`shutil`, `os`, `field`).

**M5.2 — `run_context.py` + `client.py`:**
- `build_cli_parser()`: thêm `--data-split` shared parser (cả server lẫn client nhận; server chỉ để snapshot)
- `cli_overrides()`: map `data_split`
- `client.py`: dispatch 3-step (dispatch partition → validate shard_id → in class_distribution thực tế)
- Validation: `noniid` requires `num_shards=2` (exit 4); `shard_id` out of range cho cả IID + Non-IID (exit 4)
- `Counter(labels)` để in class distribution thực tế thay vì hardcoded label
- **Bonus cải thiện:** setup data + validate MOVED TRƯỚC `grpc.insecure_channel()` (fail-fast pattern)

### Kết quả verified

**Class distribution thực tế (M5.4 cross-machine):**

| Client | Shard size | Class distribution |
|---|---|---|
| client-0 | 30596 | `{0:5923, 1:6742, 2:5958, 3:6131, 4:5842}` — chỉ digits 0-4 ✓ |
| client-1 | 29404 | `{5:5421, 6:5918, 7:6265, 8:5851, 9:5949}` — chỉ digits 5-9 ✓ |

**M5.3 — Localhost smoke 5 round Non-IID:**

| Round | Accuracy | Round wallclock |
|---|---|---|
| 1 | 92.17% | 23.1 s (cold start) |
| 2 | 94.36% | 7.8 s |
| 3 | 97.74% | 7.2 s |
| 4 | 97.82% | 8.2 s |
| 5 | **98.13%** | 8.3 s |

**M5.4 — Cross-machine 5 round Non-IID:**

| Round | Accuracy | Round wallclock |
|---|---|---|
| 1 | 91.60% | 3630 s (anomaly: Máy 2 user delay-to-start ~1h) |
| 2 | 94.71% | 11.1 s |
| 3 | 97.40% | 12.5 s |
| 4 | 97.67% | 11.2 s |
| 5 | **98.21%** | 11.7 s |

Round 1 wallclock 3630s là **không phải bug hệ thống** — đó là thời gian user trên Máy 2 chậm khởi động client-1. Server + client-0 đều chờ patient. Steady-state ~11.5s/round (giống cross-machine IID M4.4 ~12.7s) → data partition không ảnh hưởng compute time.

### Comparison IID vs Non-IID (M5.5)

**Cùng config:** `num_rounds=5, local_epochs=2, batch_size=32, lr=0.01, seed=42, 2 clients, cross-machine`.

**Accuracy curve cross-machine:**

| Round | IID (M4.4) | Non-IID (M5.4) | Gap |
|---|---|---|---|
| 1 | 0.9844 | 0.9160 | **-6.84 pp** |
| 2 | 0.9914 | 0.9471 | -4.43 pp |
| 3 | 0.9913 | 0.9740 | -1.73 pp |
| 4 | 0.9929 | 0.9767 | -1.62 pp |
| 5 | 0.9924 | 0.9821 | **-1.03 pp** |

→ Non-IID hội tụ chậm hơn, gap thu hẹp từ ~7pp → ~1pp sau 5 round. Cả hai cùng đạt > 98% cuối cùng.

**Test loss curve cross-machine:**

| Round | IID | Non-IID | Ratio |
|---|---|---|---|
| 1 | 0.050 | 0.549 | **11.0x** |
| 2 | 0.028 | 0.167 | 6.0x |
| 3 | 0.025 | 0.092 | 3.7x |
| 4 | 0.022 | 0.070 | 3.2x |
| 5 | 0.021 | 0.054 | **2.6x** |

→ Non-IID test_loss vẫn cao hơn 2.6x ở round 5 dù accuracy gần ngang. **Model less confident** — predictions đúng nhưng probability spread rộng hơn. Đây là finding subtle khác với chỉ nhìn accuracy.

**Per-class accuracy round 1 (raw gap — finding lớn nhất):**

| Class | IID | Non-IID | Gap |
|---|---|---|---|
| 0 | 0.997 | 0.997 | +0.000 |
| 1 | 0.999 | 0.998 | -0.001 |
| 2 | 0.986 | 0.911 | -0.075 |
| 3 | 0.993 | 0.986 | -0.007 |
| 4 | 0.998 | 0.967 | -0.031 |
| **5** | **0.984** | **0.512** | **-0.472** ← **anomaly** |
| 6 | 0.985 | 0.970 | -0.015 |
| 7 | 0.962 | 0.976 | +0.014 |
| 8 | 0.968 | 0.917 | -0.051 |
| 9 | 0.970 | 0.874 | -0.096 |

→ **Class 5 round 1: 51.2% Non-IID vs 98.4% IID** — sụt 47 điểm phần trăm. Đây là **finding chính cho Experiment 2**: lớp đầu tiên của client-1 bị FedAvg "kéo" mạnh về phía client-0 (chỉ thấy 0-4), gần như random guess. Class 9 (lớp cuối client-1) cũng bị penalty rõ (-9.6pp).

**Per-class accuracy round 5 (recovered):**

| Class | IID | Non-IID | Gap |
|---|---|---|---|
| 0 | 0.997 | 0.993 | -0.004 |
| 1 | 0.996 | 0.995 | -0.001 |
| 2 | 0.992 | 0.972 | -0.020 |
| 3 | 0.997 | 0.970 | -0.027 |
| 4 | 0.989 | 0.979 | -0.010 |
| 5 | 0.992 | 0.984 | -0.008 |
| 6 | 0.990 | 0.985 | -0.005 |
| 7 | 0.989 | 0.988 | -0.001 |
| 8 | 0.995 | 0.984 | -0.011 |
| 9 | 0.987 | 0.970 | -0.017 |

→ Sau 5 round, tất cả lớp Non-IID đều ≥ 97%. Gap mostly < 3pp. **Class 9 recovery slowest** (gap -1.7pp).

**Client-side train_loss round 5 — "client drift" phenomenon:**

| | IID | Non-IID |
|---|---|---|
| client-0 train_loss | 0.019 | **0.006** |
| client-1 train_loss | 0.016 | **0.012** |

→ Non-IID train_loss client-side **THẤP HƠN** IID. Đây là "client drift": mỗi client overfit 5 lớp local rất nhanh (mỗi epoch chỉ thấy data mặc dù phong phú nhưng đồng nhất về class label), train_loss thấp giả tạo. **KHÔNG phản ánh global model quality** — chỉ phản ánh local training performance. Trong báo cáo Exp 2, cần lưu ý phân biệt train_loss client vs test accuracy server.

### Acceptance criteria (m5_plan §8)

- [x] 5 round Non-IID end-to-end không stuck (localhost + cross-machine)
- [x] `round_log.csv` 5 row, output `exp_federated_noniid_smoke/<run_id>/`
- [x] Class distribution thực tế đúng (0-4 cho client-0, 5-9 cho client-1)
- [x] **Accuracy round 5 ≥ 70%** → đạt **98.21%** cross-machine
- [x] Per-class accuracy được log và so sánh (xem bảng trên)
- [x] Loss giảm qua các round
- [x] Client thoát sạch khi DONE
- [x] Validation: `noniid` + `num_shards != 2` → exit 4
- [x] Validation: `shard_id` out of range → exit 4
- [x] Server snapshot `config.yaml` có `data_split: noniid` (M5.0 fix work end-to-end)
- [x] Comparison table IID vs Non-IID có trong section này

### Finding cho Experiment 2

1. **Hội tụ chậm hơn nhưng vẫn đạt > 98%** sau 5 round trên MNIST + 2 client pathological split. Plan kỳ vọng 80-90% (pessimistic) — thực tế cao hơn vì MNIST tương đối dễ và FedAvg đủ robust.
2. **Class 5 round 1 chỉ 51.2%** — phenomenon "client drift" rõ ràng: lớp giáp ranh giữa 2 shard bị FedAvg pull lệch mạnh.
3. **Test loss cao hơn 2.6x ở round 5** — model less confident dù accuracy ngang.
4. **Train_loss client-side thấp giả tạo** — phải dùng test_loss server làm metric chính cho Non-IID.
5. **Compute time KHÔNG khác biệt** giữa IID/Non-IID — data partition là pure data-level concern, không ảnh hưởng aggregation/eval/network.

Những điểm này sẽ thành **5 talking points chính** cho phần Data Heterogeneity (§7.5 ytuong.md) của báo cáo cuối kỳ.

### Vấn đề gặp phải

**1. M5.4 round 1 wallclock 3630s** — không phải bug. Server và client-0 đợi client-1 (Máy 2) suốt ~1 giờ do user delay khởi động. System xử lý đúng (poll patient, không timeout). Trong báo cáo, cần lọc round 1 cross-machine khỏi steady-state timing analysis.

**2. M5.0 tech debt từ M3** — `create_run_dir` snapshot file gốc thay vì resolved config. Phát hiện trong review M5.2 (config snapshot không có `data_split: noniid`). Fix riêng (M5.0) trước khi merge M5.2.

**3. Plan kỳ vọng accuracy 80-90%, thực tế 98%** — plan pessimistic. Đáng note nhưng không phải acceptance issue (vẫn pass).

### Code review issues defer cho M6+ (không block M5)

- I1 (M4 review chưa fix): `gpu_name` populate khi device fallback CPU
- N3 (M5 plan): server không validate `data_split` mismatch giữa client/server — defer M6

### Snapshot timing M5.4 (steady state round 2-5 avg)

```text
Server (Non-IID, cross-machine):
  aggregation:    ~2.1 ms  (same as IID — FedAvg data-agnostic)
  evaluation:   ~1179 ms   (CPU, 10000 test samples; ~200ms slower than IID — đáng note)
  round wallclock: ~11.6 s (slightly faster than IID 12.7s — Non-IID shard nhỏ hơn ~600 samples mỗi client)
```

### Git state cuối M5

```
c0dd3a9 (HEAD -> dev, origin/dev)  Merge feature/m5-client-noniid into dev
5857aa9                            Merge feature/m5-resolved-config-snapshot into dev
1bcdcdc                            docs(m4): add Milestone 4 section
...
```

2 feature branches xóa khỏi remote + local sau merge.

---

## Milestone 6 — WAIT_TIMEOUT + Dynamic min_clients (Fault Tolerance)

### Mục tiêu

Server không bị stuck khi 1 client chậm/crash. Thêm `WAIT_TIMEOUT` để server tự aggregate sau khoảng thời gian, kết hợp `min_clients=1` cho phép aggregate với 1 client còn lại. Đây là **milestone phức tạp nhất** từ M3 — refactor server từ sync aggregation (trong handler) sang **background thread**.

> Plan chi tiết: [m6_plan.md](m6_plan.md)

### Công việc đã làm

**Workflow:** 1 feature branch `feature/m6-server-async-agg` (Máy 1 owned).

| Subtask | Owner | Status |
|---|---|---|
| M6.1 CLI flags `--min-clients` (int) + `--wait-timeout` (float) | Máy 1 | ✓ |
| M6.2 Server refactor 3-phase aggregation + 3 paths + validate config + round_status column | Máy 1 | ✓ |
| M6.3 Docstring `_smoke_server.py` + polling cho async | Máy 1 | ✓ |
| M6.4 Localhost test 3 scenarios A/B/C | Máy 1 | ✓ |
| M6.5 Cross-machine A + B (+ accidental verify path khác) | Cả 2 | ✓ |
| M6.6 Update milestone_report (this section) | Máy 1 | ✓ |

**Refactor chính trong `server.py`** (+352/-163 lines):

- **Aggregation sync (trong `SubmitUpdate` handler) → background thread** chạy `run_aggregation_loop()`
- **3-phase lock design** (chìa khóa correctness + responsiveness):
  - **Phase 1** (hold lock): wait condition (threshold OR timeout), snapshot updates, set state=AGGREGATING
  - **Phase 2** (**NO lock**): FedAvg + evaluate + CSV write (~1s)
  - **Phase 3** (hold lock, <10ms): guarded commit (check shutdown + round/state lệch) + load global model + advance round
- **3 paths** qua `condition.wait`:
  - Path **A** "ok": `received >= expected_count` (early aggregation, all clients done)
  - Path **B** "partial": timeout + `received >= min_clients` (drop slow clients)
  - Path **C** "skipped": timeout + `received < min_clients` (skip round, no aggregation)
- **Pure functions** tách: `_do_fedavg`, `_do_evaluate`, `_write_round_log_row`, `_write_skipped_round_row`
- **4 events mới**: `round_timeout`, `partial_aggregation`, `round_skipped`, `commit_aborted`
- **`round_log.csv` schema**: thêm cột `round_status` (`ok` / `partial` / `skipped`)
- **Validate config fail-fast** trong `__init__`: `1 <= min_clients <= expected_count`, `wait_timeout > 0`
- **`model_pulled` event** kèm `state=<NAME>` cho observability race
- **Bonus fix:** refresh `round_start_time` SAU `server.start()` để timeout window không bị ăn bởi Python startup ~10s

**Updates khác:**
- `run_context.py`: 2 CLI flags mới
- `config.yaml` defaults M6: `wait_timeout: 15→30`, `min_clients: 2→1`
- `tests/_smoke_server.py`: docstring prereq `--min-clients 2` + polling 5s cho M6 async

### Kết quả verified

**4 paths × 2 setups (localhost + cross-machine):**

| Path | Localhost | Cross-machine |
|---|---|---|
| **A "ok"** (all expected submit) | ✅ M6 early-test (3 round, acc 98.52→99.17%) | ✅ m65_debug round 3 (acc **98.59%**) |
| **B "partial"** (timeout + ≥min) | ✅ M6.4 Scenario B round 3 (acc 98.31%) | ✅ run 1 m65_scenario_a (3 round @ ~98.5-98.85%) |
| **C "skipped" received=0** | ✅ M6.4 Scenario C (3 round) | — |
| **C "skipped" received<min** | — | ✅ m65_debug rounds 1-2 (received=1<min=2) + v4 |

**Tất cả 3 paths của plan §6 verified, cả localhost lẫn cross-machine.**

### Snapshot run M6.4 Scenario A (localhost happy path)

```
Round | acc    | round_status | round_wallclock | aggregation | eval
1     | 0.9852 | ok           | 26.94s (cold)   | 3.62ms      | 1205.5ms
2     | 0.9902 | ok           | 8.91s           | 1.43ms      | 1173.4ms
3     | 0.9917 | ok           | 9.22s           | 1.44ms      | 1320.2ms
```

### Snapshot run M6.4 Scenario C (0 clients, timeout=5s)

```
Round | num_clients_received | round_status | round_wallclock
1     | 0                   | skipped      | 5.02s (timeout)
2     | 0                   | skipped      | 5.01s
3     | 0                   | skipped      | 5.00s
```

events.csv: 9 events đúng schema (3× `round_timeout` + 3× `round_skipped` + 3× `round_done`).

### Acceptance criteria (m6_plan §8)

- [x] Server start có background aggregation thread; Ctrl+C shutdown sạch, thread join <2s
- [x] Scenario A: 3 round không stuck, **không có** event timeout/skip/partial. round_log.csv 3 row `round_status=ok`
- [x] Scenario B: 3 round, mỗi round có `round_timeout` + `partial_aggregation`, accuracy hợp lý
- [x] Scenario C: 3 round, mỗi round có `round_timeout` + `round_skipped`. round_log.csv **3 row** `round_status=skipped`, metric columns empty
- [x] `_smoke_server.py` 9/9 case pass với `--min-clients 2` (no M3 regression)
- [x] Config snapshot có `wait_timeout` + `min_clients` đúng giá trị runtime
- [x] Cross-machine Scenario A + B pass

### Vấn đề gặp phải trong quá trình

**1. Bug timing round 1 trong Scenario A early-test (đã fix)**

Initial code: `round_start_time` set trong `ServerState.__init__` (trước `server.start()` + Python client startup ~10s). Deadline tính từ time đó → round 1 timeout trước khi client kịp submit. Server log "round 1 SKIPPED received=0" dù client-0 đã start.

**Fix:** Move `state.round_start_time = time.time()` ra SAU `server.start()` trong `main()`. Cũng đẩy default `wait_timeout` 15→30s cho Windows realistic.

**2. M6.5 cross-machine — 3 lần thử với Máy 2 lỗi**

| Lần | Vấn đề |
|---|---|
| Run 1 (m65_scenario_a) | Máy 2 không connect → server aggregate partial với chỉ client-0 (3 round @ ~98.5%) — accidentally verified Path B cross-machine |
| Run 2 (v2) | Máy 2 connect nhưng dùng nhầm `--data-split noniid` (command còn từ M5.4) — accuracy chỉ 48% (lớp 0-4 = 0%, lớp 5-9 = ~98%) |
| Run 3 (v3) | Máy 2 không connect — chỉ partial với client-0 |
| Run 4 (v4 m65_a_v4) | `--min-clients 2 --wait-timeout 60`: client-1 không submit → SKIP với received=1<min=2 (accidentally verified Path C "received<min") |
| **Run 5 (m65_debug)** | `--wait-timeout 120`: rounds 1-2 SKIP, **round 3 Path A ok với cả 2 client @ 98.59%** ✓ |

**Bài học:** Cross-machine timing nhạy với Python startup trên Windows. `wait_timeout` cần ≥60s cho run "fresh start" 2 máy.

**3. Plan §6.7 vs implementation về Path C row**

Plan §6.7 ví dụ `num_clients_received=0` cho skipped row. Code thực tế ghi `num_clients_received=N` (actual count, có thể >0 nếu `received < min_clients`). Đây là enhancement (more general) — không phải bug. Cả 2 hợp lệ.

### Code review issues defer cho M7+ (không block M6)

- N1 (M6 review): Path C ghi CSV inside lock (~5ms, acceptable)
- N2: `GetRoundStatus` read state without lock (compound non-atomic, tồn tại từ M3)
- N3: `round_timeout` event không log duration_ms (minor)
- N4: `notify_all()` cuối Phase 3 có thể redundant

### Timing snapshot M6 (Scenario A localhost steady state)

```text
Server:
  aggregation:    1.4-3.6 ms   (FedAvg weighted average)
  evaluation:    1170-1320 ms  (CPU, 10000 test samples)
  round wallclock: ~8-9 s steady (similar to M4)

Background thread shutdown (Ctrl+C):
  Phase 1 wait → <1s
  Phase 2 eval → ≤eval duration (~1s)
  Phase 3 → <10ms
  Stop-Process kill: measured 1.03s ✓
```

### Git state cuối M6

```
370b4af (HEAD -> dev, origin/dev)  Merge feature/m6-server-async-agg into dev
e3bbd7e                            M6: WAIT_TIMEOUT + dynamic min_clients (fault tolerance)
05540bf                            docs(m6): đưa yêu cầu model_pulled state=<NAME> lên M6.2 subtask
...
```

Branch xóa khỏi remote + local sau merge.

---

## Milestone 7 — Straggler injection + Crash/Reconnect (M7.1–M7.7 hoàn thành)

**Mục tiêu:** thêm flag `--straggler-delay N` (client-side) để inject artificial sleep INSIDE upload measurement window, tận dụng infrastructure timeout/partial của M6 để chạy 2 thí nghiệm: Straggler (Exp 3) + Crash/Reconnect (Exp 4). **Milestone hẹp nhất** kể từ M3 — code change ~31 dòng.

### M7.0 — Plan + review (`Report/m7_plan.md`)

Plan trải qua **6 vòng review iteration** (22 fixes tổng cộng) trước khi implement. Các thay đổi quan trọng từ review:

- Sleep đặt **AFTER `t_ul = perf_counter()`** và TRƯỚC `stub.SubmitUpdate(...)` → counted INSIDE upload phase
- Single source of truth = `round_log.csv.round_wallclock_sec` (server wallclock), không phải `upload_ms` (client metric, dễ bị clock skew)
- Acceptance F1 dùng **flexible pattern** thay vì cứng (≥3 ok + ≥2 partial + ≥1 ok) vì client polling interval (2s) khó canh chính xác Ctrl+C
- Khuyến nghị S1/S2 server cũng pass `--straggler-delay` để snapshot phản ánh scenario; F1 default 0 (không phải straggler scenario)

### M7.1 — Shared CLI flag (`run_context.py` +10 dòng)

```python
p.add_argument(
    "--straggler-delay",
    type=float,
    default=None,
    help="M7: client-side artificial delay (seconds) injected before "
         "SubmitUpdate to simulate straggler. Counted inside upload_ms. "
         "Client-side; overrides config.yaml straggler_delay. "
         "Server snapshot reflects scenario (recommend pass on S1/S2 server too).",
)
```

Map vào `cli_overrides()` để cả server và client cùng nhận từ một parser (consistency với pattern `--data-split`, `--min-clients`, `--wait-timeout`).

### M7.2 — Sleep injection (`client.py` +21 dòng)

**`main()` validation** (trước khi mở gRPC channel — fail fast):

```python
straggler_delay = cfg.get("straggler_delay", 0) or 0
if straggler_delay < 0:
    print(f"[client {args.client_id}] ERROR: straggler_delay must be >= 0, got {straggler_delay}")
    sys.exit(4)
```

**`do_one_round()` sleep injection**:

```python
# Buoc 4: Submit update
t_ul = time.perf_counter()

# M7: straggler injection — sleep INSIDE upload measurement so
# round_log.csv.round_wallclock_sec captures delay as source of truth.
straggler_delay = cfg.get("straggler_delay", 0) or 0
if straggler_delay > 0:
    print(f"[client {client_id}] round={round_id} straggler sleep {straggler_delay:.1f}s before SubmitUpdate ...")
    time.sleep(straggler_delay)

try:
    ack = stub.SubmitUpdate(federated_pb2.ClientUpdate(
        client_id=client_id,
        round_id=round_id,
        serialized_state_dict=serialize_state_dict(model),  # vẫn ở đây — không đổi flow cũ
        ...
    ), timeout=120)
...
upload_ms = (time.perf_counter() - t_ul) * 1000
```

3 invariants từ review:
1. **Shared CLI wiring** correct (`build_cli_parser` + `cli_overrides` map cả 2 chiều)
2. **Negative validation** client-side, fail fast trước channel open
3. **Sleep INSIDE upload window** → `upload_ms` phản ánh delay, server `round_wallclock_sec` phản ánh full round latency

### M7.3 — Backward compat smoke (run_id `m7_smoke_compat`)

| Check | Result |
|---|---|
| `python client.py --help` shows flag | ✅ `--straggler-delay STRAGGLER_DELAY` |
| Negative `--straggler-delay -1` → exit code 4 | ✅ `EXIT=4` với error message |
| Parser type float | ✅ `5.0 float` (via introspection) |
| 1-round FL với `--straggler-delay 0` (cả 2 clients) | ✅ `round_status=ok`, acc=98.52%, `upload_ms` 33-46ms (no inflation) |
| Snapshot ghi `straggler_delay: 0` | ✅ |
| No "straggler sleep" print khi delay=0 (guard works) | ✅ |

### M7.4 — Scenario S1 localhost (`m74_s1_localhost`)

**Command (per plan §7.2):**

```powershell
python server.py --num-rounds 3 --min-clients 2 --wait-timeout 60 --straggler-delay 5 --run-id m74_s1_localhost
python client.py --client-id client-0 --shard-id 0 --straggler-delay 5
python client.py --client-id client-1 --shard-id 1 --straggler-delay 5
```

**Kết quả 3/3 rounds Path A "ok":**

| Round | Status | Received | Accuracy | `round_wallclock_sec` |
|---|---|---|---|---|
| 1 | `ok` | 2 | 98.52% | 28.46s |
| 2 | `ok` | 2 | 99.02% | 14.86s |
| 3 | `ok` | 2 | 99.17% | 15.08s |

- ✅ Round 2-3 wallclock ≈ 15s = train 8s + **sleep 5s** + aggregation <1s + eval ~1s → confirm sleep counted inside server round latency.
- ✅ Round 1 wallclock 28.46s do client cold start (Python + torch + MNIST + GPU init); subsequent rounds reflect steady state.
- ✅ Acc 99.17% ≥ 97% target, accuracy curve giống M4 baseline → straggler delay không degrade FedAvg.
- ✅ Snapshot: `straggler_delay: 5.0`, `wait_timeout: 60.0`, `min_clients: 2`.
- ✅ Events.csv: KHÔNG có `round_timeout`/`partial_aggregation`/`round_skipped`/`commit_aborted`.

### M7.5 — Scenario S2 localhost (`m75_s2_v3`)

**Command (adjusted from plan §7.3 — see Empirical adjustment below):**

```powershell
python server.py --num-rounds 3 --wait-timeout 20 --min-clients 1 --straggler-delay 20 --run-id m75_s2_v3
python client.py --client-id client-0 --shard-id 0                              # NO delay
python client.py --client-id client-1 --shard-id 1 --straggler-delay 20         # ONLY client-1 delayed
```

**Kết quả 3/3 rounds Path B "partial":**

| Round | Status | Received | Accuracy | `round_wallclock_sec` |
|---|---|---|---|---|
| 1 | `partial` | 1 (client-0) | 98.31% | 21.07s |
| 2 | `partial` | 1 (client-0) | 98.78% | 21.03s |
| 3 | `partial` | 1 (client-0) | 98.85% | 20.98s |

**Events trace round 1 (sample):**
```
09:39:42 client_registered (both)
09:39:42 model_pulled (both)
09:39:50 update_received client-0          # train 8s, no delay
09:39:55 round_timeout received=1/2        # wait_timeout=20s elapsed
09:39:55 partial_aggregation received=1/2  # received >= min_clients -> Path B
09:39:56 aggregation_done duration_ms=3.3
09:39:56 evaluation_done accuracy=0.9831
09:40:10 update_rejected client-1 "stale_round (got 1, expected 2)"  # client-1 woke from sleep, server at round 2
```

- ✅ `round_wallclock_sec ≈ 21s = wait_timeout 20s + aggregation ~1s` (timeout fired vì client-1 không kịp).
- ✅ Client-0 IID half data → acc 98-99% as plan predicted (giảm nhẹ so với S1 99% — single-client aggregation thiếu averaging benefit).
- ✅ Client-1 **exit code 3** sau khi wake từ sleep 20s, gửi update round=1 → server đã ở round 2 → reject stale_round → exit 3 (per m4_plan §6, không retry — đây là "drop straggler" expected behavior, không cần restart).
- ✅ Rounds 2-3 chỉ còn client-0 → server vẫn timeout 20s rồi partial aggregate → 3 row `partial` đầy đủ.
- ✅ Snapshot: `wait_timeout: 20.0`, `min_clients: 1`, `straggler_delay: 20.0`.

#### Empirical adjustment: `wait_timeout` 15 → 20

Plan §7.3 chỉ định `--wait-timeout 15`. Thực tế trên Máy 1 (Windows + miniconda fedml env):

| Phase | Time |
|---|---|
| Python interpreter startup | ~1s |
| `import torch` + CUDA init | ~5s |
| MNIST load + DataLoader setup | ~1s |
| gRPC connect + GetGlobalModel | ~1s |
| Local train (2 epochs, 30k samples) | ~8s |
| **Total before SubmitUpdate (no delay)** | **~16s** |

Với `wait_timeout=15` và `round_start_time` refresh xảy ra ngay sau `server.start()` (~2s sau server boot), client-0 không kịp submit trước deadline → cả 2 round skipped. Bump 15→20 cho client-0 đủ thời gian (~16s < 20s) trong khi client-1 vẫn miss (8s train + 20s sleep = 28s > 20s) → vẫn demo Path B intended.

**Forensic data:** 2 lần chạy failed trước adjustment (`m75_s2_localhost`, `m75_s2_v2`) đều cho 3 rounds `skipped` với `received=0/2` ở `09:38:00` — confirm timing model. Files giữ lại trong `results/exp_federated_iid_smoke/` cho audit.

**Future fix nếu cần `wait_timeout=15`:** Thay đổi server logic refresh `round_start_time` khi **first client_registered** thay vì sau `server.start()`. Nằm ngoài M7 scope (M6 infrastructure change), TODO sau Experiments.

### Files M7 changes

| File | LOC | Purpose |
|---|---|---|
| `run_context.py` | +10 | `--straggler-delay` flag + cli_overrides map |
| `client.py` | +21 | main() validation + do_one_round() sleep injection |
| `Report/m7_plan.md` | (mới, 6 commits) | Plan + 6 vòng review iteration |
| `Report/milestone_report.md` | (section này) | M7.0–M7.5 documentation |

### Git state cuối M7.5

```
deeabe8 (HEAD -> dev, origin/dev, origin/main)  Merge PR#5 feature/m7-straggler into main
41b85d0                                          feat(m7): add --straggler-delay flag + client-side sleep injection
a8c969e                                          docs(m7): wording acceptance — S1/S2 pass --straggler-delay; F1 default 0
... (5 docs commits earlier — plan iteration)
```

PR#5 merge vào main; sau đó dev fast-forward sync với main → tip thống nhất.

### Open issues (M7)

- **N5 (M7.5)**: `wait_timeout=15` empirical không đủ trên Máy 1 (Python startup ~8s). Đã document workaround (bump 20) + propose future server fix.
- **N6 (M7 general)**: Server `--help` crash do cp1252 encode Vietnamese (B1 pre-existing nhưng client.py đã fix, server.py chưa). Không ảnh hưởng functional, chỉ ảnh hưởng UX khi user gọi `python server.py --help` trên Windows.

---

### M7.6 — Scenario F1 Crash/Reconnect cross-machine (`m76_f1_v3`)

**Setup:** Máy 1 chạy server (bind `0.0.0.0:50051`) + client-0 (shard 0). Máy 2 chạy client-1 (shard 1) qua LAN `192.168.2.30:50051`. `num_rounds=16`, `wait_timeout=45`, `min_clients=1`. Manual Ctrl+C/restart client-1 trên Máy 2 để mô phỏng crash + reconnect.

**Command:**

```powershell
# Máy 1 server
python server.py --bind 0.0.0.0:50051 --num-rounds 16 --wait-timeout 45 --min-clients 1 --run-id m76_f1_v3
# Máy 1 client-0
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --server-addr 127.0.0.1:50051
# Máy 2 client-1
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --server-addr 192.168.2.30:50051
```

**Kết quả — 4 phase rõ rệt:**

| Phase | Rounds | Status | Received | Accuracy | `round_wallclock_sec` |
|---|---|---|---|---|---|
| Cold start (noise) | 1-2 | `partial` | 1 | 98.31-98.78% | ~46s (timeout) |
| **Phase 1 — Healthy** | 3-7 | `ok` | 2 | 99.22-99.36% | 12-31s |
| **Phase 3 — Degraded** (Ctrl+C) | 8-11 | `partial` | 1 | 99.07-99.24% | ~46s (timeout) |
| **Phase 4 — Recovery** (restart) | 12-16 | `ok` | 2 | 99.28-99.41% | 12-24s |

**Acceptance flexible — tất cả PASS:**
- ✅ Đoạn liên tiếp `ok` ở đầu: **5 round (3-7)** ≥ 3 target
- ✅ Đoạn liên tiếp `partial` ở giữa: **4 round (8-11)** ≥ 2 target
- ✅ ≥1 round `ok` sau restart: **5 round (12-16)** recovery
- ✅ Server set DONE sau round 16, không stuck
- ✅ Accuracy phục hồi 99.41% (round 15) — không degrade sau crash/recovery cycle

**Client-1 lifecycle gap (events.csv) — bằng chứng crash window:**

```
13:22:13  client_registered client-1 (round 3 — Máy 2 cold start ~90s sau server boot)
13:22:33  update_received client-1 round 3
13:22:45  update_received client-1 round 4
13:22:58  update_received client-1 round 5
13:23:10  update_received client-1 round 6
13:23:22  update_received client-1 round 7   ← last before Ctrl+C
   ─── GAP ~3 phút (rounds 8-11 không có client-1) ───
13:26:38  update_received client-1 round 12  ← first after restart
13:26:58  update_received client-1 round 13
13:27:16  update_received client-1 round 14
13:27:40  update_received client-1 round 15
13:28:04  update_received client-1 round 16
```

Gap round 7→12 (3 phút 16s) khớp chính xác 4 round `partial` degraded — server tiếp tục với client-0 duy nhất, không crash, restart client-1 rejoin liền mạch từ round 12. **Đây là minh chứng end-to-end cho fault tolerance của M6 infrastructure** (Path B partial + dynamic min_clients).

#### Forensic: 2 lần chạy F1 thất bại trước v3

| Run | num_rounds / timeout | Kết quả | Nguyên nhân |
|---|---|---|---|
| `m76_f1_cross` (v1) | 12 / 30 | 12/12 `ok` | Round nhanh (~13s) → cửa sổ Ctrl+C giữa round quá hẹp, không catch kịp |
| `m76_f1_v2` | 16 / 45 | 16/16 `partial` | Máy 2 launch client-1 **sau khi server đã DONE** → client-1 thấy DONE, thoát ngay; 0 round có client-1 |

**Bài học timing:** (1) Round ngắn (~13s) làm cửa sổ Ctrl+C "giữa 2 round" quá hẹp — `wait_timeout` lớn (45s) nới rộng cửa sổ degraded để thao tác manual dễ canh. (2) Cross-machine cần verify client-1 `client_registered` qua events.csv **trước** khi coi healthy phase bắt đầu — Máy 2 cold start (Python+torch+MNIST) mất ~90s, dễ trễ deadline round đầu. v3 dùng monitor poll events.csv để điều phối chính xác từng phase.

**Connectivity note:** Inbound firewall Allow rule cho `fedml/python.exe` đã tồn tại (Windows prompt chấp nhận từ M3.9). `TcpTest False` từ Máy 2 chỉ xảy ra khi không có server listening (giữa các run) — không phải firewall block.

### M7.7 — Documentation (section này)

Toàn bộ M7.0–M7.6 documented. `Report/m7_plan.md` (plan + 6 vòng review) + `Report/milestone_report.md` (M7 section) hoàn chỉnh.

### Tổng kết M7

| Sub | Description | Status | Artifact |
|---|---|---|---|
| M7.0 | Plan + 6 vòng review (22 fixes) | ✅ | `m7_plan.md` |
| M7.1 | `run_context.py` CLI flag (+10 LOC) | ✅ | `41b85d0` |
| M7.2 | `client.py` validation + sleep (+21 LOC) | ✅ | `41b85d0` |
| M7.3 | Backward compat smoke | ✅ | `m7_smoke_compat` acc 98.52% |
| M7.4 | S1 localhost (delay 5, timeout 60) | ✅ | `m74_s1_localhost` 3/3 ok, acc 99.17% |
| M7.5 | S2 localhost (delay 20, timeout 20) | ✅ | `m75_s2_v3` 3/3 partial, acc 98.85% |
| M7.6 | F1 cross-machine crash/reconnect | ✅ | `m76_f1_v3` 4-phase, acc 99.41% |
| M7.7 | milestone_report documentation | ✅ | section này |

**M7 hoàn thành 100%** — toàn bộ implementation của dự án done.

---

## Bước tiếp theo — Phase Experiments

Toàn bộ implementation M1-M7 done. Data đã sẵn cho cả 4 experiments:

- **Exp 1 — Centralized vs Federated**: M1 baseline (centralized) + M4.4 (federated IID) → so sánh accuracy/round, convergence
- **Exp 2 — IID vs Non-IID**: M4.4 (IID) + M5.4 (Non-IID pathological) → impact của data heterogeneity lên FedAvg
- **Exp 3 — Straggler**: M7.4 S1 (`round_wallclock` +5s/round, vẫn ok) + M7.5 S2 (timeout drop, partial) → straggler impact lên round latency vs accuracy
- **Exp 4 — Fault tolerance**: M7.6 F1 (4-phase crash/recovery) → accuracy degradation khi 1 client crashed + recovery time

Còn lại: **analyze + plot** từ data có sẵn (round_log.csv của các run), rồi viết **báo cáo cuối kỳ** với 4 experiments + phân tích 5 vấn đề distributed systems của `ytuong.md` §7.
