import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

import quantmesh.ops.soak_runner as runner
from quantmesh.data.collection_receipts import (
    CollectionCycleReceipt,
    LayerManifestIds,
    TargetCollectionEvidence,
)
from quantmesh.ops.immutable_runs import (
    DailyRunReceiptV1,
    DailyRunStatus,
    ImmutableRunStore,
    LeaseOwner,
    SlotLease,
    SoakVerificationProof,
)
from quantmesh.ops.processes import ProcessResult
from quantmesh.ops.source_contract import SourceContractV1
from quantmesh.ops.trusted_data_soak import SoakVerification

NOW = datetime(2026, 8, 31, 1, tzinfo=UTC)
COMMIT = "a" * 40


def _id(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()


def _receipt(provider: str) -> CollectionCycleReceipt:
    names = ("BTC", "ETH", "SOL") if provider == "hyperliquid-public" else ("AAPL", "NVDA")
    return CollectionCycleReceipt(
        provider=provider,
        code_commit=COMMIT,
        collection_cycle="daily-2026-08-31",
        job_id=_id(provider + "job"),
        run_id=_id(provider + "run"),
        attempt=1,
        quality_report_id=_id(provider + "quality"),
        targets=tuple(
            TargetCollectionEvidence(
                target=name,
                canonical_instrument=(
                    f"hyperliquid:perp:{name}"
                    if provider == "hyperliquid-public"
                    else f"moomoo:US:{name}:XNAS"
                ),
                interval="1m" if provider == "hyperliquid-public" else "1d",
                manifest_ids=LayerManifestIds(
                    raw=_id(f"{provider}:{name}:raw"),
                    normalized=_id(f"{provider}:{name}:normalized"),
                    adjusted=_id(f"{provider}:{name}:adjusted"),
                    feature=_id(f"{provider}:{name}:feature"),
                ),
            )
            for name in names
        ),
    )


def _result(stdout: str, *, code: int = 0, timed_out: bool = False) -> ProcessResult:
    return ProcessResult(
        argv=("command",),
        returncode=code,
        stdout=stdout,
        stderr="failure" if code else "",
        elapsed_seconds=1,
        timed_out=timed_out,
        tree_terminated=timed_out,
    )


def _source() -> SourceContractV1:
    return SourceContractV1.build(
        remote_ref="origin/0021-soak-finalize",
        head_commit=COMMIT,
        dependency_digest="b" * 64,
        script_digest="c" * 64,
        config_digest="d" * 64,
        clean=True,
        reachable=True,
    )


def _args(tmp_path: Path) -> list[str]:
    return [
        "--repo",
        str(tmp_path),
        "--data-root",
        str(tmp_path / "data"),
        "--evidence-root",
        str(tmp_path / "evidence"),
        "--run-root",
        str(tmp_path / "runs"),
        "--outbox-root",
        str(tmp_path / "outbox"),
        "--remote-ref",
        "origin/0021-soak-finalize",
        "--dependency-digest",
        "b" * 64,
        "--script-digest",
        "c" * 64,
        "--config-digest",
        "d" * 64,
    ]


def _install_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "_now", lambda: NOW)
    monkeypatch.setattr(runner, "verify_source_contract", lambda *args, **kwargs: _source())


def test_source_failure_stops_before_collection_and_writes_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(runner, "_now", lambda: NOW)
    monkeypatch.setattr(
        runner,
        "verify_source_contract",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("clean checkout required")),
    )
    monkeypatch.setattr(
        runner, "run_process", lambda *args, **kwargs: pytest.fail("collection started")
    )

    assert runner.main(_args(tmp_path)) == 1
    receipt = ImmutableRunStore(tmp_path / "runs").latest()
    assert receipt.status is DailyRunStatus.FAILED
    assert receipt.failure_stage == "source-contract"


def test_default_lease_wait_covers_every_bounded_owner_stage(tmp_path: Path) -> None:
    parsed = runner._parser().parse_args(_args(tmp_path))
    config = runner.DailyRunConfig(**vars(parsed))

    assert runner._lease_wait_budget(config) >= sum(
        (
            config.source_timeout,
            config.hyperliquid_timeout,
            config.moomoo_timeout,
            config.observe_timeout,
            config.verify_timeout,
        )
    )


