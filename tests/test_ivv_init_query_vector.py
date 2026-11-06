"""Closed Init vector over pinned SDK bodies and modeled external scheduling only."""

import ast
import hashlib
import json
import struct
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_ivv_recovery_capture import module
from test_ivv_reference_parent_chain import official_reference

METHOD = "init-query-vector-v1"


def instrumented(tmp_path, monkeypatch, case="normal"):
    f = official_reference(tmp_path, monkeypatch, case)
    f.plan["_reference_method"] = METHOD
    f.plan["policy_ref"] = dict(path="/immutable/policy.json", sha256="e" * 64)
    f.plan["provider_evidence_ref"] = dict(path="/immutable/provider.json", sha256="f" * 64)
    control = dict(
        schema_id="qm.ivv.reference-control.v2",
        method=METHOD,
        nonce="a" * 32,
        reference_attempt=f.plan["_recovery_attempt"],
        capture_attempt="connection-000002",
        reference_context="b" * 32,
        capture_context="c" * 32,
        catalog_sha256=f.plan["catalog_sha256"],
        sdk_pins_sha256=f.plan["sdk_pins_sha256"],
        policy_sha256=f.plan["policy_ref"]["sha256"],
    )
    raw = f.helper._canonical(control)
    f.plan["reference_init_ref"] = dict(
        path=str(
            __import__("pathlib").Path(f.plan["provider_evidence_ref"]["path"]).parent
            / "reference-control.json"
        ),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    original = f.helper._read_root_ref
    monkeypatch.setattr(
        f.helper,
        "_read_root_ref",
        lambda ref, **kw: raw if ref == f.plan["reference_init_ref"] else original(ref, **kw),
    )

    def factory(o, w, p, c):
        backend = f.helper._InstrumentedReferenceBackend(o, w, p, c, modules=f.modules)
        f.made.append(backend)
        return backend

    f.factory = factory
    return f


def run(f):
    return f.helper._run_reference_init(
        f.plan, f.root, backend_factory=f.factory, clock=f.clock, sync_dir=lambda _: None
    )


def late_overwrite(tmp_path, monkeypatch, mutate=None):
    f = instrumented(tmp_path, monkeypatch, "write_only")
    if mutate is not None:
        mutate(f.helper)
    base = f.modules[0].OpenQuoteContext.__mro__[1]
    env = base.__init__.__globals__
    notified = []

    def after_query_failure(*args):
        # The frozen SDK already consumed Timeout and returned NON_OK. Schedule
        # a real frozen receive/notify path before its Init delegate returns.
        req = f.transport.request_ref()
        assert req.err is env["PacketErr"].Timeout
        f.transport.received = [f.transport.frame()]
        f.transport.pump()
        assert req.err is env["PacketErr"].Ok
        notified.append(req)

    env["logger"].warning2 = after_query_failure
    result = run(f)
    return f, result, notified


def assert_late_terminal(result):
    assert result["schema_id"] == "qm.ivv.reference-init-terminal.v3"
    assert result["method"] == METHOD
    assert result["init_delegate_return"] == "NON_OK"
    assert result["constructor_status"] == "NOT_READY"
    vector = result["query_vector"]
    assert vector["primitive_wait"] == "FALSE"
    assert vector["packet_err_snapshot"] == "Timeout"
    assert vector["unpack"] == vector["ret_type"] == "UNOBSERVED"
    assert vector["attribution"] == "RACE_OR_UNKNOWN"
    assert vector["receive"]["target_notify_err"] == "Ok"
    assert vector["receive"]["notify_when"] == "AFTER_WAIT_END"
    assert vector["receive"]["first_ms"]["unpack"] is None
    assert all(result["normal_close"].values())
    assert "PRIVATE" not in json.dumps(result)


def test_frozen_sdk_late_overwrite_does_not_invent_unpack(tmp_path, monkeypatch):
    f, result, notified = late_overwrite(tmp_path, monkeypatch)
    assert_late_terminal(result)
    assert len(notified) == 1
    assert f.transport.writes == 1 and f.book.usage()["init_connect"] == 1
    assert f.book.usage()["keepalive"] == f.book.usage()["business_requests"] == 0


def test_ram_only_wrong_late_err_classifier_is_rejected(tmp_path, monkeypatch):
    def mutate(h):
        original = h._InstrumentedReferenceBackend.freeze_query_vector

        def wrong(self):
            result = original(self)
            # Deliberately wrong: late Ok does not imply actual unpack entry.
            if self._query_request.err.name == "Ok":
                result["unpack"] = "OK"
            return result

        monkeypatch.setattr(h._InstrumentedReferenceBackend, "freeze_query_vector", wrong)

    _, result, _ = late_overwrite(tmp_path, monkeypatch, mutate)
    with pytest.raises(AssertionError):
        assert_late_terminal(result)


def test_complete_vector_survives_parent_ipc_and_standalone_codec(tmp_path, monkeypatch):
    _, terminal, _ = late_overwrite(tmp_path, monkeypatch)
    r = module("ivv_trusted_runner")
    error = r._reference_result(terminal)
    obs = r._reference_from_error(error)
    assert obs["schema_id"] == "qm.ivv.reference-init-observation.v3"
    assert obs["method"] == METHOD and obs["query_vector"] == terminal["query_vector"]
    assert obs["operation_failed"] is False and obs["parent_closed"] is False
    packet = r._failed_packet(error)
    assert r._reference_from_error(r._child_failure(packet)) == obs
    # Exact function extraction models the frozen private standalone codec;
    # dependency on an unextracted new helper must fail here.
    names = {"select_reference_observation"}
    tree = ast.parse(Path(r.__file__).read_text(encoding="utf8"))
    env = dict(json=json, re=__import__("re"), need=r.need)
    exec(
        compile(
            ast.Module(
                body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names],
                type_ignores=[],
            ),
            "codec",
            "exec",
        ),
        env,
    )
    assert env["select_reference_observation"](obs) == obs
    obs["query_vector"]["socket"]["unread"] = "PAYLOAD"
    with pytest.raises(r.Refused):
        env["select_reference_observation"](obs)


