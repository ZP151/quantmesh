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


@pytest.mark.parametrize("outcome", ["passed", "separate_failure", "merged_subfailure"])
def test_passed_subtests_use_actual_child_terminal_evidence(tmp_path, monkeypatch, outcome):
    body = (
        "import unittest\nclass TestParts(unittest.TestCase):\n"
        "    def test_parts(self):\n"
        "        for value in range(2):\n"
        "            with self.subTest(value=value):\n"
        + (
            "                self.assertEqual(value, 0)\n"
            if outcome == "merged_subfailure"
            else "                self.assertTrue(True)\n"
        )
        + (
            "    def test_z_failure(self):\n        self.fail('separate failure')\n"
            if outcome == "separate_failure"
            else ""
        )
    )
    ok, rows, current, ordinary = child(tmp_path, monkeypatch, body)
    assert "subtests passed" in ordinary
    assert ok is (outcome == "passed")
    assert (
        current["status"]
        == {
            "passed": "PASSED",
            "separate_failure": "TEST_FAILED",
            "merged_subfailure": "INFRASTRUCTURE_ERROR",
        }[outcome]
    )
    if outcome == "separate_failure":
        assert rows[-1]["first_failure"]["nodeid"] == "test_probe.py::TestParts::test_z_failure"
        assert "separate failure" in ordinary
    elif outcome == "merged_subfailure":
        # One XML testcase combines a passed parent with a failed subtest;
        # the primary classifications cannot be independently reconciled.
        assert rows[-1]["exit_code"] == 1 and "SUBFAILED" in ordinary
        assert rows[-1]["missing_evidence"]


def subtest_terminal(tmp_path, *, passed=1, skipped=0, subpassed=2, long_success=False):
    import xml.etree.ElementTree as ET

    feedback = release_gate.PytestStepFeedback(tmp_path / "result.log", time.monotonic())
    root = ET.Element("testsuites")
    suite = ET.SubElement(
        root,
        "testsuite",
        name="pytest",
        tests=str(passed + skipped + subpassed),
        failures="0",
        errors="0",
        skipped=str(skipped),
    )
    for index in range(passed + skipped):
        case = ET.SubElement(
            suite,
            "testcase",
            classname="test_parts",
            file="test_parts.py",
            name=f"test_part_{index}",
        )
        if index == 0 and long_success:
            case.set("name", "test_long_" + "x" * (8293 - len("test_parts.py::test_long_")))
        if index >= passed:
            ET.SubElement(case, "skipped", message="explicit synthetic skip")
    ET.ElementTree(root).write(feedback.junit, encoding="utf-8", xml_declaration=True)
    summary = f"{passed} passed, " + (f"{skipped} skipped, " if skipped else "")
    summary += f"{subpassed} subtests passed"
    feedback.log.write_text(f"= {summary} in 2396.54s (0:39:56) =\n", encoding="utf-8")
    return feedback, suite


def test_full_scale_subtest_counts_require_all_primary_cases(tmp_path):
    feedback, _ = subtest_terminal(
        tmp_path, passed=8027, skipped=149, subpassed=5, long_success=True
    )
    assert feedback.finish(0, False, release_gate.StepLogObserver())
    result = json.loads(feedback.current.read_text())
    assert result["status"] == "PASSED" and result["completed"] == 8176
    assert "x" * 100 not in feedback.current.read_text()
    assert feedback.current.stat().st_size < 16384


@pytest.mark.parametrize(
    "damage",
    [
        "missing_summary",
        "wrong_subpassed",
        "wrong_passed",
        "wrong_total",
        "wrong_skipped",
        "truncated_summary",
        "malformed_xml",
        "truncated_xml",
        "failure_count",
        "error_count",
        "skipped_count",
        "zero_with_failure",
        "nonzero_without_failure",
        "unknown_summary",
        "duplicate_count",
        "no_subpassed",
        "negative_total",
    ],
)
def test_subtest_count_disagreement_stays_infrastructure_error(tmp_path, damage):
    import xml.etree.ElementTree as ET

    feedback, suite = subtest_terminal(tmp_path)
    summary = feedback.log.read_text()
    code = 0
    if damage == "missing_summary":
        summary = ""
    elif damage == "wrong_subpassed":
        summary = summary.replace("2 subtests", "1 subtests")
    elif damage == "wrong_passed":
        summary = summary.replace("1 passed", "2 passed")
    elif damage == "wrong_skipped":
        summary = summary.replace("1 passed", "1 passed, 1 skipped")
    elif damage == "truncated_summary":
        summary = summary.rstrip()
    elif damage == "unknown_summary":
        summary = summary.replace("1 passed", "1 passed, 1 unobserved")
    elif damage == "duplicate_count":
        summary = summary.replace("1 passed", "1 passed, 1 passed")
    elif damage == "no_subpassed":
        summary = summary.replace(", 2 subtests passed", "")
    elif damage in ("wrong_total", "negative_total"):
        suite.set("tests", "4" if damage == "wrong_total" else "-1")
    elif damage in ("failure_count", "error_count", "skipped_count"):
        suite.set(
            {"failure_count": "failures", "error_count": "errors", "skipped_count": "skipped"}[
                damage
            ],
            "1",
        )
    elif damage == "zero_with_failure":
        ET.SubElement(suite.find("testcase"), "failure", message="synthetic failure")
        suite.set("failures", "1")
        summary = summary.replace("1 passed", "1 failed")
    elif damage == "nonzero_without_failure":
        code = 1
    root = ET.Element("testsuites")
    root.append(suite)
    ET.ElementTree(root).write(feedback.junit, encoding="utf-8", xml_declaration=True)
    if damage == "malformed_xml":
        feedback.junit.write_text("<broken")
    elif damage == "truncated_xml":
        feedback.junit.write_bytes(feedback.junit.read_bytes()[:-20])
    feedback.log.write_text(summary, encoding="utf-8")
    assert not feedback.finish(code, False, release_gate.StepLogObserver())
    terminal = json.loads(feedback.current.read_text())
    assert terminal["status"] == "INFRASTRUCTURE_ERROR"
    assert terminal["missing_evidence"] == ["complete_consistent_junit_result"]


