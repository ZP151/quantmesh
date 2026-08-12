"""Watchlist persistence for the workstation (M9, issue #52).

The watchlist is the one UI-owned write surface in the workstation
(ADR-0011 decision 3): a single default watchlist of venue-scoped
instrument identities, stored as JSONL on the ADR-0006 discipline — atomic
temp+replace appends, fail-closed reads with line attribution, duplicate
identity refusal, and root-not-dir refusal. Legacy symbol-only rows remain
readable but are never assigned a guessed venue. Reading a missing store is
an empty list, never an error.
"""

from __future__ import annotations

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, field_validator

from quantmesh._fs import atomic_replace
from quantmesh.domain.models import Venue
from quantmesh.settings import settings

WATCHLIST_FILE = "watchlist.jsonl"


class WatchlistError(ValueError):
    """The watchlist was asked to do something it refuses."""


class WatchlistRecord(BaseModel):
    """One venue-scoped symbol, or a readable legacy unscoped row."""

    symbol: str = Field(min_length=1)
    venue: Venue | None = None
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
    """An append-only-by-discipline JSONL store of watchlist identities."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else settings.watchlists_dir

    def add(
        self,
        symbol: str,
        *,
        venue: Venue | str | None = None,
        now: datetime | None = None,
    ) -> WatchlistRecord:
        """Add one symbol; a duplicate or malformed symbol is refused."""
        try:
            record = WatchlistRecord(
                symbol=symbol,
                venue=venue,
                added_at=now if now is not None else datetime.now(UTC),
            )
        except ValidationError as error:
            raise WatchlistError(f"cannot add {symbol!r} to the watchlist") from error

        existing = self.all()
        if any(
            item.symbol == record.symbol
            and (item.venue is None or record.venue is None or item.venue is record.venue)
            for item in existing
        ):
            identity = (
                f"{record.venue.value}:{record.symbol}"
                if record.venue is not None
                else record.symbol
            )
            raise WatchlistError(f"{identity!r} is already on the watchlist")
        self._write(existing + [record])
        return record

    def remove(self, symbol: str, *, venue: Venue | str | None = None) -> None:
        """Remove one symbol; an absent symbol is refused (fail-closed)."""
        existing = self.all()
        selected_venue = Venue(venue) if venue is not None else None
        matches = [
            item
            for item in existing
            if item.symbol == symbol
            and (selected_venue is None or item.venue is selected_venue)
        ]
        if not matches:
            raise WatchlistError(f"{symbol!r} is not on the watchlist")
        if selected_venue is None and len(matches) > 1:
            raise WatchlistError(
                f"{symbol!r} is ambiguous across venues; supply a venue to remove it"
            )
        target = matches[0]
        remaining = [item for item in existing if item is not target]
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
        seen: dict[str, set[Venue | None]] = {}
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = WatchlistRecord.model_validate_json(line)
            except ValidationError as error:
                raise WatchlistError(
                    f"watchlist {path} line {line_number} is invalid"
                ) from error
            venues = seen.setdefault(record.symbol, set())
            if record.venue in venues or None in venues or (record.venue is None and venues):
                raise WatchlistError(
                    f"watchlist {path} line {line_number} repeats symbol "
                    f"{record.symbol!r}"
                )
            venues.add(record.venue)
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
            atomic_replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
