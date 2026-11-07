"""Real ledger IO with synthetic Operator handoffs; no native, SDK or permission issue."""

import hashlib
import importlib.util
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from quantmesh.research import ivv_recovery as contract

BASE = Path(__file__).resolve().parents[1]
METHOD = "a" * 64
OLD_PROVIDER = "b" * 64
NEW_PROVIDER = "c" * 64


def task_module():
    spec = importlib.util.spec_from_file_location(
        "_provider_repair_ledger", BASE / "tools/research/ivv_additional_task.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def pair(book, number, provider, method=METHOD):
    return {
        "schema_id": "qm.ivv.reference-pair.v1",
        "nonce": ("d" if number == 1 else "e") * 32,
        "reference_attempt": f"connection-{number:06d}",
        "capture_attempt": f"connection-{number + 1:06d}",
        "reference_context": "1" * 32,
        "capture_context": "2" * 32,
        "reference_control_sha256": "3" * 64,
        "method_sha256": method,
        "policy_sha256": book.policy_sha,
        "provider_binding_sha256": provider,
        "sdk_pins_sha256": "4" * 64,
        "provider_config_sha256": "5" * 64,
        "provider_cohort_sha256": "6" * 64,
    }


def normal_close():
    return {
        "child_reaped": True,
        "recursive_populated": 0,
        "owned_fds_closed": True,
        "resource_limit_event": False,
        "active_owned_processes": 0,
    }


def failed_reference(root, *, failure="REFERENCE_INIT_OBSERVATION"):
    task = task_module()
    book = task.RecoveryLedger(root, contract.DEFAULT_POLICY, contract)
    previous = book.begin(METHOD, now=100, reference_pair=pair(book, 1, OLD_PROVIDER))
    book.close(previous, normal_close(), failure=failure, method_sha256=METHOD)
    return task, book, previous


def proof(previous="connection-000001"):
    return {
        "schema_id": "qm.ivv.provider-repair.v1",
        "change": "same-build-owned-provider-replacement",
        "logical_task_id": contract.LOGICAL_TASK_ID,
        "previous_connection_attempt_id": previous,
        "previous_method_sha256": METHOD,
        "old_provider_binding_sha256": OLD_PROVIDER,
        "new_provider_binding_sha256": NEW_PROVIDER,
        "maintenance_id": "7" * 32,
        "maintenance_control_sha256": "8" * 64,
        "maintenance_source_sha256": "9" * 64,
        "interruption_authority_sha256": "a" * 64,
        "stop_closed_sha256": "b" * 64,
        "successor_start_intent_sha256": "c" * 64,
        "successor_nonce": "d" * 32,
        "owned_old_closed": True,
        "successor_binding_verified": True,
        "sdk_or_data_qualification": False,
    }


def install_synthetic_handoff(book, value=None, raw=None):
    """Fixture setup models the separately reviewed immutable root Operator import."""
    value = proof() if value is None else value
    raw = canonical(value) if raw is None else raw
    name = value["previous_connection_attempt_id"] + ".provider-repair.json"
    path = book.root / name
    with path.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    book.sync(book.root)
    path.chmod(0o444)
    return {
        "previous_connection_attempt_id": value["previous_connection_attempt_id"],
        "proof_sha256": hashlib.sha256(raw).hexdigest(),
    }


def test_same_method_without_repair_still_refuses_despite_new_provider(tmp_path):
    _, book, _ = failed_reference(tmp_path)
    with pytest.raises(ValueError, match="unrepaired_structural_failure"):
        book.begin(METHOD, now=101, reference_pair=pair(book, 2, NEW_PROVIDER))
    assert not (tmp_path / "connection-000002.intent.json").exists()


@pytest.mark.parametrize("method", [METHOD, "f" * 64], ids=["same-method", "changed-source"])
def test_changed_provider_handoff_reaches_exactly_one_new_intent(tmp_path, method):
    _, book, previous = failed_reference(tmp_path)
    historical = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    ref = install_synthetic_handoff(book)
    new_pair = pair(book, 2, NEW_PROVIDER, method)

    current = book.begin(
        method,
        now=101,
        reference_pair=new_pair,
        provider_repair_ref=ref,
    )

    assert current == "connection-000002"
    claim = book._read(previous + ".provider-repair-claim.json")
    assert claim == {
        "schema_id": "qm.ivv.provider-repair-claim.v1",
        "logical_task_id": contract.LOGICAL_TASK_ID,
        "previous_connection_attempt_id": previous,
        "proof_sha256": ref["proof_sha256"],
        "maintenance_id": "7" * 32,
        "maintenance_control_sha256": "8" * 64,
        "old_provider_binding_sha256": OLD_PROVIDER,
        "new_provider_binding_sha256": NEW_PROVIDER,
        "reference_pair_sha256": hashlib.sha256(canonical(new_pair)).hexdigest(),
        "connection_attempt_id": current,
        "method_sha256": method,
    }
    intent = book._read(current + ".intent.json")
    assert intent["provider_repair_ref"] == ref
    assert intent["provider_repair_claim_sha256"] == hashlib.sha256(canonical(claim)).hexdigest()
    assert intent["historical_actual_cumulative"] == "UNKNOWN"
    for name, original in historical.items():
        assert (tmp_path / name).read_bytes() == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("extra", True),
        ("schema_id", "other"),
        ("change", "unverified-restart"),
        ("logical_task_id", "other-task"),
        ("previous_connection_attempt_id", "connection-000002"),
        ("previous_method_sha256", "f" * 64),
        ("old_provider_binding_sha256", "f" * 64),
        ("new_provider_binding_sha256", OLD_PROVIDER),
        ("maintenance_control_sha256", "G" * 64),
        ("maintenance_source_sha256", None),
        ("interruption_authority_sha256", 1),
        ("stop_closed_sha256", "8" * 63),
        ("successor_start_intent_sha256", True),
        ("maintenance_id", "7" * 31),
        ("successor_nonce", True),
        ("owned_old_closed", 1),
        ("successor_binding_verified", False),
        ("sdk_or_data_qualification", 0),
    ],
)
def test_invalid_proof_refuses_even_when_method_changes(tmp_path, field, value):
    _, book, previous = failed_reference(tmp_path)
    data = proof()
    data[field] = value
    # Keep the actual previous filename even when corrupting the body identity.
    raw = canonical(data)
    ref = install_synthetic_handoff(book, raw=raw)
    with pytest.raises(ValueError):
        book.begin(
            "f" * 64,
            now=101,
            reference_pair=pair(book, 2, NEW_PROVIDER, "f" * 64),
            provider_repair_ref=ref,
        )
    assert not (tmp_path / (previous + ".provider-repair-claim.json")).exists()
    assert not (tmp_path / "connection-000002.intent.json").exists()


