"""Canonical lake layout: path grammar, shard naming and discovery (ADR-0003).

The partition convention is a durable contract:

    <dataset>/<interval>/<venue>/<symbol>/<date>/shard-0000.parquet

Every path component is validated against a whitelist here, so no name
can escape the lake root, cross partitions, or break tooling. The lake
and manifest modules both build on this single source of truth.
"""

import re
from pathlib import Path

DATASET_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")
SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
DAY_PATTERN = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
SHARD_NAME = "shard-0000.parquet"

# Windows device names (and the base name of "con.txt") cannot be
# directories; failing here gives a clean ValueError instead of a raw
# OSError at mkdir time on the workstation this runs on.
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


def _reject_windows_reserved(name: str, kind: str) -> None:
    if name.split(".")[0].lower() in _WINDOWS_RESERVED:
        raise ValueError(f"invalid {kind} {name!r} (reserved Windows device name)")


def validate_dataset_name(dataset: str) -> None:
    """Reject dataset names that could escape the lake root or break tooling."""
    _reject_windows_reserved(dataset, "dataset name")
    if DATASET_PATTERN.fullmatch(dataset) is None:
        raise ValueError(
            f"invalid dataset name {dataset!r} "
            "(expected lowercase [a-z0-9], separators only inside)"
        )


def validate_symbol(symbol: str) -> None:
    """Reject symbols that could escape the lake root or cross partitions."""
    _reject_windows_reserved(symbol, "symbol")
    if SYMBOL_PATTERN.fullmatch(symbol) is None:
        raise ValueError(
            f"invalid symbol {symbol!r} "
            "(expected [A-Za-z0-9], separators and dots only inside)"
        )


def validate_day(day: str) -> None:
    """Reject partition dates that are not canonical ISO UTC dates."""
    if DAY_PATTERN.fullmatch(day) is None:
        raise ValueError(f"invalid day {day!r} (expected an ISO UTC date like 2026-08-07)")


def shards_in(partition: Path) -> list[Path]:
    """Canonical shard files under one partition dir, in ISO-day order.

    Only ``<day>/shard-0000.parquet`` with a valid ISO UTC day name
    counts; stray files or directories are never merged into a series.
    Symlinked shards or day directories are rejected: a link could point
    the lake at bytes outside the root, and reads must never depend on
    where a link happens to resolve.
    """
    shards: list[Path] = []
    for path in partition.glob(f"*/{SHARD_NAME}"):
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError(f"symlink in lake layout is not allowed: {path}")
        if DAY_PATTERN.fullmatch(path.parent.name) is not None:
            shards.append(path)
    return sorted(shards)
