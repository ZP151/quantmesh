"""Behavioral contracts for the tiered local validation executor."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from tools import quality_gate
from tools.gate_policy import GateDecision, GateTier, decide_paths
from tools.quality_gate import (
    DOMAIN_TIMEOUT_SECONDS,
    E2E_TARGETS,
    FAST_TIMEOUT_SECONDS,
    MANDATORY_SAFETY_TARGETS,
    SLOW_TARGETS,
    GateCommand,
    build_commands,
    discover_e2e_targets,
    execute_commands,
    main,
    npm_test_argv,
    vitest_argv,
)


def _pytest_command(commands: tuple[GateCommand, ...]) -> GateCommand:
    return next(command for command in commands if command.name.startswith("pytest"))


def _positional_pytest_targets(command: GateCommand) -> tuple[str, ...]:
    arguments = iter(command.argv[command.argv.index("pytest") + 1 :])
    targets: list[str] = []
    for argument in arguments:
        if argument in {"-m", "--ignore"}:
            next(arguments)
        elif not argument.startswith("-"):
            targets.append(argument)
    return tuple(targets)


def _pytest_basetemp(command: GateCommand) -> Path:
    arguments = tuple(value for value in command.argv if value.startswith("--basetemp="))
    assert len(arguments) == 1
    return Path(arguments[0].partition("=")[2])


@pytest.mark.parametrize(
    ("mode", "domain"),
    [
        ("fast", None),
        ("domain", "workstation-shell"),
        ("browser", None),
        ("release", None),
    ],
)
def test_every_pytest_gate_command_has_a_distinct_external_basetemp(
    mode: str, domain: str | None
) -> None:
    """Each construction must avoid pytest's shared per-user temp/current alias."""

    decision = GateDecision(GateTier(mode if mode != "browser" else "browser"))
    first = _pytest_command(build_commands(mode, decision, domain))
    second = _pytest_command(build_commands(mode, decision, domain))
    first_basetemp = _pytest_basetemp(first)
    second_basetemp = _pytest_basetemp(second)

    assert first_basetemp.is_absolute()
    assert first_basetemp.parent == Path(tempfile.gettempdir())
    assert first_basetemp.name.startswith("quantmesh-pytest-")
    assert first_basetemp != second_basetemp
    assert not first_basetemp.exists()
    assert not second_basetemp.exists()


def test_non_pytest_gate_commands_do_not_receive_basetemp() -> None:
    decision = GateDecision(
        GateTier.FAST,
        pytest_targets=("frontend/src/screens/Watchlist.test.tsx",),
        frontend=True,
    )

    commands = build_commands("fast", decision)
    non_pytest = tuple(command for command in commands if "pytest" not in command.argv)

    assert {command.name for command in non_pytest} == {
        "ruff",
        "frontend lint",
        "frontend component tests",
    }
    assert all(
        not any(arg.startswith("--basetemp") for arg in command.argv) for command in non_pytest
    )


@pytest.mark.parametrize(("assertion", "expected_returncode"), [("True", 0), ("False", 1)])
def test_executor_removes_the_owned_pytest_basetemp_after_exit(
    tmp_path: Path, assertion: str, expected_returncode: int
) -> None:
    """Successful and failed child processes must not retain their isolated temp tree."""

    generated = _pytest_command(build_commands("release", GateDecision(GateTier.RELEASE)))
    basetemp_argument = next(arg for arg in generated.argv if arg.startswith("--basetemp="))
    basetemp = Path(basetemp_argument.partition("=")[2])
    probe = tmp_path / "test_probe.py"
    probe.write_text(
        f"def test_probe(tmp_path):\n    assert tmp_path.exists()\n    assert {assertion}\n",
        encoding="utf-8",
    )
    command = GateCommand(
        "pytest cleanup probe",
        (
            sys.executable,
            "-m",
            "pytest",
            "-q",
            str(probe),
            basetemp_argument,
        ),
        tmp_path,
        30,
    )

    try:
        assert execute_commands((command,)) == expected_returncode
        assert not basetemp.exists()
    finally:
        shutil.rmtree(basetemp, ignore_errors=True)


