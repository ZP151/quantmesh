"""Scoped US current-minute candles: SDK safety and source normalization."""

import sys
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.moomoo.opend import (
    MoomooOpenDClient,
    OpenDProtocolError,
    OpenDUnavailableError,
    SdkTransport,
)


def instrument(symbol="AAPL", **kwargs):
    return Instrument(
        symbol=symbol, venue=kwargs.get("venue", Venue.MOOMOO),
        instrument_type=kwargs.get("instrument_type", InstrumentType.EQUITY),
        metadata={"market": kwargs.get("market", "US")},
    )


def row(time_key="2026-10-08 09:31:00", **values):
    return {
        "code": "US.AAPL", "time_key": time_key,
        "open": 210, "high": 212, "low": 209, "close": 211, "volume": 100,
        **values,
    }


def payload(rows=None, **values):
    return {
        "code": "US.AAPL", "interval": "1m", "autype": "None", "session": "regular",
        "rows": [row()] if rows is None else rows, **values,
    }


def normalize(value, requested=None):
    from quantmesh.moomoo.minute_candles import minute_candles

    return minute_candles(requested or instrument(), value)


@pytest.fixture
def sdk(monkeypatch):
    events = []

    class Table:
        def to_dict(self, orientation):
            assert orientation == "records"
            return [row()]

    class QuoteContext:
        subscription_result = (0, None)
        candle_result = (0, Table())

        def __init__(self, **kwargs):
            events.append("open")

        def subscribe(self, codes, subtypes, **kwargs):
            events.append(("subscribe", codes, subtypes, kwargs))
            return self.subscription_result

        def get_cur_kline(self, code, **kwargs):
            events.append(("read", code, kwargs))
            return self.candle_result

        def close(self):
            events.append("close")

    def forbidden_trade(**kwargs):
        raise AssertionError("current candles never open a trade context")

    module = SimpleNamespace(
        OpenQuoteContext=QuoteContext, OpenSecTradeContext=forbidden_trade,
        SubType=SimpleNamespace(K_1M="K_1M"), KLType=SimpleNamespace(K_1M="K_1M"),
        AuType=SimpleNamespace(NONE="NONE"), Session=SimpleNamespace(RTH="RTH"),
    )
    monkeypatch.setitem(sys.modules, "moomoo", module)
    return module, events


def transport():
    return SdkTransport(host="127.0.0.1", port=11111, connect_timeout_s=1, request_timeout_s=1)


def test_sdk_current_candles_explicit_raw_regular_subscription_and_cleanup(sdk):
    _, events = sdk
    assert MoomooOpenDClient(transport()).current_kline("US.AAPL", num=390) == payload()
    assert events == [
        "open",
        ("subscribe", ["US.AAPL"], ["K_1M"], {"subscribe_push": False, "session": "RTH"}),
        ("read", "US.AAPL", {"num": 390, "ktype": "K_1M", "autype": "NONE"}),
        "close",
    ]


@pytest.mark.parametrize("stage", ["subscription_result", "candle_result"])
@pytest.mark.parametrize("result,error", [
    ((False, None), OpenDProtocolError), ((0.0, None), OpenDProtocolError),
    ((0,), OpenDProtocolError), ((0, None, None), OpenDProtocolError),
    ((-1, "unavailable"), OpenDUnavailableError),
])
def test_sdk_strict_status_and_cleanup(sdk, stage, result, error):
    module, events = sdk
    setattr(module.OpenQuoteContext, stage, result)
    with pytest.raises(error):
        transport().current_kline("US.AAPL", num=390)
    assert events[-1] == "close"
    if stage == "subscription_result":
        assert not any(isinstance(event, tuple) and event[0] == "read" for event in events)


@pytest.mark.parametrize("method", ["subscribe", "get_cur_kline"])
def test_sdk_exception_closes_context(sdk, monkeypatch, method):
    module, events = sdk

    def fail(*args, **kwargs):
        raise TimeoutError("request timed out")

    monkeypatch.setattr(module.OpenQuoteContext, method, fail)
    with pytest.raises(OpenDUnavailableError):
        transport().current_kline("US.AAPL", num=1)
    assert events[-1] == "close"


