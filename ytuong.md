# Federated Learning Mini System — Revised Proposal

## 1. Ý tưởng chính

Thay vì gom toàn bộ dữ liệu về một máy trung tâm để huấn luyện, ta có nhiều **client** tự huấn luyện mô hình trên dữ liệu riêng của mình. Sau đó, mỗi client chỉ gửi **model weights** về server. Server tổng hợp các mô hình đó thành một mô hình chung bằng thuật toán **FedAvg**.

```text
Client 1 (Máy 1, RTX 2000 Ada) ──────┐
                                       ├──> Server (Máy 1) ──> Global model
Client 2 (Máy 2, RTX 2000 Ada) ──────┘

Server không nhìn thấy dữ liệu gốc của client.
```

> **Giới hạn privacy:** Hệ thống không truyền dữ liệu gốc, nhưng chưa đảm bảo privacy mạnh vì chưa có secure aggregation hoặc differential privacy. Model weights/gradients vẫn có thể rò rỉ thông tin qua các attacks như model inversion.

---

## 2. Hardware thực tế

| Thành phần | Máy 1 | Máy 2 |
|---|---|---|
| GPU | RTX 2000 Ada | RTX 2000 Ada |
| Vai trò | Server + Client 1 | Client 2 |
| Kết nối | LAN/WiFi | LAN/WiFi |

**Ghi chú thiết kế:** Server chạy trên Máy 1 dưới dạng process riêng, không chiếm GPU — GPU của Máy 1 dành toàn bộ cho Client 1. Hai GPU tham gia training thật sự trên 2 máy vật lý, tạo ra network boundary thật và cho phép đo latency có ý nghĩa.

---

## 3. Bài toán demo

| Thành phần | Lựa chọn |
|---|---|
| Dataset | MNIST (nhận diện chữ số viết tay 0–9) |
| Model | CNN nhỏ (2 conv layers + 2 FC layers) |
| Số client | 2 (thật, mỗi client trên 1 máy vật lý) |
| Số round | 20–30 rounds |

**Phân chia dữ liệu — 2 mức cho Experiment 2:**

```text
IID:             mỗi client có đủ 0–9, phân phối đều
Extreme Non-IID: Client 1: 0–4 | Client 2: 5–9
```

Extreme Non-IID là **pathological split** — trường hợp cực đoan để stress test hệ thống. Mỗi client không thấy một nửa nhãn, FedAvg có thể hội tụ chậm hoặc dao động. Đây chính là điểm thú vị để phân tích trong báo cáo.

---

## 4. Kiến trúc hệ thống

### 4.1 Communication Layer: gRPC

**Lý do chọn gRPC thay vì HTTP/REST:**

- gRPC dùng **Protocol Buffers** (binary serialization) — giúp truyền model weights hiệu quả hơn JSON/REST, từ đó giảm communication overhead trong federated setup. Việc Federated nhanh hơn hay chậm hơn Centralized sẽ được kiểm chứng bằng thực nghiệm
- Có thể đo latency, serialization time, transfer time thực tế qua network
- Tạo ra network boundary thật giữa server và client — không phải function call giả lập

**Interface định nghĩa:**

```protobuf
service FederatedLearning {
  rpc GetGlobalModel (RoundRequest) returns (ModelWeights);  // RoundRequest chứa round_id; server trả về model nếu round_id hợp lệ
  rpc SubmitUpdate   (ClientUpdate) returns (AckResponse);
  rpc GetRoundStatus (Empty)        returns (RoundStatus);
}
```

**Round lifecycle:** Client định kỳ gọi `GetRoundStatus` để biết `current_round` và trạng thái round (waiting / training / aggregating). Khi server chuyển sang round mới, client gọi `GetGlobalModel(round_id)` để lấy model tương ứng rồi bắt đầu local training.

### 4.2 Server (Máy 1 — process riêng, không dùng GPU)

