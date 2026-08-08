"""M7 Phase D tests: portfolio constraint surface and exposure
decomposition (issue #42).

The constraint surface is four typed cap classes evaluated as pure
arithmetic over the holdings' target weights: per-venue caps,
asset-class caps, risk-weighted event-exposure caps (the M6 implied
probability of the held side), and per-venue leverage limits drawn
from the M5 risk checks. Violations are typed observed-vs-limit
values; exposure decomposes by venue, asset class and event.
"""

import pytest
from pydantic import ValidationError

from quantmesh.domain.models import Venue
from quantmesh.hyperliquid.risk import RiskLimits
from quantmesh.portfolio import (
    AssetClassCap,
    ConstraintKind,
    EventRiskCap,
    ExposureDecomposition,
    LeverageCap,
    PortfolioConstraints,
    PortfolioHolding,
    VenueCap,
    check_constraints,
    constraint_values,
    decompose_exposure,
    leverage_cap_from_risk_limits,
)


def _holding(
    venue=Venue.MOOMOO,
    symbol="AAA",
    asset_class="equity",
    event_key=None,
    held_probability=None,
    weight=0.25,
) -> PortfolioHolding:
    return PortfolioHolding(
        venue=venue,
        symbol=symbol,
        asset_class=asset_class,
        event_key=event_key,
        held_probability=held_probability,
        weight=weight,
    )


class TestHoldingValidation:
    def test_probability_without_event_key_refused(self) -> None:
        with pytest.raises(ValidationError, match="without an event key"):
            _holding(event_key=None, held_probability=0.5)

    def test_event_without_probability_refused(self) -> None:
        with pytest.raises(ValidationError, match="missing the implied probability"):
            _holding(event_key="FED-SEP", held_probability=None)

    def test_negative_weight_refused(self) -> None:
        with pytest.raises(ValidationError, match="weight"):
            _holding(weight=-0.1)


class TestCapValidation:
    def test_venue_cap_bounds(self) -> None:
        with pytest.raises(ValidationError, match="max_fraction"):
            VenueCap(venue=Venue.MOOMOO, max_fraction=0.0)
        with pytest.raises(ValidationError, match="max_fraction"):
            VenueCap(venue=Venue.MOOMOO, max_fraction=1.5)

    def test_constraints_refuse_duplicates(self) -> None:
        with pytest.raises(ValidationError, match="duplicate venue caps"):
            PortfolioConstraints(
                venue_caps=[
                    VenueCap(venue=Venue.MOOMOO, max_fraction=0.5),
                    VenueCap(venue=Venue.MOOMOO, max_fraction=0.4),
                ]
            )
        with pytest.raises(ValidationError, match="duplicate asset-class caps"):
            PortfolioConstraints(
                asset_class_caps=[
                    AssetClassCap(asset_class="equity", max_fraction=0.5),
                    AssetClassCap(asset_class="equity", max_fraction=0.4),
                ]
            )
        with pytest.raises(ValidationError, match="duplicate leverage caps"):
            PortfolioConstraints(
                leverage_caps=[
                    LeverageCap(venue=Venue.MOOMOO, max_leverage=2.0),
                    LeverageCap(venue=Venue.MOOMOO, max_leverage=3.0),
                ]
            )

    def test_empty_surface_has_no_constraints(self) -> None:
        assert PortfolioConstraints().is_empty()
        assert not PortfolioConstraints(
            venue_caps=[VenueCap(venue=Venue.MOOMOO, max_fraction=0.5)]
        ).is_empty()

    def test_leverage_cap_drawn_from_m5_risk_limits(self) -> None:
        """The M5 pre-submission check's max_leverage is the source of
        the portfolio-level per-venue limit (issue #31 linkage)."""
        limits = RiskLimits(max_leverage=4.5)
        cap = leverage_cap_from_risk_limits(Venue.HYPERLIQUID, limits)
        assert cap.venue is Venue.HYPERLIQUID
        assert cap.max_leverage == 4.5
        assert cap.model_dump() == {
            "venue": "hyperliquid",
            "max_leverage": 4.5,
        }


