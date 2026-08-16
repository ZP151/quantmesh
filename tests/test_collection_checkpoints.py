import json
import os
import subprocess
import sys
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest

import quantmesh.data.checkpoints as checkpoint_module
from quantmesh.data.checkpoints import (
    CheckpointConflictError,
    CheckpointIntegrityError,
    CheckpointStore,
    CollectionCheckpoint,
    ConcurrentWriterError,
    GraphAdvance,
    committed_current,
    committed_history,
    reserved_job,
)

JOB_ID = "a" * 64
RUN_ID = "b" * 64
COMMIT_ID = "c" * 64
PREFLIGHT_ID = "d" * 64
MANIFEST_1 = "e" * 64
MANIFEST_2 = "f" * 64
KNOWLEDGE_1 = datetime(2026, 8, 14, 1, tzinfo=UTC)
KNOWLEDGE_2 = datetime(2026, 8, 14, 2, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _isolate_graph_journal_contract_from_quality_closure(monkeypatch) -> None:
    """These synthetic digest tests exercise journal mechanics, not data closure."""
    monkeypatch.setattr(
        checkpoint_module,
        "_verify_committed_quality_evidence",
        lambda *args, **kwargs: None,
    )

_PRELINK_CRASH = r"""
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import quantmesh.data.checkpoints as checkpoints
from quantmesh.data.checkpoints import CheckpointStore, CollectionCheckpoint

root = Path(sys.argv[1])
fail_on = int(sys.argv[2])
calls = 0
original = os.link

def crashing_link(source, target):
    global calls
    calls += 1
    if calls == fail_on:
        os._exit(17)
    return original(source, target)

checkpoints.os.link = crashing_link
checkpoint = CollectionCheckpoint(
    job_id='a' * 64, generation=1, provider_cursor='cursor-1',
    last_complete_source_event='event-1', raw_object_digests=('1' * 64,),
    manifest_ids=('e' * 64,), preflight_id='d' * 64,
    quality_report_id=None, run_id='b' * 64, attempt=1,
    updated_at=datetime(2026, 8, 14, 1, tzinfo=UTC),
)
with CheckpointStore(root) as store:
    with store.writer():
        store.commit(
            previous=None, next_checkpoint=checkpoint, advances=(),
            commit_id='c' * 64,
        )
"""

_POSTLINK_INTENT_CRASH = _PRELINK_CRASH.replace(
    "    if calls == fail_on:\n        os._exit(17)\n    return original(source, target)",
    "    result = original(source, target)\n"
    "    if calls == fail_on:\n        os._exit(17)\n    return result",
)


def _checkpoint(generation: int, *, attempt: int | None = None) -> CollectionCheckpoint:
    return CollectionCheckpoint(
        job_id=JOB_ID,
        generation=generation,
        provider_cursor=f"cursor-{generation}",
        last_complete_source_event=f"event-{generation}",
        raw_object_digests=("1" * 64,),
        manifest_ids=(MANIFEST_1 if generation == 1 else MANIFEST_2,),
        preflight_id=PREFLIGHT_ID,
        quality_report_id=None,
        run_id=RUN_ID,
        attempt=attempt or generation,
        updated_at=datetime(2026, 8, 14, generation, tzinfo=UTC),
    )


def test_graph_commit_atomically_advances_checkpoint_current_and_history(
    tmp_path: Path,
) -> None:
    first = _checkpoint(1)
    with CheckpointStore(tmp_path) as store:
        with store.writer():
            store.commit(
                previous=None,
                next_checkpoint=first,
                advances=(
                    GraphAdvance(
                        dataset_id="btc-raw",
                        expected_current=None,
                        expected_revision=0,
                        expected_knowledge_end=None,
                        manifest_id=MANIFEST_1,
                        revision=1,
                        knowledge_start=KNOWLEDGE_1,
                        knowledge_end=KNOWLEDGE_1,
                    ),
                ),
                commit_id=COMMIT_ID,
            )

    assert committed_current(tmp_path, "btc-raw") == MANIFEST_1
    assert committed_history(tmp_path, "btc-raw") == (MANIFEST_1,)
    with CheckpointStore(tmp_path) as reopened:
        assert reopened.get(JOB_ID) == first


def test_graph_commit_is_cas_for_checkpoint_and_each_dataset(tmp_path: Path) -> None:
    first = _checkpoint(1)
    with CheckpointStore(tmp_path) as store:
        with store.writer():
            store.commit(
                previous=None,
                next_checkpoint=first,
                advances=(
                    GraphAdvance(
                        dataset_id="btc-raw",
                        expected_current=None,
                        expected_revision=0,
                        expected_knowledge_end=None,
                        manifest_id=MANIFEST_1,
                        revision=1,
                        knowledge_start=KNOWLEDGE_1,
                        knowledge_end=KNOWLEDGE_1,
                    ),
                ),
                commit_id=COMMIT_ID,
            )
        with store.writer():
            with pytest.raises(CheckpointConflictError, match="checkpoint"):
                store.commit(
                    previous=None,
                    next_checkpoint=_checkpoint(2),
                    advances=(),
                    commit_id="2" * 64,
                )
        with store.writer():
            with pytest.raises(CheckpointConflictError, match="btc-raw"):
                store.commit(
                    previous=first,
                    next_checkpoint=_checkpoint(2),
                    advances=(
                        GraphAdvance(
                            dataset_id="btc-raw",
                            expected_current=None,
                            expected_revision=0,
                            expected_knowledge_end=None,
                            manifest_id=MANIFEST_2,
                            revision=1,
                            knowledge_start=KNOWLEDGE_1,
                            knowledge_end=KNOWLEDGE_1,
                        ),
                    ),
                    commit_id="3" * 64,
                )

    assert committed_current(tmp_path, "btc-raw") == MANIFEST_1


def test_multi_dataset_commit_rolls_back_every_mapping_on_one_lost_cas(
    tmp_path: Path,
) -> None:
    first = _checkpoint(1)
    genesis = (
        GraphAdvance(
            dataset_id=dataset,
            expected_current=None,
            expected_revision=0,
            expected_knowledge_end=None,
            manifest_id=MANIFEST_1,
            revision=1,
            knowledge_start=KNOWLEDGE_1,
            knowledge_end=KNOWLEDGE_1,
        )
        for dataset in ("btc-raw", "btc-normalized")
    )
    with CheckpointStore(tmp_path) as store:
        with store.writer():
            store.commit(
                previous=None,
                next_checkpoint=first,
                advances=tuple(genesis),
                commit_id=COMMIT_ID,
            )
        with store.writer():
            with pytest.raises(CheckpointConflictError, match="btc-normalized"):
                store.commit(
                    previous=first,
                    next_checkpoint=_checkpoint(2),
                    advances=(
                        GraphAdvance(
                            dataset_id="btc-raw",
                            expected_current=MANIFEST_1,
                            expected_revision=1,
                            expected_knowledge_end=KNOWLEDGE_1,
                            manifest_id=MANIFEST_2,
                            revision=2,
                            knowledge_start=KNOWLEDGE_2,
                            knowledge_end=KNOWLEDGE_2,
                        ),
                        GraphAdvance(
                            dataset_id="btc-normalized",
                            expected_current="0" * 64,
                            expected_revision=1,
                            expected_knowledge_end=KNOWLEDGE_1,
                            manifest_id=MANIFEST_2,
                            revision=2,
                            knowledge_start=KNOWLEDGE_2,
                            knowledge_end=KNOWLEDGE_2,
                        ),
                    ),
                    commit_id="2" * 64,
                )

    assert committed_current(tmp_path, "btc-raw") == MANIFEST_1
    assert committed_current(tmp_path, "btc-normalized") == MANIFEST_1
    with CheckpointStore(tmp_path) as reopened:
        assert reopened.get(JOB_ID) == first


def test_graph_advance_rejects_nonforward_knowledge_time() -> None:
    with pytest.raises(ValueError, match="knowledge time must advance"):
        GraphAdvance(
            dataset_id="btc-raw",
            expected_current=MANIFEST_1,
            expected_revision=1,
            expected_knowledge_end=KNOWLEDGE_1,
            manifest_id=MANIFEST_2,
            revision=2,
            knowledge_start=KNOWLEDGE_1,
            knowledge_end=KNOWLEDGE_2,
        )


def test_committed_transaction_repairs_its_durable_intent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = _checkpoint(1)
    with CheckpointStore(tmp_path) as store:
        original = store._write_journal_file

        def interrupt_committed_marker(path: Path, payload: bytes) -> None:
            if path.parent.name == "graph-commits":
                raise RuntimeError("simulated process loss before committed marker")
            original(path, payload)

        monkeypatch.setattr(store, "_write_journal_file", interrupt_committed_marker)
        with store.writer(), pytest.raises(RuntimeError, match="process loss"):
            store.commit(
                previous=None,
                next_checkpoint=checkpoint,
                advances=(
                    GraphAdvance(
                        dataset_id="btc-raw",
                        expected_current=None,
                        expected_revision=0,
                        expected_knowledge_end=None,
                        manifest_id=MANIFEST_1,
                        revision=1,
                        knowledge_start=KNOWLEDGE_1,
                        knowledge_end=KNOWLEDGE_1,
                    ),
                ),
                commit_id=COMMIT_ID,
            )

        with pytest.raises(CheckpointIntegrityError, match="journal set"):
            committed_current(tmp_path, "btc-raw")
        monkeypatch.setattr(store, "_write_journal_file", original)
        with store.writer():
            store.repair_commit_journals()

    assert committed_current(tmp_path, "btc-raw") == MANIFEST_1


def test_uncommitted_intent_is_removed_before_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = _checkpoint(1)
    advance = GraphAdvance(
        dataset_id="btc-raw",
        expected_current=None,
        expected_revision=0,
        expected_knowledge_end=None,
        manifest_id=MANIFEST_1,
        revision=1,
        knowledge_start=KNOWLEDGE_1,
        knowledge_end=KNOWLEDGE_1,
    )
    with CheckpointStore(tmp_path) as store:
        original = store._advance_dataset
        monkeypatch.setattr(
            store,
            "_advance_dataset",
            lambda *_args: (_ for _ in ()).throw(RuntimeError("lost CAS")),
        )
        with store.writer(), pytest.raises(RuntimeError, match="lost CAS"):
            store.commit(
                previous=None,
                next_checkpoint=checkpoint,
                advances=(advance,),
                commit_id=COMMIT_ID,
            )
        monkeypatch.setattr(store, "_advance_dataset", original)
        with store.writer():
            store.repair_commit_journals()
            store.commit(
                previous=None,
                next_checkpoint=checkpoint,
                advances=(advance,),
                commit_id=COMMIT_ID,
            )

    assert committed_current(tmp_path, "btc-raw") == MANIFEST_1


def test_commit_journal_recovers_a_deleted_checkpoint_row(tmp_path: Path) -> None:
    checkpoint = _checkpoint(1)
    with CheckpointStore(tmp_path) as store:
        with store.writer():
            store.commit(
                previous=None,
                next_checkpoint=checkpoint,
                advances=(
                    GraphAdvance(
                        dataset_id="btc-raw",
                        expected_current=None,
                        expected_revision=0,
                        expected_knowledge_end=None,
                        manifest_id=MANIFEST_1,
                        revision=1,
                        knowledge_start=KNOWLEDGE_1,
                        knowledge_end=KNOWLEDGE_1,
                    ),
                ),
                commit_id=COMMIT_ID,
            )
        with store._connect() as connection:
            connection.execute(
                "DELETE FROM collection_checkpoints WHERE job_id = ?", [JOB_ID]
            )
        with pytest.raises(CheckpointIntegrityError, match="checkpoint rows"):
            committed_current(tmp_path, "btc-raw")
        with store.writer():
            store.repair_commit_journals()

        assert store.get(JOB_ID) == checkpoint


def test_checkpoint_index_tampering_fails_closed(tmp_path: Path) -> None:
    checkpoint = _checkpoint(1)
    with CheckpointStore(tmp_path) as store:
        with store.writer():
            store.commit(
                previous=None,
                next_checkpoint=checkpoint,
                advances=(),
                commit_id=COMMIT_ID,
            )
        with store._connect() as connection:
            connection.execute(
                "UPDATE collection_checkpoints SET generation = 9 WHERE job_id = ?",
                [JOB_ID],
            )

        with pytest.raises(CheckpointIntegrityError, match="index columns"):
            store.get(JOB_ID)
        with store.writer(), pytest.raises(
            CheckpointIntegrityError, match="commit journal"
        ):
            store.repair_commit_journals()


def test_checkpoint_body_tampering_fails_against_immutable_journal(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(1)
    forged = checkpoint.model_copy(update={"provider_cursor": "forged-cursor"})
    with CheckpointStore(tmp_path) as store:
        with store.writer():
            store.commit(
                previous=None,
                next_checkpoint=checkpoint,
                advances=(),
                commit_id=COMMIT_ID,
            )
        with store._connect() as connection:
            connection.execute(
                "UPDATE collection_checkpoints SET body_json = ? WHERE job_id = ?",
                [forged.model_dump_json(), JOB_ID],
            )

        with pytest.raises(CheckpointIntegrityError, match="checkpoint rows"):
            store.get(JOB_ID)


def test_graph_read_fails_on_corruption_in_another_dataset(tmp_path: Path) -> None:
    checkpoint = _checkpoint(1)
    advances = tuple(
        GraphAdvance(
            dataset_id=dataset_id,
            expected_current=None,
            expected_revision=0,
            expected_knowledge_end=None,
            manifest_id=MANIFEST_1,
            revision=1,
            knowledge_start=KNOWLEDGE_1,
            knowledge_end=KNOWLEDGE_1,
        )
        for dataset_id in ("btc-raw", "btc-normalized")
    )
    with CheckpointStore(tmp_path) as store:
        with store.writer():
            store.commit(
                previous=None,
                next_checkpoint=checkpoint,
                advances=advances,
                commit_id=COMMIT_ID,
            )
        with store._connect() as connection:
            connection.execute(
                "DELETE FROM graph_currents WHERE dataset_id = 'btc-normalized'"
            )

    with pytest.raises(CheckpointIntegrityError, match="graph current"):
        committed_current(tmp_path, "btc-raw")


@pytest.mark.parametrize("table", ["graph_history", "graph_currents"])
def test_graph_read_detects_commit_id_tampering(
    tmp_path: Path, table: str
) -> None:
    checkpoint = _checkpoint(1)
    with CheckpointStore(tmp_path) as store:
        with store.writer():
            store.commit(
                previous=None,
                next_checkpoint=checkpoint,
                advances=(
                    GraphAdvance(
                        dataset_id="btc-raw",
                        expected_current=None,
                        expected_revision=0,
                        expected_knowledge_end=None,
                        manifest_id=MANIFEST_1,
                        revision=1,
                        knowledge_start=KNOWLEDGE_1,
                        knowledge_end=KNOWLEDGE_1,
                    ),
                ),
                commit_id=COMMIT_ID,
            )
        with store._connect() as connection:
            connection.execute(
                f"UPDATE {table} SET commit_id = ? WHERE dataset_id = ?",
                ["9" * 64, "btc-raw"],
            )

    expected = "graph history" if table == "graph_history" else "graph current"
    with pytest.raises(CheckpointIntegrityError, match=expected):
        committed_current(tmp_path, "btc-raw")


def test_current_read_detects_deleted_intermediate_graph_revision(tmp_path: Path) -> None:
    manifests = (MANIFEST_1, MANIFEST_2, "2" * 64)
    knowledge = (KNOWLEDGE_1, KNOWLEDGE_2, datetime(2026, 8, 14, 3, tzinfo=UTC))
    previous_manifest: str | None = None
    previous_knowledge: datetime | None = None
    with CheckpointStore(tmp_path) as store:
        for index, (manifest_id, known_at) in enumerate(
            zip(manifests, knowledge, strict=True), start=1
        ):
            checkpoint = _checkpoint(1).model_copy(
                update={
                    "job_id": str(index) * 64,
                    "manifest_ids": (manifest_id,),
                    "run_id": str(index + 3) * 64,
                    "updated_at": known_at,
                }
            )
            with store.writer():
                store.commit(
                    previous=None,
                    next_checkpoint=checkpoint,
                    advances=(
                        GraphAdvance(
                            dataset_id="btc-raw",
                            expected_current=previous_manifest,
                            expected_revision=index - 1,
                            expected_knowledge_end=previous_knowledge,
                            manifest_id=manifest_id,
                            revision=index,
                            knowledge_start=known_at,
                            knowledge_end=known_at,
                        ),
                    ),
                    commit_id=str(index + 6) * 64,
                )
            previous_manifest = manifest_id
            previous_knowledge = known_at
        with store._connect() as connection:
            connection.execute(
                """
                DELETE FROM graph_history
                WHERE dataset_id = 'btc-raw' AND compatibility_revision = 2
                """
            )

    with pytest.raises(CheckpointIntegrityError, match="journal.*history"):
        committed_current(tmp_path, "btc-raw")


def test_control_lock_rejects_hard_links_before_mutation(tmp_path: Path) -> None:
    store = CheckpointStore(tmp_path)
    store.lock_path.unlink()
    external = tmp_path / "external-lock-target"
    external.write_bytes(b"safe")
    os.link(external, store.lock_path)

    with pytest.raises(CheckpointIntegrityError, match="hard links"):
        with store.writer():
            pass

    assert external.read_bytes() == b"safe"


def test_interrupted_hard_link_publish_removes_its_temporary_link(
    tmp_path: Path,
) -> None:
    store = CheckpointStore(tmp_path)
    target = store._journal_path(COMMIT_ID, committed=True)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.stem}.interrupted.tmp"
    payload = b'{"contract":"test"}'
    temporary.write_bytes(payload)
    os.link(temporary, target)

    store._write_journal_file(target, payload)

    assert not temporary.exists()
    assert target.stat().st_nlink == 1


def test_restart_repairs_a_committed_journal_temporary_hard_link(
    tmp_path: Path,
) -> None:
    checkpoint = _checkpoint(1)
    with CheckpointStore(tmp_path) as store:
        with store.writer():
            store.commit(
                previous=None,
                next_checkpoint=checkpoint,
                advances=(),
                commit_id=COMMIT_ID,
            )
        target = store._journal_path(COMMIT_ID, committed=True)

    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os, pathlib; "
                "target=pathlib.Path(os.environ['QM_JOURNAL']); "
                "temporary=target.parent / f'.{target.stem}.crashed.tmp'; "
                "os.link(target, temporary); os._exit(17)"
            ),
        ],
        check=False,
        env={**os.environ, "QM_JOURNAL": str(target)},
    )
    assert target.stat().st_nlink == 2

    with CheckpointStore(tmp_path) as reopened:
        with reopened.writer():
            reopened.repair_commit_journals()
        assert reopened.get(JOB_ID) == checkpoint
    assert target.stat().st_nlink == 1


