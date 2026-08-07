"""Kalshi trade-api v2 wire-shape parsing (M6, issue #35, Phase B).

Payload contracts are pinned to wire shapes recorded from the live
public API at ``https://api.elections.kalshi.com`` on 2026-08-08 plus
the endpoint/field contract at docs.kalshi.com — there is no
vendorable SDK authority (the legacy ``kalshi-python`` repo is
removed; modern SDKs are PyPI-generated from an unpublishable spec),
so the recorded fixtures themselves are the versioned authority
(ADR-0008 decision 2). The observed shapes:

- ``GET /events``: ``{"cursor": str, "events": [{event_ticker,
  title, sub_title, category, series_ticker, mutually_exclusive,
  collateral_return_type, strike_period, available_on_brokers,
  exchange_index, last_updated_ts (ISO), strike_date (ISO, optional),
  product_metadata (optional), settlement_sources: [{name, url}]}],
  "milestones": [...]}``.
- ``GET /events/{ticker}``: the event object **plus its markets** in
  one body — ``{"event": {...}, "markets": [...]}``.
- ``GET /markets``: ``{"cursor", "markets": [market objects]}``;
  ``GET /markets/{ticker}``: ``{"market": {...}}``. The market object
  carries ``ticker/event_ticker/title/status/market_type/result/
  rules_primary/rules_secondary/expiration_time/yes|no_bid|ask_dollars/
  yes|no_bid|ask_size_fp/last_price_dollars/volume_fp/price_ranges``
  plus timestamps. ``status`` is one of unopened/active/closed/
  settled/finalized (observed active and finalized); ``result`` is
  ``""`` or ``"yes"``/``"no"``; ``market_type`` is ``"binary"`` or
  ``"multicategorical"`` (the adapter refuses non-binary — Phase C
  probabilities are binary-payoff).
- ``GET /markets/{ticker}/orderbook``: ``{"orderbook_fp":
  {"yes_dollars": [[price, size], ...], "no_dollars": [...]}}``.
  Both ladders are resting **bids** on their own axis, listed
  **ascending worst-first** (the live wire contradicts the docs'
  "best to worst" claim — recorded wire wins; best levels are taken
  order-agnostically). YES asks are derived: a NO bid at price y
  implies a YES ask at 1 - y with the same count (the docs' own
  derivation rule). Verified against the market object at the same
  instant: best YES bid = max(yes_dollars) and best YES ask = 1 -
  max(no_dollars) matched the market's reported bid/ask exactly.
- ``GET /markets/trades?ticker=``: ``{"cursor", "trades": [{trade_id,
  ticker, count_fp, created_time (ISO), is_block_trade,
  taker_side/taker_outcome_side ("yes"/"no"), taker_book_side
  ("bid"/"ask"), yes_price_dollars, no_price_dollars}]}`` — the
  complementary prices always sum to 1. An unknown ticker returns an
  empty list, not an error. (The older ``/markets/{ticker}/trades``
  route 404s on the live server — documented divergence.)
- ``GET /series/{series}/markets/{ticker}/candlesticks``: ``{"candlesticks":
  [{end_period_ts (unix, the period END), open_interest_fp,
  volume_fp, price: {previous_dollars} or {open/high/low/close/mean/
  previous_dollars when the period traded}, yes_ask: {OHLC},
  yes_bid: {OHLC}}]}``. ``volume_fp`` is reported — Kalshi serves a
  genuine bar surface (unlike Polymarket). The bar-surface route is
  ``/series/{series}/markets/{ticker}/candlesticks``; the
  ``/markets/{ticker}/candlesticks`` route 404s.
- ``GET /series/{ticker}``: ``{"series": {series_ticker, category,
  fee_multiplier, fee_type, frequency, settlement_sources, ...}}``.
- Error shapes: 404s are ``{"error": {"code", "message"}}`` (e.g.
  "market not found"); 400 parameter validation is ``{"msg":
  "Parameter validation failed ..."}``; the migration host
  ``trading-api.kalshi.com`` answers a plain-text 401 ("API has been
  moved ...") and is refused at construction, never reached.

Every parser fails closed: a missing key, a non-string price or size,
a price outside [0, 1], a negative fp size, an out-of-order ladder or
candle series, a status/result/side value outside the pinned set, a
traded candlestick missing its OHLC, or complementary trade prices
that do not sum to 1 raises ``KalshiProtocolError`` instead of
producing a silently wrong model.
"""

