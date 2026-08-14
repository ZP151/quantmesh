from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from quantmesh.data.artifacts import (
    ArtifactLayer,
    ArtifactManifest,
    ManifestStore,
    canonical_json_bytes,
)
from quantmesh.data.calendars import (
    CONTINUOUS_UTC_VERSION,
    XNYS_REGULAR_VERSION,
    SessionPolicy,
)
from quantmesh.data.capabilities import DataKind, EntitlementState
from quantmesh.data.catalog import TrustedDataCatalog
from quantmesh.data.checkpoints import CheckpointIntegrityError
from quantmesh.data.collection import (
    CollectionCoordinator,
    CollectionJob,
    InjectedCrash,
    PublicationStage,
    QualityPublicationContext,
    StagingManifestStore,
    _quality_window_end,
)
from quantmesh.data.envelopes import ProvenanceClass, RawEnvelope
from quantmesh.data.instruments import CanonicalInstrumentId, InstrumentCatalog
from quantmesh.data.quality import (
    QualityBinding,
    QualityEvaluator,
    QualityPolicy,
    QualityReport,
    QualityStatus,
)
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue

T0 = datetime(2026, 8, 14, tzinfo=UTC)


def _job(
    provider_id: str = "hyperliquid-public",
    *,
    collection_cycle: str = "initial",
) -> CollectionJob:
    return CollectionJob(
        provider_id=provider_id,
        endpoints=("info/candleSnapshot",),
        source_request_ids=("quality-publication",),
        canonical_instruments=(CanonicalInstrumentId(value="hyperliquid:perp:BTC"),),
        data_kinds=(DataKind.BARS,),
        intervals=("1m",),
        calendar_version=CONTINUOUS_UTC_VERSION,
        session_policy=SessionPolicy.CONTINUOUS,
        window_start=T0,
        window_end=T0 + timedelta(minutes=1),
        adjustment_policy="identity-no-corporate-actions-v1",
        schema_versions=("hyperliquid-candleSnapshot-v1",),
        mapping_version=InstrumentCatalog.bounded_default().catalog_id,
        code_commit="3" * 40,
        collection_cycle=collection_cycle,
    )


def _envelope(
    store: ManifestStore,
    *,
    provider_id: str = "hyperliquid-public",
    provenance: ProvenanceClass = ProvenanceClass.REAL,
) -> RawEnvelope:
    return RawEnvelope.capture(
        objects=store.objects,
        payload=b"[]",
        content_type="application/json",
        provider_id=provider_id,
        endpoint="info/candleSnapshot",
        request_id="quality-publication",
        request_window_start=T0,
        request_window_end=T0,
        collection_window_start=T0,
        collection_window_end=T0 + timedelta(minutes=1),
        cursor=None,
        canonical_instrument=CanonicalInstrumentId(value="hyperliquid:perp:BTC"),
        provider_symbol="BTC",
        data_kind=DataKind.BARS,
        source_event_ids=("BTC:2026-08-14T00:00:00+00:00",),
        event_start=T0,
        event_end=T0,
        session_date=T0.date(),
        provider_available_at=T0,
        received_at=T0 + timedelta(minutes=1),
        ingested_at=T0 + timedelta(minutes=1),
        provider_version="mainnet-v1",
        adapter_version="quality-publication-v1",
        schema_version="hyperliquid-candleSnapshot-v1",
        source_rights_id=(
            "hyperliquid-public-market-data"
            if provenance is ProvenanceClass.REAL
            else "fixture-test-data"
        ),
        entitlement=EntitlementState.NOT_REQUIRED,
        provenance=provenance,
    )


