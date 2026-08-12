"""QuantMesh-owned evidence contracts for isolated framework bake-offs."""

import math
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

FRAMEWORK_HARD_GATE_NAMES = (
    "license",
    "windows_install",
    "deterministic",
    "chronological_split",
    "no_leakage",
    "paper_only",
    "contract_mapping",
)
FRAMEWORK_SCORE_INPUT_NAMES = (
    "workflow_fit",
    "adapter_cost",
    "maintenance",
    "resource_cost",
    "packaging",
    "observability",
    "migration",
)
FRAMEWORK_SCORE_WEIGHTS: Mapping[str, float] = MappingProxyType(
    {
        "workflow_fit": 25,
        "adapter_cost": 20,
        "maintenance": 15,
        "resource_cost": 15,
        "packaging": 10,
        "observability": 10,
        "migration": 5,
    }
)
FrameworkName = Literal["finrl-x", "nautilus-trader"]
FrameworkDisposition = Literal["adopt-adapter", "isolated-comparator", "reject"]


def calculate_framework_total(scores: Mapping[str, float]) -> float:
    """Apply the immutable schema-v1 weights with stable half-up rounding."""
    weighted = sum(
        Decimal(str(scores[name])) * Decimal(str(FRAMEWORK_SCORE_WEIGHTS[name]))
        for name in FRAMEWORK_SCORE_INPUT_NAMES
    )
    total_weight = sum(
        Decimal(str(FRAMEWORK_SCORE_WEIGHTS[name]))
        for name in FRAMEWORK_SCORE_INPUT_NAMES
    )
    return float(
        (weighted / total_weight).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    )


def evaluate_framework_policy(
    framework: FrameworkName,
    hard_gates: Mapping[str, bool],
    total: float,
) -> tuple[bool, FrameworkDisposition]:
    """Return schema-v1 runtime admission and its truthful disposition."""
    runtime_admissible = all(
        hard_gates[name] for name in FRAMEWORK_HARD_GATE_NAMES
    ) and total >= 80
    if runtime_admissible:
        return True, "adopt-adapter"
    comparator_gates = FRAMEWORK_HARD_GATE_NAMES[:-1]
    if (
        framework == "nautilus-trader"
        and all(hard_gates[name] for name in comparator_gates)
        and not hard_gates["contract_mapping"]
    ):
        return False, "isolated-comparator"
    return False, "reject"


class FrameworkRunEvidence(BaseModel):
    """Evidence emitted by one isolated framework evaluation run."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    schema_version: Literal[1] = 1
    framework: FrameworkName
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
        unknown = set(value) - set(FRAMEWORK_SCORE_INPUT_NAMES)
        if unknown:
            raise ValueError(f"unknown score_inputs keys: {sorted(unknown)}")
        if any(not math.isfinite(score) or not 0 <= score <= 100 for score in value.values()):
            raise ValueError("score_inputs values must be finite and within 0..100")
        return value

    @field_validator("checks")
    @classmethod
    def checks_use_known_boolean_gates(cls, value: dict[str, bool]) -> dict[str, bool]:
        unknown = set(value) - set(FRAMEWORK_HARD_GATE_NAMES)
        if unknown:
            raise ValueError(f"unknown checks keys: {sorted(unknown)}")
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
    """Deterministic result of applying the framework admission scorecard."""

    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)

    schema_version: Literal[1] = 1
    framework: FrameworkName
    revision: str = Field(min_length=7)
    hard_gates: dict[str, bool]
    soft_scores: dict[str, float]
    total: float = Field(ge=0, le=100)
    runtime_admissible: bool
    disposition: FrameworkDisposition
    missing_inputs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("hard_gates")
    @classmethod
    def hard_gates_have_exact_shape(cls, value: dict[str, bool]) -> dict[str, bool]:
        if set(value) != set(FRAMEWORK_HARD_GATE_NAMES):
            raise ValueError("hard_gates must contain exactly the schema-v1 gates")
        return value

    @field_validator("soft_scores")
    @classmethod
    def soft_scores_have_exact_shape_and_range(
        cls, value: dict[str, float]
    ) -> dict[str, float]:
        if set(value) != set(FRAMEWORK_SCORE_INPUT_NAMES):
            raise ValueError("soft_scores must contain exactly the schema-v1 inputs")
        if any(not math.isfinite(score) or not 0 <= score <= 100 for score in value.values()):
            raise ValueError("soft_scores values must be finite and within 0..100")
        return value

    @field_validator("missing_inputs")
    @classmethod
    def missing_inputs_are_ordered_unique_subset(cls, value: list[str]) -> list[str]:
        selected = set(value)
        canonical = [name for name in FRAMEWORK_SCORE_INPUT_NAMES if name in selected]
        if len(selected) != len(value) or value != canonical:
            raise ValueError("missing_inputs must be an ordered unique schema-v1 subset")
        return value

    @model_validator(mode="after")
    def normalized_score_is_self_consistent(self) -> "FrameworkScore":
        if any(self.soft_scores[name] != 0 for name in self.missing_inputs):
            raise ValueError("missing_inputs must identify zero-valued soft_scores")
        expected_total = calculate_framework_total(self.soft_scores)
        if self.total != expected_total:
            raise ValueError(f"total must equal deterministic score {expected_total}")
        expected_admission, expected_disposition = evaluate_framework_policy(
            self.framework, self.hard_gates, self.total
        )
        if self.runtime_admissible is not expected_admission:
            raise ValueError(
                f"runtime_admissible must be {expected_admission} for this score"
            )
        if self.disposition != expected_disposition:
            raise ValueError(
                f"disposition must be {expected_disposition!r} for this score"
            )
        return self
