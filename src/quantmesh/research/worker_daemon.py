"""Persistent two-slot loop around the existing fenced WorkerRunner."""

from __future__ import annotations

import uuid
from pathlib import Path
from threading import Event, Thread
from typing import TYPE_CHECKING

from quantmesh.research.worker_execution import (
    LinuxWorkerExecution,
    WorkerRunner,
    _worker_stop_scope,
)
from quantmesh.research.worker_stop import _WorkerStop

if TYPE_CHECKING:
    from quantmesh.research.job_store import JobStore


class WorkerDaemonError(RuntimeError):
    """Sanitized daemon failure; internal paths and provider errors stay private."""

    def __init__(self) -> None:
        super().__init__("worker_daemon_failed")


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

        def run_slot(slot: int) -> None:
            owner = f"worker-{process_id}-slot-{slot}"
            try:
                with _worker_stop_scope(stop_event):
                    while not stop_event.is_set():
                        execution.runtime_fingerprint()
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

        slots = [
            Thread(target=run_slot, args=(index,), name=f"research-worker-{index}")
            for index in range(2)
        ]
        started: list[Thread] = []
        try:
            for thread in slots:
                thread.start()
                started.append(thread)
        except BaseException:
            stop_event.set()
            for thread in started:
                thread.join()
            raise WorkerDaemonError() from None
        for thread in started:
            thread.join()
        if failed.is_set():
            raise WorkerDaemonError() from None