class TestConstraintValues:
    def test_venue_exposure_sums_weights(self) -> None:
        constraints = PortfolioConstraints(
            venue_caps=[VenueCap(venue=Venue.MOOMOO, max_fraction=0.5)]
        )
        holdings = [
            _holding(Venue.MOOMOO, "AAA", weight=0.2),
            _holding(Venue.MOOMOO, "BBB", weight=0.2),
            _holding(Venue.HYPERLIQUID, "BTC", weight=0.6),
        ]
        values = constraint_values(holdings, constraints)
        assert len(values) == 1
        value = values[0]
        assert value.kind is ConstraintKind.VENUE
        assert value.label == "venue:moomoo"
        assert value.observed == pytest.approx(0.4)
        assert value.limit == 0.5
        assert not value.is_violated()

    def test_every_constraint_class_is_measured(self) -> None:
        constraints = PortfolioConstraints(
            venue_caps=[VenueCap(venue=Venue.MOOMOO, max_fraction=0.6)],
            asset_class_caps=[AssetClassCap(asset_class="equity", max_fraction=0.7)],
            event_risk_caps=[EventRiskCap(max_fraction=0.3)],
            leverage_caps=[LeverageCap(venue=Venue.MOOMOO, max_leverage=2.0)],
        )
        holdings = [
            _holding(Venue.MOOMOO, "AAA", asset_class="equity", weight=0.4),
            # An event holding: risk exposure counts weight x (1 - p).
            _holding(
                Venue.POLYMARKET,
                "tok-1",
                asset_class="event",
                event_key="FED-SEP",
                held_probability=0.05,
                weight=0.3,
            ),
            _holding(Venue.HYPERLIQUID, "BTC", asset_class="crypto", weight=0.3),
        ]
        values = constraint_values(holdings, constraints)
        by_label = {value.label: value for value in values}
        assert by_label["venue:moomoo"].observed == pytest.approx(0.4)
        assert by_label["class:equity"].observed == pytest.approx(0.4)
        # 0.3 x (1 - 0.05): a position on a 5%-probability outcome.
        assert by_label["event-risk:0"].observed == pytest.approx(0.285)
        assert by_label["leverage:moomoo"].observed == pytest.approx(0.4)
        assert by_label["leverage:moomoo"].limit == 2.0
        assert not any(value.is_violated() for value in values)

    def test_violation_is_typed_observed_vs_limit(self) -> None:
        constraints = PortfolioConstraints(
            venue_caps=[VenueCap(venue=Venue.MOOMOO, max_fraction=0.5)]
        )
        holdings = [_holding(Venue.MOOMOO, "AAA", weight=0.6)]
        checks = check_constraints(holdings, constraints)
        violations = checks.violations()
        assert len(violations) == 1
        assert violations[0].observed == pytest.approx(0.6)
        assert violations[0].limit == 0.5
        assert not checks.allowed()

    def test_checks_allowed_with_zero_violations(self) -> None:
        constraints = PortfolioConstraints(
            venue_caps=[VenueCap(venue=Venue.MOOMOO, max_fraction=0.5)]
        )
        holdings = [_holding(Venue.MOOMOO, "AAA", weight=0.4)]
        assert check_constraints(holdings, constraints).allowed()

    def test_duplicate_holdings_fail_closed(self) -> None:
        constraints = PortfolioConstraints()
        holdings = [
            _holding(Venue.MOOMOO, "AAA", weight=0.4),
            _holding(Venue.MOOMOO, "AAA", weight=0.4),
        ]
        with pytest.raises(ValueError, match="duplicate holdings"):
            check_constraints(holdings, constraints)


class TestExposureDecomposition:
    def test_decomposes_by_venue_class_and_event(self) -> None:
        holdings = [
            _holding(Venue.MOOMOO, "AAA", asset_class="equity", weight=0.3),
            _holding(Venue.MOOMOO, "BBB", asset_class="equity", weight=0.2),
            _holding(Venue.HYPERLIQUID, "BTC", asset_class="crypto", weight=0.2),
            _holding(
                Venue.POLYMARKET,
                "tok-1",
                asset_class="event",
                event_key="FED-SEP",
                held_probability=0.25,
                weight=0.2,
            ),
            _holding(
                Venue.KALSHI,
                "KXFED",
                asset_class="event",
                event_key="FED-SEP",
                held_probability=0.5,
                weight=0.1,
            ),
        ]
        result = decompose_exposure(holdings)
        assert isinstance(result, ExposureDecomposition)
        assert result.total == pytest.approx(1.0)
        assert result.by_venue == {
            "moomoo": pytest.approx(0.5),
            "hyperliquid": pytest.approx(0.2),
            "polymarket": pytest.approx(0.2),
            "kalshi": pytest.approx(0.1),
        }
        assert result.by_asset_class == {
            "equity": pytest.approx(0.5),
            "crypto": pytest.approx(0.2),
            "event": pytest.approx(0.3),
        }
        # Both FED-SEP markets aggregate under one event key.
        assert result.by_event == {"FED-SEP": pytest.approx(0.3)}
        # 0.2 x 0.75 + 0.1 x 0.5.
        assert result.event_risk == pytest.approx(0.2)

    def test_event_risk_zero_without_event_holdings(self) -> None:
        result = decompose_exposure(
            [_holding(Venue.MOOMOO, "AAA", weight=0.5), _holding(Venue.MOOMOO, "BBB", weight=0.5)]
        )
        assert result.by_event == {}
        assert result.event_risk == 0.0

    def test_venue_exposure_accessor(self) -> None:
        result = decompose_exposure([_holding(Venue.MOOMOO, "AAA", weight=0.3)])
        assert result.venue_exposure(Venue.MOOMOO) == pytest.approx(0.3)
        assert result.venue_exposure(Venue.KALSHI) == pytest.approx(0.0)
