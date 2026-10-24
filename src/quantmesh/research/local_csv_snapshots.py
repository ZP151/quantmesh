"""Bounded inspection of already-held daily CSVs, never source-rights admission."""

from __future__ import annotations

import csv
import hashlib
import io
import os
import stat
import tempfile
import threading
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.calendars import CalendarService
from quantmesh.data.layout import validate_symbol
from quantmesh.data.manifest import DatasetClass, DatasetManifest, SeriesCoverage
from quantmesh.data.objects import ObjectIntegrityError, ObjectRef, ObjectStore, is_reparse_point
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Venue
from quantmesh.research.jobs import DatasetRef, DatasetRejected
from quantmesh.research.realdata_snapshots import _bytes, _json, _utc

MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_REQUEST_BYTES = 3 * 1024 * 1024
MAX_ROWS = 10_000
MAX_LOCATIONS = 100


class LocalCsvModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class LocalCsvSource(LocalCsvModel):
    provider: str = Field(default="unknown", min_length=1, max_length=200)
    received_at: str | None = Field(default=None, max_length=100)
    license_scope: str = Field(default="unknown", min_length=1, max_length=500)
    license_evidence: str = Field(default="unknown", min_length=1, max_length=500)
    pit_status: str = Field(default="unknown", min_length=1, max_length=500)
    adjustment: Literal["raw", "adjusted", "unknown"] = "unknown"
    volume_unit: Literal["shares", "base_units", "contracts", "unknown"] = "unknown"
    session_semantics: str = Field(default="unknown", min_length=1, max_length=500)

    @field_validator("received_at")
    @classmethod
    def receipt_is_utc(cls, value):
        if value is not None:
            _utc(value)
        return value


class LocalCsvEvidence(LocalCsvModel):
    preauthorization_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    post_review_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_evidence_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @field_validator("preauthorization_sha256", "post_review_sha256", "source_evidence_sha256")
    @classmethod
    def no_placeholder_reference(cls, value):
        if value == "0" * 64:
            raise ValueError("placeholder reference")
        return value


class LocalCsvRequest(LocalCsvModel):
    schema_version: Literal[1] = 1
    label: str = Field(min_length=1, max_length=120)
    symbol: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    venue: Literal["moomoo", "hyperliquid"]
    calendar_id: Literal["XNYS", "24/7"]
    interval: Literal["1d"] = "1d"
    required_start: str
    required_end: str
    evidence_kind: Literal["user_snapshot", "fixture"] = "user_snapshot"
    source: LocalCsvSource = Field(default_factory=LocalCsvSource)
    evidence: LocalCsvEvidence = Field(default_factory=LocalCsvEvidence)
    csv_text: str = Field(min_length=1, max_length=MAX_CSV_BYTES)

    @field_validator("schema_version", mode="before")
    @classmethod
    def strict_schema_version(cls, value):
        if type(value) is not int:
            raise ValueError("integer schema version required")
        return value

    @field_validator("symbol")
    @classmethod
    def compatible_symbol(cls, value):
        validate_symbol(value)
        return value

    @model_validator(mode="after")
    def supported_daily_window(self):
        start, end = date.fromisoformat(self.required_start), date.fromisoformat(self.required_end)
        if (
            start.isoformat() != self.required_start
            or end.isoformat() != self.required_end
            or not date(2000, 1, 3) <= start <= end <= date(2035, 12, 31)
            or (end - start).days > 3660
            or (self.venue, self.calendar_id) not in {("moomoo", "XNYS"), ("hyperliquid", "24/7")}
        ):
            raise ValueError("unsupported local daily window")
        return self


class LocalCsvLocation(LocalCsvModel):
    row: int | None = None
    date: str | None = None
    field: str
    expected: str | None = None
    actual: str | None = None


class LocalCsvCheck(LocalCsvModel):
    code: str
    status: Literal["PASS", "REJECT", "INSUFFICIENT"]
    count: int = Field(ge=0)
    message: str
    locations: list[LocalCsvLocation] = Field(default_factory=list)
    locations_truncated: bool = False


class LocalCsvCoverage(LocalCsvModel):
    rows: int = Field(ge=0)
    valid_rows: int = Field(
        ge=0,
        description="Rows with parseable UTC and valid OHLCV shapes; session, duplicate "
        "and order issues are not deducted. Not a qualification/coverage ratio.",
    )
    first_date: str | None
    last_date: str | None
    expected_sessions: int = Field(ge=0)
    missing_sessions: list[str]
    unexpected_sessions: list[str]


