"""Polymarket wire-shape parsing (M6, issue #34, Phase A).

Payload contracts are pinned to the vendored ``py-clob-client-v2``
source where one exists and to wire shapes recorded from the live
public API on 2026-08-08 otherwise (ADR-0008 decision 2):

- Gamma ``/events`` rows: event keys ``id/ticker/slug/title/category/
  startDate/endDate/closed/closedTime/volume/liquidity/markets``;
  market keys ``id/question/conditionId/slug/description/
  resolutionSource/outcomes`` (JSON-encoded array *string*),
  ``outcomePrices`` (JSON-encoded array of decimal *strings*),
  ``clobTokenIds`` (JSON-encoded array of token-id strings),
  ``endDate/closed/closedTime``, ``liquidity/volume`` (decimal
  strings).
- CLOB ``GET /book``: ``{market, asset_id, timestamp (ms string),
  hash, bids, asks}`` with levels as object pairs
  ``{"price": dec-str, "size": dec-str}`` — the same shape the
  vendored SDK's ``parse_raw_orderbook_summary`` reads. Two recorded
  divergences from the vendored parser: the live wire omits the
  SDK's ``last_trade_price``/``min_order_size``/``neg_risk``/
  ``tick_size`` fields (those come from the market object instead),
  and level order is observed worst-first (bids ascending, asks
  descending) — best levels are extracted order-agnostically.
- CLOB ``GET /markets/{condition_id}``: the market object directly
  (``condition_id/question/end_date_iso/minimum_tick_size/
  minimum_order_size/maker_base_fee/taker_base_fee/closed`` plus
  ``tokens: [{token_id, outcome, price, winner}]``).
- CLOB ``GET /prices-history``: ``{"history": [{"t": unix seconds,
  "p": price}, ...]}`` — object rows, not arrays.
- CLOB ``GET /fee-rate``: ``{"base_fee": bps}`` (the SDK's own
  authority for fee rates; its ``or 0`` fallback on a missing field
  is fail-open and is not replicated — a missing ``base_fee`` is a
  protocol error).
- CLOB ``GET /tick-size``: ``{"minimum_tick_size": 0.001}``.
- Every CLOB error response is ``{"error": "..."}`` (recorded from
  live 400/404s) and raises ``PolymarketProtocolError`` carrying the
  server message — never a silent empty result.

Every parser fails closed: a missing key, a non-numeric price, a
price outside [0, 1], a negative size, a non-finite value, a JSON
array that does not parse, a token/outcome count mismatch, a naive
timestamp, or out-of-order history raises ``PolymarketProtocolError``
instead of producing a silently wrong model.
"""

import json
import math
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from quantmesh.polymarket.errors import PolymarketProtocolError

__all__ = [
    "GammaEvent",
    "GammaMarket",
    "ClobBook",
    "ClobLevel",
    "ClobMarket",
    "ClobToken",
    "PricePoint",
    "parse_gamma_events",
    "parse_clob_book",
    "parse_clob_market",
    "parse_prices_history",
    "parse_fee_rate",
    "parse_tick_size",
]


def _protocol(message: str) -> PolymarketProtocolError:
    return PolymarketProtocolError(message)


def _require_error_free(payload: object, endpoint: str) -> None:
    """The CLOB speaks errors as ``{"error": "..."}`` (recorded live)."""
    if isinstance(payload, dict) and isinstance(payload.get("error"), str):
        raise _protocol(f"{endpoint} refused: {payload['error']}")


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
    parsed = _parse_finite(value, where)
    if not 0.0 <= parsed <= 1.0:
        raise _protocol(f"{where}: price {parsed} outside [0, 1]")
    return parsed


def _parse_ms_timestamp(value: object, where: str) -> datetime:
    """Unix-millisecond string timestamps (the book's ``timestamp``)."""
    if isinstance(value, bool):
        raise _protocol(f"{where}: boolean where a timestamp is required")
    try:
        seconds = int(value) / 1000.0
    except (TypeError, ValueError) as error:
        raise _protocol(f"{where}: {value!r} is not a millisecond timestamp") from error
    return datetime.fromtimestamp(seconds, tz=UTC)


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


def _parse_json_string_array(value: object, where: str) -> list[str]:
    """Gamma encodes arrays as JSON *strings*; anything else fails."""
    if not isinstance(value, str):
        raise _protocol(f"{where}: {value!r} is not a JSON-encoded array")
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise _protocol(f"{where}: {value!r} is not valid JSON") from error
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise _protocol(f"{where}: expected an array of strings, got {value!r}")
    return parsed


