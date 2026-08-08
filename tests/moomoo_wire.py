"""Shared wire-shaped OpenD payloads and a wire stub transport (issue #26, Phase B).

These payloads are shaped like what ``SdkTransport`` produces from the
vendored SDK's DataFrames (ADR-0004 extension): plain dicts with
market-qualified codes and venue-local wall-clock times. The vendor
reports times in the venue's local zone — US in Eastern Time, HK in
Beijing (HKT) time — so the fixture times encode that contract: the
adapter's UTC conversion is exactly what these tests pin down.
"""


from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.moomoo.opend import OpenDProtocolError, OpenDTransport

AAPL = Instrument(
    symbol="AAPL",
    venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY,
    currency="USD",
    metadata={"market": "US"},
)
TENCENT = Instrument(
    symbol="00700",
    venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY,
    currency="HKD",
    metadata={"market": "HK"},
)

US_AAPL_1D = {
    "code": "US.AAPL",
    "interval": "1d",
    "autype": "None",
    "rows": [
        {
            "time_key": "2026-08-03",
            "open": 200.0,
            "high": 205.0,
            "low": 199.0,
            "close": 204.0,
            "volume": 1000,
            "turnover": 204000.0,
        },
        {
            "time_key": "2026-08-04",
            "open": 204.0,
            "high": 208.0,
            "low": 202.0,
            "close": 207.0,
            "volume": 900,
            "turnover": 185000.0,
        },
        {
            "time_key": "2026-08-05",
            "open": 207.0,
            "high": 210.0,
            "low": 206.0,
            "close": 209.5,
            "volume": 1100,
            "turnover": 230000.0,
        },
    ],
}

US_AAPL_5M = {
    "code": "US.AAPL",
    "interval": "5m",
    "autype": "None",
    "rows": [
        {
            "time_key": "2026-08-03 09:30:00",
            "open": 200.0,
            "high": 202.0,
            "low": 199.5,
            "close": 201.0,
            "volume": 500,
        },
        {
            "time_key": "2026-08-03 09:35:00",
            "open": 201.0,
            "high": 204.0,
            "low": 200.5,
            "close": 203.5,
            "volume": 700,
        },
        {
            "time_key": "2026-08-03 09:40:00",
            "open": 203.5,
            "high": 205.0,
            "low": 203.0,
            "close": 204.5,
            "volume": 600,
        },
    ],
}

HK_00700_1D = {
    "code": "HK.00700",
    "interval": "1d",
    "autype": "None",
    "rows": [
        {
            "time_key": "2026-08-03",
            "open": 380.0,
            "high": 385.0,
            "low": 378.0,
            "close": 383.0,
            "volume": 20000,
        },
        {
            "time_key": "2026-08-04",
            "open": 383.0,
            "high": 390.0,
            "low": 382.0,
            "close": 388.0,
            "volume": 25000,
        },
    ],
}

HK_00700_5M = {
    "code": "HK.00700",
    "interval": "5m",
    "autype": "None",
    "rows": [
        {
            "time_key": "2026-08-03 09:30:00",
            "open": 380.0,
            "high": 382.0,
            "low": 379.0,
            "close": 381.0,
            "volume": 3000,
        },
        {
            "time_key": "2026-08-03 09:35:00",
            "open": 381.0,
            "high": 384.0,
            "low": 380.5,
            "close": 383.5,
            "volume": 4000,
        },
    ],
}

US_AAPL_TICKER = {
    "code": "US.AAPL",
    "rows": [
        {
            "time": "2026-08-03 09:30:01",
            "sequence": 5001,
            "price": 200.0,
            "volume": 100,
            "turnover": 20000.0,
            "direction": "BUY",
            "type": "AUTOMATCH",
        },
        {
            "time": "2026-08-03 09:30:02",
            "sequence": 5002,
            "price": 200.1,
            "volume": 50,
            "turnover": 10005.0,
            "direction": "SELL",
            "type": "AUTOMATCH",
        },
        {
            "time": "2026-08-03 09:30:03",
            "sequence": 5003,
            "price": 200.1,
            "volume": 10,
            "turnover": 2001.0,
            "direction": "NEUTRAL",
            "type": "AUCTION",
        },
    ],
}

US_AAPL_QUOTE = {
    "rows": [
        {
            "code": "US.AAPL",
            "data_date": "2026-08-03",
            "data_time": "16:00:00",
            "last_price": 204.0,
            "open_price": 200.0,
            "high_price": 205.0,
            "low_price": 199.0,
            "prev_close_price": 199.5,
            "volume": 1000,
            "turnover": 204000.0,
        }
    ],
}


class WireTransport(OpenDTransport):
    """Transport serving canned wire payloads, with injectable errors.

    Records every request it serves so tests can assert delegation.
    """

    def __init__(
        self,
        *,
        kline: dict | None = None,
        kline_by_code: dict[str, dict] | None = None,
        ticker: dict | None = None,
        quote: dict | None = None,
        error: Exception | None = None,
    ) -> None:
        self._kline = kline if kline is not None else US_AAPL_1D
        self._kline_by_code = kline_by_code
        self._ticker = ticker if ticker is not None else US_AAPL_TICKER
        self._quote = quote if quote is not None else US_AAPL_QUOTE
        self.error = error
        self.kline_requests: list[tuple] = []
        self.ticker_requests: list[tuple] = []
        self.quote_requests: list[list[str]] = []
        self.closed = False

    def probe(self) -> dict:
        return {
            "quote": True,
            "history_kline": True,
            "order": False,
            "order_query": False,
            "auth_required": False,
        }

    def history_kline(
        self, code: str, *, interval: str, start: str | None, end: str | None, autype: str
    ) -> dict:
        self.kline_requests.append((code, interval, start, end, autype))
        if self.error is not None:
            raise self.error
        if self._kline_by_code is not None:
            if code not in self._kline_by_code:
                raise OpenDProtocolError(f"no wire fixture for code {code!r}")
            return self._kline_by_code[code]
        return self._kline

    def rt_ticker(self, code: str, *, num: int) -> dict:
        self.ticker_requests.append((code, num))
        if self.error is not None:
            raise self.error
        return self._ticker

    def stock_quote(self, codes: list[str]) -> dict:
        self.quote_requests.append(list(codes))
        if self.error is not None:
            raise self.error
        return self._quote

    def close(self) -> None:
        self.closed = True
