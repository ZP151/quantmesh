"""One fixed, opt-in development replay; no generic jobs or trading authority."""

from __future__ import annotations

import hashlib
import io
import json
import math
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.calendars import XNYS_REGULAR_VERSION, CalendarService, SessionPolicy
from quantmesh.data.objects import ObjectRef, ObjectStore, is_reparse_point
from quantmesh.ops.paper_controls import WriterLease
from quantmesh.persistence.jsonl import JsonlStore
from quantmesh.research import spy_policy_exception as once
from quantmesh.research import spy_replay_engine as engine

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
MAX_OBJECT = 1024 * 1024
MAX_JOBS = 32
_SOURCE_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_ENGINE_SHA = hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest()


class ReplayError(ValueError):
    """Fixed safe public code only."""


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(raw):
    def pairs(items):
        output = {}
        for key, value in items:
            if key in output:
                raise ValueError("duplicate key")
            output[key] = value
        return output

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")),
    )


def _safe(path):
    if any(is_reparse_point(p) for p in (path, *path.parents)):
        raise ReplayError("service_unavailable")


def _uuid(value):
    return str(UUID(str(value)))


def _now():
    return datetime.now(UTC)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class EvidenceFact(Contract):
    value: str | None = Field(default=None, max_length=160)
    status: Literal["recorded", "synthetic", "unknown", "not_applicable"] = "unknown"
    reason: str | None = Field(default="not_recorded", max_length=160)

    @model_validator(mode="after")
    def available_or_reason(self):
        if self.status in {"unknown", "not_applicable"}:
            if self.value is not None or not self.reason:
                raise ValueError("unknown fact needs reason")
        elif self.value is None or self.reason is not None:
            raise ValueError("available fact needs value")
        return self


def _fact(value=None, *, status="recorded", reason=None):
    return EvidenceFact(value=value, status=status, reason=reason)


class EvidenceTimes(Contract):
    requested_at_utc: EvidenceFact = Field(default_factory=EvidenceFact)
    received_at_utc: EvidenceFact = Field(default_factory=EvidenceFact)
    post_reviewed_at_utc: EvidenceFact = Field(default_factory=EvidenceFact)
    acceptance_reviewed_at_utc: EvidenceFact = Field(default_factory=EvidenceFact)
    available_at_utc: EvidenceFact = Field(default_factory=EvidenceFact)

    @model_validator(mode="after")
    def utc_times(self):
        for name in type(self).model_fields:
            value = getattr(self, name).value
            if value is not None and datetime.fromisoformat(value).utcoffset() != timedelta(0):
                raise ValueError("UTC required")
        return self


class EvidenceRefs(Contract):
    freeze: ObjectRef | None = None
    raw_capture: ObjectRef | None = None
    authorization: ObjectRef | None = None
    post_review: ObjectRef | None = None
    acceptance: ObjectRef | None = None
    normalized_bars: ObjectRef | None = None
    distributions: ObjectRef | None = None

    @model_validator(mode="after")
    def bounded(self):
        if any(
            ref is not None and ref.byte_length > 8 * MAX_OBJECT
            for name in type(self).model_fields
            for ref in [getattr(self, name)]
        ):
            raise ValueError("evidence reference too large")
        return self


class SourceFacts(Contract):
    source_use: EvidenceFact = Field(default_factory=EvidenceFact)
    allowed_use: EvidenceFact = Field(default_factory=EvidenceFact)
    pit: EvidenceFact = Field(default_factory=EvidenceFact)
    revision_status: EvidenceFact = Field(default_factory=EvidenceFact)
    price_adjustment: EvidenceFact = Field(default_factory=EvidenceFact)
    currency: EvidenceFact = Field(default_factory=EvidenceFact)
    volume_unit: EvidenceFact = Field(default_factory=EvidenceFact)
    dividend_unit: EvidenceFact = Field(default_factory=EvidenceFact)
    action_coverage: EvidenceFact = Field(default_factory=EvidenceFact)


class ReviewHashes(Contract):
    action_coverage_sha256: Digest | None = None
    field_semantics_sha256: Digest | None = None
    independent_input_review_sha256: Digest | None = None


class SampleProvenance(Contract):
    """Trusted construction only; never accepted from the public request."""

    sample_id: str = Field(default="SPY", min_length=1, max_length=80)
    sample_version: str | None = Field(default=None, min_length=1, max_length=80)
    parent_version: str | None = Field(default=None, min_length=1, max_length=80)
    sample_role: Literal["fixed_golden", "historical_diagnostic", "rolling_diagnostic"] | None = (
        None
    )
    times: EvidenceTimes = Field(default_factory=EvidenceTimes)
    refs: EvidenceRefs = Field(default_factory=EvidenceRefs)
    source_facts: SourceFacts = Field(default_factory=SourceFacts)
    review_hashes: ReviewHashes = Field(default_factory=ReviewHashes)


class SampleQuality(Contract):
    rows: Literal[121] = 121
    warmup_sessions: Literal[100] = 100
    observation_sessions: Literal[21] = 21
    missing_sessions: Literal[0] = 0
    duplicate_sessions: Literal[0] = 0
    ordered_sessions_match: Literal[True] = True
    ohlcv_checked: Literal[True] = True
    structural_status: Literal["PASS"] = "PASS"


class SampleCalendar(Contract):
    calendar_id: Literal["XNYS"] = "XNYS"
    calendar_version: str = Field(min_length=1, max_length=100)
    source_grace_minutes: Literal[30] = 30
    last_session: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")


