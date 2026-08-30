import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from quantmesh.data.artifacts import (
    ArtifactLayer,
    ArtifactManifest,
    ManifestStore,
    canonical_json_bytes,
)
from quantmesh.data.calendars import XNYS_REGULAR_VERSION, SessionPolicy
from quantmesh.data.capabilities import DataKind, EntitlementState
from quantmesh.data.checkpoints import CheckpointStore, CollectionCheckpoint, GraphAdvance
from quantmesh.data.envelopes import ProvenanceClass, RawEnvelope
from quantmesh.data.instruments import CanonicalInstrumentId, InstrumentCatalog
from quantmesh.data.objects import FABRIC_NAMESPACE
from quantmesh.data.overlap_resolutions import (
    OverlapConflict,
    OverlapFieldDiff,
    OverlapResolution,
    OverlapResolutionIntegrityError,
    OverlapResolutionStore,
    ResolutionAttestation,
    ResolutionUsePolicy,
)
from quantmesh.data.quality import (
    QualityBinding,
    QualityEvaluator,
    QualityEvidenceStore,
    QualityPolicy,
    QualityReport,
    QualityStatus,
)
from quantmesh.domain.models import Venue

T_EVENT = datetime(2026, 8, 21, 4, 0, tzinfo=UTC)
T_BASELINE = datetime(2026, 8, 22, 0, tzinfo=UTC)
T_CANDIDATE = T_BASELINE + timedelta(days=1)
T_REVIEW = T_CANDIDATE + timedelta(days=1)
IDENTITY = "US.NVDA:2026-08-21"


def _policy(data_kind: DataKind = DataKind.BARS) -> QualityPolicy:
    return QualityPolicy(
        venue=Venue.MOOMOO,
        layer=ArtifactLayer.RAW,
        data_kind=data_kind,
        interval="1d" if data_kind is DataKind.BARS else None,
        calendar_version=XNYS_REGULAR_VERSION,
        session_policy=SessionPolicy.REGULAR,
        grace_period_seconds=300,
        minimum_coverage_ratio=1.0,
        max_freshness_seconds=604_800,
        max_latency_seconds=604_800,
        require_terminal_pagination=True,
    )


def _raw_manifest(
    root: Path,
    *,
    revision: int,
    known_at: datetime,
    turnover: float,
    row_updates: dict | None = None,
    stage: bool = True,
    data_kind: DataKind = DataKind.BARS,
) -> ArtifactManifest:
    store = ManifestStore(root)
    row = {
        "code": "US.NVDA",
        "time_key": "2026-08-21 09:30:00",
        "open": 180.0,
        "high": 181.0,
        "low": 179.0,
        "close": 180.5,
        "volume": 1_000_000,
        "turnover": turnover,
    }
    row.update(row_updates or {})
    envelope = RawEnvelope.capture(
        objects=store.objects,
        payload=canonical_json_bytes({"rows": [row]}),
        content_type="application/json",
        provider_id="moomoo-opend",
        endpoint="request_history_kline",
        request_id=f"nvda-revision-{revision}",
        request_window_start=T_EVENT,
        request_window_end=T_EVENT,
        cursor=None,
        canonical_instrument=CanonicalInstrumentId(value="moomoo:US:NVDA:XNAS"),
        provider_symbol="US.NVDA",
        data_kind=data_kind,
        source_event_ids=(IDENTITY,),
        event_start=T_EVENT,
        event_end=T_EVENT,
        session_date=T_EVENT.date(),
        provider_available_at=known_at,
        received_at=known_at,
        ingested_at=known_at,
        provider_version="10.10.7008",
        adapter_version="overlap-test-v1",
        schema_version="moomoo-kline-v1",
        source_rights_id="moomoo-operator-entitlement",
        entitlement=EntitlementState.AVAILABLE,
        provenance=ProvenanceClass.REAL,
    )
    envelope_ref = store.objects.put_bytes(
        "application/vnd.quantmesh.raw-envelope+json", envelope.canonical_bytes()
    )
    manifest = ArtifactManifest.build(
        dataset_id="moomoo-nvda-1d-raw-bars",
        compatibility_revision=revision,
        layer=ArtifactLayer.RAW,
        canonical_instrument=CanonicalInstrumentId(value="moomoo:US:NVDA:XNAS"),
        instrument_catalog_id=InstrumentCatalog.bounded_default().catalog_id,
        data_kind=data_kind,
        interval="1d" if data_kind is DataKind.BARS else None,
        calendar_version=XNYS_REGULAR_VERSION,
        session_policy=SessionPolicy.REGULAR,
        objects=(envelope.raw_object, envelope_ref),
        row_identities=(IDENTITY,),
        schema_digest="1" * 64,
        adapter_version="overlap-test-v1",
        parent_manifest_ids=(),
        transformation_policy_digest="2" * 64,
        source_rights_id="moomoo-operator-entitlement",
        entitlement=EntitlementState.AVAILABLE,
        event_start=T_EVENT,
        event_end=T_EVENT,
        knowledge_start=known_at,
        knowledge_end=known_at,
        adjustment_policy=None,
        quality_report_id=None,
        created_at=known_at,
        code_commit="3" * 40,
        collection_run_id=f"nvda-revision-{revision}",
    )
    if stage:
        store.stage(manifest)
    return manifest


