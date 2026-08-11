"""Venue supervisor protocol + Hyperliquid supervisor drills (0015 Phase B).

Fixture-first: the M5 discipline carried over — every transition takes
an explicit clock, every wire is a scripted transport, and the live
pump is never exercised against the network (the Phase G live smoke
drill is its gate).
"""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from quantmesh.domain.models import Venue
from quantmesh.hyperliquid.errors import HyperliquidProtocolError
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.contract import MarketUpdate, Provenance, SourceState, UpdateKind
from quantmesh.live.hyperliquid import (
    HyperliquidVenueSupervisor,
    ScriptedHyperliquidTransport,
)
from quantmesh.live.supervisor import (
    BackpressureGate,
    GapFinding,
    SourceStatusTracker,
    next_backoff,
)

T0 = datetime(2026, 8, 9, 10, 0, 0, tzinfo=UTC)
LAG = timedelta(seconds=30)
STALE = timedelta(seconds=90)


def _bbo(
    coin: str, bid: float = 100.0, ask: float = 100.5, time_ms: int = 1_750_000_000_000
) -> dict:
    return {
        "channel": "bbo",
        "data": {
            "coin": coin,
            "time": time_ms,
            "bid": bid,
            "bidSz": 1.0,
            "ask": ask,
            "askSz": 2.0,
        },
    }


def _candle(coin: str, open_: float, close: float, t: int) -> dict:
    return {
        "channel": "candle",
        "data": {
            "t": t,
            "T": t + 60_000,
            "s": coin,
            "i": "1m",
            "o": open_,
            "c": close,
            "h": max(open_, close),
            "l": min(open_, close),
            "v": 1.0,
            "n": 1,
        },
    }


def _trade(coin: str, tid: int, px: float = 100.25, side: str = "A") -> dict:
    return {
        "channel": "trades",
        "data": [
            {"coin": coin, "tid": tid, "px": px, "sz": 0.5, "side": side, "time": 1_750_000_000_000}
        ],
    }


def _l2(coin: str) -> dict:
    return {
        "channel": "l2Book",
        "data": {
            "coin": coin,
            "time": 1_750_000_000_000,
            "levels": [
                [{"px": "100.0", "sz": "1.0", "n": 1}, {"px": "99.5", "sz": "2.0", "n": 1}],
                [{"px": "100.5", "sz": "0.5", "n": 1}],
            ],
            "type": "book",
        },
    }


def _mids() -> dict:
    return {"channel": "allMids", "data": {"mids": {"BTC": 100.25}}}


def _asset_ctx() -> dict:
    ctx = {"funding": 1.25e-05, "markPx": 100.3, "oraclePx": 100.1, "openInterest": 123.4}
    return {"channel": "activeAssetCtx", "data": {"BTC": ctx}}


def _setup(
    script: list[object] | None = None, **kwargs
) -> tuple[HyperliquidVenueSupervisor, ScriptedHyperliquidTransport]:
    transport = ScriptedHyperliquidTransport(script or [])
    supervisor = HyperliquidVenueSupervisor(transport, **kwargs)
    supervisor.subscribe(["BTC"])
    return supervisor, transport


class TestNextBackoff:
    def test_exponential_and_capped(self) -> None:
        assert next_backoff(0) == 1.0
        assert next_backoff(1) == 2.0
        assert next_backoff(2) == 4.0
        assert next_backoff(10) == 30.0  # capped

    def test_negative_attempt_rejected(self) -> None:
        with pytest.raises(ValueError):
            next_backoff(-1)


