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


def test_persistent_modifier_alone_is_no_effect_denial(monkeypatch):
    monkeypatch.setattr(stage, "_admit", lambda *a, **k: pytest.fail("invalid mode inspected host"))
    with pytest.raises(SystemExit) as exc:
        stage.main(["--persistent"])
    assert exc.value.code == 2
