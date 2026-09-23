"""Hard deadline and credential-free worker boundary for readiness."""

import sys
import time

import pytest

from quantmesh.moomoo import readiness_process
from quantmesh.settings import Settings


def test_stalled_provider_is_terminated_and_scratch_removed(monkeypatch, tmp_path):
    # Substitute a worker that never answers, exercising the real process gate.
    monkeypatch.setattr(readiness_process, "_worker_command", lambda: [
        sys.executable, "-c", "import time; time.sleep(60)", "{request}", "{output}"
    ])
    started = time.monotonic()
    result = readiness_process.run_readiness_process(
        Settings(), ["US.AAPL"], timeout_seconds=0.2, scratch_root=tmp_path
    )
    assert time.monotonic() - started < 10
    assert result["status"] == "timeout"
    assert result["order_checked"] is False
    assert list(tmp_path.iterdir()) == []


def test_worker_receives_only_readiness_configuration(monkeypatch, tmp_path):
    config = Settings()
    captured = {}

    def fake_worker(command, **kwargs):
        captured.update(kwargs["request"])
        return {"status": "unavailable", "order_checked": False, "symbols": []}

    monkeypatch.setattr(readiness_process, "run_bounded_json_process", fake_worker)
    readiness_process.run_readiness_process(
        config, ["US.AAPL"], timeout_seconds=2, scratch_root=tmp_path
    )
    assert captured == {
        "host": config.moomoo_opend_host, "port": config.moomoo_opend_port,
        "connect_timeout_s": config.moomoo_opend_connect_timeout_s,
        "request_timeout_s": config.moomoo_opend_request_timeout_s,
        "codes": ["US.AAPL"],
    }


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan"), 301])
def test_invalid_deadline_never_launches_worker(timeout):
    with pytest.raises(ValueError):
        readiness_process.run_readiness_process(Settings(), ["US.AAPL"], timeout_seconds=timeout)
