"""Reference Init uses actual guarded helper/ledger code and synthetic external I/O."""

import json
from types import SimpleNamespace as NS

import pytest
from test_ivv_capture_contract import Clock
from test_ivv_capture_contract import contract as old_plan
from test_ivv_init_e2e import full_transport
from test_ivv_recovery_capture import ledger, module


@pytest.mark.parametrize("identity", ["nonce", "reference_context", "capture_context"])
def test_hash_consistent_reference_pair_control_mismatch_precedes_held_permit_and_may(
    tmp_path, monkeypatch, identity
):
    from test_ivv_recovery_capture import connected_recovery_capture

    with pytest.raises(Exception) as refused:
        connected_recovery_capture(
            tmp_path, monkeypatch, reference=True, reference_identity_fault=identity
        )
    assert not list((tmp_path / "ledger").glob("*.may.json"))
    assert isinstance(refused.value, ValueError)
    assert str(refused.value) == "reference_control_pair"
    assert not (tmp_path / "permit.json").exists()
    assert not (tmp_path / "capture").exists()


@pytest.mark.parametrize("fault", ["control", "permit", "plan"])
def test_reference_actual_held_admission_drift_refuses_before_may(tmp_path, monkeypatch, fault):
    from pathlib import Path

    from test_ivv_recovery_capture import connected_recovery_capture

    def entry(helper, issuer, runner, state, final, profile, snapshot, root):
        target = {
            "control": Path(final["reference_init_ref"]["path"]),
            "permit": tmp_path / "permit.json",
            "plan": tmp_path / "plan.json",
        }[fault]
        raw = target.read_bytes()
        target.write_bytes(raw + b" ")
        return lambda *a: pytest.fail("drift reached SDK constructor")

    with pytest.raises(ValueError):
        connected_recovery_capture(tmp_path, monkeypatch, reference=True, entry_hook=entry)
    assert not list((tmp_path / "ledger").glob("*.may.json"))
    assert not (tmp_path / "capture").exists()


@pytest.mark.parametrize("fault", ["partial", "close"])
def test_reference_partial_constructor_and_close_failure_never_observed_ready(
    tmp_path, monkeypatch, fault
):
    f = official_reference(tmp_path, monkeypatch)
    base = f.modules[0].OpenQuoteContext
    original = base.__init__

    def partial(ctx, **kw):
        original(ctx, **kw)
        raise RuntimeError("synthetic constructor failure")

    if fault == "partial":
        base.__init__ = partial
    else:
        base.close = lambda ctx: (_ for _ in ()).throw(OSError("synthetic close failure"))
    result = f.helper._run_reference_init(
        f.plan, f.root, backend_factory=f.factory, clock=f.clock, sync_dir=lambda _: None
    )
    assert result["state"] == "REFERENCE_FAILED"
    r = module("ivv_trusted_runner")
    failed = r._reference_result(result)
    assert r.reason(failed) == (
        "REFERENCE_INIT_FAILED" if fault == "partial" else "SDK_CLOSE_UNKNOWN"
    )
    obs = r._reference_from_error(failed)
    assert obs["parent_closed"] is False
    assert not (f.book.root / "connection-000002.intent.json").exists()


@pytest.mark.parametrize("patch", [{"reason": "OTHER"}, {"unit_returncode": 0}])
def test_expected_reference_parent_stop_requires_exact_exit_reason(patch):
    r = module("ivv_trusted_runner")
    obs = dict(observation(), parent_closed=True)
    status = dict(
        state="STOP",
        reason="REFERENCE_INIT_OBSERVATION",
        unit_returncode=1,
        reference_init_observation=obs,
        stage="RELEASED_RECOVERY_ATTEMPT",
        automatic_retry=False,
        provider_mutation=False,
        publication_sha256="b" * 64,
    )
    status.update(patch)
    with pytest.raises(r.Refused, match="REFERENCE_STOP_BINDING"):
        r.select_failure_status(status, "b" * 64)