**Nhiệm vụ:**
- Khởi tạo global model
- Cung cấp global model để client pull qua gRPC (mỗi client chủ động gọi `GetGlobalModel` đầu round)
- Nhận model updates từ client
- Aggregate bằng FedAvg
- Evaluate global model trên test set sau mỗi round
- Log đầy đủ (round time, client status, accuracy)

**Server state:**

```python
global_model      # weights hiện tại
current_round     # round đang chạy
received_updates  # dict: client_id -> (weights, round_id)
active_clients    # danh sách client đang online
```

**Timeout-based synchronization:**

```python
WAIT_TIMEOUT = 15  # seconds
MIN_CLIENTS  = 1   # tối thiểu 1/2 client để aggregate
```

Logic:
```text
Nếu cả 2 client gửi update trước timeout → aggregate ngay
Nếu timeout → bỏ client chậm, aggregate với client đã gửi
Nếu 0 client gửi → skip round, log lại
```

### 4.3 Client (mỗi máy 1 process, dùng GPU)

**Nhiệm vụ:**
- Kết nối server qua gRPC
- Nhận global model từ server
- Train trên dữ liệu local (GPU)
- Gửi `ClientUpdate` về server (gồm: `client_id`, `round_id`, `weights`, `num_samples`, `train_loss`, `timing_info`)
- Không chia sẻ dữ liệu gốc

### 4.4 Sơ đồ kiến trúc

```
          +----------------------------------+
          |           Máy 1                  |
          |                                  |
          |  +----------+   +------------+   |
          |  |  Server  |   |  Client 1  |   |
          |  | (CPU)    |   | (RTX 2000) |   |
          |  +----+-----+   +-----+------+   |
          |       |               |          |
          +-------+---------------+----------+
                  |         gRPC (LAN)
          +-------+---------------------------+
          |       |           Máy 2           |
          |  +----+-------+                   |
          |  |  Client 2  |                   |
          |  | (RTX 2000) |                   |
          |  +------------+                   |
          +------------------------------------+
```

---

## 5. Thuật toán FedAvg

Server tính weighted average sau mỗi round:

```text
global_weight = (n1 * w1 + n2 * w2) / (n1 + n2)
```

Trong đó:
- `w1, w2`: model weights từ Client 1, Client 2
- `n1, n2`: số lượng training samples của từng client

Nếu một client bị timeout, chỉ dùng weights của client còn lại (tức `global_weight = w_available`).

> **Stale update prevention:** Mỗi `ModelWeights` và `ClientUpdate` gắn với `round_id`. Server reject update nếu:
> - `round_id != current_round` (stale update từ round trước)
> - `client_id` không nằm trong `active_clients`
> - `num_samples` bị thiếu hoặc bằng 0
>
> Mọi trường hợp reject đều được log lại. Đây là vấn đề thực tế trong hệ phân tán khi client chậm gửi update sau khi server đã sang round mới.

> **Lưu ý khi MIN_CLIENTS = 1 với Non-IID cực đoan:** Nếu Client 2 timeout nhiều round liên tiếp, global model sẽ bị kéo mạnh về phân phối của Client 1 (digits 0–4). Per-class accuracy sẽ phản ánh điều này rõ hơn accuracy tổng thể.

---

## 6. Luồng hoạt động mỗi round

```text
Round bắt đầu:
  1. Client 1 và Client 2 pull global model từ server qua gRPC (`GetGlobalModel`)
  2. Client 1 và Client 2 train song song trên GPU riêng
  3. Client gửi weights về server (gRPC)
  4. Server chờ tối đa WAIT_TIMEOUT giây
  5. Server aggregate bằng FedAvg
  6. Server evaluate trên test set → log accuracy, loss
  7. Server log: round time, communication size, client status
Round tiếp theo...
```

---

## 7. Vấn đề Distributed Systems cần phân tích

Đây là phần trọng tâm của báo cáo — **không phải ML**.

### 7.1 Communication Overhead

```text
Mỗi round:
  communication cost = model_size_bytes × 2 chiều × số client
```

