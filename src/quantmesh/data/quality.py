"""Versioned quality policies and immutable evaluation evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from quantmesh.data.adjustments import EquitySplitAction
from quantmesh.data.artifacts import (
    ArtifactDataset,
    ArtifactLayer,
    ArtifactManifest,
    ManifestIntegrityError,
    ManifestStore,
    canonical_json_bytes,
)
from quantmesh.data.calendars import CalendarService, SessionPolicy
from quantmesh.data.capabilities import DataKind, EntitlementState
from quantmesh.data.envelopes import ProvenanceClass, RawEnvelope
from quantmesh.data.objects import FABRIC_NAMESPACE, ObjectIntegrityError, ObjectRef, ObjectStore
from quantmesh.domain.market_data import interval_to_timedelta
from quantmesh.domain.models import Venue


class QualityFailure(ValueError):
    """A candidate contains evidence that cannot qualify as real data."""


class QualityIntegrityError(ValueError):
    """Immutable quality evidence is missing, changed or internally inconsistent."""


class QualityStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_DUE = "not-due"
    UNAVAILABLE = "unavailable"


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


class QualityPolicy(_FrozenContract):
    """One content-addressed SLA for a venue/data-kind/calendar tuple."""

    contract: str = Field(default="quality-policy-v1", pattern=r"^quality-policy-v1$")
    venue: Venue
    layer: ArtifactLayer
    data_kind: DataKind
    interval: str | None = None
    calendar_version: str = Field(min_length=1)
    session_policy: SessionPolicy
    grace_period_seconds: int = Field(ge=0)
    minimum_coverage_ratio: float = Field(ge=1.0, le=1.0)
    max_freshness_seconds: int = Field(ge=0)
    max_latency_seconds: int = Field(ge=0)
    require_terminal_pagination: bool

    @model_validator(mode="after")
    def target_is_consistent(self) -> Self:
        if self.venue not in {Venue.MOOMOO, Venue.HYPERLIQUID}:
            raise ValueError("quality policy venue is outside the trusted-data scope")
        if self.data_kind is DataKind.BARS:
            if self.interval is None:
                raise ValueError("bar quality policies require an interval")
            interval_to_timedelta(self.interval)
        elif self.interval is not None:
            raise ValueError("only bar quality policies declare an interval")
        expected = (
            ("exchange-calendars:", SessionPolicy.REGULAR)
            if self.venue is Venue.MOOMOO
            else ("quantmesh:", SessionPolicy.CONTINUOUS)
        )
        if (
            not self.calendar_version.startswith(expected[0])
            or self.session_policy is not expected[1]
        ):
            raise ValueError("quality policy venue, calendar and session disagree")
        return self

    def identity_body(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"policy_id"})

    @computed_field
    @property
    def policy_id(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.identity_body())).hexdigest()


class QualityObservation(_FrozenContract):
    """Exact measured numerators and integrity counts for one evaluation."""

    evaluated_at: datetime
    expected_count: int = Field(ge=0)
    observed_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    hash_mismatch_count: int = Field(ge=0)
    schema_mismatch_count: int = Field(ge=0)
    order_violation_count: int = Field(ge=0)
    overlap_conflict_count: int = Field(ge=0)
    overlap_conflict_fingerprints: tuple[str, ...] = ()
    synthetic_row_count: int = Field(ge=0)
    pagination_terminal: bool | None
    source_rights_known: bool
    entitlement: EntitlementState
    freshness_seconds: int | None = Field(default=None, ge=0)
    latency_seconds: int | None = Field(default=None, ge=0)
    unavailable_reason: str | None = None

    @field_validator("evaluated_at")
    @classmethod
    def evaluation_time_is_utc(cls, value: datetime) -> datetime:
        if not _is_utc(value):
            raise ValueError("evaluated_at must be UTC")
        return value

    @field_validator("unavailable_reason")
    @classmethod
    def unavailable_reason_is_not_blank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("unavailable_reason must not be blank")
        return value

    @field_validator("overlap_conflict_fingerprints")
    @classmethod
    def overlap_fingerprints_are_canonical(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))) or any(
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            for value in values
        ):
            raise ValueError("overlap conflict fingerprints must be canonical digests")
        return values

    @model_validator(mode="after")
    def overlap_count_matches_fingerprints(self) -> Self:
        if self.overlap_conflict_count != len(self.overlap_conflict_fingerprints):
            raise ValueError("overlap conflict count and fingerprints disagree")
        return self


class QualityDecision(_FrozenContract):
    status: QualityStatus
    issue_codes: tuple[str, ...]
    expected_count: int = Field(ge=0)


class QualityEvaluation(_FrozenContract):
    """Immutable exact result; amendments append and never replace evidence."""

    contract: str = Field(default="quality-evaluation-v1", pattern=r"^quality-evaluation-v1$")
    evaluation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    window_start: datetime
    window_end: datetime
    evaluated_at: datetime
    status: QualityStatus
    expected_count: int = Field(ge=0)
    reported_expected_count: int = Field(ge=0)
    observed_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    hash_mismatch_count: int = Field(ge=0)
    schema_mismatch_count: int = Field(ge=0)
    order_violation_count: int = Field(ge=0)
    overlap_conflict_count: int = Field(ge=0)
    overlap_conflict_fingerprints: tuple[str, ...] = ()
    synthetic_row_count: int = Field(ge=0)
    coverage_numerator: int = Field(ge=0)
    coverage_denominator: int = Field(ge=0)
    grace_period_seconds: int = Field(ge=0)
    freshness_seconds: int | None = Field(default=None, ge=0)
    latency_seconds: int | None = Field(default=None, ge=0)
    pagination_terminal: bool | None
    source_rights_known: bool
    entitlement: EntitlementState
    unavailable_reason: str | None = None
    issue_codes: tuple[str, ...]
    amends: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    amendment_reason: str | None = None

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = _QualityEvaluationBody.model_validate(values)
        payload = canonical_json_bytes(body.model_dump(mode="json"))
        return cls(
            **body.model_dump(),
            evaluation_id=hashlib.sha256(payload).hexdigest(),
        )

    @field_validator("window_start", "window_end", "evaluated_at")
    @classmethod
    def times_are_utc(cls, value: datetime, info) -> datetime:
        if not _is_utc(value):
            raise ValueError(f"{info.field_name} must be UTC")
        return value

    @field_validator("issue_codes")
    @classmethod
    def issues_are_canonical(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(set(values))) != values or any(not value.strip() for value in values):
            raise ValueError("issue codes must be sorted, unique and nonblank")
        return values

    @field_validator("overlap_conflict_fingerprints")
    @classmethod
    def overlap_fingerprints_are_canonical(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if values != tuple(sorted(set(values))) or any(
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            for value in values
        ):
            raise ValueError("overlap conflict fingerprints must be canonical digests")
        return values

    @field_validator("unavailable_reason", "amendment_reason")
    @classmethod
    def optional_reason_is_not_blank(cls, value: str | None, info) -> str | None:
        if value is not None and not value.strip():
            raise ValueError(f"{info.field_name.replace('_', ' ')} must not be blank")
        return value

    @model_validator(mode="after")
    def identity_and_window_are_valid(self) -> Self:
        _validate_evaluation_semantics(self)
        body = self.model_dump(mode="json", exclude={"evaluation_id"})
        actual = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
        if actual != self.evaluation_id:
            raise ValueError(
                f"evaluation_id mismatch: expected {self.evaluation_id}, observed {actual}"
            )
        return self

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json", exclude={"evaluation_id"}))


class _QualityEvaluationBody(QualityEvaluation):
    evaluation_id: str = Field(default="0" * 64, exclude=True)

    @model_validator(mode="after")
    def identity_and_window_are_valid(self) -> Self:
        _validate_evaluation_semantics(self)
        return self


def _validate_evaluation_semantics(evaluation: QualityEvaluation) -> None:
    """Reject self-addressed bodies whose exact fields disagree."""
    if evaluation.window_end <= evaluation.window_start:
        raise ValueError("quality window must have positive duration")
    if evaluation.evaluated_at < evaluation.window_start:
        raise ValueError("evaluation cannot precede its window")
    if evaluation.coverage_numerator != evaluation.observed_count:
        raise ValueError("coverage numerator must equal observed count")
    if evaluation.coverage_denominator != evaluation.expected_count:
        raise ValueError("coverage denominator must equal expected count")
    if evaluation.overlap_conflict_count != len(evaluation.overlap_conflict_fingerprints):
        raise ValueError("overlap conflict count and fingerprints disagree")
    if (evaluation.status is QualityStatus.PASS) != (not evaluation.issue_codes):
        raise ValueError("quality status and issues disagree")
    if (evaluation.unavailable_reason is not None) != (
        "provider-unavailable" in evaluation.issue_codes
    ):
        raise ValueError("provider unavailability reason and issue disagree")
    if (evaluation.amends is None) != (evaluation.amendment_reason is None):
        raise ValueError("quality amendment requires both target and reason")


class QualityBinding(_FrozenContract):
    manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_id: str = Field(pattern=r"^[0-9a-f]{64}$")


class QualityReport(_FrozenContract):
    """One immutable manifest-to-evaluation bundle bound by a later checkpoint."""

    contract: str = Field(default="quality-report-v1", pattern=r"^quality-report-v1$")
    report_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    job_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_body_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    bindings: tuple[QualityBinding, ...] = Field(min_length=1)

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = _QualityReportBody.model_validate(values)
        payload = canonical_json_bytes(body.model_dump(mode="json"))
        return cls(
            **body.model_dump(),
            report_id=hashlib.sha256(payload).hexdigest(),
        )

    @model_validator(mode="after")
    def identity_and_bindings_are_valid(self) -> Self:
        identities = [item.manifest_id for item in self.bindings]
        evaluations = [item.evaluation_id for item in self.bindings]
        if len(identities) != len(set(identities)) or len(evaluations) != len(set(evaluations)):
            raise ValueError("quality report bindings must be one-to-one")
        if self.bindings != tuple(
            sorted(self.bindings, key=lambda item: (item.manifest_id, item.evaluation_id))
        ):
            raise ValueError("quality report bindings must use canonical order")
        actual = hashlib.sha256(
            canonical_json_bytes(self.model_dump(mode="json", exclude={"report_id"}))
        ).hexdigest()
        if actual != self.report_id:
            raise ValueError("quality report ID disagrees with its canonical body")
        return self

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json", exclude={"report_id"}))


class _QualityReportBody(QualityReport):
    report_id: str = Field(default="0" * 64, exclude=True)

    @model_validator(mode="after")
    def identity_and_bindings_are_valid(self) -> Self:
        identities = [item.manifest_id for item in self.bindings]
        evaluations = [item.evaluation_id for item in self.bindings]
        if len(identities) != len(set(identities)) or len(evaluations) != len(set(evaluations)):
            raise ValueError("quality report bindings must be one-to-one")
        if self.bindings != tuple(
            sorted(self.bindings, key=lambda item: (item.manifest_id, item.evaluation_id))
        ):
            raise ValueError("quality report bindings must use canonical order")
        return self


class QualityEvidenceStore:
    """Persist policy/evaluation bodies in the existing immutable object store."""

    _POLICY_MEDIA = "application/vnd.quantmesh.quality-policy+json"
    _EVALUATION_MEDIA = "application/vnd.quantmesh.quality-evaluation+json"
    _REPORT_MEDIA = "application/vnd.quantmesh.quality-report+json"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.objects = ObjectStore(self.root)
        self.manifests = ManifestStore(self.root)

    def record_policy(self, policy: QualityPolicy) -> str:
        reference = self.objects.put_bytes(
            self._POLICY_MEDIA, canonical_json_bytes(policy.identity_body())
        )
        if reference.digest != policy.policy_id:
            raise QualityIntegrityError("quality policy identity changed while recording")
        return policy.policy_id

    def load_policy(self, policy_id: str) -> QualityPolicy:
        path = self.path_for(policy_id)
        try:
            size = path.lstat().st_size
            payload = self.objects.get_bytes(
                ObjectRef(
                    digest=policy_id,
                    media_type=self._POLICY_MEDIA,
                    byte_length=size,
                )
            )
            policy = QualityPolicy.model_validate_json(payload)
        except (
            ObjectIntegrityError,
            OSError,
            TypeError,
            ValueError,
        ) as error:
            raise QualityIntegrityError(
                f"quality policy hash or body is invalid for {policy_id}"
            ) from error
        if policy.policy_id != policy_id:
            raise QualityIntegrityError("quality policy identity disagrees with its path")
        return policy

    def record(
        self,
        evaluation: QualityEvaluation,
        *,
        admitted_manifest_ids: frozenset[str] = frozenset(),
    ) -> QualityEvaluation:
        self._verify_evaluation(
            evaluation,
            admitted_manifest_ids=admitted_manifest_ids,
        )
        reference = self.objects.put_bytes(self._EVALUATION_MEDIA, evaluation.canonical_bytes())
        if reference.digest != evaluation.evaluation_id:
            raise QualityIntegrityError("quality evaluation identity changed while recording")
        return evaluation

    def _verify_evaluation(
        self,
        evaluation: QualityEvaluation,
        *,
        admitted_manifest_ids: frozenset[str],
        seen: frozenset[str] = frozenset(),
    ) -> None:
        if evaluation.evaluation_id in seen:
            raise QualityIntegrityError("quality amendment chain contains a cycle")
        policy = self.load_policy(evaluation.policy_id)
        evaluator = QualityEvaluator(self.manifests)
        manifest = evaluator.require_admitted_manifest(
            evaluation.manifest_id,
            admitted_manifest_ids=admitted_manifest_ids,
        )
        evaluator.validate_lineage(
            manifest,
            _observation_from_evaluation(evaluation),
            admitted_manifest_ids=admitted_manifest_ids,
        )
        evaluator._validate_target(policy, manifest)
        measured = evaluator.measure(
            policy,
            evaluation.manifest_id,
            window_start=evaluation.window_start,
            window_end=evaluation.window_end,
            evaluated_at=evaluation.evaluated_at,
            admitted_manifest_ids=admitted_manifest_ids,
        )
        if measured != _observation_from_evaluation(evaluation):
            raise QualityIntegrityError(
                "quality evaluation measurements disagree with immutable evidence"
            )
        decision = evaluator.evaluate_status(
            policy,
            window_start=evaluation.window_start,
            window_end=evaluation.window_end,
            observation=_observation_from_evaluation(evaluation),
            reconciles_overlap=(
                evaluation.amends is not None and evaluation.amendment_reason is not None
            ),
        )
        if (
            decision.status,
            decision.issue_codes,
            decision.expected_count,
        ) != (
            evaluation.status,
            evaluation.issue_codes,
            evaluation.expected_count,
        ):
            raise QualityIntegrityError("quality evaluation disagrees with its policy")
        if evaluation.amends is not None:
            try:
                previous = self.load(evaluation.amends)
            except QualityIntegrityError as error:
                raise QualityIntegrityError("quality amendment target is missing") from error
            previous_manifest = self.manifests.open(previous.manifest_id).manifest
            current_manifest = self.manifests.open(evaluation.manifest_id).manifest
            if (
                previous.policy_id,
                previous_manifest.dataset_id,
                previous.window_start,
                previous.window_end,
            ) != (
                evaluation.policy_id,
                current_manifest.dataset_id,
                evaluation.window_start,
                evaluation.window_end,
            ):
                raise QualityIntegrityError("quality amendment target does not match")
            if evaluation.evaluated_at <= previous.evaluated_at:
                raise QualityIntegrityError("quality amendment time must advance")
            if evaluation.overlap_conflict_count and (
                "historical-live-overlap" not in previous.issue_codes
                or evaluation.overlap_conflict_fingerprints
                != previous.overlap_conflict_fingerprints
            ):
                raise QualityIntegrityError(
                    "overlap reconciliation must match the exact prior conflict set"
                )
            self._verify_evaluation(
                previous,
                admitted_manifest_ids=admitted_manifest_ids,
                seen=seen | {evaluation.evaluation_id},
            )

    def path_for(self, evaluation_id: str) -> Path:
        if len(evaluation_id) != 64 or any(
            char not in "0123456789abcdef" for char in evaluation_id
        ):
            raise ValueError("evaluation_id must be a lowercase SHA-256 digest")
        return (
            self.root / FABRIC_NAMESPACE / "objects" / "sha256" / evaluation_id[:2] / evaluation_id
        )

    def load(self, evaluation_id: str) -> QualityEvaluation:
        path = self.path_for(evaluation_id)
        try:
            size = path.lstat().st_size
            payload = self.objects.get_bytes(
                ObjectRef(
                    digest=evaluation_id,
                    media_type=self._EVALUATION_MEDIA,
                    byte_length=size,
                )
            )
            body = _QualityEvaluationBody.model_validate_json(payload)
            evaluation = QualityEvaluation.build(**body.model_dump(exclude={"evaluation_id"}))
        except (
            ObjectIntegrityError,
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise QualityIntegrityError(
                f"quality evidence hash or body is invalid for {evaluation_id}"
            ) from error
        if evaluation.evaluation_id != evaluation_id:
            raise QualityIntegrityError("quality evidence identity disagrees with its path")
        return evaluation

    def record_report(
        self,
        report: QualityReport,
        *,
        admitted_manifest_ids: frozenset[str] = frozenset(),
    ) -> QualityReport:
        for binding in report.bindings:
            evaluation = self.load(binding.evaluation_id)
            if evaluation.manifest_id != binding.manifest_id:
                raise QualityIntegrityError("quality report binding disagrees with its evaluation")
            self._verify_evaluation(
                evaluation,
                admitted_manifest_ids=admitted_manifest_ids,
            )
        reference = self.objects.put_bytes(self._REPORT_MEDIA, report.canonical_bytes())
        if reference.digest != report.report_id:
            raise QualityIntegrityError("quality report identity changed while recording")
        return report

    def verify_report(
        self,
        report_id: str,
        *,
        admitted_manifest_ids: frozenset[str] = frozenset(),
    ) -> QualityReport:
        """Verify the complete report/evaluation/policy/manifest closure."""
        report = self.load_report(report_id)
        for binding in report.bindings:
            evaluation = self.load(binding.evaluation_id)
            if evaluation.manifest_id != binding.manifest_id:
                raise QualityIntegrityError("quality report binding disagrees with its evaluation")
            self._verify_evaluation(
                evaluation,
                admitted_manifest_ids=admitted_manifest_ids,
            )
        return report

    def verify_report_integrity(self, report_id: str) -> QualityReport:
        """Verify the immutable stored closure without re-running measurements."""
        report = self.load_report(report_id)
        for binding in report.bindings:
            evaluation = self.load(binding.evaluation_id)
            if evaluation.manifest_id != binding.manifest_id:
                raise QualityIntegrityError("quality report binding disagrees with its evaluation")
            self._verify_stored_evaluation_closure(evaluation, seen=frozenset())
        return report

    def _verify_stored_evaluation_closure(
        self,
        evaluation: QualityEvaluation,
        *,
        seen: frozenset[str],
    ) -> None:
        if evaluation.evaluation_id in seen:
            raise QualityIntegrityError("quality amendment chain contains a cycle")
        policy = self.load_policy(evaluation.policy_id)
        manifest = self.manifests.open(evaluation.manifest_id).manifest
        QualityEvaluator._validate_target(policy, manifest)
        if evaluation.amends is not None:
            previous = self.load(evaluation.amends)
            self._verify_stored_evaluation_closure(
                previous,
                seen=seen | {evaluation.evaluation_id},
            )

    def load_report(self, report_id: str) -> QualityReport:
        path = self.path_for(report_id)
        try:
            size = path.lstat().st_size
            payload = self.objects.get_bytes(
                ObjectRef(
                    digest=report_id,
                    media_type=self._REPORT_MEDIA,
                    byte_length=size,
                )
            )
            body = _QualityReportBody.model_validate_json(payload)
            report = QualityReport.build(**body.model_dump(exclude={"report_id"}))
        except (
            ObjectIntegrityError,
            OSError,
            TypeError,
            ValueError,
        ) as error:
            raise QualityIntegrityError(
                f"quality report hash or body is invalid for {report_id}"
            ) from error
        if report.report_id != report_id:
            raise QualityIntegrityError("quality report identity disagrees with its path")
        return report


class QualityEvaluator:
    """Evaluate one committed manifest against one exact versioned policy."""

    def __init__(self, manifests: ManifestStore) -> None:
        self.manifests = manifests

    def evaluate(
        self,
        policy: QualityPolicy,
        manifest_id: str,
        *,
        window_start: datetime,
        window_end: datetime,
        observation: QualityObservation,
        amends: str | None = None,
        amendment_reason: str | None = None,
        admitted_manifest_ids: frozenset[str] = frozenset(),
    ) -> QualityEvaluation:
        manifest = self.require_admitted_manifest(
            manifest_id,
            admitted_manifest_ids=admitted_manifest_ids,
        )
        self._validate_target(policy, manifest)
        self.validate_lineage(
            manifest,
            observation,
            admitted_manifest_ids=admitted_manifest_ids,
        )
        measured = self.measure(
            policy,
            manifest_id,
            window_start=window_start,
            window_end=window_end,
            evaluated_at=observation.evaluated_at,
            admitted_manifest_ids=admitted_manifest_ids,
        )
        if observation != measured:
            raise QualityFailure("quality observation disagrees with immutable manifest evidence")
        observation = measured
        decision = self.evaluate_status(
            policy,
            window_start=window_start,
            window_end=window_end,
            observation=observation,
            reconciles_overlap=amends is not None and amendment_reason is not None,
        )
        return QualityEvaluation.build(
            policy_id=policy.policy_id,
            manifest_id=manifest_id,
            window_start=window_start,
            window_end=window_end,
            evaluated_at=observation.evaluated_at,
            status=decision.status,
            expected_count=decision.expected_count,
            reported_expected_count=observation.expected_count,
            observed_count=observation.observed_count,
            duplicate_count=observation.duplicate_count,
            gap_count=observation.gap_count,
            hash_mismatch_count=observation.hash_mismatch_count,
            schema_mismatch_count=observation.schema_mismatch_count,
            order_violation_count=observation.order_violation_count,
            overlap_conflict_count=observation.overlap_conflict_count,
            overlap_conflict_fingerprints=observation.overlap_conflict_fingerprints,
            synthetic_row_count=observation.synthetic_row_count,
            coverage_numerator=observation.observed_count,
            coverage_denominator=decision.expected_count,
            grace_period_seconds=policy.grace_period_seconds,
            freshness_seconds=observation.freshness_seconds,
            latency_seconds=observation.latency_seconds,
            pagination_terminal=observation.pagination_terminal,
            source_rights_known=observation.source_rights_known,
            entitlement=observation.entitlement,
            unavailable_reason=observation.unavailable_reason,
            issue_codes=decision.issue_codes,
            amends=amends,
            amendment_reason=amendment_reason,
        )

    def measure(
        self,
        policy: QualityPolicy,
        manifest_id: str,
        *,
        window_start: datetime,
        window_end: datetime,
        evaluated_at: datetime,
        admitted_manifest_ids: frozenset[str] = frozenset(),
    ) -> QualityObservation:
        """Derive quality facts from exact manifest/object/envelope evidence."""
        manifest = self.require_admitted_manifest(
            manifest_id,
            admitted_manifest_ids=admitted_manifest_ids,
        )
        self._validate_target(policy, manifest)
        envelopes = self._raw_envelopes(
            manifest,
            admitted_manifest_ids=admitted_manifest_ids,
        )
        for reference in manifest.objects:
            self.manifests.objects.get_bytes(reference)

        timestamps: list[datetime] = []
        if manifest.layer is ArtifactLayer.RAW:
            expected_identities = tuple(
                identity
                for envelope in envelopes
                for identity in envelope.source_event_ids
                if not identity.startswith("empty-response:")
            )
            observed_identities = tuple(
                identity
                for identity in manifest.row_identities
                if not identity.startswith("empty-response:")
            )
            expected_set = set(expected_identities)
            observed_set = set(observed_identities)
            observed_count = len(observed_identities)
            expected_count = len(expected_identities)
            duplicate_count = len(expected_identities) - len(expected_set)
            gap_count = len(expected_set - observed_set) + len(observed_set - expected_set)
            order_violation_count = int(
                expected_set == observed_set and expected_identities != observed_identities
            )
            latest_event = _manifest_event_available_at(manifest, envelopes)
            payload_fingerprints = tuple(
                _raw_payload_fingerprints(envelope, self.manifests.objects)
                for envelope in envelopes
            )
            schema_mismatch_count = int(
                any(envelope.raw_object not in manifest.objects for envelope in envelopes)
                or any(item is None for item in payload_fingerprints)
                or tuple(
                    identity for envelope in envelopes for identity in envelope.source_event_ids
                )
                != manifest.row_identities
            )
        elif manifest.data_kind is DataKind.BARS:
            schema_mismatch_count = 0
            if manifest.layer is ArtifactLayer.FEATURE:
                timestamps = [
                    datetime.fromisoformat(item["timestamp"])
                    for item in ArtifactDataset(
                        manifest, self.manifests.objects, self.manifests
                    ).read_features()
                ]
                if len(manifest.parent_manifest_ids) != 1:
                    raise QualityFailure("feature quality requires one adjusted bar parent")
                parent = self.require_admitted_manifest(
                    manifest.parent_manifest_ids[0],
                    admitted_manifest_ids=admitted_manifest_ids,
                )
                if (
                    parent.layer is not ArtifactLayer.ADJUSTED
                    or parent.data_kind is not DataKind.BARS
                ):
                    raise QualityFailure("feature quality parent must be adjusted bars")
                feature_expected_timestamps = [
                    bar.timestamp
                    for bar in ArtifactDataset(
                        parent, self.manifests.objects, self.manifests
                    ).read_bars()[2:]
                ]
            else:
                timestamps = [
                    bar.timestamp
                    for bar in ArtifactDataset(
                        manifest, self.manifests.objects, self.manifests
                    ).read_bars()
                ]
            if manifest.layer is not ArtifactLayer.RAW:
                timestamps = [item.astimezone(UTC) for item in timestamps]
                observed_timestamps = [
                    item for item in timestamps if window_start <= item < window_end
                ]
                if manifest.layer is ArtifactLayer.FEATURE:
                    expected_timestamps = tuple(
                        item.astimezone(UTC)
                        for item in feature_expected_timestamps
                        if window_start <= item < window_end
                        and _bar_available_at(item, policy=policy) <= evaluated_at
                    )
                else:
                    calendar_id = "XNYS" if policy.venue is Venue.MOOMOO else "24/7"
                    _, expected_timestamps = _scheduled_and_completed_bar_opens(
                        CalendarService(),
                        calendar_id,
                        window_start,
                        window_end,
                        policy=policy,
                        evaluated_at=evaluated_at,
                    )
                expected_set = set(expected_timestamps)
                observed_set = set(observed_timestamps)
                gap_count = len(expected_set - observed_set) + len(observed_set - expected_set)
                duplicate_count = len(observed_timestamps) - len(observed_set)
                order_violation_count = sum(
                    left > right
                    for left, right in zip(observed_timestamps, observed_timestamps[1:])
                )
                observed_count = len(observed_timestamps)
                expected_count = len(expected_timestamps)
                latest_event = max(observed_timestamps, default=None)
                if latest_event is not None:
                    latest_event = _bar_available_at(
                        latest_event,
                        policy=policy,
                    )
        else:
            observed_count = sum(
                not identity.startswith("empty-response:") for identity in manifest.row_identities
            )
            expected_count = 0
            duplicate_count = 0
            gap_count = 0
            order_violation_count = 0
            latest_event = manifest.event_end if observed_count else window_end
            schema_mismatch_count = _nonbar_schema_mismatch(
                manifest,
                self.manifests,
            )

        rights = {item.source_rights_id for item in envelopes}
        entitlements = {item.entitlement for item in envelopes}
        if rights != {manifest.source_rights_id} or entitlements != {manifest.entitlement}:
            raise QualityFailure("manifest rights or entitlement disagree with raw evidence")
        latency_seconds = max(
            max(
                0,
                int(
                    (
                        envelope.received_at - _envelope_available_at(envelope, manifest)
                    ).total_seconds()
                ),
            )
            for envelope in envelopes
        )
        freshness_seconds = (
            None
            if latest_event is None
            else max(0, int((evaluated_at - latest_event).total_seconds()))
        )
        overlap_conflict_fingerprints = self._overlap_conflicts(
            manifest,
            admitted_manifest_ids=admitted_manifest_ids,
        )
        return QualityObservation(
            evaluated_at=evaluated_at,
            expected_count=expected_count,
            observed_count=observed_count,
            duplicate_count=duplicate_count,
            gap_count=gap_count,
            hash_mismatch_count=0,
            schema_mismatch_count=schema_mismatch_count,
            order_violation_count=order_violation_count,
            overlap_conflict_count=len(overlap_conflict_fingerprints),
            overlap_conflict_fingerprints=overlap_conflict_fingerprints,
            synthetic_row_count=0,
            pagination_terminal=all(_pagination_is_terminal(item.cursor) for item in envelopes),
            source_rights_known=bool(rights) and all(item.strip() for item in rights),
            entitlement=manifest.entitlement,
            freshness_seconds=freshness_seconds,
            latency_seconds=latency_seconds,
            unavailable_reason=None,
        )

    def _overlap_conflicts(
        self,
        manifest: ArtifactManifest,
        *,
        admitted_manifest_ids: frozenset[str],
    ) -> tuple[str, ...]:
        previous = [
            candidate
            for candidate in (
                self.manifests.open(manifest_id).manifest
                for manifest_id in admitted_manifest_ids
                if manifest_id != manifest.manifest_id
            )
            if candidate.dataset_id == manifest.dataset_id
            and candidate.compatibility_revision < manifest.compatibility_revision
            and candidate.knowledge_end <= manifest.knowledge_start
        ]
        if not previous:
            return ()
        predecessor = max(
            previous,
            key=lambda item: (
                item.compatibility_revision,
                item.knowledge_end,
                item.manifest_id,
            ),
        )
        current_rows = self._row_fingerprints(manifest)
        previous_rows = self._row_fingerprints(predecessor)
        return tuple(
            sorted(
                hashlib.sha256(
                    canonical_json_bytes(
                        {
                            "current": fingerprint,
                            "identity": identity,
                            "previous": previous_rows[identity],
                        }
                    )
                ).hexdigest()
                for identity, fingerprint in current_rows.items()
                if identity in previous_rows and previous_rows[identity] != fingerprint
            )
        )

    def _row_fingerprints(self, manifest: ArtifactManifest) -> dict[str, str]:
        dataset = ArtifactDataset(manifest, self.manifests.objects, self.manifests)
        if manifest.layer is ArtifactLayer.RAW:
            result: dict[str, str] = {}
            for reference in manifest.objects:
                if reference.media_type != "application/vnd.quantmesh.raw-envelope+json":
                    continue
                envelope = RawEnvelope.model_validate_json(
                    self.manifests.objects.get_bytes(reference)
                )
                fingerprints = _raw_payload_fingerprints(envelope, self.manifests.objects)
                if fingerprints is not None:
                    result.update(fingerprints)
            return result
        if manifest.data_kind is DataKind.BARS:
            rows: tuple[Any, ...]
            if manifest.layer is ArtifactLayer.FEATURE:
                rows = dataset.read_features()
            else:
                rows = dataset.read_bars()
            return {
                identity: hashlib.sha256(
                    canonical_json_bytes(
                        row.model_dump(mode="json") if isinstance(row, BaseModel) else row
                    )
                ).hexdigest()
                for identity, row in zip(manifest.row_identities, rows)
            }
        if (
            manifest.layer is ArtifactLayer.NORMALIZED
            and manifest.data_kind is DataKind.SPLITS
            and len(manifest.objects) == 1
            and manifest.objects[0].media_type == "application/vnd.quantmesh.equity-splits+json"
        ):
            try:
                payload = json.loads(self.manifests.objects.get_bytes(manifest.objects[0]))
                if not isinstance(payload, list):
                    return {}
                actions = tuple(EquitySplitAction.model_validate(row) for row in payload)
                return {
                    action.action_id: hashlib.sha256(
                        canonical_json_bytes(action.model_dump(mode="json"))
                    ).hexdigest()
                    for action in actions
                }
            except (TypeError, ValueError, json.JSONDecodeError):
                return {}
        return {}

    def evaluate_status(
        self,
        policy: QualityPolicy,
        *,
        window_start: datetime,
        window_end: datetime,
        observation: QualityObservation,
        reconciles_overlap: bool = False,
    ) -> QualityDecision:
        if not _is_utc(window_start) or not _is_utc(window_end) or window_end <= window_start:
            raise ValueError("quality window must be a positive UTC range")
        calendar_id = "XNYS" if policy.venue is Venue.MOOMOO else "24/7"
        calendar = CalendarService()
        scheduled_opens: tuple[datetime, ...] = ()
        completed_opens: tuple[datetime, ...] = ()
        if policy.data_kind is DataKind.BARS and policy.interval is not None:
            scheduled_opens, completed_opens = _scheduled_and_completed_bar_opens(
                calendar,
                calendar_id,
                window_start,
                window_end,
                policy=policy,
                evaluated_at=observation.evaluated_at,
            )
            due = bool(scheduled_opens) and len(completed_opens) == len(scheduled_opens)
        else:
            due = _window_is_due(
                calendar,
                calendar_id,
                window_start,
                window_end,
                policy=policy,
            )
        expected_count = (
            len(completed_opens)
            if policy.data_kind is DataKind.BARS
            and policy.layer in {ArtifactLayer.NORMALIZED, ArtifactLayer.ADJUSTED}
            and policy.interval is not None
            else 0
        )
        if policy.layer in {ArtifactLayer.RAW, ArtifactLayer.FEATURE}:
            expected_count = observation.expected_count
        checks = (
            (observation.duplicate_count, "duplicate-source-identity"),
            (observation.gap_count, "unexplained-gap"),
            (observation.hash_mismatch_count, "object-hash-mismatch"),
            (observation.schema_mismatch_count, "schema-mismatch"),
            (observation.order_violation_count, "order-or-timestamp-violation"),
            (
                0 if reconciles_overlap else observation.overlap_conflict_count,
                "historical-live-overlap",
            ),
        )
        if not due:
            issues = [code for count, code in checks if count]
            unexpected = (
                observation.observed_count > len(completed_opens)
                if policy.data_kind is DataKind.BARS
                else bool(observation.observed_count)
            )
            if unexpected:
                issues.append("unexpected-out-of-session-data")
            if issues:
                return QualityDecision(
                    status=QualityStatus.FAIL,
                    issue_codes=tuple(sorted(set(issues))),
                    expected_count=0,
                )
            return QualityDecision(
                status=QualityStatus.NOT_DUE,
                issue_codes=("calendar-not-due",),
                expected_count=0,
            )
        hard_issues: list[str] = []
        if observation.expected_count != expected_count:
            hard_issues.append("expected-count-mismatch")
        hard_issues.extend(code for count, code in checks if count)
        if policy.require_terminal_pagination and observation.pagination_terminal is False:
            hard_issues.append("pagination-incomplete")
        deadline_base = window_end
        if scheduled_opens:
            deadline_base = max(
                deadline_base,
                max(_bar_available_at(item, policy=policy) for item in scheduled_opens),
            )
        deadline = deadline_base + timedelta(seconds=policy.grace_period_seconds)
        if hard_issues:
            issues = list(hard_issues)
            if observation.evaluated_at >= deadline:
                issues.extend(_post_grace_sla_issues(policy, observation, expected_count))
            return QualityDecision(
                status=QualityStatus.FAIL,
                issue_codes=tuple(sorted(set(issues))),
                expected_count=expected_count,
            )
        unavailable: list[str] = []
        if observation.entitlement is EntitlementState.UNKNOWN:
            unavailable.append("unknown-entitlement")
        elif observation.entitlement in {EntitlementState.DEGRADED, EntitlementState.UNAVAILABLE}:
            unavailable.append("entitlement-unavailable")
        if not observation.source_rights_known:
            unavailable.append("unknown-source-rights")
        if observation.unavailable_reason is not None:
            unavailable.append("provider-unavailable")
        if unavailable:
            return QualityDecision(
                status=QualityStatus.UNAVAILABLE,
                issue_codes=tuple(sorted(set(unavailable))),
                expected_count=expected_count,
            )
        if observation.evaluated_at < deadline:
            return QualityDecision(
                status=QualityStatus.NOT_DUE,
                issue_codes=("within-grace-period",),
                expected_count=expected_count,
            )
        issues = _post_grace_sla_issues(policy, observation, expected_count)
        return QualityDecision(
            status=QualityStatus.FAIL if issues else QualityStatus.PASS,
            issue_codes=tuple(sorted(set(issues))),
            expected_count=expected_count,
        )

    @staticmethod
    def _validate_target(policy: QualityPolicy, manifest: ArtifactManifest) -> None:
        venue = (
            Venue.MOOMOO
            if manifest.canonical_instrument.value.startswith("moomoo:")
            else Venue.HYPERLIQUID
        )
        if (
            policy.venue,
            policy.layer,
            policy.data_kind,
            policy.interval,
            policy.calendar_version,
            policy.session_policy,
        ) != (
            venue,
            manifest.layer,
            manifest.data_kind,
            manifest.interval,
            manifest.calendar_version,
            manifest.session_policy,
        ):
            raise QualityFailure("quality policy does not match its manifest")

    def require_admitted_manifest(
        self,
        manifest_id: str,
        *,
        admitted_manifest_ids: frozenset[str],
    ) -> ArtifactManifest:
        """Open an exact manifest only when committed or in the candidate graph."""
        try:
            manifest = self.manifests.open(manifest_id).manifest
        except ManifestIntegrityError as error:
            raise QualityFailure("quality evaluation requires an admitted manifest") from error
        if manifest_id in admitted_manifest_ids:
            return manifest
        committed = {item.manifest_id for item in self.manifests.manifests(manifest.dataset_id)}
        if manifest_id not in committed:
            raise QualityFailure("quality evaluation requires an admitted manifest")
        return manifest

    def _raw_envelopes(
        self,
        manifest: ArtifactManifest,
        *,
        admitted_manifest_ids: frozenset[str],
    ) -> tuple[RawEnvelope, ...]:
        pending = [manifest]
        seen: set[str] = set()
        envelopes: list[RawEnvelope] = []
        while pending:
            current = pending.pop()
            if current.manifest_id in seen:
                continue
            seen.add(current.manifest_id)
            self.require_admitted_manifest(
                current.manifest_id,
                admitted_manifest_ids=admitted_manifest_ids,
            )
            if current.layer is ArtifactLayer.RAW:
                current_envelopes = [
                    RawEnvelope.model_validate_json(self.manifests.objects.get_bytes(reference))
                    for reference in current.objects
                    if reference.media_type == "application/vnd.quantmesh.raw-envelope+json"
                ]
                if not current_envelopes:
                    raise QualityFailure("every raw lineage leaf requires a real raw envelope")
                envelopes.extend(current_envelopes)
            elif not current.parent_manifest_ids:
                raise QualityFailure("derived quality lineage must terminate at raw manifests")
            pending.extend(
                self.manifests.open(parent_id).manifest for parent_id in current.parent_manifest_ids
            )
        return tuple(envelopes)

    def validate_lineage(
        self,
        manifest: ArtifactManifest,
        observation: QualityObservation,
        *,
        admitted_manifest_ids: frozenset[str] = frozenset(),
    ) -> None:
        if observation.synthetic_row_count:
            raise QualityFailure("synthetic rows cannot qualify real data")
        pending = [manifest]
        seen: set[str] = set()
        found_real_raw_envelope = False
        while pending:
            current = pending.pop()
            if current.manifest_id in seen:
                continue
            seen.add(current.manifest_id)
            self.require_admitted_manifest(
                current.manifest_id,
                admitted_manifest_ids=admitted_manifest_ids,
            )
            if current.source_rights_id.startswith(("fixture-", "synthetic-", "demo-")):
                raise QualityFailure("synthetic or fixture lineage cannot qualify")
            if current.layer.value == "raw":
                raw_envelopes = 0
                for reference in current.objects:
                    if reference.media_type != "application/vnd.quantmesh.raw-envelope+json":
                        continue
                    envelope = RawEnvelope.model_validate_json(
                        self.manifests.objects.get_bytes(reference)
                    )
                    if envelope.provenance is not ProvenanceClass.REAL:
                        raise QualityFailure("synthetic raw lineage cannot qualify")
                    raw_envelopes += 1
                    found_real_raw_envelope = True
                if not raw_envelopes:
                    raise QualityFailure("every raw lineage leaf requires a real raw envelope")
            elif not current.parent_manifest_ids:
                raise QualityFailure("derived quality lineage must terminate at raw manifests")
            pending.extend(
                self.manifests.open(parent_id).manifest for parent_id in current.parent_manifest_ids
            )
        if not found_real_raw_envelope:
            raise QualityFailure("quality evaluation requires a real raw envelope ancestor")


def _observation_from_evaluation(evaluation: QualityEvaluation) -> QualityObservation:
    return QualityObservation(
        evaluated_at=evaluation.evaluated_at,
        expected_count=evaluation.reported_expected_count,
        observed_count=evaluation.observed_count,
        duplicate_count=evaluation.duplicate_count,
        gap_count=evaluation.gap_count,
        hash_mismatch_count=evaluation.hash_mismatch_count,
        schema_mismatch_count=evaluation.schema_mismatch_count,
        order_violation_count=evaluation.order_violation_count,
        overlap_conflict_count=evaluation.overlap_conflict_count,
        overlap_conflict_fingerprints=evaluation.overlap_conflict_fingerprints,
        synthetic_row_count=evaluation.synthetic_row_count,
        pagination_terminal=evaluation.pagination_terminal,
        source_rights_known=evaluation.source_rights_known,
        entitlement=evaluation.entitlement,
        freshness_seconds=evaluation.freshness_seconds,
        latency_seconds=evaluation.latency_seconds,
        unavailable_reason=evaluation.unavailable_reason,
    )


def _raw_payload_fingerprints(
    envelope: RawEnvelope,
    objects: ObjectStore,
) -> dict[str, str] | None:
    try:
        decoded = json.loads(objects.get_bytes(envelope.raw_object))
        if isinstance(decoded, dict) and isinstance(decoded.get("rows"), list):
            rows = decoded["rows"]
        elif isinstance(decoded, list) and all(
            isinstance(page, dict) and isinstance(page.get("rows"), list) for page in decoded
        ):
            rows = [row for page in decoded for row in page["rows"]]
        elif isinstance(decoded, list):
            rows = decoded
        else:
            return None
        identities = tuple(
            identity
            for identity in envelope.source_event_ids
            if not identity.startswith("empty-response:")
        )
        if not identities and not rows:
            return {}
        if len(identities) != len(rows):
            return None
        return {
            identity: hashlib.sha256(canonical_json_bytes(row)).hexdigest()
            for identity, row in zip(identities, rows)
        }
    except (ObjectIntegrityError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _pagination_is_terminal(cursor: str | None) -> bool:
    if cursor is None:
        return True
    try:
        body = json.loads(cursor)
        pages = body["pages"]
        terminal = pages[-1]["next"]
    except (IndexError, KeyError, TypeError, json.JSONDecodeError):
        return False
    return terminal is None or terminal == "-1"


def _post_grace_sla_issues(
    policy: QualityPolicy,
    observation: QualityObservation,
    expected_count: int,
) -> list[str]:
    issues: list[str] = []
    if expected_count and (
        observation.observed_count / expected_count < policy.minimum_coverage_ratio
    ):
        issues.append("coverage-below-threshold")
    if policy.require_terminal_pagination and observation.pagination_terminal is not True:
        issues.append("pagination-incomplete")
    if observation.freshness_seconds is None:
        issues.append("freshness-unavailable")
    elif observation.freshness_seconds > policy.max_freshness_seconds:
        issues.append("freshness-sla")
    if observation.latency_seconds is None:
        issues.append("latency-unavailable")
    elif observation.latency_seconds > policy.max_latency_seconds:
        issues.append("latency-sla")
    return issues


def _window_is_due(
    calendar: CalendarService,
    calendar_id: str,
    start: datetime,
    end: datetime,
    *,
    policy: QualityPolicy,
) -> bool:
    sessions = calendar.sessions(
        calendar_id,
        start.date(),
        (end - timedelta(microseconds=1)).date(),
        policy=policy.session_policy,
    )
    return any(start < session.close_at and end > session.open_at for session in sessions)


def _scheduled_and_completed_bar_opens(
    calendar: CalendarService,
    calendar_id: str,
    start: datetime,
    end: datetime,
    *,
    policy: QualityPolicy,
    evaluated_at: datetime,
) -> tuple[tuple[datetime, ...], tuple[datetime, ...]]:
    scheduled = calendar.expected_bar_opens(
        calendar_id,
        start,
        end,
        interval=policy.interval or "1d",
        policy=policy.session_policy,
    )
    completed = tuple(
        item for item in scheduled if _bar_available_at(item, policy=policy) <= evaluated_at
    )
    return scheduled, completed


def _bar_available_at(
    timestamp: datetime,
    *,
    policy: QualityPolicy,
) -> datetime:
    if (
        policy.venue is Venue.MOOMOO
        and policy.interval is not None
        and interval_to_timedelta(policy.interval) >= timedelta(days=1)
    ):
        session_date = timestamp.astimezone(ZoneInfo("America/New_York")).date()
        sessions = CalendarService().sessions(
            "XNYS",
            session_date,
            session_date,
            policy=policy.session_policy,
        )
        if not sessions:
            return timestamp
        return sessions[0].close_at
    return timestamp + interval_to_timedelta(policy.interval or "1d")


def _manifest_bar_available_at(manifest: ArtifactManifest, timestamp: datetime) -> datetime:
    venue = (
        Venue.MOOMOO
        if manifest.canonical_instrument.value.startswith("moomoo:")
        else Venue.HYPERLIQUID
    )
    policy = QualityPolicy(
        venue=venue,
        layer=manifest.layer,
        data_kind=manifest.data_kind,
        interval=manifest.interval,
        calendar_version=manifest.calendar_version,
        session_policy=manifest.session_policy,
        grace_period_seconds=0,
        minimum_coverage_ratio=1.0,
        max_freshness_seconds=0,
        max_latency_seconds=0,
        require_terminal_pagination=False,
    )
    return _bar_available_at(timestamp, policy=policy)


def _envelope_available_at(envelope: RawEnvelope, manifest: ArtifactManifest) -> datetime:
    if envelope.provider_available_at is not None:
        return envelope.provider_available_at
    if envelope.data_kind is DataKind.BARS and manifest.interval is not None:
        return _manifest_bar_available_at(manifest, envelope.event_end)
    return envelope.event_end


def _manifest_event_available_at(
    manifest: ArtifactManifest, envelopes: tuple[RawEnvelope, ...]
) -> datetime:
    return max(_envelope_available_at(envelope, manifest) for envelope in envelopes)


def _nonbar_schema_mismatch(
    manifest: ArtifactManifest,
    manifests: ManifestStore,
) -> int:
    if not (
        manifest.layer is ArtifactLayer.NORMALIZED
        and manifest.data_kind is DataKind.SPLITS
        and len(manifest.objects) == 1
        and manifest.objects[0].media_type == "application/vnd.quantmesh.equity-splits+json"
    ):
        return 1
    try:
        payload = json.loads(manifests.objects.get_bytes(manifest.objects[0]))
        if not isinstance(payload, list):
            raise TypeError("split payload must be a list")
        actions = tuple(EquitySplitAction.model_validate(item) for item in payload)
        identities = tuple(action.action_id for action in actions)
        if actions:
            if (
                identities != manifest.row_identities
                or min(action.effective_at for action in actions) != manifest.event_start
                or max(action.effective_at for action in actions) != manifest.event_end
            ):
                raise ValueError("split declarations disagree with typed rows")
        elif not (
            len(manifest.row_identities) == 1 and manifest.row_identities[0].startswith("no-split:")
        ):
            raise ValueError("empty split payload has no canonical sentinel")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return 1
    return 0
