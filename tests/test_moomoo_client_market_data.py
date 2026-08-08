"""MoomooOpenDClient market-data methods (issue #26, Phase B).

The client is a thin typed boundary: validate the request, delegate to
the transport, propagate typed failures. Wire-shaped payloads come back
untouched — mapping to canonical models is the adapter's job.
"""

import pytest
from moomoo_wire import US_AAPL_1D, WireTransport

from quantmesh.moomoo.opend import MoomooOpenDClient, OpenDTransport, OpenDUnavailableError


def test_history_kline_delegates_with_request_args() -> None:
    transport = WireTransport()
    payload = MoomooOpenDClient(transport).history_kline(
        "US.AAPL", interval="1d", start="2026-08-01", end="2026-08-05"
    )
    assert payload == US_AAPL_1D
    assert transport.kline_requests == [("US.AAPL", "1d", "2026-08-01", "2026-08-05", "None")]


def test_history_kline_defaults_to_raw_autype_and_open_bounds() -> None:
    transport = WireTransport()
    MoomooOpenDClient(transport).history_kline("US.AAPL", interval="1d")
    assert transport.kline_requests == [("US.AAPL", "1d", None, None, "None")]


def test_history_kline_passes_explicit_autype() -> None:
    transport = WireTransport()
    MoomooOpenDClient(transport).history_kline("US.AAPL", interval="1d", autype="qfq")
    assert transport.kline_requests == [("US.AAPL", "1d", None, None, "qfq")]


def test_history_kline_rejects_unparseable_interval() -> None:
    transport = WireTransport()
    with pytest.raises(ValueError, match="interval"):
        MoomooOpenDClient(transport).history_kline("US.AAPL", interval="1mo")
    assert transport.kline_requests == []


def test_history_kline_rejects_unknown_autype() -> None:
    transport = WireTransport()
    with pytest.raises(ValueError, match="autype"):
        MoomooOpenDClient(transport).history_kline("US.AAPL", interval="1d", autype="bogus")
    assert transport.kline_requests == []


def test_rt_ticker_delegates_with_default_num() -> None:
    transport = WireTransport()
    MoomooOpenDClient(transport).rt_ticker("US.AAPL")
    assert transport.ticker_requests == [("US.AAPL", 500)]


@pytest.mark.parametrize("num", [0, -1, 1001, 1.5])
def test_rt_ticker_rejects_invalid_num(num: object) -> None:
    transport = WireTransport()
    with pytest.raises(ValueError, match="num"):
        MoomooOpenDClient(transport).rt_ticker("US.AAPL", num=num)  # type: ignore[arg-type]
    assert transport.ticker_requests == []


def test_stock_quote_delegates() -> None:
    transport = WireTransport()
    MoomooOpenDClient(transport).stock_quote(["US.AAPL", "US.MSFT"])
    assert transport.quote_requests == [["US.AAPL", "US.MSFT"]]


@pytest.mark.parametrize("codes", [[], "US.AAPL", [1]])
def test_stock_quote_rejects_invalid_codes(codes: object) -> None:
    transport = WireTransport()
    with pytest.raises(ValueError, match="codes"):
        MoomooOpenDClient(transport).stock_quote(codes)  # type: ignore[arg-type]
    assert transport.quote_requests == []


def test_transport_failures_propagate_typed() -> None:
    error = OpenDUnavailableError("connection refused")
    client = MoomooOpenDClient(WireTransport(error=error))
    with pytest.raises(OpenDUnavailableError, match="connection refused"):
        client.history_kline("US.AAPL", interval="1d")
    with pytest.raises(OpenDUnavailableError, match="connection refused"):
        client.rt_ticker("US.AAPL")
    with pytest.raises(OpenDUnavailableError, match="connection refused"):
        client.stock_quote(["US.AAPL"])


def test_probe_only_transport_fails_on_market_data_requests() -> None:
    class ProbeOnlyTransport(OpenDTransport):
        def probe(self) -> dict:
            return {}

        def close(self) -> None:
            pass

    client = MoomooOpenDClient(ProbeOnlyTransport())
    with pytest.raises(NotImplementedError, match="historical klines"):
        client.history_kline("US.AAPL", interval="1d")
    with pytest.raises(NotImplementedError, match="tickers"):
        client.rt_ticker("US.AAPL")
    with pytest.raises(NotImplementedError, match="quotes"):
        client.stock_quote(["US.AAPL"])


def test_close_closes_transport() -> None:
    transport = WireTransport()
    client = MoomooOpenDClient(transport)
    client.close()
    assert transport.closed is True
