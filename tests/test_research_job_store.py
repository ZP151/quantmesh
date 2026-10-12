"""Durability, fencing and independently recoverable advisory outbox."""

import hashlib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from test_research_jobs import request_for

from quantmesh.research.job_store import SQLiteJobStore
from quantmesh.research.jobs import (
    AnalysisRecord,
    ArtifactRef,
    DatasetRejected,
    IdempotencyConflict,
    StoreUnavailable,
)
from tests.research_fixtures import pinned_lake


@pytest.fixture
def setup(tmp_path):
    lake = tmp_path / "lake"
    pinned_lake(lake)
    now = [datetime.now(UTC)]
    path = tmp_path / "jobs.sqlite"
    store = SQLiteJobStore(path, lake_root=lake, clock=lambda: now[0])
    return store, lake, path, now


def report_artifact(store, job):
    raw = json.dumps({"request_digest": job.request_digest, "fixture": True}).encode()
    digest = hashlib.sha256(raw).hexdigest()
    key = f"{job.job_id}/{digest}.json"
    path = store.artifact_root / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return ArtifactRef(
        artifact_id=digest,
        kind="report",
        schema_version=1,
        sha256=digest,
        byte_size=len(raw),
        object_key=key,
    )


def analysis_record(lease, state="failed"):
    return AnalysisRecord(
        job_id=lease.job_id,
        report_digest=lease.report_digest,
        state=state,
        citations=[],
        verdict="unavailable",
        error_code="analysis_failed",
    )


def analysis_output(store, job, report):
    raw = json.dumps(
        {
            "job_id": job.job_id,
            "report_digest": report.sha256,
            "verdict": "inconclusive",
            "fixture": True,
        }
    ).encode()
    digest = hashlib.sha256(raw).hexdigest()
    ref = ArtifactRef(
        artifact_id=digest,
        kind="analysis",
        sha256=digest,
        byte_size=len(raw),
        object_key=f"{job.job_id}/{digest}.json",
    )
    (store.artifact_root / ref.object_key).write_bytes(raw)
    return AnalysisRecord(
        job_id=job.job_id,
        report_digest=report.sha256,
        state="succeeded",
        provider="offline",
        model="scripted-fixture",
        prompt_digest="a" * 64,
        output_digest=digest,
        output_artifact=ref,
        citations=[report],
        verdict="inconclusive",
    )


def test_same_key_same_job_and_conflict(setup):
    store, lake, path, now = setup
    req = request_for(lake)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = list(pool.map(lambda _: store.submit("local", "key", req), range(2)))
    assert jobs[0].job_id == jobs[1].job_id
    reopened = SQLiteJobStore(path, lake_root=lake, clock=lambda: now[0])
    assert reopened.get("local", jobs[0].job_id) == jobs[0]
    assert reopened.submit("local", "key", req).job_id == jobs[0].job_id
    with pytest.raises(IdempotencyConflict):
        store.submit("local", "key", request_for(lake, analysis_requested=True))
    with pytest.raises(KeyError):
        store.get("other", jobs[0].job_id)
    assert jobs[0].usage.estimated_model_usd is None


def test_expired_attempt_cannot_publish(setup):
    store, lake, _, now = setup
    job = store.submit("local", "key", request_for(lake))
    first = store.claim("worker-a", now[0])
    assert first.attempt == 1
    assert store.heartbeat(job.job_id, "wrong", 1, now[0]) is False
    now[0] += timedelta(seconds=61)
    assert store.heartbeat(job.job_id, "worker-a", 1, now[0]) is False
    assert store.finish(job.job_id, "worker-a", 1, "failed", [], "worker_failed") is False
    second = store.claim("worker-b", now[0])
    assert second.attempt == 2
    artifact = report_artifact(store, job)
    assert store.finish(job.job_id, "worker-a", 1, "succeeded", [artifact], None) is False
    assert store.finish(job.job_id, "worker-b", 2, "succeeded", [artifact], None) is True
    assert store.finish(job.job_id, "worker-b", 2, "succeeded", [artifact], None) is False


