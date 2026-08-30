"""Crash-safe immutable receipts and owner-proven operational slot leases."""

from __future__ import annotations

import errno
import hashlib
import os
import stat
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.artifacts import canonical_json_bytes
from quantmesh.data.objects import is_reparse_point


class ImmutableRunConflictError(RuntimeError):
    """Create-once operational evidence conflicts with durable bytes."""


class LeaseHeldError(RuntimeError):
    """Another live owner holds the requested operational slot."""


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    return value.astimezone(UTC)


class DailyRunStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    TIMED_OUT = "timed-out"
    BLOCKED_USER_AUTH = "blocked-user-auth"
    INTERRUPTED = "interrupted"


class StageOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    TIMED_OUT = "timed-out"
    SKIPPED = "skipped"


class DailyStageReceiptV1(_FrozenContract):
    contract: str = Field(
        default="operational-stage-receipt-v1",
        pattern=r"^operational-stage-receipt-v1$",
    )
    run_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    slot: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    stage: str = Field(min_length=1)
    command_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    started_at: datetime
    finished_at: datetime
    outcome: StageOutcome
    exit_code: int | None = None
    stdout_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    stderr_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    output_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    receipt_id: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("started_at", "finished_at")
    @classmethod
    def times_are_utc(cls, value: datetime, info: Any) -> datetime:
        return _utc(value, info.field_name)

    @model_validator(mode="after")
    def identity_matches(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("stage cannot finish before it starts")
        body = self.model_dump(mode="json", exclude={"receipt_id"})
        if self.receipt_id != _digest(body):
            raise ValueError("stage receipt ID disagrees with its body")
        return self

    @classmethod
    def build(cls, **values: Any) -> DailyStageReceiptV1:
        probe = cls.model_construct(**values, receipt_id="0" * 64)
        identity = _digest(probe.model_dump(mode="json", exclude={"receipt_id"}))
        return cls(**values, receipt_id=identity)

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class SoakVerificationProof(_FrozenContract):
    accepted: bool
    reasons: tuple[str, ...]
    candidate_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    report_count: int = Field(ge=0)
    observed_hours: float = Field(ge=0)
    xnys_session_count: int = Field(ge=0)

    @field_validator("reasons")
    @classmethod
    def reasons_are_canonical(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))) or any(not value.strip() for value in values):
            raise ValueError("verification reasons must be sorted, unique and nonblank")
        return values


