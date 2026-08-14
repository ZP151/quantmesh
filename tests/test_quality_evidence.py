from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from quantmesh.data.artifacts import (
    ArtifactLayer,
    ArtifactManifest,
    ManifestStore,
    canonical_json_bytes,
)
from quantmesh.data.calendars import CONTINUOUS_UTC_VERSION, SessionPolicy
from quantmesh.data.capabilities import DataKind, EntitlementState
from quantmesh.data.envelopes import ProvenanceClass, RawEnvelope
from quantmesh.data.instruments import CanonicalInstrumentId, InstrumentCatalog
from quantmesh.data.quality import (
    QualityBinding,
    QualityEvaluation,
    QualityEvaluator,
    QualityEvidenceStore,
    QualityFailure,
    QualityIntegrityError,
    QualityPolicy,
    QualityReport,
    QualityStatus,
)
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue

T0 = datetime(2026, 8, 14, tzinfo=UTC)


def _policy() -> QualityPolicy:
    return QualityPolicy(
        venue=Venue.HYPERLIQUID,
        layer=ArtifactLayer.NORMALIZED,
        data_kind=DataKind.BARS,
        interval="1m",
        calendar_version=CONTINUOUS_UTC_VERSION,
        session_policy=SessionPolicy.CONTINUOUS,
        grace_period_seconds=300,
        minimum_coverage_ratio=1.0,
        max_freshness_seconds=600,
        max_latency_seconds=120,
        require_terminal_pagination=False,
    )


def _subject(
    root: Path,
    *,
    event_time: datetime = T0,
    received_at: datetime = T0,
    revision: int = 1,
) -> ArtifactManifest:
    manifests = ManifestStore(root)
    instrument = CanonicalInstrumentId(value="hyperliquid:perp:BTC")
    envelope = RawEnvelope.capture(
        objects=manifests.objects,
        payload=b"[]",
        content_type="application/json",
        provider_id="hyperliquid-public",
        endpoint="info/candleSnapshot",
        request_id="quality-evidence",
        request_window_start=event_time,
        request_window_end=event_time,
        cursor=None,
        canonical_instrument=instrument,
        provider_symbol="BTC",
        data_kind=DataKind.BARS,
        source_event_ids=(f"BTC:{event_time.isoformat()}",),
        event_start=event_time,
        event_end=event_time,
        session_date=event_time.date(),
        provider_available_at=received_at,
        received_at=received_at,
        ingested_at=received_at,
        provider_version="mainnet-v1",
        adapter_version="quality-evidence-v1",
        schema_version="bars-v1",
        source_rights_id="public-market-data",
        entitlement=EntitlementState.NOT_REQUIRED,
        provenance=ProvenanceClass.REAL,
    )
    envelope_ref = manifests.objects.put_bytes(
        "application/vnd.quantmesh.raw-envelope+json", envelope.canonical_bytes()
    )
    raw = ArtifactManifest.build(
        dataset_id="quality-evidence-raw",
        compatibility_revision=revision,
        layer=ArtifactLayer.RAW,
        canonical_instrument=instrument,
        instrument_catalog_id=InstrumentCatalog.bounded_default().catalog_id,
        data_kind=DataKind.BARS,
        interval="1m",
        calendar_version=CONTINUOUS_UTC_VERSION,
        session_policy=SessionPolicy.CONTINUOUS,
        objects=(envelope_ref,),
        row_identities=(f"BTC:{event_time.isoformat()}",),
        schema_digest="1" * 64,
        adapter_version="quality-evidence-v1",
        parent_manifest_ids=(),
        transformation_policy_digest="2" * 64,
        source_rights_id="public-market-data",
        entitlement=EntitlementState.NOT_REQUIRED,
        event_start=event_time,
        event_end=event_time,
        knowledge_start=received_at,
        knowledge_end=received_at,
        adjustment_policy=None,
        quality_report_id=None,
        created_at=received_at,
        code_commit="3" * 40,
        collection_run_id="quality-evidence-run",
    )
    raw_current = manifests.current(raw.dataset_id)
    manifests.publish(
        raw,
        expected_current=(None if raw_current is None else raw_current.manifest.manifest_id),
    )
    bar = Bar(
        instrument=Instrument(
            symbol="BTC",
            venue=Venue.HYPERLIQUID,
            instrument_type=InstrumentType.PERPETUAL,
            currency="USD",
        ),
        timestamp=event_time,
        interval="1m",
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.0,
        volume=1.0,
    )
    bar_ref = manifests.objects.put_bytes(
        "application/vnd.quantmesh.bars+json",
        canonical_json_bytes([bar.model_dump(mode="json")]),
    )
    normalized = ArtifactManifest.build(
        dataset_id="quality-evidence-subject",
        compatibility_revision=revision,
        layer=ArtifactLayer.NORMALIZED,
        canonical_instrument=instrument,
        instrument_catalog_id=InstrumentCatalog.bounded_default().catalog_id,
        data_kind=DataKind.BARS,
        interval="1m",
        calendar_version=CONTINUOUS_UTC_VERSION,
        session_policy=SessionPolicy.CONTINUOUS,
        objects=(bar_ref,),
        row_identities=(f"BTC:{event_time.isoformat()}",),
        schema_digest="4" * 64,
        adapter_version="quality-evidence-v1",
        parent_manifest_ids=(raw.manifest_id,),
        transformation_policy_digest="5" * 64,
        source_rights_id="public-market-data",
        entitlement=EntitlementState.NOT_REQUIRED,
        event_start=event_time,
        event_end=event_time,
        knowledge_start=received_at,
        knowledge_end=received_at,
        adjustment_policy=None,
        quality_report_id=None,
        created_at=received_at,
        code_commit="3" * 40,
        collection_run_id="quality-evidence-run",
    )
    current = manifests.current(normalized.dataset_id)
    manifests.publish(
        normalized,
        expected_current=None if current is None else current.manifest.manifest_id,
    )
    return normalized


