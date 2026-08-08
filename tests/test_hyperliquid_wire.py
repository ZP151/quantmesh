"""Hyperliquid wire-shape parsing tests (M5, issue #29, Phase A).

Payload contracts are pinned to the vendored SDK source: candles with
float-string OHLCV and ms open/close, l2Book ``levels`` arrays, trades
with ``A``/``B`` sides, funding with string rates, ``allMids``, and the
``meta``/``spotMeta`` universes. Every parser fails closed on shape
violations — nothing ambiguous may become a model.
"""

from datetime import UTC, datetime

import pytest

from quantmesh.domain.market_data import Bar, OrderBook
from quantmesh.domain.models import Instrument, InstrumentType, Side, Venue
from quantmesh.hyperliquid.errors import HyperliquidProtocolError
from quantmesh.hyperliquid.wire import (
    PerpMeta,
    SpotPair,
    ms_to_utc,
    parse_all_mids,
    parse_candle,
    parse_candle_frame,
    parse_funding,
    parse_l2_book,
    parse_meta,
    parse_spot_meta,
    parse_trades,
)

BTC = Instrument(
    symbol="BTC",
    venue=Venue.HYPERLIQUID,
    instrument_type=InstrumentType.PERPETUAL,
    currency="USD",
)

T0 = 1754600400000
STEP_MS = 60_000


