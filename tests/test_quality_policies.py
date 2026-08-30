from datetime import UTC, date, datetime, timedelta

import pytest

from quantmesh.data.adjustments import EquitySplitAction
from quantmesh.data.artifacts import (
    ArtifactLayer,
    ArtifactManifest,
    ManifestStore,
    canonical_json_bytes,
)
from quantmesh.data.calendars import (
    CONTINUOUS_UTC_VERSION,
    XNYS_REGULAR_VERSION,
    CalendarService,
    SessionPolicy,
)
from quantmesh.data.capabilities import DataKind, EntitlementState
from quantmesh.data.envelopes import ProvenanceClass, RawEnvelope
from quantmesh.data.instruments import CanonicalInstrumentId, InstrumentCatalog
from quantmesh.data.quality import (
    QualityBaseline,
    QualityEvaluator,
    QualityEvidenceStore,
    QualityFailure,
    QualityObservation,
    QualityPolicy,
    QualityStatus,
    _post_grace_sla_issues,
)
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from tests.test_overlap_resolutions import (
    T_CANDIDATE as OVERLAP_T_CANDIDATE,
)
from tests.test_overlap_resolutions import (
    T_EVENT as OVERLAP_T_EVENT,
)
from tests.test_overlap_resolutions import (
    _policy as _overlap_policy,
)
from tests.test_overlap_resolutions import (
    _raw_manifest as _overlap_raw_manifest,
)

T0 = datetime(2026, 8, 14, 20, tzinfo=UTC)


def _policy(
    *,
    venue: Venue = Venue.HYPERLIQUID,
    data_kind: DataKind = DataKind.BARS,
    layer: ArtifactLayer = ArtifactLayer.NORMALIZED,
) -> QualityPolicy:
    equity = venue is Venue.MOOMOO
    return QualityPolicy(
        venue=venue,
        layer=layer,
        data_kind=data_kind,
        interval=("1d" if equity else "1m") if data_kind is DataKind.BARS else None,
        calendar_version=XNYS_REGULAR_VERSION if equity else CONTINUOUS_UTC_VERSION,
        session_policy=SessionPolicy.REGULAR if equity else SessionPolicy.CONTINUOUS,
        grace_period_seconds=300,
        minimum_coverage_ratio=1.0,
        max_freshness_seconds=600,
        max_latency_seconds=120,
        require_terminal_pagination=equity,
    )


def _observation(**updates) -> QualityObservation:
    values = {
        "evaluated_at": T0 + timedelta(minutes=10),
        "expected_count": 10,
        "observed_count": 10,
        "duplicate_count": 0,
        "gap_count": 0,
        "hash_mismatch_count": 0,
        "schema_mismatch_count": 0,
        "order_violation_count": 0,
        "overlap_conflict_count": 0,
        "synthetic_row_count": 0,
        "pagination_terminal": True,
        "source_rights_known": True,
        "entitlement": EntitlementState.NOT_REQUIRED,
        "freshness_seconds": 30,
        "latency_seconds": 10,
        "unavailable_reason": None,
    }
    values.update(updates)
    return QualityObservation(**values)


