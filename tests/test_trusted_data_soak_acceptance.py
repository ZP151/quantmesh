import hashlib
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from quantmesh.ops.connection_witness import (
    ConnectionProbeOutcome,
    ConnectionProbeResult,
    ConnectionWitnessReceiptV1,
    ConnectionWitnessStatus,
    ConnectionWitnessStore,
    ExecutionKind,
    FormalTaskState,
    SlotAuthority,
)
from quantmesh.ops.immutable_runs import (
    DailyRunReceiptV1,
    DailyRunStatus,
    ImmutableRunStore,
    LeaseOwner,
    SoakVerificationProof,
)
from quantmesh.ops.soak_acceptance import (
    OperationalAcceptanceStore,
    main,
    required_connection_slots,
    verify_operational_soak,
)
from quantmesh.ops.trusted_data_soak import (
    SoakCandidateV2,
    SoakReportV2,
    SoakStoreV2,
    SoakTargetEvidenceV2,
    SoakVerification,
)
from quantmesh.ops.witness_outbox import (
    IneligibleWitnessError,
    WitnessIntentV1,
    WitnessKind,
    WitnessOutbox,
)

START = datetime(2026, 9, 1, 0, 5, tzinfo=UTC)
EVIDENCE_AS_OF = START + timedelta(days=7)
COMMIT = "a" * 40
SOURCE_ID = "b" * 64
OTHER_SOURCE_ID = "c" * 64


