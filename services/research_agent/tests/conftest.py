"""Offline fixtures are explicitly local; PostgreSQL tests use an opt-in owned DB."""

import hashlib
import json
from datetime import UTC, datetime

import pytest
from test_research_jobs import request_for

from quantmesh.research.job_store import SQLiteJobStore
from quantmesh.research.jobs import ArtifactRef
from tests.research_fixtures import pinned_lake


@pytest.fixture
def local(tmp_path):
    lake = tmp_path / "lake"
    pinned_lake(lake)
    clock = [datetime.now(UTC)]
    store = SQLiteJobStore(tmp_path / "local.sqlite", lake_root=lake, clock=lambda: clock[0])
    return store, lake, clock


def publish(store, job):
    raw = json.dumps(
        {
            "schema_version": 1,
            "request_digest": job.request_digest,
            "implementation_digest": job.implementation_digest,
            "result": {"fixture": True, "metrics": {"return": 0.1}},
        }
    ).encode()
    digest = hashlib.sha256(raw).hexdigest()
    ref = ArtifactRef(
        artifact_id=digest,
        kind="report",
        sha256=digest,
        byte_size=len(raw),
        object_key=f"{job.job_id}/{digest}.json",
    )
    path = store.artifact_root / ref.object_key
    path.parent.mkdir(parents=True)
    path.write_bytes(raw)
    worker = store.claim("worker", store._clock())
    assert worker.job_id == job.job_id
    assert store.finish(job.job_id, "worker", worker.attempt, "succeeded", [ref], None)
    return ref


def succeeded(store, lake):
    job = store.submit("operator", "first", request_for(lake, analysis_requested=True))
    ref = publish(store, job)
    return store.get("operator", job.job_id), ref
