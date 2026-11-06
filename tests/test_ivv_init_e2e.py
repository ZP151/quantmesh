"""Finite Init diagnosis, actual pinned SDK control flow, modeled external I/O."""

import ast
import hashlib
import json
import queue
import struct
import weakref
from importlib.metadata import distribution
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace as NS

import pytest
from test_ivv_init_observation import CANARY, open_fixture, pinned_ast, sdk_class, sdk_transport
from test_ivv_recovery_capture import module

PUBLIC_PINS = {
    "common/utils.py": "51d47fa5e239a7ddf6768a7ffb011927bb8c14aa393b5d15a07a77d4dde8013d",
    "common/pb/Common_pb2.py": "ddf3765381062b2213081b2af76059495310252d89100e5cce2b7c04f093fdbd",
    "common/pb/InitConnect_pb2.py": (
        "93ffed96eb8cb7b1c488ef883d4cdbaa487fc471743b9188bbddb3ce900b7e9d"
    ),
}


def public_ast(relative):
    raw = distribution("moomoo-api").locate_file("moomoo/" + relative).read_bytes()
    assert hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == PUBLIC_PINS[relative]
    return ast.parse(raw)


def full_transport(case):
    """Real public parser/poll/send/read/query/unpack; external socket/timer models."""
    from google.protobuf import descriptor_pool, message_factory

    modules, state = sdk_transport("timeout")
    quote = modules[0].OpenQuoteContext
    base = quote.__mro__[1]
    env = base.__init__.__globals__
    env.update(queue=queue, struct=struct, hashlib=hashlib, calcsize=struct.calcsize, IS_PY2=False)
    env.update(selectors=NS(EVENT_READ=1, EVENT_WRITE=2), Connection=NS)

    def quiet(*args, **kwargs):
        pass

    env["logger"].warning = quiet
    env["logger"].debug = quiet
    env["is_socket_exception_wouldblock"] = lambda e: isinstance(e, BlockingIOError)
    for name in ("ProtoId", "ProtoFMT"):
        sdk_class(env, "common/constant.py", name)
    constants = pinned_ast("common/constant.py")
    fmt = next(
        n
        for n in constants.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "MESSAGE_HEAD_FMT" for t in n.targets)
    )
    exec(compile(ast.Module(body=[fmt], type_ignores=[]), "constant.py", "exec"), env)
    nodes = [
        n
        for n in public_ast("common/utils.py").body
        if isinstance(n, (ast.FunctionDef, ast.ClassDef))
        and n.name
        in {
            "parse_head",
            "get_message_head_len",
            "decrypt_rsp_body",
            "parse_rsp",
            "binary2pb",
            "ParseRspErr",
            "ParseRspResult",
        }
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "utils.py", "exec"), env)
    pool = descriptor_pool.DescriptorPool()
    for relative in ("common/pb/Common_pb2.py", "common/pb/InitConnect_pb2.py"):
        call = next(
            n
            for n in ast.walk(public_ast(relative))
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "AddSerializedFile"
        )
        pool.AddSerializedFile(ast.literal_eval(call.args[0]))
    response = message_factory.GetMessageClass(pool.FindMessageTypeByName("InitConnect.Response"))
    env["pb_map"] = {1001: response()}
    env["print"] = lambda *args: setattr(state, "decoder_logged", True)
    state.decoder_logged = False
    original_base = next(
        n
        for n in pinned_ast("common/open_context_base.py").body
        if isinstance(n, ast.ClassDef) and n.name == "OpenContextBase"
    )
    for node in original_base.body:
        if isinstance(node, ast.FunctionDef) and node.name in {"on_recv", "_handle_recv"}:
            exec(
                compile(ast.Module(body=[node], type_ignores=[]), "open_context_base.py", "exec"),
                env,
            )
            setattr(base, node.name, env[node.name])
    manager = sdk_class(
        env,
        "common/network_manager.py",
        "NetManager",
        ["send", "do_send", "_get_conn", "poll", "_on_read", "_on_write", "_watch_write"],
    )
    sdk_class(env, "common/network_manager.py", "ConnStatus")
    sdk_class(env, "common/network_manager.py", "CloseReason")
    env["Err"] = NS(ConnectionLost=NS(text=CANARY), NotConnected=NS(text=CANARY))
    net = manager.__new__(manager)
    env["NetManager"] = NS(default=lambda: net)
    state.net = net
    state.writes = 0
    state.reads = 0
    state.received = []
    state.write_steps = []
    state.thread_alive = True
    state.conn = conn = NS(
        conn_id=23, status=env["ConnStatus"].Connected, writebuf=bytearray(), handler=None
    )

    def frame(serial=7, invalid=False):
        pb = response(retType=0)
        pb.s2c.serverVer = 1
        pb.s2c.loginUserID = 0
        pb.s2c.connID = 0
        pb.s2c.connAESKey = ""
        pb.s2c.keepAliveInterval = 10
        body = pb.SerializeToString(deterministic=True)
        sha = b"\0" * 20 if invalid else hashlib.sha1(body).digest()
        return (
            struct.pack(
                env["MESSAGE_HEAD_FMT"],
                b"F",
                b"T",
                1001,
                env["ProtoFMT"].Protobuf,
                0,
                serial,
                len(body),
                sha,
                b"\0" * 8,
            )
            + body
        )

    state.frame = frame
    request = (
        struct.pack(env["MESSAGE_HEAD_FMT"], b"F", b"T", 1001, 0, 0, 7, 1, b"\0" * 20, b"\0" * 8)
        + b"Q"
    )
    env["InitConnect"].pack_req = staticmethod(lambda **kw: (0, CANARY, request, 1001, 7))
    if case in {"normal", "wrong_serial", "invalid", "fragmented"}:
        data = frame(8 if case == "wrong_serial" else 7, case == "invalid")
        state.received = [data[:17], data[17:]] if case == "fragmented" else [data]

    class DataSocket:
        def send(self, data):
            state.writes += 1
            step = state.write_steps.pop(0) if state.write_steps else len(data)
            if isinstance(step, BaseException):
                raise step
            return min(step, len(data))

        def recv(self, maximum):
            assert maximum == 128 * 1024
            state.reads += 1
            return state.received.pop(0)

    conn.sock = DataSocket()
    net._conn_map = {23: conn}
    net._req_queue = queue.Queue()
    net._last_check_time = net._last_tick_time = float("inf")
    net._thread = NS(is_alive=lambda: state.thread_alive)
    net.connect = quiet
    net._selector = NS(get_key=lambda sock: NS(events=0), modify=quiet, unregister=quiet)

    def select_events(timeout):
        return [(NS(fileobj=net._r_sock), 1)]

    net._selector.select = select_events
    net._do_close = lambda *args: net._conn_map.pop(23, None)

    def pump():
        net.poll()
        while conn.writebuf and state.write_steps:
            net._on_write(conn)
        while state.received:
            net._on_read(conn)

    state.pump = pump

    class Event:
        signaled = False

        def set(self):
            self.signaled = True

        def wait(self, timeout):
            assert timeout == 20
            return self.signaled

    env["threading"] = NS(Event=Event)
    net._r_sock = NS(recv=lambda maximum: b"1")

    def wake(raw):
        assert raw == b"1"
        state.request_ref = weakref.ref(state.ctx._req_map[(1001, 7)])
        if case != "queued":
            pump()
        return 1

    net._w_sock = NS(send=wake)
    connect = base._connect_sync

    def connected(ctx):
        result = connect(ctx)
        conn.handler = ctx
        ctx._recv_buf = bytearray()
        ctx._is_encrypt = False
        ctx._opend_conn_id = 0
        return result

    base._connect_sync = connected

    def close(ctx):
        ctx._status = "CLOSED"
        ctx._req_map.clear()
        ctx._recv_buf.clear()
        net._conn_map.pop(23, None)

    base.close = close
    util = NS(MESSAGE_HEAD_FMT=env["MESSAGE_HEAD_FMT"], parse_head=env["parse_head"])
    return (modules[0], util, modules[2]), state


