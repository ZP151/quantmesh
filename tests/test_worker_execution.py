"""Construction and actual owned-interface checks; fake Engine is not qualification."""

import importlib
import importlib.util
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event, current_thread
from threading import enumerate as active_threads

import pytest
from test_linux_owned import _inspect_for_create
from test_research_jobs import request_for

from quantmesh.research import job_runner, linux_owned
from quantmesh.research.baselines import run_baseline_report
from quantmesh.research.job_artifacts import _canonical, canonical_result
from quantmesh.research.job_store import SQLiteJobStore
from quantmesh.research.reports import ReportRegistry
from tests.research_fixtures import pinned_lake

RUNTIME = dict(
    build_digest="a" * 64,
    dependency_digest="b" * 64,
    git_commit="c" * 40,
    python_version="test-only measured interface",
    python_executable_digest="d" * 64,
)
linux_owner = pytest.mark.skipif(
    sys.platform != "linux", reason="Linux owner with fake Engine; not native qualification"
)


def api():
    assert importlib.util.find_spec("quantmesh.research.worker_execution"), (
        "WorkerRunner construction dispatcher missing"
    )
    return importlib.import_module("quantmesh.research.worker_execution")


@pytest.fixture(scope="module")
def small_fixture_data(tmp_path_factory):
    # Lazy initialization keeps absent-feature RED from allocating fixture copies.
    values = []

    def prepare():
        if not values:
            root = tmp_path_factory.mktemp("construction")
            lake = root / "lake"
            pinned_lake(lake)
            request = request_for(lake)
            report = run_baseline_report(
                dataset="equities",
                revision=request.dataset.revision,
                strategy=request.strategy_id,
                interval=request.interval,
                universe=request.universe,
                window_spec=request.window_spec,
                costs=request.costs,
                commit=job_runner.get_strategy("momentum", "1").implementation_digest,
                registry=ReportRegistry(root / "direct", lake_root=lake),
            )
            values.append((lake, report))
        return values[0]

    return prepare


@pytest.fixture
def small_fixture(tmp_path, small_fixture_data):
    # Reuse immutable numerical inputs only. Each case owns its queue and output:
    # a deliberately unclaimed job must never become another case's next job.
    values = []

    def prepare():
        if not values:
            lake, report = small_fixture_data()
            store = SQLiteJobStore(tmp_path / "jobs.sqlite", lake_root=lake)
            values.append((tmp_path, lake, store, report))
        return values[0]

    return prepare


