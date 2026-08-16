"""Moomoo wire payload → canonical model mapping (issue #26, Phase B).

The pure adapter half of the OpenD market-data boundary (ADR-0004
extension): payloads produced by a transport — real ``SdkTransport`` or
a fixture stub — are validated and mapped to canonical ``Bar``,
``TradeEvent`` and ``Quote``. No transport, no pandas, no SDK: every
input is a plain mapping, so unit tests run with neither OpenD nor the
vendored SDK.

The SDK reports times as venue-local wall-clock strings (US = Eastern,
HK/CN = Beijing) with no zone marker. Those strings are provider
metadata: the market prefix of the payload's code selects the IANA zone
and the timestamp is converted to UTC, DST-aware. An unknown market, an
unparseable time, or a payload code that does not match the requested
instrument is an ``OpenDProtocolError`` — a timestamp is never guessed.
"""

import math
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from quantmesh.domain.market_data import Bar, TradeEvent
from quantmesh.domain.models import Instrument, Quote, Side
from quantmesh.moomoo.opend import OpenDProtocolError

# The SDK's own adjustment markers (``AuType``): raw prices by default.
_AUTYPE_KEYS = ("None", "qfq", "hfq")

# Venue-local zones the vendored SDK reports times in, keyed by the
# market prefix of a code (``US.AAPL``, ``HK.00700``, ``CN.600000``).
_MARKET_TZ = {
    "US": ZoneInfo("America/New_York"),
    "HK": ZoneInfo("Asia/Hong_Kong"),
    "CN": ZoneInfo("Asia/Shanghai"),
}

# The SDK's wall-clock formats, longest first: intraday carries seconds
# (the server sends minute precision for minute bars), daily is date-only.
_WALL_CLOCK_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)
_DATE_FORMAT = "%Y-%m-%d"

_REQUIRED_KLINE_ROW_KEYS = ("code", "time_key", "open", "high", "low", "close", "volume")
_REQUIRED_TICKER_ROW_KEYS = ("time", "price", "volume")
_REQUIRED_QUOTE_ROW_KEYS = ("data_date", "last_price")


def market_zone(market: object) -> ZoneInfo:
    """IANA zone for a bare market prefix (``US``, ``HK``, ``CN``)."""
    if not isinstance(market, str) or market not in _MARKET_TZ:
        raise ValueError(f"market {market!r} (supported: {', '.join(sorted(_MARKET_TZ))})")
    return _MARKET_TZ[market]


def market_tz(code: object) -> ZoneInfo:
    """IANA zone for a market-qualified code; unknown markets fail closed."""
    market, _ = _split_code(code)
    try:
        return _MARKET_TZ[market]
    except KeyError as error:
        raise OpenDProtocolError(
            "no timezone metadata for market "
            f"{market!r} (supported: {', '.join(sorted(_MARKET_TZ))})"
        ) from error


def sdk_code(instrument: Instrument) -> str:
    """Market-qualified SDK code for an instrument (``US.AAPL``).

    The market is provider metadata: it cannot be derived from the bare
    symbol (``AAPL``, ``00700``), so an instrument reaching OpenD must
    declare it. Fail closed rather than guess.
    """
    market = instrument.metadata.get("market")
    if market not in _MARKET_TZ:
        raise ValueError(
            f"instrument {instrument.symbol!r} needs metadata 'market' in "
            f"{sorted(_MARKET_TZ)} to reach OpenD"
        )
    return f"{market}.{instrument.symbol}"


def _split_code(code: object) -> tuple[str, str]:
    if not isinstance(code, str):
        raise OpenDProtocolError(f"payload code must be a string, got {type(code).__name__}")
    market, sep, symbol = code.partition(".")
    if not sep or not market or not symbol:
        raise OpenDProtocolError(
            f"payload code {code!r} is not market-qualified (expected e.g. 'US.AAPL')"
        )
    return market, symbol


def _check_symbol(code: str, symbol: str) -> None:
    _, code_symbol = _split_code(code)
    if code_symbol != symbol:
        raise OpenDProtocolError(
            f"payload code {code!r} does not match instrument symbol {symbol!r}"
        )


