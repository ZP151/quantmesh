"""Honest venue-aware instrument directory for a live workstation.

The directory declares configured or discovered instruments so navigation can
resolve a symbol to its venue.  It deliberately carries no market prices: live
marks belong to the timestamped feed surfaces and must never be fabricated
from configuration alone.
"""

from __future__ import annotations

from collections.abc import Iterable

from quantmesh.domain.models import Venue
from quantmesh.instruments.contracts import DatasetBinding
from quantmesh.live.prediction import PredictionBoard

LiveMarketDirectory = dict[str, dict[str, float | None]]


def build_live_market_directory(
    *,
    hyperliquid_symbols: Iterable[str] = (),
    moomoo_symbols: Iterable[str] = (),
    prediction: PredictionBoard | None = None,
    bindings: Iterable[DatasetBinding] = (),
) -> LiveMarketDirectory:
    """Combine configured watchlists and discovered history without fake marks."""

    directory: LiveMarketDirectory = {}

    def register(venue: Venue, symbols: Iterable[str]) -> None:
        for raw_symbol in symbols:
            symbol = raw_symbol.strip()
            if symbol:
                directory.setdefault(venue.value, {})[symbol] = None

    register(Venue.HYPERLIQUID, hyperliquid_symbols)
    register(Venue.MOOMOO, moomoo_symbols)
    if prediction is not None:
        for venue, symbols in prediction.venues().items():
            register(venue, symbols)
    for binding in bindings:
        register(binding.venue, (binding.symbol,))

    return {
        venue: dict(sorted(instruments.items())) for venue, instruments in sorted(directory.items())
    }
