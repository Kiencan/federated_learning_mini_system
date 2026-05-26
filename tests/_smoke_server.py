"""Smoke test M3 server — chạy 5 case validation + 1 case happy path.

Chạy sau khi server đã start trên 127.0.0.1:50051 với --num-rounds 1.
Test này chỉ dùng cho dev kiểm tra nhanh server M3 mà chưa có client M3 thật
(Máy 2 đang dev song song). Sẽ xóa hoặc thay bằng test_stale_update.py
sau khi M3.8 merge.
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

# Add repo root to path so we can import model, proto, etc.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import grpc
import torch

from model import MnistCNN, serialize_state_dict
from proto import federated_pb2, federated_pb2_grpc


SERVER_ADDR = "127.0.0.1:50051"


def make_update(client_id: str, round_id: int, num_samples: int = 30000) -> federated_pb2.ClientUpdate:
    """Tao 1 ClientUpdate gia voi state_dict ngau nhien."""
    m = MnistCNN()
    return federated_pb2.ClientUpdate(
        client_id=client_id,
        round_id=round_id,
        serialized_state_dict=serialize_state_dict(m),
        num_samples=num_samples,
        train_loss=0.5,
        hostname="test-host",
        gpu_name="test-gpu",
        torch_version="2.5.1",
        cuda_version="12.1",
    )


def main():
    options = [
        ("grpc.max_send_message_length", 16 * 1024 * 1024),
        ("grpc.max_receive_message_length", 16 * 1024 * 1024),
    ]
    with grpc.insecure_channel(SERVER_ADDR, options=options) as channel:
        grpc.channel_ready_future(channel).result(timeout=5)
        stub = federated_pb2_grpc.FederatedLearningStub(channel)

        # CASE 0: GetRoundStatus baseline
        st = stub.GetRoundStatus(federated_pb2.Empty())
        print(f"[0] status: round={st.current_round} state={federated_pb2.RoundStatus.State.Name(st.state)} total={st.num_rounds_total}")
        assert st.current_round == 1
        assert st.state == federated_pb2.RoundStatus.TRAINING

        # CASE 1: GetGlobalModel — happy path
        model_resp = stub.GetGlobalModel(federated_pb2.RoundRequest(round_id=1, client_id="client-0"))
        print(f"[1] GetGlobalModel: round={model_resp.round_id} bytes={len(model_resp.serialized_state_dict)}")
        assert len(model_resp.serialized_state_dict) > 1_000_000  # state_dict ~1.6 MB

        # CASE 2: SubmitUpdate — unknown_client
        ack = stub.SubmitUpdate(make_update(client_id="hacker", round_id=1))
        print(f"[2] SubmitUpdate unknown: accepted={ack.accepted} msg={ack.message!r}")
        assert not ack.accepted
        assert ack.message == "unknown_client"

        # CASE 3: SubmitUpdate — stale_round
        ack = stub.SubmitUpdate(make_update(client_id="client-0", round_id=99))
        print(f"[3] SubmitUpdate stale_round: accepted={ack.accepted} msg={ack.message!r}")
        assert not ack.accepted
        assert "stale_round" in ack.message

        # CASE 4: SubmitUpdate — happy path client-0
        ack = stub.SubmitUpdate(make_update(client_id="client-0", round_id=1))
        print(f"[4] SubmitUpdate client-0: accepted={ack.accepted}")
        assert ack.accepted

        # CASE 5: SubmitUpdate — duplicate
        ack = stub.SubmitUpdate(make_update(client_id="client-0", round_id=1))
        print(f"[5] SubmitUpdate duplicate: accepted={ack.accepted} msg={ack.message!r}")
        assert not ack.accepted
        assert ack.message == "duplicate_update"

        # CASE 6: SubmitUpdate — client-1 (trigger aggregation)
        print("[6] SubmitUpdate client-1 (will trigger aggregation, may take few sec)...")
        ack = stub.SubmitUpdate(make_update(client_id="client-1", round_id=1))
        print(f"[6] SubmitUpdate client-1: accepted={ack.accepted}")
        assert ack.accepted

        # CASE 7: After DONE, server should reject further submits
        st = stub.GetRoundStatus(federated_pb2.Empty())
        print(f"[7] post-agg status: state={federated_pb2.RoundStatus.State.Name(st.state)}")
        assert st.state == federated_pb2.RoundStatus.DONE

        # CASE 8: Submit after DONE should be rejected with state_not_training
        ack = stub.SubmitUpdate(make_update(client_id="client-0", round_id=1))
        print(f"[8] SubmitUpdate after DONE: accepted={ack.accepted} msg={ack.message!r}")
        assert not ack.accepted
        assert "state_not_training" in ack.message

    print("\nALL CASES PASSED")


if __name__ == "__main__":
    main()
