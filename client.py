"""Federated Learning client.

M2 status: chỉ gọi GetRoundStatus 1 lần roi thoat -- de verify network boundary.
M3+ se them training loop: pull model -> train -> submit update.
"""
from __future__ import annotations

import argparse
import sys
import time

import grpc

from proto import federated_pb2, federated_pb2_grpc
from run_context import build_cli_parser, cli_overrides, load_config


def main() -> None:
    parser = build_cli_parser("Federated Learning client (M2: hello world)")
    parser.add_argument("--client-id", default="client-2", help="dinh danh client")
    parser.add_argument(
        "--server-addr",
        default=None,
        help="dia chi server host:port (override config.server_addr)",
    )
    parser.add_argument(
        "--poll",
        type=int,
        default=1,
        help="so lan poll GetRoundStatus (default=1). >1 de stress test.",
    )
    args = parser.parse_args()

    cfg = load_config(args.config, overrides=cli_overrides(args))
    server_addr = args.server_addr or cfg["server_addr"]
    print(f"[client {args.client_id}] connecting to {server_addr}")

    options = [
        ("grpc.max_send_message_length", 16 * 1024 * 1024),
        ("grpc.max_receive_message_length", 16 * 1024 * 1024),
    ]
    with grpc.insecure_channel(server_addr, options=options) as channel:
        # Wait for channel to be ready (timeout 5s) — catch network issues sớm
        try:
            grpc.channel_ready_future(channel).result(timeout=5)
        except grpc.FutureTimeoutError:
            print(f"[client] ERROR: khong connect duoc den {server_addr} sau 5s")
            print("[client] Kiem tra: server da chay chua? Firewall port 50051? LAN IP dung?")
            sys.exit(1)

        stub = federated_pb2_grpc.FederatedLearningStub(channel)
        for i in range(args.poll):
            t0 = time.perf_counter()
            try:
                status = stub.GetRoundStatus(federated_pb2.Empty(), timeout=10)
            except grpc.RpcError as e:
                print(f"[client] RPC error: code={e.code()} details={e.details()}")
                sys.exit(2)
            rtt_ms = (time.perf_counter() - t0) * 1000
            state_name = federated_pb2.RoundStatus.State.Name(status.state)
            print(
                f"[client] poll {i+1}/{args.poll}: "
                f"round={status.current_round}/{status.num_rounds_total} "
                f"state={state_name} rtt={rtt_ms:.1f}ms"
            )
            if i + 1 < args.poll:
                time.sleep(0.5)

    print(f"[client {args.client_id}] done")


if __name__ == "__main__":
    main()