def test_fast_gate_excludes_browser_and_declared_slow_targets() -> None:
    """Removing an E2E/slow exclusion would make this routine gate unsafe."""

    command = _pytest_command(build_commands("fast", GateDecision(GateTier.FAST)))

    ignored = {
        command.argv[index + 1]
        for index, value in enumerate(command.argv[:-1])
        if value == "--ignore"
    }
    assert command.timeout_seconds == FAST_TIMEOUT_SECONDS == 600
    assert "-x" in command.argv
    assert "--durations=25" in command.argv
    assert set(E2E_TARGETS).issubset(ignored)
    assert set(SLOW_TARGETS).issubset(ignored)
    targets = command.argv[command.argv.index(MANDATORY_SAFETY_TARGETS[0]) :]
    assert not set(E2E_TARGETS).intersection(targets)
    assert not set(SLOW_TARGETS).intersection(targets)


def test_fast_gate_deduplicates_a_reviewed_python_target() -> None:
    """A repeated direct mapping must not make pytest execute one contract twice."""

    decision = GateDecision(
        GateTier.FAST,
        pytest_targets=("tests/test_ai_gateway.py", "tests/test_ai_gateway.py"),
    )

    command = _pytest_command(build_commands("fast", decision))

    assert command.argv.count("tests/test_ai_gateway.py") == 1


def test_fast_gate_runs_a_reviewed_frontend_component_test() -> None:
    """A mapped frontend test must be passed to Vitest rather than lint alone."""

    decision = decide_paths(["frontend/src/screens/Watchlist.test.tsx"])
    commands = build_commands("fast", decision)

    frontend_test = next(
        command for command in commands if command.name == "frontend component tests"
    )
    assert decision.pytest_targets == ("frontend/src/screens/Watchlist.test.tsx",)
    assert frontend_test.argv == vitest_argv(
        ("frontend/src/screens/Watchlist.test.tsx",), platform=os.name
    )
    assert frontend_test.argv[-1] == "src/screens/Watchlist.test.tsx"


def test_npm_and_vitest_argvs_are_shell_free_on_windows_and_posix() -> None:
    """A POSIX runner must never receive Windows' cmd.exe wrapper."""

    target = "frontend/src/screens/Watchlist.test.tsx"

    assert npm_test_argv((target,), platform="nt") == ("npm.cmd", "run", "test", "--", target)
    assert npm_test_argv((target,), platform="posix") == ("npm", "run", "test", "--", target)
    assert vitest_argv((target,), platform="nt") == (
        "npx.cmd",
        "vitest",
        "run",
        "src/screens/Watchlist.test.tsx",
    )
    assert vitest_argv((target,), platform="posix") == (
        "npx",
        "vitest",
        "run",
        "src/screens/Watchlist.test.tsx",
    )


