"""Typed receipts derived only from one collector's exact returned manifests."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.artifacts import (
    ArtifactLayer,
    ArtifactManifest,
    ManifestStore,
    canonical_json_bytes,
)
from quantmesh.data.capabilities import DataKind
from quantmesh.data.checkpoints import CheckpointStore
from quantmesh.data.collection import CollectionJob, CollectionRun
from quantmesh.data.envelopes import ProvenanceClass, RawEnvelope
from quantmesh.data.instruments import CanonicalInstrumentId


class CollectionReceiptIntegrityError(ValueError):
    """Returned manifests cannot prove one exact real collection cycle."""


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


_LAYERS = ("raw", "normalized", "adjusted", "feature")
_REQUIRED_TARGETS = {
    "hyperliquid-public": frozenset({"BTC", "ETH", "SOL"}),
    "moomoo-opend": frozenset({"AAPL", "NVDA"}),
}


class LayerManifestIds(_FrozenContract):
    """Deeply immutable four-layer identities with map-shaped JSON output."""

    raw: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized: str = Field(pattern=r"^[0-9a-f]{64}$")
    adjusted: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def identities_are_unique(self) -> Self:
        if len(set(self.ordered_values())) != len(_LAYERS):
            raise ValueError("target manifest IDs must be unique")
        return self

    def ordered_values(self) -> tuple[str, ...]:
        return (self.raw, self.normalized, self.adjusted, self.feature)


class TargetCollectionEvidence(_FrozenContract):
    """Exact four-layer bar lineage returned for one requested target."""

    target: str = Field(min_length=1)
    canonical_instrument: str = Field(min_length=1)
    interval: str = Field(min_length=1)
    manifest_ids: LayerManifestIds

    @field_validator("target", "canonical_instrument", "interval")
    @classmethod
    def text_is_not_blank(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        return value

class CollectionCycleReceipt(_FrozenContract):
    """One checkpoint-bound, exact collector return for a requested cycle."""

    contract: str = Field(
        default="collection-cycle-receipt-v1",
        pattern=r"^collection-cycle-receipt-v1$",
    )
    provider: str = Field(pattern=r"^(hyperliquid-public|moomoo-opend)$")
    code_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    collection_cycle: str = Field(min_length=1)
    job_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt: int = Field(ge=1)
    quality_report_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    targets: tuple[TargetCollectionEvidence, ...] = Field(min_length=1)

    @field_validator("collection_cycle")
    @classmethod
    def cycle_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("collection cycle must not be blank")
        return value

    @model_validator(mode="after")
    def targets_are_canonical(self) -> Self:
        labels = [item.target for item in self.targets]
        if labels != sorted(labels) or len(labels) != len(set(labels)):
            raise ValueError("collection receipt targets must be sorted and unique")
        validate_receipt_targets(self.provider, tuple(labels))
        manifest_ids = [
            manifest_id
            for item in self.targets
            for manifest_id in item.manifest_ids.ordered_values()
        ]
        if len(manifest_ids) != len(set(manifest_ids)):
            raise ValueError("collection receipt manifests must be unique across targets")
        return self

    @property
    def receipt_id(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


def derive_collection_receipt(
    *,
    root: Path,
    provider: str,
    code_commit: str,
    collection_cycle: str,
    manifest_ids: tuple[str, ...],
    targets: tuple[str, ...],
    interval: str,
) -> CollectionCycleReceipt:
    """Derive a receipt without consulting mutable catalog-current pointers."""
    validate_receipt_targets(provider, targets)
    if not manifest_ids:
        raise CollectionReceiptIntegrityError("current collection returned an empty manifest set")
    if len(manifest_ids) != len(set(manifest_ids)):
        raise CollectionReceiptIntegrityError("current collection returned duplicate manifests")
    expected_targets = tuple(sorted(targets))

    store = ManifestStore(Path(root))
    try:
        manifests = tuple(store.open(manifest_id).manifest for manifest_id in manifest_ids)
    except (OSError, ValueError) as error:
        raise CollectionReceiptIntegrityError(
            "current collection returned a missing or invalid manifest"
        ) from error
    if any(manifest.code_commit != code_commit for manifest in manifests):
        raise CollectionReceiptIntegrityError("returned manifest uses a stale producing commit")

    bar_manifests = tuple(
        manifest
        for manifest in manifests
        if manifest.data_kind is DataKind.BARS and manifest.interval == interval
    )
    if any(
        manifest.data_kind is DataKind.BARS and manifest.interval != interval
        for manifest in manifests
    ):
        raise CollectionReceiptIntegrityError(
            "returned bar manifest has the wrong interval"
        )
    by_target: dict[str, list[ArtifactManifest]] = {target: [] for target in expected_targets}
    for manifest in bar_manifests:
        target = _target_label(manifest, provider)
        if target not in by_target:
            raise CollectionReceiptIntegrityError("returned bar manifest has the wrong target")
        by_target[target].append(manifest)

    target_evidence = tuple(
        _target_evidence(
            store,
            provider=provider,
            target=target,
            interval=interval,
            manifests=tuple(by_target[target]),
            returned_manifests=manifests,
        )
        for target in expected_targets
    )

    try:
        owners = CheckpointStore(Path(root)).checkpoints_for_manifests(manifest_ids)
    except (OSError, RuntimeError, ValueError) as error:
        raise CollectionReceiptIntegrityError(
            "returned manifest checkpoint proof is invalid"
        ) from error
    if set(owners) != set(manifest_ids):
        raise CollectionReceiptIntegrityError("returned manifest lacks one checkpoint owner")
    checkpoints = tuple(owners.values())
    checkpoint = checkpoints[0]
    if any(
        (item.job_id, item.run_id, item.attempt, item.quality_report_id)
        != (checkpoint.job_id, checkpoint.run_id, checkpoint.attempt, checkpoint.quality_report_id)
        for item in checkpoints[1:]
    ):
        raise CollectionReceiptIntegrityError("current collection mixes checkpoint identities")
    if set(checkpoint.manifest_ids) != set(manifest_ids):
        raise CollectionReceiptIntegrityError(
            "checkpoint contains manifests not returned by the current collection"
        )
    if checkpoint.quality_report_id is None:
        raise CollectionReceiptIntegrityError("collection checkpoint has no quality report")
    if any(manifest.collection_run_id != checkpoint.run_id for manifest in manifests):
        raise CollectionReceiptIntegrityError("returned manifest uses a stale collection run")
    expected_job = _reconstruct_job(
        store,
        provider=provider,
        code_commit=code_commit,
        collection_cycle=collection_cycle,
        interval=interval,
        manifests=manifests,
        target_evidence=target_evidence,
        request_targets=targets,
    )
    if expected_job.job_id != checkpoint.job_id:
        raise CollectionReceiptIntegrityError(
            "checkpoint disagrees with the producing commit, collection cycle, or request"
        )
    if (
        CollectionRun.for_job(expected_job, attempt=checkpoint.attempt).run_id
        != checkpoint.run_id
    ):
        raise CollectionReceiptIntegrityError(
            "checkpoint run ID disagrees with its exact collection job"
        )

    return CollectionCycleReceipt(
        provider=provider,
        code_commit=code_commit,
        collection_cycle=collection_cycle,
        job_id=checkpoint.job_id,
        run_id=checkpoint.run_id,
        attempt=checkpoint.attempt,
        quality_report_id=checkpoint.quality_report_id,
        targets=target_evidence,
    )


def _target_evidence(
    store: ManifestStore,
    *,
    provider: str,
    target: str,
    interval: str,
    manifests: tuple[ArtifactManifest, ...],
    returned_manifests: tuple[ArtifactManifest, ...],
) -> TargetCollectionEvidence:
    layers: dict[str, ArtifactManifest] = {}
    for manifest in manifests:
        key = manifest.layer.value
        if key not in _LAYERS or key in layers:
            raise CollectionReceiptIntegrityError("target has a duplicate or unsupported layer")
        layers[key] = manifest
    if tuple(layer for layer in _LAYERS if layer in layers) != _LAYERS:
        raise CollectionReceiptIntegrityError("target lacks one exact four-layer bar lineage")
    canonical = {manifest.canonical_instrument.value for manifest in layers.values()}
    if len(canonical) != 1:
        raise CollectionReceiptIntegrityError("target layers disagree on canonical instrument")
    adjusted_parents = (layers["normalized"].manifest_id,)
    if provider == "moomoo-opend":
        action_parents = tuple(
            manifest.manifest_id
            for manifest in returned_manifests
            if manifest.canonical_instrument == layers["raw"].canonical_instrument
            and manifest.data_kind is DataKind.SPLITS
            and manifest.layer is ArtifactLayer.NORMALIZED
        )
        if len(action_parents) != 1:
            raise CollectionReceiptIntegrityError(
                "Moomoo target lacks one exact normalized action parent"
            )
        adjusted_parents = (*adjusted_parents, action_parents[0])
    if (
        layers["normalized"].parent_manifest_ids != (layers["raw"].manifest_id,)
        or layers["adjusted"].parent_manifest_ids != adjusted_parents
        or layers["feature"].parent_manifest_ids
        != (layers["adjusted"].manifest_id,)
    ):
        raise CollectionReceiptIntegrityError(
            "target layers do not form one exact returned lineage"
        )
    raw = layers[ArtifactLayer.RAW.value]
    envelope_refs = tuple(
        reference
        for reference in raw.objects
        if reference.media_type == "application/vnd.quantmesh.raw-envelope+json"
    )
    if len(envelope_refs) != 1:
        raise CollectionReceiptIntegrityError("raw target lacks one exact provenance envelope")
    try:
        envelope = RawEnvelope.model_validate_json(store.objects.get_bytes(envelope_refs[0]))
    except (OSError, ValueError) as error:
        raise CollectionReceiptIntegrityError("raw target provenance is invalid") from error
    if envelope.provenance is not ProvenanceClass.REAL or envelope.provider_id != provider:
        raise CollectionReceiptIntegrityError(
            "fixture or wrong-provider provenance is not receiptable"
        )
    return TargetCollectionEvidence(
        target=target,
        canonical_instrument=next(iter(canonical)),
        interval=interval,
        manifest_ids=LayerManifestIds(
            raw=layers["raw"].manifest_id,
            normalized=layers["normalized"].manifest_id,
            adjusted=layers["adjusted"].manifest_id,
            feature=layers["feature"].manifest_id,
        ),
    )


def _target_label(manifest: ArtifactManifest, provider: str) -> str:
    parts = manifest.canonical_instrument.value.split(":")
    if provider == "hyperliquid-public" and len(parts) == 3 and parts[:2] == [
        "hyperliquid",
        "perp",
    ]:
        return parts[2]
    if provider == "moomoo-opend" and len(parts) == 4 and parts[:2] == ["moomoo", "US"]:
        return parts[2]
    raise CollectionReceiptIntegrityError(
        "returned manifest canonical target disagrees with provider"
    )


def _reconstruct_job(
    store: ManifestStore,
    *,
    provider: str,
    code_commit: str,
    collection_cycle: str,
    interval: str,
    manifests: tuple[ArtifactManifest, ...],
    target_evidence: tuple[TargetCollectionEvidence, ...],
    request_targets: tuple[str, ...],
) -> CollectionJob:
    """Rebuild the collection identity so cycle text cannot be relabelled."""
    expected_kinds = (
        (DataKind.BARS,)
        if provider == "hyperliquid-public"
        else (
            DataKind.BARS,
            DataKind.ADJUSTMENT_FACTORS,
            DataKind.SPLITS,
            DataKind.DIVIDENDS,
        )
    )
    raw_manifests = tuple(
        manifest for manifest in manifests if manifest.layer is ArtifactLayer.RAW
    )
    envelopes: dict[tuple[str, DataKind], RawEnvelope] = {}
    for manifest in raw_manifests:
        target = _target_label(manifest, provider)
        envelope = _raw_envelope(store, manifest)
        key = (target, manifest.data_kind)
        if (
            key in envelopes
            or envelope.provider_id != provider
            or envelope.canonical_instrument != manifest.canonical_instrument
            or envelope.data_kind is not manifest.data_kind
        ):
            raise CollectionReceiptIntegrityError(
                "raw collection envelopes disagree with the returned graph"
            )
        envelopes[key] = envelope

    target_labels = request_targets
    evidence_by_target = {item.target: item for item in target_evidence}
    expected_keys = {
        (target, data_kind) for target in target_labels for data_kind in expected_kinds
    }
    if set(envelopes) != expected_keys:
        raise CollectionReceiptIntegrityError(
            "returned graph lacks the exact provider source envelopes"
        )

    endpoint_by_kind: dict[DataKind, str] = {}
    for data_kind in expected_kinds:
        endpoints = {envelopes[(target, data_kind)].endpoint for target in target_labels}
        if len(endpoints) != 1:
            raise CollectionReceiptIntegrityError(
                "provider targets disagree on collection endpoints"
            )
        endpoint_by_kind[data_kind] = endpoints.pop()

    windows = {
        _envelope_window(envelope, provider=provider) for envelope in envelopes.values()
    }
    if len(windows) != 1:
        raise CollectionReceiptIntegrityError(
            "provider envelopes disagree on the collection window"
        )
    window_start, window_end = windows.pop()
    catalog_ids = {manifest.instrument_catalog_id for manifest in manifests}
    if len(catalog_ids) != 1:
        raise CollectionReceiptIntegrityError(
            "returned manifests disagree on the instrument catalog"
        )

    return CollectionJob(
        provider_id=provider,
        endpoints=tuple(endpoint_by_kind[data_kind] for data_kind in expected_kinds),
        source_request_ids=tuple(
            envelopes[(target, data_kind)].request_id
            for target in target_labels
            for data_kind in expected_kinds
        ),
        canonical_instruments=tuple(
            CanonicalInstrumentId(
                value=evidence_by_target[target].canonical_instrument
            )
            for target in target_labels
        ),
        data_kinds=expected_kinds,
        intervals=(interval,),
        calendar_version=manifests[0].calendar_version,
        session_policy=manifests[0].session_policy,
        window_start=window_start,
        window_end=window_end,
        adjustment_policy=(
            "identity-no-corporate-actions-v1"
            if provider == "hyperliquid-public"
            else "split-adjusted-v1"
        ),
        schema_versions=tuple(
            envelopes[(target_labels[0], data_kind)].schema_version
            for data_kind in expected_kinds
        ),
        mapping_version=catalog_ids.pop(),
        code_commit=code_commit,
        collection_cycle=collection_cycle,
    )


def _raw_envelope(store: ManifestStore, manifest: ArtifactManifest) -> RawEnvelope:
    references = tuple(
        reference
        for reference in manifest.objects
        if reference.media_type == "application/vnd.quantmesh.raw-envelope+json"
    )
    if len(references) != 1:
        raise CollectionReceiptIntegrityError(
            "raw manifest lacks one exact provenance envelope"
        )
    try:
        return RawEnvelope.model_validate_json(store.objects.get_bytes(references[0]))
    except (OSError, ValueError) as error:
        raise CollectionReceiptIntegrityError("raw target provenance is invalid") from error


def _envelope_window(
    envelope: RawEnvelope, *, provider: str
) -> tuple[datetime, datetime]:
    if provider == "hyperliquid-public":
        return envelope.request_window_start, envelope.request_window_end
    if envelope.collection_window_start is None or envelope.collection_window_end is None:
        raise CollectionReceiptIntegrityError(
            "Moomoo envelope lacks its exact collection window"
        )
    return envelope.collection_window_start, envelope.collection_window_end


def validate_receipt_targets(provider: str, targets: tuple[str, ...]) -> None:
    """Reject partial, duplicate, or out-of-scope formal collection sets."""
    required = _REQUIRED_TARGETS.get(provider)
    if required is None:
        raise CollectionReceiptIntegrityError(
            "collection provider is not receipt-capable"
        )
    if len(targets) != len(set(targets)):
        raise CollectionReceiptIntegrityError("receipt targets must be unique")
    if frozenset(targets) != required:
        raise CollectionReceiptIntegrityError(
            "receipt requires the exact provider target set"
        )
