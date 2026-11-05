"""Operator startup only; no service, terminal, SDK or credential is used."""

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

NONCE = "4ae19a7fad3fdaf8e3d23c1a4eb4b3d4"
AUTH = "0d2965519662b53c448e003f6a8ddcf8d07834d399da2ece4ab2407475f9a945"


def launcher(monkeypatch):
    path = Path(__file__).resolve().parents[1] / "deploy/aws/opend/stage_console.py"
    spec = importlib.util.spec_from_file_location("opend_restore_test", path)
    m = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, m)
    spec.loader.exec_module(m)
    return m


def envelope(m):
    return {
        "schema": "qm.opend.operator-restore.v1",
        "authority_sha256": AUTH,
        "claims": dict(
            schema_version=2,
            purpose="opend_persistent_private_console",
            nonce=NONCE,
            approved_build="b" * 40,
            launcher_sha256="a" * 64,
            tmux_version="3.4",
            tmux_sha256=m.TMUX_SHA,
            machine_sha256=m.MACHINE_SHA,
            gateway_uid=997,
            gateway_gid=997,
            not_before="2026-11-05T09:00:00+00:00",
            expires_at="2026-11-05T09:05:00+00:00",
            max_seconds=300,
            human_reviewers=["Operator"],
            safety_owner="Operator",
            ci_conclusion="success",
            operator_window_approved=True,
            new_device_approved=True,
            market_right_transfer_approved=True,
            session_lifetime="until_operator_stop",
        ),
    }


def test_fresh_selector_beside_occupied_expired_controls(monkeypatch, tmp_path):
    m = launcher(monkeypatch)
    old = tmp_path / "persistent-recovery.json"
    old.write_bytes(b"occupied")
    monkeypatch.setattr(m, "RECOVERY_PERMIT", old)

    def historical(*args):
        raise m.StageDenied("permit_denied")

    monkeypatch.setattr(m, "_module", lambda *args: SimpleNamespace(load=historical))
    raw = json.dumps(envelope(m), sort_keys=True).encode()
    monkeypatch.setattr(m, "_restore_bytes", lambda: raw, raising=False)
    restored = m.select_console_window(NONCE, persistent=True)
    assert restored.nonce == NONCE and restored.control_sha256 == hashlib.sha256(raw).hexdigest()
    assert m.reload_console_window(restored) == restored
    with pytest.raises(m.StageDenied):
        m.select_console_window(m.PRIVATE_STORAGE_NONCE, persistent=True)
    assert old.read_bytes() == b"occupied"


@pytest.mark.parametrize(
    "fault", ["authority", "schema", "nonce", "field", "claims", "missing", "duplicate"]
)
def test_restore_invalid_refuses_without_historical_fallback(monkeypatch, fault):
    m = launcher(monkeypatch)
    doc = envelope(m)
    if fault in ("authority", "schema", "field"):
        doc[{"authority": "authority_sha256", "schema": "schema", "field": "qualified"}[fault]] = (
            "bad"
        )
    elif fault == "nonce":
        doc["claims"]["nonce"] = m.PRIVATE_STORAGE_NONCE
    elif fault == "claims":
        doc["claims"].pop("safety_owner")
    raw = json.dumps(doc).encode()
    if fault == "duplicate":
        raw = b'{"schema":"other",' + raw[1:]

    def read():
        if fault == "missing":
            raise m.StageDenied("protected_path")
        return raw

    monkeypatch.setattr(m, "_restore_bytes", read)
    monkeypatch.setattr(m, "load_staging_window", lambda **kw: pytest.fail("no fallback"))
    with pytest.raises(m.StageDenied):
        m.select_console_window(NONCE, persistent=True)


def test_existing_expiry_and_exact_restore_reload(monkeypatch):
    m = launcher(monkeypatch)
    raw = json.dumps(envelope(m)).encode()
    monkeypatch.setattr(m, "_restore_bytes", lambda: raw)
    window = m.select_console_window(NONCE, persistent=True)
    kwargs = dict(
        identity={"machine_sha256": m.MACHINE_SHA, "gateway_uid": 997, "gateway_gid": 997},
        hashes={"launcher_sha256": "a" * 64, "tmux_sha256": m.TMUX_SHA},
    )
    m.validate_staging_window(window, now=m._utc("2026-11-05T09:01:00+00:00"), **kwargs)
    with pytest.raises(m.StageDenied):
        m.validate_staging_window(window, now=window.expires, **kwargs)
    assert m._runtime_persistent(window)
    raw += b" "
    with pytest.raises(m.StageDenied, match="pin_drift"):
        m.reload_console_window(window)


@pytest.mark.parametrize("fault", [None, "mode", "named", "short", "symlink"])
def test_restore_held_control_checks_named_bytes(monkeypatch, fault):
    from contextlib import nullcontext

    m = launcher(monkeypatch)
    raw = b"sample"
    info = dict(
        st_dev=1,
        st_ino=2,
        st_mode=0o100444,
        st_size=len(raw),
        st_uid=0,
        st_nlink=1,
        st_mtime_ns=1,
        st_ctime_ns=1,
    )
    if fault == "mode":
        info["st_mode"] = 0o100644
    inode = SimpleNamespace(**info)
    path = SimpleNamespace(
        lstat=lambda: SimpleNamespace(**{**info, "st_ino": 3 if fault == "named" else 2})
    )
    monkeypatch.setattr(m, "RESTORE_CONTROL", path)

    def protected(name):
        assert name is path
        if fault == "symlink":
            raise m.StageDenied("protected_path")
        return nullcontext(12)

    monkeypatch.setattr(m, "_protected_fd", protected)
    monkeypatch.setattr(
        m,
        "os",
        SimpleNamespace(
            fstat=lambda fd: inode, pread=lambda *a: raw[:-1] if fault == "short" else raw
        ),
    )
    if fault:
        with pytest.raises(m.StageDenied):
            m._restore_bytes()
    else:
        assert m._restore_bytes() == raw


