"""Canonical identity and durable replay for immutable decision packets."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from quantmesh.domain.models import Side, Venue
from quantmesh.instruments.contracts import (
    DecisionDisposition,
    DecisionPacket,
    DecisionPacketActionResult,
    HistoryRange,
    InstrumentWorkspace,
)
from quantmesh.instruments.proposals import PaperDecisionService
from quantmesh.persistence.jsonl import JsonlStore

_LOCKS_GUARD = threading.Lock()
_ROOT_LOCKS: dict[str, threading.RLock] = {}


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
        self._store = JsonlStore(
            root,
            filename="decision-packets.jsonl",
            model=DecisionPacket,
            label="decision packet store",
            id_label="decision packet",
            key=lambda packet: packet.packet_id,
            extra_validate=self._validate_identity,
        )

    @property
    def root(self) -> Path:
        return self._store.root

    @property
    def path(self) -> Path:
        return self._store.path

    @staticmethod
    def _validate_identity(packet: DecisionPacket) -> None:
        if packet.packet_id != decision_packet_id(packet):
            raise ValueError("decision packet identity does not match canonical content")

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
                        "packet_id", "version", "parent_packet_id", "created_at",
                        "disposition", "operator_reason", "proposal_id",
                    },
                )
                child_facts = packet.model_dump(
                    mode="json",
                    exclude={
                        "packet_id", "version", "parent_packet_id", "created_at",
                        "disposition", "operator_reason", "proposal_id",
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
        with self._lock, _interprocess_lock(self.root):
            packets = self._records()
            self._validate_identity(packet)
            self._store.check_absent(packet, packets)
            self._validate_collection([*packets, packet])
            self._store.append(packet)
            self._records()
        return packet

    def get(self, packet_id: str) -> DecisionPacket:
        for packet in self._records():
            if packet.packet_id == packet_id:
                return packet
        raise ValueError(f"decision packet {packet_id!r} is not recorded")

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
        workspace: InstrumentWorkspace = self._workspace().render(
            venue,
            symbol,
            selected_range,
        )
        draft = workspace.decision.draft
        if draft.packet_id != expected_packet_id:
            raise ValueError(
                "expected decision packet id does not match the current workspace draft"
            )
        try:
            existing = self.store.get(draft.packet_id)
        except ValueError as error:
            if "is not recorded" not in str(error):
                raise
        else:
            return existing
        return self.store.record(draft)

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
        parent = self.store.get(parent_packet_id)
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
        proposal = self._proposals.propose(
            artifact_id,
            side=side,
            quantity=quantity,
            limit_price=limit_price,
        )
        if (
            proposal.artifact_id != artifact_id
            or proposal.instrument != parent.instrument
            or proposal.dataset_id != parent.evidence.forecast_dataset_id
            or proposal.dataset_revision != parent.evidence.forecast_dataset_revision
        ):
            raise ValueError("paper proposal does not match immutable decision packet evidence")
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
