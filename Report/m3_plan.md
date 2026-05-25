# M3 Plan — Server/client chạy 1 round IID

> Tài liệu này là plan chi tiết cho Milestone 3. Tham khảo: [plan.md](../plan.md) (kế hoạch tổng), [milestone_report.md](milestone_report.md) (báo cáo tiến độ).

---

## 1. Mục tiêu

Chạy thành công **1 round Federated Learning end-to-end**: server gửi global model → 2 client train trên IID partition → server FedAvg + evaluate. Verify trên cả localhost (Máy 1) lẫn cross-machine (Máy 1 + Máy 2).

Sau M3, ~80% logic federated đã có; M4-M7 chỉ thêm tính năng (multi-round, Non-IID, timeout/stale, fault tolerance).

## 2. Scope

**IN — phải có:**
- Server state machine: `TRAINING → AGGREGATING → EVALUATING → DONE` (M3 chỉ 1 round)
- `GetGlobalModel` + `SubmitUpdate` đầy đủ
- Validation đầy đủ 4 lớp (xem §4)
- FedAvg weighted by `num_samples`
- Server evaluate trên CPU (không tranh GPU với Client 1)
- Round log CSV per-round + **events.csv structured**
- IID partition cho 2 client
- Client training loop hoàn chỉnh + timing breakdown
- Test localhost + cross-machine

**OUT — KHÔNG làm ở M3:**
- Multi-round (M4)
- WAIT_TIMEOUT (M6)
- Non-IID partition (M5)
- Straggler simulation (M7)
- Fault tolerance (M7)
- Aggregation async / background thread (M6 khi cần timeout)

## 3. Cấu hình cho M3

Override config.yaml cho M3:

```yaml
# Cấu hình ÉP cho M3 — sẽ revert ở M6 khi mở fault tolerance
num_rounds: 1            # 1 round duy nhất
local_epochs: 2
required_clients: 2      # PHẢI đủ 2 client để aggregate
min_clients: 2           # M3 không chạy với 1 client (M6 sẽ mở lại = 1)
experiment_name: "exp_federated_iid_smoke"
```

Sau M3, `min_clients` sẽ về lại `1` để hỗ trợ fault tolerance experiment.

## 4. Design decisions

| Quyết định | Lựa chọn | Lý do |
|---|---|---|
| `current_round` khởi tạo | `1` (KHÔNG phải 0) | Round 0 dành cho "chưa khởi động". Log dễ đọc, đồng bộ với M2 mock có thể đổi sau |
| Khi nào server bắt đầu round? | Khởi động là state=TRAINING ngay, current_round=1 | Đơn giản, không cần lệnh start |
| Khi nào aggregate? | Trong handler `SubmitUpdate` khi `len(updates) >= required_clients` | M3 không timeout → đồng bộ là đủ. M6 sẽ refactor sang background thread |
| Thread safety | `threading.Lock` quanh state + received_updates | gRPC ThreadPoolExecutor xử lý song song |
| Client pick shard | `--shard-id 0\|1 --num-shards 2` | Cả 2 máy dùng cùng `seed` → `partition_iid(seed=42, num_clients=2)` trả về 2 shard giống nhau, mỗi client tự lấy phần |
| Server eval device | CPU | Không tranh GPU với Client 1 chạy trên Máy 1 |
| Per-client log columns | `client_0_*`, `client_1_*` hard-code cho M3 | M3 chỉ 2 client. **Đánh dấu refactor cho M4+** nếu sang num_clients > 2 (hiện không có trong scope) |
| Stale update test | **Script test riêng** `tests/test_stale_update.py` dùng gRPC trực tiếp | Tránh nhét debug flag (`--override-round-id`) vào product code |

## 5. Validation order trong `SubmitUpdate`

Khi server nhận update, validate theo **đúng thứ tự** sau (fail-fast, log lý do reject vào events.csv):

