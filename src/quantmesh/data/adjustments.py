"""Explicit adjustment policies for trusted-data publications."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantmesh.data.instruments import CanonicalInstrumentId
from quantmesh.domain.market_data import Bar


class AdjustmentUnavailableError(ValueError):
    """Corporate-action evidence cannot support the requested adjusted series."""


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


class EquitySplitAction(BaseModel):
    """One provider-evidenced split, including when it became knowable."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    action_id: str = Field(min_length=1)
    canonical_instrument: CanonicalInstrumentId
    announced_at: datetime
    effective_at: datetime
    ratio: float = Field(gt=0)

    @model_validator(mode="after")
    def timestamps_and_ratio_are_unambiguous(self) -> Self:
        if not _is_utc(self.announced_at) or not _is_utc(self.effective_at):
            raise ValueError("split announcement and effective timestamps must be UTC")
        if self.announced_at > self.effective_at:
            raise ValueError("split announcement cannot be after effective timestamp")
        if not math.isfinite(self.ratio) or self.ratio == 1.0:
            raise ValueError("split ratio must be finite and different from one")
        return self


class EquityAdjustmentPolicy(BaseModel):
    """A knowledge-bounded split policy pinned to factor and action evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    policy_id: str = "split-adjusted-v1"
    canonical_instrument: CanonicalInstrumentId
    factor_manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    known_at: datetime
    applies_corporate_actions: bool = True
    qualifies: bool = True

    @model_validator(mode="after")
    def policy_is_supported_and_knowledge_is_utc(self) -> Self:
        if self.policy_id != "split-adjusted-v1":
            raise ValueError(f"unsupported equity adjustment policy {self.policy_id!r}")
        if not self.applies_corporate_actions or not self.qualifies:
            raise ValueError("split-adjusted-v1 must declare qualifying corporate actions")
        if not _is_utc(self.known_at):
            raise ValueError("equity adjustment knowledge time must be UTC")
        if self.factor_manifest_id == self.action_manifest_id:
            raise ValueError("factor and action manifests must be independently identified")
        return self

    def apply(self, bars: list[Bar], actions: list[EquitySplitAction]) -> list[Bar]:
        """Apply only splits evidenced no later than this policy's knowledge time."""
        return build_adjusted_series(bars=bars, actions=actions, policy=self)


def adjust_split(bar: Bar, *, factor: float) -> Bar:
    """Backward-adjust one bar for a split ratio without mutating the input."""
    if (
        isinstance(factor, bool)
        or not isinstance(factor, (int, float))
        or not math.isfinite(factor)
        or factor <= 0
    ):
        raise AdjustmentUnavailableError("split factor must be a finite positive number")
    return bar.model_copy(
        update={
            "open": bar.open / factor,
            "high": bar.high / factor,
            "low": bar.low / factor,
            "close": bar.close / factor,
            "volume": bar.volume * factor,
        }
    )


def build_adjusted_series(
    *,
    bars: list[Bar],
    actions: list[EquitySplitAction],
    policy: EquityAdjustmentPolicy,
) -> list[Bar]:
    """Build a backward split-adjusted series under an explicit knowledge cutoff."""
    expected = policy.canonical_instrument.value
    expected_symbol = expected.split(":")[2]
    if any(
        bar.instrument.symbol != expected_symbol or bar.instrument.venue.value != "moomoo"
        for bar in bars
    ):
        raise AdjustmentUnavailableError("bar instrument disagrees with adjustment policy")
    if any(action.canonical_instrument != policy.canonical_instrument for action in actions):
        raise AdjustmentUnavailableError("action instrument disagrees with adjustment policy")
    if any(action.announced_at > policy.known_at for action in actions):
        raise AdjustmentUnavailableError(
            "corporate action was unavailable at the requested knowledge time"
        )

    action_ids = [action.action_id for action in actions]
    if len(action_ids) != len(set(action_ids)):
        raise AdjustmentUnavailableError("ambiguous duplicate corporate-action identity")
    effective_ratios: dict[datetime, float] = {}
    for action in actions:
        observed = effective_ratios.setdefault(action.effective_at, action.ratio)
        if observed != action.ratio:
            raise AdjustmentUnavailableError("ambiguous split ratios for one effective timestamp")

    effective_actions = [
        action for action in actions if action.effective_at <= policy.known_at
    ]
    adjusted: list[Bar] = []
    for bar in bars:
        factor = math.prod(
            action.ratio for action in effective_actions if bar.timestamp < action.effective_at
        )
        adjusted.append(adjust_split(bar, factor=factor))
    return adjusted


class AdjustmentPolicy(BaseModel):
    """A named, immutable price-adjustment contract."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    policy_id: str = Field(min_length=1)
    applies_corporate_actions: bool
    qualifies: bool

    @model_validator(mode="after")
    def identity_policy_is_truthful(self) -> Self:
        if self.policy_id == "unadjusted-identity-v1" and (
            self.applies_corporate_actions or self.qualifies
        ):
            raise ValueError("the unadjusted identity policy cannot claim adjusted evidence")
        return self

    def apply(self, bars: list[Bar]) -> list[Bar]:
        """Apply this policy without mutating caller-owned rows."""
        if self.policy_id != "unadjusted-identity-v1":
            raise ValueError(f"unsupported adjustment policy {self.policy_id!r}")
        return list(bars)


UNADJUSTED_IDENTITY = AdjustmentPolicy(
    policy_id="unadjusted-identity-v1",
    applies_corporate_actions=False,
    qualifies=False,
)