def configured(monkeypatch, small_fixture, *, running=False, oom=False, code=0):
    module = api()
    root, lake, store, report = small_fixture()
    cli = root / "docker-fixture"
    cli.write_text("not an executable engine")
    profile = linux_owned.LinuxExecutionProfile(
        "unix:///var/run/docker.sock",
        cli,
        "sha256:" + "e" * 64,
        (os.getuid() or 10001) if os.name == "posix" else 10001,
        (os.getgid() or 10001) if os.name == "posix" else 10001,
        root,
    )
    state = {"Running": running, "ExitCode": code, "OOMKilled": oom}
    calls, nonce, mounts, pulses, create_args = [], [], {}, [], []
    limits = {
        "memory.max": "2147483648",
        "memory.swap.max": "0",
        "cpu.max": "100000 100000",
        "pids.max": "128",
    }

    def invoke(self, args):
        calls.append(args)
        if args[0] == "info":
            return json.dumps({"OSType": "linux", "CgroupVersion": "2", "ID": "fixture"})
        if args[:2] == ["image", "inspect"]:
            return json.dumps([{"Id": profile.image_id, "Os": "linux"}])
        if args[0] == "create":
            create_args[:] = args
            nonce.append(args[args.index("--label") + 1].split("=", 1)[1])
            for arg in args:
                if arg.startswith("type=bind,src="):
                    src, dst = arg.split(",")[1:3]
                    mounts[dst.removeprefix("dst=")] = Path(src.removeprefix("src="))
            return "f" * 64
        if args[0] == "inspect":
            inspected = _inspect_for_create(profile, create_args, nonce[-1], state)
            inspected["Id"] = "f" * 64
            return json.dumps([inspected])
        return ""

    class Attachment:
        on_pulse = None
        closed = False
        pulse_transport = None

        def receive(self, timeout):
            return dict(
                event="ready", bootstrap_sha256=linux_owned.bootstrap_digest(), limits=limits
            )

        def send(self, value):
            if value == "pulse":
                if self.pulse_transport is not None:
                    self.pulse_transport.send(value)
                pulses.append(
                    store.get(
                        "local", json.loads((mounts["/inputs"] / "job.json").read_bytes())["job_id"]
                    ).state
                )
                if self.on_pulse:
                    self.on_pulse()
            if value.startswith("go:") and not code and not oom:
                job = json.loads((mounts["/inputs"] / "job.json").read_bytes())
                actual_report = report.model_copy(deep=True)
                actual_report.evidence.update(
                    RUNTIME,
                    request_digest=job["request_digest"],
                    manifest_digest=job["request"]["dataset"]["manifest_digest"],
                    export_digest=job["request"]["dataset"]["export_digest"],
                )
                output = mounts["/output"]
                (output / "result.json").write_bytes(canonical_result(actual_report))
                (output / "receipt.json").write_bytes(
                    _canonical(
                        dict(
                            report=actual_report.model_dump(mode="json"),
                            runtime=RUNTIME,
                            owner=job["lease_owner"],
                            attempt=job["attempt"],
                        )
                    )
                )

        def close(self):
            self.closed = True
            if self.pulse_transport is not None:
                self.pulse_transport.close()

        def terminal_drained(self):
            return self.pulse_transport.terminal_drained()

    attachment = Attachment()
    attachment.state = state
    monkeypatch.setattr(linux_owned.LinuxExecutionProfile, "invoke", invoke)
    monkeypatch.setattr(linux_owned, "_attach", lambda *args: attachment)

    class TestAdmission:
        # Test-only independently supplied provider, deliberately no ready bool.
        # Production image admission/probe implementation remains a later gate.
        def verify(self, actual_profile):
            actual_profile.prerequisites()
            return dict(RUNTIME)

        def prepare_parent_binding(self, process, job, runtime, ready):
            from quantmesh.research.worker_build import ParentBindingContract, encode_parent_binding

            contract = ParentBindingContract(
                schema=1,
                engine_id=process.evidence["engine_id"],
                image_id=process.profile.image_id,
                image_config_sha256="a" * 64,
                container_id=process.container_id,
                owner_nonce=process.nonce,
                manifest_sha256="b" * 64,
                inventory_sha256="c" * 64,
                dependency_lock_sha256=runtime["dependency_digest"],
                python_executable_sha256=runtime["python_executable_digest"],
                entry_sha256="f" * 64,
                observer_sha256="0" * 64,
                expected_prefix="/usr/local",
                python_version="3.12.15",
                kernel_profile_sha256="1" * 64,
            )
            return encode_parent_binding(contract)

    execution = module.LinuxWorkerExecution(profile=profile, admission=TestAdmission())
    return module.WorkerRunner(execution=execution), store, lake, calls, mounts, pulses, attachment


def _terminal_pulse_transport(monkeypatch, attachment):
    """Keep production transport methods; replace only the external CLI process."""

    class Process:
        stdin = io.BytesIO()
        stdout = io.BytesIO()
        stderr = io.BytesIO()

        def poll(self):
            return None if attachment.state["Running"] else 0

        def wait(self, timeout):
            return self.poll()

        def kill(self):
            pass

    with monkeypatch.context() as patch:
        patch.setattr(linux_owned.subprocess, "Popen", lambda *args, **kwargs: Process())
        transport = linux_owned._Transport(["fixture"], {}, lines=True)
    for thread in transport.threads:
        thread.join(1)
        assert not thread.is_alive()
    attachment.pulse_transport = transport
    return transport


