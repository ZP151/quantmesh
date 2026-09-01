import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import quantmesh.ops.connection_witness as connection_runner
import quantmesh.ops.soak_runner as daily_runner
from quantmesh.ops.connection_witness import (
    ConnectionProbeOutcome,
    ConnectionProbeResult,
    ConnectionWitnessReceiptV1,
    ConnectionWitnessStatus,
    ExecutionKind,
    FormalTaskState,
    SlotAuthority,
)
from quantmesh.ops.immutable_runs import (
    DailyRunReceiptV1,
    DailyRunStatus,
    ImmutableRunConflictError,
    ImmutableRunStore,
    LeaseHeldError,
    LeaseOwner,
    SoakVerificationProof,
)
from quantmesh.ops.trusted_data_soak import (
    SoakCandidateV2,
    SoakReportV2,
    SoakStoreV2,
    SoakTargetEvidenceV2,
)
from quantmesh.ops.witness_outbox import (
    AmbiguousRemoteResult,
    DuplicateRemoteWitnessError,
    IneligibleWitnessError,
    OutboxIntentError,
    PublicationValidationError,
    RemoteCommentV1,
    WitnessIntentV1,
    WitnessKind,
    WitnessOutbox,
    WitnessPublicationReceiptV1,
    WitnessPublisher,
    WitnessReconciler,
)
from quantmesh.ops.witness_outbox import (
    main as outbox_main,
)

NOW = datetime(2026, 9, 1, 2, 20, tzinfo=UTC)
DAILY_START = datetime(2026, 9, 1, 0, 0, 2, tzinfo=UTC)
COMMIT = "a" * 40
SOURCE_ID = "b" * 64
SLOT = "2026-09-01T02:10Z"