def _evaluation(
    status: QualityStatus,
    *,
    manifest_id: str = "1" * 64,
    amends: str | None = None,
) -> QualityEvaluation:
    return QualityEvaluation.build(
        policy_id=_policy().policy_id,
        manifest_id=manifest_id,
        window_start=T0,
        window_end=T0 + timedelta(minutes=1),
        evaluated_at=T0 + timedelta(minutes=11 if amends is not None else 10),
        status=status,
        expected_count=1,
        reported_expected_count=1,
        observed_count=1 if status is QualityStatus.PASS else 0,
        duplicate_count=0,
        gap_count=0 if status is QualityStatus.PASS else 1,
        hash_mismatch_count=0,
        schema_mismatch_count=0,
        order_violation_count=0,
        overlap_conflict_count=0,
        synthetic_row_count=0,
        coverage_numerator=1 if status is QualityStatus.PASS else 0,
        coverage_denominator=1,
        grace_period_seconds=300,
        freshness_seconds=600 if amends is not None else 540,
        latency_seconds=0,
        pagination_terminal=True,
        source_rights_known=True,
        entitlement=EntitlementState.NOT_REQUIRED,
        unavailable_reason=None,
        issue_codes=(
            () if status is QualityStatus.PASS else ("coverage-below-threshold", "unexplained-gap")
        ),
        amends=amends,
        amendment_reason="corrected quality evidence" if amends is not None else None,
    )


def test_original_failure_remains_after_amended_pass(tmp_path: Path) -> None:
    store = QualityEvidenceStore(tmp_path)
    policy = _policy()
    store.record_policy(policy)
    missing = _subject(
        tmp_path,
        event_time=T0 + timedelta(minutes=1),
        received_at=T0 + timedelta(minutes=2),
    )
    evaluator = QualityEvaluator(ManifestStore(tmp_path))
    failed_observation = evaluator.measure(
        policy,
        missing.manifest_id,
        window_start=T0,
        window_end=T0 + timedelta(minutes=1),
        evaluated_at=T0 + timedelta(minutes=9),
    )
    failed = store.record(
        evaluator.evaluate(
            policy,
            missing.manifest_id,
            window_start=T0,
            window_end=T0 + timedelta(minutes=1),
            observation=failed_observation,
        )
    )
    corrected = _subject(
        tmp_path,
        event_time=T0,
        received_at=T0 + timedelta(minutes=3),
        revision=2,
    )
    passed_observation = evaluator.measure(
        policy,
        corrected.manifest_id,
        window_start=T0,
        window_end=T0 + timedelta(minutes=1),
        evaluated_at=T0 + timedelta(minutes=10),
    )
    passed = store.record(
        evaluator.evaluate(
            policy,
            corrected.manifest_id,
            window_start=T0,
            window_end=T0 + timedelta(minutes=1),
            observation=passed_observation,
            amends=failed.evaluation_id,
            amendment_reason="provider correction added the missing candle",
        )
    )

    assert store.load(failed.evaluation_id).status is QualityStatus.FAIL
    assert store.load(passed.evaluation_id).status is QualityStatus.PASS
    assert passed.amends == failed.evaluation_id


