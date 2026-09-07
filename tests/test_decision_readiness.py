from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from quantmesh.data.artifacts import ArtifactLayer
from quantmesh.data.calendars import CONTINUOUS_UTC_VERSION, SessionPolicy
from quantmesh.data.capabilities import DataKind, EntitlementState, ProviderAccess
from quantmesh.data.catalog import (
    CatalogCheckpoint,
    CatalogEntry,
    CatalogLineage,
    CatalogQuality,
)
from quantmesh.data.quality import QualityStatus
from quantmesh.instruments.readiness import DecisionReadinessService
from tests.test_decision_packets import NOW, packet

MANIFEST = "a" * 64
EVALUATION = "b" * 64
REPORT = "c" * 64


class ExactCatalog:
    def __init__(self, lineages: dict[str, CatalogLineage]) -> None:
        self._lineages = lineages
        self.requested: list[str] = []

    def entries(self) -> tuple[CatalogEntry, ...]:
        raise AssertionError("readiness must not traverse catalog entries")

    def lineage(self, manifest_id: str) -> CatalogLineage:
        self.requested.append(manifest_id)
        return self._lineages[manifest_id]


def _lineage(
    *,
    manifest_id: str = MANIFEST,
    evaluation_id: str = EVALUATION,
    status: QualityStatus = QualityStatus.PASS,
    rights_known: bool = True,
    evaluated_at: datetime = NOW,
) -> CatalogLineage:
    quality = CatalogQuality(
        report_id=REPORT,
        evaluation_id=evaluation_id,
        policy_id="d" * 64,
        status=status,
        issue_codes=() if status is QualityStatus.PASS else ("unexplained-gap",),
        evaluated_at=evaluated_at,
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
        source_rights_known=rights_known,
    )
    return CatalogLineage(
        entry=CatalogEntry(
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
            manifest_id=manifest_id,
            current_manifest_id=manifest_id,
            compatibility_revision=1,
            parent_manifest_ids=("e" * 64,),
            object_digests=("f" * 64,),
            row_count=1,
            event_start=NOW,
            event_end=NOW,
            knowledge_start=NOW,
            knowledge_end=NOW,
            source_rights_id="hyperliquid-public-market-data",
            entitlement=EntitlementState.NOT_REQUIRED,
            quality=quality,
            latest_checkpoint=CatalogCheckpoint(
                job_id="1" * 64,
                generation=1,
                run_id="2" * 64,
                attempt=1,
                provider_cursor="terminal",
                last_complete_source_event="BTC:2026-09-02T20:00:00+00:00",
                updated_at=evaluated_at,
                quality_report_id=REPORT,
            ),
        ),
        ancestors=(),
    )


def _real_packet(
    *,
    forecast: bool = False,
    history_generated_at: datetime = NOW,
    forecast_generated_at: datetime = NOW,
):
    original = packet()
    evidence = original.evidence.model_copy(
        update={
            "history_manifest_id": MANIFEST,
            "history_quality_evaluation_id": EVALUATION,
            "history_source": "trusted-provider",
            "forecast_artifact_id": "forecast-real" if forecast else None,
            "forecast_dataset_id": "btc-adjusted" if forecast else None,
            "forecast_dataset_revision": 1 if forecast else None,
            "forecast_manifest_id": "f" * 64 if forecast else None,
            "forecast_quality_evaluation_id": "e" * 64 if forecast else None,
            "forecast_synthetic": False if forecast else None,
            "forecast_eligible": True if forecast else None,
            "forecast_model_name": "model" if forecast else None,
            "forecast_model_version": "v1" if forecast else None,
            "forecast_config_digest": "1" * 64 if forecast else None,
            "forecast_history_digest": "2" * 64 if forecast else None,
            "forecast_benchmark_name": "baseline" if forecast else None,
            "forecast_generated_at": forecast_generated_at if forecast else None,
            "history_generated_at": history_generated_at,
        }
    )
    return original.model_copy(update={"evidence": evidence})


def test_exact_trusted_history_returns_ready_with_exact_evidence() -> None:
    real_packet = _real_packet()
    catalog = ExactCatalog({MANIFEST: _lineage()})

    result = DecisionReadinessService(catalog_provider=lambda: catalog).evaluate(
        real_packet,
        checked_at=NOW,
    )

    assert result.status == "ready"
    assert result.history is not None
    assert result.history.manifest_id == real_packet.evidence.history_manifest_id
    assert result.history.evaluation_id == real_packet.evidence.history_quality_evaluation_id
    assert catalog.requested == [real_packet.evidence.history_manifest_id]
    assert result.limiting_evidence_at == NOW


def test_demo_history_returns_demo_without_catalog_call() -> None:
    catalog = ExactCatalog({})

    result = DecisionReadinessService(catalog_provider=lambda: catalog).evaluate(
        packet(), checked_at=NOW
    )

    assert result.status == "demo"
    assert result.reason_code == "demo_evidence"
    assert catalog.requested == []