def _manifest(
    store: ManifestStore,
    *,
    rights: str = "public-market-data",
    provider_available_at: datetime | None = T0,
) -> ArtifactManifest:
    timestamps = [T0 - timedelta(minutes=10 - index) for index in range(10)]
    bars = [
        Bar(
            instrument=Instrument(
                symbol="BTC",
                venue=Venue.HYPERLIQUID,
                instrument_type=InstrumentType.PERPETUAL,
                currency="USD",
            ),
            timestamp=timestamp,
            interval="1m",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1.0,
        )
        for timestamp in timestamps
    ]
    row_ids = tuple(f"BTC:{timestamp.isoformat()}" for timestamp in timestamps)
    payload = store.objects.put_bytes(
        "application/vnd.quantmesh.bars+json",
        canonical_json_bytes([bar.model_dump(mode="json") for bar in bars]),
    )
    envelope = RawEnvelope.capture(
        objects=store.objects,
        payload=canonical_json_bytes([bar.model_dump(mode="json") for bar in bars]),
        content_type="application/json",
        provider_id="hyperliquid-public",
        endpoint="info/candleSnapshot",
        request_id="quality-test",
        request_window_start=timestamps[0],
        request_window_end=timestamps[-1],
        cursor=None,
        canonical_instrument=CanonicalInstrumentId(value="hyperliquid:perp:BTC"),
        provider_symbol="BTC",
        data_kind=DataKind.BARS,
        source_event_ids=row_ids,
        event_start=timestamps[0],
        event_end=timestamps[-1],
        session_date=timestamps[0].date(),
        provider_available_at=provider_available_at,
        received_at=T0,
        ingested_at=T0,
        provider_version="mainnet-v1",
        adapter_version="quality-test-v1",
        schema_version="bars-v1",
        source_rights_id=rights,
        entitlement=EntitlementState.NOT_REQUIRED,
        provenance=ProvenanceClass.REAL,
    )
    envelope_object = store.objects.put_bytes(
        "application/vnd.quantmesh.raw-envelope+json", envelope.canonical_bytes()
    )
    raw = ArtifactManifest.build(
        dataset_id="btc-quality-raw",
        compatibility_revision=1,
        layer=ArtifactLayer.RAW,
        canonical_instrument=CanonicalInstrumentId(value="hyperliquid:perp:BTC"),
        instrument_catalog_id=InstrumentCatalog.bounded_default().catalog_id,
        data_kind=DataKind.BARS,
        interval="1m",
        calendar_version=CONTINUOUS_UTC_VERSION,
        session_policy=SessionPolicy.CONTINUOUS,
        objects=(envelope_object,),
        row_identities=row_ids,
        schema_digest="0" * 64,
        adapter_version="quality-test-v1",
        parent_manifest_ids=(),
        transformation_policy_digest="0" * 64,
        source_rights_id=rights,
        entitlement=EntitlementState.NOT_REQUIRED,
        event_start=timestamps[0],
        event_end=timestamps[-1],
        knowledge_start=T0,
        knowledge_end=T0,
        adjustment_policy=None,
        quality_report_id=None,
        created_at=T0,
        code_commit="3" * 40,
        collection_run_id="quality-run",
    )
    store.publish(raw, expected_current=None)
    return ArtifactManifest.build(
        dataset_id="btc-quality-subject",
        compatibility_revision=1,
        layer=ArtifactLayer.NORMALIZED,
        canonical_instrument=CanonicalInstrumentId(value="hyperliquid:perp:BTC"),
        instrument_catalog_id=InstrumentCatalog.bounded_default().catalog_id,
        data_kind=DataKind.BARS,
        interval="1m",
        calendar_version=CONTINUOUS_UTC_VERSION,
        session_policy=SessionPolicy.CONTINUOUS,
        objects=(payload,),
        row_identities=row_ids,
        schema_digest="1" * 64,
        adapter_version="quality-test-v1",
        parent_manifest_ids=(raw.manifest_id,),
        transformation_policy_digest="2" * 64,
        source_rights_id=rights,
        entitlement=EntitlementState.NOT_REQUIRED,
        event_start=timestamps[0],
        event_end=timestamps[-1],
        knowledge_start=T0,
        knowledge_end=T0,
        adjustment_policy=None,
        quality_report_id=None,
        created_at=T0,
        code_commit="3" * 40,
        collection_run_id="quality-run",
    )


def test_policy_identity_changes_with_thresholds() -> None:
    policy = _policy()
    changed = policy.model_copy(update={"max_latency_seconds": 121})

    assert policy.policy_id == _policy().policy_id
    assert policy.policy_id != changed.policy_id


def test_hard_completeness_cannot_be_weakened_by_policy() -> None:
    with pytest.raises(ValueError, match="greater than or equal to 1"):
        QualityPolicy.model_validate(
            {
                **_policy().model_dump(exclude={"policy_id"}),
                "minimum_coverage_ratio": 0.99,
            }
        )


