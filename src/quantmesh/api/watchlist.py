"""Watchlist persistence for the workstation (M9, issue #52).

The watchlist is the one UI-owned write surface in the workstation
(ADR-0011 decision 3): a single default watchlist of instrument
symbols, stored as JSONL on the ADR-0006 discipline — atomic
temp+replace appends, fail-closed reads with line attribution,
duplicate-symbol refusal, root-not-dir refusal. Reading a missing
store is an empty list, never an error.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

from quantmesh.settings import settings

WATCHLIST_FILE = "watchlist.jsonl"


class WatchlistError(ValueError):
    """The watchlist was asked to do something it refuses."""


class WatchlistRecord(BaseModel):
    """One symbol on the default watchlist, with its added-at stamp."""

    symbol: str = Field(min_length=1)
    added_at: datetime

    model_config = {"extra": "forbid"}

    @field_validator("symbol")
    @classmethod
    def symbol_shape(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("symbol must not be empty or whitespace")
        if any(character.isspace() for character in value):
            raise ValueError("symbol must not contain whitespace")
        return value

    @field_validator("added_at")
    @classmethod
    def aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("added_at must carry a timezone")
        return value.astimezone(UTC)


class WatchlistStore:
    """An append-only-by-discipline JSONL store of watchlist symbols."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else settings.watchlists_dir

    def add(self, symbol: str, *, now: datetime | None = None) -> WatchlistRecord:
        """Add one symbol; a duplicate or malformed symbol is refused."""
        try:
            record = WatchlistRecord(
                symbol=symbol,
                added_at=now if now is not None else datetime.now(UTC),
            )
        except ValidationError as error:
            raise WatchlistError(f"cannot add {symbol!r} to the watchlist") from error

        existing = self.all()
        if any(item.symbol == record.symbol for item in existing):
            raise WatchlistError(f"{record.symbol!r} is already on the watchlist")
        self._write(existing + [record])
        return record

    def remove(self, symbol: str) -> None:
        """Remove one symbol; an absent symbol is refused (fail-closed)."""
        existing = self.all()
        remaining = [item for item in existing if item.symbol != symbol]
        if len(remaining) == len(existing):
            raise WatchlistError(f"{symbol!r} is not on the watchlist")
        self._write(remaining)

    def all(self) -> list[WatchlistRecord]:
        if not self.root.exists():
            return []
        if not self.root.is_dir():
            raise WatchlistError(f"watchlist root {self.root} is not a directory")
        path = self.root / WATCHLIST_FILE
        if not path.exists():
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise WatchlistError(f"watchlist {path} is unreadable") from error
        records = []
        seen: set[str] = set()
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = WatchlistRecord.model_validate_json(line)
            except ValidationError as error:
                raise WatchlistError(
                    f"watchlist {path} line {line_number} is invalid"
                ) from error
            if record.symbol in seen:
                raise WatchlistError(
                    f"watchlist {path} line {line_number} repeats symbol "
                    f"{record.symbol!r}"
                )
            seen.add(record.symbol)
            records.append(record)
        return records

    def _write(self, records: list[WatchlistRecord]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / WATCHLIST_FILE
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{WATCHLIST_FILE}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(record.model_dump_json())
                    handle.write("\n")
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
