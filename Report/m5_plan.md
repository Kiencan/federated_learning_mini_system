# M5 Plan — Non-IID Partition (Pathological Split)

> Plan chi tiết cho Milestone 5. Tham khảo: [plan.md](../plan.md), [m4_plan.md](m4_plan.md), [milestone_report.md](milestone_report.md).

---

## 1. Mục tiêu

Thêm tùy chọn **Non-IID pathological split** (Client 0: digits 0-4 | Client 1: digits 5-9) vào client.py. Verify FedAvg vẫn aggregate đúng nhưng accuracy + per-class accuracy sẽ **giảm đáng kể** so với IID. Đây là **data point quan trọng nhất** cho **Experiment 2 (IID vs Non-IID)** trong báo cáo cuối kỳ.

Mục tiêu chính KHÔNG phải đạt accuracy cao — mà là **observe + đo lường được hiện tượng Non-IID**.

## 2. Scope

**IN — phải có:**
- Client thêm CLI flag `--data-split iid|noniid` (override config.yaml)
- Khi `noniid`, dispatch sang `partition_noniid_pathological()` (đã có sẵn ở `data_partition.py`)
- Validation: `noniid` chỉ hỗ trợ `num_shards=2` (per spec) — friendly error nếu sai
- Test 5 round Non-IID (localhost + cross-machine)
- **Compare quantitative IID vs Non-IID**: accuracy curve, per-class accuracy, convergence behavior
- Separate output folder: `exp_federated_noniid_smoke/<run_id>/` (server `--experiment-name`)

**OUT — KHÔNG làm ở M5:**
- WAIT_TIMEOUT / async aggregation (M6)
- Straggler simulation (M7)
- Fault tolerance (M7)
- Custom Non-IID schemes (chỉ pathological cho M5)
- Mid-experiment data_split switch — split fixed cho cả run

## 3. Cấu hình cho M5

Mở rộng `config.yaml` (đã có sẵn key `data_split`):

```yaml
data_split: "iid"        # iid | noniid — client đọc và dispatch
# (giữ nguyên rest)
```

Nếu user CLI `--data-split noniid` → override config.

**Smoke run M5 commands** (lưu ý 2 client cùng `--data-split noniid`):

```powershell
# Server
python server.py --num-rounds 5 --experiment-name exp_federated_noniid_smoke --run-id m5_local

# Client 0
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --data-split noniid

# Client 1
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --data-split noniid
```

> **Lưu ý quan trọng:** Server không biết clients đang dùng IID hay Non-IID — chỉ aggregate weights. User phải đảm bảo cả 2 client cùng `--data-split`. Nếu lệch (1 IID + 1 Non-IID), kết quả vô nghĩa nhưng server không phát hiện. **Mismatch validation defer cho M6+** nếu cần.

## 4. Design decisions

| Quyết định | Lựa chọn | Lý do |
|---|---|---|
| Thêm `--data-split` flag client | CLI > config.yaml | Đã có pattern từ M3/M4; người dùng dễ chuyển giữa IID/Non-IID |
| Dispatch ở đâu | Trong client `run_federated`, ngay sau `load_mnist()` | Thay 1 dòng `partition_iid(...)` thành `if/else` |
| Validation `noniid` requires `num_shards=2` | Raise `ValueError` rõ ràng nếu sai | `partition_noniid_pathological` đã raise nhưng client wrap với message rõ hơn |
| Server có biết Non-IID không? | KHÔNG (data-agnostic) | FedAvg server-side không quan tâm partition — đúng design federated |
| Server `--experiment-name` cho Non-IID | User pass `exp_federated_noniid_smoke` | Tránh override accidentally `exp_federated_iid_smoke` |
| Comparison IID vs Non-IID | Manual analysis CSV side-by-side | Tự động compare là Exp 2 phase, không phải M5 |

## 5. Subtask breakdown

