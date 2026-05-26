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

**Smoke run M5 commands** (cả **server** lẫn 2 client đều cần `--data-split noniid`):

```powershell
# Server — cần --data-split để snapshot config phản ánh đúng Non-IID
python server.py --num-rounds 5 --data-split noniid --experiment-name exp_federated_noniid_smoke --run-id m5_local

# Client 0 (digits 0-4)
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --data-split noniid

# Client 1 (digits 5-9)
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --data-split noniid
```

> **Tại sao server cần `--data-split` dù không dùng để aggregate:** server snapshot `config.yaml` vào `run_dir`. Nếu server không nhận CLI flag, snapshot sẽ ghi `data_split: iid` mặc dù client thực tế chạy Non-IID. Sau này nhìn `results/.../config.yaml` sẽ sai. Server đọc giá trị nhưng KHÔNG dùng để xử lý — chỉ để log.

> **Lưu ý quan trọng:** Server vẫn không validate client `data_split` khớp với mình. User phải đảm bảo cả 2 client + server cùng `--data-split`. Mismatch validation defer cho M6+.

## 4. Design decisions

| Quyết định | Lựa chọn | Lý do |
|---|---|---|
| Thêm `--data-split` flag | Đưa vào `build_cli_parser()` chung ở `run_context.py` → cả 3 script (server, client, centralized) đều nhận | Tránh `args.data_split` AttributeError khi `cli_overrides()` map nó; server snapshot config đúng |
| Dispatch partition ở đâu | Trong client `run_federated`, ngay sau `load_mnist()` | Thay 1 dòng `partition_iid(...)` thành `if/else` |
| Validation `noniid` requires `num_shards=2` | Raise rõ ràng + exit code 4 | `partition_noniid_pathological` đã raise nhưng client wrap với message rõ hơn |
| Validation `0 <= shard_id < num_shards` | Check đầu `run_federated` cho **cả IID lẫn Non-IID** | `shards[shard_id]` văng `IndexError` không thân thiện nếu user sai (vd `--shard-id 2 --num-shards 2`) |
| Server **có dùng** `data_split` không? | KHÔNG để aggregate (data-agnostic), CÓ để snapshot config | FedAvg không quan tâm partition; nhưng `run_dir/config.yaml` cần phản ánh đúng giá trị run thật |
| Server `--experiment-name` cho Non-IID | User pass `exp_federated_noniid_smoke` | Tránh override accidentally folder `exp_federated_iid_smoke` |
| Comparison IID vs Non-IID | Manual analysis CSV side-by-side | Tự động compare là Exp 2 phase, không phải M5 |
| Cùng config cho fair comparison | M5.5 phải dùng IID run với **cùng** `num_rounds`, `local_epochs`, `batch_size`, `lr`, `seed`, 2 clients | M4.4 đã smoke với `num_rounds=5, local_epochs=2, batch=32, lr=0.01, seed=42` — match được; nếu khác phải rerun IID |

## 5. Subtask breakdown

| # | Subtask | File | Owner | Branch | Estimate |
|---|---|---|---|---|---|
| **M5.0** | **Fix `create_run_dir()` snapshot resolved config** (tech debt từ M3 — hiện `shutil.copyfile` copy file gốc, không phản ánh CLI overrides). Sửa thành `yaml.safe_dump(cfg, ...)` để snapshot khớp với run thật. | `run_context.py` | **Máy 1** | `feature/m5-resolved-config-snapshot` | 15 min |
| M5.1 | Verify server không cần đổi business logic (đọc code, confirm data-agnostic) | server.py (no change) | **Máy 1** | — | 5 min |
| M5.2 | (a) Thêm `--data-split` vào `build_cli_parser()` chung. (b) Client dispatch + validation + **class distribution print**. | `run_context.py`, `client.py` | **Máy 2** | `feature/m5-client-noniid` | 25 min |
| M5.3 | Localhost smoke 5 round Non-IID | (run) | **Máy 1** | — (sau merge) | 10 min |
| M5.4 | Cross-machine 5 round Non-IID | (run) | **Cả 2** | — | 10 min |
| M5.5 | Compare IID vs Non-IID (CSV side-by-side, per-class table) | analysis | **Máy 1** | — | 20 min |
| M5.6 | Update `Report/milestone_report.md` với M5 section + comparison table | report | **Máy 1** | direct commit dev | 20 min |

**Tổng:** ~1.75 giờ.

**Thứ tự merge bắt buộc:**

1. **M5.0 trước M5.2** — vì cả 2 đều sửa `run_context.py`. Nếu Máy 2 push M5.2 trước, sẽ có conflict + Máy 2 không có snapshot fix để verify.
2. Máy 1 push `feature/m5-resolved-config-snapshot` → merge dev → báo Máy 2 pull → Máy 2 bắt đầu `feature/m5-client-noniid`.

## 6. Client implementation (M5.2) — pseudocode

### 6.1 `run_context.py` — 2 thay đổi

**(a) M5.0 (Máy 1, prereq):** Fix `create_run_dir()` snapshot **resolved config** thay vì copy file gốc.