class SampleEvidence(SampleProvenance):
    schema_version: Literal[1] = 1
    snapshot_digest: Digest
    protocol_digest: Digest
    evidence_kind: Literal["engineering_fixture", "reviewed_opend_freeze_v2"]
    sample_version: str = Field(min_length=1, max_length=80)
    sample_role: Literal["fixed_golden", "historical_diagnostic", "rolling_diagnostic"]
    purpose: Literal["fixed_engineering_regression", "historical_development_diagnostic"]
    as_of_utc: str
    frozen_at_utc: str
    timestamp_basis: Literal["synthetic_declared", "source_receipts"]
    provider: Literal["synthetic", "opend"]
    quality: SampleQuality = Field(default_factory=SampleQuality)
    calendar: SampleCalendar
    exposure_status: Literal["synthetic_not_oos", "historical_exposed_not_independent_oos"]
    first_viewed_at_utc: EvidenceFact = Field(default_factory=EvidenceFact)
    trial_count: None = None
    trial_count_reason: Literal["trial_history_unavailable"] = "trial_history_unavailable"
    last_checked_at_utc: str
    check_scope: Literal["structural_bytes_only", "structural_bytes_and_receipt_bindings"]
    next_trigger: Literal["code_protocol_or_boundary_change", "new_qualified_frozen_version"]

    @model_validator(mode="after")
    def bounded_and_honest(self):
        for value in (self.as_of_utc, self.frozen_at_utc, self.last_checked_at_utc):
            if datetime.fromisoformat(value).utcoffset() != timedelta(0):
                raise ValueError("UTC required")
        if self.refs.freeze is not None and self.refs.freeze.digest != self.snapshot_digest:
            raise ValueError("freeze identity mismatch")
        synthetic = self.evidence_kind == "engineering_fixture"
        if synthetic:
            if (self.provider, self.timestamp_basis, self.sample_role, self.purpose) != (
                "synthetic",
                "synthetic_declared",
                "fixed_golden",
                "fixed_engineering_regression",
            ) or any(
                getattr(self.refs, name) is not None
                for name in ("freeze", "raw_capture", "authorization", "post_review", "acceptance")
            ):
                raise ValueError("synthetic is not source qualification")
        elif (self.provider, self.timestamp_basis, self.purpose) != (
            "opend",
            "source_receipts",
            "historical_development_diagnostic",
        ) or self.sample_role == "fixed_golden":
            raise ValueError("source evidence identity mismatch")
        if len(canonical(self.model_dump(mode="json"))) > 32768:
            raise ValueError("sample evidence too large")
        return self


EXCEPTION_KIND = "reviewed_opend_policy_exception_once_v3"
PROOF_NAMES = {
    "human-approval.json",
    "source-use-policy.md",
    "capture-intent.json",
    "capture-authorization.json",
    "post-review.json",
    "acceptance.json",
    "freeze.json",
    "protocol.json",
}


class ExceptionSampleEvidence(SampleEvidence):
    schema_version: Literal[2] = 2
    evidence_kind: Literal["reviewed_opend_policy_exception_once_v3"]
    policy_exception: once.OnceBinding
    capture_intent_ref: ObjectRef
    proof_refs: dict[str, ObjectRef]

    @model_validator(mode="after")
    def proof_bounds(self):
        if set(self.proof_refs) != PROOF_NAMES or any(
            not 1
            <= ref.byte_length
            <= (MAX_OBJECT if name in {"protocol.json", "freeze.json"} else once.MAX_PROOF)
            for name, ref in self.proof_refs.items()
        ):
            raise ValueError("exception_proofs_invalid")
        return self


class SampleFreshnessView(Contract):
    read_at_utc: datetime
    evaluated_snapshot_digest: Digest
    calendar_version: str | None = None
    source_grace_minutes: int | None = None
    latest_complete_session: str | None = None
    lag_complete_sessions: int | None = Field(default=None, ge=0)
    applicability: Literal[
        "fixed_regression_not_required", "historical_diagnostic", "recent_diagnostic", "unknown"
    ] = "unknown"
    reason: Literal[
        "fixed_sample_no_daily_refresh",
        "historical_window_not_recency_target",
        "current",
        "lags_latest_complete_session",
        "legacy_sample_role_unknown",
        "calendar_unavailable",
        "report_unavailable",
        "input_identity_mismatch",
        "sample_end_after_latest_complete",
    ]


def sample_freshness_view(report, snapshot_digest, read_at):
    """Read-only age from this artifact's calendar; never from next-input options."""
    data = dict(read_at_utc=read_at, evaluated_snapshot_digest=snapshot_digest)
    if report is None:
        return SampleFreshnessView(**data, reason="report_unavailable")
    if report.get("snapshot_digest") != snapshot_digest:
        return SampleFreshnessView(**data, reason="input_identity_mismatch")
    window = report.get("window", {})
    if not isinstance(window, dict):
        return SampleFreshnessView(**data, reason="calendar_unavailable")
    data.update(
        calendar_version=window.get("calendar_version"),
        source_grace_minutes=window.get("source_grace_minutes"),
    )
    try:
        last = date.fromisoformat(window["score_end"])
        if (
            window["calendar_version"] != XNYS_REGULAR_VERSION
            or window["source_grace_minutes"] != 30
            or read_at.utcoffset() != timedelta(0)
            or not date(2000, 1, 3) <= last <= date(2035, 12, 31)
            or not date(2000, 2, 3) <= read_at.date() <= date(2035, 12, 31)
        ):
            raise ValueError("calendar unavailable")
        sessions = CalendarService().sessions(
            "XNYS",
            min(last, read_at.date() - timedelta(days=30)),
            read_at.date(),
            policy=SessionPolicy.REGULAR,
        )
        complete = [
            s.session_date.isoformat()
            for s in sessions
            if s.close_at + timedelta(minutes=30) <= read_at
        ]
        latest = complete[-1]
    except Exception:
        return SampleFreshnessView(**data, reason="calendar_unavailable")
    data["latest_complete_session"] = latest
    if last.isoformat() > latest:
        return SampleFreshnessView(**data, reason="sample_end_after_latest_complete")
    data["lag_complete_sessions"] = sum(day > last.isoformat() for day in complete)
    role = report.get("sample_evidence", {}).get("sample_role")
    if role == "fixed_golden":
        return SampleFreshnessView(
            **data,
            applicability="fixed_regression_not_required",
            reason="fixed_sample_no_daily_refresh",
        )
    if role == "historical_diagnostic":
        return SampleFreshnessView(
            **data, applicability=role, reason="historical_window_not_recency_target"
        )
    if role == "rolling_diagnostic":
        return SampleFreshnessView(
            **data,
            applicability="recent_diagnostic",
            reason="current"
            if data["lag_complete_sessions"] == 0
            else "lags_latest_complete_session",
        )
    return SampleFreshnessView(**data, reason="legacy_sample_role_unknown")


class ReplayRequest(Contract):
    snapshot_digest: Digest
    protocol_digest: Digest


