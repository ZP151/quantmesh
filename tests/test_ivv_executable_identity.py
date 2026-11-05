"""Equivalent executable origin: actual guard/proof, modeled kernel and immutable files."""

import hashlib
import json
import stat
import sys
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest
import test_ivv_runtime_failure_evidence as base

SHA = hashlib.sha256(b"ELF!").hexdigest()
MODE = "connection-000003"


def environment(monkeypatch, fault=None, *, exact_path=False):
    r = base.runner()
    events, opened = [], set()
    files = {"moomoo/quote/open_quote_context.py": b"quote", "moomoo/pb/Qot_pb2.py": b"proto"}
    files.update({f"moomoo/module{i}.py": b"module" for i in range(10)})
    pins = {
        "pins": [
            {"relative_path": k, "LF_sha256": hashlib.sha256(v).hexdigest()}
            for k, v in files.items()
        ]
    }
    initial = dict(
        st_dev=1,
        st_ino=11,
        st_mode=stat.S_IFREG | 0o755,
        st_uid=0,
        st_nlink=1,
        st_size=4,
        st_ctime_ns=10,
        st_mtime_ns=20,
    )

    def info(fd=None):
        value = dict(initial)
        changes = {
            "uid": ("st_uid", 1),
            "mode": ("st_mode", stat.S_IFREG | 0o777),
            "links": ("st_nlink", 2),
            "type": ("st_mode", stat.S_IFDIR | 0o755),
            "size": ("st_size", 0),
            "oversize": ("st_size", 32 * 1024**2 + 1),
        }
        prefix = "named_" if fd == 20 else "kernel_" if fd == 21 else "none_"
        if fault and fault.startswith(prefix) and fault[len(prefix) :] in changes:
            key, v = changes[fault[len(prefix) :]]
            value[key] = v
        if fd == 21 and fault == "different_object":
            value["st_ino"] = 22
        if fd == 20 and fault == "stamp_drift" and any(e[0] == "read" for e in events):
            value["st_mtime_ns"] = 21
        return SimpleNamespace(**value)

    class P(PurePosixPath):
        def resolve(self, strict=False):
            if str(self) == "/proc/self/exe":
                events.append(("resolve", strict))
                if strict:
                    raise FileNotFoundError(2, "PRIVATE")
                return P("/usr/bin/python3.12") if exact_path else P("/private/live")
            if str(self) == "/usr/bin/python3.12" and fault == "symlink":
                return P("/private/alias")
            return self

        def lstat(self):
            if str(self) == "/usr" and fault == "ancestor":
                return SimpleNamespace(st_uid=1, st_mode=stat.S_IFDIR | 0o755)
            return info()

        def stat(self, **kw):
            return SimpleNamespace(st_mode=stat.S_IFDIR)

        def exists(self):
            return True

        def read_bytes(self):
            return files[str(self.relative_to("/opt/sdk"))]

    def open_fd(path, flags):
        path = str(path)
        if path == "/usr/bin/python3.12":
            assert flags & 0x20000
            if fault == "open_named":
                raise OSError("PRIVATE")
            fd = 20
        else:
            assert path == "/proc/self/exe" and flags & 0x200000 and not flags & 0x20000
            assert 20 in opened
            if fault == "open_kernel":
                raise OSError("PRIVATE")
            fd = 21
        assert flags & 0x80000
        opened.add(fd)
        events.append(("open", fd))
        return fd

    def status(path, **kw):
        if str(path) == "/proc/self/ns/mnt":
            value = (
                45
                if (
                    fault == "namespace"
                    and any(e[0] == "read" for e in events)
                    or fault == "role_namespace"
                    and 21 in opened
                )
                else 44
            )
            return SimpleNamespace(st_ino=value)
        assert str(path) == "/usr/bin/python3.12" and kw.get("follow_symlinks") is False
        value = info()
        if (
            fault == "named_race" and any(e[0] == "read" for e in events)
        ) or fault == "early_named_race":
            value.st_ino = 12
        return value

    def vfs(fd):
        assert fd in opened
        if fd == 21 and fault == "kernel_vfs_unknown":
            raise OSError(9, "PRIVATE")
        return SimpleNamespace(
            f_flag=0 if fault == ("named_rw" if fd == 20 else "kernel_rw") else 1
        )

    def pread(fd, size, offset):
        assert fd == 20, "never read/hash kernel/private contents"
        assert opened == {20, 21} and size == 5 and offset == 0
        events.append(("read", fd))
        if fault == "read_error":
            raise OSError("PRIVATE")
        return b"ELF" if fault == "truncated" else b"FAIL" if fault == "hash" else b"ELF!"

    def close(fd):
        assert fd in opened
        events.append(("close", fd))
        opened.remove(fd)
        if fault == ("close_named" if fd == 20 else "close_kernel"):
            raise OSError("PRIVATE")

    monkeypatch.setattr(r, "Path", P)
    monkeypatch.setattr(r, "SDK", P("/opt/sdk"))
    monkeypatch.setattr(
        r,
        "os",
        SimpleNamespace(
            open=open_fd,
            fstat=info,
            stat=status,
            fstatvfs=vfs,
            pread=pread,
            close=close,
            readlink=lambda path: "/private/live",
            O_RDONLY=0,
            O_NOFOLLOW=0x20000,
            O_CLOEXEC=0x80000,
            O_NONBLOCK=0x800,
            O_PATH=0x200000,
            ST_RDONLY=1,
            statvfs=lambda path: SimpleNamespace(f_flag=1),
            environ={"HOME": "/home/owned"},
        ),
    )
    monkeypatch.setattr(
        r,
        "sys",
        SimpleNamespace(
            exc_info=sys.exc_info,
            version_info=(3, 12, 3),
            executable="/usr/bin/python3.12",
            path=["/usr/lib/python3.12", "/opt/sdk"],
        ),
    )
    monkeypatch.setattr(r, "_writable_mounts", lambda *args, **kw: None)

    def read_ref(ref, path, *args):
        events.append(("material", str(path)))
        if fault == "later_material":
            raise r.Refused("CONTROL_DIGEST")
        return r.raw_json(pins) if str(path).endswith("sdk-pins.json") else b"source"

    monkeypatch.setattr(r, "read_ref", read_ref)
    monkeypatch.setattr(
        r.importlib.machinery.PathFinder,
        "find_spec",
        lambda *args: SimpleNamespace(origin="/opt/sdk/moomoo/__init__.py"),
    )
    plan = {"sdk_root": "/opt/sdk", "sdk_pins_ref": {}, "sdk_pins_sha256": "1" * 64}
    catalog = {**{k: "2" * 64 for k in r._sources(MODE)}, "python_sha256": SHA}
    return r, events, opened, plan, catalog


