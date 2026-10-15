"""Regression tests for the fail-closed changed-path validation policy."""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from tools.gate_policy import (
    DOMAIN_SOURCE_PATHS,
    DOMAIN_TARGETS,
    GateTier,
    _diff_paths,
    decide_paths,
)

_OLD_WORKSTATION_TARGETS = {
    "tests/test_api.py",
    "tests/test_spa_api.py",
    "tests/test_workstation.py",
    "tests/test_decision_inbox.py",
    "tests/test_decision_packet_api.py",
    "tests/test_decision_packets.py",
    "tests/test_packet_copilot.py",
    "tests/test_packet_monitoring.py",
    "tests/test_packet_reviews.py",
    "tests/test_demo.py",
    "tests/test_demo_instrument_workspace.py",
    "tests/test_demo_reset_finalization.py",
    "tests/test_demo_reset_runtime.py",
    "tests/test_instrument_api.py",
    "tests/test_instrument_history.py",
    "tests/test_instrument_workspace_api.py",
    "tests/test_watchlist.py",
}

_WORKSTATION_SUBDOMAIN_TARGETS = {
    "workstation-shell": {
        "tests/test_api.py",
        "tests/test_spa_api.py",
        "tests/test_workstation.py",
        "tests/test_instrument_api.py",
        "tests/test_instrument_history.py",
        "tests/test_instrument_workspace_api.py",
        "tests/test_watchlist.py",
    },
    "decision-inbox": {"tests/test_decision_inbox.py"},
    "decision-packet-api": {"tests/test_decision_packet_api.py"},
    "decision-packets": {"tests/test_decision_packets.py"},
    "packet-copilot": {"tests/test_packet_copilot.py"},
    "demo-runtime": {
        "tests/test_demo.py",
        "tests/test_demo_instrument_workspace.py",
        "tests/test_demo_reset_finalization.py",
        "tests/test_demo_reset_runtime.py",
    },
    "packet-monitoring": {"tests/test_packet_monitoring.py"},
    "packet-review": {"tests/test_packet_reviews.py"},
}

_CROSS_CUTTING_WORKSTATION_SOURCES = {
    "src/quantmesh/api/workstation.py",
    "src/quantmesh/demo/runtime.py",
    "src/quantmesh/demo/seeder.py",
}

_DECISION_SUBDOMAINS = (
    "decision-inbox",
    "decision-packet-api",
    "decision-packets",
    "packet-copilot",
)


def _git(repository: Path, *args: str, input_text: str | None = None) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=repository,
        check=True,
        capture_output=True,
        input=input_text,
        text=True,
    ).stdout.strip()


