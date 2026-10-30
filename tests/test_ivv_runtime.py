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
    ):
        with pytest.raises(ValueError):
            module.validate_close_receipt({**good, **change}, good["code"])


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
