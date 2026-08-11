"""Score committed framework evidence and write the architecture scorecard."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from types import MappingProxyType

from quantmesh.research.frameworks import FrameworkRunEvidence, FrameworkScore

_SCORE_CATEGORIES = (
    "workflow_fit",
    "adapter_cost",
    "maintenance",
    "resource_cost",
    "packaging",
    "observability",
    "migration",
)
_HARD_GATES = (
    "license",
    "windows_install",
    "deterministic",
    "chronological_split",
    "no_leakage",
    "paper_only",
    "contract_mapping",
)
_COMPARATOR_GATES = _HARD_GATES[:-1]
_TOTAL_QUANTUM = Decimal("0.01")

DEFAULT_SCORE_WEIGHTS: Mapping[str, float] = MappingProxyType(
    {
        "workflow_fit": 25,
        "adapter_cost": 20,
        "maintenance": 15,
        "resource_cost": 15,
        "packaging": 10,
        "observability": 10,
        "migration": 5,
    }
)


def _validate_weights(weights: Mapping[str, float]) -> dict[str, float]:
    unknown = set(weights) - set(_SCORE_CATEGORIES)
    if unknown:
        raise ValueError(f"unknown weight categories: {sorted(unknown)}")
    missing = set(_SCORE_CATEGORIES) - set(weights)
    if missing:
        raise ValueError(f"missing weight categories: {sorted(missing)}")

    normalized: dict[str, float] = {}
    for name in _SCORE_CATEGORIES:
        value = weights[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 100
        ):
            raise ValueError(f"weight {name!r} must be finite and within 0..100")
        normalized[name] = float(value)
    if not any(normalized.values()):
        raise ValueError("weight total must be positive")
    return normalized


def _normalize_score_inputs(run: FrameworkRunEvidence) -> tuple[dict[str, float], list[str]]:
    unknown = set(run.score_inputs) - set(_SCORE_CATEGORIES)
    if unknown:
        raise ValueError(f"unknown score input categories: {sorted(unknown)}")

    normalized: dict[str, float] = {}
    missing: list[str] = []
    for name in _SCORE_CATEGORIES:
        if name not in run.score_inputs:
            normalized[name] = 0.0
            missing.append(name)
            continue
        value = run.score_inputs[name]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 100
        ):
            raise ValueError(f"score input {name!r} must be finite and within 0..100")
        normalized[name] = float(value)
    return normalized, missing


def _weighted_total(scores: Mapping[str, float], weights: Mapping[str, float]) -> float:
    weighted = sum(
        Decimal(str(scores[name])) * Decimal(str(weights[name]))
        for name in _SCORE_CATEGORIES
    )
    total_weight = sum(Decimal(str(weights[name])) for name in _SCORE_CATEGORIES)
    return float((weighted / total_weight).quantize(_TOTAL_QUANTUM, rounding=ROUND_HALF_UP))


def score_framework(
    run: FrameworkRunEvidence,
    weights: Mapping[str, float] = DEFAULT_SCORE_WEIGHTS,
) -> FrameworkScore:
    """Apply the exact scorecard without inferring unavailable soft evidence."""
    normalized_weights = _validate_weights(weights)
    soft_scores, missing_inputs = _normalize_score_inputs(run)
    hard_gates = {
        "license": run.checks.get("license", False),
        "windows_install": run.checks.get("windows_install", False),
        "deterministic": run.deterministic,
        "chronological_split": run.checks.get("chronological_split", False),
        "no_leakage": run.checks.get("no_leakage", False),
        "paper_only": run.checks.get("paper_only", False),
        "contract_mapping": run.checks.get("contract_mapping", False),
    }
    total = _weighted_total(soft_scores, normalized_weights)
    runtime_admissible = all(hard_gates.values()) and total >= 80
    if runtime_admissible:
        disposition = "adopt-adapter"
    elif (
        run.framework == "nautilus-trader"
        and all(hard_gates[name] for name in _COMPARATOR_GATES)
        and not hard_gates["contract_mapping"]
    ):
        disposition = "isolated-comparator"
    else:
        disposition = "reject"

    limitations = list(run.limitations)
    limitations.extend(f"missing-score-input:{name}" for name in missing_inputs)
    return FrameworkScore(
        framework=run.framework,
        revision=run.revision,
        hard_gates=hard_gates,
        soft_scores=soft_scores,
        total=total,
        runtime_admissible=runtime_admissible,
        disposition=disposition,
        missing_inputs=missing_inputs,
        limitations=limitations,
    )


def _paths_alias(left: Path, right: Path) -> bool:
    if left.resolve(strict=False) == right.resolve(strict=False):
        return True
    if left.exists() and right.exists():
        try:
            return os.path.samefile(left, right)
        except OSError:
            return True
    return False


def _read_evidence(path: Path) -> FrameworkRunEvidence:
    return FrameworkRunEvidence.model_validate_json(path.read_text(encoding="utf-8"))


def _scorecard_entry(run: FrameworkRunEvidence) -> dict[str, object]:
    score = score_framework(run)
    payload = score.model_dump(mode="json")
    payload["resource_facts"] = {
        "duration_seconds": run.duration_seconds,
        "environment_bytes": run.environment_bytes,
        "peak_rss_mb": run.peak_rss_mb,
    }
    payload["evidence"] = {
        "input_digest": run.input_digest,
        "output_digest": run.output_digest,
        "status": run.status,
    }
    return payload


def _write_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=".framework-scorecard.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _generate(finrl_path: Path, nautilus_path: Path, output_path: Path) -> None:
    if _paths_alias(finrl_path, nautilus_path):
        raise ValueError("framework evidence inputs must be distinct files")
    if _paths_alias(output_path, finrl_path) or _paths_alias(output_path, nautilus_path):
        raise ValueError("output must not alias an evidence input")

    finrl = _read_evidence(finrl_path)
    nautilus = _read_evidence(nautilus_path)
    frameworks = [finrl.framework, nautilus.framework]
    if len(set(frameworks)) != 2:
        raise ValueError("framework evidence inputs must not be duplicates")
    if finrl.framework != "finrl-x":
        raise ValueError("--finrl input must contain finrl-x evidence")
    if nautilus.framework != "nautilus-trader":
        raise ValueError("--nautilus input must contain nautilus-trader evidence")

    payload: dict[str, object] = {
        "frameworks": [_scorecard_entry(finrl), _scorecard_entry(nautilus)],
        "schema_version": 1,
    }
    _write_atomic(output_path, payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--finrl", type=Path, required=True)
    parser.add_argument("--nautilus", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        _generate(args.finrl, args.nautilus, args.output)
    except Exception as error:
        print(f"scorecard error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
