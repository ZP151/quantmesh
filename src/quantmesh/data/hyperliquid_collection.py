"""Bounded Hyperliquid public candles into immutable four-layer lineage."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from quantmesh.data.artifacts import (
    ArtifactDataset,
    ArtifactLayer,
    ArtifactManifest,
    ManifestIntegrityError,
    ManifestStore,
    canonical_json_bytes,
)
from quantmesh.data.calendars import CONTINUOUS_UTC_VERSION, SessionPolicy
from quantmesh.data.capabilities import (
    DataKind,
    EntitlementState,
    ProviderAccess,
    ProviderCapability,
    ProviderRequest,
)
from quantmesh.data.envelopes import ProvenanceClass, RawEnvelope
from quantmesh.data.fabric import FabricFeatureSpec, FabricPublisher
from quantmesh.data.instruments import CanonicalInstrumentId, InstrumentCatalog
from quantmesh.data.objects import ObjectRef
from quantmesh.domain.market_data import Bar, interval_to_timedelta
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.hyperliquid.errors import HyperliquidProtocolError
from quantmesh.hyperliquid.market_data import HyperliquidDataAdapter
from quantmesh.hyperliquid.public_info import PublicInfoResponse, PublicInfoTransport

_SYMBOLS = frozenset({"BTC", "ETH", "SOL"})
_MAX_CANDLES = 5_000
_ADJUSTMENT_POLICY = "identity-no-corporate-actions-v1"
_RAW_MEDIA_TYPE = "application/vnd.quantmesh.hyperliquid-candles+json"
_ENVELOPE_MEDIA_TYPE = "application/vnd.quantmesh.raw-envelope+json"
_BARS_MEDIA_TYPE = "application/vnd.quantmesh.bars+json"
_FEATURES_MEDIA_TYPE = "application/vnd.quantmesh.features+json"


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _object_ref(media_type: str, payload: bytes) -> ObjectRef:
    return ObjectRef(
        digest=hashlib.sha256(payload).hexdigest(),
        media_type=media_type,
        byte_length=len(payload),
    )


def _clean_git_commit_matches(code_commit: str) -> bool:
    """Require the producing checkout to be clean and exactly at `code_commit`."""
    root = next(
        (parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists()),
        None,
    )
    if root is None:
        return False
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (FileNotFoundError, subprocess.SubprocessError):
        return False
    return head == code_commit and not status.strip()


class HyperliquidPublication(BaseModel):
    """Stable identities for one public candle lineage."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    raw_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    adjusted_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    qualifies: bool

    @property
    def manifest_ids(self) -> tuple[str, ...]:
        return (self.raw_id, self.normalized_id, self.adjusted_id, self.feature_id)


class HyperliquidCollectionWindow(BaseModel):
    """One explicit UTC candle request window."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def window_is_utc_and_ordered(self) -> Self:
        if (
            self.start.tzinfo is None
            or self.end.tzinfo is None
            or self.start.utcoffset() != timedelta(0)
            or self.end.utcoffset() != timedelta(0)
        ):
            raise ValueError("candle window must be UTC")
        if self.end < self.start:
            raise ValueError("candle window end must not precede start")
        return self


class _PublicCandleRow(BaseModel):
    """Exact public `candleSnapshot` wire contract admitted as raw evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    close_time: int = Field(alias="T", ge=0)
    close: str = Field(alias="c", min_length=1)
    high: str = Field(alias="h", min_length=1)
    interval: str = Field(alias="i", min_length=1)
    low: str = Field(alias="l", min_length=1)
    trade_count: int = Field(alias="n", ge=0)
    open: str = Field(alias="o", min_length=1)
    symbol: str = Field(alias="s", min_length=1)
    open_time: int = Field(alias="t", ge=0)
    volume: str = Field(alias="v", min_length=1)


