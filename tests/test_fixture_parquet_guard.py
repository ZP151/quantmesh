"""Primitive-only tests: no Parquet decoding, filesystem, or native queries."""

from __future__ import annotations

import importlib
import importlib.util

import pytest

from quantmesh.research.jobs import DatasetRejected


def guard():
    name = "quantmesh.research._fixture_parquet_guard"
    if importlib.util.find_spec(name) is None:
        pytest.fail("bounded Parquet guard is not implemented")
    return importlib.import_module(name)


def metadata():
    return (
        [
            ["timestamp", "TIMESTAMP WITH TIME ZONE"],
            ["open", "DOUBLE"],
            ["high", "DOUBLE"],
            ["low", "DOUBLE"],
            ["close", "DOUBLE"],
            ["volume", "DOUBLE"],
            ["instrument_type", "VARCHAR"],
            ["currency", "VARCHAR"],
        ],
        [
            ["duckdb_schema", None, "REQUIRED", 8, None, None],
            [
                "timestamp",
                "INT64",
                "OPTIONAL",
                None,
                "TIMESTAMP_MICROS",
                "TimestampType(isAdjustedToUTC=1, unit=TimeUnit(MILLIS=<null>, "
                "MICROS=MicroSeconds(), NANOS=<null>))",
            ],
            ["open", "DOUBLE", "OPTIONAL", None, None, None],
            ["high", "DOUBLE", "OPTIONAL", None, None, None],
            ["low", "DOUBLE", "OPTIONAL", None, None, None],
            ["close", "DOUBLE", "OPTIONAL", None, None, None],
            ["volume", "DOUBLE", "OPTIONAL", None, None, None],
            ["instrument_type", "BYTE_ARRAY", "OPTIONAL", None, "UTF8", None],
            ["currency", "BYTE_ARRAY", "OPTIONAL", None, "UTF8", None],
        ],
        [[2, 1, 1]],
    )


def rejected(call):
    with pytest.raises(DatasetRejected) as exc:
        call()
    assert exc.value.reason == "fixture_parquet_invalid"
    assert str(exc.value) == "dataset rejected: fixture_parquet_invalid"


class Hostile:
    calls = 0

    def callback(self, *args):
        type(self).calls += 1
        raise AssertionError("untrusted callback executed")

    __eq__ = __ne__ = __str__ = __iter__ = __len__ = __bool__ = __int__ = callback


class StringSubclass(str):
    __eq__ = Hostile.callback


class ListSubclass(list):
    __iter__ = __len__ = Hostile.callback


class IntSubclass(int):
    __eq__ = Hostile.callback


class BytesSubclass(bytes):
    __eq__ = Hostile.callback


class HostileMeta(type):
    def __eq__(cls, other):
        raise AssertionError("untrusted metaclass equality executed")


class ForeignContainer(metaclass=HostileMeta):
    pass


@pytest.mark.parametrize("nested", [False, True])
def test_foreign_container_metaclass_equality_is_never_called(nested):
    logical, physical, footer = metadata()
    if nested:
        logical[0] = ForeignContainer()
    else:
        logical = ForeignContainer()
    rejected(lambda: guard().validate_metadata(logical, physical, footer, 2))


@pytest.mark.parametrize("tuples", [False, True])
def test_accepts_observed_flat_schema_and_returns_actual_rows(tuples):
    logical, physical, footer = metadata()
    if tuples:
        logical, physical, footer = (
            tuple(tuple(row) for row in rows) for rows in (logical, physical, footer)
        )
    assert guard().validate_metadata(logical, physical, footer, 2) == 2


@pytest.mark.parametrize("section", [0, 1, 2])
@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "wrong-width"])
def test_refuses_missing_extra_duplicate_or_wrong_width_rows(section, mutation):
    parts = metadata()
    rows = parts[section]
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        rows.append(rows[-1][:])
    elif mutation == "duplicate":
        if len(rows) > 1:
            rows[-1] = rows[0][:]
        else:
            rows.append(rows[0][:])
    else:
        rows[0].append(None)
    rejected(lambda: guard().validate_metadata(*parts, 2))


@pytest.mark.parametrize("column", range(8))
@pytest.mark.parametrize("field", [0, 1])
def test_refuses_wrong_logical_names_types_and_order(column, field):
    logical, physical, footer = metadata()
    logical[column][field] = "foreign"
    rejected(lambda: guard().validate_metadata(logical, physical, footer, 2))


@pytest.mark.parametrize("row", range(9))
@pytest.mark.parametrize("field", range(6))
def test_refuses_wrong_physical_field_in_every_row(row, field):
    logical, physical, footer = metadata()
    physical[row][field] = "foreign" if physical[row][field] != "foreign" else None
    rejected(lambda: guard().validate_metadata(logical, physical, footer, 2))


@pytest.mark.parametrize("bad", [True, 2.0, "2", float("nan"), float("inf"), None])
@pytest.mark.parametrize("field", range(3))
def test_refuses_coerced_or_nonfinite_footer_values(bad, field):
    logical, physical, footer = metadata()
    footer[0][field] = bad
    rejected(lambda: guard().validate_metadata(logical, physical, footer, 2))


