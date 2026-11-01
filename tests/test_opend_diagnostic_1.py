"""Fixed diagnostic authority controls on public synthetic files; never a host start."""

import copy
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import pytest
from test_opend_same_unit_recovery import NOW, identity
from test_opend_same_unit_recovery import lifecycle as lifecycle
from test_opend_same_unit_recovery import private_recovery as private_recovery
from test_opend_same_unit_recovery import recovery as recovery
from test_opend_staging_window import stage

C8 = "c8f0d0de4ca641a491fca6df24c66ceb"


@pytest.fixture
def diagnostic(recovery, tmp_path, monkeypatch):
    return configure_diagnostic(recovery, tmp_path, monkeypatch)


def configure_diagnostic(recovery, tmp_path, monkeypatch):
    files = recovery.files
    claim = recovery.state / C8
    claim.write_bytes(b"")
    files.metadata[claim] = dict(uid=997, gid=987, mode=0o600)
    files.metadata[recovery.state].update(uid=997, gid=987)
    recovery.actor.update(gateway_uid=997, gateway_gid=987)
    old = copy.deepcopy(recovery.claims)
    old.update(
        schema_version=4,
        nonce=C8,
        unit="quantmesh-opend-console@" + C8 + ".service",
        gateway_uid=997,
        gateway_gid=987,
        original_claim=identity(files, claim),
        storage_profile_sha256=old.get("storage_profile_sha256", "e" * 64),
    )
    history = tmp_path / "protected-history.json"
    history.write_bytes(json.dumps(old, sort_keys=True).encode())
    files.metadata[history] = dict(uid=0, gid=0, mode=0o444)
    old_digest = hashlib.sha256(history.read_bytes()).hexdigest()
    marker = recovery.state / (C8 + ".recovery")
    marker.write_bytes(
        (
            json.dumps(
                dict(
                    schema_version=1,
                    state="ATTEMPTED",
                    purpose="opend_same_unit_recovery_consumed",
                    nonce=C8,
                    control_sha256=old_digest,
                ),
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
    )
    files.metadata[marker] = dict(uid=997, gid=987, mode=0o600)
    claims = copy.deepcopy(old)
    claims.update(
        schema_version=5,
        purpose="opend_fixed_diagnostic_recovery",
        max_seconds=90,
        session_lifetime="bounded_diagnostic",
        diagnostic_id="diagnostic-1",
        spent_recovery={
            "control": {"identity": identity(files, history), "sha256": old_digest},
            "marker": {
                "identity": identity(files, marker),
                "sha256": hashlib.sha256(marker.read_bytes()).hexdigest(),
            },
        },
    )
    recovery.path.write_bytes(json.dumps(claims).encode())
    monkeypatch.setattr(stage, "RECOVERY_HISTORY", history, raising=False)
    module_loader = stage._module
    pinned_history = old_digest
    pinned_marker = claims["spent_recovery"]["marker"]["sha256"]

    def synthetic_pins(path, digest):
        module = module_loader(path, digest)
        if path.name == "same_unit_recovery.py":
            # Test-only public fixture seam; no production configuration override.
            monkeypatch.setattr(module, "DIAGNOSTIC_HISTORY_SHA", pinned_history, raising=False)
            monkeypatch.setattr(module, "DIAGNOSTIC_MARKER_SHA", pinned_marker, raising=False)
        return module

    monkeypatch.setattr(stage, "_module", synthetic_pins)
    recovery.real_module_loader = module_loader
    opened = files.open
    new_marker = recovery.state / (C8 + ".diagnostic-1.recovery")

    def open_owned(path, flags, mode=0o777, **kwargs):
        fd = opened(path, flags, mode, **kwargs)
        if files.path(path, kwargs.get("dir_fd")) == new_marker:
            files.metadata[new_marker].update(uid=997, gid=987)
        return fd

    monkeypatch.setattr(files, "open", open_owned)
    recovery.claim = claim
    recovery.claims = claims
    recovery.history = history
    recovery.old_marker = marker
    recovery.new_marker = new_marker
    recovery.old_claims = old
    return recovery


def load(d):
    return stage.select_console_window(C8, persistent=True).control


def originals(d):
    return {
        p: (p.read_bytes(), identity(d.files, p))
        for p in (d.claim, d.prior, d.history, d.old_marker)
    }


def test_fixed_diagnostic_check_admits_without_any_consumption(diagnostic, capsys):
    before = originals(diagnostic)
    assert stage.main(["--check-window", "--persistent", "--nonce", C8]) == 0
    assert json.loads(capsys.readouterr().out)["scope"] == "STAGING_WINDOW_ONLY"
    assert originals(diagnostic) == before and not diagnostic.new_marker.exists()


def test_new_marker_only_is_consumed_and_never_refunded(diagnostic):
    before = originals(diagnostic)
    control = load(diagnostic)
    with control.release_lease() as lease:
        lease.consume()
    assert originals(diagnostic) == before
    assert json.loads(diagnostic.new_marker.read_bytes())["control_sha256"] == control.digest
    diagnostic.claims["expires_at"] = (NOW + timedelta(seconds=65)).isoformat()
    diagnostic.path.write_bytes(json.dumps(diagnostic.claims).encode())
    with pytest.raises(stage.StageDenied, match="^duplicate_recovery$"):
        load(diagnostic).check_available()


def test_concurrent_fixed_diagnostic_consumes_at_most_once(diagnostic):
    control = load(diagnostic)

    def consume():
        try:
            with control.release_lease() as lease:
                lease.consume()
            return "consumed"
        except stage.StageDenied as e:
            return e.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: consume(), range(2)))
    assert sorted(outcomes) == ["consumed", "duplicate_recovery"]


