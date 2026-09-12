from __future__ import annotations

import importlib.util
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY_PROGRAM = ROOT / "deploy" / "aws" / "lightsail" / "deploy_release.py"
SERVICE_UNIT = ROOT / "deploy" / "aws" / "lightsail" / "quantmesh-staging.service"
GOOD_REF = "0123456789abcdef0123456789abcdef01234567"
OLD_REF = "89abcdef0123456789abcdef0123456789abcdef"
STAGING_ORIGIN = "https://quantmesh-staging.example-tailnet.ts.net"
LIVE_PROFILE = (
    "QUANTMESH_STAGING_ARGS=--live\n"
    "QUANTMESH_LIVE_WATCHLIST=BTC,ETH,SOL\n"
    "QUANTMESH_LAKE_ROOT=/var/lib/quantmesh/live/data\n"
    "QUANTMESH_ORDERS_DIR=/var/lib/quantmesh/live/orders\n"
    "QUANTMESH_DECISIONS_DIR=/var/lib/quantmesh/live/decisions\n"
)


def _load_deploy_program() -> ModuleType:
    spec = importlib.util.spec_from_file_location("quantmesh_deploy_release", DEPLOY_PROGRAM)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeCommands:
    def __init__(self, expected_ref: str) -> None:
        self.expected_ref = expected_ref
        self.calls: list[tuple[tuple[str, ...], Path | None]] = []

    def __call__(self, command: Sequence[str], cwd: Path | None = None) -> str:
        args = tuple(str(item) for item in command)
        self.calls.append((args, cwd))
        if args[-2:] == ("rev-parse", "FETCH_HEAD"):
            return f"{self.expected_ref}\n"
        if "worktree" in args and "add" in args:
            Path(args[-2]).mkdir(parents=True)
        return ""


class FakeService:
    def __init__(self) -> None:
        self.actions: list[str] = []

    def restart(self) -> None:
        self.actions.append("restart")

    def stop(self) -> None:
        self.actions.append("stop")


def _activation(initial: Path | None):
    state = {"active": initial}
    history: list[Path | None] = []

    def read_active() -> Path | None:
        return state["active"]

    def activate(target: Path | None) -> None:
        history.append(target)
        state["active"] = target

    return state, history, read_active, activate


def _retained_release(release: Path, *, profile: str = "") -> None:
    release.mkdir(parents=True)
    (release / ".staging.env").write_text(
        f"QUANTMESH_ENVIRONMENT=staging\nQUANTMESH_BUILD_REF={release.name}\n"
        f"QUANTMESH_STAGING_ORIGIN={STAGING_ORIGIN}\n" + profile,
        encoding="utf-8",
    )


def _healthy(commit: str, mode: str = "demo") -> dict[str, object]:
    return {
        "status": "ok",
        "runtime_mode": mode,
        "paper_mode": True,
        "live_trading": False,
        "deployment": {"environment": "staging", "build_ref": commit},
    }


@pytest.mark.parametrize(
    "bad_ref",
    ["", "abc", GOOD_REF.upper(), "g" * 40, f"{GOOD_REF}0"],
)
def test_invalid_ref_is_rejected_before_commands_or_filesystem_changes(
    tmp_path: Path, bad_ref: str
) -> None:
    deploy = _load_deploy_program()
    root = tmp_path / "quantmesh"
    commands = FakeCommands(GOOD_REF)
    service = FakeService()
    state, history, read_active, activate = _activation(None)

    with pytest.raises(deploy.DeploymentError, match="40 lowercase hexadecimal"):
        deploy.deploy(
            bad_ref,
            staging_origin=STAGING_ORIGIN,
            layout=deploy.Layout(root=root),
            run_command=commands,
            service=service,
            read_active=read_active,
            activate=activate,
            read_health=lambda: {},
            health_attempts=1,
            sleep=lambda _: None,
        )

    assert commands.calls == []
    assert service.actions == []
    assert history == []
    assert state["active"] is None
    assert not root.exists()


