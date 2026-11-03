"""Constructed software evidence for the original trusted-environment family."""

import contextlib
import hashlib
import json
import os
import stat
from pathlib import Path, PurePosixPath
from types import SimpleNamespace

import pytest
from test_ivv_capture_contract import DATES, Clock, ScriptedBackend, leaf
from test_ivv_dev_diagnostic import dev_module, dev_plan, policy

FAMILY = ".dev-trusted-environment.v1"
AUTH = "3fede456cf8fff2e4ee29748fa6037617fe250d382c8b09474e1f6be4fe7e452"
ASSURANCE = "UNVERIFIED_TRUSTED_EXTERNAL"


def _kernel_path_arguments(args, aliases, path_type):
    """Preserve known physical fixture paths before projecting logical prefixes."""
    if not args:
        return args
    value = os.fspath(args[0]).replace("\\", "/")
    candidate = path_type(value)
    if any(candidate == actual or candidate.is_relative_to(actual) for _, actual in aliases):
        return args
    for logical, actual in aliases:
        if value == logical or value.startswith(logical + "/"):
            return (actual / value[len(logical) :].lstrip("/"), *args[1:])
    return args


@pytest.mark.parametrize("prefix", ["/tmp/fixture", "/home/runner/work/_temp/fixture"])
@pytest.mark.parametrize(
    "logical", ["/child", "/sdk", "/home", "/once", "/usr", "/source", "/controls"]
)
@pytest.mark.parametrize("physical", [False, True])
def test_connected_kernel_path_arguments_preserve_physical_and_project_logical(
    prefix, logical, physical
):
    root = PurePosixPath(prefix)
    aliases = [
        (name, root / name.lstrip("/"))
        for name in ("/child", "/sdk", "/home", "/once", "/usr", "/source", "/controls")
    ]
    actual = dict(aliases)[logical]
    value = str(actual) if physical else logical
    projected = _kernel_path_arguments((value, "nested", "file"), aliases, PurePosixPath)
    assert PurePosixPath(*projected) == actual / "nested/file"


@pytest.mark.parametrize("value", ["/homey/file", "/source-other/file", "relative/file"])
def test_connected_kernel_path_arguments_do_not_match_similar_logical_prefixes(value):
    root = PurePosixPath("/home/runner/work/_temp/fixture")
    aliases = [("/home", root / "home"), ("/source", root / "source")]
    assert _kernel_path_arguments((value,), aliases, PurePosixPath) == (value,)


def test_connected_kernel_path_arguments_do_not_whitelist_a_physical_sibling():
    root = PurePosixPath("/home/runner/work/_temp/fixture")
    aliases = [("/home", root / "home"), ("/controls", root)]
    value = "/home/runner/work/_temp/fixture-sibling/file"
    projected = _kernel_path_arguments((value,), aliases, PurePosixPath)
    assert PurePosixPath(*projected) == root / "home/runner/work/_temp/fixture-sibling/file"
    assert PurePosixPath(*projected) != PurePosixPath(value)


def trusted_plan(m):
    plan = dev_plan(m)
    plan["schema_id"] = "qm.ivv.capture-plan" + FAMILY
    plan["_verified_binding"].update(
        authorization_sha256=AUTH,
        diagnostic_mode="DEV_TRUSTED_ENVIRONMENT",
        channel_assurance=ASSURANCE,
    )
    return plan


def test_trusted_capture_binds_human_exception_through_seven_sends(tmp_path):
    m = leaf()
    root = tmp_path / "capture"
    result = m._run_capture(
        trusted_plan(m),
        root,
        dates=DATES,
        synthetic=True,
        sync_dir=lambda path: None,
        clock=Clock(),
        backend_factory=lambda o, w, p, c: ScriptedBackend(m, o, w, c, root),
    )
    assert result["state"] == "CAPTURED_UNREVIEWED"
    assert result["counts"]["application_sends"] == 7
    for kind, obj in (
        ("capture", result),
        ("capture-intent", json.loads((root / "capture-intent.json").read_bytes())),
    ):
        assert obj["schema_id"] == "qm.ivv." + kind + FAMILY
        assert obj["authorization_sha256"] == AUTH
        assert obj["channel_assurance"] == ASSURANCE
        assert obj["provider_tail_max"] == "UNKNOWN"
        assert obj["hard_limit_enforced"] is False


def test_trusted_policy_cannot_be_read_as_old_a():
    m, d = leaf(), dev_module()
    plan = trusted_plan(m)
    material = policy(m)
    material.update(
        schema_id="qm.ivv.capture-policy" + FAMILY,
        diagnostic_mode="DEV_TRUSTED_ENVIRONMENT",
        authorization_sha256=AUTH,
        channel_assurance=ASSURANCE,
    )
    material["exceptions"].append("external_provider_terminal_ipc_socket_environment")
    d.validate_trusted_policy(m, material, plan, AUTH)
    with pytest.raises(ValueError):
        d.validate_policy(m, material, plan, AUTH)
    for key, value in (("channel_assurance", "VERIFIED"), ("authorization_sha256", "2" * 64)):
        with pytest.raises(ValueError):
            d.validate_trusted_policy(m, {**material, key: value}, plan, AUTH)


def test_consumer_requires_external_family_on_each_binding():
    from types import SimpleNamespace

    from quantmesh.research import ivv_admission as v

    proofs = SimpleNamespace(
        capture_policy_ref=object(),
        authorization_ref=object(),
        expected_policy_sha256="1" * 64,
        expected_authorization_sha256=AUTH,
    )
    for kind in ("root-go", "capture-parent-close", "input-acceptance", "registration"):
        assert v._schema(proofs, kind) == "qm.ivv." + kind + FAMILY
    binding = trusted_plan(leaf())["_verified_binding"]
    assert v._dev_binding(proofs, binding)["channel_assurance"] == ASSURANCE
    with pytest.raises(ValueError):
        v._dev_binding(proofs, {**binding, "channel_assurance": "VERIFIED"})


def runner():
    import importlib.util
    from pathlib import Path

    p = Path(__file__).resolve().parents[1] / "tools" / "research" / "ivv_trusted_runner.py"
    assert p.exists(), "owned runner missing"
    spec = importlib.util.spec_from_file_location("qm_trusted_test", p)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def test_root_refuses_unowned_signal_or_cgroup_targets():
    import inspect

    r = runner()
    assert list(inspect.signature(r.run_once).parameters) == ["startup_ref"]
    with pytest.raises((ValueError, RuntimeError)):
        r.run_once({"pid": 1, "cgroup": "/", "control_fd": 1})


def test_shared_legacy_entry_cannot_consume_new_permit():
    d, m = dev_module(), leaf()
    m._read_held_json = lambda fd, sha: {"schema_id": "qm.ivv.root-permit" + FAMILY}
    with pytest.raises(m.CaptureRejected, match="dev_permit_schema"):
        d.admit_dev(
            m,
            "plan",
            "root",
            3,
            "a" * 64,
            expected_policy_sha256="b" * 64,
            expected_authorization_sha256=AUTH,
            expected_go_sha256="d" * 64,
        )


def test_projected_quote_configuration_never_reads_live_xml(monkeypatch):
    from test_ivv_dev_native import native_module

    n = native_module()
    opened = []

    def guarded(path, maximum):
        opened.append(path)
        assert not path.endswith(".xml")
        raise OSError("fixture has no protected public inputs")

    monkeypatch.setattr(n, "_protected_bytes", guarded)
    monkeypatch.setattr(n.sys, "platform", "linux")
    monkeypatch.setattr(n.os, "getuid", lambda: 0, raising=False)
    monkeypatch.setattr(n.os, "geteuid", lambda: 0, raising=False)
    with pytest.raises(OSError):
        n.trusted_quote_configuration({})
    assert opened == ["/opt/quantmesh/opend/validate_profile.py"]


def test_cleanup_never_kills_unbound_processes_in_owned_leaf(monkeypatch):
    """A foreign process grafted into our leaf is uncertainty, not kill authority."""

    r = runner()
    scope = r._Scope.__new__(r._Scope)
    scope.pid, scope.reaped, scope.leaf, scope.moved = 123, True, 40, True
    scope.pop = 41
    scope.check_leaf = lambda: None
    scope.remove = lambda: r.need(False, "CGROUP_NOT_EMPTY")
    writes = []
    scope.write = lambda name, value: writes.append((name, value))
    monkeypatch.setattr(r, "_events", lambda fd: {"populated": 1})
    failures = scope.abort()
    assert writes == [], "unbound process must never receive cgroup.kill"
    assert failures == ["CGROUP_NOT_EMPTY"]


def test_ready_gate_runtime_cannot_omit_installed_sdk_search_origin(monkeypatch):
    """The runner must admit the SDK path before runtime validation/import."""

    r = runner()
    m = leaf()
    m._native_actor = lambda: {"pid": 123}
    m._admit_material = lambda *args: (None, None, None)
    context = ({}, {"catalog_ref": {}, "budget_ref": {}}, None, m, None, None)
    observed = []

    class Channel:
        def recv(self, pid):
            return {"op": "enter"}

        def send(self, packet):
            observed.append(packet)
            raise r.Refused("STOP_AT_READY")

    monkeypatch.setattr(r, "_child_namespace", lambda *a: 44)
    monkeypatch.setattr(r, "_environment", lambda: None)
    monkeypatch.setattr(r, "_bind_parent", lambda *a: None)
    monkeypatch.setattr(
        r, "_runtime", lambda *a: r.need(str(r.SDK) in r.sys.path, "SDK_SEARCH_MISSING")
    )
    with pytest.raises(r.Refused, match="STOP_AT_READY"):
        r._child(Channel(), 1, context, {})
    assert observed == [{"op": "ready"}]


@pytest.mark.parametrize("pidfd_first", [False, True])
def test_connected_trusted_issuer_capture_parent_consumer_cold(tmp_path, monkeypatch, pidfd_first):
    _connected_capture(tmp_path, monkeypatch, pidfd_first, None)


def connected_additional_capture(tmp_path, monkeypatch, *, private=True, fault=None):
    from test_ivv_additional_task import additional

    return _connected_capture(
        tmp_path, monkeypatch, False, additional(), private=private, fault=fault
    )


