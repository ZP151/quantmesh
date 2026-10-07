"""Raw US current 1m normalization; provider end labels remain source evidence.

Only this empirically verified current-minute surface uses end labels. Daily
and historical adapters keep their existing semantics. Calendar filtering
preserves actual observations without inventing regular-session coverage.
"""

import math
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from quantmesh.data.calendars import CalendarService, CalendarUnavailableError, SessionPolicy
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.moomoo.opend import OpenDProtocolError

_EASTERN = ZoneInfo("America/New_York")
_MINUTE = timedelta(minutes=1)


@lru_cache(maxsize=1)
def _calendar() -> CalendarService:
    return CalendarService()


def minute_candles(instrument: Instrument, payload: object) -> list[dict]:
    """Validate ordered real observations and retain XNYS regular minute slots."""
    if (
        instrument.venue != Venue.MOOMOO
        or instrument.instrument_type != InstrumentType.EQUITY
        or instrument.symbol not in {"AAPL", "NVDA"}
        or instrument.metadata.get("market") != "US"
    ):
        raise ValueError("current minute candles require scoped US Moomoo AAPL/NVDA equities")
    code = f"US.{instrument.symbol}"
    if not isinstance(payload, dict) or any(
        payload.get(key) != expected
        for key, expected in {
            "code": code, "interval": "1m", "autype": "None", "session": "regular",
        }.items()
    ):
        raise OpenDProtocolError("current-minute identity/interval/adjustment/session disagrees")
    rows = payload.get("rows")
    if not isinstance(rows, list) or len(rows) > 390:
        raise OpenDProtocolError("current-minute rows must be a bounded list")
    result = []
    previous_end = None
    sessions = {}
    for row in rows:
        if not isinstance(row, dict) or row.get("code") != code:
            raise OpenDProtocolError("current-minute row identity disagrees")
        raw_time = row.get("time_key")
        end = _provider_end(raw_time)
        if previous_end is not None and end <= previous_end:
            raise OpenDProtocolError("current-minute labels must be unique and ascending")
        previous_end = end
        values = {key: _number(row.get(key), key) for key in (
            "open", "high", "low", "close", "volume",
        )}
        if (
            values["high"] < max(values["open"], values["low"], values["close"])
            or values["low"] > min(values["open"], values["high"], values["close"])
        ):
            raise OpenDProtocolError("current-minute OHLC bounds disagree")
        start = end - _MINUTE
        session_date = end.astimezone(_EASTERN).date()
        if session_date not in sessions:
            try:
                sessions[session_date] = _calendar().sessions(
                    "XNYS", session_date, session_date, policy=SessionPolicy.REGULAR,
                )
            except CalendarUnavailableError as error:
                raise OpenDProtocolError("current-minute session calendar unavailable") from error
        windows = sessions[session_date]
        if not windows or start < windows[0].open_at or end > windows[0].close_at:
            continue
        result.append({
            "timestamp": start, "provider_time_key": raw_time, "provider_end": end, **values,
        })
    return result


def _provider_end(value: object) -> datetime:
    if not isinstance(value, str):
        raise OpenDProtocolError("current-minute time_key must be a local wall-clock string")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            local = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if local.second:
            break
        return local.replace(tzinfo=_EASTERN).astimezone(UTC)
    raise OpenDProtocolError("current-minute time_key must label an exact local minute")


def _number(value: object, key: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OpenDProtocolError(f"current-minute {key} must be a real source number")
    try:
        number = float(value)
    except (OverflowError, ValueError) as error:
        raise OpenDProtocolError(f"current-minute {key} is not finite") from error
    if not math.isfinite(number) or (number < 0 if key == "volume" else number <= 0):
        raise OpenDProtocolError(f"current-minute {key} is outside valid source bounds")
    return number
