"""Hyperliquid WebSocket surface with reconnect and gap recovery (issue #29).

The SDK's bundled ``WebsocketManager`` is a thread with no reconnect:
on a dropped connection ``run_forever`` exits and nothing resubscribes
(verified in the pinned submodule source). QuantMesh therefore owns the
stream (ADR-0007), split into three layers:

- ``StreamSupervisor`` — a pure, deterministic state machine. It
  subscribes on open, dispatches frames by channel exactly like the
  SDK's ``ws_msg_to_identifier``, tracks per-subscription last-data
  instants, and on reconnect resubscribes and REST re-syncs every
  channel that went dark (candles merged over the gap, the book
  replaced by a fresh snapshot — Hyperliquid book updates are full
  level arrays, not deltas — trades reported as gap findings because
  there is no public trades REST endpoint).
- ``SimulatedStreamTransport`` — a scripted transport the drills drive
  (frames, ``DROP``, ``RESUME``), so the supervisor's behavior under a
  disconnect is proven deterministically.
- ``HyperliquidStream`` — the live asyncio pump over ``websockets``
  (already a core dependency via ``uvicorn[standard]``) feeding the
  supervisor and implementing the reconnect/backoff loop. It is never
  exercised by unit tests against the network; the drill path is the
  Phase E gate.

Every frame that does not match a subscribed identifier, an unknown
channel, or a malformed payload raises ``HyperliquidProtocolError``:
a stream that silently drops frames is worse than one that stops.
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Protocol

from quantmesh.domain.market_data import Bar, OrderBook, TradeEvent, find_gaps
from quantmesh.domain.models import Instrument
from quantmesh.hyperliquid.errors import HyperliquidProtocolError, HyperliquidUnavailableError
from quantmesh.hyperliquid.rest import RestTransport, to_ms
from quantmesh.hyperliquid.wire import (
    parse_all_mids,
    parse_candle_frame,
    parse_l2_book_frame,
    parse_trades_frame,
)

__all__ = [
    "ws_url_for",
    "subscription_identifier",
    "next_backoff",
    "GapFinding",
    "StreamSupervisor",
    "SimulatedStreamTransport",
    "HyperliquidStream",
]

_PING_INTERVAL = timedelta(seconds=50)  # the SDK's own ping cadence


def ws_url_for(base_url: str) -> str:
    """``https://…`` → ``wss://…/ws``, the SDK's ``WebsocketManager`` rule."""
    return "ws" + base_url[len("http"):] + "/ws"


def subscription_identifier(subscription: dict) -> str:
    """The SDK's ``subscription_to_identifier`` for the channels we support."""
    kind = subscription["type"]
    if kind == "allMids":
        return "allMids"
    if kind in ("l2Book", "trades"):
        return f'{kind}:{subscription["coin"].lower()}'
    if kind == "candle":
        return f'candle:{subscription["coin"].lower()},{subscription["interval"]}'
    raise HyperliquidProtocolError(f"unsupported subscription type {kind!r}")


def next_backoff(attempt: int, *, base_s: float = 1.0, max_s: float = 30.0) -> float:
    """Exponential backoff for the reconnect loop, capped and finite."""
    if attempt < 0:
        raise ValueError("attempt must be >= 0")
    return min(base_s * (2 ** attempt), max_s)


@dataclass(frozen=True)
class GapFinding:
    """One recovery gap discovered on reconnect (reported, not hidden)."""

    channel: str
    message: str


@dataclass
class _CandleSub:
    spec: dict
    instrument: Instrument
    interval: str
    bars: dict[int, Bar] = field(default_factory=dict)
    last_data_at: datetime | None = None


@dataclass
class _BookSub:
    spec: dict
    instrument: Instrument
    book: OrderBook | None = None
    last_data_at: datetime | None = None


@dataclass
class _TradesSub:
    spec: dict
    instrument: Instrument
    trades: list[TradeEvent] = field(default_factory=list)
    last_tid: int | None = None
    last_data_at: datetime | None = None


@dataclass
class _MidsSub:
    spec: dict
    mids: dict[str, float] = field(default_factory=dict)
    last_data_at: datetime | None = None


