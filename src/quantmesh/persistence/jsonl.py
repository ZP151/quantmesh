"""Shared durable JSONL persistence on the ADR-0006 discipline.

Every registry used to reimplement the same append-only JSONL discipline:
atomic temp+replace appends, fail-closed reads with line attribution,
duplicate identity refusal, hostile-path refusal and schema validation
through the caller's pydantic model. ``JsonlStore`` centralizes that
discipline behind a small interface so a caller no longer reimplements
any of it.

The store is deliberately generic: the caller supplies the record model,
the identity key used for duplicate detection, the human labels used in
refusal messages and the error type those refusals raise. Domain concerns
— a report's lake pin gate, an order journal's replay validation, a
watchlist's venue-aware identity — stay in their owning modules and plug
in through the constructor.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from quantmesh._fs import atomic_replace

Model = TypeVar("Model", bound=BaseModel)


class JsonlStore(Generic[Model]):
    """Append-only JSONL store of pydantic records under one root."""

    def __init__(
        self,
        root: Path,
        *,
        filename: str,
        model: type[Model],
        label: str,
        id_label: str,
        key: Callable[[Model], str] | None = None,
        error_type: type[Exception] = ValueError,
        extra_validate: Callable[[Model], None] | None = None,
        article: str = "a",
        secondary_keys: Sequence[tuple[str, Callable[[Model], str | None]]] = (),
        record_label: str | None = None,
    ) -> None:
        self.root = root
        self.filename = filename
        self.model = model
        self.label = label
        self.id_label = id_label
        self._key = key
        self.error_type = error_type
        self.extra_validate = extra_validate
        self.article = article
        self.secondary_keys = secondary_keys
        self.record_label = record_label if record_label is not None else id_label

    @property
    def path(self) -> Path:
        return self.root / self.filename

    def _error(self, message: str) -> Exception:
        return self.error_type(message)

    def _refuse_symlink(self, candidate: Path) -> None:
        if candidate.is_symlink():
            raise self._error(
                f"symlink in {self.label} layout is not allowed: {candidate}"
            )

    def _refuse_hostile_root(self) -> None:
        self._refuse_symlink(self.root)
        if self.root.exists() and not self.root.is_dir():
            raise self._error(f"{self.label} root {self.root} is not a directory")

    def read(self) -> list[Model]:
        """Fail-closed, line-attributed read with duplicate refusal.

        A missing root or store file is an empty list, never an error. A
        root that is a file, a store path that is a directory, a symlinked
        root or store file, an unreadable file, a schema-invalid line, a
        duplicate identity and a failed ``extra_validate`` are all refused
        with the store's error type and line attribution.
        """
        self._refuse_hostile_root()
        if not self.root.exists():
            return []
        self._refuse_symlink(self.path)
        if not self.path.exists():
            return []
        if not self.path.is_file():
            raise self._error(f"{self.label} path {self.path} is not a file")
        try:
            text = self.path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise self._error(f"{self.label} {self.path} is unreadable") from error
        records: list[Model] = []
        seen: dict[str, int] = {}
        seen_secondary: dict[int, dict[str, int]] = {}
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                record = self.model.model_validate_json(line)
            except ValidationError as error:
                raise self._error(
                    f"{self.label} {self.path} line {line_number} is invalid"
                ) from error
            if self._key is not None:
                key = self._key(record)
                if key in seen:
                    raise self._error(
                        f"{self.label} {self.path} lines {seen[key]} and {line_number} "
                        f"share {self.article} {self.id_label} id"
                    )
                for index, (secondary_label, secondary_key) in enumerate(
                    self.secondary_keys
                ):
                    secondary_value = secondary_key(record)
                    if secondary_value is None:
                        continue
                    bucket = seen_secondary.setdefault(index, {})
                    if secondary_value in bucket:
                        raise self._error(
                            f"{self.label} {self.path} lines {bucket[secondary_value]} and "
                            f"{line_number} share {self.article} {secondary_label}"
                        )
                    bucket[secondary_value] = line_number
                seen[key] = line_number
            if self.extra_validate is not None:
                try:
                    self.extra_validate(record)
                except ValueError as error:
                    raise self._error(
                        f"{self.label} {self.path} line {line_number} has invalid "
                        f"derived state: {error}"
                    ) from error
            records.append(record)
        return records

    def write(self, records: Iterable[Model]) -> None:
        """Atomically replace the store with ``records``.

        One temp file plus ``os.replace`` (through ``atomic_replace``) per
        write; a crash mid-write leaves the previous store intact and the
        temp file is cleaned up in the ``finally`` block.
        """
        self._refuse_hostile_root()
        self.root.mkdir(parents=True, exist_ok=True)
        self._refuse_symlink(self.path)
        if self.path.exists() and not self.path.is_file():
            raise self._error(f"{self.label} path {self.path} is not a file")
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{self.filename}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                for record in records:
                    handle.write(record.model_dump_json())
                    handle.write("\n")
            atomic_replace(temp_name, self.path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def check_absent(self, record: Model, existing: Sequence[Model] | None = None) -> None:
        """Refuse a duplicate identity against ``existing`` (a fresh read if omitted).

        ``append`` uses this internally; a caller that must sequence its own
        domain precondition (e.g. a lake pin gate) after the duplicate refusal
        but before the write can call ``read`` + ``check_absent`` + ``write``
        in that exact order without reimplementing the duplicate check.
        """
        if existing is None:
            existing = self.read()
        key = self._key(record)
        if any(self._key(item) == key for item in existing):
            raise self._error(f"{self.record_label} {key!r} already recorded")

    def append(self, record: Model) -> Model:
        """Refuse a duplicate identity, then append atomically."""
        existing = self.read()
        self.check_absent(record, existing)
        self.write([*existing, record])
        return record

    def update(self, record: Model) -> Model:
        """Replace the snapshot of an existing record sharing ``record``'s key.

        An unknown key is refused before anything is written; the replacement
        is one atomic full rewrite, so an order's growing event history still
        lands as a single temp+replace.
        """
        existing = self.read()
        key = self._key(record)
        if not any(self._key(item) == key for item in existing):
            raise self._error(f"{self.id_label} {key!r} is not recorded")
        updated = [record if self._key(item) == key else item for item in existing]
        self.write(updated)
        return record

    def scan(self) -> list[Path]:
        """Report crash orphans and hostile entries; never delete or modify.

        A crash between temp-file creation and ``os.replace`` can leave a
        ``.filename.*.tmp`` behind, and a symlinked root or store file can
        redirect reads/writes outside the root. Return every offending path
        (empty when clean).
        """
        problems: list[Path] = []
        if self.root.is_symlink():
            problems.append(self.root)
        if self.path.is_symlink():
            problems.append(self.path)
        if self.root.exists() and self.root.is_dir():
            problems.extend(sorted(self.root.glob(f".{self.filename}.*.tmp")))
        return problems
