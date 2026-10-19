"""Deterministic original-deadline expiry through admission and final GO write."""

import importlib
import io
import sys
from threading import Event
from types import SimpleNamespace

import pytest
from test_research_jobs import request_for
from test_worker_execution import configured
from test_worker_execution import small_fixture as small_fixture
from test_worker_execution import small_fixture_data as small_fixture_data

from quantmesh.research import job_runner, linux_owned, worker_execution


@pytest.mark.skipif(
    sys.platform != "linux", reason="Linux fake-Engine interface, not OCI qualification"
)
@pytest.mark.parametrize(
    "boundary",
    [
        "outer-fingerprint",
        "inner-fingerprint",
        "handoff",
        "prerequisites",
        "create-return",
        "first-inspect",
        "ready",
        "binding",
        "final-inspect",
    ],
)
def test_original_deadline_prevents_launch_after_admission_work(
    monkeypatch, small_fixture, boundary
):
    runner, store, lake, calls, _, _, attachment = configured(monkeypatch, small_fixture)
    store.submit("local", "deadline-" + boundary, request_for(lake, budget={"timeout_seconds": 1}))
    clock = [100.0]
    monkeypatch.setattr(job_runner.time, "monotonic", lambda: clock[0])
    sent = []
    original_send = attachment.send
    attachment.send = lambda value: (sent.append(value), original_send(value))[-1]
    admission = runner.execution.admission
    verify = admission.verify
    verification = []

    def measured(profile):
        result = verify(profile)
        verification.append(True)
        if boundary == ("outer-fingerprint" if len(verification) == 1 else "inner-fingerprint"):
            clock[0] = 102.0
        return result

    monkeypatch.setattr(admission, "verify", measured)
    handoff = worker_execution.handoff_worker_bundle

    def handed(*args):
        result = handoff(*args)
        if boundary == "handoff":
            clock[0] = 102.0
        return result

    monkeypatch.setattr(worker_execution, "handoff_worker_bundle", handed)
    prerequisites = linux_owned.LinuxExecutionProfile.prerequisites
    entries = []

    def prepared(profile):
        result = prerequisites(profile)
        entries.append(True)
        if boundary == "prerequisites" and len(entries) >= 3:
            clock[0] = 102.0
        return result

    monkeypatch.setattr(linux_owned.LinuxExecutionProfile, "prerequisites", prepared)
    invoke = linux_owned.LinuxExecutionProfile.invoke
    inspected = []

    def observed(profile, args):
        result = invoke(profile, args)
        if args[0] == "inspect":
            inspected.append(True)
        if (
            (boundary == "create-return" and args[0] == "create")
            or (boundary == "first-inspect" and args[0] == "inspect" and len(inspected) == 1)
            or (boundary == "final-inspect" and args[0] == "inspect" and len(inspected) == 2)
        ):
            clock[0] = 102.0
        return result

    monkeypatch.setattr(linux_owned.LinuxExecutionProfile, "invoke", observed)
    receive = attachment.receive

    def ready(timeout):
        result = receive(timeout)
        if boundary == "ready":
            clock[0] = 102.0
        return result

    attachment.receive = ready
    binding = admission.prepare_parent_binding

    def bound(*args):
        result = binding(*args)
        if boundary == "binding":
            clock[0] = 102.0
        return result

    monkeypatch.setattr(admission, "prepare_parent_binding", bound)
    result = runner.run_next_job(store, "deadline-owner", lake, store.artifact_root)
    assert result.state == "failed" and result.error_code == "timeout"
    deadline = importlib.import_module("quantmesh.research._launch_deadline")
    assert deadline._launch_deadline.get() is None
    assert not any(v.startswith("go") for v in sent)
    created = any(c[0] == "create" for c in calls)
    if boundary in {"outer-fingerprint", "inner-fingerprint", "handoff", "prerequisites"}:
        assert not created
    if created:
        assert any(c[0] == "rm" and c[-1] == "f" * 64 for c in calls)


def test_go_writer_thread_captures_original_deadline_before_actual_pipe_write(monkeypatch):
    assert importlib.util.find_spec("quantmesh.research._launch_deadline"), (
        "missing deadline context"
    )
    deadline = importlib.import_module("quantmesh.research._launch_deadline")
    clock = [100.0]
    monkeypatch.setattr(linux_owned.time, "monotonic", lambda: clock[0])
    transport = object.__new__(linux_owned._Transport)
    stream = io.BytesIO()
    transport.process = SimpleNamespace(stdin=stream, poll=lambda: None, kill=lambda: None)
    transport.overflow = Event()
    thread = linux_owned.threading.Thread

    def delayed(*args, **kwargs):
        clock[0] = 102.0
        return thread(*args, **kwargs)

    monkeypatch.setattr(linux_owned.threading, "Thread", delayed)
    token = deadline._launch_deadline.set(101.0)
    try:
        with pytest.raises(deadline.LaunchDeadlineExceeded):
            transport.send("go:fixture-only")
    finally:
        deadline._launch_deadline.reset(token)
    assert stream.getvalue() == b""
