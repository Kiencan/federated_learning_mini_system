"""Shared aggregation + evaluation utilities.

- fedavg: weighted average of state_dicts by num_samples
- evaluate: test-set evaluation returning loss, accuracy, per-class accuracy

Dùng chung giữa server.py (federated aggregation) và centralized_train.py
(baseline eval) để tránh code duplication.
"""
from __future__ import annotations

from typing import Iterable

import torch
import torch.nn as nn
import torch.nn.functional as F


def fedavg(
    updates: Iterable[tuple[dict[str, torch.Tensor], int]],
) -> dict[str, torch.Tensor]:
    """Weighted average state_dicts theo num_samples.

    Args:
        updates: iterable of (state_dict, num_samples). State_dict tensors
                 must be trên CPU (caller chịu trách nhiệm).

    Returns:
        Aggregated state_dict (CPU tensors).
    """
    updates_list = list(updates)
    if not updates_list:
        raise ValueError("fedavg: không có update nào để aggregate")

    total_samples = sum(n for _, n in updates_list)
    if total_samples == 0:
        raise ValueError("fedavg: total num_samples = 0")

    # Khởi tạo accumulator từ keys của state_dict đầu tiên
    first_sd = updates_list[0][0]
    avg_state = {k: torch.zeros_like(v, dtype=torch.float32) for k, v in first_sd.items()}

    for sd, n in updates_list:
        weight = n / total_samples
        for k in avg_state:
            avg_state[k] += sd[k].to(torch.float32) * weight

    # Đưa về dtype gốc (vd long tensor cho running_mean nếu có buffers integer)
    return {k: v.to(first_sd[k].dtype) for k, v in avg_state.items()}


def evaluate(
    model: nn.Module,
    loader,
    device: str,
) -> tuple[float, float, list[float]]:
    """Evaluate model trên test loader.

    Returns:
        (avg_loss, accuracy, per_class_accuracy) — per_class_accuracy là list 10 phần tử cho MNIST.
    """
    model.eval()
    model.to(device)
    total_loss = 0.0
    total_correct = 0
    total_samples = 0
    class_correct = [0] * 10
    class_total = [0] * 10

    with torch.no_grad():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            loss = F.cross_entropy(logits, y, reduction="sum")
            total_loss += loss.item()
            preds = logits.argmax(dim=1)
            total_correct += (preds == y).sum().item()
            total_samples += y.size(0)
            for cls in range(10):
                mask = y == cls
                class_total[cls] += mask.sum().item()
                class_correct[cls] += ((preds == y) & mask).sum().item()

    avg_loss = total_loss / total_samples
    accuracy = total_correct / total_samples
    per_class = [
        (class_correct[c] / class_total[c]) if class_total[c] else 0.0 for c in range(10)
    ]
    return avg_loss, accuracy, per_class