def test_queue_acceptance_does_not_claim_tcp_write():
    m, backend, lifecycle, state = open_fixture("timeout")
    with pytest.raises(m.CaptureRejected, match="sdk_initial_connection_failed"):
        backend.open()
    trace = lifecycle.value["receive_trace"]
    assert lifecycle.value["init_observation"]["send"] == "OK"
    assert trace["dequeues"] == 0 and trace["read_callbacks"] == 0
    assert trace["tcp_progress"] in ("UNOBSERVED", "UNKNOWN")
    assert trace["tcp_accepted"] is None and trace["tcp_pending"] is None
    assert trace["target_notify_err"] == "UNOBSERVED"
    assert trace["wait_ended"] and trace["network_thread"] == "UNKNOWN"
    assert state.sends == 1 and len(json.dumps(trace).encode()) <= 2048
    before = json.loads(json.dumps(trace))
    backend.close()
    assert lifecycle.value["receive_trace"] == before
    assert CANARY not in json.dumps(lifecycle.value)


def test_actual_queued_work_and_tcp_acceptance_are_separate_witnesses():
    transport = full_transport("write_only")
    m, backend, lifecycle, state = open_fixture("timeout", transport=transport)
    with pytest.raises(m.CaptureRejected, match="sdk_initial_connection_failed"):
        backend.open()
    trace = lifecycle.value["receive_trace"]
    assert trace["polls"] == 1 and trace["dequeues"] == 1
    assert trace["tcp_progress"] == "FULL"
    assert trace["tcp_accepted"] == 45 and trace["tcp_pending"] == 0
    assert trace["read_callbacks"] == 0 and trace["network_thread"] == "ALIVE"
    assert state.writes == 1 and state.reads == 0
    backend.close()
    assert all(backend.close_evidence().values())


