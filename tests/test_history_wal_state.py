"""WAL-state software vectors; synthetic receipts are not actual admission."""

import hashlib
import json
from copy import deepcopy

import pytest

from quantmesh.live import history_ram_aux as ram
from tests.test_history_ram_aux import admission, encoded

APPROVAL = "1462eae76d7c909e53cc94fc65dfc62ac05a5676f1a8dde95c1353976971730b"
DESIGN = "e46450c6469b0d05ce3f4d4cf2a7f2feb6b03477013615bb717bbd148624090b"
AUTHORITY = "281575d1d400ea7439ed5d1865b08e61f4349f5eaf3ace7778b821b020c93fc7"
BOOT = "11111111-2222-3333-4444-555555555555"


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def vector(root, presence="ABSENT"):
    old = admission(root)
    snap = old["snapshot"]
    db, wal = snap.pop("files")
    snap.update(db=db, wal={"presence": "PRESENT", "file": wal}, dependency_files=[])
    old.update(
        schema_id="qm.history-ram-aux.admission.v2",
        profile="isolated-ram-aux-wal-state-v2",
        approval_sha256=APPROVAL,
        design_sha256=DESIGN,
        authority_sha256=AUTHORITY,
    )
    proofs = None
    if presence == "ABSENT":
        (root / "live/updates.duckdb.wal").unlink()
        st = (root / "live").stat()
        parent = dict(
            path="live",
            device=st.st_dev,
            inode=st.st_ino,
            mount_id=19,
            mtime_ns=st.st_mtime_ns,
            ctime_ns=st.st_ctime_ns,
        )
        checkpoint = dict(
            schema_id="qm.history-checkpoint.v1",
            nonce=old["nonce"],
            boot_id=BOOT,
            db=db,
            runtime=old["runtime"],
            cut=snap["cut"],
            completed_monotonic=90.0,
            completion="CHECKPOINT_COMPLETED",
            pending_recovery="NONE",
            event_receipt_sha256="d" * 64,
            generation_receipt_sha256=snap["generation_receipt_sha256"],
            no_writer_receipt_sha256=snap["no_writer_receipt_sha256"],
            dependency_receipt_sha256=snap["dependency_receipt_sha256"],
        )
        common = dict(
            nonce=old["nonce"],
            boot_id=BOOT,
            epoch_id="owned-epoch-1",
            issued_monotonic=100.0,
            expires_monotonic=200.0,
            parent=parent,
            db_sha256=db["sha256"],
            generation_receipt_sha256=snap["generation_receipt_sha256"],
            no_writer_receipt_sha256=snap["no_writer_receipt_sha256"],
            namespace_receipt_sha256="e" * 64,
            checkpoint_receipt_sha256=digest(checkpoint),
        )
        epoch = dict(
            common, schema_id="qm.history-absence-epoch.v1", actor=old["actor"], guard=old["guard"]
        )
        absence = dict(
            common,
            schema_id="qm.history-absence.v1",
            basename="updates.duckdb.wal",
            dependency_receipt_sha256=snap["dependency_receipt_sha256"],
            epoch_receipt_sha256=digest(epoch),
            enforcement="ENFORCED_NAMESPACE_EXCLUSION",
        )
        snap["wal"] = dict(
            presence="ABSENT",
            parent=parent,
            basename="updates.duckdb.wal",
            checkpoint_receipt_sha256=digest(checkpoint),
            absence_receipt_sha256=digest(absence),
            epoch_receipt_sha256=digest(epoch),
        )
        proofs = {
            k: deepcopy(v)
            for k, v in dict(checkpoint=checkpoint, absence=absence, epoch=epoch).items()
        }
    snap["content_manifest_sha256"] = digest(
        {k: snap[k] for k in ("db", "wal", "dependency_files")}
    )
    return old, proofs