def _venue_time(value: object, tz: ZoneInfo, *, allow_date_only: bool = False) -> datetime:
    """Venue-local wall-clock string → aware UTC instant; never guess."""
    if not isinstance(value, str):
        raise OpenDProtocolError(f"time must be a string, got {type(value).__name__}")
    formats = (*_WALL_CLOCK_FORMATS, _DATE_FORMAT) if allow_date_only else _WALL_CLOCK_FORMATS
    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=tz).astimezone(UTC)
    raise OpenDProtocolError(f"unparseable venue-local time {value!r}")


class MoomooDataAdapter:
    """Maps wire payloads to canonical models, fail closed (ADR-0004 ext.)."""

    def history_kline_to_bars(self, instrument: Instrument, payload: object) -> list[Bar]:
        rows = _payload_rows(payload, "history-kline", top_keys=("code", "interval", "autype"))
        code = _code(payload, "history-kline")
        tz = market_tz(code)
        _check_symbol(code, instrument.symbol)
        interval, autype = payload["interval"], payload["autype"]  # type: ignore[index]
        if not isinstance(interval, str) or not isinstance(autype, str):
            raise OpenDProtocolError("history-kline payload interval/autype must be strings")
        if autype not in _AUTYPE_KEYS:
            raise OpenDProtocolError(
                f"history-kline payload has unknown autype {autype!r} "
                f"(expected one of {_AUTYPE_KEYS})"
            )
        bars: list[Bar] = []
        for index, row in enumerate(rows):
            missing = [key for key in _REQUIRED_KLINE_ROW_KEYS if key not in row]
            if missing:
                raise OpenDProtocolError(f"history-kline row {index} is missing {missing}")
            if row["code"] != code:
                raise OpenDProtocolError(
                    f"history-kline row {index} code {row['code']!r} disagrees with {code!r}"
                )
            timestamp = _venue_time(row["time_key"], tz, allow_date_only=interval in {"1d", "1w"})
            values = {
                key: _finite_source_number(row[key], key=key, row_index=index)
                for key in ("open", "high", "low", "close", "volume")
            }
            try:
                bars.append(
                    Bar(
                        instrument=instrument,
                        timestamp=timestamp,
                        interval=interval,
                        open=values["open"],
                        high=values["high"],
                        low=values["low"],
                        close=values["close"],
                        volume=values["volume"],
                    )
                )
            except ValueError as error:
                raise OpenDProtocolError(
                    f"history-kline row {index} is invalid: {error}"
                ) from error
        return bars

    def history_pages_to_bars(self, instrument: Instrument, pages: object) -> list[Bar]:
        """Map ordered raw pages and reject metadata drift or duplicate rows."""
        if not isinstance(pages, list) or not pages:
            raise OpenDProtocolError("history pages must be a non-empty list")
        expected: tuple[object, object, object] | None = None
        bars: list[Bar] = []
        identities: set[tuple[datetime, str]] = set()
        previous: datetime | None = None
        for page_index, page in enumerate(pages):
            if not isinstance(page, dict):
                raise OpenDProtocolError(f"history page {page_index} is not a mapping")
            metadata = (page.get("code"), page.get("interval"), page.get("autype"))
            if expected is None:
                expected = metadata
            elif metadata != expected:
                raise OpenDProtocolError("history page metadata changes between pages")
            for bar in self.history_kline_to_bars(instrument, page):
                identity = (bar.timestamp, bar.interval)
                if identity in identities:
                    raise OpenDProtocolError(
                        f"duplicate history row at {bar.timestamp.isoformat()}"
                    )
                if previous is not None and bar.timestamp <= previous:
                    raise OpenDProtocolError("history rows are not strictly ordered")
                identities.add(identity)
                previous = bar.timestamp
                bars.append(bar)
        return bars

    def ticker_to_trades(self, instrument: Instrument, payload: object) -> list[TradeEvent]:
        rows = _payload_rows(payload, "ticker", top_keys=("code",))
        code = _code(payload, "ticker")
        tz = market_tz(code)
        _check_symbol(code, instrument.symbol)
        trades: list[TradeEvent] = []
        for index, row in enumerate(rows):
            missing = [key for key in _REQUIRED_TICKER_ROW_KEYS if key not in row]
            if missing:
                raise OpenDProtocolError(f"ticker row {index} is missing {missing}")
            timestamp = _venue_time(row["time"], tz)
            try:
                trades.append(
                    TradeEvent(
                        instrument=instrument,
                        timestamp=timestamp,
                        price=row["price"],
                        quantity=row["volume"],
                        aggressor_side=_direction(row.get("direction")),
                        venue_sequence=_sequence(row.get("sequence")),
                    )
                )
            except ValueError as error:
                raise OpenDProtocolError(f"ticker row {index} is invalid: {error}") from error
        return trades

    def stock_quote_to_quote(self, instrument: Instrument, payload: object) -> Quote:
        rows = _payload_rows(payload, "stock-quote")
        if len(rows) != 1:
            raise OpenDProtocolError(
                f"stock-quote payload must carry exactly one row, got {len(rows)}"
            )
        row = rows[0]
        missing = [key for key in ("code", *_REQUIRED_QUOTE_ROW_KEYS) if key not in row]
        if missing:
            raise OpenDProtocolError(f"stock-quote row is missing {missing}")
        tz = market_tz(row["code"])
        _check_symbol(row["code"], instrument.symbol)
        data_time = row.get("data_time") or "00:00:00"
        if not isinstance(row["data_date"], str) or not isinstance(data_time, str):
            raise OpenDProtocolError("stock-quote data_date/data_time must be strings")
        timestamp = _venue_time(f"{row['data_date']} {data_time}", tz)
        try:
            return Quote(
                instrument=instrument,
                timestamp=timestamp,
                last=row["last_price"],
                volume=row.get("volume"),
            )
        except ValueError as error:
            raise OpenDProtocolError(f"stock-quote row is invalid: {error}") from error


