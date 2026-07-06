# Báo cáo Benchmark CIFAR-10 — Federated Learning 1 máy vs 2 máy

Mở rộng hệ Federated Learning từ MNIST sang **CIFAR-10** (ảnh màu, khó hơn nhiều),
dùng **model lớn hơn**, đo và so sánh **3 tiêu chí**: thời gian train (1 máy vs 2 máy),
độ chính xác, và thời gian communication. Trọng tâm phân tích là **hệ phân tán**.

## 1. Cấu hình thí nghiệm

| Thành phần | Giá trị |
|------------|---------|
| Dataset | CIFAR-10 (50.000 train / 10.000 test, ảnh 3×32×32 RGB, 10 lớp) |
| Model | `CifarCNN` — 3 conv block (32/64/128) + BatchNorm + 2 FC, **620K tham số**, payload **2.38 MB** |
| Thuật toán | FedAvg (weighted average theo `num_samples`) |
| Phân chia dữ liệu | IID, 2 shard (25.000 mẫu/client) |
| Siêu tham số | `num_rounds=30`, `local_epochs=2`, `batch_size=32`, `lr=0.01`, SGD momentum 0.9 |
| Phần cứng | Máy 1 & Máy 2: NVIDIA RTX 2000 Ada · kết nối **Ethernet trực tiếp 2.5GbE** (10.0.0.1 ↔ 10.0.0.2) |

**3 kịch bản:**

| | Mô tả | Vị trí |
|---|---|---|
| **B1** Centralized | Train thuần trên toàn bộ train set, không gRPC | 1 máy |
| **B2** Federated localhost | Server + 2 client cùng 1 máy (127.0.0.1) — cô lập overhead gRPC | 1 máy |
| **B3** Federated 2 máy | Server + client-0 ở Máy 1, client-1 ở Máy 2 (qua Ethernet) | 2 máy |

## 2. Kết quả tổng hợp

| Kịch bản | Best acc | Final acc | Tổng thời gian | Train/round | Comm/round |
|----------|:--------:|:---------:|:--------------:|:-----------:|:----------:|
| **B1 Centralized** | 81.17% | 80.26% | **249.6s** | 8.32s/epoch | — |
| **B2 Fed localhost** | 81.90% | 81.59% | **360.7s** | 8.30s | 28.2ms |
| **B3 Fed 2 máy (Ethernet)** | 82.11% | 81.73% | **431.0s** | 9.10s | 42.7ms |

> B3 dùng bản chạy có **rendezvous barrier** (§3.4) — round-1 đo sạch (10.96s thay vì 89.6s).
> `Train/round` và `Comm/round` là trung bình 2 client trên các round `ok` (bỏ round 1).
> `Comm/round ≈ 2 × download` (download model + upload update, payload đối xứng).

**Hình minh hoạ** (sinh bởi [analyze_cifar.py](../analyze_cifar.py), lưu ở `Report/figures/`):
- `cifar_accuracy_per_round.png` — đường hội tụ accuracy 3 kịch bản
- `cifar_round_time_breakdown.png` — phân rã compute / communication / aggregate+eval mỗi round
- `cifar_communication_overhead.png` — download/round: localhost vs Ethernet

## 3. Phân tích theo 3 tiêu chí

### 3.1. Độ chính xác (accuracy)

Cả 3 kịch bản đạt **~80–82%**, gần như bằng nhau:
- Federated (B2/B3) nhỉnh hơn centralized (B1) một chút vì mỗi round có 2 local epoch →
  30 round ≈ 60 epoch-equivalent so với 30 epoch của centralized.
- **B3 (2 máy, 81.73%) ≈ B2 (1 máy, 81.59%)**: phân tán vật lý **không** làm giảm accuracy —
  FedAvg cho kết quả nhất quán bất kể client nằm trên 1 hay 2 máy. Đây là tính đúng đắn
  (correctness) của thuật toán phân tán.
- Model nhỏ tới hạn ở ~82% (train_loss thấp nhưng test acc bão hoà — plateau từ round ~15).