def expected(method="NAMED_OBJECT", phase="INITIAL", mount=True):
    return {
        "schema": "qm.ivv.executable-origin.v1",
        "method": method,
        "phase": phase,
        "python_sha256": SHA,
        "namespace_inode": 44,
        "kernel_mount_readonly": mount,
    }


@pytest.mark.parametrize(
    "fault,mount", [(None, True), ("kernel_rw", False), ("kernel_vfs_unknown", "UNKNOWN")]
)
def test_actual_runtime_full_object_proof_allows_remaining_original_gates(
    monkeypatch, fault, mount
):
    r, events, opened, plan, catalog = environment(monkeypatch, fault)
    value = r._runtime(plan, None, 44, catalog, None, additional=MODE, origin_phase="INITIAL")
    assert value["executable_origin"] == expected(mount=mount)
    assert not opened
    assert [e for e in events if e[0] == "read"] == [("read", 20)]
    assert events.index(("close", 20)) < next(i for i, e in enumerate(events) if e[0] == "material")
    assert [e for e in events if e[0] == "resolve"] == [("resolve", False)]


@pytest.mark.parametrize(
    "fault",
    [
        "ancestor",
        "symlink",
        "open_named",
        "named_uid",
        "named_mode",
        "named_links",
        "named_type",
        "named_size",
        "named_oversize",
        "named_rw",
        "open_kernel",
        "kernel_uid",
        "kernel_mode",
        "kernel_links",
        "kernel_type",
        "kernel_size",
        "kernel_oversize",
        "different_object",
        "role_namespace",
        "early_named_race",
    ],
)
def test_role_failure_never_reads_or_hashes_unbound_contents(monkeypatch, fault):
    r, events, opened, plan, catalog = environment(monkeypatch, fault)
    with pytest.raises(r.Refused, match="^RUNTIME_ORIGIN$") as error:
        r._runtime(plan, None, 44, catalog, None, additional=MODE, origin_phase="INITIAL")
    identity = r._failure_record(error.value)["origin_failure"]["executable_identity"]
    assert identity["stage"] != "VERIFIED" and identity["descriptor_close"] == "CLOSED"
    assert not opened and not any(e[0] in ("read", "material") for e in events)
    assert "PRIVATE" not in json.dumps(r._failure_record(error.value))