def test_mapped_frontend_command_collects_the_existing_vitest_file() -> None:
    """A generated frontend command must collect its component file, not only look valid."""

    binary = "vitest.cmd" if os.name == "nt" else "vitest"
    if not (quality_gate.REPO / "frontend" / "node_modules" / ".bin" / binary).exists():
        pytest.skip("frontend dependencies are not installed in this local developer worktree")
    command = next(
        item
        for item in build_commands(
            "fast", decide_paths(["frontend/src/screens/Watchlist.test.tsx"])
        )
        if item.name == "frontend component tests"
    )

    result = subprocess.run(
        command.argv,
        cwd=command.cwd,
        capture_output=True,
        check=False,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert "Watchlist.test.tsx" in result.stdout


@pytest.mark.parametrize(
    ("domain", "required_targets"),
    [
        (
            "execution-connectors",
            {
                "tests/test_live_fence.py",
                "tests/test_enablement.py",
                "tests/test_paper_proposals.py",
                "tests/test_accounting.py",
                "tests/test_matcher.py",
                "tests/test_orders.py",
                "tests/test_store.py",
                "tests/test_account_store.py",
                "tests/test_numeric_policy.py",
                "tests/test_hyperliquid_wallet_isolation.py",
                "tests/test_hyperliquid_risk.py",
                "tests/test_hyperliquid_exchange.py",
                "tests/test_moomoo_execution.py",
                "tests/test_reconciliation_engine.py",
                "tests/test_moomoo_reconciliation.py",
                "tests/test_hyperliquid_reconciliation.py",
                "tests/test_recovery.py",
            },
        ),
        (
            "data-research",
            {
                "tests/test_research_baselines.py",
                "tests/test_research_pipelines.py",
                "tests/test_price_forecast.py",
                "tests/test_bitemporal_history.py",
                "tests/test_fabric_pipeline.py",
                "tests/test_raw_envelopes.py",
                "tests/test_artifact_manifests.py",
                "tests/test_collection_checkpoints.py",
                "tests/test_research_features.py",
                "tests/test_collection_recovery.py",
            },
        ),
        (
            "ai",
            {
                "tests/test_ai_redact.py",
                "tests/test_hyperliquid_wallet_isolation.py",
                "tests/test_security.py",
                "tests/test_ai_decisions.py",
                "tests/test_ai_acceptance.py",
            },
        ),
    ],
)
def test_domain_gate_has_reviewed_targets_and_mandatory_safety_floor(
    domain: str, required_targets: set[str]
) -> None:
    """Dropping a named safety contract must fail the domain gate contract."""

    command = _pytest_command(
        build_commands("domain", GateDecision(GateTier.DOMAIN, domains=(domain,)), domain)
    )

    assert command.timeout_seconds == DOMAIN_TIMEOUT_SECONDS == 1800
    assert "-x" in command.argv
    assert "--durations=50" in command.argv
    assert set(MANDATORY_SAFETY_TARGETS).issubset(command.argv)
    assert required_targets.issubset(command.argv)


def test_domain_targets_are_immutable_and_reject_unknown_domain() -> None:
    """A typo must not silently create an incomplete, unreviewed target set."""

    with pytest.raises(ValueError, match="unknown domain"):
        build_commands("domain", GateDecision(GateTier.DOMAIN), "not-a-domain")

    with pytest.raises(AttributeError):
        MANDATORY_SAFETY_TARGETS.append("tests/test_unreviewed.py")  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("domain", "expected_targets"),
    [
        (
            "workstation-shell",
            {
                "tests/test_api.py",
                "tests/test_spa_api.py",
                "tests/test_workstation.py",
                "tests/test_instrument_api.py",
                "tests/test_instrument_history.py",
                "tests/test_instrument_workspace_api.py",
                "tests/test_watchlist.py",
            },
        ),
        ("decision-inbox", {"tests/test_decision_inbox.py"}),
        ("decision-packet-api", {"tests/test_decision_packet_api.py"}),
        ("decision-packets", {"tests/test_decision_packets.py"}),
        ("packet-copilot", {"tests/test_packet_copilot.py"}),
        (
            "demo-runtime",
            {
                "tests/test_demo.py",
                "tests/test_demo_instrument_workspace.py",
                "tests/test_demo_reset_finalization.py",
                "tests/test_demo_reset_runtime.py",
            },
        ),
        ("packet-monitoring", {"tests/test_packet_monitoring.py"}),
        ("packet-review", {"tests/test_packet_reviews.py"}),
    ],
)
def test_workstation_subdomain_command_is_complete_bounded_and_keeps_timeout(
    domain: str, expected_targets: set[str]
) -> None:
    command = _pytest_command(
        build_commands("domain", GateDecision(GateTier.DOMAIN, domains=(domain,)), domain)
    )
    positional_targets = set(_positional_pytest_targets(command))

    assert command.timeout_seconds == DOMAIN_TIMEOUT_SECONDS == 1800
    assert positional_targets == set(MANDATORY_SAFETY_TARGETS) | expected_targets
    assert len(expected_targets) < 17


def test_research_framework_change_has_a_real_non_slow_positional_contract() -> None:
    """Framework scorecard coverage must be selected, not merely named by --ignore."""

    decision = decide_paths(["src/quantmesh/research/frameworks.py"])
    command = _pytest_command(build_commands("domain", decision, "data-research"))
    positional_targets = _positional_pytest_targets(command)
    ignored_targets = {
        command.argv[index + 1]
        for index, argument in enumerate(command.argv[:-1])
        if argument == "--ignore"
    }

    assert decision.tier is GateTier.DOMAIN
    assert decision.domains == ("data-research",)
    assert "tests/test_framework_scorecard.py" in positional_targets
    assert "tests/test_framework_bakeoff_contract.py" not in positional_targets
    assert "tests/test_framework_bakeoff_contract.py" in ignored_targets


def test_e2e_gate_discovers_every_matching_test_file() -> None:
    """A newly added browser-flow file must be selected without hand-editing a list."""

    repository = Path(__file__).resolve().parents[1]
    expected = tuple(
        sorted(
            path.relative_to(repository).as_posix()
            for path in (repository / "tests").glob("test_*e2e.py")
        )
    )

    assert discover_e2e_targets(repository) == expected
    command = _pytest_command(build_commands("browser", GateDecision(GateTier.BROWSER)))
    assert E2E_TARGETS == expected
    assert set(expected).issubset(command.argv)
    assert "-x" in command.argv
    assert "--durations=50" in command.argv
    assert command.timeout_seconds == DOMAIN_TIMEOUT_SECONDS


