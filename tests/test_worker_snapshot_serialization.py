"""Real POSIX snapshot concurrency; inert child seam is not OCI qualification."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event, Lock, current_thread

import pytest
from test_research_jobs import request_for

from quantmesh.research import fixture_snapshot, job_runner
from quantmesh.research.job_store import SQLiteJobStore
from tests.research_fixtures import pinned_lake


class PreparationComplete(Exception):
    pass


@pytest.fixture
def prepared(tmp_path):
    from quantmesh.research._fixture_handles import (
        UnsupportedSnapshotProfile,
        require_snapshot_profile,
    )

    try:
        require_snapshot_profile()
    except UnsupportedSnapshotProfile:
        pytest.skip("requires actual POSIX no-follow snapshot I/O")
    lake = tmp_path / "lake"
    pinned_lake(lake)
    # SQLite journal creation must not be another writer of snapshot ancestors.
    # Production's diagnosed pair uses PostgreSQL, whose claim has no such writes.
    store = SQLiteJobStore(
        tmp_path / "state/jobs.sqlite", lake_root=lake, artifact_root=tmp_path / "artifacts"
    )
    jobs = [store.submit("local", str(i), request_for(lake)) for i in range(2)]
    return store, lake, jobs


def test_sibling_attempt_creation_waits_for_snapshot_and_children_can_overlap(
    prepared, monkeypatch
):
    store, lake, jobs = prepared
    first_copy, second_claim, second_mkdir, release = Event(), Event(), Event(), Event()
    starts = Barrier(2)
    snapshots = []
    real_stream, real_mkdir, real_claim = (
        fixture_snapshot._Copy.stream,
        Path.mkdir,
        store.claim,
    )

    def stream(copy, *args, **kwargs):
        result = real_stream(copy, *args, **kwargs)
        if (
            current_thread().name.endswith("_0")
            and kwargs.get("target")
            and not first_copy.is_set()
        ):
            first_copy.set()
            assert release.wait(5)
        return result

    def mkdir(path, *args, **kwargs):
        result = real_mkdir(path, *args, **kwargs)
        if path == store.artifact_root / jobs[1].job_id:
            second_mkdir.set()
        return result

    def claim(owner, now):
        job = real_claim(owner, now)
        if owner == "second":
            second_claim.set()
        return job

    class Execution:
        def runtime_fingerprint(self):
            return {}

        def start(self, job, runtime, bundle, output):
            snapshots.append((job.job_id, (bundle / "inputs/equities/manifest.json").read_bytes()))
            starts.wait(5)
            raise PreparationComplete

    def run(owner):
        token = job_runner._execution.set(Execution())
        try:
            return job_runner.run_next_job(store, owner, lake, store.artifact_root)
        finally:
            job_runner._execution.reset(token)

    monkeypatch.setattr(fixture_snapshot._Copy, "stream", stream)
    monkeypatch.setattr(Path, "mkdir", mkdir)
    monkeypatch.setattr(store, "claim", claim)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, "first")
        try:
            assert first_copy.wait(5)
            second = pool.submit(run, "second")
            assert second_claim.wait(5)
            mutated_during_copy = second_mkdir.wait(0.2)
        finally:
            release.set()
        outcomes = []
        for future in (first, second):
            try:
                result = future.result(timeout=8)
            except PreparationComplete:
                outcomes.append("prepared")
            else:
                outcomes.append((result.state, result.error_code))
    assert outcomes == ["prepared", "prepared"]
    assert not mutated_during_copy
    assert second_mkdir.is_set()
    assert {job_id for job_id, _ in snapshots} == {job.job_id for job in jobs}
    assert snapshots[0][1] == snapshots[1][1]


def test_waiting_preparation_uses_original_timeout_without_creating_attempt(
    prepared, tmp_path, monkeypatch
):
    _, lake, _ = prepared
    store = SQLiteJobStore(tmp_path / "timed.sqlite", lake_root=lake)
    job = store.submit("local", "timed", request_for(lake, budget={"timeout_seconds": 1}))
    guard = Lock()
    monkeypatch.setattr(job_runner, "_SNAPSHOT_LOCK", guard, raising=False)

    def forbidden_snapshot(*args):
        raise PreparationComplete("expired waiter reached snapshot")

    monkeypatch.setattr(job_runner, "_snapshot", forbidden_snapshot)
    with guard:
        result = job_runner.run_next_job(store, "waiting", lake, store.artifact_root)
    assert result.state == "failed" and result.error_code == "timeout"
    assert not (store.artifact_root / job.job_id).exists()


def test_waiting_preparation_observes_stop_without_creating_attempt(prepared, monkeypatch):
    store, lake, jobs = prepared
    guard, acquiring, stop = Lock(), Event(), Event()

    class ObservedLock:
        def acquire(self, *args, **kwargs):
            acquiring.set()
            return guard.acquire(*args, **kwargs)

        def release(self):
            guard.release()

    monkeypatch.setattr(job_runner, "_SNAPSHOT_LOCK", ObservedLock(), raising=False)

    def forbidden_snapshot(*args):
        raise PreparationComplete("stopped waiter reached snapshot")

    def run():
        token = job_runner._stop_event.set(stop)
        try:
            return job_runner.run_next_job(store, "waiting", lake, store.artifact_root)
        finally:
            job_runner._stop_event.reset(token)

    monkeypatch.setattr(job_runner, "_snapshot", forbidden_snapshot)
    with ThreadPoolExecutor(max_workers=1) as pool:
        guard.acquire()
        try:
            future = pool.submit(run)
            assert acquiring.wait(3)
            stop.set()
            result = future.result(timeout=2)
        finally:
            guard.release()
    assert result.state == "running"
    assert not (store.artifact_root / jobs[0].job_id).exists()


def test_snapshot_failure_releases_preparation_for_next_job(prepared, monkeypatch):
    store, lake, _ = prepared
    calls = []

    def snapshot(job, *args):
        calls.append(job.job_id)
        if len(calls) == 1:
            raise job_runner.DatasetRejected("intentional fixture failure")
        raise PreparationComplete

    monkeypatch.setattr(job_runner, "_snapshot", snapshot)
    failed = job_runner.run_next_job(store, "bad", lake, store.artifact_root)
    assert failed.state == "failed" and failed.error_code == "dataset_rejected"
    with ThreadPoolExecutor(max_workers=1) as pool:
        with pytest.raises(PreparationComplete):
            pool.submit(job_runner.run_next_job, store, "next", lake, store.artifact_root).result(
                timeout=3
            )
    assert len(set(calls)) == 2
