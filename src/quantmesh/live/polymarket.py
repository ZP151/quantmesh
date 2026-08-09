"""Polymarket read-only venue supervisor (iteration 0015 Phase E,
ADR-0014).

Drives the public CLOB market channel
(``wss://ws-subscriptions-clob.polymarket.com/ws/market``), one
``{"type": "market", "assets_ids": [token]}`` subscription per
watchlist token. Two documented frame kinds carry the surface:

- ``book`` — a full snapshot of the token's book: both L2 sides and
  the touch QUOTE (with sizes from the best levels);
- ``price_change`` — touch price moves **without sizes**: a QUOTE
  with bid/ask only (the contract makes sizes optional), with sizes
  composed from the last known book state when it exists.

``tick_size_change`` is a known metadata frame that changes nothing
on the normalized surface (the tick size is not part of the ADR-0014
contract), so it is accepted and produces no update; any other frame
kind — and any frame for an unsubscribed asset — raises
``PolymarketProtocolError`` (fail-closed: an unrecognized wire is a
real defect, not a silence).

Depth at connect and after reconnect comes from the REST book
boundary (``PolymarketBookSource`` → ``ClobBook``), the same public
``GET /book`` surface the M6 connector uses; without one, the WS
book frames fill depth on their own cadence and the reconnect finding
is reported venue-level. Prices normalize to dollars in [0, 1] (the
venue's own price space); implied probability on the board is the
mid, scaled to percent by the board itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from quantmesh.domain.models import Venue
from quantmesh.live.contract import MarketUpdate, Provenance, UpdateKind
from quantmesh.live.supervisor import GapFinding, VenueSupervisor
from quantmesh.polymarket.wire import ClobBook, parse_clob_book

__all__ = ["PolymarketProtocolError", "PolymarketVenueSupervisor", "PolymarketBookSource"]

MARKET_CHANNEL_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"


class PolymarketProtocolError(ValueError):
    """A frame that does not match the documented market channel."""


class PolymarketBookSource(Protocol):
    """The REST book boundary: one token's order book, parsed."""

    def clob_book(self, token_id: str) -> ClobBook: ...


class ClobBookSource:
    """Raw-wire adapter: ``PolyRestTransport`` payload → parsed book.

    The parsed book's own asset id must match the requested token —
    a book for the wrong market is a real wire error, and swallowing
    it would fabricate depth for the wrong instrument.
    """

    def __init__(self, transport) -> None:
        self._transport = transport

    def clob_book(self, token_id: str) -> ClobBook:
        book = parse_clob_book(self._transport.clob_book(token_id))
        if book.asset_id != token_id:
            raise PolymarketProtocolError(
                f"book asset {book.asset_id!r} does not match requested token {token_id!r}"
            )
        return book


def _frame_time(frame: dict) -> datetime:
    """The market channel's microsecond epoch timestamp, fail-closed."""
    raw = frame.get("timestamp")
    if isinstance(raw, str) and raw.isdigit():
        raw = int(raw)
    if not isinstance(raw, int):
        raise PolymarketProtocolError(f"market frame missing an integer timestamp: {raw!r}")
    return datetime.fromtimestamp(raw / 1_000_000, tz=UTC)


def _number(raw: object, where: str) -> float:
    if isinstance(raw, str):
        try:
            raw = float(raw)
        except ValueError as error:
            raise PolymarketProtocolError(f"{where}: not a number: {raw!r}") from error
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise PolymarketProtocolError(f"{where}: not a number: {raw!r}")
    value = float(raw)
    if value != value or value in (float("inf"), float("-inf")):
        raise PolymarketProtocolError(f"{where}: not a finite number: {raw!r}")
    return value


