"""Single-authority SQLite job storage, transactional leases and analysis outbox.

Each operation opens/closes its own connection; reopening requires no process
state. BEGIN IMMEDIATE serializes admission, claims and publication. Workers
must heartbeat every 15 seconds, and may publish only while their 60s lease
and owner/attempt fence still hold. There is no background worker in this slice.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import re
import sqlite3
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from pydantic import TypeAdapter, ValidationError

from quantmesh.research.jobs import (
    LEASE_SECONDS,
    MAX_CONCURRENT_JOBS,
    AnalysisLease,
    AnalysisRecord,
    ArtifactRef,
    ErrorCode,
    IdempotencyConflict,
    Identifier,
    JobRecord,
    ResearchJobRequest,
    StoreUnavailable,
    canonical_request_digest,
)
from quantmesh.research.strategy_registry import get_strategy, validate_dataset
from quantmesh.settings import settings


class JobStore(Protocol):
    def submit(
        self, operator_id: str, idempotency_key: str, request: ResearchJobRequest
    ) -> JobRecord: ...
    def get(self, operator_id: str, job_id: str) -> JobRecord: ...
    def claim(self, owner: str, now: datetime) -> JobRecord | None: ...
    def heartbeat(self, job_id: str, owner: str, attempt: int, now: datetime) -> bool: ...
    def request_cancel(self, operator_id: str, job_id: str) -> JobRecord: ...
    def finish(
        self,
        job_id: str,
        owner: str,
        attempt: int,
        state: str,
        artifacts: list[ArtifactRef],
        error_code: str | None,
    ) -> bool: ...
    def claim_analysis(self, owner: str, now: datetime) -> AnalysisLease | None: ...
    def heartbeat_analysis(self, lease: AnalysisLease, now: datetime) -> bool: ...
    def finish_analysis(self, lease: AnalysisLease, record: AnalysisRecord) -> bool: ...


def protocol_digest() -> str:
    """Digest names, order, annotations and defaults independently of implementation."""
    names = (
        "submit",
        "get",
        "claim",
        "heartbeat",
        "request_cancel",
        "finish",
        "claim_analysis",
        "heartbeat_analysis",
        "finish_analysis",
    )
    body = {name: str(inspect.signature(getattr(JobStore, name))) for name in names}
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _time(now: datetime) -> datetime:
    if now.utcoffset() is None:
        raise ValueError("lease clock must be timezone-aware")
    return now.astimezone(UTC)


def _identifier(value: str) -> str:
    try:
        return TypeAdapter(Identifier).validate_python(value)
    except ValidationError:
        raise ValueError("invalid identifier") from None


def _replace(record: JobRecord, **updates) -> JobRecord:
    return JobRecord.model_validate({**record.model_dump(mode="json"), **updates})


class SQLiteJobStore:
    def __init__(
        self,
        path: Path,
        *,
        lake_root: Path | None = None,
        artifact_root: Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = Path(path)
        self.lake_root = Path(lake_root) if lake_root is not None else settings.lake_root
        self.artifact_root = (
            Path(artifact_root) if artifact_root is not None else (self.path.parent / "artifacts")
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._transaction() as con:
                version = con.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise StoreUnavailable("unsupported job store schema")
                con.execute(
                    "CREATE TABLE IF NOT EXISTS jobs ("
                    "job_id TEXT PRIMARY KEY, operator_id TEXT NOT NULL, "
                    "idempotency_key TEXT NOT NULL, payload TEXT NOT NULL, "
                    "UNIQUE(operator_id, idempotency_key))"
                )
                con.execute(
                    "CREATE TABLE IF NOT EXISTS analysis_outbox ("
                    "job_id TEXT PRIMARY KEY REFERENCES jobs(job_id), "
                    "lease TEXT, attempt INTEGER NOT NULL DEFAULT 0)"
                )
                con.execute("PRAGMA user_version=1")
        except OSError:
            raise StoreUnavailable("job store unavailable") from None

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        con = None
        try:
            con = sqlite3.connect(self.path, timeout=2)
            con.execute("PRAGMA foreign_keys=ON")
            con.execute("PRAGMA synchronous=FULL")
            con.execute("BEGIN IMMEDIATE")
            yield con
            con.commit()
        except sqlite3.Error:
            if con is not None:
                con.rollback()
            raise StoreUnavailable("job store unavailable") from None
        except BaseException:
            if con is not None:
                con.rollback()
            raise
        finally:
            if con is not None:
                con.close()

    @staticmethod
    def _decode(payload: str) -> JobRecord:
        try:
            record = JobRecord.model_validate_json(payload)
            if record.request_digest != canonical_request_digest(record.request):
                raise ValueError("digest mismatch")
            return record
        except ValueError:
            raise StoreUnavailable("job record invalid") from None

    def _read(self, con, job_id: str) -> JobRecord | None:
        row = con.execute("SELECT payload FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._decode(row[0]) if row else None

    def _all(self, con) -> list[JobRecord]:
        rows = con.execute("SELECT payload FROM jobs ORDER BY rowid").fetchall()
        return [self._decode(row[0]) for row in rows]

    @staticmethod
    def _write(con, record: JobRecord) -> None:
        con.execute(
            "UPDATE jobs SET payload=? WHERE job_id=?", (record.model_dump_json(), record.job_id)
        )

    def submit(
        self, operator_id: str, idempotency_key: str, request: ResearchJobRequest
    ) -> JobRecord:
        _identifier(operator_id)
        _identifier(idempotency_key)
        digest = canonical_request_digest(request)
        request = ResearchJobRequest.model_validate(request.model_dump(mode="json"))
        now = _time(self._clock())
        with self._transaction() as con:
            row = con.execute(
                "SELECT payload FROM jobs WHERE operator_id=? AND idempotency_key=?",
                (operator_id, idempotency_key),
            ).fetchone()
            if row:
                existing = self._decode(row[0])
                if existing.request_digest != digest:
                    raise IdempotencyConflict("idempotency key has different configuration")
                return existing  # Accepted work survives later changes to the lake.
            validate_dataset(request, self.lake_root, now)
            record = JobRecord(
                job_id=uuid.uuid4().hex,
                operator_id=operator_id,
                idempotency_key=idempotency_key,
                request=request,
                request_digest=digest,
                implementation_digest=get_strategy(
                    request.strategy_id, request.strategy_version
                ).implementation_digest,
                created_at=now,
                updated_at=now,
                analysis_state="pending" if request.analysis_requested else "not_requested",
            )
            con.execute(
                "INSERT INTO jobs VALUES (?, ?, ?, ?)",
                (record.job_id, operator_id, idempotency_key, record.model_dump_json()),
            )
            return record

    def get(self, operator_id: str, job_id: str) -> JobRecord:
        with self._transaction() as con:
            record = self._read(con, job_id)
            if record is None or record.operator_id != operator_id:
                raise KeyError("job not found")
            return record

    def _busy(self, con, now: datetime) -> int:
        count = sum(r.state == "running" and r.lease_expires_at > now for r in self._all(con))
        for (payload,) in con.execute("SELECT lease FROM analysis_outbox WHERE lease IS NOT NULL"):
            lease = AnalysisLease.model_validate_json(payload)
            record = self._read(con, lease.job_id)
            count += record.analysis_state == "running" and lease.expires_at > now
        return count

    def claim(self, owner: str, now: datetime) -> JobRecord | None:
        _identifier(owner)
        now = _time(now)
        with self._transaction() as con:
            if self._busy(con, now) >= MAX_CONCURRENT_JOBS:
                return None
            for record in self._all(con):
                eligible = record.state == "queued" or (
                    record.state == "running" and record.lease_expires_at <= now
                )
                if eligible and not record.cancel_requested:
                    claimed = _replace(
                        record,
                        state="running",
                        attempt=record.attempt + 1,
                        lease_owner=owner,
                        lease_expires_at=now + timedelta(seconds=LEASE_SECONDS),
                        updated_at=now,
                    )
                    self._write(con, claimed)
                    return claimed
        return None

    @staticmethod
    def _fenced(record, owner, attempt, now) -> bool:
        return bool(
            record
            and record.state == "running"
            and not record.cancel_requested
            and record.lease_owner == owner
            and record.attempt == attempt
            and record.lease_expires_at > now
        )

    def heartbeat(self, job_id: str, owner: str, attempt: int, now: datetime) -> bool:
        now = _time(now)
        with self._transaction() as con:
            record = self._read(con, job_id)
            if not self._fenced(record, owner, attempt, now):
                return False
            self._write(
                con,
                _replace(
                    record, updated_at=now, lease_expires_at=now + timedelta(seconds=LEASE_SECONDS)
                ),
            )
            return True

    def request_cancel(self, operator_id: str, job_id: str) -> JobRecord:
        now = _time(self._clock())
        with self._transaction() as con:
            record = self._read(con, job_id)
            if record is None or record.operator_id != operator_id:
                raise KeyError("job not found")
            updates = dict(cancel_requested=True, updated_at=now)
            if record.state in ("queued", "running"):
                updates.update(
                    state="cancelled",
                    finished_at=now,
                    lease_owner=None,
                    lease_expires_at=None,
                    error_code="cancelled",
                )
            if record.analysis_state in ("pending", "running"):
                updates["analysis_state"] = "cancelled"
            cancelled = _replace(record, **updates)
            self._write(con, cancelled)
            con.execute("DELETE FROM analysis_outbox WHERE job_id=?", (job_id,))
            return cancelled

    def _artifact_bytes(self, record: JobRecord, ref: ArtifactRef) -> bytes:
        try:
            path = self.artifact_root / ref.object_key
            root = self.artifact_root.resolve()
            if root not in path.resolve().parents or any(
                p.is_symlink() for p in (path, *path.parents)
            ):
                raise ValueError("artifact path invalid")
            if not ref.object_key.startswith(record.job_id + "/"):
                raise ValueError("artifact ownership invalid")
            raw = path.read_bytes()
            if len(raw) != ref.byte_size or hashlib.sha256(raw).hexdigest() != ref.sha256:
                raise ValueError("artifact digest invalid")
            return raw
        except (OSError, ValueError):
            raise ValueError("artifact validation failed") from None

    def _artifacts(self, record: JobRecord, artifacts: list[ArtifactRef]) -> list[ArtifactRef]:
        refs = [ArtifactRef.model_validate(a.model_dump()) for a in artifacts]
        if len({a.object_key for a in refs}) != len(refs):
            raise ValueError("duplicate artifact")
        reports = [a for a in refs if a.kind == "report"]
        if len(reports) != 1:
            raise ValueError("one report artifact required")
        try:
            for ref in refs:
                raw = self._artifact_bytes(record, ref)
                if ref.kind == "report":
                    # This envelope pins every admitted input. Numerical schema belongs to Worker.
                    envelope = json.loads(raw)
                    if envelope.get("request_digest") != record.request_digest:
                        raise ValueError("artifact lineage invalid")
        except (OSError, ValueError, AttributeError):
            raise ValueError("artifact validation failed") from None
        return refs

    def finish(
        self,
        job_id: str,
        owner: str,
        attempt: int,
        state: str,
        artifacts: list[ArtifactRef],
        error_code: str | None,
    ) -> bool:
        now = _time(self._clock())
        with self._transaction() as con:
            record = self._read(con, job_id)
            if not self._fenced(record, owner, attempt, now):
                return False
            if state not in ("succeeded", "failed", "cancelled"):
                raise ValueError("invalid terminal state")
            try:
                TypeAdapter(ErrorCode | None).validate_python(error_code)
            except ValueError:
                raise ValueError("invalid error code") from None
            if state == "succeeded" and error_code is not None:
                raise ValueError("successful job cannot have an error")
            if state != "succeeded" and (artifacts or error_code is None):
                raise ValueError("failed/cancelled job requires error code and no artifacts")
            refs = self._artifacts(record, artifacts) if state == "succeeded" else []
            analysis_state = record.analysis_state
            if record.request.analysis_requested:
                analysis_state = "pending" if state == "succeeded" else "cancelled"
            result = _replace(
                record,
                state=state,
                artifacts=refs,
                error_code=error_code,
                lease_owner=None,
                lease_expires_at=None,
                updated_at=now,
                finished_at=now,
                cancel_requested=state == "cancelled",
                analysis_state=analysis_state,
            )
            self._write(con, result)
            if state == "succeeded" and record.request.analysis_requested:
                con.execute("INSERT INTO analysis_outbox(job_id) VALUES (?)", (job_id,))
            return True

    def claim_analysis(self, owner: str, now: datetime) -> AnalysisLease | None:
        _identifier(owner)
        now = _time(now)
        with self._transaction() as con:
            if self._busy(con, now) >= MAX_CONCURRENT_JOBS:
                return None
            for job_id, payload, attempt in con.execute(
                "SELECT job_id, lease, attempt FROM analysis_outbox ORDER BY rowid"
            ).fetchall():
                record = self._read(con, job_id)
                old = AnalysisLease.model_validate_json(payload) if payload else None
                if (
                    record.state != "succeeded"
                    or record.cancel_requested
                    or record.analysis_state not in ("pending", "running")
                    or (old and old.expires_at > now)
                ):
                    continue
                report = next(a for a in record.artifacts if a.kind == "report")
                lease = AnalysisLease(
                    job_id=job_id,
                    owner=owner,
                    attempt=attempt + 1,
                    expires_at=now + timedelta(seconds=LEASE_SECONDS),
                    report_digest=report.sha256,
                )
                con.execute(
                    "UPDATE analysis_outbox SET lease=?, attempt=? WHERE job_id=?",
                    (lease.model_dump_json(), lease.attempt, job_id),
                )
                self._write(con, _replace(record, analysis_state="running", updated_at=now))
                return lease
        return None

    def _analysis_fenced(self, con, lease, now):
        row = con.execute(
            "SELECT lease FROM analysis_outbox WHERE job_id=?", (lease.job_id,)
        ).fetchone()
        if not row or row[0] is None:
            return None
        stored = AnalysisLease.model_validate_json(row[0])
        record = self._read(con, lease.job_id)
        # Heartbeats extend stored expiry; caller may still hold the original token.
        if (
            stored.owner != lease.owner
            or stored.attempt != lease.attempt
            or stored.report_digest != lease.report_digest
            or stored.expires_at <= now
            or record.state != "succeeded"
            or record.cancel_requested
            or record.analysis_state != "running"
        ):
            return None
        return record

    def heartbeat_analysis(self, lease: AnalysisLease, now: datetime) -> bool:
        now = _time(now)
        with self._transaction() as con:
            record = self._analysis_fenced(con, lease, now)
            if record is None:
                return False
            renewed = AnalysisLease.model_validate(
                {**lease.model_dump(), "expires_at": now + timedelta(seconds=LEASE_SECONDS)}
            )
            con.execute(
                "UPDATE analysis_outbox SET lease=? WHERE job_id=?",
                (renewed.model_dump_json(), lease.job_id),
            )
            self._write(con, _replace(record, updated_at=now))
            return True

    def finish_analysis(self, lease: AnalysisLease, record: AnalysisRecord) -> bool:
        now = _time(self._clock())
        with self._transaction() as con:
            job = self._analysis_fenced(con, lease, now)
            if job is None:
                return False
            record = AnalysisRecord.model_validate(record.model_dump(mode="json"))
            if record.job_id != job.job_id or record.report_digest != lease.report_digest:
                raise ValueError("analysis lineage invalid")
            for citation in record.citations:
                if citation not in job.artifacts:
                    raise ValueError("analysis citation is not published evidence")
                self._artifact_bytes(job, citation)
            if record.output_artifact is not None:
                raw = self._artifact_bytes(job, record.output_artifact)
                if record.state == "succeeded":
                    try:
                        output = json.loads(raw)
                        if not isinstance(output, dict):
                            raise ValueError("analysis output must be an object")
                        expected = {
                            "job_id": job.job_id,
                            "report_digest": lease.report_digest,
                            "request_digest": job.request_digest,
                            "implementation_digest": job.implementation_digest,
                        }
                        if any(
                            key in output and output[key] != value
                            for key, value in expected.items()
                        ):
                            raise ValueError("analysis output lineage invalid")
                    except (ValueError, UnicodeDecodeError):
                        raise ValueError("analysis output envelope invalid") from None
            self._write(
                con, _replace(job, analysis_state=record.state, analysis=record, updated_at=now)
            )
            con.execute("DELETE FROM analysis_outbox WHERE job_id=?", (job.job_id,))
            return True


class _PostgresConnection:
    """Small SQL compatibility layer for the shared, validated store operations."""

    def __init__(self, connection, schema: str) -> None:
        self.connection = connection
        self.schema = schema

    def execute(self, statement: str, parameters=()):
        statement = re.sub(r"\bjobs\b", f'"{self.schema}".jobs', statement)
        statement = re.sub(r"\banalysis_outbox\b", f'"{self.schema}".analysis_outbox', statement)
        statement = re.sub(r"\browid\b", "queue_position", statement)
        if statement.startswith(f'INSERT INTO "{self.schema}".jobs VALUES'):
            statement = statement.replace(
                f'INSERT INTO "{self.schema}".jobs VALUES',
                f'INSERT INTO "{self.schema}".jobs '
                "(job_id, operator_id, idempotency_key, payload) VALUES",
                1,
            )
        return self.connection.execute(statement.replace("?", "%s"), parameters)


class PostgresJobStore(SQLiteJobStore):
    """PostgreSQL-backed durable job store implementing the existing contract."""

    _SCHEMA_VERSION = 1
    _LOCK_ID = 0x514D4A4F425354

    def __init__(
        self,
        dsn: str,
        *,
        schema: str = "quantmesh",
        lake_root: Path | None = None,
        artifact_root: Path | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(schema, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", schema):
            raise ValueError("invalid PostgreSQL schema")
        try:
            import psycopg
        except ImportError:
            raise StoreUnavailable("PostgreSQL driver unavailable") from None

        self.dsn = dsn
        self.schema = schema
        self.lake_root = Path(lake_root) if lake_root is not None else settings.lake_root
        self.artifact_root = (
            Path(artifact_root) if artifact_root is not None else (self.lake_root / "artifacts")
        )
        self._clock = clock or (lambda: datetime.now(UTC))
        self._psycopg = psycopg
        try:
            with psycopg.connect(dsn) as con:
                con.execute("SELECT pg_advisory_xact_lock(%s)", (self._LOCK_ID,))
                con.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
                con.execute(
                    f'CREATE TABLE IF NOT EXISTS "{schema}".job_store_schema '
                    "(singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton), "
                    "version INTEGER NOT NULL)"
                )
                con.execute(
                    f'INSERT INTO "{schema}".job_store_schema(singleton, version) '
                    "VALUES (TRUE, %s) ON CONFLICT (singleton) DO NOTHING",
                    (self._SCHEMA_VERSION,),
                )
                row = con.execute(
                    f'SELECT version FROM "{schema}".job_store_schema WHERE singleton=TRUE'
                ).fetchone()
                if row is None or row[0] != self._SCHEMA_VERSION:
                    raise StoreUnavailable("unsupported job store schema")
                con.execute(
                    f'CREATE TABLE IF NOT EXISTS "{schema}".jobs ('
                    "queue_position BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE, "
                    "job_id TEXT PRIMARY KEY, operator_id TEXT NOT NULL, "
                    "idempotency_key TEXT NOT NULL, payload TEXT NOT NULL, "
                    "UNIQUE(operator_id, idempotency_key))"
                )
                con.execute(
                    f'CREATE TABLE IF NOT EXISTS "{schema}".analysis_outbox ('
                    "job_id TEXT PRIMARY KEY REFERENCES "
                    f'"{schema}".jobs(job_id) ON DELETE CASCADE, '
                    "lease TEXT, attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0))"
                )
        except StoreUnavailable:
            raise
        except psycopg.Error:
            raise StoreUnavailable("job store unavailable") from None

    @contextmanager
    def _transaction(self):
        con = None
        try:
            con = self._psycopg.connect(self.dsn)
            con.execute("SELECT pg_advisory_xact_lock(%s)", (self._LOCK_ID,))
            yield _PostgresConnection(con, self.schema)
            con.commit()
        except self._psycopg.Error:
            if con is not None:
                con.rollback()
            raise StoreUnavailable("job store unavailable") from None
        except BaseException:
            if con is not None:
                con.rollback()
            raise
        finally:
            if con is not None:
                con.close()