@pytest.mark.parametrize("code,num", [
    ("US.MSFT", 390), ("HK.AAPL", 390), ("AAPL", 390), (None, 390),
    ("US.AAPL", True), ("US.AAPL", 0), ("US.AAPL", 391), ("US.AAPL", 1.0),
])
def test_invalid_request_never_reaches_sdk(sdk, code, num):
    _, events = sdk
    for boundary in (transport(), MoomooOpenDClient(transport())):
        with pytest.raises(ValueError):
            boundary.current_kline(code, num=num)
    assert events == []


@pytest.mark.parametrize("time_key,expected", [
    ("2026-10-08 09:31:00", datetime(2026, 10, 8, 13, 30, tzinfo=UTC)),
    ("2026-01-08 09:31:00", datetime(2026, 1, 8, 14, 30, tzinfo=UTC)),
])
def test_eastern_end_labels_map_to_utc_start_with_dst(time_key, expected):
    normalized = normalize(payload([row(time_key)]))
    assert normalized == [{
        "timestamp": expected, "provider_time_key": time_key,
        "provider_end": expected.replace(minute=31),
        "open": 210.0, "high": 212.0, "low": 209.0, "close": 211.0, "volume": 100.0,
    }]


@pytest.mark.parametrize("date,last", [("2026-10-08", "16:00"), ("2026-11-27", "13:00")])
def test_regular_session_filters_open_label_and_extended_and_obeys_early_close(date, last):
    rows = [row(f"{date} 09:30:00"), row(f"{date} 09:31:00"), row(f"{date} {last}:00"),
            row(f"{date} 16:01:00")]
    result = normalize(payload(rows))
    assert [c["provider_time_key"] for c in result] == [rows[1]["time_key"], rows[2]["time_key"]]


def test_holiday_and_weekend_rows_are_not_regular_session_candles():
    assert normalize(payload([row("2026-07-03 10:01:00"), row("2026-07-04 10:01:00")])) == []


@pytest.mark.parametrize("rows", [
    [row(), row()], [row("2026-10-08 09:32:00"), row()],
    [row("2026-10-08 09:31:01")], [row("2026-10-08")],
    [row("2026-10-08 09:31:00+00:00")], [row(code="US.NVDA")],
])
def test_malformed_time_order_or_identity_is_rejected(rows):
    with pytest.raises(OpenDProtocolError):
        normalize(payload(rows))


@pytest.mark.parametrize("key,value", [
    ("open", 0), ("high", float("inf")), ("low", float("nan")), ("close", True),
    ("volume", -1), ("volume", "100"), ("high", 208), ("low", 213),
])
def test_invalid_source_prices_and_volume_fail_closed(key, value):
    with pytest.raises(OpenDProtocolError):
        normalize(payload([row(**{key: value})]))


@pytest.mark.parametrize("value", [
    None, [], payload(interval="1d"), payload(autype="qfq"), payload(session="extended"),
    payload(code="US.NVDA"), payload(rows=[None]), payload(rows=[row()] * 391),
])
def test_payload_contract_fails_closed(value):
    with pytest.raises(OpenDProtocolError):
        normalize(value)


@pytest.mark.parametrize("requested", [
    instrument("MSFT"), instrument(market="HK"), instrument(venue=Venue.INTERNAL),
    instrument(instrument_type=InstrumentType.ETF),
])
def test_only_scoped_us_moomoo_equities_are_supported(requested):
    with pytest.raises(ValueError):
        normalize(payload(), requested)


def test_nvda_empty_and_zero_volume_are_admitted():
    assert normalize(payload([])) == []
    value = payload([row(code="US.NVDA", volume=0)], code="US.NVDA")
    assert normalize(value, instrument("NVDA"))[0]["volume"] == 0
