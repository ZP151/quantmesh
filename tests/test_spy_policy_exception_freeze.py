"""Controlled contract fixtures only; no SDK, market data or financial math."""

import copy
import hashlib
from datetime import timedelta
from uuid import uuid4

import pytest

from quantmesh.data.objects import ObjectRef, ObjectStore
from quantmesh.research import spy_policy_exception as policy
from tests.test_freeze_opend_spy_daily import AS_OF, authorization, payload, post_review
from tools.research import freeze_opend_spy_daily as freezer


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def authority(tmp_path, monkeypatch):
    # Replace trust pins only inside this controlled unit test, never through DTOs.
    approval = freezer._canonical(
        dict(
            status="HUMAN_APPROVED_ONCE",
            proposal_sha256="a" * 64,
            internal_decision="APPROVE_ONCE_PRIVATE_DIAGNOSTIC_EXCEPTION",
            actual_data_math_budget_gates="UNCHANGED",
            explicit_prohibition="STOP if established",
        )
    )
    text = b"CONTROLLED ENGINEERING POLICY. No real qualification."
    monkeypatch.setattr(policy, "HUMAN_DECISION_SHA256", sha(approval))
    monkeypatch.setattr(policy, "POLICY_DOCUMENT_SHA256", sha(text))
    monkeypatch.setattr(policy, "PROPOSAL_SHA256", "a" * 64)
    root, scope = tmp_path / "capture", tmp_path / "authority"
    monkeypatch.setenv("QUANTMESH_SPY_ONCE_AUTHORITY_ROOT", str(scope))
    store = ObjectStore(root)
    refs = dict(
        human_approval_ref=store.put_bytes("application/json", approval).model_dump(),
        policy_document_ref=store.put_bytes("text/markdown", text).model_dump(),
    )
    binding = dict(
        schema_version=3,
        policy_status="POLICY_EXCEPTION_ONCE",
        internal_once_exception="HUMAN_APPROVED",
        provider_permission_verified=False,
        internal_decision="APPROVE_ONCE_PRIVATE_DIAGNOSTIC_EXCEPTION",
        external_api_storage_applicability="UNKNOWN",
        diagnostic_status="diagnostic_only_under_policy_exception",
        scope="US.SPY/1d/private_research",
        once_scope_id=sha(approval),
        proposal_sha256="a" * 64,
        capture_intent_id=str(uuid4()),
        job_idempotency_key=policy.job_key(sha(approval)),
        window_sha256=sha(freezer._canonical(freezer.plan_window(AS_OF))),
        output_root_sha256=policy.root_pin(root),
        authority_root_sha256=policy.root_pin(scope),
        **refs,
    )
    return root, scope, binding


def v3_authorization(binding):
    return {
        **authorization(),
        "schema_version": 3,
        "use_status": "POLICY_EXCEPTION_ONCE",
        "use_document_sha256": binding["policy_document_ref"]["digest"],
        "policy_exception": binding,
    }


def consumed(authority):
    root, scope, binding = authority
    auth = v3_authorization(binding)
    marker = policy.consume_once(binding, auth, scope, root, AS_OF)
    return auth, marker


def test_trusted_authority_bytes_and_single_scope_are_checked(authority):
    root, _, binding = authority
    parsed = policy.verify_authority(binding, ObjectStore(root))
    assert parsed.once_scope_id == binding["human_approval_ref"]["digest"]
    assert parsed.provider_permission_verified is False
    broken = copy.deepcopy(binding)
    broken["human_approval_ref"]["digest"] = "b" * 64
    with pytest.raises(ValueError):
        policy.verify_authority(broken, ObjectStore(root))


@pytest.mark.parametrize(
    "field,value",
    [
        ("external_api_storage_applicability", "VERIFIED"),
        ("provider_permission_verified", True),
        ("policy_status", "ALLOW_WITH_SCOPE"),
        ("scope", "US.QQQ/1d/private_research"),
        ("job_idempotency_key", str(uuid4())),
        ("once_scope_id", "c" * 64),
    ],
)
def test_exception_cannot_launder_scope_or_permission(authority, field, value):
    root, _, binding = authority
    broken = {**binding, field: value}
    with pytest.raises(ValueError):
        policy.verify_authority(broken, ObjectStore(root))


def test_consumption_is_create_only_before_any_sdk_and_cannot_change_nonce(authority):
    root, scope, binding = authority
    auth, marker = consumed(authority)
    proof = policy.verify_intent(binding, auth, marker, ObjectStore(root))
    assert proof["authorization_sha256"] == sha(freezer._canonical(auth))
    assert list(scope.glob("capture-intent-*.json"))
    changed = {**binding, "capture_intent_id": str(uuid4())}
    with pytest.raises(ValueError, match="once_scope_consumed"):
        policy.consume_once(changed, v3_authorization(changed), scope, root, AS_OF)
    with pytest.raises(ValueError):
        policy.consume_once(binding, auth, scope, root.parent / "other", AS_OF)