@pytest.mark.parametrize("presence", ["PRESENT", "ABSENT"])
def test_explicit_v2_state_decodes_without_fake_wal(tmp_path, presence):
    # Removing v2 dispatch or treating ABSENT as an optional file must fail this.
    value, _ = vector(tmp_path / "archive", presence)
    parsed = ram._decode_admission(encoded(value))
    assert parsed.snapshot.wal.presence == presence
    assert [f.path for f in parsed.snapshot.files] == (
        ["live/updates.duckdb", "live/updates.duckdb.wal"]
        if presence == "PRESENT"
        else ["live/updates.duckdb"]
    )


@pytest.mark.parametrize(
    "damage", ["old_approval", "fake_file", "unknown_state", "wrong_manifest", "sidecar"]
)
def test_mixed_or_downgraded_contract_rejected_before_engine(tmp_path, damage):
    value, _ = vector(tmp_path / "archive")
    if damage == "old_approval":
        value["approval_sha256"] = ram.APPROVAL
    elif damage == "fake_file":
        value["snapshot"]["wal"]["file"] = value["snapshot"]["db"]
    elif damage == "unknown_state":
        value["snapshot"]["wal"]["presence"] = "OPTIONAL"
    elif damage == "wrong_manifest":
        value["snapshot"]["content_manifest_sha256"] = "f" * 64
    else:
        f = deepcopy(value["snapshot"]["db"])
        f["path"] = "live/updates.duckdb.wal.recovery"
        value["snapshot"]["dependency_files"] = [f]
    if damage != "wrong_manifest":
        value["snapshot"]["content_manifest_sha256"] = digest(
            {k: value["snapshot"][k] for k in ("db", "wal", "dependency_files")}
        )
    with pytest.raises(ram.HistoryRamAuxRejected):
        ram._decode_admission(encoded(value))


def test_v1_keeps_requiring_present_wal(tmp_path):
    value = admission(tmp_path / "archive")
    value["snapshot"]["files"].pop()
    with pytest.raises(ram.HistoryRamAuxRejected):
        ram._decode_admission(encoded(value))


def test_offline_producer_validates_receipt_lineage_without_issuing_proof(tmp_path):
    from quantmesh.live.history_wal_state import encode_history_wal_state_bundle

    value, proofs = vector(tmp_path / "archive")
    bundle = encode_history_wal_state_bundle(value, **proofs)
    assert bundle["admission"] == encoded(value)
    assert json.loads(bundle["checkpoint"])["completion"] == "CHECKPOINT_COMPLETED"
    wrong = deepcopy(proofs)
    wrong["checkpoint"]["db"]["sha256"] = "f" * 64
    with pytest.raises(ram.HistoryRamAuxRejected):
        encode_history_wal_state_bundle(value, **wrong)


def test_present_sidecar_uses_same_ascii_path_boundary_as_v1(tmp_path):
    value, _ = vector(tmp_path / "archive", "PRESENT")
    bad = deepcopy(value["snapshot"]["db"])
    bad["path"] = "live/updates.duckdb.wal." + chr(233)
    value["snapshot"]["dependency_files"] = [bad]
    value["snapshot"]["content_manifest_sha256"] = digest(
        {k: value["snapshot"][k] for k in ("db", "wal", "dependency_files")}
    )
    with pytest.raises(ram.HistoryRamAuxRejected):
        ram._decode_admission(encoded(value))


@pytest.fixture(scope="module")
def checkpointed_archive(tmp_path_factory):
    import os
    from pathlib import Path

    from tests.test_historical_feed_profile import saved_archive

    reuse = os.environ.get("QM_TEST_WAL_STATE_ARCHIVE")
    if reuse:
        root = Path(reuse).resolve(strict=True)
        owned = (
            Path(__file__).resolve().parents[1] / "output/history-wal-state-implementation-20261030"
        )
        assert root.is_relative_to(owned.resolve())
        raw = (root / "live/updates.duckdb").read_bytes()
        assert len(raw) <= 2 * 1024**2
        assert hashlib.sha256(raw).hexdigest() == os.environ["QM_TEST_WAL_STATE_ARCHIVE_SHA"]
    else:
        root = saved_archive.__wrapped__(tmp_path_factory)
    assert not (root / "live/updates.duckdb.wal").exists()
    return root