def _connected_capture(tmp_path, monkeypatch, pidfd_first, extra, *, private=False, fault=None):
    """Real immutable bytes cross every policy/permit/capture/seal/import boundary.

    Only Linux metadata/IPC/provider observations and the SDK are modeled. This
    is software integration evidence, never native qualification or input review.
    """
    from test_ivv_dev_diagnostic import (
        _consume_real_capture_artifacts,
        _registration_authorities,
        kernel_fixture,
    )

    from quantmesh.research import ivv_admission as v

    if extra:
        from test_ivv_additional_task import private_inputs, window_controls

        from quantmesh.research import native_daily_candidate
        from quantmesh.research import native_daily_real as daily

        if private:
            private_inputs()
        controls = window_controls(private)
        registration = {
            "go_fields": {
                "code": native_daily_candidate._code(),
                "adapter_sha256": "a" * 64,
                "gate_sha256": "b" * 64,
                "output_root_digest": daily._root_pin(tmp_path / "study"),
                "runtime": daily.runtime_versions(),
            }
        }
        d, m, old_ref, root, kwargs, snapshot = kernel_fixture(
            tmp_path, monkeypatch, additional_controls=controls
        )
    else:
        registration = _registration_authorities(tmp_path, monkeypatch)
        d, m, old_ref, root, kwargs, snapshot = kernel_fixture(
            tmp_path, monkeypatch, registration=registration
        )
    r = runner()
    child_root = tmp_path / "child"
    child_root.mkdir()
    root = child_root / "capture"
    auth = kwargs["expected_authorization_sha256"]  # fictional authority, never actual once
    if extra:
        if private:
            approval, descriptor, policy_bytes, windows = private_inputs()
            extra.authenticate(approval, descriptor, policy_bytes, windows)
        additional_ledger = tmp_path / "additional-once"
        additional_ledger.mkdir()
        monkeypatch.setattr(extra, "_remote_ledger", lambda: additional_ledger)
        if fault == "context_fsync":

            def uncertain(path):
                raise OSError("directory flush uncertain")

            monkeypatch.setattr(extra, "_sync_directory", uncertain)
        else:
            monkeypatch.setattr(extra, "_sync_directory", m._sync_dir)

        assert hasattr(r, "run_additional_once"), "additional normal parent entry missing"
    else:
        for owner, name in ((r, "AUTH"), (m, "TRUSTED_AUTH"), (v, "TRUSTED_AUTH")):
            monkeypatch.setattr(owner, name, auth)
    monkeypatch.setattr(r, "CONTROL", tmp_path)
    monkeypatch.setattr(r, "CHILD", child_root)
    monkeypatch.setattr(r, "RECEIPT", root)
    monkeypatch.setattr(r, "LEDGER", m.ONCE_LEDGER)

    # Materialize the fixed production filenames in the syscall fixture root.
    def body(name, value):
        target = tmp_path / name
        target.write_bytes(m._canonical(value))
        return {"path": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}

    plan = json.loads(Path(old_ref["path"]).read_bytes())
    plan["receipt_root"] = str(root)
    plan["schema_id"] = "qm.ivv.capture-plan" + FAMILY
    material = json.loads(Path(plan["policy_ref"]["path"]).read_bytes())
    material.update(
        schema_id="qm.ivv.capture-policy" + FAMILY,
        diagnostic_mode="DEV_TRUSTED_ENVIRONMENT",
        channel_assurance=ASSURANCE,
    )
    material["exceptions"].append("external_provider_terminal_ipc_socket_environment")
    plan["policy_ref"] = body("policy", material)
    if extra:
        plan.update(
            schema_id="qm.ivv.capture-plan" + extra.FAMILY,
            scope_id=extra.APPROVED.capture_scope_id,
            effect_id=extra.TASK,
            approval_sha256=extra.APPROVED.capture_effect_sha256,
            execution_sha256=extra.APPROVED.authorization_sha256,
        )
        common = extra.provenance()
        common.pop("policy_sha256")
        material.update(
            common,
            schema_id="qm.ivv.capture-policy" + extra.FAMILY,
            scope_id=plan["scope_id"],
            execution_sha256=plan["execution_sha256"],
            effect_id=extra.TASK,
        )
        plan["policy_ref"] = body("policy.json", material)
        assert plan["policy_ref"]["sha256"] == extra.POLICY
        source = tmp_path / "authority.json"
        source.write_bytes(approval if private else b"protected approval held outside portable CI")
        kwargs["authorization_ref"] = {
            "path": str(source),
            "sha256": extra.APPROVED.authorization_sha256,
        }
        if not private:
            original_read = m._read_root_ref

            def protected_approval(ref, **kwargs):
                if (
                    ref["path"].endswith("authority.json")
                    and ref["sha256"] == extra.APPROVED.authorization_sha256
                ):
                    return source.read_bytes()
                return original_read(ref, **kwargs)

            monkeypatch.setattr(m, "_read_root_ref", protected_approval)
    sdk_root = Path(plan["sdk_root"])
    roles = [
        "moomoo/quote/open_quote_context.py",
        "moomoo/pb/Qot_pb2.py",
        *["moomoo/module" + str(i) + ".py" for i in range(10)],
    ]
    pins = {"pins": []}
    for role in roles:
        path = sdk_root / role
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"# fixed SDK source\n")
        pins["pins"].append(
            {"relative_path": role, "LF_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
    plan["sdk_pins_ref"] = body("sdk-pins.json", pins)
    plan["sdk_pins_sha256"] = plan["sdk_pins_ref"]["sha256"]
    catalog = json.loads(Path(kwargs["catalog_ref"]["path"]).read_bytes())
    catalog["trusted_runner_sha256"] = hashlib.sha256(Path(r.__file__).read_bytes()).hexdigest()
    python = tmp_path / "usr/bin/python3.12"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"model interpreter")
    catalog["python_sha256"] = hashlib.sha256(python.read_bytes()).hexdigest()
    if extra:
        catalog["additional_task_sha256"] = hashlib.sha256(
            Path(extra.__file__).read_bytes()
        ).hexdigest()
    catalog_ref = body("catalog", catalog)
    plan["catalog_sha256"] = catalog_ref["sha256"]
    actor = m._native_actor()
    scope = SimpleNamespace(
        child=actor, parent={"pid": actor["pid"] + 1, "uid": 0}, initial=[{"oom_kill": 0}]
    )
    snapshot = {**snapshot, "listener_binding_sha256": snapshot.pop("channels_binding_sha256")}
    monitor = SimpleNamespace(
        first={
            k: snapshot[k]
            for k in (
                "provider_actor",
                "endpoint",
                "identity_binding_sha256",
                "configuration_binding_sha256",
                "listener_binding_sha256",
            )
        },
        last=snapshot,
        peak=0,
        series=SimpleNamespace(samples=2),
    )
    startup = {
        "catalog_ref": catalog_ref,
        "authorization_ref": kwargs["authorization_ref"],
        "budget_ref": body("budget.json", {"G": 1000, "P": 1000}),
    }
    values = {
        "catalog_ref": catalog,
        "go_fields_ref": registration["go_fields"],
        "budget_ref": {"G": 1000, "P": 1000},
    }
    if extra:
        values["go_fields_ref"].pop("controls", None)
        values["_additional"] = extra
        values["go_fields_ref"] = {
            **values["go_fields_ref"],
            "job_id": extra.APPROVED.job_id,
            "windows_policy_sha256": extra.WINDOWS,
            "numeric_runtime_sha256": "8" * 64,
        }
        r._validate_windows_fields(values["go_fields_ref"], extra)
    from test_ivv_native_producer import producer

    context = (startup, values, d, m, None, producer())
    # File ownership and mount observations are the Linux syscall boundary.
    monkeypatch.setattr(os, "lstat", lambda path, **kw: os.stat(path, **kw))
    old_stat, old_fstat = os.stat, os.fstat
    descriptor_paths = {}
    old_open, old_close = os.open, os.close

    def opened(path, *a, **kw):
        fd = old_open(path, *a, **kw)
        descriptor_paths[fd] = Path(path)
        return fd

    def closed(fd):
        descriptor_paths.pop(fd, None)
        old_close(fd)

    def metadata(info, path):
        actual_root = root.real() if hasattr(root, "real") else root
        if path is not None and path.parent == actual_root:
            return SimpleNamespace(**{**vars(info), "st_mode": stat.S_IFREG | 0o600})
        return info

    monkeypatch.setattr(os, "open", opened)
    monkeypatch.setattr(os, "close", closed)
    monkeypatch.setattr(os, "stat", lambda path, **kw: metadata(old_stat(path, **kw), Path(path)))
    monkeypatch.setattr(os, "fstat", lambda fd: metadata(old_fstat(fd), descriptor_paths.get(fd)))
    # Directory fsync is unavailable on Windows, while real file writes/fsync remain.
    monkeypatch.setattr(r, "_sync_dir", lambda path: None, raising=False)
    scope, kernel = owned_scope(r, monkeypatch)
    monkeypatch.setattr(m, "_native_actor", lambda: scope.child)
    # Undo the old fixture's provider stub: exercise the production live-session bridge.
    real_d = dev_module()
    monkeypatch.setattr(d, "_read_native_provider", real_d._read_native_provider)

    class NativeClock(Clock):
        def phase(self, until):
            return contextlib.nullcontext()

    class Backend(ScriptedBackend):
        def open(self):
            if extra:
                assert (additional_ledger / extra.APPROVED.capture_once_key).exists()
                assert not any(m.ONCE_LEDGER.iterdir())
            else:
                assert len(list(m.ONCE_LEDGER.iterdir())) == 1
            assert json.loads((root / "capture-intent.json").read_bytes())["synthetic"] is False
            self.o.context_created()
            self.o.initializing()

        def close(self):
            self.clock.value = 389.9
            super().close()
            if fault == "close":
                raise OSError("modeled abnormal socket close")

    monkeypatch.setattr(m, "_NativeClock", NativeClock)
    monkeypatch.setattr(m, "_OfficialBackend", lambda o, w, p, c: Backend(m, o, w, c, root))
    import queue
    import struct
    import threading

    done, available = threading.Event(), threading.Event()
    parent_clock = {"now": 0.0}
    local = threading.local()
    kernel.os.getpid = lambda: 502 if getattr(local, "child", False) else 501
    kernel.os.getppid = lambda: 501
    # Modeled fork memory has process-local getpid; no real process is signalled.
    proxy = {name: getattr(os, name) for name in dir(os)}
    proxy["getpid"] = lambda: 502
    monkeypatch.setattr(m, "os", SimpleNamespace(**proxy))
    monkeypatch.setattr(d, "os", SimpleNamespace(**proxy))
    monkeypatch.setattr(real_d, "os", SimpleNamespace(**proxy))
    for key, val in (("SO_PASSCRED", 16), ("SCM_CREDENTIALS", 2), ("SOCK_SEQPACKET", 5)):
        monkeypatch.setattr(r.socket, key, val, raising=False)
    monkeypatch.setattr(r.socket, "CMSG_SPACE", lambda size: size + 16, raising=False)
    original_fstat = kernel.os.fstat
    kernel.os.fstat = lambda fd: (
        SimpleNamespace(st_dev=77, st_ino=fd, st_mode=stat.S_IFSOCK | 0o600, st_uid=0)
        if fd in (6000, 6001)
        else original_fstat(fd)
    )

    class Socket:
        type = 5

        def __init__(self, fd):
            self.fd = fd
            self.incoming = queue.Queue()
            self.closed = False

        def fileno(self):
            return self.fd

        def setsockopt(self, *args):
            pass

        def settimeout(self, *args):
            pass

        def send(self, raw):
            packet = json.loads(raw)
            if packet.get("op") == "observe" and getattr(acquired, "closed_at", None) == 389.9:
                parent_clock["now"] = 390.05
            elif packet.get("op") == "terminal":
                parent_clock["now"] = 390.1
            self.peer.incoming.put((raw, kernel.os.getpid()))
            available.set()
            return len(raw)

        def recvmsg(self, *args):
            if self.peer.closed and self.incoming.empty():
                return b"", [], 0, None
            raw, pid = self.incoming.get(timeout=2)
            return (
                raw,
                [(r.socket.SOL_SOCKET, r.socket.SCM_CREDENTIALS, struct.pack("3i", pid, 0, 0))],
                0,
                None,
            )

        def recv(self, *args):
            assert self.peer.closed and self.incoming.empty()
            return b""

    a, b = Socket(6000), Socket(6001)
    a.peer, b.peer = b, a
    channel, child_channel = r._Channel(a), r._Channel(b)
    monitor.next = 0

    def sample():
        monitor.next = 500
        return snapshot

    monitor.sample = sample
    monkeypatch.setattr(r, "_Provider", lambda *a, **kw: monitor)
    # R1: this connected positive must drive the real acquisition bodies.
    acquired = connected_acquisition_kernel(r, kernel, monkeypatch, tmp_path, local, d, m, real_d)
    monkeypatch.setattr(r, "time", SimpleNamespace(monotonic=lambda: parent_clock["now"]))
    if extra:
        legacy_locations = r._locations
        monkeypatch.setattr(r, "_locations", lambda additional: legacy_locations(False))
        if fault == "source":
            catalog["additional_task_sha256"] = "9" * 64
        if fault == "namespace":
            original_stat = acquired.Path.stat

            def namespace_stat(path, *args, **kwargs):
                if str(path) == "/proc/502/ns/mnt":
                    return SimpleNamespace(st_ino=40)
                return original_stat(path, *args, **kwargs)

            monkeypatch.setattr(acquired.Path, "stat", namespace_stat)
    assert r.RELEASE.is_absolute() and r.RELEASE.resolve(strict=True) == r.RELEASE, (
        str(r.RELEASE),
        r.RELEASE.drive,
        r.RELEASE.anchor,
        str(r.RELEASE.resolve(strict=True)),
    )
    root = acquired.Path(root)
    for ref in startup.values():
        ref["path"] = str(acquired.Path(ref["path"]))
    for key, value in plan.items():
        if type(value) is dict and "path" in value:
            value["path"] = str(acquired.Path(value["path"]))
        elif key in ("sdk_root", "receipt_root"):
            plan[key] = str(acquired.Path(value))
    monkeypatch.setattr(__import__("test_ivv_dev_diagnostic"), "Path", acquired.Path)
    status = {"rc": 1}

    def child_entry():
        local.child = True
        try:
            r._child(child_channel, 501, context, plan)
            status["rc"] = 0
        except BaseException as error:
            status["error"] = error
            child_channel.send({"op": "failed", "code": r.reason(error)})
        finally:
            b.closed = True
            done.set()
            available.set()

    def ready(*args):
        if a.incoming.empty() and not done.is_set():
            available.clear()
            if a.incoming.empty() and not done.is_set():
                assert available.wait(2), "modeled private IPC stalled"
        if not a.incoming.empty() and not (pidfd_first and done.is_set()):
            return [a], [], []
        assert done.is_set()
        parent_clock["now"] = 391.0
        if fault == "event":
            kernel.nodes[kernel.handles[scope.leaf] + "/memory.events"]["content"] = "oom_kill 1"
        kernel.nodes[kernel.handles[scope.leaf] + "/cgroup.procs"]["content"] = ""
        return [scope.pidfd], [], []

    monkeypatch.setattr(r, "select", SimpleNamespace(select=ready))
    kernel.os.waitid = lambda *a: SimpleNamespace(si_pid=502, si_code=1, si_status=status["rc"])
    # Windows lacks MSG_DONTWAIT; modeled EOF here is the external socket boundary.
    monkeypatch.setattr(r.socket, "MSG_DONTWAIT", 64, raising=False)
    child_thread = threading.Thread(target=child_entry)
    child_thread.start()
    try:
        produced = r._supervise(scope, channel, 6001, context, plan)
    finally:
        child_thread.join(timeout=3)
        if status.get("error") and fault != "namespace":
            raise status["error"]
    assert not child_thread.is_alive() and status["rc"] == 0
    assert acquired.namespace == 44 and acquired.nnp == 1 and acquired.caps == 0
    assert acquired.runtime_reads > 12 and acquired.bound_mounts
    assert scope.reaped is True
    assert acquired.closed_at == 389.9 and produced["elapsed_seconds"] == 391.0
    scope.check_resources()
    scope.remove()
    result = json.loads((root / "capture-manifest.json").read_bytes())
    if extra:
        assert not any(m.ONCE_LEDGER.iterdir())
        assert (
            json.loads((root / "plain.json").read_bytes())["scope_id"]
            == extra.APPROVED.capture_scope_id
        )
        requests = json.loads((root / "requests.json").read_bytes())
        assert requests["sent"] == [
            "state",
            "quota",
            "basic",
            "rehab",
            "dividends",
            "splits",
            "history",
        ]
        return (
            result,
            json.loads((root / "capture-intent.json").read_bytes()),
            produced,
            json.loads((tmp_path / "go.json").read_bytes()),
        )
    kwargs.update(
        go_ref={
            "path": str(tmp_path / "go.json"),
            "sha256": result["source_binding"]["root_go_sha256"],
        },
        catalog_ref=catalog_ref,
        expected_go_sha256=result["source_binding"]["root_go_sha256"],
        expected_policy_sha256=result["policy_sha256"],
    )
    _consume_real_capture_artifacts(
        m, root, result, kwargs, tmp_path, monkeypatch, registration, produced_parent=produced
    )
    assert produced["schema_id"] == "qm.ivv.capture-parent-close" + FAMILY
    assert len(produced["evidence_refs"]) == 8
    for suffix in (".v1", ".dev-diagnostic.v1", FAMILY):
        with pytest.raises(m.CaptureRejected, match="spent_capture_effect"):
            m._reserve_once(
                {
                    **plan,
                    "schema_id": "qm.ivv.capture-plan" + suffix,
                    "effect_id": "new-opaque-label",
                    "receipt_root": str(root.parent / "other"),
                    "capture_helper_sha256": "f" * 64,
                }
            )


@pytest.mark.parametrize("actual_parent", [41, 1])
def test_child_binds_parent_death_signal_before_waiting_gate(monkeypatch, actual_parent):
    r = runner()
    events = []
    monkeypatch.setattr(r.signal, "SIGKILL", 9, raising=False)
    monkeypatch.setattr(r.os, "getppid", lambda: actual_parent)
    monkeypatch.setattr(r, "_libcall", lambda *a: events.append(a))
    if actual_parent == 1:
        with pytest.raises(r.Refused, match="PARENT_LOST"):
            r._bind_parent(41)
    else:
        r._bind_parent(41)
        assert events == [("prctl", 1, r.signal.SIGKILL, 0, 0, 0)]


def test_actual_released_helper_bytes_match_issuer_bootstrap(monkeypatch):
    from test_ivv_dev_native import _linux_source_file

    d = dev_module()
    path = Path(d.__file__).with_name("capture_opend_ivv_daily.py")
    _linux_source_file(monkeypatch, d, path, "good")
    monkeypatch.setattr(d.sys, "platform", "linux")
    loaded = d._capture()
    assert loaded.capture_trusted_once is not None


@pytest.mark.parametrize("case", ["replaced", "close_primary", "writable"])
def test_readonly_source_read_retains_exact_fd_lifetime_and_primary(tmp_path, monkeypatch, case):
    r = runner()
    path = tmp_path / "source.py"
    data = b"# source\n"
    path.write_bytes(data)
    fixed = dict(
        st_dev=1,
        st_ino=2,
        st_mode=stat.S_IFREG | 0o444,
        st_uid=0,
        st_nlink=1,
        st_size=len(data),
        st_ctime_ns=5,
        st_mtime_ns=6,
    )
    before = SimpleNamespace(**fixed)
    calls = []

    def fstat(fd):
        calls.append(fd)
        return (
            SimpleNamespace(**{**fixed, "st_ino": 99})
            if case == "replaced" and len(calls) > 1
            else before
        )

    fake = SimpleNamespace(
        O_RDONLY=0,
        O_NOFOLLOW=0,
        O_CLOEXEC=0,
        O_NONBLOCK=0,
        ST_RDONLY=1,
        open=lambda *a: 40,
        fstat=fstat,
        stat=lambda *a, **kw: before,
        fstatvfs=lambda fd: SimpleNamespace(f_flag=0 if case == "writable" else 1),
        pread=lambda *a: b"wrong" if case == "close_primary" else data,
    )

    def close(fd):
        if case == "close_primary":
            raise OSError("DO_NOT_EXPOSE_PATH_OR_DATA")

    fake.close = close
    monkeypatch.setattr(r, "os", fake)
    monkeypatch.setattr(r, "protected", lambda path: None)
    code = {
        "replaced": "CONTROL_RACE",
        "close_primary": "CONTROL_RACE",
        "writable": "SOURCE_WRITABLE",
    }[case]
    with pytest.raises(r.Refused, match=code):
        r.read_ref(
            {"path": str(path), "sha256": hashlib.sha256(data).hexdigest()}, path, readonly=True
        )


def owned_scope(r, monkeypatch, *, create=True, unit="owned.service"):
    """Kernel boundary: real _Scope ownership checks over literal cgroup2 nodes."""
    nodes, handles, stamps, writes, signals = {}, {}, {}, [], []
    root = "/sys/fs/cgroup/system.slice/" + unit
    manager = root + "/manager"
    parent = {
        "pid": 501,
        "uid": 0,
        "start_ticks": 11,
        "cgroup": "/system.slice/" + unit + "/manager",
    }
    child = {"pid": 502, "uid": 0, "start_ticks": 22, "cgroup": parent["cgroup"]}
    process = {501: (parent, 1), 502: (child, 501)}

    def add(path, directory=False, content=""):
        nodes[path] = {"ino": len(nodes) + 100, "directory": directory, "content": content}

    def directory(path, procs):
        add(path, True)
        for name, value in {
            **r.LIMITS,
            "cgroup.procs": procs,
            "cgroup.events": "populated 0",
            "cgroup.controllers": "cpu memory pids",
            "cgroup.subtree_control": "",
            "memory.events": "oom_kill 0",
            "pids.events": "max 0",
            "memory.swap.events": "max 0",
        }.items():
            add(path + "/" + name, content=value)

    directory(root, "")
    directory(manager, "501")

    def name(path, where=None):
        return (
            (handles[where] + "/" + str(path))
            if where is not None
            else str(path).replace("\\", "/")
        )

    def info(path):
        node = nodes[path]
        return SimpleNamespace(
            st_dev=7,
            st_ino=node["ino"],
            st_mode=(stat.S_IFDIR | 0o700) if node["directory"] else stat.S_IFREG | 0o644,
            st_uid=0,
        )

    def opened(path, flags, mode=0o777, *, dir_fd=None):
        path = name(path, dir_fd)
        if not path.startswith("/sys/fs/cgroup"):
            return os.open(path, flags, mode)
        if path not in nodes:
            raise FileNotFoundError(path)
        fd = max([19, *handles]) + 1
        handles[fd] = path
        stamps[fd] = info(path)
        return fd

    def mkdir(path, mode, dir_fd):
        path = name(path, dir_fd)
        if path in nodes:
            raise FileExistsError(path)
        directory(path, "")

    def write(fd, raw):
        path = handles[fd]
        writes.append((path, raw))
        nodes[path]["content"] = raw.decode()
        if path.endswith("/cgroup.subtree_control"):
            nodes[path]["content"] = raw.decode().replace("+", "")
        if path.endswith("/cgroup.procs"):
            actor, ppid = process[int(raw)]
            process[int(raw)] = (
                {**actor, "cgroup": path.removeprefix("/sys/fs/cgroup").rsplit("/", 1)[0]},
                ppid,
            )
        return len(raw)

    def scan(fd):
        path = handles[fd]
        entries = [
            SimpleNamespace(name=k.rsplit("/", 1)[1], is_dir=lambda follow_symlinks=False: True)
            for k, v in nodes.items()
            if k.rsplit("/", 1)[0] == path and v["directory"]
        ]
        return contextlib.nullcontext(entries)

    def remove(path, dir_fd):
        path = name(path, dir_fd)
        for key in list(nodes):
            if key == path or key.startswith(path + "/"):
                del nodes[key]

    fake = SimpleNamespace(
        O_RDONLY=0,
        O_WRONLY=1,
        O_CLOEXEC=0,
        O_NOFOLLOW=0,
        O_DIRECTORY=65536,
        getpid=lambda: 501,
        open=opened,
        close=lambda fd: handles.pop(fd) if fd in handles else (None if fd == 90 else os.close(fd)),
        mkdir=mkdir,
        rmdir=remove,
        stat=lambda p, dir_fd=None, **kw: (
            info(name(p, dir_fd))
            if name(p, dir_fd).startswith("/sys/fs/cgroup")
            else os.stat(p, **kw)
        ),
        fstat=lambda fd: stamps[fd] if fd in stamps else os.fstat(fd),
        pread=lambda fd, n, o: (
            nodes[handles[fd]]["content"].encode()[o : o + n]
            if fd in handles
            else os.pread(fd, n, o)
        ),
        write=write,
        scandir=scan,
        pidfd_open=lambda pid: 90,
        P_PIDFD=3,
        WEXITED=4,
        WNOHANG=1,
        CLD_EXITED=1,
        waitid=lambda *a: SimpleNamespace(si_pid=502, si_code=1, si_status=0),
    )
    for key in ("O_CREAT", "O_EXCL", "O_NONBLOCK", "fdopen", "fchmod", "fsync"):
        setattr(fake, key, getattr(os, key, 0))
    monkeypatch.setattr(r, "os", fake)
    monkeypatch.setattr(r, "_cgroup_mount", lambda: 44)
    monkeypatch.setattr(r, "_mount_id", lambda fd: 44)
    monkeypatch.setattr(r, "_process", lambda pid: process[pid])
    monkeypatch.setattr(r, "_manager_contract", lambda parent: {"InvocationID": "1" * 32})
    prior = Path.read_text

    def text(path, *a, **kw):
        if path.as_posix() == "/proc/self/fdinfo/90":
            return "Pid:\t502\n"
        return prior(path, *a, **kw)

    monkeypatch.setattr(Path, "read_text", text)
    monkeypatch.setattr(
        r.signal, "pidfd_send_signal", lambda fd, sig: signals.append((fd, sig)), raising=False
    )
    monkeypatch.setattr(r.signal, "SIGKILL", 9, raising=False)
    if unit != "owned.service":
        monkeypatch.setattr(r, "protected", lambda path: info(str(path).replace(chr(92), "/")))
    stack = contextlib.ExitStack()
    scope = r._Scope(stack) if create else None
    if scope is not None:
        scope.bind(502)
    return scope, SimpleNamespace(
        nodes=nodes,
        handles=handles,
        writes=writes,
        signals=signals,
        process=process,
        os=fake,
        stack=stack,
    )


@pytest.mark.parametrize(
    "case", ["normal", "pid", "pidfd", "cgroup", "event", "missing", "foreign", "crash"]
)
def test_owned_scope_actual_wait_resource_and_inode_gates(monkeypatch, case):
    r = runner()
    scope, kernel = owned_scope(r, monkeypatch)
    leaf = kernel.handles[scope.leaf]
    if case == "pid":
        actor, ppid = kernel.process[502]
        kernel.process[502] = ({**actor, "start_ticks": 23}, ppid)
    elif case == "pidfd":
        prior = Path.read_text
        monkeypatch.setattr(
            Path,
            "read_text",
            lambda p, *a, **kw: (
                "Pid:\t1\n" if p.as_posix() == "/proc/self/fdinfo/90" else prior(p, *a, **kw)
            ),
        )
    elif case == "cgroup":
        kernel.nodes[leaf]["ino"] += 1
    elif case == "event":
        kernel.nodes[leaf + "/memory.events"]["content"] = "oom_kill 1"
    elif case == "missing":
        del kernel.nodes[leaf]
    elif case == "foreign":
        kernel.nodes[leaf + "/cgroup.procs"]["content"] = "999"
    elif case == "crash":
        kernel.os.waitid = lambda *a: SimpleNamespace(si_pid=502, si_code=2, si_status=9)
    if case in ("pid", "pidfd"):
        with pytest.raises(r.Refused):
            scope.reap()
        assert kernel.signals == []
    elif case in ("cgroup", "event", "missing"):
        with pytest.raises((r.Refused, KeyError)):
            scope.check_resources()
    elif case == "crash":
        with pytest.raises(r.Refused, match="ABNORMAL_CHILD_EXIT"):
            scope.reap()
    else:
        assert scope.reap() == 0
        kernel.nodes[leaf + "/cgroup.procs"]["content"] = "" if case == "normal" else "999"
        if case == "foreign":
            with pytest.raises(r.Refused, match="CGROUP_NOT_EMPTY"):
                scope.remove()
        else:
            scope.check_resources()
            scope.remove()
            assert leaf not in kernel.nodes
    assert not any(path.endswith("/cgroup.kill") for path, _ in kernel.writes)


@pytest.mark.parametrize(
    "change",
    [
        {},
        {"KillMode": "control-group"},
        {"SendSIGKILL": "yes"},
        {"MainPID": "999"},
        {"InvocationID": ""},
        {"Delegate": "no"},
    ],
)
def test_manager_never_supplies_groupwide_kill_or_self_exit_authority(monkeypatch, change):
    r = runner()
    fields = {
        "Id": "owned.service",
        "MainPID": "501",
        "InvocationID": "1" * 32,
        "ControlGroup": "/system.slice/owned.service",
        "KillMode": "process",
        "SendSIGKILL": "no",
        "Delegate": "yes",
        "DelegateSubgroup": "manager",
        "ActiveState": "active",
        "SubState": "running",
    }
    monkeypatch.setattr(r, "_manager_fields", lambda unit: {**fields, **change}, raising=False)
    parent = {"pid": 501, "cgroup": "/system.slice/owned.service/manager"}
    if change:
        with pytest.raises(r.Refused, match="OWN_MANAGER_CONTRACT"):
            r._manager_contract(parent)
    else:
        assert r._manager_contract(parent) == fields


@pytest.mark.parametrize("ready", [True, False])
def test_child_environment_keeps_only_verified_own_home(monkeypatch, ready):
    r = runner()

    class Environment:
        def __init__(self):
            self.values = {"HOME": "/root", "PRIVATE_VALUE": "never read or exported"}

        def get(self, key):
            assert key == "HOME"
            return self.values[key]

        def clear(self):
            self.values.clear()

        def update(self, value):
            self.values.update(value)

    env = Environment()
    monkeypatch.setattr(
        r,
        "os",
        SimpleNamespace(environ=env, ST_RDONLY=1, statvfs=lambda path: SimpleNamespace(f_flag=1)),
    )
    monkeypatch.setattr(r, "protected", lambda path: None)
    from pathlib import PurePosixPath

    class Home(PurePosixPath):
        def resolve(self, strict=False):
            return self

        def stat(self):
            return SimpleNamespace(
                st_mode=(stat.S_IFDIR | 0o700) if ready else stat.S_IFREG | 0o600
            )

    monkeypatch.setattr(r, "Path", Home)
    if ready:
        r._environment()
        assert env.values == {"HOME": "/root", "PATH": "/usr/bin:/bin", "LC_ALL": "C"}
    else:
        with pytest.raises(r.Refused, match="HOME_LOG_PREREQUISITE"):
            r._environment()


def test_all_retained_close_errors_survive_primary_failure():
    r = runner()
    with r._Handles() as held:

        def bad(code):
            raise OSError(code)

        held.callback(bad, "private path 1")
        held.callback(bad, "private path 2")
    assert held.errors == ["CLOSE_OSError", "CLOSE_OSError"]


@pytest.mark.parametrize("case", ["good", "fd_swap", "credentials", "truncated", "eof"])
def test_control_channel_uses_held_socket_and_kernel_credentials(monkeypatch, case):
    import struct

    r = runner()
    info = SimpleNamespace(st_dev=1, st_ino=9, st_mode=stat.S_IFSOCK | 0o600, st_uid=0)
    fake = SimpleNamespace(fstat=lambda fd: info)
    monkeypatch.setattr(r, "os", fake)
    for key, value in (("SO_PASSCRED", 16), ("SCM_CREDENTIALS", 2), ("SOCK_SEQPACKET", 5)):
        monkeypatch.setattr(r.socket, key, value, raising=False)
    cmsg = [
        (
            r.socket.SOL_SOCKET,
            r.socket.SCM_CREDENTIALS,
            struct.pack("3i", 502 if case != "credentials" else 999, 0, 0),
        )
    ]
    sock = SimpleNamespace(
        fileno=lambda: 40,
        type=5,
        setsockopt=lambda *a: None,
        settimeout=lambda *a: None,
        recvmsg=lambda *a: (
            b"" if case == "eof" else b'{"op":"ready"}',
            [] if case == "eof" else cmsg,
            32 if case == "truncated" else 0,
            None,
        ),
    )
    monkeypatch.setattr(r.socket, "CMSG_SPACE", lambda size: size + 16, raising=False)
    channel = r._Channel(sock)
    if case == "fd_swap":
        fake.fstat = lambda fd: SimpleNamespace(st_dev=1, st_ino=10, st_mode=info.st_mode, st_uid=0)
    if case == "good":
        assert channel.recv(502) == {"op": "ready"}
    else:
        with pytest.raises(r.Refused):
            channel.recv(502)


@pytest.mark.parametrize(
    "case", ["good", "threshold", "identity", "listener", "resource", "postcheck", "cleanup"]
)
def test_parent_provider_sample_runs_real_identity_growth_and_thresholds(monkeypatch, case):
    from test_ivv_dev_native import native_module
    from test_ivv_native_producer import NativeFixture, producer

    r, n, p = runner(), native_module(), producer()
    identity_doc = NativeFixture().identity()
    paths = {name: i + 20 for i, name in enumerate(n._ROLE_PATHS)}
    held = set()
    state = {"failed": False, "closed": False}

    def info(fd):
        return SimpleNamespace(
            st_dev=5,
            st_ino=fd % 100,
            st_mode=stat.S_IFDIR | 0o700,
            st_nlink=1,
            st_uid=997,
            st_gid=987,
            st_size=0,
            st_blocks=0,
            st_ctime_ns=3,
            st_mtime_ns=3,
        )

    native_os = SimpleNamespace(
        O_RDONLY=0,
        O_PATH=8,
        O_NOFOLLOW=1,
        O_CLOEXEC=2,
        O_DIRECTORY=4,
        open=lambda path, flags, dir_fd: dir_fd + 100,
        fstat=info,
        scandir=lambda fd: contextlib.nullcontext([]),
    )
    monkeypatch.setattr(n, "os", native_os)

    class Reader:
        root = 10
        manager_fields = {"ControlGroup": "/system.slice/provider.service"}
        processes = {705711: (700, None, identity_doc["processes"][2])}

        def identity(self):
            if case == "identity":
                return {**identity_doc, "main_pid": 999}
            return identity_doc

        def socket_inodes(self, fd):
            return {900}

        def held_path(self, path, root):
            return self.keep(paths[path])

        def keep(self, fd):
            held.add(fd)
            return fd

        def release(self, fd):
            held.discard(fd)

        def directory(self, path):
            return self.keep(300)

        def read(self, fd, name, bound):
            if name.startswith("/proc/self/fdinfo/"):
                return b"mnt_id: 1\n"
            if name == "net/tcp":
                return (
                    b"header\n"
                    if case == "listener"
                    else b"header\n0: 0100007F:2B68 00000000:0000 0A 0 0 0 0 0 900\n"
                )
            return {
                "memory.max": b"1073741824",
                "memory.swap.max": b"0",
                "cpu.max": b"50000 100000",
                "pids.max": b"999" if case == "resource" else b"128",
            }[name]

        def finish(self):
            return ["drift"] if case in ("postcheck", "cleanup") else []

        def close(self):
            state["closed"] = True
            if case == "cleanup":
                raise OSError("private names never serialized")

    monkeypatch.setattr(p, "PosixReader", Reader)
    endpoint = {"host": "127.0.0.1", "port": 11112, "is_encrypt": False, "security_firm": "NONE"}
    monkeypatch.setattr(n, "trusted_quote_configuration", lambda plan: (endpoint, "9" * 64))
    monkeypatch.setattr(
        r,
        "read_ref",
        lambda *a: r.raw_json({"G": 10500000001 if case == "threshold" else 1000, "P": 1000}),
    )
    monkeypatch.setattr(
        r,
        "os",
        SimpleNamespace(statvfs=lambda path: SimpleNamespace(f_bavail=100000000000, f_frsize=1)),
    )
    monkeypatch.setattr(r.time, "monotonic", lambda: 0)
    monitor = r._Provider(n, p, leaf(), {"started_monotonic": 0}, {})
    if case == "good":
        snapshot = monitor.sample()
        assert snapshot["provider_actor"]["pid"] == 705711
        assert snapshot["sample"]["incremental_bytes"] == 0
        assert "channels_binding_sha256" not in snapshot
        assert monitor.series.samples == 1 and monitor.next == 5
    else:
        with pytest.raises((ValueError, RuntimeError)) as exc:
            monitor.sample()
        if case == "cleanup":
            assert str(exc.value) == "PROVIDER_DRIFT+OSError"
    assert state["closed"] and not held


@pytest.mark.parametrize(
    "case", ["good", "namespace", "source", "sdk_pin", "import", "search", "home", "runtime"]
)
def test_child_runtime_gate_checks_real_pin_set_and_readonly_origins(monkeypatch, case):
    from pathlib import PurePosixPath

    r = runner()
    sdk = PurePosixPath("/opt/sdk")
    files = {
        "moomoo/quote/open_quote_context.py": b"# quote",
        "moomoo/pb/Qot_pb2.py": b"# protocol",
    }
    files.update({"moomoo/module" + str(i) + ".py": b"# fixed" for i in range(10)})
    pins = {
        "pins": [
            {"relative_path": name, "LF_sha256": hashlib.sha256(data).hexdigest()}
            for name, data in files.items()
        ]
    }

    class KernelPath(PurePosixPath):
        def resolve(self, strict=False):
            return KernelPath("/usr/bin/python3.12") if str(self) == "/proc/self/exe" else self

        def stat(self):
            return SimpleNamespace(st_mode=stat.S_IFREG if case == "home" else stat.S_IFDIR)

        def exists(self):
            return True

        def read_bytes(self):
            data = files[str(self.relative_to(sdk))]
            return data + b"changed" if case == "sdk_pin" else data

    monkeypatch.setattr(r, "Path", KernelPath)
    sdk = KernelPath(sdk)
    monkeypatch.setattr(r, "SDK", sdk)
    monkeypatch.setattr(r, "RELEASE", KernelPath("/opt/release"))
    monkeypatch.setattr(r, "CONTROL", KernelPath("/controls"))
    monkeypatch.setattr(r, "protected", lambda path: None)
    monkeypatch.setattr(r, "_writable_mounts", lambda producer: None)

    def read(ref, path, *a):
        if case == "source" and str(path).endswith("ivv_trusted_runner.py"):
            raise r.Refused("CONTROL_DIGEST")
        return r.raw_json(pins) if str(path).endswith("sdk-pins.json") else b"source"

    monkeypatch.setattr(r, "read_ref", read)
    monkeypatch.setattr(
        r,
        "sys",
        SimpleNamespace(
            version_info=(3, 11) if case == "runtime" else (3, 12),
            executable="/usr/bin/python3.12",
            path=["/other" if case == "search" else "/usr/lib/python3.12", str(sdk)],
        ),
    )
    monkeypatch.setattr(
        r,
        "os",
        SimpleNamespace(
            stat=lambda path: SimpleNamespace(st_ino=45 if case == "namespace" else 44),
            environ={"HOME": "/root"},
            ST_RDONLY=1,
            statvfs=lambda path: SimpleNamespace(f_flag=1),
        ),
    )
    monkeypatch.setattr(
        r.importlib.machinery.PathFinder,
        "find_spec",
        lambda *a: SimpleNamespace(
            origin="/other/moomoo/__init__.py"
            if case == "import"
            else str(sdk / "moomoo/__init__.py")
        ),
    )
    plan = {"sdk_root": str(sdk), "sdk_pins_ref": {}, "sdk_pins_sha256": "1" * 64}
    catalog = {**{key: "2" * 64 for key in r.SOURCES}, "python_sha256": "3" * 64}
    if case == "good":
        assert r._runtime(plan, None, 44, catalog, None)["namespace_inode"] == 44
    else:
        with pytest.raises(r.Refused):
            r._runtime(plan, None, 44, catalog, None)


@pytest.mark.parametrize("case", ["good", "writable", "landlock", "caps", "fd"])
def test_actual_child_namespace_acquisition_has_no_fallback(monkeypatch, case):
    from pathlib import PurePosixPath

    from test_ivv_native_producer import producer

    r, p = runner(), producer()
    live = {0, 1, 2, 9, 10}
    state = {"namespace": 40, "readonly": {}, "null": False}
    calls = []

    class KernelPath(PurePosixPath):
        def stat(self):
            directory = str(self).startswith(
                (
                    "/owned/child",
                    "/fixed/once",
                    "/usr",
                    "/release",
                    "/sdk",
                    "/controls",
                    "/sys/fs/cgroup",
                )
            )
            return SimpleNamespace(
                st_ino=state["namespace"], st_mode=stat.S_IFDIR if directory else stat.S_IFREG
            )

        def resolve(self, strict=False):
            return self

        def read_bytes(self):
            root = "ro" if state["readonly"].get("/", False) else "rw"

            def mode(path):
                return "ro" if state["readonly"].get(path, False) else "rw"

            rows = [
                f"1 99 8:1 / / {root} - ext4 /dev/root rw",
                f"2 1 8:1 /child /owned/child {mode('/owned/child')} - ext4 /dev/root rw",
                f"3 1 8:1 /once /fixed/once {mode('/fixed/once')} - ext4 /dev/root rw",
            ]
            if case == "writable":
                rows.append("4 1 8:1 /tmp /tmp rw - ext4 /dev/root rw")
            return ("\n".join(rows) + "\n").encode()

        def read_text(self):
            if str(self).endswith("cap_last_cap"):
                return "40"
            return "\n".join(
                [
                    "NoNewPrivs:\t1",
                    *(
                        k + ":\t" + ("1" if case == "caps" else "0")
                        for k in ("CapEff", "CapPrm", "CapInh", "CapBnd", "CapAmb")
                    ),
                ]
            )

    monkeypatch.setattr(r, "Path", KernelPath)
    monkeypatch.setattr(r, "CHILD", KernelPath("/owned/child"))
    monkeypatch.setattr(r, "LEDGER", KernelPath("/fixed/once"))
    monkeypatch.setattr(r, "RELEASE", KernelPath("/release"))
    monkeypatch.setattr(r, "SDK", KernelPath("/sdk"))
    monkeypatch.setattr(r, "CONTROL", KernelPath("/controls"))
    monkeypatch.setattr(
        r, "_process", lambda pid: ({"cgroup": "/system.slice/unit.service/ivv-owned-501-11"}, 501)
    )
    monkeypatch.setattr(r, "protected", lambda path: None)

    def opened(path, flags):
        if str(path) == "/dev/null":
            live.add(10)
            state["null"] = True
            return 10
        return 30 if str(path) == "/owned/child" else 31

    def fstat(fd):
        if fd not in live:
            raise OSError(9, "closed")
        return SimpleNamespace(
            st_dev=1,
            st_ino=fd + (1 if case == "fd" and state["null"] and fd == 9 else 0),
            st_mode=stat.S_IFSOCK | 0o600 if fd == 9 else stat.S_IFCHR | 0o600,
            st_uid=0,
            st_rdev=259,
        )

    fake = SimpleNamespace(
        listdir=lambda path: list(map(str, live)),
        fstat=fstat,
        stat=lambda path: SimpleNamespace(st_ino=state["namespace"]),
        close=lambda fd: live.discard(fd),
        open=opened,
        dup2=lambda *a, **kw: None,
        makedev=lambda a, b: 259,
        uname=lambda: SimpleNamespace(machine="x86_64"),
        O_RDWR=2,
        O_NOFOLLOW=0,
        O_PATH=8,
        O_DIRECTORY=4,
        O_CLOEXEC=2,
    )
    fake.getpid = lambda: 502
    monkeypatch.setattr(r, "os", fake)

    def libcall(name, *args):
        calls.append((name, args))
        if name == "unshare":
            state["namespace"] = 44
        if name == "syscall":
            import ctypes

            attr = ctypes.cast(args[4], ctypes.POINTER(r._MountAttr)).contents
            path = args[2].decode()
            if path == "/" and args[3] == 0x8000:
                state["readonly"].update({p: True for p in ("/", "/owned/child", "/fixed/once")})
            state["readonly"][path] = bool(attr.set)

    fake.fsencode = os.fsencode
    monkeypatch.setattr(r, "_libcall", libcall)

    def landlock(number, *args):
        calls.append((number, args))
        if number == 444 and args[-1] == 1:
            return 4 if case == "landlock" else 5
        return 75 if number == 444 else 0

    monkeypatch.setattr(r.ctypes, "CDLL", lambda *a, **kw: SimpleNamespace(syscall=landlock))
    for key, value in (("SO_PASSCRED", 16), ("SOCK_SEQPACKET", 5)):
        monkeypatch.setattr(r.socket, key, value, raising=False)
    channel = r._Channel(
        SimpleNamespace(
            fileno=lambda: 9, type=5, setsockopt=lambda *a: None, settimeout=lambda *a: None
        )
    )
    if case == "good":
        assert r._child_namespace(channel, p) == 44
        assert live == {0, 1, 2, 9}
        assert any(name == 446 for name, _ in calls)
        assert any(name == "capset" for name, _ in calls)
    else:
        with pytest.raises(r.Refused):
            r._child_namespace(channel, p)


@pytest.mark.parametrize(
    "case", ["good", "exe_device", "shared_namespace", "cap", "extra_fd", "writable"]
)
def test_parent_independently_reads_child_kernel_state(monkeypatch, case):
    from pathlib import PurePosixPath

    from test_ivv_native_producer import producer

    r, p = runner(), producer()

    class KernelPath(PurePosixPath):
        def stat(self):
            if str(self).endswith("ns/mnt"):
                return SimpleNamespace(st_ino=40 if case == "shared_namespace" else 44)
            if str(self).endswith("exe"):
                return SimpleNamespace(
                    st_dev=2 if case == "exe_device" and "502" in str(self) else 1,
                    st_ino=99,
                    st_mode=stat.S_IFREG | 0o755,
                    st_uid=0,
                )
            fd = int(self.name)
            return SimpleNamespace(
                st_ino=700 if fd == 3 else fd,
                st_mode=stat.S_IFSOCK if fd == 3 else stat.S_IFCHR,
                st_rdev=259,
            )

        def read_bytes(self):
            return (
                "1 99 8:1 / / " + ("rw" if case == "writable" else "ro") + " - ext4 /dev/root rw\n"
                "2 1 8:1 /child /owned/child rw - ext4 /dev/root rw\n"
                "3 1 8:1 /once /fixed/once rw - ext4 /dev/root rw\n"
            ).encode()

        def read_text(self):
            return "\n".join(
                [
                    "NoNewPrivs:\t1",
                    *(
                        k + ":\t" + ("1" if case == "cap" else "0")
                        for k in ("CapEff", "CapBnd", "CapAmb", "CapInh", "CapPrm")
                    ),
                ]
            )

        def iterdir(self):
            return iter([self / str(i) for i in range(5 if case == "extra_fd" else 4)])

    monkeypatch.setattr(r, "Path", KernelPath)
    monkeypatch.setattr(r, "CHILD", KernelPath("/owned/child"))
    monkeypatch.setattr(r, "LEDGER", KernelPath("/fixed/once"))
    monkeypatch.setattr(
        r,
        "os",
        SimpleNamespace(stat=lambda path: SimpleNamespace(st_ino=40), makedev=lambda *a: 259),
    )
    scope = SimpleNamespace(pid=502, check_pid=lambda: None, child={"pid": 502})
    if case == "good":
        assert r._child_kernel(scope, p, 700, True)["namespace_inode"] == 44
    else:
        with pytest.raises(r.Refused):
            r._child_kernel(scope, p, 700, True)


def test_parent_manifest_read_rejects_replaced_held_inode(monkeypatch, tmp_path):
    r = runner()
    path = tmp_path / "capture-manifest.json"
    raw = b'{"state":"CAPTURED_UNREVIEWED"}'
    fields = dict(
        st_dev=1,
        st_ino=2,
        st_mode=stat.S_IFREG | 0o600,
        st_uid=0,
        st_nlink=1,
        st_size=len(raw),
        st_ctime_ns=1,
        st_mtime_ns=1,
    )
    before = SimpleNamespace(**fields)
    seen = []

    def held(fd):
        seen.append(fd)
        return before if len(seen) == 1 else SimpleNamespace(**{**fields, "st_ino": 3})

    monkeypatch.setattr(r, "protected", lambda path: None)
    monkeypatch.setattr(
        r,
        "os",
        SimpleNamespace(
            O_RDONLY=0,
            O_NOFOLLOW=0,
            O_CLOEXEC=0,
            open=lambda *a: 40,
            fstat=held,
            pread=lambda *a: raw,
            close=lambda fd: None,
        ),
    )
    monkeypatch.setattr(Path, "stat", lambda p, **kw: before if p == path else os.stat(p, **kw))
    with pytest.raises(r.Refused, match="CAPTURE_RECEIPT_DIGEST"):
        r._manifest(hashlib.sha256(raw).hexdigest(), path)


def test_every_live_snapshot_stops_on_own_runtime_drift():
    r = runner()
    sends = []
    channel = SimpleNamespace(send=lambda obj: sends.append(obj), recv=lambda pid: {"snapshot": {}})

    def changed():
        raise r.Refused("SDK_PIN_DRIFT")

    session = r._ChildSession(channel, 501, changed)
    with pytest.raises(r.Refused, match="SDK_PIN_DRIFT"):
        session.snapshot()
    assert sends == []


def test_landlock_does_not_expose_home_credentials_or_initial_environment(monkeypatch):
    import ctypes
    from pathlib import PurePosixPath

    r = runner()

    class PublicPath(PurePosixPath):
        def resolve(self, strict=False):
            return self

        def stat(self):
            return SimpleNamespace(
                st_mode=stat.S_IFDIR
                if str(self).startswith(
                    ("/usr", "/source", "/sdk", "/controls", "/output", "/once", "/sys/fs/cgroup")
                )
                else stat.S_IFREG
            )

    for name, path in (
        ("RELEASE", "/source"),
        ("SDK", "/sdk"),
        ("CONTROL", "/controls"),
        ("CHILD", "/output"),
        ("LEDGER", "/once"),
    ):
        monkeypatch.setattr(r, name, PublicPath(path))
    monkeypatch.setattr(r, "Path", PublicPath)
    monkeypatch.setattr(r, "protected", lambda path: None)
    monkeypatch.setattr(
        r, "_process", lambda pid: ({"cgroup": "/system.slice/unit.service/ivv-owned-501-11"}, 501)
    )
    paths, rules = {}, []

    def opened(path, flags):
        fd = len(paths) + 20
        paths[fd] = str(path)
        return fd

    monkeypatch.setattr(
        r,
        "os",
        SimpleNamespace(
            open=opened,
            close=lambda fd: None,
            getpid=lambda: 502,
            O_PATH=8,
            O_DIRECTORY=4,
            O_CLOEXEC=2,
            O_NOFOLLOW=1,
        ),
    )
    state = {}

    def syscall(number, *args):
        if number == 444 and args[-1] == 1:
            return 5
        if number == 444:
            state["handled"] = ctypes.cast(args[0], ctypes.POINTER(ctypes.c_uint64)).contents.value
            return 75
        if number == 445:

            class Rule(ctypes.Structure):
                _pack_ = 1
                _fields_ = [("access", ctypes.c_uint64), ("fd", ctypes.c_int32)]

            rule = ctypes.cast(args[2], ctypes.POINTER(Rule)).contents
            rules.append((paths[rule.fd], rule.access))
        return 0

    monkeypatch.setattr(r.ctypes, "CDLL", lambda *a, **kw: SimpleNamespace(syscall=syscall))
    monkeypatch.setattr(r, "_libcall", lambda *a: None)
    r._landlock()

    def allowed(path, right):
        return not state["handled"] & right or any(
            (path == root or path.startswith(root + "/")) and bits & right for root, bits in rules
        )

    for path in (
        "/root/.aws/credentials",
        "/root/.com.moomoo.OpenD/account.key",
        "/proc/502/environ",
        "/etc/private-key",
    ):
        assert not allowed(path, 4), path
    assert allowed("/source/ivv_trusted_runner.py", 4)
    assert allowed("/sdk/moomoo/__init__.py", 4)
    assert allowed("/output/capture/plain.json", 2)
    assert not allowed("/source/ivv_trusted_runner.py", 2)
    assert not allowed("/usr/bin/python3.12", 1)


@pytest.mark.parametrize("drift", [False, True])
def test_bootstrap_authenticates_same_held_release_bytes_before_helpers(
    tmp_path, monkeypatch, drift
):
    check_bootstrap(tmp_path, monkeypatch, drift)


def check_bootstrap(tmp_path, monkeypatch, drift, *, additional=None):
    import sys

    from test_ivv_dev_diagnostic import kernel_fixture

    _, _, _, _, kwargs, _ = kernel_fixture(tmp_path, monkeypatch)
    r = runner()
    release = tmp_path / "release"
    release.mkdir()
    controls = tmp_path / "parent"
    controls.mkdir()
    catalog = {}
    for key, name in r._sources(bool(additional)).items():
        raw = (Path(r.__file__).parent / name).read_bytes()
        (release / name).write_bytes(raw)
        catalog[key] = hashlib.sha256(raw).hexdigest()

    def put(path, value):
        path.write_bytes(r.raw_json(value))
        return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    startup = {"catalog_ref": put(release / "release-catalog.json", catalog)}
    for key, name, value in (
        ("seed_ref", "plan-seed.json", {}),
        ("budget_ref", "budget.json", {}),
        ("authorization_ref", "authorization.json", {"fictional human": True}),
        ("go_fields_ref", "windows-go-fields.json", {}),
    ):
        startup[key] = put(controls / name, value)
    if additional:
        from test_ivv_additional_task import private_inputs

        original_open = os.open
        monkeypatch.setattr(
            os,
            "open",
            lambda path, flags, *a, **kw: original_open(
                path, flags | getattr(os, "O_BINARY", 0), *a, **kw
            ),
        )
        originals = private_inputs()
        for (key, name), raw in zip(
            (
                ("authorization_ref", "authorization.json"),
                ("descriptor_ref", "descriptor.json"),
                ("capture_policy_ref", "policy.json"),
                ("windows_policy_ref", "windows-policy.json"),
            ),
            originals,
            strict=True,
        ):
            path = controls / name
            path.write_bytes(raw)
            startup[key] = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}
        monkeypatch.setattr(r, "__file__", str(release / "ivv_trusted_runner.py"))
        original_locations = r._locations
        monkeypatch.setattr(r, "_locations", lambda additional: original_locations(False))
    ref = put(controls / "startup.json", startup)
    monkeypatch.setattr(r, "AUTH", startup["authorization_ref"]["sha256"])
    monkeypatch.setattr(r, "RELEASE", release)
    monkeypatch.setattr(r, "CONTROL", controls)
    monkeypatch.setattr(r, "SDK", tmp_path / "sdk")
    monkeypatch.setattr(
        r,
        "sys",
        SimpleNamespace(
            platform="linux",
            flags=SimpleNamespace(isolated=True, no_site=True),
            dont_write_bytecode=True,
            modules={},
            exc_info=sys.exc_info,
        ),
    )
    monkeypatch.setattr(os, "lstat", lambda path, **kw: os.stat(path, **kw))
    monkeypatch.setattr(r, "_private_mounts", lambda: 44)
    mounts = []
    monkeypatch.setattr(r, "_bind", lambda path: mounts.append(str(path)))
    monkeypatch.setattr(r, "_attr", lambda path, readonly, recursive: None)
    if drift:
        (release / "ivv_trusted_runner.py").write_bytes(
            b"raise RuntimeError('untrusted code must not run')"
        )
        with pytest.raises(r.Refused, match="CONTROL_DIGEST"):
            r._bootstrap(ref)
    else:
        context = r._bootstrap(ref, additional=bool(additional))
        if additional:
            assert (
                context[1]["_additional"].APPROVED.authorization_sha256
                == startup["authorization_ref"]["sha256"]
            )
        assert context[3].capture_trusted_once is not None
        assert context[5].PosixReader is not None
        assert mounts == [
            str(release),
            str(tmp_path / "sdk"),
            str(Path("/usr/lib")),
            str(Path("/usr/bin")),
        ]


