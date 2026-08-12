"""Reconciliation-disciplined cross-platform event mapping (issue #37, Phase D).

A Polymarket ``EventMarket`` and a Kalshi ``EventMarket`` describing the
same real-world event are paired only through explicit, recorded
evidence — never silent fuzzy matching (ADR-0008 decision 5). Four
independent evidence kinds are evaluated per candidate pair:

- **Title** — the normalized question texts are equal.
- **Outcome set** — the normalized outcome name sets are equal.
- **Expiry** — both events carry expiries within the tolerance.
- **Resolution rule** — the canonical rule fingerprints are equal.

Pair status is a deterministic function of the satisfied evidence
(ADR-0006 discipline applied to events): two or more independent
evidence items make a pair MATCHED; exactly one leaves it PENDING
(more evidence — typically the resolution itself — is required); and
when one event is strongly matched by two candidates on the other
venue, the conflicting pairs are AMBIGUOUS with all their evidence
recorded. Events with no candidate pair at all are reported unmatched,
never guessed.

Every pair that passes mapping is recorded in the append-only mapping
ledger (``MappingLedger``, JSONL with atomic appends and fail-closed
reads with line attribution), one record per pair with its status,
evidence, and the code commit that produced it. Re-recording an
identical pair state is refused; re-evaluating a pair with different
evidence is history, not an error — a PENDING pair that later matches
on the resolution upgrades to MATCHED with the evidence to prove it.
"""

import hashlib
import json
import os
import subprocess
import tempfile
import unicodedata
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError, model_validator

from quantmesh._fs import atomic_replace
from quantmesh.events.models import EventMarket
from quantmesh.settings import settings

__all__ = [
    "EvidenceKind",
    "EventMappingReport",
    "EventPairing",
    "MappingEvidence",
    "MappingLedger",
    "MappingRecord",
    "MappingStatus",
    "MAPPINGS_FILE",
    "map_events",
    "normalize_event_text",
    "pair_key",
]

MAPPINGS_FILE = "mappings.jsonl"

ID_PATTERN = "^[0-9a-f]{16}$"
COMMIT_PATTERN = "^[0-9a-f]{7,64}$"

# Default expiry tolerance for the EXPIRY evidence (seconds). Two
# venues rarely stamp the same instant; an hour of slack admits
# sub-minute clock skew without admitting adjacent meetings.
_DEFAULT_EXPIRY_TOLERANCE_S = 3600.0

# Evidence count that upgrades a pair from PENDING to MATCHED.
_STRONG_EVIDENCE = 2


class MappingStatus(StrEnum):
    """Deterministic verdict per candidate pair."""

    MATCHED = "matched"
    PENDING = "pending"
    AMBIGUOUS = "ambiguous"


class EvidenceKind(StrEnum):
    """The four independent evidence kinds; a pair needs two."""

    TITLE = "title"
    OUTCOME_SET = "outcome_set"
    EXPIRY = "expiry"
    RESOLUTION_RULE = "resolution_rule"


def normalize_event_text(text: str) -> str:
    """Canonical form for comparing event texts across venues.

    Same normalization as resolution-rule fingerprints (ADR-0008):
    NFKC, case folding, whitespace collapsing — two venues stating the
    same question with different casing or wrapping compare equal,
    while any substantive wording change does not.
    """
    folded = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(folded.split())


def pair_key(polymarket_market_id: str, kalshi_market_id: str) -> str:
    """Deterministic, order-invariant identity of a candidate pair."""
    canonical = json.dumps(
        sorted([polymarket_market_id, kalshi_market_id]),
        separators=(",", ":"),
    )
    return hashlib.sha256(f"event-pair\0{canonical}".encode()).hexdigest()[:16]


class MappingEvidence(BaseModel):
    """One satisfied evidence item, with what satisfied it."""

    kind: EvidenceKind
    detail: str = Field(min_length=1)


