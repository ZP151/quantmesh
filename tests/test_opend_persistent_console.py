"""Explicit one-person persistent authority, not authentication qualification."""

import hashlib
import signal
import sys
import time
from datetime import timedelta

import pytest
from test_opend_staging_window import NOW, ROOT, manager, permit, stage


def persistent_permit():
    value = permit()
    value.update(
        schema_version=2,
        purpose="opend_persistent_private_console",
        human_reviewers=["Operator"],
        safety_owner="Operator",
        session_lifetime="until_operator_stop",
    )
    return value


def validate(value, now=NOW):
    stage.validate_staging_window(
        stage.StagingWindow(value),
        now=now,
        identity={"machine_sha256": stage.MACHINE_SHA, "gateway_uid": 1001, "gateway_gid": 1001},
        hashes={"launcher_sha256": "c" * 64, "tmux_sha256": stage.TMUX_SHA},
    )


def test_one_actual_operator_can_authorize_persistent_session():
    value = persistent_permit()
    validate(value)
    assert stage.StagingWindow(value).persistent
    assert value["human_reviewers"] == [value["safety_owner"]] == ["Operator"]
    assert not any(stage.FALSE_FLAGS.values())


@pytest.mark.parametrize(
    "key,value",
    [
        ("human_reviewers", ["Operator", "invented-second-person"]),
        ("safety_owner", "someone-else"),
        ("schema_version", True),
        ("purpose", "opend_initialization_qualification"),
        ("session_lifetime", "promote_source_qualification"),
        ("max_seconds", 901),
        ("password", "fixture-not-a-credential"),
    ],
)
def test_persistent_authority_rejects_role_or_scope_drift(key, value):
    candidate = persistent_permit()
    candidate[key] = value
    with pytest.raises(stage.StageDenied):
        validate(candidate)


def test_expired_persistent_permit_still_denies_initial_launch():
    with pytest.raises(stage.StageDenied):
        validate(persistent_permit(), NOW + timedelta(seconds=61))


def test_expiring_stage_does_not_accept_single_person_or_persistent_lifetime():
    candidate = permit()
    candidate["human_reviewers"] = ["Operator"]
    candidate["safety_owner"] = "Operator"
    with pytest.raises(stage.StageDenied):
        validate(candidate)


def test_persistent_template_and_paths_are_separate_and_resource_bounded():
    window = stage.StagingWindow(persistent_permit())
    unit = ROOT / "deploy/aws/opend/quantmesh-opend-console@.service"
    raw = unit.read_bytes()
    text = raw.decode()
    assert hashlib.sha256(raw).hexdigest() == stage.PERSISTENT_UNIT_SHA
    assert stage._unit(window) == "quantmesh-opend-console@" + window.nonce + ".service"
    assert stage._paths(window).name == "quantmesh-opend-console-" + window.nonce
    assert "--persistent" in stage._pane_command(window)
    for line in (
        "RuntimeMaxSec=infinity",
        "Restart=no",
        "MemoryMax=1G",
        "MemorySwapMax=0",
        "CPUQuota=50%",
        "TasksMax=128",
        "StandardOutput=null",
        "StandardError=null",
    ):
        assert line in text
    assert "WantedBy=" not in text


def test_persistent_manager_requires_infinite_lifetime_and_exact_resources():
    window = stage.StagingWindow(persistent_permit())
    data = manager()
    data.update(
        RuntimeMaxUSec="infinity",
        FragmentPath="/etc/systemd/system/quantmesh-opend-console@.service",
        Id=stage._unit(window),
        RuntimeDirectory=stage._paths(window).name,
        ControlGroup="/system.slice/" + stage._unit(window),
        MemoryMax="1073741824",
        MemoryHigh="805306368",
        MemorySwapMax="0",
        CPUQuotaPerSecUSec="500ms",
        TasksMax="128",
    )
    stage._validate_manager(window, data)
    data["RuntimeMaxUSec"] = "15min"
    with pytest.raises(stage.StageDenied):
        stage._validate_manager(window, data)


@pytest.mark.skipif(sys.platform != "linux", reason="actual Linux fork/pidfd lifecycle")
def test_actual_persistent_child_survives_launch_window_and_owned_stop():
    """Real synthetic process, no vendor/terminal data; explicit cleanup via pidfd."""
    child = stage._spawn_gated(None, fixture=True, seconds=0, persistent=True)
    sibling = stage._spawn_gated(None, fixture=True, seconds=8)
    try:
        child.release()
        sibling.release()
        # The explicit zero lifetime would exit immediately or fail to create on old code.
        time.sleep(1.15)
        assert child.alive() and sibling.alive()
        child.close()
        assert child.terminal and child.returncode == -signal.SIGTERM and sibling.alive()
    finally:
        child.close()
        sibling.close()


