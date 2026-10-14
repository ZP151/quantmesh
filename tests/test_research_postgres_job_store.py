"""Explicitly gated integration checks for durable PostgreSQL job storage."""

import hashlib
import importlib.util
import inspect
import json
import os
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from test_research_jobs import request_for

from quantmesh.research.job_store import JobStore, protocol_digest
from quantmesh.research.jobs import ArtifactRef, IdempotencyConflict
from tests.research_fixtures import pinned_lake

POSTGRES_URL = os.environ.get("QUANTMESH_TEST_POSTGRES_URL")


def test_postgres_backend_preserves_job_store_protocol():
    from quantmesh.research.job_store import PostgresJobStore

    assert protocol_digest()
    methods = (
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
    assert all(callable(getattr(PostgresJobStore, name)) for name in methods)
    assert all(hasattr(JobStore, name) for name in methods)
    assert all(
        inspect.signature(getattr(PostgresJobStore, name))
        == inspect.signature(getattr(JobStore, name))
        for name in methods
    )


@pytest.mark.skipif(
    not POSTGRES_URL or importlib.util.find_spec("psycopg") is None,
    reason="set QUANTMESH_TEST_POSTGRES_URL and install psycopg to run PostgreSQL integration",
)
def test_postgres_store_migrates_v1_outbox_ordering_column(tmp_path):
    """A populated v1 database gains deterministic FIFO ordering before use."""
    from quantmesh.research.job_store import PostgresJobStore

    schema = "qm_legacy_" + re.sub("-", "", uuid.uuid4().hex)
    import psycopg

    lake = tmp_path / "lake"
    pinned_lake(lake)
    artifact_root = tmp_path / "artifacts"
    now = datetime.now(UTC)
    try:
        with psycopg.connect(POSTGRES_URL) as connection:
            connection.execute(f'CREATE SCHEMA "{schema}"')
        store = PostgresJobStore(
            POSTGRES_URL, schema=schema, lake_root=lake, artifact_root=artifact_root
        )
        jobs = []
        for index in range(2):
            store._clock = lambda: now
            job = store.submit(
                "local",
                f"legacy-{index}",
                request_for(lake, analysis_requested=True),
            )
            claimed = store.claim(f"worker-{index}", now)
            assert claimed and claimed.job_id == job.job_id
            raw = json.dumps({"request_digest": job.request_digest, "fixture": True}).encode()
            digest = hashlib.sha256(raw).hexdigest()
            object_key = f"{job.job_id}/{digest}.json"
            path = artifact_root / object_key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            report = ArtifactRef(
                artifact_id=digest,
                kind="report",
                schema_version=1,
                sha256=digest,
                byte_size=len(raw),
                object_key=object_key,
            )
            store._clock = lambda i=index: now + timedelta(seconds=(i + 1) * 10)
            assert store.finish(job.job_id, f"worker-{index}", 1, "succeeded", [report], None)
            jobs.append(job)

        # Reverse physical row insertion so migration must use enqueue timestamps.
        with psycopg.connect(POSTGRES_URL) as connection:
            rows = connection.execute(
                f'SELECT job_id, lease, attempt FROM "{schema}".analysis_outbox '
                "ORDER BY queue_position"
            ).fetchall()
            connection.execute(f'TRUNCATE TABLE "{schema}".analysis_outbox')
            connection.execute(
                f'ALTER TABLE "{schema}".analysis_outbox DROP COLUMN queue_position CASCADE'
            )
            connection.execute(f'ALTER TABLE "{schema}".jobs DROP COLUMN queue_position CASCADE')
            connection.execute(
                f'UPDATE "{schema}".job_store_schema SET version=1 WHERE singleton=TRUE'
            )
            for row in reversed(rows):
                connection.execute(
                    f'INSERT INTO "{schema}".analysis_outbox(job_id, lease, attempt) '
                    "VALUES (%s, %s, %s)",
                    row,
                )

        migrated = PostgresJobStore(
            POSTGRES_URL, schema=schema, lake_root=lake, artifact_root=artifact_root
        )
        lease = migrated.claim_analysis("reviewer", now + timedelta(seconds=30))
        assert lease and lease.job_id == jobs[0].job_id
        next_lease = migrated.claim_analysis("next-reviewer", now + timedelta(seconds=30))
        assert next_lease and next_lease.job_id == jobs[1].job_id
        assert migrated.claim_analysis("blocked", now + timedelta(seconds=30)) is None
        migrated._clock = lambda: now
        appended = migrated.submit("local", "legacy-after-migration", request_for(lake))
        with psycopg.connect(POSTGRES_URL) as connection:
            version = connection.execute(
                f'SELECT version FROM "{schema}".job_store_schema WHERE singleton=TRUE'
            ).fetchone()[0]
            for table in ("jobs", "analysis_outbox"):
                columns = {
                    row[0]
                    for row in connection.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema=%s AND table_name=%s",
                        (schema, table),
                    )
                }
                assert "queue_position" in columns
                queue_indexes = connection.execute(
                    "SELECT indexdef FROM pg_indexes WHERE schemaname=%s AND tablename=%s "
                    "AND indexdef ILIKE '%%queue_position%%'",
                    (schema, table),
                ).fetchall()
                assert len(queue_indexes) == 1
            positions = connection.execute(
                f'SELECT job_id, queue_position FROM "{schema}".jobs WHERE job_id = ANY(%s)',
                ([job.job_id for job in jobs] + [appended.job_id],),
            ).fetchall()
            assert len({position for _, position in positions}) == 3
            assert dict(positions)[appended.job_id] > max(
                dict(positions)[job.job_id] for job in jobs
            )
            assert version == 2
    finally:
        with psycopg.connect(POSTGRES_URL) as connection:
            connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@pytest.mark.skipif(
    not POSTGRES_URL or importlib.util.find_spec("psycopg") is None,
    reason="set QUANTMESH_TEST_POSTGRES_URL and install psycopg to run PostgreSQL integration",
)
def test_postgres_store_reopens_jobs_reports_and_analysis_outbox(tmp_path):
    from quantmesh.research.job_store import PostgresJobStore

    schema = "qm_test_" + re.sub("-", "", uuid.uuid4().hex)
    import psycopg

    with psycopg.connect(POSTGRES_URL) as connection:
        connection.execute(f'CREATE SCHEMA "{schema}"')

    lake = tmp_path / "lake"
    pinned_lake(lake)
    now = datetime.now(UTC)
    artifact_root = tmp_path / "artifacts"
    try:
        store = PostgresJobStore(
            POSTGRES_URL, schema=schema, lake_root=lake, artifact_root=artifact_root
        )
        request = request_for(lake, analysis_requested=True)
        job = store.submit("local", "postgres-key", request)
        assert store.submit("local", "postgres-key", request).job_id == job.job_id
        with pytest.raises(IdempotencyConflict):
            store.submit("local", "postgres-key", request_for(lake))

        first = store.claim("worker-a", now)
        assert first and first.attempt == 1
        assert store.heartbeat(job.job_id, "wrong-worker", 1, now) is False

        raw = json.dumps({"request_digest": job.request_digest, "fixture": True}).encode()
        digest = hashlib.sha256(raw).hexdigest()
        object_key = f"{job.job_id}/{digest}.json"
        path = artifact_root / object_key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        report = ArtifactRef(
            artifact_id=digest,
            kind="report",
            schema_version=1,
            sha256=digest,
            byte_size=len(raw),
            object_key=object_key,
        )
        assert store.finish(job.job_id, "worker-a", 1, "succeeded", [report], None)

        # A new store instance models process restart. Job JSON, published report
        # references, and the pending analysis outbox must all remain recoverable.
        reopened = PostgresJobStore(
            POSTGRES_URL, schema=schema, lake_root=lake, artifact_root=artifact_root
        )
        saved = reopened.get("local", job.job_id)
        assert saved.state == "succeeded"
        assert saved.artifacts == [report]
        lease = reopened.claim_analysis("analyst", now)
        assert lease and lease.job_id == job.job_id
        assert lease.report_digest == report.sha256
        assert reopened.claim_analysis("other", now) is None
        assert reopened.heartbeat_analysis(lease, now)
        assert reopened.heartbeat_analysis(lease, now + timedelta(seconds=61)) is False
        recovered = reopened.claim_analysis("analyst-recovery", now + timedelta(seconds=61))
        assert recovered and recovered.job_id == job.job_id
        assert recovered.attempt == lease.attempt + 1
        assert reopened.heartbeat_analysis(lease, now + timedelta(seconds=62)) is False
        with psycopg.connect(POSTGRES_URL) as connection:
            for table in ("jobs", "analysis_outbox"):
                queue_indexes = connection.execute(
                    "SELECT indexdef FROM pg_indexes WHERE schemaname=%s AND tablename=%s "
                    "AND indexdef ILIKE '%%queue_position%%'",
                    (schema, table),
                ).fetchall()
                assert len(queue_indexes) == 1
    finally:
        with psycopg.connect(POSTGRES_URL) as connection:
            connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
