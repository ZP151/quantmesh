"""Replay lake round-trip, filtering and retention (0015 Phase A, ADR-0014)."""

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import quantmesh.live.buffer as buffer_module
from quantmesh.domain.models import Venue
from quantmesh.live.buffer import LiveBuffer, LiveIdentityConflictError
from quantmesh.live.contract import (
    MarketUpdate,
    Provenance,
    SourceState,
    UpdateKind,
)


def _update(
    venue: Venue,
    instrument: str,
    kind: UpdateKind,
    payload: dict,
    *,
    data_time: datetime | None = None,
    received_at: datetime | None = None,
    sequence: int | None = None,
    sequence_gap: bool = False,
    provenance: Provenance = Provenance.REAL,
    state: SourceState | None = None,
    state_note: str | None = None,
    source_event_id: str | None = None,
    snapshot_epoch: str | None = None,
) -> MarketUpdate:
    return MarketUpdate(
        venue=venue,
        instrument=instrument,
        kind=kind,
        provenance=provenance,
        data_time=data_time or datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC),
        received_at=received_at or datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC),
        sequence=sequence,
        sequence_gap=sequence_gap,
        payload=payload,
        state=state,
        state_note=state_note,
        source_event_id=source_event_id,
        snapshot_epoch=snapshot_epoch,
    )


def _quote(instrument: str, bid: float = 100.0, **overrides: object) -> MarketUpdate:
    return _update(
        Venue.HYPERLIQUID,
        instrument,
        UpdateKind.QUOTE,
        {"bid": bid, "ask": bid + 0.5},
        **overrides,
    )


class _FailStatusWriteOnce:
    """DuckDB boundary proxy that fails after the replay-event insert."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._armed = True
        self.error = RuntimeError("injected source_status write failure")

    def execute(self, query: str, parameters: object = None) -> Any:
        if self._armed and query.startswith("INSERT INTO source_status"):
            self._armed = False
            raise self.error
        if parameters is None:
            return self._connection.execute(query)
        return self._connection.execute(query, parameters)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


class _PauseAfterSequenceQuery:
    """Expose a competing replay between ``execute`` and ``fetchone``."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self.sequence_query_ready = threading.Event()
        self.competing_query_finished = threading.Event()

    def execute(self, query: str, parameters: object = None) -> Any:
        if parameters is None:
            result = self._connection.execute(query)
        else:
            result = self._connection.execute(query, parameters)
        if query.startswith("SELECT COALESCE(MAX(local_seq)"):
            self.sequence_query_ready.set()
            self.competing_query_finished.wait(timeout=1)
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


class _FailSecondMarketInsertOnce:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._count = 0

    def execute(self, query: str, parameters: object = None) -> Any:
        if query.startswith("INSERT INTO market_updates"):
            self._count += 1
            if self._count == 2:
                raise RuntimeError("injected second snapshot-side failure")
        if parameters is None:
            return self._connection.execute(query)
        return self._connection.execute(query, parameters)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


@pytest.fixture
def buffer(tmp_path: Path) -> LiveBuffer:
    yield LiveBuffer(tmp_path, retention_days=7)
    # closed by the test itself where needed; GC otherwise


