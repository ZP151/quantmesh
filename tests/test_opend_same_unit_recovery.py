"""Synthetic same-unit controls; no host, credential, vendor or SDK execution."""

import copy
import hashlib
import importlib.util
import json
import os
import stat
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_opend_persistent_console import persistent_permit
from test_opend_staging_window import stage

NOW = datetime(2026, 10, 31, tzinfo=UTC)


class SyntheticFiles:
    """Real private file IO/O_EXCL, with modeled Linux ownership metadata."""

    O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
    O_NONBLOCK = getattr(os, "O_NONBLOCK", 1 << 30)

    @staticmethod
    def getuid():
        return 1001

    def __init__(self):
        self.paths = {}
        self.directories = {}
        self.metadata = {}
        self.next_directory = 100000

    def __getattr__(self, name):
        return getattr(os, name)

    def path(self, path, dir_fd=None):
        return (self.directories[dir_fd] / path) if dir_fd is not None else Path(path)

    def open(self, path, flags, mode=0o777, *, dir_fd=None):
        path = self.path(path, dir_fd)
        if not hasattr(os, "O_NONBLOCK"):
            flags &= ~self.O_NONBLOCK  # Linux flag is modeled on Windows only.
        fd = os.open(path, flags | getattr(os, "O_BINARY", 0), mode)
        self.paths[fd] = path
        self.metadata.setdefault(path, {"uid": 1001, "gid": 1001, "mode": 0o600})
        return fd

    def close(self, fd):
        self.paths.pop(fd, None)
        os.close(fd)

    def info(self, value, path):
        attributes = {key: getattr(value, key) for key in dir(value) if key.startswith("st_")}
        if os.name == "nt":
            # Windows stat/fstat creation-time views differ during concurrent IO.
            # Model POSIX ctime consistently; Linux runs retain native timestamps.
            attributes["st_ctime_ns"] = value.st_mtime_ns
            attributes["st_ctime"] = value.st_mtime
        meta = self.metadata.get(path, {})
        for key in ("uid", "gid", "nlink"):
            if key in meta:
                attributes["st_" + key] = meta[key]
        if "mode" in meta:
            attributes["st_mode"] = stat.S_IFMT(value.st_mode) | meta["mode"]
        return SimpleNamespace(**attributes)

    def fstat(self, fd):
        return self.info(os.fstat(fd), self.paths[fd])

    def stat(self, name, *, dir_fd=None, follow_symlinks=True):
        path = self.path(name, dir_fd)
        return self.info(os.stat(path, follow_symlinks=follow_symlinks), path)

    def fchmod(self, fd, mode):
        self.metadata[self.paths[fd]]["mode"] = mode

    def fsync(self, fd):
        if fd not in self.directories:
            os.fsync(fd)

    @contextmanager
    def directory(self, path):
        self.next_directory += 1
        fd = self.next_directory
        self.directories[fd] = Path(path)
        try:
            yield fd
        finally:
            self.directories.pop(fd)

    @contextmanager
    def protected(self, path):
        fd = self.open(path, os.O_RDONLY)
        try:
            yield fd
        finally:
            self.close(fd)


def identity(files, path):
    value = files.stat(path)
    return {
        "device": value.st_dev,
        "inode": value.st_ino,
        "uid": value.st_uid,
        "gid": value.st_gid,
        "mode": stat.S_IMODE(value.st_mode),
        "nlink": value.st_nlink,
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
        "ctime_ns": value.st_ctime_ns,
    }


