import json
import math
from pathlib import Path

import pytest

from quantmesh.data.lake import Lake
from quantmesh.domain.models import Venue
from quantmesh.research.frameworks import FrameworkRunEvidence, FrameworkScore
from tools.framework_bakeoff.fixture import build_nvda_fixture, load_pins

PINS_PATH = Path(__file__).parents[1] / "tools" / "framework_bakeoff" / "pins.json"


def test_nvda_fixture_is_manifest_gated_and_byte_reproducible(tmp_path: Path) -> None:
    left = build_nvda_fixture(tmp_path / "left")
    right = build_nvda_fixture(tmp_path / "right")

    assert left.coverage[0].rows == 420
    assert len(
        Lake(tmp_path / "left").dataset(left.dataset).read_bars(
            interval="1d", venue=Venue.MOOMOO, symbol="NVDA"
        )
    ) == 420
    assert left.source == "quantmesh-deterministic-bakeoff"
    assert left.license == "QuantMesh synthetic test data"
    assert (
        Lake(tmp_path / "left")
        .dataset(left.dataset)
        .read_bars(interval="1d", venue=Venue.MOOMOO, symbol="NVDA")[1]
        .close
        == pytest.approx(120.686628124390651)
    )
    assert left.model_dump(mode="json", exclude={"generated_at"}) == right.model_dump(
        mode="json", exclude={"generated_at"}
    )


def test_framework_evidence_rejects_an_unpinned_or_nondeterministic_pass() -> None:
    with pytest.raises(ValueError, match="passing run requires"):
        FrameworkRunEvidence(
            framework="finrl-x",
            revision="",
            status="passed",
            deterministic=False,
            input_digest="0" * 64,
            output_digest="1" * 64,
            duration_seconds=1.0,
            peak_rss_mb=1.0,
            environment_bytes=1,
            checks={},
            artifacts={},
        )


@pytest.mark.parametrize("value", [math.nan, math.inf, -0.1, 100.1])
def test_framework_evidence_rejects_score_inputs_outside_zero_to_one_hundred(
    value: float,
) -> None:
    with pytest.raises(ValueError, match="score_inputs"):
        FrameworkRunEvidence(
            framework="finrl-x",
            revision="e65d6f0",
            status="failed",
            deterministic=False,
            input_digest="0" * 64,
            duration_seconds=1.0,
            peak_rss_mb=1.0,
            environment_bytes=1,
            checks={},
            artifacts={},
            score_inputs={"fit": value},
        )


def test_framework_score_requires_a_pinned_revision() -> None:
    with pytest.raises(ValueError):
        FrameworkScore(
            framework="finrl-x",
            revision="short",
            hard_gates={},
            soft_scores={},
            total=0.0,
            runtime_admissible=False,
            disposition="reject",
        )


def test_framework_score_rejects_a_total_above_one_hundred() -> None:
    with pytest.raises(ValueError):
        FrameworkScore(
            framework="finrl-x",
            revision="e65d6f0",
            hard_gates={},
            soft_scores={},
            total=100.1,
            runtime_admissible=False,
            disposition="reject",
        )


def test_load_pins_returns_immutable_validated_metadata() -> None:
    pins = load_pins(PINS_PATH)

    assert pins["finrl-x"].revision == "e65d6f0483ead7d2ef4a5fc940cdf960392a25c1"
    assert pins["nautilus-trader"].tag == "v1.231.0"
    with pytest.raises(TypeError):
        pins["other"] = pins["finrl-x"]  # type: ignore[index]
    with pytest.raises(ValueError, match="frozen"):
        pins["finrl-x"].revision = "0" * 40


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("repository", "http://github.com/example/repository.git"),
        ("revision", "E65D6F0483EAD7D2EF4A5FC940CDF960392A25C1"),
        ("license", "   "),
        ("tag", ""),
    ],
)
def test_load_pins_rejects_invalid_repository_metadata(
    tmp_path: Path, field: str, value: str
) -> None:
    payload = {
        "finrl-x": {
            "repository": "https://github.com/example/repository.git",
            "revision": "e65d6f0483ead7d2ef4a5fc940cdf960392a25c1",
            "license": "Apache-2.0",
            "tag": "v1.0.0",
        }
    }
    payload["finrl-x"][field] = value
    path = tmp_path / "pins.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        load_pins(path)


def test_load_pins_rejects_unrecognized_repository_metadata(tmp_path: Path) -> None:
    payload = {
        "finrl-x": {
            "repository": "https://github.com/example/repository.git",
            "revision": "e65d6f0483ead7d2ef4a5fc940cdf960392a25c1",
            "license": "Apache-2.0",
            "unexpected": "not provenance",
        }
    }
    path = tmp_path / "pins.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError):
        load_pins(path)