def _committed_repository(tmp_path: Path) -> tuple[Path, str]:
    repository = tmp_path / "repository"
    repository.mkdir()
    _git(repository, "init")
    _git(repository, "config", "user.name", "Gate Policy Test")
    _git(repository, "config", "user.email", "gate-policy@example.invalid")
    (repository / "src/quantmesh/risk").mkdir(parents=True)
    (repository / "docs").mkdir()
    (repository / "README.md").write_text("baseline\n", encoding="utf-8")
    (repository / "src/quantmesh/risk/guard.py").write_text("SAFE = True\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "baseline")
    return repository, _git(repository, "rev-parse", "HEAD")


def test_workstation_contract_is_partitioned_into_bounded_reviewed_subdomains() -> None:
    selected = {domain: set(DOMAIN_TARGETS[domain]) for domain in _WORKSTATION_SUBDOMAIN_TARGETS}
    membership = Counter(target for targets in selected.values() for target in targets)

    assert selected == _WORKSTATION_SUBDOMAIN_TARGETS
    assert set(membership) == _OLD_WORKSTATION_TARGETS
    assert set(membership.values()) == {1}
    assert all(len(targets) < len(_OLD_WORKSTATION_TARGETS) for targets in selected.values())
    assert "workstation" not in DOMAIN_TARGETS
    assert "decision-core" not in DOMAIN_TARGETS


def test_each_legacy_workstation_test_selects_its_one_reviewed_subdomain() -> None:
    for domain, targets in _WORKSTATION_SUBDOMAIN_TARGETS.items():
        for target in targets:
            decision = decide_paths([target])

            assert decision.tier is GateTier.DOMAIN
            assert decision.domains == (domain,)


def test_workstation_source_allowlist_is_exact_and_cross_cutting_only_when_reviewed() -> None:
    shell_sources = set(DOMAIN_SOURCE_PATHS["workstation-shell"])

    assert {path for path in shell_sources if path.startswith("src/quantmesh/api/")} == {
        "src/quantmesh/api/app.py",
        "src/quantmesh/api/static/style.css",
        "src/quantmesh/api/templates/audit.html",
        "src/quantmesh/api/templates/base.html",
        "src/quantmesh/api/templates/document_detail.html",
        "src/quantmesh/api/templates/enablement.html",
        "src/quantmesh/api/templates/experiment_detail.html",
        "src/quantmesh/api/templates/experiments.html",
        "src/quantmesh/api/templates/forecasts.html",
        "src/quantmesh/api/templates/instruments.html",
        "src/quantmesh/api/templates/kill_switch.html",
        "src/quantmesh/api/templates/orders.html",
        "src/quantmesh/api/templates/overview.html",
        "src/quantmesh/api/templates/pnl.html",
        "src/quantmesh/api/templates/positions.html",
        "src/quantmesh/api/templates/promotions.html",
        "src/quantmesh/api/templates/risk.html",
        "src/quantmesh/api/templates/watchlist.html",
        "src/quantmesh/api/watchlist.py",
        "src/quantmesh/api/workstation.py",
    }
    assert shell_sources - {
        path for path in shell_sources if path.startswith("src/quantmesh/api/")
    } == _CROSS_CUTTING_WORKSTATION_SOURCES - {"src/quantmesh/api/workstation.py"}
    for domain in _DECISION_SUBDOMAINS:
        assert set(DOMAIN_SOURCE_PATHS[domain]) == _CROSS_CUTTING_WORKSTATION_SOURCES
    assert set(DOMAIN_SOURCE_PATHS["packet-monitoring"]) == (_CROSS_CUTTING_WORKSTATION_SOURCES)
    assert set(DOMAIN_SOURCE_PATHS["packet-review"]) == _CROSS_CUTTING_WORKSTATION_SOURCES
    assert set(DOMAIN_SOURCE_PATHS["demo-runtime"]) == (
        _CROSS_CUTTING_WORKSTATION_SOURCES
        | {
            "src/quantmesh/demo/datalink.py",
            "src/quantmesh/demo/generators.py",
        }
    )


@pytest.mark.parametrize(
    ("path", "tier", "domains"),
    [
        ("src/quantmesh/api/app.py", GateTier.BROWSER, ("workstation-shell",)),
        (
            "src/quantmesh/api/workstation.py",
            GateTier.BROWSER,
            (
                *_DECISION_SUBDOMAINS[:3],
                "demo-runtime",
                _DECISION_SUBDOMAINS[3],
                "packet-monitoring",
                "packet-review",
                "workstation-shell",
            ),
        ),
        ("src/quantmesh/api/templates/overview.html", GateTier.DOMAIN, ("workstation-shell",)),
        ("src/quantmesh/demo/datalink.py", GateTier.DOMAIN, ("demo-runtime",)),
        ("src/quantmesh/demo/generators.py", GateTier.DOMAIN, ("demo-runtime",)),
        (
            "src/quantmesh/demo/runtime.py",
            GateTier.DOMAIN,
            (
                *_DECISION_SUBDOMAINS[:3],
                "demo-runtime",
                _DECISION_SUBDOMAINS[3],
                "packet-monitoring",
                "packet-review",
                "workstation-shell",
            ),
        ),
        (
            "src/quantmesh/demo/seeder.py",
            GateTier.DOMAIN,
            (
                *_DECISION_SUBDOMAINS[:3],
                "demo-runtime",
                _DECISION_SUBDOMAINS[3],
                "packet-monitoring",
                "packet-review",
                "workstation-shell",
            ),
        ),
        ("frontend/src/App.tsx", GateTier.BROWSER, ("workstation-shell",)),
    ],
)
def test_workstation_sources_select_exact_reviewed_subdomains(
    path: str, tier: GateTier, domains: tuple[str, ...]
) -> None:
    decision = decide_paths([path])

    assert decision.tier is tier
    assert decision.domains == domains


def test_normalizes_separators_and_sorts_all_decision_values() -> None:
    decision = decide_paths(
        [
            "src\\quantmesh\\ai\\gateway.py",
            "src/quantmesh/research/frameworks.py",
            "src/quantmesh/ai/roles.py",
        ]
    )

    assert decision.tier is GateTier.DOMAIN
    assert decision.domains == ("ai", "data-research")
    assert decision.reasons == (
        "domain:ai",
        "domain:data-research",
    )
    assert decision.pytest_targets == ("tests/test_ai_gateway.py",)


def test_docs_only_change_requires_no_pytest() -> None:
    decision = decide_paths(["README.md", "docs/adr/0020-gates.md"])

    assert decision.tier is GateTier.FAST
    assert decision.domains == ()
    assert decision.pytest_targets == ()
    assert decision.frontend is False
    assert decision.reasons == ("docs-only",)


def test_frontend_only_change_adds_browser_e2e() -> None:
    decision = decide_paths(["frontend/src/routes/Watchlist.tsx"])

    assert decision.tier is GateTier.BROWSER
    assert decision.domains == ("workstation-shell",)
    assert decision.frontend is True
    assert decision.pytest_targets == ()
    assert decision.reasons == ("domain:workstation-shell", "frontend", "browser")


def test_multi_domain_change_is_deterministic() -> None:
    decision = decide_paths(
        [
            "src/quantmesh/ai/gateway.py",
            "src/quantmesh/api/workstation.py",
            "src/quantmesh/research/frameworks.py",
        ]
    )

    assert decision.tier is GateTier.BROWSER
    assert decision.domains == (
        "ai",
        "data-research",
        "decision-inbox",
        "decision-packet-api",
        "decision-packets",
        "demo-runtime",
        "packet-copilot",
        "packet-monitoring",
        "packet-review",
        "workstation-shell",
    )
    assert decision.pytest_targets == (
        "tests/test_ai_gateway.py",
        "tests/test_spa_api.py",
        "tests/test_workstation.py",
    )
    assert decision.reasons == (
        "domain:ai",
        "domain:data-research",
        "domain:decision-inbox",
        "domain:decision-packet-api",
        "domain:decision-packets",
        "domain:demo-runtime",
        "domain:packet-copilot",
        "domain:packet-monitoring",
        "domain:packet-review",
        "domain:workstation-shell",
        "browser",
    )


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_ai_new_behavior.py",
        "tests/test_research_new_behavior.py",
        "tests/test_workstation_new_behavior.py",
    ],
)
def test_unmapped_test_inside_known_domain_fails_closed(path: str) -> None:
    decision = decide_paths([path])

    assert decision.tier is GateTier.RELEASE
    assert decision.reasons == (f"unknown:{path}",)


