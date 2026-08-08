"""Risk-budget portfolio construction (M7 Phase D, issue #42).

``risk_budget_weights`` solves for the weight vector whose risk
contributions are as equal as the constraint surface allows: minimize
the squared deviation of each asset's risk contribution
``w_k (Sigma w)_k`` from its budget ``risk_total / n`` (equal budgets,
the classic risk-parity objective) via scipy SLSQP, subject to

- full investment: ``sum(w) == 1``;
- long-only box: ``0 <= w <= 1``;
- the constraint surface (``constraints.py``) as linear inequalities:
  per-venue caps, asset-class caps, risk-weighted event-exposure caps
  (M6 implied probabilities), and per-venue leverage limits (M5
  ``RiskLimits``) — every cap is a linear form in the weights.

Determinism and fail-closed discipline:

- No RNG anywhere; SLSQP is deterministic for fixed inputs.
- The starting point is documented: inverse-volatility weights
  normalized to unit sum (the risk-parity prior), or equal weight on
  request — never a random seed.
- Structural infeasibility is refused before solving: the per-venue
  caps partition the universe, so venue caps summing below 1 admit no
  weight vector at all. Covariance inputs are validated (square,
  finite, symmetric, positive semi-definite) and non-finite inputs are
  refused everywhere.
- Every solve is re-verified after the fact: solver failure, a
  non-finite objective or weights, a violated equality/box/linear
  constraint (beyond tolerance) all fail closed with the solver's
  message attached. scipy loads lazily and raises
  ``PipelineUnavailableError`` when the research extra is missing.
"""

import importlib
import math

import numpy as np
from pydantic import BaseModel

from quantmesh.portfolio.constraints import (
    ConstraintValue,
    PortfolioConstraints,
    constraint_values,
)
from quantmesh.portfolio.exposure import PortfolioHolding, holding_key
from quantmesh.research.pipelines import PipelineUnavailableError

# Equality and box re-verification tolerance: weights are rounded to 6
# dp after the solve, so feasibility tolerances stay well below that.
FEASIBILITY_TOLERANCE = 1e-6
WEIGHT_ROUNDING = 6


def _require_scipy():
    try:
        return importlib.import_module("scipy")
    except ImportError as error:
        raise PipelineUnavailableError(
            "scipy is not installed; install quantmesh[research] to run the "
            "risk-budget optimizer"
        ) from error


class OptimizationFailure(ValueError):
    """Typed fail-closed verdict: the solver or its verification refused."""


class OptimizationResult(BaseModel):
    """The verified optimum: weights, per-asset risk contributions, the
    objective value, solver iterations and the post-solve constraint
    re-verification."""

    weights: dict[str, float]
    risk_contributions: dict[str, float]
    objective: float
    iterations: int
    checks: list[ConstraintValue]


def _validate_covariance(covariance: np.ndarray, n_holdings: int) -> np.ndarray:
    if covariance.ndim != 2:
        raise OptimizationFailure(
            f"covariance must be a 2-D matrix, got {covariance.ndim}-D"
        )
    if covariance.shape != (n_holdings, n_holdings):
        raise OptimizationFailure(
            f"covariance shape {covariance.shape} does not match the "
            f"{n_holdings}-holding universe"
        )
    if not np.isfinite(covariance).all():
        raise OptimizationFailure("covariance contains non-finite entries")
    asymmetry = np.abs(covariance - covariance.T).max()
    if asymmetry > 1e-9:
        raise OptimizationFailure(f"covariance is not symmetric (max |A - A^T| {asymmetry:.2e})")
    eigenvalues = np.linalg.eigvalsh(covariance)
    if eigenvalues.min() < -1e-9:
        raise OptimizationFailure(
            f"covariance is not positive semi-definite (min eigenvalue {eigenvalues.min():.2e})"
        )
    return covariance


