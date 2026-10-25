"""One fixed, opt-in development replay; no generic jobs or trading authority."""

from __future__ import annotations

import hashlib
import io
import json
import math
import platform
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.objects import ObjectRef, ObjectStore, is_reparse_point
from quantmesh.ops.paper_controls import WriterLease
from quantmesh.persistence.jsonl import JsonlStore
from quantmesh.research import spy_replay_engine as engine

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
MAX_OBJECT = 1024 * 1024
MAX_JOBS = 32
_SOURCE_SHA = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_ENGINE_SHA = hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest()


class ReplayError(ValueError):
    """Fixed safe public code only."""


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json(raw):
    def pairs(items):
        output = {}
        for key, value in items:
            if key in output:
                raise ValueError("duplicate key")
            output[key] = value
        return output

    return json.loads(
        raw,
        object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")),
    )


def _safe(path):
    if any(is_reparse_point(p) for p in (path, *path.parents)):
        raise ReplayError("service_unavailable")


def _uuid(value):
    return str(UUID(str(value)))


def _now():
    return datetime.now(UTC)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class ReplayRequest(Contract):
    snapshot_digest: Digest
    protocol_digest: Digest


class DecisionRequest(Contract):
    request_digest: Digest
    report_digest: Digest
    disposition: Literal["reject", "watch"]
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("reason")
    @classmethod
    def reason_trimmed(cls, value):
        if not value.strip():
            raise ValueError("reason required")
        return value.strip()


class ReplayDecision(DecisionRequest):
    schema_version: Literal[1] = 1
    decision_key: str
    job_id: str
    snapshot_digest: Digest
    protocol_digest: Digest
    created_at: datetime


class ReplayJob(Contract):
    schema_version: Literal[1] = 1
    job_id: str
    request_digest: Digest
    request: ReplayRequest
    state: Literal["running", "succeeded", "failed", "interrupted"]
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    report: ObjectRef | None = None
    decision: ReplayDecision | None = None
    decision_ref: ObjectRef | None = None
    error_code: Literal["computation_failed", "artifact_invalid", "interrupted"] | None = None
    financial_qualification: Literal["INSUFFICIENT"] = "INSUFFICIENT"
    paper_allowed: Literal[False] = False

    @model_validator(mode="after")
    def consistent(self):
        if _uuid(self.job_id) != self.job_id or self.request_digest != digest(
            canonical(self.request.model_dump())
        ):
            raise ValueError("job identity mismatch")
        times = [self.created_at, self.updated_at, self.completed_at]
        if any(t is not None and t.utcoffset() != UTC.utcoffset(t) for t in times):
            raise ValueError("UTC required")
        if self.updated_at < self.created_at or (
            self.completed_at is not None and self.completed_at < self.created_at
        ):
            raise ValueError("time order")
        if (self.state == "running") != (self.completed_at is None):
            raise ValueError("completion mismatch")
        if (self.state == "succeeded") != (self.report is not None):
            raise ValueError("report mismatch")
        if (self.state in {"failed", "interrupted"}) != (self.error_code is not None):
            raise ValueError("error mismatch")
        if (self.decision is None) != (self.decision_ref is None):
            raise ValueError("decision mismatch")
        for ref in (self.report, self.decision_ref):
            if ref is not None and (
                not 1 <= ref.byte_length <= MAX_OBJECT or ref.media_type != "application/json"
            ):
                raise ValueError("artifact bounds")
        if self.decision is not None:
            d = self.decision
            if self.report is None or (
                d.job_id,
                d.request_digest,
                d.snapshot_digest,
                d.protocol_digest,
                d.report_digest,
            ) != (
                self.job_id,
                self.request_digest,
                self.request.snapshot_digest,
                self.request.protocol_digest,
                self.report.digest,
            ):
                raise ValueError("decision binding")
            if _uuid(d.decision_key) != d.decision_key or d.created_at < self.completed_at:
                raise ValueError("decision identity/time")
        return self


class _StoredJob(ReplayJob):
    implementation_digest: Digest


class ReplayInputSummary(Contract):
    snapshot_digest: Digest
    protocol_digest: Digest
    symbol: Literal["SPY"] = "SPY"
    interval: Literal["1d"] = "1d"
    as_of_utc: str
    frozen_at_utc: str
    warmup_start: str
    observation_start: str
    observation_end: str
    evidence_kind: Literal["reviewed_opend_freeze_v2", "engineering_fixture"]
    limitations: list[str]


