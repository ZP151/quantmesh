import io
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tools import release_gate


class Cp1252Console(io.StringIO):
    encoding = "cp1252"

    def write(self, value: str) -> int:
        value.encode(self.encoding, errors="strict")
        return super().write(value)


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
    tmp_path: Path, monkeypatch, capsys,
):
    monkeypatch.setattr(release_gate, "STEPS", [])
    ok, _ = release_gate.run_step(
        "failure probe",
        [sys.executable, "-c", "import sys; print('stdout evidence'); "
         "print('stderr evidence', file=sys.stderr); sys.exit(7)"],
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
        [sys.executable, "-u", "-c",
         "import pathlib, sys, time; print('before timeout', flush=True); "
         "time.sleep(2); pathlib.Path(sys.argv[1]).touch()", str(finished)],
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
        "tree timeout", [sys.executable, "-u", "-c", parent, str(finished)],
        tmp_path, tmp_path, timeout=1,
    )

    assert ok is False
    assert "descendant started" in (tmp_path / "01-tree-timeout.log").read_text(encoding="utf-8")
    time.sleep(1.3)
    assert not finished.exists(), "timeout must stop the owned descendant, not only its launcher"
