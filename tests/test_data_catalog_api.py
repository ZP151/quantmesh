from datetime import UTC, datetime

from fastapi.testclient import TestClient

from quantmesh.api.workstation import create_workstation_app
from quantmesh.data.artifacts import ArtifactLayer, ManifestIntegrityError
from quantmesh.data.calendars import CONTINUOUS_UTC_VERSION, SessionPolicy
from quantmesh.data.capabilities import DataKind, EntitlementState, ProviderAccess
from quantmesh.data.catalog import (
    CatalogCheckpoint,
    CatalogEntry,
    CatalogLineage,
    CatalogNotFoundError,
    CatalogQuality,
)
from quantmesh.data.quality import QualityStatus
from quantmesh.execution.accounting import PaperAccount

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
MANIFEST_ID = "1" * 64


def _entry() -> CatalogEntry:
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
        manifest_id=MANIFEST_ID,
        current_manifest_id=MANIFEST_ID,
        compatibility_revision=1,
        parent_manifest_ids=("2" * 64,),
        object_digests=("8" * 64,),
        row_count=1,
        event_start=NOW,
        event_end=NOW,
        knowledge_start=NOW,
        knowledge_end=NOW,
        source_rights_id="hyperliquid-public-market-data",
        entitlement=EntitlementState.NOT_REQUIRED,
        quality=CatalogQuality(
            report_id="3" * 64,
            evaluation_id="4" * 64,
            policy_id="5" * 64,
            status=QualityStatus.PASS,
            issue_codes=(),
            evaluated_at=NOW,
            expected_count=1,
            observed_count=1,
            duplicate_count=0,
            gap_count=0,
            hash_mismatch_count=0,
            schema_mismatch_count=0,
            order_violation_count=0,
            overlap_conflict_count=0,
            synthetic_row_count=0,
            freshness_seconds=60,
            latency_seconds=1,
            pagination_terminal=True,
            source_rights_known=True,
        ),
        latest_checkpoint=CatalogCheckpoint(
            job_id="6" * 64,
            generation=1,
            run_id="7" * 64,
            attempt=1,
            provider_cursor="terminal",
            last_complete_source_event="BTC:2026-08-14T12:00:00+00:00",
            updated_at=NOW,
            quality_report_id="3" * 64,
        ),
    )


class _Catalog:
    def entries(self) -> tuple[CatalogEntry, ...]:
        return (_entry(),)

    def lineage(self, manifest_id: str) -> CatalogLineage:
        if manifest_id != MANIFEST_ID:
            raise CatalogNotFoundError(f"manifest {manifest_id} is not cataloged")
        return CatalogLineage(entry=_entry(), ancestors=())


class _CorruptCatalog(_Catalog):
    def lineage(self, manifest_id: str) -> CatalogLineage:
        raise ManifestIntegrityError("manifest body is invalid")


def _client(catalog: object | None) -> TestClient:
    return TestClient(
        create_workstation_app(
            account=PaperAccount(cash=100_000.0),
            data_catalog=catalog,
            host="127.0.0.1",
        )
    )


def test_catalog_api_lists_entries_and_resolves_exact_lineage() -> None:
    with _client(_Catalog()) as client:
        listing = client.get("/api/data/catalog")
        detail = client.get(f"/api/data/catalog/{MANIFEST_ID}")

    assert listing.status_code == 200
    assert listing.json()[0]["current_manifest_id"] == MANIFEST_ID
    assert listing.json()[0]["trusted_for_research"] is True
    assert detail.status_code == 200
    assert detail.json()["entry"]["quality"]["evaluation_id"] == "4" * 64


def test_catalog_api_is_typed_when_unbound_or_unknown() -> None:
    with _client(None) as client:
        assert client.get("/api/data/catalog").status_code == 404

    with _client(_Catalog()) as client:
        response = client.get(f"/api/data/catalog/{'9' * 64}")
    assert response.status_code == 404
    assert response.json()["detail"] == f"manifest {'9' * 64} is not cataloged"


def test_catalog_api_does_not_mask_integrity_failure_as_not_found() -> None:
    client = TestClient(
        create_workstation_app(
            account=PaperAccount(cash=100_000.0),
            data_catalog=_CorruptCatalog(),
            host="127.0.0.1",
        ),
        raise_server_exceptions=False,
    )
    with client:
        response = client.get(f"/api/data/catalog/{MANIFEST_ID}")

    assert response.status_code == 500
