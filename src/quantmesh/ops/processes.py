"""One finite, argv-only child-process boundary for operational commands."""

from __future__ import annotations

import math
import os
import signal
import subprocess
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class ProcessResult(_FrozenContract):
    argv: tuple[str, ...] = Field(min_length=1)
    returncode: int | None
    stdout: str
    stderr: str
    elapsed_seconds: float = Field(ge=0)
    timed_out: bool
    tree_terminated: bool

    @field_validator("argv")
    @classmethod
    def argv_is_safe(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value or "\x00" in value for value in values):
            raise ValueError("argv entries must be nonempty and contain no NUL")
        return values

    @model_validator(mode="after")
    def termination_state_is_consistent(self) -> Self:
        if self.tree_terminated and not self.timed_out:
            raise ValueError("only a timed-out child may report tree termination")
        return self


def run_process(
    argv: Sequence[str],
    *,
    timeout_seconds: float,
    cwd: Path,
) -> ProcessResult:
    """Run one child under a finite monotonic deadline and kill descendants."""
    if isinstance(argv, (str, bytes)):
        raise TypeError("argv must be a sequence, not a command string")
    command = tuple(argv)
    if not command or any(
        not isinstance(value, str) or not value or "\x00" in value for value in command
    ):
        raise ValueError("argv must contain only nonempty strings without NUL")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("process timeout must be finite and positive")
    directory = Path(cwd)
    if not directory.is_dir():
        raise ValueError("process cwd must be an existing directory")

    options: dict[str, Any] = {
        "cwd": directory,
        "text": True,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "shell": False,
    }
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True

    started = time.monotonic()
    process = subprocess.Popen(command, **options)
    timed_out = False
    tree_terminated = False
    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        tree_terminated = _terminate_process_tree(process, timeout_seconds=10.0)
        try:
            stdout, stderr = process.communicate(timeout=10.0)
        except subprocess.TimeoutExpired:
            stdout, stderr = "", "process tree did not terminate after deadline"
            tree_terminated = False
    elapsed = time.monotonic() - started
    return ProcessResult(
        argv=command,
        returncode=process.returncode,
        stdout=stdout or "",
        stderr=stderr or "",
        elapsed_seconds=max(0.0, elapsed),
        timed_out=timed_out,
        tree_terminated=tree_terminated,
    )


def _terminate_process_tree(
    process: subprocess.Popen[str], *, timeout_seconds: float
) -> bool:
    if process.returncode is not None:
        return True
    if os.name == "nt":
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                text=True,
                capture_output=True,
                shell=False,
                timeout=timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=min(timeout_seconds, 5.0))
        return True
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=max(0.1, timeout_seconds - 5.0))
            return True
        except (OSError, subprocess.SubprocessError):
            return False
    except (OSError, ProcessLookupError):
        return process.poll() is not None
