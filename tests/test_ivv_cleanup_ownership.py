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