def test_diagnostic_full_is_fail_fast_but_never_certification(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Changing diagnostic full into a certification command would misrepresent evidence."""

    command = _pytest_command(build_commands("release", GateDecision(GateTier.RELEASE)))

    assert "-x" in command.argv
    assert "--durations=50" in command.argv
    assert "tests" in command.argv

    with pytest.raises(SystemExit) as error:
        main(["release"])
    assert error.value.code == 2
    assert "tools/release_gate.py" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("decision", "required_commands"),
    [
        (
            GateDecision(GateTier.RELEASE, reasons=("safety:tools/quality_gate.py",)),
            ("python tools/quality_gate.py release --diagnostic",),
        ),
        (
            GateDecision(
                GateTier.BROWSER,
                domains=("decision-inbox", "workstation-shell"),
            ),
            (
                "python tools/quality_gate.py domain --domain decision-inbox",
                "python tools/quality_gate.py domain --domain workstation-shell",
                "python tools/quality_gate.py browser",
            ),
        ),
        (
            GateDecision(GateTier.DOMAIN, domains=("ai",)),
            ("python tools/quality_gate.py domain --domain ai",),
        ),
        (
            GateDecision(GateTier.DOMAIN, domains=("ai", "data-research")),
            (
                "python tools/quality_gate.py domain --domain ai",
                "python tools/quality_gate.py domain --domain data-research",
            ),
        ),
    ],
)
def test_fast_base_refuses_every_stronger_decision_with_exact_follow_up_commands(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    decision: GateDecision,
    required_commands: tuple[str, ...],
) -> None:
    """A fail-closed decision must not silently fall through to the fast suite."""

    monkeypatch.setattr(quality_gate, "_decision_from_args", lambda *_args: decision)
    monkeypatch.setattr(quality_gate, "execute_commands", pytest.fail)

    assert quality_gate.main(["fast", "--base", "origin/main"]) == 2
    output = capsys.readouterr().out
    for command in required_commands:
        assert command in output


def test_fast_base_docs_only_keeps_safety_floor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A docs decision still runs the mandatory safety floor."""

    monkeypatch.setattr(
        quality_gate,
        "_decision_from_args",
        lambda *_args: GateDecision(GateTier.FAST, reasons=("docs-only",)),
    )
    commands = []
    monkeypatch.setattr(quality_gate, "execute_commands", lambda items: commands.extend(items) or 0)

    assert quality_gate.main(["fast", "--base", "origin/main"]) == 0
    assert set(MANDATORY_SAFETY_TARGETS).issubset(_pytest_command(tuple(commands)).argv)


def test_executor_timeout_reaps_a_real_grandchild(tmp_path: Path) -> None:
    """A timeout must not leave a server-like grandchild holding later gate state."""

    started = tmp_path / "grandchild-started"
    finished = tmp_path / "grandchild-finished"
    grandchild = (
        "import pathlib, sys, time; "
        "pathlib.Path(sys.argv[1]).touch(); time.sleep(3); pathlib.Path(sys.argv[2]).touch()"
    )
    parent = (
        "import subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}, sys.argv[1], sys.argv[2]]); "
        "time.sleep(10)"
    )

    command = GateCommand(
        "timeout probe", (sys.executable, "-c", parent, str(started), str(finished)), tmp_path, 1
    )
    result = execute_commands((command,))

    assert result == 1
    assert started.exists(), "the grandchild must have started before the timeout"
    time.sleep(3.2)
    assert not finished.exists(), "timeout cleanup must reap the grandchild tree"


def test_posix_cleanup_kills_the_group_after_its_leader_exits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful leader wait must not suppress the final group SIGKILL."""

    class ExitedLeader:
        def poll(self) -> int:
            return 0

        def wait(self, timeout: float | None = None) -> int:
            return 0

        def kill(self) -> None:
            pytest.fail("the exited leader must not be killed directly")

    signals: list[int] = []
    monkeypatch.setattr(
        quality_gate.os,
        "killpg",
        lambda _pgid, sig: signals.append(sig),
        raising=False,
    )
    monkeypatch.setattr(quality_gate.signal, "SIGKILL", 9, raising=False)

    quality_gate._kill_process_tree(ExitedLeader(), process_group_id=42, platform="posix")

    assert signals == [signal.SIGTERM, 9]


@pytest.mark.skipif(os.name == "nt", reason="POSIX process groups are unavailable on Windows")
def test_posix_timeout_reaps_a_sigterm_resistant_grandchild(tmp_path: Path) -> None:
    """A descendant that ignores TERM must still die with its owned process group."""

    started = tmp_path / "stubborn-grandchild-started"
    finished = tmp_path / "stubborn-grandchild-finished"
    grandchild = (
        "import pathlib, signal, sys, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "pathlib.Path(sys.argv[1]).touch(); time.sleep(3); pathlib.Path(sys.argv[2]).touch()"
    )
    parent = (
        "import signal, subprocess, sys, time; "
        "signal.signal(signal.SIGTERM, lambda *_args: sys.exit(0)); "
        f"subprocess.Popen([sys.executable, '-c', {grandchild!r}, sys.argv[1], sys.argv[2]]); "
        "time.sleep(10)"
    )
    command = GateCommand(
        "posix stubborn tree",
        (sys.executable, "-c", parent, str(started), str(finished)),
        tmp_path,
        1,
    )

    assert execute_commands((command,)) == 1
    assert started.exists()
    time.sleep(3.2)
    assert not finished.exists(), "SIGKILL must reap a TERM-resistant descendant"


def test_quality_gate_script_runs_from_the_repository_root() -> None:
    """Direct CLI execution must resolve the policy module outside pytest imports."""

    result = subprocess.run(
        [sys.executable, "tools/quality_gate.py", "decide", "--paths", "docs/guide.md"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert result.stdout == (
        '{"domains":[],"frontend":false,"pytest_targets":[],'
        '"reasons":["docs-only"],"tier":"fast"}\n'
    )


def test_executor_stops_after_the_first_failed_command(
    tmp_path: Path,
) -> None:
    """A later command must not run after a failed prerequisite."""

    second_ran = tmp_path / "second-ran"
    commands = (
        GateCommand("first", (sys.executable, "-c", "raise SystemExit(3)"), tmp_path, 1),
        GateCommand(
            "second",
            (sys.executable, "-c", f"from pathlib import Path; Path({str(second_ran)!r}).touch()"),
            tmp_path,
            1,
        ),
    )

    assert execute_commands(commands) == 3
    assert not second_ran.exists()


def test_tier_plan_only_does_not_spawn(monkeypatch, capsys):
    monkeypatch.setattr(quality_gate, "execute_commands", pytest.fail)
    assert main(["--tier", "fast", "--plan-only"]) == 0
    import json

    plan = json.loads(capsys.readouterr().out)
    assert plan["tier"] == "fast"
    assert set(MANDATORY_SAFETY_TARGETS).issubset(plan["commands"][-1]["argv"])


def test_executor_timeout_retains_machine_readable_evidence(tmp_path):
    import json

    command = GateCommand(
        "owned timeout",
        (
            sys.executable,
            "-u",
            "-c",
            "import time; print('probe alive', flush=True); time.sleep(2)",
        ),
        tmp_path,
        0.3,
    )
    assert execute_commands((command,), logs=tmp_path / "logs", progress_interval_seconds=0.05) != 0
    events = [
        json.loads(line) for line in (tmp_path / "logs/events.jsonl").read_text().splitlines()
    ]
    assert events[0]["event"] == "step_started"
    assert events[-1]["event"] == "step_finished"
    assert events[-1]["exit_code"] != 0
    assert events[-1]["timed_out"] is True
    assert events[-1]["slow_tests"] == []
    assert Path(events[-1]["log_path"]).read_text().startswith("probe alive")
    assert events[-1]["elapsed_seconds"] > 0
    assert events[-1]["timestamp"] >= events[0]["timestamp"]
    assert any(event["event"] == "step_progress" for event in events)


def test_executor_retains_real_slow_test_summary(tmp_path):
    import json

    probe = tmp_path / "test_slow_probe.py"
    probe.write_text("import time\ndef test_probe():\n    time.sleep(0.02)\n")
    command = GateCommand(
        "slow evidence",
        (sys.executable, "-m", "pytest", "-q", "--durations=1", str(probe)),
        tmp_path,
        15,
    )
    assert execute_commands((command,), logs=tmp_path / "logs") == 0
    events = [
        json.loads(line) for line in (tmp_path / "logs/events.jsonl").read_text().splitlines()
    ]
    assert any(
        "call" in row and "test_slow_probe.py::test_probe" in row
        for row in events[-1]["slow_tests"]
    )