@pytest.mark.parametrize(
    "fault", ["monitor", "crash", "nonzero", "foreign", "event", "manager", "control", "terminal"]
)
def test_supervisor_cannot_seal_uncertain_child_or_monitor(monkeypatch, fault):
    r = runner()
    scope, kernel = owned_scope(r, monkeypatch)
    helper = leaf()
    monitor = SimpleNamespace(next=0, last={})

    def sample():
        if fault == "monitor":
            raise r.Refused("MONITOR_FAILED")
        monitor.next = 5

    monitor.sample = sample
    monkeypatch.setattr(r, "_Provider", lambda *a: monitor)
    monkeypatch.setattr(r, "_authorize", lambda *a: ({}, {}, {}, {}))
    monkeypatch.setattr(r, "_child_kernel", lambda *a: {"namespace_inode": 44})
    monkeypatch.setattr(r, "_owned_peer", lambda *a: (1, 2))
    monkeypatch.setattr(r.time, "monotonic", lambda: 0)
    packets = [{"op": "ready"}, {"op": "observe"}]
    if fault != "terminal":
        packets.append({"op": "terminal", "permit_sha256": "1" * 64, "manifest_sha256": "2" * 64})

    def check():
        if fault == "control":
            raise r.Refused("CONTROL_FD_SWAPPED")

    channel = SimpleNamespace(
        send=lambda packet: None,
        recv=lambda pid: (
            packets.pop(0) if packets else (_ for _ in ()).throw(r.Refused("CONTROL_EOF"))
        ),
        check=check,
        s=SimpleNamespace(recv=lambda *a: b""),
    )

    def ready(*a):
        if packets:
            return [channel.s], [], []
        leaf = kernel.handles[scope.leaf]
        kernel.nodes[leaf + "/cgroup.procs"]["content"] = "999" if fault == "foreign" else ""
        if fault == "event":
            kernel.nodes[leaf + "/memory.events"]["content"] = "oom_kill 1"
        if fault == "manager":
            monkeypatch.setattr(r, "_manager_contract", lambda parent: {"InvocationID": "2" * 32})
        return [scope.pidfd], [], []

    monkeypatch.setattr(r, "select", SimpleNamespace(select=ready))
    monkeypatch.setattr(r.socket, "MSG_DONTWAIT", 64, raising=False)
    kernel.os.waitid = lambda *a: SimpleNamespace(
        si_pid=502, si_code=2 if fault == "crash" else 1, si_status=1 if fault == "nonzero" else 0
    )

    def forbidden(*args):
        pytest.fail("uncertain kernel/provider state reached parent seal")

    monkeypatch.setattr(r, "_seal", forbidden)
    context = ({"budget_ref": {}}, {}, None, helper, None, None)
    with pytest.raises(r.Refused):
        r._supervise(scope, channel, 700, context, {"started_monotonic": 0})