def _starting_weights(
    covariance: np.ndarray, mode: str
) -> np.ndarray:
    diagonal = np.diag(covariance)
    if mode == "equal":
        return np.full(len(diagonal), 1.0 / len(diagonal))
    if mode != "inverse_vol":
        raise OptimizationFailure(
            f"unknown starting point {mode!r} (choose 'inverse_vol' or 'equal')"
        )
    if (diagonal <= 0).any():
        raise OptimizationFailure(
            "inverse-volatility starting point needs strictly positive "
            "variances; a zero-variance holding has no defined risk budget"
        )
    weights = 1.0 / np.sqrt(diagonal)
    return weights / weights.sum()


def _constraint_rows(
    holdings: list[PortfolioHolding],
    constraints: PortfolioConstraints,
    n: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Compile the constraint surface into rows A w <= b.

    Each cap is a linear form in the weights: venue caps sum the
    venue's weights, asset-class caps sum the class's weights, event
    risk sums ``weight x (1 - held_probability)`` per event holding
    (0 for non-event holdings), leverage caps sum the venue's weights.
    """
    rows: list[list[float]] = []
    bounds: list[float] = []
    for cap in constraints.venue_caps:
        row = [1.0 if holding.venue is cap.venue else 0.0 for holding in holdings]
        rows.append(row)
        bounds.append(cap.max_fraction)
    for cap in constraints.asset_class_caps:
        row = [
            1.0 if holding.asset_class == cap.asset_class else 0.0 for holding in holdings
        ]
        rows.append(row)
        bounds.append(cap.max_fraction)
    for cap in constraints.event_risk_caps:
        row = [
            (1.0 - holding.held_probability) if holding.event_key is not None else 0.0
            for holding in holdings
        ]
        rows.append(row)
        bounds.append(cap.max_fraction)
    for cap in constraints.leverage_caps:
        row = [1.0 if holding.venue is cap.venue else 0.0 for holding in holdings]
        rows.append(row)
        bounds.append(cap.max_leverage)
    if not rows:
        return np.empty((0, n)), np.empty(0)
    return np.asarray(rows, dtype=float), np.asarray(bounds, dtype=float)


def _verify(
    weights: np.ndarray,
    covariance: np.ndarray,
    checks: list[ConstraintValue],
    objective: float,
    iterations: int,
    keys: list[str],
    holdings: list[PortfolioHolding],
    constraints: PortfolioConstraints,
) -> OptimizationResult:
    """Post-solve re-verification: anything out of tolerance fails
    closed instead of shipping an infeasible "optimum". The refusal
    tests the solver's (unrounded) point with the feasibility
    tolerance; the returned checks re-measure the ROUNDED weights the
    caller actually receives, so the report and the weights never
    disagree."""
    if not math.isfinite(objective) or not np.isfinite(weights).all():
        raise OptimizationFailure("solver returned non-finite weights or objective")
    if abs(weights.sum() - 1.0) > FEASIBILITY_TOLERANCE:
        raise OptimizationFailure(
            f"solver returned weights summing to {weights.sum():.8f}, not 1"
        )
    if (weights < -FEASIBILITY_TOLERANCE).any():
        raise OptimizationFailure("solver returned negative weights (long-only box)")
    if (weights > 1.0 + FEASIBILITY_TOLERANCE).any():
        raise OptimizationFailure("solver returned weights above 1 (long-only box)")
    solved_holdings = [
        holding.model_copy(update={"weight": float(weight)})
        for holding, weight in zip(holdings, weights)
    ]
    for check in constraint_values(solved_holdings, constraints):
        if check.observed > check.limit + FEASIBILITY_TOLERANCE:
            raise OptimizationFailure(
                f"constraint {check.label} violated after optimization: "
                f"{check.observed:.6f} > {check.limit:.6f}"
            )
    rounded = np.round(weights, WEIGHT_ROUNDING)
    risk_contributions = {
        key: float(rounded[index] * (covariance @ rounded)[index])
        for index, key in enumerate(keys)
    }
    rounded_holdings = [
        holding.model_copy(update={"weight": float(weight)})
        for holding, weight in zip(holdings, rounded)
    ]
    return OptimizationResult(
        weights={key: float(weight) for key, weight in zip(keys, rounded)},
        risk_contributions=risk_contributions,
        objective=float(objective),
        iterations=int(iterations),
        checks=constraint_values(rounded_holdings, constraints),
    )


def risk_budget_weights(
    *,
    covariance: np.ndarray,
    holdings: list[PortfolioHolding],
    constraints: PortfolioConstraints | None = None,
    initial: str = "inverse_vol",
) -> OptimizationResult:
    """Solve the equal-risk-budget portfolio under the constraint
    surface. ``covariance`` is the n x n return covariance of the
    holdings in list order (a research-side input, never computed
    here); ``initial`` chooses the documented starting point."""
    scipy = _require_scipy()
    constraints = constraints if constraints is not None else PortfolioConstraints()
    n_holdings = len(holdings)
    if n_holdings < 2:
        raise OptimizationFailure(
            f"risk budgeting needs at least 2 holdings, got {n_holdings}"
        )
    keys = [holding_key(holding) for holding in holdings]
    if len(set(keys)) != n_holdings:
        raise OptimizationFailure(f"duplicate holdings in the universe: {keys}")
    covariance = _validate_covariance(covariance, n_holdings)
    start = _starting_weights(covariance, initial)

    # Structural infeasibility: when the venue caps cover every venue
    # in the universe they partition it, so caps summing below 1 admit
    # no weight vector at all. An empty or partial surface has no such
    # partition argument (uncapped venues absorb the remaining weight).
    capped_venues = {cap.venue for cap in constraints.venue_caps}
    uncapped_venues = {holding.venue for holding in holdings} - capped_venues
    venue_sum = sum(cap.max_fraction for cap in constraints.venue_caps)
    if not uncapped_venues and venue_sum < 1.0 - FEASIBILITY_TOLERANCE:
        raise OptimizationFailure(
            f"the per-venue caps sum to {venue_sum:.4f} < 1; no weight vector "
            "can satisfy them (structural infeasibility)"
        )

    matrix, bounds = _constraint_rows(holdings, constraints, n_holdings)

    def objective(weights: np.ndarray) -> float:
        portfolio_variance = float(weights @ covariance @ weights)
        if portfolio_variance <= 0.0:
            return float("inf")
        budget = portfolio_variance / n_holdings
        risk_contributions = weights * (covariance @ weights)
        return float(np.sum((risk_contributions - budget) ** 2))

    def jacobian(weights: np.ndarray) -> np.ndarray:
        # d/dw_k sum_j (RC_j - b)^2 with RC = w * (Sigma w), b = (w^T Sigma w)/n:
        #   dRC_j/dw_k = delta_jk (Sigma w)_j + w_j Sigma_jk
        #   db/dw_k    = 2 (Sigma w)_k / n
        sigma_w = covariance @ weights
        portfolio_variance = float(weights @ sigma_w)
        gradient = np.zeros(n_holdings)
        for index in range(n_holdings):
            deviation_sum = 0.0
            for j in range(n_holdings):
                rc = weights[j] * sigma_w[j]
                budget = portfolio_variance / n_holdings
                d_rc = sigma_w[index] if j == index else 0.0
                d_rc += weights[j] * covariance[j, index]
                d_budget = 2.0 * sigma_w[index] / n_holdings
                deviation_sum += (rc - budget) * (d_rc - d_budget)
            gradient[index] = 2.0 * deviation_sum
        return gradient

    linear = [
        {"type": "ineq", "fun": lambda w, row=row, bound=bound: bound - float(row @ w)}
        for row, bound in zip(matrix, bounds)
    ]
    result = scipy.optimize.minimize(
        objective,
        start,
        jac=jacobian,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n_holdings,
        constraints=[{"type": "eq", "fun": lambda w: float(w.sum()) - 1.0}] + linear,
        options={"ftol": 1e-10, "maxiter": 500},
    )
    if not result.success:
        raise OptimizationFailure(
            f"scipy SLSQP did not converge: {result.message}"
        )

    return _verify(
        result.x, covariance, [], result.fun, result.nit, keys, holdings, constraints
    )
