"""Passive Init evidence; frozen public SDK pure bodies and synthetic OS only."""

import ast
import builtins
import hashlib
import json
import os
import socket
import stat
import struct
import time
from importlib.metadata import distribution
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from test_ivv_init_e2e import public_ast
from test_ivv_init_observation import pinned_ast, sdk_class
from test_ivv_init_query_vector import instrumented, run
from test_ivv_recovery_capture import module

METHOD = "init-peer-flow-v1"


def test_active_checkout_provenance():
    from quantmesh.research import ivv_recovery

    root = Path(__file__).resolve().parents[1]
    assert Path(ivv_recovery.__file__).resolve() == root / "src/quantmesh/research/ivv_recovery.py"
    for name in ("capture_opend_ivv_daily", "ivv_trusted_runner"):
        loaded = module(name)
        assert Path(loaded.__file__).resolve() == root / "tools/research" / (name + ".py")


def real_public_pack(f):
    """Execute the pinned serializer/protobuf, never import an SDK package."""
    from google.protobuf import descriptor_pool, message_factory

    base = f.modules[0].OpenQuoteContext.__mro__[1]
    env = base.__init__.__globals__
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
    request = message_factory.GetMessageClass(pool.FindMessageTypeByName("InitConnect.Request"))
    # Public configuration defaults execute from their actual frozen bodies.
    config_raw = distribution("moomoo-api").locate_file("moomoo/common/sys_config.py").read_bytes()
    assert hashlib.sha256(config_raw.replace(b"\r\n", b"\n")).hexdigest() == (
        "7e9aa6d47f28d6e6c7de8c41ddb25b1f397170a1a2f2f2a152f33c9e9c730902"
    )
    constants = [
        n
        for n in pinned_ast("common/constant.py").body
        if isinstance(n, ast.Assign)
        and any(
            isinstance(t, ast.Name)
            and t.id
            in {"DEFULAT_CLIENT_ID", "CLIENT_VERSION", "DEFULAT_PROTO_FMT", "API_PROTO_VER"}
            for t in n.targets
        )
    ]
    exec(compile(ast.Module(body=constants, type_ignores=[]), "pinned-defaults", "exec"), env)
    config = next(
        n
        for n in ast.parse(config_raw).body
        if isinstance(n, ast.ClassDef) and n.name == "SysConfig"
    )
    config.body = [
        n
        for n in config.body
        if isinstance(n, ast.FunctionDef)
        and n.name in {"get_client_id", "get_client_ver", "get_proto_fmt"}
        or isinstance(n, ast.Assign)
        and any(
            isinstance(t, ast.Name)
            and t.id in {"CLINET_ID", "CLIENT_VER", "PROTO_FMT", "INIT_RSA_FILE"}
            for t in n.targets
        )
    ]
    exec(compile(ast.Module(body=[config], type_ignores=[]), "pinned-sys-config", "exec"), env)
    original_import = builtins.__import__

    def pure_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "common.pb.InitConnect_pb2" and level == 2 and fromlist == ("Request",):
            return NS(Request=request)
        assert not name.startswith(("moomoo", "futu"))
        return original_import(name, globals, locals, fromlist, level)

    env["__builtins__"] = {**vars(builtins), "__import__": pure_import}
    env.update(
        Common_pb2=NS(
            **{v.name: v.number for v in pool.FindEnumTypeByName("Common.PacketEncAlgo").values}
        ),
        get_unique_id32=lambda: 7,
    )
    # Preserve the fixture's external connection-registry sink for the real
    # successful _handle_init_connect_rsp path; only encryption lookup is modeled.
    env["FutuConnMng"].is_conn_encrypt = lambda _: False
    nodes = [
        n
        for n in public_ast("common/utils.py").body
        if isinstance(n, ast.FunctionDef) and n.name in {"pack_pb_req", "_joint_head"}
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "pinned-utils.py", "exec"), env)
    sdk_class(env, "quote/quote_query.py", "InitConnect", ["pack_req", "unpack_rsp"])
    return env, request


def modeled_peer(f, monkeypatch):
    sock = f.transport.conn.sock
    sock.fileno = lambda: 1000000
    old_stat = f.helper.os.fstat
    monkeypatch.setattr(
        f.helper.os,
        "fstat",
        lambda fd: (
            NS(st_dev=1, st_ino=987, st_mode=stat.S_IFSOCK) if fd == 1000000 else old_stat(fd)
        ),
    )
    monkeypatch.setattr(f.helper.sys, "platform", "linux")
    monkeypatch.setattr(f.helper.os, "uname", lambda: NS(machine="x86_64"), raising=False)
    calls = []

    def tcp_info(level, option, size):
        assert (level, option, size) == (6, 11, 256)
        backend = f.made[0]
        before = not calls
        req = backend._query_request
        if not before:
            assert req.err.name in ("Timeout", "Ok", "SendFail")
            assert "wait" not in vars(req) and "wait" not in vars(req.event)
            assert req.unpack_func == f.transport.public_unpack
        calls.append("TCP_BEFORE" if before else "TCP_POST_QUERY")
        data = bytearray(136)
        data[0] = 1
        struct.pack_into("=I", data, 24, 0)
        struct.pack_into("=QQ", data, 120, 1 if before else 85, 0)
        return bytes(data)

    sock.getsockopt = tcp_info

    def peer(phase, fd, inode):
        assert (fd, inode) == (1000000, 987)
        calls.append(phase)
        return dict(
            identity="VERIFIED",
            row="MATCH",
            state="ESTABLISHED",
            vendor_fd="PRESENT",
            rx="ZERO",
            tx="ZERO",
            offset_ms=0,
        )

    f.plan["_peer_flow"] = peer
    return calls