@pytest.mark.parametrize("mutation", ["extra_path", "body", "previous", "pin", "not_ref"])
def test_repair_ref_cannot_select_caller_path_body_or_other_pin(tmp_path, mutation):
    _, book, previous = failed_reference(tmp_path)
    ref = install_synthetic_handoff(book)
    if mutation == "extra_path":
        ref["path"] = str(tmp_path / "elsewhere.json")
    elif mutation == "body":
        ref["proof"] = proof()
    elif mutation == "previous":
        ref["previous_connection_attempt_id"] = "../../outside"
    elif mutation == "pin":
        ref["proof_sha256"] = "f" * 64
    else:
        ref = canonical(ref)
    with pytest.raises(ValueError):
        book.begin(
            "f" * 64,
            now=101,
            reference_pair=pair(book, 2, NEW_PROVIDER, "f" * 64),
            provider_repair_ref=ref,
        )
    assert not (tmp_path / (previous + ".provider-repair-claim.json")).exists()


@pytest.mark.parametrize("raw_kind", ["padding", "array", "oversized", "noncanonical"])
def test_proof_requires_exact_canonical_bounded_original(tmp_path, raw_kind):
    _, book, previous = failed_reference(tmp_path)
    if raw_kind == "padding":
        raw = canonical(proof()) + b"\n"
    elif raw_kind == "array":
        raw = b"[]"
    elif raw_kind == "oversized":
        raw = b"x" * 32769
    else:
        raw = json.dumps(proof()).encode()
    ref = install_synthetic_handoff(book, raw=raw)
    with pytest.raises(ValueError):
        book.begin(
            METHOD, now=101, reference_pair=pair(book, 2, NEW_PROVIDER), provider_repair_ref=ref
        )
    assert not (tmp_path / (previous + ".provider-repair-claim.json")).exists()


