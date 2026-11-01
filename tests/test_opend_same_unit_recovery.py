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
ORIGINAL_ADMIT = stage._admit


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
        self.directory_info = {}
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
        if fd in self.directories:
            return self.info(self.directory_info[fd], self.directories[fd])
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
        self.directory_info[fd] = os.stat(path)
        try:
            yield fd
        finally:
            self.directories.pop(fd)
            self.directory_info.pop(fd)

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
    files.metadata[state] = {"uid": 1001, "gid": 1001, "mode": 0o700}
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


@pytest.mark.parametrize(
    "field", ["machine_sha256", "launcher_sha256", "vendor_sha256", "tmux_sha256"]
)
def test_identity_drift_during_marker_persistence_refuses_with_spent_attempt(
    recovery, lifecycle, monkeypatch, field
):
    window = stage.select_console_window("a" * 32, persistent=True)
    original = recovery.files.fsync

    def mutate(fd):
        original(fd)
        target = recovery.actor if field in recovery.actor else recovery.hashes
        target[field] = "0" * 64

    monkeypatch.setattr(recovery.files, "fsync", mutate)
    with pytest.raises(stage.StageDenied):
        stage.start_staging_console(window)
    assert lifecycle.releases == 0
    assert (recovery.state / ("a" * 32 + ".recovery")).exists()
    assert all(child.closed for child in lifecycle.children)


@pytest.mark.parametrize("change", ["inode", "uid", "gid", "mode", "nlink"])
def test_live_state_directory_drift_refuses_even_when_old_claim_fd_matches(
    recovery, lifecycle, monkeypatch, change
):
    window = stage.select_console_window("a" * 32, persistent=True)
    changed = False
    original_sync = recovery.files.fsync
    original_directory = recovery.files.directory

    def mutate(fd):
        nonlocal changed
        original_sync(fd)
        changed = True
        if change != "inode":
            recovery.files.metadata[recovery.state][change] = {
                "uid": 0,
                "gid": 0,
                "mode": 0o777,
                "nlink": 99,
            }[change]

    @contextmanager
    def current_directory(path):
        with original_directory(path) as fd:
            if changed and change == "inode":
                value = recovery.files.directory_info[fd]
                attributes = {
                    key: getattr(value, key) for key in dir(value) if key.startswith("st_")
                }
                attributes["st_ino"] += 1  # New live dir; existing dirfd keeps old identity.
                recovery.files.directory_info[fd] = SimpleNamespace(**attributes)
            yield fd

    monkeypatch.setattr(recovery.files, "fsync", mutate)
    monkeypatch.setattr(stage, "_owned_dir", current_directory)
    with pytest.raises(stage.StageDenied):
        stage.start_staging_console(window)
    assert lifecycle.releases == 0
    assert (recovery.state / ("a" * 32 + ".recovery")).exists()
    assert all(child.closed for child in lifecycle.children)


def test_authority_changed_during_post_persistence_admission_is_rechecked(
    recovery, lifecycle, monkeypatch
):
    window = stage.select_console_window("a" * 32, persistent=True)
    original = stage._admit

    def late_admission(candidate):
        result = original(candidate)
        if (recovery.state / ("a" * 32 + ".recovery")).exists():
            recovery.files.metadata[recovery.claim]["mode"] = 0o644
        return result

    monkeypatch.setattr(stage, "_admit", late_admission)
    with pytest.raises(stage.StageDenied):
        stage.start_staging_console(window)
    assert lifecycle.releases == 0
    assert (recovery.state / ("a" * 32 + ".recovery")).exists()
    assert all(child.closed for child in lifecycle.children)


