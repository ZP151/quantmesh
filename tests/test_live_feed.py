"""LiveFeed unit drills (iteration 0015 Phase C): the deterministic hub.

The cache, the label derivation, the status aggregation, the lake
integration and the bounded per-client fan-out are all pure functions of
their inputs — the tests drive ``ingest``/``subscribe`` directly and
never start the pump (the browser E2E is the pump's gate).
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.domain.models import Venue
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import MarketUpdate, Provenance, SourceState, UpdateKind
from quantmesh.live.feed import LiveFeed, label
from quantmesh.live.hyperliquid import HyperliquidVenueSupervisor, ScriptedHyperliquidTransport

T0 = datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC)
LAG = timedelta(seconds=30)
STALE = timedelta(seconds=90)


def _upd(
    instrument: str = "BTC",
    kind: UpdateKind = UpdateKind.QUOTE,
    *,
    provenance: Provenance = Provenance.REAL,
    received_at: datetime = T0,
    state: SourceState | None = None,
    sequence: int | None = None,
    sequence_gap: bool = False,
    payload: dict | None = None,
) -> MarketUpdate:
    return MarketUpdate(
        venue=Venue.HYPERLIQUID,
        instrument=instrument,
        kind=kind,
        provenance=provenance,
        data_time=received_at,
        received_at=received_at,
        # STATUS updates carry no payload (contract validator); the rest
        # of the kinds default to a valid quote shape.
        payload=(
            payload
            if payload is not None
            else ({} if kind is UpdateKind.STATUS else {"bid": 100.0, "ask": 100.5})
        ),
        state=state,
        state_note="drill" if state is not None else None,
        sequence=sequence,
        sequence_gap=sequence_gap,
    )


def _feed(**kwargs) -> LiveFeed:
    return LiveFeed(lag=LAG, stale=STALE, **kwargs)


class TestLabel:
    def test_provenance_labels(self) -> None:
        fresh = T0 + timedelta(seconds=5)
        assert label(_upd(), fresh, lag=LAG) == "real"
        assert label(_upd(provenance=Provenance.DELAYED), fresh, lag=LAG) == "delayed"
        assert label(_upd(provenance=Provenance.SYNTHETIC), fresh, lag=LAG) == "synthetic"
        assert label(_upd(provenance=Provenance.UNAVAILABLE), fresh, lag=LAG) == "unavailable"

    def test_real_past_lag_is_stale(self) -> None:
        assert label(_upd(), T0 + LAG + timedelta(seconds=1), lag=LAG) == "stale"

    def test_real_within_lag_stays_fresh(self) -> None:
        assert label(_upd(), T0 + LAG - timedelta(seconds=1), lag=LAG) == "real"


class TestIngestAndCache:
    def test_ingest_caches_latest_per_kind(self) -> None:
        feed = _feed()
        feed.ingest([_upd(received_at=T0)])
        feed.ingest(
            [_upd(received_at=T0 + timedelta(seconds=1), payload={"bid": 101.0, "ask": 101.5})]
        )
        feed.ingest(
            [
                _upd(
                    kind=UpdateKind.CANDLE,
                    payload={
                        "open": 100.0,
                        "high": 100.5,
                        "low": 99.5,
                        "close": 100.25,
                        "volume": 10.0,
                    },
                )
            ]
        )
        state = feed.latest_state(now=T0 + timedelta(seconds=1))
        instruments = state["instruments"]
        assert set(instruments) == {"BTC"}
        kinds = instruments["BTC"]["kinds"]
        assert set(kinds) == {"quote", "candle"}
        assert kinds["quote"]["payload"]["bid"] == 101.0  # latest won
        assert instruments["BTC"]["label"] == "real"

    def test_distinct_instruments_coexist(self) -> None:
        feed = _feed()
        feed.ingest([_upd(), _upd(instrument="ETH")])
        assert set(feed.latest_state(now=T0)["instruments"]) == {"BTC", "ETH"}

    def test_age_ms_and_sequence_are_preserved(self) -> None:
        feed = _feed()
        feed.ingest([_upd(sequence=42, sequence_gap=True, received_at=T0)])
        state = feed.latest_state(now=T0 + timedelta(seconds=3))
        view = state["instruments"]["BTC"]["kinds"]["quote"]
        assert view["age_ms"] == 3000
        assert view["sequence"] == 42
        assert view["sequence_gap"] is True


class TestStatuses:
    def test_status_updates_group_by_venue(self) -> None:
        feed = _feed()
        feed.ingest(
            [
                _upd(kind=UpdateKind.STATUS, state=SourceState.CONNECTED),
                _upd(instrument="ETH", kind=UpdateKind.STATUS, state=SourceState.STALE),
            ]
        )
        statuses = feed.statuses(now=T0)
        venues = statuses["venues"]
        assert len(venues) == 1
        assert venues[0]["venue"] == "hyperliquid"
        assert venues[0]["connected"] is True
        states = {s["instrument"]: s["state"] for s in venues[0]["sources"]}
        assert states == {"BTC": "connected", "ETH": "stale"}

    def test_disconnected_venue_is_not_connected(self) -> None:
        feed = _feed()
        feed.ingest([_upd(kind=UpdateKind.STATUS, state=SourceState.DISCONNECTED)])
        assert feed.statuses(now=T0)["venues"][0]["connected"] is False

    def test_watchlist_instruments_default_to_unavailable(self) -> None:
        feed = _feed()
        supervisor = HyperliquidVenueSupervisor(ScriptedHyperliquidTransport([]))
        supervisor.subscribe(["BTC", "ETH"])
        feed.attach(supervisor)
        feed.ingest([_upd(kind=UpdateKind.STATUS, state=SourceState.CONNECTED)])
        statuses = feed.statuses(now=T0)
        sources = {s["instrument"]: s["state"] for s in statuses["venues"][0]["sources"]}
        assert sources == {"BTC": "connected", "ETH": "unavailable"}

    def test_data_without_status_is_not_a_status_entry(self) -> None:
        feed = _feed()
        feed.ingest([_upd()])
        assert feed.statuses(now=T0)["venues"] == []


class TestFanOut:
    def test_subscribers_receive_published_updates(self) -> None:
        feed = _feed()
        queue = feed.subscribe()
        asyncio.run(feed.publish(_upd(sequence=7)))
        assert queue.get_nowait().sequence == 7
        assert queue.qsize() == 0

    def test_overflow_drops_oldest_per_client(self) -> None:
        feed = _feed(queue_size=2)
        queue = feed.subscribe()
        async def push_all() -> None:
            for offset in range(3):
                await feed.publish(_upd(received_at=T0 + timedelta(seconds=offset)))

        asyncio.run(push_all())
        received = [queue.get_nowait() for _ in range(queue.qsize())]
        assert [u.received_at for u in received] == [
            T0 + timedelta(seconds=1),
            T0 + timedelta(seconds=2),
        ]

    def test_unsubscribe_stops_delivery(self) -> None:
        feed = _feed()
        queue = feed.subscribe()
        feed.unsubscribe(queue)
        asyncio.run(feed.publish(_upd()))
        assert queue.qsize() == 0

    def test_publish_threadsafe_ingests_even_before_the_pump(self) -> None:
        feed = _feed()
        feed.publish_threadsafe(_upd())
        assert "BTC" in feed.latest_state(now=T0)["instruments"]


class TestLake:
    def test_ingest_appends_to_the_replay_lake(self, tmp_path) -> None:
        with LiveBuffer(root=tmp_path) as lake:
            feed = _feed(lake=lake)
            feed.ingest(
                [
                    _upd(),
                    _upd(
                        kind=UpdateKind.TRADE,
                        payload={"price": 100.25, "size": 1.0, "side": "buy"},
                    ),
                ]
            )
            updates = lake.replay()
            assert [u.kind for u in updates] == [UpdateKind.QUOTE, UpdateKind.TRADE]
            assert updates[0].venue is Venue.HYPERLIQUID

    def test_status_upserts_the_source_status_table(self, tmp_path) -> None:
        with LiveBuffer(root=tmp_path) as lake:
            feed = _feed(lake=lake)
            feed.ingest([_upd(kind=UpdateKind.STATUS, state=SourceState.CONNECTED)])
            rows = lake.statuses()
            assert len(rows) == 1
            assert rows[0]["state"] == "connected"


class TestConstruction:
    def test_lag_must_precede_stale(self) -> None:
        with pytest.raises(ValueError):
            LiveFeed(lag=LAG, stale=LAG)
        with pytest.raises(ValueError):
            LiveFeed(lag=STALE, stale=LAG)
