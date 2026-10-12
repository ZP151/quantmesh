"""Run bounded local validation; use ``tools/release_gate.py`` to certify a release.

The commands here deliberately use already-installed developer dependencies.
They are fast diagnostic evidence, never a clean-checkout release certification.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

if __package__:
    from tools import release_gate
    from tools.gate_policy import (
        DOMAIN_TARGETS,
        MANDATORY_SAFETY_TARGETS,
        GateDecision,
        GateTier,
        _diff_paths,
        decide_paths,
    )
else:  # pragma: no cover - direct ``python tools/quality_gate.py`` invocation.
    import release_gate
    from gate_policy import (
        DOMAIN_TARGETS,
        MANDATORY_SAFETY_TARGETS,
        GateDecision,
        GateTier,
        _diff_paths,
        decide_paths,
    )

REPO = Path(__file__).resolve().parents[1]
FAST_TIMEOUT_SECONDS = 600
DOMAIN_TIMEOUT_SECONDS = 1800
FULL_DIAGNOSTIC_TIMEOUT_SECONDS = 10800
SLOW_TARGETS = (
    "tests/test_finrl_x_bakeoff.py",
    "tests/test_framework_bakeoff_contract.py",
    "tests/test_nautilus_bakeoff.py",
    "tests/test_trusted_data_soak.py",
)
PYTEST_BASETEMP_PREFIX = "quantmesh-pytest-"


@dataclass(frozen=True, slots=True)
class GateCommand:
    """One auditable local command in a selected validation gate."""

    name: str
    argv: tuple[str, ...]
    cwd: Path
    timeout_seconds: int


def discover_e2e_targets(repository: Path = REPO) -> tuple[str, ...]:
    """Return every browser E2E module currently present in ``tests``."""

    tests_root = repository / "tests"
    return tuple(
        sorted(path.relative_to(repository).as_posix() for path in tests_root.glob("test_*e2e.py"))
    )


E2E_TARGETS = discover_e2e_targets()


def _pytest_command(
    name: str,
    targets: Iterable[str],
    *,
    durations: int,
    timeout_seconds: int,
    ignored: Iterable[str] = (),
    exclude_marked_slow_or_e2e: bool = False,
) -> GateCommand:
    basetemp = Path(tempfile.gettempdir()) / (
        f"{PYTEST_BASETEMP_PREFIX}{os.getpid()}-{uuid.uuid4().hex}"
    )
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        f"--durations={durations}",
        f"--basetemp={basetemp}",
    ]
    if exclude_marked_slow_or_e2e:
        argv.extend(("-m", "not slow and not e2e"))
    for target in ignored:
        argv.extend(("--ignore", target))
    argv.extend(targets)
    return GateCommand(name, tuple(argv), REPO, timeout_seconds)


def _ruff_command() -> GateCommand:
    return GateCommand(
        "ruff",
        (sys.executable, "-m", "ruff", "check", "src", "tests", "tools"),
        REPO,
        FAST_TIMEOUT_SECONDS,
    )


def _owned_pytest_basetemp(command: GateCommand) -> Path | None:
    """Return a validated temp tree owned by one generated pytest command."""

    if command.argv[1:3] != ("-m", "pytest"):
        return None
    arguments = tuple(arg for arg in command.argv if arg.startswith("--basetemp="))
    if not arguments:
        return None
    if len(arguments) != 1:
        raise RuntimeError(f"pytest command has ambiguous basetemp: {command.name}")
    basetemp = Path(arguments[0].partition("=")[2])
    suffix = basetemp.name.removeprefix(PYTEST_BASETEMP_PREFIX)
    process_id, separator, token = suffix.partition("-")
    is_owned_name = (
        basetemp.name.startswith(PYTEST_BASETEMP_PREFIX)
        and process_id.isdecimal()
        and separator == "-"
        and len(token) == 32
        and all(character in "0123456789abcdef" for character in token)
    )
    if (
        not basetemp.is_absolute()
        or basetemp.parent != Path(tempfile.gettempdir())
        or not is_owned_name
    ):
        raise RuntimeError(f"refusing unsafe pytest basetemp cleanup: {basetemp}")
    return basetemp


def _cleanup_pytest_basetemp(command: GateCommand) -> None:
    """Remove only the uniquely named external tree owned by this command."""

    basetemp = _owned_pytest_basetemp(command)
    if basetemp is None or not basetemp.exists():
        return

    def make_writable(function: Callable[[str], object], path: str, _error: object) -> None:
        os.chmod(path, os.stat(path).st_mode | stat.S_IWRITE)
        function(path)

    shutil.rmtree(basetemp, onerror=make_writable)


def npm_test_argv(targets: Iterable[str], *, platform: str = os.name) -> tuple[str, ...]:
    """Return the shell-free npm test argv for the requested OS family."""

    npm = "npm.cmd" if platform == "nt" else "npm"
    return (npm, "run", "test", "--", *targets)


def vitest_argv(targets: Iterable[str], *, platform: str = os.name) -> tuple[str, ...]:
    """Return shell-free Vitest argv with paths relative to the frontend cwd."""

    relative_targets: list[str] = []
    for target in targets:
        try:
            relative_targets.append(PurePosixPath(target).relative_to("frontend").as_posix())
        except ValueError as error:
            raise ValueError(f"frontend test target must start with frontend/: {target}") from error
    npx = "npx.cmd" if platform == "nt" else "npx"
    return (npx, "vitest", "run", *relative_targets)


def _targets_for_domain(domain: str) -> tuple[str, ...]:
    try:
        domain_targets = DOMAIN_TARGETS[domain]
    except KeyError as error:
        raise ValueError(f"unknown domain: {domain}") from error
    return tuple(dict.fromkeys((*MANDATORY_SAFETY_TARGETS, *domain_targets)))


def build_commands(
    mode: str, decision: GateDecision, domain: str | None = None
) -> tuple[GateCommand, ...]:
    """Build explicit local validation commands without executing them."""

    if mode == "fast":
        commands = [_ruff_command()]
        mapped_python_targets = tuple(
            dict.fromkeys(
                target for target in decision.pytest_targets if target.startswith("tests/")
            )
        )
        mapped_frontend_targets = tuple(
            dict.fromkeys(
                target for target in decision.pytest_targets if target.startswith("frontend/")
            )
        )
        if decision.frontend:
            commands.append(
                GateCommand(
                    "frontend lint",
                    npm_test_argv((), platform=os.name)[:1] + ("run", "lint"),
                    REPO / "frontend",
                    FAST_TIMEOUT_SECONDS,
                )
            )
        if mapped_frontend_targets:
            commands.append(
                GateCommand(
                    "frontend component tests",
                    vitest_argv(mapped_frontend_targets),
                    REPO / "frontend",
                    FAST_TIMEOUT_SECONDS,
                )
            )
        commands.append(
            _pytest_command(
                "pytest fast",
                (
                    *MANDATORY_SAFETY_TARGETS,
                    "tests/test_gate_policy.py",
                    "tests/test_quality_gate.py",
                    *mapped_python_targets,
                ),
                durations=25,
                timeout_seconds=FAST_TIMEOUT_SECONDS,
                ignored=(*E2E_TARGETS, *SLOW_TARGETS),
                exclude_marked_slow_or_e2e=True,
            )
        )
        return tuple(commands)
    if mode == "domain":
        if domain is None:
            raise ValueError("domain mode requires a domain name")
        return (
            _ruff_command(),
            _pytest_command(
                f"pytest domain {domain}",
                _targets_for_domain(domain),
                durations=50,
                timeout_seconds=DOMAIN_TIMEOUT_SECONDS,
                ignored=(*E2E_TARGETS, *SLOW_TARGETS),
                exclude_marked_slow_or_e2e=True,
            ),
        )
    if mode == "browser":
        return (
            _pytest_command(
                "pytest e2e",
                E2E_TARGETS,
                durations=50,
                timeout_seconds=DOMAIN_TIMEOUT_SECONDS,
            ),
        )
    if mode == "release":
        return (
            _pytest_command(
                "pytest full diagnostic",
                ("tests",),
                durations=50,
                timeout_seconds=FULL_DIAGNOSTIC_TIMEOUT_SECONDS,
            ),
        )
    raise ValueError(f"unknown gate mode: {mode}")


def execute_commands(
    commands: Iterable[GateCommand],
    *,
    logs: Path | None = None,
    progress_interval_seconds: float = release_gate.DEFAULT_PROGRESS_INTERVAL_SECONDS,
) -> int:
    """Retain owned-process evidence and stop diagnostic runs at first failure."""
    logs = logs or (
        Path(os.environ["QUANTMESH_GATE_LOGS"])
        if os.environ.get("QUANTMESH_GATE_LOGS")
        else Path(tempfile.mkdtemp(prefix="quantmesh-gate-"))
    )
    logs.mkdir(parents=True, exist_ok=True)
    release_gate.STEPS.clear()
    for command in commands:
        try:
            ok, _ = release_gate.run_step(
                command.name,
                list(command.argv),
                command.cwd,
                logs,
                timeout=command.timeout_seconds,
                progress_interval_seconds=progress_interval_seconds,
            )
            if not ok:
                events = (logs / "events.jsonl").read_text(encoding="utf-8").splitlines()
                finished = json.loads(events[-1])
                return 1 if finished["timed_out"] else int(finished["exit_code"] or 1)
        finally:
            _cleanup_pytest_basetemp(command)
    return 0


def _kill_process_tree(
    proc: subprocess.Popen[object],
    *,
    process_group_id: int | None = None,
    platform: str | None = None,
) -> None:
    """Reap the complete owned command tree with bounded platform cleanup."""

    current_platform = os.name if platform is None else platform
    if current_platform == "nt":
        if proc.poll() is not None:
            return
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            pass
    else:
        group_id = proc.pid if process_group_id is None else process_group_id
        try:
            os.killpg(group_id, signal.SIGTERM)
        except ProcessLookupError:
            pass
        # The group can retain descendants after its leader has exited.  Keep
        # the group ID and always send the final signal after a bounded grace.
        time.sleep(0.2)
        try:
            os.killpg(group_id, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if proc.poll() is None:
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:  # pragma: no cover - platform process failure.
        pass


def _required_follow_up_commands(decision: GateDecision) -> tuple[str, ...]:
    """Return the commands required when a base diff selects a stronger tier."""

    if decision.tier is GateTier.RELEASE:
        return ("python tools/quality_gate.py release --diagnostic",)
    commands = tuple(
        f"python tools/quality_gate.py domain --domain {domain}" for domain in decision.domains
    )
    if decision.tier is GateTier.BROWSER:
        commands += ("python tools/quality_gate.py browser",)
    return commands


def _decision_from_args(
    base: str | None, head: str | None, paths: list[str] | None
) -> GateDecision:
    if paths is not None:
        return decide_paths(paths)
    if base is None:
        return GateDecision(GateTier.FAST, reasons=("explicit-local-gate",))
    diff_paths = _diff_paths(base, head or "HEAD")
    return (
        decide_paths(diff_paths)
        if diff_paths is not None
        else GateDecision(GateTier.RELEASE, reasons=("git-diff-unavailable",))
    )


def _run_or_plan(
    mode: str, decision: GateDecision, domain: str | None = None, *, plan_only: bool = False
) -> int:
    commands = build_commands(mode, decision, domain)
    if plan_only:
        print(
            json.dumps(
                {
                    "tier": mode,
                    "commands": [
                        {
                            "name": c.name,
                            "argv": list(c.argv),
                            "cwd": str(c.cwd),
                            "timeout_seconds": c.timeout_seconds,
                        }
                        for c in commands
                    ],
                },
                sort_keys=True,
            )
        )
        return 0
    return execute_commands(commands)


def main(argv: list[str] | None = None) -> int:
    """Run the local tier selected by the requested CLI subcommand."""

    argv = list(sys.argv[1:] if argv is None else argv)
    if "--tier" in argv:
        index = argv.index("--tier")
        if index + 1 < len(argv):
            tier = argv[index + 1]
            del argv[index : index + 2]
            argv.insert(0, tier)
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    fast = subparsers.add_parser("fast", help="run bounded routine validation")
    fast.add_argument("--base", help="git diff base reference")
    fast.add_argument("--head", default="HEAD", help="git diff head reference")
    domain_parser = subparsers.add_parser("domain", help="run one reviewed domain suite")
    domain_parser.add_argument("--domain", required=True, choices=tuple(DOMAIN_TARGETS))
    browser = subparsers.add_parser("browser", help="run every discovered browser E2E module")
    full = subparsers.add_parser("release", help="run diagnostic full pytest; not certification")
    full.add_argument(
        "--diagnostic",
        action="store_true",
        help="acknowledge this is diagnostic; use tools/release_gate.py to certify",
    )
    decide = subparsers.add_parser("decide", help="print the changed-path decision")
    input_group = decide.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--paths", nargs="+", help="explicit repository-relative paths")
    input_group.add_argument("--base", help="git diff base reference")
    decide.add_argument("--head", default="HEAD", help="git diff head reference")
    for subparser in (fast, domain_parser, full, browser):
        subparser.add_argument(
            "--plan-only", action="store_true", help="print commands without running"
        )
    args = parser.parse_args(argv)

    if args.command == "decide":
        print(_decision_from_args(args.base, args.head, args.paths).to_json())
        return 0
    if args.command == "fast":
        decision = _decision_from_args(args.base, args.head, None)
        if decision.tier in {GateTier.RELEASE, GateTier.DOMAIN, GateTier.BROWSER}:
            print("REFUSED: fast validation is insufficient for this changed-path decision.")
            for command in _required_follow_up_commands(decision):
                print(f"Required: {command}")
            return 2
        return _run_or_plan("fast", decision, plan_only=args.plan_only)
    if args.command == "domain":
        decision = GateDecision(GateTier.DOMAIN, domains=(args.domain,))
        return _run_or_plan("domain", decision, args.domain, plan_only=args.plan_only)
    if args.command == "browser":
        return _run_or_plan("browser", GateDecision(GateTier.BROWSER), plan_only=args.plan_only)
    if args.plan_only:
        print(
            json.dumps(
                {
                    "tier": "release",
                    "certification": [sys.executable, "tools/release_gate.py"],
                    "diagnostic_commands": [
                        list(c.argv)
                        for c in build_commands("release", GateDecision(GateTier.RELEASE))
                    ],
                },
                sort_keys=True,
            )
        )
        return 0
    if not args.diagnostic:
        parser.error(
            "full local pytest is diagnostic only; use tools/release_gate.py to certify a release"
        )
    return execute_commands(build_commands("release", GateDecision(GateTier.RELEASE)))


if __name__ == "__main__":
    raise SystemExit(main())
