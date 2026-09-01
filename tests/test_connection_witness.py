import hashlib
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

import quantmesh.ops.connection_witness as witness
from quantmesh.ops.connection_witness import (
    ConnectionProbeOutcome,
    ConnectionProbeResult,
    ConnectionWitnessConfig,
    ConnectionWitnessReceiptV1,
    ConnectionWitnessStatus,
    ConnectionWitnessStore,
    ExecutionKind,
    FormalTaskSnapshot,
    FormalTaskState,
    SlotAuthority,
    interpret_formal_task,
    run_connection_witness,
)
from quantmesh.ops.immutable_runs import (
    DailyRunReceiptV1,
    DailyRunStatus,
    ImmutableRunStore,
    LeaseHeldError,
    LeaseOwner,
    SoakVerificationProof,
)
from quantmesh.ops.processes import ProcessResult
from quantmesh.ops.trusted_data_soak import (
    SoakCandidateV2,
    SoakReportV2,
    SoakStoreV2,
    SoakTargetEvidenceV2,
)

NOW = datetime(2026, 9, 1, 2, 10, tzinfo=UTC)
DAILY_START = datetime(2026, 9, 1, 0, 0, 2, tzinfo=UTC)
COMMIT = "a" * 40
SOURCE_ID = "b" * 64
SLOT = "2026-09-01T02:10Z"