@linux_owner
def test_normal_exit_during_current_record_read_keeps_full_publication_path(
    small_fixture, monkeypatch
):
    # Removing pulse's exact-owned terminal reconciliation must fail this loop.
    runner, store, lake, calls, _, _, attachment = configured(
        monkeypatch, small_fixture, running=True
    )
    _terminal_pulse_transport(monkeypatch, attachment)
    job = store.submit("local", "terminal-pulse", request_for(lake))
    ticks, stages = [0.0], []
    monkeypatch.setattr(job_runner.time, "monotonic", lambda: ticks[0])
    get = store.get

    def exit_in_record_read(*args):
        current = get(*args)
        if ticks[0] == 1 and any(call[0] == "create" for call in calls):
            attachment.state["Running"] = False
        return current

    monkeypatch.setattr(store, "get", exit_in_record_read)
    observe = job_runner._observe_worker_call

    def observed(stage, callback):
        result = observe(stage, callback)
        stages.append(stage)
        return result

    monkeypatch.setattr(job_runner, "_observe_worker_call", observed)
    stop = Event()
    monkeypatch.setattr(stop, "wait", lambda seconds: ticks.__setitem__(0, ticks[0] + 1))
    with api()._worker_stop_scope(stop):
        result = runner.run_next_job(store, "worker", lake, store.artifact_root)
    assert result.job_id == job.job_id and result.state == "succeeded"
    assert len(result.artifacts) == 1 and result.attempt == 1
    assert stages[stages.index("pulse") :] == [
        "pulse",
        "poll",
        "validate_exit_first",
        "receipt_validation",
        "heartbeat_before_publish",
        "validate_exit_second",
        "publish",
        "finish_succeeded",
        "cleanup",
        "final_get",
    ]
    assert attachment.closed and ["rm", "--force", "f" * 64] in calls


@linux_owner
@pytest.mark.parametrize(
    "refusal", ["cancel", "receipt", "runtime", "binding", "stale", "deadline"]
)
def test_terminal_pulse_preserves_receipt_runtime_and_store_fences(
    small_fixture, monkeypatch, refusal
):
    runner, store, lake, calls, mounts, _, attachment = configured(
        monkeypatch, small_fixture, running=True
    )
    transport = _terminal_pulse_transport(monkeypatch, attachment)
    job = store.submit("local", "terminal-fence-" + refusal, request_for(lake))
    ticks, entered, published = [0.0], [], []
    monkeypatch.setattr(job_runner.time, "monotonic", lambda: ticks[0])
    get, drained = store.get, transport.terminal_drained

    def exit_in_record_read(*args):
        current = get(*args)
        if ticks[0] == 1 and any(call[0] == "create" for call in calls):
            attachment.state["Running"] = False
        return current

    def guarded_drain():
        result = drained()
        entered.append("reconcile")
        if refusal == "cancel":
            store.request_cancel("local", job.job_id)
        if refusal in {"receipt", "runtime"}:
            path = mounts["/output"] / "receipt.json"
            if refusal == "receipt":
                path.write_bytes(b"{}")
            else:
                receipt = json.loads(path.read_bytes())
                receipt["runtime"]["build_digest"] = "9" * 64
                path.write_bytes(_canonical(receipt))
        if refusal == "binding":
            path = mounts["/inputs"] / "parent-binding.json"
            path.chmod(0o600)
            path.write_bytes(path.read_bytes() + b" ")
            path.chmod(0o400)
        if refusal == "stale":
            future = datetime.now(UTC) + timedelta(seconds=61)
            assert store.claim("replacement", future).attempt == 2
        if refusal == "deadline":
            ticks[0] = job.request.budget.timeout_seconds
        return result

    monkeypatch.setattr(store, "get", exit_in_record_read)
    monkeypatch.setattr(transport, "terminal_drained", guarded_drain)
    publish = job_runner.publish_result

    def observed_publish(*args):
        published.append(True)
        return publish(*args)

    monkeypatch.setattr(job_runner, "publish_result", observed_publish)
    monkeypatch.setattr(
        job_runner.time, "sleep", lambda seconds: ticks.__setitem__(0, ticks[0] + 1)
    )
    result = runner.run_next_job(store, "worker", lake, store.artifact_root)
    assert entered == ["reconcile"]
    assert result.job_id == job.job_id and result.artifacts == [] and published == []
    if refusal == "cancel":
        assert result.state == "cancelled"
    elif refusal == "stale":
        assert result.attempt == 2 and result.lease_owner == "replacement"
    else:
        assert result.state == "failed"
    assert attachment.closed and ["rm", "--force", "f" * 64] in calls