class TestSourceStatusTracker:
    def test_connected_then_lagging_then_stale(self) -> None:
        tracker = SourceStatusTracker(LAG, STALE)
        tracker.note_activity("BTC", T0)
        assert (
            tracker.evaluate("BTC", T0 + timedelta(seconds=10), connected=True)
            is SourceState.CONNECTED
        )
        assert (
            tracker.evaluate("BTC", T0 + timedelta(seconds=31), connected=True)
            is SourceState.LAGGING
        )
        assert (
            tracker.evaluate("BTC", T0 + timedelta(seconds=91), connected=True)
            is SourceState.STALE
        )

    def test_never_seen_is_unavailable_then_disconnected(self) -> None:
        tracker = SourceStatusTracker(LAG, STALE)
        assert tracker.evaluate("BTC", T0, connected=False) is SourceState.UNAVAILABLE
        tracker.note_activity("BTC", T0)
        assert (
            tracker.evaluate("BTC", T0 + timedelta(seconds=5), connected=False)
            is SourceState.DISCONNECTED
        )

    def test_freshly_opened_connected_source_is_connected(self) -> None:
        tracker = SourceStatusTracker(LAG, STALE)
        assert tracker.evaluate("BTC", T0, connected=True) is SourceState.CONNECTED

    def test_transitions_only_on_change(self) -> None:
        tracker = SourceStatusTracker(LAG, STALE)
        tracker.note_activity("BTC", T0)
        first = tracker.transitions(["BTC"], T0, connected=True)
        assert [state for _, state, _ in first] == [SourceState.CONNECTED]
        second = tracker.transitions(["BTC"], T0 + timedelta(seconds=5), connected=True)
        assert second == []  # still connected: no new transition

    def test_bad_thresholds_rejected(self) -> None:
        with pytest.raises(ValueError):
            SourceStatusTracker(timedelta(0), STALE)
        with pytest.raises(ValueError):
            SourceStatusTracker(STALE, LAG)


class TestBackpressureGate:
    def _quote(self, seq: int, instrument: str = "BTC") -> MarketUpdate:
        return MarketUpdate(
            venue=Venue.HYPERLIQUID,
            instrument=instrument,
            kind=UpdateKind.QUOTE,
            provenance=Provenance.REAL,
            data_time=T0,
            sequence=seq,
            payload={"bid": 100.0, "ask": 100.5},
        )

    def test_stages_until_flush(self) -> None:
        gate = BackpressureGate(maxsize=4)
        assert gate.push(self._quote(1)) == 0
        assert gate.push(self._quote(2)) == 0
        assert gate.push(self._quote(3)) == 0
        assert [u.sequence for u in gate.flush()] == [1, 2, 3]

    def test_drop_oldest_marks_next_update_as_gap(self) -> None:
        gate = BackpressureGate(maxsize=2)
        gate.push(self._quote(1))
        gate.push(self._quote(2))
        dropped = gate.push(self._quote(3))
        assert dropped == 1  # update 1 dropped
        emitted = gate.flush()
        assert [u.sequence for u in emitted] == [2, 3]
        assert emitted[0].sequence_gap is False
        assert emitted[1].sequence_gap is True  # explicit gap marking

    def test_gap_marking_is_per_stream(self) -> None:
        gate = BackpressureGate(maxsize=1)
        assert gate.push(self._quote(1, instrument="BTC")) == 0
        assert gate.push(self._quote(2, instrument="ETH")) == 1  # drops the BTC quote
        [eth] = gate.flush()
        assert eth.sequence_gap is False  # ETH was not dropped: stays clean
        # the dropped BTC update gap marks the NEXT BTC update
        assert gate.push(self._quote(3, instrument="BTC")) == 0  # nothing to drop: empty
        [btc] = gate.flush()
        assert btc.sequence_gap is True

    def test_flush_returns_everything_in_order(self) -> None:
        gate = BackpressureGate(maxsize=10)
        gate.push(self._quote(1))
        gate.push(self._quote(2))
        assert [u.sequence for u in gate.flush()] == [1, 2]
        assert gate.flush() == []

    def test_bad_maxsize_rejected(self) -> None:
        with pytest.raises(ValueError):
            BackpressureGate(maxsize=0)


