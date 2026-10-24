"""Daily-session quality facts using the existing calendar and Bar primitives."""

from __future__ import annotations

import csv
import io
import math
from datetime import date, datetime, timedelta

from quantmesh.data.calendars import CalendarService, SessionPolicy
from quantmesh.domain.market_data import Bar, find_duplicates, monotonic_violations
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.research.local_csv_snapshots import (
    MAX_CSV_BYTES,
    MAX_LOCATIONS,
    MAX_ROWS,
    LocalCsvCheck,
    LocalCsvCoverage,
    LocalCsvFreshness,
    LocalCsvLocation,
    LocalCsvRequest,
)
from quantmesh.research.realdata_snapshots import SnapshotInputError, SnapshotTooLarge, _utc

FIELDS = ["timestamp_utc", "open", "high", "low", "close", "volume"]


def instrument(request: LocalCsvRequest) -> Instrument:
    return Instrument(
        symbol=request.symbol,
        venue=Venue(request.venue),
        instrument_type=InstrumentType.EQUITY
        if request.venue == "moomoo"
        else InstrumentType.PERPETUAL,
        currency="UNKNOWN",  # CSV carries no independently established currency/unit contract.
    )


def policy(request: LocalCsvRequest) -> SessionPolicy:
    return SessionPolicy.REGULAR if request.calendar_id == "XNYS" else SessionPolicy.CONTINUOUS


def freshness(calendar, request, last_day, now):
    result = dict(
        as_of=now.isoformat(),
        latest_complete_session=None,
        last_session=last_day,
        age_sessions=None,
        status="INSUFFICIENT",
    )
    if not date(2000, 1, 3) <= now.date() <= date(2035, 12, 31):
        return LocalCsvFreshness(**result)
    start = max(date(2000, 1, 3), now.date() - timedelta(days=30))
    if last_day:
        start = max(date(2000, 1, 3), min(start, date.fromisoformat(last_day)))
    sessions = calendar.sessions(request.calendar_id, start, now.date(), policy=policy(request))
    completed = [
        session.session_date.isoformat()
        for session in sessions
        if session.close_at + timedelta(minutes=30) <= now
    ]
    if completed:
        latest = completed[-1]
        result["latest_complete_session"] = latest
        if last_day and last_day <= latest:
            age = sum(day > last_day for day in completed)
            result.update(age_sessions=age, status="CURRENT" if age == 0 else "STALE")
    return LocalCsvFreshness(**result)


