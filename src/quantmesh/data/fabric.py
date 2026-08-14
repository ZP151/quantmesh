"""Bounded raw-to-feature publication tracer for the trusted-data fabric."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from quantmesh.data.adjustments import (
    AdjustmentPolicy,
    EquityAdjustmentPolicy,
    EquitySplitAction,
    normalize_moomoo_split_actions,
)
from quantmesh.data.artifacts import (
    ArtifactLayer,
    ArtifactManifest,
    ManifestIntegrityError,
    ManifestStore,
    canonical_json_bytes,
)
from quantmesh.data.calendars import XNYS_REGULAR_VERSION, CalendarService, SessionPolicy
from quantmesh.data.capabilities import DataKind, EntitlementState
from quantmesh.data.envelopes import ProvenanceClass, RawEnvelope
from quantmesh.data.instruments import InstrumentCatalog
from quantmesh.data.moomoo_collection import MoomooRawPayload, MoomooWorkerRequest
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.moomoo.market_data import MoomooDataAdapter
from quantmesh.research.features import FEATURES

_AAPL = "moomoo:US:AAPL:XNAS"
_BARS_MEDIA_TYPE = "application/vnd.quantmesh.bars+json"
_FEATURES_MEDIA_TYPE = "application/vnd.quantmesh.features+json"
_SPLITS_MEDIA_TYPE = "application/vnd.quantmesh.equity-splits+json"
_NEW_YORK = ZoneInfo("America/New_York")


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _manifest_run_id(store: object, fallback: str) -> str:
    return getattr(store, "collection_run_id", None) or fallback


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


class MoomooFabricPublication(BaseModel):
    """Every immutable artifact produced from one complete OpenD bundle."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    bars_raw_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    factors_raw_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    splits_raw_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    dividends_raw_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    actions_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    adjusted_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    qualifies: bool

    @property
    def manifest_ids(self) -> tuple[str, ...]:
        return (
            self.bars_raw_id,
            self.factors_raw_id,
            self.splits_raw_id,
            self.dividends_raw_id,
            self.normalized_id,
            self.actions_id,
            self.adjusted_id,
            self.feature_id,
        )


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
            "collection_run_id": _manifest_run_id(self.store, envelope.request_id),
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
            or raw.collection_run_id
            != _manifest_run_id(self.store, envelope.request_id)
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