def assert_timeout_causal(backend, result, calls):
    assert result["query_vector"]["primitive_wait"] == "FALSE"
    assert result["query_vector"]["packet_err_snapshot"] == "Timeout"
    assert result["query_vector"]["unpack"] == "UNOBSERVED"
    assert all(result["normal_close"].values())
    flow = getattr(backend, "peer_flow", None)
    assert flow is not None, "missing complete passive peer-flow evidence after real SDK timeout"
    assert flow["wire"]["state"] == "PUBLIC_CONFORMANT"
    assert flow["wire"]["packet_sha256"] is not None
    assert flow["client"]["acked_delta"] == 84
    assert flow["client"]["received_delta"] == 0
    assert flow["client"]["relation"] == "VALID"
    assert flow["peer_before"]["rx"] == flow["peer_after"]["rx"] == "ZERO"
    assert "read" not in json.dumps(flow).lower()
    assert calls == ["TCP_BEFORE", "BEFORE_SEND", "TCP_POST_QUERY", "POST_QUERY"]


def timeout_causal(tmp_path, monkeypatch):
    f, calls = selected_peer(tmp_path, monkeypatch)
    result = run(f)
    assert f.transport.writes == 1 and f.transport.reads == 0
    assert f.book.usage()["init_connect"] == 1
    return f, result, calls


def test_real_sdk_timeout_keeps_public_wire_and_post_query_flow_without_peer_read_claim(
    tmp_path, monkeypatch
):
    f, result, calls = timeout_causal(tmp_path, monkeypatch)
    assert_timeout_causal(f.made[0], result, calls)


def test_ram_rx_zero_does_not_establish_handler_read_mutant(tmp_path, monkeypatch):
    f, result, calls = timeout_causal(tmp_path, monkeypatch)
    flow = f.made[0].peer_flow
    assert flow["peer_after"]["rx"] == "ZERO"
    flow["peer_after"]["handler_read"] = True
    with pytest.raises(AssertionError):
        assert_timeout_causal(f.made[0], result, calls)
    with pytest.raises(f.helper.CaptureRejected, match="init_peer_flow_shape"):
        f.helper._select_peer_flow(flow, f.helper._require)


def selected_peer(tmp_path, monkeypatch, case="write_only"):
    f = instrumented(tmp_path, monkeypatch, case)
    env, _ = real_public_pack(f)
    f.transport.public_unpack = env["InitConnect"].unpack_rsp
    calls = modeled_peer(f, monkeypatch)
    old_ref = f.plan["reference_init_ref"]
    control = json.loads(f.helper._read_root_ref(old_ref))
    control.update(schema_id="qm.ivv.reference-control.v3", method=METHOD)
    raw = f.helper._canonical(control)
    f.plan["reference_init_ref"] = dict(
        path=old_ref["path"], sha256=hashlib.sha256(raw).hexdigest()
    )
    read = f.helper._read_root_ref
    monkeypatch.setattr(
        f.helper,
        "_read_root_ref",
        lambda ref, **kw: raw if ref == f.plan["reference_init_ref"] else read(ref, **kw),
    )
    f.plan["_reference_method"] = METHOD

    def factory(o, w, p, c):
        backend = f.helper._PeerFlowReferenceBackend(o, w, p, c, modules=f.modules)
        f.made.append(backend)
        return backend

    f.factory = factory
    return f, calls


def test_selected_held_v3_emits_v4_and_roundtrips_standalone(tmp_path, monkeypatch):
    f, calls = selected_peer(tmp_path, monkeypatch)
    result = run(f)
    assert result["schema_id"] == "qm.ivv.reference-init-terminal.v4"
    assert result["method"] == METHOD
    assert result["peer_flow"] == f.made[0].peer_flow
    assert_timeout_causal(f.made[0], result, calls)
    r = module("ivv_trusted_runner")
    obs = r._reference_from_error(r._reference_result(result))
    assert obs["schema_id"] == "qm.ivv.reference-init-observation.v4"
    assert obs["peer_flow"] == result["peer_flow"]
    assert (
        r._reference_from_error(r._child_failure(r._failed_packet(r._reference_result(result))))
        == obs
    )
    # Existing consumer extracts this function alone for standalone STOP codecs.
    tree = ast.parse(__import__("inspect").getsource(r.select_reference_observation))
    namespace = dict(json=json, re=__import__("re"), need=r.need)
    exec(compile(tree, "standalone-selector", "exec"), namespace)
    assert namespace["select_reference_observation"](obs) == obs
    packet = r._failed_packet(r._reference_result(result))
    assert r._reference_packet(packet, f.plan) == packet
    with pytest.raises(r.Refused, match="REFERENCE_TERMINAL_METHOD"):
        r._reference_packet(packet, {"reference_init_ref": f.plan["reference_init_ref"]})
    downgraded = json.loads(json.dumps(packet))
    downgraded["reference_init_observation"].update(
        schema_id="qm.ivv.reference-init-observation.v3", method="init-query-vector-v1"
    )
    del downgraded["reference_init_observation"]["peer_flow"]
    with pytest.raises(r.Refused, match="REFERENCE_TERMINAL_METHOD"):
        r._reference_packet(downgraded, f.plan)


def test_real_sdk_success_keeps_public_packet_notify_unpack_and_normal_close(tmp_path, monkeypatch):
    f, calls = selected_peer(tmp_path, monkeypatch, "normal")
    result = run(f)
    assert result["state"] == "REFERENCE_READY_CLOSED"
    assert result["init_delegate_return"] == "OK"
    assert result["query_vector"]["primitive_wait"] == "TRUE"
    assert result["query_vector"]["unpack"] == "OK"
    assert all(result["normal_close"].values())
    assert result["peer_flow"]["wire"]["state"] == "PUBLIC_CONFORMANT"
    assert calls == ["TCP_BEFORE", "BEFORE_SEND", "TCP_POST_QUERY", "POST_QUERY"]


