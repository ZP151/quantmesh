"""Standalone worker bootstrap boundaries; effects use ordered fakes only."""

import importlib
import importlib.util
import json
import signal
from pathlib import Path
from threading import Event
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from qm_research_agent import runtime as service_runtime
from qm_research_agent import store as service_store


def api():
    assert importlib.util.find_spec("qm_research_agent.worker_runtime"), (
        "standalone worker runtime module missing"
    )
    return importlib.import_module("qm_research_agent.worker_runtime")


def pin_data(**updates):
    values = {
        "engine_id": "fixture-engine-id",
        "image_id": "sha256:" + "1" * 64,
        "image_config_sha256": "2" * 64,
        "oci_manifest_sha256": "1" * 64,
        "oci_config_sha256": "2" * 64,
        "source_commit": "a" * 40,
        "manifest_sha256": "3" * 64,
        "inventory_sha256": "4" * 64,
        "runtime_metadata_sha256": "5" * 64,
        "dependency_lock_sha256": "6" * 64,
        "python_executable_sha256": "7" * 64,
        "entry_sha256": "8" * 64,
        "observer_sha256": "9" * 64,
        "expected_prefix": "/usr/local",
        "python_version": "3.12.15 (fixture)",
        "apparmor_name": "qm-worker-fixture",
        "apparmor_sha256": "a" * 64,
        "seccomp_sha256": "b" * 64,
        "compiled_policy_sha256": "c" * 64,
        "docker_default_sha256": "d" * 64,
        "elf_map_sha256": "e" * 64,
        "kernel_profile_sha256": "f" * 64,
    }
    values.update(updates)
    return values


def config_data(root: Path, **updates):
    fixture = root / "fixture"
    values = {
        "schema_version": 1,
        "service_config": str(root / "service.json"),
        "snapshot_root": str(fixture / "snapshot"),
        "profile": {
            "endpoint": "unix:///var/run/docker.sock",
            "docker_cli": "/usr/bin/docker",
            "image_id": "sha256:" + "1" * 64,
            "uid": 10001,
            "gid": 10001,
            "fixture_root": str(fixture),
            "apparmor_profile": "qm-worker-fixture",
            "seccomp_path": str(fixture / "policy.seccomp.json"),
        },
        "pins": pin_data(),
    }
    values.update(updates)
    return values


def private_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    path.chmod(0o600)
    return path


@pytest.fixture
def service_runtime_stub(tmp_path):
    fixture = tmp_path / "fixture"
    lake, artifacts = fixture / "lake", fixture / "artifacts"
    lake.mkdir(parents=True)
    artifacts.mkdir()
    (fixture / "snapshot").mkdir(mode=0o700)
    runtime = SimpleNamespace(
        actual_build="a" * 40,
        lock_sha256="f" * 64,
        postgres_dsn=object(),
        config=SimpleNamespace(
            expected_build="a" * 40,
            lake_root=lake,
            artifact_root=artifacts,
        ),
        preflight=lambda: {
            "schema_version": 1,
            "mode": "preflight",
            "actual_build": "a" * 40,
            "paper": True,
            "live": False,
            "capabilities": {"worker": "pending_containment", "model": "unavailable"},
        },
    )
    return runtime


def test_worker_runtime_exists_with_fixed_strict_config(tmp_path):
    module = api()
    raw = config_data(tmp_path)

    config = module.WorkerRuntimeConfig.model_validate(raw)

    assert config.schema_version == 1
    assert len(config.pins.model_dump()) == 22
    assert set(type(config.profile).model_fields) == {
        "endpoint",
        "docker_cli",
        "image_id",
        "uid",
        "gid",
        "fixture_root",
        "apparmor_profile",
        "seccomp_path",
    }


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"schema_version": True},
        {"unexpected": "private"},
        {"service_config": "relative.json"},
        {"snapshot_root": "relative"},
        {"profile": {"extra": "field"}},
        {"profile": {"apparmor_profile": None}},
        {"profile": {"endpoint": "tcp://unbounded.example:2375"}},
        {"profile": {"image_id": "latest"}},
        {"profile": {"gid": 1000}},
        {"pins": {"extra": "field"}},
        {"pins": {"source_commit": 7}},
    ],
)
def test_worker_config_rejects_wrong_schema_extra_and_relative_paths(tmp_path, change):
    module = api()
    raw = config_data(tmp_path)
    for key, value in change.items():
        if key == "profile" and isinstance(value, dict) and "extra" not in value:
            raw[key].update(value)
        elif key == "profile" and value == {"extra": "field"}:
            raw[key]["extra"] = value["extra"]
        elif key == "pins" and isinstance(value, dict) and "extra" not in value:
            raw[key].update(value)
        elif key == "pins" and value == {"extra": "field"}:
            raw[key]["extra"] = value["extra"]
        else:
            raw[key] = value

    with pytest.raises((ValidationError, ValueError)):
        module.WorkerRuntimeConfig.model_validate(raw)


