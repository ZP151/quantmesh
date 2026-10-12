"""Version-one research contracts. No executable code or order authority."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantmesh.data.layout import validate_dataset_name, validate_symbol
from quantmesh.research.reports import CostModel, UniverseMember, WalkForwardSpec

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,128}$")]
JobState = Literal["queued", "running", "succeeded", "failed", "cancelled"]
AnalysisState = Literal[
    "not_requested", "pending", "running", "succeeded", "failed", "unavailable", "cancelled"
]
ErrorCode = Literal[
    "worker_failed",
    "timeout",
    "budget_exhausted",
    "artifact_invalid",
    "dataset_rejected",
    "analysis_failed",
    "model_unavailable",
    "unknown_effect",
    "cancelled",
]
LEASE_SECONDS = 60
HEARTBEAT_SECONDS = 15
MAX_CONCURRENT_JOBS = 2


class ResearchError(ValueError):
    """Safe, typed boundary errors; never attach raw input to public messages."""


class IdempotencyConflict(ResearchError):
    pass


class DatasetRejected(ResearchError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"dataset rejected: {reason}")


class StoreUnavailable(ResearchError):
    pass


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @model_validator(mode="after")
    def aware_times(self):
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, datetime) and value.utcoffset() is None:
                raise ValueError("timestamps must be timezone-aware")
        return self


class StrategySpec(Contract):
    strategy_id: Identifier
    version: Identifier
    family: Identifier
    parameters_schema: dict
    supported_markets: list[str]
    supported_intervals: list[str]
    dataset_requirements: dict
    cost_policy_id: Identifier
    implementation_digest: Digest


class DatasetRef(Contract):
    dataset_id: str
    revision: int = Field(ge=1)
    manifest_digest: Digest
    permission_class: Literal["fixture", "local_research", "remote_export"]
    export_digest: Digest

    @model_validator(mode="after")
    def safe_dataset(self):
        validate_dataset_name(self.dataset_id)
        return self


class RunBudget(Contract):
    timeout_seconds: int = Field(default=900, ge=1, le=900)
    memory_mib: int = Field(default=2048, ge=1, le=2048)
    cpu_limit: float = Field(default=1.0, gt=0, le=1.0)
    max_model_calls: int = Field(default=12, ge=0, le=12)
    max_estimated_model_usd: float = Field(default=1.0, ge=0, le=1.0)


class JobCosts(CostModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)

    @model_validator(mode="after")
    def explicit_costs(self):
        if min(self.fee_bps, self.half_spread_bps, self.slippage_bps) <= 0:
            raise ValueError("research requires positive fees, spread and slippage")
        return self


class JobWindows(WalkForwardSpec):
    model_config = ConfigDict(extra="forbid", frozen=True)


class JobUniverseMember(UniverseMember):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def safe_symbol(self):
        validate_symbol(self.symbol)
        return self


class ResearchJobRequest(Contract):
    schema_version: Literal[1] = 1
    strategy_id: Identifier
    strategy_version: Identifier
    dataset: DatasetRef
    interval: str
    universe: list[JobUniverseMember] = Field(min_length=1)
    parameters: dict = Field(default_factory=dict)
    costs: JobCosts
    window_spec: JobWindows
    budget: RunBudget = Field(default_factory=RunBudget)
    analysis_requested: bool = False

    @model_validator(mode="after")
    def registered_setup(self):
        from quantmesh.research.baselines import validate_universe
        from quantmesh.research.strategy_registry import get_strategy

        spec = get_strategy(self.strategy_id, self.strategy_version)
        if self.interval not in spec.supported_intervals:
            raise ValueError("unsupported interval")
        if self.parameters:
            raise ValueError("version-one baselines accept no parameters")
        validate_universe(self.universe)
        if any(m.venue.value not in spec.supported_markets for m in self.universe):
            raise ValueError("unsupported market")
        return self


def canonical_request_digest(request: ResearchJobRequest) -> str:
    # Revalidate even model_construct/model_copy inputs before hashing/admission.
    valid = ResearchJobRequest.model_validate(request.model_dump(mode="json"))
    raw = json.dumps(
        valid.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class ArtifactRef(Contract):
    artifact_id: Digest
    kind: Literal["report", "equity_curve", "trades", "analysis"]
    schema_version: Literal[1] = 1
    sha256: Digest
    byte_size: int = Field(ge=1)
    object_key: str = Field(pattern=r"^[A-Za-z0-9_-]+/[0-9a-f]{64}\.[a-z]+$")


class Usage(Contract):
    """None is unknown/unmeasured, including when no worker has run."""

    elapsed_seconds: float | None = Field(default=None, ge=0)
    peak_memory_mib: float | None = Field(default=None, ge=0)
    model_calls: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    estimated_model_usd: float | None = Field(default=None, ge=0)


class AnalysisRecord(Contract):
    job_id: Identifier
    report_digest: Digest
    state: Literal["succeeded", "failed", "unavailable", "cancelled"]
    provider: Identifier | None = None
    model: Identifier | None = None
    prompt_digest: Digest | None = None
    output_digest: Digest | None = None
    output_artifact: ArtifactRef | None = None
    citations: list[ArtifactRef] = Field(default_factory=list)
    verdict: Literal["support", "challenge", "inconclusive", "unavailable"]
    usage: Usage = Field(default_factory=Usage)
    estimated_price_version: Identifier | None = None
    error_code: ErrorCode | None = None

    @model_validator(mode="after")
    def honest_analysis(self):
        if (self.provider is None) != (self.model is None):
            raise ValueError("provider and model must be supplied together")
        if self.prompt_digest == "0" * 64 or self.output_digest == "0" * 64:
            raise ValueError("placeholder digests are not evidence")
        if self.output_digest is not None and (self.prompt_digest is None or self.model is None):
            raise ValueError("output requires prompt and model identity")
        if self.output_artifact is not None and (
            self.output_artifact.kind != "analysis"
            or self.output_artifact.sha256 != self.output_digest
        ):
            raise ValueError("analysis output reference must match output digest")
        if self.state == "succeeded":
            if (
                self.error_code is not None
                or self.provider is None
                or self.model is None
                or self.prompt_digest is None
                or self.output_digest is None
                or self.output_artifact is None
                or not self.citations
                or self.verdict == "unavailable"
            ):
                raise ValueError("successful analysis requires generated metadata and citations")
        elif self.error_code is None or self.verdict != "unavailable":
            raise ValueError("unsuccessful analysis requires unavailable verdict and error code")
        return self


class AnalysisLease(Contract):
    job_id: Identifier
    owner: Identifier
    attempt: int = Field(ge=1)
    expires_at: datetime
    report_digest: Digest


class JobRecord(Contract):
    job_id: Identifier
    operator_id: Identifier
    idempotency_key: Identifier
    request: ResearchJobRequest
    request_digest: Digest
    implementation_digest: Digest
    state: JobState = "queued"
    attempt: int = Field(default=0, ge=0)
    lease_owner: Identifier | None = None
    lease_expires_at: datetime | None = None
    cancel_requested: bool = False
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None = None
    error_code: ErrorCode | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    analysis_state: AnalysisState = "not_requested"
    analysis: AnalysisRecord | None = None


def schema_digest() -> str:
    """Canonical schema bundle for Batch-B consumers; protocol is frozen separately."""
    models = (
        StrategySpec,
        DatasetRef,
        RunBudget,
        ResearchJobRequest,
        JobRecord,
        ArtifactRef,
        AnalysisRecord,
        AnalysisLease,
    )
    raw = json.dumps(
        {m.__name__: m.model_json_schema() for m in models},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(raw).hexdigest()