@pytest.mark.parametrize("mode", ["wrong_method", "bare_flag", "extra_key"])
def test_new_mode_requires_exact_held_control(tmp_path, monkeypatch, mode):
    f, _ = selected_peer(tmp_path, monkeypatch)
    raw = f.helper._read_root_ref(f.plan["reference_init_ref"])
    control = json.loads(raw)
    if mode == "wrong_method":
        control["method"] = "init-query-vector-v1"
    elif mode == "extra_key":
        control["pid"] = 999
    else:
        control.update(schema_id="qm.ivv.reference-control.v2", method="init-query-vector-v1")
    changed = f.helper._canonical(control)
    monkeypatch.setattr(f.helper, "_read_root_ref", lambda *a, **k: changed)
    with pytest.raises(f.helper.CaptureRejected):
        run(f)
    assert f.transport.writes == 0


def public_packet(tmp_path, monkeypatch):
    f = instrumented(tmp_path, monkeypatch, "write_only")
    env, request = real_public_pack(f)
    result = env["InitConnect"].pack_req(300, "PyNormal", True, False, 0)
    assert result[:2] == (0, "") and result[3:] == (1001, 7)
    return f.helper, result[2], request


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "custom_id",
        "extra",
        "duplicate",
        "noncanonical",
        "private",
        "truncated",
        "serial",
        "serial_bool",
        "ft",
        "proto",
        "fmt",
        "version",
        "sha",
        "reserved",
        "size",
        "encrypted",
        "large",
        "type",
    ],
)
def test_digest_requires_actual_closed_public_packet(tmp_path, monkeypatch, fault):
    h, original, request = public_packet(tmp_path, monkeypatch)
    raw, serial = bytearray(original), 7
    if fault in ("custom_id", "extra", "duplicate", "noncanonical", "private", "encrypted"):
        body = bytes(raw[44:])
        if fault == "custom_id":
            pb = request.FromString(body)
            pb.c2s.clientID = "PRIVATE-CLIENT"
            body = pb.SerializeToString()
        elif fault == "extra":
            body += b"\x10\x01"
        elif fault == "duplicate":
            body += body
        elif fault == "noncanonical":
            body = b"\x0a\xa6\x00" + body[2:]
        elif fault == "private":
            body += b"\x1a\x0bPRIVATE-KEY"
        else:
            body = b"ENCRYPTED-UNKNOWN"
        raw[44:] = body
        raw[12:16] = struct.pack("<I", len(body))
        raw[16:36] = hashlib.sha1(body).digest()
    elif fault == "truncated":
        raw = raw[:43]
    elif fault == "serial":
        serial = 8
    elif fault == "serial_bool":
        serial = True
    elif fault in ("ft", "proto", "fmt", "version", "sha", "reserved", "size"):
        raw[
            {"ft": 0, "proto": 2, "fmt": 6, "version": 7, "sha": 16, "reserved": 36, "size": 12}[
                fault
            ]
        ] ^= 1
    elif fault == "large":
        raw += b"x" * 1024
    elif fault == "type":
        raw = memoryview(raw)
    observed = h._public_init_wire(raw, serial)
    if fault == "none":
        assert observed["state"] == "PUBLIC_CONFORMANT"
        assert observed["packet_sha256"] == hashlib.sha256(original).hexdigest()
        assert len(original) == 84
    else:
        assert observed["state"] in ("NONCONFORMANT", "UNKNOWN")
        assert observed["packet_sha256"] is None
    assert "PRIVATE" not in json.dumps(observed)
    h._select_peer_flow(dict(h._empty_peer_flow(), wire=observed), h._require)


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "short",
        "state",
        "counter_regress",
        "prior",
        "denied",
        "identity",
        "big_endian",
        "unsupported",
    ],
)
def test_tcp_info_native_prefix_counter_and_identity_controls(tmp_path, monkeypatch, fault):
    f, calls = selected_peer(tmp_path, monkeypatch)
    sock = f.transport.conn.sock
    original = sock.getsockopt
    count = 0

    def info(*args):
        nonlocal count
        count += 1
        raw = bytearray(original(*args))
        if fault == "short":
            return bytes(raw[:135])
        if fault == "state":
            raw[0] = 8
        if fault == "counter_regress" and count == 2:
            struct.pack_into("=Q", raw, 120, 0)
        if fault == "prior" and count == 1:
            struct.pack_into("=Q", raw, 128, 1)
        if fault == "denied":
            raise PermissionError("PRIVATE")
        if fault == "identity" and count == 2:
            sock.fileno = lambda: 1000001
        return bytes(raw)

    sock.getsockopt = info
    if fault == "big_endian":
        monkeypatch.setattr(f.helper.sys, "byteorder", "big")
    if fault == "unsupported":
        monkeypatch.setattr(f.helper.sys, "platform", "win32")
    result = run(f)
    client = result["peer_flow"]["client"]
    assert all(result["normal_close"].values()) and f.transport.writes == 1
    if fault == "none":
        assert client["relation"] == "VALID" and client["acked_delta"] == 84
    else:
        assert client["relation"] == "RACE_OR_UNKNOWN"
        if fault in ("short", "big_endian", "unsupported"):
            assert client["abi"] == "UNSUPPORTED" and client["acked_delta"] is None
        elif fault == "counter_regress":
            assert client["acked_delta"] is None
        elif fault == "identity":
            assert client["identity"] == "DRIFT" and client["acked_delta"] is None
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("phase", ["BEFORE_SEND", "POST_QUERY"])
@pytest.mark.parametrize("kind", ["optional", "mandatory", "interrupt", "corrupt_reply"])
def test_sensor_faults_keep_owned_close_and_mandatory_refusal(tmp_path, monkeypatch, phase, kind):
    f, _ = selected_peer(tmp_path, monkeypatch)
    callback = f.plan["_peer_flow"]

    def sensor(point, fd, inode):
        if point != phase:
            return callback(point, fd, inode)
        if kind == "optional":
            raise OSError("PRIVATE")
        if kind == "mandatory":
            raise f.helper.CaptureRejected("mandatory_guard")
        if kind == "interrupt":
            raise KeyboardInterrupt("PRIVATE")
        return {"payload": "PRIVATE"}

    f.plan["_peer_flow"] = sensor
    result = run(f)
    assert all(result["normal_close"].values())
    if kind == "optional":
        assert f.transport.writes == 1
        assert result["query_vector"]["primitive_wait"] == "FALSE"
    else:
        assert result["query_vector"]["guard"] != dict(stage="NONE", code="NONE")
        r = module("ivv_trusted_runner")
        assert r._reference_from_error(r._reference_result(result))["operation_failed"] is True
    assert "PRIVATE" not in json.dumps(result)


