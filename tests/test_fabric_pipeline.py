import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from quantmesh.data.adjustments import UNADJUSTED_IDENTITY
from quantmesh.data.artifacts import (
    ArtifactLayer,
    ArtifactManifest,
    ManifestIntegrityError,
    ManifestStore,
)
from quantmesh.data.capabilities import DataKind, EntitlementState
from quantmesh.data.envelopes import ProvenanceClass, RawEnvelope
from quantmesh.data.fabric import FabricFeatureSpec, FabricPublisher
from quantmesh.data.instruments import CanonicalInstrumentId
from quantmesh.data.objects import ObjectIntegrityError
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue

T0 = datetime(2026, 8, 12, 13, 30, tzinfo=UTC)
AAPL = Instrument(
    symbol="AAPL",
    venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY,
    currency="USD",
)


def _bars(last_close: float = 102.0) -> list[Bar]:
    closes = (100.0, 101.0, last_close)
    return [
        Bar(
            instrument=AAPL,
            timestamp=T0 + timedelta(days=index),
            interval="1d",
            open=close,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=1_000.0 + index,
        )
        for index, close in enumerate(closes)
    ]


def _envelope(
    store: ManifestStore,
    *,
    known_at: datetime = T0 + timedelta(days=3),
    last_close: float = 102.0,
    fixture_bars: list[Bar] | None = None,
) -> RawEnvelope:
    bars = fixture_bars or _bars(last_close=last_close)
    payload = json.dumps(
        [bar.model_dump(mode="json") for bar in bars],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return RawEnvelope.capture(
        objects=store.objects,
        payload=payload,
        content_type="application/json",
        provider_id="fixture-moomoo",
        endpoint="fixture://aapl-daily",
        request_id=f"request-{known_at.isoformat()}",
        request_window_start=bars[0].timestamp,
        request_window_end=bars[-1].timestamp,
        cursor=None,
        canonical_instrument=CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
        provider_symbol="US.AAPL",
        data_kind=DataKind.BARS,
        source_event_ids=tuple(f"US.AAPL:{bar.timestamp.date().isoformat()}" for bar in bars),
        event_start=bars[0].timestamp,
        event_end=bars[-1].timestamp,
        session_date=date(2026, 8, 12),
        provider_available_at=None,
        received_at=known_at,
        ingested_at=known_at,
        provider_version="fixture-v1",
        adapter_version="fixture-adapter-v1",
        schema_version="fixture-bars-v1",
        source_rights_id="fixture-test-data",
        entitlement=EntitlementState.NOT_REQUIRED,
        provenance=ProvenanceClass.FIXTURE,
    )


def _publisher(store: ManifestStore) -> FabricPublisher:
    return FabricPublisher(store, code_commit="3" * 40)


def test_raw_normalized_adjusted_feature_chain_is_complete(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    fabric = _publisher(store)
    publication = fabric.publish_bars(
        _envelope(store),
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )

    chain = fabric.lineage(publication.feature_id)
    assert [item.layer for item in chain] == [
        ArtifactLayer.RAW,
        ArtifactLayer.NORMALIZED,
        ArtifactLayer.ADJUSTED,
        ArtifactLayer.FEATURE,
    ]
    assert publication.qualifies is False
    features = store.open(publication.feature_id).read_features()
    assert features == [
        {
            "name": "log_return",
            "timestamp": (T0 + timedelta(days=2)).isoformat(),
            "value": pytest.approx(math.log(102.0) - math.log(100.0)),
            "window": 2,
        }
    ]


def test_raw_tampering_fails_before_normalization(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    envelope = _envelope(store)
    store.objects.path_for(envelope.raw_object).write_bytes(b"tampered")

    with pytest.raises(ObjectIntegrityError, match="hash mismatch"):
        _publisher(store).publish_bars(
            envelope,
            _bars(),
            adjustment_policy=UNADJUSTED_IDENTITY,
            feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
        )


def test_identical_publication_is_idempotent(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    fabric = _publisher(store)
    envelope = _envelope(store)
    arguments = {
        "adjustment_policy": UNADJUSTED_IDENTITY,
        "feature_specs": (FabricFeatureSpec(name="log_return", window=2),),
    }

    first = fabric.publish_bars(envelope, _bars(), **arguments)
    second = fabric.publish_bars(envelope, _bars(), **arguments)

    assert second == first
    assert [
        store.open(manifest_id).manifest.compatibility_revision
        for manifest_id in (
            second.raw_id,
            second.normalized_id,
            second.adjusted_id,
            second.feature_id,
        )
    ] == [1, 1, 1, 1]


def test_raw_payload_must_match_normalized_input(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)

    with pytest.raises(ValueError, match="raw payload disagrees"):
        _publisher(store).publish_bars(
            _envelope(store),
            _bars(last_close=103.0),
            adjustment_policy=UNADJUSTED_IDENTITY,
            feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
        )


def test_source_event_ids_must_match_fixture_rows(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    envelope = _envelope(store).model_copy(
        update={"source_event_ids": ("fabricated:1", "fabricated:2", "fabricated:3")}
    )

    with pytest.raises(ValueError, match="source event identities"):
        _publisher(store).publish_bars(
            envelope,
            _bars(),
            adjustment_policy=UNADJUSTED_IDENTITY,
            feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
        )


def test_lineage_rejects_feature_not_derived_from_parent(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    fabric = _publisher(store)
    first = fabric.publish_bars(
        _envelope(store),
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )
    corrected_known = T0 + timedelta(days=4)
    corrected = fabric.publish_bars(
        _envelope(store, known_at=corrected_known, last_close=103.0),
        _bars(last_close=103.0),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )
    stale_feature = store.open(first.feature_id).manifest
    current_feature = store.open(corrected.feature_id).manifest
    values = current_feature.model_dump(exclude={"manifest_id", "compatibility_revision"})
    values.update(dataset_id="forged-aapl-feature", objects=stale_feature.objects)
    forged = ArtifactManifest.build(compatibility_revision=1, **values)
    store.publish(forged, expected_current=None)

    with pytest.raises(ManifestIntegrityError, match="not derived"):
        fabric.lineage(forged.manifest_id)


def test_aapl_daily_bars_must_match_xnys_sessions(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    bars = _bars()
    bars[1] = bars[1].model_copy(update={"timestamp": datetime(2026, 8, 15, 13, 30, tzinfo=UTC)})
    bars[2] = bars[2].model_copy(update={"timestamp": datetime(2026, 8, 17, 13, 30, tzinfo=UTC)})

    with pytest.raises(ValueError, match="XNYS session opens"):
        _publisher(store).publish_bars(
            _envelope(
                store,
                known_at=datetime(2026, 8, 18, 13, 30, tzinfo=UTC),
                fixture_bars=bars,
            ),
            bars,
            adjustment_policy=UNADJUSTED_IDENTITY,
            feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
        )


def test_invalid_instrument_metadata_leaves_no_partial_dataset(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    invalid_instrument = AAPL.model_copy(
        update={"instrument_type": InstrumentType.ETF, "currency": "EUR"}
    )
    bars = [bar.model_copy(update={"instrument": invalid_instrument}) for bar in _bars()]

    with pytest.raises(ValueError, match="AAPL daily contract"):
        _publisher(store).publish_bars(
            _envelope(store, fixture_bars=bars),
            bars,
            adjustment_policy=UNADJUSTED_IDENTITY,
            feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
        )

    assert all(
        store.current(dataset_id) is None
        for dataset_id in (
            "aapl-daily-raw",
            "aapl-daily-normalized",
            "aapl-daily-adjusted",
            "aapl-daily-feature-log-return-2",
        )
    )


def test_non_finite_bars_leave_no_partial_dataset(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    bars = _bars()
    bars[-1] = bars[-1].model_copy(update={"open": math.inf, "high": math.inf, "close": math.inf})

    with pytest.raises(ValueError, match="OHLCV values must be finite"):
        _publisher(store).publish_bars(
            _envelope(store, fixture_bars=bars),
            bars,
            adjustment_policy=UNADJUSTED_IDENTITY,
            feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
        )

    assert all(
        store.current(dataset_id) is None
        for dataset_id in (
            "aapl-daily-raw",
            "aapl-daily-normalized",
            "aapl-daily-adjusted",
            "aapl-daily-feature-log-return-2",
        )
    )


def test_other_fixture_provider_leaves_no_partial_dataset(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    envelope = _envelope(store).model_copy(update={"provider_id": "fixture-other"})

    with pytest.raises(ValueError, match="fixture-moomoo provenance"):
        _publisher(store).publish_bars(
            envelope,
            _bars(),
            adjustment_policy=UNADJUSTED_IDENTITY,
            feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
        )

    assert store.current("aapl-daily-raw") is None


def test_raw_only_lineage_validates_bar_semantics(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    fabric = _publisher(store)
    envelope = _envelope(store)
    publication = fabric.publish_bars(
        envelope,
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )
    nvda = AAPL.model_copy(update={"symbol": "NVDA"})
    nvda_bars = [bar.model_copy(update={"instrument": nvda}) for bar in _bars()]
    raw_payload = json.dumps(
        [bar.model_dump(mode="json") for bar in nvda_bars],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    raw_object = store.objects.put_bytes("application/json", raw_payload)
    forged_envelope = envelope.model_copy(update={"raw_object": raw_object})
    envelope_object = store.objects.put_bytes(
        "application/vnd.quantmesh.raw-envelope+json",
        forged_envelope.canonical_bytes(),
    )
    raw = store.open(publication.raw_id).manifest
    values = raw.model_dump(exclude={"manifest_id", "compatibility_revision"})
    values.update(
        dataset_id="forged-nvda-as-aapl-raw",
        objects=(raw_object, envelope_object),
    )
    forged = ArtifactManifest.build(compatibility_revision=1, **values)
    store.publish(forged, expected_current=None)

    with pytest.raises(ManifestIntegrityError, match="raw bars violate"):
        fabric.lineage(forged.manifest_id)


def test_lineage_provenance_must_be_rooted_in_raw_envelope(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    fabric = _publisher(store)
    publication = fabric.publish_bars(
        _envelope(store),
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )
    raw = store.open(publication.raw_id).manifest
    raw_values = raw.model_dump(exclude={"manifest_id", "compatibility_revision"})
    raw_values.update(
        dataset_id="forged-aapl-raw",
        source_rights_id="forged-real-provider-rights",
        entitlement=EntitlementState.AVAILABLE,
    )
    forged_raw = ArtifactManifest.build(compatibility_revision=1, **raw_values)
    store.publish(forged_raw, expected_current=None)

    normalized = store.open(publication.normalized_id).manifest
    normalized_values = normalized.model_dump(exclude={"manifest_id", "compatibility_revision"})
    normalized_values.update(
        dataset_id="forged-aapl-normalized",
        parent_manifest_ids=(forged_raw.manifest_id,),
        source_rights_id="forged-real-provider-rights",
        entitlement=EntitlementState.AVAILABLE,
    )
    forged_normalized = ArtifactManifest.build(compatibility_revision=1, **normalized_values)
    store.publish(forged_normalized, expected_current=None)

    with pytest.raises(ManifestIntegrityError, match="raw manifest declarations"):
        fabric.lineage(forged_normalized.manifest_id)


def test_lineage_rejects_real_provenance_for_fixture_tracer(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    fabric = _publisher(store)
    envelope = _envelope(store)
    publication = fabric.publish_bars(
        envelope,
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )
    real_envelope = envelope.model_copy(
        update={
            "provider_id": "moomoo-opend",
            "source_rights_id": "real-provider-rights",
            "entitlement": EntitlementState.AVAILABLE,
            "provenance": ProvenanceClass.REAL,
        }
    )
    envelope_object = store.objects.put_bytes(
        "application/vnd.quantmesh.raw-envelope+json",
        real_envelope.canonical_bytes(),
    )
    raw = store.open(publication.raw_id).manifest
    raw_values = raw.model_dump(exclude={"manifest_id", "compatibility_revision"})
    raw_values.update(
        dataset_id="forged-real-aapl-raw",
        objects=(real_envelope.raw_object, envelope_object),
        source_rights_id="real-provider-rights",
        entitlement=EntitlementState.AVAILABLE,
    )
    forged_raw = ArtifactManifest.build(compatibility_revision=1, **raw_values)
    store.publish(forged_raw, expected_current=None)

    with pytest.raises(ManifestIntegrityError, match="nonqualifying fixture"):
        fabric.lineage(forged_raw.manifest_id)

    normalized = store.open(publication.normalized_id).manifest
    normalized_values = normalized.model_dump(exclude={"manifest_id", "compatibility_revision"})
    normalized_values.update(
        dataset_id="forged-real-aapl-normalized",
        parent_manifest_ids=(forged_raw.manifest_id,),
        source_rights_id="real-provider-rights",
        entitlement=EntitlementState.AVAILABLE,
    )
    forged_normalized = ArtifactManifest.build(compatibility_revision=1, **normalized_values)
    store.publish(forged_normalized, expected_current=None)

    with pytest.raises(ManifestIntegrityError, match="nonqualifying fixture"):
        fabric.lineage(forged_normalized.manifest_id)
