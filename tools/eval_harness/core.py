"""Small, dependency-free scoring and immutable dataset contract."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath

CATEGORIES = {"specification", "data", "tool", "model", "verification", "infrastructure", "policy"}
ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = {
    "happy-path",
    "boundary",
    "recovery",
    "security",
    "high-complexity",
    "historical-regression",
}


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def safe_path(root: Path, name: str) -> Path:
    """Validate canonical repository-relative paths before reading any bytes."""
    parts = PurePosixPath(name).parts
    if (
        not parts
        or PurePosixPath(name).as_posix() != name
        or any(p in {".", ".."} for p in parts)
        or not re.fullmatch(r"[A-Za-z0-9_./-]+", name)
        or PurePosixPath(name).is_absolute()
    ):
        raise ValueError("unsafe pinned path")
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("pinned symlink escapes repository")
    return path


def byte_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def harness_hash() -> str:
    return digest(
        {
            p.relative_to(ROOT).as_posix(): byte_hash(p)
            for p in [
                *sorted((ROOT / "tools/eval_harness").glob("*.py")),
                ROOT / "tools/release_gate.py",
            ]
        }
    )


def freeze_dataset(repo: Path, cases: list[dict]) -> dict:
    """Pin existing pytest/fixture bytes; freezing never executes a workflow."""
    files = {}
    for folder in ("tests", "benchmarks/quantmesh_v2", "src/quantmesh/data/providers/fixtures"):
        for path in sorted((repo / folder).rglob("*")):
            if path.is_file() and path.suffix in {".py", ".json"}:
                if path.name in {"test_eval_harness.py", "dataset.json", "legacy-catalog.json"}:
                    continue
                name = path.relative_to(repo).as_posix()
                files[name] = byte_hash(safe_path(repo, name))
    verifiers = dict(files)
    if (repo / "pyproject.toml").exists():
        verifiers["pyproject.toml"] = byte_hash(repo / "pyproject.toml")
    document = dict(
        version="2.0.0",
        taxonomy=sorted(CATEGORIES),
        fixture_files=files,
        verifier_files=verifiers,
        harness_sha256=harness_hash(),
        cases=[],
    )
    for case in cases:
        node_file = case["nodeid"].split("::")[0]
        item = dict(
            case,
            case_id=case["task_id"],
            source_ref=node_file,
            source_sha256=byte_hash(safe_path(repo, node_file)),
            expected_boundary_result="acceptance assertions pass",
        )
        item["fixture_sha256"] = digest(
            {"files": files, "nodeid": item["nodeid"], "acceptance": item["acceptance"]}
        )
        item["verifier_sha256"] = digest(
            {"files": verifiers, "nodeid": item["nodeid"], "harness": document["harness_sha256"]}
        )
        document["cases"].append(item)
    return validate_dataset(document, repo)


def load_dataset(path: Path, repo: Path = ROOT) -> dict:
    document = json.loads(path.read_text(encoding="utf-8"))
    return validate_dataset(document, repo)


def validate_dataset(document: dict, repo: Path) -> dict:
    if not isinstance(document, dict) or document.get("version") != "2.0.0":
        raise ValueError("incompatible legacy catalog: requires frozen 2.0.0")
    if document.get("taxonomy") != sorted(CATEGORIES):
        raise ValueError("incompatible taxonomy")
    if set(document) != {
        "version",
        "taxonomy",
        "fixture_files",
        "verifier_files",
        "harness_sha256",
        "cases",
    }:
        raise ValueError("unexpected catalog fields")
    for field in ("fixture_files", "verifier_files"):
        pins = document[field]
        if not isinstance(pins, dict) or not pins:
            raise ValueError("missing byte pins")
        for name, expected in pins.items():
            if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
                raise ValueError("invalid byte pin")
            if byte_hash(safe_path(repo, name)) != expected:
                raise ValueError(f"byte pin mismatch: {name}")
    if document["harness_sha256"] != harness_hash():
        raise ValueError("harness byte pin mismatch")
    cases = document.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("dataset requires cases")
    ids = set()
    for case in cases:
        fields = (
            "task_id",
            "scenario",
            "difficulty",
            "task_type",
            "nodeid",
            "source",
            "acceptance",
            "failure_category",
            "case_id",
            "source_ref",
            "source_sha256",
            "fixture_sha256",
            "verifier_sha256",
            "expected_boundary_result",
        )
        if not isinstance(case, dict) or set(case) != set(fields):
            raise ValueError("unexpected case fields")
        for field in fields:
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ValueError(f"missing case field: {field}")
        if case["task_id"] in ids:
            raise ValueError("duplicate task_id")
        ids.add(case["task_id"])
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", case["task_id"]):
            raise ValueError("unsafe task_id")
        if case["case_id"] != case["task_id"]:
            raise ValueError("case/task ID mismatch")
        node = case["nodeid"].split("::")[0]
        safe_path(repo, node)
        parts = PurePosixPath(node).parts
        if (
            not parts
            or parts[0] not in {"tests", "benchmarks"}
            or ".." in parts
            or "\\" in node
            or ":" in node
            or not node.endswith(".py")
            or "::" not in case["nodeid"]
        ):
            raise ValueError("unsafe nodeid")
        if not all(
            re.fullmatch(r"(?:Test\w+|test_\w+)(?:\[[A-Za-z0-9_,.=-]+\])?", part)
            for part in case["nodeid"].split("::")[1:]
        ):
            raise ValueError("unsafe node selector")
        if (
            case["source_ref"] != node
            or document["verifier_files"].get(node) != case["source_sha256"]
        ):
            raise ValueError("source pin mismatch")
        fixture = digest(
            {
                "files": document["fixture_files"],
                "nodeid": case["nodeid"],
                "acceptance": case["acceptance"],
            }
        )
        verifier = digest(
            {
                "files": document["verifier_files"],
                "nodeid": case["nodeid"],
                "harness": document["harness_sha256"],
            }
        )
        if case["fixture_sha256"] != fixture or case["verifier_sha256"] != verifier:
            raise ValueError("case byte pin mismatch")
        if case["failure_category"] not in CATEGORIES:
            raise ValueError("unknown failure category")
        if case["difficulty"] not in {"easy", "medium", "hard"}:
            raise ValueError("unknown difficulty")
        if case["scenario"] not in SCENARIOS:
            raise ValueError("unknown scenario")
    return document


def verdict(exit_code: int, evidence: dict | None) -> str:
    if evidence is None or evidence.get("incomplete"):
        return "error"
    reports = evidence.get("reports", [])
    if any(r["outcome"] == "failed" and r["when"] != "call" for r in reports):
        return "error"
    calls = [r for r in reports if r["when"] == "call"]
    if any(r["outcome"] == "failed" for r in calls):
        return "failed"
    if any(r.get("wasxfail") for r in reports):
        return "skipped"
    if any(r["outcome"] == "skipped" for r in reports):
        return "skipped"
    return "passed" if exit_code == 0 and calls else "error"


def ratio(n: int, d: int) -> float | None:
    return n / d if d else None


def aggregate(rows: list[dict]) -> dict:
    count = len(rows)
    success = sum(r["status"] == "passed" for r in rows)
    latencies = sorted(r["latency_seconds"] for r in rows)

    def measured_total(field):
        return (
            sum(r[field] for r in rows)
            if rows and all(r[field] is not None for r in rows)
            else None
        )

    def observed_total(field):
        values = [r[field] for r in rows if r[field] is not None]
        return sum(values) if values else None

    tools, errors = measured_total("tool_calls"), measured_total("tool_errors")
    checks, passed_checks = measured_total("verifiers_total"), measured_total("verifiers_passed")
    return {
        "cases": count,
        "passed": success,
        "task_success_rate": ratio(success, count),
        "first_pass_success": ratio(
            sum(r["status"] == "passed" and r["attempts"] == 1 for r in rows), count
        ),
        "verifier_pass_rate": ratio(passed_checks, checks)
        if checks is not None and passed_checks is not None
        else None,
        "verifiers_passed": passed_checks,
        "verifiers_total": checks,
        "human_intervention_rate": ratio(sum(r["human_interventions"] > 0 for r in rows), count),
        "tool_error_rate": ratio(errors, tools)
        if tools is not None and errors is not None
        else None,
        "tool_errors": errors,
        "tool_calls": tools,
        "model_calls": measured_total("model_calls"),
        "telemetry_coverage": ratio(
            sum(
                all(r[f] is not None for f in ("model_calls", "tool_calls", "tool_errors"))
                for r in rows
            ),
            count,
        ),
        "observed_model_calls": observed_total("model_calls"),
        "observed_tool_calls": observed_total("tool_calls"),
        "latency_seconds_total": sum(latencies),
        "latency_seconds_p50": latencies[math.ceil(count * 0.5) - 1] if count else None,
        "latency_seconds_p95": latencies[math.ceil(count * 0.95) - 1] if count else None,
        "tokens": (
            sum(r["tokens"] for r in rows)
            if rows and all(r["tokens"] is not None for r in rows)
            else None
        ),
        "cost_usd": (
            sum(r["cost_usd"] for r in rows)
            if rows and all(r["cost_usd"] is not None for r in rows)
            else None
        ),
    }


def buckets(rows: list[dict]) -> dict:
    return {
        field: {
            key: aggregate([r for r in rows if r[field] == key])
            for key in sorted({r[field] for r in rows})
        }
        for field in ("scenario", "difficulty", "task_type")
    }


def compare(baseline: dict, candidate: dict) -> dict:
    for run in (baseline, candidate):
        if run.get("schema_version") != "2.0.0" or run.get("taxonomy") != sorted(CATEGORIES):
            raise ValueError("incompatible schema/taxonomy; legacy runs cannot be relabelled")
        if run.get("injection") is not None:
            raise ValueError("incompatible known-bad injection cannot score improvement")
        if not all(
            run.get(f) is True
            for f in (
                "source_unchanged_during_run",
                "verifiers_unchanged_during_run",
                "catalog_unchanged_during_run",
            )
        ):
            raise ValueError("input drift cannot be compared")
    if baseline.get("timeout_seconds_per_case") != candidate.get("timeout_seconds_per_case"):
        raise ValueError("incompatible timeout budget")
    for field in ("dataset_hash", "verifier_hash"):
        if baseline[field] != candidate[field]:
            raise ValueError(f"incompatible {field}: freeze benchmark and verifiers")
    if any(r.get("status") != "complete" for r in (baseline, candidate)):
        raise ValueError("incomplete run cannot be compared")

    def index(run):
        result = {r["task_id"]: r for r in run["results"]}
        if len(result) != len(run["results"]):
            raise ValueError("duplicate task IDs in results")
        return result

    old, new = index(baseline), index(candidate)
    if old.keys() != new.keys():
        raise ValueError("missing or added cases: exact task set required")
    for key in old:
        for field in (
            "case_id",
            "acceptance",
            "fixture_sha256",
            "verifier_sha256",
            "scenario",
            "difficulty",
            "task_type",
        ):
            if not old[key].get(field) or old[key][field] != new[key].get(field):
                raise ValueError(f"incompatible per-case {field}")
    regressions = sorted(
        k for k in old if old[k]["status"] == "passed" and new[k]["status"] != "passed"
    )
    improvements = sorted(
        k for k in old if old[k]["status"] != "passed" and new[k]["status"] == "passed"
    )
    groups = {}
    for field in ("scenario", "difficulty", "task_type"):
        groups[field] = {}
        for key in sorted({r[field] for r in old.values()}):
            before = [r for r in old.values() if r[field] == key]
            after = [new[r["task_id"]] for r in before]
            groups[field][key] = {
                "baseline": aggregate(before),
                "candidate": aggregate(after),
                "regression_rate": ratio(
                    sum(r["task_id"] in regressions for r in before),
                    sum(r["status"] == "passed" for r in before),
                ),
            }
    return {
        "regression_rate": ratio(
            len(regressions), sum(r["status"] == "passed" for r in old.values())
        ),
        "regressions": regressions,
        "improvements": improvements,
        "baseline": aggregate(list(old.values())),
        "candidate": aggregate(list(new.values())),
        "buckets": groups,
        "environment_equal": baseline.get("environment") == candidate.get("environment"),
    }
