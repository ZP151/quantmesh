"""Bounded, non-interactive subprocess support for isolated bake-offs."""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


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


class ProcessContainmentError(RuntimeError):
    """A Windows child could not be safely contained before execution."""


class WorkRootOwnershipError(ValueError):
    """A scratch root cannot be safely treated as owned by a bake-off task."""

    def __init__(self, message: str, *, code: str = "work-root-ownership") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OwnedWorkRootPolicy:
    """Exact marker and direct-child allowlist for one destructive scratch root."""

    marker_name: str
    marker_payload: Mapping[str, object]
    owned_children: frozenset[str]


def _path_is_link_or_reparse(path: Path) -> bool:
    """Detect links and any Windows reparse point without following the target."""
    if path.is_symlink():
        return True
    if hasattr(os.path, "isjunction") and os.path.isjunction(path):
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except (FileNotFoundError, OSError):
        return False
    return bool(attributes & 0x400)  # FILE_ATTRIBUTE_REPARSE_POINT


def prepare_owned_work_root(work_root: Path, policy: OwnedWorkRootPolicy) -> None:
    """Create or safely clear a marker-owned root without following links."""
    if work_root.exists() and (
        _path_is_link_or_reparse(work_root) or not work_root.is_dir()
    ):
        raise WorkRootOwnershipError("work root must be a real directory, not a file or link")
    if not work_root.exists():
        work_root.mkdir(parents=True)
    marker = work_root / policy.marker_name
    entries = {entry.name for entry in work_root.iterdir()}
    if not marker.exists():
        if entries:
            raise WorkRootOwnershipError(
                "work root is nonempty and has no valid ownership marker"
            )
        marker.write_text(
            json.dumps(
                policy.marker_payload,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        return
    if _path_is_link_or_reparse(marker) or not marker.is_file():
        raise WorkRootOwnershipError("work-root ownership marker is not a regular file")
    try:
        marker_payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkRootOwnershipError("work-root ownership marker is unreadable") from error
    if marker_payload != policy.marker_payload:
        raise WorkRootOwnershipError("work-root ownership marker does not match this task")
    unknown = entries - policy.owned_children - {policy.marker_name}
    if unknown:
        raise WorkRootOwnershipError(
            f"marked work root contains unknown children: {', '.join(sorted(unknown))}"
        )
    owned_children = [
        work_root / name for name in sorted(entries & policy.owned_children)
    ]
    for child in owned_children:
        if _path_is_link_or_reparse(child):
            raise WorkRootOwnershipError(
                "owned child is a link or reparse point",
                code="work-root-owned-child-reparse",
            )
    for child in owned_children:
        if child.parent.resolve() != work_root.resolve():
            raise WorkRootOwnershipError("owned child escaped the resolved work root")
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


_INHERITED_ENVIRONMENT = {
    "COMSPEC",
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
_PROXY_ENVIRONMENT = {"ALL_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"}
_BLOCKED_ENVIRONMENT_MARKERS = ("API_KEY", "PASSWORD", "PRIVATE_KEY", "SECRET", "TOKEN")
_POST_KILL_TIMEOUT_SECONDS = 0.75
_CREATE_SUSPENDED = 0x00000004


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class _BasicLimitInformation(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_ulong),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_ulong),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_ulong),
        ("SchedulingClass", ctypes.c_ulong),
    ]


class _ExtendedLimitInformation(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _BasicLimitInformation),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _assign_kill_on_close_job(process: subprocess.Popen[object]) -> int | None:
    if os.name != "nt":
        return None
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return None
    limits = _ExtendedLimitInformation()
    limits.BasicLimitInformation.LimitFlags = 0x00002000
    configured = kernel32.SetInformationJobObject(
        ctypes.c_void_p(job), 9, ctypes.byref(limits), ctypes.sizeof(limits)
    )
    assigned = configured and kernel32.AssignProcessToJobObject(
        ctypes.c_void_p(job), ctypes.c_void_p(int(process._handle))  # type: ignore[attr-defined]
    )
    if not assigned:
        kernel32.CloseHandle(ctypes.c_void_p(job))
        return None
    return int(job)


def _close_job(job: int | None) -> None:
    if job is not None:
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(job))  # type: ignore[attr-defined]


def _resume_windows_process(process: subprocess.Popen[object]) -> bool:
    ntdll = ctypes.windll.ntdll  # type: ignore[attr-defined]
    ntdll.NtResumeProcess.argtypes = [ctypes.c_void_p]
    ntdll.NtResumeProcess.restype = ctypes.c_long
    return ntdll.NtResumeProcess(
        ctypes.c_void_p(int(process._handle))  # type: ignore[attr-defined]
    ) == 0