def supervisor_reference(monkeypatch, fault=None, pidfd_first=False, run_root=None):
    import stat
    import struct

    from test_ivv_trusted_runner import owned_scope

    r = module("ivv_trusted_runner")
    helper = module("capture_opend_ivv_daily")
    mode = "connection-000001"
    scope, kernel = owned_scope(
        r,
        monkeypatch,
        create=run_root is None,
        unit="owned.service" if run_root is None else "qm-ivv-recovery-" + mode + ".service",
    )
    if run_root is not None:
        bind = r._Scope.bind

        def bound(owner, pid):
            nonlocal scope
            bind(owner, pid)
            scope = owner

        monkeypatch.setattr(r._Scope, "bind", bound)
    monitor = NS(next=0, last={}, sample=lambda: setattr(monitor, "next", 5))
    monkeypatch.setattr(r, "_Provider", lambda *a, **kw: monitor)
    monkeypatch.setattr(r, "_authorize", lambda *a: ({}, {}, {}, {}))
    monkeypatch.setattr(r, "_child_kernel", lambda *a, **kw: {"namespace_inode": 44})
    monkeypatch.setattr(r, "_owned_peer", lambda *a: (1, 2))
    monkeypatch.setattr(r.time, "monotonic", lambda: 0)
    origin = dict(
        schema="qm.ivv.executable-origin.v1",
        method="EXACT_PATH",
        phase="INITIAL",
        python_sha256="b" * 64,
        namespace_inode=44,
        kernel_mount_readonly="UNKNOWN",
    )
    obs = observation()
    if fault == "owner":
        obs["parent_closed"] = True
    if fault == "sdk_close":
        obs["normal_close"]["callbacks_stopped"] = False
    if fault == "operation":
        obs["operation_failed"] = True
    if fault == "control":
        obs["reference_control_sha256"] = "c" * 64
    terminal = dict(op="failed", code="REFERENCE_INIT_OBSERVATION", reference_init_observation=obs)
    packets = [
        dict(op="ready", executable_origin=origin),
        dict(op="observe", executable_origin=dict(origin, phase="SESSION")),
    ]
    if fault != "missing":
        packets.append(terminal)
    if fault == "duplicate":
        packets.append(terminal)

    class Socket:
        type = 5

        def fileno(self):
            return 99

        def setsockopt(self, *a):
            pass

        def settimeout(self, *a):
            pass

        def gettimeout(self):
            return 20

        def close(self):
            pass

        def send(self, raw):
            return len(raw)

        def recvmsg(self, *a):
            if not packets:
                if fault == "no_eof":
                    return b"{}", [(1, 2, struct.pack("3i", 502, 0, 0))], 0, None
                return b"", [], 0, None
            item = packets.pop(0)
            peer = 999 if fault == "foreign" and item.get("op") == "failed" else 502
            return r.raw_json(item), [(1, 2, struct.pack("3i", peer, 0, 0))], 0, None

    monkeypatch.setattr(
        r,
        "socket",
        NS(
            SOL_SOCKET=1,
            SO_PASSCRED=3,
            SOCK_SEQPACKET=5,
            SCM_CREDENTIALS=2,
            CMSG_SPACE=lambda n: n,
            MSG_DONTWAIT=64,
        ),
    )
    fstat = kernel.os.fstat
    kernel.os.fstat = lambda fd: (
        NS(st_dev=1, st_ino=99, st_uid=0, st_mode=stat.S_IFSOCK) if fd == 99 else fstat(fd)
    )
    channel = r._Channel(Socket())

    def ready(*args):
        final = (pidfd_first and len(packets) == 1) or not packets
        if not final:
            return [channel.s], [], []
        leaf = kernel.handles[scope.leaf]
        kernel.nodes[leaf + "/cgroup.procs"]["content"] = "999" if fault == "populated" else ""
        if fault == "resource":
            kernel.nodes[leaf + "/memory.events"]["content"] = "oom_kill 1"
        return [scope.pidfd], [], []

    monkeypatch.setattr(r, "select", NS(select=ready))
    kernel.os.waitid = lambda *a: NS(
        si_pid=502, si_code=2 if fault == "signal" else 1, si_status=1 if fault == "nonzero" else 0
    )
    monkeypatch.setattr(r, "_seal", lambda *a: pytest.fail("reference reached capture seal"))
    context = (
        dict(budget_ref={}),
        dict(_recovery_mode="connection-000001", catalog_ref=dict(python_sha256="b" * 64)),
        None,
        helper,
        None,
        None,
    )
    plan = dict(started_monotonic=0, reference_init_ref=dict(sha256="a" * 64))
    if run_root is not None:
        from pathlib import Path

        from quantmesh.research import ivv_recovery as contract

        task = module("ivv_additional_task")
        profile = task.RecoveryProfile(contract, contract.DEFAULT_POLICY, mode)
        run_root.mkdir()
        book = task.RecoveryLedger(run_root, profile.policy, contract, sync_dir=lambda _: None)
        catalog = {k: "b" * 64 for k in r._sources(mode)}
        method = r.digest(r.raw_json(catalog))
        book.begin(method, now=0)
        ledger_type = task.RecoveryLedger
        task.RecoveryLedger = lambda *a: ledger_type(*a, sync_dir=lambda _: None)
        context[1].update(
            _additional=profile,
            _recovery_task=task,
            catalog_ref={**catalog, "python_sha256": "b" * 64},
        )
        monkeypatch.setattr(r, "_locations", lambda mode: NS(control=run_root, ledger=run_root))
        monkeypatch.setattr(r, "_bootstrap", lambda *a, **kw: context)
        monkeypatch.setattr(r, "_seed", lambda *a, **kw: plan)
        monkeypatch.setattr(r, "_stdio", lambda: None)
        monkeypatch.setattr(r, "_fds", lambda: {0, 1, 2, 100})
        prior = Path.iterdir
        monkeypatch.setattr(
            Path, "iterdir", lambda p: iter([1]) if p.as_posix() == "/proc/self/task" else prior(p)
        )
        kernel.os.umask = lambda mode: None
        kernel.os.fork = lambda: 502
        kernel_stat = kernel.os.stat
        kernel.os.stat = lambda p, **kw: (
            NS(st_dev=1, st_ino=44, st_uid=0, st_mode=0)
            if str(p) == "/proc/self/ns/mnt"
            else kernel_stat(p, **kw)
        )
        r.socket.AF_UNIX = 1
        r.socket.SOCK_CLOEXEC = 0
        r.socket.socketpair = lambda *a: (channel.s, Socket())
        original_close = kernel.os.close

        def closed(fd):
            if fd == 100:
                if fault == "lease":
                    raise OSError("modeled lease close")
                return
            original_close(fd)
            if fault == "fd" and fd == scope.total_events[0]:
                raise OSError("modeled FD close")

        kernel.os.close = closed
        remove = kernel.os.rmdir

        def removed(*a, **kw):
            remove(*a, **kw)
            if fault == "late_resource":
                path = kernel.handles[scope.group] + "/memory.events"
                kernel.nodes[path]["content"] = "oom_kill 1"

        kernel.os.rmdir = removed
        monkeypatch.setattr(
            r, "put", lambda *a: pytest.fail("reference wrote a capture parent seal")
        )
        with pytest.raises(r.Refused) as raised:
            r._run(dict(sha256="c" * 64), additional=mode, lifecycle=r._RecoveryLease(100))
        return r, r._failure_record(raised.value), book, kernel
    result = r._supervise(scope, channel, 700, context, plan)
    return r, result, scope, kernel


