"""Command tests are not native OCI qualification."""

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from quantmesh.research import linux_bootstrap as bootstrap
from quantmesh.research import linux_owned as owned
from quantmesh.research.jobs import RunBudget


@pytest.fixture
def profile(tmp_path):
    cli = tmp_path / "docker"
    cli.write_text("fixture")
    root = tmp_path / "fixtures"
    root.mkdir()
    return owned.LinuxExecutionProfile(
        endpoint="unix:///var/run/docker.sock",
        docker_cli=cli,
        image_id="sha256:" + "a" * 64,
        # A real POSIX ownership check stays enabled in these fake-engine tests.
        # Non-root CI cannot assign an unrelated hardcoded container identity.
        uid=(os.getuid() or 10001) if os.name == "posix" else 10001,
        gid=(os.getgid() or 10001) if os.name == "posix" else 10001,
        fixture_root=root,
    )


@pytest.fixture
def paths(profile):
    inputs = profile.fixture_root / "inputs"
    inputs.mkdir()
    return inputs, profile.fixture_root / "attempt"


class Attach:
    def __init__(self, ready):
        self.ready = ready
        self.sent = []
        self.stopped = False

    def receive(self, timeout):
        return self.ready

    def send(self, value):
        self.sent.append(value)

    def close(self):
        self.stopped = True


@pytest.fixture
def engine(monkeypatch, profile):
    calls = []
    state = {"Running": True, "ExitCode": 0, "OOMKilled": False}
    nonce = []
    attach = Attach(
        {
            "event": "ready",
            "bootstrap_sha256": owned.bootstrap_digest(),
            "limits": {
                "memory.max": "2147483648",
                "memory.swap.max": "0",
                "cpu.max": "100000 100000",
                "pids.max": "128",
            },
        }
    )

    def invoke(self, args):
        calls.append(args)
        if args[0] == "info":
            return json.dumps({"OSType": "linux", "CgroupVersion": "2", "ID": "fixture"})
        if args[:2] == ["image", "inspect"]:
            return json.dumps([{"Id": profile.image_id, "Os": "linux"}])
        if args[0] == "create":
            nonce.append(args[args.index("--label") + 1].split("=", 1)[1])
            return "b" * 64
        if args[0] == "inspect":
            return json.dumps(
                [
                    {
                        "Id": "b" * 64,
                        "Image": profile.image_id,
                        "Config": {"Labels": {owned.OWNER_LABEL: nonce[0]}},
                        "State": state,
                    }
                ]
            )
        return ""

    monkeypatch.setattr(owned.LinuxExecutionProfile, "invoke", invoke)
    monkeypatch.setattr(owned, "_attach", lambda *a: attach)
    return calls, state, nonce, attach


def test_fixed_creation_and_gated_start(profile, paths, engine):
    calls, state, _, attach = engine
    process = owned.LinuxOwnedProcess(
        profile, ["/usr/local/bin/python3", "-V"], RunBudget(), *paths
    )
    create = next(a for a in calls if a[0] == "create")
    for flag in [
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=128",
        "--cpus=1",
        "--memory=2048m",
        "--memory-swap=2048m",
        "--restart=no",
    ]:
        assert flag in create
    assert create.count("--mount") == 2
    assert create[create.index(profile.image_id) + 1] == "-B"
    assert create[create.index("--user") + 1] == f"{profile.uid}:{profile.gid}"
    assert "readonly" in create[create.index("--mount") + 1]
    assert attach.sent == ["go"]
    process.pulse()
    assert attach.sent[-1] == "pulse"
    assert process.poll() is None
    state.update(Running=False, ExitCode=7)
    assert process.poll() == 7
    process.close()
    assert calls[-1] == ["rm", "--force", "b" * 64]


def test_explicit_bytecode_env_image_admission(profile, paths, engine, monkeypatch):
    original = profile.invoke

    def with_bytecode(self, args):
        result = original(args)
        if args[:2] == ["image", "inspect"]:
            doc = json.loads(result)
            doc[0]["Config"] = {"Env": ["PYTHONDONTWRITEBYTECODE=1"]}
            return json.dumps(doc)
        return result

    monkeypatch.setattr(owned.LinuxExecutionProfile, "invoke", with_bytecode)
    process = owned.LinuxOwnedProcess(profile, ["/bin/true"], RunBudget(), *paths)
    process.close()


