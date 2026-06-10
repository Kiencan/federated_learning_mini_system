"""Phase Experiments — analyze.py (E1).

Đọc round_log.csv của các baseline run + cross-machine timing run, sinh 4 plots
vào Report/figures/ và in bảng metrics ra stdout.

Xử lý 3 schema round_log.csv:
  - Centralized:  round_id, train_loss, test_loss, accuracy, epoch_time_sec,
                  cumulative_time_sec, acc_class_0..9
  - Federated M6+: ... round_status, accuracy, ... round_wallclock_sec ...
  - Federated M4:  giống M6+ nhưng KHÔNG có round_status

Mọi schema đều có `accuracy` + `acc_class_0..9` → chuẩn hoá về cùng tập cột.

Phân vai trò data (per experiments_plan.md):
  - Accuracy/convergence: dùng E0 baseline localhost (20 round/epoch).
  - Timing breakdown "normal federated": dùng cross-machine m44_cross / m54_cross.
    KHÔNG dùng m76_f1_v3 (fault scenario, timing bị méo bởi crash/recovery).
"""
from __future__ import annotations

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
# Hằng số + đường dẫn run (khớp results/ thật)
# ============================================================

REPO = Path(__file__).resolve().parent
FIG_DIR = REPO / "Report" / "figures"

MODEL_SIZE_BYTES = 1_689_280  # state_dict serialized, đo từ events.csv
NUM_CLIENTS = 2
MIB = 1024 * 1024

# Accuracy/convergence — E0 baseline localhost
CENTRALIZED = REPO / "results" / "exp_centralized" / "baseline_20ep"
FED_IID = REPO / "results" / "exp_federated_iid" / "baseline_20r"
FED_NONIID = REPO / "results" / "exp_federated_noniid" / "baseline_20r"

# Timing breakdown — cross-machine "normal federated" (KHÔNG dùng fault run)
TIMING_IID = REPO / "results" / "exp_federated_iid_smoke" / "m44_cross"

ACC_CLASS_COLS = [f"acc_class_{i}" for i in range(10)]


# ============================================================
# Load + chuẩn hoá schema
# ============================================================


def load_round_log(run_dir: Path) -> pd.DataFrame:
    """Đọc round_log.csv, detect schema, trả DataFrame đã chuẩn hoá.

    Cột đảm bảo có: round_id, accuracy, acc_class_0..9.
    Cột optional (nếu schema có): round_wallclock_sec, aggregation_time_ms,
    eval_time_ms, epoch_time_sec.
    """
    path = run_dir / "round_log.csv"
    if not path.exists():
        sys.exit(f"[analyze] THIẾU file: {path}")
    df = pd.read_csv(path)
    if "accuracy" not in df.columns:
        sys.exit(f"[analyze] {path} không có cột 'accuracy' — schema lạ")
    return df


def to_minutes_axis(df: pd.DataFrame) -> pd.Series:
    """Trả round_id (federated) hoặc epoch_id (centralized) làm trục x."""
    return df["round_id"]


# ============================================================
# Plot 1 — Accuracy per round/epoch
# ============================================================