def _id(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _write_report(root: Path) -> SoakReportV2:
    targets = (
        ("AAPL", "moomoo-opend", "moomoo:US:AAPL:XNAS", "1d"),
        ("BTC", "hyperliquid-public", "hyperliquid:perp:BTC", "1m"),
        ("ETH", "hyperliquid-public", "hyperliquid:perp:ETH", "1m"),
        ("NVDA", "moomoo-opend", "moomoo:US:NVDA:XNAS", "1d"),
        ("SOL", "hyperliquid-public", "hyperliquid:perp:SOL", "1m"),
    )
    evidence = tuple(
        sorted(
            (
                SoakTargetEvidenceV2(
                    target_id=f"{provider}:{target}",
                    provider=provider,
                    target=target,
                    canonical_instrument=instrument,
                    interval=interval,
                    raw_manifest_id=_id(f"{target}:raw"),
                    normalized_manifest_id=_id(f"{target}:normalized"),
                    adjusted_manifest_id=_id(f"{target}:adjusted"),
                    feature_manifest_id=_id(f"{target}:feature"),
                    job_id=_id(f"{target}:job"),
                    run_id=_id(f"{target}:run"),
                    attempt=1,
                    quality_report_id=_id(f"{target}:quality-report"),
                    quality_evaluation_id=_id(f"{target}:quality-evaluation"),
                    checkpoint_digest=_id(f"{target}:checkpoint"),
                    event_end=DAILY_START,
                )
                for target, provider, instrument, interval in targets
            ),
            key=lambda item: item.target_id,
        )
    )
    candidate = SoakCandidateV2.build(
        started_at=DAILY_START,
        source_contract_id=SOURCE_ID,
        code_commit=COMMIT,
        policy_ids=(_id("policy"),),
        calendar_versions=("XNYS@2026.1",),
        schema_versions=("bars@1",),
        required_targets=tuple(sorted(item.target_id for item in evidence)),
    )
    store = SoakStoreV2(root)
    store.write_candidate(candidate, now=candidate.started_at)
    report = SoakReportV2.build(
        candidate_id=candidate.candidate_id,
        source_contract_id=SOURCE_ID,
        code_commit=COMMIT,
        config_digest=candidate.config_digest,
        recorded_at=DAILY_START + timedelta(minutes=5),
        report_date=DAILY_START.date().isoformat(),
        predecessor_report_id=None,
        collection_receipt_ids=tuple(sorted((_id("hyper"), _id("moomoo")))),
        manifest_ids=tuple(
            sorted(
                manifest_id
                for item in evidence
                for manifest_id in (
                    item.raw_manifest_id,
                    item.normalized_manifest_id,
                    item.adjusted_manifest_id,
                    item.feature_manifest_id,
                )
            )
        ),
        quality_evaluation_ids=tuple(sorted(item.quality_evaluation_id for item in evidence)),
        checkpoint_digests=tuple(sorted(item.checkpoint_digest for item in evidence)),
        target_evidence=evidence,
        completed_xnys_sessions=("2026-08-31",),
        crypto_observed=True,
        critical_issues=(),
    )
    store.append(report, now=report.recorded_at)
    return report


def _publish_daily(
    run_root: Path,
    report: SoakReportV2,
    *,
    attempt: int = 1,
    started_at: datetime = DAILY_START,
    status: DailyRunStatus = DailyRunStatus.PASSED,
    commit: str = COMMIT,
    source_id: str = SOURCE_ID,
) -> DailyRunReceiptV1:
    values = {
        "slot": DAILY_START.date().isoformat(),
        "attempt": attempt,
        "started_at": started_at,
        "finished_at": started_at + timedelta(minutes=2),
        "status": status,
        "code_commit": commit,
        "source_contract_id": source_id,
    }
    if status is DailyRunStatus.PASSED:
        values.update(
            {
                "hyperliquid_receipt_id": _id(f"hyper:{attempt}"),
                "moomoo_receipt_id": _id(f"moomoo:{attempt}"),
                "soak_report_id": report.report_id,
                "verification": SoakVerificationProof(
                    accepted=True,
                    reasons=(),
                    candidate_id=report.candidate_id,
                    report_count=1,
                    observed_hours=0,
                    xnys_session_count=1,
                ),
            }
        )
    else:
        values.update(
            {
                "failure_stage": "verify",
                "failure_code": "verification-rejected",
                "detail": "the exact daily verifier rejected",
            }
        )
    receipt = DailyRunReceiptV1.build(**values)
    ImmutableRunStore(run_root).publish_terminal(receipt)
    return receipt


def _snapshot(
    *,
    task_name: str = "QuantMesh Daily Soak",
    enabled: bool = True,
    state: str = "Ready",
    result: int = 0,
    last_run_time: datetime | None = DAILY_START,
) -> FormalTaskSnapshot:
    return FormalTaskSnapshot(
        task_name=task_name,
        enabled=enabled,
        state=state,
        last_task_result=result,
        last_run_time=last_run_time,
    )


def _interpret(
    tmp_path: Path,
    snapshot: FormalTaskSnapshot | None,
    *,
    now: datetime = NOW,
):
    return interpret_formal_task(
        snapshot,
        now=now,
        daily_store=ImmutableRunStore(tmp_path / "daily-runs"),
        report_root=tmp_path / "reports",
        expected_commit=COMMIT,
        expected_source_contract_id=SOURCE_ID,
        formal_deadline_seconds=3600,
        stale_after_seconds=93600,
        match_early_seconds=120,
        match_late_seconds=900,
    )


@pytest.mark.parametrize(
    ("snapshot", "now", "state", "code"),
    (
        (
            _snapshot(state="Running", result=0x41301),
            DAILY_START + timedelta(minutes=59),
            FormalTaskState.IN_PROGRESS,
            "formal-task-in-progress",
        ),
        (
            _snapshot(state="Running", result=0x41301),
            DAILY_START + timedelta(hours=1, seconds=1),
            FormalTaskState.FAILED,
            "formal-task-overdue",
        ),
        (
            _snapshot(result=0x41306),
            NOW,
            FormalTaskState.FAILED,
            "formal-task-terminated",
        ),
        (
            _snapshot(enabled=False),
            NOW,
            FormalTaskState.FAILED,
            "formal-task-disabled",
        ),
        (
            _snapshot(last_run_time=None),
            NOW,
            FormalTaskState.FAILED,
            "formal-task-never-ran",
        ),
        (
            _snapshot(last_run_time=NOW + timedelta(seconds=1)),
            NOW,
            FormalTaskState.FAILED,
            "formal-task-future-dated",
        ),
        (
            _snapshot(last_run_time=NOW - timedelta(hours=26, seconds=1)),
            NOW,
            FormalTaskState.FAILED,
            "formal-task-stale",
        ),
    ),
)
def test_formal_task_state_table_fails_closed(
    tmp_path: Path,
    snapshot: FormalTaskSnapshot,
    now: datetime,
    state: FormalTaskState,
    code: str,
) -> None:
    interpreted = _interpret(tmp_path, snapshot, now=now)

    assert interpreted.state is state
    assert interpreted.code == code
    assert interpreted.daily_receipt_id is None


def test_completed_zero_requires_exact_daily_report_source_and_latest_pointer(
    tmp_path: Path,
) -> None:
    report = _write_report(tmp_path / "reports")
    receipt = _publish_daily(tmp_path / "daily-runs", report)

    interpreted = _interpret(tmp_path, _snapshot())

    assert interpreted.state is FormalTaskState.PASSED
    assert interpreted.code == "formal-task-passed"
    assert interpreted.daily_receipt_id == receipt.receipt_id
    assert interpreted.soak_report_id == report.report_id


def test_completed_zero_rejects_missing_ambiguous_and_newer_nonpassing_receipts(
    tmp_path: Path,
) -> None:
    report = _write_report(tmp_path / "reports")
    assert _interpret(tmp_path, _snapshot()).code == "daily-receipt-missing"

    _publish_daily(tmp_path / "daily-runs", report, attempt=1)
    _publish_daily(
        tmp_path / "daily-runs",
        report,
        attempt=2,
        started_at=DAILY_START + timedelta(seconds=30),
    )
    assert _interpret(tmp_path, _snapshot()).code == "daily-receipt-ambiguous"

    other = tmp_path / "newer-failure"
    other_report = _write_report(other / "reports")
    _publish_daily(other / "daily-runs", other_report, attempt=1)
    _publish_daily(
        other / "daily-runs",
        other_report,
        attempt=2,
        started_at=DAILY_START + timedelta(hours=1),
        status=DailyRunStatus.FAILED,
    )
    assert _interpret(other, _snapshot()).code == "daily-receipt-not-latest"


def test_completed_zero_rejects_source_or_report_substitution(tmp_path: Path) -> None:
    report = _write_report(tmp_path / "reports")
    _publish_daily(tmp_path / "daily-runs", report, commit="c" * 40)

    assert _interpret(tmp_path, _snapshot()).code == "daily-source-mismatch"

    valid = tmp_path / "missing-report"
    _publish_daily(valid / "daily-runs", report)
    assert _interpret(valid, _snapshot()).code == "daily-report-invalid"


def _config(
    tmp_path: Path,
    *,
    execution_kind: ExecutionKind = ExecutionKind.SCHEDULED,
    scheduled_slot: str | None = None,
) -> ConnectionWitnessConfig:
    return ConnectionWitnessConfig(
        repo=tmp_path,
        report_root=tmp_path / "reports",
        daily_run_root=tmp_path / "daily-runs",
        connection_run_root=tmp_path / "connection-runs",
        formal_task_name="QuantMesh Daily Soak",
        connection_task_name="QuantMesh Connection Witness",
        expected_commit=COMMIT,
        expected_source_contract_id=SOURCE_ID,
        execution_kind=execution_kind,
        scheduled_slot=scheduled_slot,
        formal_deadline_seconds=3600,
        stale_after_seconds=93600,
        match_early_seconds=120,
        match_late_seconds=900,
        python_timeout_seconds=5,
        tcp_timeout_seconds=5,
        scheduler_timeout_seconds=5,
        daily_receipt_timeout_seconds=5,
        moomoo_timeout_seconds=5,
        hyperliquid_timeout_seconds=5,
    )


def _pass(name: str) -> ConnectionProbeResult:
    return ConnectionProbeResult(
        name=name,
        outcome=ConnectionProbeOutcome.PASSED,
        code=f"{name}-passed",
        detail=f"{name} read-only probe passed",
        elapsed_seconds=0.1,
        tree_terminated=False,
    )


def _install_probes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    formal: FormalTaskSnapshot,
    moomoo: ConnectionProbeResult | None = None,
    tcp: ConnectionProbeResult | None = None,
) -> list[str]:
    calls: list[str] = []

    def scheduler(config: ConnectionWitnessConfig, task_name: str):
        calls.append(f"scheduler:{task_name}")
        if task_name == config.connection_task_name:
            return _snapshot(
                task_name=task_name,
                state="Running",
                result=0x41301,
                last_run_time=NOW,
            )
        return formal

    def probe(name: str, result: ConnectionProbeResult):
        def run(_config: ConnectionWitnessConfig):
            calls.append(name)
            return result

        return run

    monkeypatch.setattr(witness, "_now", lambda: NOW)
    monkeypatch.setattr(witness, "_read_scheduler_task", scheduler)
    monkeypatch.setattr(witness, "_probe_python", probe("python", _pass("python")))
    monkeypatch.setattr(
        witness, "_probe_tcp", probe("tcp", tcp if tcp is not None else _pass("tcp"))
    )
    monkeypatch.setattr(
        witness,
        "_probe_moomoo",
        probe("moomoo", moomoo if moomoo is not None else _pass("moomoo")),
    )
    monkeypatch.setattr(
        witness,
        "_probe_hyperliquid",
        probe("hyperliquid", _pass("hyperliquid")),
    )
    return calls