| # | Subtask | File | Owner | Branch | Estimate |
|---|---|---|---|---|---|
| M5.1 | Verify server không cần đổi (đọc code, confirm data-agnostic) | server.py (no change) | **Máy 1** | — | 5 min |
| M5.2 | Client `--data-split` flag + dispatch + validation | client.py | **Máy 2** | `feature/m5-client-noniid` | 20 min |
| M5.3 | Localhost smoke 5 round Non-IID | (run) | **Máy 1** | — (sau merge) | 10 min |
| M5.4 | Cross-machine 5 round Non-IID | (run) | **Cả 2** | — | 10 min |
| M5.5 | Compare IID vs Non-IID (CSV side-by-side, per-class table) | analysis | **Máy 1** | — | 20 min |
| M5.6 | Update `Report/milestone_report.md` với M5 section + comparison table | report | **Máy 1** | direct commit dev | 20 min |

**Tổng:** ~1.5 giờ. Scope hẹp nhất từ trước đến giờ.

## 6. Client implementation (M5.2) — pseudocode

Trong `run_federated`, thay đoạn setup data hiện tại:

```python
# HIỆN TẠI (M4):
train_set, _ = load_mnist(data_root=cfg.get("data_root", "./data"))
shards = partition_iid(train_set, num_clients=args.num_shards, seed=cfg["seed"])
shard = shards[args.shard_id]
```

bằng:

```python
# M5:
train_set, _ = load_mnist(data_root=cfg.get("data_root", "./data"))

data_split = cfg.get("data_split", "iid")
if data_split == "noniid":
    if args.num_shards != 2:
        print(f"[client {client_id}] ERROR: noniid yêu cầu --num-shards 2, got {args.num_shards}")
        sys.exit(4)
    shards = partition_noniid_pathological(train_set, num_clients=2)
    print(f"[client {client_id}] split=noniid (pathological): shard {args.shard_id} = digits "
          f"{'0-4' if args.shard_id == 0 else '5-9'}")
elif data_split == "iid":
    shards = partition_iid(train_set, num_clients=args.num_shards, seed=cfg["seed"])
    print(f"[client {client_id}] split=iid: shard {args.shard_id}/{args.num_shards}")
else:
    print(f"[client {client_id}] ERROR: unknown data_split={data_split!r}, expected iid|noniid")
    sys.exit(4)

shard = shards[args.shard_id]
```

CLI parser thêm:

```python
parser.add_argument(
    "--data-split",
    choices=["iid", "noniid"],
    default=None,
    help="data partition mode (override config.yaml data_split)",
)
```

`cli_overrides()` trong `run_context.py` cần map thêm:

```python
"data_split": args.data_split,
```

→ Nếu CLI không passed (None), config value giữ nguyên; nếu passed, override.

> Lưu ý: kiểm tra `build_cli_parser` ở `run_context.py` đã có `--data-split` chưa. **Nếu chưa**, thêm vào parser chung hoặc add ở client.py riêng — Máy 2 quyết định khi implement (tránh duplication nếu sau này server cũng cần).

## 7. Test plan

### 7.1 Localhost smoke 5 round Non-IID (M5.3)

```powershell
# Terminal 1: server (note experiment name khác)
python server.py --num-rounds 5 --experiment-name exp_federated_noniid_smoke --run-id m5_local

# Terminal 2: client 0 (digits 0-4)
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --data-split noniid

# Terminal 3: client 1 (digits 5-9)
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --data-split noniid
```

Output: `results/exp_federated_noniid_smoke/m5_local/{round_log.csv, events.csv, run_meta.json}`

Kỳ vọng (xem §9 risk):
- 5 round chạy không stuck
- **Accuracy thấp hơn IID đáng kể** (kỳ vọng ~80-90% vs 99%+ IID)
- **Per-class accuracy lệch**: lớp gần ranh giới (4, 5) có thể thấp; toàn bộ vẫn ≥ 50% (global model ít nhất học được pattern chung)
- Hội tụ chậm hơn / dao động mạnh hơn giữa các round

