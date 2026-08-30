import hashlib
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
from quantmesh.data.catalog import CatalogQualificationError, TrustedDataCatalog
from quantmesh.data.checkpoints import (
    CheckpointIntegrityError,
    CheckpointStore,
    CollectionCheckpoint,
    GraphAdvance,
)
from quantmesh.data.envelopes import ProvenanceClass, RawEnvelope
from quantmesh.data.instruments import CanonicalInstrumentId, InstrumentCatalog
from quantmesh.data.quality import (
    QualityBaseline,
    QualityBinding,
    QualityEvaluation,
    QualityEvaluationV2,
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
from tests.test_overlap_resolutions import (
    T_CANDIDATE as OVERLAP_T_CANDIDATE,
)
from tests.test_overlap_resolutions import T_EVENT as OVERLAP_T_EVENT
from tests.test_overlap_resolutions import _raw_manifest as _overlap_raw_manifest
from tests.test_overlap_resolutions import _resolution as _overlap_resolution

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


def test_v2_evaluation_identity_records_stable_overlap_baseline() -> None:
    legacy = _evaluation(QualityStatus.PASS)
    baseline = QualityBaseline(
        manifest_id="6" * 64,
        evaluation_id="7" * 64,
        resolution_id="8" * 64,
    )
    evaluation = QualityEvaluationV2.build(
        **legacy.model_dump(exclude={"contract", "evaluation_id"}),
        overlap_baseline_manifest_id=baseline.manifest_id,
        overlap_baseline_evaluation_id=baseline.evaluation_id,
        overlap_resolution_id=baseline.resolution_id,
    )

    assert evaluation.contract == "quality-evaluation-v2"
    assert evaluation.overlap_baseline_manifest_id == baseline.manifest_id
    assert evaluation.overlap_baseline_evaluation_id == baseline.evaluation_id
    assert evaluation.overlap_resolution_id == baseline.resolution_id
    assert (
        QualityEvaluationV2.build(**evaluation.model_dump(exclude={"contract", "evaluation_id"}))
        == evaluation
    )


def test_v1_evaluation_canonical_bytes_remain_unchanged() -> None:
    evaluation = _evaluation(QualityStatus.PASS)

    assert evaluation.contract == "quality-evaluation-v1"
    assert (
        QualityEvaluation.build(
            **evaluation.model_dump(exclude={"contract", "evaluation_id"})
        ).canonical_bytes()
        == evaluation.canonical_bytes()
    )


def test_store_dispatches_and_verifies_v2_without_changing_v1_loader(tmp_path: Path) -> None:
    subject = _subject(tmp_path)
    policy = _policy()
    store = QualityEvidenceStore(tmp_path)
    store.record_policy(policy)
    evaluator = QualityEvaluator(ManifestStore(tmp_path))
    observation = evaluator.measure(
        policy,
        subject.manifest_id,
        window_start=T0,
        window_end=T0 + timedelta(minutes=1),
        evaluated_at=T0 + timedelta(minutes=10),
    )
    evaluation = evaluator.evaluate_v2(
        policy,
        subject.manifest_id,
        window_start=T0,
        window_end=T0 + timedelta(minutes=1),
        observation=observation,
        baseline=None,
    )

    store.record(evaluation)

    assert store.load(evaluation.evaluation_id) == evaluation
    assert isinstance(store.load(evaluation.evaluation_id), QualityEvaluationV2)


def _resolved_v2_pass(tmp_path: Path):
    resolutions, resolution, context = _overlap_resolution(tmp_path)
    resolutions.record(resolution, admitted_manifest_ids=context[2])
    _, revision_6, admitted, failed_6, _, _ = context
    revision_7 = _overlap_raw_manifest(
        tmp_path,
        revision=7,
        known_at=OVERLAP_T_CANDIDATE + timedelta(days=1),
        turnover=180_500_001.0,
    )
    admitted = admitted | {revision_7.manifest_id}
    evidence = QualityEvidenceStore(tmp_path)
    policy = evidence.load_policy(failed_6.policy_id)
    baseline = QualityBaseline(
        manifest_id=revision_6.manifest_id,
        evaluation_id=failed_6.evaluation_id,
        resolution_id=resolution.resolution_id,
    )
    evaluator = QualityEvaluator(ManifestStore(tmp_path))
    observation = evaluator.measure(
        policy,
        revision_7.manifest_id,
        window_start=OVERLAP_T_EVENT - timedelta(minutes=1),
        window_end=OVERLAP_T_EVENT + timedelta(days=1),
        evaluated_at=revision_7.knowledge_end + timedelta(hours=1),
        admitted_manifest_ids=admitted,
        overlap_baseline_manifest_id=baseline.manifest_id,
    )
    passed = evaluator.evaluate_v2(
        policy,
        revision_7.manifest_id,
        window_start=OVERLAP_T_EVENT - timedelta(minutes=1),
        window_end=OVERLAP_T_EVENT + timedelta(days=1),
        observation=observation,
        baseline=baseline,
        admitted_manifest_ids=admitted,
    )
    return resolutions, resolution, revision_7, admitted, evidence, policy, passed


def test_v2_record_rejects_omitted_available_accepted_baseline(tmp_path: Path) -> None:
    _, _, revision_7, admitted, evidence, policy, _ = _resolved_v2_pass(tmp_path)
    evaluator = QualityEvaluator(ManifestStore(tmp_path))
    observation = evaluator.measure(
        policy,
        revision_7.manifest_id,
        window_start=OVERLAP_T_EVENT - timedelta(minutes=1),
        window_end=OVERLAP_T_EVENT + timedelta(days=1),
        evaluated_at=revision_7.knowledge_end + timedelta(hours=1),
        admitted_manifest_ids=admitted,
    )
    forged = evaluator.evaluate_v2(
        policy,
        revision_7.manifest_id,
        window_start=OVERLAP_T_EVENT - timedelta(minutes=1),
        window_end=OVERLAP_T_EVENT + timedelta(days=1),
        observation=observation,
        baseline=None,
        admitted_manifest_ids=admitted,
    )

    with pytest.raises(QualityIntegrityError, match="accepted baseline"):
        evidence.record(forged, admitted_manifest_ids=admitted)


def test_stored_v2_pass_revalidates_inherited_resolution(tmp_path: Path) -> None:
    resolutions, resolution, _, admitted, evidence, _, passed = _resolved_v2_pass(tmp_path)
    evidence.record(passed, admitted_manifest_ids=admitted)
    report = QualityReport.build(
        job_id="8" * 64,
        run_id="9" * 64,
        checkpoint_body_digest="a" * 64,
        bindings=(
            QualityBinding(
                manifest_id=passed.manifest_id,
                evaluation_id=passed.evaluation_id,
            ),
        ),
    )
    evidence.record_report(report, admitted_manifest_ids=admitted)
    resolutions.path_for(resolution.resolution_id).unlink()

    with pytest.raises(QualityIntegrityError, match="resolution"):
        evidence.verify_report_integrity(report.report_id)


def test_passing_revision_propagates_resolution_into_baseline_and_catalog(tmp_path: Path) -> None:
    resolutions, resolution, revision_7, admitted, evidence, policy, passed = _resolved_v2_pass(
        tmp_path
    )
    evidence.record(passed, admitted_manifest_ids=admitted)
    provisional = CollectionCheckpoint(
        job_id="b" * 64,
        generation=1,
        provider_cursor="terminal",
        last_complete_source_event=revision_7.row_identities[-1],
        raw_object_digests=tuple(item.digest for item in revision_7.objects),
        manifest_ids=(revision_7.manifest_id,),
        preflight_id="c" * 64,
        quality_report_id=None,
        run_id="d" * 64,
        attempt=1,
        updated_at=passed.evaluated_at,
    )
    digest = hashlib.sha256(
        canonical_json_bytes(provisional.model_dump(mode="json", exclude={"quality_report_id"}))
    ).hexdigest()
    report = QualityReport.build(
        job_id=provisional.job_id,
        run_id=provisional.run_id,
        checkpoint_body_digest=digest,
        bindings=(
            QualityBinding(
                manifest_id=revision_7.manifest_id,
                evaluation_id=passed.evaluation_id,
            ),
        ),
    )
    evidence.record_report(report, admitted_manifest_ids=admitted)
    checkpoint = provisional.model_copy(update={"quality_report_id": report.report_id})
    revision_6 = ManifestStore(tmp_path).manifests(revision_7.dataset_id)[-1]
    with CheckpointStore(tmp_path) as checkpoints:
        with checkpoints.writer():
            checkpoints.commit(
                previous=None,
                next_checkpoint=checkpoint,
                advances=(
                    GraphAdvance(
                        dataset_id=revision_7.dataset_id,
                        expected_current=revision_6.manifest_id,
                        expected_revision=revision_6.compatibility_revision,
                        expected_knowledge_end=revision_6.knowledge_end,
                        manifest_id=revision_7.manifest_id,
                        revision=revision_7.compatibility_revision,
                        knowledge_start=revision_7.knowledge_start,
                        knowledge_end=revision_7.knowledge_end,
                    ),
                ),
                commit_id="e" * 64,
            )
    revision_8 = _overlap_raw_manifest(
        tmp_path,
        revision=8,
        known_at=OVERLAP_T_CANDIDATE + timedelta(days=2),
        turnover=180_500_001.0,
    )
    admitted = admitted | {revision_8.manifest_id}

    baseline = evidence.accepted_baseline(
        revision_8,
        policy_id=policy.policy_id,
        admitted_manifest_ids=admitted,
    )
    entry = TrustedDataCatalog(tmp_path).lineage(revision_7.manifest_id).entry

    assert baseline == QualityBaseline(
        manifest_id=revision_7.manifest_id,
        evaluation_id=passed.evaluation_id,
        resolution_id=resolution.resolution_id,
    )
    assert entry.quality is not None
    assert entry.quality.original_status is QualityStatus.PASS
    assert entry.quality.qualification == "qualified-with-resolution"
    assert entry.quality.resolution_id == resolution.resolution_id
    with pytest.raises(CatalogQualificationError, match="turnover"):
        TrustedDataCatalog(tmp_path).require_research(revision_7.manifest_id, use="turnover")

    resolutions.path_for(resolution.resolution_id).unlink()
    with pytest.raises((CheckpointIntegrityError, QualityIntegrityError)):
        evidence.accepted_baseline(
            revision_8,
            policy_id=policy.policy_id,
            admitted_manifest_ids=admitted,
        )


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
