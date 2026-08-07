"""Canonical event-market models (M6, issue #34, Phase A).

Venue-neutral contracts that the Polymarket and Kalshi adapters
normalize into, so consumers (calibration, forecast reports, cross-
platform mapping) never see a vendor schema:

- ``EventVenue`` — the closed set of venues that speak "events":
  POLYMARKET and KALSHI. Mapped into the domain ``Venue`` for the M3
  provider/lake surface by ``to_domain_venue()``, which fails closed on
  anything outside the pair (an event market cannot be a Moomoo equity).
- ``EventMarket`` — one tradeable market on one venue (Polymarket:
  a condition id with its token pair; Kalshi: a market ticker), carrying
  its outcomes, expiry, resolution rule (text + normalized fingerprint)
  and resolution state. ``resolution`` is a *list* of resolved outcome
  names: empty means unresolved, one name is a binary resolution, and
  multiple names are a real Polymarket 50/50-style split — never
  flattened into a string.
- ``MarketQuote`` — one depth snapshot of one token: best bid/ask
  (``None`` when a side is empty), depth, tick size, minimum order size
  and the venue's reported fee rate. Prices are constrained to [0, 1]
  because every event contract pays 0 or 1 units; anything outside
  fails closed at validation.
- ``ImpliedProbability`` — the Phase C contract: probability with its
  spread adjustment, liquidity confidence and basis. The model is
  pinned here; Phase C computes the values.
"""

import hashlib
import re
import unicodedata
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

from quantmesh.domain.models import Venue


class EventVenue(StrEnum):
    """Closed set of event venues the canonical models speak."""

    POLYMARKET = "polymarket"
    KALSHI = "kalshi"

    def to_domain_venue(self) -> Venue:
        """Map into the domain ``Venue`` for the M3 surface; closed set."""
        try:
            return _DOMAIN_VENUE_BY_EVENT[self]
        except KeyError as error:
            raise ValueError(f"event venue {self.value!r} has no domain venue") from error


_DOMAIN_VENUE_BY_EVENT = {
    EventVenue.POLYMARKET: Venue.POLYMARKET,
    EventVenue.KALSHI: Venue.KALSHI,
}


def _require_aware(value: datetime | None, name: str) -> None:
    if value is not None and value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _normalize_rule_text(text: str) -> str:
    """Canonical form for resolution-rule fingerprints.

    NFKC normalization, case folding and whitespace collapsing — two
    venues stating the same rule with different casing or wrapping
    produce the same fingerprint, while any substantive wording change
    produces a different one.
    """
    folded = unicodedata.normalize("NFKC", text).casefold()
    return re.sub(r"\s+", " ", folded).strip()


class ResolutionRule(BaseModel):
    """Canonical rule text plus a normalized fingerprint (issue #34)."""

    rule_text: str = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def fingerprint_matches_text(self) -> "ResolutionRule":
        expected = hashlib.sha256(
            _normalize_rule_text(self.rule_text).encode("utf-8")
        ).hexdigest()
        if self.fingerprint != expected:
            raise ValueError("fingerprint does not match the normalized rule text")
        return self

    @classmethod
    def of(cls, rule_text: str) -> "ResolutionRule":
        """Build with the fingerprint computed from the text (setup-only)."""
        fingerprint = hashlib.sha256(
            _normalize_rule_text(rule_text).encode("utf-8")
        ).hexdigest()
        return cls(rule_text=rule_text, fingerprint=fingerprint)


class Outcome(BaseModel):
    """One possible resolution of an event market.

    ``venue_outcome_id`` is the venue's own identifier for the outcome
    (Polymarket: the CLOB token id; Kalshi: the outcome identifier) —
    the id that quotes and trades reference.
    """

    name: str = Field(min_length=1)
    venue_outcome_id: str = Field(min_length=1)


class EventMarket(BaseModel):
    """One tradeable market on one event venue (issue #34)."""

    venue: EventVenue
    venue_market_id: str = Field(min_length=1)  # Polymarket condition id, Kalshi market ticker
    event_ticker: str = Field(min_length=1)  # Polymarket Gamma slug, Kalshi event ticker
    title: str = Field(min_length=1)  # the question
    category: str | None = None
    start_at: datetime | None = None
    expiry_at: datetime | None = None
    outcomes: list[Outcome] = Field(min_length=1)
    resolution_rule: ResolutionRule
    # Resolved outcome names; empty = unresolved. A multi-name list is a
    # genuine split resolution (e.g. Polymarket 50/50) — never collapsed.
    resolution: list[str] = Field(default_factory=list)
    resolved_at: datetime | None = None

    @model_validator(mode="after")
    def times_are_aware(self) -> "EventMarket":
        for name, value in (
            ("start_at", self.start_at),
            ("expiry_at", self.expiry_at),
            ("resolved_at", self.resolved_at),
        ):
            _require_aware(value, name)
        return self

    @model_validator(mode="after")
    def outcome_names_are_unique(self) -> "EventMarket":
        names = [outcome.name for outcome in self.outcomes]
        if len(names) != len(set(names)):
            raise ValueError(f"outcome names are not unique: {names}")
        return self

    @model_validator(mode="after")
    def resolution_names_exist(self) -> "EventMarket":
        known = {outcome.name for outcome in self.outcomes}
        unknown = [name for name in self.resolution if name not in known]
        if unknown:
            raise ValueError(f"resolution names are not outcomes: {unknown}")
        return self

    def outcome_id(self, name: str) -> str | None:
        """The venue outcome id for ``name``, or None when absent."""
        for outcome in self.outcomes:
            if outcome.name == name:
                return outcome.venue_outcome_id
        return None


class MarketQuote(BaseModel):
    """One depth snapshot of one event token (issue #34)."""

    venue: EventVenue
    symbol: str = Field(min_length=1)  # Polymarket token id, Kalshi market ticker
    timestamp: datetime
    best_bid: float | None = Field(default=None, ge=0, le=1)
    best_ask: float | None = Field(default=None, ge=0, le=1)
    last_trade_price: float | None = Field(default=None, ge=0, le=1)
    bid_depth: float = Field(default=0.0, ge=0)
    ask_depth: float = Field(default=0.0, ge=0)
    tick_size: float = Field(gt=0)
    min_order_size: float | None = Field(default=None, ge=0)
    # Fee rate as reported by the venue's own contract (Polymarket:
    # ``taker_base_fee`` in bps). Interpretation (what the fee applies
    # to) is the Phase C fee-structure decision, not this model's.
    taker_fee_bps: float = Field(default=0.0, ge=0)

    @model_validator(mode="after")
    def timestamp_is_aware(self) -> "MarketQuote":
        _require_aware(self.timestamp, "timestamp")
        return self


class ImpliedProbability(BaseModel):
    """A fee/spread/liquidity-aware probability estimate (Phase C computes)."""

    probability: float = Field(ge=0, le=1)
    # Signed probability-point adjustment from the raw market mid:
    # positive means the estimate is above the raw mid.
    spread_adjustment: float
    liquidity_confidence: float = Field(ge=0, le=1)
    basis: str = Field(min_length=1)  # what produced the estimate
    timestamp: datetime

    @model_validator(mode="after")
    def timestamp_is_aware(self) -> "ImpliedProbability":
        _require_aware(self.timestamp, "timestamp")
        return self