def test_cancel_revokes_publication(setup):
    store, lake, _, now = setup
    job = store.submit("local", "key", request_for(lake, analysis_requested=True))
    store.claim("worker", now[0])
    cancelled = store.request_cancel("local", job.job_id)
    assert cancelled.state == "cancelled"
    assert cancelled.analysis_state == "cancelled"
    assert (
        store.finish(job.job_id, "worker", 1, "succeeded", [report_artifact(store, job)], None)
        is False
    )
    assert store.claim_analysis("analyst", now[0]) is None


def test_analysis_outbox_is_atomic_and_independent(setup):
    store, lake, path, now = setup
    job = store.submit("local", "key", request_for(lake, analysis_requested=True))
    assert store.claim_analysis("analyst", now[0]) is None
    store.claim("worker", now[0])
    assert store.finish(job.job_id, "worker", 1, "succeeded", [report_artifact(store, job)], None)
    store = SQLiteJobStore(path, lake_root=lake, clock=lambda: now[0])
    assert store.get("local", job.job_id).analysis_state == "pending"
    lease = store.claim_analysis("analyst", now[0])
    assert store.claim_analysis("other", now[0]) is None
    assert store.heartbeat_analysis(lease, now[0])
    now[0] += timedelta(seconds=61)
    assert store.heartbeat_analysis(lease, now[0]) is False
    assert store.finish_analysis(lease, analysis_record(lease)) is False
    replacement = store.claim_analysis("other", now[0])
    assert replacement.attempt == 2
    assert store.finish_analysis(replacement, analysis_record(replacement))
    result = store.get("local", job.job_id)
    assert result.state == "succeeded" and result.analysis_state == "failed"
    assert result.analysis.usage.estimated_model_usd is None


def test_cancel_analysis_preserves_success(setup):
    store, lake, _, now = setup
    job = store.submit("local", "key", request_for(lake, analysis_requested=True))
    store.claim("worker", now[0])
    assert store.finish(job.job_id, "worker", 1, "succeeded", [report_artifact(store, job)], None)
    lease = store.claim_analysis("analyst", now[0])
    result = store.request_cancel("local", job.job_id)
    assert result.state == "succeeded" and result.analysis_state == "cancelled"
    assert store.finish_analysis(lease, analysis_record(lease)) is False


def test_admission_rejects_changed_manifest_and_permission(setup):
    store, lake, _, _ = setup
    request = request_for(lake)
    path = lake / "equities" / "manifest.json"
    original = path.read_bytes()
    manifest = json.loads(original)
    manifest["source"] = "real-provider"
    path.write_text(json.dumps(manifest))
    with pytest.raises(DatasetRejected):
        store.submit("local", "key", request)
    path.write_bytes(original)
    assert store.claim("worker", datetime.now(UTC)) is None
    admitted = store.submit("local", "key", request)
    assert admitted.state == "queued"


def test_concurrency_and_artifact_lineage_fail_closed(setup):
    store, lake, _, now = setup
    for i in range(3):
        store.submit("local", str(i), request_for(lake))
    one = store.claim("one", now[0])
    assert store.claim("two", now[0]) is not None
    assert store.claim("three", now[0]) is None
    artifact = report_artifact(store, one)
    (store.artifact_root / artifact.object_key).write_text("tampered")
    with pytest.raises(ValueError):
        store.finish(one.job_id, "one", 1, "succeeded", [artifact], None)
    assert store.get("local", one.job_id).state == "running"


def test_unavailable_is_sanitized(tmp_path):
    path = tmp_path / "secret-token"
    path.write_text("invalid sqlite")
    with pytest.raises(StoreUnavailable) as exc:
        SQLiteJobStore(path)
    assert "secret-token" not in str(exc.value)