def test_malformed_collection_stops_before_observe_and_writes_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_source(monkeypatch)
    calls = 0

    def run(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            pytest.fail("runner advanced after malformed collection")
        return _result("{}")

    monkeypatch.setattr(runner, "run_process", run)
    assert runner.main(_args(tmp_path)) == 1
    assert calls == 1
    assert ImmutableRunStore(tmp_path / "runs").latest().failure_stage == "collect-hyperliquid"


def test_timeout_records_timed_out_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_source(monkeypatch)
    monkeypatch.setattr(
        runner,
        "run_process",
        lambda *args, **kwargs: _result("", code=-9, timed_out=True),
    )
    assert runner.main(_args(tmp_path)) == 1
    receipt = ImmutableRunStore(tmp_path / "runs").latest()
    assert receipt.status is DailyRunStatus.TIMED_OUT
    assert receipt.failure_code == "deadline-exceeded"


def test_typed_collections_reach_observe_and_verifier_failure_is_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_source(monkeypatch)
    hyper = _receipt("hyperliquid-public")
    moomoo = _receipt("moomoo-opend")

    def outer(receipt: CollectionCycleReceipt) -> str:
        return json.dumps(
            {
                "provider": receipt.provider,
                "read_only": True,
                "collection_receipt": receipt.model_dump(mode="json"),
                "status": "published",
                "reason_code": None,
                "detail": None,
                "manifest_ids": [],
            }
        )

    verification = SoakVerification(
        accepted=False,
        reasons=("critical issue",),
        candidate_id=None,
        report_count=1,
        observed_hours=0,
        xnys_session_count=1,
    )
    results = iter(
        (
            _result(outer(hyper)),
            _result(outer(moomoo)),
            _result("not-a-report", code=1),
            _result(verification.model_dump_json(), code=1),
        )
    )
    calls: list[tuple[str, ...]] = []

    def run(argv, **kwargs):
        calls.append(tuple(str(item) for item in argv))
        return next(results)

    monkeypatch.setattr(runner, "run_process", run)
    assert runner.main(_args(tmp_path)) == 1
    assert any("verify" in call for call in calls)
    assert ImmutableRunStore(tmp_path / "runs").latest().status is DailyRunStatus.FAILED


def _passed_terminal() -> DailyRunReceiptV1:
    source = _source()
    return DailyRunReceiptV1.build(
        slot=NOW.date().isoformat(),
        attempt=1,
        started_at=NOW,
        finished_at=NOW,
        status=DailyRunStatus.PASSED,
        code_commit=COMMIT,
        source_contract_id=source.source_contract_id,
        hyperliquid_receipt_id=_id("hyper-terminal"),
        moomoo_receipt_id=_id("moomoo-terminal"),
        soak_report_id=_id("report-terminal"),
        verification=SoakVerificationProof(
            accepted=True,
            reasons=(),
            candidate_id=_id("candidate"),
            report_count=1,
            observed_hours=0,
            xnys_session_count=1,
        ),
    )


def test_same_day_retry_reuses_exact_evidence_and_reruns_only_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_source(monkeypatch)
    monkeypatch.setattr(runner, "_ensure_daily_witness", lambda *_args, **_kwargs: None)
    store = ImmutableRunStore(tmp_path / "runs")
    prior = _passed_terminal()
    store.publish_terminal(prior)
    verification = SoakVerification(
        accepted=True,
        reasons=(),
        candidate_id=_id("candidate"),
        report_count=1,
        observed_hours=0,
        xnys_session_count=1,
    )
    calls: list[tuple[str, ...]] = []

    def run(argv, **kwargs):
        calls.append(tuple(str(item) for item in argv))
        return _result(verification.model_dump_json())

    monkeypatch.setattr(runner, "run_process", run)

    assert runner.main(_args(tmp_path)) == 0
    recovered = store.latest()
    assert len(calls) == 1
    assert "verify" in calls[0]
    assert recovered.attempt == 2
    assert recovered.recovery_of_run_id == prior.run_id
    assert recovered.soak_report_id == prior.soak_report_id
    assert recovered.status is DailyRunStatus.PASSED


def test_concurrent_invocation_returns_existing_compatible_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_source(monkeypatch)
    monkeypatch.setattr(runner, "_ensure_daily_witness", lambda *_args, **_kwargs: None)
    store = ImmutableRunStore(tmp_path / "runs")
    prior = _passed_terminal()
    store.publish_terminal(prior)
    owner = LeaseOwner.current(token="active", process_start_token="active-process")
    lease = SlotLease.acquire(tmp_path / "runs", prior.slot, owner=owner, now=NOW)
    monkeypatch.setattr(
        runner, "run_process", lambda *args, **kwargs: pytest.fail("contender ran a child")
    )
    try:
        parsed = runner._parser().parse_args(_args(tmp_path))
        observed = runner.run_daily(runner.DailyRunConfig(**vars(parsed)))
    finally:
        lease.release()

    assert observed == prior
    assert store.terminals(prior.slot) == (prior,)


def test_crash_recovery_reverifies_only_the_exact_durable_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_source(monkeypatch)
    monkeypatch.setattr(runner, "_ensure_daily_witness", lambda *_args, **_kwargs: None)
    hyper = _receipt("hyperliquid-public")
    moomoo = _receipt("moomoo-opend")
    report = SimpleNamespace(
        report_date=NOW.date().isoformat(),
        report_id=_id("durable-report"),
        source_contract_id=_source().source_contract_id,
        code_commit=COMMIT,
        collection_receipt_ids=tuple(sorted((hyper.receipt_id, moomoo.receipt_id))),
        critical_issues=(),
    )

    class FakeSoakStore:
        def __init__(self, root: Path) -> None:
            assert root == tmp_path / "evidence"

        def reports(self):
            return (report,)

        def load_cycle_receipt(self, receipt_id: str):
            return {hyper.receipt_id: hyper, moomoo.receipt_id: moomoo}[receipt_id]

    verification = SoakVerification(
        accepted=True,
        reasons=(),
        candidate_id=_id("candidate"),
        report_count=1,
        observed_hours=0,
        xnys_session_count=1,
    )
    calls: list[tuple[str, ...]] = []

    def run(argv, **kwargs):
        calls.append(tuple(str(item) for item in argv))
        return _result(verification.model_dump_json())

    monkeypatch.setattr(runner, "SoakStoreV2", FakeSoakStore, raising=False)
    monkeypatch.setattr(runner, "run_process", run)

    assert runner.main(_args(tmp_path)) == 0
    recovered = ImmutableRunStore(tmp_path / "runs").latest()
    assert len(calls) == 1
    assert "verify" in calls[0]
    assert recovered.status is DailyRunStatus.PASSED
    assert recovered.soak_report_id == report.report_id
    assert recovered.hyperliquid_receipt_id == hyper.receipt_id
    assert recovered.moomoo_receipt_id == moomoo.receipt_id
