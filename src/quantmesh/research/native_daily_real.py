"""Fixed candidate workstation records; no public data or grant qualification."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import threading
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.objects import ObjectRef, ObjectStore, is_reparse_point
from quantmesh.ops.paper_controls import WriterLease
from quantmesh.persistence.jsonl import JsonlStore

CANDIDATE = "doublema_daily_overlay_candidate_v1"
KERNEL = "native-daily-v2"
MAX_OBJECT = 1024 * 1024
MAX_JOBS = 32
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
_ENGINEERING_AUTHORITY = object()


class NativeError(ValueError):
    """A fixed public failure code."""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def _uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise NativeError("invalid_request") from None


def _now():
    return datetime.now(UTC).isoformat()


def _loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    return json.loads(
        raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError())
    )


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NativeRequest(Contract):
    candidate: Literal["doublema_daily_overlay_candidate_v1"] = CANDIDATE
    package_ref: ObjectRef | None = None
    grant_ref: ObjectRef | None = None
    approved_scope_ref: ObjectRef | None = None
    protocol_ref: ObjectRef | None = None


class InputWindow(Contract):
    warmup_start: date
    score_start: date
    score_end: date
    warmup: Literal[100] = 100
    observations: Literal[21] = 21

    @field_validator("warmup", "observations", mode="before")
    @classmethod
    def integer_counts(cls, value):
        if type(value) is not int:
            raise ValueError("window_counts")
        return value

    @model_validator(mode="after")
    def ordered(self):
        if not self.warmup_start < self.score_start <= self.score_end:
            raise ValueError("window_order")
        return self


class InputObjects(Contract):
    bars: ObjectRef
    distributions: ObjectRef
    schedule: ObjectRef


class RealInput(Contract):
    """Source facts and objects; validity is not an execution permission."""

    schema_id: Literal["qm.native-daily.real-input.v1"]
    candidate: Literal["doublema_daily_overlay_candidate_v1"]
    evidence_kind: Literal["engineering_fixture", "reviewed_real"]
    inputs: InputObjects
    instrument: str = Field(min_length=1, max_length=80)
    source_id: str = Field(min_length=1, max_length=160)
    source_use: str = Field(min_length=1, max_length=160)
    currency: Literal["USD"]
    price_adjustment: Literal["raw"]
    volume_unit: Literal["shares"]
    historical_trade_venues: str = Field(min_length=1, max_length=1000)
    action_coverage: Literal["complete_cash_ex_pay_no_splits"]
    calendar_id: Literal["XNYS"]
    calendar_timezone: Literal["America/New_York"]
    calendar_version: str = Field(min_length=1, max_length=160)
    availability_assumption: Literal["completed_close_plus30min_assumed"]
    pit_status: Literal["known", "unknown"]
    revision_note: str = Field(min_length=1, max_length=1000)
    review_refs: list[ObjectRef] = Field(min_length=1, max_length=8)
    source_asset_refs: list[ObjectRef] = Field(min_length=1, max_length=8)
    window: InputWindow
    sample_role: str = Field(min_length=1, max_length=80)
    exposure_ref: ObjectRef
    trial_ledger_ref: ObjectRef

    @field_validator(
        "instrument",
        "source_id",
        "source_use",
        "historical_trade_venues",
        "calendar_version",
        "revision_note",
        "sample_role",
    )
    @classmethod
    def nonblank_facts(cls, value):
        if not value.strip():
            raise ValueError("input_fact_missing")
        return value.strip()

    @model_validator(mode="after")
    def preserves_input_bounds(self):
        references = [
            *self.review_refs,
            *self.source_asset_refs,
            self.exposure_ref,
            self.trial_ledger_ref,
            *self.inputs.model_dump().values(),
        ]
        for ref in references:
            reference = ref if isinstance(ref, ObjectRef) else ObjectRef.model_validate(ref)
            if not 1 <= reference.byte_length <= MAX_OBJECT:
                raise ValueError("input_object_bounds")
            if (
                reference.digest
                == "d882c232ed68666ea35d1d3876470bcc60853c6f7678d281cda9403a58e3d9ae"
            ):
                raise ValueError("consumed_source_not_transferable")
        if self.inputs.bars.media_type != "text/csv" or any(
            ref.media_type != "application/json"
            for ref in (self.inputs.distributions, self.inputs.schedule)
        ):
            raise ValueError("input_media")
        return self


class ResearchScope(Contract):
    schema_id: Literal["qm.native-daily.research-scope.v1"]
    candidate: Literal["doublema_daily_overlay_candidate_v1"]
    package_ref: ObjectRef
    source_id: str
    source_use: str
    instrument: str
    window_digest: Digest
    sample_role: str
    exposure_ref: ObjectRef
    trial_ledger_ref: ObjectRef
    output_root_digest: Digest


class BoundGrant(ResearchScope):
    schema_id: Literal["qm.native-daily.bound-grant.v1"]
    approved_scope_ref: ObjectRef
    authority_ref: ObjectRef
    max_trials: Literal[1]

    @field_validator("max_trials", mode="before")
    @classmethod
    def exact_one(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("trial_limit")
        return value


class NativeDecisionRequest(Contract):
    request_digest: Digest
    admission_digest: Digest
    report_digest: Digest | None = None
    disposition: Literal["reject", "watch"]
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def trimmed(cls, value):
        if not value.strip():
            raise ValueError("reason required")
        return value.strip()


class ComputeAttempt(Contract):
    """One durable local execution, distinct from an SDK or research experiment."""

    attempt_id: str
    sequence: Annotated[int, Field(strict=True, ge=1)]
    state: Literal["running", "failed", "interrupted", "prepared", "committed"]
    request: NativeRequest
    request_digest: Digest
    admission: ObjectRef
    real_binding: ObjectRef | None = None
    policy: dict
    provenance: dict
    started_at: str
    completed_at: str | None = None
    failure_code: Literal["COMPUTE_FAILED", "EXECUTION_INTERRUPTED"] | None = None
    report: ObjectRef | None = None


class ResearchTransaction(Contract):
    identity: dict[str, str]
    attempts: list[ComputeAttempt] = Field(min_length=1)
    prepared_report: ObjectRef | None = None


class NativeJob(Contract):
    job_id: str
    request: NativeRequest
    request_digest: Digest
    state: Literal["not_run", "running", "succeeded", "failed", "interrupted"]
    admission_status: Literal[
        "INSUFFICIENT", "REJECT", "ACCEPTED_ENGINEERING", "ACCEPTED_DECLARED_RESEARCH"
    ]
    admission: ObjectRef
    report: ObjectRef | None = None
    decision: ObjectRef | None = None
    decision_key: str | None = None
    consumed_grant: Digest | None = None
    scope_trial_key: Digest | None = None
    real_binding: ObjectRef | None = None
    transaction: ResearchTransaction | None = None
    created_at: str
    completed_at: str | None = None
    financial_qualification: Literal["INSUFFICIENT"] = "INSUFFICIENT"
    paper_allowed: Literal[False] = False
    live_allowed: Literal[False] = False


def _root_pin(root):
    return digest(str(Path(root).absolute()).encode())


@dataclass(frozen=True)
class RegisteredInput:
    """Trusted local registration, not an HTTP input or a provider permission."""

    store: ObjectStore
    package_ref: ObjectRef
    grant_ref: ObjectRef
    approved_scope_ref: ObjectRef
    protocol_ref: ObjectRef
    _authority: object = field(default=None, repr=False, compare=False)
    authority_ref: ObjectRef | None = None
    real_binding: ObjectRef | None = None
    recovery: dict | None = field(default=None, repr=False, compare=False)

    @property
    def request(self):
        return NativeRequest(
            package_ref=self.package_ref,
            grant_ref=self.grant_ref,
            approved_scope_ref=self.approved_scope_ref,
            protocol_ref=self.protocol_ref,
        )


def _accounting_contract():
    from quantmesh.research import native_daily_candidate as native

    contract = native._contract("schema_only_not_data", {}, {}, {})
    result = {
        key: contract[key] for key in ("rules", "costs", "arms", "benchmark100_cap_exception")
    }
    result["window"] = {
        key: value for key, value in contract["window"].items() if key != "timestamps"
    }
    return result


def runtime_versions():
    from quantmesh.research import native_daily_candidate as native

    return {
        "python": native.platform.python_version(),
        "pandas": native.pd.__version__,
        "numpy": native.engine.np.__version__,
        "calendar": f"{version('exchange-calendars')} / {native.XNYS_REGULAR_VERSION}",
    }


def register_bound_input(store, *, package_ref, grant_ref, approved_scope_ref, authority_ref):
    """Trusted configuration seam. It binds existing proofs; never mints a grant."""
    from quantmesh.research import native_daily_candidate as native

    manifest = RealInput.model_validate(_loads(NativeDailyService._from_store(store, package_ref)))
    protocol = {
        "schema_id": "qm.native-daily.real-protocol.v3",
        "candidate": CANDIDATE,
        "kernel": KERNEL,
        "evidence_kind": manifest.evidence_kind,
        "package_ref": package_ref.model_dump(),
        "grant_ref": grant_ref.model_dump(),
        "approved_scope_ref": approved_scope_ref.model_dump(),
        "authority_ref": authority_ref.model_dump(),
        "accounting_contract": _accounting_contract(),
        "code": native._code(),
        "runtime": runtime_versions(),
        "adapter_sha256": digest(Path(__file__).read_bytes()),
        "financial_qualification": "INSUFFICIENT",
        "paper_allowed": False,
        "live_allowed": False,
    }
    protocol_ref = store.put_bytes("application/json", canonical(protocol))
    return RegisteredInput(
        store,
        package_ref,
        grant_ref,
        approved_scope_ref,
        protocol_ref,
        _ENGINEERING_AUTHORITY,
        authority_ref,
    )


def engineering_registration(store: ObjectStore, *, output_root):
    """Explicit engineering substitute only; never called by a request/default startup."""
    from quantmesh.research import native_daily_candidate as native

    value = native.engineering_input()
    original_protocol = native.freeze_protocol(value)
    inputs = {
        name: store.put_bytes(media, raw).model_dump()
        for name, media, raw in (
            ("bars", "text/csv", value.bars_csv),
            ("distributions", "application/json", value.distributions_json),
            ("schedule", "application/json", value.schedule_json),
        )
    }
    original_ref = store.put_bytes("application/json", original_protocol)
    package = {
        "schema_id": "qm.native-daily.input.v1",
        "candidate": CANDIDATE,
        "kernel": KERNEL,
        "evidence_kind": "engineering_fixture",
        "inputs": inputs,
        "engineering_protocol_ref": original_ref.model_dump(),
        "source_use": "synthetic_no_vendor",
        "real_input_enabled": False,
    }
    package_ref = store.put_bytes("application/json", canonical(package))
    scope = {
        "schema_id": "qm.native-daily.offline-scope.v1",
        "candidate": CANDIDATE,
        "package_ref": package_ref.model_dump(),
        "output_root_digest": _root_pin(output_root),
        "purpose": "offline_engineering_only",
        "real_data_authorized": False,
    }
    scope_ref = store.put_bytes("application/json", canonical(scope))
    grant = {
        "schema_id": "qm.native-daily.candidate-grant.v1",
        "candidate": CANDIDATE,
        "package_ref": package_ref.model_dump(),
        "approved_scope_ref": scope_ref.model_dump(),
        "output_root_digest": _root_pin(output_root),
        "purpose": "offline_engineering_only",
        "max_trials": 1,
        "real_data_authorized": False,
    }
    grant_ref = store.put_bytes("application/json", canonical(grant))
    protocol = {
        "schema_id": "qm.native-daily.real-protocol.v1",
        "candidate": CANDIDATE,
        "kernel": KERNEL,
        "evidence_kind": "engineering_fixture",
        "package_ref": package_ref.model_dump(),
        "grant_ref": grant_ref.model_dump(),
        "approved_scope_ref": scope_ref.model_dump(),
        "engineering_protocol_ref": original_ref.model_dump(),
        "adapter_sha256": digest(Path(__file__).read_bytes()),
        "financial_qualification": "INSUFFICIENT",
        "paper_allowed": False,
        "live_allowed": False,
    }
    protocol_ref = store.put_bytes("application/json", canonical(protocol))
    return RegisteredInput(
        store, package_ref, grant_ref, scope_ref, protocol_ref, _ENGINEERING_AUTHORITY
    )


# Strong references keep an uncertain exact owner and its WriterLease alive even
# if a caller drops the service. Entries are removed only after terminal cleanup.
_UNCERTAIN_OWNER_ROOTS = {}


class NativeDailyService:
    """One durable writer, fixed candidate, explicit missing-input decisions."""

    def __init__(self, root: Path, *, registered=(), real_runtime_factory=None):
        self.root = Path(root).absolute()
        for path in (self.root, *self.root.parents):
            if is_reparse_point(path):
                raise NativeError("unsafe_storage")
        prior_owner = _UNCERTAIN_OWNER_ROOTS.get(str(self.root))
        if prior_owner is not None:
            prior_owner.close()  # Exact known owner only, before acquiring another lease.
        self._condition = threading.Condition(threading.RLock())
        self._closed = False
        self._closing = False
        self._inflight = None
        self._registered = tuple(registered)
        self._real_runtime_factory = real_runtime_factory
        self._real_runtimes = {}
        self._cleanup_pending = {}
        self._durable_recovery = any(r.recovery is not None for r in self._registered)
        if self._durable_recovery:
            from quantmesh._fs import durable_mkdir

            durable_mkdir(self.root)
        self.objects = ObjectStore(self.root, durable=self._durable_recovery)
        self._lease = WriterLease(self.root / ".writer.lock")
        self._store = JsonlStore(
            self.root,
            filename="jobs.jsonl",
            model=NativeJob,
            label="native daily",
            id_label="job",
            key=lambda job: job.job_id,
            secondary_keys=(
                ("consumed grant", lambda job: job.consumed_grant),
                ("scope trial", lambda job: job.scope_trial_key),
            ),
        )
        try:
            jobs = self._records()
            if any(j.transaction is not None for j in jobs):
                self._durable_recovery = self.objects.durable = self._store.durable = True
                self._publish_records(jobs)  # Cold barrier before any prepared commit/effect.
            changed = []
            for job in jobs:
                if job.state == "running":
                    if job.transaction is not None:
                        job = (
                            self._committed_transaction(job)
                            if job.transaction.prepared_report
                            else self._interrupted_transaction(job)
                        )
                    else:
                        job = job.model_copy(
                            update={"state": "interrupted", "completed_at": _now()}
                        )
                changed.append(job)
            if changed != jobs:
                self._publish_records(changed)
        except BaseException:
            self._lease.close()
            raise

    @staticmethod
    def _recovery_metadata(registration):
        """Only trusted startup registrations carry recovery policy, never HTTP."""
        if registration.recovery is None:
            return None
        from quantmesh.research import ivv_recovery as recovery

        value = registration.recovery
        if set(value) != {"recovery_identity", "attempt_policy", "recovery_provenance"}:
            raise NativeError("study_not_admitted")
        identity = recovery.validate_identity(value["recovery_identity"])
        policy = value["attempt_policy"]
        if (
            set(policy) != {"policy_ref", "batch_id", "max_numerical_attempts"}
            or type(policy["max_numerical_attempts"]) is not int
            or policy["max_numerical_attempts"] < 1
            or not isinstance(policy["batch_id"], str)
            or not policy["batch_id"]
        ):
            raise NativeError("study_not_admitted")
        policy_ref = ObjectRef.model_validate(policy["policy_ref"])
        actual_policy = recovery.validate_policy(
            _loads(NativeDailyService._from_store(registration.store, policy_ref))
        )
        recovery.validate_attempt_policy(policy, actual_policy)
        if identity["math_cost_spec"] != digest(canonical(_accounting_contract())):
            raise NativeError("study_not_admitted")
        provenance = value["recovery_provenance"]
        if set(provenance) != {"input_manifest_ref", "capture_attempt_refs"}:
            raise NativeError("study_not_admitted")
        ObjectRef.model_validate(provenance["input_manifest_ref"])
        if not isinstance(provenance["capture_attempt_refs"], list):
            raise NativeError("study_not_admitted")
        for ref in provenance["capture_attempt_refs"]:
            ObjectRef.model_validate(ref)
        return {**value, "recovery_identity": identity}

    @staticmethod
    def _transaction_job_id(identity):
        from quantmesh.research import ivv_recovery as recovery

        return recovery.logical_job_id(identity)

    def _verify_transaction(self, job):
        from quantmesh.research import ivv_recovery as recovery

        tx = job.transaction
        identity = recovery.validate_identity(tx.identity)
        if (
            job.job_id != self._transaction_job_id(identity)
            or job.scope_trial_key != identity["business_key"]
            or len({a.attempt_id for a in tx.attempts}) != len(tx.attempts)
        ):
            raise ValueError("transaction_identity")
        last = tx.attempts[-1]
        for sequence, attempt in enumerate(tx.attempts, 1):
            if (
                _uuid(attempt.attempt_id) != attempt.attempt_id
                or attempt.sequence != sequence
                or digest(canonical(attempt.request.model_dump(mode="json")))
                != attempt.request_digest
                or attempt.policy["max_numerical_attempts"] < sequence
                or type(attempt.policy["max_numerical_attempts"]) is not int
                or (sequence < len(tx.attempts) and attempt.state not in {"failed", "interrupted"})
                or (attempt.state in {"prepared", "committed"}) != (attempt.report is not None)
                or (attempt.completed_at is None) != (attempt.state in {"running", "prepared"})
                or attempt.failure_code
                != {"failed": "COMPUTE_FAILED", "interrupted": "EXECUTION_INTERRUPTED"}.get(
                    attempt.state
                )
            ):
                raise ValueError("transaction_attempt")
            for ref in [
                attempt.policy["policy_ref"],
                attempt.provenance["input_manifest_ref"],
                *attempt.provenance["capture_attempt_refs"],
            ]:
                self._object(ObjectRef.model_validate(ref))
            policy_ref = ObjectRef.model_validate(attempt.policy["policy_ref"])
            archived_policy = recovery.validate_policy(_loads(self._object(policy_ref)))
            recovery.validate_attempt_policy(attempt.policy, archived_policy)
            snapshot = job.model_copy(
                update={
                    "transaction": None,
                    "request": attempt.request,
                    "request_digest": attempt.request_digest,
                    "admission": attempt.admission,
                    "real_binding": attempt.real_binding,
                    "scope_trial_key": identity["business_key"] if attempt.real_binding else None,
                    "consumed_grant": attempt.request.grant_ref.digest,
                    "state": "succeeded" if attempt.report else attempt.state,
                    "report": attempt.report,
                    "decision": None,
                    "decision_key": None,
                    "created_at": attempt.started_at,
                    "completed_at": attempt.completed_at,
                }
            )
            self._verify(snapshot)
            if attempt.real_binding is not None:
                actual_basis = self._ivv_binding(snapshot, executing=False)
                if (
                    actual_basis["recovery_identity"] != identity
                    or actual_basis["attempt_policy"] != attempt.policy
                    or actual_basis["recovery_provenance"] != attempt.provenance
                ):
                    raise ValueError("transaction_provenance")
        if (
            job.request != last.request
            or job.request_digest != last.request_digest
            or job.admission != last.admission
            or job.real_binding != last.real_binding
            or job.state
            != {
                "running": "running",
                "prepared": "running",
                "failed": "failed",
                "interrupted": "interrupted",
                "committed": "succeeded",
            }[last.state]
            or (job.completed_at is None) != (job.state == "running")
            or (tx.prepared_report is not None) != (last.state == "prepared")
            or (tx.prepared_report is not None and tx.prepared_report != last.report)
            or job.report != (last.report if last.state == "committed" else None)
        ):
            raise ValueError("transaction_snapshot")

    def _interrupted_transaction(self, job):
        tx = job.transaction
        attempt = tx.attempts[-1].model_copy(
            update={
                "state": "interrupted",
                "completed_at": _now(),
                "failure_code": "EXECUTION_INTERRUPTED",
            }
        )
        return job.model_copy(
            update={
                "state": "interrupted",
                "completed_at": _now(),
                "transaction": tx.model_copy(update={"attempts": [*tx.attempts[:-1], attempt]}),
            }
        )

    def _committed_transaction(self, job):
        tx = job.transaction
        if tx.prepared_report is None:
            raise NativeError("artifact_invalid")
        attempt = tx.attempts[-1].model_copy(update={"state": "committed", "completed_at": _now()})
        done = job.model_copy(
            update={
                "state": "succeeded",
                "report": tx.prepared_report,
                "completed_at": _now(),
                "transaction": tx.model_copy(
                    update={"prepared_report": None, "attempts": [*tx.attempts[:-1], attempt]}
                ),
            }
        )
        self._verify(done)
        return done

    def _submit_transaction(self, request, key):
        """Return None for legacy jobs; one local result commit for each business key."""
        with self._condition:
            if self._closed or self._closing:
                raise NativeError("service_closed")
            jobs = self._records()
            existing = next((j for j in jobs if j.job_id == key), None)
            registration = next(
                (r for r in self._registered if r.request == request and r.recovery is not None),
                None,
            )
            if registration is None and (existing is None or existing.transaction is None):
                return None
            if existing is not None and existing.transaction is None:
                raise NativeError("idempotency_conflict")  # Never migrate an old spent claim.
            meta = self._recovery_metadata(registration) if registration else None
            if existing is not None:
                if (meta is None and existing.request != request) or (
                    meta and meta["recovery_identity"] != existing.transaction.identity
                ):
                    raise NativeError("idempotency_conflict")
                if existing.report is not None or existing.decision is not None:
                    return self._public(existing), False
                if existing.transaction.prepared_report is not None and self._inflight is None:
                    done = self._committed_transaction(existing)
                    self._publish_records([done if j.job_id == key else j for j in jobs])
                    return self._public(done), False
                if existing.state == "running" or meta is None:
                    return self._public(existing), False
            if meta is None or key != self._transaction_job_id(meta["recovery_identity"]):
                raise NativeError("study_not_admitted")
            identity = meta["recovery_identity"]
            for prior in jobs:
                if prior.job_id == key:
                    continue
                if prior.scope_trial_key == identity["business_key"]:
                    raise NativeError("idempotency_conflict")
                if prior.transaction is not None:
                    registered_identity = prior.transaction.identity
                    if (
                        registered_identity["logical_task_id"] == identity["logical_task_id"]
                        and registered_identity["experiment_id"] == identity["experiment_id"]
                    ):
                        # A changed data/math version needs an explicit new experiment.
                        raise NativeError("idempotency_conflict")
            attempts = existing.transaction.attempts if existing else []
            task_attempts = sum(
                len(prior.transaction.attempts)
                for prior in jobs
                if prior.transaction is not None
                and prior.transaction.identity["logical_task_id"] == identity["logical_task_id"]
            )
            if task_attempts >= meta["attempt_policy"]["max_numerical_attempts"]:
                raise NativeError("study_not_admitted")
            self._recover_pending_cleanup()
            if self._inflight is not None:
                raise NativeError("capacity_exceeded")
            if existing is None and len(jobs) >= MAX_JOBS:
                raise NativeError("capacity_exceeded")
            attempt_id = str(uuid4())
            conflicts = [j for j in jobs if j.job_id != key]
            try:
                admitted, reasons = self._admit(
                    request, conflicts, key=key, recovery_attempt_id=attempt_id
                )
                if admitted is None:
                    raise NativeError("study_not_admitted")
                _, contents = self._binding(request, registration.store, executing=True)
                references = [
                    meta["attempt_policy"]["policy_ref"],
                    meta["recovery_provenance"]["input_manifest_ref"],
                    *meta["recovery_provenance"]["capture_attempt_refs"],
                ]
                for ref in references:
                    ref = ObjectRef.model_validate(ref)
                    contents.append((ref, self._from_store(registration.store, ref)))
                basis = None
                if registration.real_binding is not None:
                    from quantmesh.research import ivv_admission as ivv

                    contents.extend(
                        ivv.binding_objects(registration.store, registration.real_binding)
                    )
                    basis = ivv.verify_saved_binding(
                        registration.store,
                        request.package_ref,
                        registration.real_binding,
                        executing=True,
                    )
                    if any(basis.get(k) != v for k, v in meta.items()):
                        raise NativeError("study_not_admitted")
                for ref, raw in contents:
                    if self._put(raw, ref.media_type) != ref:
                        raise NativeError("artifact_invalid")
                now = _now()
                identity = digest(canonical(request.model_dump(mode="json")))
                status = "ACCEPTED_DECLARED_RESEARCH" if basis else "ACCEPTED_ENGINEERING"
                admission = {
                    "schema_id": "qm.native-daily.admission.v2"
                    if basis
                    else "qm.native-daily.admission.v1",
                    "job_id": key,
                    "request_digest": identity,
                    "request": request.model_dump(mode="json"),
                    "status": status,
                    "reasons": reasons,
                    "created_at": now,
                    "financial_qualification": "INSUFFICIENT",
                    "paper_allowed": False,
                    "live_allowed": False,
                }
                if basis:
                    admission["use_basis"] = basis
                admission_ref = self._put(canonical(admission))
                attempt = ComputeAttempt(
                    attempt_id=attempt_id,
                    sequence=len(attempts) + 1,
                    state="running",
                    request=request,
                    request_digest=identity,
                    admission=admission_ref,
                    real_binding=registration.real_binding,
                    policy=meta["attempt_policy"],
                    provenance=meta["recovery_provenance"],
                    started_at=now,
                )
                job = NativeJob(
                    job_id=key,
                    request=request,
                    request_digest=identity,
                    state="running",
                    admission_status=status,
                    admission=admission_ref,
                    created_at=existing.created_at if existing else now,
                    consumed_grant=request.grant_ref.digest,
                    scope_trial_key=meta["recovery_identity"]["business_key"],
                    real_binding=registration.real_binding,
                    transaction=ResearchTransaction(
                        identity=meta["recovery_identity"], attempts=[*attempts, attempt]
                    ),
                )
                self._verify(job)
                self._publish_records(
                    [job if j.job_id == key else j for j in jobs] if existing else [*jobs, job]
                )
                self._inflight = key
            except BaseException:
                self._release_real_runtime(registration)
                raise
        try:
            raw = self._compute(registration, job)
            with self._condition:
                report = self._put(raw)
                tx = job.transaction
                prepared_attempt = tx.attempts[-1].model_copy(
                    update={"state": "prepared", "report": report}
                )
                prepared = job.model_copy(
                    update={
                        "transaction": tx.model_copy(
                            update={
                                "prepared_report": report,
                                "attempts": [*tx.attempts[:-1], prepared_attempt],
                            }
                        )
                    }
                )
                self._verify(prepared)
                self._publish_records([prepared if j.job_id == key else j for j in self._records()])
                done = self._committed_transaction(prepared)
                self._publish_records([done if j.job_id == key else j for j in self._records()])
                return self._public(done), existing is None
        except Exception:
            with self._condition:
                current = next(j for j in self._records() if j.job_id == key)
                if current.report is not None:
                    return self._public(current), existing is None
                if current.transaction.prepared_report is not None:
                    raise
                tx = current.transaction
                failed_attempt = tx.attempts[-1].model_copy(
                    update={
                        "state": "failed",
                        "completed_at": _now(),
                        "failure_code": "COMPUTE_FAILED",
                    }
                )
                failed = current.model_copy(
                    update={
                        "state": "failed",
                        "completed_at": _now(),
                        "transaction": tx.model_copy(
                            update={"attempts": [*tx.attempts[:-1], failed_attempt]}
                        ),
                    }
                )
                self._publish_records([failed if j.job_id == key else j for j in self._records()])
                return self._public(failed), existing is None
        finally:
            self._finish_runtime(registration)

    def _release_real_runtime(self, registration):
        if registration.real_binding is not None:
            pin = registration.real_binding.digest
            owner = self._real_runtimes.get(pin)
            if owner is not None:
                try:
                    owner.close()
                except BaseException:
                    self._cleanup_pending[pin] = self._inflight
                    _UNCERTAIN_OWNER_ROOTS[str(self.root)] = self
                    raise
                del self._real_runtimes[pin]
                self._cleanup_pending.pop(pin, None)
                if not self._cleanup_pending:
                    _UNCERTAIN_OWNER_ROOTS.pop(str(self.root), None)

    def _recover_pending_cleanup(self):
        """Only retry the same held owner; no new child or computation here."""
        with self._condition:
            for pin, job_id in list(self._cleanup_pending.items()):
                self._real_runtimes[pin].close()
                del self._real_runtimes[pin]
                del self._cleanup_pending[pin]
                if self._inflight == job_id:
                    self._inflight = None
            if not self._cleanup_pending:
                _UNCERTAIN_OWNER_ROOTS.pop(str(self.root), None)
            self._condition.notify_all()

    def _finish_runtime(self, registration):
        with self._condition:
            try:
                self._release_real_runtime(registration)
            finally:
                # A failed close leaves the exact owner AND its inflight claim held.
                if not self._cleanup_pending:
                    self._inflight = None
                self._condition.notify_all()

    def _publish_records(self, records):
        records = list(records)
        if self._durable_recovery or any(j.transaction is not None for j in records):
            self._durable_recovery = self.objects.durable = self._store.durable = True
            references = {}

            def collect(value):
                if isinstance(value, dict):
                    if set(value) == {"algorithm", "digest", "media_type", "byte_length"}:
                        ref = ObjectRef.model_validate(value)
                        references[ref.digest] = ref
                    else:
                        for item in value.values():
                            collect(item)
                elif isinstance(value, list):
                    for item in value:
                        collect(item)

            for job in records:
                if job.transaction is None:
                    continue
                collect(job.model_dump(mode="json"))
                for attempt in job.transaction.attempts:
                    _, contents = self._binding(attempt.request, self.objects)
                    for ref, _ in contents:
                        references[ref.digest] = ref
                    if attempt.real_binding is not None:
                        from quantmesh.research import ivv_admission as ivv

                        for ref, _ in ivv.binding_objects(self.objects, attempt.real_binding):
                            references[ref.digest] = ref
            for ref in references.values():
                self.objects.confirm_durable(ref)
        self._store.write(records)

    def _object(self, reference):
        return self._from_store(self.objects, reference)

    @staticmethod
    def _from_store(store, reference):
        if not 1 <= reference.byte_length <= MAX_OBJECT:
            raise NativeError("artifact_invalid")
        try:
            if store.path_for(reference).stat().st_size != reference.byte_length:
                raise ValueError
            return store.get_bytes(reference)
        except (OSError, ValueError):
            raise NativeError("artifact_invalid") from None

    def _artifact_capacity(self):
        from quantmesh.research import ivv_recovery as recovery

        limits = [8 * MAX_OBJECT]
        for registration in self._registered:
            meta = self._recovery_metadata(registration)
            if meta is not None:
                ref = ObjectRef.model_validate(meta["attempt_policy"]["policy_ref"])
                policy = recovery.validate_policy(_loads(self._from_store(registration.store, ref)))
                limits.append(policy["storage"]["study"])
        # Cold decision writes retain the allowance actually archived by admitted
        # attempts; a missing current selector never discards previous originals.
        for job in self._records():
            if job.transaction is not None:
                for attempt in job.transaction.attempts:
                    ref = ObjectRef.model_validate(attempt.policy["policy_ref"])
                    policy = recovery.validate_policy(_loads(self._object(ref)))
                    limits.append(policy["storage"]["study"])
        return max(limits)

    def _put(self, raw, media="application/json"):
        if not 1 <= len(raw) <= MAX_OBJECT:
            raise NativeError("capacity_exceeded")
        used = sum(path.stat().st_size for path in self.root.rglob("*") if path.is_file())
        if used + 2 * len(raw) + 512 * 1024 > self._artifact_capacity():
            raise NativeError("capacity_exceeded")
        return self.objects.put_bytes(media, raw)

    def _bound_binding(self, request, store, *, executing):
        from quantmesh.research import native_daily_candidate as native

        manifest = RealInput.model_validate(_loads(self._from_store(store, request.package_ref)))
        scope = ResearchScope.model_validate(
            _loads(self._from_store(store, request.approved_scope_ref))
        )
        grant = BoundGrant.model_validate(_loads(self._from_store(store, request.grant_ref)))
        expected = {
            "schema_id": "qm.native-daily.research-scope.v1",
            "candidate": CANDIDATE,
            "package_ref": request.package_ref.model_dump(),
            "source_id": manifest.source_id,
            "source_use": manifest.source_use,
            "instrument": manifest.instrument,
            "window_digest": digest(canonical(manifest.window.model_dump(mode="json"))),
            "sample_role": manifest.sample_role,
            "exposure_ref": manifest.exposure_ref.model_dump(),
            "trial_ledger_ref": manifest.trial_ledger_ref.model_dump(),
            "output_root_digest": scope.output_root_digest,
        }
        if canonical(scope.model_dump(mode="json")) != canonical(expected):
            raise NativeError("input_not_qualified")
        grant_expected = {
            **expected,
            "schema_id": "qm.native-daily.bound-grant.v1",
            "approved_scope_ref": request.approved_scope_ref.model_dump(),
            "authority_ref": grant.authority_ref.model_dump(),
            "max_trials": 1,
        }
        if canonical(grant.model_dump(mode="json")) != canonical(grant_expected):
            raise NativeError("input_not_qualified")
        authority = _loads(self._from_store(store, grant.authority_ref))
        authority_expected = {
            "schema_id": "qm.native-daily.scope-authority.v1",
            "candidate": CANDIDATE,
            "approved_scope_ref": request.approved_scope_ref.model_dump(),
            "review_refs": [ref.model_dump() for ref in manifest.review_refs],
            "decision": "APPROVED_OFFLINE_ENGINEERING"
            if manifest.evidence_kind == "engineering_fixture"
            else "APPROVED_DECLARED_RESEARCH",
        }
        if canonical(authority) != canonical(authority_expected):
            raise NativeError("input_not_qualified")
        protocol = _loads(self._from_store(store, request.protocol_ref))
        schema = protocol["schema_id"]
        if schema not in {"qm.native-daily.real-protocol.v2", "qm.native-daily.real-protocol.v3"}:
            raise NativeError("input_not_qualified")
        if schema.endswith(".v2") and executing:
            # Unreleased draft artifacts remain readable; unknown runtimes are never backfilled.
            raise NativeError("input_not_qualified")
        protocol_expected = {
            "schema_id": schema,
            "candidate": CANDIDATE,
            "kernel": KERNEL,
            "evidence_kind": manifest.evidence_kind,
            "package_ref": request.package_ref.model_dump(),
            "grant_ref": request.grant_ref.model_dump(),
            "approved_scope_ref": request.approved_scope_ref.model_dump(),
            "authority_ref": grant.authority_ref.model_dump(),
            "accounting_contract": _accounting_contract(),
            "code": protocol["code"],
            "adapter_sha256": protocol["adapter_sha256"],
            "financial_qualification": "INSUFFICIENT",
            "paper_allowed": False,
            "live_allowed": False,
        }
        if schema.endswith(".v3"):
            runtime = protocol["runtime"]
            if (
                not isinstance(runtime, dict)
                or set(runtime) != {"python", "pandas", "numpy", "calendar"}
                or any(
                    not isinstance(value, str) or not 1 <= len(value) <= 160
                    for value in runtime.values()
                )
            ):
                raise NativeError("input_not_qualified")
            protocol_expected["runtime"] = runtime
        if canonical(protocol) != canonical(protocol_expected):
            raise NativeError("input_not_qualified")
        if executing and (
            scope.output_root_digest != _root_pin(self.root)
            or protocol["code"] != native._code()
            or protocol["adapter_sha256"] != digest(Path(__file__).read_bytes())
            or protocol["runtime"] != runtime_versions()
        ):
            raise NativeError("input_not_qualified")
        references = [
            request.package_ref,
            request.grant_ref,
            request.approved_scope_ref,
            request.protocol_ref,
            grant.authority_ref,
            manifest.exposure_ref,
            manifest.trial_ledger_ref,
            *manifest.review_refs,
            *manifest.source_asset_refs,
            manifest.inputs.bars,
            manifest.inputs.distributions,
            manifest.inputs.schedule,
        ]
        contents = [(ref, self._from_store(store, ref)) for ref in references]
        if executing:
            self._check_input(manifest, store)
        return manifest.model_dump(mode="json"), contents

    def _check_input(self, manifest, store):
        """Admission-only structural/units/session checks, not a second cashbook."""
        from decimal import Decimal

        from quantmesh.research import native_daily_candidate as native

        raw = self._from_store(store, manifest.inputs.bars).decode("utf-8")
        reader = csv.DictReader(io.StringIO(raw))
        if reader.fieldnames != ["date", "open", "high", "low", "close", "volume", "dividend"]:
            raise NativeError("input_not_qualified")
        rows = list(reader)
        if len(rows) != 121 or any(set(row) != set(reader.fieldnames) for row in rows):
            raise NativeError("input_not_qualified")
        dates = [date.fromisoformat(row["date"]) for row in rows]
        if dates != sorted(set(dates)) or (dates[0], dates[100], dates[-1]) != (
            manifest.window.warmup_start,
            manifest.window.score_start,
            manifest.window.score_end,
        ):
            raise NativeError("input_not_qualified")
        for row in rows:
            values = {key: float(row[key]) for key in reader.fieldnames if key != "date"}
            if (
                not all(math.isfinite(value) for value in values.values())
                or min(values[key] for key in ("open", "high", "low", "close")) <= 0
                or values["volume"] < 0
                or values["dividend"] < 0
                or values["high"] < max(values["open"], values["close"])
                or values["low"] > min(values["open"], values["close"])
            ):
                raise NativeError("input_not_qualified")
        schedule = _loads(self._from_store(store, manifest.inputs.schedule))
        sessions = native.CalendarService().sessions(
            "XNYS", dates[0], dates[-1], policy=native.SessionPolicy.REGULAR
        )
        expected = [
            {
                "date": session.session_date.isoformat(),
                "open": session.open_at.isoformat(),
                "close": session.close_at.isoformat(),
            }
            for session in sessions
        ]
        if schedule != expected or [row["date"] for row in schedule] != [
            value.isoformat() for value in dates
        ]:
            raise NativeError("input_not_qualified")
        events = _loads(self._from_store(store, manifest.inputs.distributions))
        if not isinstance(events, list) or len(events) > 121:
            raise NativeError("input_not_qualified")
        totals = {}
        for event in events:
            if not isinstance(event, dict) or set(event) != {"ex_date", "pay_date", "amount"}:
                raise NativeError("input_not_qualified")
            ex, pay = date.fromisoformat(event["ex_date"]), date.fromisoformat(event["pay_date"])
            if type(event["amount"]) not in (int, float) or not math.isfinite(event["amount"]):
                raise NativeError("input_not_qualified")
            amount = Decimal(str(event["amount"]))
            if ex not in dates or pay < ex or not amount.is_finite() or amount <= 0:
                raise NativeError("input_not_qualified")
            totals[ex] = totals.get(ex, Decimal(0)) + amount
        if any(
            Decimal(row["dividend"]) != totals.get(day, Decimal(0))
            for row, day in zip(rows, dates, strict=True)
        ):
            raise NativeError("input_not_qualified")

    def _binding(self, request, store, *, executing=False):
        from quantmesh.research import native_daily_candidate as native

        def load(reference):
            if reference is None:
                raise NativeError("input_not_qualified")
            return _loads(self._from_store(store, reference))

        first = _loads(self._from_store(store, request.package_ref))
        if first.get("schema_id") == "qm.native-daily.real-input.v1":
            return self._bound_binding(request, store, executing=executing)
        package, grant, scope, protocol = map(
            load,
            (
                request.package_ref,
                request.grant_ref,
                request.approved_scope_ref,
                request.protocol_ref,
            ),
        )
        p, g, s = (
            ref.model_dump()
            for ref in (request.package_ref, request.grant_ref, request.approved_scope_ref)
        )
        if (
            package["schema_id"] != "qm.native-daily.input.v1"
            or package["candidate"] != CANDIDATE
            or package["kernel"] != KERNEL
            or package["evidence_kind"] != "engineering_fixture"
            or package["source_use"] != "synthetic_no_vendor"
            or package["real_input_enabled"] is not False
        ):
            raise NativeError("input_not_qualified")
        scope_expected = {
            "schema_id": "qm.native-daily.offline-scope.v1",
            "candidate": CANDIDATE,
            "package_ref": p,
            "output_root_digest": scope["output_root_digest"],
            "purpose": "offline_engineering_only",
            "real_data_authorized": False,
        }
        grant_expected = {
            "schema_id": "qm.native-daily.candidate-grant.v1",
            "candidate": CANDIDATE,
            "package_ref": p,
            "approved_scope_ref": s,
            "output_root_digest": scope["output_root_digest"],
            "purpose": "offline_engineering_only",
            "max_trials": 1,
            "real_data_authorized": False,
        }
        if canonical(scope) != canonical(scope_expected) or canonical(grant) != canonical(
            grant_expected
        ):
            raise NativeError("input_not_qualified")
        if executing and scope["output_root_digest"] != _root_pin(self.root):
            raise NativeError("input_not_qualified")
        protocol_expected = {
            "schema_id": "qm.native-daily.real-protocol.v1",
            "candidate": CANDIDATE,
            "kernel": KERNEL,
            "evidence_kind": "engineering_fixture",
            "package_ref": p,
            "grant_ref": g,
            "approved_scope_ref": s,
            "engineering_protocol_ref": package["engineering_protocol_ref"],
            "adapter_sha256": protocol["adapter_sha256"],
            "financial_qualification": "INSUFFICIENT",
            "paper_allowed": False,
            "live_allowed": False,
        }
        if canonical(protocol) != canonical(protocol_expected):
            raise NativeError("input_not_qualified")
        original_ref = ObjectRef.model_validate(package["engineering_protocol_ref"])
        original_raw = self._from_store(store, original_ref)
        original = _loads(original_raw)
        expected = native._contract(
            original["case"],
            native._V1_INPUTS[original["case"]],
            original["code"],
            original["runtime"],
        )
        if original_raw != native.canonical(expected) or package["inputs"] != original["inputs"]:
            raise NativeError("input_not_qualified")
        if executing and (
            protocol["adapter_sha256"] != digest(Path(__file__).read_bytes())
            or original["code"] != native._code()
        ):
            raise NativeError("input_not_qualified")
        references = [
            request.package_ref,
            request.grant_ref,
            request.approved_scope_ref,
            request.protocol_ref,
            original_ref,
        ]
        references.extend(ObjectRef.model_validate(ref) for ref in package["inputs"].values())
        contents = [(reference, self._from_store(store, reference)) for reference in references]
        return package, contents

    def _admit(self, request, jobs, *, key, recovery_attempt_id=None):
        self._recover_pending_cleanup()
        from quantmesh.research import ivv_admission as ivv

        missing = []
        if request.package_ref is None:
            missing.append("package_missing")
        if request.grant_ref is None:
            missing.append("candidate_grant_missing")
        if missing:
            return None, missing
        registration = next((item for item in self._registered if item.request == request), None)
        if registration is None or registration._authority not in (
            _ENGINEERING_AUTHORITY,
            ivv._REAL_AUTHORITY,
        ):
            return None, ["candidate_grant_not_qualified"]
        try:
            recovery_meta = self._recovery_metadata(registration)
            if recovery_meta is not None and key != self._transaction_job_id(
                recovery_meta["recovery_identity"]
            ):
                return None, ["request_identity_not_authorized"]
            package, contents = self._binding(request, registration.store, executing=True)
            if package["evidence_kind"] == "reviewed_real":
                if (
                    registration._authority is not ivv._REAL_AUTHORITY
                    or registration.real_binding is None
                ):
                    return None, ["real_execution_not_enabled"]
                checked = ivv.verify_saved_binding(
                    registration.store,
                    request.package_ref,
                    registration.real_binding,
                    executing=True,
                )
                if checked["output_root_digest"] != _root_pin(self.root):
                    return None, ["candidate_grant_not_qualified"]
                if any(job.scope_trial_key == checked["scope_trial_key"] for job in jobs):
                    return None, ["scope_trial_already_reserved"]
                if key != checked["job_id"]:
                    return None, ["request_identity_not_authorized"]
                try:
                    owner = self._real_runtimes.get(registration.real_binding.digest)
                    if owner is None:
                        factory = self._real_runtime_factory or ivv.prepare_runtime
                        runtime_basis = (
                            {**checked, "compute_attempt_id": recovery_attempt_id}
                            if recovery_meta
                            else checked
                        )
                        owner = factory(self.root, runtime_basis, registration.store)
                        self._real_runtimes[registration.real_binding.digest] = owner
                    pending = {
                        ref.digest: len(raw)
                        for ref, raw in [
                            *contents,
                            *ivv.binding_objects(registration.store, registration.real_binding),
                        ]
                    }
                    if owner.check(pending_bytes=sum(pending.values())) is not True:
                        raise ValueError("runtime")
                except (ValueError, OSError, RuntimeError):
                    self._release_real_runtime(registration)
                    return None, ["study_runtime_not_admitted"]
            elif (
                registration.real_binding is not None
                or registration._authority is ivv._REAL_AUTHORITY
            ):
                return None, ["candidate_grant_not_qualified"]
            if package.get("schema_id") == "qm.native-daily.real-input.v1":
                grant = _loads(self._from_store(registration.store, request.grant_ref))
                if registration.authority_ref != ObjectRef.model_validate(grant["authority_ref"]):
                    return None, ["candidate_grant_not_qualified"]
        except (KeyError, TypeError, ValueError, OSError, csv.Error, RecursionError):
            return None, ["candidate_grant_not_qualified"]
        if any(
            job.consumed_grant == request.grant_ref.digest
            or (
                job.transaction is not None
                and any(
                    a.request.grant_ref.digest == request.grant_ref.digest
                    for a in job.transaction.attempts
                )
            )
            for job in jobs
        ):
            return None, ["trial_already_reserved"]
        if self._inflight is not None:
            raise NativeError("capacity_exceeded")
        return registration, []

    def _compute(self, registration, job):
        import pandas as pd

        from quantmesh.research import native_daily_candidate as native

        package, _ = self._binding(job.request, self.objects)
        bars = self._object(ObjectRef.model_validate(package["inputs"]["bars"]))
        events = _loads(self._object(ObjectRef.model_validate(package["inputs"]["distributions"])))
        receipt = None
        if job.real_binding is not None:
            calculation, receipt = self._real_runtimes[job.real_binding.digest].calculate(
                bars, events, job.request.protocol_ref.digest, native._code()
            )
        else:
            frame = pd.read_csv(io.BytesIO(bars), dtype={"date": str}).set_index("date")
            calculation = native._calculate_matrix(frame, events, job.request.protocol_ref.digest)
        result = {
            "schema_id": "qm.native-daily.real-report.v1",
            "job_id": job.job_id,
            "request_digest": job.request_digest,
            "protocol_ref": job.request.protocol_ref.model_dump(),
            "package_ref": job.request.package_ref.model_dump(),
            "grant_ref": job.request.grant_ref.model_dump(),
            "evidence_kind": "engineering_fixture",
            "calculation": calculation,
            "financial_qualification": "INSUFFICIENT",
            "paper_allowed": False,
            "live_allowed": False,
        }
        if package.get("schema_id") == "qm.native-daily.real-input.v1":
            result["input_facts"] = package
        if job.real_binding is not None:
            result.update(
                schema_id="qm.native-daily.real-report.v2",
                evidence_kind="reviewed_real",
                use_basis=self._ivv_binding(job, executing=False),
                runtime_receipt=receipt,
            )
        return canonical(native.engine._plain(result))

    def _ivv_binding(self, job, *, executing):
        from quantmesh.research import ivv_admission as ivv

        if job.real_binding is None or job.scope_trial_key is None:
            raise NativeError("artifact_invalid")
        checked = ivv.verify_saved_binding(
            self.objects, job.request.package_ref, job.real_binding, executing=executing
        )
        if checked["scope_trial_key"] != job.scope_trial_key or checked["job_id"] != job.job_id:
            raise NativeError("artifact_invalid")
        return checked

    def _records(self):
        try:
            self._lease.validate()
            if self.objects.durability_uncertain or self._store.durability_uncertain:
                raise OSError("study_publication_uncertain")
            if self._store.path.exists() and self._store.path.stat().st_size > 256 * 1024:
                raise ValueError
            jobs = self._store.read()
            if len(jobs) > MAX_JOBS:
                raise ValueError
            for job in jobs:
                self._verify(job)
            return jobs
        except (OSError, ValueError):
            raise NativeError("artifact_invalid") from None

    def _verify(self, job):
        try:
            if (
                _uuid(job.job_id) != job.job_id
                or digest(canonical(job.request.model_dump(mode="json"))) != job.request_digest
            ):
                raise ValueError
            admission = _loads(self._object(job.admission))
            is_real = job.admission_status == "ACCEPTED_DECLARED_RESEARCH"
            basis = self._ivv_binding(job, executing=False) if is_real else None
            if job.transaction is not None:
                self._verify_transaction(job)
            if not is_real and (
                job.real_binding is not None
                or (job.scope_trial_key is not None and job.transaction is None)
            ):
                raise ValueError
            expected = {
                "schema_id": "qm.native-daily.admission.v2"
                if is_real
                else "qm.native-daily.admission.v1",
                "job_id": job.job_id,
                "request_digest": job.request_digest,
                "request": job.request.model_dump(mode="json"),
                "status": job.admission_status,
                "financial_qualification": "INSUFFICIENT",
                "paper_allowed": False,
                "live_allowed": False,
            }
            if is_real:
                expected["use_basis"] = basis
            if any(admission.get(key) != value for key, value in expected.items()):
                raise ValueError
            if job.state == "not_run" and (
                job.report is not None or job.consumed_grant is not None
            ):
                raise ValueError
            if (job.state == "succeeded") != (job.report is not None):
                raise ValueError
            if job.admission_status in ("ACCEPTED_ENGINEERING", "ACCEPTED_DECLARED_RESEARCH"):
                if (
                    job.request.grant_ref is None
                    or job.consumed_grant != job.request.grant_ref.digest
                ):
                    raise ValueError
                package, _ = self._binding(job.request, self.objects)
                if job.report is not None:
                    from quantmesh.research import native_daily_candidate as native

                    report = _loads(self._object(job.report))
                    expected_report = {
                        "schema_id": "qm.native-daily.real-report.v2"
                        if is_real
                        else "qm.native-daily.real-report.v1",
                        "job_id": job.job_id,
                        "request_digest": job.request_digest,
                        "protocol_ref": job.request.protocol_ref.model_dump(),
                        "package_ref": job.request.package_ref.model_dump(),
                        "grant_ref": job.request.grant_ref.model_dump(),
                        "evidence_kind": "reviewed_real" if is_real else "engineering_fixture",
                        "financial_qualification": "INSUFFICIENT",
                        "paper_allowed": False,
                        "live_allowed": False,
                    }
                    if package.get("schema_id") == "qm.native-daily.real-input.v1":
                        expected_report["input_facts"] = package
                    if is_real:
                        from quantmesh.research.ivv_runtime import validate_close_receipt

                        expected_report["use_basis"] = basis
                        saved_go = _loads(
                            self._object(ObjectRef.model_validate(basis["proofs"]["go_ref"]))
                        )
                        validate_close_receipt(report.get("runtime_receipt"), saved_go["code"])
                        expected_report["runtime_receipt"] = report["runtime_receipt"]
                    if set(report) != set(expected_report) | {"calculation"} or any(
                        report.get(key) != value for key, value in expected_report.items()
                    ):
                        raise ValueError
                    schedule = _loads(
                        self._object(ObjectRef.model_validate(package["inputs"]["schedule"]))
                    )
                    native._check_matrix(
                        {**report, "request_digest": job.request.protocol_ref.digest}, schedule
                    )
            if job.decision is not None:
                decision = _loads(self._object(job.decision))
                pinned = {
                    "schema_id": "qm.native-daily.research-decision.v1",
                    "job_id": job.job_id,
                    "request_digest": job.request_digest,
                    "admission_digest": job.admission.digest,
                    "report_digest": job.report.digest if job.report is not None else None,
                    "decision_key": job.decision_key,
                    "financial_qualification": "INSUFFICIENT",
                    "paper_allowed": False,
                    "live_allowed": False,
                }
                if any(decision.get(key) != value for key, value in pinned.items()):
                    raise ValueError
                NativeDecisionRequest.model_validate(
                    {k: decision[k] for k in NativeDecisionRequest.model_fields}
                )
        except (KeyError, TypeError, ValueError):
            raise NativeError("artifact_invalid") from None

    def _public(self, job):
        result = job.model_dump(
            mode="json",
            exclude={
                "consumed_grant",
                "decision_key",
                "scope_trial_key",
                "real_binding",
                "transaction",
            },
        )
        if job.transaction is not None:
            tx = job.transaction
            result["recovery_status"] = {
                "business_key": tx.identity["business_key"],
                "experiment_id": tx.identity["experiment_id"],
                "registered_attempts": len(tx.attempts),
                "last_attempt_state": tx.attempts[-1].state,
                "request_digest_history": [a.request_digest for a in tx.attempts],
            }
        result["trial_consumed"] = job.consumed_grant is not None
        result["admission_reasons"] = _loads(self._object(job.admission))["reasons"]
        return result

    def _find(self, key):
        key = _uuid(key)
        job = next((job for job in self._records() if job.job_id == key), None)
        if job is None:
            raise NativeError("not_found")
        return job

    def options(self):
        from quantmesh.research import ivv_admission as ivv

        packages, grants = [], []
        for registration in self._registered:
            try:
                package, _ = self._binding(registration.request, registration.store, executing=True)
                real = package["evidence_kind"] == "reviewed_real"
                checked = None
                if real:
                    if (
                        registration._authority is not ivv._REAL_AUTHORITY
                        or registration.real_binding is None
                    ):
                        continue
                    checked = ivv.verify_saved_binding(
                        registration.store,
                        registration.package_ref,
                        registration.real_binding,
                        executing=True,
                    )
                    if checked["output_root_digest"] != _root_pin(self.root):
                        continue
            except (KeyError, TypeError, ValueError, OSError):
                continue
            packages.append(
                {
                    "label": "IVV · declared retrospective research"
                    if real
                    else "Trusted engineering substitute · not real data",
                    "evidence_kind": "reviewed_real" if real else "engineering_fixture",
                    "package_ref": registration.package_ref.model_dump(),
                    "approved_scope_ref": registration.approved_scope_ref.model_dump(),
                    "protocol_ref": registration.protocol_ref.model_dump(),
                }
            )
            if checked is not None:
                packages[-1]["job_id"] = checked["job_id"]
            grants.append(
                {
                    "label": "One private diagnostic · external retention UNKNOWN"
                    if real
                    else "One engineering trial · no provider permission",
                    "package_digest": registration.package_ref.digest,
                    "grant_ref": registration.grant_ref.model_dump(),
                }
            )
        return {
            "configured": True,
            "candidate": CANDIDATE,
            "kernel": KERNEL,
            "packages": packages,
            "grants": grants,
            "real_input_enabled": any(p["evidence_kind"] == "reviewed_real" for p in packages),
            "financial_qualification": "INSUFFICIENT",
            "paper_allowed": False,
            "live_allowed": False,
        }

    def submit(self, request: NativeRequest, key):
        request = NativeRequest.model_validate(request.model_dump())
        key = _uuid(key)
        identity = digest(canonical(request.model_dump(mode="json")))
        transaction_result = self._submit_transaction(request, key)
        if transaction_result is not None:
            return transaction_result
        with self._condition:
            if self._closed or self._closing:
                raise NativeError("service_closed")
            jobs = self._records()
            existing = next((job for job in jobs if job.job_id == key), None)
            if existing is not None:
                if existing.request_digest != identity:
                    raise NativeError("idempotency_conflict")
                return self._public(existing), False
            if len(jobs) >= MAX_JOBS:
                raise NativeError("capacity_exceeded")
            registration, reasons = self._admit(request, jobs, key=key)
            if registration is None:
                from quantmesh.research import ivv_admission as ivv

                for item in self._registered:
                    if item._authority is ivv._REAL_AUTHORITY and item.real_binding is not None:
                        checked = ivv.verify_saved_binding(
                            item.store, item.package_ref, item.real_binding, executing=False
                        )
                        if checked["job_id"] == key and checked["output_root_digest"] == _root_pin(
                            self.root
                        ):
                            # A refusal is not a durable trial reservation. Diagnostic
                            # records use another ID; preserve the authorized ID intact.
                            raise NativeError("study_not_admitted")
            status = "INSUFFICIENT" if registration is None else "ACCEPTED_ENGINEERING"
            real_binding = None
            scope_trial_key = None
            basis = None
            if registration is not None:
                _, contents = self._binding(request, registration.store, executing=True)
                for reference, raw in contents:
                    if self._put(raw, reference.media_type) != reference:
                        raise NativeError("artifact_invalid")
                if registration.real_binding is not None:
                    from quantmesh.research import ivv_admission as ivv

                    for reference, raw in ivv.binding_objects(
                        registration.store, registration.real_binding
                    ):
                        if self._put(raw, reference.media_type) != reference:
                            raise NativeError("artifact_invalid")
                    real_binding = registration.real_binding
                    basis = ivv.verify_saved_binding(
                        self.objects, request.package_ref, real_binding, executing=True
                    )
                    scope_trial_key = basis["scope_trial_key"]
                    status = "ACCEPTED_DECLARED_RESEARCH"
            now = _now()
            admission = {
                "schema_id": "qm.native-daily.admission.v2"
                if basis
                else "qm.native-daily.admission.v1",
                "job_id": key,
                "request_digest": identity,
                "request": request.model_dump(mode="json"),
                "status": status,
                "reasons": reasons,
                "created_at": now,
                "financial_qualification": "INSUFFICIENT",
                "paper_allowed": False,
                "live_allowed": False,
            }
            if basis:
                admission["use_basis"] = basis
            reference = self._put(canonical(admission))
            job = NativeJob(
                job_id=key,
                request=request,
                request_digest=identity,
                state="not_run" if registration is None else "running",
                admission_status=status,
                admission=reference,
                created_at=now,
                completed_at=now if registration is None else None,
                consumed_grant=request.grant_ref.digest if registration is not None else None,
                scope_trial_key=scope_trial_key,
                real_binding=real_binding,
            )
            self._publish_records([*jobs, job])
            if registration is None:
                return self._public(job), True
            self._inflight = key
        try:
            raw = self._compute(registration, job)
            with self._condition:
                reference = self._put(raw)
                done = job.model_copy(
                    update={"state": "succeeded", "report": reference, "completed_at": _now()}
                )
                self._verify(done)
                self._publish_records(
                    [done if item.job_id == key else item for item in self._records()]
                )
                return self._public(done), True
        except Exception:
            with self._condition:
                failed = job.model_copy(update={"state": "failed", "completed_at": _now()})
                self._publish_records(
                    [failed if item.job_id == key else item for item in self._records()]
                )
                return self._public(failed), True
        finally:
            self._finish_runtime(registration)

    def read(self, key):
        with self._condition:
            return self._public(self._find(key))

    def artifact(self, key, kind):
        if kind not in {"admission", "report", "decision"}:
            raise NativeError("invalid_request")
        with self._condition:
            reference = getattr(self._find(key), kind)
            if reference is None:
                raise NativeError("artifact_unavailable")
            return self._object(reference)

    def decide(self, key, request: NativeDecisionRequest, decision_key):
        request = NativeDecisionRequest.model_validate(request.model_dump())
        decision_key = _uuid(decision_key)
        with self._condition:
            if self._closed or self._closing:
                raise NativeError("service_closed")
            job = self._find(key)
            if (request.request_digest, request.admission_digest, request.report_digest) != (
                job.request_digest,
                job.admission.digest,
                job.report.digest if job.report else None,
            ) or job.state == "running":
                raise NativeError("decision_conflict")
            if job.decision is not None:
                prior = _loads(self._object(job.decision))
                if job.decision_key == decision_key and all(
                    prior[k] == v for k, v in request.model_dump().items()
                ):
                    return self._public(job), False
                raise NativeError("decision_conflict")
            value = {
                "schema_id": "qm.native-daily.research-decision.v1",
                "job_id": job.job_id,
                **request.model_dump(),
                "decision_key": decision_key,
                "created_at": _now(),
                "financial_qualification": "INSUFFICIENT",
                "paper_allowed": False,
                "live_allowed": False,
            }
            reference = self._put(canonical(value))
            saved = job.model_copy(update={"decision": reference, "decision_key": decision_key})
            self._publish_records(
                [saved if item.job_id == job.job_id else item for item in self._records()]
            )
            return self._public(saved), True

    def close(self):
        with self._condition:
            self._closing = True
            self._recover_pending_cleanup()
            while self._inflight is not None:
                self._recover_pending_cleanup()
                if self._inflight is None:
                    break
                self._condition.wait()
            if not self._closed:
                for pin, owner in list(self._real_runtimes.items()):
                    try:
                        owner.close()
                    except BaseException:
                        self._cleanup_pending[pin] = None
                        _UNCERTAIN_OWNER_ROOTS[str(self.root)] = self
                        raise
                    del self._real_runtimes[pin]
                self._lease.close()
                self._closed = True
                _UNCERTAIN_OWNER_ROOTS.pop(str(self.root), None)
