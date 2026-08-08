"""Hyperliquid stream supervisor and reconnect tests (M5, issue #29).

The supervisor is a pure state machine — every transition takes ``now``
explicitly, so the disconnect/reconnect drill is fully deterministic:
scripted frames, a scripted ``DROP``, a ``RESUME``, and scripted REST
re-sync payloads prove the acceptance criterion (candle coverage clean,
book rebuilt, trades gap reported). The live asyncio pump is smoke-tested
with a fake connect, never against the network.
"""

import asyncio
import json
from datetime import UTC, datetime

import pytest

from quantmesh.domain.market_data import find_gaps
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.hyperliquid.errors import (
    HyperliquidProtocolError,
    HyperliquidUnavailableError,
)
from quantmesh.hyperliquid.market_data import FIXTURE_DIR
from quantmesh.hyperliquid.rest import ScriptedRestTransport
from quantmesh.hyperliquid.stream import (
    HyperliquidStream,
    SimulatedStreamTransport,
    StreamSupervisor,
    next_backoff,
    subscription_identifier,
    ws_url_for,
)

BTC = Instrument(
    symbol="BTC",
    venue=Venue.HYPERLIQUID,
    instrument_type=InstrumentType.PERPETUAL,
    currency="USD",
)

T0 = 1754600400000
STEP_MS = 60_000


