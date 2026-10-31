"""Synthetic invocation witness controls; no original Source CLI/vendor/host."""

import hashlib
import json
import os
from types import SimpleNamespace

import pytest
from test_opend_staging_window import stage

BIND = {
    "invocation": "1" * 32,
    "source": "2" * 64,
    "control": "3" * 64,
    "nonce": "c8f0d0de4ca641a491fca6df24c66ceb",
    "pid": 321,
    "start": 456,
}


@pytest.fixture
def writer(monkeypatch):
    data = bytearray(32768)
    writes = []

    def write(fd, raw, offset):
        writes.append((offset, bytes(raw)))
        data[offset : offset + len(raw)] = raw
        return len(raw)

    monkeypatch.setattr(stage.os, "pwrite", write, raising=False)
    monkeypatch.setattr(stage.os, "fsync", lambda fd: None)
    monkeypatch.setattr(stage.os, "close", lambda fd: None)
    w = stage._Witness(7, BIND)
    return w, data, writes


def test_write_once_binding_checksum_complete_and_durability(writer):
    w, data, writes = writer
    w.event("PANE_ENTER")
    w.event("CHILD_REGISTERED", pid=654, start=987)
    w.finish()
    result = stage._witness_read(bytes(data), BIND)
    assert result["content_valid"] and result["stream_complete"]
    assert result["durability"] == "UNKNOWN_NOT_PROVEN_BY_READ"
    assert result["events"][-1]["stage"] == "TERMINAL"
    assert len({o for o, _ in writes}) == len(writes)
    assert all(len(b) == 512 for _, b in writes)


@pytest.mark.parametrize("kind", ["absent", "partial", "checksum", "binding", "sequence"])
def test_invalid_or_stale_never_becomes_complete(writer, kind):
    w, data, _ = writer
    w.event("PANE_ENTER")
    w.finish()
    if kind == "absent":
        data = bytearray()
    elif kind == "partial":
        data = data[:700]
    elif kind == "checksum":
        data[530] ^= 1
    elif kind == "sequence":
        data[1024:1536] = data[512:1024]
    expected = dict(BIND, control="4" * 64) if kind == "binding" else BIND
    assert not stage._witness_read(bytes(data), expected)["stream_complete"]


def test_no_record_means_unknown():
    result = stage._witness_read(b"", BIND)
    assert result["events"] == [] and not result["content_valid"]


def test_fork_to_ack_is_memory_only_no_new_io(writer):
    w, _, writes = writer
    before = len(writes)
    w.hold = True
    w.event("CHILD_REGISTERED", pid=654, start=987)
    w.event("GATE_WRITE_ENTER")
    with pytest.raises(stage.StageDenied):
        w.flush()
    assert len(writes) == before
    w.hold = False
    w.event("GATE_ACK")
    w.flush()
    assert len(writes) > before


def test_caps_short_write_and_primary_not_masked(writer, monkeypatch):
    w, _, _ = writer
    for _ in range(48):
        try:
            w.event("PANE_ENTER")
        except stage.StageDenied:
            break
    assert w.attempts <= 48 and w.bytes_attempted <= 24576
    assert w.failed
    w.finish(primary=ValueError("private sentinel"))
    w2 = stage._Witness(7, BIND)
    monkeypatch.setattr(stage.os, "pwrite", lambda *a: 5)
    with pytest.raises(stage.StageDenied):
        w2.event("PANE_ENTER")
    assert w2.failed


@pytest.mark.parametrize("kind", ["PARENT", "TIMEOUT", "GATE", "SETUP", "CHDIR", "EXEC", "OTHER"])
def test_child_failure_enum_and_fragment_unknown(kind):
    raw = stage._child_failure_frame(kind, 13, 1234)
    assert len(raw) == 14
    decoded = stage._decode_child_frames(raw)
    assert decoded == [{"kind": kind, "errno": 13, "monotonic_ns": 1234}]
    assert stage._decode_child_frames(raw[:-1]) is None
    assert stage._decode_child_frames(raw + b"x") is None


@pytest.mark.parametrize("code", [40, 41, 0, -15])
def test_ack_eof_exit_collision_never_proves_exec(code):
    result = stage._witness_outcome(True, b"", code, False)
    assert result["exec_observed"] is False
    assert result["preexec"] == "UNKNOWN"
    assert result["returncode"] == code
    assert stage._witness_outcome(True, b"", code, True)["exec_observed"] is True