def test_demo_history_with_real_forecast_requires_exact_forecast_closure() -> None:
    demo_packet = _real_packet(forecast=True).model_copy(
        update={
            "evidence": _real_packet(forecast=True).evidence.model_copy(
                update={"history_source": "demo-synthetic"}
            )
        }
    )
    catalog = ExactCatalog({"f" * 64: _lineage(manifest_id="f" * 64, evaluation_id="e" * 64)})

    result = DecisionReadinessService(catalog_provider=lambda: catalog).evaluate(
        demo_packet, checked_at=NOW
    )

    assert result.status == "demo"
    assert result.forecast is not None
    assert catalog.requested == ["f" * 64]


def test_demo_history_with_unavailable_real_forecast_fails_closed() -> None:
    forecast_packet = _real_packet(
        forecast=True,
        history_generated_at=NOW - timedelta(days=1),
        forecast_generated_at=NOW - timedelta(days=2),
    )
    demo_packet = forecast_packet.model_copy(
        update={
            "evidence": forecast_packet.evidence.model_copy(
                update={"history_source": "demo-synthetic"}
            )
        }
    )
    catalog = ExactCatalog({})

    result = DecisionReadinessService(catalog_provider=lambda: catalog).evaluate(
        demo_packet, checked_at=NOW
    )

    assert result.status == "unavailable"
    assert result.reason_code == "forecast_catalog_unavailable"
    assert result.limiting_evidence_at == NOW - timedelta(days=2)
    assert result.history is None
    assert result.forecast is None
    assert catalog.requested == ["f" * 64]


def test_returned_wrong_manifest_identity_is_sanitized() -> None:
    catalog = ExactCatalog({MANIFEST: _lineage(manifest_id="9" * 64)})

    result = DecisionReadinessService(catalog_provider=lambda: catalog).evaluate(
        _real_packet(), checked_at=NOW
    )

    assert result.status == "unavailable"
    assert result.reason_code == "history_manifest_mismatch"
    assert result.history is None
    assert catalog.requested == [MANIFEST]


def test_failed_exact_closure_keeps_packet_generation_as_limiting_evidence() -> None:
    real_packet = _real_packet().model_copy(
        update={
            "evidence": _real_packet().evidence.model_copy(
                update={"history_generated_at": NOW - timedelta(days=1)}
            )
        }
    )

    result = DecisionReadinessService(catalog_provider=lambda: None).evaluate(
        real_packet, checked_at=NOW
    )

    assert result.status == "unavailable"
    assert result.limiting_evidence_at == NOW - timedelta(days=1)


def test_failed_forecast_closure_keeps_older_forecast_generation_as_limiting_evidence() -> None:
    forecast_generated_at = NOW - timedelta(days=2)
    real_packet = _real_packet(
        forecast=True,
        history_generated_at=NOW - timedelta(days=1),
        forecast_generated_at=forecast_generated_at,
    )
    catalog = ExactCatalog(
        {
            MANIFEST: _lineage(),
            "f" * 64: _lineage(
                manifest_id="f" * 64,
                evaluation_id="e" * 64,
                status=QualityStatus.FAIL,
            ),
        }
    )

    result = DecisionReadinessService(catalog_provider=lambda: catalog).evaluate(
        real_packet, checked_at=NOW
    )

    assert result.status == "blocked"
    assert result.reason_code == "forecast_not_trusted"
    assert result.limiting_evidence_at == forecast_generated_at


@pytest.mark.parametrize(
    ("lineage", "reason_code"),
    [
        (
            _lineage(manifest_id="f" * 64, evaluation_id="9" * 64),
            "forecast_evaluation_mismatch",
        ),
        (
            _lineage(manifest_id="f" * 64, evaluation_id="e" * 64, rights_known=False),
            "forecast_rights_unknown",
        ),
        (
            _lineage(manifest_id="f" * 64, evaluation_id="e" * 64, status=QualityStatus.FAIL),
            "forecast_not_trusted",
        ),
    ],
)
def test_demo_real_forecast_blockers_place_exact_evidence_in_forecast(
    lineage: CatalogLineage, reason_code: str
) -> None:
    forecast_packet = _real_packet(forecast=True)
    demo_packet = forecast_packet.model_copy(
        update={
            "evidence": forecast_packet.evidence.model_copy(
                update={"history_source": "demo-synthetic"}
            )
        }
    )
    catalog = ExactCatalog({"f" * 64: lineage})

    result = DecisionReadinessService(catalog_provider=lambda: catalog).evaluate(
        demo_packet, checked_at=NOW
    )

    assert result.status == "blocked"
    assert result.reason_code == reason_code
    assert result.history is None
    assert result.forecast is not None
    assert result.forecast.manifest_id == "f" * 64


