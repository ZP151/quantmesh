"""Real PostgreSQL only: opt in to a new schema on an explicitly disposable DB."""

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from conftest import publish, scripted_effects
from pydantic import SecretStr
from qm_research_agent.store import PostgresJobStore, connect
from test_research_jobs import request_for

from quantmesh.research.jobs import AnalysisRecord, IdempotencyConflict, RunBudget
from tests.research_fixtures import pinned_lake


@pytest.fixture
def pg(tmp_path):
    # Never auto-detect/read existing credentials or use a production schema.
    dsn = os.environ.get("QM_TEST_DISPOSABLE_POSTGRES_DSN")
    if not dsn or os.environ.get("QM_TEST_DISPOSABLE_POSTGRES_ACK") != "owned-disposable":
        pytest.skip("real owned disposable PostgreSQL fixture pending")
    schema = "qm_test_" + uuid.uuid4().hex
    lake = tmp_path / "lake"
    pinned_lake(lake)
    clock = [datetime.now(UTC)]

    def factory():
        return PostgresJobStore(
            SecretStr(dsn),
            schema=schema,
            lake_root=lake,
            artifact_root=tmp_path / "artifacts",
            clock=lambda: clock[0],
        )

    store = factory()
    try:
        yield store, lake, clock, factory
    finally:
        con = connect(SecretStr(dsn))
        try:
            con.cursor().execute(f'DROP SCHEMA "{schema}" CASCADE')
            con.commit()
        finally:
            con.close()


def test_postgres_concurrency_fencing_reopen_recovery(pg):
    store, lake, clock, factory = pg
    req = request_for(lake, analysis_requested=True)
    with ThreadPoolExecutor(2) as pool:
        jobs = list(pool.map(lambda _: factory().submit("operator", "key", req), range(2)))
    assert jobs[0] == jobs[1]
    job = jobs[0]
    with pytest.raises(IdempotencyConflict):
        store.submit("operator", "key", request_for(lake))
    with ThreadPoolExecutor(2) as pool:
        claims = list(pool.map(lambda owner: factory().claim(owner, clock[0]), ["one", "two"]))
    assert sum(c is not None for c in claims) == 1
    first = next(c for c in claims if c)
    clock[0] += timedelta(seconds=61)
    second = factory().claim("new", clock[0])
    assert second.attempt == 2
    assert not store.finish(job.job_id, first.lease_owner, 1, "failed", [], "worker_failed")
    assert store.finish(job.job_id, "new", 2, "failed", [], "worker_failed")
    assert factory().get("operator", job.job_id).state == "failed"


def test_postgres_controlled_stop_handoff_reopens_with_same_job(pg):
    store, lake, clock, factory = pg
    job = store.submit("operator", "controlled-stop", request_for(lake))
    first = store.claim("one", clock[0])
    clock[0] += timedelta(seconds=1)
    assert not factory()._expire_owned_lease(job.job_id, "other", 1, clock[0])
    assert factory().get("operator", job.job_id) == first
    assert factory()._expire_owned_lease(job.job_id, "one", 1, clock[0])
    expired = factory().get("operator", job.job_id)
    assert expired.model_dump() == {**first.model_dump(), "lease_expires_at": clock[0]}
    second = factory().claim("two", clock[0])
    assert second.job_id == job.job_id and second.attempt == 2
    assert not store._expire_owned_lease(job.job_id, "one", 1, clock[0])
    assert factory().get("operator", job.job_id) == second


def test_postgres_shared_slots_cancellation_and_analysis(pg):
    store, lake, clock, factory = pg
    one = store.submit("operator", "one", request_for(lake, analysis_requested=True))
    ref = publish(store, one)
    lease = factory().claim_analysis("analyst", clock[0])
    assert lease.report_digest == ref.sha256
    store.submit("operator", "two", request_for(lake))
    store.submit("operator", "three", request_for(lake))
    two = factory().claim("worker", clock[0])
    assert store.claim("other", clock[0]) is None
    cancelled = store.request_cancel("operator", one.job_id)
    assert cancelled.state == "succeeded" and cancelled.analysis_state == "cancelled"
    record = AnalysisRecord(
        job_id=one.job_id,
        report_digest=ref.sha256,
        state="unavailable",
        verdict="unavailable",
        error_code="model_unavailable",
    )
    assert not store.finish_analysis(lease, record)
    assert store.claim("other", clock[0]) is not None
    assert not store.heartbeat(two.job_id, "wrong", two.attempt, clock[0])


def test_postgres_concurrent_reservations_cannot_exceed_allowance(pg):
    store, lake, clock, factory = pg
    job = store.submit("operator", "one", request_for(lake, analysis_requested=True))
    publish(store, job)
    lease = store.claim_analysis("analyst", clock[0])

    def reserve(i):
        return scripted_effects(factory()).reserve_call(
            job.job_id, f"{i:064x}", Decimal("0.6"), RunBudget(), lease
        )

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(reserve, [1, 2])) == [False, True]


def test_postgres_manifest_and_artifact_actual_bytes(pg):
    store, lake, _, factory = pg
    request = request_for(lake)
    manifest = lake / "equities" / "manifest.json"
    manifest.write_bytes(manifest.read_bytes() + b" ")
    with pytest.raises(ValueError):
        store.submit("operator", "bad", request)
    job = store.submit("operator", "one", request_for(lake))
    ref = publish(store, job)
    (store.artifact_root / ref.object_key).write_bytes(b"tampered")
    with pytest.raises(ValueError):
        factory()._artifact_bytes(job, ref)


def test_postgres_transaction_rollback_and_unknown_version(pg):
    store, _, _, factory = pg
    with pytest.raises(RuntimeError), store._transaction() as con:
        con.execute("UPDATE qm_schema SET version=999")
        raise RuntimeError("fixture rollback")
    assert factory()
    with store._transaction() as con:
        con.execute("UPDATE qm_schema SET version=999")
    with pytest.raises(ValueError):
        factory()