def test_fixed_event_privacy(writer):
    w, data, _ = writer
    with pytest.raises(stage.StageDenied):
        w.event("private secret argv")
    with pytest.raises(stage.StageDenied):
        w.event("PANE_ENTER", arbitrary="secret")
    assert b"secret" not in data and b"argv" not in data


def test_c8_schema4_only_and_original_modes_unchanged():
    assert stage._witness_enabled(
        SimpleNamespace(persistent=True, nonce=BIND["nonce"]), {"schema_version": 4}
    )
    assert not stage._witness_enabled(
        SimpleNamespace(persistent=True, nonce="f" * 32), {"schema_version": 4}
    )
    assert not stage._witness_enabled(
        SimpleNamespace(persistent=True, nonce=BIND["nonce"]), {"schema_version": 3}
    )


def test_preallocation_requires_actual_blocks(monkeypatch):
    called = []
    monkeypatch.setattr(
        stage.os, "posix_fallocate", lambda fd, off, n: called.append(n), raising=False
    )
    monkeypatch.setattr(stage.os, "fstat", lambda fd: SimpleNamespace(st_size=32768, st_blocks=1))
    with pytest.raises(stage.StageDenied):
        stage._witness_reserve(7)
    assert called == [32768]


def test_valid_checksum_does_not_admit_private_unknown_fields(writer):
    w, data, _ = writer
    w.event("PANE_ENTER")
    w.finish()
    obj = json.loads(bytes(data[576:1024]).rstrip(b"\0"))
    obj["event"]["argv"] = "private sentinel"
    body = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode().ljust(448, b"\0")
    data[512:1024] = hashlib.sha256(body).hexdigest().encode() + body
    result = stage._witness_read(bytes(data), BIND)
    assert not result["stream_complete"]
    assert "sentinel" not in json.dumps(result)


def test_final_flush_failure_is_not_durable_or_primary_mask(writer, monkeypatch):
    w, data, _ = writer
    monkeypatch.setattr(stage.os, "fsync", lambda fd: (_ for _ in ()).throw(OSError(28, "secret")))
    original = ValueError("original private failure")
    w.finish(primary=original)
    assert w.closed and w.failed
    result = stage._witness_read(bytes(data), BIND)
    assert result["durability"] == "UNKNOWN_NOT_PROVEN_BY_READ"


def test_early_binding_failure_cannot_reach_selection_or_admit(monkeypatch, capsys):
    calls = []

    def reject(**kwargs):
        calls.append("binding")
        raise stage.StageDenied("backend_denied")

    monkeypatch.setattr(stage, "_witness_open", reject)
    monkeypatch.setattr(stage, "select_console_window", lambda *a, **k: pytest.fail("selected"))
    assert stage.main(["--pane", "--persistent", "--nonce", BIND["nonce"]]) == 2
    assert calls == ["binding"] and not capsys.readouterr().out


def test_reap_drains_without_wait_before_original_report_close(writer, monkeypatch):
    w, _, _ = writer
    monkeypatch.setattr(stage, "_WITNESS", w)
    w.hold = True
    child = SimpleNamespace(report=12, report_prefix=b"", released=True, returncode=41)
    raw = stage._child_failure_frame("EXEC", 13, 54321)
    monkeypatch.setattr(stage.os, "set_blocking", lambda *a: None)
    monkeypatch.setattr(stage.os, "read", lambda fd, n: raw)
    stage._witness_reaped(child)
    assert not w.hold
    assert child.witness_outcome["preexec"][0]["kind"] == "EXEC"
    assert child.witness_outcome["returncode"] == 41
    assert not child.witness_outcome["exec_observed"]


def test_report_failure_keeps_original_exit_path(monkeypatch):
    monkeypatch.setattr(stage.os, "write", lambda *a: (_ for _ in ()).throw(OSError(9, "private")))
    stage._child_fail(7, "PARENT", None, True)