def point_at_checkpoint(value, proofs, root):
    # Only the owned engineering fixture is checkpointed. Never touch its WAL path.
    dbpath = root / "live/updates.duckdb"
    st = dbpath.stat()
    db = dict(
        path="live/updates.duckdb",
        device=st.st_dev,
        inode=st.st_ino,
        byte_length=st.st_size,
        mtime_ns=st.st_mtime_ns,
        ctime_ns=st.st_ctime_ns,
        sha256=hashlib.sha256(dbpath.read_bytes()).hexdigest(),
    )
    st = (root / "live").stat()
    parent = dict(
        path="live",
        device=st.st_dev,
        inode=st.st_ino,
        mount_id=19,
        mtime_ns=st.st_mtime_ns,
        ctime_ns=st.st_ctime_ns,
    )
    snap = value["snapshot"]
    snap["root"], snap["db"] = str(root), db
    proofs["checkpoint"]["db"] = db
    cp = digest(proofs["checkpoint"])
    for name in ["epoch", "absence"]:
        proofs[name].update(parent=parent, db_sha256=db["sha256"], checkpoint_receipt_sha256=cp)
    ep = digest(proofs["epoch"])
    proofs["absence"]["epoch_receipt_sha256"] = ep
    snap["wal"].update(
        parent=parent,
        checkpoint_receipt_sha256=cp,
        epoch_receipt_sha256=ep,
        absence_receipt_sha256=digest(proofs["absence"]),
    )
    snap["content_manifest_sha256"] = digest(
        {k: snap[k] for k in ("db", "wal", "dependency_files")}
    )


@pytest.fixture
def absent_capability(tmp_path, monkeypatch, checkpointed_archive):
    import os

    from tests.test_history_ram_aux import Kernel

    root = checkpointed_archive
    value, proofs = vector(tmp_path / "contract-vector")
    point_at_checkpoint(value, proofs, root)
    parent_marker = tmp_path / "parent-os-vector.fd"
    parent_marker.write_bytes(b"synthetic directory FD projection; not native proof")

    class OSVector(Kernel):
        def __init__(self, value):
            super().__init__(value)
            self.value["snapshot"]["files"] = [value["snapshot"]["db"]]

        def boot(self):
            return BOOT

        def open_parent(self, root, name):
            return os.open(parent_marker, os.O_RDONLY)

        def parent(self, root, name, fd):
            st = (root / name).stat()
            return dict(
                path=name,
                device=st.st_dev,
                inode=st.st_ino,
                mount_id=19,
                mtime_ns=st.st_mtime_ns,
                ctime_ns=st.st_ctime_ns,
                directory=True,
                readonly=True,
            )

        def absent(self, fd, basename):
            return not any(p.name.startswith(basename) for p in (root / "live").iterdir())

    kernel = OSVector(value)

    revoked = {"epoch": False}
    epoch_inode = {"value": None}

    def stamp(fd):
        st = os.fstat(fd)
        # Windows cannot unlink an open CRT descriptor. Project Linux nlink0
        # within these explicitly synthetic OS vectors; POSIX uses real unlink.
        links = (
            0
            if os.name == "nt" and revoked["epoch"] and st.st_ino == epoch_inode["value"]
            else st.st_nlink
        )
        return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns, links)

    def read(fd):
        position = os.lseek(fd, 0, os.SEEK_CUR)
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, 32769)
        os.lseek(fd, position, os.SEEK_SET)
        return raw, stamp(fd)

    # Real DB/query/API, explicitly synthetic privileged OS/transport vectors.
    monkeypatch.setattr(ram, "_Kernel", lambda: kernel)
    monkeypatch.setattr(ram, "_read_admission_fd", read)
    monkeypatch.setattr(ram, "_fd_stamp", stamp)
    paths = {"admission": tmp_path / "admission.json"}
    paths.update({k: tmp_path / (k + ".json") for k in proofs})
    paths["admission"].write_bytes(encoded(value))
    for k, v in proofs.items():
        paths[k].write_bytes(encoded(v))
    fds = {k: os.open(p, os.O_RDONLY) for k, p in paths.items()}
    epoch_inode["value"] = os.fstat(fds["epoch"]).st_ino

    def revoke_epoch():
        if not revoked["epoch"]:
            revoked["epoch"] = True
            if os.name != "nt":
                paths["epoch"].unlink()

    paths["revoke_epoch"] = revoke_epoch
    for fd in fds.values():
        os.lseek(fd, 7, os.SEEK_SET)
    kwargs = dict(
        admission_fd=fds["admission"],
        expected_sha256=digest(value),
        checkpoint_fd=fds["checkpoint"],
        absence_fd=fds["absence"],
        epoch_fd=fds["epoch"],
    )
    cap = None
    try:
        cap = ram.admit_history_ram_aux(root, **kwargs)
        yield root, cap, kernel, paths, fds, kwargs
    finally:
        if cap is not None:
            cap.close()
        for fd in fds.values():
            assert os.lseek(fd, 0, os.SEEK_CUR) == 7
            os.close(fd)


