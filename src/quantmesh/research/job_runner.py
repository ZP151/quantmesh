"""Recoverable registered fixture baselines in an owned bounded process tree.

Windows uses an OS Job Object (tree lifetime, memory and CPU affinity).
Linux requires explicitly constructed crash-safe containment; fractional CPU quotas
and other platforms are explicitly unsupported, never silently unbounded.
No user code, vendor query, model call or execution authority is accepted.
"""

from __future__ import annotations

import ctypes
import hashlib
import importlib.metadata
import json
import os
import platform
import stat
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from quantmesh.data._fixture_read_scope import bind_reader
from quantmesh.research._fixture_handles import (
    DirectoryHandles,
    UnsupportedSnapshotProfile,
    require_snapshot_profile,
)
from quantmesh.research._fixture_reader import FixtureReader
from quantmesh.research._launch_deadline import (
    LaunchDeadlineExceeded,
    _check_launch_deadline,
    _launch_deadline,
)
from quantmesh.research.baselines import run_baseline_report
from quantmesh.research.fixture_snapshot import copy_fixture_snapshot
from quantmesh.research.job_artifacts import (
    _canonical,
    _contained,
    canonical_result,
    publish_result,
)
from quantmesh.research.job_store import JobStore, SQLiteJobStore
from quantmesh.research.jobs import (
    HEARTBEAT_SECONDS,
    DatasetRejected,
    JobRecord,
    RunBudget,
    canonical_request_digest,
)
from quantmesh.research.linux_owned import LinuxContainmentError, LinuxOwnedProcess
from quantmesh.research.reports import ReportRegistry, StrategyReport
from quantmesh.research.strategy_registry import get_strategy, validate_dataset
from quantmesh.research.worker_execution import (
    _bind_worker_job,
    _execution,
    _observe_worker_call,
    _stop_event,
    _worker_unwinding,
)
from quantmesh.research.worker_stop import _WorkerStop

_POLL_SECONDS = 0.1
_MAX_OUTPUT_BYTES = 16 * 1024 * 1024
_MAX_INPUT_METADATA_BYTES = 256 * 1024
_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SOURCE_ROOT.parent
# Sibling attempt mkdir changes ancestors held by protected snapshot copies.
# Coordinate preparation within this process without relaxing namespace checks.
_SNAPSHOT_LOCK = Lock()


