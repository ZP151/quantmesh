"""One private diagnostic exception; no public enrollment or permission registry."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.objects import ObjectRef, ObjectStore, is_reparse_point

HUMAN_DECISION_SHA256 = "ff2d3886c07504854a6ece89f4029177d51182eb7f99b33354b6268610b9b2c9"
POLICY_DOCUMENT_SHA256 = "91cf0c560cadab5f80a3421604fa90b0ad5e7dc6b7ae5492058cb4013f2ccd36"
PROPOSAL_SHA256 = "aafd036f8e5402a14cb0c2a85421a27ab98cc69180e693c6ab8d4f8bbd7ead13"
MAX_PROOF = 16384
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


def canonical(value):
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")
    if len(raw) > MAX_PROOF:
        raise ValueError("policy_proof_too_large")
    return raw


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def loads(raw):
    if len(raw) > MAX_PROOF:
        raise ValueError("policy_proof_too_large")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("policy_duplicate_key")
            result[key] = value
        return result

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("policy_nonfinite")),
    )


def job_key(scope):
    return str(uuid5(NAMESPACE_URL, "quantmesh:spy-private-diagnostic-once:" + scope))


def root_pin(root):
    return sha(str(Path(root).resolve()).encode("utf-8"))


class OnceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    schema_version: Literal[3]
    policy_status: Literal["POLICY_EXCEPTION_ONCE"]
    internal_once_exception: Literal["HUMAN_APPROVED"]
    provider_permission_verified: Literal[False]
    internal_decision: Literal["APPROVE_ONCE_PRIVATE_DIAGNOSTIC_EXCEPTION"]
    external_api_storage_applicability: Literal["UNKNOWN"]
    diagnostic_status: Literal["diagnostic_only_under_policy_exception"]
    scope: Literal["US.SPY/1d/private_research"]
    once_scope_id: Digest
    proposal_sha256: Digest
    capture_intent_id: str
    job_idempotency_key: str
    window_sha256: Digest
    output_root_sha256: Digest
    authority_root_sha256: Digest
    human_approval_ref: ObjectRef
    policy_document_ref: ObjectRef

    @field_validator("provider_permission_verified", mode="before")
    @classmethod
    def exact_false(cls, value):
        if value is not False:
            raise ValueError("external_permission_not_verified")
        return value

    @model_validator(mode="after")
    def bound(self):
        if (
            self.once_scope_id != HUMAN_DECISION_SHA256
            or self.human_approval_ref.digest != HUMAN_DECISION_SHA256
            or self.policy_document_ref.digest != POLICY_DOCUMENT_SHA256
            or self.proposal_sha256 != PROPOSAL_SHA256
            or self.job_idempotency_key != job_key(self.once_scope_id)
            or str(UUID(self.capture_intent_id)) != self.capture_intent_id
            or any(
                value == "0" * 64
                for value in (
                    self.window_sha256,
                    self.output_root_sha256,
                    self.authority_root_sha256,
                )
            )
        ):
            raise ValueError("policy_binding_invalid")
        for ref, media in (
            (self.human_approval_ref, "application/json"),
            (self.policy_document_ref, "text/markdown"),
        ):
            if not 1 <= ref.byte_length <= MAX_PROOF or ref.media_type != media:
                raise ValueError("policy_proof_invalid")
        return self


def verify_authority(binding, store):
    try:
        b = OnceBinding.model_validate(binding)
        approval = loads(_proof_bytes(store, b.human_approval_ref))
        _proof_bytes(store, b.policy_document_ref)
        if (
            approval.get("status") != "HUMAN_APPROVED_ONCE"
            or approval.get("proposal_sha256") != PROPOSAL_SHA256
            or approval.get("internal_decision") != b.internal_decision
            or approval.get("actual_data_math_budget_gates") != "UNCHANGED"
            or approval.get("explicit_prohibition") != "STOP if established"
        ):
            raise ValueError
        return b
    except Exception:
        raise ValueError("policy_authority_invalid") from None


def _safe(root):
    path = Path(root).absolute()
    if any(is_reparse_point(p) for p in (path, *path.parents)):
        raise ValueError("policy_path_invalid")
    return path


def _proof_bytes(store, ref):
    path = _safe(store.path_for(ref))
    if not 1 <= ref.byte_length <= MAX_PROOF or path.stat().st_size != ref.byte_length:
        raise ValueError("policy_proof_invalid")
    return store.get_bytes(ref)


def _configured_authority(binding):
    """The operator fixes this private location independently of authorization JSON."""
    configured = os.environ.get("QUANTMESH_SPY_ONCE_AUTHORITY_ROOT")
    if not configured:
        raise ValueError("once_authority_unconfigured")
    root = _safe(configured)
    if root_pin(root) != binding.authority_root_sha256:
        raise ValueError("once_authority_mismatch")
    return root


def consume_once(binding, authorization, authority_root, output_root, at):
    """A canonical scope filename consumes even failed/uncertain attempts; never reset."""
    b = verify_authority(binding, ObjectStore(_safe(output_root)))
    authority_root, output_root = _safe(authority_root), _safe(output_root)
    configured = _configured_authority(b)
    if (
        root_pin(authority_root) != b.authority_root_sha256
        or root_pin(authority_root) != root_pin(configured)
        or root_pin(output_root) != b.output_root_sha256
        or at.utcoffset() != UTC.utcoffset(at)
        or authorization.get("policy_exception") != b.model_dump(mode="json")
    ):
        raise ValueError("policy_intent_invalid")
    authority_root.mkdir(parents=True, exist_ok=True)
    marker = dict(
        schema_version=3,
        policy_exception=b.model_dump(mode="json"),
        authorization_sha256=sha(canonical(authorization)),
        consumed_at_utc=at.isoformat(),
    )
    raw = canonical(marker)
    try:
        with (authority_root / f"capture-intent-{b.once_scope_id}.json").open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError:
        raise ValueError("once_scope_consumed") from None
    # Publication failure after consumption never refunds the canonical marker.
    return ObjectStore(output_root).put_bytes("application/json", raw).model_dump(mode="json")


def verify_intent(binding, authorization, ref, store, *, require_live_marker=False):
    b = verify_authority(binding, store)
    reference = ObjectRef.model_validate(ref)
    if reference.media_type != "application/json" or not 1 <= reference.byte_length <= MAX_PROOF:
        raise ValueError("policy_intent_invalid")
    raw = _proof_bytes(store, reference)
    marker = loads(raw)
    if (
        set(marker)
        != {"schema_version", "policy_exception", "authorization_sha256", "consumed_at_utc"}
        or type(marker["schema_version"]) is not int
        or marker["schema_version"] != 3
        or marker["policy_exception"] != b.model_dump(mode="json")
        or marker["authorization_sha256"] != sha(canonical(authorization))
        or datetime.fromisoformat(marker["consumed_at_utc"]).utcoffset() != UTC.utcoffset(None)
    ):
        raise ValueError("policy_intent_invalid")
    if require_live_marker:
        root = _configured_authority(b)
        path = root / f"capture-intent-{b.once_scope_id}.json"
        _safe(path)
        if path.stat().st_size != len(raw) or path.read_bytes() != raw:
            raise ValueError("policy_intent_invalid")
    return marker
