"""Real daemon/runner control flow; offline numerical/store/child seams only."""

import dataclasses
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, current_thread
from types import SimpleNamespace

import pytest

from quantmesh.research import job_runner, worker_execution
from quantmesh.research.job_store import SQLiteJobStore
from quantmesh.research.jobs import StoreUnavailable
from quantmesh.research.linux_owned import LinuxContainmentError, LinuxOwnedProcess
from quantmesh.research.worker_daemon import WorkerDaemon, WorkerDaemonError
from quantmesh.research.worker_execution import LinuxWorkerExecution, WorkerRunner
from quantmesh.research.worker_stop import _WorkerStop

PRIVATE = "private-value-never-retained"


@pytest.fixture
def run_case(tmp_path, monkeypatch):
    def run(case, inspect_capture=None):
        stop = _WorkerStop()
        sibling_ready, sibling_receipt = Event(), Event()
        first_captured = Event()
        claims, records, heartbeats, validations = set(), {}, {}, {}
        states = {0: "running", 1: "running"}
        cleanups, handoffs, operations = [], [], []
        primary = LinuxContainmentError(PRIVATE)
        primary.__cause__ = RuntimeError(PRIVATE + "-cause")
        cleanup = LinuxContainmentError(PRIVATE + "-cleanup")

        def fail(stage):
            assert sibling_ready.wait(3), "sibling constructor did not return"
            operations.append(stage)
            if case == "finish_store":
                raise StoreUnavailable(PRIVATE)
            raise primary

        def serialize_job(slot):
            if case == "job_serialization" and slot == 0:
                fail("job_serialization")
            return "{}"

        class Store(SQLiteJobStore):
            def __init__(self):
                pass

            def claim(self, owner, now):
                slot = int(owner[-1])
                if slot in claims:
                    if case in {"receipt_value_error", "heartbeat_false", "finish_false"}:
                        stop.set()
                    return None
                claims.add(slot)
                records[slot] = SimpleNamespace(
                    slot=slot,
                    job_id=str(slot) * 32,
                    operator_id="synthetic",
                    attempt=2,
                    request=SimpleNamespace(budget=SimpleNamespace(timeout_seconds=30)),
                    state="running",
                    cancel_requested=False,
                    lease_owner=owner,
                    lease_expires_at=datetime.now(UTC) + timedelta(seconds=60),
                    model_dump_json=lambda: serialize_job(slot),
                )
                return records[slot]

            def get(self, operator_id, job_id):
                return records[int(job_id[-1])]

            def heartbeat(self, job_id, owner, attempt, now):
                slot = int(job_id[-1])
                heartbeats[slot] = heartbeats.get(slot, 0) + 1
                return not (case == "heartbeat_false" and slot == 0 and heartbeats[slot] == 2)

            def finish(self, job_id, owner, attempt, state, refs, error):
                slot = int(job_id[-1])
                operations.append(("finish", slot, state))
                if case == "finish_store" and slot == 0:
                    fail("finish_store")
                if case == "finish_false" and slot == 0:
                    return False
                states[slot] = state
                return True

            def _expire_owned_lease(self, *args):
                handoffs.append(args)
                return True

        class Child(LinuxOwnedProcess):
            def __init__(self, job):
                self.job, self.closed = job, False

            def poll(self):
                if self.job.slot == 1:
                    if case == "admission_after_success":
                        sibling_receipt.set()
                        return 0
                    return None
                if case == "poll":
                    fail("poll")
                return 0

            def close(self):
                operations.append(("close", self.job.slot))
                if self.job.slot == 1 and case == "sibling_cleanup":
                    assert first_captured.wait(3)
                    raise cleanup
                if self.job.slot == 0 and case in {"cleanup", "primary_cleanup", "handled_cleanup"}:
                    assert sibling_ready.wait(3)
                    raise cleanup
                self.closed = True
                cleanups.append(self.job.slot)

        def fingerprint(execution):
            slot = int(current_thread().name[-1])
            if case == "admission_after_success" and slot == 0 and states[0] == "succeeded":
                assert sibling_receipt.wait(3)
                fail("admission_after_success")
            return {"synthetic": True}

        def start(execution, job, runtime, bundle, output):
            if job.slot == 1:
                sibling_ready.set()
            if case == "constructor" and job.slot == 0:
                fail("constructor")
            return Child(job)

        def validate(execution, child, job, runtime):
            slot = job.slot
            validations[slot] = validations.get(slot, 0) + 1
            stage = "validate_exit_first" if validations[slot] == 1 else "validate_exit_second"
            if slot == 0 and (case == stage or case in {"primary_cleanup", "sibling_cleanup"}):
                fail(stage)
            if case == "admission_after_success" and slot == 1:
                assert stop.wait(3)

        def result(job, *args):
            if case == "handled_cleanup" and job.slot == 0:
                assert sibling_ready.wait(3)
                stop.set()
                raise ValueError(PRIVATE)
            if case == "receipt_value_error" and job.slot == 0:
                raise ValueError(PRIVATE)
            return b"{}"

        monkeypatch.setattr(LinuxWorkerExecution, "runtime_fingerprint", fingerprint)
        monkeypatch.setattr(LinuxWorkerExecution, "start", start)
        monkeypatch.setattr(LinuxWorkerExecution, "validate_exit", validate)
        monkeypatch.setattr(job_runner, "_snapshot", lambda *a: None)
        monkeypatch.setattr(job_runner, "_contained", lambda *a: None)
        monkeypatch.setattr(job_runner, "_validated_child_result", result)
        monkeypatch.setattr(job_runner, "publish_result", lambda *a: object())
        if case == "claim_clock":

            class ClaimClock:
                @staticmethod
                def now(zone):
                    if current_thread().name.endswith("0"):
                        fail("claim_clock")
                    return datetime.now(zone)

            monkeypatch.setattr(job_runner, "datetime", ClaimClock)
        if case == "runtime_serialization":
            canonical = job_runner._canonical

            def serialize_runtime(value):
                if current_thread().name.endswith("0"):
                    fail("runtime_serialization")
                return canonical(value)

            monkeypatch.setattr(job_runner, "_canonical", serialize_runtime)
        if case == "sibling_cleanup" or inspect_capture is not None:
            escaping = worker_execution._WorkerSlotDiagnostics.escaping

            def capture(state):
                if inspect_capture is not None:
                    inspect_capture(stop)
                value = escaping(state)
                if state.slot == 0:
                    first_captured.set()
                return value

            monkeypatch.setattr(worker_execution._WorkerSlotDiagnostics, "escaping", capture)
        daemon = WorkerDaemon(
            runner=WorkerRunner(execution=LinuxWorkerExecution(None, None)),
            store=Store(),
            inputs_root=tmp_path,
            artifacts_root=tmp_path,
        )
        error = None
        try:
            daemon.run(stop)
        except WorkerDaemonError as caught:
            error = caught
        return SimpleNamespace(
            error=error,
            states=states,
            cleanups=cleanups,
            handoffs=handoffs,
            stop=stop,
            operations=operations,
        )

    return run


