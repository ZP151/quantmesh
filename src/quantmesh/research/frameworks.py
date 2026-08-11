"""QuantMesh-owned evidence contracts for isolated framework bake-offs."""

import math
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class FrameworkRunEvidence(BaseModel):
    """Evidence emitted by one isolated framework evaluation run."""

    schema_version: Literal[1] = 1
    framework: Literal["finrl-x", "nautilus-trader"]
    revision: str = Field(min_length=7)
    status: Literal["passed", "failed"]
    deterministic: bool
    input_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    duration_seconds: float = Field(ge=0)
    peak_rss_mb: float = Field(ge=0)
    environment_bytes: int = Field(ge=0)
    checks: dict[str, bool]
    artifacts: dict[str, str]
    score_inputs: dict[str, float] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def incomplete_passes_fail_with_the_evidence_gate(cls, value: object) -> object:
        """Keep the public evidence-gate error ahead of field-level errors."""
        if not isinstance(value, dict) or value.get("status") != "passed":
            return value
        required = {"windows_install", "chronological_split", "no_leakage", "license"}
        checks = value.get("checks")
        revision = value.get("revision")
        if (
            not isinstance(revision, str)
            or len(revision) < 7
            or not value.get("deterministic")
            or value.get("output_digest") is None
            or not isinstance(checks, dict)
            or not required.issubset(checks)
            or not all(checks[name] for name in required)
        ):
            raise ValueError("passing run requires deterministic output and all mandatory checks")
        return value

    @field_validator("score_inputs")
    @classmethod
    def score_inputs_are_finite_percentages(cls, value: dict[str, float]) -> dict[str, float]:
        if any(not math.isfinite(score) or not 0 <= score <= 100 for score in value.values()):
            raise ValueError("score_inputs values must be finite and within 0..100")
        return value

    @model_validator(mode="after")
    def passed_runs_are_complete(self) -> "FrameworkRunEvidence":
        required = {"windows_install", "chronological_split", "no_leakage", "license"}
        if self.status == "passed" and (
            not self.deterministic
            or self.output_digest is None
            or not required.issubset(self.checks)
            or not all(self.checks[name] for name in required)
        ):
            raise ValueError("passing run requires deterministic output and all mandatory checks")
        return self


class FrameworkScore(BaseModel):
    """Data-only scorecard result; Task 4 owns scoring behavior."""

    schema_version: Literal[1] = 1
    framework: Literal["finrl-x", "nautilus-trader"]
    revision: str = Field(min_length=7)
    hard_gates: dict[str, bool]
    soft_scores: dict[str, float]
    total: float = Field(ge=0, le=100)
    runtime_admissible: bool
    disposition: Literal["adopt-adapter", "isolated-comparator", "reject"]
    limitations: list[str] = Field(default_factory=list)
