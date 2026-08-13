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

import json
import threading
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from quantmesh.live.contract import (
    ContinuityEvidence,
    ContinuityState,
    MarketUpdate,
    SourceState,
    UpdateKind,
)


class LiveIdentityConflictError(RuntimeError):
    """A provider identity was redelivered with different normalized content."""


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
CREATE INDEX IF NOT EXISTS idx_updates_partition
    ON market_updates (venue, instrument, kind, local_seq);
CREATE INDEX IF NOT EXISTS idx_updates_received
    ON market_updates (received_at);
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

_UPDATE_COLUMNS = (
    "local_seq, venue, instrument, kind, provenance, data_time, received_at, "
    "sequence, sequence_gap, continuity, source_event_id, content_digest, "
    "snapshot_epoch, continuity_evidence_json, state, state_note, payload_json"
)


class LiveBuffer:
    """Append-only DuckDB lake for replayable live updates."""

    def __init__(self, root: Path, retention_days: int = 7) -> None:
        if retention_days < 0:
            raise ValueError("retention_days must be non-negative")
        self.root = Path(root)
        self.retention = timedelta(days=retention_days)
        self.path = self.root / "live" / "updates.duckdb"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection_lock = threading.RLock()
        self._con = duckdb.connect(str(self.path))
        # pin the session timezone so TIMESTAMPTZ rows read back as the
        # UTC instants they were written with — replay output (and its
        # ISO representations) must not depend on the host's TZ
        self._con.execute("SET TimeZone = 'UTC'")
        self._assert_supported_schema()
        self._con.execute(_SCHEMA)
        self._migrate_market_updates()

    def _assert_supported_schema(self) -> None:
        """Fail closed before mutating a lake written by newer software."""
        metadata_exists = self._con.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = 'live_schema_metadata'"
        ).fetchone()[0]
        if not metadata_exists:
            return
        row = self._con.execute(
            "SELECT version FROM live_schema_metadata "
            "WHERE component = 'market_updates'"
        ).fetchone()
        if row is not None and row[0] > 2:
            version = row[0]
            self._con.close()
            raise RuntimeError(
                f"live lake schema {version} is newer than supported version 2"
            )

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
        """Atomically admit a normalized batch, including both book sides."""
        if not updates:
            return []
        validated = [
            MarketUpdate.model_validate(update.model_dump(mode="python"))
            for update in updates
        ]
        self._validate_snapshot_batches(validated)
        with self._connection_lock:
            existing_by_key: dict[tuple[str, str, str, str], tuple[int, str]] = {}
            for update in validated:
                key = self._identity_key(update)
                existing = existing_by_key.get(key)
                if existing is None:
                    row = self._con.execute(
                        "SELECT local_seq, content_digest FROM market_updates "
                        "WHERE venue = ? AND instrument = ? AND kind = ? "
                        "AND source_event_id = ?",
                        list(key),
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
            if (
                update.kind is not UpdateKind.L2_SNAPSHOT
                or update.venue.value != "hyperliquid"
            ):
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
                    self._con.execute(
                        f"ALTER TABLE market_updates ADD COLUMN {name} {data_type}"
                    )
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
        # DuckDB cannot create an index in a transaction with outstanding row
        # updates. A second idempotent transaction installs constraints before
        # advancing the version, so interruption leaves an old version that is
        # safely retried rather than a falsely complete migration.
        self._con.execute("BEGIN TRANSACTION")
        try:
            self._con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_updates_source_identity "
                "ON market_updates "
                "(venue, instrument, kind, source_event_id)"
            )
            self._con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_quarantine_conflict_identity "
                "ON identity_quarantine "
                "(venue, instrument, kind, source_event_id, "
                "existing_content_digest, conflicting_content_digest)"
            )
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
        """Delete updates older than the retention window (bounded lake).

        Returns the number of rows removed. ``retention_days=0``
        disables pruning entirely (unbounded lake). The status table is
        kept — it is small and current-state, not event data.
        """
        if self.retention == timedelta(0):
            return 0
        cutoff = datetime.now(UTC) - self.retention
        with self._connection_lock:
            before = self._con.execute("SELECT COUNT(*) FROM market_updates").fetchone()[0]
            self._con.execute(
                "DELETE FROM market_updates WHERE "
                "(kind != 'l2_snapshot' AND received_at < ?) OR "
                "(kind = 'l2_snapshot' AND snapshot_epoch IS NULL "
                "AND received_at < ?) OR "
                "(kind = 'l2_snapshot' AND "
                "(venue, instrument, snapshot_epoch) IN ("
                "  SELECT venue, instrument, snapshot_epoch FROM market_updates "
                "  WHERE kind = 'l2_snapshot' "
                "  GROUP BY venue, instrument, snapshot_epoch "
                "  HAVING MAX(received_at) < ?"
                "))",
                [cutoff, cutoff, cutoff],
            )
            after = self._con.execute("SELECT COUNT(*) FROM market_updates").fetchone()[0]
        return before - after

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
        with self._connection_lock:
            rows = self._con.execute(
                f"SELECT {_UPDATE_COLUMNS} FROM market_updates {where} "
                "QUALIFY ROW_NUMBER() OVER ("
                "  PARTITION BY venue, instrument, kind, "
                "  CASE WHEN kind = 'l2_snapshot' "
                "    THEN json_extract_string(payload_json, '$.side') "
                "  WHEN kind = 'metrics' "
                "    THEN CASE WHEN json_extract(payload_json, '$.mid') IS NOT NULL "
                "      THEN 'allMids' ELSE 'activeAssetCtx' END "
                "  ELSE '' END "
                "  ORDER BY local_seq DESC"
                ") = 1 ORDER BY local_seq",
                params,
            ).fetchall()
        return [_row_to_update(row) for row in rows]

    def recovery_checkpoints(
        self, *, venue: str, instruments: list[str]
    ) -> list[MarketUpdate]:
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
        with self._connection_lock:
            rows = self._con.execute(
                f"SELECT {_UPDATE_COLUMNS} FROM market_updates WHERE {where} "
                "QUALIFY ROW_NUMBER() OVER ("
                "  PARTITION BY venue, instrument, kind, "
                "  CASE WHEN kind = 'l2_snapshot' "
                "    THEN json_extract_string(payload_json, '$.side') "
                "  WHEN kind = 'metrics' "
                "    THEN CASE WHEN json_extract(payload_json, '$.mid') IS NOT NULL "
                "      THEN 'allMids' ELSE 'activeAssetCtx' END "
                "  ELSE '' END "
                "  ORDER BY local_seq DESC"
                ") = 1 ORDER BY local_seq",
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
            self._con.close()

    def __enter__(self) -> LiveBuffer:
        return self

    def __exit__(self, *exc: object) -> None:
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