def test_context_resets_on_exception_nested_default_and_independent_thread(monkeypatch):
    module = api()
    # Exercise the public wrapper and its consumer; no OS launch is needed here.
    outer, inner = object(), object()
    runner = module.WorkerRunner(execution=outer)
    nested = module.WorkerRunner(execution=inner)

    def consume(store, owner, inputs_root, artifacts_root):
        current = module._execution.get()
        if owner == "raise":
            assert current is outer
            raise SystemExit(23)
        if owner == "nested":
            assert nested.run_next_job(None, "read", None, None) is inner
            assert module.WorkerRunner().run_next_job(None, "read", None, None) is None
            with ThreadPoolExecutor(max_workers=1) as pool:
                assert (
                    pool.submit(job_runner.run_next_job, None, "read", None, None).result() is None
                )
            assert module._execution.get() is outer
        return current

    monkeypatch.setattr(job_runner, "run_next_job", consume)
    assert runner.run_next_job(None, "nested", None, None) is outer
    with pytest.raises(SystemExit):
        runner.run_next_job(None, "raise", None, None)
    assert job_runner.run_next_job(None, "read", None, None) is None


def test_worker_stop_scope_resets_on_nested_and_exceptional_exit():
    from threading import Event

    module = api()
    outer, inner = Event(), Event()
    assert module._stop_event.get() is None
    with module._worker_stop_scope(outer):
        assert module._stop_event.get() is outer
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(module._stop_event.get).result() is None
        with module._worker_stop_scope(inner):
            assert module._stop_event.get() is inner
        assert module._stop_event.get() is outer
        with pytest.raises(RuntimeError, match="scope failure"):
            with module._worker_stop_scope(inner):
                raise RuntimeError("scope failure")
        assert module._stop_event.get() is outer
    assert module._stop_event.get() is None


@linux_owner
def test_worker_stop_prevents_claim_when_runner_call_races_stop(small_fixture, monkeypatch):
    from threading import Event

    module = api()
    runner, store, lake, calls, _, _, _ = configured(monkeypatch, small_fixture)
    job = store.submit("local", "daemon-stop-before-claim", request_for(lake))
    stop = Event()
    stop.set()

    with module._worker_stop_scope(stop):
        result = runner.run_next_job(store, "daemon-owner-slot-0", lake, store.artifact_root)

    assert result is None and calls == []
    assert store.get("local", job.job_id).state == "queued"


@linux_owner
def test_worker_stop_racing_with_claim_leaves_lease_without_heartbeat(small_fixture, monkeypatch):
    from threading import Event

    module = api()
    runner, store, lake, calls, _, _, attachment = configured(monkeypatch, small_fixture)
    job = store.submit("local", "daemon-stop-after-claim", request_for(lake))
    stop = Event()
    claim = store.claim
    heartbeats = []

    def claim_then_stop(owner, now):
        record = claim(owner, now)
        stop.set()
        return record

    heartbeat = store.heartbeat

    def record_heartbeat(*args):
        heartbeats.append(args)
        return heartbeat(*args)

    monkeypatch.setattr(store, "claim", claim_then_stop)
    monkeypatch.setattr(store, "heartbeat", record_heartbeat)
    with module._worker_stop_scope(stop):
        result = runner.run_next_job(store, "daemon-owner-slot-0", lake, store.artifact_root)

    assert result.state == "running" and result.attempt == 1
    assert result.cancel_requested is False and result.artifacts == []
    assert heartbeats == [] and calls == [] and attachment.closed is False
    retry = store.claim("replacement-owner", result.lease_expires_at + timedelta(seconds=1))
    assert retry is not None and retry.job_id == job.job_id and retry.attempt == 2


