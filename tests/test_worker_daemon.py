import importlib
import importlib.util
import inspect
import re
from datetime import UTC, datetime
from threading import Barrier, Event, Lock, Thread

import pytest
from test_research_jobs import request_for

from quantmesh.research import job_runner
from quantmesh.research.job_store import SQLiteJobStore
from quantmesh.research.worker_execution import LinuxWorkerExecution, WorkerRunner
from tests.research_fixtures import pinned_lake


def _daemon_api():
    assert importlib.util.find_spec("quantmesh.research.worker_daemon"), (
        "persistent worker daemon module missing"
    )
    return importlib.import_module("quantmesh.research.worker_daemon")


def _worker_runner(monkeypatch, fingerprint, run_next_job):
    runner = WorkerRunner(execution=LinuxWorkerExecution(profile=None, admission=None))
    monkeypatch.setattr(LinuxWorkerExecution, "runtime_fingerprint", fingerprint)
    monkeypatch.setattr(job_runner, "run_next_job", run_next_job)
    return runner


def _store(tmp_path, count=1):
    lake = tmp_path / "lake"
    pinned_lake(lake)
    store = SQLiteJobStore(tmp_path / "jobs.sqlite", lake_root=lake)
    jobs = [
        store.submit("local", f"daemon-test-{index}", request_for(lake)) for index in range(count)
    ]
    return store, lake, jobs


def test_worker_daemon_stopped_before_start_does_not_claim(tmp_path, monkeypatch):
    WorkerDaemon = _daemon_api().WorkerDaemon
    store, lake, jobs = _store(tmp_path)
    calls = []
    runner = _worker_runner(
        monkeypatch,
        lambda execution: {"qualified": True},
        lambda *args: calls.append(args),
    )
    stop = Event()
    stop.set()

    WorkerDaemon(
        runner=runner,
        store=store,
        inputs_root=lake,
        artifacts_root=store.artifact_root,
    ).run(stop)

    assert calls == []
    assert store.get("local", jobs[0].job_id).state == "queued"
    assert store.claim("third-party", datetime.now(UTC)).job_id == jobs[0].job_id


def test_worker_daemon_revalidates_before_each_slot_claim(tmp_path, monkeypatch):
    WorkerDaemon = _daemon_api().WorkerDaemon
    store, lake, _ = _store(tmp_path)
    stop = Event()
    both_admitted = Barrier(2)
    guard = Lock()
    admitted = []
    owners = []

    def run_next(store, owner, inputs_root, artifacts_root):
        with guard:
            owners.append(owner)
            if len(owners) == 2:
                stop.set()
        return None

    def count_fingerprint(execution):
        with guard:
            admitted.append(True)
        both_admitted.wait(3)
        return {"qualified": True}

    runner = _worker_runner(monkeypatch, count_fingerprint, run_next)

    WorkerDaemon(
        runner=runner,
        store=store,
        inputs_root=lake,
        artifacts_root=store.artifact_root,
    ).run(stop)

    assert len(admitted) == len(owners) == 2
    assert len(set(owners)) == 2
    assert all(re.fullmatch(r"worker-[0-9a-f]{32}-slot-[01]", owner) for owner in owners)


def test_worker_daemon_refuses_missing_linux_execution(tmp_path):
    module = _daemon_api()
    store, lake, _ = _store(tmp_path)
    runner = WorkerRunner()

    with pytest.raises(module.WorkerDaemonError) as error:
        module.WorkerDaemon(
            runner=runner,
            store=store,
            inputs_root=lake,
            artifacts_root=store.artifact_root,
        ).run(Event())

    assert str(error.value) == "worker_daemon_failed"


def test_worker_daemon_refuses_non_linux_execution_before_claim(tmp_path):
    module = _daemon_api()
    store, lake, jobs = _store(tmp_path)

    class UnboundedExecution:
        def runtime_fingerprint(self):
            return {
                "build_digest": "a" * 64,
                "dependency_digest": "b" * 64,
                "git_commit": "c" * 40,
                "python_version": "test-only measured interface",
                "python_executable_digest": "d" * 64,
            }

    with pytest.raises(module.WorkerDaemonError) as error:
        module.WorkerDaemon(
            runner=WorkerRunner(execution=UnboundedExecution()),
            store=store,
            inputs_root=lake,
            artifacts_root=store.artifact_root,
        ).run(Event())

    assert str(error.value) == "worker_daemon_failed"
    assert store.get("local", jobs[0].job_id).state == "queued"


