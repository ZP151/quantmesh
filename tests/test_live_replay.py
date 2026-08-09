"""Replay determinism drills (0015 Phase G, ADR-0014 decision 3).

The replay lake's contract: any session appended to the lake replays
deterministically — the same updates in the same order, on any
connection, at any later time — and a point-in-time replay (``end`` on
``received_at``) reconstructs exactly the live surface the feed held as
of that moment. Nothing is silently reconstructed: provenance, venue
sequences, gap marks and the age dimension survive the round trip, so
a replayed session labels exactly as the live session did and a
backfill never resurrects old data as fresh.

Folding a replay into a fresh feed is the reconciliation truth the UI
uses after a reconnect, so the equivalence drilled here is the
reconnect/backfill path itself.
"""

from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.domain.models import Venue
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import (
    MarketUpdate,
    Provenance,
    SourceState,
    UpdateKind,
)
from quantmesh.live.feed import LiveFeed
from quantmesh.live.supervisor import BackpressureGate

_LAG = timedelta(seconds=5)
_STALE = timedelta(seconds=15)
_T0 = datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC)


def _update(
    venue: Venue,
    instrument: str,
    kind: UpdateKind,
    payload: dict,
    *,
    at: datetime = _T0,
    sequence: int | None = None,
    sequence_gap: bool = False,
    provenance: Provenance = Provenance.REAL,
    state: SourceState | None = None,
    state_note: str | None = None,
) -> MarketUpdate:
    return MarketUpdate(
        venue=venue,
        instrument=instrument,
        kind=kind,
        provenance=provenance,
        data_time=at,
        received_at=at,
        sequence=sequence,
        sequence_gap=sequence_gap,
        payload=payload,
        state=state,
        state_note=state_note,
    )


def _quote(instrument: str, bid: float, *, at: datetime, **overrides: object) -> MarketUpdate:
    return _update(
        Venue.HYPERLIQUID,
        instrument,
        UpdateKind.QUOTE,
        {"bid": bid, "ask": bid + 0.5},
        at=at,
        **overrides,
    )


def _trade(
    instrument: str, price: float, side: str, *, at: datetime, sequence: int | None = None
) -> MarketUpdate:
    return _update(
        Venue.HYPERLIQUID,
        instrument,
        UpdateKind.TRADE,
        {"price": price, "size": 1.0, "side": side},
        at=at,
        sequence=sequence,
    )


def _metrics(
    instrument: str, last: float, *, at: datetime, venue: Venue = Venue.MOOMOO
) -> MarketUpdate:
    return _update(venue, instrument, UpdateKind.METRICS, {"last": last}, at=at)


def _status(
    instrument: str,
    state: SourceState,
    *,
    at: datetime,
    venue: Venue = Venue.HYPERLIQUID,
    provenance: Provenance = Provenance.REAL,
) -> MarketUpdate:
    return _update(
        venue,
        instrument,
        UpdateKind.STATUS,
        {},
        at=at,
        provenance=provenance,
        state=state,
        state_note=f"drill {state.value}",
    )


def _feed(buffer: LiveBuffer | None = None) -> LiveFeed:
    return LiveFeed(lake=buffer, lag=_LAG, stale=_STALE)


def _instruments_view(state: dict[str, object]) -> dict[str, object]:
    """The per-instrument surface minus the wall-clock ``generated_at``."""
    return state["instruments"]


def _natural_session() -> list[list[MarketUpdate]]:
    """A multi-venue session with received_at monotone in append order:
    per-instrument quotes+trades at t+1, then a status at t+2, then the
    next round at t+8/t+9, then a status at t+10 (labels: fresh, then
    stale by t+20)."""
    t0 = _T0
    return [
        [
            _quote("BTC", 100.0, at=t0 + timedelta(seconds=1), sequence=1),
            _trade("BTC", 100.5, "buy", at=t0 + timedelta(seconds=1), sequence=2),
            _metrics("AAPL", 190.0, at=t0 + timedelta(seconds=1)),
        ],
        [
            _status("BTC", SourceState.CONNECTED, at=t0 + timedelta(seconds=2)),
            _status("AAPL", SourceState.CONNECTED, at=t0 + timedelta(seconds=2)),
        ],
        [
            _quote("BTC", 101.0, at=t0 + timedelta(seconds=8), sequence=3),
            _trade("BTC", 101.5, "sell", at=t0 + timedelta(seconds=8), sequence=4),
            _metrics("AAPL", 191.0, at=t0 + timedelta(seconds=8)),
        ],
        [
            _quote("BTC", 102.0, at=t0 + timedelta(seconds=9), sequence=5),
        ],
        [
            _status("BTC", SourceState.LAGGING, at=t0 + timedelta(seconds=10)),
            _status("AAPL", SourceState.LAGGING, at=t0 + timedelta(seconds=10)),
        ],
    ]