def test_authorization_cannot_choose_a_second_canonical_authority_root(authority):
    root, scope, binding = authority
    another = scope.parent / "new-authority"
    changed = {**binding, "authority_root_sha256": policy.root_pin(another)}
    with pytest.raises(ValueError):
        policy.consume_once(changed, v3_authorization(changed), another, root, AS_OF)
    assert not another.exists()


def test_oversized_authority_bytes_refuse_before_loading_contents(authority, monkeypatch):
    root, _, binding = authority
    store = ObjectStore(root)
    ref = ObjectRef.model_validate(binding["human_approval_ref"])
    store.path_for(ref).write_bytes(b"x" * (policy.MAX_PROOF + 1))
    reads = []

    def forbidden(reference):
        reads.append(reference)
        raise ValueError("must reject stat before read")

    monkeypatch.setattr(store, "get_bytes", forbidden)
    with pytest.raises(ValueError):
        policy.verify_authority(binding, store)
    assert reads == []


def test_v3_authorization_requires_fixed_policy_module_origin(authority, monkeypatch, tmp_path):
    root, _, binding = authority
    foreign = tmp_path / "other-policy.py"
    foreign.write_text("# controlled foreign origin", encoding="utf-8")
    monkeypatch.setattr(policy, "__file__", str(foreign))
    with pytest.raises(ValueError):
        freezer._authorization(
            v3_authorization(binding), AS_OF, AS_OF, proof_store=ObjectStore(root)
        )


def test_v2_stays_allow_only_and_v3_cannot_claim_allow(authority):
    _, _, binding = authority
    with pytest.raises(ValueError):
        freezer._authorization(
            {**authorization(), "use_status": "POLICY_EXCEPTION_ONCE"}, AS_OF, AS_OF
        )
    bad = {**v3_authorization(binding), "use_status": "ALLOW_WITH_SCOPE"}
    with pytest.raises(ValueError):
        freezer._authorization(bad, AS_OF, AS_OF)


def frozen_v3(authority):
    root, _, binding = authority
    auth, marker = consumed(authority)
    raw = {
        **payload(freezer.plan_window(AS_OF)),
        "schema_version": 3,
        "authorization_sha256": sha(freezer._canonical(auth)),
        "requested_at_utc": (AS_OF + timedelta(seconds=30)).isoformat(),
        "capture_intent_ref": marker,
    }
    review = {
        **post_review(raw, auth),
        "schema_version": 3,
        "capture_intent_ref": marker,
        "policy_exception": binding,
    }
    result = freezer.freeze_capture(
        raw,
        AS_OF,
        {"schema_version": 3, "authorization": auth, "review": review},
        root,
        frozen_at=AS_OF + timedelta(minutes=3),
    )
    return result, auth, raw, review


def test_v3_freeze_and_reopen_bind_original_policy_and_consumed_intent(authority):
    result, _, _, _ = frozen_v3(authority)
    assert result["schema_id"] == "qm.spy-daily.freeze.v3.policy-exception-once"
    reopened = freezer.reopen_freeze(authority[0], result["freeze_digest"])
    assert reopened["members"] == result["members"]
    assert reopened["policy_exception"] == authority[2]
    assert reopened["capture_intent_ref"]["digest"]


@pytest.mark.parametrize("member", ["protocol_ref", "post-review.json", "raw-capture.json"])
def test_v3_reopen_refuses_changed_size_before_object_read(authority, monkeypatch, member):
    result, _, _, _ = frozen_v3(authority)
    ref = ObjectRef.model_validate(
        result[member] if member == "protocol_ref" else result["members"][member]
    )
    store = ObjectStore(authority[0])
    path = store.path_for(ref)
    path.write_bytes(path.read_bytes() + b" ")
    reads = []
    original = ObjectStore.get_bytes

    def observed(self, reference):
        if reference == ref:
            reads.append(reference)
        return original(self, reference)

    monkeypatch.setattr(ObjectStore, "get_bytes", observed)
    with pytest.raises(ValueError):
        freezer.reopen_freeze(authority[0], result["freeze_digest"])
    assert reads == []


@pytest.mark.parametrize(
    "name", ["human-approval.json", "source-use-policy.md", "capture-intent.json"]
)
def test_freeze_rechecks_proof_size_after_review_before_copy(authority, monkeypatch, name):
    root, _, binding = authority
    store, reads, selected = ObjectStore(root), [], []
    original_review = freezer._reviewed_inputs_v3
    original_get = ObjectStore.get_bytes

    def replaced_after_review(raw, *args):
        result = original_review(raw, *args)
        reference = {
            "human-approval.json": binding["human_approval_ref"],
            "source-use-policy.md": binding["policy_document_ref"],
            "capture-intent.json": raw["capture_intent_ref"],
        }[name]
        selected.append(ObjectRef.model_validate(reference))
        store.path_for(selected[0]).write_bytes(b"x" * (16384 + 1))
        return result

    def observed(self, reference):
        if selected and reference == selected[0]:
            reads.append(reference)
        return original_get(self, reference)

    monkeypatch.setattr(freezer, "_reviewed_inputs_v3", replaced_after_review)
    monkeypatch.setattr(ObjectStore, "get_bytes", observed)
    with pytest.raises(ValueError):
        frozen_v3(authority)
    assert selected and reads == []


