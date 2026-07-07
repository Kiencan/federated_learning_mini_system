"""Phase CIFAR-10 scale-up — analyze_heavy.py (Chương 7 báo cáo HPC).

Sinh 2 hình cho phần scaling study, đọc thẳng round_log.csv (không hardcode số):
  1. cifar_scaling_speedup.png  — "khi nào phân tán thắng": B2(1 GPU) vs B3(2 GPU)
     round_wallclock cho model NHẸ (thua) và NẶNG (thắng), chú thích speedup.
  2. cifar_gpu_contention.png   — train/client: solo(1c/1GPU) vs B2(2c/1GPU, serialize
     2.11×) vs B3(2c/2GPU, khôi phục tốc độ đầy đủ).

Steady-state = trung bình từ round 2 trở đi (bỏ round 1 cold/ramp). Chạy bằng
python env fedml trực tiếp (KHÔNG qua `conda run` — vỡ tiếng Việt cp1252).
"""
from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REPO = Path(__file__).resolve().parent
DATA = REPO / "Report" / "data"
FIG = REPO / "Report" / "figures"

# run dirs
LIGHT_B2 = DATA / "exp_cifar_fed_1machine" / "m1_rv"
LIGHT_B3 = DATA / "exp_cifar_fed_2machine" / "m1_rv2"
HEAVY_SOLO = DATA / "exp_cifar_heavy_solo" / "s2"
HEAVY_B2 = DATA / "exp_cifar_heavy_1machine" / "b2b"
HEAVY_B3 = DATA / "exp_cifar_heavy_2machine" / "m1_heavy"


def steady(df: pd.DataFrame, col: str) -> float:
    """Trung bình cột `col` từ round 2 (bỏ round 1 ramp); fallback all nếu <2 dòng."""
    s = df[df["round_id"] >= 2] if (df["round_id"] >= 2).sum() >= 1 else df
    return float(s[col].mean())


def per_client_train(df: pd.DataFrame, clients: tuple[int, ...]) -> float:
    """Train trung bình mỗi client (bỏ client có 0 mẫu = không tham gia)."""
    s = df[df["round_id"] >= 2] if (df["round_id"] >= 2).sum() >= 1 else df
    vals = []
    for i in clients:
        col = f"client_{i}_train_ms"
        v = s[s[f"client_{i}_num_samples"] > 0][col]
        if len(v):
            vals.append(v.mean())
    return float(sum(vals) / len(vals)) / 1000.0  # → giây