def _terminate_suspended_process(
    process: subprocess.Popen[object], job: int | None
) -> None:
    if job is not None:
        ctypes.windll.kernel32.TerminateJobObject(  # type: ignore[attr-defined]
            ctypes.c_void_p(job), 1
        )
    else:
        process.kill()
    try:
        process.wait(timeout=_POST_KILL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=_POST_KILL_TIMEOUT_SECONDS)


def _validate_proxy(name: str, value: str) -> None:
    if name.upper() == "NO_PROXY":
        return
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(f"credential-bearing proxy URL is forbidden: {name}")


def _child_environment(
    extra: Mapping[str, str] | None, *, inherit_proxy: bool
) -> dict[str, str]:
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
    if inherit_proxy:
        for name, value in os.environ.items():
            upper_name = name.upper()
            if upper_name in _PROXY_ENVIRONMENT:
                _validate_proxy(upper_name, value)
                environment[upper_name] = value
    for name, value in (extra or {}).items():
        upper_name = name.upper()
        if any(marker in upper_name for marker in _BLOCKED_ENVIRONMENT_MARKERS):
            raise ValueError(f"credential-like environment variable is forbidden: {name}")
        if upper_name in _PROXY_ENVIRONMENT:
            _validate_proxy(upper_name, value)
        environment[name] = value
    return environment


def _portable_command(command: Sequence[str], placeholders: Mapping[Path, str]) -> str:
    replacements = sorted(
        (
            (candidate, replacement)
            for path, replacement in placeholders.items()
            for candidate in dict.fromkeys((str(path), str(path.resolve())))
        ),
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


def _terminate_process_tree(
    process: subprocess.Popen[object], job: int | None
) -> str:
    if os.name == "nt":
        if job is not None and ctypes.windll.kernel32.TerminateJobObject(  # type: ignore[attr-defined]
            ctypes.c_void_p(job), 1
        ):
            mechanism = "job_object_terminated"
        else:
            try:
                killed = subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=_POST_KILL_TIMEOUT_SECONDS,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                mechanism = f"taskkill_exit={killed.returncode}"
            except subprocess.TimeoutExpired:
                mechanism = "taskkill_timeout"
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            mechanism = "process_group_sigkill"
        except ProcessLookupError:
            mechanism = "process_group_already_exited"
    try:
        process.wait(timeout=_POST_KILL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=_POST_KILL_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            return f"{mechanism}; direct_process_termination_unverified"
    return f"{mechanism}; direct_process_termination_verified"


def run_command(
    command: Sequence[str],
    *,
    cwd: Path,
    logs_root: Path,
    label: str,
    placeholders: Mapping[Path, str],
    timeout_seconds: float,
    env: Mapping[str, str] | None = None,
    inherit_proxy: bool = False,
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
    child_environment = _child_environment(env, inherit_proxy=inherit_proxy)
    started = time.perf_counter()
    creation_flags = (
        subprocess.CREATE_NO_WINDOW
        | subprocess.CREATE_NEW_PROCESS_GROUP
        | _CREATE_SUSPENDED
        if os.name == "nt"
        else 0
    )
    with stdout_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr_handle:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=child_environment,
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            creationflags=creation_flags,
            start_new_session=os.name != "nt",
        )
        job: int | None = None
        try:
            if os.name == "nt":
                try:
                    job = _assign_kill_on_close_job(process)
                except Exception as error:
                    _terminate_suspended_process(process, None)
                    raise ProcessContainmentError(
                        "Windows process containment setup failed: job-assignment"
                    ) from error
                if job is None:
                    _terminate_suspended_process(process, None)
                    raise ProcessContainmentError(
                        "Windows process containment setup failed: job-assignment"
                    )
                try:
                    resumed = _resume_windows_process(process)
                except Exception as error:
                    _terminate_suspended_process(process, job)
                    raise ProcessContainmentError(
                        "Windows process containment setup failed: process-resume"
                    ) from error
                if not resumed:
                    _terminate_suspended_process(process, job)
                    raise ProcessContainmentError(
                        "Windows process containment setup failed: process-resume"
                    )
            peak_rss_mb = 0.0
            timed_out = False
            while True:
                peak_rss_mb = max(peak_rss_mb, _peak_process_rss_mb(process))
                remaining = timeout_seconds - (time.perf_counter() - started)
                if remaining <= 0:
                    timed_out = True
                    termination = _terminate_process_tree(process, job)
                    break
                try:
                    process.wait(timeout=min(0.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue

            duration_seconds = time.perf_counter() - started
            peak_rss_mb = max(peak_rss_mb, _peak_process_rss_mb(process))
            if timed_out:
                stderr_handle.write(
                    f"\ncommand timed out after {timeout_seconds:.3f} seconds; "
                    f"{termination}\n"
                )
                exit_code = -1
            else:
                exit_code = process.returncode
        finally:
            _close_job(job)
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