@pytest.mark.parametrize("fail_on", [1, 2])
def test_restart_recovers_prelink_intent_and_commit_temporaries(
    tmp_path: Path, fail_on: int
) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _PRELINK_CRASH, str(tmp_path), str(fail_on)],
        check=False,
    )
    assert result.returncode != 0

    checkpoint = _checkpoint(1)
    with CheckpointStore(tmp_path) as reopened:
        with reopened.writer():
            reopened.repair_commit_journals()
            if fail_on == 1:
                reopened.commit(
                    previous=None,
                    next_checkpoint=checkpoint,
                    advances=(),
                    commit_id=COMMIT_ID,
                )
        assert reopened.get(JOB_ID) == checkpoint

    control = tmp_path / ".trusted-data-v2" / "control"
    assert not tuple((control / "graph-intents").glob(".*.tmp"))
    assert not tuple((control / "graph-commits").glob(".*.tmp"))


def test_restart_recovers_postlink_uncommitted_intent(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-c", _POSTLINK_INTENT_CRASH, str(tmp_path), "1"],
        check=False,
    )
    assert result.returncode != 0

    with CheckpointStore(tmp_path) as reopened:
        with reopened.writer():
            reopened.repair_commit_journals()
            reopened.commit(
                previous=None,
                next_checkpoint=_checkpoint(1),
                advances=(),
                commit_id=COMMIT_ID,
            )
        assert reopened.get(JOB_ID) == _checkpoint(1)