So sánh:
- Phân tích kích thước truyền khi gửi full model weights mỗi round
- Các kỹ thuật giảm communication như weight delta, gradient compression, hoặc quantization được thảo luận ở Future Work
- gRPC (protobuf) vs. HTTP+JSON về tốc độ serialization

### 7.2 Synchronization Model

Hệ thống dùng **bounded synchronous** model:
- Có timeout → không bị block vô hạn bởi client chậm
- Vẫn chờ đủ `MIN_CLIENTS` trước khi aggregate
- Tradeoff: accuracy vs. round completion time

### 7.3 Straggler Problem

Client chậm ảnh hưởng toàn bộ round. Sẽ được simulate và đo trong Experiment 3.

### 7.4 Fault Tolerance

Server tiếp tục hoạt động khi 1 client crash hoặc timeout. Mọi sự kiện phải được log rõ ràng:

```text
[Round 7] Client 2 timeout after 15s — proceeding with 1 update
[Round 8] Client 2 reconnected
```

### 7.5 Data Heterogeneity (Non-IID)

Dữ liệu phân bố không đồng đều giữa các client ảnh hưởng đến tốc độ hội tụ và accuracy cuối cùng. Trong centralized training, toàn bộ dữ liệu được gom lại nên không có vấn đề lệch phân phối giữa các client trong quá trình tối ưu như Federated Learning.

---

## 8. Kế hoạch Experiment

### Experiment 1: Centralized vs. Federated

| | Centralized | Federated |
|---|---|---|
| Setup | Gom toàn bộ data, train trên 1 GPU | 2 client, 2 GPU, FedAvg |
| Metric | Accuracy, training time | Accuracy, total time, comm. overhead |

Giả thuyết: Federated có thể giảm thời gian local training nhờ song song hóa trên 2 GPU, nhưng tổng thời gian có thể tăng do communication và synchronization overhead. Experiment này sẽ đo tradeoff giữa parallel training và distributed overhead.

### Experiment 2: IID vs. Non-IID

| | IID | Non-IID |
|---|---|---|
| Phân chia | Mỗi client có đủ 0–9 | Client 1: 0–4, Client 2: 5–9 |
| Kỳ vọng | Hội tụ nhanh, accuracy cao | Hội tụ chậm hơn, accuracy thấp hơn |

### Experiment 3: Straggler Simulation

Giả lập Client 2 bị delay bằng `time.sleep(N)` trước khi gửi weights.

So sánh:
```text
Case A — No timeout:   server chờ → round time tăng, accuracy ổn
Case B — Timeout 15s:  server skip → round nhanh, accuracy có thể giảm nhẹ
```

Đo: round completion time, final accuracy, throughput (rounds/minute).

### Experiment 4: Client Failure

```text
Round 1–4:  cả 2 client hoạt động bình thường
Round 5–7:  Client 2 disconnect (simulate crash)
Round 8+:   Client 2 reconnect
```

Phân tích:
- Hệ thống có tiếp tục chạy không?
- Accuracy giảm bao nhiêu khi thiếu 1 client?
- Recovery sau khi client quay lại nhanh thế nào?

---

## 9. Metrics cần đo

**Core metrics** (bắt buộc đo):

| Metric | Đơn vị | Ghi chú |
|---|---|---|
| Accuracy per round | % | Đo trên test set tập trung ở server |
| Per-class accuracy | % | Accuracy riêng cho từng digit 0–9 — phát hiện model lệch do Non-IID hoặc client timeout |
| Loss per round | float | Train loss + test loss |
| Round completion time | seconds | Tổng thời gian 1 round |
| ↳ Download global model | ms | Thời gian client pull model từ server |
| ↳ Local training time | ms | Thời gian train trên GPU |
| ↳ Upload update | ms | Thời gian gửi `ClientUpdate` về server |
| ↳ Waiting time | ms | Server chờ client chậm |
| Communication size | MB/round | Kích thước model weights được truyền |
| Client participation rate | % | Số client gửi update đúng `round_id` / tổng client |

**Optional metrics** (nếu có thời gian):