class TestAppendReplayRoundTrip:
    def test_redelivery_after_restart_is_a_noop(self, tmp_path: Path) -> None:
        first_update = _update(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.TRADE,
            {"price": 100.25, "size": 0.5, "side": "buy"},
            sequence=11,
            source_event_id="trade-a",
        )
        first = LiveBuffer(tmp_path)
        assert first.append(first_update) == 1
        first.close()

        reopened = LiveBuffer(tmp_path)
        redelivery = first_update.model_copy(
            update={"received_at": first_update.received_at + timedelta(seconds=10)}
        )
        try:
            assert reopened.append(redelivery) == 1
            assert reopened.replay() == [first_update]
        finally:
            reopened.close()

    def test_identity_content_conflict_is_quarantined(self, tmp_path: Path) -> None:
        lake = LiveBuffer(tmp_path)
        original = _update(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.TRADE,
            {"price": 100.25, "size": 0.5, "side": "buy"},
            source_event_id="trade-a",
        )
        conflict = _update(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.TRADE,
            {"price": 101.0, "size": 0.5, "side": "buy"},
            source_event_id="trade-a",
        )
        try:
            assert lake.append(original) == 1
            with pytest.raises(LiveIdentityConflictError, match="trade-a"):
                lake.append(conflict)
            with pytest.raises(LiveIdentityConflictError, match="trade-a"):
                lake.append(conflict)

            assert lake.replay() == [original]
            [quarantined] = lake.quarantined()
            assert quarantined["source_event_id"] == "trade-a"
            assert quarantined["existing_content_digest"] == original.content_digest
            assert quarantined["conflicting_content_digest"] == conflict.content_digest
        finally:
            lake.close()

        reopened = LiveBuffer(tmp_path)
        try:
            assert len(reopened.quarantined()) == 1
        finally:
            reopened.close()

    def test_same_source_identity_is_scoped_by_venue_instrument_and_kind(
        self, buffer: LiveBuffer
    ) -> None:
        first = _quote("BTC", source_event_id="shared")
        second = _quote("ETH", source_event_id="shared")

        assert buffer.append(first) == 1
        assert buffer.append(second) == 2

    def test_append_revalidates_digest_after_mutable_payload_change(
        self, buffer: LiveBuffer
    ) -> None:
        update = _quote("BTC", source_event_id="quote-a")
        update.payload["bid"] = 99.0

        with pytest.raises(ValidationError, match="content_digest"):
            buffer.append(update)

        assert buffer.replay() == []

    def test_two_sided_snapshot_rolls_back_atomically_on_second_insert(
        self, tmp_path: Path
    ) -> None:
        lake = LiveBuffer(tmp_path)
        bid = _update(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.L2_SNAPSHOT,
            {"side": "bid", "levels": [[99.5, 1.0]]},
        )
        ask = _update(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.L2_SNAPSHOT,
            {"side": "ask", "levels": [[100.5, 1.0]]},
            snapshot_epoch=bid.snapshot_epoch,
        )
        lake._con = _FailSecondMarketInsertOnce(lake._con)
        try:
            with pytest.raises(RuntimeError, match="second snapshot-side"):
                lake.append_many([bid, ask])
            assert lake.replay() == []
        finally:
            lake.close()

    def test_pre_0021_lake_migrates_transactionally_and_idempotently(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "live" / "updates.duckdb"
        path.parent.mkdir(parents=True)
        connection = buffer_module.duckdb.connect(str(path))
        connection.execute(
            "CREATE TABLE market_updates ("
            "local_seq BIGINT PRIMARY KEY, venue VARCHAR NOT NULL, "
            "instrument VARCHAR NOT NULL, kind VARCHAR NOT NULL, "
            "provenance VARCHAR NOT NULL, data_time TIMESTAMPTZ NOT NULL, "
            "received_at TIMESTAMPTZ NOT NULL, sequence BIGINT, "
            "sequence_gap BOOLEAN NOT NULL DEFAULT FALSE, state VARCHAR, "
            "state_note VARCHAR, payload_json VARCHAR NOT NULL)"
        )
        connection.execute(
            "INSERT INTO market_updates VALUES "
            "(7, 'hyperliquid', 'BTC', 'quote', 'real', ?, ?, 9, true, "
            "NULL, NULL, ?)",
            [
                datetime(2026, 8, 9, 10, 0, tzinfo=UTC),
                datetime(2026, 8, 9, 10, 0, tzinfo=UTC),
                json.dumps({"bid": 100.0, "ask": 100.5}),
            ],
        )
        connection.close()

        migrated = LiveBuffer(tmp_path)
        [row] = migrated.replay()
        assert row.source_event_id == "legacy-v1:7"
        assert row.continuity.value == "known-gap"
        migrated.close()

        reopened = LiveBuffer(tmp_path)
        try:
            [same] = reopened.replay()
            assert same == row
            assert reopened._con.execute(
                "SELECT version FROM live_schema_metadata "
                "WHERE component = 'market_updates'"
            ).fetchone() == (2,)
        finally:
            reopened.close()

    def test_future_schema_fails_before_mutating_the_lake(self, tmp_path: Path) -> None:
        path = tmp_path / "live" / "updates.duckdb"
        path.parent.mkdir(parents=True)
        connection = buffer_module.duckdb.connect(str(path))
        connection.execute(
            "CREATE TABLE live_schema_metadata "
            "(component VARCHAR PRIMARY KEY, version INTEGER NOT NULL)"
        )
        connection.execute("INSERT INTO live_schema_metadata VALUES ('market_updates', 99)")
        connection.close()

        with pytest.raises(RuntimeError, match="newer than supported"):
            LiveBuffer(tmp_path)

        inspected = buffer_module.duckdb.connect(str(path))
        try:
            assert inspected.execute(
                "SELECT version FROM live_schema_metadata"
            ).fetchone() == (99,)
            assert inspected.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_name = 'market_updates'"
            ).fetchone() == (0,)
        finally:
            inspected.close()

    def test_recovery_checkpoints_preserve_both_metrics_channels(
        self, buffer: LiveBuffer
    ) -> None:
        buffer.append(
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.METRICS,
                {"mid": 100.25},
                source_event_id="all-mids-1",
            )
        )
        buffer.append(
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.METRICS,
                {"funding_rate": 0.0001, "mark_price": 100.3},
                source_event_id="asset-ctx-1",
            )
        )

        rows = buffer.recovery_checkpoints(venue="hyperliquid", instruments=["BTC"])

        assert {row.source_event_id for row in rows} == {"all-mids-1", "asset-ctx-1"}

    def test_tail_limit_selects_latest_rows_but_preserves_replay_order(
        self, buffer: LiveBuffer
    ) -> None:
        for sequence in (1, 2, 3):
            buffer.append(_quote("BTC", sequence=sequence))

        rows = buffer.replay(limit=2, tail=True)

        assert [row.sequence for row in rows] == [2, 3]

    def test_append_and_replay_serialize_access_to_the_shared_connection(
        self, tmp_path: Path
    ) -> None:
        lake = LiveBuffer(tmp_path)
        paused_connection = _PauseAfterSequenceQuery(lake._con)
        lake._con = paused_connection
        failures: list[BaseException] = []

        def append() -> None:
            try:
                lake.append(_quote("BTC", sequence=1))
            except BaseException as exc:
                failures.append(exc)

        def replay() -> None:
            assert paused_connection.sequence_query_ready.wait(timeout=1)
            try:
                lake.replay()
            except BaseException as exc:
                failures.append(exc)
            finally:
                paused_connection.competing_query_finished.set()

        writer = threading.Thread(target=append)
        reader = threading.Thread(target=replay)
        try:
            writer.start()
            reader.start()
            writer.join(timeout=2)
            reader.join(timeout=2)

            assert not writer.is_alive()
            assert not reader.is_alive()
            assert failures == []
            assert lake.replay() == [_quote("BTC", sequence=1)]
        finally:
            paused_connection.competing_query_finished.set()
            writer.join(timeout=2)
            reader.join(timeout=2)
            lake.close()

    def test_status_append_is_atomic_and_retry_reuses_the_local_sequence(
        self, tmp_path: Path
    ) -> None:
        lake = LiveBuffer(tmp_path)
        failing_connection = _FailStatusWriteOnce(lake._con)
        lake._con = failing_connection
        status = _update(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.STATUS,
            {},
            state=SourceState.DISCONNECTED,
            state_note="fault drill",
        )
        try:
            with pytest.raises(
                RuntimeError, match="injected source_status write failure"
            ) as caught:
                lake.append(status)
            assert caught.value is failing_connection.error

            assert lake.replay() == []
            assert lake.statuses() == []

            assert lake.append(status) == 1
            assert lake.replay() == [status]
            assert lake.statuses() == [
                {
                    "venue": Venue.HYPERLIQUID.value,
                    "instrument": "BTC",
                    "state": SourceState.DISCONNECTED.value,
                    "note": "fault drill",
                    "changed_at": status.received_at,
                }
            ]
        finally:
            lake.close()

    def test_non_status_append_commits_for_a_reopened_long_lived_lake(
        self, tmp_path: Path
    ) -> None:
        lake = LiveBuffer(tmp_path)
        update = _quote("BTC", sequence=7)
        assert lake.append(update) == 1
        lake.close()

        reopened = LiveBuffer(tmp_path)
        try:
            assert reopened.replay() == [update]
        finally:
            reopened.close()

    def test_all_kinds_round_trip(self, buffer: LiveBuffer) -> None:
        book_bid = _update(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.L2_SNAPSHOT,
            {"side": "bid", "levels": [[99.5, 3.0], [99.0, 5.0]]},
        )
        book_ask = _update(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.L2_SNAPSHOT,
            {"side": "ask", "levels": [[100.5, 2.0], [101.0, 1.0]]},
            snapshot_epoch=book_bid.snapshot_epoch,
        )
        updates = [
            _quote("BTC"),
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.TRADE,
                {"price": 100.25, "size": 0.5, "side": "sell"},
                sequence=7,
            ),
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.CANDLE,
                {"open": 99.0, "high": 101.0, "low": 98.5, "close": 100.0, "volume": 3},
            ),
            book_bid,
            book_ask,
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.METRICS,
                {"funding_rate": 0.0001, "open_interest": 42.0},
            ),
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.STATUS,
                {},
                state=SourceState.CONNECTED,
            ),
        ]
        for update in updates[:3]:
            buffer.append(update)
        buffer.append_many([book_bid, book_ask])
        for update in updates[5:]:
            buffer.append(update)
        replayed = buffer.replay()
        assert len(replayed) == len(updates)
        for original, row in zip(updates, replayed):
            assert row.venue is original.venue
            assert row.instrument == original.instrument
            assert row.kind is original.kind
            assert row.provenance is original.provenance
            assert row.data_time == original.data_time
            assert row.sequence == original.sequence
            assert row.sequence_gap == original.sequence_gap
            assert row.payload == original.payload
            assert row.state == original.state
            assert row.state_note == original.state_note

    def test_provenance_and_gap_flags_persist(self, buffer: LiveBuffer) -> None:
        update = _quote(
            "BTC",
            provenance=Provenance.DELAYED,
            sequence_gap=True,
            received_at=datetime(2026, 8, 9, 10, 0, 5, tzinfo=UTC),
        )
        buffer.append(update)
        [row] = buffer.replay()
        assert row.provenance is Provenance.DELAYED
        assert row.sequence_gap is True

    def test_local_seq_is_monotonic_across_venues(self, buffer: LiveBuffer) -> None:
        first = _quote("BTC")
        second = _update(
            Venue.POLYMARKET,
            "trump-2028",
            UpdateKind.QUOTE,
            {"bid": 0.48, "ask": 0.52},
        )
        assert buffer.append(first) == 1
        assert buffer.append(second) == 2

    def test_constructor_pins_utc_even_when_connection_opens_non_utc(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real_connect = buffer_module.duckdb.connect

        def non_utc_connect(*args: object, **kwargs: object):
            connection = real_connect(*args, **kwargs)
            connection.execute("SET TimeZone = 'America/New_York'")
            return connection

        monkeypatch.setattr(buffer_module.duckdb, "connect", non_utc_connect)
        lake = buffer_module.LiveBuffer(tmp_path)
        try:
            lake.append(_quote("BTC"))
            [row] = lake.replay()
            assert row.received_at.isoformat().endswith("+00:00")
        finally:
            lake.close()


class TestReplayFilters:
    def _seed(self, buffer: LiveBuffer) -> None:
        for symbol in ("BTC", "ETH"):
            buffer.append(_quote(symbol))
        buffer.append(
            _update(
                Venue.POLYMARKET,
                "trump-2028",
                UpdateKind.QUOTE,
                {"bid": 0.48, "ask": 0.52},
                received_at=datetime(2026, 8, 9, 11, 0, 0, tzinfo=UTC),
            )
        )
        buffer.append(
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.TRADE,
                {"price": 100.25, "size": 0.5, "side": "buy"},
                received_at=datetime(2026, 8, 9, 11, 30, 0, tzinfo=UTC),
            )
        )

    def test_filter_by_venue(self, buffer: LiveBuffer) -> None:
        self._seed(buffer)
        rows = buffer.replay(venue=Venue.POLYMARKET.value)
        assert [r.instrument for r in rows] == ["trump-2028"]

    def test_filter_by_instrument(self, buffer: LiveBuffer) -> None:
        self._seed(buffer)
        rows = buffer.replay(instrument="ETH")
        assert [r.instrument for r in rows] == ["ETH"]

    def test_filter_by_kinds(self, buffer: LiveBuffer) -> None:
        self._seed(buffer)
        rows = buffer.replay(kinds={UpdateKind.TRADE.value})
        assert [r.kind for r in rows] == [UpdateKind.TRADE]

    def test_filter_by_time_window(self, buffer: LiveBuffer) -> None:
        self._seed(buffer)
        start = datetime(2026, 8, 9, 11, 0, 0, tzinfo=UTC)
        end = datetime(2026, 8, 9, 11, 30, 0, tzinfo=UTC)
        rows = buffer.replay(start=start, end=end)
        assert len(rows) == 2  # polymarket quote + trade at exactly 11:00/11:30

    def test_limit_applies_oldest_first(self, buffer: LiveBuffer) -> None:
        self._seed(buffer)
        rows = buffer.replay(limit=2)
        assert len(rows) == 2
        assert [r.instrument for r in rows] == ["BTC", "ETH"]

    def test_local_sequence_reconstructs_same_timestamp_cutoff(
        self, buffer: LiveBuffer
    ) -> None:
        timestamp = datetime(2026, 8, 9, 12, 0, 0, tzinfo=UTC)
        first_seq = buffer.append(_quote("BTC", bid=100.0, received_at=timestamp))
        buffer.append(_quote("BTC", bid=101.0, received_at=timestamp))

        rows = buffer.replay(through_local_seq=first_seq)

        assert len(rows) == 1
        assert rows[0].payload["bid"] == 100.0
        assert len(buffer.replay(end=timestamp)) == 2

    def test_local_sequence_cutoff_must_be_positive(self, buffer: LiveBuffer) -> None:
        with pytest.raises(ValueError, match="positive integer"):
            buffer.replay(through_local_seq=0)