def observation(result):
    value = getattr(result.error, "observation", None)
    assert value is not None, "escaping Worker failure lost stage/category/monotonic evidence"
    return dataclasses.asdict(value)


@pytest.mark.parametrize(
    ("case", "stage", "job_id", "cleanups"),
    [
        ("job_serialization", "bundle_write", "0" * 32, [1]),
        ("claim_clock", "claim", None, [1]),
        ("runtime_serialization", "bundle_write", "0" * 32, [1]),
    ],
)
def test_argument_evaluation_is_attributed_to_intended_operation(
    run_case, case, stage, job_id, cleanups
):
    result = run_case(case)
    captured = observation(result)
    first = captured["first_failure"]
    assert first["stage"] == stage
    assert first["category"] == "containment_failed"
    assert first["job_id"] == job_id
    assert sorted(result.cleanups) == cleanups
    assert result.states == {0: "running", 1: "running"}
    assert result.handoffs == [] and result.stop.is_set() and not result.stop.controlled
    assert PRIVATE not in json.dumps(captured)


def test_second_exit_validation_preserves_first_escaping_failure(run_case):
    result = run_case("validate_exit_second")
    captured = observation(result)
    first = captured["first_failure"]
    assert first["stage"] == "validate_exit_second"
    assert first["category"] == "containment_failed"
    assert first["slot"] == 0 and first["job_id"] == "0" * 32 and first["attempt"] == 2
    assert type(first["monotonic_ns"]) is int and first["monotonic_ns"] >= 0
    assert captured["secondary_cleanup"] == ()
    assert PRIVATE not in json.dumps(captured)
    assert result.states == {0: "running", 1: "running"}
    assert sorted(result.cleanups) == [0, 1] and result.handoffs == []
    assert result.stop.is_set() and not result.stop.controlled
    assert str(result.error) == "worker_daemon_failed"