def test_owner_marker_recovers_after_reservation_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = json.dumps(
        {
            "job_id": JOB_ID,
            "advances": [{"dataset_id": "btc-raw"}],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    with CheckpointStore(tmp_path) as store:
        original = store._write_graph_owner
        monkeypatch.setattr(
            store,
            "_write_graph_owner",
            lambda _dataset_id: (_ for _ in ()).throw(RuntimeError("owner crash")),
        )
        with store.writer(), pytest.raises(RuntimeError, match="owner crash"):
            store.save_pending(JOB_ID, body)
        monkeypatch.setattr(store, "_write_graph_owner", original)
        with store.writer():
            store.repair_graph_owners()

        assert store.pending(JOB_ID) == body
        assert reserved_job(tmp_path, "btc-raw") == JOB_ID
        assert store._graph_owner_path("btc-raw").exists()


def test_writer_lease_refuses_a_nested_owner_before_opening_duckdb(tmp_path: Path) -> None:
    with CheckpointStore(tmp_path) as store:
        with store.writer():
            with pytest.raises(ConcurrentWriterError):
                with store.writer():
                    pass


def test_writer_mutations_require_the_owner_thread(tmp_path: Path) -> None:
    errors: list[BaseException] = []
    with CheckpointStore(tmp_path) as store:
        with store.writer():
            worker = threading.Thread(
                target=lambda: _capture_error(
                    errors, lambda: store.next_attempt(JOB_ID)
                )
            )
            worker.start()
            worker.join(timeout=10)

    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
    assert "writer lease" in str(errors[0])


def _capture_error(errors: list[BaseException], operation) -> None:
    try:
        operation()
    except BaseException as error:  # noqa: BLE001 - asserted by the test
        errors.append(error)


def test_pending_graph_reserves_every_target_dataset(tmp_path: Path) -> None:
    def body(job_id: str, dataset_id: str) -> str:
        return json.dumps(
            {
                "job_id": job_id,
                "advances": [{"dataset_id": dataset_id}],
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    with CheckpointStore(tmp_path) as store:
        with store.writer():
            store.save_pending(JOB_ID, body(JOB_ID, "btc-raw"))
        with store.writer():
            with pytest.raises(CheckpointConflictError, match="reserved"):
                store.save_pending("9" * 64, body("9" * 64, "btc-raw"))


def test_writer_lease_refuses_another_process_and_recovers_after_kill(
    tmp_path: Path,
) -> None:
    with CheckpointStore(tmp_path):
        pass
    script = """
import sys
from pathlib import Path
from quantmesh.data.checkpoints import CheckpointStore
store = CheckpointStore(Path(sys.argv[1]))
with store.writer():
    print('READY', flush=True)
    sys.stdin.read(1)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", script, str(tmp_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        assert child.stdout is not None
        assert child.stdout.readline().strip() == "READY"
        with CheckpointStore(tmp_path) as contender:
            with pytest.raises(ConcurrentWriterError):
                with contender.writer():
                    pass
    finally:
        child.kill()
        child.wait(timeout=10)

    with CheckpointStore(tmp_path) as recovered:
        with recovered.writer():
            pass


def test_eight_processes_create_one_logical_graph_commit(tmp_path: Path) -> None:
    with CheckpointStore(tmp_path):
        pass
    gate = tmp_path / "start-eight-collectors"
    script = """
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from quantmesh.data.checkpoints import (
    CheckpointStore,
    CollectionCheckpoint,
    ConcurrentWriterError,
    GraphAdvance,
)

root, gate_path = Path(sys.argv[1]), Path(sys.argv[2])
while not gate_path.exists():
    time.sleep(0.005)
store = CheckpointStore(root)
try:
    with store.writer():
        if store.get('a' * 64) is not None:
            print('REPLAY')
        else:
            attempt = store.next_attempt('a' * 64)
            time.sleep(0.2)
            store.commit(
                previous=None,
                next_checkpoint=CollectionCheckpoint(
                    job_id='a' * 64,
                    generation=1,
                    provider_cursor='cursor',
                    last_complete_source_event='event',
                    raw_object_digests=('1' * 64,),
                    manifest_ids=('e' * 64,),
                    preflight_id='d' * 64,
                    quality_report_id=None,
                    run_id='b' * 64,
                    attempt=attempt,
                    updated_at=datetime(2026, 8, 14, tzinfo=UTC),
                ),
                advances=(GraphAdvance(
                    dataset_id='btc-raw',
                    expected_current=None,
                    expected_revision=0,
                    expected_knowledge_end=None,
                    manifest_id='e' * 64,
                    revision=1,
                    knowledge_start=datetime(2026, 8, 14, tzinfo=UTC),
                    knowledge_end=datetime(2026, 8, 14, tzinfo=UTC),
                ),),
                commit_id='c' * 64,
            )
            print('COMMIT')
except ConcurrentWriterError:
    print('BUSY')
"""
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_path), str(gate)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(8)
    ]
    gate.touch()
    results = [process.communicate(timeout=20) for process in processes]

    outcomes = [stdout.strip() for stdout, _stderr in results]
    assert outcomes.count("COMMIT") == 1
    assert set(outcomes) <= {"COMMIT", "BUSY", "REPLAY"}
    assert [process.returncode for process in processes] == [0] * 8
    assert committed_current(tmp_path, "btc-raw") == MANIFEST_1
    journals = tuple(
        (tmp_path / ".trusted-data-v2" / "control" / "graph-commits").glob("*.json")
    )
    assert len(journals) == 1
