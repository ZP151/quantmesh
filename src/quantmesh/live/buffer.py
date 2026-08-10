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
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb

from quantmesh.live.contract import MarketUpdate, SourceState, UpdateKind

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
"""

_UPDATE_COLUMNS = (
    "local_seq, venue, instrument, kind, provenance, data_time, received_at, "
    "sequence, sequence_gap, state, state_note, payload_json"
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
        self._con = duckdb.connect(str(self.path))
        # pin the session timezone so TIMESTAMPTZ rows read back as the
        # UTC instants they were written with — replay output (and its
        # ISO representations) must not depend on the host's TZ
        self._con.execute("SET TimeZone = 'UTC'")
        self._con.execute(_SCHEMA)

    # -- writes -----------------------------------------------------------

    def append(self, update: MarketUpdate) -> int:
        """Persist one update; returns its ``local_seq``.

        Status updates also upsert the ``source_status`` table so the
        current per-source state is cheap to read. Raises on any
        validation failure — nothing invalid ever enters the lake.
        """
        local_seq = self._con.execute(
            "SELECT COALESCE(MAX(local_seq), 0) + 1 FROM market_updates"
        ).fetchone()[0]
        self._con.execute(
            f"INSERT INTO market_updates ({_UPDATE_COLUMNS}) VALUES "
            "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                update.state.value if update.state is not None else None,
                update.state_note,
                json.dumps(update.payload, sort_keys=True),
            ],
        )
        if update.kind is UpdateKind.STATUS:
            self._con.execute(
                "INSERT INTO source_status (venue, instrument, state, note, changed_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT (venue, instrument) DO UPDATE SET "
                "state = excluded.state, note = excluded.note, changed_at = excluded.changed_at",
                [
                    update.venue.value,
                    update.instrument,
                    update.state.value if update.state is not None else None,
                    update.state_note,
                    update.received_at,
                ],
            )
        return local_seq

    def prune(self) -> int:
        """Delete updates older than the retention window (bounded lake).

        Returns the number of rows removed. ``retention_days=0``
        disables pruning entirely (unbounded lake). The status table is
        kept — it is small and current-state, not event data.
        """
        if self.retention == timedelta(0):
            return 0
        cutoff = datetime.now(UTC) - self.retention
        before = self._con.execute("SELECT COUNT(*) FROM market_updates").fetchone()[0]
        self._con.execute("DELETE FROM market_updates WHERE received_at < ?", [cutoff])
        after = self._con.execute("SELECT COUNT(*) FROM market_updates").fetchone()[0]
        return before - after

    # -- reads ------------------------------------------------------------

    def price_trail(
        self, symbols: list[str], limit: int = 20
    ) -> dict[str, list[float]]:
        result: dict[str, list[float]] = {s: [] for s in symbols}
        if not symbols:
            return result
        placeholders = ", ".join("?" for _ in symbols)
        rows = self._con.execute(
            f"SELECT instrument, payload_json FROM market_updates "
            f"WHERE kind = 'candle' AND instrument IN ({placeholders}) "
            f"QUALIFY ROW_NUMBER() OVER (PARTITION BY instrument ORDER BY local_seq DESC) <= ? "
            f"ORDER BY instrument, local_seq",
            [*symbols, limit],
        ).fetchall()
        for instrument, payload_json in rows:
            payload = json.loads(payload_json)
            close = payload.get("close")
            if isinstance(close, (int, float)):
                result[instrument].append(float(close))
        return result

    def replay(
        self,
        *,
        venue: str | None = None,
        instrument: str | None = None,
        kinds: set[str] | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        through_local_seq: int | None = None,
        limit: int = 1000,
    ) -> list[MarketUpdate]:
        """Replay appended updates in ``local_seq`` order, oldest first.

        All filters are optional; ``start``/``end`` filter inclusively on
        ``received_at`` and must be timezone-aware. ``through_local_seq``
        is the inclusive append boundary returned by :meth:`append`, so
        callers can reproduce every intermediate state even when several
        updates share the same timestamp. Corrupt or invalid rows raise
        instead of being silently skipped.
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
        if through_local_seq is not None:
            if through_local_seq < 1:
                raise ValueError("through_local_seq must be a positive integer")
            clauses.append("local_seq <= ?")
            params.append(through_local_seq)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._con.execute(
            f"SELECT {_UPDATE_COLUMNS} FROM market_updates {where} "
            "ORDER BY local_seq LIMIT ?",
            [*params, limit],
        ).fetchall()
        return [_row_to_update(row) for row in rows]

    def latest(
        self, *, venue: str | None = None, instrument: str | None = None
    ) -> list[MarketUpdate]:
        """The most recent update per (venue, instrument, kind)."""
        clauses: list[str] = []
        params: list[object] = []
        if venue is not None:
            clauses.append("venue = ?")
            params.append(venue)
        if instrument is not None:
            clauses.append("instrument = ?")
            params.append(instrument)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._con.execute(
            f"SELECT {_UPDATE_COLUMNS} FROM market_updates {where} "
            "QUALIFY ROW_NUMBER() OVER ("
            "  PARTITION BY venue, instrument, kind ORDER BY local_seq DESC"
            ") = 1",
            params,
        ).fetchall()
        return [_row_to_update(row) for row in rows]

    def statuses(self) -> list[dict[str, object]]:
        """Current per-source state rows (from status updates only)."""
        rows = self._con.execute(
            "SELECT venue, instrument, state, note, changed_at FROM source_status "
            "ORDER BY venue, instrument"
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

    def extent(self) -> dict[str, object]:
        """The recorded extent: earliest/latest ``received_at``, row
        count and distinct venues — the replay-window metadata (iteration
        0019 slice 4). All bounds are UTC instants."""
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
        state=SourceState(state) if state is not None else None,
        state_note=state_note,
        payload=json.loads(payload_json),
    )
