"""Immutable trusted-data manifests and exact artifact readers."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import stat
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh._fs import atomic_replace
from quantmesh.data.calendars import (
    CONTINUOUS_UTC_VERSION,
    XNYS_REGULAR_VERSION,
    SessionPolicy,
)
from quantmesh.data.capabilities import DataKind, EntitlementState
from quantmesh.data.instruments import CanonicalInstrumentId
from quantmesh.data.layout import validate_dataset_name
from quantmesh.data.objects import (
    FABRIC_NAMESPACE,
    ObjectRef,
    ObjectStore,
    is_reparse_point,
)
from quantmesh.domain.market_data import Bar, interval_to_timedelta
from quantmesh.domain.models import InstrumentType, Venue


class ManifestConflictError(ValueError):
    """A publication lost compare-and-swap or attempted a rollback."""


class ManifestIntegrityError(ValueError):
    """A manifest or pointer no longer matches its immutable identity."""


class ArtifactLayer(StrEnum):
    """Stages in the raw-to-feature trusted-data lineage."""

    RAW = "raw"
    NORMALIZED = "normalized"
    ADJUSTED = "adjusted"
    FEATURE = "feature"


def canonical_json_bytes(value: Any) -> bytes:
    """Encode JSON using the single byte representation used for identities."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _is_utc(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() == timedelta(0)


