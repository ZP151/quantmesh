"""Wire/authority unit checks; no image, native or numerical qualification."""

import hashlib
import json
import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_worker_binding_contract import _binding
from test_worker_build import _bind, _runtime

from quantmesh.research import worker_build as build

pytest_plugins = ["test_worker_build"]


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


def base_runtime():
    return dict(
        build_digest="a" * 64,
        dependency_digest="b" * 64,
        git_commit="c" * 40,
        python_version="3.12.15 pinned",
        python_executable_digest="d" * 64,
    )


def test_runtime_profile_and_report_claims_are_explicit_and_not_mutable_aliases():
    runtime = build.runtime_with_profile(base_runtime(), selected())
    assert runtime["runtime_schema"] == 2
    assert runtime["execution_profile"] == selected()
    assert len(runtime) == 7
    evidence = build.profile_report_evidence(runtime)
    assert evidence == dict(
        execution_profile_id="registered-fixture",
        execution_profile_version=1,
        execution_profile_digest=hashlib.sha256(selected().encode()).hexdigest(),
        fixture_only=True,
        opaque_native_cache_state="unverified",
    )
    build.validate_report_profile(runtime, evidence)
    assert build.profile_report_evidence(base_runtime()) == {}


@pytest.mark.parametrize("change", ["missing", "claim", "profile", "downgrade"])
def test_profile_report_and_runtime_substitution_refuse(change):
    runtime = build.runtime_with_profile(base_runtime(), selected())
    evidence = build.profile_report_evidence(runtime)
    if change == "missing":
        del evidence["execution_profile_digest"]
    elif change == "claim":
        evidence["opaque_native_cache_state"] = "verified"
    elif change == "profile":
        runtime["execution_profile"] = "{}"
    else:
        runtime = base_runtime()
    with pytest.raises(build.WorkerBuildRejected):
        build.validate_report_profile(runtime, evidence)


def test_execution_accepts_explicit_parent_runtime_but_rejects_forged_mode():
    from quantmesh.research.linux_owned import LinuxContainmentError
    from quantmesh.research.worker_execution import LinuxWorkerExecution

    runtime = build.runtime_with_profile(base_runtime(), selected())
    provider = SimpleNamespace(verify=lambda profile: dict(runtime))
    execution = LinuxWorkerExecution(SimpleNamespace(), provider)
    assert execution.runtime_fingerprint() == runtime
    runtime["execution_profile"] = "{}"
    with pytest.raises(LinuxContainmentError):
        execution.runtime_fingerprint()


def test_fixed_entry_decodes_explicit_v2_before_source_preflight():
    from test_worker_entry import _entry_module

    value = {**_binding(), "schema": 2, "execution_profile": selected()}
    raw = canonical(value)
    assert _entry_module()._decode_binding(raw, hashlib.sha256(raw).hexdigest()) == value
    value["schema"] = 1
    raw = canonical(value)
    with pytest.raises(ValueError):
        _entry_module()._decode_binding(raw, hashlib.sha256(raw).hexdigest())


def test_child_cannot_use_profile_without_actual_preimport_measurement(tmp_path):
    from quantmesh.research.job_runner import _child_main

    with pytest.raises(SystemExit) as stopped:
        _child_main(str(tmp_path), execution_profile=selected())
    assert stopped.value.code == 2
    assert json.loads((tmp_path / "error.json").read_bytes()) == {"error_code": "worker_failed"}
    assert not (tmp_path / "result.json").exists()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux absolute runtime paths required")
def test_registered_bytes_stay_pinned_and_strict_native_cache_refusal_remains(sealed, monkeypatch):
    _runtime(build, sealed, monkeypatch)
    pin = _bind(sealed)
    build.sys.modules["opaque_generated_cache"] = SimpleNamespace()
    with pytest.raises(build.WorkerBuildRejected):
        build.measure_worker_runtime(sealed.manifest, manifest_sha256=pin)
    current = build.measure_worker_runtime(
        sealed.manifest,
        manifest_sha256=pin,
        execution_profile=selected(),
    )
    assert current["execution_profile"] == selected()
    sealed.library.write_bytes(b"unreviewed native library replacement")
    with pytest.raises(build.WorkerBuildRejected):
        build.measure_worker_runtime(
            sealed.manifest,
            manifest_sha256=pin,
            execution_profile=selected(),
        )


@pytest.mark.parametrize("field", ["build_digest", "dependency_digest"])
def test_parent_rejects_report_runtime_substitution_after_schema_validation(monkeypatch, field):
    from pathlib import Path

    from quantmesh.research import job_runner

    runtime = build.runtime_with_profile(base_runtime(), selected())
    evidence = {
        **build.profile_report_evidence(runtime),
        "build_digest": runtime["build_digest"],
        "dependency_digest": runtime["dependency_digest"],
    }
    evidence[field] = "0" * 64
    report = SimpleNamespace(evidence=evidence)
    # Isolate the parent binding check; real numerical/canonical validators have
    # separate coverage and the actual server acceptance remains mandatory.
    receipt = canonical(
        dict(runtime=runtime, attempt=1, owner="owner", fixture_only=True, report={})
    )
    monkeypatch.setattr(
        job_runner,
        "_read_child_file",
        lambda root, path, limit: b"result" if path.name == "result.json" else receipt,
    )
    monkeypatch.setattr(
        job_runner, "StrategyReport", SimpleNamespace(model_validate=lambda value: report)
    )
    monkeypatch.setattr(job_runner, "canonical_result", lambda value: b"result")
    with pytest.raises(ValueError):
        job_runner._validated_child_result(
            SimpleNamespace(attempt=1), "owner", runtime, Path("owned")
        )
