"""Existing origin rejection evidence; OS boundaries modeled, no SDK/native call."""

import json
from pathlib import PurePosixPath
from types import SimpleNamespace

import pytest
import test_ivv_runtime_failure_evidence as base


def path_fact(kind="EXPECTED_DELETED", path="/usr/bin/python3.12 (deleted)"):
    return {"classification": kind, "path": path}


def observation():
    return {
        "schema": "qm.ivv.executable-observation.v1",
        "nonstrict": path_fact(),
        "readlink": {"status": "OK", "result": path_fact()},
        "strict": {"status": "ENOENT", "result": None},
        "namespace": "SAME",
    }


def runtime_case(
    monkeypatch,
    *,
    mode="connection-000002",
    result=None,
    lookup_error=None,
    strict_error=None,
    readlink_error=None,
    namespace=(44, 44, 44),
):
    r = base.runner()
    calls = []
    inodes = iter(namespace)
    if result is None:
        result = PurePosixPath("/usr/bin/python3.12 (deleted)")
    if strict_error is None:
        strict_error = FileNotFoundError(2, "PRIVATE_EXCEPTION")

    class Proc:
        def resolve(self, strict=False):
            calls.append(("resolve", strict))
            if strict:
                raise strict_error
            if lookup_error is not None:
                raise lookup_error
            return result

    def paths(value="."):
        return Proc() if value == "/proc/self/exe" else PurePosixPath(value)

    def readlink(value):
        assert value == "/proc/self/exe"
        calls.append(("readlink", value))
        if readlink_error is not None:
            raise readlink_error
        return "/usr/bin/python3.12 (deleted)"

    def stat(value):
        assert value == "/proc/self/ns/mnt"
        return SimpleNamespace(st_ino=next(inodes))

    monkeypatch.setattr(r, "Path", paths)
    monkeypatch.setattr(r, "os", SimpleNamespace(stat=stat, readlink=readlink, environ={}))
    monkeypatch.setattr(r, "sys", SimpleNamespace(version_info=(3, 12, 3)))
    monkeypatch.setattr(r, "_writable_mounts", lambda *a, **kw: None)
    with pytest.raises(BaseException) as caught:
        r._runtime(
            {"sdk_root": str(r.SDK)}, None, 44, {}, None, additional=mode, origin_phase="INITIAL"
        )
    return r, caught.value, calls


def test_original_single_result_survives_actual_rejection(monkeypatch):
    r, error, calls = runtime_case(monkeypatch)
    assert error.args == ("RUNTIME_ORIGIN",)
    selected = r._failure_record(error)
    assert selected["origin_failure"]["executable_observation"] == observation()
    assert calls == [("resolve", False), ("readlink", "/proc/self/exe"), ("resolve", True)]
    assert "PRIVATE" not in json.dumps(selected)


@pytest.mark.parametrize("mode", [False, True])
def test_legacy_family_has_no_extra_reads(monkeypatch, mode):
    r, error, calls = runtime_case(monkeypatch, mode=mode)
    assert "executable_observation" not in r._failure_record(error)["origin_failure"]
    assert calls == [("resolve", False)]


def test_passing_guard_and_original_lookup_exception_do_not_observe(monkeypatch):
    r, error, calls = runtime_case(monkeypatch, result=PurePosixPath("/usr/bin/python3.12"))
    assert error.args == ("HOME_NOT_READY",)
    assert "origin_failure" not in r._failure_record(error)
    assert calls == [("resolve", False)]
    original = PermissionError(13, "PRIVATE_EXCEPTION")
    r, error, calls = runtime_case(monkeypatch, lookup_error=original)
    assert error is original and error.args == (13, "PRIVATE_EXCEPTION")
    assert calls == [("resolve", False)]
    assert "executable_observation" not in r._failure_record(error)["origin_failure"]


@pytest.mark.parametrize(
    "namespace,want", [((44, 44, 45), "CHANGED"), ((44, 45, 45), "CHANGED"), ((44,), "UNAVAILABLE")]
)
def test_actual_namespace_continuity_is_not_host_identity(monkeypatch, namespace, want):
    r, error, _ = runtime_case(monkeypatch, namespace=namespace)
    assert r._failure_record(error)["origin_failure"]["executable_observation"]["namespace"] == want