class _ArtifactManifestBody(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: int = Field(default=2, ge=2, le=2)
    dataset_id: str
    compatibility_revision: int = Field(ge=1, le=2**63 - 1)
    layer: ArtifactLayer
    canonical_instrument: CanonicalInstrumentId
    instrument_catalog_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    data_kind: DataKind
    interval: str | None = None
    calendar_version: str = Field(min_length=1)
    session_policy: SessionPolicy
    objects: tuple[ObjectRef, ...] = Field(min_length=1)
    row_identities: tuple[str, ...] = Field(min_length=1)
    schema_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    adapter_version: str = Field(min_length=1)
    parent_manifest_ids: tuple[str, ...] = ()
    transformation_policy_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_rights_id: str = Field(min_length=1)
    entitlement: EntitlementState
    event_start: datetime
    event_end: datetime
    knowledge_start: datetime
    knowledge_end: datetime
    adjustment_policy: str | None = None
    quality_report_id: str | None = None
    created_at: datetime
    code_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    collection_run_id: str = Field(min_length=1)

    @field_validator(
        "dataset_id",
        "calendar_version",
        "adapter_version",
        "source_rights_id",
        "collection_run_id",
    )
    @classmethod
    def text_is_valid(cls, value: str, info) -> str:
        if not value.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        if info.field_name == "dataset_id":
            validate_dataset_name(value)
        return value

    @field_validator("parent_manifest_ids")
    @classmethod
    def parents_are_content_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("parent_manifest_ids must be unique")
        for value in values:
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError("parent manifest IDs must be lowercase SHA-256 digests")
        return values

    @field_validator("row_identities")
    @classmethod
    def rows_are_unique_and_nonblank(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("row_identities must be unique")
        if any(not value.strip() for value in values):
            raise ValueError("row identities must not be blank")
        return values

    @field_validator("objects")
    @classmethod
    def object_references_are_unique(cls, values: tuple[ObjectRef, ...]) -> tuple[ObjectRef, ...]:
        identities = [(value.algorithm, value.digest) for value in values]
        if len(identities) != len(set(identities)):
            raise ValueError("object references must be unique")
        return values

    @field_validator("adjustment_policy", "quality_report_id")
    @classmethod
    def optional_metadata_is_valid(cls, value: str | None, info) -> str | None:
        if value is not None and not value.strip():
            raise ValueError(f"{info.field_name} must not be blank")
        if info.field_name == "quality_report_id" and value is not None:
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError("quality_report_id must be a lowercase SHA-256 digest")
        return value

    @field_validator("event_start", "event_end", "knowledge_start", "knowledge_end", "created_at")
    @classmethod
    def timestamps_are_utc(cls, value: datetime, info) -> datetime:
        if not _is_utc(value):
            raise ValueError(f"{info.field_name} must be UTC")
        return value

    @model_validator(mode="after")
    def lineage_shape_is_consistent(self) -> _ArtifactManifestBody:
        if self.event_start > self.event_end:
            raise ValueError("event_start must not be after event_end")
        if self.knowledge_start > self.knowledge_end:
            raise ValueError("knowledge_start must not be after knowledge_end")
        if self.created_at < self.knowledge_end:
            raise ValueError("created_at must not be before knowledge_end")
        if self.data_kind is DataKind.BARS:
            if self.interval is None:
                raise ValueError("bar artifacts require interval")
            interval_to_timedelta(self.interval)
        elif self.interval is not None:
            raise ValueError("only bar artifacts declare interval")
        if self.canonical_instrument.value.startswith("moomoo:"):
            expected_calendar = (XNYS_REGULAR_VERSION, SessionPolicy.REGULAR)
        else:
            expected_calendar = (CONTINUOUS_UTC_VERSION, SessionPolicy.CONTINUOUS)
        if (self.calendar_version, self.session_policy) != expected_calendar:
            raise ValueError("calendar and session policy disagree with canonical instrument")
        return self


class ArtifactManifest(_ArtifactManifestBody):
    """A self-addressed declaration of exact objects and lineage metadata."""

    manifest_id: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def build(cls, **values: Any) -> ArtifactManifest:
        """Validate a body and derive its identity from canonical body bytes."""
        body = _ArtifactManifestBody.model_validate(values)
        body_bytes = canonical_json_bytes(body.model_dump(mode="json"))
        return cls(
            **body.model_dump(),
            manifest_id=hashlib.sha256(body_bytes).hexdigest(),
        )

    @model_validator(mode="after")
    def manifest_id_matches_body(self) -> ArtifactManifest:
        body = self.model_dump(mode="json", exclude={"manifest_id"})
        actual = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
        if self.manifest_id != actual:
            raise ValueError(
                f"manifest_id mismatch: expected {self.manifest_id}, observed {actual}"
            )
        return self

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


class ArtifactDataset:
    """A reader permanently bound to one immutable manifest."""

    def __init__(
        self,
        manifest: ArtifactManifest,
        objects: ObjectStore,
        manifest_store: ManifestStore | None = None,
    ) -> None:
        self.manifest = manifest
        self.objects = objects
        self.manifest_store = manifest_store

    def read_bytes(self) -> bytes:
        return b"".join(self.objects.get_bytes(reference) for reference in self.manifest.objects)

    def read_bars(self, *, known_at: datetime | None = None) -> list[Bar]:
        if known_at is not None:
            if self.manifest_store is None:
                raise ValueError("knowledge-time reads require a manifest store")
            return self.manifest_store.open_known_at(
                self.manifest.manifest_id, known_at=known_at
            ).read_bars()
        if self.manifest.data_kind is not DataKind.BARS:
            raise ValueError("artifact does not contain bars")
        bars: list[Bar] = []
        for reference in self.manifest.objects:
            if reference.media_type != "application/vnd.quantmesh.bars+json":
                raise ManifestIntegrityError(
                    f"bar artifact has unsupported media type {reference.media_type!r}"
                )
            try:
                rows = json.loads(self.objects.get_bytes(reference))
                if not isinstance(rows, list):
                    raise TypeError("bar object must be a JSON list")
                bars.extend(Bar.model_validate(row) for row in rows)
            except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError) as error:
                raise ManifestIntegrityError(
                    "bar object is not valid canonical bar data"
                ) from error
        self._validate_bar_declarations(bars)
        return bars

    def read_features(self) -> list[dict[str, Any]]:
        if self.manifest.layer is not ArtifactLayer.FEATURE:
            raise ValueError("artifact is not a feature layer")
        rows: list[dict[str, Any]] = []
        for reference in self.manifest.objects:
            if reference.media_type != "application/vnd.quantmesh.features+json":
                raise ManifestIntegrityError(
                    f"feature artifact has unsupported media type {reference.media_type!r}"
                )
            try:
                decoded = json.loads(self.objects.get_bytes(reference))
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise ManifestIntegrityError("feature object is invalid JSON") from error
            if not isinstance(decoded, list):
                raise ManifestIntegrityError("feature object must be a JSON list")
            for item in decoded:
                required = {"name", "timestamp", "value", "window"}
                if not isinstance(item, dict) or set(item) != required:
                    raise ManifestIntegrityError("feature row has an invalid shape")
                if item["name"] != "log_return" or item["window"] != 2:
                    raise ManifestIntegrityError("feature row is outside the tracer contract")
                if (
                    isinstance(item["value"], bool)
                    or not isinstance(item["value"], (int, float))
                    or not math.isfinite(item["value"])
                ):
                    raise ManifestIntegrityError("feature value must be finite")
                try:
                    timestamp = datetime.fromisoformat(item["timestamp"])
                except (TypeError, ValueError) as error:
                    raise ManifestIntegrityError("feature timestamp is invalid") from error
                if not _is_utc(timestamp):
                    raise ManifestIntegrityError("feature timestamp must be UTC")
                rows.append(item)
        identities = tuple(f"log_return:{item['timestamp']}" for item in rows)
        if identities != self.manifest.row_identities:
            raise ManifestIntegrityError("feature rows disagree with manifest row identities")
        timestamps = [datetime.fromisoformat(item["timestamp"]) for item in rows]
        if not timestamps:
            raise ManifestIntegrityError("feature artifact must contain at least one row")
        if (
            min(timestamps) != self.manifest.event_start
            or max(timestamps) != self.manifest.event_end
        ):
            raise ManifestIntegrityError("feature timestamps disagree with manifest event coverage")
        return rows

    def _validate_bar_declarations(self, bars: list[Bar]) -> None:
        canonical = self.manifest.canonical_instrument.value
        if canonical.startswith("moomoo:"):
            expected = (canonical.split(":")[2], Venue.MOOMOO, InstrumentType.EQUITY, "USD")
        else:
            expected = (
                canonical.split(":")[2],
                Venue.HYPERLIQUID,
                InstrumentType.PERPETUAL,
                "USD",
            )
        for bar in bars:
            observed = (
                bar.instrument.symbol,
                bar.instrument.venue,
                bar.instrument.instrument_type,
                bar.instrument.currency,
            )
            if observed != expected:
                raise ManifestIntegrityError(
                    "bar instrument disagrees with manifest canonical instrument"
                )
            if bar.interval != self.manifest.interval:
                raise ManifestIntegrityError("bar interval disagrees with manifest interval")
        timestamps = [bar.timestamp.astimezone(UTC) for bar in bars]
        if not timestamps:
            raise ManifestIntegrityError("bar artifact must contain at least one row")
        if (
            min(timestamps) != self.manifest.event_start
            or max(timestamps) != self.manifest.event_end
        ):
            raise ManifestIntegrityError("bar timestamps disagree with manifest event coverage")
        identities = tuple(
            f"{bar.instrument.symbol}:{bar.timestamp.astimezone(UTC).isoformat()}" for bar in bars
        )
        if identities != self.manifest.row_identities:
            raise ManifestIntegrityError("bar rows disagree with manifest row identities")


@contextmanager
def _exclusive_lock(path: Path, *, allowed_root: Path) -> Iterator[None]:
    """Hold a one-byte cross-process lock for pointer compare-and-swap."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.resolve().relative_to(allowed_root.resolve())
    except ValueError as error:
        raise ManifestIntegrityError(f"lock path escapes store root: {path}") from error
    if is_reparse_point(path):
        raise ManifestIntegrityError(f"lock path is a symlink or reparse point: {path}")
    with path.open("a+b") as handle:
        opened = os.fstat(handle.fileno())
        occupant = path.lstat()
        if not stat.S_ISREG(occupant.st_mode):
            raise ManifestIntegrityError(f"lock path is not a regular file: {path}")
        if opened.st_dev != occupant.st_dev or opened.st_ino != occupant.st_ino:
            raise ManifestIntegrityError(f"lock path changed while opening: {path}")
        if opened.st_nlink != 1:
            raise ManifestIntegrityError(f"lock path has multiple hard links: {path}")
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


class ManifestStore:
    """Publish immutable manifests and atomically advance dataset pointers."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.objects = ObjectStore(self.root)

    def manifest_path(self, dataset_id: str, manifest_id: str) -> Path:
        validate_dataset_name(dataset_id)
        self._validate_manifest_id(manifest_id)
        path = (
            self.root
            / FABRIC_NAMESPACE
            / "datasets"
            / dataset_id
            / "manifests"
            / f"{manifest_id}.json"
        )
        self._reject_symlink_components(path)
        return path

    def publish(
        self,
        manifest: ArtifactManifest,
        *,
        expected_current: str | None,
    ) -> None:
        """Publish immutable bytes, then CAS the mutable current pointer."""
        for reference in manifest.objects:
            self.objects.get_bytes(reference)
        self._validate_typed_dataset(ArtifactDataset(manifest, self.objects))
        pointer = self._pointer_path(manifest.dataset_id)
        with _exclusive_lock(self._lock_path(manifest.dataset_id), allowed_root=self.root):
            self._repair_history_tail(manifest, expected_current=expected_current)
            current = self._read_pointer(manifest.dataset_id)
            if current is None:
                if pointer.parent.exists():
                    raise ManifestConflictError(
                        "current pointer deletion reset is forbidden; explicit recovery is required"
                    )
                self._require_expected(current, expected_current)
                if manifest.compatibility_revision != 1:
                    raise ManifestConflictError(
                        "the atomic genesis manifest must use compatibility revision 1"
                    )
                self._publish_genesis(manifest)
                return
            if current["manifest_id"] == manifest.manifest_id:
                return
            self._require_expected(current, expected_current)
            current_manifest = self.open(current["manifest_id"]).manifest
            self._require_forward_knowledge(current_manifest, manifest)
            pending = current.get("_pending_history")
            if pending is not None:
                if manifest.manifest_id != pending["manifest_id"]:
                    raise ManifestConflictError(
                        "compatibility revision already belongs to a pending manifest"
                    )
                if manifest.compatibility_revision != pending["compatibility_revision"]:
                    raise ManifestConflictError("pending manifest compatibility revision disagrees")
                self._write_revision_reservation(manifest)
                self._write_immutable_manifest(manifest)
                self._write_pointer(manifest)
                return
            expected_revision = current["compatibility_revision"] + 1
            if manifest.compatibility_revision != expected_revision:
                raise ManifestConflictError(
                    "compatibility revision must advance exactly once: "
                    f"expected {expected_revision}, got {manifest.compatibility_revision}"
                )
            self._append_history(manifest)
            self._write_revision_reservation(manifest)
            self._write_immutable_manifest(manifest)
            self._write_pointer(manifest)

    def point_current(self, manifest_id: str, *, expected_current: str | None) -> None:
        """Advance a pointer to an already-published manifest; never roll back."""
        target = self.open(manifest_id).manifest
        with _exclusive_lock(self._lock_path(target.dataset_id), allowed_root=self.root):
            self._repair_history_tail(target, expected_current=expected_current)
            current = self._read_pointer(target.dataset_id)
            if current is None:
                raise ManifestConflictError(
                    "current pointer deletion reset is forbidden; explicit recovery is required"
                )
            if current["manifest_id"] == target.manifest_id:
                return
            self._require_expected(current, expected_current)
            pending = current.get("_pending_history")
            if pending is not None:
                if target.manifest_id != pending["manifest_id"]:
                    raise ManifestConflictError(
                        "only the pending manifest may complete pointer recovery"
                    )
                current_manifest = self.open(current["manifest_id"]).manifest
                self._require_forward_knowledge(current_manifest, target)
                self._write_revision_reservation(target)
                self._write_pointer(target)
                return
            if target.compatibility_revision <= current["compatibility_revision"]:
                raise ManifestConflictError(
                    "manifest pointer rollback is forbidden: "
                    f"current revision {current['compatibility_revision']}, "
                    f"target revision {target.compatibility_revision}"
                )
            current_manifest = self.open(current["manifest_id"]).manifest
            self._require_forward_knowledge(current_manifest, target)
            expected_revision = current["compatibility_revision"] + 1
            if target.compatibility_revision != expected_revision:
                raise ManifestConflictError(
                    "compatibility revision must advance exactly once: "
                    f"expected {expected_revision}, got {target.compatibility_revision}"
                )
            self._write_pointer(target)

    def open(self, manifest_id: str) -> ArtifactDataset:
        """Open the one canonical manifest with this ID, independent of current."""
        self._validate_manifest_id(manifest_id)
        base = self.root / FABRIC_NAMESPACE / "datasets"
        matches: list[Path] = []
        if base.exists():
            if is_reparse_point(base):
                raise ManifestIntegrityError(f"dataset root is a symlink or reparse point: {base}")
            for dataset_dir in base.iterdir():
                if is_reparse_point(dataset_dir):
                    raise ManifestIntegrityError(
                        f"dataset path is a symlink or reparse point: {dataset_dir}"
                    )
                manifest_dir = dataset_dir / "manifests"
                if is_reparse_point(manifest_dir):
                    raise ManifestIntegrityError(
                        f"manifest directory is a symlink or reparse point: {manifest_dir}"
                    )
                candidate = manifest_dir / f"{manifest_id}.json"
                if candidate.exists():
                    matches.append(candidate)
        if len(matches) != 1:
            qualifier = "missing" if not matches else "ambiguous"
            raise ManifestIntegrityError(f"manifest {manifest_id} is {qualifier}")
        manifest = self._read_manifest_file(matches[0], manifest_id)
        for reference in manifest.objects:
            self.objects.get_bytes(reference)
        dataset = ArtifactDataset(manifest, self.objects, self)
        self._validate_typed_dataset(dataset)
        return dataset

    def current(self, dataset_id: str) -> ArtifactDataset | None:
        """Open the validated current revision for a dataset, if initialized."""
        validate_dataset_name(dataset_id)
        if not self._pointer_path(dataset_id).exists():
            return None
        pointer = self._read_pointer(dataset_id)
        if pointer is None:
            return None
        return self.open(pointer["manifest_id"])

    def manifests(self, dataset_id: str) -> tuple[ArtifactManifest, ...]:
        """Return all committed revisions in immutable history order."""
        validate_dataset_name(dataset_id)
        if not self._pointer_path(dataset_id).exists():
            return ()
        pointer = self._read_pointer(dataset_id)
        if pointer is None:
            return ()
        records = self._read_history(dataset_id)
        committed = records[: pointer["compatibility_revision"]]
        return tuple(self.open(record["manifest_id"]).manifest for record in committed)

    def open_known_at(self, manifest_id: str, *, known_at: datetime) -> ArtifactDataset:
        """Open the latest committed revision visible at one UTC knowledge time."""
        if not _is_utc(known_at):
            raise ValueError("known_at must be UTC")
        base = self.open(manifest_id).manifest
        visible = [
            item for item in self.manifests(base.dataset_id) if item.knowledge_end <= known_at
        ]
        if not visible:
            raise ValueError(
                f"no artifact was known for {base.dataset_id!r} at {known_at.isoformat()}"
            )
        selected = max(
            visible,
            key=lambda item: (
                item.knowledge_end,
                item.knowledge_start,
                item.compatibility_revision,
            ),
        )
        return self.open(selected.manifest_id)

    def _read_manifest_file(self, path: Path, manifest_id: str) -> ArtifactManifest:
        if is_reparse_point(path):
            raise ManifestIntegrityError(f"manifest path is a symlink or reparse point: {path}")
        payload = path.read_bytes()
        try:
            manifest = ArtifactManifest.model_validate_json(payload)
        except ValueError as error:
            raise ManifestIntegrityError(f"manifest {manifest_id} is invalid") from error
        if manifest.manifest_id != manifest_id or path.parent.parent.name != manifest.dataset_id:
            raise ManifestIntegrityError("manifest identity and path disagree")
        if payload != manifest.canonical_bytes():
            raise ManifestIntegrityError("manifest is not stored as canonical bytes")
        return manifest

    @staticmethod
    def _validate_typed_dataset(dataset: ArtifactDataset) -> None:
        manifest = dataset.manifest
        if manifest.layer is ArtifactLayer.FEATURE:
            dataset.read_features()
        elif manifest.layer is not ArtifactLayer.RAW and manifest.data_kind is DataKind.BARS:
            dataset.read_bars()

    @staticmethod
    def _require_forward_knowledge(current: ArtifactManifest, target: ArtifactManifest) -> None:
        if target.knowledge_start <= current.knowledge_end:
            raise ManifestConflictError(
                "knowledge time must advance beyond the current revision: "
                f"current ends {current.knowledge_end.isoformat()}, "
                f"target starts {target.knowledge_start.isoformat()}"
            )

    def _write_immutable_manifest(self, manifest: ArtifactManifest) -> None:
        path = self.manifest_path(manifest.dataset_id, manifest.manifest_id)
        payload = manifest.canonical_bytes()
        path.parent.mkdir(parents=True, exist_ok=True)
        if is_reparse_point(path):
            raise ManifestIntegrityError(f"manifest path is a symlink or reparse point: {path}")
        if path.exists():
            if path.read_bytes() != payload:
                raise ManifestIntegrityError("immutable manifest contains conflicting bytes")
            return
        descriptor, temp_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{manifest.manifest_id}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp_name, path)
            except FileExistsError:
                if path.read_bytes() != payload:
                    raise ManifestIntegrityError("immutable manifest contains conflicting bytes")
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _pointer_path(self, dataset_id: str) -> Path:
        validate_dataset_name(dataset_id)
        path = self.root / FABRIC_NAMESPACE / "datasets" / dataset_id / "current.json"
        self._reject_symlink_components(path)
        return path

    def _lock_path(self, dataset_id: str) -> Path:
        validate_dataset_name(dataset_id)
        path = self.root / FABRIC_NAMESPACE / "locks" / "datasets" / f"{dataset_id}.lock"
        self._reject_symlink_components(path)
        return path

    def _publish_genesis(self, manifest: ArtifactManifest) -> None:
        """Atomically make one fully initialized dataset directory visible."""
        datasets = self.root / FABRIC_NAMESPACE / "datasets"
        staging_root = self.root / FABRIC_NAMESPACE / ".staging" / "datasets"
        target = datasets / manifest.dataset_id
        for directory in (datasets, staging_root):
            self._reject_symlink_components(directory)
            directory.mkdir(parents=True, exist_ok=True)
            self._reject_symlink_components(directory)
        staged = Path(
            tempfile.mkdtemp(
                dir=staging_root,
                prefix=f".{manifest.dataset_id}.",
            )
        )
        marker = canonical_json_bytes(
            {
                "dataset_id": manifest.dataset_id,
                "manifest_id": manifest.manifest_id,
            }
        )
        pointer = canonical_json_bytes(
            {
                "dataset_id": manifest.dataset_id,
                "manifest_id": manifest.manifest_id,
                "compatibility_revision": manifest.compatibility_revision,
            }
        )
        try:
            manifest_directory = staged / "manifests"
            revision_directory = staged / "revisions"
            manifest_directory.mkdir()
            revision_directory.mkdir()
            self._write_staged_file(
                manifest_directory / f"{manifest.manifest_id}.json",
                manifest.canonical_bytes(),
            )
            self._write_staged_file(
                revision_directory / f"{manifest.compatibility_revision:020d}.json",
                self._revision_reservation_bytes(manifest),
            )
            self._write_staged_file(staged / "current.json", pointer)
            self._write_staged_file(staged / "genesis.json", marker)
            self._write_staged_file(staged / "initialized.json", marker)
            self._write_staged_file(
                staged / "history.jsonl",
                self._history_record_bytes(manifest, previous_digest=None) + b"\n",
            )
            self._activate_genesis(staged, target)
        finally:
            if staged.exists():
                shutil.rmtree(staged)

    @staticmethod
    def _write_staged_file(path: Path, payload: bytes) -> None:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

    @staticmethod
    def _activate_genesis(staged: Path, target: Path) -> None:
        try:
            os.rename(staged, target)
        except FileExistsError as error:
            raise ManifestConflictError(
                f"dataset {target.name!r} was initialized concurrently"
            ) from error

    @staticmethod
    def _revision_reservation_bytes(manifest: ArtifactManifest) -> bytes:
        return canonical_json_bytes(
            {
                "compatibility_revision": manifest.compatibility_revision,
                "dataset_id": manifest.dataset_id,
                "manifest_id": manifest.manifest_id,
            }
        )

    @staticmethod
    def _history_record_bytes(manifest: ArtifactManifest, *, previous_digest: str | None) -> bytes:
        body = {
            "compatibility_revision": manifest.compatibility_revision,
            "dataset_id": manifest.dataset_id,
            "manifest_id": manifest.manifest_id,
            "previous_digest": previous_digest,
        }
        history_digest = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
        return canonical_json_bytes({**body, "history_digest": history_digest})

    def _append_history(self, manifest: ArtifactManifest) -> None:
        records = self._read_history(manifest.dataset_id)
        revision = manifest.compatibility_revision
        if revision <= len(records):
            if records[revision - 1]["manifest_id"] != manifest.manifest_id:
                raise ManifestConflictError(
                    "compatibility revision is already bound in immutable history"
                )
            return
        if revision != len(records) + 1:
            raise ManifestConflictError(
                f"history revision must advance from {len(records)} to {len(records) + 1}"
            )
        path = self._history_path(manifest.dataset_id)
        payload = self._history_record_bytes(
            manifest,
            previous_digest=records[-1]["history_digest"],
        )
        with path.open("ab") as handle:
            handle.write(payload + b"\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _write_revision_reservation(self, manifest: ArtifactManifest) -> None:
        directory = self.root / FABRIC_NAMESPACE / "datasets" / manifest.dataset_id / "revisions"
        self._reject_symlink_components(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{manifest.compatibility_revision:020d}.json"
        self._reject_symlink_components(path)
        payload = self._revision_reservation_bytes(manifest)
        if path.exists():
            if path.read_bytes() != payload:
                raise ManifestConflictError(
                    "compatibility revision is already reserved for another manifest"
                )
            return
        descriptor, temp_name = tempfile.mkstemp(
            dir=directory,
            prefix=f".{manifest.compatibility_revision:020d}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp_name, path)
            except FileExistsError:
                if path.read_bytes() != payload:
                    raise ManifestConflictError(
                        "compatibility revision is already reserved for another manifest"
                    )
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _initialization_marker_path(self, dataset_id: str, name: str) -> Path:
        validate_dataset_name(dataset_id)
        if name not in {"genesis", "initialized"}:
            raise ValueError(f"unknown initialization marker {name!r}")
        path = self.root / FABRIC_NAMESPACE / "datasets" / dataset_id / f"{name}.json"
        self._reject_symlink_components(path)
        return path

    def _read_initialization_marker(self, dataset_id: str, name: str) -> dict[str, str] | None:
        path = self._initialization_marker_path(dataset_id, name)
        if not path.exists():
            return None
        payload = path.read_bytes()
        try:
            value = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ManifestIntegrityError(f"{name} marker is invalid JSON") from error
        if not isinstance(value, dict) or set(value) != {"dataset_id", "manifest_id"}:
            raise ManifestIntegrityError(f"{name} marker has an invalid shape")
        if value["dataset_id"] != dataset_id:
            raise ManifestIntegrityError(f"{name} marker dataset identity disagrees")
        try:
            self._validate_manifest_id(value["manifest_id"])
        except ValueError as error:
            raise ManifestIntegrityError(f"{name} marker manifest ID is invalid") from error
        if payload != canonical_json_bytes(value):
            raise ManifestIntegrityError(f"{name} marker is not stored as canonical bytes")
        return value

    def _history_path(self, dataset_id: str) -> Path:
        validate_dataset_name(dataset_id)
        path = self.root / FABRIC_NAMESPACE / "datasets" / dataset_id / "history.jsonl"
        self._reject_symlink_components(path)
        return path

    def _read_history(self, dataset_id: str) -> list[dict[str, Any]]:
        path = self._history_path(dataset_id)
        if not path.is_file() or is_reparse_point(path):
            raise ManifestIntegrityError("initialized dataset has no valid history log")
        return self._parse_history_payload(dataset_id, path.read_bytes())

    def _parse_history_payload(self, dataset_id: str, payload: bytes) -> list[dict[str, Any]]:
        if not payload or not payload.endswith(b"\n"):
            raise ManifestIntegrityError("history log is empty or has an incomplete tail")
        records: list[dict[str, Any]] = []
        previous_digest: str | None = None
        for expected, line in enumerate(payload.splitlines(), start=1):
            try:
                item = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise ManifestIntegrityError(
                    f"history record {expected} is invalid JSON"
                ) from error
            required = {
                "compatibility_revision",
                "dataset_id",
                "history_digest",
                "manifest_id",
                "previous_digest",
            }
            if not isinstance(item, dict) or set(item) != required:
                raise ManifestIntegrityError(f"history record {expected} has an invalid shape")
            if item["compatibility_revision"] != expected:
                raise ManifestIntegrityError("history revision sequence has a gap")
            if item["dataset_id"] != dataset_id:
                raise ManifestIntegrityError("history dataset identity disagrees")
            if item["previous_digest"] != previous_digest:
                raise ManifestIntegrityError("history hash chain is broken")
            try:
                self._validate_manifest_id(item["manifest_id"])
                self._validate_manifest_id(item["history_digest"])
            except ValueError as error:
                raise ManifestIntegrityError("history digest is invalid") from error
            body = {key: value for key, value in item.items() if key != "history_digest"}
            actual = hashlib.sha256(canonical_json_bytes(body)).hexdigest()
            if item["history_digest"] != actual:
                raise ManifestIntegrityError("history record digest mismatch")
            if line != canonical_json_bytes(item):
                raise ManifestIntegrityError("history record is not canonical JSON")
            records.append(item)
            previous_digest = item["history_digest"]
        return records

    def _repair_history_tail(
        self, manifest: ArtifactManifest, *, expected_current: str | None
    ) -> None:
        path = self._history_path(manifest.dataset_id)
        if not path.exists():
            return
        if is_reparse_point(path):
            raise ManifestIntegrityError("history log is a symlink or reparse point")
        payload = path.read_bytes()
        if payload.endswith(b"\n"):
            return
        boundary = payload.rfind(b"\n")
        if boundary < 0:
            raise ManifestIntegrityError("history log has no committed record")
        complete = payload[: boundary + 1]
        incomplete = payload[boundary + 1 :]
        records = self._parse_history_payload(manifest.dataset_id, complete)
        pointer_path = self._pointer_path(manifest.dataset_id)
        try:
            pointer_payload = pointer_path.read_bytes()
            pointer = json.loads(pointer_payload)
        except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ManifestIntegrityError(
                "torn history tail has no valid current pointer"
            ) from error
        required = {"compatibility_revision", "dataset_id", "manifest_id"}
        if not isinstance(pointer, dict) or set(pointer) != required:
            raise ManifestIntegrityError("torn history recovery pointer has an invalid shape")
        if pointer["dataset_id"] != manifest.dataset_id:
            raise ManifestIntegrityError("torn history recovery dataset identity disagrees")
        if type(pointer["compatibility_revision"]) is not int:
            raise ManifestIntegrityError("torn history recovery revision is invalid")
        try:
            self._validate_manifest_id(pointer["manifest_id"])
        except ValueError as error:
            raise ManifestIntegrityError(
                "torn history recovery pointer manifest ID is invalid"
            ) from error
        if pointer_payload != canonical_json_bytes(pointer):
            raise ManifestIntegrityError("torn history recovery pointer is not canonical JSON")
        if pointer["manifest_id"] != expected_current:
            raise ManifestConflictError(
                "torn history recovery expected current does not match the pointer"
            )
        if pointer["compatibility_revision"] != len(records):
            raise ManifestIntegrityError("torn history overlaps a committed pointer revision")
        if manifest.compatibility_revision != len(records) + 1:
            raise ManifestIntegrityError(
                "only the exact next revision can repair a torn history tail"
            )
        reservations = self._read_revision_reservations(manifest.dataset_id)
        if len(reservations) not in {len(records), len(records) + 1}:
            raise ManifestIntegrityError(
                "torn history recovery disagrees with revision reservations"
            )
        independently_bound = False
        if (
            len(reservations) == len(records) + 1
            and reservations[-1]["manifest_id"] != manifest.manifest_id
        ):
            raise ManifestIntegrityError(
                "torn history recovery manifest disagrees with its reservation"
            )
        if len(reservations) == len(records) + 1:
            independently_bound = True
        for manifest_path in self._published_manifests(manifest.dataset_id):
            item = self._read_manifest_file(manifest_path, manifest_path.stem)
            if (
                item.compatibility_revision == manifest.compatibility_revision
                and item.manifest_id != manifest.manifest_id
            ):
                raise ManifestIntegrityError(
                    "torn history recovery manifest disagrees with published evidence"
                )
            if (
                item.compatibility_revision == manifest.compatibility_revision
                and item.manifest_id == manifest.manifest_id
            ):
                independently_bound = True
        candidate = self._history_record_bytes(
            manifest,
            previous_digest=records[-1]["history_digest"],
        )
        if incomplete != candidate[: len(incomplete)]:
            raise ManifestIntegrityError(
                "torn history tail does not belong to the retrying manifest"
            )
        if not independently_bound and manifest.manifest_id.encode("ascii") not in incomplete:
            raise ManifestIntegrityError(
                "torn history tail lacks an authenticated manifest identity"
            )
        repaired = complete + candidate + b"\n"
        descriptor, temp_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=".history-repair.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(repaired)
                handle.flush()
                os.fsync(handle.fileno())
            atomic_replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def _read_pointer(self, dataset_id: str) -> dict[str, Any] | None:
        path = self._pointer_path(dataset_id)
        if not path.exists():
            return None
        if is_reparse_point(path):
            raise ManifestIntegrityError(f"current pointer is a symlink or reparse point: {path}")
        payload = path.read_bytes()
        try:
            value = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ManifestIntegrityError("current pointer is invalid JSON") from error
        required = {"dataset_id", "manifest_id", "compatibility_revision"}
        if not isinstance(value, dict) or set(value) != required:
            raise ManifestIntegrityError("current pointer has an invalid shape")
        if value["dataset_id"] != dataset_id:
            raise ManifestIntegrityError("current pointer dataset identity disagrees")
        try:
            self._validate_manifest_id(value["manifest_id"])
        except ValueError as error:
            raise ManifestIntegrityError("current pointer manifest ID is invalid") from error
        if type(value["compatibility_revision"]) is not int or value["compatibility_revision"] < 1:
            raise ManifestIntegrityError("current pointer revision is invalid")
        if payload != canonical_json_bytes(value):
            raise ManifestIntegrityError("current pointer is not stored as canonical bytes")
        genesis = self._read_initialization_marker(dataset_id, "genesis")
        initialized = self._read_initialization_marker(dataset_id, "initialized")
        if genesis is None or initialized is None:
            raise ManifestIntegrityError(
                "atomically initialized dataset is missing an initialization marker"
            )
        if initialized != genesis:
            raise ManifestIntegrityError("initialized marker disagrees with the genesis marker")
        manifest = self.open(value["manifest_id"]).manifest
        if (
            manifest.dataset_id != dataset_id
            or manifest.compatibility_revision != value["compatibility_revision"]
        ):
            raise ManifestIntegrityError("current pointer does not match its manifest")
        history = self._read_history(dataset_id)
        reservations = self._read_revision_reservations(dataset_id)
        if genesis["manifest_id"] != history[0]["manifest_id"]:
            raise ManifestIntegrityError(
                "genesis marker does not identify compatibility revision 1"
            )
        pointer_revision = value["compatibility_revision"]
        if pointer_revision not in {len(history), len(history) - 1}:
            raise ManifestIntegrityError(
                "current pointer does not identify the history head or its predecessor"
            )
        if value["manifest_id"] != history[pointer_revision - 1]["manifest_id"]:
            raise ManifestIntegrityError("current pointer disagrees with the hash-chained history")
        if len(reservations) not in {len(history), len(history) - 1}:
            raise ManifestIntegrityError(
                "revision reservations do not follow the history high-water mark"
            )
        if len(reservations) < pointer_revision:
            raise ManifestIntegrityError("current revision has no immutable reservation")
        for reservation, record in zip(reservations, history):
            if reservation["manifest_id"] != record["manifest_id"]:
                raise ManifestIntegrityError(
                    "revision reservation disagrees with hash-chained history"
                )
        published: dict[int, ArtifactManifest] = {}
        for manifest_path in self._published_manifests(dataset_id):
            try:
                self._validate_manifest_id(manifest_path.stem)
                item = self._read_manifest_file(manifest_path, manifest_path.stem)
            except (ManifestIntegrityError, ValueError) as error:
                raise ManifestIntegrityError(
                    f"published manifest is invalid: {manifest_path.name}"
                ) from error
            if item.compatibility_revision in published:
                raise ManifestIntegrityError(
                    f"compatibility revision {item.compatibility_revision} is reused"
                )
            published[item.compatibility_revision] = item
        reserved_revisions = {reservation["compatibility_revision"] for reservation in reservations}
        for record in history:
            revision = record["compatibility_revision"]
            item = published.get(revision)
            if item is None:
                if revision <= pointer_revision:
                    raise ManifestIntegrityError(
                        f"reserved manifest for revision {revision} is missing"
                    )
                continue
            if item.manifest_id != record["manifest_id"]:
                raise ManifestIntegrityError(
                    f"manifest for revision {revision} disagrees with history"
                )
            if revision not in reserved_revisions:
                raise ManifestIntegrityError(f"manifest for revision {revision} has no reservation")
        if set(published) - reserved_revisions:
            raise ManifestIntegrityError("published manifest exists without a revision reservation")
        if len(history) == pointer_revision + 1:
            value["_pending_history"] = history[-1]
        return value

    def _read_revision_reservations(self, dataset_id: str) -> list[dict[str, Any]]:
        directory = self.root / FABRIC_NAMESPACE / "datasets" / dataset_id / "revisions"
        self._reject_symlink_components(directory)
        if not directory.is_dir():
            raise ManifestIntegrityError("initialized dataset has no revision reservations")
        reservations: list[dict[str, Any]] = []
        for expected, path in enumerate(sorted(directory.glob("*.json")), start=1):
            if is_reparse_point(path):
                raise ManifestIntegrityError(
                    f"revision reservation is a symlink or reparse point: {path}"
                )
            payload = path.read_bytes()
            try:
                item = json.loads(payload)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise ManifestIntegrityError(
                    f"revision reservation is invalid JSON: {path.name}"
                ) from error
            required = {"compatibility_revision", "dataset_id", "manifest_id"}
            if not isinstance(item, dict) or set(item) != required:
                raise ManifestIntegrityError(
                    f"revision reservation has an invalid shape: {path.name}"
                )
            revision = item["compatibility_revision"]
            if type(revision) is not int or not (1 <= revision <= 2**63 - 1):
                raise ManifestIntegrityError(
                    f"revision reservation has an invalid revision: {path.name}"
                )
            if revision != expected or path.name != f"{revision:020d}.json":
                raise ManifestIntegrityError("revision reservation history has a gap")
            if item["dataset_id"] != dataset_id:
                raise ManifestIntegrityError("revision reservation dataset identity disagrees")
            try:
                self._validate_manifest_id(item["manifest_id"])
            except ValueError as error:
                raise ManifestIntegrityError(
                    "revision reservation manifest ID is invalid"
                ) from error
            if payload != canonical_json_bytes(item):
                raise ManifestIntegrityError(
                    "revision reservation is not stored as canonical bytes"
                )
            reservations.append(item)
        if not reservations:
            raise ManifestIntegrityError("initialized dataset has no revision reservations")
        return reservations

    def _published_manifests(self, dataset_id: str) -> tuple[Path, ...]:
        directory = self.root / FABRIC_NAMESPACE / "datasets" / dataset_id / "manifests"
        self._reject_symlink_components(directory)
        if not directory.exists():
            return ()
        return tuple(directory.glob("*.json"))

    def _reject_symlink_components(self, path: Path) -> None:
        try:
            relative = path.relative_to(self.root)
        except ValueError as error:
            raise ManifestIntegrityError(f"artifact path escapes store root: {path}") from error
        candidate = self.root
        if is_reparse_point(candidate):
            raise ManifestIntegrityError(
                f"artifact path contains a symlink or reparse point: {candidate}"
            )
        for part in relative.parts:
            candidate /= part
            if is_reparse_point(candidate):
                raise ManifestIntegrityError(
                    f"artifact path contains a symlink or reparse point: {candidate}"
                )

    def _write_pointer(self, manifest: ArtifactManifest) -> None:
        path = self._pointer_path(manifest.dataset_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = canonical_json_bytes(
            {
                "dataset_id": manifest.dataset_id,
                "manifest_id": manifest.manifest_id,
                "compatibility_revision": manifest.compatibility_revision,
            }
        )
        descriptor, temp_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=".current.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            atomic_replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @staticmethod
    def _validate_manifest_id(manifest_id: str) -> None:
        if (
            not isinstance(manifest_id, str)
            or len(manifest_id) != 64
            or any(character not in "0123456789abcdef" for character in manifest_id)
        ):
            raise ValueError("manifest_id must be a lowercase SHA-256 digest")

    @staticmethod
    def _require_expected(current: dict[str, Any] | None, expected: str | None) -> None:
        actual = None if current is None else current["manifest_id"]
        if actual != expected:
            raise ManifestConflictError(f"expected current {expected!r}, observed {actual!r}")