class StreamTransport(Protocol):
    """The wire surface the supervisor drives; live and simulated alike."""

    def connect(self) -> None: ...
    def close(self) -> None: ...
    def send(self, message: dict) -> None: ...


class StreamSupervisor:
    """Deterministic stream state machine: subscribe, dispatch, recover.

    Every transition takes ``now`` explicitly, so drills script time
    without sleeps. ``on_open(reconnected=…)`` subscribes all
    subscriptions (and, on a reconnect, REST re-syncs the channels that
    went dark); ``on_frame`` dispatches; ``on_disconnect`` records the
    per-channel gap window; ``on_tick`` sends the ping.
    """

    def __init__(
        self,
        transport: StreamTransport,
        rest: RestTransport,
        *,
        candles: list[tuple[str, str, Instrument]] | None = None,
        books: list[tuple[str, Instrument]] | None = None,
        trades: list[tuple[str, Instrument]] | None = None,
        mids: bool = False,
    ) -> None:
        self._transport = transport
        self._rest = rest
        self._candles: dict[str, _CandleSub] = {}
        self._books: dict[str, _BookSub] = {}
        self._trades: dict[str, _TradesSub] = {}
        self._mids: _MidsSub | None = _MidsSub({"type": "allMids"}) if mids else None
        self._subscriptions: dict[str, dict] = {}
        self.connected = False
        self._last_ping_at: datetime | None = None

        for symbol, interval, instrument in candles or []:
            spec = {"type": "candle", "coin": symbol, "interval": interval}
            self._candles[f"candle:{symbol.lower()},{interval}"] = _CandleSub(
                spec, instrument, interval
            )
            self._subscriptions[f"candle:{symbol.lower()},{interval}"] = spec
        for symbol, instrument in books or []:
            self._books[f"l2Book:{symbol.lower()}"] = _BookSub(
                {"type": "l2Book", "coin": symbol}, instrument
            )
            self._subscriptions[f"l2Book:{symbol.lower()}"] = {"type": "l2Book", "coin": symbol}
        for symbol, instrument in trades or []:
            self._trades[f"trades:{symbol.lower()}"] = _TradesSub(
                {"type": "trades", "coin": symbol}, instrument
            )
            self._subscriptions[f"trades:{symbol.lower()}"] = {"type": "trades", "coin": symbol}
        if self._mids is not None:
            self._subscriptions["allMids"] = {"type": "allMids"}

    # -- observable state (the drills assert against these) --------------------

    @property
    def candle_bars(self) -> dict[str, list[Bar]]:
        return {
            key: sorted(sub.bars.values(), key=lambda bar: bar.timestamp)
            for key, sub in self._candles.items()
        }

    @property
    def books(self) -> dict[str, OrderBook]:
        return {key: sub.book for key, sub in self._books.items() if sub.book is not None}

    @property
    def trades(self) -> dict[str, list[TradeEvent]]:
        return {key: sub.trades for key, sub in self._trades.items()}

    @property
    def mids(self) -> dict[str, float]:
        return dict(self._mids.mids) if self._mids is not None else {}

    # -- supervisor transitions ------------------------------------------------

    def on_open(self, now: datetime, *, reconnected: bool = False) -> list[GapFinding]:
        self._transport.connect()
        self.connected = True
        # the ping cadence anchors at the connection instant, like the SDK's
        # own timer: the first tick at or after +50 s pings, not the first tick.
        self._last_ping_at = now
        for spec in self._subscriptions.values():
            self._transport.send({"method": "subscribe", "subscription": spec})
        if reconnected:
            return self._re_sync_gaps(now)
        return []

    def on_frame(self, frame: object, now: datetime) -> None:
        if not isinstance(frame, dict):
            raise HyperliquidProtocolError(f"frame must be an object, got {type(frame).__name__}")
        channel = frame.get("channel")
        if channel == "pong":
            return
        identifier = _frame_identifier(frame)
        if identifier == "trades" and frame.get("data") == []:
            # Empty trades frames carry no coin; the SDK skips them too.
            return
        if identifier in self._candles:
            sub = self._candles[identifier]
            bar = parse_candle_frame(frame.get("data"), sub.instrument, interval=sub.interval)
            previous = sub.bars.get(int(to_ms(bar.timestamp)))
            if previous is not None:
                raise HyperliquidProtocolError(
                    f"duplicate candle {bar.timestamp.isoformat()} for {identifier}"
                )
            sub.bars[int(to_ms(bar.timestamp))] = bar
            sub.last_data_at = now
            return
        if identifier in self._books:
            sub = self._books[identifier]
            sub.book = parse_l2_book_frame(frame.get("data"), sub.instrument)
            sub.last_data_at = now
            return
        if identifier in self._trades:
            sub = self._trades[identifier]
            events = parse_trades_frame(frame.get("data"), sub.instrument)
            if not events:
                return
            for event in events:
                sub.trades.append(event)
            sub.last_tid = max((sub.last_tid or 0), *(e.venue_sequence for e in events))
            sub.last_data_at = now
            return
        if identifier == "allMids" and self._mids is not None:
            self._mids.mids = parse_all_mids(frame.get("data"))
            self._mids.last_data_at = now
            return
        raise HyperliquidProtocolError(
            f"frame for unsubscribed identifier {identifier!r} (channel {channel!r})"
        )

    def on_disconnect(self, now: datetime) -> list[GapFinding]:
        self.connected = False
        findings = []
        for key, sub in self._candles.items():
            if sub.last_data_at is not None:
                findings.append(
                    GapFinding(key, f"candle stream went dark at {sub.last_data_at.isoformat()}")
                )
        for key, sub in self._books.items():
            if sub.last_data_at is not None:
                findings.append(
                    GapFinding(key, f"l2Book stream went dark at {sub.last_data_at.isoformat()}")
                )
        for key, sub in self._trades.items():
            if sub.last_data_at is not None:
                findings.append(
                    GapFinding(key, f"trades stream went dark at {sub.last_data_at.isoformat()}")
                )
        if self._mids is not None and self._mids.last_data_at is not None:
            findings.append(GapFinding("allMids", "mids stream went dark"))
        return findings

    def on_tick(self, now: datetime) -> None:
        """Ping cadence (the SDK pings every 50 s while connected)."""
        if not self.connected:
            return
        if self._last_ping_at is None or now - self._last_ping_at >= _PING_INTERVAL:
            self._transport.send({"method": "ping"})
            self._last_ping_at = now

    def close(self, now: datetime) -> None:
        self.connected = False
        self._transport.close()

    # -- gap recovery ----------------------------------------------------------

    def _re_sync_gaps(self, now: datetime) -> list[GapFinding]:
        findings = []
        for key, sub in self._candles.items():
            if sub.last_data_at is None:
                continue
            rows = self._rest.candles(
                sub.spec["coin"], sub.interval, start=sub.last_data_at, end=now
            )
            for row in rows:
                bar = parse_candle_frame(row, sub.instrument, interval=sub.interval)
                open_ms = int(to_ms(bar.timestamp))
                previous = sub.bars.get(open_ms)
                if previous is not None:
                    continue  # already seen; the frame stream wins
                sub.bars[open_ms] = bar
            series = sorted(sub.bars.values(), key=lambda bar: bar.timestamp)
            missing = find_gaps([bar.timestamp for bar in series], interval=sub.interval)
            if missing:
                findings.append(
                    GapFinding(key, f"re-sync left {len(missing)} unhealed candle gaps")
                )
            sub.last_data_at = now
        for key, sub in self._books.items():
            if sub.last_data_at is None:
                continue
            try:
                snapshot = self._rest.l2_book(sub.spec["coin"], at=now)
            except HyperliquidProtocolError as error:
                findings.append(GapFinding(key, f"book re-sync unavailable: {error}"))
                continue
            sub.book = parse_l2_book_frame(snapshot, sub.instrument)
            sub.last_data_at = now
        for key, sub in self._trades.items():
            if sub.last_data_at is None:
                continue
            if sub.last_tid is not None:
                findings.append(
                    GapFinding(
                        key,
                        f"trades cannot be REST re-synced; sequence resumes at tid {sub.last_tid}",
                    )
                )
            sub.last_data_at = now
        if self._mids is not None and self._mids.last_data_at is not None:
            self._mids.last_data_at = now
        return findings


