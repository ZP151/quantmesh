"""Explicit, fail-closed bootstrap for the standalone research worker."""

from __future__ import annotations

import argparse
import json
import re
import signal
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from qm_research_agent import runtime as service_runtime
from qm_research_agent import store as service_store
from quantmesh.research.linux_owned import LinuxContainmentError, LinuxExecutionProfile
from quantmesh.research.worker_admission import WorkerAdmissionPins, WorkerImageAdmission
from quantmesh.research.worker_build import registered_fixture_profile
from quantmesh.research.worker_daemon import WorkerDaemon, WorkerDaemonError
from quantmesh.research.worker_execution import (
    _WORKER_CATEGORIES,
    _WORKER_STAGES,
    LinuxWorkerExecution,
    WorkerRunner,
    _WorkerFailure,
    _WorkerObservation,
    _WorkerSlotSnapshot,
    _WorkerStage,
)
from quantmesh.research.worker_stop import _WorkerStop

_MAX_CONFIG_BYTES = 64 * 1024
_PIN_FIELDS = frozenset(WorkerAdmissionPins.__dataclass_fields__)


class WorkerRuntimeRejected(ValueError):
    """A fixed worker-bootstrap refusal that never contains input values."""

    def __init__(self, category: str):
        if category not in {
            "configuration_invalid",
            "worker_configuration_invalid",
            "worker_admission_failed",
            "source_unqualified",
        }:
            category = "configuration_invalid"
        super().__init__(category)


class _StrictModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        strict=True,
        hide_input_in_errors=True,
    )


def _absolute_path(value: object) -> bool:
    return (
        type(value) is str
        and "\x00" not in value
        and "\n" not in value
        and "\r" not in value
        and Path(value).is_absolute()
        and ".." not in Path(value).parts
    )


class WorkerProfileConfig(_StrictModel):
    endpoint: str
    docker_cli: str
    image_id: str
    uid: int
    gid: int
    fixture_root: str
    apparmor_profile: str
    seccomp_path: str

    @model_validator(mode="before")
    @classmethod
    def exact_profile(cls, value):
        if type(value) is not dict or set(value) != {
            "endpoint",
            "docker_cli",
            "image_id",
            "uid",
            "gid",
            "fixture_root",
            "apparmor_profile",
            "seccomp_path",
        }:
            raise ValueError("worker profile fields rejected")
        if type(value.get("uid")) is not int or type(value.get("gid")) is not int:
            raise ValueError("worker profile identity rejected")
        return value

    @model_validator(mode="after")
    def valid_profile_paths(self):
        if not all(
            _absolute_path(getattr(self, name))
            for name in ("docker_cli", "fixture_root", "seccomp_path")
        ):
            raise ValueError("worker profile path rejected")
        if (
            self.endpoint
            not in {
                "unix:///var/run/docker.sock",
                "npipe:////./pipe/dockerDesktopLinuxEngine",
            }
            and re.fullmatch(r"unix:///run/user/[1-9][0-9]*/docker.sock", self.endpoint) is None
        ):
            raise ValueError("worker endpoint rejected")
        if (
            re.fullmatch(r"sha256:[0-9a-f]{64}", self.image_id) is None
            or re.fullmatch(
                r"qm-worker-(?:[a-z0-9]|[a-z0-9][a-z0-9-]{0,52}[a-z0-9])",
                self.apparmor_profile,
            )
            is None
            or self.uid != 10001
            or self.gid != 10001
        ):
            raise ValueError("worker profile policy rejected")
        return self


class WorkerPinsConfig(_StrictModel):
    engine_id: str
    image_id: str
    image_config_sha256: str
    oci_manifest_sha256: str
    oci_config_sha256: str
    source_commit: str
    manifest_sha256: str
    inventory_sha256: str
    runtime_metadata_sha256: str
    dependency_lock_sha256: str
    python_executable_sha256: str
    entry_sha256: str
    observer_sha256: str
    expected_prefix: str
    python_version: str
    apparmor_name: str
    apparmor_sha256: str
    seccomp_sha256: str
    compiled_policy_sha256: str
    docker_default_sha256: str
    elf_map_sha256: str
    kernel_profile_sha256: str

    @model_validator(mode="after")
    def valid_pins(self):
        try:
            if set(self.model_fields_set) != _PIN_FIELDS:
                raise ValueError
            WorkerAdmissionPins(**self.model_dump())
        except (LinuxContainmentError, TypeError, ValueError):
            raise ValueError("worker pins rejected") from None
        return self