def test_auxiliary_errors_preserve_primary_exception_and_redact_args(monkeypatch):
    r, error, _ = runtime_case(
        monkeypatch,
        readlink_error=PermissionError(13, "SECRET_URI"),
        strict_error=RuntimeError("SECRET_URI"),
    )
    obs = r._failure_record(error)["origin_failure"]["executable_observation"]
    assert error.args == ("RUNTIME_ORIGIN",)
    assert obs["readlink"] == {"status": "EACCES", "result": None}
    assert obs["strict"] == {"status": "OTHER_EXCEPTION", "result": None}
    assert "SECRET" not in json.dumps(obs)


def test_retained_value_stringification_cannot_override_original(monkeypatch):
    class Hostile:
        def __eq__(self, other):
            return False

        def __str__(self):
            raise RuntimeError("SECRET_STRINGIFIER")

    r, error, _ = runtime_case(monkeypatch, result=Hostile())
    assert error.args == ("RUNTIME_ORIGIN",)
    obs = r._failure_record(error)["origin_failure"]["executable_observation"]
    assert obs["nonstrict"] == path_fact("REDACTED", None)
    assert "SECRET" not in json.dumps(obs)


@pytest.mark.parametrize(
    "value,want",
    [
        (PurePosixPath("/home/private/account"), path_fact("REDACTED", None)),
        (PurePosixPath("/proc/12345/exe"), path_fact("PROC_EXE", None)),
        (
            PurePosixPath("/usr/local/bin/python3.12"),
            path_fact("OTHER_PUBLIC", "/usr/local/bin/python3.12"),
        ),
        (PurePosixPath("/usr/bin/" + "a" * 161), path_fact("REDACTED", None)),
    ],
)
def test_actual_retained_result_privacy_projection(monkeypatch, value, want):
    r, error, _ = runtime_case(monkeypatch, result=value)
    assert r._failure_record(error)["origin_failure"]["executable_observation"]["nonstrict"] == want


@pytest.mark.parametrize("ordering", ["channel", "pidfd", "both"])
def test_observation_crosses_actual_authenticated_ipc_main_reader_and_stop(monkeypatch, ordering):
    r, error, _ = runtime_case(monkeypatch)
    expected = {**base.evidence("INITIAL", "EXECUTABLE"), "executable_observation": observation()}
    result = base.test_real_child_ipc_parent_wrap_main_reader_selector(
        monkeypatch, ordering, (r, error, expected)
    )
    assert result["origin_failure"] == expected
    assert result["actual_contexts"] == "UNKNOWN"


@pytest.mark.parametrize(
    "change",
    [
        lambda o: o.update(secret="PRIVATE"),
        lambda o: o["nonstrict"].update(path="/home/private/account"),
        lambda o: o["strict"].update(status="PRIVATE"),
        lambda o: o.update(namespace=True),
        lambda o: o["readlink"].update(result={"classification": "REDACTED", "path": "PRIVATE"}),
    ],
)
def test_strict_codec_refuses_malformed_or_private_observation(change):
    r = base.runner()
    o = observation()
    change(o)
    with pytest.raises(ValueError):
        r.select_origin_failure(
            {**base.evidence("INITIAL", "EXECUTABLE"), "executable_observation": o}
        )


def test_observation_cannot_be_attached_to_unexecuted_predicate():
    r = base.runner()
    with pytest.raises(ValueError):
        r.select_origin_failure({**base.evidence(), "executable_observation": observation()})
    assert r.select_origin_failure(base.evidence()) == base.evidence()


@pytest.mark.parametrize(
    "value",
    [
        "/usr/../home/secret",
        "/usr/bin/../private",
        "/usr/bin/a\nsecret",
        "/usr/bin/" + "x" * 170,
        "/usr/bin//python3.12",
    ],
)
def test_untrusted_public_looking_payload_is_refused(value):
    r = base.runner()
    o = observation()
    o["nonstrict"] = path_fact("OTHER_PUBLIC", value)
    with pytest.raises(ValueError):
        r.select_origin_failure(
            {**base.evidence("INITIAL", "EXECUTABLE"), "executable_observation": o}
        )


@pytest.mark.parametrize("number", [True, float("nan"), 999])
def test_auxiliary_errno_is_not_truthy_or_coerced(monkeypatch, number):
    r, error, _ = runtime_case(monkeypatch, readlink_error=OSError(number, "SECRET"))
    assert r._failure_record(error)["origin_failure"]["executable_observation"]["readlink"] == {
        "status": "OTHER_OSERROR",
        "result": None,
    }