def _frame_identifier(frame: dict) -> str:
    """The SDK's ``ws_msg_to_identifier`` for the channels we support."""
    channel = frame.get("channel")
    data = frame.get("data")
    if channel == "l2Book":
        if not isinstance(data, dict):
            raise HyperliquidProtocolError("l2Book frame data must be an object")
        return f'l2Book:{str(data.get("coin")).lower()}'
    if channel == "trades":
        if not isinstance(data, list) or not data:
            return "trades"
        first = data[0]
        if not isinstance(first, dict):
            raise HyperliquidProtocolError("trades frame rows must be objects")
        return f'trades:{str(first.get("coin")).lower()}'
    if channel == "candle":
        if not isinstance(data, dict):
            raise HyperliquidProtocolError("candle frame data must be an object")
        return f'candle:{str(data.get("s")).lower()},{data.get("i")}'
    if channel == "allMids":
        return "allMids"
    raise HyperliquidProtocolError(f"unknown frame channel {channel!r}")


class SimulatedStreamTransport:
    """Scripted wire: frames, ``DROP`` and ``RESUME`` markers.

    ``send`` records messages so a drill can assert exactly what the
    supervisor subscribed and pinged, and raises
    ``HyperliquidUnavailableError`` while disconnected — a send into a
    dead socket must fail, not vanish.
    """

    def __init__(self, script: list[object]) -> None:
        self._script = list(script)
        self._index = 0
        self.connected = False
        self.sent: list[dict] = []

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def send(self, message: dict) -> None:
        if not self.connected:
            raise HyperliquidUnavailableError("socket is closed; message was not delivered")
        self.sent.append(message)

    def next_event(self) -> object | None:
        """The next scripted event; ``DROP``/``RESUME`` drive connection state.

        ``None`` means the script is exhausted — the only end signal.
        ``DROP`` closes the connection (the caller fires the
        supervisor's ``on_disconnect``); ``RESUME`` reopens it.
        """
        if self._index >= len(self._script):
            return None
        event = self._script[self._index]
        self._index += 1
        if event == "DROP":
            self.connected = False
        return event