@pytest.mark.parametrize(
    "damage", ["empty_name", "empty_file", "duplicate", "damaged_name", "long_failure"]
)
def test_subtest_identity_validation_is_not_relaxed(tmp_path, damage):
    import copy
    import xml.etree.ElementTree as ET

    feedback, suite = subtest_terminal(tmp_path)
    case = suite.find("testcase")
    summary = feedback.log.read_text()
    if damage == "empty_name":
        case.set("name", "")
    elif damage == "empty_file":
        case.set("file", "")
    elif damage == "duplicate":
        suite.append(copy.deepcopy(case))
        suite.set("tests", "4")
        summary = summary.replace("1 passed", "2 passed")
    elif damage == "damaged_name":
        case.set("name", "test_bad\nidentity")
    else:
        case.set("name", "test_long_" + "x" * (8293 - len("test_parts.py::test_long_")))
        ET.SubElement(case, "failure", message="synthetic failure")
        suite.set("failures", "1")
        summary = summary.replace("1 passed", "1 failed")
    root = ET.Element("testsuites")
    root.append(suite)
    ET.ElementTree(root).write(feedback.junit, encoding="utf-8", xml_declaration=True)
    feedback.log.write_text(summary, encoding="utf-8")
    assert not feedback.finish(
        1 if damage == "long_failure" else 0, False, release_gate.StepLogObserver()
    )
    assert json.loads(feedback.current.read_text())["status"] == "INFRASTRUCTURE_ERROR"
    assert "x" * 100 not in feedback.current.read_text()


@pytest.mark.parametrize(
    ("first", "second", "expected"),
    [
        ("passed", "call", "INFRASTRUCTURE_ERROR"),
        ("call", "passed", "INFRASTRUCTURE_ERROR"),
        ("setup", "call", "INFRASTRUCTURE_ERROR"),
        ("call", "setup", "INFRASTRUCTURE_ERROR"),
        ("collection", "collection", "INFRASTRUCTURE_ERROR"),
        ("call", "teardown", "TEST_FAILED"),
        ("setup", "teardown", "TEST_FAILED"),
    ],
)
def test_junit_identity_has_only_consistent_primary_phases(tmp_path, first, second, expected):
    import xml.etree.ElementTree as ET

    feedback = release_gate.PytestStepFeedback(tmp_path / "result.log", time.monotonic())
    root = ET.Element("testsuites")
    phases = (first, second)
    passed, failed = phases.count("passed"), phases.count("call")
    errors = 2 - passed - failed
    suite = ET.SubElement(
        root,
        "testsuite",
        name="pytest",
        tests="3",
        failures=str(failed),
        errors=str(errors),
        skipped="0",
    )
    for phase in phases:
        case = ET.SubElement(
            suite, "testcase", file="test_parts.py", classname="test_parts", name="test_same"
        )
        if phase == "call":
            ET.SubElement(case, "failure", message="synthetic call failure")
        elif phase != "passed":
            message = (
                "collection failure"
                if phase == "collection"
                else f"failed on {phase} with synthetic error"
            )
            ET.SubElement(case, "error", message=message)
    ET.ElementTree(root).write(feedback.junit, encoding="utf-8", xml_declaration=True)
    counts = [(passed, "passed"), (failed, "failed"), (errors, "errors"), (1, "subtests passed")]
    summary = ", ".join(f"{count} {kind}" for count, kind in counts if count)
    feedback.log.write_text(f"= {summary} in 0.10s =\n", encoding="utf-8")
    assert not feedback.finish(1, False, release_gate.StepLogObserver())
    terminal = json.loads(feedback.current.read_text())
    assert terminal["status"] == expected
    if expected == "TEST_FAILED":
        assert terminal["completed"] == 1
        assert terminal["first_failure"]["phase"] == first
    else:
        assert terminal["missing_evidence"] == ["complete_consistent_junit_result"]
        assert terminal["first_failure"] is None


def test_actual_call_failure_and_teardown_error_share_one_completed_node(tmp_path, monkeypatch):
    body = (
        "import pytest\n"
        "@pytest.fixture\ndef owner():\n    yield\n    raise RuntimeError('teardown error')\n"
        "def test_first(owner):\n    assert False, 'call failure'\n"
    )
    ok, rows, current, ordinary = child(tmp_path, monkeypatch, body)
    assert not ok and current["status"] == "TEST_FAILED"
    assert current["completed"] == 1
    assert rows[-1]["first_failure"]["phase"] == "call"
    assert "call failure" in ordinary and "teardown error" in ordinary