class ReplayOptions(Contract):
    schema_version: Literal[1] = 1
    configured: bool
    unavailable_reason: Literal["not_configured", "input_not_qualified"] | None
    input: ReplayInputSummary | None
    fixed: dict = Field(
        default_factory=lambda: dict(
            strategy_id="SMA100-long-cash",
            warmup_sessions=100,
            observation_sessions=21,
            capital_usd=100000,
            base_one_way_bps=5,
            stress_one_way_bps=10,
            cash_interest=0,
            fee_spread_slippage_components=None,
        )
    )
    limits: dict = Field(default_factory=lambda: dict(max_jobs=32, max_inflight=1))
    financial_qualification: Literal["INSUFFICIENT"] = "INSUFFICIENT"
    paper_allowed: Literal[False] = False


LIMITATIONS = [
    "Historical development diagnostic; no independent OOS or profitability qualification.",
    "Daily OPEN proxy; historical executable prices and calibrated costs are not established.",
    "Combined cost proxy; fee/spread/slippage decomposition unavailable. Cash interest assumed0.",
    "Source review receipts do not establish independent legal or historical PIT proof.",
    "Paper and live trading are not authorized.",
]


def _freezer():
    from tools.research import freeze_opend_spy_daily

    if Path(freeze_opend_spy_daily.__file__).resolve() != (
        Path(__file__).resolve().parents[3] / "tools/research/freeze_opend_spy_daily.py"
    ):
        raise ReplayError("input_not_qualified")
    return freeze_opend_spy_daily


