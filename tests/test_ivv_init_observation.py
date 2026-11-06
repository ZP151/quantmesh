"""Same pinned SDK control flow, with no SDK imports, socket, threads or provider."""

import ast
import enum
import hashlib
import json
import struct
import threading
import weakref
from collections import namedtuple
from copy import copy
from functools import lru_cache
from importlib.metadata import distribution
from types import SimpleNamespace as NS

import pytest
from test_ivv_recovery_capture import module

CANARY = "PRIVATE-INIT-ACC-KEY-PB"
PINS = {
    "common/open_context_base.py": (
        "d88cc4786ca26b43717d6addf7dca7ce96ba4478c15d7144ad0f2968d8c0dd0d"
    ),
    "quote/open_quote_context.py": (
        "ef77c2a66941a8ae8079b5d4dc258286e8426561e1f1b33f00f6c1913d3cc558"
    ),
    "quote/quote_query.py": "19da6fe6515486b9ab1b09077290b36ddbfb820d6aff45466c3e9d3162419836",
    "common/network_manager.py": "d3d48a0eac9736f579ec09b05c60a2d82fd5a1ef77ae09543509ef0ffa9436e4",
    "common/constant.py": "8b4ec4d4d4fad2bc9d5224317a7c74876e7192aaf26513dc674bfd649b1a2fcf",
}


@lru_cache
def pinned_ast(path):
    dist = distribution("moomoo-api")
    assert dist.version == "10.10.7008"
    raw = dist.locate_file("moomoo/" + path).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(raw).hexdigest() == PINS[path]
    return ast.parse(raw)


def sdk_class(env, path, name, methods=None):
    original = next(
        n for n in pinned_ast(path).body if isinstance(n, ast.ClassDef) and n.name == name
    )
    node = copy(original)
    if methods is not None:
        node.body = [
            n for n in original.body if isinstance(n, ast.FunctionDef) and n.name in methods
        ]
        assert {n.name for n in node.body} == set(methods)
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), env)
    return env[name]


