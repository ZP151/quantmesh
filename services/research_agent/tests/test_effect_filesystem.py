"""Private syscall fixtures; native cgroup tamper proof is separate."""

import ctypes
import importlib.util

import pytest


def test_filesystem_guard_exists():
    assert importlib.util.find_spec("qm_research_agent.effect_filesystem") is not None


def fixture_guard(monkeypatch, fault=None):
    from qm_research_agent import effect_filesystem as guard

    events = []

    class Syscall:
        def __call__(self, number, *args):
            number = number.value
            if number == 444 and args[-1].value == 1:
                events.append("abi")
                return 2 if fault == "abi" else 6
            if number == 444:
                attr = ctypes.cast(args[0], ctypes.POINTER(ctypes.c_uint64))[0]
                events.append(("ruleset", attr))
                return -1 if fault == "create" else 81
            assert number == 446 and args[0].value == 81
            events.append("restrict")
            return -1 if fault == "restrict" else 0

    class Libc:
        syscall = Syscall()

        def prctl(self, option, value, *args):
            assert option == 38 and value == 1
            events.append("no_new_privileges")
            return -1 if fault == "privileges" else 0

    monkeypatch.setattr(guard.platform, "system", lambda: "Linux")
    monkeypatch.setattr(guard.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(guard.ctypes, "CDLL", lambda *args, **kwargs: Libc())
    monkeypatch.setattr(guard.os, "close", lambda fd: events.append(("close", fd)))
    return guard, events


def test_guard_denies_all_filesystem_mutation_before_return(monkeypatch):
    guard, events = fixture_guard(monkeypatch)
    guard.deny_filesystem_writes()
    mask = (1 << 1) | sum(1 << bit for bit in range(4, 15))
    assert events == ["abi", ("ruleset", mask), "no_new_privileges", "restrict", ("close", 81)]


@pytest.mark.parametrize("fault", ["abi", "create", "privileges", "restrict"])
def test_guard_fails_closed_and_releases_ruleset(monkeypatch, fault):
    guard, events = fixture_guard(monkeypatch, fault)
    with pytest.raises(RuntimeError, match="effect filesystem unavailable"):
        guard.deny_filesystem_writes()
    assert (("close", 81) in events) is (fault in {"privileges", "restrict"})
    if fault in {"abi", "create", "privileges"}:
        assert "restrict" not in events


def test_guard_rejects_unknown_platform_before_syscall(monkeypatch):
    guard, events = fixture_guard(monkeypatch)
    monkeypatch.setattr(guard.platform, "machine", lambda: "other")
    with pytest.raises(RuntimeError, match="effect filesystem unavailable"):
        guard.deny_filesystem_writes()
    assert events == []


def test_worker_guard_failure_prevents_private_configuration_read(monkeypatch):
    import io
    import json
    import os
    import runpy
    import sys

    from qm_research_agent import effect_filesystem as guard

    class DeniedByFixture(RuntimeError):
        pass

    def reject():
        raise DeniedByFixture

    class PrivateInput:
        @property
        def buffer(self):
            pytest.fail("private configuration was accessed before guard admission")

    class Output:
        buffer = io.BytesIO()

    class Libc:
        def prctl(self, *args):
            return 0

    monkeypatch.setenv("QM_EFFECT_SCOPE_REQUIRED", "1")
    monkeypatch.setenv("QM_EFFECT_OWNER_PID", str(os.getppid()))
    monkeypatch.setattr(guard, "deny_filesystem_writes", reject)
    monkeypatch.setattr(ctypes, "CDLL", lambda *args, **kwargs: Libc())
    monkeypatch.setattr(sys, "stdin", PrivateInput())
    output = Output()
    monkeypatch.setattr(sys, "stdout", output)
    with pytest.raises(SystemExit) as raised:
        runpy.run_module("qm_research_agent.effect_worker", run_name="__main__")
    assert raised.value.code == 1
    assert json.loads(output.buffer.getvalue()) == {
        "error": "model_effect_unavailable",
        "stage": "containment",
        "type": "DeniedByFixture",
    }