| Metric | Đơn vị | Ghi chú |
|---|---|---|
| Serialization time | ms | Thời gian encode/decode protobuf |
| Aggregation time | ms | Thời gian FedAvg trên server |
| Evaluation time | ms | Thời gian evaluate global model |
| GPU utilization | % | Đo bằng `nvidia-smi` |
| Training throughput | samples/sec | Riêng phần local training |

---

## 10. Cấu trúc project

```text
federated-learning-mini/
│
├── proto/
│   └── federated.proto          # gRPC service definition
│
├── server.py                    # Aggregation server
├── client.py                    # Client (chạy trên từng máy)
├── model.py                     # CNN model definition
├── data_partition.py            # IID / Non-IID data split
├── experiments.py               # Chạy các experiment tự động
│
├── requirements.txt
├── README.md
│
└── results/
    ├── exp1_centralized_vs_federated.csv
    ├── exp2_iid_vs_noniid.csv
    ├── exp3_straggler.csv
    ├── exp4_fault_tolerance.csv
    └── plots/
        ├── accuracy_per_round.png
        ├── round_time_comparison.png
        └── communication_overhead.png
```

---

## 11. Tech Stack

| Thành phần | Thư viện |
|---|---|
| ML Framework | PyTorch |
| Communication | gRPC + protobuf (`grpcio`, `grpcio-tools`) |
| HTTP/REST comparison (optional) | FastAPI — dùng để so sánh overhead với gRPC nếu có thời gian |
| Monitoring | `nvidia-smi`, Python `logging` |
| Visualization | Matplotlib, pandas |
| Containerization (optional) | Docker Compose |

---

## 12. Scope cuối cùng (MVP)

```text
Dataset    : MNIST
Model      : CNN nhỏ
Hardware   : 2 máy × RTX 2000 Ada, kết nối LAN
Clients    : 2 (thật, không simulate)
Server     : 1 (Máy 1, CPU only)
Algorithm  : FedAvg với weighted average
Comm layer : gRPC (protobuf)
Sync model : Bounded synchronous với timeout

Experiments:
  1. Centralized vs. Federated (throughput + accuracy)
  2. IID vs. Non-IID
  3. Straggler simulation
  4. Client failure + recovery
```

---

## 13. Deliverables

| # | Deliverable |
|---|---|
| 1 | Source code server + client chạy được trên 2 máy vật lý |
| 2 | Log CSV cho 4 experiments (centralized vs federated, IID vs non-IID, straggler, fault tolerance) |
| 3 | Biểu đồ accuracy per round, round time breakdown, communication overhead |
| 4 | Báo cáo phân tích tradeoff: parallel training vs distributed overhead, IID vs non-IID convergence, fault tolerance behavior |

---

## 14. Framing cho báo cáo

> Dự án xây dựng một hệ thống Federated Learning tối giản trên 2 máy vật lý kết nối LAN, trong đó mỗi máy đóng vai trò một client huấn luyện độc lập trên GPU riêng. Server trung tâm tổng hợp model bằng FedAvg qua gRPC. Hệ thống được thiết kế để phân tích các vấn đề cốt lõi của distributed systems: communication overhead, bounded synchronization, straggler problem, và fault tolerance — với kết quả thực nghiệm trên hardware thật.

---

## 15. Tên đề tài

**"Design and Evaluation of a Two-Node Federated Learning System with gRPC Communication"**

Hoặc tiếng Việt:

**"Thiết kế và đánh giá hệ thống Federated Learning hai node với giao tiếp gRPC"**

---

## 16. Future Work (không cần implement)

- **Asynchronous FL:** Server aggregate ngay khi nhận update, không chờ đủ client — giải quyết straggler nhưng phát sinh stale gradient
- **Differential Privacy:** Thêm Gaussian noise vào weights trước khi gửi để bảo vệ dữ liệu
- **Gradient Compression:** Giảm communication cost bằng cách chỉ gửi top-k gradients
- **FedProx:** Thuật toán thay thế FedAvg, robust hơn với Non-IID data