@pytest.fixture
def buffer(tmp_path) -> LiveBuffer:
    yield LiveBuffer(tmp_path, retention_days=7)


class TestPointInTimeReplay:
    """Replaying a session as of a cutoff reproduces the live surface
    the feed held at that moment — the backfill/reconciliation path."""

    def test_as_of_replay_reconstructs_live_surface(
        self, buffer: LiveBuffer
    ) -> None:
        feed = _feed(buffer)
        cutoffs: list[tuple[datetime, dict[str, object]]] = []
        for batch in _natural_session():
            feed.ingest(batch)
            now = batch[-1].received_at
            cutoffs.append((now, _instruments_view(feed.latest_state(now=now))))
        # every cutoff, not just the last: mid-session replay must
        # reconstruct the partial surface exactly
        for cutoff, live in cutoffs:
            replayed = buffer.replay(end=cutoff)
            rebuilt = _feed()
            rebuilt.ingest(replayed)
            assert _instruments_view(rebuilt.latest_state(now=cutoff)) == live
            assert len(replayed) >= 3  # the surface was not empty

    def test_full_replay_reconstructs_final_surface(self, buffer: LiveBuffer) -> None:
        feed = _feed(buffer)
        for batch in _natural_session():
            feed.ingest(batch)
        now = _T0 + timedelta(seconds=10)
        live = _instruments_view(feed.latest_state(now=now))
        rebuilt = _feed()
        rebuilt.ingest(buffer.replay())
        assert _instruments_view(rebuilt.latest_state(now=now)) == live
        # statuses() reconciles too: the status table is read back
        # through the same STATUS updates, so the connector-health view
        # must match the live one exactly
        assert rebuilt.statuses(now=now) == feed.statuses(now=now)

    def test_as_of_replay_excludes_future_updates(self, buffer: LiveBuffer) -> None:
        feed = _feed(buffer)
        feed.ingest([_quote("BTC", 100.0, at=_T0 + timedelta(seconds=1), sequence=1)])
        cutoff = _T0 + timedelta(seconds=1)
        feed.ingest([_quote("BTC", 101.0, at=_T0 + timedelta(seconds=9), sequence=2)])
        replayed = buffer.replay(end=cutoff)
        assert len(replayed) == 1
        assert replayed[0].payload["bid"] == 100.0
        rebuilt = _feed()
        rebuilt.ingest(replayed)
        view = _instruments_view(rebuilt.latest_state(now=cutoff))
        assert view["BTC"]["kinds"]["quote"]["sequence"] == 1
        assert "BTC" in view and view["BTC"]["label"] == "real"

    def test_append_order_not_timestamp_order_determines_replay(
        self, buffer: LiveBuffer
    ) -> None:
        """The latest per (venue, instrument, kind) is the last APPENDED,
        not the highest received_at — so a replay fold always reproduces
        the live cache even when the wire's timestamps are not monotone
        with delivery. Replay order is local_seq order, always."""
        feed = _feed(buffer)
        feed.ingest([_quote("BTC", 100.0, at=_T0 + timedelta(seconds=9), sequence=1)])
        feed.ingest([_quote("BTC", 101.0, at=_T0 + timedelta(seconds=1), sequence=2)])
        # the second append arrived first on the wire: the cache holds
        # sequence 2 (last delivered), and so must the replay fold
        now = _T0 + timedelta(seconds=10)
        live = _instruments_view(feed.latest_state(now=now))
        replayed = buffer.replay()
        assert [u.sequence for u in replayed] == [1, 2]  # local_seq order
        rebuilt = _feed()
        rebuilt.ingest(replayed)
        assert _instruments_view(rebuilt.latest_state(now=now)) == live
        assert live["BTC"]["kinds"]["quote"]["sequence"] == 2

    def test_replay_is_byte_identical_across_fresh_connections(
        self, tmp_path,
    ) -> None:
        """Closing the lake and reopening the file must replay the same
        updates — same order, same every field — and repeated replays on
        one connection must agree with each other too."""
        path = tmp_path
        first = LiveBuffer(path, retention_days=7)
        feed = _feed(first)
        for batch in _natural_session():
            feed.ingest(batch)
        expected = [u.model_dump() for u in first.replay()]
        # replayed timestamps read back UTC-pinned: the ISO
        # representation must be byte-identical to what was written,
        # whatever timezone the host session runs in
        assert all(u.data_time.isoformat().endswith("+00:00") for u in first.replay())
        first.close()

        second = LiveBuffer(path, retention_days=7)
        try:
            again = [u.model_dump() for u in second.replay()]
            assert again == expected
            assert [u.model_dump() for u in second.replay()] == expected
        finally:
            second.close()

    def test_gap_marks_survive_the_round_trip(self, buffer: LiveBuffer) -> None:
        """An overflow drop is marked on the next update of that stream by
        the backpressure gate; the mark must still be on the row the
        replay returns, and the next clean update must not inherit it."""
        gate = BackpressureGate(maxsize=2)
        assert gate.push(_quote("BTC", 100.0, at=_T0 + timedelta(seconds=1), sequence=1)) == 0
        assert gate.push(_quote("BTC", 101.0, at=_T0 + timedelta(seconds=2), sequence=2)) == 0
        # pushing the AAPL metrics overflows the bound and drops the
        # oldest pending BTC quote; the first BTC update delivered after
        # the drop (the survivor, seq 2) carries the gap mark
        assert gate.push(_metrics("AAPL", 190.0, at=_T0 + timedelta(seconds=3))) == 1
        flushed = gate.flush()
        assert [u.sequence_gap for u in flushed] == [True, False]
        assert [u.sequence for u in flushed] == [2, None]
        feed = _feed(buffer)
        feed.ingest(flushed)
        replayed = buffer.replay()
        assert [u.sequence_gap for u in replayed] == [True, False]
        assert [u.sequence for u in replayed] == [2, None]
        rebuilt = _feed()
        rebuilt.ingest(replayed)
        view = _instruments_view(rebuilt.latest_state(now=_T0 + timedelta(seconds=10)))
        assert view["BTC"]["kinds"]["quote"]["sequence_gap"] is True
        assert view["BTC"]["kinds"]["quote"]["sequence"] == 2
        assert view["AAPL"]["kinds"]["metrics"]["sequence_gap"] is False

    def test_provenance_labels_survive_the_round_trip(self, buffer: LiveBuffer) -> None:
        """real/delayed/synthetic/unavailable updates replay with the same
        provenance, and the feed labels the rebuilt surface exactly as it
        labeled the live one — the cockpit states stay distinct after a
        reconnect."""
        feed = _feed(buffer)
        t0 = _T0
        session = [
            _quote("BTC", 100.0, at=t0 + timedelta(seconds=1), sequence=1),
            _update(
                Venue.POLYMARKET,
                "YES-1",
                UpdateKind.QUOTE,
                {"bid": 0.5, "ask": 0.6},
                at=t0 + timedelta(seconds=1),
                provenance=Provenance.DELAYED,
            ),
            _update(
                Venue.KALSHI,
                "K-1",
                UpdateKind.METRICS,
                {"last": 42.0},
                at=t0 + timedelta(seconds=1),
                provenance=Provenance.SYNTHETIC,
            ),
            _status(
                "BTC",
                SourceState.DISCONNECTED,
                at=t0 + timedelta(seconds=2),
                provenance=Provenance.UNAVAILABLE,  # like the supervisor's disconnect path
            ),
        ]
        feed.ingest(session)
        now = t0 + timedelta(seconds=1)
        live = _instruments_view(feed.latest_state(now=now))
        replayed = buffer.replay()
        assert {u.provenance for u in replayed} == {
            Provenance.REAL,
            Provenance.DELAYED,
            Provenance.SYNTHETIC,
            Provenance.UNAVAILABLE,
        }
        rebuilt = _feed()
        rebuilt.ingest(replayed)
        assert _instruments_view(rebuilt.latest_state(now=now)) == live
        labels = {
            instrument: view["label"]
            for instrument, view in _instruments_view(
                rebuilt.latest_state(now=now)
            ).items()
        }
        assert labels == {"BTC": "unavailable", "YES-1": "delayed", "K-1": "synthetic"}

    def test_replay_does_not_resurrect_old_data_as_fresh(self, buffer: LiveBuffer) -> None:
        """The age dimension survives replay: a real update received long
        ago stays stale when labeled at replay time, because the label
        derives from received_at, not from when the replay happened."""
        feed = _feed(buffer)
        feed.ingest([_quote("BTC", 100.0, at=_T0 + timedelta(seconds=1), sequence=1)])
        now = _T0 + timedelta(minutes=10)  # well past both lag and stale
        live = _instruments_view(feed.latest_state(now=now))
        rebuilt = _feed()
        rebuilt.ingest(buffer.replay())
        assert _instruments_view(rebuilt.latest_state(now=now)) == live
        assert live["BTC"]["label"] == "stale"
        assert live["BTC"]["kinds"]["quote"]["label"] == "stale"
