"""Joint R1 correction: modeled owned child; no SDK or actual research execution."""

import threading
from types import SimpleNamespace

import pytest
from test_ivv_transaction_recovery_product import reviewed_recovery_registration

from quantmesh.research import ivv_runtime as runtime
from quantmesh.research import native_daily_real as daily


@pytest.mark.parametrize("failures", [1, 4])
def test_calculation_cleanup_failure_retains_exact_owner_until_terminal_cleanup(
    tmp_path, monkeypatch, failures
):
    gate, store, root, key, kwargs = reviewed_recovery_registration(tmp_path, monkeypatch)
    registered = gate.register_ivv_input(store, **kwargs)
    events = []
    owners = []

    class Child:
        def __init__(self):
            self.remaining = failures

        def poll(self):
            return 1

        def close(self, *, verify=False):
            assert verify is True
            events.append("cleanup")
            if self.remaining:
                self.remaining -= 1
                raise OSError("authored cleanup uncertainty")
            events.append("terminal")
            return True

    def factory(*args):
        events.append("new-owner")
        owner = runtime.IVVRuntime.__new__(runtime.IVVRuntime)
        owner.child = Child()
        owner.closed = False
        owner.timer = None
        owner.started = 0
        owner._lock = threading.RLock()
        owner.directory = root / "modeled-numeric"
        monkeypatch.setattr(owner, "check", lambda **kw: True)
        owners.append(owner)
        return owner

    service = daily.NativeDailyService(root, registered=(registered,), real_runtime_factory=factory)
    # Use real calculate's failure/finally path without actual child creation.
    (root / "modeled-numeric").mkdir()
    try:
        try:
            service.submit(registered.request, key)
        except OSError:
            pass
        if failures > 1:
            assert owners[0].closed is False
            assert service._real_runtimes[registered.real_binding.digest] is owners[0]
            assert service._inflight == key
            with pytest.raises((OSError, daily.NativeError)):
                service.submit(registered.request, key)
            assert len(owners) == 1
            owners[0].child.remaining = 0
        # A terminal cleanup retry can release this owner; no refund of the debit.
        service._recover_pending_cleanup()
        assert owners[0].closed is True
        assert service._real_runtimes == {}
        assert service._inflight is None
        assert len(service._records()[0].transaction.attempts) == 1
        assert events.index("terminal") > events.index("cleanup")
        try:
            service.submit(registered.request, key)
        except OSError:
            pass
        assert len(owners) == 2
        assert len(service._records()[0].transaction.attempts) == 2
        assert events.index("terminal") < [i for i, e in enumerate(events) if e == "new-owner"][1]
    finally:
        for owner in owners:
            owner.child.remaining = 0
        # Explicit close must also recover pending cleanup rather than deadlock.
        service.close()


@pytest.mark.parametrize(
    "defect", ["terminate", "query", "jobclose", "processclose", "reap", "log", "active"]
)
def test_verified_owned_child_close_checks_each_terminal_boundary_and_retains_handle(
    monkeypatch, defect
):
    import io

    from quantmesh.research import job_runner as runner

    events = []
    broken = {"enabled": True}

    class Handle(int):
        closed = False

    class Process:
        stdin = None
        _handle = Handle(124)

        def poll(self):
            return 1

        def wait(self, timeout):
            if defect == "reap" and broken["enabled"]:
                raise TimeoutError("authored reap unknown")
            events.append("reap")

    class Log(io.BytesIO):
        def close(self):
            if defect == "log" and broken["enabled"]:
                raise OSError("authored FD close unknown")
            events.append("fd-close")
            super().close()

    class Kernel:
        def TerminateJobObject(self, handle, code):
            events.append("terminate")
            return not (defect == "terminate" and broken["enabled"])

        def QueryInformationJobObject(self, handle, kind, pointer, size, unused):
            events.append("active-readback")
            pointer._obj.active = int(
                not owner.process._handle.closed or (defect == "active" and broken["enabled"])
            )
            return not (defect == "query" and broken["enabled"])

        def CloseHandle(self, handle):
            events.append("job-handle-close" if handle.value == 123 else "process-handle-close")
            return not (
                broken["enabled"]
                and (
                    (defect == "jobclose" and handle.value == 123)
                    or (defect == "processclose" and handle.value == 124)
                )
            )

    monkeypatch.setattr(runner.ctypes, "windll", SimpleNamespace(kernel32=Kernel()), raising=False)
    clock = iter(range(0, 1000, 6))
    monkeypatch.setattr(
        runner, "time", SimpleNamespace(monotonic=lambda: next(clock), sleep=lambda _: None)
    )
    owner = runner._OwnedChild.__new__(runner._OwnedChild)
    owner.job_handle = 123
    owner.process = Process()
    owner.log = Log()
    with pytest.raises((OSError, TimeoutError)):
        owner.close(verify=True)
    assert owner.job_handle == 123
    broken["enabled"] = False
    assert owner.close(verify=True) is True
    assert owner.job_handle is None and owner.log.closed
    assert events.index("reap") < events.index("fd-close") < events.index("active-readback")