@pytest.mark.parametrize("live_market_data", [False, True])
def test_successful_deployment_activates_exact_healthy_release(
    tmp_path: Path, live_market_data: bool
) -> None:
    deploy = _load_deploy_program()
    layout = deploy.Layout(root=tmp_path / "quantmesh")
    commands = FakeCommands(GOOD_REF)
    service = FakeService()
    previous = layout.releases / OLD_REF
    _retained_release(previous)
    state, history, read_active, activate = _activation(previous)

    result = deploy.deploy(
        GOOD_REF,
        staging_origin=STAGING_ORIGIN,
        live_market_data=live_market_data,
        layout=layout,
        run_command=commands,
        service=service,
        read_active=read_active,
        activate=activate,
        read_health=lambda: {
            "status": "ok",
            "runtime_mode": "live" if live_market_data else "demo",
            "paper_mode": True,
            "live_trading": False,
            "deployment": {"environment": "staging", "build_ref": GOOD_REF},
        },
        health_attempts=1,
        sleep=lambda _: None,
    )

    release = layout.releases / GOOD_REF
    assert result.commit == GOOD_REF
    assert result.release == release
    assert result.health["deployment"]["build_ref"] == GOOD_REF
    assert state["active"] == release
    assert history == [release]
    assert service.actions == ["restart"]
    assert (release / ".staging.env").read_text(encoding="utf-8") == (
        f"QUANTMESH_ENVIRONMENT=staging\nQUANTMESH_BUILD_REF={GOOD_REF}\n"
        f"QUANTMESH_STAGING_ORIGIN={STAGING_ORIGIN}\n" + (LIVE_PROFILE if live_market_data else "")
    )
    flattened = [call for call, _ in commands.calls]
    assert any(call[-2:] == ("origin", GOOD_REF) for call in flattened)
    assert any(call[-2:] == ("rev-parse", "FETCH_HEAD") for call in flattened)
    assert any("worktree" in call and str(release) in call for call in flattened)
    install_commands = [call for call in flattened if "pip" in call and "install" in call]
    assert install_commands == [
        (
            str(release / ".venv" / "bin" / "python"),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--constraint",
            str(release / "requirements-audit.txt"),
            str(release),
        )
    ]


def test_fetched_commit_mismatch_never_activates_release(tmp_path: Path) -> None:
    deploy = _load_deploy_program()
    layout = deploy.Layout(root=tmp_path / "quantmesh")
    commands = FakeCommands(OLD_REF)
    service = FakeService()
    state, history, read_active, activate = _activation(None)

    with pytest.raises(deploy.DeploymentError, match="fetched commit mismatch"):
        deploy.deploy(
            GOOD_REF,
            staging_origin=STAGING_ORIGIN,
            layout=layout,
            run_command=commands,
            service=service,
            read_active=read_active,
            activate=activate,
            read_health=lambda: {},
            health_attempts=1,
            sleep=lambda _: None,
        )

    assert state["active"] is None
    assert history == []
    assert service.actions == []
    assert not (layout.releases / GOOD_REF).exists()


def test_health_identity_mismatch_restores_previous_release(tmp_path: Path) -> None:
    deploy = _load_deploy_program()
    layout = deploy.Layout(root=tmp_path / "quantmesh")
    commands = FakeCommands(GOOD_REF)
    service = FakeService()
    previous = layout.releases / OLD_REF
    _retained_release(previous)
    state, history, read_active, activate = _activation(previous)

    with pytest.raises(deploy.DeploymentError, match="health check"):
        deploy.deploy(
            GOOD_REF,
            staging_origin=STAGING_ORIGIN,
            layout=layout,
            run_command=commands,
            service=service,
            read_active=read_active,
            activate=activate,
            read_health=lambda: _healthy(OLD_REF),
            health_attempts=1,
            sleep=lambda _: None,
        )

    assert state["active"] == previous
    assert history == [layout.releases / GOOD_REF, previous]
    assert service.actions == ["restart", "restart"]