@pytest.mark.parametrize(
    "case", ["pidfd_first", "terminal_after390", "parent_work", "reap_work", "over480"]
)
def test_r1_terminal_exit_and_parent_deadlines_are_independent(monkeypatch, case):
    r = runner()
    scope, kernel = owned_scope(r, monkeypatch)
    clock = {"now": 0.0, "step": 0}
    if case == "reap_work":
        prior_reap = scope.reap

        def slow_reap():
            rc = prior_reap()
            clock["now"] = 465.0
            return rc

        scope.reap = slow_reap
    monkeypatch.setattr(r.time, "monotonic", lambda: clock["now"])
    monitor = SimpleNamespace(next=0, last={})

    def sample():
        monitor.next = 500
        if scope.reaped and case in ("parent_work", "over480"):
            clock["now"] = 465.0 if case == "parent_work" else 480.1

    monitor.sample = sample
    monkeypatch.setattr(r, "_Provider", lambda *a: monitor)
    monkeypatch.setattr(r, "_authorize", lambda *a: ({}, {}, {}, {}))
    monkeypatch.setattr(r, "_child_kernel", lambda *a: {"namespace_inode": 44})
    monkeypatch.setattr(r, "_owned_peer", lambda *a: (1, 2))
    packets = [{"op": "ready"}, {"op": "observe"}]
    if case == "terminal_after390":
        packets.append({"op": "observe"})
    packets.append({"op": "terminal", "permit_sha256": "1" * 64, "manifest_sha256": "2" * 64})

    def recv(pid):
        if packets:
            return packets.pop(0)
        raise r.Refused("CONTROL_EOF")

    channel = SimpleNamespace(
        send=lambda packet: None,
        recv=recv,
        check=lambda: None,
        s=SimpleNamespace(recv=lambda *a: b""),
    )

    def ready(*a):
        step = clock["step"]
        clock["step"] += 1
        if step < 2:
            return [channel.s], [], []
        if case == "terminal_after390" and step in (2, 3):
            clock["now"] = 390.05 if step == 2 else 390.1
            return [channel.s], [], []
        if step == 2 and case != "pidfd_first":
            clock["now"] = 419.8
            return [channel.s], [], []
        clock["now"] = (
            1.0 if case == "pidfd_first" else 391.0 if case == "terminal_after390" else 419.9
        )
        kernel.nodes[kernel.handles[scope.leaf] + "/cgroup.procs"]["content"] = ""
        return [scope.pidfd], [], []

    monkeypatch.setattr(r, "select", SimpleNamespace(select=ready))
    monkeypatch.setattr(r.socket, "MSG_DONTWAIT", 64, raising=False)
    monkeypatch.setattr(r, "_seal", lambda *args: {"elapsed_seconds": args[-1], "kernel": args[-4]})
    context = ({"budget_ref": {}}, {}, None, leaf(), None, None)
    if case == "over480":
        with pytest.raises(r.Refused, match="FINAL_SEAL_DEADLINE"):
            r._supervise(scope, channel, 700, context, {"started_monotonic": 0})
    else:
        result = r._supervise(scope, channel, 700, context, {"started_monotonic": 0})
        assert result["elapsed_seconds"] == (
            465.0 if case in ("parent_work", "reap_work") else clock["now"]
        )
        assert scope.reaped