@pytest.mark.parametrize(
    "footer,remaining",
    [
        ([[0, 1, 1]], 2),
        ([[-1, 1, 1]], 2),
        ([[3, 1, 1]], 2),
        ([[2, 0, 1]], 2),
        ([[2, 3, 1]], 2),
        ([[5000, 4097, 1]], 5000),
        ([[2, 1, 0]], 2),
        ([[2, 1, 2]], 2),
        ([[1000001, 1, 1]], 1000001),
    ],
)
def test_refuses_footer_rows_groups_version_outside_bounds(footer, remaining):
    logical, physical, _ = metadata()
    rejected(lambda: guard().validate_metadata(logical, physical, footer, remaining))


@pytest.mark.parametrize("remaining", [True, 2.0, "2", None, 0, -1, 1000001])
def test_refuses_invalid_remaining_budget(remaining):
    rejected(lambda: guard().validate_metadata(*metadata(), remaining))


@pytest.mark.parametrize("rows,groups", [(1, 1), (1000000, 4096)])
def test_accepts_footer_row_and_group_boundaries(rows, groups):
    logical, physical, _ = metadata()
    assert guard().validate_metadata(logical, physical, [[rows, groups, 1]], rows) == rows


@pytest.mark.parametrize("slot", range(11))
def test_untrusted_objects_are_rejected_before_callbacks(slot):
    logical, physical, footer = metadata()
    remaining = 2
    hostile = Hostile()
    Hostile.calls = 0
    if slot == 0:
        logical = hostile
    elif slot == 1:
        physical = hostile
    elif slot == 2:
        footer = hostile
    elif slot == 3:
        logical[0] = hostile
    elif slot == 4:
        physical[0] = hostile
    elif slot == 5:
        footer[0] = hostile
    elif slot == 6:
        logical[0][0] = hostile
    elif slot == 7:
        physical[0][0] = hostile
    elif slot == 8:
        physical[0][3] = hostile
    elif slot == 9:
        footer[0][0] = hostile
    else:
        remaining = hostile
    rejected(lambda: guard().validate_metadata(logical, physical, footer, remaining))
    assert Hostile.calls == 0


@pytest.mark.parametrize("slot", range(5))
def test_primitive_subclasses_are_not_allowed(slot):
    logical, physical, footer = metadata()
    remaining = 2
    if slot == 0:
        logical = ListSubclass(logical)
    elif slot == 1:
        physical[1][5] = StringSubclass(physical[1][5])
    elif slot == 2:
        physical[0][3] = IntSubclass(8)
    elif slot == 3:
        footer[0][0] = IntSubclass(2)
    else:
        remaining = IntSubclass(2)
    rejected(lambda: guard().validate_metadata(logical, physical, footer, remaining))


@pytest.mark.parametrize("footer_size,file_size", [(1, 13), (262144, 262156), (1, 268435456)])
def test_envelope_accepts_bounded_footer_and_returns_its_length(footer_size, file_size):
    tail = footer_size.to_bytes(4, "little") + b"PAR1"
    assert guard().validate_file_envelope(b"PAR1", tail, file_size) == footer_size


@pytest.mark.parametrize(
    "first,last,size",
    [
        (b"PAR", b"\x01\0\0\0PAR1", 13),
        (b"PARE", b"\x01\0\0\0PAR1", 13),
        (b"PAR1", b"\x01\0\0\0PAR", 13),
        (b"PAR1", b"\x01\0\0\0PARE", 13),
        (b"PAR1", b"\0\0\0\0PAR1", 13),
        (b"PAR1", b"\x02\0\0\0PAR1", 13),
        (b"PAR1", b"\x01\0\x04\0PAR1", 262157),
        (b"PAR1", b"\xff\xff\xff\xffPAR1", 268435456),
        (b"PAR1", b"\x01\0\0\0PAR1", 11),
        (b"PAR1", b"\x01\0\0\0PAR1", 12),
        (b"PAR1", b"\x01\0\0\0PAR1", 268435457),
    ],
)
def test_envelope_refuses_truncation_magic_and_footer_size_bounds(first, last, size):
    rejected(lambda: guard().validate_file_envelope(first, last, size))


@pytest.mark.parametrize("slot", range(3))
@pytest.mark.parametrize("kind", ["foreign", "subclass", "coerced"])
def test_envelope_refuses_foreign_objects_and_wrong_exact_types(slot, kind):
    args = [b"PAR1", b"\x01\0\0\0PAR1", 13]
    if kind == "foreign":
        args[slot] = Hostile()
    elif kind == "subclass":
        args[slot] = IntSubclass(13) if slot == 2 else BytesSubclass(args[slot])
    else:
        args[slot] = True if slot == 2 else bytearray(args[slot])
    Hostile.calls = 0
    rejected(lambda: guard().validate_file_envelope(*args))
    assert Hostile.calls == 0
