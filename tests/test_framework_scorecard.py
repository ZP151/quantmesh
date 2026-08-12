import hashlib
import json
import math
import os
from pathlib import Path

import pytest

from quantmesh.research.frameworks import (
    FRAMEWORK_HARD_GATE_NAMES,
    FRAMEWORK_SCORE_INPUT_NAMES,
    FrameworkRunEvidence,
    FrameworkScore,
)
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
REPOSITORY_ROOT = Path(__file__).parents[1]
COMMITTED_EVIDENCE = (
    REPOSITORY_ROOT / "docs" / "evidence" / "0020" / "finrl-x-run.json",
    REPOSITORY_ROOT / "docs" / "evidence" / "0020" / "nautilus-run.json",
)
COMMITTED_SCORECARD = (
    REPOSITORY_ROOT / "docs" / "evidence" / "0020" / "framework-scorecard.json"
)
EVIDENCE_SOURCE_IDS = {
    "finrl-x": "docs/evidence/0020/finrl-x-run.json",
    "nautilus-trader": "docs/evidence/0020/nautilus-run.json",
}
EXPECTED_RECORD_HASHES = {
    "finrl-x": "5d0e26fb14be84d94bd901113ab97fc553243965ca53f34d39cd49f398348aad",
    "nautilus-trader": "36ea1f79108b049bc56954cce690745bcf5ba60d3345cff833c255e089468008",
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


def set_nested(payload: dict[str, object], dotted_path: str, value: object) -> None:
    target = payload
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        nested = target[part]
        assert isinstance(nested, dict)
        target = nested
    target[parts[-1]] = value


def valid_score_payload() -> dict[str, object]:
    return score_framework(
        evidence(score_inputs={name: 80.0 for name in DEFAULT_SCORE_WEIGHTS})
    ).model_dump(mode="json")


@pytest.mark.parametrize(
    ("dotted_path", "invalid_value"),
    [
        pytest.param("unexpected", True, id="unknown-top-level"),
        pytest.param("deterministic", "true", id="coerced-top-level-bool"),
        pytest.param("duration_seconds", "12.5", id="coerced-top-level-float"),
        pytest.param("environment_bytes", 123_456.0, id="coerced-top-level-int"),
        pytest.param("peak_rss_mb", math.inf, id="nonfinite-top-level-float"),
        pytest.param("checks.license", "yes", id="coerced-check-bool"),
        pytest.param("checks.paper_only", 1, id="integer-check-bool"),
        pytest.param("checks.unexpected", True, id="unknown-check"),
        pytest.param("score_inputs.workflow_fit", "80", id="coerced-score-string"),
        pytest.param("score_inputs.workflow_fit", True, id="boolean-score"),
        pytest.param("score_inputs.workflow_fit", math.nan, id="nonfinite-score"),
        pytest.param("score_inputs.popularity", 80.0, id="unknown-score"),
    ],
)
def test_cli_strictly_rejects_malformed_schema_v1_evidence(
    tmp_path: Path, dotted_path: str, invalid_value: object
) -> None:
    finrl_path = tmp_path / "finrl.json"
    nautilus_path = tmp_path / "nautilus.json"
    output_path = tmp_path / "scorecard.json"
    payload = evidence().model_dump(mode="json")
    set_nested(payload, dotted_path, invalid_value)
    raw = json.dumps(payload, separators=(",", ":"), allow_nan=True)
    finrl_path.write_text(raw, encoding="utf-8")
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


def test_framework_evidence_direct_construction_rejects_extra_fields() -> None:
    payload = evidence().model_dump()
    payload["unexpected"] = True

    with pytest.raises(ValueError, match="unexpected"):
        FrameworkRunEvidence.model_validate(payload)


@pytest.mark.parametrize("path", COMMITTED_EVIDENCE, ids=("finrl", "nautilus"))
def test_committed_framework_evidence_revalidates_as_strict_schema_v1(
    path: Path,
) -> None:
    run = FrameworkRunEvidence.model_validate_json(path.read_bytes(), strict=True)

    assert run.schema_version == 1


def test_framework_score_requires_exact_gate_and_score_mapping_shapes() -> None:
    for mapping_name, canonical_names in (
        ("hard_gates", FRAMEWORK_HARD_GATE_NAMES),
        ("soft_scores", FRAMEWORK_SCORE_INPUT_NAMES),
    ):
        missing = valid_score_payload()
        missing_mapping = missing[mapping_name]
        assert isinstance(missing_mapping, dict)
        missing_mapping.pop(canonical_names[-1])
        with pytest.raises(ValueError, match=mapping_name):
            FrameworkScore.model_validate(missing)

        unknown = valid_score_payload()
        unknown_mapping = unknown[mapping_name]
        assert isinstance(unknown_mapping, dict)
        unknown_mapping["unexpected"] = True if mapping_name == "hard_gates" else 1.0
        with pytest.raises(ValueError, match=mapping_name):
            FrameworkScore.model_validate(unknown)


@pytest.mark.parametrize(
    ("dotted_path", "invalid_value"),
    [
        pytest.param("hard_gates.license", "true", id="coerced-hard-gate"),
        pytest.param("hard_gates.paper_only", 1, id="integer-hard-gate"),
        pytest.param("soft_scores.workflow_fit", "80", id="coerced-soft-score"),
        pytest.param("soft_scores.workflow_fit", True, id="boolean-soft-score"),
        pytest.param("soft_scores.workflow_fit", math.nan, id="nonfinite-soft-score"),
        pytest.param("soft_scores.workflow_fit", -0.01, id="negative-soft-score"),
        pytest.param("soft_scores.workflow_fit", 100.01, id="oversized-soft-score"),
    ],
)
def test_framework_score_rejects_non_strict_gate_and_score_values(
    dotted_path: str, invalid_value: object
) -> None:
    payload = valid_score_payload()
    set_nested(payload, dotted_path, invalid_value)

    with pytest.raises(ValueError):
        FrameworkScore.model_validate(payload)


@pytest.mark.parametrize(
    "missing_inputs",
    [
        ["workflow_fit", "workflow_fit"],
        ["adapter_cost", "workflow_fit"],
        ["popularity"],
    ],
    ids=("duplicate", "out-of-order", "unknown"),
)
def test_framework_score_rejects_invalid_missing_input_lists(
    missing_inputs: list[str],
) -> None:
    payload = valid_score_payload()
    payload["missing_inputs"] = missing_inputs

    with pytest.raises(ValueError, match="missing_inputs"):
        FrameworkScore.model_validate(payload)


def test_framework_score_rejects_missing_input_with_nonzero_score() -> None:
    payload = valid_score_payload()
    payload["missing_inputs"] = ["workflow_fit"]

    with pytest.raises(ValueError, match="missing_inputs"):
        FrameworkScore.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("total", 79.99),
        ("runtime_admissible", False),
        ("disposition", "reject"),
    ],
)
def test_framework_score_rejects_policy_contradictions(
    field: str, invalid_value: object
) -> None:
    payload = valid_score_payload()
    payload[field] = invalid_value

    with pytest.raises(ValueError, match=field):
        FrameworkScore.model_validate(payload)