def test_partial_child_construction_keeps_exact_owner_until_checked_cleanup(tmp_path, monkeypatch):
    class Child:
        def __init__(self, *args):
            self.failed = True
            raise OSError("authored partial launch")

        def close(self, *, verify=False):
            assert verify
            if self.failed:
                self.failed = False
                raise OSError("authored cleanup uncertainty")
            return True

    monkeypatch.setattr(runtime, "_OwnedChild", Child)
    owner = runtime.IVVRuntime.__new__(runtime.IVVRuntime)
    owner.directory = tmp_path / "numeric"
    owner.closed = False
    owner.timer = owner.child = None
    owner._lock = threading.RLock()
    with pytest.raises(OSError, match="cleanup uncertainty"):
        owner.check()
    assert isinstance(owner.child, Child) and owner.closed is False
    assert owner.cleanup_pending is True
    with pytest.raises(ValueError, match="numeric_cleanup_unconfirmed"):
        owner.check()
    owner.close()
    assert owner.closed and not owner.cleanup_pending


def test_close_failure_holds_root_lease_and_owner_across_garbage_collection(tmp_path):
    import gc
    import weakref

    class Owner:
        failing = True

        def close(self):
            if self.failing:
                raise OSError("authored terminal cleanup unknown")

    owner = Owner()
    service = daily.NativeDailyService(tmp_path)
    service._real_runtimes["authored-exact-owner"] = owner
    with pytest.raises(OSError):
        service.close()
    retained = weakref.ref(service)
    del service
    gc.collect()
    assert retained() is not None
    with pytest.raises((OSError, ValueError)):
        daily.NativeDailyService(tmp_path)
    owner.failing = False
    recovered = daily.NativeDailyService(tmp_path)
    recovered.close()
    assert retained() is None or retained()._closed


def test_normal_numeric_receipt_requires_released_process_reference_and_empty_job(
    tmp_path, monkeypatch
):
    import io
    import time

    from quantmesh.research import job_runner as runner

    class Handle(int):
        closed = False

    class Process:
        _handle = Handle(124)
        stdin = SimpleNamespace(closed=True)

        def wait(self, timeout):
            return 0

    process = Process()
    events = []

    class Kernel:
        def CloseHandle(self, handle):
            events.append(handle.value)
            return 1

    monkeypatch.setattr(runner.ctypes, "windll", SimpleNamespace(kernel32=Kernel()), raising=False)
    owner = runtime.IVVRuntime.__new__(runtime.IVVRuntime)
    owner.directory = tmp_path
    owner.closed = False
    owner.cleanup_pending = False
    owner.started = time.monotonic()
    owner.timer = SimpleNamespace(cancel=lambda: None)
    owner._lock = threading.RLock()
    owner.child = SimpleNamespace(process=process, log=io.BytesIO(), job_handle=123, poll=lambda: 0)
    monkeypatch.setattr(owner, "check", lambda **kwargs: True)

    def active(child):
        assert child.job_handle == 123
        assert child.process._handle.closed
        events.append("empty-job-readback")
        return 0

    monkeypatch.setattr(runtime, "_active", active)
    owner.native_limits = {
        "job_commit_bytes": 536870912,
        "affinity": 1,
        "process_affinity": 1,
        "kernel_flags": 0x2210,
        "child_membership_verified": True,
    }
    (tmp_path / "result.json").write_bytes(b"{}")
    matrix, receipt = owner.calculate(
        b"authored engineering control", [], "a" * 64, {"authored": "a" * 64}
    )
    assert matrix == {} and receipt["returncode"] == 0 and receipt["active_processes"] == 0
    assert owner.closed and owner.child.job_handle is None and owner.child.log.closed
    assert events[0] == 124 and events[-1] == 123


