"""Primitive-only conversion for one bounded fixture row chunk."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

from quantmesh.data.layout import validate_day, validate_symbol
from quantmesh.domain.market_data import Bar, interval_to_timedelta
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.research.jobs import DatasetRejected

_MAX_ROWS = 1024
_MAX_TEXT = 512
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_ALLOWED_TYPES = frozenset(item.value for item in InstrumentType)


def _invalid() -> None:
    raise DatasetRejected("fixture_rows_invalid")


def rows_to_bars(rows: object, *, interval: str, venue: Venue, symbol: str, day: str) -> list[Bar]:
    """Convert a small fixed projection into validated UTC bars."""
    try:
        if type(rows) is not list or len(rows) > _MAX_ROWS:
            _invalid()
        if type(venue) is not Venue:
            _invalid()
        if type(symbol) is not str or not 1 <= len(symbol) <= _MAX_TEXT:
            _invalid()
        if type(day) is not str or len(day) != 10:
            _invalid()
        if type(interval) is not str or not 1 <= len(interval) <= _MAX_TEXT:
            _invalid()
        validate_symbol(symbol)
        validate_day(day)
        date.fromisoformat(day)
        step = interval_to_timedelta(interval)
        step_us = (step.days * 86400 + step.seconds) * 1_000_000 + step.microseconds
        if step_us <= 0:
            _invalid()

        prepared = []
        for row in rows:
            if (type(row) is not tuple and type(row) is not list) or len(row) != 8:
                _invalid()
            ts, op, hi, lo, cl, vol, kind, currency = row
            # Gate every cell before any comparison, hashing, arithmetic, or coercion.
            if (
                type(ts) is not int
                or any(type(value) is not float for value in (op, hi, lo, cl, vol))
                or type(kind) is not str
                or type(currency) is not str
            ):
                _invalid()
            if len(kind) > _MAX_TEXT or not kind or len(currency) > _MAX_TEXT or not currency:
                _invalid()
            if kind not in _ALLOWED_TYPES:
                _invalid()
            if any(not math.isfinite(value) for value in (op, hi, lo, cl, vol)):
                _invalid()
            if (
                op <= 0
                or hi <= 0
                or lo <= 0
                or cl <= 0
                or vol < 0
                or hi < max(op, cl)
                or lo > min(op, cl)
            ):
                _invalid()
            if ts % step_us != 0:
                _invalid()
            timestamp = _EPOCH + timedelta(microseconds=ts)
            if timestamp.date().isoformat() != day:
                _invalid()
            prepared.append((timestamp, op, hi, lo, cl, vol, InstrumentType(kind), currency))

        return [
            Bar(
                instrument=Instrument(
                    symbol=symbol,
                    venue=venue,
                    instrument_type=item[6],
                    currency=item[7],
                ),
                timestamp=item[0],
                interval=interval,
                open=item[1],
                high=item[2],
                low=item[3],
                close=item[4],
                volume=item[5],
            )
            for item in prepared
        ]
    except DatasetRejected:
        raise
    except Exception:
        _invalid()