@pytest.fixture
def recovery(tmp_path, monkeypatch):
    files = SyntheticFiles()
    state = tmp_path / "state"
    state.mkdir()
    claim = state / ("a" * 32)
    claim.write_bytes(b"")
    files.metadata[claim] = {"uid": 1001, "gid": 1001, "mode": 0o600}
    prior = tmp_path / "persistent-session.json"
    expired = persistent_permit()
    expired.update(nonce="d" * 32, expires_at=(NOW - timedelta(seconds=60)).isoformat())
    prior.write_bytes(json.dumps(expired).encode())
    files.metadata[prior] = {"uid": 0, "gid": 0, "mode": 0o644}
    control_path = tmp_path / "persistent-recovery.json"
    claims = persistent_permit()
    claims.update(
        schema_version=3,
        purpose="opend_same_unit_recovery",
        nonce="a" * 32,
        unit="quantmesh-opend-console@" + "a" * 32 + ".service",
        vendor_sha256=stage.VENDOR_SHA,
        max_seconds=180,
        not_before=(NOW - timedelta(seconds=1)).isoformat(),
        expires_at=(NOW + timedelta(seconds=60)).isoformat(),
        original_claim=identity(files, claim),
        prior_permit={
            "identity": identity(files, prior),
            "sha256": hashlib.sha256(prior.read_bytes()).hexdigest(),
        },
    )
    control_path.write_bytes(json.dumps(claims).encode())
    files.metadata[control_path] = {"uid": 0, "gid": 0, "mode": 0o444}
    monkeypatch.setattr(stage, "os", files)
    monkeypatch.setattr(stage, "STATE", state)
    monkeypatch.setattr(stage, "PERSISTENT_PERMIT", prior)
    monkeypatch.setattr(stage, "RECOVERY_PERMIT", control_path, raising=False)
    monkeypatch.setattr(stage, "_protected_fd", files.protected)
    monkeypatch.setattr(stage, "_owned_dir", files.directory)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    monkeypatch.setattr(stage, "datetime", Clock)
    hashes = {
        "launcher_sha256": "c" * 64,
        "tmux_sha256": stage.TMUX_SHA,
        "vendor_sha256": stage.VENDOR_SHA,
    }
    actor = {"machine_sha256": stage.MACHINE_SHA, "gateway_uid": 1001, "gateway_gid": 1001}

    def admit(window):
        if hasattr(window, "control"):
            window.control.validate(now=NOW, identity=actor, hashes=hashes)
        else:
            stage.validate_staging_window(window, now=NOW, identity=actor, hashes=hashes)
        return None, None

    def module(path, digest):
        source = Path(stage.__file__).parent / path.name
        data = source.read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest
        spec = importlib.util.spec_from_file_location("synthetic_recovery_control", source)
        loaded = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = loaded
        spec.loader.exec_module(loaded)
        return loaded

    monkeypatch.setattr(stage, "_admit", admit)
    monkeypatch.setattr(stage, "_module", module)
    yield SimpleNamespace(
        files=files,
        state=state,
        claim=claim,
        prior=prior,
        path=control_path,
        claims=claims,
        actor=actor,
        hashes=hashes,
    )
    assert not files.paths, "recovery leaked a file descriptor"
    assert not files.directories, "recovery leaked a directory descriptor"