def test_cli_submit_status_reopen(setup, tmp_path):
    _, lake, path, _ = setup
    request_path = tmp_path / "request.json"
    request_path.write_text(request_for(lake).model_dump_json())
    common = ["--store", str(path), "--lake-root", str(lake)]
    submit = subprocess.run(
        [
            sys.executable,
            "tools/research_job.py",
            "submit",
            "--request",
            str(request_path),
            "--key",
            "cli",
            *common,
        ],
        capture_output=True,
        text=True,
    )
    assert submit.returncode == 0, submit.stderr
    job = json.loads(submit.stdout)
    status = subprocess.run(
        [sys.executable, "tools/research_job.py", "status", "--job-id", job["job_id"], *common],
        capture_output=True,
        text=True,
    )
    assert status.returncode == 0, status.stderr
    saved = json.loads(status.stdout)
    assert (saved["job_id"], saved["request_digest"], saved["state"]) == (
        job["job_id"],
        job["request_digest"],
        "queued",
    )


@pytest.mark.parametrize(
    "fault",
    [
        "revision",
        "manifest",
        "export",
        "permission",
        "window",
        "future",
        "missing",
        "duplicate",
        "nonfinite",
    ],
)
def test_rejected_admission_never_queues(setup, fault):
    from quantmesh.data.lake import Lake
    from quantmesh.data.manifest import ManifestWriter
    from quantmesh.research.jobs import DatasetRef
    from tests.research_fixtures import fixture_bars

    store, lake, _, now = setup
    request = request_for(lake)
    if fault in ("revision", "manifest", "export", "permission"):
        field, value = {
            "revision": ("revision", 2),
            "manifest": ("manifest_digest", "0" * 64),
            "export": ("export_digest", "0" * 64),
            "permission": ("permission_class", "remote_export"),
        }[fault]
        ref = DatasetRef.model_validate({**request.dataset.model_dump(), field: value})
        request = request_for(lake, dataset=ref)
    elif fault == "window":
        request = request_for(lake, window_spec={"train_bars": 60, "test_bars": 5, "step_bars": 5})
    elif fault == "future":
        now[0] = datetime(2025, 1, 1, tzinfo=UTC)
    elif fault == "missing":
        request = request_for(lake, universe=[{"venue": "moomoo", "symbol": "NOTHERE"}])
    else:
        bars = fixture_bars("AAA")
        if fault == "duplicate":
            bars[1] = bars[0]
        else:
            bars[1] = bars[1].model_copy(update={"high": float("inf")})
        Lake(lake).write_bars("equities", bars)
        ManifestWriter(lake).generate("equities", source="fixture", license="test")
        request = request_for(lake)
    with pytest.raises(DatasetRejected):
        store.submit("local", "rejected", request)
    assert store.claim("worker", now[0]) is None


def test_heartbeat_and_pinned_implementation(setup):
    store, lake, _, now = setup
    job = store.submit("local", "heartbeat", request_for(lake))
    from quantmesh.research.strategy_registry import get_strategy

    assert job.implementation_digest == get_strategy("momentum", "1").implementation_digest
    claimed = store.claim("worker", now[0])
    now[0] += timedelta(seconds=15)
    assert store.heartbeat(job.job_id, "worker", claimed.attempt, now[0])
    assert store.get("local", job.job_id).lease_expires_at == now[0] + timedelta(seconds=60)
    assert store.finish(job.job_id, "worker", claimed.attempt, "failed", [], "worker_failed")
    result = store.get("local", job.job_id)
    assert result.state == "failed" and result.error_code == "worker_failed"