def test_cleanup_secondary_does_not_replace_escaping_primary(run_case):
    result = run_case("primary_cleanup")
    captured = observation(result)
    assert captured["first_failure"]["stage"] == "validate_exit_first"
    assert captured["secondary_cleanup"][0]["stage"] == "cleanup"
    assert captured["secondary_cleanup"][0]["category"] == "containment_failed"
    assert result.states == {0: "running", 1: "running"}
    assert result.cleanups == [1] and result.handoffs == []


@pytest.mark.parametrize(
    ("case", "stage", "state"),
    [
        ("constructor", "constructor", "running"),
        ("poll", "poll", "running"),
        ("validate_exit_first", "validate_exit_first", "running"),
        ("validate_exit_second", "validate_exit_second", "running"),
        ("cleanup", "cleanup", "succeeded"),
        ("finish_store", "finish_failed", "running"),
        ("admission_after_success", "slot_admission", "succeeded"),
    ],
)
def test_failure_mechanisms_keep_original_outcomes(run_case, case, stage, state):
    result = run_case(case)
    captured = observation(result)
    assert captured["first_failure"]["stage"] == stage
    assert result.states == {0: state, 1: "running"}
    assert result.handoffs == []
    assert result.stop.is_set() and not result.stop.controlled
    if case == "admission_after_success":
        assert captured["first_failure"]["job_id"] is None
        assert captured["first_failure"]["attempt"] is None
    if case == "finish_store":
        assert captured["first_failure"]["category"] == "store_unavailable"
        assert [("finish", 0, "succeeded"), ("finish", 0, "failed")] == [
            entry
            for entry in result.operations
            if isinstance(entry, tuple) and entry[0] == "finish"
        ]


@pytest.mark.parametrize(
    ("case", "state"),
    [
        ("receipt_value_error", "failed"),
        ("heartbeat_false", "running"),
        ("finish_false", "running"),
    ],
)
def test_handled_failure_and_fence_refusals_do_not_fail_daemon(run_case, case, state):
    result = run_case(case)
    assert result.error is None
    assert result.states == {0: state, 1: "running"}
    assert result.handoffs == []


@pytest.fixture
def worker_service_source(monkeypatch):
    service_source = Path(__file__).resolve().parents[1] / "services/research_agent/src"
    monkeypatch.syspath_prepend(str(service_source))
    from qm_research_agent import worker_runtime

    assert (
        Path(worker_runtime.__file__).resolve()
        == (service_source / "qm_research_agent/worker_runtime.py").resolve()
    )


def bootstrap(monkeypatch, error):
    from qm_research_agent import worker_runtime

    monkeypatch.setattr(
        worker_runtime, "load_worker_config", lambda *a: SimpleNamespace(service_config="unused")
    )
    monkeypatch.setattr(worker_runtime.service_runtime, "load_runtime", lambda *a: object())

    def fail(*args):
        raise error

    monkeypatch.setattr(worker_runtime, "_run_worker", fail)
    return worker_runtime.main(["--config", "unused", "--run"])


@pytest.mark.usefixtures("worker_service_source")
def test_bootstrap_emits_bounded_fixed_failure_fields(run_case, monkeypatch, capsys):
    result = run_case("primary_cleanup")
    assert bootstrap(monkeypatch, result.error) == 3
    captured = capsys.readouterr()
    assert captured.out == ""
    lines = captured.err.splitlines()
    assert len(lines) == 2, "safe observation must survive the bootstrap stderr boundary"
    assert lines[0] == "worker_daemon_failed"
    payload = json.loads(lines[1])
    assert payload["event"] == "worker_failure_observation" and payload["schema_version"] == 1
    assert payload["first_failure"]["stage"] == "validate_exit_first"
    assert payload["secondary_cleanup"][0]["stage"] == "cleanup"
    assert len(lines[1].encode()) <= 16 * 1024
    assert PRIVATE not in captured.err


@pytest.mark.usefixtures("worker_service_source")
def test_bootstrap_without_observation_preserves_original_single_line(monkeypatch, capsys):
    assert bootstrap(monkeypatch, WorkerDaemonError()) == 3
    assert capsys.readouterr().err == "worker_daemon_failed\n"