def _t(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def _candle_frame(t_ms: int, **overrides: object) -> dict:
    frame = {
        "channel": "candle",
        "data": {
            "t": t_ms,
            "T": t_ms + STEP_MS,
            "s": "BTC",
            "i": "1m",
            "o": "100.0",
            "c": str(100.0 + (t_ms - T0) / STEP_MS),
            "h": "105.0",
            "l": "99.0",
            "v": "10.0",
            "n": 5,
        },
    }
    frame["data"].update(overrides)
    return frame


def _book_frame(t_ms: int) -> dict:
    return {
        "channel": "l2Book",
        "data": {
            "coin": "BTC",
            "levels": [
                [{"n": 3, "px": "107.5", "sz": "2.0"}, {"n": 5, "px": "107.0", "sz": "4.5"}],
                [{"n": 4, "px": "108.0", "sz": "3.0"}, {"n": 6, "px": "108.5", "sz": "5.5"}],
            ],
            "time": t_ms,
        },
    }


def _trades_frame() -> dict:
    return {
        "channel": "trades",
        "data": [
            {"coin": "BTC", "px": "107.2", "side": "A", "sz": "1.5", "time": T0, "tid": 7},
            {"coin": "BTC", "px": "107.3", "side": "B", "sz": "0.8", "time": T0, "tid": 8},
        ],
    }


def _mids_frame() -> dict:
    return {"channel": "allMids", "data": {"mids": {"BTC": "107.25"}, "time": T0}}


def _supervisor(transport, rest) -> StreamSupervisor:
    return StreamSupervisor(
        transport,
        rest,
        candles=[("BTC", "1m", BTC)],
        books=[("BTC", BTC)],
        trades=[("BTC", BTC)],
        mids=True,
    )


def _fixture_candle_rows() -> list[dict]:
    path = FIXTURE_DIR / "wire_candles.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _rest_with_candles(low_ms: int, high_ms: int) -> ScriptedRestTransport:
    """Scripted REST serving fixture rows in ``[low_ms, high_ms]`` and a
    fresh book snapshot per query."""
    rows = [row for row in _fixture_candle_rows() if low_ms <= int(row["t"]) <= high_ms]
    return ScriptedRestTransport(
        candles={("BTC", "1m"): rows},
        l2_books={"BTC": lambda at: _book_frame(int(at.timestamp() * 1000))["data"]},
    )


def _warm_up(supervisor: StreamSupervisor, transport: SimulatedStreamTransport) -> datetime:
    """Feed one frame per channel so every sub has ``last_data_at`` set."""
    supervisor.on_frame(_candle_frame(T0), _t(T0))
    supervisor.on_frame(_candle_frame(T0 + STEP_MS), _t(T0 + STEP_MS))
    supervisor.on_frame(_book_frame(T0 + 2 * STEP_MS), _t(T0 + 2 * STEP_MS))
    supervisor.on_frame(_trades_frame(), _t(T0 + 2 * STEP_MS))
    supervisor.on_frame(_mids_frame(), _t(T0 + 2 * STEP_MS))
    return _t(T0 + 2 * STEP_MS)


# --- subscription and dispatch -------------------------------------------------

def test_open_subscribes_exactly_the_declared_channels() -> None:
    transport = SimulatedStreamTransport([])
    supervisor = _supervisor(transport, ScriptedRestTransport())

    supervisor.on_open(_t(T0))

    sent = [message for message in transport.sent if message["method"] == "subscribe"]
    assert sorted(message["subscription"]["type"] for message in sent) == [
        "allMids",
        "candle",
        "l2Book",
        "trades",
    ]
    assert supervisor.connected is True


def test_candle_frames_accumulate_in_time_order() -> None:
    transport = SimulatedStreamTransport([])
    supervisor = _supervisor(transport, ScriptedRestTransport())
    supervisor.on_open(_t(T0))

    for i in range(3):
        supervisor.on_frame(_candle_frame(T0 + i * STEP_MS), _t(T0 + (i + 1) * STEP_MS))

    bars = supervisor.candle_bars["candle:btc,1m"]
    assert [bar.timestamp for bar in bars] == [_t(T0), _t(T0 + STEP_MS), _t(T0 + 2 * STEP_MS)]


def test_duplicate_candle_frames_fail_closed() -> None:
    transport = SimulatedStreamTransport([])
    supervisor = _supervisor(transport, ScriptedRestTransport())
    supervisor.on_open(_t(T0))
    supervisor.on_frame(_candle_frame(T0), _t(T0))

    with pytest.raises(HyperliquidProtocolError, match="duplicate candle"):
        supervisor.on_frame(_candle_frame(T0), _t(T0))


def test_book_frames_replace_the_book_and_trades_append() -> None:
    transport = SimulatedStreamTransport([])
    supervisor = _supervisor(transport, ScriptedRestTransport())
    supervisor.on_open(_t(T0))

    supervisor.on_frame(_book_frame(T0 + STEP_MS), _t(T0 + STEP_MS))
    supervisor.on_frame(_trades_frame(), _t(T0 + STEP_MS))

    assert supervisor.books["l2Book:btc"].timestamp == _t(T0 + STEP_MS)
    assert [trade.venue_sequence for trade in supervisor.trades["trades:btc"]] == [7, 8]
    assert supervisor.trades["trades:btc"][-1].aggressor_side.value == "sell"


def test_mids_frames_update_the_mid_table() -> None:
    transport = SimulatedStreamTransport([])
    supervisor = _supervisor(transport, ScriptedRestTransport())
    supervisor.on_open(_t(T0))

    supervisor.on_frame(_mids_frame(), _t(T0))

    assert supervisor.mids == {"BTC": 107.25}


def test_pong_and_empty_trades_frames_are_ignored() -> None:
    transport = SimulatedStreamTransport([])
    supervisor = _supervisor(transport, ScriptedRestTransport())
    supervisor.on_open(_t(T0))

    supervisor.on_frame({"channel": "pong"}, _t(T0))
    supervisor.on_frame({"channel": "trades", "data": []}, _t(T0))

    assert supervisor.trades == {"trades:btc": []}


def test_unknown_channels_and_unsubscribed_ids_fail_closed() -> None:
    transport = SimulatedStreamTransport([])
    supervisor = _supervisor(transport, ScriptedRestTransport())
    supervisor.on_open(_t(T0))

    with pytest.raises(HyperliquidProtocolError, match="unknown frame channel"):
        supervisor.on_frame({"channel": "spooky", "data": {}}, _t(T0))
    with pytest.raises(HyperliquidProtocolError, match="unsubscribed identifier"):
        supervisor.on_frame({"channel": "trades", "data": [{"coin": "ETH"}]}, _t(T0))
    with pytest.raises(HyperliquidProtocolError, match="unsubscribed identifier"):
        supervisor.on_frame(_candle_frame(T0, s="ETH"), _t(T0))


def test_malformed_frames_fail_closed() -> None:
    transport = SimulatedStreamTransport([])
    supervisor = _supervisor(transport, ScriptedRestTransport())
    supervisor.on_open(_t(T0))

    with pytest.raises(HyperliquidProtocolError, match="must be an object"):
        supervisor.on_frame([1, 2], _t(T0))
    with pytest.raises(HyperliquidProtocolError, match="must be an object"):
        supervisor.on_frame({"channel": "l2Book", "data": []}, _t(T0))


# --- ping cadence ---------------------------------------------------------------

def test_ping_fires_on_the_sdk_cadence_while_connected() -> None:
    transport = SimulatedStreamTransport([])
    supervisor = _supervisor(transport, ScriptedRestTransport())
    supervisor.on_open(_t(T0))

    supervisor.on_tick(_t(T0 + 49_000))
    assert transport.sent[-1]["method"] != "ping"
    supervisor.on_tick(_t(T0 + 50_000))
    assert transport.sent[-1] == {"method": "ping"}
    supervisor.on_tick(_t(T0 + 99_000))
    assert transport.sent[-1] == {"method": "ping"}


def test_ping_stops_while_disconnected() -> None:
    transport = SimulatedStreamTransport([])
    supervisor = _supervisor(transport, ScriptedRestTransport())
    supervisor.on_open(_t(T0))

    supervisor.on_disconnect(_t(T0 + 1000))
    supervisor.on_tick(_t(T0 + 100_000))

    assert not any(message["method"] == "ping" for message in transport.sent)


# --- disconnect / reconnect drill --------------------------------------------------

def test_disconnect_reports_every_dark_channel() -> None:
    transport = SimulatedStreamTransport([])
    supervisor = _supervisor(transport, ScriptedRestTransport())
    supervisor.on_open(_t(T0))
    _warm_up(supervisor, transport)

    findings = supervisor.on_disconnect(_t(T0 + 5 * STEP_MS))

    assert supervisor.connected is False
    channels = {finding.channel for finding in findings}
    assert channels == {"candle:btc,1m", "l2Book:btc", "trades:btc", "allMids"}
    assert any("went dark at" in finding.message for finding in findings)


def test_reconnect_resubscribes_and_resyncs_candle_gaps() -> None:
    """The acceptance drill: scripted DROP mid-stream, RESUME, re-sync.

    Frames arrive for t0..t1 plus one book/trades/mids update; the
    connection drops; on reconnect the supervisor resubscribes, REST
    re-syncs candles over the gap so the merged series is gap-free,
    replaces the book with a fresh snapshot (Hyperliquid book updates are
    full arrays), and reports the trades gap (no public trades REST
    endpoint) instead of pretending.
    """
    script = [
        _candle_frame(T0),
        _candle_frame(T0 + STEP_MS),
        _book_frame(T0 + 2 * STEP_MS),
        _trades_frame(),
        _mids_frame(),
        "DROP",
        "RESUME",
    ]
    transport = SimulatedStreamTransport(script)
    rest = _rest_with_candles(T0 + STEP_MS, T0 + 5 * STEP_MS)
    supervisor = _supervisor(transport, rest)
    now = _t(T0)

    supervisor.on_open(now)
    while True:
        event = transport.next_event()
        if event is None:
            break
        if event == "DROP":
            now = _t(T0 + 4 * STEP_MS)
            supervisor.on_disconnect(now)
        elif event == "RESUME":
            now = _t(T0 + 6 * STEP_MS)
            findings = supervisor.on_open(now, reconnected=True)
            trades_findings = [f for f in findings if f.channel == "trades:btc"]
            assert trades_findings and "cannot be REST re-synced" in trades_findings[0].message
        else:
            supervisor.on_frame(event, now)

    bars = supervisor.candle_bars["candle:btc,1m"]
    timestamps = [bar.timestamp for bar in bars]
    assert find_gaps(timestamps, interval="1m") == []
    assert len(bars) == 6
    assert bars[-1].timestamp == _t(T0 + 5 * STEP_MS)

    # the book was replaced by a fresh snapshot at the reconnect instant
    assert supervisor.books["l2Book:btc"].timestamp == _t(T0 + 6 * STEP_MS)
    # every subscription was re-sent on the reconnected socket
    subscribes = [m for m in transport.sent if m["method"] == "subscribe"]
    assert len(subscribes) == 8


def test_reconnect_with_unhealed_gaps_reports_a_finding() -> None:
    transport = SimulatedStreamTransport(
        [_candle_frame(T0), _candle_frame(T0 + STEP_MS), "DROP", "RESUME"]
    )
    rest = _rest_with_candles(T0 + 3 * STEP_MS, T0 + 3 * STEP_MS)  # t2 never returns
    supervisor = _supervisor(transport, rest)
    now = _t(T0)

    supervisor.on_open(now)
    while True:
        event = transport.next_event()
        if event is None:
            break
        if event == "DROP":
            now = _t(T0 + 4 * STEP_MS)
            supervisor.on_disconnect(now)
        elif event == "RESUME":
            now = _t(T0 + 6 * STEP_MS)
            findings = supervisor.on_open(now, reconnected=True)
            assert any("unhealed candle gaps" in f.message for f in findings)
        else:
            supervisor.on_frame(event, now)


def test_send_into_a_dead_socket_fails_closed() -> None:
    transport = SimulatedStreamTransport([])

    with pytest.raises(HyperliquidUnavailableError, match="socket is closed"):
        transport.send({"method": "ping"})


# --- helpers -------------------------------------------------------------------

def test_subscription_identifiers_follow_the_sdk_conventions() -> None:
    assert (
        subscription_identifier({"type": "candle", "coin": "BTC", "interval": "1m"})
        == "candle:btc,1m"
    )
    assert subscription_identifier({"type": "l2Book", "coin": "BTC"}) == "l2Book:btc"
    assert subscription_identifier({"type": "trades", "coin": "BTC"}) == "trades:btc"
    assert subscription_identifier({"type": "allMids"}) == "allMids"
    with pytest.raises(HyperliquidProtocolError, match="unsupported subscription"):
        subscription_identifier({"type": "userEvents"})


def test_ws_url_derivation_follows_the_sdk_rule() -> None:
    assert ws_url_for("https://api.hyperliquid-testnet.xyz") == "wss://api.hyperliquid-testnet.xyz/ws"


def test_backoff_is_exponential_and_capped() -> None:
    assert next_backoff(0) == 1.0
    assert next_backoff(1) == 2.0
    assert next_backoff(3) == 8.0
    assert next_backoff(10) == 30.0
    with pytest.raises(ValueError, match=">= 0"):
        next_backoff(-1)


# --- live pump smoke (no network) --------------------------------------------------

class FakeSocket:
    def __init__(self, frames: list[dict]) -> None:
        self._frames = iter(frames)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return json.dumps(next(self._frames))
        except StopIteration as error:
            raise StopAsyncIteration from error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


async def _pump_drill(
    connect_calls: list,
    frames: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[StreamSupervisor, int]:
    import quantmesh.hyperliquid.stream as stream_module

    transport = SimulatedStreamTransport([])
    rest = ScriptedRestTransport(candles={("BTC", "1m"): []})
    supervisor = _supervisor(transport, rest)

    async def fake_connect(url: str, timeout_s: float):
        connect_calls.append(url)
        if len(connect_calls) == 1:
            raise ConnectionError("first connect refused")
        return FakeSocket(frames)

    monkeypatch.setattr(stream_module, "_connect", fake_connect)
    monkeypatch.setattr(
        stream_module,
        "next_backoff",
        lambda attempt, *, base_s=0.01, max_s=0.05: 0.01,
    )
    pump = HyperliquidStream("wss://test/ws", supervisor, connect_timeout_s=1.0)
    task = asyncio.create_task(pump.run())
    for _ in range(200):
        if len(connect_calls) >= 2:
            break
        await asyncio.sleep(0.005)
    pump.close()
    await asyncio.wait_for(task, timeout=5.0)
    return supervisor, len(connect_calls)


@pytest.mark.asyncio
async def test_pump_reconnects_after_a_failed_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor, connect_count = await _pump_drill([], [_candle_frame(T0)], monkeypatch)

    assert connect_count >= 2
    assert supervisor.candle_bars["candle:btc,1m"][0].timestamp == _t(T0)
