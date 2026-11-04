"""Real pure IVV contract regressions; no SDK, filesystem or native invocation."""

import copy
import importlib
import json

import pytest


def recovery():
    return importlib.import_module("quantmesh.research.ivv_recovery")


def identity():
    return {
        "logical_task_id": "ivv-trend-staged-20261029",
        "experiment_id": "declared-trend-staged-v1",
        "input_version": "a" * 64,
        "math_cost_spec": "7e0c785311bdae85828898bcc63b7a88d724da9bab4f844eb35673c923c34fea",
    }


def reference(digest="a" * 64, media="application/json"):
    return {"algorithm": "sha256", "digest": digest, "media_type": media, "byte_length": 4}


def semantic():
    return {
        "candidate": "doublema_daily_overlay_candidate_v1",
        "inputs": {
            "bars": reference(media="text/csv"),
            "distributions": reference("b" * 64),
            "schedule": reference("c" * 64),
        },
        "instrument": "US.IVV",
        "source_id": "provider",
        "source_use": "private declared retrospective",
        "currency": "USD",
        "price_adjustment": "raw",
        "volume_unit": "shares",
        "historical_trade_venues": "observed feed fact",
        "action_coverage": "complete_cash_ex_pay_no_splits",
        "calendar_id": "XNYS",
        "calendar_timezone": "America/New_York",
        "calendar_version": "4.13.2",
        "availability_assumption": "completed_close_plus30min_assumed",
        "pit_status": "unknown",
        "revision_note": "actual provider revision fact",
        "window": {"warmup": 100, "observations": 21},
        "sample_role": "development_only_retrospective",
    }


def test_business_key_and_job_are_stable_under_mapping_order_and_checked_on_read():
    r = recovery()
    value = identity()
    checked = r.validate_identity(value)
    assert set(checked) == {*value, "business_key"}
    reordered = dict(reversed(list(value.items())))
    assert r.business_key(reordered) == checked["business_key"]
    assert r.logical_job_id(reordered) == r.logical_job_id(checked)
    altered = {**checked, "business_key": "0" * 64}
    with pytest.raises(ValueError):
        r.validate_identity(altered)
    assert r.business_key({**value, "input_version": "d" * 64}) != checked["business_key"]
    assert (
        r.business_key({**value, "experiment_id": "declared-trend-staged-v2"})
        != checked["business_key"]
    )


@pytest.mark.parametrize("extra", ["authorization_sha256", "sourcepack", "compute_attempt_id"])
def test_authority_and_attempt_fields_cannot_become_experiment_identity(extra):
    with pytest.raises(ValueError):
        recovery().business_key({**identity(), extra: "private-provenance"})


@pytest.mark.parametrize("change", ["raw_ref", "review_refs", "source_asset_refs", "exposure_ref"])
def test_semantic_hash_rejects_audit_aliases_instead_of_hashing_authority(change):
    r = recovery()
    value = semantic()
    before = r.semantic_input_version(value)
    with pytest.raises(ValueError):
        r.semantic_input_version({**value, change: reference("d" * 64)})
    changed = copy.deepcopy(value)
    changed["revision_note"] = "different actual revision fact"
    assert r.semantic_input_version(changed) != before
    changed = copy.deepcopy(value)
    changed["inputs"]["bars"]["digest"] = "d" * 64
    assert r.semantic_input_version(changed) != before


@pytest.mark.parametrize("corrupt", ["missing_schedule", "extra_raw", "negative_size", "nan"])
def test_semantic_hash_refuses_incomplete_or_noncanonical_inputs(corrupt):
    value = semantic()
    if corrupt == "missing_schedule":
        del value["inputs"]["schedule"]
    elif corrupt == "extra_raw":
        value["inputs"]["raw"] = reference()
    elif corrupt == "negative_size":
        value["inputs"]["bars"]["byte_length"] = -1
    else:
        value["window"]["warmup"] = float("nan")
    with pytest.raises(ValueError):
        recovery().semantic_input_version(value)


def test_allowance_extension_is_policy_provenance_not_a_new_business_identity():
    r = recovery()
    before = r.validate_identity(identity())
    policy = copy.deepcopy(r.DEFAULT_POLICY)
    checked = r.validate_policy(policy)
    ref = reference(r.digest(r.canonical(checked)))
    ref["byte_length"] = len(r.canonical(checked))
    attempt = r.attempt_policy(checked, ref)
    assert attempt == {
        "policy_ref": ref,
        "batch_id": checked["batch"]["batch_id"],
        "max_numerical_attempts": 3,
    }
    assert r.validate_attempt_policy(attempt, checked) == attempt
    policy["batch"]["max_numerical_attempts"] = 5
    policy["batch"]["batch_id"] = "ivv-recovery-batch-02"
    policy["authority_sha256"] = "d" * 64
    extended = r.validate_policy(policy)
    assert r.validate_identity(identity()) == before
    assert r.policy_provenance(extended)["batch_id"] == "ivv-recovery-batch-02"
    with pytest.raises(ValueError):
        r.validate_attempt_policy(attempt, extended)
    assert r.DEFAULT_POLICY["batch"]["max_numerical_attempts"] == 3


@pytest.mark.parametrize(
    "path,value",
    [
        (("batch", "contexts"), True),
        (("batch", "business_requests"), 0),
        (("batch", "max_business_per_second"), float("inf")),
        (("batch", "max_numerical_attempts"), 9),
        (("thresholds", "guard_G"), 12884901889),
        (("thresholds", "free"), 1),
        (("actor", "swap_bytes"), 1),
        (("actor", "windows_affinity_cores"), True),
        (("actor", "cpu_percent"), 50.0),
        (("assurance", "provider_hard_limit_enforced"), 0),
        (("assurance", "historical_actual_cumulative"), 0),
    ],
)
def test_policy_refuses_unfunded_unsafe_or_fabricated_facts(path, value):
    r = recovery()
    policy = copy.deepcopy(r.DEFAULT_POLICY)
    policy[path[0]][path[1]] = value
    with pytest.raises(ValueError):
        r.validate_policy(policy)


def test_policy_reference_must_match_actual_canonical_bytes():
    r = recovery()
    policy = copy.deepcopy(r.DEFAULT_POLICY)
    with pytest.raises(ValueError):
        r.attempt_policy(policy, reference("0" * 64))
    assert json.loads(r.canonical(policy)) == policy


def test_readonly_protocols_are_exact_integer_protocols_not_numeric_aliases():
    r = recovery()
    policy = copy.deepcopy(r.DEFAULT_POLICY)
    policy["read_only_protocols"][0] = 1002.0
    with pytest.raises(ValueError):
        r.validate_policy(policy)
