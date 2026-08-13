import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from quantmesh.data.artifacts import (
    ArtifactLayer,
    ArtifactManifest,
    ManifestConflictError,
    ManifestIntegrityError,
    ManifestStore,
)
from quantmesh.data.calendars import SessionPolicy
from quantmesh.data.capabilities import DataKind, EntitlementState
from quantmesh.data.instruments import CanonicalInstrumentId, InstrumentCatalog
from quantmesh.data.lake import Lake
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue

T0 = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
AAPL = Instrument(
    symbol="AAPL",
    venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY,
    currency="USD",
)
NVDA = Instrument(
    symbol="NVDA",
    venue=Venue.MOOMOO,
    instrument_type=InstrumentType.EQUITY,
    currency="USD",
)


def _instrument_bar(instrument: Instrument, close: float) -> Bar:
    return Bar(
        instrument=instrument,
        timestamp=T0,
        interval="1d",
        open=100.0,
        high=max(101.0, close),
        low=min(99.0, close),
        close=close,
        volume=1_000.0,
    )


def _bar(close: float) -> Bar:
    return _instrument_bar(AAPL, close)


def _payload(close: float) -> bytes:
    return json.dumps(
        [_bar(close).model_dump(mode="json")],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _manifest(store: ManifestStore, close: float, revision: int) -> ArtifactManifest:
    object_ref = store.objects.put_bytes("application/vnd.quantmesh.bars+json", _payload(close))
    knowledge_time = T0 + timedelta(seconds=revision - 1)
    return ArtifactManifest.build(
        dataset_id="aapl-daily",
        compatibility_revision=revision,
        layer=ArtifactLayer.NORMALIZED,
        canonical_instrument=CanonicalInstrumentId(value="moomoo:US:AAPL:XNAS"),
        instrument_catalog_id=InstrumentCatalog.bounded_default().catalog_id,
        data_kind=DataKind.BARS,
        interval="1d",
        calendar_version="exchange-calendars:4.13.2:XNYS",
        session_policy=SessionPolicy.REGULAR,
        objects=(object_ref,),
        row_identities=(f"AAPL:{T0.isoformat()}",),
        schema_digest="1" * 64,
        adapter_version="moomoo-v1",
        parent_manifest_ids=(),
        transformation_policy_digest="2" * 64,
        source_rights_id="moomoo-operator-entitlement",
        entitlement=EntitlementState.AVAILABLE,
        event_start=T0,
        event_end=T0,
        knowledge_start=knowledge_time,
        knowledge_end=knowledge_time,
        adjustment_policy=None,
        quality_report_id=None,
        created_at=knowledge_time,
        code_commit="3" * 40,
        collection_run_id="run-20260814",
    )


def test_same_range_content_change_has_a_new_manifest_id(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    second = _manifest(store, close=101.0, revision=2)
    store.publish(second, expected_current=first.manifest_id)

    assert first.event_start == second.event_start
    assert first.event_end == second.event_end
    assert first.manifest_id != second.manifest_id
    assert store.open(first.manifest_id).read_bytes() != store.open(second.manifest_id).read_bytes()


def test_open_reader_is_stable_after_new_publication(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    reader = store.open(first.manifest_id)

    second = _manifest(store, close=101.0, revision=2)
    store.publish(second, expected_current=first.manifest_id)

    assert reader.read_bars()[0].close == 100.0
    assert store.open(second.manifest_id).read_bars()[0].close == 101.0


def test_publish_rejects_stale_compare_and_swap(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    second = _manifest(store, close=101.0, revision=2)

    with pytest.raises(ManifestConflictError, match="expected current"):
        store.publish(second, expected_current="f" * 64)


def test_current_pointer_rejects_rollback(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    second = _manifest(store, close=101.0, revision=2)
    store.publish(second, expected_current=first.manifest_id)

    with pytest.raises(ManifestConflictError, match="rollback"):
        store.point_current(first.manifest_id, expected_current=second.manifest_id)


def test_restored_old_pointer_cannot_reuse_a_revision(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    pointer = tmp_path / ".trusted-data-v2" / "datasets" / first.dataset_id / "current.json"
    old_pointer = pointer.read_bytes()
    second = _manifest(store, close=101.0, revision=2)
    store.publish(second, expected_current=first.manifest_id)
    pointer.write_bytes(old_pointer)

    reused_revision = _manifest(store, close=102.0, revision=2)
    with pytest.raises(ManifestConflictError, match="already belongs"):
        store.publish(reused_revision, expected_current=first.manifest_id)


def test_deleted_latest_manifest_and_restored_pointer_cannot_reuse_revision(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    pointer = tmp_path / ".trusted-data-v2" / "datasets" / first.dataset_id / "current.json"
    old_pointer = pointer.read_bytes()
    second = _manifest(store, close=101.0, revision=2)
    store.publish(second, expected_current=first.manifest_id)
    store.manifest_path(second.dataset_id, second.manifest_id).unlink()
    reservation = (
        tmp_path
        / ".trusted-data-v2"
        / "datasets"
        / second.dataset_id
        / "revisions"
        / f"{second.compatibility_revision:020d}.json"
    )
    reservation.unlink()
    pointer.write_bytes(old_pointer)

    replacement = _manifest(store, close=102.0, revision=2)
    with pytest.raises(ManifestConflictError, match="already belongs"):
        store.publish(replacement, expected_current=first.manifest_id)


def test_exact_retry_repairs_only_an_uncommitted_torn_history_tail(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    second = _manifest(store, close=101.0, revision=2)
    history = store._history_path(first.dataset_id)
    first_record = json.loads(history.read_bytes().splitlines()[0])
    next_record = store._history_record_bytes(
        second,
        previous_digest=first_record["history_digest"],
    )
    identity_end = next_record.index(second.manifest_id.encode("ascii")) + len(second.manifest_id)
    with history.open("ab") as handle:
        handle.write(next_record[:identity_end])

    store.publish(second, expected_current=first.manifest_id)

    assert store.open(second.manifest_id).read_bars()[0].close == 101.0


def test_different_manifest_cannot_hijack_a_torn_history_tail(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    intended = _manifest(store, close=101.0, revision=2)
    replacement = _manifest(store, close=102.0, revision=2)
    history = store._history_path(first.dataset_id)
    first_record = json.loads(history.read_bytes().splitlines()[0])
    intended_record = store._history_record_bytes(
        intended,
        previous_digest=first_record["history_digest"],
    )
    with history.open("ab") as handle:
        handle.write(intended_record[: len(intended_record) // 2])
    before = history.read_bytes()

    with pytest.raises(ManifestIntegrityError, match="does not belong"):
        store.publish(replacement, expected_current=first.manifest_id)

    assert history.read_bytes() == before


def test_common_one_byte_history_tail_cannot_bind_a_different_manifest(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    intended = _manifest(store, close=101.0, revision=2)
    replacement = _manifest(store, close=102.0, revision=2)
    history = store._history_path(first.dataset_id)
    first_record = json.loads(history.read_bytes().splitlines()[0])
    intended_record = store._history_record_bytes(
        intended,
        previous_digest=first_record["history_digest"],
    )
    with history.open("ab") as handle:
        handle.write(intended_record[:1])
    before = history.read_bytes()

    with pytest.raises(ManifestIntegrityError, match="authenticated manifest identity"):
        store.publish(replacement, expected_current=first.manifest_id)

    assert history.read_bytes() == before


def test_torn_history_repair_validates_expected_current_before_mutation(
    tmp_path: Path,
) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    second = _manifest(store, close=101.0, revision=2)
    history = store._history_path(first.dataset_id)
    first_record = json.loads(history.read_bytes().splitlines()[0])
    next_record = store._history_record_bytes(
        second,
        previous_digest=first_record["history_digest"],
    )
    with history.open("ab") as handle:
        handle.write(next_record[: len(next_record) // 2])
    before = history.read_bytes()

    with pytest.raises(ManifestConflictError, match="expected current"):
        store.publish(second, expected_current="f" * 64)

    assert history.read_bytes() == before


def test_torn_committed_history_record_fails_closed(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    second = _manifest(store, close=101.0, revision=2)
    store.publish(second, expected_current=first.manifest_id)
    history = store._history_path(first.dataset_id)
    records = history.read_bytes().splitlines(keepends=True)
    history.write_bytes(records[0] + records[1][: len(records[1]) // 2])
    third = _manifest(store, close=102.0, revision=3)

    with pytest.raises(ManifestIntegrityError, match="committed pointer revision"):
        store.publish(third, expected_current=second.manifest_id)


def test_publish_retry_completes_manifest_pointer_crash_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    second = _manifest(store, close=101.0, revision=2)

    def crash_before_pointer(_manifest: ArtifactManifest) -> None:
        raise RuntimeError("simulated crash")

    with monkeypatch.context() as patch:
        patch.setattr(store, "_write_pointer", crash_before_pointer)
        with pytest.raises(RuntimeError, match="simulated crash"):
            store.publish(second, expected_current=first.manifest_id)

    recovered = ManifestStore(tmp_path)
    recovered.publish(second, expected_current=first.manifest_id)

    assert recovered.open(second.manifest_id).read_bars()[0].close == 101.0


def test_publish_retry_recovers_before_atomic_genesis_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)

    def crash_before_activation(_staged: Path, _target: Path) -> None:
        raise RuntimeError("simulated genesis crash")

    with monkeypatch.context() as patch:
        patch.setattr(store, "_activate_genesis", crash_before_activation)
        with pytest.raises(RuntimeError, match="simulated genesis crash"):
            store.publish(first, expected_current=None)

    recovered = ManifestStore(tmp_path)
    recovered.publish(first, expected_current=None)

    pointer = tmp_path / ".trusted-data-v2" / "datasets" / first.dataset_id / "current.json"
    assert json.loads(pointer.read_text(encoding="utf-8"))["manifest_id"] == first.manifest_id


def test_point_current_is_idempotent_after_atomic_genesis_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    activate = store._activate_genesis

    def crash_after_activation(staged: Path, target: Path) -> None:
        activate(staged, target)
        raise RuntimeError("simulated genesis crash")

    with monkeypatch.context() as patch:
        patch.setattr(store, "_activate_genesis", crash_after_activation)
        with pytest.raises(RuntimeError, match="simulated genesis crash"):
            store.publish(first, expected_current=None)

    recovered = ManifestStore(tmp_path)
    recovered.point_current(first.manifest_id, expected_current=None)

    assert recovered.open(first.manifest_id).read_bars()[0].close == 100.0


def test_boolean_pointer_revision_is_not_an_integer(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    pointer = tmp_path / ".trusted-data-v2" / "datasets" / first.dataset_id / "current.json"
    pointer.write_bytes(
        json.dumps(
            {
                "compatibility_revision": True,
                "dataset_id": first.dataset_id,
                "manifest_id": first.manifest_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )

    second = _manifest(store, close=101.0, revision=2)
    with pytest.raises(ManifestIntegrityError, match="revision is invalid"):
        store.publish(second, expected_current=first.manifest_id)


def test_forged_initialization_markers_fail_closed(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    forged = json.dumps(
        {"dataset_id": first.dataset_id, "manifest_id": "f" * 64},
        sort_keys=True,
        separators=(",", ":"),
    )
    dataset_dir = tmp_path / ".trusted-data-v2" / "datasets" / first.dataset_id
    (dataset_dir / "genesis.json").write_text(forged, encoding="utf-8")
    (dataset_dir / "initialized.json").write_text(forged, encoding="utf-8")

    second = _manifest(store, close=101.0, revision=2)
    with pytest.raises(ManifestIntegrityError, match="revision 1"):
        store.publish(second, expected_current=first.manifest_id)


def test_deleted_current_pointer_cannot_reset_revision_history(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    dataset_dir = tmp_path / ".trusted-data-v2" / "datasets" / first.dataset_id
    pointer = dataset_dir / "current.json"
    pointer.unlink()
    (dataset_dir / "initialized.json").unlink()

    replacement = _manifest(store, close=101.0, revision=1)
    with pytest.raises(ManifestConflictError, match="deletion reset"):
        store.publish(replacement, expected_current=None)


def test_manifest_read_detects_tampering(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    manifest = _manifest(store, close=100.0, revision=1)
    store.publish(manifest, expected_current=None)
    path = store.manifest_path(manifest.dataset_id, manifest.manifest_id)
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    with pytest.raises(ManifestIntegrityError, match="canonical bytes"):
        store.open(manifest.manifest_id)


def test_normalized_manifest_rejects_bar_instrument_mismatch(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    template = _manifest(store, close=100.0, revision=1)
    payload = json.dumps(
        [_instrument_bar(NVDA, 100.0).model_dump(mode="json")],
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    reference = store.objects.put_bytes("application/vnd.quantmesh.bars+json", payload)
    values = template.model_dump(exclude={"manifest_id", "objects", "row_identities"})
    values.update(
        objects=(reference,),
        row_identities=(f"NVDA:{T0.isoformat()}",),
    )
    mismatched = ArtifactManifest.build(**values)

    with pytest.raises(ManifestIntegrityError, match="canonical instrument"):
        store.publish(mismatched, expected_current=None)


def test_equity_manifest_rejects_continuous_calendar(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    template = _manifest(store, close=100.0, revision=1)
    values = template.model_dump(exclude={"manifest_id"})
    values.update(
        calendar_version="quantmesh:1:24/7",
        session_policy=SessionPolicy.CONTINUOUS,
    )

    with pytest.raises(ValueError, match="calendar and session policy"):
        ArtifactManifest.build(**values)


def test_current_pointer_detects_tampering(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    manifest = _manifest(store, close=100.0, revision=1)
    store.publish(manifest, expected_current=None)
    pointer = tmp_path / ".trusted-data-v2" / "datasets" / manifest.dataset_id / "current.json"
    pointer.write_text(pointer.read_text(encoding="utf-8") + " ", encoding="utf-8")

    next_manifest = _manifest(store, close=101.0, revision=2)
    with pytest.raises(ManifestIntegrityError, match="canonical bytes"):
        store.publish(next_manifest, expected_current=manifest.manifest_id)


def test_concurrent_publication_has_one_cas_winner(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    contenders = (
        _manifest(store, close=101.0, revision=2),
        _manifest(store, close=102.0, revision=2),
    )

    def publish(manifest: ArtifactManifest) -> str:
        store.publish(manifest, expected_current=first.manifest_id)
        return manifest.manifest_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(publish, manifest) for manifest in contenders]
    winners = [future.result() for future in futures if future.exception() is None]
    conflicts = [future.exception() for future in futures if future.exception() is not None]

    assert len(winners) == 1
    assert len(conflicts) == 1
    assert isinstance(conflicts[0], ManifestConflictError)
    assert store.open(winners[0]).manifest.compatibility_revision == 2


def test_cross_process_publication_has_one_cas_winner(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    first = _manifest(store, close=100.0, revision=1)
    store.publish(first, expected_current=None)
    contenders = (
        _manifest(store, close=101.0, revision=2),
        _manifest(store, close=102.0, revision=2),
    )
    gate = tmp_path / "start-publication"
    script = """
import sys
import time
from pathlib import Path
from quantmesh.data.artifacts import ArtifactManifest, ManifestConflictError, ManifestStore

root, manifest_json, expected_current, gate_path = sys.argv[1:]
while not Path(gate_path).exists():
    time.sleep(0.005)
try:
    ManifestStore(Path(root)).publish(
        ArtifactManifest.model_validate_json(manifest_json),
        expected_current=expected_current,
    )
except ManifestConflictError:
    print("CONFLICT")
else:
    print("OK")
"""
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                script,
                str(tmp_path),
                contender.canonical_bytes().decode("utf-8"),
                first.manifest_id,
                str(gate),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for contender in contenders
    ]
    gate.touch()
    results = [process.communicate(timeout=20) for process in processes]

    assert sorted(stdout.strip() for stdout, _ in results) == ["CONFLICT", "OK"]
    assert [process.returncode for process in processes] == [0, 0]


def test_lake_v2_accessor_does_not_change_v1_dataset_api(tmp_path: Path) -> None:
    lake = Lake(tmp_path)

    assert isinstance(lake.artifact_store(), ManifestStore)
    assert lake.artifact_store().root == tmp_path
    assert callable(lake.dataset)


def test_lock_hard_link_is_rejected_before_external_file_mutation(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    manifest = _manifest(store, close=100.0, revision=1)
    external = tmp_path / "external-lock-target"
    external.write_bytes(b"")
    lock = store._lock_path(manifest.dataset_id)
    lock.parent.mkdir(parents=True)
    os.link(external, lock)

    with pytest.raises(ManifestIntegrityError, match="hard links"):
        store.publish(manifest, expected_current=None)

    assert external.read_bytes() == b""