def test_checkpointed_absent_opens_ordinary_api_without_creating_wal(absent_capability, tmp_path):
    from fastapi.testclient import TestClient

    from quantmesh.live.buffer import LiveBuffer
    from tests.test_historical_feed_profile import get, history_app

    root, cap, _, _, fds, _ = absent_capability
    path = root / "live/updates.duckdb"
    before = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    reader = LiveBuffer._open_history_ram_aux(root, cap)
    owned_fds = [cap._fd, *cap._evidence.owned, cap._evidence.parent_fd]
    try:
        app, _, _, account = history_app(reader)
        assert account.kill_switch is True
        with TestClient(app) as client:
            response = get(client)
            assert response.status_code == 200, response.text
            data = response.json()
            assert len(data["primary"]["bars"]) == 3
            assert data["source_time"] == "2026-10-23T23:43:00Z"
            assert all(
                [b[k] for k in ("open", "high", "low", "close", "volume")]
                == [100, 101, 99, 100, 10]
                for b in data["primary"]["bars"]
            )
        assert not (root / "live/updates.duckdb.wal").exists()
    finally:
        reader.close()
    assert cap._fd is None and reader._closed
    import errno
    import os

    import duckdb

    with pytest.raises(duckdb.ConnectionException):
        reader._con.execute("SELECT 1")
    for fd in owned_fds:
        with pytest.raises(OSError) as closed:
            os.fstat(fd)
        assert closed.value.errno == errno.EBADF
    assert before == (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns)
    assert not (root / "live/updates.duckdb.wal").exists()

    import os

    evidence = dict(
        kind="OWNED_SYNTHETIC_CHECKPOINT_API_SOFTWARE_ONLY",
        api_status=response.status_code,
        bars=len(data["primary"]["bars"]),
        source_time=data["source_time"],
        db_sha256_before=before[0],
        db_sha256_after=hashlib.sha256(path.read_bytes()).hexdigest(),
        db_mtime_unchanged=before[1] == path.stat().st_mtime_ns,
        wal_created=False,
        reader_closed=reader._closed,
        capability_fd_closed=cap._fd is None,
        caller_positions=[os.lseek(fd, 0, os.SEEK_CUR) for fd in fds.values()],
        owned_fd_closed_count=len(owned_fds),
        connection_reuse_refused=True,
        actual_OS_proof=False,
        original111x17=False,
    )
    (tmp_path / "engineering-api-close.json").write_text(
        json.dumps(evidence, indent=2), encoding="utf-8"
    )


