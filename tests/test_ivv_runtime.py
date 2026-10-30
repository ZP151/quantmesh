"""Small native-control doubles, never a production scope or market calculation."""

import importlib

import pytest


def test_numeric_close_rejects_forced_or_unbounded_receipts():
    module = importlib.import_module("quantmesh.research.ivv_runtime")
    good = {
        "schema_id": "qm.ivv.numeric-close.v1",
        "job_commit_bytes": 536870912,
        "affinity": 1,
        "returncode": 0,
        "active_processes": 0,
        "owned_fds_closed": True,
        "kernel_flags": 0x2210,
        "process_affinity": 1,
        "child_membership_verified": True,
        "wall_seconds": 0.1,
        "code": {"test": "a" * 64},
    }
    module.validate_close_receipt(good, good["code"])
    for change in (
        {"returncode": 1},
        {"active_processes": 1},
        {"owned_fds_closed": False},
        {"wall_seconds": 81},
        {"affinity": 3},
        {"job_commit_bytes": 1},
        {"wall_seconds": float("nan")},
        {"returncode": False},
        {"kernel_flags": 0},
        {"process_affinity": 3},
        {"child_membership_verified": False},
    ):
        with pytest.raises(ValueError):
            module.validate_close_receipt({**good, **change}, good["code"])


def test_owned_artifact_capacity_is_checked_before_starting_child(tmp_path, monkeypatch):
    module = importlib.import_module("quantmesh.research.ivv_runtime")
    monkeypatch.setattr(module, "ARTIFACT_BYTES", 1024, raising=False)
    (tmp_path / "existing").write_bytes(b"x" * 600)
    module.ensure_capacity(tmp_path, 400)
    with pytest.raises(ValueError):
        module.ensure_capacity(tmp_path, 425)


def test_readback_failure_closes_owned_process_before_work(tmp_path, monkeypatch):
    module = importlib.import_module("quantmesh.research.ivv_runtime")
    closed = []

    class Child:
        def __init__(self, *args):
            self.job_handle = 123

        def close(self):
            closed.append(True)

    monkeypatch.setattr(module, "_OwnedChild", Child)
    monkeypatch.setattr(module, "_readback", lambda _: (_ for _ in ()).throw(ValueError()))
    owner = module.IVVRuntime.__new__(module.IVVRuntime)
    owner.directory = tmp_path / "numeric"
    owner.child = None
    owner.started = None
    owner.timer = None
    owner.closed = False
    with pytest.raises(ValueError):
        owner.check()
    assert closed == [True]
    assert not (tmp_path / "command.json").exists()


@pytest.mark.parametrize("bad", ["flags", "memory", "membership", "affinity", "query"])
def test_native_readback_checks_kernel_facts_not_declared_booleans(monkeypatch, bad):
    from types import SimpleNamespace

    module = importlib.import_module("quantmesh.research.ivv_runtime")

    class Kernel:
        def QueryInformationJobObject(self, handle, kind, pointer, size, returned):
            limits = pointer._obj
            limits.basic.flags = 0x2210 if bad != "flags" else 0x210
            limits.basic.affinity = 1
            limits.job_memory = module.COMMIT_BYTES if bad != "memory" else 1
            return bad != "query"

        def IsProcessInJob(self, process, handle, result):
            result._obj.value = int(bad != "membership")
            return 1

        def GetProcessAffinityMask(self, process, actual, system):
            actual._obj.value = 1 if bad != "affinity" else 3
            system._obj.value = 255
            return 1

    monkeypatch.setattr(module.ctypes, "windll", SimpleNamespace(kernel32=Kernel()))
    child = SimpleNamespace(job_handle=7, process=SimpleNamespace(_handle=8))
    with pytest.raises(ValueError):
        module._readback(child)