@pytest.mark.parametrize(
    "path",
    [
        "src/quantmesh/ai/new_behavior.py",
        "src/quantmesh/research/new_behavior.py",
        "src/quantmesh/api/new_behavior.py",
    ],
)
def test_unmapped_source_inside_known_domain_fails_closed(path: str) -> None:
    decision = decide_paths([path])

    assert decision.tier is GateTier.RELEASE
    assert decision.reasons == (f"unknown:{path}",)


@pytest.mark.parametrize(
    ("path", "domains"),
    [
        ("src/quantmesh/api/app.py", ("workstation-shell",)),
        (
            "src/quantmesh/api/workstation.py",
            (
                "decision-inbox",
                "decision-packet-api",
                "decision-packets",
                "demo-runtime",
                "packet-copilot",
                "packet-monitoring",
                "packet-review",
                "workstation-shell",
            ),
        ),
    ],
)
def test_api_route_change_requires_workstation_e2e(path: str, domains: tuple[str, ...]) -> None:
    decision = decide_paths([path])

    assert decision.tier is GateTier.BROWSER
    assert decision.domains == domains
    assert decision.reasons[-1] == "browser"


def test_reviewed_python_path_maps_to_its_direct_test_target() -> None:
    """Removing a reviewed mapping would leave a small Python change untested in fast mode."""

    decision = decide_paths(["src/quantmesh/ai/gateway.py"])

    assert decision.tier is GateTier.DOMAIN
    assert decision.domains == ("ai",)
    assert decision.pytest_targets == ("tests/test_ai_gateway.py",)