def test_native_ephemeral_tcp_info_and_exact_reverse_queue_frontiers():
    if os.name != "posix":
        pytest.skip("Linux TCP_INFO and procfs native control")
    h, r = module("capture_opend_ivv_daily"), module("ivv_trusted_runner")
    listener = socket.socket()
    client = socket.socket()
    peer = None
    try:
        listener.settimeout(2)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        client.settimeout(2)
        client.connect(listener.getsockname())
        peer, _ = listener.accept()
        peer.settimeout(2)
        conn = NS(sock=client)
        net = NS(_conn_map={1: conn})
        binding = (
            net,
            1,
            conn,
            client,
            client.fileno(),
            h._InstrumentedReferenceBackend._socket_stamp(client.fileno()),
        )
        before = h._owned_tcp_info(binding, "BEFORE_SEND")
        assert before["abi"] == "SUPPORTED" and before["state"] == "ESTABLISHED"
        payload = b"public-synthetic-request"
        client.sendall(payload)
        deadline = time.monotonic() + 2
        while True:
            end = h._owned_tcp_info(binding, "POST_QUERY")
            if end["acked"] - before["acked"] == len(payload):
                break
            assert time.monotonic() < deadline
            time.sleep(0.001)
        assert end["received"] == before["received"]
        from pathlib import Path

        producer = module("ivv_native_producer")
        reader = producer.PosixReader()
        reader.deadline = time.monotonic() + 2
        try:
            own = reader.directory("/proc/" + str(os.getpid()))
            assert r._peer_read(reader, own, "net/tcp", 1) is None
            inodes = r._peer_socket_inodes(reader, own)
            sample, key = r._peer_table_projection(
                r._peer_read(reader, own, "net/tcp"), os.fstat(client.fileno()).st_ino, inodes
            )
            assert sample["vendor_fd"] == "PRESENT" and sample["rx"] == "LE_1K"
            assert key == (
                f"0100007F:{client.getsockname()[1]:04X}".encode(),
                f"0100007F:{peer.getsockname()[1]:04X}".encode(),
            )
            # ACK and queued data precede the synthetic application's consume.
            assert peer.recv(1024) == payload
            after, _ = r._peer_table_projection(
                r._peer_read(reader, own, "net/tcp"), os.fstat(client.fileno()).st_ino, inodes
            )
            assert after["rx"] == "ZERO"
            peer.sendall(b"synthetic-response")
            deadline = time.monotonic() + 2
            while h._owned_tcp_info(binding, "POST_QUERY")["received"] == end["received"]:
                assert time.monotonic() < deadline
                time.sleep(0.001)
            assert client.recv(1024) == b"synthetic-response"
            # A port-only/foreign reverse row cannot substitute for the full tuple.
            assert Path("/proc/self/fd/" + str(client.fileno())).is_socket()
        finally:
            reader.close()
            assert reader.fds == [] and not reader.close_failed
    finally:
        if peer is not None:
            peer.close()
        client.close()
        listener.close()


def origin():
    return dict(
        schema="qm.ivv.executable-origin.v1",
        method="EXACT_PATH",
        phase="SESSION",
        python_sha256="b" * 64,
        namespace_inode=44,
        kernel_mount_readonly="UNKNOWN",
    )


def test_child_rpc_uses_checked_existing_channel_and_order_only():
    r = module("ivv_trusted_runner")
    sent, checks = [], []
    channel = NS(send=sent.append, recv=lambda pid: {"peer_flow": r._peer_unknown()})
    session = r._ChildSession(
        channel, 19, lambda: checks.append(True) or {"executable_origin": origin()}
    )
    assert session.peer_flow("BEFORE_SEND", 12, 37) == r._peer_unknown()
    assert session.peer_flow("POST_QUERY", 12, 37) == r._peer_unknown()
    assert len(checks) == 2
    assert [p["phase"] for p in sent] == ["BEFORE_SEND", "POST_QUERY"]
    assert all(set(p) == {"op", "phase", "fd", "inode", "executable_origin"} for p in sent)
    assert all(p["op"] == "init_peer_flow" and p["executable_origin"] == origin() for p in sent)
    with pytest.raises(r.Refused, match="PEER_FLOW_ORDER"):
        session.peer_flow("POST_QUERY", 12, 37)


