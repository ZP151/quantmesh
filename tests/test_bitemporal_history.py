from datetime import datetime, timedelta
from pathlib import Path

import pytest

from quantmesh.data.adjustments import UNADJUSTED_IDENTITY
from quantmesh.data.artifacts import (
    ArtifactManifest,
    ManifestConflictError,
    ManifestStore,
)
from quantmesh.data.fabric import FabricFeatureSpec, FabricPublisher
from tests.test_fabric_pipeline import T0, _bars, _envelope


def test_correction_does_not_leak_before_knowledge_time(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    fabric = FabricPublisher(store, code_commit="3" * 40)
    first_known = T0 + timedelta(days=3)
    corrected_known = T0 + timedelta(days=4)
    original = fabric.publish_bars(
        _envelope(store, known_at=first_known),
        _bars(last_close=102.0),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )
    corrected = fabric.publish_bars(
        _envelope(store, known_at=corrected_known, last_close=103.0),
        _bars(last_close=103.0),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )

    assert fabric.history(original.normalized_id, known_at=first_known)[-1].close == 102.0
    assert fabric.history(corrected.normalized_id, known_at=corrected_known)[-1].close == 103.0
    assert store.open(corrected.normalized_id).read_bars(known_at=first_known)[-1].close == 102.0


def test_history_before_first_knowledge_time_fails_closed(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    fabric = FabricPublisher(store, code_commit="3" * 40)
    known_at = T0 + timedelta(days=3)
    publication = fabric.publish_bars(
        _envelope(store, known_at=known_at),
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )

    with pytest.raises(ValueError, match="no artifact was known"):
        fabric.history(publication.normalized_id, known_at=known_at - timedelta(seconds=1))


def test_history_rejects_naive_knowledge_time(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    fabric = FabricPublisher(store, code_commit="3" * 40)
    publication = fabric.publish_bars(
        _envelope(store),
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )

    with pytest.raises(ValueError, match="known_at must be UTC"):
        fabric.history(publication.normalized_id, known_at=datetime(2026, 8, 15))


def test_changed_revision_cannot_claim_an_earlier_knowledge_time(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    fabric = FabricPublisher(store, code_commit="3" * 40)
    first_known = T0 + timedelta(days=4)
    fabric.publish_bars(
        _envelope(store, known_at=first_known),
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )

    with pytest.raises(ValueError, match="strictly later knowledge time"):
        fabric.publish_bars(
            _envelope(
                store,
                known_at=first_known - timedelta(hours=1),
                last_close=103.0,
            ),
            _bars(last_close=103.0),
            adjustment_policy=UNADJUSTED_IDENTITY,
            feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
        )


def test_manifest_written_before_pointer_is_not_visible_by_knowledge_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ManifestStore(tmp_path)
    fabric = FabricPublisher(store, code_commit="3" * 40)
    first_known = T0 + timedelta(days=3)
    corrected_known = T0 + timedelta(days=4)
    original = fabric.publish_bars(
        _envelope(store, known_at=first_known),
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )
    write_pointer = store._write_pointer

    def fail_raw_revision_pointer(manifest) -> None:
        if manifest.dataset_id == "aapl-daily-raw" and manifest.compatibility_revision == 2:
            raise OSError("simulated crash before current pointer")
        write_pointer(manifest)

    monkeypatch.setattr(store, "_write_pointer", fail_raw_revision_pointer)
    with pytest.raises(OSError, match="simulated crash"):
        fabric.publish_bars(
            _envelope(store, known_at=corrected_known, last_close=103.0),
            _bars(last_close=103.0),
            adjustment_policy=UNADJUSTED_IDENTITY,
            feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
        )

    visible = store.open_known_at(original.raw_id, known_at=corrected_known)
    assert visible.manifest.manifest_id == original.raw_id


def test_historical_retry_after_correction_is_idempotent(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    fabric = FabricPublisher(store, code_commit="3" * 40)
    first_known = T0 + timedelta(days=3)
    corrected_known = T0 + timedelta(days=4)
    first_envelope = _envelope(store, known_at=first_known)
    first = fabric.publish_bars(
        first_envelope,
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )
    corrected = fabric.publish_bars(
        _envelope(store, known_at=corrected_known, last_close=103.0),
        _bars(last_close=103.0),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )

    retry = fabric.publish_bars(
        first_envelope,
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )

    assert retry == first
    assert [
        store.current(dataset_id).manifest.manifest_id
        for dataset_id in (
            "aapl-daily-raw",
            "aapl-daily-normalized",
            "aapl-daily-adjusted",
            "aapl-daily-feature-log-return-2",
        )
    ] == [
        corrected.raw_id,
        corrected.normalized_id,
        corrected.adjusted_id,
        corrected.feature_id,
    ]


def test_revision_is_visible_only_after_knowledge_range_is_complete(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    fabric = FabricPublisher(store, code_commit="3" * 40)
    original = fabric.publish_bars(
        _envelope(store),
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )
    first = store.open(original.normalized_id).manifest
    values = first.model_dump(exclude={"manifest_id", "compatibility_revision"})
    range_start = first.knowledge_end + timedelta(hours=1)
    range_end = range_start + timedelta(hours=1)
    values.update(
        knowledge_start=range_start,
        knowledge_end=range_end,
        created_at=range_end,
        collection_run_id="multi-page-knowledge-range",
    )
    ranged = ArtifactManifest.build(compatibility_revision=2, **values)
    store.publish(ranged, expected_current=original.normalized_id)

    during = store.open_known_at(
        ranged.manifest_id,
        known_at=range_start + timedelta(minutes=30),
    )
    complete = store.open_known_at(ranged.manifest_id, known_at=range_end)
    assert during.manifest.manifest_id == original.normalized_id
    assert complete.manifest.manifest_id == ranged.manifest_id


def test_manifest_store_rejects_retroactive_knowledge_revision(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    fabric = FabricPublisher(store, code_commit="3" * 40)
    original = fabric.publish_bars(
        _envelope(store),
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )
    first = store.open(original.normalized_id).manifest
    values = first.model_dump(exclude={"manifest_id", "compatibility_revision"})
    retroactive = first.knowledge_start - timedelta(seconds=1)
    values.update(
        knowledge_start=retroactive,
        knowledge_end=retroactive,
        collection_run_id="retroactive-direct-publication",
    )
    candidate = ArtifactManifest.build(compatibility_revision=2, **values)

    with pytest.raises(ManifestConflictError, match="knowledge time must advance"):
        store.publish(candidate, expected_current=original.normalized_id)
    assert len(store._read_history("aapl-daily-normalized")) == 1


def test_pending_pointer_recovery_cannot_bypass_knowledge_order(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    fabric = FabricPublisher(store, code_commit="3" * 40)
    original = fabric.publish_bars(
        _envelope(store),
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )
    first = store.open(original.normalized_id).manifest
    values = first.model_dump(exclude={"manifest_id", "compatibility_revision"})
    retroactive = first.knowledge_start - timedelta(seconds=1)
    values.update(
        knowledge_start=retroactive,
        knowledge_end=retroactive,
        collection_run_id="retroactive-pending-publication",
    )
    pending = ArtifactManifest.build(compatibility_revision=2, **values)
    store._append_history(pending)
    store._write_revision_reservation(pending)
    store._write_immutable_manifest(pending)

    with pytest.raises(ManifestConflictError, match="knowledge time must advance"):
        store.point_current(pending.manifest_id, expected_current=original.normalized_id)
    assert store.current("aapl-daily-normalized").manifest.manifest_id == original.normalized_id
