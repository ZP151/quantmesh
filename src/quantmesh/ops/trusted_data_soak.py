"""Immutable daily acceptance evidence for one frozen trusted-data candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import sys
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.artifacts import ArtifactLayer, ManifestStore, canonical_json_bytes
from quantmesh.data.calendars import CalendarService, SessionPolicy
from quantmesh.data.capabilities import DataKind
from quantmesh.data.catalog import CatalogEntry, TrustedDataCatalog
from quantmesh.data.checkpoints import CheckpointStore, CollectionCheckpoint
from quantmesh.data.collection_receipts import CollectionCycleReceipt
from quantmesh.data.objects import is_reparse_point
from quantmesh.ops.immutable_runs import (
    LeaseOwner,
    SlotLease,
    publish_create_once,
    read_safe_bytes,
    reject_reparse_chain,
)

_SCHEMA = "quantmesh-trusted-data-soak-v1"
_MAX_CLOCK_SKEW = timedelta(minutes=5)
_MAX_DAILY_GAP = timedelta(hours=26)
_MAX_CRYPTO_AGE = timedelta(hours=26)
# Real-time freshness/latency SLAs are not meaningful for a historical backfill;
# the replay still enforces every functional invariant (coverage, gaps, order,
# schema, pagination, synthetic rows).
_REPLAY_IGNORED_ISSUES = frozenset(
    {
        "freshness-sla",
        "latency-sla",
        "within-grace-period",
        "freshness-unavailable",
        "latency-unavailable",
    }
)


def _target_id(
    provider_id: str,
    instrument: str,
    layer: ArtifactLayer,
    data_kind: DataKind,
    interval: str | None,
) -> str:
    # Non-bar layers (adjustment factors, splits, dividends) carry no interval;
    # they never match a required bar target but still need a stable identity.
    return "|".join((provider_id, instrument, layer.value, data_kind.value, interval or ""))


_REQUIRED_TARGETS = tuple(
    sorted(
        (
            *(
                _target_id(
                    "hyperliquid-public",
                    f"hyperliquid:perp:{symbol}",
                    ArtifactLayer.ADJUSTED,
                    DataKind.BARS,
                    "1m",
                )
                for symbol in ("BTC", "ETH", "SOL")
            ),
            *(
                _target_id(
                    "moomoo-opend",
                    f"moomoo:US:{symbol}:XNAS",
                    ArtifactLayer.ADJUSTED,
                    DataKind.BARS,
                    "1d",
                )
                for symbol in ("AAPL", "NVDA")
            ),
        )
    )
)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    return value.astimezone(UTC)


def _canonical_tuple(values: Sequence[str], label: str) -> tuple[str, ...]:
    result = tuple(sorted(set(values)))
    if not result or any(not item.strip() for item in result):
        raise ValueError(f"{label} must be non-empty canonical evidence")
    return result


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class SoakCandidate(_FrozenModel):
    schema_version: str = Field(pattern=r"^quantmesh-trusted-data-soak-v1$")
    started_at: datetime
    code_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    policy_ids: tuple[str, ...] = Field(min_length=1)
    calendar_versions: tuple[str, ...] = Field(min_length=1)
    schema_versions: tuple[str, ...] = Field(min_length=1)
    required_targets: tuple[str, ...] = Field(min_length=1)
    config_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("started_at")
    @classmethod
    def start_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "candidate start")

    @field_validator(
        "policy_ids", "calendar_versions", "schema_versions", "required_targets"
    )
    @classmethod
    def baseline_evidence_is_canonical(
        cls, value: tuple[str, ...], info: Any
    ) -> tuple[str, ...]:
        if value != _canonical_tuple(value, info.field_name):
            raise ValueError(f"{info.field_name} must be sorted and unique")
        return value

    @model_validator(mode="after")
    def identities_match(self) -> Self:
        config = {
            "policy_ids": list(self.policy_ids),
            "calendar_versions": list(self.calendar_versions),
            "schema_versions": list(self.schema_versions),
            "required_targets": list(self.required_targets),
        }
        if self.config_digest != _digest(config):
            raise ValueError("candidate config digest does not match its baseline")
        body = self.model_dump(mode="json", exclude={"candidate_id"})
        if self.candidate_id != _digest(body):
            raise ValueError("candidate ID does not match its immutable body")
        return self

    @classmethod
    def build(
        cls,
        *,
        started_at: datetime,
        code_commit: str,
        policy_ids: Sequence[str],
        calendar_versions: Sequence[str],
        schema_versions: Sequence[str],
        required_targets: Sequence[str] = _REQUIRED_TARGETS,
    ) -> SoakCandidate:
        policies = _canonical_tuple(policy_ids, "policy IDs")
        calendars = _canonical_tuple(calendar_versions, "calendar versions")
        schemas = _canonical_tuple(schema_versions, "schema versions")
        targets = _canonical_tuple(required_targets, "required targets")
        config = {
            "policy_ids": list(policies),
            "calendar_versions": list(calendars),
            "schema_versions": list(schemas),
            "required_targets": list(targets),
        }
        values = {
            "schema_version": _SCHEMA,
            "started_at": _utc(started_at, "candidate start"),
            "code_commit": code_commit,
            "policy_ids": policies,
            "calendar_versions": calendars,
            "schema_versions": schemas,
            "required_targets": targets,
            "config_digest": _digest(config),
        }
        probe = cls.model_construct(**values, candidate_id="0" * 64)
        candidate_id = _digest(probe.model_dump(mode="json", exclude={"candidate_id"}))
        return cls(**values, candidate_id=candidate_id)

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class SoakTargetEvidence(_FrozenModel):
    target_id: str = Field(min_length=1)
    manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    quality_evaluation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_end: datetime

    @field_validator("event_end")
    @classmethod
    def event_end_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "target event end")


class SoakReport(_FrozenModel):
    schema_version: str = Field(pattern=r"^quantmesh-trusted-data-soak-v1$")
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    config_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    recorded_at: datetime
    report_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    predecessor_report_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    manifest_ids: tuple[str, ...] = Field(min_length=1)
    quality_evaluation_ids: tuple[str, ...] = Field(min_length=1)
    checkpoint_digests: tuple[str, ...] = Field(min_length=1)
    target_evidence: tuple[SoakTargetEvidence, ...]
    completed_xnys_sessions: tuple[str, ...]
    crypto_observed: bool
    critical_issues: tuple[str, ...]
    report_id: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("recorded_at")
    @classmethod
    def recorded_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "report time")

    @field_validator(
        "manifest_ids",
        "quality_evaluation_ids",
        "checkpoint_digests",
        "completed_xnys_sessions",
        "critical_issues",
    )
    @classmethod
    def report_evidence_is_canonical(
        cls, value: tuple[str, ...], info: Any
    ) -> tuple[str, ...]:
        canonical = tuple(sorted(set(value)))
        if value != canonical or any(not item.strip() for item in value):
            raise ValueError(f"{info.field_name} must be sorted, unique and non-blank")
        return value

    @model_validator(mode="after")
    def identity_and_date_match(self) -> Self:
        if self.report_date != self.recorded_at.date().isoformat():
            raise ValueError("report date does not match its UTC timestamp")
        target_ids = tuple(item.target_id for item in self.target_evidence)
        if target_ids != tuple(sorted(set(target_ids))):
            raise ValueError("target evidence must be sorted and unique")
        body = self.model_dump(mode="json", exclude={"report_id"})
        if self.report_id != _digest(body):
            raise ValueError("report ID does not match its immutable body")
        return self

    @classmethod
    def build(
        cls,
        *,
        candidate: SoakCandidate,
        recorded_at: datetime,
        predecessor_report_id: str | None,
        manifest_ids: Sequence[str],
        quality_evaluation_ids: Sequence[str],
        checkpoint_digests: Sequence[str],
        target_evidence: Sequence[SoakTargetEvidence],
        completed_xnys_sessions: Sequence[str],
        crypto_observed: bool,
        critical_issues: Sequence[str],
    ) -> SoakReport:
        instant = _utc(recorded_at, "report time")
        values = {
            "schema_version": _SCHEMA,
            "candidate_id": candidate.candidate_id,
            "code_commit": candidate.code_commit,
            "config_digest": candidate.config_digest,
            "recorded_at": instant,
            "report_date": instant.date().isoformat(),
            "predecessor_report_id": predecessor_report_id,
            "manifest_ids": _canonical_tuple(manifest_ids, "manifest IDs"),
            "quality_evaluation_ids": _canonical_tuple(
                quality_evaluation_ids, "quality evaluation IDs"
            ),
            "checkpoint_digests": _canonical_tuple(
                checkpoint_digests, "checkpoint digests"
            ),
            "target_evidence": tuple(
                sorted(target_evidence, key=lambda item: item.target_id)
            ),
            "completed_xnys_sessions": tuple(sorted(set(completed_xnys_sessions))),
            "crypto_observed": crypto_observed,
            "critical_issues": tuple(sorted(set(critical_issues))),
        }
        probe = cls.model_construct(**values, report_id="0" * 64)
        report_id = _digest(probe.model_dump(mode="json", exclude={"report_id"}))
        return cls(**values, report_id=report_id)

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class SoakVerification(_FrozenModel):
    accepted: bool
    reasons: tuple[str, ...]
    candidate_id: str | None
    report_count: int = Field(ge=0)
    observed_hours: float = Field(ge=0)
    xnys_session_count: int = Field(ge=0)


class SoakTargetEvidenceV2(_FrozenModel):
    target_id: str = Field(min_length=1)
    provider: Literal["hyperliquid-public", "moomoo-opend"]
    target: Literal["BTC", "ETH", "SOL", "AAPL", "NVDA"]
    canonical_instrument: str = Field(min_length=1)
    interval: Literal["1m", "1d"]
    raw_manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    adjusted_manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    job_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    run_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    attempt: int = Field(ge=1)
    quality_report_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    quality_evaluation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_end: datetime

    @field_validator("event_end")
    @classmethod
    def event_end_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "target event end")


class SoakCandidateV2(_FrozenModel):
    schema_version: Literal["quantmesh-trusted-data-soak-v2"]
    started_at: datetime
    source_contract_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    policy_ids: tuple[str, ...] = Field(min_length=1)
    calendar_versions: tuple[str, ...] = Field(min_length=1)
    schema_versions: tuple[str, ...] = Field(min_length=1)
    required_targets: tuple[str, ...] = Field(min_length=1)
    config_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("started_at")
    @classmethod
    def started_at_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "candidate start")

    @model_validator(mode="after")
    def identity_matches(self) -> Self:
        for values in (
            self.policy_ids,
            self.calendar_versions,
            self.schema_versions,
            self.required_targets,
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError("v2 candidate evidence must be sorted and unique")
        config = {
            "policy_ids": list(self.policy_ids),
            "calendar_versions": list(self.calendar_versions),
            "schema_versions": list(self.schema_versions),
            "required_targets": list(self.required_targets),
        }
        if self.config_digest != _digest(config):
            raise ValueError("v2 candidate config digest disagrees with its baseline")
        if self.candidate_id != _digest(
            self.model_dump(mode="json", exclude={"candidate_id"})
        ):
            raise ValueError("v2 candidate ID disagrees with its body")
        return self

    @classmethod
    def build(cls, **values: Any) -> SoakCandidateV2:
        config = {
            field: list(values[field])
            for field in (
                "policy_ids",
                "calendar_versions",
                "schema_versions",
                "required_targets",
            )
        }
        values = {
            **values,
            "schema_version": "quantmesh-trusted-data-soak-v2",
            "config_digest": _digest(config),
        }
        probe = cls.model_construct(**values, candidate_id="0" * 64)
        return cls(
            **values,
            candidate_id=_digest(
                probe.model_dump(mode="json", exclude={"candidate_id"})
            ),
        )

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class SoakReportV2(_FrozenModel):
    schema_version: Literal["quantmesh-trusted-data-soak-v2"]
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_contract_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    code_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    config_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    recorded_at: datetime
    report_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    predecessor_report_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    collection_receipt_ids: tuple[str, str]
    manifest_ids: tuple[str, ...] = Field(min_length=1)
    quality_evaluation_ids: tuple[str, ...] = Field(min_length=1)
    checkpoint_digests: tuple[str, ...] = Field(min_length=1)
    target_evidence: tuple[SoakTargetEvidenceV2, ...] = Field(min_length=5, max_length=5)
    completed_xnys_sessions: tuple[str, ...]
    crypto_observed: bool
    critical_issues: tuple[str, ...]
    report_id: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("recorded_at")
    @classmethod
    def recorded_at_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "report time")

    @model_validator(mode="after")
    def identity_matches(self) -> Self:
        if self.report_date != self.recorded_at.date().isoformat():
            raise ValueError("v2 report date disagrees with its timestamp")
        for values in (
            self.collection_receipt_ids,
            self.manifest_ids,
            self.quality_evaluation_ids,
            self.checkpoint_digests,
            self.completed_xnys_sessions,
            self.critical_issues,
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError("v2 report evidence must be sorted and unique")
        target_ids = tuple(item.target_id for item in self.target_evidence)
        if target_ids != tuple(sorted(set(target_ids))):
            raise ValueError("v2 report targets must be sorted and unique")
        if self.report_id != _digest(
            self.model_dump(mode="json", exclude={"report_id"})
        ):
            raise ValueError("v2 report ID disagrees with its body")
        return self

    @classmethod
    def build(cls, **values: Any) -> SoakReportV2:
        values = {**values, "schema_version": "quantmesh-trusted-data-soak-v2"}
        probe = cls.model_construct(**values, report_id="0" * 64)
        return cls(
            **values,
            report_id=_digest(probe.model_dump(mode="json", exclude={"report_id"})),
        )

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class SoakStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    @property
    def candidate_path(self) -> Path:
        return self.root / "candidate.json"

    @property
    def report_dir(self) -> Path:
        return self.root / "reports"

    def report_path(self, report_id: str) -> Path:
        return self.report_dir / f"{report_id}.json"

    def _safe(self) -> None:
        paths = (self.root, self.candidate_path, self.report_dir)
        components = {
            component
            for path in paths
            for component in (path.absolute(), *path.absolute().parents)
            if component.exists()
        }
        for path in components:
            if is_reparse_point(path):
                raise ValueError(f"soak evidence path is a symlink or reparse point: {path}")

    @staticmethod
    def _read_evidence(path: Path, model: type[SoakCandidate] | type[SoakReport]):
        if is_reparse_point(path):
            raise ValueError(f"evidence path is a symlink or reparse point: {path}")
        details = path.lstat()
        if not stat.S_ISREG(details.st_mode):
            raise ValueError(f"evidence path is not a regular file: {path}")
        if details.st_nlink != 1:
            raise ValueError(f"evidence path is not a single-link file: {path}")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            current = path.lstat()
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
                or is_reparse_point(path)
            ):
                raise ValueError(f"evidence path changed or redirected while opening: {path}")
            with os.fdopen(descriptor, "rb", closefd=False) as handle:
                payload = handle.read()
        finally:
            os.close(descriptor)
        evidence = model.model_validate_json(payload)
        if payload != evidence.canonical_bytes():
            raise ValueError(f"evidence JSON is not canonical: {path}")
        return evidence

    def load_candidate(self) -> SoakCandidate:
        self._safe()
        return self._read_evidence(self.candidate_path, SoakCandidate)

    def reports(self) -> tuple[SoakReport, ...]:
        self._safe()
        if not self.report_dir.exists():
            return ()
        paths = sorted(self.report_dir.iterdir())
        if any(path.suffix != ".json" for path in paths):
            raise ValueError("report directory contains an unexpected evidence entry")
        reports = tuple(self._read_evidence(path, SoakReport) for path in paths)
        if any(path.stem != report.report_id for path, report in zip(paths, reports, strict=True)):
            raise ValueError("daily report filename disagrees with its immutable identity")
        return tuple(sorted(reports, key=lambda report: (report.recorded_at, report.report_id)))

    def write_candidate(self, candidate: SoakCandidate, *, now: datetime) -> None:
        instant = _utc(now, "candidate write time")
        if abs(instant - candidate.started_at) > _MAX_CLOCK_SKEW:
            raise ValueError("candidate baseline must be written at its actual start time")
        self._safe()
        self.root.mkdir(parents=True, exist_ok=True)
        self._safe()
        payload = candidate.canonical_bytes()
        if self.candidate_path.exists():
            if self.load_candidate().canonical_bytes() != payload:
                raise ValueError("candidate baseline is immutable")
            return
        with self.candidate_path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.utime(self.candidate_path, (instant.timestamp(), instant.timestamp()))

    def append(self, report: SoakReport, *, now: datetime) -> None:
        instant = _utc(now, "report write time")
        if abs(instant - report.recorded_at) > _MAX_CLOCK_SKEW:
            raise ValueError("report must be written at its original UTC observation time")
        candidate = self.load_candidate()
        if (
            report.candidate_id != candidate.candidate_id
            or report.code_commit != candidate.code_commit
            or report.config_digest != candidate.config_digest
        ):
            raise ValueError("report candidate baseline changed")
        existing = self.reports()
        if any(item.report_date == report.report_date for item in existing):
            raise ValueError(f"one report already exists for UTC day {report.report_date}")
        expected_predecessor = None if not existing else existing[-1].report_id
        if report.predecessor_report_id != expected_predecessor:
            raise ValueError("report predecessor does not match the append-only chain")
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self._safe()
        target = self.report_path(report.report_id)
        with target.open("xb") as handle:
            handle.write(report.canonical_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        os.utime(target, (instant.timestamp(), instant.timestamp()))


def _mtime(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _change_time(path: Path) -> datetime:
    """Return a secondary local-filesystem creation/change-time signal."""
    return datetime.fromtimestamp(path.stat().st_ctime, tz=UTC)


def verify_soak(
    root: Path,
    data_root: Path,
    *,
    minimum_hours: int = 168,
    minimum_xnys_sessions: int = 4,
) -> SoakVerification:
    if minimum_hours < 0 or minimum_xnys_sessions < 0:
        raise ValueError("minimum evidence thresholds must be non-negative")
    candidate_path = Path(root) / "candidate.json"
    try:
        schema = _evidence_schema(candidate_path) if candidate_path.exists() else None
    except (OSError, TypeError, ValueError):
        schema = None
    if schema == "quantmesh-trusted-data-soak-v2":
        return _verify_soak_v2(
            root,
            data_root,
            minimum_hours=minimum_hours,
            minimum_xnys_sessions=minimum_xnys_sessions,
        )
    store = SoakStore(root)
    reasons: list[str] = []
    try:
        candidate = store.load_candidate()
    except Exception as error:
        return SoakVerification(
            accepted=False,
            reasons=(f"candidate baseline is unavailable or invalid: {error}",),
            candidate_id=None,
            report_count=0,
            observed_hours=0,
            xnys_session_count=0,
        )
    try:
        reports = store.reports()
    except Exception as error:
        return SoakVerification(
            accepted=False,
            reasons=(f"daily reports are unavailable or invalid: {error}",),
            candidate_id=candidate.candidate_id,
            report_count=0,
            observed_hours=0,
            xnys_session_count=0,
        )

    if abs(_mtime(store.candidate_path) - candidate.started_at) > _MAX_CLOCK_SKEW:
        reasons.append("candidate baseline lacks continuous observation provenance")
    if abs(_change_time(store.candidate_path) - candidate.started_at) > _MAX_CLOCK_SKEW:
        reasons.append("candidate baseline has a late filesystem creation/change time")
    predecessor = None
    dates: set[str] = set()
    sessions: set[str] = set()
    for report in reports:
        path = store.report_path(report.report_id)
        if not path.exists() or path.stem != report.report_id:
            reasons.append("daily report filename disagrees with its immutable identity")
        if abs(_mtime(path) - report.recorded_at) > _MAX_CLOCK_SKEW:
            reasons.append(
                f"{report.report_date} report was not written during continuous observation"
            )
        if abs(_change_time(path) - report.recorded_at) > _MAX_CLOCK_SKEW:
            reasons.append(
                f"{report.report_date} report has a late filesystem creation/change time"
            )
        if (
            report.candidate_id != candidate.candidate_id
            or report.code_commit != candidate.code_commit
            or report.config_digest != candidate.config_digest
        ):
            reasons.append(f"{report.report_date} changed the frozen candidate baseline")
        if report.predecessor_report_id != predecessor:
            reasons.append(f"{report.report_date} breaks the append-only predecessor chain")
        predecessor = report.report_id
        if report.report_date in dates:
            reasons.append(f"{report.report_date} has duplicate daily reports")
        dates.add(report.report_date)
        sessions.update(report.completed_xnys_sessions)
        if not report.crypto_observed:
            reasons.append(f"{report.report_date} has no qualifying crypto observation")
        if report.critical_issues:
            reasons.append(
                f"{report.report_date} has critical SLA issues: "
                + ",".join(report.critical_issues)
            )
        if not (
            report.manifest_ids
            and report.quality_evaluation_ids
            and report.checkpoint_digests
        ):
            reasons.append(f"{report.report_date} has incomplete immutable evidence")

    observed_hours = 0.0
    if reports:
        observed_hours = max(
            0.0,
            (reports[-1].recorded_at - candidate.started_at).total_seconds() / 3600,
        )
        initial_interval = reports[0].recorded_at - candidate.started_at
        daily_intervals = [
            current.recorded_at - previous.recorded_at
            for previous, current in zip(reports, reports[1:], strict=False)
        ]
        if (
            initial_interval < timedelta(0)
            or initial_interval > _MAX_DAILY_GAP
            or any(
                interval <= timedelta(0) or interval > _MAX_DAILY_GAP
                for interval in daily_intervals
            )
        ):
            reasons.append("daily report cadence does not prove continuous observation")
    if observed_hours < minimum_hours:
        reasons.append(
            f"continuous observation is {observed_hours:.2f}h; {minimum_hours}h required"
        )
    required_reports = 0 if minimum_hours == 0 else (minimum_hours + 23) // 24
    if len(reports) < required_reports:
        reasons.append(
            f"only {len(reports)} daily crypto reports exist; {required_reports} required"
        )
    if len(sessions) < minimum_xnys_sessions:
        reasons.append(
            f"only {len(sessions)} completed XNYS sessions exist; "
            f"{minimum_xnys_sessions} required"
        )
    reasons.extend(_verify_data_closure(data_root, candidate, reports))
    return SoakVerification(
        accepted=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
        candidate_id=candidate.candidate_id,
        report_count=len(reports),
        observed_hours=observed_hours,
        xnys_session_count=len(sessions),
    )


def _evidence_schema(path: Path) -> str | None:
    if is_reparse_point(path):
        raise ValueError("candidate path is a symlink or reparse point")
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise ValueError("candidate path must be one regular single-link file")
    payload = json.loads(path.read_bytes())
    return payload.get("schema_version") if isinstance(payload, dict) else None


def _verify_soak_v2(
    root: Path,
    data_root: Path,
    *,
    minimum_hours: int,
    minimum_xnys_sessions: int,
) -> SoakVerification:
    store = SoakStoreV2(root)
    reasons: list[str] = []
    try:
        candidate = store.load_candidate()
        reports = store.reports()
    except Exception as error:
        return SoakVerification(
            accepted=False,
            reasons=(f"v2 evidence is unavailable or invalid: {error}",),
            candidate_id=None,
            report_count=0,
            observed_hours=0,
            xnys_session_count=0,
        )
    if candidate.required_targets != _REQUIRED_TARGETS:
        reasons.append("v2 candidate does not freeze the exact five-target matrix")
    try:
        if candidate.code_commit != _git_commit():
            raise ValueError("v2 candidate commit differs from the clean checkout")
    except Exception as error:
        reasons.append(f"v2 source closure is unavailable or invalid: {error}")
    predecessor = None
    dates: set[str] = set()
    sessions: set[str] = set()
    for report in reports:
        if report.predecessor_report_id != predecessor:
            reasons.append(f"{report.report_date} breaks the v2 predecessor chain")
        predecessor = report.report_id
        if report.report_date in dates:
            reasons.append(f"{report.report_date} has duplicate v2 reports")
        dates.add(report.report_date)
        if report.critical_issues:
            reasons.extend(
                f"{report.report_date} critical: {issue}"
                for issue in report.critical_issues
            )
        if (
            report.candidate_id != candidate.candidate_id
            or report.source_contract_id != candidate.source_contract_id
            or report.code_commit != candidate.code_commit
            or report.config_digest != candidate.config_digest
        ):
            reasons.append(f"{report.report_date} changed the v2 candidate baseline")
        try:
            receipts = tuple(
                store.load_cycle_receipt(receipt_id)
                for receipt_id in report.collection_receipt_ids
            )
            by_provider = {item.provider: item for item in receipts}
            ordered = (
                by_provider["hyperliquid-public"],
                by_provider["moomoo-opend"],
            )
            evidence, config, manifests, _entries = _v2_explicit_snapshot(
                data_root, ordered
            )
            if (
                tuple(sorted(item.receipt_id for item in ordered))
                != report.collection_receipt_ids
                or evidence != report.target_evidence
                or manifests != report.manifest_ids
                or tuple(config["required_targets"]) != candidate.required_targets
            ):
                raise ValueError("v2 report disagrees with exact cycle receipts")
        except Exception as error:
            reasons.append(
                f"{report.report_date} v2 data closure is unavailable or invalid: {error}"
            )
        sessions.update(report.completed_xnys_sessions)
    for previous, current in zip(reports, reports[1:]):
        gap = current.recorded_at - previous.recorded_at
        if gap > _MAX_DAILY_GAP:
            reasons.append(f"daily observation gap is {gap}")
    observed_hours = (
        0.0
        if not reports
        else max(
            0.0,
            (reports[-1].recorded_at - candidate.started_at).total_seconds() / 3600,
        )
    )
    if not reports:
        reasons.append("no v2 daily reports exist")
    if observed_hours < minimum_hours:
        reasons.append(
            f"continuous observation is {observed_hours:.2f}h; {minimum_hours}h required"
        )
    if len(sessions) < minimum_xnys_sessions:
        reasons.append(
            f"XNYS session coverage is {len(sessions)}; {minimum_xnys_sessions} required"
        )
    return SoakVerification(
        accepted=not reasons,
        reasons=tuple(sorted(set(reasons))),
        candidate_id=candidate.candidate_id,
        report_count=len(reports),
        observed_hours=observed_hours,
        xnys_session_count=len(sessions),
    )


def _git_commit() -> str:
    script = Path(sys.argv[0]).resolve()
    anchor = (
        script.parents[1]
        if script.name == "trusted_data_soak.py" and script.parent.name == "tools"
        else Path.cwd()
    )
    repo = Path(
        subprocess.run(
            ["git", "-C", str(anchor), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    )
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    ).stdout
    if len(head) != 40 or status.strip():
        raise ValueError("soak observation requires the exact clean candidate commit")
    return head


def _checkpoint_digest(entry: CatalogEntry) -> str:
    if entry.latest_checkpoint is None:
        raise ValueError(f"{entry.dataset_id} has no committed checkpoint")
    return _digest(entry.latest_checkpoint.model_dump(mode="json"))


def _entry_target_id(entry: CatalogEntry) -> str:
    return _target_id(
        entry.provider_id,
        entry.canonical_instrument,
        entry.layer,
        entry.data_kind,
        entry.interval,
    )


def _latest_completed_xnys_session(instant: datetime):
    sessions = CalendarService().sessions(
        "XNYS",
        (instant - timedelta(days=10)).date(),
        instant.date(),
        policy=SessionPolicy.REGULAR,
    )
    completed = tuple(session for session in sessions if session.close_at <= instant)
    if not completed:
        raise ValueError("no completed XNYS session exists in the verification horizon")
    return completed[-1]


def _verify_data_closure(
    data_root: Path,
    candidate: SoakCandidate,
    reports: tuple[SoakReport, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    try:
        if candidate.required_targets != _REQUIRED_TARGETS:
            raise ValueError("candidate does not freeze the exact five-target matrix")
        if candidate.code_commit != _git_commit():
            raise ValueError("candidate commit differs from the current clean checkout")
        catalog = TrustedDataCatalog(data_root)
        manifest_store = ManifestStore(data_root)
        previous_targets: dict[str, SoakTargetEvidence] = {}
        required = frozenset(candidate.required_targets)
        required_crypto = frozenset(
            target for target in required if target.startswith("hyperliquid-public|")
        )
        for report in reports:
            entries: dict[str, CatalogEntry] = {}
            observed_evaluations: set[str] = set()
            observed_checkpoints: set[str] = set()
            observed_policies: set[str] = set()
            observed_calendars: set[str] = set()
            observed_schemas: set[str] = set()
            for manifest_id in report.manifest_ids:
                entry = catalog.lineage(manifest_id).entry
                manifest = manifest_store.open(manifest_id).manifest
                entries[manifest_id] = entry
                if entry.quality is None or entry.latest_checkpoint is None:
                    raise ValueError(f"manifest {manifest_id} has incomplete quality closure")
                if manifest.code_commit != candidate.code_commit:
                    raise ValueError(f"manifest {manifest_id} has a different producing commit")
                observed_evaluations.add(entry.quality.evaluation_id)
                observed_checkpoints.add(_checkpoint_digest(entry))
                observed_policies.add(entry.quality.policy_id)
                observed_calendars.add(entry.calendar_version)
                observed_schemas.add(
                    f"artifact-v{manifest.schema_version}:{manifest.schema_digest}:"
                    f"{manifest.adapter_version}"
                )
            if observed_evaluations != set(report.quality_evaluation_ids):
                raise ValueError(
                    f"{report.report_date} quality evaluations disagree with data closure"
                )
            if observed_checkpoints != set(report.checkpoint_digests):
                raise ValueError(
                    f"{report.report_date} checkpoints disagree with data closure"
                )
            if observed_policies != set(candidate.policy_ids):
                raise ValueError(
                    f"{report.report_date} policies disagree with candidate baseline"
                )
            if observed_calendars != set(candidate.calendar_versions):
                raise ValueError(
                    f"{report.report_date} calendars disagree with candidate baseline"
                )
            if observed_schemas != set(candidate.schema_versions):
                raise ValueError(
                    f"{report.report_date} schemas disagree with candidate baseline"
                )
            targets = {item.target_id: item for item in report.target_evidence}
            if frozenset(targets) != required:
                missing = sorted(required.difference(targets))
                extra = sorted(frozenset(targets).difference(required))
                raise ValueError(
                    f"{report.report_date} target matrix mismatch; "
                    f"missing={missing}, extra={extra}"
                )
            latest_xnys = _latest_completed_xnys_session(report.recorded_at)
            completed_sessions: set[str] = set()
            qualified_crypto: set[str] = set()
            for target_id, evidence in targets.items():
                entry = entries.get(evidence.manifest_id)
                if entry is None:
                    raise ValueError(f"{target_id} manifest is absent from the daily closure")
                if (
                    _entry_target_id(entry) != target_id
                    or entry.quality is None
                    or entry.quality.evaluation_id != evidence.quality_evaluation_id
                    or _checkpoint_digest(entry) != evidence.checkpoint_digest
                    or entry.event_end != evidence.event_end
                ):
                    raise ValueError(f"{target_id} evidence disagrees with catalog closure")
                if not entry.trusted_for_research:
                    raise ValueError(f"{target_id} is not qualified for research")
                if target_id in required_crypto:
                    if not (
                        report.recorded_at - _MAX_CRYPTO_AGE
                        <= entry.event_end
                        <= report.recorded_at
                    ):
                        raise ValueError(f"{target_id} is stale for the daily report")
                    qualified_crypto.add(target_id)
                else:
                    if entry.event_end.date() != latest_xnys.session_date:
                        raise ValueError(
                            f"{target_id} does not cover the latest completed XNYS session"
                        )
                    completed_sessions.add(latest_xnys.session_date.isoformat())
                previous = previous_targets.get(target_id)
                if previous is not None:
                    if evidence.event_end < previous.event_end:
                        raise ValueError(f"{target_id} event frontier moved backward")
                    if target_id in required_crypto and evidence.event_end == previous.event_end:
                        raise ValueError(f"{target_id} crypto frontier did not advance")
                    if evidence.event_end > previous.event_end and (
                        evidence.manifest_id == previous.manifest_id
                        or evidence.quality_evaluation_id
                        == previous.quality_evaluation_id
                        or evidence.checkpoint_digest == previous.checkpoint_digest
                    ):
                        raise ValueError(
                            f"{target_id} advanced without new immutable closure IDs"
                        )
                previous_targets[target_id] = evidence
            if qualified_crypto != required_crypto or report.crypto_observed is not True:
                raise ValueError(
                    f"{report.report_date} lacks the complete Hyperliquid target matrix"
                )
            if set(report.completed_xnys_sessions) != completed_sessions:
                raise ValueError(
                    f"{report.report_date} XNYS sessions disagree with the pinned calendar"
                )
    except Exception as error:
        reasons.append(f"trusted data closure is unavailable or invalid: {error}")
    return tuple(reasons)


def _catalog_snapshot(
    data_root: Path,
) -> tuple[tuple[CatalogEntry, ...], dict[str, tuple[str, ...]]]:
    entries = TrustedDataCatalog(data_root).entries()
    if not entries:
        raise ValueError("trusted-data catalog is empty")
    store = ManifestStore(data_root)
    policy_ids: list[str] = []
    calendars: list[str] = []
    schemas: list[str] = []
    for entry in entries:
        if entry.quality is None:
            raise ValueError(f"{entry.dataset_id} has no immutable quality evaluation")
        manifest = store.open(entry.manifest_id).manifest
        policy_ids.append(entry.quality.policy_id)
        calendars.append(entry.calendar_version)
        schemas.append(
            f"artifact-v{manifest.schema_version}:{manifest.schema_digest}:"
            f"{manifest.adapter_version}"
        )
    return entries, {
        "policy_ids": tuple(sorted(set(policy_ids))),
        "calendar_versions": tuple(sorted(set(calendars))),
        "schema_versions": tuple(sorted(set(schemas))),
        "required_targets": _REQUIRED_TARGETS,
    }


def _build_report(
    candidate: SoakCandidate,
    entries: tuple[CatalogEntry, ...],
    *,
    recorded_at: datetime,
    predecessor_report_id: str | None,
) -> SoakReport:
    issues: list[str] = []
    manifests: list[str] = []
    evaluations: list[str] = []
    checkpoints: list[str] = []
    sessions: set[str] = set()
    target_evidence: list[SoakTargetEvidence] = []
    qualified_targets: set[str] = set()
    for entry in entries:
        quality = entry.quality
        if quality is None:
            issues.append(f"{entry.dataset_id}:quality-unavailable")
            continue
        manifests.append(entry.manifest_id)
        evaluations.append(quality.evaluation_id)
        checkpoints.append(_checkpoint_digest(entry))
        target_id = _entry_target_id(entry)
        if target_id in candidate.required_targets and entry.latest_checkpoint is not None:
            target_evidence.append(
                SoakTargetEvidence(
                    target_id=target_id,
                    manifest_id=entry.manifest_id,
                    quality_evaluation_id=quality.evaluation_id,
                    checkpoint_digest=_checkpoint_digest(entry),
                    event_end=entry.event_end,
                )
            )
        if not entry.trusted_for_research:
            issues.append(f"{entry.dataset_id}:not-trusted")
        elif target_id in candidate.required_targets:
            qualified_targets.add(target_id)
        issues.extend(f"{entry.dataset_id}:{code}" for code in quality.issue_codes)
        if quality.synthetic_row_count:
            issues.append(f"{entry.dataset_id}:synthetic-rows")
        if (
            target_id in candidate.required_targets
            and entry.provider_id == "moomoo-opend"
            and entry.session_policy.value == "regular"
            and entry.trusted_for_research
        ):
            sessions.add(entry.event_end.date().isoformat())
    observed_target_ids = {item.target_id for item in target_evidence}
    missing_targets = sorted(set(candidate.required_targets).difference(observed_target_ids))
    issues.extend(f"required-target-missing:{target}" for target in missing_targets)
    required_crypto = {
        target
        for target in candidate.required_targets
        if target.startswith("hyperliquid-public|")
    }
    report = SoakReport.build(
        candidate=candidate,
        recorded_at=recorded_at,
        predecessor_report_id=predecessor_report_id,
        manifest_ids=manifests,
        quality_evaluation_ids=evaluations,
        checkpoint_digests=checkpoints,
        target_evidence=target_evidence,
        completed_xnys_sessions=tuple(sessions),
        crypto_observed=required_crypto.issubset(qualified_targets),
        critical_issues=issues,
    )
    return report


class SoakStoreV2:
    """Separate additive v2 evidence store; v1 bytes and paths remain unchanged."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.base = SoakStore(root)
        self.receipt_dir = self.root / "cycle-receipts"

    @property
    def candidate_path(self) -> Path:
        return self.base.candidate_path

    @property
    def report_dir(self) -> Path:
        return self.base.report_dir

    def report_path(self, report_id: str) -> Path:
        return self.base.report_path(report_id)

    def receipt_path(self, receipt_id: str) -> Path:
        return self.receipt_dir / f"{receipt_id}.json"

    def load_candidate(self) -> SoakCandidateV2:
        self.base._safe()
        return self.base._read_evidence(self.candidate_path, SoakCandidateV2)

    def reports(self) -> tuple[SoakReportV2, ...]:
        self.base._safe()
        if not self.report_dir.exists():
            return ()
        paths = sorted(self.report_dir.iterdir())
        if any(path.suffix != ".json" for path in paths):
            raise ValueError("v2 report directory contains an unexpected entry")
        reports = tuple(
            self.base._read_evidence(path, SoakReportV2) for path in paths
        )
        if any(
            path.stem != report.report_id
            for path, report in zip(paths, reports, strict=True)
        ):
            raise ValueError("v2 report filename disagrees with its identity")
        return tuple(sorted(reports, key=lambda item: (item.recorded_at, item.report_id)))

    def write_candidate(self, candidate: SoakCandidateV2, *, now: datetime) -> None:
        instant = _utc(now, "candidate write time")
        if abs(instant - candidate.started_at) > _MAX_CLOCK_SKEW:
            raise ValueError("v2 candidate must be written at its actual start")
        reject_reparse_chain(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.base._safe()
        _write_exact(self.candidate_path, candidate.canonical_bytes(), "v2 candidate")
        os.utime(self.candidate_path, (instant.timestamp(), instant.timestamp()))

    def write_cycle_receipt(self, receipt: CollectionCycleReceipt) -> None:
        reject_reparse_chain(self.root)
        self.receipt_dir.mkdir(parents=True, exist_ok=True)
        reject_reparse_chain(self.receipt_dir)
        _write_exact(
            self.receipt_path(receipt.receipt_id),
            receipt.canonical_bytes(),
            "cycle receipt",
        )

    def load_cycle_receipt(self, receipt_id: str) -> CollectionCycleReceipt:
        reject_reparse_chain(self.root)
        reject_reparse_chain(self.receipt_dir)
        receipt = self.base._read_evidence(
            self.receipt_path(receipt_id), CollectionCycleReceipt
        )
        if receipt.receipt_id != receipt_id:
            raise ValueError("cycle receipt filename disagrees with its content digest")
        return receipt

    def append(self, report: SoakReportV2, *, now: datetime) -> SoakReportV2:
        instant = _utc(now, "report write time")
        if abs(instant - report.recorded_at) > _MAX_CLOCK_SKEW:
            raise ValueError("v2 report must be written at its observation time")
        owner = LeaseOwner.current(token=uuid.uuid4().hex)
        with SlotLease.acquire(
            self.root / ".append-locks",
            report.report_date,
            owner=owner,
            now=instant,
            stale_after=timedelta(minutes=5),
        ):
            candidate = self.load_candidate()
            if (
                report.candidate_id != candidate.candidate_id
                or report.source_contract_id != candidate.source_contract_id
                or report.code_commit != candidate.code_commit
                or report.config_digest != candidate.config_digest
            ):
                raise ValueError("v2 report candidate baseline changed")
            existing = self.reports()
            same_day = tuple(
                item for item in existing if item.report_date == report.report_date
            )
            if same_day:
                if len(same_day) == 1 and same_day[0] == report:
                    return same_day[0]
                raise ValueError("conflicting v2 report already exists for UTC day")
            predecessor = None if not existing else existing[-1].report_id
            if report.predecessor_report_id != predecessor:
                raise ValueError("v2 report predecessor does not match the chain")
            self.report_dir.mkdir(parents=True, exist_ok=True)
            _write_exact(
                self.report_path(report.report_id),
                report.canonical_bytes(),
                "v2 report",
            )
            os.utime(
                self.report_path(report.report_id),
                (instant.timestamp(), instant.timestamp()),
            )
            return report


def _write_exact(path: Path, payload: bytes, label: str) -> None:
    publish_create_once(path, payload, label=label)


def _read_cycle_receipt(path: Path) -> CollectionCycleReceipt:
    reject_reparse_chain(path.parent)
    if is_reparse_point(path):
        raise ValueError("cycle receipt path is a symlink or reparse point")
    details = path.lstat()
    if not stat.S_ISREG(details.st_mode) or details.st_nlink != 1:
        raise ValueError("cycle receipt path must be one regular single-link file")
    payload = read_safe_bytes(path)
    receipt = CollectionCycleReceipt.model_validate_json(payload)
    if payload != receipt.canonical_bytes():
        raise ValueError("cycle receipt JSON is not canonical")
    return receipt


def _v2_explicit_snapshot(
    data_root: Path,
    receipts: tuple[CollectionCycleReceipt, CollectionCycleReceipt],
) -> tuple[
    tuple[SoakTargetEvidenceV2, ...],
    dict[str, tuple[str, ...]],
    tuple[str, ...],
    tuple[CatalogEntry, ...],
]:
    catalog = TrustedDataCatalog(data_root)
    store = ManifestStore(data_root)
    target_evidence: list[SoakTargetEvidenceV2] = []
    policies: set[str] = set()
    calendars: set[str] = set()
    schemas: set[str] = set()
    all_manifest_ids: set[str] = set()
    exact_entries: list[CatalogEntry] = []
    for receipt in receipts:
        provider_checkpoint = _validate_receipt_checkpoint(data_root, receipt)
        for target in receipt.targets:
            layer_ids = target.manifest_ids.ordered_values()
            all_manifest_ids.update(layer_ids)
            layers = {}
            for expected_layer, manifest_id in zip(
                ("raw", "normalized", "adjusted", "feature"),
                layer_ids,
                strict=True,
            ):
                manifest = store.open(manifest_id).manifest
                if (
                    manifest.code_commit != receipt.code_commit
                    or manifest.collection_run_id != receipt.run_id
                    or manifest.layer.value != expected_layer
                    or manifest.canonical_instrument.value
                    != target.canonical_instrument
                    or manifest.data_kind is not DataKind.BARS
                    or manifest.interval != target.interval
                ):
                    raise ValueError(
                        "cycle receipt manifest disagrees with its exact target lineage"
                    )
                layers[expected_layer] = manifest
            adjusted_parents = (layers["normalized"].manifest_id,)
            if receipt.provider == "moomoo-opend":
                action_candidates = tuple(
                    store.open(manifest_id).manifest
                    for manifest_id in provider_checkpoint.manifest_ids
                    if manifest_id not in layer_ids
                    and store.open(manifest_id).manifest.canonical_instrument.value
                    == target.canonical_instrument
                    and store.open(manifest_id).manifest.layer
                    is ArtifactLayer.NORMALIZED
                    and store.open(manifest_id).manifest.data_kind is DataKind.SPLITS
                )
                if len(action_candidates) != 1:
                    raise ValueError(
                        "Moomoo receipt lacks one exact normalized action parent"
                    )
                action = action_candidates[0]
                raw_action_parents = tuple(
                    store.open(parent_id).manifest
                    for parent_id in action.parent_manifest_ids
                    if parent_id in provider_checkpoint.manifest_ids
                )
                if (
                    action.code_commit != receipt.code_commit
                    or action.collection_run_id != receipt.run_id
                    or len(raw_action_parents) != 2
                    or {
                        (item.layer, item.data_kind)
                        for item in raw_action_parents
                    }
                    != {
                        (ArtifactLayer.RAW, DataKind.ADJUSTMENT_FACTORS),
                        (ArtifactLayer.RAW, DataKind.SPLITS),
                    }
                    or any(
                        item.canonical_instrument.value
                        != target.canonical_instrument
                        or item.code_commit != receipt.code_commit
                        or item.collection_run_id != receipt.run_id
                        for item in raw_action_parents
                    )
                ):
                    raise ValueError("Moomoo action parent closure is invalid")
                adjusted_parents = (
                    layers["normalized"].manifest_id,
                    action.manifest_id,
                )
            if (
                layers["normalized"].parent_manifest_ids
                != (layers["raw"].manifest_id,)
                or layers["adjusted"].parent_manifest_ids != adjusted_parents
                or layers["feature"].parent_manifest_ids
                != (layers["adjusted"].manifest_id,)
            ):
                raise ValueError("cycle receipt bars-to-action lineage is invalid")
            entry = catalog.lineage(target.manifest_ids.adjusted).entry
            if entry.quality is None or entry.latest_checkpoint is None:
                raise ValueError("cycle receipt target lacks immutable quality closure")
            entry_checkpoint = entry.latest_checkpoint
            if (
                entry.manifest_id != target.manifest_ids.adjusted
                or entry.provider_id != receipt.provider
                or entry.canonical_instrument != target.canonical_instrument
                or entry.interval != target.interval
                or entry_checkpoint.job_id != receipt.job_id
                or entry_checkpoint.run_id != receipt.run_id
                or entry_checkpoint.attempt != receipt.attempt
                or entry_checkpoint.quality_report_id != receipt.quality_report_id
            ):
                raise ValueError("cycle receipt target disagrees with checkpoint closure")
            target_id = _entry_target_id(entry)
            exact_entries.append(entry)
            target_evidence.append(
                SoakTargetEvidenceV2(
                    target_id=target_id,
                    provider=receipt.provider,
                    target=target.target,
                    canonical_instrument=target.canonical_instrument,
                    interval=target.interval,
                    raw_manifest_id=target.manifest_ids.raw,
                    normalized_manifest_id=target.manifest_ids.normalized,
                    adjusted_manifest_id=target.manifest_ids.adjusted,
                    feature_manifest_id=target.manifest_ids.feature,
                    job_id=receipt.job_id,
                    run_id=receipt.run_id,
                    attempt=receipt.attempt,
                    quality_report_id=receipt.quality_report_id,
                    quality_evaluation_id=entry.quality.evaluation_id,
                    checkpoint_digest=_checkpoint_digest(entry),
                    event_end=entry.event_end,
                )
            )
            policies.add(entry.quality.policy_id)
            calendars.add(entry.calendar_version)
            manifest = store.open(entry.manifest_id).manifest
            schemas.add(
                f"artifact-v{manifest.schema_version}:{manifest.schema_digest}:"
                f"{manifest.adapter_version}"
            )
    evidence = tuple(sorted(target_evidence, key=lambda item: item.target_id))
    if tuple(item.target_id for item in evidence) != _REQUIRED_TARGETS:
        raise ValueError("cycle receipts do not cover the exact five-target matrix")
    entries_by_id = {
        _entry_target_id(entry): entry for entry in exact_entries
    }
    return (
        evidence,
        {
            "policy_ids": tuple(sorted(policies)),
            "calendar_versions": tuple(sorted(calendars)),
            "schema_versions": tuple(sorted(schemas)),
            "required_targets": _REQUIRED_TARGETS,
        },
        tuple(sorted(all_manifest_ids)),
        tuple(entries_by_id[item.target_id] for item in evidence),
    )


def _validate_receipt_checkpoint(
    data_root: Path, receipt: CollectionCycleReceipt
) -> CollectionCheckpoint:
    """Bind receipt bars to one exact provider checkpoint, allowing owned action nodes."""
    provider_manifest_ids = tuple(
        manifest_id
        for target in receipt.targets
        for manifest_id in target.manifest_ids.ordered_values()
    )
    owners = CheckpointStore(data_root).checkpoints_for_manifests(
        provider_manifest_ids
    )
    if set(owners) != set(provider_manifest_ids):
        raise ValueError("cycle receipt manifest lacks one checkpoint owner")
    checkpoints = tuple(owners.values())
    checkpoint = checkpoints[0]
    if any(item != checkpoint for item in checkpoints[1:]) or not set(
        provider_manifest_ids
    ).issubset(checkpoint.manifest_ids):
        raise ValueError("cycle receipt does not bind one exact provider checkpoint")
    if (
        checkpoint.job_id != receipt.job_id
        or checkpoint.run_id != receipt.run_id
        or checkpoint.attempt != receipt.attempt
        or checkpoint.quality_report_id != receipt.quality_report_id
    ):
        raise ValueError("cycle receipt identity disagrees with its checkpoint")
    if receipt.provider == "hyperliquid-public" and set(
        checkpoint.manifest_ids
    ) != set(provider_manifest_ids):
        raise ValueError("Hyperliquid receipt must cover its complete checkpoint")
    if receipt.provider == "moomoo-opend":
        manifests = tuple(
            ManifestStore(data_root).open(manifest_id).manifest
            for manifest_id in checkpoint.manifest_ids
        )
        expected_nodes = {
            node
            for target in receipt.targets
            for node in (
                (target.canonical_instrument, ArtifactLayer.RAW, DataKind.BARS, target.interval),
                (
                    target.canonical_instrument,
                    ArtifactLayer.RAW,
                    DataKind.ADJUSTMENT_FACTORS,
                    None,
                ),
                (target.canonical_instrument, ArtifactLayer.RAW, DataKind.SPLITS, None),
                (target.canonical_instrument, ArtifactLayer.RAW, DataKind.DIVIDENDS, None),
                (
                    target.canonical_instrument,
                    ArtifactLayer.NORMALIZED,
                    DataKind.BARS,
                    target.interval,
                ),
                (
                    target.canonical_instrument,
                    ArtifactLayer.NORMALIZED,
                    DataKind.SPLITS,
                    None,
                ),
                (
                    target.canonical_instrument,
                    ArtifactLayer.ADJUSTED,
                    DataKind.BARS,
                    target.interval,
                ),
                (
                    target.canonical_instrument,
                    ArtifactLayer.FEATURE,
                    DataKind.BARS,
                    target.interval,
                ),
            )
        }
        actual_nodes = {
            (
                item.canonical_instrument.value,
                item.layer,
                item.data_kind,
                item.interval,
            )
            for item in manifests
        }
        if (
            len(manifests) != len(expected_nodes)
            or actual_nodes != expected_nodes
            or any(
                item.code_commit != receipt.code_commit
                or item.collection_run_id != receipt.run_id
                for item in manifests
            )
        ):
            raise ValueError("Moomoo receipt checkpoint contains an unexpected node")
    return checkpoint


def observe_v2(
    evidence_root: Path,
    data_root: Path,
    *,
    cycle_receipt_paths: tuple[Path, Path],
    source_contract_id: str,
    now: datetime,
    code_commit: str,
) -> SoakReportV2:
    instant = _utc(now, "observation time")
    loaded = tuple(_read_cycle_receipt(path) for path in cycle_receipt_paths)
    by_provider = {receipt.provider: receipt for receipt in loaded}
    if set(by_provider) != {"hyperliquid-public", "moomoo-opend"}:
        raise ValueError("observation requires one receipt for each exact provider")
    receipts = (by_provider["hyperliquid-public"], by_provider["moomoo-opend"])
    if len({item.collection_cycle for item in receipts}) != 1:
        raise ValueError("cycle receipts use different collection cycles")
    if {item.code_commit for item in receipts} != {code_commit}:
        raise ValueError("cycle receipts use a different producing commit")
    evidence, config, manifest_ids, exact_entries = _v2_explicit_snapshot(
        data_root, receipts
    )
    store = SoakStoreV2(evidence_root)
    existing = store.reports() if store.candidate_path.exists() else ()
    same_day = tuple(item for item in existing if item.report_date == instant.date().isoformat())
    receipt_ids = tuple(sorted(item.receipt_id for item in receipts))
    if same_day:
        if (
            len(same_day) != 1
            or same_day[0].collection_receipt_ids != receipt_ids
            or same_day[0].source_contract_id != source_contract_id
        ):
            raise ValueError("existing v2 daily report disagrees with this exact retry")
        return same_day[0]
    if store.candidate_path.exists():
        candidate = store.load_candidate()
        expected = SoakCandidateV2.build(
            started_at=candidate.started_at,
            source_contract_id=source_contract_id,
            code_commit=code_commit,
            **config,
        )
        if expected.candidate_id != candidate.candidate_id:
            raise ValueError("v2 candidate source or configuration changed")
    else:
        candidate = SoakCandidateV2.build(
            started_at=instant,
            source_contract_id=source_contract_id,
            code_commit=code_commit,
            **config,
        )
        store.write_candidate(candidate, now=instant)
    for receipt in receipts:
        store.write_cycle_receipt(receipt)
    issues: list[str] = []
    sessions: set[str] = set()
    evaluations: set[str] = set()
    checkpoints: set[str] = set()
    for item, entry in zip(evidence, exact_entries, strict=True):
        if entry.quality is None or not entry.trusted_for_research:
            issues.append(f"{item.target_id}:not-trusted")
        elif entry.quality.issue_codes:
            issues.extend(f"{item.target_id}:{code}" for code in entry.quality.issue_codes)
        if entry.quality is not None:
            evaluations.add(entry.quality.evaluation_id)
        checkpoints.add(item.checkpoint_digest)
        if item.provider == "moomoo-opend" and entry.trusted_for_research:
            sessions.add(entry.event_end.date().isoformat())
    report = SoakReportV2.build(
        candidate_id=candidate.candidate_id,
        source_contract_id=source_contract_id,
        code_commit=code_commit,
        config_digest=candidate.config_digest,
        recorded_at=instant,
        report_date=instant.date().isoformat(),
        predecessor_report_id=None if not existing else existing[-1].report_id,
        collection_receipt_ids=receipt_ids,
        manifest_ids=manifest_ids,
        quality_evaluation_ids=tuple(sorted(evaluations)),
        checkpoint_digests=tuple(sorted(checkpoints)),
        target_evidence=evidence,
        completed_xnys_sessions=tuple(sorted(sessions)),
        crypto_observed=all(
            item.provider == "hyperliquid-public"
            for item in evidence
            if item.target in {"BTC", "ETH", "SOL"}
        ),
        critical_issues=tuple(sorted(set(issues))),
    )
    return store.append(report, now=instant)


def _observe(
    evidence_root: Path,
    data_root: Path,
    *,
    now: datetime,
    code_commit: str,
) -> SoakReport:
    instant = _utc(now, "observation time")
    entries, config = _catalog_snapshot(data_root)
    store = SoakStore(evidence_root)
    new_candidate = not store.candidate_path.exists()
    if new_candidate:
        candidate = SoakCandidate.build(
            started_at=instant,
            code_commit=code_commit,
            **config,
        )
    else:
        candidate = store.load_candidate()
        expected = SoakCandidate.build(
            started_at=candidate.started_at,
            code_commit=code_commit,
            **config,
        )
        if expected.candidate_id != candidate.candidate_id:
            raise ValueError("current code or data configuration changed the candidate baseline")
    existing = store.reports()
    if new_candidate and existing:
        raise ValueError("daily reports exist without a frozen candidate baseline")
    report = _build_report(
        candidate,
        entries,
        recorded_at=instant,
        predecessor_report_id=None if not existing else existing[-1].report_id,
    )
    if new_candidate:
        reasons = tuple(report.critical_issues) + _verify_data_closure(
            data_root, candidate, (report,)
        )
        if reasons:
            raise ValueError(
                "candidate does not satisfy initial qualification: " + "; ".join(reasons)
            )
        store.write_candidate(candidate, now=instant)
    store.append(report, now=instant)
    return report


def observe(evidence_root: Path, data_root: Path) -> SoakReport:
    """Record one real-time observation bound to the current clean commit."""
    return _observe(
        evidence_root,
        data_root,
        now=datetime.now(UTC),
        code_commit=_git_commit(),
    )


def replay_historical(
    data_root: Path,
    *,
    min_crypto_windows: int = 7,
    min_xnys_sessions: int = 4,
) -> dict[str, Any]:
    """Historical-replay functional acceptance.

    Replays the daily frontier, lineage and calendar invariants against real
    per-day collections using each manifest's own event time. This mode is
    explicitly labeled: it never rewrites timestamps and never claims to be a
    real-time observation.
    """
    catalog = TrustedDataCatalog(data_root)
    store = ManifestStore(data_root)
    entries = catalog.entries()
    if not entries:
        raise ValueError("trusted-data catalog is empty")

    reasons: list[str] = []
    crypto_datasets = sorted(
        {
            entry.dataset_id
            for entry in entries
            if entry.provider_id == "hyperliquid-public"
            and entry.layer is ArtifactLayer.ADJUSTED
            and entry.data_kind is DataKind.BARS
        }
    )
    crypto_windows: dict[str, int] = {}
    for dataset_id in crypto_datasets:
        revisions = sorted(
            (
                manifest
                for manifest in store.manifests(dataset_id)
                if manifest.layer is ArtifactLayer.ADJUSTED
            ),
            key=lambda manifest: manifest.compatibility_revision,
        )
        ends = [manifest.event_end for manifest in revisions]
        crypto_windows[dataset_id] = len(set(ends))
        if len(set(ends)) < min_crypto_windows:
            reasons.append(
                f"{dataset_id}: {len(set(ends))} distinct windows; "
                f"{min_crypto_windows} required"
            )
        # Compare in collection (revision) order, not event order, so a
        # non-advancing frontier is actually detected.
        for previous, current in zip(ends, ends[1:]):
            if current <= previous:
                reasons.append(f"{dataset_id}: crypto frontier did not advance")
        for manifest in revisions:
            dataset = store.open(manifest.manifest_id)
            for reference in dataset.manifest.objects:
                dataset.objects.get_bytes(reference)

    xnys_sessions: set[str] = set()
    for entry in entries:
        quality = entry.quality
        if quality is None:
            reasons.append(f"{entry.dataset_id}:quality-unavailable")
            continue
        if quality.synthetic_row_count:
            reasons.append(f"{entry.dataset_id}:synthetic-rows")
        functional_issues = [
            code for code in quality.issue_codes if code not in _REPLAY_IGNORED_ISSUES
        ]
        if entry.provider_id == "moomoo-opend" and not entry.trusted_for_research:
            reasons.append(f"{entry.dataset_id}:not-trusted")
        reasons.extend(f"{entry.dataset_id}:{code}" for code in functional_issues)
        if (
            entry.provider_id == "moomoo-opend"
            and entry.layer is ArtifactLayer.ADJUSTED
            and entry.data_kind is DataKind.BARS
            and entry.session_policy.value == "regular"
        ):
            for bar in store.open(entry.manifest_id).read_bars():
                xnys_sessions.add(bar.timestamp.date().isoformat())
    if len(xnys_sessions) < min_xnys_sessions:
        reasons.append(
            f"XNYS coverage has {len(xnys_sessions)} sessions; "
            f"{min_xnys_sessions} required"
        )

    return {
        "mode": "historical-replay",
        "accepted": not reasons,
        "reasons": tuple(sorted(set(reasons))),
        "crypto_windows": crypto_windows,
        "xnys_sessions": tuple(sorted(xnys_sessions)),
        "code_commit": _git_commit(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    observe_command = commands.add_parser("observe", help="append one immutable UTC report")
    observe_command.add_argument(
        "--evidence-root",
        type=Path,
        default=Path(".quantmesh-evidence/trusted-data"),
    )
    observe_command.add_argument("--data-root", type=Path, required=True)
    observe_command.add_argument(
        "--cycle-receipt",
        type=Path,
        action="append",
        default=[],
        help="exact collection receipt; v2 requires one per provider",
    )
    observe_command.add_argument("--source-contract-id")
    verify_command = commands.add_parser("verify", help="verify a frozen evidence window")
    verify_command.add_argument(
        "--evidence-root",
        type=Path,
        default=Path(".quantmesh-evidence/trusted-data"),
    )
    verify_command.add_argument("--data-root", type=Path, required=True)
    verify_command.add_argument("--minimum-hours", type=int, default=168)
    verify_command.add_argument("--minimum-xnys-sessions", type=int, default=4)
    replay_command = commands.add_parser(
        "replay", help="historical-replay functional acceptance"
    )
    replay_command.add_argument("--data-root", type=Path, required=True)
    replay_command.add_argument("--min-crypto-windows", type=int, default=7)
    replay_command.add_argument("--min-xnys-sessions", type=int, default=4)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "observe":
            if args.cycle_receipt:
                if len(args.cycle_receipt) != 2 or not args.source_contract_id:
                    raise ValueError(
                        "v2 observe requires two cycle receipts and a source contract ID"
                    )
                report = observe_v2(
                    args.evidence_root,
                    args.data_root,
                    cycle_receipt_paths=tuple(args.cycle_receipt),
                    source_contract_id=args.source_contract_id,
                    now=datetime.now(UTC),
                    code_commit=_git_commit(),
                )
            else:
                report = observe(args.evidence_root, args.data_root)
            print(report.model_dump_json())
            return 0
        if args.command == "replay":
            result = replay_historical(
                args.data_root,
                min_crypto_windows=args.min_crypto_windows,
                min_xnys_sessions=args.min_xnys_sessions,
            )
            print(json.dumps(result, sort_keys=True))
            return 0 if result["accepted"] else 1
        result = verify_soak(
            args.evidence_root,
            args.data_root,
            minimum_hours=args.minimum_hours,
            minimum_xnys_sessions=args.minimum_xnys_sessions,
        )
        print(result.model_dump_json())
        return 0 if result.accepted else 1
    except Exception as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
