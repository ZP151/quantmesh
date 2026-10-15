"""Staging authority stays separate from source/production qualification."""

import hashlib
import importlib.util
import json
import os
import stat
import sys
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

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
    assert "new-session" not in config
    pane = stage._pane_command(stage.StagingWindow(permit()))
    assert pane[-3:] == ["--pane", "--nonce", "a" * 32]
    assert pane[4:12] == ["new-session", "-d", "-s", "opend", "/usr/bin/python3", "-I", "-S", "-B"]
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


def test_service_creates_pane_only_after_foreground_exec():
    unit = (ROOT / "deploy/aws/opend/quantmesh-opend-stage@.service").read_text()
    assert (
        "ExecStartPost=/usr/bin/python3 -I -S -B /opt/quantmesh/opend/stage_console.py "
        "--create-pane --nonce %i" in unit
    )
    assert unit.index("ExecStart=") < unit.index("ExecStartPost=")


def test_installed_unit_pin_matches_exact_template_bytes():
    assert (
        hashlib.sha256(
            (ROOT / "deploy/aws/opend/quantmesh-opend-stage@.service").read_bytes()
        ).hexdigest()
        == stage.UNIT_SHA
    )


def test_activation_transition_preserves_manager_authority():
    before = manager()
    after = dict(before, ActiveState="activating")
    assert stage._same_manager(before, after)
    after["MainPID"] = "9999"
    assert not stage._same_manager(before, after)


NATIVE = pytest.mark.skipif(
    sys.platform != "linux", reason="native descriptors; root/manager mocked"
)


@contextmanager
def inherited_terminal(slave):
    saved = [os.dup(fd) for fd in (0, 1, 2)]
    try:
        for fd in (0, 1, 2):
            os.dup2(slave, fd)
        yield
    finally:
        for target, fd in enumerate(saved):
            os.dup2(fd, target)
            os.close(fd)


@NATIVE
@pytest.mark.parametrize("bad", ["echo", "mode", "mismatch", "direction", "owner"])
def test_actual_context_terminal_rejection_precedes_release(monkeypatch, bad):
    from tools import qualify_opend_private_terminal as helper

    monkeypatch.setattr(stage, "_admit", lambda w: ({}, helper))
    facts = manager()
    facts["MainPID"] = str(os.getppid())
    monkeypatch.setattr(stage, "_manager", lambda w: facts)
    monkeypatch.setattr(stage, "_cgroup", lambda pid: facts["ControlGroup"])
    with stage._fixture_pty() as (_, slave), inherited_terminal(slave):
        import termios

        proof = helper.inspect_private_terminal(0, 1, 2, expected_uid=os.getuid())
        # Root/backend authority and socket are simulated; descriptors are genuine.
        monkeypatch.setattr(stage, "_runtime_config", lambda w: None)
        monkeypatch.setattr(os, "readlink", lambda p: "/usr/bin/tmux")
        original_open = os.open

        def opened(path, *args, **kwargs):
            if str(path).endswith("/exe"):
                return original_open("/dev/null", os.O_RDONLY)
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(os, "open", opened)

        @contextmanager
        def pinned(path):
            fd = original_open("/dev/null", os.O_RDONLY)
            try:
                yield fd
            finally:
                os.close(fd)

        monkeypatch.setattr(stage, "_protected_fd", pinned)
        monkeypatch.setattr(stage, "_digest_fd", lambda fd: stage.TMUX_SHA)
        monkeypatch.setattr(stage, "_owned_dir", lambda p: pinned(p))
        real_stat = os.stat
        monkeypatch.setattr(
            os,
            "stat",
            lambda p, *a, **k: (
                SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600, st_uid=os.getuid())
                if p == "socket"
                else real_stat(p, *a, **k)
            ),
        )
        window = stage.StagingWindow(permit())
        socket = stage._paths(window) / "socket"
        monkeypatch.setenv("TMUX", f"{socket},{os.getppid()},0")
        monkeypatch.setenv("TMUX_PANE", "%0")
        monkeypatch.setattr(
            stage,
            "_command",
            lambda argv: f"{os.getpid()}|{os.ttyname(0)}|{os.getppid()}|{socket}|0|0|0",
        )
        if bad == "echo":
            attrs = termios.tcgetattr(slave)
            attrs[3] |= termios.ECHO
            termios.tcsetattr(slave, termios.TCSANOW, attrs)
        elif bad == "mode":
            os.fchmod(slave, 0o620)
        elif bad == "mismatch":
            with stage._fixture_pty() as (_, other):
                os.dup2(other, 2)
        elif bad == "direction":
            wrong = original_open(os.ttyname(slave), os.O_WRONLY)
            os.dup2(wrong, 0)
            os.close(wrong)
        else:
            actual = helper.inspect_private_terminal
            monkeypatch.setattr(
                helper,
                "inspect_private_terminal",
                lambda *fds, **kw: actual(*fds, expected_uid=os.getuid() + 1),
            )
        with pytest.raises(helper.TerminalQualificationError):
            stage.start_staging_console(window)
        assert proof["echo"] is False


