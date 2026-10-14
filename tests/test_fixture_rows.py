from datetime import UTC, datetime

import pytest

from quantmesh.domain.models import InstrumentType, Venue
from quantmesh.research import _fixture_rows
from quantmesh.research._fixture_rows import rows_to_bars
from quantmesh.research.jobs import DatasetRejected


def row(ts=1791936000000000, *, kind="equity", currency="USD", **changes):
    values = [ts, 10.0, 12.0, 9.0, 11.0, 100.0, kind, currency]
    for index, value in changes.items():
        values[int(index)] = value
    return tuple(values)


def reject(rows, **overrides):
    args = {"interval": "1m", "venue": Venue.MOOMOO, "symbol": "AAPL", "day": "2026-10-14"}
    args.update(overrides)
    with pytest.raises(DatasetRejected, match="fixture_rows_invalid"):
        rows_to_bars(rows, **args)


def test_two_primitive_rows_make_utc_aligned_bars():
    bars = rows_to_bars(
        [row(), row(1791936060000000)],
        interval="1m",
        venue=Venue.MOOMOO,
        symbol="AAPL",
        day="2026-10-14",
    )
    assert len(bars) == 2
    assert bars[0].timestamp == datetime(2026, 10, 14, tzinfo=UTC)
    assert bars[0].timestamp.tzinfo is UTC
    assert bars[1].timestamp.microsecond == 0
    assert bars[0].instrument.instrument_type is InstrumentType.EQUITY


@pytest.mark.parametrize(
    "bad",
    [
        [row(kind="stock")],
        [row(kind="not-a-type")],
        [row("x")],
        [row(ts=True)],
        [row(ts=1791936000000000.0)],
        [row(ts=None)],
        [row(**{"1": float("nan")})],
        [row(**{"2": float("inf")})],
        [row(**{"3": 0.0})],
        [row(**{"4": -1.0})],
        [row(**{"5": -1.0})],
        [row(currency="")],
        [row(currency="x" * 513)],
        [row(ts=1791936000000001)],
        [row(ts=1791849600000000)],
        [row(**{"2": 9.0, "3": 10.0})],
        [[*row()[:-1], None]],
        [(1, 2, 3, 4, 5, 6, "equity", "USD")],
    ],
)
def test_invalid_rows_rejected(bad):
    reject(bad)


class HostileList(list):
    def __len__(self):
        raise AssertionError("callback")


class HostileString(str):
    def __eq__(self, other):
        raise AssertionError("callback")


class HostileFloat(float):
    def __lt__(self, other):
        raise AssertionError("callback")


def test_hostile_subclasses_rejected_without_callbacks():
    reject(HostileList([row()]))
    hostile = list(row())
    hostile[6] = HostileString("equity")
    reject([hostile])
    hostile = list(row())
    hostile[1] = HostileFloat(10.0)
    reject([hostile])


def test_rows_are_bounded_and_domain_arguments_are_exact():
    reject([row()] * 1025)
    reject([row()], interval="0m")
    reject([row()], symbol="../AAPL")
    reject([row()], day="2026-02-30")
    reject([row()], venue="moomoo")


def test_invalid_late_row_rejects_before_any_model_construction(monkeypatch):
    def forbidden(**kwargs):
        raise AssertionError("model construction started before complete validation")

    monkeypatch.setattr(_fixture_rows, "Instrument", forbidden)
    monkeypatch.setattr(_fixture_rows, "Bar", forbidden)
    reject([row(), row(**{"2": 8.0})])


_CALLBACKS = []


class RecordingMeta(type):
    def __eq__(cls, other):
        _CALLBACKS.append("eq")
        return False

    def __hash__(cls):
        _CALLBACKS.append("hash")
        return 0


class ForeignRow(metaclass=RecordingMeta):
    pass


class RecordingList(list):
    def __len__(self):
        _CALLBACKS.append("len")
        return super().__len__()


class RecordingString(str):
    def __eq__(self, other):
        _CALLBACKS.append("cell-eq")
        return super().__eq__(other)


def test_rejects_nonprimitive_roots_rows_and_cells_without_callbacks():
    _CALLBACKS.clear()
    reject(RecordingList([row()]))
    reject([ForeignRow()])
    hostile = list(row())
    hostile[6] = RecordingString("equity")
    reject([hostile])
    assert _CALLBACKS == []


def test_integer_epoch_conversion_preserves_negative_utc_second():
    bars = rows_to_bars(
        [row(-86_400_000_000), row(-86_399_000_000)],
        interval="1s",
        venue=Venue.MOOMOO,
        symbol="AAPL",
        day="1969-12-31",
    )
    assert bars[0].timestamp == datetime(1969, 12, 31, tzinfo=UTC)
    assert bars[1].timestamp == datetime(1969, 12, 31, 0, 0, 1, tzinfo=UTC)