def test_r1_run_once_keeps_total_events_through_publication(monkeypatch):
    r = runner()
    closed = []

    class Scope:
        def __init__(self, stack):
            self.leaf = 40
            stack.callback(closed.append, "total-events")

        def bind(self, pid):
            assert pid == 502

        def check_resources(self):
            assert not closed

        def check_final_resources(self):
            assert not closed

        def remove(self):
            pass

        def abort(self):
            return []

    class Socket:
        def close(self):
            pass

    monkeypatch.setattr(r, "_Scope", Scope)
    monkeypatch.setattr(r, "_bootstrap", lambda ref: ({}, {}, None, None, None, None))
    monkeypatch.setattr(r, "_seed", lambda *a: {"started_monotonic": 0})
    monkeypatch.setattr(r, "_stdio", lambda: None)
    monkeypatch.setattr(r, "_fds", lambda: {0, 1, 2})
    monkeypatch.setattr(r, "_Channel", lambda sock: SimpleNamespace(origin=(1, 700)))
    monkeypatch.setattr(r, "_supervise", lambda *a: {"state": "NORMAL_EXIT"})
    monkeypatch.setattr(
        r, "os", SimpleNamespace(umask=lambda mask: None, getpid=lambda: 501, fork=lambda: 502)
    )
    monkeypatch.setattr(r.socket, "socketpair", lambda *a: (Socket(), Socket()))
    monkeypatch.setattr(r.socket, "SOCK_SEQPACKET", 5, raising=False)
    monkeypatch.setattr(r.socket, "SOCK_CLOEXEC", 0, raising=False)
    monkeypatch.setattr(r.socket, "AF_UNIX", 1, raising=False)
    monkeypatch.setattr(r.time, "monotonic", lambda: 1.0)
    prior = Path.iterdir
    monkeypatch.setattr(
        Path, "iterdir", lambda p: iter([1]) if p.as_posix() == "/proc/self/task" else prior(p)
    )
    published = []

    def publish(path, obj):
        assert not closed, "resource event handles ended before normal publication"
        published.append(obj)
        return {"path": str(path), "sha256": "1" * 64}

    monkeypatch.setattr(r, "put", publish)
    monkeypatch.setattr(r, "_commit_close", lambda ref: r.need(not closed, "EVENTS_CLOSED"))
    assert r.run_once({})["state"] == "NORMAL_EXIT"
    assert len(published) == 1 and closed == ["total-events"]