@pytest.mark.parametrize(
    "kind",
    [
        "checkpoint_future",
        "epoch_nonce",
        "nonce",
        "boot",
        "runtime",
        "db",
        "namespace",
        "actor",
        "enforcement",
        "event",
    ],
)
def test_matching_digests_do_not_hide_mismatched_proof_context(tmp_path, kind):
    from quantmesh.live.history_wal_state import encode_history_wal_state_bundle

    value, proofs = vector(tmp_path / "archive")
    cp, ep, ab = (proofs[n] for n in ("checkpoint", "epoch", "absence"))
    if kind == "checkpoint_future":
        cp["completed_monotonic"] = 101.0
    elif kind == "epoch_nonce":
        ep["nonce"] = ab["nonce"] = "other-run"
    elif kind == "nonce":
        cp["nonce"] = "other-run"
    elif kind == "boot":
        cp["boot_id"] = "00000000-0000-0000-0000-000000000001"
    elif kind == "runtime":
        cp["runtime"]["catalog_sha256"] = "f" * 64
    elif kind == "db":
        cp["db"]["sha256"] = "f" * 64
    elif kind == "namespace":
        ep["namespace_receipt_sha256"] = "f" * 64
    elif kind == "actor":
        ep["actor"]["start_ticks"] = 11
    elif kind == "enforcement":
        ab["enforcement"] = "POLLED_NO_EVENT_SEEN"
    else:
        cp["event_receipt_sha256"] = "0" * 64
    cp_sha = digest(cp)
    ep["checkpoint_receipt_sha256"] = ab["checkpoint_receipt_sha256"] = cp_sha
    ep_sha = digest(ep)
    ab["epoch_receipt_sha256"] = ep_sha
    value["snapshot"]["wal"].update(
        checkpoint_receipt_sha256=cp_sha,
        epoch_receipt_sha256=ep_sha,
        absence_receipt_sha256=digest(ab),
    )
    value["snapshot"]["content_manifest_sha256"] = digest(
        {k: value["snapshot"][k] for k in ("db", "wal", "dependency_files")}
    )
    with pytest.raises(ram.HistoryRamAuxRejected):
        encode_history_wal_state_bundle(value, **proofs)


@pytest.mark.parametrize("missing", ["checkpoint_fd", "absence_fd", "epoch_fd"])
def test_absent_requires_all_proof_fds_without_revoking_other_capability(
    absent_capability, missing
):
    root, cap, _, _, _, kwargs = absent_capability
    altered = dict(kwargs, **{missing: None})
    with pytest.raises(ram.HistoryRamAuxRejected):
        ram.admit_history_ram_aux(root, **altered)
    cap.check()


def test_epoch_unlink_recreate_cannot_reauthorize(absent_capability):
    import os

    root, cap, _, paths, fds, _ = absent_capability
    epoch = paths["epoch"]
    raw = epoch.read_bytes()
    paths["revoke_epoch"]()
    if os.name != "nt":
        epoch.write_bytes(raw)  # A new name cannot repair the old held inode.
    with pytest.raises(ram.HistoryRamAuxRejected):
        cap.check()
    assert cap._fd is None and cap._evidence.closed
    with pytest.raises(ram.HistoryRamAuxRejected):
        cap.check()
    assert not (root / "live/updates.duckdb.wal").exists()
    for fd in fds.values():
        os.fstat(fd)


@pytest.mark.parametrize(
    "kind", ["empty_wal", "recovery", "disappeared_wal", "boot", "parent", "permission"]
)
def test_live_absence_failure_is_permanent(absent_capability, kind):
    root, cap, kernel, paths, _, _ = absent_capability
    wal = root / "live/updates.duckdb.wal"
    extra = None
    original_parent = kernel.parent
    if kind == "empty_wal":
        extra = wal
        extra.write_bytes(b"")
    elif kind == "recovery":
        extra = wal.with_name(wal.name + ".recovery")
        extra.write_bytes(b"owned")
    elif kind == "disappeared_wal":
        wal.write_bytes(b"")
        wal.unlink()
        paths["revoke_epoch"]()
    elif kind == "boot":
        kernel.boot = lambda: "00000000-0000-0000-0000-000000000001"
    elif kind == "parent":

        def changed(*args):
            return original_parent(*args) | {"inode": 1}

        kernel.parent = changed
    else:

        def denied(*args):
            raise PermissionError("owned negative vector")

        kernel.absent = denied
    try:
        with pytest.raises(ram.HistoryRamAuxRejected):
            cap.check()
        if extra is not None:
            extra.unlink()
            extra = None
        kernel.parent = original_parent
        with pytest.raises(ram.HistoryRamAuxRejected):
            cap.check()
        assert cap._fd is None and cap._evidence.closed
    finally:
        if extra is not None:
            extra.unlink()


