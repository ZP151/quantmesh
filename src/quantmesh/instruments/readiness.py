"""Exact trusted-data readiness for persisted decision packet evidence."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import Field, field_validator

from quantmesh.data.catalog import (
    CatalogIntegrityError,
    CatalogLineage,
    CatalogNotFoundError,
)
from quantmesh.instruments.contracts import DecisionPacket, StrictContract


class ExactCatalogReader(Protocol):
    """The deliberately narrow catalog surface allowed to readiness reads."""

    def lineage(self, manifest_id: str) -> CatalogLineage: ...


CatalogProvider = Callable[[], ExactCatalogReader | None]


class DecisionReadinessEvidenceRef(StrictContract):
    manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluation_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    report_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    evaluated_at: datetime

    @field_validator("evaluated_at")
    @classmethod
    def evaluated_at_is_utc(cls, value: datetime) -> datetime:
        return _utc(value, "evaluated_at")


class DecisionReadiness(StrictContract):
    status: Literal["ready", "demo", "blocked", "unavailable"]
    checked_at: datetime
    limiting_evidence_at: datetime | None = None
    reason_code: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    history: DecisionReadinessEvidenceRef | None = None
    forecast: DecisionReadinessEvidenceRef | None = None

    @field_validator("checked_at", "limiting_evidence_at")
    @classmethod
    def readiness_times_are_utc(cls, value: datetime | None, info) -> datetime | None:
        return None if value is None else _utc(value, info.field_name)


class DecisionSessionSummary(StrictContract):
    generated_at: datetime
    last_checked_at: datetime | None
    registered_count: int = Field(ge=0)
    triggered_count: int = Field(ge=0)
    blocked_count: int = Field(ge=0)

    @field_validator("generated_at", "last_checked_at")
    @classmethod
    def session_times_are_utc(cls, value: datetime | None, info) -> datetime | None:
        return None if value is None else _utc(value, info.field_name)


class _Qualification(StrictContract):
    status: Literal["ready", "blocked", "unavailable"]
    reason_code: str
    reason: str
    evidence: DecisionReadinessEvidenceRef | None = None


class DecisionReadinessService:
    """Evaluate only the immutable evidence IDs named by one packet."""

    def __init__(self, *, catalog_provider: CatalogProvider) -> None:
        self._catalog_provider = catalog_provider

    def evaluate(self, packet: DecisionPacket, *, checked_at: datetime) -> DecisionReadiness:
        checked_at = _utc(checked_at, "checked_at")
        evidence = packet.evidence
        if evidence.history_source == "demo-synthetic":
            if evidence.forecast_artifact_id is not None and evidence.forecast_synthetic is False:
                catalog = self._catalog_provider()
                if catalog is None:
                    return _unavailable(
                        checked_at,
                        "catalog_unavailable",
                        "Trusted evidence catalog is unavailable.",
                        packet,
                    )
                forecast = _qualify_packet_forecast(catalog, packet)
                if forecast.status != "ready":
                    return _from_qualification(
                        checked_at, forecast, packet, evidence_field="forecast"
                    )
                return _demo_readiness(packet, checked_at, forecast.evidence)
            return _demo_readiness(packet, checked_at)
        if evidence.history_manifest_id is None or evidence.history_quality_evaluation_id is None:
            return _blocked(
                checked_at,
                "missing_history_binding",
                "Exact history manifest and quality evaluation are required.",
                packet,
            )
        catalog = self._catalog_provider()
        if catalog is None:
            return _unavailable(
                checked_at,
                "catalog_unavailable",
                "Trusted evidence catalog is unavailable.",
                packet,
            )
        history = _qualify_exact(
            catalog,
            manifest_id=evidence.history_manifest_id,
            evaluation_id=evidence.history_quality_evaluation_id,
            label="history",
        )
        if history.status != "ready":
            return _from_qualification(checked_at, history, packet, evidence_field="history")
        forecast = _qualify_packet_forecast(catalog, packet)
        if forecast.status != "ready":
            return _from_qualification(
                checked_at,
                forecast,
                packet,
                evidence_field="forecast",
                history=history.evidence,
            )
        return DecisionReadiness(
            status="ready",
            checked_at=checked_at,
            limiting_evidence_at=_packet_limiting_evidence_at(
                packet, history.evidence, forecast.evidence
            ),
            reason_code="trusted_evidence",
            reason="Exact packet evidence is trusted for research.",
            history=history.evidence,
            forecast=forecast.evidence,
        )


def _qualify_packet_forecast(
    catalog: ExactCatalogReader,
    packet: DecisionPacket,
) -> _Qualification:
    evidence = packet.evidence
    if evidence.forecast_artifact_id is None or evidence.forecast_synthetic is True:
        return _Qualification(
            status="ready",
            reason_code="no_real_forecast",
            reason="No real forecast closure is required.",
        )
    if evidence.forecast_manifest_id is None or evidence.forecast_quality_evaluation_id is None:
        return _Qualification(
            status="blocked",
            reason_code="missing_forecast_binding",
            reason="Exact forecast manifest and quality evaluation are required.",
        )
    return _qualify_exact(
        catalog,
        manifest_id=evidence.forecast_manifest_id,
        evaluation_id=evidence.forecast_quality_evaluation_id,
        label="forecast",
    )


def _qualify_exact(
    catalog: ExactCatalogReader,
    *,
    manifest_id: str,
    evaluation_id: str,
    label: Literal["history", "forecast"],
) -> _Qualification:
    try:
        lineage = catalog.lineage(manifest_id)
    except CatalogNotFoundError:
        return _unavailable_qualification(
            f"{label}_manifest_unavailable", f"Exact {label} manifest is unavailable."
        )
    except (CatalogIntegrityError, KeyError, OSError):
        return _unavailable_qualification(
            f"{label}_catalog_unavailable", f"Exact {label} catalog closure is unavailable."
        )
    entry = lineage.entry
    if entry.manifest_id != manifest_id:
        return _unavailable_qualification(
            f"{label}_manifest_mismatch",
            f"Exact {label} manifest identity does not match this packet.",
        )
    quality = entry.quality
    if quality is None or entry.latest_checkpoint is None:
        return _blocked_qualification(
            f"{label}_quality_unavailable", f"Exact {label} quality evidence is unavailable."
        )
    reference = DecisionReadinessEvidenceRef(
        manifest_id=manifest_id,
        evaluation_id=evaluation_id,
        report_id=quality.report_id,
        evaluated_at=quality.evaluated_at,
    )
    if quality.evaluation_id != evaluation_id:
        return _blocked_qualification(
            f"{label}_evaluation_mismatch",
            "Exact quality evaluation does not match this packet.",
            reference,
        )
    if entry.latest_checkpoint.quality_report_id != quality.report_id:
        return _blocked_qualification(
            f"{label}_checkpoint_mismatch",
            f"Exact {label} quality report does not match its checkpoint.",
            reference,
        )
    if not quality.source_rights_known:
        return _blocked_qualification(
            f"{label}_rights_unknown", f"Exact {label} source rights are unknown.", reference
        )
    if not entry.trusted_for_research:
        return _blocked_qualification(
            f"{label}_not_trusted",
            f"Exact {label} evidence is not trusted for research.",
            reference,
        )
    return _Qualification(
        status="ready",
        reason_code=f"{label}_trusted",
        reason=f"Exact {label} evidence is trusted for research.",
        evidence=reference,
    )


def _from_qualification(
    checked_at: datetime,
    qualification: _Qualification,
    packet: DecisionPacket,
    *,
    evidence_field: Literal["history", "forecast"],
    history: DecisionReadinessEvidenceRef | None = None,
) -> DecisionReadiness:
    history_evidence = qualification.evidence if evidence_field == "history" else history
    forecast_evidence = qualification.evidence if evidence_field == "forecast" else None
    return DecisionReadiness(
        status=qualification.status,
        checked_at=checked_at,
        limiting_evidence_at=_packet_limiting_evidence_at(
            packet, history_evidence, forecast_evidence
        ),
        reason_code=qualification.reason_code,
        reason=qualification.reason,
        history=history_evidence,
        forecast=forecast_evidence,
    )


def _blocked(
    checked_at: datetime, reason_code: str, reason: str, packet: DecisionPacket
) -> DecisionReadiness:
    return DecisionReadiness(
        status="blocked",
        checked_at=checked_at,
        limiting_evidence_at=_packet_limiting_evidence_at(packet),
        reason_code=reason_code,
        reason=reason,
    )


def _unavailable(
    checked_at: datetime, reason_code: str, reason: str, packet: DecisionPacket
) -> DecisionReadiness:
    return DecisionReadiness(
        status="unavailable",
        checked_at=checked_at,
        limiting_evidence_at=_packet_limiting_evidence_at(packet),
        reason_code=reason_code,
        reason=reason,
    )


def _blocked_qualification(
    reason_code: str,
    reason: str,
    evidence: DecisionReadinessEvidenceRef | None = None,
) -> _Qualification:
    return _Qualification(
        status="blocked", reason_code=reason_code, reason=reason, evidence=evidence
    )


def _unavailable_qualification(reason_code: str, reason: str) -> _Qualification:
    return _Qualification(status="unavailable", reason_code=reason_code, reason=reason)


def _demo_readiness(
    packet: DecisionPacket,
    checked_at: datetime,
    forecast: DecisionReadinessEvidenceRef | None = None,
) -> DecisionReadiness:
    return DecisionReadiness(
        status="demo",
        checked_at=checked_at,
        limiting_evidence_at=_packet_limiting_evidence_at(packet, forecast),
        reason_code="demo_evidence",
        reason="This packet uses demo-synthetic evidence.",
        forecast=forecast,
    )


def _packet_limiting_evidence_at(
    packet: DecisionPacket,
    *references: DecisionReadinessEvidenceRef | None,
) -> datetime:
    timestamps = [packet.evidence.history_generated_at]
    if packet.evidence.forecast_generated_at is not None:
        timestamps.append(packet.evidence.forecast_generated_at)
    timestamps.extend(item.evaluated_at for item in references if item is not None)
    return min(timestamps)


def _utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)
