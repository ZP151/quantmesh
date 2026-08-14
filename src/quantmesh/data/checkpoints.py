"""Atomic graph-current mappings and collection checkpoints."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import stat
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

import duckdb
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.layout import validate_dataset_name
from quantmesh.data.objects import FABRIC_NAMESPACE, is_reparse_point


class CheckpointConflictError(ValueError):
    """A checkpoint or graph-current compare-and-swap was lost."""


class CheckpointIntegrityError(RuntimeError):
    """Committed graph control rows are missing or internally inconsistent."""


class ConcurrentWriterError(RuntimeError):
    """Another process or thread owns the graph publication lease."""


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CollectionCheckpoint(_FrozenContract):
    """One graph commit's exact provider and publication frontier."""

    job_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation: int = Field(ge=1, le=2**63 - 1)
    provider_cursor: str = Field(min_length=1)
    last_complete_source_event: str = Field(min_length=1)
    raw_object_digests: tuple[str, ...] = Field(min_length=1)
    manifest_ids: tuple[str, ...] = Field(min_length=1)
    preflight_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    quality_report_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt: int = Field(ge=1, le=2**63 - 1)
    updated_at: datetime

    @field_validator("provider_cursor", "last_complete_source_event")
    @classmethod
    def text_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("checkpoint text must not be blank")
        return value

    @field_validator("raw_object_digests", "manifest_ids")
    @classmethod
    def identities_are_unique_digests(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("checkpoint identities must be unique")
        if any(not _is_digest(value) for value in values):
            raise ValueError("checkpoint identities must be lowercase SHA-256 digests")
        return values

    @field_validator("updated_at")
    @classmethod
    def updated_at_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("updated_at must be UTC")
        return value


class GraphAdvance(_FrozenContract):
    """One dataset mapping changed by the same graph commit."""

    dataset_id: str
    expected_current: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    expected_revision: int = Field(ge=0, le=2**63 - 2)
    expected_knowledge_end: datetime | None = None
    manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision: int = Field(ge=1, le=2**63 - 1)
    knowledge_start: datetime
    knowledge_end: datetime

    @field_validator("dataset_id")
    @classmethod
    def dataset_is_valid(cls, value: str) -> str:
        validate_dataset_name(value)
        return value

    @field_validator("expected_knowledge_end", "knowledge_start", "knowledge_end")
    @classmethod
    def knowledge_times_are_utc(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() != timedelta(0)):
            raise ValueError("graph knowledge times must be UTC")
        return value

    @model_validator(mode="after")
    def knowledge_progresses(self) -> GraphAdvance:
        if self.knowledge_start > self.knowledge_end:
            raise ValueError("graph knowledge range is reversed")
        if self.expected_current is None:
            if self.expected_revision != 0 or self.expected_knowledge_end is not None:
                raise ValueError("graph genesis cannot declare predecessor state")
        elif self.expected_revision == 0 or self.expected_knowledge_end is None:
            raise ValueError("graph successor must declare predecessor knowledge")
        elif self.knowledge_start <= self.expected_knowledge_end:
            raise ValueError("graph knowledge time must advance beyond its predecessor")
        return self


class GraphMember(_FrozenContract):
    """The exact manifest high-water included in one committed graph."""

    dataset_id: str
    manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    revision: int = Field(ge=1, le=2**63 - 1)
    knowledge_end: datetime

    @field_validator("dataset_id")
    @classmethod
    def member_dataset_is_valid(cls, value: str) -> str:
        validate_dataset_name(value)
        return value

    @field_validator("knowledge_end")
    @classmethod
    def member_knowledge_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("graph member knowledge time must be UTC")
        return value


_PROCESS_LOCKS: dict[str, threading.RLock] = {}
_PROCESS_LOCKS_GUARD = threading.Lock()
_THREAD_STATE = threading.local()


def _is_digest(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _process_lock(path: Path) -> threading.RLock:
    key = str(path.absolute())
    with _PROCESS_LOCKS_GUARD:
        return _PROCESS_LOCKS.setdefault(key, threading.RLock())


def _owned_paths() -> set[str]:
    owned = getattr(_THREAD_STATE, "owned_paths", None)
    if owned is None:
        owned = set()
        _THREAD_STATE.owned_paths = owned
    return owned


@contextmanager
def _control_lock(path: Path, *, blocking: bool) -> Iterator[None]:
    """Acquire a process-local and OS-visible exclusive one-byte lock."""
    key = str(path.absolute())
    if key in _owned_paths():
        yield
        return
    local = _process_lock(path)
    if not local.acquire(blocking=blocking):
        raise ConcurrentWriterError("trusted-data control plane already has a writer")
    handle = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            _require_safe_lock(path)
        handle = path.open("a+b")
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise CheckpointIntegrityError(
                "trusted-data control lock must be one regular, unlinked inode"
            )
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                deadline = time.monotonic() + 30.0
                while True:
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError as error:
                        retryable = error.errno in {
                            errno.EACCES,
                            errno.EAGAIN,
                            errno.EDEADLK,
                        } or error.winerror in {32, 33, 36}
                        if not blocking or not retryable or time.monotonic() >= deadline:
                            raise
                        time.sleep(0.05)
            else:
                import fcntl

                mode = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
                fcntl.flock(handle.fileno(), mode)
        except (BlockingIOError, OSError) as error:
            raise ConcurrentWriterError(
                "trusted-data control plane already has a writer"
            ) from error
        _require_safe_lock(path)
        if not os.path.samestat(path.stat(), os.fstat(handle.fileno())):
            raise CheckpointIntegrityError(
                "trusted-data control lock path changed while acquiring the lease"
            )
        _owned_paths().add(key)
        try:
            yield
        finally:
            _owned_paths().remove(key)
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        if handle is not None:
            handle.close()
        local.release()


def _require_safe_lock(path: Path) -> None:
    metadata = path.lstat()
    if (
        is_reparse_point(path)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise CheckpointIntegrityError(
            "trusted-data control lock rejects symlinks, reparse points, and hard links"
        )


class CheckpointStore:
    """Short-lived DuckDB transactions behind one cross-process writer lock."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.control = self.root / FABRIC_NAMESPACE / "control"
        self.path = self.control / "collection-checkpoints.duckdb"
        self.lock_path = self.control / "collection-writer.lock"
        self._writer_active = False
        self._writer_owner: int | None = None
        self._reject_reparse_components(self.control)
        self.control.mkdir(parents=True, exist_ok=True)
        self._reject_reparse_components(self.control)
        if not self.path.exists():
            if self._has_graph_ownership_evidence():
                raise CheckpointIntegrityError(
                    "checkpoint database is missing below graph ownership evidence"
                )
            with _control_lock(self.lock_path, blocking=True):
                if not self.path.exists():
                    with self._connect() as connection:
                        self._create_schema(connection)

    def __enter__(self) -> CheckpointStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Compatibility no-op; no DuckDB connection is held between calls."""

    @contextmanager
    def writer(self) -> Iterator[None]:
        if self._writer_active or str(self.lock_path.absolute()) in _owned_paths():
            raise ConcurrentWriterError("trusted-data control plane already has a writer")
        with _control_lock(self.lock_path, blocking=False):
            self._writer_active = True
            self._writer_owner = threading.get_ident()
            try:
                yield
            finally:
                self._writer_owner = None
                self._writer_active = False

    def get(self, job_id: str) -> CollectionCheckpoint | None:
        if not _is_digest(job_id):
            raise ValueError("job_id must be a lowercase SHA-256 digest")
        with self._read_guard(), self._connect(read_only=True) as connection:
            _journal_advances(self.root, connection)
            row = connection.execute(
                """
                SELECT generation, attempt, body_json
                FROM collection_checkpoints WHERE job_id = ?
                """,
                [job_id],
            ).fetchone()
        if row is None:
            return None
        checkpoint = CollectionCheckpoint.model_validate_json(row[2])
        if (int(row[0]), int(row[1])) != (
            checkpoint.generation,
            checkpoint.attempt,
        ):
            raise CheckpointIntegrityError(
                "checkpoint index columns disagree with its canonical body"
            )
        return checkpoint

    def next_attempt(self, job_id: str) -> int:
        """Durably allocate the next retry number while holding the writer lease."""
        self._require_writer_owner("attempt allocation")
        if not _is_digest(job_id):
            raise ValueError("job_id must be a lowercase SHA-256 digest")
        with self._connect() as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                row = connection.execute(
                    "SELECT attempt FROM collection_attempts WHERE job_id = ?",
                    [job_id],
                ).fetchone()
                attempt = 1 if row is None else int(row[0]) + 1
                connection.execute(
                    """
                    INSERT INTO collection_attempts VALUES (?, ?)
                    ON CONFLICT (job_id) DO UPDATE SET attempt = excluded.attempt
                    """,
                    [job_id, attempt],
                )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        return attempt

    def pending(self, job_id: str) -> str | None:
        """Load an exact complete graph candidate, if one survived a crash."""
        if not _is_digest(job_id):
            raise ValueError("job_id must be a lowercase SHA-256 digest")
        with self._read_guard(), self._connect(read_only=True) as connection:
            _journal_advances(self.root, connection)
            row = connection.execute(
                "SELECT body_json FROM pending_graphs WHERE job_id = ?",
                [job_id],
            ).fetchone()
        return None if row is None else str(row[0])

    def source_snapshot(
        self, job_id: str
    ) -> tuple[str, str, int, tuple[str, ...]] | None:
        """Return the aggregate source object and exact raw payload digests."""
        if not _is_digest(job_id):
            raise ValueError("job_id must be a lowercase SHA-256 digest")
        with self._read_guard(), self._connect(read_only=True) as connection:
            _journal_advances(self.root, connection)
            row = connection.execute(
                """
                SELECT media_type, digest, byte_length, raw_digests_json
                FROM source_snapshots WHERE job_id = ?
                """,
                [job_id],
            ).fetchone()
        if row is None:
            return None
        return _source_snapshot_tuple(row)

    def save_source_snapshot(
        self,
        job_id: str,
        *,
        media_type: str,
        digest: str,
        byte_length: int,
        raw_object_digests: tuple[str, ...],
    ) -> None:
        """Bind one exact immutable provider batch to a job before graph building."""
        self._require_writer_owner("source snapshot persistence")
        if not _is_digest(job_id) or not _is_digest(digest):
            raise ValueError("source snapshot identities must be SHA-256 digests")
        if (
            not media_type.strip()
            or byte_length < 0
            or not raw_object_digests
            or any(not _is_digest(item) for item in raw_object_digests)
        ):
            raise ValueError("source snapshot metadata is invalid")
        raw_digests_json = _canonical(list(raw_object_digests))
        observed = (media_type, digest, byte_length, raw_digests_json)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT media_type, digest, byte_length, raw_digests_json
                FROM source_snapshots WHERE job_id = ?
                """,
                [job_id],
            ).fetchone()
            marker_path = self._source_snapshot_path(job_id)
            marker_payload = self._source_snapshot_payload(job_id, observed)
            if row is not None and not marker_path.exists():
                raise CheckpointIntegrityError(
                    "source snapshot marker is missing below its database row"
                )
            if row is None:
                self._write_journal_file(marker_path, marker_payload)
                connection.execute(
                    "INSERT INTO source_snapshots VALUES (?, ?, ?, ?, ?)",
                    [job_id, media_type, digest, byte_length, raw_digests_json],
                )
                return
            expected = (str(row[0]), str(row[1]), int(row[2]), str(row[3]))
            if expected == observed:
                self._write_journal_file(marker_path, marker_payload)
                return
            body = _canonical(
                {
                    "contract": "source-snapshot-conflict-v1",
                    "expected": {
                        "media_type": expected[0],
                        "digest": expected[1],
                        "byte_length": expected[2],
                        "raw_object_digests": json.loads(expected[3]),
                    },
                    "job_id": job_id,
                    "observed": {
                        "media_type": observed[0],
                        "digest": observed[1],
                        "byte_length": observed[2],
                        "raw_object_digests": json.loads(observed[3]),
                    },
                }
            )
            conflict_id = hashlib.sha256(body.encode()).hexdigest()
            connection.execute(
                "INSERT OR IGNORE INTO collection_quarantine VALUES (?, ?, ?, ?)",
                [conflict_id, job_id, -1, body],
            )
            raise CheckpointConflictError(
                "source bytes changed for the same collection job identity"
            )

    def repair_source_snapshots(self) -> None:
        """Reconstruct mutable source rows only from immutable snapshot markers."""
        self._require_writer_owner("source snapshot recovery")
        marker_dir = self.control / "source-snapshots"
        self._reject_reparse_components(marker_dir)
        markers: dict[str, tuple[str, str, int, str]] = {}
        if marker_dir.exists():
            for temporary in list(marker_dir.glob(".*.tmp")):
                metadata = temporary.lstat()
                if (
                    is_reparse_point(temporary)
                    or not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_nlink not in {1, 2}
                ):
                    raise CheckpointIntegrityError(
                        "source snapshot temporary is not canonical"
                    )
                payload = temporary.read_bytes()
                try:
                    body = json.loads(payload)
                    job_id = body["job_id"]
                    if (
                        not _is_digest(job_id)
                        or not temporary.name.startswith(f".{job_id}.")
                    ):
                        raise ValueError("identity mismatch")
                    _decode_source_snapshot_marker(job_id, payload)
                except (KeyError, TypeError, ValueError) as error:
                    raise CheckpointIntegrityError(
                        "source snapshot temporary is invalid"
                    ) from error
                self._recover_prelink_temporary(
                    self._source_snapshot_path(job_id), payload
                )
            for marker_path in marker_dir.iterdir():
                if marker_path.suffix != ".json" or not _is_digest(marker_path.stem):
                    raise CheckpointIntegrityError(
                        "source snapshot directory is not canonical"
                    )
                metadata = marker_path.lstat()
                if (
                    is_reparse_point(marker_path)
                    or not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_nlink != 1
                ):
                    raise CheckpointIntegrityError(
                        "source snapshot marker is not canonical"
                    )
                payload = marker_path.read_bytes()
                self._require_journal_bytes(marker_path, payload)
                markers[marker_path.stem] = _decode_source_snapshot_marker(
                    marker_path.stem, payload
                )
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT job_id, media_type, digest, byte_length, raw_digests_json
                FROM source_snapshots ORDER BY job_id
                """
            ).fetchall()
            database = {
                str(job_id): (
                    str(media_type),
                    str(digest),
                    int(byte_length),
                    str(raw_digests_json),
                )
                for job_id, media_type, digest, byte_length, raw_digests_json in rows
            }
            missing_markers = sorted(set(database) - set(markers))
            if missing_markers:
                raise CheckpointIntegrityError(
                    "source snapshot marker is missing below its database row"
                )
            for job_id, expected in markers.items():
                observed = database.get(job_id)
                if observed is None:
                    connection.execute(
                        "INSERT INTO source_snapshots VALUES (?, ?, ?, ?, ?)",
                        [job_id, *expected],
                    )
                elif observed != expected:
                    raise CheckpointIntegrityError(
                        "source snapshot row disagrees with immutable marker"
                    )

    def save_pending(self, job_id: str, body_json: str) -> None:
        """Persist one immutable complete graph plan before preflight/commit."""
        self._require_writer_owner("pending graph persistence")
        if not _is_digest(job_id):
            raise ValueError("job_id must be a lowercase SHA-256 digest")
        decoded = json.loads(body_json)
        declared = decoded.get("dataset_ids")
        dataset_ids = (
            tuple(declared)
            if isinstance(declared, list)
            else tuple(
                sorted({item["dataset_id"] for item in decoded.get("advances", [])})
            )
        )
        if any(not isinstance(item, str) for item in dataset_ids):
            raise ValueError("pending graph dataset reservations are invalid")
        if len(dataset_ids) != len(set(dataset_ids)):
            raise ValueError("pending graph dataset reservations repeat a dataset")
        for dataset_id in dataset_ids:
            validate_dataset_name(dataset_id)
        with self._connect() as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                conflicts = (
                    connection.execute(
                        """
                        SELECT dataset_id, job_id FROM graph_reservations
                        WHERE dataset_id IN (SELECT UNNEST(?)) AND job_id <> ?
                        """,
                        [list(dataset_ids), job_id],
                    ).fetchall()
                    if dataset_ids
                    else []
                )
                if conflicts:
                    raise CheckpointConflictError(
                        f"dataset {conflicts[0][0]} is reserved by another pending graph"
                    )
                row = connection.execute(
                    "SELECT body_json FROM pending_graphs WHERE job_id = ?",
                    [job_id],
                ).fetchone()
                if row is None:
                    connection.execute(
                        "INSERT INTO pending_graphs VALUES (?, ?)", [job_id, body_json]
                    )
                elif row[0] != body_json:
                    raise CheckpointConflictError(
                        "complete pending graph changed for the same collection job"
                    )
                for dataset_id in dataset_ids:
                    connection.execute(
                        "INSERT OR IGNORE INTO graph_reservations VALUES (?, ?)",
                        [dataset_id, job_id],
                    )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        for dataset_id in dataset_ids:
            self._write_graph_owner(dataset_id)

    def record_progress(
        self,
        job_id: str,
        *,
        position: int,
        dataset_id: str,
        manifest_id: str,
        layer: str,
    ) -> None:
        """Record or compare one staged role; conflicts append quarantine evidence."""
        self._require_writer_owner("graph progress")
        if not _is_digest(job_id) or not _is_digest(manifest_id):
            raise ValueError("graph progress identities must be SHA-256 digests")
        validate_dataset_name(dataset_id)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT dataset_id, manifest_id, layer
                FROM collection_progress WHERE job_id = ? AND position = ?
                """,
                [job_id, position],
            ).fetchone()
            observed = (dataset_id, manifest_id, layer)
            if row is None:
                connection.execute(
                    "INSERT INTO collection_progress VALUES (?, ?, ?, ?, ?)",
                    [job_id, position, dataset_id, manifest_id, layer],
                )
                return
            expected = (str(row[0]), str(row[1]), str(row[2]))
            if expected == observed:
                return
            body = _canonical(
                {
                    "contract": "collection-conflict-v1",
                    "expected": {
                        "dataset_id": expected[0],
                        "manifest_id": expected[1],
                        "layer": expected[2],
                    },
                    "job_id": job_id,
                    "observed": {
                        "dataset_id": observed[0],
                        "manifest_id": observed[1],
                        "layer": observed[2],
                    },
                    "position": position,
                }
            )
            conflict_id = hashlib.sha256(body.encode()).hexdigest()
            connection.execute(
                "INSERT OR IGNORE INTO collection_quarantine VALUES (?, ?, ?, ?)",
                [conflict_id, job_id, position, body],
            )
            raise CheckpointConflictError(
                "staged content changed for the same collection job identity"
            )

    def quarantined(self, job_id: str) -> tuple[str, ...]:
        if not _is_digest(job_id):
            raise ValueError("job_id must be a lowercase SHA-256 digest")
        with self._read_guard(), self._connect(read_only=True) as connection:
            _journal_advances(self.root, connection)
            rows = connection.execute(
                """
                SELECT body_json FROM collection_quarantine
                WHERE job_id = ? ORDER BY position, conflict_id
                """,
                [job_id],
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def commit(
        self,
        *,
        previous: CollectionCheckpoint | None,
        next_checkpoint: CollectionCheckpoint,
        advances: tuple[GraphAdvance, ...],
        commit_id: str,
        owned_dataset_ids: tuple[str, ...] | None = None,
        members: tuple[GraphMember, ...] | None = None,
        source_snapshot: dict[str, Any] | None = None,
    ) -> None:
        """CAS all graph mappings and the checkpoint in one DuckDB transaction."""
        self._require_writer_owner("graph commit")
        if not _is_digest(commit_id):
            raise ValueError("commit_id must be a lowercase SHA-256 digest")
        self._validate_progression(previous, next_checkpoint)
        dataset_ids = [advance.dataset_id for advance in advances]
        if len(dataset_ids) != len(set(dataset_ids)):
            raise ValueError("a graph commit may advance each dataset only once")
        owned_dataset_ids = (
            tuple(dataset_ids)
            if owned_dataset_ids is None
            else owned_dataset_ids
        )
        if len(owned_dataset_ids) != len(set(owned_dataset_ids)):
            raise ValueError("a graph commit may own each dataset only once")
        for dataset_id in owned_dataset_ids:
            validate_dataset_name(dataset_id)
        if not set(dataset_ids).issubset(owned_dataset_ids):
            raise ValueError("every graph advance must belong to the committed graph")
        members = (
            tuple(
                GraphMember(
                    dataset_id=advance.dataset_id,
                    manifest_id=advance.manifest_id,
                    revision=advance.revision,
                    knowledge_end=advance.knowledge_end,
                )
                for advance in advances
            )
            if members is None
            else members
        )
        member_ids = [member.dataset_id for member in members]
        if len(member_ids) != len(set(member_ids)):
            raise ValueError("a graph commit may anchor each dataset only once")
        if set(member_ids) != set(owned_dataset_ids):
            raise ValueError("every owned dataset requires an exact member anchor")
        member_by_dataset = {member.dataset_id: member for member in members}
        if any(
            member_by_dataset[advance.dataset_id]
            != GraphMember(
                dataset_id=advance.dataset_id,
                manifest_id=advance.manifest_id,
                revision=advance.revision,
                knowledge_end=advance.knowledge_end,
            )
            for advance in advances
        ):
            raise ValueError("graph advance disagrees with its member anchor")
        body = _canonical(
            {
                "advances": [advance.model_dump(mode="json") for advance in advances],
                "checkpoint": next_checkpoint.model_dump(mode="json"),
                "commit_id": commit_id,
                "contract": "trusted-graph-commit-v1",
                "members": [member.model_dump(mode="json") for member in members],
                "owned_dataset_ids": list(owned_dataset_ids),
                "source_snapshot": source_snapshot,
                "journal_sequence": self._next_journal_sequence(),
                "previous_journal_digest": self._previous_journal_digest(),
            }
        )
        intent_path = self._journal_path(commit_id, committed=False)
        self._write_journal_file(intent_path, body.encode())
        with self._connect() as connection:
            connection.execute("BEGIN TRANSACTION")
            try:
                self._require_checkpoint(connection, previous, next_checkpoint.job_id)
                for advance in advances:
                    self._advance_dataset(connection, advance, commit_id)
                connection.execute(
                    "INSERT INTO graph_commits VALUES (?, ?, ?, ?, ?)",
                    [
                        commit_id,
                        next_checkpoint.job_id,
                        next_checkpoint.run_id,
                        json.loads(body)["journal_sequence"],
                        body,
                    ],
                )
                checkpoint_json = _canonical(next_checkpoint.model_dump(mode="json"))
                if previous is None:
                    connection.execute(
                        "INSERT INTO collection_checkpoints VALUES (?, ?, ?, ?)",
                        [
                            next_checkpoint.job_id,
                            next_checkpoint.generation,
                            next_checkpoint.attempt,
                            checkpoint_json,
                        ],
                    )
                else:
                    connection.execute(
                        """
                        UPDATE collection_checkpoints
                        SET generation = ?, attempt = ?, body_json = ?
                        WHERE job_id = ?
                        """,
                        [
                            next_checkpoint.generation,
                            next_checkpoint.attempt,
                            checkpoint_json,
                            next_checkpoint.job_id,
                        ],
                    )
                connection.execute(
                    "DELETE FROM pending_graphs WHERE job_id = ?",
                    [next_checkpoint.job_id],
                )
                connection.execute(
                    "DELETE FROM collection_progress WHERE job_id = ?",
                    [next_checkpoint.job_id],
                )
                connection.execute(
                    "DELETE FROM graph_reservations WHERE job_id = ?",
                    [next_checkpoint.job_id],
                )
                connection.execute("COMMIT")
            except BaseException:
                connection.execute("ROLLBACK")
                raise
        for dataset_id in owned_dataset_ids:
            self._write_graph_owner(dataset_id)
        self._write_journal_file(
            self._journal_path(commit_id, committed=True),
            body.encode(),
        )
        intent_path.unlink(missing_ok=True)

    def repair_commit_journals(self) -> None:
        """Finish only journals whose graph transaction is already committed."""
        self._require_writer_owner("commit journal recovery")
        with self._connect(read_only=True) as connection:
            rows = connection.execute(
                "SELECT commit_id, body_json FROM graph_commits ORDER BY journal_sequence"
            ).fetchall()
        for commit_id, body_json in rows:
            committed_path = self._journal_path(str(commit_id), committed=True)
            intent_path = self._journal_path(str(commit_id), committed=False)
            expected_payload = str(body_json).encode()
            self._recover_prelink_temporary(committed_path, expected_payload)
            self._recover_prelink_temporary(intent_path, expected_payload)
            if committed_path.exists():
                self._recover_temporary_links(
                    committed_path, expected_payload
                )
                self._require_journal_bytes(committed_path, expected_payload)
                if intent_path.exists():
                    self._recover_temporary_links(
                        intent_path, expected_payload
                    )
                    self._require_journal_bytes(intent_path, expected_payload)
                    intent_path.unlink()
                continue
            if not intent_path.exists():
                raise CheckpointIntegrityError(
                    f"committed graph {commit_id} has no recoverable commit journal"
                )
            self._recover_temporary_links(intent_path, expected_payload)
            payload = intent_path.read_bytes()
            if payload != str(body_json).encode():
                raise CheckpointIntegrityError("commit journal intent disagrees with DuckDB")
            self._write_journal_file(committed_path, payload)
            intent_path.unlink(missing_ok=True)
        committed_ids = {str(commit_id) for commit_id, _body_json in rows}
        intent_dir = self.control / "graph-intents"
        self._reject_reparse_components(intent_dir)
        if intent_dir.exists():
            self._remove_uncommitted_intent_temporaries(committed_ids)
            for intent_path in intent_dir.iterdir():
                if intent_path.suffix != ".json" or not _is_digest(intent_path.stem):
                    raise CheckpointIntegrityError(
                        "commit intent directory is not canonical"
                    )
                payload = intent_path.read_bytes()
                self._recover_temporary_links(intent_path, payload)
                self._require_journal_bytes(intent_path, payload)
                try:
                    body = json.loads(payload)
                except (json.JSONDecodeError, UnicodeDecodeError) as error:
                    raise CheckpointIntegrityError("commit intent is invalid") from error
                if (
                    body.get("contract") != "trusted-graph-commit-v1"
                    or body.get("commit_id") != intent_path.stem
                ):
                    raise CheckpointIntegrityError("commit intent identity is invalid")
                if intent_path.stem not in committed_ids:
                    intent_path.unlink()
        latest: dict[str, CollectionCheckpoint] = {}
        for _commit_id, body_json in rows:
            body = json.loads(str(body_json))
            checkpoint = CollectionCheckpoint.model_validate_json(
                _canonical(body["checkpoint"])
            )
            latest[checkpoint.job_id] = checkpoint
        with self._connect() as connection:
            for checkpoint in latest.values():
                row = connection.execute(
                    """
                    SELECT generation, attempt, body_json
                    FROM collection_checkpoints WHERE job_id = ?
                    """,
                    [checkpoint.job_id],
                ).fetchone()
                expected = _canonical(checkpoint.model_dump(mode="json"))
                if row is None:
                    connection.execute(
                        "INSERT INTO collection_checkpoints VALUES (?, ?, ?, ?)",
                        [
                            checkpoint.job_id,
                            checkpoint.generation,
                            checkpoint.attempt,
                            expected,
                        ],
                    )
                elif (
                    int(row[0]),
                    int(row[1]),
                    str(row[2]),
                ) != (
                    checkpoint.generation,
                    checkpoint.attempt,
                    expected,
                ):
                    raise CheckpointIntegrityError(
                        "checkpoint row disagrees with immutable commit journal"
                    )

    def repair_graph_owners(self) -> None:
        """Complete owner markers from durable reservations and committed graphs."""
        self._require_writer_owner("graph owner recovery")
        with self._connect(read_only=True) as connection:
            reserved = {
                str(row[0])
                for row in connection.execute(
                    "SELECT dataset_id FROM graph_reservations"
                ).fetchall()
            }
            bodies = connection.execute(
                "SELECT body_json FROM graph_commits ORDER BY journal_sequence"
            ).fetchall()
        committed: set[str] = set()
        for (body_json,) in bodies:
            body = json.loads(str(body_json))
            declared = body.get("owned_dataset_ids")
            if declared is None:
                declared = [item["dataset_id"] for item in body["advances"]]
            committed.update(str(item) for item in declared)
        for dataset_id in sorted(reserved | committed):
            self._write_graph_owner(dataset_id)

    def _next_journal_sequence(self) -> int:
        with self._connect(read_only=True) as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(journal_sequence), 0) FROM graph_commits"
            ).fetchone()
        return int(row[0]) + 1

    def _previous_journal_digest(self) -> str | None:
        with self._connect(read_only=True) as connection:
            row = connection.execute(
                """
                SELECT body_json FROM graph_commits
                ORDER BY journal_sequence DESC LIMIT 1
                """
            ).fetchone()
        return None if row is None else hashlib.sha256(str(row[0]).encode()).hexdigest()

    def _journal_path(self, commit_id: str, *, committed: bool) -> Path:
        if not _is_digest(commit_id):
            raise ValueError("journal commit ID must be a SHA-256 digest")
        directory = "graph-commits" if committed else "graph-intents"
        path = self.control / directory / f"{commit_id}.json"
        self._reject_reparse_components(path)
        return path

    def _graph_owner_path(self, dataset_id: str) -> Path:
        validate_dataset_name(dataset_id)
        path = (
            self.root
            / FABRIC_NAMESPACE
            / "datasets"
            / dataset_id
            / "graph-owner.json"
        )
        self._reject_reparse_components(path)
        return path

    def _source_snapshot_path(self, job_id: str) -> Path:
        if not _is_digest(job_id):
            raise ValueError("source snapshot job ID must be a SHA-256 digest")
        path = self.control / "source-snapshots" / f"{job_id}.json"
        self._reject_reparse_components(path)
        return path

    @staticmethod
    def _source_snapshot_payload(
        job_id: str, snapshot: tuple[str, str, int, str]
    ) -> bytes:
        media_type, digest, byte_length, raw_digests_json = snapshot
        return _canonical(
            {
                "byte_length": byte_length,
                "contract": "trusted-source-snapshot-v1",
                "digest": digest,
                "job_id": job_id,
                "media_type": media_type,
                "raw_object_digests": json.loads(raw_digests_json),
            }
        ).encode()

    def _write_graph_owner(self, dataset_id: str) -> None:
        self._write_journal_file(
            self._graph_owner_path(dataset_id),
            _canonical(
                {"contract": "trusted-graph-owner-v1", "dataset_id": dataset_id}
            ).encode(),
        )

    def _has_graph_ownership_evidence(self) -> bool:
        committed = self.control / "graph-commits"
        if committed.exists() and any(committed.iterdir()):
            return True
        datasets = self.root / FABRIC_NAMESPACE / "datasets"
        return datasets.exists() and any(datasets.glob("*/graph-owner.json"))

    def _write_journal_file(self, path: Path, payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._reject_reparse_components(path)
        self._recover_prelink_temporary(path, payload)
        if path.exists():
            self._recover_temporary_links(path, payload)
            self._require_journal_bytes(path, payload)
            return
        descriptor, temporary = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.stem}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                self._require_journal_bytes(path, payload)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self._require_journal_bytes(path, payload)

    def _recover_prelink_temporary(self, path: Path, expected: bytes) -> None:
        """Promote exact one-link bytes left before the atomic hard-link step."""
        for candidate in path.parent.glob(f".{path.stem}.*.tmp"):
            metadata = candidate.lstat()
            if (
                is_reparse_point(candidate)
                or not stat.S_ISREG(metadata.st_mode)
                or candidate.read_bytes() != expected
            ):
                raise CheckpointIntegrityError(
                    "journal temporary file is not canonical recovery evidence"
                )
            if metadata.st_nlink == 2 and path.exists():
                self._recover_temporary_links(path, expected)
                continue
            if metadata.st_nlink != 1:
                raise CheckpointIntegrityError(
                    "journal temporary file has an invalid link count"
                )
            if not path.exists():
                os.link(candidate, path)
            candidate.unlink()

    def _remove_uncommitted_intent_temporaries(
        self, committed_ids: set[str]
    ) -> None:
        intent_dir = self.control / "graph-intents"
        for temporary in intent_dir.glob(".*.tmp"):
            metadata = temporary.lstat()
            if (
                is_reparse_point(temporary)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink not in {1, 2}
            ):
                raise CheckpointIntegrityError(
                    "uncommitted intent temporary is not canonical"
                )
            payload = temporary.read_bytes()
            try:
                body = json.loads(payload)
                commit_id = body["commit_id"]
                if (
                    body.get("contract") != "trusted-graph-commit-v1"
                    or not _is_digest(commit_id)
                    or not temporary.name.startswith(f".{commit_id}.")
                    or commit_id in committed_ids
                ):
                    raise ValueError("identity mismatch")
            except (KeyError, TypeError, ValueError) as error:
                raise CheckpointIntegrityError(
                    "uncommitted intent temporary is invalid"
                ) from error
            if metadata.st_nlink == 2:
                target = self._journal_path(commit_id, committed=False)
                if (
                    not target.exists()
                    or target.read_bytes() != payload
                    or not os.path.samestat(target.lstat(), metadata)
                ):
                    raise CheckpointIntegrityError(
                        "post-link intent temporary lost its authoritative target"
                    )
            temporary.unlink()

    def _recover_temporary_links(self, path: Path, expected: bytes) -> None:
        """Remove only same-inode temporary links left by an interrupted publish."""
        metadata = path.lstat()
        if (
            is_reparse_point(path)
            or not stat.S_ISREG(metadata.st_mode)
            or path.read_bytes() != expected
        ):
            return
        for candidate in path.parent.glob(f".{path.stem}.*.tmp"):
            candidate_metadata = candidate.lstat()
            if (
                not is_reparse_point(candidate)
                and stat.S_ISREG(candidate_metadata.st_mode)
                and os.path.samestat(metadata, candidate_metadata)
            ):
                candidate.unlink()

    @staticmethod
    def _require_journal_bytes(path: Path, expected: bytes) -> None:
        metadata = path.lstat()
        if (
            is_reparse_point(path)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or path.read_bytes() != expected
        ):
            raise CheckpointIntegrityError("commit journal is not canonical immutable evidence")

    def _advance_dataset(
        self,
        connection: duckdb.DuckDBPyConnection,
        advance: GraphAdvance,
        commit_id: str,
    ) -> None:
        if advance.revision != advance.expected_revision + 1:
            raise CheckpointConflictError(
                f"dataset {advance.dataset_id} revision is not consecutive"
            )
        row = connection.execute(
            """
            SELECT manifest_id, compatibility_revision, knowledge_end
            FROM graph_currents WHERE dataset_id = ?
            """,
            [advance.dataset_id],
        ).fetchone()
        if row is not None and (row[0], row[1], row[2]) != (
            advance.expected_current,
            advance.expected_revision,
            advance.expected_knowledge_end.isoformat()
            if advance.expected_knowledge_end is not None
            else None,
        ):
            raise CheckpointConflictError(
                f"dataset {advance.dataset_id} current compare-and-swap lost"
            )
        if row is None and advance.expected_revision == 0 and advance.expected_current is not None:
            raise CheckpointConflictError(
                f"dataset {advance.dataset_id} has a current ID without a revision"
            )
        connection.execute(
            "INSERT INTO graph_history VALUES (?, ?, ?, ?, ?, ?)",
            [
                advance.dataset_id,
                advance.revision,
                advance.manifest_id,
                commit_id,
                advance.knowledge_start.isoformat(),
                advance.knowledge_end.isoformat(),
            ],
        )
        connection.execute(
            """
            INSERT INTO graph_currents VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (dataset_id) DO UPDATE SET
                manifest_id = excluded.manifest_id,
                compatibility_revision = excluded.compatibility_revision,
                commit_id = excluded.commit_id,
                knowledge_end = excluded.knowledge_end
            """,
            [
                advance.dataset_id,
                advance.manifest_id,
                advance.revision,
                commit_id,
                advance.knowledge_end.isoformat(),
            ],
        )

    @staticmethod
    def _validate_progression(
        previous: CollectionCheckpoint | None,
        next_checkpoint: CollectionCheckpoint,
    ) -> None:
        expected_generation = 1 if previous is None else previous.generation + 1
        if next_checkpoint.generation != expected_generation:
            raise CheckpointConflictError("checkpoint generation is not consecutive")
        if previous is not None:
            if previous.job_id != next_checkpoint.job_id:
                raise CheckpointConflictError("checkpoint job IDs differ")
            if next_checkpoint.attempt <= previous.attempt:
                raise CheckpointConflictError("checkpoint attempt did not advance")

    @staticmethod
    def _require_checkpoint(
        connection: duckdb.DuckDBPyConnection,
        previous: CollectionCheckpoint | None,
        job_id: str,
    ) -> None:
        row = connection.execute(
            "SELECT body_json FROM collection_checkpoints WHERE job_id = ?",
            [job_id],
        ).fetchone()
        actual = None if row is None else CollectionCheckpoint.model_validate_json(row[0])
        if actual != previous:
            raise CheckpointConflictError("checkpoint compare-and-swap lost")

    @contextmanager
    def _read_guard(self) -> Iterator[None]:
        if self._writer_owner == threading.get_ident():
            yield
        else:
            with _control_lock(self.lock_path, blocking=True):
                yield

    def _require_writer_owner(self, operation: str) -> None:
        if not self._writer_active or self._writer_owner != threading.get_ident():
            raise RuntimeError(f"{operation} requires this thread's writer lease")

    def _connect(self, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
        self._reject_reparse_components(self.path)
        return duckdb.connect(str(self.path), read_only=read_only)

    @staticmethod
    def _create_schema(connection: duckdb.DuckDBPyConnection) -> None:
        connection.execute(
            """
            CREATE TABLE collection_checkpoints (
                job_id VARCHAR PRIMARY KEY,
                generation BIGINT NOT NULL,
                attempt BIGINT NOT NULL,
                body_json VARCHAR NOT NULL
            );
            CREATE TABLE graph_currents (
                dataset_id VARCHAR PRIMARY KEY,
                manifest_id VARCHAR NOT NULL,
                compatibility_revision BIGINT NOT NULL,
                commit_id VARCHAR NOT NULL,
                knowledge_end VARCHAR NOT NULL
            );
            CREATE TABLE graph_history (
                dataset_id VARCHAR NOT NULL,
                compatibility_revision BIGINT NOT NULL,
                manifest_id VARCHAR NOT NULL,
                commit_id VARCHAR NOT NULL,
                knowledge_start VARCHAR NOT NULL,
                knowledge_end VARCHAR NOT NULL,
                PRIMARY KEY (dataset_id, compatibility_revision)
            );
            CREATE TABLE graph_commits (
                commit_id VARCHAR PRIMARY KEY,
                job_id VARCHAR NOT NULL,
                run_id VARCHAR NOT NULL,
                journal_sequence BIGINT UNIQUE NOT NULL,
                body_json VARCHAR NOT NULL
            );
            CREATE TABLE collection_attempts (
                job_id VARCHAR PRIMARY KEY,
                attempt BIGINT NOT NULL
            );
            CREATE TABLE pending_graphs (
                job_id VARCHAR PRIMARY KEY,
                body_json VARCHAR NOT NULL
            );
            CREATE TABLE graph_reservations (
                dataset_id VARCHAR PRIMARY KEY,
                job_id VARCHAR NOT NULL
            );
            CREATE TABLE source_snapshots (
                job_id VARCHAR PRIMARY KEY,
                media_type VARCHAR NOT NULL,
                digest VARCHAR NOT NULL,
                byte_length BIGINT NOT NULL,
                raw_digests_json VARCHAR NOT NULL
            );
            CREATE TABLE collection_progress (
                job_id VARCHAR NOT NULL,
                position BIGINT NOT NULL,
                dataset_id VARCHAR NOT NULL,
                manifest_id VARCHAR NOT NULL,
                layer VARCHAR NOT NULL,
                PRIMARY KEY (job_id, position)
            );
            CREATE TABLE collection_quarantine (
                conflict_id VARCHAR PRIMARY KEY,
                job_id VARCHAR NOT NULL,
                position BIGINT NOT NULL,
                body_json VARCHAR NOT NULL
            )
            """
        )

    def _reject_reparse_components(self, target: Path) -> None:
        try:
            relative = target.relative_to(self.root)
        except ValueError as error:
            raise ValueError(f"checkpoint path escapes trusted root: {target}") from error
        _reject_existing_reparse_chain(self.root)
        _reject_existing_reparse_chain(self.root / relative)


def committed_current(root: Path, dataset_id: str) -> str | None:
    """Return a graph-committed current manifest without creating control state."""
    validate_dataset_name(dataset_id)
    database, lock = _control_paths(Path(root))
    if not database.exists():
        if _surviving_graph_evidence(Path(root)):
            raise CheckpointIntegrityError(
                "checkpoint database is missing below graph ownership evidence"
            )
        return None
    _reject_control_reparse(Path(root), database, lock)
    with _control_lock(lock, blocking=True), duckdb.connect(
        str(database), read_only=True
    ) as connection:
        evidence = _journal_advances(Path(root), connection)
        row = connection.execute(
            """
            SELECT manifest_id, compatibility_revision, commit_id, knowledge_end
            FROM graph_currents WHERE dataset_id = ?
            """,
            [dataset_id],
        ).fetchone()
        history = connection.execute(
            """
            SELECT manifest_id, compatibility_revision, commit_id,
                   knowledge_start, knowledge_end
            FROM graph_history WHERE dataset_id = ?
            ORDER BY compatibility_revision
            """,
            [dataset_id],
        ).fetchall()
        reservation = connection.execute(
            "SELECT job_id FROM graph_reservations WHERE dataset_id = ?",
            [dataset_id],
        ).fetchone()
    owned = _graph_owner(Path(root), dataset_id)
    latest = None if not history else history[-1]
    journal_rows = evidence.history.get(dataset_id, ())
    if journal_rows and tuple(tuple(item) for item in history) != journal_rows:
        raise CheckpointIntegrityError("commit journal is missing from graph history")
    if history and not journal_rows:
        raise CheckpointIntegrityError("graph history has no committed journal evidence")
    if row is None and latest is not None:
        raise CheckpointIntegrityError("graph current is missing below committed history")
    if row is not None and latest is None:
        raise CheckpointIntegrityError("graph history is missing below committed current")
    if row is not None and latest is not None and tuple(row) != (
        latest[0],
        latest[1],
        latest[2],
        latest[4],
    ):
        raise CheckpointIntegrityError("graph current disagrees with committed history")
    if (
        owned
        and row is None
        and reservation is None
        and dataset_id not in evidence.owned_dataset_ids
    ):
        raise CheckpointIntegrityError(
            "graph-owned dataset has no current or pending reservation"
        )
    if row is not None and not owned:
        raise CheckpointIntegrityError("graph current has no ownership marker")
    return None if row is None else str(row[0])


def committed_history(root: Path, dataset_id: str) -> tuple[str, ...]:
    """Return graph-committed manifest IDs in compatibility order."""
    validate_dataset_name(dataset_id)
    database, lock = _control_paths(Path(root))
    if not database.exists():
        if _surviving_graph_evidence(Path(root)):
            raise CheckpointIntegrityError(
                "checkpoint database is missing below graph ownership evidence"
            )
        return ()
    _reject_control_reparse(Path(root), database, lock)
    with _control_lock(lock, blocking=True), duckdb.connect(
        str(database), read_only=True
    ) as connection:
        evidence = _journal_advances(Path(root), connection)
        rows = connection.execute(
            """
            SELECT manifest_id, compatibility_revision, commit_id,
                   knowledge_start, knowledge_end
            FROM graph_history
            WHERE dataset_id = ? ORDER BY compatibility_revision
            """,
            [dataset_id],
        ).fetchall()
        current = connection.execute(
            """
            SELECT manifest_id, compatibility_revision, commit_id, knowledge_end
            FROM graph_currents WHERE dataset_id = ?
            """,
            [dataset_id],
        ).fetchone()
        reservation = connection.execute(
            "SELECT job_id FROM graph_reservations WHERE dataset_id = ?",
            [dataset_id],
        ).fetchone()
    owned = _graph_owner(Path(root), dataset_id)
    journal_rows = evidence.history.get(dataset_id, ())
    if journal_rows and tuple(tuple(row) for row in rows) != journal_rows:
        raise CheckpointIntegrityError("commit journal disagrees with graph history")
    if rows and not journal_rows:
        raise CheckpointIntegrityError("graph history has no committed journal evidence")
    if rows and current is None:
        raise CheckpointIntegrityError("graph current is missing below committed history")
    if current is not None and not rows:
        raise CheckpointIntegrityError("graph history is missing below committed current")
    if rows and current is not None and (
        rows[-1][0],
        rows[-1][1],
        rows[-1][2],
        rows[-1][4],
    ) != tuple(current):
        raise CheckpointIntegrityError("graph current disagrees with committed history")
    if (
        owned
        and current is None
        and reservation is None
        and dataset_id not in evidence.owned_dataset_ids
    ):
        raise CheckpointIntegrityError(
            "graph-owned dataset has no current or pending reservation"
        )
    if current is not None and not owned:
        raise CheckpointIntegrityError("graph current has no ownership marker")
    return tuple(str(row[0]) for row in rows)


_GraphHistoryRow = tuple[str, int, str, str, str]


class _VerifiedGraph(NamedTuple):
    history: dict[str, tuple[_GraphHistoryRow, ...]]
    owned_dataset_ids: frozenset[str]
    members: dict[str, GraphMember]


def _journal_advances(
    root: Path, connection: duckdb.DuckDBPyConnection
) -> _VerifiedGraph:
    """Verify immutable commit evidence and reconstruct graph-managed history."""
    control = root / FABRIC_NAMESPACE / "control"
    journal_dir = control / "graph-commits"
    _reject_control_reparse(root, journal_dir)
    database_rows = connection.execute(
        """
        SELECT commit_id, job_id, run_id, journal_sequence, body_json
        FROM graph_commits ORDER BY journal_sequence
        """
    ).fetchall()
    database = {
        str(commit_id): (str(job_id), str(run_id), int(sequence), str(body_json))
        for commit_id, job_id, run_id, sequence, body_json in database_rows
    }
    files: dict[str, Path] = {}
    if journal_dir.exists():
        for path in journal_dir.iterdir():
            if path.suffix != ".json" or not _is_digest(path.stem):
                raise CheckpointIntegrityError("commit journal directory is not canonical")
            files[path.stem] = path
    if set(files) != set(database):
        raise CheckpointIntegrityError("commit journal set disagrees with DuckDB commits")

    advances: dict[str, list[_GraphHistoryRow]] = {}
    owned_dataset_ids: set[str] = set()
    latest_members: dict[str, GraphMember] = {}
    previous_digest: str | None = None
    expected_checkpoints: dict[str, CollectionCheckpoint] = {}
    committed_snapshots: dict[str, dict[str, Any] | None] = {}
    for expected_sequence, (commit_id, record) in enumerate(database.items(), start=1):
        job_id, run_id, sequence, body_json = record
        path = files[commit_id]
        CheckpointStore._require_journal_bytes(path, body_json.encode())
        try:
            body = json.loads(body_json)
            if (
                body.get("contract") != "trusted-graph-commit-v1"
                or body.get("commit_id") != commit_id
                or body.get("journal_sequence") != sequence
                or sequence != expected_sequence
                or body.get("previous_journal_digest") != previous_digest
            ):
                raise ValueError("identity mismatch")
            checkpoint = CollectionCheckpoint.model_validate_json(
                _canonical(body["checkpoint"])
            )
            if checkpoint.job_id != job_id or checkpoint.run_id != run_id:
                raise ValueError("checkpoint identity mismatch")
            expected_checkpoints[checkpoint.job_id] = checkpoint
            source_snapshot = body["source_snapshot"]
            if source_snapshot is not None and not isinstance(source_snapshot, dict):
                raise ValueError("source snapshot evidence is invalid")
            committed_snapshots[checkpoint.job_id] = source_snapshot
            decoded = tuple(
                GraphAdvance.model_validate_json(_canonical(item))
                for item in body["advances"]
            )
            declared_owners = tuple(body["owned_dataset_ids"])
            if len(declared_owners) != len(set(declared_owners)):
                raise ValueError("duplicate graph owner")
            for dataset_id in declared_owners:
                validate_dataset_name(dataset_id)
            if not {advance.dataset_id for advance in decoded}.issubset(
                declared_owners
            ):
                raise ValueError("graph advance is outside its ownership set")
            members = tuple(
                GraphMember.model_validate_json(_canonical(item))
                for item in body["members"]
            )
            if (
                len({member.dataset_id for member in members}) != len(members)
                or {member.dataset_id for member in members}
                != set(declared_owners)
            ):
                raise ValueError("graph member anchors disagree with ownership")
            member_by_dataset = {
                member.dataset_id: member for member in members
            }
            advance_by_dataset = {
                advance.dataset_id: advance for advance in decoded
            }
            if any(
                member_by_dataset[advance.dataset_id]
                != GraphMember(
                    dataset_id=advance.dataset_id,
                    manifest_id=advance.manifest_id,
                    revision=advance.revision,
                    knowledge_end=advance.knowledge_end,
                )
                for advance in decoded
            ):
                raise ValueError("graph member anchor disagrees with its advance")
            for dataset_id, member in member_by_dataset.items():
                previous_member = latest_members.get(dataset_id)
                advance = advance_by_dataset.get(dataset_id)
                if previous_member is None:
                    continue
                if advance is None and member != previous_member:
                    raise ValueError("unchanged graph member anchor moved")
                if advance is not None and (
                    advance.expected_current,
                    advance.expected_revision,
                    advance.expected_knowledge_end,
                ) != (
                    previous_member.manifest_id,
                    previous_member.revision,
                    previous_member.knowledge_end,
                ):
                    raise ValueError("graph member predecessor anchor changed")
            owned_dataset_ids.update(declared_owners)
            latest_members.update(member_by_dataset)
        except (KeyError, TypeError, ValueError) as error:
            raise CheckpointIntegrityError("commit journal body is invalid") from error
        previous_digest = hashlib.sha256(body_json.encode()).hexdigest()
        for advance in decoded:
            advances.setdefault(advance.dataset_id, []).append(
                (
                    advance.manifest_id,
                    advance.revision,
                    commit_id,
                    advance.knowledge_start.isoformat(),
                    advance.knowledge_end.isoformat(),
                )
            )

    checkpoint_rows = connection.execute(
        """
        SELECT job_id, generation, attempt, body_json
        FROM collection_checkpoints ORDER BY job_id
        """
    ).fetchall()
    observed_checkpoints = {
        str(job_id): (int(generation), int(attempt), str(body_json))
        for job_id, generation, attempt, body_json in checkpoint_rows
    }
    for generation, attempt, body_json in observed_checkpoints.values():
        checkpoint = CollectionCheckpoint.model_validate_json(body_json)
        if (generation, attempt) != (checkpoint.generation, checkpoint.attempt):
            raise CheckpointIntegrityError(
                "checkpoint index columns disagree with its canonical body"
            )
    expected_checkpoint_rows = {
        job_id: (
            checkpoint.generation,
            checkpoint.attempt,
            _canonical(checkpoint.model_dump(mode="json")),
        )
        for job_id, checkpoint in expected_checkpoints.items()
    }
    if observed_checkpoints != expected_checkpoint_rows:
        raise CheckpointIntegrityError(
            "checkpoint rows disagree with immutable commit journals"
        )

    durable_snapshots = _verify_source_snapshot_rows(root, connection)
    for job_id, expected_snapshot in committed_snapshots.items():
        observed_snapshot = durable_snapshots.get(job_id)
        if expected_snapshot != observed_snapshot:
            raise CheckpointIntegrityError(
                "committed source snapshot disagrees with immutable evidence"
            )

    result: dict[str, tuple[_GraphHistoryRow, ...]] = {}
    for dataset_id, values in advances.items():
        ordered = tuple(sorted(values, key=lambda item: item[1]))
        if len({item[1] for item in ordered}) != len(ordered):
            raise CheckpointIntegrityError("commit journal repeats a graph revision")
        result[dataset_id] = ordered
    verified = _VerifiedGraph(
        result, frozenset(owned_dataset_ids), latest_members
    )
    _verify_complete_graph_state(root, connection, verified)
    return verified


def _source_snapshot_tuple(
    row: tuple[Any, ...],
) -> tuple[str, str, int, tuple[str, ...]]:
    raw_digests = tuple(json.loads(str(row[3])))
    if not raw_digests or any(not _is_digest(item) for item in raw_digests):
        raise CheckpointIntegrityError("source snapshot raw digest set is invalid")
    media_type, digest, byte_length = str(row[0]), str(row[1]), int(row[2])
    if not media_type.strip() or not _is_digest(digest) or byte_length < 0:
        raise CheckpointIntegrityError("source snapshot metadata is invalid")
    return media_type, digest, byte_length, raw_digests


def _decode_source_snapshot_marker(
    job_id: str, payload: bytes
) -> tuple[str, str, int, str]:
    try:
        body = json.loads(payload)
        if (
            body.get("contract") != "trusted-source-snapshot-v1"
            or body.get("job_id") != job_id
        ):
            raise ValueError("identity mismatch")
        snapshot = _source_snapshot_tuple(
            (
                body["media_type"],
                body["digest"],
                body["byte_length"],
                _canonical(body["raw_object_digests"]),
            )
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise CheckpointIntegrityError("source snapshot marker is invalid") from error
    return snapshot[0], snapshot[1], snapshot[2], _canonical(list(snapshot[3]))


def _source_snapshot_evidence(
    job_id: str, snapshot: tuple[str, str, int, str]
) -> dict[str, Any]:
    return {
        "byte_length": snapshot[2],
        "digest": snapshot[1],
        "job_id": job_id,
        "media_type": snapshot[0],
        "raw_object_digests": json.loads(snapshot[3]),
    }


def _verify_source_snapshot_rows(
    root: Path, connection: duckdb.DuckDBPyConnection
) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT job_id, media_type, digest, byte_length, raw_digests_json
        FROM source_snapshots ORDER BY job_id
        """
    ).fetchall()
    database = {
        str(job_id): (
            str(media_type),
            str(digest),
            int(byte_length),
            str(raw_digests_json),
        )
        for job_id, media_type, digest, byte_length, raw_digests_json in rows
    }
    marker_dir = root / FABRIC_NAMESPACE / "control" / "source-snapshots"
    _reject_control_reparse(root, marker_dir)
    markers: dict[str, tuple[str, str, int, str]] = {}
    if marker_dir.exists():
        for marker_path in marker_dir.iterdir():
            if marker_path.suffix != ".json" or not _is_digest(marker_path.stem):
                raise CheckpointIntegrityError(
                    "source snapshot directory is not canonical"
                )
            metadata = marker_path.lstat()
            if (
                is_reparse_point(marker_path)
                or not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
            ):
                raise CheckpointIntegrityError(
                    "source snapshot marker is not canonical"
                )
            payload = marker_path.read_bytes()
            CheckpointStore._require_journal_bytes(marker_path, payload)
            markers[marker_path.stem] = _decode_source_snapshot_marker(
                marker_path.stem, payload
            )
    if database != markers:
        raise CheckpointIntegrityError(
            "source snapshot rows disagree with immutable markers"
        )
    return {
        job_id: _source_snapshot_evidence(job_id, snapshot)
        for job_id, snapshot in markers.items()
    }


def _verify_complete_graph_state(
    root: Path,
    connection: duckdb.DuckDBPyConnection,
    evidence: _VerifiedGraph,
) -> None:
    """Compare every graph mapping and owner against the immutable journal graph."""
    history_rows = connection.execute(
        """
        SELECT dataset_id, manifest_id, compatibility_revision, commit_id,
               knowledge_start, knowledge_end
        FROM graph_history ORDER BY dataset_id, compatibility_revision
        """
    ).fetchall()
    observed_history: dict[str, list[_GraphHistoryRow]] = {}
    for (
        dataset_id,
        manifest_id,
        revision,
        commit_id,
        knowledge_start,
        knowledge_end,
    ) in history_rows:
        observed_history.setdefault(str(dataset_id), []).append(
            (
                str(manifest_id),
                int(revision),
                str(commit_id),
                str(knowledge_start),
                str(knowledge_end),
            )
        )
    if {
        dataset_id: tuple(rows) for dataset_id, rows in observed_history.items()
    } != evidence.history:
        raise CheckpointIntegrityError("commit journal disagrees with graph history")

    current_rows = connection.execute(
        """
        SELECT dataset_id, manifest_id, compatibility_revision, commit_id,
               knowledge_end
        FROM graph_currents ORDER BY dataset_id
        """
    ).fetchall()
    observed_currents = {
        str(dataset_id): (
            str(manifest_id),
            int(revision),
            str(commit_id),
            str(knowledge_end),
        )
        for dataset_id, manifest_id, revision, commit_id, knowledge_end in current_rows
    }
    expected_currents = {
        dataset_id: (rows[-1][0], rows[-1][1], rows[-1][2], rows[-1][4])
        for dataset_id, rows in evidence.history.items()
    }
    for dataset_id, expected_current in expected_currents.items():
        member = evidence.members.get(dataset_id)
        if member is None or (
            member.manifest_id,
            member.revision,
            member.knowledge_end.isoformat(),
        ) != (expected_current[0], expected_current[1], expected_current[3]):
            raise CheckpointIntegrityError(
                "graph current disagrees with its immutable member anchor"
            )
    if observed_currents != expected_currents:
        missing = sorted(set(expected_currents) - set(observed_currents))
        if missing:
            raise CheckpointIntegrityError(
                f"graph current is missing for committed dataset {missing[0]}"
            )
        raise CheckpointIntegrityError(
            "graph current disagrees with immutable commit journals"
        )

    reservations = {
        str(dataset_id): str(job_id)
        for dataset_id, job_id in connection.execute(
            "SELECT dataset_id, job_id FROM graph_reservations ORDER BY dataset_id"
        ).fetchall()
    }
    for dataset_id in sorted(evidence.owned_dataset_ids | set(reservations)):
        if not _graph_owner(root, dataset_id):
            subject = "reservation" if dataset_id in reservations else "current"
            raise CheckpointIntegrityError(
                f"graph {subject} has no ownership marker for {dataset_id}"
            )

    datasets = root / FABRIC_NAMESPACE / "datasets"
    _reject_control_reparse(root, datasets)
    if not datasets.exists():
        return
    for owner_path in datasets.glob("*/graph-owner.json"):
        dataset_id = owner_path.parent.name
        validate_dataset_name(dataset_id)
        _graph_owner(root, dataset_id)
        if (
            dataset_id not in evidence.owned_dataset_ids
            and dataset_id not in reservations
        ):
            raise CheckpointIntegrityError(
                f"graph-owned dataset {dataset_id} has no current or reservation"
            )


def reserved_job(root: Path, dataset_id: str) -> str | None:
    """Return the pending job that exclusively reserved a dataset, if any."""
    validate_dataset_name(dataset_id)
    database, lock = _control_paths(Path(root))
    if not database.exists():
        if _surviving_graph_evidence(Path(root)):
            raise CheckpointIntegrityError(
                "checkpoint database is missing below graph ownership evidence"
            )
        return None
    _reject_control_reparse(Path(root), database, lock)
    with _control_lock(lock, blocking=True), duckdb.connect(
        str(database), read_only=True
    ) as connection:
        _journal_advances(Path(root), connection)
        row = connection.execute(
            "SELECT job_id FROM graph_reservations WHERE dataset_id = ?",
            [dataset_id],
        ).fetchone()
    return None if row is None else str(row[0])


def committed_owner(root: Path, dataset_id: str) -> bool:
    """Return whether an immutable graph commit permanently owns a dataset."""
    validate_dataset_name(dataset_id)
    database, lock = _control_paths(Path(root))
    if not database.exists():
        if _surviving_graph_evidence(Path(root)):
            raise CheckpointIntegrityError(
                "checkpoint database is missing below graph ownership evidence"
            )
        return False
    _reject_control_reparse(Path(root), database, lock)
    with _control_lock(lock, blocking=True), duckdb.connect(
        str(database), read_only=True
    ) as connection:
        evidence = _journal_advances(Path(root), connection)
    return dataset_id in evidence.owned_dataset_ids


def committed_legacy_predecessor(
    root: Path, dataset_id: str
) -> tuple[str, int] | None:
    """Return the legacy high-water bound captured by the first graph advance."""
    validate_dataset_name(dataset_id)
    database, lock = _control_paths(Path(root))
    if not database.exists():
        if _surviving_graph_evidence(Path(root)):
            raise CheckpointIntegrityError(
                "checkpoint database is missing below graph ownership evidence"
            )
        return None
    _reject_control_reparse(Path(root), database, lock)
    with _control_lock(lock, blocking=True), duckdb.connect(
        str(database), read_only=True
    ) as connection:
        _journal_advances(Path(root), connection)
        rows = connection.execute(
            "SELECT body_json FROM graph_commits ORDER BY journal_sequence"
        ).fetchall()
    for (body_json,) in rows:
        body = json.loads(str(body_json))
        for item in body["advances"]:
            advance = GraphAdvance.model_validate_json(_canonical(item))
            if advance.dataset_id != dataset_id:
                continue
            if advance.expected_revision == 0:
                return None
            if advance.expected_current is None:
                raise CheckpointIntegrityError(
                    "graph migration predecessor identity is missing"
                )
            return advance.expected_current, advance.expected_revision
        for item in body["members"]:
            member = GraphMember.model_validate_json(_canonical(item))
            if member.dataset_id == dataset_id:
                return member.manifest_id, member.revision
    return None


def _control_paths(root: Path) -> tuple[Path, Path]:
    control = root / FABRIC_NAMESPACE / "control"
    return control / "collection-checkpoints.duckdb", control / "collection-writer.lock"


def _graph_owner(root: Path, dataset_id: str) -> bool:
    path = root / FABRIC_NAMESPACE / "datasets" / dataset_id / "graph-owner.json"
    _reject_control_reparse(root, path)
    if not path.exists():
        return False
    expected = _canonical(
        {"contract": "trusted-graph-owner-v1", "dataset_id": dataset_id}
    ).encode()
    CheckpointStore._require_journal_bytes(path, expected)
    return True


def _surviving_graph_evidence(root: Path) -> bool:
    control = root / FABRIC_NAMESPACE / "control"
    commits = control / "graph-commits"
    _reject_control_reparse(root, commits)
    if commits.exists() and any(commits.iterdir()):
        return True
    datasets = root / FABRIC_NAMESPACE / "datasets"
    _reject_control_reparse(root, datasets)
    return datasets.exists() and any(datasets.glob("*/graph-owner.json"))


@contextmanager
def control_writer_guard(root: Path) -> Iterator[None]:
    """Serialize legacy pointer writes with graph commits during migration."""
    database, lock = _control_paths(Path(root))
    _reject_control_reparse(Path(root), database, lock)
    with _control_lock(lock, blocking=True):
        yield


def _reject_control_reparse(root: Path, *paths: Path) -> None:
    for path in paths:
        try:
            relative = path.relative_to(root)
        except ValueError as error:
            raise ValueError(f"control path escapes trusted root: {path}") from error
        _reject_existing_reparse_chain(root)
        _reject_existing_reparse_chain(root / relative)


def _reject_existing_reparse_chain(target: Path) -> None:
    absolute = target.absolute()
    candidate = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        candidate /= part
        if candidate.exists() and is_reparse_point(candidate):
            raise ValueError(
                f"control path is a symlink or reparse point: {candidate}"
            )
