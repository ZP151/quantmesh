"""Canonical identity and durable replay for immutable decision packets."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from quantmesh.domain.models import Venue
from quantmesh.instruments.contracts import DecisionPacket, HistoryRange
from quantmesh.persistence.jsonl import JsonlStore


def decision_packet_id(packet: DecisionPacket) -> str:
    """Return the packet's canonical content identity, excluding bookkeeping time only."""
    payload = packet.model_dump(mode="json", exclude={"packet_id", "created_at"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"packet-{hashlib.sha256(canonical).hexdigest()[:24]}"


class DecisionPacketStore:
    """Fail-closed JSONL replay for one immutable decision-packet collection."""

    def __init__(self, root: Path) -> None:
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
        for packet in packets:
            cls._validate_identity(packet)
            if packet.packet_id in by_id:
                raise ValueError("duplicate decision packet identity")
            if packet.parent_packet_id is None:
                if packet.version != 1:
                    raise ValueError("root decision packet must have version 1")
                if packet.disposition.value != "draft":
                    raise ValueError("root decision packet must be draft")
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