def test_worker_config_requires_coherent_profile_and_pins(tmp_path):
    module = api()
    raw = config_data(tmp_path)
    raw["profile"]["image_id"] = "sha256:" + "9" * 64
    with pytest.raises((ValidationError, ValueError)):
        module.WorkerRuntimeConfig.model_validate(raw)

    raw = config_data(tmp_path)
    raw["profile"]["uid"] = 1000
    with pytest.raises((ValidationError, ValueError)):
        module.WorkerRuntimeConfig.model_validate(raw)


def test_worker_config_reader_reuses_private_reader_and_rejects_duplicate_keys(
    tmp_path, monkeypatch
):
    module = api()
    path = private_json(tmp_path / "worker.json", config_data(tmp_path))
    calls = []
    read_private = service_runtime._read_private

    def recording_reader(candidate, limit):
        calls.append((candidate, limit))
        return read_private(candidate, limit)

    monkeypatch.setattr(service_runtime, "_read_private", recording_reader)
    loaded = module.load_worker_config(path)
    assert loaded.service_config == str(tmp_path / "service.json")
    assert calls == [(path, 65536)]

    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
    duplicate.chmod(0o600)
    with pytest.raises(module.WorkerRuntimeRejected, match="configuration_invalid"):
        module.load_worker_config(duplicate)


def test_worker_runtime_rejects_paths_outside_its_fixture(tmp_path, service_runtime_stub):
    module = api()
    raw = config_data(tmp_path)
    raw["profile"]["fixture_root"] = str(tmp_path / "elsewhere")
    raw["snapshot_root"] = str(tmp_path / "elsewhere" / "snapshot")
    config = module.WorkerRuntimeConfig.model_validate(raw)

    with pytest.raises(module.WorkerRuntimeRejected, match="worker_configuration_invalid"):
        module.build_execution(config, service_runtime_stub)


def test_worker_runtime_rejects_source_pin_mismatch_before_profile_construction(
    tmp_path, service_runtime_stub, monkeypatch
):
    module = api()
    config = module.WorkerRuntimeConfig.model_validate(config_data(tmp_path))
    service_runtime_stub.actual_build = "b" * 40
    calls = []
    monkeypatch.setattr(module, "LinuxExecutionProfile", lambda **kwargs: calls.append(kwargs))

    with pytest.raises(module.WorkerRuntimeRejected, match="worker_configuration_invalid"):
        module.build_execution(config, service_runtime_stub)

    assert calls == []


def test_execution_uses_fixed_registered_profile_and_exact_pins(
    tmp_path, service_runtime_stub, monkeypatch
):
    module = api()
    config = module.WorkerRuntimeConfig.model_validate(config_data(tmp_path))
    calls = []

    class Profile:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            calls.append(("profile", kwargs))

    class Admission:
        def __init__(self, pins, snapshot_root, execution_profile):
            calls.append(("admission", pins, snapshot_root, execution_profile))

    class Execution:
        def __init__(self, profile, admission):
            calls.append(("execution", profile, admission))

    fixed = '{"profile_id":"registered-fixture"}'
    monkeypatch.setattr(module, "LinuxExecutionProfile", Profile)
    monkeypatch.setattr(module, "WorkerImageAdmission", Admission)
    monkeypatch.setattr(module, "LinuxWorkerExecution", Execution)
    monkeypatch.setattr(module, "registered_fixture_profile", lambda: fixed)

    execution = module.build_execution(config, service_runtime_stub)

    assert isinstance(execution, Execution)
    assert calls[0][0] == "profile"
    assert calls[0][1]["uid"] == calls[0][1]["gid"] == 10001
    assert calls[1][0] == "admission"
    assert calls[1][1] == module.WorkerAdmissionPins(**config.pins.model_dump())
    assert calls[1][2:] == (Path(config.snapshot_root), fixed)
    assert calls[2][0] == "execution"