def plot_accuracy_per_round(cen: pd.DataFrame, iid: pd.DataFrame, noniid: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(iid["round_id"], iid["accuracy"], "o-", label="Federated IID", color="#2563eb")
    ax.plot(noniid["round_id"], noniid["accuracy"], "s-", label="Federated Non-IID", color="#dc2626")
    ax.plot(
        cen["round_id"], cen["accuracy"], "^--",
        label="Centralized (baseline gom data)", color="#16a34a", alpha=0.8,
    )
    ax.set_xlabel("Round (federated) / Epoch (centralized)")
    ax.set_ylabel("Test accuracy")
    ax.set_title("Accuracy theo round — IID vs Non-IID vs Centralized")
    ax.set_ylim(0.90, 1.0)
    ax.grid(True, alpha=0.3)
    ax.legend(loc="lower right")
    fig.tight_layout()
    out = FIG_DIR / "accuracy_per_round.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"  ✓ {out.name}")


# ============================================================
# Plot 2 — Round time breakdown (coarse, normal federated)
# ============================================================


def plot_round_time_breakdown(timing: pd.DataFrame, label: str) -> None:
    """Stacked bar coarse: aggregation + eval + other_round_time.

    other_round_time_ms = round_wallclock_sec*1000 - agg - eval.
    Tên trung tính: gồm client train + download/upload + polling + wait.
    Chỉ mô tả NORMAL federated timing — fault-timeout phân tích riêng ở Exp 4.
    """
    df = timing.copy()
    agg = df["aggregation_time_ms"]
    ev = df["eval_time_ms"]
    other = (df["round_wallclock_sec"] * 1000) - agg - ev
    other = other.clip(lower=0)  # tránh âm do jitter đo lường

    rounds = df["round_id"]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(rounds, other / 1000, label="other (train+comm+wait)", color="#94a3b8")
    ax.bar(rounds, ev / 1000, bottom=other / 1000, label="evaluation", color="#f59e0b")
    ax.bar(
        rounds, agg / 1000, bottom=(other + ev) / 1000,
        label="aggregation", color="#7c3aed",
    )
    ax.set_xlabel("Round")
    ax.set_ylabel("Thời gian (giây)")
    ax.set_title(f"Round time breakdown (coarse) — {label} cross-machine\n(round 1 gồm client cold start)")
    ax.set_xticks(rounds)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out = FIG_DIR / "round_time_breakdown.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"  ✓ {out.name}")


# ============================================================
# Plot 3 — Communication overhead (MiB cumulative)
# ============================================================


def plot_communication_overhead(num_rounds: int) -> None:
    per_round_mib = MODEL_SIZE_BYTES * 2 * NUM_CLIENTS / MIB  # down+up × clients
    rounds = list(range(1, num_rounds + 1))
    cumulative = [per_round_mib * r for r in rounds]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(rounds, cumulative, "o-", color="#0891b2")
    ax.fill_between(rounds, cumulative, alpha=0.15, color="#0891b2")
    ax.set_xlabel("Round")
    ax.set_ylabel("Cumulative communication (MiB)")
    ax.set_title(
        f"Communication overhead — {per_round_mib:.2f} MiB/round "
        f"({NUM_CLIENTS} client × 2 chiều × {MODEL_SIZE_BYTES/MIB:.3f} MiB)"
    )
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = FIG_DIR / "communication_overhead.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"  ✓ {out.name}  ({per_round_mib:.2f} MiB/round, {cumulative[-1]:.1f} MiB @ {num_rounds}r)")


# ============================================================
# Plot 4 — Per-class accuracy IID vs Non-IID (round cuối)
# ============================================================


def plot_per_class_iid_vs_noniid(iid: pd.DataFrame, noniid: pd.DataFrame) -> None:
    iid_last = iid.iloc[-1][ACC_CLASS_COLS].astype(float).values
    non_last = noniid.iloc[-1][ACC_CLASS_COLS].astype(float).values
    classes = list(range(10))
    width = 0.38

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar([c - width / 2 for c in classes], iid_last, width, label="IID", color="#2563eb")
    ax.bar([c + width / 2 for c in classes], non_last, width, label="Non-IID", color="#dc2626")
    ax.set_xlabel("Digit class")
    ax.set_ylabel("Per-class accuracy (round cuối)")
    ax.set_title("Per-class accuracy — IID vs Non-IID (round cuối)")
    ax.set_xticks(classes)
    ax.set_ylim(0.90, 1.0)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    out = FIG_DIR / "per_class_accuracy_iid_vs_noniid.png"
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"  ✓ {out.name}")


# ============================================================
# Metrics table
# ============================================================


def rounds_to_threshold(df: pd.DataFrame, thr: float) -> str:
    hit = df[df["accuracy"] >= thr]
    if hit.empty:
        return f">{int(df['round_id'].max())}"
    return str(int(hit.iloc[0]["round_id"]))


def avg_acc_first_n(df: pd.DataFrame, n: int = 5) -> float:
    return df[df["round_id"] <= n]["accuracy"].mean()


def print_metrics_table(cen, iid, noniid, num_rounds: int) -> None:
    per_round_mib = MODEL_SIZE_BYTES * 2 * NUM_CLIENTS / MIB
    total_mib = per_round_mib * num_rounds

    rows = [
        ("Centralized", cen, None),
        ("Federated IID", iid, total_mib),
        ("Federated Non-IID", noniid, total_mib),
    ]
    print("\n" + "=" * 78)
    print(f"{'Setup':<20}{'final_acc':>10}{'avg_first5':>12}{'r→98%':>8}{'comm MiB':>12}")
    print("-" * 78)
    for name, df, comm in rows:
        final_acc = df.iloc[-1]["accuracy"]
        a5 = avg_acc_first_n(df, 5)
        r98 = rounds_to_threshold(df, 0.98)
        comm_s = f"{comm:.1f}" if comm is not None else "—"
        print(f"{name:<20}{final_acc:>10.4f}{a5:>12.4f}{r98:>8}{comm_s:>12}")
    print("=" * 78)
    print(f"comm/round = {per_round_mib:.2f} MiB  |  model = {MODEL_SIZE_BYTES/MIB:.3f} MiB × 2 × {NUM_CLIENTS} client")


# ============================================================
# Main
# ============================================================


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[analyze] figures → {FIG_DIR}")

    cen = load_round_log(CENTRALIZED)
    iid = load_round_log(FED_IID)
    noniid = load_round_log(FED_NONIID)
    timing = load_round_log(TIMING_IID)
    num_rounds = int(iid["round_id"].max())

    print("[analyze] sinh plots:")
    plot_accuracy_per_round(cen, iid, noniid)
    plot_round_time_breakdown(timing, label="Fed IID (m44_cross)")
    plot_communication_overhead(num_rounds)
    plot_per_class_iid_vs_noniid(iid, noniid)

    print_metrics_table(cen, iid, noniid, num_rounds)
    print("\n[analyze] done.")


if __name__ == "__main__":
    main()