@pytest.mark.parametrize("entry", ["owner", "native_sibling"])
def test_qualification_python_launch_disables_bytecode(profile, tmp_path, monkeypatch, entry):
    module = _qualification_module()
    seen = []

    class Stop(RuntimeError):
        pass

    def capture(profile, command, *args):
        seen.append(command)
        raise Stop

    monkeypatch.setattr(module, "LinuxOwnedProcess", capture)
    output = profile.fixture_root / "qualification"
    output.mkdir()
    with pytest.raises(Stop):
        if entry == "owner":
            monkeypatch.setattr(module, "load_profile", lambda path: profile)
            module._owner(tmp_path / "profile", output)
        else:
            module.native_checks(profile, output, tmp_path / "profile", {})
    assert seen[0][1] == "-B"


@pytest.mark.skipif(sys.platform != "linux", reason="real standalone child env check")
def test_standalone_child_has_clean_bytecode_environment(tmp_path):
    (tmp_path / "local_fixture.py").write_text("value=1\n")
    workload = (
        "import os,sys,local_fixture;assert sys.dont_write_bytecode;"
        "assert os.environ.get('PYTHONDONTWRITEBYTECODE')=='1'"
    )
    command = [sys.executable, "-B", "-c", workload]
    script = (
        "import sys;from pathlib import Path;"
        "from quantmesh.research.linux_bootstrap import supervise;"
        f"sys.exit(supervise({command!r},Path({str(tmp_path)!r}),3))"
    )
    process = subprocess.Popen([sys.executable, "-B", "-c", script], stdin=subprocess.PIPE)
    try:
        assert process.wait(timeout=5) == 0
        assert not (tmp_path / "__pycache__").exists()
    finally:
        process.stdin.close()


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() == 0,
    reason="requires the real non-root POSIX ownership boundary",
)
def test_unassignable_output_owner_refuses_before_container_create(profile, paths, engine):
    from dataclasses import replace

    calls, _, _, _ = engine
    foreign = replace(profile, uid=profile.uid + 1)
    with pytest.raises(PermissionError):
        owned.LinuxOwnedProcess(foreign, ["/bin/true"], RunBudget(), *paths)
    assert not any(args[0] == "create" for args in calls)


@pytest.mark.parametrize(
    "field,value",
    [
        ("image_id", "python:latest"),
        ("endpoint", "tcp://localhost:2375"),
        ("endpoint", "ssh://root@server"),
        ("uid", 0),
        ("gid", 0),
    ],
)
def test_profile_refuses_unsafe_identity(profile, field, value):
    from dataclasses import replace

    with pytest.raises(owned.LinuxContainmentError):
        replace(profile, **{field: value})


def test_clean_cli_environment(profile, monkeypatch):
    monkeypatch.setenv("DOCKER_HOST", "tcp://secret")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "secret")
    env = profile.cli_environment()
    assert "DOCKER_HOST" not in env and "AWS_SECRET_ACCESS_KEY" not in env
    assert "HOME" not in env and "DOCKER_CONTEXT" not in env
    assert profile.argv(["info"])[1:3] == ["--host", profile.endpoint]


def test_creation_failure_never_guesses_container(profile, paths, engine, monkeypatch):
    calls, _, _, _ = engine
    original = profile.invoke

    def fail(self, args):
        if args[0] == "create":
            raise owned.LinuxContainmentError("engine_command_failed")
        return original(args)

    monkeypatch.setattr(owned.LinuxExecutionProfile, "invoke", fail)
    with pytest.raises(owned.LinuxContainmentError):
        owned.LinuxOwnedProcess(profile, ["/bin/true"], RunBudget(), *paths)
    assert not any(a[0] == "rm" for a in calls)