def sdk_transport(case):
    state = NS(sends=0, callbacks=0, failure=RuntimeError(CANARY))

    def quiet(*args, **kw):
        pass

    env = dict(
        RET_OK=0,
        RET_ERROR=-1,
        enum=enum,
        RLock=threading.RLock,
        copy=copy,
        time=NS(time=lambda: 0),
        ProtoInfo=namedtuple("ProtoInfo", "proto_id serial_no"),
        ProtoId=NS(InitConnect=1001),
        FTLog=NS(BOTH_FILE_CONSOLE=0),
        logger=NS(info=quiet, info2=quiet, warning2=quiet),
        SecurityFirm=NS(NONE="NONE", if_has_key=lambda k: True),
        SubRecord=dict,
        SysConfig=NS(
            get_client_ver=lambda: 1, get_proto_fmt=lambda: 1, get_client_id=lambda: CANARY
        ),
        FutuConnMng=NS(add_conn=quiet),
        HandlerContext=lambda f: None,
        CallbackExecutor=lambda: NS(_thread=NS(join=quiet, is_alive=lambda: False)),
    )
    status = sdk_class(env, "common/constant.py", "ContextStatus")
    packet = sdk_class(env, "common/network_manager.py", "PacketErr")
    manager = sdk_class(env, "common/network_manager.py", "NetManager", ["send"])
    base_path = "common/open_context_base.py"
    sdk_class(env, base_path, "ReqInfo", ["__init__", "is_sync", "wait", "notify_finish"])
    base = sdk_class(
        env,
        base_path,
        "OpenContextBase",
        [
            "__init__",
            "status",
            "conn_str",
            "set_sync_query_connect_timeout",
            "_query_sync",
            "_init_connect_sync",
            "_send_init_connect_sync",
            "_handle_init_connect_rsp",
            "can_send_proto",
        ],
    )
    quote = sdk_class(env, "quote/open_quote_context.py", "OpenQuoteContext", ["__init__"])
    init = sdk_class(env, "quote/quote_query.py", "InitConnect", ["unpack_rsp"])
    if case == "unpack_alias":
        original_unpack = init.unpack_rsp

        def unpack_alias(pb):
            _, msg, data = original_unpack(pb)
            return False, msg, data

        init.unpack_rsp = staticmethod(unpack_alias)
    serial = 8 if case == "wrong_serial" else 7
    init.pack_req = staticmethod(
        lambda **kw: (0, CANARY, struct.pack(">II", 1001, serial), 1001, 7)
    )

    class Event:
        def wait(self, timeout):
            assert timeout == 20
            return case != "timeout"

    env["threading"] = NS(Event=Event)
    net = manager()
    env["NetManager"] = NS(default=lambda: net)
    base.is_encrypt = lambda ctx: False
    base._is_proc_run = quiet

    def connect(ctx):
        state.ctx = ctx
        ctx._conn_id = 23
        ctx._status = status.CONNECTED
        return 0

    base._connect_sync = connect

    def reconnected(ctx):
        state.callbacks += 1
        if case == "foreign_context":
            foreign = object.__new__(type(ctx))
            foreign._lock = threading.RLock()
            foreign._handle_init_connect_rsp({"conn_id": 0, "keep_alive_interval": 1})
        if case == "ctor_raise":
            raise state.failure
        if case == "race":
            ctx._status = status.CLOSED
        if case == "unknown_status":
            ctx._status = CANARY
        if case == "ready_alias":
            ctx._status = type("PrivateAlias", (str,), {})(status.READY)
        return 0, ""

    base.on_api_socket_reconnected = reconnected
    base.close = lambda ctx: setattr(ctx, "_status", status.CLOSED)
    net.connect = quiet
    net._get_conn = lambda conn: None
    net._req_queue = NS(put=quiet)

    def wake(raw):
        ctx = state.ctx
        if case == "send_raise":
            raise OSError(CANARY)
        if case == "send_interrupt":
            raise state.failure
        req = ctx._req_map.pop((1001, 7))
        state.request_ref = weakref.ref(req)
        req.msg = CANARY
        req.rsp = NS(
            retType=0,
            retMsg=CANARY,
            HasField=lambda field: True,
            s2c=NS(
                serverVer=1,
                loginUserID=CANARY,
                connID=9,
                connAESKey=CANARY,
                HasField=lambda field: False,
                keepAliveInterval=10,
            ),
        )
        if case in ("Invalid", "Disconnect", "SendFail"):
            req.err = getattr(packet, case)
        if case == "wrong_req_invalid":
            req.err = packet.Invalid
        if case in ("unknown_packet", "unknown_ready"):
            req.err = CANARY
        if case == "unpack_raise":
            req.rsp = None
        if case == "non_ok":
            req.rsp.retType = -1
        if case == "missing_s2c":
            req.rsp.HasField = lambda field: False
        return 1

    net._w_sock = NS(send=wake)
    original = net.send

    def send(conn, raw):
        state.sends += 1
        if case == "send_fail":
            return -1, CANARY
        result = original(conn, raw)
        return (False, CANARY) if case == "send_alias" else result

    net.send = send
    if case == "unknown_ready":
        original_init = quote.__init__

        def ready_after_failure(ctx, **kw):
            original_init(ctx, **kw)
            ctx._status = status.READY

        quote.__init__ = ready_after_failure

    if case in ("wrong_req", "wrong_req_invalid"):

        class SubstitutedMap(dict):
            def get(self, key, default=None):
                actual = super().get(key, default)
                substitute = copy(actual)
                state.bound_request_ref = weakref.ref(substitute)
                return substitute

        def connect_with_foreign_req(ctx):
            ctx._req_map = SubstitutedMap()
            return connect(ctx)

        base._connect_sync = connect_with_foreign_req
    sdk = NS(OpenQuoteContext=quote, SecurityFirm=env["SecurityFirm"])
    util = NS(
        MESSAGE_HEAD_FMT=">II",
        parse_head=lambda b: dict(
            zip(("proto_id", "serial_no"), struct.unpack(">II", b), strict=True)
        ),
    )
    return (sdk, util, NS(ContextStatus=status)), state


def open_fixture(case, *, transport=None):
    m = module("capture_opend_ivv_daily")
    r = module("ivv_trusted_runner")
    trace = m._CaptureLifecycle(lambda e: r.classify_capture_exception(e, m.CaptureRejected))
    plan = {
        "endpoint": {"is_encrypt": False, "security_firm": "NONE"},
        "started_monotonic": 0,
        "_capture_lifecycle": trace,
    }
    clock = NS(mono=lambda: 0)
    observer = m._CaptureObserver(plan, None, clock)
    modules, state = transport if transport is not None else sdk_transport(case)
    backend = m._OfficialBackend(observer, None, plan, clock, modules=modules)
    return m, backend, trace, state


