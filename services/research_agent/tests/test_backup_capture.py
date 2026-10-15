from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr
from qm_research_agent import backup_capture
from qm_research_agent.accounting import PortfolioBudgetPolicy

from quantmesh.research.jobs import (
    AnalysisLease,
    ArtifactRef,
    JobRecord,
    canonical_request_digest,
)
from quantmesh.research.strategy_registry import get_strategy
from tests.research_fixtures import pinned_lake
from tests.test_research_jobs import request_for


class FakeDatabase:
    def __init__(
        self,
        *,
        ledger_tables=(),
        jobs=(),
        outbox=(),
        effects=(),
        portfolio_schema=(),
        portfolio_policy=(),
        reservations=(),
        broken_effect_join=False,
    ):
        self.ledger_tables = set(ledger_tables)
        self.jobs = list(jobs)
        self.outbox = list(outbox)
        self.effects = list(effects)
        self.portfolio_schema = list(portfolio_schema)
        self.portfolio_policy = list(portfolio_policy)
        self.reservations = list(reservations)
        self.broken_effect_join = broken_effect_join
        self.statements = []
        self.closed = False
        self.rolled_back = False
        self.events = []
        self.snapshot = "owned-snapshot-token-must-not-escape"

    def cursor(self):
        return FakeCursor(self)

    def rollback(self):
        self.events.append("rollback")
        self.rolled_back = True

    def close(self):
        self.events.append("close")
        self.closed = True