def test_reviewed_frontend_component_path_maps_to_its_vitest_target() -> None:
    """A component change must expose its direct Vitest file to the executor."""

    decision = decide_paths(["frontend/src/screens/Watchlist.tsx"])

    assert decision.tier is GateTier.BROWSER
    assert decision.domains == ("workstation-shell",)
    assert decision.pytest_targets == ("frontend/src/screens/Watchlist.test.tsx",)


def test_generic_browser_e2e_test_adds_e2e_without_frontend_source() -> None:
    decision = decide_paths(["tests/test_new_e2e.py"])

    assert decision.tier is GateTier.BROWSER
    assert decision.domains == ()
    assert decision.frontend is False
    assert decision.reasons == ("browser",)


def test_reviewed_frontend_test_support_path_uses_fast_validation() -> None:
    decision = decide_paths(["frontend/src/test/setup.ts"])

    assert decision.tier is GateTier.FAST
    assert decision.domains == ()
    assert decision.frontend is True
    assert decision.reasons == ("frontend-test-support",)


def test_frontend_support_and_domain_change_uses_domain_without_browser_e2e() -> None:
    decision = decide_paths(["frontend/src/test/setup.ts", "src/quantmesh/ai/gateway.py"])

    assert decision.tier is GateTier.DOMAIN
    assert decision.domains == ("ai",)
    assert decision.frontend is True
    assert decision.reasons == ("domain:ai", "frontend")


@pytest.mark.parametrize(
    "path",
    [
        "src/quantmesh/execution/orders.py",
        "src/quantmesh/risk/approvals.py",
        "src/quantmesh/connectors/broker.py",
        "src/quantmesh/domain/orders.py",
        "src/quantmesh/portfolio/constraints.py",
        "src/quantmesh/live/feed.py",
        "src/quantmesh/ops/secrets.py",
        "src/quantmesh/settings.py",
        "src/quantmesh/_fs.py",
        "src/quantmesh/account/store.py",
        "src/quantmesh/recovery.py",
        "src/quantmesh/hyperliquid/exchange.py",
        "src/quantmesh/moomoo/execution.py",
        "src/quantmesh/kalshi/market_data.py",
        "src/quantmesh/polymarket/market_data.py",
        "src/quantmesh/data/collection.py",
        "src/quantmesh/data/catalog.py",
        "src/quantmesh/data/artifact_manifests.py",
        "src/quantmesh/data/checkpoints.py",
        "src/quantmesh/data/fixtures/source.json",
        "src/quantmesh/ai/redact.py",
        "src/quantmesh/ai/transport.py",
        "src/quantmesh/security/secrets.py",
        "pyproject.toml",
        "requirements-audit.txt",
        ".github/workflows/ci.yml",
        "tools/gate_policy.py",
        "frontend/package.json",
        "tests/test_live_fence.py",
        "tests/test_risk_e2e.py",
        "src/quantmesh/api/security.py",
        "src/quantmesh/api/persistence.py",
        "src/quantmesh/api/order_handoff.py",
        "frontend/src/auth/session.test.ts",
        "frontend/src/security/setup.ts",
        "frontend/src/brokers/mock.test.ts",
        "tests/security/test_new_e2e.py",
        "tests/test_ai_tools.py",
        "tests/test_ai_transport.py",
        "tests/ai/permissions/test_prompt_e2e.py",
        "frontend/src/credentials/form.ts",
        "src/quantmesh/api/database.py",
        "src/quantmesh/api/credentials.py",
        "frontend/npm-shrinkwrap.json",
        "frontend/yarn.lock",
    ],
)
def test_safety_critical_paths_always_escalate_to_full(path: str) -> None:
    decision = decide_paths([path])

    assert decision.tier is GateTier.RELEASE
    assert decision.domains == ()
    assert decision.pytest_targets == ()
    assert decision.reasons == ("safety:" + path.replace("\\", "/"),)


