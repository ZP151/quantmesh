"""SDK protobuf path role: real recovery child and SESSION guard, modeled OS and import."""

import hashlib
import importlib.machinery
import stat
import types
from types import SimpleNamespace

import pytest
from test_ivv_capture_contract import leaf
from test_ivv_executable_identity import MODE, base, environment

PB = "/opt/sdk/moomoo/common/pb"
PIN = "49f94f30ceac89078d784ddcad041e637100bd1e61f6e238b1347c8256d26907"


def child_session(monkeypatch, *, mode=MODE, initial_extra=()):
    helper = leaf()
    original = base.runner()
    held_read = original.read_ref
    monkeypatch.setattr(base, "runner", lambda: original)
    r, events, opened, plan, catalog = environment(
        monkeypatch, exact_path=not isinstance(mode, str)
    )
    real_session = r._ChildSession
    sessions = []
    channel = SimpleNamespace(
        send=lambda msg: events.append(("channel", msg["op"])),
        recv=lambda parent: next(replies),
    )
    replies = iter(
        [
            {"op": "enter"},
            {"op": "go", "plan_ref": {}, "go_ref": {}},
            {"snapshot": {}},
            {"snapshot": {}},
        ]
    )
    real_read = r.read_ref

    def read(ref, path, *args):
        if str(path) == PB + "/__init__.py":
            return held_read(ref, path, *args)
        if path.name == "plan.json":
            return r.raw_json({**plan, "provider_evidence_ref": {}})
        if path.name == "provider.json":
            return b"{}"
        return real_read(ref, path, *args)

    class SessionReady(Exception):
        pass

    def install(*args):
        sessions.append(real_session(*args))
        raise SessionReady

    monkeypatch.setattr(r, "read_ref", read)
    monkeypatch.setattr(r, "_ChildSession", install)
    monkeypatch.setattr(r, "_bind_parent", lambda parent: None)
    monkeypatch.setattr(r, "_child_namespace", lambda *a, **kw: 44)
    monkeypatch.setattr(r, "_environment", lambda: None)
    monkeypatch.setattr(r.os, "getpid", lambda: 73, raising=False)
    monkeypatch.setattr(helper, "_native_actor", lambda: {"pid": 73})
    monkeypatch.setattr(helper, "_admit_material", lambda *a: None)
    r.sys.path.extend(initial_extra)
    context = (
        {},
        {"catalog_ref": catalog, "budget_ref": {}, "_recovery_mode": mode},
        None,
        helper,
        None,
        None,
    )
    with pytest.raises(SessionReady):
        r._child(channel, 72, context, plan)
    assert not opened
    session = sessions.pop()
    observer = helper._CaptureObserver(
        {"started_monotonic": 1, "_live_verifier": session.snapshot},
        None,
        SimpleNamespace(mono=lambda: 2),
    )
    return r, session, observer, events


