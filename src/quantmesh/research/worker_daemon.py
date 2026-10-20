"""Persistent two-slot loop around the existing fenced WorkerRunner."""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path
from threading import Event, Lock, Thread
from typing import TYPE_CHECKING

from quantmesh.research.worker_execution import (
    LinuxWorkerExecution,
    WorkerRunner,
    _observe_worker_call,
    _worker_diagnostic_scope,
    _worker_stop_scope,
    _WorkerObservation,
    _WorkerSlotDiagnostics,
)
from quantmesh.research.worker_stop import _WorkerStop

if TYPE_CHECKING:
    from quantmesh.research.job_store import JobStore


class WorkerDaemonError(RuntimeError):
    """Sanitized daemon failure; internal paths and provider errors stay private."""

    def __init__(self, observation: _WorkerObservation | None = None) -> None:
        super().__init__("worker_daemon_failed")
        self.observation = observation


class WorkerDaemon:
    """Run exactly two claim loops; the JobStore enforces global capacity."""

    def __init__(
        self,
        *,
        runner: WorkerRunner,
        store: JobStore,
        inputs_root: Path,
        artifacts_root: Path,
    ) -> None:
        self.runner = runner
        self.store = store
        self.inputs_root = Path(inputs_root)
        self.artifacts_root = Path(artifacts_root)

    def run(self, stop_event: Event | _WorkerStop) -> None:
        if type(self.runner) is not WorkerRunner:
            raise WorkerDaemonError() from None
        execution = getattr(self.runner, "execution", None)
        if not isinstance(execution, LinuxWorkerExecution):
            raise WorkerDaemonError() from None
        if stop_event.is_set():
            return

        process_id = uuid.uuid4().hex
        failed = Event()
        capture_lock = None
        first_failure = None
        try:
            capture_lock = Lock()
            origin_ns = time.monotonic_ns()
            diagnostics = [_WorkerSlotDiagnostics(slot, origin_ns) for slot in range(2)]
        except BaseException:
            diagnostics = []

        def capture(slot: int) -> None:
            nonlocal first_failure
            try:
                with capture_lock:
                    if first_failure is None:
                        first_failure = diagnostics[slot].escaping()
            except BaseException:
                pass

        def observation() -> _WorkerObservation | None:
            try:
                if first_failure is not None:
                    secondary = []
                    for state in diagnostics:
                        cleanup = state.secondary_cleanup
                        if cleanup is None and state.last_failure is not None:
                            if state.last_failure.stage == "cleanup":
                                cleanup = state.last_failure
                        if cleanup is not None and cleanup != first_failure:
                            secondary.append(cleanup)
                    return _WorkerObservation(
                        first_failure,
                        tuple(secondary),
                        tuple(state.snapshot() for state in diagnostics),
                    )
            except BaseException:
                pass
            return None

        def run_slot(slot: int) -> None:
            owner = f"worker-{process_id}-slot-{slot}"
            try:
                with (
                    _worker_stop_scope(stop_event),
                    _worker_diagnostic_scope(diagnostics[slot] if diagnostics else None),
                ):
                    while not stop_event.is_set():
                        if diagnostics:
                            try:
                                diagnostics[slot].reset()
                            except BaseException:
                                pass
                        _observe_worker_call(
                            "slot_admission", lambda: execution.runtime_fingerprint()
                        )
                        if stop_event.is_set():
                            break
                        result = self.runner.run_next_job(
                            self.store, owner, self.inputs_root, self.artifacts_root
                        )
                        if result is None:
                            stop_event.wait(1.0)
            except BaseException:
                failed.set()
                stop_event.set()
                # Stop ordering stays authoritative; capture cannot delay it.
                capture(slot)

        slots = [
            Thread(target=run_slot, args=(index,), name=f"research-worker-{index}")
            for index in range(2)
        ]
        started: list[Thread] = []
        try:
            for slot, thread in enumerate(slots):
                thread.start()
                started.append(thread)
        except BaseException:
            stop_event.set()
            for thread in started:
                thread.join()
            if diagnostics:
                try:
                    diagnostics[slot].enter("thread_start")
                    diagnostics[slot].failure(sys.exc_info()[0] or RuntimeError)
                    capture(slot)
                except BaseException:
                    pass
            raise WorkerDaemonError(observation()) from None
        for thread in started:
            thread.join()
        if failed.is_set():
            raise WorkerDaemonError(observation()) from None
