"""Sinh hình §8 báo cáo HPC — all-reduce vs parameter-server.

Đọc crit-path all-reduce từ Report/data/exp_cifar_allreduce/*; các mốc federated
opt-A (9.70/10.56 s/round × 30) và centralized B1 (train 540.8s) là hằng số tra
từ Phụ lục A (runs m1_opt / m1_opt5 / m1_le2fair). Chạy từ thư mục gốc repo:
    python analyze_allreduce.py
"""
import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

DATA = Path("Report/data/exp_cifar_allreduce")
OUT = Path("Report/figures"); OUT.mkdir(parents=True, exist_ok=True)
BLUE, GREEN, PURPLE, RED = "#4C72B0", "#55A868", "#8172B3", "#C44E52"


def critpath(run):
    rows = list(csv.DictReader(open(DATA / run / "round_log.csv", encoding="utf-8")))
    return sum(float(r["round_wallclock_sec"]) for r in rows)


# All-reduce đo trực tiếp từ data; federated opt-A / centralized tra Phụ lục A.
ar1, ar2 = critpath("A_s42"), critpath("A_2m_s42")
arB = critpath("B_s42")
fed = [291.0, 316.8]          # opt-A B2 (m1_opt), B3 (m1_opt5): 9.70/10.56 × 30
cen = 540.8                   # B1 60ep train-only (m1_le2fair)

# ---- Figure 1: grouped bars ----
ar = [ar1, ar2]; speed = [f / a for f, a in zip(fed, ar)]
x = np.arange(2); w = 0.36
plt.figure(figsize=(7.5, 5))
plt.bar(x - w/2, fed, w, label="Federated opt-A (parameter-server)", color=BLUE)
plt.bar(x + w/2, ar, w, label="All-reduce A (phi tập trung)", color=GREEN)
for i, (f, a, s) in enumerate(zip(fed, ar, speed)):
    plt.text(x[i]-w/2, f+6, f"{f:.0f}s", ha="center", fontsize=9)
    plt.text(x[i]+w/2, a+6, f"{a:.0f}s", ha="center", fontsize=9)
    plt.annotate(f"{s:.2f}× nhanh hơn", (x[i]+w/2, a), (x[i]+w/2, a+55),
                 ha="center", fontsize=10, fontweight="bold", color=GREEN,
                 arrowprops=dict(arrowstyle="->", color=GREEN))
plt.xticks(x, ["1 máy", "2 máy"])
plt.ylabel("Crit-path (giây, loại eval — cùng 3000K image-pass)")
plt.title("All-reduce vs Parameter-server: điều phối tăng khi ra 2 máy, all-reduce phẳng")
plt.ylim(0, 380); plt.legend(loc="upper left"); plt.tight_layout()
plt.savefig(OUT / "cifar_allreduce_speedup.png", dpi=120); plt.close()

# ---- Figure 2: landscape ----
labels = ["All-reduce A\n(2 máy)", "All-reduce A\n(1 máy)",
          "Federated opt-A\n(B2, 1 máy)", "Federated opt-A\n(B3, 2 máy)",
          "Centralized B1\n(1 proc)", "All-reduce B\n(mỗi batch)"]
vals = [ar2, ar1, fed[0], fed[1], cen, arB]
colors = [GREEN, GREEN, BLUE, BLUE, PURPLE, RED]
order = np.argsort(vals)
labels = [labels[i] for i in order]; vals = [vals[i] for i in order]; colors = [colors[i] for i in order]
plt.figure(figsize=(8, 5))
plt.barh(range(len(vals)), vals, color=colors)
for i, v in enumerate(vals):
    plt.text(v + 15, i, f"{v:.0f}s", va="center", fontsize=9)
plt.yticks(range(len(labels)), labels, fontsize=9)
plt.xlabel("Thời gian hoàn thành 3000K image-pass (giây, loại eval)")
plt.title("Toàn cảnh: kiến trúc điều phối quyết định tốc độ (accuracy đều ~82%)")
plt.xlim(0, 1750); plt.tight_layout()
plt.savefig(OUT / "cifar_allreduce_landscape.png", dpi=120); plt.close()
print("saved cifar_allreduce_speedup.png, cifar_allreduce_landscape.png")
