"""CNN models — dùng chung giữa centralized baseline và federated clients.

Hai kiến trúc theo dataset:
  - MnistCNN:  2 conv (32, 64) + 2 FC          — input 1×28×28 (MNIST, grayscale)
  - CifarCNN:  3 conv (32, 64, 128) + 2 FC     — input 3×32×32 (CIFAR-10, RGB)

Chọn model qua `build_model(dataset)` để server/client/centralized không hardcode.
"""
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


class CifarCNN(nn.Module):
    """Model lớn hơn cho CIFAR-10: 3 conv block (32, 64, 128) + BatchNorm + 2 FC.

    Input 3×32×32 → sau 3 lần pool còn 128×4×4. Sâu hơn MnistCNN (3 conv vs 2,
    thêm BatchNorm) vì CIFAR-10 (ảnh màu, vật thể tự nhiên) khó hơn MNIST nhiều.
    ~1.1M tham số — vẫn đủ nhẹ để train trên 2 máy có GPU.
    """

    def __init__(self, num_classes: int = 10) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(3, 32, kernel_size=3, padding=1)
        self.bn1 = nn.BatchNorm2d(32)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)
        self.bn2 = nn.BatchNorm2d(64)
        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        self.bn3 = nn.BatchNorm2d(128)
        self.pool = nn.MaxPool2d(2, 2)
        self.dropout = nn.Dropout(0.25)
        self.fc1 = nn.Linear(128 * 4 * 4, 256)
        self.fc2 = nn.Linear(256, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.pool(F.relu(self.bn1(self.conv1(x))))  # 32 -> 16
        x = self.pool(F.relu(self.bn2(self.conv2(x))))  # 16 -> 8
        x = self.pool(F.relu(self.bn3(self.conv3(x))))  # 8 -> 4
        x = x.view(x.size(0), -1)
        x = self.dropout(x)
        x = F.relu(self.fc1(x))
        return self.fc2(x)


class _BasicBlock(nn.Module):
    """ResNet BasicBlock: 2 conv 3×3 + skip connection."""

    def __init__(self, in_c: int, out_c: int, stride: int = 1) -> None:
        super().__init__()
        self.conv1 = nn.Conv2d(in_c, out_c, 3, stride, 1, bias=False)
        self.bn1 = nn.BatchNorm2d(out_c)
        self.conv2 = nn.Conv2d(out_c, out_c, 3, 1, 1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_c)
        self.shortcut = nn.Sequential()
        if stride != 1 or in_c != out_c:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_c, out_c, 1, stride, bias=False),
                nn.BatchNorm2d(out_c),
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out = out + self.shortcut(x)
        return F.relu(out)


class CifarResNet(nn.Module):
    """ResNet-18 cho CIFAR-10 (~11M params) — compute NẶNG để test GPU contention.

    Dùng cho thí nghiệm scale-up (phương án C): khi 1 client đủ saturate GPU, chạy
    2 client trên 1 GPU (B2) phải serialize, còn 2 GPU riêng (B3) chạy song song →
    phân tán thắng. Kiến trúc ResNet-18 chuẩn adapt cho input 3×32×32.
    """

    def __init__(self, num_classes: int = 10) -> None:
        super().__init__()
        self.in_c = 64
        self.conv1 = nn.Conv2d(3, 64, 3, 1, 1, bias=False)
        self.bn1 = nn.BatchNorm2d(64)
        self.layer1 = self._make_layer(64, 2, 1)
        self.layer2 = self._make_layer(128, 2, 2)
        self.layer3 = self._make_layer(256, 2, 2)
        self.layer4 = self._make_layer(512, 2, 2)
        self.fc = nn.Linear(512, num_classes)

    def _make_layer(self, out_c: int, blocks: int, stride: int) -> nn.Sequential:
        layers = []
        for s in [stride] + [1] * (blocks - 1):
            layers.append(_BasicBlock(self.in_c, out_c, s))
            self.in_c = out_c
        return nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = F.relu(self.bn1(self.conv1(x)))  # 32×32
        out = self.layer1(out)                 # 32×32
        out = self.layer2(out)                 # 16×16
        out = self.layer3(out)                 # 8×8
        out = self.layer4(out)                 # 4×4
        out = F.adaptive_avg_pool2d(out, 1).flatten(1)
        return self.fc(out)


def build_model(dataset: str, num_classes: int = 10, arch: str = "cnn") -> nn.Module:
    """Factory chọn kiến trúc theo dataset + arch. Server/client/centralized gọi chung.

    dataset: "mnist" | "cifar10". arch: "cnn" (mặc định) | "resnet" (chỉ cifar10,
    ResNet-18 nặng cho thí nghiệm scale-up). Raise ValueError nếu không hỗ trợ.
    """
    if dataset == "mnist":
        return MnistCNN(num_classes)
    if dataset == "cifar10":
        if arch == "resnet":
            return CifarResNet(num_classes)
        return CifarCNN(num_classes)
    raise ValueError(f"build_model: dataset không hỗ trợ {dataset!r} (mnist|cifar10)")


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