@pytest.mark.parametrize("phase", ["after_sql", "during_decode"])
def test_revoked_epoch_during_read_discards_rows_and_normally_closes(
    absent_capability, monkeypatch, phase
):
    from datetime import UTC, datetime, timedelta

    import quantmesh.live.buffer as buffer

    root, cap, _, paths, _, _ = absent_capability
    reader = buffer.LiveBuffer._open_history_ram_aux(root, cap)
    fetched = []
    if phase == "after_sql":
        original = reader._tail_rows

        def fetch(*args):
            rows = original(*args)
            fetched.extend(rows)
            paths["revoke_epoch"]()
            return rows

        monkeypatch.setattr(reader, "_tail_rows", fetch)
    else:
        original = buffer._row_to_update

        def decode(row):
            result = original(row)
            fetched.append(row)
            paths["revoke_epoch"]()
            return result

        monkeypatch.setattr(buffer, "_row_to_update", decode)
    cut = datetime(2026, 10, 23, 23, 44, 1, tzinfo=UTC)
    try:
        with pytest.raises(ram.HistoryRamAuxRejected):
            reader.replay(
                venue="hyperliquid",
                instrument="BTC",
                kinds={"candle", "status"},
                start=cut - timedelta(days=1),
                end=cut,
                data_time_start=cut - timedelta(days=1),
                data_time_end=cut,
                limit=10000,
                tail=True,
            )
        assert len(fetched) == 3
        assert reader._closed and cap._fd is None and cap._evidence.closed
    finally:
        reader.close()


def test_absence_requires_exact_enoent_not_only_exception_class(monkeypatch):
    import errno
    import os
    from contextlib import nullcontext

    def wrong_errno(*args, **kwargs):
        raise FileNotFoundError(errno.EACCES, "not an absence observation")

    with monkeypatch.context() as local:
        local.setattr(os, "stat", wrong_errno)
        local.setattr(os, "lseek", lambda *_: 0)
        local.setattr(os, "scandir", lambda *_: nullcontext(iter(())))
        with pytest.raises(OSError):
            ram._absent_at(123, "updates.duckdb.wal")


def test_present_producer_has_no_absence_transport_or_downgrade(tmp_path):
    from pydantic import ValidationError

    from quantmesh.live.history_wal_state import encode_history_wal_state_bundle

    value, _ = vector(tmp_path / "archive", "PRESENT")
    bundle = encode_history_wal_state_bundle(value)
    assert bundle == dict(admission=encoded(value), checkpoint=None, absence=None, epoch=None)
    with pytest.raises(ram.HistoryRamAuxRejected):
        encode_history_wal_state_bundle(value, checkpoint={})
    # The frozen v1 model is the old reader boundary, not the new dispatcher.
    with pytest.raises(ValidationError):
        ram._Admission.model_validate(value)


def test_revocation_does_not_hold_capability_lock_while_closing_reader(
    absent_capability, monkeypatch
):
    import threading

    from quantmesh.live.buffer import LiveBuffer

    root, cap, _, paths, _, _ = absent_capability
    reader = LiveBuffer._open_history_ram_aux(root, cap)
    normal_close = reader.close
    done = threading.Event()
    failures = []

    def concurrent_check():
        try:
            cap.check()
        except ram.HistoryRamAuxRejected:
            failures.append("revoked")
        finally:
            done.set()

    def close_with_concurrent_monitor():
        thread = threading.Thread(target=concurrent_check, daemon=True)
        thread.start()
        # Another monitor must be able to observe revocation while reader close
        # waits on its own lock. Otherwise reader->cap/cap->reader can deadlock.
        assert done.wait(2), "reader close held capability lock and blocked monitor"
        thread.join()
        normal_close()

    monkeypatch.setattr(reader, "close", close_with_concurrent_monitor)
    paths["revoke_epoch"]()
    try:
        with pytest.raises(ram.HistoryRamAuxRejected):
            cap.check()
    finally:
        normal_close()
    assert failures == ["revoked"]
    assert reader._closed and cap._fd is None