class GammaMarket(BaseModel):
    """One market inside a Gamma event (wire shape, issue #34)."""

    id: str
    question: str
    condition_id: str
    slug: str
    outcomes: list[str] = Field(min_length=1)
    outcome_prices: list[float] = Field(default_factory=list)
    clob_token_ids: list[str] = Field(default_factory=list)
    end_date: datetime | None = None
    closed: bool = False
    closed_time: datetime | None = None
    liquidity: float | None = None
    volume: float | None = None
    description: str | None = None
    resolution_source: str | None = None


class GammaEvent(BaseModel):
    """One Gamma discovery event (wire shape, issue #34)."""

    id: str
    ticker: str
    title: str
    category: str | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    closed: bool = False
    closed_time: datetime | None = None
    volume: float | None = None
    liquidity: float | None = None
    markets: list[GammaMarket] = Field(default_factory=list)


class ClobLevel(BaseModel):
    """One aggregated book level: an object pair ``{"price", "size"}``."""

    price: float = Field(ge=0, le=1)
    size: float = Field(ge=0)


class ClobBook(BaseModel):
    """The order book for one token (``GET /book``)."""

    market: str  # condition id
    asset_id: str  # token id
    timestamp: datetime
    hash: str
    bids: list[ClobLevel] = Field(default_factory=list)
    asks: list[ClobLevel] = Field(default_factory=list)


class ClobToken(BaseModel):
    """One token of a CLOB market object: outcome + price + winner flag."""

    token_id: str
    outcome: str
    price: float = Field(ge=0, le=1)
    winner: bool = False


class ClobMarket(BaseModel):
    """The CLOB market object (``GET /markets/{condition_id}``)."""

    condition_id: str
    question: str
    end_date_iso: datetime | None = None
    minimum_tick_size: float = Field(gt=0)
    minimum_order_size: float = Field(default=0, ge=0)
    maker_base_fee: float = Field(default=0, ge=0)  # bps as reported
    taker_base_fee: float = Field(default=0, ge=0)  # bps as reported
    closed: bool = False
    tokens: list[ClobToken] = Field(default_factory=list)


class PricePoint(BaseModel):
    """One prices-history row: ``{"t": unix seconds, "p": price}``."""

    timestamp: datetime
    price: float = Field(ge=0, le=1)


