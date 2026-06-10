# Report/data — CSV inputs cho analyze.py (tracked)

Thư mục này chứa **các `round_log.csv` tối thiểu** để tái tạo 4 plots + báo cáo
cuối kỳ từ một clean checkout, vì `results/` bị gitignore (run outputs không commit).

## Cấu trúc (giữ nguyên cây như `results/`)

| Path | Dùng cho | Nguồn run |
|---|---|---|
| `exp_centralized/baseline_20ep/round_log.csv` | Exp 1 accuracy | E0.1 Centralized 20 epoch |
| `exp_federated_iid/baseline_20r/round_log.csv` | Exp 1 & 2 accuracy | E0.2 Fed IID 20 round localhost |
| `exp_federated_noniid/baseline_20r/round_log.csv` | Exp 2 accuracy + per-class | E0.3 Fed Non-IID 20 round localhost |
| `exp_federated_iid_smoke/m44_cross/round_log.csv` | Timing breakdown (normal federated) | M4.4 cross-machine |
| `exp_federated_iid_smoke/m74_s1_localhost/round_log.csv` | Exp 3 Straggler S1 (cited) | M7.4 |
| `exp_federated_iid_smoke/m75_s2_v3/round_log.csv` | Exp 3 Straggler S2 (cited) | M7.5 |
| `exp_federated_iid_smoke/m76_f1_v3/{round_log,events}.csv` | Exp 4 Fault tolerance (cited) | M7.6 |

4 file đầu là **input trực tiếp** của `analyze.py`; phần còn lại là **bằng chứng**
cho số liệu Exp 3/4 trích trong `bao_cao_cuoi_ky.md`.

## Tái tạo plots (figures) từ CSV đã commit

```bash
python analyze.py                 # đọc Report/data (mặc định) → Report/figures/*.png
```

## Override để chạy trên run outputs gốc

```bash
python analyze.py --data-root results
```

## Tạo lại CSV từ đầu (chạy lại E0 — cần MNIST + môi trường fedml)

```bash
# E0.1 Centralized
python centralized_train.py --num-rounds 20 --run-id baseline_20ep

# E0.2 Fed IID (server + 2 client localhost, Ctrl+C server sau khi xong)
python server.py --num-rounds 20 --min-clients 2 --wait-timeout 60 \
    --experiment-name exp_federated_iid --run-id baseline_20r
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --server-addr 127.0.0.1:50051
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --server-addr 127.0.0.1:50051

# E0.3 Fed Non-IID (thêm --data-split noniid cho server + 2 client)
python server.py --num-rounds 20 --min-clients 2 --wait-timeout 60 --data-split noniid \
    --experiment-name exp_federated_noniid --run-id baseline_20r
python client.py --client-id client-0 --shard-id 0 --num-shards 2 --data-split noniid --server-addr 127.0.0.1:50051
python client.py --client-id client-1 --shard-id 1 --num-shards 2 --data-split noniid --server-addr 127.0.0.1:50051
```

Sau đó copy các `round_log.csv` từ `results/.../` vào đây, hoặc chạy
`python analyze.py --data-root results` trực tiếp.