@pytest.mark.parametrize(
    "fault",
    [
        "order",
        "fd_bool",
        "inode_bool",
        "negative",
        "overflow",
        "origin",
        "reply_extra",
        "reply_type",
        "private",
        "false_read",
    ],
)
def test_child_rpc_refuses_spoof_and_malformed_reply(fault):
    r = module("ivv_trusted_runner")
    answer = {"peer_flow": r._peer_unknown()}
    phase, fd, inode = "BEFORE_SEND", 12, 37
    if fault == "order":
        phase = "POST_QUERY"
    elif fault == "fd_bool":
        fd = True
    elif fault == "inode_bool":
        inode = True
    elif fault == "negative":
        fd = -1
    elif fault == "overflow":
        inode = 1 << 63
    elif fault == "reply_extra":
        answer["payload"] = "PRIVATE"
    elif fault == "reply_type":
        answer["peer_flow"]["offset_ms"] = True
    elif fault == "private":
        answer["peer_flow"]["rx"] = "PRIVATE"
    elif fault == "false_read":
        answer["peer_flow"]["handler_read"] = True
    channel = NS(send=lambda _: None, recv=lambda _: answer)
    session = r._ChildSession(
        channel, 19, lambda: {} if fault == "origin" else {"executable_origin": origin()}
    )
    with pytest.raises(r.Refused):
        session.peer_flow(phase, fd, inode)


def table(
    client_inode=37,
    reverse=True,
    remote=b"0100007F:2B68",
    rx=0,
    peer_state=b"01",
    duplicate=False,
    client_port=b"ABCD",
    peer_inode=42,
):
    def row(local, remote, state, inode, rx=0):
        return (
            b"0: "
            + local
            + b" "
            + remote
            + b" "
            + state
            + b" 00000000:"
            + f"{rx:08X}".encode()
            + b" 00:00000000 00000000 0 0 "
            + str(inode).encode()
            + b"\n"
        )

    client = row(b"0100007F:" + client_port, remote, b"01", client_inode)
    peer = row(remote, b"0100007F:" + client_port, peer_state, peer_inode, rx)
    return b"header\n" + client + (peer if reverse else b"") + (peer if duplicate else b"")


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "missing",
        "ambiguous",
        "wrong_tuple",
        "no_vendor_fd",
        "closing",
        "listener",
        "large",
        "row_bound",
        "malformed",
    ],
)
def test_exact_reverse_projection_is_not_accept_or_read_claim(fault):
    r = module("ivv_trusted_runner")
    raw, sockets = table(rx=8), {42}
    if fault == "missing":
        raw = table(reverse=False)
    elif fault == "ambiguous":
        raw = table(duplicate=True)
    elif fault == "wrong_tuple":
        raw = table().replace(b"0100007F:ABCD 01 ", b"0100007F:ABCE 01 ")
    elif fault == "no_vendor_fd":
        sockets = set()
    elif fault == "closing":
        raw = table(peer_state=b"08", rx=8)
    elif fault == "listener":
        raw = table(peer_state=b"0A", rx=8)
    elif fault == "large":
        raw = b"x" * 262145
    elif fault == "row_bound":
        raw = b"x\n" * 4097
    elif fault == "malformed":
        raw = b"header\nbad\n"
    sample, key = r._peer_table_projection(raw, 37, sockets)
    if fault == "none":
        assert sample["row"] == "MATCH" and sample["vendor_fd"] == "PRESENT"
        assert sample["rx"] == "LE_1K" and key == (b"0100007F:ABCD", b"0100007F:2B68")
    elif fault in ("missing", "wrong_tuple"):
        assert sample["row"] == "NOT_OBSERVED" and sample["vendor_fd"] == "UNKNOWN"
    elif fault == "ambiguous":
        assert sample["row"] == "AMBIGUOUS"
    elif fault == "no_vendor_fd":
        assert sample["row"] == "MATCH" and sample["vendor_fd"] == "NOT_OBSERVED"
        assert "UNACCEPTED" not in json.dumps(sample)
    elif fault in ("closing", "listener"):
        assert sample["rx"] == sample["tx"] == "UNKNOWN"
    else:
        assert sample == r._peer_unknown() and key is None


def modeled_provider(monkeypatch):
    r = module("ivv_trusted_runner")
    control = dict(schema_id="qm.ivv.reference-control.v3", method=METHOD)
    reader = NS(
        deadline=2,
        processes={7: (103,)},
        closed=False,
        directory=lambda name, parent=None: 102 if name == "8" else 101,
        finish=lambda: [],
        close=lambda: setattr(reader, "closed", True),
        stamp=lambda s: (s.st_dev, s.st_ino, s.st_mode),
        socket_inodes=lambda _: {42},
    )
    provider = r._Provider.__new__(r._Provider)
    provider.__dict__.update(
        helper=NS(_read_reference_control=lambda _: control),
        plan=dict(started_monotonic=0),
        binding=NS(cohort=((1,), (2,), (7,)), net=44),
        producer=NS(OperatorReader=lambda _: reader),
        gateway_gid=1,
        native=NS(_operator_identity=lambda *a: None, _provider_controls=lambda _: None),
        _peer_phase=None,
        _peer_key=None,
        _peer_descriptor=None,
    )
    scope = NS(pid=8, child=dict(start_ticks=9), check_pid=lambda: None)
    old_stat, old_readlink = r.os.stat, r.os.readlink

    def metadata(name, *, dir_fd=None, **kw):
        if dir_fd in (102, 103):
            return NS(
                st_dev=1,
                st_ino=44 if name == "ns/net" else 37,
                st_mode=stat.S_IFDIR if name == "ns/net" else stat.S_IFSOCK,
            )
        return old_stat(name, **kw)

    monkeypatch.setattr(r.os, "stat", metadata)
    monkeypatch.setattr(
        r.os,
        "readlink",
        lambda name, *, dir_fd=None: "socket:[37]" if dir_fd == 102 else old_readlink(name),
    )
    monkeypatch.setattr(r.time, "monotonic", lambda: 0)
    monkeypatch.setattr(r, "_peer_socket_inodes", lambda *a: {42})
    monkeypatch.setattr(r, "_owned_peer", lambda *a, **k: (37, 42))
    monkeypatch.setattr(r, "_peer_read", lambda *a: table())
    request = dict(
        op="init_peer_flow", phase="BEFORE_SEND", fd=12, inode=37, executable_origin=origin()
    )
    return r, provider, reader, scope, request, control