```python
# HIỆN TẠI (M3 tech debt):
snapshot = run_dir / "config.yaml"
if Path(config_path).resolve() != snapshot.resolve():
    shutil.copyfile(config_path, snapshot)   # ← copy file GỐC, mất CLI overrides

# SỬA THÀNH:
snapshot = run_dir / "config.yaml"
with snapshot.open("w", encoding="utf-8") as f:
    yaml.safe_dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
```

Verify sau M5.0 merge: chạy bất kỳ script với CLI override (vd `python server.py --num-rounds 99 --run-id test_snapshot`) → `cat results/.../test_snapshot/config.yaml` phải thấy `num_rounds: 99`, không phải `30` (config gốc).

`shutil` import có thể remove (không còn dùng).

**(b) M5.2 (Máy 2):** Thêm `--data-split` vào shared parser để **server + client + centralized đều nhận**:

```python
# Trong build_cli_parser() ở run_context.py
parser.add_argument(
    "--data-split",
    choices=["iid", "noniid"],
    default=None,
    help="data partition mode (override config.yaml data_split). "
         "Server: chỉ snapshot vào config; Client: dispatch partition function.",
)

# Trong cli_overrides()
def cli_overrides(args):
    return {
        # ... existing keys ...
        "data_split": args.data_split,
    }
```

→ Vì flag đã ở parser chung, `args.data_split` luôn tồn tại (defaults None) → an toàn cho mọi script.

**Lưu ý:** M5.2 cần làm SAU khi M5.0 merge (cả 2 đều sửa `run_context.py`, tránh conflict). Máy 2 pull dev mới nhất trước khi bắt đầu branch.

### 6.2 `client.py` — dispatch + validation

Thay đoạn setup data hiện tại:

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
        print(f"[client {client_id}] ERROR: noniid requires --num-shards 2, got {args.num_shards}")
        sys.exit(4)
    shards = partition_noniid_pathological(train_set, num_clients=2)
    digit_range = "0-4" if args.shard_id == 0 else "5-9"
    print(f"[client {client_id}] split=noniid (pathological): "
          f"shard {args.shard_id} = digits {digit_range}")
elif data_split == "iid":
    shards = partition_iid(train_set, num_clients=args.num_shards, seed=cfg["seed"])
    print(f"[client {client_id}] split=iid: shard {args.shard_id}/{args.num_shards}")
else:
    print(f"[client {client_id}] ERROR: unknown data_split={data_split!r}, expected iid|noniid")
    sys.exit(4)

# Validation cho CẢ IID lẫn Non-IID: shard_id phải trong khoảng hợp lệ
if not (0 <= args.shard_id < len(shards)):
    print(f"[client {client_id}] ERROR: --shard-id {args.shard_id} out of range "
          f"[0, {len(shards) - 1}] (split={data_split}, num_shards={args.num_shards})")
    sys.exit(4)

shard = shards[args.shard_id]

# In class distribution THỰC TẾ (không phải hardcoded label) — hữu ích debug
from collections import Counter
labels = [int(train_set.targets[i]) for i in shard.indices]
dist = dict(sorted(Counter(labels).items()))
print(f"[client {client_id}] shard size={len(shard)} class_distribution={dist}")
```

→ `--data-split` flag được pickup từ shared `build_cli_parser` (không thêm riêng ở client).

### 6.3 Validation matrix

| `data_split` | `num_shards` | `shard_id` | Kết quả |
|---|---|---|---|
| `iid` | bất kỳ ≥ 1 | hợp lệ | ✓ |
| `iid` | 2 | 2 (vd) | exit 4 "out of range" |
| `noniid` | 2 | 0 hoặc 1 | ✓ |
| `noniid` | 3 | bất kỳ | exit 4 "noniid requires --num-shards 2" |
| `foo` | bất kỳ | bất kỳ | exit 4 "unknown data_split" (hoặc argparse `choices=` reject sớm) |

## 7. Test plan

### 7.1 Localhost smoke 5 round Non-IID (M5.3)

```powershell
# Terminal 1: server — phải có --data-split noniid để snapshot config đúng
python server.py --num-rounds 5 --data-split noniid --experiment-name exp_federated_noniid_smoke --run-id m5_local

# Terminal 2: client 0 (digits 0-4)
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --data-split noniid

# Terminal 3: client 1 (digits 5-9)
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --data-split noniid
```

Output: `results/exp_federated_noniid_smoke/m5_local/{round_log.csv, events.csv, run_meta.json, config.yaml}`

Verify ngay sau khi run xong:
```powershell
# Snapshot phải khớp với CLI
type results\exp_federated_noniid_smoke\m5_local\config.yaml
# Phải thấy: data_split: noniid (không phải iid)