class DailyRunReceiptV1(_FrozenContract):
    """One content-derived terminal result for one UTC slot and attempt."""

    contract: str = Field(default="daily-run-receipt-v1", pattern=r"^daily-run-receipt-v1$")
    run_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    slot: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    attempt: int = Field(ge=1, le=2**63 - 1)
    started_at: datetime
    finished_at: datetime
    status: DailyRunStatus
    code_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    source_contract_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    stage_receipt_ids: tuple[str, ...] = ()
    hyperliquid_receipt_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    moomoo_receipt_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    soak_report_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    verification: SoakVerificationProof | None = None
    failure_stage: str | None = Field(default=None, min_length=1)
    failure_code: str | None = Field(default=None, min_length=1)
    detail: str | None = Field(default=None, min_length=1)
    recovery_of_run_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    receipt_id: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("started_at", "finished_at")
    @classmethod
    def times_are_utc(cls, value: datetime, info: Any) -> datetime:
        return _utc(value, info.field_name)

    @field_validator("failure_stage", "failure_code", "detail")
    @classmethod
    def optional_text_is_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("optional terminal text must not be blank")
        return value

    @model_validator(mode="after")
    def terminal_contract_is_consistent(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("daily run cannot finish before it starts")
        proof_ids = (
            self.hyperliquid_receipt_id,
            self.moomoo_receipt_id,
            self.soak_report_id,
        )
        failures = (self.failure_stage, self.failure_code, self.detail)
        if self.status is DailyRunStatus.PASSED:
            if any(value is None for value in proof_ids):
                raise ValueError("passed run requires both collections and the soak report")
            if self.verification is None or not self.verification.accepted:
                raise ValueError("passed run requires an accepted verifier proof")
            if any(value is not None for value in failures):
                raise ValueError("passed run cannot contain failure metadata")
        elif any(value is None for value in failures):
            raise ValueError("non-passing run requires typed failure metadata")
        body = self.model_dump(mode="json", exclude={"receipt_id"})
        if self.receipt_id != _digest(body):
            raise ValueError("daily run receipt ID disagrees with its immutable body")
        return self

    @classmethod
    def build(cls, **values: Any) -> DailyRunReceiptV1:
        if "run_id" not in values:
            values["run_id"] = _digest(
                {
                    "contract": "daily-operational-run-v1",
                    "slot": values["slot"],
                    "attempt": values["attempt"],
                    "code_commit": values["code_commit"],
                }
            )
        probe = cls.model_construct(**values, receipt_id="0" * 64)
        receipt_id = _digest(probe.model_dump(mode="json", exclude={"receipt_id"}))
        return cls(**values, receipt_id=receipt_id)

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class LatestRunPointerV1(_FrozenContract):
    contract: str = Field(default="latest-run-pointer-v1", pattern=r"^latest-run-pointer-v1$")
    slot: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    attempt: int = Field(ge=1)
    receipt_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    prior_pointer_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    pointer_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def identity_matches(self) -> Self:
        body = self.model_dump(mode="json", exclude={"pointer_digest"})
        if self.pointer_digest != _digest(body):
            raise ValueError("latest pointer digest disagrees with its body")
        return self

    @classmethod
    def build(
        cls,
        *,
        slot: str,
        attempt: int,
        receipt_id: str,
        prior_pointer_digest: str | None,
    ) -> LatestRunPointerV1:
        values = {
            "slot": slot,
            "attempt": attempt,
            "receipt_id": receipt_id,
            "prior_pointer_digest": prior_pointer_digest,
        }
        probe = cls.model_construct(**values, pointer_digest="0" * 64)
        return cls(
            **values,
            pointer_digest=_digest(
                probe.model_dump(mode="json", exclude={"pointer_digest"})
            ),
        )

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


_MUTEXES: dict[str, threading.Lock] = {}
_MUTEXES_GUARD = threading.Lock()


@contextmanager
def _file_mutex(path: Path) -> Iterator[None]:
    key = str(path.absolute())
    with _MUTEXES_GUARD:
        local = _MUTEXES.setdefault(key, threading.Lock())
    with local:
        _reject_reparse_chain(path.parent)
        path.parent.mkdir(parents=True, exist_ok=True)
        _reject_reparse_chain(path.parent)
        handle = path.open("a+b")
        try:
            _require_safe_regular(path, label="run-store lock")
            if handle.seek(0, os.SEEK_END) == 0:
                handle.write(b"\0")
                handle.flush()
                os.fsync(handle.fileno())
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                deadline = time.monotonic() + 30
                while True:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError as error:
                        if time.monotonic() >= deadline:
                            raise LeaseHeldError("run-store pointer lock is held") from error
                        time.sleep(0.05)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


class ImmutableRunStore:
    """Create-once run evidence with a verified replaceable latest pointer."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.receipt_dir = self.root / "receipts"
        self.stage_dir = self.root / "stages"
        self.terminal_dir = self.root / "terminals"
        self.latest_path = self.root / "latest.json"
        self.pointer_lock = self.root / ".latest.lock"

    def receipt_path(self, receipt_id: str) -> Path:
        return self.receipt_dir / f"{receipt_id}.json"

    def terminal_path(self, slot: str, attempt: int) -> Path:
        return self.terminal_dir / slot / f"{attempt}.json"

    def stage_path(self, run_id: str, receipt_id: str) -> Path:
        return self.stage_dir / run_id / f"{receipt_id}.json"

    def publish_stage(self, receipt: DailyStageReceiptV1) -> None:
        self._prepare()
        _publish_create_once(
            self.stage_path(receipt.run_id, receipt.receipt_id),
            receipt.canonical_bytes(),
            conflict_label="stage receipt",
        )

    def publish_terminal(self, receipt: DailyRunReceiptV1) -> None:
        self._prepare()
        terminal_path = self.terminal_path(receipt.slot, receipt.attempt)
        _publish_create_once(
            self.receipt_path(receipt.receipt_id),
            receipt.canonical_bytes(),
            conflict_label="receipt",
        )
        _publish_create_once(
            terminal_path,
            receipt.canonical_bytes(),
            conflict_label="terminal",
        )
        with _file_mutex(self.pointer_lock):
            current = self.load_latest_pointer() if self.latest_path.exists() else None
            if current is not None:
                current_position = (current.slot, current.attempt)
                new_position = (receipt.slot, receipt.attempt)
                if current_position > new_position:
                    return
                if current_position == new_position:
                    if current.receipt_id != receipt.receipt_id:
                        raise ImmutableRunConflictError(
                            "latest pointer conflicts with terminal receipt"
                        )
                    return
            pointer = LatestRunPointerV1.build(
                slot=receipt.slot,
                attempt=receipt.attempt,
                receipt_id=receipt.receipt_id,
                prior_pointer_digest=(
                    None if current is None else current.pointer_digest
                ),
            )
            _atomic_replace(self.latest_path, pointer.canonical_bytes())

    def load_terminal(self, slot: str, attempt: int) -> DailyRunReceiptV1:
        terminal = _read_model(
            self.terminal_path(slot, attempt), DailyRunReceiptV1
        )
        receipt = _read_model(
            self.receipt_path(terminal.receipt_id), DailyRunReceiptV1
        )
        if terminal != receipt or terminal.slot != slot or terminal.attempt != attempt:
            raise ValueError("terminal path disagrees with immutable receipt")
        return terminal

    def terminals(self, slot: str) -> tuple[DailyRunReceiptV1, ...]:
        directory = self.terminal_dir / slot
        if not directory.exists():
            return ()
        _reject_reparse_chain(directory)
        paths = tuple(directory.iterdir())
        if any(path.suffix != ".json" or not path.stem.isdigit() for path in paths):
            raise ValueError("terminal slot contains an unexpected entry")
        paths = tuple(sorted(paths, key=lambda item: int(item.stem)))
        return tuple(self.load_terminal(slot, int(path.stem)) for path in paths)

    def load_latest_pointer(self) -> LatestRunPointerV1:
        return _read_model(self.latest_path, LatestRunPointerV1)

    def latest(self) -> DailyRunReceiptV1:
        pointer = self.load_latest_pointer()
        receipt = self.load_terminal(pointer.slot, pointer.attempt)
        if receipt.receipt_id != pointer.receipt_id:
            raise ValueError("latest pointer target disagrees with its receipt")
        return receipt

    def _prepare(self) -> None:
        _reject_reparse_chain(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        _reject_reparse_chain(self.root)
        for directory in (self.receipt_dir, self.stage_dir, self.terminal_dir):
            directory.mkdir(parents=True, exist_ok=True)
            _reject_reparse_chain(directory)


class LeaseOwner(_FrozenContract):
    pid: int = Field(ge=1)
    token: str = Field(min_length=1)
    process_start_token: str = Field(min_length=1)

    @classmethod
    def current(
        cls, *, token: str, process_start_token: str | None = None
    ) -> LeaseOwner:
        pid = os.getpid()
        return cls(
            pid=pid,
            token=token,
            process_start_token=(
                process_start_token
                if process_start_token is not None
                else _process_start_token(pid) or f"opaque-pid:{pid}"
            ),
        )


class _LeaseRecord(_FrozenContract):
    contract: str = Field(default="slot-lease-v1", pattern=r"^slot-lease-v1$")
    slot: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    owner: LeaseOwner
    acquired_at: datetime
    expires_at: datetime
    record_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("acquired_at", "expires_at")
    @classmethod
    def times_are_utc(cls, value: datetime, info: Any) -> datetime:
        return _utc(value, info.field_name)

    @model_validator(mode="after")
    def identity_matches(self) -> Self:
        if self.expires_at <= self.acquired_at:
            raise ValueError("slot lease expiry must follow acquisition")
        body = self.model_dump(mode="json", exclude={"record_digest"})
        if self.record_digest != _digest(body):
            raise ValueError("slot lease digest disagrees with its body")
        return self

    @classmethod
    def build(
        cls,
        *,
        slot: str,
        owner: LeaseOwner,
        acquired_at: datetime,
        expires_at: datetime,
    ) -> _LeaseRecord:
        values = {
            "slot": slot,
            "owner": owner,
            "acquired_at": acquired_at,
            "expires_at": expires_at,
        }
        probe = cls.model_construct(**values, record_digest="0" * 64)
        return cls(
            **values,
            record_digest=_digest(
                probe.model_dump(mode="json", exclude={"record_digest"})
            ),
        )

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class SlotLease:
    """Create-once owner-token lease with dead-owner stale recovery."""

    def __init__(self, path: Path, record: _LeaseRecord) -> None:
        self.path = path
        self.record = record
        self._released = False

    @classmethod
    def acquire(
        cls,
        root: Path,
        slot: str,
        *,
        owner: LeaseOwner,
        now: datetime,
        stale_after: timedelta = timedelta(minutes=30),
        owner_alive: Callable[[LeaseOwner], bool] | None = None,
    ) -> SlotLease:
        instant = _utc(now, "lease acquisition time")
        if stale_after <= timedelta(0):
            raise ValueError("slot lease duration must be positive")
        lease_dir = Path(root) / "leases"
        _reject_reparse_chain(Path(root))
        lease_dir.mkdir(parents=True, exist_ok=True)
        _reject_reparse_chain(lease_dir)
        path = lease_dir / f"{slot}.lock"
        record = _LeaseRecord.build(
            slot=slot,
            owner=owner,
            acquired_at=instant,
            expires_at=instant + stale_after,
        )
        try:
            _publish_create_once(
                path,
                record.canonical_bytes(),
                conflict_label="slot lease",
            )
            return cls(path, record)
        except ImmutableRunConflictError:
            existing = _read_model(path, _LeaseRecord)
            if existing.owner == owner:
                return cls(path, existing)
            if instant <= existing.expires_at:
                raise LeaseHeldError("slot lease is held by another owner")
            probe = owner_alive or _owner_is_alive
            if probe(existing.owner):
                raise LeaseHeldError("stale slot lease owner is still alive")
            quarantine = path.with_name(
                f".{path.name}.{existing.record_digest}.{uuid.uuid4().hex}.recovered"
            )
            try:
                os.replace(path, quarantine)
            except FileNotFoundError:
                return cls.acquire(
                    root,
                    slot,
                    owner=owner,
                    now=instant,
                    stale_after=stale_after,
                    owner_alive=owner_alive,
                )
            try:
                recovered = _read_model(quarantine, _LeaseRecord)
                if recovered != existing:
                    raise ImmutableRunConflictError(
                        "slot lease changed during stale recovery"
                    )
                _publish_create_once(
                    path,
                    record.canonical_bytes(),
                    conflict_label="slot lease",
                )
            finally:
                quarantine.unlink(missing_ok=True)
            return cls(path, record)

    def release(self) -> None:
        if self._released:
            return
        existing = _read_model(self.path, _LeaseRecord)
        if existing != self.record:
            raise ImmutableRunConflictError("slot lease ownership changed before release")
        self.path.unlink()
        self._released = True

    def __enter__(self) -> SlotLease:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


def _owner_is_alive(owner: LeaseOwner) -> bool:
    if not _pid_exists(owner.pid):
        return False
    if owner.process_start_token.startswith("os-start:"):
        current = _process_start_token(owner.pid)
        return current is None or current == owner.process_start_token
    return True


def _pid_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError as error:
        return error.errno == errno.EPERM
    return True


def _process_start_token(pid: int) -> str | None:
    """Return an OS-verifiable process-instance token where the host supports it."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME),
        )
        kernel32.GetProcessTimes.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return None
        creation = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        try:
            if not kernel32.GetProcessTimes(
                handle,
                ctypes.byref(creation),
                ctypes.byref(exit_time),
                ctypes.byref(kernel),
                ctypes.byref(user),
            ):
                return None
            value = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
            return f"os-start:{value}"
        finally:
            kernel32.CloseHandle(handle)
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        fields = stat_path.read_text(encoding="ascii").split()
    except (OSError, UnicodeError):
        return None
    return f"os-start:{fields[21]}" if len(fields) > 21 else None