def test_parent_binds_known_pid_namespace_start_fd_and_same_four_tuple(monkeypatch):
    r, provider, reader, scope, request, _ = modeled_provider(monkeypatch)
    assert provider.peer_flow(scope, request)["vendor_fd"] == "PRESENT"
    key = provider._peer_key
    assert key[:3] == ((1, 44), 8, 9) and key[-1] == (b"0100007F:ABCD", b"0100007F:2B68")
    assert reader.closed
    request["phase"] = "POST_QUERY"
    monkeypatch.setattr(r, "_peer_read", lambda *a: table(client_port=b"ABCE"))
    sample = provider.peer_flow(scope, request)
    assert sample["identity"] == "DRIFT" and sample["rx"] == "UNKNOWN"
    assert provider._peer_key == key
    with pytest.raises(r.Refused, match="PEER_FLOW_ORDER"):
        provider.peer_flow(scope, request)


@pytest.mark.parametrize(
    "fault",
    [
        "pid",
        "address",
        "path",
        "fd_bool",
        "inode_bool",
        "old_mode",
        "order",
        "endpoint",
        "mandatory",
        "cleanup",
        "optional",
    ],
)
def test_parent_finite_authority_and_faults(monkeypatch, fault):
    r, provider, reader, scope, request, control = modeled_provider(monkeypatch)
    if fault in ("pid", "address", "path"):
        request[fault] = "PRIVATE"
    elif fault == "fd_bool":
        request["fd"] = True
    elif fault == "inode_bool":
        request["inode"] = True
    elif fault == "old_mode":
        control.update(schema_id="qm.ivv.reference-control.v2", method="init-query-vector-v1")
    elif fault == "order":
        request["phase"] = "POST_QUERY"
    elif fault == "endpoint":
        monkeypatch.setattr(r, "_peer_read", lambda *a: table(remote=b"0100007F:1234"))
    elif fault == "mandatory":
        reader.finish = lambda: ["PROVIDER_RACE"]
    elif fault == "cleanup":
        reader.close = lambda: (_ for _ in ()).throw(OSError("PRIVATE"))
    elif fault == "optional":
        monkeypatch.setattr(r, "_peer_read", lambda *a: None)
    if fault == "optional":
        assert provider.peer_flow(scope, request)["row"] == "UNKNOWN" and reader.closed
    else:
        with pytest.raises(r.Refused):
            provider.peer_flow(scope, request)


@pytest.mark.parametrize("fault", ["fd", "namespace", "pid", "mandatory_peer", "permission"])
def test_parent_identity_refusals_remain_mandatory(monkeypatch, fault):
    r, provider, reader, scope, request, _ = modeled_provider(monkeypatch)
    metadata = r.os.stat
    if fault in ("fd", "namespace"):

        def changed(name, *, dir_fd=None, **kwargs):
            result = metadata(name, dir_fd=dir_fd, **kwargs)
            if dir_fd in (102, 103) and (
                (fault == "fd" and name.startswith("fd/"))
                or (fault == "namespace" and name == "ns/net")
            ):
                result.st_ino += 1
            return result

        monkeypatch.setattr(r.os, "stat", changed)
    elif fault == "pid":
        scope.check_pid = lambda: (_ for _ in ()).throw(r.Refused("CHILD_PID_CHANGED"))
    elif fault == "mandatory_peer":
        monkeypatch.setattr(
            r,
            "_owned_peer",
            lambda *a, **k: (_ for _ in ()).throw(r.Refused("CAPTURE_PEER_NOT_PROVIDER_OWNED")),
        )
    else:
        monkeypatch.setattr(
            r, "_peer_read", lambda *a: (_ for _ in ()).throw(PermissionError("PRIVATE"))
        )
    if fault == "permission":
        assert provider.peer_flow(scope, request) == r._peer_unknown()
    else:
        with pytest.raises(r.Refused):
            provider.peer_flow(scope, request)


@pytest.mark.parametrize(
    "field,value",
    [
        ("acked_delta", True),
        ("acked_delta", -1),
        ("acked_delta", 1 << 63),
        ("unacked_end", 1 << 32),
        ("received_delta", 1.5),
    ],
)
def test_delta_contract_rejects_type_confusion_and_overflow(field, value):
    h, r = module("capture_opend_ivv_daily"), module("ivv_trusted_runner")
    flow = h._empty_peer_flow()
    flow["client"][field] = value
    with pytest.raises(h.CaptureRejected):
        h._select_peer_flow(flow, h._require)
    with pytest.raises(r.Refused):
        r._select_peer_flow(flow, r.need)


