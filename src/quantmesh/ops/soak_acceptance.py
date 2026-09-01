"""Compose provider, daily, connection and outbox evidence without extending its clock."""

from __future__ import annotations

import argparse
import hashlib
import math
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.artifacts import canonical_json_bytes
from quantmesh.ops.connection_witness import (
    ConnectionAttemptReservationV1,
    ConnectionWitnessReceiptV1,
    ConnectionWitnessStatus,
    ConnectionWitnessStore,
    ExecutionKind,
    SlotAuthority,
)
from quantmesh.ops.immutable_runs import (
    DailyRunReceiptV1,
    DailyRunStatus,
    ImmutableRunStore,
    SoakVerificationProof,
    publish_create_once,
    read_safe_bytes,
    reject_reparse_chain,
)
from quantmesh.ops.trusted_data_soak import (
    SoakCandidateV2,
    SoakReportV2,
    SoakStoreV2,
    SoakVerification,
    verify_soak,
)
from quantmesh.ops.witness_outbox import WitnessIntentV1, WitnessKind, WitnessOutbox

_DIGEST_PATTERN = r"^[0-9a-f]{64}$"
_COMMIT_PATTERN = r"^[0-9a-f]{40}$"
_SLOT_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}Z$"
_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
_MAX_DAILY_GAP = timedelta(hours=26)
_FINAL_MINIMUM_HOURS = 168
_FINAL_MINIMUM_XNYS_SESSIONS = 4
_SCHEDULE_TIMEZONE = "Asia/Singapore"
_CONNECTION_INTERVAL_MINUTES = 120
_CONNECTION_MINUTE = 10
_CONNECTION_EARLY_SECONDS = 120
_CONNECTION_LATE_SECONDS = 900


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{label} must be UTC")
    return value.astimezone(UTC)


class DailyReportBindingV1(_FrozenContract):
    report_date: str = Field(pattern=_DATE_PATTERN)
    report_id: str = Field(pattern=_DIGEST_PATTERN)
    terminal_receipt_ids: tuple[str, ...] = Field(min_length=1)
    canonical_pass_receipt_id: str = Field(pattern=_DIGEST_PATTERN)

    @model_validator(mode="after")
    def chain_is_canonical(self) -> Self:
        if len(set(self.terminal_receipt_ids)) != len(self.terminal_receipt_ids):
            raise ValueError("daily binding receipt IDs must be unique")
        if self.canonical_pass_receipt_id != self.terminal_receipt_ids[-1]:
            raise ValueError("daily canonical receipt must end its recovery chain")
        return self