def test_first_deployment_health_failure_deactivates_and_stops(tmp_path: Path) -> None:
    deploy = _load_deploy_program()
    layout = deploy.Layout(root=tmp_path / "quantmesh")
    commands = FakeCommands(GOOD_REF)
    service = FakeService()
    state, history, read_active, activate = _activation(None)

    with pytest.raises(deploy.DeploymentError, match="health check"):
        deploy.deploy(
            GOOD_REF,
            staging_origin=STAGING_ORIGIN,
            layout=layout,
            run_command=commands,
            service=service,
            read_active=read_active,
            activate=activate,
            read_health=lambda: (_ for _ in ()).throw(OSError("not ready")),
            health_attempts=1,
            sleep=lambda _: None,
        )

    assert state["active"] is None
    assert history == [layout.releases / GOOD_REF, None]
    assert service.actions == ["restart", "stop"]


def test_existing_release_can_be_health_checked_and_reactivated(tmp_path: Path) -> None:
    deploy = _load_deploy_program()
    layout = deploy.Layout(root=tmp_path / "quantmesh")
    target = layout.releases / OLD_REF
    target.mkdir(parents=True)
    (target / ".staging.env").write_text(
        f"QUANTMESH_ENVIRONMENT=staging\nQUANTMESH_BUILD_REF={OLD_REF}\n"
        f"QUANTMESH_STAGING_ORIGIN={STAGING_ORIGIN}\n",
        encoding="utf-8",
    )
    current = layout.releases / GOOD_REF
    _retained_release(current)
    service = FakeService()
    state, history, read_active, activate = _activation(current)

    result = deploy.activate_existing(
        OLD_REF,
        staging_origin=STAGING_ORIGIN,
        layout=layout,
        service=service,
        read_active=read_active,
        activate=activate,
        read_health=lambda: {
            "status": "ok",
            "runtime_mode": "demo",
            "paper_mode": True,
            "live_trading": False,
            "deployment": {"environment": "staging", "build_ref": OLD_REF},
        },
        health_attempts=1,
        sleep=lambda _: None,
    )

    assert result.commit == OLD_REF
    assert result.release == target
    assert state["active"] == target
    assert history == [target]
    assert service.actions == ["restart"]


def test_failed_existing_release_reactivation_restores_current(tmp_path: Path) -> None:
    deploy = _load_deploy_program()
    layout = deploy.Layout(root=tmp_path / "quantmesh")
    target = layout.releases / OLD_REF
    target.mkdir(parents=True)
    (target / ".staging.env").write_text(
        f"QUANTMESH_ENVIRONMENT=staging\nQUANTMESH_BUILD_REF={OLD_REF}\n"
        f"QUANTMESH_STAGING_ORIGIN={STAGING_ORIGIN}\n",
        encoding="utf-8",
    )
    current = layout.releases / GOOD_REF
    _retained_release(current)
    service = FakeService()
    state, history, read_active, activate = _activation(current)

    with pytest.raises(deploy.DeploymentError, match="health check"):
        deploy.activate_existing(
            OLD_REF,
            staging_origin=STAGING_ORIGIN,
            layout=layout,
            service=service,
            read_active=read_active,
            activate=activate,
            read_health=lambda: _healthy(GOOD_REF),
            health_attempts=1,
            sleep=lambda _: None,
        )

    assert state["active"] == current
    assert history == [target, current]
    assert service.actions == ["restart", "restart"]


def _parse_unit(path: Path) -> dict[str, dict[str, list[str]]]:
    sections: dict[str, dict[str, list[str]]] = {}
    current: dict[str, list[str]] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = sections.setdefault(line[1:-1], {})
            continue
        assert current is not None
        key, value = line.split("=", 1)
        current.setdefault(key, []).append(value)
    return sections