def _levels(raw: object, where: str) -> list[tuple[float, float]]:
    """``[{"price": "...", "size": "..."}]`` → deduplicated levels.

    Levels of zero size carry no liquidity and are dropped (snapshot
    semantics); repeated prices keep the last occurrence — the frame
    is a snapshot, so the newest size wins. The contract then sees a
    strictly monotonic ladder.
    """
    if not isinstance(raw, list):
        raise PolymarketProtocolError(f"{where}: expected a list of levels")
    seen: dict[float, float] = {}
    for index, entry in enumerate(raw):
        level_where = f"{where}[{index}]"
        if not isinstance(entry, dict):
            raise PolymarketProtocolError(f"{level_where}: expected an object pair")
        price = _number(entry.get("price"), f"{level_where}.price")
        if not 0 <= price <= 1:
            raise PolymarketProtocolError(f"{level_where}.price outside [0, 1]: {price}")
        size = _number(entry.get("size"), f"{level_where}.size")
        if size < 0:
            raise PolymarketProtocolError(f"{level_where}.size negative: {size}")
        if size > 0:
            seen[price] = size
    return sorted(seen.items(), reverse=True)  # best-first; caller orients


class PolymarketVenueSupervisor(VenueSupervisor):
    """Market-channel supervisor for a watchlist of CLOB token ids.

    ``book_source`` is the optional REST boundary; drills inject a
    stub, the live ``--live`` assembly wires ``ClobBookSource`` over
    the keyless ``SdkPolyTransport`` (explicit construction only —
    no registry, no credentials).
    """

    def __init__(
        self,
        transport,
        *,
        book_source: PolymarketBookSource | None = None,
        lag: timedelta = timedelta(seconds=30),
        stale: timedelta = timedelta(seconds=90),
        max_buffered: int = 1000,
    ) -> None:
        super().__init__(transport, lag=lag, stale=stale, max_buffered=max_buffered)
        self._book_source = book_source
        self._book_cache: dict[str, dict[str, float]] = {}
        self._touch: dict[str, dict[str, float]] = {}

    @property
    def venue(self) -> Venue:
        return Venue.POLYMARKET

    def specs(self, watchlist: list[str]) -> dict[str, dict]:
        """One ``{"type": "market", "assets_ids": [token]}`` per token."""
        return {token: {"type": "market", "assets_ids": [token]} for token in watchlist}

    # -- wire ---------------------------------------------------------------

    def _asset(self, frame: dict) -> str:
        asset = frame.get("asset_id")
        if not isinstance(asset, str) or not asset:
            raise PolymarketProtocolError(f"market frame missing an asset_id: {asset!r}")
        if asset not in self._subscribed:
            raise PolymarketProtocolError(
                f"market frame for unsubscribed asset {asset!r}"
            )
        return asset

    def dispatch(self, frame: object, now: datetime) -> list[MarketUpdate]:
        if not isinstance(frame, dict):
            raise PolymarketProtocolError(f"market frame must be an object, got {frame!r}")
        kind = frame.get("event_type")
        if kind == "book":
            return self._on_book(frame, now)
        if kind == "price_change":
            return self._on_price_change(frame, now)
        if kind == "tick_size_change":
            # Known metadata frame; the tick size is not part of the
            # ADR-0014 contract, so it changes nothing we emit.
            return []
        raise PolymarketProtocolError(f"unknown market event_type {kind!r}")

    def _on_book(self, frame: dict, now: datetime) -> list[MarketUpdate]:
        asset = self._asset(frame)
        ts = _frame_time(frame)
        bids = _levels(frame.get("bids"), f"book {asset} bids")
        asks = _levels(frame.get("asks"), f"book {asset} asks")
        updates: list[MarketUpdate] = []
        if bids:
            bid_price, bid_size = bids[0]
            self._touch[asset] = {**self._touch.get(asset, {}), "bid": bid_price}
            updates.append(
                self._update(
                    asset,
                    UpdateKind.L2_SNAPSHOT,
                    ts,
                    now,
                    {"side": "bid", "levels": list(bids)},
                )
            )
        if asks:
            ask_price, ask_size = asks[-1]
            self._touch[asset] = {**self._touch.get(asset, {}), "ask": ask_price}
            updates.append(
                self._update(
                    asset,
                    UpdateKind.L2_SNAPSHOT,
                    ts,
                    now,
                    {"side": "ask", "levels": list(reversed(asks))},
                )
            )
        if bids and asks:
            self._book_cache[asset] = {
                "bid": bid_price,
                "bid_size": bid_size,
                "ask": ask_price,
                "ask_size": ask_size,
            }
            updates.append(self._quote(asset, ts, now))
        return updates

    def _on_price_change(self, frame: dict, now: datetime) -> list[MarketUpdate]:
        asset = self._asset(frame)
        ts = _frame_time(frame)
        changes = frame.get("price_changes")
        if not isinstance(changes, list) or not changes:
            raise PolymarketProtocolError(f"price_change {asset}: no price_changes list")
        touch: dict[str, float] = dict(self._touch.get(asset, {}))
        for index, change in enumerate(changes):
            where = f"price_change {asset}[{index}]"
            if not isinstance(change, dict):
                raise PolymarketProtocolError(f"{where}: expected an object")
            price = _number(change.get("price"), f"{where}.price")
            if not 0 <= price <= 1:
                raise PolymarketProtocolError(f"{where}.price outside [0, 1]: {price}")
            side = change.get("side")
            if side == "BUY":
                touch["bid"] = price
            elif side == "SELL":
                touch["ask"] = price
            else:
                raise PolymarketProtocolError(f"{where}: unknown side {side!r}")
        if "bid" not in touch or "ask" not in touch:
            # The venue's own examples show single-sided price changes;
            # the side is remembered, but nothing is quoted until the
            # touch is complete (a quote would be a fabrication).
            self._touch[asset] = touch
            return []
        if touch["ask"] < touch["bid"]:
            raise PolymarketProtocolError(
                f"price_change {asset}: ask {touch['ask']} below "
                f"bid {touch['bid']}"
            )
        self._touch[asset] = touch
        return [self._quote(asset, ts, now)]

    def _quote(self, asset: str, ts: datetime, now: datetime) -> MarketUpdate:
        """QUOTE from the touch; sizes only when the book state knows them."""
        touch = self._touch[asset]
        payload: dict[str, float] = {"bid": touch["bid"], "ask": touch["ask"]}
        cached = self._book_cache.get(asset)
        if cached is not None:
            payload["bid_size"] = cached["bid_size"]
            payload["ask_size"] = cached["ask_size"]
        return self._update(
            asset, UpdateKind.QUOTE, ts, now, payload
        )

    def _update(
        self,
        asset: str,
        kind: UpdateKind,
        ts: datetime,
        now: datetime,
        payload: dict[str, object],
    ) -> MarketUpdate:
        return MarketUpdate(
            venue=self.venue,
            instrument=asset,
            kind=kind,
            provenance=Provenance.REAL,
            data_time=ts,
            received_at=now,
            sequence=None,
            payload=payload,
        )

    # -- recovery -----------------------------------------------------------

    def resync(self, now: datetime) -> list[MarketUpdate]:
        """REST book snapshot per token: depth at connect/reconnect."""
        if self._book_source is None:
            self._gap_pending.append(
                GapFinding("polymarket", "no REST book source; reconnect gaps reported only")
            )
            return []
        updates: list[MarketUpdate] = []
        for token in self._watchlist:
            try:
                book = self._book_source.clob_book(token)
            except Exception as error:
                self._gap_pending.append(GapFinding(token, f"book re-sync unavailable: {error}"))
                continue
            if not book.bids or not book.asks:
                # An empty snapshot has no depth to bless; keeping the
                # old book state would mislabel it as current.
                self._gap_pending.append(GapFinding(token, "book re-sync returned no levels"))
                continue
            ts = book.timestamp
            self._touch[token] = {
                "bid": book.bids[0].price,
                "ask": book.asks[0].price,
            }
            self._book_cache[token] = {
                "bid": book.bids[0].price,
                "bid_size": book.bids[0].size,
                "ask": book.asks[0].price,
                "ask_size": book.asks[0].size,
            }
            updates.append(
                self._update(
                    token,
                    UpdateKind.L2_SNAPSHOT,
                    ts,
                    now,
                    {
                        "side": "bid",
                        "levels": [(level.price, level.size) for level in book.bids],
                    },
                )
            )
            updates.append(
                self._update(
                    token,
                    UpdateKind.L2_SNAPSHOT,
                    ts,
                    now,
                    {
                        "side": "ask",
                        "levels": [(level.price, level.size) for level in book.asks],
                    },
                )
            )
            updates.append(self._quote(token, ts, now))
        return updates
