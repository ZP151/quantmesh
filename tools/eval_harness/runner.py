"""One isolated pytest process per task; frozen tasks, append-only evidence."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from tools import release_gate
from tools.eval_harness.core import aggregate, buckets, digest, harness_hash, load_dataset, verdict

HARNESS_ROOT = Path(__file__).resolve().parents[2]


def write_json(path: Path, value: object):
    # Same-directory replace protects the last complete summary from partial writes.
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def git(repo: Path, *args: str) -> str | None:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=10)
    return (
        result.stdout.decode("utf-8", errors="replace").strip() if result.returncode == 0 else None
    )


def tree_hash(root: Path, paths: tuple[str, ...]) -> str:
    files = {}
    for name in paths:
        directory = root / name
        for path in sorted(directory.rglob("*.py")):
            files[path.relative_to(root).as_posix()] = path.read_bytes().hex()
    return digest(files)


def environment() -> dict:
    packages = {}
    for name in ("pytest", "duckdb", "pydantic", "fastapi", "numpy", "httpx"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": packages,
    }


def verifier_hash(repo: Path) -> str:
    return digest(
        {
            "tests": tree_hash(repo, ("tests",)),
            "harness": tree_hash(HARNESS_ROOT, ("tools/eval_harness", "benchmarks")),
            "pytest_config": (repo / "pyproject.toml").read_text(encoding="utf-8")
            if (repo / "pyproject.toml").exists()
            else None,
            "owned_process_observer": harness_hash(),
        }
    )


@contextmanager
def child_environment(env: dict):
    """The reused observer inherits this environment; restore it even on failure."""
    previous = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(previous)


def summary_markdown(run: dict) -> str:
    def percent(value):
        return "N/A" if value is None else f"{value:.1%}"

    lines = [
        "# QuantMesh offline contract evaluation",
        "",
        f"Dataset: `{run['dataset_version']}` / `{run['dataset_hash']}`",
        f"Code: `{run['code_revision']}`; status: **{run['status']}**",
        "",
        "Scripted model responses; no real-model quality or investment-return claim.",
        "",
        "| Bucket | n | Success | First pass | Verifier pass | p95 seconds |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    summaries = {"all": aggregate(run["results"])}
    for field, groups in buckets(run["results"]).items():
        summaries.update({f"{field}/{key}": value for key, value in groups.items()})
    for name, value in summaries.items():
        latency = value["latency_seconds_p95"]
        lines.append(
            f"| {name} | {value['cases']} | {percent(value['task_success_rate'])} | "
            f"{percent(value['first_pass_success'])} | "
            f"{percent(value['verifier_pass_rate'])} | "
            f"{latency:.3f} |"
            if latency is not None
            else f"| {name} | 0 | N/A |"
        )
    totals = summaries["all"]
    lines += [
        "",
        f"Model calls (scripted): {totals['model_calls']}; "
        f"ToolRegistry calls: {totals['tool_calls']}; "
        f"tool error rate: {percent(totals['tool_error_rate'])} (includes expected refusals).",
        f"Declared human intervention rate: {percent(totals['human_intervention_rate'])}.",
        "Tokens/cost: N/A (scripted transport usage is not real provider usage).",
        "Regression rate: N/A in a single run; use the compare command.",
        "",
        "| Task | Status | Category (observed boundary, not proven root cause) | Acceptance |",
        "|---|---|---|---|",
    ]
    for result in run["results"]:
        criterion = result["acceptance"].replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {result['task_id']} | {result['status']} | "
            f"{result['failure_category'] or '—'} | {criterion} |"
        )
    return "\n".join(lines) + "\n"


def execute(
    repo: Path,
    dataset_path: Path,
    output: Path,
    *,
    timeout: float = 120,
    interventions: tuple[str, ...] = (),
    inject_known_bad: bool = False,
) -> dict:
    repo, output = repo.resolve(), output.resolve()
    dataset = load_dataset(dataset_path, repo)
    ids = {c["task_id"] for c in dataset["cases"]}
    if not set(interventions) <= ids:
        raise ValueError("intervention names unknown task")
    if not isinstance(timeout, (int, float)) or not 0 < timeout < float("inf"):
        raise ValueError("timeout must be positive")
    output.mkdir(parents=True, exist_ok=False)
    (output / "trace").mkdir()
    (output / "scratch").mkdir()
    (output / "logs").mkdir()
    write_json(output / "dataset.json", dataset)
    source_hash = tree_hash(repo, ("src",))
    run = {
        "schema_version": "2.0.0",
        "taxonomy": dataset["taxonomy"],
        "injection": "known-bad" if inject_known_bad else None,
        "run_id": output.name,
        "started_at": datetime.now(UTC).isoformat(),
        "status": "running",
        "dataset_version": dataset["version"],
        "dataset_hash": digest(dataset),
        "code_revision": git(repo, "rev-parse", "HEAD"),
        "source_hash": source_hash,
        "git_status": git(repo, "status", "--porcelain"),
        "dirty_diff_hash": digest(git(repo, "diff", "HEAD")),
        "verifier_hash": verifier_hash(repo),
        "environment": environment(),
        "model_mode": "scripted-only",
        "timeout_seconds_per_case": timeout,
        "results": [],
    }
    write_json(output / "run.json", run)
    env = os.environ.copy()
    env.update(
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        PYTHONIOENCODING="utf-8",
        PYTHONPATH=os.pathsep.join(
            [str(repo / "src"), str(repo), str(HARNESS_ROOT), env.get("PYTHONPATH", "")]
        ),
    )
    # Do not inherit machine-specific pytest flags or accidentally select paid model settings.
    env.pop("PYTEST_ADDOPTS", None)
    for name in list(env):
        if name.startswith("QUANTMESH_"):
            env.pop(name)
    for case in dataset["cases"]:
        task_id = case["task_id"]
        trace_path = output / "trace" / f"{task_id}.json"
        env["QUANTMESH_EVAL_TRACE"] = str(trace_path)
        env["QUANTMESH_EVAL_REPO"] = str(repo)
        file_name, *selector = case["nodeid"].split("::")
        # Both desired audit assertions and existing verifiers use candidate bytes.
        node_root = repo
        path = (node_root / file_name).resolve()
        if not path.is_relative_to(node_root):
            raise ValueError("verifier symlink escapes repository")
        node = "::".join([str(path), *selector])
        command = [
            sys.executable,
            "-c",
            "import importlib.util,sys; "
            "spec=importlib.util.spec_from_file_location('quantmesh_eval_pinned_plugin',"
            "sys.argv.pop(1)); plugin=importlib.util.module_from_spec(spec); "
            "sys.modules[spec.name]=plugin; spec.loader.exec_module(plugin); "
            "import pytest; raise SystemExit(pytest.main(sys.argv[1:],plugins=[plugin]))",
            str(HARNESS_ROOT / "tools/eval_harness/pytest_plugin.py"),
            "-q",
            "--tb=short",
            "-s",
            "--durations=5",
            "-p",
            "pytest_asyncio.plugin",
            "-o",
            "addopts=",
            "--rootdir",
            str(repo),
            "-o",
            f'pythonpath="{(repo / "src").as_posix()}" "{repo.as_posix()}"',
            "--basetemp",
            str(output / "scratch" / task_id),
            node,
        ]
        env["QUANTMESH_EVAL_INJECT_BAD"] = "1" if inject_known_bad else "0"
        log_dir = output / "logs" / task_id
        log_dir.mkdir()
        with child_environment(env):
            _, duration = release_gate.run_step(
                task_id, command, repo, log_dir, timeout=timeout, progress_interval_seconds=15
            )
        event = json.loads((log_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()[-1])
        exit_code, timed_out = event["exit_code"], event["timed_out"]
        try:
            evidence = json.loads(trace_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            evidence = None
        status = "failed" if timed_out else verdict(exit_code, evidence)
        telemetry_complete = (
            evidence is not None
            and not evidence.get("incomplete")
            and not timed_out
            and evidence.get("exit_code") == exit_code
        )
        reports = evidence["reports"] if evidence else []
        events = evidence["events"] if evidence else []
        # Include setup skips/errors in verifier denominator, once per collected item.
        collected = evidence.get("collected_nodeids") if evidence else None
        nodeids = set(collected) if isinstance(collected, list) else {r["nodeid"] for r in reports}
        passed = sum(
            any(
                r["when"] == "call" and r["outcome"] == "passed" and not r.get("wasxfail")
                for r in reports
                if r["nodeid"] == nodeid
            )
            and not any(r["outcome"] != "passed" for r in reports if r["nodeid"] == nodeid)
            for nodeid in nodeids
        )
        if timed_out or status == "error":
            passed = 0
        if evidence is None or timed_out:
            write_json(
                trace_path,
                {
                    "reports": reports,
                    "events": events,
                    "incomplete": True,
                    "reason": "timeout" if timed_out else "missing plugin evidence",
                    "collected_nodeids": collected,
                },
            )
        category = (
            None
            if status == "passed"
            else "infrastructure"
            if status == "error" or timed_out
            else "verification"
            if status == "skipped"
            else case["failure_category"]
        )
        result = {
            **case,
            "run_id": run["run_id"],
            "dataset_hash": run["dataset_hash"],
            "verifier_hash": run["verifier_hash"],
            "dataset_version": dataset["version"],
            "code_revision": run["code_revision"],
            "status": status,
            "attempts": 1,
            "failure_category": category,
            "failure_attribution": "observed acceptance boundary",
            "final_result": {"status": status, "exit_code": exit_code, "timed_out": timed_out},
            "trace": f"trace/{task_id}.json",
            "raw_log": Path(event["log_path"]).relative_to(output).as_posix(),
            "progress_log": f"logs/{task_id}/events.jsonl",
            "command": command,
            "latency_seconds": duration,
            "verifiers_passed": passed if isinstance(collected, list) else None,
            "verifiers_total": len(collected) if isinstance(collected, list) else None,
            "model_calls": sum(e["kind"] == "model" for e in events)
            if telemetry_complete
            else None,
            "tool_calls": sum(e["kind"] == "tool" for e in events) if telemetry_complete else None,
            "tool_errors": (
                sum(e["kind"] == "tool" and e["outcome"] == "error" for e in events)
                if telemetry_complete
                else None
            ),
            "telemetry_complete": telemetry_complete,
            "human_interventions": interventions.count(task_id),
            "tokens": None,
            "cost_usd": None,
            "usage_unavailable_reason": "scripted fixtures; no real provider usage",
        }
        run["results"].append(result)
        with (output / "results.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(result, ensure_ascii=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        write_json(output / "run.json", run)
        print(f"{task_id}: {status} ({duration:.2f}s)", flush=True)
    run["status"] = "complete"
    run["finished_at"] = datetime.now(UTC).isoformat()
    run["source_unchanged_during_run"] = source_hash == tree_hash(repo, ("src",))
    run["verifiers_unchanged_during_run"] = run["verifier_hash"] == verifier_hash(repo)
    try:
        run["catalog_unchanged_during_run"] = load_dataset(dataset_path, repo) == dataset
    except (ValueError, OSError):
        run["catalog_unchanged_during_run"] = False
    if not all(
        run[f]
        for f in (
            "source_unchanged_during_run",
            "verifiers_unchanged_during_run",
            "catalog_unchanged_during_run",
        )
    ):
        run["status"] = "invalid-input-changed"
    run["metrics"] = aggregate(run["results"])
    run["buckets"] = buckets(run["results"])
    write_json(output / "run.json", run)
    (output / "summary.md").write_text(summary_markdown(run), encoding="utf-8")
    return run
