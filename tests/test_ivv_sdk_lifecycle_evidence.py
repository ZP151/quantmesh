"""Real recovery entry/guards/lifecycle; authored SDK/kernel/provider seams only."""

import importlib.machinery
import json
import os
import stat
import struct
from types import SimpleNamespace

import pytest
import test_ivv_executable_identity as identity
from test_ivv_recovery_capture import connected_recovery_capture, module


def test_actual_context_guard_chain_reaches_constructor(tmp_path, monkeypatch):
    events = []
    finder = importlib.machinery.PathFinder.find_spec
    with monkeypatch.context() as runtime_patch:
        runtime, _, _, runtime_plan, runtime_catalog = identity.environment(runtime_patch)
        runtime_patch.setattr(
            importlib.machinery.PathFinder,
            "find_spec",
            lambda name, *a, **kw: (
                SimpleNamespace(origin="/opt/sdk/moomoo/__init__.py")
                if name == "moomoo"
                else finder(name, *a, **kw)
            ),
        )
        initial = runtime._runtime(
            runtime_plan,
            None,
            44,
            runtime_catalog,
            None,
            additional=identity.MODE,
            origin_phase="INITIAL",
        )["executable_origin"]

        def entry(m, issuer, runner, state, final, profile, snapshot, root):
            state.capture_classifier = lambda error: runner.classify_capture_exception(
                error, m.CaptureRejected
            )
            # Restore actual issuer reader replaced only by the generic kernel fixture.
            monkeypatch.setattr(
                issuer, "_read_native_provider", module("ivv_dev_diagnostic")._read_native_provider
            )
            state.plan = m._canonical(
                {
                    k: v
                    for k, v in final.items()
                    if not k.startswith("_") and k != "provider_evidence_ref"
                }
            )
            state.evidence = m._canonical(
                json.loads(
                    __import__("pathlib").Path(final["provider_evidence_ref"]["path"]).read_bytes()
                )
            )
            parent = os.getpid() + 1
            packets = []

            class Sock:
                type = 5

                def fileno(self):
                    return 991

                def setsockopt(self, *a):
                    pass

                def settimeout(self, v):
                    pass

                def send(self, raw):
                    item = json.loads(raw)
                    assert set(item) == {"op", "executable_origin"} and item["op"] == "observe"
                    runner._accept_executable_origin(
                        item["executable_origin"],
                        {"catalog_ref": runtime_catalog},
                        phase="SESSION",
                        namespace=44,
                    )
                    events.append("AUTHENTICATED_OBSERVE")
                    packets.append(m._canonical({"snapshot": snapshot}))
                    return len(raw)

                def recvmsg(self, *a):
                    return packets.pop(0), [(1, 2, struct.pack("3i", parent, 0, 0))], 0, None

            monkeypatch.setattr(
                runner,
                "socket",
                SimpleNamespace(
                    SOL_SOCKET=1,
                    SO_PASSCRED=3,
                    SOCK_SEQPACKET=5,
                    SCM_CREDENTIALS=2,
                    CMSG_SPACE=lambda n: n,
                ),
            )

            class Kernel:
                def __getattr__(self, name):
                    return getattr(os, name)

                def fstat(self, fd):
                    return (
                        SimpleNamespace(st_dev=1, st_ino=991, st_uid=0, st_mode=stat.S_IFSOCK)
                        if fd == 991
                        else os.fstat(fd)
                    )

            monkeypatch.setattr(runner, "os", Kernel())

            def checked():
                return runtime._runtime(
                    runtime_plan,
                    None,
                    44,
                    runtime_catalog,
                    None,
                    additional=identity.MODE,
                    origin_phase="SESSION",
                )

            state.session = runner._ChildSession(runner._Channel(Sock()), parent, checked)
            from test_ivv_capture_contract import ScriptedBackend

            class SDKContext:
                def __init__(ctx, **kwargs):
                    events.append("CONSTRUCTOR")
                    assert events[-2] == "AUTHENTICATED_OBSERVE"
                    ctx.status = "READY"
                    ctx._conn_id = 1
                    ctx._callback_executor = SimpleNamespace(
                        _thread=SimpleNamespace(join=lambda **kw: None, is_alive=lambda: False)
                    )
                    ctx._net_mgr = SimpleNamespace(
                        send=lambda *a: None, connect=lambda *a: None, _get_conn=lambda conn: None
                    )
                    ctx._init_connect_sync()

                def _init_connect_sync(ctx):
                    return None

                def set_sync_query_connect_timeout(ctx, n):
                    assert n == 5

                def close(ctx):
                    ctx.status = "CLOSED"

            sdk = SimpleNamespace(
                OpenQuoteContext=SDKContext,
                SecurityFirm=SimpleNamespace(
                    NONE="N/A", FUTUSG="FUTUSG", FUTUINC="FUTUINC", FUTUSECURITIES="FUTUSECURITIES"
                ),
            )
            original = m._OfficialBackend

            class Backend(original):
                def __init__(self, o, w, p, c):
                    super().__init__(
                        o,
                        w,
                        p,
                        c,
                        modules=(
                            sdk,
                            SimpleNamespace(),
                            SimpleNamespace(
                                ContextStatus=SimpleNamespace(READY="READY", CLOSED="CLOSED")
                            ),
                        ),
                    )
                    self.script = ScriptedBackend(m, o, w, c, root)

                def open(self):
                    super().open()
                    self.o.before_send(1001, 1)

                def invoke(self, tag, params):
                    return self.script.invoke(tag, params)

            return Backend

        result = connected_recovery_capture(
            tmp_path,
            monkeypatch,
            kernel_extra={
                "executable_origin": {
                    "initial": initial,
                    "last": {**initial, "phase": "SESSION"},
                    "checks": 2,
                }
            },
            entry_hook=entry,
        )
    assert events.count("CONSTRUCTOR") == 1 and events.count("AUTHENTICATED_OBSERVE") > 2
    manifest = json.loads((result["root"] / "capture-manifest.json").read_bytes())
    assert manifest["state"] == "CAPTURED_UNREVIEWED" and "capture_lifecycle" not in manifest


