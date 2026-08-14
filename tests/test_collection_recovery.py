import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from quantmesh.data.adjustments import UNADJUSTED_IDENTITY
from quantmesh.data.artifacts import ArtifactLayer, ManifestConflictError, ManifestStore
from quantmesh.data.calendars import XNYS_REGULAR_VERSION, SessionPolicy
from quantmesh.data.capabilities import DataKind, EntitlementState
from quantmesh.data.checkpoints import (
    CheckpointConflictError,
    CheckpointIntegrityError,
    ConcurrentWriterError,
)
from quantmesh.data.collection import (
    CollectionCoordinator,
    CollectionJob,
    InjectedCrash,
    PublicationStage,
    StagingManifestStore,
)
from quantmesh.data.envelopes import ProvenanceClass, RawEnvelope
from quantmesh.data.fabric import FabricFeatureSpec, FabricPublisher
from quantmesh.data.instruments import CanonicalInstrumentId, InstrumentCatalog
from quantmesh.data.objects import FABRIC_NAMESPACE
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue

T0 = datetime(2026, 8, 12, 13, 30, tzinfo=UTC)
AAPL = Instrument(
    symbol="AAPL",
    venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY,
    currency="USD",
)
DATASETS = (
    "aapl-daily-raw",
    "aapl-daily-normalized",
    "aapl-daily-adjusted",
    "aapl-daily-feature-log-return-2",
)


_SUBPROCESS_COORDINATOR = r'''
import json
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from quantmesh.data.adjustments import UNADJUSTED_IDENTITY
from quantmesh.data.artifacts import ManifestStore
from quantmesh.data.calendars import XNYS_REGULAR_VERSION, SessionPolicy
from quantmesh.data.capabilities import DataKind, EntitlementState
from quantmesh.data.checkpoints import ConcurrentWriterError
from quantmesh.data.collection import (
    CollectionCoordinator, CollectionJob, InjectedCrash, PublicationStage,
)
from quantmesh.data.envelopes import ProvenanceClass, RawEnvelope
from quantmesh.data.fabric import FabricFeatureSpec, FabricPublisher
from quantmesh.data.instruments import CanonicalInstrumentId, InstrumentCatalog
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue

root = Path(sys.argv[1])
stage = None if sys.argv[2] == '-' else PublicationStage(sys.argv[2])
gate = None if sys.argv[3] == '-' else Path(sys.argv[3])
if gate is not None:
    while not gate.exists():
        time.sleep(0.005)
t0 = datetime(2026, 8, 12, 13, 30, tzinfo=UTC)
instrument = Instrument(
    symbol='AAPL', venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY, currency='USD',
)
bars = [
    Bar(
        instrument=instrument,
        timestamp=t0 + timedelta(days=index), interval='1d',
        open=close, high=close + 1, low=close - 1, close=close,
        volume=1000 + index,
    )
    for index, close in enumerate((100.0, 101.0, 102.0))
]
store = ManifestStore(root)
payload = json.dumps(
    [bar.model_dump(mode='json') for bar in bars],
    sort_keys=True, separators=(',', ':'),
).encode()
envelope = RawEnvelope.capture(
    objects=store.objects, payload=payload, content_type='application/json',
    provider_id='fixture-moomoo', endpoint='fixture://aapl-daily',
    request_id='restart-proof', request_window_start=bars[0].timestamp,
    request_window_end=bars[-1].timestamp, cursor=None,
    canonical_instrument=CanonicalInstrumentId(value='moomoo:US:AAPL:XNAS'),
    provider_symbol='US.AAPL', data_kind=DataKind.BARS,
    source_event_ids=tuple(
        f'US.AAPL:{bar.timestamp.date().isoformat()}' for bar in bars
    ),
    event_start=bars[0].timestamp, event_end=bars[-1].timestamp,
    session_date=bars[0].timestamp.date(), provider_available_at=None,
    received_at=t0 + timedelta(days=3), ingested_at=t0 + timedelta(days=3),
    provider_version='fixture-v1', adapter_version='fixture-adapter-v1',
    schema_version='fixture-bars-v1', source_rights_id='fixture-test-data',
    entitlement=EntitlementState.NOT_REQUIRED, provenance=ProvenanceClass.FIXTURE,
)
job = CollectionJob(
    provider_id='fixture-moomoo', endpoints=('fixture://aapl-daily',),
    source_request_ids=('restart-proof',),
    canonical_instruments=(CanonicalInstrumentId(value='moomoo:US:AAPL:XNAS'),),
    data_kinds=(DataKind.BARS,), intervals=('1d',),
    calendar_version=XNYS_REGULAR_VERSION, session_policy=SessionPolicy.REGULAR,
    window_start=bars[0].timestamp, window_end=bars[-1].timestamp,
    adjustment_policy=UNADJUSTED_IDENTITY.policy_id,
    schema_versions=('fixture-bars-v1',),
    mapping_version=InstrumentCatalog.bounded_default().catalog_id,
    code_commit='3' * 40,
)
coordinator = CollectionCoordinator(store)
try:
    if coordinator.source(job) is None:
        coordinator.capture_source(
            job, media_type='application/test-source', payload=payload,
            raw_payloads=(payload,),
        )
    def produce(staging):
        result = FabricPublisher(staging, code_commit='3' * 40).publish_bars(
            envelope, bars, adjustment_policy=UNADJUSTED_IDENTITY,
            feature_specs=(FabricFeatureSpec(name='log_return', window=2),),
        )
        return (
            result.raw_id, result.normalized_id,
            result.adjusted_id, result.feature_id,
        )
    result = coordinator.run(
        job, producer=produce, provider_cursor='cursor',
        last_complete_source_event=bars[-1].timestamp.isoformat(),
        updated_at=t0 + timedelta(days=3), crash_after=stage,
    )
except InjectedCrash:
    print('CRASH')
except ConcurrentWriterError:
    print('BUSY')
else:
    print('OK:' + ','.join(result.manifest_ids))
'''