def _t(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def candle(**overrides: object) -> dict:
    row = {
        "T": T0 + STEP_MS,
        "c": "104.5",
        "h": "105.0",
        "i": "1m",
        "l": "99.0",
        "n": 12,
        "o": "100.0",
        "s": "BTC",
        "t": T0,
        "v": "12.5",
    }
    row.update(overrides)
    return row


def l2_book(**overrides: object) -> dict:
    payload = {
        "coin": "BTC",
        "levels": [
            [{"n": 3, "px": "107.5", "sz": "2.0"}, {"n": 5, "px": "107.0", "sz": "4.5"}],
            [{"n": 4, "px": "108.0", "sz": "3.0"}, {"n": 6, "px": "108.5", "sz": "5.5"}],
        ],
        "time": T0 + STEP_MS,
    }
    payload.update(overrides)
    return payload


def trade(**overrides: object) -> dict:
    row = {
        "coin": "BTC",
        "px": "107.2",
        "side": "A",
        "sz": "1.5",
        "time": T0 + STEP_MS,
        "tid": 7,
        "users": ["0x1111"],
    }
    row.update(overrides)
    return row


def funding(**overrides: object) -> dict:
    row = {"coin": "BTC", "fundingRate": "0.00001", "premium": "0.00002", "time": T0}
    row.update(overrides)
    return row


# --- candles ----------------------------------------------------------------

def test_candle_parses_into_a_canonical_bar() -> None:
    bar = parse_candle(candle(), BTC, interval="1m")

    assert isinstance(bar, Bar)
    assert bar.timestamp == _t(T0)
    assert bar.open == 100.0
    assert bar.high == 105.0
    assert bar.low == 99.0
    assert bar.close == 104.5
    assert bar.volume == 12.5
    assert bar.interval == "1m"
    assert bar.instrument == BTC


def test_candle_frame_uses_the_same_parser() -> None:
    frame = {"channel": "candle", "data": candle()}

    bar = parse_candle_frame(frame["data"], BTC, interval="1m")

    assert bar.timestamp == _t(T0)


def test_candle_interval_mismatch_fails_closed() -> None:
    with pytest.raises(HyperliquidProtocolError, match="does not match requested"):
        parse_candle(candle(i="5m"), BTC, interval="1m")


def test_candle_symbol_mismatch_fails_closed() -> None:
    with pytest.raises(HyperliquidProtocolError, match="does not match instrument"):
        parse_candle(candle(s="ETH"), BTC, interval="1m")


def test_candle_close_must_land_exactly_one_interval_after_open() -> None:
    with pytest.raises(HyperliquidProtocolError, match="spans"):
        parse_candle(candle(T=T0 + 2 * STEP_MS), BTC, interval="1m")


def test_candle_non_numeric_prices_fail_closed() -> None:
    with pytest.raises(HyperliquidProtocolError, match="open must be numeric"):
        parse_candle(candle(o="not-a-number"), BTC, interval="1m")


def test_candle_nan_fails_closed() -> None:
    with pytest.raises(HyperliquidProtocolError, match="finite"):
        parse_candle(candle(c="nan"), BTC, interval="1m")


def test_candle_missing_price_key_fails_closed() -> None:
    with pytest.raises(HyperliquidProtocolError, match="close must be numeric"):
        parse_candle(candle(c=None), BTC, interval="1m")


def test_candle_non_mapping_row_fails_closed() -> None:
    with pytest.raises(HyperliquidProtocolError, match="must be an object"):
        parse_candle([1, 2], BTC, interval="1m")


# --- l2Book -----------------------------------------------------------------

def test_l2_book_parses_into_a_canonical_book() -> None:
    book = parse_l2_book(l2_book(), BTC)

    assert isinstance(book, OrderBook)
    assert book.timestamp == _t(T0 + STEP_MS)
    assert [level.price for level in book.bids] == [107.5, 107.0]
    assert [level.quantity for level in book.asks] == [3.0, 5.5]


def test_l2_book_needs_at_least_two_level_arrays() -> None:
    with pytest.raises(HyperliquidProtocolError, match="at least 2"):
        parse_l2_book(l2_book(levels=[[]]), BTC)


def test_l2_book_rejects_unknown_extra_level_arrays() -> None:
    payload = l2_book(levels=[[], [], []])
    with pytest.raises(HyperliquidProtocolError, match="exactly 2"):
        parse_l2_book(payload, BTC)


def test_l2_book_non_numeric_prices_fail_closed() -> None:
    payload = l2_book(levels=[[{"n": 1, "px": "high", "sz": "1.0"}], []])
    with pytest.raises(HyperliquidProtocolError, match="bid price must be numeric"):
        parse_l2_book(payload, BTC)


def test_l2_book_level_without_count_fails_closed() -> None:
    payload = l2_book(levels=[[{"n": "3", "px": "107.5", "sz": "2.0"}], []])
    with pytest.raises(HyperliquidProtocolError, match="count must be an int"):
        parse_l2_book(payload, BTC)


def test_l2_book_disordered_bids_fail_closed() -> None:
    payload = l2_book(
        levels=[
            [{"n": 1, "px": "106.0", "sz": "1.0"}, {"n": 1, "px": "107.0", "sz": "1.0"}],
            [],
        ]
    )
    with pytest.raises(HyperliquidProtocolError, match="values invalid"):
        parse_l2_book(payload, BTC)


def test_l2_book_symbol_mismatch_fails_closed() -> None:
    with pytest.raises(HyperliquidProtocolError, match="does not match instrument"):
        parse_l2_book(l2_book(coin="ETH"), BTC)


# --- trades -----------------------------------------------------------------

def test_trades_parse_with_aggressor_sides() -> None:
    events = parse_trades([trade(), trade(side="B", tid=8)], BTC)

    assert [event.aggressor_side for event in events] == [Side.BUY, Side.SELL]
    assert [event.venue_sequence for event in events] == [7, 8]
    assert events[0].timestamp == _t(T0 + STEP_MS)


def test_trades_reject_unknown_sides() -> None:
    with pytest.raises(HyperliquidProtocolError, match="unknown trade side"):
        parse_trades([trade(side="HODL")], BTC)


def test_trades_reject_non_lists() -> None:
    with pytest.raises(HyperliquidProtocolError, match="must be a list"):
        parse_trades({"coin": "BTC"}, BTC)


def test_trades_reject_wrong_symbols() -> None:
    with pytest.raises(HyperliquidProtocolError, match="does not match instrument"):
        parse_trades([trade(coin="ETH")], BTC)


# --- funding ----------------------------------------------------------------

def test_funding_parses_rates_and_premiums() -> None:
    rates = parse_funding([funding()])

    assert len(rates) == 1
    assert rates[0].coin == "BTC"
    assert rates[0].rate == 0.00001
    assert rates[0].premium == 0.00002
    assert rates[0].timestamp == _t(T0)


def test_funding_non_numeric_rate_fails_closed() -> None:
    with pytest.raises(HyperliquidProtocolError, match="fundingRate must be numeric"):
        parse_funding([funding(fundingRate="ten")])


def test_funding_rejects_non_lists() -> None:
    with pytest.raises(HyperliquidProtocolError, match="must be a list"):
        parse_funding({})


# --- allMids / meta / spotMeta -----------------------------------------------

def test_all_mids_parses_float_string_prices() -> None:
    mids = parse_all_mids({"mids": {"BTC": "107.25", "ETH": "3500.5"}, "time": T0})

    assert mids == {"BTC": 107.25, "ETH": 3500.5}


def test_all_mids_without_mids_object_fails_closed() -> None:
    with pytest.raises(HyperliquidProtocolError, match="'mids' object"):
        parse_all_mids({"time": T0})


def test_all_mids_non_numeric_price_fails_closed() -> None:
    with pytest.raises(HyperliquidProtocolError, match="mid price"):
        parse_all_mids({"mids": {"BTC": "free"}, "time": T0})


def test_meta_parses_the_perp_universe() -> None:
    payload = {
        "universe": [
            {"name": "BTC", "szDecimals": 5, "maxLeverage": 50, "onlyIsolated": False},
            {"name": "ETH", "szDecimals": 4, "maxLeverage": 25, "onlyIsolated": True},
        ],
        "dexes": [],
    }

    parsed = parse_meta(payload)

    assert parsed == [
        PerpMeta(name="BTC", sz_decimals=5, max_leverage=50, only_isolated=False),
        PerpMeta(name="ETH", sz_decimals=4, max_leverage=25, only_isolated=True),
    ]


def test_meta_missing_key_fails_closed() -> None:
    with pytest.raises(HyperliquidProtocolError, match="missing key"):
        parse_meta({"universe": [{"name": "BTC"}]})


def test_spot_meta_resolves_token_pairs() -> None:
    payload = {
        "tokens": [{"name": "BTC", "index": 0}, {"name": "USDC", "index": 2}],
        "universe": [{"name": "BTC", "tokens": [0, 2], "index": 0}],
    }

    parsed = parse_spot_meta(payload)

    assert parsed == [SpotPair(name="BTC", base="BTC", quote="USDC")]


def test_spot_meta_unknown_token_index_fails_closed() -> None:
    payload = {
        "tokens": [{"name": "USDC", "index": 2}],
        "universe": [{"name": "BTC", "tokens": [0, 2], "index": 0}],
    }
    with pytest.raises(HyperliquidProtocolError, match="unknown token indices"):
        parse_spot_meta(payload)


# --- time -------------------------------------------------------------------

def test_ms_to_utc_converts_and_rejects_junk() -> None:
    assert ms_to_utc(T0) == _t(T0)
    assert ms_to_utc(str(T0)) == _t(T0)
    with pytest.raises(HyperliquidProtocolError, match="milliseconds"):
        ms_to_utc(True)
    with pytest.raises(HyperliquidProtocolError, match="milliseconds"):
        ms_to_utc("soon")
    with pytest.raises(HyperliquidProtocolError, match="negative"):
        ms_to_utc(-1)
