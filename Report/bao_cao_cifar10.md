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
| **B1 Centralized** | 81.17% | 80.26% | **237.6s** | 7.92s/epoch | — |
| **B2 Fed localhost** | 82.24% | 81.97% | **340.3s** | 8.47s | 27.4ms |
| **B3 Fed 2 máy (Ethernet)** | 82.11% | 81.73% | **431.0s** | 9.10s | 42.7ms |

> Cả 3 kịch bản anchor trên Máy 1 (phần cứng nhất quán); B2/B3 dùng **rendezvous barrier**
> (§3.4) nên round-1 đo sạch (B2 11.34s, B3 10.96s). `Train/round` và `Comm/round` là trung
> bình 2 client trên các round `ok` (bỏ round 1). `Comm/round ≈ 2 × download` (đối xứng).

**Hình minh hoạ** (sinh bởi [analyze_cifar.py](../analyze_cifar.py), lưu ở `Report/figures/`):
- `cifar_accuracy_per_round.png` — đường hội tụ accuracy 3 kịch bản
- `cifar_round_time_breakdown.png` — phân rã compute / communication / aggregate+eval mỗi round
- `cifar_communication_overhead.png` — download/round: localhost vs Ethernet

## 3. Phân tích theo 3 tiêu chí

### 3.1. Độ chính xác (accuracy)

Cả 3 kịch bản đạt **~80–82%**, gần như bằng nhau:
- Federated (B2/B3) nhỉnh hơn centralized (B1) một chút vì mỗi round có 2 local epoch →
  30 round ≈ 60 epoch-equivalent so với 30 epoch của centralized.
- **B3 (2 máy, 81.73%) ≈ B2 (1 máy, 81.97%)**: phân tán vật lý **không** làm giảm accuracy —
  FedAvg cho kết quả nhất quán bất kể client nằm trên 1 hay 2 máy. Đây là tính đúng đắn
  (correctness) của thuật toán phân tán.
- Model nhỏ tới hạn ở ~82% (train_loss thấp nhưng test acc bão hoà — plateau từ round ~15).

### 3.2. Communication time

Đây là phát hiện quan trọng nhất về hệ phân tán:

| Đo | Giá trị |
|----|---------|
| Download model/round (localhost B2) | ~12.7ms |
| Download model/round (Ethernet B3) | ~21.3ms |
| Communication/round (B3, ≈2×download) | **42.7ms** |
| Tỷ lệ comm / thời gian 1 round (~14.5s) | **~0.3%** |
| Ethernet / localhost | 1.6× |
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

Ngược với kỳ vọng "chia 2 máy sẽ nhanh hơn", **B3 (431s) vẫn chậm hơn B2 (340s) và B1 (238s)**.
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

Rendezvous cũng cải thiện **B2 localhost** (round-1 ~30s → **11.34s**), nhưng mức ít hơn B3 vì
localhost 2 client boot gần như đồng thời → xác nhận rendezvous là fix tổng quát cho startup,
tác dụng lớn nhất khi client khởi động lệch nhau nhiều (cross-machine).

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
| **Tối ưu overhead** | Eval off critical path + poll 0.5s → B3 round 14.5s→10.7s (26%) (§5) |
| **Cân bằng tải** | Shard 45/55 (node kiêm server ít data hơn) → B3 10.7s→9.8s ≈ B2 9.7s; chênh phân tán 3.2s→0.1s (§5) |
| **Scale-up (khi nào phân tán thắng)** | Model nặng (ResNet-18) → GPU saturate → B3 thắng B2 **1.96×** (eff 98%); lợi ích phân tán tỷ lệ compute (§6) |

## 5. Tối ưu tăng tốc (opt-A + opt-B) — triệt tiêu chi phí phân tán

Phân rã 1 round B3 (14.5s) cho thấy 2 overhead **không phải communication**:

| Thành phần | Thời gian | |
|-----------|:---------:|---|
| Client chậm nhất train (Máy 1 c0) | ~10.4s | compute (mất cân bằng) |
| **Eval trên critical path** | **~2.9s** | ⚠️ client phải chờ server eval xong mới pull model round sau |
| Poll latency (`POLL_INTERVAL=2s`) | ~1.1s | client chờ mới phát hiện round mới |
| Aggregation + download | <0.03s | không đáng kể |

**opt-A (2 fix rẻ, không đổi kiến trúc):**
1. **Đưa eval RA KHỎI critical path**: server 4-phase — aggregate → commit + **advance round NGAY**
   (client được giải phóng pull model + train round sau) → **eval + log ở Phase 4 chạy nền song song**
   round sau (eval trên temp model, không chạm `state.model`). Bỏ ~2.9s khỏi latency mỗi round.
2. **Giảm `POLL_INTERVAL_SEC` 2.0 → 0.5**: client phát hiện round mới nhanh hơn.

**Kết quả (before/after, cùng phần cứng + rendezvous):**

| Kịch bản | Steady/round | Tổng | opt-A tiết kiệm |
|----------|:---:|:---:|:---:|
| B2 localhost — no-opt | 11.3s | 340s | — |
| **B2 localhost — opt-A** | **9.7s** | **291s** | −1.6s/round |
| B3 2 máy — no-opt | 14.5s | 431s | — |
| **B3 2 máy — opt-A** | **10.7s** | **317s** | −3.8s/round (**26%**) |

**Phân tích trung thực:**
- opt-A tăng tốc **cả hai** cấu hình; B3 hưởng lợi nhiều hơn (−3.8s) vì eval nằm trọn trên
  critical path của round, còn localhost eval chồng lấn compute ít hơn.
- **Khoảng cách phân tán thu hẹp mạnh:** chênh B3−B2 từ **3.2s** (14.5−11.3) xuống **0.9s** (10.7−9.7)
  — **giảm 72%**. Communication vẫn không đổi (vẫn 0.3%), nên toàn bộ cải thiện đến từ cắt overhead
  điều phối, không phải mạng.
- **Phần dư 0.9s = mất cân bằng tải:** B3 vẫn bị gate bởi Máy 1 straggler (c0_train ~10.1s vs Máy 2
  ~8.2s, do Máy 1 kiêm server) → xử lý bằng opt-B dưới đây.

**opt-B — cân bằng shard theo tốc độ node.** Cấp Máy 1 (kiêm server, chậm hơn) **shard nhỏ hơn**
để 2 client về đích cùng lúc. Ước lượng tỷ lệ từ rate: Máy 1 25k/10.1s vs Máy 2 25k/8.2s →
**45/55** (Máy 1 22.500 mẫu, Máy 2 27.500). FedAvg weighted theo `num_samples` nên **accuracy giữ
nguyên** (81.62%). CLI `--shard-weights 0.45,0.55` (giống nhau mọi client).

| Kịch bản | Steady/round | c0_train (Máy1) | c1_train (Máy2) | Chênh train |
|----------|:---:|:---:|:---:|:---:|
| B3 opt-A (đều 50/50) | 10.7s | 10.1s | 8.2s | 1.86s |
| **B3 opt-A+B (45/55)** | **9.8s** | 7.5s | 8.7s | **1.21s** |
| B2 opt-A (1 máy) | 9.7s | — | — | — |

→ Round giảm tiếp **10.7s → 9.8s** (cắt được client chậm nhất 10.1s→8.7s). Về train skew:
1.86s (Máy 1 chậm hơn) → **−1.21s** — **giảm 37% nhưng ĐỔI DẤU**: 45/55 hơi quá tay, giờ Máy 2
(55% data) thành client chậm hơn. Tỷ lệ tối ưu ~**48/52**, chưa cân hoàn hảo. Dù vậy **B3 (9.8s)
≈ B2 (9.7s)** — chênh chỉ 0.08s (trong nhiễu). **Lưu ý quan trọng:** đây là *ngang bằng*, KHÔNG
phải thắng — với model nhẹ, phân tán tốt nhất chỉ **hòa** 1 máy (xem §6 để phân tán THẮNG).