def _payload_rows(payload: object, contract: str, *, top_keys: tuple[str, ...] = ()) -> list[dict]:
    """Validate the payload shape, returning the validated row list.

    Quote payloads carry their code per row; klines and tickers carry it
    at the top level, which callers read via ``_code``.
    """
    if not isinstance(payload, dict):
        raise OpenDProtocolError(
            f"{contract} payload must be a mapping, got {type(payload).__name__}"
        )
    missing = [key for key in ("rows", *top_keys) if key not in payload]
    if missing:
        raise OpenDProtocolError(f"{contract} payload is missing {missing}")
    rows = payload["rows"]
    if not isinstance(rows, list):
        raise OpenDProtocolError(
            f"{contract} payload rows must be a list, got {type(rows).__name__}"
        )
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise OpenDProtocolError(
                f"{contract} row {index} is not a mapping, got {type(row).__name__}"
            )
    return rows


def _code(payload: dict, contract: str) -> str:
    code = payload["code"]
    if not isinstance(code, str):
        raise OpenDProtocolError(
            f"{contract} payload code must be a string, got {type(code).__name__}"
        )
    return code


def _direction(marker: object) -> Side | None:
    """Ticker direction → aggressor side; neutral/unknown markers map to None."""
    if marker is None:
        return None
    if not isinstance(marker, str):
        raise OpenDProtocolError(f"ticker direction must be a string, got {type(marker).__name__}")
    if marker in ("NEUTRAL", "N/A"):
        return None
    try:
        return {"BUY": Side.BUY, "SELL": Side.SELL}[marker]
    except KeyError as error:
        raise OpenDProtocolError(f"unknown ticker direction {marker!r}") from error


def _sequence(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise OpenDProtocolError(f"ticker sequence must be an integer, got {type(value).__name__}")
    return value


def _finite_source_number(value: object, *, key: str, row_index: int) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OpenDProtocolError(
            f"history-kline row {row_index} {key} must be a finite number, "
            f"got {type(value).__name__}"
        )
    if not math.isfinite(float(value)):
        raise OpenDProtocolError(f"history-kline row {row_index} {key} must be a finite number")
    return value
