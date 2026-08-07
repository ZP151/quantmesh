"""Portfolio constraint surface (M7 Phase D, issue #42).

Four constraint classes, each a deterministic cap on a portfolio
property evaluated against the target weight vector (weights are
fractions of equity, so the numbers compare directly to the caps):

- per-venue caps (``VenueCap``) — max equity fraction of gross
  exposure on one venue;
- asset-class caps (``AssetClassCap``) — max equity fraction per
  declared asset class;
- event-risk caps (``EventRiskCap``) — max risk-weighted event
  exposure, ``weight x (1 - implied probability of the held side)``
  summed over event-keyed holdings, computed from the M6 implied
  probabilities;
- per-venue leverage limits (``LeverageCap``) — max gross exposure /
  equity per venue, drawn from the M5 pre-submission check
  (``hyperliquid.risk.RiskLimits.max_leverage``, issue #31) via
  ``leverage_cap_from_risk_limits``.

A constraint check is a pure evaluation: observed vs limit, and
``checks().violations()`` is the M5 RiskRefusal idiom — typed
refusals with observed/expected values. Infeasible weight vectors are
the optimizer's business; here every value is simply measured.
"""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from quantmesh.domain.models import Venue
from quantmesh.hyperliquid.risk import RiskLimits
from quantmesh.portfolio.exposure import PortfolioHolding, holding_key

# Tolerance for comparing observed exposure against a cap: weights are
# rounded to 6 dp, so a violation means observed > limit + 1e-9.
TOLERANCE = 1e-9


class ConstraintKind(StrEnum):
    VENUE = "venue"
    ASSET_CLASS = "asset_class"
    EVENT_RISK = "event_risk"
    LEVERAGE = "leverage"


class VenueCap(BaseModel):
    """Max fraction of equity gross exposure on one venue."""

    venue: Venue
    max_fraction: float = Field(gt=0, le=1)


class AssetClassCap(BaseModel):
    """Max fraction of equity gross exposure in one asset class."""

    asset_class: str = Field(min_length=1)
    max_fraction: float = Field(gt=0, le=1)


class EventRiskCap(BaseModel):
    """Cap on risk-weighted event exposure: sum over event-keyed
    holdings of ``weight x (1 - implied probability of the held side)``
    (the M6 implied probability), i.e. the expected loss if the other
    side resolves. A position on a 0.05-probability outcome counts
    0.95 of its weight; a near-certain position counts almost nothing.
    """

    max_fraction: float = Field(gt=0, le=1)


class LeverageCap(BaseModel):
    """Max gross exposure / equity on one venue. The M5 check bounds
    one order's resulting position (issue #31); this is the portfolio-
    level per-venue version of the same limit."""

    venue: Venue
    max_leverage: float = Field(gt=0)


def leverage_cap_from_risk_limits(venue: Venue, limits: RiskLimits) -> LeverageCap:
    """Portfolio-level per-venue leverage drawn from the M5
    pre-submission ``RiskLimits`` — the linkage the plan demands
    ("per-venue leverage limits drawn from the M5 risk checks")."""
    return LeverageCap(venue=venue, max_leverage=limits.max_leverage)


class PortfolioConstraints(BaseModel):
    """The full constraint surface; empty lists mean "no constraint of
    that class"."""

    venue_caps: list[VenueCap] = Field(default_factory=list)
    asset_class_caps: list[AssetClassCap] = Field(default_factory=list)
    event_risk_caps: list[EventRiskCap] = Field(default_factory=list)
    leverage_caps: list[LeverageCap] = Field(default_factory=list)

    @model_validator(mode="after")
    def caps_are_unique(self) -> "PortfolioConstraints":
        venues = [cap.venue for cap in self.venue_caps]
        if len(set(venues)) != len(venues):
            raise ValueError(f"duplicate venue caps: {venues}")
        classes = [cap.asset_class for cap in self.asset_class_caps]
        if len(set(classes)) != len(classes):
            raise ValueError(f"duplicate asset-class caps: {classes}")
        leveraged = [cap.venue for cap in self.leverage_caps]
        if len(set(leveraged)) != len(leveraged):
            raise ValueError(f"duplicate leverage caps: {leveraged}")
        return self

    def is_empty(self) -> bool:
        return not (
            self.venue_caps
            or self.asset_class_caps
            or self.event_risk_caps
            or self.leverage_caps
        )