def _evidence(
    root: Path,
    *,
    candidate_turnover: float = 180_500_001.0,
    candidate_row_updates: dict | None = None,
    data_kind: DataKind = DataKind.BARS,
):
    manifests = ManifestStore(root)
    predecessors = tuple(
        _raw_manifest(
            root,
            revision=revision,
            known_at=T_EVENT + timedelta(hours=revision),
            turnover=180_500_000.0,
            stage=False,
            data_kind=data_kind,
        )
        for revision in range(1, 5)
    )
    baseline = _raw_manifest(
        root,
        revision=5,
        known_at=T_BASELINE,
        turnover=180_500_000.0,
        stage=False,
        data_kind=data_kind,
    )
    current_id = None
    for predecessor in predecessors:
        manifests.publish(predecessor, expected_current=current_id)
        current_id = predecessor.manifest_id
    manifests.publish(baseline, expected_current=current_id)
    candidate = _raw_manifest(
        root,
        revision=6,
        known_at=T_CANDIDATE,
        turnover=candidate_turnover,
        row_updates=candidate_row_updates,
        data_kind=data_kind,
    )
    admitted = frozenset(
        {
            baseline.manifest_id,
            candidate.manifest_id,
            *(item.manifest_id for item in predecessors),
        }
    )
    evaluator = QualityEvaluator(manifests)
    policy = _policy(data_kind)
    observation = evaluator.measure(
        policy,
        candidate.manifest_id,
        window_start=T_EVENT - timedelta(minutes=1),
        window_end=T_EVENT + timedelta(days=1),
        evaluated_at=T_CANDIDATE + timedelta(hours=1),
        admitted_manifest_ids=admitted,
    )
    failed = evaluator.evaluate(
        policy,
        candidate.manifest_id,
        window_start=T_EVENT - timedelta(minutes=1),
        window_end=T_EVENT + timedelta(days=1),
        observation=observation,
        admitted_manifest_ids=admitted,
    )
    assert failed.status is QualityStatus.FAIL
    assert failed.issue_codes == ("historical-live-overlap",)
    evidence = QualityEvidenceStore(root)
    evidence.record_policy(policy)
    evidence.record(failed, admitted_manifest_ids=admitted)
    provisional_checkpoint = CollectionCheckpoint(
        job_id="4" * 64,
        generation=1,
        provider_cursor="terminal",
        last_complete_source_event=IDENTITY,
        raw_object_digests=tuple(item.digest for item in candidate.objects),
        manifest_ids=(candidate.manifest_id,),
        preflight_id="6" * 64,
        quality_report_id=None,
        run_id="5" * 64,
        attempt=1,
        updated_at=failed.evaluated_at,
    )
    checkpoint_body_digest = hashlib.sha256(
        canonical_json_bytes(
            provisional_checkpoint.model_dump(mode="json", exclude={"quality_report_id"})
        )
    ).hexdigest()
    report = QualityReport.build(
        job_id=provisional_checkpoint.job_id,
        run_id=provisional_checkpoint.run_id,
        checkpoint_body_digest=checkpoint_body_digest,
        bindings=(
            QualityBinding(
                manifest_id=candidate.manifest_id,
                evaluation_id=failed.evaluation_id,
            ),
        ),
    )
    evidence.record_report(report, admitted_manifest_ids=admitted)
    checkpoint = provisional_checkpoint.model_copy(update={"quality_report_id": report.report_id})
    with CheckpointStore(root) as checkpoints:
        with checkpoints.writer():
            checkpoints.commit(
                previous=None,
                next_checkpoint=checkpoint,
                advances=(
                    GraphAdvance(
                        dataset_id=candidate.dataset_id,
                        expected_current=baseline.manifest_id,
                        expected_revision=baseline.compatibility_revision,
                        expected_knowledge_end=baseline.knowledge_end,
                        manifest_id=candidate.manifest_id,
                        revision=candidate.compatibility_revision,
                        knowledge_start=candidate.knowledge_start,
                        knowledge_end=candidate.knowledge_end,
                    ),
                ),
                commit_id="7" * 64,
            )
    conflicts = evaluator.overlap_conflicts(
        candidate.manifest_id,
        baseline.manifest_id,
        admitted_manifest_ids=admitted,
    )
    return baseline, candidate, admitted, failed, report, conflicts