def package(r, monkeypatch, fault=None):
    name = "moomoo.common.pb"
    origin = PB + "/__init__.py"
    module = types.ModuleType(name)
    loader = importlib.machinery.SourceFileLoader(name, origin)
    spec = importlib.machinery.ModuleSpec(name, loader, origin=origin, is_package=True)
    spec.submodule_search_locations = [PB]
    module.__file__ = origin
    module.__path__ = spec.submodule_search_locations
    module.__spec__ = spec
    module.__loader__ = loader
    r.sys.modules = {name: module}
    # Portable held-file model uses inert test bytes. The real reader hashes and
    # compares them; also bind the independent expected release pin before substitution.
    assert r._SDK_PB_INITIALIZER_SHA256 == PIN
    data = b"X" * 64
    monkeypatch.setattr(r, "_SDK_PB_INITIALIZER_SHA256", hashlib.sha256(data).hexdigest())
    kernel = r.os
    info = SimpleNamespace(
        st_dev=2,
        st_ino=16,
        st_uid=0,
        st_mode=stat.S_IFREG | 0o444,
        st_nlink=1,
        st_size=len(data),
        st_ctime_ns=11,
        st_mtime_ns=13,
    )

    class FileKernel:
        def __getattr__(self, key):
            return getattr(kernel, key)

        def open(self, path, flags):
            if str(path) != origin:
                return kernel.open(path, flags)
            assert flags & kernel.O_NOFOLLOW and flags & kernel.O_CLOEXEC
            return 33

        def stat(self, path, **kw):
            if str(path) != origin:
                return kernel.stat(path, **kw)
            assert kw["follow_symlinks"] is False
            return SimpleNamespace(**{**vars(info), "st_ino": 19}) if fault == "rebound" else info

        def statvfs(self, path):
            if str(path) == PB and fault == "writable":
                return SimpleNamespace(f_flag=0)
            return kernel.statvfs(path)

        def fstat(self, fd):
            return info if fd == 33 else kernel.fstat(fd)

        def fstatvfs(self, fd):
            if fd == 33:
                return SimpleNamespace(f_flag=int(fault != "file_writable"))
            return kernel.fstatvfs(fd)

        def pread(self, fd, size, offset):
            if fd == 33:
                assert offset == 0 and size == 65
                return b"Z" * 64 if fault == "source" else data
            return kernel.pread(fd, size, offset)

        def close(self, fd):
            if fd != 33:
                return kernel.close(fd)
            if fault == "close":
                raise OSError(9, "modeled close")

    monkeypatch.setattr(r, "os", FileKernel())
    return module


def test_verified_sdk_append_reaches_constructor_sentinel(monkeypatch):
    r, session, observer, events = child_session(monkeypatch)
    session.snapshot()  # Actual pre-import SESSION is already valid.
    package(r, monkeypatch)
    r.sys.path.append(PB)  # Model the verified initializer's only path mutation.
    observer.context_created()
    events.append(("constructor", "sentinel"))
    assert events[-2:] == [("channel", "observe"), ("constructor", "sentinel")]


@pytest.mark.parametrize(
    "change",
    [
        "sibling",
        "prefix",
        "relative",
        "dot",
        "duplicate",
        "insert",
        "reorder",
        "extra",
        "nonexistent_extra",
        "alternate_spelling",
        "unapproved_directory",
    ],
)
def test_only_single_terminal_canonical_append(monkeypatch, change):
    r, _, observer, events = child_session(monkeypatch)
    package(r, monkeypatch)
    original = list(r.sys.path)
    replacements = {
        "sibling": [*original, PB + "2"],
        "prefix": [*original, PB + "/nested"],
        "relative": [*original, "moomoo/common/pb"],
        "dot": [*original, PB + "/."],
        "duplicate": [*original, PB, PB],
        "insert": [PB, *original],
        "reorder": [*reversed(original), PB],
        "extra": [*original, PB, original[0]],
        "nonexistent_extra": [*original, "/missing", PB],
        "alternate_spelling": [*original, PB.replace("/pb", "//pb")],
        "unapproved_directory": [*original, "/opt/other"],
    }
    r.sys.path = replacements[change]
    with pytest.raises(r.Refused, match="^PYTHON_SEARCH_PATH$"):
        observer.context_created()
    assert ("channel", "observe") not in events


