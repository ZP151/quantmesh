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
    finally:
        with psycopg.connect(POSTGRES_URL) as connection:
            connection.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
