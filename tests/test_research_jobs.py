"""Offline admission contract; these bytes are fixtures, never market evidence."""

import hashlib
import json

import pytest
from pydantic import ValidationError

from quantmesh.research.jobs import ResearchJobRequest, canonical_request_digest
from quantmesh.research.strategy_registry import get_strategy, pin_fixture_dataset
from tests.research_fixtures import pinned_lake


def request_for(root, **updates):
    ref = pin_fixture_dataset(root, "equities")
    data = dict(
        strategy_id="momentum",
        strategy_version="1",
        dataset=ref.model_dump(),
        interval="1h",
        universe=[{"venue": "moomoo", "symbol": "AAA"}],
        parameters={},
        costs={"fee_bps": 1, "half_spread_bps": 2, "slippage_bps": 3},
        window_spec={"train_bars": 10, "test_bars": 5, "step_bars": 5},
    )
    data.update(updates)
    return ResearchJobRequest.model_validate(data)


@pytest.fixture
def lake(tmp_path):
    root = tmp_path / "lake"
    pinned_lake(root)
    return root


@pytest.mark.parametrize(
    "updates",
    [
        {"strategy_id": "python"},
        {"strategy_version": "2"},
        {"interval": "1s"},
        {"universe": []},
        {"universe": [{"venue": "moomoo", "symbol": "../secret"}]},
        {"universe": [{"venue": "moomoo", "symbol": "AAA", "order": "buy"}]},
        {"parameters": {"x": float("nan")}},
        {"parameters": {"shell": "echo secret"}},
        {"costs": {"fee_bps": -1, "half_spread_bps": 1, "slippage_bps": 1}},
        {"costs": {"fee_bps": 0, "half_spread_bps": 0, "slippage_bps": 0}},
        {"costs": {"fee_bps": 1, "half_spread_bps": 1, "slippage_bps": 1, "order": "buy"}},
        {"window_spec": {"train_bars": 10, "test_bars": 5, "step_bars": 4}},
        {"budget": {"cpu_limit": float("inf")}},
        {"order": "buy"},
    ],
)
def test_request_and_registry_reject_unsafe_inputs(lake, updates):
    with pytest.raises((ValueError, ValidationError)):
        request_for(lake, **updates)


def test_registry_defaults_and_canonical_digest(lake):
    for name in ("momentum", "mean_reversion", "risk_parity"):
        spec = get_strategy(name, "1")
        assert len(spec.implementation_digest) == 64
        assert spec.parameters_schema["additionalProperties"] is False
    with pytest.raises(ValueError):
        get_strategy("lightgbm", "1")
    req = request_for(lake)
    assert req.budget.model_dump() == dict(
        timeout_seconds=900,
        memory_mib=2048,
        cpu_limit=1.0,
        max_model_calls=12,
        max_estimated_model_usd=1.0,
    )
    raw = json.dumps(
        req.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()
    assert canonical_request_digest(req) == hashlib.sha256(raw).hexdigest()
    assert canonical_request_digest(
        ResearchJobRequest.model_validate_json(req.model_dump_json())
    ) == canonical_request_digest(req)


def test_all_public_contracts_reject_extra_fields(lake):
    from quantmesh.research import jobs

    models = (
        jobs.StrategySpec,
        jobs.DatasetRef,
        jobs.RunBudget,
        jobs.ResearchJobRequest,
        jobs.JobRecord,
        jobs.ArtifactRef,
        jobs.AnalysisRecord,
        jobs.AnalysisLease,
    )
    for model in models:
        assert model.model_json_schema()["additionalProperties"] is False
    req = request_for(lake)
    assert canonical_request_digest(req) != canonical_request_digest(
        request_for(lake, strategy_id="risk_parity")
    )
    # A constructed object must not bypass validated hashing.
    unsafe = req.model_copy(update={"parameters": {"x": float("inf")}})
    with pytest.raises(ValueError):
        canonical_request_digest(unsafe)


def test_analysis_failure_before_model_has_no_fabricated_metadata():
    from quantmesh.research.jobs import AnalysisRecord

    record = AnalysisRecord(
        job_id="job",
        report_digest="a" * 64,
        state="unavailable",
        verdict="unavailable",
        error_code="model_unavailable",
    )
    assert record.provider is None and record.model is None
    assert record.prompt_digest is None and record.output_digest is None
    assert record.output_artifact is None
    assert record.usage.model_calls is None and record.usage.estimated_model_usd is None


@pytest.mark.parametrize(
    "updates",
    [
        {},
        {"error_code": "analysis_failed"},
        {"output_digest": None},
        {"citations": []},
        {"output_artifact": None},
    ],
)
def test_successful_analysis_requires_generated_metadata_and_citations(updates):
    from quantmesh.research.jobs import AnalysisRecord, ArtifactRef

    valid = dict(
        job_id="job",
        report_digest="a" * 64,
        state="succeeded",
        provider="offline",
        model="scripted-fixture",
        prompt_digest="b" * 64,
        output_digest="c" * 64,
        verdict="inconclusive",
        citations=[
            ArtifactRef(
                artifact_id="a" * 64,
                kind="report",
                sha256="a" * 64,
                byte_size=1,
                object_key="job/" + "a" * 64 + ".json",
            )
        ],
        output_artifact=ArtifactRef(
            artifact_id="c" * 64,
            kind="analysis",
            sha256="c" * 64,
            byte_size=1,
            object_key="job/" + "c" * 64 + ".json",
        ),
    )
    if not updates:
        valid = dict(
            job_id="job", report_digest="a" * 64, state="succeeded", verdict="inconclusive"
        )
    valid.update(updates)
    with pytest.raises(ValueError):
        AnalysisRecord(**valid)


def test_fixture_pin_rejects_paths_before_read(tmp_path, monkeypatch):
    from pathlib import Path

    from quantmesh.research.jobs import DatasetRejected

    def forbidden_read(path):
        pytest.fail("unsafe dataset name reached file I/O")

    monkeypatch.setattr(Path, "read_bytes", forbidden_read)
    with pytest.raises(DatasetRejected):
        pin_fixture_dataset(tmp_path, "../outside")