def test_systemd_unit_is_loopback_demo_paper_and_hardened() -> None:
    unit = _parse_unit(SERVICE_UNIT)
    service: dict[str, list[str]] = unit["Service"]
    exec_start = service["ExecStart"][-1]
    environment = service["Environment"]

    assert service["User"] == ["quantmesh"]
    assert service["Group"] == ["quantmesh"]
    assert service["WorkingDirectory"] == ["/opt/quantmesh/current"]
    assert service["EnvironmentFile"] == ["/opt/quantmesh/current/.staging.env"]
    assert "HOME=/var/lib/quantmesh" in environment
    assert "QUANTMESH_WORKSTATION_HOST=127.0.0.1" in environment
    assert "QUANTMESH_DEFAULT_PAPER_MODE=true" in environment
    assert "QUANTMESH_ALLOW_LIVE_TRADING=false" in environment
    assert exec_start.startswith("/opt/quantmesh/current/.venv/bin/quantmesh-workstation ")
    assert '"QUANTMESH_STAGING_ARGS=--demo --demo-root /var/lib/quantmesh/demo"' in environment
    assert "$QUANTMESH_STAGING_ARGS" in exec_start
    assert "--port 8765" in exec_start
    assert "--live" not in exec_start
    assert "0.0.0.0" not in exec_start
    assert service["ProtectSystem"] == ["strict"]
    assert service["NoNewPrivileges"] == ["true"]
    assert service["ReadWritePaths"] == ["/var/lib/quantmesh"]


def test_explicit_live_deployment_writes_isolated_canonical_profile(tmp_path: Path) -> None:
    deploy = _load_deploy_program()
    layout = deploy.Layout(root=tmp_path / "quantmesh")
    state, history, read_active, activate = _activation(None)
    result = deploy.deploy(
        GOOD_REF,
        staging_origin=STAGING_ORIGIN,
        live_market_data=True,
        layout=layout,
        run_command=FakeCommands(GOOD_REF),
        service=FakeService(),
        read_active=read_active,
        activate=activate,
        read_health=lambda: {
            "status": "ok",
            "runtime_mode": "live",
            "paper_mode": True,
            "live_trading": False,
            "deployment": {"environment": "staging", "build_ref": GOOD_REF},
        },
        health_attempts=1,
    )
    assert state["active"] == result.release
    assert history == [result.release]
    assert (result.release / ".staging.env").read_text(encoding="utf-8") == (
        f"QUANTMESH_ENVIRONMENT=staging\nQUANTMESH_BUILD_REF={GOOD_REF}\n"
        f"QUANTMESH_STAGING_ORIGIN={STAGING_ORIGIN}\n" + LIVE_PROFILE
    )


@pytest.mark.parametrize("live_market_data", [False, True])
@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("runtime_mode", "operator"),
        ("runtime_mode", None),
        ("paper_mode", False),
        ("paper_mode", None),
        ("paper_mode", 1),
        ("live_trading", True),
        ("live_trading", None),
        ("live_trading", 0),
        ("deployment", {"environment": "staging", "build_ref": OLD_REF}),
    ],
)
def test_runtime_or_safety_mismatch_restores_retained_release(
    tmp_path: Path, live_market_data: bool, field: str, bad_value: object
) -> None:
    deploy = _load_deploy_program()
    layout = deploy.Layout(root=tmp_path / "quantmesh")
    previous = layout.releases / OLD_REF
    _retained_release(previous)
    state, history, read_active, activate = _activation(previous)
    service = FakeService()
    health = {
        "status": "ok",
        "runtime_mode": "live" if live_market_data else "demo",
        "paper_mode": True,
        "live_trading": False,
        "deployment": {"environment": "staging", "build_ref": GOOD_REF},
    }
    health[field] = bad_value
    with pytest.raises(deploy.DeploymentError, match="health check"):
        deploy.deploy(
            GOOD_REF,
            staging_origin=STAGING_ORIGIN,
            live_market_data=live_market_data,
            layout=layout,
            run_command=FakeCommands(GOOD_REF),
            service=service,
            read_active=read_active,
            activate=activate,
            read_health=lambda: health if state["active"] != previous else _healthy(OLD_REF),
            health_attempts=1,
        )
    assert state["active"] == previous
    assert history == [layout.releases / GOOD_REF, previous]
    assert service.actions == ["restart", "restart"]