### 7.2 Cross-machine 5 round Non-IID (M5.4)

Same setup nhưng Máy 1 server + client-0, Máy 2 client-1 (`--server-addr 192.168.2.30:50051`).

### 7.3 Validation test (manual, optional)

```powershell
# Test num_shards != 2 với noniid
python client.py --client-id client-0 --shard-id 0 --num-shards 3 --data-split noniid
# Kỳ vọng: exit code 4 với message rõ ràng

# Test unknown data_split
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --data-split foo
# Kỳ vọng: argparse rejects với `choices=[iid, noniid]` validation
```

## 8. Acceptance criteria

- [ ] 5 round Non-IID chạy end-to-end không stuck (localhost + cross-machine)
- [ ] `round_log.csv` đủ 5 row, output đúng folder `exp_federated_noniid_smoke/`
- [ ] **Client-0 nhận data chỉ digits 0-4, Client-1 chỉ 5-9** (verified qua log size hoặc print)
- [ ] **Accuracy round 5 ≥ 70%** (acceptance NỚI hơn IID — Non-IID khó hội tụ)
- [ ] **Per-class accuracy có lệch rõ rệt** so với IID (verify qua compare)
- [ ] Loss giảm qua các round (cải thiện có giảm, không nhất thiết bằng IID rate)
- [ ] Client thoát sạch sau round cuối
- [ ] Validation: `noniid` + `num_shards != 2` → exit code 4 với message rõ
- [ ] **Comparison table IID vs Non-IID** xuất hiện trong M5 section của milestone_report

## 9. Rủi ro & finding kỳ vọng

**Đây là milestone đầu tiên ta KỲ VỌNG kết quả "kém hơn" có chủ đích.**

1. **Accuracy giảm mạnh là dấu hiệu HEALTHY**, không phải bug. Pathological Non-IID là worst-case scenario:
   - Client-0 không bao giờ thấy digit 5-9 → local model bias mạnh về 0-4
   - Client-1 ngược lại
   - FedAvg average 2 model bias → global model dao động, hội tụ chậm
   - Kỳ vọng: ~80-90% round 5 (so với 99.2% IID)
   - Nếu accuracy < 50% → có thể bug serialization hoặc partition; verify

2. **Per-class accuracy mất cân bằng** là **finding chính** cho báo cáo:
   - Lớp transition (4, 5) khó hội tụ vì rơi vào ranh giới mỗi client
   - Một số lớp có thể tụt < 70% trong khi IID >98%
   - Vẽ bar chart per-class IID vs Non-IID = visual quan trọng cho Exp 2

3. **Hội tụ dao động** giữa các round (accuracy có thể tăng giảm xen kẽ):
   - Bình thường với pathological split
   - Acceptance đã nới: chỉ cần round 5 ≥ 70%, không yêu cầu monotonic

4. **Aggregation/Eval timing không đổi** so với IID (data partition không ảnh hưởng compute server-side).

5. **Train loss client-side có thể thấp** (vì mỗi client overfit 5 lớp local rất nhanh) — nhưng KHÔNG phản ánh global model performance. Đây là phenomenon "client drift" của FedAvg trong Non-IID.

## 10. Sau M5 xong

Update `Report/milestone_report.md`:
- Overview: M5 → ✅ Done
- Section M5 với **comparison table IID vs Non-IID**:
  - Accuracy curve 5 round (2 cột)
  - Per-class accuracy round 5 (10 lớp × 2 cột)
  - Round wallclock (kỳ vọng giống nhau)
- Bước tiếp theo → M6 (WAIT_TIMEOUT + dynamic min_clients)

**Sau M5, ta có dữ liệu cho Experiment 2** — quan trọng nhất của báo cáo về Data Heterogeneity (§7.5 ytuong.md).

---

## 11. Workflow (giản lược như M4)

```text
dev
  └── feature/m5-client-noniid (Máy 2)
       → PR review → merge dev → smoke → report
```

Quy trình lặp lại như M4. Branch xóa sau merge.