class WorkerRuntimeConfig(_StrictModel):
    schema_version: Literal[1]
    service_config: str
    snapshot_root: str
    profile: WorkerProfileConfig
    pins: WorkerPinsConfig

    @model_validator(mode="before")
    @classmethod
    def exact_config(cls, value):
        if type(value) is not dict or set(value) != {
            "schema_version",
            "service_config",
            "snapshot_root",
            "profile",
            "pins",
        }:
            raise ValueError("worker configuration fields rejected")
        if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
            raise ValueError("worker schema rejected")
        return value

    @model_validator(mode="after")
    def valid_paths_and_identity(self):
        if not _absolute_path(self.service_config) or not _absolute_path(self.snapshot_root):
            raise ValueError("worker configuration path rejected")
        fixture = Path(self.profile.fixture_root)
        snapshot = Path(self.snapshot_root)
        if snapshot == fixture or not snapshot.is_relative_to(fixture):
            raise ValueError("worker snapshot boundary rejected")
        if (
            self.profile.image_id != self.pins.image_id
            or self.profile.apparmor_profile != self.pins.apparmor_name
            or self.profile.uid != 10001
            or self.profile.gid != 10001
        ):
            raise ValueError("worker profile identity rejected")
        return self


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise WorkerRuntimeRejected("configuration_invalid")


def _event() -> _WorkerStop:
    return _WorkerStop()


def load_worker_config(path: Path) -> WorkerRuntimeConfig:
    """Read only the explicit bounded private worker config; never search secrets."""
    try:
        raw = service_runtime._read_private(Path(path), _MAX_CONFIG_BYTES)
        values = json.loads(raw, object_pairs_hook=service_runtime._unique_object)
        return WorkerRuntimeConfig.model_validate(values)
    except WorkerRuntimeRejected:
        raise
    except service_runtime.RuntimeRejected:
        raise WorkerRuntimeRejected("configuration_invalid") from None
    except (OSError, TypeError, ValueError):
        raise WorkerRuntimeRejected("configuration_invalid") from None


def _roots_are_owned(config: WorkerRuntimeConfig, runtime) -> bool:
    try:
        fixture = Path(config.profile.fixture_root).resolve(strict=True)
        lake = runtime.config.lake_root.resolve(strict=True)
        artifacts = runtime.config.artifact_root.resolve(strict=True)
        snapshot = Path(config.snapshot_root).resolve(strict=True)
        return (
            lake != artifacts
            and lake.parent == fixture
            and artifacts.parent == fixture
            and snapshot != fixture
            and snapshot.is_relative_to(fixture)
            and not snapshot.is_relative_to(lake)
            and not snapshot.is_relative_to(artifacts)
            and not lake.is_relative_to(snapshot)
            and not artifacts.is_relative_to(snapshot)
        )
    except (OSError, RuntimeError, TypeError, ValueError):
        return False