@pytest.mark.skipif(sys.platform != "linux", reason="actual Linux fork/pidfd lifecycle")
def test_persistent_gate_denial_never_releases_child():
    child = stage._spawn_gated(None, fixture=True, seconds=0, persistent=True)
    try:
        with pytest.raises(stage.StageDenied):
            child.release(lambda: (_ for _ in ()).throw(stage.StageDenied()))
        assert not child.released
    finally:
        child.close()


@pytest.mark.skipif(sys.platform != "linux", reason="actual Linux fork/pidfd release gate")
def test_final_child_identity_read_cannot_release_after_launch_deadline(monkeypatch):
    child = stage._spawn_gated(None, fixture=True, seconds=0, persistent=True)
    real_clock = stage.time.monotonic
    real_identity = stage._identity
    expired = []
    deadline = real_clock() + 5

    def identity(pid, handle):
        value = real_identity(pid, handle)
        expired.append(True)
        return value

    monkeypatch.setattr(stage, "_identity", identity)
    monkeypatch.setattr(stage.time, "monotonic", lambda: real_clock() + (100 if expired else 0))
    try:
        with pytest.raises(stage.StageDenied, match="deadline"):
            child.release(deadline=deadline)
        assert not child.released
    finally:
        child.close()


def test_persistent_modifier_alone_is_no_effect_denial(monkeypatch):
    monkeypatch.setattr(stage, "_admit", lambda *a, **k: pytest.fail("invalid mode inspected host"))
    with pytest.raises(SystemExit) as exc:
        stage.main(["--persistent"])
    assert exc.value.code == 2


@pytest.mark.skipif(sys.platform != "linux", reason="actual Linux PTY/fork/pidfd release gate")
@pytest.mark.parametrize("clock", ["wall", "monotonic"])
def test_expiry_during_final_private_context_never_releases_child(monkeypatch, clock):
    import json
    import os
    from contextlib import contextmanager
    from datetime import UTC, datetime

    from test_opend_staging_window import inherited_terminal

    from tools import qualify_opend_private_terminal as helper

    profile = json.loads((ROOT / "deploy/aws/opend/gateway-profile.json").read_bytes())
    value = persistent_permit()
    wall = datetime.now(UTC)
    value["expires_at"] = (wall + timedelta(seconds=10)).isoformat()
    window = stage.StagingWindow(value)
    expired = []
    real_monotonic = stage.time.monotonic

    class Clock(datetime):
        @staticmethod
        def now(tz):
            return wall + timedelta(seconds=100 if expired and clock == "wall" else 0)

    monkeypatch.setattr(stage, "datetime", Clock)
    monkeypatch.setattr(
        stage.time,
        "monotonic",
        lambda: real_monotonic() + (100 if expired and clock == "monotonic" else 0),
    )
    monkeypatch.setattr(stage, "_admit", lambda w: (profile, helper))
    monkeypatch.setattr(stage, "load_staging_window", lambda **kw: window)
    monkeypatch.setattr(stage, "_unclaimed", lambda w: None)
    monkeypatch.setattr(stage, "_claim", lambda w, d: None)
    monkeypatch.setattr(stage, "_finish_backend", os.close)
    monkeypatch.setattr(stage, "_digest_fd", lambda fd: stage.VENDOR_SHA)
    monkeypatch.setattr(stage, "_cgroup", lambda pid: "fixture")

    @contextmanager
    def fixture_file(path):
        fd = os.open("/dev/null", os.O_RDONLY)
        try:
            yield fd
        finally:
            os.close(fd)

    monkeypatch.setattr(stage, "_protected_fd", fixture_file)
    monkeypatch.setattr(stage, "_owned_dir", fixture_file)
    spawn = stage._spawn_gated
    captured = []

    def synthetic(fds, **kw):
        child = spawn(fds, fixture=True, seconds=0, persistent=True, registry=kw["registry"])
        captured.append(child)
        return child

    monkeypatch.setattr(stage, "_spawn_gated", synthetic)
    with stage._fixture_pty() as (_, slave), inherited_terminal(slave):
        calls = []

        def context(w):
            properties = manager()
            properties["ControlGroup"] = "fixture"
            proof = helper.inspect_private_terminal(0, 1, 2, expected_uid=os.getuid())
            if calls:
                expired.append(True)
            calls.append(True)
            return dict(
                manager=properties, terminal=proof, backend_pidfd=os.pidfd_open(os.getpid())
            )

        monkeypatch.setattr(stage, "inspect_staging_context", context)
        # If buggy code releases, stop after one loop so this negative test cannot hang.
        real_select = stage.select.select

        def select_once(reads, writes, errors, timeout):
            if captured and captured[0].released and len(reads) == 2 and timeout == 0.2:
                raise RuntimeError("released_after_expiry")
            return real_select(reads, writes, errors, timeout)

        monkeypatch.setattr(stage.select, "select", select_once)
        with pytest.raises(stage.StageDenied, match="deadline"):
            stage.start_staging_console(window)
        assert captured and not captured[0].released and captured[0].closed