@pytest.mark.parametrize("schema", [3, 4])
def test_old_c8_authority_stays_spent_even_if_marker_name_missing(
    diagnostic, monkeypatch, capsys, schema
):
    old = copy.deepcopy(diagnostic.old_claims)
    old["schema_version"] = schema
    if schema == 3:
        old.pop("storage_profile_sha256")
    diagnostic.path.write_bytes(json.dumps(old).encode())
    stat = diagnostic.files.stat

    def hidden(name, **kwargs):
        if diagnostic.files.path(name, kwargs.get("dir_fd")) == diagnostic.old_marker:
            raise FileNotFoundError
        return stat(name, **kwargs)

    monkeypatch.setattr(diagnostic.files, "stat", hidden)
    assert stage.main(["--check-window", "--persistent", "--nonce", C8]) == 2
    assert not diagnostic.new_marker.exists()
    capsys.readouterr()


@pytest.mark.parametrize(
    "change",
    [
        lambda c: c.update(diagnostic_id="diagnostic-2"),
        lambda c: c.update(generation=1),
        lambda c: c.update(max_seconds=180),
        lambda c: c.update(session_lifetime="until_operator_stop"),
        lambda c: c.update(expires_at=(NOW + timedelta(seconds=90)).isoformat()),
        lambda c: c["spent_recovery"]["marker"].update(sha256="f" * 64),
        lambda c: c["spent_recovery"]["control"]["identity"].update(inode=1),
    ],
)
def test_invalid_diagnostic_cannot_release_or_change_old_state(diagnostic, capsys, change):
    before = originals(diagnostic)
    candidate = copy.deepcopy(diagnostic.claims)
    change(candidate)
    diagnostic.path.write_bytes(json.dumps(candidate).encode())
    assert stage.main(["--check-window", "--persistent", "--nonce", C8]) == 2
    assert originals(diagnostic) == before and not diagnostic.new_marker.exists()
    capsys.readouterr()


@pytest.mark.parametrize(
    "which,damage",
    [
        ("history", "partial"),
        ("old_marker", "partial"),
        ("old_marker", "wrongowner"),
        ("old_marker", "nlink"),
        ("history", "writable"),
    ],
)
def test_old_evidence_must_remain_complete_and_held_matching(diagnostic, which, damage):
    p = getattr(diagnostic, which)
    if damage == "partial":
        p.write_bytes(b"{")
    elif damage == "wrongowner":
        diagnostic.files.metadata[p]["uid"] = 0
    elif damage == "nlink":
        diagnostic.files.metadata[p]["nlink"] = 2
    else:
        diagnostic.files.metadata[p]["mode"] = 0o644
    with pytest.raises(stage.StageDenied):
        load(diagnostic).check_available()
    assert not diagnostic.new_marker.exists()


