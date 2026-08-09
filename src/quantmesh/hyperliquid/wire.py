"""Hyperliquid wire-shape parsing (M5, issue #29, Phase A).

Payload contracts are derived from the pinned hyperliquid-python-sdk
submodule source, not from docs:

- ``candleSnapshot`` rows: ``{"T", "c", "h", "i", "l", "n", "o", "s",
  "t", "v"}`` — OHLCV are float *strings*, ``t``/``T`` are open/close
  unix milliseconds, ``i`` is the interval, ``s`` the coin.
- ``l2Book`` responses: ``{"coin", "levels": [[{n, px, sz}, ...], ...],
  "time"}`` — ``levels[0]`` bids, ``levels[1]`` asks; ``px``/``sz`` are
  float strings.
- WS ``trades`` frames: ``{"coin", "px", "sz", "side": "A"|"B", "time",
  "tid", "users"}``.
- ``fundingHistory`` rows: ``{"coin", "fundingRate", "premium", "time"}``
  with float-string rates.
- WS ``allMids`` frames: ``{"mids": {coin: float string}, "time"}``.
- ``meta``/``spotMeta`` universes: ``{"universe": [{name, szDecimals,
  maxLeverage, onlyIsolated, ...}]}``.

Every parser fails closed: a missing key, a non-numeric price, an
unknown side, a symbol or interval that does not match the request, or
a candle whose close does not land exactly one interval after its open
raises ``HyperliquidProtocolError`` instead of producing a silently
wrong model. Unambiguous shapes (``s`` matches the instrument symbol,
``T - t`` equals the interval) are the only thing that may pass.
"""

import math
from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError, model_validator

from quantmesh.domain.market_data import (
    Bar,
    DepthLevel,
    OrderBook,
    TradeEvent,
    interval_to_timedelta,
)
from quantmesh.domain.models import Instrument, Side
from quantmesh.hyperliquid.errors import HyperliquidProtocolError

__all__ = [
    "FundingRate",
    "PerpMeta",
    "SpotPair",
    "parse_candle",
    "parse_candle_frame",
    "parse_l2_book",
    "parse_l2_book_frame",
    "parse_trades",
    "parse_trades_frame",
    "parse_funding",
    "parse_all_mids",
    "parse_meta",
    "parse_spot_meta",
    "ms_to_utc",
]

_SIDES = {"A": Side.BUY, "B": Side.SELL}