@pytest.fixture
def private_recovery(recovery, tmp_path, monkeypatch):
    """Real control/lease/file IO plus explicit modeled Linux/vendor metadata."""
    from test_opend_private_storage import NONCE, PROFILE, ProfileWorld, layout, module

    spec = importlib.util.spec_from_file_location(
        "storage_profile_validator", Path(stage.__file__).parent / "validate_profile.py"
    )
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    guard = module()
    public_profile, snapshot = layout()
    world = ProfileWorld(public_profile, snapshot)
    monkeypatch.setattr(guard, "os", world.os)
    monkeypatch.setattr(guard, "open", world.open_file, raising=False)
    claim = recovery.state / NONCE
    claim.write_bytes(b"")
    recovery.files.metadata[claim] = {"uid": 997, "gid": 987, "mode": 0o600}
    recovery.files.metadata[recovery.state].update(uid=997, gid=987)
    recovery.actor.update(gateway_uid=997, gateway_gid=987)
    machine = b"SYNTHETIC_MACHINE_METADATA"
    machine_hash = hashlib.sha256(machine).hexdigest()
    monkeypatch.setattr(stage, "MACHINE_SHA", machine_hash)
    recovery.actor["machine_sha256"] = machine_hash
    recovery.claims.update(
        schema_version=4,
        nonce=NONCE,
        unit="quantmesh-opend-console@" + NONCE + ".service",
        gateway_uid=997,
        gateway_gid=987,
        machine_sha256=machine_hash,
        original_claim=identity(recovery.files, claim),
        storage_profile_sha256=hashlib.sha256(world.nodes[PROFILE].data).hexdigest(),
    )
    recovery.path.write_bytes(json.dumps(recovery.claims).encode())
    original_open = recovery.files.open

    def open_as_service(path, flags, mode=0o777, *, dir_fd=None):
        fd = original_open(path, flags, mode, dir_fd=dir_fd)
        if flags & os.O_CREAT:
            recovery.files.metadata[recovery.files.paths[fd]].update(uid=997, gid=987)
        return fd

    monkeypatch.setattr(recovery.files, "open", open_as_service)
    for name, value in {"getuid": 997, "geteuid": 997, "getgid": 987, "getegid": 987}.items():
        monkeypatch.setattr(recovery.files, name, lambda value=value: value, raising=False)
    monkeypatch.setattr(recovery.files, "getgroups", lambda: [987], raising=False)
    monkeypatch.setitem(
        sys.modules, "pwd", SimpleNamespace(getpwnam=lambda n: SimpleNamespace(pw_uid=997))
    )
    monkeypatch.setitem(
        sys.modules, "grp", SimpleNamespace(getgrnam=lambda n: SimpleNamespace(gr_gid=987))
    )
    monkeypatch.setattr(stage, "_native", lambda **kw: None)
    monkeypatch.setattr(stage, "_admit", ORIGINAL_ADMIT)
    old_module = stage._module

    def modules(path, digest):
        if path.name == "private_storage.py":
            assert (
                digest
                == hashlib.sha256(
                    (Path(stage.__file__).parent / path.name).read_bytes()
                ).hexdigest()
            )
            return guard
        if path.name == "validate_profile.py":
            return validator
        if path.name == "same_unit_recovery.py":
            return old_module(path, digest)
        return SimpleNamespace()  # Terminal helper is never executed by check-window.

    monkeypatch.setattr(stage, "_module", modules)
    candidate_profile = (Path(stage.__file__).parent / "gateway-profile.json").read_bytes()
    monkeypatch.setattr(
        stage,
        "_bytes",
        lambda path, digest=None: (
            candidate_profile
            if path == stage.PROFILE
            else validator.reviewed_configuration()
            if path == stage.CONFIG
            else machine
        ),
    )
    monkeypatch.setattr(
        stage,
        "_digest",
        lambda path: (
            stage.RECOVERY_SHA
            if path.name == "same_unit_recovery.py"
            else stage.VENDOR_SHA
            if path == stage.VENDOR
            else stage.TMUX_SHA
            if path.name == "tmux"
            else "c" * 64
        ),
    )
    monkeypatch.setattr(
        stage, "_vendor_tree", lambda path: None
    )  # Immutable installation metadata only.
    home = tmp_path / "synthetic-home"
    home.mkdir()
    recovery.files.metadata[home] = {"uid": 997, "gid": 987, "mode": 0o700}
    directory = recovery.files.directory
    monkeypatch.setattr(
        stage,
        "_owned_dir",
        lambda path: directory(home if path == Path("/var/lib/quantmesh-opend") else path),
    )
    from test_opend_diagnostic_1 import configure_diagnostic

    configure_diagnostic(recovery, tmp_path, monkeypatch)
    result = SimpleNamespace(recovery=recovery, world=world, guard=guard, nonce=NONCE, claim=claim)
    yield result
    assert not world.handles


