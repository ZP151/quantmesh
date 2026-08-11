import json
import math
import os
from pathlib import Path

import pytest

from quantmesh.research.frameworks import FrameworkRunEvidence
from tools.framework_bakeoff.score import (
    DEFAULT_SCORE_WEIGHTS,
    main,
    score_framework,
)

ALL_CHECKS = {
    "license": True,
    "windows_install": True,
    "deterministic": True,
    "chronological_split": True,
    "no_leakage": True,
    "paper_only": True,
    "contract_mapping": True,
}


def evidence(
    *,
    framework: str = "finrl-x",
    deterministic: bool = True,
    checks: dict[str, bool] | None = None,
    score_inputs: dict[str, float] | None = None,
    status: str = "passed",
) -> FrameworkRunEvidence:
    return FrameworkRunEvidence(
        framework=framework,
        revision=(
            "e65d6f0483ead7d2ef4a5fc940cdf960392a25c1"
            if framework == "finrl-x"
            else "27a8e54e7ac3c57d6cbf8891f0283dfbaee97317"
        ),
        status=status,
        deterministic=deterministic,
        input_digest="1" * 64,
        output_digest="2" * 64 if deterministic else None,
        duration_seconds=12.5,
        peak_rss_mb=7.25,
        environment_bytes=123_456,
        checks=ALL_CHECKS if checks is None else checks,
        artifacts={},
        score_inputs={} if score_inputs is None else score_inputs,
        limitations=["source limitation"],
    )


def write_evidence(path: Path, run: FrameworkRunEvidence) -> None:
    path.write_text(run.model_dump_json(), encoding="utf-8")


def test_default_weights_are_the_exact_approved_scorecard() -> None:
    assert dict(DEFAULT_SCORE_WEIGHTS) == {
        "workflow_fit": 25,
        "adapter_cost": 20,
        "maintenance": 15,
        "resource_cost": 15,
        "packaging": 10,
        "observability": 10,
        "migration": 5,
    }


def test_empty_scores_are_zero_filled_and_explicitly_limited() -> None:
    score = score_framework(evidence(score_inputs={}))

    assert score.soft_scores == {name: 0.0 for name in DEFAULT_SCORE_WEIGHTS}
    assert score.total == 0.0
    assert score.missing_inputs == list(DEFAULT_SCORE_WEIGHTS)
    assert score.limitations == [
        "source limitation",
        *[f"missing-score-input:{name}" for name in DEFAULT_SCORE_WEIGHTS],
    ]


def test_partial_scores_use_zero_only_for_the_missing_categories() -> None:
    score = score_framework(evidence(score_inputs={"workflow_fit": 100.0}))

    assert score.soft_scores["workflow_fit"] == 100.0
    assert score.soft_scores["adapter_cost"] == 0.0
    assert score.total == 25.0
    assert score.missing_inputs == list(DEFAULT_SCORE_WEIGHTS)[1:]


def test_complete_scores_use_stable_decimal_rounding() -> None:
    score = score_framework(
        evidence(score_inputs={name: 33.345 for name in DEFAULT_SCORE_WEIGHTS})
    )

    assert score.total == 33.35
    assert score.missing_inputs == []
    assert score.limitations == ["source limitation"]


def test_runtime_admission_requires_every_exact_hard_gate_and_score_80() -> None:
    score = score_framework(
        evidence(score_inputs={name: 80.0 for name in DEFAULT_SCORE_WEIGHTS})
    )

    assert score.total == 80.0
    assert score.runtime_admissible
    assert score.disposition == "adopt-adapter"
    assert list(score.hard_gates) == [
        "license",
        "windows_install",
        "deterministic",
        "chronological_split",
        "no_leakage",
        "paper_only",
        "contract_mapping",
    ]

    failed_license = dict(ALL_CHECKS, license=False)
    assert not score_framework(
        evidence(
            status="failed",
            checks=failed_license,
            score_inputs={name: 100.0 for name in DEFAULT_SCORE_WEIGHTS},
        )
    ).runtime_admissible


