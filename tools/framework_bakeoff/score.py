"""Score committed framework evidence and write the architecture scorecard."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

from quantmesh.research.frameworks import (
    FRAMEWORK_SCORE_INPUT_NAMES,
    FRAMEWORK_SCORE_WEIGHTS,
    FrameworkRunEvidence,
    FrameworkScore,
    calculate_framework_total,
    evaluate_framework_policy,
)

DEFAULT_SCORE_WEIGHTS = FRAMEWORK_SCORE_WEIGHTS
_FINRL_SOURCE_ID = "docs/evidence/0020/finrl-x-run.json"
_NAUTILUS_SOURCE_ID = "docs/evidence/0020/nautilus-run.json"


def _validate_weights(weights: Mapping[str, float]) -> dict[str, float]:
    unknown = set(weights) - set(FRAMEWORK_SCORE_INPUT_NAMES)
    if unknown:
        raise ValueError(f"unknown weight categories: {sorted(unknown)}")
    missing = set(FRAMEWORK_SCORE_INPUT_NAMES) - set(weights)
    if missing:
        raise ValueError(f"missing weight categories: {sorted(missing)}")

    normalized: dict[str, float] = {}
    for name in FRAMEWORK_SCORE_INPUT_NAMES:
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
    if normalized != dict(FRAMEWORK_SCORE_WEIGHTS):
        raise ValueError("weights must equal the exact schema v1 weights")
    return normalized


def _normalize_score_inputs(run: FrameworkRunEvidence) -> tuple[dict[str, float], list[str]]:
    unknown = set(run.score_inputs) - set(FRAMEWORK_SCORE_INPUT_NAMES)
    if unknown:
        raise ValueError(f"unknown score input categories: {sorted(unknown)}")

    normalized: dict[str, float] = {}
    missing: list[str] = []
    for name in FRAMEWORK_SCORE_INPUT_NAMES:
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


def score_framework(
    run: FrameworkRunEvidence,
    weights: Mapping[str, float] = DEFAULT_SCORE_WEIGHTS,
) -> FrameworkScore:
    """Apply the exact scorecard without inferring unavailable soft evidence."""
    _validate_weights(weights)
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
    total = calculate_framework_total(soft_scores)
    runtime_admissible, disposition = evaluate_framework_policy(
        run.framework, hard_gates, total
    )

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


def _read_evidence(path: Path) -> tuple[FrameworkRunEvidence, str]:
    source_bytes = path.read_bytes()
    record_sha256 = hashlib.sha256(source_bytes).hexdigest()
    run = FrameworkRunEvidence.model_validate_json(source_bytes, strict=True)
    return run, record_sha256


def _scorecard_entry(
    run: FrameworkRunEvidence, source_id: str, record_sha256: str
) -> dict[str, object]:
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
        "record_sha256": record_sha256,
        "source_id": source_id,
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

    finrl, finrl_record_sha256 = _read_evidence(finrl_path)
    nautilus, nautilus_record_sha256 = _read_evidence(nautilus_path)
    frameworks = [finrl.framework, nautilus.framework]
    if len(set(frameworks)) != 2:
        raise ValueError("framework evidence inputs must not be duplicates")
    if finrl.framework != "finrl-x":
        raise ValueError("--finrl input must contain finrl-x evidence")
    if nautilus.framework != "nautilus-trader":
        raise ValueError("--nautilus input must contain nautilus-trader evidence")

    payload: dict[str, object] = {
        "frameworks": [
            _scorecard_entry(finrl, _FINRL_SOURCE_ID, finrl_record_sha256),
            _scorecard_entry(
                nautilus, _NAUTILUS_SOURCE_ID, nautilus_record_sha256
            ),
        ],
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