def ms_to_utc(millis: object) -> datetime:
    """Unix milliseconds → aware UTC; ints and numeric strings accepted."""
    if isinstance(millis, bool) or not isinstance(millis, (int, str)):
        raise HyperliquidProtocolError(f"time must be unix milliseconds, got {millis!r}")
    try:
        value = int(millis)
    except (TypeError, ValueError) as error:
        raise HyperliquidProtocolError(f"time must be unix milliseconds, got {millis!r}") from error
    if value < 0:
        raise HyperliquidProtocolError(f"time must not be negative, got {value}")
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def _num(value: object, field: str) -> float:
    """Float-string or numeric → float; NaN/Infinity and junk fail closed."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise HyperliquidProtocolError(f"{field} must be numeric, got {value!r}")
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError as error:
            raise HyperliquidProtocolError(
                f"{field} must be numeric, got {value!r}"
            ) from error
    if not math.isfinite(value):
        raise HyperliquidProtocolError(f"{field} must be finite, got {value!r}")
    return float(value)


def _mapping(row: object, what: str) -> dict:
    if not isinstance(row, dict):
        raise HyperliquidProtocolError(f"{what} must be an object, got {type(row).__name__}")
    return row


def _require_symbol(row: dict, instrument: Instrument) -> None:
    symbol = row.get("s", row.get("coin"))
    if symbol != instrument.symbol:
        raise HyperliquidProtocolError(
            f"payload symbol {symbol!r} does not match instrument {instrument.symbol!r}"
        )


def parse_candle(row: object, instrument: Instrument, *, interval: str) -> Bar:
    """One ``candleSnapshot`` row → canonical ``Bar`` (open time ``t``)."""
    row = _mapping(row, "candle")
    if row.get("i") != interval:
        raise HyperliquidProtocolError(
            f"candle interval {row.get('i')!r} does not match requested {interval!r}"
        )
    _require_symbol(row, instrument)
    step = interval_to_timedelta(interval)
    open_ms, close_ms = row.get("t"), row.get("T")
    try:
        open_dt = ms_to_utc(open_ms)
        close_dt = ms_to_utc(close_ms)
    except HyperliquidProtocolError as error:
        raise HyperliquidProtocolError(f"candle time: {error}") from error
    if close_dt - open_dt != step:
        raise HyperliquidProtocolError(
            f"candle {instrument.symbol!r} {interval} spans {close_dt - open_dt}, "
            f"expected exactly {step}"
        )
    try:
        return Bar(
            instrument=instrument,
            timestamp=open_dt,
            interval=interval,
            open=_num(row.get("o"), "open"),
            high=_num(row.get("h"), "high"),
            low=_num(row.get("l"), "low"),
            close=_num(row.get("c"), "close"),
            volume=_num(row.get("v"), "volume"),
        )
    except ValidationError as error:
        raise HyperliquidProtocolError(f"candle values invalid: {error}") from error


def parse_l2_book(row: object, instrument: Instrument) -> OrderBook:
    """One ``l2Book`` payload → canonical ``OrderBook`` (bids/asks arrays)."""
    row = _mapping(row, "l2Book")
    _require_symbol(row, instrument)
    levels = row.get("levels")
    if not isinstance(levels, list) or len(levels) < 2:
        raise HyperliquidProtocolError(
            f"l2Book for {instrument.symbol!r} needs at least 2 level arrays"
        )
    if len(levels) > 2:
        raise HyperliquidProtocolError(
            f"l2Book for {instrument.symbol!r} has {len(levels)} level arrays; "
            "the wire contract we pin has exactly 2 (bids, asks)"
        )

    def parse_side(side_rows: object, side: str) -> list[DepthLevel]:
        if not isinstance(side_rows, list):
            raise HyperliquidProtocolError(f"{side} levels must be a list")
        levels = []
        for level_row in side_rows:
            level = _mapping(level_row, f"{side} level")
            if not isinstance(level.get("n"), int):
                raise HyperliquidProtocolError(f"{side} level count must be an int")
            levels.append(
                DepthLevel(
                    price=_num(level.get("px"), f"{side} price"),
                    quantity=_num(level.get("sz"), f"{side} size"),
                )
            )
        return levels

    try:
        return OrderBook(
            instrument=instrument,
            timestamp=ms_to_utc(row.get("time")),
            bids=parse_side(levels[0], "bid"),
            asks=parse_side(levels[1], "ask"),
        )
    except HyperliquidProtocolError:
        raise
    except ValidationError as error:
        raise HyperliquidProtocolError(f"l2Book values invalid: {error}") from error


def _parse_trade(row: object, instrument: Instrument) -> TradeEvent:
    row = _mapping(row, "trade")
    _require_symbol(row, instrument)
    side = row.get("side")
    if side not in _SIDES:
        raise HyperliquidProtocolError(
            f"unknown trade side {side!r} for {instrument.symbol!r} (expected 'A' or 'B')"
        )
    try:
        return TradeEvent(
            instrument=instrument,
            timestamp=ms_to_utc(row.get("time")),
            price=_num(row.get("px"), "price"),
            quantity=_num(row.get("sz"), "size"),
            aggressor_side=_SIDES[side],
            venue_sequence=row.get("tid"),
        )
    except HyperliquidProtocolError:
        raise
    except ValidationError as error:
        raise HyperliquidProtocolError(f"trade values invalid: {error}") from error


def parse_trades(rows: object, instrument: Instrument) -> list[TradeEvent]:
    """A REST/WS trades list → canonical ``TradeEvent`` rows."""
    if not isinstance(rows, list):
        raise HyperliquidProtocolError(f"trades must be a list, got {type(rows).__name__}")
    return [_parse_trade(row, instrument) for row in rows]


def parse_candle_frame(frame: object, instrument: Instrument, *, interval: str) -> Bar:
    """A WS ``candle`` frame's data payload → canonical ``Bar``.

    The WS candle data has the same keys as the REST row (``t``/``T``/
    ``s``/``i``/``o``/``c``/``h``/``l``/``v``/``n``), so the REST parser
    applies unchanged.
    """
    return parse_candle(_mapping(frame, "candle frame"), instrument, interval=interval)


def parse_l2_book_frame(frame: object, instrument: Instrument) -> OrderBook:
    """A WS ``l2Book`` frame's data payload → canonical ``OrderBook``.

    Hyperliquid pushes full level arrays on every update (snapshots, not
    deltas), so the REST parser applies unchanged.
    """
    return parse_l2_book(_mapping(frame, "l2Book frame"), instrument)


def parse_trades_frame(frame: object, instrument: Instrument) -> list[TradeEvent]:
    """A WS ``trades`` frame's data payload → canonical ``TradeEvent`` rows.

    The supervisor unwraps the envelope and hands over the ``data`` list
    (like ``parse_candle_frame`` hands over its data object); an empty
    list is a valid frame (the SDK skips it for dispatch) and returns an
    empty result rather than failing.
    """
    return parse_trades(frame, instrument)


def parse_all_mids(frame: object) -> dict[str, float]:
    """A WS ``allMids`` frame's data payload → coin → mid price."""
    frame = _mapping(frame, "allMids frame")
    mids = frame.get("mids")
    if not isinstance(mids, dict):
        raise HyperliquidProtocolError("allMids payload must carry a 'mids' object")
    parsed: dict[str, float] = {}
    for coin, price in mids.items():
        parsed[str(coin)] = _num(price, f"mid price for {coin}")
    return parsed