@pytest.mark.parametrize(
    "fault",
    [
        "read_error",
        "truncated",
        "hash",
        "named_race",
        "stamp_drift",
        "namespace",
        "close_named",
        "close_kernel",
    ],
)
def test_read_race_or_close_failure_cannot_pass_original_guard(monkeypatch, fault):
    r, events, opened, plan, catalog = environment(monkeypatch, fault)
    with pytest.raises(r.Refused, match="^RUNTIME_ORIGIN$") as error:
        r._runtime(plan, None, 44, catalog, None, additional=MODE, origin_phase="SESSION")
    record = r._failure_record(error.value)
    assert record["origin_failure"]["executable_identity"]["descriptor_close"] == (
        "UNKNOWN" if fault.startswith("close_") else "CLOSED"
    )
    assert not opened and not any(e[0] == "material" for e in events)
    assert [e for e in events if e[0] == "close"] == [("close", 21), ("close", 20)]


def test_successful_object_relation_survives_later_runtime_failure(monkeypatch):
    r, events, opened, plan, catalog = environment(monkeypatch, "later_material")
    with pytest.raises(r.Refused, match="^CONTROL_DIGEST$") as error:
        r._runtime(plan, None, 44, catalog, None, additional=MODE, origin_phase="INITIAL")
    assert r._failure_record(error.value)["executable_origin"] == expected()
    assert "origin_failure" not in r._failure_record(error.value)
    assert not opened


def test_exact_original_path_never_opens_equivalence_descriptors(monkeypatch):
    r, events, opened, plan, catalog = environment(monkeypatch, exact_path=True)
    value = r._runtime(plan, None, 44, catalog, None, additional=MODE, origin_phase="SESSION")
    assert value["executable_origin"] == expected("EXACT_PATH", "SESSION", "UNKNOWN")
    assert not opened and not any(e[0] in ("open", "read", "close") for e in events)


@pytest.mark.parametrize("mode", [False, True])
def test_old_family_nonmatching_path_still_refuses_without_proof(monkeypatch, mode):
    r, events, opened, plan, catalog = environment(monkeypatch)
    with pytest.raises(r.Refused, match="^RUNTIME_ORIGIN$"):
        r._runtime(plan, None, 44, catalog, None, additional=mode, origin_phase="INITIAL")
    assert not opened and not any(e[0] == "open" for e in events)


def test_late_positive_proof_crosses_actual_authenticated_failure_chain(monkeypatch):
    r, events, opened, plan, catalog = environment(monkeypatch, "later_material")
    with pytest.raises(r.Refused) as caught:
        r._runtime(plan, None, 44, catalog, None, additional=MODE, origin_phase="INITIAL")
    selected = base.test_real_child_ipc_parent_wrap_main_reader_selector(
        monkeypatch, "pidfd", (r, caught.value, None)
    )
    assert selected["executable_origin"] == expected() and selected["actual_contexts"] == "UNKNOWN"


