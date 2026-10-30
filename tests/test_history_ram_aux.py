"""Private RAM profile controls; synthetic OS evidence is not native admission."""

import hashlib
import importlib
import json
from copy import deepcopy

import pytest


def module():
    try:
        return importlib.import_module("quantmesh.live.history_ram_aux")
    except ModuleNotFoundError:
        pytest.fail("guarded RAM auxiliary capability is not implemented")


def admission(root, *, create_files=True):
    files = []
    (root.parent / "aux").mkdir(exist_ok=True)
    (root / "live").mkdir(parents=True, exist_ok=True)
    for name, raw in [
        ("live/updates.duckdb", b"author db"),
        ("live/updates.duckdb.wal", b"author wal"),
    ]:
        path = root / name
        if create_files:
            path.write_bytes(raw)
        raw = path.read_bytes()
        st = path.stat()
        files.append(
            dict(
                path=name,
                device=st.st_dev,
                inode=st.st_ino,
                byte_length=st.st_size,
                mtime_ns=st.st_mtime_ns,
                ctime_ns=st.st_ctime_ns,
                sha256=hashlib.sha256(raw).hexdigest(),
            )
        )
    return dict(
        schema_id="qm.history-ram-aux.admission.v1",
        profile="isolated-ram-aux-v1",
        approval_sha256="b737f446acfc4c5e1479ec05083c7c46467f30648057fda66f431253f0ea70e1",
        design_sha256="a2119e8331b869f33a94fbaf509ce3e5ea8dc51df29ea95cef67905feaacb746",
        authority_sha256="c8b1be862f4f8d939c007f42bc2a819811b9cfb567d45eca96ed395f376b4ab0",
        nonce="1b855862-c0ae-46e1-b88c-66d51b481962",
        issued_monotonic=100.0,
        expires_monotonic=200.0,
        actor=dict(pid=1001, start_ticks=10, uid=999, cgroup="/qm-native.scope/native"),
        unit=dict(cgroup="/qm-native.scope", receipt_sha256="1" * 64),
        aux=dict(path=str(root.parent / "aux"), mount_id=12, device=33, inode=44),
        guard=dict(
            pid=1002,
            start_ticks=9,
            uid=999,
            cgroup="/qm-native.scope/native",
            receipt_sha256="2" * 64,
        ),
        snapshot=dict(
            root=str(root),
            files=files,
            content_manifest_sha256=hashlib.sha256(
                json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            generation_receipt_sha256="3" * 64,
            no_writer_receipt_sha256="4" * 64,
            dependency_receipt_sha256="5" * 64,
            cut="2026-10-23T23:44:01Z",
            selected_keys=111,
            fields=17,
            key_sha256="7644c851644b387fce7a8b173b89c74e43fcd91e422ac9a14dd9d69aa3ed1ecd",
        ),
        runtime=dict(
            python_version="3.12.3",
            duckdb_version="1.5.5",
            python_executable_sha256="6" * 64,
            duckdb_module_sha256="7" * 64,
            duckdb_extension_sha256="8" * 64,
            buffer_source_sha256="9" * 64,
            profile_source_sha256="a" * 64,
            catalog_sha256="b" * 64,
        ),
        controller_receipt_sha256="c" * 64,
    )


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def test_exact_contract_and_manifest_binding(tmp_path):
    m = module()
    value = admission(tmp_path / "archive")
    parsed = m._decode_admission(encoded(value))
    assert parsed.snapshot.selected_keys == 111
    value["snapshot"]["files"][0]["sha256"] = "f" * 64
    with pytest.raises(m.HistoryRamAuxRejected):
        m._decode_admission(encoded(value))


@pytest.mark.parametrize(
    "change",
    [
        "boolean_pid",
        "unknown_flag",
        "wrong_profile",
        "wrong_scope",
        "nonfinite",
        "same_guard",
        "zero_proof",
        "file_escape",
    ],
)
def test_forged_contract_refuses_without_authority(tmp_path, change):
    m = module()
    value = admission(tmp_path / "archive")
    if change == "boolean_pid":
        value["actor"]["pid"] = True
    elif change == "unknown_flag":
        value["approved"] = True
    elif change == "wrong_profile":
        value["profile"] = "1GiB"
    elif change == "wrong_scope":
        value["snapshot"]["selected_keys"] = 110
    elif change == "nonfinite":
        value["expires_monotonic"] = float("inf")
    elif change == "same_guard":
        value["guard"]["pid"] = value["actor"]["pid"]
    elif change == "zero_proof":
        value["snapshot"]["no_writer_receipt_sha256"] = "0" * 64
    else:
        value["snapshot"]["files"][0]["path"] = "../escape"
    with pytest.raises(m.HistoryRamAuxRejected):
        m._decode_admission(encoded(value))


def test_duplicate_json_and_unbounded_body_refused(tmp_path):
    m = module()
    for raw in [b'{"profile":1,"profile":2}', b" " * 32769]:
        with pytest.raises(m.HistoryRamAuxRejected):
            m._decode_admission(raw)


def test_mount_and_lock_parsers_require_real_kernel_semantics():
    m = module()
    mount = "12 1 0:33 / /owned/aux rw,nosuid,nodev,noexec - tmpfs tmpfs rw,size=262144k,noswap\n"
    assert m._mount_entry(mount, "/owned/aux")["id"] == 12
    assert m._whole_read_lock("1: POSIX ADVISORY READ 1002 08:01:55 0 EOF\n", 1002, 8, 1, 55)
    for row in [
        "1: POSIX ADVISORY READ 1001 08:01:55 0 EOF",
        "1: FLOCK ADVISORY READ 1002 08:01:55 0 EOF",
        "1: POSIX ADVISORY READ 1002 08:01:55 1 EOF",
        "1: POSIX ADVISORY WRITE 1002 08:01:55 0 EOF",
    ]:
        assert not m._whole_read_lock(row, 1002, 8, 1, 55)
    with pytest.raises(m.HistoryRamAuxRejected):
        m._mount_entry(mount.replace(",noswap", ""), "/owned/aux")


class Kernel:
    """Complete synthetic kernel vectors, never a production admission option."""

    def __init__(self, value):
        self.value = deepcopy(value)
        self.damage = None

    def platform(self):
        return "linux"

    def now(self):
        return 150.0

    def current(self):
        return (1001, 999, 999)

    def process(self, pid):
        part = self.value["actor" if pid == 1001 else "guard"]
        return dict(
            start_ticks=part["start_ticks"],
            uid=part["uid"],
            cgroup=part["cgroup"],
            oom_score_adj=1000,
        )

    def unit(self, cgroup):
        return {
            "memory.max": "2147483648",
            "memory.swap.max": "0",
            "memory.oom.group": "1",
            "cpu.max": "50000 100000",
        }

    def available(self):
        return 8 * 1024**3

    def aux(self, path):
        return dict(self.value["aux"], uid=999, mode=0o700, bytes=256 * 1024**2, empty=True)

    def file(self, root, name):
        item = next(x for x in self.value["snapshot"]["files"] if x["path"] == name)
        return {k: v for k, v in item.items() if k != "sha256"} | {
            "readonly": True,
            "regular": True,
        }

    def lock(self, pid, device, inode):
        return True

    def runtime(self):
        return {k: v for k, v in self.value["runtime"].items() if k != "catalog_sha256"}


def test_complete_kernel_vector_and_exact_root(tmp_path):
    m = module()
    value = admission(tmp_path / "archive")
    a = m._decode_admission(encoded(value))
    kernel = Kernel(value)
    m._check_live(a, tmp_path / "archive", kernel, initial=True)
    with pytest.raises(m.HistoryRamAuxRejected):
        m._check_live(a, tmp_path / "wrong", kernel, initial=True)


@pytest.mark.parametrize(
    "damage",
    [
        "unit",
        "swap",
        "oom",
        "cpu",
        "guard_start",
        "guard_cgroup",
        "lock",
        "quota",
        "mount",
        "readonly",
        "runtime",
        "expiry",
        "headroom",
    ],
)
def test_one_missing_live_gate_refuses_even_with_complete_receipt(tmp_path, damage):
    m = module()
    value = admission(tmp_path / "archive")
    kernel = Kernel(value)
    if damage in {"unit", "swap", "oom", "cpu"}:
        facts = kernel.unit(None)
        facts[
            {
                "unit": "memory.max",
                "swap": "memory.swap.max",
                "oom": "memory.oom.group",
                "cpu": "cpu.max",
            }[damage]
        ] = {"unit": "max", "swap": "max", "oom": "0", "cpu": "max 100000"}[damage]
        kernel.unit = lambda _: facts
    elif damage in {"guard_start", "guard_cgroup"}:
        original = kernel.process

        def process(pid):
            fact = original(pid)
            if pid == 1002:
                fact["start_ticks" if damage == "guard_start" else "cgroup"] = (
                    999 if damage == "guard_start" else "/other"
                )
            return fact

        kernel.process = process
    elif damage == "lock":
        kernel.lock = lambda *_: False
    elif damage in {"quota", "mount"}:
        facts = kernel.aux(None)
        facts["bytes" if damage == "quota" else "mount_id"] += 1
        kernel.aux = lambda _: facts
    elif damage == "readonly":
        original = kernel.file
        kernel.file = lambda *args: original(*args) | {"readonly": False}
    elif damage == "runtime":
        facts = kernel.runtime()
        facts["duckdb_extension_sha256"] = "d" * 64
        kernel.runtime = lambda: facts
    elif damage == "expiry":
        kernel.now = lambda: 201.0
    else:
        kernel.available = lambda: 1024**3
    with pytest.raises(m.HistoryRamAuxRejected):
        m._check_live(
            m._decode_admission(encoded(value)), tmp_path / "archive", kernel, initial=True
        )


def test_descriptor_requires_root_readonly_single_link_regular():
    import os
    import stat
    from types import SimpleNamespace

    m = module()
    state = dict(
        st_mode=stat.S_IFREG | 0o444,
        st_uid=0,
        st_gid=0,
        st_nlink=1,
        st_dev=1,
        st_ino=2,
        st_size=12,
        st_mtime_ns=3,
        st_ctime_ns=4,
    )
    m._validate_fd_stat(SimpleNamespace(**state), os.O_RDONLY)
    for field, bad in [
        ("st_uid", 999),
        ("st_mode", stat.S_IFREG | 0o644),
        ("st_nlink", 2),
        ("st_mode", stat.S_IFIFO | 0o444),
        ("st_size", 32769),
    ]:
        with pytest.raises(m.HistoryRamAuxRejected):
            m._validate_fd_stat(SimpleNamespace(**(state | {field: bad})), os.O_RDONLY)
    with pytest.raises(m.HistoryRamAuxRejected):
        m._validate_fd_stat(SimpleNamespace(**state), os.O_RDWR)


def test_public_constructor_and_missing_capability_remain_closed(tmp_path):
    import inspect

    from quantmesh.live.buffer import LiveBuffer

    assert "capability" not in inspect.signature(LiveBuffer).parameters
    with pytest.raises(ValueError):
        LiveBuffer._open_history_ram_aux(tmp_path, True)


@pytest.fixture(scope="module")
def shared_engineering_archive(tmp_path_factory):
    import os
    from pathlib import Path

    from tests.test_historical_feed_profile import saved_archive

    reuse = os.environ.get("QM_TEST_RAM_AUX_ARCHIVE")
    if reuse:
        root = Path(reuse).resolve(strict=True)
        owned = (
            Path(__file__).resolve().parents[1] / "output/history-ram-aux-implementation-20261030"
        )
        assert root.is_relative_to(owned.resolve())
        raw = (root / "live/updates.duckdb").read_bytes()
        assert len(raw) <= 2 * 1024**2
        assert hashlib.sha256(raw).hexdigest() == os.environ["QM_TEST_RAM_AUX_ARCHIVE_SHA"]
        assert (root / "live/updates.duckdb.wal").read_bytes() == b""
        return root
    root = saved_archive.__wrapped__(tmp_path_factory)
    (root / "live/updates.duckdb.wal").write_bytes(b"")  # authored empty WAL
    return root


@pytest.fixture
def synthetic_capability(tmp_path, monkeypatch, shared_engineering_archive):
    import os

    m = module()
    root = shared_engineering_archive
    value = admission(root, create_files=False)
    kernel = Kernel(value)
    path = tmp_path / "synthetic-admission.json"
    path.write_bytes(encoded(value))

    def stamp(fd):
        st = os.fstat(fd)
        return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

    def read(fd):
        position = os.lseek(fd, 0, os.SEEK_CUR)
        os.lseek(fd, 0, os.SEEK_SET)
        raw = os.read(fd, 32769)
        os.lseek(fd, position, os.SEEK_SET)
        return raw, stamp(fd)

    # These are complete synthetic OS/FD vectors, NOT a runtime capability bypass.
    # Production admission hardwires _Kernel and root-owned FD checks.
    monkeypatch.setattr(m, "_Kernel", lambda: kernel)
    monkeypatch.setattr(m, "_read_admission_fd", read)
    monkeypatch.setattr(m, "_fd_stamp", stamp)
    fd = os.open(path, os.O_RDONLY)
    os.lseek(fd, 7, os.SEEK_SET)
    cap = m.admit_history_ram_aux(
        root, admission_fd=fd, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
    )
    assert os.lseek(fd, 0, os.SEEK_CUR) == 7
    try:
        yield root, cap, kernel, path, fd
    finally:
        cap.close()
        os.close(fd)


def test_profile_opens_original_factory_and_closes_without_mutation(synthetic_capability):
    from fastapi.testclient import TestClient

    from quantmesh.api.workstation import create_workstation_app
    from quantmesh.execution.accounting import PaperAccount
    from quantmesh.instruments.live_history import LiveHistoryService
    from quantmesh.live.buffer import LiveBuffer
    from quantmesh.live.feed import LiveFeed

    root, cap, _, _, _ = synthetic_capability
    before = hashlib.sha256((root / "live/updates.duckdb").read_bytes()).hexdigest()
    lake = LiveBuffer._open_history_ram_aux(root, cap)
    settings = lake._con.execute(
        "SELECT current_setting('memory_limit'), "
        "current_setting('max_temp_directory_size'), "
        "current_setting('TimeZone'), current_setting('threads')"
    ).fetchone()
    assert settings == ("1.0 GiB", "256.0 MiB", "UTC", 1)
    service = LiveHistoryService(None, LiveFeed(lake=lake, history_only=True))
    app = create_workstation_app(
        account=PaperAccount(cash=0, kill_switch=True), history=service, host="127.0.0.1"
    )
    try:
        with TestClient(app) as client:
            response = client.get(
                "/api/instruments/hyperliquid/BTC/history-inspection",
                params={"at": "2026-10-23T23:44:01Z"},
            )
            assert response.status_code == 200, response.text
            data = response.json()
            assert len(data["primary"]["bars"]) == 3
            assert data["source_time"] == "2026-10-23T23:43:00Z"
        cap.check()
    finally:
        lake.close()
    assert cap._fd is None
    assert hashlib.sha256((root / "live/updates.duckdb").read_bytes()).hexdigest() == before


def test_reusing_capability_does_not_close_its_existing_reader(synthetic_capability):
    from quantmesh.live.buffer import LiveBuffer

    root, cap, _, _, _ = synthetic_capability
    lake = LiveBuffer._open_history_ram_aux(root, cap)
    try:
        with pytest.raises(ValueError):
            LiveBuffer._open_history_ram_aux(root, cap)
        cap.check()
        assert lake._con.execute("SELECT 1").fetchone() == (1,)
    finally:
        lake.close()


def test_lost_guard_refuses_before_payload_and_still_closes(synthetic_capability, monkeypatch):
    from quantmesh.live.buffer import LiveBuffer

    root, cap, kernel, _, _ = synthetic_capability
    lake = LiveBuffer._open_history_ram_aux(root, cap)
    kernel.lock = lambda *_: False
    calls = []
    monkeypatch.setattr(lake, "_tail_rows", lambda *args: calls.append(args))
    try:
        with pytest.raises(ValueError):
            lake.replay()
        assert not calls
    finally:
        lake.close()
    assert cap._fd is None


@pytest.mark.parametrize("field", ["selected_keys", "fields"])
def test_fixed_integer_contract_does_not_coerce_float(tmp_path, field):
    m = module()
    value = admission(tmp_path / "archive")
    value["snapshot"][field] = float(value["snapshot"][field])
    with pytest.raises(m.HistoryRamAuxRejected):
        m._decode_admission(encoded(value))


def test_proc_process_parser_uses_start_identity_and_cgroup(monkeypatch):
    m = module()
    tail = ["S"] + ["0"] * 18 + ["1234"]
    records = {
        "stat": "42 (owned guard) " + " ".join(tail),
        "status": "Uid:\t999\t999\t999\t999\n",
        "cgroup": "0::/qm.slice/native.scope\n",
        "oom_score_adj": "1000\n",
    }
    monkeypatch.setattr(m, "_read_text", lambda path, *_: records[path.name])
    assert m._Kernel().process(42) == dict(
        start_ticks=1234, uid=999, cgroup="/qm.slice/native.scope", oom_score_adj=1000
    )
    records["status"] = "Uid:\t999\t0\t999\t999\n"
    with pytest.raises(m.HistoryRamAuxRejected):
        m._Kernel().process(42)


def test_off_scope_request_is_rejected_before_any_business_query(synthetic_capability, monkeypatch):
    from quantmesh.live.buffer import LiveBuffer

    root, cap, _, _, _ = synthetic_capability
    lake = LiveBuffer._open_history_ram_aux(root, cap)
    calls = []
    monkeypatch.setattr(lake, "_tail_rows", lambda *args: calls.append(args))
    try:
        with pytest.raises(ValueError):
            lake.replay(venue="hyperliquid", instrument="OTHER", tail=True)
        assert not calls
        with pytest.raises(ValueError):
            lake.latest()
    finally:
        lake.close()


def test_real_adapter_is_unavailable_without_trusted_linux_admission(tmp_path):
    m = module()
    for fd, digest in [(True, "f" * 64), (-1, "f" * 64), (0, "0" * 64)]:
        with pytest.raises(m.HistoryRamAuxRejected):
            m.admit_history_ram_aux(tmp_path, admission_fd=fd, expected_sha256=digest)


@pytest.mark.parametrize("change", ["type", "root", "noexec", "quota"])
def test_mount_parser_rejects_substitute_storage(change):
    m = module()
    line = "12 1 0:33 / /owned/aux rw,nosuid,nodev,noexec - tmpfs tmpfs rw,size=262144k,noswap\n"
    if change == "type":
        line = line.replace("- tmpfs tmpfs", "- ext4 disk")
    elif change == "root":
        line = line.replace("0:33 / /owned", "0:33 /subdir /owned")
    elif change == "noexec":
        line = line.replace(",noexec", "")
    else:
        line = line.replace("262144k", "524288k")
    with pytest.raises(m.HistoryRamAuxRejected):
        m._mount_entry(line, "/owned/aux")


@pytest.mark.parametrize("phase", ["after_sql", "during_decode"])
def test_guard_revoked_during_admitted_read_discards_rows_and_closes(
    synthetic_capability, monkeypatch, phase
):
    import os
    from datetime import UTC, datetime, timedelta

    import quantmesh.live.buffer as buffer

    root, cap, kernel, _, caller_fd = synthetic_capability
    before = hashlib.sha256((root / "live/updates.duckdb").read_bytes()).hexdigest()
    lake = buffer.LiveBuffer._open_history_ram_aux(root, cap)
    fetched = []
    if phase == "after_sql":
        original = lake._tail_rows

        def fetch(*args):
            rows = original(*args)
            fetched.extend(rows)
            kernel.lock = lambda *_: False
            return rows

        monkeypatch.setattr(lake, "_tail_rows", fetch)
    else:
        original = buffer._row_to_update

        def decode(row):
            result = original(row)
            fetched.append(row)
            kernel.lock = lambda *_: False
            return result

        monkeypatch.setattr(buffer, "_row_to_update", decode)
    cut = datetime(2026, 10, 23, 23, 44, 1, tzinfo=UTC)
    try:
        with pytest.raises(module().HistoryRamAuxRejected):
            lake.replay(
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
    finally:
        lake.close()
    assert cap._fd is None and lake._closed
    os.fstat(caller_fd)  # Source never closes the startup caller's original descriptor.
    assert hashlib.sha256((root / "live/updates.duckdb").read_bytes()).hexdigest() == before