@linux_owner
def test_worker_stop_leaves_claimed_attempt_for_lease_reclaim(small_fixture, monkeypatch):
    from threading import Event

    module = api()
    runner, store, lake, calls, _, pulses, attachment = configured(
        monkeypatch, small_fixture, running=True
    )
    job = store.submit("local", "daemon-stop-reclaim", request_for(lake))
    stop = Event()
    original_send = attachment.send

    def stop_after_start(value):
        original_send(value)
        if value.startswith("go:"):
            stop.set()

    attachment.send = stop_after_start
    with module._worker_stop_scope(stop):
        result = runner.run_next_job(store, "daemon-owner-slot-0", lake, store.artifact_root)

    assert result.state == "running" and result.attempt == 1
    assert result.cancel_requested is False and result.artifacts == []
    assert pulses == []
    assert ["rm", "--force", "f" * 64] in calls and attachment.closed

    retry_time = result.lease_expires_at + timedelta(seconds=1)
    retry = store.claim("replacement-owner", retry_time)
    assert retry is not None and retry.job_id == job.job_id and retry.attempt == 2
    assert (
        store.finish(job.job_id, "daemon-owner-slot-0", 1, "failed", [], "worker_failed") is False
    )


@linux_owner
def test_worker_stop_after_blob_upload_leaves_no_authoritative_report(small_fixture, monkeypatch):
    from threading import Event

    from quantmesh.research.worker_daemon import WorkerDaemon

    runner, store, lake, _, _, _, attachment = configured(monkeypatch, small_fixture)
    job = store.submit("local", "daemon-stop-before-finish", request_for(lake))
    stop = Event()
    publish = job_runner.publish_result
    published = []

    def publish_then_stop(claimed, raw, root):
        ref = publish(claimed, raw, root)
        published.append(ref)
        stop.set()
        return ref

    monkeypatch.setattr(job_runner, "publish_result", publish_then_stop)
    WorkerDaemon(
        runner=runner,
        store=store,
        inputs_root=lake,
        artifacts_root=store.artifact_root,
    ).run(stop)

    result = store.get("local", job.job_id)
    assert result.state == "running" and result.attempt == 1
    assert result.cancel_requested is False and result.artifacts == []
    assert len(published) == 1
    assert (store.artifact_root / published[0].object_key).is_file()
    assert attachment.closed


@linux_owner
def test_worker_stop_before_publish_does_not_upload_or_finish(small_fixture, monkeypatch):
    from threading import Event

    from quantmesh.research.worker_daemon import WorkerDaemon

    runner, store, lake, _, _, _, attachment = configured(monkeypatch, small_fixture)
    job = store.submit("local", "daemon-stop-before-publish", request_for(lake))
    stop = Event()
    validate = job_runner._validated_child_result
    publish = job_runner.publish_result
    published = []

    def validate_then_stop(*args, **kwargs):
        raw = validate(*args, **kwargs)
        stop.set()
        return raw

    def record_publish(*args, **kwargs):
        published.append(True)
        return publish(*args, **kwargs)

    monkeypatch.setattr(job_runner, "_validated_child_result", validate_then_stop)
    monkeypatch.setattr(job_runner, "publish_result", record_publish)
    WorkerDaemon(
        runner=runner,
        store=store,
        inputs_root=lake,
        artifacts_root=store.artifact_root,
    ).run(stop)

    result = store.get("local", job.job_id)
    assert result.state == "running" and result.attempt == 1 and result.artifacts == []
    assert published == [] and attachment.closed


@linux_owner
def test_worker_daemon_slot_failure_closes_sibling_owned_child(small_fixture, monkeypatch):
    from threading import Event, current_thread

    from quantmesh.research.worker_daemon import WorkerDaemon, WorkerDaemonError

    runner, store, lake, calls, _, _, attachment = configured(
        monkeypatch, small_fixture, running=True
    )
    job = store.submit("local", "daemon-sibling-cleanup", request_for(lake))
    child_started = Event()
    original_verify = runner.execution.admission.verify

    def fail_second_slot_after_child_start(profile):
        if current_thread().name == "research-worker-1":
            assert child_started.wait(3)
            raise RuntimeError("private admission detail")
        return original_verify(profile)

    monkeypatch.setattr(runner.execution.admission, "verify", fail_second_slot_after_child_start)
    original_start = type(runner.execution).start

    def start_and_signal(execution, *args, **kwargs):
        child = original_start(execution, *args, **kwargs)
        if execution is runner.execution:
            child_started.set()
        return child

    monkeypatch.setattr(type(runner.execution), "start", start_and_signal)

    with pytest.raises(WorkerDaemonError, match="worker_daemon_failed"):
        WorkerDaemon(
            runner=runner,
            store=store,
            inputs_root=lake,
            artifacts_root=store.artifact_root,
        ).run(Event())

    result = store.get("local", job.job_id)
    assert result.state == "running" and result.attempt == 1 and result.artifacts == []
    assert ["rm", "--force", "f" * 64] in calls
    assert attachment.closed