class TestHyperliquidSupervisor:
    def test_on_open_subscribes_every_spec(self) -> None:
        supervisor, transport = _setup()
        findings = supervisor.on_open(T0)
        assert findings == []
        methods = [m.get("method") for m in transport.sent]
        assert methods == ["subscribe"] * 6  # per-coin x4 + allMids + assetCtx
        first = transport.sent[0]["subscription"]
        assert first == {"type": "candle", "coin": "BTC", "interval": "1m"}
        kinds = {s.get("type") for m in transport.sent for s in [m["subscription"]]}
        assert kinds == {"candle", "l2Book", "trades", "bbo", "allMids", "activeAssetCtx"}

    def test_bbo_frame_normalizes_to_quote(self) -> None:
        supervisor, _ = _setup()
        supervisor.on_open(T0)
        supervisor.on_frame(_bbo("BTC"), T0 + timedelta(seconds=1))
        [update] = supervisor.drain()
        assert update.kind is UpdateKind.QUOTE
        assert update.provenance is Provenance.REAL
        assert update.instrument == "BTC"
        assert update.payload["bid"] == 100.0 and update.payload["ask"] == 100.5
        assert update.data_time == datetime.fromtimestamp(1_750_000_000, tz=UTC)

    def test_candle_frame_normalizes_to_candle(self) -> None:
        supervisor, _ = _setup()
        supervisor.on_open(T0)
        supervisor.on_frame(
            _candle("BTC", 99.0, 101.0, 1_750_000_000_000), T0 + timedelta(seconds=1)
        )
        [update] = supervisor.drain()
        assert update.kind is UpdateKind.CANDLE
        assert update.payload["open"] == 99.0
        assert update.payload["close"] == 101.0
        assert update.payload["interval"] == "1m"
        assert update.sequence == 1_750_000_000_000

    def test_trade_sequence_gap_detected(self) -> None:
        supervisor, _ = _setup()
        supervisor.on_open(T0)
        supervisor.on_frame(_trade("BTC", tid=100), T0 + timedelta(seconds=1))
        supervisor.on_frame(
            _trade("BTC", tid=103), T0 + timedelta(seconds=2)  # tids 101-102 missing
        )
        first, second = supervisor.drain()
        assert first.sequence_gap is False
        assert second.sequence_gap is True

    def test_trade_sequence_advances_without_gap(self) -> None:
        supervisor, _ = _setup()
        supervisor.on_open(T0)
        supervisor.on_frame(_trade("BTC", tid=100), T0 + timedelta(seconds=1))
        supervisor.on_frame(_trade("BTC", tid=101), T0 + timedelta(seconds=2))
        first, second = supervisor.drain()
        assert first.sequence_gap is False and second.sequence_gap is False

    def test_l2_frame_emits_two_side_snapshots(self) -> None:
        supervisor, _ = _setup()
        supervisor.on_open(T0)
        supervisor.on_frame(_l2("BTC"), T0 + timedelta(seconds=1))
        bid_side, ask_side = supervisor.drain()
        assert bid_side.kind is UpdateKind.L2_SNAPSHOT and bid_side.payload["side"] == "bid"
        assert ask_side.kind is UpdateKind.L2_SNAPSHOT and ask_side.payload["side"] == "ask"
        assert bid_side.payload["levels"][0] == [100.0, 1.0]  # best bid first

    def test_mids_and_asset_ctx_normalize_to_metrics(self) -> None:
        supervisor, _ = _setup()
        supervisor.on_open(T0)
        supervisor.on_frame(_mids(), T0 + timedelta(seconds=1))
        supervisor.on_frame(_asset_ctx(), T0 + timedelta(seconds=2))
        mids, ctx = supervisor.drain()
        assert mids.kind is UpdateKind.METRICS and mids.payload == {"mid": 100.25}
        assert ctx.kind is UpdateKind.METRICS
        assert ctx.payload["funding_rate"] == 1.25e-05
        assert ctx.payload["mark_price"] == 100.3

    def test_unknown_channel_fails_closed(self) -> None:
        supervisor, _ = _setup()
        supervisor.on_open(T0)
        with pytest.raises(HyperliquidProtocolError):
            supervisor.on_frame({"channel": "webData2"}, T0)

    def test_unknown_coin_fails_closed(self) -> None:
        supervisor, _ = _setup()
        supervisor.on_open(T0)
        with pytest.raises(HyperliquidProtocolError):
            supervisor.on_frame(_bbo("DOGE"), T0 + timedelta(seconds=1))

    def test_unsubscribed_identifier_fails_closed(self) -> None:
        supervisor, _ = _setup()
        supervisor.on_open(T0)
        with pytest.raises(HyperliquidProtocolError):
            supervisor.on_frame({"channel": "bbo", "data": {"coin": "SOL"}}, T0)


