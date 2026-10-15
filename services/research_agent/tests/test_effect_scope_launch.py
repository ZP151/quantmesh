"""Offline launch ordering and cleanup, not cgroup/native qualification."""

import json
import signal
import subprocess
import sys
from types import SimpleNamespace

import pytest
from qm_research_agent import bounded

from quantmesh.ai.gateway import ModelGateway
from quantmesh.ai.transport import ScriptedModelTransport
from quantmesh.ai.wire import ChatMessage, ModelRequest
from quantmesh.research.jobs import RunBudget

UNIT = "quantmesh-research-advisory.service"
pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux effect scope wiring")


def fixture_launch(tmp_path, monkeypatch, fault=None):
    events = []
    monkeypatch.setattr(bounded, "__file__", str(tmp_path / "src/pkg/bounded.py"))

    class Scope:
        def __init__(self, unit, budget):
            assert unit == UNIT and budget.cpu_limit == 1
            events.append("scope")
            if fault == "scope":
                raise RuntimeError("scope refused")

        def attach(self, process):
            assert process.pid == 43210
            events.append("attach")
            if fault == "attach":
                raise RuntimeError("attach refused")

        def close(self):
            events.append("close")
            if fault == "close":
                raise RuntimeError("cleanup refused")

    # Only the offline syscall boundary is replaced; production has no fake mode.
    monkeypatch.setitem(
        sys.modules, "qm_research_agent.linux_effect_scope", SimpleNamespace(EffectScope=Scope)
    )

    class Child:
        pid = 43210
        returncode = None
        stdin = stdout = None

        def communicate(self, payload, *, timeout):
            assert events[-1] == "attach" and payload and timeout == 5
            events.append("send")
            if fault in {"timeout", "close"}:
                raise subprocess.TimeoutExpired("fixture", timeout)
            self.returncode = 0
            return json.dumps(
                {
                    "response": {"model_name": "scripted-fixture", "content": "fixture"},
                    "scripted_seen": 1,
                }
            ).encode(), None

        def poll(self):
            return self.returncode

        def wait(self, timeout):
            self.returncode = -9
            events.append("wait")

    def spawn(*args, **kwargs):
        assert kwargs["env"]["QM_EFFECT_SCOPE_REQUIRED"] == "1"
        events.append("spawn")
        if fault == "spawn":
            raise OSError("spawn refused")
        return Child()

    monkeypatch.setattr(bounded.subprocess, "Popen", spawn)
    monkeypatch.setattr("os.killpg", lambda pid, sig: events.append(("kill", pid, sig)))
    return events


def invoke():
    gateway = ModelGateway(ScriptedModelTransport([]), model_name="scripted-fixture")
    return bounded.bounded_complete(
        gateway,
        ModelRequest(messages=[ChatMessage(role="user", content="public fixture")]),
        RunBudget(timeout_seconds=5),
        effect_scope_unit=UNIT,
    )


def test_effect_attaches_before_private_payload_and_always_closes_scope(tmp_path, monkeypatch):
    events = fixture_launch(tmp_path, monkeypatch)
    assert invoke().content == "fixture"
    assert events == ["scope", "spawn", "attach", "send", "close"]


def test_scope_admission_failure_prevents_child_creation(tmp_path, monkeypatch):
    events = fixture_launch(tmp_path, monkeypatch, "scope")
    with pytest.raises(RuntimeError, match="scope refused"):
        invoke()
    assert events == ["scope"]


def test_child_spawn_failure_closes_empty_owned_scope(tmp_path, monkeypatch):
    events = fixture_launch(tmp_path, monkeypatch, "spawn")
    with pytest.raises(OSError, match="spawn refused"):
        invoke()
    assert events == ["scope", "spawn", "close"]


@pytest.mark.parametrize("fault", ["attach", "timeout"])
def test_scope_and_direct_child_cleanup_on_failure(tmp_path, monkeypatch, fault):
    events = fixture_launch(tmp_path, monkeypatch, fault)
    with pytest.raises((RuntimeError, subprocess.TimeoutExpired)):
        invoke()
    assert "close" in events
    assert ("send" in events) is (fault == "timeout")
    assert events[-2:] == [("kill", 43210, signal.SIGKILL), "wait"]


def test_scope_cleanup_failure_still_reaps_owned_direct_child(tmp_path, monkeypatch):
    events = fixture_launch(tmp_path, monkeypatch, "close")
    with pytest.raises(RuntimeError, match="cleanup refused"):
        invoke()
    assert events == [
        "scope",
        "spawn",
        "attach",
        "send",
        "close",
        ("kill", 43210, signal.SIGKILL),
        "wait",
    ]
