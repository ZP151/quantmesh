"""Private, reference-bound IVV admission; no market access or grant minting.

Expected GO/acceptance pins come from trusted operator configuration. They are
not browser request fields. Content-addressed data is never its own authority.
"""

import csv
import io
import math
from dataclasses import replace
from pathlib import Path

from quantmesh.research import native_daily_real as daily

SCOPE_ID = "e28541ddae3d7b567e23e2963cc454995aa01c420bd567d8eb8aace6b6354f07"
SOURCE_ID = "moomoo_opend"
SOURCE_USE = "private_diagnostic_internal_once_external_retention_unknown"
WINDOW_SHA = "38f7822357ce458d4fe1d974821e7fda89deb3a31208c68dcea6abb85b04eaf4"
WINDOW = {
    "warmup_start": "2026-05-08",
    "score_start": "2026-10-01",
    "score_end": "2026-10-29",
    "warmup": 100,
    "observations": 21,
}
ORIGINAL_PINS = {
    "scope": "fc2e0942cf1bcd39ddee0bb2a6e327c8ed28e5f1391a38f938777f8a31122971",
    "effect": "37e4667460e66026ba6f281116ceeb6bb525f9aebc1b10d432405a410a139e45",
    "execution": "0f523db13273e7325cad752e529eece44168a17903275d0047adf1e93b50efa3",
}
REVIEWER = "01a14f1c-b716-77f3-9339-416d56fc65fa"
INPUT_CHECKS = (
    "raw_prices",
    "shares_unit",
    "historical_venues",
    "complete_actions",
    "all121_ex_pay",
    "no_splits",
    "normal_close",
    "originals_complete",
    "source_provenance",
    "parent_seal_verified",
)
_REAL_AUTHORITY = object()


def prepare_runtime(root, basis, store):
    from quantmesh.research.ivv_runtime import IVVRuntime

    return IVVRuntime(root, basis, store)


class TrustedIVVProofs(daily.Contract):
    """Trusted startup refs/pins, never accepted by the public request model."""

    scope_ref: daily.ObjectRef
    effect_ref: daily.ObjectRef
    execution_ref: daily.ObjectRef
    go_ref: daily.ObjectRef
    acceptance_ref: daily.ObjectRef
    windows_policy_ref: daily.ObjectRef
    expected_go_sha256: daily.Digest
    expected_acceptance_sha256: daily.Digest


def input_set_digest(package):
    """The review signs facts/inputs, excluding its own future reference."""
    value = dict(package)
    value.pop("review_refs", None)
    return daily.digest(daily.canonical(value))


def _load(store, ref):
    reference = daily.ObjectRef.model_validate(ref)
    if reference.media_type != "application/json":
        raise ValueError("proof_media")
    value = daily._loads(daily.NativeDailyService._from_store(store, reference))
    if not isinstance(value, dict):
        raise ValueError("proof_object")
    return value


def _require(condition):
    if not condition:
        raise ValueError("ivv_proof")


def _capture_refs(raw):
    """Read original bytes by hash, never follow paths named by a remote child."""
    refs = []

    def local(value, media="application/json"):
        name = value["path"]
        _require(
            isinstance(name, str)
            and name not in (".", "..")
            and Path(name).name == name
            and "/" not in name
            and "\\" not in name
        )
        ref = daily.ObjectRef(digest=value["sha256"], byte_length=value["bytes"], media_type=media)
        _require(1 <= ref.byte_length <= daily.MAX_OBJECT)
        refs.append(ref)
        return ref

    for key in ("intent_ref", "metadata_ref", "plain_ref", "request_ref"):
        local(raw[key])
    _require(set(raw["responses"]) == {"rehab", "dividends", "splits", "history"})
    for response in raw["responses"].values():
        _require(response["encoding"] == "SDK_PROTOBUF_REENCODING_NOT_NETWORK_FRAME")
        sdk = local(response["sdk_ref"], "application/octet-stream")
        fields = local(response["fields_ref"])
        _require(sdk.byte_length + fields.byte_length <= daily.MAX_OBJECT)
    return refs