class EventPairing(BaseModel):
    """One candidate pair and the verdict over its recorded evidence."""

    pair_key: str = Field(pattern=ID_PATTERN)
    polymarket_market_id: str = Field(min_length=1)
    kalshi_market_id: str = Field(min_length=1)
    status: MappingStatus
    evidence: list[MappingEvidence] = Field(min_length=1)

    @model_validator(mode="after")
    def pair_is_consistent(self) -> "EventPairing":
        if self.pair_key != pair_key(self.polymarket_market_id, self.kalshi_market_id):
            raise ValueError(
                f"pair key {self.pair_key!r} does not match the pair "
                f"({self.polymarket_market_id!r}, {self.kalshi_market_id!r})"
            )
        expected = sorted(
            self.evidence,
            key=lambda item: (item.kind.value, item.detail),
        )
        if [item.kind for item in self.evidence] != [item.kind for item in expected]:
            raise ValueError(
                f"pair {self.pair_key!r}: evidence must be sorted by kind"
            )
        if self.status is MappingStatus.PENDING and len(self.evidence) != 1:
            raise ValueError(
                f"pair {self.pair_key!r}: a pending pair has exactly one "
                f"evidence item, got {len(self.evidence)}"
            )
        if (
            self.status in (MappingStatus.MATCHED, MappingStatus.AMBIGUOUS)
            and len(self.evidence) < _STRONG_EVIDENCE
        ):
            raise ValueError(
                f"pair {self.pair_key!r}: {self.status.value} needs at least "
                f"{_STRONG_EVIDENCE} evidence items, got {len(self.evidence)}"
            )
        return self


class EventMappingReport(BaseModel):
    """The full verdict of one mapping pass over two fixture universes."""

    pairs: list[EventPairing] = Field(default_factory=list)
    unmatched_polymarket: list[str] = Field(default_factory=list)
    unmatched_kalshi: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def report_is_consistent(self) -> "EventMappingReport":
        keys = [pair.pair_key for pair in self.pairs]
        if len(keys) != len(set(keys)):
            raise ValueError("mapping report lists a pair more than once")
        poly_ids = {pair.polymarket_market_id for pair in self.pairs}
        if poly_ids & set(self.unmatched_polymarket):
            raise ValueError(
                "a polymarket event cannot be both paired and unmatched"
            )
        kalshi_ids = {pair.kalshi_market_id for pair in self.pairs}
        if kalshi_ids & set(self.unmatched_kalshi):
            raise ValueError("a kalshi event cannot be both paired and unmatched")
        return self


def _titles_match(poly: EventMarket, kalshi: EventMarket) -> bool:
    return normalize_event_text(poly.title) == normalize_event_text(kalshi.title)


def _outcome_sets_match(poly: EventMarket, kalshi: EventMarket) -> bool:
    return sorted(
        normalize_event_text(outcome.name) for outcome in poly.outcomes
    ) == sorted(normalize_event_text(outcome.name) for outcome in kalshi.outcomes)


def _expiry_within(poly: EventMarket, kalshi: EventMarket, tolerance_s: float) -> bool:
    if poly.expiry_at is None or kalshi.expiry_at is None:
        return False
    return abs((poly.expiry_at - kalshi.expiry_at).total_seconds()) <= tolerance_s


def _rules_match(poly: EventMarket, kalshi: EventMarket) -> bool:
    return poly.resolution_rule.fingerprint == kalshi.resolution_rule.fingerprint


def _evidence_for(
    poly: EventMarket, kalshi: EventMarket, tolerance_s: float
) -> list[MappingEvidence]:
    items: list[MappingEvidence] = []
    if _titles_match(poly, kalshi):
        items.append(
            MappingEvidence(
                kind=EvidenceKind.TITLE,
                detail=f"normalized titles equal: {normalize_event_text(poly.title)}",
            )
        )
    if _outcome_sets_match(poly, kalshi):
        names = sorted(
            normalize_event_text(outcome.name) for outcome in poly.outcomes
        )
        items.append(
            MappingEvidence(
                kind=EvidenceKind.OUTCOME_SET,
                detail=f"outcome sets equal: {', '.join(names)}",
            )
        )
    if _expiry_within(poly, kalshi, tolerance_s):
        items.append(
            MappingEvidence(
                kind=EvidenceKind.EXPIRY,
                detail=(
                    f"expiries within {tolerance_s:g}s: "
                    f"{poly.expiry_at.isoformat()} vs "
                    f"{kalshi.expiry_at.isoformat()}"
                ),
            )
        )
    if _rules_match(poly, kalshi):
        items.append(
            MappingEvidence(
                kind=EvidenceKind.RESOLUTION_RULE,
                detail=f"resolution-rule fingerprint {poly.resolution_rule.fingerprint}",
            )
        )
    return sorted(items, key=lambda item: (item.kind.value, item.detail))