class DecisionRequest(Contract):
    request_digest: Digest
    report_digest: Digest
    disposition: Literal["reject", "watch"]
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_trimmed(cls, value):
        if not value.strip():
            raise ValueError("reason required")
        return value.strip()


class ReplayDecision(DecisionRequest):
    schema_version: Literal[1] = 1
    decision_key: str
    job_id: str
    snapshot_digest: Digest
    protocol_digest: Digest
    created_at: datetime


class ReplayJob(Contract):
    schema_version: Literal[1] = 1
    job_id: str
    request_digest: Digest
    request: ReplayRequest
    state: Literal["running", "succeeded", "failed", "interrupted"]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    report: ObjectRef | None = None
    decision: ReplayDecision | None = None
    decision_ref: ObjectRef | None = None
    error_code: Literal["computation_failed", "artifact_invalid", "interrupted"] | None = None
    financial_qualification: Literal["INSUFFICIENT"] = "INSUFFICIENT"
    paper_allowed: Literal[False] = False

    @model_validator(mode="after")
    def consistent(self):
        if _uuid(self.job_id) != self.job_id or self.request_digest != digest(
            canonical(self.request.model_dump())
        ):
            raise ValueError("job identity mismatch")
        times = [self.created_at, self.updated_at, self.completed_at]
        if any(t is not None and t.utcoffset() != UTC.utcoffset(t) for t in times):
            raise ValueError("UTC required")
        if self.updated_at < self.created_at or (
            self.completed_at is not None and self.completed_at < self.created_at
        ):
            raise ValueError("time order")
        if (self.state == "running") != (self.completed_at is None):
            raise ValueError("completion mismatch")
        if (self.state == "succeeded") != (self.report is not None):
            raise ValueError("report mismatch")
        if (self.state in {"failed", "interrupted"}) != (self.error_code is not None):
            raise ValueError("error mismatch")
        if (self.decision is None) != (self.decision_ref is None):
            raise ValueError("decision mismatch")
        for ref in (self.report, self.decision_ref):
            if ref is not None and (
                not 1 <= ref.byte_length <= MAX_OBJECT or ref.media_type != "application/json"
            ):
                raise ValueError("artifact bounds")
        if self.decision is not None:
            d = self.decision
            if self.report is None or (
                d.job_id,
                d.request_digest,
                d.snapshot_digest,
                d.protocol_digest,
                d.report_digest,
            ) != (
                self.job_id,
                self.request_digest,
                self.request.snapshot_digest,
                self.request.protocol_digest,
                self.report.digest,
            ):
                raise ValueError("decision binding")
            if _uuid(d.decision_key) != d.decision_key or d.created_at < self.completed_at:
                raise ValueError("decision identity/time")
        return self


class _StoredJob(ReplayJob):
    implementation_digest: Digest


class ReplayJobRead(ReplayJob):
    """GET-only extension; POST responses and stored records stay ReplayJob."""

    sample_freshness_view: SampleFreshnessView


class ReplayInputSummary(Contract):
    snapshot_digest: Digest
    protocol_digest: Digest
    symbol: Literal["SPY"] = "SPY"
    interval: Literal["1d"] = "1d"
    as_of_utc: str
    frozen_at_utc: str
    warmup_start: str
    observation_start: str
    observation_end: str
    evidence_kind: Literal["reviewed_opend_freeze_v2", "engineering_fixture"]
    limitations: list[str]


class ExceptionInputSummary(ReplayInputSummary):
    evidence_kind: Literal["reviewed_opend_policy_exception_once_v3"]
    policy_exception: once.OnceBinding


class ReplayOptions(Contract):
    schema_version: Literal[1] = 1
    configured: bool
    unavailable_reason: Literal["not_configured", "input_not_qualified"] | None
    input: ReplayInputSummary | ExceptionInputSummary | None
    fixed: dict = Field(
        default_factory=lambda: dict(
            strategy_id="SMA100-long-cash",
            warmup_sessions=100,
            observation_sessions=21,
            capital_usd=100000,
            base_one_way_bps=5,
            stress_one_way_bps=10,
            cash_interest=0,
            fee_spread_slippage_components=None,
        )
    )
    limits: dict = Field(default_factory=lambda: dict(max_jobs=32, max_inflight=1))
    financial_qualification: Literal["INSUFFICIENT"] = "INSUFFICIENT"
    paper_allowed: Literal[False] = False


LIMITATIONS = [
    "Historical development diagnostic; no independent OOS or profitability qualification.",
    "Daily OPEN proxy; historical executable prices and calibrated costs are not established.",
    "Combined cost proxy; fee/spread/slippage decomposition unavailable. Cash interest assumed0.",
    "Source review receipts do not establish independent legal or historical PIT proof.",
    "Paper and live trading are not authorized.",
]


def _freezer():
    from tools.research import freeze_opend_spy_daily

    if Path(freeze_opend_spy_daily.__file__).resolve() != (
        Path(__file__).resolve().parents[3] / "tools/research/freeze_opend_spy_daily.py"
    ):
        raise ReplayError("input_not_qualified")
    return freeze_opend_spy_daily


