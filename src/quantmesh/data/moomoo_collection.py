"""Bounded read-only Moomoo collection contracts and XNYS coverage semantics."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.artifacts import ManifestStore
from quantmesh.data.calendars import CalendarService, SessionPolicy
from quantmesh.data.collection_process import (
    CollectionProcessError,
    CollectionProcessTimeout,
    run_bounded_json_process,
)
from quantmesh.data.instruments import CanonicalInstrumentId
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Instrument, InstrumentType, Venue
from quantmesh.moomoo.market_data import MoomooDataAdapter
from quantmesh.settings import Settings

_APPROVED_TARGETS = {
    ("US.AAPL", "moomoo:US:AAPL:XNAS", "1d"),
    ("US.AAPL", "moomoo:US:AAPL:XNAS", "1m"),
    ("US.NVDA", "moomoo:US:NVDA:XNAS", "1d"),
    ("US.NVDA", "moomoo:US:NVDA:XNAS", "1m"),
}
_MAX_WINDOW = timedelta(days=366)


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class CollectionWindow(_FrozenContract):
    """One UTC request window with a hard whole-run upper bound."""

    start: datetime
    end: datetime

    @model_validator(mode="after")
    def window_is_utc_ordered_and_bounded(self) -> Self:
        if not _is_utc(self.start) or not _is_utc(self.end):
            raise ValueError("collection window timestamps must be UTC")
        if self.end < self.start:
            raise ValueError("collection window start must not be after end")
        if self.end - self.start > _MAX_WINDOW:
            raise ValueError("collection window cannot exceed 366 days")
        return self


class MoomooCollectionTarget(_FrozenContract):
    """One approved provider symbol, canonical identity and interval."""

    provider_symbol: str
    canonical_instrument: CanonicalInstrumentId
    interval: str

    @model_validator(mode="after")
    def target_is_approved(self) -> Self:
        identity = (
            self.provider_symbol,
            self.canonical_instrument.value,
            self.interval,
        )
        if identity not in _APPROVED_TARGETS:
            raise ValueError("target is outside the approved Moomoo collection universe")
        return self


class MoomooCollectionPlan(_FrozenContract):
    """Bounded collection scope; it grants read-only market-data authority only."""

    targets: tuple[MoomooCollectionTarget, ...] = Field(min_length=1, max_length=4)
    process_deadline_seconds: int = Field(default=120, ge=1, le=300)

    @field_validator("targets")
    @classmethod
    def targets_are_unique(
        cls, values: tuple[MoomooCollectionTarget, ...]
    ) -> tuple[MoomooCollectionTarget, ...]:
        identities = [
            (item.provider_symbol, item.canonical_instrument.value, item.interval)
            for item in values
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("collection targets must be unique")
        return values

    @classmethod
    def bounded_default(cls) -> MoomooCollectionPlan:
        targets = tuple(
            MoomooCollectionTarget(
                provider_symbol=provider_symbol,
                canonical_instrument=CanonicalInstrumentId(value=canonical),
                interval=interval,
            )
            for provider_symbol, canonical, interval in sorted(_APPROVED_TARGETS)
        )
        return cls(targets=targets)


class CollectionStatus(StrEnum):
    PUBLISHED = "published"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


class MoomooWorkerRequest(_FrozenContract):
    """Credential-free request passed to the isolated OpenD worker."""

    target: MoomooCollectionTarget
    window: CollectionWindow
    host: str = Field(pattern=r"^(127\.0\.0\.1|localhost)$")
    port: int = Field(ge=1, le=65535)
    connect_timeout_seconds: float = Field(gt=0, le=60)
    request_timeout_seconds: float = Field(gt=0, le=120)


class MoomooRawPayload(_FrozenContract):
    """Strict parent-side decoding of one complete worker response."""

    provider_version: str = Field(pattern=r"^10\.10\.7008$")
    received_at: datetime
    bars: tuple[Bar, ...] = Field(min_length=1)
    history_pages: tuple[dict[str, Any], ...] = Field(min_length=1)
    adjustment_factors: dict[str, Any]
    stock_split_pages: tuple[dict[str, Any], ...] = Field(min_length=1)
    dividends: dict[str, Any]

    @model_validator(mode="after")
    def payload_time_is_utc(self) -> Self:
        if not _is_utc(self.received_at):
            raise ValueError("worker receipt time must be UTC")
        return self

    def validate_for(self, request: MoomooWorkerRequest) -> MoomooRawPayload:
        """Reject a child result that escaped the exact requested target/window."""
        symbol = request.target.provider_symbol.split(".", maxsplit=1)[1]
        if any(
            bar.instrument.symbol != symbol
            or bar.instrument.venue.value != "moomoo"
            or bar.interval != request.target.interval
            or not (request.window.start <= bar.timestamp <= request.window.end)
            for bar in self.bars
        ):
            raise ValueError("worker bars disagree with the bounded collection request")
        timestamps = [bar.timestamp for bar in self.bars]
        if timestamps != sorted(set(timestamps)):
            raise ValueError("worker bars must be strictly ordered and unique")
        if timestamps[-1] > self.received_at:
            raise ValueError("worker receipt time precedes source event time")
        expected_code = request.target.provider_symbol
        payloads = [*self.history_pages, self.adjustment_factors, *self.stock_split_pages]
        if any(payload.get("code") != expected_code for payload in payloads):
            raise ValueError("worker source payload code disagrees with collection request")
        if self.dividends.get("code") != expected_code:
            raise ValueError("worker dividend payload code disagrees with collection request")
        for label, payload in (
            ("adjustment-factor", self.adjustment_factors),
            ("dividend", self.dividends),
        ):
            if not isinstance(payload.get("rows"), list):
                raise ValueError(f"worker {label} payload rows must be a list")
        if any(not isinstance(payload.get("rows"), list) for payload in self.stock_split_pages):
            raise ValueError("worker stock-split payload rows must be lists")
        instrument = Instrument(
            symbol=symbol,
            venue=Venue.MOOMOO,
            instrument_type=InstrumentType.EQUITY,
            currency="USD",
        )
        derived = tuple(
            MoomooDataAdapter().history_pages_to_bars(instrument, list(self.history_pages))
        )
        if derived != self.bars:
            raise ValueError("worker bars are not the canonical derivation of history pages")
        return self


class MoomooWorkerResult(_FrozenContract):
    """Child-process result before anything is allowed into the manifest store."""

    status: CollectionStatus
    reason_code: str | None = None
    detail: str | None = None
    payload: MoomooRawPayload | None = None

    @model_validator(mode="after")
    def status_and_payload_agree(self) -> Self:
        if self.status is CollectionStatus.PUBLISHED:
            if self.payload is None or self.reason_code is not None:
                raise ValueError("successful worker result requires payload only")
        elif self.payload is not None or not self.reason_code or not self.detail:
            raise ValueError("unavailable worker result requires a typed reason and no payload")
        return self


def run_moomoo_worker(
    request: MoomooWorkerRequest,
    *,
    process_deadline_seconds: float,
    scratch_root: Path,
) -> MoomooWorkerResult:
    """Execute the official synchronous SDK outside the publishing process."""
    raw = run_bounded_json_process(
        [
            sys.executable,
            "-m",
            "quantmesh.data.moomoo_collection_worker",
            "{request}",
            "{output}",
        ],
        request=request.model_dump(mode="json"),
        timeout_seconds=process_deadline_seconds,
        scratch_root=scratch_root,
    )
    result = MoomooWorkerResult.model_validate_json(
        json.dumps(raw, sort_keys=True, separators=(",", ":"))
    )
    if result.payload is not None:
        result.payload.validate_for(request)
    return result


class EquityCoverageReport(_FrozenContract):
    """Expected XNYS sessions compared with observed provider sessions."""

    expected: tuple[date, ...]
    observed: tuple[date, ...]
    missing: tuple[date, ...]
    unexpected: tuple[date, ...]


def evaluate_equity_coverage(
    window: CollectionWindow,
    *,
    observed_sessions: tuple[date, ...],
    calendars: CalendarService | None = None,
) -> EquityCoverageReport:
    """Evaluate daily coverage without treating holidays or weekends as gaps."""
    if len(observed_sessions) != len(set(observed_sessions)):
        raise ValueError("observed equity sessions must be unique")
    observed = tuple(sorted(observed_sessions))
    service = calendars or CalendarService()
    sessions = service.sessions(
        "XNYS",
        window.start.date(),
        window.end.date(),
        policy=SessionPolicy.REGULAR,
    )
    expected = tuple(item.session_date for item in sessions)
    expected_set = set(expected)
    observed_set = set(observed)
    return EquityCoverageReport(
        expected=expected,
        observed=observed,
        missing=tuple(item for item in expected if item not in observed_set),
        unexpected=tuple(item for item in observed if item not in expected_set),
    )


class MoomooCollectionResult(_FrozenContract):
    """Typed outcome; unavailable/failed runs can never claim real manifests."""

    status: CollectionStatus
    reason_code: str | None = None
    detail: str | None = None
    manifest_ids: tuple[str, ...] = ()

    @field_validator("manifest_ids")
    @classmethod
    def manifest_ids_are_valid(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("manifest IDs must be unique")
        if any(
            len(value) != 64 or any(character not in "0123456789abcdef" for character in value)
            for value in values
        ):
            raise ValueError("manifest IDs must be lowercase SHA-256 digests")
        return values

    @model_validator(mode="after")
    def status_and_evidence_agree(self) -> Self:
        if self.status is CollectionStatus.PUBLISHED:
            if not self.manifest_ids:
                raise ValueError("published collection requires manifest evidence")
            if self.reason_code is not None:
                raise ValueError("published collection cannot declare an unavailable reason")
        elif self.manifest_ids:
            raise ValueError("unavailable or failed collection cannot claim real manifests")
        elif not self.reason_code or not self.detail:
            raise ValueError("unavailable or failed collection requires a typed reason")
        return self

    @classmethod
    def unavailable(cls, *, reason_code: str, detail: str) -> MoomooCollectionResult:
        return cls(
            status=CollectionStatus.UNAVAILABLE,
            reason_code=reason_code,
            detail=detail,
        )


class MoomooCollector:
    """Collect every target before publishing any result into the fabric."""

    def __init__(
        self,
        store: ManifestStore,
        *,
        code_commit: str,
        scratch_root: Path,
        settings: Settings | None = None,
        worker: Callable[..., MoomooWorkerResult] = run_moomoo_worker,
    ) -> None:
        self.store = store
        self.code_commit = code_commit
        self.scratch_root = Path(scratch_root)
        self.settings = settings or Settings()
        self.worker = worker

    def collect(
        self,
        plan: MoomooCollectionPlan,
        window: CollectionWindow,
    ) -> MoomooCollectionResult:
        """Collect bounded real bundles, or publish nothing for unavailable input."""
        requests = [
            MoomooWorkerRequest(
                target=target,
                window=window,
                host=self.settings.moomoo_opend_host,
                port=self.settings.moomoo_opend_port,
                connect_timeout_seconds=self.settings.moomoo_opend_connect_timeout_s,
                request_timeout_seconds=self.settings.moomoo_opend_request_timeout_s,
            )
            for target in plan.targets
        ]
        collected: list[tuple[MoomooWorkerRequest, MoomooRawPayload]] = []
        for request in requests:
            try:
                result = self.worker(
                    request,
                    process_deadline_seconds=plan.process_deadline_seconds,
                    scratch_root=self.scratch_root,
                )
            except CollectionProcessTimeout:
                return MoomooCollectionResult(
                    status=CollectionStatus.FAILED,
                    reason_code="process-timeout",
                    detail="Moomoo collection exceeded the process deadline",
                )
            except CollectionProcessError:
                return MoomooCollectionResult(
                    status=CollectionStatus.FAILED,
                    reason_code="worker-failed",
                    detail="Moomoo collection worker failed before publication",
                )
            if result.status is not CollectionStatus.PUBLISHED or result.payload is None:
                return MoomooCollectionResult(
                    status=result.status,
                    reason_code=result.reason_code or "unavailable",
                    detail=result.detail or "Moomoo collection is unavailable",
                )
            payload = result.payload.model_copy(update={"received_at": datetime.now(UTC)})
            payload.validate_for(request)
            collected.append((request, payload))

        # Local import keeps the collection contracts independent from their
        # concrete manifest publisher while avoiding a module cycle.
        from quantmesh.data.fabric import MoomooFabricPublisher

        publisher = MoomooFabricPublisher(self.store, code_commit=self.code_commit)
        manifest_ids: list[str] = []
        for request, payload in collected:
            manifest_ids.extend(publisher.publish(request, payload).manifest_ids)
        return MoomooCollectionResult(
            status=CollectionStatus.PUBLISHED,
            manifest_ids=tuple(manifest_ids),
        )
