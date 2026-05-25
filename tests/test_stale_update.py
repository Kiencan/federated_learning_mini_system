"""M3.8 — Stale update validation test.

Verify server reject đúng 4 case theo m3_plan.md §9.2:
  Case 1: round_id=99  (known client, sai round)    → reject "stale_round"
  Case 2: client_id="unknown-client"                → reject "unknown_client"
  Case 3: update hợp lệ (client-0, round=1)         → accept
  Case 4: update lại từ client-0                    → reject "duplicate_update"

QUAN TRỌNG (m3_plan.md §11 risk 5):
  Script này phải chạy ngay sau khi server vừa start, TRƯỚC khi bất kỳ client
  thật nào submit. Nếu server đã DONE (round 1 kết thúc), một số case sẽ bị
  reject theo "state_not_training" thay vì đúng lý do → kết quả sai.
  → Restart server trước khi chạy lại test này.

  Sau khi test xong, server còn lưu update của client-0 (case 3).
  Restart server trước khi chạy full smoke test M3.7.

Chạy:
  python tests/test_stale_update.py
  python tests/test_stale_update.py --server-addr 192.168.2.30:50051
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Thêm repo root vào sys.path để import model, proto, v.v.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import grpc

from model import MnistCNN, serialize_state_dict
from proto import federated_pb2, federated_pb2_grpc


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_update(
    client_id: str,
    round_id: int,
    num_samples: int = 30000,
) -> federated_pb2.ClientUpdate:
    """Tạo ClientUpdate với state_dict ngẫu nhiên (đủ để server deserialize)."""
    return federated_pb2.ClientUpdate(
        client_id=client_id,
        round_id=round_id,
        serialized_state_dict=serialize_state_dict(MnistCNN()),
        num_samples=num_samples,
        train_loss=0.42,
        hostname="test-host",
        gpu_name="",
        torch_version="test",
        cuda_version="",
    )


def _pass(case: int, desc: str) -> None:
    print(f"  [PASS] case {case}: {desc}")


def _fail(case: int, desc: str, detail: str) -> None:
    print(f"  [FAIL] case {case}: {desc}")
    print(f"         detail: {detail}")


# ── Test runner ────────────────────────────────────────────────────────────────

def run_tests(server_addr: str) -> bool:
    """Chạy 4 test case. Trả về True nếu tất cả PASS."""
    options = [
        ("grpc.max_send_message_length", 16 * 1024 * 1024),
        ("grpc.max_receive_message_length", 16 * 1024 * 1024),
    ]

    print(f"\n[test] connecting to {server_addr} ...")
    with grpc.insecure_channel(server_addr, options=options) as channel:
        try:
            grpc.channel_ready_future(channel).result(timeout=5)
        except grpc.FutureTimeoutError:
            print(f"[test] ERROR: không connect được {server_addr} sau 5s")
            print("[test] Kiểm tra: server đã chạy chưa? Firewall port 50051?")
            return False

        stub = federated_pb2_grpc.FederatedLearningStub(channel)

        # ── Tiền điều kiện: server phải đang TRAINING ─────────────────────────
        status = stub.GetRoundStatus(federated_pb2.Empty(), timeout=5)
        state_name = federated_pb2.RoundStatus.State.Name(status.state)

        if status.state != federated_pb2.RoundStatus.TRAINING:
            print(
                f"\n[test] ABORT: server state={state_name}, cần TRAINING.\n"
                f"  → Restart server rồi chạy lại: python server.py --num-rounds 1"
            )
            return False

        print(
            f"[test] server state=TRAINING round={status.current_round}/"
            f"{status.num_rounds_total} — OK, bắt đầu test\n"
        )

        results: list[bool] = []

        # ── Case 1: stale round ───────────────────────────────────────────────
        # client_id hợp lệ (client-0) nhưng round_id sai (99)
        # Validation order §5: unknown_client → state → stale_round → duplicate
        # → vượt qua check 1 (known), vượt qua check 2 (TRAINING), fail ở check 3
        ack = stub.SubmitUpdate(_make_update(client_id="client-0", round_id=99))
        if not ack.accepted and "stale_round" in ack.message:
            _pass(1, f"stale round rejected: {ack.message!r}")
            results.append(True)
        else:
            _fail(1, "stale round should be rejected",
                  f"accepted={ack.accepted} message={ack.message!r}")
            results.append(False)

        # ── Case 2: unknown client ────────────────────────────────────────────
        # client_id không có trong expected_client_ids → fail ở check 1
        ack = stub.SubmitUpdate(_make_update(client_id="unknown-client", round_id=1))
        if not ack.accepted and "unknown_client" in ack.message:
            _pass(2, f"unknown client rejected: {ack.message!r}")
            results.append(True)
        else:
            _fail(2, "unknown client should be rejected",
                  f"accepted={ack.accepted} message={ack.message!r}")
            results.append(False)

        # ── Case 3: valid update ──────────────────────────────────────────────
        # client-0, round=1, lần đầu → accept
        ack = stub.SubmitUpdate(_make_update(client_id="client-0", round_id=1))
        if ack.accepted:
            _pass(3, f"valid update accepted (server_round={ack.server_round})")
            results.append(True)
        else:
            _fail(3, "valid update should be accepted",
                  f"accepted={ack.accepted} message={ack.message!r}")
            results.append(False)

        # ── Case 4: duplicate update ──────────────────────────────────────────
        # client-0 submit lần 2 → fail ở check 4 (duplicate)
        # Server vẫn TRAINING (mới có 1/2 update) nên không trigger aggregation
        ack = stub.SubmitUpdate(_make_update(client_id="client-0", round_id=1))
        if not ack.accepted and "duplicate_update" in ack.message:
            _pass(4, f"duplicate rejected: {ack.message!r}")
            results.append(True)
        else:
            _fail(4, "duplicate update should be rejected",
                  f"accepted={ack.accepted} message={ack.message!r}")
            results.append(False)

    return all(results)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="M3.8: stale update validation test (m3_plan.md §9.2)"
    )
    parser.add_argument(
        "--server-addr",
        default="127.0.0.1:50051",
        help="địa chỉ server host:port (default=127.0.0.1:50051)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("M3.8 — Stale Update Validation Test")
    print("=" * 60)
    print("NOTE: chạy trước khi bất kỳ client thật nào submit.")
    print("      Restart server trước khi chạy full smoke test M3.7.")

    passed = run_tests(args.server_addr)

    print()
    if passed:
        print("=" * 60)
        print("RESULT: ALL 4 CASES PASSED ✓")
        print("=" * 60)
        print("NOTE: server còn lưu update của client-0 (case 3).")
        print("      Restart server trước khi chạy smoke test M3.7.")
        sys.exit(0)
    else:
        print("=" * 60)
        print("RESULT: SOME CASES FAILED ✗")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
