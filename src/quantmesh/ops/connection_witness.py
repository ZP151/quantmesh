"""Deadline-bounded, read-only workstation connection witness authority."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import socket
import sys
import time
import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.artifacts import canonical_json_bytes
from quantmesh.ops.immutable_runs import (
    DailyRunStatus,
    ImmutableRunConflictError,
    ImmutableRunStore,
    LeaseOwner,
    SlotLease,
    atomic_replace,
    operational_file_mutex,
    publish_create_once,
    read_safe_bytes,
    reject_reparse_chain,
)
from quantmesh.ops.processes import ProcessResult, run_process
from quantmesh.ops.trusted_data_soak import SoakStoreV2

_RUNNING = 0x00041301
_TERMINATED = 0x00041306
_SLOT_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$"
_COMPLETE_PROBE_NAMES = ("hyperliquid", "moomoo", "python", "scheduler", "tcp")


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    return value.astimezone(UTC)


def _now() -> datetime:
    return datetime.now(UTC)


class FormalTaskState(StrEnum):
    PASSED = "passed"
    IN_PROGRESS = "in-progress"
    FAILED = "failed"


class ConnectionWitnessStatus(StrEnum):
    PASSED = "passed"
    IN_PROGRESS = "in-progress"
    FAILED = "failed"
    TIMED_OUT = "timed-out"
    BLOCKED_USER_AUTH = "blocked-user-auth"
    INTERRUPTED = "interrupted"


class ConnectionProbeOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    TIMED_OUT = "timed-out"
    SKIPPED = "skipped"


class ExecutionKind(StrEnum):
    SCHEDULED = "scheduled"
    SUPPLEMENTAL = "supplemental"


class SlotAuthority(StrEnum):
    SCHEDULER = "scheduler"
    EXPLICIT_SUPPLEMENTAL = "explicit-supplemental"
    FALLBACK_FAILURE = "fallback-failure"


class FormalTaskSnapshot(_FrozenContract):
    task_name: str = Field(min_length=1)
    enabled: bool
    state: str = Field(min_length=1)
    last_task_result: int
    last_run_time: datetime | None

    @field_validator("task_name", "state")
    @classmethod
    def text_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("scheduler task text must not be blank")
        return value

    @field_validator("last_run_time")
    @classmethod
    def last_run_is_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value, "Scheduler LastRunTime")


class FormalTaskInterpretation(_FrozenContract):
    state: FormalTaskState
    code: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    daily_receipt_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    soak_report_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class ConnectionProbeResult(_FrozenContract):
    name: str = Field(min_length=1)
    outcome: ConnectionProbeOutcome
    code: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    elapsed_seconds: float = Field(ge=0)
    tree_terminated: bool

    @field_validator("elapsed_seconds")
    @classmethod
    def elapsed_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("probe elapsed time must be finite")
        return value


class ConnectionAttemptReservationV1(_FrozenContract):
    contract: str = Field(
        default="connection-attempt-reservation-v1",
        pattern=r"^connection-attempt-reservation-v1$",
    )
    slot: str = Field(pattern=_SLOT_PATTERN)
    attempt: int = Field(ge=1, le=2**63 - 1)
    execution_kind: ExecutionKind
    slot_authority: SlotAuthority
    slot_source_time: datetime | None = None
    started_at: datetime
    owner_token: str = Field(min_length=1)
    allocation_token: str = Field(min_length=1)
    reservation_id: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("slot_source_time", "started_at")
    @classmethod
    def reservation_times_are_utc(cls, value: datetime | None, info: Any) -> datetime | None:
        return None if value is None else _utc(value, info.field_name)

    @model_validator(mode="after")
    def identity_matches(self) -> Self:
        if self.execution_kind is ExecutionKind.SUPPLEMENTAL:
            if (
                self.slot_authority is not SlotAuthority.EXPLICIT_SUPPLEMENTAL
                or self.slot_source_time is not None
            ):
                raise ValueError("supplemental reservation requires explicit slot authority")
        elif self.slot_authority is SlotAuthority.EXPLICIT_SUPPLEMENTAL:
            raise ValueError("scheduled reservation cannot claim supplemental slot authority")
        if self.slot_authority is SlotAuthority.SCHEDULER and (
            self.slot_source_time is None
            or _scheduled_slot_at_or_before(self.slot_source_time) != self.slot
        ):
            raise ValueError("Scheduler slot authority requires its exact source time")
        if (
            self.slot_authority is SlotAuthority.FALLBACK_FAILURE
            and self.slot_source_time is not None
        ):
            raise ValueError("fallback slot authority cannot claim a source time")
        body = self.model_dump(mode="json", exclude={"reservation_id"})
        if self.reservation_id != _digest(body):
            raise ValueError("connection reservation ID disagrees with its body")
        return self

    @classmethod
    def build(cls, **values: Any) -> ConnectionAttemptReservationV1:
        probe = cls.model_construct(**values, reservation_id="0" * 64)
        return cls(
            **values,
            reservation_id=_digest(probe.model_dump(mode="json", exclude={"reservation_id"})),
        )

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class ConnectionWitnessReceiptV1(_FrozenContract):
    contract: str = Field(
        default="connection-witness-receipt-v1",
        pattern=r"^connection-witness-receipt-v1$",
    )
    run_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    slot: str = Field(pattern=_SLOT_PATTERN)
    attempt: int = Field(ge=1, le=2**63 - 1)
    execution_kind: ExecutionKind
    slot_authority: SlotAuthority
    slot_source_time: datetime | None = None
    reservation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    started_at: datetime
    finished_at: datetime
    status: ConnectionWitnessStatus
    expected_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    expected_source_contract_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    formal_state: FormalTaskState
    formal_code: str = Field(min_length=1)
    formal_last_run_time: datetime | None
    daily_receipt_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    soak_report_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    probes: tuple[ConnectionProbeResult, ...]
    failure_code: str | None = Field(default=None, min_length=1)
    detail: str | None = Field(default=None, min_length=1)
    receipt_id: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("slot_source_time", "started_at", "finished_at", "formal_last_run_time")
    @classmethod
    def times_are_utc(cls, value: datetime | None, info: Any) -> datetime | None:
        return None if value is None else _utc(value, info.field_name)

    @model_validator(mode="after")
    def terminal_is_consistent(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("connection witness cannot finish before it starts")
        names = tuple(item.name for item in self.probes)
        if names != tuple(sorted(set(names))):
            raise ValueError("connection probes must be sorted and unique")
        if self.execution_kind is ExecutionKind.SUPPLEMENTAL:
            if (
                self.slot_authority is not SlotAuthority.EXPLICIT_SUPPLEMENTAL
                or self.slot_source_time is not None
            ):
                raise ValueError("supplemental receipt requires explicit slot authority")
        elif self.slot_authority is SlotAuthority.EXPLICIT_SUPPLEMENTAL:
            raise ValueError("scheduled receipt cannot claim supplemental slot authority")
        if self.slot_authority is SlotAuthority.SCHEDULER and (
            self.slot_source_time is None
            or _scheduled_slot_at_or_before(self.slot_source_time) != self.slot
        ):
            raise ValueError("Scheduler receipt requires its exact slot source time")
        if (
            self.slot_authority is SlotAuthority.FALLBACK_FAILURE
            and self.slot_source_time is not None
        ):
            raise ValueError("fallback slot authority cannot claim a source time")
        if self.status in {
            ConnectionWitnessStatus.PASSED,
            ConnectionWitnessStatus.IN_PROGRESS,
        }:
            if self.failure_code is not None or self.detail is not None:
                raise ValueError("zero-outcome connection receipt cannot contain failure")
            if names != _COMPLETE_PROBE_NAMES:
                raise ValueError("zero-outcome connection receipt requires every named probe")
            if self.slot_authority is SlotAuthority.FALLBACK_FAILURE:
                raise ValueError("fallback slot authority can never produce a zero outcome")
        elif self.failure_code is None or self.detail is None:
            raise ValueError("nonzero connection receipt requires typed failure")
        if self.status is ConnectionWitnessStatus.PASSED and (
            self.formal_state is not FormalTaskState.PASSED
            or self.daily_receipt_id is None
            or self.soak_report_id is None
        ):
            raise ValueError("passed connection receipt requires exact daily proof")
        if self.status is ConnectionWitnessStatus.PASSED and any(
            item.outcome is not ConnectionProbeOutcome.PASSED for item in self.probes
        ):
            raise ValueError("passed connection receipt requires every probe to pass")
        if self.status is ConnectionWitnessStatus.IN_PROGRESS and (
            self.formal_state is not FormalTaskState.IN_PROGRESS
            or self.daily_receipt_id is not None
            or self.soak_report_id is not None
        ):
            raise ValueError("in-progress connection receipt cannot claim daily proof")
        if self.status is ConnectionWitnessStatus.IN_PROGRESS:
            outcomes = {item.name: item for item in self.probes}
            if any(
                outcomes[name].outcome is not ConnectionProbeOutcome.PASSED
                for name in ("hyperliquid", "python", "scheduler", "tcp")
            ) or (
                outcomes["moomoo"].outcome is not ConnectionProbeOutcome.SKIPPED
                or outcomes["moomoo"].code != "moomoo-suppressed-formal-in-progress"
            ):
                raise ValueError("in-progress connection receipt has invalid probe outcomes")
        body = self.model_dump(mode="json", exclude={"receipt_id"})
        if self.receipt_id != _digest(body):
            raise ValueError("connection receipt ID disagrees with its body")
        return self

    @classmethod
    def build(cls, **values: Any) -> ConnectionWitnessReceiptV1:
        values = {
            **values,
            "run_id": _digest(
                {
                    "contract": "connection-operational-run-v1",
                    "slot": values["slot"],
                    "attempt": values["attempt"],
                    "expected_commit": values["expected_commit"],
                }
            ),
        }
        probe = cls.model_construct(**values, receipt_id="0" * 64)
        return cls(
            **values,
            receipt_id=_digest(probe.model_dump(mode="json", exclude={"receipt_id"})),
        )

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class ConnectionLatestPointerV1(_FrozenContract):
    contract: str = Field(
        default="connection-latest-pointer-v1",
        pattern=r"^connection-latest-pointer-v1$",
    )
    slot: str = Field(pattern=_SLOT_PATTERN)
    attempt: int = Field(ge=1)
    receipt_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_pointer_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    pointer_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def identity_matches(self) -> Self:
        body = self.model_dump(mode="json", exclude={"pointer_digest"})
        if self.pointer_digest != _digest(body):
            raise ValueError("connection pointer ID disagrees with its body")
        return self

    @classmethod
    def build(cls, **values: Any) -> ConnectionLatestPointerV1:
        probe = cls.model_construct(**values, pointer_digest="0" * 64)
        return cls(
            **values,
            pointer_digest=_digest(probe.model_dump(mode="json", exclude={"pointer_digest"})),
        )

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


def _slot_token(slot: str) -> str:
    parsed = datetime.strptime(slot, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
    return parsed.strftime("%Y-%m-%dT%H%MZ")


class ConnectionWitnessStore:
    """Immutable reservations and terminals with one atomic latest pointer."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.reservation_dir = self.root / "reservations"
        self.receipt_dir = self.root / "receipts"
        self.terminal_dir = self.root / "terminals"
        self.latest_path = self.root / "latest.json"
        self.pointer_lock_path = self.root / ".latest.lock"

    def reservation_path(self, slot: str, attempt: int) -> Path:
        return self.reservation_dir / _slot_token(slot) / f"{attempt}.json"

    def receipt_path(self, receipt_id: str) -> Path:
        return self.receipt_dir / f"{receipt_id}.json"

    def terminal_path(self, slot: str, attempt: int) -> Path:
        return self.terminal_dir / _slot_token(slot) / f"{attempt}.json"

    def acquire_slot(
        self,
        slot: str,
        *,
        owner: LeaseOwner,
        now: datetime,
        stale_after: timedelta,
        owner_alive: Callable[[LeaseOwner], bool] | None = None,
    ) -> SlotLease:
        self._prepare()
        return SlotLease.acquire(
            self.root,
            slot,
            owner=owner,
            now=now,
            stale_after=stale_after,
            owner_alive=owner_alive,
        )

    def reserve_attempt(
        self,
        slot: str,
        *,
        lease: SlotLease,
        execution_kind: ExecutionKind,
        slot_authority: SlotAuthority,
        slot_source_time: datetime | None = None,
        started_at: datetime,
    ) -> ConnectionAttemptReservationV1:
        self._prepare()
        if (
            lease.record.slot != slot
            or lease.path.parent != self.root / "leases"
            or read_safe_bytes(lease.path) != lease.record.canonical_bytes()
        ):
            raise ValueError("connection attempt requires the active slot lease")
        for attempt in range(1, 2**31):
            reservation = ConnectionAttemptReservationV1.build(
                slot=slot,
                attempt=attempt,
                execution_kind=execution_kind,
                slot_authority=slot_authority,
                slot_source_time=slot_source_time,
                started_at=started_at,
                owner_token=lease.record.owner.token,
                allocation_token=uuid.uuid4().hex,
            )
            for transient_retry in range(101):
                try:
                    publish_create_once(
                        self.reservation_path(slot, attempt),
                        reservation.canonical_bytes(),
                        label="connection attempt reservation",
                    )
                except ImmutableRunConflictError:
                    break
                except ValueError as error:
                    if "hard link" not in str(error) or transient_retry == 100:
                        raise
                    time.sleep(0.001)
                    continue
                return reservation
            else:  # pragma: no cover - the loop returns or raises
                raise AssertionError("reservation retry loop did not terminate")
            continue
        raise RuntimeError("connection attempt space is exhausted")

    def load_reservation(self, slot: str, attempt: int) -> ConnectionAttemptReservationV1:
        reservation = self._read_model(
            self.reservation_path(slot, attempt), ConnectionAttemptReservationV1
        )
        if reservation.slot != slot or reservation.attempt != attempt:
            raise ValueError("connection reservation path disagrees with its body")
        return reservation

    def publish_terminal(self, receipt: ConnectionWitnessReceiptV1) -> None:
        self._prepare()
        reservation = self.load_reservation(receipt.slot, receipt.attempt)
        if (
            reservation.reservation_id != receipt.reservation_id
            or reservation.execution_kind is not receipt.execution_kind
            or reservation.slot_authority is not receipt.slot_authority
            or reservation.slot_source_time != receipt.slot_source_time
            or reservation.started_at != receipt.started_at
        ):
            raise ValueError("connection terminal disagrees with its reservation")
        publish_create_once(
            self.receipt_path(receipt.receipt_id),
            receipt.canonical_bytes(),
            label="connection receipt",
        )
        publish_create_once(
            self.terminal_path(receipt.slot, receipt.attempt),
            receipt.canonical_bytes(),
            label="connection terminal",
        )
        with operational_file_mutex(self.pointer_lock_path):
            current: ConnectionLatestPointerV1 | None = None
            if self.latest_path.exists():
                current = self._read_model(self.latest_path, ConnectionLatestPointerV1)
                current_receipt = self.load_terminal(current.slot, current.attempt)
                if current_receipt.receipt_id != current.receipt_id:
                    raise ValueError("connection latest pointer target is invalid")
                current_key = (current.slot, current.attempt)
                receipt_key = (receipt.slot, receipt.attempt)
                if receipt_key < current_key:
                    return
                if receipt_key == current_key:
                    if current.receipt_id != receipt.receipt_id:
                        raise ImmutableRunConflictError(
                            "connection latest pointer conflicts at the same attempt"
                        )
                    return
            pointer = ConnectionLatestPointerV1.build(
                slot=receipt.slot,
                attempt=receipt.attempt,
                receipt_id=receipt.receipt_id,
                prior_pointer_digest=(None if current is None else current.pointer_digest),
            )
            atomic_replace(self.latest_path, pointer.canonical_bytes())

    def load_terminal(self, slot: str, attempt: int) -> ConnectionWitnessReceiptV1:
        terminal = self._read_model(self.terminal_path(slot, attempt), ConnectionWitnessReceiptV1)
        receipt = self._read_model(
            self.receipt_path(terminal.receipt_id), ConnectionWitnessReceiptV1
        )
        if terminal != receipt or terminal.slot != slot or terminal.attempt != attempt:
            raise ValueError("connection terminal path disagrees with immutable receipt")
        return terminal

    def terminals(self, slot: str) -> tuple[ConnectionWitnessReceiptV1, ...]:
        directory = self.terminal_dir / _slot_token(slot)
        if not directory.exists():
            return ()
        reject_reparse_chain(directory)
        paths = tuple(directory.iterdir())
        if any(path.suffix != ".json" or not path.stem.isdigit() for path in paths):
            raise ValueError("connection terminal slot contains an unexpected entry")
        return tuple(
            self.load_terminal(slot, int(path.stem))
            for path in sorted(paths, key=lambda item: int(item.stem))
        )

    def latest(self) -> ConnectionWitnessReceiptV1:
        if not self.latest_path.exists():
            raise FileNotFoundError("no connection latest pointer exists")
        latest = self._read_model(self.latest_path, ConnectionLatestPointerV1)
        receipt = self.load_terminal(latest.slot, latest.attempt)
        if receipt.receipt_id != latest.receipt_id:
            raise ValueError("connection pointer target disagrees with its receipt")
        return receipt

    def _prepare(self) -> None:
        reject_reparse_chain(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        reject_reparse_chain(self.root)
        for directory in (
            self.reservation_dir,
            self.receipt_dir,
            self.terminal_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
            reject_reparse_chain(directory)

    @staticmethod
    def _read_model(path: Path, model: type[_FrozenContract]):
        payload = read_safe_bytes(path)
        evidence = model.model_validate_json(payload)
        if payload != canonical_json_bytes(evidence.model_dump(mode="json")):
            raise ValueError(f"connection evidence JSON is not canonical: {path}")
        return evidence


class ConnectionWitnessConfig(_FrozenContract):
    repo: Path
    report_root: Path
    daily_run_root: Path
    connection_run_root: Path
    outbox_root: Path
    formal_task_path: str = Field(min_length=1)
    formal_task_name: str = Field(min_length=1)
    connection_task_path: str = Field(min_length=1)
    connection_task_name: str = Field(min_length=1)
    expected_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    expected_source_contract_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_kind: ExecutionKind = ExecutionKind.SCHEDULED
    scheduled_slot: str | None = Field(default=None, pattern=_SLOT_PATTERN)
    formal_deadline_seconds: float = Field(default=3600, gt=0)
    stale_after_seconds: float = Field(default=93600, gt=0)
    match_early_seconds: float = Field(default=120, ge=0)
    match_late_seconds: float = Field(default=900, ge=0)
    python_timeout_seconds: float = Field(default=10, gt=0)
    tcp_timeout_seconds: float = Field(default=5, gt=0)
    scheduler_timeout_seconds: float = Field(default=15, gt=0)
    slot_identity_max_age_seconds: float = Field(default=900, gt=0)
    slot_lease_seconds: float = Field(default=900, gt=0)
    daily_receipt_timeout_seconds: float = Field(default=10, gt=0)
    moomoo_timeout_seconds: float = Field(default=30, gt=0)
    hyperliquid_timeout_seconds: float = Field(default=15, gt=0)

    @field_validator("repo", "report_root", "daily_run_root", "connection_run_root", "outbox_root")
    @classmethod
    def roots_are_absolute(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("connection witness roots must be absolute")
        return value

    @field_validator("formal_task_name", "connection_task_name")
    @classmethod
    def task_names_are_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Scheduler task names must not be blank")
        return value

    @field_validator("formal_task_path", "connection_task_path")
    @classmethod
    def task_paths_are_absolute_and_terminated(cls, value: str) -> str:
        if not value.startswith("\\") or not value.endswith("\\"):
            raise ValueError("Scheduler task paths must start and end with a backslash")
        return value

    @field_validator(
        "formal_deadline_seconds",
        "stale_after_seconds",
        "match_early_seconds",
        "match_late_seconds",
        "python_timeout_seconds",
        "tcp_timeout_seconds",
        "scheduler_timeout_seconds",
        "slot_identity_max_age_seconds",
        "slot_lease_seconds",
        "daily_receipt_timeout_seconds",
        "moomoo_timeout_seconds",
        "hyperliquid_timeout_seconds",
    )
    @classmethod
    def budgets_are_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("connection witness budgets must be finite")
        return value

    @model_validator(mode="after")
    def mode_has_exact_slot_contract(self) -> Self:
        if self.execution_kind is ExecutionKind.SCHEDULED and self.scheduled_slot is not None:
            raise ValueError("scheduled_slot is forbidden for scheduled execution")
        if self.execution_kind is ExecutionKind.SUPPLEMENTAL and self.scheduled_slot is None:
            raise ValueError("scheduled_slot is required for supplemental execution")
        if self.stale_after_seconds <= self.formal_deadline_seconds:
            raise ValueError("stale threshold must exceed the formal deadline")
        roots = tuple(
            path.resolve()
            for path in (
                self.report_root,
                self.daily_run_root,
                self.connection_run_root,
                self.outbox_root,
            )
        )
        if any(
            left == right or left.is_relative_to(right) or right.is_relative_to(left)
            for index, left in enumerate(roots)
            for right in roots[index + 1 :]
        ):
            raise ValueError("report, daily-run, connection-run and outbox roots must be disjoint")
        return self


def _failed(code: str, detail: str) -> FormalTaskInterpretation:
    return FormalTaskInterpretation(
        state=FormalTaskState.FAILED,
        code=code,
        detail=detail,
    )


def interpret_formal_task(
    snapshot: FormalTaskSnapshot | None,
    *,
    now: datetime,
    daily_store: ImmutableRunStore,
    report_root: Path,
    expected_commit: str,
    expected_source_contract_id: str,
    formal_deadline_seconds: float,
    stale_after_seconds: float,
    match_early_seconds: float,
    match_late_seconds: float,
) -> FormalTaskInterpretation:
    """Interpret Scheduler state only after exact immutable daily read-back."""
    instant = _utc(now, "formal task interpretation time")
    if snapshot is None:
        return _failed("formal-task-missing", "the formal Scheduler task is missing")
    if not snapshot.enabled or snapshot.state.casefold() == "disabled":
        return _failed("formal-task-disabled", "the formal Scheduler task is disabled")
    last_run = snapshot.last_run_time
    if last_run is None:
        return _failed("formal-task-never-ran", "the formal Scheduler task never ran")
    age = (instant - last_run).total_seconds()
    if age < 0:
        return _failed("formal-task-future-dated", "Scheduler LastRunTime is in the future")
    result = snapshot.last_task_result & 0xFFFFFFFF
    running_state = snapshot.state.casefold() == "running"
    if result == _TERMINATED:
        return _failed("formal-task-terminated", "Scheduler terminated the formal task")
    if running_state or result == _RUNNING:
        if not running_state or result != _RUNNING:
            return _failed(
                "formal-task-state-inconsistent",
                "Scheduler Running state and result code disagree",
            )
        if age <= formal_deadline_seconds:
            return FormalTaskInterpretation(
                state=FormalTaskState.IN_PROGRESS,
                code="formal-task-in-progress",
                detail="the formal daily task is within its bounded deadline",
            )
        return _failed("formal-task-overdue", "the formal daily task exceeded its deadline")
    if age > stale_after_seconds:
        return _failed("formal-task-stale", "the formal Scheduler evidence is stale")
    if result != 0:
        return _failed(
            "formal-task-nonzero",
            f"the formal Scheduler task returned 0x{result:08x}",
        )

    slot = last_run.date().isoformat()
    try:
        terminals = daily_store.terminals(slot)
    except (OSError, ValueError) as error:
        return _failed("daily-receipt-invalid", f"daily receipts are invalid: {error}")
    matching = tuple(
        item
        for item in terminals
        if -match_early_seconds
        <= (item.started_at - last_run).total_seconds()
        <= match_late_seconds
    )
    if not matching:
        return _failed("daily-receipt-missing", "no matching daily terminal exists")
    if len(matching) != 1:
        return _failed("daily-receipt-ambiguous", "multiple daily terminals match LastRunTime")
    receipt = matching[0]
    if receipt != terminals[-1]:
        return _failed("daily-receipt-not-latest", "a newer daily attempt exists")
    try:
        if daily_store.latest() != receipt:
            return _failed(
                "daily-receipt-not-latest",
                "daily latest pointer does not target the matching terminal",
            )
    except (OSError, ValueError) as error:
        return _failed("daily-receipt-invalid", f"daily latest pointer is invalid: {error}")
    if (
        receipt.code_commit != expected_commit
        or receipt.source_contract_id != expected_source_contract_id
    ):
        return _failed(
            "daily-source-mismatch",
            "daily terminal does not match the expected source contract",
        )
    if receipt.status is not DailyRunStatus.PASSED or receipt.soak_report_id is None:
        return _failed("daily-receipt-failed", "the latest matching daily terminal did not pass")
    try:
        report_store = SoakStoreV2(report_root)
        candidate = report_store.load_candidate()
        reports = report_store.reports()
        report_matches = tuple(item for item in reports if item.report_id == receipt.soak_report_id)
    except (OSError, ValueError) as error:
        return _failed("daily-report-invalid", f"daily report read-back failed: {error}")
    if len(report_matches) != 1:
        return _failed("daily-report-invalid", "the exact daily report is missing or ambiguous")
    report = report_matches[0]
    proof = receipt.verification
    if (
        proof is None
        or not proof.accepted
        or candidate.candidate_id != report.candidate_id
        or candidate.code_commit != expected_commit
        or candidate.source_contract_id != expected_source_contract_id
        or candidate.config_digest != report.config_digest
        or proof.candidate_id != report.candidate_id
        or report.code_commit != expected_commit
        or report.source_contract_id != expected_source_contract_id
    ):
        return _failed(
            "daily-report-mismatch",
            "daily report, terminal, source contract and verifier proof disagree",
        )
    return FormalTaskInterpretation(
        state=FormalTaskState.PASSED,
        code="formal-task-passed",
        detail="Scheduler zero is bound to the exact accepted daily report",
        daily_receipt_id=receipt.receipt_id,
        soak_report_id=report.report_id,
    )


def _formal_child_main(argv: Sequence[str] | None = None) -> int:
    """Read exact daily evidence in a child that the parent can tree-terminate."""
    parser = argparse.ArgumentParser(prog="quantmesh-formal-readback-child")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--now", required=True)
    parser.add_argument("--daily-run-root", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-source-contract-id", required=True)
    parser.add_argument("--formal-deadline-seconds", type=float, required=True)
    parser.add_argument("--stale-after-seconds", type=float, required=True)
    parser.add_argument("--match-early-seconds", type=float, required=True)
    parser.add_argument("--match-late-seconds", type=float, required=True)
    values = parser.parse_args(argv)
    snapshot_payload = base64.urlsafe_b64decode(values.snapshot.encode("ascii"))
    snapshot = FormalTaskSnapshot.model_validate_json(snapshot_payload)
    interpretation = interpret_formal_task(
        snapshot,
        now=datetime.fromisoformat(values.now.replace("Z", "+00:00")),
        daily_store=ImmutableRunStore(values.daily_run_root),
        report_root=values.report_root,
        expected_commit=values.expected_commit,
        expected_source_contract_id=values.expected_source_contract_id,
        formal_deadline_seconds=values.formal_deadline_seconds,
        stale_after_seconds=values.stale_after_seconds,
        match_early_seconds=values.match_early_seconds,
        match_late_seconds=values.match_late_seconds,
    )
    print(interpretation.canonical_bytes().decode("utf-8"))
    return 0


def _run_formal_interpretation(
    config: ConnectionWitnessConfig,
    snapshot: FormalTaskSnapshot,
    *,
    now: datetime,
    scheduler_elapsed_seconds: float,
) -> tuple[FormalTaskInterpretation, ConnectionProbeResult]:
    source_root = Path(__file__).resolve().parents[2]
    bootstrap = (
        "import sys;"
        f"sys.path.insert(0,{str(source_root)!r});"
        "from quantmesh.ops.connection_witness import _formal_child_main;"
        "raise SystemExit(_formal_child_main())"
    )
    snapshot_payload = base64.urlsafe_b64encode(
        canonical_json_bytes(snapshot.model_dump(mode="json"))
    ).decode("ascii")
    result = run_process(
        (
            sys.executable,
            "-c",
            bootstrap,
            "--snapshot",
            snapshot_payload,
            "--now",
            now.isoformat(),
            "--daily-run-root",
            str(config.daily_run_root),
            "--report-root",
            str(config.report_root),
            "--expected-commit",
            config.expected_commit,
            "--expected-source-contract-id",
            config.expected_source_contract_id,
            "--formal-deadline-seconds",
            str(config.formal_deadline_seconds),
            "--stale-after-seconds",
            str(config.stale_after_seconds),
            "--match-early-seconds",
            str(config.match_early_seconds),
            "--match-late-seconds",
            str(config.match_late_seconds),
        ),
        timeout_seconds=config.daily_receipt_timeout_seconds,
        cwd=config.repo,
    )
    elapsed = scheduler_elapsed_seconds + result.elapsed_seconds
    if result.timed_out:
        formal = _failed(
            "daily-receipt-deadline-exceeded",
            "exact daily receipt read-back exceeded its deadline",
        )
        return formal, ConnectionProbeResult(
            name="scheduler",
            outcome=ConnectionProbeOutcome.TIMED_OUT,
            code=formal.code,
            detail=formal.detail,
            elapsed_seconds=elapsed,
            tree_terminated=result.tree_terminated,
        )
    if result.returncode != 0:
        formal = _failed(
            "daily-receipt-child-failed",
            "exact daily receipt read-back child returned nonzero",
        )
        return formal, ConnectionProbeResult(
            name="scheduler",
            outcome=ConnectionProbeOutcome.FAILED,
            code=formal.code,
            detail=formal.detail,
            elapsed_seconds=elapsed,
            tree_terminated=result.tree_terminated,
        )
    try:
        formal = FormalTaskInterpretation.model_validate_json(result.stdout)
        if result.stdout.strip().encode("utf-8") != formal.canonical_bytes():
            raise ValueError("formal child output is not canonical")
    except (ValueError, json.JSONDecodeError):
        formal = _failed(
            "daily-receipt-child-invalid",
            "exact daily receipt read-back child returned invalid evidence",
        )
        return formal, ConnectionProbeResult(
            name="scheduler",
            outcome=ConnectionProbeOutcome.FAILED,
            code=formal.code,
            detail=formal.detail,
            elapsed_seconds=elapsed,
            tree_terminated=result.tree_terminated,
        )
    return formal, ConnectionProbeResult(
        name="scheduler",
        outcome=(
            ConnectionProbeOutcome.FAILED
            if formal.state is FormalTaskState.FAILED
            else ConnectionProbeOutcome.PASSED
        ),
        code=formal.code,
        detail=formal.detail,
        elapsed_seconds=elapsed,
        tree_terminated=result.tree_terminated,
    )


def _result_probe(name: str, result: ProcessResult) -> ConnectionProbeResult:
    if result.timed_out:
        return ConnectionProbeResult(
            name=name,
            outcome=ConnectionProbeOutcome.TIMED_OUT,
            code=f"{name}-deadline-exceeded",
            detail=f"{name} read-only probe exceeded its deadline",
            elapsed_seconds=result.elapsed_seconds,
            tree_terminated=result.tree_terminated,
        )
    if result.returncode != 0:
        return ConnectionProbeResult(
            name=name,
            outcome=ConnectionProbeOutcome.FAILED,
            code=f"{name}-failed",
            detail=f"{name} read-only probe returned nonzero",
            elapsed_seconds=result.elapsed_seconds,
            tree_terminated=result.tree_terminated,
        )
    return ConnectionProbeResult(
        name=name,
        outcome=ConnectionProbeOutcome.PASSED,
        code=f"{name}-passed",
        detail=f"{name} read-only probe passed",
        elapsed_seconds=result.elapsed_seconds,
        tree_terminated=result.tree_terminated,
    )


def _probe_python(config: ConnectionWitnessConfig) -> ConnectionProbeResult:
    result = run_process(
        (sys.executable, "-c", "import quantmesh; import pydantic"),
        timeout_seconds=config.python_timeout_seconds,
        cwd=config.repo,
    )
    return _result_probe("python", result)


def _probe_tcp(config: ConnectionWitnessConfig) -> ConnectionProbeResult:
    started = time.monotonic()
    try:
        with socket.create_connection(("127.0.0.1", 11111), config.tcp_timeout_seconds):
            pass
    except TimeoutError:
        return ConnectionProbeResult(
            name="tcp",
            outcome=ConnectionProbeOutcome.TIMED_OUT,
            code="tcp-deadline-exceeded",
            detail="loopback TCP 11111 probe timed out",
            elapsed_seconds=time.monotonic() - started,
            tree_terminated=False,
        )
    except OSError:
        return ConnectionProbeResult(
            name="tcp",
            outcome=ConnectionProbeOutcome.FAILED,
            code="blocked-user-auth",
            detail="loopback OpenD TCP 11111 is unavailable",
            elapsed_seconds=time.monotonic() - started,
            tree_terminated=False,
        )
    return ConnectionProbeResult(
        name="tcp",
        outcome=ConnectionProbeOutcome.PASSED,
        code="tcp-passed",
        detail="loopback TCP 11111 accepted a bounded connection",
        elapsed_seconds=time.monotonic() - started,
        tree_terminated=False,
    )


def _probe_moomoo(config: ConnectionWitnessConfig) -> ConnectionProbeResult:
    result = run_process(
        (sys.executable, "-m", "quantmesh.moomoo.cli", "probe"),
        timeout_seconds=config.moomoo_timeout_seconds,
        cwd=config.repo,
    )
    probe = _result_probe("moomoo", result)
    if not result.timed_out and result.returncode in {1, 2}:
        return probe.model_copy(
            update={
                "code": "blocked-user-auth",
                "detail": "OpenD is unavailable or requires interactive authentication",
            }
        )
    return probe


def _probe_hyperliquid(config: ConnectionWitnessConfig) -> ConnectionProbeResult:
    command = (
        "from quantmesh.hyperliquid.public_info import PublicInfoTransport; "
        f"PublicInfoTransport(request_timeout_s={config.hyperliquid_timeout_seconds!r})"
        ".l2_book('BTC')"
    )
    result = run_process(
        (sys.executable, "-c", command),
        timeout_seconds=config.hyperliquid_timeout_seconds,
        cwd=config.repo,
    )
    return _result_probe("hyperliquid", result)


def _read_scheduler_task(config: ConnectionWitnessConfig, task_name: str) -> FormalTaskSnapshot:
    if task_name == config.formal_task_name:
        task_path = config.formal_task_path
    elif task_name == config.connection_task_name:
        task_path = config.connection_task_path
    else:
        raise ValueError("Scheduler query requested an unconfigured task identity")
    escaped = task_name.replace("'", "''")
    escaped_path = task_path.replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop';"
        f"$task=Get-ScheduledTask -TaskPath '{escaped_path}' -TaskName '{escaped}';"
        f"$info=Get-ScheduledTaskInfo -TaskPath '{escaped_path}' -TaskName '{escaped}';"
        "$last=$null;"
        "if($info.LastRunTime -and $info.LastRunTime.Year -gt 1900){"
        "$last=$info.LastRunTime.ToUniversalTime().ToString('o')};"
        "[ordered]@{task_path=$task.TaskPath;task_name=$task.TaskName;"
        "enabled=($task.State -ne 'Disabled');"
        "state=[string]$task.State;last_task_result=[int64]$info.LastTaskResult;"
        "last_run_time=$last}|ConvertTo-Json -Compress"
    )
    result = run_process(
        ("powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script),
        timeout_seconds=config.scheduler_timeout_seconds,
        cwd=config.repo,
    )
    if result.timed_out:
        raise TimeoutError("Scheduler query exceeded its deadline")
    if result.returncode != 0:
        raise RuntimeError("Scheduler query returned nonzero")
    try:
        payload = json.loads(result.stdout)
        observed_path = payload.pop("task_path", None)
        if payload.get("last_run_time") is not None:
            payload["last_run_time"] = datetime.fromisoformat(
                payload["last_run_time"].replace("Z", "+00:00")
            )
        snapshot = FormalTaskSnapshot.model_validate(payload)
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError("Scheduler query returned invalid JSON") from error
    if observed_path != task_path:
        raise ValueError("Scheduler query returned a different task path")
    if snapshot.task_name != task_name:
        raise ValueError("Scheduler query returned a different task identity")
    return snapshot


def _safe_probe(
    name: str,
    operation: Callable[[ConnectionWitnessConfig], ConnectionProbeResult],
    config: ConnectionWitnessConfig,
) -> ConnectionProbeResult:
    started = time.monotonic()
    try:
        result = operation(config)
    except Exception as error:
        return ConnectionProbeResult(
            name=name,
            outcome=ConnectionProbeOutcome.FAILED,
            code=f"{name}-exception",
            detail=f"{name} read-only probe raised {type(error).__name__}",
            elapsed_seconds=time.monotonic() - started,
            tree_terminated=False,
        )
    if result.name != name:
        return ConnectionProbeResult(
            name=name,
            outcome=ConnectionProbeOutcome.FAILED,
            code=f"{name}-identity-mismatch",
            detail=f"{name} probe returned a mismatched identity",
            elapsed_seconds=time.monotonic() - started,
            tree_terminated=result.tree_terminated,
        )
    return result


def _scheduled_slot_at_or_before(value: datetime) -> str:
    instant = _utc(value, "connection scheduled slot source")
    boundary = instant.replace(minute=10, second=0, microsecond=0)
    if instant.minute < 10:
        boundary -= timedelta(hours=1)
    if boundary.hour % 2:
        boundary -= timedelta(hours=1)
    return boundary.strftime("%Y-%m-%dT%H:%MZ")


def _connection_self_probe(
    snapshot: FormalTaskSnapshot,
    *,
    now: datetime,
    maximum_age_seconds: float,
    elapsed_seconds: float,
) -> ConnectionProbeResult:
    last_run = snapshot.last_run_time
    result = snapshot.last_task_result & 0xFFFFFFFF
    age = None if last_run is None else (now - last_run).total_seconds()
    valid = (
        snapshot.enabled
        and snapshot.state.casefold() == "running"
        and result == _RUNNING
        and age is not None
        and 0 <= age <= maximum_age_seconds
    )
    return ConnectionProbeResult(
        name="scheduler-self",
        outcome=(ConnectionProbeOutcome.PASSED if valid else ConnectionProbeOutcome.FAILED),
        code="scheduler-self-passed" if valid else "scheduler-self-invalid",
        detail=(
            "connection Scheduler slot was normalized to UTC"
            if valid
            else "connection Scheduler state/result/time is invalid"
        ),
        elapsed_seconds=elapsed_seconds,
        tree_terminated=False,
    )


def _failure_from(
    formal: FormalTaskInterpretation,
    probes: tuple[ConnectionProbeResult, ...],
) -> tuple[ConnectionWitnessStatus, str | None, str | None]:
    timed_out = next(
        (item for item in probes if item.outcome is ConnectionProbeOutcome.TIMED_OUT),
        None,
    )
    if timed_out is not None:
        return ConnectionWitnessStatus.TIMED_OUT, timed_out.code, timed_out.detail
    blocked = next((item for item in probes if item.code == "blocked-user-auth"), None)
    if blocked is not None:
        return (
            ConnectionWitnessStatus.BLOCKED_USER_AUTH,
            blocked.code,
            blocked.detail,
        )
    failed = next(
        (item for item in probes if item.outcome is ConnectionProbeOutcome.FAILED),
        None,
    )
    if failed is not None:
        return ConnectionWitnessStatus.FAILED, failed.code, failed.detail
    if formal.state is FormalTaskState.FAILED:
        return ConnectionWitnessStatus.FAILED, formal.code, formal.detail
    if formal.state is FormalTaskState.IN_PROGRESS:
        return ConnectionWitnessStatus.IN_PROGRESS, None, None
    return ConnectionWitnessStatus.PASSED, None, None


def _ensure_connection_witness(
    config: ConnectionWitnessConfig, terminal: ConnectionWitnessReceiptV1
):
    from quantmesh.ops.witness_outbox import (
        IneligibleWitnessError,
        OutboxIntentError,
        WitnessKind,
        WitnessOutbox,
    )

    outbox = WitnessOutbox(config.outbox_root)
    try:
        if (
            terminal.expected_commit != config.expected_commit
            or terminal.expected_source_contract_id != config.expected_source_contract_id
        ):
            raise IneligibleWitnessError("connection terminal source identity is not expected")
        return outbox.ensure_connection_intent(terminal)
    except Exception as error:
        conflict = isinstance(error, ImmutableRunConflictError)
        outbox.record_reconciliation_failure(
            source_kind=WitnessKind.CONNECTION_STATE,
            terminal_receipt_id=terminal.receipt_id,
            error_code="intent-conflict" if conflict else "intent-error",
            detail=(
                "exact connection intent conflicts with durable outbox evidence"
                if conflict
                else f"connection intent enqueue raised {type(error).__name__}"
            ),
            observed_at=terminal.finished_at,
        )
        raise OutboxIntentError(
            "connection terminal is durable but its exact witness intent is missing"
        ) from error


def run_connection_witness(
    config: ConnectionWitnessConfig,
) -> ConnectionWitnessReceiptV1:
    """Run every read-only probe and publish one terminal from the final boundary."""
    started = _utc(_now(), "connection witness start")
    store = ConnectionWitnessStore(config.connection_run_root)
    slot = config.scheduled_slot or _scheduled_slot_at_or_before(started)
    slot_authority = (
        SlotAuthority.EXPLICIT_SUPPLEMENTAL
        if config.execution_kind is ExecutionKind.SUPPLEMENTAL
        else SlotAuthority.FALLBACK_FAILURE
    )
    slot_source_time: datetime | None = None
    self_probe: ConnectionProbeResult
    self_snapshot: FormalTaskSnapshot | None = None
    interrupted: BaseException | None = None
    if config.execution_kind is ExecutionKind.SCHEDULED:
        before = time.monotonic()
        try:
            self_snapshot = _read_scheduler_task(config, config.connection_task_name)
            self_probe = _connection_self_probe(
                self_snapshot,
                now=started,
                maximum_age_seconds=config.slot_identity_max_age_seconds,
                elapsed_seconds=time.monotonic() - before,
            )
            if (
                self_probe.outcome is ConnectionProbeOutcome.PASSED
                and self_snapshot.last_run_time is not None
            ):
                slot = _scheduled_slot_at_or_before(self_snapshot.last_run_time)
                slot_authority = SlotAuthority.SCHEDULER
                slot_source_time = self_snapshot.last_run_time
        except BaseException as error:
            if not isinstance(error, Exception):
                interrupted = error
            timed_out = isinstance(error, TimeoutError)
            self_probe = ConnectionProbeResult(
                name="scheduler-self",
                outcome=(
                    ConnectionProbeOutcome.TIMED_OUT if timed_out else ConnectionProbeOutcome.FAILED
                ),
                code=(
                    "scheduler-self-deadline-exceeded" if timed_out else "scheduler-self-exception"
                ),
                detail=f"connection Scheduler query raised {type(error).__name__}",
                elapsed_seconds=time.monotonic() - before,
                tree_terminated=timed_out,
            )
    else:
        self_probe = ConnectionProbeResult(
            name="scheduler-self",
            outcome=ConnectionProbeOutcome.SKIPPED,
            code="scheduler-self-supplemental",
            detail="supplemental execution uses its explicit scheduled slot",
            elapsed_seconds=0,
            tree_terminated=False,
        )
    owner = LeaseOwner.current(token=uuid.uuid4().hex)
    lease = store.acquire_slot(
        slot,
        owner=owner,
        now=started,
        stale_after=timedelta(seconds=config.slot_lease_seconds),
    )
    try:
        reservation = store.reserve_attempt(
            slot,
            lease=lease,
            execution_kind=config.execution_kind,
            slot_authority=slot_authority,
            slot_source_time=slot_source_time,
            started_at=started,
        )
    except BaseException:
        lease.release()
        raise
    probes: list[ConnectionProbeResult] = []
    formal = _failed("scheduler-exception", "formal Scheduler query did not complete")
    formal_snapshot: FormalTaskSnapshot | None = None
    receipt: ConnectionWitnessReceiptV1 | None = None
    try:
        if interrupted is None and self_probe.outcome not in {
            ConnectionProbeOutcome.FAILED,
            ConnectionProbeOutcome.TIMED_OUT,
        }:
            probes.append(_safe_probe("python", _probe_python, config))
            tcp_probe = _safe_probe("tcp", _probe_tcp, config)
            probes.append(tcp_probe)
            scheduler_started = time.monotonic()
            try:
                formal_snapshot = _read_scheduler_task(config, config.formal_task_name)
                formal, formal_probe = _run_formal_interpretation(
                    config,
                    formal_snapshot,
                    now=started,
                    scheduler_elapsed_seconds=time.monotonic() - scheduler_started,
                )
            except Exception as error:
                timed_out = isinstance(error, TimeoutError)
                formal = _failed(
                    "scheduler-deadline-exceeded" if timed_out else "scheduler-exception",
                    f"formal Scheduler query raised {type(error).__name__}",
                )
                formal_probe = ConnectionProbeResult(
                    name="scheduler",
                    outcome=(
                        ConnectionProbeOutcome.TIMED_OUT
                        if timed_out
                        else ConnectionProbeOutcome.FAILED
                    ),
                    code=formal.code,
                    detail=formal.detail,
                    elapsed_seconds=time.monotonic() - scheduler_started,
                    tree_terminated=timed_out,
                )
            probes.append(formal_probe)
            if formal.state is FormalTaskState.IN_PROGRESS:
                probes.append(
                    ConnectionProbeResult(
                        name="moomoo",
                        outcome=ConnectionProbeOutcome.SKIPPED,
                        code="moomoo-suppressed-formal-in-progress",
                        detail="Moomoo probe suppressed to avoid competing with the formal task",
                        elapsed_seconds=0,
                        tree_terminated=False,
                    )
                )
            elif tcp_probe.code == "blocked-user-auth":
                probes.append(
                    ConnectionProbeResult(
                        name="moomoo",
                        outcome=ConnectionProbeOutcome.SKIPPED,
                        code="moomoo-suppressed-opend-unavailable",
                        detail="Moomoo probe suppressed because OpenD TCP is unavailable",
                        elapsed_seconds=0,
                        tree_terminated=False,
                    )
                )
            else:
                probes.append(_safe_probe("moomoo", _probe_moomoo, config))
            probes.append(_safe_probe("hyperliquid", _probe_hyperliquid, config))
        else:
            formal = _failed(self_probe.code, self_probe.detail)
            probes.append(self_probe.model_copy(update={"name": "scheduler"}))
    except BaseException as error:
        interrupted = error
    finally:
        try:
            ordered = tuple(sorted(probes, key=lambda item: item.name))
            if interrupted is not None:
                status = ConnectionWitnessStatus.INTERRUPTED
                failure_code = "connection-witness-interrupted"
                detail = f"connection witness interrupted by {type(interrupted).__name__}"
            else:
                status, failure_code, detail = _failure_from(formal, ordered)
            receipt = ConnectionWitnessReceiptV1.build(
                slot=slot,
                attempt=reservation.attempt,
                execution_kind=config.execution_kind,
                slot_authority=slot_authority,
                slot_source_time=slot_source_time,
                reservation_id=reservation.reservation_id,
                started_at=started,
                finished_at=_utc(_now(), "connection witness finish"),
                status=status,
                expected_commit=config.expected_commit,
                expected_source_contract_id=config.expected_source_contract_id,
                formal_state=formal.state,
                formal_code=formal.code,
                formal_last_run_time=(
                    None if formal_snapshot is None else formal_snapshot.last_run_time
                ),
                daily_receipt_id=formal.daily_receipt_id,
                soak_report_id=formal.soak_report_id,
                probes=ordered,
                failure_code=failure_code,
                detail=detail,
            )
            store.publish_terminal(receipt)
        finally:
            lease.release()
    assert receipt is not None
    outbox_error: Exception | None = None
    try:
        _ensure_connection_witness(config, receipt)
    except Exception as error:
        outbox_error = error
    if interrupted is not None:
        raise interrupted from outbox_error
    if outbox_error is not None:
        raise outbox_error
    return receipt


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantmesh-connection-witness")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--report-root", type=Path, required=True)
    parser.add_argument("--daily-run-root", type=Path, required=True)
    parser.add_argument("--connection-run-root", type=Path, required=True)
    parser.add_argument("--outbox-root", type=Path, required=True)
    parser.add_argument("--formal-task-path", required=True)
    parser.add_argument("--formal-task-name", required=True)
    parser.add_argument("--connection-task-path", required=True)
    parser.add_argument("--connection-task-name", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-source-contract-id", required=True)
    parser.add_argument(
        "--execution-kind",
        choices=tuple(item.value for item in ExecutionKind),
        default=ExecutionKind.SCHEDULED.value,
    )
    parser.add_argument("--scheduled-slot")
    parser.add_argument("--formal-deadline-seconds", type=float, default=3600)
    parser.add_argument("--stale-after-seconds", type=float, default=93600)
    parser.add_argument("--match-early-seconds", type=float, default=120)
    parser.add_argument("--match-late-seconds", type=float, default=900)
    parser.add_argument("--python-timeout-seconds", type=float, default=10)
    parser.add_argument("--tcp-timeout-seconds", type=float, default=5)
    parser.add_argument("--scheduler-timeout-seconds", type=float, default=15)
    parser.add_argument("--slot-identity-max-age-seconds", type=float, default=900)
    parser.add_argument("--slot-lease-seconds", type=float, default=900)
    parser.add_argument("--daily-receipt-timeout-seconds", type=float, default=10)
    parser.add_argument("--moomoo-timeout-seconds", type=float, default=30)
    parser.add_argument("--hyperliquid-timeout-seconds", type=float, default=15)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    values = vars(_parser().parse_args(argv))
    values["execution_kind"] = ExecutionKind(values["execution_kind"])
    try:
        receipt = run_connection_witness(ConnectionWitnessConfig(**values))
    except Exception as error:
        print(f"FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        return 1
    print(receipt.canonical_bytes().decode("utf-8"))
    return (
        0
        if receipt.status in {ConnectionWitnessStatus.PASSED, ConnectionWitnessStatus.IN_PROGRESS}
        else 1
    )
