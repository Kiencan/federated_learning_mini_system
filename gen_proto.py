"""Regenerate proto/federated_pb2*.py từ proto/federated.proto.

Chạy sau khi sửa schema:
    python gen_proto.py

Yêu cầu: pip install grpcio-tools (đã có trong environment.yml).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parent
    proto_file = repo_root / "proto" / "federated.proto"
    if not proto_file.exists():
        sys.exit(f"Not found: {proto_file}")

    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"-I{repo_root}",                        # for "from proto import ..." in generated code
        f"--python_out={repo_root}",
        f"--grpc_python_out={repo_root}",
        str(proto_file),
    ]
    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)
    print("Generated:")
    for f in (repo_root / "proto").glob("federated_pb2*.py"):
        print(f"  {f.relative_to(repo_root)}")


if __name__ == "__main__":
    main()