def test_output_limit_is_failure(profile, paths, engine, monkeypatch):
    process = owned.LinuxOwnedProcess(profile, ["/bin/true"], RunBudget(), *paths)
    monkeypatch.setattr(owned, "output_size", lambda p: owned.MAX_OUTPUT_BYTES + 1)
    assert process.poll() == 125
    assert process.evidence["controller_failure"] == "output_limit"


@pytest.mark.parametrize("unsafe", ["oversized", "symlink"])
def test_terminal_output_cannot_succeed(profile, paths, engine, monkeypatch, unsafe):
    process = owned.LinuxOwnedProcess(profile, ["/bin/true"], RunBudget(), *paths)
    engine[1].update(Running=False, ExitCode=0)

    def output_size(path):
        if unsafe == "symlink":
            raise ValueError("unsafe_output")
        return owned.MAX_OUTPUT_BYTES + 1

    monkeypatch.setattr(owned, "output_size", output_size)
    assert process.poll() == 125
    process.close()


def test_transient_cleanup_can_retry_exact_ownership(profile, paths, engine, monkeypatch):
    process = owned.LinuxOwnedProcess(profile, ["/bin/true"], RunBudget(), *paths)
    original = profile.invoke
    failures = [True]

    def remove(self, args):
        if args[0] == "rm" and failures.pop():
            raise owned.LinuxContainmentError("engine_unavailable")
        return original(args)

    monkeypatch.setattr(owned.LinuxExecutionProfile, "invoke", remove)
    with pytest.raises(owned.LinuxContainmentError):
        process.close()
    assert process.closed is False
    failures.append(False)
    process.close()
    assert process.closed is True
    assert engine[0][-2:] == [["inspect", "b" * 64], ["rm", "--force", "b" * 64]]


def test_hung_pulse_write_has_deadline(monkeypatch):
    import threading

    transport = object.__new__(owned._Transport)
    transport.overflow = threading.Event()

    class Stdin:
        def write(self, value):
            time.sleep(0.3)

        def flush(self):
            pass

    class Process:
        stdin = Stdin()

        def poll(self):
            return None

        def kill(self):
            pass

    transport.process = Process()
    monkeypatch.setattr(owned, "CONTROL_WRITE_SECONDS", 0.05, raising=False)
    start = time.monotonic()
    with pytest.raises(owned.LinuxContainmentError):
        transport.send("pulse")
    assert time.monotonic() - start < 0.2