def test_worker_refuses_to_create_container_without_parent_binding_provider(
    monkeypatch, small_fixture
):
    module = api()
    root, lake, store, _ = small_fixture()
    cli = root / "docker-no-binding"
    cli.write_text("not an executable engine")
    profile = linux_owned.LinuxExecutionProfile(
        "unix:///var/run/docker.sock",
        cli,
        "sha256:" + "e" * 64,
        (os.getuid() or 10001) if os.name == "posix" else 10001,
        (os.getgid() or 10001) if os.name == "posix" else 10001,
        root,
    )
    requested = []
    monkeypatch.setattr(
        module,
        "LinuxOwnedProcess",
        lambda *args, **kwargs: requested.append((args, kwargs)),
    )

    class NoParentBindingAdmission:
        def verify(self, actual_profile):
            return dict(RUNTIME)

    execution = module.LinuxWorkerExecution(profile, NoParentBindingAdmission())
    job = store.submit("local", "parent-binding-required", request_for(lake))
    with pytest.raises(linux_owned.LinuxContainmentError, match="parent_binding_required"):
        execution.start(job, dict(RUNTIME), root / "bundle", root / "output")
    assert requested == []


@pytest.mark.parametrize("outcome", ["success", "nonzero", "oom"])
@linux_owner
def test_actual_owned_status_separate_bundle_and_publication(small_fixture, monkeypatch, outcome):
    runner, store, lake, calls, mounts, _, attachment = configured(
        monkeypatch, small_fixture, code=7 if outcome == "nonzero" else 0, oom=outcome == "oom"
    )
    job = store.submit("local", outcome, request_for(lake))
    result = runner.run_next_job(store, "worker", lake, store.artifact_root)
    assert result.job_id == job.job_id
    assert result.state == ("succeeded" if outcome == "success" else "failed")
    assert bool(result.artifacts) == (outcome == "success")
    assert mounts["/inputs"].name == "bundle" and mounts["/output"].name == "output"
    assert not mounts["/output"].is_relative_to(mounts["/inputs"])
    assert not list(mounts["/inputs"].rglob("receipt.json"))
    create = next(args for args in calls if args[0] == "create")
    assert create[-11:] == [
        "/usr/local/bin/python3",
        "-B",
        "-I",
        "-S",
        "/opt/quantmesh/worker_entry.py",
        "--binding",
        "/inputs/parent-binding.json",
        "--manifest",
        "/opt/quantmesh/manifest.json",
        "--inventory",
        "/opt/quantmesh/inventory.json",
    ]
    assert ["rm", "--force", "f" * 64] in calls and attachment.closed


@linux_owner
def test_cancel_fence_stops_pulses_and_preserves_no_success(small_fixture, monkeypatch):
    runner, store, lake, calls, _, pulses, attachment = configured(
        monkeypatch, small_fixture, running=True
    )
    job = store.submit("local", "cancel-live", request_for(lake))
    ticks = [0.0]
    monkeypatch.setattr(job_runner.time, "monotonic", lambda: ticks[0])
    monkeypatch.setattr(
        job_runner.time, "sleep", lambda seconds: ticks.__setitem__(0, ticks[0] + 1)
    )
    attachment.on_pulse = lambda: store.request_cancel("local", job.job_id)
    result = runner.run_next_job(store, "worker", lake, store.artifact_root)
    assert result.cancel_requested and result.artifacts == []
    assert pulses == ["running"]
    assert ["rm", "--force", "f" * 64] in calls and attachment.closed


