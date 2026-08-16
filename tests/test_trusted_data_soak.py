import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import tools.trusted_data_soak as soak_module
from quantmesh.data.artifacts import ManifestStore
from quantmesh.data.collection import CollectionCoordinator
from tests.test_data_catalog import _entry as _catalog_entry
from tests.test_data_catalog import _quality as _catalog_quality
from tests.test_quality_publication import _envelope, _job, _producer
from tools.trusted_data_soak import (
    SoakCandidate,
    SoakReport,
    SoakStore,
    SoakTargetEvidence,
    _observe,
    verify_soak,
)

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
COMMIT = "a" * 40
MANIFEST = "b" * 64
EVALUATION = "c" * 64
CHECKPOINT = "d" * 64
POLICY = "e" * 64


def _candidate(started_at: datetime = NOW - timedelta(days=7), *, policy: str = POLICY):
    return SoakCandidate.build(
        started_at=started_at,
        code_commit=COMMIT,
        policy_ids=(policy,),
        calendar_versions=("continuous-utc-v1", "XNYS-2026a"),
        schema_versions=("artifact-v2:bars-v1",),
        required_targets=("test-target",),
    )


def _report(
    candidate: SoakCandidate,
    *,
    recorded_at: datetime,
    predecessor: str | None,
    xnys_sessions: tuple[str, ...] = (),
    crypto_observed: bool = True,
):
    return SoakReport.build(
        candidate=candidate,
        recorded_at=recorded_at,
        predecessor_report_id=predecessor,
        manifest_ids=(MANIFEST,),
        quality_evaluation_ids=(EVALUATION,),
        checkpoint_digests=(CHECKPOINT,),
        target_evidence=(
            SoakTargetEvidence(
                target_id="test-target",
                manifest_id=MANIFEST,
                quality_evaluation_id=EVALUATION,
                checkpoint_digest=CHECKPOINT,
                event_end=recorded_at,
            ),
        ),
        completed_xnys_sessions=xnys_sessions,
        crypto_observed=crypto_observed,
        critical_issues=(),
    )


def _set_mtime(path: Path, instant: datetime) -> None:
    stamp = instant.timestamp()
    os.utime(path, (stamp, stamp))


def test_replay_historical_refuses_empty_catalog(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="empty"):
        soak_module.replay_historical(tmp_path / "data")


def test_replay_historical_rejects_non_advancing_crypto_frontier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = _catalog_entry(quality=_catalog_quality())
    opened = SimpleNamespace(
        manifest=SimpleNamespace(objects=()),
        objects=SimpleNamespace(get_bytes=lambda reference: b"{}"),
    )
    non_advancing = (
        SimpleNamespace(
            compatibility_revision=1,
            event_end=datetime(2026, 8, 13, 12, 30, tzinfo=UTC),
            manifest_id="a" * 64,
            layer=soak_module.ArtifactLayer.ADJUSTED,
        ),
        SimpleNamespace(
            compatibility_revision=2,
            event_end=datetime(2026, 8, 13, 12, 0, tzinfo=UTC),
            manifest_id="b" * 64,
            layer=soak_module.ArtifactLayer.ADJUSTED,
        ),
    )
    monkeypatch.setattr(
        soak_module,
        "TrustedDataCatalog",
        lambda root: SimpleNamespace(entries=lambda: (entry,)),
    )
    monkeypatch.setattr(
        soak_module,
        "ManifestStore",
        lambda root: SimpleNamespace(
            manifests=lambda dataset_id: non_advancing,
            open=lambda manifest_id: opened,
        ),
    )
    monkeypatch.setattr(soak_module, "_git_commit", lambda: "3" * 40)

    result = soak_module.replay_historical(tmp_path)

    assert result["accepted"] is False
    assert any("did not advance" in reason for reason in result["reasons"])


def test_entry_target_id_handles_non_bar_layers_with_none_interval() -> None:
    entry = _catalog_entry(quality=_catalog_quality()).model_copy(update={"interval": None})

    target_id = soak_module._entry_target_id(entry)

    assert isinstance(target_id, str)
    assert target_id.endswith("|")