def runtime_fingerprint(
    *,
    manifest_path: Path | None = None,
    manifest_sha256: str | None = None,
    execution_profile: str | None = None,
) -> dict:
    """Bind source bytes and installed dependency metadata, independently of engine SHA.

    RECORD pins the complete installed distribution inventory. This fingerprint
    identifies the environment; it is not an attestation of every installed byte.
    """
    if manifest_path is not None or manifest_sha256 is not None:
        from quantmesh.research.worker_build import measure_worker_runtime

        if execution_profile is not None:
            return measure_worker_runtime(
                manifest_path, manifest_sha256=manifest_sha256, execution_profile=execution_profile
            )
        return measure_worker_runtime(manifest_path, manifest_sha256=manifest_sha256)
    if execution_profile is not None:
        raise ValueError("profile requires image byte admission")
    source = [
        (p.relative_to(_SOURCE_ROOT).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest())
        for p in sorted((_SOURCE_ROOT / "quantmesh").rglob("*.py"))
    ]
    build = hashlib.sha256(_canonical(source)).hexdigest()
    dependencies = []
    for dist in importlib.metadata.distributions():
        if dist.metadata["Name"].lower() == "quantmesh":
            continue  # Editable project identity is bound by source bytes above.
        metadata = {
            name: hashlib.sha256((dist.read_text(name) or "").encode()).hexdigest()
            for name in ("METADATA", "RECORD", "direct_url.json")
        }
        dependencies.append((dist.metadata["Name"], dist.version, metadata))
    executable_digest = hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest()
    dependency = hashlib.sha256(
        _canonical(
            dict(
                packages=[json.loads(d) for d in sorted({_canonical(d) for d in dependencies})],
                python_version=sys.version,
                python_executable_digest=executable_digest,
                platform=sys.platform,
                machine=platform.machine(),
            )
        )
    ).hexdigest()
    head = subprocess.run(
        ["git", "-C", str(_REPO), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    ).stdout.strip()
    return dict(
        build_digest=build,
        dependency_digest=dependency,
        git_commit=head,
        python_version=sys.version,
        python_executable_digest=executable_digest,
    )


def _verify_identity(job: JobRecord) -> None:
    if canonical_request_digest(job.request) != job.request_digest:
        raise ValueError("request digest mismatch")
    spec = get_strategy(job.request.strategy_id, job.request.strategy_version)
    if spec.implementation_digest != job.implementation_digest:
        raise ValueError("queued engine changed")


def _verify(job: JobRecord, inputs_root: Path) -> None:
    _verify_identity(job)
    validate_dataset(job.request, inputs_root, datetime.now(UTC))


def _snapshot(job: JobRecord, source: Path, destination: Path) -> None:
    """Check queued metadata and copy bytes; content admission belongs to the child."""
    require_snapshot_profile()
    if canonical_request_digest(job.request) != job.request_digest:
        raise ValueError("request digest mismatch")
    spec = get_strategy(job.request.strategy_id, job.request.strategy_version)
    if spec.implementation_digest != job.implementation_digest:
        raise ValueError("queued engine changed")
    copy_fixture_snapshot(job, source, destination)


class UnsupportedLimits(ValueError):
    """The OS cannot enforce the requested tree/budget; fail before baseline work."""


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_longlong),
        ("job_time", ctypes.c_longlong),
        ("flags", ctypes.c_ulong),
        ("min_ws", ctypes.c_size_t),
        ("max_ws", ctypes.c_size_t),
        ("active", ctypes.c_ulong),
        ("affinity", ctypes.c_size_t),
        ("priority", ctypes.c_ulong),
        ("scheduling", ctypes.c_ulong),
    ]


class _IOCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "read_ops",
            "write_ops",
            "other_ops",
            "read_bytes",
            "write_bytes",
            "other_bytes",
        )
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io", _IOCounters),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process", ctypes.c_size_t),
        ("peak_job", ctypes.c_size_t),
    ]