def test_actual_report_ack_then_failure_has_no_exec_claim(writer, monkeypatch):
    w, _, _ = writer
    monkeypatch.setattr(stage, "_WITNESS", w)
    w.hold = True
    child = stage._Owned(123, 20, 21, 22, {"pid": 123, "start_ticks": 789})
    monkeypatch.setattr(child, "alive", lambda: True)
    monkeypatch.setattr(stage, "_identity", lambda *a: child.identity)
    monkeypatch.setattr(stage.os, "write", lambda *a: 1)
    monkeypatch.setattr(stage, "_report", lambda *a: b"R")
    monkeypatch.setattr(stage, "_witness_vendor_identity", lambda *a: None)
    child.release()
    assert child.released and not w.hold
    assert stage._witness_read(bytes(writer[1]), BIND)["stream_complete"] is False


@pytest.mark.parametrize(
    "drift", [None, "invocation", "source", "control_nonce", "cgroup", "parent"]
)
def test_actual_early_binding_has_fixed_query_and_refuses_drift(monkeypatch, drift):
    from contextlib import contextmanager

    claims = dict(schema_version=4, nonce=BIND["nonce"], launcher_sha256=BIND["source"])
    properties = dict(
        Id="quantmesh-opend-console@" + BIND["nonce"] + ".service",
        InvocationID=BIND["invocation"],
        ControlGroup="fixed-original-cgroup",
        MainPID="123",
    )
    if drift == "source":
        claims["launcher_sha256"] = "f" * 64
    if drift == "control_nonce":
        claims["nonce"] = "f" * 32
    if drift == "invocation":
        properties["InvocationID"] = "f" * 32
    if drift == "cgroup":
        properties["ControlGroup"] = "other"
    if drift == "parent":
        properties["MainPID"] = "999"
    calls = []

    def command(argv):
        calls.append(argv)
        assert argv[-1] == "--property=Id,InvocationID,ControlGroup,MainPID"
        assert argv[:2] == ["/usr/bin/systemctl", "show"]
        return "\n".join(k + "=" + v for k, v in properties.items())

    @contextmanager
    def protected(path):
        yield 7

    monkeypatch.setattr(stage, "_bytes", lambda *a, **k: json.dumps(claims).encode())
    monkeypatch.setattr(stage, "_protected_fd", protected)
    monkeypatch.setattr(stage, "_digest_fd", lambda fd: BIND["source"])
    monkeypatch.setattr(stage, "_command", command)
    monkeypatch.setattr(stage, "_cgroup", lambda pid: "fixed-original-cgroup")
    fakeos = SimpleNamespace(
        environ={"INVOCATION_ID": BIND["invocation"]},
        getppid=lambda: 123,
        pidfd_open=lambda p: 8,
        close=lambda p: None,
    )
    monkeypatch.setattr(stage, "os", fakeos)
    monkeypatch.setattr(stage.select, "select", lambda *a: ([], [], []))
    if drift:
        with pytest.raises(stage.StageDenied):
            stage._witness_binding(pane=True)
    else:
        got = stage._witness_binding(pane=True)
        assert got["source"] == BIND["source"] and got["invocation"] == BIND["invocation"]
        assert got["control"] == hashlib.sha256(json.dumps(claims).encode()).hexdigest()
        assert len(calls) == 1


def test_diagnostic_close_error_never_masks_primary(writer, monkeypatch):
    w, _, _ = writer
    calls = []
    w.directory_fd = 8

    def close(fd):
        calls.append(fd)
        raise OSError(9, "private")

    monkeypatch.setattr(stage.os, "close", close)
    w.finish(primary=ValueError("original"))
    assert calls == [7, 8] and w.failed and w.close_attempted and not w.closed


def test_child_excludes_witness_fds_and_holds_before_fork():
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(stage._spawn_gated))
    source = ast.unparse(tree)
    assert source.index("_WITNESS.hold = True") < source.index("os.fork()")
    branch = next(
        n for n in ast.walk(tree) if isinstance(n, ast.If) and ast.unparse(n.test) == "pid == 0"
    )
    child_source = ast.unparse(branch)
    assert child_source.index("os.close(_WITNESS.fd)") < child_source.index("_child(")
    assert child_source.index("os.close(_WITNESS.directory_fd)") < child_source.index("_child(")


def test_real_child_report_descriptor_preserved_until_exec_no_extra_gate_wait():
    import inspect

    code = inspect.getsource(stage._child)
    assert "if not diagnostic:\n                os.close(report)" in code
    assert code.count("select.select([gate], [], [], 2)") == 1
    assert "os.set_inheritable" not in code