def _id(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _report(root: Path) -> SoakReportV2:
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


def _daily(report: SoakReportV2, *, attempt: int = 1) -> DailyRunReceiptV1:
    return DailyRunReceiptV1.build(
        slot="2026-09-01",
        attempt=attempt,
        started_at=DAILY_START + timedelta(seconds=attempt - 1),
        finished_at=DAILY_START + timedelta(minutes=2, seconds=attempt - 1),
        status=DailyRunStatus.PASSED,
        code_commit=COMMIT,
        source_contract_id=SOURCE_ID,
        hyperliquid_receipt_id=_id("hyper-cycle"),
        moomoo_receipt_id=_id("moomoo-cycle"),
        soak_report_id=report.report_id,
        verification=SoakVerificationProof(
            accepted=True,
            reasons=(),
            candidate_id=report.candidate_id,
            report_count=1,
            observed_hours=24,
            xnys_session_count=1,
        ),
    )


def _probe(name: str) -> ConnectionProbeResult:
    return ConnectionProbeResult(
        name=name,
        outcome=ConnectionProbeOutcome.PASSED,
        code=f"{name}-passed",
        detail=f"{name} passed",
        elapsed_seconds=0.1,
        tree_terminated=False,
    )


def _connection(
    *,
    attempt: int = 1,
    status: ConnectionWitnessStatus = ConnectionWitnessStatus.PASSED,
    execution_kind: ExecutionKind = ExecutionKind.SCHEDULED,
) -> ConnectionWitnessReceiptV1:
    passed = status is ConnectionWitnessStatus.PASSED
    supplemental = execution_kind is ExecutionKind.SUPPLEMENTAL
    return ConnectionWitnessReceiptV1.build(
        slot=SLOT,
        attempt=attempt,
        execution_kind=execution_kind,
        slot_authority=(
            SlotAuthority.EXPLICIT_SUPPLEMENTAL if supplemental else SlotAuthority.SCHEDULER
        ),
        slot_source_time=(None if supplemental else datetime(2026, 9, 1, 2, 10, tzinfo=UTC)),
        reservation_id=_id(f"reservation:{attempt}"),
        started_at=datetime(2026, 9, 1, 2, 10, tzinfo=UTC),
        finished_at=datetime(2026, 9, 1, 2, 11, tzinfo=UTC),
        status=status,
        expected_commit=COMMIT,
        expected_source_contract_id=SOURCE_ID,
        formal_state=FormalTaskState.PASSED if passed else FormalTaskState.FAILED,
        formal_code="formal-task-passed" if passed else "formal-task-terminated",
        formal_last_run_time=DAILY_START,
        daily_receipt_id=_id("daily") if passed else None,
        soak_report_id=_id("report") if passed else None,
        probes=tuple(
            _probe(name) for name in ("hyperliquid", "moomoo", "python", "scheduler", "tcp")
        ),
        failure_code=None if passed else "formal-task-terminated",
        detail=None if passed else "formal task terminated",
    )


def _intent(label: str = "one") -> WitnessIntentV1:
    return WitnessIntentV1.build(
        issue_number=127,
        witness_kind=WitnessKind.CONNECTION_STATE,
        local_evidence_id=_id(label),
        terminal_receipt_id=_id(f"terminal:{label}"),
        report_id=None,
        source_contract_id=SOURCE_ID,
        code_commit=COMMIT,
        occurred_at=NOW,
        summary=f"connection witness {label}",
    )


class _Remote:
    def __init__(self) -> None:
        self.comments: list[RemoteCommentV1] = []
        self.post_calls = 0
        self.raise_after_post = False

    def list_exact(self, issue_number: int, idempotency_key: str):
        return tuple(
            item
            for item in self.comments
            if item.issue_number == issue_number and item.idempotency_key == idempotency_key
        )

    def post_comment(self, issue_number: int, idempotency_key: str, body: str) -> None:
        self.post_calls += 1
        self.comments.append(
            RemoteCommentV1.build(
                issue_number=issue_number,
                idempotency_key=idempotency_key,
                comment_url=f"https://github.com/ZP151/quantmesh/issues/{issue_number}#issuecomment-{self.post_calls}",
                body=body,
            )
        )
        if self.raise_after_post:
            raise AmbiguousRemoteResult("connection dropped after POST")


def test_exact_enqueue_retry_and_conflicting_intent_rejection(tmp_path: Path) -> None:
    outbox = WitnessOutbox(tmp_path)
    intent = _intent()

    assert outbox.enqueue(intent) == intent
    assert outbox.enqueue(intent) == intent

    conflict = WitnessIntentV1.build(
        **{
            **intent.model_dump(exclude={"intent_id", "body", "body_digest"}),
            "summary": "different summary for the same authority key",
        }
    )
    with pytest.raises(ImmutableRunConflictError, match="intent"):
        outbox.enqueue(conflict)


def test_operational_intent_cannot_bypass_accepted_result_readback(
    tmp_path: Path,
) -> None:
    forged = WitnessIntentV1.build(
        issue_number=124,
        witness_kind=WitnessKind.OPERATIONAL_ACCEPTED,
        local_evidence_id=_id("acceptance"),
        terminal_receipt_id=_id("daily-terminal"),
        report_id=_id("final-report"),
        source_contract_id=SOURCE_ID,
        code_commit=COMMIT,
        occurred_at=NOW,
        summary="forged final operational acceptance",
    )

    with pytest.raises(IneligibleWitnessError, match="accepted-result read-back"):
        WitnessOutbox(tmp_path).enqueue(forged)


def test_pending_order_is_deterministic_and_publication_removes_exact_key(
    tmp_path: Path,
) -> None:
    outbox = WitnessOutbox(tmp_path)
    intents = tuple(outbox.enqueue(_intent(label)) for label in ("z", "a", "m"))
    assert outbox.pending() == tuple(sorted(intents, key=lambda item: item.idempotency_key))

    remote = _Remote()
    publisher = WitnessPublisher(outbox, remote)
    receipts = publisher.publish_pending(now=NOW)

    assert len(receipts) == 3
    assert outbox.pending() == ()
    assert remote.post_calls == 3


def test_cross_process_publisher_lease_blocks_live_and_recovers_dead_owner(
    tmp_path: Path,
) -> None:
    outbox = WitnessOutbox(tmp_path)
    old = LeaseOwner(pid=111, token="old", process_start_token="old-process")
    new = LeaseOwner(pid=222, token="new", process_start_token="new-process")
    held = outbox.acquire_publisher(
        owner=old,
        now=NOW,
        stale_after=timedelta(seconds=1),
        owner_alive=lambda _owner: True,
    )
    with pytest.raises(LeaseHeldError):
        outbox.acquire_publisher(
            owner=new,
            now=NOW,
            stale_after=timedelta(seconds=1),
            owner_alive=lambda _owner: True,
        )

    recovered = outbox.acquire_publisher(
        owner=new,
        now=NOW + timedelta(seconds=2),
        stale_after=timedelta(seconds=1),
        owner_alive=lambda owner: owner != old,
    )
    assert recovered.record.owner == new
    assert not held.path.exists() or recovered.path == held.path
    recovered.release()


def test_ambiguous_post_requeries_and_restart_does_not_post_again(tmp_path: Path) -> None:
    outbox = WitnessOutbox(tmp_path)
    intent = outbox.enqueue(_intent())
    remote = _Remote()
    remote.raise_after_post = True
    publisher = WitnessPublisher(outbox, remote)

    receipts = publisher.publish_pending(now=NOW)

    assert len(receipts) == 1
    assert receipts[0].idempotency_key == intent.idempotency_key
    assert remote.post_calls == 1
    assert WitnessPublisher(outbox, remote).publish_pending(now=NOW) == ()
    assert remote.post_calls == 1


def test_ambiguous_post_without_match_requeries_before_one_retry(tmp_path: Path) -> None:
    class LostBeforeCommit(_Remote):
        def post_comment(self, issue_number: int, idempotency_key: str, body: str) -> None:
            if self.post_calls == 0:
                self.post_calls += 1
                raise AmbiguousRemoteResult("request outcome is unknown")
            super().post_comment(issue_number, idempotency_key, body)

    outbox = WitnessOutbox(tmp_path)
    outbox.enqueue(_intent())
    remote = LostBeforeCommit()

    receipts = WitnessPublisher(outbox, remote).publish_pending(now=NOW)

    assert len(receipts) == 1
    assert remote.post_calls == 2


def test_duplicate_remote_match_and_readback_digest_mismatch_fail_closed(
    tmp_path: Path,
) -> None:
    outbox = WitnessOutbox(tmp_path)
    intent = outbox.enqueue(_intent())
    remote = _Remote()
    valid = RemoteCommentV1.build(
        issue_number=intent.issue_number,
        idempotency_key=intent.idempotency_key,
        comment_url="https://github.com/ZP151/quantmesh/issues/127#issuecomment-1",
        body=intent.body,
    )
    remote.comments = [
        valid,
        RemoteCommentV1.build(
            issue_number=intent.issue_number,
            idempotency_key=intent.idempotency_key,
            comment_url=valid.comment_url + "0",
            body=intent.body,
        ),
    ]
    with pytest.raises(DuplicateRemoteWitnessError):
        WitnessPublisher(outbox, remote).publish_pending(now=NOW)

    remote.comments = [
        RemoteCommentV1.build(
            issue_number=intent.issue_number,
            idempotency_key=intent.idempotency_key,
            comment_url=valid.comment_url,
            body=intent.body + "\nforged",
        )
    ]
    with pytest.raises(PublicationValidationError, match="digest"):
        WitnessPublisher(outbox, remote).publish_pending(now=NOW)


def test_publication_receipt_rejects_non_https_url(tmp_path: Path) -> None:
    intent = _intent()
    with pytest.raises(ValidationError, match="HTTPS"):
        RemoteCommentV1.build(
            issue_number=intent.issue_number,
            idempotency_key=intent.idempotency_key,
            comment_url="http://example.test/comment/1",
            body=intent.body,
        )


@pytest.mark.parametrize(
    "comment_url",
    [
        "https://example.test/ZP151/quantmesh/issues/127#issuecomment-1",
        "https://github.com/attacker/quantmesh/issues/127#issuecomment-1",
        "https://github.com/ZP151/quantmesh/issues/124#issuecomment-1",
        "https://github.com/ZP151/quantmesh/issues/127",
    ],
)
def test_publication_receipt_rejects_wrong_repository_or_issue_url(
    comment_url: str,
) -> None:
    intent = _intent()
    with pytest.raises(ValidationError, match="expected ZP151/quantmesh issue"):
        RemoteCommentV1.build(
            issue_number=intent.issue_number,
            idempotency_key=intent.idempotency_key,
            comment_url=comment_url,
            body=intent.body,
        )


def test_store_revalidates_frozen_model_copies_before_publication(tmp_path: Path) -> None:
    outbox = WitnessOutbox(tmp_path)
    intent = _intent()
    with pytest.raises(ValidationError, match="body"):
        outbox.enqueue(intent.model_copy(update={"summary": "forged"}))

    intent = outbox.enqueue(intent)
    comment = RemoteCommentV1.build(
        issue_number=intent.issue_number,
        idempotency_key=intent.idempotency_key,
        comment_url="https://github.com/ZP151/quantmesh/issues/127#issuecomment-1",
        body=intent.body,
    )
    receipt = WitnessPublicationReceiptV1.build(intent, comment, recorded_at=NOW)
    with pytest.raises(ValidationError, match="read-back"):
        outbox.record_publication(
            receipt.model_copy(update={"remote_body": intent.body + "\nforged"})
        )


def test_daily_reconciliation_recovers_terminal_before_enqueue_and_reopens_proof(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path / "reports")
    terminal = _daily(report)
    ImmutableRunStore(tmp_path / "daily").publish_terminal(terminal)
    outbox = WitnessOutbox(tmp_path / "outbox")
    reconciler = WitnessReconciler(
        outbox,
        report_root=tmp_path / "reports",
        expected_commit=COMMIT,
        expected_source_contract_id=SOURCE_ID,
    )

    created = reconciler.reconcile_daily(tmp_path / "daily")

    assert len(created) == 1
    assert created[0].issue_number == 124
    assert created[0].witness_kind is WitnessKind.DAILY_ACCEPTED
    assert created[0].report_id == report.report_id
    assert reconciler.reconcile_daily(tmp_path / "daily") == ()


def test_issue_124_success_cannot_enqueue_without_passing_full_verifier_proof(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path / "reports")
    terminal = _daily(report)
    forged = terminal.model_copy(update={"verification": None})
    outbox = WitnessOutbox(tmp_path / "outbox")

    with pytest.raises(IneligibleWitnessError, match="verifier"):
        outbox.ensure_daily_intent(
            forged,
            report_root=tmp_path / "reports",
            expected_commit=COMMIT,
            expected_source_contract_id=SOURCE_ID,
        )
    assert outbox.pending() == ()


def test_connection_reconciliation_preserves_failed_and_supplemental_attempts(
    tmp_path: Path,
) -> None:
    outbox = WitnessOutbox(tmp_path / "outbox")
    failed = _connection(status=ConnectionWitnessStatus.FAILED)
    recovered = _connection(
        attempt=2,
        execution_kind=ExecutionKind.SUPPLEMENTAL,
    )

    first = outbox.ensure_connection_intent(failed)
    second = outbox.ensure_connection_intent(recovered)

    assert first.idempotency_key != second.idempotency_key
    assert tuple(item.terminal_receipt_id for item in outbox.pending()) == tuple(
        item.terminal_receipt_id
        for item in sorted((first, second), key=lambda item: item.idempotency_key)
    )


def test_connection_reconciler_recovers_durable_terminal_before_enqueue(
    tmp_path: Path,
) -> None:
    root = tmp_path / "connections"
    store = connection_runner.ConnectionWitnessStore(root)
    owner = LeaseOwner(pid=111, token="connection", process_start_token="test")
    started = datetime(2026, 9, 1, 2, 10, tzinfo=UTC)
    lease = store.acquire_slot(
        SLOT,
        owner=owner,
        now=started,
        stale_after=timedelta(minutes=15),
    )
    reservation = store.reserve_attempt(
        SLOT,
        lease=lease,
        execution_kind=ExecutionKind.SCHEDULED,
        slot_authority=SlotAuthority.SCHEDULER,
        slot_source_time=started,
        started_at=started,
    )
    template = _connection()
    values = template.model_dump(
        mode="python",
        exclude={"contract", "run_id", "receipt_id", "reservation_id", "started_at"},
    )
    values["probes"] = template.probes
    terminal = ConnectionWitnessReceiptV1.build(
        **values,
        reservation_id=reservation.reservation_id,
        started_at=reservation.started_at,
    )
    store.publish_terminal(terminal)
    lease.release()
    outbox = WitnessOutbox(tmp_path / "outbox")
    reconciler = WitnessReconciler(
        outbox,
        report_root=tmp_path / "reports",
        expected_commit=COMMIT,
        expected_source_contract_id=SOURCE_ID,
    )

    created = reconciler.reconcile_connection(root)

    assert len(created) == 1
    assert created[0].terminal_receipt_id == terminal.receipt_id
    assert reconciler.reconcile_connection(root) == ()


def test_reconciliation_conflict_persists_typed_failure_and_remains_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _report(tmp_path / "reports")
    terminal = _daily(report)
    ImmutableRunStore(tmp_path / "daily").publish_terminal(terminal)
    outbox = WitnessOutbox(tmp_path / "outbox")
    reconciler = WitnessReconciler(
        outbox,
        report_root=tmp_path / "reports",
        expected_commit=COMMIT,
        expected_source_contract_id=SOURCE_ID,
    )
    monkeypatch.setattr(
        outbox,
        "enqueue",
        lambda _intent: (_ for _ in ()).throw(ImmutableRunConflictError("conflict")),
    )

    with pytest.raises(ImmutableRunConflictError):
        reconciler.reconcile_daily(tmp_path / "daily")

    failures = outbox.reconciliation_failures()
    assert len(failures) == 1
    assert failures[0].terminal_receipt_id == terminal.receipt_id
    assert failures[0].error_code == "intent-conflict"


def test_daily_terminal_remains_immutable_when_post_terminal_enqueue_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = _report(tmp_path / "reports")
    terminal = _daily(report)
    run_store = ImmutableRunStore(tmp_path / "daily")
    run_store.publish_terminal(terminal)
    config = SimpleNamespace(
        outbox_root=tmp_path / "outbox",
        evidence_root=tmp_path / "reports",
    )
    monkeypatch.setattr(
        WitnessOutbox,
        "enqueue",
        lambda _self, _intent: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OutboxIntentError):
        daily_runner._ensure_daily_witness(
            config,
            terminal,
            expected_commit=COMMIT,
            expected_source_contract_id=SOURCE_ID,
        )

    assert run_store.latest() == terminal
    failures = WitnessOutbox(tmp_path / "outbox").reconciliation_failures()
    assert len(failures) == 1
    assert failures[0].terminal_receipt_id == terminal.receipt_id


def test_daily_runner_boundary_pairs_passing_terminal_before_success(
    tmp_path: Path,
) -> None:
    report = _report(tmp_path / "reports")
    terminal = _daily(report)
    config = SimpleNamespace(
        outbox_root=tmp_path / "outbox",
        evidence_root=tmp_path / "reports",
    )

    intent = daily_runner._ensure_daily_witness(
        config,
        terminal,
        expected_commit=COMMIT,
        expected_source_contract_id=SOURCE_ID,
    )

    assert intent is not None
    assert intent.terminal_receipt_id == terminal.receipt_id
    assert WitnessOutbox(tmp_path / "outbox").pending() == (intent,)


def test_connection_terminal_enqueue_failure_is_separate_and_non_mutating(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    terminal = _connection()
    config = SimpleNamespace(
        outbox_root=tmp_path / "outbox",
        expected_commit=COMMIT,
        expected_source_contract_id=SOURCE_ID,
    )
    monkeypatch.setattr(
        WitnessOutbox,
        "enqueue",
        lambda _self, _intent: (_ for _ in ()).throw(OSError("disk full")),
    )

    with pytest.raises(OutboxIntentError):
        connection_runner._ensure_connection_witness(config, terminal)

    assert terminal.status is ConnectionWitnessStatus.PASSED
    failures = WitnessOutbox(tmp_path / "outbox").reconciliation_failures()
    assert len(failures) == 1
    assert failures[0].terminal_receipt_id == terminal.receipt_id


def test_outbox_and_reconciliation_roots_are_absolute_and_disjoint(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="absolute"):
        WitnessOutbox(Path("relative"))
    outbox = WitnessOutbox(tmp_path / "outbox")
    with pytest.raises(ValueError, match="disjoint"):
        WitnessReconciler(
            outbox,
            report_root=tmp_path / "outbox" / "reports",
            expected_commit=COMMIT,
            expected_source_contract_id=SOURCE_ID,
        )


def test_local_cli_lists_and_shows_but_cannot_claim_remote_publication(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    outbox = WitnessOutbox(tmp_path / "outbox")
    intent = outbox.enqueue(_intent())
    assert outbox_main(["list", "--outbox-root", str(outbox.root)]) == 0
    assert intent.idempotency_key in capsys.readouterr().out
    assert (
        outbox_main(
            [
                "show",
                "--outbox-root",
                str(outbox.root),
                "--idempotency-key",
                intent.idempotency_key,
            ]
        )
        == 0
    )
    assert intent.intent_id in capsys.readouterr().out
    body_path = tmp_path / "remote-body.txt"
    body_path.write_bytes(intent.body.encode("utf-8"))
    with pytest.raises(SystemExit):
        outbox_main(
            [
                "record-publication",
                "--outbox-root",
                str(outbox.root),
                "--idempotency-key",
                intent.idempotency_key,
                "--comment-url",
                "https://github.com/ZP151/quantmesh/issues/127#issuecomment-1",
                "--remote-body-path",
                str(body_path),
                "--recorded-at",
                NOW.isoformat(),
            ]
        )
    assert outbox.pending() == (intent,)