def _resolution(root: Path) -> tuple[OverlapResolutionStore, OverlapResolution, tuple]:
    baseline, candidate, admitted, failed, report, conflicts = _evidence(root)
    resolution = OverlapResolution.build(
        failed_evaluation_id=failed.evaluation_id,
        failed_report_id=report.report_id,
        policy_id=failed.policy_id,
        dataset_id="moomoo-nvda-1d-raw-bars",
        baseline_manifest_id=baseline.manifest_id,
        candidate_manifest_id=candidate.manifest_id,
        conflicts=conflicts,
        predecessor_known_at=baseline.knowledge_end,
        candidate_known_at=candidate.knowledge_end,
        reviewed_at=T_REVIEW,
        operator="local-operator",
        reason="Moomoo revised one historical turnover value; canonical OHLCV is unchanged",
        attestation=ResolutionAttestation.OPERATOR_ACKNOWLEDGED,
        use_policy=ResolutionUsePolicy.OHLCV_DERIVATIVES_ONLY,
    )
    return (
        OverlapResolutionStore(root),
        resolution,
        (
            baseline,
            candidate,
            admitted,
            failed,
            report,
            conflicts,
        ),
    )


def test_conflict_has_exact_rows_field_diff_and_stable_fingerprint(tmp_path: Path) -> None:
    baseline, candidate, admitted, failed, _, conflicts = _evidence(tmp_path)

    assert conflicts == (
        OverlapConflict.build(
            identity=IDENTITY,
            prior_row_fingerprint="a36dc2fc2577fad2055a79bb5b30ec6c623144be4e7e78fe622a77d5ec86a208",
            current_row_fingerprint="410e0ce978866856beb6af465f2908525b4e8a1e03c8b4b76a2c7949bdc4a383",
            field_diffs=(
                OverlapFieldDiff(
                    field="turnover",
                    prior=180_500_000.0,
                    current=180_500_001.0,
                ),
            ),
        ),
    )
    assert conflicts[0].legacy_evaluation_fingerprint == failed.overlap_conflict_fingerprints[0]
    assert conflicts[0].fingerprint == (
        "74a7a819f7b23123bbdd2fc687cf88642813ea544345b5457415557b5ba6da51"
    )
    assert conflicts[0].legacy_evaluation_fingerprint == (
        "e394d233752d11b624cb2d73c30cad6b90e3cea1d579e9f48b787e53a78cf451"
    )
    assert baseline.manifest_id != candidate.manifest_id
    assert {baseline.manifest_id, candidate.manifest_id} <= admitted
    assert len(admitted) == 6


