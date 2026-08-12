"""LiveFeed unit drills (iteration 0015 Phase C): the deterministic hub.

The cache, the label derivation, the status aggregation, the lake
integration and the bounded per-client fan-out are all pure functions of
their inputs — the tests drive ``ingest``/``subscribe`` directly and
never start the pump (the browser E2E is the pump's gate).
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from quantmesh.domain.models import Venue
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import MarketUpdate, Provenance, SourceState, UpdateKind
from quantmesh.live.feed import LiveFeed, label
from quantmesh.live.hyperliquid import HyperliquidVenueSupervisor, ScriptedHyperliquidTransport

T0 = datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC)
LAG = timedelta(seconds=30)
STALE = timedelta(seconds=90)


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


def _upd(
    instrument: str = "BTC",
    kind: UpdateKind = UpdateKind.QUOTE,
    *,
    venue: Venue = Venue.HYPERLIQUID,
    provenance: Provenance = Provenance.REAL,
    data_time: datetime | None = None,
    received_at: datetime = T0,
    state: SourceState | None = None,
    sequence: int | None = None,
    sequence_gap: bool = False,
    payload: dict | None = None,
) -> MarketUpdate:
    return MarketUpdate(
        venue=venue,
        instrument=instrument,
        kind=kind,
        provenance=provenance,
        data_time=data_time if data_time is not None else received_at,
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


def _candle(
    *,
    venue: Venue = Venue.HYPERLIQUID,
    instrument: str = "BTC",
    data_time: datetime = T0,
    received_at: datetime | None = None,
    sequence: int | None = 100,
    sequence_gap: bool = False,
    interval: str = "1m",
) -> MarketUpdate:
    return _upd(
        venue=venue,
        instrument=instrument,
        kind=UpdateKind.CANDLE,
        data_time=data_time,
        received_at=received_at if received_at is not None else data_time,
        sequence=sequence,
        sequence_gap=sequence_gap,
        payload={
            "interval": interval,
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
        },
    )


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
    def test_exact_snapshot_is_keyed_by_venue_symbol_and_kind(self) -> None:
        feed = _feed()
        feed.ingest(
            [
                _upd(venue=Venue.HYPERLIQUID, payload={"bid": 100.0, "ask": 100.5}),
                _upd(venue=Venue.MOOMOO, payload={"bid": 200.0, "ask": 200.5}),
            ]
        )

        snapshot = feed.snapshot_exact(
            Venue.MOOMOO,
            "BTC",
            UpdateKind.QUOTE,
            as_of=T0,
        )

        assert snapshot is not None
        assert snapshot.venue is Venue.MOOMOO
        assert snapshot.instrument == "BTC"
        assert snapshot.kind is UpdateKind.QUOTE
        assert snapshot.payload["bid"] == 200.0

    def test_exact_snapshot_and_cache_are_detached_from_mutation(self) -> None:
        feed = _feed()
        update = _upd(payload={"bid": 100.0, "ask": 100.5, "levels": [[100.0, 2.0]]})
        feed.ingest([update])

        snapshot = feed.snapshot_exact(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.QUOTE,
            as_of=T0,
        )
        assert snapshot is not None
        update.payload["bid"] = 999.0
        update.payload["levels"][0][0] = 999.0

        second = feed.snapshot_exact(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.QUOTE,
            as_of=T0,
        )
        assert second is not None
        assert second.payload["bid"] == 100.0
        assert second.payload["levels"] == ((100.0, 2.0),)
        with pytest.raises(TypeError):
            snapshot.payload["bid"] = 1.0  # type: ignore[index]

    def test_latest_state_is_a_detached_snapshot(self) -> None:
        feed = _feed()
        feed.ingest([_upd(payload={"bid": 100.0, "ask": 100.5})])

        rendered = feed.latest_state(now=T0)
        rendered["instruments"]["hyperliquid:BTC"]["kinds"]["quote"]["payload"]["bid"] = 999.0
        snapshot = feed.snapshot_exact(
            Venue.HYPERLIQUID, "BTC", UpdateKind.QUOTE, as_of=T0
        )

        assert snapshot is not None
        assert snapshot.payload["bid"] == 100.0


class TestExactContinuity:
    def test_quote_proof_and_payload_are_isolated_by_venue(self) -> None:
        feed = _feed()
        for venue, bid in ((Venue.HYPERLIQUID, 100.0), (Venue.MOOMOO, 200.0)):
            feed.ingest(
                [
                    _upd(venue=venue, sequence=1, payload={"bid": bid, "ask": bid + 0.5}),
                    _upd(
                        venue=venue,
                        sequence=2,
                        received_at=T0 + timedelta(milliseconds=1),
                        payload={"bid": bid, "ask": bid + 0.5},
                    ),
                ]
            )

        hyperliquid = feed.snapshot_exact(
            Venue.HYPERLIQUID, "BTC", UpdateKind.QUOTE, as_of=T0 + timedelta(seconds=1)
        )
        moomoo = feed.snapshot_exact(
            Venue.MOOMOO, "BTC", UpdateKind.QUOTE, as_of=T0 + timedelta(seconds=1)
        )

        assert hyperliquid is not None and hyperliquid.continuity_proven is True
        assert moomoo is not None and moomoo.continuity_proven is True
        assert hyperliquid.payload["bid"] == 100.0
        assert moomoo.payload["bid"] == 200.0
        presented = feed.latest_state(now=T0 + timedelta(seconds=1))["instruments"]
        assert presented["hyperliquid:BTC"]["kinds"]["quote"]["payload"]["bid"] == 100.0
        assert presented["moomoo:BTC"]["kinds"]["quote"]["payload"]["bid"] == 200.0

    def test_first_observation_is_unproven_and_valid_second_update_is_proven(self) -> None:
        feed = _feed()
        feed.ingest([_candle(sequence=80)])
        first = feed.snapshot_exact(
            Venue.HYPERLIQUID, "BTC", UpdateKind.CANDLE, as_of=T0
        )

        assert first is not None
        assert first.continuity_proven is False
        assert first.predecessor_sequence is None
        assert first.predecessor_data_time is None

        feed.ingest(
            [
                _candle(
                    data_time=T0 + timedelta(minutes=1),
                    received_at=T0 + timedelta(minutes=1),
                    sequence=81,
                )
            ]
        )
        second = feed.snapshot_exact(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.CANDLE,
            as_of=T0 + timedelta(minutes=1),
        )

        assert second is not None
        assert second.continuity_proven is True
        assert second.predecessor_sequence == 80
        assert second.predecessor_data_time == T0

    @pytest.mark.parametrize(
        ("data_time", "sequence"),
        [
            (T0, 100),
            (T0 + timedelta(minutes=1), 101),
        ],
    )
    def test_same_bar_and_next_bar_updates_can_prove_continuity(
        self, data_time: datetime, sequence: int
    ) -> None:
        feed = _feed()
        feed.ingest([_candle(sequence=100)])
        feed.ingest(
            [
                _candle(
                    data_time=data_time,
                    received_at=T0 + timedelta(seconds=1),
                    sequence=sequence,
                )
            ]
        )

        snapshot = feed.snapshot_exact(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.CANDLE,
            as_of=T0 + timedelta(seconds=1),
        )

        assert snapshot is not None
        assert snapshot.continuity_proven is True

    def test_gap_resets_proof_until_two_clean_observations_follow(self) -> None:
        feed = _feed()
        feed.ingest([_candle(sequence=100)])
        feed.ingest(
            [
                _candle(
                    data_time=T0 + timedelta(minutes=1),
                    sequence=101,
                    sequence_gap=True,
                )
            ]
        )
        feed.ingest(
            [_candle(data_time=T0 + timedelta(minutes=2), sequence=102)]
        )
        post_gap = feed.snapshot_exact(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.CANDLE,
            as_of=T0 + timedelta(minutes=2),
        )

        assert post_gap is not None
        assert post_gap.continuity_proven is False

        feed.ingest(
            [_candle(data_time=T0 + timedelta(minutes=3), sequence=103)]
        )
        recovered = feed.snapshot_exact(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.CANDLE,
            as_of=T0 + timedelta(minutes=3),
        )
        assert recovered is not None
        assert recovered.continuity_proven is True
        assert recovered.predecessor_sequence == 102

    @pytest.mark.parametrize(
        "boundary_state",
        [SourceState.DISCONNECTED, SourceState.UNAVAILABLE],
    )
    def test_disconnect_boundary_requires_two_new_session_candles(
        self, boundary_state: SourceState
    ) -> None:
        feed = _feed()
        feed.ingest(
            [
                _candle(sequence=100),
                _candle(
                    data_time=T0 + timedelta(minutes=1),
                    received_at=T0 + timedelta(minutes=1),
                    sequence=101,
                ),
            ]
        )
        proven = feed.snapshot_exact(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.CANDLE,
            as_of=T0 + timedelta(minutes=1),
        )
        assert proven is not None and proven.continuity_proven is True

        feed.ingest(
            [
                _upd(
                    kind=UpdateKind.STATUS,
                    state=boundary_state,
                    received_at=T0 + timedelta(minutes=1, seconds=1),
                )
            ]
        )
        retained = feed.snapshot_exact(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.CANDLE,
            as_of=T0 + timedelta(minutes=1, seconds=1),
        )
        assert retained is not None
        assert retained.sequence == 101
        assert retained.continuity_proven is False

        feed.ingest(
            [
                _candle(
                    data_time=T0 + timedelta(minutes=2),
                    received_at=T0 + timedelta(minutes=2),
                    sequence=102,
                )
            ]
        )
        first = feed.snapshot_exact(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.CANDLE,
            as_of=T0 + timedelta(minutes=2),
        )
        assert first is not None and first.continuity_proven is False

        feed.ingest(
            [
                _candle(
                    data_time=T0 + timedelta(minutes=3),
                    received_at=T0 + timedelta(minutes=3),
                    sequence=103,
                )
            ]
        )
        second = feed.snapshot_exact(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.CANDLE,
            as_of=T0 + timedelta(minutes=3),
        )
        assert second is not None
        assert second.continuity_proven is True
        assert second.predecessor_sequence == 102

    @pytest.mark.parametrize(
        "state", [SourceState.CONNECTED, SourceState.LAGGING]
    )
    def test_connected_or_lagging_status_cannot_fabricate_proof(
        self, state: SourceState
    ) -> None:
        feed = _feed()
        feed.ingest([_candle(sequence=100)])
        feed.ingest(
            [
                _upd(
                    kind=UpdateKind.STATUS,
                    state=state,
                    received_at=T0 + timedelta(seconds=1),
                )
            ]
        )

        snapshot = feed.snapshot_exact(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.CANDLE,
            as_of=T0 + timedelta(seconds=1),
        )

        assert snapshot is not None
        assert snapshot.continuity_proven is False

    def test_disconnect_barrier_is_isolated_by_exact_venue_and_instrument(self) -> None:
        feed = _feed()
        for venue, instrument in (
            (Venue.HYPERLIQUID, "BTC"),
            (Venue.HYPERLIQUID, "ETH"),
            (Venue.MOOMOO, "BTC"),
        ):
            feed.ingest(
                [
                    _candle(venue=venue, instrument=instrument, sequence=100),
                    _candle(
                        venue=venue,
                        instrument=instrument,
                        data_time=T0 + timedelta(minutes=1),
                        received_at=T0 + timedelta(minutes=1),
                        sequence=101,
                    ),
                ]
            )
        feed.ingest(
            [
                _upd(
                    venue=Venue.HYPERLIQUID,
                    instrument="BTC",
                    kind=UpdateKind.STATUS,
                    state=SourceState.DISCONNECTED,
                    received_at=T0 + timedelta(minutes=1, seconds=1),
                )
            ]
        )

        proofs = {
            (venue, instrument): feed.snapshot_exact(
                venue,
                instrument,
                UpdateKind.CANDLE,
                as_of=T0 + timedelta(minutes=1, seconds=1),
            )
            for venue, instrument in (
                (Venue.HYPERLIQUID, "BTC"),
                (Venue.HYPERLIQUID, "ETH"),
                (Venue.MOOMOO, "BTC"),
            )
        }

        assert proofs[(Venue.HYPERLIQUID, "BTC")] is not None
        assert proofs[(Venue.HYPERLIQUID, "BTC")].continuity_proven is False
        assert proofs[(Venue.HYPERLIQUID, "ETH")] is not None
        assert proofs[(Venue.HYPERLIQUID, "ETH")].continuity_proven is True
        assert proofs[(Venue.MOOMOO, "BTC")] is not None
        assert proofs[(Venue.MOOMOO, "BTC")].continuity_proven is True

    def test_disconnect_before_first_candle_still_requires_a_predecessor(self) -> None:
        feed = _feed()
        feed.ingest(
            [
                _upd(
                    kind=UpdateKind.STATUS,
                    state=SourceState.DISCONNECTED,
                ),
                _candle(
                    data_time=T0 + timedelta(minutes=1),
                    received_at=T0 + timedelta(minutes=1),
                    sequence=101,
                ),
            ]
        )
        first = feed.snapshot_exact(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.CANDLE,
            as_of=T0 + timedelta(minutes=1),
        )
        assert first is not None and first.continuity_proven is False

        feed.ingest(
            [
                _candle(
                    data_time=T0 + timedelta(minutes=2),
                    received_at=T0 + timedelta(minutes=2),
                    sequence=102,
                )
            ]
        )
        second = feed.snapshot_exact(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.CANDLE,
            as_of=T0 + timedelta(minutes=2),
        )
        assert second is not None and second.continuity_proven is True

    @pytest.mark.parametrize(
        "second",
        [
            _candle(data_time=T0 + timedelta(minutes=2), sequence=101),
            _candle(data_time=T0 + timedelta(minutes=1), sequence=99),
            _candle(
                data_time=T0 + timedelta(minutes=1),
                received_at=T0 - timedelta(seconds=1),
                sequence=101,
            ),
            _candle(data_time=T0 + timedelta(minutes=1), sequence=101, interval="5m"),
        ],
    )
    def test_gap_time_sequence_and_interval_mismatches_are_unproven(
        self, second: MarketUpdate
    ) -> None:
        feed = _feed()
        feed.ingest([_candle(sequence=100)])
        feed.ingest([second])

        snapshot = feed.snapshot_exact(
            Venue.HYPERLIQUID,
            "BTC",
            UpdateKind.CANDLE,
            as_of=T0 + timedelta(minutes=2),
        )

        assert snapshot is not None
        assert snapshot.continuity_proven is False

    def test_concurrent_ingest_and_exact_reads_remain_consistent(self) -> None:
        feed = _feed()
        feed.ingest([_candle(sequence=1)])

        def write(offset: int) -> None:
            feed.ingest(
                [
                    _candle(
                        data_time=T0,
                        received_at=T0 + timedelta(milliseconds=offset),
                        sequence=offset + 1,
                    )
                ]
            )

        def read(_: int) -> tuple[Venue, str, UpdateKind, object]:
            snapshot = feed.snapshot_exact(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.CANDLE,
                as_of=T0 + timedelta(seconds=1),
            )
            assert snapshot is not None
            return snapshot.venue, snapshot.instrument, snapshot.kind, snapshot.payload["interval"]

        with ThreadPoolExecutor(max_workers=8) as pool:
            writes = [pool.submit(write, offset) for offset in range(1, 101)]
            reads = [pool.submit(read, offset) for offset in range(100)]
            for future in writes:
                future.result()
            snapshots = [future.result() for future in reads]

        assert set(snapshots) == {
            (Venue.HYPERLIQUID, "BTC", UpdateKind.CANDLE, "1m")
        }

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
        assert set(instruments) == {"hyperliquid:BTC"}
        kinds = instruments["hyperliquid:BTC"]["kinds"]
        assert set(kinds) == {"quote", "candle"}
        assert kinds["quote"]["payload"]["bid"] == 101.0  # latest won
        assert instruments["hyperliquid:BTC"]["label"] == "real"
        assert instruments["hyperliquid:BTC"]["instrument"] == "BTC"

    def test_distinct_instruments_coexist(self) -> None:
        feed = _feed()
        feed.ingest([_upd(), _upd(instrument="ETH")])
        assert set(feed.latest_state(now=T0)["instruments"]) == {
            "hyperliquid:BTC",
            "hyperliquid:ETH",
        }

    def test_age_ms_and_sequence_are_preserved(self) -> None:
        feed = _feed()
        feed.ingest([_upd(sequence=42, sequence_gap=True, received_at=T0)])
        state = feed.latest_state(now=T0 + timedelta(seconds=3))
        view = state["instruments"]["hyperliquid:BTC"]["kinds"]["quote"]
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
        assert "hyperliquid:BTC" in feed.latest_state(now=T0)["instruments"]


class TestLake:
    def test_attached_lake_ingest_is_one_serialized_exactly_once_transaction(
        self, tmp_path
    ) -> None:
        with LiveBuffer(root=tmp_path) as lake:
            feed = _feed(lake=lake)
            updates = [
                _upd(
                    sequence=offset,
                    received_at=T0 + timedelta(milliseconds=offset),
                    payload={"bid": 100.0 + offset, "ask": 100.5 + offset},
                )
                for offset in range(100)
            ]

            def publish(update: MarketUpdate) -> None:
                feed.publish_threadsafe(update)
                feed.snapshot_exact(
                    Venue.HYPERLIQUID,
                    "BTC",
                    UpdateKind.QUOTE,
                    as_of=T0 + timedelta(seconds=1),
                )
                feed.latest_state(now=T0 + timedelta(seconds=1))
                feed.statuses(now=T0 + timedelta(seconds=1))

            errors: list[BaseException] = []
            with ThreadPoolExecutor(max_workers=8) as pool:
                futures = [pool.submit(publish, update) for update in updates]
                for future in futures:
                    try:
                        future.result()
                    except BaseException as error:  # capture every worker failure
                        errors.append(error)

            assert errors == []
            replayed = lake.replay(limit=200)
            assert len(replayed) == 100
            assert sorted(update.sequence for update in replayed) == list(range(100))
            snapshot = feed.snapshot_exact(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.QUOTE,
                as_of=T0 + timedelta(seconds=1),
            )
            assert snapshot is not None
            assert snapshot.sequence == replayed[-1].sequence
            # 100 distinct rows followed by 101 proves local_seq was unique,
            # gap-free and contiguous from the lake's public append boundary.
            assert lake.append(_upd(sequence=100)) == 101

    def test_lake_append_failure_does_not_publish_unpersisted_cache_or_proof(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with LiveBuffer(root=tmp_path) as lake:
            feed = _feed(lake=lake)
            feed.ingest(
                [
                    _candle(sequence=100),
                    _candle(
                        data_time=T0 + timedelta(minutes=1),
                        received_at=T0 + timedelta(minutes=1),
                        sequence=101,
                    ),
                ]
            )
            before = feed.snapshot_exact(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.CANDLE,
                as_of=T0 + timedelta(minutes=1),
            )
            assert before is not None and before.continuity_proven is True

            def fail_append(update: MarketUpdate) -> int:
                raise RuntimeError(f"persistence failed for {update.sequence}")

            monkeypatch.setattr(lake, "append", fail_append)
            with pytest.raises(RuntimeError, match="persistence failed for 102"):
                feed.ingest(
                    [
                        _candle(
                            data_time=T0 + timedelta(minutes=2),
                            received_at=T0 + timedelta(minutes=2),
                            sequence=102,
                        )
                    ]
                )

            after = feed.snapshot_exact(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.CANDLE,
                as_of=T0 + timedelta(minutes=1),
            )
            assert after == before
            assert [row.sequence for row in lake.replay()] == [100, 101]

    def test_failed_status_transaction_preserves_cache_proof_and_session_barrier(
        self, tmp_path
    ) -> None:
        with LiveBuffer(root=tmp_path) as lake:
            feed = _feed(lake=lake)
            feed.ingest(
                [
                    _candle(sequence=100),
                    _candle(
                        data_time=T0 + timedelta(minutes=1),
                        received_at=T0 + timedelta(minutes=1),
                        sequence=101,
                    ),
                ]
            )
            before = feed.snapshot_exact(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.CANDLE,
                as_of=T0 + timedelta(minutes=1),
            )
            assert before is not None and before.continuity_proven is True

            lake._con = _FailStatusWriteOnce(lake._con)
            disconnected = _upd(
                kind=UpdateKind.STATUS,
                state=SourceState.DISCONNECTED,
                received_at=T0 + timedelta(minutes=1, seconds=1),
            )
            with pytest.raises(RuntimeError, match="injected source_status write failure"):
                feed.ingest([disconnected])

            assert feed.snapshot_exact(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.CANDLE,
                as_of=T0 + timedelta(minutes=1),
            ) == before
            assert feed.statuses(now=T0 + timedelta(minutes=1))["venues"] == []
            assert lake.replay(kinds={UpdateKind.STATUS.value}) == []
            assert lake.statuses() == []

            feed.ingest(
                [
                    _candle(
                        data_time=T0 + timedelta(minutes=2),
                        received_at=T0 + timedelta(minutes=2),
                        sequence=102,
                    )
                ]
            )
            uninterrupted = feed.snapshot_exact(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.CANDLE,
                as_of=T0 + timedelta(minutes=2),
            )
            assert uninterrupted is not None
            assert uninterrupted.continuity_proven is True

            feed.ingest([disconnected])
            assert len(lake.replay(kinds={UpdateKind.STATUS.value})) == 1
            assert len(lake.statuses()) == 1
            after_retry = feed.snapshot_exact(
                Venue.HYPERLIQUID,
                "BTC",
                UpdateKind.CANDLE,
                as_of=T0 + timedelta(minutes=2),
            )
            assert after_retry is not None
            assert after_retry.sequence == 102
            assert after_retry.continuity_proven is False

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
