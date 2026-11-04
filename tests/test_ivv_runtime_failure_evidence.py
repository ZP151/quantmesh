"""Offline failure evidence: actual runner bodies, modeled external boundaries only."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def runner():
    spec = importlib.util.spec_from_file_location(
        "origin_runner", ROOT / "tools/research/ivv_trusted_runner.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evidence(phase="INITIAL", predicate="SDK_ROOT", outcome="FIRST_FALSE"):
    return {
        "schema": "qm.ivv.runtime-origin-failure.v1",
        "phase": phase,
        "predicate": predicate,
        "outcome": outcome,
    }


def origin_seams(r, monkeypatch, target, result=False, error=None, where="comparison"):
    calls = []

    class Value:
        def __init__(self, name):
            self.name = name
            self.n = 0

        def __eq__(self, other):
            calls.append(("eq", self.name))
            if self.name == target and error is not None and where == "comparison":
                raise error
            return self

        def __bool__(self):
            self.n += 1
            calls.append(("bool", self.name, self.n))
            if self.name == target:
                if error is not None and where == "truth":
                    raise error
                return result(self.n) if callable(result) else result
            return True

    values = {name: Value(name) for name in ("SDK_ROOT", "PYTHON_VERSION", "EXECUTABLE")}

    class Plan:
        def __getitem__(self, key):
            calls.append(("lookup", "SDK_ROOT"))
            if target == "SDK_ROOT" and error is not None and where == "lookup":
                raise error
            return values["SDK_ROOT"]

    class Version:
        def __getitem__(self, key):
            calls.append(("lookup", "PYTHON_VERSION"))
            if target == "PYTHON_VERSION" and error is not None and where == "lookup":
                raise error
            return values["PYTHON_VERSION"]

    class P:
        def __init__(self, path):
            self.path = path

        def resolve(self):
            calls.append(("lookup", "EXECUTABLE"))
            if target == "EXECUTABLE" and error is not None and where == "lookup":
                raise error
            return values["EXECUTABLE"]

    monkeypatch.setattr(r, "Path", P)
    monkeypatch.setattr(
        r, "os", SimpleNamespace(stat=lambda p: SimpleNamespace(st_ino=44), environ={})
    )
    monkeypatch.setattr(r, "_writable_mounts", lambda p: None)
    monkeypatch.setattr(r, "sys", SimpleNamespace(version_info=Version()))
    return Plan(), calls


@pytest.mark.parametrize("phase", ["INITIAL", "SESSION", "UNKNOWN"])
@pytest.mark.parametrize("predicate", ["SDK_ROOT", "PYTHON_VERSION", "EXECUTABLE"])
@pytest.mark.parametrize("exception", [False, True])
def test_actual_origin_short_circuit_evidence(monkeypatch, phase, predicate, exception):
    r = runner()
    original = r.Refused("RUNTIME_ORIGIN") if exception else None
    plan, calls = origin_seams(r, monkeypatch, predicate, error=original)
    with pytest.raises(r.Refused) as caught:
        r._runtime(plan, None, 44, {}, None, origin_phase=phase)
    if original is not None:
        assert caught.value is original
        assert caught.value.args == ("RUNTIME_ORIGIN",)
    actual = getattr(caught.value, "_qm_origin_failure", None)
    assert actual == evidence(phase, predicate, "EXCEPTION" if exception else "FIRST_FALSE")
    names = ["SDK_ROOT", "PYTHON_VERSION", "EXECUTABLE"]
    assert [row[1] for row in calls if row[0] == "lookup"] == names[: names.index(predicate) + 1]
    assert "private" not in json.dumps(actual)


def test_stateful_truth_and_bool_exception_preserve_original(monkeypatch):
    r = runner()
    private = RuntimeError("private account/path", 17)

    def truth(n):
        if n == 2:
            raise private
        return False

    plan, calls = origin_seams(r, monkeypatch, "SDK_ROOT", result=truth)
    with pytest.raises(RuntimeError) as caught:
        r._runtime(plan, None, 44, {}, None, origin_phase="INITIAL")
    assert caught.value is private and caught.value.args == ("private account/path", 17)
    assert calls == [
        ("lookup", "SDK_ROOT"),
        ("eq", "SDK_ROOT"),
        ("bool", "SDK_ROOT", 1),
        ("bool", "SDK_ROOT", 2),
    ]
    assert getattr(private, "_qm_origin_failure", None) == evidence(outcome="EXCEPTION")


def test_legacy_and_malformed_origin_payloads():
    r = runner()
    assert r.select_origin_failure(None) is None
    for value in (
        {},
        {**evidence(), "private": "secret"},
        {**evidence(), "phase": True},
        {**evidence(), "outcome": "GUESS"},
        {**evidence(), "predicate": "UNKNOWN"},
    ):
        with pytest.raises(ValueError):
            r.select_origin_failure(value)
    status = {
        "state": "STOP",
        "publication_sha256": "a" * 64,
        "stage": "RELEASED_ADDITIONAL_RUNNER_ONCE",
        "automatic_retry": False,
        "provider_mutation": False,
        "unit_returncode": 1,
        "reason": "RUNTIME_ORIGIN",
        "actual_contexts": 0,
    }
    selected = r.select_failure_status({**status, "origin_failure": evidence()}, "a" * 64)
    assert selected["actual_contexts"] == "UNKNOWN"
    assert selected["origin_failure"] == evidence()
    assert "origin_failure" not in r.select_failure_status(status, "a" * 64)
    with pytest.raises(ValueError):
        r.select_failure_status({**status, "origin_failure": {"private": "secret"}}, "a" * 64)


def test_lookup_exception_messages_never_enter_failure_record(monkeypatch):
    r = runner()
    secret = ValueError("PRIVATE_ACCOUNT_IDENTIFIER")
    plan, _ = origin_seams(r, monkeypatch, "SDK_ROOT", error=secret)
    with pytest.raises(ValueError) as caught:
        r._runtime(plan, None, 44, {}, None)
    assert caught.value is secret
    record = r._failure_record(secret)
    assert record["reason"] == "ValueError"
    assert "PRIVATE" not in json.dumps(record)


def test_actual_child_initial_phase(monkeypatch):
    r = runner()
    plan, _ = origin_seams(r, monkeypatch, "SDK_ROOT")
    r.sys.path = []
    monkeypatch.setattr(r, "_bind_parent", lambda pid: None)
    monkeypatch.setattr(r, "_child_namespace", lambda *a: 44)
    monkeypatch.setattr(r, "_environment", lambda: None)
    channel = SimpleNamespace(recv=lambda parent: {"op": "enter"})
    context = ({}, {"catalog_ref": {}}, None, None, None, None)
    with pytest.raises(r.Refused) as caught:
        r._child(channel, 11, context, plan)
    assert r._origin_from_error(caught.value) == evidence()


def test_actual_child_session_callback_phase(monkeypatch):
    r = runner()
    checked = []

    class Stop(BaseException):
        pass

    def runtime(*args, **kw):
        checked.append(kw.get("origin_phase"))

    monkeypatch.setattr(r, "_runtime", runtime)
    monkeypatch.setattr(r, "_bind_parent", lambda pid: None)
    monkeypatch.setattr(r, "_child_namespace", lambda *a: 44)
    monkeypatch.setattr(r, "_environment", lambda: None)

    def session(channel, parent, check):
        check()
        raise Stop()

    monkeypatch.setattr(r, "_ChildSession", session)
    monkeypatch.setattr(r, "sys", SimpleNamespace(path=[], modules={}))
    plan = {"provider_evidence_ref": {}}
    replies = iter([{"op": "enter"}, {"op": "go", "plan_ref": {}, "go_ref": {}}])
    channel = SimpleNamespace(recv=lambda parent: next(replies), send=lambda value: None)
    m = SimpleNamespace(
        _native_actor=lambda: {}, _admit_material=lambda *a: None, _strict_json=lambda raw: plan
    )
    monkeypatch.setattr(r, "read_ref", lambda *a: b"{}")
    context = ({}, {"catalog_ref": {}, "budget_ref": {}}, None, m, None, None)
    with pytest.raises(Stop):
        r._child(channel, 11, context, plan)
    assert checked == ["INITIAL", "SESSION"]


@pytest.mark.parametrize("ordering", ["channel", "pidfd", "both", "absent", "eof", "malformed"])
def test_real_child_ipc_parent_wrap_main_reader_selector(
    monkeypatch, ordering, executable_case=None
):
    if executable_case is None:
        r = runner()
        plan, _ = origin_seams(r, monkeypatch, "EXECUTABLE")
        with pytest.raises(r.Refused) as caught:
            r._runtime(plan, None, 44, {}, None, origin_phase="SESSION")
        original = caught.value
        expected_origin = evidence("SESSION", "EXECUTABLE")
    else:
        r, original, expected_origin = executable_case
    packets, written = [], []
    phase = {"child": True}

    class P:
        def __init__(self, name):
            self.name = name

        def __truediv__(self, name):
            return P(self.name + "/" + name)

        def iterdir(self):
            return iter([1])

        def exists(self):
            return bool(written)

    class S:
        type = 5

        def close(self):
            pass

        def fileno(self):
            return 10 if self is b else 9

        def setsockopt(self, *args):
            pass

        def settimeout(self, value):
            self.timeout = value

        def gettimeout(self):
            return self.timeout

        def send(self, raw):
            if self is b:
                packets.append(raw)
            return len(raw)

        def recvmsg(self, *args):
            import struct

            if ordering in ("pidfd", "absent", "eof", "malformed"):
                assert len(args) == 3 and args[2] == 64 and self.timeout == 0
            if ordering == "eof":
                return b"", [], 0, None
            if not packets:
                raise BlockingIOError()
            return packets.pop(0), [(1, 2, struct.pack("3i", 502, 0, 0))], 0, None

    class Scope:
        def __init__(self, stack):
            self.pid, self.pidfd = 502, 8
            stack.callback(lambda: None)

        def bind(self, pid):
            assert pid == 502

        def check_pid(self):
            pass

        def check_resources(self):
            pass

        def reap(self):
            return 1

        def abort(self):
            return ["CLEANUP_UNKNOWN"]

    a, b = S(), S()

    def exit_child(rc):
        raise SystemExit(rc)

    monkeypatch.setattr(r, "Path", P)
    monkeypatch.setattr(r, "_locations", lambda additional: SimpleNamespace(control=P("/parent")))
    monkeypatch.setattr(r, "_Scope", Scope)
    monkeypatch.setattr(
        r, "_bootstrap", lambda ref: ({"budget_ref": {}}, {}, None, None, None, None)
    )
    monkeypatch.setattr(r, "_seed", lambda *a: {"started_monotonic": 0})
    monkeypatch.setattr(r, "_stdio", lambda: None)
    monkeypatch.setattr(r, "_fds", lambda: {0, 1, 2})
    monkeypatch.setattr(r, "_child", lambda *a: (_ for _ in ()).throw(original))
    monkeypatch.setattr(
        r,
        "os",
        SimpleNamespace(
            umask=lambda n: None,
            getpid=lambda: 501,
            fork=lambda: 0 if phase["child"] else 502,
            _exit=exit_child,
            fstat=lambda fd: SimpleNamespace(st_dev=1, st_ino=fd, st_mode=0, st_uid=0),
        ),
    )
    monkeypatch.setattr(
        r,
        "socket",
        SimpleNamespace(
            socketpair=lambda *a: (a_socket, b_socket),
            AF_UNIX=1,
            SOCK_SEQPACKET=5,
            SOCK_CLOEXEC=0,
            SOL_SOCKET=1,
            SO_PASSCRED=3,
            SCM_CREDENTIALS=2,
            CMSG_SPACE=lambda n: n,
            MSG_DONTWAIT=64,
        ),
    )
    a_socket, b_socket = a, b
    monkeypatch.setattr(r, "time", SimpleNamespace(monotonic=lambda: 1))
    monkeypatch.setattr(
        r,
        "select",
        SimpleNamespace(
            select=lambda *a: (
                [a_socket]
                if ordering == "channel"
                else [a_socket, 8]
                if ordering == "both"
                else [8],
                [],
                [],
            )
        ),
    )
    monkeypatch.setattr(r, "_Provider", lambda *a: SimpleNamespace(next=10))
    monkeypatch.setattr(r, "put", lambda path, value: written.append(r.raw_json(value)))
    # Fake _exit unwinds; the real child branch has already serialized its IPC.
    with pytest.raises(r.Refused):
        r._run({}, additional=False)
    assert json.loads(packets[0])["origin_failure"] == expected_origin
    if ordering == "absent":
        packets.clear()
    elif ordering == "malformed":
        packets[0] = (
            b'{"op":"failed","code":"RUNTIME_ORIGIN","origin_failure":{"secret":"PRIVATE"}}'
        )
    phase["child"] = False
    assert r.main(["0" * 64]) == 1
    assert a.timeout == 20
    record = r.read_runner_failure(P("/parent"), lambda path, maximum: written[-1])
    if ordering in ("absent", "eof", "malformed"):
        assert "origin_failure" not in record and "PRIVATE" not in json.dumps(record)
        assert record["reason"] == (
            "CHILD_TERMINAL_MISSING+CLEANUP_UNKNOWN"
            if ordering in ("absent", "eof")
            else "ORIGIN_FAILURE_SHAPE+CLEANUP_UNKNOWN"
        )
        return
    assert record["reason"] == "RUNTIME_ORIGIN+CLEANUP_UNKNOWN"
    status = {
        **record,
        "stage": "RELEASED_ADDITIONAL_RUNNER_ONCE",
        "unit_returncode": 1,
        "publication_sha256": "a" * 64,
        "actual_contexts": 0,
        "automatic_retry": False,
        "provider_mutation": False,
    }
    selected = r.select_failure_status(status, "a" * 64)
    assert selected["origin_failure"] == expected_origin
    assert selected["actual_contexts"] == "UNKNOWN"
    if executable_case is not None:
        return selected


def test_unowned_wellformed_exception_attribute_is_not_evidence():
    r = runner()
    foreign = r.Refused("OTHER_FAILURE")
    foreign._qm_origin_failure = evidence("SESSION", "EXECUTABLE")
    assert "origin_failure" not in r._failure_record(foreign)
    assert "origin_failure" not in r._failed_packet(foreign)


def test_explicit_null_child_metadata_is_not_a_legacy_packet():
    r = runner()
    with pytest.raises(ValueError):
        r._child_failure({"op": "failed", "code": "RUNTIME_ORIGIN", "origin_failure": None})


@pytest.mark.parametrize("phase", ["INITIAL", "SESSION", "UNKNOWN"])
@pytest.mark.parametrize("predicate", ["SDK_ROOT", "PYTHON_VERSION", "EXECUTABLE"])
@pytest.mark.parametrize("where", ["lookup", "truth"])
def test_actual_lookup_and_truth_exceptions_are_not_recomputed(
    monkeypatch, phase, predicate, where
):
    r = runner()
    error = PermissionError("PRIVATE_PATH", 19)
    plan, calls = origin_seams(r, monkeypatch, predicate, error=error, where=where)
    with pytest.raises(PermissionError) as caught:
        r._runtime(plan, None, 44, {}, None, origin_phase=phase)
    assert caught.value is error and error.args == ("PRIVATE_PATH", 19)
    assert r._origin_from_error(error) == evidence(phase, predicate, "EXCEPTION")
    assert r._failure_record(error)["reason"] == "PermissionError"
    order = ["SDK_ROOT", "PYTHON_VERSION", "EXECUTABLE"]
    assert [x[1] for x in calls if x[0] == "lookup"] == order[: order.index(predicate) + 1]


@pytest.mark.parametrize("flip", [False, True])
def test_later_runtime_failure_has_no_origin_attribution(monkeypatch, flip):
    r = runner()
    # A stateful false-then-true first comparison must retain the original two
    # truth tests, skip later operands, and pass need() exactly as before.
    plan, calls = origin_seams(
        r, monkeypatch, "SDK_ROOT" if flip else None, result=lambda n: n == 2
    )
    with pytest.raises(r.Refused, match="HOME_NOT_READY") as caught:
        r._runtime(plan, None, 44, {}, None, origin_phase="INITIAL")
    assert r._origin_from_error(caught.value) is None
    assert r._failure_record(caught.value) == {"state": "STOP", "reason": "HOME_NOT_READY"}
    assert len([row for row in calls if row[0] == "lookup"]) == (1 if flip else 3)


def test_session_reused_exception_gets_only_current_call_trace(monkeypatch):
    r = runner()
    error = ValueError("PRIVATE")
    for phase, predicate in (("INITIAL", "SDK_ROOT"), ("SESSION", "EXECUTABLE")):
        plan, _ = origin_seams(r, monkeypatch, predicate, error=error)
        with pytest.raises(ValueError) as caught:
            r._runtime(plan, None, 44, {}, None, origin_phase=phase)
        assert caught.value is error
        assert r._origin_from_error(error) == evidence(phase, predicate, "EXCEPTION")


def test_reader_legacy_unknown_duplicate_and_private_fields():
    r = runner()

    class P:
        def __truediv__(self, name):
            return self

        def exists(self):
            return True

    legacy = b'{"state":"STOP","reason":"OLD_CODE"}'
    assert r.read_runner_failure(P(), lambda p, n: legacy) == {
        "state": "STOP",
        "reason": "OLD_CODE",
    }
    for raw in (
        b'{"state":"STOP","reason":"OLD","reason":"PRIVATE"}',
        b'{"state":"STOP","reason":"OLD","private":"secret"}',
        b'{"state":"STOP","reason":"OLD","origin_failure":null}',
    ):
        with pytest.raises(ValueError):
            r.read_runner_failure(P(), lambda p, n: raw)
    unknown = evidence("UNKNOWN", "UNKNOWN", "UNKNOWN")
    assert r.select_origin_failure(unknown) == unknown


@pytest.mark.parametrize("hook", ["set", "get", "code", "descriptor"])
def test_metadata_never_invokes_exception_hooks_or_changes_args(monkeypatch, hook):
    r = runner()
    accesses = []

    class Hooked(Exception):
        def __setattr__(self, name, value):
            if name.startswith("_qm"):
                accesses.append(("set", name))
                BaseException.__setattr__(self, "args", ("CHANGED",))
                raise RuntimeError("setter")
            return BaseException.__setattr__(self, name, value)

        def __getattribute__(self, name):
            if name.startswith("_qm") and hook == "get":
                accesses.append(("get", name))
                raise RuntimeError("getter")
            if name == "_qm_origin_code" and hook == "code":
                accesses.append(("code", name))
                raise RuntimeError("code getter")
            return BaseException.__getattribute__(self, name)

        @property
        def _qm_origin_owner(self):
            accesses.append(("descriptor", "owner"))
            raise RuntimeError("descriptor")

    error = Hooked("ORIGINAL")
    plan, _ = origin_seams(r, monkeypatch, "SDK_ROOT", error=error)
    with pytest.raises(Hooked) as caught:
        r._runtime(plan, None, 44, {}, None, origin_phase="SESSION")
    assert caught.value is error and error.args == ("ORIGINAL",)
    assert r._failed_packet(error)["origin_failure"] == evidence("SESSION", "SDK_ROOT", "EXCEPTION")
    assert r._failure_code(error) == "ORIGIN_EVALUATION_EXCEPTION"
    assert accesses == []
    unowned = Hooked("UNOWNED")
    assert r._origin_from_error(unowned) is None
    assert "origin_failure" not in r._failed_packet(unowned)
    assert unowned.args == ("UNOWNED",) and accesses == []


def test_unsupported_exception_storage_is_declined_without_hooks(monkeypatch):
    r = runner()

    class Hooked(Exception):
        @property
        def __dict__(self):
            pytest.fail("custom dict descriptor invoked")

        def __getattr__(self, name):
            pytest.fail("custom missing getter invoked")

        def __setattr__(self, name, value):
            pytest.fail("custom setter invoked")

    error = Hooked("original")
    assert r._carry_origin(error, evidence()) is error
    assert r._origin_from_error(error) == evidence()
    monkeypatch.setattr(r, "_EXCEPTION_DICT", None)
    assert r._carry_origin(error, evidence("SESSION")) is error
    assert r._origin_from_error(error) is None
    assert error.args == ("original",)


def test_corrupt_exception_storage_keys_cannot_run_equality_hooks():
    r = runner()
    calls = []

    class Key:
        def __hash__(self):
            return hash("_qm_origin_owner")

        def __eq__(self, other):
            calls.append(other)
            return False

    error = Exception("original")
    BaseException.__dict__["__dict__"].__get__(error, BaseException)[Key()] = "bad"
    assert r._carry_origin(error, evidence()) is error
    assert r._origin_from_error(error) is None
    assert calls == [] and error.args == ("original",)