def _id(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _targets(day: int) -> tuple[SoakTargetEvidenceV2, ...]:
    definitions = (
        ("AAPL", "moomoo-opend", "moomoo:US:AAPL:XNAS", "1d"),
        ("BTC", "hyperliquid-public", "hyperliquid:perp:BTC", "1m"),
        ("ETH", "hyperliquid-public", "hyperliquid:perp:ETH", "1m"),
        ("NVDA", "moomoo-opend", "moomoo:US:NVDA:XNAS", "1d"),
        ("SOL", "hyperliquid-public", "hyperliquid:perp:SOL", "1m"),
    )
    return tuple(
        sorted(
            (
                SoakTargetEvidenceV2(
                    target_id=f"{provider}:{target}",
                    provider=provider,
                    target=target,
                    canonical_instrument=instrument,
                    interval=interval,
                    raw_manifest_id=_id(f"{day}:{target}:raw"),
                    normalized_manifest_id=_id(f"{day}:{target}:normalized"),
                    adjusted_manifest_id=_id(f"{day}:{target}:adjusted"),
                    feature_manifest_id=_id(f"{day}:{target}:feature"),
                    job_id=_id(f"{day}:{target}:job"),
                    run_id=_id(f"{day}:{target}:run"),
                    attempt=1,
                    quality_report_id=_id(f"{day}:{target}:quality-report"),
                    quality_evaluation_id=_id(f"{day}:{target}:quality-evaluation"),
                    checkpoint_digest=_id(f"{day}:{target}:checkpoint"),
                    event_end=START + timedelta(days=day),
                )
                for target, provider, instrument, interval in definitions
            ),
            key=lambda item: item.target_id,
        )
    )


def _write_reports(
    root: Path,
    *,
    candidate_started_at: datetime = START,
    report_started_at: datetime = START,
    report_offsets: tuple[timedelta, ...] | None = None,
) -> tuple[SoakCandidateV2, tuple[SoakReportV2, ...]]:
    first_targets = _targets(0)
    candidate = SoakCandidateV2.build(
        started_at=candidate_started_at,
        source_contract_id=SOURCE_ID,
        code_commit=COMMIT,
        policy_ids=(_id("policy"),),
        calendar_versions=("XNYS@2026.1",),
        schema_versions=("bars@1",),
        required_targets=tuple(item.target_id for item in first_targets),
    )
    store = SoakStoreV2(root)
    store.write_candidate(candidate, now=candidate_started_at)
    reports: list[SoakReportV2] = []
    sessions = ("2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03")
    offsets = report_offsets or tuple(timedelta(days=day) for day in range(8))
    for day, offset in enumerate(offsets):
        targets = _targets(day)
        recorded_at = report_started_at + offset
        report = SoakReportV2.build(
            candidate_id=candidate.candidate_id,
            source_contract_id=SOURCE_ID,
            code_commit=COMMIT,
            config_digest=candidate.config_digest,
            recorded_at=recorded_at,
            report_date=recorded_at.date().isoformat(),
            predecessor_report_id=None if not reports else reports[-1].report_id,
            collection_receipt_ids=tuple(
                sorted((_id(f"{day}:hyper"), _id(f"{day}:moomoo")))
            ),
            manifest_ids=tuple(
                sorted(
                    manifest_id
                    for item in targets
                    for manifest_id in (
                        item.raw_manifest_id,
                        item.normalized_manifest_id,
                        item.adjusted_manifest_id,
                        item.feature_manifest_id,
                    )
                )
            ),
            quality_evaluation_ids=tuple(
                sorted(item.quality_evaluation_id for item in targets)
            ),
            checkpoint_digests=tuple(
                sorted(item.checkpoint_digest for item in targets)
            ),
            target_evidence=targets,
            completed_xnys_sessions=(sessions[min(day, len(sessions) - 1)],),
            crypto_observed=True,
            critical_issues=(),
        )
        store.append(report, now=report.recorded_at)
        reports.append(report)
    return candidate, tuple(reports)


def _daily_terminal(
    report: SoakReportV2,
    *,
    candidate: SoakCandidateV2,
    index: int,
    attempt: int = 1,
    source_id: str = SOURCE_ID,
    recovery_of_run_id: str | None = None,
) -> DailyRunReceiptV1:
    started_at = report.recorded_at - timedelta(minutes=5) + timedelta(seconds=attempt - 1)
    return DailyRunReceiptV1.build(
        slot=report.report_date,
        attempt=attempt,
        started_at=started_at,
        finished_at=report.recorded_at + timedelta(minutes=1, seconds=attempt - 1),
        status=DailyRunStatus.PASSED,
        code_commit=COMMIT,
        source_contract_id=source_id,
        hyperliquid_receipt_id=report.collection_receipt_ids[0],
        moomoo_receipt_id=report.collection_receipt_ids[1],
        soak_report_id=report.report_id,
        verification=SoakVerificationProof(
            accepted=True,
            reasons=(),
            candidate_id=candidate.candidate_id,
            report_count=index + 1,
            observed_hours=index * 24,
            xnys_session_count=min(index + 1, 4),
        ),
        recovery_of_run_id=recovery_of_run_id,
    )


def _write_daily(
    root: Path,
    candidate: SoakCandidateV2,
    reports: tuple[SoakReportV2, ...],
    *,
    mode: str = "exact",
) -> tuple[DailyRunReceiptV1, ...]:
    terminals: list[DailyRunReceiptV1] = []
    for index, report in enumerate(reports):
        if mode == "missing-last" and index == len(reports) - 1:
            continue
        terminal = _daily_terminal(
            report,
            candidate=candidate,
            index=index,
            source_id=(
                OTHER_SOURCE_ID
                if mode == "wrong-source" and index == len(reports) - 1
                else SOURCE_ID
            ),
        )
        ImmutableRunStore(root).publish_terminal(terminal)
        terminals.append(terminal)
    if mode in {"duplicate-last", "valid-recovery"}:
        duplicate = _daily_terminal(
            reports[-1],
            candidate=candidate,
            index=len(reports) - 1,
            attempt=2,
            recovery_of_run_id=(terminals[-1].run_id if mode == "valid-recovery" else None),
        )
        ImmutableRunStore(root).publish_terminal(duplicate)
        terminals.append(duplicate)
    return tuple(terminals)


def _intent_for_daily(terminal: DailyRunReceiptV1) -> WitnessIntentV1:
    return WitnessIntentV1.build(
        issue_number=124,
        witness_kind=WitnessKind.DAILY_ACCEPTED,
        local_evidence_id=terminal.run_id,
        terminal_receipt_id=terminal.receipt_id,
        report_id=terminal.soak_report_id,
        source_contract_id=terminal.source_contract_id,
        code_commit=terminal.code_commit,
        occurred_at=terminal.finished_at,
        summary=f"daily slot {terminal.slot} attempt {terminal.attempt} accepted",
    )


def _probe(name: str) -> ConnectionProbeResult:
    return ConnectionProbeResult(
        name=name,
        outcome=ConnectionProbeOutcome.PASSED,
        code=f"{name}-passed",
        detail=f"{name} passed",
        elapsed_seconds=0.01,
        tree_terminated=False,
    )


def _slot_time(slot: str) -> datetime:
    return datetime.strptime(slot, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)


def _publish_connection(
    root: Path,
    slot: str,
    *,
    reports: tuple[SoakReportV2, ...],
    daily: tuple[DailyRunReceiptV1, ...],
    execution_kind: ExecutionKind = ExecutionKind.SCHEDULED,
    status: ConnectionWitnessStatus = ConnectionWitnessStatus.PASSED,
    start_delay_seconds: int = 2,
    source_id: str = SOURCE_ID,
) -> ConnectionWitnessReceiptV1:
    when = _slot_time(slot)
    reports_by_id = {report.report_id: report for report in reports}
    eligible = [
        (reports_by_id[terminal.soak_report_id], terminal)
        for terminal in daily
        if terminal.soak_report_id in reports_by_id
        and reports_by_id[terminal.soak_report_id].recorded_at <= when
    ]
    eligible.sort(key=lambda item: (item[0].recorded_at, item[1].attempt))
    report, terminal = eligible[-1]
    supplemental = execution_kind is ExecutionKind.SUPPLEMENTAL
    store = ConnectionWitnessStore(root)
    owner = LeaseOwner.current(token=_id(f"owner:{slot}:{execution_kind}"))
    with store.acquire_slot(
        slot,
        owner=owner,
        now=when,
        stale_after=timedelta(minutes=15),
    ) as lease:
        reservation = store.reserve_attempt(
            slot,
            lease=lease,
            execution_kind=execution_kind,
            slot_authority=(
                SlotAuthority.EXPLICIT_SUPPLEMENTAL
                if supplemental
                else SlotAuthority.SCHEDULER
            ),
            slot_source_time=(
                None if supplemental else when + timedelta(seconds=start_delay_seconds)
            ),
            started_at=when + timedelta(seconds=start_delay_seconds),
        )
        passed = status is ConnectionWitnessStatus.PASSED
        receipt = ConnectionWitnessReceiptV1.build(
            slot=slot,
            attempt=reservation.attempt,
            execution_kind=execution_kind,
            slot_authority=reservation.slot_authority,
            slot_source_time=reservation.slot_source_time,
            reservation_id=reservation.reservation_id,
            started_at=reservation.started_at,
            finished_at=reservation.started_at + timedelta(minutes=1),
            status=status,
            expected_commit=COMMIT,
            expected_source_contract_id=source_id,
            formal_state=FormalTaskState.PASSED if passed else FormalTaskState.FAILED,
            formal_code="formal-task-passed" if passed else "formal-task-terminated",
            formal_last_run_time=terminal.started_at,
            daily_receipt_id=terminal.receipt_id if passed else None,
            soak_report_id=report.report_id if passed else None,
            probes=tuple(
                _probe(name)
                for name in ("hyperliquid", "moomoo", "python", "scheduler", "tcp")
            ),
            failure_code=None if passed else "formal-task-terminated",
            detail=None if passed else "formal task did not complete",
        )
        for retry in range(20):
            try:
                store.publish_terminal(receipt)
                break
            except PermissionError:
                if retry == 19:
                    raise
                time.sleep(0.01)
        return receipt


def _intent_for_connection(terminal: ConnectionWitnessReceiptV1) -> WitnessIntentV1:
    return WitnessIntentV1.build(
        issue_number=127,
        witness_kind=WitnessKind.CONNECTION_STATE,
        local_evidence_id=terminal.run_id,
        terminal_receipt_id=terminal.receipt_id,
        report_id=terminal.soak_report_id,
        source_contract_id=terminal.expected_source_contract_id,
        code_commit=terminal.expected_commit,
        occurred_at=terminal.finished_at,
        summary=(
            f"connection slot {terminal.slot} attempt {terminal.attempt} "
            f"{terminal.execution_kind.value} {terminal.status.value}"
        ),
    )


def _write_connections(
    root: Path,
    *,
    reports: tuple[SoakReportV2, ...],
    daily: tuple[DailyRunReceiptV1, ...],
    mode: str = "exact",
) -> tuple[tuple[str, ...], tuple[ConnectionWitnessReceiptV1, ...]]:
    slots = required_connection_slots(START, EVIDENCE_AS_OF)
    target = slots[len(slots) // 2]
    receipts: list[ConnectionWitnessReceiptV1] = []
    for slot in slots:
        if slot == target and mode == "nonterminal":
            when = _slot_time(slot)
            store = ConnectionWitnessStore(root)
            owner = LeaseOwner.current(token=_id(f"nonterminal-owner:{slot}"))
            with store.acquire_slot(
                slot,
                owner=owner,
                now=when,
                stale_after=timedelta(minutes=15),
            ) as lease:
                store.reserve_attempt(
                    slot,
                    lease=lease,
                    execution_kind=ExecutionKind.SCHEDULED,
                    slot_authority=SlotAuthority.SCHEDULER,
                    slot_source_time=when + timedelta(seconds=2),
                    started_at=when + timedelta(seconds=2),
                )
            continue
        if slot == target and mode in {"missing", "supplemental-only"}:
            if mode == "supplemental-only":
                receipts.append(
                    _publish_connection(
                        root,
                        slot,
                        reports=reports,
                        daily=daily,
                        execution_kind=ExecutionKind.SUPPLEMENTAL,
                    )
                )
            continue
        status = (
            ConnectionWitnessStatus.FAILED
            if slot == target and mode in {"failed", "failed-plus-supplemental"}
            else ConnectionWitnessStatus.PASSED
        )
        receipts.append(
            _publish_connection(
                root,
                slot,
                reports=reports,
                daily=daily,
                status=status,
                start_delay_seconds=(901 if slot == target and mode == "late" else 2),
                source_id=(
                    OTHER_SOURCE_ID
                    if slot == target and mode == "wrong-source"
                    else SOURCE_ID
                ),
            )
        )
        if slot == target and mode == "duplicate":
            receipts.append(_publish_connection(root, slot, reports=reports, daily=daily))
        if slot == target and mode == "valid-retry":
            receipts.append(
                _publish_connection(
                    root,
                    slot,
                    reports=reports,
                    daily=daily,
                    start_delay_seconds=63,
                )
            )
        if slot == target and mode == "failed-plus-supplemental":
            receipts.append(
                _publish_connection(
                    root,
                    slot,
                    reports=reports,
                    daily=daily,
                    execution_kind=ExecutionKind.SUPPLEMENTAL,
                )
            )
    return slots, tuple(receipts)


def _provider_result(*, accepted: bool = True, hours: float = 168) -> SoakVerification:
    return SoakVerification(
        accepted=accepted,
        reasons=() if accepted else ("continuous observation is insufficient",),
        candidate_id=None if not accepted else _id("filled-by-fixture"),
        report_count=8,
        observed_hours=hours,
        xnys_session_count=4,
    )


def _case(
    tmp_path: Path,
    *,
    daily_mode: str = "exact",
    connection_mode: str = "exact",
    outbox_mode: str = "exact",
):
    evidence_root = tmp_path / "evidence"
    daily_root = tmp_path / "daily"
    connection_root = tmp_path / "connection"
    outbox_root = tmp_path / "outbox"
    candidate, reports = _write_reports(evidence_root)
    daily = _write_daily(daily_root, candidate, reports, mode=daily_mode)
    slots, connections = _write_connections(
        connection_root,
        reports=reports,
        daily=daily,
        mode=connection_mode,
    )
    outbox = WitnessOutbox(outbox_root)
    for index, terminal in enumerate(daily):
        if outbox_mode == "missing-daily" and index == len(daily) - 1:
            continue
        outbox.enqueue(_intent_for_daily(terminal))
    for index, terminal in enumerate(connections):
        if outbox_mode == "missing-connection" and index == len(connections) - 1:
            continue
        outbox.enqueue(_intent_for_connection(terminal))

    def verifier(_evidence: Path, _data: Path, **thresholds: int) -> SoakVerification:
        assert thresholds == {"minimum_hours": 168, "minimum_xnys_sessions": 4}
        return SoakVerification(
            accepted=True,
            reasons=(),
            candidate_id=candidate.candidate_id,
            report_count=len(reports),
            observed_hours=168,
            xnys_session_count=4,
        )

    arguments = {
        "data_root": tmp_path / "data",
        "evidence_root": evidence_root,
        "daily_run_root": daily_root,
        "connection_run_root": connection_root,
        "outbox_root": outbox_root,
        "acceptance_root": tmp_path / "acceptance",
        "expected_commit": COMMIT,
        "expected_source_contract_id": SOURCE_ID,
        "provider_verifier": verifier,
    }
    return candidate, reports, daily, slots, arguments


def test_required_connection_slots_are_wall_clock_minute_10_without_backfill() -> None:
    slots = required_connection_slots(START, EVIDENCE_AS_OF)

    assert len(slots) == 84
    assert slots[0] == "2026-09-01T00:10Z"
    assert slots[-1] == "2026-09-07T22:10Z"
    assert all(_slot_time(slot).minute == 10 for slot in slots)
    assert all(
        current - previous == timedelta(hours=2)
        for previous, current in zip(map(_slot_time, slots), map(_slot_time, slots[1:]))
    )
    exact_boundary = START.replace(minute=10)
    assert required_connection_slots(
        exact_boundary, exact_boundary + timedelta(hours=2)
    ) == (
        "2026-09-01T00:10Z",
        "2026-09-01T02:10Z",
    )


def test_final_acceptance_reopens_exact_daily_and_connection_evidence(
    tmp_path: Path,
) -> None:
    candidate, reports, daily, slots, arguments = _case(tmp_path)

    result = verify_operational_soak(**arguments)

    assert result.accepted is True, result.reasons
    assert result.candidate_id == candidate.candidate_id
    assert result.evidence_as_of == reports[-1].recorded_at
    assert result.provider_verification.observed_hours == 168
    assert result.minimum_hours == 168
    assert tuple(item.report_id for item in result.daily_bindings) == tuple(
        item.report_id for item in reports
    )
    assert tuple(item.canonical_pass_receipt_id for item in result.daily_bindings) == tuple(
        item.receipt_id for item in daily
    )
    assert result.required_connection_slots == slots
    assert tuple(item.slot for item in result.connection_bindings) == slots
    assert len(result.outbox_intent_ids) == len(daily) + len(slots)
    store = OperationalAcceptanceStore(arguments["acceptance_root"])
    assert store.load(result.acceptance_id) == result
    store.publish(result)
    assert store.load(result.acceptance_id).canonical_bytes() == result.canonical_bytes()


def test_nonoverlapping_zero_outcome_recovery_chains_remain_auditable(
    tmp_path: Path,
) -> None:
    *_, arguments = _case(
        tmp_path,
        daily_mode="valid-recovery",
        connection_mode="valid-retry",
    )

    result = verify_operational_soak(**arguments)

    assert result.accepted is True, result.reasons
    assert len(result.daily_bindings[-1].terminal_receipt_ids) == 2
    assert result.daily_bindings[-1].canonical_pass_receipt_id == (
        result.daily_bindings[-1].terminal_receipt_ids[-1]
    )
    assert any(
        len(binding.scheduled_receipt_ids) == 2
        for binding in result.connection_bindings
    )


@pytest.mark.parametrize("daily_mode", ("missing-last", "duplicate-last", "wrong-source"))
def test_final_acceptance_rejects_manual_duplicate_or_source_mismatched_daily_report(
    tmp_path: Path,
    daily_mode: str,
) -> None:
    *_, arguments = _case(tmp_path, daily_mode=daily_mode)

    result = verify_operational_soak(**arguments)

    assert result.accepted is False
    assert any("daily" in reason for reason in result.reasons)


@pytest.mark.parametrize(
    "connection_mode",
    (
        "missing",
        "nonterminal",
        "duplicate",
        "failed",
        "supplemental-only",
        "failed-plus-supplemental",
        "late",
        "wrong-source",
    ),
)
def test_supplemental_never_fills_or_heals_a_required_scheduled_slot(
    tmp_path: Path,
    connection_mode: str,
) -> None:
    *_, arguments = _case(tmp_path, connection_mode=connection_mode)

    result = verify_operational_soak(**arguments)

    assert result.accepted is False
    assert any("connection" in reason for reason in result.reasons)


@pytest.mark.parametrize("outbox_mode", ("missing-daily", "missing-connection"))
def test_every_admitted_terminal_requires_its_exact_local_outbox_intent(
    tmp_path: Path,
    outbox_mode: str,
) -> None:
    *_, arguments = _case(tmp_path, outbox_mode=outbox_mode)

    result = verify_operational_soak(**arguments)

    assert result.accepted is False
    assert any("outbox" in reason for reason in result.reasons)


def test_final_verifier_rejects_minimum_zero_and_publication_time_cannot_extend_clock(
    tmp_path: Path,
) -> None:
    *_, arguments = _case(tmp_path)
    arguments["minimum_hours"] = 0
    with pytest.raises(ValueError, match="final operational acceptance requires at least 168"):
        verify_operational_soak(**arguments)

    arguments["minimum_hours"] = 168
    arguments["minimum_xnys_sessions"] = 1
    with pytest.raises(ValueError, match="at least four XNYS sessions"):
        verify_operational_soak(**arguments)

    arguments["minimum_xnys_sessions"] = 4

    def rejected(_evidence: Path, _data: Path, **_thresholds: int) -> SoakVerification:
        return _provider_result(accepted=False, hours=24)

    arguments["provider_verifier"] = rejected
    result = verify_operational_soak(**arguments)
    assert result.accepted is False
    assert result.provider_verification.observed_hours == 24
    assert any("provider" in reason for reason in result.reasons)


def test_operational_roots_must_be_absolute_and_pairwise_disjoint(
    tmp_path: Path,
) -> None:
    arguments = {
        "data_root": tmp_path / "data",
        "evidence_root": tmp_path / "evidence",
        "daily_run_root": tmp_path / "daily",
        "connection_run_root": tmp_path / "connection",
        "outbox_root": tmp_path / "outbox",
        "acceptance_root": tmp_path / "acceptance",
        "expected_commit": COMMIT,
        "expected_source_contract_id": SOURCE_ID,
    }
    relative = {**arguments, "acceptance_root": Path("relative-acceptance")}
    with pytest.raises(ValueError, match="must be absolute"):
        verify_operational_soak(**relative)

    nested = {
        **arguments,
        "acceptance_root": arguments["evidence_root"] / "nested-acceptance",
    }
    with pytest.raises(ValueError, match="pairwise disjoint"):
        verify_operational_soak(**nested)


@pytest.mark.parametrize("gap_kind", ("first", "adjacent"))
def test_operational_layer_rejects_daily_gap_even_if_v2_provider_says_pass(
    tmp_path: Path,
    gap_kind: str,
) -> None:
    evidence_root = tmp_path / "evidence"
    if gap_kind == "first":
        candidate, reports = _write_reports(
            evidence_root,
            report_started_at=START + timedelta(hours=27),
        )
    else:
        candidate, reports = _write_reports(
            evidence_root,
            report_offsets=tuple(
                timedelta(hours=hours)
                for hours in (0, 24, 48, 72, 99, 123, 147, 171)
            ),
        )
    daily = _write_daily(tmp_path / "daily", candidate, reports)
    outbox = WitnessOutbox(tmp_path / "outbox")
    for terminal in daily:
        outbox.enqueue(_intent_for_daily(terminal))

    def accepted(_evidence: Path, _data: Path, **_thresholds: int) -> SoakVerification:
        return SoakVerification(
            accepted=True,
            reasons=(),
            candidate_id=candidate.candidate_id,
            report_count=len(reports),
            observed_hours=(reports[-1].recorded_at - candidate.started_at).total_seconds()
            / 3600,
            xnys_session_count=4,
        )

    result = verify_operational_soak(
        data_root=tmp_path / "data",
        evidence_root=evidence_root,
        daily_run_root=tmp_path / "daily",
        connection_run_root=tmp_path / "connection",
        outbox_root=tmp_path / "outbox",
        acceptance_root=tmp_path / "acceptance",
        expected_commit=COMMIT,
        expected_source_contract_id=SOURCE_ID,
        provider_verifier=accepted,
    )

    assert result.accepted is False
    assert any("daily-gap" in reason for reason in result.reasons)


def test_acceptance_store_rejects_noncanonical_or_identity_mismatched_bytes(
    tmp_path: Path,
) -> None:
    *_, arguments = _case(tmp_path)
    result = verify_operational_soak(**arguments)
    path = OperationalAcceptanceStore(arguments["acceptance_root"]).acceptance_path(
        result.acceptance_id
    )
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        OperationalAcceptanceStore(arguments["acceptance_root"]).load(
            result.acceptance_id
        )


def test_only_reopened_accepted_result_can_authorize_final_outbox_intent(
    tmp_path: Path,
) -> None:
    *_, arguments = _case(tmp_path)
    result = verify_operational_soak(**arguments)
    outbox = WitnessOutbox(arguments["outbox_root"])

    forged = WitnessIntentV1.build(
        issue_number=124,
        witness_kind=WitnessKind.OPERATIONAL_ACCEPTED,
        local_evidence_id=result.acceptance_id,
        terminal_receipt_id=result.daily_bindings[-1].canonical_pass_receipt_id,
        report_id=result.daily_bindings[-1].report_id,
        source_contract_id=result.expected_source_contract_id,
        code_commit=result.expected_commit,
        occurred_at=result.evidence_as_of,
        summary="forged operational completion",
    )
    with pytest.raises(IneligibleWitnessError, match="accepted-result read-back"):
        outbox.enqueue(forged)

    intent = outbox.ensure_operational_intent(
        result.acceptance_id,
        acceptance_root=arguments["acceptance_root"],
    )

    assert intent.witness_kind is WitnessKind.OPERATIONAL_ACCEPTED
    assert intent.issue_number == 124
    assert intent.local_evidence_id == result.acceptance_id
    assert intent.report_id == result.daily_bindings[-1].report_id
    assert (
        intent.terminal_receipt_id
        == result.daily_bindings[-1].canonical_pass_receipt_id
    )
    assert verify_operational_soak(**arguments).acceptance_id == result.acceptance_id

    def rejected(_evidence: Path, _data: Path, **_thresholds: int) -> SoakVerification:
        return _provider_result(accepted=False, hours=24)

    rejected_arguments = {
        **arguments,
        "acceptance_root": tmp_path / "rejected-acceptance",
        "provider_verifier": rejected,
    }
    rejected_result = verify_operational_soak(**rejected_arguments)
    with pytest.raises(IneligibleWitnessError, match="accepted operational"):
        outbox.ensure_operational_intent(
            rejected_result.acceptance_id,
            acceptance_root=rejected_arguments["acceptance_root"],
        )


def test_cli_refuses_minimum_zero_before_reading_any_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        [
            "verify",
            "--data-root",
            str(tmp_path / "data"),
            "--evidence-root",
            str(tmp_path / "evidence"),
            "--daily-run-root",
            str(tmp_path / "daily"),
            "--connection-run-root",
            str(tmp_path / "connection"),
            "--outbox-root",
            str(tmp_path / "outbox"),
            "--acceptance-root",
            str(tmp_path / "acceptance"),
            "--expected-commit",
            COMMIT,
            "--expected-source-contract-id",
            SOURCE_ID,
            "--minimum-hours",
            "0",
        ]
    )

    assert exit_code == 1
    assert "168" in capsys.readouterr().err
