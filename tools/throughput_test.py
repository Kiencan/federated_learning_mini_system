"""Đo throughput TCP thực giữa 2 máy (không cần cài iperf3 — chỉ socket stdlib).

Đo băng thông thực của link Ethernet 10.0.0.x để bổ sung cho phân tích
communication time trong báo cáo (link speed negotiated != throughput thực).

Cách dùng (2 máy cùng subnet):
    # Máy nhận (chạy TRƯỚC) — vd Máy 1 = 10.0.0.1:
    python tools/throughput_test.py server --bind 0.0.0.0 --port 5201

    # Máy gửi — vd Máy 2:
    python tools/throughput_test.py client --host 10.0.0.1 --port 5201 --mb 1024

Client gửi `--mb` MB dữ liệu, đo thời gian, in throughput (MB/s và Gbps).
Mặc định 1024 MB (1 GB) — đủ lớn để số ổn định, qua 2.5GbE mất ~4s.
"""
from __future__ import annotations

import argparse
import socket
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

CHUNK = 1024 * 1024  # 1 MB / lần send/recv


def run_server(bind: str, port: int) -> None:
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((bind, port))
    srv.listen(1)
    print(f"[server] listening on {bind}:{port} — chờ client kết nối ...")
    conn, addr = srv.accept()
    print(f"[server] client connected: {addr[0]}:{addr[1]}")

    total = 0
    buf = bytearray(CHUNK)
    t0 = time.perf_counter()
    while True:
        n = conn.recv_into(buf, CHUNK)
        if n == 0:
            break
        total += n
    elapsed = time.perf_counter() - t0

    mb = total / (1024 * 1024)
    mbps = mb / elapsed if elapsed > 0 else 0.0
    gbit = (total * 8) / (elapsed * 1e9) if elapsed > 0 else 0.0
    print(
        f"[server] nhận {mb:.1f} MB trong {elapsed:.2f}s → "
        f"{mbps:.1f} MB/s ({gbit:.2f} Gbps)"
    )
    conn.close()
    srv.close()


def run_client(host: str, port: int, mb: int) -> None:
    payload = bytes(CHUNK)
    rounds = mb
    print(f"[client] kết nối {host}:{port}, gửi {mb} MB ...")
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((host, port))

    t0 = time.perf_counter()
    for _ in range(rounds):
        sock.sendall(payload)
    sock.shutdown(socket.SHUT_WR)  # báo server hết dữ liệu
    sock.close()
    elapsed = time.perf_counter() - t0

    total_mb = rounds
    mbps = total_mb / elapsed if elapsed > 0 else 0.0
    gbit = (total_mb * 1024 * 1024 * 8) / (elapsed * 1e9) if elapsed > 0 else 0.0
    print(
        f"[client] gửi {total_mb} MB trong {elapsed:.2f}s → "
        f"{mbps:.1f} MB/s ({gbit:.2f} Gbps)"
    )


def main() -> None:
    p = argparse.ArgumentParser(description="TCP throughput test (no iperf needed)")
    sub = p.add_subparsers(dest="role", required=True)

    ps = sub.add_parser("server", help="máy nhận (chạy trước)")
    ps.add_argument("--bind", default="0.0.0.0")
    ps.add_argument("--port", type=int, default=5201)

    pc = sub.add_parser("client", help="máy gửi")
    pc.add_argument("--host", required=True, help="IP máy server, vd 10.0.0.1")
    pc.add_argument("--port", type=int, default=5201)
    pc.add_argument("--mb", type=int, default=1024, help="số MB gửi (default 1024 = 1GB)")

    args = p.parse_args()
    if args.role == "server":
        run_server(args.bind, args.port)
    else:
        run_client(args.host, args.port, args.mb)


if __name__ == "__main__":
    main()