### 3.2. Communication time

Đây là phát hiện quan trọng nhất về hệ phân tán:

| Đo | Giá trị |
|----|---------|
| Download model/round (localhost B2) | ~14.1ms |
| Download model/round (Ethernet B3) | ~21.3ms |
| Communication/round (B3, ≈2×download) | **42.7ms** |
| Tỷ lệ comm / thời gian 1 round (~14.5s) | **~0.3%** |
| Ethernet / localhost | 1.5× |
| **Throughput thô của link (test 1GB)** | **281.8 MB/s = 2.36 Gbps** (~94% của 2.5GbE) |
| Throughput hiệu dụng khi truyền model (2.38MB qua gRPC) | ~0.88 Gbps |

**Nhận xét:**
- Communication **cực nhỏ so với compute**: 44ms so với ~9s train → chỉ chiếm **0.3%** thời gian
  mỗi round. Với model 2.38MB và link nhanh, truyền dữ liệu **không phải nút cổ chai**.
- Chênh lệch throughput đáng chú ý: link thô đạt **2.36 Gbps** (đo bằng
  [tools/throughput_test.py](../tools/throughput_test.py), truyền 1GB liên tục), nhưng truyền
  model chỉ đạt **~0.88 Gbps**. Nguyên nhân: message nhỏ (2.38MB) bị chi phối bởi **overhead
  gRPC + serialize/deserialize (torch.save/load) + latency bắt tay**, chưa kịp bão hoà băng thông.
  → Bài học: với message nhỏ, tối ưu overhead-per-message quan trọng hơn tăng băng thông.

### 3.3. Thời gian train — 1 máy vs 2 máy

Ngược với kỳ vọng "chia 2 máy sẽ nhanh hơn", **B3 (431s) vẫn chậm hơn B2 (361s) và B1 (250s)**.
Nguyên nhân **không phải communication** (chỉ 0.3%) mà là **mất cân bằng tải + rào đồng bộ**:

- **Rào đồng bộ (synchronous barrier).** FedAvg đồng bộ phải **chờ client chậm nhất** mỗi round.
- **Mất cân bằng tải.** Trong B3:
  - client-0 (Máy 1): train **~10.4s/round** — vì Máy 1 **kiêm luôn server** (phục vụ gRPC,
    aggregation, evaluation) → tải nặng hơn.
  - client-1 (Máy 2): train **~7.9s/round** — máy chuyên dụng, chỉ chạy 1 client.
  → Round bị gate bởi node chậm (Máy 1 ~10.4s). Steady-state: B3 ~14.5s/round vs B2 ~11.4s/round.
  Tách 2 máy **không** rút ngắn được thời gian vì node kiêm server trở thành straggler.

**Kết luận tiêu chí này:** với workload nhẹ (model 2.38MB) trên link nhanh, "đi phân tán"
**không tăng tốc** mà thêm chi phí **điều phối/đồng bộ** và **mất cân bằng tải**, chứ không phải
chi phí truyền dữ liệu. Phân tán chỉ có lợi khi compute đủ nặng để lợi ích chia GPU vượt qua
các overhead này (ví dụ model lớn hơn, batch nhiều hơn, hoặc nhiều client hơn 1 server).

### 3.4. Rendezvous barrier — sửa lỗi đo round-1 (đóng góp về hệ phân tán)

**Vấn đề phát hiện:** ban đầu round-1 của B3 đo **89.6s** — gấp ~6× các round sau. Điều tra
events.csv cho thấy đây **không phải hệ chậm** mà là **bấm đồng hồ sai điểm**: `round_start_time`
được đặt ngay khi server bật, TRƯỚC khi client kết nối. Nên round-1 cộng luôn thời gian Máy 2
boot + độ trễ join (import torch + init CUDA + load data + độ trễ khởi động lệch nhau giữa 2 máy).
Một lần đo cho thấy client-0 xong round 1 từ giây thứ 7 nhưng server phải **ngồi chờ Máy 2 tận 69s**.