def _capture_close(store, raw_ref, acceptance, go, proofs):
    raw = _load(store, raw_ref)
    _require(raw["schema_id"] == "qm.ivv.capture.v1" and raw["state"] == "CAPTURED_UNREVIEWED")
    _require(raw["scope_id"] == SCOPE_ID and raw["symbol"] == "US.IVV")
    _require(
        raw["window_digest"] == go["input_window_digest"]
        and raw["full_window_sha256"] == WINDOW_SHA
    )
    _require(raw["requires_parent_close_receipt"] is True and raw["synthetic"] is False)
    _require(raw["primary_failure"] is None and raw["close_failure"] is None)
    _require(
        all(
            raw["normal_close"].get(k) is True
            for k in ("context_closed", "callbacks_stopped", "data_socket_closed")
        )
    )
    binding = raw["source_binding"]
    _require(binding["root_go_sha256"] == proofs.go_ref.digest)
    _require(
        binding["approval_sha256"] == proofs.effect_ref.digest
        and binding["execution_sha256"] == proofs.execution_ref.digest
    )
    _require(
        binding["catalog_sha256"] == go["catalog_sha256"]
        and binding["capture_helper_sha256"] == go["capture_helper_sha256"]
    )
    parent_ref = daily.ObjectRef.model_validate(acceptance["parent_close_ref"])
    parent = _load(store, parent_ref)
    _require(parent["schema_id"] == "qm.ivv.capture-parent-close.v1")
    _require(parent["state"] == "NORMAL_EXIT" and parent["termination"] == "NORMAL")
    expected = {
        "scope_id": SCOPE_ID,
        "effect_id": raw["effect_id"],
        "capture_manifest_sha256": raw_ref.digest,
        "intent_sha256": raw["intent_ref"]["sha256"],
        "catalog_sha256": binding["catalog_sha256"],
        "helper_sha256": binding["capture_helper_sha256"],
        "root_permit_sha256": binding["root_permit_sha256"],
        "capture_actor": binding["actor"],
    }
    _require(all(parent.get(k) == value for k, value in expected.items()))
    _require(raw["effect_id"] == go["capture_effect_id"])
    for key in ("helper_exit_code", "active_owned_processes"):
        _require(type(parent[key]) is int and parent[key] == 0)
    _require(
        parent["owned_fds_closed"] is True
        and parent["force_killed"] is False
        and parent["resource_limit_event"] is False
    )
    elapsed = parent["elapsed_seconds"]
    _require(type(elapsed) in (int, float) and math.isfinite(elapsed) and 0 <= elapsed <= 480)
    _require(isinstance(parent["executor_actor"], dict) and bool(parent["executor_actor"]))
    evidence = [daily.ObjectRef.model_validate(r) for r in acceptance["parent_evidence_refs"]]
    _require(1 <= len(evidence) <= 8 and len(evidence) == len(parent["evidence_refs"]))
    _require([r.digest for r in evidence] == [r["sha256"] for r in parent["evidence_refs"]])
    refs = [parent_ref, *evidence, *_capture_refs(raw)]
    for ref in refs:
        daily.NativeDailyService._from_store(store, ref)
    return parent_ref, refs


