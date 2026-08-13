"""Bounded raw-to-feature publication tracer for the trusted-data fabric."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from quantmesh.data.adjustments import AdjustmentPolicy
from quantmesh.data.artifacts import (
    ArtifactLayer,
    ArtifactManifest,
    ManifestIntegrityError,
    ManifestStore,
    canonical_json_bytes,
)
from quantmesh.data.calendars import XNYS_REGULAR_VERSION, CalendarService, SessionPolicy
from quantmesh.data.capabilities import DataKind
from quantmesh.data.envelopes import ProvenanceClass, RawEnvelope
from quantmesh.data.instruments import InstrumentCatalog
from quantmesh.domain.market_data import Bar
from quantmesh.research.features import FEATURES

_AAPL = "moomoo:US:AAPL:XNAS"
_BARS_MEDIA_TYPE = "application/vnd.quantmesh.bars+json"
_FEATURES_MEDIA_TYPE = "application/vnd.quantmesh.features+json"


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


class FabricFeatureSpec(BaseModel):
    """The one feature admitted to the first end-to-end tracer."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    name: str = Field(pattern=r"^log_return$")
    window: int = Field(ge=2, le=2)


class FabricPublication(BaseModel):
    """Stable IDs for one complete raw-to-feature publication."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    raw_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    adjusted_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    qualifies: bool


class FabricPublisher:
    """Publish one conservative AAPL daily-bars lineage vertical slice."""

    def __init__(
        self,
        store: ManifestStore,
        *,
        code_commit: str,
        catalog: InstrumentCatalog | None = None,
    ) -> None:
        if len(code_commit) != 40 or any(
            character not in "0123456789abcdef" for character in code_commit
        ):
            raise ValueError("code_commit must be a lowercase 40-character hex commit")
        self.store = store
        self.code_commit = code_commit
        self.catalog = catalog or InstrumentCatalog.bounded_default()
        self.calendar = CalendarService()

    def publish_bars(
        self,
        envelope: RawEnvelope,
        bars: list[Bar],
        *,
        adjustment_policy: AdjustmentPolicy,
        feature_specs: tuple[FabricFeatureSpec, ...],
    ) -> FabricPublication:
        """Validate raw bytes first, then publish four immutable linked layers."""
        raw_payload = self.store.objects.get_bytes(envelope.raw_object)
        self._validate_request(envelope, bars, adjustment_policy, feature_specs, raw_payload)
        normalized_payload = canonical_json_bytes([bar.model_dump(mode="json") for bar in bars])
        normalized_object = self.store.objects.put_bytes(_BARS_MEDIA_TYPE, normalized_payload)
        envelope_object = self.store.objects.put_bytes(
            "application/vnd.quantmesh.raw-envelope+json",
            envelope.canonical_bytes(),
        )
        adjusted_bars = adjustment_policy.apply(bars)
        if adjusted_bars != bars:
            raise ValueError("the identity adjustment policy must not change bars")
        adjusted_payload = canonical_json_bytes(
            [bar.model_dump(mode="json") for bar in adjusted_bars]
        )
        adjusted_object = self.store.objects.put_bytes(_BARS_MEDIA_TYPE, adjusted_payload)
        feature_rows = self._compute_features(adjusted_bars, feature_specs)
        feature_object = self.store.objects.put_bytes(
            _FEATURES_MEDIA_TYPE, canonical_json_bytes(feature_rows)
        )
        common = self._common(envelope, bars)

        raw = self._publish(
            dataset_id="aapl-daily-raw",
            layer=ArtifactLayer.RAW,
            objects=(envelope.raw_object, envelope_object),
            row_identities=envelope.source_event_ids,
            parent_ids=(),
            schema_digest=_digest({"raw_schema": envelope.schema_version}),
            transformation_digest=_digest({"operation": "capture-exact-bytes-v1"}),
            adjustment_policy=None,
            event_start=envelope.event_start,
            event_end=envelope.event_end,
            **common,
        )
        normalized = self._publish(
            dataset_id="aapl-daily-normalized",
            layer=ArtifactLayer.NORMALIZED,
            objects=(normalized_object,),
            row_identities=self._bar_identities(bars),
            parent_ids=(raw.manifest_id,),
            schema_digest=_digest({"model": "Bar", "schema": 1}),
            transformation_digest=_digest(
                {
                    "operation": "fixture-json-to-canonical-bars-v1",
                    "adapter": envelope.adapter_version,
                }
            ),
            adjustment_policy=None,
            event_start=bars[0].timestamp.astimezone(UTC),
            event_end=bars[-1].timestamp.astimezone(UTC),
            **common,
        )
        adjusted = self._publish(
            dataset_id="aapl-daily-adjusted",
            layer=ArtifactLayer.ADJUSTED,
            objects=(adjusted_object,),
            row_identities=self._bar_identities(adjusted_bars),
            parent_ids=(normalized.manifest_id,),
            schema_digest=_digest({"model": "Bar", "schema": 1}),
            transformation_digest=_digest(adjustment_policy.model_dump(mode="json")),
            adjustment_policy=adjustment_policy.policy_id,
            event_start=adjusted_bars[0].timestamp.astimezone(UTC),
            event_end=adjusted_bars[-1].timestamp.astimezone(UTC),
            **common,
        )
        feature = self._publish(
            dataset_id="aapl-daily-feature-log-return-2",
            layer=ArtifactLayer.FEATURE,
            objects=(feature_object,),
            row_identities=tuple(f"log_return:{row['timestamp']}" for row in feature_rows),
            parent_ids=(adjusted.manifest_id,),
            schema_digest=_digest(
                {"fields": ["name", "timestamp", "value", "window"], "schema": 1}
            ),
            transformation_digest=_digest(
                {"features": [item.model_dump(mode="json") for item in feature_specs]}
            ),
            adjustment_policy=adjustment_policy.policy_id,
            event_start=datetime.fromisoformat(feature_rows[0]["timestamp"]),
            event_end=datetime.fromisoformat(feature_rows[-1]["timestamp"]),
            **common,
        )
        return FabricPublication(
            raw_id=raw.manifest_id,
            normalized_id=normalized.manifest_id,
            adjusted_id=adjusted.manifest_id,
            feature_id=feature.manifest_id,
            qualifies=envelope.qualifies and adjustment_policy.qualifies,
        )

    def lineage(self, manifest_id: str) -> tuple[ArtifactManifest, ...]:
        """Return and validate the single-parent lineage from raw to the target."""
        chain: list[ArtifactManifest] = []
        seen: set[str] = set()
        current = self.store.open(manifest_id).manifest
        while True:
            if current.manifest_id in seen:
                raise ManifestIntegrityError("artifact lineage contains a cycle")
            seen.add(current.manifest_id)
            chain.append(current)
            if not current.parent_manifest_ids:
                break
            if len(current.parent_manifest_ids) != 1:
                raise ManifestIntegrityError("tracer lineage must have exactly one parent")
            parent = self.store.open(current.parent_manifest_ids[0]).manifest
            if parent.canonical_instrument != current.canonical_instrument:
                raise ManifestIntegrityError("lineage changes canonical instrument")
            current = parent
        chain.reverse()
        layers = tuple(item.layer for item in chain)
        expected = tuple(ArtifactLayer)[0 : len(layers)]
        if layers != expected:
            raise ManifestIntegrityError("artifact lineage layers are not contiguous")
        self._validate_lineage_derivation(chain)
        return tuple(chain)

    def history(self, manifest_id: str, *, known_at: datetime) -> list[Bar]:
        """Read the latest revision that was knowable at ``known_at``."""
        return self.store.open_known_at(manifest_id, known_at=known_at).read_bars()

    def _validate_request(
        self,
        envelope: RawEnvelope,
        bars: list[Bar],
        adjustment_policy: AdjustmentPolicy,
        feature_specs: tuple[FabricFeatureSpec, ...],
        raw_payload: bytes,
    ) -> None:
        if (
            envelope.provenance is not ProvenanceClass.FIXTURE
            or envelope.provider_id != "fixture-moomoo"
            or envelope.qualifies
        ):
            raise ValueError("the Task 4 tracer admits fixture-moomoo provenance only")
        if adjustment_policy.policy_id != "unadjusted-identity-v1":
            raise ValueError("the Task 4 tracer requires the explicit identity policy")
        if feature_specs != (FabricFeatureSpec(name="log_return", window=2),):
            raise ValueError("the Task 4 tracer requires log_return(window=2)")
        self._validate_bars_contract(envelope, bars)
        try:
            raw_rows = json.loads(raw_payload)
            raw_bars = [Bar.model_validate(item) for item in raw_rows]
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise ValueError("fixture raw payload is not a valid bar response") from error
        if raw_bars != bars:
            raise ValueError("fixture raw payload disagrees with normalized input bars")

    def _validate_bars_contract(self, envelope: RawEnvelope, bars: list[Bar]) -> None:
        """Apply the same bounded raw-bar semantics before writes and on reads."""
        if envelope.canonical_instrument.value != _AAPL or envelope.data_kind is not DataKind.BARS:
            raise ValueError("the Task 4 tracer admits AAPL bars only")
        if len(bars) < 3:
            raise ValueError("the tracer requires at least three bars")
        timestamps = [bar.timestamp.astimezone(UTC) for bar in bars]
        if timestamps != sorted(set(timestamps)):
            raise ValueError("bars must be strictly ordered and unique")
        if any(
            bar.instrument.symbol != "AAPL"
            or bar.instrument.venue.value != "moomoo"
            or bar.instrument.instrument_type.value != "equity"
            or bar.instrument.currency != "USD"
            or bar.interval != "1d"
            for bar in bars
        ):
            raise ValueError("bars disagree with the bounded AAPL daily contract")
        if any(
            not all(
                math.isfinite(value)
                for value in (bar.open, bar.high, bar.low, bar.close, bar.volume)
            )
            for bar in bars
        ):
            raise ValueError("bar OHLCV values must be finite before publication")
        sessions = self.calendar.sessions(
            "XNYS",
            timestamps[0].date(),
            timestamps[-1].date(),
            policy=SessionPolicy.REGULAR,
        )
        opens = {session.session_date: session.open_at for session in sessions}
        if any(opens.get(timestamp.date()) != timestamp for timestamp in timestamps):
            raise ValueError("bar timestamps must match pinned XNYS session opens")
        if envelope.event_start != timestamps[0] or envelope.event_end != timestamps[-1]:
            raise ValueError("envelope event coverage disagrees with bars")
        expected_source_ids = tuple(
            f"US.AAPL:{timestamp.date().isoformat()}" for timestamp in timestamps
        )
        if envelope.source_event_ids != expected_source_ids:
            raise ValueError("source event identities disagree with the fixture rows")
        resolved = self.catalog.resolve(
            "moomoo-opend",
            envelope.provider_symbol,
            effective_at=envelope.session_date,
            known_at=envelope.knowledge_time,
        )
        if resolved != envelope.canonical_instrument:
            raise ValueError("catalog identity disagrees with the raw envelope")

    def _common(self, envelope: RawEnvelope, bars: list[Bar]) -> dict[str, Any]:
        return {
            "canonical_instrument": envelope.canonical_instrument,
            "instrument_catalog_id": self.catalog.catalog_id,
            "data_kind": DataKind.BARS,
            "interval": bars[0].interval,
            "calendar_version": XNYS_REGULAR_VERSION,
            "session_policy": SessionPolicy.REGULAR,
            "adapter_version": envelope.adapter_version,
            "source_rights_id": envelope.source_rights_id,
            "entitlement": envelope.entitlement,
            "knowledge_start": envelope.knowledge_time,
            "knowledge_end": envelope.knowledge_time,
            "quality_report_id": None,
            "created_at": envelope.ingested_at,
            "code_commit": self.code_commit,
            "collection_run_id": envelope.request_id,
        }

    def _publish(
        self,
        *,
        dataset_id: str,
        layer: ArtifactLayer,
        objects: tuple,
        row_identities: tuple[str, ...],
        parent_ids: tuple[str, ...],
        schema_digest: str,
        transformation_digest: str,
        adjustment_policy: str | None,
        event_start: datetime,
        event_end: datetime,
        **common: Any,
    ) -> ArtifactManifest:
        current = self.store.current(dataset_id)
        revision = 1 if current is None else current.manifest.compatibility_revision
        values = {
            **common,
            "dataset_id": dataset_id,
            "layer": layer,
            "objects": objects,
            "row_identities": row_identities,
            "parent_manifest_ids": parent_ids,
            "schema_digest": schema_digest,
            "transformation_policy_digest": transformation_digest,
            "adjustment_policy": adjustment_policy,
            "event_start": event_start,
            "event_end": event_end,
        }
        candidate = ArtifactManifest.build(compatibility_revision=revision, **values)
        if current is not None and candidate.manifest_id == current.manifest.manifest_id:
            return current.manifest
        if current is not None:
            for historical in self.store.manifests(dataset_id):
                historical_candidate = ArtifactManifest.build(
                    compatibility_revision=historical.compatibility_revision,
                    **values,
                )
                if historical_candidate.manifest_id == historical.manifest_id:
                    return historical
            if common["knowledge_start"] <= current.manifest.knowledge_start:
                raise ValueError("a changed revision must have a strictly later knowledge time")
            candidate = ArtifactManifest.build(compatibility_revision=revision + 1, **values)
        self.store.publish(
            candidate,
            expected_current=None if current is None else current.manifest.manifest_id,
        )
        return candidate

    @staticmethod
    def _bar_identities(bars: list[Bar]) -> tuple[str, ...]:
        return tuple(
            f"{bar.instrument.symbol}:{bar.timestamp.astimezone(UTC).isoformat()}" for bar in bars
        )

    @staticmethod
    def _compute_features(
        bars: list[Bar], specs: tuple[FabricFeatureSpec, ...]
    ) -> list[dict[str, Any]]:
        spec = specs[0]
        closes = pd.Series(
            [bar.close for bar in bars],
            index=pd.DatetimeIndex([bar.timestamp for bar in bars]),
            dtype="float64",
        )
        computed = FEATURES[spec.name](closes, {"window": spec.window}).dropna()
        rows = [
            {
                "name": spec.name,
                "timestamp": timestamp.to_pydatetime().astimezone(UTC).isoformat(),
                "value": float(value),
                "window": spec.window,
            }
            for timestamp, value in computed.items()
        ]
        if not rows:
            raise ValueError("feature computation produced no rows")
        return rows

    def _validate_lineage_derivation(self, chain: list[ArtifactManifest]) -> None:
        raw = chain[0]
        envelope_refs = [
            reference
            for reference in raw.objects
            if reference.media_type == "application/vnd.quantmesh.raw-envelope+json"
        ]
        response_refs = [reference for reference in raw.objects if reference not in envelope_refs]
        if len(envelope_refs) != 1 or len(response_refs) != 1:
            raise ManifestIntegrityError("raw lineage must contain one response and one envelope")
        try:
            envelope_payload = self.store.objects.get_bytes(envelope_refs[0])
            envelope = RawEnvelope.model_validate_json(envelope_payload)
            raw_rows = json.loads(self.store.objects.get_bytes(response_refs[0]))
            raw_bars = [Bar.model_validate(item) for item in raw_rows]
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise ManifestIntegrityError("raw lineage cannot be decoded") from error
        if envelope.raw_object != response_refs[0]:
            raise ManifestIntegrityError("raw envelope does not identify its response object")
        if envelope_payload != envelope.canonical_bytes():
            raise ManifestIntegrityError("raw envelope metadata is not canonical")
        if (
            envelope.provenance is not ProvenanceClass.FIXTURE
            or envelope.provider_id != "fixture-moomoo"
            or envelope.qualifies
        ):
            raise ManifestIntegrityError(
                "the Task 4 lineage must be rooted in nonqualifying fixture provenance"
            )
        if raw.row_identities != envelope.source_event_ids:
            raise ManifestIntegrityError("raw manifest identities disagree with its envelope")
        if (
            raw.canonical_instrument != envelope.canonical_instrument
            or raw.instrument_catalog_id != self.catalog.catalog_id
            or raw.data_kind != envelope.data_kind
            or raw.adapter_version != envelope.adapter_version
            or raw.source_rights_id != envelope.source_rights_id
            or raw.entitlement != envelope.entitlement
            or raw.knowledge_start != envelope.knowledge_time
            or raw.knowledge_end != envelope.knowledge_time
            or raw.collection_run_id != envelope.request_id
            or raw.event_start != envelope.event_start
            or raw.event_end != envelope.event_end
            or raw.schema_digest != _digest({"raw_schema": envelope.schema_version})
            or raw.transformation_policy_digest != _digest({"operation": "capture-exact-bytes-v1"})
        ):
            raise ManifestIntegrityError("raw manifest declarations disagree with its envelope")
        try:
            resolved = self.catalog.resolve(
                "moomoo-opend",
                envelope.provider_symbol,
                effective_at=envelope.session_date,
                known_at=envelope.knowledge_time,
            )
        except ValueError as error:
            raise ManifestIntegrityError(
                "raw provider identity is not catalog-resolvable"
            ) from error
        if resolved != envelope.canonical_instrument:
            raise ManifestIntegrityError("raw provider symbol changes canonical instrument")
        try:
            self._validate_bars_contract(envelope, raw_bars)
        except ValueError as error:
            raise ManifestIntegrityError("raw bars violate the tracer contract") from error
        shared_fields = (
            "canonical_instrument",
            "instrument_catalog_id",
            "data_kind",
            "interval",
            "calendar_version",
            "session_policy",
            "adapter_version",
            "source_rights_id",
            "entitlement",
            "knowledge_start",
            "knowledge_end",
            "code_commit",
            "collection_run_id",
        )
        for parent, child in zip(chain, chain[1:]):
            if any(getattr(parent, field) != getattr(child, field) for field in shared_fields):
                raise ManifestIntegrityError("lineage changes shared provenance declarations")
        if len(chain) < 2:
            return
        normalized = chain[1]
        normalized_bars = self.store.open(normalized.manifest_id).read_bars()
        if raw_bars != normalized_bars:
            raise ManifestIntegrityError("normalized bars are not derived from the raw response")
        if len(normalized.objects) != 1 or self.store.objects.get_bytes(
            normalized.objects[0]
        ) != canonical_json_bytes([bar.model_dump(mode="json") for bar in raw_bars]):
            raise ManifestIntegrityError("normalized artifact is not the canonical derivation")
        if normalized.schema_digest != _digest({"model": "Bar", "schema": 1}):
            raise ManifestIntegrityError("normalized schema declaration is invalid")
        if normalized.transformation_policy_digest != _digest(
            {
                "operation": "fixture-json-to-canonical-bars-v1",
                "adapter": envelope.adapter_version,
            }
        ):
            raise ManifestIntegrityError("normalized transformation declaration is invalid")
        if len(chain) < 3:
            return
        adjusted = chain[2]
        if adjusted.adjustment_policy != "unadjusted-identity-v1":
            raise ManifestIntegrityError("adjusted lineage uses an unsupported policy")
        adjusted_bars = self.store.open(adjusted.manifest_id).read_bars()
        if adjusted_bars != normalized_bars:
            raise ManifestIntegrityError("identity-adjusted bars differ from normalized bars")
        if (
            len(adjusted.objects) != 1
            or self.store.objects.get_bytes(adjusted.objects[0])
            != self.store.objects.get_bytes(normalized.objects[0])
            or adjusted.schema_digest != _digest({"model": "Bar", "schema": 1})
        ):
            raise ManifestIntegrityError("adjusted artifact is not the canonical identity output")
        if adjusted.transformation_policy_digest != _digest(
            {
                "policy_id": "unadjusted-identity-v1",
                "applies_corporate_actions": False,
                "qualifies": False,
            }
        ):
            raise ManifestIntegrityError("adjustment transformation declaration is invalid")
        if len(chain) < 4:
            return
        feature = chain[3]
        expected_rows = self._compute_features(
            adjusted_bars,
            (FabricFeatureSpec(name="log_return", window=2),),
        )
        observed_rows = self.store.open(feature.manifest_id).read_features()
        if observed_rows != expected_rows:
            raise ManifestIntegrityError("feature rows are not derived from adjusted bars")
        if len(feature.objects) != 1 or self.store.objects.get_bytes(
            feature.objects[0]
        ) != canonical_json_bytes(expected_rows):
            raise ManifestIntegrityError("feature artifact is not the canonical derivation")
        if feature.schema_digest != _digest(
            {"fields": ["name", "timestamp", "value", "window"], "schema": 1}
        ):
            raise ManifestIntegrityError("feature schema declaration is invalid")
        if feature.transformation_policy_digest != _digest(
            {"features": [{"name": "log_return", "window": 2}]}
        ):
            raise ManifestIntegrityError("feature transformation declaration is invalid")