def test_linked_proof_fails_existing_single_inode_custody(tmp_path):
    _, book, previous = failed_reference(tmp_path)
    ref = install_synthetic_handoff(book)
    os.link(tmp_path / (previous + ".provider-repair.json"), tmp_path / "linked-proof.json")
    with pytest.raises(ValueError, match="recovery_journal_file"):
        book.begin(
            METHOD, now=101, reference_pair=pair(book, 2, NEW_PROVIDER), provider_repair_ref=ref
        )
    assert not (tmp_path / (previous + ".provider-repair-claim.json")).exists()


@pytest.mark.parametrize("mode", ["ordinary", "capture_transition"])
def test_explicit_repair_ref_is_never_an_orphan_on_other_roles(tmp_path, mode):
    _, book, previous = failed_reference(tmp_path)
    ref = install_synthetic_handoff(book)
    kwargs = {} if mode == "ordinary" else {"reference_transition": {"untrusted": "placeholder"}}
    with pytest.raises(ValueError, match="provider_repair_role"):
        book.begin("f" * 64, now=101, provider_repair_ref=ref, **kwargs)
    assert not (tmp_path / (previous + ".provider-repair-claim.json")).exists()


def test_repair_ref_without_any_previous_attempt_refuses(tmp_path):
    task = task_module()
    book = task.RecoveryLedger(tmp_path, contract.DEFAULT_POLICY, contract)
    with pytest.raises(ValueError, match="provider_repair_role"):
        book.begin(
            METHOD,
            now=100,
            reference_pair=pair(book, 1, NEW_PROVIDER),
            provider_repair_ref={
                "previous_connection_attempt_id": "connection-000001",
                "proof_sha256": "a" * 64,
            },
        )
    assert not list(tmp_path.iterdir())


def test_ordinary_failed_job_cannot_supply_reference_repair_proof(tmp_path):
    task = task_module()
    book = task.RecoveryLedger(tmp_path, contract.DEFAULT_POLICY, contract)
    first = book.begin(METHOD, now=100)
    book.close(first, normal_close(), failure="REFERENCE_INIT_OBSERVATION", method_sha256=METHOD)
    ref = install_synthetic_handoff(book)
    with pytest.raises(ValueError, match="provider_repair_previous"):
        book.begin(
            "f" * 64,
            now=101,
            reference_pair=pair(book, 2, NEW_PROVIDER, "f" * 64),
            provider_repair_ref=ref,
        )
    assert not (tmp_path / (first + ".provider-repair-claim.json")).exists()


@pytest.mark.parametrize("failure", [None, "RUNTIME_ORIGIN", "CAPTURE_TIMEOUT"])
def test_proof_only_applies_to_current_reference_init_failure(tmp_path, failure):
    _, book, previous = failed_reference(tmp_path, failure=failure)
    ref = install_synthetic_handoff(book)
    with pytest.raises(ValueError, match="provider_repair_previous"):
        book.begin(
            "f" * 64,
            now=101,
            reference_pair=pair(book, 2, NEW_PROVIDER, "f" * 64),
            provider_repair_ref=ref,
        )
    assert not (tmp_path / (previous + ".provider-repair-claim.json")).exists()


def test_repair_for_nonlatest_attempt_cannot_be_remapped(tmp_path):
    _, book, previous = failed_reference(tmp_path)
    ref = install_synthetic_handoff(book)
    second = book.begin("f" * 64, now=101, reference_pair=pair(book, 2, NEW_PROVIDER, "f" * 64))
    book.close(second, normal_close(), failure="REFERENCE_INIT_OBSERVATION", method_sha256="f" * 64)
    with pytest.raises(ValueError, match="provider_repair_ref"):
        book.begin(
            "f" * 64,
            now=102,
            reference_pair=pair(book, 3, "8" * 64, "f" * 64),
            provider_repair_ref=ref,
        )
    assert not (tmp_path / (previous + ".provider-repair-claim.json")).exists()


def test_unchanged_or_wrong_successor_provider_refuses(tmp_path):
    _, book, previous = failed_reference(tmp_path)
    ref = install_synthetic_handoff(book)
    for provider in [OLD_PROVIDER, "f" * 64]:
        with pytest.raises(ValueError, match="provider_repair_binding"):
            book.begin(
                METHOD, now=101, reference_pair=pair(book, 2, provider), provider_repair_ref=ref
            )
    assert not (tmp_path / (previous + ".provider-repair-claim.json")).exists()