def _verify(store, package_ref, proofs, *, executing):
    from quantmesh.research import native_daily_candidate as native

    proofs = TrustedIVVProofs.model_validate(proofs)
    originals = {}
    for key in ORIGINAL_PINS:
        ref = getattr(proofs, key + "_ref")
        _require(ref.digest == ORIGINAL_PINS[key])
        originals[key] = _load(store, ref)
    _require(originals["scope"]["selection"]["asset"] == "US.IVV")
    _require(originals["effect"]["scope_approval_sha256"] == proofs.scope_ref.digest)
    _require(originals["effect"]["paper_live"] is False)
    _require(originals["execution"]["approval_sha256"] == proofs.effect_ref.digest)
    fixed = originals["execution"]["fixed_scope"]
    _require(fixed["asset"] == "US.IVV" and fixed["scope_id"] == SCOPE_ID)
    _require(fixed["input_window_digest"] == daily.digest(daily.canonical(WINDOW)))
    from quantmesh.research.ivv_runtime import WINDOWS_POLICY_SHA

    policy = _load(store, proofs.windows_policy_ref)
    _require(proofs.windows_policy_ref.digest == WINDOWS_POLICY_SHA)
    _require(policy["planning_scope_id"] == SCOPE_ID)
    _require(policy["full_execution_approval_sha256"] == proofs.effect_ref.digest)
    _require(proofs.go_ref.digest == proofs.expected_go_sha256)
    _require(proofs.acceptance_ref.digest == proofs.expected_acceptance_sha256)
    go, acceptance = _load(store, proofs.go_ref), _load(store, proofs.acceptance_ref)
    package = _load(store, package_ref)
    manifest = daily.RealInput.model_validate(package)
    _require(manifest.evidence_kind == "reviewed_real")
    _require(manifest.instrument == "US.IVV" and manifest.source_id == SOURCE_ID)
    _require(manifest.source_use == SOURCE_USE)
    _require(manifest.window.model_dump(mode="json") == WINDOW)
    _require(manifest.sample_role == "development_only_retrospective")
    _require(manifest.calendar_version == "exchange-calendars:4.13.2:XNYS")
    reviews = {ref.digest for ref in manifest.review_refs}
    _require(
        all(
            getattr(proofs, name).digest in reviews
            for name in (
                "scope_ref",
                "effect_ref",
                "execution_ref",
                "go_ref",
                "acceptance_ref",
                "windows_policy_ref",
            )
        )
    )
    _require(go["schema_id"] == "qm.ivv.root-go.v1")
    _require(go["decision"] == "GO_ONCE_AFTER_INPUT_ACCEPTANCE" and go["scope_id"] == SCOPE_ID)
    _require(go["execution_sha256"] == proofs.execution_ref.digest)
    _require(go["input_window_digest"] == fixed["input_window_digest"])
    _require(go["full_window_sha256"] == WINDOW_SHA)
    _require(type(go["max_trials"]) is int and go["max_trials"] == 1)
    _require(type(go["max_capture_intents"]) is int and go["max_capture_intents"] == 1)
    _require(
        all(
            go["controls"].get(key) is True
            for key in ("released", "resource_bounds", "provider_log_cache_bounds")
        )
    )
    daily._uuid(go["job_id"])
    _require(policy["planning_job_uuid"] == go["job_id"])
    _require(go["windows_policy_sha256"] == proofs.windows_policy_ref.digest)
    if executing:
        _require(go["code"] == native._code())
        _require(go["adapter_sha256"] == daily.digest(Path(daily.__file__).read_bytes()))
        _require(go["gate_sha256"] == daily.digest(Path(__file__).read_bytes()))
        _require(go["runtime"] == daily.runtime_versions())
    _require(acceptance["schema_id"] == "qm.ivv.input-acceptance.v1")
    _require(acceptance["decision"] == "ACCEPT_FOR_ONE_DECLARED_RETROSPECTIVE_RESEARCH")
    _require(acceptance["reviewer"] == REVIEWER and acceptance["scope_id"] == SCOPE_ID)
    _require(acceptance["input_set_digest"] == input_set_digest(package))
    _require(all(acceptance["checks"].get(key) is True for key in INPUT_CHECKS))
    _require(acceptance["financial_qualification"] == "INSUFFICIENT")
    _require(acceptance["paper_allowed"] is False and acceptance["live_allowed"] is False)
    raw_ref = daily.ObjectRef.model_validate(acceptance["capture_ref"])
    _require(raw_ref in manifest.source_asset_refs)
    parent_ref, _ = _capture_close(store, raw_ref, acceptance, go, proofs)
    source = _load(store, acceptance["source_facts_ref"])
    _require(source["schema_id"] == "qm.ivv.source-facts.v1")
    _require(
        source["currency"] == manifest.currency and source["volume_unit"] == manifest.volume_unit
    )
    _require(source["historical_trade_venues"] == manifest.historical_trade_venues)
    _require(source["action_coverage"] == manifest.action_coverage)
    _require(isinstance(source["basis"], str) and bool(source["basis"].strip()))
    exposure, ledger = _load(store, manifest.exposure_ref), _load(store, manifest.trial_ledger_ref)
    _require(exposure["scope_id"] == SCOPE_ID and exposure["unseen_oos"] is False)
    _require(exposure["sample_role"] == manifest.sample_role)
    _require(ledger["scope_id"] == SCOPE_ID and ledger["trial_id"] == "qm-ivv-trial-" + SCOPE_ID)
    _require(type(ledger["max_trials"]) is int and ledger["max_trials"] == 1)
    _require(ledger["state"] == "UNRESERVED")
    return {
        "scope_id": SCOPE_ID,
        "scope_trial_key": daily.digest(
            daily.canonical(
                {
                    "execution": proofs.execution_ref.digest,
                    "scope": SCOPE_ID,
                    "trial": 1,
                }
            )
        ),
        "job_id": go["job_id"],
        "output_root_digest": go["output_root_digest"],
        "proofs": proofs.model_dump(mode="json"),
        "source_facts_ref": acceptance["source_facts_ref"],
        "capture_ref": raw_ref.model_dump(),
        "parent_close_ref": parent_ref.model_dump(),
        "source_use": SOURCE_USE,
        "provider_permission_verified": False,
        "external_API_retention_applicability": "UNKNOWN",
    }