def _bars() -> list[Bar]:
    return [
        Bar(
            instrument=AAPL,
            timestamp=T0 + timedelta(days=index),
            interval="1d",
            open=close,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=1_000.0 + index,
        )
        for index, close in enumerate((100.0, 101.0, 102.0))
    ]


def _envelope(
    store: ManifestStore,
    *,
    bars: list[Bar] | None = None,
    request_id: str = "request-2026-08-14",
    received_at: datetime = T0 + timedelta(days=3),
) -> RawEnvelope:
    bars = _bars() if bars is None else bars
    payload = json.dumps(
        [bar.model_dump(mode="json") for bar in bars],
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return RawEnvelope.capture(
        objects=store.objects,
        payload=payload,
        content_type="application/json",
        provider_id="fixture-moomoo",
        endpoint="fixture://aapl-daily",
        request_id=request_id,
        request_window_start=bars[0].timestamp,
        request_window_end=bars[-1].timestamp,
        cursor=None,
        canonical_instrument=CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
        provider_symbol="US.AAPL",
        data_kind=DataKind.BARS,
        source_event_ids=tuple(
            f"US.AAPL:{bar.timestamp.date().isoformat()}" for bar in bars
        ),
        event_start=bars[0].timestamp,
        event_end=bars[-1].timestamp,
        session_date=date(2026, 8, 12),
        provider_available_at=None,
        received_at=received_at,
        ingested_at=received_at,
        provider_version="fixture-v1",
        adapter_version="fixture-adapter-v1",
        schema_version="fixture-bars-v1",
        source_rights_id="fixture-test-data",
        entitlement=EntitlementState.NOT_REQUIRED,
        provenance=ProvenanceClass.FIXTURE,
    )


def _job(*, request_id: str = "request-2026-08-14") -> CollectionJob:
    return CollectionJob(
        provider_id="fixture-moomoo",
        endpoints=("fixture://aapl-daily",),
        source_request_ids=(request_id,),
        canonical_instruments=(
            CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
        ),
        data_kinds=(DataKind.BARS,),
        intervals=("1d",),
        calendar_version=XNYS_REGULAR_VERSION,
        session_policy=SessionPolicy.REGULAR,
        window_start=T0,
        window_end=T0 + timedelta(days=2),
        adjustment_policy="unadjusted-identity-v1",
        schema_versions=("fixture-bars-v1",),
        mapping_version=InstrumentCatalog.bounded_default().catalog_id,
        code_commit="3" * 40,
    )


def _producer(store: ManifestStore, envelope: RawEnvelope, calls: list[int]):
    def produce(staging: StagingManifestStore) -> tuple[str, ...]:
        calls.append(1)
        publication = FabricPublisher(staging, code_commit="3" * 40).publish_bars(
            envelope,
            _bars(),
            adjustment_policy=UNADJUSTED_IDENTITY,
            feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
        )
        return (
            publication.raw_id,
            publication.normalized_id,
            publication.adjusted_id,
            publication.feature_id,
        )

    return produce


@pytest.mark.parametrize("stage", list(PublicationStage))
def test_retry_after_every_graph_boundary_is_idempotent(
    tmp_path: Path, stage: PublicationStage
) -> None:
    store = ManifestStore(tmp_path)
    envelope = _envelope(store)
    calls: list[int] = []
    coordinator = CollectionCoordinator(store)
    arguments = {
        "producer": _producer(store, envelope, calls),
        "provider_cursor": "US.AAPL:2026-08-14",
        "last_complete_source_event": "US.AAPL:2026-08-14",
        "updated_at": T0 + timedelta(days=3),
    }

    with pytest.raises(InjectedCrash, match=stage.value):
        coordinator.run(_job(), crash_after=stage, **arguments)
    if stage is PublicationStage.COMMIT:
        assert all(store.current(dataset) is not None for dataset in DATASETS)
    else:
        assert all(store.current(dataset) is None for dataset in DATASETS)

    publication = coordinator.run(_job(), **arguments)
    assert publication.quality_report_id is None
    assert len(publication.manifest_ids) == 4
    assert [store.open(item).manifest.layer for item in publication.manifest_ids] == list(
        ArtifactLayer
    )
    assert all(store.current(dataset) is not None for dataset in DATASETS)
    if stage in {PublicationStage.MANIFEST, PublicationStage.PREFLIGHT, PublicationStage.COMMIT}:
        assert len(calls) == 1
    else:
        assert len(calls) == 2


def test_completed_checkpoint_fails_closed_when_preflight_disappears(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    envelope = _envelope(store)
    coordinator = CollectionCoordinator(store)
    publication = coordinator.run(
        _job(),
        producer=_producer(store, envelope, []),
        provider_cursor="US.AAPL:2026-08-14",
        last_complete_source_event="US.AAPL:2026-08-14",
        updated_at=T0 + timedelta(days=3),
    )
    path = (
        tmp_path
        / FABRIC_NAMESPACE
        / "objects"
        / "sha256"
        / publication.preflight_id[:2]
        / publication.preflight_id
    )
    path.unlink()

    with pytest.raises(ValueError, match="preflight object is missing"):
        coordinator.run(
            _job(),
            producer=lambda _store: (_ for _ in ()).throw(
                AssertionError("completed jobs must not recollect")
            ),
            provider_cursor="ignored",
            last_complete_source_event="ignored",
            updated_at=T0 + timedelta(days=4),
        )


def test_every_manifest_is_bound_to_the_deterministic_collection_run(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    publication = CollectionCoordinator(store).run(
        _job(),
        producer=_producer(store, _envelope(store), []),
        provider_cursor="cursor",
        last_complete_source_event="event",
        updated_at=T0 + timedelta(days=3),
    )

    assert {
        store.open(manifest_id).manifest.collection_run_id
        for manifest_id in publication.manifest_ids
    } == {publication.run_id}


def test_completed_job_retry_returns_historical_identity_after_newer_job(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    coordinator = CollectionCoordinator(store)
    first_job = _job()
    first_envelope = _envelope(store)
    first = coordinator.run(
        first_job,
        producer=_producer(store, first_envelope, []),
        provider_cursor="cursor-1",
        last_complete_source_event="event-1",
        updated_at=T0 + timedelta(days=3),
    )
    second_job = _job(request_id="request-2026-08-15")
    second_envelope = _envelope(
        store,
        request_id="request-2026-08-15",
        received_at=T0 + timedelta(days=4),
    )
    second = coordinator.run(
        second_job,
        producer=_producer(store, second_envelope, []),
        provider_cursor="cursor-2",
        last_complete_source_event="event-2",
        updated_at=T0 + timedelta(days=4),
    )
    assert first.manifest_ids != second.manifest_ids

    retried = coordinator.run(
        first_job,
        producer=lambda _store: (_ for _ in ()).throw(
            AssertionError("completed historical jobs must not recollect")
        ),
        provider_cursor="ignored",
        last_complete_source_event="ignored",
        updated_at=T0 + timedelta(days=5),
    )

    assert retried == first


def test_changed_content_after_raw_crash_is_quarantined(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    envelope = _envelope(store)
    coordinator = CollectionCoordinator(store)
    arguments = {
        "provider_cursor": "US.AAPL:2026-08-14",
        "last_complete_source_event": "US.AAPL:2026-08-14",
        "updated_at": T0 + timedelta(days=3),
    }
    coordinator.capture_source(
        _job(),
        media_type="application/test-source",
        payload=b"original",
        raw_payloads=(store.objects.get_bytes(envelope.raw_object),),
    )
    with pytest.raises(InjectedCrash, match="raw"):
        coordinator.run(
            _job(),
            producer=_producer(store, envelope, []),
            crash_after=PublicationStage.RAW,
            **arguments,
        )

    with pytest.raises(CheckpointConflictError, match="source bytes changed"):
        coordinator.capture_source(
            _job(),
            media_type="application/test-source",
            payload=b"changed",
            raw_payloads=(store.objects.get_bytes(envelope.raw_object),),
        )

    records = coordinator.checkpoints.quarantined(_job().job_id)
    assert len(records) == 1
    evidence = json.loads(records[0])
    assert evidence["contract"] == "source-snapshot-conflict-v1"
    assert evidence["expected"]["digest"] != evidence["observed"]["digest"]


def test_saved_source_snapshot_must_bind_the_raw_envelope_bytes(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    envelope = _envelope(store)
    coordinator = CollectionCoordinator(store)
    coordinator.capture_source(
        _job(),
        media_type="application/test-source",
        payload=b"aggregate batch",
        raw_payloads=(b"different raw response",),
    )

    with pytest.raises(ValueError, match="source snapshot.*raw envelope"):
        coordinator.run(
            _job(),
            producer=_producer(store, envelope, []),
            provider_cursor="cursor",
            last_complete_source_event="event",
            updated_at=T0 + timedelta(days=3),
        )


def test_source_snapshot_preserves_duplicate_payload_multiplicity(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    coordinator = CollectionCoordinator(store)
    coordinator.capture_source(
        _job(),
        media_type="application/test-source",
        payload=b"aggregate batch",
        raw_payloads=(b"same endpoint bytes", b"same endpoint bytes"),
    )

    snapshot = coordinator.checkpoints.source_snapshot(_job().job_id)
    assert snapshot is not None
    assert len(snapshot[3]) == 2
    assert snapshot[3][0] == snapshot[3][1]


def test_deleted_source_snapshot_row_recovers_without_provider_recontact(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    coordinator = CollectionCoordinator(store)
    payload = b"durable provider batch"
    coordinator.capture_source(
        _job(),
        media_type="application/test-source",
        payload=payload,
        raw_payloads=(b"raw provider response",),
    )
    database = (
        tmp_path
        / FABRIC_NAMESPACE
        / "control"
        / "collection-checkpoints.duckdb"
    )
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "DELETE FROM source_snapshots WHERE job_id = ?", [_job().job_id]
        )

    assert coordinator.has_state(_job()) is False
    assert coordinator.source(_job()) == payload


def test_self_consistent_source_snapshot_row_tampering_fails_closed(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    coordinator = CollectionCoordinator(store)
    coordinator.capture_source(
        _job(),
        media_type="application/test-source",
        payload=b"original aggregate",
        raw_payloads=(b"raw provider response",),
    )
    replacement = store.objects.put_bytes(
        "application/test-source", b"forged aggregate"
    )
    database = (
        tmp_path
        / FABRIC_NAMESPACE
        / "control"
        / "collection-checkpoints.duckdb"
    )
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            """
            UPDATE source_snapshots SET digest = ?, byte_length = ?
            WHERE job_id = ?
            """,
            [replacement.digest, replacement.byte_length, _job().job_id],
        )

    with pytest.raises(CheckpointIntegrityError, match="source snapshot rows"):
        coordinator.source(_job())


@pytest.mark.parametrize("damage", ["delete", "corrupt"])
def test_completed_retry_revalidates_aggregate_source_object(
    tmp_path: Path, damage: str
) -> None:
    store = ManifestStore(tmp_path)
    envelope = _envelope(store)
    coordinator = CollectionCoordinator(store)
    coordinator.capture_source(
        _job(),
        media_type="application/test-source",
        payload=b"aggregate distinct from endpoint payload",
        raw_payloads=(store.objects.get_bytes(envelope.raw_object),),
    )
    coordinator.run(
        _job(),
        producer=_producer(store, envelope, []),
        provider_cursor="cursor",
        last_complete_source_event="event",
        updated_at=T0 + timedelta(days=3),
    )
    snapshot = coordinator.checkpoints.source_snapshot(_job().job_id)
    assert snapshot is not None
    path = (
        tmp_path
        / FABRIC_NAMESPACE
        / "objects"
        / "sha256"
        / snapshot[1][:2]
        / snapshot[1]
    )
    if damage == "delete":
        path.unlink()
    else:
        path.write_bytes(b"corrupt")

    with pytest.raises(ValueError, match="object"):
        coordinator.run(
            _job(),
            producer=lambda _store: (_ for _ in ()).throw(
                AssertionError("completed retry must not recollect")
            ),
            provider_cursor="ignored",
            last_complete_source_event="ignored",
            updated_at=T0 + timedelta(days=4),
        )


def test_changed_manifest_after_raw_crash_is_quarantined(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    envelope = _envelope(store)
    coordinator = CollectionCoordinator(store)
    arguments = {
        "provider_cursor": "US.AAPL:2026-08-14",
        "last_complete_source_event": "US.AAPL:2026-08-14",
        "updated_at": T0 + timedelta(days=3),
    }
    with pytest.raises(InjectedCrash, match="raw"):
        coordinator.run(
            _job(),
            producer=_producer(store, envelope, []),
            crash_after=PublicationStage.RAW,
            **arguments,
        )

    def changed_code(staging: StagingManifestStore) -> tuple[str, ...]:
        publication = FabricPublisher(staging, code_commit="4" * 40).publish_bars(
            envelope,
            _bars(),
            adjustment_policy=UNADJUSTED_IDENTITY,
            feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
        )
        return (
            publication.raw_id,
            publication.normalized_id,
            publication.adjusted_id,
            publication.feature_id,
        )

    with pytest.raises(CheckpointConflictError, match="staged content changed"):
        coordinator.run(_job(), producer=changed_code, **arguments)

    records = coordinator.checkpoints.quarantined(_job().job_id)
    assert any(json.loads(item)["contract"] == "collection-conflict-v1" for item in records)


def test_job_window_cannot_commit_a_different_source_graph(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    envelope = _envelope(store)
    changed_job = _job().model_copy(
        update={"window_end": T0 + timedelta(days=3)}
    )

    with pytest.raises(ValueError, match="window disagrees"):
        CollectionCoordinator(store).run(
            changed_job,
            producer=_producer(store, envelope, []),
            provider_cursor="US.AAPL:2026-08-14",
            last_complete_source_event="US.AAPL:2026-08-14",
            updated_at=T0 + timedelta(days=3),
        )


def test_eight_concurrent_attempts_create_one_logical_graph(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    envelope = _envelope(store)

    def attempt() -> tuple[str, ...] | None:
        def delayed(staging: StagingManifestStore) -> tuple[str, ...]:
            time.sleep(0.1)
            return _producer(store, envelope, [])(staging)

        try:
            return CollectionCoordinator(store).run(
                _job(),
                producer=delayed,
                provider_cursor="US.AAPL:2026-08-14",
                last_complete_source_event="US.AAPL:2026-08-14",
                updated_at=T0 + timedelta(days=3),
            ).manifest_ids
        except ConcurrentWriterError:
            return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _index: attempt(), range(8)))

    completed = {item for item in outcomes if item is not None}
    assert len(completed) == 1
    assert all(store.current(dataset) is not None for dataset in DATASETS)


def test_pending_graph_reservation_fences_legacy_publication(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    first_envelope = _envelope(store)
    FabricPublisher(store, code_commit="3" * 40).publish_bars(
        first_envelope,
        _bars(),
        adjustment_policy=UNADJUSTED_IDENTITY,
        feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
    )
    pending_job = _job(request_id="request-2026-08-15")
    pending_envelope = _envelope(
        store,
        request_id="request-2026-08-15",
        received_at=T0 + timedelta(days=4),
    )
    coordinator = CollectionCoordinator(store)
    with pytest.raises(InjectedCrash, match="manifest"):
        coordinator.run(
            pending_job,
            producer=_producer(store, pending_envelope, []),
            provider_cursor="cursor",
            last_complete_source_event="event",
            updated_at=T0 + timedelta(days=4),
            crash_after=PublicationStage.MANIFEST,
        )
    assert coordinator.checkpoints.pending(pending_job.job_id) is not None
    conflicting_envelope = _envelope(
        store,
        request_id="request-2026-08-16",
        received_at=T0 + timedelta(days=5),
    )

    with pytest.raises(ManifestConflictError, match="reserved"):
        FabricPublisher(store, code_commit="3" * 40).publish_bars(
            conflicting_envelope,
            _bars(),
            adjustment_policy=UNADJUSTED_IDENTITY,
            feature_specs=(FabricFeatureSpec(name="log_return", window=2),),
        )


@pytest.mark.parametrize("stage", list(PublicationStage))
def test_process_restart_recovers_every_publication_stage(
    tmp_path: Path, stage: PublicationStage
) -> None:
    first = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_COORDINATOR, str(tmp_path), stage.value, "-"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    second = subprocess.run(
        [sys.executable, "-c", _SUBPROCESS_COORDINATOR, str(tmp_path), "-", "-"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert first.stdout.strip() == "CRASH"
    assert second.stdout.startswith("OK:")
    manifest_ids = tuple(second.stdout.strip().removeprefix("OK:").split(","))
    assert len(manifest_ids) == 4
    assert len(set(manifest_ids)) == 4
    store = ManifestStore(tmp_path)
    assert tuple(store.open(item).manifest.manifest_id for item in manifest_ids) == manifest_ids


def test_eight_process_coordinators_commit_one_complete_graph(tmp_path: Path) -> None:
    gate = tmp_path / "start-complete-coordinators"
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", _SUBPROCESS_COORDINATOR, str(tmp_path), "-", str(gate)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(8)
    ]
    gate.touch()
    results = [process.communicate(timeout=30) for process in processes]
    outcomes = [stdout.strip() for stdout, _stderr in results]

    assert any(item.startswith("OK:") for item in outcomes)
    assert all(item == "BUSY" or item.startswith("OK:") for item in outcomes)
    assert [process.returncode for process in processes] == [0] * 8
    successful_ids = {
        item.removeprefix("OK:") for item in outcomes if item.startswith("OK:")
    }
    assert len(successful_ids) == 1
    checkpoint_store = CollectionCoordinator(ManifestStore(tmp_path)).checkpoints
    with checkpoint_store._connect(read_only=True) as connection:
        assert connection.execute("SELECT COUNT(*) FROM graph_commits").fetchone()[0] == 1