class TestPriceTrailIdentity:
    def test_same_symbol_is_filtered_and_partitioned_by_venue(
        self, buffer: LiveBuffer
    ) -> None:
        for venue, closes in (
            (Venue.HYPERLIQUID, (100.0, 101.0)),
            (Venue.MOOMOO, (200.0, 201.0)),
        ):
            for sequence, close in enumerate(closes, start=1):
                buffer.append(
                    _update(
                        venue,
                        "BTC",
                        UpdateKind.CANDLE,
                        {
                            "open": close,
                            "high": close + 1,
                            "low": close - 1,
                            "close": close,
                        },
                        sequence=sequence,
                    )
                )

        trail = buffer.price_trail(
            [(Venue.HYPERLIQUID.value, "BTC")], limit=20
        )

        assert trail == {"hyperliquid:BTC": [100.0, 101.0]}


class TestLatest:
    def test_one_row_per_venue_instrument_kind(self, buffer: LiveBuffer) -> None:
        buffer.append(_quote("BTC", bid=100.0))
        buffer.append(_quote("BTC", bid=100.5))
        buffer.append(_quote("ETH", bid=2000.0))
        buffer.append(
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.TRADE,
                {"price": 100.25, "size": 0.5, "side": "buy"},
            )
        )
        latest = buffer.latest()
        by_key = {(r.venue, r.instrument, r.kind): r for r in latest}
        assert len(by_key) == 3
        assert by_key[(Venue.HYPERLIQUID, "BTC", UpdateKind.QUOTE)].payload["bid"] == 100.5
        assert by_key[(Venue.HYPERLIQUID, "ETH", UpdateKind.QUOTE)].payload["bid"] == 2000.0
        assert by_key[(Venue.HYPERLIQUID, "BTC", UpdateKind.TRADE)].payload["price"] == 100.25

    def test_latest_scope_filters(self, buffer: LiveBuffer) -> None:
        buffer.append(_quote("BTC"))
        buffer.append(
            _update(
                Venue.POLYMARKET,
                "trump-2028",
                UpdateKind.QUOTE,
                {"bid": 0.48, "ask": 0.52},
            )
        )
        rows = buffer.latest(venue=Venue.POLYMARKET.value)
        assert len(rows) == 1
        assert rows[0].instrument == "trump-2028"


