"""Read-only catalog over committed trusted-data manifests and quality evidence."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from quantmesh.data.artifacts import (
    ArtifactDataset,
    ArtifactLayer,
    ArtifactManifest,
    ManifestIntegrityError,
    ManifestStore,
)
from quantmesh.data.calendars import SessionPolicy
from quantmesh.data.capabilities import DataKind, EntitlementState, ProviderAccess
from quantmesh.data.checkpoints import CheckpointStore, CollectionCheckpoint
from quantmesh.data.layout import validate_dataset_name
from quantmesh.data.objects import FABRIC_NAMESPACE, is_reparse_point
from quantmesh.data.overlap_resolutions import (
    OverlapResolutionIntegrityError,
    OverlapResolutionStore,
    ResolutionUsePolicy,
)
from quantmesh.data.quality import QualityEvaluationV2, QualityEvidenceStore, QualityStatus


class CatalogIntegrityError(RuntimeError):
    """Committed catalog state is missing or internally inconsistent."""


class CatalogNotFoundError(ValueError):
    """An exact manifest is not part of committed catalog state."""


class CatalogQualificationError(ValueError):
    """A committed manifest is not qualified for downstream research."""


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


class CatalogQuality(_FrozenContract):
    """Exact immutable evaluation qualifying one manifest."""

    contract: str = Field(default="catalog-quality-v2", pattern=r"^catalog-quality-v2$")
    report_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: QualityStatus
    original_status: QualityStatus = QualityStatus.PASS
    issue_codes: tuple[str, ...]
    evaluated_at: datetime
    expected_count: int = Field(ge=0)
    observed_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    hash_mismatch_count: int = Field(ge=0)
    schema_mismatch_count: int = Field(ge=0)
    order_violation_count: int = Field(ge=0)
    overlap_conflict_count: int = Field(ge=0)
    synthetic_row_count: int = Field(ge=0)
    freshness_seconds: int | None = Field(default=None, ge=0)
    latency_seconds: int | None = Field(default=None, ge=0)
    pagination_terminal: bool | None
    source_rights_known: bool
    unavailable_reason: str | None = None
    resolution_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    qualification: str = Field(
        default="clean",
        pattern=r"^(clean|qualified-with-resolution|failed)$",
    )
    use_policy: ResolutionUsePolicy | None = None

    @field_validator("evaluated_at")
    @classmethod
    def evaluated_at_is_utc(cls, value: datetime) -> datetime:
        if not _is_utc(value):
            raise ValueError("catalog quality time must be UTC")
        return value

    @model_validator(mode="after")
    def status_matches_issues(self) -> Self:
        if (self.status is QualityStatus.PASS) != (not self.issue_codes):
            raise ValueError("catalog quality status and issues disagree")
        if self.status is not self.original_status:
            raise ValueError("catalog quality must preserve the original evaluation status")
        if self.qualification == "clean":
            if self.status is not QualityStatus.PASS or self.resolution_id or self.use_policy:
                raise ValueError("clean catalog quality requires an ordinary pass")
        elif self.qualification == "qualified-with-resolution":
            if (
                self.resolution_id is None
                or self.use_policy is None
                or not (
                    self.status is QualityStatus.PASS
                    or (
                        self.status is QualityStatus.FAIL
                        and self.issue_codes == ("historical-live-overlap",)
                    )
                )
            ):
                raise ValueError("resolved catalog quality requires one exact overlap resolution")
        elif self.status is QualityStatus.PASS or self.resolution_id or self.use_policy:
            raise ValueError("failed catalog quality cannot carry a resolution policy")
        return self


class CatalogCheckpoint(_FrozenContract):
    """Latest collection checkpoint owning a cataloged manifest."""

    job_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation: int = Field(ge=1)
    run_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt: int = Field(ge=1)
    provider_cursor: str = Field(min_length=1)
    last_complete_source_event: str = Field(min_length=1)
    updated_at: datetime
    quality_report_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("provider_cursor", "last_complete_source_event")
    @classmethod
    def checkpoint_text_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("catalog checkpoint text must not be blank")
        return value

    @field_validator("updated_at")
    @classmethod
    def updated_at_is_utc(cls, value: datetime) -> datetime:
        if not _is_utc(value):
            raise ValueError("catalog checkpoint time must be UTC")
        return value

    @classmethod
    def from_checkpoint(cls, checkpoint: CollectionCheckpoint) -> Self:
        return cls(
            job_id=checkpoint.job_id,
            generation=checkpoint.generation,
            run_id=checkpoint.run_id,
            attempt=checkpoint.attempt,
            provider_cursor=checkpoint.provider_cursor,
            last_complete_source_event=checkpoint.last_complete_source_event,
            updated_at=checkpoint.updated_at,
            quality_report_id=checkpoint.quality_report_id,
        )


class CatalogEntry(_FrozenContract):
    """One committed dataset head and its exact qualification state."""

    provider_id: str = Field(pattern=r"^[a-z][a-z0-9_-]*(?::[a-z0-9_-]+)*$")
    provider_access: ProviderAccess
    dataset_id: str
    canonical_instrument: str = Field(min_length=1)
    layer: ArtifactLayer
    data_kind: DataKind
    interval: str | None = None
    calendar_version: str = Field(min_length=1)
    session_policy: SessionPolicy
    adjustment_policy: str | None = None
    manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    compatibility_revision: int = Field(ge=1)
    parent_manifest_ids: tuple[str, ...]
    object_digests: tuple[str, ...] = Field(min_length=1)
    row_count: int = Field(ge=1)
    event_start: datetime
    event_end: datetime
    knowledge_start: datetime
    knowledge_end: datetime
    source_rights_id: str = Field(min_length=1)
    entitlement: EntitlementState
    quality: CatalogQuality | None = None
    latest_checkpoint: CatalogCheckpoint | None = None

    @field_validator("dataset_id")
    @classmethod
    def dataset_is_canonical(cls, value: str) -> str:
        validate_dataset_name(value)
        return value

    @field_validator("parent_manifest_ids", "object_digests")
    @classmethod
    def digest_lists_are_canonical(
        cls,
        values: tuple[str, ...],
        info,
    ) -> tuple[str, ...]:
        if len(values) != len(set(values)) or any(
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            for value in values
        ):
            raise ValueError(f"{info.field_name} must contain unique SHA-256 digests")
        return values

    @field_validator("event_start", "event_end", "knowledge_start", "knowledge_end")
    @classmethod
    def coverage_time_is_utc(cls, value: datetime, info) -> datetime:
        if not _is_utc(value):
            raise ValueError(f"{info.field_name} must be UTC")
        return value

    @model_validator(mode="after")
    def qualification_is_checkpoint_bound(self) -> Self:
        report_id = (
            None if self.latest_checkpoint is None else self.latest_checkpoint.quality_report_id
        )
        if self.quality is None:
            if report_id is not None:
                raise ValueError("quality report requires an exact manifest evaluation")
        elif report_id != self.quality.report_id:
            raise ValueError("quality report and checkpoint binding disagree")
        return self

    @computed_field
    @property
    def is_current(self) -> bool:
        return self.manifest_id == self.current_manifest_id

    @computed_field
    @property
    def trusted_for_research(self) -> bool:
        return (
            self.provider_access is not ProviderAccess.FIXTURE
            and self.quality is not None
            and self.quality.qualification in {"clean", "qualified-with-resolution"}
            and self.latest_checkpoint is not None
            and self.latest_checkpoint.quality_report_id == self.quality.report_id
        )


class CatalogLineage(_FrozenContract):
    """One exact manifest and its recursively ordered immutable parents."""

    entry: CatalogEntry
    ancestors: tuple[CatalogEntry, ...]


class TrustedDataCatalog:
    """Project committed v2 graph state into a stable read-only catalog."""

    _RESEARCH_USES = frozenset({"ohlcv", "turnover", "liquidity", "cost", "capacity", "slippage"})

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.manifests = ManifestStore(self.root)
        self.quality = QualityEvidenceStore(self.root)

    def entries(self) -> tuple[CatalogEntry, ...]:
        checkpoints = self._checkpoints()
        by_manifest = self._checkpoint_index(checkpoints)
        entries: list[CatalogEntry] = []
        for dataset_id in self._dataset_ids():
            dataset = self.manifests.current(dataset_id)
            if dataset is None:
                continue
            entries.append(
                self._entry(
                    dataset.manifest,
                    by_manifest.get(dataset.manifest.manifest_id),
                )
            )
        return tuple(sorted(entries, key=lambda item: (item.dataset_id, item.current_manifest_id)))

    def lineage(self, manifest_id: str) -> CatalogLineage:
        if len(manifest_id) != 64 or any(
            character not in "0123456789abcdef" for character in manifest_id
        ):
            raise CatalogNotFoundError(f"manifest {manifest_id} is not cataloged")
        try:
            target = self.manifests.open(manifest_id).manifest
        except ManifestIntegrityError as error:
            if str(error) == f"manifest {manifest_id} is missing":
                raise CatalogNotFoundError(f"manifest {manifest_id} is not cataloged") from error
            raise
        committed_ids = {item.manifest_id for item in self.manifests.manifests(target.dataset_id)}
        if manifest_id not in committed_ids:
            raise CatalogNotFoundError(f"manifest {manifest_id} is not cataloged")
        ancestor_manifests: list[ArtifactManifest] = []
        visiting: set[str] = set()
        visited: set[str] = {manifest_id}

        def walk(current: ArtifactManifest) -> None:
            if current.manifest_id in visiting:
                raise CatalogIntegrityError("catalog lineage contains a cycle")
            visiting.add(current.manifest_id)
            for parent_id in current.parent_manifest_ids:
                if parent_id in visited:
                    continue
                try:
                    parent = self.manifests.open(parent_id).manifest
                except ValueError as error:
                    raise CatalogIntegrityError(
                        f"catalog parent manifest {parent_id} is unavailable"
                    ) from error
                walk(parent)
                visited.add(parent_id)
                ancestor_manifests.append(parent)
            visiting.remove(current.manifest_id)

        walk(target)
        checkpoint_store = self._checkpoint_store()
        by_manifest = (
            {}
            if checkpoint_store is None
            else checkpoint_store.checkpoints_for_manifests(
                (manifest_id, *(item.manifest_id for item in ancestor_manifests))
            )
        )
        return CatalogLineage(
            entry=self._entry(target, by_manifest.get(manifest_id)),
            ancestors=tuple(
                self._entry(item, by_manifest.get(item.manifest_id)) for item in ancestor_manifests
            ),
        )

    def require_research(self, manifest_id: str, *, use: str = "ohlcv") -> CatalogEntry:
        """Return exact passing current evidence or refuse downstream use."""
        if use not in self._RESEARCH_USES:
            raise CatalogQualificationError(f"unknown research use {use!r}")
        lineage = self.lineage(manifest_id)
        entry = lineage.entry
        if not entry.trusted_for_research:
            status = "missing" if entry.quality is None else entry.quality.status.value
            raise CatalogQualificationError(f"manifest {manifest_id} quality status is {status}")
        restricted = any(
            item.quality is not None and item.quality.qualification == "qualified-with-resolution"
            for item in (entry, *lineage.ancestors)
        )
        if restricted and use != "ohlcv":
            raise CatalogQualificationError(
                f"manifest {manifest_id} is not qualified for {use} use"
            )
        return entry

    def open_research_dataset(
        self,
        manifest_id: str,
        *,
        evaluation_id: str,
        dataset_id: str,
        compatibility_revision: int,
    ) -> ArtifactDataset:
        """Open one qualified artifact after matching every compatibility pin."""
        entry = self.require_research(manifest_id)
        if (
            entry.dataset_id != dataset_id
            or entry.compatibility_revision != compatibility_revision
            or entry.quality is None
            or entry.quality.evaluation_id != evaluation_id
        ):
            raise CatalogQualificationError(
                "trusted manifest, revision, dataset and quality pin disagree"
            )
        return self.manifests.open(manifest_id)

    def _entry(
        self,
        manifest: ArtifactManifest,
        checkpoint: CollectionCheckpoint | None,
    ) -> CatalogEntry:
        quality = None
        if checkpoint is not None and checkpoint.quality_report_id is not None:
            report = self.quality.verify_report_integrity(checkpoint.quality_report_id)
            admitted: set[str] = set()
            for binding in report.bindings:
                bound = self.manifests.open(binding.manifest_id).manifest
                admitted.update(
                    item.manifest_id for item in self.manifests.manifests(bound.dataset_id)
                )
            admitted_manifest_ids = frozenset(admitted)
            report = self.quality.verify_report(
                checkpoint.quality_report_id,
                admitted_manifest_ids=admitted_manifest_ids,
            )
            matches = [item for item in report.bindings if item.manifest_id == manifest.manifest_id]
            if len(matches) != 1:
                raise CatalogIntegrityError(
                    "quality report must contain exactly one catalog manifest binding"
                )
            evaluation = self.quality.load(matches[0].evaluation_id)
            resolution = None
            qualification = "clean" if evaluation.status is QualityStatus.PASS else "failed"
            resolution_store = OverlapResolutionStore(self.root)
            if evaluation.issue_codes == ("historical-live-overlap",):
                try:
                    resolution = resolution_store.for_evaluation(
                        evaluation.evaluation_id,
                        admitted_manifest_ids=admitted_manifest_ids,
                    )
                    qualification = "qualified-with-resolution"
                except OverlapResolutionIntegrityError:
                    resolution = None
            elif (
                isinstance(evaluation, QualityEvaluationV2)
                and evaluation.status is QualityStatus.PASS
                and evaluation.overlap_resolution_id is not None
            ):
                try:
                    inherited = resolution_store.load(evaluation.overlap_resolution_id)
                    resolution = resolution_store.for_evaluation(
                        inherited.failed_evaluation_id,
                        admitted_manifest_ids=admitted_manifest_ids,
                    )
                except OverlapResolutionIntegrityError as error:
                    raise CatalogIntegrityError(
                        "passing catalog quality has an invalid inherited resolution"
                    ) from error
                if resolution.resolution_id != evaluation.overlap_resolution_id:
                    raise CatalogIntegrityError(
                        "passing catalog quality resolution proof disagrees"
                    )
                qualification = "qualified-with-resolution"
            quality = CatalogQuality(
                report_id=report.report_id,
                evaluation_id=evaluation.evaluation_id,
                policy_id=evaluation.policy_id,
                status=evaluation.status,
                original_status=evaluation.status,
                issue_codes=evaluation.issue_codes,
                evaluated_at=evaluation.evaluated_at,
                expected_count=evaluation.expected_count,
                observed_count=evaluation.observed_count,
                duplicate_count=evaluation.duplicate_count,
                gap_count=evaluation.gap_count,
                hash_mismatch_count=evaluation.hash_mismatch_count,
                schema_mismatch_count=evaluation.schema_mismatch_count,
                order_violation_count=evaluation.order_violation_count,
                overlap_conflict_count=evaluation.overlap_conflict_count,
                synthetic_row_count=evaluation.synthetic_row_count,
                freshness_seconds=evaluation.freshness_seconds,
                latency_seconds=evaluation.latency_seconds,
                pagination_terminal=evaluation.pagination_terminal,
                source_rights_known=evaluation.source_rights_known,
                unavailable_reason=evaluation.unavailable_reason,
                resolution_id=None if resolution is None else resolution.resolution_id,
                qualification=qualification,
                use_policy=None if resolution is None else resolution.use_policy,
            )
        provider_id, provider_access = self._provider_identity(manifest)
        current = self.manifests.current(manifest.dataset_id)
        if current is None:
            raise CatalogIntegrityError(
                f"catalog dataset {manifest.dataset_id} has no committed current manifest"
            )
        return CatalogEntry(
            provider_id=provider_id,
            provider_access=provider_access,
            dataset_id=manifest.dataset_id,
            canonical_instrument=manifest.canonical_instrument.value,
            layer=manifest.layer,
            data_kind=manifest.data_kind,
            interval=manifest.interval,
            calendar_version=manifest.calendar_version,
            session_policy=manifest.session_policy,
            adjustment_policy=manifest.adjustment_policy,
            manifest_id=manifest.manifest_id,
            current_manifest_id=current.manifest.manifest_id,
            compatibility_revision=manifest.compatibility_revision,
            parent_manifest_ids=manifest.parent_manifest_ids,
            object_digests=tuple(reference.digest for reference in manifest.objects),
            row_count=len(manifest.row_identities),
            event_start=manifest.event_start,
            event_end=manifest.event_end,
            knowledge_start=manifest.knowledge_start,
            knowledge_end=manifest.knowledge_end,
            source_rights_id=manifest.source_rights_id,
            entitlement=manifest.entitlement,
            quality=quality,
            latest_checkpoint=(
                None if checkpoint is None else CatalogCheckpoint.from_checkpoint(checkpoint)
            ),
        )

    @staticmethod
    def _checkpoint_index(
        checkpoints: tuple[CollectionCheckpoint, ...],
    ) -> dict[str, CollectionCheckpoint]:
        result: dict[str, CollectionCheckpoint] = {}
        for checkpoint in checkpoints:
            for manifest_id in checkpoint.manifest_ids:
                previous = result.get(manifest_id)
                if previous is not None and previous.job_id != checkpoint.job_id:
                    raise CatalogIntegrityError("manifest is owned by multiple collection jobs")
                result[manifest_id] = checkpoint
        return result

    @staticmethod
    def _provider_identity(manifest: ArtifactManifest) -> tuple[str, ProviderAccess]:
        if manifest.source_rights_id.startswith("fixture"):
            return "fixture:trusted-data", ProviderAccess.FIXTURE
        if manifest.canonical_instrument.value.startswith("moomoo:"):
            return "moomoo-opend", ProviderAccess.AUTHENTICATED_READ_ONLY
        if manifest.canonical_instrument.value.startswith("hyperliquid:"):
            return "hyperliquid-public", ProviderAccess.PUBLIC_LIVE
        raise CatalogIntegrityError("catalog manifest has no bounded provider identity")

    def _dataset_ids(self) -> tuple[str, ...]:
        base = self.root / FABRIC_NAMESPACE / "datasets"
        if not base.exists():
            return ()
        if not base.is_dir() or is_reparse_point(base):
            raise CatalogIntegrityError("trusted-data dataset root is unsafe")
        result: list[str] = []
        for path in base.iterdir():
            if not path.is_dir() or is_reparse_point(path):
                raise CatalogIntegrityError("trusted-data dataset entry is unsafe")
            try:
                validate_dataset_name(path.name)
            except ValueError as error:
                raise CatalogIntegrityError("trusted-data dataset entry is invalid") from error
            result.append(path.name)
        return tuple(sorted(result))

    def _checkpoints(self) -> tuple[CollectionCheckpoint, ...]:
        store = self._checkpoint_store()
        return () if store is None else store.list_checkpoints()

    def _checkpoint_store(self) -> CheckpointStore | None:
        path = self.root / FABRIC_NAMESPACE / "control" / "collection-checkpoints.duckdb"
        if not path.exists():
            return None
        if not path.is_file() or is_reparse_point(path):
            raise CatalogIntegrityError("trusted-data checkpoint database is unsafe")
        return CheckpointStore(self.root)