def test_evaluation_identity_covers_exact_counts() -> None:
    failed = _evaluation(QualityStatus.FAIL)
    changed = failed.model_copy(update={"observed_count": 1, "coverage_numerator": 1})

    with pytest.raises(ValueError, match="evaluation_id mismatch"):
        QualityEvaluation.model_validate(changed.model_dump())


@pytest.mark.parametrize(
    ("updates", "message"),
    [
        ({"coverage_numerator": 1438}, "coverage numerator"),
        ({"coverage_denominator": 1439}, "coverage denominator"),
        ({"status": QualityStatus.PASS}, "status and issues"),
    ],
)
def test_evaluation_rejects_semantically_inconsistent_evidence(updates, message) -> None:
    values = _evaluation(QualityStatus.FAIL).model_dump(exclude={"evaluation_id"})
    values.update(updates)

    with pytest.raises(ValueError, match=message):
        QualityEvaluation.build(**values)


def test_store_rejects_self_addressed_fabricated_pass(tmp_path: Path) -> None:
    subject = _subject(tmp_path)
    store = QualityEvidenceStore(tmp_path)
    store.record_policy(_policy())
    values = _evaluation(QualityStatus.PASS, manifest_id=subject.manifest_id).model_dump(
        exclude={"evaluation_id"}
    )
    values["duplicate_count"] = 1
    forged = QualityEvaluation.build(**values)

    with pytest.raises(QualityIntegrityError, match="measurements"):
        store.record(forged)


def test_evidence_tampering_fails_closed(tmp_path: Path) -> None:
    store = QualityEvidenceStore(tmp_path)
    subject = _subject(tmp_path)
    store.record_policy(_policy())
    evaluation = store.record(_evaluation(QualityStatus.PASS, manifest_id=subject.manifest_id))
    path = store.path_for(evaluation.evaluation_id)
    path.write_bytes(path.read_bytes() + b" ")

    with pytest.raises(QualityIntegrityError, match="hash"):
        store.load(evaluation.evaluation_id)


def test_amendment_must_reference_existing_matching_evidence(tmp_path: Path) -> None:
    store = QualityEvidenceStore(tmp_path)
    subject = _subject(tmp_path)
    store.record_policy(_policy())

    with pytest.raises(QualityIntegrityError, match="amendment target"):
        store.record(
            _evaluation(
                QualityStatus.PASS,
                manifest_id=subject.manifest_id,
                amends="f" * 64,
            )
        )


def test_evaluation_requires_its_exact_immutable_policy(tmp_path: Path) -> None:
    store = QualityEvidenceStore(tmp_path)

    with pytest.raises(QualityIntegrityError, match="policy"):
        store.record(_evaluation(QualityStatus.FAIL))


def test_evaluation_rejects_missing_or_unadmitted_manifest(tmp_path: Path) -> None:
    store = QualityEvidenceStore(tmp_path)
    store.record_policy(_policy())

    with pytest.raises(QualityFailure, match="admitted manifest"):
        store.record(_evaluation(QualityStatus.PASS))


def test_candidate_evidence_requires_explicit_graph_admission(tmp_path: Path) -> None:
    committed = _subject(tmp_path)
    manifests = ManifestStore(tmp_path)
    candidate = ArtifactManifest.build(
        **committed.model_dump(exclude={"manifest_id", "dataset_id"}),
        dataset_id="quality-evidence-candidate",
    )
    manifests.stage(candidate)
    store = QualityEvidenceStore(tmp_path)
    store.record_policy(_policy())
    evaluation = _evaluation(QualityStatus.PASS, manifest_id=candidate.manifest_id)

    with pytest.raises(QualityFailure, match="admitted manifest"):
        store.record(evaluation)

    assert (
        store.record(
            evaluation,
            admitted_manifest_ids=frozenset({candidate.manifest_id}),
        )
        == evaluation
    )


def test_report_binds_exact_manifest_to_recorded_evaluation(tmp_path: Path) -> None:
    store = QualityEvidenceStore(tmp_path)
    subject = _subject(tmp_path)
    store.record_policy(_policy())
    evaluation = store.record(_evaluation(QualityStatus.PASS, manifest_id=subject.manifest_id))
    report = QualityReport.build(
        job_id="2" * 64,
        run_id="3" * 64,
        checkpoint_body_digest="4" * 64,
        bindings=(
            QualityBinding(
                manifest_id=evaluation.manifest_id,
                evaluation_id=evaluation.evaluation_id,
            ),
        ),
    )

    recorded = store.record_report(report)

    assert store.load_report(recorded.report_id) == report
