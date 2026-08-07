"""M7 Phase D tests: risk-budget portfolio construction (issue #42).

The equal-risk-budget optimum is verified against closed forms
(two-asset risk parity is inverse-volatility regardless of correlation:
for variances a and 1 the parity weights are (1/(1+sqrt(a)), sqrt(a)/
(1+sqrt(a)))), against each binding constraint class, and against the
fail-closed discipline: structural infeasibility, invalid covariance
inputs, and a missing scipy all refuse with typed errors.
"""

import numpy as np
import pytest

import quantmesh.portfolio.optimizer as optimizer_module
from quantmesh.domain.models import Venue
from quantmesh.portfolio import (
    AssetClassCap,
    EventRiskCap,
    LeverageCap,
    OptimizationFailure,
    PortfolioConstraints,
    PortfolioHolding,
    VenueCap,
    risk_budget_weights,
)
from quantmesh.research.pipelines import PipelineUnavailableError


def _holding(symbol="AAA", venue=Venue.MOOMOO, asset_class="equity") -> PortfolioHolding:
    return PortfolioHolding(
        venue=venue, symbol=symbol, asset_class=asset_class, weight=0.0
    )


def _aa_bb(asset_class="equity") -> list[PortfolioHolding]:
    return [_holding("AAA", Venue.MOOMOO, asset_class), _holding("BBB", Venue.MOOMOO, asset_class)]


class TestRiskBudget:
    def test_uncorrelated_two_asset_closed_form(self) -> None:
        """diag(4, 1): parity weights are inverse-vol (1/3, 2/3) with
        equal risk contributions 4/9 — the solver must reach the
        closed form from the equal-weight start."""
        result = risk_budget_weights(
            covariance=np.diag([4.0, 1.0]), holdings=_aa_bb(), initial="equal"
        )
        assert result.weights["moomoo:AAA"] == pytest.approx(1 / 3, abs=1e-3)
        assert result.weights["moomoo:BBB"] == pytest.approx(2 / 3, abs=1e-3)
        assert result.risk_contributions["moomoo:AAA"] == pytest.approx(
            4 / 9, abs=1e-4
        )
        assert result.risk_contributions["moomoo:BBB"] == pytest.approx(
            4 / 9, abs=1e-4
        )
        assert result.objective < 1e-8
        assert sum(result.weights.values()) == pytest.approx(1.0, abs=1e-5)

    def test_correlated_two_asset_parity(self) -> None:
        """[[4, 1.5], [1.5, 1]]: parity is still inverse-vol (1/3, 2/3)
        (correlation cancels for two assets) with RC 7/9 each."""
        result = risk_budget_weights(
            covariance=np.array([[4.0, 1.5], [1.5, 1.0]]),
            holdings=_aa_bb(),
            initial="equal",
        )
        assert result.weights["moomoo:AAA"] == pytest.approx(1 / 3, abs=1e-3)
        assert result.weights["moomoo:BBB"] == pytest.approx(2 / 3, abs=1e-3)
        assert result.risk_contributions["moomoo:AAA"] == pytest.approx(
            7 / 9, abs=1e-4
        )
        assert result.risk_contributions["moomoo:BBB"] == pytest.approx(
            7 / 9, abs=1e-4
        )

    def test_default_inverse_vol_start_matches(self) -> None:
        """The documented starting point is the parity prior: the same
        optimum from either start."""
        via_inverse_vol = risk_budget_weights(
            covariance=np.diag([4.0, 1.0]), holdings=_aa_bb()
        )
        via_equal = risk_budget_weights(
            covariance=np.diag([4.0, 1.0]), holdings=_aa_bb(), initial="equal"
        )
        assert via_inverse_vol.weights == via_equal.weights

    def test_determinism(self) -> None:
        first = risk_budget_weights(covariance=np.diag([4.0, 1.0]), holdings=_aa_bb())
        second = risk_budget_weights(covariance=np.diag([4.0, 1.0]), holdings=_aa_bb())
        assert first.weights == second.weights
        assert first.objective == second.objective
        assert first.iterations == second.iterations