def test_existing_fixed_check_routes_explicit_recovery_without_consuming(recovery, capsys):
    before = recovery.claim.read_bytes(), recovery.prior.read_bytes()
    assert stage.main(["--check-window", "--persistent", "--nonce", "a" * 32]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "admitted"
    assert not any(result[key] for key in stage.FALSE_FLAGS)
    assert before == (recovery.claim.read_bytes(), recovery.prior.read_bytes())
    assert not (recovery.state / ("a" * 32 + ".recovery")).exists()


def test_repeated_checks_do_not_consume(recovery, capsys):
    for _ in range(3):
        assert stage.main(["--check-window", "--persistent", "--nonce", "a" * 32]) == 0
    assert len(capsys.readouterr().out.splitlines()) == 3
    assert recovery.claim.read_bytes() == b""
    assert not (recovery.state / ("a" * 32 + ".recovery")).exists()


@pytest.mark.parametrize(
    "change",
    [
        lambda c: c.update(extra_authority=True),
        lambda c: c.update(schema_version=True),
        lambda c: c.update(purpose="opend_persistent_private_console"),
        lambda c: c.update(nonce="b" * 32),
        lambda c: c.update(unit="quantmesh-opend-console@" + "b" * 32 + ".service"),
        lambda c: c.update(gateway_uid=True),
        lambda c: c.update(gateway_gid=1002),
        lambda c: c.update(max_seconds=181),
        lambda c: c.update(session_lifetime="unbounded_authority"),
        lambda c: c.update(human_reviewers=["Operator", "invented"]),
        lambda c: c.update(safety_owner="invented"),
        lambda c: c.update(ci_conclusion="pending"),
        lambda c: c.update(launcher_sha256="d" * 64),
        lambda c: c.update(vendor_sha256="d" * 64),
        lambda c: c.update(machine_sha256="d" * 64),
        lambda c: c.update(expires_at=NOW.isoformat()),
        lambda c: c.update(not_before=(NOW + timedelta(seconds=1)).isoformat()),
        lambda c: c.update(expires_at=(NOW + timedelta(seconds=301)).isoformat()),
        lambda c: c["original_claim"].update(size=1),
        lambda c: c["original_claim"].update(inode=c["original_claim"]["inode"] + 1),
        lambda c: c["original_claim"].update(mode=0o666),
        lambda c: c["original_claim"].update(uid=0),
        lambda c: c["prior_permit"].update(sha256="d" * 64),
        lambda c: c["prior_permit"]["identity"].update(uid=1001),
    ],
)
def test_bad_recovery_control_refuses_before_any_consumption(recovery, capsys, change):
    original_claim = recovery.claim.read_bytes()
    candidate = copy.deepcopy(recovery.claims)
    change(candidate)
    recovery.path.write_bytes(json.dumps(candidate).encode())
    assert stage.main(["--check-window", "--persistent", "--nonce", "a" * 32]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "pending"
    assert recovery.claim.read_bytes() == original_claim
    assert not (recovery.state / ("a" * 32 + ".recovery")).exists()


@pytest.mark.parametrize(
    "which,field,value",
    [
        ("path", "uid", 1001),
        ("path", "mode", 0o644),
        ("path", "nlink", 2),
        ("prior", "uid", 1001),
        ("prior", "mode", 0o666),
        ("prior", "nlink", 2),
        ("claim", "uid", 0),
        ("claim", "mode", 0o644),
        ("claim", "nlink", 2),
    ],
)
def test_live_metadata_drift_refuses(recovery, capsys, which, field, value):
    recovery.files.metadata[getattr(recovery, which)][field] = value
    assert stage.main(["--check-window", "--persistent", "--nonce", "a" * 32]) == 2
    capsys.readouterr()
    assert not (recovery.state / ("a" * 32 + ".recovery")).exists()


def test_absent_recovery_control_preserves_initial_persistent_route(recovery, capsys, monkeypatch):
    recovery.path.unlink()  # This synthetic control only, never an old runtime artifact.
    initial = persistent_permit()
    initial.update(
        nonce="b" * 32,
        not_before=(NOW - timedelta(seconds=1)).isoformat(),
        expires_at=(NOW + timedelta(seconds=60)).isoformat(),
    )
    recovery.prior.write_bytes(json.dumps(initial).encode())
    monkeypatch.setattr(
        stage, "_module", lambda *a: pytest.fail("legacy route loaded recovery module")
    )
    assert stage.main(["--check-window", "--persistent", "--nonce", "b" * 32]) == 0
    assert json.loads(capsys.readouterr().out)["scope"] == "STAGING_WINDOW_ONLY"
    assert recovery.claim.read_bytes() == b""


def test_present_invalid_recovery_never_falls_back_to_valid_initial(recovery, capsys):
    initial = persistent_permit()
    initial.update(
        not_before=(NOW - timedelta(seconds=1)).isoformat(),
        expires_at=(NOW + timedelta(seconds=60)).isoformat(),
    )
    recovery.prior.write_bytes(json.dumps(initial).encode())
    recovery.path.write_bytes(b"{broken}")
    assert stage.main(["--check-window", "--persistent", "--nonce", "a" * 32]) == 2
    capsys.readouterr()


def test_prepare_and_create_pane_use_same_recovery_without_consumption(
    recovery, tmp_path, monkeypatch, capsys
):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "socket").write_bytes(b"")  # Backend metadata is modeled, no socket exists.
    monkeypatch.setattr(stage, "_paths", lambda w: runtime)
    monkeypatch.setattr(stage, "_manager", lambda w, **kw: {"ControlGroup": "SYNTHETIC_GROUP"})
    monkeypatch.setattr(stage, "_cgroup", lambda who: "SYNTHETIC_GROUP")
    assert stage.main(["--prepare", "--persistent", "--nonce", "a" * 32]) == 0
    capsys.readouterr()
    assert (runtime / "tmux.conf").read_bytes() == stage._tmux_config(
        stage.StagingWindow(persistent_permit())
    )
    seen = []
    monkeypatch.setattr(stage, "_backend_context", lambda w, **kw: {"backend_pidfd": 50000})
    monkeypatch.setattr(stage, "_command", lambda argv: seen.append(argv))
    original_close = recovery.files.close
    monkeypatch.setattr(
        recovery.files, "close", lambda fd: None if fd == 50000 else original_close(fd)
    )
    assert stage.main(["--create-pane", "--persistent", "--nonce", "a" * 32]) == 0
    capsys.readouterr()
    assert seen[0][-4:] == ["--pane", "--nonce", "a" * 32, "--persistent"]
    assert recovery.claim.read_bytes() == b""
    assert not (recovery.state / ("a" * 32 + ".recovery")).exists()


@pytest.fixture
def lifecycle(recovery, tmp_path, monkeypatch):
    record = SimpleNamespace(
        releases=0, children=[], closed_handles=[], on_spawn=None, on_gate=None
    )
    vendor = tmp_path / "SYNTHETIC_VENDOR_NEVER_EXECUTED"
    vendor.write_bytes(b"SYNTHETIC_RELEASE_SPY_ONLY")
    recovery.files.metadata[vendor] = {"uid": 0, "gid": 0, "mode": 0o444}
    monkeypatch.setattr(stage, "VENDOR", vendor)
    proof = {"descriptors": [{"rdev": 3}, {"rdev": 3}, {"rdev": 3}]}
    helper = SimpleNamespace(inspect_private_terminal=lambda *a, **k: copy.deepcopy(proof))
    profile = {"runtime": {"argv": ["--fixed-synthetic-config"]}}
    admit = stage._admit

    def admitted(window):
        admit(window)
        return profile, helper

    monkeypatch.setattr(stage, "_admit", admitted)
    group = "SYNTHETIC_CGROUP"

    def inspect(window):
        admitted(window)
        return {
            "manager": {"ControlGroup": group, "MainPID": "7"},
            "terminal": copy.deepcopy(proof),
            "backend_pidfd": 50000,
        }

    monkeypatch.setattr(stage, "inspect_staging_context", inspect)
    monkeypatch.setattr(stage, "_cgroup", lambda who: group)
    monkeypatch.setattr(
        stage, "_finish_backend", lambda handle: record.closed_handles.append(handle)
    )
    old_close = recovery.files.close

    def close(fd):
        if fd == 50000:
            record.closed_handles.append(fd)
        else:
            old_close(fd)

    monkeypatch.setattr(recovery.files, "close", close)
    old_digest = stage._digest_fd
    monkeypatch.setattr(
        stage,
        "_digest_fd",
        lambda fd: stage.VENDOR_SHA if recovery.files.paths.get(fd) == vendor else old_digest(fd),
    )
    signals = {}

    def signal(number, handler):
        prior = signals.get(number, "SYNTHETIC_ORIGINAL_HANDLER")
        signals[number] = handler
        return prior

    monkeypatch.setattr(
        stage, "signal", SimpleNamespace(SIGINT=2, SIGTERM=15, SIGHUP=1, signal=signal)
    )
    old_write = recovery.files.write

    def write(fd, data):
        if fd == 50001:
            if record.on_gate:
                record.on_gate()
            record.releases += 1
            return len(data)
        return old_write(fd, data)

    monkeypatch.setattr(recovery.files, "write", write)
    monkeypatch.setattr(stage, "_report", lambda *a, **kw: b"R")
    monkeypatch.setattr(stage, "_identity", lambda pid, handle: {"synthetic_pid": pid})

    class Child:
        release = stage._Owned.release  # Exercise the existing actual gate method unchanged.
        pid = 11
        gate = 50001
        report = 50002
        pidfd = 50003
        identity = {"synthetic_pid": 11}

        def __init__(self):
            self.closed = False
            self.terminal = False
            self.released = False

        def alive(self):
            return not self.released and not self.closed

        def close(self):
            self.closed = True
            self.terminal = True
            self.returncode = 0

    def spawn(*a, registry=None, **kw):
        child = Child()
        record.children.append(child)
        registry.append(child)
        if record.on_spawn:
            record.on_spawn()
        return child

    monkeypatch.setattr(stage, "_spawn_gated", spawn)
    return record


def test_one_recovery_consumes_only_at_actual_gate_and_preserves_initial(recovery, lifecycle):
    window = stage.select_console_window("a" * 32, persistent=True)
    before = recovery.claim.read_bytes(), recovery.prior.read_bytes()
    result = stage.start_staging_console(window)
    assert result["status"] == "stopped"
    assert lifecycle.releases == 1
    assert all(child.closed for child in lifecycle.children)
    assert before == (recovery.claim.read_bytes(), recovery.prior.read_bytes())
    marker = recovery.state / ("a" * 32 + ".recovery")
    assert marker.exists()
    assert (
        json.loads(marker.read_bytes())["control_sha256"]
        == hashlib.sha256(recovery.path.read_bytes()).hexdigest()
    )
    with pytest.raises(stage.StageDenied, match="duplicate_recovery"):
        stage.start_staging_console(stage.select_console_window("a" * 32, persistent=True))
    assert lifecycle.releases == 1


def test_claim_replacement_during_last_native_pid_check_cannot_release(
    recovery, lifecycle, monkeypatch
):
    window = stage.select_console_window("a" * 32, persistent=True)
    changed = False
    original_stat = recovery.files.stat

    def named_stat(name, *, dir_fd=None, follow_symlinks=True):
        value = original_stat(name, dir_fd=dir_fd, follow_symlinks=follow_symlinks)
        if changed and recovery.files.path(name, dir_fd) == recovery.claim:
            value.st_ino += 1  # Model POSIX name replacement while old FD stays held.
        return value

    monkeypatch.setattr(recovery.files, "stat", named_stat)

    def identity_changed(pid, handle):
        nonlocal changed
        changed = True
        return {"synthetic_pid": pid}

    monkeypatch.setattr(stage, "_identity", identity_changed)
    with pytest.raises(stage.StageDenied):
        stage.start_staging_console(window)
    assert lifecycle.releases == 0
    assert all(child.closed for child in lifecycle.children)


@pytest.mark.parametrize("contended_run", range(10))
def test_two_concurrent_recovery_consumers_release_at_most_once(recovery, contended_run):
    control = stage.select_console_window("a" * 32, persistent=True).control
    barrier = threading.Barrier(2)

    def contend():
        try:
            with control.release_lease() as lease:
                barrier.wait(timeout=5)
                lease.consume()
                return "RELEASE_ALLOWED"
        except stage.StageDenied as error:
            if error.code != "duplicate_recovery":
                raise
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: contend(), range(2)))
    assert sorted(outcomes) == ["RELEASE_ALLOWED", "duplicate_recovery"]
    assert recovery.claim.read_bytes() == b""
    marker = recovery.state / ("a" * 32 + ".recovery")
    assert marker.exists()