def test_default_preflight_loads_service_runtime_without_worker_effects(
    tmp_path, service_runtime_stub, monkeypatch, capsys
):
    module = api()
    config_path = private_json(tmp_path / "worker.json", config_data(tmp_path))
    calls = []
    monkeypatch.setattr(
        service_runtime,
        "load_runtime",
        lambda path: calls.append(("load_runtime", path)) or service_runtime_stub,
    )

    def forbidden(*args, **kwargs):
        raise AssertionError("preflight crossed the worker activation boundary")

    monkeypatch.setattr(module, "build_execution", forbidden)
    monkeypatch.setattr(service_store, "PostgresJobStore", forbidden)
    monkeypatch.setattr(module, "LinuxExecutionProfile", forbidden)
    monkeypatch.setattr(module, "WorkerImageAdmission", forbidden)
    monkeypatch.setattr(module, "WorkerRunner", forbidden)
    monkeypatch.setattr(module, "WorkerDaemon", forbidden)
    monkeypatch.setattr(service_runtime, "build_app", forbidden)
    assert module.main(["--config", str(config_path)]) == 0

    receipt = json.loads(capsys.readouterr().out)
    assert calls == [("load_runtime", Path(config_data(tmp_path)["service_config"]))]
    assert receipt["actual_build"] == "a" * 40
    assert receipt["paper"] is True and receipt["live"] is False
    assert receipt["capabilities"]["worker"] == "activation_pending"
    assert (
        "model" not in receipt["capabilities"] or receipt["capabilities"]["model"] == "unavailable"
    )


def test_run_orders_live_admission_source_recheck_store_and_daemon(
    tmp_path, service_runtime_stub, monkeypatch
):
    module = api()
    config_path = private_json(tmp_path / "worker.json", config_data(tmp_path))
    events = []
    stop_event = Event()
    previous = object()

    def signal_bind(signum, handler):
        events.append(("signal", signum))
        return previous

    monkeypatch.setattr(module.signal, "signal", signal_bind)
    monkeypatch.setattr(module, "_event", lambda: stop_event)
    monkeypatch.setattr(
        service_runtime,
        "load_runtime",
        lambda path: (
            events.append(("load", path)),
            events.append(("initial_source",)),
            service_runtime_stub,
        )[-1],
    )
    monkeypatch.setattr(
        service_runtime,
        "_admit_runtime",
        lambda expected: (
            events.append(("source", expected))
            or (service_runtime_stub.actual_build, service_runtime_stub.lock_sha256)
        ),
    )

    class Execution:
        def runtime_fingerprint(self):
            events.append(("fingerprint",))
            return {"git_commit": "a" * 40}

    monkeypatch.setattr(
        module, "build_execution", lambda *args: events.append(("execution",)) or Execution()
    )

    class Store:
        def __init__(self, dsn, **kwargs):
            events.append(("store", dsn, kwargs))

    monkeypatch.setattr(service_store, "PostgresJobStore", Store)

    class Runner:
        def __init__(self, execution):
            events.append(("runner", execution))

    monkeypatch.setattr(module, "WorkerRunner", Runner)

    class Daemon:
        def __init__(self, **kwargs):
            events.append(("daemon", kwargs))

        def run(self, stop_event):
            events.append(("run", stop_event))

    monkeypatch.setattr(module, "WorkerDaemon", Daemon)

    assert module.main(["--config", str(config_path), "--run"]) == 0
    names = [item[0] for item in events]
    assert (
        names.index("load")
        < names.index("initial_source")
        < names.index("execution")
        < names.index("fingerprint")
    )
    assert names.index("fingerprint") < names.index("source") < names.index("store")
    assert names.index("store") < names.index("runner") < names.index("daemon") < names.index("run")
    assert events[names.index("store")][2] == {
        "lake_root": service_runtime_stub.config.lake_root,
        "artifact_root": service_runtime_stub.config.artifact_root,
        "schema": "qm_research",
    }
    assert events[names.index("run")][1] is stop_event
    assert events.count(("signal", signal.SIGINT)) == 2
    assert events.count(("signal", signal.SIGTERM)) == 2