@pytest.mark.parametrize("pidfd_first", [False, True])
def test_actual_supervisor_reference_stop_requires_normal_wait_and_eof(monkeypatch, pidfd_first):
    r, result, scope, kernel = supervisor_reference(monkeypatch, pidfd_first=pidfd_first)
    assert result == {"reference_init_observation": observation()}
    assert scope.reaped is True and kernel.signals == []
    assert result["reference_init_observation"]["parent_closed"] is False


@pytest.mark.parametrize(
    "fault",
    [
        "foreign",
        "owner",
        "sdk_close",
        "operation",
        "control",
        "duplicate",
        "no_eof",
        "missing",
        "populated",
        "resource",
        "signal",
        "nonzero",
    ],
)
def test_actual_supervisor_reference_uncertainty_is_not_expected_stop(monkeypatch, fault):
    with pytest.raises(ValueError):
        supervisor_reference(monkeypatch, fault)


@pytest.mark.parametrize("fault", [None, "fd", "lease", "late_resource"])
def test_real_parent_reference_marker_waits_for_final_closure(tmp_path, monkeypatch, fault):
    r, record, book, kernel = supervisor_reference(monkeypatch, fault, run_root=tmp_path / "ledger")
    if fault is None:
        assert record["reason"] == "REFERENCE_INIT_OBSERVATION"
        assert record["reference_init_observation"]["parent_closed"] is True
        assert kernel.handles == {} and kernel.signals == []
        closure = book._read("connection-000001.close.json")
        assert closure["owner_state"] == "CLOSED"
    else:
        assert record["reason"] != "REFERENCE_INIT_OBSERVATION"
        assert not record.get("reference_init_observation", {}).get("parent_closed", False)
    assert len(list(book.root.glob("connection-*.intent.json"))) == 1
    assert not (book.root / "parent-close.json").exists()