def test_in_progress_persists_zero_outcome_without_starting_moomoo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_probes(
        monkeypatch,
        formal=_snapshot(state="Running", result=0x41301, last_run_time=NOW),
    )
    monkeypatch.setattr(
        witness,
        "_probe_moomoo",
        lambda _config: pytest.fail("Moomoo must be suppressed while formal task runs"),
    )

    receipt = run_connection_witness(_config(tmp_path))

    assert receipt.status is ConnectionWitnessStatus.IN_PROGRESS
    assert receipt.formal_state is FormalTaskState.IN_PROGRESS
    assert "moomoo" not in calls
    assert {item.name for item in receipt.probes} == {
        "hyperliquid",
        "moomoo",
        "python",
        "scheduler",
        "tcp",
    }
    moomoo = next(item for item in receipt.probes if item.name == "moomoo")
    assert moomoo.outcome is ConnectionProbeOutcome.SKIPPED
    assert ConnectionWitnessStore(tmp_path / "connection-runs").latest() == receipt


def test_logged_out_moomoo_is_blocked_user_auth_and_mutates_no_report_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _write_report(tmp_path / "reports")
    _publish_daily(tmp_path / "daily-runs", report)
    before = tuple(
        sorted(path.relative_to(tmp_path / "reports") for path in (tmp_path / "reports").rglob("*"))
    )
    blocked = ConnectionProbeResult(
        name="moomoo",
        outcome=ConnectionProbeOutcome.FAILED,
        code="blocked-user-auth",
        detail="OpenD is logged out",
        elapsed_seconds=0.2,
        tree_terminated=False,
    )
    _install_probes(monkeypatch, formal=_snapshot(), moomoo=blocked)

    receipt = run_connection_witness(_config(tmp_path))

    assert receipt.status is ConnectionWitnessStatus.BLOCKED_USER_AUTH
    assert receipt.failure_code == "blocked-user-auth"
    after = tuple(
        sorted(path.relative_to(tmp_path / "reports") for path in (tmp_path / "reports").rglob("*"))
    )
    assert after == before