def build_execution(config: WorkerRuntimeConfig, runtime) -> LinuxWorkerExecution:
    """Build the sole registered-profile provider after checking identity/root ties."""
    try:
        pins = WorkerAdmissionPins(**config.pins.model_dump())
        if (
            config.profile.image_id != pins.image_id
            or pins.source_commit != runtime.actual_build
            or not _roots_are_owned(config, runtime)
        ):
            raise WorkerRuntimeRejected("worker_configuration_invalid")
        profile = LinuxExecutionProfile(
            endpoint=config.profile.endpoint,
            docker_cli=Path(config.profile.docker_cli),
            image_id=config.profile.image_id,
            uid=config.profile.uid,
            gid=config.profile.gid,
            fixture_root=Path(config.profile.fixture_root),
            apparmor_profile=config.profile.apparmor_profile,
            seccomp_path=Path(config.profile.seccomp_path),
        )
        if (
            profile.apparmor_profile is None
            or profile.seccomp_path is None
            or profile.uid != 10001
            or profile.gid != 10001
            or profile.image_id != pins.image_id
            or profile.apparmor_profile != pins.apparmor_name
        ):
            raise WorkerRuntimeRejected("worker_configuration_invalid")
        admission = WorkerImageAdmission(
            pins=pins,
            snapshot_root=Path(config.snapshot_root),
            execution_profile=registered_fixture_profile(),
        )
        return LinuxWorkerExecution(profile=profile, admission=admission)
    except WorkerRuntimeRejected:
        raise
    except (LinuxContainmentError, TypeError, ValueError, OSError):
        raise WorkerRuntimeRejected("worker_admission_failed") from None


def _stopped(event: Event | _WorkerStop) -> bool:
    return event.is_set()


@contextmanager
def _signal_scope(event: Event | _WorkerStop) -> Iterator[None]:
    previous = {}

    def request_stop(signum, _frame):
        if type(event) is _WorkerStop:
            event.request_signal(signum)
        else:
            event.set()

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous[signum] = signal.signal(signum, request_stop)
        yield
    finally:
        for signum, handler in reversed(tuple(previous.items())):
            signal.signal(signum, handler)


def _preflight(runtime) -> dict:
    result = runtime.preflight()
    return {
        "schema_version": 1,
        "mode": "preflight",
        "actual_build": result["actual_build"],
        "paper": True,
        "live": False,
        "capabilities": {"worker": "activation_pending", "model": "unavailable"},
    }


def _run_worker(config: WorkerRuntimeConfig, runtime, stop_event: Event | _WorkerStop) -> int:
    if _stopped(stop_event):
        return 0
    execution = build_execution(config, runtime)
    if _stopped(stop_event):
        return 0
    fingerprint = execution.runtime_fingerprint()
    if _stopped(stop_event):
        return 0
    if (
        type(fingerprint) is not dict
        or fingerprint.get("git_commit") != runtime.actual_build
        or config.pins.source_commit != runtime.actual_build
    ):
        raise WorkerRuntimeRejected("source_unqualified")
    current = service_runtime._admit_runtime(runtime.config.expected_build)
    if _stopped(stop_event):
        return 0
    if current != (runtime.actual_build, runtime.lock_sha256):
        raise WorkerRuntimeRejected("source_unqualified")
    if _stopped(stop_event):
        return 0
    store = service_store.PostgresJobStore(
        runtime.postgres_dsn,
        lake_root=runtime.config.lake_root,
        artifact_root=runtime.config.artifact_root,
        schema="qm_research",
    )
    if _stopped(stop_event):
        return 0
    runner = WorkerRunner(execution=execution)
    if _stopped(stop_event):
        return 0
    daemon = WorkerDaemon(
        runner=runner,
        store=store,
        inputs_root=runtime.config.lake_root,
        artifacts_root=runtime.config.artifact_root,
    )
    if _stopped(stop_event):
        return 0
    daemon.run(stop_event)
    return 0