def check_csv(request: LocalCsvRequest, now: datetime, calendar: CalendarService):
    raw = request.csv_text.encode("utf-8")
    if len(raw) > MAX_CSV_BYTES:
        raise SnapshotTooLarge("local_csv_too_large")
    try:
        reader = csv.DictReader(
            io.StringIO(request.csv_text.lstrip("\ufeff"), newline=""), strict=True
        )
        if reader.fieldnames != FIELDS:
            raise ValueError("unsupported CSV header")
        rows = []
        for row in reader:
            if len(rows) >= MAX_ROWS or None in row or None in row.values():
                raise ValueError("invalid CSV shape")
            rows.append(row)
    except (csv.Error, UnicodeError, ValueError) as error:
        raise SnapshotInputError("local_csv_invalid") from error
    sessions = calendar.sessions(
        request.calendar_id,
        date.fromisoformat(request.required_start),
        date.fromisoformat(request.required_end),
        policy=policy(request),
    )
    schedule = {session.session_date.isoformat(): session for session in sessions}
    locations: dict[str, list[LocalCsvLocation]] = {
        code: []
        for code in (
            "bar_values",
            "bar_time",
            "bar_order",
            "bar_duplicates",
            "session_coverage",
            "unfinished_session",
            "source_receipt",
        )
    }

    def locate(code, row=None, day=None, field="", expected=None, actual=None):
        locations[code].append(
            LocalCsvLocation(
                row=row,
                date=day,
                field=field,
                expected=str(expected)[:160] if expected is not None else None,
                actual=str(actual)[:160] if actual is not None else None,
            )
        )

    bars, dates, moments, positions = [], [], [], []
    received = _utc(request.source.received_at) if request.source.received_at else None
    if received is not None and received > now:
        locate("source_receipt", field="received_at", expected="not after import", actual=received)
    for position, row in enumerate(rows, start=2):
        moment = None
        try:
            moment = _utc(row["timestamp_utc"])
        except (ValueError, OverflowError):
            locate(
                "bar_time",
                position,
                field="timestamp_utc",
                expected="aware UTC bar OPEN",
                actual=row["timestamp_utc"],
            )
        if moment is not None:
            day = moment.date().isoformat()
            dates.append(day)
            moments.append(moment)
            positions.append(position)
            session = schedule.get(day)
            if session is None or moment != session.open_at:
                locate("bar_time", position, day, "timestamp_utc", "declared session OPEN", moment)
            if session is not None:
                if session.close_at + timedelta(minutes=30) > now:
                    locate(
                        "unfinished_session",
                        position,
                        day,
                        "timestamp_utc",
                        "session close +30min research grace",
                        now,
                    )
                if received is not None and received < session.close_at:
                    locate(
                        "source_receipt",
                        position,
                        day,
                        "received_at",
                        "not before this daily session closes",
                        received,
                    )
        try:
            numbers = {name: float(row[name]) for name in FIELDS[1:]}
            if not all(math.isfinite(value) for value in numbers.values()):
                raise ValueError("nonfinite OHLCV")
            if moment is not None:
                bars.append(
                    Bar(instrument=instrument(request), timestamp=moment, interval="1d", **numbers)
                )
            else:
                # Reuse the same OHLC checks without turning an invalid time into a valid row.
                Bar(instrument=instrument(request), timestamp=now, interval="1d", **numbers)
        except (ValueError, OverflowError):
            locate(
                "bar_values",
                position,
                moment.date().isoformat() if moment else None,
                "OHLCV",
                "finite positive OHLC, consistent bounds, nonnegative volume",
                ",".join(row[name] for name in FIELDS[1:])[:160],
            )
    for _, current in monotonic_violations(moments):
        locate(
            "bar_order",
            positions[current],
            dates[current],
            "timestamp_utc",
            "strict chronological input",
            moments[current],
        )
    for day, indices in find_duplicates(dates).items():
        for index in indices[1:]:
            locate(
                "bar_duplicates", positions[index], day, "session_date", "one row per session", day
            )
    missing, unexpected = sorted(set(schedule) - set(dates)), sorted(set(dates) - set(schedule))
    for day in missing:
        locate(
            "session_coverage", day=day, field="session_date", expected="present", actual="missing"
        )
    for day in unexpected:
        locate(
            "session_coverage",
            day=day,
            field="session_date",
            expected="inside declared sessions",
            actual="unexpected",
        )
    if not rows:
        locate("bar_values", field="rows", expected="at least one row", actual=0)
    if not sessions:
        locate(
            "session_coverage",
            field="required_window",
            expected="at least one session",
            actual="empty calendar window",
        )
    messages = {
        "bar_values": "Finite OHLCV and price bounds checked; zero volume is not fill evidence.",
        "bar_time": "UTC bar OPEN aligned to the explicitly selected daily session calendar.",
        "bar_order": "Original input order checked without sorting or repairing rows.",
        "bar_duplicates": "Daily session duplicates checked without silently deduplicating rows.",
        "session_coverage": "Declared date range compared with the pinned session calendar.",
        "unfinished_session": "Daily bar requires session close plus 30 minute research grace.",
        "source_receipt": "Receipt chronology checked; receipt is not historical available_at.",
    }
    checks = [
        LocalCsvCheck(
            code=code,
            status="REJECT" if found else "PASS",
            count=len(found),
            message=messages[code],
            locations=found[:MAX_LOCATIONS],
            locations_truncated=len(found) > MAX_LOCATIONS,
        )
        for code, found in locations.items()
    ]
    for code, message in (
        (
            "source_rights",
            "Scope/license are caller claims; usage rights are not independently verified.",
        ),
        (
            "point_in_time",
            "Bar time and receipt are not historical available_at or revision/PIT evidence.",
        ),
        (
            "source_finality",
            "Elapsed sessions by import time do not prove this held file was final "
            "when captured; source finality/revisions remain unverified.",
        ),
        (
            "corporate_actions",
            "Corporate actions, adjustments and dividend ex/pay-date coverage "
            "are not independently verified.",
        ),
        (
            "source_session",
            "Calendar alignment does not verify the source's daily-session semantics.",
        ),
        (
            "adjustment_basis",
            f"Declared adjustment={request.source.adjustment}; "
            "price/currency units and adjustment lineage remain unverified.",
        ),
        (
            "volume_units",
            f"Declared volume unit={request.source.volume_unit}; "
            "units do not establish executable liquidity or fills.",
        ),
        (
            "phase1_evidence",
            "Phase1 preauthorization/post-review/source-evidence digests are claims, "
            "not independently verified receipts.",
        ),
    ):
        checks.append(LocalCsvCheck(code=code, status="INSUFFICIENT", count=0, message=message))
    if request.evidence_kind == "fixture":
        checks.append(
            LocalCsvCheck(
                code="fixture_scope",
                status="INSUFFICIENT",
                count=0,
                message="Declared fixture is engineering-only; no financial qualification.",
            )
        )
    coverage = LocalCsvCoverage(
        rows=len(rows),
        valid_rows=len(bars),
        first_date=min(dates) if dates else None,
        last_date=max(dates) if dates else None,
        expected_sessions=len(sessions),
        missing_sessions=missing,
        unexpected_sessions=unexpected,
    )
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(FIELDS)
    for bar in bars:
        writer.writerow(
            [bar.timestamp.isoformat(), bar.open, bar.high, bar.low, bar.close, bar.volume]
        )
    return checks, coverage, output.getvalue().encode(), bars