def _publish_create_once(
    path: Path,
    payload: bytes,
    *,
    conflict_label: str,
) -> None:
    _reject_reparse_chain(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_reparse_chain(path.parent)
    if path.exists():
        if _read_bytes(path) == payload:
            return
        raise ImmutableRunConflictError(f"{conflict_label} already has different bytes")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    linked = False
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
            linked = True
        except FileExistsError:
            if _read_bytes(path) != payload:
                raise ImmutableRunConflictError(
                    f"{conflict_label} already has different bytes"
                )
        if linked:
            temporary.unlink()
        _require_safe_regular(path, label=conflict_label)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_replace(path: Path, payload: bytes) -> None:
    _reject_reparse_chain(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    _reject_reparse_chain(path.parent)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _require_safe_regular(path, label="latest pointer")
    finally:
        temporary.unlink(missing_ok=True)


def _read_model(path: Path, model: type[_FrozenContract]):
    payload = _read_bytes(path)
    evidence = model.model_validate_json(payload)
    if payload != canonical_json_bytes(evidence.model_dump(mode="json")):
        raise ValueError(f"operational evidence JSON is not canonical: {path}")
    return evidence


def _read_bytes(path: Path) -> bytes:
    _require_safe_regular(path, label="operational evidence")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        current = path.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
            or is_reparse_point(path)
        ):
            raise ValueError(f"operational evidence changed while opening: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            return handle.read()
    finally:
        os.close(descriptor)


def _require_safe_regular(path: Path, *, label: str) -> None:
    if is_reparse_point(path):
        raise ValueError(f"{label} path is a symlink or reparse point: {path}")
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode):
        raise ValueError(f"{label} path is not a regular file: {path}")
    if details.st_nlink != 1:
        raise ValueError(f"{label} path has a hard link: {path}")


def _reject_reparse_chain(path: Path) -> None:
    absolute = path.absolute()
    for candidate in (absolute, *absolute.parents):
        if candidate.exists() and is_reparse_point(candidate):
            raise ValueError(f"operational path contains a symlink or reparse point: {candidate}")


def publish_create_once(path: Path, payload: bytes, *, label: str) -> None:
    """Shared crash-safe create-once publication for operational evidence."""
    _publish_create_once(path, payload, conflict_label=label)


def read_safe_bytes(path: Path) -> bytes:
    """Read one regular, single-link, non-reparse operational file."""
    return _read_bytes(path)


def reject_reparse_chain(path: Path) -> None:
    """Reject any existing reparse component in an operational path."""
    _reject_reparse_chain(path)