def test_scheduler_exception_and_probe_timeout_still_publish_terminal_receipts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_probes(monkeypatch, formal=_snapshot())
    original = witness._read_scheduler_task

    def scheduler(config: ConnectionWitnessConfig, task_name: str):
        if task_name == config.formal_task_name:
            raise RuntimeError("scheduler RPC failed")
        return original(config, task_name)

    monkeypatch.setattr(witness, "_read_scheduler_task", scheduler)
    failed = run_connection_witness(_config(tmp_path))
    assert failed.status is ConnectionWitnessStatus.FAILED
    assert failed.failure_code == "scheduler-exception"
    assert ConnectionWitnessStore(tmp_path / "connection-runs").latest() == failed
    assert "hyperliquid" in calls

    timed_root = tmp_path / "timed"
    report = _write_report(timed_root / "reports")
    _publish_daily(timed_root / "daily-runs", report)
    timeout = ConnectionProbeResult(
        name="tcp",
        outcome=ConnectionProbeOutcome.TIMED_OUT,
        code="tcp-deadline-exceeded",
        detail="loopback TCP probe timed out",
        elapsed_seconds=5,
        tree_terminated=True,
    )
    _install_probes(monkeypatch, formal=_snapshot(), tcp=timeout)
    timed = run_connection_witness(_config(timed_root))
    assert timed.status is ConnectionWitnessStatus.TIMED_OUT
    assert timed.failure_code == "tcp-deadline-exceeded"
    assert next(item for item in timed.probes if item.name == "tcp").tree_terminated
    assert ConnectionWitnessStore(timed_root / "connection-runs").latest() == timed