@pytest.mark.parametrize("invalid", ["metadata", "large", "arbitrary"])
@pytest.mark.usefixtures("worker_service_source")
def test_renderer_rejects_unsafe_or_oversized_observation(run_case, monkeypatch, capsys, invalid):
    error = run_case("validate_exit_second").error
    safe = error.observation
    if invalid == "metadata":
        error.observation = dataclasses.replace(
            safe, first_failure=dataclasses.replace(safe.first_failure, job_id=PRIVATE)
        )
    elif invalid == "large":
        error.observation = dataclasses.replace(safe, slots=safe.slots * 10000)
    else:
        error.observation = SimpleNamespace(raw=PRIVATE)
    assert bootstrap(monkeypatch, error) == 3
    assert capsys.readouterr().err == "worker_daemon_failed\n"


@pytest.mark.usefixtures("worker_service_source")
def test_renderer_ignores_unlisted_attributes(run_case, monkeypatch, capsys):
    error = run_case("validate_exit_second").error
    object.__setattr__(error.observation, "raw_payload", PRIVATE)
    assert bootstrap(monkeypatch, error) == 3
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 2
    assert PRIVATE not in lines[1]


@pytest.mark.usefixtures("worker_service_source")
def test_renderer_failure_does_not_replace_original_exit(run_case, monkeypatch, capsys):
    from qm_research_agent import worker_runtime

    error = run_case("validate_exit_second").error
    monkeypatch.setattr(
        worker_runtime.json, "dumps", lambda *a, **kw: (_ for _ in ()).throw(ValueError(PRIVATE))
    )
    assert bootstrap(monkeypatch, error) == 3
    assert capsys.readouterr().err == "worker_daemon_failed\n"


def test_ordinary_stop_is_silent(tmp_path, capsys):
    stop = _WorkerStop()
    stop.set()
    WorkerDaemon(
        runner=WorkerRunner(execution=LinuxWorkerExecution(None, None)),
        store=object(),
        inputs_root=tmp_path,
        artifacts_root=tmp_path,
    ).run(stop)
    assert capsys.readouterr() == ("", "")


def test_handled_stop_exception_is_not_promoted_when_cleanup_later_fails(run_case):
    captured = observation(run_case("handled_cleanup"))
    assert captured["first_failure"]["stage"] == "cleanup"
    assert captured["first_failure"]["category"] == "containment_failed"


@pytest.mark.parametrize("method", ["enter", "returned", "failure"])
def test_observation_errors_preserve_return_and_exception_identity(monkeypatch, method):
    state = worker_execution._WorkerSlotDiagnostics(0, 0)

    def broken(*args):
        raise KeyboardInterrupt(PRIVATE)

    monkeypatch.setattr(state, method, broken)
    original = LinuxContainmentError(PRIVATE)
    calls = []

    def returns():
        calls.append("return")
        return False

    def raises():
        calls.append("raise")
        raise original

    with worker_execution._worker_diagnostic_scope(state):
        assert worker_execution._observe_worker_call("poll", returns) is False
        with pytest.raises(LinuxContainmentError) as caught:
            worker_execution._observe_worker_call("poll", raises)
    assert caught.value is original
    assert calls == ["return", "raise"]


def test_stage_cells_and_metadata_are_bounded_and_context_is_reset():
    state = worker_execution._WorkerSlotDiagnostics(0, 0)
    with worker_execution._worker_diagnostic_scope(state):
        worker_execution._bind_worker_job(SimpleNamespace(job_id=PRIVATE, attempt=True))
        for _ in range(1000):
            worker_execution._observe_worker_call("poll", lambda: None)
        worker_execution._observe_worker_call(PRIVATE, lambda: None)
    assert worker_execution._worker_diagnostics.get() is None
    assert state.job_id is None and state.attempt is None
    assert len(state.snapshot().stages) == 1
    assert PRIVATE not in json.dumps(dataclasses.asdict(state.snapshot()))
    state.reset()
    assert state.last_failure is None and state.primary is None and state.stages == {}


