"""Dataset loading + IID / Non-IID partition cho federated clients.

Hỗ trợ MNIST (1×28×28) và CIFAR-10 (3×32×32). Chọn qua `load_dataset(name)`.
Centralized baseline chỉ cần full train/test loader; federated milestones dùng
`partition_iid` và `partition_noniid_pathological` (logic dataset-agnostic).
"""
from __future__ import annotations

from typing import List

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset, Subset
from torchvision import datasets, transforms

MNIST_MEAN = (0.1307,)
MNIST_STD = (0.3081,)

# CIFAR-10 per-channel mean/std (RGB), tính trên train set chuẩn.
CIFAR10_MEAN = (0.4914, 0.4822, 0.4465)
CIFAR10_STD = (0.2470, 0.2435, 0.2616)


def _mnist_transform() -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.ToTensor(),
            transforms.Normalize(MNIST_MEAN, MNIST_STD),
        ]
    )


def _cifar10_transform() -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.ToTensor(),
            transforms.Normalize(CIFAR10_MEAN, CIFAR10_STD),
        ]
    )


def load_mnist(data_root: str = "./data") -> tuple[datasets.MNIST, datasets.MNIST]:
    """Tải MNIST train/test (download nếu chưa có)."""
    train = datasets.MNIST(data_root, train=True, download=True, transform=_mnist_transform())
    test = datasets.MNIST(data_root, train=False, download=True, transform=_mnist_transform())
    return train, test


def load_cifar10(data_root: str = "./data") -> tuple[datasets.CIFAR10, datasets.CIFAR10]:
    """Tải CIFAR-10 train/test (download nếu chưa có)."""
    train = datasets.CIFAR10(data_root, train=True, download=True, transform=_cifar10_transform())
    test = datasets.CIFAR10(data_root, train=False, download=True, transform=_cifar10_transform())
    return train, test


def load_dataset(dataset: str, data_root: str = "./data") -> tuple[Dataset, Dataset]:
    """Factory chọn dataset theo tên. Raise ValueError nếu không hỗ trợ.

    dataset: "mnist" | "cifar10". Cả hai đều 10 lớp → aggregation.evaluate()
    (hardcode 10 lớp) và FedAvg dùng chung không cần đổi.
    """
    if dataset == "mnist":
        return load_mnist(data_root)
    if dataset == "cifar10":
        return load_cifar10(data_root)
    raise ValueError(f"load_dataset: dataset không hỗ trợ {dataset!r} (mnist|cifar10)")


def make_loader(dataset, batch_size: int, shuffle: bool, num_workers: int = 0) -> DataLoader:
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=torch.cuda.is_available(),
    )


def partition_iid(
    train: Dataset, num_clients: int, seed: int = 42, weights=None
) -> List[Subset]:
    """Chia ngẫu nhiên — mỗi client có phân phối tương tự full set.

    weights=None → chia đều (np.array_split). weights=[w0,w1,...] → chia theo tỷ lệ
    (opt-B cân bằng tải: cấp node chậm/kiêm server shard nhỏ hơn để 2 client về đích
    cùng lúc). FedAvg weighted theo num_samples nên accuracy giữ nguyên dù shard lệch.
    Weights phải giống nhau trên mọi client (cùng seed → cùng cách chia, mỗi client
    lấy shard_id của mình).
    """
    rng = np.random.default_rng(seed)
    indices = np.arange(len(train))
    rng.shuffle(indices)
    if weights is None:
        splits = np.array_split(indices, num_clients)
    else:
        if len(weights) != num_clients:
            raise ValueError(
                f"shard_weights phải có {num_clients} phần tử, got {len(weights)}"
            )
        w = np.asarray(weights, dtype=float)
        w = w / w.sum()  # normalize về tổng 1
        boundaries = (np.cumsum(w)[:-1] * len(indices)).astype(int)
        splits = np.split(indices, boundaries)
    return [Subset(train, idx.tolist()) for idx in splits]


def partition_noniid_pathological(
    train: Dataset, num_clients: int = 2
) -> List[Subset]:
    """Pathological split: Client 1 chỉ có lớp 0-4, Client 2 chỉ có lớp 5-9.

    Dataset-agnostic: MNIST = digits 0-4 / 5-9, CIFAR-10 = 5 lớp đầu / 5 lớp sau.
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