def test_auxiliary_internal_failure_cannot_replace_original(monkeypatch):
    r = base.runner()
    plan, _ = base.origin_seams(r, monkeypatch, "EXECUTABLE")
    # Keep the real guard, but model failure of the optional diagnostic serialization.
    monkeypatch.setattr(r, "_locations", lambda mode: None)
    monkeypatch.setattr(r, "_writable_mounts", lambda *args, **kw: None)
    monkeypatch.setattr(
        r, "_observe_executable", lambda *args: (_ for _ in ()).throw(MemoryError("SECRET"))
    )
    with pytest.raises(r.Refused) as caught:
        r._runtime(plan, None, 44, {}, None, additional="connection-000002", origin_phase="INITIAL")
    assert caught.value.args == ("RUNTIME_ORIGIN",)
    assert r._failure_record(caught.value)["origin_failure"] == base.evidence(
        "INITIAL", "EXECUTABLE"
    )


def test_actual_child_initial_reaches_observation_before_native_admission(monkeypatch):
    r, _, calls = runtime_case(monkeypatch)
    calls.clear()
    r.os.stat = lambda path: SimpleNamespace(st_ino=44)
    r.sys.path = []
    monkeypatch.setattr(r, "_bind_parent", lambda parent: None)
    monkeypatch.setattr(r, "_child_namespace", lambda *args, **kw: 44)
    monkeypatch.setattr(r, "_environment", lambda: None)
    plan = {"sdk_root": str(r.SDK), "_recovery_mode": "connection-000002"}
    context = (
        {},
        {"catalog_ref": {}, "_recovery_mode": "connection-000002"},
        None,
        None,
        None,
        None,
    )
    with pytest.raises(r.Refused) as caught:
        r._child(SimpleNamespace(recv=lambda parent: {"op": "enter"}), 11, context, plan)
    assert caught.value.args == ("RUNTIME_ORIGIN",)
    assert (
        r._failure_record(caught.value)["origin_failure"]["executable_observation"] == observation()
    )
    assert calls == [("resolve", False), ("readlink", "/proc/self/exe"), ("resolve", True)]


@pytest.mark.parametrize("where", ["lookup", "comparison", "truth"])
def test_recovery_original_exception_object_args_and_lazy_counts(monkeypatch, where):
    r = base.runner()
    original = r.Refused("RUNTIME_ORIGIN")
    plan, calls = base.origin_seams(r, monkeypatch, "EXECUTABLE", error=original, where=where)
    monkeypatch.setattr(r, "_locations", lambda mode: None)
    monkeypatch.setattr(r, "_writable_mounts", lambda *args, **kw: None)
    with pytest.raises(r.Refused) as caught:
        r._runtime(plan, None, 44, {}, None, additional="connection-000002", origin_phase="INITIAL")
    assert caught.value is original and original.args == ("RUNTIME_ORIGIN",)
    assert r._failure_record(original)["origin_failure"] == base.evidence(
        "INITIAL", "EXECUTABLE", "EXCEPTION"
    )
    assert len([c for c in calls if c == ("lookup", "EXECUTABLE")]) == 1
    assert len([c for c in calls if c == ("eq", "EXECUTABLE")]) == (0 if where == "lookup" else 1)
    assert len([c for c in calls if c[0] == "bool" and c[1] == "EXECUTABLE"]) == (
        1 if where == "truth" else 0
    )


def test_recovery_earlier_false_short_circuits_without_observing(monkeypatch):
    r = base.runner()
    plan, calls = base.origin_seams(r, monkeypatch, "SDK_ROOT")
    monkeypatch.setattr(r, "_locations", lambda mode: None)
    monkeypatch.setattr(r, "_writable_mounts", lambda *args, **kw: None)
    with pytest.raises(r.Refused) as caught:
        r._runtime(plan, None, 44, {}, None, additional="connection-000002", origin_phase="INITIAL")
    assert r._failure_record(caught.value)["origin_failure"] == base.evidence()
    assert calls == [
        ("lookup", "SDK_ROOT"),
        ("eq", "SDK_ROOT"),
        ("bool", "SDK_ROOT", 1),
        ("bool", "SDK_ROOT", 2),
    ]