def test_soak_rejects_seven_reports_generated_after_the_fact(tmp_path: Path) -> None:
    candidate = _candidate()
    store = SoakStore(tmp_path)
    store.root.mkdir(parents=True, exist_ok=True)
    store.candidate_path.write_bytes(candidate.canonical_bytes())
    predecessor = None
    for day in range(1, 8):
        report = _report(
            candidate,
            recorded_at=candidate.started_at + timedelta(days=day),
            predecessor=predecessor,
        )
        store.report_dir.mkdir(parents=True, exist_ok=True)
        store.report_path(report.report_id).write_bytes(report.canonical_bytes())
        predecessor = report.report_id

    result = verify_soak(
        tmp_path, tmp_path / "data", minimum_hours=168, minimum_xnys_sessions=0
    )

    assert not result.accepted
    assert any("continuous observation" in reason for reason in result.reasons)


def test_soak_rejects_changed_candidate_baseline(tmp_path: Path) -> None:
    candidate = _candidate()
    changed = _candidate(policy="f" * 64)
    store = SoakStore(tmp_path)
    store.write_candidate(candidate, now=candidate.started_at)
    report = _report(
        changed,
        recorded_at=candidate.started_at + timedelta(days=1),
        predecessor=None,
    )
    store.report_dir.mkdir(parents=True)
    path = store.report_path(report.report_id)
    path.write_bytes(report.canonical_bytes())
    _set_mtime(path, report.recorded_at)

    result = verify_soak(
        tmp_path, tmp_path / "data", minimum_hours=1, minimum_xnys_sessions=0
    )

    assert not result.accepted
    assert any("candidate baseline" in reason for reason in result.reasons)


def test_soak_rejects_incomplete_market_evidence(tmp_path: Path) -> None:
    candidate = _candidate(started_at=NOW - timedelta(hours=2))
    store = SoakStore(tmp_path)
    store.write_candidate(candidate, now=candidate.started_at)
    report = _report(
        candidate,
        recorded_at=NOW,
        predecessor=None,
        crypto_observed=False,
    )
    store.append(report, now=NOW)

    result = verify_soak(
        tmp_path, tmp_path / "data", minimum_hours=1, minimum_xnys_sessions=1
    )

    assert not result.accepted
    assert any("crypto" in reason for reason in result.reasons)
    assert any("XNYS" in reason for reason in result.reasons)


def test_valid_seven_day_chain_is_accepted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(soak_module, "_change_time", soak_module._mtime)
    monkeypatch.setattr(soak_module, "_verify_data_closure", lambda *args: ())
    candidate = _candidate()
    store = SoakStore(tmp_path)
    store.write_candidate(candidate, now=candidate.started_at)
    predecessor = None
    for day in range(1, 8):
        sessions = tuple(
            f"2026-08-{session:02d}" for session in range(3, min(7, day + 3))
        )
        report = _report(
            candidate,
            recorded_at=candidate.started_at + timedelta(days=day),
            predecessor=predecessor,
            xnys_sessions=sessions,
        )
        store.append(report, now=report.recorded_at)
        predecessor = report.report_id

    result = verify_soak(
        tmp_path, tmp_path / "data", minimum_hours=168, minimum_xnys_sessions=4
    )

    assert result.accepted
    assert result.reasons == ()
    assert result.report_count == 7


def test_store_refuses_second_report_for_one_utc_day(tmp_path: Path) -> None:
    candidate = _candidate(started_at=NOW - timedelta(days=1))
    store = SoakStore(tmp_path)
    store.write_candidate(candidate, now=candidate.started_at)
    first = _report(candidate, recorded_at=NOW, predecessor=None)
    store.append(first, now=NOW)
    second = _report(
        candidate,
        recorded_at=NOW + timedelta(minutes=1),
        predecessor=first.report_id,
    )

    with pytest.raises(ValueError, match="UTC day"):
        store.append(second, now=second.recorded_at)


