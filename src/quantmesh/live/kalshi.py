"""Kalshi read-only venue supervisor (iteration 0015 Phase E, ADR-0014).

Drives the public trade-api WebSocket v2
(``wss://api.elections.kalshi.com/trade-api/ws/v2``): one socket, one
subscription per watchlist ticker over three channels at once —
``market`` (last price, volume, open interest), ``orderbook_delta``
(the two bid ladders) and ``trades``. The subscribe envelope is
Kalshi's own (``{"id": n, "cmd": "subscribe", "params": {...}}``),
via the protocol's overridable ``_subscribe_message`` hook.

The book is maintained as two cents-keyed bid ladders (YES bids at
YES prices, NO bids at NO prices — the venue's own model, the same
one the M6 adapter parses). YES asks are the complement of NO bids
(the docs' rule: a NO bid at q implies a YES ask at 1 - q), so the
normalized QUOTE is ``(best YES bid, 1 - best NO bid)`` in dollars
and the ask L2 ladder is the NO ladder mirrored — ascending in
derived price, levels at or below zero skipped (a NO bid at $1.00
carries no tradeable YES ask depth).

The initial book state comes from the REST boundary
(``KalshiBookSource`` → ``KalshiOrderbook``) on *every* open —
including the first — because ``orderbook_delta`` frames only make
sense against the snapshot they mutate: applying removals to an
empty local book is a protocol error, so the supervisor refuses to
start streaming deltas without its initial state. Deltas apply as
changes (positive adds/updates, negative removes, counts clamped at
zero); a removal of a level the local state never saw means the
state has diverged from the venue and raises ``KalshiProtocolError``
— the reconnect/backoff heals it with a fresh REST snapshot. Prices
normalize to dollars in [0, 1]; nothing on this path can trade.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from quantmesh.domain.models import Venue
from quantmesh.kalshi.wire import KalshiOrderbook, parse_orderbook
from quantmesh.live.contract import MarketUpdate, Provenance, UpdateKind
from quantmesh.live.supervisor import GapFinding, VenueSupervisor

__all__ = ["KalshiProtocolError", "KalshiVenueSupervisor", "KalshiBookSource"]

TRADE_API_WS_URL = "wss://api.elections.kalshi.com/trade-api/ws/v2"
# The three channels one subscription carries; the ticker is bound per
# subscription so the watchlist and the wire stay one-to-one.
KALSHI_CHANNELS = ["market", "orderbook_delta", "trades"]


class KalshiProtocolError(ValueError):
    """A frame that does not match the documented trade-api wire."""


class KalshiBookSource(Protocol):
    """The REST book boundary: one market's two bid ladders, parsed."""

    def orderbook(self, ticker: str) -> KalshiOrderbook: ...


class KalshiOrderbookSource:
    """Raw-wire adapter: the M6 transport payload → parsed orderbook."""

    def __init__(self, transport) -> None:
        self._transport = transport

    def orderbook(self, ticker: str) -> KalshiOrderbook:
        return parse_orderbook(self._transport.orderbook(ticker))


def _frame_time(frame: dict) -> datetime:
    """The envelope's microsecond epoch timestamp, fail-closed."""
    raw = frame.get("ts")
    if not isinstance(raw, int):
        raise KalshiProtocolError(f"kalshi frame missing an integer ts: {raw!r}")
    return datetime.fromtimestamp(raw / 1_000_000, tz=UTC)