@pytest.mark.parametrize(("profile", "mode"), [("", "demo"), (LIVE_PROFILE, "live")])
@pytest.mark.parametrize("matching_mode", [True, False])
def test_retained_release_infers_profile_without_rewriting_environment(
    tmp_path: Path, profile: str, mode: str, matching_mode: bool
) -> None:
    deploy = _load_deploy_program()
    layout = deploy.Layout(root=tmp_path / "quantmesh")
    target = layout.releases / OLD_REF
    target.mkdir(parents=True)
    environment = target / ".staging.env"
    original_bytes = (
        f"QUANTMESH_ENVIRONMENT=staging\nQUANTMESH_BUILD_REF={OLD_REF}\n"
        f"QUANTMESH_STAGING_ORIGIN={STAGING_ORIGIN}\n" + profile
    ).encode("utf-8")
    environment.write_bytes(original_bytes)
    original_mtime = environment.stat().st_mtime_ns
    current = layout.releases / GOOD_REF
    _retained_release(current)
    state, history, read_active, activate = _activation(current)
    service = FakeService()

    def reactivate():
        return deploy.activate_existing(
            OLD_REF,
            staging_origin=STAGING_ORIGIN,
            layout=layout,
            service=service,
            read_active=read_active,
            activate=activate,
            read_health=lambda: (
                _healthy(GOOD_REF)
                if state["active"] == current
                else {
                    "status": "ok",
                    "runtime_mode": mode
                    if matching_mode
                    else ("demo" if mode == "live" else "live"),
                    "paper_mode": True,
                    "live_trading": False,
                    "deployment": {"environment": "staging", "build_ref": OLD_REF},
                }
            ),
            health_attempts=1,
        )

    if matching_mode:
        assert reactivate().release == target
        assert state["active"] == target
        assert history == [target]
    else:
        with pytest.raises(deploy.DeploymentError, match="health check"):
            reactivate()
        assert state["active"] == current
        assert history == [target, current]
    assert environment.read_bytes() == original_bytes
    assert environment.stat().st_mtime_ns == original_mtime


@pytest.mark.parametrize(
    "bad_profile",
    [
        "QUANTMESH_STAGING_ARGS=--live\n",
        LIVE_PROFILE.replace("BTC,ETH,SOL", "BTC,ETH,SOL,HYPE"),
        LIVE_PROFILE.replace("/live/data", "/demo/data"),
        LIVE_PROFILE + "QUANTMESH_ALLOW_LIVE_TRADING=true\n",
        LIVE_PROFILE + "QUANTMESH_STAGING_ARGS=--demo\n",
        "QUANTMESH_STAGING_ARGS=--demo\n",
    ],
)
def test_retained_noncanonical_profile_is_rejected_before_activation(
    tmp_path: Path, bad_profile: str
) -> None:
    deploy = _load_deploy_program()
    layout = deploy.Layout(root=tmp_path / "quantmesh")
    target = layout.releases / OLD_REF
    target.mkdir(parents=True)
    environment = target / ".staging.env"
    original = (
        f"QUANTMESH_ENVIRONMENT=staging\nQUANTMESH_BUILD_REF={OLD_REF}\n"
        f"QUANTMESH_STAGING_ORIGIN={STAGING_ORIGIN}\n" + bad_profile
    )
    environment.write_text(original, encoding="utf-8")
    state, history, read_active, activate = _activation(None)
    service = FakeService()
    with pytest.raises(deploy.DeploymentError, match="release identity"):
        deploy.activate_existing(
            OLD_REF,
            staging_origin=STAGING_ORIGIN,
            layout=layout,
            service=service,
            read_active=read_active,
            activate=activate,
            read_health=lambda: {},
            health_attempts=1,
        )
    assert state["active"] is None
    assert history == []
    assert service.actions == []
    assert environment.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("live_flag", [[], ["--live-market-data"]])