```python
def SubmitUpdate(request, context):
    with self.lock:
        # 1. Unknown client (sau M6 sẽ có whitelist active_clients)
        if request.client_id not in self.known_clients:
            return _reject("unknown_client", request)

        # 2. State must be TRAINING — quan trọng nhất
        if self.state != RoundStatus.TRAINING:
            return _reject(f"state_not_training (is {self.state})", request)

        # 3. Round mismatch (stale)
        if request.round_id != self.current_round:
            return _reject(f"stale_round (got {request.round_id}, expected {self.current_round})", request)

        # 4. Duplicate update từ cùng client
        if request.client_id in self.received_updates:
            return _reject("duplicate_update", request)

        # All checks passed
        self.received_updates[request.client_id] = request
        # Trigger aggregation nếu đủ
        if len(self.received_updates) >= self.required_clients:
            self.state = RoundStatus.AGGREGATING
            self._aggregate_and_evaluate()  # M6 sẽ chuyển sang background thread
    return _accept(request)
```

**Lý do thứ tự này:** State check trước round check vì nếu server đã DONE (state=DONE), `current_round` vẫn = 1 → client submit muộn với `round_id=1` sẽ không bị stale theo round, phải reject theo state.

## 6. Round log CSV schema

`results/exp_federated_iid_smoke/<run_id>/round_log.csv`:

| Cột | Mô tả |
|---|---|
| `round_id` | Round number (M3: chỉ có 1) |
| `num_clients_received` | Số client gửi update trong round |
| `accuracy` | Test set accuracy sau aggregation |
| `test_loss` | Test loss sau aggregation |
| `acc_class_0` .. `acc_class_9` | Per-class accuracy (10 cột) |
| `aggregation_time_ms` | Thời gian FedAvg |
| `eval_time_ms` | Thời gian evaluate trên test set |
| `round_wallclock_sec` | Tổng thời gian từ start round đến set DONE |
| `client_0_train_loss` | Train loss báo cáo từ client 0 |
| `client_0_num_samples` | Số sample client 0 train |
| `client_1_train_loss` | Train loss báo cáo từ client 1 |
| `client_1_num_samples` | Số sample client 1 train |

> **Refactor note cho M4+:** Per-client columns hard-code chỉ ổn với num_clients=2. Nếu sang num_clients>2 phải đổi sang format dài (mỗi client 1 row trong file riêng) hoặc cột JSON.

## 7. Events CSV schema

`results/exp_federated_iid_smoke/<run_id>/events.csv` — **structured ngay từ M3** để Exp 3/4 parse dễ:

```text
timestamp,round_id,event,client_id,message,num_samples
```

Các `event` type dự kiến trong M3:
- `client_registered` — client gọi `GetRoundStatus` lần đầu (M3: không thực sự register, chỉ log lần đầu thấy client_id)
- `model_pulled` — client gọi `GetGlobalModel` thành công
- `update_received` — client submit update hợp lệ
- `update_rejected` — kèm lý do trong `message` (unknown_client / state_not_training / stale_round / duplicate_update)
- `aggregation_start` — server bắt đầu FedAvg
- `aggregation_done` — kèm `message="duration_ms=..."`
- `evaluation_done` — kèm `message="accuracy=0.95"`
- `round_done` — round kết thúc, state=DONE

`client_id` để rỗng cho event của server (aggregation, evaluation).
`num_samples` chỉ có giá trị với `update_received`/`update_rejected`.

## 8. Subtask breakdown