@pytest.mark.parametrize(
    "paths, reason",
    [
        (["notes/unclassified.txt"], "unknown:notes/unclassified.txt"),
        ([], "empty-or-ambiguous-diff"),
        (["C:/outside/repository.py"], "invalid-path:C:/outside/repository.py"),
        (["/tmp/outside.py"], "invalid-path:/tmp/outside.py"),
        (["src/quantmesh/../risk/approvals.py"], "invalid-path:src/quantmesh/../risk/approvals.py"),
        (["src/quantmesh/unmapped_module.py"], "unknown:src/quantmesh/unmapped_module.py"),
        (["tests/test_unmapped_contract.py"], "unknown:tests/test_unmapped_contract.py"),
        (["schemas/new-contract.json"], "unknown:schemas/new-contract.json"),
        (["migrations/0001_new_schema.sql"], "unknown:migrations/0001_new_schema.sql"),
    ],
)
def test_unknown_or_ambiguous_paths_fail_closed(paths: list[str], reason: str) -> None:
    decision = decide_paths(paths)

    assert decision.tier is GateTier.RELEASE
    assert decision.reasons == (reason,)


def test_invalid_paths_are_canonicalized_deduplicated_and_order_independent() -> None:
    first = decide_paths(["/z", "C:\\outside\\repository.py", "/a", "C:/outside/repository.py"])
    second = decide_paths(["C:/outside/repository.py", "/a", "/z", "C:\\outside\\repository.py"])

    assert first == second
    assert first.reasons == (
        "invalid-path:/a",
        "invalid-path:/z",
        "invalid-path:C:/outside/repository.py",
    )


def test_repeated_forward_or_backslash_separators_are_malformed_deterministically() -> None:
    forward = decide_paths(["src//quantmesh//ai//gateway.py"])
    backward = decide_paths([r"src\\quantmesh\\ai\\gateway.py"])

    assert forward.tier is GateTier.RELEASE
    assert backward == forward
    assert forward.reasons == ("invalid-path:src//quantmesh//ai//gateway.py",)


def test_safety_override_precedes_frontend_and_domain_classification() -> None:
    decision = decide_paths(
        [
            "frontend/package.json",
            "src/quantmesh/api/security.py",
            "src/quantmesh/api/persistence.py",
        ]
    )

    assert decision.tier is GateTier.RELEASE
    assert decision.reasons == (
        "safety:frontend/package.json",
        "safety:src/quantmesh/api/persistence.py",
        "safety:src/quantmesh/api/security.py",
    )


def test_watchlist_persistence_source_requires_full() -> None:
    decision = decide_paths(["src/quantmesh/api/watchlist.py"])

    assert decision.tier is GateTier.RELEASE
    assert decision.domains == ()
    assert decision.pytest_targets == ()
    assert decision.reasons == ("safety:src/quantmesh/api/watchlist.py",)


@pytest.mark.parametrize(
    "path",
    [
        "src/quantmesh/ai/decisions.py",
        "src/quantmesh/ai/retrieval.py",
        "src/quantmesh/research/drift.py",
        "src/quantmesh/research/ensemble.py",
        "src/quantmesh/research/reports.py",
    ],
)
def test_reviewed_persisted_format_owner_requires_full(path: str) -> None:
    decision = decide_paths([path])

    assert decision.tier is GateTier.RELEASE
    assert decision.domains == ()
    assert decision.pytest_targets == ()
    assert decision.reasons == (f"safety:{path}",)


def test_safety_sensitive_e2e_test_stays_full() -> None:
    decision = decide_paths(["tests/test_live_e2e.py"])

    assert decision.tier is GateTier.RELEASE
    assert decision.reasons == ("safety:tests/test_live_e2e.py",)


@pytest.mark.parametrize(
    "path",
    [
        "frontend/src/components/Tooltip.tsx",
        "frontend/src/components/Border.tsx",
        "frontend/src/components/Clock.tsx",
    ],
)
def test_non_safety_frontend_words_do_not_trigger_full(path: str) -> None:
    decision = decide_paths([path])

    assert decision.tier is GateTier.BROWSER
    assert decision.domains == ("workstation-shell",)
    assert decision.frontend is True


def test_json_is_compact_and_has_stable_keys_and_values() -> None:
    decision = decide_paths(["src/quantmesh/api/workstation.py"])

    assert decision.to_json() == (
        '{"domains":["decision-inbox","decision-packet-api","decision-packets",'
        '"demo-runtime","packet-copilot","packet-monitoring","packet-review",'
        '"workstation-shell"],"frontend":false,'
        '"pytest_targets":["tests/test_spa_api.py","tests/test_workstation.py"],'
        '"reasons":["domain:decision-inbox","domain:decision-packet-api",'
        '"domain:decision-packets","domain:demo-runtime","domain:packet-copilot",'
        '"domain:packet-monitoring","domain:packet-review",'
        '"domain:workstation-shell","browser"],"tier":"browser"}'
    )
    assert list(json.loads(decision.to_json())) == [
        "domains",
        "frontend",
        "pytest_targets",
        "reasons",
        "tier",
    ]


