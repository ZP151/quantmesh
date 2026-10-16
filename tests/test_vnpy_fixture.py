"""The experimental native adapter cannot weaken baseline contracts."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from quantmesh.research.vnpy_fixture import (
    FIXTURE_SHA256,
    SESSION_CLOSES,
    FixtureManager,
    FixtureRequest,
    canonical,
    options,
)


def test_defaults_and_explicit_native_cost_units():
    request = FixtureRequest()
    assert request.strategy_id == "DoubleMaStrategy"
    assert request.parameters == {"fast_window": 10, "slow_window": 20}
    assert request.costs.fee_bps == 5
    assert request.costs.half_spread_price == 0.005
    assert options()["fixture_sha256"] == FIXTURE_SHA256
    assert len(options()["strategies"]) == 2


@pytest.mark.parametrize(
    "value",
    [
        {"strategy_id": "os.system"},
        {"parameters": {"fast_window": 20, "slow_window": 10}},
        {"parameters": {"fast_window": True, "slow_window": 20}},
        {"parameters": {"fast_window": 10.5, "slow_window": 20}},
        {"parameters": {"fast_window": 10, "slow_window": 20, "path": "x"}},
        {"costs": {"fee_bps": float("nan")}},
        {"costs": {"fee_bps": 0}},
        {"costs": {"slippage_price": -1}},
        {"costs": {"fee_bps": True}},
        {"costs": {"fee_bps": "5"}},
        {"fixture": "other.csv"},
    ],
)
def test_invalid_requests_fail_before_execution(value):
    with pytest.raises(ValidationError):
        FixtureRequest.model_validate(value)


def test_strategy_defaults_and_canonical_parameter_order():
    atr = FixtureRequest(strategy_id="AtrRsiStrategy")
    assert atr.parameters["rsi_entry"] == 16
    left = FixtureRequest(parameters={"fast_window": 10, "slow_window": 20})
    right = FixtureRequest(parameters={"slow_window": 20, "fast_window": 10})
    assert canonical(left.model_dump()) == canonical(right.model_dump())


def test_fixture_drift_is_rejected(tmp_path):
    fixture = tmp_path / "fixture.csv"
    fixture.write_text("wrong")
    with pytest.raises(ValueError, match="fixture"):
        FixtureManager(Path("missing.exe"), fixture, tmp_path / "jobs")


def test_report_hash_is_exact_bytes():
    raw = canonical({"schema_version": 1, "value": 1.5})
    assert json.loads(raw)["value"] == 1.5
    assert hashlib.sha256(raw).hexdigest() == hashlib.sha256(raw).hexdigest()


def test_idempotency_cancel_and_corruption(tmp_path, monkeypatch):
    """Use the real manager and a blocked execution boundary, never a fake store."""
    monkeypatch.setattr(FixtureManager, "_admit", lambda self: None)
    monkeypatch.setattr(FixtureManager, "_start", lambda self, job: None)
    manager = FixtureManager(Path("python.exe"), Path("fixture.csv"), tmp_path)
    key = str(uuid4())
    first = manager.submit(FixtureRequest(), key)
    assert manager.submit(FixtureRequest(), key) == first
    with pytest.raises(ValueError, match="idempotency_conflict"):
        manager.submit(FixtureRequest(parameters={"fast_window": 5, "slow_window": 20}), key)
    assert manager.get(first["job_id"])["state"] == "queued"
    cancelled = manager.cancel(first["job_id"])
    assert cancelled["state"] == "cancelled"
    with pytest.raises(ValueError, match="report_unavailable"):
        manager.report(first["job_id"])
    manager.close()


def valid_report(job):
    return {
        "schema_version": 1,
        "request_digest": job["request_digest"],
        "request": job["request"],
        "identity": job["identity"],
        "lifecycle": {
            "replay_bars": 1950,
            "warmup_bars": 2340,
            "on_init": 1,
            "on_start": 1,
            "on_stop": 1,
        },
        "trades": [],
        "daily": [
            {
                "date": session,
                "balance": 100000,
                "net_pnl": 0,
                "close_price": close,
                "commission": 0,
                "slippage": 0,
                "end_pos": 0,
            }
            for session, close in SESSION_CLOSES.items()
        ],
        "statistics": {
            "capital": 100000,
            "end_balance": 100000,
            "total_commission": 0,
            "total_slippage": 0,
            "total_trade_count": 0,
            "total_turnover": 0,
        },
    }


@pytest.mark.parametrize("mutation", ["pnl", "fee", "stop", "date", "nonfinite"])
def test_report_accounting_and_lifecycle_corruption(tmp_path, monkeypatch, mutation):
    monkeypatch.setattr(FixtureManager, "_admit", lambda self: None)
    monkeypatch.setattr(FixtureManager, "_start", lambda self, job: None)
    manager = FixtureManager(Path("python.exe"), Path("fixture.csv"), tmp_path)
    job = manager.submit(FixtureRequest(), str(uuid4()))
    result = valid_report(job)
    if mutation == "pnl":
        result["statistics"]["end_balance"] = 100005
    elif mutation == "fee":
        result["statistics"]["total_commission"] = 1
    elif mutation == "stop":
        result["lifecycle"]["on_stop"] = 0
    elif mutation == "date":
        result["daily"][0]["date"] = "2026-10-16"
    else:
        result["statistics"]["end_balance"] = float("nan")
    with pytest.raises(ValueError):
        manager._validate_report(job, result)
    manager.close()


def test_completed_report_tampering_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(FixtureManager, "_admit", lambda self: None)
    monkeypatch.setattr(FixtureManager, "_start", lambda self, job: None)
    manager = FixtureManager(Path("python.exe"), Path("fixture.csv"), tmp_path)
    job = manager.submit(FixtureRequest(), str(uuid4()))
    raw = canonical(valid_report(job))
    sha = hashlib.sha256(raw).hexdigest()
    target = tmp_path / f"{sha}.json"
    target.write_bytes(raw)
    manager._jobs[job["job_id"]].update(state="succeeded", report_sha256=sha)
    assert manager.report(job["job_id"])["sha256"] == sha
    target.write_bytes(raw + b" ")
    with pytest.raises(ValueError, match="report_invalid"):
        manager.report(job["job_id"])
    manager.close()


@pytest.mark.parametrize(
    "mode,expected", [("timeout", "failed"), ("exit", "failed"), ("cancel", "cancelled")]
)
def test_owned_child_cleanup_on_terminal_paths(tmp_path, monkeypatch, mode, expected):
    from quantmesh.research import job_runner

    monkeypatch.setattr(FixtureManager, "_admit", lambda self: None)
    closed = []
    manager = FixtureManager(Path("python.exe"), Path("fixture.csv"), tmp_path)

    class Child:
        def __init__(self, command, budget, directory):
            assert budget.memory_mib == 1024 and budget.cpu_limit == 1
            if mode == "cancel":
                manager.cancel(directory.name)

        def poll(self):
            return 1 if mode == "exit" else None

        def close(self):
            closed.append(True)

    clock = iter([0, 1000])
    monkeypatch.setattr(job_runner, "_OwnedChild", Child)
    if mode == "timeout":
        monkeypatch.setattr("quantmesh.research.vnpy_fixture.monotonic", lambda: next(clock))
    job = manager.submit(FixtureRequest(), str(uuid4()))
    for thread in manager._threads:
        thread.join(timeout=5)
    assert manager.get(job["job_id"])["state"] == expected
    assert closed == [True]
    manager.close()


def test_cancel_does_not_admit_another_child_until_cleanup(tmp_path, monkeypatch):
    import threading

    from quantmesh.research import job_runner

    monkeypatch.setattr(FixtureManager, "_admit", lambda self: None)
    entered, release = threading.Event(), threading.Event()
    manager = FixtureManager(Path("python.exe"), Path("fixture.csv"), tmp_path)

    class Child:
        def __init__(self, command, budget, directory):
            manager.cancel(directory.name)

        def poll(self):
            return None

        def close(self):
            entered.set()
            release.wait(timeout=5)

    monkeypatch.setattr(job_runner, "_OwnedChild", Child)
    manager.submit(FixtureRequest(), str(uuid4()))
    assert entered.wait(timeout=5)
    try:
        with pytest.raises(ValueError, match="capacity_exceeded"):
            manager.submit(FixtureRequest(), str(uuid4()))
    finally:
        release.set()
        manager.close()


@pytest.mark.parametrize("file", ["runner", "adapter"])
def test_adapter_source_drift_after_startup_rejected(tmp_path, monkeypatch, file):
    from quantmesh.research import vnpy_fixture

    monkeypatch.setattr(FixtureManager, "_admit", lambda self: None)
    monkeypatch.setattr(FixtureManager, "_start", lambda self, job: None)
    manager = FixtureManager(Path("python.exe"), Path("fixture.csv"), tmp_path)
    if file == "runner":
        changed = tmp_path / "runner.py"
        changed.write_bytes(manager.runner.read_bytes() + b"\n# drift\n")
        manager.runner = changed
    else:
        original_digest = vnpy_fixture.digest
        monkeypatch.setattr(
            vnpy_fixture,
            "digest",
            lambda path: "0" * 64 if path.name == "vnpy_fixture.py" else original_digest(path),
        )
    with pytest.raises(ValueError, match="adapter source drift"):
        manager.submit(FixtureRequest(), str(uuid4()))
    manager.close()