| # | Subtask | File | Owner | Branch | Estimate |
|---|---|---|---|---|---|
| M3.1 | Refactor `server.py`: ServerState class (global_model, current_round=1, received_updates dict, state=TRAINING, lock, known_clients) | server.py | **Máy 1** | `feature/m3-server-state` | 30 min |
| M3.2 | Implement `GetGlobalModel`: serialize state_dict, log `model_pulled` event | server.py | **Máy 1** | `feature/m3-server-state` (cùng M3.1) | 15 min |
| M3.3 | Implement `SubmitUpdate`: 4-layer validation (§5), log từng outcome vào events.csv | server.py | **Máy 1** | `feature/m3-server-validation` | 45 min |
| M3.4 | `_aggregate_and_evaluate`: FedAvg → write model state → eval CPU → log round_log.csv → set DONE → log `round_done` | server.py | **Máy 1** | `feature/m3-server-aggregation` | 45 min |
| M3.5 | Refactor `client.py`: training loop (poll → pull → train → submit), timing breakdown, **thoát sạch khi state=DONE** | client.py | **Máy 2** | `feature/m3-client-loop` | 45 min |
| M3.6 | Client: pick shard từ `partition_iid(seed=42, num_clients=2)`, gửi metadata (hostname/GPU/torch_ver) trong update đầu | client.py | **Máy 2** | `feature/m3-client-loop` (cùng M3.5) | 15 min |
| M3.7 | Smoke test localhost (server + 2 client trên Máy 1, 3 PowerShell terminal) | (run) | **Máy 1** | — (chạy sau khi merge) | 20 min |
| M3.8 | `tests/test_stale_update.py`: script gRPC client trực tiếp gửi `round_id=99` để verify reject | tests/ | **Máy 2** | `feature/m3-stale-test` | 20 min |
| M3.9 | Cross-machine test (Máy 1 server + client-0, Máy 2 client-1) | (run) | **Cả hai** | — (chạy sau khi tất cả merge) | 20 min |
| M3.10 | Append M3 section vào `Report/milestone_report.md` + commit + push | report | **Máy 1** | `feature/m3-report` | 20 min |

**Tổng ước tính:** ~4-4.5 giờ làm việc. **Song song hóa:** Máy 1 và Máy 2 có thể chạy đồng thời M3.1-M3.4 (Máy 1) và M3.5-M3.6 + M3.8 (Máy 2) → giảm wall-clock xuống còn ~2-2.5 giờ.

## 9. Test plan

### 9.1 Localhost smoke test (Máy 1, 3 PowerShell terminals)

```powershell
# Terminal 1: server
conda activate fedml
python server.py --num-rounds 1

# Terminal 2: client 0
conda activate fedml
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --server-addr 127.0.0.1:50051

# Terminal 3: client 1
conda activate fedml
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --server-addr 127.0.0.1:50051
```

Kỳ vọng:
- Cả 2 client pull model thành công, train ~5-10s/client trên GPU
- Server log accuracy + events
- Cả 2 client thoát sạch khi thấy state=DONE
- `results/exp_federated_iid_smoke/<run_id>/{config.yaml, run_meta.json, round_log.csv, events.csv}` tồn tại đầy đủ

### 9.2 Stale update test

```powershell
# Trên Máy 1, server vẫn chạy hoặc restart:
python server.py --num-rounds 1
# Trên cùng máy, terminal khác:
python tests/test_stale_update.py
```

Test script gửi 4 case:
1. Update với `round_id=99` → reject "stale_round"
2. Update với `client_id="unknown"` → reject "unknown_client"
3. Update hợp lệ → accept
4. Update lại từ cùng client → reject "duplicate_update"

### 9.3 Cross-machine test (Máy 1 + Máy 2)

- **Máy 1:** server + client-0 (`--shard-id 0`)
- **Máy 2:** client-1 (`--shard-id 1 --server-addr 192.168.2.30:50051`)

Verify cùng output như localhost, có thêm: timing upload/download trên LAN thực tế (~5-10ms RTT cộng dồn).

## 10. Acceptance criteria

- [ ] 1 round chạy end-to-end không stuck **cả localhost lẫn cross-machine**
- [ ] Server reject 4 case stale (xem §9.2) — log đúng lý do trong events.csv
- [ ] **Accuracy sau 1 round IID > 80%** (kỳ vọng ~90-95% nhưng không phải acceptance cứng)
- [ ] Loss giảm so với khởi tạo (proxy: chỉ cần accuracy hợp lý > random 10%)
- [ ] `round_log.csv` đủ cột (§6), `events.csv` đủ event type (§7)
- [ ] Timing breakdown của client (download/train/upload) được log
- [ ] Client thoát sạch khi state=DONE (không poll vô tận)
- [ ] Cross-machine: cả 2 client trên 2 máy đều submit thành công

## 11. Rủi ro & lưu ý

