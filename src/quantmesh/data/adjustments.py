"""Explicit adjustment policies for trusted-data publications."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantmesh.domain.market_data import Bar


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