@NATIVE
@pytest.mark.parametrize("bad", ["parent", "cgroup", "exe", "pidfd", "pane"])
def test_actual_backend_context_denies_unknown_or_borrowed_before_terminal(monkeypatch, bad):
    helper = SimpleNamespace(
        inspect_private_terminal=lambda *a, **k: pytest.fail("denial reached terminal")
    )
    monkeypatch.setattr(stage, "_admit", lambda w: ({}, helper))
    facts = manager()
    facts["MainPID"] = str(os.getppid())
    monkeypatch.setattr(stage, "_manager", lambda w: facts)
    monkeypatch.setattr(
        stage, "_cgroup", lambda p: facts["ControlGroup"] if bad != "cgroup" else "/borrowed"
    )
    monkeypatch.setattr(
        os, "readlink", lambda p: "/usr/bin/tmux" if bad != "exe" else "/bin/borrowed"
    )
    if bad == "parent":
        monkeypatch.setattr(os, "getppid", lambda: 999999)
    elif bad == "pidfd":
        monkeypatch.setattr(os, "pidfd_open", lambda pid: (_ for _ in ()).throw(OSError()))
    elif bad == "pane":
        # Fail an unknown pane at the new metadata command, before helper admission.
        @contextmanager
        def pinned(path):
            fd = os.open("/dev/null", os.O_RDONLY)
            try:
                yield fd
            finally:
                os.close(fd)

        monkeypatch.setattr(stage, "_protected_fd", pinned)
        real_open = os.open
        monkeypatch.setattr(
            os,
            "open",
            lambda path, *a, **k: (
                real_open("/dev/null", os.O_RDONLY)
                if str(path).endswith("/exe")
                else real_open(path, *a, **k)
            ),
        )
        monkeypatch.setattr(stage, "_digest_fd", lambda fd: stage.TMUX_SHA)
        monkeypatch.setattr(stage, "_runtime_config", lambda w: None)
        monkeypatch.setattr(stage, "_owned_dir", pinned)
        real_stat = os.stat
        monkeypatch.setattr(
            os,
            "stat",
            lambda p, *a, **k: (
                SimpleNamespace(st_mode=stat.S_IFSOCK | 0o600, st_uid=os.getuid())
                if p == "socket"
                else real_stat(p, *a, **k)
            ),
        )
        socket = stage._paths(stage.StagingWindow(permit())) / "socket"
        monkeypatch.setenv("TMUX", f"{socket},{os.getppid()},0")
        monkeypatch.setenv("TMUX_PANE", "%0")
        monkeypatch.setattr(stage, "_command", lambda argv: "mismatched-pane")
    monkeypatch.setattr(stage, "_spawn_gated", lambda *a, **k: pytest.fail("denial spawned child"))
    with pytest.raises((stage.StageDenied, OSError)):
        stage.start_staging_console(stage.StagingWindow(permit()))


@NATIVE
@pytest.mark.parametrize("bad", ["qualified", "unsafe_argv", "public_endpoint", "profile_hash"])
def test_actual_profile_admission_denies_before_backend_or_child(monkeypatch, bad):
    import grp
    import pwd

    from deploy.aws.opend import validate_profile as validator
    from tools import qualify_opend_private_terminal as helper

    profile = json.loads((ROOT / "deploy/aws/opend/gateway-profile.json").read_bytes())
    if bad == "qualified":
        profile["qualification"].update(
            state="qualified",
            install_allowed=True,
            operator_approved=True,
            server_startup_verified=True,
        )
        profile["sdk"]["wire_compatibility_verified"] = True
        profile["authentication"]["private_input_verified"] = True
    elif bad == "unsafe_argv":
        profile["runtime"]["argv"].append("-unapproved=fixture")
    elif bad == "public_endpoint":
        profile["endpoint"]["host"] = "0.0.0.0"
    # All root/identity/pin facts here are explicitly simulated; validator is genuine.
    monkeypatch.setattr(stage, "_native", lambda **k: None)
    monkeypatch.setattr(pwd, "getpwnam", lambda n: SimpleNamespace(pw_uid=os.getuid()))
    monkeypatch.setattr(grp, "getgrnam", lambda n: SimpleNamespace(gr_gid=os.getgid()))
    monkeypatch.setattr(os, "getgroups", lambda: [os.getgid()])
    monkeypatch.setattr(stage, "validate_staging_window", lambda *a, **k: None)
    monkeypatch.setattr(stage, "_digest", lambda p: stage.VENDOR_SHA)
    monkeypatch.setattr(
        stage, "_module", lambda p, digest: validator if p.name == "validate_profile.py" else helper
    )

    def pinned_bytes(path, digest=None):
        if path == stage.PROFILE:
            if bad == "profile_hash":
                raise stage.StageDenied("pin_drift")
            return json.dumps(profile).encode()
        return validator.reviewed_configuration() if path == stage.CONFIG else b"mocked-machine"

    monkeypatch.setattr(stage, "_bytes", pinned_bytes)
    monkeypatch.setattr(
        stage, "_manager", lambda *a, **k: pytest.fail("profile denial reached backend")
    )
    monkeypatch.setattr(
        stage, "_spawn_gated", lambda *a, **k: pytest.fail("profile denial spawned child")
    )
    with pytest.raises(stage.StageDenied, match="pin_drift"):
        stage.start_staging_console(stage.StagingWindow(permit()))