@pytest.mark.parametrize(
    "case,wait,unpack,ret_type",
    [
        ("normal", "TRUE", "OK", "OK"),
        ("fragmented", "TRUE", "OK", "OK"),
        ("write_only", "FALSE", "UNOBSERVED", "UNOBSERVED"),
        ("queued", "FALSE", "UNOBSERVED", "UNOBSERVED"),
        ("invalid", "TRUE", "UNOBSERVED", "UNOBSERVED"),
        ("wrong_serial", "FALSE", "UNOBSERVED", "UNOBSERVED"),
    ],
)
def test_frozen_sdk_complete_receive_branches(tmp_path, monkeypatch, case, wait, unpack, ret_type):
    f = instrumented(tmp_path, monkeypatch, case)
    result = run(f)
    vector = result["query_vector"]
    assert vector["send"] == "OK"
    assert vector["primitive_wait"] == wait
    assert vector["unpack"] == unpack and vector["ret_type"] == ret_type
    assert result["state"] == ("REFERENCE_READY_CLOSED" if unpack == "OK" else "REFERENCE_FAILED")
    req = f.made[0]._query_request
    assert "wait" not in vars(req) and "wait" not in vars(req.event)
    assert (
        req.unpack_func
        == f.modules[0].OpenQuoteContext.__init__.__globals__["InitConnect"].unpack_rsp
    )
    assert all(result["normal_close"].values())


@pytest.mark.parametrize(
    "outcome,want",
    [(True, "TRUE"), (False, "FALSE"), (None, "UNKNOWN"), (1, "UNKNOWN"), ("raise", "RAISED")],
)
def test_actual_bound_event_preserves_single_call_args_result_and_exception(
    tmp_path, monkeypatch, outcome, want
):
    f = instrumented(tmp_path, monkeypatch, "write_only")
    env = f.modules[0].OpenQuoteContext.__init__.__globals__
    calls = []
    failure = KeyboardInterrupt("PRIVATE")

    def wait(event, *args, **kwargs):
        calls.append((args, kwargs))
        if outcome == "raise":
            raise failure
        return outcome

    env["threading"].Event.wait = wait
    result = run(f)
    assert calls == [((), {"timeout": 20})]
    assert result["query_vector"]["primitive_wait"] == want
    assert result["query_vector"]["unpack"] == (
        "RAISED" if outcome is True or type(outcome) is int else "UNOBSERVED"
    )
    assert "wait" not in vars(f.made[0]._query_request.event)


@pytest.mark.parametrize(
    "fault,want", [("non_ok", "NON_OK"), ("raise", "RAISED"), ("alias", "UNKNOWN")]
)
def test_saved_send_failure_is_observed_even_when_sdk_catches(tmp_path, monkeypatch, fault, want):
    f = instrumented(tmp_path, monkeypatch, "queued")
    calls = []

    def send(*args, **kwargs):
        calls.append((args, kwargs))
        if fault == "raise":
            raise OSError("PRIVATE")
        return (True if fault == "alias" else -1), "PRIVATE"

    f.transport.net.send = send
    result = run(f)
    assert len(calls) == 1
    assert result["query_vector"]["send"] == want
    assert result["query_vector"]["primitive_wait"] == "UNOBSERVED"
    assert result["query_vector"]["unpack"] == "UNOBSERVED"


@pytest.mark.parametrize("fault", ["method", "missing", "extra", "v1_flag", "derived_flag"])
def test_held_control_and_derived_method_cannot_disagree(tmp_path, monkeypatch, fault):
    f = instrumented(tmp_path, monkeypatch)
    raw = f.helper._read_root_ref(f.plan["reference_init_ref"])
    control = json.loads(raw)
    if fault == "method":
        control["method"] = "arbitrary"
    elif fault == "missing":
        del control["method"]
    elif fault == "extra":
        control["observer"] = True
    elif fault == "v1_flag":
        control["schema_id"] = "qm.ivv.reference-control.v1"
        del control["method"]
    elif fault == "derived_flag":
        f.plan["_reference_method"] = None
    changed = f.helper._canonical(control)
    f.plan["reference_init_ref"]["sha256"] = hashlib.sha256(changed).hexdigest()
    monkeypatch.setattr(f.helper, "_read_root_ref", lambda *args, **kw: changed)
    with pytest.raises(f.helper.CaptureRejected, match="reference_(control_shape|method_binding)"):
        run(f)
    assert not f.made and f.transport.writes == 0


@pytest.mark.parametrize(
    "path,bad",
    [
        (("primitive_wait",), False),
        (("ret_type",), 0),
        (("send",), "payload"),
        (("unpack",), []),
        (("guard", "stage"), "private"),
        (("guard", "code"), "private"),
        (("socket", "identity"), "fd23"),
        (("socket", "wait_delta_ms"), True),
        (("socket", "wait_delta_ms"), 480001),
        (("socket", "readable"), True),
        (("socket", "sample_order"), "ATOMIC"),
        (("receive", "polls"), 4097),
        (("receive", "read_bytes"), True),
        (("receive", "first_ms", "wait"), -1),
    ],
)
def test_terminal_and_runner_reject_nonclosed_vector(path, bad):
    from test_ivv_reference_init_return import terminal

    h, r = module("capture_opend_ivv_daily"), module("ivv_trusted_runner")
    value = dict(
        terminal("v2"),
        schema_id="qm.ivv.reference-init-terminal.v3",
        method=METHOD,
        query_vector=h._empty_query_vector(),
    )
    parent = value["query_vector"]
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = bad
    with pytest.raises(h.CaptureRejected):
        h._select_reference_terminal(value)
    obs = dict(
        schema_id="qm.ivv.reference-init-observation.v3",
        method=METHOD,
        query_vector=value["query_vector"],
        init_delegate_return="UNKNOWN",
        reference_control_sha256="a" * 64,
        constructor_status="NOT_READY",
        operation_failed=False,
        close_failed=False,
        parent_closed=False,
        normal_close=value["normal_close"],
    )
    with pytest.raises(r.Refused):
        r.select_reference_observation(obs)