def test_actual_full_decoder_target_notification_precedes_wait_end():
    m, backend, lifecycle, state = open_fixture("normal", transport=full_transport("normal"))
    backend.open()
    trace = lifecycle.value["receive_trace"]
    assert trace["read_events"] == trace["read_callbacks"] == 1
    assert trace["read_bytes"] > 44
    assert trace["complete_candidate_seen"] and trace["target_candidate_seen"]
    assert trace["target_notify_err"] == "Ok"
    assert trace["notify_when"] == "BEFORE_WAIT_END"
    assert trace["wait_ended"] and not trace["scan_unknown"]
    assert lifecycle.value["init_observation"]["unpack"] == "OK"
    assert not state.decoder_logged
    assert CANARY not in json.dumps(trace)
    backend.close()
    assert all(backend.close_evidence().values())


def test_recorder_scan_failure_cannot_suppress_original_receive(monkeypatch):
    m, backend, lifecycle, state = open_fixture("normal", transport=full_transport("normal"))

    def recorder_failure(*args):
        raise RuntimeError(CANARY)

    monkeypatch.setattr(m._InitReceiveTrace, "scan", recorder_failure)
    backend.open()
    assert state.reads == 1 and lifecycle.value["init_observation"]["unpack"] == "OK"
    assert lifecycle.value["receive_trace"]["recorder_error"]
    backend.close()
    assert CANARY not in json.dumps(lifecycle.value)


@pytest.mark.parametrize(
    "steps,old,progress,accepted,pending",
    [
        ([2], b"", "PARTIAL", 2, 43),
        ([2, 43], b"", "FULL", 45, 0),
        ([BlockingIOError(11, CANARY)], b"", "NONE", 0, 45),
        ([], b"OLD", "UNKNOWN", None, None),
    ],
)
def test_partial_eagain_and_mixed_buffers_preserve_write_semantics(
    steps, old, progress, accepted, pending
):
    transport = full_transport("write_only")
    transport[1].write_steps = list(steps)
    transport[1].conn.writebuf.extend(old)
    m, backend, lifecycle, state = open_fixture("timeout", transport=transport)
    with pytest.raises(m.CaptureRejected, match="sdk_initial_connection_failed"):
        backend.open()
    trace = lifecycle.value["receive_trace"]
    assert (trace["tcp_progress"], trace["tcp_accepted"], trace["tcp_pending"]) == (
        progress,
        accepted,
        pending,
    )
    assert lifecycle.value["init_observation"]["send"] == "OK"
    backend.close()


@pytest.mark.parametrize(
    "case,callbacks,target,err,ready",
    [
        ("fragmented", 2, True, "Ok", True),
        ("wrong_serial", 1, False, "UNOBSERVED", False),
        ("invalid", 1, True, "Invalid", False),
    ],
)
def test_real_decoder_fragmentation_wrong_serial_and_invalid_hash(
    case, callbacks, target, err, ready
):
    m, backend, lifecycle, state = open_fixture("normal", transport=full_transport(case))
    if ready:
        backend.open()
    else:
        with pytest.raises(m.CaptureRejected, match="sdk_initial_connection_failed"):
            backend.open()
    trace = lifecycle.value["receive_trace"]
    assert trace["read_callbacks"] == callbacks
    assert trace["complete_candidate_seen"] and trace["target_candidate_seen"] is target
    assert trace["target_notify_err"] == err
    assert state.ctx._recv_buf == bytearray()
    backend.close()
    assert CANARY not in json.dumps(trace)


def test_callback_parser_exception_is_observed_without_replacing_sdk_handling():
    transport = full_transport("write_only")
    state = transport[1]
    raw = bytearray(state.frame())
    raw[2:6] = struct.pack("<I", 999999)
    state.received = [bytes(raw)]
    m, backend, lifecycle, state = open_fixture("timeout", transport=transport)
    with pytest.raises(m.CaptureRejected, match="sdk_initial_connection_failed"):
        backend.open()
    trace = lifecycle.value["receive_trace"]
    assert trace["complete_candidate_seen"]
    assert trace["callback_error"] == "OTHER"
    assert trace["target_notify_err"] == "UNOBSERVED"
    backend.close()
    assert CANARY not in json.dumps(trace)


def test_loop_failure_preserves_exception_identity_and_preclose_liveness():
    transport = full_transport("write_only")
    state = transport[1]
    failure = RuntimeError(CANARY)
    original = state.net.poll

    def failed_select(timeout):
        state.thread_alive = False
        raise failure

    def poll():
        try:
            return original()
        except RuntimeError as error:
            state.observed_error = error
            raise

    state.net._selector.select = failed_select
    state.net.poll = poll
    m, backend, lifecycle, _ = open_fixture("timeout", transport=transport)
    with pytest.raises(m.CaptureRejected, match="sdk_initial_connection_failed"):
        backend.open()
    assert state.observed_error is failure
    trace = lifecycle.value["receive_trace"]
    assert trace["loop_error"] == "RUNTIME_ERROR" and trace["network_thread"] == "DEAD"
    assert trace["polls"] == 1 and trace["dequeues"] == 0
    assert trace["first_ms"]["poll"] == trace["last_ms"]["poll"] == 0
    assert trace["first_ms"]["dequeue"] is None
    backend.close()
    assert trace["network_thread"] == "DEAD" and CANARY not in json.dumps(trace)