def test_cli_writes_compact_github_outputs(tmp_path: Path) -> None:
    output = tmp_path / "github-output.txt"
    result = subprocess.run(
        [
            sys.executable,
            "tools/gate_policy.py",
            "decide",
            "--paths",
            "docs/guide.md",
            "--github-output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout == (
        '{"domains":[],"frontend":false,"pytest_targets":[],'
        '"reasons":["docs-only"],"tier":"fast"}\n'
    )
    assert output.read_text(encoding="utf-8").splitlines() == [
        "decision=" + result.stdout.strip(),
        "tier=fast",
        "frontend=false",
        "run_browser=false",
    ]


def test_git_diff_retains_safety_deletion_with_docs_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, base = _committed_repository(tmp_path)
    (repository / "src/quantmesh/risk/guard.py").unlink()
    (repository / "README.md").write_text("docs edit\n", encoding="utf-8")
    _git(repository, "add", "--all")
    _git(repository, "commit", "-m", "delete safety file with docs edit")
    monkeypatch.chdir(repository)

    paths = _diff_paths(base, "HEAD")

    assert paths == ("README.md", "src/quantmesh/risk/guard.py")
    assert decide_paths(paths).tier is GateTier.RELEASE


def test_git_diff_retains_both_safety_rename_endpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, base = _committed_repository(tmp_path)
    _git(repository, "mv", "src/quantmesh/risk/guard.py", "docs/guard.py")
    _git(repository, "commit", "-m", "move safety file into docs")
    monkeypatch.chdir(repository)

    paths = _diff_paths(base, "HEAD")

    assert paths == ("docs/guard.py", "src/quantmesh/risk/guard.py")
    assert decide_paths(paths).tier is GateTier.RELEASE


def test_git_diff_retains_type_changes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repository, base = _committed_repository(tmp_path)
    path = "src/quantmesh/risk/guard.py"
    blob = _git(repository, "hash-object", "-w", "--stdin", input_text="README.md\n")
    _git(repository, "update-index", "--cacheinfo", "120000", blob, path)
    _git(repository, "commit", "-m", "change safety file type")
    monkeypatch.chdir(repository)

    paths = _diff_paths(base, "HEAD")

    assert paths == (path,)
    assert decide_paths(paths).tier is GateTier.RELEASE


@pytest.mark.parametrize("event", ["push", "main", "tag", "workflow_dispatch", "unknown", ""])
def test_non_pr_events_select_release_even_for_docs(event):
    from tools.gate_policy import select_tier

    assert select_tier(["docs/guide.md"], event) == "release"


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (["docs/guide.md"], "fast"),
        (["src/quantmesh/ai/gateway.py"], "domain"),
        (["frontend/src/screens/Watchlist.tsx"], "browser"),
        (["unknown.py"], "release"),
        (["src/quantmesh/research/jobs.py"], "release"),
        (["src/quantmesh/risk/guard.py"], "release"),
        (["frontend/package-lock.json"], "release"),
        ([".github/workflows/ci.yml"], "release"),
    ],
)
def test_select_tier_has_four_public_tiers(paths, expected):
    from tools.gate_policy import select_tier

    assert select_tier(paths, "pull_request") == expected


@pytest.mark.parametrize(
    "paths",
    [
        None,
        "docs/guide.md",
        [None],
        [42],
        ["docs/x\x00.md"],
        ["docs/x\n.md"],
        ["C:guide.md"],
        ["docs/script.py"],
    ],
)
def test_malformed_path_input_cannot_select_fast(paths):
    assert decide_paths(paths).tier is GateTier.RELEASE


def test_mapping_input_cannot_hide_safety_values():
    from tools.gate_policy import select_tier

    paths = {"docs/guide.md": "src/quantmesh/risk/guard.py"}
    assert decide_paths(paths).tier is GateTier.RELEASE
    assert select_tier(paths, "pull_request") == "release"