@pytest.mark.parametrize("changed", ["actual_build", "lock_sha256"])
def test_run_refuses_source_drift_before_constructing_store(
    tmp_path, service_runtime_stub, monkeypatch, capsys, changed
):
    module = api()
    config_path = private_json(tmp_path / "worker.json", config_data(tmp_path))
    monkeypatch.setattr(service_runtime, "load_runtime", lambda path: service_runtime_stub)
    monkeypatch.setattr(
        service_runtime,
        "_admit_runtime",
        lambda expected: (
            "b" * 40 if changed == "actual_build" else service_runtime_stub.actual_build,
            "b" * 64 if changed == "lock_sha256" else service_runtime_stub.lock_sha256,
        ),
    )
    monkeypatch.setattr(
        module,
        "build_execution",
        lambda *args: SimpleNamespace(runtime_fingerprint=lambda: {"git_commit": "a" * 40}),
    )
    stores = []
    monkeypatch.setattr(
        service_store,
        "PostgresJobStore",
        lambda *args, **kwargs: stores.append(args),
    )

    assert module.main(["--config", str(config_path), "--run"]) != 0
    captured = capsys.readouterr()
    assert captured.err.strip() == "source_unqualified"
    assert str(tmp_path) not in captured.err and stores == []


def test_stop_during_live_admission_prevents_source_recheck_and_store(
    tmp_path, service_runtime_stub, monkeypatch
):
    module = api()
    config_path = private_json(tmp_path / "worker.json", config_data(tmp_path))
    stop = Event()
    monkeypatch.setattr(module, "_event", lambda: stop)
    monkeypatch.setattr(service_runtime, "load_runtime", lambda path: service_runtime_stub)
    monkeypatch.setattr(
        service_runtime,
        "_admit_runtime",
        lambda expected: (_ for _ in ()).throw(AssertionError("source recheck after stop")),
    )

    class Execution:
        def runtime_fingerprint(self):
            stop.set()
            return {"git_commit": "a" * 40}

    monkeypatch.setattr(module, "build_execution", lambda *args: Execution())
    monkeypatch.setattr(
        service_store,
        "PostgresJobStore",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("SQL after stop")),
    )

    assert module.main(["--config", str(config_path), "--run"]) == 0


def test_stop_during_argument_parsing_prevents_private_config_read(monkeypatch):
    module = api()
    stop = Event()
    monkeypatch.setattr(module, "_event", lambda: stop)

    class Parser:
        def __init__(self, **kwargs):
            pass

        def add_argument(self, *args, **kwargs):
            pass

        def parse_args(self, argv):
            stop.set()
            return SimpleNamespace(config=Path("/private/worker.json"), run=True)

    monkeypatch.setattr(module, "_Parser", Parser)
    monkeypatch.setattr(
        module,
        "load_worker_config",
        lambda path: (_ for _ in ()).throw(AssertionError("private config read after stop")),
    )

    assert module.main(["--config", "/private/worker.json", "--run"]) == 0


def test_stop_during_runner_construction_prevents_daemon_construction(
    tmp_path, service_runtime_stub, monkeypatch
):
    module = api()
    config_path = private_json(tmp_path / "worker.json", config_data(tmp_path))
    stop = Event()
    monkeypatch.setattr(module, "_event", lambda: stop)
    monkeypatch.setattr(service_runtime, "load_runtime", lambda path: service_runtime_stub)
    monkeypatch.setattr(
        service_runtime,
        "_admit_runtime",
        lambda expected: (service_runtime_stub.actual_build, service_runtime_stub.lock_sha256),
    )
    monkeypatch.setattr(
        module,
        "build_execution",
        lambda *args: SimpleNamespace(runtime_fingerprint=lambda: {"git_commit": "a" * 40}),
    )
    monkeypatch.setattr(service_store, "PostgresJobStore", lambda *args, **kwargs: object())

    class Runner:
        def __init__(self, execution):
            stop.set()

    monkeypatch.setattr(module, "WorkerRunner", Runner)
    monkeypatch.setattr(
        module,
        "WorkerDaemon",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("daemon after stop")),
    )

    assert module.main(["--config", str(config_path), "--run"]) == 0