class TestDisconnectDrill:
    def test_disconnect_emits_status_and_reset_reconnects(self) -> None:
        supervisor, transport = _setup()
        supervisor.on_open(T0)
        supervisor.on_frame(_bbo("BTC"), T0 + timedelta(seconds=1))
        supervisor.drain()
        transport.connected = False
        findings = supervisor.on_disconnect(T0 + timedelta(seconds=5))
        assert supervisor.connected is False
        statuses = supervisor.drain()
        assert statuses and statuses[0].kind is UpdateKind.STATUS
        assert statuses[0].state is SourceState.DISCONNECTED
        assert findings == []
        # reconnect: resubscribes every spec
        supervisor.on_open(T0 + timedelta(seconds=10), reconnected=True)
        assert supervisor.connected is True
        assert len(transport.sent) == 12  # 6 on the first open, 6 on the reconnect

    def test_reconnect_with_rest_resync_heals_and_reports(self) -> None:
        class ScriptedRest:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def candles(self, coin: str, interval: str, *, start, end) -> list[dict]:
                self.calls.append(f"candles:{coin}")
                return [
                    {"t": 1_750_000_000_000, "T": 1_750_000_060_000, "s": "BTC", "i": "1m",
                     "o": 98.0, "c": 99.0, "h": 99.0, "l": 98.0, "v": 1.0, "n": 1}
                ]

            def l2_book(self, coin: str, *, at=None) -> dict:
                self.calls.append(f"book:{coin}")
                return {
                    "coin": coin,
                    "time": 1_750_000_000_000,
                    "levels": [
                        [{"px": "101.0", "sz": "3.0", "n": 1}],
                        [{"px": "101.5", "sz": "1.0", "n": 1}],
                    ],
                    "type": "book",
                }

        supervisor, transport = _setup(rest=ScriptedRest())
        supervisor.on_open(T0)
        supervisor.on_frame(_trade("BTC", tid=50), T0 + timedelta(seconds=1))
        supervisor.drain()
        transport.connected = False
        supervisor.on_disconnect(T0 + timedelta(seconds=5))
        supervisor.drain()
        findings = supervisor.on_open(T0 + timedelta(seconds=10), reconnected=True)
        updates = supervisor.drain()
        kinds = {u.kind for u in updates}
        assert UpdateKind.CANDLE in kinds  # REST backfill emitted
        assert UpdateKind.L2_SNAPSHOT in kinds  # book snapshot replaced
        gapped = [u for u in updates if u.kind in (UpdateKind.CANDLE, UpdateKind.L2_SNAPSHOT)]
        assert all(u.sequence_gap for u in gapped)
        candle = next(update for update in updates if update.kind is UpdateKind.CANDLE)
        assert candle.payload["interval"] == "1m"
        messages = " ".join(f.message for f in findings)
        assert "cannot be REST re-synced" in messages  # trades gap reported

    def test_venue_level_findings_never_become_phantom_rows(self) -> None:
        """``_surface_findings`` is the live pump's surfacing step (the
        pump itself is drill-gated), so the drill drives it directly: a
        reconnect finding keyed on the venue (resync without a REST
        transport) is reported but must never fabricate a watchlist row
        — only per-source findings surface as LAGGING statuses."""
        supervisor, _ = _setup()
        supervisor.on_open(T0)
        supervisor.drain()
        supervisor._surface_findings(
            [
                GapFinding("hyperliquid", "no REST transport; reconnect gaps reported only"),
                GapFinding("BTC", "book re-sync unavailable: boom"),
            ],
            T0 + timedelta(seconds=1),
        )
        statuses = supervisor.drain()
        assert len(statuses) == 1
        assert statuses[0].instrument == "BTC"
        assert statuses[0].state is SourceState.LAGGING

    def test_freshness_transitions_emit_status(self) -> None:
        supervisor, _ = _setup(lag=timedelta(seconds=10), stale=timedelta(seconds=20))
        supervisor.on_open(T0)
        supervisor.on_frame(_bbo("BTC"), T0 + timedelta(seconds=1))
        supervisor.drain()
        supervisor.on_tick(T0 + timedelta(seconds=12))  # last data 11s ago: now lagging
        statuses = supervisor.drain()
        assert statuses and statuses[0].state is SourceState.LAGGING
        supervisor.on_tick(T0 + timedelta(seconds=22))  # last data 21s ago: now stale
        statuses = supervisor.drain()
        assert statuses and statuses[0].state is SourceState.STALE


