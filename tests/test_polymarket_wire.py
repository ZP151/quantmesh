"""Polymarket wire parsers over the recorded live fixtures (issue #34).

Every fixture here was recorded from the live public API on
2026-08-08 (ADR-0008 decision 2) or is a malformed variant that must
fail closed. A fixture failure is a parser failure — the recorded
shapes are the versioned contract authority.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from quantmesh.polymarket.errors import PolymarketProtocolError
from quantmesh.polymarket.wire import (
    parse_clob_book,
    parse_clob_market,
    parse_fee_rate,
    parse_gamma_events,
    parse_prices_history,
    parse_tick_size,
)

FIXTURES = Path(__file__).parent.parent / "src" / "quantmesh" / "polymarket" / "fixtures"

FED_YES_TOKEN = "97186030785608128217926542396950266594898339988989015155120280107165449433603"
FED_CONDITION = "0x5e464d85eb49f22d876f3ed6168a7db5e2288e9ae1eb91effd2758e994676f86"


def _load(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _malformed(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# -- Gamma discovery -----------------------------------------------------------


def test_gamma_events_parses_the_resolved_nba_event() -> None:
    events = parse_gamma_events(_load("gamma_events.json"))
    assert len(events) == 1
    event = events[0]
    assert event.ticker == (
        "nba-will-the-mavericks-beat-the-grizzlies-by-more-than-"
        "5pt5-points-in-their-december-4-matchup"
    )
    assert event.closed is True
    assert event.closed_time is not None
    assert event.closed_time.tzinfo is not None
    assert len(event.markets) == 1
    market = event.markets[0]
    assert market.condition_id == (
        "0x064d33e3f5703792aafa92bfb0ee10e08f461b1b34c02c1f02671892ede1609a"
    )
    assert market.outcomes == ["Yes", "No"]
    assert len(market.clob_token_ids) == 2
    assert len(market.outcome_prices) == 2
    assert all(0.0 <= price <= 1.0 for price in market.outcome_prices)
    assert market.end_date is not None and market.end_date.tzinfo is not None
    assert market.liquidity == 50.000009
    assert market.closed is True


def test_gamma_events_parses_the_active_fed_event() -> None:
    events = parse_gamma_events(_load("gamma_active.json"))
    assert len(events) == 1
    event = events[0]
    assert event.ticker == "fed-decision-in-september-762"
    assert event.closed is False
    assert len(event.markets) == 5
    for market in event.markets:
        assert market.outcomes == ["Yes", "No"]
        assert len(market.clob_token_ids) == 2
        assert len(market.outcome_prices) == 2
        assert market.condition_id.startswith("0x")
        assert market.end_date == datetime(2026, 9, 16, tzinfo=UTC)


def test_gamma_events_rejects_a_non_list_payload() -> None:
    with pytest.raises(PolymarketProtocolError, match="expected a list"):
        parse_gamma_events({"events": []})


def test_gamma_token_outcome_count_mismatch_fails_closed() -> None:
    payload = _malformed("gamma_active.json")
    payload[0]["markets"][0]["clobTokenIds"] = json.dumps(["only-one-token"])
    with pytest.raises(PolymarketProtocolError, match="outcomes but"):
        parse_gamma_events(payload)


def test_gamma_plain_list_outcomes_are_rejected() -> None:
    payload = _malformed("gamma_events.json")
    payload[0]["markets"][0]["outcomes"] = ["Yes", "No"]  # not JSON-encoded
    with pytest.raises(PolymarketProtocolError, match="JSON-encoded"):
        parse_gamma_events(payload)


def test_gamma_outcome_price_count_mismatch_fails_closed() -> None:
    payload = _malformed("gamma_active.json")
    payload[0]["markets"][0]["outcomePrices"] = json.dumps(["0.5"])
    with pytest.raises(PolymarketProtocolError, match="outcomes but"):
        parse_gamma_events(payload)


def test_gamma_non_finite_price_fails_closed() -> None:
    payload = _malformed("gamma_active.json")
    payload[0]["markets"][0]["outcomePrices"] = json.dumps(["NaN", "0.5"])
    with pytest.raises(PolymarketProtocolError, match="not finite"):
        parse_gamma_events(payload)


# -- CLOB book -----------------------------------------------------------------


def test_clob_book_parses_the_recorded_yes_token_book() -> None:
    book = parse_clob_book(_load("clob_book.json"))
    assert book.market == FED_CONDITION
    assert book.asset_id == FED_YES_TOKEN
    assert book.timestamp.tzinfo is not None
    assert book.hash
    assert book.bids and book.asks
    # Observed live convention (recorded): bids ascending, asks
    # descending — worst levels first. The parser pins the shape, not
    # an ordering assumption; the adapter takes best levels by max/min.
    bid_prices = [level.price for level in book.bids]
    ask_prices = [level.price for level in book.asks]
    assert bid_prices == sorted(bid_prices)
    assert ask_prices == sorted(ask_prices, reverse=True)
    assert all(0.0 <= level.price <= 1.0 for level in [*book.bids, *book.asks])
    assert all(level.size >= 0 for level in [*book.bids, *book.asks])


def test_clob_book_error_payload_is_a_typed_refusal() -> None:
    with pytest.raises(PolymarketProtocolError, match="No orderbook exists"):
        parse_clob_book(_load("clob_book_error.json"))


def test_clob_book_allows_empty_levels_but_requires_keys() -> None:
    payload = _malformed("clob_book.json")
    payload["bids"] = []
    payload["asks"] = []
    book = parse_clob_book(payload)
    assert book.bids == [] and book.asks == []
    del payload["hash"]
    with pytest.raises(PolymarketProtocolError, match="missing 'hash'"):
        parse_clob_book(payload)


def test_clob_book_rejects_out_of_range_levels() -> None:
    payload = _malformed("clob_book.json")
    payload["bids"][0]["price"] = "1.5"
    with pytest.raises(PolymarketProtocolError, match=r"\[0, 1\]"):
        parse_clob_book(payload)


def test_clob_book_rejects_boolean_prices() -> None:
    payload = _malformed("clob_book.json")
    payload["bids"][0]["price"] = True
    with pytest.raises(PolymarketProtocolError, match="boolean"):
        parse_clob_book(payload)


def test_clob_book_rejects_a_naive_or_garbage_timestamp() -> None:
    payload = _malformed("clob_book.json")
    payload["timestamp"] = "2026-08-08T12:00:00"
    with pytest.raises(PolymarketProtocolError, match="millisecond"):
        parse_clob_book(payload)


# -- CLOB market ---------------------------------------------------------------


def test_clob_market_parses_the_recorded_fed_market() -> None:
    market = parse_clob_market(_load("clob_market.json"))
    assert market.condition_id == FED_CONDITION
    assert market.minimum_tick_size == 0.001
    assert market.minimum_order_size == 5
    assert market.maker_base_fee == 1000
    assert market.taker_base_fee == 1000
    assert market.closed is False
    assert market.end_date_iso == datetime(2026, 9, 16, tzinfo=UTC)
    assert [token.outcome for token in market.tokens] == ["Yes", "No"]
    assert market.tokens[0].token_id == FED_YES_TOKEN
    assert all(token.winner is False for token in market.tokens)
    assert all(0.0 <= token.price <= 1.0 for token in market.tokens)


def test_clob_market_error_payload_is_a_typed_refusal() -> None:
    with pytest.raises(PolymarketProtocolError, match="market not found"):
        parse_clob_market(_load("clob_market_error.json"))


def test_clob_market_requires_the_fee_contract_fields() -> None:
    payload = _malformed("clob_market.json")
    del payload["taker_base_fee"]
    with pytest.raises(PolymarketProtocolError, match="taker_base_fee"):
        parse_clob_market(payload)


# -- prices-history ------------------------------------------------------------


def test_prices_history_parses_the_recorded_series() -> None:
    points = parse_prices_history(_load("clob_history.json"))
    assert len(points) == 707
    assert all(points[i].timestamp <= points[i + 1].timestamp for i in range(len(points) - 1))
    assert points[0].timestamp == datetime.fromtimestamp(1783450807, tz=UTC)
    assert all(0.0 <= point.price <= 1.0 for point in points)
    assert points[-1].price == 0.0095


def test_prices_history_error_payload_is_a_typed_refusal() -> None:
    with pytest.raises(PolymarketProtocolError, match="interval is too long"):
        parse_prices_history(_load("clob_history_error.json"))


def test_prices_history_requires_the_history_key() -> None:
    with pytest.raises(PolymarketProtocolError, match="history"):
        parse_prices_history({"foo": []})


def test_prices_history_rejects_out_of_order_rows() -> None:
    payload = _malformed("clob_history.json")
    first, second = payload["history"][0], payload["history"][1]
    payload["history"][1] = {"t": first["t"] - 1, "p": second["p"]}
    with pytest.raises(PolymarketProtocolError, match="non-decreasing"):
        parse_prices_history(payload)


def test_prices_history_rejects_array_rows() -> None:
    payload = _malformed("clob_history.json")
    payload["history"] = [[1783450807, 0.5]]
    with pytest.raises(PolymarketProtocolError, match="expected an object"):
        parse_prices_history(payload)


# -- fee-rate and tick-size ----------------------------------------------------


def test_fee_rate_parses_the_recorded_contract() -> None:
    assert parse_fee_rate(_load("fee_rate.json")) == 1000.0


def test_fee_rate_missing_base_fee_fails_closed() -> None:
    # The vendored SDK defaults a missing fee to 0 (``or 0``); that
    # fail-open is deliberately not replicated (ADR-0008).
    with pytest.raises(PolymarketProtocolError, match="base_fee"):
        parse_fee_rate({})


def test_tick_size_parses_the_recorded_contract() -> None:
    assert parse_tick_size(_load("tick_size.json")) == 0.001


def test_tick_size_non_positive_fails_closed() -> None:
    with pytest.raises(PolymarketProtocolError, match="non-positive"):
        parse_tick_size({"minimum_tick_size": 0})