def register_ivv_input(store, *, package_ref, grant_ref, approved_scope_ref, authority_ref, proofs):
    """One operator-configured real registration, after independent acceptance."""
    try:
        evidence = _verify(store, package_ref, proofs, executing=True)
        scope = _load(store, approved_scope_ref)
        _require(scope["output_root_digest"] == evidence["output_root_digest"])
        registration = daily.register_bound_input(
            store,
            package_ref=package_ref,
            grant_ref=grant_ref,
            approved_scope_ref=approved_scope_ref,
            authority_ref=authority_ref,
        )
        record = {"schema_id": "qm.ivv.registration.v1", **evidence}
        binding = store.put_bytes("application/json", daily.canonical(record))
        return replace(registration, _authority=_REAL_AUTHORITY, real_binding=binding)
    except (KeyError, TypeError, ValueError, OSError, RecursionError):
        raise daily.NativeError("ivv_not_admitted") from None


def verify_saved_binding(store, package_ref, binding_ref, *, executing):
    """Cold reads validate stored authority bytes, not today's runtime/calendar."""
    record = _load(store, binding_ref)
    _require(record.pop("schema_id") == "qm.ivv.registration.v1")
    checked = _verify(store, package_ref, record["proofs"], executing=executing)
    _require(record == checked)
    return checked


def binding_objects(store, binding_ref):
    record = _load(store, binding_ref)
    proofs = TrustedIVVProofs.model_validate(record["proofs"])
    _, capture_refs = _capture_close(
        store,
        daily.ObjectRef.model_validate(record["capture_ref"]),
        _load(store, proofs.acceptance_ref),
        _load(store, proofs.go_ref),
        proofs,
    )
    refs = [
        binding_ref,
        *[
            getattr(proofs, key)
            for key in (
                "scope_ref",
                "effect_ref",
                "execution_ref",
                "go_ref",
                "acceptance_ref",
                "windows_policy_ref",
            )
        ],
        daily.ObjectRef.model_validate(record["source_facts_ref"]),
        *capture_refs,
    ]
    return [(ref, daily.NativeDailyService._from_store(store, ref)) for ref in refs]


def _put(store, value):
    raw = daily.canonical(value)
    _require(0 < len(raw) <= daily.MAX_OBJECT)
    return store.put_bytes("application/json", raw)


