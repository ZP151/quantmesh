"""Moomoo OpenD read-only venue supervisor (iteration 0015 Phase F).

OpenD is request/response, not a push stream: the local daemon
answers ``get_rt_ticker`` (recent trade ticks per code) and
``get_stock_quote`` (a batch snapshot of last price + volume with the
venue's own data date/time). ``MoomooVenueTransport`` turns that
polling boundary into the venue wire — a poll task on the pump's
loop calls the sync client off-thread and queues one frame per
payload, so ``recv()`` feeds the supervisor exactly like a socket.

Honesty comes from the venue's own timestamps: every frame carries
the data date/time OpenD reported (venue-local, converted to UTC by
the M4 adapter). While OpenD answers with fresh timestamps the feed
labels the surface real; an answer whose venue clock is outside the
realtime window (``lag``) — a closed market, a delayed feed — is
blocked at dispatch, so nothing old is ever labeled real: the last
real numbers age to Stale through the feed's own freshness machine,
and the tracker walks the LAGGING → STALE ladder. A probe failure at
connect (or a poll failure mid-stream) disconnects the pump — the
status model then surfaces the watchlist as unavailable/disconnected
and the backoff loop retries, so the surface recovers on its own when
the local daemon comes back.

The normalized surface carries no bid/ask: the M4 stock-quote payload
is last price + volume only, and the contract's QUOTE requires both
sides. The supervisor therefore emits METRICS (last + volume) from
the quote snapshot and TRADE ticks from ``rt_ticker`` — never a
fabricated two-sided quote, and paper orders stay impossible for
Moomoo instruments by construction (the quote fence has no quote to
bless). Ticker rows whose aggressor side the venue reports as
neutral/unknown are accepted and produce no update (documented venue
behavior, like the Polymarket single-sided ``price_change`` frames):
the price and size are real but the side is not, and the trade
identity on the normalized surface includes the side.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Protocol

from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.live.contract import MarketUpdate, Provenance, UpdateKind
from quantmesh.live.supervisor import GapFinding, VenueSupervisor
from quantmesh.moomoo.market_data import MoomooDataAdapter, _split_code
from quantmesh.moomoo.opend import OpenDCapabilities, OpenDError

__all__ = ["MoomooProtocolError", "MoomooVenueSupervisor", "MoomooVenueTransport"]

DEFAULT_POLL_INTERVAL = timedelta(seconds=5)


class MoomooProtocolError(ValueError):
    """A poll frame that does not match the OpenD payload contract."""


class _PollClient(Protocol):
    """The OpenD boundary the transport polls (the M4 client shape)."""

    def probe(self) -> OpenDCapabilities: ...

    def stock_quote(self, codes: list[str]) -> dict: ...

    def rt_ticker(self, code: str, *, num: int) -> dict: ...


class MoomooVenueTransport:
    """Poll-driven venue wire over a local OpenD client.

    ``connect()`` probes OpenD (a failed probe raises, which the pump
    turns into the unavailable/disconnected surface); ``send()`` collects
    the subscription specs, whose codes drive the poll task; each poll
    cycle yields one ``{"kind": "stock_quote"|"rt_ticker", "payload"}``
    frame per payload through ``recv()``. A poll call failure is queued
    as a ``poll_error`` frame — the supervisor raises on it, the pump
    disconnects, and the backoff loop reconnects (fail-closed, like a
    dropped socket).
    """

    def __init__(
        self,
        client: _PollClient,
        *,
        poll_interval: timedelta = DEFAULT_POLL_INTERVAL,
        ticker_num: int = 100,
    ) -> None:
        self._client = client
        self._poll_interval = poll_interval
        self._ticker_num = ticker_num
        self._frames: asyncio.Queue[object] | None = None
        self._codes: dict[str, str] = {}  # symbol -> sdk code
        self._codes_ready = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def connect(self) -> None:
        capabilities = self._client.probe()
        if not capabilities.quote:
            raise MoomooProtocolError(
                "OpenD probe reports quote capability off — the read-only "
                "market surface cannot be served"
            )
        if self._task is not None:
            # a stale poll task from a previous session must never poll
            # twice; the supervisor closes the transport on disconnect,
            # but cancel defensively so connect() is idempotent
            self._task.cancel()
        self._frames = asyncio.Queue()
        self._codes_ready.clear()
        loop = asyncio.get_running_loop()
        self._task = loop.create_task(self._poll())

    def send(self, message: object) -> None:
        """Collect subscription specs: ``{"code": "US.AAPL"}`` per symbol."""
        if not isinstance(message, dict) or not isinstance(message.get("code"), str):
            raise MoomooProtocolError(
                f"moomoo subscription spec must carry a code, got {message!r}"
            )
        symbol = message.get("symbol")
        if not isinstance(symbol, str):
            raise MoomooProtocolError(f"moomoo subscription spec missing its symbol: {message!r}")
        self._codes[symbol] = message["code"]
        self._codes_ready.set()

    async def recv(self) -> object:
        if self._frames is None:
            raise MoomooProtocolError("recv before connect")
        return await self._frames.get()

    def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self._frames = None
        self._codes_ready.clear()
        self._codes = {}

    async def _poll(self) -> None:
        await self._codes_ready.wait()
        while True:
            codes = sorted(self._codes.values())
            try:
                quote = await asyncio.to_thread(self._client.stock_quote, codes)
                await self._frames.put({"kind": "stock_quote", "payload": quote})
                for code in codes:
                    ticker = await asyncio.to_thread(
                        self._client.rt_ticker, code, num=self._ticker_num
                    )
                    await self._frames.put({"kind": "rt_ticker", "payload": ticker})
            except OpenDError as error:
                await self._frames.put({"kind": "poll_error", "message": str(error)})
            await asyncio.sleep(self._poll_interval.total_seconds())


class MoomooVenueSupervisor(VenueSupervisor):
    """The OpenD poll surface as a venue supervisor.

    The watchlist is bare symbols (``AAPL``); the SDK needs
    market-qualified codes (``US.AAPL``), derived from the instrument's
    ``metadata["market"]`` via ``sdk_code`` — an instrument without a
    known market fails closed at subscribe time rather than guessing.
    """

    def __init__(
        self,
        transport: MoomooVenueTransport,
        *,
        market: str = "US",
        lag: timedelta = timedelta(seconds=30),
        stale: timedelta = timedelta(seconds=90),
        max_buffered: int = 1000,
    ) -> None:
        super().__init__(transport, lag=lag, stale=stale, max_buffered=max_buffered)
        self._market = market
        self._adapter = MoomooDataAdapter()
        # ticker rows are polled repeatedly; venue sequences dedupe the
        # overlapping windows so the tape never replays the same tick.
        self._seen_sequences: dict[str, set[int]] = {}

    @property
    def venue(self) -> Venue:
        return Venue.MOOMOO

    def _instrument(self, symbol: str) -> Instrument:
        return Instrument(
            symbol=symbol,
            venue=Venue.MOOMOO,
            instrument_type=InstrumentType.EQUITY,
            metadata={"market": self._market},
        )

    def specs(self, watchlist: list[str]) -> dict[str, dict]:
        """One poll target per symbol: the market-qualified SDK code."""
        from quantmesh.moomoo.market_data import sdk_code

        specs: dict[str, dict] = {}
        for symbol in watchlist:
            specs[symbol] = {
                "symbol": symbol,
                "code": sdk_code(self._instrument(symbol)),
            }
        return specs

    # -- wire ---------------------------------------------------------------

    def _update(
        self,
        symbol: str,
        kind: UpdateKind,
        ts: datetime,
        now: datetime,
        payload: dict[str, object],
        *,
        sequence: int | None = None,
    ) -> MarketUpdate:
        return MarketUpdate(
            venue=self.venue,
            instrument=symbol,
            kind=kind,
            provenance=Provenance.REAL,
            data_time=ts,
            received_at=now,
            sequence=sequence,
            payload=payload,
        )

    def dispatch(self, frame: object, now: datetime) -> list[MarketUpdate]:
        if not isinstance(frame, dict):
            raise MoomooProtocolError(f"poll frame must be an object, got {frame!r}")
        kind = frame.get("kind")
        if kind == "stock_quote":
            return self._on_stock_quote(frame.get("payload"), now)
        if kind == "rt_ticker":
            return self._on_rt_ticker(frame.get("payload"), now)
        if kind == "poll_error":
            message = frame.get("message")
            raise MoomooProtocolError(f"OpenD poll failed: {message!r}")
        raise MoomooProtocolError(f"unknown poll frame kind {kind!r}")

    def _on_stock_quote(self, payload: object, now: datetime) -> list[MarketUpdate]:
        """Quote snapshot rows → one METRICS update (last + volume)
        per subscribed symbol, with the venue's own data date/time as
        the honest timestamp. No bid/ask exists on the wire, so no
        QUOTE is ever emitted."""
        if not isinstance(payload, dict):
            raise MoomooProtocolError(f"stock_quote payload must be an object, got {payload!r}")
        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            raise MoomooProtocolError(f"stock_quote payload must carry rows: {payload!r}")
        updates: list[MarketUpdate] = []
        for row in rows:
            # one snapshot per subscribed code: split the batch so the
            # M4 adapter (one row per payload) sees its own contract
            code = row.get("code")
            if not isinstance(code, str):
                raise MoomooProtocolError(f"stock_quote row missing its code: {row!r}")
            symbol = _split_code(code)[1]
            if symbol not in self._watchlist:
                raise MoomooProtocolError(f"stock_quote payload for unsubscribed symbol {symbol!r}")
            instrument = self._instrument(symbol)
            quote = self._adapter.stock_quote_to_quote(instrument, {"rows": [row]})
            if now - quote.timestamp > self._freshness.lag:
                # the venue's own clock places this snapshot outside the
                # realtime window (closed market, delayed feed): emitting
                # it would label old data "real". Blocking it lets the
                # last real numbers age honestly (Stale) and the tracker
                # surface the LAGGING → STALE ladder.
                continue
            metrics: dict[str, object] = {"last": quote.last}
            if quote.volume is not None:
                metrics["volume"] = quote.volume
            updates.append(
                self._update(symbol, UpdateKind.METRICS, quote.timestamp, now, metrics)
            )
        return updates

    def _on_rt_ticker(self, payload: object, now: datetime) -> list[MarketUpdate]:
        """Ticker rows → TRADE updates (price, size, aggressor side).

        Rows the venue reports with a neutral/unknown direction are
        accepted and skipped — the side is part of the normalized
        trade identity, and inventing one would fabricate. Rows whose
        venue sequence was already emitted (the poll windows overlap)
        are skipped so the tape never replays a tick."""
        if not isinstance(payload, dict):
            raise MoomooProtocolError(f"rt_ticker payload must be an object, got {payload!r}")
        code = payload.get("code")
        if not isinstance(code, str):
            raise MoomooProtocolError(f"rt_ticker payload missing its code: {payload!r}")
        symbol = _split_code(code)[1]
        if symbol not in self._watchlist:
            raise MoomooProtocolError(f"rt_ticker payload for unsubscribed symbol {symbol!r}")
        instrument = self._instrument(symbol)
        trades = self._adapter.ticker_to_trades(instrument, payload)
        seen = self._seen_sequences.setdefault(symbol, set())
        updates: list[MarketUpdate] = []
        for trade in trades:
            if now - trade.timestamp > self._freshness.lag:
                continue  # stale venue tick — not current market data
            if trade.aggressor_side is None:
                continue  # documented neutral tick: no side to claim
            if trade.venue_sequence is not None:
                if trade.venue_sequence in seen:
                    continue
                seen.add(trade.venue_sequence)
            updates.append(
                self._update(
                    symbol,
                    UpdateKind.TRADE,
                    trade.timestamp,
                    now,
                    {
                        "price": trade.price,
                        "size": trade.quantity,
                        "side": trade.aggressor_side.value,
                    },
                    sequence=trade.venue_sequence,
                )
            )
        return updates

    def _subscribe_message(self, spec: dict) -> dict:
        """OpenD has no wire envelope: the subscription spec itself is
        the message (the transport collects the codes to poll)."""
        return spec

    def resync(self, now: datetime) -> list[MarketUpdate]:
        """The poll covers the reconnect window (the next cycle fetches
        the full surface); nothing to backfill."""
        return []

    def on_disconnect(self, now: datetime) -> list[GapFinding]:
        self._seen_sequences = {}
        # stop the poll task while the pump is out — otherwise it would
        # keep streaming frames into a wire the supervisor no longer
        # drains, and the reconnect's connect() would double-poll behind
        # a fresh task.
        self._transport.close()
        return super().on_disconnect(now)
