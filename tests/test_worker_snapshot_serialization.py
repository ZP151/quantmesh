"""Real POSIX snapshot concurrency; inert child seam is not OCI qualification."""

import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path
from threading import Barrier, Event, Lock, current_thread
from types import SimpleNamespace

import pytest
from test_research_jobs import request_for

from quantmesh.research import fixture_snapshot, job_runner
from quantmesh.research.job_store import SQLiteJobStore
from quantmesh.research.worker_execution import WorkerRunner
from tests.research_fixtures import pinned_lake


class PreparationComplete(Exception):
    pass


@pytest.fixture
def waiting_lease(tmp_path, monkeypatch, request):
    """Real store/runner with only the approved clock/I/O/child seams isolated."""
    if sys.platform != "linux":
        pytest.skip("Linux runner/inert-child seam, not native execution qualification")

    class Clock:
        nanoseconds = 0
        epoch = datetime(2026, 10, 22, tzinfo=UTC)

        def monotonic(self):
            return self.nanoseconds / 1_000_000_000

        def now(self, zone=UTC):
            return self.epoch + timedelta(microseconds=self.nanoseconds // 1000)

        def advance(self, seconds):
            self.nanoseconds += round(seconds * 1_000_000_000)

    clock, stop = Clock(), Event()
    lake = tmp_path / "lake"
    pinned_lake(lake)
    store = SQLiteJobStore(
        tmp_path / "state/jobs.sqlite",
        lake_root=lake,
        artifact_root=tmp_path / "artifacts",
        clock=clock.now,
    )
    timeout = getattr(request, "param", 90)
    job = store.submit("local", "waiting", request_for(lake, budget={"timeout_seconds": timeout}))
    claims, heartbeats, acquired, starts, cleanups, lock_calls = [], [], [], [], [], []
    hooks = SimpleNamespace(after_miss=None, after_heartbeat=None)
    real_claim, real_heartbeat = store.claim, store.heartbeat

    def claim(owner, now):
        value = real_claim(owner, now)
        claims.append(value)
        return value

    def heartbeat(*args):
        assert not stop.is_set(), "heartbeat began after cooperative stop"
        value = real_heartbeat(*args)
        heartbeats.append((clock.monotonic(), value))
        if hooks.after_heartbeat is not None:
            hooks.after_heartbeat()
        return value

    class ContendedLock:
        release_at = 65
        releases = 0

        def acquire(self, *, timeout):
            lock_calls.append(clock.monotonic())
            if clock.monotonic() < self.release_at:
                clock.advance(min(timeout, self.release_at - clock.monotonic()))
                if hooks.after_miss is not None:
                    hooks.after_miss()
                return False
            acquired.append(store.get("local", job.job_id))
            return True

        def release(self):
            self.releases += 1

    guard = ContendedLock()

    class Child:
        def poll(self):
            stop.set()  # Inert child stops before output validation/publication.
            return None

        def close(self):
            cleanups.append(clock.monotonic())

    class Execution:
        def runtime_fingerprint(self):
            return {}

        def start(self, *args):
            starts.append(clock.monotonic())
            return Child()

    def snapshot(job, source, destination):
        destination.mkdir()

    monkeypatch.setattr(store, "claim", claim)
    monkeypatch.setattr(store, "heartbeat", heartbeat)
    monkeypatch.setattr(job_runner, "_SNAPSHOT_LOCK", guard)
    monkeypatch.setattr(job_runner, "_snapshot", snapshot)
    monkeypatch.setattr(job_runner, "datetime", SimpleNamespace(now=clock.now))
    monkeypatch.setattr(
        job_runner, "time", SimpleNamespace(monotonic=clock.monotonic, sleep=clock.advance)
    )
    monkeypatch.setattr(
        import_module("quantmesh.research._launch_deadline"),
        "time",
        SimpleNamespace(monotonic=clock.monotonic),
    )

    def run():
        token = job_runner._stop_event.set(stop)
        try:
            return WorkerRunner(execution=Execution()).run_next_job(
                store, "waiting-owner", lake, store.artifact_root
            )
        finally:
            job_runner._stop_event.reset(token)

    return SimpleNamespace(
        run=run,
        store=store,
        job=job,
        clock=clock,
        guard=guard,
        stop=stop,
        claims=claims,
        heartbeats=heartbeats,
        acquired=acquired,
        starts=starts,
        cleanups=cleanups,
        hooks=hooks,
        lock_calls=lock_calls,
    )


def test_contended_snapshot_wait_renews_real_lease_before_first_child(waiting_lease):
    case = waiting_lease
    result = case.run()
    fresh = case.store.get("local", case.job.job_id)
    assert result.state == "running" and fresh.attempt == 1
    assert result.artifacts == [] and fresh.analysis_state == "not_requested"
    assert case.store.claim_analysis("oracle", case.clock.now()) is None
    assert case.claims[0].lease_expires_at == case.clock.epoch + timedelta(seconds=60)
    assert case.clock.monotonic() == 65
    assert case.starts == [65.0], {
        "state": fresh.state,
        "attempt": fresh.attempt,
        "fresh_lease_at_lock": case.acquired[0].lease_expires_at,
        "heartbeats": case.heartbeats,
        "constructors": case.starts,
    }
    assert case.cleanups == [65.0] and case.guard.releases == 1
    assert case.heartbeats == [(15.0, True), (30.0, True), (45.0, True), (60.0, True), (65.0, True)]
    assert case.acquired[0].lease_expires_at == case.clock.epoch + timedelta(seconds=120)
    # A stale claim's -5s is not the current authoritative lease's +55s.
    assert (case.claims[0].lease_expires_at - case.clock.now()).total_seconds() == -5
    assert (case.acquired[0].lease_expires_at - case.clock.now()).total_seconds() == 55


def test_uncontended_snapshot_keeps_original_heartbeat_count(waiting_lease):
    case = waiting_lease
    case.guard.release_at = 0
    result = case.run()
    assert result.state == "running" and result.attempt == 1
    assert case.heartbeats == [(0.0, True)]
    assert case.starts == case.cleanups == [0.0]
    assert case.guard.releases == 1


@pytest.mark.parametrize("stop_at", ["lock_miss", "heartbeat_return"])
def test_contended_wait_stops_before_any_next_operation(waiting_lease, stop_at):
    case = waiting_lease

    def stop_at_renewal_boundary():
        if case.clock.monotonic() >= 15:
            case.stop.set()

    if stop_at == "lock_miss":
        case.hooks.after_miss = stop_at_renewal_boundary
    else:
        case.hooks.after_heartbeat = stop_at_renewal_boundary
    result = case.run()
    assert result.state == "running" and result.attempt == 1
    assert case.clock.monotonic() == 15
    assert case.heartbeats == ([] if stop_at == "lock_miss" else [(15.0, True)])
    assert case.starts == case.cleanups == case.acquired == []
    assert case.guard.releases == 0 and max(case.lock_calls) < 15
    assert not (case.store.artifact_root / case.job.job_id).exists()


@pytest.mark.parametrize("fence", ["expired", "cancelled", "reclaimed-owner", "reclaimed-attempt"])
def test_contended_wait_honors_real_store_fence_without_constructing(waiting_lease, fence):
    case = waiting_lease
    expected = []
    at = 65 if fence == "expired" else 15 if fence == "cancelled" else 61

    def concurrent_change_during_wait():
        case.hooks.after_miss = None
        case.clock.advance(at - case.clock.monotonic())
        if fence == "cancelled":
            case.store.request_cancel("local", case.job.job_id)
        elif fence.startswith("reclaimed"):
            owner = "replacement" if fence == "reclaimed-owner" else "waiting-owner"
            reclaimed = case.store.claim(owner, case.clock.now())
            assert reclaimed is not None and reclaimed.attempt == 2
        expected.append(case.store.get("local", case.job.job_id))

    case.hooks.after_miss = concurrent_change_during_wait
    result = case.run()
    assert result == expected[0] == case.store.get("local", case.job.job_id)
    assert case.heartbeats == [(float(at), False)]
    assert case.starts == case.cleanups == case.acquired == []
    assert case.guard.releases == 0
    assert not (case.store.artifact_root / case.job.job_id).exists()
    assert result.artifacts == []
    assert case.store.claim_analysis("oracle", case.clock.now()) is None


@pytest.mark.parametrize("waiting_lease", [30], indirect=True)
@pytest.mark.parametrize("renewal_delay", [0, 15])
def test_contended_wait_keeps_original_deadline_after_renewal(waiting_lease, renewal_delay):
    case = waiting_lease
    case.hooks.after_heartbeat = lambda: case.clock.advance(renewal_delay)
    result = case.run()
    assert result.state == "failed" and result.error_code == "timeout" and result.attempt == 1
    assert case.clock.monotonic() == 30
    assert case.heartbeats == [(15.0, True)]
    assert case.starts == case.cleanups == case.acquired == []
    assert case.guard.releases == 0 and max(case.lock_calls) < 30
    assert not (case.store.artifact_root / case.job.job_id).exists()


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