def test_claim_is_exclusive_across_independent_concurrent_books(tmp_path):
    task, book, previous = failed_reference(tmp_path)
    ref = install_synthetic_handoff(book)

    def attempt(_):
        candidate = task.RecoveryLedger(tmp_path, contract.DEFAULT_POLICY, contract)
        try:
            return candidate.begin(
                METHOD,
                now=101,
                reference_pair=pair(candidate, 2, NEW_PROVIDER),
                provider_repair_ref=ref,
            )
        except (ValueError, FileExistsError):
            return "REFUSED_SPENT_OR_IN_PROGRESS"

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(attempt, range(4)))
    assert results.count("connection-000002") == 1
    assert results.count("REFUSED_SPENT_OR_IN_PROGRESS") == 3
    assert (tmp_path / (previous + ".provider-repair-claim.json")).exists()


def test_claim_fsync_crash_cannot_be_reused_by_changed_method_or_pair(tmp_path):
    task, book, previous = failed_reference(tmp_path)
    ref = install_synthetic_handoff(book)

    def crash(_):
        raise OSError("synthetic parent-directory fsync uncertainty")

    book.sync = crash
    with pytest.raises(OSError):
        book.begin(
            METHOD, now=101, reference_pair=pair(book, 2, NEW_PROVIDER), provider_repair_ref=ref
        )
    assert (tmp_path / (previous + ".provider-repair-claim.json")).exists()
    assert not (tmp_path / "connection-000002.intent.json").exists()
    assert not (tmp_path / "connection-000002.reference-pair.json").exists()
    persisted = (tmp_path / (previous + ".provider-repair-claim.json")).read_bytes()
    replay = task.RecoveryLedger(tmp_path, contract.DEFAULT_POLICY, contract)
    for method, nonce in [(METHOD, "e" * 32), ("f" * 64, "0" * 32)]:
        new_pair = pair(replay, 2, NEW_PROVIDER, method)
        new_pair["nonce"] = nonce
        with pytest.raises(FileExistsError):
            replay.begin(method, now=101, reference_pair=new_pair, provider_repair_ref=ref)
    assert replay.usage()["contexts"] == 1
    assert (tmp_path / (previous + ".provider-repair-claim.json")).read_bytes() == persisted


def test_crash_after_durable_claim_before_intent_keeps_claim_spent(tmp_path):
    task, book, previous = failed_reference(tmp_path)
    ref = install_synthetic_handoff(book)

    class Interrupted(task.RecoveryLedger):
        def _write(self, name, value):
            result = super()._write(name, value)
            if name.endswith(".provider-repair-claim.json"):
                raise KeyboardInterrupt("synthetic post-claim interruption")
            return result

    interrupted = Interrupted(tmp_path, contract.DEFAULT_POLICY, contract)
    with pytest.raises(KeyboardInterrupt):
        interrupted.begin(
            METHOD,
            now=101,
            reference_pair=pair(interrupted, 2, NEW_PROVIDER),
            provider_repair_ref=ref,
        )
    with pytest.raises(FileExistsError):
        book.begin(
            METHOD, now=101, reference_pair=pair(book, 2, NEW_PROVIDER), provider_repair_ref=ref
        )
    assert not (tmp_path / "connection-000002.intent.json").exists()
    assert not (tmp_path / "connection-000002.reference-pair.json").exists()
    assert (tmp_path / (previous + ".provider-repair-claim.json")).exists()


def test_no_ref_legacy_changed_method_keeps_exact_old_intent_shape(tmp_path):
    _, book, _ = failed_reference(tmp_path)
    current = book.begin("f" * 64, now=101)
    assert book._read(current + ".intent.json") == {
        "schema_id": "qm.ivv.connection-attempt.v1",
        "state": "INTENT",
        "logical_task_id": contract.LOGICAL_TASK_ID,
        "batch_id": book.policy["batch"]["batch_id"],
        "policy_sha256": book.policy_sha,
        "connection_attempt_id": "connection-000002",
        "method_sha256": "f" * 64,
        "started": 101,
        "historical_actual_cumulative": "UNKNOWN",
    }
    assert not list(tmp_path.glob("*.provider-repair*"))


def test_missing_handoff_never_creates_claim_or_intent(tmp_path):
    _, book, previous = failed_reference(tmp_path)
    ref = {"previous_connection_attempt_id": previous, "proof_sha256": "f" * 64}
    with pytest.raises(FileNotFoundError):
        book.begin(
            METHOD, now=101, reference_pair=pair(book, 2, NEW_PROVIDER), provider_repair_ref=ref
        )
    assert not (tmp_path / (previous + ".provider-repair-claim.json")).exists()
    assert not (tmp_path / "connection-000002.intent.json").exists()


