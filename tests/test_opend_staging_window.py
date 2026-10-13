"""Staging authority stays separate from source/production qualification."""

import importlib.util
import json
import os
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("stage", ROOT / "deploy/aws/opend/stage_console.py")
stage = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = stage
SPEC.loader.exec_module(stage)
NOW = datetime(2026, 10, 13, tzinfo=UTC)


def permit():
    return dict(
        schema_version=1,
        purpose="opend_initialization_qualification",
        nonce="a" * 32,
        approved_build="b" * 40,
        launcher_sha256="c" * 64,
        tmux_version="3.4",
        tmux_sha256=stage.TMUX_SHA,
        machine_sha256=stage.MACHINE_SHA,
        gateway_uid=1001,
        gateway_gid=1001,
        not_before=(NOW - timedelta(seconds=1)).isoformat(),
        expires_at=(NOW + timedelta(seconds=60)).isoformat(),
        max_seconds=60,
        human_reviewers=["reviewer-one", "reviewer-two"],
        safety_owner="reviewer-one",
        ci_conclusion="success",
        operator_window_approved=True,
        new_device_approved=True,
        market_right_transfer_approved=True,
    )


def validate(value):
    stage.validate_staging_window(
        stage.StagingWindow(value),
        now=NOW,
        identity={"machine_sha256": stage.MACHINE_SHA, "gateway_uid": 1001, "gateway_gid": 1001},
        hashes={"launcher_sha256": "c" * 64, "tmux_sha256": stage.TMUX_SHA},
    )


def test_valid_permit_is_staging_authority_only():
    validate(permit())
    assert all(value is False for value in stage.FALSE_FLAGS.values())


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("nonce", "../../x"),
        ("approved_build", "z" * 40),
        ("max_seconds", True),
        ("max_seconds", 901),
        ("max_seconds", 0),
        ("gateway_uid", 0),
        ("gateway_gid", True),
        ("tmux_version", "3.5"),
        ("tmux_sha256", "d" * 64),
        ("machine_sha256", "e" * 64),
        ("human_reviewers", ["same", "same"]),
        ("safety_owner", "outsider"),
        ("ci_conclusion", "pending"),
        ("operator_window_approved", False),
        ("new_device_approved", 1),
        ("market_right_transfer_approved", False),
        ("not_before", (NOW + timedelta(seconds=1)).isoformat()),
        ("expires_at", NOW.isoformat()),
        ("expires_at", "2026-10-14T00:00:00"),
        ("expires_at", (NOW + timedelta(seconds=901)).isoformat()),
        ("launcher_sha256", "d" * 64),
    ],
)
def test_malformed_or_wrong_authority_denied(field, value):
    candidate = permit()
    candidate[field] = value
    with pytest.raises(stage.StageDenied):
        validate(candidate)


@pytest.mark.parametrize(
    "field", ["password", "account_id", "token", "source_qualified", "install_allowed"]
)
def test_unknown_and_credential_claims_denied(field):
    candidate = permit()
    candidate[field] = "not-a-secret"
    with pytest.raises(stage.StageDenied):
        validate(candidate)