import math
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from quantmesh.kalshi.errors import KalshiProtocolError

__all__ = [
    "KalshiEvent",
    "KalshiMarket",
    "KalshiMarketStatus",
    "KalshiOrderbook",
    "KalshiSeries",
    "KalshiTrade",
    "KalshiCandlestick",
    "KalshiPriceRange",
    "parse_events",
    "parse_event_bundle",
    "parse_markets",
    "parse_market",
    "parse_orderbook",
    "parse_trades",
    "parse_candlesticks",
    "parse_series",
]

_PRICE_TOLERANCE = 1e-6


def _protocol(message: str) -> KalshiProtocolError:
    return KalshiProtocolError(message)


def _require_error_free(payload: object, endpoint: str) -> None:
    """The venue speaks two recorded error shapes: 404s are
    ``{"error": {"code", "message"}}`` and parameter validation is
    ``{"msg": ...}``. Both become typed refusals carrying the server
    message — never a silent empty result."""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            raise _protocol(f"{endpoint} refused: {error['message']}")
        if isinstance(error, str):
            raise _protocol(f"{endpoint} refused: {error}")
        if isinstance(payload.get("msg"), str):
            raise _protocol(f"{endpoint} refused: {payload['msg']}")


def _parse_finite(value: object, where: str) -> float:
    if isinstance(value, bool):
        raise _protocol(f"{where}: boolean where a number is required")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise _protocol(f"{where}: {value!r} is not numeric") from error
    if not math.isfinite(parsed):
        raise _protocol(f"{where}: {value!r} is not finite")
    return parsed


def _parse_price(value: object, where: str) -> float:
    """A dollar price: a string like ``"0.7700"`` inside [0, 1]."""
    parsed = _parse_finite(value, where)
    if not 0.0 <= parsed <= 1.0:
        raise _protocol(f"{where}: price {parsed} outside [0, 1]")
    return parsed


def _parse_fp(value: object, where: str) -> float:
    """A fixed-point count string like ``"105025.00"`` (contracts)."""
    parsed = _parse_finite(value, where)
    if parsed < 0:
        raise _protocol(f"{where}: negative size {parsed}")
    return parsed


