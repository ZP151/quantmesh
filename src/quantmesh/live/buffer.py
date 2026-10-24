"""Append-only replay lake for normalized live updates (ADR-0014, decision 3).

Every ``MarketUpdate`` accepted by a venue supervisor is appended here
with its provenance, so the cockpit can replay a session, backfill the
UI after a reconnect, and feed point-in-time checks — all from data
whose source and gaps are recorded, never silently reconstructed.
Retention is bounded; the table is append-only from the app's point of
view (the only deletes are the retention sweep).

Single-writer design: one workstation process owns the lake. ``local_seq``
is assigned here on append and preserved in replay order.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import threading
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
from pydantic import BaseModel, ConfigDict, Field

from quantmesh.data.objects import is_reparse_point
from quantmesh.live.contract import (
    ContinuityEvidence,
    ContinuityState,
    MarketUpdate,
    SourceState,
    UpdateKind,
)


class LiveIdentityConflictError(RuntimeError):
    """A provider identity was redelivered with different normalized content."""


class LiveCapacityExceeded(ValueError):
    """No further acquisition may be admitted; existing history remains readable."""


class _HotBudgetSpec(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    schema_version: int = Field(ge=1, le=1)
    root: str = Field(min_length=1, max_length=4096)
    ledger_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    peak_bound_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    leaf_remaining_bytes: int = Field(ge=0, le=64 * 1024 * 1024)
    global_reserved_bytes: int = Field(ge=0)
    peak_operation_bytes: int = Field(ge=4096)
    close_failure_reserve_bytes: int = Field(ge=4096)
    max_batch_bytes: int = Field(gt=0, le=65536)
    expires_at_utc: str = Field(min_length=1, max_length=64)


class HotCacheBudget:
    """Consume externally bounded operation reservations, never estimate WAL from JSON.

    The operator's existing capacity ledger must earmark global_reserved_bytes
    and establish peak_bound_sha256 for this exact runtime/batch limit, including
    startup, index/WAL/scratch/ledger overhead. Unknown bounds grant no writes.
    Failed attempts consume the full reservation; neither restart nor small
    actual writes refund it. This is admission against a trusted external bound,
    not a claim that DuckDB enforces a native maximum database file size.
    """

    def __init__(self, root: Path, record: dict) -> None:
        try:
            self.spec = _HotBudgetSpec.model_validate(record)
            self.root = Path(root).absolute()
            if (
                self.spec.root != str(self.root.resolve())
                or any(is_reparse_point(p) for p in (self.root, *self.root.parents))
                or self.spec.ledger_sha256 == "0" * 64
                or self.spec.peak_bound_sha256 == "0" * 64
            ):
                raise ValueError
            self.expires = datetime.fromisoformat(self.spec.expires_at_utc)
            if self.expires.utcoffset() != timedelta(0):
                raise ValueError
            self.limit = min(self.spec.leaf_remaining_bytes, self.spec.global_reserved_bytes)
            if self.limit < self.spec.close_failure_reserve_bytes:
                raise LiveCapacityExceeded("hot capacity exhausted")
            self._lock = threading.RLock()
            self._session: int | None = None
            self._failed = False
            self._owners = 0
            self.header = json.dumps(self.spec.model_dump(), sort_keys=True).encode()
            header_path = self.root / "budget-spec.json"
            if header_path.exists():
                if is_reparse_point(header_path) or header_path.read_bytes() != self.header:
                    raise ValueError
            else:
                if self.root.exists() and any(self.root.iterdir()):
                    raise ValueError  # No adopting an unaccounted database or resetting a ledger.
                self._headroom(
                    self.spec.peak_operation_bytes + self.spec.close_failure_reserve_bytes
                )
                self.root.mkdir(parents=True, exist_ok=True)
                self._write_once(header_path, self.header)
            self._spent()
        except LiveCapacityExceeded:
            raise
        except Exception:
            raise ValueError("hot budget unavailable or incompatible") from None

    @classmethod
    def from_file(cls, root: Path, path: Path) -> HotCacheBudget:
        if Path(path).stat().st_size > 8192:
            raise ValueError("hot budget invalid")
        return cls(root, json.loads(Path(path).read_bytes()))

    @staticmethod
    def _write_once(path: Path, raw: bytes) -> None:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if hasattr(os, "O_DIRECTORY"):
            for parent in (path.parent, path.parent.parent):
                descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)

    def _headroom(self, needed: int) -> None:
        probe = self.root
        while not probe.exists():
            probe = probe.parent
        if shutil.disk_usage(probe).free - needed < 50_000_000_000:
            raise LiveCapacityExceeded("hot capacity exhausted")

    def _spent(self) -> int:
        paths = sorted(self.root.glob("budget-intent-*.json"))
        if len(paths) > 16384:
            raise ValueError("hot budget invalid")
        for number, path in enumerate(paths, 1):
            expected = {
                "attempt": number,
                "spec_sha256": hashlib.sha256(self.header).hexdigest(),
                "reserved_bytes": self.spec.peak_operation_bytes,
            }
            if (
                path.name != f"budget-intent-{number:06d}.json"
                or is_reparse_point(path)
                or path.stat().st_size > 1024
                or path.read_bytes() != json.dumps(expected, sort_keys=True).encode()
            ):
                raise ValueError("hot budget ledger invalid")
        return len(paths) * self.spec.peak_operation_bytes

    def reserve(self, batch_bytes: int = 0) -> None:
        with self._lock:
            try:
                spent = self._check_available(batch_bytes)
                peak = self.spec.peak_operation_bytes
                number = spent // peak + 1
                self._write_once(
                    self.root / f"budget-intent-{number:06d}.json",
                    json.dumps(
                        {
                            "attempt": number,
                            "spec_sha256": hashlib.sha256(self.header).hexdigest(),
                            "reserved_bytes": peak,
                        },
                        sort_keys=True,
                    ).encode(),
                )
            except BaseException:
                self.fail_session()
                raise

    def fail_session(self) -> None:
        """Irreversible within this process; the preexisting open record survives a crash."""
        with self._lock:
            self._failed = True

    def _session_record(self, start: int, end: int | None = None) -> bytes:
        record = {"start_attempt": start, "spec_sha256": hashlib.sha256(self.header).hexdigest()}
        if end is not None:
            record["final_attempt"] = end
        return json.dumps(record, sort_keys=True).encode()

    @staticmethod
    def _exact_record(path: Path, expected: bytes) -> bool:
        return (
            path.is_file()
            and not is_reparse_point(path)
            and path.stat().st_size <= 1024
            and path.read_bytes() == expected
        )

    def start_session(self) -> None:
        """Prove prior normal closes, charge startup, fsync open marker before DuckDB I/O."""
        with self._lock:
            try:
                self._require_directory_sync()
                if self._session is not None:
                    raise ValueError("session already used")
                attempts = self._spent() // self.spec.peak_operation_bytes
                sessions = sorted(self.root.glob("budget-session-*.json"))
                if (
                    len(sessions) > 16384
                    or (attempts and not sessions)
                    or (not attempts and (self.root / "live").exists())
                ):
                    raise ValueError("session evidence missing")
                starts = [int(path.stem.removeprefix("budget-session-")) for path in sessions]
                if starts and (starts[0] != 1 or len(set(starts)) != len(starts)):
                    raise ValueError("session evidence invalid")
                closed = set(self.root.glob("budget-closed-*.json"))
                ready = set(self.root.glob("budget-close-ready-*.json"))
                if len(closed) > 16384 or len(ready) > 16384:
                    raise ValueError("session evidence invalid")
                for index, (path, start) in enumerate(zip(sessions, starts, strict=True)):
                    end = starts[index + 1] - 1 if index + 1 < len(starts) else attempts
                    receipt = self.root / f"budget-closed-{start:06d}.json"
                    prepared = self.root / f"budget-close-ready-{start:06d}.json"
                    if (
                        path.name != f"budget-session-{start:06d}.json"
                        or not 1 <= start <= end <= attempts
                        or not self._exact_record(path, self._session_record(start))
                        or not self._exact_record(receipt, self._session_record(start, end))
                        or not self._exact_record(prepared, self._session_record(start, end))
                    ):
                        raise ValueError("session not demonstrably closed")
                    closed.discard(receipt)
                    ready.discard(prepared)
                if closed or ready:
                    raise ValueError("foreign close evidence")
                self.reserve()  # Failed startup keeps its full intent, even if marker fails.
                start = attempts + 1
                self._write_once(
                    self.root / f"budget-session-{start:06d}.json", self._session_record(start)
                )
                self._session = start
            except Exception:
                self.fail_session()
                raise LiveCapacityExceeded("hot admission session unavailable") from None

    def _require_directory_sync(self) -> None:
        if not hasattr(os, "O_DIRECTORY"):
            raise LiveCapacityExceeded("durable directory sync unavailable")

    def claim_owner(self) -> None:
        with self._lock:
            if self._session is None or self._failed:
                raise LiveCapacityExceeded("hot admission session unavailable")
            self._owners += 1

    def release_owner(self, *, clean: bool) -> None:
        with self._lock:
            if not clean:
                self.fail_session()
            self._owners -= 1

    def close_session(self) -> None:
        """Called only after successful database close, after accepted work has joined."""
        with self._lock:
            if self._failed or self._owners or self._session is None:
                self.fail_session()
                return
            start = self._session
            raw = self._session_record(start, self._spent() // self.spec.peak_operation_bytes)
            try:
                # Prepare+fsync content and directories before atomic publication.
                # No fallible storage step follows publication. Lost publication
                # after a crash refuses restart; visible publication proves a true close.
                ready = self.root / f"budget-close-ready-{start:06d}.json"
                self._write_once(ready, raw)
                os.link(ready, self.root / f"budget-closed-{start:06d}.json")
            except BaseException:
                self.fail_session()
                raise

    def can_reserve(self) -> bool:
        with self._lock:
            try:
                self._check_available(0)
                return True
            except LiveCapacityExceeded:
                self.fail_session()
                return False
            except BaseException:
                self.fail_session()
                raise

    def record_stop_failure(self) -> None:
        """Keep a separate terminal failure receipt; never erase the failed stop file."""
        with self._lock:
            self.fail_session()
            path = self.root / "budget-stop-failure.json"
            if not path.exists():
                self._write_once(
                    path,
                    json.dumps(
                        {
                            "reason": "budget_stop_persistence_failed",
                            "reserved_bytes": self._spent(),
                            "spec_sha256": hashlib.sha256(self.header).hexdigest(),
                        },
                        sort_keys=True,
                    ).encode(),
                )

    def _check_available(self, batch_bytes: int) -> int:
        stop = self.root / "budget-stop.json"
        if self._failed or stop.exists() or (self.root / "budget-stop-failure.json").exists():
            self.fail_session()
            raise LiveCapacityExceeded("hot capacity exhausted")
        spent = self._spent()
        peak = self.spec.peak_operation_bytes
        if (
            datetime.now(UTC) > self.expires
            or batch_bytes > self.spec.max_batch_bytes
            or spent + peak + self.spec.close_failure_reserve_bytes > self.limit
        ):
            self.fail_session()
            self._write_once(
                stop,
                json.dumps(
                    {
                        "reason": "capacity_exhausted",
                        "reserved_bytes": spent,
                        "spec_sha256": hashlib.sha256(self.header).hexdigest(),
                    },
                    sort_keys=True,
                ).encode(),
            )
            raise LiveCapacityExceeded("hot capacity exhausted")
        try:
            self._headroom(peak + self.spec.close_failure_reserve_bytes)
        except LiveCapacityExceeded:
            self.fail_session()
            self._write_once(
                stop,
                json.dumps(
                    {
                        "reason": "capacity_exhausted",
                        "reserved_bytes": spent,
                        "spec_sha256": hashlib.sha256(self.header).hexdigest(),
                    },
                    sort_keys=True,
                ).encode(),
            )
            raise
        return spent


class AppendSequence(int):
    """Backward-compatible sequence result carrying exactly-once admission state."""

    inserted: bool

    def __new__(cls, value: int, *, inserted: bool) -> AppendSequence:
        instance = int.__new__(cls, value)
        instance.inserted = inserted
        return instance


_SCHEMA = """
CREATE TABLE IF NOT EXISTS market_updates (
    local_seq     BIGINT PRIMARY KEY,
    venue         VARCHAR NOT NULL,
    instrument    VARCHAR NOT NULL,
    kind          VARCHAR NOT NULL,
    provenance    VARCHAR NOT NULL,
    data_time     TIMESTAMPTZ NOT NULL,
    received_at   TIMESTAMPTZ NOT NULL,
    sequence      BIGINT,
    sequence_gap  BOOLEAN NOT NULL DEFAULT FALSE,
    continuity    VARCHAR,
    source_event_id VARCHAR,
    content_digest VARCHAR,
    snapshot_epoch VARCHAR,
    continuity_evidence_json VARCHAR,
    state         VARCHAR,
    state_note    VARCHAR,
    payload_json  VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS source_status (
    venue       VARCHAR NOT NULL,
    instrument  VARCHAR NOT NULL,
    state       VARCHAR NOT NULL,
    note        VARCHAR,
    changed_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (venue, instrument)
);
CREATE TABLE IF NOT EXISTS identity_quarantine (
    quarantine_id BIGINT PRIMARY KEY,
    venue VARCHAR NOT NULL,
    instrument VARCHAR NOT NULL,
    kind VARCHAR NOT NULL,
    source_event_id VARCHAR NOT NULL,
    existing_content_digest VARCHAR NOT NULL,
    conflicting_content_digest VARCHAR NOT NULL,
    observed_at TIMESTAMPTZ NOT NULL,
    conflicting_update_json VARCHAR NOT NULL
);
CREATE TABLE IF NOT EXISTS live_schema_metadata (
    component VARCHAR PRIMARY KEY,
    version INTEGER NOT NULL
);
"""

_BASE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_updates_partition
    ON market_updates (venue, instrument, kind, local_seq);
CREATE INDEX IF NOT EXISTS idx_updates_received
    ON market_updates (received_at);
"""

_IDENTITY_INDEXES = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_updates_source_identity
    ON market_updates (venue, instrument, kind, source_event_id);
CREATE INDEX IF NOT EXISTS idx_updates_source_event_lookup
    ON market_updates (source_event_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_quarantine_conflict_identity
    ON identity_quarantine
    (venue, instrument, kind, source_event_id,
     existing_content_digest, conflicting_content_digest);
"""

_RETENTION_PREDICATE = """
(kind != 'l2_snapshot' AND received_at < ?) OR
(kind = 'l2_snapshot' AND snapshot_epoch IS NULL AND received_at < ?) OR
(kind = 'l2_snapshot' AND
 (venue, instrument, snapshot_epoch) IN (
   SELECT venue, instrument, snapshot_epoch FROM market_updates
   WHERE kind = 'l2_snapshot'
   GROUP BY venue, instrument, snapshot_epoch
   HAVING MAX(received_at) < ?
 ))
"""

_UPDATE_COLUMNS = (
    "local_seq, venue, instrument, kind, provenance, data_time, received_at, "
    "sequence, sequence_gap, continuity, source_event_id, content_digest, "
    "snapshot_epoch, continuity_evidence_json, state, state_note, payload_json"
)


class LiveBuffer:
    """Append-only DuckDB lake for replayable live updates."""

    @classmethod
    def from_bounded_config(cls, root: Path, budget_file: Path) -> LiveBuffer:
        try:
            return cls.open_bounded_hot(root, HotCacheBudget.from_file(root, budget_file))
        except LiveCapacityExceeded:
            logging.getLogger(__name__).warning("Live acquisition disabled: hot capacity exhausted")
            return cls._stopped_reader(root)

    @classmethod
    def open_bounded_hot(cls, root: Path, budget: HotCacheBudget) -> LiveBuffer:
        try:
            return cls(root, retention_days=0, write_budget=budget)
        except LiveCapacityExceeded:
            # Exhausting admission must not remove previously persisted reads.
            logging.getLogger(__name__).warning("Live acquisition disabled: hot capacity exhausted")
            return cls._stopped_reader(root)

    @classmethod
    def _stopped_reader(cls, root: Path) -> LiveBuffer:
        if (Path(root) / "live/updates.duckdb").exists():
            return cls(root, read_only=True)
        # No hot was ever admitted: an empty, read-only in-memory reader carries
        # zero observations. It never creates a disk DB or stands in for archive.
        reader = cls.__new__(cls)
        reader.root = Path(root)
        reader.path = reader.root / "live/updates.duckdb"
        reader.read_only, reader.write_budget = True, None
        reader.retention = timedelta(0)
        reader._connection_lock = threading.RLock()
        reader._con = duckdb.connect(
            ":memory:",
            config={
                "max_temp_directory_size": "0B",
                "memory_limit": "128MiB",
                "threads": 1,
            },
        )
        reader._con.execute("SET TimeZone = 'UTC'")
        reader._con.execute(_SCHEMA)
        return reader

    def __init__(
        self,
        root: Path,
        retention_days: int = 7,
        *,
        read_only: bool = False,
        write_budget: HotCacheBudget | None = None,
    ) -> None:
        if retention_days < 0:
            raise ValueError("retention_days must be non-negative")
        self.root = Path(root)
        self.read_only = read_only
        self.write_budget = write_budget
        if write_budget is not None:
            if retention_days != 0 or read_only or write_budget.root != self.root.absolute():
                raise ValueError("bounded hot requires retention=0 and its exact budget root")
            write_budget.start_session()  # Durable session precedes constructor DB/index/WAL I/O.
        self.retention = timedelta(days=retention_days)
        self.path = self.root / "live" / "updates.duckdb"
        self._connection_lock = threading.RLock()
        if read_only:
            try:
                self._con = duckdb.connect(
                    str(self.path),
                    read_only=True,
                    config={
                        "max_temp_directory_size": "0B",
                        "memory_limit": "128MiB",
                        "threads": 1,
                    },
                )
                self._con.execute("SET TimeZone = 'UTC'")
                self._assert_supported_schema()
                required = set(_UPDATE_COLUMNS.split(", "))
                if not required.issubset(self._market_update_columns()):
                    raise ValueError("incompatible archive schema")
            except Exception:
                if hasattr(self, "_con"):
                    self._con.close()
                raise ValueError("archive unavailable or incompatible") from None
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._con = duckdb.connect(
            str(self.path),
            **(
                {
                    "config": {
                        "max_temp_directory_size": "0B",
                        "memory_limit": "128MiB",
                        "threads": 1,
                    }
                }
                if write_budget is not None
                else {}
            ),
        )
        # pin the session timezone so TIMESTAMPTZ rows read back as the
        # UTC instants they were written with — replay output (and its
        # ISO representations) must not depend on the host's TZ
        self._con.execute("SET TimeZone = 'UTC'")
        self._assert_supported_schema()
        self._con.execute(_SCHEMA)
        columns = self._market_update_columns()
        if {"kind", "received_at", "snapshot_epoch"}.issubset(columns):
            self._prune_before_migration()
            self._migrate_market_updates()
        else:
            # Legacy rows do not have the retention marker needed by the
            # sweep.  Migrate them first, then prune before installing the
            # identity indexes so the first cleanup is safe as well.
            self._migrate_market_updates()
            self._prune_after_migration()
        self._ensure_indexes()

    def _prune_before_migration(self) -> None:
        """Bound schema-v2 lakes before rebuilding identity indexes.

        Legacy lakes do not have the retention columns yet, so they must pass
        through the identity migration before a retention sweep is possible.
        """
        self._prune_with_indexes_disabled()

    def _prune_after_migration(self) -> None:
        """Prune a legacy lake after retention columns become available."""
        self._prune_with_indexes_disabled()

    def _market_update_columns(self) -> set[str]:
        return {
            row[1] for row in self._con.execute("PRAGMA table_info('market_updates')").fetchall()
        }

    def _prune_with_indexes_disabled(self) -> int:
        """Sweep rows while secondary indexes are detached.

        DuckDB versions used by the deployed workstation can reject a DELETE
        from a persisted indexed table.  Startup is single-writer, so detach
        every secondary index on ``market_updates`` for the short retention
        transaction, then rebuild the supported indexes even when the sweep
        raises.  The same guard is used by the running-feed cadence. The
        primary-key constraint remains database-owned.
        """
        if self.retention == timedelta(0):
            return 0
        cutoff = datetime.now(UTC) - self.retention
        parameters = [cutoff, cutoff, cutoff]
        with self._connection_lock:
            eligible = self._con.execute(
                f"SELECT COUNT(*) FROM market_updates WHERE {_RETENTION_PREDICATE}",
                parameters,
            ).fetchone()[0]
            if eligible == 0:
                return 0
            index_names = [
                row[0]
                for row in self._con.execute(
                    "SELECT index_name FROM duckdb_indexes() WHERE table_name = 'market_updates'"
                ).fetchall()
            ]
            try:
                for index_name in index_names:
                    quoted_name = '"' + index_name.replace('"', '""') + '"'
                    self._con.execute(f"DROP INDEX IF EXISTS {quoted_name}")
                self._con.execute(
                    f"DELETE FROM market_updates WHERE {_RETENTION_PREDICATE}",
                    parameters,
                )
                return eligible
            finally:
                self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Install the supported lookup and retention indexes idempotently."""
        self._con.execute(_IDENTITY_INDEXES)
        self._con.execute(_BASE_INDEXES)

    def _assert_supported_schema(self) -> None:
        """Fail closed before mutating a lake written by newer software."""
        metadata_exists = self._con.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'live_schema_metadata'"
        ).fetchone()[0]
        if not metadata_exists:
            return
        row = self._con.execute(
            "SELECT version FROM live_schema_metadata WHERE component = 'market_updates'"
        ).fetchone()
        if row is not None and row[0] > 2:
            version = row[0]
            self._con.close()
            raise RuntimeError(f"live lake schema {version} is newer than supported version 2")

    # -- writes -----------------------------------------------------------

    def append(self, update: MarketUpdate) -> int:
        """Persist one update; returns its ``local_seq``.

        Status updates also upsert the ``source_status`` table so the
        current per-source state is cheap to read. Sequence allocation,
        replay insertion and that conditional upsert commit atomically.
        Raises on any validation or storage failure without a partial row.
        """
        return self.append_many([update])[0]

    def append_many(self, updates: list[MarketUpdate]) -> list[AppendSequence]:
        try:
            return self._append_many(updates)
        except BaseException:
            if self.write_budget is not None:
                self.write_budget.fail_session()
            raise

    def _append_many(self, updates: list[MarketUpdate]) -> list[AppendSequence]:
        """Atomically admit a normalized batch, including both book sides."""
        if self.read_only:
            raise ValueError("read-only archive")
        if not updates:
            return []
        validated = [
            MarketUpdate.model_validate(update.model_dump(mode="python")) for update in updates
        ]
        self._validate_snapshot_batches(validated)
        with self._connection_lock:
            if self.write_budget is not None:
                self.write_budget.reserve(sum(len(u.model_dump_json().encode()) for u in validated))
            existing_by_key: dict[tuple[str, str, str, str], tuple[int, str]] = {}
            for update in validated:
                key = self._identity_key(update)
                existing = existing_by_key.get(key)
                if existing is None:
                    # Row equality keeps exact scope without preventing DuckDB's
                    # single-column source-ID index scan.
                    row = self._con.execute(
                        "SELECT local_seq, content_digest FROM market_updates "
                        "WHERE source_event_id = ? "
                        "AND row(venue, instrument, kind) = row(?, ?, ?)",
                        [key[3], key[0], key[1], key[2]],
                    ).fetchone()
                    if row is not None:
                        existing = (row[0], row[1])
                        existing_by_key[key] = existing
                if existing is not None and existing[1] != update.content_digest:
                    self._quarantine(update, existing[1])
                    raise LiveIdentityConflictError(
                        f"source event {update.source_event_id!r} conflicts with stored content"
                    )

            next_seq = self._con.execute(
                "SELECT COALESCE(MAX(local_seq), 0) + 1 FROM market_updates"
            ).fetchone()[0]
            receipts: list[AppendSequence] = []
            pending: list[tuple[int, MarketUpdate]] = []
            admitted_by_key = dict(existing_by_key)
            for update in validated:
                key = self._identity_key(update)
                admitted = admitted_by_key.get(key)
                if admitted is not None:
                    if admitted[1] != update.content_digest:
                        self._quarantine(update, admitted[1])
                        raise LiveIdentityConflictError(
                            f"source event {update.source_event_id!r} conflicts within batch"
                        )
                    receipts.append(AppendSequence(admitted[0], inserted=False))
                    continue
                local_seq = next_seq
                next_seq += 1
                admitted_by_key[key] = (local_seq, update.content_digest or "")
                pending.append((local_seq, update))
                receipts.append(AppendSequence(local_seq, inserted=True))

            self._con.execute("BEGIN TRANSACTION")
            try:
                for local_seq, update in pending:
                    self._insert_update(local_seq, update)
                self._con.execute("COMMIT")
            except BaseException:
                with suppress(BaseException):
                    self._con.execute("ROLLBACK")
                raise
        return receipts

    @staticmethod
    def _identity_key(update: MarketUpdate) -> tuple[str, str, str, str]:
        assert update.source_event_id is not None
        return (
            update.venue.value,
            update.instrument,
            update.kind.value,
            update.source_event_id,
        )

    @staticmethod
    def _validate_snapshot_batches(updates: list[MarketUpdate]) -> None:
        epochs: dict[tuple[str, str, str], set[str]] = {}
        for update in updates:
            if update.kind is not UpdateKind.L2_SNAPSHOT or update.venue.value != "hyperliquid":
                continue
            assert update.snapshot_epoch is not None
            key = (update.venue.value, update.instrument, update.snapshot_epoch)
            epochs.setdefault(key, set()).add(str(update.payload["side"]))
        for sides in epochs.values():
            if sides != {"bid", "ask"}:
                raise ValueError("L2 snapshot batches require atomic bid and ask sides")

    def _insert_update(self, local_seq: int, update: MarketUpdate) -> None:
        self._con.execute(
            f"INSERT INTO market_updates ({_UPDATE_COLUMNS}) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                local_seq,
                update.venue.value,
                update.instrument,
                update.kind.value,
                update.provenance.value,
                update.data_time,
                update.received_at,
                update.sequence,
                update.sequence_gap,
                update.continuity.value,
                update.source_event_id,
                update.content_digest,
                update.snapshot_epoch,
                (
                    update.continuity_evidence.model_dump_json()
                    if update.continuity_evidence is not None
                    else None
                ),
                update.state.value if update.state is not None else None,
                update.state_note,
                json.dumps(update.payload, sort_keys=True),
            ],
        )
        if update.kind is UpdateKind.STATUS:
            self._con.execute(
                "INSERT INTO source_status "
                "(venue, instrument, state, note, changed_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (venue, instrument) DO UPDATE SET "
                "state = excluded.state, note = excluded.note, "
                "changed_at = excluded.changed_at",
                [
                    update.venue.value,
                    update.instrument,
                    update.state.value if update.state is not None else None,
                    update.state_note,
                    update.received_at,
                ],
            )

    def _quarantine(self, update: MarketUpdate, existing_digest: str) -> None:
        assert update.source_event_id is not None
        assert update.content_digest is not None
        quarantined = self._con.execute(
            "SELECT quarantine_id FROM identity_quarantine "
            "WHERE venue = ? AND instrument = ? AND kind = ? "
            "AND source_event_id = ? AND existing_content_digest = ? "
            "AND conflicting_content_digest = ?",
            [*self._identity_key(update), existing_digest, update.content_digest],
        ).fetchone()
        if quarantined is not None:
            return
        quarantine_id = self._con.execute(
            "SELECT COALESCE(MAX(quarantine_id), 0) + 1 FROM identity_quarantine"
        ).fetchone()[0]
        self._con.execute(
            "INSERT INTO identity_quarantine VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                quarantine_id,
                *self._identity_key(update),
                existing_digest,
                update.content_digest,
                datetime.now(UTC),
                update.model_dump_json(),
            ],
        )

    def _migrate_market_updates(self) -> None:
        """Upgrade pre-0021 lakes without inventing provider identities."""
        columns = {
            row[1] for row in self._con.execute("PRAGMA table_info('market_updates')").fetchall()
        }
        additions = {
            "continuity": "VARCHAR",
            "source_event_id": "VARCHAR",
            "content_digest": "VARCHAR",
            "snapshot_epoch": "VARCHAR",
            "continuity_evidence_json": "VARCHAR",
        }
        self._con.execute("BEGIN TRANSACTION")
        try:
            for name, data_type in additions.items():
                if name not in columns:
                    self._con.execute(f"ALTER TABLE market_updates ADD COLUMN {name} {data_type}")
            legacy_rows = self._con.execute(
                "SELECT local_seq, venue, instrument, kind, provenance, data_time, "
                "received_at, sequence, sequence_gap, state, state_note, payload_json "
                "FROM market_updates WHERE source_event_id IS NULL "
                "OR content_digest IS NULL OR continuity IS NULL"
            ).fetchall()
            for row in legacy_rows:
                local_seq = row[0]
                snapshot_epoch = (
                    f"legacy-v1-book:{local_seq}"
                    if row[3] == UpdateKind.L2_SNAPSHOT.value
                    else None
                )
                update = MarketUpdate(
                    venue=row[1],
                    instrument=row[2],
                    kind=row[3],
                    provenance=row[4],
                    data_time=row[5],
                    received_at=row[6],
                    sequence=row[7],
                    sequence_gap=bool(row[8]),
                    state=SourceState(row[9]) if row[9] is not None else None,
                    state_note=row[10],
                    payload=json.loads(row[11]),
                    source_event_id=f"legacy-v1:{local_seq}",
                    snapshot_epoch=snapshot_epoch,
                )
                self._con.execute(
                    "UPDATE market_updates SET continuity = ?, source_event_id = ?, "
                    "content_digest = ?, snapshot_epoch = ?, "
                    "continuity_evidence_json = NULL WHERE local_seq = ?",
                    [
                        update.continuity.value,
                        update.source_event_id,
                        update.content_digest,
                        update.snapshot_epoch,
                        local_seq,
                    ],
                )
            missing = self._con.execute(
                "SELECT COUNT(*) FROM market_updates WHERE continuity IS NULL "
                "OR source_event_id IS NULL OR content_digest IS NULL"
            ).fetchone()[0]
            if missing:
                raise RuntimeError("live lake migration left incomplete identities")
            self._con.execute("COMMIT")
        except BaseException:
            with suppress(BaseException):
                self._con.execute("ROLLBACK")
            raise
        # Advance the version only after every row has an identity.  Index DDL
        # is intentionally kept out of this transaction: retention may need to
        # detach persisted indexes before deleting rows, then reinstall them
        # after migration/pruning has completed.
        self._con.execute("BEGIN TRANSACTION")
        try:
            self._con.execute(
                "INSERT INTO live_schema_metadata VALUES ('market_updates', 2) "
                "ON CONFLICT (component) DO UPDATE SET version = excluded.version"
            )
            self._con.execute("COMMIT")
        except BaseException:
            with suppress(BaseException):
                self._con.execute("ROLLBACK")
            raise

    def prune(self) -> int:
        """Safely delete updates older than the retention window.

        Returns the number of rows removed. ``retention_days=0``
        disables pruning entirely (unbounded lake). The status table is
        kept — it is small and current-state, not event data. Secondary
        indexes are detached and rebuilt around the DELETE for DuckDB builds
        that reject deleting rows from a persisted indexed table.
        """
        if self.read_only:
            raise ValueError("read-only archive")
        return self._prune_with_indexes_disabled()

    # -- reads ------------------------------------------------------------

    def price_trail(
        self, identities: list[tuple[str, str]], limit: int = 20
    ) -> dict[str, list[float]]:
        """Return trailing candle closes for exact ``(venue, instrument)`` pairs."""
        result: dict[str, list[float]] = {
            f"{venue}:{instrument}": [] for venue, instrument in identities
        }
        if not identities:
            return result
        identity_filter = " OR ".join("(venue = ? AND instrument = ?)" for _ in identities)
        params = [value for identity in identities for value in identity]
        with self._connection_lock:
            rows = self._con.execute(
                "SELECT venue, instrument, payload_json FROM market_updates "
                f"WHERE kind = 'candle' AND ({identity_filter}) "
                "QUALIFY ROW_NUMBER() OVER "
                "(PARTITION BY venue, instrument ORDER BY local_seq DESC) <= ? "
                "ORDER BY venue, instrument, local_seq",
                [*params, limit],
            ).fetchall()
        for venue, instrument, payload_json in rows:
            payload = json.loads(payload_json)
            close = payload.get("close")
            if isinstance(close, (int, float)):
                result[f"{venue}:{instrument}"].append(float(close))
        return result

    def replay(
        self,
        *,
        venue: str | None = None,
        instrument: str | None = None,
        kinds: set[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        data_time_start: datetime | None = None,
        data_time_end: datetime | None = None,
        through_local_seq: int | None = None,
        limit: int = 1000,
        tail: bool = False,
    ) -> list[MarketUpdate]:
        """Replay appended updates in ``local_seq`` order, oldest first.

        All filters are optional; ``start``/``end`` filter inclusively on
        ``received_at`` while ``data_time_start``/``data_time_end`` filter
        inclusively on market time. Time bounds must be timezone-aware.
        Every filter is applied before ordering and limiting.
        ``through_local_seq`` is the inclusive append boundary returned by
        :meth:`append`, so callers can reproduce every intermediate state
        even when several updates share the same timestamp. Corrupt or
        invalid rows raise instead of being silently skipped.
        """
        clauses: list[str] = []
        params: list[object] = []
        if venue is not None:
            clauses.append("venue = ?")
            params.append(venue)
        if instrument is not None:
            clauses.append("instrument = ?")
            params.append(instrument)
        if kinds:
            placeholders = ", ".join("?" for _ in kinds)
            clauses.append(f"kind IN ({placeholders})")
            params.extend(sorted(kinds))
        if start is not None:
            clauses.append("received_at >= ?")
            params.append(start)
        if end is not None:
            clauses.append("received_at <= ?")
            params.append(end)
        if data_time_start is not None:
            clauses.append("data_time >= ?")
            params.append(data_time_start)
        if data_time_end is not None:
            clauses.append("data_time <= ?")
            params.append(data_time_end)
        if through_local_seq is not None:
            if through_local_seq < 1:
                raise ValueError("through_local_seq must be a positive integer")
            clauses.append("local_seq <= ?")
            params.append(through_local_seq)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        if tail:
            query = (
                f"SELECT {_UPDATE_COLUMNS} FROM market_updates {where} "
                "QUALIFY ROW_NUMBER() OVER (ORDER BY local_seq DESC) <= ? "
                "ORDER BY local_seq"
            )
        else:
            query = (
                f"SELECT {_UPDATE_COLUMNS} FROM market_updates {where} ORDER BY local_seq LIMIT ?"
            )
        with self._connection_lock:
            rows = self._con.execute(query, [*params, limit]).fetchall()
        return [_row_to_update(row) for row in rows]

    def latest(
        self, *, venue: str | None = None, instrument: str | None = None
    ) -> list[MarketUpdate]:
        """The most recent update per stream, preserving both L2 sides."""
        clauses: list[str] = []
        params: list[object] = []
        if venue is not None:
            clauses.append("venue = ?")
            params.append(venue)
        if instrument is not None:
            clauses.append("instrument = ?")
            params.append(instrument)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        stream_channel = (
            "CASE WHEN kind = 'l2_snapshot' "
            "  THEN json_extract_string(payload_json, '$.side') "
            "WHEN kind = 'metrics' "
            "  THEN CASE WHEN json_extract(payload_json, '$.mid') IS NOT NULL "
            "    THEN 'allMids' ELSE 'activeAssetCtx' END "
            "ELSE '' END"
        )
        with self._connection_lock:
            # Keep only one scalar sequence per stream while scanning the lake.
            # A window over every retained row can materialize the whole lake
            # on the small staging host before it discards all but these rows.
            rows = self._con.execute(
                f"WITH latest_seq AS ("
                f"  SELECT MAX(local_seq) AS local_seq FROM market_updates {where} "
                f"  GROUP BY venue, instrument, kind, {stream_channel}"
                f") SELECT {_UPDATE_COLUMNS} FROM market_updates "
                "WHERE local_seq IN (SELECT local_seq FROM latest_seq) "
                "ORDER BY local_seq",
                params,
            ).fetchall()
        return [_row_to_update(row) for row in rows]

    def recovery_checkpoints(self, *, venue: str, instruments: list[str]) -> list[MarketUpdate]:
        """Latest durable rows used to restore a venue supervisor's cursors."""
        if not instruments:
            return []
        placeholders = ", ".join("?" for _ in instruments)
        clauses = ["venue = ?", f"instrument IN ({placeholders})"]
        params: list[object] = [venue, *instruments]
        if venue == "hyperliquid":
            clauses.append(
                "(kind != 'candle' OR ("
                "json_extract_string(payload_json, '$.final') = 'true' "
                "AND continuity IN ('complete', 'recovered')))"
            )
        where = " AND ".join(clauses)
        checkpoint_columns = ", ".join(
            f"checkpoint.{column}" for column in _UPDATE_COLUMNS.split(", ")
        )
        with self._connection_lock:
            # local_seq is unique and non-null: one complete struct wins per
            # stream, including nullable fields, without a wide historical window.
            rows = self._con.execute(
                "WITH checkpoint_rows AS ("
                "  SELECT arg_max(struct_pack("
                "    local_seq := local_seq, venue := venue, instrument := instrument, "
                "    kind := kind, provenance := provenance, data_time := data_time, "
                "    received_at := received_at, sequence := sequence, "
                "    sequence_gap := sequence_gap, continuity := continuity, "
                "    source_event_id := source_event_id, content_digest := content_digest, "
                "    snapshot_epoch := snapshot_epoch, "
                "    continuity_evidence_json := continuity_evidence_json, "
                "    state := state, state_note := state_note, payload_json := payload_json"
                "  ), local_seq) AS checkpoint "
                f"  FROM market_updates WHERE {where} "
                "  GROUP BY venue, instrument, kind, "
                "  CASE WHEN kind = 'l2_snapshot' "
                "    THEN json_extract_string(payload_json, '$.side') "
                "  WHEN kind = 'metrics' "
                "    THEN CASE WHEN json_extract(payload_json, '$.mid') IS NOT NULL "
                "      THEN 'allMids' ELSE 'activeAssetCtx' END "
                "  ELSE '' END"
                f") SELECT {checkpoint_columns} FROM checkpoint_rows "
                "ORDER BY checkpoint.local_seq",
                params,
            ).fetchall()
        return [_row_to_update(row) for row in rows]

    def statuses(self) -> list[dict[str, object]]:
        """Current per-source state rows (from status updates only)."""
        with self._connection_lock:
            rows = self._con.execute(
                "SELECT venue, instrument, state, note, changed_at "
                "FROM source_status ORDER BY venue, instrument"
            ).fetchall()
        return [
            {
                "venue": venue,
                "instrument": instrument,
                "state": state,
                "note": note,
                "changed_at": changed_at,
            }
            for venue, instrument, state, note, changed_at in rows
        ]

    def quarantined(self) -> list[dict[str, object]]:
        """Persisted identity/content conflicts, in observation order."""
        with self._connection_lock:
            rows = self._con.execute(
                "SELECT quarantine_id, venue, instrument, kind, source_event_id, "
                "existing_content_digest, conflicting_content_digest, observed_at "
                "FROM identity_quarantine ORDER BY quarantine_id"
            ).fetchall()
        keys = (
            "quarantine_id",
            "venue",
            "instrument",
            "kind",
            "source_event_id",
            "existing_content_digest",
            "conflicting_content_digest",
            "observed_at",
        )
        return [dict(zip(keys, row, strict=True)) for row in rows]

    def extent(self) -> dict[str, object]:
        """The recorded extent: earliest/latest ``received_at``, row
        count and distinct venues — the replay-window metadata (iteration
        0019 slice 4). All bounds are UTC instants."""
        with self._connection_lock:
            row = self._con.execute(
                "SELECT COUNT(*), MIN(received_at), MAX(received_at) FROM market_updates"
            ).fetchone()
            count, earliest, latest = row
            venues = self._con.execute(
                "SELECT DISTINCT venue FROM market_updates ORDER BY venue"
            ).fetchall()
        return {
            "count": count,
            "earliest": earliest.isoformat() if earliest is not None else None,
            "latest": latest.isoformat() if latest is not None else None,
            "venues": [venue for (venue,) in venues],
        }

    def close(self) -> None:
        with self._connection_lock:
            if getattr(self, "_closed", False):
                return
            try:
                self._con.close()
                self._closed = True
                if self.write_budget is not None:
                    self.write_budget.close_session()
            except BaseException:
                if self.write_budget is not None:
                    self.write_budget.fail_session()
                raise

    def __enter__(self) -> LiveBuffer:
        return self

    def __exit__(self, *exc: object) -> None:
        if exc and exc[0] is not None and self.write_budget is not None:
            self.write_budget.fail_session()
        self.close()


def _row_to_update(row: tuple[object, ...]) -> MarketUpdate:
    """Reconstruct an update from a lake row; invalid rows raise."""
    (
        local_seq,
        venue,
        instrument,
        kind,
        provenance,
        data_time,
        received_at,
        sequence,
        sequence_gap,
        continuity,
        source_event_id,
        content_digest,
        snapshot_epoch,
        continuity_evidence_json,
        state,
        state_note,
        payload_json,
    ) = row
    return MarketUpdate(
        venue=venue,
        instrument=instrument,
        kind=kind,
        provenance=provenance,
        data_time=data_time,
        received_at=received_at,
        sequence=sequence,
        sequence_gap=bool(sequence_gap),
        continuity=ContinuityState(continuity),
        source_event_id=source_event_id,
        content_digest=content_digest,
        snapshot_epoch=snapshot_epoch,
        continuity_evidence=(
            ContinuityEvidence.model_validate_json(continuity_evidence_json)
            if continuity_evidence_json is not None
            else None
        ),
        state=SourceState(state) if state is not None else None,
        state_note=state_note,
        payload=json.loads(payload_json),
    )