def test_cli_explicit_v3_verify_caps_manifest_before_read(authority, monkeypatch, capsys):
    result, _, _, _ = frozen_v3(authority)
    store = ObjectStore(authority[0])
    ref = ObjectRef.model_validate(result["freeze_ref"])
    store.path_for(ref).write_bytes(b"x" * (1024 * 1024 + 1))
    original, reads = ObjectStore.get_bytes, []

    def observed(self, reference):
        if reference.digest == ref.digest:
            reads.append(reference)
        return original(self, reference)

    monkeypatch.setattr(ObjectStore, "get_bytes", observed)
    assert (
        freezer.main(
            ["verify", "--root", str(authority[0]), "--digest", ref.digest, "--policy-exception"]
        )
        == 2
    )
    assert reads == [] and "freeze_failed" in capsys.readouterr().err


def test_policy_does_not_relax_real_fields_or_review_timing(authority):
    root, _, binding = authority
    auth, marker = consumed(authority)
    raw = {
        **payload(freezer.plan_window(AS_OF)),
        "schema_version": 3,
        "authorization_sha256": sha(freezer._canonical(auth)),
        "requested_at_utc": (AS_OF + timedelta(seconds=30)).isoformat(),
        "capture_intent_ref": marker,
    }
    review = {
        **post_review(raw, auth),
        "schema_version": 3,
        "capture_intent_ref": marker,
        "policy_exception": binding,
        "currency": "UNKNOWN",
    }
    with pytest.raises(ValueError):
        freezer.freeze_capture(
            raw,
            AS_OF,
            {"schema_version": 3, "authorization": auth, "review": review},
            root,
            frozen_at=AS_OF + timedelta(minutes=3),
        )


def test_v3_collect_reuses_real_provider_and_records_same_bounded_wire(authority):
    from tests.test_freeze_opend_spy_daily import Wire

    root, _, _ = authority
    auth, marker = consumed(authority)
    (root / "capture-intent-ref.json").write_bytes(freezer._canonical(marker))
    wire = Wire(payload(freezer.plan_window(AS_OF)))
    raw = freezer.collect(
        wire, AS_OF, auth, raw_root=root, clock=lambda: AS_OF + timedelta(minutes=1)
    )
    assert raw["schema_version"] == 3 and raw["capture_intent_ref"] == marker
    assert len(wire.requests) == 1 and len(raw["history_pages"][0]["rows"]) == 121
    assert wire.requests[0][1]["autype"] == "None"


def test_sdk_setup_failure_consumes_before_construction_and_never_retries(
    authority, monkeypatch, capsys
):
    from quantmesh.moomoo import opend

    root, scope, binding = authority
    auth = v3_authorization(binding)
    path = root / "authorization.json"
    path.write_bytes(freezer._canonical(auth))
    attempts = []

    def sdk(**kwargs):
        assert (scope / f"capture-intent-{binding['once_scope_id']}.json").exists()
        assert (root / "capture-intent-ref.json").exists()
        attempts.append(1)
        raise RuntimeError("controlled setup failure")

    monkeypatch.setattr(opend, "SdkTransport", sdk)
    old_version = freezer.version
    monkeypatch.setattr(
        freezer,
        "version",
        lambda name: "synthetic-no-sdk" if name == "moomoo-api" else old_version(name),
    )
    args = [
        "capture",
        "--as-of",
        AS_OF.isoformat(),
        "--authorization-json",
        str(path),
        "--root",
        str(root),
        "--once-authority-root",
        str(scope),
        "--port",
        "11111",
        "--execute-once",
    ]
    assert freezer.main(args, clock=lambda: AS_OF + timedelta(minutes=1)) == 2
    assert "freeze_failed" in capsys.readouterr().err and attempts == [1]
    assert freezer.main(args, clock=lambda: AS_OF + timedelta(minutes=1)) == 2
    assert "once_scope_consumed" in capsys.readouterr().err and attempts == [1]


def test_existing_v2_freeze_remains_v2_with_original_allow_semantics(tmp_path):
    from tests.test_freeze_opend_spy_daily import freeze_evidence, v2raw

    raw = v2raw()
    frozen = freezer.freeze_capture(
        raw, AS_OF, freeze_evidence(raw), tmp_path, frozen_at=AS_OF + timedelta(minutes=3)
    )
    store = ObjectStore(tmp_path)
    ref = ObjectRef.model_validate(frozen["freeze_ref"])
    before = store.get_bytes(ref)
    reopened = freezer.reopen_freeze(tmp_path, ref.digest)
    assert reopened["schema_id"] == "qm.spy-daily.freeze.v2"
    assert store.get_bytes(ref) == before and "policy_exception" not in reopened