def _producer(
    store: ManifestStore,
    envelope: RawEnvelope,
    *,
    dataset_prefix: str = "quality-publication",
):
    envelope_ref = store.objects.put_bytes(
        "application/vnd.quantmesh.raw-envelope+json", envelope.canonical_bytes()
    )

    def produce(staging: StagingManifestStore) -> tuple[str, ...]:
        bar = Bar(
            instrument=Instrument(
                symbol="BTC",
                venue=Venue.HYPERLIQUID,
                instrument_type=InstrumentType.PERPETUAL,
                currency="USD",
            ),
            timestamp=T0,
            interval="1m",
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.0,
            volume=1.0,
        )
        bar_ref = store.objects.put_bytes(
            "application/vnd.quantmesh.bars+json",
            canonical_json_bytes([bar.model_dump(mode="json")]),
        )
        feature_ref = store.objects.put_bytes(
            "application/vnd.quantmesh.features+json",
            canonical_json_bytes(
                [
                    {
                        "name": "log_return",
                        "timestamp": T0.isoformat(),
                        "value": 0.0,
                        "window": 2,
                    }
                ]
            ),
        )
        common = {
            "compatibility_revision": 1,
            "canonical_instrument": envelope.canonical_instrument,
            "instrument_catalog_id": InstrumentCatalog.bounded_default().catalog_id,
            "data_kind": DataKind.BARS,
            "interval": "1m",
            "calendar_version": CONTINUOUS_UTC_VERSION,
            "session_policy": SessionPolicy.CONTINUOUS,
            "adapter_version": envelope.adapter_version,
            "source_rights_id": envelope.source_rights_id,
            "entitlement": envelope.entitlement,
            "event_start": T0,
            "event_end": T0,
            "knowledge_start": envelope.knowledge_time,
            "knowledge_end": envelope.knowledge_time,
            "quality_report_id": None,
            "created_at": envelope.ingested_at,
            "code_commit": "3" * 40,
            "collection_run_id": staging.collection_run_id,
        }
        raw = ArtifactManifest.build(
            dataset_id=f"{dataset_prefix}-raw",
            layer=ArtifactLayer.RAW,
            objects=(envelope.raw_object, envelope_ref),
            row_identities=envelope.source_event_ids,
            schema_digest="1" * 64,
            parent_manifest_ids=(),
            transformation_policy_digest="2" * 64,
            adjustment_policy=None,
            **common,
        )
        normalized = ArtifactManifest.build(
            dataset_id=f"{dataset_prefix}-normalized",
            layer=ArtifactLayer.NORMALIZED,
            objects=(bar_ref,),
            row_identities=(f"BTC:{T0.isoformat()}",),
            schema_digest="3" * 64,
            parent_manifest_ids=(raw.manifest_id,),
            transformation_policy_digest="4" * 64,
            adjustment_policy=None,
            **common,
        )
        adjusted = ArtifactManifest.build(
            dataset_id=f"{dataset_prefix}-adjusted",
            layer=ArtifactLayer.ADJUSTED,
            objects=(bar_ref,),
            row_identities=(f"BTC:{T0.isoformat()}",),
            schema_digest="3" * 64,
            parent_manifest_ids=(normalized.manifest_id,),
            transformation_policy_digest="5" * 64,
            adjustment_policy="identity-no-corporate-actions-v1",
            **common,
        )
        feature = ArtifactManifest.build(
            dataset_id=f"{dataset_prefix}-feature",
            layer=ArtifactLayer.FEATURE,
            objects=(feature_ref,),
            row_identities=(f"log_return:{T0.isoformat()}",),
            schema_digest="6" * 64,
            parent_manifest_ids=(adjusted.manifest_id,),
            transformation_policy_digest="7" * 64,
            adjustment_policy="identity-no-corporate-actions-v1",
            **common,
        )
        manifests = (raw, normalized, adjusted, feature)
        for manifest in manifests:
            staging.publish(manifest, expected_current=None)
        return tuple(manifest.manifest_id for manifest in manifests)

    return produce


