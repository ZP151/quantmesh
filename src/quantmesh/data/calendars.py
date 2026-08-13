"""Versioned XNYS and continuous-UTC session calendars."""

from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from functools import lru_cache
from importlib.metadata import version

import exchange_calendars
from pydantic import BaseModel, ConfigDict, model_validator

_EXCHANGE_CALENDARS_VERSION = "4.13.2"
_XNYS_VERSION = f"exchange-calendars:{_EXCHANGE_CALENDARS_VERSION}:XNYS"
_CONTINUOUS_VERSION = "quantmesh:1:24/7"
XNYS_REGULAR_VERSION = _XNYS_VERSION
CONTINUOUS_UTC_VERSION = _CONTINUOUS_VERSION
_CONTINUOUS_START = date(2000, 1, 1)
_XNYS_START = date(2000, 1, 3)
_SUPPORTED_END = date(2035, 12, 31)


class CalendarUnavailableError(ValueError):
    """A requested calendar, policy or session range is not available."""


class SessionPolicy(StrEnum):
    """Trading-session boundaries admitted by a calendar request."""

    REGULAR = "regular"
    EXTENDED = "extended"
    CONTINUOUS = "continuous"


def _require_calendar_version() -> None:
    installed = version("exchange-calendars")
    if installed != _EXCHANGE_CALENDARS_VERSION:
        raise CalendarUnavailableError(
            "exchange-calendars version mismatch: "
            f"expected {_EXCHANGE_CALENDARS_VERSION}, installed {installed}"
        )


@lru_cache(maxsize=1)
def _xnys_calendar():
    _require_calendar_version()
    return exchange_calendars.get_calendar(
        "XNYS",
        start=_XNYS_START.isoformat(),
        end=_SUPPORTED_END.isoformat(),
    )


class SessionWindow(BaseModel):
    """One immutable market session with a validated UTC identity."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    calendar_id: str
    calendar_version: str
    session_policy: SessionPolicy
    session_date: date
    open_at: datetime
    close_at: datetime

    @model_validator(mode="after")
    def identity_and_boundaries_are_valid(self) -> "SessionWindow":
        expected = {
            "XNYS": (_XNYS_VERSION, SessionPolicy.REGULAR),
            "24/7": (_CONTINUOUS_VERSION, SessionPolicy.CONTINUOUS),
        }
        if expected.get(self.calendar_id) != (
            self.calendar_version,
            self.session_policy,
        ):
            raise ValueError("calendar identity, version and session policy disagree")
        for name, value in (("open_at", self.open_at), ("close_at", self.close_at)):
            if value.tzinfo is not UTC or value.utcoffset() != timedelta(0):
                raise ValueError(f"{name} must be UTC")
        if self.close_at <= self.open_at:
            raise ValueError("close_at must be after open_at")
        if self.open_at.date() != self.session_date:
            raise ValueError("session_date must match the UTC open date")
        if self.calendar_id == "24/7":
            if not (_CONTINUOUS_START <= self.session_date <= _SUPPORTED_END):
                raise ValueError("continuous session date is outside supported range")
            expected_open = datetime.combine(self.session_date, time.min, tzinfo=UTC)
            if self.open_at != expected_open or self.close_at != expected_open + timedelta(
                days=1
            ):
                raise ValueError("continuous session must cover one exact UTC day")
        else:
            if not (_XNYS_START <= self.session_date <= _SUPPORTED_END):
                raise ValueError("XNYS session date is outside supported range")
            calendar = _xnys_calendar()
            label = self.session_date.isoformat()
            if not calendar.is_session(label):
                raise ValueError(f"{self.session_date} is not an XNYS session")
            expected_open = calendar.session_open(label).to_pydatetime().astimezone(UTC)
            expected_close = calendar.session_close(label).to_pydatetime().astimezone(UTC)
            if self.open_at != expected_open or self.close_at != expected_close:
                raise ValueError("session window does not match pinned XNYS schedule")
        return self


class CalendarService:
    """Resolve deterministic sessions from one pinned calendar source."""

    def __init__(self) -> None:
        _require_calendar_version()
        self._xnys = _xnys_calendar()

    def sessions(
        self,
        calendar_id: str,
        start: date,
        end: date,
        *,
        policy: SessionPolicy,
    ) -> tuple[SessionWindow, ...]:
        if end < start:
            raise ValueError("end must not precede start")
        if calendar_id not in {"XNYS", "24/7"}:
            raise CalendarUnavailableError(f"unknown calendar {calendar_id!r}")
        if calendar_id == "XNYS":
            if policy is SessionPolicy.EXTENDED:
                raise CalendarUnavailableError(
                    "XNYS extended session policy is explicit but not implemented"
                )
            if policy is not SessionPolicy.REGULAR:
                raise CalendarUnavailableError("XNYS requires the regular policy")
        elif policy is not SessionPolicy.CONTINUOUS:
            raise CalendarUnavailableError("24/7 requires the continuous policy")
        supported_start = _XNYS_START if calendar_id == "XNYS" else _CONTINUOUS_START
        if start < supported_start or end > _SUPPORTED_END:
            raise CalendarUnavailableError(
                f"{calendar_id} request is outside supported range "
                f"{supported_start}..{_SUPPORTED_END}"
            )
        if calendar_id == "24/7":
            return self._continuous_sessions(start, end)
        labels = self._xnys.sessions_in_range(start.isoformat(), end.isoformat())
        result = []
        for label in labels:
            row = self._xnys.schedule.loc[label]
            result.append(
                SessionWindow(
                    calendar_id="XNYS",
                    calendar_version=_XNYS_VERSION,
                    session_policy=SessionPolicy.REGULAR,
                    session_date=label.date(),
                    open_at=row["open"].to_pydatetime().astimezone(UTC),
                    close_at=row["close"].to_pydatetime().astimezone(UTC),
                )
            )
        return tuple(result)

    @staticmethod
    def _continuous_sessions(start: date, end: date) -> tuple[SessionWindow, ...]:
        count = (end - start).days + 1
        result = []
        for offset in range(count):
            session_date = start + timedelta(days=offset)
            open_at = datetime.combine(session_date, time.min, tzinfo=UTC)
            result.append(
                SessionWindow(
                    calendar_id="24/7",
                    calendar_version=_CONTINUOUS_VERSION,
                    session_policy=SessionPolicy.CONTINUOUS,
                    session_date=session_date,
                    open_at=open_at,
                    close_at=open_at + timedelta(days=1),
                )
            )
        return tuple(result)