@linux_owner
def test_post_upload_reclaim_rejects_old_success(small_fixture, monkeypatch):
    runner, store, lake, _, _, _, _ = configured(monkeypatch, small_fixture)
    job = store.submit("local", "reclaimed", request_for(lake))
    publish = job_runner.publish_result

    def reclaim(claimed, raw, root):
        ref = publish(claimed, raw, root)
        future = datetime.now(UTC) + timedelta(seconds=61)
        store._clock = lambda: future
        assert store.claim("new-owner", future).attempt == 2
        return ref

    monkeypatch.setattr(job_runner, "publish_result", reclaim)
    try:
        result = runner.run_next_job(store, "old-owner", lake, store.artifact_root)
        assert result.job_id == job.job_id and result.attempt == 2
        assert result.lease_owner == "new-owner" and result.artifacts == []
        store.finish(job.job_id, "new-owner", 2, "failed", [], "worker_failed")
    finally:
        store._clock = lambda: datetime.now(UTC)


@linux_owner
def test_unconfigured_function_after_runner_still_refuses_linux(small_fixture, monkeypatch):
    runner, store, lake, _, _, _, _ = configured(monkeypatch, small_fixture)
    store.submit("local", "configured", request_for(lake))
    assert runner.run_next_job(store, "worker", lake, store.artifact_root).state == "succeeded"
    job = store.submit("local", "unconfigured", request_for(lake))
    monkeypatch.setattr(job_runner, "runtime_fingerprint", lambda: dict(RUNTIME))
    monkeypatch.setattr(job_runner.sys, "platform", "linux")
    result = job_runner.run_next_job(store, "direct", lake, store.artifact_root)
    assert result.job_id == job.job_id and result.state == "failed" and result.artifacts == []
    failure = next((store.artifact_root / job.job_id).rglob("failure.json"))
    assert json.loads(failure.read_bytes())["limitation"] == "platform_or_cpu_quota_unsupported"


@linux_owner
def test_changed_admission_after_child_exit_cannot_publish(small_fixture, monkeypatch):
    runner, store, lake, _, _, _, _ = configured(monkeypatch, small_fixture)
    job = store.submit("local", "changed-admission", request_for(lake))
    admitted = runner.execution.admission.verify
    reads = []

    def changed(profile):
        runtime = admitted(profile)
        reads.append(None)
        if len(reads) > 2:
            runtime["dependency_digest"] = "9" * 64
        return runtime

    monkeypatch.setattr(runner.execution.admission, "verify", changed)
    result = runner.run_next_job(store, "worker", lake, store.artifact_root)
    assert result.job_id == job.job_id and result.state == "failed"
    assert result.artifacts == []


@linux_owner
def test_parent_binding_is_rechecked_after_result_validation_before_publish(
    small_fixture, monkeypatch
):
    runner, store, lake, _, mounts, _, _ = configured(monkeypatch, small_fixture)
    job = store.submit("local", "binding-drift-before-publish", request_for(lake))
    validate_result = job_runner._validated_child_result

    def drift_binding(*args, **kwargs):
        raw = validate_result(*args, **kwargs)
        binding = mounts["/inputs"] / "parent-binding.json"
        binding.chmod(0o600)
        binding.write_bytes(binding.read_bytes() + b" ")
        binding.chmod(0o400)
        return raw

    monkeypatch.setattr(job_runner, "_validated_child_result", drift_binding)
    result = runner.run_next_job(store, "worker", lake, store.artifact_root)
    assert result.job_id == job.job_id and result.state == "failed"
    assert result.artifacts == []


@linux_owner
def test_heartbeat_denial_stops_owned_tree_before_more_pulses(small_fixture, monkeypatch):
    runner, store, lake, calls, _, pulses, attachment = configured(
        monkeypatch, small_fixture, running=True
    )
    job = store.submit("local", "heartbeat-denied", request_for(lake))
    ticks, heartbeats = [0.0], []
    original = store.heartbeat

    def deny_after_launch(*args):
        heartbeats.append(ticks[0])
        return original(*args) if len(heartbeats) == 1 else False

    monkeypatch.setattr(store, "heartbeat", deny_after_launch)
    monkeypatch.setattr(job_runner.time, "monotonic", lambda: ticks[0])
    monkeypatch.setattr(
        job_runner.time, "sleep", lambda seconds: ticks.__setitem__(0, ticks[0] + 1)
    )
    result = runner.run_next_job(store, "worker", lake, store.artifact_root)
    assert result.state == "running" and result.artifacts == []
    assert heartbeats == [0.0, 15.0] and len(pulses) == 14
    assert ["rm", "--force", "f" * 64] in calls and attachment.closed
    store.request_cancel("local", job.job_id)


