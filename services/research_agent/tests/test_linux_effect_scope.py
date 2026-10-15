"""Offline admission and lifecycle tests for delegated Linux effect scopes."""

import inspect
import os
import subprocess
from types import SimpleNamespace

import pytest
from qm_research_agent import linux_effect_scope as scope_module

from quantmesh.research.jobs import RunBudget

UNIT = "quantmesh-research-advisory.service"
PROPERTIES = {
    "MainPID": "41",
    "KillMode": "control-group",
    "Delegate": "yes",
    "DelegateControllers": "cpu memory pids",
    "DelegateSubgroup": "controller",
    "ControlGroup": "/system.slice/quantmesh-research-advisory.service",
}


class FakeController:
    def __init__(self, unit, budget):
        self.unit = unit
        self.budget = budget
        self.calls = []
        self.scope_name = "effect-0123456789abcdef0123456789abcdef"

    def attach(self, process):
        self.calls.append(("attach", process))

    def snapshot(self):
        return {"scope": self.scope_name, "memory_max": self.budget.memory_mib * 1024**2}

    def close(self):
        self.calls.append(("close", self.scope_name))


def test_effect_scope_only_admits_supported_unit_and_one_cpu(monkeypatch):
    made = []

    def controller(unit, budget):
        made.append((unit, budget))
        return FakeController(unit, budget)

    monkeypatch.setattr(scope_module, "_LinuxEffectCgroup", controller)
    with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
        scope_module.EffectScope("other.service", RunBudget())
    with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
        scope_module.EffectScope(UNIT, RunBudget(cpu_limit=0.5))
    assert made == []

    scope = scope_module.EffectScope(UNIT, RunBudget(memory_mib=64))
    assert made == [(UNIT, scope.budget)]
    assert scope.snapshot()["memory_max"] == 64 * 1024**2


@pytest.mark.parametrize(
    "updates",
    [
        {"MainPID": "42"},
        {"KillMode": "process"},
        {"Delegate": "no"},
        {"DelegateControllers": "cpu memory"},
        {"DelegateSubgroup": "other"},
        {"ControlGroup": "/"},
        {"ControlGroup": "/system.slice/../escape"},
    ],
)
def test_manager_properties_fail_closed(updates):
    properties = {**PROPERTIES, **updates}
    with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
        scope_module._validate_manager_properties(UNIT, properties, current_pid=41)


def test_manager_properties_accept_exact_delegated_unit():
    assert (
        scope_module._validate_manager_properties(UNIT, PROPERTIES, current_pid=41)
        == PROPERTIES["ControlGroup"]
    )
    with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
        scope_module._validate_manager_properties(
            "quantmesh-advisory-qa-" + "A" * 32 + ".service",
            {**PROPERTIES, "MainPID": "41"},
            current_pid=41,
        )


def test_manager_requires_exact_delegate_controller_set():
    for controllers in ("cpu memory", "cpu memory pids io", "cpu cpu memory pids"):
        with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
            scope_module._validate_manager_properties(
                UNIT,
                {**PROPERTIES, "DelegateControllers": controllers},
                current_pid=41,
            )
    exact = {**PROPERTIES, "DelegateControllers": "pids cpu memory"}
    assert scope_module._validate_manager_properties(UNIT, exact, current_pid=41)


def test_systemctl_reads_delegate_controller_set(monkeypatch):
    seen = []

    def run(argv, **_kwargs):
        seen.extend(argv)
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "MainPID=41\nKillMode=control-group\nDelegate=yes\n"
                "DelegateControllers=cpu memory pids\nDelegateSubgroup=controller\n"
                "ControlGroup=/system.slice/quantmesh-research-advisory.service\n"
            ).encode("ascii"),
            stderr=b"",
        )

    monkeypatch.setattr(scope_module.subprocess, "run", run)
    properties = scope_module._run_systemctl(UNIT)
    assert properties["Delegate"] == "yes"
    assert properties["DelegateControllers"] == "cpu memory pids"
    assert "DelegateControllers" in next(
        arg.split("=", 1)[1] for arg in seen if arg.startswith("--property=")
    ).split(",")


def test_proc_membership_requires_exact_delegate_subgroup():
    expected = PROPERTIES["ControlGroup"] + "/controller"
    assert scope_module._parse_unified_cgroup("0::" + expected + "\n") == expected
    for raw in (
        "0::/system.slice/other.service/controller\n",
        "0::/system.slice/quantmesh-research-advisory.service\n",
    ):
        assert scope_module._parse_unified_cgroup(raw) != expected
    for raw in ("2:cpu:/legacy\n", "0::/system.slice/../escape\n", "0::/one\n0::/two\n"):
        with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
            scope_module._parse_unified_cgroup(raw)


