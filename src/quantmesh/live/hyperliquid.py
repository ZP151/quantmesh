"""Hyperliquid venue supervisor (iteration 0015 Phase B, ADR-0014).

Subscribes the 4–8 perp watchlist over the official public WebSocket
(candle/l2Book/trades/bbo per coin, allMids and activeAssetCtx once),
normalizes every frame into the owned ``MarketUpdate`` contract and
recovers on reconnect exactly like the M5 ``StreamSupervisor``: REST
candle backfill over the dark window, book snapshot replace, trades
reported as an unhealable gap, and per-coin sequence continuity
detection. Every frame that does not match a subscription raises
``HyperliquidProtocolError`` — a stream that silently drops frames is
worse than one that stops.

The wire parsers (``quantmesh.hyperliquid.wire``) and the REST surface
are reused as-is; ``ScriptedHyperliquidTransport`` drives the drills
deterministically, mirroring ``SimulatedStreamTransport``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.hyperliquid.errors import HyperliquidProtocolError
from quantmesh.hyperliquid.rest import RestTransport, to_ms
from quantmesh.hyperliquid.wire import (
    parse_all_mids,
    parse_asset_ctx_map,
    parse_bbo_frame,
    parse_candle_frame,
    parse_l2_book_frame,
    parse_trades_frame,
)
from quantmesh.live.contract import MarketUpdate, Provenance, UpdateKind
from quantmesh.live.supervisor import GapFinding, VenueSupervisor

_CANDLE_INTERVAL = "1m"
_RESYNC_WINDOW = timedelta(minutes=5)  # REST candle backfill window on reconnect


def _instrument(coin: str) -> Instrument:
    return Instrument(
        symbol=coin,
        venue=Venue.HYPERLIQUID,
        instrument_type=InstrumentType.PERPETUAL,
        currency="USD",
    )


def _update(
    instrument: Instrument,
    kind: UpdateKind,
    payload: dict,
    *,
    data_time: datetime,
    sequence: int | None = None,
    sequence_gap: bool = False,
) -> MarketUpdate:
    return MarketUpdate(
        venue=Venue.HYPERLIQUID,
        instrument=instrument.symbol,
        kind=kind,
        provenance=Provenance.REAL,
        data_time=data_time,
        sequence=sequence,
        sequence_gap=sequence_gap,
        payload=payload,
    )


def _levels(rows: list) -> list[list[float]]:
    return [[level.price, level.quantity] for level in rows]


class HyperliquidVenueSupervisor(VenueSupervisor):
    """Normalizes the Hyperliquid public stream into ``MarketUpdate``s.

    Watchlist symbols are perp coins (``"BTC"``, ``"ETH"``, …).
    ``resync`` needs a REST transport; when the watchlist is configured
    without one (drills), reconnects report the recovery gaps without
    REST healing.
    """

    @property
    def venue(self) -> Venue:
        return Venue.HYPERLIQUID

    def __init__(self, transport, *, rest: RestTransport | None = None, **kwargs) -> None:
        super().__init__(transport, **kwargs)
        self._rest = rest
        self._coins: list[str] = []
        self._last_tid: dict[str, int] = {}

    def specs(self, watchlist: list[str]) -> dict[str, dict]:
        """identifier -> subscription spec (the SDK's identifier rules)."""
        self._coins = list(watchlist)
        specs: dict[str, dict] = {}
        for coin in watchlist:
            specs[f"candle:{coin.lower()},{_CANDLE_INTERVAL}"] = {
                "type": "candle",
                "coin": coin,
                "interval": _CANDLE_INTERVAL,
            }
            specs[f"l2Book:{coin.lower()}"] = {"type": "l2Book", "coin": coin}
            specs[f"trades:{coin.lower()}"] = {"type": "trades", "coin": coin}
            specs[f"bbo:{coin.lower()}"] = {"type": "bbo", "coin": coin}
        specs["allMids"] = {"type": "allMids"}
        specs["activeAssetCtx"] = {"type": "activeAssetCtx"}
        return specs

    # -- dispatch -------------------------------------------------------------

    def dispatch(self, frame: object, now: datetime) -> list[MarketUpdate]:
        if not isinstance(frame, dict):
            raise HyperliquidProtocolError(
                f"frame must be an object, got {type(frame).__name__}"
            )
        channel = frame.get("channel")
        if channel == "pong":
            return []
        identifier = _frame_identifier(frame)
        if identifier == "trades" and frame.get("data") == []:
            return []  # empty trades frames carry no coin; the SDK skips them too
        if identifier not in self._subscribed:
            raise HyperliquidProtocolError(
                f"frame for unsubscribed identifier {identifier!r} (channel {channel!r})"
            )
        if identifier.startswith("candle:"):
            return self._on_candle(identifier, frame.get("data"))
        if identifier.startswith("l2Book:"):
            return self._on_book(identifier, frame.get("data"))
        if identifier.startswith("trades:"):
            return self._on_trades(identifier, frame.get("data"))
        if identifier.startswith("bbo:"):
            return self._on_bbo(identifier, frame.get("data"))
        if identifier == "allMids":
            return self._on_all_mids(frame.get("data"), now)
        if identifier == "activeAssetCtx":
            return self._on_asset_ctx(frame.get("data"), now)
        raise HyperliquidProtocolError(
            f"frame for unsubscribed identifier {identifier!r} (channel {channel!r})"
        )

    def _on_candle(self, identifier: str, data: object) -> list[MarketUpdate]:
        coin = identifier.split(":")[1].rsplit(",", 1)[0].upper()
        bar = parse_candle_frame(data, _instrument(coin), interval=_CANDLE_INTERVAL)
        return [
            _update(
                _instrument(coin),
                UpdateKind.CANDLE,
                {
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                },
                data_time=bar.timestamp,
                sequence=int(to_ms(bar.timestamp)),
            )
        ]

    def _on_book(self, identifier: str, data: object) -> list[MarketUpdate]:
        coin = identifier.split(":")[1].upper()
        book = parse_l2_book_frame(data, _instrument(coin))
        return [
            _update(
                _instrument(coin),
                UpdateKind.L2_SNAPSHOT,
                {"side": "bid", "levels": _levels(book.bids)},
                data_time=book.timestamp,
            ),
            _update(
                _instrument(coin),
                UpdateKind.L2_SNAPSHOT,
                {"side": "ask", "levels": _levels(book.asks)},
                data_time=book.timestamp,
            ),
        ]

    def _on_trades(self, identifier: str, data: object) -> list[MarketUpdate]:
        coin = identifier.split(":")[1].upper()
        events = parse_trades_frame(data, _instrument(coin))
        updates: list[MarketUpdate] = []
        for event in events:
            tid = event.venue_sequence
            last = self._last_tid.get(coin)
            # a gap needs a continuity reference: the first trade after a
            # subscription (or reconnect) has none, so it is never a gap
            gap = last is not None and tid is not None and tid > last + 1
            if tid is not None and (last is None or tid > last):
                self._last_tid[coin] = tid
            updates.append(
                _update(
                    _instrument(coin),
                    UpdateKind.TRADE,
                    {
                        "price": event.price,
                        "size": event.quantity,
                        "side": (
                            "buy"
                            if event.aggressor_side is None
                            else event.aggressor_side.value
                        ),
                    },
                    data_time=event.timestamp,
                    sequence=tid,
                    sequence_gap=gap,
                )
            )
        return updates

    def _on_bbo(self, identifier: str, data: object) -> list[MarketUpdate]:
        coin = identifier.split(":")[1].upper()
        payload = parse_bbo_frame(data)
        assert isinstance(data, dict)
        return [
            _update(
                _instrument(coin),
                UpdateKind.QUOTE,
                payload,
                data_time=_frame_time(data),
            )
        ]

    def _on_all_mids(self, data: object, now: datetime) -> list[MarketUpdate]:
        mids = parse_all_mids(data)
        return [
            _update(_instrument(coin), UpdateKind.METRICS, {"mid": price}, data_time=now)
            for coin, price in mids.items()
            if coin in self._coins
        ]

    def _on_asset_ctx(self, data: object, now: datetime) -> list[MarketUpdate]:
        ctx = parse_asset_ctx_map(data)
        return [
            _update(_instrument(coin), UpdateKind.METRICS, metrics, data_time=now)
            for coin, metrics in ctx.items()
            if coin in self._coins
        ]

    # -- reconnect recovery -----------------------------------------------------

    def resync(self, now: datetime) -> list[MarketUpdate]:
        """REST-heal the channels that went dark; report unhealable gaps."""
        if self._rest is None:
            self._gap_pending.append(
                GapFinding("hyperliquid", "no REST transport; reconnect gaps reported only")
            )
            return []
        updates: list[MarketUpdate] = []
        for coin in self._coins:
            instrument = _instrument(coin)
            try:
                rows = self._rest.candles(
                    coin, _CANDLE_INTERVAL, start=now - _RESYNC_WINDOW, end=now
                )
            except Exception as error:  # REST transport may fail like any network call
                self._gap_pending.append(GapFinding(coin, f"candle re-sync unavailable: {error}"))
                continue
            for row in rows:
                bar = parse_candle_frame(row, instrument, interval=_CANDLE_INTERVAL)
                updates.append(
                    _update(
                        instrument,
                        UpdateKind.CANDLE,
                        {
                            "open": bar.open,
                            "high": bar.high,
                            "low": bar.low,
                            "close": bar.close,
                            "volume": bar.volume,
                        },
                        data_time=bar.timestamp,
                        sequence=int(to_ms(bar.timestamp)),
                        sequence_gap=True,
                    )
                )
            try:
                snapshot = self._rest.l2_book(coin, at=now)
                book = parse_l2_book_frame(snapshot, instrument)
                updates.extend(
                    [
                        _update(
                            instrument,
                            UpdateKind.L2_SNAPSHOT,
                            {"side": "bid", "levels": _levels(book.bids)},
                            data_time=now,
                            sequence_gap=True,
                        ),
                        _update(
                            instrument,
                            UpdateKind.L2_SNAPSHOT,
                            {"side": "ask", "levels": _levels(book.asks)},
                            data_time=now,
                            sequence_gap=True,
                        ),
                    ]
                )
            except Exception as error:
                self._gap_pending.append(GapFinding(coin, f"book re-sync unavailable: {error}"))
            if coin in self._last_tid:
                self._gap_pending.append(
                    GapFinding(
                        coin,
                        f"trades cannot be REST re-synced; sequence resumes at tid "
                        f"{self._last_tid[coin]}",
                    )
                )
        return updates


def _frame_time(row: dict) -> datetime:
    """The BBO row's venue time as an aware datetime."""
    millis = row.get("time")
    if not isinstance(millis, int):
        raise HyperliquidProtocolError("bbo row missing an integer 'time'")
    return datetime.fromtimestamp(millis / 1000, tz=UTC)


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
    if channel == "bbo":
        if not isinstance(data, dict):
            raise HyperliquidProtocolError("bbo frame data must be an object")
        return f'bbo:{str(data.get("coin")).lower()}'
    if channel == "allMids":
        return "allMids"
    if channel == "activeAssetCtx":
        return "activeAssetCtx"
    raise HyperliquidProtocolError(f"unknown frame channel {channel!r}")


class ScriptedHyperliquidTransport:
    """Scripted wire for the drills (mirrors ``SimulatedStreamTransport``).

    ``send`` records messages so a drill can assert exactly what the
    supervisor subscribed; ``next_event`` plays the script with
    ``DROP``/``RESUME`` driving connection state.
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
            raise HyperliquidProtocolError("socket is closed; message was not delivered")
        self.sent.append(message)

    async def recv(self) -> object:
        raise AssertionError("scripted transports are driven by drills, not the pump")

    def next_event(self) -> object | None:
        """Next scripted event; ``DROP``/``RESUME`` drive connection state."""
        if self._index >= len(self._script):
            return None
        event = self._script[self._index]
        self._index += 1
        if event == "DROP":
            self.connected = False
        return event


class LiveHyperliquidTransport:
    """The live wire for ``HyperliquidVenueSupervisor`` (ADR-0014).

    The supervisor protocol is synchronous (drills), so this transport
    defers the actual socket open to the first ``recv`` and queues the
    subscription sends until the socket is up — the pump flushes them on
    the wire before the first frame. Only the live pump constructs this
    (or the browser E2E, pointed at the local fixture venue); drills use
    ``ScriptedHyperliquidTransport``, and the live smoke drill is this
    path's gate — never unit-tested against the network.
    """

    def __init__(self, url: str, *, connect_timeout_s: float = 10.0) -> None:
        self._url = url
        self._connect_timeout_s = connect_timeout_s
        self._socket = None
        self._outbox: list[str] = []

    def connect(self) -> None:
        """No-op: the socket opens on the first ``recv`` (the pump calls
        this synchronously inside the running loop, so nothing here may
        block or await)."""

    def close(self) -> None:
        """Best-effort close at shutdown; the pump is cancelled with us."""
        self._socket = None

    def send(self, message: dict) -> None:
        """Queue a subscription; flushed to the wire once the socket
        opens (each ``on_open`` rebuilds the outbox)."""
        self._outbox.append(json.dumps(message))

    async def recv(self) -> object:
        socket = await self._ensure_open()
        return json.loads(await socket.recv())

    async def _ensure_open(self):
        import websockets

        if self._socket is None:
            self._socket = await websockets.connect(
                self._url, open_timeout=self._connect_timeout_s
            )
        if self._outbox:
            pending, self._outbox = self._outbox, []
            for message in pending:
                await self._socket.send(message)
        return self._socket