def parse_bbo_frame(frame: object) -> dict[str, float]:
    """A WS ``bbo`` frame's data payload → normalized best bid/ask quote.

    Hyperliquid's BBO channel pushes one row per coin: ``{coin, time,
    bid, bidSz, ask, askSz}`` where sizes are USD notional. The
    supervisor normalizes this into the cockpit QUOTE contract.
    """
    row = _mapping(frame, "bbo frame")
    bid = _num(row.get("bid"), "bbo bid")
    ask = _num(row.get("ask"), "bbo ask")
    if ask < bid:
        raise HyperliquidProtocolError(f"bbo ask {ask} below bid {bid} for {row.get('coin')!r}")
    return {
        "bid": bid,
        "ask": ask,
        "bid_size": _num(row.get("bidSz"), "bbo bidSz"),
        "ask_size": _num(row.get("askSz"), "bbo askSz"),
    }


def parse_asset_ctx_map(frame: object) -> dict[str, dict[str, float]]:
    """A WS ``activeAssetCtx`` frame's data payload → coin → metrics.

    Hyperliquid pushes one map per frame: ``{coin: {funding, markPx,
    oraclePx, openInterest, premium, …}}``; only the fields the cockpit
    renders are kept, and every value must be numeric or the frame is
    rejected (fail-closed).
    """
    frame = _mapping(frame, "activeAssetCtx frame")
    parsed: dict[str, dict[str, float]] = {}
    for coin, ctx in frame.items():
        ctx = _mapping(ctx, f"activeAssetCtx row for {coin}")
        parsed[str(coin)] = {
            "funding_rate": _num(ctx.get("funding"), f"funding for {coin}"),
            "mark_price": _num(ctx.get("markPx"), f"markPx for {coin}"),
            "index_price": _num(ctx.get("oraclePx"), f"oraclePx for {coin}"),
            "open_interest": _num(ctx.get("openInterest"), f"openInterest for {coin}"),
        }
    return parsed


class FundingRate(BaseModel):
    """One funding-history row (canonical shape; venue-agnostic fields)."""

    coin: str
    rate: float
    premium: float
    timestamp: datetime

    @model_validator(mode="after")
    def timestamp_must_be_aware(self) -> "FundingRate":
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return self


def parse_funding(rows: object) -> list[FundingRate]:
    """``fundingHistory`` rows → canonical ``FundingRate`` rows."""
    if not isinstance(rows, list):
        raise HyperliquidProtocolError(f"funding must be a list, got {type(rows).__name__}")
    parsed = []
    for row in rows:
        row = _mapping(row, "funding row")
        try:
            parsed.append(
                FundingRate(
                    coin=str(row.get("coin")),
                    rate=_num(row.get("fundingRate"), "fundingRate"),
                    premium=_num(row.get("premium"), "premium"),
                    timestamp=ms_to_utc(row.get("time")),
                )
            )
        except HyperliquidProtocolError:
            raise
        except ValidationError as error:
            raise HyperliquidProtocolError(f"funding values invalid: {error}") from error
    return parsed


class PerpMeta(BaseModel):
    """One perpetual asset from the ``meta`` universe (Phase C risk input)."""

    name: str
    sz_decimals: int
    max_leverage: int | None = None
    only_isolated: bool = False


class SpotPair(BaseModel):
    """One spot pair from ``spotMeta``; ``name`` is the SDK coin (e.g. "BTC")."""

    name: str
    base: str
    quote: str


def parse_meta(payload: object) -> list[PerpMeta]:
    """``meta()`` universe → canonical perp metadata."""
    payload = _mapping(payload, "meta")
    universe = payload.get("universe")
    if not isinstance(universe, list):
        raise HyperliquidProtocolError("meta must carry a 'universe' list")
    parsed = []
    for row in universe:
        row = _mapping(row, "meta asset")
        try:
            parsed.append(
                PerpMeta(
                    name=str(row["name"]),
                    sz_decimals=int(row["szDecimals"]),
                    max_leverage=row.get("maxLeverage"),
                    only_isolated=bool(row.get("onlyIsolated", False)),
                )
            )
        except KeyError as error:
            raise HyperliquidProtocolError(f"meta asset missing key {error}") from error
        except ValidationError as error:
            raise HyperliquidProtocolError(f"meta values invalid: {error}") from error
    return parsed


def parse_spot_meta(payload: object) -> list[SpotPair]:
    """``spotMeta()`` universe → canonical spot pairs (token indices resolved)."""
    payload = _mapping(payload, "spotMeta")
    universe = payload.get("universe")
    tokens = payload.get("tokens")
    if not isinstance(universe, list) or not isinstance(tokens, list):
        raise HyperliquidProtocolError("spotMeta must carry 'universe' and 'tokens' lists")
    by_index = {}
    for token in tokens:
        token = _mapping(token, "spot token")
        by_index[token.get("index")] = str(token.get("name"))
    parsed = []
    for row in universe:
        row = _mapping(row, "spot pair")
        pair = row.get("tokens")
        if not isinstance(pair, list) or len(pair) != 2:
            raise HyperliquidProtocolError("spot pair must carry a 2-token 'tokens' list")
        base, quote = (by_index.get(index) for index in pair)
        if base is None or quote is None:
            raise HyperliquidProtocolError(f"spot pair references unknown token indices {pair}")
        parsed.append(SpotPair(name=str(row.get("name")), base=base, quote=quote))
    return parsed
