"""Exercise polling through the real adapter with subscription-enforcing SDK."""

import asyncio
import sys
from types import SimpleNamespace

import pytest

from quantmesh.live.moomoo import DEFAULT_POLL_INTERVAL, MoomooVenueTransport
from quantmesh.moomoo.opend import (
    MoomooOpenDClient,
    OpenDProtocolError,
    OpenDUnavailableError,
    SdkTransport,
)


@pytest.fixture
def sdk(monkeypatch):
    events = []

    class Table:
        def __init__(self, rows):
            self.rows = rows

        def to_dict(self, orientation):
            assert orientation == "records"
            return self.rows

    class QuoteContext:
        def __init__(self, **kwargs):
            self.subscriptions = set()
            events.append("open")

        def subscribe(self, codes, subtypes, *, subscribe_push):
            assert subscribe_push is False
            self.subscriptions.update((code, subtype) for code in codes for subtype in subtypes)
            events.append(("subscribe", codes, subtypes))
            return 0, None

        def get_stock_quote(self, codes):
            assert all((code, "QUOTE") in self.subscriptions for code in codes)
            events.append("quote")
            return 0, Table([{
                "code": code, "data_date": "2026-09-23", "data_time": "10:00:00",
                "last_price": 210, "volume": 1000,
            } for code in codes])

        def get_rt_ticker(self, code, *, num):
            events.append(("ticker", code, num))
            if (code, "TICKER") not in self.subscriptions:
                return -1, "Please subscribe to TICKER first"
            return 0, Table([{
                "time": "2026-09-23 10:00:01", "sequence": 17, "price": 210.5,
                "volume": 100, "turnover": 21050, "ticker_direction": "BUY", "type": "AUTO",
            }])

        def close(self):
            events.append("close")

    def forbidden_trade(**kwargs):
        events.append("trade")
        raise AssertionError("market polling must not create a trading context")

    module = SimpleNamespace(
        OpenQuoteContext=QuoteContext, OpenSecTradeContext=forbidden_trade,
        SubType=SimpleNamespace(QUOTE="QUOTE", TICKER="TICKER"),
    )
    monkeypatch.setitem(sys.modules, "moomoo", module)
    return module, events


def transport():
    return SdkTransport(host="127.0.0.1", port=11111, connect_timeout_s=1, request_timeout_s=1)


def test_real_poll_chain_is_quote_only_and_preserves_source(sdk):
    _, events = sdk

    async def run():
        wire = MoomooVenueTransport(MoomooOpenDClient(transport()))
        try:
            wire.connect()
            for symbol in ("AAPL", "NVDA"):
                wire.send({"symbol": symbol, "code": f"US.{symbol}"})
            frames = [await asyncio.wait_for(wire.recv(), 2) for _ in range(3)]
            assert [frame["kind"] for frame in frames] == [
                "stock_quote", "rt_ticker", "rt_ticker",
            ]
            assert [r["code"] for r in frames[0]["payload"]["rows"]] == ["US.AAPL", "US.NVDA"]
            assert frames[0]["payload"]["rows"][0]["data_time"] == "10:00:00"
            for frame in frames[1:]:
                assert frame["payload"]["rows"][0] == {
                    "time": "2026-09-23 10:00:01", "sequence": 17, "price": 210.5,
                    "volume": 100, "turnover": 21050, "direction": "BUY", "type": "AUTO",
                }
            assert "trade" not in events
            assert events.count("open") == events.count("close")
            assert DEFAULT_POLL_INTERVAL.total_seconds() == 5
        finally:
            wire.close()

    asyncio.run(run())


def test_ticker_subscribes_before_read_and_closes(sdk):
    _, events = sdk
    payload = transport().rt_ticker("US.AAPL", num=100)
    assert payload["rows"][0]["sequence"] == 17
    assert events == [
        "open", ("subscribe", ["US.AAPL"], ["TICKER"]),
        ("ticker", "US.AAPL", 100), "close",
    ]


@pytest.mark.parametrize("result,error", [
    ((-1, "denied"), OpenDUnavailableError),
    ((False, None), OpenDProtocolError),
    ((0.0, None), OpenDProtocolError),
    ((0,), OpenDProtocolError),
    ((0, None, None), OpenDProtocolError),
])
def test_failed_ticker_subscription_never_reads_and_closes(sdk, monkeypatch, result, error):
    module, events = sdk
    monkeypatch.setattr(module.OpenQuoteContext, "subscribe", lambda *a, **kw: result)
    with pytest.raises(error):
        transport().rt_ticker("US.AAPL", num=100)
    assert events == ["open", "close"]


def test_ticker_subscription_exception_closes(sdk, monkeypatch):
    module, events = sdk

    def fail(*args, **kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(module.OpenQuoteContext, "subscribe", fail)
    with pytest.raises(OpenDUnavailableError):
        transport().rt_ticker("US.AAPL", num=100)
    assert events == ["open", "close"]
