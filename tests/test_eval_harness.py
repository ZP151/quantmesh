"""Eval evidence must preserve failures, unknown usage and immutable inputs."""

import ast
import copy
import json
import shutil

import pytest

from tools.eval_harness import core, runner


def row(task_id="a", status="passed", **overrides):
    result = dict(
        case_id=task_id,
        task_id=task_id,
        status=status,
        attempts=1,
        scenario="security",
        difficulty="hard",
        task_type="contract",
        acceptance="must hold",
        fixture_sha256="fixture",
        verifier_sha256="verifier",
        latency_seconds=2.0,
        verifiers_passed=int(status == "passed"),
        verifiers_total=1,
        model_calls=0,
        tool_calls=0,
        tool_errors=0,
        human_interventions=0,
        tokens=None,
        cost_usd=None,
    )
    result.update(overrides)
    return result


def run(rows):
    return dict(
        schema_version="2.0.0",
        taxonomy=sorted(core.CATEGORIES),
        dataset_hash="same",
        verifier_hash="same",
        status="complete",
        source_unchanged_during_run=True,
        verifiers_unchanged_during_run=True,
        catalog_unchanged_during_run=True,
        timeout_seconds_per_case=30,
        results=rows,
    )


def case(node="tests/test_probe.py::test_ok"):
    return dict(
        task_id="probe",
        scenario="happy-path",
        difficulty="easy",
        task_type="workflow-contract",
        nodeid=node,
        source="harness self-test: synthetic arithmetic fixture",
        acceptance="arithmetic holds",
        failure_category="verification",
    )


def catalog(root, cases=None):
    path = root / "catalog.json"
    path.write_text(json.dumps(core.freeze_dataset(root, cases or [case()])), encoding="utf-8")
    return path


@pytest.fixture
def candidate(tmp_path):
    root = tmp_path / "candidate with space"
    (root / "tests").mkdir(parents=True)
    shutil.copytree(runner.HARNESS_ROOT / "src", root / "src")
    (root / "tests/test_probe.py").write_text("def test_ok():\n    assert 2 + 2 == 4\n")
    return root


def test_missing_usage_is_unknown_not_zero():
    metrics = core.aggregate([row(model_calls=None, tool_calls=None, tool_errors=None)])
    for field in (
        "model_calls",
        "tool_calls",
        "tool_error_rate",
        "tokens",
        "cost_usd",
        "observed_model_calls",
        "observed_tool_calls",
    ):
        assert metrics[field] is None
    assert metrics["telemetry_coverage"] == 0
    assert core.aggregate([])["task_success_rate"] is None


def test_metrics_keep_denominators():
    metrics = core.aggregate(
        [
            row(),
            row("b", "failed", model_calls=2, tool_calls=2, tool_errors=1),
            row("c", attempts=2, human_interventions=1),
        ]
    )
    assert metrics["task_success_rate"] == pytest.approx(2 / 3)
    assert metrics["first_pass_success"] == pytest.approx(1 / 3)
    assert metrics["verifier_pass_rate"] == pytest.approx(2 / 3)
    assert metrics["human_intervention_rate"] == pytest.approx(1 / 3)
    assert metrics["tool_error_rate"] == 0.5
    assert metrics["model_calls"] == 2
    assert metrics["tokens"] is None and metrics["cost_usd"] is None


@pytest.mark.parametrize(
    "field",
    ["dataset_hash", "verifier_hash", "taxonomy", "schema_version", "timeout_seconds_per_case"],
)
def test_catalog_change_blocks_comparison(field):
    baseline = run([row()])
    changed = copy.deepcopy(baseline)
    changed[field] = "changed"
    with pytest.raises(ValueError, match="incompatible"):
        core.compare(baseline, changed)


def test_regression_denominator_is_baseline_passes():
    result = core.compare(run([row(), row("b", "failed")]), run([row(status="failed"), row("b")]))
    assert result["regression_rate"] == 1
    assert result["regressions"] == ["a"] and result["improvements"] == ["b"]


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate",
        "acceptance",
        "fixture_sha256",
        "verifier_sha256",
        "source_unchanged_during_run",
    ],
)
def test_comparison_refuses_result_tampering(change):
    baseline = run([row()])
    changed = copy.deepcopy(baseline)
    if change == "missing":
        changed["results"] = []
    elif change == "duplicate":
        changed["results"] *= 2
    elif change == "source_unchanged_during_run":
        changed[change] = False
    else:
        changed["results"][0][change] = "changed"
    with pytest.raises(ValueError):
        core.compare(baseline, changed)


