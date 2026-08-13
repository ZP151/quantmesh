"""Moomoo wire payload → canonical model mapping tests (issue #26, Phase B).

The adapter is pure: wire payload in, canonical models out, with
fail-closed validation of every contract violation (ADR-0004 extension).
Times arrive as venue-local wall-clock strings — the SDK's contract —
and must land as aware UTC instants; the DST case is what proves
zoneinfo is doing real timezone work, not applying a fixed offset.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from moomoo_wire import (
    AAPL,
    HK_00700_1D,
    TENCENT,
    US_AAPL_1D,
    US_AAPL_5M,
    US_AAPL_QUOTE,
    US_AAPL_TICKER,
)

from quantmesh.domain.models import Side
from quantmesh.moomoo.market_data import MoomooDataAdapter, market_tz, sdk_code
from quantmesh.moomoo.opend import OpenDProtocolError

adapter = MoomooDataAdapter()


# --- kline → Bar -----------------------------------------------------------


def test_daily_us_bars_convert_eastern_time_to_utc() -> None:
    bars = adapter.history_kline_to_bars(AAPL, US_AAPL_1D)
    assert len(bars) == 3
    assert bars[0].timestamp == datetime(2026, 8, 3, 4, 0, tzinfo=UTC)
    assert bars[2].timestamp == datetime(2026, 8, 5, 4, 0, tzinfo=UTC)
    assert bars[0].instrument == AAPL
    assert bars[0].interval == "1d"
    assert bars[0].volume == 1000.0


def test_history_pages_map_in_order_without_duplicate_rows() -> None:
    first = {**US_AAPL_1D, "rows": US_AAPL_1D["rows"][:2]}
    second = {**US_AAPL_1D, "rows": US_AAPL_1D["rows"][2:]}

    bars = adapter.history_pages_to_bars(AAPL, [first, second])

    assert [bar.close for bar in bars] == [204.0, 207.0, 209.5]


def test_history_pages_reject_duplicate_boundary_row() -> None:
    first = {**US_AAPL_1D, "rows": US_AAPL_1D["rows"][:2]}
    second = {**US_AAPL_1D, "rows": US_AAPL_1D["rows"][1:]}

    with pytest.raises(OpenDProtocolError, match="duplicate history row"):
        adapter.history_pages_to_bars(AAPL, [first, second])


def test_history_row_code_must_match_requested_instrument() -> None:
    payload = {
        **US_AAPL_1D,
        "rows": [dict(US_AAPL_1D["rows"][0], code="US.NVDA")],
    }

    with pytest.raises(OpenDProtocolError, match="row 0 code"):
        adapter.history_kline_to_bars(AAPL, payload)


@pytest.mark.parametrize("bad_value", [True, False, "100.0", float("inf"), float("nan")])
def test_history_ohlcv_requires_finite_non_boolean_numbers(bad_value) -> None:
    payload = {
        **US_AAPL_1D,
        "rows": [dict(US_AAPL_1D["rows"][0], close=bad_value)],
    }

    with pytest.raises(OpenDProtocolError, match="row 0 close"):
        adapter.history_kline_to_bars(AAPL, payload)


def test_intraday_us_bars_convert_eastern_time_to_utc() -> None:
    bars = adapter.history_kline_to_bars(AAPL, US_AAPL_5M)
    assert [bar.timestamp for bar in bars] == [
        datetime(2026, 8, 3, 13, 30, tzinfo=UTC),
        datetime(2026, 8, 3, 13, 35, tzinfo=UTC),
        datetime(2026, 8, 3, 13, 40, tzinfo=UTC),
    ]
    assert all(bar.interval == "5m" for bar in bars)


def test_intraday_bar_rejects_date_only_time_key() -> None:
    payload = {
        **US_AAPL_1D,
        "interval": "1m",
        "rows": [dict(US_AAPL_1D["rows"][0], time_key="2026-08-03")],
    }

    with pytest.raises(OpenDProtocolError, match="unparseable"):
        adapter.history_kline_to_bars(AAPL, payload)


def test_us_bars_respect_daylight_saving_boundary() -> None:
    payload = {
        "code": "US.AAPL",
        "interval": "1m",
        "autype": "None",
        "rows": [
            {
                "code": "US.AAPL",
                "time_key": "2026-01-05 09:30:00",
                "open": 1.0,
                "high": 2.0,
                "low": 1.0,
                "close": 2.0,
                "volume": 10,
            }
        ],
    }
    (bar,) = adapter.history_kline_to_bars(AAPL, payload)
    # January is EST (UTC-5), so 09:30 local is 14:30 UTC — not 13:30
    # (which would mean the DST offset was applied year-round).
    assert bar.timestamp == datetime(2026, 1, 5, 14, 30, tzinfo=UTC)


def test_hk_bars_convert_beijing_time_to_utc() -> None:
    bars = adapter.history_kline_to_bars(TENCENT, HK_00700_1D)
    # Midnight HKT is 16:00 UTC on the previous day.
    assert [bar.timestamp for bar in bars] == [
        datetime(2026, 8, 2, 16, 0, tzinfo=UTC),
        datetime(2026, 8, 3, 16, 0, tzinfo=UTC),
    ]


def test_extra_vendor_keys_are_tolerated() -> None:
    payload = {
        "code": "US.AAPL",
        "interval": "1d",
        "autype": "None",
        "rows": [
            {
                "code": "US.AAPL",
                "time_key": "2026-08-03",
                "open": 200.0,
                "high": 205.0,
                "low": 199.0,
                "close": 204.0,
                "volume": 1000,
                "pe_ratio": 25.4,
                "change_rate": 2.2,
            }
        ],
    }
    (bar,) = adapter.history_kline_to_bars(AAPL, payload)
    assert bar.close == 204.0


@pytest.mark.parametrize("dropped", ["code", "time_key", "open", "high", "low", "close", "volume"])
def test_kline_row_missing_required_key_fails_closed(dropped: str) -> None:
    row = {key: value for key, value in US_AAPL_1D["rows"][1].items() if key != dropped}
    payload = {
        "code": "US.AAPL",
        "interval": "1d",
        "autype": "None",
        "rows": [row, dict(US_AAPL_1D["rows"][2])],
    }
    with pytest.raises(OpenDProtocolError, match="row 0"):
        adapter.history_kline_to_bars(AAPL, payload)


def test_kline_row_non_mapping_fails_closed() -> None:
    payload = {"code": "US.AAPL", "interval": "1d", "autype": "None", "rows": [[200.0]]}
    with pytest.raises(OpenDProtocolError, match="row 0"):
        adapter.history_kline_to_bars(AAPL, payload)


def test_kline_row_invalid_price_fails_with_row_attribution() -> None:
    payload = {
        "code": "US.AAPL",
        "interval": "1d",
        "autype": "None",
        "rows": [
            dict(US_AAPL_1D["rows"][0]),
            dict(US_AAPL_1D["rows"][1], close=-1.0),
        ],
    }
    with pytest.raises(OpenDProtocolError, match="row 1"):
        adapter.history_kline_to_bars(AAPL, payload)


def test_kline_unparseable_time_fails_closed() -> None:
    payload = {
        "code": "US.AAPL",
        "interval": "1d",
        "autype": "None",
        "rows": [dict(US_AAPL_1D["rows"][0], time_key="yesterday")],
    }
    with pytest.raises(OpenDProtocolError, match="unparseable"):
        adapter.history_kline_to_bars(AAPL, payload)


def test_kline_unknown_market_fails_closed() -> None:
    payload = {"code": "JP.AAPL", "interval": "1d", "autype": "None", "rows": US_AAPL_1D["rows"]}
    with pytest.raises(OpenDProtocolError, match="timezone metadata"):
        adapter.history_kline_to_bars(AAPL, payload)


def test_kline_unqualified_code_fails_closed() -> None:
    payload = {"code": "AAPL", "interval": "1d", "autype": "None", "rows": US_AAPL_1D["rows"]}
    with pytest.raises(OpenDProtocolError, match="market-qualified"):
        adapter.history_kline_to_bars(AAPL, payload)


def test_kline_code_symbol_mismatch_fails_closed() -> None:
    payload = {"code": "US.MSFT", "interval": "1d", "autype": "None", "rows": US_AAPL_1D["rows"]}
    with pytest.raises(OpenDProtocolError, match="does not match instrument"):
        adapter.history_kline_to_bars(AAPL, payload)


def test_kline_unknown_autype_fails_closed() -> None:
    payload = {"code": "US.AAPL", "interval": "1d", "autype": "bogus", "rows": US_AAPL_1D["rows"]}
    with pytest.raises(OpenDProtocolError, match="autype"):
        adapter.history_kline_to_bars(AAPL, payload)


def test_kline_payload_not_a_mapping_fails_closed() -> None:
    with pytest.raises(OpenDProtocolError, match="payload must be a mapping"):
        adapter.history_kline_to_bars(AAPL, [])  # type: ignore[arg-type]


# --- ticker → TradeEvent ----------------------------------------------------


def test_ticker_maps_to_trades() -> None:
    trades = adapter.ticker_to_trades(AAPL, US_AAPL_TICKER)
    assert len(trades) == 3
    assert trades[0].timestamp == datetime(2026, 8, 3, 13, 30, 1, tzinfo=UTC)
    assert trades[0].price == 200.0
    assert trades[0].quantity == 100.0
    assert trades[0].aggressor_side is Side.BUY
    assert trades[0].venue_sequence == 5001
    assert trades[1].aggressor_side is Side.SELL
    assert trades[2].aggressor_side is None  # NEUTRAL has no aggressor


def test_ticker_sequence_is_optional() -> None:
    payload = {
        "code": "US.AAPL",
        "rows": [
            {
                "time": "2026-08-03 09:30:01",
                "price": 200.0,
                "volume": 100,
                "direction": "BUY",
            }
        ],
    }
    (trade,) = adapter.ticker_to_trades(AAPL, payload)
    assert trade.venue_sequence is None


def test_ticker_unknown_direction_fails_closed() -> None:
    payload = {
        "code": "US.AAPL",
        "rows": [
            {
                "time": "2026-08-03 09:30:01",
                "price": 200.0,
                "volume": 100,
                "direction": "HOLD",
            }
        ],
    }
    with pytest.raises(OpenDProtocolError, match="direction"):
        adapter.ticker_to_trades(AAPL, payload)


def test_ticker_missing_time_fails_closed() -> None:
    payload = {"code": "US.AAPL", "rows": [{"price": 200.0, "volume": 100}]}
    with pytest.raises(OpenDProtocolError, match="row 0"):
        adapter.ticker_to_trades(AAPL, payload)


def test_ticker_bad_sequence_type_fails_closed() -> None:
    payload = {
        "code": "US.AAPL",
        "rows": [
            {
                "time": "2026-08-03 09:30:01",
                "price": 200.0,
                "volume": 100,
                "sequence": 5001.5,
            }
        ],
    }
    with pytest.raises(OpenDProtocolError, match="sequence"):
        adapter.ticker_to_trades(AAPL, payload)


# --- stock quote → Quote ----------------------------------------------------


def test_quote_maps_to_canonical_quote() -> None:
    quote = adapter.stock_quote_to_quote(AAPL, US_AAPL_QUOTE)
    assert quote.last == 204.0
    assert quote.volume == 1000.0
    assert quote.bid is None
    assert quote.ask is None
    # 16:00 Eastern (EDT) is 20:00 UTC.
    assert quote.timestamp == datetime(2026, 8, 3, 20, 0, tzinfo=UTC)


def test_quote_without_data_time_defaults_to_midnight() -> None:
    payload = {
        "rows": [{"code": "US.AAPL", "data_date": "2026-08-03", "last_price": 204.0}],
    }
    quote = adapter.stock_quote_to_quote(AAPL, payload)
    assert quote.timestamp == datetime(2026, 8, 3, 4, 0, tzinfo=UTC)


def test_quote_requires_last_price() -> None:
    payload = {
        "rows": [{"code": "US.AAPL", "data_date": "2026-08-03", "data_time": "16:00:00"}],
    }
    with pytest.raises(OpenDProtocolError, match="last_price"):
        adapter.stock_quote_to_quote(AAPL, payload)


def test_quote_multiple_rows_fail_closed() -> None:
    payload = {"rows": US_AAPL_QUOTE["rows"] + US_AAPL_QUOTE["rows"]}
    with pytest.raises(OpenDProtocolError, match="exactly one row"):
        adapter.stock_quote_to_quote(AAPL, payload)


# --- shared helpers ----------------------------------------------------------


def test_market_tz_resolves_vendor_local_zones() -> None:
    assert str(market_tz("US.AAPL")) == str(ZoneInfo("America/New_York"))
    assert str(market_tz("HK.00700")) == str(ZoneInfo("Asia/Hong_Kong"))


def test_market_tz_rejects_unknown_market() -> None:
    with pytest.raises(OpenDProtocolError, match="timezone metadata"):
        market_tz("JP.7203")


def test_sdk_code_builds_market_qualified_code() -> None:
    assert sdk_code(AAPL) == "US.AAPL"
    assert sdk_code(TENCENT) == "HK.00700"


def test_sdk_code_requires_market_metadata() -> None:
    bare = AAPL.model_copy(update={"metadata": {}})
    with pytest.raises(ValueError, match="market"):
        sdk_code(bare)