def observation():
    return dict(
        schema_id="qm.ivv.reference-init-observation.v1",
        reference_control_sha256="a" * 64,
        constructor_status="READY",
        operation_failed=False,
        close_failed=False,
        normal_close=dict(context_closed=True, callbacks_stopped=True, data_socket_closed=True),
        parent_closed=False,
    )


def test_reference_stop_survives_existing_failure_channel_without_owner_promotion():
    r = module("ivv_trusted_runner")
    obs = observation()
    error = r._carry_reference_observation(r.Refused("REFERENCE_INIT_OBSERVATION"), obs)
    packet = r._failed_packet(error)
    assert packet["op"] == "failed" and packet["reference_init_observation"] == obs
    received = r._child_failure(packet)
    record = r._failure_record(received)
    assert record == dict(
        state="STOP", reason="REFERENCE_INIT_OBSERVATION", reference_init_observation=obs
    )
    status = dict(
        record,
        stage="RELEASED_RECOVERY_ATTEMPT",
        unit_returncode=1,
        automatic_retry=False,
        provider_mutation=False,
        publication_sha256="b" * 64,
    )
    assert r.select_failure_status(status, "b" * 64)["reference_init_observation"] == obs
    packet["reference_init_observation"]["parent_closed"] = True
    with pytest.raises(r.Refused, match="REFERENCE_CHILD_OWNER"):
        r._child_failure(packet)


@pytest.mark.parametrize(
    "change",
    [
        {"owner_closed": True},
        {"constructor_status": "PRIVATE"},
        {"parent_closed": 1},
        {"normal_close": {"context_closed": True}},
    ],
)
def test_reference_stop_selector_is_closed(change):
    r = module("ivv_trusted_runner")
    with pytest.raises(r.Refused, match="REFERENCE_OBSERVATION"):
        r.select_reference_observation(dict(observation(), **change))


def reference_plan(helper, book, attempt):
    plan = old_plan(helper)
    plan.update(
        schema_id="qm.ivv.capture-plan" + helper.RECOVERY_SUFFIX,
        scope_id=helper.RECOVERY_SCOPE,
        approval_sha256=helper.RECOVERY_EFFECT,
        execution_sha256=helper.RECOVERY_AUTH,
        effect_id="ivv-trend-staged-20261029-capture",
        recovery=dict(connection_attempt_id=attempt),
        _recovery_ledger=book,
        _recovery_attempt=attempt,
        _live_verifier=lambda: None,
        _verified_binding=dict(
            actor=dict(pid=502, uid=0, start_ticks=22, cgroup="/fixture"),
            root_go_sha256="a" * 64,
            root_permit_sha256="b" * 64,
            plan_sha256="c" * 64,
        ),
        reference_init_ref=dict(path="/immutable/reference.json", sha256="d" * 64),
    )
    return plan