def test_deterministic_gate_uses_top_level_evidence_not_the_checks_mapping() -> None:
    run = evidence(
        deterministic=False,
        status="failed",
        checks=dict(ALL_CHECKS, deterministic=True),
        score_inputs={name: 100.0 for name in DEFAULT_SCORE_WEIGHTS},
    )

    score = score_framework(run)

    assert score.hard_gates["deterministic"] is False
    assert score.runtime_admissible is False


@pytest.mark.parametrize("total_input", [79.99, 80.0])
def test_runtime_admission_has_an_inclusive_eighty_boundary(
    total_input: float,
) -> None:
    score = score_framework(
        evidence(
            score_inputs={name: total_input for name in DEFAULT_SCORE_WEIGHTS}
        )
    )

    assert score.runtime_admissible is (total_input == 80.0)


def test_nautilus_isolated_comparator_requires_only_contract_mapping_to_fail() -> None:
    contract_mismatch = dict(ALL_CHECKS, contract_mapping=False)
    score = score_framework(
        evidence(
            framework="nautilus-trader",
            status="failed",
            checks=contract_mismatch,
            score_inputs={name: 100.0 for name in DEFAULT_SCORE_WEIGHTS},
        )
    )

    assert score.runtime_admissible is False
    assert score.disposition == "isolated-comparator"

    failed_install = dict(contract_mismatch, windows_install=False)
    assert (
        score_framework(
            evidence(
                framework="nautilus-trader",
                deterministic=True,
                status="failed",
                checks=failed_install,
                score_inputs={name: 100.0 for name in DEFAULT_SCORE_WEIGHTS},
            )
        ).disposition
        == "reject"
    )


def test_finrl_contract_mismatch_and_failed_install_are_rejected() -> None:
    contract_mismatch = score_framework(
        evidence(
            status="failed",
            checks=dict(ALL_CHECKS, contract_mapping=False),
            score_inputs={name: 100.0 for name in DEFAULT_SCORE_WEIGHTS},
        )
    )
    score = score_framework(
        evidence(
            status="failed",
            deterministic=False,
            checks={name: False for name in ALL_CHECKS},
            score_inputs={},
        )
    )

    assert contract_mismatch.disposition == "reject"
    assert score.disposition == "reject"


@pytest.mark.parametrize("value", [math.nan, math.inf, -0.01, 100.01])
def test_score_framework_rejects_invalid_score_inputs(value: float) -> None:
    payload = evidence(status="failed").model_dump()
    payload["score_inputs"] = {"workflow_fit": value}
    run = FrameworkRunEvidence.model_construct(**payload)

    with pytest.raises(ValueError, match="score input"):
        score_framework(run)


def test_score_framework_rejects_unknown_score_inputs() -> None:
    with pytest.raises(ValueError, match="unknown score input"):
        score_framework(evidence(score_inputs={"popularity": 100.0}))


@pytest.mark.parametrize("value", [math.nan, math.inf, -0.01, 100.01])
def test_score_framework_rejects_invalid_weights(value: float) -> None:
    weights = dict(DEFAULT_SCORE_WEIGHTS)
    weights["workflow_fit"] = value

    with pytest.raises(ValueError, match="weight"):
        score_framework(evidence(), weights=weights)


def test_score_framework_rejects_unknown_or_missing_weights() -> None:
    unknown = dict(DEFAULT_SCORE_WEIGHTS, popularity=1.0)
    missing = dict(DEFAULT_SCORE_WEIGHTS)
    missing.pop("migration")

    with pytest.raises(ValueError, match="unknown weight"):
        score_framework(evidence(), weights=unknown)
    with pytest.raises(ValueError, match="missing weight"):
        score_framework(evidence(), weights=missing)