def test_skip_xfail_teardown_failure_and_empty_checks_not_pass():
    assert core.verdict(0, {"reports": []}) == "error"
    assert core.verdict(5, None) == "error"
    for report in [
        dict(when="call", outcome="skipped"),
        dict(when="call", outcome="passed", wasxfail=True),
    ]:
        assert core.verdict(0, {"reports": [report]}) == "skipped"
    assert (
        core.verdict(
            1,
            {
                "reports": [
                    dict(when="call", outcome="passed"),
                    dict(when="teardown", outcome="failed"),
                ]
            },
        )
        == "error"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_id", "../escape"),
        ("task_id", "中文"),
        ("source", ""),
        ("acceptance", ""),
        ("nodeid", "../outside.py::test_x"),
        ("nodeid", "tests/x.py::test_x --override"),
        ("nodeid", "tests//x.py::test_x"),
        ("failure_category", "runtime"),
    ],
)
def test_strict_id_paths_source_acceptance(candidate, field, value):
    document = core.freeze_dataset(candidate, [case()])
    document["cases"][0][field] = value
    path = candidate / "catalog.json"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        core.load_dataset(path, candidate)


def test_fixture_and_verifier_bytes_are_pinned(candidate):
    path = catalog(candidate)
    document = core.load_dataset(path, candidate)
    assert document["version"] == "2.0.0"
    assert document["cases"][0]["fixture_sha256"] and document["cases"][0]["verifier_sha256"]
    (candidate / "tests/test_probe.py").write_text("def test_ok():\n    assert False\n")
    with pytest.raises(ValueError, match="pin"):
        core.load_dataset(path, candidate)


def test_runner_persists_trace_logs_and_refuses_overwrite(candidate):
    output = candidate / "output"
    result = runner.execute(candidate, catalog(candidate), output, timeout=30)
    assert result["status"] == "complete"
    record = result["results"][0]
    assert record["status"] == "passed" and record["case_id"] == "probe"
    for field in ("dataset_hash", "verifier_hash", "run_id"):
        assert record[field] == result[field]
    assert json.loads((output / record["trace"]).read_text())["reports"]
    assert (output / record["raw_log"]).exists() and (output / record["progress_log"]).exists()
    assert record["tokens"] is None and record["cost_usd"] is None
    assert (output / "results.jsonl").read_text().count("\n") == 1
    with pytest.raises(FileExistsError):
        runner.execute(candidate, candidate / "catalog.json", output)


def test_known_bad_fixture_fails(candidate):
    result = runner.execute(
        candidate, catalog(candidate), candidate / "bad", timeout=30, inject_known_bad=True
    )
    assert result["injection"] == "known-bad"
    record = result["results"][0]
    assert record["status"] == "failed" and record["final_result"]["exit_code"] == 1
    trace = json.loads((candidate / "bad" / record["trace"]).read_text())
    assert any(r["outcome"] == "failed" for r in trace["reports"])
    assert result["metrics"]["task_success_rate"] == 0


def test_skip_timeout_not_pass(candidate):
    (candidate / "tests/test_probe.py").write_text(
        "import pytest\ndef test_ok():\n    pytest.skip('synthetic skip')\n"
    )
    skipped = runner.execute(candidate, catalog(candidate), candidate / "skip", timeout=30)
    assert skipped["results"][0]["status"] == "skipped"
    assert skipped["metrics"]["task_success_rate"] == 0
    (candidate / "tests/test_probe.py").write_text(
        "import time\ndef test_ok():\n"
        "    print('partial raw log', flush=True)\n    time.sleep(30)\n"
    )
    timed = runner.execute(candidate, catalog(candidate), candidate / "timeout", timeout=5)
    record = timed["results"][0]
    assert record["status"] == "failed" and record["failure_category"] == "infrastructure"
    assert record["final_result"]["timed_out"]
    assert record["model_calls"] is None and record["tool_calls"] is None
    assert record["verifiers_passed"] == 0
    assert "partial raw log" in (candidate / "timeout" / record["raw_log"]).read_text()


def test_frozen_badcase_imports_candidate_source(candidate):
    directory = candidate / "benchmarks/quantmesh_v2"
    directory.mkdir(parents=True)
    shutil.copyfile(
        runner.HARNESS_ROOT / "benchmarks/quantmesh_v2/test_audit_badcases.py",
        directory / "test_audit_badcases.py",
    )
    origin = candidate / "src/quantmesh/api/workstation.py"
    source = origin.read_text(encoding="utf-8")
    # Intentionally corrupt only the owned candidate. The healthy harness
    # checkout must not mask that corruption by supplying its own imports.
    function = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "_is_loopback"
    )
    lines = source.splitlines(keepends=True)
    lines[function.lineno - 1 : function.end_lineno] = [
        "def _is_loopback(host: str) -> bool:\n    return True\n"
    ]
    origin.write_text("".join(lines), encoding="utf-8")
    probe = case(
        "benchmarks/quantmesh_v2/test_audit_badcases.py::test_disguised_loopback_origin_is_refused"
    )
    result = runner.execute(candidate, catalog(candidate, [probe]), candidate / "cross", timeout=30)
    assert result["results"][0]["status"] == "failed"
    assert result["results"][0]["verifiers_passed"] == 0