@pytest.mark.parametrize("failure", ["partial", "file_fsync", "dir_fsync"])
def test_created_diagnostic_marker_is_spent_after_io_failure(diagnostic, monkeypatch, failure):
    written = diagnostic.files.write
    sync = diagnostic.files.fsync
    calls = []

    def write(fd, data):
        if diagnostic.files.paths.get(fd) == diagnostic.new_marker and failure == "partial":
            if not calls:
                calls.append(True)
                return written(fd, data[:1])
            raise OSError(28, "synthetic")
        return written(fd, data)

    def fsync(fd):
        if (
            failure == "file_fsync" and diagnostic.files.paths.get(fd) == diagnostic.new_marker
        ) or (failure == "dir_fsync" and fd in diagnostic.files.directories):
            raise OSError(5, "synthetic")
        return sync(fd)

    monkeypatch.setattr(diagnostic.files, "write", write)
    monkeypatch.setattr(diagnostic.files, "fsync", fsync)
    control = load(diagnostic)
    with pytest.raises((OSError, stage.StageDenied)):
        with control.release_lease() as lease:
            lease.consume()
    assert diagnostic.new_marker.exists()
    with pytest.raises(stage.StageDenied, match="^duplicate_recovery$"):
        control.check_available()


def test_fixed5_witness_and_runtime_are_bounded_not_generic(diagnostic):
    window = stage.RecoveryWindow(load(diagnostic))
    assert stage._witness_enabled(window, window.claims)
    assert stage._runtime_persistent(window) is False
    old = stage.StagingWindow({"schema_version": 2})
    assert stage._runtime_persistent(old) is True