→ **Kết luận opt — hành trình thu hẹp chi phí phân tán (model nhẹ):**

| | B3 round | B2 round | B3−B2 | Phân tán |
|---|:---:|:---:|:---:|:---:|
| Baseline (rendezvous) | 14.48s | 11.34s | **+3.14s** | **THUA 1.28×** |
| + opt-A (eval off-path + poll) | 10.66s | 9.73s | +0.93s | thua nhẹ |
| + opt-B (cân bằng shard) | 9.81s | 9.73s | +0.08s | **hòa** |

**Điểm mấu chốt:** với model nhẹ, ở baseline phân tán **THUA rõ 1.28×** (B3 14.48s > B2 11.34s) —
vì GPU chưa bão hoà nên 2 client/1 GPU (B2) không serialize, trong khi B3 gánh thêm network +
straggler Máy 1 kiêm server. Sau opt-A + opt-B, phân tán chỉ **đuổi kịp về hòa**, KHÔNG bao giờ
thắng. Communication (0.3%) chưa bao giờ là nút cổ chai — các nút thực là **eval trên critical
path, poll latency, load imbalance**, đều xử lý được không đụng mạng. **Nhưng "hòa" chưa đủ hấp
dẫn để phân tán → đó là động lực chuyển sang model nặng ở §6, nơi phân tán thực sự THẮNG.**

## 6. Khi nào phân tán THẮNG — scale-up compute intensity

§5 cho thấy với model nhẹ (CifarCNN 620K), phân tán **thua ở baseline (1.28×)** và tốt nhất chỉ
**hòa** 1 máy sau tối ưu. Câu hỏi: **có khi nào phân tán thực sự nhanh hơn?** Giả thuyết: khi
compute đủ nặng để **1 client saturate GPU**, thì 2 client trên 1 GPU (B2) phải serialize, còn
2 GPU riêng (B3) chạy song song → B3 thắng.

**Thí nghiệm:** đổi sang model nặng **ResNet-18** (11.17M params, gấp 18× CifarCNN; payload
**42.7 MB** so với 2.4 MB). CLI `--model resnet`. (Phải bump gRPC message limit 16→128MB.)

**Đo GPU contention (localhost, ResNet, 25k mẫu/client):**

| | Train time/round |
|---|:---:|
| T1 — 1 client (full GPU) | 34.1s |
| T2 — 2 client (chung 1 GPU) | 71.9s |
| **Contention factor T2/T1** | **2.11×** |

→ Với ResNet, GPU bị saturate: 2 client chung 1 GPU **serialize gần hoàn toàn** (2.11×), khác hẳn
CifarCNN nhẹ (2 client chạy chồng lấn gần như miễn phí).

**Kết quả 2 máy thật (ResNet):**

| | Round (steady) | Cơ chế |
|---|:---:|---|
| B2 (1 máy, 2 client/1 GPU) | 74.3s | serialize |
| **B3 (2 máy, 2 GPU song song)** | **37.8s** | song song |
| **→ Phân tán nhanh hơn** | **1.96×** (hiệu suất 98%) | |

→ B3 mỗi client chạy trên GPU riêng (Máy1 ~36s, Máy2 ~30s, round gate bởi Máy1), khớp T1 solo
(~34s). Speedup **1.96×** trên 2 máy ⇒ **hiệu suất song song 98%** — gần strong-scaling lý tưởng.
Communication (payload 42.7MB) là 390ms/round = **~1% round** — kể cả model gấp 18×, **mạng vẫn
không phải nút cổ chai** trên link 2.5GbE. *(Lưu ý: B2-heavy chạy ít round — n=2 steady; số ổn
định nhưng nên chạy dài hơn nếu cần độ chính xác cao hơn.)*

