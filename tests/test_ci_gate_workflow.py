"""Executable contract for tiered GitHub Actions validation gates."""

from pathlib import Path

import yaml

from tools.gate_policy import GateTier, decide_paths

REPO = Path(__file__).resolve().parents[1]


def _load_workflow(name: str) -> dict[str, object]:
    # PyYAML's default 1.1 resolver coerces the GitHub key ``on`` to True.
    # BaseLoader preserves the workflow expression language and scalar values.
    workflow = yaml.load(
        (REPO / ".github" / "workflows" / name).read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    assert isinstance(workflow, dict)
    return workflow


def _steps(job: dict[str, object]) -> dict[str, dict[str, str]]:
    return {
        step["name"]: step for step in job["steps"] if isinstance(step, dict) and "name" in step
    }


def test_ci_exposes_pr_main_tag_and_manual_entry_points() -> None:
    workflow = _load_workflow("ci.yml")

    triggers = workflow["on"]
    assert triggers["pull_request"]["branches"] == ["main"]
    assert triggers["push"]["branches"] == ["main"]
    assert triggers["push"]["tags"] == ["v*"]
    assert "workflow_dispatch" in triggers


def test_classifier_publishes_only_gate_policy_outputs() -> None:
    workflow = _load_workflow("ci.yml")
    classifier = workflow["jobs"]["classify"]

    assert classifier["timeout-minutes"] == "5"
    assert classifier["outputs"] == {
        "decision": "${{ steps.policy.outputs.decision }}",
        "domains": "${{ toJSON(fromJSON(steps.policy.outputs.decision).domains) }}",
        "frontend": "${{ steps.policy.outputs.frontend }}",
        "run_browser": "${{ steps.policy.outputs.run_browser }}",
        "tier": "${{ steps.policy.outputs.tier }}",
    }
    policy = _steps(classifier)["Classify validation impact"]
    assert policy["id"] == "policy"
    assert "tools/gate_policy.py decide" in policy["run"]
    assert '--github-output "$GITHUB_OUTPUT"' in policy["run"]


def test_fast_job_runs_unless_cancelled_and_keeps_frontend_feedback() -> None:
    workflow = _load_workflow("ci.yml")
    fast = workflow["jobs"]["fast"]

    assert fast["needs"] == "classify"
    assert fast["if"] == "${{ !cancelled() }}"
    assert fast["timeout-minutes"] == "10"
    steps = _steps(fast)
    assert steps["Check generated OpenAPI client"]["run"] == "npm run check:api"
    assert steps["Type-check frontend"]["run"] == "npm run typecheck"
    assert steps["Lint frontend"]["run"] == "npm run lint"
    assert steps["Test frontend"]["run"] == "npx vitest run"
    command = steps["Run bounded fast gate"]["run"]
    assert "tools.quality_gate import build_commands, execute_commands" in command
    assert 'build_commands("fast", GateDecision(GateTier.FAST))' in command


def test_domain_and_e2e_jobs_consume_classifier_outputs() -> None:
    workflow = _load_workflow("ci.yml")
    domain = workflow["jobs"]["domain"]
    e2e = workflow["jobs"]["browser"]

    assert domain["needs"] == "classify"
    assert domain["timeout-minutes"] == "30"
    assert domain["strategy"]["matrix"]["domain"] == (
        "${{ fromJSON(needs.classify.outputs.domains) }}"
    )
    assert "needs.classify.outputs.tier == 'domain'" in domain["if"]
    assert "needs.classify.outputs.tier == 'browser'" in domain["if"]
    assert _steps(domain)["Run domain gate"]["run"].endswith("--domain ${{ matrix.domain }}")

    assert e2e["needs"] == "classify"
    assert e2e["if"] == "needs.classify.outputs.run_browser == 'true'"
    assert e2e["timeout-minutes"] == "30"
    assert _steps(e2e)["Run browser E2E gate"]["run"] == ("python tools/quality_gate.py browser")


def test_e2e_only_decision_skips_empty_domain_matrix() -> None:
    workflow = _load_workflow("ci.yml")
    domain = workflow["jobs"]["domain"]
    decision = decide_paths(["tests/test_instrument_workspace_e2e.py"])

    assert decision.tier is GateTier.BROWSER
    assert decision.domains == ()
    assert "needs.classify.outputs.domains != '[]'" in domain["if"]
    assert workflow["jobs"]["browser"]["if"] == ("needs.classify.outputs.run_browser == 'true'")


def test_composite_workstation_change_expands_parallel_subdomain_matrix() -> None:
    workflow = _load_workflow("ci.yml")
    domain = workflow["jobs"]["domain"]
    decision = decide_paths(["src/quantmesh/api/workstation.py"])

    assert decision.tier is GateTier.BROWSER
    assert decision.domains == (
        "decision-inbox",
        "decision-packet-api",
        "decision-packets",
        "demo-runtime",
        "packet-copilot",
        "packet-monitoring",
        "packet-review",
        "workstation-shell",
    )
    assert domain["strategy"]["fail-fast"] == "false"
    assert domain["strategy"]["matrix"]["domain"] == (
        "${{ fromJSON(needs.classify.outputs.domains) }}"
    )
    assert "needs.classify.outputs.domains != '[]'" in domain["if"]


def test_release_job_certifies_escalated_pr_main_tag_and_manual_runs() -> None:
    workflow = _load_workflow("ci.yml")
    full = workflow["jobs"]["release"]

    assert full["needs"] == "classify"
    assert full["timeout-minutes"] == "180"
    condition = full["if"]
    assert "!cancelled()" in condition
    assert "needs.classify.result != 'success'" in condition
    assert "github.event_name != 'pull_request'" in condition
    assert "!contains(fromJSON" in condition
    assert _steps(full)["Certify exact checkout"]["run"] == "python tools/release_gate.py"


def test_concurrency_cancels_only_superseded_pull_request_runs() -> None:
    workflow = _load_workflow("ci.yml")

    concurrency = workflow["concurrency"]
    assert concurrency["group"] == (
        "${{ github.workflow }}-${{ github.event.pull_request.number || github.run_id }}"
    )
    assert concurrency["cancel-in-progress"] == ("${{ github.event_name == 'pull_request' }}")


def test_security_workflow_remains_independent_and_dependency_scoped() -> None:
    security = _load_workflow("security.yml")

    assert "concurrency" not in security
    assert all("needs" not in job for job in security["jobs"].values())
    paths = security["on"]["push"]["paths"]
    assert "pyproject.toml" in paths
    assert "requirements-audit.txt" in paths
    assert "frontend/package-lock.json" in paths
    assert ".github/workflows/security.yml" in paths


def test_required_python_check_aggregates_all_gate_failures():
    workflow = _load_workflow("ci.yml")
    job = workflow["jobs"]["python"]
    assert set(job["needs"]) == {"classify", "fast", "domain", "browser", "release"}
    assert job["if"] == "${{ always() }}"
    import os
    import subprocess
    import sys

    source = _steps(job)["Require successful selected gates"]["run"]
    program = source.split("python - <<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    cases = [
        (
            {
                "classify": "success",
                "fast": "success",
                "domain": "skipped",
                "browser": "skipped",
                "release": "skipped",
            },
            0,
        ),
        (
            {
                "classify": "success",
                "fast": "success",
                "domain": "failure",
                "browser": "success",
                "release": "skipped",
            },
            1,
        ),
        (
            {
                "classify": "failure",
                "fast": "success",
                "domain": "skipped",
                "browser": "skipped",
                "release": "success",
            },
            1,
        ),
        (
            {
                "classify": "success",
                "fast": "success",
                "domain": "skipped",
                "browser": "skipped",
                "release": "cancelled",
            },
            1,
        ),
    ]
    import json

    for results, expected in cases:
        payload = {name: {"result": value} for name, value in results.items()}
        actual = subprocess.run(
            [sys.executable, "-c", program],
            env={**os.environ, "GATE_RESULTS": json.dumps(payload)},
            capture_output=True,
        )
        assert actual.returncode == expected