def test_gate_write_is_not_ack_in_reaped_outcome(writer, monkeypatch):
    w, _, _ = writer
    monkeypatch.setattr(stage, "_WITNESS", w)
    child = SimpleNamespace(
        report=12,
        report_prefix=b"",
        released=True,
        acknowledged=False,
        exec_observed=False,
        returncode=40,
    )
    monkeypatch.setattr(stage.os, "set_blocking", lambda *a: None)
    monkeypatch.setattr(stage.os, "read", lambda *a: stage._child_failure_frame("TIMEOUT", 0, 11))
    stage._witness_reaped(child)
    assert child.witness_outcome["ack"] is False


def test_safe_error_fields_never_persist_exception_message(writer, monkeypatch):
    w, data, _ = writer
    monkeypatch.setattr(stage, "_WITNESS", w)
    stage._witness_failure("PANE_FAILED", OSError(13, "private argv/XML secret"))
    result = stage._witness_read(bytes(data), BIND)
    assert result["events"][-1]["errno"] == 13
    assert result["events"][-1]["error_type"] == "OSError"
    assert b"secret" not in data and b"XML" not in data


def test_non_schema4_open_does_not_introduce_identity_or_file_gate(monkeypatch):
    monkeypatch.setattr(stage, "_witness_binding", lambda **k: None)
    monkeypatch.setattr(
        stage.os, "getuid", lambda: pytest.fail("old mode identity gate"), raising=False
    )
    assert stage._witness_open(pane=True) is None


@pytest.mark.skipif(not hasattr(os, "fork"), reason="POSIX synthetic child protocol only")
@pytest.mark.parametrize("kind", ["PARENT", "TIMEOUT", "GATE", "SETUP", "CHDIR", "EXEC"])
def test_actual_child_branch_reports_fixed_failure_and_preserves_exit(monkeypatch, kind):
    gate_r, gate_w = os.pipe()
    report_r, report_w = os.pipe()
    os.write(gate_w, b"X" if kind == "GATE" else b"R")
    pid = os.fork()
    if pid == 0:
        stage._WITNESS = SimpleNamespace()  # Enable only existing-pipe diagnostics.
        stage._prctl = lambda *a: None
        if kind == "TIMEOUT":
            stage.select.select = lambda *a: ([], [], [])
        if kind == "SETUP":
            stage._prctl = lambda *a: (_ for _ in ()).throw(OSError(13, "secret"))
        stage.os.chdir = lambda *a: None
        if kind == "CHDIR":
            stage.os.chdir = lambda *a: (_ for _ in ()).throw(OSError(13, "secret"))
        stage.os.execve = lambda *a: (_ for _ in ()).throw(OSError(13, "secret"))
        stage._child(
            gate_r,
            report_w,
            None,
            1,
            -1 if kind == "PARENT" else os.getppid(),
            False,
            "blocked",
            None,
            (),
            False,
        )
        os._exit(99)
    os.close(gate_r)
    os.close(gate_w)
    os.close(report_w)
    waited, status = os.waitpid(pid, 0)
    raw = os.read(report_r, 64)
    os.close(report_r)
    assert waited == pid
    ack = raw.startswith(b"R")
    frames = stage._decode_child_frames(raw[1:] if ack else raw)
    assert frames is not None and frames[0]["kind"] == kind
    assert ack == (kind in ("CHDIR", "EXEC"))
    assert os.waitstatus_to_exitcode(status) == (
        40 if kind in ("PARENT", "TIMEOUT", "GATE") else 41
    )


@pytest.mark.parametrize("failure", ["exception", "short"])
def test_gate_failure_has_enter_but_no_return_or_ack(writer, monkeypatch, failure):
    w, _, _ = writer
    monkeypatch.setattr(stage, "_WITNESS", w)
    w.hold = True
    child = stage._Owned(123, 20, 21, 22, {"pid": 123, "start_ticks": 789})
    monkeypatch.setattr(child, "alive", lambda: True)
    monkeypatch.setattr(stage, "_identity", lambda *a: child.identity)

    def write(*args):
        if failure == "exception":
            raise BrokenPipeError(32, "private")
        return 0

    monkeypatch.setattr(stage.os, "write", write)
    with pytest.raises((BrokenPipeError, stage.StageDenied)):
        child.release()
    assert not child.released and not child.acknowledged
    assert [e["stage"] for e in w.buffer][-1] == "GATE_WRITE_ENTER"
    assert not any(e["stage"] == "GATE_WRITE_RETURNED" for e in w.buffer)