1. **Race condition khi 2 client submit gần đồng thời** → `threading.Lock` quanh `received_updates` + state transition. Test bằng cách chạy localhost (2 client nhanh hơn cross-machine, dễ race)
2. **Server eval trên CPU có thể chậm** (~5-10s cho 10000 sample) → log `eval_time_ms` riêng, không gộp vào round_time
3. **Client cuối thấy RPC chậm**: vì aggregation đồng bộ trong handler, client cuối sẽ block ~5-10s chờ FedAvg + eval. M6 sẽ refactor sang background thread khi thêm timeout
4. **Hard-code 2 client**: per-client log columns + `required_clients=2` chỉ ổn cho M3. **Đánh dấu refactor** trong code comment để M4+ dễ tìm khi cần mở rộng (hiện chưa có scope)
5. **Stale test cần server đang TRAINING**: nếu chạy stale test sau khi round 1 đã DONE, một số case sẽ reject theo `state_not_training` thay vì `stale_round`. Test script phải chạy ngay sau khi start server (trước khi client submit), hoặc restart server trước mỗi test

## 12. Sau khi M3 xong

Update `Report/milestone_report.md`:
- Bảng tổng quan: M3 chuyển thành ✅ Done
- Section "Milestone 3" với cùng cấu trúc (mục tiêu / công việc / verified / acceptance / vấn đề)
- Cập nhật snapshot timing: LAN aggregate RTT, FedAvg duration, eval duration, training duration

---

## 13. Git workflow cho 2 dev

**Mô hình:** Feature branch + Pull Request + review trước khi merge vào `dev`.

```text
main (stable)
  ├── dev (integration)
  │     ├── feature/m3-server-state       (Máy 1)
  │     ├── feature/m3-server-validation  (Máy 1)
  │     ├── feature/m3-server-aggregation (Máy 1)
  │     ├── feature/m3-client-loop        (Máy 2)
  │     ├── feature/m3-stale-test         (Máy 2)
  │     └── feature/m3-report             (Máy 1)
```

### Quy ước branch naming

`feature/<milestone>-<scope>` — ví dụ `feature/m3-client-loop`, `feature/m3-stale-test`. Một feature branch nên chứa 1 logical unit (có thể gồm nhiều subtask liên quan như M3.1+M3.2).

### Quy trình per feature (cả 2 máy đều làm tương tự)

```powershell
# 1. Sync dev mới nhất
git checkout dev
git pull origin dev

# 2. Tạo feature branch
git checkout -b feature/m3-client-loop

# 3. Code + commit (nhiều commit nhỏ OK)
# ... edit files ...
git add client.py
git commit -m "M3.5: client training loop with timing breakdown"

# 4. Push lên GitHub
git push -u origin feature/m3-client-loop

# 5. Mở Pull Request trên GitHub: feature/m3-client-loop → dev
#    Title: "M3.5+M3.6: client training loop + shard pick"
#    Description: mô tả thay đổi, test đã chạy, link tới subtask trong m3_plan.md
```

### Quy trình review (Máy 1 = reviewer)

Khi Máy 2 push PR:

1. **Máy 1 đọc diff trên GitHub** (Files changed tab)
2. **Pull về local để test:**
   ```powershell
   git fetch origin
   git checkout feature/m3-client-loop
   # Test thử
   ```
3. **Comment trên PR**: comment inline trên dòng cụ thể hoặc general comment
4. **Nếu cần sửa:** Máy 2 commit thêm vào cùng branch, push, Máy 1 re-review
5. **Khi đồng ý:** Máy 1 click "Merge pull request" trên GitHub (chọn "Create a merge commit" để giữ history rõ)

### Sau khi merge

**Cả 2 máy** sync lại để pull các merge mới nhất:

```powershell
git checkout dev
git pull origin dev
# Xóa branch local đã merge (optional)
git branch -d feature/m3-client-loop
```

### Conflict resolution

Vì server.py (Máy 1) và client.py (Máy 2) là **file khác nhau**, conflict gần như không xảy ra. Nếu có:

- `proto/federated.proto`: **LOCK lại đã**, không sửa trong M3 (đã đầy đủ schema từ M2)
- `config.yaml`: nếu cần thêm key, coordinate trước qua Slack/chat
- `Report/m3_plan.md`: chỉ Máy 1 edit
- Nếu thực sự conflict: ai merge sau phải rebase và resolve, push lại

### Review checklist (rút gọn)

Reviewer (Máy 1) check trước khi approve:

