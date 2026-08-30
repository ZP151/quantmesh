import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

import quantmesh.ops.immutable_runs as immutable_module
from quantmesh.ops.immutable_runs import (
    DailyRunReceiptV1,
    DailyRunStatus,
    ImmutableRunConflictError,
    ImmutableRunStore,
    LeaseHeldError,
    LeaseOwner,
    SlotLease,
    SoakVerificationProof,
)

NOW = datetime(2026, 8, 31, 1, tzinfo=UTC)


def _receipt(
    *,
    slot: str = "2026-08-31",
    status: DailyRunStatus = DailyRunStatus.PASSED,
) -> DailyRunReceiptV1:
    values = {
        "slot": slot,
        "attempt": 1,
        "started_at": NOW,
        "finished_at": NOW + timedelta(minutes=3),
        "status": status,
        "code_commit": "a" * 40,
        "source_contract_id": "b" * 64,
    }
    if status is DailyRunStatus.PASSED:
        values.update(
            {
                "hyperliquid_receipt_id": "c" * 64,
                "moomoo_receipt_id": "d" * 64,
                "soak_report_id": "e" * 64,
                "verification": SoakVerificationProof(
                    accepted=True,
                    reasons=(),
                    candidate_id="f" * 64,
                    report_count=1,
                    observed_hours=0,
                    xnys_session_count=1,
                ),
            }
        )
    else:
        values.update(
            {
                "failure_stage": "collect-moomoo",
                "failure_code": "deadline-exceeded",
                "detail": "bounded child exceeded its deadline",
            }
        )
    return DailyRunReceiptV1.build(**values)


def test_terminal_receipt_is_create_once_and_exact_retry_is_idempotent(
    tmp_path: Path,
) -> None:
    store = ImmutableRunStore(tmp_path)
    receipt = _receipt()

    store.publish_terminal(receipt)
    store.publish_terminal(receipt)

    assert store.load_terminal(receipt.slot, receipt.attempt) == receipt
    assert store.latest() == receipt
    assert store.receipt_path(receipt.receipt_id).read_bytes() == receipt.canonical_bytes()


def test_terminal_receipt_rejects_conflicting_overwrite(tmp_path: Path) -> None:
    store = ImmutableRunStore(tmp_path)
    store.publish_terminal(_receipt())
    conflict = _receipt(status=DailyRunStatus.FAILED)

    with pytest.raises(ImmutableRunConflictError, match="terminal"):
        store.publish_terminal(conflict)

    assert store.latest().status is DailyRunStatus.PASSED


def test_terminal_retry_recovers_crash_after_authoritative_receipt_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ImmutableRunStore(tmp_path)
    receipt = _receipt()
    original = immutable_module._publish_create_once
    calls = 0

    def crash_on_terminal(path: Path, payload: bytes, *, conflict_label: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt("injected terminal-index crash")
        original(path, payload, conflict_label=conflict_label)

    with monkeypatch.context() as context:
        context.setattr(immutable_module, "_publish_create_once", crash_on_terminal)
        with pytest.raises(KeyboardInterrupt, match="injected"):
            store.publish_terminal(receipt)

    assert store.receipt_path(receipt.receipt_id).exists()
    assert not store.terminal_path(receipt.slot, receipt.attempt).exists()

    store.publish_terminal(receipt)
    assert store.load_terminal(receipt.slot, receipt.attempt) == receipt


def test_latest_pointer_forms_a_verified_digest_chain(tmp_path: Path) -> None:
    store = ImmutableRunStore(tmp_path)
    first = _receipt(slot="2026-08-30")
    second = _receipt(slot="2026-08-31")

    store.publish_terminal(first)
    first_pointer = store.load_latest_pointer()
    store.publish_terminal(second)
    second_pointer = store.load_latest_pointer()

    assert second_pointer.prior_pointer_digest == first_pointer.pointer_digest
    assert second_pointer.receipt_id == second.receipt_id
    assert store.latest() == second

    payload = json.loads(store.latest_path.read_text(encoding="utf-8"))
    payload["receipt_id"] = "0" * 64
    store.latest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="pointer"):
        store.latest()


def test_slot_lease_is_exclusive_and_owner_can_release(tmp_path: Path) -> None:
    owner = LeaseOwner.current(token="owner-a", process_start_token="process-a")
    contender = LeaseOwner.current(token="owner-b", process_start_token="process-a")
    first = SlotLease.acquire(tmp_path, "2026-08-31", owner=owner, now=NOW)

    with pytest.raises(LeaseHeldError, match="held"):
        SlotLease.acquire(tmp_path, "2026-08-31", owner=contender, now=NOW)

    first.release()
    second = SlotLease.acquire(tmp_path, "2026-08-31", owner=contender, now=NOW)
    second.release()


def test_stale_slot_lease_requires_dead_owner_proof_before_recovery(
    tmp_path: Path,
) -> None:
    stale_owner = LeaseOwner(
        pid=999_999,
        token="stale-owner",
        process_start_token="old-process",
    )
    lease = SlotLease.acquire(tmp_path, "2026-08-31", owner=stale_owner, now=NOW)
    del lease
    replacement = LeaseOwner.current(
        token="replacement",
        process_start_token="new-process",
    )
    later = NOW + timedelta(hours=2)

    with pytest.raises(LeaseHeldError, match="owner is still alive"):
        SlotLease.acquire(
            tmp_path,
            "2026-08-31",
            owner=replacement,
            now=later,
            stale_after=timedelta(minutes=30),
            owner_alive=lambda owner: True,
        )

    recovered = SlotLease.acquire(
        tmp_path,
        "2026-08-31",
        owner=replacement,
        now=later,
        stale_after=timedelta(minutes=30),
        owner_alive=lambda owner: False,
    )
    assert recovered.record.owner == replacement
    recovered.release()


def test_owner_liveness_rejects_a_reused_pid_with_different_start_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = LeaseOwner(
        pid=1234,
        token="old-owner",
        process_start_token="os-start:111",
    )
    monkeypatch.setattr(immutable_module, "_pid_exists", lambda pid: pid == 1234)
    monkeypatch.setattr(
        immutable_module, "_process_start_token", lambda pid: "os-start:222"
    )

    assert immutable_module._owner_is_alive(owner) is False


def test_run_store_rejects_hard_linked_receipt(tmp_path: Path) -> None:
    store = ImmutableRunStore(tmp_path)
    receipt = _receipt()
    store.publish_terminal(receipt)
    alias = tmp_path / "receipt-alias.json"
    try:
        os.link(store.receipt_path(receipt.receipt_id), alias)
    except OSError as error:
        pytest.skip(f"hard-link creation unavailable: {error}")

    with pytest.raises(ValueError, match="hard link"):
        store.load_terminal(receipt.slot, receipt.attempt)


def test_run_store_rejects_symlinked_root_without_target_mutation(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "linked"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")

    try:
        with pytest.raises(ValueError, match="reparse"):
            ImmutableRunStore(linked).publish_terminal(_receipt())
        assert list(outside.iterdir()) == []
    finally:
        linked.unlink(missing_ok=True)