def test_cli_writes_compact_sorted_atomic_scorecard_from_exact_frameworks(
    tmp_path: Path,
) -> None:
    finrl_path = tmp_path / "finrl.json"
    nautilus_path = tmp_path / "nautilus.json"
    output_path = tmp_path / "scorecard.json"
    write_evidence(
        finrl_path,
        evidence(
            status="failed",
            deterministic=False,
            checks={name: False for name in ALL_CHECKS},
        ),
    )
    write_evidence(
        nautilus_path,
        evidence(
            framework="nautilus-trader",
            status="failed",
            checks=dict(ALL_CHECKS, contract_mapping=False),
        ),
    )

    assert (
        main(
            [
                "--finrl",
                str(finrl_path),
                "--nautilus",
                str(nautilus_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    raw = output_path.read_text(encoding="utf-8")
    payload = json.loads(raw)
    assert raw == json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    assert payload["schema_version"] == 1
    assert [item["framework"] for item in payload["frameworks"]] == [
        "finrl-x",
        "nautilus-trader",
    ]
    assert payload["frameworks"][0]["revision"] == (
        "e65d6f0483ead7d2ef4a5fc940cdf960392a25c1"
    )
    assert payload["frameworks"][0]["evidence"] == {
        "input_digest": "1" * 64,
        "output_digest": None,
        "status": "failed",
    }
    assert payload["frameworks"][1]["resource_facts"] == {
        "duration_seconds": 12.5,
        "environment_bytes": 123_456,
        "peak_rss_mb": 7.25,
    }
    assert payload["frameworks"][1]["disposition"] == "isolated-comparator"
    assert payload["frameworks"][1]["missing_inputs"] == list(
        DEFAULT_SCORE_WEIGHTS
    )


@pytest.mark.parametrize("malformation", ["not json", "{}"])
def test_cli_fails_closed_on_malformed_input_without_replacing_output(
    tmp_path: Path, malformation: str
) -> None:
    finrl_path = tmp_path / "finrl.json"
    nautilus_path = tmp_path / "nautilus.json"
    output_path = tmp_path / "scorecard.json"
    finrl_path.write_text(malformation, encoding="utf-8")
    write_evidence(nautilus_path, evidence(framework="nautilus-trader"))
    output_path.write_text("preserve-me", encoding="utf-8")

    assert (
        main(
            [
                "--finrl",
                str(finrl_path),
                "--nautilus",
                str(nautilus_path),
                "--output",
                str(output_path),
            ]
        )
        == 2
    )
    assert output_path.read_text(encoding="utf-8") == "preserve-me"


def test_cli_rejects_duplicate_and_wrong_framework_inputs(tmp_path: Path) -> None:
    finrl_path = tmp_path / "finrl.json"
    duplicate_path = tmp_path / "duplicate.json"
    output_path = tmp_path / "scorecard.json"
    write_evidence(finrl_path, evidence())
    write_evidence(duplicate_path, evidence())

    args = [
        "--finrl",
        str(finrl_path),
        "--nautilus",
        str(duplicate_path),
        "--output",
        str(output_path),
    ]
    assert main(args) == 2
    assert not output_path.exists()

    write_evidence(finrl_path, evidence(framework="nautilus-trader"))
    write_evidence(duplicate_path, evidence(framework="finrl-x"))
    assert main(args) == 2
    assert not output_path.exists()


@pytest.mark.parametrize("aliased_input", ["finrl", "nautilus"])
def test_cli_prevents_output_aliasing_either_input(
    tmp_path: Path, aliased_input: str
) -> None:
    finrl_path = tmp_path / "finrl.json"
    nautilus_path = tmp_path / "nautilus.json"
    write_evidence(finrl_path, evidence())
    write_evidence(nautilus_path, evidence(framework="nautilus-trader"))
    output_path = finrl_path if aliased_input == "finrl" else nautilus_path
    before = output_path.read_bytes()

    assert (
        main(
            [
                "--finrl",
                str(finrl_path),
                "--nautilus",
                str(nautilus_path),
                "--output",
                str(output_path),
            ]
        )
        == 2
    )
    assert output_path.read_bytes() == before


def test_atomic_replace_failure_preserves_existing_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    finrl_path = tmp_path / "finrl.json"
    nautilus_path = tmp_path / "nautilus.json"
    output_path = tmp_path / "scorecard.json"
    write_evidence(finrl_path, evidence())
    write_evidence(nautilus_path, evidence(framework="nautilus-trader"))
    output_path.write_text("old-scorecard", encoding="utf-8")

    def fail_replace(source: str | Path, destination: str | Path) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)

    assert (
        main(
            [
                "--finrl",
                str(finrl_path),
                "--nautilus",
                str(nautilus_path),
                "--output",
                str(output_path),
            ]
        )
        == 2
    )
    assert output_path.read_text(encoding="utf-8") == "old-scorecard"
    assert list(tmp_path.glob(".framework-scorecard.*.tmp")) == []