class ConnectionSlotBindingV1(_FrozenContract):
    slot: str = Field(pattern=_SLOT_PATTERN)
    scheduled_receipt_ids: tuple[str, ...] = Field(min_length=1)
    statuses: tuple[ConnectionWitnessStatus, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def attempts_are_canonical(self) -> Self:
        if len(self.scheduled_receipt_ids) != len(self.statuses):
            raise ValueError("connection receipt and status counts must match")
        if len(set(self.scheduled_receipt_ids)) != len(self.scheduled_receipt_ids):
            raise ValueError("connection receipt IDs must be unique")
        return self


class OperationalSoakAcceptanceV1(_FrozenContract):
    contract: str = Field(
        default="operational-soak-acceptance-v1",
        pattern=r"^operational-soak-acceptance-v1$",
    )
    expected_commit: str = Field(pattern=_COMMIT_PATTERN)
    expected_source_contract_id: str = Field(pattern=_DIGEST_PATTERN)
    candidate_id: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    config_digest: str | None = Field(default=None, pattern=_DIGEST_PATTERN)
    evidence_started_at: datetime | None = None
    evidence_as_of: datetime | None = None
    minimum_hours: int = Field(ge=_FINAL_MINIMUM_HOURS)
    minimum_xnys_sessions: int = Field(ge=_FINAL_MINIMUM_XNYS_SESSIONS)
    provider_verification: SoakVerificationProof
    daily_bindings: tuple[DailyReportBindingV1, ...]
    required_connection_slots: tuple[str, ...]
    connection_bindings: tuple[ConnectionSlotBindingV1, ...]
    supplemental_receipt_ids: tuple[str, ...]
    outbox_intent_ids: tuple[str, ...]
    accepted: bool
    reasons: tuple[str, ...]
    acceptance_id: str = Field(pattern=_DIGEST_PATTERN)

    @field_validator("evidence_started_at", "evidence_as_of")
    @classmethod
    def evidence_times_are_utc(cls, value: datetime | None, info: Any) -> datetime | None:
        return None if value is None else _utc(value, info.field_name)

    @model_validator(mode="after")
    def result_is_canonical(self) -> Self:
        if self.reasons != tuple(sorted(set(self.reasons))):
            raise ValueError("operational acceptance reasons must be sorted and unique")
        if self.required_connection_slots != tuple(
            sorted(set(self.required_connection_slots))
        ):
            raise ValueError("required connection slots must be sorted and unique")
        binding_slots = tuple(item.slot for item in self.connection_bindings)
        if binding_slots != tuple(sorted(set(binding_slots))):
            raise ValueError("connection bindings must be sorted and unique")
        if self.supplemental_receipt_ids != tuple(
            sorted(set(self.supplemental_receipt_ids))
        ):
            raise ValueError("supplemental receipt IDs must be sorted and unique")
        if self.outbox_intent_ids != tuple(sorted(set(self.outbox_intent_ids))):
            raise ValueError("outbox intent IDs must be sorted and unique")
        if self.accepted:
            if self.reasons:
                raise ValueError("accepted operational evidence cannot contain reasons")
            if (
                self.candidate_id is None
                or self.config_digest is None
                or self.evidence_started_at is None
                or self.evidence_as_of is None
                or not self.provider_verification.accepted
                or self.provider_verification.reasons
                or self.provider_verification.candidate_id != self.candidate_id
                or self.provider_verification.observed_hours < self.minimum_hours
                or self.provider_verification.xnys_session_count
                < self.minimum_xnys_sessions
                or self.provider_verification.report_count != len(self.daily_bindings)
                or not self.daily_bindings
                or not self.outbox_intent_ids
                or binding_slots != self.required_connection_slots
                or any(
                    status
                    not in {
                        ConnectionWitnessStatus.PASSED,
                        ConnectionWitnessStatus.IN_PROGRESS,
                    }
                    for binding in self.connection_bindings
                    for status in binding.statuses
                )
            ):
                raise ValueError("accepted operational evidence lacks its exact proof")
        elif not self.reasons:
            raise ValueError("rejected operational evidence requires typed reasons")
        body = self.model_dump(mode="json", exclude={"acceptance_id"})
        if self.acceptance_id != _digest(body):
            raise ValueError("operational acceptance ID disagrees with its body")
        return self

    @classmethod
    def build(cls, **values: Any) -> OperationalSoakAcceptanceV1:
        values = {
            **values,
            "reasons": tuple(sorted(set(values.get("reasons", ())))),
            "supplemental_receipt_ids": tuple(
                sorted(set(values.get("supplemental_receipt_ids", ())))
            ),
            "outbox_intent_ids": tuple(sorted(set(values.get("outbox_intent_ids", ())))),
        }
        probe = cls.model_construct(**values, acceptance_id="0" * 64)
        return cls(
            **values,
            acceptance_id=_digest(
                probe.model_dump(mode="json", exclude={"acceptance_id"})
            ),
        )

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class OperationalAcceptanceStore:
    """Create-once operational results without a mutable latest pointer."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        if not self.root.is_absolute():
            raise ValueError("operational acceptance root must be absolute")
        self.acceptance_dir = self.root / "acceptances"

    def acceptance_path(self, acceptance_id: str) -> Path:
        if re.fullmatch(_DIGEST_PATTERN, acceptance_id) is None:
            raise ValueError("operational acceptance ID must be a digest")
        return self.acceptance_dir / f"{acceptance_id}.json"

    def publish(self, result: OperationalSoakAcceptanceV1) -> OperationalSoakAcceptanceV1:
        self._prepare()
        validated = OperationalSoakAcceptanceV1.model_validate(
            result.model_dump(mode="python")
        )
        publish_create_once(
            self.acceptance_path(validated.acceptance_id),
            validated.canonical_bytes(),
            label="operational acceptance",
        )
        return self.load(validated.acceptance_id)

    def load(self, acceptance_id: str) -> OperationalSoakAcceptanceV1:
        path = self.acceptance_path(acceptance_id)
        payload = read_safe_bytes(path)
        result = OperationalSoakAcceptanceV1.model_validate_json(payload)
        if result.acceptance_id != acceptance_id or path.stem != result.acceptance_id:
            raise ValueError("operational acceptance path disagrees with its body")
        if payload != result.canonical_bytes():
            raise ValueError("operational acceptance JSON is not canonical")
        return result

    def results(self) -> tuple[OperationalSoakAcceptanceV1, ...]:
        self._prepare()
        paths = tuple(self.acceptance_dir.iterdir())
        if any(
            path.suffix != ".json" or re.fullmatch(_DIGEST_PATTERN, path.stem) is None
            for path in paths
        ):
            raise ValueError("operational acceptance store contains an unexpected entry")
        return tuple(self.load(path.stem) for path in sorted(paths))

    def _prepare(self) -> None:
        reject_reparse_chain(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        reject_reparse_chain(self.root)
        self.acceptance_dir.mkdir(parents=True, exist_ok=True)
        reject_reparse_chain(self.acceptance_dir)


ProviderVerifier = Callable[..., SoakVerification]


def required_connection_slots(
    evidence_started_at: datetime,
    evidence_as_of: datetime,
    *,
    timezone_id: str = _SCHEDULE_TIMEZONE,
    interval_minutes: int = _CONNECTION_INTERVAL_MINUTES,
    minute: int = _CONNECTION_MINUTE,
) -> tuple[str, ...]:
    started = _utc(evidence_started_at, "candidate start")
    finished = _utc(evidence_as_of, "evidence end")
    if finished < started:
        raise ValueError("evidence end cannot precede candidate start")
    if interval_minutes <= 0 or 1440 % interval_minutes != 0:
        raise ValueError("connection interval must divide one wall-clock day")
    if minute < 0 or minute > 59:
        raise ValueError("connection minute is invalid")
    timezone = ZoneInfo(timezone_id)
    local_start = started.astimezone(timezone)
    local_end = finished.astimezone(timezone)
    boundary = local_start.replace(hour=0, minute=minute, second=0, microsecond=0)
    interval = timedelta(minutes=interval_minutes)
    while boundary < local_start:
        boundary += interval
    slots: list[str] = []
    while boundary <= local_end:
        slots.append(boundary.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ"))
        boundary += interval
    if len(slots) != len(set(slots)):
        raise ValueError("connection wall-clock cadence produced an ambiguous UTC slot")
    return tuple(slots)


def _slot_time(slot: str) -> datetime:
    return datetime.strptime(slot, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)


def _slot_token(slot: str) -> str:
    return _slot_time(slot).strftime("%Y-%m-%dT%H%MZ")


def _all_daily_terminals(root: Path) -> tuple[DailyRunReceiptV1, ...]:
    store = ImmutableRunStore(root)
    if not store.terminal_dir.exists():
        return ()
    reject_reparse_chain(store.terminal_dir)
    directories = tuple(store.terminal_dir.iterdir())
    if any(
        not path.is_dir() or re.fullmatch(_DATE_PATTERN, path.name) is None
        for path in directories
    ):
        raise ValueError("daily terminal store contains an unexpected slot")
    terminals = [
        terminal
        for directory in sorted(directories)
        for terminal in store.terminals(directory.name)
    ]
    return tuple(terminals)


def _all_connection_terminals(root: Path) -> tuple[ConnectionWitnessReceiptV1, ...]:
    store = ConnectionWitnessStore(root)
    if not store.terminal_dir.exists():
        return ()
    reject_reparse_chain(store.terminal_dir)
    directories = tuple(store.terminal_dir.iterdir())
    if any(
        not path.is_dir() or re.fullmatch(r"^\d{4}-\d{2}-\d{2}T\d{4}Z$", path.name) is None
        for path in directories
    ):
        raise ValueError("connection terminal store contains an unexpected slot")
    terminals: list[ConnectionWitnessReceiptV1] = []
    for directory in sorted(directories):
        slot = datetime.strptime(directory.name, "%Y-%m-%dT%H%MZ").replace(
            tzinfo=UTC
        ).strftime("%Y-%m-%dT%H:%MZ")
        terminals.extend(store.terminals(slot))
    return tuple(terminals)


def _reservations(
    store: ConnectionWitnessStore, slot: str
) -> tuple[ConnectionAttemptReservationV1, ...]:
    directory = store.reservation_dir / _slot_token(slot)
    if not directory.exists():
        return ()
    reject_reparse_chain(directory)
    paths = tuple(directory.iterdir())
    if any(path.suffix != ".json" or not path.stem.isdigit() for path in paths):
        raise ValueError("connection reservation slot contains an unexpected entry")
    return tuple(
        store.load_reservation(slot, int(path.stem))
        for path in sorted(paths, key=lambda item: int(item.stem))
    )


def _daily_expected_intent(terminal: DailyRunReceiptV1) -> WitnessIntentV1:
    return WitnessIntentV1.build(
        issue_number=124,
        witness_kind=WitnessKind.DAILY_ACCEPTED,
        local_evidence_id=terminal.run_id,
        terminal_receipt_id=terminal.receipt_id,
        report_id=terminal.soak_report_id,
        source_contract_id=terminal.source_contract_id,
        code_commit=terminal.code_commit,
        occurred_at=terminal.finished_at,
        summary=f"daily slot {terminal.slot} attempt {terminal.attempt} accepted",
    )


def _connection_expected_intent(
    terminal: ConnectionWitnessReceiptV1,
) -> WitnessIntentV1:
    return WitnessIntentV1.build(
        issue_number=127,
        witness_kind=WitnessKind.CONNECTION_STATE,
        local_evidence_id=terminal.run_id,
        terminal_receipt_id=terminal.receipt_id,
        report_id=terminal.soak_report_id,
        source_contract_id=terminal.expected_source_contract_id,
        code_commit=terminal.expected_commit,
        occurred_at=terminal.finished_at,
        summary=(
            f"connection slot {terminal.slot} attempt {terminal.attempt} "
            f"{terminal.execution_kind.value} {terminal.status.value}"
        ),
    )


def _proof(result: SoakVerification) -> SoakVerificationProof:
    return SoakVerificationProof(
        accepted=result.accepted,
        reasons=tuple(sorted(set(result.reasons))),
        candidate_id=result.candidate_id,
        report_count=result.report_count,
        observed_hours=result.observed_hours,
        xnys_session_count=result.xnys_session_count,
    )


def _validate_roots(paths: tuple[Path, ...]) -> None:
    if any(not path.is_absolute() for path in paths):
        raise ValueError("operational acceptance roots must be absolute")
    resolved = tuple(path.resolve() for path in paths)
    if any(
        left == right or left.is_relative_to(right) or right.is_relative_to(left)
        for index, left in enumerate(resolved)
        for right in resolved[index + 1 :]
    ):
        raise ValueError("operational acceptance roots must be pairwise disjoint")


def _validate_daily(
    *,
    candidate: SoakCandidateV2,
    reports: tuple[SoakReportV2, ...],
    run_root: Path,
    expected_commit: str,
    expected_source_contract_id: str,
    reasons: list[str],
) -> tuple[tuple[DailyReportBindingV1, ...], tuple[DailyRunReceiptV1, ...]]:
    try:
        terminals = _all_daily_terminals(run_root)
    except Exception as error:
        reasons.append(f"daily.store-invalid:{type(error).__name__}:{error}")
        return (), ()
    report_ids = {report.report_id for report in reports}
    extras = tuple(item for item in terminals if item.soak_report_id not in report_ids)
    if extras:
        reasons.append("daily.unpaired-terminal")
    bindings: list[DailyReportBindingV1] = []
    admitted: list[DailyRunReceiptV1] = []
    sessions: set[str] = set()
    for index, report in enumerate(reports):
        sessions.update(report.completed_xnys_sessions)
        chain = tuple(item for item in terminals if item.soak_report_id == report.report_id)
        if not chain:
            reasons.append(f"daily.missing-terminal:{report.report_date}")
            continue
        chain = tuple(sorted(chain, key=lambda item: item.attempt))
        for position, terminal in enumerate(chain):
            proof = terminal.verification
            expected_recovery = None if position == 0 else chain[position - 1].run_id
            expected_hours = max(
                0.0,
                (report.recorded_at - candidate.started_at).total_seconds() / 3600,
            )
            if (
                terminal.slot != report.report_date
                or terminal.status is not DailyRunStatus.PASSED
                or terminal.code_commit != expected_commit
                or terminal.source_contract_id != expected_source_contract_id
                or terminal.recovery_of_run_id != expected_recovery
                or (position > 0 and terminal.attempt != chain[position - 1].attempt + 1)
                or terminal.finished_at < report.recorded_at
                or {
                    terminal.hyperliquid_receipt_id,
                    terminal.moomoo_receipt_id,
                }
                != set(report.collection_receipt_ids)
                or proof is None
                or not proof.accepted
                or proof.reasons
                or proof.candidate_id != candidate.candidate_id
                or proof.report_count != index + 1
                or not math.isclose(
                    proof.observed_hours, expected_hours, rel_tol=0, abs_tol=1e-9
                )
                or proof.xnys_session_count != len(sessions)
            ):
                reasons.append(f"daily.binding-mismatch:{report.report_date}")
        bindings.append(
            DailyReportBindingV1(
                report_date=report.report_date,
                report_id=report.report_id,
                terminal_receipt_ids=tuple(item.receipt_id for item in chain),
                canonical_pass_receipt_id=chain[-1].receipt_id,
            )
        )
        admitted.extend(chain)
    if reports:
        try:
            latest = ImmutableRunStore(run_root).latest()
            if not bindings or latest.receipt_id != bindings[-1].canonical_pass_receipt_id:
                reasons.append("daily.latest-pointer-mismatch")
        except Exception as error:
            reasons.append(f"daily.latest-pointer-invalid:{type(error).__name__}:{error}")
    return tuple(bindings), tuple(admitted)


def _validate_connections(
    *,
    candidate: SoakCandidateV2,
    evidence_as_of: datetime,
    run_root: Path,
    expected_commit: str,
    expected_source_contract_id: str,
    daily_terminals: tuple[DailyRunReceiptV1, ...],
    reasons: list[str],
) -> tuple[
    tuple[str, ...],
    tuple[ConnectionSlotBindingV1, ...],
    tuple[ConnectionWitnessReceiptV1, ...],
    tuple[str, ...],
]:
    required = required_connection_slots(candidate.started_at, evidence_as_of)
    store = ConnectionWitnessStore(run_root)
    admitted: list[ConnectionWitnessReceiptV1] = []
    supplemental: list[str] = []
    bindings: list[ConnectionSlotBindingV1] = []
    daily_by_id = {item.receipt_id: item for item in daily_terminals}
    for slot in required:
        try:
            reservations = _reservations(store, slot)
            terminals = store.terminals(slot)
        except Exception as error:
            reasons.append(f"connection.store-invalid:{slot}:{type(error).__name__}:{error}")
            continue
        scheduled_reservations = tuple(
            item for item in reservations if item.execution_kind is ExecutionKind.SCHEDULED
        )
        scheduled = tuple(
            item for item in terminals if item.execution_kind is ExecutionKind.SCHEDULED
        )
        slot_supplemental = tuple(
            item for item in terminals if item.execution_kind is ExecutionKind.SUPPLEMENTAL
        )
        supplemental.extend(item.receipt_id for item in slot_supplemental)
        admitted.extend(slot_supplemental)
        if not scheduled_reservations or not scheduled:
            reasons.append(f"connection.missing-scheduled-terminal:{slot}")
            continue
        if {
            item.reservation_id for item in scheduled_reservations
        } != {item.reservation_id for item in scheduled}:
            reasons.append(f"connection.nonterminal-reservation:{slot}")
        scheduled = tuple(sorted(scheduled, key=lambda item: item.attempt))
        previous: ConnectionWitnessReceiptV1 | None = None
        boundary = _slot_time(slot)
        for terminal in scheduled:
            timing_values = (terminal.slot_source_time, terminal.started_at)
            timing_valid = all(
                value is not None
                and boundary - timedelta(seconds=_CONNECTION_EARLY_SECONDS)
                <= value
                <= boundary + timedelta(seconds=_CONNECTION_LATE_SECONDS)
                for value in timing_values
            )
            daily = (
                None
                if terminal.daily_receipt_id is None
                else daily_by_id.get(terminal.daily_receipt_id)
            )
            passed_binding_valid = (
                terminal.status is not ConnectionWitnessStatus.PASSED
                or (
                    daily is not None
                    and terminal.soak_report_id == daily.soak_report_id
                )
            )
            if (
                terminal.slot_authority is not SlotAuthority.SCHEDULER
                or terminal.expected_commit != expected_commit
                or terminal.expected_source_contract_id != expected_source_contract_id
                or terminal.status
                not in {
                    ConnectionWitnessStatus.PASSED,
                    ConnectionWitnessStatus.IN_PROGRESS,
                }
                or not timing_valid
                or not passed_binding_valid
                or (previous is not None and previous.finished_at > terminal.started_at)
            ):
                reasons.append(f"connection.binding-mismatch:{slot}:attempt-{terminal.attempt}")
            previous = terminal
        bindings.append(
            ConnectionSlotBindingV1(
                slot=slot,
                scheduled_receipt_ids=tuple(item.receipt_id for item in scheduled),
                statuses=tuple(item.status for item in scheduled),
            )
        )
        admitted.extend(scheduled)
    try:
        all_terminals = _all_connection_terminals(run_root)
        if all_terminals:
            expected_latest = max(all_terminals, key=lambda item: (item.slot, item.attempt))
            if store.latest().receipt_id != expected_latest.receipt_id:
                reasons.append("connection.latest-pointer-mismatch")
    except Exception as error:
        reasons.append(f"connection.latest-pointer-invalid:{type(error).__name__}:{error}")
    return required, tuple(bindings), tuple(admitted), tuple(sorted(set(supplemental)))


def _validate_outbox(
    root: Path,
    *,
    daily: tuple[DailyRunReceiptV1, ...],
    connections: tuple[ConnectionWitnessReceiptV1, ...],
    reasons: list[str],
) -> tuple[str, ...]:
    outbox = WitnessOutbox(root)
    intent_ids: list[str] = []
    for label, terminal, expected in (
        *(
            ("daily", terminal, _daily_expected_intent(terminal))
            for terminal in daily
        ),
        *(
            ("connection", terminal, _connection_expected_intent(terminal))
            for terminal in connections
        ),
    ):
        try:
            observed = outbox.intent(expected.idempotency_key)
            if observed != expected:
                raise ValueError("intent body differs from the exact terminal")
            intent_ids.append(observed.intent_id)
        except Exception as error:
            reasons.append(
                f"outbox.{label}-intent-invalid:{terminal.receipt_id}:"
                f"{type(error).__name__}:{error}"
            )
    return tuple(sorted(set(intent_ids)))


def verify_operational_soak(
    *,
    data_root: Path,
    evidence_root: Path,
    daily_run_root: Path,
    connection_run_root: Path,
    outbox_root: Path,
    acceptance_root: Path,
    expected_commit: str,
    expected_source_contract_id: str,
    minimum_hours: int = _FINAL_MINIMUM_HOURS,
    minimum_xnys_sessions: int = _FINAL_MINIMUM_XNYS_SESSIONS,
    provider_verifier: ProviderVerifier = verify_soak,
) -> OperationalSoakAcceptanceV1:
    if minimum_hours < _FINAL_MINIMUM_HOURS:
        raise ValueError("final operational acceptance requires at least 168 hours")
    if minimum_xnys_sessions < _FINAL_MINIMUM_XNYS_SESSIONS:
        raise ValueError("final operational acceptance requires at least four XNYS sessions")
    if re.fullmatch(_COMMIT_PATTERN, expected_commit) is None:
        raise ValueError("expected commit must be a full SHA")
    if re.fullmatch(_DIGEST_PATTERN, expected_source_contract_id) is None:
        raise ValueError("expected source contract must be a digest")
    paths = tuple(
        Path(path)
        for path in (
            data_root,
            evidence_root,
            daily_run_root,
            connection_run_root,
            outbox_root,
            acceptance_root,
        )
    )
    _validate_roots(paths)
    (
        data_root,
        evidence_root,
        daily_run_root,
        connection_run_root,
        outbox_root,
        acceptance_root,
    ) = paths
    reasons: list[str] = []
    try:
        provider = provider_verifier(
            evidence_root,
            data_root,
            minimum_hours=minimum_hours,
            minimum_xnys_sessions=minimum_xnys_sessions,
        )
    except Exception as error:
        provider = SoakVerification(
            accepted=False,
            reasons=(f"provider verifier raised {type(error).__name__}: {error}",),
            candidate_id=None,
            report_count=0,
            observed_hours=0,
            xnys_session_count=0,
        )
    if (
        not provider.accepted
        or provider.reasons
        or provider.observed_hours < minimum_hours
        or provider.xnys_session_count < minimum_xnys_sessions
    ):
        reasons.append("provider.final-verification-rejected")
    reasons.extend(f"provider.reason:{reason}" for reason in provider.reasons)

    candidate: SoakCandidateV2 | None = None
    reports: tuple[SoakReportV2, ...] = ()
    try:
        evidence = SoakStoreV2(evidence_root)
        candidate = evidence.load_candidate()
        reports = evidence.reports()
    except Exception as error:
        reasons.append(f"provider.evidence-invalid:{type(error).__name__}:{error}")

    daily_bindings: tuple[DailyReportBindingV1, ...] = ()
    daily_terminals: tuple[DailyRunReceiptV1, ...] = ()
    required_slots: tuple[str, ...] = ()
    connection_bindings: tuple[ConnectionSlotBindingV1, ...] = ()
    connection_terminals: tuple[ConnectionWitnessReceiptV1, ...] = ()
    supplemental: tuple[str, ...] = ()
    evidence_as_of = None if not reports else reports[-1].recorded_at
    if candidate is not None:
        if (
            candidate.code_commit != expected_commit
            or candidate.source_contract_id != expected_source_contract_id
            or provider.candidate_id != candidate.candidate_id
            or provider.report_count != len(reports)
        ):
            reasons.append("provider.candidate-or-count-mismatch")
        if not reports:
            reasons.append("daily.no-provider-reports")
        else:
            first_gap = reports[0].recorded_at - candidate.started_at
            if first_gap < timedelta(0) or first_gap > _MAX_DAILY_GAP:
                reasons.append("daily-gap.candidate-to-first-report")
            for previous, current in zip(reports, reports[1:]):
                gap = current.recorded_at - previous.recorded_at
                if gap <= timedelta(0) or gap > _MAX_DAILY_GAP:
                    reasons.append(
                        f"daily-gap.report-to-report:{previous.report_date}:"
                        f"{current.report_date}"
                    )
            expected_hours = (
                reports[-1].recorded_at - candidate.started_at
            ).total_seconds() / 3600
            sessions = {
                session for report in reports for session in report.completed_xnys_sessions
            }
            if (
                not math.isclose(
                    provider.observed_hours, expected_hours, rel_tol=0, abs_tol=1e-9
                )
                or provider.xnys_session_count != len(sessions)
            ):
                reasons.append("provider.clock-or-session-mismatch")
        daily_bindings, daily_terminals = _validate_daily(
            candidate=candidate,
            reports=reports,
            run_root=daily_run_root,
            expected_commit=expected_commit,
            expected_source_contract_id=expected_source_contract_id,
            reasons=reasons,
        )
        if evidence_as_of is not None:
            (
                required_slots,
                connection_bindings,
                connection_terminals,
                supplemental,
            ) = _validate_connections(
                candidate=candidate,
                evidence_as_of=evidence_as_of,
                run_root=connection_run_root,
                expected_commit=expected_commit,
                expected_source_contract_id=expected_source_contract_id,
                daily_terminals=daily_terminals,
                reasons=reasons,
            )
    intent_ids = _validate_outbox(
        outbox_root,
        daily=daily_terminals,
        connections=connection_terminals,
        reasons=reasons,
    )
    accepted = not reasons
    result = OperationalSoakAcceptanceV1.build(
        expected_commit=expected_commit,
        expected_source_contract_id=expected_source_contract_id,
        candidate_id=None if candidate is None else candidate.candidate_id,
        config_digest=None if candidate is None else candidate.config_digest,
        evidence_started_at=None if candidate is None else candidate.started_at,
        evidence_as_of=evidence_as_of,
        minimum_hours=minimum_hours,
        minimum_xnys_sessions=minimum_xnys_sessions,
        provider_verification=_proof(provider),
        daily_bindings=daily_bindings,
        required_connection_slots=required_slots,
        connection_bindings=connection_bindings,
        supplemental_receipt_ids=supplemental,
        outbox_intent_ids=intent_ids,
        accepted=accepted,
        reasons=tuple(reasons),
    )
    return OperationalAcceptanceStore(acceptance_root).publish(result)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    verify = commands.add_parser("verify", help="compose final immutable local evidence")
    verify.add_argument("--data-root", required=True, type=Path)
    verify.add_argument("--evidence-root", required=True, type=Path)
    verify.add_argument("--daily-run-root", required=True, type=Path)
    verify.add_argument("--connection-run-root", required=True, type=Path)
    verify.add_argument("--outbox-root", required=True, type=Path)
    verify.add_argument("--acceptance-root", required=True, type=Path)
    verify.add_argument("--expected-commit", required=True)
    verify.add_argument("--expected-source-contract-id", required=True)
    verify.add_argument("--minimum-hours", type=int, default=_FINAL_MINIMUM_HOURS)
    verify.add_argument(
        "--minimum-xnys-sessions",
        type=int,
        default=_FINAL_MINIMUM_XNYS_SESSIONS,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command != "verify":
            raise AssertionError(f"unsupported operational command: {args.command}")
        result = verify_operational_soak(
            data_root=args.data_root,
            evidence_root=args.evidence_root,
            daily_run_root=args.daily_run_root,
            connection_run_root=args.connection_run_root,
            outbox_root=args.outbox_root,
            acceptance_root=args.acceptance_root,
            expected_commit=args.expected_commit,
            expected_source_contract_id=args.expected_source_contract_id,
            minimum_hours=args.minimum_hours,
            minimum_xnys_sessions=args.minimum_xnys_sessions,
        )
        print(result.canonical_bytes().decode("utf-8"))
        return 0 if result.accepted else 1
    except Exception as error:
        print(f"FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
