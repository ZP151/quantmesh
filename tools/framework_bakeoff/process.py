"""Bounded, non-interactive subprocess support for isolated bake-offs."""

from __future__ import annotations

import ctypes
import os
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandResult:
    """Portable command metadata with raw output retained under the work root."""

    command: str
    exit_code: int
    duration_seconds: float
    peak_rss_mb: float
    stdout_log: str
    stderr_log: str


class CommandFailure(RuntimeError):
    """A checked command failed without leaking raw local paths into evidence."""

    def __init__(self, result: CommandResult) -> None:
        super().__init__(f"command failed with exit code {result.exit_code}: {result.command}")
        self.command = result.command
        self.exit_code = result.exit_code
        self.stdout_log = result.stdout_log
        self.stderr_log = result.stderr_log
        self.duration_seconds = result.duration_seconds
        self.peak_rss_mb = result.peak_rss_mb


_INHERITED_ENVIRONMENT = {
    "COMSPEC",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "NO_PROXY",
    "PATH",
    "PATHEXT",
    "REQUESTS_CA_BUNDLE",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "SYSTEMDRIVE",
    "SYSTEMROOT",
    "TEMP",
    "TMP",
    "WINDIR",
}
_BLOCKED_ENVIRONMENT_MARKERS = ("API_KEY", "PASSWORD", "PRIVATE_KEY", "SECRET", "TOKEN")


def _child_environment(extra: Mapping[str, str] | None) -> dict[str, str]:
    environment = {
        name: value for name, value in os.environ.items() if name.upper() in _INHERITED_ENVIRONMENT
    }
    environment.update(
        {
            "GCM_INTERACTIVE": "Never",
            "GIT_TERMINAL_PROMPT": "0",
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUNBUFFERED": "1",
            "PYTHONUTF8": "1",
        }
    )
    for name, value in (extra or {}).items():
        upper_name = name.upper()
        if any(marker in upper_name for marker in _BLOCKED_ENVIRONMENT_MARKERS):
            raise ValueError(f"credential-like environment variable is forbidden: {name}")
        environment[name] = value
    return environment


def _portable_command(command: Sequence[str], placeholders: Mapping[Path, str]) -> str:
    replacements = sorted(
        ((str(path.resolve()), replacement) for path, replacement in placeholders.items()),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    portable: list[str] = []
    for argument in command:
        normalized = str(argument)
        for local_path, replacement in replacements:
            normalized = normalized.replace(local_path, replacement)
            normalized = normalized.replace(local_path.replace("\\", "/"), replacement)
        portable.append(normalized)
    return subprocess.list2cmdline(portable)


def _peak_process_rss_mb(process: subprocess.Popen[str]) -> float:
    if os.name != "nt":
        return 0.0

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    try:
        handle = ctypes.c_void_p(int(process._handle))  # type: ignore[attr-defined]
        succeeded = ctypes.windll.psapi.GetProcessMemoryInfo(  # type: ignore[attr-defined]
            handle, ctypes.byref(counters), counters.cb
        )
    except (AttributeError, OSError, TypeError, ValueError):
        return 0.0
    if not succeeded:
        return 0.0
    return counters.PeakWorkingSetSize / (1024 * 1024)


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    logs_root: Path,
    label: str,
    placeholders: Mapping[Path, str],
    timeout_seconds: float,
    env: Mapping[str, str] | None = None,
    check: bool = True,
) -> CommandResult:
    """Run one argv-only command with bounded time, sanitized env, and raw logs."""
    if not command:
        raise ValueError("command must not be empty")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if not label or any(character in label for character in "\\/:"):
        raise ValueError("label must be a portable filename stem")

    cwd = cwd.resolve()
    logs_root = logs_root.resolve()
    logs_root.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_root / f"{label}.stdout.log"
    stderr_path = logs_root / f"{label}.stderr.log"
    display_command = _portable_command(command, placeholders)
    started = time.perf_counter()
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        list(command),
        cwd=cwd,
        env=_child_environment(env),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=creation_flags,
    )
    peak_rss_mb = 0.0
    timed_out = False
    while True:
        peak_rss_mb = max(peak_rss_mb, _peak_process_rss_mb(process))
        remaining = timeout_seconds - (time.perf_counter() - started)
        if remaining <= 0:
            timed_out = True
            process.kill()
            stdout, stderr = process.communicate()
            break
        try:
            stdout, stderr = process.communicate(timeout=min(0.1, remaining))
            break
        except subprocess.TimeoutExpired:
            continue

    duration_seconds = time.perf_counter() - started
    peak_rss_mb = max(peak_rss_mb, _peak_process_rss_mb(process))
    if timed_out:
        stderr = f"{stderr}\ncommand timed out after {timeout_seconds:.3f} seconds\n"
        exit_code = -1
    else:
        exit_code = process.returncode
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    relative_root = logs_root.parent
    result = CommandResult(
        command=display_command,
        exit_code=exit_code,
        duration_seconds=duration_seconds,
        peak_rss_mb=peak_rss_mb,
        stdout_log=stdout_path.relative_to(relative_root).as_posix(),
        stderr_log=stderr_path.relative_to(relative_root).as_posix(),
    )
    if check and result.exit_code != 0:
        raise CommandFailure(result)
    return result