def test_first_report_may_share_the_candidate_freeze_instant(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(soak_module, "_change_time", soak_module._mtime)
    monkeypatch.setattr(soak_module, "_verify_data_closure", lambda *args: ())
    candidate = _candidate(started_at=NOW)
    store = SoakStore(tmp_path)
    store.write_candidate(candidate, now=NOW)
    store.append(
        _report(candidate, recorded_at=NOW, predecessor=None),
        now=NOW,
    )

    result = verify_soak(
        tmp_path, tmp_path / "data", minimum_hours=0, minimum_xnys_sessions=0
    )

    assert result.accepted
    assert result.report_count == 1


def test_soak_rejects_noncanonical_candidate_bytes(tmp_path: Path) -> None:
    candidate = _candidate()
    store = SoakStore(tmp_path)
    store.root.mkdir(parents=True, exist_ok=True)
    store.candidate_path.write_bytes(b" " + candidate.canonical_bytes())
    _set_mtime(store.candidate_path, candidate.started_at)

    result = verify_soak(
        tmp_path, tmp_path / "data", minimum_hours=0, minimum_xnys_sessions=0
    )

    assert not result.accepted
    assert any("canonical" in reason for reason in result.reasons)


def test_soak_rejects_backfill_even_when_mtime_is_forged(tmp_path: Path) -> None:
    candidate = _candidate()
    store = SoakStore(tmp_path)
    store.root.mkdir(parents=True, exist_ok=True)
    store.candidate_path.write_bytes(candidate.canonical_bytes())
    _set_mtime(store.candidate_path, candidate.started_at)
    store.report_dir.mkdir(parents=True)
    predecessor = None
    for day in range(1, 8):
        report = _report(
            candidate,
            recorded_at=candidate.started_at + timedelta(days=day),
            predecessor=predecessor,
        )
        path = store.report_path(report.report_id)
        path.write_bytes(report.canonical_bytes())
        _set_mtime(path, report.recorded_at)
        predecessor = report.report_id

    result = verify_soak(
        tmp_path, tmp_path / "data", minimum_hours=168, minimum_xnys_sessions=0
    )

    assert not result.accepted
    assert any("filesystem creation" in reason for reason in result.reasons)


def test_soak_rejects_hard_linked_candidate(tmp_path: Path) -> None:
    candidate = _candidate()
    store = SoakStore(tmp_path)
    store.root.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "candidate-source.json"
    source.write_bytes(candidate.canonical_bytes())
    os.link(source, store.candidate_path)
    _set_mtime(store.candidate_path, candidate.started_at)

    result = verify_soak(
        tmp_path, tmp_path / "data", minimum_hours=0, minimum_xnys_sessions=0
    )

    assert not result.accepted
    assert any("single-link" in reason for reason in result.reasons)


def test_soak_rejects_unexpected_report_directory_entry(tmp_path: Path) -> None:
    candidate = _candidate()
    store = SoakStore(tmp_path)
    store.write_candidate(candidate, now=candidate.started_at)
    store.report_dir.mkdir(parents=True)
    (store.report_dir / "notes.txt").write_text("not evidence", encoding="utf-8")

    result = verify_soak(
        tmp_path, tmp_path / "data", minimum_hours=0, minimum_xnys_sessions=0
    )

    assert not result.accepted
    assert any("unexpected" in reason for reason in result.reasons)


def test_soak_rejects_a_symlinked_daily_report(tmp_path: Path) -> None:
    candidate = _candidate()
    store = SoakStore(tmp_path)
    store.write_candidate(candidate, now=candidate.started_at)
    report = _report(
        candidate,
        recorded_at=candidate.started_at + timedelta(days=1),
        predecessor=None,
    )
    source = tmp_path / "outside-report.json"
    source.write_bytes(report.canonical_bytes())
    store.report_dir.mkdir(parents=True)
    try:
        os.symlink(source, store.report_path(report.report_id))
    except OSError as error:
        pytest.skip(f"symlink creation unavailable on this host: {error}")

    result = verify_soak(
        tmp_path, tmp_path / "data", minimum_hours=0, minimum_xnys_sessions=0
    )

    assert not result.accepted
    assert any("symlink or reparse" in reason for reason in result.reasons)


def test_report_reparse_check_is_applied_to_each_daily_file(
    tmp_path: Path, monkeypatch
) -> None:
    candidate = _candidate()
    store = SoakStore(tmp_path)
    store.write_candidate(candidate, now=candidate.started_at)
    report = _report(
        candidate,
        recorded_at=candidate.started_at + timedelta(days=1),
        predecessor=None,
    )
    store.report_dir.mkdir(parents=True)
    path = store.report_path(report.report_id)
    path.write_bytes(report.canonical_bytes())
    original = soak_module.is_reparse_point
    monkeypatch.setattr(
        soak_module,
        "is_reparse_point",
        lambda candidate_path: candidate_path == path or original(candidate_path),
    )

    result = verify_soak(
        tmp_path, tmp_path / "data", minimum_hours=0, minimum_xnys_sessions=0
    )

    assert not result.accepted
    assert any("symlink or reparse" in reason for reason in result.reasons)


def test_first_observation_refuses_invalid_catalog_without_freezing(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    evidence_root = tmp_path / "evidence"
    store = ManifestStore(data_root)
    coordinator = CollectionCoordinator(store)
    job = _job()
    envelope = _envelope(store)
    coordinator.capture_source(
        job,
        media_type="application/vnd.quantmesh.hyperliquid-source-batch+json",
        payload=b"[]",
        raw_payloads=(b"[]",),
    )
    publication = coordinator.run(
        job,
        producer=_producer(store, envelope),
        provider_cursor="terminal",
        last_complete_source_event=envelope.source_event_ids[-1],
        updated_at=NOW + timedelta(minutes=10),
    )

    with pytest.raises(ValueError, match="initial qualification"):
        _observe(
            evidence_root,
            data_root,
            now=NOW + timedelta(minutes=11),
            code_commit="3" * 40,
        )

    assert publication.manifest_ids
    assert not evidence_root.exists()


def test_data_closure_rejects_a_stale_reused_crypto_head(
    tmp_path: Path, monkeypatch
) -> None:
    entry = _catalog_entry(quality=_catalog_quality())
    target_id = soak_module._entry_target_id(entry)
    schema_version = "artifact-v2:" + "9" * 64 + ":test-adapter"
    candidate = SoakCandidate.build(
        started_at=NOW,
        code_commit=COMMIT,
        policy_ids=(entry.quality.policy_id,),
        calendar_versions=(entry.calendar_version,),
        schema_versions=(schema_version,),
        required_targets=(target_id,),
    )
    checkpoint_digest = soak_module._checkpoint_digest(entry)
    report = SoakReport.build(
        candidate=candidate,
        recorded_at=NOW + timedelta(days=2),
        predecessor_report_id=None,
        manifest_ids=(entry.manifest_id,),
        quality_evaluation_ids=(entry.quality.evaluation_id,),
        checkpoint_digests=(checkpoint_digest,),
        target_evidence=(
            SoakTargetEvidence(
                target_id=target_id,
                manifest_id=entry.manifest_id,
                quality_evaluation_id=entry.quality.evaluation_id,
                checkpoint_digest=checkpoint_digest,
                event_end=entry.event_end,
            ),
        ),
        completed_xnys_sessions=(),
        crypto_observed=True,
        critical_issues=(),
    )
    catalog = SimpleNamespace(
        lineage=lambda manifest_id: SimpleNamespace(entry=entry)
    )
    monkeypatch.setattr(soak_module, "TrustedDataCatalog", lambda root: catalog)
    monkeypatch.setattr(soak_module, "_REQUIRED_TARGETS", (target_id,))
    monkeypatch.setattr(soak_module, "_git_commit", lambda: COMMIT)
    manifest = SimpleNamespace(
        schema_version=2,
        schema_digest="9" * 64,
        adapter_version="test-adapter",
        code_commit=COMMIT,
    )
    manifest_store = SimpleNamespace(
        open=lambda manifest_id: SimpleNamespace(manifest=manifest)
    )
    monkeypatch.setattr(soak_module, "ManifestStore", lambda root: manifest_store)

    reasons = soak_module._verify_data_closure(tmp_path, candidate, (report,))

    assert any("stale" in reason for reason in reasons)


def test_data_closure_rejects_a_candidate_defined_target_matrix(
    tmp_path: Path, monkeypatch
) -> None:
    entry = _catalog_entry(quality=_catalog_quality())
    target_id = soak_module._entry_target_id(entry)
    candidate = SoakCandidate.build(
        started_at=NOW,
        code_commit=COMMIT,
        policy_ids=(entry.quality.policy_id,),
        calendar_versions=(entry.calendar_version,),
        schema_versions=("artifact-v2:bars-v1",),
        required_targets=(target_id, "required-but-missing"),
    )
    checkpoint_digest = soak_module._checkpoint_digest(entry)
    report = SoakReport.build(
        candidate=candidate,
        recorded_at=NOW,
        predecessor_report_id=None,
        manifest_ids=(entry.manifest_id,),
        quality_evaluation_ids=(entry.quality.evaluation_id,),
        checkpoint_digests=(checkpoint_digest,),
        target_evidence=(
            SoakTargetEvidence(
                target_id=target_id,
                manifest_id=entry.manifest_id,
                quality_evaluation_id=entry.quality.evaluation_id,
                checkpoint_digest=checkpoint_digest,
                event_end=entry.event_end,
            ),
        ),
        completed_xnys_sessions=(),
        crypto_observed=True,
        critical_issues=(),
    )
    catalog = SimpleNamespace(
        lineage=lambda manifest_id: SimpleNamespace(entry=entry)
    )
    monkeypatch.setattr(soak_module, "TrustedDataCatalog", lambda root: catalog)

    reasons = soak_module._verify_data_closure(tmp_path, candidate, (report,))

    assert any("exact five-target matrix" in reason for reason in reasons)
