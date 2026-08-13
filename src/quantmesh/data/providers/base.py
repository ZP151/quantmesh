"""Provider contract: the fetch surface every venue adapter implements.

Adapters return canonical domain models only (issue #14 schemas);
provider-specific payload shapes live inside adapters and their bundled
fixture files. A consumer of the lake or of ``Provider.fetch_*`` never
sees a vendor's schema — the M3 provider-isolation exit criterion.

Legacy providers remain fixture-only in the registry unless they expose an
immutable, bounded capability descriptor. A descriptor can admit read-only
live data, but it grants no order method or execution authority.
"""

import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from quantmesh.data.capabilities import ProviderDescriptor
from quantmesh.domain.market_data import Bar, OrderBook, TradeEvent
from quantmesh.domain.models import Instrument, Side, Venue


class ProviderMode(StrEnum):
    """How a provider reaches its venue; fixture is the only M3 mode."""

    FIXTURE = "fixture"
    SANDBOX = "sandbox"
    LIVE = "live"


_SIDE_MAP = {"B": Side.BUY, "S": Side.SELL}


class Provider(ABC):
    """Venue adapter contract: bars, order books and trades, canonical out."""

    venue: Venue
    mode: ProviderMode = ProviderMode.FIXTURE
    descriptor: ProviderDescriptor | None = None

    def _require_venue(self, instrument: Instrument) -> None:
        """Fail closed when an instrument belongs to another venue's adapter."""
        if instrument.venue is not self.venue:
            raise ValueError(
                f"{self.venue.value} adapter cannot serve {instrument.venue.value} instruments"
            )

    @abstractmethod
    def fetch_bars(
        self,
        instrument: Instrument,
        *,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]:
        """Bars for ``instrument`` at the canonical ``interval``, provider order."""

    @abstractmethod
    def fetch_order_books(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[OrderBook]:
        """Depth snapshots in the order the provider reports them."""

    @abstractmethod
    def fetch_trades(
        self,
        instrument: Instrument,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[TradeEvent]:
        """Executed trades in the order the provider reports them."""


def _require_aware(timestamp: datetime | None, name: str) -> None:
    if timestamp is not None and timestamp.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _within(timestamp: datetime, start: datetime | None, end: datetime | None) -> bool:
    """Inclusive range membership, matching the lake's range semantics."""
    if start is not None and timestamp < start:
        return False
    if end is not None and timestamp > end:
        return False
    return True


class FixtureProvider(Provider, ABC):
    """Base for adapters serving bundled JSON fixture payloads.

    ``fixture_dir`` is injectable so tests can point at their own
    payloads; the default is the package's ``fixtures/`` directory.
    """

    def __init__(self, fixture_dir: Path | None = None) -> None:
        self._fixture_dir = (
            fixture_dir if fixture_dir is not None else Path(__file__).parent / "fixtures"
        )

    def _load(self, name: str) -> object:
        path = self._fixture_dir / name
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"fixture {path} is unreadable or invalid: {error}") from error

    def _load_rows(self, name: str) -> list[dict]:
        """Load a fixture, failing closed when it holds no rows.

        An empty fixture would be indistinguishable from "no data in the
        requested range" — that ambiguity is fail-open, so it is an error.
        """
        rows = self._load(name)
        if not rows:
            raise ValueError(f"fixture {self._fixture_dir / name} has no rows")
        return rows

    def _map_rows(self, name: str, rows: list[dict], parse: Callable[[dict], object]) -> list:
        """Map fixture rows, attributing failures to the fixture and row.

        Hand-edited fixtures that drop a key, drift to a naive timestamp,
        or trip a domain validator surface as a ``ValueError`` naming the
        fixture file and row index instead of a raw ``KeyError`` or a bare
        model dump.
        """
        path = self._fixture_dir / name
        parsed = []
        for index, row in enumerate(rows):
            try:
                parsed.append(parse(row))
            except ValueError as error:
                raise ValueError(f"fixture {path} row {index} is invalid: {error}") from error
            except (KeyError, IndexError, TypeError) as error:
                raise ValueError(f"fixture {path} row {index} is malformed: {error}") from error
        return parsed

    def _filtered(self, events: list[Bar | OrderBook | TradeEvent], start, end) -> list:
        """Inclusive time filter with fail-closed aware bounds."""
        _require_aware(start, "start")
        _require_aware(end, "end")
        return [event for event in events if _within(event.timestamp, start, end)]

    @staticmethod
    def _utc(value: str) -> datetime:
        """Parse a fixture timestamp, failing closed when it is naive."""
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError(f"fixture timestamp {value!r} is not timezone-aware")
        return parsed.astimezone(UTC)

    @staticmethod
    def _side(marker: str) -> Side:
        """Map a fixture side marker, failing closed on anything unknown."""
        try:
            return _SIDE_MAP[marker]
        except KeyError as error:
            raise ValueError(f"unknown trade side {marker!r}") from error