def map_events(
    polymarket_events: list[EventMarket],
    kalshi_events: list[EventMarket],
    *,
    expiry_tolerance_s: float = _DEFAULT_EXPIRY_TOLERANCE_S,
) -> EventMappingReport:
    """Map two fixture universes into evidence-backed pairs.

    Deterministic over its inputs: the verdict depends only on the
    satisfied evidence, never on list order (pairs are sorted by pair
    key) and never on a guess.
    """
    if not polymarket_events or not kalshi_events:
        raise ValueError("mapping needs at least one event per venue")
    for label, events in (("polymarket", polymarket_events), ("kalshi", kalshi_events)):
        ids = [event.venue_market_id for event in events]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{label} events repeat a venue_market_id")

    candidates: list[tuple[EventMarket, EventMarket, list[MappingEvidence]]] = []
    for poly in polymarket_events:
        for kalshi in kalshi_events:
            evidence = _evidence_for(poly, kalshi, expiry_tolerance_s)
            if evidence:
                candidates.append((poly, kalshi, evidence))

    strong_by_poly: dict[str, int] = {}
    strong_by_kalshi: dict[str, int] = {}
    for poly, kalshi, evidence in candidates:
        if len(evidence) >= _STRONG_EVIDENCE:
            strong_by_poly[poly.venue_market_id] = (
                strong_by_poly.get(poly.venue_market_id, 0) + 1
            )
            strong_by_kalshi[kalshi.venue_market_id] = (
                strong_by_kalshi.get(kalshi.venue_market_id, 0) + 1
            )

    pairs: list[EventPairing] = []
    paired_poly: set[str] = set()
    paired_kalshi: set[str] = set()
    for poly, kalshi, evidence in candidates:
        key = pair_key(poly.venue_market_id, kalshi.venue_market_id)
        if len(evidence) >= _STRONG_EVIDENCE and (
            strong_by_poly[poly.venue_market_id] > 1
            or strong_by_kalshi[kalshi.venue_market_id] > 1
        ):
            status = MappingStatus.AMBIGUOUS
        elif len(evidence) >= _STRONG_EVIDENCE:
            status = MappingStatus.MATCHED
        else:
            status = MappingStatus.PENDING
        pairs.append(
            EventPairing(
                pair_key=key,
                polymarket_market_id=poly.venue_market_id,
                kalshi_market_id=kalshi.venue_market_id,
                status=status,
                evidence=evidence,
            )
        )
        paired_poly.add(poly.venue_market_id)
        paired_kalshi.add(kalshi.venue_market_id)

    return EventMappingReport(
        pairs=sorted(pairs, key=lambda pair: pair.pair_key),
        unmatched_polymarket=sorted(
            event.venue_market_id
            for event in polymarket_events
            if event.venue_market_id not in paired_poly
        ),
        unmatched_kalshi=sorted(
            event.venue_market_id
            for event in kalshi_events
            if event.venue_market_id not in paired_kalshi
        ),
    )