def _parse_iso(value: object, where: str) -> datetime:
    if not isinstance(value, str):
        raise _protocol(f"{where}: {value!r} is not an ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise _protocol(f"{where}: {value!r} is not an ISO timestamp") from error
    if parsed.tzinfo is None:
        raise _protocol(f"{where}: timestamp {value!r} is not timezone-aware")
    return parsed.astimezone(UTC)


def _parse_optional_iso(value: object, where: str) -> datetime | None:
    if value is None:
        return None
    return _parse_iso(value, where)


def _require_str(value: object, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise _protocol(f"{where}: expected a non-empty string, got {value!r}")
    return value


def _optional_str(value: object, where: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _protocol(f"{where}: expected a string, got {value!r}")
    return value


def _require_bool(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        raise _protocol(f"{where}: expected a boolean, got {value!r}")
    return value


def _parse_levels(raw_levels: object, side: str) -> list["KalshiLevel"]:
    """One orderbook ladder: ``[[price_str, size_str], ...]`` listed
    ascending worst-first (recorded live; the docs' "best to worst"
    claim is contradicted by the wire). Any reordering or duplicated
    price fails closed — best-level extraction is order-agnostic but
    the ladder must be honest."""
    if not isinstance(raw_levels, list):
        raise _protocol(f"orderbook.{side}: expected a list of levels")
    levels: list[KalshiLevel] = []
    previous = -1.0
    for index, raw in enumerate(raw_levels):
        where = f"orderbook.{side}[{index}]"
        if not isinstance(raw, list) or len(raw) != 2:
            raise _protocol(f"{where}: expected a [price, size] pair, got {raw!r}")
        price = _parse_price(raw[0], f"{where}[0]")
        size = _parse_fp(raw[1], f"{where}[1]")
        if price <= previous:
            raise _protocol(
                f"{where}: level prices are not strictly ascending (worst-first)"
            )
        previous = price
        levels.append(KalshiLevel(price=price, size=size))
    return levels


class KalshiSource(BaseModel):
    """One settlement source: ``{"name", "url"}``."""

    name: str
    url: str | None = None


class KalshiEvent(BaseModel):
    """One event row from the discovery list (wire shape, issue #35)."""

    event_ticker: str
    title: str
    series_ticker: str
    sub_title: str = ""
    category: str | None = None
    mutually_exclusive: bool = False
    collateral_return_type: str = ""
    strike_period: str = ""
    strike_date: datetime | None = None
    available_on_brokers: bool = False
    exchange_index: int | None = None
    last_updated_ts: datetime | None = None
    settlement_sources: list[KalshiSource] = Field(default_factory=list)


class KalshiMarketStatus(StrEnum):
    """The venue's market lifecycle; anything else fails closed."""

    UNOPENED = "unopened"
    ACTIVE = "active"
    CLOSED = "closed"
    SETTLED = "settled"
    FINALIZED = "finalized"


class KalshiPriceRange(BaseModel):
    """One ``price_ranges`` entry: tradeable price grid on [start, end]."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)
    step: float = Field(gt=0)


class KalshiMarket(BaseModel):
    """The market object (``GET /markets/{ticker}``, wire shape).

    ``result`` is ``""`` while unresolved and ``"yes"``/``"no"`` after
    settlement; ``status`` tells which. ``market_type`` distinguishes
    binary markets from ``multicategorical`` ones — the adapter
    refuses non-binary (Phase C probabilities are binary-payoff).
    """

    ticker: str
    title: str
    event_ticker: str
    status: KalshiMarketStatus
    market_type: str
    result: str = ""
    rules_primary: str = ""
    rules_secondary: str = ""
    expiration_time: datetime
    close_time: datetime | None = None
    open_time: datetime | None = None
    created_time: datetime | None = None
    updated_time: datetime | None = None
    settlement_ts: datetime | None = None
    settlement_value_dollars: float | None = None
    yes_bid_dollars: float | None = None
    yes_ask_dollars: float | None = None
    no_bid_dollars: float | None = None
    no_ask_dollars: float | None = None
    yes_bid_size_fp: float | None = None
    yes_ask_size_fp: float | None = None
    last_price_dollars: float | None = None
    previous_price_dollars: float | None = None
    volume_fp: float | None = None
    volume_24h_fp: float | None = None
    open_interest_fp: float | None = None
    liquidity_dollars: float | None = None
    notional_value_dollars: float | None = None
    is_provisional: bool | None = None
    settlement_timer_seconds: int | None = None
    price_level_structure: str | None = None
    price_ranges: list[KalshiPriceRange] = Field(default_factory=list)


class KalshiLevel(BaseModel):
    """One orderbook level: price in dollars, size in contracts."""

    price: float = Field(ge=0, le=1)
    size: float = Field(ge=0)


class KalshiOrderbook(BaseModel):
    """The order book for one market (``GET /markets/{ticker}/orderbook``).

    Both ladders hold resting **bids** on their own axis, ascending
    worst-first: ``yes_dollars`` are YES bids at YES prices and
    ``no_dollars`` are NO bids at NO prices. YES asks are derived as
    1 - no_bid_price with the same count (the docs' own rule).
    """

    yes_dollars: list[KalshiLevel] = Field(default_factory=list)
    no_dollars: list[KalshiLevel] = Field(default_factory=list)


class KalshiTrade(BaseModel):
    """One executed trade row (``GET /markets/trades``, wire shape).

    ``count_fp`` is the size in contracts; the complementary prices
    always sum to 1 within tolerance.
    """

    trade_id: str
    ticker: str
    count_fp: float = Field(ge=0)
    created_time: datetime
    is_block_trade: bool = False
    taker_side: str  # "yes" | "no" — what the taker bought
    taker_outcome_side: str  # "yes" | "no"
    taker_book_side: str  # "bid" | "ask" — the side of the book the taker hit
    yes_price_dollars: float = Field(ge=0, le=1)
    no_price_dollars: float = Field(ge=0, le=1)


class KalshiPriceBar(BaseModel):
    """The trade-price OHLC of one candlestick period.

    ``previous_dollars`` is always present; the OHLC fields exist only
    when the period actually traded (the recorded zero-volume rows
    carry just the previous close).
    """

    open_dollars: float | None = Field(default=None, ge=0, le=1)
    high_dollars: float | None = Field(default=None, ge=0, le=1)
    low_dollars: float | None = Field(default=None, ge=0, le=1)
    close_dollars: float | None = Field(default=None, ge=0, le=1)
    mean_dollars: float | None = Field(default=None, ge=0, le=1)
    previous_dollars: float | None = Field(default=None, ge=0, le=1)


class KalshiOhlc(BaseModel):
    """One side's OHLC for a period (yes_bid / yes_ask)."""

    open_dollars: float = Field(ge=0, le=1)
    high_dollars: float = Field(ge=0, le=1)
    low_dollars: float = Field(ge=0, le=1)
    close_dollars: float = Field(ge=0, le=1)


class KalshiCandlestick(BaseModel):
    """One candlestick row; ``end_period_ts`` is the period END
    (converted to an aware datetime here; the bar adapter re-bases it
    to the M3 bar-open convention)."""

    end_period_ts: datetime
    open_interest_fp: float = Field(ge=0)
    volume_fp: float = Field(ge=0)
    price: KalshiPriceBar
    yes_ask: KalshiOhlc
    yes_bid: KalshiOhlc


class KalshiSeries(BaseModel):
    """One series object (``GET /series/{ticker}``)."""

    series_ticker: str
    category: str | None = None
    fee_multiplier: float | None = None
    fee_type: str | None = None
    frequency: str | None = None
    settlement_sources: list[KalshiSource] = Field(default_factory=list)


def _event_from_raw(raw: dict, where: str) -> KalshiEvent:
    return KalshiEvent(
        event_ticker=_require_str(raw["event_ticker"], f"{where}.event_ticker"),
        title=_require_str(raw["title"], f"{where}.title"),
        series_ticker=_require_str(raw["series_ticker"], f"{where}.series_ticker"),
        sub_title=_optional_str(raw.get("sub_title"), f"{where}.sub_title") or "",
        category=_optional_str(raw.get("category"), f"{where}.category"),
        mutually_exclusive=_require_bool(
            raw["mutually_exclusive"], f"{where}.mutually_exclusive"
        ),
        collateral_return_type=(
            _optional_str(raw.get("collateral_return_type"), f"{where}.collateral_return_type")
            or ""
        ),
        strike_period=_optional_str(raw.get("strike_period"), f"{where}.strike_period") or "",
        strike_date=_parse_optional_iso(raw.get("strike_date"), f"{where}.strike_date"),
        available_on_brokers=_require_bool(
            raw["available_on_brokers"], f"{where}.available_on_brokers"
        ),
        exchange_index=_optional_int(raw.get("exchange_index"), f"{where}.exchange_index"),
        last_updated_ts=_parse_optional_iso(raw.get("last_updated_ts"), f"{where}.last_updated_ts"),
        settlement_sources=_parse_sources(raw.get("settlement_sources") or [], f"{where}"),
    )


def _optional_int(value: object, where: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _protocol(f"{where}: expected an integer, got {value!r}")
    return value


def _parse_sources(raw_sources: object, where: str) -> list[KalshiSource]:
    if not isinstance(raw_sources, list):
        raise _protocol(f"{where}: settlement_sources must be a list")
    sources = []
    for index, raw in enumerate(raw_sources):
        src_where = f"{where}.settlement_sources[{index}]"
        if not isinstance(raw, dict):
            raise _protocol(f"{src_where}: expected an object")
        sources.append(
            KalshiSource(
                name=_require_str(raw.get("name"), f"{src_where}.name"),
                url=_optional_str(raw.get("url"), f"{src_where}.url"),
            )
        )
    return sources


def _market_from_raw(raw: dict, where: str) -> KalshiMarket:
    status_raw = raw.get("status")
    if not isinstance(status_raw, str) or status_raw not in {
        member.value for member in KalshiMarketStatus
    }:
        raise _protocol(f"{where}.status: unknown market status {status_raw!r}")
    market_type = _require_str(raw["market_type"], f"{where}.market_type")
    if market_type not in {"binary", "multicategorical"}:
        raise _protocol(f"{where}.market_type: unknown type {market_type!r}")
    result = raw.get("result", "")
    if result not in {"", "yes", "no"}:
        raise _protocol(f"{where}.result: unknown result {result!r}")
    ranges = []
    for index, raw_range in enumerate(raw.get("price_ranges") or []):
        range_where = f"{where}.price_ranges[{index}]"
        if not isinstance(raw_range, dict):
            raise _protocol(f"{range_where}: expected an object")
        ranges.append(
            KalshiPriceRange(
                start=_parse_finite(raw_range["start"], f"{range_where}.start"),
                end=_parse_finite(raw_range["end"], f"{range_where}.end"),
                step=_parse_finite(raw_range["step"], f"{range_where}.step"),
            )
        )
    return KalshiMarket(
        ticker=_require_str(raw["ticker"], f"{where}.ticker"),
        title=_require_str(raw["title"], f"{where}.title"),
        event_ticker=_require_str(raw["event_ticker"], f"{where}.event_ticker"),
        status=KalshiMarketStatus(status_raw),
        market_type=market_type,
        result=result,
        rules_primary=_optional_str(raw.get("rules_primary"), f"{where}.rules_primary") or "",
        rules_secondary=_optional_str(raw.get("rules_secondary"), f"{where}.rules_secondary")
        or "",
        expiration_time=_parse_iso(raw["expiration_time"], f"{where}.expiration_time"),
        close_time=_parse_optional_iso(raw.get("close_time"), f"{where}.close_time"),
        open_time=_parse_optional_iso(raw.get("open_time"), f"{where}.open_time"),
        created_time=_parse_optional_iso(raw.get("created_time"), f"{where}.created_time"),
        updated_time=_parse_optional_iso(raw.get("updated_time"), f"{where}.updated_time"),
        settlement_ts=_parse_optional_iso(raw.get("settlement_ts"), f"{where}.settlement_ts"),
        settlement_value_dollars=_parse_optional_price(
            raw.get("settlement_value_dollars"), f"{where}.settlement_value_dollars"
        ),
        yes_bid_dollars=_parse_optional_price(
            raw.get("yes_bid_dollars"), f"{where}.yes_bid_dollars"
        ),
        yes_ask_dollars=_parse_optional_price(
            raw.get("yes_ask_dollars"), f"{where}.yes_ask_dollars"
        ),
        no_bid_dollars=_parse_optional_price(raw.get("no_bid_dollars"), f"{where}.no_bid_dollars"),
        no_ask_dollars=_parse_optional_price(raw.get("no_ask_dollars"), f"{where}.no_ask_dollars"),
        yes_bid_size_fp=_parse_optional_fp(raw.get("yes_bid_size_fp"), f"{where}.yes_bid_size_fp"),
        yes_ask_size_fp=_parse_optional_fp(raw.get("yes_ask_size_fp"), f"{where}.yes_ask_size_fp"),
        last_price_dollars=_parse_optional_price(
            raw.get("last_price_dollars"), f"{where}.last_price_dollars"
        ),
        previous_price_dollars=_parse_optional_price(
            raw.get("previous_price_dollars"), f"{where}.previous_price_dollars"
        ),
        volume_fp=_parse_optional_fp(raw.get("volume_fp"), f"{where}.volume_fp"),
        volume_24h_fp=_parse_optional_fp(raw.get("volume_24h_fp"), f"{where}.volume_24h_fp"),
        open_interest_fp=_parse_optional_fp(
            raw.get("open_interest_fp"), f"{where}.open_interest_fp"
        ),
        liquidity_dollars=_parse_optional_price(
            raw.get("liquidity_dollars"), f"{where}.liquidity_dollars"
        ),
        notional_value_dollars=_parse_optional_price(
            raw.get("notional_value_dollars"), f"{where}.notional_value_dollars"
        ),
        is_provisional=_optional_bool(raw.get("is_provisional"), f"{where}.is_provisional"),
        settlement_timer_seconds=_optional_int(
            raw.get("settlement_timer_seconds"), f"{where}.settlement_timer_seconds"
        ),
        price_level_structure=_optional_str(
            raw.get("price_level_structure"), f"{where}.price_level_structure"
        ),
        price_ranges=ranges,
    )


def _parse_optional_price(value: object, where: str) -> float | None:
    if value is None:
        return None
    return _parse_price(value, where)


def _parse_optional_fp(value: object, where: str) -> float | None:
    if value is None:
        return None
    return _parse_fp(value, where)


def _optional_bool(value: object, where: str) -> bool | None:
    if value is None:
        return None
    return _require_bool(value, where)


def parse_events(payload: object) -> list[KalshiEvent]:
    """``GET /events`` → the event list; fails closed on any bad row."""
    if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
        raise _protocol("Kalshi /events: expected {'events': [...]}")
    events = []
    for index, raw in enumerate(payload["events"]):
        where = f"Kalshi /events event {index}"
        if not isinstance(raw, dict):
            raise _protocol(f"{where}: expected an object")
        try:
            events.append(_event_from_raw(raw, where))
        except (KalshiProtocolError, KeyError) as error:
            if isinstance(error, KeyError):
                raise _protocol(f"{where}: missing {error}") from error
            raise _protocol(f"{where}: {error}") from error
    return events


def parse_event_bundle(payload: object) -> tuple[KalshiEvent, list[KalshiMarket]]:
    """``GET /events/{ticker}`` → (event, its markets) in one body."""
    if not isinstance(payload, dict) or not isinstance(payload.get("event"), dict):
        raise _protocol("Kalshi /events/{ticker}: expected {'event': {...}, 'markets': [...]}")
    event = _event_from_raw(payload["event"], "Kalshi /events/{ticker}.event")
    return event, parse_markets({"markets": payload.get("markets") or []})


def parse_markets(payload: object) -> list[KalshiMarket]:
    """``GET /markets`` → the market list; fails closed on any bad row."""
    if not isinstance(payload, dict) or not isinstance(payload.get("markets"), list):
        raise _protocol("Kalshi /markets: expected {'markets': [...]}")
    markets = []
    for index, raw in enumerate(payload["markets"]):
        where = f"Kalshi /markets market {index}"
        if not isinstance(raw, dict):
            raise _protocol(f"{where}: expected an object")
        try:
            markets.append(_market_from_raw(raw, where))
        except (KalshiProtocolError, KeyError) as error:
            if isinstance(error, KeyError):
                raise _protocol(f"{where}: missing {error}") from error
            raise _protocol(f"{where}: {error}") from error
    return markets


def parse_market(payload: object) -> KalshiMarket:
    """``GET /markets/{ticker}`` → the market object (fails closed)."""
    _require_error_free(payload, "Kalshi /markets/{ticker}")
    if not isinstance(payload, dict) or not isinstance(payload.get("market"), dict):
        raise _protocol("Kalshi /markets/{ticker}: expected {'market': {...}}")
    where = "Kalshi /markets/{ticker}.market"
    try:
        return _market_from_raw(payload["market"], where)
    except (KalshiProtocolError, KeyError) as error:
        if isinstance(error, KeyError):
            raise _protocol(f"{where}: missing {error}") from error
        raise _protocol(f"{where}: {error}") from error


def parse_orderbook(payload: object) -> KalshiOrderbook:
    """``GET /markets/{ticker}/orderbook`` → the two bid ladders."""
    _require_error_free(payload, "Kalshi orderbook")
    if not isinstance(payload, dict) or not isinstance(payload.get("orderbook_fp"), dict):
        raise _protocol("Kalshi orderbook: expected {'orderbook_fp': {...}}")
    book = payload["orderbook_fp"]
    try:
        return KalshiOrderbook(
            yes_dollars=_parse_levels(book["yes_dollars"], "yes_dollars"),
            no_dollars=_parse_levels(book["no_dollars"], "no_dollars"),
        )
    except KeyError as error:
        raise _protocol(f"Kalshi orderbook: missing {error}") from error


def parse_trades(payload: object) -> list[KalshiTrade]:
    """``GET /markets/trades`` → the trade list (empty for unknown tickers)."""
    _require_error_free(payload, "Kalshi /markets/trades")
    if not isinstance(payload, dict) or not isinstance(payload.get("trades"), list):
        raise _protocol("Kalshi /markets/trades: expected {'trades': [...]}")
    trades = []
    for index, raw in enumerate(payload["trades"]):
        where = f"Kalshi trades[{index}]"
        if not isinstance(raw, dict):
            raise _protocol(f"{where}: expected an object")
        try:
            yes = _parse_price(raw["yes_price_dollars"], f"{where}.yes_price_dollars")
            no = _parse_price(raw["no_price_dollars"], f"{where}.no_price_dollars")
            if abs(yes + no - 1.0) > _PRICE_TOLERANCE:
                raise _protocol(
                    f"{where}: complementary prices {yes} + {no} do not sum to 1"
                )
            taker_side = _require_str(raw["taker_side"], f"{where}.taker_side")
            if taker_side not in {"yes", "no"}:
                raise _protocol(f"{where}.taker_side: unknown side {taker_side!r}")
            for field, allowed in (
                ("taker_outcome_side", {"yes", "no"}),
                ("taker_book_side", {"bid", "ask"}),
            ):
                value = _require_str(raw[field], f"{where}.{field}")
                if value not in allowed:
                    raise _protocol(f"{where}.{field}: unknown value {value!r}")
            trades.append(
                KalshiTrade(
                    trade_id=_require_str(raw["trade_id"], f"{where}.trade_id"),
                    ticker=_require_str(raw["ticker"], f"{where}.ticker"),
                    count_fp=_parse_fp(raw["count_fp"], f"{where}.count_fp"),
                    created_time=_parse_iso(raw["created_time"], f"{where}.created_time"),
                    is_block_trade=_require_bool(
                        raw["is_block_trade"], f"{where}.is_block_trade"
                    ),
                    taker_side=taker_side,
                    taker_outcome_side=raw["taker_outcome_side"],
                    taker_book_side=raw["taker_book_side"],
                    yes_price_dollars=yes,
                    no_price_dollars=no,
                )
            )
        except (KalshiProtocolError, KeyError) as error:
            if isinstance(error, KeyError):
                raise _protocol(f"{where}: missing {error}") from error
            raise _protocol(f"{where}: {error}") from error
    return trades


def _parse_ohlc(raw: object, where: str) -> KalshiOhlc:
    if not isinstance(raw, dict):
        raise _protocol(f"{where}: expected an object")
    try:
        return KalshiOhlc(
            open_dollars=_parse_price(raw["open_dollars"], f"{where}.open_dollars"),
            high_dollars=_parse_price(raw["high_dollars"], f"{where}.high_dollars"),
            low_dollars=_parse_price(raw["low_dollars"], f"{where}.low_dollars"),
            close_dollars=_parse_price(raw["close_dollars"], f"{where}.close_dollars"),
        )
    except KeyError as error:
        raise _protocol(f"{where}: missing {error}") from error


def _parse_price_bar(raw: object, where: str) -> KalshiPriceBar:
    if not isinstance(raw, dict):
        raise _protocol(f"{where}: expected an object")
    try:
        return KalshiPriceBar(
            open_dollars=_parse_optional_price(raw.get("open_dollars"), f"{where}.open_dollars"),
            high_dollars=_parse_optional_price(raw.get("high_dollars"), f"{where}.high_dollars"),
            low_dollars=_parse_optional_price(raw.get("low_dollars"), f"{where}.low_dollars"),
            close_dollars=_parse_optional_price(raw.get("close_dollars"), f"{where}.close_dollars"),
            mean_dollars=_parse_optional_price(raw.get("mean_dollars"), f"{where}.mean_dollars"),
            previous_dollars=_parse_optional_price(
                raw.get("previous_dollars"), f"{where}.previous_dollars"
            ),
        )
    except KeyError as error:
        raise _protocol(f"{where}: missing {error}") from error


def parse_candlesticks(payload: object) -> list[KalshiCandlestick]:
    """``GET /series/{series}/markets/{ticker}/candlesticks`` → rows.

    ``end_period_ts`` must be non-decreasing; a traded row (volume > 0)
    without its trade OHLC is a contract violation.
    """
    _require_error_free(payload, "Kalshi candlesticks")
    if not isinstance(payload, dict) or not isinstance(payload.get("candlesticks"), list):
        raise _protocol("Kalshi candlesticks: expected {'candlesticks': [...]}")
    rows: list[KalshiCandlestick] = []
    previous_ts: int | None = None
    for index, raw in enumerate(payload["candlesticks"]):
        where = f"Kalshi candlesticks[{index}]"
        if not isinstance(raw, dict):
            raise _protocol(f"{where}: expected an object")
        try:
            end_raw = raw["end_period_ts"]
            if isinstance(end_raw, bool):
                raise _protocol(f"{where}: boolean where a timestamp is required")
            end_ts = int(end_raw)
            end_period = datetime.fromtimestamp(end_ts, tz=UTC)
            volume = _parse_fp(raw["volume_fp"], f"{where}.volume_fp")
            price = _parse_price_bar(raw["price"], f"{where}.price")
            if volume > 0 and price.open_dollars is None:
                raise _protocol(f"{where}: traded period missing its trade OHLC")
            rows.append(
                KalshiCandlestick(
                    end_period_ts=end_period,
                    open_interest_fp=_parse_fp(
                        raw["open_interest_fp"], f"{where}.open_interest_fp"
                    ),
                    volume_fp=volume,
                    price=price,
                    yes_ask=_parse_ohlc(raw["yes_ask"], f"{where}.yes_ask"),
                    yes_bid=_parse_ohlc(raw["yes_bid"], f"{where}.yes_bid"),
                )
            )
        except (KalshiProtocolError, KeyError) as error:
            if isinstance(error, KeyError):
                raise _protocol(f"{where}: missing {error}") from error
            raise _protocol(f"{where}: {error}") from error
        except (TypeError, ValueError, OverflowError) as error:
            raise _protocol(f"{where}: {end_raw!r} is not a unix timestamp") from error
        if previous_ts is not None and end_ts < previous_ts:
            raise _protocol(f"{where}: end_period_ts is not non-decreasing")
        previous_ts = end_ts
    return rows


def parse_series(payload: object) -> KalshiSeries:
    """``GET /series/{ticker}`` → the series object.

    The recorded wire carries the series' identity in ``ticker``, not
    ``series_ticker`` — the object's own field is absent (recorded
    live 2026-08-08; the docs' schema was stale on this too).
    """
    _require_error_free(payload, "Kalshi /series/{ticker}")
    if not isinstance(payload, dict) or not isinstance(payload.get("series"), dict):
        raise _protocol("Kalshi /series/{ticker}: expected {'series': {...}}")
    raw = payload["series"]
    where = "Kalshi /series/{ticker}.series"
    return KalshiSeries(
        series_ticker=_require_str(raw.get("ticker"), f"{where}.ticker"),
        category=_optional_str(raw.get("category"), f"{where}.category"),
        fee_multiplier=_parse_optional_fp(raw.get("fee_multiplier"), f"{where}.fee_multiplier"),
        fee_type=_optional_str(raw.get("fee_type"), f"{where}.fee_type"),
        frequency=_optional_str(raw.get("frequency"), f"{where}.frequency"),
        settlement_sources=_parse_sources(raw.get("settlement_sources") or [], where),
    )