class LocalCsvFreshness(LocalCsvModel):
    as_of: str
    latest_complete_session: str | None
    last_session: str | None
    age_sessions: int | None
    status: Literal["CURRENT", "STALE", "INSUFFICIENT"]


class LocalCsvQualification(LocalCsvModel):
    status: Literal["REJECT", "INSUFFICIENT"]
    structural_status: Literal["PASS", "REJECT"]
    allowed_use: list[str]
    R1: Literal["INSUFFICIENT"] = "INSUFFICIENT"
    R2: Literal["INSUFFICIENT"] = "INSUFFICIENT"
    R3: Literal["NOT_AUTHORIZED"] = "NOT_AUTHORIZED"
    reasons: list[str]


class LocalCsvLineage(LocalCsvModel):
    original_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class LocalCsvNextAction(LocalCsvModel):
    kind: Literal["inspect_issues", "plan_experiment"]
    href: Literal["/app/research/jobs"] = "/app/research/jobs"
    submission_allowed: Literal[False] = False
    reason: str


class LocalCsvReport(LocalCsvModel):
    schema_version: Literal[1] = 1
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    imported_at: str
    label: str
    symbol: str
    venue: Literal["moomoo", "hyperliquid"]
    calendar_id: Literal["XNYS", "24/7"]
    interval: Literal["1d"]
    evidence_kind: Literal["user_snapshot", "fixture"]
    source: LocalCsvSource
    coverage: LocalCsvCoverage
    freshness: LocalCsvFreshness
    qualification: LocalCsvQualification
    checks: list[LocalCsvCheck]
    dataset_ref: DatasetRef | None
    report_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    lineage: LocalCsvLineage
    next_action: LocalCsvNextAction


class LocalCsvList(LocalCsvModel):
    schema_version: Literal[1] = 1
    snapshots: list[LocalCsvReport]


class LocalCsvEligibility(LocalCsvModel):
    status: Literal["BLOCKED"] = "BLOCKED"
    reasons: list[str]


class LocalCsvReference(LocalCsvModel):
    schema_version: Literal[1] = 1
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    dataset_ref: DatasetRef | None
    manifest: DatasetManifest | None
    normalized_csv: ObjectRef | None
    eligibility: LocalCsvEligibility
    evidence: LocalCsvEvidence
    intended_use: Literal["local_protocol_planning_only"] = "local_protocol_planning_only"
    runner_status: Literal["blocked_unqualified_input"] = "blocked_unqualified_input"


class _LocalCsvIndex(LocalCsvModel):
    snapshot_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    request: ObjectRef
    original: ObjectRef
    report: ObjectRef
    reference: ObjectRef
    normalized: ObjectRef | None
    manifest: ObjectRef | None


