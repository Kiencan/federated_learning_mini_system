"""CNN nhỏ cho MNIST — dùng chung giữa centralized baseline và federated clients."""
from __future__ import annotations

import io

import torch
import torch.nn as nn
import torch.nn.functional as F


class MnistCNN(nn.Module):
    """2 conv (32, 64 filters) + 2 FC + dropout. Đầu ra: logits 10 lớp."""

    def __init__(self, num_classes: int = 10) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(1, 32, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.pool = nn.MaxPool2d(2, 2)
        self.dropout = nn.Dropout(0.25)
        self.fc1 = nn.Linear(64 * 7 * 7, 128)
        self.fc2 = nn.Linear(128, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.pool(F.relu(self.conv1(x)))  # 28 -> 14
        x = self.pool(F.relu(self.conv2(x)))  # 14 -> 7
        x = x.view(x.size(0), -1)
        x = self.dropout(x)
        x = F.relu(self.fc1(x))
        return self.fc2(x)


def serialize_state_dict(model: nn.Module) -> bytes:
    """Encode state_dict → bytes để nhét vào gRPC ModelWeights.

    Chỉ serialize state_dict, KHÔNG serialize toàn bộ nn.Module — tránh
    class/dependency mismatch giữa server và client.
    """
    buffer = io.BytesIO()
    torch.save(model.state_dict(), buffer)
    return buffer.getvalue()


def load_state_dict_from_bytes(model: nn.Module, payload: bytes) -> None:
    """Decode bytes → state_dict và load vào model."""
    buffer = io.BytesIO(payload)
    state_dict = torch.load(buffer, map_location="cpu", weights_only=True)
    model.load_state_dict(state_dict)