@pytest.mark.parametrize("failure", [False, True])
def test_cleanup_signal_request_and_actual_result_are_distinct(writer, monkeypatch, failure):
    w, data, _ = writer
    monkeypatch.setattr(stage, "_WITNESS", w)

    def send(*args):
        if failure:
            raise PermissionError(13, "private")

    monkeypatch.setattr(stage.signal, "pidfd_send_signal", send, raising=False)
    if failure:
        with pytest.raises(PermissionError):
            stage._witness_signal(8, 15, 123, 789)
    else:
        stage._witness_signal(8, 15, 123, 789)
    events = stage._witness_read(bytes(data), BIND)["events"]
    rows = [e for e in events if e["stage"] == "CLEANUP_SIGNAL"]
    assert rows[0]["requested"] is True
    assert rows[1]["result"] is (not failure)
    assert all(row["pid"] == 123 for row in rows[:2])


def test_pre_fork_failure_never_invents_reaped_exit_zero(writer, monkeypatch):
    w, data, _ = writer
    monkeypatch.setattr(stage, "_WITNESS", w)
    monkeypatch.setattr(stage, "_native", lambda: None)
    monkeypatch.setattr(stage.os, "pipe", lambda: (_ for _ in ()).throw(OSError(24, "private")))
    with pytest.raises(stage.StageDenied):
        stage._spawn_gated(None, fixture=True, seconds=1)
    events = stage._witness_read(bytes(data), BIND)["events"]
    assert not any(e["stage"] == "CHILD_REAPED" for e in events)


def test_registration_failure_drains_report_after_reap_before_close(writer, monkeypatch):
    w, _, _ = writer
    monkeypatch.setattr(stage, "_WITNESS", w)
    monkeypatch.setattr(stage, "_native", lambda: None)
    events = []
    pipes = iter(((10, 11), (12, 13)))
    real_os = stage.os

    class ModelOS:
        WNOHANG = 1

        def __getattr__(self, name):
            return getattr(real_os, name)

        def pipe(self):
            return next(pipes)

        def fork(self):
            return 123

        def getpid(self):
            return 321

        def get_inheritable(self, fd):
            return False

        def close(self, fd):
            events.append(("close", fd))

        def pidfd_open(self, *args):
            raise OSError(24, "private")

        def waitpid(self, pid, flags):
            events.append(("reap", pid))
            return pid, 40 << 8

        def set_blocking(self, *args):
            pass

        def read(self, fd, count):
            events.append(("read", fd))
            return stage._child_failure_frame("GATE", 0, 1234)

    monkeypatch.setattr(stage, "os", ModelOS())
    fake_signal = SimpleNamespace(
        SIG_BLOCK=1,
        SIG_SETMASK=2,
        SIGINT=2,
        SIGTERM=15,
        SIGHUP=1,
        pthread_sigmask=lambda *args: set(),
    )
    monkeypatch.setattr(stage, "signal", fake_signal)
    with pytest.raises(stage.StageDenied):
        stage._spawn_gated(None, fixture=True, seconds=1)
    assert events.index(("reap", 123)) < events.index(("read", 12)) < events.index(("close", 12))


def test_prepare_original_cgroup_denial_precedes_any_witness_creation(monkeypatch):
    window = SimpleNamespace(persistent=True, nonce=BIND["nonce"], claims={"schema_version": 4})
    monkeypatch.setattr(stage, "_unclaimed", lambda window: None)
    monkeypatch.setattr(stage, "_manager", lambda *a, **k: {"ControlGroup": "foreign"})
    monkeypatch.setattr(stage, "_cgroup", lambda pid: "original")
    monkeypatch.setattr(
        stage, "_witness_open", lambda **k: pytest.fail("witness before original guard")
    )
    with pytest.raises(stage.StageDenied, match="^backend_denied$"):
        stage._prepare(window)