@pytest.mark.parametrize(
    "error,want,number",
    [
        (OSError(9, "PRIVATE"), "OS", 9),
        (BlockingIOError(11, "PRIVATE"), "BLOCKED", 11),
        (BrokenPipeError(32, "PRIVATE"), "BROKEN_PIPE", 32),
        (ConnectionResetError(104, "PRIVATE"), "CONN_RESET", 104),
        (PermissionError(13, "PRIVATE"), "PERMISSION", 13),
        (TypeError("PRIVATE"), "TYPE", None),
        (KeyboardInterrupt("PRIVATE"), "INTERRUPT", None),
    ],
)
def test_finite_exception_identity_errno_and_same_exception_preserved(
    tmp_path, monkeypatch, error, want, number
):
    f = instrumented(tmp_path, monkeypatch, "queued")
    writer = f.helper._Writer(f.root, lambda _: None)
    observer = f.helper._InstrumentedReferenceObserver(f.plan, writer, f.clock)
    backend = f.helper._InstrumentedReferenceBackend(
        observer, writer, f.plan, f.clock, modules=f.modules
    )
    calls = []

    def fail(*args, **kw):
        calls.append((args, kw))
        raise error

    with pytest.raises(type(error)) as caught:
        backend._observe_init_return("send", fail, 23, b"PRIVATE")
    assert caught.value is error and len(calls) == 1
    assert backend.query_vector["errors"]["send"] == dict(type=want, errno=number)
    assert "PRIVATE" not in json.dumps(backend.query_vector)


def test_unknown_error_subclass_does_not_touch_private_errno(tmp_path, monkeypatch):
    class PrivateError(OSError):
        @property
        def errno(self):
            pytest.fail("private errno property inspected")

    f = instrumented(tmp_path, monkeypatch, "queued")
    writer = f.helper._Writer(f.root, lambda _: None)
    observer = f.helper._InstrumentedReferenceObserver(f.plan, writer, f.clock)
    backend = f.helper._InstrumentedReferenceBackend(
        observer, writer, f.plan, f.clock, modules=f.modules
    )
    error = PrivateError("PRIVATE")

    def fail():
        raise error

    with pytest.raises(PrivateError):
        backend._observe_init_return("unpack", fail)
    assert backend.query_vector["errors"]["unpack"] == dict(type="UNKNOWN", errno=None)


@pytest.mark.parametrize(
    "field,result",
    [
        ("send", (0,)),
        ("send", (0, "PRIVATE", None)),
        ("send", (False, "PRIVATE")),
        ("send", [0, "PRIVATE"]),
        ("unpack", (0, "PRIVATE")),
        ("unpack", (0, "PRIVATE", None, None)),
        ("unpack", (False, "PRIVATE", None)),
    ],
)
def test_exact_delegate_tuple_arity_and_identity(tmp_path, monkeypatch, field, result):
    f = instrumented(tmp_path, monkeypatch, "queued")
    writer = f.helper._Writer(f.root, lambda _: None)
    observer = f.helper._InstrumentedReferenceObserver(f.plan, writer, f.clock)
    backend = f.helper._InstrumentedReferenceBackend(
        observer, writer, f.plan, f.clock, modules=f.modules
    )
    calls = []

    def returned(*args):
        calls.append(args)
        return result

    assert backend._observe_init_return(field, returned, NS(retType=0)) is result
    assert len(calls) == 1 and backend.query_vector[field] == "UNKNOWN"
    assert backend.query_vector["errors"][field] == dict(type="NONE", errno=None)


@pytest.mark.parametrize(
    "kind,want,ret_type",
    [
        ("ordinary", "OK", "OK"),
        ("non_ok", "NON_OK", "NON_OK"),
        ("missing_s2c", "NON_OK", "OK"),
    ],
)
def test_real_frozen_init_unpack_ret_type_families(tmp_path, monkeypatch, kind, want, ret_type):
    f = instrumented(tmp_path, monkeypatch)
    env = f.modules[0].OpenQuoteContext.__init__.__globals__
    frame = f.transport.received[0]
    response = type(env["pb_map"][1001])()
    response.ParseFromString(frame[44:])
    if kind == "non_ok":
        response.retType = 17
    if kind == "missing_s2c":
        response.ClearField("s2c")
    body = response.SerializeToString(deterministic=True)
    head = list(struct.unpack(env["MESSAGE_HEAD_FMT"], frame[:44]))
    head[6], head[7] = len(body), hashlib.sha1(body).digest()
    f.transport.received = [struct.pack(env["MESSAGE_HEAD_FMT"], *head) + body]
    result = run(f)
    assert result["query_vector"]["unpack"] == want
    assert result["query_vector"]["ret_type"] == ret_type
    assert result["query_vector"]["receive"]["first_ms"]["unpack"] is not None
    assert result["query_vector"]["errors"]["unpack"] == dict(type="NONE", errno=None)


def test_frozen_query_actual_unpack_after_timeout_snapshot_is_not_gated(tmp_path, monkeypatch):
    f = instrumented(tmp_path, monkeypatch, "write_only")
    env = f.modules[0].OpenQuoteContext.__init__.__globals__
    query = env["OpenContextBase"]._query_sync
    # Source line is selected from the verified function body, never hardcoded.
    from test_ivv_init_observation import pinned_ast

    node = next(
        n
        for n in ast.walk(pinned_ast("common/open_context_base.py"))
        if isinstance(n, ast.FunctionDef) and n.name == "_query_sync"
    )
    condition = next(n for n in node.body if isinstance(n, ast.If))
    scheduled = []

    def schedule(frame, event, arg):
        if (
            frame.f_code is query.__code__
            and event == "line"
            and frame.f_lineno == condition.lineno
        ):
            assert f.made[0].query_vector["packet_err_snapshot"] == "Timeout"
            f.transport.received = [f.transport.frame()]
            f.transport.pump()
            scheduled.append(True)
        return schedule

    previous = sys.gettrace()
    try:
        sys.settrace(schedule)
        result = run(f)
    finally:
        sys.settrace(previous)
    assert sys.gettrace() is previous
    assert scheduled == [True]
    assert result["constructor_status"] == "READY"
    vector = result["query_vector"]
    assert vector["primitive_wait"] == "FALSE" and vector["packet_err_snapshot"] == "Timeout"
    assert vector["unpack"] == vector["ret_type"] == "OK"
    assert vector["attribution"] == "RACE_OR_UNKNOWN"