def _qualification_module():
    spec = importlib.util.spec_from_file_location("qualify", "tools/qualify_linux_worker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_native_timeout_requires_actual_container_exit(monkeypatch):
    module = _qualification_module()

    class Worker:
        def poll(self):
            return 124  # Host rescue is not a native PID1 timeout certificate.

        def _inspect(self):
            return {"State": {"Running": True, "ExitCode": 0, "OOMKilled": False}}

        def pulse(self):
            pass

    ticks = iter([0, 1, 26])
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(module.time, "sleep", lambda s: None)
    with pytest.raises(owned.LinuxContainmentError, match="witness_timeout"):
        module._wait(Worker(), Worker())


def test_native_hung_attachment_is_required():
    assert "hung_attach" in _qualification_module().REQUIRED


@pytest.mark.parametrize("lines,buffer", [(["go", "pulse"], b""), (["go"], b"pul")])
def test_pid1_go_preserves_coalesced_and_fragmented_pulses(tmp_path, monkeypatch, lines, buffer):
    # Protocol unit only: mocked PID1/cgroup admission is never native evidence.
    for key, value in {
        "memory.max": "67108864",
        "memory.swap.max": "0",
        "cpu.max": "100000 100000",
        "pids.max": "128",
    }.items():
        (tmp_path / key).write_text(value)
    monkeypatch.setattr(bootstrap, "CGROUP", tmp_path)
    monkeypatch.setattr(bootstrap.os, "getpid", lambda: 1)
    monkeypatch.setattr(bootstrap.os, "getuid", lambda: 10001, raising=False)
    monkeypatch.setattr(bootstrap.sys, "platform", "linux")
    monkeypatch.setattr(bootstrap.sys, "argv", ["bootstrap", "64", "20", "/bin/true"])

    class Control:
        def __init__(self):
            self.buffer = buffer

        def read(self, timeout):
            return lines

        def close(self):
            pass

    observed = []
    monkeypatch.setattr(bootstrap, "Control", Control)

    def supervise(*args, **kwargs):
        observed.append(kwargs.get("control"))
        return 0

    monkeypatch.setattr(bootstrap, "supervise", supervise)
    assert bootstrap.main() == 0
    assert observed and observed[0].buffer == buffer


def test_qualification_missing_profile_is_nonzero(tmp_path):
    spec = importlib.util.spec_from_file_location("qualify", "tools/qualify_linux_worker.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    output = tmp_path / "evidence"
    assert module.main(["--profile", str(tmp_path / "absent.json"), "--output", str(output)]) != 0
    result = json.loads((output / "qualification.json").read_text())
    assert result["status"] == "pending"
    assert result["native_qualified"] is False


@pytest.mark.parametrize(
    "property,value", [("Volumes", {"/secret": {}}), ("Env", ["AWS_SECRET_ACCESS_KEY=secret"])]
)
def test_unsafe_image_refused(profile, paths, engine, monkeypatch, property, value):
    original = profile.invoke

    def changed(self, args):
        result = original(args)
        if args[:2] == ["image", "inspect"]:
            doc = json.loads(result)
            doc[0]["Config"] = {property: value}
            return json.dumps(doc)
        return result

    monkeypatch.setattr(owned.LinuxExecutionProfile, "invoke", changed)
    with pytest.raises(owned.LinuxContainmentError):
        owned.LinuxOwnedProcess(profile, ["/bin/true"], RunBudget(), *paths)


@pytest.mark.parametrize("reason", ["engine", "image", "fractional", "missing", "overlap"])
def test_refusal_before_create(profile, paths, engine, monkeypatch, reason):
    calls, _, _, _ = engine
    budget = RunBudget()
    inputs, output = paths
    original = profile.invoke
    if reason in {"engine", "image"}:

        def broken(self, args):
            if args[0] == ("info" if reason == "engine" else "image"):
                raise owned.LinuxContainmentError("prerequisite_unavailable")
            return original(args)

        monkeypatch.setattr(owned.LinuxExecutionProfile, "invoke", broken)
    elif reason == "fractional":
        budget = RunBudget(cpu_limit=0.5)
    elif reason == "missing":
        inputs = inputs / "missing"
    else:
        output = inputs / "attempt"
    with pytest.raises(owned.LinuxContainmentError):
        owned.LinuxOwnedProcess(profile, ["/bin/true"], budget, inputs, output)
    assert not any(a[0] == "create" for a in calls)


@pytest.mark.parametrize("failure", ["cgroup", "digest", "attach", "nonce", "id"])
def test_admission_and_owned_cleanup(profile, paths, engine, monkeypatch, failure):
    calls, _, nonce, attach = engine
    if failure == "cgroup":
        attach.ready["limits"]["memory.max"] = "max"
    elif failure == "digest":
        attach.ready["bootstrap_sha256"] = "0" * 64
    elif failure == "attach":

        def fail(*args):
            raise owned.LinuxContainmentError("attach_failed")

        monkeypatch.setattr(owned, "_attach", fail)
    else:
        original = profile.invoke

        def changed(self, args):
            result = original(args)
            if args[0] == "inspect":
                doc = json.loads(result)
                if failure == "nonce":
                    doc[0]["Config"]["Labels"][owned.OWNER_LABEL] = "other"
                else:
                    doc[0]["Id"] = "c" * 64
                return json.dumps(doc)
            return result

        monkeypatch.setattr(owned.LinuxExecutionProfile, "invoke", changed)
    with pytest.raises(owned.LinuxContainmentError):
        owned.LinuxOwnedProcess(profile, ["/bin/true"], RunBudget(), *paths)
    assert "go" not in attach.sent
    assert any(a[0] == "rm" for a in calls) == (failure not in {"nonce", "id"})


def test_actual_oom_is_failure(profile, paths, engine):
    _, state, _, _ = engine
    process = owned.LinuxOwnedProcess(profile, ["/bin/true"], RunBudget(), *paths)
    state.update(Running=False, ExitCode=0, OOMKilled=True)
    assert process.poll() != 0
    assert process.evidence["oom_killed"] is True
    process.close()


def test_existing_output_and_symlink_refused(profile, paths, engine):
    inputs, output = paths
    output.mkdir()
    with pytest.raises(owned.LinuxContainmentError):
        owned.LinuxOwnedProcess(profile, ["/bin/true"], RunBudget(), inputs, output)
    link = profile.fixture_root / "link"
    try:
        link.symlink_to(inputs, target_is_directory=True)
    except OSError:
        pytest.skip("host cannot create symlinks; native mount witness remains required")
    with pytest.raises(owned.LinuxContainmentError):
        owned.LinuxOwnedProcess(profile, ["/bin/true"], RunBudget(), link, output / "new")


@pytest.mark.parametrize(
    "key,bad",
    [
        ("memory.max", "max"),
        ("memory.swap.max", "max"),
        ("cpu.max", "max 100000"),
        ("pids.max", "max"),
    ],
)
def test_cgroup_admission(key, bad):
    values = {
        "memory.max": "67108864",
        "memory.swap.max": "0",
        "cpu.max": "100000 100000",
        "pids.max": "128",
    }
    bootstrap.verify_limits(values, 64)
    values[key] = bad
    with pytest.raises(ValueError):
        bootstrap.verify_limits(values, 64)


@pytest.mark.skipif(sys.platform != "linux", reason="standalone Linux controller only")
@pytest.mark.parametrize(
    "mode,expected", [("normal", 0), ("nonzero", 7), ("eof", 124), ("silent", 124), ("output", 125)]
)
def test_standalone_controller(tmp_path, mode, expected):
    # No fake cgroups: test the controller loop separately from native admission/PID1.
    workload = {
        "normal": "pass",
        "nonzero": "raise SystemExit(7)",
        "eof": "import time;time.sleep(20)",
        "silent": "import time;time.sleep(20)",
        "output": 'print("x"*200000)',
    }[mode]
    command = [sys.executable, "-B", "-c", workload]
    script = (
        "import sys;from pathlib import Path;"
        "from quantmesh.research.linux_bootstrap import supervise;"
        f"sys.exit(supervise({command!r},"
        f"Path({str(tmp_path)!r}),2,watchdog_seconds=0.3,max_output_bytes=100000))"
    )
    p = subprocess.Popen(
        [sys.executable, "-B", "-c", script],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if mode == "eof":
        p.stdin.close()
        p.stdin = None
    try:
        assert p.wait(timeout=5) == expected
    finally:
        if p.stdin is not None:
            p.stdin.close()
        p.stdout.close()
        p.stderr.close()


@pytest.mark.skipif(sys.platform != "linux", reason="standalone Linux controller only")
def test_standalone_reparented_descendant_and_sibling(tmp_path):
    sibling = subprocess.Popen([sys.executable, "-B", "-c", "import time;time.sleep(20)"])
    workload = (
        "import os,time;from pathlib import Path;pid=os.fork();"
        "Path('descendant.pid').write_text(str(pid)) if pid else time.sleep(20)"
    )
    script = (
        "import sys;from pathlib import Path;"
        "from quantmesh.research.linux_bootstrap import supervise;"
        f"sys.exit(supervise({[sys.executable, '-B', '-c', workload]!r},Path({str(tmp_path)!r}),2))"
    )
    controller = subprocess.Popen([sys.executable, "-B", "-c", script], stdin=subprocess.PIPE)
    try:
        assert controller.wait(timeout=5) == 0
        pid = int((tmp_path / "descendant.pid").read_text())
        status = Path(f"/proc/{pid}/stat")
        assert not status.exists() or status.read_text().split()[2] == "Z"
        assert sibling.poll() is None
    finally:
        controller.stdin.close()
        sibling.kill()
        sibling.wait(timeout=5)