# Class distribution phải khớp với pathological split
# Trong console output mỗi client: client-0 thấy {0..4}, client-1 thấy {5..9}
```

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
- [ ] **Client-0 nhận data chỉ digits 0-4, Client-1 chỉ 5-9** — verified qua `class_distribution=...` print của client (in giá trị Counter thực tế, không phải hardcoded label). Client-0 phải in `{0: ~5923, 1: ~6742, 2: ~5958, 3: ~6131, 4: ~5842}` (số xấp xỉ MNIST), client-1 in các keys 5-9.
- [ ] **Accuracy round 5 ≥ 70%** (acceptance NỚI hơn IID — Non-IID khó hội tụ). Nếu <70% nhưng ≥50%, xem §9 risk 1 trước khi kết luận bug.
- [ ] **Per-class accuracy được log và so sánh** với IID baseline. Ghi nhận chênh lệch nếu có; KHÔNG fail M5 nếu pattern lệch không khớp expectation cụ thể (4, 5 thấp) — depend on seed/hyperparameter.
- [ ] Loss giảm qua các round (cải thiện có giảm, không nhất thiết bằng IID rate, có thể dao động)
- [ ] Client thoát sạch sau round cuối
- [ ] Validation: `noniid` + `num_shards != 2` → exit code 4 với message rõ
- [ ] Validation: `shard_id` ngoài range → exit code 4 (cả IID lẫn Non-IID)
- [ ] Server snapshot `config.yaml` ghi đúng `data_split: noniid` (verify bằng `cat results/.../config.yaml`)
- [ ] **Comparison table IID vs Non-IID** xuất hiện trong M5 section, **dùng IID run cùng cấu hình** (xem §10)

## 9. Rủi ro & finding kỳ vọng

**Đây là milestone đầu tiên ta KỲ VỌNG kết quả "kém hơn" có chủ đích.**

1. **Accuracy giảm mạnh là dấu hiệu HEALTHY**, không phải bug. Pathological Non-IID là worst-case scenario:
   - Client-0 không bao giờ thấy digit 5-9 → local model bias mạnh về 0-4
   - Client-1 ngược lại
   - FedAvg average 2 model bias → global model dao động, hội tụ chậm
   - Kỳ vọng: ~80-90% round 5 (so với 99.2% IID)
   
   **Quy trình debug nếu accuracy thấp hơn kỳ vọng:**
   - **< 50%:** nghi bug nghiêm trọng. Verify partition (in `len(shard)` + class distribution), verify state_dict serialization, verify events.csv không có reject lạ. Có thể là model bị reset, FedAvg bị bypass, hoặc partition trả empty.
   - **50% ≤ acc < 70%:** **chưa nghi bug ngay**. Kiểm tra: (a) shard size đúng (mỗi shard ~30k), (b) per-class accuracy có pattern hợp lý (vd lớp 0-4 cao trên client-0's local view), (c) train_loss có giảm. Nếu system metrics đúng → ghi nhận "Non-IID rất khó hội tụ với config hiện tại" và pass M5. Hyperparameter tuning (lr, local_epochs) là Exp 2 scope, không phải M5.
   - **≥ 70%:** pass acceptance.

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

### Comparison config — MUST match for fair compare

Khi so sánh IID vs Non-IID, **bắt buộc cùng cấu hình** để chênh lệch đến từ partition, không phải hyperparameter:

| Param | M4.4 IID baseline | M5 Non-IID |
|---|---|---|
| `num_rounds` | 5 | 5 |
| `local_epochs` | 2 (default) | 2 |
| `batch_size` | 32 | 32 |
| `lr` | 0.01 | 0.01 |
| `seed` | 42 | 42 |
| `min_clients` | 2 | 2 |
| Num clients | 2 | 2 |
| Setup | Cross-machine (Máy 1 + Máy 2) | Cross-machine (Máy 1 + Máy 2) |

**M4.4 đã chạy đúng config trên** → có thể tái sử dụng `results/exp_federated_iid_smoke/m44_cross/` làm IID baseline. **Không cần rerun IID** nếu Non-IID dùng cùng config.

Nếu vì lý do nào đó M5 phải đổi config (vd seed khác): **rerun IID smoke trước** rồi so sánh với run mới đó.

### Update `Report/milestone_report.md`

- Overview: M5 → ✅ Done
- Section M5 với **comparison table IID vs Non-IID**:
  - **Accuracy curve 5 round** (2 cột side-by-side)
  - **Per-class accuracy round 5** (10 lớp × 2 cột) — finding chính
  - **Round wallclock** (kỳ vọng giống nhau ~12.7s cross-machine — verify Non-IID không slow hơn vì compute cost không đổi)
  - **Train loss per client** (lưu ý: Non-IID train_loss có thể RẤT thấp vì overfit 5 lớp local, không phản ánh global model performance — "client drift" phenomenon)
- Discussion: ý nghĩa cho **Experiment 2** của báo cáo cuối kỳ
- Bước tiếp theo → M6 (WAIT_TIMEOUT + dynamic `min_clients=1` mở lại cho fault tolerance)

**Sau M5, ta có dữ liệu cho Experiment 2** — quan trọng nhất của báo cáo về Data Heterogeneity (§7.5 ytuong.md).

---

## 11. Workflow (giản lược như M4)

```text
dev
  └── feature/m5-client-noniid (Máy 2)
       → PR review → merge dev → smoke → report
```

Quy trình lặp lại như M4. Branch xóa sau merge.
