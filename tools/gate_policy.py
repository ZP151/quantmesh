"""Fail-closed changed-path policy for QuantMesh validation gates.

The policy is deliberately pure: callers may safely choose a full gate whenever
path classification is absent, malformed, or cannot be mapped conservatively.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import PurePosixPath, PureWindowsPath
from types import MappingProxyType


class GateTier(StrEnum):
    """The strongest validation tier selected by a changed path set."""

    FAST = "fast"
    DOMAIN = "domain"
    BROWSER = "browser"
    RELEASE = "release"


@dataclass(frozen=True, slots=True)
class GateDecision:
    """A stable, serializable validation decision."""

    tier: GateTier
    domains: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    pytest_targets: tuple[str, ...] = ()
    frontend: bool = False

    def to_json(self) -> str:
        """Return compact JSON with lexically stable keys and values."""

        return json.dumps(asdict(self), default=str, sort_keys=True, separators=(",", ":"))


_DOCS_PREFIXES = ("docs/",)
_DOCS_ROOT_FILES = {"README.md", "README.zh-CN.md", "LICENSE", "NOTICE", "CONTRIBUTING.md"}
_FRONTEND_PREFIXES = ("frontend/", "src/quantmesh/api/static/app/")
_SAFETY_PREFIXES = (
    ".github/",
    "tools/",
    "src/quantmesh/account/",
    "src/quantmesh/connectors/",
    "src/quantmesh/data/",
    "src/quantmesh/domain/",
    "src/quantmesh/execution/",
    "src/quantmesh/hyperliquid/",
    "src/quantmesh/instruments/",
    "src/quantmesh/kalshi/",
    "src/quantmesh/live/",
    "src/quantmesh/moomoo/",
    "src/quantmesh/ops/",
    "src/quantmesh/polymarket/",
    "src/quantmesh/portfolio/",
    "src/quantmesh/risk/",
    "src/quantmesh/security/",
)
_SAFETY_EXACT = {
    "pyproject.toml",
    "requirements-audit.txt",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "uv.lock",
    "src/quantmesh/_fs.py",
    "src/quantmesh/settings.py",
    "src/quantmesh/recovery.py",
    # These reviewed modules own durable JSONL record schemas and stores.
    # Keep the paths literal: a similarly named consumer is not necessarily a
    # persistence-format boundary.
    "src/quantmesh/ai/decisions.py",
    "src/quantmesh/ai/retrieval.py",
    "src/quantmesh/api/watchlist.py",
    "src/quantmesh/research/drift.py",
    "src/quantmesh/research/ensemble.py",
    "src/quantmesh/research/reports.py",
}
_SAFETY_AI_FILES = {
    "src/quantmesh/ai/redact.py",
    "src/quantmesh/ai/tools.py",
    "src/quantmesh/ai/transport.py",
}
_SAFETY_RESEARCH_FILES = {
    "src/quantmesh/research/baselines.py",
    "src/quantmesh/research/experiments.py",
    "src/quantmesh/research/features.py",
    "src/quantmesh/research/models.py",
    "src/quantmesh/research/pipelines.py",
}
_SAFETY_TEST_PREFIXES = (
    "tests/fixtures/",
    "tests/schemas/",
)
_SAFETY_COMPONENTS = frozenset(
    {
        "account",
        "auth",
        "broker",
        "brokers",
        "catalog",
        "checkpoint",
        "collection",
        "connector",
        "connectors",
        "credentials",
        "database",
        "execution",
        "fence",
        "fixture",
        "handoff",
        "journal",
        "live",
        "lock",
        "manifest",
        "migration",
        "order",
        "permission",
        "permissions",
        "persistence",
        "reconciliation",
        "recovery",
        "redact",
        "risk",
        "schema",
        "secret",
        "security",
        "store",
        "tool",
        "tools",
        "transport",
        "wallet",
    }
)
_DEPENDENCY_BASENAMES = frozenset(
    {
        "bun.lockb",
        "cargo.lock",
        "cargo.toml",
        "composer.json",
        "composer.lock",
        "gemfile",
        "gemfile.lock",
        "go.mod",
        "go.sum",
        "npm-shrinkwrap.json",
        "package-lock.json",
        "package.json",
        "pipfile",
        "pipfile.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "uv.lock",
        "yarn.lock",
    }
)

# These target sets are deliberately explicit rather than globbed.  The policy
# is reviewed as a safety artifact: adding a domain contract requires a code
# review that can see exactly which existing tests will run.
MANDATORY_SAFETY_TARGETS = (
    "tests/test_live_fence.py",
    "tests/test_enablement.py",
    "tests/test_paper_proposals.py",
    "tests/test_accounting.py",
    "tests/test_matcher.py",
    "tests/test_orders.py",
    "tests/test_store.py",
    "tests/test_account_store.py",
    "tests/test_numeric_policy.py",
    "tests/test_ai_redact.py",
    "tests/test_hyperliquid_wallet_isolation.py",
    "tests/test_security.py",
    "tests/test_ai_decisions.py",
    "tests/test_ai_acceptance.py",
)

DOMAIN_TARGETS = MappingProxyType(
    {
        "workstation-shell": (
            "tests/test_api.py",
            "tests/test_spa_api.py",
            "tests/test_workstation.py",
            "tests/test_instrument_api.py",
            "tests/test_instrument_history.py",
            "tests/test_instrument_workspace_api.py",
            "tests/test_watchlist.py",
        ),
        "decision-inbox": ("tests/test_decision_inbox.py",),
        "decision-packet-api": ("tests/test_decision_packet_api.py",),
        "decision-packets": ("tests/test_decision_packets.py",),
        "packet-copilot": ("tests/test_packet_copilot.py",),
        "packet-monitoring": ("tests/test_packet_monitoring.py",),
        "packet-review": ("tests/test_packet_reviews.py",),
        "demo-runtime": (
            "tests/test_demo.py",
            "tests/test_demo_instrument_workspace.py",
            "tests/test_demo_reset_finalization.py",
            "tests/test_demo_reset_runtime.py",
        ),
        "data-research": (
            "tests/test_research_baselines.py",
            "tests/test_research_drift.py",
            "tests/test_research_ensemble.py",
            "tests/test_research_features.py",
            "tests/test_research_models.py",
            "tests/test_research_pipelines.py",
            "tests/test_research_reports.py",
            "tests/test_price_forecast.py",
            "tests/test_bitemporal_history.py",
            "tests/test_fabric_pipeline.py",
            "tests/test_raw_envelopes.py",
            "tests/test_artifact_manifests.py",
            "tests/test_collection_checkpoints.py",
            "tests/test_collection_identity.py",
            "tests/test_collection_recovery.py",
            "tests/test_data_catalog.py",
            "tests/test_data_catalog_api.py",
            "tests/test_datalink.py",
            "tests/test_equity_adjustments.py",
            "tests/test_events_calibration.py",
            "tests/test_events_forecast.py",
            "tests/test_events_mapping.py",
            "tests/test_events_models.py",
            "tests/test_experiments.py",
            "tests/test_framework_scorecard.py",
            "tests/test_ingestion.py",
            "tests/test_lake.py",
            "tests/test_manifest.py",
            "tests/test_market_calendars.py",
            "tests/test_market_data.py",
            "tests/test_object_store.py",
            "tests/test_provider_capabilities.py",
            "tests/test_providers.py",
            "tests/test_quality_evidence.py",
            "tests/test_quality_policies.py",
            "tests/test_quality_publication.py",
            "tests/test_trusted_instruments.py",
        ),
        "ai": (
            "tests/test_ai_gateway.py",
            "tests/test_ai_retrieval.py",
            "tests/test_ai_roles.py",
            "tests/test_ai_tools.py",
        ),
        "execution-connectors": (
            "tests/test_execution_journal.py",
            "tests/test_hyperliquid_collection.py",
            "tests/test_hyperliquid_exchange.py",
            "tests/test_hyperliquid_provider.py",
            "tests/test_hyperliquid_public_info.py",
            "tests/test_hyperliquid_reconciliation.py",
            "tests/test_hyperliquid_rest.py",
            "tests/test_hyperliquid_risk.py",
            "tests/test_hyperliquid_signal.py",
            "tests/test_hyperliquid_stream.py",
            "tests/test_hyperliquid_wire.py",
            "tests/test_kalshi_market_data.py",
            "tests/test_kalshi_wire.py",
            "tests/test_moomoo_cli.py",
            "tests/test_moomoo_client_market_data.py",
            "tests/test_moomoo_collection.py",
            "tests/test_moomoo_execution.py",
            "tests/test_moomoo_market_data.py",
            "tests/test_moomoo_opend.py",
            "tests/test_moomoo_provider.py",
            "tests/test_moomoo_reconciliation.py",
            "tests/test_polymarket_market_data.py",
            "tests/test_polymarket_wire.py",
            "tests/test_portfolio_constraints.py",
            "tests/test_portfolio_optimizer.py",
            "tests/test_portfolio_reports.py",
            "tests/test_portfolio_scenarios.py",
            "tests/test_reconciliation_engine.py",
            "tests/test_recovery.py",
        ),
    }
)

# Source routing is exact by design. A new source module must either be added
# here with its complete reviewed domain contract or conservatively select full
# validation as an unknown path.
DOMAIN_SOURCE_PATHS = MappingProxyType(
    {
        "workstation-shell": (
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
            "src/quantmesh/demo/runtime.py",
            "src/quantmesh/demo/seeder.py",
        ),
        "decision-inbox": (
            "src/quantmesh/api/workstation.py",
            "src/quantmesh/demo/runtime.py",
            "src/quantmesh/demo/seeder.py",
        ),
        "decision-packet-api": (
            "src/quantmesh/api/workstation.py",
            "src/quantmesh/demo/runtime.py",
            "src/quantmesh/demo/seeder.py",
        ),
        "decision-packets": (
            "src/quantmesh/api/workstation.py",
            "src/quantmesh/demo/runtime.py",
            "src/quantmesh/demo/seeder.py",
        ),
        "packet-copilot": (
            "src/quantmesh/api/workstation.py",
            "src/quantmesh/demo/runtime.py",
            "src/quantmesh/demo/seeder.py",
        ),
        "demo-runtime": (
            "src/quantmesh/api/workstation.py",
            "src/quantmesh/demo/datalink.py",
            "src/quantmesh/demo/generators.py",
            "src/quantmesh/demo/runtime.py",
            "src/quantmesh/demo/seeder.py",
        ),
        "packet-monitoring": (
            "src/quantmesh/api/workstation.py",
            "src/quantmesh/demo/runtime.py",
            "src/quantmesh/demo/seeder.py",
        ),
        "packet-review": (
            "src/quantmesh/api/workstation.py",
            "src/quantmesh/demo/runtime.py",
            "src/quantmesh/demo/seeder.py",
        ),
        "data-research": (
            "src/quantmesh/research/__init__.py",
            "src/quantmesh/research/drift.py",
            "src/quantmesh/research/ensemble.py",
            "src/quantmesh/research/frameworks.py",
            "src/quantmesh/research/reports.py",
        ),
        "ai": (
            "src/quantmesh/ai/__init__.py",
            "src/quantmesh/ai/decisions.py",
            "src/quantmesh/ai/errors.py",
            "src/quantmesh/ai/gateway.py",
            "src/quantmesh/ai/retrieval.py",
            "src/quantmesh/ai/roles.py",
            "src/quantmesh/ai/wire.py",
        ),
        # Execution and connector source changes are safety overrides and
        # intentionally select full rather than a reduced domain decision.
        "execution-connectors": (),
    }
)

_E2E_ROUTE_PATHS = frozenset(
    {
        "src/quantmesh/api/app.py",
        "src/quantmesh/api/workstation.py",
    }
)

# Direct mappings provide the short feedback-loop contract.  They complement
# (never replace) the complete reviewed domain tuples above.
PATH_TEST_TARGETS = MappingProxyType(
    {
        "src/quantmesh/ai/gateway.py": ("tests/test_ai_gateway.py",),
        "src/quantmesh/api/workstation.py": (
            "tests/test_spa_api.py",
            "tests/test_workstation.py",
        ),
        "src/quantmesh/research/reports.py": ("tests/test_research_reports.py",),
        "frontend/src/screens/Watchlist.tsx": ("frontend/src/screens/Watchlist.test.tsx",),
        "frontend/src/screens/Watchlist.test.tsx": ("frontend/src/screens/Watchlist.test.tsx",),
    }
)


def _path_components(path: str) -> frozenset[str]:
    """Return exact lowercase directory, stem, and identifier components."""

    components: set[str] = set()
    for segment in path.split("/"):
        stem = segment.rsplit(".", 1)[0]
        components.add(stem.lower())
        camel_words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", stem)
        components.update(word.lower() for word in re.split(r"[^a-zA-Z0-9]+", camel_words) if word)
    return frozenset(components)


def _canonical_path(value: str) -> str:
    """Normalize separator spellings for stable valid and invalid diagnostics."""

    return value.replace("\\", "/")


def _normalized_path(value: str) -> str | None:
    """Return a safe repository-relative POSIX path, or ``None`` when invalid."""

    if not isinstance(value, str) or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return None
    path = _canonical_path(value)
    if not path or PurePosixPath(path).is_absolute() or PureWindowsPath(value).is_absolute():
        return None
    if re.match(r"^[A-Za-z]:/", path) or any(part in {"", ".", ".."} for part in path.split("/")):
        return None
    return path


def _is_safety_path(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    components = _path_components(path)
    return (
        path in MANDATORY_SAFETY_TARGETS
        or path in _SAFETY_EXACT
        or name in _DEPENDENCY_BASENAMES
        or name == "requirements.txt"
        or name.startswith(("requirements-", "constraints-"))
        and name.endswith(".txt")
        or path in _SAFETY_AI_FILES
        or path in _SAFETY_RESEARCH_FILES
        or path.startswith(_SAFETY_PREFIXES)
        or path.startswith(_SAFETY_TEST_PREFIXES)
        or path.startswith(("src/", "tests/", "frontend/"))
        and bool(components & _SAFETY_COMPONENTS)
    )


def _is_frontend_test_support(path: str) -> bool:
    """Return whether a reviewed frontend-only test/support file can use fast."""

    if not path.startswith("frontend/"):
        return False
    return (
        path.startswith(("frontend/src/test/", "frontend/test/", "frontend/tests/"))
        or path.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
        or PurePosixPath(path).name in {"vitest.setup.ts", "setup.ts", "setup.tsx"}
    )


def _domains_for(path: str) -> set[str]:
    domains = {
        domain for domain, reviewed_paths in DOMAIN_SOURCE_PATHS.items() if path in reviewed_paths
    }
    domains.update(
        domain for domain, reviewed_tests in DOMAIN_TARGETS.items() if path in reviewed_tests
    )
    if path.startswith(_FRONTEND_PREFIXES):
        domains.add("workstation-shell")
    return domains


def decide_paths(paths: Iterable[str]) -> GateDecision:
    """Classify paths using ordered, conservative rules.

    Any uncertain source, test, configuration, schema, fixture, migration, or
    executable path is deliberately left unmapped and selects ``release``.
    """

    if paths is None or isinstance(paths, (str, bytes)):
        return GateDecision(GateTier.RELEASE, reasons=("malformed-path-input",))
    normalized: list[str] = []
    invalid_paths: list[str] = []
    for raw_path in paths:
        path = _normalized_path(raw_path)
        if path is None:
            invalid_paths.append(
                _canonical_path(raw_path) if isinstance(raw_path, str) else "<non-string>"
            )
            continue
        normalized.append(path)

    if invalid_paths:
        return GateDecision(
            GateTier.RELEASE,
            reasons=tuple(f"invalid-path:{path}" for path in sorted(set(invalid_paths))),
        )

    unique_paths = tuple(sorted(set(normalized)))
    if not unique_paths:
        return GateDecision(GateTier.RELEASE, reasons=("empty-or-ambiguous-diff",))

    safety_paths = tuple(path for path in unique_paths if _is_safety_path(path))
    if safety_paths:
        return GateDecision(
            GateTier.RELEASE,
            reasons=tuple(f"safety:{path}" for path in safety_paths),
        )

    domains: set[str] = set()
    frontend_affected = False
    production_frontend_requires_e2e = False
    e2e = False
    fast_frontend_support = False
    pytest_targets: set[str] = set()
    unknown_paths: list[str] = []
    docs_only = True
    for path in unique_paths:
        is_docs = path in _DOCS_ROOT_FILES or (
            path.startswith(_DOCS_PREFIXES)
            and PurePosixPath(path).suffix.lower()
            in {".md", ".rst", ".txt", ".png", ".jpg", ".jpeg", ".svg", ".pdf"}
        )
        docs_only = docs_only and is_docs
        is_fast_frontend_support = _is_frontend_test_support(path)
        is_generic_e2e = path.startswith("tests/") and path.endswith("_e2e.py")
        is_route = path in _E2E_ROUTE_PATHS
        is_frontend = path.startswith(_FRONTEND_PREFIXES)
        frontend_affected = frontend_affected or is_frontend
        production_frontend_requires_e2e = (
            production_frontend_requires_e2e or is_frontend and not is_fast_frontend_support
        )
        fast_frontend_support = fast_frontend_support or is_fast_frontend_support
        e2e = e2e or is_generic_e2e or is_route
        pytest_targets.update(PATH_TEST_TARGETS.get(path, ()))
        path_domains = set() if is_fast_frontend_support else _domains_for(path)
        domains.update(path_domains)
        if not (
            is_docs or is_fast_frontend_support or is_generic_e2e or path_domains or is_frontend
        ):
            unknown_paths.append(path)

    if unknown_paths:
        return GateDecision(
            GateTier.RELEASE,
            reasons=tuple(f"unknown:{path}" for path in unknown_paths),
        )
    if docs_only:
        return GateDecision(GateTier.FAST, reasons=("docs-only",))

    if fast_frontend_support and not domains and not e2e:
        return GateDecision(
            GateTier.FAST,
            reasons=("frontend-test-support",),
            pytest_targets=tuple(sorted(pytest_targets)),
            frontend=True,
        )

    reasons = tuple(f"domain:{domain}" for domain in sorted(domains))
    targets = tuple(sorted(pytest_targets))
    if frontend_affected:
        reasons += ("frontend",)
    if production_frontend_requires_e2e or e2e:
        return GateDecision(
            GateTier.BROWSER,
            domains=tuple(sorted(domains)),
            reasons=reasons + ("browser",),
            pytest_targets=targets,
            frontend=frontend_affected,
        )
    if domains:
        return GateDecision(
            GateTier.DOMAIN,
            domains=tuple(sorted(domains)),
            reasons=reasons,
            pytest_targets=targets,
            frontend=frontend_affected,
        )
    return GateDecision(
        GateTier.FAST,
        reasons=("safe-non-domain-change",),
        pytest_targets=targets,
    )


def select_tier(changed_paths: list[str], event: str) -> str:
    """Return one of four tiers; only PR diffs may reduce release coverage."""
    if event != "pull_request":
        return GateTier.RELEASE.value
    return decide_paths(changed_paths).tier.value


def _diff_paths(base: str, head: str) -> tuple[str, ...] | None:
    try:
        completed = subprocess.run(
            [
                "git",
                "diff",
                "--name-only",
                "--no-renames",
                "-z",
                "--diff-filter=ACDMRT",
                f"{base}...{head}",
            ],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    paths = tuple(
        path.decode("utf-8", errors="surrogateescape")
        for path in completed.stdout.split(b"\0")
        if path
    )
    return paths or None


def _write_github_output(path: str, decision: GateDecision) -> None:
    payload = decision.to_json()
    lines = (
        f"decision={payload}",
        f"tier={decision.tier}",
        f"frontend={str(decision.frontend).lower()}",
        f"run_browser={str(decision.tier is GateTier.BROWSER).lower()}",
    )
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    """Run the path decision CLI."""

    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    decide = subparsers.add_parser("decide", help="classify changed repository paths")
    input_group = decide.add_mutually_exclusive_group()
    input_group.add_argument("--paths", nargs="+", help="explicit repository-relative paths")
    input_group.add_argument("--base", help="git diff base reference")
    decide.add_argument(
        "--event", default="pull_request", help="event context; non-PR runs require release"
    )
    decide.add_argument("--head", help="git diff head reference")
    decide.add_argument("--github-output", help="append GitHub Actions output values to this file")
    args = parser.parse_args(argv)

    if args.command != "decide":  # pragma: no cover - argparse enforces the only command.
        return 2
    if bool(args.base) != bool(args.head):
        parser.error("--base and --head must be provided together")

    if args.paths is not None:
        decision = decide_paths(args.paths)
    elif args.base is not None:
        paths = _diff_paths(args.base, args.head)
        decision = (
            decide_paths(paths)
            if paths is not None
            else GateDecision(GateTier.RELEASE, reasons=("git-diff-unavailable",))
        )
    else:
        decision = decide_paths(line.rstrip("\n") for line in sys.stdin)

    if args.event != "pull_request":
        decision = GateDecision(GateTier.RELEASE, reasons=(f"event:{args.event}",))
    print(decision.to_json())
    if args.github_output:
        _write_github_output(args.github_output, decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