def test_thread_start_failure_stops_joins_and_preserves_fixed_evidence(tmp_path, monkeypatch):
    from quantmesh.research import worker_daemon

    joined = []
    original_thread = worker_daemon.Thread

    class Thread(original_thread):
        def start(self):
            if self.name.endswith("1"):
                raise RuntimeError(PRIVATE)
            return super().start()

        def join(self):
            super().join()
            joined.append(self.name)

    monkeypatch.setattr(worker_daemon, "Thread", Thread)
    monkeypatch.setattr(LinuxWorkerExecution, "runtime_fingerprint", lambda *a: {})
    monkeypatch.setattr(job_runner, "run_next_job", lambda *a: None)
    stop = _WorkerStop()
    with pytest.raises(WorkerDaemonError) as caught:
        WorkerDaemon(
            runner=WorkerRunner(execution=LinuxWorkerExecution(None, None)),
            store=object(),
            inputs_root=tmp_path,
            artifacts_root=tmp_path,
        ).run(stop)
    captured = dataclasses.asdict(caught.value.observation)
    assert captured["first_failure"]["stage"] == "thread_start"
    assert captured["first_failure"]["slot"] == 1
    assert joined == ["research-worker-0"]
    assert stop.is_set() and not stop.controlled


def test_thread_join_failure_keeps_original_exception(tmp_path, monkeypatch):
    from quantmesh.research import worker_daemon

    original_thread = worker_daemon.Thread
    original = RuntimeError(PRIVATE)
    stop = _WorkerStop()

    class Thread(original_thread):
        def join(self):
            super().join()
            raise original

    monkeypatch.setattr(worker_daemon, "Thread", Thread)
    monkeypatch.setattr(LinuxWorkerExecution, "runtime_fingerprint", lambda *a: {})
    monkeypatch.setattr(job_runner, "run_next_job", lambda *a: stop.set())
    with pytest.raises(RuntimeError) as caught:
        WorkerDaemon(
            runner=WorkerRunner(execution=LinuxWorkerExecution(None, None)),
            store=object(),
            inputs_root=tmp_path,
            artifacts_root=tmp_path,
        ).run(stop)
    assert caught.value is original


def test_later_sibling_cleanup_is_secondary_and_cannot_replace_first_capture(run_case):
    captured = observation(run_case("sibling_cleanup"))
    assert captured["first_failure"]["stage"] == "validate_exit_first"
    assert captured["first_failure"]["slot"] == 0
    assert len(captured["secondary_cleanup"]) == 1
    assert captured["secondary_cleanup"][0]["slot"] == 1
    assert captured["secondary_cleanup"][0]["stage"] == "cleanup"


def test_capture_runs_after_original_failed_then_stop_order(run_case, monkeypatch):
    from quantmesh.research import worker_daemon

    events = []
    event_type = worker_daemon.Event

    class Failed(event_type):
        def set(self):
            events.append("failed")
            return super().set()

    set_stop = _WorkerStop.set

    def stop_first(stop):
        events.append("stop")
        return set_stop(stop)

    monkeypatch.setattr(worker_daemon, "Event", Failed)
    monkeypatch.setattr(_WorkerStop, "set", stop_first)

    def inspect(stop):
        assert events[:2] == ["failed", "stop"]
        assert stop.is_set()

    observation(run_case("validate_exit_first", inspect_capture=inspect))


def test_observation_retains_only_frozen_scalars(run_case):
    value = run_case("primary_cleanup").error.observation

    def safe(item):
        if dataclasses.is_dataclass(item):
            assert item.__dataclass_params__.frozen
            for field in dataclasses.fields(item):
                safe(getattr(item, field.name))
        elif type(item) is tuple:
            for child in item:
                safe(child)
        else:
            assert item is None or type(item) in {int, str}

    safe(value)


def test_diagnostic_lock_creation_failure_does_not_change_worker_failure(run_case, monkeypatch):
    from quantmesh.research import worker_daemon

    def broken():
        raise RuntimeError(PRIVATE)

    monkeypatch.setattr(worker_daemon, "Lock", broken)
    result = run_case("validate_exit_first")
    assert str(result.error) == "worker_daemon_failed"
    assert result.error.observation is None


@pytest.mark.parametrize("phase", ["set", "reset"])
def test_diagnostic_scope_failure_cannot_replace_original_exception(monkeypatch, phase):
    original = LinuxContainmentError(PRIVATE)

    class BrokenScope:
        def set(self, state):
            if phase == "set":
                raise RuntimeError(PRIVATE)
            return object()

        def reset(self, token):
            raise RuntimeError(PRIVATE)

    monkeypatch.setattr(worker_execution, "_worker_diagnostics", BrokenScope())
    with pytest.raises(LinuxContainmentError) as caught:
        with worker_execution._worker_diagnostic_scope(None):
            raise original
    assert caught.value is original
