"""Construction-only execution binding; no image admission or default activation.

An independent image-admission provider must measure and verify the configured
image, source/runtime inventory and probe before returning its container tuple.
There is deliberately no saved-record/qualified-boolean provider here.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from quantmesh.research.jobs import JobRecord
from quantmesh.research.linux_bootstrap import verify_limits
from quantmesh.research.linux_owned import (
    LinuxContainmentError,
    LinuxExecutionProfile,
    LinuxOwnedProcess,
    bootstrap_digest,
)
from quantmesh.research.worker_bundle import handoff_worker_bundle

if TYPE_CHECKING:
    from quantmesh.research.job_store import JobStore

_execution: ContextVar[LinuxWorkerExecution | None] = ContextVar(
    "quantmesh_worker_execution", default=None
)
_COMMAND = (
    "/usr/local/bin/python3",
    "-B",
    "-I",
    "-S",
    "/opt/quantmesh/worker_entry.py",
    "--binding",
    "/inputs/parent-binding.json",
    "--manifest",
    "/opt/quantmesh/manifest.json",
    "--inventory",
    "/opt/quantmesh/inventory.json",
)


class WorkerImageAdmission(Protocol):
    """Trusted independent boundary, implemented by later image tooling.

    verify must rebind actual Engine/Image/config, manifest/inventory/source/lock,
    controller/entry/probe bytes to the profile. Metadata or a host runtime tuple
    alone is insufficient. This interface provides no qualification by itself.
    """

    def verify(self, profile: LinuxExecutionProfile) -> dict: ...

    def prepare_parent_binding(
        self, process: LinuxOwnedProcess, job: JobRecord, runtime: dict, ready: dict
    ) -> tuple[bytes, str]: ...


@dataclass(frozen=True)
class LinuxWorkerExecution:
    profile: LinuxExecutionProfile
    admission: WorkerImageAdmission

    def runtime_fingerprint(self) -> dict:
        runtime = self.admission.verify(self.profile)
        if not isinstance(runtime, dict) or set(runtime) != {
            "build_digest",
            "dependency_digest",
            "git_commit",
            "python_version",
            "python_executable_digest",
        }:
            raise LinuxContainmentError("worker_admission_failed")
        for name, length in (
            ("build_digest", 64),
            ("dependency_digest", 64),
            ("git_commit", 40),
            ("python_executable_digest", 64),
        ):
            if not isinstance(runtime[name], str) or not re.fullmatch(
                rf"[0-9a-f]{{{length}}}", runtime[name]
            ):
                raise LinuxContainmentError("worker_admission_failed")
        if not isinstance(runtime["python_version"], str) or not runtime["python_version"]:
            raise LinuxContainmentError("worker_admission_failed")
        return dict(runtime)

    def start(self, job: JobRecord, runtime: dict, bundle: Path, output: Path) -> LinuxOwnedProcess:
        if self.runtime_fingerprint() != runtime:
            raise LinuxContainmentError("worker_admission_changed")
        prepare = getattr(self.admission, "prepare_parent_binding", None)
        if not callable(prepare):
            raise LinuxContainmentError("parent_binding_required")
        handoff_worker_bundle(bundle, self.profile.uid, self.profile.gid)
        return LinuxOwnedProcess(
            self.profile,
            list(_COMMAND),
            job.request.budget,
            bundle,
            output,
            prepare_parent_binding=lambda process, ready: prepare(process, job, runtime, ready),
        )

    def validate_exit(self, child: LinuxOwnedProcess, job: JobRecord, runtime: dict) -> None:
        child._inspect()
        evidence = child.evidence
        if (
            self.runtime_fingerprint() != runtime
            or child.profile != self.profile
            or evidence.get("image_id") != self.profile.image_id
            or evidence.get("bootstrap_sha256") != bootstrap_digest()
            or evidence.get("running") is not False
            or evidence.get("oom_killed") is not False
            or evidence.get("exit_code") != 0
            or evidence.get("controller_failure")
        ):
            raise LinuxContainmentError("worker_exit_rejected")
        try:
            verify_limits(evidence["limits"], job.request.budget.memory_mib)
        except (KeyError, ValueError, TypeError):
            raise LinuxContainmentError("worker_exit_rejected") from None


@dataclass(frozen=True, kw_only=True)
class WorkerRunner:
    execution: LinuxWorkerExecution | None = None

    def run_next_job(
        self, store: JobStore, owner: str, inputs_root: Path, artifacts_root: Path
    ) -> JobRecord | None:
        from quantmesh.research.job_runner import run_next_job

        token = _execution.set(self.execution)
        try:
            return run_next_job(store, owner, inputs_root, artifacts_root)
        finally:
            _execution.reset(token)