def test_reference_child_has_one_existing_may_and_no_capture_manifest(tmp_path):
    helper = module("capture_opend_ivv_daily")
    journal = tmp_path / "ledger"
    journal.mkdir()
    book = ledger(journal)
    clock = Clock()
    attempt = book.begin("a" * 64, now=clock.mono())
    plan = reference_plan(helper, book, attempt)
    observed = []

    class SDK:
        def __init__(self, observer, writer, plan, clock):
            self.o = observer
            self.o.backend = self
            self._bind_init = self._receive_trace = self._init_facts = None
            self.constructor_returned = False
            self.constructor_status = "NOT_RETURNED"

        def open(self):
            assert (journal / (attempt + ".may.json")).is_file()
            self.o.context_created()
            self.o.initializing()
            self.o.before_send(1001, 7)
            assert (journal / (attempt + "-request-000001.may.json")).is_file()
            observed.append(1001)
            self.constructor_returned = True
            self.constructor_status = "READY"

        def close(self):
            pass

        def close_evidence(self):
            return dict(context_closed=True, callbacks_stopped=True, data_socket_closed=True)

    result = helper._run_reference_init(
        plan,
        tmp_path / "reference",
        backend_factory=SDK,
        clock=clock,
        sync_dir=lambda _: None,
    )
    assert result["schema_id"] == "qm.ivv.reference-init-terminal.v2"
    assert result["state"] == "REFERENCE_READY_CLOSED"
    assert result["counts"] == dict(
        contexts=1, initializations=1, init_sends=1, keepalive_sends=0, business_sends=0
    )
    assert observed == [1001] and book.usage()["contexts"] == 1
    assert len(list(journal.glob("connection-*.intent.json"))) == 2  # context + request
    assert len(list(journal.glob("connection-*.may.json"))) == 2
    assert not list((tmp_path / "reference").glob("capture-*"))
    assert not (journal / (attempt + ".close.json")).exists()
    assert json.loads((tmp_path / "reference/reference-terminal.json").read_bytes()) == result


def test_reference_terminal_rejects_child_claim_of_owner_close():
    helper = module("capture_opend_ivv_daily")
    with pytest.raises(ValueError, match="reference_terminal"):
        helper._select_reference_terminal(dict(owner_closed=True, state="REFERENCE_READY_CLOSED"))


def official_reference(tmp_path, monkeypatch, case="normal"):
    import ast

    from test_ivv_init_observation import pinned_ast

    helper = module("capture_opend_ivv_daily")
    root = tmp_path / "ledger"
    root.mkdir()
    book = ledger(root)
    clock = Clock()
    attempt = book.begin("a" * 64, now=clock.mono())
    plan = reference_plan(helper, book, attempt)
    modules, transport = full_transport(case)
    base = modules[0].OpenQuoteContext.__mro__[1]
    original = next(
        n
        for n in pinned_ast("common/open_context_base.py").body
        if isinstance(n, ast.ClassDef) and n.name == "OpenContextBase"
    )
    env = base.__init__.__globals__
    for node in original.body:
        if isinstance(node, ast.FunctionDef) and node.name in {
            "_get_sync_query_processor",
            "on_tick",
            "_check_req_timeout",
        }:
            exec(
                compile(ast.Module(body=[node], type_ignores=[]), "open_context_base.py", "exec"),
                env,
            )
            setattr(base, node.name, env[node.name])
    connect = base._connect_sync

    def connected(ctx):
        transport.net.connect(("127.0.0.1", 11112))
        return connect(ctx)

    base._connect_sync = connected
    made = []

    def factory(o, w, p, c):
        backend = helper._ReferenceBackend(o, w, p, c, modules=modules)
        made.append(backend)
        opened = backend.open

        def open_and_tick():
            opened()
            backend.ctx.on_tick(23, 10)

        backend.open = open_and_tick
        return backend

    return NS(
        helper=helper,
        book=book,
        plan=plan,
        clock=clock,
        modules=modules,
        transport=transport,
        factory=factory,
        made=made,
        root=tmp_path / "reference",
    )


def test_actual_official_init_inherits_methods_and_suppresses_post_ready_tick(
    tmp_path, monkeypatch
):
    f = official_reference(tmp_path, monkeypatch)
    assert f.helper._ReferenceBackend._install_wire is f.helper._OfficialBackend._install_wire
    assert f.helper._ReferenceBackend.close is f.helper._OfficialBackend.close
    result = f.helper._run_reference_init(
        f.plan, f.root, backend_factory=f.factory, clock=f.clock, sync_dir=lambda _: None
    )
    assert result["state"] == "REFERENCE_READY_CLOSED"
    backend = f.made[0]
    for name in (
        "_query_sync",
        "_handle_init_connect_rsp",
        "_get_sync_query_processor",
        "on_recv",
        "_handle_recv",
        "on_tick",
    ):
        assert getattr(type(backend.ctx), name) is getattr(f.modules[0].OpenQuoteContext, name)
    assert backend._bind_init is backend._receive_trace is backend._init_facts is None
    assert f.transport.writes == 1 and f.book.usage()["init_connect"] == 1
    assert f.book.usage()["keepalive"] == f.book.usage()["business_requests"] == 0
    assert all(result["normal_close"].values())