def socket_model(f, monkeypatch, *, size=0, readable=False, selector="READ", fault=None):
    sock = f.transport.conn.sock
    sock.fd = 1000000
    sock.inode = 2
    sock.fileno = lambda: sock.fd
    calls = []
    original_stat = f.helper.os.fstat

    def own_stat(fd):
        if fd != 1000000:
            return original_stat(fd)
        if fault == "fstat_denied":
            raise PermissionError(13, "PRIVATE")
        return NS(st_dev=1, st_ino=sock.inode, st_mode=__import__("stat").S_IFSOCK)

    monkeypatch.setattr(f.helper.os, "fstat", own_stat)

    def key(owned):
        assert owned is sock
        if selector == "ABSENT":
            raise KeyError("PRIVATE")
        return NS(fileobj=sock, data=f.transport.conn, events=1 if selector == "READ" else 0)

    f.transport.net._selector.get_key = key

    def select_owned(read, write, error, timeout):
        assert read == [sock] and write == error == [] and timeout == 0
        req = f.made[0]._query_request
        assert "wait" not in vars(req) and "wait" not in vars(req.event)
        calls.append("select")
        if fault == "denied":
            raise PermissionError(13, "PRIVATE")
        if fault == "drift":
            sock.fd += 1
        if fault == "reuse":
            sock.inode += 1
        return ([sock] if readable else []), [], []

    monkeypatch.setattr(f.helper.select, "select", select_owned)

    def unread(fd, code, data):
        assert fd == 1000000 and code == 123 and data == struct.pack("i", 0)
        calls.append("unread")
        if fault == "denied":
            raise PermissionError(13, "PRIVATE")
        return struct.pack("i", size)

    monkeypatch.setitem(sys.modules, "fcntl", NS(ioctl=unread))
    monkeypatch.setitem(sys.modules, "termios", NS(FIONREAD=123))
    return calls


@pytest.mark.parametrize(
    "size,want",
    [
        (0, "ZERO"),
        (1, "LE_1K"),
        (1024, "LE_1K"),
        (1025, "LE_64K"),
        (65536, "LE_64K"),
        (65537, "GT_64K"),
        (-1, "UNKNOWN"),
    ],
)
def test_owned_socket_nonconsuming_snapshot_and_unread_buckets(tmp_path, monkeypatch, size, want):
    f = instrumented(tmp_path, monkeypatch, "write_only")
    calls = socket_model(f, monkeypatch, size=size, readable=size > 0)
    result = run(f)
    snapshot = result["query_vector"]["socket"]
    assert snapshot == dict(
        identity="VERIFIED",
        selector="READ",
        readable="TRUE" if size > 0 else "FALSE",
        unread=want,
        wait_delta_ms=0,
        sample_order="SEQUENTIAL",
    )
    assert calls == ["select", "unread"]
    assert f.transport.reads == 0 and f.transport.writes == 1
    assert result["primary_failure"]["code"] == "sdk_initial_connection_failed"
    assert all(result["normal_close"].values())


@pytest.mark.parametrize("fault", ["denied", "drift", "unavailable", "reuse", "fstat_denied"])
def test_optional_owned_socket_fault_remains_unknown_and_normal_close(tmp_path, monkeypatch, fault):
    f = instrumented(tmp_path, monkeypatch, "write_only")
    calls = socket_model(f, monkeypatch, fault=fault)
    if fault == "unavailable":
        del f.transport.conn.sock.fileno
    result = run(f)
    snapshot = result["query_vector"]["socket"]
    assert snapshot["identity"] == (
        "DRIFT"
        if fault in ("drift", "reuse")
        else "UNKNOWN"
        if fault in ("unavailable", "fstat_denied")
        else "VERIFIED"
    )
    assert snapshot["readable"] == snapshot["unread"] == "UNKNOWN"
    assert result["query_vector"]["attribution"] == "RACE_OR_UNKNOWN"
    assert result["primary_failure"]["code"] == "sdk_initial_connection_failed"
    assert all(result["normal_close"].values())
    assert f.transport.reads == 0
    if fault in ("unavailable", "fstat_denied"):
        assert calls == []


@pytest.mark.parametrize("selector", ["READ", "NO_READ", "ABSENT"])
def test_existing_selector_interest_is_scalar_only(tmp_path, monkeypatch, selector):
    f = instrumented(tmp_path, monkeypatch, "write_only")
    socket_model(f, monkeypatch, selector=selector)
    result = run(f)
    assert result["query_vector"]["socket"]["selector"] == selector


@pytest.mark.parametrize("fault", ["live", "wire", "request", "post_constructor"])
def test_sticky_guard_survives_sdk_catch_without_false_ready(tmp_path, monkeypatch, fault):
    f = instrumented(tmp_path, monkeypatch, "queued")
    if fault == "live":
        checks = []

        def live():
            checks.append(True)
            if len(checks) >= 4:
                raise f.helper.CaptureRejected("PRIVATE")

        f.plan["_live_verifier"] = live
    elif fault == "wire":

        def refused(raw):
            raise f.helper.CaptureRejected("wire_header")

        f.modules[1].parse_head = refused
    elif fault == "request":
        f.modules[1].parse_head = lambda raw: dict(proto_id=1004, serial_no=7)
    else:

        def live():
            if f.made and f.made[0].constructor_returned:
                raise RuntimeError("PRIVATE")

        f.plan["_live_verifier"] = live
    result = run(f)
    guard = result["query_vector"]["guard"]
    assert (
        guard["stage"]
        == dict(live="LIVE", wire="WIRE", request="REQUEST", post_constructor="POST_CONSTRUCTOR")[
            fault
        ]
    )
    assert guard["code"] != "NONE"
    assert result["state"] == "REFERENCE_FAILED" and all(result["normal_close"].values())