@pytest.mark.parametrize("change", [None, "profile_bytes", "old_schema3"])
def test_original_c8_check_requires_the_bound_live_private_storage(
    private_recovery, capsys, change
):
    from test_opend_private_storage import PROFILE

    fixture = private_recovery
    if change == "profile_bytes":
        node = fixture.world.nodes[PROFILE]
        node.data += b" "
        node.info.st_size += 1
    elif change == "old_schema3":
        fixture.recovery.claims["schema_version"] = 3
        fixture.recovery.claims.pop("storage_profile_sha256")
        fixture.recovery.path.write_bytes(json.dumps(fixture.recovery.claims).encode())
    result = stage.main(["--check-window", "--persistent", "--nonce", fixture.nonce])
    assert result == (0 if change is None else 2)
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == ("admitted" if change is None else "pending")
    assert fixture.claim.read_bytes() == b""
    assert not (fixture.recovery.state / (fixture.nonce + ".diagnostic-1.recovery")).exists()


@pytest.mark.parametrize(
    "change",
    [
        None,
        "DropInPaths",
        "PrivateMounts",
        "MountFlags_missing",
        "MountFlags_empty",
        "MountFlags_shared",
        "MountFlags_slave",
        "MountFlags_unknown",
        "MemoryPressureWatch_missing",
        "MemoryPressureWatch_empty",
        "MemoryPressureWatch_on",
        "MemoryPressureWatch_auto",
        "MemoryPressureWatch_unknown",
        "PrivateTmp",
        "StateDirectory",
        "RuntimeDirectoryPreserve",
        "ReadOnlyPaths_missing",
        "ReadOnlyPaths_empty",
        "ReadOnlyPaths_wrong",
        "ReadOnlyPaths_without_pool",
        "ReadOnlyPaths_without_run",
        "ReadOnlyPaths_without_hugepages",
        "ReadOnlyPaths_extra",
        "ReadOnlyPaths_duplicate",
        "ReadWritePaths",
        "ProtectSystem",
        "dropin_bytes",
    ],
)
def test_c8_manager_requires_only_its_exact_storage_dropin(
    private_recovery, lifecycle, monkeypatch, change
):
    nonce = private_recovery.nonce
    unit = "quantmesh-opend-console@" + nonce + ".service"
    dropin = "/etc/systemd/system/" + unit + ".d/30-private-storage.conf"
    runtime = "quantmesh-opend-console-" + nonce
    properties = dict(stage.MANAGER_FIXED)
    properties.update(
        RuntimeMaxUSec="infinity",
        FragmentPath="/etc/systemd/system/quantmesh-opend-console@.service",
        MemoryMax="1073741824",
        MemoryHigh="805306368",
        MemorySwapMax="0",
        CPUQuotaPerSecUSec="500ms",
        TasksMax="128",
        Id=unit,
        MainPID="7",
        ActiveState="active",
        ControlGroup=r"/system.slice/system-quantmesh-opend-console.slice/" + unit,
        RuntimeDirectory=runtime,
        DropInPaths=dropin,
        PrivateMounts="yes",
        MountFlags="private",
        MemoryPressureWatch="off",
        PrivateTmp="no",
        StateDirectory="",
        RuntimeDirectoryPreserve="yes",
        ProtectSystem="strict",
        ReadOnlyPaths=(
            "/run/quantmesh-opend-storage-c8f0d0de4ca641a491fca6df24c66ceb /run /dev/hugepages"
        ),
        ReadWritePaths=(
            "/var/lib/quantmesh-opend /var/lib/quantmesh-opend-stage "
            f"/run/{runtime} /tmp /var/tmp /dev/shm"
        ),
    )
    values = {
        properties["FragmentPath"]: (
            Path(stage.__file__).parent / "quantmesh-opend-console@.service"
        ).read_bytes(),
        dropin: (
            Path(stage.__file__).parent / "quantmesh-opend-console-c8-private-storage.conf"
        ).read_bytes(),
    }
    if change == "dropin_bytes":
        values[dropin] += b"# drift\n"
    elif change == "MountFlags_missing":
        del properties["MountFlags"]
    elif change and change.startswith("MountFlags_"):
        properties["MountFlags"] = {
            "MountFlags_empty": "",
            "MountFlags_shared": "shared",
            "MountFlags_slave": "slave",
            "MountFlags_unknown": "unrecognized",
        }[change]
    elif change == "MemoryPressureWatch_missing":
        del properties["MemoryPressureWatch"]
    elif change and change.startswith("MemoryPressureWatch_"):
        properties["MemoryPressureWatch"] = {
            "MemoryPressureWatch_empty": "",
            "MemoryPressureWatch_on": "on",
            "MemoryPressureWatch_auto": "auto",
            "MemoryPressureWatch_unknown": "unrecognized",
        }[change]
    elif change == "ReadOnlyPaths_missing":
        del properties["ReadOnlyPaths"]
    elif change and change.startswith("ReadOnlyPaths_"):
        properties["ReadOnlyPaths"] = {
            "ReadOnlyPaths_empty": "",
            "ReadOnlyPaths_wrong": "/run/foreign-storage",
            "ReadOnlyPaths_without_pool": "/run /dev/hugepages",
            "ReadOnlyPaths_without_run": (
                "/run/quantmesh-opend-storage-c8f0d0de4ca641a491fca6df24c66ceb /dev/hugepages"
            ),
            "ReadOnlyPaths_without_hugepages": (
                "/run/quantmesh-opend-storage-c8f0d0de4ca641a491fca6df24c66ceb /run"
            ),
            "ReadOnlyPaths_extra": properties["ReadOnlyPaths"] + " /host-extra",
            "ReadOnlyPaths_duplicate": properties["ReadOnlyPaths"]
            + " "
            + properties["ReadOnlyPaths"],
        }[change]
    elif change:
        properties[change] = {
            "DropInPaths": dropin + " /foreign.conf",
            "PrivateMounts": "no",
            "PrivateTmp": "yes",
            "StateDirectory": "quantmesh-opend-stage",
            "RuntimeDirectoryPreserve": "no",
            "ReadWritePaths": properties["ReadWritePaths"] + " /host-escape",
            "ProtectSystem": "no",
        }[change]

    admitted_bytes = stage._bytes

    def public_bytes(path, digest=None):
        if path.as_posix() not in values:
            return admitted_bytes(path, digest)
        raw = values[path.as_posix()]
        if hashlib.sha256(raw).hexdigest() != digest:
            raise stage.StageDenied("pin_drift")
        return raw

    def manager_output(argv):
        assert argv[0] == "/usr/bin/systemctl" and argv[-1] == unit
        names = next(x.split("=", 1)[1] for x in argv if x.startswith("--property=")).split(",")
        return "\n".join(key + "=" + properties[key] for key in names if key in properties)

    monkeypatch.setattr(stage, "_bytes", public_bytes)
    monkeypatch.setattr(stage, "_command", manager_output)
    window = stage.select_console_window(nonce, persistent=True)
    if change:
        # Exercise the actual start boundary before child creation and marker consumption.
        # The external terminal/backend inspection seam still calls the real manager gate.
        before = (
            private_recovery.claim.read_bytes(),
            identity(private_recovery.recovery.files, private_recovery.claim),
            private_recovery.recovery.prior.read_bytes(),
            private_recovery.recovery.path.read_bytes(),
        )
        backend_context = stage.inspect_staging_context

        def checked_context(w):
            stage._manager(w)
            return backend_context(w)

        monkeypatch.setattr(stage, "inspect_staging_context", checked_context)
        with pytest.raises(stage.StageDenied, match="^backend_denied$|^pin_drift$"):
            stage.start_staging_console(window)
        assert lifecycle.children == []
        assert lifecycle.releases == 0
        assert not (private_recovery.recovery.state / (nonce + ".diagnostic-1.recovery")).exists()
        assert before == (
            private_recovery.claim.read_bytes(),
            identity(private_recovery.recovery.files, private_recovery.claim),
            private_recovery.recovery.prior.read_bytes(),
            private_recovery.recovery.path.read_bytes(),
        )
    else:
        observed = stage._manager(window)
        assert observed["DropInPaths"] == dropin
        assert observed["MountFlags"] == "private"
        assert observed["MemoryPressureWatch"] == "off"
        assert observed["ControlGroup"].startswith(
            r"/system.slice/system-quantmesh-opend-console.slice/"
        )