def test_worker_daemon_preserves_single_attempt_public_signatures():
    from quantmesh.research.job_runner import run_next_job

    assert list(inspect.signature(run_next_job).parameters) == [
        "store",
        "owner",
        "inputs_root",
        "artifacts_root",
    ]
    assert list(inspect.signature(WorkerRunner.run_next_job).parameters) == [
        "self",
        "store",
        "owner",
        "inputs_root",
        "artifacts_root",
    ]


def test_worker_daemon_rejects_duck_typed_runner(tmp_path):
    module = _daemon_api()
    store, lake, _ = _store(tmp_path)
    calls = []
    stop = Event()

    class UntrustedRunner:
        execution = LinuxWorkerExecution(profile=None, admission=None)

        def run_next_job(self, store, owner, inputs_root, artifacts_root):
            calls.append(owner)
            stop.set()
            return None

    with pytest.raises(module.WorkerDaemonError):
        module.WorkerDaemon(
            runner=UntrustedRunner(),
            store=store,
            inputs_root=lake,
            artifacts_root=store.artifact_root,
        ).run(stop)

    assert calls == []


def test_worker_daemon_shares_store_global_two_slot_limit(tmp_path, monkeypatch):
    WorkerDaemon = _daemon_api().WorkerDaemon
    store, lake, jobs = _store(tmp_path, count=3)
    stop, release, both_claimed = Event(), Event(), Event()
    owners = []
    guard = Lock()

    def claim_next(store, owner, inputs_root, artifacts_root):
        claimed = store.claim(owner, datetime.now(UTC))
        if claimed is not None:
            with guard:
                owners.append(owner)
                if len(owners) == 2:
                    both_claimed.set()
            release.wait(3)
        return claimed

    runner = _worker_runner(monkeypatch, lambda execution: {"qualified": True}, claim_next)

    daemon = WorkerDaemon(
        runner=runner,
        store=store,
        inputs_root=lake,
        artifacts_root=store.artifact_root,
    )
    errors = []

    def run_daemon():
        try:
            daemon.run(stop)
        except BaseException as exc:
            errors.append(exc)

    thread = Thread(target=run_daemon)
    thread.start()
    try:
        assert both_claimed.wait(3)
        assert len(set(owners)) == 2
        assert store.claim("third-party", datetime.now(UTC)) is None
    finally:
        stop.set()
        release.set()
        thread.join(3)

    assert not thread.is_alive()
    assert errors == []
    assert all(store.get("local", job.job_id).state == "running" for job in jobs[:2])
    assert store.get("local", jobs[2].job_id).state == "queued"


def test_worker_daemon_admission_drift_stops_before_claim(tmp_path, monkeypatch):
    WorkerDaemon = _daemon_api().WorkerDaemon
    store, lake, jobs = _store(tmp_path)
    stop = Event()

    calls = []

    def drifted_fingerprint(execution):
        raise RuntimeError("private admission path must not escape")

    runner = _worker_runner(monkeypatch, drifted_fingerprint, lambda *args: calls.append(args))
    daemon = WorkerDaemon(
        runner=runner,
        store=store,
        inputs_root=lake,
        artifacts_root=store.artifact_root,
    )

    with pytest.raises(RuntimeError, match="worker_daemon_failed") as error:
        daemon.run(stop)

    assert str(error.value) == "worker_daemon_failed"
    assert calls == []
    assert store.get("local", jobs[0].job_id).state == "queued"


def test_worker_daemon_slot_failure_stops_and_joins_sibling(tmp_path, monkeypatch):
    WorkerDaemon = _daemon_api().WorkerDaemon
    from quantmesh.research import worker_execution

    store, lake, jobs = _store(tmp_path)
    claimed = Event()
    sibling_cleaned = Event()
    call_lock = Lock()
    calls = 0

    def block_claimed(store, owner, inputs_root, artifacts_root):
        record = store.claim(owner, datetime.now(UTC))
        if record is None:
            return None
        claimed.set()
        stop = worker_execution._stop_event.get()
        assert stop is not None and stop.wait(3)
        sibling_cleaned.set()
        return record

    def coordinated_fingerprint(execution):
        nonlocal calls
        with call_lock:
            calls += 1
            call = calls
        if call == 2:
            assert claimed.wait(3)
            raise RuntimeError("untrusted admission details")
        return {"qualified": True}

    runner = _worker_runner(monkeypatch, coordinated_fingerprint, block_claimed)

    daemon = WorkerDaemon(
        runner=runner,
        store=store,
        inputs_root=lake,
        artifacts_root=store.artifact_root,
    )

    with pytest.raises(RuntimeError, match="worker_daemon_failed") as error:
        daemon.run(Event())

    assert str(error.value) == "worker_daemon_failed"
    assert sibling_cleaned.is_set()
    record = store.get("local", jobs[0].job_id)
    assert record.state == "running" and record.attempt == 1 and record.artifacts == []
