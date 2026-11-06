"""Small synthetic controls for the release-only pytest profiler."""

import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from tools import ci_profile_plugin


@pytest.mark.parametrize("phase", ["setup", "call", "teardown", "passed", "collection"])
def test_feedback_subprocess_retains_exact_failure_and_normal_teardown(tmp_path, phase):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    marker = tmp_path / "finished"
    body = (
        "import pytest\nfrom pathlib import Path\n"
        "@pytest.fixture\ndef resource():\n"
        + ("    assert False, 'synthetic setup assertion'\n" if phase == "setup" else "")
        + "    yield\n"
        + f"    Path({str(marker)!r}).write_text('closed')\n"
        + ("    assert False, 'synthetic teardown assertion'\n" if phase == "teardown" else "")
        + "def test_first(resource):\n"
        + ("    assert False, 'synthetic call assertion'\n" if phase == "call" else "    pass\n")
        + "def test_later():\n    pass\n"
    )
    if phase == "collection":
        body = "raise RuntimeError('synthetic collection assertion')\n"
    (tmp_path / "test_probe.py").write_text(body, encoding="utf-8")
    events = tmp_path / "feedback.jsonl"
    command = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-p",
        "tools.ci_profile_plugin",
        "-q",
        "--maxfail=1",
        "-p",
        "no:cacheprovider",
        "--tb=short",
        f"--ci-events={events}",
        "--ci-log=ordinary.log",
        f"--rootdir={tmp_path}",
        "test_probe.py",
    ]
    result = subprocess.run(
        command,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(root),
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        timeout=30,
    )
    (tmp_path / "ordinary.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    assert result.returncode == (0 if phase == "passed" else 1 if phase != "collection" else 2)
    rows = [json.loads(line) for line in events.read_text().splitlines()]
    assert rows[0]["event"] == "session_started"
    assert rows[0]["identity"]["python_version"]
    assert len(rows[0]["identity"]["executable_sha256"]) == 64
    assert rows[-1]["event"] == "session_finished"
    assert rows[-1]["exit_code"] == result.returncode
    failures = [r for r in rows if r["event"] == "first_failure"]
    if phase == "passed":
        assert not failures and rows[-1]["completed"] == 2
    else:
        (failure,) = failures
        assert failure["nodeid"] == (
            "test_probe.py" if phase == "collection" else "test_probe.py::test_first"
        )
        assert failure["phase"] == phase
        assert failure["log"] == "ordinary.log"
        assert "synthetic " + phase + " assertion" in result.stdout
    assert marker.exists() is (phase in ("call", "teardown", "passed"))
    assert "synthetic" not in events.read_text()
    assert all("locals" not in row and "environ" not in row for row in rows)


def test_feedback_write_failure_cannot_be_green(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    pass\n")
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-q",
            "-p",
            "tools.ci_profile_plugin",
            "-p",
            "no:cacheprovider",
            f"--ci-events={tmp_path}",
            "test_ok.py",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": str(root), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
    )
    assert result.returncode != 0
    assert "CI_FEEDBACK_ERROR" in result.stdout + result.stderr


def test_contract_missing_collection_cannot_pass_or_run_body(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    raise AssertionError('body ran')\n")
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-q",
            "-p",
            "tools.ci_profile_plugin",
            "-p",
            "no:cacheprovider",
            "--ci-contract",
            "test_ok.py",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "PYTHONPATH": str(root), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
    )
    assert result.returncode == 4
    assert "missing release contract targets" in result.stderr
    assert "body ran" not in result.stdout


def test_active_snapshot_identifies_a_running_call_before_it_finishes(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    events = tmp_path / "run.jsonl"
    ready, release = tmp_path / "ready", tmp_path / "release"
    (tmp_path / "test_active.py").write_text(
        "from pathlib import Path\nimport time\n"
        "def test_active():\n    Path('ready').touch()\n"
        "    deadline=time.monotonic()+5\n"
        "    while not Path('release').exists() and time.monotonic()<deadline: time.sleep(0.01)\n"
        "    assert Path('release').exists()\n"
    )
    with (tmp_path / "ordinary.log").open("w") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-B",
                "-m",
                "pytest",
                "-q",
                "-p",
                "tools.ci_profile_plugin",
                "-p",
                "no:cacheprovider",
                f"--ci-events={events}",
                f"--rootdir={tmp_path}",
                "test_active.py",
            ],
            cwd=tmp_path,
            stdout=log,
            stderr=subprocess.STDOUT,
            env={**os.environ, "PYTHONPATH": str(root), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        )
        try:
            deadline = time.monotonic() + 4
            while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists()
            current = json.loads(events.with_suffix(".current.json").read_text())
            assert current["nodeid"] == "test_active.py::test_active"
            assert current["phase"] == "call" and current["completed"] == 0
        finally:
            release.touch()
            process.wait(timeout=5)
        assert process.returncode == 0


def test_profile_call_restores_calendar_and_keeps_distinct_argument_digests() -> None:
    class Calendar:
        def sessions(self, calendar_id, start, end, *, policy):
            return (calendar_id, start, end, policy)

    original = Calendar.sessions
    with ci_profile_plugin.profile_call(Calendar) as capture:
        calendar = Calendar()
        for _ in range(2):
            assert calendar.sessions("XNYS", date(2025, 1, 2), date(2025, 1, 3), policy="regular")
        assert calendar.sessions("XNYS", date(2025, 1, 3), date(2025, 1, 3), policy="regular")

    assert Calendar.sessions is original
    summary = capture.summary("synthetic")
    assert summary["calendar_calls"] == 3
    assert summary["calendar_unique_arguments"] == 2
    assert sorted(row["calls"] for row in summary["calendar_arguments"]) == [1, 2]
    assert all(len(row["sha256"]) == 64 for row in summary["calendar_arguments"])
    assert "2025" not in json.dumps(summary)
    assert summary["functions"]


def test_profile_call_restores_calendar_when_test_raises() -> None:
    class Calendar:
        def sessions(self, calendar_id, start, end, *, policy):
            raise RuntimeError("original failure")

    original = Calendar.sessions
    with pytest.raises(RuntimeError, match="original failure"):
        with ci_profile_plugin.profile_call(Calendar) as capture:
            Calendar().sessions("XNYS", date(2025, 1, 2), date(2025, 1, 2), policy="regular")

    assert Calendar.sessions is original
    assert capture.summary("synthetic")["calendar_calls"] == 1


def test_profile_summary_is_bounded_and_redacts_function_paths() -> None:
    class Calendar:
        def sessions(self, calendar_id, start, end, *, policy):
            return None

    with ci_profile_plugin.profile_call(Calendar) as capture:
        for day in range(1, 20):
            Calendar().sessions("XNYS", date(2025, 1, day), date(2025, 1, day), policy="regular")

    summary = capture.summary("synthetic")
    assert len(summary["calendar_arguments"]) <= ci_profile_plugin.MAX_ROWS
    assert len(summary["functions"]) <= ci_profile_plugin.MAX_ROWS
    assert summary["calendar_unique_arguments"] == 19
    assert "C:\\" not in json.dumps(summary)
    assert "/Users/" not in json.dumps(summary)


def test_release_profiler_targets_only_fixed_nodes() -> None:
    assert ci_profile_plugin.TARGETS == frozenset(
        {
            "tests/test_packet_reviews.py::test_risk_refusal_and_operator_invoked_watch_coverage_remain_exact",
            "tests/test_decision_session_e2e.py::test_nvda_aapl_refresh_is_bounded_and_exact_results_survive_reconstruction",
        }
    )


def test_hook_emits_one_bounded_line_for_selected_call(monkeypatch) -> None:
    class Calendar:
        def sessions(self, calendar_id, start, end, *, policy):
            return (start, end)

    fake_module = ModuleType("quantmesh.data.calendars")
    fake_module.CalendarService = Calendar
    fake_module.XNYS_REGULAR_VERSION = "pinned-xnys"
    fake_module.CONTINUOUS_UTC_VERSION = "pinned-continuous"
    monkeypatch.setitem(sys.modules, fake_module.__name__, fake_module)
    lines = []
    reporter = SimpleNamespace(write_line=lines.append)
    manager = SimpleNamespace(
        get_plugin=lambda name: reporter if name == "terminalreporter" else None
    )
    item = SimpleNamespace(
        nodeid=next(iter(ci_profile_plugin.TARGETS)),
        config=SimpleNamespace(pluginmanager=manager),
    )

    call = ci_profile_plugin.pytest_runtest_call(item)
    next(call)
    assert Calendar().sessions("XNYS", date(2025, 1, 2), date(2025, 1, 2), policy="regular")
    with pytest.raises(StopIteration):
        next(call)

    assert len(lines) == 1
    assert lines[0].startswith("CI_PROFILE ")
    summary = json.loads(lines[0].removeprefix("CI_PROFILE "))
    assert summary["nodeid"] == item.nodeid
    assert summary["calendar_calls"] == 1
