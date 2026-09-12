#!/usr/bin/env python3
"""Install and activate one exact QuantMesh staging commit."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

REPOSITORY_URL = "https://github.com/ZP151/quantmesh.git"
HEALTH_URL = "http://127.0.0.1:8765/api/health"
EXACT_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class DeploymentError(RuntimeError):
    """A release could not be prepared or safely activated."""


@dataclass(frozen=True)
class Layout:
    root: Path = Path("/opt/quantmesh")

    @property
    def repository(self) -> Path:
        return self.root / "repository"

    @property
    def releases(self) -> Path:
        return self.root / "releases"

    @property
    def current(self) -> Path:
        return self.root / "current"


@dataclass(frozen=True)
class DeploymentResult:
    commit: str
    release: Path
    health: Mapping[str, Any]


class ServiceControl(Protocol):
    def restart(self) -> None: ...

    def stop(self) -> None: ...


RunCommand = Callable[[Sequence[str], Path | None], str]
ReadActive = Callable[[], Path | None]
Activate = Callable[[Path | None], None]
ReadHealth = Callable[[], Mapping[str, Any]]


def validate_commit(commit: str) -> str:
    if EXACT_COMMIT.fullmatch(commit) is None:
        raise DeploymentError("commit must be exactly 40 lowercase hexadecimal characters")
    return commit


def validate_staging_origin(origin: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(origin)
        port = parsed.port
    except ValueError as exc:
        raise DeploymentError("origin must be one canonical Tailscale HTTPS origin") from exc
    hostname = parsed.hostname
    if (
        parsed.scheme != "https"
        or hostname is None
        or hostname == "ts.net"
        or not hostname.endswith(".ts.net")
        or port is not None
        or origin != f"https://{hostname}"
    ):
        raise DeploymentError("origin must be one canonical Tailscale HTTPS origin")
    return origin


def run_command(command: Sequence[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        list(command),
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


class SystemdService:
    def __init__(self, unit: str = "quantmesh-staging.service") -> None:
        self.unit = unit

    def restart(self) -> None:
        subprocess.run(["systemctl", "restart", self.unit], check=True)

    def stop(self) -> None:
        subprocess.run(["systemctl", "stop", self.unit], check=True)


def read_active_release(current: Path) -> Path | None:
    if not current.is_symlink():
        return None
    target = Path(os.readlink(current))
    if not target.is_absolute():
        target = current.parent / target
    return target.resolve(strict=False)


def activate_release(current: Path, target: Path | None) -> None:
    if target is None:
        current.unlink(missing_ok=True)
        return

    temporary = current.with_name(f".{current.name}-{uuid.uuid4().hex}")
    os.symlink(target, temporary, target_is_directory=True)
    try:
        os.replace(temporary, current)
    finally:
        temporary.unlink(missing_ok=True)


def read_health() -> Mapping[str, Any]:
    with urllib.request.urlopen(HEALTH_URL, timeout=3) as response:  # noqa: S310
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise DeploymentError("health response is not an object")
    return payload


def _matching_health(payload: Mapping[str, Any], commit: str, runtime_mode: str) -> bool:
    deployment = payload.get("deployment")
    return (
        payload.get("status") == "ok"
        and payload.get("runtime_mode") == runtime_mode
        and payload.get("paper_mode") is True
        and payload.get("live_trading") is False
        and isinstance(deployment, dict)
        and deployment.get("environment") == "staging"
        and deployment.get("build_ref") == commit
    )


def _wait_for_health(
    commit: str,
    *,
    runtime_mode: str,
    read: ReadHealth,
    attempts: int,
    sleep: Callable[[float], None],
) -> Mapping[str, Any]:
    if attempts < 1:
        raise DeploymentError("health attempts must be positive")
    last_problem = "identity, runtime mode or paper safety did not match"
    for attempt in range(attempts):
        try:
            payload = read()
            if _matching_health(payload, commit, runtime_mode):
                return payload
            last_problem = "identity, runtime mode or paper safety did not match"
        except (OSError, TimeoutError, ValueError, DeploymentError) as exc:
            last_problem = type(exc).__name__
        if attempt + 1 < attempts:
            sleep(1)
    raise DeploymentError(f"health check failed for {commit}: {last_problem}")


def _environment_text(commit: str, staging_origin: str, *, live_market_data: bool = False) -> str:
    # Retain the legacy demo environment exactly so old releases stay activatable.
    environment = (
        f"QUANTMESH_ENVIRONMENT=staging\nQUANTMESH_BUILD_REF={commit}\n"
        f"QUANTMESH_STAGING_ORIGIN={staging_origin}\n"
    )
    if live_market_data:
        environment += (
            "QUANTMESH_STAGING_ARGS=--live\n"
            "QUANTMESH_LIVE_WATCHLIST=BTC,ETH,SOL\n"
            "QUANTMESH_LAKE_ROOT=/var/lib/quantmesh/live/data\n"
            "QUANTMESH_ORDERS_DIR=/var/lib/quantmesh/live/orders\n"
            "QUANTMESH_DECISIONS_DIR=/var/lib/quantmesh/live/decisions\n"
        )
    return environment


def _retained_runtime_mode(commit: str, release: Path, staging_origin: str) -> str:
    validate_commit(commit)
    if not release.is_dir():
        raise DeploymentError(f"release does not exist: {release}")
    environment_file = release / ".staging.env"
    if not environment_file.is_file():
        raise DeploymentError(f"release identity does not match: {release}")
    environment = environment_file.read_text(encoding="utf-8")
    if environment == _environment_text(commit, staging_origin):
        return "demo"
    if environment == _environment_text(commit, staging_origin, live_market_data=True):
        return "live"
    raise DeploymentError(f"release identity does not match: {release}")


def _activate_and_verify(
    commit: str,
    release: Path,
    *,
    staging_origin: str,
    runtime_mode: str,
    service: ServiceControl,
    previous: Path | None,
    activate: Activate,
    read_health: ReadHealth,
    health_attempts: int,
    sleep: Callable[[float], None],
) -> DeploymentResult:
    activate(release)
    try:
        service.restart()
        health = _wait_for_health(
            commit,
            runtime_mode=runtime_mode,
            read=read_health,
            attempts=health_attempts,
            sleep=sleep,
        )
    except Exception as exc:
        try:
            if previous is None:
                activate(None)
                service.stop()
            else:
                previous_mode = _retained_runtime_mode(previous.name, previous, staging_origin)
                activate(previous)
                service.restart()
                _wait_for_health(
                    previous.name,
                    runtime_mode=previous_mode,
                    read=read_health,
                    attempts=health_attempts,
                    sleep=sleep,
                )
        except Exception as rollback_exc:
            original_problem = str(exc) if isinstance(exc, DeploymentError) else type(exc).__name__
            rollback_problem = (
                str(rollback_exc)
                if isinstance(rollback_exc, DeploymentError)
                else type(rollback_exc).__name__
            )
            raise DeploymentError(
                f"activation failed for {commit}: {original_problem}; "
                f"rollback failed: {rollback_problem}"
            ) from rollback_exc
        if isinstance(exc, DeploymentError):
            raise
        raise DeploymentError(f"health check failed for {commit}") from exc
    return DeploymentResult(commit=commit, release=release, health=health)


def deploy(
    commit: str,
    *,
    staging_origin: str,
    live_market_data: bool = False,
    layout: Layout = Layout(),
    repository_url: str = REPOSITORY_URL,
    run_command: RunCommand = run_command,
    service: ServiceControl | None = None,
    read_active: ReadActive | None = None,
    activate: Activate | None = None,
    read_health: ReadHealth = read_health,
    health_attempts: int = 30,
    sleep: Callable[[float], None] = time.sleep,
) -> DeploymentResult:
    commit = validate_commit(commit)
    staging_origin = validate_staging_origin(staging_origin)
    service = service or SystemdService()
    read_active = read_active or (lambda: read_active_release(layout.current))
    activate = activate or (lambda target: activate_release(layout.current, target))

    release = layout.releases / commit
    if release.exists():
        raise DeploymentError(f"release already exists: {release}")

    layout.root.mkdir(parents=True, exist_ok=True)
    layout.releases.mkdir(parents=True, exist_ok=True)
    if not layout.repository.exists():
        run_command(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                repository_url,
                str(layout.repository),
            ],
            None,
        )
    elif not (layout.repository / ".git").exists():
        raise DeploymentError(f"repository cache is not a Git repository: {layout.repository}")

    run_command(
        ["git", "-C", str(layout.repository), "fetch", "--depth=1", "origin", commit],
        None,
    )
    resolved = run_command(
        ["git", "-C", str(layout.repository), "rev-parse", "FETCH_HEAD"], None
    ).strip()
    if resolved != commit:
        raise DeploymentError(f"fetched commit mismatch: requested {commit}, resolved {resolved}")

    run_command(
        [
            "git",
            "-C",
            str(layout.repository),
            "worktree",
            "add",
            "--detach",
            str(release),
            commit,
        ],
        None,
    )
    run_command(["python3", "-m", "venv", str(release / ".venv")], None)
    release_python = release / ".venv" / "bin" / "python"
    run_command(
        [
            str(release_python),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            str(release),
        ],
        None,
    )
    (release / ".staging.env").write_text(
        _environment_text(commit, staging_origin, live_market_data=live_market_data),
        encoding="utf-8",
    )

    previous = read_active()
    return _activate_and_verify(
        commit,
        release,
        staging_origin=staging_origin,
        runtime_mode="live" if live_market_data else "demo",
        service=service,
        previous=previous,
        activate=activate,
        read_health=read_health,
        health_attempts=health_attempts,
        sleep=sleep,
    )


def activate_existing(
    commit: str,
    *,
    staging_origin: str,
    layout: Layout = Layout(),
    service: ServiceControl | None = None,
    read_active: ReadActive | None = None,
    activate: Activate | None = None,
    read_health: ReadHealth = read_health,
    health_attempts: int = 30,
    sleep: Callable[[float], None] = time.sleep,
) -> DeploymentResult:
    commit = validate_commit(commit)
    staging_origin = validate_staging_origin(staging_origin)
    service = service or SystemdService()
    read_active = read_active or (lambda: read_active_release(layout.current))
    activate = activate or (lambda target: activate_release(layout.current, target))

    release = layout.releases / commit
    runtime_mode = _retained_runtime_mode(commit, release, staging_origin)

    return _activate_and_verify(
        commit,
        release,
        staging_origin=staging_origin,
        runtime_mode=runtime_mode,
        service=service,
        previous=read_active(),
        activate=activate,
        read_health=read_health,
        health_attempts=health_attempts,
        sleep=sleep,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("commit", help="exact lowercase 40-character Git commit")
    parser.add_argument(
        "--origin", required=True, help="canonical https://<device>.<tailnet>.ts.net origin"
    )
    parser.add_argument(
        "--live-market-data",
        action="store_true",
        help="prepare the canonical BTC/ETH/SOL live-data profile with paper trading only",
    )
    parser.add_argument(
        "--activate-existing",
        action="store_true",
        help="reactivate a retained release instead of preparing a new one",
    )
    args = parser.parse_args()
    if args.activate_existing and args.live_market_data:
        parser.error("--activate-existing infers its retained profile; omit --live-market-data")
    try:
        if args.activate_existing:
            result = activate_existing(args.commit, staging_origin=args.origin)
        else:
            result = deploy(
                args.commit, staging_origin=args.origin, live_market_data=args.live_market_data
            )
    except (DeploymentError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"deployment failed: {exc}\n")
    print(f"activated {result.commit} at {result.release}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
