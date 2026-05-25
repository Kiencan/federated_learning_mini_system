"""MNIST loading + IID / Non-IID partition cho federated clients.

Centralized baseline (Milestone 1) chỉ cần `load_mnist` để lấy full train/test loader.
Federated milestones sẽ dùng `partition_iid` và `partition_noniid_pathological`.
"""
from __future__ import annotations

from typing import List

import numpy as np
import torch
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms

MNIST_MEAN = (0.1307,)
MNIST_STD = (0.3081,)


def _transform() -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.ToTensor(),
            transforms.Normalize(MNIST_MEAN, MNIST_STD),
        ]
    )


def load_mnist(data_root: str = "./data") -> tuple[datasets.MNIST, datasets.MNIST]:
    """Tải MNIST train/test (download nếu chưa có)."""
    train = datasets.MNIST(data_root, train=True, download=True, transform=_transform())
    test = datasets.MNIST(data_root, train=False, download=True, transform=_transform())
    return train, test


def make_loader(dataset, batch_size: int, shuffle: bool, num_workers: int = 0) -> DataLoader:
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
    )


def partition_iid(train: datasets.MNIST, num_clients: int, seed: int = 42) -> List[Subset]:
    """Chia ngẫu nhiên đều — mỗi client có phân phối tương tự full set."""
    rng = np.random.default_rng(seed)
    indices = np.arange(len(train))
    rng.shuffle(indices)
    splits = np.array_split(indices, num_clients)
    return [Subset(train, idx.tolist()) for idx in splits]


def partition_noniid_pathological(
    train: datasets.MNIST, num_clients: int = 2
) -> List[Subset]:
    """Pathological split: Client 1 chỉ có digits 0-4, Client 2 chỉ có 5-9.

    Chỉ hỗ trợ num_clients = 2 (theo design trong ytuong.md). Đây là trường hợp
    cực đoan để stress test FedAvg dưới Non-IID.
    """
    if num_clients != 2:
        raise ValueError("partition_noniid_pathological chỉ hỗ trợ num_clients=2")

    targets = np.asarray(train.targets)
    client_indices = []
    for digits in [(0, 1, 2, 3, 4), (5, 6, 7, 8, 9)]:
        mask = np.isin(targets, digits)
        client_indices.append(np.where(mask)[0].tolist())
    return [Subset(train, idx) for idx in client_indices]
