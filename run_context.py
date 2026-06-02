"""Shared utilities cho mọi training script.

- load_config: đọc config.yaml + apply CLI override
- set_seed: reproducibility
- create_run_dir: tạo {results_root}/{experiment_name}/{run_id}/, snapshot config.yaml
- write_run_meta: ghi run_meta.json (hostname, torch version, GPU, ...)
"""
from __future__ import annotations

import argparse
import json
import random
import socket
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml


@dataclass
class RunContext:
    config: dict
    run_dir: Path
    run_id: str
    config_path: Path


def load_config(config_path: str, overrides: dict[str, Any] | None = None) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    if overrides:
        for key, value in overrides.items():
            if value is not None:
                cfg[key] = value
    return cfg


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _git_commit() -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode().strip()
    except Exception:
        return None


def _gpu_info() -> dict[str, Any]:
    info: dict[str, Any] = {
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": None,
        "cuda_version": None,
    }
    if torch.cuda.is_available():
        info["gpu_name"] = torch.cuda.get_device_name(0)
        info["cuda_version"] = torch.version.cuda
    return info


def create_run_dir(config: dict, config_path: str) -> RunContext:
    """Tạo {results_root}/{experiment_name}/{run_id}/ và snapshot RESOLVED config.

    Snapshot dùng yaml.safe_dump(config, ...) thay vì copy file gốc — để
    `config.yaml` trong run_dir phản ánh đúng CLI overrides (vd --num-rounds 5,
    --data-split noniid) thay vì giá trị default trong config.yaml gốc.

    Fix tech debt từ M3 (M5.0): trước đây shutil.copyfile(config_path, snapshot)
    copy file gốc → snapshot không khớp với run thật khi user pass CLI flag.
    """
    run_id = config.get("run_id") or datetime.now().strftime("%Y-%m-%d_%H%M")
    run_dir = Path(config["results_root"]) / config["experiment_name"] / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    snapshot = run_dir / "config.yaml"
    with snapshot.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            config,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )

    return RunContext(config=config, run_dir=run_dir, run_id=run_id, config_path=snapshot)


def write_run_meta(
    ctx: RunContext,
    role: str,
    extra: dict[str, Any] | None = None,
) -> None:
    """Ghi run_meta.json. Federated sẽ gọi nhiều lần và merge — M1 chỉ ghi 1 lần."""
    meta_path = ctx.run_dir / "run_meta.json"
    gpu = _gpu_info()
    entry = {
        "role": role,
        "hostname": socket.gethostname(),
        "torch_version": torch.__version__,
        "device": ctx.config.get("device"),
        **gpu,
    }
    if extra:
        entry.update(extra)

    meta: dict[str, Any] = {
        "start_time": datetime.now().isoformat(timespec="seconds"),
        "git_commit": _git_commit(),
        "config_snapshot": str(ctx.config_path),
    }
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.setdefault("nodes", []).append(entry)

    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def build_cli_parser(description: str) -> argparse.ArgumentParser:
    """CLI tham số phổ biến — script có thể add_argument thêm."""
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--config", default="config.yaml", help="đường dẫn config.yaml")
    p.add_argument("--num-rounds", type=int, default=None)
    p.add_argument("--local-epochs", type=int, default=None)
    p.add_argument("--batch-size", type=int, default=None)
    p.add_argument("--lr", type=float, default=None)
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--device", default=None)
    p.add_argument("--experiment-name", default=None)
    p.add_argument("--run-id", default=None)
    p.add_argument(
        "--data-split",
        choices=["iid", "noniid"],
        default=None,
        help="data partition mode (override config.yaml data_split). "
             "Server: chỉ snapshot vào config; Client: dispatch partition function.",
    )
    p.add_argument(
        "--min-clients",
        type=int,
        default=None,
        help="M6: minimum clients to aggregate (1 = fault tolerant). "
             "Server-side; overrides config.yaml min_clients.",
    )
    p.add_argument(
        "--wait-timeout",
        type=float,
        default=None,
        help="M6: max seconds server chờ clients trong 1 round trước khi "
             "fallback aggregation. Server-side; overrides config.yaml wait_timeout.",
    )
    p.add_argument(
        "--straggler-delay",
        type=float,
        default=None,
        help="M7: client-side artificial delay (seconds) injected before "
             "SubmitUpdate to simulate straggler. Counted inside upload_ms. "
             "Client-side; overrides config.yaml straggler_delay. "
             "Server snapshot reflects scenario (recommend pass on S1/S2 server too).",
    )
    return p


def cli_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """Map CLI args → config keys (chỉ những giá trị không phải None)."""
    mapping = {
        "num_rounds": args.num_rounds,
        "local_epochs": args.local_epochs,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "seed": args.seed,
        "device": args.device,
        "experiment_name": args.experiment_name,
        "run_id": args.run_id,
        "data_split": args.data_split,
        "min_clients": args.min_clients,
        "wait_timeout": args.wait_timeout,
        "straggler_delay": args.straggler_delay,
    }
    return {k: v for k, v in mapping.items() if v is not None}