class MappingRecord(BaseModel):
    """One ledger entry: a pair's verdict at the time it was recorded."""

    pair_key: str = Field(pattern=ID_PATTERN)
    status: MappingStatus
    evidence: list[MappingEvidence] = Field(min_length=1)
    commit: str = Field(pattern=COMMIT_PATTERN)
    recorded_at: datetime

    @model_validator(mode="after")
    def record_is_consistent(self) -> "MappingRecord":
        if self.recorded_at.tzinfo is None:
            raise ValueError("recorded_at must be timezone-aware")
        self.recorded_at = self.recorded_at.astimezone(UTC)
        expected = sorted(
            self.evidence,
            key=lambda item: (item.kind.value, item.detail),
        )
        if [item.kind for item in self.evidence] != [item.kind for item in expected]:
            raise ValueError(
                f"pair {self.pair_key!r}: evidence must be sorted by kind"
            )
        if self.status is MappingStatus.PENDING and len(self.evidence) != 1:
            raise ValueError(
                f"pair {self.pair_key!r}: a pending record has exactly one "
                f"evidence item, got {len(self.evidence)}"
            )
        if (
            self.status in (MappingStatus.MATCHED, MappingStatus.AMBIGUOUS)
            and len(self.evidence) < _STRONG_EVIDENCE
        ):
            raise ValueError(
                f"pair {self.pair_key!r}: {self.status.value} needs at least "
                f"{_STRONG_EVIDENCE} evidence items, got {len(self.evidence)}"
            )
        return self


class MappingLedger:
    """Append-only record of every mapping verdict (ADR-0006 discipline).

    Atomic appends (temp + replace), fail-closed reads with line
    attribution, and identical re-records refused — but a pair
    re-evaluated with *different* evidence appends as history: a
    PENDING pair that later matches on the resolution records both
    verdicts, and ``by_pair`` returns them in order.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else settings.mappings_dir

    def record(
        self,
        report: EventMappingReport,
        commit: str | None = None,
        recorded_at: datetime | None = None,
    ) -> list[MappingRecord]:
        """Record every pair verdict of a report in one timestamped batch.

        ``recorded_at`` defaults to the current time; pin it explicitly
        when the records must be byte-reproducible (demo seed, replay).
        """
        if commit is None:
            commit = current_commit()
        now = recorded_at or datetime.now(UTC)
        records = [
            MappingRecord(
                pair_key=pair.pair_key,
                status=pair.status,
                evidence=pair.evidence,
                commit=commit,
                recorded_at=now,
            )
            for pair in report.pairs
        ]
        existing = self.all()
        existing_keys = {
            (record.pair_key, record.status.value, _evidence_signature(record.evidence))
            for record in existing
        }
        for record in records:
            signature = (record.pair_key, record.status.value, _evidence_signature(record.evidence))
            if signature in existing_keys:
                raise ValueError(
                    f"mapping record {record.pair_key!r} ({record.status.value}) "
                    "already recorded with identical evidence"
                )
        self._append(existing + records)
        return records

    def all(self) -> list[MappingRecord]:
        return self._read()

    def by_pair(self, pair_key_value: str) -> list[MappingRecord]:
        return [record for record in self.all() if record.pair_key == pair_key_value]

    def _append(self, records: list[MappingRecord]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / MAPPINGS_FILE
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{MAPPINGS_FILE}.", suffix=".tmp"
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

    def _read(self) -> list[MappingRecord]:
        if not self.root.exists():
            return []
        if not self.root.is_dir():
            raise ValueError(f"mapping ledger root {self.root} is not a directory")
        path = self.root / MAPPINGS_FILE
        if not path.exists():
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"mapping ledger {path} is unreadable") from error
        records = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = MappingRecord.model_validate_json(line)
            except ValidationError as error:
                raise ValueError(
                    f"mapping ledger {path} line {line_number} is invalid"
                ) from error
            records.append(record)
        return records


def _evidence_signature(evidence: list[MappingEvidence]) -> str:
    return json.dumps(
        [(item.kind.value, item.detail) for item in evidence],
        separators=(",", ":"),
    )


def current_commit() -> str:
    """HEAD of the git repository the ledger runs in; else fail closed."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        raise ValueError("cannot resolve the code commit; pass commit explicitly") from error
    if not head:
        raise ValueError("cannot resolve the code commit; pass commit explicitly")
    return head
