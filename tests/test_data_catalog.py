from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from quantmesh.data.artifacts import ArtifactLayer, ManifestIntegrityError, ManifestStore
from quantmesh.data.calendars import CONTINUOUS_UTC_VERSION, SessionPolicy
from quantmesh.data.capabilities import DataKind, EntitlementState, ProviderAccess
from quantmesh.data.catalog import (
    CatalogCheckpoint,
    CatalogEntry,
    CatalogQualificationError,
    CatalogQuality,
    TrustedDataCatalog,
)
from quantmesh.data.overlap_resolutions import ResolutionUsePolicy
from quantmesh.data.quality import QualityStatus
from tests.test_artifact_manifests import _manifest
from tests.test_overlap_resolutions import _resolution as _overlap_resolution

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
DIGEST = "1" * 64


def _quality(status: QualityStatus = QualityStatus.PASS) -> CatalogQuality:
    return CatalogQuality(
        report_id="2" * 64,
        evaluation_id="3" * 64,
        policy_id="4" * 64,
        status=status,
        original_status=status,
        issue_codes=() if status is QualityStatus.PASS else ("unexplained-gap",),
        qualification="clean" if status is QualityStatus.PASS else "failed",
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


def test_resolved_overlap_is_trusted_only_for_bounded_ohlcv_use(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed = _quality(QualityStatus.FAIL)
    resolved = CatalogQuality(
        **failed.model_dump(
            exclude={
                "status",
                "original_status",
                "issue_codes",
                "qualification",
                "resolution_id",
                "use_policy",
            }
        ),
        status=QualityStatus.FAIL,
        original_status=QualityStatus.FAIL,
        issue_codes=("historical-live-overlap",),
        resolution_id="9" * 64,
        qualification="qualified-with-resolution",
        use_policy=ResolutionUsePolicy.OHLCV_DERIVATIVES_ONLY,
    )
    entry = _entry(quality=resolved)
    catalog = TrustedDataCatalog(tmp_path)
    monkeypatch.setattr(
        catalog,
        "lineage",
        lambda manifest_id: SimpleNamespace(entry=entry, ancestors=()),
    )

    assert resolved.original_status is QualityStatus.FAIL
    assert resolved.qualification == "qualified-with-resolution"
    assert resolved.resolution_id == "9" * 64
    assert entry.trusted_for_research is True
    assert catalog.require_research(entry.manifest_id, use="ohlcv") == entry
    for use in ("turnover", "liquidity", "cost", "capacity", "slippage"):
        with pytest.raises(CatalogQualificationError, match="use|qualified"):
            catalog.require_research(entry.manifest_id, use=use)

    descendant = _entry(quality=_quality())
    monkeypatch.setattr(
        catalog,
        "lineage",
        lambda manifest_id: SimpleNamespace(entry=descendant, ancestors=(entry,)),
    )
    assert catalog.require_research(descendant.manifest_id, use="ohlcv") == descendant
    with pytest.raises(CatalogQualificationError, match="cost"):
        catalog.require_research(descendant.manifest_id, use="cost")


def test_passing_quality_inheriting_resolution_remains_use_bounded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inherited = CatalogQuality(
        **_quality().model_dump(exclude={"qualification", "resolution_id", "use_policy"}),
        qualification="qualified-with-resolution",
        resolution_id="9" * 64,
        use_policy=ResolutionUsePolicy.OHLCV_DERIVATIVES_ONLY,
    )
    entry = _entry(quality=inherited)
    catalog = TrustedDataCatalog(tmp_path)
    monkeypatch.setattr(
        catalog,
        "lineage",
        lambda manifest_id: SimpleNamespace(entry=entry, ancestors=()),
    )

    assert inherited.original_status is QualityStatus.PASS
    assert catalog.require_research(entry.manifest_id, use="ohlcv") == entry
    for use in ("turnover", "liquidity", "cost", "capacity", "slippage"):
        with pytest.raises(CatalogQualificationError, match=use):
            catalog.require_research(entry.manifest_id, use=use)


def test_nonterminal_quality_cannot_inherit_resolution_qualification() -> None:
    values = _quality().model_dump(
        exclude={
            "status",
            "original_status",
            "issue_codes",
            "qualification",
            "resolution_id",
            "use_policy",
        }
    )

    with pytest.raises(ValidationError, match="resolved catalog quality"):
        CatalogQuality(
            **values,
            status=QualityStatus.NOT_DUE,
            original_status=QualityStatus.NOT_DUE,
            issue_codes=("within-grace-period",),
            qualification="qualified-with-resolution",
            resolution_id="9" * 64,
            use_policy=ResolutionUsePolicy.OHLCV_DERIVATIVES_ONLY,
        )


def test_catalog_projects_checkpoint_bound_exact_overlap_resolution(tmp_path: Path) -> None:
    resolutions, resolution, context = _overlap_resolution(tmp_path)
    resolutions.record(resolution, admitted_manifest_ids=context[2])
    catalog = TrustedDataCatalog(tmp_path)

    entry = catalog.lineage(resolution.candidate_manifest_id).entry

    assert entry.quality is not None
    assert entry.quality.original_status is QualityStatus.FAIL
    assert entry.quality.qualification == "qualified-with-resolution"
    assert entry.quality.resolution_id == resolution.resolution_id
    assert entry.quality.use_policy is ResolutionUsePolicy.OHLCV_DERIVATIVES_ONLY
    assert entry.trusted_for_research is True
    assert catalog.require_research(entry.manifest_id, use="ohlcv") == entry
    with pytest.raises(CatalogQualificationError, match="turnover"):
        catalog.require_research(entry.manifest_id, use="turnover")


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
    control_database = tmp_path / ".trusted-data-v2" / "control" / "collection-checkpoints.duckdb"
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
