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
| M5 | Thêm Non-IID partition | ⏳ Pending | — |
| M6 | Timeout + stale update rejection | ⏳ Pending | — |
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

## Bước tiếp theo (M5)

Thêm **Non-IID partition** (Client 1: digits 0-4, Client 2: digits 5-9 — pathological split):

1. Client thêm CLI flag `--data-split iid|noniid`
2. Khi `noniid`, dùng `partition_noniid_pathological(train_set)` (đã có sẵn ở `data_partition.py`)
3. Verify FedAvg vẫn aggregate đúng (server không quan tâm partition)
4. Acceptance: 5+ round Non-IID không stuck; accuracy có thể **thấp hơn IID** (~80-90%), per-class accuracy sẽ lệch (mỗi client chỉ thấy 5 lớp local)

Đây là phép thử distributed systems quan trọng nhất của dự án — chuẩn bị data cho Experiment 2 (IID vs Non-IID). M5 scope hẹp như M4 (chủ yếu là test + log analysis, code change tối thiểu).