@pytest.mark.parametrize("stage", ["source", "store"])
def test_stop_after_source_or_store_stage_prevents_later_startup(
    tmp_path, service_runtime_stub, monkeypatch, stage
):
    module = api()
    config_path = private_json(tmp_path / "worker.json", config_data(tmp_path))
    stop = Event()
    monkeypatch.setattr(module, "_event", lambda: stop)
    monkeypatch.setattr(service_runtime, "load_runtime", lambda path: service_runtime_stub)

    class Execution:
        def runtime_fingerprint(self):
            return {"git_commit": "a" * 40}

    monkeypatch.setattr(module, "build_execution", lambda *args: Execution())
    source_calls, store_calls, runner_calls = [], [], []

    def readmit(expected):
        source_calls.append(expected)
        if stage == "source":
            stop.set()
        return service_runtime_stub.actual_build, service_runtime_stub.lock_sha256

    monkeypatch.setattr(service_runtime, "_admit_runtime", readmit)

    class Store:
        def __init__(self, *args, **kwargs):
            store_calls.append(kwargs)
            if stage == "store":
                stop.set()

    monkeypatch.setattr(service_store, "PostgresJobStore", Store)

    class Runner:
        def __init__(self, execution):
            runner_calls.append(execution)

    monkeypatch.setattr(module, "WorkerRunner", Runner)
    monkeypatch.setattr(
        module,
        "WorkerDaemon",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("daemon after stop")),
    )

    assert module.main(["--config", str(config_path), "--run"]) == 0
    assert len(source_calls) == 1
    assert len(store_calls) == int(stage == "store")
    assert runner_calls == []


def test_worker_runtime_errors_are_fixed_and_signal_handlers_are_restored(
    tmp_path, monkeypatch, capsys
):
    module = api()
    config_path = private_json(tmp_path / "worker.json", config_data(tmp_path))
    handlers = {}

    def signal_change(signum, handler):
        previous = handlers.get(signum, signal.SIG_DFL)
        handlers[signum] = handler
        return previous

    monkeypatch.setattr(module.signal, "signal", signal_change)
    monkeypatch.setattr(
        service_runtime,
        "load_runtime",
        lambda path: (_ for _ in ()).throw(RuntimeError("private DSN and path")),
    )

    assert module.main(["--config", str(config_path), "--run"]) != 0
    captured = capsys.readouterr()
    assert captured.err.strip() == "worker_runtime_unavailable"
    assert "private" not in captured.err and "Traceback" not in captured.err
    assert handlers[signal.SIGINT] == signal.SIG_DFL
    assert handlers[signal.SIGTERM] == signal.SIG_DFL


def test_service_template_is_inert_and_has_explicit_shutdown_and_restart_controls():
    path = Path(__file__).parents[1] / "deploy" / "quantmesh-research-worker.service"
    assert path.is_file(), "worker service template missing"
    text = path.read_text(encoding="utf-8")
    assert "User=ubuntu" in text and "Group=ubuntu" in text
    expected_exec = (
        "ExecStart=/home/ubuntu/qm-research/runtime/venv/bin/python "
        "-B -m qm_research_agent.worker_runtime "
        "--config /home/ubuntu/qm-research/config/worker.json --run"
    )
    assert expected_exec in text
    assert "WorkingDirectory=/home/ubuntu/qm-research/releases/REVIEWED_MERGED_SHA/source" in text
    assert (
        "PYTHONPATH=/home/ubuntu/qm-research/releases/REVIEWED_MERGED_SHA/source/services/research_agent/src:/home/ubuntu/qm-research/releases/REVIEWED_MERGED_SHA/source/src"
        in text
    )
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in text
    assert "NoNewPrivileges=yes" in text
    assert "KillMode=control-group" in text and "TimeoutStopSec=20" in text
    assert "Restart=on-failure" in text and "RestartSec=5" in text
    assert "StartLimitIntervalSec=60" in text and "StartLimitBurst=3" in text
    assert "SupplementaryGroups=" not in text and "EnvironmentFile=" not in text
