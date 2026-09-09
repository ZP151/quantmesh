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


def test_successful_deployment_activates_exact_healthy_release(tmp_path: Path) -> None:
    deploy = _load_deploy_program()
    layout = deploy.Layout(root=tmp_path / "quantmesh")
    commands = FakeCommands(GOOD_REF)
    service = FakeService()
    previous = layout.releases / OLD_REF
    state, history, read_active, activate = _activation(previous)

    result = deploy.deploy(
        GOOD_REF,
        staging_origin=STAGING_ORIGIN,
        layout=layout,
        run_command=commands,
        service=service,
        read_active=read_active,
        activate=activate,
        read_health=lambda: {
            "status": "ok",
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
        f"QUANTMESH_STAGING_ORIGIN={STAGING_ORIGIN}\n"
    )
    flattened = [call for call, _ in commands.calls]
    assert any(call[-2:] == ("origin", GOOD_REF) for call in flattened)
    assert any(call[-2:] == ("rev-parse", "FETCH_HEAD") for call in flattened)
    assert any("worktree" in call and str(release) in call for call in flattened)


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
            read_health=lambda: {
                "status": "ok",
                "deployment": {"environment": "staging", "build_ref": OLD_REF},
            },
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
    assert "QUANTMESH_DEFAULT_PAPER_MODE=true" in environment
    assert "QUANTMESH_ALLOW_LIVE_TRADING=false" in environment
    assert exec_start.startswith("/opt/quantmesh/current/.venv/bin/quantmesh-workstation ")
    assert "--demo" in exec_start
    assert "--demo-root /var/lib/quantmesh/demo" in exec_start
    assert "--port 8765" in exec_start
    assert "--live" not in exec_start
    assert "0.0.0.0" not in exec_start
    assert service["ProtectSystem"] == ["strict"]
    assert service["NoNewPrivileges"] == ["true"]
    assert service["ReadWritePaths"] == ["/var/lib/quantmesh"]