class _OwnedChild:
    """Only this Popen handle/session or Job Object can be stopped by this owner."""

    def __init__(self, command: list[str], budget: RunBudget, directory: Path):
        self.job_handle = None
        self.process = None
        if budget.cpu_limit != 1.0 or os.name != "nt" or sys.platform != "win32":
            raise UnsupportedLimits("requested platform/CPU quota unsupported")
        # Minimal environment: no inherited credentials, provider config or user site.
        env = {
            k: v
            for k, v in os.environ.items()
            if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "LANG"}
        }
        env.update(
            PYTHONPATH=str(_SOURCE_ROOT),
            PYTHONNOUSERSITE="1",
            PYTHONDONTWRITEBYTECODE="1",
            OPENBLAS_NUM_THREADS="1",
            OMP_NUM_THREADS="1",
            USERPROFILE=str(directory),
            HOME=str(directory),
        )
        self.log = (directory / "child.log").open("wb")
        try:
            # Child blocks on stdin until parent has established OS ownership and limits.
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=self.log,
                cwd=directory,
                env=env,
                creationflags=0x08000000 | 0x4,  # hidden and suspended before launcher can spawn
            )
            self._windows_limits(budget)
            ntdll = ctypes.windll.ntdll
            ntdll.NtResumeProcess.argtypes = [ctypes.c_void_p]
            ntdll.NtResumeProcess.restype = ctypes.c_long
            if ntdll.NtResumeProcess(ctypes.c_void_p(int(self.process._handle))) != 0:
                raise UnsupportedLimits("cannot resume owned process")
            self.process.stdin.write(b"go\n")
            self.process.stdin.flush()
            self.process.stdin.close()
        except BaseException:
            self.close()
            raise

    def _windows_limits(self, budget):
        kernel = ctypes.windll.kernel32
        kernel.CreateJobObjectW.restype = ctypes.c_void_p
        handle = kernel.CreateJobObjectW(None, None)
        if not handle:
            raise UnsupportedLimits("cannot create owned OS job")
        self.job_handle = handle
        limits = _ExtendedLimits()
        # One affinity core limits CPU to at most one processor; job memory is tree-wide.
        mask, system = ctypes.c_size_t(), ctypes.c_size_t()
        process_handle = ctypes.c_void_p(int(self.process._handle))
        if not kernel.GetProcessAffinityMask(
            process_handle, ctypes.byref(mask), ctypes.byref(system)
        ):
            raise UnsupportedLimits("cannot resolve owned CPU affinity")
        limits.basic.flags = 0x2000 | 0x200 | 0x10  # kill-on-close, job memory, affinity
        limits.basic.affinity = mask.value & -mask.value
        limits.job_memory = budget.memory_mib * 1024 * 1024
        if not kernel.SetInformationJobObject(
            ctypes.c_void_p(handle), 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            raise UnsupportedLimits("cannot enforce owned OS limits")
        if not kernel.AssignProcessToJobObject(ctypes.c_void_p(handle), process_handle):
            raise UnsupportedLimits("cannot assign owned process tree")

    def poll(self) -> int | None:
        return self.process.poll()

    def pulse(self) -> None:
        """Windows Job Object lifetime has no owner-pulse channel."""

    def close(self):
        if self.job_handle is not None:
            kernel = ctypes.windll.kernel32
            kernel.TerminateJobObject(ctypes.c_void_p(self.job_handle), 1)
            kernel.CloseHandle(ctypes.c_void_p(self.job_handle))
            self.job_handle = None
        if self.process is not None:
            # A created job may be empty if configuration/assignment failed.
            # The direct child is still ours and must always be reaped.
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=5)
        self.log.close()


def _child_command(attempt: Path) -> list[str]:
    # Boot gate precedes importing DuckDB/numpy or any baseline code.
    boot = (
        "import sys; token=sys.stdin.readline(); "
        "sys.exit(3) if token != 'go\\n' else None; "
        "from quantmesh.research.job_runner import _child_main; _child_main(sys.argv[1])"
    )
    return [sys.executable, "-B", "-c", boot, str(attempt)]