@linux_owner
def test_stop_racing_job_read_prevents_heartbeat_and_pulse(small_fixture, monkeypatch):
    runner, store, lake, calls, _, pulses, attachment = configured(
        monkeypatch, small_fixture, running=True
    )
    store.submit("local", "stop-during-read", request_for(lake))
    stop = Event()
    original_get = store.get
    original_heartbeat = store.heartbeat
    heartbeats = []
    ticks = [0.0]

    def get_and_stop(operator_id, job_id):
        record = original_get(operator_id, job_id)
        if not attachment.closed and any(call[0] == "create" for call in calls):
            ticks[0] = 2.0
            stop.set()
        return record

    def count_heartbeat(*args):
        heartbeats.append(args)
        return original_heartbeat(*args)

    monkeypatch.setattr(store, "get", get_and_stop)
    monkeypatch.setattr(store, "heartbeat", count_heartbeat)
    monkeypatch.setattr(job_runner.time, "monotonic", lambda: ticks[0])
    monkeypatch.setattr(job_runner, "HEARTBEAT_SECONDS", 1.0)

    with api()._worker_stop_scope(stop):
        result = runner.run_next_job(store, "worker", lake, store.artifact_root)

    assert result.state == "running" and result.artifacts == []
    assert len(heartbeats) == 1  # initial lease heartbeat only
    assert pulses == []
    assert ["rm", "--force", "f" * 64] in calls and attachment.closed


@linux_owner
def test_daemon_slot_failure_closes_sibling_owned_child(small_fixture, monkeypatch):
    from quantmesh.research.worker_daemon import WorkerDaemon, WorkerDaemonError

    runner, store, lake, calls, _, _, attachment = configured(
        monkeypatch, small_fixture, running=True
    )
    job = store.submit("local", "sibling-cleanup", request_for(lake))
    child_started = Event()
    verify = runner.execution.admission.verify

    def fail_after_sibling_start(profile):
        if current_thread().name == "research-worker-0":
            assert child_started.wait(5)
            raise RuntimeError("untrusted admission detail")
        return verify(profile)

    monkeypatch.setattr(runner.execution.admission, "verify", fail_after_sibling_start)
    execution_type = type(runner.execution)
    original_start = execution_type.start

    def signal_child_started(execution, *args, **kwargs):
        child = original_start(execution, *args, **kwargs)
        child_started.set()
        return child

    monkeypatch.setattr(execution_type, "start", signal_child_started)
    daemon = WorkerDaemon(
        runner=runner,
        store=store,
        inputs_root=lake,
        artifacts_root=store.artifact_root,
    )

    with pytest.raises(WorkerDaemonError, match="worker_daemon_failed"):
        daemon.run(Event())

    assert child_started.is_set()
    assert ["rm", "--force", "f" * 64] in calls
    assert attachment.closed
    assert not any(
        thread.is_alive() and thread.name.startswith("research-worker-")
        for thread in active_threads()
    )
    record = store.get("local", job.job_id)
    assert record.state == "running" and record.attempt == 1 and record.artifacts == []


@linux_owner
def test_linux_child_refuses_host_fingerprint_without_manifest(small_fixture, monkeypatch):
    api()
    root, lake, store, _ = small_fixture()
    queued = store.submit("local", "child-no-manifest", request_for(lake))
    job = store.claim("worker", datetime.now(UTC))
    bundle, output = root / "child-bundle", root / "child-output"
    bundle.mkdir()
    output.mkdir()
    job_runner._snapshot(job, lake, bundle / "inputs")
    (bundle / "job.json").write_text(job.model_dump_json())
    (bundle / "runtime.json").write_bytes(_canonical(RUNTIME))
    monkeypatch.setattr(job_runner, "runtime_fingerprint", lambda **kwargs: dict(RUNTIME))
    with pytest.raises(SystemExit):
        job_runner._child_main(str(bundle), output_directory=str(output))
    assert not (output / "result.json").exists()
    store.finish(queued.job_id, "worker", 1, "failed", [], "worker_failed")