class TestScriptedTransport:
    def test_plays_events_and_drop_closes(self) -> None:
        frame = _bbo("BTC")
        transport = ScriptedHyperliquidTransport([frame, "DROP", frame])
        assert transport.next_event() == frame
        assert transport.next_event() == "DROP"
        assert transport.connected is False  # DROP closed the socket
        assert transport.next_event() == frame
        assert transport.next_event() is None

    def test_send_requires_open_connection(self) -> None:
        transport = ScriptedHyperliquidTransport([])
        with pytest.raises(HyperliquidProtocolError):
            transport.send({"method": "subscribe", "subscription": {"type": "bbo", "coin": "BTC"}})


class TestFixtureWebSocketDrill:
    """The scripted venue over a real ephemeral WebSocket (M5 pattern:
    sync test, ``asyncio.run`` inside, matching the stream drills)."""

    def test_fixture_server_delivers_frames(self) -> None:
        from tests.fixture_ws_venue import ScriptedVenue, collect_frames

        async def drill() -> list[object]:
            async with ScriptedVenue(
                plan=[(0.01, _bbo("BTC")), (0.01, _candle("BTC", 99.0, 101.0, 1_750_000_000_000))]
            ) as venue:
                return await collect_frames(venue)

        frames = asyncio.run(drill())
        assert len(frames) == 2
        assert frames[0]["channel"] == "bbo"
        assert frames[1]["channel"] == "candle"

    def test_fixture_drop_closes_connection(self) -> None:
        import websockets

        from tests.fixture_ws_venue import ScriptedVenue, collect_frames

        async def drill() -> None:
            async with ScriptedVenue(
                plan=[(0.01, _bbo("BTC")), (0.01, {"__cmd": "drop"})]
            ) as venue:
                await collect_frames(venue)

        # a network drop kills the socket mid-stream: the client sees the
        # connection die abnormally instead of a clean end-of-session
        with pytest.raises(websockets.exceptions.ConnectionClosedError):
            asyncio.run(drill())


class TestBufferIntegration:
    def test_supervisor_updates_flow_into_lake(self, tmp_path) -> None:
        supervisor, _ = _setup()
        buffer = LiveBuffer(tmp_path)
        supervisor.on_open(T0)
        frames = [
            _bbo("BTC"),
            _candle("BTC", 99.0, 101.0, 1_750_000_000_000),
            _trade("BTC", tid=1),
        ]
        for frame in frames:
            supervisor.on_frame(frame, T0 + timedelta(seconds=1))
        for update in supervisor.drain():
            buffer.append(update)
        replayed = buffer.replay()
        assert len(replayed) == 3
        assert {u.kind for u in replayed} == {UpdateKind.QUOTE, UpdateKind.CANDLE, UpdateKind.TRADE}
        assert all(u.provenance is Provenance.REAL for u in replayed)
        # status updates upsert the source-status table
        supervisor.on_disconnect(T0 + timedelta(seconds=5))
        for update in supervisor.drain():
            buffer.append(update)
        statuses = buffer.statuses()
        assert statuses and statuses[0]["state"] == SourceState.DISCONNECTED.value
        buffer.close()


def test_venue_enum_used() -> None:
    """The contract's venue enum is the domain enum (no new venue strings)."""
    assert Venue.HYPERLIQUID.value == "hyperliquid"