@dataclass(frozen=True)
class ReplayInput:
    """Trusted construction only. No public request accepts input bytes or flags."""

    snapshot_digest: str
    protocol_bytes: bytes
    bars_csv: bytes
    distributions_json: bytes
    frozen_at_utc: datetime
    evidence_kind: Literal["reviewed_opend_freeze_v2", "engineering_fixture"]
    source_root: Path | None = None

    def verified(self):
        freezer = _freezer()
        protocol = _json(self.protocol_bytes)
        w = protocol["window"]
        if freezer.plan_window(datetime.fromisoformat(w["as_of_utc"])) != w:
            raise ReplayError("input_not_qualified")
        expected = freezer._protocol_v2(w)
        if any(
            protocol.get(k) != expected[k]
            for k in (
                "schema_id",
                "provider_symbol",
                "currency",
                "interval",
                "rule",
                "costs",
                "benchmarks",
                "financial_qualification",
                "paper_qualification",
            )
        ):
            raise ReplayError("input_not_qualified")
        if self.frozen_at_utc.utcoffset() != UTC.utcoffset(self.frozen_at_utc):
            raise ReplayError("input_not_qualified")
        if self.evidence_kind not in {"reviewed_opend_freeze_v2", "engineering_fixture"}:
            raise ReplayError("input_not_qualified")
        for name, raw in (
            ("normalized-bars.csv", self.bars_csv),
            ("normalized-distributions.json", self.distributions_json),
        ):
            ref = ObjectRef.model_validate(protocol["members"][name])
            if len(raw) > MAX_OBJECT or len(raw) != ref.byte_length or digest(raw) != ref.digest:
                raise ReplayError("input_not_qualified")
        bars = pd.read_csv(io.BytesIO(self.bars_csv), dtype={"date": str})
        if list(bars.columns) != ["date", "open", "high", "low", "close", "volume", "dividend"]:
            raise ReplayError("input_not_qualified")
        if bars.date.tolist() != w["sessions"] or len(bars) != 121:
            raise ReplayError("input_not_qualified")
        for row in bars.itertuples():
            values = [row.open, row.high, row.low, row.close, row.volume, row.dividend]
            if (
                not all(math.isfinite(v) for v in values)
                or min(values[:4]) <= 0
                or min(values[4:]) < 0
            ):
                raise ReplayError("input_not_qualified")
            if row.high < max(row.open, row.close) or row.low > min(row.open, row.close):
                raise ReplayError("input_not_qualified")
        distributions = _json(self.distributions_json)
        if not isinstance(distributions, list) or len(distributions) > 512:
            raise ReplayError("input_not_qualified")
        for event in distributions:
            if set(event) != {"ex_date", "pay_date", "amount"} or not (
                w["score_start"] <= event["ex_date"] <= w["score_end"]
                and event["pay_date"] >= event["ex_date"]
                and type(event["amount"]) in {int, float}
                and math.isfinite(event["amount"])
                and event["amount"] >= 0
            ):
                raise ReplayError("input_not_qualified")
        return protocol, bars.set_index("date"), distributions

    def summary(self):
        p, _, _ = self.verified()
        w = p["window"]
        return ReplayInputSummary(
            snapshot_digest=self.snapshot_digest,
            protocol_digest=digest(self.protocol_bytes),
            as_of_utc=w["as_of_utc"],
            frozen_at_utc=self.frozen_at_utc.isoformat(),
            warmup_start=w["warmup_start"],
            observation_start=w["score_start"],
            observation_end=w["score_end"],
            evidence_kind=self.evidence_kind,
            limitations=(
                ["Synthetic engineering fixture; not real market acceptance."]
                if self.evidence_kind == "engineering_fixture"
                else []
            )
            + LIMITATIONS,
        )

    @classmethod
    def from_descriptor(cls, path: Path):
        """Operator-only config consumes a bound actual external acceptance receipt.

        A valid freeze alone explicitly requires independent review. Neither this
        descriptor nor its trusted receipt is accepted through the public API.
        """
        try:
            path = Path(path).absolute()
            _safe(path)
            if path.stat().st_size > 16384:
                raise ValueError
            descriptor = _json(path.read_bytes())
            if set(descriptor) != {"freeze_root", "freeze_digest", "acceptance"}:
                raise ValueError
            root = Path(descriptor["freeze_root"]).absolute()
            _safe(root)
            freezer = _freezer()
            frozen = freezer.reopen_freeze(root, descriptor["freeze_digest"])
            if frozen["schema_id"] != "qm.spy-daily.freeze.v2":
                raise ValueError
            store = ObjectStore(root)
            approval_ref = ObjectRef.model_validate(descriptor["acceptance"])
            if approval_ref.byte_length > 16384:
                raise ValueError
            approval = _Acceptance.model_validate_json(store.get_bytes(approval_ref))
            protocol_ref = ObjectRef.model_validate(frozen["protocol_ref"])
            if (approval.snapshot_digest, approval.protocol_digest) != (
                descriptor["freeze_digest"],
                protocol_ref.digest,
            ) or approval.reviewed_at_utc < datetime.fromisoformat(frozen["frozen_at_utc"]):
                raise ValueError
            authorization = _json(
                store.get_bytes(
                    ObjectRef.model_validate(frozen["members"]["capture-authorization.json"])
                )
            )
            if approval.use_document_sha256 != authorization["use_document_sha256"]:
                raise ValueError
            value = cls(
                snapshot_digest=descriptor["freeze_digest"],
                protocol_bytes=store.get_bytes(protocol_ref),
                bars_csv=store.get_bytes(
                    ObjectRef.model_validate(frozen["members"]["normalized-bars.csv"])
                ),
                distributions_json=store.get_bytes(
                    ObjectRef.model_validate(frozen["members"]["normalized-distributions.json"])
                ),
                frozen_at_utc=datetime.fromisoformat(frozen["frozen_at_utc"]),
                evidence_kind="reviewed_opend_freeze_v2",
                source_root=root,
            )
            value.verified()
            return value
        except Exception:
            raise ReplayError("input_not_qualified") from None


class _Acceptance(Contract):
    status: Literal["accepted_for_historical_development_replay"]
    scope: Literal["US.SPY/1d/private_research"]
    snapshot_digest: Digest
    protocol_digest: Digest
    use_document_sha256: Digest
    independent_input_review_sha256: Digest
    reviewed_at_utc: datetime

    @model_validator(mode="after")
    def real_references(self):
        if any(
            v == "0" * 64 for v in (self.use_document_sha256, self.independent_input_review_sha256)
        ) or self.reviewed_at_utc.utcoffset() != UTC.utcoffset(self.reviewed_at_utc):
            raise ValueError("acceptance evidence invalid")
        return self


