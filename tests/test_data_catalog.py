from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from quantmesh.data.artifacts import ArtifactLayer, ManifestIntegrityError, ManifestStore
from quantmesh.data.calendars import CONTINUOUS_UTC_VERSION, SessionPolicy
from quantmesh.data.capabilities import DataKind, EntitlementState, ProviderAccess
from quantmesh.data.catalog import (
    CatalogCheckpoint,
    CatalogEntry,
    CatalogQuality,
    TrustedDataCatalog,
)
from quantmesh.data.quality import QualityStatus
from tests.test_artifact_manifests import _manifest

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
DIGEST = "1" * 64


def _quality(status: QualityStatus = QualityStatus.PASS) -> CatalogQuality:
    return CatalogQuality(
        report_id="2" * 64,
        evaluation_id="3" * 64,
        policy_id="4" * 64,
        status=status,
        issue_codes=() if status is QualityStatus.PASS else ("unexplained-gap",),
        evaluated_at=NOW,
        expected_count=1,
        observed_count=1,
        duplicate_count=0,
        gap_count=0 if status is QualityStatus.PASS else 1,
        hash_mismatch_count=0,
        schema_mismatch_count=0,
        order_violation_count=0,
        overlap_conflict_count=0,
        synthetic_row_count=0,
        freshness_seconds=60,
        latency_seconds=1,
        pagination_terminal=True,
        source_rights_known=True,
    )


def _entry(*, quality: CatalogQuality | None = None) -> CatalogEntry:
    return CatalogEntry(
        provider_id="hyperliquid-public",
        provider_access=ProviderAccess.PUBLIC_LIVE,
        dataset_id="btc-adjusted",
        canonical_instrument="hyperliquid:perp:BTC",
        layer=ArtifactLayer.ADJUSTED,
        data_kind=DataKind.BARS,
        interval="1m",
        calendar_version=CONTINUOUS_UTC_VERSION,
        session_policy=SessionPolicy.CONTINUOUS,
        adjustment_policy="identity-no-corporate-actions-v1",
        manifest_id=DIGEST,
        current_manifest_id=DIGEST,
        compatibility_revision=1,
        parent_manifest_ids=("5" * 64,),
        object_digests=("8" * 64,),
        row_count=1,
        event_start=NOW,
        event_end=NOW,
        knowledge_start=NOW,
        knowledge_end=NOW,
        source_rights_id="hyperliquid-public-market-data",
        entitlement=EntitlementState.NOT_REQUIRED,
        quality=quality,
        latest_checkpoint=CatalogCheckpoint(
            job_id="6" * 64,
            generation=1,
            run_id="7" * 64,
            attempt=1,
            provider_cursor="terminal",
            last_complete_source_event="BTC:2026-08-14T12:00:00+00:00",
            updated_at=NOW,
            quality_report_id="2" * 64,
        ),
    )


def test_catalog_entry_is_trusted_only_with_exact_passing_quality() -> None:
    passing = _entry(quality=_quality())
    assert passing.trusted_for_research is True

    failed = _entry(quality=_quality(QualityStatus.FAIL))
    assert failed.trusted_for_research is False

    with pytest.raises(ValidationError, match="quality report"):
        _entry(quality=None)


def test_empty_catalog_has_no_fabricated_entries(tmp_path: Path) -> None:
    catalog = TrustedDataCatalog(tmp_path)
    assert catalog.entries() == ()
    assert list(tmp_path.iterdir()) == []


def test_manifest_lookup_rejects_unknown_identity(tmp_path: Path) -> None:
    catalog = TrustedDataCatalog(tmp_path)
    with pytest.raises(ValueError, match="not cataloged"):
        catalog.lineage(DIGEST)


def test_legacy_v2_lineage_query_remains_read_only(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    manifest = _manifest(store, close=100.0, revision=1)
    store.publish(manifest, expected_current=None)
    control_database = (
        tmp_path
        / ".trusted-data-v2"
        / "control"
        / "collection-checkpoints.duckdb"
    )
    assert not control_database.exists()

    lineage = TrustedDataCatalog(tmp_path).lineage(manifest.manifest_id)

    assert lineage.entry.current_manifest_id == manifest.manifest_id
    assert lineage.entry.latest_checkpoint is None
    assert lineage.entry.trusted_for_research is False
    assert not control_database.exists()


def test_catalog_propagates_tampered_target_as_integrity_failure(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    manifest = _manifest(store, close=100.0, revision=1)
    store.publish(manifest, expected_current=None)
    store.manifest_path(manifest.dataset_id, manifest.manifest_id).write_text(
        "{}",
        encoding="utf-8",
    )

    with pytest.raises(ManifestIntegrityError, match="invalid"):
        TrustedDataCatalog(tmp_path).lineage(manifest.manifest_id)


def test_historical_lineage_distinguishes_exact_manifest_from_dataset_head(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    second = _manifest(store, close=101.0, revision=2)
    store.publish(second, expected_current=first.manifest_id)

    entry = TrustedDataCatalog(tmp_path).lineage(first.manifest_id).entry

    assert entry.manifest_id == first.manifest_id
    assert entry.current_manifest_id == second.manifest_id
    assert entry.is_current is False