def test_framework_score_strict_json_reload_rejects_tampering() -> None:
    score = score_framework(
        evidence(score_inputs={name: 80.0 for name in DEFAULT_SCORE_WEIGHTS})
    )
    reloaded = FrameworkScore.model_validate_json(score.model_dump_json(), strict=True)
    assert reloaded == score

    tampered = score.model_dump(mode="json")
    tampered["total"] = 99.0
    with pytest.raises(ValueError, match="total"):
        FrameworkScore.model_validate_json(json.dumps(tampered), strict=True)


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
    with pytest.raises(ValueError, match="unknown score_inputs"):
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


def test_score_framework_rejects_noncanonical_schema_v1_weights() -> None:
    changed = dict(DEFAULT_SCORE_WEIGHTS)
    changed["workflow_fit"] = 24.0

    with pytest.raises(ValueError, match="schema v1 weights"):
        score_framework(evidence(), weights=changed)


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
        "record_sha256": hashlib.sha256(finrl_path.read_bytes()).hexdigest(),
        "source_id": EVIDENCE_SOURCE_IDS["finrl-x"],
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
    assert str(tmp_path) not in raw


def test_one_byte_evidence_mutation_changes_record_hash(tmp_path: Path) -> None:
    finrl_path = tmp_path / "finrl.json"
    nautilus_path = tmp_path / "nautilus.json"
    first_output = tmp_path / "first.json"
    second_output = tmp_path / "second.json"
    write_evidence(finrl_path, evidence())
    write_evidence(nautilus_path, evidence(framework="nautilus-trader"))

    first_args = [
        "--finrl",
        str(finrl_path),
        "--nautilus",
        str(nautilus_path),
        "--output",
        str(first_output),
    ]
    assert main(first_args) == 0
    original_hash = hashlib.sha256(finrl_path.read_bytes()).hexdigest()

    finrl_path.write_bytes(finrl_path.read_bytes() + b" ")
    second_args = [*first_args[:-1], str(second_output)]
    assert main(second_args) == 0
    mutated_hash = hashlib.sha256(finrl_path.read_bytes()).hexdigest()

    first_payload = json.loads(first_output.read_text(encoding="utf-8"))
    second_payload = json.loads(second_output.read_text(encoding="utf-8"))
    assert original_hash != mutated_hash
    assert first_payload["frameworks"][0]["evidence"]["record_sha256"] == (
        original_hash
    )
    assert second_payload["frameworks"][0]["evidence"]["record_sha256"] == (
        mutated_hash
    )


def test_committed_scorecard_pins_exact_source_evidence_bytes() -> None:
    payload = json.loads(COMMITTED_SCORECARD.read_text(encoding="utf-8"))

    for entry in payload["frameworks"]:
        framework = entry["framework"]
        assert entry["evidence"]["source_id"] == EVIDENCE_SOURCE_IDS[framework]
        assert entry["evidence"]["record_sha256"] == EXPECTED_RECORD_HASHES[framework]


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
