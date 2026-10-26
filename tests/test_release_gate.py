import io
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tools import release_gate


def _events(logs: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (logs / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]


class Cp1252Console(io.StringIO):
    encoding = "cp1252"

    def write(self, value: str) -> int:
        value.encode(self.encoding, errors="strict")
        return super().write(value)


class _ExitWritingProcess:
    """Popen double that writes its final failure during the confirming poll."""

    pid = 4242

    def __init__(self, stdout) -> None:
        self.stdout = stdout
        self.returncode = None
        self.poll_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        del exc_type, exc, traceback
        return False

    def poll(self):
        self.poll_count += 1
        if self.poll_count == 2:
            self.stdout.write(b"FAILED tests/test_probe.py::test_probe\n")
            self.stdout.flush()
            self.returncode = 1
        return self.returncode


def test_console_summary_replaces_unencodable_log_characters() -> None:
    console = Cp1252Console()

    release_gate.print_console("golden path: 60 checks � PASSED", file=console)

    assert console.getvalue() == "golden path: 60 checks ? PASSED\n"


def test_venv_script_resolves_platform_console_entrypoint() -> None:
    path = release_gate._venv_script(Path("acceptance-venv"), "quantmesh-data")

    if os.name == "nt":
        assert path == Path("acceptance-venv/Scripts/quantmesh-data.exe")
    else:
        assert path == Path("acceptance-venv/bin/quantmesh-data")


def test_full_pytest_timeout_exceeds_measured_baseline() -> None:
    assert release_gate.FULL_PYTEST_TIMEOUT_SECONDS >= 10800


@pytest.mark.parametrize("platform", ["nt", "posix"])
def test_full_pytest_command_is_exhaustive_with_duration_reporting(
    tmp_path: Path,
    monkeypatch,
    platform,
) -> None:
    gate_root = tmp_path / "gate-root"
    gate_root.mkdir()
    commands: dict[str, list[str]] = {}

    def fake_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
        del cwd
        if args == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(["git", *args], 0, stdout="")
        if args == ["rev-parse", "--abbrev-ref", "HEAD"]:
            return subprocess.CompletedProcess(["git", *args], 0, stdout="test-branch\n")
        return subprocess.CompletedProcess(["git", *args], 0, stdout="a" * 40 + "\n")

    def fake_run_step(
        name: str,
        cmd: list[str],
        cwd: Path,
        logs: Path,
        timeout: int,
    ) -> tuple[bool, float]:
        del cwd, logs, timeout
        commands[name] = cmd
        return True, 0.0

    monkeypatch.setattr(release_gate.tempfile, "mkdtemp", lambda prefix: str(gate_root))
    monkeypatch.setattr(release_gate, "_git", fake_git)
    monkeypatch.setattr(release_gate, "run_step", fake_run_step)
    monkeypatch.setattr(sys, "argv", ["release_gate.py", "--keep"])
    node_command = release_gate._node_command
    monkeypatch.setattr(
        release_gate, "_node_command", lambda argv: node_command(argv, platform=platform)
    )

    assert release_gate.main() == 0
    prefix = ["cmd", "/c"] if platform == "nt" else []
    assert commands["npm ci (frontend deps)"] == prefix + ["npm", "ci"]
    assert commands["npm audit --audit-level=high"] == prefix + [
        "npm",
        "audit",
        "--audit-level=high",
    ]
    assert commands["frontend unit tests (vitest)"] == prefix + ["npx", "vitest", "run"]
    full_pytest = commands["full pytest suite"]
    pytest_index = full_pytest.index("pytest")
    assert full_pytest[pytest_index:] == [
        "pytest",
        "-vv",
        "--durations=50",
        "--basetemp",
        str(gate_root / "pytest-tmp"),
    ]


def test_run_step_streams_log_before_process_exit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(release_gate, "STEPS", [])
    release = tmp_path / "release-child"
    script = (
        "import pathlib, sys, time\n"
        "print('step ready', flush=True)\n"
        "while not pathlib.Path(sys.argv[1]).exists(): time.sleep(0.01)\n"
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(
            release_gate.run_step,
            "stream probe",
            [sys.executable, "-u", "-c", script, str(release)],
            tmp_path,
            tmp_path,
            15,
        )
        log = tmp_path / "01-stream-probe.log"
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if log.exists() and "step ready" in log.read_text(encoding="utf-8"):
                    break
                time.sleep(0.01)
            assert log.exists(), "step log must exist before child exit"
            assert "step ready" in log.read_text(encoding="utf-8")
            assert not result.done(), "child is still waiting for the release event"
        finally:
            release.touch()
            assert result.result(timeout=10)[0] is True


def test_run_step_reports_nonzero_exit_and_retains_failure_tail(
    tmp_path: Path,
    monkeypatch,
    capsys,
):
    monkeypatch.setattr(release_gate, "STEPS", [])
    ok, _ = release_gate.run_step(
        "failure probe",
        [
            sys.executable,
            "-c",
            "import sys; print('stdout evidence'); "
            "print('stderr evidence', file=sys.stderr); sys.exit(7)",
        ],
        tmp_path,
        tmp_path,
    )

    assert ok is False
    log = (tmp_path / "01-failure-probe.log").read_text(encoding="utf-8")
    assert "stdout evidence" in log
    assert "stderr evidence" in log
    output = capsys.readouterr().out
    assert "FAILED after" in output
    assert "stdout evidence" in output
    assert "stderr evidence" in output


def test_run_step_timeout_keeps_partial_log_and_reaps_child(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(release_gate, "STEPS", [])
    finished = tmp_path / "child-finished"
    ok, elapsed = release_gate.run_step(
        "timeout probe",
        [
            sys.executable,
            "-u",
            "-c",
            "import pathlib, sys, time; print('before timeout', flush=True); "
            "time.sleep(2); pathlib.Path(sys.argv[1]).touch()",
            str(finished),
        ],
        tmp_path,
        tmp_path,
        timeout=1,
    )

    assert ok is False
    assert elapsed < 5
    log = (tmp_path / "01-timeout-probe.log").read_text(encoding="utf-8")
    assert "before timeout" in log
    assert "TIMEOUT after 1s" in log
    assert "FAILED after" in capsys.readouterr().out
    assert _events(tmp_path)[-1]["exit_code"] != 0
    time.sleep(1.2)
    assert not finished.exists(), "timed-out child must not continue working"


def test_run_step_timeout_reaps_descendants(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(release_gate, "STEPS", [])
    finished = tmp_path / "descendant-finished"
    descendant = "import pathlib, sys, time; time.sleep(2); pathlib.Path(sys.argv[1]).touch()"
    parent = (
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {descendant!r}, sys.argv[1]], "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        "print('descendant started', flush=True)\n"
        "time.sleep(10)\n"
    )
    ok, _ = release_gate.run_step(
        "tree timeout",
        [sys.executable, "-u", "-c", parent, str(finished)],
        tmp_path,
        tmp_path,
        timeout=1,
    )

    assert ok is False
    assert "descendant started" in (tmp_path / "01-tree-timeout.log").read_text(encoding="utf-8")
    time.sleep(1.3)
    assert not finished.exists(), "timeout must stop the owned descendant, not only its launcher"


def test_run_step_emits_low_noise_lifecycle_events(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(release_gate, "STEPS", [])
    script = (
        "import time\n"
        "print('[ 25%] collecting', flush=True)\n"
        "time.sleep(0.18)\n"
        "print('[ 25%] unchanged', flush=True)\n"
        "time.sleep(0.18)\n"
    )

    ok, _ = release_gate.run_step(
        "observation probe",
        [sys.executable, "-u", "-c", script],
        tmp_path,
        tmp_path,
        progress_interval_seconds=0.05,
    )

    assert ok is True
    events = _events(tmp_path)
    assert [event["event"] for event in events] == [
        "step_started",
        "step_progress",
        "step_progress",
        "step_finished",
    ]
    started, first_progress, second_progress, finished = events
    assert started["name"] == "observation probe"
    assert isinstance(started["pid"], int)
    assert started["timeout_seconds"] == 1800
    assert started["log_path"] == str(tmp_path / "01-observation-probe.log")
    assert first_progress["pytest_percentage"] == 25
    assert first_progress["log_size_bytes"] < second_progress["log_size_bytes"]
    assert finished["exit_code"] == 0
    assert finished["log_path"] == started["log_path"]
    assert all(str(event["timestamp"]).endswith("Z") for event in events)


def test_run_step_emits_one_first_failure_event_and_timeout_exit_code(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(release_gate, "STEPS", [])
    script = (
        "import time\nprint('FAILED tests/test_probe.py::test_probe', flush=True)\ntime.sleep(2)\n"
    )

    ok, _ = release_gate.run_step(
        "failure observation probe",
        [sys.executable, "-u", "-c", script],
        tmp_path,
        tmp_path,
        timeout=1,
        progress_interval_seconds=0.05,
    )

    assert ok is False
    events = _events(tmp_path)
    assert [event["event"] for event in events].count("step_failure_seen") == 1
    failure = next(event for event in events if event["event"] == "step_failure_seen")
    assert failure["log_path"] == str(tmp_path / "01-failure-observation-probe.log")
    finished = events[-1]
    assert finished["event"] == "step_finished"
    assert isinstance(finished["exit_code"], int)


def test_run_step_accepts_zero_exit_during_final_controller_wait(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(release_gate, "STEPS", [])
    class ExitedDuringWait:
        pid = 4242
        returncode = None
        polls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def poll(self):
            self.polls += 1
            if self.polls == 2:
                self.returncode = 0
            return self.returncode

    proc = ExitedDuringWait()
    monkeypatch.setattr(release_gate.subprocess, "Popen", lambda *args, **kwargs: proc)
    ok, _ = release_gate.run_step(
        "deadline success probe",
        [sys.executable, "-u", "-c", "pass"],
        tmp_path,
        tmp_path,
        timeout=0.5,
        progress_interval_seconds=0.5,
    )

    assert ok is True
    assert proc.polls >= 2
    assert "TIMEOUT" not in (tmp_path / "01-deadline-success-probe.log").read_text()
    assert _events(tmp_path)[-1]["exit_code"] == 0


@pytest.mark.parametrize("deadline_edge", [False, True], ids=["controller-wait", "deadline"])
def test_run_step_observes_failure_written_between_sample_and_exit_poll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, deadline_edge: bool
) -> None:
    monkeypatch.setattr(release_gate, "STEPS", [])
    process: _ExitWritingProcess | None = None

    def fake_popen(*args, **kwargs):
        nonlocal process
        del args
        process = _ExitWritingProcess(kwargs["stdout"])
        return process

    clock_calls = 0

    def fake_monotonic() -> float:
        nonlocal clock_calls
        clock_calls += 1
        if clock_calls == 1:
            return 0.0
        return 2.0 if deadline_edge else 0.0

    monkeypatch.setattr(release_gate.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(release_gate.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(release_gate.time, "sleep", lambda seconds: None)

    ok, _ = release_gate.run_step(
        "exit observation probe",
        ["fake-child"],
        tmp_path,
        tmp_path,
        timeout=1,
        progress_interval_seconds=10,
    )

    assert process is not None
    assert process.poll_count == 2
    assert ok is False
    assert [event["event"] for event in _events(tmp_path)] == [
        "step_started",
        "step_failure_seen",
        "step_finished",
    ]


def test_run_step_detects_quiet_pytest_failure_progress(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(release_gate, "STEPS", [])
    script = (
        "import sys, time\n"
        "print('.F [ 1%]', flush=True)\n"
        "print('.E [ 2%]', flush=True)\n"
        "time.sleep(0.2)\n"
        "sys.exit(1)\n"
    )

    ok, _ = release_gate.run_step(
        "quiet failure probe",
        [sys.executable, "-u", "-c", script],
        tmp_path,
        tmp_path,
        progress_interval_seconds=0.05,
    )

    assert ok is False
    assert [event["event"] for event in _events(tmp_path)].count("step_failure_seen") == 1


def test_run_step_detects_mixed_quiet_pytest_failure_progress_early(
    tmp_path: Path,
    monkeypatch,
):
    monkeypatch.setattr(release_gate, "STEPS", [])
    release = tmp_path / "release-child"
    script = (
        "import pathlib, sys, time\n"
        "print('.F.s [ 1%]', flush=True)\n"
        "print('.E.xX [ 2%]', flush=True)\n"
        "while not pathlib.Path(sys.argv[1]).exists(): time.sleep(0.01)\n"
        "sys.exit(1)\n"
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        result = executor.submit(
            release_gate.run_step,
            "mixed quiet failure probe",
            [sys.executable, "-u", "-c", script, str(release)],
            tmp_path,
            tmp_path,
            15,
            0.05,
        )
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                events_path = tmp_path / "events.jsonl"
                if (
                    events_path.exists()
                    and [event["event"] for event in _events(tmp_path)].count("step_failure_seen")
                    == 1
                ):
                    break
                time.sleep(0.01)
            assert not result.done(), "failure observation must precede child completion"
            assert [event["event"] for event in _events(tmp_path)].count("step_failure_seen") == 1
        finally:
            release.touch()
            assert result.result(timeout=10)[0] is False


def test_run_step_detects_all_failure_quiet_status_rows_early(tmp_path: Path, monkeypatch):
    script = (
        "import pathlib, sys, time\n"
        "print(sys.argv[1], flush=True)\n"
        "while not pathlib.Path(sys.argv[2]).exists(): time.sleep(0.01)\n"
        "sys.exit(1)\n"
    )
    for status in ("F [100%]", "FFs [ 8%]", "EExX [ 9%]"):
        monkeypatch.setattr(release_gate, "STEPS", [])
        child_root = tmp_path / status.replace(" ", "-").replace("[", "").replace("]", "")
        child_root.mkdir()
        release = child_root / "release-child"
        with ThreadPoolExecutor(max_workers=1) as executor:
            result = executor.submit(
                release_gate.run_step,
                "all failure quiet probe",
                [sys.executable, "-u", "-c", script, status, str(release)],
                child_root,
                child_root,
                15,
                0.05,
            )
            try:
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    events_path = child_root / "events.jsonl"
                    if (
                        events_path.exists()
                        and [event["event"] for event in _events(child_root)].count(
                            "step_failure_seen"
                        )
                        == 1
                    ):
                        break
                    time.sleep(0.01)
                assert not result.done(), f"{status} must be observed before child completion"
                assert [event["event"] for event in _events(child_root)].count(
                    "step_failure_seen"
                ) == 1
            finally:
                release.touch()
                assert result.result(timeout=10)[0] is False


def test_step_log_observer_resets_after_truncate_and_regrow(tmp_path: Path):
    log_path = tmp_path / "step.log"
    observer = release_gate.StepLogObserver()
    log_path.write_text(".F [ 1%]", encoding="utf-8")
    old_offset = log_path.stat().st_size

    assert observer.sample(log_path)[2] is True
    clean_replacement = "clean status [ 2%] more output"
    assert len(clean_replacement.encode()) > old_offset
    log_path.write_text(clean_replacement, encoding="utf-8")

    _, percentage, saw_failure = observer.sample(log_path)
    assert percentage == 2
    assert saw_failure is False


def test_step_log_observer_ignores_generic_failure_letter_before_percentage(tmp_path: Path):
    log_path = tmp_path / "step.log"
    log_path.write_text("informative F [ 1%]", encoding="utf-8")

    assert release_gate.StepLogObserver().sample(log_path)[2] is False


def test_step_log_observer_requires_quiet_status_line_end(tmp_path: Path):
    log_path = tmp_path / "step.log"
    for text in ("F [7%]", "FFs [8%] \t", "EExX [9%]\t  "):
        log_path.write_text(text, encoding="utf-8")
        assert release_gate.StepLogObserver().sample(log_path)[2] is True
    for text in ("F [7%] ordinary prose", "FFs [8%]\ttrailing prose"):
        log_path.write_text(text, encoding="utf-8")
        assert release_gate.StepLogObserver().sample(log_path)[2] is False


def test_run_step_detects_marker_before_large_log_tail(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(release_gate, "STEPS", [])
    script = (
        "import sys, time\n"
        "sys.stdout.buffer.write(b'FAILED tests/test_probe.py::test_probe\\n' + b'x' * 70000)\n"
        "sys.stdout.flush()\n"
        "time.sleep(0.2)\n"
        "sys.exit(1)\n"
    )

    ok, _ = release_gate.run_step(
        "rollover failure probe",
        [sys.executable, "-u", "-c", script],
        tmp_path,
        tmp_path,
        progress_interval_seconds=0.05,
    )

    assert ok is False
    assert [event["event"] for event in _events(tmp_path)].count("step_failure_seen") == 1


def test_initial_event_failure_reaps_owned_tree(tmp_path, monkeypatch):
    monkeypatch.setattr(release_gate, "STEPS", [])
    ready = tmp_path / "ready"
    finished = tmp_path / "finished"
    child = (
        "import pathlib, sys, time; pathlib.Path(sys.argv[1]).touch(); "
        "time.sleep(1.5); pathlib.Path(sys.argv[2]).touch()"
    )
    parent = (
        "import subprocess, sys, time; "
        + f"subprocess.Popen([sys.executable, '-c', {child!r}, sys.argv[1], sys.argv[2]]); "
        "time.sleep(1.2)"
    )
    emit = release_gate._emit_event

    def fail_initial(path, event, **fields):
        if event == "step_started":
            deadline = time.monotonic() + 1
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert ready.exists()
            raise OSError("injected evidence write failure")
        emit(path, event, **fields)

    monkeypatch.setattr(release_gate, "_emit_event", fail_initial)
    with pytest.raises(OSError, match="injected evidence"):
        release_gate.run_step(
            "evidence failure",
            [sys.executable, "-c", parent, str(ready), str(finished)],
            tmp_path,
            tmp_path,
            timeout=0.5,
        )
    time.sleep(0.6)
    assert not finished.exists(), "evidence failure must stop the owned descendants"
