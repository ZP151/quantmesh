"""Recoverable registered fixture baselines in an owned bounded process tree.

Windows uses an OS Job Object (tree lifetime, memory and CPU affinity).
Linux requires a future crash-safe containment adapter; fractional CPU quotas
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
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from quantmesh.data.layout import shards_in
from quantmesh.research.baselines import run_baseline_report
from quantmesh.research.job_artifacts import (
    _canonical,
    _contained,
    canonical_result,
    publish_result,
)
from quantmesh.research.job_store import JobStore
from quantmesh.research.jobs import (
    HEARTBEAT_SECONDS,
    DatasetRejected,
    JobRecord,
    RunBudget,
    canonical_request_digest,
)
from quantmesh.research.reports import ReportRegistry, StrategyReport
from quantmesh.research.strategy_registry import get_strategy, pin_fixture_dataset, validate_dataset

_POLL_SECONDS = 0.1
_MAX_OUTPUT_BYTES = 16 * 1024 * 1024
_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_REPO = _SOURCE_ROOT.parent


def runtime_fingerprint() -> dict:
    """Bind source bytes and installed dependency metadata, independently of engine SHA.

    RECORD pins the complete installed distribution inventory. This fingerprint
    identifies the environment; it is not an attestation of every installed byte.
    """
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


def _verify(job: JobRecord, inputs_root: Path) -> None:
    if canonical_request_digest(job.request) != job.request_digest:
        raise ValueError("request digest mismatch")
    spec = get_strategy(job.request.strategy_id, job.request.strategy_version)
    if spec.implementation_digest != job.implementation_digest:
        raise ValueError("queued engine changed")
    validate_dataset(job.request, inputs_root, datetime.now(UTC))


def _snapshot(job: JobRecord, source: Path, destination: Path) -> None:
    """Copy exactly the manifest-covered shards, then re-pin the private snapshot."""
    _verify(job, source)
    name = job.request.dataset.dataset_id
    dataset = source / name
    manifest = dataset / "manifest.json"
    _contained(source, manifest)
    raw = manifest.read_bytes()
    declared = json.loads(raw)
    relative_paths = {Path("manifest.json")}
    for coverage in declared["coverage"]:
        partition = dataset / coverage["interval"] / coverage["venue"] / coverage["symbol"]
        _contained(source, partition)
        relative_paths.update(p.relative_to(dataset) for p in shards_in(partition))
    total = 0
    for relative in sorted(relative_paths):
        original = dataset / relative
        _contained(source, original)
        data = raw if relative == Path("manifest.json") else original.read_bytes()
        total += len(data)
        if total > 256 * 1024 * 1024:
            raise DatasetRejected("fixture_snapshot_too_large")
        target = destination / name / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if pin_fixture_dataset(source, name) != job.request.dataset:
        raise DatasetRejected("pin_changed_during_snapshot")
    _verify(job, destination)


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
    return [sys.executable, "-c", boot, str(attempt)]


def _child_main(directory: str) -> None:
    path = Path(directory)
    try:
        job = JobRecord.model_validate_json((path / "job.json").read_bytes())
        _verify(job, path / "inputs")
        runtime = runtime_fingerprint()
        if runtime != json.loads((path / "runtime.json").read_bytes()):
            raise ValueError("runtime changed before execution")
        r = job.request
        registry = ReportRegistry(path / "registry", lake_root=path / "inputs")
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
        _verify(job, path / "inputs")
        (path / "receipt.json").write_bytes(
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
                        else "process_address_space",
                        tree_owned=True,
                    ),
                )
            )
        )
        (path / "result.json").write_bytes(canonical_result(report))
    except DatasetRejected:
        (path / "error.json").write_text('{"error_code":"dataset_rejected"}')
        raise SystemExit(2) from None
    except Exception:
        (path / "error.json").write_text('{"error_code":"worker_failed"}')
        raise SystemExit(2) from None


def run_next_job(
    store: JobStore, owner: str, inputs_root: Path, artifacts_root: Path
) -> JobRecord | None:
    """Claim one job; execute a private snapshot; fence immutable report publication."""
    job = store.claim(owner, datetime.now(UTC))
    if job is None:
        return None
    attempt = (
        Path(artifacts_root).absolute()
        / job.job_id
        / "receipts"
        / (f"attempt-{job.attempt}-{uuid.uuid4().hex}")
    )
    child = None
    started = time.monotonic()
    error = "worker_failed"
    try:
        _contained(Path(artifacts_root), attempt)
        attempt.mkdir(parents=True, exist_ok=False)
        _snapshot(job, Path(inputs_root).absolute(), attempt / "inputs")
        runtime = runtime_fingerprint()
        (attempt / "job.json").write_text(job.model_dump_json(), encoding="utf-8")
        (attempt / "runtime.json").write_bytes(_canonical(runtime))
        if not store.heartbeat(job.job_id, owner, job.attempt, datetime.now(UTC)):
            return store.get(job.operator_id, job.job_id)
        child = _OwnedChild(_child_command(attempt), job.request.budget, attempt)
        heartbeat = time.monotonic()
        while child.process.poll() is None:
            if time.monotonic() - started >= job.request.budget.timeout_seconds:
                error = "timeout"
                raise TimeoutError("owned worker deadline exceeded")
            current = store.get(job.operator_id, job.job_id)
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
                if not store.heartbeat(job.job_id, owner, job.attempt, datetime.now(UTC)):
                    return store.get(job.operator_id, job.job_id)
                heartbeat = time.monotonic()
            time.sleep(_POLL_SECONDS)
        if time.monotonic() - started >= job.request.budget.timeout_seconds:
            error = "timeout"
            raise TimeoutError("owned worker deadline exceeded")
        if child.process.returncode:
            failure = attempt / "error.json"
            if (
                failure.exists()
                and json.loads(failure.read_bytes()).get("error_code") == "dataset_rejected"
            ):
                error = "dataset_rejected"
            raise ValueError("owned worker failed")
        result_path = attempt / "result.json"
        if result_path.stat().st_size > _MAX_OUTPUT_BYTES:
            raise ValueError("report too large")
        raw = result_path.read_bytes()
        # Parent validates the actual child receipt and numerical schema before publication.
        receipt = json.loads((attempt / "receipt.json").read_bytes())
        if receipt["runtime"] != runtime or receipt["attempt"] != job.attempt:
            raise ValueError("worker receipt mismatch")
        if canonical_result(StrategyReport.model_validate(receipt["report"])) != raw:
            raise ValueError("worker result mismatch")
        if not store.heartbeat(job.job_id, owner, job.attempt, datetime.now(UTC)):
            return store.get(job.operator_id, job.job_id)
        ref = publish_result(job, raw, Path(artifacts_root))
        store.finish(job.job_id, owner, job.attempt, "succeeded", [ref], None)
    except DatasetRejected:
        store.finish(job.job_id, owner, job.attempt, "failed", [], "dataset_rejected")
    except UnsupportedLimits:
        (attempt / "failure.json").write_bytes(
            _canonical(
                dict(
                    error_code="worker_failed",
                    limitation="platform_or_cpu_quota_unsupported",
                    platform=sys.platform,
                    cpu_limit=job.request.budget.cpu_limit,
                )
            )
        )
        store.finish(job.job_id, owner, job.attempt, "failed", [], "worker_failed")
    except (ValueError, OSError, subprocess.SubprocessError):
        store.finish(job.job_id, owner, job.attempt, "failed", [], error)
    finally:
        if child is not None:
            child.close()
    return store.get(job.operator_id, job.job_id)
