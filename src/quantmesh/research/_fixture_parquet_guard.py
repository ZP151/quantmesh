"""Bounded primitive metadata checks for the canonical job fixture reader.

No file opening or numerical execution occurs here. These checks do not admit
a Worker or certify a native decoder; the caller must enforce its read policy.
"""

from __future__ import annotations

from quantmesh.research.jobs import DatasetRejected

_LOGICAL = (
    ("timestamp", "TIMESTAMP WITH TIME ZONE"),
    ("open", "DOUBLE"),
    ("high", "DOUBLE"),
    ("low", "DOUBLE"),
    ("close", "DOUBLE"),
    ("volume", "DOUBLE"),
    ("instrument_type", "VARCHAR"),
    ("currency", "VARCHAR"),
)
_PHYSICAL = (
    ("duckdb_schema", None, "REQUIRED", 8, None, None),
    (
        "timestamp",
        "INT64",
        "OPTIONAL",
        None,
        "TIMESTAMP_MICROS",
        "TimestampType(isAdjustedToUTC=1, unit=TimeUnit(MILLIS=<null>, "
        "MICROS=MicroSeconds(), NANOS=<null>))",
    ),
    ("open", "DOUBLE", "OPTIONAL", None, None, None),
    ("high", "DOUBLE", "OPTIONAL", None, None, None),
    ("low", "DOUBLE", "OPTIONAL", None, None, None),
    ("close", "DOUBLE", "OPTIONAL", None, None, None),
    ("volume", "DOUBLE", "OPTIONAL", None, None, None),
    ("instrument_type", "BYTE_ARRAY", "OPTIONAL", None, "UTF8", None),
    ("currency", "BYTE_ARRAY", "OPTIONAL", None, "UTF8", None),
)


def _reject() -> None:
    raise DatasetRejected("fixture_parquet_invalid")


def _rows(value: object, count: int, width: int) -> list | tuple:
    if (type(value) is not list and type(value) is not tuple) or len(value) != count:
        _reject()
    for row in value:
        if (type(row) is not list and type(row) is not tuple) or len(row) != width:
            _reject()
    return value


def _schema(value: object, expected: tuple) -> None:
    rows = _rows(value, len(expected), len(expected[0]))
    # No supplied cell is compared until every cell has its exact primitive type.
    # This rejects subclasses and avoids invoking foreign equality callbacks.
    for row, wanted in zip(rows, expected, strict=True):
        for cell, literal in zip(row, wanted, strict=True):
            if type(cell) is not type(literal):
                _reject()
    for row, wanted in zip(rows, expected, strict=True):
        for cell, literal in zip(row, wanted, strict=True):
            if cell != literal:
                _reject()


def validate_metadata(
    logical: object, physical: object, footer: object, remaining_rows: int
) -> int:
    """Return declared physical row count after exact schema and budget checks."""
    if type(remaining_rows) is not int or not 1 <= remaining_rows <= 1_000_000:
        _reject()
    _schema(logical, _LOGICAL)
    _schema(physical, _PHYSICAL)
    fields = _rows(footer, 1, 3)[0]
    if any(type(field) is not int for field in fields):
        _reject()
    rows, groups, version = fields
    if not 1 <= rows <= remaining_rows or not 1 <= groups <= min(rows, 4096) or version != 1:
        _reject()
    return rows


def validate_file_envelope(first4: bytes, last8: bytes, file_size: int) -> int:
    """Check fixed framing and return footer length without decoding its bytes."""
    if type(first4) is not bytes or type(last8) is not bytes or type(file_size) is not int:
        _reject()
    if not 12 <= file_size <= 256 * 1024 * 1024:
        _reject()
    if len(first4) != 4 or len(last8) != 8 or first4 != b"PAR1" or last8[4:] != b"PAR1":
        _reject()
    footer_len = int.from_bytes(last8[:4], "little")
    if not 1 <= footer_len <= 256 * 1024 or footer_len > file_size - 12:
        _reject()
    return footer_len
