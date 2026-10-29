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
from uuid import UUID

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


class NativeJob(Contract):
    job_id: str
    request: NativeRequest
    request_digest: Digest
    state: Literal["not_run", "running", "succeeded", "failed", "interrupted"]
    admission_status: Literal["INSUFFICIENT", "REJECT", "ACCEPTED_ENGINEERING"]
    admission: ObjectRef
    report: ObjectRef | None = None
    decision: ObjectRef | None = None
    decision_key: str | None = None
    consumed_grant: Digest | None = None
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


class NativeDailyService:
    """One durable writer, fixed candidate, explicit missing-input decisions."""

    def __init__(self, root: Path, *, registered=()):
        self.root = Path(root).absolute()
        for path in (self.root, *self.root.parents):
            if is_reparse_point(path):
                raise NativeError("unsafe_storage")
        self._condition = threading.Condition(threading.RLock())
        self._closed = False
        self._closing = False
        self._inflight = None
        self._registered = tuple(registered)
        self.objects = ObjectStore(self.root)
        self._lease = WriterLease(self.root / ".writer.lock")
        self._store = JsonlStore(
            self.root,
            filename="jobs.jsonl",
            model=NativeJob,
            label="native daily",
            id_label="job",
            key=lambda job: job.job_id,
            secondary_keys=(("consumed grant", lambda job: job.consumed_grant),),
        )
        try:
            jobs = self._records()
            changed = [
                job.model_copy(update={"state": "interrupted", "completed_at": _now()})
                if job.state == "running"
                else job
                for job in jobs
            ]
            if changed != jobs:
                self._store.write(changed)
        except BaseException:
            self._lease.close()
            raise

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

    def _put(self, raw, media="application/json"):
        if not 1 <= len(raw) <= MAX_OBJECT:
            raise NativeError("capacity_exceeded")
        used = sum(path.stat().st_size for path in self.root.rglob("*") if path.is_file())
        if used + 2 * len(raw) + 512 * 1024 > 8 * MAX_OBJECT:
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

    def _admit(self, request, jobs):
        missing = []
        if request.package_ref is None:
            missing.append("package_missing")
        if request.grant_ref is None:
            missing.append("candidate_grant_missing")
        if missing:
            return None, missing
        registration = next((item for item in self._registered if item.request == request), None)
        if registration is None or registration._authority is not _ENGINEERING_AUTHORITY:
            return None, ["candidate_grant_not_qualified"]
        try:
            package, _ = self._binding(request, registration.store, executing=True)
            if package["evidence_kind"] == "reviewed_real":
                return None, ["real_execution_not_enabled"]
            if package.get("schema_id") == "qm.native-daily.real-input.v1":
                grant = _loads(self._from_store(registration.store, request.grant_ref))
                if registration.authority_ref != ObjectRef.model_validate(grant["authority_ref"]):
                    return None, ["candidate_grant_not_qualified"]
        except (KeyError, TypeError, ValueError, OSError, csv.Error, RecursionError):
            return None, ["candidate_grant_not_qualified"]
        if any(job.consumed_grant == request.grant_ref.digest for job in jobs):
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
        frame = pd.read_csv(io.BytesIO(bars), dtype={"date": str}).set_index("date")
        result = {
            "schema_id": "qm.native-daily.real-report.v1",
            "job_id": job.job_id,
            "request_digest": job.request_digest,
            "protocol_ref": job.request.protocol_ref.model_dump(),
            "package_ref": job.request.package_ref.model_dump(),
            "grant_ref": job.request.grant_ref.model_dump(),
            "evidence_kind": "engineering_fixture",
            "calculation": native._calculate_matrix(frame, events, job.request.protocol_ref.digest),
            "financial_qualification": "INSUFFICIENT",
            "paper_allowed": False,
            "live_allowed": False,
        }
        if package.get("schema_id") == "qm.native-daily.real-input.v1":
            result["input_facts"] = package
        return canonical(native.engine._plain(result))

    def _records(self):
        try:
            self._lease.validate()
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
            expected = {
                "schema_id": "qm.native-daily.admission.v1",
                "job_id": job.job_id,
                "request_digest": job.request_digest,
                "request": job.request.model_dump(mode="json"),
                "status": job.admission_status,
                "financial_qualification": "INSUFFICIENT",
                "paper_allowed": False,
                "live_allowed": False,
            }
            if any(admission.get(key) != value for key, value in expected.items()):
                raise ValueError
            if job.state == "not_run" and (
                job.report is not None or job.consumed_grant is not None
            ):
                raise ValueError
            if (job.state == "succeeded") != (job.report is not None):
                raise ValueError
            if job.admission_status == "ACCEPTED_ENGINEERING":
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
                        "schema_id": "qm.native-daily.real-report.v1",
                        "job_id": job.job_id,
                        "request_digest": job.request_digest,
                        "protocol_ref": job.request.protocol_ref.model_dump(),
                        "package_ref": job.request.package_ref.model_dump(),
                        "grant_ref": job.request.grant_ref.model_dump(),
                        "evidence_kind": "engineering_fixture",
                        "financial_qualification": "INSUFFICIENT",
                        "paper_allowed": False,
                        "live_allowed": False,
                    }
                    if package.get("schema_id") == "qm.native-daily.real-input.v1":
                        expected_report["input_facts"] = package
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
        result = job.model_dump(mode="json", exclude={"consumed_grant", "decision_key"})
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
        packages, grants = [], []
        for registration in self._registered:
            try:
                package, _ = self._binding(registration.request, registration.store, executing=True)
                if package["evidence_kind"] != "engineering_fixture":
                    continue
            except (KeyError, TypeError, ValueError, OSError):
                continue
            packages.append(
                {
                    "label": "Trusted engineering substitute · not real data",
                    "evidence_kind": "engineering_fixture",
                    "package_ref": registration.package_ref.model_dump(),
                    "approved_scope_ref": registration.approved_scope_ref.model_dump(),
                    "protocol_ref": registration.protocol_ref.model_dump(),
                }
            )
            grants.append(
                {
                    "label": "One engineering trial · no provider permission",
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
            "real_input_enabled": False,
            "financial_qualification": "INSUFFICIENT",
            "paper_allowed": False,
            "live_allowed": False,
        }

    def submit(self, request: NativeRequest, key):
        request = NativeRequest.model_validate(request.model_dump())
        key = _uuid(key)
        identity = digest(canonical(request.model_dump(mode="json")))
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
            registration, reasons = self._admit(request, jobs)
            status = "INSUFFICIENT" if registration is None else "ACCEPTED_ENGINEERING"
            if registration is not None:
                _, contents = self._binding(request, registration.store, executing=True)
                for reference, raw in contents:
                    if self._put(raw, reference.media_type) != reference:
                        raise NativeError("artifact_invalid")
            now = _now()
            admission = {
                "schema_id": "qm.native-daily.admission.v1",
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
            )
            self._store.write([*jobs, job])
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
                self._store.write(
                    [done if item.job_id == key else item for item in self._records()]
                )
                return self._public(done), True
        except Exception:
            with self._condition:
                failed = job.model_copy(update={"state": "failed", "completed_at": _now()})
                self._store.write(
                    [failed if item.job_id == key else item for item in self._records()]
                )
                return self._public(failed), True
        finally:
            with self._condition:
                self._inflight = None
                self._condition.notify_all()

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
            self._store.write(
                [saved if item.job_id == job.job_id else item for item in self._records()]
            )
            return self._public(saved), True

    def close(self):
        with self._condition:
            self._closing = True
            while self._inflight is not None:
                self._condition.wait()
            if not self._closed:
                self._lease.close()
                self._closed = True