class TestBindingConstraints:
    def test_venue_cap_binds(self) -> None:
        """Unconstrained w_AAA = 1/3; a 0.25 cap on moomoo pins it at
        the boundary (BBB on a second, uncapped venue keeps the surface
        feasible)."""
        result = risk_budget_weights(
            covariance=np.diag([4.0, 1.0]),
            holdings=[
                _holding("AAA", Venue.MOOMOO),
                _holding("BBB", Venue.HYPERLIQUID),
            ],
            constraints=PortfolioConstraints(
                venue_caps=[VenueCap(venue=Venue.MOOMOO, max_fraction=0.25)]
            ),
        )
        assert result.weights["moomoo:AAA"] == pytest.approx(0.25, abs=1e-3)
        venue = next(value for value in result.checks if value.label == "venue:moomoo")
        assert venue.observed == pytest.approx(0.25, abs=1e-6)
        assert venue.observed <= venue.limit + 1e-6
        assert sum(result.weights.values()) == pytest.approx(1.0, abs=1e-5)

    def test_asset_class_cap_binds(self) -> None:
        holdings = [
            _holding("AAA", Venue.MOOMOO, "equity"),
            _holding("BBB", Venue.HYPERLIQUID, "equity"),
            _holding("CCC", Venue.KALSHI, "crypto"),
        ]
        result = risk_budget_weights(
            covariance=np.diag([4.0, 1.0, 1.0]),
            holdings=holdings,
            constraints=PortfolioConstraints(
                asset_class_caps=[AssetClassCap(asset_class="equity", max_fraction=0.5)]
            ),
        )
        by_class = next(
            value for value in result.checks if value.label == "class:equity"
        )
        assert by_class.observed == pytest.approx(0.5, abs=1e-6)
        assert by_class.observed <= by_class.limit + 1e-6
        assert result.weights["moomoo:AAA"] + result.weights["hyperliquid:BBB"] == (
            pytest.approx(0.5, abs=1e-5)
        )

    def test_event_risk_cap_binds(self) -> None:
        """A 0.15 risk cap on a 0.5-probability event holding caps its
        weight at 0.3."""
        holdings = [
            _holding("AAA", Venue.POLYMARKET, "event").model_copy(
                update={"event_key": "FED-SEP", "held_probability": 0.5}
            ),
            _holding("BBB", Venue.MOOMOO, "equity"),
        ]
        result = risk_budget_weights(
            covariance=np.diag([4.0, 1.0]),
            holdings=holdings,
            constraints=PortfolioConstraints(
                event_risk_caps=[EventRiskCap(max_fraction=0.15)]
            ),
        )
        event_risk = next(
            value for value in result.checks if value.label.startswith("event-risk")
        )
        assert event_risk.observed == pytest.approx(0.15, abs=1e-6)
        assert event_risk.observed <= event_risk.limit + 1e-6
        assert result.weights["polymarket:AAA"] == pytest.approx(0.3, abs=1e-3)

    def test_leverage_cap_binds(self) -> None:
        result = risk_budget_weights(
            covariance=np.diag([4.0, 1.0]),
            holdings=[
                _holding("AAA", Venue.MOOMOO),
                _holding("BBB", Venue.HYPERLIQUID),
            ],
            constraints=PortfolioConstraints(
                leverage_caps=[LeverageCap(venue=Venue.MOOMOO, max_leverage=0.25)]
            ),
        )
        leverage = next(
            value for value in result.checks if value.label == "leverage:moomoo"
        )
        assert leverage.observed == pytest.approx(0.25, abs=1e-6)
        assert leverage.observed <= leverage.limit + 1e-6
        assert result.weights["moomoo:AAA"] == pytest.approx(0.25, abs=1e-3)

    def test_checks_remeasure_the_returned_weights(self) -> None:
        """The returned checks re-measure the ROUNDED weights the
        caller receives, so the report never disagrees with them."""
        constraints = PortfolioConstraints(
            venue_caps=[VenueCap(venue=Venue.MOOMOO, max_fraction=0.25)]
        )
        result = risk_budget_weights(
            covariance=np.diag([4.0, 1.0]),
            holdings=[
                _holding("AAA", Venue.MOOMOO),
                _holding("BBB", Venue.HYPERLIQUID),
            ],
            constraints=constraints,
        )
        venue = next(value for value in result.checks if value.label == "venue:moomoo")
        assert venue.observed == pytest.approx(result.weights["moomoo:AAA"], abs=1e-9)
        assert not venue.is_violated()