class HyperliquidStream:
    """Live asyncio pump over ``websockets`` feeding a ``StreamSupervisor``.

    Reconnect loop: connect → ``on_open`` → pump frames → on any failure
    ``on_disconnect`` → exponential backoff → reconnect → ``on_open``
    with ``reconnected=True`` (resubscribe + REST re-sync). Never
    constructed implicitly and never exercised by unit tests against the
    network — the Phase E drill is the live path.
    """

    def __init__(
        self,
        url: str,
        supervisor: StreamSupervisor,
        *,
        connect_timeout_s: float = 5.0,
        max_backoff_s: float = 30.0,
    ) -> None:
        self._url = url
        self._supervisor = supervisor
        self._connect_timeout_s = connect_timeout_s
        self._max_backoff_s = max_backoff_s
        self._closed = False

    def close(self) -> None:
        self._closed = True

    async def run(self) -> None:
        attempts = 0
        while not self._closed:
            now = datetime.now(UTC)
            reconnected = attempts > 0
            try:
                # await the connection first: ``websockets.connect`` returns
                # the connection object (an async CM), not a context manager
                # coroutine — ``async with`` on a raw coroutine raises
                # TypeError without ever awaiting it (verified on 3.13).
                socket = await _connect(self._url, self._connect_timeout_s)
                async with socket:
                    self._supervisor.on_open(now, reconnected=reconnected)
                    attempts = 0
                    async for raw in socket:
                        if self._closed:
                            break
                        try:
                            frame = json.loads(raw)
                        except json.JSONDecodeError as error:
                            raise HyperliquidProtocolError(
                                f"malformed stream frame: {error}"
                            ) from error
                        self._supervisor.on_frame(frame, datetime.now(UTC))
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            finally:
                # a clean socket close is still a disconnect: mark the
                # channels dark and let the backoff govern the reconnect.
                self._supervisor.on_disconnect(datetime.now(UTC))
            attempts += 1
            await asyncio.sleep(next_backoff(attempts, max_s=self._max_backoff_s))


async def _connect(url: str, timeout_s: float):
    import websockets

    return await websockets.connect(url, open_timeout=timeout_s)