def stage_ivv_input_set(
    store, *, normalized, source_facts, capture_ref, exposure_ref, trial_ledger_ref
):
    """Publish an unreviewed input-set, never a grant or a runnable package."""
    try:
        _require(normalized["status"] == "NORMALIZED_UNREVIEWED")
        _require(len(normalized["bars"]) == 121 and len(normalized["schedule"]) == 121)
        text = io.StringIO(newline="")
        names = ["date", "open", "high", "low", "close", "volume", "dividend"]
        writer = csv.DictWriter(text, fieldnames=names, lineterminator="\n")
        writer.writeheader()
        for row in normalized["bars"]:
            _require(set(row) == set(names))
            writer.writerow(row)
        bars = text.getvalue().encode()
        _require(len(bars) <= daily.MAX_OBJECT)
        inputs = {
            "bars": store.put_bytes("text/csv", bars).model_dump(),
            "distributions": _put(store, normalized["distributions"]).model_dump(),
            "schedule": _put(store, normalized["schedule"]).model_dump(),
        }
        _require(source_facts["currency"] == "USD" and source_facts["volume_unit"] == "shares")
        _require(source_facts["action_coverage"] == "complete_cash_ex_pay_no_splits")
        _require(bool(source_facts["historical_trade_venues"].strip()))
        facts = {
            "schema_id": "qm.native-daily.real-input.v1",
            "candidate": daily.CANDIDATE,
            "evidence_kind": "reviewed_real",
            "inputs": inputs,
            "instrument": "US.IVV",
            "source_id": SOURCE_ID,
            "source_use": SOURCE_USE,
            "currency": "USD",
            "price_adjustment": "raw",
            "volume_unit": "shares",
            "historical_trade_venues": source_facts["historical_trade_venues"],
            "action_coverage": source_facts["action_coverage"],
            "calendar_id": "XNYS",
            "calendar_timezone": "America/New_York",
            "calendar_version": "exchange-calendars:4.13.2:XNYS",
            "availability_assumption": "completed_close_plus30min_assumed",
            "pit_status": source_facts["pit_status"],
            "revision_note": source_facts["revision_note"],
            "source_asset_refs": [daily.ObjectRef.model_validate(capture_ref).model_dump()],
            "window": WINDOW,
            "sample_role": "development_only_retrospective",
            "exposure_ref": daily.ObjectRef.model_validate(exposure_ref).model_dump(),
            "trial_ledger_ref": daily.ObjectRef.model_validate(trial_ledger_ref).model_dump(),
        }
        # The facts describe the target manifest. Without review refs this is
        # deliberately NOT a RealInput or a trusted registration.
        return _put(
            store,
            {
                "schema_id": "qm.ivv.unreviewed-input-set.v1",
                "facts": facts,
                "input_set_digest": input_set_digest(facts),
            },
        )
    except (KeyError, TypeError, ValueError, OSError, AttributeError):
        raise daily.NativeError("ivv_not_admitted") from None


def bind_reviewed_ivv_input(store, *, input_set_ref, proofs, output_root):
    """Bind already accepted facts to existing internal scope/grant contracts."""
    try:
        staged = _load(store, input_set_ref)
        _require(staged["schema_id"] == "qm.ivv.unreviewed-input-set.v1")
        _require(staged["input_set_digest"] == input_set_digest(staged["facts"]))
        proofs = TrustedIVVProofs.model_validate(proofs)
        facts = dict(staged["facts"])
        _require("review_refs" not in facts)
        facts["review_refs"] = [
            getattr(proofs, key).model_dump()
            for key in (
                "acceptance_ref",
                "scope_ref",
                "effect_ref",
                "execution_ref",
                "go_ref",
                "windows_policy_ref",
            )
        ]
        package_ref = _put(store, facts)
        checked = _verify(store, package_ref, proofs, executing=True)
        _require(checked["output_root_digest"] == daily._root_pin(output_root))
        manifest = daily.RealInput.model_validate(facts)
        scope = {
            "schema_id": "qm.native-daily.research-scope.v1",
            "candidate": daily.CANDIDATE,
            "package_ref": package_ref.model_dump(),
            "source_id": manifest.source_id,
            "source_use": manifest.source_use,
            "instrument": manifest.instrument,
            "window_digest": daily.digest(daily.canonical(facts["window"])),
            "sample_role": manifest.sample_role,
            "exposure_ref": facts["exposure_ref"],
            "trial_ledger_ref": facts["trial_ledger_ref"],
            "output_root_digest": checked["output_root_digest"],
        }
        scope_ref = _put(store, scope)
        authority_ref = _put(
            store,
            {
                "schema_id": "qm.native-daily.scope-authority.v1",
                "candidate": daily.CANDIDATE,
                "approved_scope_ref": scope_ref.model_dump(),
                "review_refs": facts["review_refs"],
                "decision": "APPROVED_DECLARED_RESEARCH",
            },
        )
        grant_ref = _put(
            store,
            {
                **scope,
                "schema_id": "qm.native-daily.bound-grant.v1",
                "approved_scope_ref": scope_ref.model_dump(),
                "authority_ref": authority_ref.model_dump(),
                "max_trials": 1,
            },
        )
        return register_ivv_input(
            store,
            package_ref=package_ref,
            grant_ref=grant_ref,
            approved_scope_ref=scope_ref,
            authority_ref=authority_ref,
            proofs=proofs,
        )
    except (KeyError, TypeError, ValueError, OSError, RecursionError):
        raise daily.NativeError("ivv_not_admitted") from None