@dataclass(frozen=True)
class ReplayInput:
    """Trusted construction only. No public request accepts input bytes or flags."""

    snapshot_digest: str
    protocol_bytes: bytes
    bars_csv: bytes
    distributions_json: bytes
    frozen_at_utc: datetime
    evidence_kind: Literal[
        "reviewed_opend_freeze_v2", "engineering_fixture", "reviewed_opend_policy_exception_once_v3"
    ]
    source_root: Path | None = None
    provenance: SampleProvenance | None = None
    policy_exception: once.OnceBinding | None = None
    capture_intent_ref: ObjectRef | None = None
    proof_refs: dict[str, ObjectRef] | None = None

    def verified(self):
        freezer = _freezer()
        protocol = _json(self.protocol_bytes)
        w = protocol["window"]
        if freezer.plan_window(datetime.fromisoformat(w["as_of_utc"])) != w:
            raise ReplayError("input_not_qualified")
        exception = self.evidence_kind == EXCEPTION_KIND
        if exception:
            if (
                self.source_root is None
                or self.policy_exception is None
                or self.capture_intent_ref is None
            ):
                raise ReplayError("input_not_qualified")
            frozen = freezer.reopen_freeze(
                self.source_root, self.snapshot_digest, policy_exception=True
            )
            if (
                frozen["protocol"] != protocol
                or frozen["policy_exception"] != self.policy_exception.model_dump(mode="json")
                or frozen["capture_intent_ref"] != self.capture_intent_ref.model_dump(mode="json")
            ):
                raise ReplayError("input_not_qualified")
            expected = freezer._protocol_v3(
                w,
                self.policy_exception.model_dump(mode="json"),
                self.capture_intent_ref.model_dump(mode="json"),
            )
        else:
            expected = freezer._protocol_v2(w)
        if any(
            protocol.get(k) != expected[k]
            for k in (
                "schema_id",
                "provider_symbol",
                "currency",
                "interval",
                "rule",
                "costs",
                "benchmarks",
                "financial_qualification",
                "paper_qualification",
            )
        ):
            raise ReplayError("input_not_qualified")
        if self.frozen_at_utc.utcoffset() != UTC.utcoffset(self.frozen_at_utc):
            raise ReplayError("input_not_qualified")
        if self.evidence_kind not in {
            "reviewed_opend_freeze_v2",
            "engineering_fixture",
            EXCEPTION_KIND,
        }:
            raise ReplayError("input_not_qualified")
        for name, raw in (
            ("normalized-bars.csv", self.bars_csv),
            ("normalized-distributions.json", self.distributions_json),
        ):
            ref = ObjectRef.model_validate(protocol["members"][name])
            if len(raw) > MAX_OBJECT or len(raw) != ref.byte_length or digest(raw) != ref.digest:
                raise ReplayError("input_not_qualified")
        bars = pd.read_csv(io.BytesIO(self.bars_csv), dtype={"date": str})
        if list(bars.columns) != ["date", "open", "high", "low", "close", "volume", "dividend"]:
            raise ReplayError("input_not_qualified")
        if bars.date.tolist() != w["sessions"] or len(bars) != 121:
            raise ReplayError("input_not_qualified")
        for row in bars.itertuples():
            values = [row.open, row.high, row.low, row.close, row.volume, row.dividend]
            if (
                not all(math.isfinite(v) for v in values)
                or min(values[:4]) <= 0
                or min(values[4:]) < 0
            ):
                raise ReplayError("input_not_qualified")
            if row.high < max(row.open, row.close) or row.low > min(row.open, row.close):
                raise ReplayError("input_not_qualified")
        distributions = _json(self.distributions_json)
        if not isinstance(distributions, list) or len(distributions) > 512:
            raise ReplayError("input_not_qualified")
        for event in distributions:
            if set(event) != {"ex_date", "pay_date", "amount"} or not (
                w["score_start"] <= event["ex_date"] <= w["score_end"]
                and event["pay_date"] >= event["ex_date"]
                and type(event["amount"]) in {int, float}
                and math.isfinite(event["amount"])
                and event["amount"] >= 0
            ):
                raise ReplayError("input_not_qualified")
        return protocol, bars.set_index("date"), distributions

    def summary(self):
        p, _, _ = self.verified()
        w = p["window"]
        cls = ExceptionInputSummary if self.policy_exception is not None else ReplayInputSummary
        return cls(
            snapshot_digest=self.snapshot_digest,
            protocol_digest=digest(self.protocol_bytes),
            as_of_utc=w["as_of_utc"],
            frozen_at_utc=self.frozen_at_utc.isoformat(),
            warmup_start=w["warmup_start"],
            observation_start=w["score_start"],
            observation_end=w["score_end"],
            evidence_kind=self.evidence_kind,
            **(
                {"policy_exception": self.policy_exception}
                if self.policy_exception is not None
                else {}
            ),
            limitations=(
                ["Synthetic engineering fixture; not real market acceptance."]
                if self.evidence_kind == "engineering_fixture"
                else []
            )
            + (
                [
                    "diagnostic_only_under_policy_exception; external API storage "
                    "applicability UNKNOWN; no provider permission verification."
                ]
                if self.policy_exception is not None
                else []
            )
            + LIMITATIONS,
        )

    def evidence(self, protocol, bars):
        """Capture known immutable facts before math; absence never becomes approval."""
        if digest(canonical(protocol)) != digest(self.protocol_bytes) or len(bars) != 121:
            raise ReplayError("input_not_qualified")
        p = self.provenance or SampleProvenance()
        synthetic = self.evidence_kind == "engineering_fixture"
        values = p.model_dump()
        if synthetic:
            no_receipt = _fact(status="not_applicable", reason="synthetic_no_provider_receipt")
            values["times"] = {name: no_receipt for name in EvidenceTimes.model_fields}
            facts = {
                name: _fact(status="not_applicable", reason="synthetic_not_market_evidence")
                for name in SourceFacts.model_fields
            }
            for name, value in dict(
                price_adjustment="raw",
                currency="USD",
                volume_unit="shares",
                dividend_unit="USD/share",
                action_coverage=(
                    "synthetic_defined_events"
                    if _json(self.distributions_json)
                    else "synthetic_defined_empty"
                ),
            ).items():
                facts[name] = _fact(value, status="synthetic")
            values["source_facts"] = facts
        refs = p.refs.model_dump()
        refs.update(
            normalized_bars=protocol["members"]["normalized-bars.csv"],
            distributions=protocol["members"]["normalized-distributions.json"],
        )
        w = protocol["window"]
        cls = ExceptionSampleEvidence if self.policy_exception is not None else SampleEvidence
        return cls(
            **(
                {
                    "policy_exception": self.policy_exception,
                    "capture_intent_ref": self.capture_intent_ref,
                    "proof_refs": self.proof_refs,
                }
                if self.policy_exception is not None
                else {}
            ),
            **{
                **values,
                "refs": refs,
                "sample_version": p.sample_version or self.snapshot_digest,
                "sample_role": p.sample_role
                or ("fixed_golden" if synthetic else "historical_diagnostic"),
            },
            snapshot_digest=self.snapshot_digest,
            protocol_digest=digest(self.protocol_bytes),
            evidence_kind=self.evidence_kind,
            purpose="fixed_engineering_regression"
            if synthetic
            else "historical_development_diagnostic",
            as_of_utc=w["as_of_utc"],
            frozen_at_utc=self.frozen_at_utc.isoformat(),
            timestamp_basis="synthetic_declared" if synthetic else "source_receipts",
            provider="synthetic" if synthetic else "opend",
            calendar=SampleCalendar(
                calendar_version=w["calendar_version"], last_session=w["score_end"]
            ),
            exposure_status="synthetic_not_oos"
            if synthetic
            else "historical_exposed_not_independent_oos",
            last_checked_at_utc=_now().isoformat(),
            check_scope="structural_bytes_and_receipt_bindings"
            if p.refs.acceptance
            else "structural_bytes_only",
            next_trigger="code_protocol_or_boundary_change"
            if synthetic
            else "new_qualified_frozen_version",
        )

    @classmethod
    def from_descriptor(cls, path: Path):
        """Operator-only config consumes a bound actual external acceptance receipt.

        A valid freeze alone explicitly requires independent review. Neither this
        descriptor nor its trusted receipt is accepted through the public API.
        """
        try:
            path = Path(path).absolute()
            _safe(path)
            if path.stat().st_size > 16384:
                raise ValueError
            descriptor = _json(path.read_bytes())
            if (
                isinstance(descriptor, dict)
                and type(descriptor.get("schema_version")) is int
                and descriptor["schema_version"] == 3
            ):
                return cls._from_v3_descriptor(descriptor)
            if set(descriptor) != {"freeze_root", "freeze_digest", "acceptance"}:
                raise ValueError
            root = Path(descriptor["freeze_root"]).absolute()
            _safe(root)
            freezer = _freezer()
            frozen = freezer.reopen_freeze(root, descriptor["freeze_digest"])
            if frozen["schema_id"] != "qm.spy-daily.freeze.v2":
                raise ValueError
            store = ObjectStore(root)
            approval_ref = ObjectRef.model_validate(descriptor["acceptance"])
            if approval_ref.byte_length > 16384:
                raise ValueError
            approval = _Acceptance.model_validate_json(store.get_bytes(approval_ref))
            protocol_ref = ObjectRef.model_validate(frozen["protocol_ref"])
            if (approval.snapshot_digest, approval.protocol_digest) != (
                descriptor["freeze_digest"],
                protocol_ref.digest,
            ) or approval.reviewed_at_utc < datetime.fromisoformat(frozen["frozen_at_utc"]):
                raise ValueError
            authorization = _json(
                store.get_bytes(
                    ObjectRef.model_validate(frozen["members"]["capture-authorization.json"])
                )
            )
            if approval.use_document_sha256 != authorization["use_document_sha256"]:
                raise ValueError
            review = _json(
                store.get_bytes(ObjectRef.model_validate(frozen["members"]["post-review.json"]))
            )
            raw = _json(
                store.get_bytes(ObjectRef.model_validate(frozen["members"]["raw-capture.json"]))
            )
            freeze_ref = ObjectRef(
                digest=descriptor["freeze_digest"], byte_length=0, media_type="application/json"
            )
            freeze_ref = freeze_ref.model_copy(
                update={"byte_length": store.path_for(freeze_ref).stat().st_size}
            )
            store.get_bytes(freeze_ref)
            provenance = SampleProvenance(
                times=EvidenceTimes(
                    requested_at_utc=_fact(raw["requested_at_utc"]),
                    received_at_utc=_fact(raw["received_at_utc"]),
                    post_reviewed_at_utc=_fact(review["reviewed_at_utc"]),
                    acceptance_reviewed_at_utc=_fact(approval.reviewed_at_utc.isoformat()),
                    available_at_utc=_fact(status="unknown", reason="not_established_by_receipts"),
                ),
                refs=EvidenceRefs(
                    freeze=freeze_ref,
                    acceptance=approval_ref,
                    raw_capture=ObjectRef.model_validate(frozen["members"]["raw-capture.json"]),
                    authorization=ObjectRef.model_validate(
                        frozen["members"]["capture-authorization.json"]
                    ),
                    post_review=ObjectRef.model_validate(frozen["members"]["post-review.json"]),
                ),
                source_facts=SourceFacts(
                    source_use=_fact(authorization["use_status"]),
                    allowed_use=_fact(authorization["scope"]),
                    price_adjustment=_fact(review["price_adjustment"]),
                    currency=_fact(review["currency"]),
                    volume_unit=_fact(review["volume_unit"]),
                    dividend_unit=_fact(review["dividend_unit"]),
                    action_coverage=_fact(review["action_coverage_status"]),
                ),
                review_hashes=ReviewHashes(
                    action_coverage_sha256=review["action_coverage_sha256"],
                    field_semantics_sha256=review["field_semantics_sha256"],
                    independent_input_review_sha256=approval.independent_input_review_sha256,
                ),
            )
            value = cls(
                snapshot_digest=descriptor["freeze_digest"],
                protocol_bytes=store.get_bytes(protocol_ref),
                bars_csv=store.get_bytes(
                    ObjectRef.model_validate(frozen["members"]["normalized-bars.csv"])
                ),
                distributions_json=store.get_bytes(
                    ObjectRef.model_validate(frozen["members"]["normalized-distributions.json"])
                ),
                frozen_at_utc=datetime.fromisoformat(frozen["frozen_at_utc"]),
                evidence_kind="reviewed_opend_freeze_v2",
                source_root=root,
                provenance=provenance,
            )
            value.verified()
            return value
        except Exception:
            raise ReplayError("input_not_qualified") from None

    @classmethod
    def _from_v3_descriptor(cls, descriptor):
        if set(descriptor) != {"schema_version", "freeze_root", "freeze_digest", "acceptance"}:
            raise ValueError("v3_descriptor_invalid")
        root = Path(descriptor["freeze_root"]).absolute()
        _safe(root)
        freezer, store = _freezer(), ObjectStore(root)
        frozen = freezer.reopen_freeze(root, descriptor["freeze_digest"], policy_exception=True)
        if frozen["schema_id"] != "qm.spy-daily.freeze.v3.policy-exception-once":
            raise ValueError("v3_descriptor_invalid")
        acceptance_ref = ObjectRef.model_validate(descriptor["acceptance"])
        if acceptance_ref.byte_length > once.MAX_PROOF:
            raise ValueError
        acceptance = _AcceptanceV3.model_validate(
            once.loads(once.read_object(store, acceptance_ref))
        )
        binding = once.verify_authority(frozen["policy_exception"], store)
        protocol_ref = ObjectRef.model_validate(frozen["protocol_ref"])
        members = frozen["members"]
        if (
            acceptance.snapshot_digest != descriptor["freeze_digest"]
            or acceptance.protocol_digest != protocol_ref.digest
            or acceptance.reviewed_at_utc < datetime.fromisoformat(frozen["frozen_at_utc"])
            or acceptance.use_document_sha256 != binding.policy_document_ref.digest
            or acceptance.authorization_sha256 != members["capture-authorization.json"]["digest"]
            or acceptance.post_review_sha256 != members["post-review.json"]["digest"]
            or acceptance.policy_exception != binding
            or acceptance.capture_intent_ref.model_dump(mode="json") != frozen["capture_intent_ref"]
        ):
            raise ValueError("acceptance_binding_invalid")
        raw = _json(once.read_object(store, members["raw-capture.json"], limit=freezer.MAX_BYTES))
        review = _json(once.read_object(store, members["post-review.json"]))
        freeze_probe = ObjectRef(
            digest=descriptor["freeze_digest"], byte_length=0, media_type="application/json"
        )
        freeze_ref = freeze_probe.model_copy(
            update={"byte_length": store.path_for(freeze_probe).stat().st_size}
        )
        proofs = {
            name: ObjectRef.model_validate(members[name])
            for name in (
                "human-approval.json",
                "source-use-policy.md",
                "capture-intent.json",
                "capture-authorization.json",
                "post-review.json",
            )
        }
        proofs.update(
            {
                "acceptance.json": acceptance_ref,
                "freeze.json": freeze_ref,
                "protocol.json": protocol_ref,
            }
        )
        provenance = SampleProvenance(
            times=EvidenceTimes(
                requested_at_utc=_fact(raw["requested_at_utc"]),
                received_at_utc=_fact(raw["received_at_utc"]),
                post_reviewed_at_utc=_fact(review["reviewed_at_utc"]),
                acceptance_reviewed_at_utc=_fact(acceptance.reviewed_at_utc.isoformat()),
                available_at_utc=_fact(status="unknown", reason="not_established_by_receipts"),
            ),
            refs=EvidenceRefs(
                freeze=freeze_ref,
                acceptance=acceptance_ref,
                raw_capture=ObjectRef.model_validate(members["raw-capture.json"]),
                authorization=ObjectRef.model_validate(members["capture-authorization.json"]),
                post_review=ObjectRef.model_validate(members["post-review.json"]),
            ),
            source_facts=SourceFacts(
                source_use=_fact("POLICY_EXCEPTION_ONCE"),
                allowed_use=_fact(binding.scope),
                price_adjustment=_fact(review["price_adjustment"]),
                currency=_fact(review["currency"]),
                volume_unit=_fact(review["volume_unit"]),
                dividend_unit=_fact(review["dividend_unit"]),
                action_coverage=_fact(review["action_coverage_status"]),
            ),
            review_hashes=ReviewHashes(
                action_coverage_sha256=review["action_coverage_sha256"],
                field_semantics_sha256=review["field_semantics_sha256"],
                independent_input_review_sha256=acceptance.independent_input_review_sha256,
            ),
        )
        value = cls(
            snapshot_digest=descriptor["freeze_digest"],
            protocol_bytes=once.read_object(store, protocol_ref, limit=MAX_OBJECT),
            bars_csv=once.read_object(store, members["normalized-bars.csv"], limit=MAX_OBJECT),
            distributions_json=once.read_object(
                store, members["normalized-distributions.json"], limit=MAX_OBJECT
            ),
            frozen_at_utc=datetime.fromisoformat(frozen["frozen_at_utc"]),
            evidence_kind=EXCEPTION_KIND,
            source_root=root,
            provenance=provenance,
            policy_exception=binding,
            capture_intent_ref=acceptance.capture_intent_ref,
            proof_refs=proofs,
        )
        value.verified()
        return value


