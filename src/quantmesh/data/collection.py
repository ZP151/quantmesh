"""Graph-level orchestration for existing trusted-data publishers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from quantmesh.data.artifacts import (
    ArtifactLayer,
    ArtifactManifest,
    ManifestConflictError,
    ManifestStore,
)
from quantmesh.data.calendars import (
    CONTINUOUS_UTC_VERSION,
    XNYS_REGULAR_VERSION,
    CalendarService,
    SessionPolicy,
)
from quantmesh.data.capabilities import DataKind
from quantmesh.data.checkpoints import (
    CheckpointIntegrityError,
    CheckpointStore,
    CollectionCheckpoint,
    GraphAdvance,
    GraphMember,
)
from quantmesh.data.envelopes import RawEnvelope
from quantmesh.data.instruments import CanonicalInstrumentId
from quantmesh.data.layout import validate_dataset_name
from quantmesh.data.objects import FABRIC_NAMESPACE, ObjectRef
from quantmesh.data.quality import (
    QualityBinding,
    QualityEvaluator,
    QualityEvidenceStore,
    QualityIntegrityError,
    QualityPolicy,
    QualityReport,
)
from quantmesh.domain.market_data import interval_to_timedelta
from quantmesh.domain.models import Venue


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


class CollectionJob(_FrozenContract):
    """A bounded provider request whose complete lineage is one logical graph."""

    provider_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    endpoints: tuple[str, ...] = Field(min_length=1)
    source_request_ids: tuple[str, ...] = Field(min_length=1)
    canonical_instruments: tuple[CanonicalInstrumentId, ...] = Field(min_length=1)
    data_kinds: tuple[DataKind, ...] = Field(min_length=1)
    intervals: tuple[str, ...] = ()
    calendar_version: str = Field(min_length=1)
    session_policy: SessionPolicy
    window_start: datetime
    window_end: datetime
    adjustment_policy: str = Field(min_length=1)
    schema_versions: tuple[str, ...] = Field(min_length=1)
    mapping_version: str = Field(min_length=1)
    code_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    collection_cycle: str = Field(default="initial", min_length=1)

    @field_validator("endpoints", "source_request_ids", "schema_versions")
    @classmethod
    def endpoints_are_unique_and_nonblank(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)) or any(not value.strip() for value in values):
            raise ValueError("endpoints must be unique and nonblank")
        return values

    @field_validator("collection_cycle")
    @classmethod
    def cycle_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("collection_cycle must not be blank")
        return value

    @field_validator("canonical_instruments", "data_kinds")
    @classmethod
    def values_are_unique(cls, values: tuple[Any, ...]) -> tuple[Any, ...]:
        if len(values) != len(set(str(value) for value in values)):
            raise ValueError("collection graph dimensions must be unique")
        return values

    @field_validator("window_start", "window_end")
    @classmethod
    def window_time_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("collection window times must be UTC")
        return value

    @model_validator(mode="after")
    def provider_calendar_and_window_agree(self) -> CollectionJob:
        if self.window_end < self.window_start:
            raise ValueError("window_end must not be before window_start")
        if DataKind.BARS in self.data_kinds:
            if not self.intervals:
                raise ValueError("bar collection jobs require at least one interval")
            if len(self.intervals) != len(set(self.intervals)):
                raise ValueError("collection intervals must be unique")
            for interval in self.intervals:
                interval_to_timedelta(interval)
        elif self.intervals:
            raise ValueError("only collection graphs containing bars declare intervals")
        prefixes = {item.value.split(":", maxsplit=1)[0] for item in self.canonical_instruments}
        if self.provider_id in {"moomoo-opend", "fixture-moomoo"}:
            expected = ({"moomoo"}, XNYS_REGULAR_VERSION, SessionPolicy.REGULAR)
        elif self.provider_id in {"hyperliquid-public", "fixture-hyperliquid-public"}:
            expected = (
                {"hyperliquid"},
                CONTINUOUS_UTC_VERSION,
                SessionPolicy.CONTINUOUS,
            )
        else:
            raise ValueError("provider is outside the bounded trusted-data universe")
        if (prefixes, self.calendar_version, self.session_policy) != expected:
            raise ValueError("provider, instrument, calendar and session policy disagree")
        return self

    def identity_body(self) -> dict[str, Any]:
        return {
            "adjustment_policy": self.adjustment_policy,
            "calendar_version": self.calendar_version,
            "canonical_instruments": [item.value for item in self.canonical_instruments],
            "code_commit": self.code_commit,
            "collection_cycle": self.collection_cycle,
            "contract": "collection-job-v2",
            "data_kinds": [item.value for item in self.data_kinds],
            "endpoints": list(self.endpoints),
            "intervals": list(self.intervals),
            "mapping_version": self.mapping_version,
            "provider_id": self.provider_id,
            "schema_versions": list(self.schema_versions),
            "source_request_ids": list(self.source_request_ids),
            "session_policy": self.session_policy.value,
            "window_end": self.window_end.isoformat(),
            "window_start": self.window_start.isoformat(),
        }

    @computed_field
    @property
    def job_id(self) -> str:
        return _digest(self.identity_body())


class CollectionRun(_FrozenContract):
    job_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt: int = Field(ge=1, le=2**63 - 1)

    @classmethod
    def for_job(cls, job: CollectionJob, *, attempt: int) -> CollectionRun:
        return cls(
            job_id=job.job_id,
            run_id=_digest({"contract": "collection-run-v2", "job_id": job.job_id}),
            attempt=attempt,
        )


class PublicationStage(StrEnum):
    RAW = "raw"
    DERIVED = "derived"
    MANIFEST = "manifest"
    PREFLIGHT = "preflight"
    QUALITY = "quality"
    COMMIT = "commit"


class InjectedCrash(RuntimeError):
    """Test-only interruption after a durable graph boundary."""


class PreflightStatus(StrEnum):
    INTEGRITY_ONLY = "integrity-only-not-quality-evaluated"


class IntegrityPreflight(_FrozenContract):
    """Typed non-qualifying evidence; Task 10 alone may issue quality status."""

    contract: Literal["publication-integrity-preflight-v1"] = "publication-integrity-preflight-v1"
    status: PreflightStatus = PreflightStatus.INTEGRITY_ONLY
    job_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_ids: tuple[str, ...] = Field(min_length=1)
    object_digests: tuple[str, ...] = Field(min_length=1)
    manifests_staged: Literal[True]
    objects_verified: Literal[True]
    parents_resolvable: Literal[True]

    @computed_field
    @property
    def preflight_id(self) -> str:
        return _digest(self.model_dump(mode="json", exclude={"preflight_id"}))


class QualityPublicationContext(_FrozenContract):
    """Exact candidate checkpoint projection supplied to a quality builder."""

    job_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt: int = Field(ge=1)
    manifest_ids: tuple[str, ...] = Field(min_length=1)
    preflight_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_body_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    window_start: datetime
    window_end: datetime
    updated_at: datetime

    @field_validator("window_start", "window_end", "updated_at")
    @classmethod
    def times_are_utc(cls, value: datetime, info) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError(f"{info.field_name} must be UTC")
        return value

    @model_validator(mode="after")
    def window_is_positive(self) -> QualityPublicationContext:
        if self.window_end <= self.window_start:
            raise ValueError("quality publication window must be positive")
        return self


class PendingGraph(_FrozenContract):
    job_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    job_body: dict[str, Any]
    run_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt: int = Field(ge=1)
    manifest_ids: tuple[str, ...] = Field(min_length=1)
    dataset_ids: tuple[str, ...] = Field(min_length=1)
    members: tuple[GraphMember, ...] = Field(min_length=1)
    advances: tuple[GraphAdvance, ...]
    source_snapshot: dict[str, Any] | None
    provider_cursor: str = Field(min_length=1)
    last_complete_source_event: str = Field(min_length=1)
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def updated_at_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("updated_at must be UTC")
        return value

    @field_validator("manifest_ids")
    @classmethod
    def manifest_ids_are_unique_digests(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)) or any(
            len(value) != 64 or any(char not in "0123456789abcdef" for char in value)
            for value in values
        ):
            raise ValueError("pending manifest IDs must be unique SHA-256 digests")
        return values

    @field_validator("dataset_ids")
    @classmethod
    def dataset_ids_are_unique_and_valid(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("pending dataset IDs must be unique")
        for value in values:
            validate_dataset_name(value)
        return values


class CollectionPublication(_FrozenContract):
    job_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt: int = Field(ge=1)
    manifest_ids: tuple[str, ...] = Field(min_length=1)
    preflight_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    quality_report_id: str | None = None


class StagingManifestStore:
    """ManifestStore facade that records candidates without changing visibility."""

    def __init__(
        self,
        store: ManifestStore,
        *,
        collection_run_id: str | None = None,
        crash_after: PublicationStage | None = None,
        progress: Callable[[int, ArtifactManifest], None] | None = None,
    ) -> None:
        self._store = store
        self.root = store.root
        self.objects = store.objects
        self.advances: list[GraphAdvance] = []
        self._crash_after = crash_after
        self._raw_boundary_seen = False
        self._derived_boundary_seen = False
        self.stages_graphs = True
        self._progress = progress
        self._manifest_count = 0
        self._collection_run_id = collection_run_id

    @property
    def collection_run_id(self) -> str | None:
        return self._collection_run_id

    def current(self, dataset_id: str):
        return self._store.current(dataset_id)

    def manifests(self, dataset_id: str):
        return self._store.manifests(dataset_id)

    def open(self, manifest_id: str):
        return self._store.open(manifest_id)

    def manifest_path(self, dataset_id: str, manifest_id: str) -> Path:
        return self._store.manifest_path(dataset_id, manifest_id)

    def publish(self, manifest: ArtifactManifest, *, expected_current: str | None) -> None:
        current = self._store.current(manifest.dataset_id)
        actual = None if current is None else current.manifest.manifest_id
        revision = 0 if current is None else current.manifest.compatibility_revision
        if actual != expected_current:
            raise ValueError(f"dataset {manifest.dataset_id} changed while staging its graph")
        position = self._manifest_count
        self._manifest_count += 1
        if actual == manifest.manifest_id:
            if self._store.open(manifest.manifest_id).manifest != manifest:
                raise ValueError("current manifest bytes disagree with staged candidate")
            if self._progress is not None:
                self._progress(position, manifest)
            self._stage_boundary(manifest)
            return
        if current is not None and manifest.knowledge_start <= current.manifest.knowledge_end:
            raise ManifestConflictError(
                "knowledge time must advance beyond the current revision: "
                f"current ends {current.manifest.knowledge_end.isoformat()}, "
                f"target starts {manifest.knowledge_start.isoformat()}"
            )
        if manifest.compatibility_revision != revision + 1:
            raise ValueError("staged manifest revision is not consecutive")
        self._store.stage(manifest)
        self.advances.append(
            GraphAdvance(
                dataset_id=manifest.dataset_id,
                expected_current=actual,
                expected_revision=revision,
                expected_knowledge_end=(
                    None if current is None else current.manifest.knowledge_end
                ),
                manifest_id=manifest.manifest_id,
                revision=manifest.compatibility_revision,
                knowledge_start=manifest.knowledge_start,
                knowledge_end=manifest.knowledge_end,
            )
        )
        if self._progress is not None:
            self._progress(position, manifest)
        self._stage_boundary(manifest)

    def _stage_boundary(self, manifest: ArtifactManifest) -> None:
        if manifest.layer is ArtifactLayer.RAW and not self._raw_boundary_seen:
            self._raw_boundary_seen = True
            self._crash(PublicationStage.RAW)
        elif manifest.layer is not ArtifactLayer.RAW and not self._derived_boundary_seen:
            self._derived_boundary_seen = True
            self._crash(PublicationStage.DERIVED)

    def _crash(self, stage: PublicationStage) -> None:
        if self._crash_after is stage:
            raise InjectedCrash(f"injected crash after {stage.value}")


class CollectionCoordinator:
    """Atomically commit complete manifest graphs built by venue publishers."""

    def __init__(self, store: ManifestStore) -> None:
        self.store = store
        self.checkpoints = CheckpointStore(store.root)
        self.quality = QualityEvidenceStore(store.root)

    def has_state(self, job: CollectionJob) -> bool:
        """Return whether this job can resume without contacting its provider."""
        with self.checkpoints.writer():
            self.checkpoints.repair_source_snapshots()
            self.checkpoints.repair_graph_owners()
            self.checkpoints.repair_commit_journals()
            return (
                self.checkpoints.get(
                    job.job_id, _verify_quality_evidence=False
                )
                is not None
                or self.checkpoints.pending(job.job_id) is not None
            )

    def capture_source(
        self,
        job: CollectionJob,
        *,
        media_type: str,
        payload: bytes,
        raw_payloads: tuple[bytes, ...],
    ) -> None:
        """Persist exact provider output before any manifest transformation."""
        reference = self.store.objects.put_bytes(media_type, payload)
        raw_digests = tuple(
            self.store.objects.put_bytes("application/octet-stream", item).digest
            for item in raw_payloads
        )
        with self.checkpoints.writer():
            self.checkpoints.save_source_snapshot(
                job.job_id,
                media_type=reference.media_type,
                digest=reference.digest,
                byte_length=reference.byte_length,
                raw_object_digests=raw_digests,
            )

    def source(self, job: CollectionJob) -> bytes | None:
        """Load the exact provider batch already bound to a job."""
        snapshot = self.checkpoints.source_snapshot(job.job_id)
        if snapshot is None:
            return None
        media_type, digest, byte_length, _raw_digests = snapshot
        return self.store.objects.get_bytes(
            ObjectRef(
                digest=digest,
                media_type=media_type,
                byte_length=byte_length,
            )
        )

    def run(
        self,
        job: CollectionJob,
        *,
        producer: Callable[[StagingManifestStore], tuple[str, ...]],
        provider_cursor: str,
        last_complete_source_event: str,
        updated_at: datetime,
        crash_after: PublicationStage | None = None,
        quality_builder: Callable[[QualityPublicationContext], QualityReport] | None = None,
    ) -> CollectionPublication:
        """Stage through an existing publisher, preflight, then commit once."""
        with self.checkpoints.writer():
            self.checkpoints.repair_source_snapshots()
            self.checkpoints.repair_graph_owners()
            self.checkpoints.repair_commit_journals()
            completed = self.checkpoints.get(
                job.job_id, _verify_quality_evidence=False
            )
            if completed is not None:
                return self._verified_publication(completed, job=job)
            pending_json = self.checkpoints.pending(job.job_id)
            if pending_json is None:
                attempt = self.checkpoints.next_attempt(job.job_id)
                run = CollectionRun.for_job(job, attempt=attempt)
                staging = StagingManifestStore(
                    self.store,
                    collection_run_id=run.run_id,
                    crash_after=crash_after,
                    progress=lambda position, manifest: self.checkpoints.record_progress(
                        job.job_id,
                        position=position,
                        dataset_id=manifest.dataset_id,
                        manifest_id=manifest.manifest_id,
                        layer=manifest.layer.value,
                    ),
                )
                manifest_ids = producer(staging)
                manifests = tuple(
                    self.store.open(manifest_id).manifest for manifest_id in manifest_ids
                )
                if len({manifest.dataset_id for manifest in manifests}) != len(manifests):
                    raise ValueError("collection graph may contain each dataset only once")
                members = tuple(
                    GraphMember(
                        dataset_id=manifest.dataset_id,
                        manifest_id=manifest.manifest_id,
                        revision=manifest.compatibility_revision,
                        knowledge_end=manifest.knowledge_end,
                    )
                    for manifest in sorted(manifests, key=lambda item: item.dataset_id)
                )
                pending = PendingGraph(
                    job_id=job.job_id,
                    job_body=job.identity_body(),
                    run_id=run.run_id,
                    attempt=attempt,
                    manifest_ids=manifest_ids,
                    dataset_ids=tuple(member.dataset_id for member in members),
                    members=members,
                    advances=tuple(staging.advances),
                    source_snapshot=self._source_snapshot_body(job),
                    provider_cursor=provider_cursor,
                    last_complete_source_event=last_complete_source_event,
                    updated_at=updated_at,
                )
                self._verify_graph(pending.manifest_ids)
                self._validate_job_graph(job, pending.manifest_ids)
                pending_json = _canonical_bytes(pending.model_dump(mode="json")).decode()
                self.checkpoints.save_pending(job.job_id, pending_json)
                self._crash(crash_after, PublicationStage.MANIFEST)
            pending = PendingGraph.model_validate_json(pending_json)
            if pending.job_body != job.identity_body() or pending.job_id != job.job_id:
                raise ValueError("pending graph is not bound to the requested collection job")
            if pending.dataset_ids != tuple(member.dataset_id for member in pending.members):
                raise ValueError("pending dataset membership disagrees with its manifests")
            observed_members = tuple(
                GraphMember(
                    dataset_id=manifest.dataset_id,
                    manifest_id=manifest.manifest_id,
                    revision=manifest.compatibility_revision,
                    knowledge_end=manifest.knowledge_end,
                )
                for manifest in sorted(
                    (self.store.open(manifest_id).manifest for manifest_id in pending.manifest_ids),
                    key=lambda item: item.dataset_id,
                )
            )
            if pending.members != observed_members:
                raise ValueError("pending graph member anchors changed after staging")
            if pending.source_snapshot != self._source_snapshot_body(job):
                raise ValueError("pending graph source snapshot changed after staging")
            self._validate_job_graph(job, pending.manifest_ids)
            self._require_commit_targets(pending)

            preflight = self._preflight(pending)
            payload = _canonical_bytes(preflight.model_dump(mode="json", exclude={"preflight_id"}))
            reference = self.store.objects.put_bytes(
                "application/vnd.quantmesh.integrity-preflight+json", payload
            )
            if reference.digest != preflight.preflight_id:
                raise ValueError("preflight object identity changed while writing")
            self._crash(crash_after, PublicationStage.PREFLIGHT)

            raw_digests = self._raw_object_digests(pending.manifest_ids)
            checkpoint_projection = CollectionCheckpoint(
                job_id=pending.job_id,
                generation=1,
                provider_cursor=pending.provider_cursor,
                last_complete_source_event=pending.last_complete_source_event,
                raw_object_digests=raw_digests,
                manifest_ids=pending.manifest_ids,
                preflight_id=preflight.preflight_id,
                quality_report_id=None,
                run_id=pending.run_id,
                attempt=pending.attempt,
                updated_at=pending.updated_at,
            )
            checkpoint_body_digest = _checkpoint_body_digest(checkpoint_projection)
            quality_report_id = None
            quality_admitted = self._quality_admitted_manifest_ids(
                pending.manifest_ids
            )
            selected_quality_builder = quality_builder
            if selected_quality_builder is None and not job.provider_id.startswith("fixture-"):
                selected_quality_builder = self._default_quality_builder(job)
            if selected_quality_builder is not None:
                report = selected_quality_builder(
                    QualityPublicationContext(
                        job_id=pending.job_id,
                        run_id=pending.run_id,
                        attempt=pending.attempt,
                        manifest_ids=pending.manifest_ids,
                        preflight_id=preflight.preflight_id,
                        checkpoint_body_digest=checkpoint_body_digest,
                        window_start=job.window_start,
                        window_end=job.window_end,
                        updated_at=pending.updated_at,
                    )
                )
                self.quality.record_report(
                    report,
                    admitted_manifest_ids=quality_admitted,
                )
                for binding in report.bindings:
                    evaluation = self.quality.load(binding.evaluation_id)
                    manifest = self.store.open(binding.manifest_id).manifest
                    expected_policy = self._quality_policy_for_manifest(manifest)
                    if evaluation.policy_id != expected_policy.policy_id:
                        raise ValueError(
                            "real quality report does not use the authoritative policy"
                        )
                    if (
                        evaluation.window_start != job.window_start
                        or evaluation.window_end
                        != _quality_window_end(manifest, job.window_end)
                        or evaluation.evaluated_at != pending.updated_at
                    ):
                        raise ValueError(
                            "real quality report does not use the authoritative window"
                        )
                if (
                    report.job_id != pending.job_id
                    or report.run_id != pending.run_id
                    or report.checkpoint_body_digest != checkpoint_body_digest
                    or tuple(binding.manifest_id for binding in report.bindings)
                    != tuple(sorted(pending.manifest_ids))
                ):
                    raise ValueError("quality report disagrees with its candidate checkpoint")
                quality_report_id = report.report_id
            self._crash(crash_after, PublicationStage.QUALITY)
            checkpoint = CollectionCheckpoint(
                **checkpoint_projection.model_dump(exclude={"quality_report_id"}),
                quality_report_id=quality_report_id,
            )
            commit_id = _digest(
                {
                    "checkpoint": checkpoint.model_dump(mode="json"),
                    "advances": [advance.model_dump(mode="json") for advance in pending.advances],
                    "owned_dataset_ids": list(pending.dataset_ids),
                    "members": [member.model_dump(mode="json") for member in pending.members],
                    "source_snapshot": pending.source_snapshot,
                }
            )
            self.checkpoints.commit(
                previous=None,
                next_checkpoint=checkpoint,
                advances=pending.advances,
                commit_id=commit_id,
                owned_dataset_ids=pending.dataset_ids,
                members=pending.members,
                source_snapshot=pending.source_snapshot,
            )
            self._crash(crash_after, PublicationStage.COMMIT)
            return self._verified_publication(checkpoint, job=job)

    def _preflight(self, pending: PendingGraph) -> IntegrityPreflight:
        objects = self._verify_graph(pending.manifest_ids)
        return IntegrityPreflight(
            job_id=pending.job_id,
            run_id=pending.run_id,
            manifest_ids=pending.manifest_ids,
            object_digests=objects,
            manifests_staged=True,
            objects_verified=True,
            parents_resolvable=True,
        )

    def _verified_publication(
        self, checkpoint: CollectionCheckpoint, *, job: CollectionJob
    ) -> CollectionPublication:
        if checkpoint.job_id != job.job_id:
            raise ValueError("checkpoint is not bound to the requested collection job")
        self._source_snapshot_body(job)
        self._validate_job_graph(job, checkpoint.manifest_ids)
        objects = self._verify_graph(checkpoint.manifest_ids)
        preflight_path = (
            self.store.root
            / FABRIC_NAMESPACE
            / "objects"
            / "sha256"
            / checkpoint.preflight_id[:2]
            / checkpoint.preflight_id
        )
        try:
            byte_length = preflight_path.lstat().st_size
        except FileNotFoundError as error:
            raise ValueError("checkpoint preflight object is missing") from error
        payload = self.store.objects.get_bytes(
            ObjectRef(
                digest=checkpoint.preflight_id,
                media_type="application/vnd.quantmesh.integrity-preflight+json",
                byte_length=byte_length,
            )
        )
        preflight = IntegrityPreflight.model_validate_json(payload)
        if (
            preflight.job_id != checkpoint.job_id
            or preflight.run_id != checkpoint.run_id
            or preflight.manifest_ids != checkpoint.manifest_ids
            or preflight.object_digests != objects
            or preflight.status is not PreflightStatus.INTEGRITY_ONLY
            or not preflight.manifests_staged
            or not preflight.objects_verified
            or not preflight.parents_resolvable
        ):
            raise ValueError("checkpoint and preflight evidence disagree")
        expected_raw = self._raw_object_digests(checkpoint.manifest_ids)
        if checkpoint.raw_object_digests != expected_raw:
            raise ValueError("checkpoint raw object identities disagree with its graph")
        fixture = job.provider_id.startswith("fixture-")
        if fixture and checkpoint.quality_report_id is not None:
            raise ValueError("fixture checkpoints must not carry real-data quality evidence")
        if not fixture and checkpoint.quality_report_id is None:
            raise ValueError("real checkpoint is unqualified without quality evidence")
        if checkpoint.quality_report_id is not None:
            try:
                report = self.quality.verify_report(
                    checkpoint.quality_report_id,
                    admitted_manifest_ids=self._quality_admitted_manifest_ids(
                        checkpoint.manifest_ids
                    ),
                )
            except QualityIntegrityError as error:
                raise CheckpointIntegrityError(
                    "checkpoint quality evidence is invalid"
                ) from error
            if (
                report.job_id != checkpoint.job_id
                or report.run_id != checkpoint.run_id
                or report.checkpoint_body_digest != _checkpoint_body_digest(checkpoint)
                or tuple(binding.manifest_id for binding in report.bindings)
                != tuple(sorted(checkpoint.manifest_ids))
            ):
                raise ValueError("checkpoint and quality report evidence disagree")
        return CollectionPublication(
            job_id=checkpoint.job_id,
            run_id=checkpoint.run_id,
            attempt=checkpoint.attempt,
            manifest_ids=checkpoint.manifest_ids,
            preflight_id=checkpoint.preflight_id,
            quality_report_id=checkpoint.quality_report_id,
        )

    def _default_quality_builder(
        self, job: CollectionJob
    ) -> Callable[[QualityPublicationContext], QualityReport]:
        """Create deterministic evidence for every real candidate graph member."""

        def build(context: QualityPublicationContext) -> QualityReport:
            if context.job_id != job.job_id:
                raise ValueError("quality context is not bound to the collection job")
            admitted = self._quality_admitted_manifest_ids(context.manifest_ids)
            bindings: list[QualityBinding] = []
            evaluator = QualityEvaluator(self.store)
            for manifest_id in context.manifest_ids:
                manifest = self.store.open(manifest_id).manifest
                policy = self._quality_policy_for_manifest(manifest)
                self.quality.record_policy(policy)
                window_end = _quality_window_end(manifest, context.window_end)
                observation = evaluator.measure(
                    policy,
                    manifest_id,
                    window_start=context.window_start,
                    window_end=window_end,
                    evaluated_at=context.updated_at,
                    admitted_manifest_ids=admitted,
                )
                evaluation = evaluator.evaluate(
                    policy,
                    manifest_id,
                    window_start=context.window_start,
                    window_end=window_end,
                    observation=observation,
                    admitted_manifest_ids=admitted,
                )
                self.quality.record(
                    evaluation,
                    admitted_manifest_ids=admitted,
                )
                bindings.append(
                    QualityBinding(
                        manifest_id=manifest_id,
                        evaluation_id=evaluation.evaluation_id,
                    )
                )
            return QualityReport.build(
                job_id=context.job_id,
                run_id=context.run_id,
                checkpoint_body_digest=context.checkpoint_body_digest,
                bindings=tuple(
                    sorted(
                        bindings,
                        key=lambda item: (item.manifest_id, item.evaluation_id),
                    )
                ),
            )

        return build

    def _quality_admitted_manifest_ids(
        self, candidate_manifest_ids: tuple[str, ...]
    ) -> frozenset[str]:
        admitted = set(candidate_manifest_ids)
        for manifest_id in candidate_manifest_ids:
            manifest = self.store.open(manifest_id).manifest
            admitted.update(
                item.manifest_id
                for item in self.store.manifests(manifest.dataset_id)
            )
        return frozenset(admitted)

    @staticmethod
    def _quality_policy_for_manifest(
        manifest: ArtifactManifest,
    ) -> QualityPolicy:
        venue = (
            Venue.MOOMOO
            if manifest.canonical_instrument.value.startswith("moomoo:")
            else Venue.HYPERLIQUID
        )
        step_seconds = (
            int(interval_to_timedelta(manifest.interval).total_seconds())
            if manifest.interval is not None
            else 86_400
        )
        return QualityPolicy(
            venue=venue,
            layer=manifest.layer,
            data_kind=manifest.data_kind,
            interval=manifest.interval,
            calendar_version=manifest.calendar_version,
            session_policy=manifest.session_policy,
            grace_period_seconds=3_600 if venue is Venue.MOOMOO else 300,
            minimum_coverage_ratio=1.0,
            max_freshness_seconds=max(600, step_seconds * 2),
            # Leave a real observation window after grace expires and scale with
            # the interval: a next-day daily collection is far older than a
            # same-minute intraday collection. Equal grace and latency
            # thresholds make a passing post-grace evaluation possible only at
            # one exact instant.
            max_latency_seconds=max(7_200 if venue is Venue.MOOMOO else 600, step_seconds * 2),
            require_terminal_pagination=(
                venue is Venue.MOOMOO
                and manifest.layer is ArtifactLayer.RAW
                and manifest.data_kind in {DataKind.BARS, DataKind.SPLITS}
            ),
        )

    def _source_snapshot_body(self, job: CollectionJob) -> dict[str, Any] | None:
        snapshot = self.checkpoints.source_snapshot(job.job_id)
        if snapshot is None:
            if job.provider_id.startswith("fixture-"):
                return None
            raise ValueError("real collection graph has no durable source snapshot")
        media_type, digest, byte_length, raw_digests = snapshot
        self.store.objects.get_bytes(
            ObjectRef(
                digest=digest,
                media_type=media_type,
                byte_length=byte_length,
            )
        )
        return {
            "byte_length": byte_length,
            "digest": digest,
            "job_id": job.job_id,
            "media_type": media_type,
            "raw_object_digests": list(raw_digests),
        }

    def _verify_graph(self, manifest_ids: tuple[str, ...]) -> tuple[str, ...]:
        if not manifest_ids or len(manifest_ids) != len(set(manifest_ids)):
            raise ValueError("publication graph manifest IDs must be unique and nonempty")
        manifests = tuple(self.store.open(manifest_id).manifest for manifest_id in manifest_ids)
        admitted = set(manifest_ids)
        object_digests: list[str] = []
        for manifest in manifests:
            for parent_id in manifest.parent_manifest_ids:
                if parent_id not in admitted:
                    parent = self.store.open(parent_id).manifest
                    committed = {
                        item.manifest_id for item in self.store.manifests(parent.dataset_id)
                    }
                    if parent_id not in committed:
                        raise ValueError("external parent is not in validated committed history")
            for reference in manifest.objects:
                self.store.objects.get_bytes(reference)
                object_digests.append(reference.digest)
        return tuple(dict.fromkeys(object_digests))

    def _validate_job_graph(self, job: CollectionJob, manifest_ids: tuple[str, ...]) -> None:
        manifests = tuple(self.store.open(item).manifest for item in manifest_ids)
        raw = tuple(item for item in manifests if item.layer is ArtifactLayer.RAW)
        envelopes: list[RawEnvelope] = []
        for manifest in raw:
            references = [
                reference
                for reference in manifest.objects
                if reference.media_type == "application/vnd.quantmesh.raw-envelope+json"
            ]
            if len(references) != 1:
                raise ValueError("raw graph role must contain exactly one source envelope")
            envelopes.append(
                RawEnvelope.model_validate_json(self.store.objects.get_bytes(references[0]))
            )
        if not envelopes:
            raise ValueError("collection graph has no raw source envelopes")
        snapshot = self.checkpoints.source_snapshot(job.job_id)
        if snapshot is None and not job.provider_id.startswith("fixture-"):
            raise ValueError("real collection graph has no durable source snapshot")
        if snapshot is not None:
            expected_raw_digests = snapshot[3]
            observed_raw_digests = tuple(item.raw_object.digest for item in envelopes)
            if observed_raw_digests != expected_raw_digests:
                raise ValueError("source snapshot raw payloads disagree with raw envelope objects")
        if {item.provider_id for item in envelopes} != {job.provider_id}:
            raise ValueError("collection provider disagrees with raw graph evidence")
        observed_endpoints = {item.endpoint for item in envelopes}
        if observed_endpoints != set(job.endpoints):
            raise ValueError("collection endpoints disagree with raw graph evidence")
        if {item.request_id for item in envelopes} != set(job.source_request_ids):
            raise ValueError("collection request IDs disagree with raw graph evidence")
        if {item.canonical_instrument for item in envelopes} != set(job.canonical_instruments):
            raise ValueError("collection instruments disagree with raw graph evidence")
        if {item.data_kind for item in envelopes} != set(job.data_kinds):
            raise ValueError("collection data kinds disagree with raw graph evidence")
        if {item.schema_version for item in envelopes} != set(job.schema_versions):
            raise ValueError("collection schemas disagree with raw graph evidence")
        if any(
            (item.collection_window_start or item.request_window_start) != job.window_start
            or (item.collection_window_end or item.request_window_end) != job.window_end
            for item in envelopes
        ):
            raise ValueError("collection window disagrees with raw graph evidence")
        if any(
            item.calendar_version != job.calendar_version
            or item.session_policy is not job.session_policy
            or item.instrument_catalog_id != job.mapping_version
            or item.code_commit != job.code_commit
            for item in manifests
        ):
            raise ValueError(
                "collection calendar, session, catalog mapping or code commit disagrees"
            )
        expected_run_id = CollectionRun.for_job(job, attempt=1).run_id
        if {item.collection_run_id for item in manifests} != {expected_run_id}:
            raise ValueError("manifest graph is not bound to the deterministic collection run")
        intervals = {
            item.interval
            for item in manifests
            if item.data_kind is DataKind.BARS and item.interval is not None
        }
        if intervals != set(job.intervals):
            raise ValueError("collection intervals disagree with manifest graph")
        adjusted_policies = {
            item.adjustment_policy
            for item in manifests
            if item.layer in {ArtifactLayer.ADJUSTED, ArtifactLayer.FEATURE}
        }
        if adjusted_policies != {job.adjustment_policy}:
            raise ValueError("collection adjustment policy disagrees with manifest graph")

    def _raw_object_digests(self, manifest_ids: tuple[str, ...]) -> tuple[str, ...]:
        digests = [
            reference.digest
            for manifest_id in manifest_ids
            for manifest in (self.store.open(manifest_id).manifest,)
            if manifest.layer is ArtifactLayer.RAW
            for reference in manifest.objects
        ]
        if not digests:
            raise ValueError("publication graph has no raw evidence")
        return tuple(dict.fromkeys(digests))

    def _require_commit_targets(self, pending: PendingGraph) -> None:
        advances = {advance.manifest_id: advance for advance in pending.advances}
        if any(advance.manifest_id not in pending.manifest_ids for advance in pending.advances):
            raise ValueError("graph advance references a manifest outside the graph")
        for manifest_id in pending.manifest_ids:
            manifest = self.store.open(manifest_id).manifest
            current = self.store.current(manifest.dataset_id)
            current_id = None if current is None else current.manifest.manifest_id
            if current_id == manifest_id:
                continue
            advance = advances.get(manifest_id)
            if advance is None or advance.dataset_id != manifest.dataset_id:
                raise ValueError(
                    "publication graph contains a non-current manifest without an advance"
                )

    @staticmethod
    def _crash(requested: PublicationStage | None, completed: PublicationStage) -> None:
        if requested is completed:
            raise InjectedCrash(f"injected crash after {completed.value}")


def _checkpoint_body_digest(checkpoint: CollectionCheckpoint) -> str:
    """Hash the final checkpoint projection without its report back-reference."""
    return _digest(checkpoint.model_dump(mode="json", exclude={"quality_report_id"}))


def _quality_window_end(
    manifest: ArtifactManifest, requested_end: datetime
) -> datetime:
    """Convert an inclusive provider terminal bar open to an exclusive SLA bound."""
    if manifest.data_kind is not DataKind.BARS or manifest.interval is None:
        return requested_end
    step = interval_to_timedelta(manifest.interval)
    if manifest.canonical_instrument.value.startswith("hyperliquid:"):
        return requested_end + step
    if step >= timedelta(days=1):
        zone = ZoneInfo("America/New_York")
        local = requested_end.astimezone(zone)
        if local.time() == time.min:
            return datetime.combine(
                local.date() + timedelta(days=1), time.min, tzinfo=zone
            ).astimezone(UTC)
        return requested_end
    sessions = CalendarService().sessions(
        "XNYS",
        requested_end.date(),
        requested_end.date(),
        policy=manifest.session_policy,
    )
    if any(
        session.open_at <= requested_end < session.close_at
        and not (requested_end - session.open_at) % step
        for session in sessions
    ):
        return requested_end + step
    return requested_end