def test_demo_real_forecast_checkpoint_failure_places_exact_evidence_in_forecast() -> None:
    base = _lineage(manifest_id="f" * 64, evaluation_id="e" * 64)
    broken_checkpoint = base.entry.latest_checkpoint.model_copy(
        update={"quality_report_id": "9" * 64}
    )
    broken_lineage = base.model_copy(
        update={"entry": base.entry.model_copy(update={"latest_checkpoint": broken_checkpoint})}
    )
    forecast_packet = _real_packet(forecast=True)
    demo_packet = forecast_packet.model_copy(
        update={
            "evidence": forecast_packet.evidence.model_copy(
                update={"history_source": "demo-synthetic"}
            )
        }
    )

    result = DecisionReadinessService(
        catalog_provider=lambda: ExactCatalog({"f" * 64: broken_lineage})
    ).evaluate(demo_packet, checked_at=NOW)

    assert result.status == "blocked"
    assert result.reason_code == "forecast_checkpoint_mismatch"
    assert result.history is None
    assert result.forecast is not None


@pytest.mark.parametrize("wrong_entry_manifest", ["9" * 64])
def test_demo_real_forecast_identity_failure_has_no_fabricated_evidence(
    wrong_entry_manifest: str,
) -> None:
    forecast_packet = _real_packet(forecast=True)
    demo_packet = forecast_packet.model_copy(
        update={
            "evidence": forecast_packet.evidence.model_copy(
                update={"history_source": "demo-synthetic"}
            )
        }
    )
    catalog = ExactCatalog(
        {
            "f" * 64: _lineage(
                manifest_id=wrong_entry_manifest,
                evaluation_id="e" * 64,
            )
        }
    )

    result = DecisionReadinessService(catalog_provider=lambda: catalog).evaluate(
        demo_packet, checked_at=NOW
    )

    assert result.status == "unavailable"
    assert result.reason_code == "forecast_manifest_mismatch"
    assert result.history is None
    assert result.forecast is None


def test_missing_history_binding_is_blocked() -> None:
    original = packet()
    real_without_binding = original.model_copy(
        update={
            "evidence": original.evidence.model_copy(update={"history_source": "trusted-provider"})
        }
    )

    result = DecisionReadinessService(catalog_provider=lambda: None).evaluate(
        real_without_binding, checked_at=NOW
    )

    assert result.status == "blocked"
    assert result.reason_code == "missing_history_binding"


@pytest.mark.parametrize(
    ("lineage", "reason_code"),
    [
        (_lineage(status=QualityStatus.FAIL), "history_not_trusted"),
        (_lineage(rights_known=False), "history_rights_unknown"),
        (_lineage(evaluation_id="9" * 64), "history_evaluation_mismatch"),
    ],
)
def test_invalid_history_closure_is_blocked_with_packet_identity(
    lineage: CatalogLineage, reason_code: str
) -> None:
    catalog = ExactCatalog({MANIFEST: lineage})

    result = DecisionReadinessService(catalog_provider=lambda: catalog).evaluate(
        _real_packet(), checked_at=NOW
    )

    assert result.status == "blocked"
    assert result.reason_code == reason_code
    assert result.history is not None
    assert result.history.manifest_id == MANIFEST
    assert result.history.evaluation_id == EVALUATION


@pytest.mark.parametrize("catalog_provider", [lambda: None, lambda: ExactCatalog({})])
def test_unavailable_closure_does_not_try_another_manifest(catalog_provider) -> None:
    result = DecisionReadinessService(catalog_provider=catalog_provider).evaluate(
        _real_packet(), checked_at=NOW
    )

    assert result.status == "unavailable"
    assert result.reason_code in {
        "catalog_unavailable",
        "history_manifest_unavailable",
        "history_catalog_unavailable",
    }


def test_optional_forecast_absence_does_not_change_valid_history() -> None:
    catalog = ExactCatalog({MANIFEST: _lineage()})

    result = DecisionReadinessService(catalog_provider=lambda: catalog).evaluate(
        _real_packet(), checked_at=NOW
    )

    assert result.status == "ready"
    assert result.forecast is None


def test_real_forecast_requires_its_own_exact_closure() -> None:
    catalog = ExactCatalog(
        {MANIFEST: _lineage(), "f" * 64: _lineage(manifest_id="f" * 64, evaluation_id="e" * 64)}
    )

    result = DecisionReadinessService(catalog_provider=lambda: catalog).evaluate(
        _real_packet(forecast=True), checked_at=NOW
    )

    assert result.status == "ready"
    assert result.forecast is not None
    assert catalog.requested == [MANIFEST, "f" * 64]


def test_naive_clock_is_rejected() -> None:
    with pytest.raises(ValueError, match="checked_at must be timezone-aware"):
        DecisionReadinessService(catalog_provider=lambda: None).evaluate(
            packet(), checked_at=datetime(2026, 9, 2, 20, 0)
        )