def connected_reference(tmp_path, monkeypatch):
    from test_ivv_recovery_capture import connected_recovery_capture

    def entry(helper, issuer, runner, state, final, profile, snapshot, root):
        modules, transport = full_transport("normal")
        backend = helper._ReferenceBackend
        return lambda o, w, p, c: backend(o, w, p, c, modules=modules)

    return connected_recovery_capture(tmp_path, monkeypatch, reference=True, entry_hook=entry)


def test_reference_uses_actual_held_permit_entry_without_capture_seal(tmp_path, monkeypatch):
    f = connected_reference(tmp_path, monkeypatch)
    assert not (f["root"] / "capture-manifest.json").exists()
    assert not (tmp_path / "parent-close.json").exists()
    assert len(list(f["book"].root.glob("connection-*.intent.json"))) == 2
    assert len(list(f["book"].root.glob("connection-*.may.json"))) == 2


def test_old_capture_entry_cannot_consume_reference_plan(tmp_path, monkeypatch):
    from test_ivv_recovery_capture import connected_recovery_capture

    def entry(helper, issuer, runner, state, final, profile, snapshot, root):
        def forbidden(*a, **kw):
            pytest.fail("reference selection reached ordinary capture")

        helper._run_capture = forbidden
        return forbidden

    # Existing helper API must reject this choice before it reserves MAY or calls the backend.
    with pytest.raises(ValueError, match="reference_entry_required"):
        connected_recovery_capture(
            tmp_path, monkeypatch, reference=True, entry_hook=entry, fault="reference_via_capture"
        )


@pytest.mark.parametrize(
    "fault", ["non1001", "duplicate", "foreign", "second_connect", "live", "observer"]
)
def test_reference_original_wire_refusal_never_becomes_false_ready(tmp_path, monkeypatch, fault):
    import struct

    f = official_reference(tmp_path, monkeypatch)
    base = f.modules[0].OpenQuoteContext
    original = base.__init__

    def initialized(ctx, **kw):
        original(ctx, **kw)
        raw = (
            struct.pack(
                f.modules[1].MESSAGE_HEAD_FMT,
                b"F",
                b"T",
                1004 if fault == "non1001" else 1001,
                0,
                0,
                9,
                1,
                b"\0" * 20,
                b"\0" * 8,
            )
            + b"Q"
        )
        try:
            if fault == "live":
                f.plan["_live_verifier"] = lambda: f.helper._require(False, "held_permit_replaced")
                ctx._net_mgr.send(ctx._conn_id, raw)
            elif fault == "observer":
                f.made[0]._init_facts = {}
                ctx.keep_alive()
            elif fault == "second_connect":
                ctx._net_mgr.connect(("127.0.0.1", 11112))
            else:
                ctx._net_mgr.send(999 if fault == "foreign" else ctx._conn_id, raw)
        except Exception:
            pass  # Model the official ordinary-error catch before a later READY assignment.
        ctx._status = f.modules[2].ContextStatus.READY

    base.__init__ = initialized
    result = f.helper._run_reference_init(
        f.plan, f.root, backend_factory=f.factory, clock=f.clock, sync_dir=lambda _: None
    )
    assert result["state"] == "REFERENCE_FAILED"
    assert f.transport.writes == 1
    assert result["constructor_returned"] is True
    assert result["constructor_status"] == "READY"
    assert f.book.usage()["init_connect"] == 1 and f.book.usage()["keepalive"] == 0
    assert not (f.book.root / "connection-000002.intent.json").exists()


@pytest.mark.parametrize("case", ["timeout", "send_raise"])
def test_reference_not_ready_is_closed_and_finite(tmp_path, monkeypatch, case):
    f = official_reference(tmp_path, monkeypatch, case)
    result = f.helper._run_reference_init(
        f.plan, f.root, backend_factory=f.factory, clock=f.clock, sync_dir=lambda _: None
    )
    assert result["state"] == "REFERENCE_FAILED"
    assert result["primary_failure"]["code"] == "sdk_initial_connection_failed"
    assert all(result["normal_close"].values())