def test_daily_receipt_readback_overrun_is_typed_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_probes(monkeypatch, formal=_snapshot())

    def timeout_child(argv, *, timeout_seconds: float, cwd: Path):
        command = tuple(argv)
        assert "_formal_child_main" in command[2]
        assert timeout_seconds == 0.001
        assert cwd == tmp_path
        return ProcessResult(
            argv=command,
            returncode=-9,
            stdout="",
            stderr="",
            elapsed_seconds=0.001,
            timed_out=True,
            tree_terminated=True,
        )

    monkeypatch.setattr(witness, "run_process", timeout_child)
    config = _config(tmp_path).model_copy(update={"daily_receipt_timeout_seconds": 0.001})

    receipt = run_connection_witness(config)

    assert receipt.status is ConnectionWitnessStatus.TIMED_OUT
    assert receipt.failure_code == "daily-receipt-deadline-exceeded"
    scheduler = next(item for item in receipt.probes if item.name == "scheduler")
    assert scheduler.tree_terminated is True


def test_failed_scheduled_slot_and_supplemental_success_are_both_immutable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_probes(monkeypatch, formal=_snapshot(result=0x41306))
    failed = run_connection_witness(_config(tmp_path))
    assert failed.status is ConnectionWitnessStatus.FAILED

    report = _write_report(tmp_path / "reports")
    _publish_daily(tmp_path / "daily-runs", report)
    _install_probes(monkeypatch, formal=_snapshot())
    recovered = run_connection_witness(
        _config(
            tmp_path,
            execution_kind=ExecutionKind.SUPPLEMENTAL,
            scheduled_slot=SLOT,
        )
    )

    store = ConnectionWitnessStore(tmp_path / "connection-runs")
    assert [(item.attempt, item.execution_kind, item.status) for item in store.terminals(SLOT)] == [
        (1, ExecutionKind.SCHEDULED, ConnectionWitnessStatus.FAILED),
        (2, ExecutionKind.SUPPLEMENTAL, ConnectionWitnessStatus.PASSED),
    ]
    assert store.load_terminal(SLOT, 1) == failed
    assert store.latest() == recovered


def test_concurrent_attempt_reservations_never_reuse_a_path(tmp_path: Path) -> None:
    store = ConnectionWitnessStore(tmp_path)
    lease = store.acquire_slot(
        SLOT,
        owner=LeaseOwner(pid=111, token="allocator", process_start_token="test"),
        now=NOW,
        stale_after=timedelta(minutes=15),
    )

    with ThreadPoolExecutor(max_workers=8) as pool:
        reservations = tuple(
            pool.map(
                lambda _: store.reserve_attempt(
                    SLOT,
                    lease=lease,
                    execution_kind=ExecutionKind.SUPPLEMENTAL,
                    slot_authority=SlotAuthority.EXPLICIT_SUPPLEMENTAL,
                    started_at=NOW,
                ),
                range(16),
            )
        )

    assert sorted(item.attempt for item in reservations) == list(range(1, 17))
    assert len({item.reservation_id for item in reservations}) == 16
    assert all(store.reservation_path(SLOT, item.attempt).exists() for item in reservations)
    lease.release()


def test_terminal_before_pointer_crash_is_retryable_without_overwrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = ConnectionWitnessStore(tmp_path)
    lease = store.acquire_slot(
        SLOT,
        owner=LeaseOwner(pid=111, token="publisher", process_start_token="test"),
        now=NOW,
        stale_after=timedelta(minutes=15),
    )
    reservation = store.reserve_attempt(
        SLOT,
        lease=lease,
        execution_kind=ExecutionKind.SUPPLEMENTAL,
        slot_authority=SlotAuthority.EXPLICIT_SUPPLEMENTAL,
        started_at=NOW,
    )
    receipt = ConnectionWitnessReceiptV1.build(
        slot=SLOT,
        attempt=reservation.attempt,
        execution_kind=reservation.execution_kind,
        slot_authority=reservation.slot_authority,
        reservation_id=reservation.reservation_id,
        started_at=reservation.started_at,
        finished_at=NOW + timedelta(seconds=1),
        status=ConnectionWitnessStatus.PASSED,
        expected_commit=COMMIT,
        expected_source_contract_id=SOURCE_ID,
        formal_state=FormalTaskState.PASSED,
        formal_code="formal-task-passed",
        formal_last_run_time=DAILY_START,
        daily_receipt_id=_id("daily"),
        soak_report_id=_id("report"),
        probes=tuple(
            _pass(name) for name in ("hyperliquid", "moomoo", "python", "scheduler", "tcp")
        ),
        failure_code=None,
        detail=None,
    )
    original = witness.atomic_replace

    def crash(path: Path, payload: bytes) -> None:
        if path == store.latest_path:
            raise RuntimeError("injected pointer crash")
        original(path, payload)

    with monkeypatch.context() as context:
        context.setattr(witness, "atomic_replace", crash)
        with pytest.raises(RuntimeError, match="pointer crash"):
            store.publish_terminal(receipt)

    assert store.load_terminal(SLOT, 1) == receipt
    assert not store.latest_path.exists()
    store.publish_terminal(receipt)
    assert store.latest() == receipt
    lease.release()