def parse_gamma_events(payload: object) -> list[GammaEvent]:
    """``GET /events`` → the event list; fails closed on any bad row."""
    if not isinstance(payload, list):
        raise _protocol("Gamma /events: expected a list of events")
    events: list[GammaEvent] = []
    for index, raw in enumerate(payload):
        where = f"Gamma /events event {index}"
        if not isinstance(raw, dict):
            raise _protocol(f"{where}: expected an object")
        try:
            markets = []
            for m_index, raw_market in enumerate(raw.get("markets") or []):
                m_where = f"{where} market {m_index}"
                if not isinstance(raw_market, dict):
                    raise _protocol(f"{m_where}: expected an object")
                outcomes = _parse_json_string_array(
                    raw_market.get("outcomes"), f"{m_where}.outcomes"
                )
                if not outcomes:
                    raise _protocol(f"{m_where}.outcomes: empty outcome set")
                outcome_prices = [
                    _parse_finite(item, f"{m_where}.outcomePrices[{i}]")
                    for i, item in enumerate(
                        _parse_json_string_array(
                            raw_market.get("outcomePrices"), f"{m_where}.outcomePrices"
                        )
                    )
                ]
                token_ids = _parse_json_string_array(
                    raw_market.get("clobTokenIds"), f"{m_where}.clobTokenIds"
                )
                # A deployed market's token list must line up 1:1 with
                # its outcomes (token order is outcome order); an empty
                # token list is a legitimate pre-deployment state.
                if token_ids and len(token_ids) != len(outcomes):
                    raise _protocol(
                        f"{m_where}: {len(outcomes)} outcomes but {len(token_ids)} token ids"
                    )
                if outcome_prices and len(outcome_prices) != len(outcomes):
                    raise _protocol(
                        f"{m_where}: {len(outcomes)} outcomes but {len(outcome_prices)} prices"
                    )
                markets.append(
                    GammaMarket(
                        id=_require_str(raw_market.get("id"), f"{m_where}.id"),
                        question=_require_str(raw_market.get("question"), f"{m_where}.question"),
                        condition_id=_require_str(
                            raw_market.get("conditionId"), f"{m_where}.conditionId"
                        ),
                        slug=_require_str(raw_market.get("slug"), f"{m_where}.slug"),
                        outcomes=outcomes,
                        outcome_prices=outcome_prices,
                        clob_token_ids=token_ids,
                        end_date=_parse_optional_iso(
                            raw_market.get("endDate"), f"{m_where}.endDate"
                        ),
                        closed=_require_bool(raw_market.get("closed", False), f"{m_where}.closed"),
                        closed_time=_parse_optional_iso(
                            raw_market.get("closedTime"), f"{m_where}.closedTime"
                        ),
                        liquidity=_parse_optional_decimal(
                            raw_market.get("liquidity"), f"{m_where}.liquidity"
                        ),
                        volume=_parse_optional_decimal(
                            raw_market.get("volume"), f"{m_where}.volume"
                        ),
                        description=_optional_str(raw_market.get("description")),
                        resolution_source=_optional_str(raw_market.get("resolutionSource")),
                    )
                )
            events.append(
                GammaEvent(
                    id=_require_str(raw.get("id"), f"{where}.id"),
                    ticker=_require_str(raw.get("ticker"), f"{where}.ticker"),
                    title=_require_str(raw.get("title"), f"{where}.title"),
                    category=_optional_str(raw.get("category")),
                    start_date=_parse_optional_iso(raw.get("startDate"), f"{where}.startDate"),
                    end_date=_parse_optional_iso(raw.get("endDate"), f"{where}.endDate"),
                    closed=_require_bool(raw.get("closed", False), f"{where}.closed"),
                    closed_time=_parse_optional_iso(
                        raw.get("closedTime"), f"{where}.closedTime"
                    ),
                    volume=_parse_optional_decimal(raw.get("volume"), f"{where}.volume"),
                    liquidity=_parse_optional_decimal(
                        raw.get("liquidity"), f"{where}.liquidity"
                    ),
                    markets=markets,
                )
            )
        except PolymarketProtocolError as error:
            raise _protocol(f"{where}: {error}") from error
    return events