def test_pinned_timeout():
    m, backend, trace, state = open_fixture("timeout")
    with pytest.raises(m.CaptureRejected, match="sdk_initial_connection_failed"):
        backend.open()
    backend.close()
    assert state.sends == 1
    assert trace.value["init_observation"] == {
        "send": "OK",
        "packet_err": "Timeout",
        "unpack": "UNOBSERVED",
        "ever_ready": False,
        "constructor_status": "CONNECTED",
    }


@pytest.mark.parametrize(
    "case,send,packet,unpack,end,ready",
    [
        ("send_fail", "NON_OK", "UNOBSERVED", "UNOBSERVED", "CONNECTED", False),
        ("send_raise", "RAISED", "UNOBSERVED", "UNOBSERVED", "CONNECTED", False),
        ("Invalid", "OK", "Invalid", "UNOBSERVED", "CONNECTED", False),
        ("Disconnect", "OK", "Disconnect", "UNOBSERVED", "CONNECTED", False),
        ("SendFail", "OK", "SendFail", "UNOBSERVED", "CONNECTED", False),
        ("unpack_raise", "OK", "Ok", "RAISED", "CONNECTED", False),
        ("non_ok", "OK", "Ok", "NON_OK", "CONNECTED", False),
        ("missing_s2c", "OK", "Ok", "NON_OK", "CONNECTED", False),
        ("race", "OK", "Ok", "OK", "CLOSED", True),
        ("normal", "OK", "Ok", "OK", "READY", True),
        ("unknown_status", "OK", "Ok", "OK", "UNKNOWN", True),
        ("unknown_packet", "OK", "UNKNOWN", "UNOBSERVED", "CONNECTED", False),
        ("unknown_ready", "OK", "UNKNOWN", "UNOBSERVED", "READY", False),
    ],
)
def test_pinned_outcomes(case, send, packet, unpack, end, ready):
    m, backend, trace, state = open_fixture(case)
    if case == "normal":
        backend.open()
        assert state.ctx._sync_query_connect_timeout == 5
    else:
        with pytest.raises(m.CaptureRejected):
            backend.open()
    backend.close()
    assert trace.value["init_observation"] == dict(
        send=send, packet_err=packet, unpack=unpack, constructor_status=end, ever_ready=ready
    )
    assert state.sends == 1 and backend.o.controls == {1001: 1}
    assert trace.value["evidence_kind"] == "OBSERVED"
    assert all(backend.close_evidence().values())
    assert CANARY not in json.dumps(trace.value)


def test_closed_selector_preserves_only_finite_facts():
    r = module("ivv_trusted_runner")
    _, backend, trace, _ = open_fixture("normal")
    backend.open()
    backend.close()
    life = trace.value
    assert r.select_capture_lifecycle(life) == life
    facts = life["init_observation"]
    for patch in (
        {"secret": CANARY},
        {"send": CANARY},
        {"packet_err": CANARY},
        {"unpack": CANARY},
        {"constructor_status": CANARY},
        {"ever_ready": 1},
        {"send": "NON_OK"},
    ):
        with pytest.raises(r.Refused):
            r.select_capture_lifecycle({**life, "init_observation": {**facts, **patch}})


@pytest.mark.parametrize("case", ["Disconnect", "forwarding_pack", "wrong_req_invalid"])
def test_failed_manifest_to_stop(monkeypatch, tmp_path, case):
    import test_ivv_runtime_failure_evidence as chain
    from test_ivv_recovery_capture import connected_recovery_capture

    modules, state = sdk_transport("normal" if case == "forwarding_pack" else case)

    def entry(m, issuer, runner, session, *args):
        session.capture_classifier = lambda e: runner.classify_capture_exception(
            e, m.CaptureRejected
        )
        cls = m._OfficialBackend
        modules[0].SecurityFirm.FUTUSECURITIES = "FUTUSECURITIES"
        modules[0].SecurityFirm.FUTUSG = "FUTUSG"
        modules[0].SecurityFirm.FUTUINC = "FUTUINC"

        def factory(o, w, p, c):
            backend = cls(o, w, p, c, modules=modules)
            if case == "forwarding_pack":
                observe = backend._observe_init_query
                backend._observe_init_query = lambda ctx, query, pack, unpack, kw: observe(
                    ctx, query, lambda **args: pack(**args), unpack, kw
                )
            return backend

        return factory

    value = connected_recovery_capture(
        tmp_path, monkeypatch, entry_hook=entry, capture_failure=True
    )
    manifest = value["result"]
    assert json.loads((value["root"] / "capture-manifest.json").read_bytes()) == manifest
    life = manifest["capture_lifecycle"]
    expected_error = "Disconnect" if case == "Disconnect" else "UNOBSERVED"
    assert life["init_observation"]["packet_err"] == expected_error
    assert manifest["counts"]["application_sends"] == 0
    assert manifest["counts"]["control_sends"] == {"1001": 1, "1004": 0}
    journal = json.loads((value["root"] / "request-journal.json").read_bytes())
    assert [row["state"] for row in journal["records"]].count("MAY_HAVE_SENT") == 1
    if case != "Disconnect":
        assert manifest["primary_failure"]["code"] == "init_observation_binding"
    assert all(life["normal_close"].values()) and state.sends == 1
    runner = value["runner"]
    with pytest.raises(runner.Refused) as caught:
        runner._check_capture_result(manifest, recovery=True)
    selected = chain.test_real_child_ipc_parent_wrap_main_reader_selector(
        monkeypatch, "pidfd", (runner, caught.value, None)
    )
    assert selected["capture_lifecycle"] == life and selected["actual_contexts"] == "UNKNOWN"
    assert CANARY not in json.dumps([selected, manifest])