@pytest.mark.parametrize(
    ("fault", "code"),
    [
        ("symlink", "CONTROL_PATH_ALIAS"),
        ("unprotected", "CONTROL_OWNERSHIP"),
        ("writable", "PYTHON_SEARCH_WRITABLE"),
        ("file_writable", "SOURCE_WRITABLE"),
        ("source", "CONTROL_DIGEST"),
        ("rebound", "CONTROL_DIGEST"),
        ("close", "FD_CLOSE_"),
        ("not_directory", "PYTHON_SEARCH_PATH"),
        ("origin", "PYTHON_SEARCH_PATH"),
        ("location", "PYTHON_SEARCH_PATH"),
        ("loader_path", "PYTHON_SEARCH_PATH"),
        ("loader", "PYTHON_SEARCH_PATH"),
        ("spec", "PYTHON_SEARCH_PATH"),
        ("missing_package", "PYTHON_SEARCH_PATH"),
        ("forged_origin", "PYTHON_SEARCH_PATH"),
        ("forged_package_path", "PYTHON_SEARCH_PATH"),
    ],
)
def test_each_session_requires_current_package_and_protected_bytes(monkeypatch, fault, code):
    r, session, observer, events = child_session(monkeypatch)
    mod = package(r, monkeypatch, fault)
    r.sys.path.append(PB)
    if fault in {"symlink", "unprotected", "not_directory"}:
        path_type = r.Path
        resolve, lstat, path_stat = path_type.resolve, path_type.lstat, path_type.stat
        if fault == "symlink":
            monkeypatch.setattr(
                path_type,
                "resolve",
                lambda p, strict=False: (
                    path_type("/private") if str(p) == PB else resolve(p, strict)
                ),
            )
        elif fault == "unprotected":
            monkeypatch.setattr(
                path_type,
                "lstat",
                lambda p: (
                    SimpleNamespace(st_uid=1, st_mode=0o755)
                    if str(p) == PB.rsplit("/", 1)[0]
                    else lstat(p)
                ),
            )
        else:
            monkeypatch.setattr(
                path_type,
                "stat",
                lambda p, **kw: (
                    SimpleNamespace(st_mode=stat.S_IFREG) if str(p) == PB else path_stat(p, **kw)
                ),
            )
    elif fault == "origin":
        mod.__spec__.origin = "/other/__init__.py"
    elif fault == "location":
        mod.__path__ = [PB, "/other"]
    elif fault == "loader_path":
        mod.__loader__.path = "/elsewhere/__init__.py"
    elif fault == "loader":
        mod.__loader__ = None
    elif fault == "spec":
        mod.__spec__ = None
    elif fault == "missing_package":
        r.sys.modules.clear()
    elif fault.startswith("forged"):

        class Pretend:
            def __eq__(self, other):
                return True

        if fault == "forged_origin":
            mod.__file__ = Pretend()
        else:
            mod.__path__ = Pretend()

    with pytest.raises(r.Refused, match=code) as refused:
        observer.context_created()
    classified = r.classify_capture_exception(refused.value, RuntimeError)
    assert classified["type"] == "Refused"
    # Existing composite cleanup errors remain unknown; fixed owning codes stay finite.
    assert classified["code"] == ("UNKNOWN" if fault == "close" else code)
    assert ("channel", "observe") not in events
    assert session.owner == 73


def test_later_session_rechecks_previously_valid_role(monkeypatch):
    r, session, observer, events = child_session(monkeypatch)
    mod = package(r, monkeypatch)
    r.sys.path.append(PB)
    observer.context_created()
    mod.__spec__.origin = "/changed/__init__.py"
    with pytest.raises(r.Refused, match="PYTHON_SEARCH_PATH"):
        session.snapshot()
    assert events.count(("channel", "observe")) == 1


@pytest.mark.parametrize("mode", [False, True])
def test_legacy_sessions_keep_existing_search_policy(monkeypatch, mode):
    r, _, observer, _ = child_session(monkeypatch, mode=mode)
    r.sys.path.append(PB)
    with pytest.raises(r.Refused, match="PYTHON_SEARCH_PATH"):
        observer.context_created()


def test_initial_phase_never_accepts_pb_directory(monkeypatch):
    with pytest.raises(ValueError, match="PYTHON_SEARCH_PATH"):
        child_session(monkeypatch, initial_extra=[PB])


def test_session_without_append_does_not_need_loaded_package(monkeypatch):
    _, _, observer, events = child_session(monkeypatch)
    observer.context_created()
    assert ("channel", "observe") in events


def test_path_drift_during_held_source_validation_refuses(monkeypatch):
    r, _, observer, events = child_session(monkeypatch)
    package(r, monkeypatch)
    r.sys.path.append(PB)
    original = r.os.pread

    def pread(fd, size, offset):
        if fd == 33:
            r.sys.path.insert(0, r.sys.path[0])
        return original(fd, size, offset)

    monkeypatch.setattr(r.os, "pread", pread)
    with pytest.raises(r.Refused, match="PYTHON_SEARCH_PATH"):
        observer.context_created()
    assert ("channel", "observe") not in events