def test_model_trace_and_network_block():
    import socket

    from quantmesh.ai.gateway import ModelGateway
    from quantmesh.ai.wire import ModelRequest
    from tools.eval_harness import pytest_plugin as plugin

    class TimeoutTransport:
        def complete(self, body):
            raise TimeoutError("synthetic")

    plugin.EVENTS.clear()
    plugin.pytest_configure(None)
    try:
        with pytest.raises(TimeoutError):
            ModelGateway(TimeoutTransport(), model_name="fixture").complete(
                ModelRequest(messages=[{"role": "user", "content": "fixture"}])
            )
        assert len(plugin.EVENTS) == 1 and plugin.EVENTS[0]["outcome"] == "error"
        assert plugin.EVENTS[0]["transport"] == "TimeoutTransport"
        with socket.socket() as sock, pytest.raises(RuntimeError, match="offline"):
            sock.connect(("example.com", 443))
    finally:
        plugin.pytest_unconfigure(None)


def test_legacy_catalog_is_explicitly_incompatible(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(dict(version="1.0.0", cases=[case()])))
    with pytest.raises(ValueError, match="incompatible"):
        core.load_dataset(path, tmp_path)


def test_bad_injection_cannot_claim_an_improvement():
    baseline = run([row(status="failed")])
    changed = run([row()])
    changed["injection"] = "known-bad"
    with pytest.raises(ValueError, match="incompatible"):
        core.compare(baseline, changed)


@pytest.mark.parametrize(
    "phase,expected", [("call", "failed"), ("setup", "error"), ("teardown", "error")]
)
def test_real_failure_precedes_sibling_xfail(phase, expected):
    evidence = {
        "reports": [
            dict(when=phase, outcome="failed"),
            dict(when="call", outcome="skipped", wasxfail=True),
        ]
    }
    assert core.verdict(1, evidence) == expected


def test_comparison_requires_explicit_completion():
    before, after = run([row(status="failed")]), run([row()])
    del before["status"]
    del after["status"]
    with pytest.raises(ValueError, match="incomplete"):
        core.compare(before, after)


def test_timeout_retains_full_collected_denominator(candidate):
    (candidate / "tests/test_probe.py").write_text(
        "import time\nclass TestMany:\n"
        "    def test_1(self):\n        time.sleep(30)\n"
        "    def test_2(self):\n        assert True\n"
        "    def test_3(self):\n        assert True\n"
    )
    result = runner.execute(
        candidate,
        catalog(candidate, [case("tests/test_probe.py::TestMany")]),
        candidate / "many",
        timeout=5,
    )
    assert result["results"][0]["verifiers_total"] == 3
    assert result["results"][0]["verifiers_passed"] == 0
    assert result["metrics"]["verifier_pass_rate"] == 0


def test_unknown_verifier_denominator_is_unknown():
    metrics = core.aggregate([row(verifiers_total=None, verifiers_passed=None)])
    assert metrics["verifiers_total"] is None
    assert metrics["verifier_pass_rate"] is None


def test_comparison_refuses_unstable_catalog():
    before, after = run([row(status="failed")]), run([row()])
    before["catalog_unchanged_during_run"] = False
    after["catalog_unchanged_during_run"] = False
    with pytest.raises(ValueError, match="drift"):
        core.compare(before, after)


def test_candidate_cannot_supply_unpinned_plugin(candidate):
    package = candidate / "tools/eval_harness"
    package.mkdir(parents=True)
    (candidate / "tools/__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    (package / "pytest_plugin.py").write_text("raise RuntimeError('unpinned candidate plugin')\n")
    result = runner.execute(candidate, catalog(candidate), candidate / "plugin", timeout=30)
    assert result["results"][0]["status"] == "passed"
    trace = json.loads((candidate / "plugin/trace/probe.json").read_text())
    assert trace["imported_plugin"] == str(
        runner.HARNESS_ROOT / "tools/eval_harness/pytest_plugin.py"
    )


def test_freeze_rejects_invalid_cases(candidate):
    for cases in ([dict(case(), acceptance="")], [case(), case()]):
        with pytest.raises(ValueError):
            core.freeze_dataset(candidate, cases)