class TestStatusUpsert:
    def test_last_status_wins_per_source(self, buffer: LiveBuffer) -> None:
        buffer.append(
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.STATUS,
                {},
                state=SourceState.CONNECTED,
                received_at=datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC),
            )
        )
        buffer.append(
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.STATUS,
                {},
                state=SourceState.STALE,
                state_note="no frames for 90s",
                received_at=datetime(2026, 8, 9, 10, 5, 0, tzinfo=UTC),
            )
        )
        statuses = buffer.statuses()
        assert len(statuses) == 1
        assert statuses[0]["state"] == SourceState.STALE.value
        assert statuses[0]["note"] == "no frames for 90s"

    def test_status_rows_are_separate_per_source(self, buffer: LiveBuffer) -> None:
        buffer.append(
            _update(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.STATUS,
                {},
                state=SourceState.CONNECTED,
            )
        )
        buffer.append(
            _update(
                Venue.POLYMARKET,
                "trump-2028",
                UpdateKind.STATUS,
                {},
                state=SourceState.UNAVAILABLE,
            )
        )
        assert len(buffer.statuses()) == 2


class TestRetention:
    def test_old_rows_pruned_fresh_kept(self, tmp_path: Path) -> None:
        past = datetime.now(UTC) - timedelta(days=10)
        buffer = LiveBuffer(tmp_path, retention_days=1)
        try:
            buffer.append(_quote("BTC", received_at=past))
            buffer.append(_quote("ETH", received_at=datetime.now(UTC)))
            assert buffer.prune() == 1
            rows = buffer.replay()
            assert [r.instrument for r in rows] == ["ETH"]
        finally:
            buffer.close()

    def test_zero_retention_disables_pruning(self, tmp_path: Path) -> None:
        past = datetime.now(UTC) - timedelta(days=10)
        buffer = LiveBuffer(tmp_path, retention_days=0)
        try:
            buffer.append(_quote("BTC", received_at=past))
            assert buffer.prune() == 0
            assert len(buffer.replay()) == 1
        finally:
            buffer.close()

    def test_prune_never_splits_one_l2_snapshot_epoch(self, tmp_path: Path) -> None:
        old = datetime.now(UTC) - timedelta(days=2)
        fresh = datetime.now(UTC)
        bid = _update(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.L2_SNAPSHOT,
            {"side": "bid", "levels": [[100.0, 1.0]]},
            received_at=old,
            source_event_id="epoch-1:bid",
            snapshot_epoch="epoch-1",
        )
        ask = _update(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.L2_SNAPSHOT,
            {"side": "ask", "levels": [[100.5, 1.0]]},
            received_at=fresh,
            source_event_id="epoch-1:ask",
            snapshot_epoch="epoch-1",
        )
        buffer = LiveBuffer(tmp_path, retention_days=1)
        try:
            buffer.append_many([bid, ask])
            assert buffer.prune() == 0
            assert {row.payload["side"] for row in buffer.replay()} == {"bid", "ask"}
        finally:
            buffer.close()


