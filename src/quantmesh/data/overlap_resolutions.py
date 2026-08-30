"""Immutable operator attestations for exact historical overlap conflicts."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.artifacts import (
    ArtifactLayer,
    ManifestIntegrityError,
    ManifestStore,
    canonical_json_bytes,
)
from quantmesh.data.capabilities import DataKind
from quantmesh.data.objects import (
    FABRIC_NAMESPACE,
    ObjectIntegrityError,
    ObjectRef,
    ObjectStore,
    is_reparse_point,
)
from quantmesh.data.quality import (
    QualityEvidenceStore,
    QualityFailure,
    QualityIntegrityError,
    QualityStatus,
)


class OverlapResolutionIntegrityError(ValueError):
    """A resolution object, binding, or referenced evidence is invalid."""


class ResolutionAttestation(StrEnum):
    OPERATOR_ACKNOWLEDGED = "operator-acknowledged"
    PROVIDER_VERIFIED = "provider-verified"


class ResolutionUsePolicy(StrEnum):
    OHLCV_DERIVATIVES_ONLY = "ohlcv-derivatives-only"


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


class OverlapFieldDiff(_FrozenContract):
    """One exact changed JSON field in a shared source row."""

    field: str = Field(min_length=1)
    prior_present: bool = True
    current_present: bool = True
    prior: Any
    current: Any

    @field_validator("field")
    @classmethod
    def field_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field must not be blank")
        return value

    @model_validator(mode="after")
    def values_are_changed_and_canonical(self) -> Self:
        try:
            prior = canonical_json_bytes(self.prior)
            current = canonical_json_bytes(self.current)
        except (TypeError, ValueError) as error:
            raise ValueError("field diff values must be canonical JSON") from error
        if self.prior_present == self.current_present and prior == current:
            raise ValueError("field diff must describe a changed value")
        return self


class OverlapConflict(_FrozenContract):
    """Exact immutable detail for one changed shared row identity."""

    identity: str = Field(min_length=1)
    prior_row_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_row_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    field_diffs: tuple[OverlapFieldDiff, ...] = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    legacy_evaluation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = _OverlapConflictBody.model_validate(values)
        fingerprint = hashlib.sha256(
            canonical_json_bytes(
                {
                    "current_row_fingerprint": body.current_row_fingerprint,
                    "field_diffs": [item.model_dump(mode="json") for item in body.field_diffs],
                    "identity": body.identity,
                    "prior_row_fingerprint": body.prior_row_fingerprint,
                }
            )
        ).hexdigest()
        legacy_evaluation_fingerprint = hashlib.sha256(
            canonical_json_bytes(
                {
                    "current": body.current_row_fingerprint,
                    "identity": body.identity,
                    "previous": body.prior_row_fingerprint,
                }
            )
        ).hexdigest()
        return cls(
            **body.model_dump(),
            fingerprint=fingerprint,
            legacy_evaluation_fingerprint=legacy_evaluation_fingerprint,
        )

    @field_validator("identity")
    @classmethod
    def identity_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("identity must not be blank")
        return value

    @model_validator(mode="after")
    def body_is_canonical_and_fingerprint_matches(self) -> Self:
        if self.prior_row_fingerprint == self.current_row_fingerprint:
            raise ValueError("overlap conflict row fingerprints must differ")
        expected_diffs = tuple(sorted(self.field_diffs, key=lambda item: item.field))
        if self.field_diffs != expected_diffs or len(
            {item.field for item in self.field_diffs}
        ) != len(self.field_diffs):
            raise ValueError("overlap field differences must be sorted and unique")
        expected = hashlib.sha256(
            canonical_json_bytes(
                {
                    "current_row_fingerprint": self.current_row_fingerprint,
                    "field_diffs": [item.model_dump(mode="json") for item in self.field_diffs],
                    "identity": self.identity,
                    "prior_row_fingerprint": self.prior_row_fingerprint,
                }
            )
        ).hexdigest()
        expected_legacy = hashlib.sha256(
            canonical_json_bytes(
                {
                    "current": self.current_row_fingerprint,
                    "identity": self.identity,
                    "previous": self.prior_row_fingerprint,
                }
            )
        ).hexdigest()
        if self.fingerprint != expected:
            raise ValueError("overlap conflict fingerprint disagrees with its exact differences")
        if self.legacy_evaluation_fingerprint != expected_legacy:
            raise ValueError("legacy overlap fingerprint disagrees with its rows")
        return self


class _OverlapConflictBody(OverlapConflict):
    fingerprint: str = Field(default="0" * 64, exclude=True)
    legacy_evaluation_fingerprint: str = Field(default="0" * 64, exclude=True)

    @model_validator(mode="after")
    def body_is_canonical_and_fingerprint_matches(self) -> Self:
        if self.prior_row_fingerprint == self.current_row_fingerprint:
            raise ValueError("overlap conflict row fingerprints must differ")
        expected_diffs = tuple(sorted(self.field_diffs, key=lambda item: item.field))
        if self.field_diffs != expected_diffs or len(
            {item.field for item in self.field_diffs}
        ) != len(self.field_diffs):
            raise ValueError("overlap field differences must be sorted and unique")
        return self


class OverlapResolution(_FrozenContract):
    """One content-addressed, bounded resolution of one failed evaluation."""

    contract: str = Field(default="overlap-resolution-v1", pattern=r"^overlap-resolution-v1$")
    resolution_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    failed_evaluation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    failed_report_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    policy_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_id: str = Field(min_length=1)
    baseline_manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    conflicts: tuple[OverlapConflict, ...] = Field(min_length=1)
    predecessor_known_at: datetime
    candidate_known_at: datetime
    reviewed_at: datetime
    operator: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    attestation: ResolutionAttestation
    use_policy: ResolutionUsePolicy

    @classmethod
    def build(cls, **values: Any) -> Self:
        body = _OverlapResolutionBody.model_validate(values)
        payload = canonical_json_bytes(body.model_dump(mode="json"))
        return cls(**body.model_dump(), resolution_id=hashlib.sha256(payload).hexdigest())

    @field_validator("dataset_id", "operator", "reason")
    @classmethod
    def text_is_not_blank(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return value

    @field_validator("predecessor_known_at", "candidate_known_at", "reviewed_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime, info) -> datetime:
        if not _is_utc(value):
            raise ValueError(f"{info.field_name} must be UTC")
        return value

    @model_validator(mode="after")
    def identity_order_and_time_are_valid(self) -> Self:
        _validate_resolution_body(self)
        actual = hashlib.sha256(
            canonical_json_bytes(self.model_dump(mode="json", exclude={"resolution_id"}))
        ).hexdigest()
        if actual != self.resolution_id:
            raise ValueError("resolution ID disagrees with its canonical body")
        return self

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json", exclude={"resolution_id"}))


class _OverlapResolutionBody(OverlapResolution):
    resolution_id: str = Field(default="0" * 64, exclude=True)

    @model_validator(mode="after")
    def identity_order_and_time_are_valid(self) -> Self:
        _validate_resolution_body(self)
        return self


def _validate_resolution_body(resolution: OverlapResolution) -> None:
    if resolution.baseline_manifest_id == resolution.candidate_manifest_id:
        raise ValueError("baseline and candidate manifests must differ")
    expected_conflicts = tuple(sorted(resolution.conflicts, key=lambda item: item.fingerprint))
    if resolution.conflicts != expected_conflicts or len(
        {item.fingerprint for item in resolution.conflicts}
    ) != len(resolution.conflicts):
        raise ValueError("conflicts must be sorted and unique")
    if resolution.predecessor_known_at >= resolution.candidate_known_at:
        raise ValueError("candidate knowledge time must follow predecessor knowledge time")
    if resolution.reviewed_at < resolution.candidate_known_at:
        raise ValueError("review time must not precede candidate knowledge time")


class _OverlapResolutionBinding(_FrozenContract):
    contract: str = Field(
        default="overlap-resolution-binding-v1",
        pattern=r"^overlap-resolution-binding-v1$",
    )
    failed_evaluation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    resolution_id: str = Field(pattern=r"^[0-9a-f]{64}$")


class OverlapResolutionStore:
    """Persist and verify exact resolutions with create-once evaluation bindings."""

    RESOLUTION_MEDIA_TYPE = "application/vnd.quantmesh.overlap-resolution+json"
    _OHLCV_SOURCE_FIELDS = frozenset(
        {
            "T",
            "c",
            "close",
            "code",
            "datetime",
            "h",
            "high",
            "i",
            "interval",
            "l",
            "low",
            "o",
            "open",
            "s",
            "symbol",
            "t",
            "time_key",
            "timestamp",
            "v",
            "volume",
        }
    )

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.objects = ObjectStore(self.root)
        self.manifests = ManifestStore(self.root)
        self.evidence = QualityEvidenceStore(self.root)

    def record(
        self,
        resolution: OverlapResolution,
        *,
        admitted_manifest_ids: frozenset[str] = frozenset(),
    ) -> OverlapResolution:
        self.verify(resolution, admitted_manifest_ids=admitted_manifest_ids)
        binding = _OverlapResolutionBinding(
            failed_evaluation_id=resolution.failed_evaluation_id,
            resolution_id=resolution.resolution_id,
        )
        self._record_binding(binding)
        reference = self.objects.put_bytes(
            self.RESOLUTION_MEDIA_TYPE,
            resolution.canonical_bytes(),
        )
        if reference.digest != resolution.resolution_id:
            raise OverlapResolutionIntegrityError("resolution identity changed while recording")
        self._record_winner(binding)
        return self.for_evaluation(
            resolution.failed_evaluation_id,
            admitted_manifest_ids=admitted_manifest_ids,
        )

    def load(self, resolution_id: str) -> OverlapResolution:
        path = self.path_for(resolution_id)
        try:
            size = path.lstat().st_size
            payload = self.objects.get_bytes(
                ObjectRef(
                    digest=resolution_id,
                    media_type=self.RESOLUTION_MEDIA_TYPE,
                    byte_length=size,
                )
            )
            body = _OverlapResolutionBody.model_validate_json(payload)
            resolution = OverlapResolution.build(**body.model_dump(exclude={"resolution_id"}))
        except (
            ObjectIntegrityError,
            OSError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ) as error:
            raise OverlapResolutionIntegrityError(
                f"overlap resolution object is missing or invalid for {resolution_id}"
            ) from error
        if resolution.resolution_id != resolution_id:
            raise OverlapResolutionIntegrityError("resolution identity disagrees with its path")
        return resolution

    def for_evaluation(
        self,
        failed_evaluation_id: str,
        *,
        admitted_manifest_ids: frozenset[str] = frozenset(),
    ) -> OverlapResolution:
        binding = self._load_binding(failed_evaluation_id)
        winners = self._winner_bindings_for_evaluation(failed_evaluation_id)
        if len(winners) > 1:
            raise OverlapResolutionIntegrityError("failed evaluation has multiple winner anchors")
        if not winners or winners[0] != binding:
            raise OverlapResolutionIntegrityError(
                "overlap resolution binding lacks its exact winner anchor"
            )
        resolution = self.load(binding.resolution_id)
        if resolution.failed_evaluation_id != failed_evaluation_id:
            raise OverlapResolutionIntegrityError(
                "resolution binding disagrees with the failed evaluation"
            )
        return self.verify(resolution, admitted_manifest_ids=admitted_manifest_ids)

    def verify(
        self,
        resolution: OverlapResolution,
        *,
        admitted_manifest_ids: frozenset[str] = frozenset(),
    ) -> OverlapResolution:
        try:
            baseline = self.manifests.open(resolution.baseline_manifest_id).manifest
        except (ManifestIntegrityError, ValueError) as error:
            raise OverlapResolutionIntegrityError(
                "resolution baseline manifest is missing or invalid"
            ) from error
        try:
            candidate = self.manifests.open(resolution.candidate_manifest_id).manifest
        except (ManifestIntegrityError, ValueError) as error:
            raise OverlapResolutionIntegrityError(
                "resolution candidate manifest is missing or invalid"
            ) from error
        try:
            failed = self.evidence.load(resolution.failed_evaluation_id)
        except (QualityIntegrityError, ValueError) as error:
            raise OverlapResolutionIntegrityError(
                "resolution failed evaluation is missing or invalid"
            ) from error
        try:
            report = self.evidence.verify_report_integrity(resolution.failed_report_id)
        except (QualityIntegrityError, ValueError) as error:
            raise OverlapResolutionIntegrityError(
                "resolution failed report is missing or invalid"
            ) from error
        try:
            policy = self.evidence.load_policy(resolution.policy_id)
        except (QualityIntegrityError, ValueError) as error:
            raise OverlapResolutionIntegrityError(
                "resolution policy is missing or invalid"
            ) from error
        if (
            baseline.dataset_id != candidate.dataset_id
            or candidate.dataset_id != resolution.dataset_id
        ):
            raise OverlapResolutionIntegrityError("resolution dataset does not match its manifests")
        history = self.manifests.manifests(candidate.dataset_id)
        candidate_positions = [
            index
            for index, manifest in enumerate(history)
            if manifest.manifest_id == candidate.manifest_id
        ]
        if len(candidate_positions) != 1 or candidate_positions[0] == 0:
            raise OverlapResolutionIntegrityError(
                "resolution candidate is not a committed successor"
            )
        predecessor = history[candidate_positions[0] - 1]
        if predecessor.manifest_id != baseline.manifest_id:
            raise OverlapResolutionIntegrityError(
                "resolution baseline is not the candidate's committed predecessor"
            )
        if baseline.knowledge_end != resolution.predecessor_known_at:
            raise OverlapResolutionIntegrityError(
                "resolution baseline manifest knowledge time changed"
            )
        if candidate.knowledge_end != resolution.candidate_known_at:
            raise OverlapResolutionIntegrityError(
                "resolution candidate manifest knowledge time changed"
            )
        if failed.policy_id != resolution.policy_id or policy.policy_id != resolution.policy_id:
            raise OverlapResolutionIntegrityError(
                "resolution policy does not match failed evidence"
            )
        if failed.manifest_id != resolution.candidate_manifest_id:
            raise OverlapResolutionIntegrityError(
                "resolution candidate manifest does not match failure"
            )
        if resolution.reviewed_at <= failed.evaluated_at:
            raise OverlapResolutionIntegrityError(
                "resolution review time must strictly follow the failed evaluation"
            )
        if failed.status is not QualityStatus.FAIL or failed.issue_codes != (
            "historical-live-overlap",
        ):
            raise OverlapResolutionIntegrityError(
                "resolution requires an overlap-only failed evaluation"
            )
        if not any(
            binding.evaluation_id == failed.evaluation_id
            and binding.manifest_id == candidate.manifest_id
            for binding in report.bindings
        ):
            raise OverlapResolutionIntegrityError(
                "failed report binding does not contain the candidate evaluation"
            )
        try:
            from quantmesh.data.checkpoints import CheckpointIntegrityError, CheckpointStore

            checkpoint_path = (
                self.root / FABRIC_NAMESPACE / "control" / "collection-checkpoints.duckdb"
            )
            if not checkpoint_path.is_file():
                raise CheckpointIntegrityError("checkpoint database is missing")
            checkpoints = CheckpointStore(self.root).checkpoints_for_manifests(
                (candidate.manifest_id,)
            )
        except (CheckpointIntegrityError, OSError, ValueError) as error:
            raise OverlapResolutionIntegrityError(
                "resolution candidate checkpoint is missing or invalid"
            ) from error
        checkpoint = checkpoints.get(candidate.manifest_id)
        if (
            checkpoint is None
            or checkpoint.quality_report_id != report.report_id
            or checkpoint.job_id != report.job_id
            or checkpoint.run_id != report.run_id
        ):
            raise OverlapResolutionIntegrityError(
                "resolution report is not bound by the candidate checkpoint"
            )
        from quantmesh.data.quality import QualityEvaluator

        try:
            conflicts = QualityEvaluator(self.manifests).overlap_conflicts(
                candidate.manifest_id,
                baseline.manifest_id,
                admitted_manifest_ids=admitted_manifest_ids,
            )
        except (ManifestIntegrityError, QualityFailure, ValueError) as error:
            raise OverlapResolutionIntegrityError(
                "resolution conflict set cannot be re-derived"
            ) from error
        if conflicts != resolution.conflicts:
            raise OverlapResolutionIntegrityError(
                "resolution conflict set disagrees with immutable manifests"
            )
        if (
            tuple(sorted(item.legacy_evaluation_fingerprint for item in conflicts))
            != failed.overlap_conflict_fingerprints
        ):
            raise OverlapResolutionIntegrityError(
                "resolution conflict fingerprints disagree with failed evidence"
            )
        if resolution.use_policy is ResolutionUsePolicy.OHLCV_DERIVATIVES_ONLY:
            if (
                candidate.layer is not ArtifactLayer.RAW
                or candidate.data_kind is not DataKind.BARS
                or baseline.data_kind is not DataKind.BARS
                or any(
                    diff.field in self._OHLCV_SOURCE_FIELDS
                    for conflict in conflicts
                    for diff in conflict.field_diffs
                )
            ):
                raise OverlapResolutionIntegrityError(
                    "ohlcv-derivatives-only requires unchanged raw OHLCV identities"
                )
        return resolution

    def path_for(self, resolution_id: str) -> Path:
        if len(resolution_id) != 64 or any(
            character not in "0123456789abcdef" for character in resolution_id
        ):
            raise ValueError("resolution_id must be a lowercase SHA-256 digest")
        return (
            self.root / FABRIC_NAMESPACE / "objects" / "sha256" / resolution_id[:2] / resolution_id
        )

    def _binding_path(self, failed_evaluation_id: str) -> Path:
        if len(failed_evaluation_id) != 64 or any(
            character not in "0123456789abcdef" for character in failed_evaluation_id
        ):
            raise ValueError("failed_evaluation_id must be a lowercase SHA-256 digest")
        return (
            self.root
            / FABRIC_NAMESPACE
            / "quality"
            / "overlap-resolutions"
            / f"{failed_evaluation_id}.json"
        )

    def _winner_path(self, resolution_id: str) -> Path:
        if len(resolution_id) != 64 or any(
            character not in "0123456789abcdef" for character in resolution_id
        ):
            raise ValueError("resolution_id must be a lowercase SHA-256 digest")
        return (
            self.root
            / FABRIC_NAMESPACE
            / "quality"
            / "overlap-resolution-winners"
            / f"{resolution_id}.json"
        )

    def _record_binding(self, binding: _OverlapResolutionBinding) -> None:
        target = self._binding_path(binding.failed_evaluation_id)
        payload = canonical_json_bytes(binding.model_dump(mode="json"))
        self._record_create_once(
            target,
            payload,
            conflict="a different overlap resolution already binds this evaluation",
        )

    def _record_winner(self, binding: _OverlapResolutionBinding) -> None:
        target = self._winner_path(binding.resolution_id)
        payload = canonical_json_bytes(binding.model_dump(mode="json"))
        self._record_create_once(
            target,
            payload,
            conflict="overlap resolution winner anchor conflicts with its binding",
        )

    def _record_create_once(self, target: Path, payload: bytes, *, conflict: str) -> None:
        self._reject_binding_reparse_points(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._reject_binding_reparse_points(target)
        descriptor, temp_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{target.stem}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp_name, target)
            except FileExistsError:
                try:
                    existing = target.read_bytes()
                except OSError as error:
                    raise OverlapResolutionIntegrityError(
                        "existing overlap resolution binding cannot be read"
                    ) from error
                if existing != payload:
                    raise OverlapResolutionIntegrityError(conflict)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _load_binding(self, failed_evaluation_id: str) -> _OverlapResolutionBinding:
        path = self._binding_path(failed_evaluation_id)
        self._reject_binding_reparse_points(path)
        try:
            payload = path.read_bytes()
            binding = _OverlapResolutionBinding.model_validate_json(payload)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise OverlapResolutionIntegrityError(
                "overlap resolution binding is missing or invalid"
            ) from error
        if binding.failed_evaluation_id != failed_evaluation_id:
            raise OverlapResolutionIntegrityError(
                "overlap resolution binding disagrees with its path"
            )
        if payload != canonical_json_bytes(binding.model_dump(mode="json")):
            raise OverlapResolutionIntegrityError("overlap resolution binding is not canonical")
        return binding

    def _load_winner(self, resolution_id: str) -> _OverlapResolutionBinding:
        path = self._winner_path(resolution_id)
        self._reject_binding_reparse_points(path)
        try:
            payload = path.read_bytes()
            winner = _OverlapResolutionBinding.model_validate_json(payload)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            raise OverlapResolutionIntegrityError(
                "overlap resolution winner anchor is missing or invalid"
            ) from error
        if winner.resolution_id != resolution_id:
            raise OverlapResolutionIntegrityError(
                "overlap resolution winner anchor disagrees with its path"
            )
        if payload != canonical_json_bytes(winner.model_dump(mode="json")):
            raise OverlapResolutionIntegrityError(
                "overlap resolution winner anchor is not canonical"
            )
        return winner

    def _winner_bindings_for_evaluation(
        self,
        failed_evaluation_id: str,
    ) -> tuple[_OverlapResolutionBinding, ...]:
        directory = self._winner_path("0" * 64).parent
        self._reject_binding_reparse_points(directory)
        try:
            paths = tuple(sorted(directory.iterdir(), key=lambda item: item.name))
        except OSError as error:
            raise OverlapResolutionIntegrityError(
                "overlap resolution winner anchors are missing or unreadable"
            ) from error
        winners = []
        for path in paths:
            if (
                not path.is_file()
                or path.suffix != ".json"
                or len(path.stem) != 64
                or any(character not in "0123456789abcdef" for character in path.stem)
            ):
                raise OverlapResolutionIntegrityError(
                    "overlap resolution winner directory contains an invalid entry"
                )
            winner = self._load_winner(path.stem)
            if winner.failed_evaluation_id == failed_evaluation_id:
                winners.append(winner)
        return tuple(winners)

    def _reject_binding_reparse_points(self, path: Path) -> None:
        try:
            relative = path.relative_to(self.root)
        except ValueError as error:
            raise OverlapResolutionIntegrityError(
                "resolution binding escapes store root"
            ) from error
        candidate = self.root
        if is_reparse_point(candidate):
            raise OverlapResolutionIntegrityError(
                f"resolution binding path contains a reparse point: {candidate}"
            )
        for part in relative.parts:
            candidate /= part
            if is_reparse_point(candidate):
                raise OverlapResolutionIntegrityError(
                    f"resolution binding path contains a reparse point: {candidate}"
                )