@pytest.mark.parametrize("point", ["__init__", "wait_end", "freeze"])
def test_recorder_construction_wait_or_snapshot_failure_cannot_cancel_init(monkeypatch, point):
    m, backend, lifecycle, state = open_fixture("normal", transport=full_transport("normal"))

    def failed_recorder(*args):
        raise RuntimeError(CANARY)

    monkeypatch.setattr(m._InitReceiveTrace, point, failed_recorder)
    backend.open()
    assert state.ctx._status == "READY" and state.writes == 1
    assert lifecycle.value["init_observation"]["unpack"] == "OK"
    assert lifecycle.value["receive_trace"]["recorder_error"]
    backend.close()
    assert all(backend.close_evidence().values())
    assert CANARY not in json.dumps(lifecycle.value)


def test_closed_lifecycle_transports_finite_receive_trace_and_refuses_payload_fields():
    _, backend, lifecycle, _ = open_fixture("normal", transport=full_transport("normal"))
    backend.open()
    backend.close()
    runner = module("ivv_trusted_runner")
    life = lifecycle.value
    selected = runner.select_capture_lifecycle(life)
    assert selected == life
    selected["receive_trace"]["first_ms"]["read"] = 42
    assert life["receive_trace"]["first_ms"]["read"] == 0
    for patch in (
        {"body": CANARY},
        {"tcp_accepted": True},
        {"read_bytes": 2147483648},
        {"polls": 4097},
        {"network_thread": CANARY},
        {"wait_ended": 1},
        {"first_ms": {"secret": CANARY}},
        {"notify_when": "AFTER_WAIT_END", "wait_ended": False},
    ):
        changed = {**life, "receive_trace": {**life["receive_trace"], **patch}}
        with pytest.raises(runner.Refused, match="CAPTURE_LIFECYCLE_SHAPE"):
            runner.select_capture_lifecycle(changed)
    error = runner.Refused("READY_CHECK")
    runner._carry_capture_lifecycle(error, life)
    assert runner._capture_lifecycle_from_error(error) == life


def test_late_actual_notification_does_not_rewrite_observed_timeout():
    transport = full_transport("queued")
    state = transport[1]
    state.received = [state.frame()]
    base = transport[0][0].OpenQuoteContext.__mro__[1]
    original = base._send_init_connect_sync

    def init_send(ctx):
        result = original(ctx)
        state.pump()
        return result

    base._send_init_connect_sync = init_send
    m, backend, lifecycle, _ = open_fixture("timeout", transport=transport)
    with pytest.raises(m.CaptureRejected, match="sdk_initial_connection_failed"):
        backend.open()
    trace = lifecycle.value["receive_trace"]
    assert trace["target_notify_err"] == "Ok" and trace["notify_when"] == "AFTER_WAIT_END"
    assert lifecycle.value["init_observation"]["packet_err"] == "Timeout"
    assert lifecycle.value["init_observation"]["unpack"] == "UNOBSERVED"
    assert module("ivv_trusted_runner").select_capture_lifecycle(lifecycle.value) == lifecycle.value
    backend.close()


def test_bounded_candidate_scan_does_not_replace_actual_decoder_association():
    transport = full_transport("write_only")
    state = transport[1]
    state.received = [state.frame(8) * 17 + state.frame()]
    _, backend, lifecycle, _ = open_fixture("normal", transport=transport)
    backend.open()
    trace = lifecycle.value["receive_trace"]
    assert trace["scan_unknown"] and trace["complete_candidate_seen"]
    assert not trace["target_candidate_seen"] and trace["target_notify_err"] == "Ok"
    backend.close()


def test_partial_header_and_callback_counter_saturation_are_bounded():
    transport = full_transport("write_only")
    state = transport[1]
    state.received = [b"Q"] * 4100
    m, backend, lifecycle, _ = open_fixture("timeout", transport=transport)
    with pytest.raises(m.CaptureRejected, match="sdk_initial_connection_failed"):
        backend.open()
    trace = lifecycle.value["receive_trace"]
    assert trace["read_events"] == trace["read_callbacks"] == 4096
    assert trace["read_bytes"] == 4100 and trace["overflow"]
    assert not trace["complete_candidate_seen"] and trace["target_notify_err"] == "UNOBSERVED"
    assert len(json.dumps(trace).encode()) <= 2048
    assert module("ivv_trusted_runner").select_capture_lifecycle(lifecycle.value) == lifecycle.value
    backend.close()