class TestFailClosed:
    def test_corrupt_payload_raises_on_replay(self, tmp_path: Path) -> None:
        buffer = LiveBuffer(tmp_path)
        try:
            buffer.append(_quote("BTC"))
            buffer._con.execute(
                "UPDATE market_updates SET payload_json = ? WHERE instrument = 'BTC'",
                ["{not json"],
            )
            with pytest.raises(Exception):
                buffer.replay()
        finally:
            buffer.close()

    def test_invalid_payload_never_enters_lake(self, tmp_path: Path) -> None:
        buffer = LiveBuffer(tmp_path)
        try:
            with pytest.raises(ValidationError):
                buffer.append(
                    _update(
                        Venue.HYPERLIQUID,
                        "BTC",
                        UpdateKind.QUOTE,
                        {"bid": 101.0, "ask": 100.0},  # ask below bid
                    )
                )
            assert buffer.replay() == []
        finally:
            buffer.close()

    def test_replay_rejects_unknown_kind_row(self, tmp_path: Path) -> None:
        buffer = LiveBuffer(tmp_path)
        try:
            buffer.append(_quote("BTC"))
            buffer._con.execute("UPDATE market_updates SET kind = 'orderbook'")
            with pytest.raises(ValidationError):
                buffer.replay()
        finally:
            buffer.close()

    def test_json_round_trip_of_payload_shape(self, buffer: LiveBuffer) -> None:
        payload = {"levels": [[99.5, 3.0], [99.0, 5.0]], "side": "bid"}
        bid = _update(Venue.HYPERLIQUID, "BTC", UpdateKind.L2_SNAPSHOT, payload)
        ask = _update(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.L2_SNAPSHOT,
            {"levels": [[100.5, 1.0]], "side": "ask"},
            snapshot_epoch=bid.snapshot_epoch,
        )
        buffer.append_many([bid, ask])
        rows = buffer.replay()
        assert rows[0].payload == payload
        # stored form is stable JSON text, ready for Parquet-style reads
        stored = buffer._con.execute(
            "SELECT payload_json FROM market_updates ORDER BY local_seq LIMIT 1"
        ).fetchone()[0]
        assert json.loads(stored) == payload

    def test_hyperliquid_book_cannot_persist_only_one_side(
        self, buffer: LiveBuffer
    ) -> None:
        bid = _update(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.L2_SNAPSHOT,
            {"levels": [[99.5, 3.0]], "side": "bid"},
        )

        with pytest.raises(ValueError, match="atomic bid and ask"):
            buffer.append(bid)

        assert buffer.replay() == []