def test_cli_errors_never_echo_user_payload(setup, tmp_path):
    _, lake, path, _ = setup
    request_path = tmp_path / "hostile.json"
    request_path.write_text('{"order": "buy", "token": "secret-test-value"}')
    result = subprocess.run(
        [
            sys.executable,
            "tools/research_job.py",
            "submit",
            "--request",
            str(request_path),
            "--key",
            "unsafe",
            "--store",
            str(path),
            "--lake-root",
            str(lake),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert json.loads(result.stderr) == {"error_code": "invalid_request"}
    assert "secret-test-value" not in result.stderr


def test_analysis_citations_must_resolve_to_published_evidence(setup):
    store, lake, _, now = setup
    job = store.submit("local", "cited", request_for(lake, analysis_requested=True))
    store.claim("worker", now[0])
    report = report_artifact(store, job)
    assert store.finish(job.job_id, "worker", 1, "succeeded", [report], None)
    lease = store.claim_analysis("analyst", now[0])
    record = analysis_output(store, job, report).model_copy(
        update={"citations": [report.model_copy(update={"artifact_id": "c" * 64})]}
    )
    with pytest.raises(ValueError, match="citation"):
        store.finish_analysis(lease, record)
    assert store.get("local", job.job_id).analysis_state == "running"
    # Even a registered reference must still resolve to its original bytes.
    record = record.model_copy(update={"citations": [report]})
    (store.artifact_root / report.object_key).write_text("tampered")
    with pytest.raises(ValueError):
        store.finish_analysis(lease, record)
    assert store.get("local", job.job_id).state == "succeeded"


@pytest.mark.parametrize("fault", ["missing", "tampered", "digest", "lineage", "none"])
def test_analysis_archive_required_and_verified(setup, fault):
    store, lake, _, now = setup
    job = store.submit("local", "archived", request_for(lake, analysis_requested=True))
    store.claim("worker", now[0])
    report = report_artifact(store, job)
    assert store.finish(job.job_id, "worker", 1, "succeeded", [report], None)
    lease = store.claim_analysis("analyst", now[0])
    record = analysis_output(store, job, report)
    output = store.artifact_root / record.output_artifact.object_key
    if fault == "missing":
        output.unlink()
    elif fault == "tampered":
        output.write_text("changed bytes")
    elif fault == "digest":
        record = record.model_copy(update={"output_digest": "b" * 64})
    elif fault == "none":
        record = record.model_copy(update={"output_artifact": None})
    else:
        raw = json.dumps({"job_id": "wrong", "report_digest": report.sha256}).encode()
        digest = hashlib.sha256(raw).hexdigest()
        ref = ArtifactRef(
            artifact_id=digest,
            kind="analysis",
            sha256=digest,
            byte_size=len(raw),
            object_key=f"{job.job_id}/{digest}.json",
        )
        (store.artifact_root / ref.object_key).write_bytes(raw)
        record = record.model_copy(update={"output_artifact": ref, "output_digest": digest})
    with pytest.raises(ValueError):
        store.finish_analysis(lease, record)
    assert store.get("local", job.job_id).analysis_state == "running"


def test_successful_analysis_replays_archived_reference(setup):
    store, lake, path, now = setup
    job = store.submit("local", "archive-success", request_for(lake, analysis_requested=True))
    store.claim("worker", now[0])
    report = report_artifact(store, job)
    assert store.finish(job.job_id, "worker", 1, "succeeded", [report], None)
    lease = store.claim_analysis("analyst", now[0])
    record = analysis_output(store, job, report)
    assert store.finish_analysis(lease, record)
    reopened = SQLiteJobStore(path, lake_root=lake, clock=lambda: now[0]).get("local", job.job_id)
    assert reopened.analysis == record and reopened.state == "succeeded"
    assert reopened.analysis_state == "succeeded"
    assert store.claim_analysis("again", now[0]) is None


def test_v2_manifest_has_explicit_unsupported_reason(setup):
    store, lake, _, _ = setup
    request = request_for(lake)
    (lake / "equities" / "manifest.json").write_text(json.dumps({"schema_version": 2}))
    with pytest.raises(DatasetRejected) as exc:
        store.submit("local", "v2", request)
    assert exc.value.reason == "manifest_schema_unsupported"


def test_missing_rights_has_explicit_permission_reason(setup):
    store, lake, _, _ = setup
    request = request_for(lake)
    path = lake / "equities" / "manifest.json"
    manifest = json.loads(path.read_text())
    del manifest["license"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(DatasetRejected) as exc:
        store.submit("local", "unknown-rights", request)
    assert exc.value.reason == "permission_unsupported"