def test_actual_preallocation_guard_failure_keeps_primary_and_close(tmp_path, monkeypatch):
    from pathlib import Path

    events = []

    def entry(m, issuer, runner, state, final, profile, snapshot, root):
        state.capture_classifier = lambda error: runner.classify_capture_exception(
            error, m.CaptureRejected
        )
        original = m._OfficialBackend
        read = Path.read_text
        active = [False]

        def kernel_read(path, *args, **kwargs):
            if active[0] and path.name == "memory.max":
                raise PermissionError(13, "PRIVATE_NATIVE_PATH")
            return read(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", kernel_read)

        class SDK:
            def __init__(self, **kw):
                events.append("CONSTRUCTOR")

        class Backend(original):
            def __init__(self, o, w, p, c):
                super().__init__(
                    o, w, p, c, modules=(SimpleNamespace(OpenQuoteContext=SDK), None, None)
                )

            def open(self):
                active[0] = True
                return super().open()

        return Backend

    value = connected_recovery_capture(
        tmp_path, monkeypatch, entry_hook=entry, capture_failure=True
    )
    result = value["result"]
    assert not events
    assert result["counts"]["contexts"] == 1 and result["counts"]["initializations"] == 0
    life = result["capture_lifecycle"]
    assert (
        life["primary"]["phase"] == "CONTEXT_RESERVE_GUARD" and life["primary"]["guard"] == "CGROUP"
    )
    assert life["primary"]["type"] == "PermissionError" and life["primary"]["errno"] == 13
    assert life["close"]["phase"] == "EVIDENCE" and life["evidence_kind"] == "DEFAULT"
    assert life["ctx_assigned"] is False and life["constructor_returned"] is False
    assert result["primary_failure"]["stage"] == "initialize"
    assert result["close_failure"]["code"] == "normal_close_not_proven"
    assert "PRIVATE" not in json.dumps(life)
    # Feed this actual failed manifest through the production mapping, then the
    # existing credentialed channel/supervisor/aggregation/main/strict-reader path.
    import test_ivv_runtime_failure_evidence as chain

    runner = value["runner"]
    with pytest.raises(runner.Refused) as caught:
        runner._check_capture_result(result, recovery=True)
    selected = chain.test_real_child_ipc_parent_wrap_main_reader_selector(
        monkeypatch, "pidfd", (runner, caught.value, None)
    )
    assert selected["capture_lifecycle"] == life and selected["actual_contexts"] == "UNKNOWN"


def test_owned_classifier_and_closed_codec_never_retain_exception_text():
    r = module("ivv_trusted_runner")
    m = module("capture_opend_ivv_daily")

    class Hostile(PermissionError):
        def __getattribute__(self, key):
            raise AssertionError("hook")

        def __str__(self):
            raise AssertionError("string")

    for error in (
        Hostile(13, "PRIVATE"),
        ValueError("PRIVATE"),
        m.CaptureRejected("private_safe_ascii"),
        r.Refused("private_safe_ascii"),
    ):
        item = r.classify_capture_exception(error, m.CaptureRejected)
        assert item["code"] == "UNKNOWN" and "PRIVATE" not in json.dumps(item)
    assert (
        r.classify_capture_exception(r.Refused("RUNTIME_ORIGIN"), m.CaptureRejected)["code"]
        == "RUNTIME_ORIGIN"
    )
    assert (
        r.classify_capture_exception(PermissionError(True, "PRIVATE"), m.CaptureRejected)["errno"]
        is None
    )
    trace = m._CaptureLifecycle(lambda e: r.classify_capture_exception(e, m.CaptureRejected))
    trace.failed("primary", PermissionError(13, "PRIVATE"))
    value = r.select_capture_lifecycle(trace.value)
    for key, bad in [
        ("errno", True),
        ("errno", float("nan")),
        ("code", "private_safe_ascii"),
        ("phase", "PRIVATE"),
    ]:
        corrupt = {**value, "primary": {**value["primary"], key: bad}}
        with pytest.raises(ValueError):
            r.select_capture_lifecycle(corrupt)
    with pytest.raises(ValueError):
        r.select_capture_lifecycle({**value, "secret": "PRIVATE"})
    assert r._failure_record(r.Refused("OLD")) == {"state": "STOP", "reason": "OLD"}


@pytest.mark.parametrize(
    "fault,phase,assigned,returned",
    [
        ("base", "BASE_LOOKUP", False, False),
        ("allocate", "ALLOCATE", False, False),
        ("arguments", "CTOR_ARGUMENTS", True, False),
        ("constructor", "CONSTRUCTOR", True, False),
        ("init", "INIT_CONNECT", True, False),
        ("ready", "READY_CHECK", True, True),
    ],
)
def test_actual_backend_open_failure_boundaries(fault, phase, assigned, returned):
    r = module("ivv_trusted_runner")
    m = module("capture_opend_ivv_daily")
    calls = []

    class Context:
        def __new__(cls):
            if fault == "allocate":
                raise TypeError("PRIVATE")
            return object.__new__(cls)

        def __init__(self, **kw):
            calls.append("constructor")
            if fault == "constructor":
                raise RuntimeError("PRIVATE")
            self._net_mgr = SimpleNamespace(send=lambda: None, connect=lambda: None)
            self._init_connect_sync()
            self.status = "BAD" if fault == "ready" else "READY"

        def _init_connect_sync(self):
            if fault == "init":
                raise OSError(5, "PRIVATE")

        def set_sync_query_connect_timeout(self, n):
            pass

    sdk = SimpleNamespace(
        SecurityFirm=SimpleNamespace() if fault == "arguments" else SimpleNamespace(NONE="N/A")
    )
    if fault != "base":
        sdk.OpenQuoteContext = Context
    plan = {"endpoint": {"is_encrypt": False, "security_firm": "NONE"}}
    trace = m._CaptureLifecycle(lambda e: r.classify_capture_exception(e, m.CaptureRejected))
    plan["_capture_lifecycle"] = trace
    o = SimpleNamespace(
        context_created=lambda: calls.append("context"), initializing=lambda: calls.append("init")
    )
    backend = m._OfficialBackend(
        o,
        None,
        plan,
        None,
        modules=(sdk, None, SimpleNamespace(ContextStatus=SimpleNamespace(READY="READY"))),
    )
    with pytest.raises(BaseException) as caught:
        backend.open()
    trace.failed("primary", caught.value)
    assert trace.value["primary"]["phase"] == phase
    assert (
        trace.value["ctx_assigned"] == assigned and trace.value["constructor_returned"] == returned
    )
    assert calls.count("context") == 1 and calls.count("constructor") <= 1
    assert "PRIVATE" not in json.dumps(r.select_capture_lifecycle(trace.value))


@pytest.mark.parametrize(
    "fault,phase,observed",
    [
        ("close", "SDK_CLOSE", False),
        ("status", "STATUS_WAIT", False),
        ("callback", "CALLBACK_JOIN", False),
        ("connection", "CONNECTION_CHECK", False),
        ("log", "LOG_CLOSE", True),
        ("async", None, True),
    ],
)
def test_actual_close_owns_only_context_and_preserves_finally(fault, phase, observed):
    r = module("ivv_trusted_runner")
    m = module("capture_opend_ivv_daily")
    events = []
    now = [0]
    trace = m._CaptureLifecycle(lambda e: r.classify_capture_exception(e, m.CaptureRejected))
    plan = {"_capture_lifecycle": trace, "started_monotonic": 0}

    def fail(where):
        events.append(where)
        if fault == where:
            raise OSError(5, "PRIVATE")

    class Context:
        _conn_id = 1
        _callback_executor = SimpleNamespace(
            _thread=SimpleNamespace(join=lambda **kw: fail("callback"), is_alive=lambda: False)
        )

        def close(self):
            fail("close")

        @property
        def status(self):
            fail("status")
            return "CLOSED" if now[0] > 0 else "CLOSING"

    net = SimpleNamespace(
        send="current", connect="current", _get_conn=lambda conn: (fail("connection"), None)[1]
    )
    backend = m._OfficialBackend(
        None,
        None,
        plan,
        SimpleNamespace(mono=lambda: now[0], sleep=lambda n: now.__setitem__(0, now[0] + n)),
        modules=(None, None, SimpleNamespace(ContextStatus=SimpleNamespace(CLOSED="CLOSED"))),
    )
    backend.ctx = Context()
    backend._net = net
    backend._old_send = "old_send"
    backend._old_connect = "old_connect"
    backend.sink = SimpleNamespace(close=lambda: fail("log"))
    if fault == "async":
        backend.close()
    else:
        with pytest.raises(OSError) as caught:
            backend.close()
        trace.failed("close", caught.value)
        assert trace.value["close"]["phase"] == phase
    assert trace.value["evidence_kind"] == ("OBSERVED" if observed else "DEFAULT")
    assert net.send == "old_send" and net.connect == "old_connect" and "log" in events
    assert not hasattr(net, "close")  # Shared manager has no context-owned shutdown call.
    assert "PRIVATE" not in json.dumps(r.select_capture_lifecycle(trace.value))


@pytest.mark.parametrize(
    "code",
    [
        "SDK_PIN_DRIFT",
        "PYTHON_SEARCH_PATH",
        "PYTHON_EXECUTABLE",
        "HOME_LOG_PREREQUISITE",
        "OWN_NAMESPACE_DRIFT",
        "CONTROL_EOF",
        "CONTROL_FD_SWAPPED",
        "CONTROL_SENDER",
        "SESSION_OWNER",
        "CONTROL_DIGEST",
    ],
)
def test_actual_owning_runtime_and_channel_codes_are_finite(code):
    r = module("ivv_trusted_runner")
    m = module("capture_opend_ivv_daily")
    assert r.classify_capture_exception(r.Refused(code), m.CaptureRejected)["code"] == code
    assert (
        r.classify_capture_exception(m.CaptureRejected(code), m.CaptureRejected)["code"]
        == "UNKNOWN"
    )
    assert (
        r.classify_capture_exception(r.Refused("PRIVATE_UPPERCASE"), m.CaptureRejected)["code"]
        == "UNKNOWN"
    )


def test_optional_corrupt_lifecycle_cannot_replace_primary_exception():
    r = module("ivv_trusted_runner")
    error = r.Refused("SDK_CLOSE_UNKNOWN")
    assert r._carry_capture_lifecycle(error, {"secret": "PRIVATE"}) is error
    assert r._failure_record(error) == {"state": "STOP", "reason": "SDK_CLOSE_UNKNOWN"}


def test_actual_result_mapping_to_authenticated_failure_chain(monkeypatch):
    import test_ivv_runtime_failure_evidence as chain

    r = module("ivv_trusted_runner")
    m = module("capture_opend_ivv_daily")
    trace = m._CaptureLifecycle(lambda e: r.classify_capture_exception(e, m.CaptureRejected))
    trace.phase = "CONTEXT_RESERVE_GUARD"
    trace.guard = "PROVIDER_SESSION"
    trace.failed("primary", r.Refused("SDK_PIN_DRIFT"))
    trace.phase = "EVIDENCE"
    trace.guard = "NOT_APPLICABLE"
    trace.failed("close", m.CaptureRejected("normal_close_not_proven"))
    result = {
        "state": "FAILED_CAPTURE_REQUIRES_PARENT_SEAL",
        "primary_failure": {"code": "exception"},
        "close_failure": {"code": "normal_close_not_proven"},
        "capture_lifecycle": trace.value,
    }
    with pytest.raises(r.Refused, match="^SDK_CLOSE_UNKNOWN$") as caught:
        r._check_capture_result(result, recovery=True)
    selected = chain.test_real_child_ipc_parent_wrap_main_reader_selector(
        monkeypatch, "pidfd", (r, caught.value, None)
    )
    assert selected["capture_lifecycle"] == trace.value and selected["actual_contexts"] == "UNKNOWN"
    assert selected["reason"] == "SDK_CLOSE_UNKNOWN+CLEANUP_UNKNOWN"


@pytest.mark.parametrize("replacement", [None, {"secret": "PRIVATE"}])
def test_reused_exception_does_not_retain_old_lifecycle(replacement):
    r = module("ivv_trusted_runner")
    m = module("capture_opend_ivv_daily")
    trace = m._CaptureLifecycle(lambda e: r.classify_capture_exception(e, m.CaptureRejected))
    error = r.Refused("SDK_CLOSE_UNKNOWN")
    r._carry_capture_lifecycle(error, trace.value)
    assert "capture_lifecycle" in r._failure_record(error)
    assert r._carry_capture_lifecycle(error, replacement) is error
    assert r._failure_record(error) == dict(state="STOP", reason="SDK_CLOSE_UNKNOWN")


@pytest.mark.parametrize(
    "kind,number",
    [
        (BrokenPipeError, 32),
        (ConnectionResetError, 104),
        (ConnectionAbortedError, 103),
        (ConnectionRefusedError, 111),
        (BlockingIOError, 11),
        (InterruptedError, 4),
    ],
)
def test_exact_builtin_channel_errors_preserve_finite_type_and_errno(kind, number):
    r = module("ivv_trusted_runner")
    m = module("capture_opend_ivv_daily")
    actual = r.classify_capture_exception(kind(number, "PRIVATE"), m.CaptureRejected)
    assert actual == dict(type=kind.__name__, errno=number, code="UNKNOWN")
    assert (
        r.classify_capture_exception(AssertionError("PRIVATE"), m.CaptureRejected)["type"]
        == "AssertionError"
    )


@pytest.mark.parametrize("failed", [False, True])
def test_guard_attribution_ends_only_after_successful_actual_observer_check(failed):
    r = module("ivv_trusted_runner")
    m = module("capture_opend_ivv_daily")
    trace = m._CaptureLifecycle(lambda e: r.classify_capture_exception(e, m.CaptureRejected))
    trace.phase = "INIT_CONNECT"

    def verifier():
        trace.guard = "PROVIDER_SESSION"
        if failed:
            raise r.Refused("CONTROL_EOF")

    observer = m._CaptureObserver.__new__(m._CaptureObserver)
    observer.plan = {
        "_capture_lifecycle": trace,
        "_live_verifier": verifier,
        "started_monotonic": 0,
    }
    observer.poison = None
    observer.clock = SimpleNamespace(mono=lambda: 1)
    if failed:
        with pytest.raises(r.Refused) as caught:
            observer.check()
        trace.failed("primary", caught.value)
        assert trace.value["primary"]["guard"] == "PROVIDER_SESSION"
    else:
        observer.check()
        trace.failed("primary", BrokenPipeError(32, "PRIVATE"))
        assert trace.value["primary"]["guard"] == "NOT_APPLICABLE"
    assert trace.value["primary"]["phase"] == "INIT_CONNECT"


@pytest.mark.parametrize(
    "owner,code", [("runner", "CHILD_WRITE_MOUNTS"), ("helper", "second_initialization")]
)
def test_direct_owned_guard_rejections_have_finite_codes(owner, code):
    r = module("ivv_trusted_runner")
    m = module("capture_opend_ivv_daily")
    error = (r.Refused if owner == "runner" else m.CaptureRejected)(code)
    assert r.classify_capture_exception(error, m.CaptureRejected)["code"] == code


def test_strict_lifecycle_rejects_inconsistent_type_code_and_errno():
    r = module("ivv_trusted_runner")
    m = module("capture_opend_ivv_daily")
    trace = m._CaptureLifecycle(lambda e: r.classify_capture_exception(e, m.CaptureRejected))
    trace.failed("primary", ValueError("PRIVATE"))
    for patch in ({"code": "SDK_PIN_DRIFT"}, {"errno": 13}):
        bad = {**trace.value, "primary": {**trace.value["primary"], **patch}}
        with pytest.raises(ValueError):
            r.select_capture_lifecycle(bad)