def test_record_load_verify_and_exact_retry_are_idempotent(tmp_path: Path) -> None:
    store, resolution, context = _resolution(tmp_path)
    admitted = context[2]

    first = store.record(resolution, admitted_manifest_ids=admitted)
    second = store.record(resolution, admitted_manifest_ids=admitted)

    assert first == second == resolution
    assert store.load(resolution.resolution_id) == resolution
    assert (
        store.for_evaluation(
            resolution.failed_evaluation_id,
            admitted_manifest_ids=admitted,
        )
        == resolution
    )
    assert store.verify(resolution, admitted_manifest_ids=admitted) == resolution


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("dataset_id", "moomoo-aapl-1d-raw-bars", "dataset"),
        ("policy_id", "a" * 64, "policy"),
        ("baseline_manifest_id", "b" * 64, "baseline manifest"),
        ("candidate_manifest_id", "c" * 64, "candidate manifest"),
        ("operator", " ", "operator"),
        ("reason", " ", "reason"),
        ("reviewed_at", T_CANDIDATE - timedelta(seconds=1), "review"),
    ],
)
def test_resolution_rejects_wrong_contract_fields(
    tmp_path: Path, field: str, value, match: str
) -> None:
    store, resolution, context = _resolution(tmp_path)
    values = resolution.model_dump(exclude={"resolution_id"})
    values[field] = value

    if field in {"operator", "reason", "reviewed_at"}:
        with pytest.raises(ValidationError, match=match):
            OverlapResolution.build(**values)
        return

    changed = OverlapResolution.build(**values)
    with pytest.raises(OverlapResolutionIntegrityError, match=match):
        store.verify(changed, admitted_manifest_ids=context[2])


def test_resolution_rejects_changed_or_partial_conflict_set(tmp_path: Path) -> None:
    store, resolution, context = _resolution(tmp_path)
    conflict = resolution.conflicts[0]
    changed_conflict = OverlapConflict.build(
        identity=conflict.identity,
        prior_row_fingerprint=conflict.prior_row_fingerprint,
        current_row_fingerprint="d" * 64,
        field_diffs=conflict.field_diffs,
    )
    changed = OverlapResolution.build(
        **{
            **resolution.model_dump(exclude={"resolution_id", "conflicts"}),
            "conflicts": (changed_conflict,),
        }
    )
    partial_values = resolution.model_dump(exclude={"resolution_id", "conflicts"})

    with pytest.raises(OverlapResolutionIntegrityError, match="conflict"):
        store.verify(changed, admitted_manifest_ids=context[2])
    with pytest.raises(ValidationError, match="conflicts"):
        OverlapResolution.build(**partial_values, conflicts=())


def test_resolution_rejects_an_older_matching_nonpredecessor(tmp_path: Path) -> None:
    store, resolution, context = _resolution_with_older(tmp_path)

    with pytest.raises(OverlapResolutionIntegrityError, match="committed predecessor"):
        store.verify(resolution, admitted_manifest_ids=context[2])


def _resolution_with_older(root: Path):
    baseline, candidate, admitted, failed, report, _ = _evidence(root)
    history = ManifestStore(root).manifests(candidate.dataset_id)
    older = history[-3]
    conflicts = QualityEvaluator(ManifestStore(root)).overlap_conflicts(
        candidate.manifest_id,
        older.manifest_id,
        admitted_manifest_ids=admitted,
    )
    resolution = OverlapResolution.build(
        failed_evaluation_id=failed.evaluation_id,
        failed_report_id=report.report_id,
        policy_id=failed.policy_id,
        dataset_id=candidate.dataset_id,
        baseline_manifest_id=older.manifest_id,
        candidate_manifest_id=candidate.manifest_id,
        conflicts=conflicts,
        predecessor_known_at=older.knowledge_end,
        candidate_known_at=candidate.knowledge_end,
        reviewed_at=T_REVIEW,
        operator="local-operator",
        reason="Incorrect older baseline with byte-equal source row",
        attestation=ResolutionAttestation.OPERATOR_ACKNOWLEDGED,
        use_policy=ResolutionUsePolicy.OHLCV_DERIVATIVES_ONLY,
    )
    return (
        OverlapResolutionStore(root),
        resolution,
        (
            baseline,
            candidate,
            admitted,
            failed,
            report,
            conflicts,
        ),
    )


def test_resolution_rejects_changed_ohlcv_under_bounded_use_policy(tmp_path: Path) -> None:
    baseline, candidate, admitted, failed, report, conflicts = _evidence(
        tmp_path,
        candidate_turnover=180_500_000.0,
        candidate_row_updates={"close": 181.5},
    )
    resolution = OverlapResolution.build(
        failed_evaluation_id=failed.evaluation_id,
        failed_report_id=report.report_id,
        policy_id=failed.policy_id,
        dataset_id=candidate.dataset_id,
        baseline_manifest_id=baseline.manifest_id,
        candidate_manifest_id=candidate.manifest_id,
        conflicts=conflicts,
        predecessor_known_at=baseline.knowledge_end,
        candidate_known_at=candidate.knowledge_end,
        reviewed_at=T_REVIEW,
        operator="local-operator",
        reason="Invalid attempt to authorize changed close",
        attestation=ResolutionAttestation.OPERATOR_ACKNOWLEDGED,
        use_policy=ResolutionUsePolicy.OHLCV_DERIVATIVES_ONLY,
    )

    with pytest.raises(OverlapResolutionIntegrityError, match="unchanged raw OHLCV"):
        OverlapResolutionStore(tmp_path).verify(
            resolution,
            admitted_manifest_ids=admitted,
        )


