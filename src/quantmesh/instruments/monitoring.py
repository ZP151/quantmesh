"""Exact-packet local monitoring with typed, restart-safe JSONL replay."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.calendars import (
    CONTINUOUS_UTC_VERSION,
    XNYS_REGULAR_VERSION,
    CalendarService,
    CalendarUnavailableError,
    SessionPolicy,
)
from quantmesh.domain.models import Instrument
from quantmesh.instruments.decision_packets import DecisionPacketStore
from quantmesh.persistence.jsonl import JsonlStore


class WatchConditionKind(StrEnum):
    ENTRY_ZONE = "entry_zone"
    INVALIDATION = "invalidation"
    DATA_STALE = "data_stale"
    FORECAST_DRIFT = "forecast_drift"


_ORDER = tuple(WatchConditionKind)
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _identity(prefix: str, value: object) -> str:
    return f"{prefix}-{hashlib.sha256(_canonical(value)).hexdigest()[:24]}"


def _utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{label} time must be timezone-aware")
    return value.astimezone(UTC)


class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)


class EntryZoneDefinition(_Contract):
    lower: float = Field(gt=0)
    upper: float = Field(gt=0)

    @model_validator(mode="after")
    def ordered(self) -> EntryZoneDefinition:
        if self.lower > self.upper:
            raise ValueError("entry-zone lower bound cannot exceed upper bound")
        return self


class InvalidationDefinition(_Contract):
    level: float = Field(gt=0)


class StaleDefinition(_Contract):
    reference_at: datetime
    history_generated_at: datetime
    forecast_generated_at: datetime | None = None
    calendar_id: Literal["XNYS", "24/7"]
    calendar_version: str = Field(min_length=1)
    session_policy: SessionPolicy
    maximum_completed_sessions: Literal[1] = 1

    @field_validator("reference_at", "history_generated_at", "forecast_generated_at")
    @classmethod
    def utc_reference(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value, "stale evidence")

    @model_validator(mode="after")
    def reference_is_oldest_evidence(self) -> StaleDefinition:
        expected = min(
            value
            for value in (self.history_generated_at, self.forecast_generated_at)
            if value is not None
        )
        if self.reference_at != expected:
            raise ValueError("stale reference must freeze the oldest packet evidence time")
        return self


class DriftDefinition(_Contract):
    baseline_artifact_id: str | None = None
    baseline_generated_at: datetime | None = None
    target_at: datetime | None = None
    baseline_p50: float | None = Field(default=None, gt=0)
    model_name: str | None = None
    model_version: str | None = None
    config_digest: str | None = None
    target: str | None = None
    calendar: str | None = None
    baseline_dataset_id: str | None = None
    baseline_dataset_revision: int | None = Field(default=None, ge=1)
    risk_per_unit: float = Field(gt=0)

    @field_validator("baseline_generated_at", "target_at")
    @classmethod
    def utc_optional(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value, "forecast baseline")


ConditionDefinition = (
    EntryZoneDefinition | InvalidationDefinition | StaleDefinition | DriftDefinition
)


class DecisionWatchCondition(_Contract):
    condition_id: str = Field(pattern=r"^condition-[0-9a-f]{24}$")
    packet_id: str = Field(pattern=r"^packet-[0-9a-f]{24}$")
    kind: WatchConditionKind
    definition: ConditionDefinition

    @model_validator(mode="after")
    def definition_matches_kind(self) -> DecisionWatchCondition:
        expected = {
            WatchConditionKind.ENTRY_ZONE: EntryZoneDefinition,
            WatchConditionKind.INVALIDATION: InvalidationDefinition,
            WatchConditionKind.DATA_STALE: StaleDefinition,
            WatchConditionKind.FORECAST_DRIFT: DriftDefinition,
        }[self.kind]
        if not isinstance(self.definition, expected):
            raise ValueError("watch condition definition does not match its fixed kind")
        payload = {
            "packet_id": self.packet_id,
            "kind": self.kind.value,
            "definition": self.definition.model_dump(mode="json"),
        }
        if self.condition_id != _identity("condition", payload):
            raise ValueError("watch condition identity does not match canonical content")
        return self


class DecisionWatchRegistration(_Contract):
    registration_id: str = Field(pattern=r"^registration-[0-9a-f]{24}$")
    packet_id: str = Field(pattern=r"^packet-[0-9a-f]{24}$")
    conditions: tuple[DecisionWatchCondition, ...] = Field(min_length=1, max_length=4)

    @model_validator(mode="after")
    def canonical_conditions(self) -> DecisionWatchRegistration:
        kinds = tuple(condition.kind for condition in self.conditions)
        if len(set(kinds)) != len(kinds) or kinds != tuple(
            kind for kind in _ORDER if kind in kinds
        ):
            raise ValueError("watch conditions must be unique and fixed-kind ordered")
        if any(condition.packet_id != self.packet_id for condition in self.conditions):
            raise ValueError("watch condition packet binding differs from registration")
        payload = {
            "packet_id": self.packet_id,
            "conditions": [condition.model_dump(mode="json") for condition in self.conditions],
        }
        if self.registration_id != _identity("registration", payload):
            raise ValueError("watch registration identity does not match canonical content")
        return self


class DecisionWatchObservation(_Contract):
    evaluated_at: datetime
    price: float | None = Field(default=None, gt=0)
    instrument: Instrument | None = None
    source: str | None = None
    provenance: str | None = None
    data_time: datetime | None = None
    received_at: datetime | None = None
    sequence: int | None = Field(default=None, ge=0)
    sequence_gap: bool | None = None
    candidate_forecast_artifact_id: str | None = None

    @field_validator("evaluated_at", "data_time", "received_at")
    @classmethod
    def utc_times(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _utc(value, "watch observation")

    @model_validator(mode="after")
    def complete_price_lineage(self) -> DecisionWatchObservation:
        lineage = (
            self.instrument,
            self.source,
            self.provenance,
            self.data_time,
            self.received_at,
            self.sequence,
            self.sequence_gap,
        )
        if self.price is None and any(item is not None for item in lineage):
            raise ValueError("absent price cannot carry partial price lineage")
        if self.price is not None and any(item is None for item in lineage):
            raise ValueError("price observation requires complete lineage")
        return self


class PriceFacts(_Contract):
    previous_price: float | None = Field(default=None, gt=0)
    current_price: float = Field(gt=0)
    lower: float | None = Field(default=None, gt=0)
    upper: float | None = Field(default=None, gt=0)
    level: float | None = Field(default=None, gt=0)


class StaleFacts(_Contract):
    reference_at: datetime
    evaluated_at: datetime
    completed_sessions: int = Field(ge=0)


class DriftFacts(_Contract):
    target_at: datetime
    baseline_p50: float = Field(gt=0)
    candidate_p50: float = Field(gt=0)
    distance: float = Field(ge=0)
    threshold: float = Field(gt=0)


class UnavailableFacts(_Contract):
    code: str = Field(min_length=1)


WatchFacts = PriceFacts | StaleFacts | DriftFacts | UnavailableFacts


def _event_identity(
    condition_id: str, observation: DecisionWatchObservation, facts: WatchFacts
) -> str:
    return _identity(
        "watch-event",
        {
            "condition_id": condition_id,
            "observation": observation.model_dump(mode="json"),
            "facts": facts.model_dump(mode="json"),
        },
    )


class DecisionWatchResult(_Contract):
    condition_id: str = Field(pattern=r"^condition-[0-9a-f]{24}$")
    state: Literal["armed", "not_triggered", "triggered", "not_comparable"]
    facts: WatchFacts
    event_id: str | None = Field(default=None, pattern=r"^watch-event-[0-9a-f]{24}$")

    @model_validator(mode="after")
    def terminal_event_shape(self) -> DecisionWatchResult:
        if (self.state == "triggered") != (self.event_id is not None):
            raise ValueError("only a triggered watch result has an event identity")
        return self


class DecisionWatchEvaluation(_Contract):
    evaluation_id: str = Field(pattern=r"^evaluation-[0-9a-f]{24}$")
    registration_id: str = Field(pattern=r"^registration-[0-9a-f]{24}$")
    observation: DecisionWatchObservation
    results: tuple[DecisionWatchResult, ...]

    @model_validator(mode="after")
    def canonical_identity(self) -> DecisionWatchEvaluation:
        payload = {
            "registration_id": self.registration_id,
            "observation": self.observation.model_dump(mode="json"),
            "results": [result.model_dump(mode="json") for result in self.results],
        }
        if self.evaluation_id != _identity("evaluation", payload):
            raise ValueError("watch evaluation identity does not match canonical content")
        return self


class DecisionWatchActivation(_Contract):
    """One atomic first-registration plus first-evaluation commit."""

    activation_id: str = Field(pattern=r"^activation-[0-9a-f]{24}$")
    registration: DecisionWatchRegistration
    evaluation: DecisionWatchEvaluation

    @model_validator(mode="after")
    def canonical_activation(self) -> DecisionWatchActivation:
        if self.evaluation.registration_id != self.registration.registration_id:
            raise ValueError("watch activation evaluation differs from registration")
        payload = {
            "registration": self.registration.model_dump(mode="json"),
            "evaluation": self.evaluation.model_dump(mode="json"),
        }
        if self.activation_id != _identity("activation", payload):
            raise ValueError("watch activation identity does not match canonical content")
        return self


class DecisionWatchState(_Contract):
    packet_id: str = Field(pattern=r"^packet-[0-9a-f]{24}$")
    registration: DecisionWatchRegistration | None = None
    evaluation: DecisionWatchEvaluation | None = None

    @model_validator(mode="after")
    def packet_binding(self) -> DecisionWatchState:
        if self.registration is not None and self.registration.packet_id != self.packet_id:
            raise ValueError("watch state registration differs from requested packet")
        return self


def _root_lock(root: Path) -> threading.RLock:
    key = str(root.resolve(strict=False)).casefold()
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _interprocess_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".decision-watch.lock"
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class DecisionWatchStore:
    """One monitoring-root lock and one evaluation record per cursor transition."""

    def __init__(self, root: Path) -> None:
        self._lock = _root_lock(root)
        self._local = threading.local()
        self._registrations = JsonlStore(
            root,
            filename="watch-registrations.jsonl",
            model=DecisionWatchRegistration,
            label="decision watch registration store",
            id_label="decision watch registration",
            key=lambda item: item.registration_id,
            extra_validate=self._validate_registration,
        )
        self._evaluations = JsonlStore(
            root,
            filename="watch-evaluations.jsonl",
            model=DecisionWatchEvaluation,
            label="decision watch evaluation store",
            id_label="decision watch evaluation",
            key=lambda item: item.evaluation_id,
            extra_validate=self._validate_evaluation,
        )
        self._activations = JsonlStore(
            root,
            filename="watch-activations.jsonl",
            model=DecisionWatchActivation,
            label="decision watch activation store",
            id_label="decision watch activation",
            key=lambda item: item.activation_id,
            extra_validate=self._validate_activation,
        )

    @property
    def root(self) -> Path:
        return self._registrations.root

    @staticmethod
    def _validate_registration(value: DecisionWatchRegistration) -> None:
        value.canonical_conditions()

    @staticmethod
    def _validate_evaluation(value: DecisionWatchEvaluation) -> None:
        value.canonical_identity()

    @staticmethod
    def _validate_activation(value: DecisionWatchActivation) -> None:
        value.canonical_activation()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        depth = getattr(self._local, "transaction_depth", 0)
        if depth:
            self._local.transaction_depth = depth + 1
            try:
                yield
            finally:
                self._local.transaction_depth -= 1
            return
        with self._lock, _interprocess_lock(self.root):
            self._local.transaction_depth = 1
            try:
                yield
            finally:
                self._local.transaction_depth = 0

    def registrations(self) -> tuple[DecisionWatchRegistration, ...]:
        records = tuple(self._registrations.read()) + tuple(
            activation.registration for activation in self._activations.read()
        )
        if len({record.packet_id for record in records}) != len(records) or len(
            {record.registration_id for record in records}
        ) != len(records):
            raise ValueError("duplicate decision watch registration for packet")
        return records

    def evaluations(self, registration_id: str) -> tuple[DecisionWatchEvaluation, ...]:
        registrations = {record.registration_id: record for record in self.registrations()}
        activated = tuple(
            activation.evaluation
            for activation in self._activations.read()
            if activation.registration.registration_id == registration_id
        )
        records = activated + tuple(
            record
            for record in self._evaluations.read()
            if record.registration_id == registration_id
        )
        registration = registrations.get(registration_id)
        if registration is None and records:
            raise ValueError("watch evaluation has no recorded registration")
        if registration is not None:
            self._validate_evaluation_chain(registration, records)
        return records

    @staticmethod
    def _validate_evaluation_chain(
        registration: DecisionWatchRegistration,
        evaluations: tuple[DecisionWatchEvaluation, ...],
    ) -> None:
        expected = tuple(condition.condition_id for condition in registration.conditions)
        terminal: dict[str, DecisionWatchResult] = {}
        previous_at: datetime | None = None
        previous_cursor: DecisionWatchObservation | None = None
        for evaluation in evaluations:
            if evaluation.registration_id != registration.registration_id:
                raise ValueError("watch evaluation registration binding differs")
            actual = tuple(result.condition_id for result in evaluation.results)
            if actual != expected or len(set(actual)) != len(actual):
                raise ValueError(
                    "watch evaluation results must completely follow registration conditions"
                )
            if previous_at is not None and evaluation.observation.evaluated_at <= previous_at:
                raise ValueError("watch evaluations must be strictly ordered")
            previous_at = evaluation.observation.evaluated_at
            for result in evaluation.results:
                prior_terminal = terminal.get(result.condition_id)
                if prior_terminal is not None and result != prior_terminal:
                    raise ValueError("watch terminal event identity changed during replay")
                if result.state == "triggered":
                    if prior_terminal is None and result.event_id != _event_identity(
                        result.condition_id, evaluation.observation, result.facts
                    ):
                        raise ValueError("watch terminal event identity is not canonical")
                    terminal[result.condition_id] = result
            accepted = any(
                isinstance(result.facts, PriceFacts)
                and result.facts.current_price == evaluation.observation.price
                for result in evaluation.results
            )
            if accepted:
                current = evaluation.observation
                if previous_cursor is not None and (
                    current.sequence != previous_cursor.sequence + 1
                    or current.data_time is None
                    or previous_cursor.data_time is None
                    or current.data_time <= previous_cursor.data_time
                    or current.received_at is None
                    or previous_cursor.received_at is None
                    or current.received_at <= previous_cursor.received_at
                ):
                    raise ValueError("watch price cursor does not continuously advance")
                previous_cursor = current

    def registration_for_packet(self, packet_id: str) -> DecisionWatchRegistration | None:
        return next(
            (record for record in self.registrations() if record.packet_id == packet_id), None
        )

    def registration(self, registration_id: str) -> DecisionWatchRegistration | None:
        return next(
            (
                record
                for record in self.registrations()
                if record.registration_id == registration_id
            ),
            None,
        )

    def record_registration(self, value: DecisionWatchRegistration) -> DecisionWatchRegistration:
        with self.transaction():
            existing = self.registration_for_packet(value.packet_id)
            if existing is not None:
                if existing != value:
                    raise ValueError("decision packet already has different watch conditions")
                return existing
            self._registrations.append(value)
            return value

    def record_evaluation(self, value: DecisionWatchEvaluation) -> DecisionWatchEvaluation:
        with self.transaction():
            existing = next(
                (
                    item
                    for item in self.evaluations(value.registration_id)
                    if item.evaluation_id == value.evaluation_id
                ),
                None,
            )
            if existing is not None:
                if existing != value:
                    raise ValueError("conflicting decision watch evaluation identity")
                return existing
            self._evaluations.append(value)
            return value

    def record_activation(
        self,
        registration: DecisionWatchRegistration,
        evaluation: DecisionWatchEvaluation,
    ) -> tuple[DecisionWatchRegistration, DecisionWatchEvaluation]:
        """Atomically expose a registration only with its initial evaluation."""
        with self.transaction():
            if self.registration_for_packet(registration.packet_id) is not None:
                raise ValueError("decision packet already has watch conditions")
            payload = {
                "registration": registration.model_dump(mode="json"),
                "evaluation": evaluation.model_dump(mode="json"),
            }
            activation = DecisionWatchActivation(
                activation_id=_identity("activation", payload),
                registration=registration,
                evaluation=evaluation,
            )
            self._activations.append(activation)
            return registration, evaluation


def validate_watch_replay(
    registration: DecisionWatchRegistration,
    evaluations: tuple[DecisionWatchEvaluation, ...],
) -> None:
    """Purely validate embedded registration/evaluation/event identities and order."""
    registration.canonical_conditions()
    for evaluation in evaluations:
        evaluation.canonical_identity()
    DecisionWatchStore._validate_evaluation_chain(registration, evaluations)


class DecisionWatchService:
    """Derive fixed rules from an exact packet and evaluate local facts only."""

    def __init__(
        self,
        *,
        packet_store: DecisionPacketStore,
        store: DecisionWatchStore,
        forecast_registry=None,
        calendar: CalendarService | None = None,
    ) -> None:
        self.packet_store = packet_store
        self.store = store
        self.forecast_registry = forecast_registry
        self.calendar = calendar or CalendarService()

    def _drift_definition(self, packet) -> DriftDefinition:
        baseline = None
        artifact = None
        artifact_id = packet.evidence.forecast_artifact_id
        if artifact_id is not None and self.forecast_registry is not None:
            try:
                artifact = self.forecast_registry.get(artifact_id)
                baseline = next(path.points[-1] for path in artifact.paths if path.sessions == 30)
            except (OSError, ValueError, StopIteration):
                baseline = None
        return DriftDefinition(
            baseline_artifact_id=artifact_id,
            baseline_generated_at=packet.evidence.forecast_generated_at,
            target_at=None if baseline is None else baseline.timestamp,
            baseline_p50=None if baseline is None else baseline.p50,
            model_name=packet.evidence.forecast_model_name,
            model_version=packet.evidence.forecast_model_version,
            config_digest=packet.evidence.forecast_config_digest,
            target=None if artifact is None else artifact.target,
            calendar=None if artifact is None else artifact.calendar,
            baseline_dataset_id=packet.evidence.forecast_dataset_id,
            baseline_dataset_revision=packet.evidence.forecast_dataset_revision,
            risk_per_unit=packet.risk_plan.risk_per_unit,
        )

    def _condition(self, packet, kind: WatchConditionKind) -> DecisionWatchCondition:
        if kind is WatchConditionKind.ENTRY_ZONE:
            definition: ConditionDefinition = EntryZoneDefinition(
                lower=min(packet.market_state.support, packet.risk_plan.entry_price),
                upper=max(packet.market_state.support, packet.risk_plan.entry_price),
            )
        elif kind is WatchConditionKind.INVALIDATION:
            definition = InvalidationDefinition(level=packet.market_state.invalidation)
        elif kind is WatchConditionKind.DATA_STALE:
            continuous = packet.instrument.metadata.get("calendar") == "24/7"
            history_generated_at = packet.evidence.history_generated_at
            forecast_generated_at = packet.evidence.forecast_generated_at
            definition = StaleDefinition(
                reference_at=min(
                    value
                    for value in (history_generated_at, forecast_generated_at)
                    if value is not None
                ),
                history_generated_at=history_generated_at,
                forecast_generated_at=forecast_generated_at,
                calendar_id="24/7" if continuous else "XNYS",
                calendar_version=CONTINUOUS_UTC_VERSION if continuous else XNYS_REGULAR_VERSION,
                session_policy=SessionPolicy.CONTINUOUS if continuous else SessionPolicy.REGULAR,
            )
        else:
            definition = self._drift_definition(packet)
        payload = {
            "packet_id": packet.packet_id,
            "kind": kind.value,
            "definition": definition.model_dump(mode="json"),
        }
        return DecisionWatchCondition(
            condition_id=_identity("condition", payload),
            packet_id=packet.packet_id,
            kind=kind,
            definition=definition,
        )

    def register(
        self, packet_id: str, kinds: tuple[WatchConditionKind, ...]
    ) -> DecisionWatchRegistration:
        with self.store.transaction():
            packet = self.packet_store.get(packet_id)
            return self.store.record_registration(self._registration(packet, kinds))

    def _registration(
        self, packet, kinds: tuple[WatchConditionKind, ...]
    ) -> DecisionWatchRegistration:
        if not 1 <= len(kinds) <= 4 or len(set(kinds)) != len(kinds):
            raise ValueError("watch conditions must be one to four unique fixed kinds")
        conditions = tuple(self._condition(packet, kind) for kind in _ORDER if kind in kinds)
        payload = {
            "packet_id": packet.packet_id,
            "conditions": [item.model_dump(mode="json") for item in conditions],
        }
        return DecisionWatchRegistration(
            registration_id=_identity("registration", payload),
            packet_id=packet.packet_id,
            conditions=conditions,
        )

    def register_and_check(
        self,
        packet_id: str,
        kinds: tuple[WatchConditionKind, ...],
        observation: DecisionWatchObservation,
    ) -> tuple[DecisionWatchRegistration, DecisionWatchEvaluation]:
        """Commit the fixed registration and its first server-derived check together.

        The observation is built before this call. A new registration and its
        initial evaluation share one atomically replaced activation record;
        concurrent processes cannot observe a half-registration or derive
        competing cursors.
        """
        with self.store.transaction():
            packet = self.packet_store.get(packet_id)
            registration = self._registration(packet, kinds)
            existing = self.store.registration_for_packet(packet_id)
            if existing is not None:
                if existing != registration:
                    raise ValueError("decision packet already has different watch conditions")
                return existing, self.check(existing.registration_id, observation)
            evaluation = self._evaluation(registration, packet, (), observation)
            return self.store.record_activation(registration, evaluation)

    def state(
        self, packet_id: str
    ) -> tuple[DecisionWatchRegistration | None, DecisionWatchEvaluation | None]:
        with self.store.transaction():
            registration = self.store.registration_for_packet(packet_id)
            if registration is None:
                return None, None
            evaluations = self.store.evaluations(registration.registration_id)
            return registration, evaluations[-1] if evaluations else None

    def _event_id(
        self, condition_id: str, observation: DecisionWatchObservation, facts: WatchFacts
    ) -> str:
        return _event_identity(condition_id, observation, facts)

    def _price_result(
        self,
        condition: DecisionWatchCondition,
        packet,
        observation: DecisionWatchObservation,
        prior: DecisionWatchObservation | None,
    ) -> DecisionWatchResult:
        if not isinstance(condition.definition, (EntryZoneDefinition, InvalidationDefinition)):
            raise ValueError("price condition has an invalid definition")
        if (
            observation.price is None
            or observation.instrument is None
            or observation.instrument.model_dump(mode="json")
            != packet.instrument.model_dump(mode="json")
            or observation.data_time is None
            or observation.received_at is None
            or observation.sequence is None
            or observation.sequence_gap is not False
            or observation.data_time <= packet.as_of
            or observation.received_at <= packet.as_of
            or observation.data_time > observation.evaluated_at
            or observation.received_at > observation.evaluated_at
        ):
            return DecisionWatchResult(
                condition_id=condition.condition_id,
                state="not_comparable",
                facts=UnavailableFacts(code="unusable_price_evidence"),
            )
        if prior is None:
            return DecisionWatchResult(
                condition_id=condition.condition_id,
                state="armed",
                facts=PriceFacts(current_price=observation.price),
            )
        if (
            prior.sequence is None
            or prior.data_time is None
            or observation.sequence != prior.sequence + 1
            or observation.data_time <= prior.data_time
        ):
            raise ValueError("price observation does not continuously advance the durable cursor")
        if condition.kind is WatchConditionKind.ENTRY_ZONE:
            definition = condition.definition
            hit = (
                not definition.lower <= prior.price <= definition.upper
                and definition.lower <= observation.price <= definition.upper
            )
            facts = PriceFacts(
                previous_price=prior.price,
                current_price=observation.price,
                lower=definition.lower,
                upper=definition.upper,
            )
        else:
            definition = condition.definition
            hit = prior.price >= definition.level and observation.price < definition.level
            facts = PriceFacts(
                previous_price=prior.price, current_price=observation.price, level=definition.level
            )
        return DecisionWatchResult(
            condition_id=condition.condition_id,
            state="triggered" if hit else "not_triggered",
            facts=facts,
            event_id=self._event_id(condition.condition_id, observation, facts) if hit else None,
        )

    def _stale_result(
        self, condition: DecisionWatchCondition, observation: DecisionWatchObservation
    ) -> DecisionWatchResult:
        if not isinstance(condition.definition, StaleDefinition):
            raise ValueError("stale condition has an invalid definition")
        definition = condition.definition
        if definition.reference_at > observation.evaluated_at:
            return DecisionWatchResult(
                condition_id=condition.condition_id,
                state="not_comparable",
                facts=UnavailableFacts(code="future_reference"),
            )
        try:
            sessions = self.calendar.sessions(
                definition.calendar_id,
                definition.reference_at.date(),
                observation.evaluated_at.date(),
                policy=definition.session_policy,
            )
        except (CalendarUnavailableError, ValueError):
            return DecisionWatchResult(
                condition_id=condition.condition_id,
                state="not_comparable",
                facts=UnavailableFacts(code="calendar_unavailable"),
            )
        completed = sum(
            definition.reference_at < session.close_at <= observation.evaluated_at
            for session in sessions
        )
        facts = StaleFacts(
            reference_at=definition.reference_at,
            evaluated_at=observation.evaluated_at,
            completed_sessions=completed,
        )
        hit = completed > definition.maximum_completed_sessions
        return DecisionWatchResult(
            condition_id=condition.condition_id,
            state="triggered" if hit else "not_triggered",
            facts=facts,
            event_id=self._event_id(condition.condition_id, observation, facts) if hit else None,
        )

    def _drift_result(
        self, condition: DecisionWatchCondition, packet, observation: DecisionWatchObservation
    ) -> DecisionWatchResult:
        if not isinstance(condition.definition, DriftDefinition):
            raise ValueError("drift condition has an invalid definition")
        definition = condition.definition
        if (
            definition.baseline_artifact_id is None
            or definition.baseline_generated_at is None
            or definition.target_at is None
            or definition.baseline_p50 is None
            or observation.candidate_forecast_artifact_id is None
            or self.forecast_registry is None
        ):
            return DecisionWatchResult(
                condition_id=condition.condition_id,
                state="not_comparable",
                facts=UnavailableFacts(code="missing_forecast"),
            )
        try:
            candidate = self.forecast_registry.get(observation.candidate_forecast_artifact_id)
            point = next(
                point
                for path in candidate.paths
                for point in path.points
                if point.timestamp == definition.target_at
            )
        except (OSError, ValueError, StopIteration):
            return DecisionWatchResult(
                condition_id=condition.condition_id,
                state="not_comparable",
                facts=UnavailableFacts(code="candidate_not_comparable"),
            )
        if (
            candidate.instrument.model_dump(mode="json")
            != packet.instrument.model_dump(mode="json")
            or candidate.generated_at <= definition.baseline_generated_at
            or candidate.generated_at > observation.evaluated_at
            or candidate.model_name != definition.model_name
            or candidate.model_version != definition.model_version
            or candidate.config_digest != definition.config_digest
            or candidate.target != definition.target
            or candidate.calendar != definition.calendar
            or candidate.dataset_id != definition.baseline_dataset_id
            or candidate.dataset_revision != definition.baseline_dataset_revision
        ):
            return DecisionWatchResult(
                condition_id=condition.condition_id,
                state="not_comparable",
                facts=UnavailableFacts(code="candidate_incompatible"),
            )
        distance = abs(point.p50 - definition.baseline_p50)
        facts = DriftFacts(
            target_at=definition.target_at,
            baseline_p50=definition.baseline_p50,
            candidate_p50=point.p50,
            distance=distance,
            threshold=definition.risk_per_unit,
        )
        hit = distance > definition.risk_per_unit
        return DecisionWatchResult(
            condition_id=condition.condition_id,
            state="triggered" if hit else "not_triggered",
            facts=facts,
            event_id=self._event_id(condition.condition_id, observation, facts) if hit else None,
        )

    def check(
        self, registration_id: str, observation: DecisionWatchObservation
    ) -> DecisionWatchEvaluation:
        with self.store.transaction():
            registration = self.store.registration(registration_id)
            if registration is None:
                raise ValueError("decision watch registration is not recorded")
            packet = self.packet_store.get(registration.packet_id)
            prior_evaluations = self.store.evaluations(registration_id)
            replay = next(
                (item for item in prior_evaluations if item.observation == observation), None
            )
            if replay is not None:
                return replay
            return self.store.record_evaluation(
                self._evaluation(registration, packet, prior_evaluations, observation)
            )

    def _evaluation(
        self,
        registration: DecisionWatchRegistration,
        packet,
        prior_evaluations: tuple[DecisionWatchEvaluation, ...],
        observation: DecisionWatchObservation,
    ) -> DecisionWatchEvaluation:
        prior_price = next(
            (
                item.observation
                for item in reversed(prior_evaluations)
                if any(
                    isinstance(result.facts, PriceFacts)
                    and result.facts.current_price == item.observation.price
                    for result in item.results
                )
            ),
            None,
        )
        terminal = {
            result.condition_id: result
            for item in prior_evaluations
            for result in item.results
            if result.state == "triggered"
        }
        results: list[DecisionWatchResult] = []
        for condition in registration.conditions:
            if condition.condition_id in terminal:
                results.append(terminal[condition.condition_id])
            elif condition.kind in {
                WatchConditionKind.ENTRY_ZONE,
                WatchConditionKind.INVALIDATION,
            }:
                results.append(self._price_result(condition, packet, observation, prior_price))
            elif condition.kind is WatchConditionKind.DATA_STALE:
                results.append(self._stale_result(condition, observation))
            else:
                results.append(self._drift_result(condition, packet, observation))
        payload = {
            "registration_id": registration.registration_id,
            "observation": observation.model_dump(mode="json"),
            "results": [result.model_dump(mode="json") for result in results],
        }
        return DecisionWatchEvaluation(
            evaluation_id=_identity("evaluation", payload),
            registration_id=registration.registration_id,
            observation=observation,
            results=tuple(results),
        )