class ReplayService:
    """One writer, one bounded synchronous computation; no automatic rerun."""

    def __init__(self, root: Path, *, replay_input: ReplayInput | None = None):
        self.root = Path(root).absolute()
        _safe(self.root)
        self._condition = threading.Condition(threading.RLock())
        self._inflight = None
        self._closing = self._closed = self._broken = False
        self._input = replay_input
        if replay_input is not None:
            replay_input.verified()
            if replay_input.source_root is not None:
                source, target = replay_input.source_root.resolve(), self.root.resolve()
                if source == target or source in target.parents or target in source.parents:
                    raise ReplayError("input_not_qualified")
        self.objects = ObjectStore(self.root)
        self._store = JsonlStore(
            self.root,
            filename="jobs.jsonl",
            model=_StoredJob,
            label="SPY replay",
            id_label="job",
            key=lambda j: j.job_id,
        )
        self._lease = WriterLease(self.root / ".writer.lock")
        try:
            jobs = self._records()
            for job in jobs:
                self._verify(job)
            changed = [
                self._updated(j, state="interrupted", error_code="interrupted", completed_at=_now())
                if j.state == "running"
                else j
                for j in jobs
            ]
            if changed != jobs:
                self._store.write(changed)
        except BaseException:
            self._lease.close()
            raise

    def _records(self):
        try:
            self._lease.validate()
        except Exception:
            raise ReplayError("service_unavailable") from None
        _safe(self._store.path)
        if self._store.path.exists() and self._store.path.stat().st_size > 256 * 1024:
            raise ReplayError("artifact_invalid")
        try:
            jobs = self._store.read()
        except (ValueError, OSError):
            raise ReplayError("artifact_invalid") from None
        if len(jobs) > MAX_JOBS:
            raise ReplayError("artifact_invalid")
        return jobs

    @staticmethod
    def _updated(job, **changes):
        return _StoredJob.model_validate({**job.model_dump(), "updated_at": _now(), **changes})

    @staticmethod
    def _public(job):
        return ReplayJob.model_validate(job.model_dump(exclude={"implementation_digest"}))

    def _object(self, ref):
        path = self.objects.path_for(ref)
        _safe(path)
        if not 1 <= ref.byte_length <= MAX_OBJECT or path.stat().st_size != ref.byte_length:
            raise ReplayError("artifact_invalid")
        return self.objects.get_bytes(ref)

    def _verify(self, job):
        try:
            if job.report is not None:
                report = _json(self._object(job.report))
                expected = dict(
                    job_id=job.job_id,
                    request_digest=job.request_digest,
                    **job.request.model_dump(),
                    implementation_digest=job.implementation_digest,
                    financial_qualification="INSUFFICIENT",
                    paper_allowed=False,
                )
                if any(report.get(k) != v for k, v in expected.items()):
                    raise ValueError
            if job.decision_ref is not None and self._object(job.decision_ref) != canonical(
                job.decision.model_dump(mode="json")
            ):
                raise ValueError
        except Exception:
            raise ReplayError("artifact_invalid") from None

    def _find(self, key):
        job = next((j for j in self._records() if j.job_id == _uuid(key)), None)
        if job is None:
            raise ReplayError("not_found")
        self._verify(job)
        return job

    def _replace(self, job):
        jobs = self._records()
        self._store.write([job if j.job_id == job.job_id else j for j in jobs])

    def options(self):
        return ReplayOptions(
            configured=self._input is not None,
            unavailable_reason=None if self._input else "input_not_qualified",
            input=self._input.summary() if self._input else None,
        )

    def get(self, key):
        with self._condition:
            return self._public(self._find(key))

    def submit(self, request: ReplayRequest, key):
        request = ReplayRequest.model_validate(request.model_dump())
        key = _uuid(key)
        request_digest = digest(canonical(request.model_dump()))
        with self._condition:
            if self._closing or self._broken:
                raise ReplayError("service_closed")
            jobs = self._records()
            existing = next((j for j in jobs if j.job_id == key), None)
            if existing is not None:
                if existing.request_digest != request_digest:
                    raise ReplayError("idempotency_conflict")
                self._verify(existing)
                return self._public(existing), False
            if (
                self._inflight is not None
                or len(jobs) >= MAX_JOBS
                or any(j.state == "running" for j in jobs)
            ):
                raise ReplayError("capacity_exceeded")
            if self._input is None:
                raise ReplayError("input_not_qualified")
            if (request.snapshot_digest, request.protocol_digest) != (
                self._input.snapshot_digest,
                digest(self._input.protocol_bytes),
            ):
                raise ReplayError("input_pin_mismatch")
            if (
                digest(Path(__file__).read_bytes()) != _SOURCE_SHA
                or digest(Path(engine.__file__).read_bytes()) != _ENGINE_SHA
            ):
                raise ReplayError("input_not_qualified")
            protocol, frame, distributions = self._input.verified()
            at = _now()
            job = _StoredJob(
                job_id=key,
                request=request,
                request_digest=request_digest,
                state="running",
                created_at=at,
                updated_at=at,
                implementation_digest=digest((_SOURCE_SHA + _ENGINE_SHA).encode()),
            )
            self._store.write([*jobs, job])
            self._inflight = key
        publishing = False
        try:
            w = protocol["window"]
            calculation = engine.calculate(frame, distributions, w["score_start"], w["score_end"])
            report = dict(
                schema_version=1,
                job_id=key,
                request_digest=request_digest,
                **request.model_dump(),
                implementation_digest=job.implementation_digest,
                evidence_kind=self._input.evidence_kind,
                engine=dict(
                    original_sha256=engine.ORIGINAL_ENGINE_SHA256, packaged_sha256=_ENGINE_SHA
                ),
                runtime=dict(python=platform.python_version(), pandas=pd.__version__),
                window=w,
                costs=protocol["costs"],
                calculation=calculation,
                financial_qualification="INSUFFICIENT",
                paper_allowed=False,
                limitations=self._input.summary().limitations,
            )
            raw = canonical(report)
            if len(raw) > MAX_OBJECT:
                raise ValueError("report too large")
            ref = self.objects.put_bytes("application/json", raw)
            completed = self._updated(job, state="succeeded", report=ref, completed_at=_now())
            self._verify(completed)
            with self._condition:
                publishing = True
                self._replace(completed)
            return self._public(completed), True
        except Exception:
            with self._condition:
                if publishing:
                    self._broken = True
                    raise ReplayError("service_unavailable") from None
                failed = self._updated(
                    job, state="failed", completed_at=_now(), error_code="computation_failed"
                )
                try:
                    self._replace(failed)
                except Exception:
                    self._broken = True
                    raise ReplayError("service_unavailable") from None
            return self._public(failed), True
        finally:
            with self._condition:
                self._inflight = None
                self._condition.notify_all()

    def artifact(self, key, kind="report"):
        with self._condition:
            job = self._find(key)
            if kind not in {"report", "decision"}:
                raise ReplayError("invalid_request")
            ref = job.report if kind == "report" else job.decision_ref
            if ref is None:
                raise ReplayError("not_found")
            return self._object(ref)

    def decide(self, key, body: DecisionRequest, decision_key):
        body = DecisionRequest.model_validate(body.model_dump())
        decision_key = _uuid(decision_key)
        with self._condition:
            if self._closing or self._broken:
                raise ReplayError("service_closed")
            job = self._find(key)
            if job.state != "succeeded":
                raise ReplayError("job_not_succeeded")
            if body.request_digest != job.request_digest or body.report_digest != job.report.digest:
                raise ReplayError("decision_conflict")
            if job.decision is not None:
                existing = job.decision.model_dump(include=set(DecisionRequest.model_fields))
                if job.decision.decision_key != decision_key or existing != body.model_dump():
                    raise ReplayError("decision_conflict")
                return self._public(job), False
            decision = ReplayDecision(
                **body.model_dump(),
                decision_key=decision_key,
                job_id=job.job_id,
                **job.request.model_dump(),
                created_at=_now(),
            )
            ref = self.objects.put_bytes(
                "application/json", canonical(decision.model_dump(mode="json"))
            )
            completed = self._updated(job, decision=decision, decision_ref=ref)
            self._verify(completed)
            self._replace(completed)
            return self._public(completed), True

    def close(self):
        with self._condition:
            self._closing = True
            while self._inflight is not None:
                self._condition.wait()
            if not self._closed:
                self._lease.close()
                self._closed = True