@pytest.mark.parametrize("case", ["normal", "wrong_serial", "invalid", "queued"])
def test_restoration_releases_exact_request_and_preserves_instance_methods(case):
    import gc

    transport = full_transport(case)
    state = transport[1]
    net_before = dict(vars(state.net))
    wire_before = state.net.send, state.net.connect
    m, backend, lifecycle, _ = open_fixture("normal", transport=transport)
    if case == "normal":
        backend.open()
    else:
        with pytest.raises(m.CaptureRejected, match="sdk_initial_connection_failed"):
            backend.open()
    before = json.dumps(lifecycle.value["receive_trace"], sort_keys=True)
    backend.close()
    gc.collect()
    assert state.request_ref() is None
    assert json.dumps(lifecycle.value["receive_trace"], sort_keys=True) == before
    for name in ("poll", "do_send", "_on_write", "_on_read"):
        assert (name in vars(state.net)) is (name in net_before)
        if name in net_before:
            assert vars(state.net)[name] is net_before[name]
    # Existing wire restoration writes the original bound delegate explicitly.
    assert state.net.send == wire_before[0] and state.net.connect == wire_before[1]
    assert "on_recv" not in vars(state.ctx) and "_handle_recv" not in vars(state.ctx)
    assert backend._receive_trace.saved == [] and backend._receive_trace.request is None


@pytest.mark.parametrize("fault", [None, "drift", "writable"])
def test_additional_public_source_pins_use_protected_reader_before_sdk_load(
    tmp_path, monkeypatch, fault
):
    m = module("capture_opend_ivv_daily")
    root = tmp_path / "sdk"
    paths = ("common/network_manager.py", "common/utils.py")
    dist = distribution("moomoo-api")
    for relative in paths:
        path = root / "moomoo" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(dist.locate_file("moomoo/" + relative).read_bytes())
    if fault == "drift":
        (root / "moomoo/common/network_manager.py").write_bytes(b"changed-public-source")
    seen = []

    def protected(ref, *, maximum):
        seen.append((ref, maximum))
        raw = Path(ref["path"]).read_bytes()
        m._require(hashlib.sha256(raw).hexdigest() == ref["sha256"], "sdk_source_pin")
        return raw

    monkeypatch.setattr(m, "_read_root_ref", protected)
    monkeypatch.setattr(
        m, "os", NS(ST_RDONLY=1, statvfs=lambda path: NS(f_flag=0 if fault == "writable" else 1))
    )
    plan = {"sdk_root": str(root)}
    if fault is None:
        m._verify_receive_sources(plan)
        assert len(seen) == 2 and all(bound <= 131072 for _, bound in seen)
        assert {p["sha256"] for p, _ in seen} == {
            "d3d48a0eac9736f579ec09b05c60a2d82fd5a1ef77ae09543509ef0ffa9436e4",
            PUBLIC_PINS["common/utils.py"],
        }
    else:
        with pytest.raises(m.CaptureRejected, match="sdk_source_pin|sdk_source_not_readonly"):
            m._verify_receive_sources(plan)


@pytest.mark.parametrize(
    "fault", [None, "foreign", "module_alias", "filename", "quote_override", "req_override"]
)
def test_actual_method_origin_refuses_substitution_before_context(tmp_path, monkeypatch, fault):
    m = module("capture_opend_ivv_daily")
    root = tmp_path / "sdk"
    modules = {}
    specifications = (
        ("common/network_manager.py", {"NetManager": {"poll", "do_send", "_on_write", "_on_read"}}),
        (
            "common/open_context_base.py",
            {
                "OpenContextBase": {"on_recv", "_handle_recv", "_query_sync"},
                "ReqInfo": {"notify_finish"},
            },
        ),
    )
    for relative, classes in specifications:
        name = "moomoo." + relative[:-3].replace("/", ".")
        mod = ModuleType(name)
        mod.Connection = NS
        nodes = []
        for node in pinned_ast(relative).body:
            if isinstance(node, ast.ClassDef) and node.name in classes:
                nodes.append(
                    ast.ClassDef(
                        name=node.name,
                        bases=[],
                        keywords=[],
                        decorator_list=[],
                        body=[
                            n
                            for n in node.body
                            if isinstance(n, ast.FunctionDef) and n.name in classes[node.name]
                        ],
                    )
                )
        tree = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
        exec(compile(tree, str(root / "moomoo" / relative), "exec"), vars(mod))
        modules[name] = mod
    utils = ModuleType("moomoo.common.utils")
    node = next(
        n
        for n in public_ast("common/utils.py").body
        if isinstance(n, ast.FunctionDef) and n.name == "parse_head"
    )
    exec(
        compile(
            ast.Module(body=[node], type_ignores=[]), str(root / "moomoo/common/utils.py"), "exec"
        ),
        vars(utils),
    )
    modules[utils.__name__] = utils
    base = modules["moomoo.common.open_context_base"]
    net = modules["moomoo.common.network_manager"]
    quote = type("OpenQuoteContext", (base.OpenContextBase,), {})
    sdk = NS(OpenQuoteContext=quote)
    if fault == "foreign":
        net.NetManager.poll = lambda self: None
    elif fault == "module_alias":
        modules[net.__name__] = ModuleType(net.__name__)
        modules[net.__name__].NetManager = net.NetManager
    elif fault == "filename":
        original = net.NetManager.poll
        import types

        net.NetManager.poll = types.FunctionType(
            original.__code__.replace(co_filename="foreign.py"), vars(net)
        )
    elif fault == "quote_override":
        quote._handle_recv = lambda self: None
    elif fault == "req_override":
        base.ReqInfo.notify_finish = lambda self: None
    monkeypatch.setattr(m, "sys", NS(modules=modules))
    if fault is None:
        m._verify_receive_modules(sdk, utils, {"sdk_root": str(root)})
    else:
        with pytest.raises(m.CaptureRejected, match="sdk_import_origin"):
            m._verify_receive_modules(sdk, utils, {"sdk_root": str(root)})


