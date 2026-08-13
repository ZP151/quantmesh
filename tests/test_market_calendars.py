from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from quantmesh.data.calendars import (
    CalendarService,
    CalendarUnavailableError,
    SessionPolicy,
    SessionWindow,
)


def test_xnys_skips_holiday_and_honors_early_close() -> None:
    sessions = CalendarService().sessions(
        "XNYS",
        date(2025, 11, 27),
        date(2025, 12, 1),
        policy=SessionPolicy.REGULAR,
    )

    assert [row.session_date.isoformat() for row in sessions] == [
        "2025-11-28",
        "2025-12-01",
    ]
    assert sessions[0].open_at == datetime(2025, 11, 28, 14, 30, tzinfo=UTC)
    assert sessions[0].close_at == datetime(2025, 11, 28, 18, 0, tzinfo=UTC)
    assert sessions[0].calendar_version == "exchange-calendars:4.13.2:XNYS"
    assert sessions[0].session_policy is SessionPolicy.REGULAR


def test_continuous_calendar_returns_every_utc_day() -> None:
    sessions = CalendarService().sessions(
        "24/7",
        date(2026, 8, 14),
        date(2026, 8, 16),
        policy=SessionPolicy.CONTINUOUS,
    )

    assert [row.session_date for row in sessions] == [
        date(2026, 8, 14),
        date(2026, 8, 15),
        date(2026, 8, 16),
    ]
    assert sessions[0].open_at == datetime(2026, 8, 14, tzinfo=UTC)
    assert sessions[0].close_at == datetime(2026, 8, 15, tzinfo=UTC)
    assert all(row.calendar_version == "quantmesh:1:24/7" for row in sessions)


def test_calendar_rejects_unknown_id_and_inverted_range() -> None:
    service = CalendarService()

    with pytest.raises(CalendarUnavailableError, match="unknown calendar"):
        service.sessions(
            "weekday",
            date(2026, 8, 14),
            date(2026, 8, 15),
            policy=SessionPolicy.REGULAR,
        )
    with pytest.raises(ValueError, match="end must not precede start"):
        service.sessions(
            "XNYS",
            date(2026, 8, 15),
            date(2026, 8, 14),
            policy=SessionPolicy.REGULAR,
        )


def test_xnys_rejects_dates_outside_pinned_package_range() -> None:
    with pytest.raises(CalendarUnavailableError, match="supported range"):
        CalendarService().sessions(
            "XNYS",
            date(1800, 1, 1),
            date(1800, 1, 2),
            policy=SessionPolicy.REGULAR,
        )


def test_continuous_calendar_rejects_unbounded_date_range() -> None:
    with pytest.raises(CalendarUnavailableError, match="supported range"):
        CalendarService().sessions(
            "24/7",
            date(1800, 1, 1),
            date(1800, 1, 2),
            policy=SessionPolicy.CONTINUOUS,
        )


def test_xnys_extended_policy_fails_closed_until_implemented() -> None:
    with pytest.raises(CalendarUnavailableError, match="extended.*not implemented"):
        CalendarService().sessions(
            "XNYS",
            date(2026, 8, 14),
            date(2026, 8, 14),
            policy=SessionPolicy.EXTENDED,
        )


def test_calendar_rejects_policy_mismatch() -> None:
    service = CalendarService()

    with pytest.raises(CalendarUnavailableError, match="continuous policy"):
        service.sessions(
            "24/7",
            date(2026, 8, 14),
            date(2026, 8, 14),
            policy=SessionPolicy.REGULAR,
        )
    with pytest.raises(CalendarUnavailableError, match="regular policy"):
        service.sessions(
            "XNYS",
            date(2026, 8, 14),
            date(2026, 8, 14),
            policy=SessionPolicy.CONTINUOUS,
        )


def test_xnys_open_tracks_dst_in_utc() -> None:
    winter = CalendarService().sessions(
        "XNYS",
        date(2026, 1, 5),
        date(2026, 1, 5),
        policy=SessionPolicy.REGULAR,
    )[0]
    summer = CalendarService().sessions(
        "XNYS",
        date(2026, 7, 6),
        date(2026, 7, 6),
        policy=SessionPolicy.REGULAR,
    )[0]

    assert winter.open_at.hour == 14
    assert summer.open_at.hour == 13


def test_session_window_rejects_forged_calendar_identity_and_non_utc_time() -> None:
    with pytest.raises(ValidationError, match="calendar identity"):
        SessionWindow(
            calendar_id="XNYS",
            calendar_version="quantmesh:1:24/7",
            session_policy=SessionPolicy.REGULAR,
            session_date=date(2026, 8, 14),
            open_at=datetime(2026, 8, 14, 13, 30, tzinfo=UTC),
            close_at=datetime(2026, 8, 14, 20, 0, tzinfo=UTC),
        )
    offset = timezone(timedelta(hours=8))
    with pytest.raises(ValidationError, match="UTC"):
        SessionWindow(
            calendar_id="24/7",
            calendar_version="quantmesh:1:24/7",
            session_policy=SessionPolicy.CONTINUOUS,
            session_date=date(2026, 8, 14),
            open_at=datetime(2026, 8, 14, tzinfo=offset),
            close_at=datetime(2026, 8, 15, tzinfo=offset),
        )


def test_session_window_rejects_holiday_and_fabricated_xnys_hours() -> None:
    with pytest.raises(ValidationError, match="not an XNYS session"):
        SessionWindow(
            calendar_id="XNYS",
            calendar_version="exchange-calendars:4.13.2:XNYS",
            session_policy=SessionPolicy.REGULAR,
            session_date=date(2025, 11, 27),
            open_at=datetime(2025, 11, 27, 14, 30, tzinfo=UTC),
            close_at=datetime(2025, 11, 27, 21, 0, tzinfo=UTC),
        )
    with pytest.raises(ValidationError, match="does not match pinned XNYS schedule"):
        SessionWindow(
            calendar_id="XNYS",
            calendar_version="exchange-calendars:4.13.2:XNYS",
            session_policy=SessionPolicy.REGULAR,
            session_date=date(2025, 11, 28),
            open_at=datetime(2025, 11, 28, 0, 0, tzinfo=UTC),
            close_at=datetime(2025, 11, 28, 1, 0, tzinfo=UTC),
        )


def test_xnys_lower_boundary_is_typed_and_continuous_boundary_is_supported() -> None:
    service = CalendarService()

    with pytest.raises(CalendarUnavailableError, match="supported range"):
        service.sessions(
            "XNYS",
            date(2000, 1, 1),
            date(2000, 1, 1),
            policy=SessionPolicy.REGULAR,
        )
    continuous = service.sessions(
        "24/7",
        date(2000, 1, 1),
        date(2000, 1, 1),
        policy=SessionPolicy.CONTINUOUS,
    )
    assert continuous[0].session_date == date(2000, 1, 1)


def test_calendar_support_upper_boundary_is_inclusive() -> None:
    sessions = CalendarService().sessions(
        "24/7",
        date(2035, 12, 31),
        date(2035, 12, 31),
        policy=SessionPolicy.CONTINUOUS,
    )

    assert sessions[0].session_date == date(2035, 12, 31)


def test_session_window_is_immutable() -> None:
    session = CalendarService().sessions(
        "24/7",
        date(2026, 8, 14),
        date(2026, 8, 14),
        policy=SessionPolicy.CONTINUOUS,
    )[0]

    with pytest.raises(ValidationError, match="frozen"):
        session.close_at = datetime(2026, 8, 16, tzinfo=UTC)