class _Acceptance(Contract):
    status: Literal["accepted_for_historical_development_replay"]
    scope: Literal["US.SPY/1d/private_research"]
    snapshot_digest: Digest
    protocol_digest: Digest
    use_document_sha256: Digest
    independent_input_review_sha256: Digest
    reviewed_at_utc: datetime

    @model_validator(mode="after")
    def real_references(self):
        if any(
            v == "0" * 64 for v in (self.use_document_sha256, self.independent_input_review_sha256)
        ) or self.reviewed_at_utc.utcoffset() != UTC.utcoffset(self.reviewed_at_utc):
            raise ValueError("acceptance evidence invalid")
        return self


class _AcceptanceV3(_Acceptance):
    schema_version: Literal[3]
    status: Literal["accepted_for_policy_exception_historical_diagnostic"]
    authorization_sha256: Digest
    post_review_sha256: Digest
    policy_exception: once.OnceBinding
    capture_intent_ref: ObjectRef


class ReplayService:
    """One writer, one bounded synchronous computation; no automatic rerun."""

    def __init__(self, root: Path, *, replay_input: ReplayInput | None = None, read_clock=_now):
        self.root = Path(root).absolute()
        _safe(self.root)
        self._condition = threading.Condition(threading.RLock())
        self._inflight = None
        self._closing = self._closed = self._broken = False
        self._input = replay_input
        self._read_clock = read_clock
        if replay_input is not None:
            replay_input.verified()
            if replay_input.source_root is not None:
                source, target = replay_input.source_root.resolve(), self.root.resolve()
                if source == target or source in target.parents or target in source.parents:
                    raise ReplayError("input_not_qualified")
        self.objects = ObjectStore(self.root)
        self._store = JsonlStore(
            self.root,
            filename="jobs.jsonl",
            model=_StoredJob,
            label="SPY replay",
            id_label="job",
            key=lambda j: j.job_id,
        )
        self._lease = WriterLease(self.root / ".writer.lock")
        try:
            jobs = self._records()
            for job in jobs:
                self._verify(job)
            changed = [
                self._updated(j, state="interrupted", error_code="interrupted", completed_at=_now())
                if j.state == "running"
                else j
                for j in jobs
            ]
            if changed != jobs:
                self._store.write(changed)
        except BaseException:
            self._lease.close()
            raise

    def _records(self):
        try:
            self._lease.validate()
        except Exception:
            raise ReplayError("service_unavailable") from None
        _safe(self._store.path)
        if self._store.path.exists() and self._store.path.stat().st_size > 256 * 1024:
            raise ReplayError("artifact_invalid")
        try:
            jobs = self._store.read()
        except (ValueError, OSError):
            raise ReplayError("artifact_invalid") from None
        if len(jobs) > MAX_JOBS:
            raise ReplayError("artifact_invalid")
        return jobs

    @staticmethod
    def _updated(job, **changes):
        return _StoredJob.model_validate({**job.model_dump(), "updated_at": _now(), **changes})

    @staticmethod
    def _public(job):
        return ReplayJob.model_validate(job.model_dump(exclude={"implementation_digest"}))

    def _object(self, ref):
        path = self.objects.path_for(ref)
        _safe(path)
        if not 1 <= ref.byte_length <= MAX_OBJECT or path.stat().st_size != ref.byte_length:
            raise ReplayError("artifact_invalid")
        return self.objects.get_bytes(ref)

    def _verify(self, job):
        try:
            if job.report is not None:
                report = _json(self._object(job.report))
                expected = dict(
                    job_id=job.job_id,
                    request_digest=job.request_digest,
                    **job.request.model_dump(),
                    implementation_digest=job.implementation_digest,
                    financial_qualification="INSUFFICIENT",
                    paper_allowed=False,
                )
                if any(report.get(k) != v for k, v in expected.items()):
                    raise ValueError
                version = report.get("schema_version")
                if type(version) is not int or version not in {1, 2, 3}:
                    raise ValueError("unsupported report version")
                if version == 1:
                    if "sample_evidence" in report:
                        raise ValueError("legacy evidence cannot be backfilled")
                else:
                    evidence = (
                        ExceptionSampleEvidence if version == 3 else SampleEvidence
                    ).model_validate(report["sample_evidence"])
                    if (
                        evidence.snapshot_digest,
                        evidence.protocol_digest,
                        evidence.evidence_kind,
                        evidence.as_of_utc,
                        evidence.calendar.calendar_version,
                        evidence.calendar.last_session,
                        evidence.calendar.source_grace_minutes,
                    ) != (
                        job.request.snapshot_digest,
                        job.request.protocol_digest,
                        report["evidence_kind"],
                        report["window"]["as_of_utc"],
                        report["window"]["calendar_version"],
                        report["window"]["score_end"],
                        report["window"]["source_grace_minutes"],
                    ):
                        raise ValueError("sample evidence binding mismatch")
                    if version == 3:
                        self._verify_exception(job, evidence, report)
            if job.decision_ref is not None and self._object(job.decision_ref) != canonical(
                job.decision.model_dump(mode="json")
            ):
                raise ValueError
        except Exception:
            raise ReplayError("artifact_invalid") from None

    def _verify_exception(self, job, evidence, report):
        """Verify thin original proof objects without current input, prices or math."""
        b, refs = evidence.policy_exception, evidence.proof_refs
        once.verify_authority(b, self.objects)
        proof = {
            name: once.read_object(
                self.objects,
                ref,
                limit=MAX_OBJECT if name in {"protocol.json", "freeze.json"} else once.MAX_PROOF,
            )
            for name, ref in refs.items()
        }
        frozen, protocol, auth, review = (
            _json(proof[name])
            for name in (
                "freeze.json",
                "protocol.json",
                "capture-authorization.json",
                "post-review.json",
            )
        )
        acceptance = _AcceptanceV3.model_validate(once.loads(proof["acceptance.json"]))
        if (
            job.job_id != b.job_idempotency_key
            or evidence.snapshot_digest != refs["freeze.json"].digest
            or evidence.protocol_digest != refs["protocol.json"].digest
            or evidence.refs.freeze != refs["freeze.json"]
            or evidence.refs.acceptance != refs["acceptance.json"]
            or evidence.refs.authorization != refs["capture-authorization.json"]
            or evidence.refs.post_review != refs["post-review.json"]
            or refs["human-approval.json"] != b.human_approval_ref
            or refs["source-use-policy.md"] != b.policy_document_ref
            or refs["capture-intent.json"] != evidence.capture_intent_ref
            or frozen.get("schema_id") != "qm.spy-daily.freeze.v3.policy-exception-once"
            or frozen.get("policy_exception") != b.model_dump(mode="json")
            or frozen.get("capture_intent_ref")
            != evidence.capture_intent_ref.model_dump(mode="json")
            or frozen.get("protocol_ref") != refs["protocol.json"].model_dump(mode="json")
            or frozen.get("members") != protocol.get("members")
            or acceptance.policy_exception != b
            or acceptance.capture_intent_ref != evidence.capture_intent_ref
            or acceptance.snapshot_digest != evidence.snapshot_digest
            or acceptance.protocol_digest != evidence.protocol_digest
            or acceptance.use_document_sha256 != b.policy_document_ref.digest
            or acceptance.authorization_sha256 != refs["capture-authorization.json"].digest
            or acceptance.post_review_sha256 != refs["post-review.json"].digest
            or acceptance.independent_input_review_sha256
            != evidence.review_hashes.independent_input_review_sha256
        ):
            raise ValueError("exception_report_binding_invalid")
        freezer = _freezer()
        as_of = datetime.fromisoformat(protocol["window"]["as_of_utc"])
        requested = datetime.fromisoformat(evidence.times.requested_at_utc.value)
        checked_auth = freezer._authorization(auth, as_of, requested, proof_store=self.objects)
        checked_review = freezer._post_review_v3(review)
        expected_facts = SourceFacts(
            source_use=_fact("POLICY_EXCEPTION_ONCE"),
            allowed_use=_fact(b.scope),
            price_adjustment=_fact(checked_review["price_adjustment"]),
            currency=_fact(checked_review["currency"]),
            volume_unit=_fact(checked_review["volume_unit"]),
            dividend_unit=_fact(checked_review["dividend_unit"]),
            action_coverage=_fact(checked_review["action_coverage_status"]),
        )
        if (
            report["window"] != protocol["window"]
            or report["costs"] != protocol["costs"]
            or evidence.as_of_utc != protocol["window"]["as_of_utc"]
            or datetime.fromisoformat(evidence.frozen_at_utc)
            != datetime.fromisoformat(frozen["frozen_at_utc"])
            or evidence.source_facts != expected_facts
            or evidence.calendar
            != SampleCalendar(
                calendar_version=protocol["window"]["calendar_version"],
                last_session=protocol["window"]["score_end"],
            )
        ):
            raise ValueError("exception_displayed_facts_invalid")
        marker = once.verify_intent(b, checked_auth, evidence.capture_intent_ref, self.objects)
        members = frozen["members"]
        if (
            checked_review["policy_exception"] != b.model_dump(mode="json")
            or checked_review["authorization_sha256"] != refs["capture-authorization.json"].digest
            or checked_review["capture_sha256"] != evidence.refs.raw_capture.digest
            or checked_review["capture_intent_ref"]
            != evidence.capture_intent_ref.model_dump(mode="json")
            or members["raw-capture.json"] != evidence.refs.raw_capture.model_dump(mode="json")
            or any(
                members[name] != refs[name].model_dump(mode="json")
                for name in (
                    "capture-authorization.json",
                    "post-review.json",
                    "human-approval.json",
                    "source-use-policy.md",
                    "capture-intent.json",
                )
            )
            or members["normalized-bars.csv"]
            != evidence.refs.normalized_bars.model_dump(mode="json")
            or members["normalized-distributions.json"]
            != evidence.refs.distributions.model_dump(mode="json")
            or checked_review["action_coverage_sha256"]
            != evidence.review_hashes.action_coverage_sha256
            or checked_review["field_semantics_sha256"]
            != evidence.review_hashes.field_semantics_sha256
            or not as_of
            <= datetime.fromisoformat(marker["consumed_at_utc"])
            <= requested
            <= datetime.fromisoformat(evidence.times.received_at_utc.value)
            <= datetime.fromisoformat(review["reviewed_at_utc"])
            <= datetime.fromisoformat(frozen["frozen_at_utc"])
            <= acceptance.reviewed_at_utc
            or datetime.fromisoformat(frozen["frozen_at_utc"])
            - datetime.fromisoformat(review["reviewed_at_utc"])
            > timedelta(minutes=30)
            or evidence.times.post_reviewed_at_utc.value != review["reviewed_at_utc"]
            or datetime.fromisoformat(evidence.times.acceptance_reviewed_at_utc.value)
            != acceptance.reviewed_at_utc
            or evidence.source_facts.source_use.value != "POLICY_EXCEPTION_ONCE"
            or evidence.source_facts.pit.status != "unknown"
            or evidence.source_facts.revision_status.status != "unknown"
        ):
            raise ValueError("exception_report_proof_invalid")
        expected = freezer._protocol_v3(
            protocol["window"],
            b.model_dump(mode="json"),
            evidence.capture_intent_ref.model_dump(mode="json"),
            normalization=freezer._normalization_metadata(checked_review),
        )
        for key in (
            "runtime",
            "normalizer_sha256",
            "source_code_sha256",
            "policy_binding_code_sha256",
        ):
            expected[key] = protocol[key]
        expected["members"] = members
        if protocol != expected or freezer._digest(protocol["window"]) != b.window_sha256:
            raise ValueError("exception_protocol_invalid")

    def _find(self, key):
        job = next((j for j in self._records() if j.job_id == _uuid(key)), None)
        if job is None:
            raise ReplayError("not_found")
        self._verify(job)
        return job

    def _replace(self, job):
        jobs = self._records()
        self._store.write([job if j.job_id == job.job_id else j for j in jobs])

    def options(self):
        return ReplayOptions(
            configured=False,
            unavailable_reason="input_not_qualified",
            input=None,
        )

    def get(self, key):
        with self._condition:
            return self._public(self._find(key))

    def read(self, key):
        with self._condition:
            job = self._find(key)
            report = _json(self._object(job.report)) if job.report is not None else None
            return ReplayJobRead(
                **self._public(job).model_dump(),
                sample_freshness_view=sample_freshness_view(
                    report, job.request.snapshot_digest, self._read_clock()
                ),
            )

    def submit(self, request: ReplayRequest, key):
        request = ReplayRequest.model_validate(request.model_dump())
        key = _uuid(key)
        request_digest = digest(canonical(request.model_dump()))
        with self._condition:
            if self._closing or self._broken:
                raise ReplayError("service_closed")
            jobs = self._records()
            existing = next((j for j in jobs if j.job_id == key), None)
            if existing is not None:
                if existing.request_digest != request_digest:
                    raise ReplayError("idempotency_conflict")
                self._verify(existing)
                return self._public(existing), False
            # Retired execution profile: original IDs and bytes stay readable,
            # but no old/once input can run under the versioned quantity kernel.
            raise ReplayError("input_not_qualified")

    def artifact(self, key, kind="report"):
        with self._condition:
            job = self._find(key)
            if kind not in {"report", "decision"}:
                raise ReplayError("invalid_request")
            ref = job.report if kind == "report" else job.decision_ref
            if ref is None:
                raise ReplayError("not_found")
            return self._object(ref)

    def decide(self, key, body: DecisionRequest, decision_key):
        body = DecisionRequest.model_validate(body.model_dump())
        decision_key = _uuid(decision_key)
        with self._condition:
            if self._closing or self._broken:
                raise ReplayError("service_closed")
            job = self._find(key)
            if job.state != "succeeded":
                raise ReplayError("job_not_succeeded")
            if body.request_digest != job.request_digest or body.report_digest != job.report.digest:
                raise ReplayError("decision_conflict")
            if job.decision is not None:
                existing = job.decision.model_dump(include=set(DecisionRequest.model_fields))
                if job.decision.decision_key != decision_key or existing != body.model_dump():
                    raise ReplayError("decision_conflict")
                return self._public(job), False
            decision = ReplayDecision(
                **body.model_dump(),
                decision_key=decision_key,
                job_id=job.job_id,
                **job.request.model_dump(),
                created_at=_now(),
            )
            ref = self.objects.put_bytes(
                "application/json", canonical(decision.model_dump(mode="json"))
            )
            completed = self._updated(job, decision=decision, decision_ref=ref)
            self._verify(completed)
            self._replace(completed)
            return self._public(completed), True

    def close(self):
        with self._condition:
            self._closing = True
            while self._inflight is not None:
                self._condition.wait()
            if not self._closed:
                self._lease.close()
                self._closed = True