def test_interruption_is_persisted_before_keyboard_interrupt_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_probes(monkeypatch, formal=_snapshot())
    monkeypatch.setattr(
        witness,
        "_probe_python",
        lambda _config: (_ for _ in ()).throw(KeyboardInterrupt("stop")),
    )

    with pytest.raises(KeyboardInterrupt, match="stop"):
        run_connection_witness(_config(tmp_path))

    terminal = ConnectionWitnessStore(tmp_path / "connection-runs").latest()
    assert terminal.status is ConnectionWitnessStatus.INTERRUPTED
    assert terminal.failure_code == "connection-witness-interrupted"


def test_child_probe_commands_are_read_only_and_propagate_tree_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[tuple[str, ...]] = []

    def run(argv, *, timeout_seconds: float, cwd: Path):
        assert timeout_seconds == 5
        assert cwd == tmp_path
        command = tuple(argv)
        commands.append(command)
        is_moomoo = "quantmesh.moomoo.cli" in command
        return ProcessResult(
            argv=command,
            returncode=-9 if is_moomoo else 0,
            stdout="",
            stderr="",
            elapsed_seconds=5 if is_moomoo else 0.1,
            timed_out=is_moomoo,
            tree_terminated=is_moomoo,
        )

    monkeypatch.setattr(witness, "run_process", run)
    config = _config(tmp_path)

    moomoo = witness._probe_moomoo(config)
    hyperliquid = witness._probe_hyperliquid(config)

    assert moomoo.outcome is ConnectionProbeOutcome.TIMED_OUT
    assert moomoo.tree_terminated is True
    assert commands[0][-3:] == ("-m", "quantmesh.moomoo.cli", "probe")
    assert "PublicInfoTransport" in commands[1][-1]
    assert ".l2_book('BTC')" in commands[1][-1]
    assert hyperliquid.outcome is ConnectionProbeOutcome.PASSED


def test_supplemental_slot_is_explicit_and_scheduled_mode_cannot_spoof_it(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValidationError, match="scheduled_slot"):
        _config(tmp_path, execution_kind=ExecutionKind.SUPPLEMENTAL)
    with pytest.raises(ValidationError, match="scheduled_slot"):
        _config(
            tmp_path,
            execution_kind=ExecutionKind.SCHEDULED,
            scheduled_slot=SLOT,
        )


def test_zero_outcome_requires_complete_named_probe_contract(tmp_path: Path) -> None:
    store = ConnectionWitnessStore(tmp_path)
    lease = store.acquire_slot(
        SLOT,
        owner=LeaseOwner(pid=111, token="contract", process_start_token="test"),
        now=NOW,
        stale_after=timedelta(minutes=15),
    )
    reservation = store.reserve_attempt(
        SLOT,
        lease=lease,
        execution_kind=ExecutionKind.SUPPLEMENTAL,
        slot_authority=SlotAuthority.EXPLICIT_SUPPLEMENTAL,
        started_at=NOW,
    )

    with pytest.raises(ValidationError, match="every named probe"):
        ConnectionWitnessReceiptV1.build(
            slot=SLOT,
            attempt=reservation.attempt,
            execution_kind=reservation.execution_kind,
            slot_authority=reservation.slot_authority,
            reservation_id=reservation.reservation_id,
            started_at=reservation.started_at,
            finished_at=NOW + timedelta(seconds=1),
            status=ConnectionWitnessStatus.PASSED,
            expected_commit=COMMIT,
            expected_source_contract_id=SOURCE_ID,
            formal_state=FormalTaskState.PASSED,
            formal_code="formal-task-passed",
            formal_last_run_time=DAILY_START,
            daily_receipt_id=_id("daily"),
            soak_report_id=_id("report"),
            probes=(_pass("scheduler"),),
            failure_code=None,
            detail=None,
        )
    lease.release()