class HyperliquidCollector:
    """Collect only bounded public candles; no trading object is reachable."""

    def __init__(
        self,
        store: ManifestStore,
        *,
        transport: PublicInfoTransport,
        code_commit: str,
        catalog: InstrumentCatalog | None = None,
    ) -> None:
        if len(code_commit) != 40 or any(
            character not in "0123456789abcdef" for character in code_commit
        ):
            raise ValueError("code_commit must be a lowercase 40-character hex commit")
        self.store = store
        self.transport = transport
        self.code_commit = code_commit
        self.catalog = catalog or InstrumentCatalog.bounded_default()

    def collect_candles(
        self,
        symbols: list[str],
        interval: str,
        window: HyperliquidCollectionWindow,
    ) -> tuple[HyperliquidPublication, ...]:
        """Publish one four-layer identity-adjusted lineage per symbol."""
        start, end = window.start, window.end
        step = interval_to_timedelta(interval)
        self._validate_request(symbols, start=start, end=end, step=step)
        responses: list[tuple[str, PublicInfoResponse, list[Bar]]] = []
        for symbol in symbols:
            self._source_admission(symbol, interval)
            response = self.transport.candles(
                symbol,
                interval,
                start=start,
                end=end,
            )
            bars = self._decode_bars(
                symbol,
                interval,
                response,
                start=start,
                end=end,
            )
            responses.append((symbol, response, bars))
        return tuple(
            self._publish(symbol, interval, start, end, response, bars)
            for symbol, response, bars in responses
        )

    @staticmethod
    def _validate_request(
        symbols: list[str], *, start: datetime, end: datetime, step: timedelta
    ) -> None:
        if not symbols or len(symbols) != len(set(symbols)):
            raise HyperliquidProtocolError("symbols must be a non-empty unique list")
        if any(symbol not in _SYMBOLS for symbol in symbols):
            raise HyperliquidProtocolError("symbol is outside BTC/ETH/SOL")
        if (
            start.tzinfo is None
            or end.tzinfo is None
            or start.utcoffset() != timedelta(0)
            or end.utcoffset() != timedelta(0)
        ):
            raise HyperliquidProtocolError("candle window must be UTC")
        if end < start:
            raise HyperliquidProtocolError("candle window end must not precede start")
        epoch = datetime(1970, 1, 1, tzinfo=UTC)
        if (start - epoch) % step or (end - epoch) % step:
            raise HyperliquidProtocolError("candle window boundaries must be interval-aligned")
        count = int((end - start) // step) + 1
        if count > _MAX_CANDLES:
            raise HyperliquidProtocolError(
                "requested horizon exceeds the provider's 5,000-candle limit"
            )

    @staticmethod
    def _decode_bars(
        symbol: str,
        interval: str,
        response: PublicInfoResponse,
        *,
        start: datetime,
        end: datetime,
    ) -> list[Bar]:
        try:
            decoded = json.loads(response.raw_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise HyperliquidProtocolError("public candle bytes are invalid JSON") from error
        if decoded != response.payload or not isinstance(decoded, list):
            raise HyperliquidProtocolError("public candle bytes disagree with decoded payload")
        try:
            for row in decoded:
                _PublicCandleRow.model_validate(row)
        except ValidationError as error:
            raise HyperliquidProtocolError(
                "public candle row violates the exact wire contract"
            ) from error
        instrument = Instrument(
            symbol=symbol,
            venue=Venue.HYPERLIQUID,
            instrument_type=InstrumentType.PERPETUAL,
            currency="USD",
        )
        bars = HyperliquidDataAdapter().bars(
            HyperliquidCollector._adapter_rows(decoded, interval),
            instrument,
            interval=interval,
        )
        if len(bars) < 3 or len(bars) > _MAX_CANDLES:
            raise HyperliquidProtocolError("trusted feature lineage requires 3–5,000 candles")
        timestamps = [bar.timestamp for bar in bars]
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            raise HyperliquidProtocolError("candle rows must be unique and ordered")
        expected = [
            start + index * interval_to_timedelta(interval)
            for index in range(int((end - start) // interval_to_timedelta(interval)) + 1)
        ]
        if timestamps != expected:
            raise HyperliquidProtocolError("candle rows do not cover the complete requested window")
        try:
            open_times = [int(row["t"]) for row in decoded]
        except (KeyError, TypeError, ValueError) as error:
            raise HyperliquidProtocolError("candle open time is invalid") from error
        if any(isinstance(row.get("t"), bool) for row in decoded):
            raise HyperliquidProtocolError("candle open time is invalid")
        step_ms = int(interval_to_timedelta(interval).total_seconds() * 1_000)
        exclusive_closes = [
            datetime.fromtimestamp((open_time + step_ms) / 1_000, tz=UTC)
            for open_time in open_times
        ]
        if any(close_time > response.received_at for close_time in exclusive_closes):
            raise HyperliquidProtocolError("candle window contains a candle that is not final")
        return bars

    def _publish(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
        response: PublicInfoResponse,
        bars: list[Bar],
    ) -> HyperliquidPublication:
        preflight_bars = self._decode_bars(
            symbol,
            interval,
            response,
            start=start,
            end=end,
        )
        if preflight_bars != bars:
            raise HyperliquidProtocolError("candidate bars disagree with the exact public response")
        canonical = CanonicalInstrumentId(value=f"hyperliquid:perp:{symbol}")
        row_ids = self._bar_ids(bars)
        (
            provenance,
            provider_id,
            provider_version,
            source_rights_id,
            entitlement,
        ) = self._source_admission(symbol, interval)
        run_id = "hyperliquid:" + _digest(
            {
                "symbol": symbol,
                "interval": interval,
                "start": start.isoformat(),
                "end": end.isoformat(),
            }
        )
        envelope = RawEnvelope.capture(
            objects=self.store.objects,
            payload=response.raw_bytes,
            content_type=_RAW_MEDIA_TYPE,
            provider_id=provider_id,
            endpoint="https://api.hyperliquid.xyz/info",
            request_id=run_id,
            request_window_start=start,
            request_window_end=end,
            cursor=None,
            canonical_instrument=canonical,
            provider_symbol=symbol,
            data_kind=DataKind.BARS,
            source_event_ids=row_ids,
            event_start=bars[0].timestamp,
            event_end=bars[-1].timestamp,
            session_date=bars[0].timestamp.date(),
            provider_available_at=None,
            received_at=response.received_at,
            ingested_at=response.received_at,
            provider_version=provider_version,
            adapter_version="quantmesh-hyperliquid-public-v1",
            schema_version="hyperliquid-candleSnapshot-v1",
            source_rights_id=source_rights_id,
            entitlement=entitlement,
            provenance=provenance,
        )
        envelope_ref = self.store.objects.put_bytes(
            _ENVELOPE_MEDIA_TYPE,
            envelope.canonical_bytes(),
        )
        prefix = f"hyperliquid-{symbol.lower()}-{interval}"
        common = {
            "canonical_instrument": canonical,
            "instrument_catalog_id": self.catalog.catalog_id,
            "data_kind": DataKind.BARS,
            "interval": interval,
            "calendar_version": CONTINUOUS_UTC_VERSION,
            "session_policy": SessionPolicy.CONTINUOUS,
            "adapter_version": "quantmesh-hyperliquid-public-v1",
            "source_rights_id": source_rights_id,
            "entitlement": entitlement,
            "knowledge_start": response.received_at,
            "knowledge_end": response.received_at,
            "quality_report_id": None,
            "created_at": response.received_at,
            "code_commit": self.code_commit,
            "collection_run_id": run_id,
        }
        raw = self._candidate_manifest(
            dataset_id=f"{prefix}-raw",
            layer=ArtifactLayer.RAW,
            objects=(envelope.raw_object, envelope_ref),
            row_identities=row_ids,
            schema_digest=_digest({"raw_schema": envelope.schema_version}),
            parent_manifest_ids=(),
            transformation_policy_digest=_digest({"operation": "capture-public-json-v1"}),
            adjustment_policy=None,
            event_start=bars[0].timestamp,
            event_end=bars[-1].timestamp,
            **common,
        )
        bar_bytes = canonical_json_bytes([bar.model_dump(mode="json") for bar in bars])
        bar_ref = self.store.objects.put_bytes(_BARS_MEDIA_TYPE, bar_bytes)
        normalized = self._candidate_manifest(
            dataset_id=f"{prefix}-normalized",
            layer=ArtifactLayer.NORMALIZED,
            objects=(bar_ref,),
            row_identities=row_ids,
            schema_digest=_digest({"model": "Bar", "schema": 1}),
            parent_manifest_ids=(raw.manifest_id,),
            transformation_policy_digest=_digest(
                {"operation": "hyperliquid-candles-to-canonical-bars-v1"}
            ),
            adjustment_policy=None,
            event_start=bars[0].timestamp,
            event_end=bars[-1].timestamp,
            **common,
        )
        adjusted = self._candidate_manifest(
            dataset_id=f"{prefix}-adjusted",
            layer=ArtifactLayer.ADJUSTED,
            objects=(bar_ref,),
            row_identities=row_ids,
            schema_digest=_digest({"model": "Bar", "schema": 1}),
            parent_manifest_ids=(normalized.manifest_id,),
            transformation_policy_digest=_digest({"policy": _ADJUSTMENT_POLICY}),
            adjustment_policy=_ADJUSTMENT_POLICY,
            event_start=bars[0].timestamp,
            event_end=bars[-1].timestamp,
            **common,
        )
        feature_rows = FabricPublisher._compute_features(
            bars,
            (FabricFeatureSpec(name="log_return", window=2),),
        )
        feature_ref = self.store.objects.put_bytes(
            _FEATURES_MEDIA_TYPE,
            canonical_json_bytes(feature_rows),
        )
        feature = self._candidate_manifest(
            dataset_id=f"{prefix}-feature-log-return-2",
            layer=ArtifactLayer.FEATURE,
            objects=(feature_ref,),
            row_identities=tuple(f"log_return:{row['timestamp']}" for row in feature_rows),
            schema_digest=_digest(
                {"fields": ["name", "timestamp", "value", "window"], "schema": 1}
            ),
            parent_manifest_ids=(adjusted.manifest_id,),
            transformation_policy_digest=_digest(
                {"features": [{"name": "log_return", "window": 2}]}
            ),
            adjustment_policy=_ADJUSTMENT_POLICY,
            event_start=datetime.fromisoformat(feature_rows[0]["timestamp"]),
            event_end=datetime.fromisoformat(feature_rows[-1]["timestamp"]),
            **common,
        )
        publication = HyperliquidPublication(
            raw_id=raw.manifest_id,
            normalized_id=normalized.manifest_id,
            adjusted_id=adjusted.manifest_id,
            feature_id=feature.manifest_id,
            qualifies=envelope.qualifies,
        )
        candidates = (raw, normalized, adjusted, feature)
        self.validate_publication(publication, candidates=candidates)
        self._activate_manifests(candidates)
        return publication

    def raw_envelope(self, publication: HyperliquidPublication) -> RawEnvelope:
        """Open the immutable source envelope for operator evidence."""
        raw = self.store.open(publication.raw_id).manifest
        envelope_ref = next(
            (item for item in raw.objects if item.media_type == _ENVELOPE_MEDIA_TYPE),
            None,
        )
        if envelope_ref is None:
            raise ManifestIntegrityError("Hyperliquid raw envelope is missing")
        return RawEnvelope.model_validate_json(self.store.objects.get_bytes(envelope_ref))

    def validate_publication(
        self,
        publication: HyperliquidPublication,
        *,
        candidates: tuple[
            ArtifactManifest,
            ArtifactManifest,
            ArtifactManifest,
            ArtifactManifest,
        ]
        | None = None,
    ) -> None:
        """Recompute canonical and identity-adjusted descendants from raw bytes."""
        if candidates is None:
            raw = self.store.open(publication.raw_id).manifest
            normalized = self.store.open(publication.normalized_id).manifest
            adjusted = self.store.open(publication.adjusted_id).manifest
            feature = self.store.open(publication.feature_id).manifest
        else:
            raw, normalized, adjusted, feature = candidates
            if tuple(item.manifest_id for item in candidates) != publication.manifest_ids:
                raise ManifestIntegrityError(
                    "Hyperliquid candidate graph disagrees with publication identity"
                )
        envelope_ref = next(
            (item for item in raw.objects if item.media_type == _ENVELOPE_MEDIA_TYPE),
            None,
        )
        if envelope_ref is None or len(raw.objects) != 2:
            raise ManifestIntegrityError("Hyperliquid raw root is invalid")
        envelope = RawEnvelope.model_validate_json(self.store.objects.get_bytes(envelope_ref))
        source_bytes = self.store.objects.get_bytes(envelope.raw_object)
        try:
            source = json.loads(source_bytes)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ManifestIntegrityError("Hyperliquid raw bytes are invalid") from error
        if not isinstance(source, list):
            raise ManifestIntegrityError("Hyperliquid raw candle source is not a list")
        symbol = envelope.provider_symbol
        try:
            bars = self._decode_bars(
                symbol,
                raw.interval or "",
                PublicInfoResponse(
                    payload=source,
                    raw_bytes=source_bytes,
                    received_at=envelope.received_at,
                ),
                start=envelope.request_window_start,
                end=envelope.request_window_end,
            )
        except (HyperliquidProtocolError, ValueError) as error:
            raise ManifestIntegrityError(f"Hyperliquid raw window invalid: {error}") from error
        row_ids = self._bar_ids(bars)
        canonical = CanonicalInstrumentId(value=f"hyperliquid:perp:{symbol}")
        try:
            resolved = self.catalog.resolve(
                "hyperliquid-public",
                symbol,
                effective_at=envelope.session_date,
                known_at=envelope.knowledge_time,
            )
        except ValueError as error:
            raise ManifestIntegrityError(
                "Hyperliquid provider identity is not catalog-resolvable"
            ) from error
        if resolved != canonical:
            raise ManifestIntegrityError("Hyperliquid provider symbol changes identity")
        capability = self._candle_capability(symbol, raw.interval or "")
        if envelope.provenance is ProvenanceClass.REAL:
            expected_provenance = ProvenanceClass.REAL
            expected_provider_id = PublicInfoTransport.descriptor.provider_id
            expected_provider_version = PublicInfoTransport.descriptor.provider_version
            expected_rights = capability.source_rights_id
            expected_entitlement = capability.entitlement
        else:
            expected_provenance = ProvenanceClass.FIXTURE
            expected_provider_id = "fixture-hyperliquid-public"
            expected_provider_version = "scripted-v1"
            expected_rights = "fixture-only"
            expected_entitlement = EntitlementState.NOT_REQUIRED
        expected_run_id = "hyperliquid:" + _digest(
            {
                "symbol": symbol,
                "interval": raw.interval,
                "start": bars[0].timestamp.isoformat(),
                "end": bars[-1].timestamp.isoformat(),
            }
        )
        prefix = f"hyperliquid-{symbol.lower()}-{raw.interval}"
        expected_dataset_ids = (
            f"{prefix}-raw",
            f"{prefix}-normalized",
            f"{prefix}-adjusted",
            f"{prefix}-feature-log-return-2",
        )
        if (
            tuple(item.dataset_id for item in (raw, normalized, adjusted, feature))
            != expected_dataset_ids
        ):
            raise ManifestIntegrityError("Hyperliquid dataset identity is false")
        if (
            raw.layer is not ArtifactLayer.RAW
            or raw.parent_manifest_ids
            or raw.objects != (envelope.raw_object, envelope_ref)
            or envelope.raw_object != _object_ref(_RAW_MEDIA_TYPE, source_bytes)
            or envelope_ref != _object_ref(_ENVELOPE_MEDIA_TYPE, envelope.canonical_bytes())
            or envelope.raw_object.media_type != _RAW_MEDIA_TYPE
            or envelope_ref.media_type != _ENVELOPE_MEDIA_TYPE
            or envelope.canonical_bytes() != self.store.objects.get_bytes(envelope_ref)
            or envelope.endpoint != "https://api.hyperliquid.xyz/info"
            or envelope.provider_id != expected_provider_id
            or envelope.provider_version != expected_provider_version
            or envelope.provenance is not expected_provenance
            or envelope.entitlement is not expected_entitlement
            or envelope.source_rights_id != expected_rights
            or envelope.canonical_instrument != canonical
            or envelope.data_kind is not DataKind.BARS
            or envelope.request_id != expected_run_id
            or envelope.request_window_start != bars[0].timestamp
            or envelope.request_window_end != bars[-1].timestamp
            or envelope.cursor is not None
            or envelope.session_date != bars[0].timestamp.date()
            or envelope.provider_available_at is not None
            or envelope.received_at != envelope.ingested_at
            or envelope.adapter_version != "quantmesh-hyperliquid-public-v1"
            or envelope.schema_version != "hyperliquid-candleSnapshot-v1"
            or envelope.source_event_ids != row_ids
            or envelope.event_start != bars[0].timestamp
            or envelope.event_end != bars[-1].timestamp
            or publication.qualifies != envelope.qualifies
        ):
            raise ManifestIntegrityError("Hyperliquid raw declarations are not source-derived")
        common = {
            "canonical_instrument": canonical,
            "instrument_catalog_id": self.catalog.catalog_id,
            "data_kind": DataKind.BARS,
            "interval": raw.interval,
            "calendar_version": CONTINUOUS_UTC_VERSION,
            "session_policy": SessionPolicy.CONTINUOUS,
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
        for manifest in (raw, normalized, adjusted, feature):
            if any(getattr(manifest, name) != value for name, value in common.items()):
                raise ManifestIntegrityError(
                    "Hyperliquid shared lineage declarations disagree with raw evidence"
                )
        expected_raw = {
            "row_identities": row_ids,
            "schema_digest": _digest({"raw_schema": envelope.schema_version}),
            "transformation_policy_digest": _digest({"operation": "capture-public-json-v1"}),
            "adjustment_policy": None,
            "event_start": bars[0].timestamp,
            "event_end": bars[-1].timestamp,
        }
        if any(getattr(raw, name) != value for name, value in expected_raw.items()):
            raise ManifestIntegrityError("Hyperliquid raw manifest declarations are false")
        canonical_bar_bytes = canonical_json_bytes([bar.model_dump(mode="json") for bar in bars])
        canonical_bar_ref = _object_ref(_BARS_MEDIA_TYPE, canonical_bar_bytes)
        normalized_bars = ArtifactDataset(normalized, self.store.objects).read_bars()
        adjusted_bars = ArtifactDataset(adjusted, self.store.objects).read_bars()
        expected_normalized = {
            "layer": ArtifactLayer.NORMALIZED,
            "parent_manifest_ids": (raw.manifest_id,),
            "row_identities": row_ids,
            "schema_digest": _digest({"model": "Bar", "schema": 1}),
            "transformation_policy_digest": _digest(
                {"operation": "hyperliquid-candles-to-canonical-bars-v1"}
            ),
            "adjustment_policy": None,
            "event_start": bars[0].timestamp,
            "event_end": bars[-1].timestamp,
        }
        if (
            normalized.objects != (canonical_bar_ref,)
            or normalized_bars != bars
            or any(
                getattr(normalized, name) != value for name, value in expected_normalized.items()
            )
        ):
            raise ManifestIntegrityError(
                "Hyperliquid normalized declarations are not source-derived"
            )
        expected_adjusted = {
            "layer": ArtifactLayer.ADJUSTED,
            "objects": (canonical_bar_ref,),
            "parent_manifest_ids": (normalized.manifest_id,),
            "row_identities": row_ids,
            "schema_digest": _digest({"model": "Bar", "schema": 1}),
            "transformation_policy_digest": _digest({"policy": _ADJUSTMENT_POLICY}),
            "adjustment_policy": _ADJUSTMENT_POLICY,
            "event_start": bars[0].timestamp,
            "event_end": bars[-1].timestamp,
        }
        if adjusted_bars != bars or any(
            getattr(adjusted, name) != value for name, value in expected_adjusted.items()
        ):
            raise ManifestIntegrityError(
                "Hyperliquid adjusted declarations are not identity-derived"
            )
        expected_features = FabricPublisher._compute_features(
            bars, (FabricFeatureSpec(name="log_return", window=2),)
        )
        expected_feature_rows = tuple(f"log_return:{row['timestamp']}" for row in expected_features)
        expected_feature = {
            "layer": ArtifactLayer.FEATURE,
            "parent_manifest_ids": (adjusted.manifest_id,),
            "row_identities": expected_feature_rows,
            "schema_digest": _digest(
                {"fields": ["name", "timestamp", "value", "window"], "schema": 1}
            ),
            "transformation_policy_digest": _digest(
                {"features": [{"name": "log_return", "window": 2}]}
            ),
            "adjustment_policy": _ADJUSTMENT_POLICY,
            "event_start": datetime.fromisoformat(expected_features[0]["timestamp"]),
            "event_end": datetime.fromisoformat(expected_features[-1]["timestamp"]),
        }
        canonical_feature_bytes = canonical_json_bytes(expected_features)
        canonical_feature_ref = _object_ref(
            _FEATURES_MEDIA_TYPE,
            canonical_feature_bytes,
        )
        if (
            feature.objects != (canonical_feature_ref,)
            or ArtifactDataset(feature, self.store.objects).read_features() != expected_features
            or any(getattr(feature, name) != value for name, value in expected_feature.items())
        ):
            raise ManifestIntegrityError(
                "Hyperliquid feature declarations are not adjusted-derived"
            )

    def _candidate_manifest(self, **values: Any) -> ArtifactManifest:
        dataset_id = values["dataset_id"]
        current = self.store.current(dataset_id)
        revision = 1 if current is None else current.manifest.compatibility_revision
        candidate = ArtifactManifest.build(compatibility_revision=revision, **values)
        if current is not None and current.manifest.manifest_id == candidate.manifest_id:
            return current.manifest
        if current is not None:
            for historical in self.store.manifests(dataset_id):
                retry = ArtifactManifest.build(
                    compatibility_revision=historical.compatibility_revision,
                    **values,
                )
                if retry.manifest_id == historical.manifest_id:
                    return historical
            candidate = ArtifactManifest.build(
                compatibility_revision=revision + 1,
                **values,
            )
        return candidate

    def _activate_manifests(
        self,
        manifests: tuple[
            ArtifactManifest,
            ArtifactManifest,
            ArtifactManifest,
            ArtifactManifest,
        ],
    ) -> None:
        """Activate a fully validated graph; Task 9 owns cross-pointer crash recovery."""
        for manifest in manifests:
            path = self.store.manifest_path(manifest.dataset_id, manifest.manifest_id)
            if path.exists():
                existing = self.store.open(manifest.manifest_id).manifest
                if existing != manifest:
                    raise ManifestIntegrityError(
                        "existing Hyperliquid manifest disagrees with candidate"
                    )
                continue
            current = self.store.current(manifest.dataset_id)
            self.store.publish(
                manifest,
                expected_current=(None if current is None else current.manifest.manifest_id),
            )

    def _source_admission(
        self,
        symbol: str,
        interval: str,
    ) -> tuple[ProvenanceClass, str, str, str, EntitlementState]:
        descriptor = PublicInfoTransport.descriptor
        capability = self._candle_capability(symbol, interval)
        if (
            type(self.transport) is not PublicInfoTransport
            or not self.transport._is_direct_network_source
        ):
            return (
                ProvenanceClass.FIXTURE,
                "fixture-hyperliquid-public",
                "scripted-v1",
                "fixture-only",
                EntitlementState.NOT_REQUIRED,
            )
        if not _clean_git_commit_matches(self.code_commit):
            raise HyperliquidProtocolError(
                "direct public collection requires a clean verified code identity"
            )
        if capability.entitlement not in (
            EntitlementState.AVAILABLE,
            EntitlementState.NOT_REQUIRED,
        ):
            raise HyperliquidProtocolError("public candle capability is not available")
        return (
            ProvenanceClass.REAL,
            descriptor.provider_id,
            descriptor.provider_version,
            capability.source_rights_id,
            capability.entitlement,
        )

    @staticmethod
    def _candle_capability(symbol: str, interval: str) -> ProviderCapability:
        descriptor = PublicInfoTransport.descriptor
        request = ProviderRequest(
            provider_id=descriptor.provider_id,
            venue=Venue.HYPERLIQUID,
            access=ProviderAccess.PUBLIC_LIVE,
            data_kind=DataKind.BARS,
            symbol=symbol,
            interval=interval,
        )
        matches = [item for item in descriptor.capabilities if item.supports(request)]
        if len(matches) != 1:
            raise HyperliquidProtocolError(
                "public transport has no exact read-only candle capability"
            )
        return matches[0]

    @staticmethod
    def _bar_ids(bars: list[Bar]) -> tuple[str, ...]:
        return tuple(
            f"{bar.instrument.symbol}:{bar.timestamp.astimezone(UTC).isoformat()}" for bar in bars
        )

    @staticmethod
    def _adapter_rows(rows: list[dict], interval: str) -> list[dict]:
        """Normalize only REST's inclusive close millisecond for the strict adapter."""
        step_ms = int(interval_to_timedelta(interval).total_seconds() * 1_000)
        normalized: list[dict] = []
        for row in rows:
            candidate = dict(row)
            open_time, close_time = candidate.get("t"), candidate.get("T")
            if not isinstance(open_time, bool) and not isinstance(close_time, bool):
                try:
                    if int(close_time) - int(open_time) == step_ms - 1:
                        candidate["T"] = int(open_time) + step_ms
                except (TypeError, ValueError):
                    pass
            normalized.append(candidate)
        return normalized