def test_default_does_not_inspect_or_spawn(monkeypatch, capsys):
    def forbidden(*args):
        pytest.fail("preflight had effects")

    monkeypatch.setattr(stage, "load_staging_window", forbidden)
    monkeypatch.setattr(stage, "run_owned_fixture", forbidden)
    assert stage.main([]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["scope"] == "PREFLIGHT_NO_EFFECT"
    assert result["production_release_qualified"] is False


@pytest.mark.parametrize(
    "args",
    [
        ["--command", "true"],
        ["--home", "/tmp"],
        ["--start", "--owned-fixture"],
        ["--nonce", "x", "--start"],
    ],
)
def test_cli_has_no_arbitrary_authority(args):
    with pytest.raises(SystemExit) as error:
        stage.main(args)
    assert error.value.code == 2


def test_template_is_distinct_foreground_and_bounded():
    unit = (ROOT / "deploy/aws/opend/quantmesh-opend-stage@.service").read_text()
    for line in [
        "RuntimeMaxSec=900",
        "TimeoutStopSec=15",
        "KillMode=control-group",
        "Restart=no",
        "StandardOutput=null",
        "StandardError=null",
        "UMask=0077",
        "RuntimeDirectoryMode=0700",
    ]:
        assert line in unit
    command = next(line for line in unit.splitlines() if line.startswith("ExecStart="))
    assert "-D -f " in command and "new-session" not in command
    assert "--require-qualified" in (ROOT / "deploy/aws/opend/quantmesh-opend.service").read_text()


@pytest.mark.skipif(sys.platform != "linux", reason="real Linux pidfd/PTY lifecycle")
def test_actual_owned_fixture():
    result = stage.run_owned_fixture()
    assert result["status"] == "passed", result
    assert result["elapsed_seconds"] < 90
    for case in [
        "expiry",
        "hup",
        "parent_loss",
        "missing_handle",
        "registration_interrupted",
        "blocked",
    ]:
        assert result["cases"][case]["terminal"]
        assert result["cases"][case]["sibling_survived"]
    assert result["all_owned_children_terminal"]
    assert result["owned_root_removed"]
    assert result["mocked"] == ["root_permit", "systemd_manager", "tmux_backend", "source_host"]
    assert all(result[key] is False for key in stage.FALSE_FLAGS)


@pytest.mark.skipif(sys.platform != "linux", reason="no-follow Linux protected paths")
def test_protected_reader_denies_link_and_mutable_parent(tmp_path):
    candidate = tmp_path / "permit.json"
    candidate.write_text(json.dumps(permit()))
    with pytest.raises(stage.StageDenied):
        stage.load_staging_window(candidate)
    link = tmp_path / "linked.json"
    link.symlink_to(candidate)
    with pytest.raises(stage.StageDenied):
        stage.load_staging_window(link)


def manager():
    value = dict(stage.MANAGER_FIXED)
    value.update(
        Id=stage._unit(stage.StagingWindow(permit())),
        MainPID="3001",
        ActiveState="active",
        ControlGroup="/system.slice/" + stage._unit(stage.StagingWindow(permit())),
        RuntimeDirectory="quantmesh-opend-stage-" + "a" * 32,
    )
    return value


@pytest.mark.parametrize(
    "key,value",
    [
        ("User", "root"),
        ("KillMode", "process"),
        ("Restart", "always"),
        ("StandardOutput", "journal"),
        ("RuntimeMaxUSec", "infinity"),
        ("TimeoutStopUSec", "16s"),
        ("DropInPaths", "/tmp/override"),
        ("MainPID", "0"),
        ("ControlGroup", "/borrowed/global"),
        ("ActiveState", "inactive"),
        ("RuntimeDirectory", "quantmesh-opend"),
        ("Id", "borrowed.service"),
    ],
)
def test_manager_wrong_authority_denies(key, value):
    data = manager()
    data[key] = value
    with pytest.raises(stage.StageDenied):
        stage._validate_manager(stage.StagingWindow(permit()), data)


def test_manager_exact_contract():
    stage._validate_manager(stage.StagingWindow(permit()), manager())


def test_generated_configuration_has_fixed_direct_guard_and_no_recording():
    config = stage._tmux_config(stage.StagingWindow(permit())).decode()
    assert "new-session -d -s opend /usr/bin/python3 -I -S -B " in config
    assert "--pane --nonce " + "a" * 32 in config
    for setting in [
        "history-limit 0",
        "set-clipboard off",
        "buffer-limit 1",
        "exit-unattached off",
        "unbind-key -a",
    ]:
        assert setting in config
    for command in ["capture-pane", "pipe-pane", "run-shell", "sh -c"]:
        assert command not in config


@pytest.mark.skipif(sys.platform != "linux", reason="native registry interruption")
def test_registry_is_retained_before_interrupt_is_unblocked():
    registry = []
    with pytest.raises(stage.StageDenied, match="registration_interrupted") as caught:
        stage._spawn_gated(
            None, fixture=True, seconds=2, failure="registered_then_interrupt", registry=registry
        )
    assert caught.value.cleanup["terminal"]
    assert caught.value.cleanup["released"] is False
    assert registry == []


def test_no_effect_check_window_redacts_unexpected_error(monkeypatch, capsys):
    def denied(*args):
        raise RuntimeError("noncredential-fixture-marker")

    monkeypatch.setattr(stage, "load_staging_window", denied)
    assert stage.main(["--check-window", "--nonce", "a" * 32]) == 2
    assert "noncredential-fixture-marker" not in capsys.readouterr().out


@pytest.mark.skipif(sys.platform != "linux", reason="real pidfd backend stop")
def test_owned_backend_stop_uses_retained_handle_and_preserves_sibling():
    children = []
    try:
        sibling = stage._spawn_gated(None, fixture=True, seconds=8, registry=children)
        sibling.release()
        backend = stage._spawn_gated(None, fixture=True, seconds=8, registry=children)
        backend.release()
        stage._stop_backend(backend.pidfd)
        assert backend.wait() == -stage.signal.SIGTERM
        assert sibling.alive()
    finally:
        for child in reversed(children):
            child.close()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux protected installation metadata")
def test_credential_free_vendor_tree_rejects_mutability(tmp_path):
    with pytest.raises(stage.StageDenied, match="protected_path"):
        stage._vendor_tree(tmp_path)


@pytest.mark.skipif(sys.platform != "linux", reason="retained native backend handle")
def test_backend_finish_signals_before_closing_handle(monkeypatch):
    read, write = os.pipe()
    calls = []

    def stop(fd):
        os.fstat(fd)
        calls.append(fd)

    monkeypatch.setattr(stage, "_stop_backend", stop)
    try:
        stage._finish_backend(read)
        assert calls == [read]
        with pytest.raises(OSError):
            os.fstat(read)
    finally:
        os.close(write)


@pytest.mark.skipif(sys.platform != "linux", reason="native gated fork lifecycle")
def test_admission_failure_never_releases_actual_child():
    def denied():
        raise stage.StageDenied("backend_denied")

    with stage._fixture_pty() as (_, slave):
        child = stage._spawn_gated(slave, fixture=True, seconds=1)
        try:
            with pytest.raises(stage.StageDenied, match="backend_denied"):
                child.release(denied)
            assert child.released is False
        finally:
            child.close()
        assert child.terminal


@pytest.mark.skipif(sys.platform != "linux", reason="native durable nonce claim")
def test_nonce_claim_is_exclusive_and_survives_reopen():
    window = stage.StagingWindow(permit())
    with tempfile.TemporaryDirectory(prefix="quantmesh-stage-claim-", dir="/var/tmp") as root:
        fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            stage._claim(window, fd)
            with pytest.raises(stage.StageDenied, match="duplicate_nonce"):
                stage._claim(window, fd)
            assert (Path(root) / window.nonce).stat().st_mode & 0o777 == 0o600
        finally:
            os.close(fd)