def test_partial_constructor_close_and_event_restore_failure_preserve_primary(
    tmp_path, monkeypatch
):
    f = instrumented(tmp_path, monkeypatch, "write_only")
    env = f.modules[0].OpenQuoteContext.__init__.__globals__
    original = env["threading"].Event
    failure = KeyboardInterrupt("PRIVATE")

    class Event(original):
        def wait(self, timeout):
            raise failure

        def __delattr__(self, name):
            if name == "wait":
                raise RuntimeError("PRIVATE-RESTORE")
            return super().__delattr__(name)

    env["threading"].Event = Event
    writer = f.helper._Writer(f.root, lambda _: None)
    observer = f.helper._InstrumentedReferenceObserver(f.plan, writer, f.clock)
    backend = f.helper._InstrumentedReferenceBackend(
        observer, writer, f.plan, f.clock, modules=f.modules
    )
    f.book.may_connect(f.plan["_recovery_attempt"])
    with pytest.raises(KeyboardInterrupt) as caught:
        backend.open()
    assert caught.value is failure
    vector = backend.freeze_query_vector()
    assert vector["guard"] == dict(stage="RESTORE", code="OTHER_GUARD")
    assert vector["primitive_wait"] == "RAISED"
    backend.close()
    assert all(backend.close_evidence().values())
    assert observer.poison == "reference_restore_failed"


def test_optional_recorder_failure_still_runs_owned_close(tmp_path, monkeypatch):
    f = instrumented(tmp_path, monkeypatch, "write_only")

    def unavailable(self):
        raise PermissionError(13, "PRIVATE")

    monkeypatch.setattr(f.helper._InstrumentedReferenceBackend, "freeze_query_vector", unavailable)
    result = run(f)
    assert all(result["normal_close"].values())
    assert result["close_failure"] is None
    assert result["primary_failure"]["code"] == "sdk_initial_connection_failed"
    assert result["query_vector"]["receive"]["recorder_error"] is True
    assert result["query_vector"]["attribution"] == "RACE_OR_UNKNOWN"


def test_invalid_request_binding_refuses_at_constructor_boundary(tmp_path, monkeypatch):
    f = instrumented(tmp_path, monkeypatch)
    env = f.modules[0].OpenQuoteContext.__init__.__globals__
    pack = env["InitConnect"].pack_req

    def foreign_serial(**kwargs):
        code, msg, raw, proto, serial = pack(**kwargs)
        head = list(struct.unpack(env["MESSAGE_HEAD_FMT"], raw[:44]))
        head[5] = 8
        return code, msg, struct.pack(env["MESSAGE_HEAD_FMT"], *head) + raw[44:], proto, serial

    env["InitConnect"].pack_req = staticmethod(foreign_serial)
    result = run(f)
    assert result["state"] == "REFERENCE_FAILED"
    assert result["query_vector"]["guard"] == dict(stage="POST_CONSTRUCTOR", code="OTHER_GUARD")
    assert result["query_vector"]["attribution"] == "RACE_OR_UNKNOWN"
    assert all(result["normal_close"].values())


def test_true_event_without_receive_notify_is_race_unknown(tmp_path, monkeypatch):
    f = instrumented(tmp_path, monkeypatch, "write_only")
    socket_model(f, monkeypatch)
    env = f.modules[0].OpenQuoteContext.__init__.__globals__
    env["threading"].Event.wait = lambda self, timeout: True
    result = run(f)
    vector = result["query_vector"]
    assert vector["primitive_wait"] == "TRUE" and vector["unpack"] == "RAISED"
    assert vector["receive"]["target_notify_err"] == "UNOBSERVED"
    assert vector["attribution"] == "RACE_OR_UNKNOWN"


@pytest.mark.parametrize("path", [("guard",), ("socket",), ("errors",), ("receive",)])
@pytest.mark.parametrize("fault", ["missing", "extra"])
def test_nested_closed_vector_keys_reject_missing_and_extra(path, fault):
    h = module("capture_opend_ivv_daily")
    vector = h._empty_query_vector()
    if fault == "missing":
        vector[path[0]].pop(next(iter(vector[path[0]])))
    else:
        vector[path[0]]["private"] = "PRIVATE"
    with pytest.raises(h.CaptureRejected):
        h._select_init_query_vector(vector, h._require)


@pytest.mark.parametrize("number", [True, -1, 65536, "9", None])
def test_exact_os_errno_rejects_bool_negative_oversized_and_nonint(number):
    h = module("capture_opend_ivv_daily")
    error = OSError("PRIVATE")
    error.errno = number
    assert h._query_error_detail(error) == dict(type="OS", errno=None)


def test_arbitrary_error_metaclass_hash_and_equality_are_not_inspected():
    h = module("capture_opend_ivv_daily")

    class Meta(type):
        def __hash__(cls):
            pytest.fail("private type hash touched")

        def __eq__(cls, other):
            pytest.fail("private type comparison touched")

    class PrivateError(Exception, metaclass=Meta):
        pass

    assert h._query_error_detail(PrivateError("PRIVATE")) == dict(type="UNKNOWN", errno=None)


@pytest.mark.parametrize(
    "cls,label",
    [
        (ConnectionAbortedError, "CONN_ABORTED"),
        (ConnectionRefusedError, "CONN_REFUSED"),
        (TimeoutError, "TIMEOUT"),
        (ConnectionError, "OS"),
        (ChildProcessError, "OS"),
        (FileExistsError, "OS"),
        (FileNotFoundError, "OS"),
        (InterruptedError, "OS"),
        (IsADirectoryError, "OS"),
        (NotADirectoryError, "OS"),
        (ProcessLookupError, "OS"),
        (ValueError, "VALUE"),
        (AttributeError, "ATTRIBUTE"),
        (KeyError, "KEY"),
        (IndexError, "INDEX"),
        (RuntimeError, "RUNTIME"),
        (AssertionError, "ASSERTION"),
        (MemoryError, "MEMORY"),
        (OverflowError, "OVERFLOW"),
        (Exception, "EXCEPTION"),
        (SystemExit, "SYSTEM_EXIT"),
        (GeneratorExit, "GENERATOR_EXIT"),
    ],
)
def test_remaining_fixed_builtin_error_categories(cls, label):
    h = module("capture_opend_ivv_daily")
    assert h._query_error_detail(cls()) == dict(type=label, errno=None)
    assert h._query_error_detail(h.CaptureRejected("PRIVATE")) == dict(type="GUARD", errno=None)