def test_clean_completed_window_passes(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    manifest = _manifest(store)
    store.publish(manifest, expected_current=None)

    evaluator = QualityEvaluator(store)
    observation = evaluator.measure(
        _policy(),
        manifest.manifest_id,
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        evaluated_at=T0 + timedelta(minutes=10),
    )
    result = evaluator.evaluate(
        _policy(),
        manifest.manifest_id,
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        observation=observation,
    )

    assert result.status is QualityStatus.PASS
    assert result.issue_codes == ()
    assert result.expected_count == result.observed_count == 10


def test_bar_latency_starts_at_candle_close_when_provider_time_is_absent(
    tmp_path,
) -> None:
    store = ManifestStore(tmp_path)
    manifest = _manifest(store, provider_available_at=None)
    store.publish(manifest, expected_current=None)

    observation = QualityEvaluator(store).measure(
        _policy(),
        manifest.manifest_id,
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        evaluated_at=T0 + timedelta(minutes=10),
    )

    assert observation.latency_seconds == 0


def test_feature_cardinality_uses_the_declared_two_period_window(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    normalized = _manifest(store)
    store.publish(normalized, expected_current=None)
    adjusted_values = normalized.model_dump(exclude={"manifest_id"})
    adjusted_values.update(
        dataset_id="btc-quality-adjusted",
        layer=ArtifactLayer.ADJUSTED,
        parent_manifest_ids=(normalized.manifest_id,),
        adjustment_policy="identity-no-corporate-actions-v1",
    )
    adjusted = ArtifactManifest.build(**adjusted_values)
    store.stage(adjusted)
    bars = store.open(adjusted.manifest_id).read_bars()
    feature_rows = [
        {
            "name": "log_return",
            "timestamp": bar.timestamp.isoformat(),
            "value": 0.0,
            "window": 2,
        }
        for bar in bars[2:]
    ]
    feature_object = store.objects.put_bytes(
        "application/vnd.quantmesh.features+json",
        canonical_json_bytes(feature_rows),
    )
    feature = ArtifactManifest.build(
        **{
            **adjusted.model_dump(exclude={"manifest_id"}),
            "dataset_id": "btc-quality-features",
            "layer": ArtifactLayer.FEATURE,
            "objects": (feature_object,),
            "row_identities": tuple(f"log_return:{row['timestamp']}" for row in feature_rows),
            "parent_manifest_ids": (adjusted.manifest_id,),
            "event_start": bars[2].timestamp,
            "event_end": bars[-1].timestamp,
        }
    )
    store.stage(feature)
    admitted = frozenset(
        {
            normalized.parent_manifest_ids[0],
            normalized.manifest_id,
            adjusted.manifest_id,
            feature.manifest_id,
        }
    )
    policy = _policy(layer=ArtifactLayer.FEATURE)
    evaluator = QualityEvaluator(store)
    observation = evaluator.measure(
        policy,
        feature.manifest_id,
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        evaluated_at=T0 + timedelta(minutes=10),
        admitted_manifest_ids=admitted,
    )
    result = evaluator.evaluate(
        policy,
        feature.manifest_id,
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        observation=observation,
        admitted_manifest_ids=admitted,
    )

    assert observation.expected_count == observation.observed_count == 8
    assert observation.gap_count == 0
    assert result.status is QualityStatus.PASS


def test_hard_sla_counts_and_thresholds_fail(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    manifest = _manifest(store)
    store.publish(manifest, expected_current=None)

    result = QualityEvaluator(store).evaluate_status(
        _policy(),
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        observation=_observation(
            observed_count=8,
            duplicate_count=1,
            gap_count=1,
            pagination_terminal=False,
            freshness_seconds=601,
        ),
    )

    assert result.status is QualityStatus.FAIL
    assert set(result.issue_codes) >= {
        "coverage-below-threshold",
        "duplicate-source-identity",
        "unexplained-gap",
        "freshness-sla",
    }


def test_post_grace_sla_skips_freshness_and_latency_for_corporate_actions() -> None:
    policy = _policy(data_kind=DataKind.SPLITS)
    observation = _observation(freshness_seconds=10_000_000, latency_seconds=10_000_000)

    issues = _post_grace_sla_issues(policy, observation, expected_count=0)

    assert issues == []


def test_changed_historical_overlap_is_measured_from_row_content(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    original = _manifest(store)
    store.publish(original, expected_current=None)
    bars = store.open(original.manifest_id).read_bars()
    bars[0] = bars[0].model_copy(update={"close": 100.5})
    payload = store.objects.put_bytes(
        "application/vnd.quantmesh.bars+json",
        canonical_json_bytes([bar.model_dump(mode="json") for bar in bars]),
    )
    values = original.model_dump(exclude={"manifest_id"})
    values.update(
        compatibility_revision=2,
        objects=(payload,),
        knowledge_start=T0 + timedelta(seconds=1),
        knowledge_end=T0 + timedelta(seconds=1),
        created_at=T0 + timedelta(seconds=1),
        collection_run_id="quality-correction-run",
    )
    correction = ArtifactManifest.build(**values)
    store.publish(correction, expected_current=original.manifest_id)

    evaluator = QualityEvaluator(store)
    observation = evaluator.measure(
        _policy(),
        correction.manifest_id,
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        evaluated_at=T0 + timedelta(minutes=10),
        admitted_manifest_ids=frozenset({original.manifest_id, correction.manifest_id}),
    )
    result = evaluator.evaluate(
        _policy(),
        correction.manifest_id,
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        observation=observation,
        admitted_manifest_ids=frozenset({original.manifest_id, correction.manifest_id}),
    )

    assert observation.overlap_conflict_count == 1
    assert result.status is QualityStatus.FAIL
    assert "historical-live-overlap" in result.issue_codes


def test_explicit_amendment_can_reconcile_a_provider_correction(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    original = _manifest(store)
    store.publish(original, expected_current=None)
    bars = store.open(original.manifest_id).read_bars()
    bars[0] = bars[0].model_copy(update={"close": 100.5})
    payload = store.objects.put_bytes(
        "application/vnd.quantmesh.bars+json",
        canonical_json_bytes([bar.model_dump(mode="json") for bar in bars]),
    )
    values = original.model_dump(exclude={"manifest_id"})
    values.update(
        compatibility_revision=2,
        objects=(payload,),
        knowledge_start=T0 + timedelta(seconds=1),
        knowledge_end=T0 + timedelta(seconds=1),
        created_at=T0 + timedelta(seconds=1),
        collection_run_id="quality-amendment-run",
    )
    correction = ArtifactManifest.build(**values)
    store.publish(correction, expected_current=original.manifest_id)
    admitted = frozenset({original.manifest_id, correction.manifest_id})
    evaluator = QualityEvaluator(store)
    policy = _policy()
    evidence = QualityEvidenceStore(tmp_path)
    evidence.record_policy(policy)
    first_observation = evaluator.measure(
        policy,
        correction.manifest_id,
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        evaluated_at=T0 + timedelta(minutes=9),
        admitted_manifest_ids=admitted,
    )
    failed = evaluator.evaluate(
        policy,
        correction.manifest_id,
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        observation=first_observation,
        admitted_manifest_ids=admitted,
    )
    evidence.record(failed, admitted_manifest_ids=admitted)
    amended_observation = evaluator.measure(
        policy,
        correction.manifest_id,
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        evaluated_at=T0 + timedelta(minutes=9, seconds=1),
        admitted_manifest_ids=admitted,
    )
    amended = evaluator.evaluate(
        policy,
        correction.manifest_id,
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        observation=amended_observation,
        amends=failed.evaluation_id,
        amendment_reason="Provider correction reviewed against immutable source evidence.",
        admitted_manifest_ids=admitted,
    )
    evidence.record(amended, admitted_manifest_ids=admitted)

    assert amended.overlap_conflict_count == 1
    assert amended.status is QualityStatus.PASS
    assert amended.issue_codes == ()


def test_raw_overlap_uses_row_content_not_whole_batch_digest(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    subject = _manifest(store)
    store.stage(subject)
    original = store.open(subject.parent_manifest_ids[0]).manifest
    envelope_reference = next(
        reference
        for reference in original.objects
        if reference.media_type == "application/vnd.quantmesh.raw-envelope+json"
    )
    envelope = RawEnvelope.model_validate_json(store.objects.get_bytes(envelope_reference))
    bars = store.open(subject.manifest_id).read_bars()
    added = bars[-1].model_copy(update={"timestamp": T0})
    extended = [*bars, added]
    added_identity = f"BTC:{T0.isoformat()}"
    metadata = envelope.model_dump(exclude={"envelope_version", "raw_object"})
    metadata.update(
        source_event_ids=(*envelope.source_event_ids, added_identity),
        event_end=T0,
        request_window_end=T0,
        provider_available_at=T0 + timedelta(minutes=1),
        received_at=T0 + timedelta(minutes=1),
        ingested_at=T0 + timedelta(minutes=1),
    )
    extended_envelope = RawEnvelope.capture(
        objects=store.objects,
        payload=canonical_json_bytes([bar.model_dump(mode="json") for bar in extended]),
        content_type="application/json",
        **metadata,
    )
    extended_envelope_object = store.objects.put_bytes(
        "application/vnd.quantmesh.raw-envelope+json",
        extended_envelope.canonical_bytes(),
    )
    values = original.model_dump(exclude={"manifest_id"})
    values.update(
        compatibility_revision=2,
        objects=(extended_envelope.raw_object, extended_envelope_object),
        row_identities=extended_envelope.source_event_ids,
        event_end=T0,
        knowledge_start=T0 + timedelta(minutes=1),
        knowledge_end=T0 + timedelta(minutes=1),
        created_at=T0 + timedelta(minutes=1),
        collection_run_id="extended-raw-run",
    )
    extended_manifest = ArtifactManifest.build(**values)
    store.stage(extended_manifest)
    admitted = frozenset({original.manifest_id, extended_manifest.manifest_id})

    observation = QualityEvaluator(store).measure(
        _policy(layer=ArtifactLayer.RAW),
        extended_manifest.manifest_id,
        window_start=T0 - timedelta(minutes=10),
        window_end=T0 + timedelta(minutes=1),
        evaluated_at=T0 + timedelta(minutes=10),
        admitted_manifest_ids=admitted,
    )

    assert observation.overlap_conflict_count == 0


def test_normalized_split_overlap_uses_typed_row_fingerprints(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    canonical = CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS")
    action_a = EquitySplitAction(
        action_id="split-a",
        canonical_instrument=canonical,
        announced_at=datetime(2026, 8, 1, tzinfo=UTC),
        effective_at=datetime(2026, 8, 10, 4, tzinfo=UTC),
        ratio=2.0,
    )
    action_b = EquitySplitAction(
        action_id="split-b",
        canonical_instrument=canonical,
        announced_at=datetime(2026, 8, 11, tzinfo=UTC),
        effective_at=datetime(2026, 8, 13, 4, tzinfo=UTC),
        ratio=3.0,
    )

    def manifest_for(
        actions: tuple[EquitySplitAction, ...],
        *,
        revision: int,
        known_at: datetime,
    ) -> ArtifactManifest:
        reference = store.objects.put_bytes(
            "application/vnd.quantmesh.equity-splits+json",
            canonical_json_bytes([action.model_dump(mode="json") for action in actions]),
        )
        return ArtifactManifest.build(
            dataset_id="aapl-quality-splits",
            compatibility_revision=revision,
            layer=ArtifactLayer.NORMALIZED,
            canonical_instrument=canonical,
            instrument_catalog_id=InstrumentCatalog.bounded_default().catalog_id,
            data_kind=DataKind.SPLITS,
            interval=None,
            calendar_version=XNYS_REGULAR_VERSION,
            session_policy=SessionPolicy.REGULAR,
            objects=(reference,),
            row_identities=tuple(action.action_id for action in actions),
            schema_digest="1" * 64,
            adapter_version="quality-test-v1",
            parent_manifest_ids=(),
            transformation_policy_digest="2" * 64,
            source_rights_id="public-market-data",
            entitlement=EntitlementState.NOT_REQUIRED,
            event_start=min(action.effective_at for action in actions),
            event_end=max(action.effective_at for action in actions),
            knowledge_start=known_at,
            knowledge_end=known_at,
            adjustment_policy=None,
            quality_report_id=None,
            created_at=known_at,
            code_commit="3" * 40,
            collection_run_id=f"split-overlap-{revision}",
        )

    first = manifest_for((action_a,), revision=1, known_at=T0)
    second = manifest_for(
        (action_a, action_b),
        revision=2,
        known_at=T0 + timedelta(minutes=1),
    )
    store.stage(first)
    store.stage(second)
    evaluator = QualityEvaluator(store)

    assert (
        evaluator._overlap_conflicts(
            second,
            admitted_manifest_ids=frozenset({first.manifest_id, second.manifest_id}),
        )
        == ()
    )


def test_v2_explicit_baseline_prevents_natural_overlap_healing(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    revision_5 = _overlap_raw_manifest(
        tmp_path,
        revision=5,
        known_at=OVERLAP_T_CANDIDATE - timedelta(days=1),
        turnover=180_500_000.0,
    )
    revision_6 = _overlap_raw_manifest(
        tmp_path,
        revision=6,
        known_at=OVERLAP_T_CANDIDATE,
        turnover=180_500_001.0,
    )
    revision_7 = _overlap_raw_manifest(
        tmp_path,
        revision=7,
        known_at=OVERLAP_T_CANDIDATE + timedelta(days=1),
        turnover=180_500_001.0,
    )
    revision_8 = _overlap_raw_manifest(
        tmp_path,
        revision=8,
        known_at=OVERLAP_T_CANDIDATE + timedelta(days=2),
        turnover=180_500_001.0,
    )
    revision_9 = _overlap_raw_manifest(
        tmp_path,
        revision=9,
        known_at=OVERLAP_T_CANDIDATE + timedelta(days=3),
        turnover=180_500_002.0,
    )
    admitted = frozenset(
        manifest.manifest_id
        for manifest in (revision_5, revision_6, revision_7, revision_8, revision_9)
    )
    evaluator = QualityEvaluator(store)
    policy = _overlap_policy()
    stable_5 = QualityBaseline(
        manifest_id=revision_5.manifest_id,
        evaluation_id="5" * 64,
        resolution_id=None,
    )

    observation_7 = evaluator.measure(
        policy,
        revision_7.manifest_id,
        window_start=OVERLAP_T_EVENT - timedelta(minutes=1),
        window_end=OVERLAP_T_EVENT + timedelta(days=1),
        evaluated_at=revision_7.knowledge_end + timedelta(hours=1),
        admitted_manifest_ids=admitted,
        overlap_baseline_manifest_id=stable_5.manifest_id,
    )
    failed_7 = evaluator.evaluate_v2(
        policy,
        revision_7.manifest_id,
        window_start=OVERLAP_T_EVENT - timedelta(minutes=1),
        window_end=OVERLAP_T_EVENT + timedelta(days=1),
        observation=observation_7,
        baseline=stable_5,
        admitted_manifest_ids=admitted,
    )
    assert failed_7.issue_codes == ("historical-live-overlap",)

    resolved_6 = QualityBaseline(
        manifest_id=revision_6.manifest_id,
        evaluation_id="6" * 64,
        resolution_id="a" * 64,
    )
    observation_8 = evaluator.measure(
        policy,
        revision_8.manifest_id,
        window_start=OVERLAP_T_EVENT - timedelta(minutes=1),
        window_end=OVERLAP_T_EVENT + timedelta(days=1),
        evaluated_at=revision_8.knowledge_end + timedelta(hours=1),
        admitted_manifest_ids=admitted,
        overlap_baseline_manifest_id=resolved_6.manifest_id,
    )
    passed_8 = evaluator.evaluate_v2(
        policy,
        revision_8.manifest_id,
        window_start=OVERLAP_T_EVENT - timedelta(minutes=1),
        window_end=OVERLAP_T_EVENT + timedelta(days=1),
        observation=observation_8,
        baseline=resolved_6,
        admitted_manifest_ids=admitted,
    )
    assert passed_8.status is QualityStatus.PASS
    assert passed_8.overlap_baseline_manifest_id == revision_6.manifest_id
    assert passed_8.overlap_resolution_id == resolved_6.resolution_id

    observation_9 = evaluator.measure(
        policy,
        revision_9.manifest_id,
        window_start=OVERLAP_T_EVENT - timedelta(minutes=1),
        window_end=OVERLAP_T_EVENT + timedelta(days=1),
        evaluated_at=revision_9.knowledge_end + timedelta(hours=1),
        admitted_manifest_ids=admitted,
        overlap_baseline_manifest_id=resolved_6.manifest_id,
    )
    failed_9 = evaluator.evaluate_v2(
        policy,
        revision_9.manifest_id,
        window_start=OVERLAP_T_EVENT - timedelta(minutes=1),
        window_end=OVERLAP_T_EVENT + timedelta(days=1),
        observation=observation_9,
        baseline=resolved_6,
        admitted_manifest_ids=admitted,
    )
    assert failed_9.issue_codes == ("historical-live-overlap",)
    assert failed_9.overlap_conflict_fingerprints != failed_7.overlap_conflict_fingerprints


def test_raw_measurement_reconciles_manifest_rows_with_envelope_events(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    subject = _manifest(store)
    raw = store.open(subject.parent_manifest_ids[0]).manifest
    values = raw.model_dump(exclude={"manifest_id"})
    values.update(
        compatibility_revision=2,
        row_identities=(raw.row_identities[0],),
        knowledge_start=T0 + timedelta(seconds=1),
        knowledge_end=T0 + timedelta(seconds=1),
        created_at=T0 + timedelta(seconds=1),
        collection_run_id="forged-raw-run",
    )
    forged = ArtifactManifest.build(**values)
    store.stage(forged)
    policy = _policy(layer=ArtifactLayer.RAW)

    observation = QualityEvaluator(store).measure(
        policy,
        forged.manifest_id,
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        evaluated_at=T0 + timedelta(minutes=10),
        admitted_manifest_ids=frozenset({forged.manifest_id}),
    )

    assert observation.expected_count == 10
    assert observation.observed_count == 1
    assert observation.gap_count == 9
    assert observation.schema_mismatch_count == 1


def test_malformed_normalized_split_object_cannot_pass(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    subject = _manifest(store)
    malformed_object = store.objects.put_bytes(
        "application/vnd.quantmesh.equity-splits+json",
        canonical_json_bytes({"garbage": True}),
    )
    malformed = ArtifactManifest.build(
        dataset_id="aapl-malformed-splits",
        compatibility_revision=1,
        layer=ArtifactLayer.NORMALIZED,
        canonical_instrument=CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
        instrument_catalog_id=InstrumentCatalog.bounded_default().catalog_id,
        data_kind=DataKind.SPLITS,
        interval=None,
        calendar_version=XNYS_REGULAR_VERSION,
        session_policy=SessionPolicy.REGULAR,
        objects=(malformed_object,),
        row_identities=("split:forged",),
        schema_digest="1" * 64,
        adapter_version="quality-test-v1",
        parent_manifest_ids=(subject.parent_manifest_ids[0],),
        transformation_policy_digest="2" * 64,
        source_rights_id="public-market-data",
        entitlement=EntitlementState.NOT_REQUIRED,
        event_start=T0 - timedelta(minutes=1),
        event_end=T0 - timedelta(minutes=1),
        knowledge_start=T0,
        knowledge_end=T0,
        adjustment_policy=None,
        quality_report_id=None,
        created_at=T0,
        code_commit="3" * 40,
        collection_run_id="malformed-splits-run",
    )
    store.stage(malformed)
    policy = _policy(venue=Venue.MOOMOO, data_kind=DataKind.SPLITS)
    evaluator = QualityEvaluator(store)
    observation = evaluator.measure(
        policy,
        malformed.manifest_id,
        window_start=T0 - timedelta(hours=1),
        window_end=T0,
        evaluated_at=T0 + timedelta(minutes=10),
        admitted_manifest_ids=frozenset({malformed.manifest_id}),
    )
    result = evaluator.evaluate_status(
        policy,
        window_start=T0 - timedelta(hours=1),
        window_end=T0,
        observation=observation,
    )

    assert observation.schema_mismatch_count == 1
    assert result.status is QualityStatus.FAIL
    assert "schema-mismatch" in result.issue_codes


def test_grace_and_xnys_holiday_are_not_due(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    manifest = _manifest(store)
    store.publish(manifest, expected_current=None)
    grace = QualityEvaluator(store).evaluate_status(
        _policy(),
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        observation=_observation(evaluated_at=T0 + timedelta(minutes=1), observed_count=0),
    )
    holiday_policy = _policy(venue=Venue.MOOMOO)
    holiday = QualityEvaluator(store).evaluate_status(
        holiday_policy,
        window_start=datetime(2026, 12, 25, tzinfo=UTC),
        window_end=datetime(2026, 12, 26, tzinfo=UTC),
        observation=_observation(expected_count=0, observed_count=0),
    )

    assert grace.status is QualityStatus.NOT_DUE
    assert holiday.status is QualityStatus.NOT_DUE
    assert not CalendarService().is_due("XNYS", date(2026, 12, 25), policy=SessionPolicy.REGULAR)


def test_xnys_premarket_window_is_not_due(tmp_path) -> None:
    result = QualityEvaluator(ManifestStore(tmp_path)).evaluate_status(
        _policy(venue=Venue.MOOMOO),
        window_start=datetime(2026, 8, 14, 11, tzinfo=UTC),
        window_end=datetime(2026, 8, 14, 12, tzinfo=UTC),
        observation=_observation(expected_count=0, observed_count=0),
    )

    assert result.status is QualityStatus.NOT_DUE
    assert result.issue_codes == ("calendar-not-due",)


def test_xnys_daily_bar_cannot_pass_before_session_close(tmp_path) -> None:
    window_start = datetime(2026, 8, 14, 4, tzinfo=UTC)
    result = QualityEvaluator(ManifestStore(tmp_path)).evaluate_status(
        _policy(venue=Venue.MOOMOO),
        window_start=window_start,
        window_end=window_start + timedelta(hours=1),
        observation=_observation(
            evaluated_at=window_start + timedelta(hours=2),
            expected_count=0,
            observed_count=1,
        ),
    )

    assert result.status is QualityStatus.FAIL
    assert "unexpected-out-of-session-data" in result.issue_codes


def test_out_of_session_rows_fail_instead_of_hiding_behind_not_due(tmp_path) -> None:
    result = QualityEvaluator(ManifestStore(tmp_path)).evaluate_status(
        _policy(venue=Venue.MOOMOO),
        window_start=datetime(2026, 12, 25, tzinfo=UTC),
        window_end=datetime(2026, 12, 26, tzinfo=UTC),
        observation=_observation(expected_count=0, observed_count=1),
    )

    assert result.status is QualityStatus.FAIL
    assert "unexpected-out-of-session-data" in result.issue_codes


def test_grace_never_masks_hard_integrity_failures(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    manifest = _manifest(store)
    store.publish(manifest, expected_current=None)

    result = QualityEvaluator(store).evaluate_status(
        _policy(),
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        observation=_observation(
            evaluated_at=T0 + timedelta(minutes=1),
            observed_count=0,
            hash_mismatch_count=1,
        ),
    )

    assert result.status is QualityStatus.FAIL
    assert "object-hash-mismatch" in result.issue_codes


def test_complete_claim_cannot_pass_before_grace_deadline(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    manifest = _manifest(store)
    store.publish(manifest, expected_current=None)

    result = QualityEvaluator(store).evaluate_status(
        _policy(),
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        observation=_observation(evaluated_at=T0 + timedelta(minutes=1)),
    )

    assert result.status is QualityStatus.NOT_DUE
    assert result.issue_codes == ("within-grace-period",)


def test_unknown_entitlement_is_unavailable(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    manifest = _manifest(store)
    store.publish(manifest, expected_current=None)

    result = QualityEvaluator(store).evaluate_status(
        _policy(),
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        observation=_observation(entitlement=EntitlementState.UNKNOWN),
    )

    assert result.status is QualityStatus.UNAVAILABLE
    assert "unknown-entitlement" in result.issue_codes


def test_unavailable_state_does_not_mask_hard_integrity_failure(tmp_path) -> None:
    result = QualityEvaluator(ManifestStore(tmp_path)).evaluate_status(
        _policy(),
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        observation=_observation(
            entitlement=EntitlementState.UNKNOWN,
            schema_mismatch_count=1,
        ),
    )

    assert result.status is QualityStatus.FAIL
    assert "schema-mismatch" in result.issue_codes


def test_event_stream_has_no_fabricated_bar_denominator(tmp_path) -> None:
    result = QualityEvaluator(ManifestStore(tmp_path)).evaluate_status(
        _policy(data_kind=DataKind.TRADES),
        window_start=T0 - timedelta(minutes=10),
        window_end=T0,
        observation=_observation(expected_count=0, observed_count=100),
    )

    assert result.status is QualityStatus.PASS
    assert result.expected_count == 0


def test_real_dataset_rejects_synthetic_lineage(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    manifest = _manifest(store, rights="fixture-test-data")
    store.publish(manifest, expected_current=None)

    with pytest.raises(QualityFailure, match="synthetic"):
        QualityEvaluator(store).evaluate(
            _policy(),
            manifest.manifest_id,
            window_start=T0 - timedelta(minutes=10),
            window_end=T0,
            observation=_observation(synthetic_row_count=1),
        )


def test_policy_rejects_venues_outside_current_trusted_data_scope() -> None:
    with pytest.raises(ValueError, match="outside the trusted-data scope"):
        QualityPolicy.model_validate(
            {**_policy().model_dump(exclude={"policy_id"}), "venue": Venue.POLYMARKET}
        )


def test_real_dataset_requires_a_real_raw_envelope_ancestor(tmp_path) -> None:
    store = ManifestStore(tmp_path)
    with_lineage = _manifest(store)
    orphan = ArtifactManifest.build(
        **with_lineage.model_dump(exclude={"manifest_id", "dataset_id", "parent_manifest_ids"}),
        dataset_id="btc-quality-orphan",
        parent_manifest_ids=(),
    )
    store.publish(orphan, expected_current=None)

    with pytest.raises(QualityFailure, match="terminate at raw manifests"):
        QualityEvaluator(store).evaluate(
            _policy(),
            orphan.manifest_id,
            window_start=T0 - timedelta(minutes=10),
            window_end=T0,
            observation=_observation(),
        )