def test_relative_phase_clock_starts_at_bound_init_not_connection_setup():
    transport = full_transport("normal")
    base = transport[0][0].OpenQuoteContext.__mro__[1]
    connect = base._connect_sync
    now = [10.0]

    def slow_connect(ctx):
        result = connect(ctx)
        now[0] = 100.0
        return result

    base._connect_sync = slow_connect
    _, backend, lifecycle, _ = open_fixture("normal", transport=transport)
    backend.clock = NS(mono=lambda: now[0])
    backend.open()
    trace = lifecycle.value["receive_trace"]
    assert trace["first_ms"]["poll"] == 0
    assert trace["first_ms"]["notify"] == 0
    backend.close()


@pytest.mark.parametrize("ordering", ["channel", "pidfd", "both"])
def test_finite_diagnosis_survives_actual_ipc_parent_and_stop_selector(monkeypatch, ordering):
    import test_ivv_runtime_failure_evidence as chain

    m, backend, lifecycle, _ = open_fixture("timeout", transport=full_transport("wrong_serial"))
    with pytest.raises(m.CaptureRejected) as failure:
        backend.open()
    lifecycle.failed("primary", failure.value)
    backend.close()
    runner = module("ivv_trusted_runner")
    error = runner.Refused("CAPTURE_FAILED")
    runner._carry_capture_lifecycle(error, lifecycle.value)
    selected = chain.test_real_child_ipc_parent_wrap_main_reader_selector(
        monkeypatch, ordering, (runner, error, None)
    )
    assert selected["capture_lifecycle"] == lifecycle.value
    assert selected["capture_lifecycle"]["receive_trace"]["target_notify_err"] == "UNOBSERVED"
    assert len(json.dumps(selected).encode()) <= 8192
    assert CANARY not in json.dumps(selected)


def test_actual_sdk_lock_order_allows_independent_receiver_thread():
    import threading

    transport = full_transport("queued")
    state = transport[1]
    state.received = [state.frame()]
    env = transport[0][0].OpenQuoteContext.__mro__[1].__init__.__globals__
    state.failed = False

    class DeadlineModel:
        def __init__(self):
            self.event = threading.Event()

        def set(self):
            self.event.set()

        def wait(self, timeout):
            assert timeout == 20
            return self.event.wait(1)  # external deadline modeled, SDK control flow unchanged

    env["threading"] = NS(Event=DeadlineModel)

    def receive():
        try:
            state.pump()
        except BaseException:
            state.failed = True

    def wake(raw):
        state.request_ref = weakref.ref(state.ctx._req_map[(1001, 7)])
        state.worker = threading.Thread(target=receive)
        state.net._thread = state.worker
        state.worker.start()
        return 1

    state.net._w_sock.send = wake
    _, backend, lifecycle, _ = open_fixture("normal", transport=transport)
    try:
        backend.open()
    finally:
        state.worker.join(1)
        assert not state.worker.is_alive()
        backend.close()
    trace = lifecycle.value["receive_trace"]
    assert not state.failed and trace["target_notify_err"] == "Ok"
    assert trace["notify_when"] == "BEFORE_WAIT_END" and trace["tcp_progress"] == "FULL"
    assert all(backend.close_evidence().values())


def test_foreign_connection_callback_cannot_claim_bound_target():
    transport = full_transport("queued")
    state = transport[1]

    def wake(raw):
        state.ctx.on_recv(999, state.frame())
        return 1

    state.net._w_sock.send = wake
    m, backend, lifecycle, _ = open_fixture("timeout", transport=transport)
    with pytest.raises(m.CaptureRejected, match="sdk_initial_connection_failed"):
        backend.open()
    trace = lifecycle.value["receive_trace"]
    assert trace["scan_unknown"] and trace["read_callbacks"] == 0
    assert not trace["target_candidate_seen"] and trace["target_notify_err"] == "UNOBSERVED"
    backend.close()