class TestRefusals:
    def test_structural_infeasibility(self) -> None:
        with pytest.raises(OptimizationFailure, match="structural infeasibility"):
            risk_budget_weights(
                covariance=np.diag([4.0, 1.0]),
                holdings=_aa_bb(),
                constraints=PortfolioConstraints(
                    venue_caps=[
                        VenueCap(venue=Venue.MOOMOO, max_fraction=0.5),
                        VenueCap(venue=Venue.HYPERLIQUID, max_fraction=0.4),
                    ]
                ),
            )

    def test_covariance_validation(self) -> None:
        covariance = np.diag([4.0, 1.0])
        holdings = _aa_bb()
        with pytest.raises(OptimizationFailure, match="2-D matrix"):
            risk_budget_weights(covariance=np.array([1.0, 1.0]), holdings=holdings)
        with pytest.raises(OptimizationFailure, match="does not match the 2-holding universe"):
            risk_budget_weights(covariance=np.eye(3), holdings=holdings)
        with pytest.raises(OptimizationFailure, match="non-finite"):
            bad = covariance.copy()
            bad[0, 1] = np.nan
            risk_budget_weights(covariance=bad, holdings=holdings)
        with pytest.raises(OptimizationFailure, match="not symmetric"):
            risk_budget_weights(covariance=np.array([[1.0, 0.1], [0.0, 1.0]]), holdings=holdings)
        with pytest.raises(OptimizationFailure, match="not positive semi-definite"):
            risk_budget_weights(covariance=np.array([[1.0, 2.0], [2.0, 1.0]]), holdings=holdings)

    def test_zero_variance_refused_for_inverse_vol_start(self) -> None:
        with pytest.raises(OptimizationFailure, match="strictly positive variances"):
            risk_budget_weights(covariance=np.diag([4.0, 0.0]), holdings=_aa_bb())

    def test_universe_size_and_uniqueness(self) -> None:
        with pytest.raises(OptimizationFailure, match="at least 2 holdings"):
            risk_budget_weights(
                covariance=np.array([[1.0]]), holdings=[_holding("AAA")]
            )
        with pytest.raises(OptimizationFailure, match="at least 2 holdings"):
            risk_budget_weights(covariance=np.empty((0, 0)), holdings=[])
        with pytest.raises(OptimizationFailure, match="duplicate holdings"):
            risk_budget_weights(
                covariance=np.diag([4.0, 1.0]),
                holdings=[_holding("AAA"), _holding("AAA")],
            )

    def test_unknown_starting_point(self) -> None:
        with pytest.raises(OptimizationFailure, match="unknown starting point"):
            risk_budget_weights(
                covariance=np.diag([4.0, 1.0]), holdings=_aa_bb(), initial="random"
            )

    def test_scipy_missing_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _MissingScipy:
            def import_module(self, name: str):
                raise ImportError(f"No module named {name!r}")

        monkeypatch.setattr(optimizer_module, "importlib", _MissingScipy())
        with pytest.raises(PipelineUnavailableError, match="scipy is not installed"):
            risk_budget_weights(covariance=np.diag([4.0, 1.0]), holdings=_aa_bb())