@NATIVE
def test_final_descriptor_replacement_refuses_actual_synthetic_gate(monkeypatch):
    from tools import qualify_opend_private_terminal as helper

    profile = json.loads((ROOT / "deploy/aws/opend/gateway-profile.json").read_bytes())
    monkeypatch.setattr(stage, "_admit", lambda w: (profile, helper))
    c = permit()
    c["expires_at"] = (datetime.now(UTC) + timedelta(seconds=5)).isoformat()
    window = stage.StagingWindow(c)
    monkeypatch.setattr(stage, "load_staging_window", lambda: window)
    monkeypatch.setattr(stage, "_unclaimed", lambda w: None)
    monkeypatch.setattr(stage, "_claim", lambda w, d: None)
    monkeypatch.setattr(stage, "_finish_backend", os.close)  # synthetic backend/manager only
    monkeypatch.setattr(stage, "_digest_fd", lambda fd: stage.VENDOR_SHA)

    @contextmanager
    def fixture_file(path):
        fd = os.open("/dev/null", os.O_RDONLY)
        try:
            yield fd
        finally:
            os.close(fd)

    monkeypatch.setattr(stage, "_protected_fd", fixture_file)
    monkeypatch.setattr(stage, "_owned_dir", fixture_file)
    original_spawn = stage._spawn_gated
    captured = []

    def synthetic(fds, **kwargs):
        child = original_spawn(fds, fixture=True, seconds=3, registry=kwargs["registry"])
        captured.append(child)
        return child

    monkeypatch.setattr(stage, "_spawn_gated", synthetic)
    with (
        stage._fixture_pty() as (_, slave),
        stage._fixture_pty() as (_, replacement),
        inherited_terminal(slave),
    ):
        calls = []

        def context(w):
            if calls:
                os.dup2(replacement, 0)
            calls.append(True)
            return dict(
                manager=manager(),
                terminal=helper.inspect_private_terminal(0, 1, 2, expected_uid=os.getuid()),
                backend_pidfd=os.pidfd_open(os.getpid()),
            )

        monkeypatch.setattr(stage, "inspect_staging_context", context)
        with pytest.raises(helper.TerminalQualificationError, match="terminal_mismatch"):
            stage.start_staging_console(window)
        assert captured and captured[0].released is False
        assert captured[0].terminal and captured[0].closed


@NATIVE
@pytest.mark.parametrize("bad", ["link", "hardlink", "owner", "writable", "hash"])
def test_specific_protected_file_boundary_with_simulated_root_metadata(monkeypatch, bad):
    real_fstat = os.fstat

    def root_metadata(fd):
        info = real_fstat(fd)
        values = list(info)
        values[4] = 0
        if stat.S_ISDIR(info.st_mode):
            values[0] = stat.S_IFDIR | 0o555
        elif bad == "owner":
            values[4] = 17
        elif bad == "writable":
            values[0] |= 0o020
        return os.stat_result(values)

    with tempfile.TemporaryDirectory(prefix="quantmesh-stage-path-", dir="/var/tmp") as root:
        path = Path(root) / "data"
        path.write_bytes(b"fixed-noncredential-fixture")
        os.chmod(path, 0o600)
        if bad == "link":
            target = Path(root) / "link"
            target.symlink_to(path)
            path = target
        elif bad == "hardlink":
            os.link(path, Path(root) / "second")
        monkeypatch.setattr(os, "fstat", root_metadata)
        with pytest.raises(
            stage.StageDenied, match="pin_drift" if bad == "hash" else "protected_path"
        ):
            stage._bytes(path, "0" * 64 if bad == "hash" else None)


@NATIVE
@pytest.mark.parametrize("bad", ["file", "directory", "symlink"])
def test_specific_vendor_descendant_boundary_not_parent_failure(monkeypatch, bad):
    real_stat = os.stat

    @contextmanager
    def root_directory(path):
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            yield fd
        finally:
            os.close(fd)

    monkeypatch.setattr(stage, "_directory", root_directory)

    def metadata(path, *a, **kw):
        info = real_stat(path, *a, **kw)
        values = list(info)
        values[4] = 0
        return os.stat_result(values)

    monkeypatch.setattr(os, "stat", metadata)
    monkeypatch.setattr(
        stage, "_protected_fd", lambda p: pytest.fail("descendant guard did not deny")
    )
    with tempfile.TemporaryDirectory(prefix="quantmesh-stage-tree-", dir="/var/tmp") as root:
        path = Path(root) / "victim"
        if bad == "file":
            path.write_bytes(b"noncredential-fixture")
            os.chmod(path, 0o620)
        elif bad == "directory":
            path.mkdir(mode=0o720)
            os.chmod(path, 0o720)
        else:
            path.symlink_to("/dev/null")
        with pytest.raises(stage.StageDenied, match="protected_path"):
            stage._vendor_tree(Path(root))


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