@pytest.mark.parametrize("lost_handle", [123, 124])
def test_close_ack_loss_never_reuses_reassigned_raw_handle(monkeypatch, lost_handle):
    import io

    from quantmesh.research import job_runner as runner

    state = {"lost": False, "foreign_alive": True}

    class Handle(int):
        closed = False

    process = SimpleNamespace(
        _handle=Handle(124), stdin=None, poll=lambda: 0, wait=lambda timeout: 0
    )

    class Kernel:
        def TerminateJobObject(self, handle, code):
            if state["lost"] and handle.value == lost_handle:
                state["foreign_alive"] = False
            return True

        def QueryInformationJobObject(self, handle, kind, pointer, size, unused):
            pointer._obj.active = 0
            return True

        def CloseHandle(self, handle):
            if handle.value == lost_handle:
                if state["lost"]:
                    state["foreign_alive"] = False
                else:
                    # Kernel closed the original and reused its numeric value;
                    # the Python caller did not receive a completion observation.
                    state["lost"] = True
                    raise KeyboardInterrupt("authored close acknowledgment loss")
            return True

    monkeypatch.setattr(runner.ctypes, "windll", SimpleNamespace(kernel32=Kernel()), raising=False)
    owner = runner._OwnedChild.__new__(runner._OwnedChild)
    owner.job_handle, owner.process, owner.log = 123, process, io.BytesIO()
    with pytest.raises(KeyboardInterrupt):
        owner.close(verify=True)
    try:
        owner.close(verify=True)
    except OSError:
        pass  # Preserving unresolved ownership is safe; touching the foreign object is not.
    assert state["foreign_alive"], "cleanup retried a potentially reassigned native handle"


@pytest.mark.parametrize("lost_handle", [123, 124])
@pytest.mark.parametrize("known_success", [False, True])
def test_interrupt_between_native_return_and_bookkeeping_never_reuses_handle(
    monkeypatch, lost_handle, known_success
):
    import inspect
    import io
    import sys

    from quantmesh.research import job_runner as runner

    native_closed = set()
    calls = []

    class Handle(int):
        closed = False

    process = SimpleNamespace(
        _handle=Handle(124), stdin=None, poll=lambda: 0, wait=lambda timeout: 0
    )

    class Kernel:
        def TerminateJobObject(self, handle, code):
            assert handle.value not in native_closed
            calls.append(("terminate", handle.value))
            return True

        def QueryInformationJobObject(self, handle, kind, pointer, size, unused):
            assert handle.value not in native_closed
            pointer._obj.active = 0
            return True

        def CloseHandle(self, handle):
            assert handle.value not in native_closed
            native_closed.add(handle.value)
            calls.append(("close", handle.value))
            return True

    monkeypatch.setattr(runner.ctypes, "windll", SimpleNamespace(kernel32=Kernel()), raising=False)
    owner = runner._OwnedChild.__new__(runner._OwnedChild)
    owner.job_handle = 123
    owner.process = process
    owner.log = io.BytesIO()
    function = runner._close_job_handle if lost_handle == 123 else runner._close_process_handle
    lines, start = inspect.getsourcelines(function)
    if lost_handle == 123:
        text = (
            "child.job_handle = None"
            if known_success
            else 'child._job_handle_close_state = "CLOSED"'
        )
    else:
        text = (
            "handle.closed = True"
            if known_success
            else 'process._owned_handle_close_state = "CLOSED"'
        )
    location = start + max(i for i, line in enumerate(lines) if line.strip() == text)

    def interrupt(frame, event, arg):
        if frame.f_code is function.__code__ and event == "line" and frame.f_lineno == location:
            sys.settrace(None)
            raise KeyboardInterrupt("authored bookkeeping interruption")
        return interrupt

    try:
        sys.settrace(interrupt)
        with pytest.raises(KeyboardInterrupt):
            owner.close(verify=True)
    finally:
        sys.settrace(None)
    assert lost_handle in native_closed
    before = list(calls)
    if known_success:
        assert owner.close(verify=True) is True
        assert calls.count(("close", lost_handle)) == 1
    else:
        with pytest.raises(OSError, match="acknowledgement_unknown"):
            owner.close(verify=True)
        assert calls == before