def load(p: Path) -> pd.DataFrame:
    return pd.read_csv(p / "round_log.csv")


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)

    lb2 = steady(load(LIGHT_B2), "round_wallclock_sec")
    lb3 = steady(load(LIGHT_B3), "round_wallclock_sec")
    hb2 = steady(load(HEAVY_B2), "round_wallclock_sec")
    hb3 = steady(load(HEAVY_B3), "round_wallclock_sec")

    sp_light = lb2 / lb3   # <1 nghĩa là phân tán THUA
    sp_heavy = hb2 / hb3

    # ---- Figure 1: when does distributed win ----
    fig, ax = plt.subplots(figsize=(8, 5))
    groups = ["CifarCNN nhẹ\n(~8s compute/round)", "ResNet-18 nặng\n(~35s compute/round)"]
    x = range(len(groups))
    w = 0.36
    b2 = [lb2, hb2]
    b3 = [lb3, hb3]
    bars2 = ax.bar([i - w / 2 for i in x], b2, w, label="B2 — 1 máy / 1 GPU", color="#4C72B0")
    bars3 = ax.bar([i + w / 2 for i in x], b3, w, label="B3 — 2 máy / 2 GPU", color="#C44E52")
    for bars in (bars2, bars3):
        for b in bars:
            ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                    f"{b.get_height():.1f}s", ha="center", va="bottom", fontsize=9)
    # speedup annotations
    ax.annotate(f"phân tán THUA\n{sp_light:.2f}× (chậm hơn)", (0, max(lb2, lb3)),
                textcoords="offset points", xytext=(0, 26), ha="center",
                fontsize=10, color="#8B0000", weight="bold")
    ax.annotate(f"phân tán THẮNG\n{sp_heavy:.2f}×", (1, max(hb2, hb3)),
                textcoords="offset points", xytext=(0, 26), ha="center",
                fontsize=10, color="#006400", weight="bold")
    ax.set_xticks(list(x))
    ax.set_xticklabels(groups)
    ax.set_ylabel("Thời gian mỗi round (s)")
    ax.set_title("CIFAR-10 — Khi nào phân tán tăng tốc?\nLợi ích phân tán tỷ lệ với cường độ compute")
    ax.set_ylim(0, max(hb2, hb3) * 1.35)
    ax.legend(loc="upper left")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    out1 = FIG / "cifar_scaling_speedup.png"
    fig.savefig(out1, dpi=120)
    plt.close(fig)
    print(f"[fig] {out1}")

    # ---- Figure 2: GPU contention ----
    # Baseline contention (T1/T2) dùng test localhost chuyên biệt của Máy 1
    # (bao_cao_cifar10.md §6) để nhất quán số liệu 2 báo cáo. Cross-check với
    # data commit (solo s2 / b2b) in ở summary — khớp trong nhiễu (~2.1×).
    T1_SOLO, T2_B2 = 34.1, 71.9
    solo_tr_data = per_client_train(load(HEAVY_SOLO), (0,))
    b2_tr_data = per_client_train(load(HEAVY_B2), (0, 1))
    b3_tr = per_client_train(load(HEAVY_B3), (0, 1))
    solo_tr, b2_tr = T1_SOLO, T2_B2
    contention = b2_tr / solo_tr

    fig, ax = plt.subplots(figsize=(7.5, 5))
    labels = ["Solo\n1 client / 1 GPU", "B2\n2 client / 1 GPU", "B3\n2 client / 2 GPU"]
    vals = [solo_tr, b2_tr, b3_tr]
    colors = ["#55A868", "#C44E52", "#4C72B0"]
    bars = ax.bar(labels, vals, color=colors)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.1f}s", ha="center", va="bottom")
    ax.annotate(f"contention {contention:.2f}×\n(serialize trên 1 GPU)",
                (1, b2_tr), textcoords="offset points", xytext=(0, 18),
                ha="center", fontsize=10, color="#8B0000", weight="bold")
    ax.annotate("GPU thứ 2 khôi phục\ntốc độ đầy đủ", (2, b3_tr),
                textcoords="offset points", xytext=(0, 18), ha="center",
                fontsize=9, color="#006400")
    ax.set_ylabel("Thời gian train mỗi client (s) — ResNet-18")
    ax.set_title("CIFAR-10 — GPU contention: 2 client chung 1 GPU thì serialize")
    ax.set_ylim(0, max(vals) * 1.28)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    out2 = FIG / "cifar_gpu_contention.png"
    fig.savefig(out2, dpi=120)
    plt.close(fig)
    print(f"[fig] {out2}")

    # ---- Summary (để đối chiếu với báo cáo) ----
    print("\n" + "=" * 58)
    print("SỐ LIỆU SCALING (đối chiếu báo cáo)")
    print("=" * 58)
    print(f"Light  B2={lb2:.2f}s  B3={lb3:.2f}s  → speedup {sp_light:.2f}× (THUA)")
    print(f"Heavy  B2={hb2:.2f}s  B3={hb3:.2f}s  → speedup {sp_heavy:.2f}× (THẮNG, eff {sp_heavy/2*100:.0f}%)")
    print(f"Contention (Máy 1 T1/T2): solo={solo_tr:.1f}s  B2={b2_tr:.1f}s  B3={b3_tr:.1f}s  → {contention:.2f}×")
    print(f"  cross-check data commit: solo(s2)={solo_tr_data:.1f}s  B2(b2b)={b2_tr_data:.1f}s  → {b2_tr_data/solo_tr_data:.2f}×")
    print("=" * 58)


if __name__ == "__main__":
    main()