def test_corrupted_old_pair_cannot_be_used_as_repair_binding(tmp_path):
    _, book, previous = failed_reference(tmp_path)
    ref = install_synthetic_handoff(book)
    corrupted = pair(book, 1, "f" * 64)
    (tmp_path / (previous + ".reference-pair.json")).write_bytes(canonical(corrupted))
    with pytest.raises(ValueError, match="provider_repair_binding"):
        book.begin(
            METHOD, now=101, reference_pair=pair(book, 2, NEW_PROVIDER), provider_repair_ref=ref
        )
    assert not (tmp_path / (previous + ".provider-repair-claim.json")).exists()


@pytest.mark.parametrize("field,value", [("method_sha256", "f" * 64), ("policy_sha256", "f" * 64)])
def test_new_pair_must_match_current_method_and_policy_before_claim(tmp_path, field, value):
    _, book, previous = failed_reference(tmp_path)
    ref = install_synthetic_handoff(book)
    malformed = pair(book, 2, NEW_PROVIDER)
    malformed[field] = value
    with pytest.raises(ValueError, match="provider_repair_binding"):
        book.begin(METHOD, now=101, reference_pair=malformed, provider_repair_ref=ref)
    assert not (tmp_path / (previous + ".provider-repair-claim.json")).exists()


def test_normal_closed_required_even_if_unknown_owner_has_later_recovery(tmp_path):
    task = task_module()
    book = task.RecoveryLedger(tmp_path, contract.DEFAULT_POLICY, contract)
    previous = book.begin(METHOD, now=100, reference_pair=pair(book, 1, OLD_PROVIDER))
    uncertain = normal_close()
    uncertain["child_reaped"] = False
    book.close(previous, uncertain, failure="REFERENCE_INIT_OBSERVATION", method_sha256=METHOD)
    book._write(
        previous + ".recovered.json",
        {
            "owner_binding_sha256": contract.digest(
                contract.canonical(book._read(previous + ".intent.json"))
            ),
            "owned_cleanup_proven": True,
            "external_effects": "UNKNOWN",
            "input_publishable": False,
        },
    )
    ref = install_synthetic_handoff(book)
    with pytest.raises(ValueError, match="provider_repair_previous"):
        book.begin(
            "f" * 64,
            now=101,
            reference_pair=pair(book, 2, NEW_PROVIDER, "f" * 64),
            provider_repair_ref=ref,
        )
    assert not (tmp_path / (previous + ".provider-repair-claim.json")).exists()


def test_context_budget_refusal_does_not_consume_completed_repair(tmp_path):
    task = task_module()
    policy = json.loads(contract.canonical(contract.DEFAULT_POLICY))
    policy["batch"]["contexts"] = 1
    policy["batch"]["init_connect"] = 1
    policy["batch"]["keepalive"] = 96
    book = task.RecoveryLedger(tmp_path, policy, contract)
    previous = book.begin(METHOD, now=100, reference_pair=pair(book, 1, OLD_PROVIDER))
    book.close(previous, normal_close(), failure="REFERENCE_INIT_OBSERVATION", method_sha256=METHOD)
    ref = install_synthetic_handoff(book)
    with pytest.raises(ValueError, match="context_budget"):
        book.begin(
            METHOD, now=101, reference_pair=pair(book, 2, NEW_PROVIDER), provider_repair_ref=ref
        )
    assert not (tmp_path / (previous + ".provider-repair-claim.json")).exists()


def test_claim_keeps_the_ref_pin_that_was_validated_even_if_caller_mutates_input(tmp_path):
    task, book, previous = failed_reference(tmp_path)
    ref = install_synthetic_handoff(book)
    original_pin = ref["proof_sha256"]

    class MutatingCaller(task.RecoveryLedger):
        def _read(self, name, *, raw_bytes=False):
            value = super()._read(name, raw_bytes=raw_bytes)
            if name == previous + ".reference-pair.json":
                ref["proof_sha256"] = "f" * 64
            return value

    mutable = MutatingCaller(tmp_path, contract.DEFAULT_POLICY, contract)
    current = mutable.begin(
        METHOD, now=101, reference_pair=pair(mutable, 2, NEW_PROVIDER), provider_repair_ref=ref
    )
    assert mutable._read(previous + ".provider-repair-claim.json")["proof_sha256"] == original_pin
    assert (
        mutable._read(current + ".intent.json")["provider_repair_ref"]["proof_sha256"]
        == original_pin
    )