def supervised_witness(monkeypatch, fault=None):
    import struct

    r, events, opened, plan, catalog = environment(monkeypatch)
    initial = r._runtime(plan, None, 44, catalog, None, additional=MODE, origin_phase="INITIAL")[
        "executable_origin"
    ]
    last = r._runtime(plan, None, 44, catalog, None, additional=MODE, origin_phase="SESSION")[
        "executable_origin"
    ]
    if fault == "catalog":
        initial["python_sha256"] = "0" * 64
    if fault == "namespace":
        initial["namespace_inode"] = 45
    if fault == "private":
        initial["private"] = "SECRET"
    if fault == "phase":
        last["phase"] = "INITIAL"
    packets = [
        {"op": "ready", "executable_origin": initial},
        {"op": "observe", "executable_origin": last},
        {"op": "terminal", "permit_sha256": "1" * 64, "manifest_sha256": "2" * 64},
    ]
    sent = []

    class S:
        type = 5

        def fileno(self):
            return 9

        def setsockopt(self, *a):
            pass

        def settimeout(self, value):
            pass

        def send(self, raw):
            sent.append(json.loads(raw))
            return len(raw)

        def recvmsg(self, *a):
            if not packets:
                return b"", [], 0, None
            return (
                r.raw_json(packets.pop(0)),
                [(1, 2, struct.pack("3i", 999 if fault == "credentials" else 502, 0, 0))],
                0,
                None,
            )

    monkeypatch.setattr(
        r,
        "socket",
        SimpleNamespace(
            SOL_SOCKET=1, SO_PASSCRED=3, SOCK_SEQPACKET=5, SCM_CREDENTIALS=2, CMSG_SPACE=lambda n: n
        ),
    )
    monkeypatch.setattr(
        r.os,
        "fstat",
        lambda fd: SimpleNamespace(st_dev=1, st_ino=700, st_mode=stat.S_IFSOCK, st_uid=0),
    )
    channel = r._Channel(S())
    scope = SimpleNamespace(
        pid=502,
        pidfd=8,
        check_pid=lambda: None,
        check_resources=lambda: None,
        verify_manager=lambda: None,
        reap=lambda: 0,
        empty=lambda: None,
    )
    monitor = SimpleNamespace(next=10, last={}, sample=lambda: None)
    monkeypatch.setattr(r, "_Provider", lambda *a, **kw: monitor)
    monkeypatch.setattr(r, "_child_kernel", lambda *a, **kw: {"namespace_inode": 44})
    monkeypatch.setattr(r, "_authorize", lambda *a: ({}, {}, {}, {}))
    monkeypatch.setattr(r, "_owned_peer", lambda pid: (10, 11))
    monkeypatch.setattr(r, "time", SimpleNamespace(monotonic=lambda: 0))
    monkeypatch.setattr(
        r, "select", SimpleNamespace(select=lambda *a: ([channel.s] if packets else [8], [], []))
    )
    monkeypatch.setattr(r, "_seal", lambda *args: args[4])
    values = {"_recovery_mode": MODE, "catalog_ref": catalog}
    context = (
        {"budget_ref": {}},
        values,
        None,
        SimpleNamespace(_digest=lambda v: bool(r.re.fullmatch("[0-9a-f]{64}", v))),
        None,
        None,
    )
    result = r._supervise(scope, channel, 700, context, {"started_monotonic": 0})
    assert sent == [{"op": "enter"}, {"op": "go", "plan_ref": {}, "go_ref": {}}, {"snapshot": {}}]
    return result["executable_origin"]


def test_real_authenticated_ready_observe_parent_witness(monkeypatch):
    assert supervised_witness(monkeypatch) == {
        "initial": expected(),
        "last": expected(phase="SESSION"),
        "checks": 2,
    }


@pytest.mark.parametrize("fault", ["catalog", "namespace", "private", "phase", "credentials"])
def test_parent_refuses_unbound_or_private_positive_witness(monkeypatch, fault):
    with pytest.raises(ValueError):
        supervised_witness(monkeypatch, fault)


def test_session_revalidates_actual_objects_and_transmits_only_current_witness(monkeypatch):
    r, events, opened, plan, catalog = environment(monkeypatch)
    monkeypatch.setattr(r.os, "getpid", lambda: 502, raising=False)
    sent = []
    session = r._ChildSession(
        SimpleNamespace(send=sent.append, recv=lambda parent: {"snapshot": {}}),
        501,
        lambda: r._runtime(plan, None, 44, catalog, None, additional=MODE, origin_phase="SESSION"),
    )
    session.snapshot()
    session.snapshot()
    assert sent == [{"op": "observe", "executable_origin": expected(phase="SESSION")}] * 2
    assert len([e for e in events if e[0] == "read"]) == 2 and not opened


