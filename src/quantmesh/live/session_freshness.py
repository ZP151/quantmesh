"""Read-only session coverage policy. This result grants no quote authority.

``last_source_time`` is a completed bar END (not its canonical open). For
observations use ``source_kind='observation'``; the last completed interval
must contain an actual source observation. Daily bars must be normalized to
their session close by the caller. Receipt time never rejuvenates coverage.
"""

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict

from quantmesh.data.calendars import CalendarService, CalendarUnavailableError, SessionPolicy
from quantmesh.domain.market_data import interval_to_timedelta


class SessionFreshness(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    market_state: Literal["open", "closed", "unknown"]
    data_state: Literal["fresh", "latest_session", "delayed", "missing", "unknown"]
    last_source_at: datetime | None
    expected_last_bar_end: datetime | None = None
    next_open_at: datetime | None = None
    calendar_version: str | None = None
    reason: str
    policy_version: str = "quantmesh:session-freshness:1"
    provider_delay_seconds: int | None = None
    opening_grace_seconds: int = 120


@lru_cache(maxsize=1)
def _calendar() -> CalendarService:
    return CalendarService()


@lru_cache(maxsize=128)
def _sessions(
    service: CalendarService, calendar_id: str, start: date, end: date, policy: SessionPolicy
):
    return service.sessions(calendar_id, start, end, policy=policy)


def evaluate_session_freshness(
    calendar_id: str,
    policy: SessionPolicy,
    now: datetime,
    last_source_time: datetime | None,
    interval: str,
    provider_delay_seconds: int | None,
    opening_grace_seconds: int = 120,
    *,
    calendar: CalendarService | None = None,
    source_kind: Literal["bar_end", "observation"] = "bar_end",
) -> SessionFreshness:
    """Compare source coverage to the latest slot due on the pinned schedule.

    Opening grace only postpones the first slot; it does not add latency to
    every later bar. Missing/unknown coverage never becomes normal closed data.
    Unsupported calendars, extended sessions or interval grids fail to unknown.
    """
    result = dict(
        market_state="unknown",
        data_state="unknown",
        last_source_at=last_source_time,
        reason="unknown_calendar_or_policy",
        provider_delay_seconds=provider_delay_seconds,
        opening_grace_seconds=opening_grace_seconds,
    )
    if now.tzinfo is None or (last_source_time is not None and last_source_time.tzinfo is None):
        return SessionFreshness(**(result | {"reason": "unknown_source_clock"}))
    now = now.astimezone(UTC)
    try:
        step = interval_to_timedelta(interval)
        if step > timedelta(days=1) or source_kind not in {"bar_end", "observation"}:
            raise ValueError("unsupported grid")
        service = calendar if calendar is not None else _calendar()
        sessions = _sessions(
            service,
            calendar_id,
            (now - timedelta(days=35)).date(),
            (now + timedelta(days=35)).date(),
            policy,
        )
    except (CalendarUnavailableError, ValueError):
        return SessionFreshness(**result)
    active = next((s for s in sessions if s.open_at <= now < s.close_at), None)
    following = next((s for s in sessions if s.open_at > now), None)
    result.update(
        market_state="open" if active is not None else "closed",
        next_open_at=following.open_at if following else None,
        calendar_version=sessions[0].calendar_version if sessions else None,
    )
    if (
        (
            provider_delay_seconds is not None
            and (type(provider_delay_seconds) is not int or provider_delay_seconds < 0)
        )
        or type(opening_grace_seconds) is not int
        or opening_grace_seconds < 0
    ):
        return SessionFreshness(**(result | {"reason": "unknown_provider_latency"}))
    if last_source_time is not None and last_source_time > now:
        return SessionFreshness(**(result | {"reason": "future_source_clock"}))
    # With unknown latency, only positive coverage of a fully closed session
    # can be established. This cutoff must never diagnose missing open data.
    cutoff = now - timedelta(seconds=provider_delay_seconds or 0)
    expected = None
    threshold = None
    for session in sessions:
        if session.open_at >= cutoff:
            break
        if step == timedelta(days=1):
            end = session.close_at if session.close_at <= cutoff else None
            start = session.open_at
        else:
            stop = min(cutoff, session.close_at)
            slots = (stop - session.open_at) // step
            end = session.open_at + slots * step if slots else None
            start = end - step if end is not None else session.open_at
            if calendar_id != "24/7" and cutoff < session.open_at + timedelta(
                seconds=opening_grace_seconds
            ):
                end = None
        if end is not None:
            expected = end
            threshold = end if source_kind == "bar_end" else start
    result["expected_last_bar_end"] = expected
    if expected is None:
        return SessionFreshness(**(result | {"reason": "no_resolved_expected_slot"}))
    if last_source_time is None and provider_delay_seconds is not None:
        return SessionFreshness(**(result | {"data_state": "missing", "reason": "no_source_data"}))
    if last_source_time is not None and last_source_time >= sessions[0].open_at:
        valid_source = any(
            (
                session.open_at <= last_source_time <= session.close_at + timedelta(seconds=1)
                if source_kind == "observation"
                else (
                    last_source_time == session.close_at
                    if step == timedelta(days=1)
                    else session.open_at < last_source_time <= session.close_at
                    and (last_source_time - session.open_at) % step == timedelta(0)
                )
            )
            for session in sessions
        )
        if not valid_source:
            return SessionFreshness(**(result | {"reason": "source_not_on_session_grid"}))
    if calendar_id == "24/7" and source_kind == "observation":
        threshold = cutoff - step
    covered = last_source_time is not None and last_source_time >= threshold
    if provider_delay_seconds is None:
        if active is None and covered:
            return SessionFreshness(
                **(
                    result
                    | {
                        "data_state": "latest_session",
                        "reason": "closed_latest_session_covered_without_latency_assumption",
                    }
                )
            )
        return SessionFreshness(**(result | {"reason": "unknown_provider_latency"}))
    state = (
        ("fresh" if active else "latest_session")
        if covered
        else ("delayed" if active else "missing")
    )
    return SessionFreshness(
        **(
            result
            | {
                "data_state": state,
                "reason": "expected_slot_covered" if covered else "expected_slot_not_covered",
            }
        )
    )
