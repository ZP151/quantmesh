"""Packet-bound structured Copilot advisory records.

The Copilot reads one exact persisted DecisionPacket, validates every model
statement against packet-only citations, requires an independent critic pass,
and stores the accepted report separately from packet and trading authority.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.ai.decisions import DecisionLog, DecisionRecord, ModelMeta
from quantmesh.ai.gateway import ModelGateway
from quantmesh.ai.redact import redact_context
from quantmesh.ai.retrieval import Citation, DecisionPacketSource, resolve_citation
from quantmesh.ai.wire import ChatMessage, ModelRequest
from quantmesh.instruments.decision_packets import DecisionPacketStore
from quantmesh.persistence.jsonl import JsonlStore

COPILOT_RECORDS_FILE = "packet-copilot-records.jsonl"
PACKET_ID_PATTERN = r"^packet-[0-9a-f]{24}$"
RECORD_ID_PATTERN = r"^copilot-[0-9a-f]{24}$"
DECISION_ID_PATTERN = r"^[0-9a-f]{16}$"
DEGRADED_REASON = "copilot-unavailable"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PacketCopilotItem(_StrictModel):
    text: str = Field(min_length=1, max_length=4_000)
    citations: tuple[Citation, ...] = Field(min_length=1, max_length=8)

    @field_validator("text")
    @classmethod
    def _text_is_not_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Copilot item text must not be blank")
        return value


class PacketCopilotDraft(_StrictModel):
    packet_id: str = Field(pattern=PACKET_ID_PATTERN)
    base_explanation: PacketCopilotItem
    bull_challenge: PacketCopilotItem
    bear_challenge: PacketCopilotItem
    evidence_gaps_or_contradictions: tuple[PacketCopilotItem, ...] = Field(
        min_length=1, max_length=12
    )
    limitations: tuple[PacketCopilotItem, ...] = Field(min_length=1, max_length=12)
    operator_questions: tuple[PacketCopilotItem, ...] = Field(min_length=1, max_length=12)

    def validate_for_packet(self, packet_id: str) -> PacketCopilotDraft:
        if self.packet_id != packet_id:
            raise ValueError("Copilot draft packet_id does not match the requested packet")
        return self

    def items(self) -> tuple[PacketCopilotItem, ...]:
        return (
            self.base_explanation,
            self.bull_challenge,
            self.bear_challenge,
            *self.evidence_gaps_or_contradictions,
            *self.limitations,
            *self.operator_questions,
        )


class PacketCopilotFlag(_StrictModel):
    item_path: str = Field(
        min_length=1,
        max_length=128,
        pattern=(
            r"^(base_explanation|bull_challenge|bear_challenge|"
            r"evidence_gaps_or_contradictions/[0-9]+|limitations/[0-9]+|"
            r"operator_questions/[0-9]+)$"
        ),
    )
    reason: str = Field(min_length=1, max_length=1_000)

    @field_validator("reason")
    @classmethod
    def _reason_is_not_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Copilot flag reason must not be blank")
        return value


class PacketCopilotCritic(_StrictModel):
    packet_id: str = Field(pattern=PACKET_ID_PATTERN)
    verdict: Literal["pass", "flag"]
    flagged_items: tuple[PacketCopilotFlag, ...] = Field(max_length=24)

    @model_validator(mode="after")
    def _verdict_matches_flags(self) -> PacketCopilotCritic:
        if self.verdict == "pass" and self.flagged_items:
            raise ValueError("pass critic verdict requires no flagged_items")
        if self.verdict == "flag" and not self.flagged_items:
            raise ValueError("flag critic verdict requires flagged_items")
        paths = tuple(item.item_path for item in self.flagged_items)
        if len(set(paths)) != len(paths):
            raise ValueError("critic flagged_items must identify unique item paths")
        return self


def _record_identity_payload(record: PacketCopilotRecord) -> dict[str, object]:
    return record.model_dump(mode="json", exclude={"record_id", "recorded_at"})


def _record_id(record: PacketCopilotRecord) -> str:
    canonical = json.dumps(
        _record_identity_payload(record), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return f"copilot-{hashlib.sha256(canonical).hexdigest()[:24]}"


class PacketCopilotRecord(_StrictModel):
    record_id: str = Field(pattern=RECORD_ID_PATTERN)
    schema_version: Literal[1] = 1
    packet_id: str = Field(pattern=PACKET_ID_PATTERN)
    request_kind: Literal["explain-and-challenge"] = "explain-and-challenge"
    report: PacketCopilotDraft
    analyst_decision_id: str = Field(pattern=DECISION_ID_PATTERN)
    critic_decision_id: str = Field(pattern=DECISION_ID_PATTERN)
    analyst_model: ModelMeta
    critic_model: ModelMeta
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def _recorded_at_is_aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("recorded_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def _record_is_consistent(self) -> PacketCopilotRecord:
        if self.report.packet_id != self.packet_id:
            raise ValueError("Copilot report packet_id does not match its record")
        if self.record_id != _record_id(self):
            raise ValueError("record_id does not match the Copilot record content")
        return self

    @classmethod
    def accepted(
        cls,
        *,
        packet_id: str,
        report: PacketCopilotDraft,
        analyst_decision_id: str,
        critic_decision_id: str,
        analyst_model: ModelMeta | None,
        critic_model: ModelMeta | None,
        recorded_at: datetime,
    ) -> PacketCopilotRecord:
        provisional = cls.model_construct(
            record_id="copilot-" + "0" * 24,
            schema_version=1,
            packet_id=packet_id,
            request_kind="explain-and-challenge",
            report=report,
            analyst_decision_id=analyst_decision_id,
            critic_decision_id=critic_decision_id,
            analyst_model=analyst_model,
            critic_model=critic_model,
            recorded_at=recorded_at.astimezone(UTC),
        )
        return cls.model_validate(
            provisional.model_dump() | {"record_id": _record_id(provisional)}
        )


class PacketCopilotState(_StrictModel):
    status: Literal["idle", "ready", "degraded"]
    packet_id: str = Field(pattern=PACKET_ID_PATTERN)
    record: PacketCopilotRecord | None = None
    reason_code: str | None = Field(default=None, min_length=1, max_length=128)

    @model_validator(mode="after")
    def _state_is_consistent(self) -> PacketCopilotState:
        if self.status == "ready":
            if self.record is None or self.reason_code is not None:
                raise ValueError("ready Copilot state requires only a record")
            if self.record.packet_id != self.packet_id:
                raise ValueError("ready Copilot state record must match packet_id")
        elif self.record is not None:
            raise ValueError("non-ready Copilot state cannot expose a record")
        elif self.status == "idle" and self.reason_code is not None:
            raise ValueError("idle Copilot state cannot carry a reason_code")
        elif self.status == "degraded" and self.reason_code is None:
            raise ValueError("degraded Copilot state requires a reason_code")
        return self


class PacketCopilotStore:
    """Append-only accepted Copilot reports under one decisions root."""

    def __init__(self, root: Path) -> None:
        self._store = JsonlStore(
            root,
            filename=COPILOT_RECORDS_FILE,
            model=PacketCopilotRecord,
            label="packet Copilot store",
            id_label="packet Copilot record",
            key=lambda record: record.record_id,
            extra_validate=self._validate_identity,
        )

    @property
    def root(self) -> Path:
        return self._store.root

    @property
    def path(self) -> Path:
        return self._store.path

    @staticmethod
    def _validate_identity(record: PacketCopilotRecord) -> None:
        if record.record_id != _record_id(record):
            raise ValueError("packet Copilot record identity does not match canonical content")

    def record(self, record: PacketCopilotRecord) -> PacketCopilotRecord:
        self._validate_identity(record)
        return self._store.append(record)

    def latest(self, packet_id: str) -> PacketCopilotRecord | None:
        records = [record for record in self._store.read() if record.packet_id == packet_id]
        if not records:
            return None
        return max(records, key=lambda record: (record.recorded_at, record.record_id))


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _citations(report: PacketCopilotDraft) -> tuple[Citation, ...]:
    return tuple(citation for item in report.items() for citation in item.citations)


def _same_decision_content(left: DecisionRecord, right: DecisionRecord) -> bool:
    return left.model_dump(exclude={"recorded_at"}) == right.model_dump(
        exclude={"recorded_at"}
    )


class PacketCopilotService:
    """Two-stage, fail-closed Copilot processing for one persisted packet."""

    def __init__(
        self,
        *,
        packet_store: DecisionPacketStore,
        store: PacketCopilotStore,
        decision_log: DecisionLog,
        analyst_gateway: ModelGateway | None,
        critic_gateway: ModelGateway | None,
        analyst_model: ModelMeta,
        critic_model: ModelMeta,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.packet_store = packet_store
        self.store = store
        self.decision_log = decision_log
        self.analyst_gateway = analyst_gateway
        self.critic_gateway = critic_gateway
        self.analyst_model = analyst_model
        self.critic_model = critic_model
        self._now = now if now is not None else lambda: datetime.now(UTC)

    @staticmethod
    def _degraded(packet_id: str) -> PacketCopilotState:
        return PacketCopilotState(
            status="degraded",
            packet_id=packet_id,
            record=None,
            reason_code=DEGRADED_REASON,
        )

    def latest(self, packet_id: str) -> PacketCopilotState:
        self.packet_store.get(packet_id)
        record = self.store.latest(packet_id)
        if record is None:
            return PacketCopilotState(status="idle", packet_id=packet_id)
        return PacketCopilotState(status="ready", packet_id=packet_id, record=record)

    def _validate_report(
        self,
        report: PacketCopilotDraft,
        packet_id: str,
    ) -> tuple[Citation, ...]:
        report.validate_for_packet(packet_id)
        citations = _citations(report)
        source = DecisionPacketSource(self.packet_store)
        for citation in citations:
            if citation.source_kind != "packet" or citation.source_id != packet_id:
                raise ValueError("Copilot citation does not bind the requested packet")
            resolve_citation(citation, {"packet": source})
        return citations

    def _record_decision(self, candidate: DecisionRecord) -> DecisionRecord:
        try:
            existing = self.decision_log.get(candidate.decision_id)
        except ValueError as error:
            if "no decision recorded" not in str(error):
                raise
            return self.decision_log.record(candidate)
        if not _same_decision_content(existing, candidate):
            raise ValueError("decision log identity collision")
        return existing

    def request(self, packet_id: str) -> PacketCopilotState:
        packet = self.packet_store.get(packet_id)
        existing = self.store.latest(packet_id)
        if existing is not None:
            return PacketCopilotState(status="ready", packet_id=packet_id, record=existing)
        if (
            self.analyst_gateway is None
            or self.critic_gateway is None
            or self.analyst_model is None
            or self.critic_model is None
        ):
            return self._degraded(packet_id)

        try:
            packet_json = _canonical_json(packet.model_dump(mode="json"))
            analyst_context, _ = redact_context({"packet": packet_json})
            analyst_prompt = (
                "Explain and challenge this exact persisted DecisionPacket. "
                "Every item must cite an exact packet scalar or scalar-list fact.\n\n"
                f"Packet:\n{analyst_context['packet']}"
            )
            report = self.analyst_gateway.complete_structured(
                ModelRequest(
                    messages=[
                        ChatMessage(
                            role="system",
                            content=(
                                "You are an advisory research analyst. You have no risk, "
                                "approval, sizing, execution or blocker-override authority."
                            ),
                        ),
                        ChatMessage(role="user", content=analyst_prompt),
                    ],
                    temperature=0.0,
                    max_tokens=4_096,
                ),
                PacketCopilotDraft,
            )
            citations = self._validate_report(report, packet_id)

            critic_context, _ = redact_context(
                {
                    "packet": packet_json,
                    "draft": report.model_dump_json(),
                }
            )
            critic_prompt = (
                "Validate the complete advisory report against the exact packet. "
                "Flag any unsupported, substituted or authority-shaped item; pass only "
                "when every item and citation is valid.\n\n"
                f"Packet:\n{critic_context['packet']}\n\n"
                f"Draft:\n{critic_context['draft']}"
            )
            critic = self.critic_gateway.complete_structured(
                ModelRequest(
                    messages=[
                        ChatMessage(
                            role="system",
                            content="You are the fail-closed critic for packet-bound research.",
                        ),
                        ChatMessage(role="user", content=critic_prompt),
                    ],
                    temperature=0.0,
                    max_tokens=2_048,
                ),
                PacketCopilotCritic,
            )
            if critic.packet_id != packet_id:
                raise ValueError("Copilot critic packet_id does not match the request")
            if critic.verdict != "pass" or critic.flagged_items:
                raise ValueError("Copilot critic refused the report")
            self._validate_report(report, packet_id)

            run_id = hashlib.sha256(
                f"packet-copilot-v1:{packet_id}:explain-and-challenge".encode()
            ).hexdigest()[:16]
            recorded_at = self._now()
            if recorded_at.tzinfo is None:
                raise ValueError("Copilot clock must be timezone-aware")
            recorded_at = recorded_at.astimezone(UTC)
            analyst_decision = DecisionRecord.for_stage(
                run_id=run_id,
                role="analyst",
                model=self.analyst_model,
                prompt=analyst_prompt,
                schema_id="packet-copilot-draft-v1",
                output=report,
                citations=list(citations),
                recorded_at=recorded_at,
            )
            critic_decision = DecisionRecord.for_stage(
                run_id=run_id,
                role="critic",
                model=self.critic_model,
                prompt=critic_prompt,
                schema_id="packet-copilot-critic-v1",
                output=critic,
                recorded_at=recorded_at,
            )
            analyst_decision = self._record_decision(analyst_decision)
            critic_decision = self._record_decision(critic_decision)
            record = PacketCopilotRecord.accepted(
                packet_id=packet_id,
                report=report,
                analyst_decision_id=analyst_decision.decision_id,
                critic_decision_id=critic_decision.decision_id,
                analyst_model=self.analyst_model,
                critic_model=self.critic_model,
                recorded_at=recorded_at,
            )
            self.store.record(record)
            return PacketCopilotState(status="ready", packet_id=packet_id, record=record)
        except Exception:
            return self._degraded(packet_id)


__all__ = [
    "COPILOT_RECORDS_FILE",
    "PacketCopilotCritic",
    "PacketCopilotDraft",
    "PacketCopilotFlag",
    "PacketCopilotItem",
    "PacketCopilotRecord",
    "PacketCopilotService",
    "PacketCopilotState",
    "PacketCopilotStore",
]
