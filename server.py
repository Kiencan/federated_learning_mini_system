"""Federated Learning server.

M2 status: chỉ implement GetRoundStatus để verify network boundary.
GetGlobalModel / SubmitUpdate trả UNIMPLEMENTED — sẽ làm trong M3.

Server bind 0.0.0.0:50051 để cả localhost và client LAN đều kết nối được.
"""
from __future__ import annotations

import argparse
from concurrent import futures

import grpc

from proto import federated_pb2, federated_pb2_grpc
from run_context import build_cli_parser, cli_overrides, load_config


class FederatedServicer(federated_pb2_grpc.FederatedLearningServicer):
    def __init__(self, num_rounds_total: int) -> None:
        self.current_round = 0
        self.state = federated_pb2.RoundStatus.WAITING
        self.num_rounds_total = num_rounds_total

    # M2: chỉ RPC này active
    def GetRoundStatus(self, request, context):
        return federated_pb2.RoundStatus(
            current_round=self.current_round,
            state=self.state,
            num_rounds_total=self.num_rounds_total,
        )

    def GetGlobalModel(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("GetGlobalModel chua implement (M3)")
        return federated_pb2.ModelWeights()

    def SubmitUpdate(self, request, context):
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("SubmitUpdate chua implement (M3)")
        return federated_pb2.AckResponse()


def main() -> None:
    parser = build_cli_parser("Federated Learning server (M2: hello world)")
    parser.add_argument(
        "--bind",
        default="0.0.0.0:50051",
        help="bind address [host:port] — mac dinh 0.0.0.0 de cho phep LAN ket noi",
    )
    args = parser.parse_args()

    cfg = load_config(args.config, overrides=cli_overrides(args))
    servicer = FederatedServicer(num_rounds_total=cfg["num_rounds"])

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=4),
        options=[
            ("grpc.max_send_message_length", 16 * 1024 * 1024),       # 16 MB
            ("grpc.max_receive_message_length", 16 * 1024 * 1024),
        ],
    )
    federated_pb2_grpc.add_FederatedLearningServicer_to_server(servicer, server)
    port = server.add_insecure_port(args.bind)
    if port == 0:
        raise RuntimeError(f"Khong bind duoc {args.bind} (port da bi chiem?)")
    server.start()

    print(f"[server] listening on {args.bind}")
    print(f"[server] num_rounds_total={servicer.num_rounds_total} state=WAITING")
    print("[server] Ctrl+C de dung")

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\n[server] stopping (grace 2s)...")
        server.stop(grace=2).wait()
        print("[server] stopped")


if __name__ == "__main__":
    main()