def _child_main(
    directory: str,
    *,
    output_directory: str | None = None,
    build_manifest: Path | None = None,
    manifest_sha256: str | None = None,
    execution_profile: str | None = None,
    before_import_runtime: dict | None = None,
) -> None:
    path = Path(directory)
    output = Path(output_directory) if output_directory is not None else path
    try:
        if execution_profile is not None and (
            before_import_runtime is None or output_directory is None or build_manifest is None
        ):
            raise ValueError("profile requires actual pre-import measurement")
        if output_directory is not None:
            if (
                sys.platform != "linux"
                or build_manifest is None
                or manifest_sha256 is None
                or not path.is_absolute()
                or not output.is_absolute()
                or output.is_relative_to(path)
                or path.is_relative_to(output)
            ):
                raise ValueError("Linux child admission missing")
            _contained(path, path / "job.json")
            _contained(output, output / "result.json")
        # Reject runtime drift and unsafe metadata before decoding any job input.
        if execution_profile is None:
            runtime = runtime_fingerprint(
                manifest_path=build_manifest, manifest_sha256=manifest_sha256
            )
        else:
            from quantmesh.research.worker_build import runtime_with_profile

            runtime = runtime_fingerprint(
                manifest_path=build_manifest,
                manifest_sha256=manifest_sha256,
                execution_profile=execution_profile,
            )
            if runtime != runtime_with_profile(before_import_runtime, execution_profile):
                raise ValueError("runtime changed after pre-import measurement")
        if runtime != json.loads(
            _read_child_file(path, path / "runtime.json", _MAX_INPUT_METADATA_BYTES)
        ):
            raise ValueError("runtime changed before execution")
        job = JobRecord.model_validate_json(
            _read_child_file(path, path / "job.json", _MAX_INPUT_METADATA_BYTES)
        )
        _verify_identity(job)
        if execution_profile is not None:
            from quantmesh.research.worker_build import validate_registered_job

            validate_registered_job(job, execution_profile)
        r = job.request
        inputs_root = path / "inputs"
        with FixtureReader(job, inputs_root, time.monotonic() + r.budget.timeout_seconds) as reader:
            with bind_reader(inputs_root, r.dataset.dataset_id, reader):
                _verify(job, inputs_root)
                registry = ReportRegistry(output / "registry", lake_root=inputs_root)
                report = run_baseline_report(
                    dataset=r.dataset.dataset_id,
                    revision=r.dataset.revision,
                    strategy=r.strategy_id,
                    interval=r.interval,
                    universe=r.universe,
                    window_spec=r.window_spec,
                    costs=r.costs,
                    commit=job.implementation_digest,
                    registry=registry,
                )
                report.evidence.update(
                    request_digest=job.request_digest,
                    manifest_digest=r.dataset.manifest_digest,
                    export_digest=r.dataset.export_digest,
                    build_digest=runtime["build_digest"],
                    dependency_digest=runtime["dependency_digest"],
                )
                if execution_profile is not None:
                    from quantmesh.research.worker_build import profile_report_evidence

                    report.evidence.update(profile_report_evidence(runtime))
                _verify(job, inputs_root)
                (output / "receipt.json").write_bytes(
                    _canonical(
                        dict(
                            report=report.model_dump(mode="json"),
                            runtime=runtime,
                            attempt=job.attempt,
                            owner=job.lease_owner,
                            fixture_only=True,
                            limits=dict(
                                platform=sys.platform,
                                memory_mib=r.budget.memory_mib,
                                cpu_limit=1.0,
                                memory_semantics="job_commit"
                                if os.name == "nt"
                                else "cgroup_v2"
                                if output_directory is not None
                                else "process_address_space",
                                tree_owned=True,
                            ),
                        )
                    )
                )
                (output / "result.json").write_bytes(canonical_result(report))
    except DatasetRejected:
        (output / "error.json").write_text('{"error_code":"dataset_rejected"}')
        raise SystemExit(2) from None
    except Exception:
        (output / "error.json").write_text('{"error_code":"worker_failed"}')
        raise SystemExit(2) from None


def _read_child_file(root: Path, path: Path, limit: int) -> bytes:
    with DirectoryHandles({"read": root.absolute()}) as handles:
        path = path.absolute()
        fd = handles.open_file(path, os.O_RDONLY | os.O_NONBLOCK, "read")
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 0 < before.st_size <= limit
        ):
            raise ValueError("invalid child file")
        chunks, remaining = [], limit + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 512 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after, named = os.fstat(fd), handles.file_stat(path, "read")

        def identity(info):
            return (
                info.st_dev,
                info.st_ino,
                info.st_mode,
                info.st_nlink,
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
                info.st_uid,
                info.st_gid,
            )

        if (
            identity(before) != identity(after)
            or identity(after) != identity(named)
            or len(raw) != before.st_size
        ):
            raise ValueError("child file changed")
        return raw


def _validated_child_result(job: JobRecord, owner: str, runtime: dict, output: Path) -> bytes:
    raw = _read_child_file(output, output / "result.json", _MAX_OUTPUT_BYTES)
    receipt_raw = _read_child_file(output, output / "receipt.json", _MAX_OUTPUT_BYTES - len(raw))
    receipt = json.loads(receipt_raw)
    if (
        not isinstance(receipt, dict)
        or _canonical(receipt) != receipt_raw
        or receipt.get("runtime") != runtime
        or type(receipt.get("attempt")) is not int
        or receipt["attempt"] != job.attempt
        or receipt.get("owner") != owner
    ):
        raise ValueError("worker receipt mismatch")
    report = StrategyReport.model_validate(receipt.get("report"))
    from quantmesh.research.worker_build import validate_report_profile

    validate_report_profile(runtime, report.evidence)
    if any(
        report.evidence.get(key) != runtime[key] for key in ("build_digest", "dependency_digest")
    ):
        raise ValueError("worker report runtime mismatch")
    if "execution_profile" in runtime and receipt.get("fixture_only") is not True:
        raise ValueError("worker profile claim mismatch")
    if canonical_result(report) != raw:
        raise ValueError("worker result mismatch")
    return raw