@pytest.mark.parametrize("case", ["wrong_req", "foreign_context", "wrong_serial"])
def test_foreign_attribution_refuses_even_after_sdk_ready(case):
    m, backend, trace, state = open_fixture(case)
    with pytest.raises(m.CaptureRejected, match="init_observation_binding"):
        backend.open()
    assert state.ctx._status == "READY"
    facts = trace.value["init_observation"]
    assert facts["ever_ready"] is (case == "foreign_context")
    assert CANARY not in json.dumps(facts)
    backend.close()


def test_partial_constructor_retains_status_and_exception_identity():
    _, backend, trace, state = open_fixture("ctor_raise")
    with pytest.raises(RuntimeError) as raised:
        backend.open()
    assert raised.value is state.failure
    facts = trace.value["init_observation"]
    assert not trace.value["constructor_returned"]
    assert facts["ever_ready"] and facts["constructor_status"] == "READY"
    backend.close()
    assert facts["constructor_status"] == "READY"


@pytest.mark.parametrize("case", ["normal", "send_raise", "unpack_raise"])
def test_delegate_identity_at_pinned_call_sites(case):
    m, backend, trace, state = open_fixture(case)
    observe = backend._observe_init_return
    outcomes = []

    def witness(field, delegate, *args, **kwargs):
        seen = []

        def actual(*args, **kwargs):
            try:
                result = delegate(*args, **kwargs)
            except BaseException as exc:
                seen.append(exc)
                raise
            seen.append(result)
            return result

        try:
            result = observe(field, actual, *args, **kwargs)
        except BaseException as exc:
            assert seen[0] is exc
            outcomes.append((field, "raised"))
            raise
        assert result is seen[0]
        outcomes.append((field, "returned"))
        return result

    backend._observe_init_return = witness
    if case == "normal":
        backend.open()
    else:
        with pytest.raises(m.CaptureRejected):
            backend.open()
    backend.close()
    expected = (
        [("send", "raised")]
        if case == "send_raise"
        else [("send", "returned"), ("unpack", "raised" if case == "unpack_raise" else "returned")]
    )
    assert outcomes == expected
    assert CANARY not in json.dumps(trace.value)


def test_sequential_observations_do_not_hold_request_or_bleed():
    import gc

    transport = sdk_transport("normal")
    _, first, one, state = open_fixture("normal", transport=transport)
    first.open()
    first.close()
    snapshot = json.dumps(one.value)
    first_request = state.request_ref
    net = first.ctx._net_mgr
    wake = net._w_sock.send

    def invalid_response(raw):
        result = wake(raw)
        req = state.request_ref()
        req.err = type(req.err).Invalid
        return result

    net._w_sock.send = invalid_response
    m, second, two, _ = open_fixture("normal", transport=transport)
    with pytest.raises(m.CaptureRejected, match="sdk_initial_connection_failed"):
        second.open()
    second.close()
    gc.collect()
    assert first.ctx is not second.ctx and net is second.ctx._net_mgr
    assert net.send is first._old_send and net.send is second._old_send
    assert first_request() is None and state.request_ref() is None
    assert two.value["init_observation"]["packet_err"] == "Invalid"
    assert one.value["init_observation"] is not two.value["init_observation"]
    assert json.dumps(one.value) == snapshot and CANARY not in snapshot


