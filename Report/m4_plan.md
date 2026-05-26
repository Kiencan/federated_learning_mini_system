# M4 Plan — Chạy 5 round IID + log CSV

> Plan chi tiết cho Milestone 4. Tham khảo: [plan.md](../plan.md) (tổng), [m3_plan.md](m3_plan.md) (M3 plan), [milestone_report.md](milestone_report.md) (tiến độ).

---

## 1. Mục tiêu

Mở rộng M3 từ 1 round → **N rounds liên tiếp (smoke = 5)**. Verify server's round advance logic và client's multi-round loop, log đủ N row vào `round_log.csv`. Sau M4, hệ thống có thể chạy full experiment (30 round IID) khi cần.

## 2. Scope

**IN — phải có:**
- Client refactor: loop N round, mỗi round pull-train-submit lại
- Server advance round: verify nhánh `s.current_round += 1` trong `_aggregate_and_evaluate_locked` chạy đúng cho N > 1
- `round_log.csv` append đủ N row
- `events.csv` ghi đủ events cho N round
- Test 5 round IID localhost + cross-machine
- (Bonus optional) Chạy thêm 30 round để có **baseline data thật cho Exp 1**

**OUT — KHÔNG làm ở M4:**
- Non-IID partition (M5)
- WAIT_TIMEOUT / async aggregation (M6)
- Straggler simulation (M7)
- Fault tolerance / client crash recovery (M7)

## 3. Cấu hình cho M4

Không đổi cấu trúc `config.yaml`. Chỉ thay đổi tham số runtime qua CLI:

```yaml
# Giữ nguyên config.yaml
num_rounds: 30           # default production; M4 smoke override --num-rounds 5
local_epochs: 2
batch_size: 32
lr: 0.01
min_clients: 2           # vẫn 2 (M6 sẽ về 1)
expected_client_ids: ["client-0", "client-1"]
```

M4 smoke: `python server.py --num-rounds 5`. Sau khi pass: chạy `--num-rounds 30` để có baseline experiment.

## 4. Design decisions

| Quyết định | Lựa chọn | Lý do |
|---|---|---|
| Client multi-round structure | Outer `while True` loop với `last_completed_round` tracker | Tránh hardcode `for _ in range(N)`; client tự thoát khi server set DONE |
| Khi nào client start round mới? | Khi `status.state == TRAINING` và `status.current_round > last_completed_round` | Tự detect server advance, không phụ thuộc client-side counter |
| Khi nào client thoát? | `status.state == DONE` | Server quản lý termination qua `num_rounds_total` |
| Model state giữa các round | Pull fresh model mỗi round qua `GetGlobalModel` | FedAvg yêu cầu client start từ global model mới |
| Optimizer giữa các round | Tạo mới mỗi round | Momentum local không exchange — reset hợp lý |
| DataLoader giữa các round | Tạo 1 lần đầu, reuse (shuffle=True tự rotate) | Tránh re-load MNIST mỗi round |
| Server round advance | Đã có sẵn từ M3 (`_aggregate_and_evaluate_locked` nhánh else) | Không sửa server.py — chỉ verify hoạt động qua test |

## 5. Subtask breakdown

| # | Subtask | File | Owner | Branch | Estimate |
|---|---|---|---|---|---|
| M4.1 | Verify server multi-round (đọc code + smoke 2-3 round local) | server.py (no change) | **Máy 1** | — (verify only) | 15 min |
| M4.2 | Client refactor: outer round loop với `last_completed_round`; tách `do_one_round()` thành function | client.py | **Máy 2** | `feature/m4-client-multiround` | 45 min |
| M4.3 | Smoke test localhost 5 round | (run) | **Máy 1** | — (sau khi merge M4.2) | 15 min |
| M4.4 | Cross-machine 5 round | (run) | **Cả hai** | — | 15 min |
| M4.5 | (Bonus) Chạy 30 round cross-machine để có baseline experiment | (run) | Cả hai | — | ~12 min runtime + record |
| M4.6 | Update `Report/milestone_report.md` với M4 section | report | **Máy 1** | (direct commit dev) | 20 min |

**Tổng ước tính:** ~2 giờ làm việc; song song hóa hạn chế vì M4 phần lớn là client-side.

## 6. Client refactor (M4.2) — pseudocode

**Setup 1 lần** (load MNIST + shard + DataLoader); **per-round** tạo lại model + optimizer:

```python
def run_federated(args, cfg, server_addr):
    # ── Setup 1 LẦN trước outer loop ────────────────────────────────
    channel, stub = open_grpc_channel(server_addr)
    train_set, _ = load_mnist(...)
    shards = partition_iid(train_set, num_clients=args.num_shards, seed=cfg["seed"])
    shard = shards[args.shard_id]
    loader = make_loader(shard, batch_size=cfg["batch_size"], shuffle=True)
    device = setup_device(cfg)

    # ── Outer multi-round loop ──────────────────────────────────────
    last_completed_round = 0
    while True:
        status = wait_for_new_round_or_done(stub, last_completed_round)
        if status.state == DONE:
            break
        round_id = status.current_round

        # Per-round: fresh model + fresh optimizer
        model = MnistCNN()                                       # mới mỗi round
        model_resp = stub.GetGlobalModel(round_id=round_id, ...)
        load_state_dict_from_bytes(model, model_resp.serialized_state_dict)
        model.to(device)
        optimizer = torch.optim.SGD(model.parameters(), lr=cfg["lr"], momentum=0.9)

        # Train + submit
        last_loss, num_samples, timings = train_local(model, loader, optimizer, ...)
        update = build_update(model, round_id, num_samples, last_loss, timings)
        ack = stub.SubmitUpdate(update, timeout=120)

        # Reject handling — exit luôn, không loop tiếp
        if not ack.accepted:
            print(f"[client] ERROR: rejected at round {round_id}: "
                  f"{ack.message} (server_round={ack.server_round})")
            sys.exit(3)

        last_completed_round = round_id

    # Summary cuối
    print_total_timing_summary()


def wait_for_new_round_or_done(stub, last_completed_round):
    while True:
        status = stub.GetRoundStatus(...)
        if status.state == DONE:
            return status
        if status.state == TRAINING and status.current_round > last_completed_round:
            return status
        # AGGREGATING / EVALUATING / TRAINING(cùng round đã submit) — chờ tiếp
        time.sleep(POLL_INTERVAL_SEC)
```

**Edge cases:**
- Server đang `AGGREGATING`/`EVALUATING` giữa round N và N+1 → client poll tiếp
- Server set `DONE` ngay sau round cuối (không pass qua TRAINING round N+1) → loop thấy DONE, thoát
- **Client mới connect mid-experiment** (vd round 3 đang chạy): `last_completed_round=0`, thấy `current_round=3 > 0`, sẽ join round 3 nếu state đang `TRAINING`. **M4 không hỗ trợ "catch up"** — không train lại round 1 và 2. Nếu khi connect server đang `AGGREGATING`/`EVALUATING`, client phải chờ đến round tiếp theo (acceptable).
- **Update bị reject**: bất kỳ lý do nào (stale_round, state_not_training, duplicate) → client print lý do + `server_round` rồi `sys.exit(3)`. **Không retry, không tiếp tục loop** — tránh log nhiễu và indicate bug rõ ràng.

## 7. Test plan

### 7.1 Server sanity-check (Máy 1)

`tests/_smoke_server.py` (từ M3) **expect server DONE ngay sau round 1** → KHÔNG thể chạy với `--num-rounds 3` (sẽ false-fail vì server đang `TRAINING round=2`).

**Cách 1 (chọn cho M4):** chạy với `--num-rounds 1` để sanity-check server M3 vẫn không bị broken sau khi merge M4 changes (M4 chỉ sửa client.py — server không đổi, nên test phải vẫn pass).

```powershell
python server.py --num-rounds 1 --run-id sanity_m4
# Terminal khác:
python tests\_smoke_server.py
# All 9 cases vẫn phải pass
```

**Cách 2 (optional, nếu muốn server-side multi-round test):** viết `tests/_smoke_server_multiround.py` gửi update cho round 1 → wait round 2 → gửi update round 2 → ... đến round N → assert DONE. Không bắt buộc cho M4 — multi-round verification sẽ ngầm pass khi M4.3 chạy với client thật.

### 7.2 Localhost smoke 5 round (M4.3, sau khi M4.2 merge)

```powershell
# Terminal 1
python server.py --num-rounds 5

# Terminal 2
python client.py --client-id client-0 --shard-id 0 --num-shards 2

# Terminal 3
python client.py --client-id client-1 --shard-id 1 --num-shards 2
```

Kỳ vọng:
- 5 round chạy liên tiếp không stuck, mỗi round ~20s localhost
- `round_log.csv` có 5 row
- Round 1 typically đạt accuracy cao (M3 cho thấy ~98.5%) **nhưng không phải acceptance cứng** — chỉ acceptance là round 5 ≥95%
- Loss/accuracy có **xu hướng cải thiện** qua 5 round (không nhất thiết monotonic — SGD/shuffle/FedAvg có dao động nhẹ)
- Không có **collapse** bất thường (accuracy tụt mạnh nhiều round liên tiếp)
- Client thoát sạch sau round 5 (thấy DONE)

### 7.3 Cross-machine 5 round (M4.4)

Như M3.9 nhưng `--num-rounds 5`. Round wallclock cross-machine kỳ vọng ~25s × 5 = 2 phút.