def run_next_job(
    store: JobStore, owner: str, inputs_root: Path, artifacts_root: Path
) -> JobRecord | None:
    """Claim one job; execute a private snapshot; fence immutable report publication."""
    stop_event = _stop_event.get()
    if stop_event is not None and stop_event.is_set():
        return None
    job = _observe_worker_call("claim", lambda: store.claim(owner, datetime.now(UTC)))
    if job is None:
        return None
    _bind_worker_job(job)
    if stop_event is not None and stop_event.is_set():
        return _observe_worker_call(
            "current_record", lambda: store.get(job.operator_id, job.job_id)
        )
    attempt = (
        Path(artifacts_root).absolute()
        / job.job_id
        / "receipts"
        / (f"attempt-{job.attempt}-{uuid.uuid4().hex}")
    )
    child = None
    execution = _execution.get()
    started = time.monotonic()
    deadline_token = _launch_deadline.set(started + job.request.budget.timeout_seconds)
    error = "worker_failed"
    attempt_failed = False
    try:
        if stop_event is not None and stop_event.is_set():
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        bundle = attempt / "bundle" if execution is not None else attempt
        output = attempt / "output" if execution is not None else attempt
        contended = False
        waiting_heartbeat = started
        while True:
            if stop_event is not None and stop_event.is_set():
                return _observe_worker_call(
                    "current_record", lambda: store.get(job.operator_id, job.job_id)
                )
            remaining = job.request.budget.timeout_seconds - (time.monotonic() - started)
            if remaining <= 0:
                error = "timeout"
                raise TimeoutError("snapshot preparation deadline exceeded")
            if contended and time.monotonic() - waiting_heartbeat >= HEARTBEAT_SECONDS:
                if stop_event is not None and stop_event.is_set():
                    return _observe_worker_call(
                        "current_record", lambda: store.get(job.operator_id, job.job_id)
                    )
                if not _observe_worker_call(
                    "heartbeat_before_start",
                    lambda: store.heartbeat(job.job_id, owner, job.attempt, datetime.now(UTC)),
                ):
                    return _observe_worker_call(
                        "current_record", lambda: store.get(job.operator_id, job.job_id)
                    )
                waiting_heartbeat = time.monotonic()
                # Recheck stop/deadline after an entered store operation completes.
                continue
            if _observe_worker_call(
                "snapshot_lock",
                lambda: _SNAPSHOT_LOCK.acquire(timeout=min(_POLL_SECONDS, remaining)),
            ):
                break
            contended = True
        try:
            if stop_event is not None and stop_event.is_set():
                return _observe_worker_call(
                    "current_record", lambda: store.get(job.operator_id, job.job_id)
                )
            if time.monotonic() - started >= job.request.budget.timeout_seconds:
                error = "timeout"
                raise TimeoutError("snapshot preparation deadline exceeded")
            _observe_worker_call("snapshot", lambda: _contained(Path(artifacts_root), attempt))
            _observe_worker_call("snapshot", lambda: attempt.mkdir(parents=True, exist_ok=False))
            if execution is not None and sys.platform != "linux":
                raise UnsupportedLimits("Linux execution requires Linux owner")
            if execution is not None:
                _observe_worker_call("snapshot", lambda: bundle.mkdir(mode=0o700))
            _observe_worker_call(
                "snapshot", lambda: _snapshot(job, Path(inputs_root).absolute(), bundle / "inputs")
            )
        finally:
            _SNAPSHOT_LOCK.release()
        if time.monotonic() - started >= job.request.budget.timeout_seconds:
            error = "timeout"
            raise TimeoutError("snapshot preparation deadline exceeded")
        runtime = _observe_worker_call(
            "attempt_runtime",
            lambda: (
                execution.runtime_fingerprint if execution is not None else runtime_fingerprint
            )(),
        )
        _observe_worker_call("deadline", lambda: _check_launch_deadline())
        _observe_worker_call(
            "bundle_write",
            lambda: (bundle / "job.json").write_text(job.model_dump_json(), encoding="utf-8"),
        )
        _observe_worker_call(
            "bundle_write", lambda: (bundle / "runtime.json").write_bytes(_canonical(runtime))
        )
        _observe_worker_call("deadline", lambda: _check_launch_deadline())
        if stop_event is not None and stop_event.is_set():
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        # This check is the cooperative-stop boundary for the following call:
        # an already-entered store operation may finish, but no later operation starts.
        if not _observe_worker_call(
            "heartbeat_before_start",
            lambda: store.heartbeat(job.job_id, owner, job.attempt, datetime.now(UTC)),
        ):
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        if stop_event is not None and stop_event.is_set():
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        _observe_worker_call("deadline", lambda: _check_launch_deadline())
        child = (
            _observe_worker_call(
                "constructor", lambda: execution.start(job, runtime, bundle, output)
            )
            if execution is not None
            else _observe_worker_call(
                "constructor",
                lambda: _OwnedChild(_child_command(attempt), job.request.budget, attempt),
            )
        )
        heartbeat = time.monotonic()
        last_pulse = heartbeat
        while True:
            if stop_event is not None and stop_event.is_set():
                return _observe_worker_call(
                    "current_record", lambda: store.get(job.operator_id, job.job_id)
                )
            code = _observe_worker_call("poll", lambda: child.poll())
            if code is not None and code != 0:
                attempt_failed = True
            if code is not None:
                break
            if stop_event is not None and stop_event.is_set():
                return _observe_worker_call(
                    "current_record", lambda: store.get(job.operator_id, job.job_id)
                )
            if time.monotonic() - started >= job.request.budget.timeout_seconds:
                error = "timeout"
                raise TimeoutError("owned worker deadline exceeded")
            current = _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
            if (
                current.state != "running"
                or current.cancel_requested
                or (
                    current.attempt != job.attempt
                    or current.lease_owner != owner
                    or current.lease_expires_at <= datetime.now(UTC)
                )
            ):
                return current
            if time.monotonic() - heartbeat >= HEARTBEAT_SECONDS:
                if stop_event is not None and stop_event.is_set():
                    return current
                if not _observe_worker_call(
                    "heartbeat_running",
                    lambda: store.heartbeat(job.job_id, owner, job.attempt, datetime.now(UTC)),
                ):
                    return _observe_worker_call(
                        "current_record", lambda: store.get(job.operator_id, job.job_id)
                    )
                heartbeat = time.monotonic()
            if time.monotonic() - last_pulse >= 1:
                if stop_event is not None and stop_event.is_set():
                    return current
                _observe_worker_call("pulse", lambda: child.pulse())
                last_pulse = time.monotonic()
            if stop_event is None:
                time.sleep(_POLL_SECONDS)
            else:
                stop_event.wait(_POLL_SECONDS)
        if stop_event is not None and stop_event.is_set():
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        if time.monotonic() - started >= job.request.budget.timeout_seconds:
            error = "timeout"
            raise TimeoutError("owned worker deadline exceeded")
        if code:
            failure = output / "error.json"
            if (
                failure.exists()
                and json.loads(_read_child_file(output, failure, _MAX_OUTPUT_BYTES)).get(
                    "error_code"
                )
                == "dataset_rejected"
            ):
                error = "dataset_rejected"
            raise ValueError("owned worker failed")
        # Parent validates the actual child receipt and numerical schema before publication.
        if execution is not None:
            _observe_worker_call(
                "validate_exit_first", lambda: execution.validate_exit(child, job, runtime)
            )
        if stop_event is not None and stop_event.is_set():
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        raw = _observe_worker_call(
            "receipt_validation", lambda: _validated_child_result(job, owner, runtime, output)
        )
        if stop_event is not None and stop_event.is_set():
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        if not _observe_worker_call(
            "heartbeat_before_publish",
            lambda: store.heartbeat(job.job_id, owner, job.attempt, datetime.now(UTC)),
        ):
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        if execution is not None:
            # Re-read the exact parent binding immediately before publication.
            _observe_worker_call(
                "validate_exit_second", lambda: execution.validate_exit(child, job, runtime)
            )
        if stop_event is not None and stop_event.is_set():
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        # Treat this check as the stop linearization point for publication.
        ref = _observe_worker_call(
            "publish", lambda: publish_result(job, raw, Path(artifacts_root))
        )
        if stop_event is not None and stop_event.is_set():
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        _observe_worker_call(
            "finish_succeeded",
            lambda: store.finish(job.job_id, owner, job.attempt, "succeeded", [ref], None),
        )
    except DatasetRejected:
        attempt_failed = True
        if stop_event is not None and stop_event.is_set():
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        _observe_worker_call(
            "finish_failed",
            lambda: store.finish(job.job_id, owner, job.attempt, "failed", [], "dataset_rejected"),
        )
    except (UnsupportedLimits, UnsupportedSnapshotProfile) as unsupported:
        attempt_failed = True
        if stop_event is not None and stop_event.is_set():
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        (attempt / "failure.json").write_bytes(
            _canonical(
                dict(
                    error_code="worker_failed",
                    limitation="fixture_snapshot_profile_unsupported"
                    if isinstance(unsupported, UnsupportedSnapshotProfile)
                    else "platform_or_cpu_quota_unsupported",
                    platform=sys.platform,
                    cpu_limit=job.request.budget.cpu_limit,
                )
            )
        )
        if stop_event is not None and stop_event.is_set():
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        _observe_worker_call(
            "finish_failed",
            lambda: store.finish(job.job_id, owner, job.attempt, "failed", [], "worker_failed"),
        )
    except LinuxContainmentError:
        attempt_failed = True
        if stop_event is not None and not stop_event.is_set():
            raise
        if stop_event is not None:
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        _observe_worker_call(
            "finish_failed",
            lambda: store.finish(job.job_id, owner, job.attempt, "failed", [], error),
        )
    except LaunchDeadlineExceeded as expired:
        attempt_failed = True
        if stop_event is not None and stop_event.is_set():
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        _observe_worker_call(
            "finish_failed",
            lambda: store.finish(job.job_id, owner, job.attempt, "failed", [], "timeout"),
        )
        if expired.__cause__ is not None:
            raise LinuxContainmentError("deadline_cleanup_unproven") from expired
    except (ValueError, OSError, subprocess.SubprocessError):
        attempt_failed = True
        if stop_event is not None and stop_event.is_set():
            return _observe_worker_call(
                "current_record", lambda: store.get(job.operator_id, job.job_id)
            )
        _observe_worker_call(
            "finish_failed",
            lambda: store.finish(job.job_id, owner, job.attempt, "failed", [], error),
        )
    finally:
        _worker_unwinding()
        try:
            if child is not None:
                _observe_worker_call("cleanup", lambda: child.close())
                # The sole post-stop write: no constructor/attempt/cleanup
                # uncertainty, no generic Event or failure-first upgrade.
                if (
                    type(stop_event) is _WorkerStop
                    and stop_event.controlled
                    and not attempt_failed
                    and sys.exc_info()[0] is None
                    and isinstance(child, LinuxOwnedProcess)
                    and child.closed
                    and isinstance(store, SQLiteJobStore)
                ):
                    _observe_worker_call(
                        "lease_handoff",
                        lambda: store._expire_owned_lease(
                            job.job_id, owner, job.attempt, datetime.now(UTC)
                        ),
                    )
        finally:
            _launch_deadline.reset(deadline_token)
    return _observe_worker_call("final_get", lambda: store.get(job.operator_id, job.job_id))
