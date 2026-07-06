"""Phase CIFAR-10 — analyze_cifar.py.

So sánh 3 kịch bản benchmark CIFAR-10 (xem Report/cifar10_plan.md):
  - B1  exp_cifar_centralized      — train thuần 1 máy (baseline tốc độ)
  - B2  exp_cifar_fed_1machine     — federated, server+2 client localhost
  - B3  exp_cifar_fed_2machine     — federated, 2 máy qua Ethernet (comm thật)

Sinh 3 hình vào Report/figures/ + in bảng metrics ra stdout:
  1. cifar_accuracy_per_round.png     — accuracy theo round: B1 vs B2 vs B3
  2. cifar_round_time_breakdown.png   — compute vs communication vs aggregate
  3. cifar_communication_overhead.png — download/round localhost (B2) vs Ethernet (B3)

Xử lý 2 schema round_log.csv:
  - Centralized (B1): round_id, train_loss, test_loss, accuracy, epoch_time_sec,
                      cumulative_time_sec, acc_class_0..9
  - Federated (B2/B3): round_id, num_clients_received, round_status, accuracy,
                      test_loss, ..., round_wallclock_sec, model_bytes,
                      client_{0,1}_download_ms, client_{0,1}_train_ms

Communication: dùng client_*_download_ms từ round_log (server→client). Upload
KHÔNG có trong round_log (chỉ ở stdout client); plan xấp xỉ upload≈download vì
payload model_bytes đối xứng, nên comm/round ≈ 2×download.

B3 optional: nếu Report/data/exp_cifar_fed_2machine chưa có (Máy 1 chưa push),
script vẫn chạy với B1+B2 và bỏ qua B3.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import matplotlib

matplotlib.use("Agg")  # non-interactive, chỉ ghi file
import matplotlib.pyplot as plt
import pandas as pd

# ============================================================
# Đường dẫn + cấu hình run
# ============================================================

REPO = Path(__file__).resolve().parent
FIG_DIR = REPO / "Report" / "figures"
DEFAULT_DATA_ROOT = REPO / "Report" / "data"

# Đường dẫn tương đối dưới data_root (giữ cấu trúc results/ gốc).
# run_id mặc định m2 (B1/B2 chạy Máy 2) / m1_rv2 (B3 server Máy 1, có rendezvous).
# B3 dùng run rendezvous (round-1 sạch); B3 cũ "m1" (no-rv) giữ lại để đối chiếu before/after.
REL_B1 = Path("exp_cifar_centralized") / "m2"
REL_B2 = Path("exp_cifar_fed_1machine") / "m2"
REL_B3 = Path("exp_cifar_fed_2machine") / "m1_rv2"

ACC_CLASS_COLS = [f"acc_class_{i}" for i in range(10)]
CLIENT_IDS = (0, 1)


# ============================================================
# Load + chuẩn hoá
# ============================================================


def load_round_log(run_dir: Path) -> pd.DataFrame | None:
    """Đọc round_log.csv. Trả None nếu thiếu (run optional chưa có)."""
    path = run_dir / "round_log.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if "accuracy" not in df.columns:
        sys.exit(f"[analyze_cifar] {path} không có cột 'accuracy' — schema lạ")
    return df


def is_federated(df: pd.DataFrame) -> bool:
    return "round_wallclock_sec" in df.columns


def accuracy_curve(df: pd.DataFrame) -> pd.DataFrame:
    """(round_id, accuracy) đã bỏ round skipped (accuracy NaN)."""
    out = df[["round_id", "accuracy"]].dropna(subset=["accuracy"])
    return out.reset_index(drop=True)


def federated_timing(df: pd.DataFrame) -> dict[str, float]:
    """Trung bình timing/round trên các round 'ok' (bỏ skipped).

    download_ms/train_ms lấy MEAN qua 2 client (mỗi round). Comm/round xấp xỉ
    2×download (download + upload đối xứng).
    """
    if "round_status" in df.columns:
        ok = df[df["round_status"] == "ok"].copy()
    else:
        ok = df.dropna(subset=["accuracy"]).copy()

    dl_cols = [f"client_{i}_download_ms" for i in CLIENT_IDS]
    tr_cols = [f"client_{i}_train_ms" for i in CLIENT_IDS]

    avg_download = ok[dl_cols].mean().mean()
    avg_train = ok[tr_cols].mean().mean()
    avg_agg = ok["aggregation_time_ms"].mean() if "aggregation_time_ms" in ok else 0.0
    avg_eval = ok["eval_time_ms"].mean() if "eval_time_ms" in ok else 0.0
    avg_wall = ok["round_wallclock_sec"].mean() * 1000.0
    model_bytes = ok["model_bytes"].iloc[0] if "model_bytes" in ok else float("nan")

    return {
        "avg_download_ms": float(avg_download),
        "avg_comm_ms": float(2 * avg_download),  # download + upload (xấp xỉ)
        "avg_train_ms": float(avg_train),
        "avg_agg_ms": float(avg_agg),
        "avg_eval_ms": float(avg_eval),
        "avg_wallclock_ms": float(avg_wall),
        "model_bytes": float(model_bytes),
        "final_acc": float(ok["accuracy"].iloc[-1]),
        "best_acc": float(ok["accuracy"].max()),
        "num_rounds": int(len(ok)),
    }


def centralized_summary(df: pd.DataFrame) -> dict[str, float]:
    return {
        "avg_epoch_ms": float(df["epoch_time_sec"].mean() * 1000.0),
        "final_acc": float(df["accuracy"].iloc[-1]),
        "best_acc": float(df["accuracy"].max()),
        "num_rounds": int(len(df)),
    }


# ============================================================
# Plots
# ============================================================


def plot_accuracy(scenarios: dict[str, pd.DataFrame]) -> None:
    plt.figure(figsize=(8, 5))
    styles = {"B1 Centralized": "o-", "B2 Fed 1 máy": "s-", "B3 Fed 2 máy": "^-"}
    for label, df in scenarios.items():
        curve = accuracy_curve(df)
        plt.plot(curve["round_id"], curve["accuracy"] * 100,
                 styles.get(label, "o-"), label=label, markersize=4)
    plt.xlabel("Round / Epoch")
    plt.ylabel("Test accuracy (%)")
    plt.title("CIFAR-10 — Accuracy hội tụ theo round")
    plt.legend()
    plt.grid(True, alpha=0.3)
    out = FIG_DIR / "cifar_accuracy_per_round.png"
    plt.tight_layout()
    plt.savefig(out, dpi=120)
    plt.close()
    print(f"[fig] {out}")


def plot_round_breakdown(fed: dict[str, dict]) -> None:
    """Stacked bar: compute (train) vs communication vs aggregate+eval / round."""
    labels = list(fed.keys())
    compute = [fed[k]["avg_train_ms"] for k in labels]
    comm = [fed[k]["avg_comm_ms"] for k in labels]
    other = [fed[k]["avg_agg_ms"] + fed[k]["avg_eval_ms"] for k in labels]

    plt.figure(figsize=(7, 5))
    plt.bar(labels, compute, label="Compute (train)", color="#4C72B0")
    plt.bar(labels, comm, bottom=compute, label="Communication (≈2×download)",
            color="#DD8452")
    bottom2 = [c + m for c, m in zip(compute, comm)]
    plt.bar(labels, other, bottom=bottom2, label="Aggregate + eval",
            color="#55A868")
    plt.ylabel("Thời gian trung bình / round (ms)")
    plt.title("CIFAR-10 — Phân rã thời gian mỗi round")
    plt.legend()
    plt.grid(True, axis="y", alpha=0.3)
    out = FIG_DIR / "cifar_round_time_breakdown.png"
    plt.tight_layout()
    plt.savefig(out, dpi=120)
    plt.close()
    print(f"[fig] {out}")


def plot_communication(fed: dict[str, dict]) -> None:
    """Bar so sánh download/round: localhost (B2) vs Ethernet (B3)."""
    labels = list(fed.keys())
    download = [fed[k]["avg_download_ms"] for k in labels]

    plt.figure(figsize=(6, 5))
    bars = plt.bar(labels, download, color=["#8172B3", "#C44E52"][: len(labels)])
    for b, v in zip(bars, download):
        plt.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f} ms",
                 ha="center", va="bottom")
    plt.ylabel("Download model / round (ms)")
    plt.title("CIFAR-10 — Communication: localhost vs Ethernet")
    plt.grid(True, axis="y", alpha=0.3)
    out = FIG_DIR / "cifar_communication_overhead.png"
    plt.tight_layout()
    plt.savefig(out, dpi=120)
    plt.close()
    print(f"[fig] {out}")


# ============================================================
# Main
# ============================================================


def main() -> None:
    p = argparse.ArgumentParser(description="Phân tích benchmark CIFAR-10 B1/B2/B3")
    p.add_argument("--data-root", default=str(DEFAULT_DATA_ROOT),
                   help="thư mục chứa run dirs (default Report/data)")
    args = p.parse_args()
    data_root = Path(args.data_root)
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    b1 = load_round_log(data_root / REL_B1)
    b2 = load_round_log(data_root / REL_B2)
    b3 = load_round_log(data_root / REL_B3)

    if b1 is None or b2 is None:
        sys.exit("[analyze_cifar] THIẾU B1 hoặc B2 — không thể phân tích")

    # --- Accuracy plot (mọi kịch bản có sẵn) ---
    acc_scenarios: dict[str, pd.DataFrame] = {"B1 Centralized": b1, "B2 Fed 1 máy": b2}
    if b3 is not None:
        acc_scenarios["B3 Fed 2 máy"] = b3
    plot_accuracy(acc_scenarios)

    # --- Timing (chỉ federated) ---
    fed_timing: dict[str, dict] = {"B2 localhost": federated_timing(b2)}
    if b3 is not None:
        fed_timing["B3 Ethernet"] = federated_timing(b3)
    plot_round_breakdown(fed_timing)
    plot_communication(fed_timing)

    # --- Bảng metrics ---
    c1 = centralized_summary(b1)
    print("\n" + "=" * 62)
    print("BẢNG SO SÁNH CIFAR-10 (B1 / B2 / B3)")
    print("=" * 62)
    print(f"{'Kịch bản':<16}{'best_acc':>10}{'final_acc':>11}"
          f"{'train_ms':>11}{'comm_ms':>10}")
    print("-" * 62)
    print(f"{'B1 Centralized':<16}{c1['best_acc']*100:>9.2f}%"
          f"{c1['final_acc']*100:>10.2f}%{c1['avg_epoch_ms']:>11.0f}{'—':>10}")
    for label, m in fed_timing.items():
        print(f"{label:<16}{m['best_acc']*100:>9.2f}%"
              f"{m['final_acc']*100:>10.2f}%{m['avg_train_ms']:>11.0f}"
              f"{m['avg_comm_ms']:>10.1f}")
    print("-" * 62)
    if b3 is None:
        print("(B3 chưa có — chạy lại sau khi Máy 1 push round_log.csv)")
    else:
        b2m, b3m = fed_timing["B2 localhost"], fed_timing["B3 Ethernet"]
        ratio = b3m["avg_comm_ms"] / b2m["avg_comm_ms"] if b2m["avg_comm_ms"] else 0
        pct = 100 * b3m["avg_comm_ms"] / b3m["avg_wallclock_ms"] if b3m["avg_wallclock_ms"] else 0
        print(f"Comm Ethernet/localhost = {ratio:.1f}× · "
              f"comm chiếm {pct:.1f}% round time (B3)")
    print("=" * 62)


if __name__ == "__main__":
    main()