@pytest.mark.parametrize("interrupted", [False, True])
def test_exclusive_restore_claim_binds_created_inode_and_two_flushes(monkeypatch, interrupted):
    from contextlib import nullcontext

    m = launcher(monkeypatch)
    raw = json.dumps(envelope(m)).encode()
    monkeypatch.setattr(m, "_restore_bytes", lambda: raw)
    win = m.select_console_window(NONCE, persistent=True)
    events = []

    def exclusive(name, flags, mode, dir_fd):
        assert (name, flags, mode, dir_fd) == (NONCE, 15, 0o600, 12)
        if events:
            raise FileExistsError
        events.append("create")
        return 13

    monkeypatch.setattr(
        m,
        "os",
        SimpleNamespace(
            O_WRONLY=1,
            O_CREAT=2,
            O_EXCL=4,
            O_NOFOLLOW=8,
            open=exclusive,
            fchmod=lambda fd, mode: None,
            fsync=events.append,
            close=lambda fd: events.append("close"),
            fstat=lambda fd: SimpleNamespace(st_dev=1, st_ino=3),
        ),
    )
    expected = pytest.raises(RuntimeError, match="interrupted") if interrupted else nullcontext()
    with expected, m._claim_fd(win, 12) as fd:
        assert fd == 13 and events == ["create", 13, 12]
        with pytest.raises(m.StageDenied, match="duplicate_nonce"), m._claim_fd(win, 12):
            pytest.fail("duplicate allowed")
        if interrupted:
            raise RuntimeError("interrupted")
    assert events == ["create", 13, 12, "close"]


@pytest.mark.parametrize(
    "fault",
    [
        None,
        "foreign_root",
        "ack",
        "manager",
        "claim",
        "recycled",
        "ack_unlink",
        "child",
        "post_ack",
    ],
)
def test_owned_post_exec_packet_is_bounded_and_root_ack_closes_channel(monkeypatch, fault):
    import struct
    from contextlib import nullcontext

    m = launcher(monkeypatch)
    raw = json.dumps(envelope(m)).encode()
    monkeypatch.setattr(m, "_restore_bytes", lambda: raw)
    win = m.select_console_window(NONCE, persistent=True)
    manager = {
        "Id": "quantmesh-opend-console@" + NONCE + ".service",
        "ControlGroup": "/system.slice/unit",
        "InvocationID": "1" * 32,
        "MainPID": "11",
        "ActiveState": "active",
    }
    ident = {"pid": 13, "start_ticks": 333, "uid": 997}
    child = SimpleNamespace(pid=13, pidfd=19, identity=ident, acknowledged=True, released=True)
    events = []

    def identity(*a):
        return {} if fault == "child" or (fault == "post_ack" and "closed" in events) else ident

    monkeypatch.setattr(m, "_identity", identity)
    monkeypatch.setattr(m, "_manager", lambda w: {} if fault == "manager" else manager)
    monkeypatch.setattr(m, "_owned_dir", lambda path: nullcontext(99))
    monkeypatch.setattr(m, "select", SimpleNamespace(select=lambda *a: ([], [], [])))

    def info(path, **kw):
        return SimpleNamespace(
            st_nlink=1, st_dev=1, st_ino=(22 if fault == "claim" else 2) if path == NONCE else 9
        )

    monkeypatch.setattr(
        m,
        "os",
        SimpleNamespace(
            getppid=lambda: 11,
            getpid=lambda: 12,
            stat=info,
            fstat=lambda fd: SimpleNamespace(
                st_dev=1,
                st_ino=2 if fd == 21 else 9,
                st_nlink=0
                if fd == 21
                and (fault == "recycled" or (fault == "ack_unlink" and "closed" in events))
                else 1,
            ),
        ),
    )

    class Channel:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            events.append("closed")

        def connect(self, path):
            assert path == "/run/quantmesh-opend-restore-" + NONCE + ".sock"

        def settimeout(self, n):
            assert 0 < n <= 5

        def getsockopt(self, *a):
            return struct.pack("3i", 301, 1 if fault == "foreign_root" else 0, 0)

        def send(self, data):
            events.append(json.loads(data))
            assert len(data) <= 2048
            return len(data)

        def recv(self, n):
            return b"NO" if fault == "ack" else b"BOUND"

    monkeypatch.setattr(
        m,
        "socket",
        SimpleNamespace(
            socket=lambda *a: Channel(), AF_UNIX=1, SOCK_SEQPACKET=5, SOL_SOCKET=1, SO_PEERCRED=17
        ),
    )
    context = dict(manager=manager, backend_pidfd=18)
    if fault:
        with pytest.raises(m.StageDenied):
            m._attribute_restore(win, context, child, 14, 21)
        if fault == "foreign_root":
            assert events == ["closed"]
    else:
        m._attribute_restore(win, context, child, 14, 21)
        assert events[0] == dict(
            schema="qm.opend.attributed-launch.v1",
            nonce=NONCE,
            authority_sha256=AUTH,
            control_sha256=win.control_sha256,
            launcher_sha256="a" * 64,
            unit=manager["Id"],
            invocation="1" * 32,
            cgroup=manager["ControlGroup"],
            main_pid=11,
            pane_pid=12,
            vendor_pid=13,
            vendor_start=333,
            claim_dev=1,
            claim_ino=2,
        )
        assert events[-1] == "closed"
