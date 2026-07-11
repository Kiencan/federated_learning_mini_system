"""Hình bổ sung cho báo cáo HPC (Chương 2/5/6/7) — analyze_extra.py.

Sinh 4 hình minh hoạ đào sâu:
  1. amdahl_speedup.png       — đường cong định luật Amdahl + điểm đo thực (p=2, S=1,96)
  2. round_wallclock_curve.png — wallclock từng vòng B3 nhẹ (rendezvous): vòng 1 sạch + steady
  3. heavy_round_breakdown.png — phân rã round heavy B2 vs B3, minh hoạ eval bị GIẤU nhờ overlap
  4. upload_bimodal.png       — histogram upload/round (Ethernet): phân phối lưỡng cực

Chạy bằng python env fedml trực tiếp (KHÔNG qua conda run — vỡ cp1252).
"""
from __future__ import annotations
import sys
from pathlib import Path
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent
DATA = REPO / "Report" / "data"
FIG = REPO / "Report" / "figures"
FIG.mkdir(parents=True, exist_ok=True)


def amdahl():
    p = np.linspace(1, 8, 200)
    plt.figure(figsize=(8, 5))
    for s, c in [(0.02, "#2E7D32"), (0.05, "#4C72B0"), (0.10, "#DD8452"), (0.20, "#C44E52")]:
        plt.plot(p, 1 / (s + (1 - s) / p), color=c, label=f"s = {int(s*100)}%")
    plt.plot(p, p, "k--", alpha=0.4, label="lý tưởng (tuyến tính)")
    plt.scatter([2], [1.96], color="#2E7D32", zorder=5, s=70)
    plt.annotate("đo thực: p=2, S=1,96 (s≈2%)", (2, 1.96),
                 textcoords="offset points", xytext=(8, -14), fontsize=10, color="#2E7D32", weight="bold")
    plt.xlabel("Số đơn vị tính toán p (số GPU)")
    plt.ylabel("Speedup S_p")
    plt.title("Định luật Amdahl — speedup bị chặn bởi phần tuần tự s")
    plt.legend(); plt.grid(True, alpha=0.3); plt.ylim(1, 8)
    out = FIG / "amdahl_speedup.png"; plt.tight_layout(); plt.savefig(out, dpi=120); plt.close()
    print(f"[fig] {out}")


def wallclock_curve():
    df = pd.read_csv(DATA / "exp_cifar_fed_2machine" / "m1_rv2" / "round_log.csv")
    plt.figure(figsize=(8, 4.5))
    plt.plot(df["round_id"], df["round_wallclock_sec"], "o-", color="#C44E52", markersize=4, label="B3 (2 máy) round_wallclock")
    plt.axhline(df[df["round_id"] >= 2]["round_wallclock_sec"].mean(), color="#4C72B0",
                linestyle="--", alpha=0.7, label=f"steady-state trung bình = {df[df['round_id']>=2]['round_wallclock_sec'].mean():.1f}s")
    plt.xlabel("Vòng (round)"); plt.ylabel("Thời gian mỗi vòng (s)")
    plt.title("CIFAR-10 nhẹ — thời gian mỗi vòng B3 (rendezvous): vòng 1 đã sạch")
    plt.legend(); plt.grid(True, alpha=0.3)
    out = FIG / "round_wallclock_curve.png"; plt.tight_layout(); plt.savefig(out, dpi=120); plt.close()
    print(f"[fig] {out}")


def heavy_breakdown():
    def steady(run, col):
        d = pd.read_csv(DATA / run / "round_log.csv"); d = d[d["round_id"] >= 2]
        return d[col].mean()
    # train mỗi client (max = client chặn vòng), comm ~ (down+up), eval (bị giấu)
    labels = ["B2 nặng\n(1 GPU)", "B3 nặng\n(2 GPU)"]
    b2 = "exp_cifar_heavy_1machine/b2b"; b3 = "exp_cifar_heavy_2machine/m1_heavy"
    wall = [steady(b2, "round_wallclock_sec"), steady(b3, "round_wallclock_sec")]
    evalt = [steady(b2, "eval_time_ms") / 1000, steady(b3, "eval_time_ms") / 1000]
    plt.figure(figsize=(7, 5))
    x = range(2)
    bars = plt.bar(x, wall, 0.5, color=["#C44E52", "#4C72B0"], label="round_wallclock thực (eval đã bị giấu)")
    # phần eval nếu KHÔNG overlap (ghost phía trên)
    plt.bar(x, evalt, 0.5, bottom=wall, color="#BBBBBB", alpha=0.55, hatch="//",
            label="eval nếu nằm trên critical path (đã tránh được)")
    for i, (w, e) in enumerate(zip(wall, evalt)):
        plt.text(i, w, f"{w:.1f}s", ha="center", va="bottom", fontsize=9, weight="bold")
        plt.text(i, w + e, f"+{e:.0f}s eval\n(giấu)", ha="center", va="bottom", fontsize=8, color="#666")
    plt.xticks(list(x), labels); plt.ylabel("Thời gian mỗi vòng (s) — ResNet-18")
    plt.title("Overlap: đánh giá ~15s bị giấu khỏi đường găng mỗi vòng")
    plt.legend(fontsize=8); plt.grid(True, axis="y", alpha=0.3)
    out = FIG / "heavy_round_breakdown.png"; plt.tight_layout(); plt.savefig(out, dpi=120); plt.close()
    print(f"[fig] {out}")


def upload_bimodal():
    # upload/round client-1 qua Ethernet (stdout run m1_opt4, ms) — dữ liệu đo thật
    up = [429, 29, 372, 21, 378, 365, 383, 387, 367, 384, 367, 376, 386, 381, 19, 20,
          19, 19, 19, 20, 383, 381, 400, 373, 18, 21, 21, 367, 379, 19]
    plt.figure(figsize=(8, 4.5))
    plt.hist(up, bins=24, color="#8172B3", edgecolor="white")
    plt.axvline(np.mean(up), color="#C44E52", linestyle="--", label=f"trung bình = {np.mean(up):.0f} ms")
    plt.xlabel("Upload mỗi vòng (ms)"); plt.ylabel("Số vòng")
    plt.title("Upload qua Ethernet — phân phối lưỡng cực (Nagle/delayed-ACK)")
    plt.annotate("cụm nhanh ~20ms", (20, 1), xytext=(60, 6), textcoords="data",
                 arrowprops=dict(arrowstyle="->", color="#666"), fontsize=9)
    plt.annotate("cụm chậm ~380ms", (380, 1), xytext=(250, 6), textcoords="data",
                 arrowprops=dict(arrowstyle="->", color="#666"), fontsize=9)
    plt.legend(); plt.grid(True, axis="y", alpha=0.3)
    out = FIG / "upload_bimodal.png"; plt.tight_layout(); plt.savefig(out, dpi=120); plt.close()
    print(f"[fig] {out}")


if __name__ == "__main__":
    amdahl(); wallclock_curve(); heavy_breakdown(); upload_bimodal()
    print("done — 4 hình bổ sung")
