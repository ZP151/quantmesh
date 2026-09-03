"""Canonical identity and durable replay for immutable decision packets."""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.domain.models import Side, Venue
from quantmesh.instruments.contracts import (
    DecisionDisposition,
    DecisionPacket,
    DecisionPacketActionResult,
    HistoryRange,
    InstrumentWorkspace,
    PaperProposal,
    PriceForecastArtifact,
    ProposalStatus,
)
from quantmesh.instruments.proposals import (
    PaperDecisionService,
    forecast_freshness_blocker,
)
from quantmesh.persistence.jsonl import JsonlStore

_LOCKS_GUARD = threading.Lock()
_ROOT_LOCKS: dict[str, threading.RLock] = {}
_PACKET_ID = re.compile(r"^packet-[0-9a-f]{24}$")
_INTENT_ID = re.compile(r"^intent-[0-9a-f]{24}$")


class DecisionPacketNotFoundError(ValueError):
    """The exact packet identity is absent from an otherwise valid store."""


class DecisionActionIntent(BaseModel):
    """Durable action intent used to recover the proposal-to-child crash window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    intent_id: str = Field(pattern=r"^intent-[0-9a-f]{24}$")
    parent_packet_id: str = Field(pattern=r"^packet-[0-9a-f]{24}$")
    proposal_id: str = Field(pattern=r"^proposal-[0-9a-f]{24}$")
    disposition: DecisionDisposition
    operator_reason: str | None = None
    side: Side
    quantity: float = Field(gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def created_at_is_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("decision action intent time must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def paper_only(self) -> DecisionActionIntent:
        if self.disposition is not DecisionDisposition.PAPER_PROPOSAL:
            raise ValueError("durable decision action intent is paper-only")
        return self


def decision_action_intent_id(intent: DecisionActionIntent) -> str:
    """Return the canonical identity of every authority-bearing intent fact."""
    payload = intent.model_dump(mode="json", exclude={"intent_id"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"intent-{hashlib.sha256(canonical).hexdigest()[:24]}"


def _root_lock(root: Path) -> threading.RLock:
    key = str(root.resolve(strict=False)).casefold()
    with _LOCKS_GUARD:
        return _ROOT_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _interprocess_lock(root: Path) -> Iterator[None]:
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".decision-packets.lock"
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
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


def decision_packet_id(packet: DecisionPacket) -> str:
    """Return the packet's canonical content identity, excluding bookkeeping time only."""
    payload = packet.model_dump(mode="json", exclude={"packet_id", "created_at"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"packet-{hashlib.sha256(canonical).hexdigest()[:24]}"


class DecisionPacketStore:
    """Fail-closed JSONL replay for one immutable decision-packet collection."""

    def __init__(self, root: Path) -> None:
        self._lock = _root_lock(root)
        self._local = threading.local()
        self._store = JsonlStore(
            root,
            filename="decision-packets.jsonl",
            model=DecisionPacket,
            label="decision packet store",
            id_label="decision packet",
            key=lambda packet: packet.packet_id,
            extra_validate=self._validate_identity,
        )
        self._intents = JsonlStore(
            root,
            filename="decision-action-intents.jsonl",
            model=DecisionActionIntent,
            label="decision action intent store",
            id_label="decision action intent",
            key=lambda intent: intent.intent_id,
            extra_validate=self._validate_intent_identity,
            secondary_keys=(("decision packet parent id", lambda intent: intent.parent_packet_id),),
        )

    @property
    def root(self) -> Path:
        return self._store.root

    @property
    def path(self) -> Path:
        return self._store.path

    @property
    def intent_path(self) -> Path:
        return self._intents.path

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Serialize packet, intent, proposal-delegation and child publication."""
        with self._lock:
            depth = getattr(self._local, "depth", 0)
            if depth:
                self._local.depth = depth + 1
                try:
                    yield
                finally:
                    self._local.depth = depth
                return
            with _interprocess_lock(self.root):
                self._local.depth = 1
                try:
                    yield
                finally:
                    self._local.depth = 0

    @staticmethod
    def _validate_identity(packet: DecisionPacket) -> None:
        if packet.packet_id != decision_packet_id(packet):
            raise ValueError("decision packet identity does not match canonical content")

    @staticmethod
    def _validate_intent_identity(intent: DecisionActionIntent) -> None:
        if _INTENT_ID.fullmatch(intent.intent_id) is None:
            raise ValueError("decision action intent id is not canonical")
        if intent.intent_id != decision_action_intent_id(intent):
            raise ValueError("decision action intent identity does not match canonical content")

    @classmethod
    def _validate_collection(cls, packets: list[DecisionPacket]) -> None:
        by_id: dict[str, DecisionPacket] = {}
        child_by_parent: dict[str, str] = {}
        root_scopes: set[tuple[str, str, str, str]] = set()
        for packet in packets:
            cls._validate_identity(packet)
            if packet.packet_id in by_id:
                raise ValueError("duplicate decision packet identity")
            if packet.parent_packet_id is None:
                if packet.version != 1:
                    raise ValueError("root decision packet must have version 1")
                if packet.disposition.value != "draft":
                    raise ValueError("root decision packet must be draft")
                scope = (
                    packet.instrument.venue.value,
                    packet.instrument.symbol,
                    packet.selected_range.value,
                    packet.as_of.isoformat(),
                )
                if scope in root_scopes:
                    raise ValueError("decision packet lineage scope already has a root")
                root_scopes.add(scope)
            else:
                parent = by_id.get(packet.parent_packet_id)
                if parent is None:
                    raise ValueError("decision packet parent must be recorded before its child")
                if packet.version != parent.version + 1:
                    raise ValueError(
                        "decision packet child version must increment its parent by one"
                    )
                if (
                    packet.instrument != parent.instrument
                    or packet.selected_range != parent.selected_range
                ):
                    raise ValueError(
                        "decision packet child must preserve its parent instrument and range"
                    )
                if packet.as_of != parent.as_of:
                    raise ValueError("decision packet child must preserve its parent as_of")
                if packet.created_at < parent.created_at:
                    raise ValueError("decision packet child cannot predate its parent")
                parent_facts = parent.model_dump(
                    mode="json",
                    exclude={
                        "packet_id",
                        "version",
                        "parent_packet_id",
                        "created_at",
                        "disposition",
                        "operator_reason",
                        "proposal_id",
                    },
                )
                child_facts = packet.model_dump(
                    mode="json",
                    exclude={
                        "packet_id",
                        "version",
                        "parent_packet_id",
                        "created_at",
                        "disposition",
                        "operator_reason",
                        "proposal_id",
                    },
                )
                if child_facts != parent_facts:
                    raise ValueError("decision packet child must preserve parent semantic facts")
                if packet.parent_packet_id in child_by_parent:
                    raise ValueError("decision packet parent already has a child transition")
                child_by_parent[packet.parent_packet_id] = packet.packet_id
            by_id[packet.packet_id] = packet

    def _records(self) -> list[DecisionPacket]:
        packets = self._store.read()
        self._validate_collection(packets)
        return packets

    def record(self, packet: DecisionPacket) -> DecisionPacket:
        """Append one validated immutable packet and immediately replay-check it."""
        with self.transaction():
            packets = self._records()
            self._validate_identity(packet)
            self._store.check_absent(packet, packets)
            self._validate_collection([*packets, packet])
            self._store.append(packet)
            self._records()
        return packet

    def get(self, packet_id: str) -> DecisionPacket:
        if _PACKET_ID.fullmatch(packet_id) is None:
            raise DecisionPacketNotFoundError(f"decision packet {packet_id!r} is not recorded")
        for packet in self._records():
            if packet.packet_id == packet_id:
                return packet
        raise DecisionPacketNotFoundError(f"decision packet {packet_id!r} is not recorded")

    def reserve_action_intent(self, intent: DecisionActionIntent) -> DecisionActionIntent:
        """Record or replay the one exact durable Paper intent for a parent packet."""
        with self.transaction():
            intents = self._intents.read()
            self._validate_intent_identity(intent)
            existing = next(
                (item for item in intents if item.parent_packet_id == intent.parent_packet_id),
                None,
            )
            if existing is not None:
                if existing != intent:
                    raise ValueError("decision packet already has a different durable intent")
                return existing
            self._intents.append(intent)
            return intent

    def action_intent(self, parent_packet_id: str) -> DecisionActionIntent | None:
        """Return the validated durable Paper intent for one exact packet, if any."""
        intents = self._intents.read()
        return next(
            (item for item in intents if item.parent_packet_id == parent_packet_id),
            None,
        )

    def all(self) -> tuple[DecisionPacket, ...]:
        return tuple(self._records())

    def lineage(self, packet_id: str) -> tuple[DecisionPacket, ...]:
        packets = self._records()
        by_id = {packet.packet_id: packet for packet in packets}
        packet = by_id.get(packet_id)
        if packet is None:
            raise ValueError(f"decision packet {packet_id!r} is not recorded")
        result: list[DecisionPacket] = []
        while packet is not None:
            result.append(packet)
            packet = by_id.get(packet.parent_packet_id) if packet.parent_packet_id else None
        return tuple(reversed(result))

    def latest(
        self, venue: Venue, symbol: str, selected_range: HistoryRange
    ) -> DecisionPacket | None:
        packets = [
            packet
            for packet in self._records()
            if packet.instrument.venue is venue
            and packet.instrument.symbol == symbol
            and packet.selected_range is selected_range
        ]
        if not packets:
            return None
        return max(packets, key=lambda packet: (packet.as_of, packet.version, packet.packet_id))


def validate_decision_packet_lineage(packets: tuple[DecisionPacket, ...]) -> None:
    """Purely validate canonical packet identities and one exact parent chain."""
    DecisionPacketStore._validate_collection(list(packets))
    if not packets:
        raise ValueError("decision packet lineage cannot be empty")
    if packets[-1].version != len(packets):
        raise ValueError("decision packet lineage is incomplete")


class DecisionPacketService:
    """Persist workspace drafts and append operator actions without order authority."""

    def __init__(
        self,
        *,
        store: DecisionPacketStore,
        workspace_provider: Callable[[], object],
        proposals: PaperDecisionService | None,
    ) -> None:
        self.store = store
        self._workspace_provider = workspace_provider
        self._proposals = proposals

    def _workspace(self) -> object:
        service = self._workspace_provider()
        if not callable(getattr(service, "render", None)):
            raise ValueError("instrument workspace service is not attached")
        return service

    def save_draft(
        self,
        venue: Venue,
        symbol: str,
        selected_range: HistoryRange,
        *,
        expected_packet_id: str,
    ) -> DecisionPacket:
        workspace_service = self._workspace()
        staged = getattr(workspace_service, "staged_draft", None)
        draft = (
            staged(
                expected_packet_id,
                venue=venue,
                symbol=symbol,
                selected_range=selected_range,
            )
            if callable(staged)
            else None
        )
        if draft is None:
            workspace: InstrumentWorkspace = workspace_service.render(
                venue,
                symbol,
                selected_range,
            )
            draft = workspace.decision.draft
        if draft.packet_id != expected_packet_id:
            raise ValueError(
                "expected decision packet id does not match the current workspace draft"
            )
        with self.store.transaction():
            try:
                existing = self.store.get(draft.packet_id)
            except DecisionPacketNotFoundError:
                return self.store.record(draft)
            return existing

    @staticmethod
    def _action_time(parent: DecisionPacket, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("decision action clock must be timezone-aware")
        action_at = value.astimezone(UTC)
        if action_at < parent.as_of:
            raise ValueError("decision action clock cannot predate the packet")
        return action_at

    @staticmethod
    def _intent_for(
        parent: DecisionPacket,
        proposal: PaperProposal,
        *,
        operator_reason: str | None,
    ) -> DecisionActionIntent:
        provisional = DecisionActionIntent(
            intent_id="intent-" + "0" * 24,
            parent_packet_id=parent.packet_id,
            proposal_id=proposal.id,
            disposition=DecisionDisposition.PAPER_PROPOSAL,
            operator_reason=operator_reason,
            side=proposal.side,
            quantity=proposal.quantity,
            limit_price=proposal.limit_price,
            created_at=proposal.created_at,
        )
        return provisional.model_copy(update={"intent_id": decision_action_intent_id(provisional)})

    @staticmethod
    def _validate_intent_request(
        intent: DecisionActionIntent,
        *,
        disposition: DecisionDisposition,
        operator_reason: str | None,
        side: Side | None,
        quantity: float | None,
        limit_price: float | None,
    ) -> None:
        if (
            intent.disposition is not disposition
            or intent.operator_reason != operator_reason
            or intent.side is not side
            or intent.quantity != quantity
            or intent.limit_price != limit_price
        ):
            raise ValueError("decision packet already has a different durable intent")

    @staticmethod
    def _validate_intent_proposal(
        intent: DecisionActionIntent,
        proposal: PaperProposal,
    ) -> None:
        if (
            intent.proposal_id != proposal.id
            or intent.side is not proposal.side
            or intent.quantity != proposal.quantity
            or intent.limit_price != proposal.limit_price
            or intent.created_at != proposal.created_at
        ):
            raise ValueError("durable decision action intent does not match paper proposal")

    @staticmethod
    def _validate_artifact_binding(
        parent: DecisionPacket,
        artifact: PriceForecastArtifact,
    ) -> None:
        evidence = parent.evidence
        chronology = evidence.forecast_chronology
        chronology_matches = chronology is not None and (
            chronology.train_start == artifact.train_start
            and chronology.train_end == artifact.train_end
            and chronology.validation_start == artifact.validation_start
            and chronology.validation_end == artifact.validation_end
            and chronology.test_start == artifact.test_start
            and chronology.test_end == artifact.test_end
        )
        if (
            evidence.forecast_artifact_id != artifact.id
            or parent.instrument.model_dump(mode="json")
            != artifact.instrument.model_dump(mode="json")
            or evidence.forecast_dataset_id != artifact.dataset_id
            or evidence.forecast_dataset_revision != artifact.dataset_revision
            or evidence.forecast_manifest_id != artifact.manifest_id
            or evidence.forecast_quality_evaluation_id != artifact.quality_evaluation_id
            or evidence.forecast_synthetic != (artifact.source == "demo-synthetic")
            or evidence.forecast_eligible != artifact.eligible
            or evidence.forecast_blockers != artifact.blockers
            or evidence.forecast_limitations != artifact.limitations
            or evidence.forecast_model_name != artifact.model_name
            or evidence.forecast_model_version != artifact.model_version
            or evidence.forecast_config_digest != artifact.config_digest
            or evidence.forecast_history_digest != artifact.history_digest
            or evidence.forecast_benchmark_name != artifact.benchmark_name
            or evidence.forecast_generated_at != artifact.generated_at
            or evidence.forecast_paths != artifact.paths
            or evidence.forecast_metrics != artifact.metrics
            or not chronology_matches
        ):
            raise ValueError("forecast artifact does not match immutable packet evidence")

    @staticmethod
    def _validate_proposal_binding(
        parent: DecisionPacket,
        proposal: PaperProposal,
    ) -> None:
        evidence = parent.evidence
        if (
            proposal.status is not ProposalStatus.PENDING
            or proposal.artifact_id != evidence.forecast_artifact_id
            or proposal.instrument.model_dump(mode="json")
            != parent.instrument.model_dump(mode="json")
            or proposal.dataset_id != evidence.forecast_dataset_id
            or proposal.dataset_revision != evidence.forecast_dataset_revision
            or proposal.forecast_generated_at != evidence.forecast_generated_at
            or proposal.model_version != evidence.forecast_model_version
            or proposal.config_digest != evidence.forecast_config_digest
            or proposal.history_digest != evidence.forecast_history_digest
        ):
            raise ValueError("paper proposal does not match immutable decision packet evidence")

    def _existing_child(
        self,
        parent: DecisionPacket,
        *,
        disposition: DecisionDisposition,
        operator_reason: str | None,
        side: Side | None,
        quantity: float | None,
        limit_price: float | None,
    ) -> DecisionPacketActionResult | None:
        latest = self.store.latest(
            parent.instrument.venue,
            parent.instrument.symbol,
            parent.selected_range,
        )
        if latest is None or latest.packet_id == parent.packet_id:
            return None
        if latest.parent_packet_id != parent.packet_id:
            raise ValueError("decision packet is not the latest actionable version")
        if latest.disposition is not disposition or latest.operator_reason != operator_reason:
            raise ValueError("decision packet already has a different child transition")
        proposal = None
        if disposition is DecisionDisposition.PAPER_PROPOSAL:
            if self._proposals is None or latest.proposal_id is None:
                raise ValueError("paper proposal service is not attached")
            proposal = self._proposals.ledger.get(latest.proposal_id)
            if (
                proposal.side is not side
                or proposal.quantity != quantity
                or proposal.limit_price != limit_price
            ):
                raise ValueError("decision packet already has a different child transition")
        return DecisionPacketActionResult(packet=latest, proposal=proposal)

    @staticmethod
    def _child(
        parent: DecisionPacket,
        *,
        disposition: DecisionDisposition,
        operator_reason: str | None,
        proposal_id: str | None,
        created_at: datetime,
    ) -> DecisionPacket:
        payload = parent.model_dump()
        payload.update(
            packet_id="packet-" + "0" * 24,
            version=parent.version + 1,
            parent_packet_id=parent.packet_id,
            created_at=created_at,
            disposition=disposition,
            operator_reason=operator_reason,
            proposal_id=proposal_id,
        )
        provisional = DecisionPacket.model_validate(payload)
        return provisional.model_copy(update={"packet_id": decision_packet_id(provisional)})

    def transition(
        self,
        parent_packet_id: str,
        *,
        disposition: DecisionDisposition,
        operator_reason: str | None = None,
        side: Side | None = None,
        quantity: float | None = None,
        limit_price: float | None = None,
    ) -> DecisionPacketActionResult:
        if disposition in {DecisionDisposition.REJECT, DecisionDisposition.WATCH}:
            if operator_reason is None or not operator_reason.strip():
                raise ValueError("reject and watch require a nonblank operator reason")
            if side is not None or quantity is not None or limit_price is not None:
                raise ValueError("reject and watch cannot carry proposal inputs")
        elif disposition is DecisionDisposition.PAPER_PROPOSAL:
            if side is None or quantity is None:
                raise ValueError("paper proposal requires side and quantity")
        else:
            raise ValueError("draft is not an operator action")
        proposal_transaction = (
            self._proposals.ledger.transaction()
            if disposition is DecisionDisposition.PAPER_PROPOSAL and self._proposals is not None
            else nullcontext()
        )
        with self.store.transaction(), proposal_transaction:
            parent = self.store.get(parent_packet_id)
            existing = self._existing_child(
                parent,
                disposition=disposition,
                operator_reason=operator_reason,
                side=side,
                quantity=quantity,
                limit_price=limit_price,
            )
            if existing is not None:
                return existing
            if parent.disposition is not DecisionDisposition.DRAFT:
                raise ValueError("only a draft decision packet can transition")

            if disposition in {DecisionDisposition.REJECT, DecisionDisposition.WATCH}:
                child = self._child(
                    parent,
                    disposition=disposition,
                    operator_reason=operator_reason,
                    proposal_id=None,
                    created_at=parent.created_at,
                )
                return DecisionPacketActionResult(packet=self.store.record(child))

            if not parent.paper_capability.allowed or parent.paper_capability.blockers:
                raise ValueError("decision packet is blocked from paper proposal")
            if self._proposals is None:
                raise ValueError("paper proposal service is not attached")
            artifact_id = parent.evidence.forecast_artifact_id
            if artifact_id is None:
                raise ValueError("decision packet has no forecast artifact binding")

            intent = self.store.action_intent(parent.packet_id)
            if intent is not None:
                self._validate_intent_request(
                    intent,
                    disposition=disposition,
                    operator_reason=operator_reason,
                    side=side,
                    quantity=quantity,
                    limit_price=limit_price,
                )
                try:
                    durable_proposal = self._proposals.ledger.get(intent.proposal_id)
                except ValueError as error:
                    if "no proposal recorded" not in str(error):
                        raise
                else:
                    self._validate_intent_proposal(intent, durable_proposal)
                    self._validate_proposal_binding(parent, durable_proposal)
                    child = self._child(
                        parent,
                        disposition=disposition,
                        operator_reason=operator_reason,
                        proposal_id=durable_proposal.id,
                        created_at=max(parent.created_at, durable_proposal.created_at),
                    )
                    return DecisionPacketActionResult(
                        packet=self.store.record(child),
                        proposal=durable_proposal,
                    )
                action_at = self._action_time(parent, intent.created_at)
            else:
                action_at = self._action_time(parent, self._proposals.current_time())

            artifact = self._proposals.resolve_artifact(artifact_id)
            self._validate_artifact_binding(parent, artifact)
            if not artifact.eligible:
                raise ValueError("forecast artifact is not eligible for paper proposal")
            freshness = forecast_freshness_blocker(artifact, action_at)
            if freshness is not None:
                raise ValueError(f"decision packet expired: {freshness}")

            def reserve_intent(proposal: PaperProposal) -> None:
                candidate = self._intent_for(
                    parent,
                    proposal,
                    operator_reason=operator_reason,
                )
                if intent is not None and candidate != intent:
                    raise ValueError("durable decision action intent does not match paper proposal")
                self.store.reserve_action_intent(candidate)

            proposal = self._proposals.propose(
                artifact_id,
                side=side,
                quantity=quantity,
                limit_price=limit_price,
                created_at=action_at,
                expected_artifact=artifact,
                before_record=reserve_intent,
            )
            self._validate_proposal_binding(parent, proposal)
            child = self._child(
                parent,
                disposition=disposition,
                operator_reason=operator_reason,
                proposal_id=proposal.id,
                created_at=max(parent.created_at, proposal.created_at),
            )
            return DecisionPacketActionResult(
                packet=self.store.record(child),
                proposal=proposal,
            )