@pytest.mark.parametrize(
    "patch",
    [
        "digest",
        "bool",
        "private",
        "read",
        "accept",
        "sequential",
        "clock",
        "valid_without_counters",
        "uppercase_digest",
    ],
)
def test_finite_privacy_and_causal_closure(patch):
    h, r = module("capture_opend_ivv_daily"), module("ivv_trusted_runner")
    flow = h._empty_peer_flow()
    if patch == "digest":
        flow["wire"]["packet_sha256"] = "a" * 64
    elif patch == "bool":
        flow["wire"]["public_c2s"] = 1
    elif patch == "private":
        flow["wire"]["client_id"] = "PRIVATE"
    elif patch == "read":
        flow["peer_after"]["handler_read"] = True
    elif patch == "accept":
        flow["peer_after"]["row"] = "UNACCEPTED"
    elif patch == "sequential":
        flow["timing"]["sequential"] = False
    elif patch == "clock":
        flow["peer_after"]["offset_ms"] = True
    elif patch == "valid_without_counters":
        flow["client"]["relation"] = "VALID"
    else:
        flow["wire"].update(state="PUBLIC_CONFORMANT", packet_sha256="A" * 64)
    with pytest.raises(h.CaptureRejected):
        h._select_peer_flow(flow, h._require)
    with pytest.raises(r.Refused):
        r._select_peer_flow(flow, r.need)


def test_zero_unacked_cannot_invent_ack_progress_and_counter_mutant_fails(tmp_path, monkeypatch):
    f, _ = selected_peer(tmp_path, monkeypatch)
    info = f.transport.conn.sock.getsockopt

    def no_ack(*args):
        raw = bytearray(info(*args))
        struct.pack_into("=Q", raw, 120, 1)
        return bytes(raw)

    f.transport.conn.sock.getsockopt = no_ack
    result = run(f)
    client = result["peer_flow"]["client"]
    assert client["unacked_before"] == client["unacked_end"] == 0
    assert client["acked_delta"] == 0
    # A RAM mutant inferring byte acknowledgement from zero outstanding packets
    # contradicts the actual cumulative byte counters.
    client["acked_delta"] = 84 if client["unacked_end"] == 0 else None
    with pytest.raises(AssertionError):
        assert client["acked_delta"] == 0


def test_late_notify_cannot_rewrite_original_timeout_under_new_method(tmp_path, monkeypatch):
    f, _ = selected_peer(tmp_path, monkeypatch)
    env = f.modules[0].OpenQuoteContext.__mro__[1].__init__.__globals__

    def late(*args):
        req = f.transport.request_ref()
        assert req.err is env["PacketErr"].Timeout
        f.transport.received = [f.transport.frame()]
        f.transport.pump()

    env["logger"].warning2 = late
    result = run(f)
    vector = result["query_vector"]
    assert vector["primitive_wait"] == "FALSE" and vector["packet_err_snapshot"] == "Timeout"
    assert vector["unpack"] == "UNOBSERVED" and result["init_delegate_return"] == "NON_OK"
    assert vector["receive"]["notify_when"] == "AFTER_WAIT_END"
    assert vector["attribution"] == "RACE_OR_UNKNOWN"
    assert all(result["normal_close"].values())


def test_ram_end_sensor_inside_event_is_detected_before_timeout_assignment(tmp_path, monkeypatch):
    f, calls = selected_peer(tmp_path, monkeypatch)
    env = f.modules[0].OpenQuoteContext.__mro__[1].__init__.__globals__
    event_wait = env["threading"].Event.wait

    def wrong_wait(event, *args, **kwargs):
        result = event_wait(event, *args, **kwargs)
        # Deliberately forbidden scheduling: before ReqInfo's Timeout decision.
        assert f.made[0]._query_request.err is env["PacketErr"].Ok
        f.made[0]._peer_post_query()
        return result

    env["threading"].Event.wait = wrong_wait
    result = run(f)
    with pytest.raises(AssertionError):
        assert_timeout_causal(f.made[0], result, calls)


@pytest.mark.parametrize("downgrade", [False, True])
def test_actual_parent_condition_binds_v3_control_to_v4_only(downgrade):
    import inspect
    import textwrap

    import test_ivv_reference_condition as fixture

    h = module("capture_opend_ivv_daily")
    tree = ast.parse(textwrap.dedent(inspect.getsource(fixture.ConditionOwner.fixture)))
    changed = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in list(node.keywords):
            if kw.arg != "schema_id" or not isinstance(kw.value, ast.Constant):
                continue
            if kw.value.value == "qm.ivv.reference-control.v1":
                kw.value.value = "qm.ivv.reference-control.v3"
                node.keywords.append(ast.keyword(arg="method", value=ast.Constant(METHOD)))
                changed.append("control")
            elif kw.value.value == "qm.ivv.reference-init-observation.v1":
                kw.value.value = (
                    "qm.ivv.reference-init-observation.v3"
                    if downgrade
                    else "qm.ivv.reference-init-observation.v4"
                )
                fields = dict(
                    method="init-query-vector-v1" if downgrade else METHOD,
                    init_delegate_return="OK",
                    query_vector=h._empty_query_vector(),
                )
                if not downgrade:
                    fields["peer_flow"] = h._empty_peer_flow()
                for key, value in fields.items():
                    node.keywords.append(
                        ast.keyword(arg=key, value=ast.parse(repr(value), mode="eval").body)
                    )
                changed.append("observation")
    assert changed == ["observation", "control"] or changed == ["control", "observation"]
    env = dict(vars(fixture))
    exec(compile(ast.fix_missing_locations(tree), "v3-v4-owner-fixture", "exec"), env)
    case = fixture.ConditionOwner()
    try:
        r, book, value, pair_sha, native, producer, read = env["fixture"](case)
        if downgrade:
            with pytest.raises(r.Refused, match="REFERENCE_CONTROL_METHOD"):
                r.reference_capture_condition(book, pair_sha, read, native, producer)
        else:
            result = r.reference_capture_condition(book, pair_sha, read, native, producer)
            assert result["pair_sha256"] == pair_sha
            outcome = book._read(value["reference_attempt"] + ".reference-condition.json")
            assert outcome["state"] == "POSITIVE"
    finally:
        case.doCleanups()