@pytest.mark.parametrize(
    "field,allowed",
    [
        ("attribution", "BOUND UNBOUND RACE_OR_UNKNOWN"),
        ("send", "UNOBSERVED ENTERED OK NON_OK RAISED UNKNOWN"),
        ("primitive_wait", "UNOBSERVED TRUE FALSE RAISED UNKNOWN"),
        ("packet_err_snapshot", "UNOBSERVED Ok Timeout Invalid Disconnect SendFail UNKNOWN"),
        ("unpack", "UNOBSERVED ENTERED OK NON_OK RAISED UNKNOWN"),
        ("ret_type", "UNOBSERVED OK NON_OK UNKNOWN"),
    ],
)
def test_all_closed_vector_enum_literals_roundtrip(field, allowed):
    h, r = module("capture_opend_ivv_daily"), module("ivv_trusted_runner")
    from test_ivv_reference_parent_chain import observation

    for literal in allowed.split():
        vector = h._empty_query_vector()
        vector[field] = literal
        if literal == "RAISED":
            vector["errors"]["wait" if field == "primitive_wait" else field] = dict(
                type="UNKNOWN", errno=None
            )
        assert h._select_init_query_vector(vector, h._require) == vector
        obs = dict(
            observation(),
            schema_id="qm.ivv.reference-init-observation.v3",
            init_delegate_return="UNKNOWN",
            method=METHOD,
            query_vector=vector,
        )
        assert r.select_reference_observation(obs)["query_vector"] == vector


def test_ret_type_observer_does_not_read_private_payload_fields(tmp_path, monkeypatch):
    f = instrumented(tmp_path, monkeypatch, "queued")
    writer = f.helper._Writer(f.root, lambda _: None)
    observer = f.helper._InstrumentedReferenceObserver(f.plan, writer, f.clock)
    backend = f.helper._InstrumentedReferenceBackend(
        observer, writer, f.plan, f.clock, modules=f.modules
    )

    class PrivateResponse:
        retType = object()

        def __getattr__(self, name):
            pytest.fail("private response field inspected")

    original = (0, "PRIVATE", object())
    assert (
        backend._observe_init_return("unpack", lambda pb: original, PrivateResponse()) is original
    )
    assert backend.query_vector["ret_type"] == "UNKNOWN"
    assert backend.query_vector["unpack"] == "OK"
    assert "PRIVATE" not in json.dumps(backend.query_vector)


def test_bound_event_preexisting_attribute_is_restored(tmp_path, monkeypatch):
    from types import MethodType

    f = instrumented(tmp_path, monkeypatch, "write_only")
    env = f.modules[0].OpenQuoteContext.__init__.__globals__
    base = env["threading"].Event
    originals = []

    class Event(base):
        def __init__(self):
            self.wait = MethodType(base.wait, self)
            originals.append(self.wait)

    env["threading"].Event = Event
    result = run(f)
    assert f.made[0]._query_request.event.wait is originals[0]
    assert result["query_vector"]["primitive_wait"] == "FALSE"


def test_event_truthy_return_object_is_not_coerced_or_replaced(tmp_path, monkeypatch):
    f = instrumented(tmp_path, monkeypatch, "write_only")
    env = f.modules[0].OpenQuoteContext.__init__.__globals__
    observed = []

    class Truthy:
        def __bool__(self):
            observed.append(self)
            return True

    returned = Truthy()
    calls = []

    def wait(event, **kwargs):
        calls.append(kwargs)
        return returned

    env["threading"].Event.wait = wait
    result = run(f)
    assert calls == [dict(timeout=20)] and observed == [returned]
    assert result["query_vector"]["primitive_wait"] == "UNKNOWN"


def test_restore_failure_without_primary_is_a_real_failure(tmp_path, monkeypatch):
    f = instrumented(tmp_path, monkeypatch, "write_only")
    env = f.modules[0].OpenQuoteContext.__init__.__globals__
    original = env["threading"].Event

    class Event(original):
        def __delattr__(self, name):
            if name == "wait":
                raise RuntimeError("PRIVATE")
            return super().__delattr__(name)

    env["threading"].Event = Event
    result = run(f)
    assert result["primary_failure"]["code"] == "reference_restore_failed"
    assert result["query_vector"]["guard"] == dict(stage="RESTORE", code="OTHER_GUARD")
    assert result["state"] == "REFERENCE_FAILED" and all(result["normal_close"].values())


def test_new_observer_cannot_enter_pure_control_path(tmp_path, monkeypatch):
    f = instrumented(tmp_path, monkeypatch)
    f.plan.pop("_reference_method")
    result = run(f)
    assert result["schema_id"] == "qm.ivv.reference-init-terminal.v2"
    assert result["primary_failure"]["code"] == "reference_observer_required"
    assert f.transport.writes == 0


