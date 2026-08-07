"""Canonical event-market domain (M6, issue #34, Phase A).

Venue-neutral event, outcome, resolution-rule, quote and implied-
probability models that both Polymarket and Kalshi adapters normalize
into. See ``quantmesh.events.models`` for the contracts.
"""

from quantmesh.events.models import (
    EventMarket,
    EventVenue,
    ImpliedProbability,
    MarketQuote,
    Outcome,
    ResolutionRule,
)

__all__ = [
    "EventMarket",
    "EventVenue",
    "ImpliedProbability",
    "MarketQuote",
    "Outcome",
    "ResolutionRule",
]