def connected_acquisition_kernel(r, kernel, monkeypatch, tmp_path, local, d, m, real_d):
    """Map a literal Linux kernel into fixture files; no acquisition predicate is stubbed."""
    import ctypes
    import sys

    RealPath = Path
    Base = type(RealPath())
    home = tmp_path / "home"
    (home / ".com.moomoo.OpenD/Log").mkdir(parents=True)
    aliases = [
        ("/child", tmp_path / "child"),
        ("/sdk", tmp_path / "sdk"),
        ("/home", home),
        ("/once", m.ONCE_LEDGER),
        ("/usr", tmp_path / "usr"),
        ("/source", RealPath(r.__file__).parent),
        ("/controls", tmp_path),
    ]
    state = SimpleNamespace(
        namespace=40,
        nnp=0,
        caps=1,
        connected=False,
        runtime_reads=0,
        bound_mounts=[],
        readonly={},
        fds={0, 1, 2, 6000, 6001, *kernel.handles},
        rules={},
        nextfd=8001,
    )

    def child():
        return getattr(local, "child", False)

    class KernelPath(Base):
        def __init__(self, *args):
            super().__init__(*_kernel_path_arguments(args, aliases, RealPath))

        def __new__(cls, *args):
            return super().__new__(cls, *_kernel_path_arguments(args, aliases, RealPath))

        def real(self):
            return RealPath(Base.__str__(self))

        def is_absolute(self):
            return bool(self.drive and self.root) or str(self).startswith("/")

        def __str__(self):
            raw = Base.__str__(self)
            actual = RealPath(raw)
            for logical, root in aliases:
                if actual == root or actual.is_relative_to(root):
                    tail = actual.relative_to(root).as_posix()
                    return logical + ("/" + tail if tail != "." else "")
            return raw.replace("\\", "/") if raw.startswith("\\") else raw

        def resolve(self, strict=False):
            name = str(self)
            if name in ("/proc/self/exe", "/proc/502/exe"):
                return KernelPath("/usr/bin/python3.12")
            if name.startswith(("/proc/", "/sys/", "/etc/")):
                return self
            return KernelPath(self.real().resolve(strict=strict))

        def stat(self, *, follow_symlinks=True):
            name = str(self)
            if name.endswith("ns/mnt"):
                ns = state.namespace if "/502/" in name or child() else 40
                return SimpleNamespace(st_ino=ns)
            if name.endswith("/exe") and name.startswith("/proc/"):
                return os.stat(tmp_path / "usr/bin/python3.12")
            if "/fd/" in name and name.startswith("/proc/"):
                fd = int(self.name)
                inode = 102 if "/705711/" in name else 101 if fd == 500 else fd
                return SimpleNamespace(
                    st_dev=77,
                    st_ino=inode,
                    st_uid=0,
                    st_rdev=259,
                    st_mode=stat.S_IFCHR | 0o600 if fd in (0, 1, 2) else stat.S_IFSOCK | 0o600,
                )
            if name.startswith("/sys/fs/cgroup"):
                return kernel.os.stat(self)
            if name.startswith(("/proc/", "/etc/")):
                directory = name in ("/proc", "/proc/self", "/proc/502", "/etc")
                return SimpleNamespace(
                    st_dev=77,
                    st_ino=100,
                    st_uid=0,
                    st_nlink=1,
                    st_mode=(stat.S_IFDIR | 0o700) if directory else stat.S_IFREG | 0o444,
                )
            return os.stat(self.real(), follow_symlinks=follow_symlinks)

        def lstat(self):
            return self.stat(follow_symlinks=False)

        def exists(self):
            return str(self).startswith(("/proc/", "/sys/", "/etc/")) or self.real().exists()

        def is_dir(self):
            return stat.S_ISDIR(self.stat().st_mode)

        def is_symlink(self):
            return (
                False
                if str(self).startswith(("/proc/", "/sys/", "/etc/"))
                else self.real().is_symlink()
            )

        def read_bytes(self):
            name = str(self)
            if name.endswith("/mountinfo"):

                def modes(path):
                    return "ro" if state.readonly.get(path, False) else "rw"

                return (
                    f"1 99 8:1 / / {modes('/')} - ext4 /dev/root rw\n"
                    f"2 1 8:1 /child /child {modes('/child')} - ext4 /dev/root rw\n"
                    f"3 1 8:1 /once /once {modes('/once')} - ext4 /dev/root rw\n"
                ).encode()
            if name.endswith("/net/tcp"):
                rows = (
                    ""
                    if not state.connected
                    else (
                        "0: 0100007F:4444 0100007F:2B68 01 0 0 0 0 0 101\n"
                        "1: 0100007F:2B68 0100007F:4444 01 0 0 0 0 0 102\n"
                    )
                )
                return ("header\n" + rows).encode()
            state.runtime_reads += 1
            return self.real().read_bytes()

        def read_text(self, *a, **kw):
            name = str(self)
            if name == "/proc/self/fdinfo/90":
                return "Pid:\t502\n"
            if name.endswith("cap_last_cap"):
                return "40"
            if name.endswith("/status"):
                return (
                    "NoNewPrivs:\t"
                    + str(state.nnp)
                    + "\n"
                    + "\n".join(
                        k + ":\t" + str(state.caps)
                        for k in ("CapEff", "CapPrm", "CapInh", "CapBnd", "CapAmb")
                    )
                )
            if name.startswith("/sys/fs/cgroup/"):
                return kernel.nodes[name]["content"]
            return self.real().read_text(*a, **kw)

        def iterdir(self):
            name = str(self)
            if name == "/proc/502/fd":
                return iter(
                    [self / str(fd) for fd in state.fds | ({500} if state.connected else set())]
                )
            if name == "/proc/705711/fd":
                return iter([self / "550"])
            return iter([KernelPath(p) for p in self.real().iterdir()])

        def mkdir(self, *a, **kw):
            return self.real().mkdir(*a, **kw)

        def write_bytes(self, data):
            return self.real().write_bytes(data)

        def open(self, *a, **kw):
            return self.real().open(*a, **kw)

    state.Path = KernelPath
    before_open, before_close, before_fstat, before_stat = (
        kernel.os.open,
        kernel.os.close,
        kernel.os.fstat,
        kernel.os.stat,
    )
    raw_open = os.open

    def opened(path, flags, mode=0o777, *, dir_fd=None):
        p = KernelPath(path) if dir_fd is None else None
        name = str(p) if p is not None else str(path)
        if flags & 2097152:
            fd = state.nextfd
            state.nextfd += 1
            state.rules[fd] = name
            state.fds.add(fd)
            return fd
        if name == "/dev/null":
            state.fds.add(7999)
            return 7999
        if name.startswith("/sys/fs/cgroup") or dir_fd is not None:
            return before_open(path, flags, mode, dir_fd=dir_fd)
        fd = raw_open(p.real(), flags | getattr(os, "O_BINARY", 0), mode)
        if child():
            state.fds.add(fd)
        return fd

    def close(fd):
        if child() and (
            fd in kernel.handles or fd in (6000, 6001, 7999, 8000) or fd in state.rules
        ):
            state.fds.discard(fd)
            return
        if child():
            state.fds.discard(fd)
        return before_close(fd)

    def fstat(fd):
        if fd in (0, 1, 2, 7999):
            return SimpleNamespace(
                st_mode=stat.S_IFCHR | 0o600, st_rdev=259, st_dev=77, st_ino=fd, st_uid=0
            )
        return before_fstat(fd)

    kernel.os.open, kernel.os.close, kernel.os.fstat = opened, close, fstat
    kernel.os.stat = lambda path, **kw: (
        before_stat(path, **kw)
        if "dir_fd" in kw or str(path).replace("\\", "/").startswith("/sys/fs/cgroup")
        else KernelPath(path).stat(**kw)
    )
    kernel.os.listdir = lambda path: list(map(str, state.fds))
    kernel.os.dup2 = lambda *a, **kw: None
    kernel.os.makedev = lambda a, b: (a << 8) | b
    kernel.os.fsencode = lambda path: os.fsencode(str(path))
    kernel.os.uname = lambda: SimpleNamespace(machine="x86_64")
    kernel.os.environ = {"HOME": "/home"}
    kernel.os.ST_RDONLY = 1
    kernel.os.statvfs = lambda path: SimpleNamespace(f_flag=1, f_bavail=100000000000, f_frsize=1)
    kernel.os.fstatvfs = lambda fd: SimpleNamespace(f_flag=1)
    kernel.os.O_PATH = 2097152
    kernel.os.O_RDWR = 2

    def libcall(name, *args):
        if name == "unshare":
            state.namespace = 44
        elif name == "mount":
            state.bound_mounts.append(args)
        elif name == "prctl" and args[:2] == (38, 1):
            state.nnp = 1
        elif name == "capset":
            state.caps = 0
        elif name == "syscall":
            attr = ctypes.cast(args[4], ctypes.POINTER(r._MountAttr)).contents
            path = args[2].decode()
            if path == "/" and args[3] == 0x8000:
                state.readonly.update({key: True for key in ("/", "/child", "/once")})
            state.readonly[path] = bool(attr.set)

    def syscall(number, *args):
        if number == 444 and args[-1] == 1:
            return 5
        if number == 444:
            state.fds.add(8000)
            return 8000
        return 0

    monkeypatch.setattr(r, "_libcall", libcall)
    monkeypatch.setattr(r.ctypes, "CDLL", lambda *a, **kw: SimpleNamespace(syscall=syscall))
    for owner in (r, m, d):
        monkeypatch.setattr(owner, "Path", KernelPath)
    for name, value in (
        ("CONTROL", tmp_path),
        ("CHILD", tmp_path / "child"),
        ("RECEIPT", tmp_path / "child/capture"),
        ("LEDGER", m.ONCE_LEDGER),
        ("SDK", tmp_path / "sdk"),
        ("RELEASE", RealPath(r.__file__).parent),
    ):
        monkeypatch.setattr(r, name, KernelPath(value))
    for owner in (m, d, real_d):
        proxy = {name: getattr(os, name) for name in dir(os)}
        proxy.update(open=opened, close=close, stat=kernel.os.stat, fstat=fstat, getpid=lambda: 502)
        monkeypatch.setattr(owner, "os", SimpleNamespace(**proxy))
    proxy = {name: getattr(sys, name) for name in dir(sys)}
    proxy.update(
        path=["/usr/lib/python3.12", str(r.SDK)],
        executable="/usr/bin/python3.12",
        version_info=(3, 12),
    )
    monkeypatch.setattr(r, "sys", SimpleNamespace(**proxy))
    monkeypatch.setattr(
        r.importlib.machinery.PathFinder,
        "find_spec",
        lambda *a: SimpleNamespace(origin=str(r.SDK / "moomoo/__init__.py")),
    )
    # The scripted SDK controls only the modeled socket's kernel lifetime.
    original = m._OfficialBackend

    def backend(*args):
        obj = original(*args)
        opening, closing = obj.open, obj.close

        def connected():
            opening()
            state.connected = True

        def disconnected():
            closing()
            state.closed_at = obj.clock.value
            state.connected = False

        obj.open, obj.close = connected, disconnected
        return obj

    monkeypatch.setattr(m, "_OfficialBackend", backend)
    return state


