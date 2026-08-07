"""Portfolio holdings and exposure decomposition (M7 Phase D, #42).

A holding is a target weight (fraction of equity) on one symbol plus
the labels the constraint surface and reports key on: asset class, and
for event markets (M6) the event key and the implied probability of
the held side. Exposure decomposes by venue, asset class and event;
event risk is the probability-weighted downside
(``weight x (1 - held_probability)``).
"""

from pydantic import BaseModel, Field, model_validator

from quantmesh.domain.models import Venue


class PortfolioHolding(BaseModel):
    """One target position: setup (what the portfolio intends to hold),
    never a result. Weights are fractions of equity and sum to 1 for a
    fully invested portfolio."""

    venue: Venue
    symbol: str = Field(min_length=1)
    asset_class: str | None = None
    # M6 event aggregate the market belongs to (Polymarket question /
    # Kalshi series identity); event-keyed holdings carry the implied
    # probability of the held side and vice versa.
    event_key: str | None = None
    held_probability: float | None = Field(default=None, ge=0, le=1)
    weight: float = Field(ge=0)

    @model_validator(mode="after")
    def probability_and_event_are_paired(self) -> "PortfolioHolding":
        if self.event_key is None and self.held_probability is not None:
            raise ValueError(
                f"holding {self.venue.value}:{self.symbol!r} carries an implied "
                "probability without an event key — only event-keyed holdings "
                "have a held side (M6)"
            )
        if self.event_key is not None and self.held_probability is None:
            raise ValueError(
                f"event holding {self.event_key!r} is missing the implied "
                "probability of the held side (M6) — event risk cannot be "
                "measured without it"
            )
        return self


def holding_key(holding: PortfolioHolding) -> str:
    return f"{holding.venue.value}:{holding.symbol}"


class ExposureDecomposition(BaseModel):
    """The portfolio's exposure split by venue, asset class and event,
    plus the risk-weighted event exposure."""

    total: float = Field(ge=0)
    by_venue: dict[str, float]  # venue.value -> sum of weights
    by_asset_class: dict[str, float]
    by_event: dict[str, float]  # event key -> sum of weights
    event_risk: float = Field(ge=0)  # sum of weight x (1 - held_probability)

    def venue_exposure(self, venue: Venue) -> float:
        return self.by_venue.get(venue.value, 0.0)


def decompose_exposure(holdings: list[PortfolioHolding]) -> ExposureDecomposition:
    """Deterministic exposure arithmetic over the holdings' weights."""
    by_venue: dict[str, float] = {}
    by_class: dict[str, float] = {}
    by_event: dict[str, float] = {}
    event_risk = 0.0
    total = 0.0
    for holding in holdings:
        weight = holding.weight
        total += weight
        by_venue[holding.venue.value] = by_venue.get(holding.venue.value, 0.0) + weight
        if holding.asset_class is not None:
            by_class[holding.asset_class] = by_class.get(holding.asset_class, 0.0) + weight
        if holding.event_key is not None:
            by_event[holding.event_key] = by_event.get(holding.event_key, 0.0) + weight
            event_risk += weight * (1.0 - holding.held_probability)
    return ExposureDecomposition(
        total=total,
        by_venue=by_venue,
        by_asset_class=by_class,
        by_event=by_event,
        event_risk=event_risk,
    )
