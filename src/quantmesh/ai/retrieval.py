"""Lexical retrieval over local sources (M8, issue #47, Phase C).

Three registered sources (documents, experiment records, audit-log
orders) behind one ``RetrievalSource`` protocol, ranked by a
deterministic IDF-weighted lexical scorer (pure python — embedding
reranking is a documented lazy extension behind the same protocol,
never a required path). Every passage carries a ``Citation`` — a
resolvable identity, never a blob — and ``resolve_citation`` fails
closed on unknown kinds, missing records, and out-of-range spans.
"""

import json
import math
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh._fs import atomic_replace
from quantmesh.ai.errors import CitationResolutionError, RetrievalError
from quantmesh.execution.journal import OrderJournal
from quantmesh.research.experiments import ExperimentRegistry
from quantmesh.settings import settings

__all__ = [
    "AuditSource",
    "Citation",
    "DOCUMENTS_FILE",
    "Document",
    "DocumentIndex",
    "DocumentSource",
    "ExperimentSource",
    "ResolvedSource",
    "RetrievalSource",
    "RetrievedPassage",
    "idf_weights",
    "rank_texts",
    "resolve_citation",
    "tokenize",
]

DOCUMENTS_FILE = "documents.jsonl"

DOCUMENT_KINDS = ("filing", "news", "note")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class Document(BaseModel):
    """One ingested local text record (filing/news/note)."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: Literal["filing", "news", "note"]
    source_path: str = Field(min_length=1)
    ingested_at: datetime
    content: str

    @field_validator("id")
    @classmethod
    def _id_not_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("document id must not be empty")
        return value

    @model_validator(mode="after")
    def _document_is_consistent(self) -> "Document":
        if self.ingested_at.tzinfo is None:
            raise ValueError("ingested_at must be timezone-aware")
        self.ingested_at = self.ingested_at.astimezone(UTC)
        return self


class Citation(BaseModel):
    """A resolvable identity into a source record, never a blob."""

    model_config = ConfigDict(extra="forbid")

    source_kind: Literal["document", "experiment", "audit"]
    source_id: str = Field(min_length=1)
    span: tuple[int, int] | None = Field(
        default=None, description="optional [start, end) char offsets into the record text"
    )

    @field_validator("span")
    @classmethod
    def _span_shape(cls, span: tuple[int, int] | None) -> tuple[int, int] | None:
        if span is not None:
            start, end = span
            if start < 0 or end < 0 or start > end:
                raise ValueError(f"span {span} is not a valid [start, end) range")
        return span


class RetrievedPassage(BaseModel):
    """One search result: a citation plus the ranked record text."""

    model_config = ConfigDict(extra="forbid")

    citation: Citation
    content: str = Field(min_length=1)


@dataclass(frozen=True)
class ResolvedSource:
    """A citation resolved to its source record plus the canonical text
    the span indexes into."""

    source_kind: str
    source_id: str
    record: object
    text: str


# ---------------------------------------------------------------------------
# Lexical ranker (pure, deterministic)
# ---------------------------------------------------------------------------


def tokenize(text: str) -> tuple[str, ...]:
    """Casefold word tokens; deterministic and dependency-free."""
    return tuple(re.findall(r"\w+", text.casefold()))


def idf_weights(texts: list[str]) -> dict[str, float]:
    """Smoothed IDF per token over a corpus: log((1+N)/(1+df)) + 1.

    Always positive, so a query token present anywhere never cancels.
    """
    token_sets = [set(tokenize(text)) for text in texts]
    document_frequency: dict[str, int] = {}
    for tokens in token_sets:
        for token in tokens:
            document_frequency[token] = document_frequency.get(token, 0) + 1
    corpus_size = len(texts)
    return {
        token: math.log((1 + corpus_size) / (1 + frequency)) + 1
        for token, frequency in document_frequency.items()
    }


def rank_texts(query: str, texts: list[str], *, top_k: int) -> list[int]:
    """Indices of texts with query overlap, best first.

    Score = sum of IDF over the query tokens present in the text
    (binary overlap, query tokens deduplicated); texts with no overlap
    are excluded. Ties break by original index, so the ranking is
    byte-deterministic. Zero-token queries and top_k < 1 fail closed.
    """
    if top_k < 1:
        raise RetrievalError(f"top_k must be >= 1, got {top_k}")
    query_tokens = set(tokenize(query))
    if not query_tokens:
        raise RetrievalError("query must contain at least one token")
    weights = idf_weights(texts)
    scored: list[tuple[float, int]] = []
    for index, text in enumerate(texts):
        overlap = query_tokens & set(tokenize(text))
        if not overlap:
            continue
        scored.append((sum(weights[token] for token in overlap), index))
    scored.sort(key=lambda pair: (-pair[0], pair[1]))
    return [index for _, index in scored[:top_k]]


# ---------------------------------------------------------------------------
# Document index (ADR-0006 discipline)
# ---------------------------------------------------------------------------


class DocumentIndex:
    """Append-only manifest of ingested documents under one root."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else settings.documents_dir

    def ingest_file(
        self, path: Path, *, kind: str, doc_id: str, ingested_at: datetime | None = None
    ) -> Document:
        """Ingest a local text file as a ``kind`` record; fail-closed on
        unreadable, non-UTF8, empty files, unknown kinds and duplicate
        ids (the duplicate is refused before the file is read). A
        relative ``path`` is read against (and stored relative to) the
        registry root, so records are portable and byte-reproducible
        across roots; absolute paths are stored as given.
        ``ingested_at`` defaults to the current time; pin it explicitly
        when the record must be byte-reproducible (demo seed, replay)."""
        if kind not in DOCUMENT_KINDS:
            raise RetrievalError(f"unknown document kind {kind!r} (filing|news|note)")
        if not doc_id.strip():
            raise RetrievalError("document id must not be empty")
        existing = self.all()
        if any(record.id == doc_id for record in existing):
            raise RetrievalError(f"document {doc_id!r} already indexed")
        path = Path(path)
        read_path = path if path.is_absolute() else self.root / path
        try:
            text = read_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise RetrievalError(f"cannot ingest {path}: {error}") from error
        if not text.strip():
            raise RetrievalError(f"cannot ingest {path}: the file is empty")
        document = Document(
            id=doc_id,
            kind=kind,
            source_path=str(path),
            ingested_at=ingested_at or datetime.now(UTC),
            content=text,
        )
        self._append(document, existing)
        return document

    def get(self, doc_id: str) -> Document:
        """The record with this id; raises when absent or unreadable."""
        for record in self.all():
            if record.id == doc_id:
                return record
        raise ValueError(f"no document recorded with id {doc_id!r}")

    def all(self) -> list[Document]:
        """Every record, in ingest order."""
        return self._read()

    def _append(self, document: Document, existing: list[Document]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / DOCUMENTS_FILE
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{DOCUMENTS_FILE}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for record in existing + [document]:
                    handle.write(record.model_dump_json())
                    handle.write("\n")
            atomic_replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _read(self) -> list[Document]:
        if not self.root.exists():
            return []
        if not self.root.is_dir():
            raise RetrievalError(f"document index root {self.root} is not a directory")
        path = self.root / DOCUMENTS_FILE
        if not path.exists():
            return []
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise RetrievalError(f"document index {path} is unreadable") from error
        records: list[Document] = []
        seen: dict[str, int] = {}
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = Document.model_validate_json(line)
            except Exception as error:
                raise RetrievalError(
                    f"document index {path} line {line_number} is invalid"
                ) from error
            if record.id in seen:
                raise RetrievalError(
                    f"document index {path} lines {seen[record.id]} and "
                    f"{line_number} share a document id"
                )
            seen[record.id] = line_number
            records.append(record)
        return records


# ---------------------------------------------------------------------------
# Registered sources
# ---------------------------------------------------------------------------


class RetrievalSource(Protocol):
    """Any local corpus searchable by query with resolvable records."""

    kind: str

    def search(self, query: str, top_k: int) -> list[RetrievedPassage]: ...

    def resolve(self, source_id: str) -> ResolvedSource: ...


def _passages(
    texts: list[str], query: str, top_k: int, *, kind: str, ids: list[str]
) -> list[RetrievedPassage]:
    indices = rank_texts(query, texts, top_k=top_k)
    return [
        RetrievedPassage(
            citation=Citation(source_kind=kind, source_id=ids[index]),
            content=texts[index],
        )
        for index in indices
    ]


class DocumentSource:
    """The document index as a retrieval source."""

    kind = "document"

    def __init__(self, index: DocumentIndex) -> None:
        self._index = index

    def search(self, query: str, top_k: int) -> list[RetrievedPassage]:
        records = self._index.all()
        return _passages(
            [record.content for record in records],
            query,
            top_k,
            kind=self.kind,
            ids=[record.id for record in records],
        )

    def resolve(self, source_id: str) -> ResolvedSource:
        for record in self._index.all():
            if record.id == source_id:
                return ResolvedSource(self.kind, source_id, record, record.content)
        raise RetrievalError(f"no document with id {source_id!r}")


class ExperimentSource:
    """The M3 experiment registry as a retrieval source."""

    kind = "experiment"

    def __init__(self, registry: ExperimentRegistry) -> None:
        self._registry = registry

    def search(self, query: str, top_k: int) -> list[RetrievedPassage]:
        records = self._registry.all()
        return _passages(
            [_render(record) for record in records],
            query,
            top_k,
            kind=self.kind,
            ids=[record.id for record in records],
        )

    def resolve(self, source_id: str) -> ResolvedSource:
        try:
            record = self._registry.get(source_id)
        except ValueError as error:
            raise RetrievalError(str(error)) from None
        return ResolvedSource(self.kind, source_id, record, _render(record))


class AuditSource:
    """The order journal (M2 audit surface) as a retrieval source."""

    kind = "audit"

    def __init__(self, journal: OrderJournal) -> None:
        self._journal = journal

    def search(self, query: str, top_k: int) -> list[RetrievedPassage]:
        records = self._journal.all()
        return _passages(
            [_render(record) for record in records],
            query,
            top_k,
            kind=self.kind,
            ids=[record.order_id for record in records],
        )

    def resolve(self, source_id: str) -> ResolvedSource:
        try:
            record = self._journal.get(source_id)
        except ValueError as error:
            raise RetrievalError(str(error)) from None
        return ResolvedSource(self.kind, source_id, record, _render(record))


def _render(record: object) -> str:
    """Canonical text of a non-document record; spans index into this."""
    if isinstance(record, BaseModel):
        return record.model_dump_json()
    return json.dumps(record, sort_keys=True, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Citation resolution (fail-closed)
# ---------------------------------------------------------------------------


def resolve_citation(
    citation: Citation,
    sources: Mapping[str, RetrievalSource],
) -> ResolvedSource:
    """Resolve a citation to its source record.

    Fails closed with ``CitationResolutionError`` when the source kind
    is unknown, the record id is missing, or the span falls outside
    the record's canonical text.
    """
    source = sources.get(citation.source_kind)
    if source is None:
        raise CitationResolutionError(
            f"unknown citation source kind {citation.source_kind!r}"
        )
    try:
        resolved = source.resolve(citation.source_id)
    except RetrievalError as error:
        raise CitationResolutionError(str(error)) from None
    if citation.span is not None:
        start, end = citation.span
        length = len(resolved.text)
        if start < 0 or end > length or start > end:
            raise CitationResolutionError(
                f"citation span {citation.span} out of range for "
                f"{citation.source_kind} {citation.source_id!r} "
                f"(record text has {length} chars)"
            )
    return resolved