class FakeCursor:
    def __init__(self, database):
        self.database = database
        self.rows = []
        self.current_sql = ""

    def execute(self, sql, params=()):
        normalized = " ".join(sql.split())
        lower = normalized.lower()
        self.current_sql = lower
        self.database.statements.append((normalized, tuple(params)))
        assert not any(
            word in lower.split()
            for word in ("create", "insert", "update", "delete", "drop", "truncate")
        ), normalized
        if lower.startswith("set transaction isolation level repeatable read read only"):
            self.rows = []
        elif lower.startswith("set local statement_timeout"):
            self.rows = []
        elif lower.startswith("set local search_path"):
            assert '"qm_research"' in normalized
            self.rows = []
        elif lower == "select pg_export_snapshot()":
            self.rows = [(self.database.snapshot,)]
        elif lower.startswith("select version from qm_schema"):
            self.rows = [(1,)]
        elif lower.startswith("select to_regclass("):
            relation = params[0].split(".", 1)[1]
            self.rows = [
                (f"qm_research.{relation}" if relation in self.database.ledger_tables else None,)
            ]
        elif lower.startswith(
            "select job_id,operator_id,idempotency_key,payload,sequence from jobs"
        ):
            self.rows = self.database.jobs
        elif lower.startswith("select job_id,lease,attempt,sequence from analysis_outbox"):
            self.rows = self.database.outbox
        elif lower.startswith(
            "select job_id,digest,price,status,response,checkpoint from model_effects"
        ):
            self.rows = self.database.effects
        elif lower.startswith("select version from qm_portfolio_schema"):
            self.rows = getattr(self.database, "portfolio_schema", [])
        elif lower.startswith("select slot,policy_id,operating_monthly_usd"):
            self.rows = self.database.portfolio_policy
        elif lower.startswith("select job_id,digest,category,period,price,reserved_at"):
            self.rows = self.database.reservations
        elif lower.startswith("select 1 from model_effects e left join"):
            self.rows = [(1,)] if self.database.broken_effect_join else []
        elif lower.startswith("select 1 from qm_portfolio_reservations r left join"):
            self.rows = [(1,)] if self.database.broken_effect_join else []
        else:
            raise AssertionError(f"unexpected SQL: {normalized}")
        return self

    def fetchall(self):
        assert not self.current_sql.startswith("set "), self.current_sql
        return list(self.rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None


def install_fake(monkeypatch, database):
    calls = []

    def connect(dsn):
        assert isinstance(dsn, SecretStr)
        calls.append(dsn)
        return database

    monkeypatch.setattr(backup_capture, "connect", connect)
    return calls


def make_job(
    lake, *, job_id="job-1", key="key-1", analysis_requested=False, state="queued", refs=()
):
    now = datetime.now(UTC)
    request = request_for(lake, analysis_requested=analysis_requested)
    implementation = get_strategy(request.strategy_id, request.strategy_version)
    return JobRecord(
        job_id=job_id,
        operator_id="operator",
        idempotency_key=key,
        request=request,
        request_digest=canonical_request_digest(request),
        implementation_digest=implementation.implementation_digest,
        state=state,
        attempt=1 if state == "running" else 0,
        lease_owner="worker" if state == "running" else None,
        lease_expires_at=now if state == "running" else None,
        error_code="worker_failed"
        if state == "failed"
        else ("cancelled" if state == "cancelled" else None),
        created_at=now,
        updated_at=now,
        finished_at=now if state in {"succeeded", "failed", "cancelled"} else None,
        artifacts=list(refs),
        analysis_state=(
            "not_requested"
            if not analysis_requested
            else ("cancelled" if state in {"failed", "cancelled"} else "pending")
        ),
    )


def db_job(job, sequence=1):
    return (
        job.job_id,
        job.operator_id,
        job.idempotency_key,
        job.model_dump_json(),
        sequence,
    )


def with_report(job, artifact_root):
    report_bytes = json.dumps(
        {
            "schema_version": 1,
            "request_digest": job.request_digest,
            "implementation_digest": job.implementation_digest,
            "result": {"metrics": {"sharpe": 1.25}},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    digest = hashlib.sha256(report_bytes).hexdigest()
    ref = ArtifactRef(
        artifact_id=digest,
        kind="report",
        sha256=digest,
        byte_size=len(report_bytes),
        object_key=f"{job.job_id}/{digest}.json",
    )
    job = job.model_copy(update={"artifacts": [ref]})
    job_dir = artifact_root / job.job_id
    job_dir.mkdir(mode=0o700)
    source = job_dir / f"{digest}.json"
    source.write_bytes(report_bytes)
    source.chmod(0o600)
    return job, ref


def test_capture_empty_uninitialized_store_exports_readonly_snapshot(monkeypatch, tmp_path):
    database = FakeDatabase()
    calls = install_fake(monkeypatch, database)
    output = tmp_path / "capture"
    lake = tmp_path / "lake"
    artifacts = tmp_path / "artifacts"
    lake.mkdir()
    artifacts.mkdir()
    result = backup_capture.capture_manifest(
        SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
        schema="qm_research",
        lake_root=lake,
        artifact_root=artifacts,
        output_root=output,
        policy=None,
    )

    assert len(calls) == 1
    sql = [statement.lower() for statement, _ in database.statements]
    assert sql.count("select pg_export_snapshot()") == 1
    assert sql[0].startswith("set transaction isolation level repeatable read read only")
    assert not any("advisory" in statement for statement in sql)
    assert result["snapshot_closed"] is True
    assert result["manifest_only"] is True
    assert result["manifest"]["effect_ledger"] == "uninitialized"
    assert result["manifest"]["references"] == []
    assert result["manifest"]["row_sequence_maxima"] == {"jobs": None, "analysis_outbox": None}
    assert database.rolled_back and database.closed
    assert database.snapshot not in json.dumps(result)
    assert (output.stat().st_mode & 0o777) == 0o700


def test_capture_rejects_schema_before_connect_or_output(monkeypatch, tmp_path):
    database = FakeDatabase()
    calls = install_fake(monkeypatch, database)
    output = tmp_path / "capture"
    lake = tmp_path / "lake"
    artifacts = tmp_path / "artifacts"
    lake.mkdir()
    artifacts.mkdir()

    with pytest.raises(ValueError):
        backup_capture.capture_manifest(
            SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
            schema="quantmesh",
            lake_root=lake,
            artifact_root=artifacts,
            output_root=output,
            policy=None,
        )

    assert calls == []
    assert not output.exists()


def test_transaction_setup_never_fetches_a_result_set(monkeypatch, tmp_path):
    database = FakeDatabase()
    install_fake(monkeypatch, database)
    lake = tmp_path / "lake"
    artifacts = tmp_path / "artifacts"
    lake.mkdir()
    artifacts.mkdir()

    backup_capture.capture_manifest(
        SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
        schema="qm_research",
        lake_root=lake,
        artifact_root=artifacts,
        output_root=tmp_path / "capture",
        policy=None,
    )


def test_all_present_empty_unconfigured_effect_ledger_is_capturable(monkeypatch, tmp_path):
    database = FakeDatabase(
        ledger_tables={
            "model_effects",
            "qm_portfolio_schema",
            "qm_portfolio_policy",
            "qm_portfolio_reservations",
        },
        portfolio_schema=[(1,)],
    )
    install_fake(monkeypatch, database)
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    pinned_lake(lake)
    artifacts.mkdir()

    result = backup_capture.capture_manifest(
        SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
        schema="qm_research",
        lake_root=lake,
        artifact_root=artifacts,
        output_root=tmp_path / "capture",
        policy=None,
    )

    assert result["manifest"]["effect_ledger"] == "unconfigured"
    assert result["manifest"]["effects"] == []
    assert result["manifest"]["reservations"] == []


def test_partial_effect_accounting_schema_refuses_before_output(monkeypatch, tmp_path):
    database = FakeDatabase(ledger_tables={"model_effects"})
    install_fake(monkeypatch, database)
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    lake.mkdir()
    artifacts.mkdir()
    output = tmp_path / "capture"

    with pytest.raises(ValueError):
        backup_capture.capture_manifest(
            SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
            schema="qm_research",
            lake_root=lake,
            artifact_root=artifacts,
            output_root=output,
            policy=None,
        )

    assert not output.exists()


def test_succeeded_job_copies_only_verified_report_reference(monkeypatch, tmp_path):
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    pinned_lake(lake)
    artifacts.mkdir()
    job = make_job(lake, state="succeeded")
    report_bytes = json.dumps(
        {
            "schema_version": 1,
            "request_digest": job.request_digest,
            "implementation_digest": job.implementation_digest,
            "result": {"metrics": {"sharpe": 1.25}},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    digest = hashlib.sha256(report_bytes).hexdigest()
    ref = ArtifactRef(
        artifact_id=digest,
        kind="report",
        sha256=digest,
        byte_size=len(report_bytes),
        object_key=f"{job.job_id}/{digest}.json",
    )
    job = job.model_copy(update={"artifacts": [ref]})
    job_dir = artifacts / job.job_id
    job_dir.mkdir(mode=0o700)
    source = job_dir / f"{digest}.json"
    source.write_bytes(report_bytes)
    source.chmod(0o600)
    database = FakeDatabase(jobs=[db_job(job, 2)])
    install_fake(monkeypatch, database)
    output = tmp_path / "capture"

    result = backup_capture.capture_manifest(
        SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
        schema="qm_research",
        lake_root=lake,
        artifact_root=artifacts,
        output_root=output,
        policy=None,
    )

    assert result["manifest"]["references"] == [
        {
            "job_id": job.job_id,
            "object_key": ref.object_key,
            "kind": "report",
            "byte_size": len(report_bytes),
            "sha256": digest,
        }
    ]
    assert (output / "artifacts" / job.job_id / f"{digest}.json").read_bytes() == report_bytes
    assert backup_capture.validate_manifest(output, result["manifest_sha256"]) == result["manifest"]

    original_copy = backup_capture._copy_one

    def mutate_then_copy(source_root_fd, destination_root_fd, reference):
        source.write_bytes(b"changed after snapshot validation")
        source.chmod(0o600)
        original_copy(source_root_fd, destination_root_fd, reference)

    monkeypatch.setattr(backup_capture, "_copy_one", mutate_then_copy)
    changed_output = tmp_path / "changed-capture"
    with pytest.raises(ValueError):
        backup_capture.capture_manifest(
            SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
            schema="qm_research",
            lake_root=lake,
            artifact_root=artifacts,
            output_root=changed_output,
            policy=None,
        )
    assert not changed_output.exists()


def test_succeeded_job_refuses_report_from_another_job(monkeypatch, tmp_path):
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    pinned_lake(lake)
    artifacts.mkdir()
    job = make_job(lake, state="succeeded")
    digest = "a" * 64
    job = job.model_copy(
        update={
            "artifacts": [
                ArtifactRef(
                    artifact_id=digest,
                    kind="report",
                    sha256=digest,
                    byte_size=1,
                    object_key=f"another-job/{digest}.json",
                )
            ]
        }
    )
    install_fake(monkeypatch, FakeDatabase(jobs=[db_job(job)]))

    with pytest.raises(ValueError):
        backup_capture.capture_manifest(
            SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
            schema="qm_research",
            lake_root=lake,
            artifact_root=artifacts,
            output_root=tmp_path / "capture",
            policy=None,
        )


def test_succeeded_pending_analysis_requires_unleased_outbox_row(monkeypatch, tmp_path):
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    pinned_lake(lake)
    artifacts.mkdir()
    job, _ = with_report(make_job(lake, state="succeeded", analysis_requested=True), artifacts)
    job = job.model_copy(update={"analysis_state": "pending"})
    install_fake(monkeypatch, FakeDatabase(jobs=[db_job(job)]))

    with pytest.raises(ValueError):
        backup_capture.capture_manifest(
            SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
            schema="qm_research",
            lake_root=lake,
            artifact_root=artifacts,
            output_root=tmp_path / "capture",
            policy=None,
        )


def test_succeeded_pending_analysis_with_empty_outbox_lease_is_capturable(monkeypatch, tmp_path):
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    pinned_lake(lake)
    artifacts.mkdir()
    job, _ = with_report(make_job(lake, state="succeeded", analysis_requested=True), artifacts)
    job = job.model_copy(update={"analysis_state": "pending"})
    database = FakeDatabase(jobs=[db_job(job)], outbox=[(job.job_id, None, 0, 1)])
    install_fake(monkeypatch, database)

    result = backup_capture.capture_manifest(
        SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
        schema="qm_research",
        lake_root=lake,
        artifact_root=artifacts,
        output_root=tmp_path / "capture",
        policy=None,
    )

    assert result["manifest"]["jobs"][0]["analysis_state"] == "pending"
    assert result["manifest"]["row_sequence_maxima"]["analysis_outbox"] == 1


def test_succeeded_running_analysis_requires_lease(monkeypatch, tmp_path):
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    pinned_lake(lake)
    artifacts.mkdir()
    job, _ = with_report(make_job(lake, state="succeeded", analysis_requested=True), artifacts)
    job = job.model_copy(update={"analysis_state": "running"})
    database = FakeDatabase(jobs=[db_job(job)], outbox=[(job.job_id, None, 1, 1)])
    install_fake(monkeypatch, database)

    with pytest.raises(ValueError):
        backup_capture.capture_manifest(
            SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
            schema="qm_research",
            lake_root=lake,
            artifact_root=artifacts,
            output_root=tmp_path / "capture",
            policy=None,
        )


def test_expired_analysis_lease_remains_capturable(monkeypatch, tmp_path):
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    pinned_lake(lake)
    artifacts.mkdir()
    job, report = with_report(make_job(lake, state="succeeded", analysis_requested=True), artifacts)
    job = job.model_copy(update={"analysis_state": "running"})
    lease = AnalysisLease(
        job_id=job.job_id,
        owner="analyst",
        attempt=3,
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
        report_digest=report.sha256,
    )
    database = FakeDatabase(
        jobs=[db_job(job)],
        outbox=[(job.job_id, lease.model_dump_json(), lease.attempt, 1)],
    )
    install_fake(monkeypatch, database)

    result = backup_capture.capture_manifest(
        SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
        schema="qm_research",
        lake_root=lake,
        artifact_root=artifacts,
        output_root=tmp_path / "capture",
        policy=None,
    )

    assert result["manifest"]["jobs"][0]["analysis_state"] == "running"
    assert result["manifest"]["row_sequence_maxima"]["analysis_outbox"] == 1


def test_capture_cleanup_errors_do_not_skip_database_cleanup(monkeypatch, tmp_path):
    database = FakeDatabase()
    install_fake(monkeypatch, database)
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    lake.mkdir()
    artifacts.mkdir()

    def fail_manifest(*args, **kwargs):
        raise OSError("private filesystem detail")

    def fail_cleanup(*args, **kwargs):
        raise backup_capture.ManifestCaptureRefused("internal test sentinel")

    opened_fds = set()
    original_open_directory = backup_capture._open_directory
    original_create_output_root = backup_capture._create_output_root

    def track_open_directory(*args, **kwargs):
        fd = original_open_directory(*args, **kwargs)
        opened_fds.add(fd)
        return fd

    def track_create_output_root(*args, **kwargs):
        fds = original_create_output_root(*args, **kwargs)
        opened_fds.update(fds)
        return fds

    monkeypatch.setattr(backup_capture, "_open_directory", track_open_directory)
    monkeypatch.setattr(backup_capture, "_create_output_root", track_create_output_root)
    monkeypatch.setattr(backup_capture, "_write_manifest", fail_manifest)
    monkeypatch.setattr(backup_capture, "_remove_output_root", fail_cleanup)

    with pytest.raises(ValueError, match="^research snapshot manifest refused$"):
        backup_capture.capture_manifest(
            SecretStr("postgresql://fixture:private@127.0.0.1/fixture?sslmode=disable"),
            schema="qm_research",
            lake_root=lake,
            artifact_root=artifacts,
            output_root=tmp_path / "capture",
            policy=None,
        )

    assert database.rolled_back
    assert database.closed
    for fd in opened_fds:
        with pytest.raises(OSError):
            os.fstat(fd)


def test_reserved_effect_and_reservation_are_preserved(monkeypatch, tmp_path):
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    pinned_lake(lake)
    artifacts.mkdir()
    job = make_job(lake, state="queued")
    stamp = "2026-10-15T00:00:00.000000+00:00"
    policy = PortfolioBudgetPolicy("test-policy", Decimal("1"), Decimal("1"))
    effect_digest = "e" * 64
    database = FakeDatabase(
        jobs=[db_job(job)],
        ledger_tables={
            "model_effects",
            "qm_portfolio_schema",
            "qm_portfolio_policy",
            "qm_portfolio_reservations",
        },
        portfolio_schema=[(1,)],
        portfolio_policy=[(1, *policy.binding(), stamp)],
        effects=[(job.job_id, effect_digest, "0.5", "reserved", None, None)],
        reservations=[(job.job_id, effect_digest, "development", "2026-10", "0.5", stamp)],
    )
    install_fake(monkeypatch, database)

    result = backup_capture.capture_manifest(
        SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
        schema="qm_research",
        lake_root=lake,
        artifact_root=artifacts,
        output_root=tmp_path / "capture",
        policy=policy,
    )

    assert result["manifest"]["effect_ledger"] == "configured"
    assert result["manifest"]["portfolio_high_water"] == stamp
    assert result["manifest"]["effects"][0]["status"] == "reserved"
    assert result["manifest"]["effects"][0]["response_sha256"] is None
    assert result["manifest"]["reservations"][0]["job_id"] == job.job_id


def test_no_lease_outbox_for_no_analysis_job_is_rejected(monkeypatch, tmp_path):
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    pinned_lake(lake)
    artifacts.mkdir()
    job = make_job(lake, state="running", analysis_requested=False)
    install_fake(monkeypatch, FakeDatabase(jobs=[db_job(job)], outbox=[(job.job_id, None, 0, 1)]))

    with pytest.raises(ValueError):
        backup_capture.capture_manifest(
            SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
            schema="qm_research",
            lake_root=lake,
            artifact_root=artifacts,
            output_root=tmp_path / "capture",
            policy=None,
        )


def test_outbox_row_without_job_is_rejected(monkeypatch, tmp_path):
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    pinned_lake(lake)
    artifacts.mkdir()
    install_fake(
        monkeypatch,
        FakeDatabase(outbox=[("missing-job", None, 0, 1)]),
    )

    with pytest.raises(ValueError):
        backup_capture.capture_manifest(
            SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
            schema="qm_research",
            lake_root=lake,
            artifact_root=artifacts,
            output_root=tmp_path / "capture",
            policy=None,
        )


def test_effect_and_reservation_pair_without_job_is_rejected(monkeypatch, tmp_path):
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    pinned_lake(lake)
    artifacts.mkdir()
    stamp = "2026-10-15T00:00:00.000000+00:00"
    policy = PortfolioBudgetPolicy("test-policy", Decimal("1"), Decimal("1"))
    digest = "d" * 64
    database = FakeDatabase(
        ledger_tables={
            "model_effects",
            "qm_portfolio_schema",
            "qm_portfolio_policy",
            "qm_portfolio_reservations",
        },
        portfolio_schema=[(1,)],
        portfolio_policy=[(1, *policy.binding(), stamp)],
        effects=[("ghost-job", digest, "0.5", "reserved", None, None)],
        reservations=[("ghost-job", digest, "development", "2026-10", "0.5", stamp)],
    )
    install_fake(monkeypatch, database)

    with pytest.raises(ValueError):
        backup_capture.capture_manifest(
            SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
            schema="qm_research",
            lake_root=lake,
            artifact_root=artifacts,
            output_root=tmp_path / "capture",
            policy=policy,
        )


@pytest.mark.parametrize("state", ["queued", "running", "failed", "cancelled"])
@pytest.mark.parametrize("analysis_requested", [False, True])
def test_jobs_without_report_or_completed_analysis_are_capturable(
    monkeypatch, tmp_path, state, analysis_requested
):
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    pinned_lake(lake)
    artifacts.mkdir()
    job = make_job(
        lake,
        state=state,
        analysis_requested=analysis_requested,
        key=f"{state}-{analysis_requested}",
    )
    database = FakeDatabase(jobs=[db_job(job, 7)])
    install_fake(monkeypatch, database)

    result = backup_capture.capture_manifest(
        SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
        schema="qm_research",
        lake_root=lake,
        artifact_root=artifacts,
        output_root=tmp_path / "capture",
        policy=None,
    )

    assert result["manifest"]["jobs"][0]["state"] == state
    assert result["manifest"]["jobs"][0]["analysis_state"] in {
        "not_requested",
        "pending",
        "cancelled",
    }
    assert result["manifest"]["references"] == []
    assert result["manifest"]["row_sequence_maxima"]["jobs"] == 7


def test_running_analysis_without_succeeded_backtest_or_outbox_is_rejected(monkeypatch, tmp_path):
    lake, artifacts = tmp_path / "lake", tmp_path / "artifacts"
    pinned_lake(lake)
    artifacts.mkdir()
    job = make_job(lake, state="running", analysis_requested=True)
    job = job.model_copy(update={"analysis_state": "running"})
    install_fake(monkeypatch, FakeDatabase(jobs=[db_job(job)]))

    with pytest.raises(ValueError):
        backup_capture.capture_manifest(
            SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
            schema="qm_research",
            lake_root=lake,
            artifact_root=artifacts,
            output_root=tmp_path / "capture",
            policy=None,
        )


def test_validate_manifest_refuses_tampered_manifest(tmp_path):
    root = tmp_path / "capture"
    root.mkdir(mode=0o700)
    artifacts = root / "artifacts"
    artifacts.mkdir(mode=0o700)
    manifest = {"manifest_version": 1, "schema": "qm_research", "references": []}
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    (root / "manifest.json").write_bytes(raw)
    (root / "manifest.json").chmod(0o600)
    expected = hashlib.sha256(raw).hexdigest()
    assert backup_capture.validate_manifest(root, expected) == manifest

    (root / "manifest.json").write_text('{"version":2}', encoding="utf-8")
    with pytest.raises(ValueError):
        backup_capture.validate_manifest(root, expected)


@pytest.mark.skipif(os.name == "nt", reason="POSIX file identity and ownership")
def test_private_capture_root_rejects_symlink(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError):
        backup_capture.validate_manifest(alias, "0" * 64)


def _bundle_setup(monkeypatch, tmp_path, body):
    monkeypatch.setattr(backup_capture, "subprocess", subprocess, raising=False)
    lake = tmp_path / "lake"
    artifacts = tmp_path / "artifacts"
    output_parent = tmp_path / "output-parent"
    prefix = tmp_path / "prefix"
    tool_bin = prefix / "bin"
    tool_lib = prefix / "lib"
    pinned_lake(lake)
    artifacts.mkdir(mode=0o700)
    output_parent.mkdir(mode=0o700)
    tool_bin.mkdir(parents=True)
    tool_lib.mkdir()
    tool = tool_bin / "pg_dump"
    tool.write_text(f"#!{sys.executable}\n{body}\n", encoding="utf-8")
    tool.chmod(0o700)
    digest = hashlib.sha256(tool.read_bytes()).hexdigest()
    monkeypatch.setattr(backup_capture, "_PG_DUMP_SHA256", digest, raising=False)
    database = FakeDatabase()
    calls = install_fake(monkeypatch, database)
    return lake, artifacts, output_parent / "bundle", tool, database, calls


def _bundle_capture(lake, artifacts, output, tool):
    return backup_capture.capture_backup_bundle(
        SecretStr("postgresql://fixture:fixture@127.0.0.1/fixture?sslmode=disable"),
        schema="qm_research",
        lake_root=lake,
        artifact_root=artifacts,
        output_root=output,
        pg_dump_path=tool,
        policy=None,
    )


def _fake_dump_body(payload=b"PGDMP-fixture", *, stderr_token=False):
    return "\n".join(
        (
            "import os, sys",
            f"os.write(1, {payload!r})",
            "if '--snapshot' not in sys.argv: raise SystemExit(41)",
            "if '--file=-' not in sys.argv: raise SystemExit(45)",
            "if '--dbname=service=quantmesh_bundle' not in sys.argv: raise SystemExit(42)",
            "service_file = os.environ.get('PGSERVICEFILE', '')",
            "if not service_file.startswith('/proc/self/fd/'): raise SystemExit(43)",
            "if os.environ.get('PGPASSWORD'): raise SystemExit(44)",
            "if any('postgresql://' in a for a in sys.argv): raise SystemExit(44)",
            "if "
            + repr(stderr_token)
            + ": os.write(2, sys.argv[sys.argv.index('--snapshot') + 1].encode())",
        )
    )


@pytest.mark.skipif(not os.environ.get("QM_LIBPQ_LIBRARY"), reason="audited libpq parser witness")
def test_service_file_bytes_round_trip_through_libpq_parser(monkeypatch, tmp_path):
    library_path = Path(os.environ["QM_LIBPQ_LIBRARY"]).resolve(strict=True)
    assert hashlib.sha256(library_path.read_bytes()).hexdigest() == (
        "755ba5cf7cf85ef3e2be4c8ef4fe7d00f2693f0398baeb38e525a81833ebb64f"
    )
    library = ctypes.CDLL(str(library_path))

    class ConninfoOption(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_char_p)
            for name in ("keyword", "envvar", "compiled", "val", "label", "dispchar")
        ] + [("dispsize", ctypes.c_int)]

    library.PQconndefaults.argtypes = []
    library.PQconndefaults.restype = ctypes.POINTER(ConninfoOption)
    library.PQconninfoFree.argtypes = [ctypes.POINTER(ConninfoOption)]
    library.PQlibVersion.argtypes = []
    library.PQlibVersion.restype = ctypes.c_int
    assert library.PQlibVersion() == 180006
    values = {
        "host": "127.0.0.1",
        "port": "55443",
        "user": "bundle-user",
        "password": "p'ass\\word=#x=y",
        "dbname": "bundle-db",
        "sslmode": "disable",
    }
    service_file = tmp_path / "pg_service.conf"
    service_file.write_bytes(backup_capture._service_file_bytes(values))
    service_file.chmod(0o600)
    monkeypatch.setenv("PGSERVICE", "quantmesh_bundle")
    monkeypatch.setenv("PGSERVICEFILE", str(service_file))
    for key in ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE", "PGSSLMODE"):
        monkeypatch.delenv(key, raising=False)

    options = library.PQconndefaults()
    assert options
    try:
        parsed = {}
        index = 0
        while options[index].keyword:
            key = options[index].keyword.decode("ascii")
            if key in values:
                parsed[key] = options[index].val
            index += 1
    finally:
        library.PQconninfoFree(options)

    assert parsed == {key: value.encode("utf-8") for key, value in values.items()}


@pytest.mark.parametrize(
    "value",
    ["trailing-space ", "trailing-tab\t", "line\nbreak", "line\rcarriage", "x" * 1020],
)
def test_service_file_bytes_refuses_values_that_libpq_cannot_preserve(value):
    with pytest.raises(ValueError, match="research snapshot manifest refused"):
        backup_capture._service_file_bytes(
            {
                "host": "localhost",
                "port": "5432",
                "user": "fixture",
                "password": value,
                "dbname": "fixture",
                "sslmode": "verify-full",
            }
        )


@pytest.mark.skipif(os.name == "nt", reason="Linux descriptor-backed executable admission")
def test_capture_backup_bundle_refuses_unrepresentable_service_value_before_connect(
    monkeypatch, tmp_path
):
    lake, artifacts, output, tool, _, _ = _bundle_setup(monkeypatch, tmp_path, _fake_dump_body())
    connects = []
    monkeypatch.setattr(backup_capture, "connect", lambda dsn: connects.append(dsn))
    dsn = SecretStr("postgresql://fixture:trailing%20@127.0.0.1/fixture?sslmode=disable")

    with pytest.raises(ValueError, match="research snapshot manifest refused"):
        backup_capture.capture_backup_bundle(
            dsn,
            schema="qm_research",
            lake_root=lake,
            artifact_root=artifacts,
            output_root=output,
            pg_dump_path=tool,
            policy=None,
        )

    assert connects == []
    assert not output.exists()


@pytest.mark.skipif(os.name == "nt", reason="Linux descriptor-backed executable admission")
def test_capture_backup_bundle_runs_pg_dump_before_exporter_close_and_hides_token(
    monkeypatch, tmp_path
):
    lake, artifacts, output, tool, database, calls = _bundle_setup(
        monkeypatch, tmp_path, _fake_dump_body(stderr_token=True)
    )
    real_popen = backup_capture.subprocess.Popen
    child_events = []

    def checked_popen(*args, **kwargs):
        assert not database.rolled_back and not database.closed
        assert any("select pg_export_snapshot()" in sql.lower() for sql, _ in database.statements)
        argv = kwargs.get("args", args[0] if args else None)
        assert database.snapshot in argv
        child_events.append("spawned_while_exporter_open")
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(backup_capture.subprocess, "Popen", checked_popen)
    result = _bundle_capture(lake, artifacts, output, tool)

    assert len(calls) == 1
    assert child_events == ["spawned_while_exporter_open"]
    assert database.events == ["rollback", "close"]
    assert result["snapshot_closed"] is True
    assert result["manifest_only"] is False
    assert database.snapshot not in json.dumps(result)
    assert database.snapshot.encode() not in b"".join(
        path.read_bytes() for path in output.rglob("*") if path.is_file()
    )
    assert backup_capture.validate_backup_bundle(output, result["bundle_sha256"])
    assert {path.name for path in output.iterdir()} == {
        "capture",
        "research.dump",
        "bundle.json",
    }
    assert not list(output.rglob("pg-service.conf"))


@pytest.mark.skipif(os.name == "nt", reason="Linux descriptor-backed executable admission")
def test_capture_backup_bundle_refuses_unpinned_tool_before_connect(monkeypatch, tmp_path):
    lake = tmp_path / "lake"
    artifacts = tmp_path / "artifacts"
    output_parent = tmp_path / "output-parent"
    pinned_lake(lake)
    artifacts.mkdir(mode=0o700)
    output_parent.mkdir(mode=0o700)
    tool_bin = tmp_path / "prefix" / "bin"
    (tmp_path / "prefix" / "lib").mkdir(parents=True)
    tool_bin.mkdir()
    tool = tool_bin / "pg_dump"
    tool.write_text(f"#!{sys.executable}\nraise SystemExit(0)\n", encoding="utf-8")
    tool.chmod(0o700)
    calls = []
    monkeypatch.setattr(backup_capture, "connect", lambda dsn: calls.append(dsn))

    with pytest.raises(ValueError):
        _bundle_capture(lake, artifacts, output_parent / "bundle", tool)

    assert calls == []
    assert not (output_parent / "bundle").exists()


@pytest.mark.skipif(os.name == "nt", reason="Linux descriptor-backed executable admission")
def test_capture_backup_bundle_executes_opened_inode_after_tool_path_replacement(
    monkeypatch, tmp_path
):
    lake, artifacts, output, tool, database, _ = _bundle_setup(
        monkeypatch, tmp_path, _fake_dump_body(payload=b"opened-inode")
    )
    original_popen = backup_capture.subprocess.Popen
    moved = tmp_path / "opened-pg-dump"

    def replace_path_then_spawn(*args, **kwargs):
        os.replace(tool, moved)
        tool.write_text(f"#!{sys.executable}\nraise SystemExit(99)\n", encoding="utf-8")
        tool.chmod(0o700)
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(backup_capture.subprocess, "Popen", replace_path_then_spawn)
    result = _bundle_capture(lake, artifacts, output, tool)

    assert result["dump_sha256"] == hashlib.sha256(b"opened-inode").hexdigest()
    assert database.closed and database.rolled_back


@pytest.mark.skipif(os.name == "nt", reason="Linux descriptor-backed executable admission")
def test_capture_backup_bundle_preserves_replaced_service_file_on_failure(monkeypatch, tmp_path):
    lake, artifacts, output, tool, database, _ = _bundle_setup(
        monkeypatch, tmp_path, _fake_dump_body(payload=b"opened-inode")
    )
    original_runner = backup_capture._run_pg_dump

    def replace_service_file(*args, **kwargs):
        result = original_runner(*args, **kwargs)
        service_path = output / "pg-service.conf"
        service_path.unlink()
        service_path.write_bytes(b"replacement-must-survive")
        service_path.chmod(0o600)
        return result

    monkeypatch.setattr(backup_capture, "_run_pg_dump", replace_service_file)
    with pytest.raises(ValueError, match="research snapshot manifest refused"):
        _bundle_capture(lake, artifacts, output, tool)

    assert database.events == ["rollback", "close"]
    assert (output / "pg-service.conf").read_bytes() == b"replacement-must-survive"


@pytest.mark.skipif(os.name == "nt", reason="Linux descriptor-backed executable admission")
def test_capture_backup_bundle_timeout_reaps_child_and_closes_database(monkeypatch, tmp_path):
    marker = tmp_path / "child.pid"
    body = (
        "import os, sys, time\n"
        f"open({str(marker)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(20)\n"
    )
    lake, artifacts, output, tool, database, _ = _bundle_setup(monkeypatch, tmp_path, body)
    monkeypatch.setattr(backup_capture, "_PG_DUMP_TIMEOUT_SECONDS", 0.2, raising=False)

    with pytest.raises(ValueError, match="research snapshot manifest refused"):
        _bundle_capture(lake, artifacts, output, tool)

    assert database.events == ["rollback", "close"]
    assert not output.exists()
    if marker.exists():
        pid = int(marker.read_text())
        assert not os.path.exists(f"/proc/{pid}")


@pytest.mark.skipif(os.name == "nt", reason="Linux descriptor-backed executable admission")
def test_capture_backup_bundle_child_failure_is_redacted_and_closes_resources(
    monkeypatch, tmp_path
):
    body = (
        "import os, sys\n"
        "os.write(2, sys.argv[sys.argv.index('--snapshot') + 1].encode())\n"
        "raise SystemExit(9)\n"
    )
    lake, artifacts, output, tool, database, _ = _bundle_setup(monkeypatch, tmp_path, body)

    with pytest.raises(ValueError, match="research snapshot manifest refused") as refused:
        _bundle_capture(lake, artifacts, output, tool)

    assert database.events == ["rollback", "close"]
    assert database.snapshot not in str(refused.value)
    assert not output.exists()


@pytest.mark.skipif(os.name == "nt", reason="Linux descriptor-backed executable admission")
@pytest.mark.parametrize("limit_kind", ["output", "dump"])
def test_capture_backup_bundle_enforces_child_byte_limits(monkeypatch, tmp_path, limit_kind):
    if limit_kind == "output":
        body = "import os, time\nos.write(2, b'x' * 4096)\ntime.sleep(5)"
        limit_name = "_MAX_PG_DUMP_OUTPUT_BYTES"
    else:
        body = "import os, time\nos.write(1, b'x' * 4096)\ntime.sleep(5)"
        limit_name = "_MAX_PG_DUMP_BYTES"
    lake, artifacts, output, tool, database, _ = _bundle_setup(monkeypatch, tmp_path, body)
    monkeypatch.setattr(backup_capture, limit_name, 64, raising=False)

    with pytest.raises(ValueError, match="research snapshot manifest refused"):
        _bundle_capture(lake, artifacts, output, tool)

    assert database.events == ["rollback", "close"]
    assert not output.exists()


@pytest.mark.skipif(os.name == "nt", reason="Linux descriptor-backed executable admission")
def test_validate_backup_bundle_rejects_dump_artifact_and_extra_path(monkeypatch, tmp_path):
    lake, artifacts, output, tool, _, _ = _bundle_setup(monkeypatch, tmp_path, _fake_dump_body())
    result = _bundle_capture(lake, artifacts, output, tool)
    extra = output / "extra"
    extra.write_text("unexpected", encoding="utf-8")
    with pytest.raises(ValueError):
        backup_capture.validate_backup_bundle(output, result["bundle_sha256"])
    extra.unlink()

    dump = output / "research.dump"
    dump.write_bytes(b"changed dump")
    with pytest.raises(ValueError):
        backup_capture.validate_backup_bundle(output, result["bundle_sha256"])


@pytest.mark.skipif(os.name == "nt", reason="Linux descriptor-backed executable admission")
def test_validate_backup_bundle_rejects_referenced_artifact_substitution(monkeypatch, tmp_path):
    lake, artifacts, output_parent = tmp_path / "lake", tmp_path / "artifacts", tmp_path / "out"
    pinned_lake(lake)
    artifacts.mkdir(mode=0o700)
    output_parent.mkdir(mode=0o700)
    job = make_job(lake, job_id="job-report", state="succeeded")
    job, ref = with_report(job, artifacts)
    database = FakeDatabase(jobs=[db_job(job)])
    install_fake(monkeypatch, database)
    body = _fake_dump_body()
    tool_bin = tmp_path / "prefix" / "bin"
    (tmp_path / "prefix" / "lib").mkdir(parents=True)
    tool_bin.mkdir()
    tool = tool_bin / "pg_dump"
    tool.write_text(f"#!{sys.executable}\n{body}\n", encoding="utf-8")
    tool.chmod(0o700)
    monkeypatch.setattr(
        backup_capture,
        "_PG_DUMP_SHA256",
        hashlib.sha256(tool.read_bytes()).hexdigest(),
        raising=False,
    )
    output = output_parent / "bundle"

    result = _bundle_capture(lake, artifacts, output, tool)
    artifact_copy = output / "capture" / "artifacts" / ref.object_key
    artifact_copy.write_bytes(b"substituted report")

    with pytest.raises(ValueError):
        backup_capture.validate_backup_bundle(output, result["bundle_sha256"])