@pytest.mark.parametrize(
    "case,field",
    [("ready_alias", "constructor_status"), ("send_alias", "send"), ("unpack_alias", "unpack")],
)
def test_unknown_even_if_sdk_accepts_equal_value(case, field):
    m, backend, trace, state = open_fixture(case)
    with pytest.raises(m.CaptureRejected, match="init_observation_binding"):
        backend.open()
    backend.close()
    r = module("ivv_trusted_runner")
    facts = r.select_capture_lifecycle(trace.value)["init_observation"]
    assert facts[field] == "UNKNOWN" and facts["ever_ready"] and state.callbacks == 1


@pytest.mark.parametrize("case", ["normal", "send_fail", "send_raise", "send_interrupt"])
def test_forwarding_pack_preserves_original_query_and_may(tmp_path, case):
    from test_ivv_recovery_capture import ledger

    m, backend, trace, state = open_fixture(case)
    book = ledger(tmp_path)
    attempt = book.begin("a" * 64, now=0)
    book.may_connect(attempt)
    backend.o.recovery, backend.o.attempt = book, attempt
    state.failure = KeyboardInterrupt(CANARY)
    observe = backend._observe_init_query
    outcomes = []

    def forwarding(ctx, query, pack, unpack, kwargs):
        seen = []

        class Query:
            __globals__ = query.__globals__

            def __call__(self, *args, **kwargs):
                try:
                    result = query(*args, **kwargs)
                except BaseException as error:
                    seen.append(error)
                    raise
                seen.append(result)
                return result

        try:
            result = observe(ctx, Query(), lambda **kw: pack(**kw), unpack, kwargs)
        except BaseException as error:
            assert seen[0] is error
            outcomes.append("RAISED")
            raise
        else:
            assert result is seen[0]
            outcomes.append(result[0])
            return result
        finally:
            seen.clear()

    backend._observe_init_query = forwarding
    with pytest.raises(BaseException) as caught:
        backend.open()
    assert state.sends == 1 and backend.o.controls == {1001: 1}
    assert book.usage()["init_connect"] == 1
    records = book.journal(attempt)["records"]
    assert [row["state"] for row in records].count("MAY_HAVE_SENT") == 1
    if case == "send_interrupt":
        assert caught.value is state.failure and outcomes == ["RAISED"]
    else:
        assert type(caught.value) is m.CaptureRejected
        assert caught.value.args == ("init_observation_binding",)
        assert outcomes == [0 if case == "normal" else -1]
    assert state.callbacks == (1 if case == "normal" else 0)
    backend.close()
    assert CANARY not in json.dumps(trace.value)


def test_wrong_request_invalid_cannot_hide_missing_actual_wait():
    import gc

    m, backend, trace, state = open_fixture("wrong_req_invalid")
    with pytest.raises(m.CaptureRejected, match="^init_observation_binding$"):
        backend.open()
    assert state.sends == 1 and backend.o.controls == {1001: 1}
    facts = trace.value["init_observation"]
    assert facts["send"] == "OK" and facts["packet_err"] == "UNOBSERVED"
    assert facts["unpack"] == "UNOBSERVED" and facts["constructor_status"] == "CONNECTED"
    assert backend._bind_init is None and backend._init_thread is None
    backend.close()
    gc.collect()
    assert state.request_ref() is None and state.bound_request_ref() is None
    assert CANARY not in json.dumps(trace.value)


def test_observation_mismatch_does_not_defer_real_send_guard(tmp_path):
    from test_ivv_recovery_capture import ledger

    m, backend, _, state = open_fixture("normal")
    book = ledger(tmp_path)
    attempt = book.begin("a" * 64, now=0)
    book.may_connect(attempt)
    backend.o.recovery, backend.o.attempt = book, attempt
    observe = backend._observe_init_query
    seen_poison = []

    def forwarding(ctx, query, pack, unpack, kw):
        backend.o.poison = "control_wire_budget"
        return observe(ctx, query, lambda **args: pack(**args), unpack, kw)

    before_send = backend.o.before_send

    def guarded(*args):
        seen_poison.append(backend.o.poison)
        return before_send(*args)

    backend._observe_init_query = forwarding
    backend.o.before_send = guarded
    with pytest.raises(m.CaptureRejected):
        backend.open()
    assert seen_poison == ["control_wire_budget"]
    assert state.sends == 0 and backend.o.controls == {}
    assert book.usage()["init_connect"] == 0 and book.journal(attempt)["records"] == []
    backend.close()