def test_notification_outside_actual_receive_scope_does_not_claim_association():
    transport = full_transport("queued")
    state = transport[1]
    env = transport[0][0].OpenQuoteContext.__mro__[1].__init__.__globals__

    def wake(raw):
        req = state.ctx._req_map[(1001, 7)]
        req.rsp = env["parse_rsp"](bytearray(state.frame()), 0, False).rsp_pb
        req.notify_finish()
        return 1

    state.net._w_sock.send = wake
    _, backend, lifecycle, _ = open_fixture("normal", transport=transport)
    backend.open()
    trace = lifecycle.value["receive_trace"]
    assert trace["target_notify_err"] == "UNOBSERVED" and trace["notify_when"] == "UNOBSERVED"
    assert trace["read_callbacks"] == 0 and not trace["complete_candidate_seen"]
    backend.close()


def test_maximum_closed_trace_and_failure_fit_existing_native_status_bounds():
    _, backend, lifecycle, _ = open_fixture("normal", transport=full_transport("normal"))
    backend.open()
    backend.close()
    runner = module("ivv_trusted_runner")
    life = json.loads(json.dumps(lifecycle.value))
    trace = life["receive_trace"]
    for field in ("polls", "dequeues", "read_events", "read_callbacks"):
        trace[field] = 4096
    trace.update(
        read_bytes=2147483647,
        tcp_progress="PARTIAL",
        tcp_accepted=2147483647,
        tcp_pending=2147483647,
        target_notify_err="Disconnect",
        notify_when="AFTER_WAIT_END",
        callback_error="MEMORY_ERROR",
        loop_error="RUNTIME_ERROR",
        read_error="MEMORY_ERROR",
        overflow=True,
        recorder_error=True,
        scan_unknown=True,
    )
    for field in ("first_ms", "last_ms"):
        trace[field] = dict.fromkeys(trace[field], 480000)
    contract = runner._capture_lifecycle_contract()
    life["primary"] = dict(
        phase="CONTEXT_RESERVE_GUARD",
        guard="PROVIDER_SESSION",
        type="CaptureRejected",
        code=max(runner._capture_refusal_codes()["CaptureRejected"], key=len),
        errno=None,
    )
    life["close"] = dict(
        phase="CONNECTION_CHECK",
        guard="PROVIDER_SESSION",
        type="ConnectionAbortedError",
        code="UNKNOWN",
        errno=111,
    )
    assert life["primary"]["code"] in contract["code"]
    selected = runner.select_capture_lifecycle(life)
    assert len(runner.raw_json(selected["receive_trace"])) <= 2048
    error = runner.Refused("CAPTURE_FAILED")
    runner._carry_capture_lifecycle(error, selected)
    assert len(runner.raw_json(runner._failure_record(error))) <= 4096
    assert (
        runner._capture_lifecycle_from_error(runner._child_failure(runner._failed_packet(error)))
        == selected
    )


@pytest.mark.parametrize("jump", [1000000.0, float("nan")])
def test_clock_clamping_or_failure_cannot_escape_as_raw_data_or_change_sdk(jump):
    transport = full_transport("normal")
    state = transport[1]
    original = state.net.poll
    now = [0.0]

    def poll():
        now[0] = jump
        return original()

    state.net.poll = poll
    _, backend, lifecycle, _ = open_fixture("normal", transport=transport)
    backend.clock = NS(mono=lambda: now[0])
    backend.open()
    trace = lifecycle.value["receive_trace"]
    assert trace["target_notify_err"] == "Ok"
    assert trace["first_ms"]["notify"] == (480000 if jump == jump else None)
    assert trace["recorder_error"] is (jump != jump)
    module("ivv_trusted_runner").select_capture_lifecycle(lifecycle.value)
    assert "NaN" not in json.dumps(trace) and len(json.dumps(trace).encode()) <= 2048
    backend.close()


def test_source_refusal_precedes_loader_or_context_effect(monkeypatch):
    m = module("capture_opend_ivv_daily")
    lifecycle = m._CaptureLifecycle(lambda error: {})
    calls = []

    def refuse(plan):
        calls.append("source")
        raise m.CaptureRejected("sdk_source_pin")

    monkeypatch.setattr(m, "_verify_receive_sources", refuse)
    monkeypatch.setattr(m, "_load_official_sdk", lambda *args: calls.append("loader"))
    with pytest.raises(m.CaptureRejected, match="sdk_source_pin"):
        m._OfficialBackend(None, None, {"_capture_lifecycle": lifecycle}, NS(mono=lambda: 0))
    assert calls == ["source"]