@pytest.mark.parametrize("wall_rollback", [False, True])
def test_diagnostic_total_deadline_is_not_rebased_after_load_or_release(
    diagnostic, lifecycle, monkeypatch, wall_rollback
):
    clock = [100.0]
    monkeypatch.setattr(stage, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    window = stage.RecoveryWindow(load(diagnostic))
    assert window.control.runtime_deadline == 160.0  # Signed expiry NOW+60, not a new 90s.
    clock[0] = 110.0
    if wall_rollback:

        def rollback_after_gate():
            monkeypatch.setattr(
                stage,
                "datetime",
                SimpleNamespace(
                    now=lambda tz: NOW - timedelta(seconds=10),
                    fromisoformat=stage.datetime.fromisoformat,
                ),
            )

        lifecycle.on_gate = rollback_after_gate
    spawn = stage._spawn_gated
    calls = []

    def bounded_spawn(*a, **kw):
        calls.append(kw.copy())
        child = spawn(*a, **kw)
        child.alive = lambda: not child.closed
        return child

    def wait(read, write, error, timeout):
        if timeout:
            clock[0] += timeout
        return [], [], []

    monkeypatch.setattr(stage, "_spawn_gated", bounded_spawn)
    monkeypatch.setattr(stage.select, "select", wait)
    result = stage.start_staging_console(window)
    assert result["scope"] == "BOUNDED_DIAGNOSTIC_ONLY"
    assert calls[0]["diagnostic_deadline"] == 160.0
    assert not calls[0].get("persistent", False)
    assert clock[0] == pytest.approx(160.0)
    assert lifecycle.releases == 1 and lifecycle.closed_handles
    assert all(c.closed and c.terminal for c in lifecycle.children)


def test_diagnostic_expiry_during_consume_cannot_release_or_refresh_budget(
    diagnostic, lifecycle, monkeypatch
):
    clock = [100.0]
    monkeypatch.setattr(stage, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    window = stage.RecoveryWindow(load(diagnostic))
    sync = diagnostic.files.fsync

    def delayed(fd):
        sync(fd)
        if diagnostic.files.paths.get(fd) == diagnostic.new_marker:
            clock[0] = 162.0

    monkeypatch.setattr(diagnostic.files, "fsync", delayed)
    with pytest.raises(stage.StageDenied, match="^deadline$"):
        stage.start_staging_console(window)
    assert diagnostic.new_marker.exists() and lifecycle.releases == 0
    assert all(c.closed for c in lifecycle.children) and lifecycle.closed_handles


def _observe_child(monkeypatch, deadline, now, seconds=90):
    # Actual child function, modeled OS only: never fork/exec/signal a native process.
    class Exit(BaseException):
        pass

    events = []
    fake_os = SimpleNamespace(
        getppid=lambda: 12,
        close=lambda fd: None,
        dup2=lambda *a: None,
        read=lambda *a: b"R",
        write=lambda fd, b: events.append(("write", b)),
        chdir=lambda p: events.append(("chdir",)),
        execve=lambda *a: (_ for _ in ()).throw(Exit("exec")),
        _exit=lambda rc: (_ for _ in ()).throw(Exit(rc)),
    )
    monkeypatch.setattr(stage, "os", fake_os)
    monkeypatch.setattr(stage, "_WITNESS", None)
    monkeypatch.setattr(stage, "_prctl", lambda *a: None)
    monkeypatch.setattr(stage.Path, "iterdir", lambda p: iter(()))
    monkeypatch.setattr(stage, "time", SimpleNamespace(monotonic=lambda: now))
    monkeypatch.setattr(
        stage,
        "signal",
        SimpleNamespace(
            SIGINT=2,
            SIGTERM=15,
            SIGHUP=1,
            SIGALRM=14,
            SIG_DFL=0,
            SIGKILL=9,
            SIG_SETMASK=2,
            ITIMER_REAL=0,
            signal=lambda *a: None,
            pthread_sigmask=lambda *a: None,
            setitimer=lambda which, value: events.append(("alarm", value)),
        ),
    )
    monkeypatch.setattr(stage.select, "select", lambda *a: ([1], [], []))
    monkeypatch.setattr(stage, "_child_fail", lambda fd, kind, *a: events.append(("failure", kind)))
    with pytest.raises(Exit):
        stage._child(
            4, 5, (0, 1, 2), seconds, 12, False, "blocked", 6, [], diagnostic_deadline=deadline
        )
    return events


@pytest.mark.parametrize("remaining", [0.375, 0, -1])
def test_child_alarm_uses_same_fractional_remaining_budget_before_ack_exec(monkeypatch, remaining):
    events = _observe_child(monkeypatch, 20 + remaining, 20)
    if remaining > 0:
        assert events[:3] == [("alarm", 0.375), ("write", b"R"), ("chdir",)]
    else:
        assert not any(e[0] in {"alarm", "write", "chdir"} for e in events)
        assert events[0] == ("failure", "DEADLINE")


@pytest.mark.parametrize("value", [float("inf"), float("nan"), True])
def test_actual_spawn_rejects_invalid_internal_deadline_before_pipe(monkeypatch, value):
    monkeypatch.setattr(stage, "_native", lambda: None)
    monkeypatch.setattr(stage.os, "pipe", lambda: pytest.fail("invalid deadline reached pipe"))
    with pytest.raises(stage.StageDenied, match="^context_denied$"):
        stage._spawn_gated(None, fixture=True, seconds=1, diagnostic_deadline=value)


def test_actual_spawn_accepts_absolute_deadline_interface_before_owned_setup(monkeypatch):
    monkeypatch.setattr(stage, "_native", lambda: None)
    calls = []

    def no_pipe():
        calls.append(True)
        raise OSError(24, "synthetic descriptor exhaustion")

    monkeypatch.setattr(stage.os, "pipe", no_pipe)
    with pytest.raises(stage.StageDenied, match="^missing_handle$"):
        stage._spawn_gated(None, fixture=True, seconds=1, diagnostic_deadline=20.375)
    assert calls == [True]


@pytest.mark.parametrize(
    "schema,identifier,allowed",
    [
        (4, None, True),
        (5, "diagnostic-1", True),
        (5, None, False),
        (5, "diagnostic-2", False),
        (6, "diagnostic-1", False),
    ],
)
def test_real_storage_gate_only_extends_eligibility_to_fixed5(
    private_recovery, schema, identifier, allowed
):
    f = private_recovery
    claims = dict(f.recovery.claims, schema_version=schema)
    if identifier is None:
        claims.pop("diagnostic_id", None)
    else:
        claims["diagnostic_id"] = identifier
    if allowed:
        assert f.guard.validate_live(claims) is None
    else:
        with pytest.raises(f.guard.StorageDenied, match="^storage_control$"):
            f.guard.validate_live(claims)
    assert not f.recovery.new_marker.exists()


@pytest.mark.parametrize("stage_of_drift", ["held_before_consume", "during_new_marker_fsync"])
def test_historical_evidence_drift_never_releases_new_authority(
    diagnostic, monkeypatch, stage_of_drift
):
    control = load(diagnostic)
    sync = diagnostic.files.fsync

    def changed():
        diagnostic.files.metadata[diagnostic.old_marker]["mode"] = 0o644

    def drift_on_sync(fd):
        sync(fd)
        if diagnostic.files.paths.get(fd) == diagnostic.new_marker:
            changed()

    if stage_of_drift == "during_new_marker_fsync":
        monkeypatch.setattr(diagnostic.files, "fsync", drift_on_sync)
    with pytest.raises(stage.StageDenied):
        with control.release_lease() as lease:
            if stage_of_drift == "held_before_consume":
                changed()
            lease.consume()
    assert diagnostic.new_marker.exists() is (stage_of_drift == "during_new_marker_fsync")
    assert diagnostic.old_marker.exists() and diagnostic.history.exists()


def test_diagnostic_deadline_frame_is_distinct_and_fragment_never_complete():
    frame = stage._child_failure_frame("DEADLINE", 0, 1234)
    assert stage._decode_child_frames(frame) == [dict(kind="DEADLINE", errno=0, monotonic_ns=1234)]
    assert stage._decode_child_frames(frame[:-1]) is None


@pytest.mark.parametrize("replacement", ["pair", "whitespace"])
def test_r1_fixed_historical_pins_reject_self_consistent_replacement(diagnostic, replacement):
    if replacement == "pair":
        old = json.loads(diagnostic.history.read_bytes())
        old["launcher_sha256"] = "d" * 64
        diagnostic.history.write_bytes(json.dumps(old, sort_keys=True).encode())
        digest = hashlib.sha256(diagnostic.history.read_bytes()).hexdigest()
        marker = json.loads(diagnostic.old_marker.read_bytes())
        marker["control_sha256"] = digest
        diagnostic.old_marker.write_bytes(json.dumps(marker, sort_keys=True).encode())
        diagnostic.claims["spent_recovery"]["control"] = dict(
            identity=identity(diagnostic.files, diagnostic.history), sha256=digest
        )
    else:
        diagnostic.old_marker.write_bytes(b" " + diagnostic.old_marker.read_bytes() + b" ")
    diagnostic.claims["spent_recovery"]["marker"] = dict(
        identity=identity(diagnostic.files, diagnostic.old_marker),
        sha256=hashlib.sha256(diagnostic.old_marker.read_bytes()).hexdigest(),
    )
    diagnostic.path.write_bytes(json.dumps(diagnostic.claims).encode())
    with pytest.raises(stage.StageDenied):
        load(diagnostic).check_available()
    assert not diagnostic.new_marker.exists()


def test_r1_production_evidence_hashes_are_independent_of_control(diagnostic):
    module = diagnostic.real_module_loader(stage.BASE / "same_unit_recovery.py", stage.RECOVERY_SHA)
    assert (
        module.DIAGNOSTIC_HISTORY_SHA
        == "8247e05ca30e7118e9a1494b31f11292502f072a1b86f119e260b71707a71afb"
    )
    assert (
        module.DIAGNOSTIC_MARKER_SHA
        == "544e4f73d22b061926d665f207265f2cf11fd9ce974f45bc62d9b4074fb6acae"
    )
    with pytest.raises(stage.StageDenied):
        module.load(stage, C8)


def test_r1_clock_sampling_stall_never_adds_monotonic_budget(diagnostic, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(stage, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    def delayed_wall(tz):
        clock[0] += 7
        return NOW

    monkeypatch.setattr(
        stage,
        "datetime",
        SimpleNamespace(now=delayed_wall, fromisoformat=stage.datetime.fromisoformat),
    )
    control = load(diagnostic)
    assert control.runtime_deadline == 160.0


@pytest.mark.parametrize("gate_now", [110.75, 115.25, 115.5])
def test_r1_forward_wall_step_passes_same_effective_deadline_to_child(
    diagnostic, lifecycle, monkeypatch, gate_now
):
    clock = [100.0]
    monkeypatch.setattr(stage, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    window = stage.RecoveryWindow(load(diagnostic))
    assert window.control.runtime_deadline == 160.0
    clock[0] = 110.0
    monkeypatch.setattr(
        stage,
        "datetime",
        SimpleNamespace(
            now=lambda tz: NOW + timedelta(seconds=54.75),
            fromisoformat=stage.datetime.fromisoformat,
        ),
    )
    original = stage._spawn_gated
    seen = []

    def spawn(*a, **kw):
        seen.append(kw)
        return original(*a, **kw)

    monkeypatch.setattr(stage, "_spawn_gated", spawn)
    stage.start_staging_console(window)
    assert seen[0]["diagnostic_deadline"] == 115.25
    events = _observe_child(
        monkeypatch, seen[0]["diagnostic_deadline"], gate_now, seen[0]["seconds"]
    )
    if gate_now < 115.25:
        assert events[:3] == [("alarm", 4.5), ("write", b"R"), ("chdir",)]
    else:
        assert events[0] == ("failure", "DEADLINE")
        assert not any(row[0] in {"alarm", "write", "chdir"} for row in events)


@pytest.mark.parametrize("clock_kind", ["wall", "monotonic"])
def test_r1_evidence_read_expiry_leaves_unused_marker_absent(diagnostic, monkeypatch, clock_kind):
    clock = [100.0]
    wall = [NOW]
    monkeypatch.setattr(stage, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(
        stage,
        "datetime",
        SimpleNamespace(now=lambda tz: wall[0], fromisoformat=stage.datetime.fromisoformat),
    )
    control = load(diagnostic)
    original = diagnostic.files.read
    armed = [False]

    def read(fd, size):
        value = original(fd, size)
        if armed[0] and diagnostic.files.paths.get(fd) == diagnostic.old_marker:
            if clock_kind == "wall":
                wall[0] = NOW + timedelta(seconds=61)
            else:
                clock[0] = 161.0
        return value

    monkeypatch.setattr(diagnostic.files, "read", read)
    with pytest.raises(stage.StageDenied):
        with control.release_lease() as lease:
            armed[0] = True
            lease.consume()
    assert not diagnostic.new_marker.exists()


def test_r1_consume_uses_caller_earlier_effective_deadline(diagnostic, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(stage, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    control = load(diagnostic)
    with control.release_lease(deadline=105.25) as lease:
        clock[0] = 105.25
        with pytest.raises(stage.StageDenied):
            lease.consume()
    assert not diagnostic.new_marker.exists()


@pytest.mark.parametrize("size", [4096, 4097])
def test_r1_admission_and_witness_share_fixed5_size_boundary(diagnostic, monkeypatch, capsys, size):
    raw = json.dumps(diagnostic.claims).encode()
    assert len(raw) < 4096
    diagnostic.path.write_bytes(raw + b" " * (size - len(raw)))
    expected = 0 if size == 4096 else 2
    assert stage.main(["--check-window", "--persistent", "--nonce", C8]) == expected
    capsys.readouterr()
    protected = stage._protected_fd
    monkeypatch.setattr(
        stage, "_protected_fd", lambda p: protected(diagnostic.path if p == stage.LAUNCHER else p)
    )
    monkeypatch.setattr(stage, "_digest_fd", lambda fd: "c" * 64)
    unit = "quantmesh-opend-console@" + C8 + ".service"
    monkeypatch.setattr(
        stage,
        "_command",
        lambda a: (
            "Id="
            + unit
            + "\nInvocationID="
            + "a" * 32
            + "\nControlGroup=/system.slice/fixed\nMainPID=7"
        ),
    )
    monkeypatch.setattr(stage, "_cgroup", lambda who: "/system.slice/fixed")
    monkeypatch.setattr(diagnostic.files, "environ", {"INVOCATION_ID": "a" * 32}, raising=False)
    if size == 4096:
        assert (
            stage._witness_binding(pane=False)["control"]
            == hashlib.sha256(diagnostic.path.read_bytes()).hexdigest()
        )
    else:
        with pytest.raises(stage.StageDenied):
            stage._witness_binding(pane=False)
    assert not diagnostic.new_marker.exists()
