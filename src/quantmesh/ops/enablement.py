"""Per-venue live-enablement approval state machine (M10 Phase E,
issue #62).

``ApprovalLedger`` persists per-venue enablement state on the ADR-0006
JSONL discipline: append-only records, atomic temp+replace writes,
fail-closed reads with line attribution, duplicate-id refusal. State is
*derived* from the ledger (the target state of the latest record per
venue), so the ledger and the reported state can never disagree.

The only path to ``enabled`` is an approval record that carries the
recorded live-enablement gate text verbatim (``GATE_TEXT``) — the
record names who approved, when, and which gate text was presented.
The machine's allowed edges are fixed: disabled → pending (request),
pending → enabled (approval), pending → disabled (withdraw),
enabled → disabled (revoke); every other transition is a typed refusal
before anything is written. In M10 the approval records exist only in
fixtures and drills — no live execution surface exists, and nothing in
the code path can fabricate a real approval.
"""

import hashlib
import json
import os
import tempfile
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from quantmesh._fs import atomic_replace
from quantmesh.domain.models import Venue
from quantmesh.research.reports import ID_PATTERN
from quantmesh.settings import settings

ENABLEMENT_FILE = "enablement.jsonl"

# The recorded live-enablement gate, verbatim from the long-running
# goal (docs/goals/ACTIVE.md, ADR-0012 decision 5, iteration 0012).
GATE_TEXT = (
    "real-money trading, wallet signing, live broker orders, "
    "credentials, paid infrastructure, and AI order authority all "
    "require explicit human approval"
)


class EnablementState(StrEnum):
    DISABLED = "disabled"
    PENDING = "pending"
    ENABLED = "enabled"


EnablementKind = Literal["request", "approval", "withdraw", "revoke"]

# The only legal transitions; the record kind names the edge.
_TRANSITIONS: dict[EnablementKind, tuple[EnablementState, EnablementState]] = {
    "request": (EnablementState.DISABLED, EnablementState.PENDING),
    "approval": (EnablementState.PENDING, EnablementState.ENABLED),
    "withdraw": (EnablementState.PENDING, EnablementState.DISABLED),
    "revoke": (EnablementState.ENABLED, EnablementState.DISABLED),
}


class EnablementError(ValueError):
    """Base for the enablement surface's typed errors."""


class EnablementTransitionError(EnablementError):
    """The record's kind does not match the venue's current state."""


class EnablementGateError(EnablementError):
    """An approval record does not carry the recorded gate text."""