@pytest.mark.parametrize("kind", ["guard", "interrupt", "exit"])
@pytest.mark.parametrize("prior", ["expected_nonready", "keyboard_primary"])
def test_snapshot_mandatory_failure_and_interrupt_are_real_failures_with_owned_close(
    tmp_path, monkeypatch, kind, prior
):
    f = instrumented(tmp_path, monkeypatch, "write_only")
    socket_model(f, monkeypatch)
    error = (
        f.helper.CaptureRejected("owned_guard_required")
        if kind == "guard"
        else KeyboardInterrupt("PRIVATE")
        if kind == "interrupt"
        else SystemExit("PRIVATE")
    )

    def refusal(*args):
        raise error

    monkeypatch.setattr(f.helper.select, "select", refusal)
    if prior == "keyboard_primary":
        env = f.modules[0].OpenQuoteContext.__init__.__globals__

        def interrupted(self, timeout):
            raise KeyboardInterrupt("PRIVATE-PRIMARY")

        env["threading"].Event.wait = interrupted
    result = run(f)
    assert all(result["normal_close"].values()) and result["close_failure"] is None
    assert result["primary_failure"]["stage"] == (
        "initialize" if prior == "keyboard_primary" else "late_guard"
    )
    if prior == "keyboard_primary":
        assert result["primary_failure"]["class"] == "KeyboardInterrupt"
    assert result["query_vector"]["guard"] == dict(stage="POST_CONSTRUCTOR", code="OTHER_GUARD")
    assert result["query_vector"]["send"] == "OK"
    r = module("ivv_trusted_runner")
    obs = r._reference_from_error(r._reference_result(result))
    assert obs["operation_failed"] is True


def test_receive_hook_restoration_failure_refuses_close_after_restoring_wire(tmp_path, monkeypatch):
    f = instrumented(tmp_path, monkeypatch, "write_only")

    def refused(trace):
        raise RuntimeError("PRIVATE")

    monkeypatch.setattr(f.helper._InitReceiveTrace, "restore", refused)
    result = run(f)
    backend = f.made[0]
    assert result["close_failure"] == dict(
        stage="close", **{"class": "CaptureRejected"}, code="reference_receive_restore_failed"
    )
    assert (
        f.transport.net.send == backend._old_send
        and f.transport.net.connect == backend._old_connect
    )
    r = module("ivv_trusted_runner")
    assert r._reference_from_error(r._reference_result(result))["close_failed"] is True


@pytest.mark.parametrize("method", [METHOD, "arbitrary", True, None])
def test_actual_parent_condition_binds_complete_control_v2_without_new_admission(method):
    import inspect
    import textwrap

    import test_ivv_reference_condition as fixture

    # Reuse the actual in-memory owning-ledger fixture; change only its synthetic
    # immutable control input construction. Production and SDK bodies stay exact.
    tree = ast.parse(textwrap.dedent(inspect.getsource(fixture.ConditionOwner.fixture)))
    changed = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if (
                    kw.arg == "schema_id"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value == "qm.ivv.reference-control.v1"
                ):
                    kw.value.value = "qm.ivv.reference-control.v2"
                    if method is not None:
                        node.keywords.append(ast.keyword(arg="method", value=ast.Constant(method)))
                    changed.append(True)
    assert changed == [True]
    env = dict(vars(fixture))
    exec(compile(ast.fix_missing_locations(tree), "control-input-fixture", "exec"), env)
    case = fixture.ConditionOwner()
    try:
        r, book, value, pair_sha, native, producer, read = env["fixture"](case)
        if method == METHOD:
            transition = r.reference_capture_condition(book, pair_sha, read, native, producer)
            assert transition["pair_sha256"] == pair_sha
            outcome = book._read(value["reference_attempt"] + ".reference-condition.json")
            assert outcome["state"] == "POSITIVE"
            assert outcome["capture_attempt"] == value["capture_attempt"]
        else:
            with pytest.raises(r.Refused, match="REFERENCE_CONTROL_BINDING"):
                r.reference_capture_condition(book, pair_sha, read, native, producer)
    finally:
        case.doCleanups()


@pytest.mark.parametrize("field", ["send", "wait", "unpack"])
@pytest.mark.parametrize("metadata_kind", ["ordinary", "guard", "interrupt"])
def test_error_classifier_failure_preserves_active_delegate_exception(
    tmp_path, monkeypatch, field, metadata_kind
):
    f = instrumented(tmp_path, monkeypatch, "write_only")
    writer = f.helper._Writer(f.root, lambda _: None)
    observer = f.helper._InstrumentedReferenceObserver(f.plan, writer, f.clock)
    backend = f.helper._InstrumentedReferenceBackend(
        observer, writer, f.plan, f.clock, modules=f.modules
    )
    original = OSError(9, "PRIVATE-ORIGINAL")
    metadata = (
        RuntimeError("PRIVATE-METADATA")
        if metadata_kind == "ordinary"
        else f.helper.CaptureRejected("metadata_guard")
        if metadata_kind == "guard"
        else SystemExit("PRIVATE-METADATA")
    )

    def classifier(error):
        assert error is original
        raise metadata

    monkeypatch.setattr(f.helper, "_query_error_detail", classifier)

    def failed(*args, **kwargs):
        raise original

    if field == "wait":
        env = f.modules[0].OpenQuoteContext.__init__.__globals__
        env["threading"].Event.wait = failed
        f.book.may_connect(f.plan["_recovery_attempt"])
        action = backend.open
    else:

        def action():
            return backend._observe_init_return(field, failed, NS(retType=0))

    with pytest.raises(BaseException) as caught:
        action()
    assert caught.value is original
    assert backend.query_vector["primitive_wait" if field == "wait" else field] == "RAISED"
    assert backend.query_vector["errors"][field] == dict(type="UNKNOWN", errno=None)
    assert backend._receive_error is True
    if metadata_kind != "ordinary":
        assert observer.poison is not None
        assert observer.guard == dict(stage="REQUEST", code="OTHER_GUARD")
    if field == "wait":
        assert "wait" not in vars(backend._query_request.event)
        backend.close()
        assert all(backend.close_evidence().values())


