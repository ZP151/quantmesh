"""Exact-packet outcome attribution and immutable operator reviews."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.domain.models import Side
from quantmesh.domain.orders import Order, OrderStatus, validate_order_replay
from quantmesh.instruments.contracts import (
    CoverageSnapshot,
    DecisionDisposition,
    DecisionPacket,
    HistoricalBar,
    HistoricalSeries,
    HistoryRange,
    PaperProposal,
    PriceForecastArtifact,
    ProposalStatus,
)
from quantmesh.instruments.decision_packets import (
    DecisionPacketNotFoundError,
    DecisionPacketStore,
    decision_packet_id,
    validate_decision_packet_lineage,
)
from quantmesh.instruments.monitoring import (
    DecisionWatchEvaluation,
    DecisionWatchRegistration,
    DecisionWatchStore,
    validate_watch_replay,
)
from quantmesh.instruments.proposals import ProposalLedger, validate_proposal_replay
from quantmesh.persistence.jsonl import JsonlStore

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _identity(prefix: str, value: object) -> str:
    return f"{prefix}-{hashlib.sha256(_canonical(value)).hexdigest()[:24]}"


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{label} time must be timezone-aware")
    return value.astimezone(UTC)


def _validate_packet_lineage(root: DecisionPacket, packet: DecisionPacket) -> None:
    try:
        validate_decision_packet_lineage((root, packet))
    except ValueError as error:
        label = "root" if root.packet_id != decision_packet_id(root) else "action"
        raise ValueError(
            f"embedded {label} packet identity or lineage is invalid: {error}"
        ) from error


def _validate_proposal_binding(
    root: DecisionPacket, packet: DecisionPacket, proposal: PaperProposal
) -> None:
    validate_proposal_replay(proposal)
    evidence = root.evidence
    if (
        proposal.id != packet.proposal_id
        or proposal.instrument.model_dump(mode="json") != packet.instrument.model_dump(mode="json")
        or proposal.artifact_id != evidence.forecast_artifact_id
        or proposal.dataset_id != evidence.forecast_dataset_id
        or proposal.dataset_revision != evidence.forecast_dataset_revision
        or proposal.forecast_generated_at != evidence.forecast_generated_at
        or proposal.model_version != evidence.forecast_model_version
        or proposal.config_digest != evidence.forecast_config_digest
        or proposal.history_digest != evidence.forecast_history_digest
        or proposal.created_at < root.created_at
        or proposal.created_at > packet.created_at
    ):
        raise ValueError("proposal does not match immutable action packet evidence")


def _validate_order_binding(proposal: PaperProposal, order: Order) -> None:
    validate_order_replay(order)
    if (
        order.order_id != proposal.order_id
        or order.idempotency_key != f"proposal:{proposal.id}"
        or order.instrument.model_dump(mode="json") != proposal.instrument.model_dump(mode="json")
        or order.side is not proposal.side
        or not math.isclose(order.quantity, proposal.quantity)
        or order.limit_price != proposal.limit_price
        or order.created_at < proposal.created_at
    ):
        raise ValueError("order does not match exact proposal")


def _path_digest_payload(path: OutcomePath) -> dict[str, object]:
    return {
        "dataset_id": path.dataset_id,
        "dataset_revision": path.dataset_revision,
        "manifest_id": path.manifest_id,
        "quality_evaluation_id": path.quality_evaluation_id,
        "source": path.source,
        "license": path.license,
        "generated_at": path.generated_at.isoformat() if path.generated_at else None,
        "interval": path.interval,
        "calendar": path.calendar,
        "adjustment": path.adjustment,
        "coverage": path.coverage.model_dump(mode="json") if path.coverage else None,
        "expected_session_times": [item.isoformat() for item in path.expected_session_times],
        "bars": [bar.model_dump(mode="json") for bar in path.bars],
    }


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class ReviewClassification(StrEnum):
    SUPPORTED = "supported"
    CHALLENGED = "challenged"
    MIXED = "mixed"
    INCONCLUSIVE = "inconclusive"


class OutcomeMetric(_Contract):
    """A value that never turns missing outcome evidence into zero."""

    status: Literal["available", "unavailable"]
    value: float | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def value_matches_status(self) -> OutcomeMetric:
        if self.status == "available":
            if self.value is None or not math.isfinite(self.value):
                raise ValueError("available outcome metric requires a finite value")
            if self.reason is not None:
                raise ValueError("available outcome metric cannot carry an unavailable reason")
        elif self.value is not None or self.reason is None or not self.reason.strip():
            raise ValueError("unavailable outcome metric requires only a reason")
        return self


class OutcomePath(_Contract):
    """Exact daily close path and the provenance used to read it."""

    status: Literal["complete", "partial", "pending", "unavailable"]
    target_at: datetime | None = None
    cutoff_at: datetime
    expected_session_times: tuple[datetime, ...] = ()
    bars: tuple[HistoricalBar, ...] = ()
    dataset_id: str | None = None
    dataset_revision: int | None = Field(default=None, ge=1)
    manifest_id: str | None = None
    quality_evaluation_id: str | None = None
    source: str | None = None
    license: str | None = None
    generated_at: datetime | None = None
    interval: str | None = None
    calendar: str | None = None
    adjustment: str | None = None
    coverage: CoverageSnapshot | None = None
    path_digest: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    reason: str | None = None

    @field_validator("target_at", "cutoff_at", "generated_at")
    @classmethod
    def times_are_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value, "outcome path")

    @field_validator("expected_session_times")
    @classmethod
    def expected_times_are_utc(cls, value: tuple[datetime, ...]) -> tuple[datetime, ...]:
        normalized = tuple(_utc(item, "expected outcome session") for item in value)
        if normalized != tuple(sorted(set(normalized))):
            raise ValueError("expected outcome sessions must be unique and chronological")
        return normalized

    @model_validator(mode="after")
    def path_shape(self) -> OutcomePath:
        provenance = (
            self.dataset_id,
            self.dataset_revision,
            self.source,
            self.license,
            self.generated_at,
            self.interval,
            self.calendar,
            self.adjustment,
            self.coverage,
            self.path_digest,
        )
        if self.bars:
            if any(value is None for value in provenance):
                raise ValueError("outcome bars require complete dataset provenance")
            timestamps = tuple(bar.timestamp for bar in self.bars)
            if timestamps != tuple(sorted(set(timestamps))):
                raise ValueError("outcome bars must be strictly chronological")
            if any(bar.timestamp > self.cutoff_at for bar in self.bars):
                raise ValueError("outcome path cannot contain future knowledge")
            if any(bar.is_live_tail for bar in self.bars):
                raise ValueError("outcome path cannot contain a live tail")
            digest = hashlib.sha256(_canonical(_path_digest_payload(self))).hexdigest()
            if self.path_digest != digest:
                raise ValueError("outcome path digest does not match embedded evidence")
        elif any(value is not None for value in provenance):
            raise ValueError("empty outcome path cannot carry fabricated provenance")
        if self.target_at is not None:
            if (
                len(self.expected_session_times) != 30
                or self.expected_session_times[-1] != self.target_at
            ):
                raise ValueError("outcome path requires the exact 30-session forecast timestamps")
        elif self.expected_session_times:
            raise ValueError("outcome sessions require a pinned target")
        actual = tuple(bar.timestamp for bar in self.bars)
        expected_by_cutoff = tuple(
            timestamp for timestamp in self.expected_session_times if timestamp <= self.cutoff_at
        )
        if self.status in {"complete", "pending"} and actual != expected_by_cutoff:
            raise ValueError("outcome path does not match expected completed sessions")
        if self.status == "complete" and actual != self.expected_session_times:
            raise ValueError("complete outcome path must contain all 30 expected sessions")
        if (self.manifest_id is None) != (self.quality_evaluation_id is None):
            raise ValueError("outcome manifest and quality IDs must be present together")
        if self.status in {"partial", "unavailable"}:
            if self.reason is None or not self.reason.strip():
                raise ValueError("incomplete outcome path requires a reason")
        elif self.reason is not None:
            raise ValueError("complete or pending outcome path cannot carry a failure reason")
        return self


class ScenarioObservation(_Contract):
    kind: Literal["bull", "base", "bear"]
    threshold_kind: Literal["resistance", "support"]
    threshold: float = Field(gt=0)
    threshold_state: Literal["observed", "not_observed", "unavailable"]
    threshold_at: datetime | None = None
    invalidation_level: float | None = Field(default=None, gt=0)
    invalidation_state: Literal["observed", "not_observed", "unavailable"]
    invalidation_at: datetime | None = None

    @field_validator("threshold_at", "invalidation_at")
    @classmethod
    def observation_times_are_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value, "scenario observation")

    @model_validator(mode="after")
    def state_matches_time(self) -> ScenarioObservation:
        if (self.threshold_state == "observed") != (self.threshold_at is not None):
            raise ValueError("scenario threshold state must match its first observation")
        if (self.invalidation_state == "observed") != (self.invalidation_at is not None):
            raise ValueError("scenario invalidation state must match its first observation")
        if self.kind == "bear":
            if self.invalidation_level is not None or self.invalidation_state != "unavailable":
                raise ValueError("Bear invalidation is unavailable for a long-only packet")
        return self


class MonitoringOutcome(_Contract):
    status: Literal[
        "not_applicable",
        "not_monitored",
        "coverage_incomplete",
        "no_trigger_recorded",
        "triggered",
    ]
    registration: DecisionWatchRegistration | None = None
    evaluations: tuple[DecisionWatchEvaluation, ...] = ()
    event_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def monitoring_shape(self) -> MonitoringOutcome:
        if self.status in {"not_applicable", "not_monitored"} and (
            self.registration is not None or self.evaluations or self.event_ids
        ):
            raise ValueError("absent monitoring cannot carry monitoring records")
        if self.status == "triggered" and not self.event_ids:
            raise ValueError("triggered monitoring requires exact event identities")
        if self.event_ids and self.status != "triggered":
            raise ValueError("only triggered monitoring carries event identities")
        return self


class PaperOutcome(_Contract):
    state: Literal[
        "not_applicable",
        "watch_only",
        "pending_no_order",
        "blocked",
        "risk_rejected",
        "accepted_unfilled",
        "filled_open",
        "unavailable",
    ]
    proposal: PaperProposal | None = None
    order: Order | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def exact_bindings(self) -> PaperOutcome:
        if self.order is not None:
            if self.proposal is None:
                raise ValueError("paper outcome order differs from its proposal")
            _validate_order_binding(self.proposal, self.order)
        if self.state in {"not_applicable", "watch_only"} and (
            self.proposal is not None or self.order is not None
        ):
            raise ValueError("non-paper action cannot carry proposal or order state")
        if self.state in {"blocked", "risk_rejected", "unavailable"}:
            if self.reason is None or not self.reason.strip():
                raise ValueError("blocked paper outcome requires an exact reason")
        elif self.reason is not None:
            raise ValueError("non-blocked paper outcome cannot carry a reason")
        expected = {
            "pending_no_order": (
                self.proposal is not None
                and self.proposal.status is ProposalStatus.PENDING
                and self.order is None
            ),
            "blocked": (
                self.proposal is not None
                and self.proposal.status is ProposalStatus.BLOCKED
                and self.order is None
            ),
            "risk_rejected": (
                self.proposal is not None
                and self.proposal.status is ProposalStatus.REJECTED
                and self.order is not None
                and self.order.status is OrderStatus.REJECTED
                and not self.order.fills
            ),
            "accepted_unfilled": (
                self.proposal is not None
                and self.proposal.status is ProposalStatus.CONFIRMED
                and self.order is not None
                and self.order.status in {OrderStatus.ACCEPTED, OrderStatus.PENDING}
                and not self.order.fills
            ),
            "filled_open": (
                self.proposal is not None
                and self.proposal.status is ProposalStatus.CONFIRMED
                and self.order is not None
                and bool(self.order.fills)
            ),
        }
        if self.state in expected and not expected[self.state]:
            raise ValueError("paper outcome state differs from proposal/order evidence")
        return self


class DecisionOutcomeSnapshot(_Contract):
    outcome_id: str = Field(pattern=r"^outcome-[0-9a-f]{24}$")
    packet_id: str = Field(pattern=r"^packet-[0-9a-f]{24}$")
    evaluated_at: datetime
    packet: DecisionPacket
    root_packet: DecisionPacket
    horizon_target_at: datetime | None = None
    attribution_policy_version: Literal["strict-close-v1"]
    attribution_basis: Literal["completed_daily_close"]
    attribution_equality: Literal["equality_does_not_cross"]
    evidence_status: Literal["complete", "partial", "pending", "unavailable"]
    path: OutcomePath
    scenarios: tuple[ScenarioObservation, ScenarioObservation, ScenarioObservation]
    target_stop_ordering: Literal[
        "target_first",
        "stop_first",
        "ambiguous_same_bar",
        "neither",
        "unavailable",
    ]
    planned_reward_to_risk: float = Field(gt=0)
    gross_path_r: OutcomeMetric
    entry_fill_deviation_r: OutcomeMetric
    mark_to_market_paper_r: OutcomeMetric
    realized_paper_r: OutcomeMetric
    paper: PaperOutcome
    monitoring: MonitoringOutcome

    @field_validator("evaluated_at", "horizon_target_at")
    @classmethod
    def outcome_times_are_utc(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value, "decision outcome")

    @model_validator(mode="after")
    def canonical_outcome(self) -> DecisionOutcomeSnapshot:
        _validate_packet_lineage(self.root_packet, self.packet)
        if self.evaluated_at < self.packet.created_at or self.evaluated_at < self.root_packet.as_of:
            raise ValueError("outcome evaluation predates its exact packet evidence")
        if self.packet.packet_id != self.packet_id:
            raise ValueError("outcome packet binding differs")
        if self.root_packet.disposition is not DecisionDisposition.DRAFT:
            raise ValueError("outcome root packet must be the draft analysis")
        if self.path.status != self.evidence_status:
            raise ValueError("outcome evidence status must match its path")
        if self.horizon_target_at != self.path.target_at:
            raise ValueError("outcome horizon must match its exact path target")
        if self.path.cutoff_at > self.evaluated_at:
            raise ValueError("outcome path cutoff exceeds its evaluation boundary")
        if self.path.generated_at is not None and self.path.generated_at > self.evaluated_at:
            raise ValueError("outcome path was generated after its evaluation boundary")
        if tuple(item.kind for item in self.scenarios) != ("bull", "base", "bear"):
            raise ValueError("outcome scenarios must be ordered bull, base, bear")
        if any(
            observed_at is not None and observed_at > self.path.cutoff_at
            for scenario in self.scenarios
            for observed_at in (scenario.threshold_at, scenario.invalidation_at)
        ):
            raise ValueError("scenario observation exceeds its exact path cutoff")
        if self.paper.proposal is not None:
            _validate_proposal_binding(self.root_packet, self.packet, self.paper.proposal)
        if self.paper.order is not None:
            if self.paper.proposal is None:
                raise ValueError("outcome order has no proposal")
            _validate_order_binding(self.paper.proposal, self.paper.order)
            if self.paper.order.created_at > self.evaluated_at or any(
                event.timestamp > self.evaluated_at for event in self.paper.order.events
            ):
                raise ValueError("order evidence exceeds its evaluation boundary")
        if self.monitoring.registration is not None:
            if self.monitoring.registration.packet_id != self.packet_id:
                raise ValueError("outcome monitoring registration differs from action packet")
            validate_watch_replay(
                self.monitoring.registration,
                self.monitoring.evaluations,
            )
            exact_events = tuple(
                dict.fromkeys(
                    result.event_id
                    for evaluation in self.monitoring.evaluations
                    for result in evaluation.results
                    if result.event_id is not None
                )
            )
            if self.monitoring.event_ids != exact_events:
                raise ValueError("outcome monitoring event identities differ from evaluations")
        elif self.monitoring.evaluations:
            raise ValueError("outcome monitoring evaluations have no registration")
        if any(
            evaluation.observation.evaluated_at > self.evaluated_at
            or any(
                timestamp is not None and timestamp > evaluation.observation.evaluated_at
                for timestamp in (
                    evaluation.observation.data_time,
                    evaluation.observation.received_at,
                )
            )
            for evaluation in self.monitoring.evaluations
        ):
            raise ValueError("outcome monitoring evidence exceeds its evaluation boundary")
        payload = self.model_dump(mode="json", exclude={"outcome_id"})
        if self.outcome_id != _identity("outcome", payload):
            raise ValueError("decision outcome identity does not match canonical content")
        return self


class DecisionReviewRecord(_Contract):
    review_id: str = Field(pattern=r"^review-[0-9a-f]{24}$")
    packet_id: str = Field(pattern=r"^packet-[0-9a-f]{24}$")
    reviewed_at: datetime
    outcome: DecisionOutcomeSnapshot
    classification: ReviewClassification
    note: str | None = Field(default=None, max_length=2_000)

    @field_validator("reviewed_at")
    @classmethod
    def review_time_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "review")

    @model_validator(mode="after")
    def canonical_review(self) -> DecisionReviewRecord:
        if self.outcome.packet_id != self.packet_id:
            raise ValueError("review packet differs from its outcome")
        if self.reviewed_at < self.outcome.evaluated_at:
            raise ValueError("review time cannot predate the fenced outcome")
        if (
            self.outcome.evidence_status != "complete"
            and self.classification is not ReviewClassification.INCONCLUSIVE
        ):
            raise ValueError("partial or unavailable outcome permits only inconclusive review")
        payload = self.model_dump(mode="json", exclude={"review_id"})
        if self.review_id != _identity("review", payload):
            raise ValueError("decision review identity does not match canonical content")
        return self


class DecisionOutcomeReviewState(_Contract):
    packet_id: str = Field(pattern=r"^packet-[0-9a-f]{24}$")
    root_packet: DecisionPacket
    outcome: DecisionOutcomeSnapshot
    review: DecisionReviewRecord | None = None

    @model_validator(mode="after")
    def exact_authoritative_packets(self) -> DecisionOutcomeReviewState:
        if self.outcome.packet_id != self.packet_id or self.outcome.root_packet != self.root_packet:
            raise ValueError("outcome review state packet binding differs")
        if self.review is not None and (
            self.review.packet_id != self.packet_id
            or self.review.outcome.packet != self.outcome.packet
            or self.review.outcome.root_packet != self.root_packet
        ):
            raise ValueError("saved review packet lineage differs from authoritative packets")
        return self


def _root_lock(root: Path) -> threading.RLock:
    key = str(root.resolve(strict=False)).casefold()
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _interprocess_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".decision-reviews.lock"
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class DecisionReviewStore:
    """One immutable review closure per exact action packet."""

    def __init__(self, root: Path) -> None:
        self._lock = _root_lock(root)
        self._local = threading.local()
        self._store = JsonlStore(
            root,
            filename="decision-reviews.jsonl",
            model=DecisionReviewRecord,
            label="decision review store",
            id_label="decision review",
            key=lambda item: item.review_id,
            secondary_keys=(("decision packet id", lambda item: item.packet_id),),
            extra_validate=self._validate,
        )

    @property
    def root(self) -> Path:
        return self._store.root

    @property
    def path(self) -> Path:
        return self._store.path

    @contextmanager
    def transaction(self) -> Iterator[None]:
        depth = getattr(self._local, "depth", 0)
        if depth:
            self._local.depth = depth + 1
            try:
                yield
            finally:
                self._local.depth = depth
            return
        with self._lock, _interprocess_lock(self.root):
            self._local.depth = 1
            try:
                yield
            finally:
                self._local.depth = 0

    @staticmethod
    def _validate(value: DecisionReviewRecord) -> None:
        value.canonical_review()

    def all(self) -> tuple[DecisionReviewRecord, ...]:
        return tuple(self._store.read())

    def for_packet(self, packet_id: str) -> DecisionReviewRecord | None:
        if re.fullmatch(r"packet-[0-9a-f]{24}", packet_id) is None:
            raise ValueError("invalid decision packet id")
        return next((item for item in self.all() if item.packet_id == packet_id), None)

    def record(self, value: DecisionReviewRecord) -> DecisionReviewRecord:
        with self.transaction():
            existing = self.for_packet(value.packet_id)
            if existing is not None:
                if existing != value:
                    raise ValueError("decision packet already has a different review")
                return existing
            self._store.append(value)
            return value


class ForecastRegistry(Protocol):
    def get(self, artifact_id: str) -> PriceForecastArtifact: ...


class HistoryReader(Protocol):
    def history(
        self,
        venue,
        symbol: str,
        range: HistoryRange,
        *,
        as_of: datetime | None = None,
    ) -> HistoricalSeries: ...


class JournalReader(Protocol):
    def get(self, order_id: str) -> Order: ...


def _unavailable(reason: str) -> OutcomeMetric:
    return OutcomeMetric(status="unavailable", reason=reason)


class DecisionOutcomeReviewService:
    """Compose read-only local evidence and atomically append one operator review."""

    def __init__(
        self,
        *,
        packet_store: DecisionPacketStore,
        review_store: DecisionReviewStore,
        forecast_registry: ForecastRegistry | None,
        history: HistoryReader | None,
        proposal_ledger: ProposalLedger | None,
        journal: JournalReader | None,
        monitoring: DecisionWatchStore | None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.packet_store = packet_store
        self.review_store = review_store
        self.forecast_registry = forecast_registry
        self.history = history
        self.proposal_ledger = proposal_ledger
        self.journal = journal
        self.monitoring = monitoring
        self._now = now or (lambda: datetime.now(UTC))

    @staticmethod
    def _validate_forecast_binding(root: DecisionPacket, artifact: PriceForecastArtifact) -> None:
        evidence = root.evidence
        if (
            evidence.forecast_artifact_id != artifact.id
            or root.instrument.model_dump(mode="json")
            != artifact.instrument.model_dump(mode="json")
            or evidence.forecast_dataset_id != artifact.dataset_id
            or evidence.forecast_dataset_revision != artifact.dataset_revision
            or evidence.forecast_manifest_id != artifact.manifest_id
            or evidence.forecast_quality_evaluation_id != artifact.quality_evaluation_id
            or evidence.forecast_generated_at != artifact.generated_at
            or evidence.forecast_model_name != artifact.model_name
            or evidence.forecast_model_version != artifact.model_version
            or evidence.forecast_config_digest != artifact.config_digest
            or evidence.forecast_history_digest != artifact.history_digest
            or evidence.forecast_paths != artifact.paths
        ):
            raise ValueError("forecast artifact does not match immutable packet evidence")

    def _lineage(self, packet_id: str) -> tuple[DecisionPacket, DecisionPacket]:
        self.packet_store.get(packet_id)
        lineage = self.packet_store.lineage(packet_id)
        if not lineage or lineage[-1].packet_id != packet_id:
            raise DecisionPacketNotFoundError(f"decision packet {packet_id!r} is not recorded")
        packet = lineage[-1]
        root = lineage[0]
        if packet.disposition is DecisionDisposition.DRAFT:
            raise ValueError("outcome review requires an exact non-draft action packet")
        if root.disposition is not DecisionDisposition.DRAFT:
            raise ValueError("outcome review lineage has no draft analysis root")
        return root, packet

    def _forecast_target(
        self, root: DecisionPacket
    ) -> tuple[PriceForecastArtifact | None, tuple[datetime, ...], str | None]:
        artifact_id = root.evidence.forecast_artifact_id
        if artifact_id is None or self.forecast_registry is None:
            return None, (), "exact 30-session forecast binding is unavailable"
        try:
            artifact = self.forecast_registry.get(artifact_id)
            self._validate_forecast_binding(root, artifact)
        except (ValueError, OSError) as error:
            return None, (), f"exact forecast evidence is unavailable: {error}"
        path = next((item for item in artifact.paths if item.sessions == 30), None)
        if path is None or len(path.points) != 30:
            return artifact, (), "exact 30-session forecast horizon is unavailable"
        return artifact, tuple(point.timestamp for point in path.points), None

    @staticmethod
    def _path_digest(
        series: HistoricalSeries,
        bars: tuple[HistoricalBar, ...],
        expected_session_times: tuple[datetime, ...],
    ) -> str:
        payload = {
            "dataset_id": series.dataset_id,
            "dataset_revision": series.dataset_revision,
            "manifest_id": series.manifest_id,
            "quality_evaluation_id": series.quality_evaluation_id,
            "source": series.source,
            "license": series.license,
            "generated_at": series.generated_at.isoformat(),
            "interval": series.interval,
            "calendar": series.calendar,
            "adjustment": series.adjustment,
            "coverage": series.coverage.model_dump(mode="json"),
            "expected_session_times": [item.isoformat() for item in expected_session_times],
            "bars": [bar.model_dump(mode="json") for bar in bars],
        }
        return hashlib.sha256(_canonical(payload)).hexdigest()

    def _path(
        self,
        root: DecisionPacket,
        artifact: PriceForecastArtifact | None,
        expected_session_times: tuple[datetime, ...],
        target_error: str | None,
        now: datetime,
    ) -> OutcomePath:
        target_at = expected_session_times[-1] if expected_session_times else None
        query_cutoff = min(now, target_at) if target_at is not None else now
        if target_error is not None or artifact is None or target_at is None:
            return OutcomePath(
                status="unavailable",
                cutoff_at=root.as_of,
                target_at=target_at,
                expected_session_times=expected_session_times,
                reason=target_error or "exact forecast evidence is unavailable",
            )
        if self.history is None:
            return OutcomePath(
                status="unavailable",
                cutoff_at=target_at if now >= target_at else root.as_of,
                target_at=target_at,
                expected_session_times=expected_session_times,
                reason="local daily outcome history is unavailable",
            )
        try:
            series = self.history.history(
                root.instrument.venue,
                root.instrument.symbol,
                HistoryRange.ONE_YEAR,
                as_of=query_cutoff,
            )
        except (ValueError, OSError) as error:
            return OutcomePath(
                status="unavailable",
                cutoff_at=target_at if now >= target_at else root.as_of,
                target_at=target_at,
                expected_session_times=expected_session_times,
                reason=f"local daily outcome history is unavailable: {error}",
            )
        if (
            series.instrument.model_dump(mode="json") != root.instrument.model_dump(mode="json")
            or series.interval != "1d"
            or series.calendar != artifact.calendar
            or series.adjustment != artifact.adjustment
        ):
            return OutcomePath(
                status="unavailable",
                cutoff_at=target_at if now >= target_at else root.as_of,
                target_at=target_at,
                expected_session_times=expected_session_times,
                reason="local outcome history does not match packet instrument/calendar",
            )
        if series.generated_at > now:
            return OutcomePath(
                status="unavailable",
                cutoff_at=target_at if now >= target_at else root.as_of,
                target_at=target_at,
                expected_session_times=expected_session_times,
                reason="local outcome history was generated after the review clock",
            )
        if series.as_of > now or any(bar.timestamp > query_cutoff for bar in series.bars):
            return OutcomePath(
                status="unavailable",
                cutoff_at=target_at if now >= target_at else root.as_of,
                target_at=target_at,
                expected_session_times=expected_session_times,
                reason="local outcome history contains future knowledge",
            )
        if any(bar.is_live_tail for bar in series.bars):
            return OutcomePath(
                status="unavailable",
                cutoff_at=target_at if now >= target_at else root.as_of,
                target_at=target_at,
                expected_session_times=expected_session_times,
                reason="local outcome history contains a live tail",
            )
        bars = tuple(bar for bar in series.bars if root.as_of < bar.timestamp <= query_cutoff)
        if not bars:
            if now < target_at:
                return OutcomePath(
                    status="pending",
                    cutoff_at=root.as_of,
                    target_at=target_at,
                    expected_session_times=expected_session_times,
                )
            return OutcomePath(
                status="unavailable",
                cutoff_at=target_at,
                target_at=target_at,
                expected_session_times=expected_session_times,
                reason="no completed post-decision daily bars reach the pinned horizon",
            )
        reason = None
        status: Literal["complete", "partial", "pending", "unavailable"]
        relevant_gaps = tuple(item for item in series.gaps if root.as_of < item <= query_cutoff)
        actual_times = tuple(bar.timestamp for bar in bars)
        expected_completed = tuple(
            timestamp for timestamp in expected_session_times if timestamp <= query_cutoff
        )
        if actual_times != expected_completed:
            status = "partial"
            reason = "local daily outcome path is missing an expected 30-session timestamp"
        elif relevant_gaps or series.duplicates:
            status = "partial"
            reason = "local daily outcome path has a gap or duplicate"
        elif now < target_at:
            status = "pending"
        elif bars[-1].timestamp != target_at:
            status = "partial"
            reason = "local daily outcome path does not reach the pinned horizon target"
        else:
            status = "complete"
        return OutcomePath(
            status=status,
            target_at=target_at,
            cutoff_at=bars[-1].timestamp,
            expected_session_times=expected_session_times,
            bars=bars,
            dataset_id=series.dataset_id,
            dataset_revision=series.dataset_revision,
            manifest_id=series.manifest_id,
            quality_evaluation_id=series.quality_evaluation_id,
            source=series.source,
            license=series.license,
            generated_at=series.generated_at,
            interval=series.interval,
            calendar=series.calendar,
            adjustment=series.adjustment,
            coverage=series.coverage,
            path_digest=self._path_digest(series, bars, expected_session_times),
            reason=reason,
        )

    @staticmethod
    def _scenario_observations(
        root: DecisionPacket, path: OutcomePath
    ) -> tuple[ScenarioObservation, ScenarioObservation, ScenarioObservation]:
        bars = path.bars

        def first(predicate) -> datetime | None:
            return next((bar.timestamp for bar in bars if predicate(bar.close)), None)

        resistance = root.market_state.resistance
        support = root.market_state.support
        invalidation = root.market_state.invalidation
        bull_at = first(lambda close: close > resistance)
        base_at = first(lambda close: close > support)
        bear_at = first(lambda close: close < support)
        invalidated_at = first(lambda close: close < invalidation)
        unavailable = not bars

        def state(value: datetime | None) -> Literal["observed", "not_observed", "unavailable"]:
            if unavailable:
                return "unavailable"
            return "observed" if value is not None else "not_observed"

        return (
            ScenarioObservation(
                kind="bull",
                threshold_kind="resistance",
                threshold=resistance,
                threshold_state=state(bull_at),
                threshold_at=bull_at,
                invalidation_level=invalidation,
                invalidation_state=state(invalidated_at),
                invalidation_at=invalidated_at,
            ),
            ScenarioObservation(
                kind="base",
                threshold_kind="support",
                threshold=support,
                threshold_state=state(base_at),
                threshold_at=base_at,
                invalidation_level=invalidation,
                invalidation_state=state(invalidated_at),
                invalidation_at=invalidated_at,
            ),
            ScenarioObservation(
                kind="bear",
                threshold_kind="support",
                threshold=support,
                threshold_state=state(bear_at),
                threshold_at=bear_at,
                invalidation_state="unavailable",
            ),
        )

    @staticmethod
    def _target_stop_ordering(root: DecisionPacket, path: OutcomePath) -> str:
        target_at = next(
            (bar.timestamp for bar in path.bars if bar.high >= root.risk_plan.target_price),
            None,
        )
        stop_at = next(
            (bar.timestamp for bar in path.bars if bar.low <= root.risk_plan.stop_price),
            None,
        )
        if target_at is None and stop_at is None:
            return "neither" if path.bars else "unavailable"
        if target_at == stop_at:
            return "ambiguous_same_bar"
        if stop_at is None or (target_at is not None and target_at < stop_at):
            return "target_first"
        return "stop_first"

    def _paper(self, root: DecisionPacket, packet: DecisionPacket, now: datetime) -> PaperOutcome:
        if packet.disposition is DecisionDisposition.REJECT:
            return PaperOutcome(state="not_applicable")
        if packet.disposition is DecisionDisposition.WATCH:
            return PaperOutcome(state="watch_only")
        if packet.proposal_id is None or self.proposal_ledger is None:
            return PaperOutcome(
                state="unavailable", reason="exact proposal ledger binding is unavailable"
            )
        try:
            proposal = self.proposal_ledger.get(packet.proposal_id)
        except (ValueError, OSError) as error:
            return PaperOutcome(
                state="unavailable", reason=f"exact proposal is unavailable: {error}"
            )
        _validate_proposal_binding(root, packet, proposal)
        if proposal.created_at > now:
            raise ValueError("proposal postdates the review clock")
        if proposal.status is ProposalStatus.PENDING:
            return PaperOutcome(state="pending_no_order", proposal=proposal)
        if proposal.status is ProposalStatus.BLOCKED:
            return PaperOutcome(
                state="blocked",
                proposal=proposal,
                reason="; ".join(proposal.blockers) or "paper proposal is blocked",
            )
        if proposal.order_id is None or self.journal is None:
            return PaperOutcome(
                state="unavailable",
                proposal=proposal,
                reason="terminal proposal has no exact order journal binding",
            )
        try:
            order = self.journal.get(proposal.order_id)
        except (ValueError, OSError) as error:
            return PaperOutcome(
                state="unavailable",
                proposal=proposal,
                reason=f"exact order is unavailable: {error}",
            )
        _validate_order_binding(proposal, order)
        if order.created_at > now or any(event.timestamp > now for event in order.events):
            raise ValueError("order does not match exact proposal or review clock")
        if proposal.status is ProposalStatus.REJECTED:
            if order.status is not OrderStatus.REJECTED or order.fills:
                raise ValueError("risk-refused proposal must bind one rejected unfilled order")
            reason = next(
                (event.reason for event in reversed(order.events) if event.reason),
                None,
            )
            return PaperOutcome(
                state="risk_rejected",
                proposal=proposal,
                order=order,
                reason=reason or "; ".join(proposal.blockers) or "paper risk rejected",
            )
        if proposal.status is not ProposalStatus.CONFIRMED:
            raise ValueError("terminal paper proposal state is unsupported")
        if order.fills:
            return PaperOutcome(state="filled_open", proposal=proposal, order=order)
        if order.status not in {OrderStatus.ACCEPTED, OrderStatus.PENDING}:
            raise ValueError("confirmed unfilled proposal has an invalid order state")
        return PaperOutcome(state="accepted_unfilled", proposal=proposal, order=order)

    def _monitoring(self, packet: DecisionPacket, now: datetime) -> MonitoringOutcome:
        if packet.disposition is DecisionDisposition.REJECT:
            return MonitoringOutcome(status="not_applicable")
        if self.monitoring is None:
            return MonitoringOutcome(status="not_monitored")
        registration = self.monitoring.registration_for_packet(packet.packet_id)
        if registration is None:
            return MonitoringOutcome(status="not_monitored")
        evaluations = self.monitoring.evaluations(registration.registration_id)
        if any(item.observation.evaluated_at > now for item in evaluations):
            raise ValueError("monitoring evidence contains future knowledge")
        event_ids = tuple(
            dict.fromkeys(
                result.event_id
                for evaluation in evaluations
                for result in evaluation.results
                if result.event_id is not None
            )
        )
        if event_ids:
            return MonitoringOutcome(
                status="triggered",
                registration=registration,
                evaluations=evaluations,
                event_ids=event_ids,
            )
        return MonitoringOutcome(
            status="coverage_incomplete",
            registration=registration,
            evaluations=evaluations,
        )

    @staticmethod
    def _metrics(
        root: DecisionPacket, path: OutcomePath, paper: PaperOutcome
    ) -> tuple[OutcomeMetric, OutcomeMetric, OutcomeMetric, OutcomeMetric]:
        gross = (
            OutcomeMetric(
                status="available",
                value=(path.bars[-1].close - root.risk_plan.entry_price)
                / root.risk_plan.risk_per_unit,
            )
            if path.bars
            else _unavailable("no valid terminal close is available")
        )
        fills = paper.order.fills if paper.order is not None else []
        if fills:
            direction = 1.0 if paper.order.side is Side.BUY else -1.0
            quantity = sum(fill.quantity for fill in fills)
            average = sum(fill.quantity * fill.price for fill in fills) / quantity
            deviation = OutcomeMetric(
                status="available",
                value=(average - root.risk_plan.entry_price)
                * direction
                / root.risk_plan.risk_per_unit,
            )
            mark = (
                OutcomeMetric(
                    status="available",
                    value=(path.bars[-1].close - average)
                    * direction
                    / root.risk_plan.risk_per_unit,
                )
                if path.bars
                else _unavailable("filled entry has no valid local terminal mark")
            )
        else:
            deviation = _unavailable("no exact proposal-bound entry fill is available")
            mark = _unavailable("mark-to-market R requires an exact entry fill and mark")
        realized = _unavailable(
            "proposal-bound exit fills, attributable quantity, and complete fees are unavailable"
        )
        return gross, deviation, mark, realized

    def _compose(self, packet_id: str, now: datetime) -> DecisionOutcomeReviewState:
        root, packet = self._lineage(packet_id)
        if now < packet.created_at or now < root.as_of:
            raise ValueError("outcome review clock cannot predate the decision packet")
        artifact, expected_session_times, target_error = self._forecast_target(root)
        target_at = expected_session_times[-1] if expected_session_times else None
        path = self._path(root, artifact, expected_session_times, target_error, now)
        paper = self._paper(root, packet, now)
        monitoring = self._monitoring(packet, now)
        gross, deviation, mark, realized = self._metrics(root, path, paper)
        evidence_times = [packet.created_at, root.as_of, path.cutoff_at]
        if paper.proposal is not None:
            evidence_times.append(paper.proposal.created_at)
        if paper.order is not None:
            evidence_times.append(paper.order.created_at)
            evidence_times.extend(event.timestamp for event in paper.order.events)
        evidence_times.extend(
            evaluation.observation.evaluated_at for evaluation in monitoring.evaluations
        )
        evaluated_at = max(evidence_times)
        scenarios = self._scenario_observations(root, path)
        target_stop_ordering = self._target_stop_ordering(root, path)
        provisional = DecisionOutcomeSnapshot.model_construct(
            outcome_id="outcome-" + "0" * 24,
            packet_id=packet.packet_id,
            evaluated_at=evaluated_at,
            packet=packet,
            root_packet=root,
            horizon_target_at=target_at,
            attribution_policy_version="strict-close-v1",
            attribution_basis="completed_daily_close",
            attribution_equality="equality_does_not_cross",
            evidence_status=path.status,
            path=path,
            scenarios=scenarios,
            target_stop_ordering=target_stop_ordering,
            planned_reward_to_risk=root.risk_plan.reward_to_risk,
            gross_path_r=gross,
            entry_fill_deviation_r=deviation,
            mark_to_market_paper_r=mark,
            realized_paper_r=realized,
            paper=paper,
            monitoring=monitoring,
        )
        outcome = DecisionOutcomeSnapshot.model_validate(
            provisional.model_dump()
            | {
                "outcome_id": _identity(
                    "outcome",
                    provisional.model_dump(mode="json", exclude={"outcome_id"}),
                )
            }
        )
        return DecisionOutcomeReviewState(
            packet_id=packet.packet_id,
            root_packet=root,
            outcome=outcome,
            review=self.review_store.for_packet(packet.packet_id),
        )

    def preview(self, packet_id: str) -> DecisionOutcomeReviewState:
        now = _utc(self._now(), "outcome review clock")
        return self._compose(packet_id, now)

    @staticmethod
    def _normalize_note(note: str | None) -> str | None:
        if note is None:
            return None
        normalized = " ".join(note.split())
        if not normalized:
            return None
        if len(normalized) > 2_000:
            raise ValueError("review note exceeds 2000 characters")
        return normalized

    def save(
        self,
        packet_id: str,
        *,
        expected_outcome_id: str,
        classification: ReviewClassification | str,
        note: str | None,
    ) -> DecisionOutcomeReviewState:
        with self.review_store.transaction():
            existing = self.review_store.for_packet(packet_id)
            normalized_note = self._normalize_note(note)
            selected = ReviewClassification(classification)
            if existing is not None:
                if (
                    existing.outcome.outcome_id != expected_outcome_id
                    or existing.classification is not selected
                    or existing.note != normalized_note
                ):
                    raise ValueError("decision packet already has a different review")
                return DecisionOutcomeReviewState(
                    packet_id=packet_id,
                    root_packet=existing.outcome.root_packet,
                    outcome=existing.outcome,
                    review=existing,
                )
            now = _utc(self._now(), "outcome review clock")
            state = self._compose(packet_id, now)
            if state.outcome.outcome_id != expected_outcome_id:
                raise ValueError("expected outcome identity drifted before review save")
            final_state = self._compose(packet_id, now)
            if final_state.outcome != state.outcome:
                raise ValueError("source evidence changed before review append")
            provisional = DecisionReviewRecord.model_construct(
                review_id="review-" + "0" * 24,
                packet_id=packet_id,
                reviewed_at=now,
                outcome=final_state.outcome,
                classification=selected,
                note=normalized_note,
            )
            record = DecisionReviewRecord.model_validate(
                provisional.model_dump()
                | {
                    "review_id": _identity(
                        "review", provisional.model_dump(mode="json", exclude={"review_id"})
                    )
                }
            )
            saved = self.review_store.record(record)
            return final_state.model_copy(update={"review": saved})