def _cents(raw: object, where: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise KalshiProtocolError(f"{where}: not an integer: {raw!r}")
    return raw


def _dollars(cents: int, where: str) -> float:
    if not 0 <= cents <= 100:
        raise KalshiProtocolError(f"{where}: cents outside [0, 100]: {cents}")
    return cents / 100


class KalshiVenueSupervisor(VenueSupervisor):
    """Three-channel supervisor for a watchlist of Kalshi tickers.

    ``book_source`` is the REST boundary the initial book state comes
    from (drills inject a stub; the live ``--live`` assembly wires
    ``KalshiOrderbookSource`` over the public M6 transport — explicit
    construction only, no registry, no credentials).
    """

    def __init__(
        self,
        transport,
        *,
        book_source: KalshiBookSource | None = None,
        lag: timedelta = timedelta(seconds=30),
        stale: timedelta = timedelta(seconds=90),
        max_buffered: int = 1000,
    ) -> None:
        super().__init__(transport, lag=lag, stale=stale, max_buffered=max_buffered)
        self._book_source = book_source
        self._subscribe_id = 0
        self._books: dict[str, dict[str, dict[int, float]]] = {}
        # Tickers whose REST snapshot has been applied; deltas only
        # apply against the seeded state (see resync).
        self._seeded: set[str] = set()

    @property
    def venue(self) -> Venue:
        return Venue.KALSHI

    def specs(self, watchlist: list[str]) -> dict[str, dict]:
        """One ticker-bound subscription over all three channels."""
        return {
            ticker: {"channels": KALSHI_CHANNELS, "ticker": ticker}
            for ticker in watchlist
        }

    def _subscribe_message(self, spec: dict) -> dict:
        self._subscribe_id += 1
        return {"id": self._subscribe_id, "cmd": "subscribe", "params": spec}

    # -- wire ---------------------------------------------------------------

    def _ticker(self, frame: dict) -> str:
        ticker = frame.get("ticker")
        if not isinstance(ticker, str) or not ticker:
            raise KalshiProtocolError(f"kalshi frame missing a ticker: {ticker!r}")
        if ticker not in self._subscribed:
            raise KalshiProtocolError(f"kalshi frame for unsubscribed ticker {ticker!r}")
        return ticker

    def dispatch(self, frame: object, now: datetime) -> list[MarketUpdate]:
        if not isinstance(frame, dict):
            raise KalshiProtocolError(f"kalshi frame must be an object, got {frame!r}")
        kind = frame.get("type")
        if kind == "market":
            return self._on_market(frame, now)
        if kind == "orderbook_delta":
            return self._on_orderbook_delta(frame, now)
        if kind == "trade":
            return self._on_trade(frame, now)
        raise KalshiProtocolError(f"unknown kalshi frame type {kind!r}")

    def _on_market(self, frame: dict, now: datetime) -> list[MarketUpdate]:
        """Market-channel metrics: last price, volume, open interest.

        The message carries more fields than the normalized surface
        (sizes, event metadata); the documented core is normalized,
        the rest is not part of the ADR-0014 contract and is ignored.
        """
        ticker = self._ticker(frame)
        ts = _frame_time(frame)
        msg = frame.get("msg")
        if not isinstance(msg, dict):
            raise KalshiProtocolError(f"market {ticker}: msg must be an object")
        payload: dict[str, object] = {
            "last": _dollars(
                _cents(msg.get("last_price"), f"market {ticker} last_price"),
                f"market {ticker} last_price",
            )
        }
        for key in ("volume", "open_interest"):
            if key in msg:
                value = msg[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise KalshiProtocolError(f"market {ticker}: {key} not numeric: {value!r}")
                payload[key] = value
        return [self._update(ticker, UpdateKind.METRICS, ts, now, payload)]

    def _on_orderbook_delta(self, frame: dict, now: datetime) -> list[MarketUpdate]:
        """Apply a delta batch to the ticker's two bid ladders and
        re-emit the quote + both L2 sides from the new state."""
        ticker = self._ticker(frame)
        ts = _frame_time(frame)
        msg = frame.get("msg")
        if not isinstance(msg, dict):
            raise KalshiProtocolError(f"orderbook_delta {ticker}: msg must be an object")
        if ticker not in self._seeded:
            # Deltas only mutate a seeded book; without the REST
            # initial state they would accumulate a partial ladder and
            # a removal of an unseen level would kill the socket. The
            # snapshot arrives in on_open's resync — until then the
            # surface stays absent, never partial.
            return []
        side = msg.get("side")
        if side not in ("yes", "no"):
            raise KalshiProtocolError(
                f"orderbook_delta {ticker}: side must be 'yes' or 'no', got {side!r}"
            )
        ladder = self._books.setdefault(ticker, {"yes": {}, "no": {}})[side]
        delta = msg.get("delta")
        if not isinstance(delta, list) or not delta:
            raise KalshiProtocolError(f"orderbook_delta {ticker}: no delta list")
        for index, entry in enumerate(delta):
            where = f"orderbook_delta {ticker}[{index}]"
            if not isinstance(entry, dict):
                raise KalshiProtocolError(f"{where}: expected an object")
            price = _cents(entry.get("price"), f"{where}.price")
            count = _cents(entry.get("count"), f"{where}.count")
            if price in ladder:
                updated = ladder[price] + count
                if updated <= 0:
                    del ladder[price]
                else:
                    ladder[price] = updated
            elif count > 0:
                ladder[price] = count
            else:
                raise KalshiProtocolError(
                    f"{where}: removal of a level the local book never saw "
                    "(book state diverged from the venue)"
                )
        return self._book_updates(ticker, ts, now)

    def _on_trade(self, frame: dict, now: datetime) -> list[MarketUpdate]:
        """One executed trade: the taker's side names the outcome they
        bought — buying YES is a buy, buying NO is a sell (M6 rule)."""
        ticker = self._ticker(frame)
        msg = frame.get("msg")
        if not isinstance(msg, dict):
            raise KalshiProtocolError(f"trade {ticker}: msg must be an object")
        side = msg.get("taker_side")
        if side not in ("yes", "no"):
            raise KalshiProtocolError(
                f"trade {ticker}: taker_side must be 'yes' or 'no', got {side!r}"
            )
        where = f"trade {ticker}"
        created = msg.get("created_time")
        if not isinstance(created, int):
            raise KalshiProtocolError(f"{where}: created_time not an integer: {created!r}")
        ts = datetime.fromtimestamp(created / 1_000_000, tz=UTC)
        price_cents = _cents(
            msg.get("yes_price" if side == "yes" else "no_price"),
            f"{where} price",
        )
        count = _cents(msg.get("count"), f"{where}.count")
        payload = {
            "price": _dollars(price_cents, f"{where}.price"),
            "size": count,
            "side": "buy" if side == "yes" else "sell",
        }
        return [self._update(ticker, UpdateKind.TRADE, ts, now, payload)]

    # -- book state → normalized surface -------------------------------------

    def _book_updates(
        self, ticker: str, ts: datetime, now: datetime
    ) -> list[MarketUpdate]:
        updates: list[MarketUpdate] = []
        ladder = self._books.setdefault(ticker, {"yes": {}, "no": {}})
        yes_prices = sorted(ladder["yes"], reverse=True)
        no_prices = sorted(ladder["no"], reverse=True)
        if yes_prices and no_prices:
            updates.append(
                self._update(
                    ticker,
                    UpdateKind.L2_SNAPSHOT,
                    ts,
                    now,
                    {
                        "side": "bid",
                        "levels": [
                            [_dollars(p, f"{ticker} yes bid"), ladder["yes"][p]]
                            for p in yes_prices
                        ],
                    },
                )
            )
            ask_levels = [
                [1.0 - _dollars(p, f"{ticker} no bid"), ladder["no"][p]]
                for p in no_prices
            ]
            ask_levels = [level for level in ask_levels if level[0] > 0]
            if ask_levels:
                updates.append(
                    self._update(
                        ticker,
                        UpdateKind.L2_SNAPSHOT,
                        ts,
                        now,
                        {"side": "ask", "levels": ask_levels},
                    )
                )
            best_yes = yes_prices[0]
            best_no = no_prices[0]
            ask = 1.0 - _dollars(best_no, f"{ticker} no bid")
            if ask > _dollars(best_yes, f"{ticker} yes bid"):
                # A derived ask at or below the best YES bid carries no
                # tradeable spread (M6's rule for derived asks at zero);
                # the book still renders, the quote stays absent until
                # the venue's ladders uncross.
                updates.append(
                    self._update(
                        ticker,
                        UpdateKind.QUOTE,
                        ts,
                        now,
                        {
                            "bid": _dollars(best_yes, f"{ticker} yes bid"),
                            "ask": ask,
                            "bid_size": ladder["yes"][best_yes],
                            "ask_size": ladder["no"][best_no],
                        },
                    )
                )
        return updates

    def _update(
        self,
        ticker: str,
        kind: UpdateKind,
        ts: datetime,
        now: datetime,
        payload: dict[str, object],
    ) -> MarketUpdate:
        return MarketUpdate(
            venue=self.venue,
            instrument=ticker,
            kind=kind,
            provenance=Provenance.REAL,
            data_time=ts,
            received_at=now,
            sequence=None,
            payload=payload,
        )

    # -- recovery -----------------------------------------------------------

    def on_open(self, now: datetime, *, reconnected: bool = False) -> list[GapFinding]:
        findings = super().on_open(now, reconnected=reconnected)
        if not reconnected:
            # Deltas stream immediately after subscribe; the book
            # needs its REST initial state before the first removal
            # can apply. On reconnect ``super().on_open`` already ran
            # resync (which refetches the snapshot over the dark
            # window) — this only seeds the first open.
            for update in self.resync(now):
                self._push(update)
            findings.extend(self._gap_pending)
            self._gap_pending = []
        return findings

    def resync(self, now: datetime) -> list[MarketUpdate]:
        """REST book snapshot per ticker: the delta state's seed."""
        if self._book_source is None:
            self._gap_pending.append(
                GapFinding("kalshi", "no REST book source; orderbook deltas cannot apply")
            )
            return []
        updates: list[MarketUpdate] = []
        for ticker in self._watchlist:
            try:
                book = self._book_source.orderbook(ticker)
            except Exception as error:
                self._gap_pending.append(
                    GapFinding(ticker, f"book re-sync unavailable: {error}")
                )
                continue
            self._seeded.add(ticker)
            self._books[ticker] = {
                "yes": {
                    round(level.price * 100): level.size
                    for level in book.yes_dollars
                    if level.size > 0
                },
                "no": {
                    round(level.price * 100): level.size
                    for level in book.no_dollars
                    if level.size > 0
                },
            }
            updates.extend(self._book_updates(ticker, now, now))
        return updates