- [ ] Code chạy được (đã test local)
- [ ] Theo đúng spec trong m3_plan.md (validation order, schema CSV, ...)
- [ ] Không thêm scope ngoài subtask
- [ ] Không sửa file của owner khác (vd Máy 2 không sửa server.py)
- [ ] Commit message rõ ràng, có reference subtask (M3.5, M3.6, ...)

---

## 14. Parallel dev — cách Máy 1 và Máy 2 làm song song không block nhau

**Tin tốt:** Proto schema đã lock từ M2 → **server-side và client-side phụ thuộc duy nhất vào proto**, không phụ thuộc implementation của nhau. Hai bên code song song được.

### Critical path

```text
M2 done (proto locked) ─┬─→ Máy 1: M3.1 → M3.2 → M3.3 → M3.4 ─┐
                        │                                       ├─→ M3.7 localhost test (Máy 1)
                        └─→ Máy 2: M3.5 + M3.6 ────────────────┤
                        └─→ Máy 2: M3.8 stale test ────────────┘
                                                                  ↓
                                                          M3.9 cross-machine (cả 2 máy)
                                                                  ↓
                                                          M3.10 report (Máy 1)
```

### Integration points (chỗ 2 bên gặp nhau)

| Contract | Bên định nghĩa | Bên consume |
|---|---|---|
| `GetGlobalModel` request/response schema | proto (đã có) | Máy 1 implement, Máy 2 gọi |
| `SubmitUpdate` validation rules | m3_plan.md §5 | Máy 1 implement, Máy 2 gọi đúng schema |
| `RoundStatus.State` enum | proto (đã có) | Máy 1 set, Máy 2 đọc |
| `events.csv` schema | m3_plan.md §7 | Máy 1 ghi (server-side) |
| `round_log.csv` schema | m3_plan.md §6 | Máy 1 ghi |
| Client shard split (`--shard-id`, `--num-shards`, `seed=42`) | m3_plan.md §4 | Máy 2 implement |

### Khuyến nghị cho Máy 2 (làm song song khi Máy 1 chưa xong server)

Máy 2 có thể test client.py mà không cần server thật bằng cách:

**Option A — Dùng server M2 (đã có):** Server hiện tại trả `RoundStatus(round=0, state=WAITING)`. Client của Máy 2 có thể test phần poll-and-detect-state. Còn `GetGlobalModel`/`SubmitUpdate` sẽ trả UNIMPLEMENTED — client phải handle lỗi này gracefully (log + retry hoặc exit).

**Option B — Mock server tối giản:** Máy 2 viết `tests/mock_server.py` ~30 dòng trả mock data cho cả 3 RPC. Khi server thật merge, bỏ mock đi. Cách này test được full loop nhưng phát sinh code throwaway.

**→ Khuyến nghị Option A** cho M3: nhanh hơn, không cần code throwaway. Máy 2 chỉ cần verify client connect được + tracking timing + exit khi state=DONE. Phần training loop thật sẽ verify ở M3.7 sau khi merge.

### Thứ tự merge khuyến nghị

1. **First**: `feature/m3-client-loop` (Máy 2) — chỉ thêm code, không phá M2 server. Merge sớm để Máy 1 dev server có client mới để test
2. **Second**: `feature/m3-server-state` + `feature/m3-server-validation` + `feature/m3-server-aggregation` (Máy 1) — có thể gộp 1 PR lớn hoặc 3 PR nhỏ tùy mức độ
3. **Third**: `feature/m3-stale-test` (Máy 2) — cần server validation đã merge để test thật
4. **Final**: `feature/m3-report` (Máy 1) — sau khi M3.7 + M3.9 đã pass

### Commands cheatsheet cho Máy 2

```powershell
# Setup lần đầu (đã làm xong ở M2)
conda activate fedml

# Sync trước khi bắt đầu work
cd <repo>
git checkout dev
git pull origin dev

# Bắt đầu feature
git checkout -b feature/m3-client-loop

# Test client với server M2 đang chạy trên Máy 1
python client.py --client-id client-2 --server-addr 192.168.2.30:50051 --poll 3

# Khi xong, push
git add client.py
git commit -m "M3.5: client training loop"
git push -u origin feature/m3-client-loop
# → Mở PR trên GitHub
```