def test_original_claim_open_cannot_wait_on_replaced_fifo(recovery, monkeypatch):
    control = stage.select_console_window("a" * 32, persistent=True).control
    opened = recovery.files.open
    observed = []

    def nonblocking(path, flags, mode=0o777, *, dir_fd=None):
        if recovery.files.path(path, dir_fd) == recovery.claim:
            observed.append(flags)
            assert flags & recovery.files.O_NONBLOCK, "claim open can block before type validation"
        return opened(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(recovery.files, "open", nonblocking)
    control.check_available()
    assert observed


@pytest.mark.parametrize("object_name", ["path", "prior", "claim"])
def test_changed_authority_after_successful_check_never_releases(recovery, lifecycle, object_name):
    window = stage.select_console_window("a" * 32, persistent=True)
    window.control.check_available()
    lifecycle.on_spawn = lambda: recovery.files.metadata[getattr(recovery, object_name)].update(
        nlink=2
    )
    with pytest.raises(stage.StageDenied):
        stage.start_staging_console(window)
    assert lifecycle.releases == 0
    assert lifecycle.children and all(child.closed for child in lifecycle.children)
    assert not (recovery.state / ("a" * 32 + ".recovery")).exists()


@pytest.mark.parametrize(
    "field", ["machine_sha256", "gateway_uid", "launcher_sha256", "vendor_sha256"]
)
def test_final_native_identity_drift_refuses_without_consumption(recovery, lifecycle, field):
    window = stage.select_console_window("a" * 32, persistent=True)

    def drift():
        target = recovery.actor if field in recovery.actor else recovery.hashes
        target[field] = 1002 if field == "gateway_uid" else "0" * 64

    lifecycle.on_spawn = drift
    with pytest.raises(stage.StageDenied):
        stage.start_staging_console(window)
    assert lifecycle.releases == 0
    assert all(child.closed for child in lifecycle.children)
    assert not (recovery.state / ("a" * 32 + ".recovery")).exists()


def test_expiry_during_final_native_checks_refuses_before_consumption(
    recovery, lifecycle, monkeypatch
):
    window = stage.select_console_window("a" * 32, persistent=True)

    class Expired(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW + timedelta(minutes=2)

    original = stage._identity

    def slow_check(*args):
        monkeypatch.setattr(stage, "datetime", Expired)
        return original(*args)

    monkeypatch.setattr(stage, "_identity", slow_check)
    with pytest.raises(stage.StageDenied):
        stage.start_staging_console(window)
    assert lifecycle.releases == 0
    assert all(child.closed for child in lifecycle.children)
    assert not (recovery.state / ("a" * 32 + ".recovery")).exists()


@pytest.mark.parametrize(
    "failure", ["gate", "ack", "write", "zero_write", "file_fsync", "directory_fsync", "expiry"]
)
def test_failure_after_consumption_stays_spent_and_closes_owned_handles(
    recovery, lifecycle, monkeypatch, failure
):
    window = stage.select_console_window("a" * 32, persistent=True)
    original_clock = stage.datetime
    original_write = recovery.files.write
    original_sync = recovery.files.fsync

    def write(fd, data):
        if fd == 50001 and failure == "gate":
            raise OSError("synthetic gate failure")
        if recovery.files.paths.get(fd) == recovery.state / ("a" * 32 + ".recovery"):
            if failure == "write":
                raise OSError("synthetic marker write failure")
            if failure == "zero_write":
                return 0
        return original_write(fd, data)

    def sync(fd):
        is_directory = fd in recovery.files.directories
        if (failure == "directory_fsync" and is_directory) or (
            failure == "file_fsync" and not is_directory
        ):
            raise OSError("synthetic fsync failure")
        original_sync(fd)
        if failure == "expiry":

            class Expired(datetime):
                @classmethod
                def now(cls, tz=None):
                    return NOW + timedelta(minutes=2)

            monkeypatch.setattr(stage, "datetime", Expired)

    monkeypatch.setattr(recovery.files, "write", write)
    monkeypatch.setattr(recovery.files, "fsync", sync)
    if failure == "ack":
        monkeypatch.setattr(stage, "_report", lambda *a, **k: b"X")
    with pytest.raises((stage.StageDenied, OSError)):
        stage.start_staging_console(window)
    assert lifecycle.releases == (1 if failure == "ack" else 0)
    assert all(child.closed for child in lifecycle.children)
    assert lifecycle.closed_handles and set(lifecycle.closed_handles) == {50000}
    assert (recovery.state / ("a" * 32 + ".recovery")).exists()
    assert recovery.claim.read_bytes() == b""
    # Restore only synthetic clock/IO seams, never remove/refund the consumed file.
    monkeypatch.setattr(stage, "datetime", original_clock)
    monkeypatch.setattr(recovery.files, "write", original_write)
    monkeypatch.setattr(recovery.files, "fsync", original_sync)
    with pytest.raises(stage.StageDenied, match="duplicate_recovery"):
        stage.start_staging_console(window)
    assert lifecycle.releases == (1 if failure == "ack" else 0)


def test_short_marker_writes_complete_before_release(recovery, lifecycle, monkeypatch):
    original = recovery.files.write
    counts = []

    def short(fd, data):
        if fd != 50001:
            counts.append(len(data))
            return original(fd, data[:7])
        return original(fd, data)

    monkeypatch.setattr(recovery.files, "write", short)
    assert (
        stage.start_staging_console(stage.select_console_window("a" * 32, persistent=True))[
            "status"
        ]
        == "stopped"
    )
    assert len(counts) > 2 and lifecycle.releases == 1
    marker = json.loads((recovery.state / ("a" * 32 + ".recovery")).read_bytes())
    assert marker["state"] == "ATTEMPTED"


def test_admission_reads_only_fixed_public_controls(recovery, monkeypatch, capsys):
    opened = []
    original = recovery.files.open

    def public_only(path, flags, mode=0o777, *, dir_fd=None):
        actual = recovery.files.path(path, dir_fd)
        assert actual in {recovery.path, recovery.prior, recovery.claim}, (
            "unexpected value read during admission"
        )
        opened.append(actual)
        return original(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(recovery.files, "open", public_only)
    assert stage.main(["--check-window", "--persistent", "--nonce", "a" * 32]) == 0
    capsys.readouterr()
    assert set(opened) == {recovery.path, recovery.prior, recovery.claim}


@pytest.mark.parametrize("object_name", ["path", "prior", "claim"])
def test_identical_bytes_in_replacement_object_cannot_reuse_recovery(
    recovery, lifecycle, object_name
):
    window = stage.select_console_window("a" * 32, persistent=True)

    def replace():
        target = getattr(recovery, object_name)
        replacement = target.with_suffix(".synthetic-replacement")
        replacement.write_bytes(target.read_bytes())
        replacement.replace(target)

    lifecycle.on_spawn = replace
    with pytest.raises(stage.StageDenied):
        stage.start_staging_console(window)
    assert lifecycle.releases == 0
    assert all(child.closed for child in lifecycle.children)
    assert not (recovery.state / ("a" * 32 + ".recovery")).exists()