def _emit_worker_observation(observation: _WorkerObservation | None) -> None:
    """Rebuild a bounded allowlisted record; telemetry never changes exit status."""
    try:
        if type(observation) is not _WorkerObservation:
            return

        def integer(value, maximum=2**63):
            return type(value) is int and 0 <= value < maximum

        def identity(job_id, attempt):
            return (
                job_id is None or (type(job_id) is str and re.fullmatch(r"[0-9a-f]{32}", job_id))
            ) and (attempt is None or (integer(attempt, 2**31) and attempt > 0))

        def failure(value):
            if (
                type(value) is not _WorkerFailure
                or not integer(value.slot, 2)
                or type(value.stage) is not str
                or value.stage not in _WORKER_STAGES
                or type(value.category) is not str
                or value.category not in _WORKER_CATEGORIES
                or not integer(value.monotonic_ns)
                or not identity(value.job_id, value.attempt)
            ):
                raise ValueError
            return dict(
                slot=value.slot,
                stage=value.stage,
                category=value.category,
                monotonic_ns=value.monotonic_ns,
                job_id=value.job_id,
                attempt=value.attempt,
            )

        if (
            type(observation.secondary_cleanup) is not tuple
            or len(observation.secondary_cleanup) > 2
            or type(observation.slots) is not tuple
            or len(observation.slots) > 2
        ):
            return
        first = failure(observation.first_failure)
        secondary = [failure(value) for value in observation.secondary_cleanup]
        if any(value["stage"] != "cleanup" for value in secondary):
            return
        slots, seen_slots = [], set()
        for slot in observation.slots:
            if (
                type(slot) is not _WorkerSlotSnapshot
                or not integer(slot.slot, 2)
                or slot.slot in seen_slots
                or not identity(slot.job_id, slot.attempt)
                or type(slot.stages) is not tuple
                or len(slot.stages) > len(_WORKER_STAGES)
            ):
                return
            seen_slots.add(slot.slot)
            stages, seen_stages = [], set()
            for stage in slot.stages:
                if (
                    type(stage) is not _WorkerStage
                    or type(stage.stage) is not str
                    or stage.stage not in _WORKER_STAGES
                    or stage.stage in seen_stages
                    or not integer(stage.started_ns)
                    or (
                        stage.finished_ns is not None
                        and (not integer(stage.finished_ns) or stage.finished_ns < stage.started_ns)
                    )
                    or type(stage.outcome) is not str
                    or stage.outcome not in {"entered", "returned", "false", "failed"}
                ):
                    return
                seen_stages.add(stage.stage)
                stages.append(
                    dict(
                        stage=stage.stage,
                        started_ns=stage.started_ns,
                        finished_ns=stage.finished_ns,
                        outcome=stage.outcome,
                    )
                )
            slots.append(
                dict(slot=slot.slot, job_id=slot.job_id, attempt=slot.attempt, stages=stages)
            )
        raw = json.dumps(
            dict(
                schema_version=1,
                event="worker_failure_observation",
                first_failure=first,
                secondary_cleanup=secondary,
                slots=slots,
            ),
            separators=(",", ":"),
            sort_keys=True,
        )
        if len(raw.encode("utf-8")) <= 16 * 1024:
            print(raw, file=sys.stderr)
    except BaseException:
        pass


def main(argv=None) -> int:
    stop_event = _event()
    try:
        with _signal_scope(stop_event):
            try:
                parser = _Parser(description="Research worker bootstrap; preflight is the default.")
                parser.add_argument("--config", type=Path, required=True)
                parser.add_argument("--run", action="store_true")
                args = parser.parse_args(argv)
                if _stopped(stop_event):
                    return 0
                config = load_worker_config(args.config)
                if _stopped(stop_event):
                    return 0
                runtime = service_runtime.load_runtime(Path(config.service_config))
                if _stopped(stop_event):
                    return 0
                if not args.run:
                    print(json.dumps(_preflight(runtime), sort_keys=True))
                    return 0
                return _run_worker(config, runtime, stop_event)
            except WorkerRuntimeRejected as error:
                print(str(error), file=sys.stderr)
                return 2
            except service_runtime.RuntimeRejected as error:
                print(str(error), file=sys.stderr)
                return 2
            except WorkerDaemonError as error:
                print("worker_daemon_failed", file=sys.stderr)
                _emit_worker_observation(error.observation)
                return 3
            except LinuxContainmentError:
                print("worker_admission_failed", file=sys.stderr)
                return 3
            except service_store.StoreUnavailable:
                print("job_store_unavailable", file=sys.stderr)
                return 3
            except Exception:
                print("worker_runtime_unavailable", file=sys.stderr)
                return 3
    except Exception:
        print("worker_runtime_unavailable", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