def test_unexpected_proof_error_never_overrides_original_refusal(monkeypatch):
    r, events, opened, plan, catalog = environment(monkeypatch)
    error = RuntimeError("PRIVATE")

    def failed(*args):
        raise error

    monkeypatch.setattr(r, "_prove_executable_identity", failed)
    with pytest.raises(r.Refused, match="^RUNTIME_ORIGIN$") as caught:
        r._runtime(plan, None, 44, catalog, None, additional=MODE, origin_phase="INITIAL")
    record = r._failure_record(caught.value)
    assert record["origin_failure"]["executable_identity"] == {
        "schema": "qm.ivv.executable-identity-failure.v1",
        "stage": "INTERNAL",
        "descriptor_close": "UNKNOWN",
    }
    assert "PRIVATE" not in json.dumps(record) and not opened


@pytest.mark.parametrize("target", ["SDK_ROOT", "PYTHON_VERSION", "EXECUTABLE"])
@pytest.mark.parametrize("where", ["lookup", "comparison", "truth"])
def test_recovery_original_exception_never_enters_object_proof(monkeypatch, target, where):
    r = base.runner()
    error = ValueError("PRIVATE")
    plan, calls = base.origin_seams(r, monkeypatch, target, error=error, where=where)
    monkeypatch.setattr(r, "_locations", lambda mode: None)
    monkeypatch.setattr(r, "_writable_mounts", lambda *a, **kw: None)
    monkeypatch.setattr(
        r, "_prove_executable_identity", lambda *a: pytest.fail("extra proof evaluation")
    )
    with pytest.raises(ValueError) as caught:
        r._runtime(plan, None, 44, {}, None, additional=MODE, origin_phase="SESSION")
    assert caught.value is error and error.args == ("PRIVATE",)
    assert r._failure_record(error)["origin_failure"]["outcome"] == "EXCEPTION"
    assert "PRIVATE" not in json.dumps(r._failure_record(error))
    assert sum(e == ("lookup", target) for e in calls) == 1


@pytest.mark.parametrize(
    "field,value",
    [
        ("private", "SECRET"),
        ("namespace_inode", True),
        ("namespace_inode", float("nan")),
        ("python_sha256", "SECRET"),
        ("kernel_mount_readonly", 1),
        ("method", "/private/alias"),
        ("phase", "AFTER_SDK"),
    ],
)
def test_strict_witness_private_or_malformed_fields_never_forward(monkeypatch, field, value):
    r = base.runner()
    witness = expected()
    witness[field] = value
    with pytest.raises(r.Refused):
        r.select_executable_origin(witness)
    error = ValueError("private old error")
    error._qm_executable_origin = expected()
    assert r._executable_from_error(error) is None
    r._carry_executable_origin(error, witness)
    assert r._executable_from_error(error) is None


@pytest.mark.parametrize("ordering", ["channel", "pidfd", "both"])
def test_proof_refusal_crosses_real_failed_ipc_and_stop(monkeypatch, ordering):
    r, events, opened, plan, catalog = environment(monkeypatch, "different_object")
    with pytest.raises(r.Refused) as caught:
        r._runtime(plan, None, 44, catalog, None, additional=MODE, origin_phase="INITIAL")
    origin = r._failure_record(caught.value)["origin_failure"]
    assert origin["executable_identity"]["stage"] == "ROLE_BINDING"
    selected = base.test_real_child_ipc_parent_wrap_main_reader_selector(
        monkeypatch, ordering, (r, caught.value, origin)
    )
    assert selected["origin_failure"] == origin and selected["actual_contexts"] == "UNKNOWN"


def test_reused_exception_cannot_attribute_a_previous_object_proof_to_new_call(monkeypatch):
    r = base.runner()
    error = ValueError("PRIVATE")
    r._carry_executable_origin(error, expected())
    plan, calls = base.origin_seams(r, monkeypatch, "EXECUTABLE", error=error, where="lookup")
    monkeypatch.setattr(r, "_locations", lambda mode: None)
    monkeypatch.setattr(r, "_writable_mounts", lambda *a, **kw: None)
    with pytest.raises(ValueError) as caught:
        r._runtime(plan, None, 44, {}, None, additional=MODE, origin_phase="SESSION")
    assert caught.value is error and error.args == ("PRIVATE",)
    assert r._executable_from_error(error) is None
    assert r._origin_from_error(error)["phase"] == "SESSION"