def test_resolution_rejects_provider_wire_close_alias_under_ohlcv_policy(
    tmp_path: Path,
) -> None:
    baseline, candidate, admitted, failed, report, conflicts = _evidence(
        tmp_path,
        candidate_turnover=180_500_000.0,
        candidate_row_updates={"c": "181.5"},
    )
    resolution = OverlapResolution.build(
        failed_evaluation_id=failed.evaluation_id,
        failed_report_id=report.report_id,
        policy_id=failed.policy_id,
        dataset_id=candidate.dataset_id,
        baseline_manifest_id=baseline.manifest_id,
        candidate_manifest_id=candidate.manifest_id,
        conflicts=conflicts,
        predecessor_known_at=baseline.knowledge_end,
        candidate_known_at=candidate.knowledge_end,
        reviewed_at=T_REVIEW,
        operator="local-operator",
        reason="Invalid attempt to authorize a wire-format close correction",
        attestation=ResolutionAttestation.OPERATOR_ACKNOWLEDGED,
        use_policy=ResolutionUsePolicy.OHLCV_DERIVATIVES_ONLY,
    )

    with pytest.raises(OverlapResolutionIntegrityError, match="unchanged raw OHLCV"):
        OverlapResolutionStore(tmp_path).verify(
            resolution,
            admitted_manifest_ids=admitted,
        )


def test_resolution_rejects_nonbar_dataset_under_ohlcv_policy(tmp_path: Path) -> None:
    baseline, candidate, admitted, failed, report, conflicts = _evidence(
        tmp_path,
        data_kind=DataKind.TRADES,
    )
    resolution = OverlapResolution.build(
        failed_evaluation_id=failed.evaluation_id,
        failed_report_id=report.report_id,
        policy_id=failed.policy_id,
        dataset_id=candidate.dataset_id,
        baseline_manifest_id=baseline.manifest_id,
        candidate_manifest_id=candidate.manifest_id,
        conflicts=conflicts,
        predecessor_known_at=baseline.knowledge_end,
        candidate_known_at=candidate.knowledge_end,
        reviewed_at=T_REVIEW,
        operator="local-operator",
        reason="Invalid attempt to apply a bar-only use policy to trades",
        attestation=ResolutionAttestation.OPERATOR_ACKNOWLEDGED,
        use_policy=ResolutionUsePolicy.OHLCV_DERIVATIVES_ONLY,
    )

    with pytest.raises(OverlapResolutionIntegrityError, match="unchanged raw OHLCV"):
        OverlapResolutionStore(tmp_path).verify(
            resolution,
            admitted_manifest_ids=admitted,
        )


def test_resolution_review_cannot_predate_failed_evaluation(tmp_path: Path) -> None:
    store, resolution, context = _resolution(tmp_path)
    backdated = OverlapResolution.build(
        **{
            **resolution.model_dump(exclude={"resolution_id", "reviewed_at"}),
            "reviewed_at": resolution.candidate_known_at,
        }
    )

    with pytest.raises(OverlapResolutionIntegrityError, match="failed evaluation"):
        store.verify(backdated, admitted_manifest_ids=context[2])


def test_resolution_review_must_strictly_follow_failed_evaluation(tmp_path: Path) -> None:
    store, resolution, context = _resolution(tmp_path)
    failed = context[3]
    simultaneous = OverlapResolution.build(
        **{
            **resolution.model_dump(exclude={"resolution_id", "reviewed_at"}),
            "reviewed_at": failed.evaluated_at,
        }
    )

    with pytest.raises(OverlapResolutionIntegrityError, match="follow.*failed evaluation"):
        store.verify(simultaneous, admitted_manifest_ids=context[2])