def _require_str(value: object, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise _protocol(f"{where}: expected a non-empty string, got {value!r}")
    return value


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _protocol(f"expected a string, got {value!r}")
    return value


def _require_bool(value: object, where: str) -> bool:
    if not isinstance(value, bool):
        raise _protocol(f"{where}: expected a boolean, got {value!r}")
    return value


def _parse_optional_iso(value: object, where: str) -> datetime | None:
    if value is None:
        return None
    return _parse_iso(value, where)


def _parse_optional_decimal(value: object, where: str) -> float | None:
    if value is None:
        return None
    return _parse_finite(value, where)


def _parse_levels(raw_levels: object, where: str) -> list[ClobLevel]:
    if not isinstance(raw_levels, list):
        raise _protocol(f"{where}: expected a list of levels")
    levels = []
    for index, raw in enumerate(raw_levels):
        level_where = f"{where}[{index}]"
        if not isinstance(raw, dict):
            raise _protocol(f"{level_where}: expected an object pair")
        try:
            levels.append(
                ClobLevel(
                    price=_parse_price(raw["price"], f"{level_where}.price"),
                    size=_parse_finite(raw["size"], f"{level_where}.size"),
                )
            )
        except KeyError as error:
            raise _protocol(f"{level_where}: missing {error}") from error
    return levels


def parse_clob_book(payload: object) -> ClobBook:
    """``GET /book`` → the order book for one token."""
    _require_error_free(payload, "CLOB /book")
    if not isinstance(payload, dict):
        raise _protocol("CLOB /book: expected an object")
    try:
        return ClobBook(
            market=_require_str(payload["market"], "book.market"),
            asset_id=_require_str(payload["asset_id"], "book.asset_id"),
            timestamp=_parse_ms_timestamp(payload["timestamp"], "book.timestamp"),
            hash=_require_str(payload["hash"], "book.hash"),
            bids=_parse_levels(payload["bids"], "book.bids"),
            asks=_parse_levels(payload["asks"], "book.asks"),
        )
    except KeyError as error:
        raise _protocol(f"CLOB /book: missing {error}") from error


def parse_clob_market(payload: object) -> ClobMarket:
    """``GET /markets/{condition_id}`` → the market object."""
    _require_error_free(payload, "CLOB /markets")
    if not isinstance(payload, dict):
        raise _protocol("CLOB /markets: expected an object")
    try:
        raw_tokens = payload.get("tokens") or []
        if not isinstance(raw_tokens, list):
            raise _protocol("market.tokens: expected a list")
        tokens = []
        for index, raw in enumerate(raw_tokens):
            token_where = f"market.tokens[{index}]"
            if not isinstance(raw, dict):
                raise _protocol(f"{token_where}: expected an object")
            try:
                tokens.append(
                    ClobToken(
                        token_id=_require_str(raw["token_id"], f"{token_where}.token_id"),
                        outcome=_require_str(raw["outcome"], f"{token_where}.outcome"),
                        price=_parse_price(raw["price"], f"{token_where}.price"),
                        winner=_require_bool(raw["winner"], f"{token_where}.winner"),
                    )
                )
            except KeyError as error:
                raise _protocol(f"{token_where}: missing {error}") from error
        return ClobMarket(
            condition_id=_require_str(payload["condition_id"], "market.condition_id"),
            question=_require_str(payload["question"], "market.question"),
            end_date_iso=_parse_optional_iso(
                payload.get("end_date_iso"), "market.end_date_iso"
            ),
            minimum_tick_size=_parse_finite(
                payload["minimum_tick_size"], "market.minimum_tick_size"
            ),
            minimum_order_size=_parse_finite(
                payload.get("minimum_order_size", 0), "market.minimum_order_size"
            ),
            maker_base_fee=_parse_finite(payload["maker_base_fee"], "market.maker_base_fee"),
            taker_base_fee=_parse_finite(payload["taker_base_fee"], "market.taker_base_fee"),
            closed=_require_bool(payload["closed"], "market.closed"),
            tokens=tokens,
        )
    except KeyError as error:
        raise _protocol(f"CLOB /markets: missing {error}") from error


def parse_prices_history(payload: object) -> list[PricePoint]:
    """``GET /prices-history`` → the price series (object rows)."""
    _require_error_free(payload, "CLOB /prices-history")
    if not isinstance(payload, dict) or "history" not in payload:
        raise _protocol("CLOB /prices-history: missing 'history' key")
    raw_rows = payload["history"]
    if not isinstance(raw_rows, list):
        raise _protocol("CLOB /prices-history: 'history' is not a list")
    points: list[PricePoint] = []
    previous_t = 0
    for index, raw in enumerate(raw_rows):
        where = f"history[{index}]"
        if not isinstance(raw, dict):
            raise _protocol(f"{where}: expected an object")
        try:
            t = raw["t"]
            if isinstance(t, bool):
                raise _protocol(f"{where}.t: boolean where a timestamp is required")
            t_int = int(t)
            point = PricePoint(
                timestamp=datetime.fromtimestamp(t_int, tz=UTC),
                price=_parse_price(raw["p"], f"{where}.p"),
            )
        except KeyError as error:
            raise _protocol(f"{where}: missing {error}") from error
        except (TypeError, ValueError, OverflowError) as error:
            raise _protocol(f"{where}.t: {t!r} is not a unix timestamp") from error
        if t_int < previous_t:
            raise _protocol(f"{where}: history timestamps are not non-decreasing")
        previous_t = t_int
        points.append(point)
    return points


def parse_fee_rate(payload: object) -> float:
    """``GET /fee-rate`` → base fee in bps; missing fee fails closed."""
    _require_error_free(payload, "CLOB /fee-rate")
    if not isinstance(payload, dict) or "base_fee" not in payload:
        raise _protocol("CLOB /fee-rate: missing 'base_fee'")
    value = _parse_finite(payload["base_fee"], "fee-rate.base_fee")
    if value < 0:
        raise _protocol(f"fee-rate.base_fee: negative fee {value}")
    return value


def parse_tick_size(payload: object) -> float:
    """``GET /tick-size`` → minimum tick size."""
    _require_error_free(payload, "CLOB /tick-size")
    if not isinstance(payload, dict) or "minimum_tick_size" not in payload:
        raise _protocol("CLOB /tick-size: missing 'minimum_tick_size'")
    value = _parse_finite(payload["minimum_tick_size"], "tick-size.minimum_tick_size")
    if value <= 0:
        raise _protocol(f"tick-size.minimum_tick_size: non-positive tick size {value}")
    return value