class ConstraintValue(BaseModel):
    """One measured constraint: observed exposure vs the limit."""

    kind: ConstraintKind
    label: str  # "venue:moomoo", "class:equity", "event-risk", "leverage:hyperliquid"
    observed: float
    limit: float

    def is_violated(self) -> bool:
        return self.observed > self.limit + TOLERANCE


class ConstraintChecks(BaseModel):
    """All constraint values measured on one weight vector; allowed
    only with zero violations."""

    values: list[ConstraintValue] = Field(default_factory=list)

    def violations(self) -> list[ConstraintValue]:
        return [value for value in self.values if value.is_violated()]

    def allowed(self) -> bool:
        return not self.violations()


def constraint_values(
    holdings: list[PortfolioHolding], constraints: PortfolioConstraints
) -> list[ConstraintValue]:
    """Evaluate every constraint against the holdings' target weights.

    Pure arithmetic over the weights — no ordering, no state. Event
    holdings without an implied probability were refused at holding
    construction, so ``1 - held_probability`` is always defined here.
    """
    values: list[ConstraintValue] = []
    by_venue: dict[Venue, float] = {}
    by_class: dict[str, float] = {}
    by_event: dict[str, float] = {}
    event_risk = 0.0
    for holding in holdings:
        weight = holding.weight
        by_venue[holding.venue] = by_venue.get(holding.venue, 0.0) + weight
        if holding.asset_class is not None:
            by_class[holding.asset_class] = by_class.get(holding.asset_class, 0.0) + weight
        if holding.event_key is not None:
            by_event[holding.event_key] = by_event.get(holding.event_key, 0.0) + weight
            event_risk += weight * (1.0 - holding.held_probability)
    for cap in constraints.venue_caps:
        values.append(
            ConstraintValue(
                kind=ConstraintKind.VENUE,
                label=f"venue:{cap.venue.value}",
                observed=by_venue.get(cap.venue, 0.0),
                limit=cap.max_fraction,
            )
        )
    for cap in constraints.asset_class_caps:
        values.append(
            ConstraintValue(
                kind=ConstraintKind.ASSET_CLASS,
                label=f"class:{cap.asset_class}",
                observed=by_class.get(cap.asset_class, 0.0),
                limit=cap.max_fraction,
            )
        )
    for index, cap in enumerate(constraints.event_risk_caps):
        values.append(
            ConstraintValue(
                kind=ConstraintKind.EVENT_RISK,
                label=f"event-risk:{index}",
                observed=event_risk,
                limit=cap.max_fraction,
            )
        )
    for cap in constraints.leverage_caps:
        values.append(
            ConstraintValue(
                kind=ConstraintKind.LEVERAGE,
                label=f"leverage:{cap.venue.value}",
                observed=by_venue.get(cap.venue, 0.0),
                limit=cap.max_leverage,
            )
        )
    return values


def check_constraints(
    holdings: list[PortfolioHolding], constraints: PortfolioConstraints
) -> ConstraintChecks:
    """One typed verdict over the whole surface (M5 RiskDecision
    idiom: allowed only with zero refusals)."""
    values = constraint_values(holdings, constraints)
    keys = {holding_key(holding) for holding in holdings}
    if len(keys) != len(holdings):
        raise ValueError(f"duplicate holdings in the portfolio: {len(holdings)} vs {len(keys)}")
    return ConstraintChecks(values=values)