def _quality_builder(
    store: ManifestStore,
    reports: list[str],
    *,
    max_latency_seconds: int = 300,
    authoritative_window: bool = True,
):
    evidence = CollectionCoordinator(store).quality

    def build(context: QualityPublicationContext) -> QualityReport:
        admitted = frozenset(context.manifest_ids)
        evaluations = []
        for manifest_id in context.manifest_ids:
            manifest = store.open(manifest_id).manifest
            policy = QualityPolicy(
                venue=Venue.HYPERLIQUID,
                layer=manifest.layer,
                data_kind=DataKind.BARS,
                interval="1m",
                calendar_version=CONTINUOUS_UTC_VERSION,
                session_policy=SessionPolicy.CONTINUOUS,
                grace_period_seconds=300,
                minimum_coverage_ratio=1.0,
                max_freshness_seconds=600,
                max_latency_seconds=max_latency_seconds,
                require_terminal_pagination=False,
            )
            evidence.record_policy(policy)
            evaluator = QualityEvaluator(store)
            window_end = (
                _quality_window_end(manifest, T0 + timedelta(minutes=1))
                if authoritative_window
                else T0 + timedelta(minutes=1)
            )
            observation = evaluator.measure(
                policy,
                manifest_id,
                window_start=T0,
                window_end=window_end,
                evaluated_at=context.updated_at,
                admitted_manifest_ids=admitted,
            )
            evaluation = evaluator.evaluate(
                policy,
                manifest_id,
                window_start=T0,
                window_end=window_end,
                observation=observation,
                admitted_manifest_ids=admitted,
            )
            evidence.record(evaluation, admitted_manifest_ids=admitted)
            evaluations.append(evaluation)
        report = QualityReport.build(
            job_id=context.job_id,
            run_id=context.run_id,
            checkpoint_body_digest=context.checkpoint_body_digest,
            bindings=tuple(
                sorted(
                    (
                        QualityBinding(
                            manifest_id=evaluation.manifest_id,
                            evaluation_id=evaluation.evaluation_id,
                        )
                        for evaluation in evaluations
                    ),
                    key=lambda binding: binding.manifest_id,
                )
            ),
        )
        reports.append(report.report_id)
        return report

    return build


