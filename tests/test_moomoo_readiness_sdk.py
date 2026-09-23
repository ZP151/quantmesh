"""Exercise readiness through the real client/transport without vendor access."""

import json
import sys
from types import SimpleNamespace

import pytest

from quantmesh.moomoo.opend import (
    MoomooOpenDClient,
    OpenDProtocolError,
    OpenDUnavailableError,
    SdkTransport,
)
from quantmesh.moomoo.readiness import run_readiness
from quantmesh.moomoo.readiness_worker import main as worker_main


class Table:
    def __init__(self, rows):
        self.rows = rows

    def to_dict(self, orientation):
        assert orientation == "records"
        return self.rows


@pytest.fixture
def sdk(monkeypatch):
    events = []

    class QuoteContext:
        def __init__(self, **kwargs):
            self.subscribed = False
            events.append("open")

        def subscribe(self, codes, subtypes, *, subscribe_push):
            assert codes == ["US.AAPL"]
            assert subtypes == ["QUOTE"]
            assert subscribe_push is False
            events.append("subscribe")
            self.subscribed = True
            return 0, None

        def get_stock_quote(self, codes):
            events.append("quote")
            if not self.subscribed:
                return -1, "Please subscribe to Basic data first"
            return 0, Table([{
                "code": codes[0], "data_date": "2026-09-23",
                "data_time": "10:00:00", "last_price": 210, "volume": 1000,
            }])

        def request_history_kline(self, code, **kwargs):
            events.append("history")
            return 0, Table([{
                "code": code, "time_key": "2026-09-22",
                "open": 209, "high": 212, "low": 208, "close": 210, "volume": 1000,
            }]), None

        def close(self):
            events.append("close")

    def forbidden_trade(**kwargs):
        events.append("trade")
        raise AssertionError("readiness must never construct a trade context")

    module = SimpleNamespace(
        OpenQuoteContext=QuoteContext, OpenSecTradeContext=forbidden_trade,
        SubType=SimpleNamespace(QUOTE="QUOTE"),
        KLType=SimpleNamespace(K_DAY="K_DAY"),
        AuType=SimpleNamespace(NONE="NONE", QFQ="QFQ", HFQ="HFQ"),
    )
    monkeypatch.setitem(sys.modules, "moomoo", module)
    return module, events


def transport():
    return SdkTransport(host="127.0.0.1", port=11111, connect_timeout_s=1, request_timeout_s=1)


def test_readiness_real_call_chain_is_quote_only(sdk):
    _, events = sdk
    report = run_readiness(MoomooOpenDClient(transport()), ["US.AAPL"])
    assert report.status == "ready"
    assert "trade" not in events
    assert report.capabilities.order is False
    assert report.capabilities.order_query is False
    assert report.order_checked is False
    assert events.count("open") == events.count("close")


def test_quote_subscribes_before_read_and_closes(sdk):
    _, events = sdk
    payload = transport().stock_quote(["US.AAPL"])
    assert payload["rows"][0]["last_price"] == 210
    assert events == ["open", "subscribe", "quote", "close"]


def test_failed_subscription_never_reads_quote_and_closes(sdk, monkeypatch):
    module, events = sdk
    monkeypatch.setattr(module.OpenQuoteContext, "subscribe", lambda *a, **kw: (-1, "denied"))
    with pytest.raises(OpenDUnavailableError):
        transport().stock_quote(["US.AAPL"])
    assert events == ["open", "close"]


@pytest.mark.parametrize("result", [(False, None), (0.0, None), (0,), (0, None, None)])
def test_malformed_subscription_is_protocol_error_and_closes(sdk, monkeypatch, result):
    module, events = sdk
    monkeypatch.setattr(module.OpenQuoteContext, "subscribe", lambda *a, **kw: result)
    with pytest.raises(OpenDProtocolError):
        transport().stock_quote(["US.AAPL"])
    assert events == ["open", "close"]


@pytest.mark.parametrize("malformed", [False, True])
def test_worker_report_uses_real_quote_only_chain(sdk, monkeypatch, tmp_path, malformed):
    _, events = sdk
    request = tmp_path / "request.json"
    output = tmp_path / "output.json"
    request.write_text(json.dumps({
        "host": "127.0.0.1", "port": 11111, "codes": ["US.AAPL"],
        "connect_timeout_s": 1, "request_timeout_s": 1,
    }), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["worker", str(request), str(output)])
    if malformed:
        monkeypatch.setattr(SdkTransport, "probe_market_data", lambda self: "SECRET_SENTINEL")
    assert worker_main() == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["status"] == ("protocol_error" if malformed else "ready")
    assert payload["order_checked"] is False
    assert "SECRET_SENTINEL" not in output.read_text(encoding="utf-8")
    assert "trade" not in events
