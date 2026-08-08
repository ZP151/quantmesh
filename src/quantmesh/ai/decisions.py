"""Content-addressed research decision log (M8, issue #48, Phase D).

Every pipeline stage records a `DecisionRecord` — run identity, role,
model metadata, the redacted prompt's digest, the output schema id,
the verdict, citations, the output digest and any refusal — on the
ADR-0006 ledger discipline under `settings.decisions_dir`. Identity is
content-addressed: `decision_id` is a 16-hex sha256 over the record
minus `recorded_at` (the FundingLedger precedent), so an identical
replay is refused as a duplicate and any difference is a new audit
entry. `DecisionRecord.for_stage` builds a record from the redacted
prompt text and the validated stage output, so digests cannot drift
from what was actually sent and produced.
"""

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from quantmesh.ai.retrieval import Citation
from quantmesh.ai.roles import ROLE_ORDER
from quantmesh.settings import settings

__all__ = [
    "DECISIONS_FILE",
    "DecisionLog",
    "DecisionRecord",
    "ModelMeta",
]

DECISIONS_FILE = "decisions.jsonl"

ID_PATTERN = "^[0-9a-f]{16}$"
DIGEST_PATTERN = "^[0-9a-f]{64}$"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class _IdentityMaterial:
    """Canonical identity content of a record (minus decision_id and
    recorded_at), with its content-addressed 16-hex id."""

    text: str

    @property
    def id(self) -> str:
        return _sha256(self.text)[:16]


def _identity_material(
    *,
    run_id: str,
    role: str,
    model: "ModelMeta",
    prompt_digest: str,
    schema_id: str,
    verdict: str,
    citations: list[Citation],
    output_digest: str,
    refusal: str | None,
) -> _IdentityMaterial:
    """The record's identity material: every content field that defines
    the audit entry. `recorded_at` is deliberately excluded — an
    identical replay is the same decision, refused as a duplicate."""
    return _IdentityMaterial(
        _canonical_json(
            {
                "run_id": run_id,
                "role": role,
                "model": model.model_dump(),
                "prompt_digest": prompt_digest,
                "schema_id": schema_id,
                "verdict": verdict,
                "citations": [citation.model_dump() for citation in citations],
                "output_digest": output_digest,
                "refusal": refusal,
            }
        )
    )


class ModelMeta(BaseModel):
    """The model that produced the recorded output (metadata only)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    endpoint_kind: str = Field(pattern="^(loopback|remote|scripted)$")


class DecisionRecord(BaseModel):
    """One content-addressed audit entry for one pipeline stage."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(pattern=ID_PATTERN)
    run_id: str = Field(pattern=ID_PATTERN)
    role: str = Field(pattern="^(analyst|critic|risk|portfolio)$")
    model: ModelMeta
    prompt_digest: str = Field(pattern=DIGEST_PATTERN)
    schema_id: str = Field(min_length=1)
    verdict: str = Field(min_length=1)
    citations: list[Citation] = Field(default_factory=list)
    output_digest: str = Field(pattern=DIGEST_PATTERN)
    refusal: str | None = Field(default=None, min_length=1)
    recorded_at: datetime

    @model_validator(mode="after")
    def _record_is_consistent(self) -> "DecisionRecord":
        if self.recorded_at.tzinfo is None:
            raise ValueError("recorded_at must be timezone-aware")
        self.recorded_at = self.recorded_at.astimezone(UTC)
        if self.decision_id != _identity_material(
            run_id=self.run_id,
            role=self.role,
            model=self.model,
            prompt_digest=self.prompt_digest,
            schema_id=self.schema_id,
            verdict=self.verdict,
            citations=self.citations,
            output_digest=self.output_digest,
            refusal=self.refusal,
        ).id:
            raise ValueError("decision_id does not match the record's content")
        return self

    @classmethod
    def for_stage(
        cls,
        *,
        run_id: str,
        role: str,
        model: ModelMeta,
        prompt: str,
        schema_id: str,
        output: BaseModel,
        citations: list[Citation] | None = None,
        refusal: str | None = None,
        recorded_at: datetime | None = None,
    ) -> "DecisionRecord":
        """A record built from the redacted prompt and the validated output.

        Digests are computed here from exactly what the stage was sent
        and produced, so they cannot drift from the wire. The verdict
        is the output's own ``verdict`` field when it has one (critic
        pass/flag), else its ``posture`` (risk/portfolio), else the
        output's canonical JSON. The id is computed from the raw
        fields, so the consistency validator has the true id at
        construction.
        """
        if role not in ROLE_ORDER:
            raise ValueError(f"unknown research role: {role!r}")
        verdict = getattr(output, "verdict", None)
        if not isinstance(verdict, str) or not verdict.strip():
            verdict = getattr(output, "posture", None)
        if not isinstance(verdict, str) or not verdict.strip():
            verdict = output.model_dump_json()
        fields = {
            "run_id": run_id,
            "role": role,
            "model": model,
            "prompt_digest": _sha256(prompt),
            "schema_id": schema_id,
            "verdict": verdict,
            "citations": citations or [],
            "output_digest": _sha256(output.model_dump_json()),
            "refusal": refusal,
        }
        return cls(
            decision_id=_identity_material(**fields).id,
            **fields,
            recorded_at=recorded_at if recorded_at is not None else datetime.now(UTC),
        )


class DecisionLog:
    """Append-only JSONL ledger of decision records under one root."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else settings.decisions_dir

    def record(self, record: DecisionRecord) -> DecisionRecord:
        """Append a record; a duplicate decision_id is refused."""
        existing = self.all()
        if any(entry.decision_id == record.decision_id for entry in existing):
            raise ValueError(f"decision {record.decision_id!r} already recorded")
        self._append(existing + [record])
        return record

    def get(self, decision_id: str) -> DecisionRecord:
        """The record with this id; raises when absent or unreadable."""
        for entry in self.all():
            if entry.decision_id == decision_id:
                return entry
        raise ValueError(f"no decision recorded with id {decision_id!r}")

    def all(self) -> list[DecisionRecord]:
        return self._read()

    def _append(self, records: list[DecisionRecord]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / DECISIONS_FILE
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{DECISIONS_FILE}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(record.model_dump_json())
                    handle.write("\n")
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _read(self) -> list[DecisionRecord]:
        if not self.root.exists():
            return []
        if not self.root.is_dir():
            raise ValueError(f"decision log root {self.root} is not a directory")
        path = self.root / DECISIONS_FILE
        if not path.exists():
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"decision log {path} is unreadable") from error
        records: list[DecisionRecord] = []
        seen: dict[str, int] = {}
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = DecisionRecord.model_validate_json(line)
            except Exception as error:
                raise ValueError(
                    f"decision log {path} line {line_number} is invalid"
                ) from error
            if record.decision_id in seen:
                raise ValueError(
                    f"decision log {path} lines {seen[record.decision_id]} and "
                    f"{line_number} share a decision id"
                )
            seen[record.decision_id] = line_number
            records.append(record)
        return records