**Kết luận scale-up:** **lợi ích phân tán tỷ lệ với độ nặng compute.** Workload nhẹ → 1 GPU gánh
2 client thoải mái (không serialize) → phân tán **thua/hòa** 1 máy (§5). Workload nặng → 1 GPU
serialize → phân tán 2 máy **tăng tốc gần tuyến tính (1.96×, hiệu suất 98%)**. Cặp **"nhẹ thua /
nặng thắng"** trả lời trực tiếp câu hỏi nghiên cứu: FL/phân tán đáng giá khi model/dữ liệu đủ lớn
để bão hoà GPU — đúng bối cảnh thực tế (model production lớn hơn nhiều CifarCNN).

## 7. Kết luận & hạn chế

**Kết luận:** Mở rộng CIFAR-10 + model lớn hơn chạy tốt trên hệ 2 máy. Accuracy ~81.5% ổn định
qua mọi cấu hình. Communication qua Ethernet 2.5GbE là **không đáng kể** với model cỡ này —
nút cổ chai thực sự là **compute + đồng bộ**, không phải mạng. **Với model nhẹ, phân tán THUA
1 máy ở baseline (1.28×)**; sau opt-A (eval off critical path + poll) và opt-B (cân bằng shard),
chi phí phân tán thu hẹp mạnh (chênh round 3.14s → 0.08s) nhưng tốt nhất chỉ **đuổi kịp về hòa**,
không thắng. Các nút cổ chai thực (eval on-path, poll, load imbalance) đều xử lý được mà không đụng
tới mạng — khẳng định communication chưa bao giờ là giới hạn. **Chỉ khi scale-up compute**
(ResNet-18, §6) phân tán mới **thắng rõ 1.96× (hiệu suất song song 98%)** vì 1 GPU serialize 2 client
còn 2 GPU chạy song song → **lợi ích phân tán tỷ lệ với độ nặng compute** (mạng vẫn ~1%). Cặp
**"nhẹ thua / nặng thắng"** là kết luận trung tâm: phân tán đáng giá khi compute đủ nặng.

**Hạn chế / lưu ý phương pháp:**
- Cả 3 kịch bản anchor trên Máy 1 (server/node chính), phần cứng nhất quán — đã kiểm chứng
  Máy 1 ≈ Máy 2 (B2 steady-state 11.3s trên Máy 1 khớp 11.4s trên Máy 2; B1 accuracy trùng
  do cùng seed). B3 client-1 chạy Máy 2 là yếu tố "remote" duy nhất — đúng bản chất thí nghiệm.
- Để thấy lợi ích tăng tốc của phân tán, cần workload nặng hơn hoặc tách riêng node server.
- `upload_ms` không đo được phía client trước khi gửi (chicken-egg) → comm ước lượng
  = 2×download (payload đối xứng), đủ chính xác cho phân tích tỷ lệ.

**Hạn chế bổ sung (§5):** so sánh opt dùng B2/B3 optimized chạy ở các thời điểm khác nhau; train
time có nhiễu run-to-run (~±0.5s). Kết luận "chênh 0.9s do straggler" vững vì lặp lại pattern
c0_train > c1_train ở mọi run B3.

**Dữ liệu thô:** `Report/data/exp_cifar_*/`:
- Baseline (rendezvous, §2-4): B1 `m1`, B2 `m1_rv`, B3 `m1_rv2`.
- Opt-A (§5): B2 `m1_opt`, B3 `m1_opt5`.
- Opt-B (§5): B3 `m1_optB` (shard 45/55; 28/30 round đủ 2 client, đo steady-state trên round sạch).
- Scale-up (§6): `exp_cifar_heavy_*` — solo `s2` (T1), 1máy `b2b` (B2), 2máy `m1_heavy` (B3), ResNet.
- Run cũ giữ đối chiếu: B1/B2 `m2`, B3 `m1` (no-rv).

Tái tạo hình baseline: `python analyze_cifar.py`.
