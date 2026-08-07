"""Canonical event-domain model contracts (M6, issue #34, Phase A)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from quantmesh.domain.models import Venue
from quantmesh.events.models import (
    EventMarket,
    EventVenue,
    ImpliedProbability,
    MarketQuote,
    Outcome,
    ResolutionRule,
)

NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)


def _market(**overrides) -> EventMarket:
    fields = dict(
        venue=EventVenue.POLYMARKET,
        venue_market_id="0xcondition",
        event_ticker="some-event",
        title="Will X happen?",
        expiry_at=NOW,
        outcomes=[
            Outcome(name="Yes", venue_outcome_id="tok-yes"),
            Outcome(name="No", venue_outcome_id="tok-no"),
        ],
        resolution_rule=ResolutionRule.of("The event resolves to Yes if X happens."),
    )
    fields.update(overrides)
    return EventMarket(**fields)


# -- ResolutionRule ------------------------------------------------------------


def test_fingerprint_is_deterministic() -> None:
    rule = ResolutionRule.of("The event resolves to Yes if X happens.")
    again = ResolutionRule.of("The event resolves to Yes if X happens.")
    assert rule.fingerprint == again.fingerprint
    assert len(rule.fingerprint) == 64
    assert all(char in "0123456789abcdef" for char in rule.fingerprint)


def test_fingerprint_is_normalized_across_case_and_whitespace() -> None:
    a = ResolutionRule.of("Cut   by 25 bps\nper the FOMC statement.")
    b = ResolutionRule.of("cut by 25 bps per the FOMC statement.")
    assert a.fingerprint == b.fingerprint


def test_a_substantive_rule_change_changes_the_fingerprint() -> None:
    a = ResolutionRule.of("Resolves to Yes if X happens.")
    b = ResolutionRule.of("Resolves to Yes if Y happens.")
    assert a.fingerprint != b.fingerprint


def test_wrong_fingerprint_is_rejected() -> None:
    with pytest.raises(ValidationError, match="fingerprint"):
        ResolutionRule(rule_text="Some rule text.", fingerprint="0" * 64)


# -- EventVenue ----------------------------------------------------------------


def test_event_venues_map_to_the_domain_venue_surface() -> None:
    assert EventVenue.POLYMARKET.to_domain_venue() is Venue.POLYMARKET
    assert EventVenue.KALSHI.to_domain_venue() is Venue.KALSHI


# -- EventMarket ---------------------------------------------------------------


def test_event_market_round_trips_with_resolution() -> None:
    market = _market(
        resolution=["No"],
        resolved_at=datetime(2026, 8, 8, 20, 0, 0, tzinfo=UTC),
    )
    assert market.resolution == ["No"]
    assert market.outcome_id("Yes") == "tok-yes"
    assert market.outcome_id("No") == "tok-no"
    assert market.outcome_id("Maybe") is None


def test_split_resolution_keeps_every_winner() -> None:
    market = _market(resolution=["Yes", "No"])
    assert market.resolution == ["Yes", "No"]


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _market(start_at=datetime(2026, 8, 8))
    with pytest.raises(ValidationError, match="timezone-aware"):
        _market(resolved_at=datetime(2026, 8, 8))


def test_duplicate_outcome_names_are_rejected() -> None:
    with pytest.raises(ValidationError, match="not unique"):
        _market(
            outcomes=[
                Outcome(name="Yes", venue_outcome_id="a"),
                Outcome(name="Yes", venue_outcome_id="b"),
            ]
        )


def test_resolution_names_must_be_outcomes() -> None:
    with pytest.raises(ValidationError, match="not outcomes"):
        _market(resolution=["Maybe"])


def test_market_needs_at_least_one_outcome() -> None:
    with pytest.raises(ValidationError):
        _market(outcomes=[])


# -- MarketQuote ---------------------------------------------------------------


def _quote(**overrides) -> MarketQuote:
    fields = dict(
        venue=EventVenue.POLYMARKET,
        symbol="tok-yes",
        timestamp=NOW,
        best_bid=0.5,
        best_ask=0.6,
        bid_depth=100.0,
        ask_depth=50.0,
        tick_size=0.001,
        min_order_size=5.0,
        taker_fee_bps=1000.0,
    )
    fields.update(overrides)
    return MarketQuote(**fields)


def test_quote_round_trips() -> None:
    quote = _quote()
    assert quote.best_bid == 0.5
    assert quote.best_ask == 0.6
    assert quote.taker_fee_bps == 1000.0


def test_quote_prices_are_bounded_to_the_unit_interval() -> None:
    for field in ("best_bid", "best_ask", "last_trade_price"):
        with pytest.raises(ValidationError):
            _quote(**{field: 1.5})
        with pytest.raises(ValidationError):
            _quote(**{field: -0.1})


def test_quote_rejects_non_positive_tick_size_and_negative_fee() -> None:
    with pytest.raises(ValidationError):
        _quote(tick_size=0.0)
    with pytest.raises(ValidationError):
        _quote(taker_fee_bps=-1.0)


def test_quote_timestamp_must_be_aware() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _quote(timestamp=datetime(2026, 8, 8))


def test_quote_side_can_be_empty() -> None:
    quote = _quote(best_bid=None, best_ask=None, bid_depth=0.0)
    assert quote.best_bid is None
    assert quote.best_ask is None


# -- ImpliedProbability (Phase C computes; Phase A pins the model) -------------


def test_implied_probability_bounds() -> None:
    with pytest.raises(ValidationError):
        ImpliedProbability(
            probability=1.01, spread_adjustment=0.0, liquidity_confidence=0.5,
            basis="clob-mid", timestamp=NOW,
        )
    with pytest.raises(ValidationError):
        ImpliedProbability(
            probability=0.5, spread_adjustment=0.0, liquidity_confidence=-0.1,
            basis="clob-mid", timestamp=NOW,
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        ImpliedProbability(
            probability=0.5, spread_adjustment=0.0, liquidity_confidence=0.5,
            basis="clob-mid", timestamp=datetime(2026, 8, 8),
        )
