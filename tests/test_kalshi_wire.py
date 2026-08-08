"""Kalshi wire parsers over the recorded live fixtures (issue #35, Phase B).

Every fixture here was recorded from the live public API at
``api.elections.kalshi.com`` on 2026-08-08 (ADR-0008 decision 2) or is
a malformed variant that must fail closed. There is no vendorable SDK
authority — the fixtures themselves are the versioned contract.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from quantmesh.kalshi.errors import KalshiProtocolError
from quantmesh.kalshi.wire import (
    KalshiMarketStatus,
    parse_candlesticks,
    parse_event_bundle,
    parse_events,
    parse_market,
    parse_markets,
    parse_orderbook,
    parse_series,
    parse_trades,
)

FIXTURES = Path(__file__).parent.parent / "src" / "quantmesh" / "kalshi" / "fixtures"
FED_TICKER = "KXFED-27APR-T3.50"


def _load(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _malformed(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# -- events --------------------------------------------------------------------


def test_events_parse_the_recorded_discovery_page() -> None:
    events = parse_events(_load("events.json"))
    assert len(events) == 3
    assert events[0].event_ticker == "KXELONMARS-99"
    assert events[0].title == "Will Elon Musk visit Mars in his lifetime?"
    assert events[0].category == "World"
    assert events[0].series_ticker == "KXELONMARS"
    assert events[0].mutually_exclusive is False
    assert events[0].last_updated_ts is not None
    assert events[0].last_updated_ts.tzinfo is not None
    assert any(source.name == "The Guardian" for source in events[0].settlement_sources)
    assert events[1].event_ticker == "KXNEXTNATOSECGEN-99"
    assert events[2].event_ticker == "KXNEWPOPE-70"


def test_events_parse_the_strike_date_and_fed_event() -> None:
    events = parse_events(_load("events_fed.json"))
    fed = [e for e in events if e.event_ticker == "KXFED-27APR"]
    assert len(fed) == 1
    assert fed[0].category == "Economics"
    assert fed[0].strike_date == datetime(2027, 4, 28, 18, 0, tzinfo=UTC)


def test_event_bundle_parses_event_plus_markets() -> None:
    event, markets = parse_event_bundle(_load("event_mars.json"))
    assert event.event_ticker == "KXELONMARS-99"
    assert event.series_ticker == "KXELONMARS"
    assert len(markets) == 1
    assert markets[0].ticker == "KXELONMARS-99"


def test_events_reject_a_missing_row_key() -> None:
    payload = _malformed("events.json")
    del payload["events"][1]["event_ticker"]
    with pytest.raises(KalshiProtocolError, match="event_ticker"):
        parse_events(payload)


# -- markets -------------------------------------------------------------------


def test_market_parses_the_recorded_active_market() -> None:
    market = parse_market(_load("market_fed.json"))
    assert market.ticker == FED_TICKER
    assert market.status is KalshiMarketStatus.ACTIVE
    assert market.market_type == "binary"
    assert market.result == ""
    assert market.rules_primary
    assert market.yes_bid_dollars == 0.42
    assert market.yes_ask_dollars == 0.69
    assert market.last_price_dollars == 0.77
    assert market.updated_time is not None and market.updated_time.tzinfo is not None
    assert market.expiration_time == datetime(2027, 5, 5, 18, 5, tzinfo=UTC)
    assert market.price_ranges[0].step == 0.01
    assert market.volume_fp == pytest.approx(22417.09)
    assert market.open_interest_fp > 0


def test_settled_market_carries_the_resolution() -> None:
    market = parse_market(_load("market_settled.json"))
    assert market.status is KalshiMarketStatus.FINALIZED
    assert market.result == "no"
    assert market.settlement_ts is not None and market.settlement_ts.tzinfo is not None
    assert market.is_provisional is True


def test_markets_parse_the_recorded_list() -> None:
    markets = parse_markets(_load("markets_mars.json"))
    assert len(markets) == 1
    assert markets[0].ticker == "KXELONMARS-99"


def test_unknown_status_fails_closed() -> None:
    payload = _malformed("market_fed.json")
    payload["market"]["status"] = "warped"
    with pytest.raises(KalshiProtocolError, match="status"):
        parse_market(payload)


def test_unknown_market_type_fails_closed() -> None:
    payload = _malformed("market_fed.json")
    payload["market"]["market_type"] = "trinary"
    with pytest.raises(KalshiProtocolError, match="market_type"):
        parse_market(payload)


def test_unknown_result_fails_closed() -> None:
    payload = _malformed("market_settled.json")
    payload["market"]["result"] = "maybe"
    with pytest.raises(KalshiProtocolError, match="result"):
        parse_market(payload)


def test_market_missing_expiration_fails_closed() -> None:
    payload = _malformed("market_fed.json")
    del payload["market"]["expiration_time"]
    with pytest.raises(KalshiProtocolError, match="expiration_time"):
        parse_market(payload)


def test_market_error_payload_is_a_typed_refusal() -> None:
    with pytest.raises(KalshiProtocolError, match="not found"):
        parse_market(_load("market_unknown.json"))


# -- orderbook -----------------------------------------------------------------


def test_orderbook_parses_the_recorded_ladders() -> None:
    book = parse_orderbook(_load("orderbook.json"))
    # Recorded live: both ladders ascend worst-first (the docs claim
    # best-to-worst; the wire wins). The best YES bid is the max of
    # yes_dollars and the best YES ask is 1 - max(no_dollars) — both
    # cross-checked against the market object's own bid/ask.
    yes_prices = [level.price for level in book.yes_dollars]
    no_prices = [level.price for level in book.no_dollars]
    assert yes_prices == sorted(yes_prices)
    assert no_prices == sorted(no_prices)
    assert yes_prices[0] == 0.01  # worst first
    assert no_prices[0] == 0.01
    assert max(yes_prices) == 0.42
    assert max(no_prices) == 0.31
    assert 1.0 - max(no_prices) == pytest.approx(0.69)
    assert book.yes_dollars[-1].size == 6.0  # the market's yes_bid_size_fp
    assert book.no_dollars[-1].size == 4.0  # the market's yes_ask_size_fp
    assert all(level.size >= 0 for level in [*book.yes_dollars, *book.no_dollars])


def test_orderbook_rejects_a_non_pair_level() -> None:
    payload = _malformed("orderbook.json")
    payload["orderbook_fp"]["yes_dollars"][0] = ["0.01"]
    with pytest.raises(KalshiProtocolError, match="pair"):
        parse_orderbook(payload)


def test_orderbook_rejects_an_out_of_order_ladder() -> None:
    payload = _malformed("orderbook.json")
    ladder = payload["orderbook_fp"]["yes_dollars"]
    ladder[0], ladder[1] = ladder[1], ladder[0]
    with pytest.raises(KalshiProtocolError, match="ascending"):
        parse_orderbook(payload)


def test_orderbook_rejects_a_price_outside_the_unit_interval() -> None:
    payload = _malformed("orderbook.json")
    payload["orderbook_fp"]["no_dollars"][0][0] = "1.5000"
    with pytest.raises(KalshiProtocolError, match=r"\[0, 1\]"):
        parse_orderbook(payload)


def test_orderbook_rejects_a_negative_size() -> None:
    payload = _malformed("orderbook.json")
    payload["orderbook_fp"]["yes_dollars"][0][1] = "-5"
    with pytest.raises(KalshiProtocolError, match="negative"):
        parse_orderbook(payload)


# -- trades --------------------------------------------------------------------


def test_trades_parse_the_recorded_rows() -> None:
    trades = parse_trades(_load("trades.json"))
    assert len(trades) == 5
    first = trades[0]
    assert first.trade_id == "70c60328-503c-45a8-c206-cb245728dc6b"
    assert first.ticker == FED_TICKER
    assert first.count_fp == 4.0
    assert first.created_time.tzinfo is not None
    assert first.is_block_trade is False
    assert first.taker_side == "yes"
    assert first.taker_book_side == "bid"
    assert first.yes_price_dollars == 0.77
    assert first.no_price_dollars == 0.23
    # every recorded row has complementary prices and known sides
    for trade in trades:
        assert trade.yes_price_dollars + trade.no_price_dollars == pytest.approx(1.0)
        assert trade.taker_side in {"yes", "no"}
        assert trade.taker_outcome_side in {"yes", "no"}
        assert trade.taker_book_side in {"bid", "ask"}


def test_trades_unknown_ticker_is_an_empty_list_not_an_error() -> None:
    assert parse_trades(_load("trades_unknown.json")) == []


def test_trades_reject_non_complementary_prices() -> None:
    payload = _malformed("trades.json")
    payload["trades"][0]["no_price_dollars"] = "0.30"
    with pytest.raises(KalshiProtocolError, match="do not sum"):
        parse_trades(payload)


def test_trades_reject_an_unknown_taker_side() -> None:
    payload = _malformed("trades.json")
    payload["trades"][0]["taker_side"] = "hold"
    with pytest.raises(KalshiProtocolError, match="taker_side"):
        parse_trades(payload)


# -- candlesticks --------------------------------------------------------------


def test_candlesticks_parse_the_recorded_series() -> None:
    rows = parse_candlesticks(_load("candles.json"))
    assert len(rows) == 230
    assert all(
        rows[i].end_period_ts <= rows[i + 1].end_period_ts for i in range(len(rows) - 1)
    )
    traded = [r for r in rows if r.volume_fp > 0]
    assert len(traded) == 10
    for row in traded:
        assert row.price.open_dollars is not None
        assert row.price.close_dollars is not None
    idle = [r for r in rows if r.volume_fp == 0]
    assert idle
    for row in idle:
        assert row.price.open_dollars is None  # no period OHLC — nothing traded
        assert row.price.previous_dollars is not None


def test_candlesticks_out_of_order_periods_fail_closed() -> None:
    payload = _malformed("candles.json")
    payload["candlesticks"][1]["end_period_ts"] = (
        payload["candlesticks"][0]["end_period_ts"] - 3600
    )
    with pytest.raises(KalshiProtocolError, match="non-decreasing"):
        parse_candlesticks(payload)


def test_candlesticks_traded_row_missing_ohlc_fails_closed() -> None:
    payload = _malformed("candles.json")
    traded = next(
        i for i, row in enumerate(payload["candlesticks"]) if float(row["volume_fp"]) > 0
    )
    del payload["candlesticks"][traded]["price"]["open_dollars"]
    with pytest.raises(KalshiProtocolError, match="trade OHLC"):
        parse_candlesticks(payload)


def test_candlesticks_parameter_validation_error_is_typed() -> None:
    with pytest.raises(KalshiProtocolError, match="Parameter validation failed"):
        parse_candlesticks(_load("candles_bad_interval.json"))


# -- series --------------------------------------------------------------------


def test_series_parses_the_recorded_object() -> None:
    series = parse_series(_load("series.json"))
    assert series.series_ticker == "KXELONMARS"
    assert series.category == "Politics"
    assert series.fee_type == "quadratic"
    assert series.fee_multiplier == 1.0
    assert series.frequency == "custom"