class MoomooFabricPublisher:
    """Publish real AAPL/NVDA evidence without weakening the fixture tracer."""

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

    def publish(
        self,
        request: MoomooWorkerRequest,
        payload: MoomooRawPayload,
    ) -> MoomooFabricPublication:
        """Publish separate raw surfaces, then canonical adjusted lineage."""
        payload.validate_for(request)
        bars = list(payload.bars)
        if len(bars) < 3:
            raise ValueError("trusted feature publication requires at least three bars")
        canonical = request.target.canonical_instrument
        split_rows = [
            row for page in payload.stock_split_pages for row in page["rows"]
        ]
        factor_rows = payload.adjustment_factors["rows"]
        dividend_rows = payload.dividends["rows"]
        actions = normalize_moomoo_split_actions(
            canonical_instrument=canonical,
            factor_rows=factor_rows,
            split_rows=split_rows,
        )
        if any(action.announced_at > payload.received_at for action in actions):
            raise ValueError("split action was not knowable at worker receipt time")
        bar_ids = self._bar_identities(bars)
        factor_ids = self._source_identities("factor", factor_rows)
        split_ids = self._source_identities("split", split_rows)
        dividend_ids = self._source_identities("dividend", dividend_rows)
        factor_times = self._factor_times(factor_rows)
        split_times = self._split_times(split_rows)
        dividend_times = self._dividend_times(dividend_rows)
        prefix = self._dataset_prefix(request)
        bars_raw = self._publish_raw_surface(
            request,
            payload,
            dataset_id=f"{prefix}-raw-bars",
            endpoint="request_history_kline",
            data_kind=DataKind.BARS,
            source=payload.history_pages,
            event_times=[bar.timestamp for bar in bars],
            row_ids=bar_ids,
        )
        factors_raw = self._publish_raw_surface(
            request,
            payload,
            dataset_id=f"{prefix}-raw-adjustment-factors",
            endpoint="get_rehab",
            data_kind=DataKind.ADJUSTMENT_FACTORS,
            source=payload.adjustment_factors,
            event_times=factor_times,
            row_ids=factor_ids,
        )
        splits_raw = self._publish_raw_surface(
            request,
            payload,
            dataset_id=f"{prefix}-raw-splits",
            endpoint="get_corporate_actions_stock_splits",
            data_kind=DataKind.SPLITS,
            source=payload.stock_split_pages,
            event_times=split_times,
            row_ids=split_ids,
        )
        dividends_raw = self._publish_raw_surface(
            request,
            payload,
            dataset_id=f"{prefix}-raw-dividends",
            endpoint="get_corporate_actions_dividends",
            data_kind=DataKind.DIVIDENDS,
            source=payload.dividends,
            event_times=dividend_times,
            row_ids=dividend_ids,
        )

        common = self._common(request, payload)
        normalized_object = self.store.objects.put_bytes(
            _BARS_MEDIA_TYPE,
            canonical_json_bytes([bar.model_dump(mode="json") for bar in bars]),
        )
        normalized = self._publish_manifest(
            dataset_id=f"{prefix}-normalized",
            layer=ArtifactLayer.NORMALIZED,
            objects=(normalized_object,),
            row_identities=bar_ids,
            parent_ids=(bars_raw.manifest_id,),
            schema_digest=_digest({"model": "Bar", "schema": 1}),
            transformation_digest=_digest(
                {"operation": "moomoo-history-pages-to-canonical-bars-v1"}
            ),
            adjustment_policy=None,
            event_start=bars[0].timestamp,
            event_end=bars[-1].timestamp,
            data_kind=DataKind.BARS,
            interval=request.target.interval,
            **common,
        )

        action_rows = [action.model_dump(mode="json") for action in actions]
        actions_object = self.store.objects.put_bytes(
            _SPLITS_MEDIA_TYPE, canonical_json_bytes(action_rows)
        )
        action_ids = tuple(action.action_id for action in actions)
        if actions:
            action_start, action_end = actions[0].effective_at, actions[-1].effective_at
        else:
            action_start = action_end = max(
                factors_raw.event_end,
                splits_raw.event_end,
            )
            action_ids = (f"no-split:{_digest([factors_raw.manifest_id, splits_raw.manifest_id])}",)
        action_manifest = self._publish_manifest(
            dataset_id=f"{prefix}-normalized-splits",
            layer=ArtifactLayer.NORMALIZED,
            objects=(actions_object,),
            row_identities=action_ids,
            parent_ids=(factors_raw.manifest_id, splits_raw.manifest_id),
            schema_digest=_digest({"model": "EquitySplitAction", "schema": 1}),
            transformation_digest=_digest(
                {"operation": "cross-check-rehab-and-corporate-actions-v1"}
            ),
            adjustment_policy=None,
            event_start=action_start,
            event_end=action_end,
            data_kind=DataKind.SPLITS,
            interval=None,
            **common,
        )

        policy = EquityAdjustmentPolicy(
            canonical_instrument=canonical,
            factor_manifest_id=factors_raw.manifest_id,
            action_manifest_id=action_manifest.manifest_id,
            known_at=payload.received_at,
        )
        adjusted_bars = policy.apply(bars, actions)
        adjusted_object = self.store.objects.put_bytes(
            _BARS_MEDIA_TYPE,
            canonical_json_bytes([bar.model_dump(mode="json") for bar in adjusted_bars]),
        )
        adjusted = self._publish_manifest(
            dataset_id=f"{prefix}-adjusted",
            layer=ArtifactLayer.ADJUSTED,
            objects=(adjusted_object,),
            row_identities=self._bar_identities(adjusted_bars),
            parent_ids=(normalized.manifest_id, action_manifest.manifest_id),
            schema_digest=_digest({"model": "Bar", "schema": 1}),
            transformation_digest=_digest(policy.model_dump(mode="json")),
            adjustment_policy=policy.policy_id,
            event_start=adjusted_bars[0].timestamp,
            event_end=adjusted_bars[-1].timestamp,
            data_kind=DataKind.BARS,
            interval=request.target.interval,
            **common,
        )
        feature_rows = FabricPublisher._compute_features(
            adjusted_bars,
            (FabricFeatureSpec(name="log_return", window=2),),
        )
        feature_object = self.store.objects.put_bytes(
            _FEATURES_MEDIA_TYPE, canonical_json_bytes(feature_rows)
        )
        feature = self._publish_manifest(
            dataset_id=f"{prefix}-feature-log-return-2",
            layer=ArtifactLayer.FEATURE,
            objects=(feature_object,),
            row_identities=tuple(f"log_return:{row['timestamp']}" for row in feature_rows),
            parent_ids=(adjusted.manifest_id,),
            schema_digest=_digest(
                {"fields": ["name", "timestamp", "value", "window"], "schema": 1}
            ),
            transformation_digest=_digest(
                {"features": [{"name": "log_return", "window": 2}]}
            ),
            adjustment_policy=policy.policy_id,
            event_start=datetime.fromisoformat(feature_rows[0]["timestamp"]),
            event_end=datetime.fromisoformat(feature_rows[-1]["timestamp"]),
            data_kind=DataKind.BARS,
            interval=request.target.interval,
            **common,
        )
        publication = MoomooFabricPublication(
            bars_raw_id=bars_raw.manifest_id,
            factors_raw_id=factors_raw.manifest_id,
            splits_raw_id=splits_raw.manifest_id,
            dividends_raw_id=dividends_raw.manifest_id,
            normalized_id=normalized.manifest_id,
            actions_id=action_manifest.manifest_id,
            adjusted_id=adjusted.manifest_id,
            feature_id=feature.manifest_id,
            qualifies=True,
        )
        self.validate_publication(publication)
        return publication

    def validate_publication(
        self, publication: MoomooFabricPublication
    ) -> tuple[ArtifactManifest, ...]:
        """Recompute the complete multi-parent derivation from immutable bytes."""
        if not publication.qualifies or len(set(publication.manifest_ids)) != 8:
            raise ManifestIntegrityError("Moomoo publication has invalid manifest roles")
        bar_source, bar_raw, bar_envelope = self._read_raw(
            publication.bars_raw_id,
            expected_kind=DataKind.BARS,
            expected_endpoint="request_history_kline",
        )
        factor_source, factors_raw, _ = self._read_raw(
            publication.factors_raw_id,
            expected_kind=DataKind.ADJUSTMENT_FACTORS,
            expected_endpoint="get_rehab",
        )
        split_source, splits_raw, _ = self._read_raw(
            publication.splits_raw_id,
            expected_kind=DataKind.SPLITS,
            expected_endpoint="get_corporate_actions_stock_splits",
        )
        _, dividends_raw, _ = self._read_raw(
            publication.dividends_raw_id,
            expected_kind=DataKind.DIVIDENDS,
            expected_endpoint="get_corporate_actions_dividends",
        )
        normalized = self.store.open(publication.normalized_id).manifest
        action_manifest = self.store.open(publication.actions_id).manifest
        adjusted = self.store.open(publication.adjusted_id).manifest
        feature = self.store.open(publication.feature_id).manifest
        manifests = (
            bar_raw,
            factors_raw,
            splits_raw,
            dividends_raw,
            normalized,
            action_manifest,
            adjusted,
            feature,
        )
        canonical = bar_raw.canonical_instrument
        shared = (
            "canonical_instrument",
            "instrument_catalog_id",
            "calendar_version",
            "session_policy",
            "source_rights_id",
            "entitlement",
            "adapter_version",
            "knowledge_start",
            "knowledge_end",
            "created_at",
            "code_commit",
            "collection_run_id",
        )
        if any(
            any(getattr(item, field) != getattr(bar_raw, field) for field in shared)
            for item in manifests[1:]
        ):
            raise ManifestIntegrityError("Moomoo publication changes shared provenance")
        if not isinstance(bar_source, list):
            raise ManifestIntegrityError("Moomoo raw history source must be a page list")
        symbol = canonical.value.split(":")[2]
        instrument = Instrument(
            symbol=symbol,
            venue=Venue.MOOMOO,
            instrument_type=InstrumentType.EQUITY,
            currency="USD",
        )
        try:
            source_bars = MoomooDataAdapter().history_pages_to_bars(instrument, bar_source)
        except ValueError as error:
            raise ManifestIntegrityError("Moomoo raw history cannot be normalized") from error
        normalized_bars = self.store.open(publication.normalized_id).read_bars()
        if (
            normalized.layer is not ArtifactLayer.NORMALIZED
            or normalized.data_kind is not DataKind.BARS
            or normalized.parent_manifest_ids != (bar_raw.manifest_id,)
            or normalized_bars != source_bars
            or normalized.row_identities != self._bar_identities(source_bars)
            or normalized.schema_digest != _digest({"model": "Bar", "schema": 1})
            or normalized.transformation_policy_digest
            != _digest({"operation": "moomoo-history-pages-to-canonical-bars-v1"})
            or normalized.adjustment_policy is not None
        ):
            raise ManifestIntegrityError("normalized bars are not derived from raw pages")
        if bar_envelope.source_event_ids != self._bar_identities(source_bars):
            raise ManifestIntegrityError("raw history identities disagree with canonical bars")
        if not isinstance(factor_source, dict) or not isinstance(split_source, list):
            raise ManifestIntegrityError("Moomoo corporate-action sources have invalid shape")
        try:
            factor_rows = factor_source["rows"]
            split_rows = [row for page in split_source for row in page["rows"]]
            expected_actions = normalize_moomoo_split_actions(
                canonical_instrument=canonical,
                factor_rows=factor_rows,
                split_rows=split_rows,
            )
            if (
                len(action_manifest.objects) != 1
                or action_manifest.objects[0].media_type != _SPLITS_MEDIA_TYPE
            ):
                raise ValueError("normalized split actions require one canonical object")
            action_payload = json.loads(
                self.store.objects.get_bytes(action_manifest.objects[0])
            )
            if not isinstance(action_payload, list):
                raise TypeError("normalized split actions must be a list")
            observed_actions = [
                EquitySplitAction.model_validate_json(canonical_json_bytes(item))
                for item in action_payload
            ]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ManifestIntegrityError("normalized split actions cannot be derived") from error
        if observed_actions != expected_actions or action_manifest.parent_manifest_ids != (
            factors_raw.manifest_id,
            splits_raw.manifest_id,
        ):
            raise ManifestIntegrityError("normalized split actions are not source-derived")
        expected_action_ids = tuple(action.action_id for action in expected_actions)
        if not expected_action_ids:
            expected_action_ids = (
                f"no-split:{_digest([factors_raw.manifest_id, splits_raw.manifest_id])}",
            )
        if expected_actions:
            expected_action_start = expected_actions[0].effective_at
            expected_action_end = expected_actions[-1].effective_at
        else:
            expected_action_start = expected_action_end = max(
                factors_raw.event_end,
                splits_raw.event_end,
            )
        if (
            action_manifest.event_start != expected_action_start
            or action_manifest.event_end != expected_action_end
        ):
            raise ManifestIntegrityError("normalized action coverage is not source-derived")
        if (
            action_manifest.layer is not ArtifactLayer.NORMALIZED
            or action_manifest.data_kind is not DataKind.SPLITS
            or action_manifest.interval is not None
            or action_manifest.row_identities != expected_action_ids
            or action_manifest.schema_digest
            != _digest({"model": "EquitySplitAction", "schema": 1})
            or action_manifest.transformation_policy_digest
            != _digest({"operation": "cross-check-rehab-and-corporate-actions-v1"})
            or action_manifest.adjustment_policy is not None
        ):
            raise ManifestIntegrityError("normalized split action declaration is invalid")
        policy = EquityAdjustmentPolicy(
            canonical_instrument=canonical,
            factor_manifest_id=factors_raw.manifest_id,
            action_manifest_id=action_manifest.manifest_id,
            known_at=adjusted.knowledge_end,
        )
        expected_adjusted = policy.apply(source_bars, expected_actions)
        observed_adjusted = self.store.open(adjusted.manifest_id).read_bars()
        if (
            adjusted.layer is not ArtifactLayer.ADJUSTED
            or adjusted.data_kind is not DataKind.BARS
            or adjusted.parent_manifest_ids
            != (normalized.manifest_id, action_manifest.manifest_id)
            or adjusted.transformation_policy_digest
            != _digest(policy.model_dump(mode="json"))
            or adjusted.schema_digest != _digest({"model": "Bar", "schema": 1})
            or adjusted.adjustment_policy != policy.policy_id
            or adjusted.row_identities != self._bar_identities(expected_adjusted)
            or observed_adjusted != expected_adjusted
        ):
            raise ManifestIntegrityError("adjusted bars are not policy-derived")
        expected_features = FabricPublisher._compute_features(
            expected_adjusted,
            (FabricFeatureSpec(name="log_return", window=2),),
        )
        if (
            feature.layer is not ArtifactLayer.FEATURE
            or feature.data_kind is not DataKind.BARS
            or feature.parent_manifest_ids != (adjusted.manifest_id,)
            or feature.schema_digest
            != _digest(
                {"fields": ["name", "timestamp", "value", "window"], "schema": 1}
            )
            or feature.transformation_policy_digest
            != _digest({"features": [{"name": "log_return", "window": 2}]})
            or feature.adjustment_policy != policy.policy_id
            or self.store.open(feature.manifest_id).read_features() != expected_features
        ):
            raise ManifestIntegrityError("feature declaration or derivation is invalid")
        return manifests

    def _read_raw(
        self,
        manifest_id: str,
        *,
        expected_kind: DataKind,
        expected_endpoint: str,
    ) -> tuple[object, ArtifactManifest, RawEnvelope]:
        manifest = self.store.open(manifest_id).manifest
        if manifest.layer is not ArtifactLayer.RAW or manifest.parent_manifest_ids:
            raise ManifestIntegrityError("Moomoo source is not a raw root")
        envelopes = [
            reference
            for reference in manifest.objects
            if reference.media_type == "application/vnd.quantmesh.raw-envelope+json"
        ]
        sources = [reference for reference in manifest.objects if reference not in envelopes]
        if len(envelopes) != 1 or len(sources) != 1:
            raise ManifestIntegrityError("Moomoo raw root must bind one source and envelope")
        try:
            envelope_bytes = self.store.objects.get_bytes(envelopes[0])
            envelope = RawEnvelope.model_validate_json(envelope_bytes)
            source_bytes = self.store.objects.get_bytes(sources[0])
            source = json.loads(source_bytes)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise ManifestIntegrityError("Moomoo raw root is not decodable") from error
        if (
            envelope.canonical_bytes() != envelope_bytes
            or canonical_json_bytes(source) != source_bytes
            or envelope.raw_object != sources[0]
            or envelope.provenance is not ProvenanceClass.REAL
            or envelope.entitlement is not EntitlementState.AVAILABLE
            or envelope.data_kind is not expected_kind
            or not envelope.endpoint.endswith(f"/{expected_endpoint}")
            or envelope.provider_symbol
            != ".".join(envelope.canonical_instrument.value.split(":")[1:3])
            or manifest.row_identities != envelope.source_event_ids
            or manifest.canonical_instrument != envelope.canonical_instrument
            or manifest.data_kind != envelope.data_kind
            or manifest.event_start != envelope.event_start
            or manifest.event_end != envelope.event_end
            or manifest.knowledge_start != envelope.knowledge_time
            or manifest.knowledge_end != envelope.knowledge_time
            or manifest.created_at != envelope.ingested_at
            or manifest.adapter_version != envelope.adapter_version
            or manifest.source_rights_id != envelope.source_rights_id
            or manifest.entitlement is not envelope.entitlement
            or manifest.schema_digest != _digest({"raw_schema": envelope.schema_version})
            or manifest.transformation_policy_digest
            != _digest({"operation": "capture-sdk-json-v1"})
            or manifest.adjustment_policy is not None
            or (
                expected_kind is DataKind.BARS
                and envelope.cursor
                != canonical_json_bytes(
                    {
                        "contract": "moomoo-history-pagination-v1",
                        "pages": [
                            {
                                "request": page["request_page_req_key"],
                                "next": page["next_page_req_key"],
                            }
                            for page in source
                        ],
                    }
                ).decode()
            )
            or (
                expected_kind is DataKind.SPLITS
                and envelope.cursor
                != canonical_json_bytes(
                    {
                        "contract": "moomoo-stock-split-pagination-v1",
                        "pages": [
                            {
                                "request": page["request_next_key"],
                                "next": page["next_key"],
                            }
                            for page in source
                        ],
                    }
                ).decode()
            )
            or (
                expected_kind not in (DataKind.BARS, DataKind.SPLITS)
                and envelope.cursor is not None
            )
        ):
            raise ManifestIntegrityError("Moomoo raw manifest disagrees with its envelope")
        try:
            expected_ids, expected_start, expected_end, expected_interval = (
                self._raw_source_declarations(
                    source,
                    source_bytes=source_bytes,
                    envelope=envelope,
                    expected_kind=expected_kind,
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ManifestIntegrityError("Moomoo raw source declarations are invalid") from error
        if (
            envelope.source_event_ids != expected_ids
            or envelope.event_start != expected_start
            or envelope.event_end != expected_end
            or manifest.row_identities != expected_ids
            or manifest.event_start != expected_start
            or manifest.event_end != expected_end
            or manifest.interval != expected_interval
        ):
            raise ManifestIntegrityError("Moomoo raw declarations are not source-derived")
        return source, manifest, envelope

    def _raw_source_declarations(
        self,
        source: object,
        *,
        source_bytes: bytes,
        envelope: RawEnvelope,
        expected_kind: DataKind,
    ) -> tuple[tuple[str, ...], datetime, datetime, str | None]:
        """Recompute raw identities and coverage from immutable provider bytes."""
        if expected_kind is DataKind.BARS:
            if not isinstance(source, list):
                raise TypeError("history source must be a page list")
            symbol = envelope.canonical_instrument.value.split(":")[2]
            instrument = Instrument(
                symbol=symbol,
                venue=Venue.MOOMOO,
                instrument_type=InstrumentType.EQUITY,
                currency="USD",
            )
            bars = MoomooDataAdapter().history_pages_to_bars(instrument, source)
            if not bars or len({bar.interval for bar in bars}) != 1:
                raise ValueError("history source has no unique interval")
            return (
                self._bar_identities(bars),
                bars[0].timestamp,
                bars[-1].timestamp,
                bars[0].interval,
            )
        if expected_kind is DataKind.ADJUSTMENT_FACTORS:
            if not isinstance(source, dict) or not isinstance(source.get("rows"), list):
                raise TypeError("factor source must contain rows")
            if source.get("code") != envelope.provider_symbol:
                raise ValueError("factor source code changes canonical instrument")
            rows = source["rows"]
            label = "factor"
            times = self._factor_times(rows)
        elif expected_kind is DataKind.SPLITS:
            if not isinstance(source, list):
                raise TypeError("split source must be a page list")
            if any(
                not isinstance(page, dict)
                or page.get("code") != envelope.provider_symbol
                or not isinstance(page.get("rows"), list)
                for page in source
            ):
                raise ValueError("split source code changes canonical instrument")
            rows = [row for page in source for row in page["rows"]]
            label = "split"
            times = self._split_times(rows)
        elif expected_kind is DataKind.DIVIDENDS:
            if not isinstance(source, dict) or not isinstance(source.get("rows"), list):
                raise TypeError("dividend source must contain rows")
            if source.get("code") != envelope.provider_symbol:
                raise ValueError("dividend source code changes canonical instrument")
            rows = source["rows"]
            label = "dividend"
            times = self._dividend_times(rows)
        else:
            raise ValueError("unsupported Moomoo raw role")
        identities = self._source_identities(label, rows)
        if not identities:
            identities = (f"empty-response:{hashlib.sha256(source_bytes).hexdigest()}",)
        return (
            identities,
            min(times, default=envelope.received_at),
            max(times, default=envelope.received_at),
            None,
        )

    def _publish_raw_surface(
        self,
        request: MoomooWorkerRequest,
        payload: MoomooRawPayload,
        *,
        dataset_id: str,
        endpoint: str,
        data_kind: DataKind,
        source: object,
        event_times: list[datetime],
        row_ids: tuple[str, ...],
    ) -> ArtifactManifest:
        source_bytes = canonical_json_bytes(source)
        event_start = min(event_times, default=payload.received_at)
        event_end = max(event_times, default=payload.received_at)
        if not row_ids:
            row_ids = (f"empty-response:{hashlib.sha256(source_bytes).hexdigest()}",)
        request_id = self._run_id(request, endpoint)
        envelope = RawEnvelope.capture(
            objects=self.store.objects,
            payload=source_bytes,
            content_type=f"application/vnd.quantmesh.moomoo-{data_kind.value}+json",
            provider_id="moomoo-opend",
            endpoint=f"opend://{request.host}:{request.port}/{endpoint}",
            request_id=request_id,
            request_window_start=min(request.window.start, event_start),
            request_window_end=max(request.window.end, event_end),
            collection_window_start=request.window.start,
            collection_window_end=request.window.end,
            cursor=(
                payload.history_pagination_evidence
                if data_kind is DataKind.BARS
                else payload.stock_split_pagination_evidence
                if data_kind is DataKind.SPLITS
                else None
            ),
            canonical_instrument=request.target.canonical_instrument,
            provider_symbol=request.target.provider_symbol,
            data_kind=data_kind,
            source_event_ids=row_ids,
            event_start=event_start,
            event_end=event_end,
            session_date=event_start.date(),
            provider_available_at=None,
            received_at=payload.received_at,
            ingested_at=payload.received_at,
            provider_version=payload.provider_version,
            adapter_version="quantmesh-moomoo-collection-v1",
            schema_version=f"moomoo-{data_kind.value}-v1",
            source_rights_id="moomoo-operator-market-data",
            entitlement=EntitlementState.AVAILABLE,
            provenance=ProvenanceClass.REAL,
        )
        envelope_object = self.store.objects.put_bytes(
            "application/vnd.quantmesh.raw-envelope+json", envelope.canonical_bytes()
        )
        return self._publish_manifest(
            dataset_id=dataset_id,
            layer=ArtifactLayer.RAW,
            objects=(envelope.raw_object, envelope_object),
            row_identities=row_ids,
            parent_ids=(),
            schema_digest=_digest({"raw_schema": envelope.schema_version}),
            transformation_digest=_digest({"operation": "capture-sdk-json-v1"}),
            adjustment_policy=None,
            event_start=event_start,
            event_end=event_end,
            data_kind=data_kind,
            interval=request.target.interval if data_kind is DataKind.BARS else None,
            collection_run_id=_manifest_run_id(
                self.store, self._run_id(request, "collection-bundle")
            ),
            **self._common(request, payload, include_run_id=False),
        )

    def _common(
        self,
        request: MoomooWorkerRequest,
        payload: MoomooRawPayload,
        *,
        include_run_id: bool = True,
    ) -> dict[str, Any]:
        values: dict[str, Any] = {
            "canonical_instrument": request.target.canonical_instrument,
            "instrument_catalog_id": self.catalog.catalog_id,
            "calendar_version": XNYS_REGULAR_VERSION,
            "session_policy": SessionPolicy.REGULAR,
            "adapter_version": "quantmesh-moomoo-collection-v1",
            "source_rights_id": "moomoo-operator-market-data",
            "entitlement": EntitlementState.AVAILABLE,
            "knowledge_start": payload.received_at,
            "knowledge_end": payload.received_at,
            "quality_report_id": None,
            "created_at": payload.received_at,
            "code_commit": self.code_commit,
        }
        if include_run_id:
            values["collection_run_id"] = _manifest_run_id(
                self.store, self._run_id(request, "collection-bundle")
            )
        return values

    def _publish_manifest(self, **values: Any) -> ArtifactManifest:
        values["parent_manifest_ids"] = values.pop("parent_ids")
        values["transformation_policy_digest"] = values.pop("transformation_digest")
        dataset_id = values["dataset_id"]
        current = self.store.current(dataset_id)
        revision = 1 if current is None else current.manifest.compatibility_revision
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
            candidate = ArtifactManifest.build(compatibility_revision=revision + 1, **values)
        self.store.publish(
            candidate,
            expected_current=None if current is None else current.manifest.manifest_id,
        )
        return candidate

    @staticmethod
    def _dataset_prefix(request: MoomooWorkerRequest) -> str:
        symbol = request.target.provider_symbol.split(".", maxsplit=1)[1].lower()
        return f"moomoo-{symbol}-{request.target.interval}"

    @staticmethod
    def _run_id(request: MoomooWorkerRequest, endpoint: str) -> str:
        return "moomoo:" + _digest(
            {"request": request.model_dump(mode="json"), "endpoint": endpoint}
        )

    @staticmethod
    def _bar_identities(bars: list[Bar]) -> tuple[str, ...]:
        return tuple(
            f"{bar.instrument.symbol}:{bar.timestamp.astimezone(UTC).isoformat()}" for bar in bars
        )

    @staticmethod
    def _source_identities(label: str, rows: list[dict]) -> tuple[str, ...]:
        identities = tuple(f"{label}:{_digest(row)}" for row in rows)
        if len(identities) != len(set(identities)):
            raise ValueError(f"duplicate {label} source rows")
        return identities

    @staticmethod
    def _factor_times(rows: list[dict]) -> list[datetime]:
        result = []
        for row in rows:
            try:
                item = date.fromisoformat(row["ex_div_date"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError("factor row has no valid ex_div_date") from error
            result.append(datetime.combine(item, time.min, tzinfo=_NEW_YORK).astimezone(UTC))
        return result

    @staticmethod
    def _split_times(rows: list[dict]) -> list[datetime]:
        result = []
        for row in rows:
            value = row.get("dir_deci_pub_date")
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError("split row has no valid announcement timestamp")
            result.append(datetime.fromtimestamp(value, UTC))
        return result

    @staticmethod
    def _dividend_times(rows: list[dict]) -> list[datetime]:
        result = []
        for row in rows:
            value = row.get("pub_date")
            if not isinstance(value, str):
                raise ValueError("dividend row has no valid publication date")
            parsed = None
            for pattern in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
                try:
                    parsed = datetime.strptime(value, pattern).date()
                    break
                except ValueError:
                    continue
            if parsed is None:
                raise ValueError("dividend row has no valid publication date")
            result.append(datetime.combine(parsed, time.min, tzinfo=_NEW_YORK).astimezone(UTC))
        return result
