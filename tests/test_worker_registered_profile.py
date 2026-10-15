"""Wire/authority unit checks; no image, native or numerical qualification."""

import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_worker_binding_contract import _binding

from quantmesh.research import worker_build as build


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def selected():
    return build.registered_fixture_profile()


def job():
    data = json.loads(selected())
    dataset = {
        key: data[key]
        for key in (
            "dataset_id",
            "revision",
            "manifest_digest",
            "export_digest",
            "permission_class",
        )
    }
    return SimpleNamespace(
        request=SimpleNamespace(
            strategy_id="momentum",
            strategy_version="1",
            parameters={},
            dataset=SimpleNamespace(model_dump=lambda: dataset),
        )
    )


def test_profile_is_exact_versioned_fixed_fixture_contract():
    raw = selected()
    data = build.parse_execution_profile(raw)
    assert canonical(data).decode() == raw
    assert data["profile_id"] == "registered-fixture"
    assert data["profile_version"] == 1
    assert data["strategy_id"] == "momentum" and data["strategy_version"] == "1"
    assert data["permission_class"] == "fixture"
    assert (
        data["manifest_digest"]
        == "79f7b95084db3eef4e81f4cd0031b7805fe5733105619682e1b9e4c8175941cf"
    )
    assert (
        data["export_digest"] == "d4e71bbee94b49dfdd38a6801b8f33308bf5ad470fdacc499badcdecc0796501"
    )
    assert data["native_state"] == "opaque native cache state unverified"
    build.validate_registered_job(job(), raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("profile_version", True),
        ("profile_id", "strict"),
        ("revision", 2),
        ("manifest_digest", "0" * 64),
        ("export_digest", "0" * 64),
        ("strategy_id", "python"),
        ("permission_class", "remote_export"),
        ("native_state", "verified"),
        ("custom_source", "user.py"),
    ],
)
def test_profile_rejects_other_contract_or_forged_claim(field, value):
    data = json.loads(selected())
    data[field] = value
    with pytest.raises(build.WorkerBuildRejected):
        build.parse_execution_profile(canonical(data).decode())


@pytest.mark.parametrize(
    "field,value",
    [
        ("strategy_id", "mean_reversion"),
        ("strategy_version", "2"),
        ("parameters", {"execution_profile": "registered-fixture"}),
    ],
)
def test_parent_and_child_can_reject_job_outside_selected_contract(field, value):
    candidate = job()
    setattr(candidate.request, field, value)
    with pytest.raises(build.WorkerBuildRejected):
        build.validate_registered_job(candidate, selected())


def test_job_dataset_substitution_refuses_even_when_profile_valid():
    candidate = job()
    dataset = candidate.request.dataset.model_dump()
    candidate.request.dataset.model_dump = lambda: {
        **dataset,
        "manifest_digest": "0" * 64,
    }
    with pytest.raises(build.WorkerBuildRejected):
        build.validate_registered_job(candidate, selected())


def test_schema2_seals_profile_and_schema1_roundtrip_is_unchanged():
    base = build.ParentBindingContract(**_binding())
    raw, digest = build.encode_parent_binding(base)
    assert set(json.loads(raw)) == set(_binding())
    assert build.parse_parent_binding(raw, expected_sha256=digest) == base
    limited = replace(base, schema=2, execution_profile=selected())
    raw, digest = build.encode_parent_binding(limited)
    assert json.loads(raw)["execution_profile"] == selected()
    assert build.parse_parent_binding(raw, expected_sha256=digest) == limited
    mutated = json.loads(raw)
    mutated["execution_profile"] = "{}"
    altered = canonical(mutated)
    with pytest.raises(build.WorkerBuildRejected):
        build.parse_parent_binding(altered, expected_sha256=hashlib.sha256(altered).hexdigest())


def test_no_implicit_binding_downgrade_or_unsealed_profile():
    base = build.ParentBindingContract(**_binding())
    for wrong in (replace(base, execution_profile=selected()), replace(base, schema=2)):
        with pytest.raises(build.WorkerBuildRejected):
            build.encode_parent_binding(wrong)


def test_request_json_cannot_select_the_parent_execution_profile():
    from quantmesh.research.jobs import ResearchJobRequest

    data = json.loads(selected())
    dataset = {
        key: data[key]
        for key in (
            "dataset_id",
            "revision",
            "manifest_digest",
            "export_digest",
            "permission_class",
        )
    }
    request = dict(
        strategy_id="momentum",
        strategy_version="1",
        dataset=dataset,
        interval="1h",
        universe=[{"venue": "moomoo", "symbol": "AAA"}],
        costs={"fee_bps": 1, "half_spread_bps": 2, "slippage_bps": 3},
        window_spec={"train_bars": 10, "test_bars": 5, "step_bars": 5},
    )
    ResearchJobRequest.model_validate(request)
    with pytest.raises(ValueError):
        ResearchJobRequest.model_validate({**request, "execution_profile": selected()})