@pytest.mark.parametrize("late_drift", [False, True])
def test_storage_guard_rechecks_after_marker_persistence_before_the_existing_gate(
    private_recovery, lifecycle, monkeypatch, late_drift
):
    fixture = private_recovery
    window = stage.select_console_window(fixture.nonce, persistent=True)
    original_sync = fixture.recovery.files.fsync

    def sync(fd):
        original_sync(fd)
        if late_drift and fixture.recovery.files.paths.get(fd) == (
            fixture.recovery.state / (fixture.nonce + ".diagnostic-1.recovery")
        ):
            fixture.world.values["/sys/block/loop8/loop/sizelimit"] = b"0\n"

    monkeypatch.setattr(fixture.recovery.files, "fsync", sync)
    if late_drift:
        with pytest.raises(stage.StageDenied, match="storage_denied"):
            stage.start_staging_console(window)
        assert lifecycle.releases == 0
    else:
        assert stage.start_staging_console(window)["status"] == "stopped"
        assert lifecycle.releases == 1
    assert (fixture.recovery.state / (fixture.nonce + ".diagnostic-1.recovery")).exists()
    assert all(child.closed for child in lifecycle.children)
    assert fixture.claim.read_bytes() == b""


@pytest.mark.parametrize(
    "change",
    [
        "missing_digest",
        "invalid_digest",
        "boolean_digest",
        "foreign_nonce",
        "foreign_uid",
        "foreign_gid",
        "extra_flag",
    ],
)
def test_private_recovery_authority_is_closed_and_cannot_transfer(private_recovery, capsys, change):
    fixture = private_recovery
    c = fixture.recovery.claims
    nonce = fixture.nonce
    if change == "missing_digest":
        c.pop("storage_profile_sha256")
    elif change == "invalid_digest":
        c["storage_profile_sha256"] = "not-a-digest"
    elif change == "boolean_digest":
        c["storage_profile_sha256"] = True
    elif change == "foreign_nonce":
        nonce = c["nonce"] = "a" * 32
        c["unit"] = "quantmesh-opend-console@" + nonce + ".service"
    elif change == "foreign_uid":
        c["gateway_uid"] = 1001
    elif change == "foreign_gid":
        c["gateway_gid"] = 1001
    else:
        c["storage_verified"] = True
    fixture.recovery.path.write_bytes(json.dumps(c).encode())
    assert stage.main(["--check-window", "--persistent", "--nonce", nonce]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "pending"
    assert not fixture.world.reads
    assert not (fixture.recovery.state / (fixture.nonce + ".diagnostic-1.recovery")).exists()


def test_storage_dropin_exemption_is_not_available_to_initial_or_other_recovery():
    initial = persistent_permit()
    initial["nonce"] = "c8f0d0de4ca641a491fca6df24c66ceb"
    windows = [stage.StagingWindow(initial), stage.RecoveryWindow(SimpleNamespace(nonce="a" * 32))]
    for window in windows:
        contract = stage._manager_contract(window)
        assert contract["DropInPaths"] == ""
        assert "PrivateMounts" not in contract
        assert "MountFlags" not in contract
        assert "MemoryPressureWatch" not in contract