class LocalCsvCatalog:
    """Content-addressed local inspection catalog; no trusted-data promotion."""

    def __init__(self, root: Path, *, clock: Callable[[], datetime] | None = None):
        self.root = Path(root).absolute()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.objects = ObjectStore(self.root)
        self._calendar = None
        self._lock = threading.RLock()

    @property
    def calendar(self):
        if self._calendar is None:
            self._calendar = CalendarService()
        return self._calendar

    def _now(self):
        value = self.clock()
        if value.tzinfo is None or value.utcoffset() != datetime.now(UTC).utcoffset():
            raise ValueError("local CSV clock must be UTC")
        return value.astimezone(UTC)

    def _index_path(self, snapshot_id):
        if (
            not isinstance(snapshot_id, str)
            or len(snapshot_id) != 64
            or any(char not in "0123456789abcdef" for char in snapshot_id)
        ):
            raise KeyError("local_csv_unknown")
        path = self.root / "snapshots" / f"{snapshot_id}.json"
        for component in (self.root, path.parent, path):
            if is_reparse_point(component):
                raise ObjectIntegrityError("local CSV index is not a regular path")
        return path

    def import_csv(self, request: LocalCsvRequest) -> LocalCsvReport:
        from quantmesh.research.local_csv_quality import check_csv, freshness

        request = LocalCsvRequest.model_validate(request.model_dump())
        request_bytes = _bytes(request.model_dump())
        snapshot_id = hashlib.sha256(request_bytes).hexdigest()
        with self._lock:
            path = self._index_path(snapshot_id)
            if path.exists():
                return self.get(snapshot_id)
            now = self._now()
            checks, coverage, normalized, bars = check_csv(request, now, self.calendar)
            rejected = any(check.status == "REJECT" for check in checks)
            reasons = [check.message for check in checks if check.status != "PASS"]
            original_ref = self.objects.put_bytes("text/csv", request.csv_text.encode("utf-8"))
            request_ref = self.objects.put_bytes("application/json", request_bytes)
            normalized_ref, manifest_ref, manifest, dataset_ref = None, None, None, None
            if not rejected:
                normalized_ref = self.objects.put_bytes("text/csv", normalized)
                manifest = DatasetManifest(
                    dataset=f"csv-{snapshot_id[:60]}",
                    source="local_csv_unverified",
                    data_class=DatasetClass.SYNTHETIC
                    if request.evidence_kind == "fixture"
                    else DatasetClass.OBSERVED,
                    license="unverified; caller scope: " + request.source.license_scope,
                    revision=1,
                    generated_at=now,
                    coverage=[
                        SeriesCoverage(
                            interval="1d",
                            venue=Venue(request.venue),
                            symbol=request.symbol,
                            start=bars[0].timestamp,
                            end=bars[-1].timestamp,
                            rows=len(bars),
                        )
                    ],
                )
                manifest_ref = self.objects.put_bytes(
                    "application/json", _bytes(manifest.model_dump(mode="json"))
                )
                dataset_ref = DatasetRef(
                    dataset_id=manifest.dataset,
                    revision=1,
                    manifest_digest=manifest_ref.digest,
                    permission_class="local_research",
                    export_digest=normalized_ref.digest,
                )
            qualification = LocalCsvQualification(
                status="REJECT" if rejected else "INSUFFICIENT",
                structural_status="REJECT" if rejected else "PASS",
                allowed_use=["engineering_only"]
                if request.evidence_kind == "fixture" and not rejected
                else ["inspect_evidence_only", "protocol_planning"]
                if not rejected
                else ["inspect_evidence_only"],
                reasons=reasons,
            )
            reference = LocalCsvReference(
                snapshot_id=snapshot_id,
                dataset_ref=dataset_ref,
                manifest=manifest,
                normalized_csv=normalized_ref,
                eligibility=LocalCsvEligibility(reasons=reasons),
                evidence=request.evidence,
            )
            reference_ref = self.objects.put_bytes(
                "application/json", _bytes(reference.model_dump(mode="json"))
            )
            report = {
                "schema_version": 1,
                "snapshot_id": snapshot_id,
                "imported_at": now.isoformat(),
                **{
                    key: getattr(request, key)
                    for key in (
                        "label",
                        "symbol",
                        "venue",
                        "calendar_id",
                        "interval",
                        "evidence_kind",
                    )
                },
                "source": request.source.model_dump(),
                "coverage": coverage.model_dump(),
                "freshness": freshness(
                    self.calendar, request, coverage.last_date, now
                ).model_dump(),
                "qualification": qualification.model_dump(),
                "checks": [check.model_dump() for check in checks],
                "dataset_ref": dataset_ref.model_dump() if dataset_ref else None,
                "lineage": LocalCsvLineage(
                    original_sha256=original_ref.digest,
                    normalized_sha256=normalized_ref.digest if normalized_ref else None,
                    manifest_sha256=manifest_ref.digest if manifest_ref else None,
                ).model_dump(),
                "next_action": LocalCsvNextAction(
                    kind="inspect_issues" if rejected else "plan_experiment",
                    reason="Input is unqualified; existing fixture jobs cannot use this reference.",
                ).model_dump(),
            }
            report_ref = self.objects.put_bytes("application/json", _bytes(report))
            index = _LocalCsvIndex(
                snapshot_id=snapshot_id,
                request=request_ref,
                original=original_ref,
                report=report_ref,
                reference=reference_ref,
                normalized=normalized_ref,
                manifest=manifest_ref,
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            self._index_path(snapshot_id)
            descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(_bytes(index.model_dump()))
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.link(temporary, path)
                except FileExistsError:
                    pass  # First identical import receipt wins, including another process.
            finally:
                os.unlink(temporary)
            return self.get(snapshot_id)

    def _read(self, snapshot_id):
        path = self._index_path(snapshot_id)
        try:
            if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > 16384:
                raise ObjectIntegrityError("local CSV index invalid")
            index = _LocalCsvIndex.model_validate(_json(path.read_bytes()))
            if index.snapshot_id != snapshot_id or index.request.digest != snapshot_id:
                raise ObjectIntegrityError("local CSV index identity mismatch")
            request = LocalCsvRequest.model_validate(_json(self.objects.get_bytes(index.request)))
            original = self.objects.get_bytes(index.original)
            report_bytes = self.objects.get_bytes(index.report)
            report = LocalCsvReport.model_validate(
                {**_json(report_bytes), "report_digest": index.report.digest}
            )
            reference_bytes = self.objects.get_bytes(index.reference)
            reference = LocalCsvReference.model_validate_json(reference_bytes)
            for key in (
                "label",
                "symbol",
                "venue",
                "calendar_id",
                "interval",
                "evidence_kind",
                "source",
            ):
                if getattr(report, key) != getattr(request, key):
                    raise ObjectIntegrityError("local CSV report source mismatch")
            if (
                original != request.csv_text.encode("utf-8")
                or report.snapshot_id != snapshot_id
                or reference.snapshot_id != snapshot_id
                or report.lineage.original_sha256 != index.original.digest
                or report.dataset_ref != reference.dataset_ref
                or reference.evidence != request.evidence
                or reference.eligibility.reasons != report.qualification.reasons
                or (index.normalized is None) != (index.manifest is None)
                or reference.normalized_csv != index.normalized
                or report.lineage.normalized_sha256
                != (index.normalized.digest if index.normalized else None)
                or report.lineage.manifest_sha256
                != (index.manifest.digest if index.manifest else None)
            ):
                raise ObjectIntegrityError("local CSV lineage mismatch")
            if index.manifest is not None:
                manifest = DatasetManifest.model_validate_json(
                    self.objects.get_bytes(index.manifest)
                )
                self.objects.get_bytes(index.normalized)
                expected = DatasetRef(
                    dataset_id=manifest.dataset,
                    revision=manifest.revision,
                    manifest_digest=index.manifest.digest,
                    permission_class="local_research",
                    export_digest=index.normalized.digest,
                )
                if (
                    reference.manifest != manifest
                    or reference.dataset_ref != expected
                    or report.qualification.structural_status != "PASS"
                ):
                    raise ObjectIntegrityError("local CSV reference mismatch")
            elif (
                reference.manifest is not None
                or reference.dataset_ref is not None
                or report.qualification.structural_status != "REJECT"
            ):
                raise ObjectIntegrityError("local CSV rejected reference mismatch")
            return index, request, report, reference, original, report_bytes, reference_bytes
        except FileNotFoundError as error:
            raise KeyError("local_csv_unknown") from error
        except ObjectIntegrityError:
            raise
        except (ValueError, TypeError, KeyError, OSError, AttributeError, RecursionError) as error:
            raise ObjectIntegrityError("local CSV stored evidence invalid") from error

    def get(self, snapshot_id) -> LocalCsvReport:
        from quantmesh.research.local_csv_quality import freshness

        _, request, report, *_ = self._read(snapshot_id)
        return report.model_copy(
            update={
                "freshness": freshness(
                    self.calendar, request, report.coverage.last_date, self._now()
                )
            }
        )

    def list(self) -> list[LocalCsvReport]:
        self._index_path("0" * 64)
        directory = self.root / "snapshots"
        return (
            [self.get(path.stem) for path in sorted(directory.glob("*.json"))]
            if directory.exists()
            else []
        )

    def reference(self, snapshot_id) -> LocalCsvReference:
        return self._read(snapshot_id)[3]

    def original_bytes(self, snapshot_id) -> bytes:
        return self._read(snapshot_id)[4]

    def report_bytes(self, snapshot_id) -> bytes:
        return self._read(snapshot_id)[5]

    def reference_bytes(self, snapshot_id) -> bytes:
        return self._read(snapshot_id)[6]

    def read_bars(
        self, snapshot_id: str, expected: DatasetRef, *, engineering_only=False
    ) -> list[Bar]:
        """Hydrate existing Bar inputs only for an explicitly declared engineering fixture."""
        from quantmesh.research.local_csv_quality import FIELDS, check_csv, instrument

        index, request, report, reference, *_ = self._read(snapshot_id)
        if (
            not engineering_only
            or request.evidence_kind != "fixture"
            or reference.dataset_ref is None
            or expected != reference.dataset_ref
        ):
            raise DatasetRejected("local_csv_unqualified_or_pin_mismatch")
        checks, _, normalized, _ = check_csv(request, _utc(report.imported_at), self.calendar)
        payload = self.objects.get_bytes(index.normalized)
        if normalized != payload or any(check.status == "REJECT" for check in checks):
            raise ObjectIntegrityError("local CSV normalized input mismatch")
        reader = csv.DictReader(io.StringIO(payload.decode(), newline=""))
        return [
            Bar(
                instrument=instrument(request),
                timestamp=_utc(row[FIELDS[0]]),
                interval="1d",
                **{key: float(row[key]) for key in FIELDS[1:]},
            )
            for row in reader
        ]