### 7.4 (Bonus) Full experiment 30 round (M4.5) — **không tính vào M4 acceptance**

M4 đóng khi 5 round localhost + cross-machine pass và log đúng. 30 round là dữ liệu cho **Experiment 1** (so với centralized 30 epoch ở M1), thực hiện sau M4 chính thức done. Không gắn vào M4.6 milestone report.

```powershell
python server.py --num-rounds 30 --experiment-name exp_federated_iid --run-id baseline
# 2 client cross-machine
```

Output → `results/exp_federated_iid/baseline/` sẽ là dataset đầu vào cho phase Experiments + báo cáo cuối kỳ.

## 8. Acceptance criteria

- [ ] 5 round liên tiếp chạy end-to-end không stuck (localhost + cross-machine)
- [ ] `round_log.csv` có **đúng 5 row**, mỗi row đầy đủ cột (accuracy, per-class, timings)
- [ ] `events.csv` có 5 chu kỳ events đầy đủ (5x `round_done`, etc.)
- [ ] **Loss/accuracy có xu hướng cải thiện** qua 5 round (không yêu cầu monotonic — dao động nhẹ là OK)
- [ ] **Không có collapse** bất thường (accuracy tụt mạnh nhiều round liên tiếp)
- [ ] **Accuracy round 5 ≥ 95%** (acceptance cứng duy nhất về metric)
- [ ] Client thoát sạch sau round cuối, không poll vô tận
- [ ] Client exit code = 3 nếu update bị reject (test bằng cách stop server giữa chừng → client gặp lỗi → exit clean)
- [ ] Cross-machine timing: round wallclock relatively stable (~20-25s mỗi round, không có round nào blow up bất thường)

## 9. Rủi ro & lưu ý

1. **State transition bug ở client**: nếu logic `last_completed_round` sai (off-by-one, race), client có thể skip round hoặc gửi update của round cũ → server reject `stale_round`. Test sẽ catch (events.csv sẽ có `update_rejected: stale_round`).

2. **Server bug khi advance round**: nếu `received_updates` không clear đúng, round 2 có thể aggregate luôn vì lock buffer cũ. (Đọc code M3 → đã có `s.received_updates = {}` trong nhánh advance). Smoke 2-3 round local sẽ catch.

3. **Memory leak qua nhiều round**: Mỗi round tạo optimizer + loader + serialize_state_dict. Nếu reference không free, RAM tăng dần. 5 round không đáng kể; 30 round có thể đáng quan tâm. Acceptable cho M4.

4. **Network blip qua nhiều round**: 5 round = 5x `GetGlobalModel` (5x download 1.6MB) + 5x `SubmitUpdate` (5x upload 1.6MB) = ~16MB tổng. Trên LAN ổn. Không có retry logic — 1 RPC failure kill client. M4 chấp nhận; M7 fault tolerance sẽ add retry.

5. **Eval CPU bottleneck**: server eval ~1s × 5 round = 5s bonus latency. Acceptable. Nếu chạy 30 round = 30s — vẫn OK.

6. **Race khi 2 client submit gần đồng thời nhiều round liên tiếp**: `_log_lock` ở M3 đã giải quyết events.csv race. State lock vẫn giữ tốt.

## 10. Sau M4 xong

Update `Report/milestone_report.md` với M4 section:
- Tổng quan: M4 → ✅ Done
- Section M4 với cùng cấu trúc (mục tiêu / công việc / verified / acceptance / vấn đề)
- Snapshot 5 round accuracy curve (tăng dần qua các round)
- Cross-machine timing trung bình per-round
- (Nếu có) baseline 30 round data → noted cho Exp 1

M5 sẽ rất dễ: chỉ cần đổi client gọi `partition_noniid_pathological` thay vì `partition_iid` (đã có sẵn ở `data_partition.py`).

---

## 11. Workflow cho M4 (giản lược so với M3)

Vì scope hẹp hơn, chỉ có 1 feature branch của Máy 2:

```text
dev
  └── feature/m4-client-multiround (Máy 2)
       → PR review từ Máy 1 → merge dev
       → Smoke test trên dev → update report
```

Quy trình cụ thể (lặp lại như M3):
1. **Máy 2**: `git pull dev` → branch `feature/m4-client-multiround` → code → push → mở PR
2. **Máy 1**: review PR (đọc diff, có thể pull về test) → comment / approve → merge
3. **Máy 1**: chạy localhost smoke trên dev → fix nếu có bug
4. **Cả hai**: cross-machine 5 round → cross-machine 30 round (optional)
5. **Máy 1**: append M4 section vào `Report/milestone_report.md`, commit trực tiếp dev

Branch sẽ xóa sau merge (như M3).