def test_concurrent_different_resolution_cannot_replace_binding(tmp_path: Path) -> None:
    store, resolution, context = _resolution(tmp_path)
    changed = OverlapResolution.build(
        **{
            **resolution.model_dump(exclude={"resolution_id", "reason"}),
            "reason": "Independent operator wording for the same exact provider correction",
        }
    )

    def record(item: OverlapResolution):
        try:
            return store.record(item, admitted_manifest_ids=context[2]).resolution_id
        except OverlapResolutionIntegrityError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(record, (resolution, changed)))

    assert sorted(result == "rejected" for result in results) == [False, True]
    bound = store.for_evaluation(
        resolution.failed_evaluation_id,
        admitted_manifest_ids=context[2],
    )
    assert bound.resolution_id in {resolution.resolution_id, changed.resolution_id}


def test_missing_object_and_altered_binding_fail_closed(tmp_path: Path) -> None:
    store, resolution, context = _resolution(tmp_path)
    store.record(resolution, admitted_manifest_ids=context[2])
    object_path = store.path_for(resolution.resolution_id)
    object_path.unlink()

    with pytest.raises(OverlapResolutionIntegrityError, match="missing|invalid"):
        store.for_evaluation(
            resolution.failed_evaluation_id,
            admitted_manifest_ids=context[2],
        )

    store.objects.put_bytes(store.RESOLUTION_MEDIA_TYPE, resolution.canonical_bytes())
    binding_path = (
        tmp_path
        / FABRIC_NAMESPACE
        / "quality"
        / "overlap-resolutions"
        / f"{resolution.failed_evaluation_id}.json"
    )
    binding = json.loads(binding_path.read_bytes())
    binding["resolution_id"] = "f" * 64
    binding_path.write_bytes(canonical_json_bytes(binding))

    with pytest.raises(OverlapResolutionIntegrityError, match="binding|resolution|winner"):
        store.for_evaluation(
            resolution.failed_evaluation_id,
            admitted_manifest_ids=context[2],
        )


def test_binding_cannot_be_repointed_to_a_losing_valid_resolution(tmp_path: Path) -> None:
    store, resolution, context = _resolution(tmp_path)
    changed = OverlapResolution.build(
        **{
            **resolution.model_dump(exclude={"resolution_id", "reason"}),
            "reason": "Second valid object that did not win the create-once binding",
        }
    )
    store.record(resolution, admitted_manifest_ids=context[2])
    with pytest.raises(OverlapResolutionIntegrityError, match="different overlap resolution"):
        store.record(changed, admitted_manifest_ids=context[2])
    binding_path = (
        tmp_path
        / FABRIC_NAMESPACE
        / "quality"
        / "overlap-resolutions"
        / f"{resolution.failed_evaluation_id}.json"
    )
    binding = json.loads(binding_path.read_bytes())
    binding["resolution_id"] = changed.resolution_id
    binding_path.write_bytes(canonical_json_bytes(binding))

    with pytest.raises(OverlapResolutionIntegrityError, match="winner anchor"):
        store.for_evaluation(
            resolution.failed_evaluation_id,
            admitted_manifest_ids=context[2],
        )


def test_binding_and_new_anchor_cannot_hide_the_original_winner(tmp_path: Path) -> None:
    store, resolution, context = _resolution(tmp_path)
    changed = OverlapResolution.build(
        **{
            **resolution.model_dump(exclude={"resolution_id", "reason"}),
            "reason": "Second valid object that did not win the create-once binding",
        }
    )
    store.record(resolution, admitted_manifest_ids=context[2])
    with pytest.raises(OverlapResolutionIntegrityError, match="different overlap resolution"):
        store.record(changed, admitted_manifest_ids=context[2])
    store.objects.put_bytes(store.RESOLUTION_MEDIA_TYPE, changed.canonical_bytes())

    binding_path = store._binding_path(resolution.failed_evaluation_id)
    forged = json.loads(binding_path.read_bytes())
    forged["resolution_id"] = changed.resolution_id
    payload = canonical_json_bytes(forged)
    binding_path.write_bytes(payload)
    winner_path = store._winner_path(changed.resolution_id)
    winner_path.parent.mkdir(parents=True, exist_ok=True)
    winner_path.write_bytes(payload)

    with pytest.raises(OverlapResolutionIntegrityError, match="multiple winner anchors"):
        store.for_evaluation(
            resolution.failed_evaluation_id,
            admitted_manifest_ids=context[2],
        )