**Cách khắc phục — thêm pha rendezvous:** server chờ **tất cả expected client register**
(gọi GetGlobalModel lần đầu) rồi **mới** reset `round_start_time`. Đây là **barrier đồng bộ
khởi động** chuẩn của hệ phân tán. Bounded bởi `startup_timeout` để không treo nếu 1 client
không lên (đúng ngữ nghĩa `min_clients`).

**Kết quả (before/after, cùng cặp máy qua Ethernet):**

| | Round-1 wallclock | Tổng thời gian |
|---|:---:|:---:|
| B3 trước rendezvous | 89.6s | 484.1s |
| **B3 sau rendezvous** | **10.96s** | **431.0s** |

→ Round-1 giảm **8×**, về ngang steady-state (~11-15s). Lần chạy sạch nhất, Máy 2 mất **128s**
để join nhưng round-1 vẫn chỉ đo **10.96s** — chứng minh boot/join time đã bị loại hoàn toàn.
Steady-state (round 2-30) **không đổi** trước/sau — đúng như thiết kế (rendezvous chỉ tác động
round-1). Đây vừa là **fix đo lường** vừa là **feature phân tán hợp lý** (startup barrier).

**Quan sát phụ — fault tolerance:** trong một lần chạy thử, client-1 (Máy 2) **chết giữa round 17**
(pull model xong rồi treo, không submit). Server **không sập**: phát hiện `round_timeout`, thực
hiện **partial aggregation** với client còn lại (`min_clients=1`), và hoàn thành đủ 30 round với
accuracy ~80%. Đây là minh chứng thực tế cho **khả năng chịu lỗi** của hệ (degrade gracefully khi
mất 1 node), dù bản chạy đó không dùng cho benchmark vì 14/30 round chỉ còn 1 client.

## 4. Phát hiện về hệ phân tán (tóm tắt)

| Vấn đề | Quan sát từ CIFAR-10 |
|--------|----------------------|
| **Correctness** | Accuracy giữ nguyên (~81.5%) dù chạy 1 hay 2 máy — FedAvg đúng đắn khi phân tán |
| **Communication overhead** | Chỉ 0.3% round time; link 2.36 Gbps nhưng model transfer 0.88 Gbps do overhead-per-message |
| **Synchronous barrier** | Round bị gate bởi client chậm nhất → straggler quyết định throughput |
| **Load imbalance** | Node kiêm server bị chậm hơn (10.4 vs 7.9s) → nên tách server khỏi node train |
| **Startup rendezvous** | Chờ đủ client trước khi đếm round-1 → loại boot time (89.6s → 10.96s) |
| **Fault tolerance** | Client chết giữa run → server partial-aggregate, hoàn thành 30 round không sập |

## 5. Kết luận & hạn chế

**Kết luận:** Mở rộng CIFAR-10 + model lớn hơn chạy tốt trên hệ 2 máy. Accuracy ~81.5% ổn định
qua mọi cấu hình. Communication qua Ethernet 2.5GbE là **không đáng kể** với model cỡ này —
nút cổ chai thực sự là **compute + đồng bộ**, không phải mạng.

**Hạn chế / lưu ý phương pháp:**
- B1/B2 chạy trên Máy 2, B3 phối hợp cả 2 máy → so sánh compute giữa các kịch bản có
  confound phần cứng/tải. Kết luận về communication (đo trực tiếp trên cùng link) vẫn vững.
- Để thấy lợi ích tăng tốc của phân tán, cần workload nặng hơn hoặc tách riêng node server.
- `upload_ms` không đo được phía client trước khi gửi (chicken-egg) → comm ước lượng
  = 2×download (payload đối xứng), đủ chính xác cho phân tích tỷ lệ.

**Dữ liệu thô:** `Report/data/exp_cifar_{centralized,fed_1machine,fed_2machine}/` — tái tạo hình
bằng `python analyze_cifar.py`. B3 dùng run `m1_rv2` (có rendezvous); giữ `m1` (no-rv) để đối
chiếu before/after ở §3.4.