def test_unreadable_scheduler_self_uses_nonqualifying_fallback_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_probes(monkeypatch, formal=_snapshot())
    original = witness._read_scheduler_task

    def scheduler(config: ConnectionWitnessConfig, task_name: str):
        if task_name == config.connection_task_name:
            raise RuntimeError("self query denied")
        return original(config, task_name)

    monkeypatch.setattr(witness, "_read_scheduler_task", scheduler)

    receipt = run_connection_witness(_config(tmp_path))

    assert receipt.status is ConnectionWitnessStatus.FAILED
    assert receipt.slot_authority is SlotAuthority.FALLBACK_FAILURE
    assert receipt.failure_code == "scheduler-self-exception"
    assert calls == []


def test_connection_slot_lease_blocks_live_owner_and_recovers_dead_stale_owner(
    tmp_path: Path,
) -> None:
    store = ConnectionWitnessStore(tmp_path)
    stale_owner = LeaseOwner(pid=111, token="stale", process_start_token="old")
    active_owner = LeaseOwner(pid=222, token="active", process_start_token="new")
    stale = store.acquire_slot(
        SLOT,
        owner=stale_owner,
        now=NOW,
        stale_after=timedelta(seconds=1),
        owner_alive=lambda _owner: True,
    )
    with pytest.raises(LeaseHeldError, match="held by another owner"):
        store.acquire_slot(
            SLOT,
            owner=active_owner,
            now=NOW,
            stale_after=timedelta(seconds=1),
            owner_alive=lambda _owner: True,
        )

    recovered = store.acquire_slot(
        SLOT,
        owner=active_owner,
        now=NOW + timedelta(seconds=2),
        stale_after=timedelta(seconds=1),
        owner_alive=lambda owner: owner != stale_owner,
    )
    assert recovered.record.owner == active_owner
    assert not tuple(stale.path.parent.glob("*.recovered"))
    recovered.release()


def test_connection_roots_must_be_absolute_and_disjoint(tmp_path: Path) -> None:
    values = _config(tmp_path).model_dump()
    with pytest.raises(ValidationError, match="absolute"):
        ConnectionWitnessConfig(**{**values, "repo": Path("relative")})

    with pytest.raises(ValidationError, match="disjoint"):
        ConnectionWitnessConfig(
            **{
                **values,
                "daily_run_root": tmp_path / "reports" / "daily",
            }
        )


@pytest.mark.skipif(os.name != "nt", reason="PowerShell wrapper is Windows-only")
def test_powershell_wrapper_forwards_every_authority_and_deadline_argument(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    python = repo / ".venv" / "Scripts" / "python.exe"
    driver = repo / "tools" / "connection_witness.py"
    python.parent.mkdir(parents=True)
    driver.parent.mkdir(parents=True)
    python.write_bytes(b"placeholder")
    driver.write_text("# placeholder", encoding="utf-8")
    roots = tuple(tmp_path / name for name in ("reports", "daily", "connection"))
    script = Path(__file__).parents[1] / "tools" / "connection_witness.ps1"

    result = subprocess.run(
        (
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-File",
            str(script),
            "-Repo",
            str(repo),
            "-ReportRoot",
            str(roots[0]),
            "-DailyRunRoot",
            str(roots[1]),
            "-ConnectionRunRoot",
            str(roots[2]),
            "-ExpectedCommit",
            COMMIT,
            "-ExpectedSourceContractId",
            SOURCE_ID,
            "-ExecutionKind",
            "supplemental",
            "-ScheduledSlot",
            SLOT,
            "-SlotIdentityMaxAgeSeconds",
            "123",
            "-SlotLeaseSeconds",
            "321",
            "-EmitInvocation",
        ),
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0, result.stderr
    invocation = json.loads(result.stdout)
    arguments = invocation["arguments"]
    assert invocation["python"] == str(python)
    expected_pairs = {
        "--repo": str(repo),
        "--report-root": str(roots[0]),
        "--daily-run-root": str(roots[1]),
        "--connection-run-root": str(roots[2]),
        "--expected-commit": COMMIT,
        "--expected-source-contract-id": SOURCE_ID,
        "--execution-kind": "supplemental",
        "--slot-identity-max-age-seconds": 123,
        "--slot-lease-seconds": 321,
        "--scheduled-slot": SLOT,
    }
    for flag, expected in expected_pairs.items():
        assert arguments[arguments.index(flag) + 1] == expected