@pytest.mark.parametrize("metadata_kind", ["ordinary", "guard", "interrupt"])
def test_post_query_sensor_never_masks_original_exception(tmp_path, monkeypatch, metadata_kind):
    f, _ = selected_peer(tmp_path, monkeypatch, "write_only")
    env = f.modules[0].OpenQuoteContext.__mro__[1].__init__.__globals__
    original = OSError(9, "PRIVATE-ORIGINAL")
    metadata = (
        RuntimeError("PRIVATE-METADATA")
        if metadata_kind == "ordinary"
        else f.helper.CaptureRejected("metadata_guard")
        if metadata_kind == "guard"
        else SystemExit("PRIVATE-METADATA")
    )

    def failed(*args, **kwargs):
        raise original

    env["threading"].Event.wait = failed
    callback = f.plan["_peer_flow"]

    def peer(phase, fd, inode):
        if phase == "POST_QUERY":
            raise metadata
        return callback(phase, fd, inode)

    f.plan["_peer_flow"] = peer
    writer = f.helper._Writer(f.root, lambda _: None)
    observer = f.helper._InstrumentedReferenceObserver(f.plan, writer, f.clock)
    backend = f.factory(observer, writer, f.plan, f.clock)
    f.book.may_connect(f.plan["_recovery_attempt"])
    try:
        with pytest.raises(BaseException) as caught:
            backend.open()
        assert caught.value is original
        assert "wait" not in vars(backend._query_request)
        assert "wait" not in vars(backend._query_request.event)
        if metadata_kind != "ordinary":
            assert observer.poison is not None
    finally:
        backend.close()
        assert all(backend.close_evidence().values())


@pytest.mark.parametrize(
    "error", [KeyboardInterrupt("PRIVATE"), SystemExit("PRIVATE"), OSError("PRIVATE")]
)
def test_actual_owned_peer_callback_preserves_interrupt_identity(error):
    import inspect

    h = module("capture_opend_ivv_daily")
    tree = ast.parse(inspect.getsource(h._capture_owned))
    callback = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "peer_flow"
    )

    def failed(*args):
        raise error

    env = dict(state=NS(session=NS(peer_flow=failed)), CaptureRejected=h.CaptureRejected)
    exec(compile(ast.Module(body=[callback], type_ignores=[]), "owned-callback", "exec"), env)
    with pytest.raises(BaseException) as caught:
        env["peer_flow"]("BEFORE_SEND", 12, 37)
    if isinstance(error, Exception):
        assert type(caught.value) is h.CaptureRejected
    else:
        assert caught.value is error


def test_native_synthetic_response_dispatch_uses_frozen_sdk_and_post_query_end(
    tmp_path, monkeypatch
):
    if os.name != "posix":
        pytest.skip("Linux native ephemeral dispatch control")
    import threading
    from pathlib import Path

    actual_uname = os.uname
    f, _ = selected_peer(tmp_path, monkeypatch, "normal")
    monkeypatch.setattr(os, "uname", actual_uname)
    r = module("ivv_trusted_runner")
    listener, client = socket.socket(), socket.socket()
    peer = None
    worker = None
    errors, phases = [], []
    try:
        listener.settimeout(2)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        client.settimeout(2)
        client.connect(listener.getsockname())
        peer, _ = listener.accept()
        peer.settimeout(2)
        response = f.transport.frame()

        def serve():
            try:
                raw = bytearray()
                while len(raw) < 84:
                    part = peer.recv(84 - len(raw))
                    assert part
                    raw.extend(part)
                assert f.helper._public_init_wire(raw, 7)["state"] == "PUBLIC_CONFORMANT"
                peer.sendall(response)
            except BaseException as error:
                errors.append(type(error).__name__)

        worker = threading.Thread(target=serve)
        worker.start()

        class NativeSocket:
            def fileno(self):
                return client.fileno()

            def getsockopt(self, *args):
                return client.getsockopt(*args)

            def send(self, raw):
                f.transport.writes += 1
                return client.send(raw)

            def recv(self, maximum):
                f.transport.reads += 1
                f.transport.received.pop(0)
                return client.recv(maximum)

        f.transport.conn.sock = NativeSocket()

        def sample(phase, fd, inode):
            assert fd == client.fileno() and inode == os.fstat(fd).st_ino
            if phase == "POST_QUERY":
                req = f.made[0]._query_request
                assert req.err.name == "Ok" and req.unpack_func == f.transport.public_unpack
                assert "wait" not in vars(req.event) and "wait" not in vars(req)
            phases.append(phase)
            selected, _ = r._peer_table_projection(
                Path("/proc/self/net/tcp").read_bytes(), inode, {os.fstat(peer.fileno()).st_ino}
            )
            return selected

        f.plan["_peer_flow"] = sample
        result = run(f)
        worker.join(2)
        assert not worker.is_alive() and not errors
        assert result["state"] == "REFERENCE_READY_CLOSED" and all(
            result["normal_close"].values()
        ), {key: result[key] for key in ("primary_failure", "close_failure", "normal_close")}
        vector, flow = result["query_vector"], result["peer_flow"]
        assert vector["primitive_wait"] == "TRUE" and vector["unpack"] == "OK"
        assert vector["receive"]["target_notify_err"] == "Ok"
        assert vector["receive"]["notify_when"] == "BEFORE_WAIT_END"
        assert flow["client"]["acked_delta"] == 84
        assert flow["client"]["received_delta"] == len(response)
        assert phases == ["BEFORE_SEND", "POST_QUERY"] and f.transport.reads == 1
        assert "PRIVATE" not in json.dumps(result)
    finally:
        if peer is not None:
            peer.close()
        client.close()
        listener.close()
        if worker is not None:
            worker.join(2)
            assert not worker.is_alive()
