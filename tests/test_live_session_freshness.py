"""Session-end coverage, never execution quote authority."""

from datetime import datetime
from importlib import import_module, util

import pytest

from quantmesh.data.calendars import CalendarService, SessionPolicy


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def evaluate(now, last, **kwargs):
    assert util.find_spec("quantmesh.live.session_freshness"), "shared policy is absent"
    return import_module("quantmesh.live.session_freshness").evaluate_session_freshness(
        kwargs.pop("calendar_id", "XNYS"),
        kwargs.pop("policy", SessionPolicy.REGULAR),
        dt(now),
        dt(last) if last else None,
        kwargs.pop("interval", "1m"),
        kwargs.pop("provider_delay_seconds", 0),
        calendar=CalendarService(),
        **kwargs,
    )


@pytest.mark.parametrize(
    "now,last,next_open",
    [
        ("2026-10-11T12:00Z", "2026-10-09T20:00Z", "2026-10-12T13:30Z"),
        ("2026-12-25T18:00Z", "2026-12-24T18:00Z", "2026-12-28T14:30Z"),
        ("2026-11-27T19:00Z", "2026-11-27T18:00Z", "2026-11-30T14:30Z"),
        ("2026-03-08T12:00Z", "2026-03-06T21:00Z", "2026-03-09T13:30Z"),
        ("2026-11-01T12:00Z", "2026-10-30T20:00Z", "2026-11-02T14:30Z"),
        ("2026-10-12T13:29Z", "2026-10-09T20:00Z", "2026-10-12T13:30Z"),
    ],
)
def test_closed_latest_session_uses_pinned_calendar(now, last, next_open):
    result = evaluate(now, last)
    assert result.market_state == "closed"
    assert result.data_state == "latest_session"
    assert result.expected_last_bar_end == dt(last)
    assert result.next_open_at == dt(next_open)
    assert result.calendar_version == "exchange-calendars:4.13.2:XNYS"


def test_closed_missing_last_minute_is_missing_coverage():
    result = evaluate("2026-10-11T12:00Z", "2026-10-09T19:59Z")
    assert result.market_state == "closed"
    assert result.data_state == "missing"


@pytest.mark.parametrize("last", [None, "2026-10-08T20:00Z"])
def test_absent_or_older_session_is_missing(last):
    assert evaluate("2026-10-11T12:00Z", last).data_state == "missing"


def test_declared_delay_during_oct12_intake_does_not_allege_failure():
    result = evaluate("2026-10-12T13:37Z", "2026-10-09T20:00Z", provider_delay_seconds=900)
    assert result.market_state == "open"
    assert result.data_state == "fresh"
    assert result.expected_last_bar_end == dt("2026-10-09T20:00Z")


def test_opening_grace_expires_and_open_session_uses_delay():
    assert evaluate("2026-10-12T13:31Z", "2026-10-09T20:00Z").data_state == "fresh"
    assert evaluate("2026-10-12T13:37Z", "2026-10-09T20:00Z").data_state == "delayed"
    result = evaluate("2026-10-12T13:52:40Z", "2026-10-12T13:37Z", provider_delay_seconds=900)
    assert result.data_state == "fresh"
    assert result.expected_last_bar_end == dt("2026-10-12T13:37Z")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"calendar_id": "unqualified"},
        {"provider_delay_seconds": None},
        {"policy": SessionPolicy.EXTENDED},
        {"interval": "2d"},
    ],
)
def test_unknown_policy_never_manufactures_fresh(kwargs):
    assert evaluate("2026-10-12T13:37Z", "2026-10-09T20:00Z", **kwargs).data_state == "unknown"


def test_continuous_crypto_still_uses_lag():
    result = evaluate(
        "2026-10-11T12:00Z",
        "2026-10-11T11:58Z",
        calendar_id="24/7",
        policy=SessionPolicy.CONTINUOUS,
    )
    assert result.market_state == "open"
    assert result.data_state == "delayed"
    assert result.expected_last_bar_end == dt("2026-10-11T12:00Z")


def test_future_source_clock_is_unknown():
    assert evaluate("2026-10-12T13:37Z", "2026-10-12T13:38Z").data_state == "unknown"


def test_daily_end_contract_uses_early_close():
    result = evaluate("2026-11-27T19:00Z", "2026-11-27T18:00Z", interval="1d")
    assert result.data_state == "latest_session"
    assert result.expected_last_bar_end == dt("2026-11-27T18:00Z")


def test_off_session_data_cannot_replace_last_regular_session():
    result = evaluate("2026-10-11T12:00Z", "2026-10-10T12:00Z")
    assert result.data_state == "unknown"


def test_partial_minute_cannot_certify_completed_coverage():
    result = evaluate("2026-10-12T13:37Z", "2026-10-12T13:36:45Z")
    assert result.data_state == "unknown"


def test_crypto_observation_lag_boundary_uses_raw_source_time():
    result = evaluate(
        "2026-10-11T12:00:29Z",
        "2026-10-11T11:59:30Z",
        calendar_id="24/7",
        policy=SessionPolicy.CONTINUOUS,
        interval="30s",
        source_kind="observation",
    )
    assert result.data_state == "delayed"


def test_continuous_completed_bars_have_no_midnight_opening_grace():
    result = evaluate(
        "2026-10-12T00:01:59Z",
        "2026-10-12T00:00Z",
        calendar_id="24/7",
        policy=SessionPolicy.CONTINUOUS,
    )
    assert result.data_state == "delayed"
    assert result.expected_last_bar_end == dt("2026-10-12T00:01Z")


@pytest.mark.parametrize(
    "source,kind",
    [
        ("2026-10-09T20:00Z", "bar_end"),
        ("2026-10-09T19:59:58Z", "observation"),
    ],
)
def test_closed_positive_coverage_does_not_need_assumed_latency(source, kind):
    result = evaluate("2026-10-11T12:00Z", source, provider_delay_seconds=None, source_kind=kind)
    assert result.market_state == "closed"
    assert result.data_state == "latest_session"
    assert result.provider_delay_seconds is None


@pytest.mark.parametrize("source", ["2026-10-10T12:00Z", "2026-10-12T13:38Z"])
def test_closed_unknown_latency_still_refuses_invalid_source(source):
    result = evaluate("2026-10-11T12:00Z", source, provider_delay_seconds=None)
    assert result.data_state == "unknown"