def test_quality_report_is_checkpoint_bound_and_retry_stable(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    envelope = _envelope(store)
    coordinator = CollectionCoordinator(store)
    job = _job()
    coordinator.capture_source(
        job,
        media_type="application/vnd.quantmesh.hyperliquid-source-batch+json",
        payload=b"[]",
        raw_payloads=(b"[]",),
    )
    reports: list[str] = []
    arguments = {
        "producer": _producer(store, envelope),
        "provider_cursor": "terminal",
        "last_complete_source_event": envelope.source_event_ids[-1],
        "updated_at": T0 + timedelta(minutes=10),
        "quality_builder": _quality_builder(store, reports),
    }

    with pytest.raises(InjectedCrash, match="quality"):
        coordinator.run(job, crash_after=PublicationStage.QUALITY, **arguments)

    publication = coordinator.run(job, **arguments)

    assert publication.quality_report_id is not None
    assert reports == [publication.quality_report_id] * 2
    checkpoint = coordinator.checkpoints.get(job.job_id)
    assert checkpoint is not None
    assert checkpoint.quality_report_id == publication.quality_report_id
    assert coordinator.quality.verify_report(publication.quality_report_id)

    report_path = coordinator.quality.path_for(publication.quality_report_id)
    report_path.write_bytes(report_path.read_bytes() + b" ")
    with pytest.raises(CheckpointIntegrityError, match="quality evidence"):
        coordinator.run(job, **arguments)


def test_real_graph_uses_default_quality_builder(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    envelope = _envelope(store)
    coordinator = CollectionCoordinator(store)
    job = _job()
    coordinator.capture_source(
        job,
        media_type="application/vnd.quantmesh.hyperliquid-source-batch+json",
        payload=b"[]",
        raw_payloads=(b"[]",),
    )

    publication = coordinator.run(
        job,
        producer=_producer(store, envelope),
        provider_cursor="terminal",
        last_complete_source_event=envelope.source_event_ids[-1],
        updated_at=T0 + timedelta(minutes=10),
    )

    assert publication.quality_report_id is not None
    report = coordinator.quality.verify_report(publication.quality_report_id)
    assert tuple(binding.manifest_id for binding in report.bindings) == tuple(
        sorted(publication.manifest_ids)
    )
    feature_id = next(
        manifest_id
        for manifest_id in publication.manifest_ids
        if store.open(manifest_id).manifest.layer is ArtifactLayer.FEATURE
    )
    feature_binding = next(
        binding for binding in report.bindings if binding.manifest_id == feature_id
    )
    feature_evaluation = coordinator.quality.load(feature_binding.evaluation_id)
    assert feature_evaluation.status is QualityStatus.FAIL
    assert "unexplained-gap" in feature_evaluation.issue_codes
    checkpoint = coordinator.checkpoints.get(job.job_id)
    assert checkpoint is not None
    with pytest.raises(ValueError, match="unqualified"):
        coordinator._verified_publication(
            checkpoint.model_copy(update={"quality_report_id": None}),
            job=job,
        )


def test_catalog_projects_exact_committed_quality_and_lineage(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    coordinator = CollectionCoordinator(store)
    job = _job()
    envelope = _envelope(store)
    coordinator.capture_source(
        job,
        media_type="application/vnd.quantmesh.hyperliquid-source-batch+json",
        payload=b"[]",
        raw_payloads=(b"[]",),
    )
    publication = coordinator.run(
        job,
        producer=_producer(store, envelope),
        provider_cursor="terminal",
        last_complete_source_event=envelope.source_event_ids[-1],
        updated_at=T0 + timedelta(minutes=10),
    )

    entries = TrustedDataCatalog(tmp_path).entries()

    assert {entry.current_manifest_id for entry in entries} == set(
        publication.manifest_ids
    )
    assert all(entry.quality is not None for entry in entries)
    assert all(
        entry.latest_checkpoint is not None
        and entry.latest_checkpoint.quality_report_id == publication.quality_report_id
        for entry in entries
    )
    for entry in entries:
        assert entry.trusted_for_research is (
            entry.quality is not None and entry.quality.status is QualityStatus.PASS
        )

    feature = next(entry for entry in entries if entry.layer is ArtifactLayer.FEATURE)
    lineage = TrustedDataCatalog(tmp_path).lineage(feature.current_manifest_id)
    assert lineage.entry == feature
    assert [item.layer for item in lineage.ancestors] == [
        ArtifactLayer.RAW,
        ArtifactLayer.NORMALIZED,
        ArtifactLayer.ADJUSTED,
    ]


def test_fixture_checkpoint_rejects_a_quality_report_identity(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    coordinator = CollectionCoordinator(store)
    job = _job("fixture-hyperliquid-public")
    envelope = _envelope(
        store,
        provider_id="fixture-hyperliquid-public",
        provenance=ProvenanceClass.FIXTURE,
    )
    coordinator.run(
        job,
        producer=_producer(store, envelope),
        provider_cursor="terminal",
        last_complete_source_event=envelope.source_event_ids[-1],
        updated_at=T0 + timedelta(minutes=10),
    )
    checkpoint = coordinator.checkpoints.get(job.job_id)
    assert checkpoint is not None

    with pytest.raises(ValueError, match="fixture checkpoints"):
        coordinator._verified_publication(
            checkpoint.model_copy(update={"quality_report_id": "0" * 64}),
            job=job,
        )


def test_real_custom_builder_cannot_relax_the_authoritative_policy(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    coordinator = CollectionCoordinator(store)
    job = _job()
    envelope = _envelope(store)
    coordinator.capture_source(
        job,
        media_type="application/vnd.quantmesh.hyperliquid-source-batch+json",
        payload=b"[]",
        raw_payloads=(b"[]",),
    )

    with pytest.raises(ValueError, match="authoritative policy"):
        coordinator.run(
            job,
            producer=_producer(store, envelope),
            provider_cursor="terminal",
            last_complete_source_event=envelope.source_event_ids[-1],
            updated_at=T0 + timedelta(minutes=10),
            quality_builder=_quality_builder(
                store,
                [],
                max_latency_seconds=301,
            ),
        )


def test_real_custom_builder_cannot_shrink_the_authoritative_window(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    coordinator = CollectionCoordinator(store)
    job = _job()
    envelope = _envelope(store)
    coordinator.capture_source(
        job,
        media_type="application/vnd.quantmesh.hyperliquid-source-batch+json",
        payload=b"[]",
        raw_payloads=(b"[]",),
    )

    with pytest.raises(ValueError, match="authoritative window"):
        coordinator.run(
            job,
            producer=_producer(store, envelope),
            provider_cursor="terminal",
            last_complete_source_event=envelope.source_event_ids[-1],
            updated_at=T0 + timedelta(minutes=10),
            quality_builder=_quality_builder(
                store,
                [],
                authoritative_window=False,
            ),
        )


def test_quality_window_includes_an_inclusive_terminal_bar_open(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    manifest_id = _producer(store, _envelope(store))(
        StagingManifestStore(store, collection_run_id="quality-window-test")
    )[1]
    manifest = store.open(manifest_id).manifest

    assert _quality_window_end(manifest, manifest.event_end) == (
        manifest.event_end + timedelta(minutes=1)
    )
    assert _quality_window_end(
        manifest, manifest.event_end + timedelta(minutes=1)
    ) == manifest.event_end + timedelta(minutes=2)


def test_moomoo_terminal_open_is_included_independently_of_observed_rows(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    manifest_id = _producer(store, _envelope(store))(
        StagingManifestStore(store, collection_run_id="quality-moomoo-window-test")
    )[1]
    source = store.open(manifest_id).manifest
    observed_end = datetime(2026, 8, 14, 13, 30, tzinfo=UTC)
    requested_end = observed_end + timedelta(minutes=1)
    values = source.model_dump(exclude={"manifest_id"})
    values.update(
        canonical_instrument=CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
        calendar_version=XNYS_REGULAR_VERSION,
        session_policy=SessionPolicy.REGULAR,
        event_start=observed_end,
        event_end=observed_end,
    )
    moomoo = ArtifactManifest.build(**values)

    assert _quality_window_end(moomoo, requested_end) == requested_end + timedelta(minutes=1)

    daily_values = moomoo.model_dump(exclude={"manifest_id"})
    daily_open = datetime(2026, 11, 1, 4, tzinfo=UTC)
    daily_values.update(
        interval="1d",
        event_start=daily_open,
        event_end=daily_open,
    )
    daily = ArtifactManifest.build(**daily_values)
    assert _quality_window_end(daily, daily_open) == datetime(2026, 11, 2, 5, tzinfo=UTC)


@pytest.mark.parametrize("missing", ["report", "evaluation", "policy"])
def test_normal_manifest_reads_fail_closed_when_quality_closure_is_missing(
    tmp_path: Path, missing: str
) -> None:
    store = ManifestStore(tmp_path)
    envelope = _envelope(store)
    coordinator = CollectionCoordinator(store)
    job = _job()
    coordinator.capture_source(
        job,
        media_type="application/vnd.quantmesh.hyperliquid-source-batch+json",
        payload=b"[]",
        raw_payloads=(b"[]",),
    )
    publication = coordinator.run(
        job,
        producer=_producer(store, envelope),
        provider_cursor="terminal",
        last_complete_source_event=envelope.source_event_ids[-1],
        updated_at=T0 + timedelta(minutes=10),
    )
    assert publication.quality_report_id is not None
    report = coordinator.quality.load_report(publication.quality_report_id)
    evaluation = coordinator.quality.load(report.bindings[0].evaluation_id)
    identity = {
        "report": publication.quality_report_id,
        "evaluation": evaluation.evaluation_id,
        "policy": evaluation.policy_id,
    }[missing]
    coordinator.quality.path_for(identity).unlink()

    with pytest.raises(CheckpointIntegrityError, match="quality evidence"):
        coordinator.checkpoints.get(job.job_id)
    with pytest.raises(CheckpointIntegrityError, match="quality evidence"):
        store.current("quality-publication-raw")
    with pytest.raises(CheckpointIntegrityError, match="quality evidence"):
        store.manifests("quality-publication-raw")


def test_quality_corruption_is_isolated_to_the_owning_job_and_datasets(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    coordinator = CollectionCoordinator(store)
    publications = []
    jobs = (
        _job(collection_cycle="independent-a"),
        _job(collection_cycle="independent-b"),
    )
    for suffix, job in zip(("a", "b"), jobs, strict=True):
        envelope = _envelope(store)
        coordinator.capture_source(
            job,
            media_type="application/vnd.quantmesh.hyperliquid-source-batch+json",
            payload=b"[]",
            raw_payloads=(b"[]",),
        )
        publications.append(
            coordinator.run(
                job,
                producer=_producer(
                    store,
                    envelope,
                    dataset_prefix=f"quality-independent-{suffix}",
                ),
                provider_cursor="terminal",
                last_complete_source_event=envelope.source_event_ids[-1],
                updated_at=T0 + timedelta(minutes=10),
            )
        )
    assert publications[0].quality_report_id is not None
    coordinator.quality.path_for(publications[0].quality_report_id).unlink()

    with pytest.raises(CheckpointIntegrityError, match="quality evidence"):
        coordinator.checkpoints.get(jobs[0].job_id)
    assert coordinator.checkpoints.get(jobs[1].job_id) is not None
    assert store.current("quality-independent-b-raw") is not None
    lineage = TrustedDataCatalog(tmp_path).lineage(publications[1].manifest_ids[0])
    assert lineage.entry.current_manifest_id == publications[1].manifest_ids[0]