@pytest.mark.parametrize("boundary", ["clock", "receive"])
@pytest.mark.parametrize("metadata_kind", ["ordinary", "guard", "interrupt"])
def test_wait_finally_observer_failure_preserves_active_primitive_exception(
    tmp_path, monkeypatch, boundary, metadata_kind
):
    f = instrumented(tmp_path, monkeypatch, "write_only")
    writer = f.helper._Writer(f.root, lambda _: None)
    observer = f.helper._InstrumentedReferenceObserver(f.plan, writer, f.clock)
    backend = f.helper._InstrumentedReferenceBackend(
        observer, writer, f.plan, f.clock, modules=f.modules
    )
    original = OSError(9, "PRIVATE-ORIGINAL")
    metadata = (
        RuntimeError("PRIVATE-METADATA")
        if metadata_kind == "ordinary"
        else f.helper.CaptureRejected("metadata_guard")
        if metadata_kind == "guard"
        else KeyboardInterrupt("PRIVATE-METADATA")
    )
    env = f.modules[0].OpenQuoteContext.__init__.__globals__

    def failed(*args, **kwargs):
        raise original

    env["threading"].Event.wait = failed
    mono = f.clock.mono
    receive = backend._receive
    if boundary == "clock":

        def observed_clock():
            if backend.query_vector["primitive_wait"] == "RAISED":
                raise metadata
            return mono()

        monkeypatch.setattr(f.clock, "mono", observed_clock)
    else:

        def observed_receive(method, *args):
            if method == "wait_end":
                raise metadata
            return receive(method, *args)

        monkeypatch.setattr(backend, "_receive", observed_receive)
    f.book.may_connect(f.plan["_recovery_attempt"])
    with pytest.raises(BaseException) as caught:
        backend.open()
    assert caught.value is original
    assert backend.query_vector["primitive_wait"] == "RAISED"
    assert backend.query_vector["packet_err_snapshot"] == "UNKNOWN"
    assert backend.query_vector["errors"]["wait"] == dict(type="OS", errno=9)
    assert backend._receive_error is True
    if metadata_kind != "ordinary":
        assert observer.poison is not None
        assert observer.guard == dict(stage="REQUEST", code="OTHER_GUARD")
    monkeypatch.setattr(f.clock, "mono", mono)
    monkeypatch.setattr(backend, "_receive", receive)
    assert "wait" not in vars(backend._query_request.event)
    backend.close()
    assert all(backend.close_evidence().values())


def test_classifier_guard_stays_sticky_when_sdk_catches_original_send_exception(
    tmp_path, monkeypatch
):
    f = instrumented(tmp_path, monkeypatch, "queued")
    original = OSError(9, "PRIVATE-ORIGINAL")

    def send(*args, **kwargs):
        raise original

    def classifier(error):
        assert error is original
        raise f.helper.CaptureRejected("metadata_guard")

    f.transport.net.send = send
    monkeypatch.setattr(f.helper, "_query_error_detail", classifier)
    result = run(f)
    assert result["query_vector"]["send"] == "RAISED"
    assert result["query_vector"]["errors"]["send"] == dict(type="UNKNOWN", errno=None)
    assert result["query_vector"]["guard"] == dict(stage="REQUEST", code="OTHER_GUARD")
    assert result["init_delegate_return"] == "NON_OK"
    assert all(result["normal_close"].values())
    r = module("ivv_trusted_runner")
    assert r._reference_from_error(r._reference_result(result))["operation_failed"] is True


@pytest.mark.parametrize("mandatory", [False, True])
def test_wait_metadata_failure_after_normal_return_is_unknown_or_guard(
    tmp_path, monkeypatch, mandatory
):
    f = instrumented(tmp_path, monkeypatch)
    factory = f.factory

    def observed_factory(*args):
        backend = factory(*args)
        receive = backend._receive

        def observed(method, *args):
            if method == "wait_end":
                if mandatory:
                    raise f.helper.CaptureRejected("metadata_guard")
                raise RuntimeError("PRIVATE-METADATA")
            return receive(method, *args)

        monkeypatch.setattr(backend, "_receive", observed)
        return backend

    f.factory = observed_factory
    result = run(f)
    vector = result["query_vector"]
    assert vector["primitive_wait"] == "TRUE" and vector["packet_err_snapshot"] == "UNKNOWN"
    assert all(result["normal_close"].values())
    if mandatory:
        r = module("ivv_trusted_runner")
        assert r._reference_from_error(r._reference_result(result))["operation_failed"] is True
    else:
        assert result["state"] == "REFERENCE_READY_CLOSED"
        assert vector["unpack"] == "OK" and vector["attribution"] == "RACE_OR_UNKNOWN"


@pytest.mark.parametrize("point", ["initial", "factory"])
def test_prebackend_live_guard_is_preserved_in_actual_terminal(tmp_path, monkeypatch, point):
    f = instrumented(tmp_path, monkeypatch)
    factory_calls = []

    def live():
        if point == "initial" or factory_calls:
            raise f.helper.CaptureRejected("prebackend_guard_required")

    def factory(observer, writer, plan, clock):
        factory_calls.append(True)
        observer.check(180)
        pytest.fail("guarded factory must not construct a backend")

    f.plan["_live_verifier"] = live
    f.factory = factory
    result = run(f)
    expected = f.helper._empty_query_vector()
    expected["guard"] = dict(stage="LIVE", code="REFERENCE_LIVE_REFUSED")
    assert result["query_vector"] == expected
    assert result["primary_failure"] == dict(
        stage="initialize", **{"class": "CaptureRejected"}, code="prebackend_guard_required"
    )
    assert result["constructor_returned"] is False
    assert result["constructor_status"] == "NOT_RETURNED"
    assert result["init_delegate_return"] == "UNKNOWN"
    assert result["counts"] == dict(
        contexts=0, initializations=0, init_sends=0, keepalive_sends=0, business_sends=0
    )
    assert result["close_failure"] is None and not any(result["normal_close"].values())
    assert result["state"] == "REFERENCE_FAILED"
    assert factory_calls == ([] if point == "initial" else [True])
    assert len(list((tmp_path / "ledger").glob("*.may.json"))) == (0 if point == "initial" else 1)
    assert not f.made and f.transport.writes == 0
    assert json.loads((f.root / "reference-terminal.json").read_bytes()) == result


def test_prebackend_ordinary_factory_error_retains_empty_guard(tmp_path, monkeypatch):
    f = instrumented(tmp_path, monkeypatch)

    def factory(*args):
        raise RuntimeError("PRIVATE")

    f.factory = factory
    result = run(f)
    assert result["query_vector"] == f.helper._empty_query_vector()
    assert result["primary_failure"] == dict(
        stage="initialize", **{"class": "RuntimeError"}, code="exception"
    )
    assert not f.made and f.transport.writes == 0
