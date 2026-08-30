import math
import subprocess
from pathlib import Path

import pytest

import quantmesh.ops.processes as process_module
from quantmesh.ops.processes import run_process


@pytest.mark.parametrize("timeout", (0, -1, math.inf, math.nan))
def test_process_boundary_rejects_nonfinite_or_nonpositive_deadline(
    tmp_path: Path,
    timeout: float,
) -> None:
    with pytest.raises(ValueError, match="timeout"):
        run_process(("python", "--version"), timeout_seconds=timeout, cwd=tmp_path)


def test_process_boundary_accepts_only_nonempty_argv(tmp_path: Path) -> None:
    for argv in ("python --version", (), ("python", "")):
        with pytest.raises((TypeError, ValueError), match="argv"):
            run_process(argv, timeout_seconds=1, cwd=tmp_path)


def test_timeout_terminates_the_complete_mocked_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, object]] = []

    class FakeProcess:
        pid = 4321
        returncode = None

        def __init__(self) -> None:
            self.communications = 0

        def communicate(self, timeout: float):
            calls.append(("communicate", timeout))
            self.communications += 1
            if self.communications == 1:
                raise subprocess.TimeoutExpired(["collector"], timeout)
            self.returncode = -9
            return "partial-out", "partial-err"

    fake = FakeProcess()

    def popen(argv, **kwargs):
        calls.append(("popen", (tuple(argv), kwargs)))
        return fake

    def terminate(process, *, timeout_seconds: float) -> bool:
        calls.append(("terminate", (process.pid, timeout_seconds)))
        return True

    monotonic = iter((10.0, 13.5))
    monkeypatch.setattr(process_module.subprocess, "Popen", popen)
    monkeypatch.setattr(process_module, "_terminate_process_tree", terminate)
    monkeypatch.setattr(process_module.time, "monotonic", lambda: next(monotonic))

    result = run_process(
        ("collector", "--bounded"),
        timeout_seconds=3,
        cwd=tmp_path,
    )

    assert result.argv == ("collector", "--bounded")
    assert result.timed_out is True
    assert result.tree_terminated is True
    assert result.returncode == -9
    assert result.elapsed_seconds == 3.5
    assert [name for name, _ in calls] == [
        "popen",
        "communicate",
        "terminate",
        "communicate",
    ]


def test_success_preserves_argv_and_captured_streams(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeProcess:
        pid = 12
        returncode = 0

        def communicate(self, timeout: float):
            assert timeout == 5
            return "stdout", "stderr"

    captured: dict[str, object] = {}

    def popen(argv, **kwargs):
        captured["argv"] = tuple(argv)
        captured["kwargs"] = kwargs
        return FakeProcess()

    monotonic = iter((1.0, 1.25))
    monkeypatch.setattr(process_module.subprocess, "Popen", popen)
    monkeypatch.setattr(process_module.time, "monotonic", lambda: next(monotonic))

    result = run_process(
        ("python", "-c", "print('ok')"),
        timeout_seconds=5,
        cwd=tmp_path,
    )

    assert captured["argv"] == ("python", "-c", "print('ok')")
    assert captured["kwargs"]["shell"] is False
    assert result.stdout == "stdout"
    assert result.stderr == "stderr"
    assert result.timed_out is False
    assert result.tree_terminated is False


@pytest.mark.skipif(process_module.os.name != "nt", reason="Windows process-tree contract")
def test_windows_tree_termination_uses_taskkill_for_descendants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        pid = 4321
        returncode = None

    def run(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(process_module.subprocess, "run", run)

    assert process_module._terminate_process_tree(  # noqa: SLF001
        FakeProcess(), timeout_seconds=7
    )
    assert captured["argv"] == ["taskkill", "/PID", "4321", "/T", "/F"]
    assert captured["kwargs"] == {
        "text": True,
        "capture_output": True,
        "shell": False,
        "timeout": 7,
        "check": False,
    }