def approval_id(
    *,
    venue: Venue,
    kind: EnablementKind,
    actor: str,
    acted_at: datetime,
    gate_text: str | None,
) -> str:
    """Deterministic approval identity over every content field. An
    identical replay at the same instant is a duplicate (refused); any
    difference is a new audit entry."""
    canonical = json.dumps(
        {
            "venue": venue.value,
            "kind": kind,
            "actor": actor,
            "acted_at": acted_at.astimezone(UTC).isoformat(),
            "gate_text": gate_text,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(f"enablement\0{canonical}".encode()).hexdigest()[:16]


class ApprovalRecord(BaseModel):
    """One enablement transition record: who, when, and (for an
    approval) which gate text was presented."""

    id: str = Field(pattern=ID_PATTERN)
    venue: Venue
    kind: EnablementKind
    actor: str = Field(min_length=1, max_length=64)
    acted_at: datetime
    gate_text: str | None = None

    @field_validator("actor")
    @classmethod
    def actor_is_not_blank(cls, actor: str) -> str:
        if not actor.strip():
            raise ValueError("actor must name the human performing the action")
        return actor

    @model_validator(mode="after")
    def record_is_consistent(self) -> "ApprovalRecord":
        if self.acted_at.tzinfo is None:
            raise ValueError("acted_at must be timezone-aware")
        self.acted_at = self.acted_at.astimezone(UTC)
        if (self.kind == "approval") != (self.gate_text is not None):
            raise ValueError(
                f"kind {self.kind!r} requires gate_text to be present exactly "
                "on an approval"
            )
        if self.kind == "approval" and self.gate_text != GATE_TEXT:
            raise ValueError(
                "approval record's gate_text does not match the recorded "
                "live-enablement gate"
            )
        expected = approval_id(
            venue=self.venue,
            kind=self.kind,
            actor=self.actor,
            acted_at=self.acted_at,
            gate_text=self.gate_text,
        )
        if self.id != expected:
            raise ValueError(
                f"approval record id {self.id!r} does not match its content "
                f"(expected {expected!r})"
            )
        return self


class ApprovalLedger:
    """Append-only JSONL ledger of enablement approval records
    (ADR-0006 discipline); per-venue state is derived from it."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else settings.enablement_dir

    def all(self) -> list[ApprovalRecord]:
        return self._read()

    def states(self) -> dict[Venue, EnablementState]:
        """Per-venue state derived from the ledger: the target state of
        the latest record wins; a venue with no records is disabled."""
        derived: dict[Venue, EnablementState] = {}
        for record in self.all():
            derived[record.venue] = _TRANSITIONS[record.kind][1]
        return derived

    def state(self, venue: Venue) -> EnablementState:
        return self.states().get(venue, EnablementState.DISABLED)

    def request(self, venue: Venue, *, actor: str, acted_at: datetime) -> ApprovalRecord:
        """disabled → pending: the operator requests enablement."""
        return self._record("request", venue, actor=actor, acted_at=acted_at)

    def approve(
        self, venue: Venue, *, actor: str, acted_at: datetime, gate_text: str
    ) -> ApprovalRecord:
        """pending → enabled: the ONLY path to ``enabled``. The
        approval must carry the recorded gate text verbatim; a
        stale, watered-down or missing gate is refused before
        anything is written."""
        if gate_text != GATE_TEXT:
            raise EnablementGateError(
                "approval gate_text does not match the recorded "
                "live-enablement gate"
            )
        return self._record(
            "approval", venue, actor=actor, acted_at=acted_at, gate_text=gate_text
        )

    def withdraw(self, venue: Venue, *, actor: str, acted_at: datetime) -> ApprovalRecord:
        """pending → disabled: the request is withdrawn or denied."""
        return self._record("withdraw", venue, actor=actor, acted_at=acted_at)

    def revoke(self, venue: Venue, *, actor: str, acted_at: datetime) -> ApprovalRecord:
        """enabled → disabled: the approval is revoked."""
        return self._record("revoke", venue, actor=actor, acted_at=acted_at)

    def _record(
        self,
        kind: EnablementKind,
        venue: Venue,
        *,
        actor: str,
        acted_at: datetime,
        gate_text: str | None = None,
    ) -> ApprovalRecord:
        if acted_at.tzinfo is None:
            raise ValueError("acted_at must be timezone-aware")
        acted_at = acted_at.astimezone(UTC)
        from_state, _to_state = _TRANSITIONS[kind]
        current = self.state(venue)
        if current is not from_state:
            raise EnablementTransitionError(
                f"{kind} record for venue {venue.value} requires state "
                f"{from_state.value}, ledger shows {current.value}"
            )
        record = ApprovalRecord(
            id=approval_id(
                venue=venue,
                kind=kind,
                actor=actor,
                acted_at=acted_at,
                gate_text=gate_text,
            ),
            venue=venue,
            kind=kind,
            actor=actor,
            acted_at=acted_at,
            gate_text=gate_text,
        )
        existing = self.all()
        if any(item.id == record.id for item in existing):
            raise ValueError(f"enablement record {record.id!r} already recorded")
        self._write(existing + [record])
        return record

    def _write(self, records: list[ApprovalRecord]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / ENABLEMENT_FILE
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{ENABLEMENT_FILE}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(record.model_dump_json())
                    handle.write("\n")
            atomic_replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _read(self) -> list[ApprovalRecord]:
        if not self.root.exists():
            return []
        if not self.root.is_dir():
            raise ValueError(f"enablement store root {self.root} is not a directory")
        path = self.root / ENABLEMENT_FILE
        if not path.exists():
            return []
        if not path.is_file():
            raise ValueError(f"enablement path {path} is not a file")
        records: list[ApprovalRecord] = []
        with path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = ApprovalRecord.model_validate_json(line)
                except Exception as error:  # noqa: BLE001 — attribution below
                    raise ValueError(
                        f"enablement store {path} line {index} is invalid: {error}"
                    ) from error
                if any(item.id == record.id for item in records):
                    raise ValueError(
                        f"enablement store {path} lines share a record id "
                        f"{record.id!r}"
                    )
                records.append(record)
        return records