def test_controller_admission_requires_cgroup2_and_all_controllers():
    assert scope_module._is_cgroup2_magic(scope_module.CGROUP2_SUPER_MAGIC)
    assert not scope_module._is_cgroup2_magic(0xEF53)
    with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
        scope_module._require_controllers("cpu memory\n")
    assert scope_module._require_controllers("cpu memory pids\n") == {"cpu", "memory", "pids"}


def test_delegated_root_must_be_empty_before_enabling_domain_controllers():
    scope_module._require_empty_delegated_root("\n")
    with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
        scope_module._require_empty_delegated_root("41\n")


def test_scope_kill_file_is_required_before_attach_and_is_not_written(tmp_path):
    kill_file = tmp_path / "cgroup.kill"
    kill_file.write_text("0", encoding="ascii")
    directory_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        scope_module._require_writable_kill_file(directory_fd)
        assert kill_file.read_text(encoding="ascii") == "0"
        kill_file.unlink()
        with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
            scope_module._require_writable_kill_file(directory_fd)
    finally:
        os.close(directory_fd)


def test_exact_limits_reject_cpu_fraction_and_readback_mismatch():
    budget = RunBudget(memory_mib=64)
    expected = {
        "memory.max": str(64 * 1024**2),
        "memory.swap.max": "0",
        "cpu.max": "100000 100000",
        "pids.max": "128",
    }
    scope_module._verify_scope_limits(expected, budget)
    for name, value in (
        ("memory.max", "max"),
        ("memory.swap.max", "1"),
        ("cpu.max", "50000 100000"),
        ("pids.max", "129"),
    ):
        with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
            scope_module._verify_scope_limits({**expected, name: value}, budget)


def test_counter_snapshot_accepts_kernel_extensions_but_only_bounded_integers():
    counters = scope_module._parse_counter_file(
        "usage_usec 12\nnr_bursts 2\nburst_usec 4\ncore_sched.force_idle_usec 1\n"
    )
    assert counters["nr_bursts"] == 2
    assert counters["core_sched.force_idle_usec"] == 1
    with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
        scope_module._parse_counter_file("usage_usec secret\n")


def test_effect_scope_attaches_only_a_direct_running_popen(monkeypatch):
    controller = FakeController(UNIT, RunBudget())
    monkeypatch.setattr(scope_module, "_LinuxEffectCgroup", lambda *_: controller)
    scope = scope_module.EffectScope(UNIT, RunBudget())
    process = SimpleNamespace(pid=73, poll=lambda: None)
    with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
        scope.attach(process)
    assert controller.calls == []

    class Child(subprocess.Popen):
        pass

    child = object.__new__(Child)
    child.returncode = None
    child.poll = lambda: None
    child.pid = 73
    scope.attach(child)
    assert controller.calls == [("attach", child)]


def test_close_targets_only_the_owned_scope_and_is_idempotent(monkeypatch):
    controllers = []

    def controller(unit, budget):
        value = FakeController(unit, budget)
        controllers.append(value)
        return value

    monkeypatch.setattr(scope_module, "_LinuxEffectCgroup", controller)
    first = scope_module.EffectScope(UNIT, RunBudget())
    scope_module.EffectScope(UNIT, RunBudget())
    first.close()
    first.close()
    assert controllers[0].calls == [("close", controllers[0].scope_name)]
    assert controllers[1].calls == []


