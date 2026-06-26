"""Milestone 1 — Centralized baseline.

Train CNN trên toàn bộ MNIST train set, không có gRPC, không có client. Mỗi epoch
log accuracy/loss/wall-clock vào round_log.csv để so sánh với federated runs sau này
(centralized "round" = "epoch").
"""
from __future__ import annotations

import csv
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import optim

from aggregation import evaluate
from data_partition import load_dataset, make_loader
from model import build_model
from run_context import (
    build_cli_parser,
    cli_overrides,
    create_run_dir,
    load_config,
    set_seed,
    write_run_meta,
)


def train_one_epoch(model: nn.Module, loader, optimizer, device: str) -> float:
    model.train()
    total_loss = 0.0
    total_samples = 0
    for x, y in loader:
        x, y = x.to(device), y.to(device)
        optimizer.zero_grad()
        logits = model(x)
        loss = F.cross_entropy(logits, y)
        loss.backward()
        optimizer.step()
        total_loss += loss.item() * y.size(0)
        total_samples += y.size(0)
    return total_loss / total_samples


def main() -> None:
    parser = build_cli_parser("Centralized MNIST baseline (Milestone 1)")
    args = parser.parse_args()

    cfg = load_config(args.config, overrides=cli_overrides(args))
    if not args.experiment_name:
        cfg["experiment_name"] = "exp_centralized"
    set_seed(cfg["seed"])

    ctx = create_run_dir(cfg, args.config)
    write_run_meta(ctx, role="centralized_trainer")

    device = cfg["device"] if torch.cuda.is_available() or cfg["device"] == "cpu" else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        device = "cpu"
    dataset = cfg.get("dataset", "mnist")
    print(f"[centralized] run_dir={ctx.run_dir} device={device} dataset={dataset}")

    train_set, test_set = load_dataset(dataset)
    train_loader = make_loader(train_set, cfg["batch_size"], shuffle=True)
    test_loader = make_loader(test_set, cfg["batch_size"] * 4, shuffle=False)

    model = build_model(dataset).to(device)
    optimizer = optim.SGD(model.parameters(), lr=cfg["lr"], momentum=0.9)

    log_path = ctx.run_dir / "round_log.csv"
    fieldnames = [
        "round_id",
        "train_loss",
        "test_loss",
        "accuracy",
        "epoch_time_sec",
        "cumulative_time_sec",
        *(f"acc_class_{c}" for c in range(10)),
    ]
    with log_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        num_epochs = cfg["num_rounds"]
        cumulative = 0.0
        for epoch in range(1, num_epochs + 1):
            t0 = time.perf_counter()
            train_loss = train_one_epoch(model, train_loader, optimizer, device)
            epoch_time = time.perf_counter() - t0
            cumulative += epoch_time

            test_loss, accuracy, per_class = evaluate(model, test_loader, device)
            row = {
                "round_id": epoch,
                "train_loss": round(train_loss, 6),
                "test_loss": round(test_loss, 6),
                "accuracy": round(accuracy, 6),
                "epoch_time_sec": round(epoch_time, 3),
                "cumulative_time_sec": round(cumulative, 3),
                **{f"acc_class_{c}": round(per_class[c], 6) for c in range(10)},
            }
            writer.writerow(row)
            f.flush()
            print(
                f"[epoch {epoch:02d}/{num_epochs}] "
                f"train_loss={train_loss:.4f} test_loss={test_loss:.4f} "
                f"acc={accuracy:.4f} time={epoch_time:.2f}s"
            )

    print(f"[centralized] done. Log: {log_path}")


if __name__ == "__main__":
    main()