@pytest.mark.parametrize(
    "fault", ["normal", "json_event", "commit_event", "fsync", "close", "both", "over480"]
)
def test_r1_real_run_once_publication_rejects_late_events_and_close_uncertainty(
    tmp_path, monkeypatch, fault
):
    from test_ivv_dev_diagnostic import kernel_fixture

    kernel_fixture(tmp_path, monkeypatch)
    r = runner()
    _, kernel = owned_scope(r, monkeypatch, create=False)
    monkeypatch.setattr(r, "CONTROL", tmp_path)
    monkeypatch.setattr(os, "lstat", lambda path, **kw: os.stat(path, **kw))
    monkeypatch.setattr(r, "_bootstrap", lambda ref: ({}, {}, None, None, None, None))
    monkeypatch.setattr(r, "_seed", lambda *a: {"started_monotonic": 0})
    monkeypatch.setattr(r, "_stdio", lambda: None)
    monkeypatch.setattr(r, "_fds", lambda: {0, 1, 2})
    clock = {"now": 1.0}
    monkeypatch.setattr(r.time, "monotonic", lambda: clock["now"])
    prior = Path.iterdir
    monkeypatch.setattr(
        Path, "iterdir", lambda p: iter([1]) if p.as_posix() == "/proc/self/task" else prior(p)
    )
    kernel.os.umask = lambda mode: None
    kernel.os.fork = lambda: 502
    kernel.os.fsencode = os.fsencode
    original_stat = kernel.os.fstat
    kernel.os.fstat = lambda fd: (
        SimpleNamespace(st_dev=77, st_ino=fd, st_mode=stat.S_IFSOCK | 0o600, st_uid=0)
        if fd in (6000, 6001)
        else original_stat(fd)
    )

    class Socket:
        type = 5

        def __init__(self, fd):
            self.fd = fd

        def fileno(self):
            return self.fd

        def setsockopt(self, *args):
            pass

        def settimeout(self, *args):
            pass

        def close(self):
            pass

    for key, value in (
        ("AF_UNIX", 1),
        ("SO_PASSCRED", 16),
        ("SOCK_SEQPACKET", 5),
        ("SOCK_CLOEXEC", 0),
    ):
        monkeypatch.setattr(r.socket, key, value, raising=False)
    monkeypatch.setattr(r.socket, "socketpair", lambda *a: (Socket(6000), Socket(6001)))
    saved = {}

    def closed_capture(scope, *args):
        assert scope.reap() == 0
        kernel.nodes[kernel.handles[scope.leaf] + "/cgroup.procs"]["content"] = ""
        scope.empty()
        scope.check_resources()
        saved["scope"] = scope
        return {"state": "NORMAL_EXIT", "resource_limit_event": False}

    monkeypatch.setattr(r, "_supervise", closed_capture)
    syncs = []

    def sync(path):
        # Both serialization fsync and commit fsync run with TOTAL event FDs held.
        scope = saved["scope"]
        if not (tmp_path / "parent-close.rejected.json").exists():
            assert all(fd in kernel.handles for fd in scope.events)
        syncs.append(str(path))
        if (fault == "json_event" and len(syncs) == 1) or (
            fault in ("commit_event", "both") and len(syncs) == 2
        ):
            kernel.nodes["/sys/fs/cgroup/system.slice/owned.service/memory.events"]["content"] = (
                "oom_kill 1"
            )
        if fault == "fsync" and len(syncs) == 2:
            raise OSError("simulated directory fsync")
        if fault == "over480" and len(syncs) == 2:
            clock["now"] = 480.1

    monkeypatch.setattr(r, "_sync_dir", sync)

    def call(name, *args):
        assert name == "renameat2" and args[0] == args[2] == -100 and args[4] == 1
        source, target = os.fsdecode(args[1]), os.fsdecode(args[3])
        assert Path(source).parent == Path(target).parent == tmp_path
        if Path(target).exists():
            raise FileExistsError(target)
        os.rename(source, target)

    monkeypatch.setattr(r, "_libcall", call)
    original_close = kernel.os.close
    failed = {"done": False}

    def close(fd):
        scope = saved.get("scope")
        if (
            fault in ("close", "both")
            and scope
            and fd == scope.total_events[0]
            and not failed["done"]
        ):
            failed["done"] = True
            original_close(fd)
            raise OSError("simulated retained close")
        original_close(fd)

    kernel.os.close = close
    if fault == "normal":
        assert r.run_once({})["state"] == "NORMAL_EXIT"
        assert (tmp_path / "parent-close.json").exists()
    else:
        with pytest.raises(r.Refused) as exc:
            r.run_once({})
        assert "SEAL_RETIRE" not in str(exc.value)
        assert not (tmp_path / "parent-close.json").exists()
        assert not (tmp_path / "parent-close.pending.json").exists()
        assert (
            json.loads((tmp_path / "parent-close.rejected.json").read_bytes())["state"]
            == "NORMAL_EXIT"
        )
        if fault == "both":
            assert "RESOURCE_LIMIT_EVENT" in str(exc.value) and "CLOSE_OSError" in str(exc.value)
    assert not kernel.handles
