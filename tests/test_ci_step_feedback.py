"""Actual subprocess contracts for feedback owned by the gate controller."""

import json
import sys
import time
from pathlib import Path

import pytest

from tools import release_gate


def child(tmp_path, monkeypatch, body, *, timeout=15, conftest=None):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_probe.py").write_text(body, encoding="utf-8")
    if conftest:
        (tmp_path / "conftest.py").write_text(conftest, encoding="utf-8")
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    monkeypatch.setattr(release_gate, "STEPS", [])
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    command = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-p",
        "tools.ci_profile_plugin",
        "-p",
        "no:cacheprovider",
        "--maxfail=1",
        "test_probe.py",
    ]
    started = time.monotonic()
    ok, elapsed = release_gate.run_step(
        "pytest probe",
        command,
        tmp_path,
        logs,
        timeout=timeout,
        progress_interval_seconds=0.02,
    )
    assert 0 <= elapsed <= time.monotonic() - started + 0.1
    rows = [
        json.loads(line)
        for line in (logs / "01-pytest-probe.pytest.jsonl").read_text().splitlines()
    ]
    current = json.loads((logs / "01-pytest-probe.pytest.current.json").read_text())
    ordinary = (logs / "01-pytest-probe.log").read_text()
    return ok, rows, current, ordinary


@pytest.mark.parametrize("phase", ["setup", "call", "teardown", "passed", "collection"])
def test_controller_uses_real_terminal_phase_and_preserves_teardown(tmp_path, monkeypatch, phase):
    body = (
        "import pytest\nfrom pathlib import Path\n"
        "@pytest.fixture\ndef owner():\n"
        + ("    assert False, 'synthetic setup assertion'\n" if phase == "setup" else "")
        + "    yield\n    Path('closed').touch()\n"
        + ("    assert False, 'synthetic teardown assertion'\n" if phase == "teardown" else "")
        + "def test_first(owner):\n"
        + ("    assert False, 'synthetic call assertion'\n" if phase == "call" else "    pass\n")
        + "def test_later():\n    Path('later').touch()\n"
    )
    if phase == "collection":
        body = "raise RuntimeError('synthetic collection assertion')\n"
    ok, rows, current, ordinary = child(tmp_path, monkeypatch, body)
    assert ok is (phase == "passed")
    assert rows[0]["event"] == "stage" and rows[0]["status"] == "STARTING"
    terminal = rows[-1]
    assert terminal["event"] == "terminal"
    assert terminal["status"] == ("PASSED" if ok else "TEST_FAILED")
    assert current["status"] == terminal["status"]
    failures = [row for row in rows if row["event"] == "first_failure"]
    if ok:
        assert not failures and terminal["completed"] == 2
    else:
        (failure,) = failures
        assert failure["phase"] == phase
        assert failure["nodeid"] == (
            "test_probe.py" if phase == "collection" else "test_probe.py::test_first"
        )
        assert failure["log"] == "01-pytest-probe.log"
        assert "synthetic " + phase + " assertion" in ordinary
    assert (tmp_path / "later").exists() is ok
    assert (tmp_path / "closed").exists() is (phase in ("call", "teardown", "passed"))
    assert "synthetic" not in json.dumps(rows)


def test_child_mocked_os_and_clock_cannot_change_parent_observation(tmp_path, monkeypatch):
    body = """import json, os, time
from pathlib import Path
from types import SimpleNamespace

def test_mocked(monkeypatch):
    base = Path('logs/01-pytest-probe')
    assert base.with_suffix('.log').exists()
    assert base.with_suffix('.pytest.jsonl').exists()
    assert base.with_suffix('.pytest.current.json').exists()
    with monkeypatch.context() as mock:
        fake = SimpleNamespace(st_mode=0o40700, st_dev=1, st_ino=7, st_uid=0)
        mock.setattr(os, 'stat', lambda *a, **kw: fake)
        mock.setattr(os, 'fstat', lambda *a, **kw: fake)
        mock.setattr(time, 'monotonic', lambda: 465.0)
        time.sleep(0.15)
        with open('logs/01-pytest-probe.pytest.current.json') as source:
            current = json.load(source)
        assert current['status'] == 'RUNNING'
        assert current['phase'] == 'UNOBSERVED'
"""
    ok, rows, current, _ = child(tmp_path, monkeypatch, body)
    assert ok and current["status"] == "PASSED"
    assert all(0 <= row["elapsed_seconds"] < 15 for row in rows)
    assert rows[-1]["completed"] == 1
    assert any(row.get("nodeid") == "test_probe.py::test_mocked" for row in rows)


def test_internal_error_keeps_last_node_without_fabricating_assertion(tmp_path, monkeypatch):
    ok, rows, current, ordinary = child(
        tmp_path,
        monkeypatch,
        "def test_first():\n    pass\n",
        conftest=(
            "def pytest_runtest_makereport(item, call):\n"
            "    if call.when == 'call':\n"
            "        raise RuntimeError('synthetic infrastructure failure')\n"
        ),
    )
    assert not ok and "INTERNALERROR" in ordinary
    assert rows[-1]["status"] == "INFRASTRUCTURE_ERROR"
    assert rows[-1]["exit_code"] != 0
    assert rows[-1]["missing_evidence"]
    assert current["nodeid"] == "test_probe.py::test_first"
    assert current["phase"] == "UNOBSERVED"
    assert not any(row["event"] == "first_failure" for row in rows)


def test_owned_timeout_keeps_prelaunch_artifacts(tmp_path, monkeypatch):
    ok, rows, current, _ = child(
        tmp_path,
        monkeypatch,
        "import time\ndef test_wait():\n    time.sleep(10)\n",
        timeout=2,
    )
    assert not ok
    assert rows[-1]["status"] == current["status"] == "TIMEOUT"
    assert rows[-1]["exit_code"] != 0
    assert rows[-1]["elapsed_seconds"] < 10
    assert rows[0]["status"] == "STARTING"
    assert not any(row["event"] == "first_failure" for row in rows)


@pytest.mark.parametrize("damage", ["missing", "malformed"])
def test_zero_exit_without_terminal_result_is_not_green(tmp_path, monkeypatch, damage):
    operation = "path.unlink()" if damage == "missing" else "path.write_text('<broken')"
    ok, rows, current, _ = child(
        tmp_path,
        monkeypatch,
        "def test_ok():\n    pass\n",
        conftest=(
            "from pathlib import Path\n"
            "def pytest_unconfigure(config):\n"
            "    path = Path(config.option.xmlpath)\n"
            f"    {operation}\n"
        ),
    )
    assert not ok
    assert rows[-1]["exit_code"] == 0
    assert rows[-1]["status"] == current["status"] == "INFRASTRUCTURE_ERROR"
    assert rows[-1]["missing_evidence"] == ["complete_consistent_junit_result"]
    assert not any(row["event"] == "first_failure" for row in rows)


def test_feedback_artifact_failure_prevents_child_start(tmp_path, monkeypatch):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "01-pytest-probe.pytest.current.json").mkdir()
    monkeypatch.setattr(release_gate, "STEPS", [])
    marker = tmp_path / "spawned"
    command = [sys.executable, "-m", "pytest", "-p", "tools.ci_profile_plugin"]

    def forbidden(*args, **kwargs):
        marker.touch()
        pytest.fail("child spawned before durable artifacts")

    monkeypatch.setattr(release_gate.subprocess, "Popen", forbidden)
    with pytest.raises(OSError):
        release_gate.run_step("pytest probe", command, tmp_path, logs)
    assert not marker.exists()