def test_cli_selects_demo_by_default_and_live_only_explicitly(
    monkeypatch: pytest.MonkeyPatch, live_flag: list[str]
) -> None:
    deploy = _load_deploy_program()
    calls = []

    def prepare(commit: str, *, staging_origin: str, live_market_data: bool):
        calls.append((commit, staging_origin, live_market_data))
        return deploy.DeploymentResult(commit=commit, release=Path("release"), health={})

    monkeypatch.setattr(deploy, "deploy", prepare)
    monkeypatch.setattr(
        sys, "argv", [str(DEPLOY_PROGRAM), GOOD_REF, "--origin", STAGING_ORIGIN, *live_flag]
    )
    assert deploy.main() == 0
    assert calls == [(GOOD_REF, STAGING_ORIGIN, bool(live_flag))]


def test_cli_refuses_to_override_retained_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    deploy = _load_deploy_program()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(DEPLOY_PROGRAM),
            OLD_REF,
            "--origin",
            STAGING_ORIGIN,
            "--activate-existing",
            "--live-market-data",
        ],
    )
    with pytest.raises(SystemExit) as failure:
        deploy.main()
    assert failure.value.code == 2


@pytest.mark.parametrize(("profile", "mode"), [("", "demo"), (LIVE_PROFILE, "live")])
@pytest.mark.parametrize(
    "rollback_fault", [None, "build", "mode", "paper", "live", "profile", "commit"]
)
def test_automatic_rollback_checks_retained_identity_profile_and_health(
    tmp_path: Path, profile: str, mode: str, rollback_fault: str | None
) -> None:
    deploy = _load_deploy_program()
    layout = deploy.Layout(root=tmp_path / "quantmesh")
    previous = layout.releases / ("invalid" if rollback_fault == "commit" else OLD_REF)
    _retained_release(previous, profile=profile)
    environment_file = previous / ".staging.env"
    if rollback_fault == "profile":
        with environment_file.open("a", encoding="utf-8") as environment:
            environment.write("QUANTMESH_ALLOW_LIVE_TRADING=true\n")
    original_bytes = environment_file.read_bytes()
    original_mtime = environment_file.stat().st_mtime_ns
    state, history, read_active, activate = _activation(previous)
    service = FakeService()
    observed: list[Path | None] = []

    def read():
        observed.append(state["active"])
        if state["active"] != previous:
            return {"status": "unavailable"}
        health = _healthy(OLD_REF, mode)
        if rollback_fault == "build":
            health["deployment"] = {"environment": "staging", "build_ref": GOOD_REF}
        elif rollback_fault == "mode":
            health["runtime_mode"] = "live" if mode == "demo" else "demo"
        elif rollback_fault == "paper":
            health["paper_mode"] = False
        elif rollback_fault == "live":
            health["live_trading"] = True
        return health

    with pytest.raises(deploy.DeploymentError) as failure:
        deploy.deploy(
            GOOD_REF,
            staging_origin=STAGING_ORIGIN,
            live_market_data=True,
            layout=layout,
            run_command=FakeCommands(GOOD_REF),
            service=service,
            read_active=read_active,
            activate=activate,
            read_health=read,
            health_attempts=2,
            sleep=lambda _: None,
        )
    assert GOOD_REF in str(failure.value)
    candidate = layout.releases / GOOD_REF
    if rollback_fault is None:
        assert "rollback failed" not in str(failure.value)
        assert observed == [candidate, candidate, previous]
        assert history == [candidate, previous]
    elif rollback_fault in {"profile", "commit"}:
        assert "rollback failed" in str(failure.value)
        assert observed == [candidate, candidate]
        assert service.actions == ["restart"]
    else:
        assert "rollback failed" in str(failure.value)
        assert OLD_REF in str(failure.value)
        assert observed == [candidate, candidate, previous, previous]
        assert history == [candidate, previous]
    assert environment_file.read_bytes() == original_bytes
    assert environment_file.stat().st_mtime_ns == original_mtime