def test_freeze_restore_between_callback_entry_and_lock_preserves_original_delegate():
    """Deterministic scheduling at the agreed private wrapper/freeze boundary."""
    import inspect
    import sys

    transport = full_transport("queued")
    state = transport[1]
    base = transport[0][0].OpenQuoteContext.__mro__[1]
    original = base._send_init_connect_sync
    m, backend, lifecycle, _ = open_fixture("timeout", transport=transport)
    scheduled = []

    def query_then_callback(ctx):
        result = original(ctx)
        callback = ctx.on_recv
        lines, start = inspect.getsourcelines(callback)
        boundary = start + next(
            i for i, line in enumerate(lines) if 'if name == "on_recv":' in line
        )

        def schedule(frame, event, arg):
            if event == "line" and frame.f_code is callback.__code__ and frame.f_lineno == boundary:
                sys.settrace(None)
                scheduled.append(True)
                backend._receive_trace.freeze(state.net)
                ctx._status = "CLOSED"
                backend._receive_trace.restore()
            return schedule

        previous_trace = sys.gettrace()
        sys.settrace(schedule)
        try:
            assert callback(23, state.frame()) is None
        finally:
            sys.settrace(previous_trace)
        return result

    base._send_init_connect_sync = query_then_callback
    with pytest.raises(m.CaptureRejected, match="sdk_initial_connection_failed"):
        backend.open()
    assert scheduled == [True]
    backend.close()
    assert lifecycle.value["receive_trace"]["target_notify_err"] == "UNOBSERVED"


def test_original_constructor_exception_survives_failed_diagnostic_snapshot(monkeypatch):
    m, backend, lifecycle, state = open_fixture("ctor_raise")

    def failed_snapshot(*args):
        raise ValueError(CANARY)

    monkeypatch.setattr(m._InitReceiveTrace, "freeze", failed_snapshot)
    with pytest.raises(RuntimeError) as caught:
        backend.open()
    assert caught.value is state.failure and state.sends == 1
    assert lifecycle.value["receive_trace"]["recorder_error"]
    backend.close()
    assert CANARY not in json.dumps(lifecycle.value)


def test_source_accurate_model_runs_with_sdk_import_and_real_socket_bombs(monkeypatch):
    import builtins
    import socket
    import sys

    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        assert name != "moomoo" and not name.startswith("moomoo.")
        return original_import(name, *args, **kwargs)

    def no_socket(*args, **kwargs):
        raise AssertionError("REAL_SOCKET_FORBIDDEN")

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr(socket, "socket", no_socket)
    _, backend, lifecycle, _ = open_fixture("normal", transport=full_transport("normal"))
    backend.open()
    backend.close()
    assert lifecycle.value["receive_trace"]["target_notify_err"] == "Ok"
    assert not any(name == "moomoo" or name.startswith("moomoo.") for name in sys.modules)


def test_r1_partial_tcp_update_failure_keeps_complete_lifecycle_through_ipc_stop(monkeypatch):
    import test_ivv_runtime_failure_evidence as chain

    m, backend, lifecycle, state = open_fixture("timeout", transport=full_transport("write_only"))
    mark = m._InitReceiveTrace.mark

    def failed_write_clock(trace, phase):
        if phase == "write":
            raise RuntimeError(CANARY)
        return mark(trace, phase)

    monkeypatch.setattr(m._InitReceiveTrace, "mark", failed_write_clock)
    with pytest.raises(m.CaptureRejected) as failure:
        backend.open()
    lifecycle.failed("primary", failure.value)
    backend.close()
    assert state.writes == 1 and not state.conn.writebuf
    runner = module("ivv_trusted_runner")
    error = runner.Refused("CAPTURE_FAILED")
    runner._carry_capture_lifecycle(error, lifecycle.value)
    assert runner._capture_lifecycle_from_error(error) == lifecycle.value
    trace = lifecycle.value["receive_trace"]
    assert trace["recorder_error"] and trace["tcp_progress"] == "UNKNOWN"
    assert trace["tcp_accepted"] is None and trace["tcp_pending"] is None
    selected = chain.test_real_child_ipc_parent_wrap_main_reader_selector(
        monkeypatch, "pidfd", (runner, error, None)
    )
    assert selected["capture_lifecycle"] == lifecycle.value
    assert all(selected["capture_lifecycle"]["normal_close"].values())


@pytest.mark.parametrize("seam", ["do_send", "_on_write"])
def test_r1_freeze_between_actual_write_and_accounting_is_unknown(seam):
    transport = full_transport("write_only")
    state = transport[1]
    if seam == "_on_write":
        state.write_steps = [2, 43]
    m, backend, lifecycle, _ = open_fixture("timeout", transport=transport)
    original = getattr(state.net, seam)

    def completed_write(*args, **kwargs):
        result = original(*args, **kwargs)
        assert not state.conn.writebuf
        state.concurrent_snapshot = backend._receive_trace.freeze(state.net)
        return result

    setattr(state.net, seam, completed_write)
    with pytest.raises(m.CaptureRejected, match="sdk_initial_connection_failed"):
        backend.open()
    trace = lifecycle.value["receive_trace"]
    assert state.concurrent_snapshot["tcp_progress"] == trace["tcp_progress"] == "UNKNOWN"
    assert trace["tcp_accepted"] is None and trace["tcp_pending"] is None
    assert not trace["recorder_error"]
    module("ivv_trusted_runner").select_capture_lifecycle(lifecycle.value)
    backend.close()