def test_empty_cleanup_removes_only_the_exact_owned_directory(tmp_path):
    parent = tmp_path / "delegated"
    parent.mkdir()
    own_scope = parent / "effect-owned"
    sibling = parent / "controller"
    own_scope.mkdir()
    sibling.mkdir()
    parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    scope_fd = os.open(own_scope, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    held = scope_module._HeldPath([parent_fd, scope_fd], ["effect-owned"])
    scope_module._remove_empty_scope(held)
    assert not own_scope.exists()
    assert sibling.is_dir()
    os.close(scope_fd)
    os.close(parent_fd)


def test_cleanup_rejects_a_replaced_scope_name(tmp_path):
    parent = tmp_path / "delegated"
    parent.mkdir()
    own_scope = parent / "effect-owned"
    moved_scope = parent / "effect-original"
    own_scope.mkdir()
    parent_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
    scope_fd = os.open(own_scope, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    held = scope_module._HeldPath([parent_fd, scope_fd], ["effect-owned"])
    own_scope.rename(moved_scope)
    own_scope.mkdir()
    with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
        scope_module._remove_empty_scope(held)
    assert own_scope.is_dir()
    assert moved_scope.is_dir()
    os.close(scope_fd)
    os.close(parent_fd)


def test_scope_directory_open_failure_removes_just_created_directory(tmp_path, monkeypatch):
    root_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    root = scope_module._HeldPath([root_fd], ["delegated"])
    name = "effect-" + "1" * 32
    real_open_directory = scope_module._open_directory

    def fail_leaf_open(path, *, parent_fd=None):
        if path == name:
            raise scope_module.EffectScopeRejected()
        return real_open_directory(path, parent_fd=parent_fd)

    monkeypatch.setattr(scope_module, "_open_directory", fail_leaf_open)
    try:
        with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
            scope_module._create_scope_directory(root, name)
        assert not (tmp_path / name).exists()
    finally:
        os.close(root_fd)


def test_scope_identity_failure_closes_fd_and_removes_exact_directory(tmp_path, monkeypatch):
    root_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    root = scope_module._HeldPath([root_fd], ["delegated"])
    name = "effect-" + "2" * 32
    real_open_directory = scope_module._open_directory
    real_stat = scope_module.os.stat
    opened_fds = []
    named_calls = 0

    def track_open(path, *, parent_fd=None):
        fd = real_open_directory(path, parent_fd=parent_fd)
        if path == name:
            opened_fds.append(fd)
        return fd

    def lie_once(path, *args, **kwargs):
        nonlocal named_calls
        result = real_stat(path, *args, **kwargs)
        if path == name and kwargs.get("dir_fd") == root_fd:
            named_calls += 1
            if named_calls == 2:
                return result.__class__(
                    (
                        result.st_mode,
                        result.st_ino + 1,
                        result.st_dev,
                        result.st_nlink,
                        result.st_uid,
                        result.st_gid,
                        result.st_size,
                        result.st_atime,
                        result.st_mtime,
                        result.st_ctime,
                    )
                )
        return result

    monkeypatch.setattr(scope_module, "_open_directory", track_open)
    monkeypatch.setattr(scope_module.os, "stat", lie_once)
    try:
        with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
            scope_module._create_scope_directory(root, name)
        assert not (tmp_path / name).exists()
        assert len(opened_fds) == 1
        with pytest.raises(OSError):
            os.fstat(opened_fds[0])
    finally:
        os.close(root_fd)


def test_scope_initial_identity_failure_does_not_remove_replacement(tmp_path, monkeypatch):
    root_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    root = scope_module._HeldPath([root_fd], ["delegated"])
    name = "effect-" + "3" * 32
    created_path = tmp_path / "created-before-stat-failure"
    real_stat = scope_module.os.stat
    real_open = scope_module._open_directory
    opened = []
    injected = False

    def fail_identity_stat(path, *args, **kwargs):
        nonlocal injected
        if path == name and kwargs.get("dir_fd") == root_fd and not injected:
            injected = True
            (tmp_path / name).rename(created_path)
            (tmp_path / name).mkdir()
            raise OSError("injected initial identity failure")
        return real_stat(path, *args, **kwargs)

    def track_open(path, *, parent_fd=None):
        fd = real_open(path, parent_fd=parent_fd)
        if path == name:
            opened.append(fd)
        return fd

    monkeypatch.setattr(scope_module.os, "stat", fail_identity_stat)
    monkeypatch.setattr(scope_module, "_open_directory", track_open)
    try:
        with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
            scope_module._create_scope_directory(root, name)
        assert created_path.is_dir()
        assert (tmp_path / name).is_dir()
        assert opened == []
    finally:
        os.close(root_fd)


@pytest.mark.parametrize("failure_stage", ["kill", "events", "timeout", "rmdir"])
def test_terminal_close_failure_releases_all_owned_descriptors(
    tmp_path, monkeypatch, failure_stage
):
    root_path = tmp_path / "delegated"
    root_path.mkdir()
    leaf_path = root_path / "effect-owned"
    leaf_path.mkdir()
    root_fd = os.open(root_path, os.O_RDONLY | os.O_DIRECTORY)
    leaf_fd = os.open(leaf_path, os.O_RDONLY | os.O_DIRECTORY)
    pidfd = os.open(tmp_path / "pidfd", os.O_CREAT | os.O_RDONLY, 0o600)
    root = scope_module._HeldPath([root_fd], ["delegated"])
    held = scope_module._HeldPath([root_fd, leaf_fd], ["delegated", "effect-owned"])
    scope = scope_module._Scope(
        held,
        "effect-owned",
        "/service/effect-owned",
        {},
        attached_pid=41,
        attached_start_time=123,
        pidfd=pidfd,
    )
    controller = object.__new__(scope_module._LinuxEffectCgroup)
    controller._scope = scope
    controller._root = root
    controller._close_failed = False
    monkeypatch.setattr(scope_module, "_ensure_held_name", lambda _held: None)

    def fail_write(_fd, filename, _value):
        if failure_stage == "kill" and filename == "cgroup.kill":
            raise scope_module.EffectScopeRejected()

    def read(_fd, filename, *_args):
        if failure_stage == "events" and filename == "cgroup.events":
            raise scope_module.EffectScopeRejected()
        if failure_stage == "timeout" and filename == "cgroup.events":
            return "populated 1\n"
        return "populated 0\n"

    def remove(_held):
        if failure_stage == "rmdir":
            raise scope_module.EffectScopeRejected()

    monkeypatch.setattr(scope_module, "_write_member", fail_write)
    monkeypatch.setattr(scope_module, "_read_member", read)
    monkeypatch.setattr(scope_module, "_remove_empty_scope", remove)
    monkeypatch.setattr(scope_module, "_CLOSE_RETRIES", 1, raising=False)
    if failure_stage == "timeout":
        monkeypatch.setattr(scope_module, "_CLOSE_TIMEOUT_SECONDS", 0)
    with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
        controller.close()
    for descriptor in (root_fd, leaf_fd, pidfd):
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_close_retries_transient_kill_failure_before_releasing_fds(tmp_path, monkeypatch):
    root_path = tmp_path / "delegated"
    root_path.mkdir()
    leaf_path = root_path / "effect-owned"
    leaf_path.mkdir()
    root_fd = os.open(root_path, os.O_RDONLY | os.O_DIRECTORY)
    leaf_fd = os.open(leaf_path, os.O_RDONLY | os.O_DIRECTORY)
    root = scope_module._HeldPath([root_fd], ["delegated"])
    held = scope_module._HeldPath([root_fd, leaf_fd], ["delegated", "effect-owned"])
    scope = scope_module._Scope(held, "effect-owned", "/service/effect-owned", {}, attached_pid=41)
    controller = object.__new__(scope_module._LinuxEffectCgroup)
    controller._scope = scope
    controller._root = root
    controller._close_failed = False
    monkeypatch.setattr(scope_module, "_ensure_held_name", lambda _held: None)
    write_calls = 0

    def fail_once(_fd, filename, _value):
        nonlocal write_calls
        if filename == "cgroup.kill":
            write_calls += 1
            if write_calls == 1:
                raise scope_module.EffectScopeRejected()

    monkeypatch.setattr(scope_module, "_write_member", fail_once)
    monkeypatch.setattr(scope_module, "_read_member", lambda *_args: "populated 0\n")
    monkeypatch.setattr(scope_module, "_remove_empty_scope", lambda _held: None)
    controller.close()
    assert write_calls == 2
    assert scope.closed
    for descriptor in (root_fd, leaf_fd):
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_snapshot_is_sanitized_and_api_has_no_payload_or_qualification_switch(monkeypatch):
    controller = FakeController(UNIT, RunBudget())
    monkeypatch.setattr(scope_module, "_LinuxEffectCgroup", lambda *_: controller)
    scope = scope_module.EffectScope(UNIT, RunBudget())
    snapshot = scope.snapshot()
    assert set(snapshot) == {"scope", "memory_max"}
    assert "api_key" not in repr(snapshot).lower()
    assert "payload" not in dir(scope)
    assert tuple(inspect.signature(scope_module.EffectScope).parameters) == ("unit", "budget")


def test_proc_stat_parser_retains_parent_and_start_time():
    fields = [
        "S",
        "41",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "0",
        "12345",
    ]
    raw = "73 (child (with spaces)) " + " ".join(fields)
    assert scope_module._parse_proc_stat(raw) == (41, 12345)
    with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
        scope_module._parse_proc_stat("73 (bad) S 41")


def test_attach_identity_requires_same_direct_child_and_start_time():
    identity = (41, 12345)
    assert scope_module._validate_owned_child_identity(identity, identity, 41) == 12345
    for before, after in (
        ((42, 12345), (42, 12345)),
        ((41, 12345), (41, 12346)),
        ((41, 12345), (42, 12345)),
    ):
        with pytest.raises(scope_module.EffectScopeRejected, match="effect scope unavailable"):
            scope_module._validate_owned_child_identity(before, after, 41)