@pytest.mark.parametrize("lost_handle", [123, 124])
def test_normal_finally_ack_loss_retains_root_owner_and_lease_across_gc(
    tmp_path, monkeypatch, lost_handle
):
    import gc
    import io
    import time
    import weakref

    from quantmesh.research import job_runner as runner

    gate, store, root, key, kwargs = reviewed_recovery_registration(tmp_path, monkeypatch)
    registration = gate.register_ivv_input(store, **kwargs)
    closed = set()
    calls = []
    owners = []

    class Handle(int):
        closed = False

    class Process:
        _handle = Handle(124)
        stdin = SimpleNamespace(closed=True)

        def wait(self, timeout):
            return 0

        def poll(self):
            assert 124 not in closed
            return 0

    class Kernel:
        def TerminateJobObject(self, handle, code):
            assert handle.value not in closed
            calls.append(("terminate", handle.value))
            return True

        def QueryInformationJobObject(self, handle, kind, pointer, size, unused):
            assert handle.value not in closed
            calls.append(("query", handle.value))
            pointer._obj.active = 0
            return True

        def CloseHandle(self, handle):
            assert handle.value not in closed
            closed.add(handle.value)
            calls.append(("close", handle.value))
            if handle.value == lost_handle:
                raise KeyboardInterrupt("authored native ack loss")
            return True

    monkeypatch.setattr(runner.ctypes, "windll", SimpleNamespace(kernel32=Kernel()), raising=False)

    def factory(*args):
        owner = runtime.IVVRuntime.__new__(runtime.IVVRuntime)
        owner.directory = root / "normal-modeled"
        owner.directory.mkdir()
        (owner.directory / "result.json").write_bytes(b"{}")
        owner.child = runner._OwnedChild.__new__(runner._OwnedChild)
        owner.child.job_handle = 123
        owner.child.process = Process()
        owner.child.log = io.BytesIO()
        owner.closed = False
        owner.cleanup_pending = False
        owner.started = time.monotonic()
        owner._lock = threading.RLock()
        owner.timer = SimpleNamespace(cancel=lambda: None)
        owner.native_limits = {
            "job_commit_bytes": 536870912,
            "affinity": 1,
            "process_affinity": 1,
            "kernel_flags": 0x2210,
            "child_membership_verified": True,
        }
        monkeypatch.setattr(owner, "check", lambda **kw: True)
        owners.append(owner)
        return owner

    service = daily.NativeDailyService(
        root, registered=(registration,), real_runtime_factory=factory
    )
    try:
        with pytest.raises(OSError, match="acknowledgement_unknown"):
            service.submit(registration.request, key)
        assert len(owners) == 1 and owners[0].closed is False
        job = service._records()[0]
        assert job.state == "failed" and job.report is None and len(job.transaction.attempts) == 1
        assert service._inflight == key
        before = list(calls)
        reference = weakref.ref(service)
        del service
        gc.collect()
        assert reference() is not None
        reference()._lease.validate()
        with pytest.raises(OSError, match="acknowledgement_unknown"):
            daily.NativeDailyService(root)
        assert calls == before
        with pytest.raises(OSError, match="acknowledgement_unknown"):
            runtime._active(owners[0].child)
        assert calls == before
    finally:
        # The authored kernel/handle table ends here; no real child or native
        # handle existed. Release the test lease only, never invoke fake handles.
        retained = daily._UNCERTAIN_OWNER_ROOTS.pop(str(root), None)
        if retained is not None:
            retained._lease.close()
            retained._closed = True
