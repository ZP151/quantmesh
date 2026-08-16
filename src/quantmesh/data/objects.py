"""Content-addressed, write-once objects for trusted data artifacts."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, field_validator

FABRIC_NAMESPACE = ".trusted-data-v2"


def is_reparse_point(path: Path) -> bool:
    """Return true for symlinks, Windows junctions and other reparse points."""
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    if is_junction is not None and is_junction():
        return True
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return os.name == "nt" and bool(getattr(metadata, "st_file_attributes", 0) & reparse_flag)


class ObjectIntegrityError(ValueError):
    """Stored bytes do not match their immutable object reference."""


class ObjectRef(BaseModel):
    """Immutable identity and representation metadata for one byte object."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    algorithm: str = Field(default="sha256", pattern=r"^sha256$")
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    media_type: str = Field(min_length=1)
    byte_length: int = Field(ge=0)

    @field_validator("media_type")
    @classmethod
    def media_type_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("media_type must not be blank")
        return value


class ObjectStore:
    """Publish and verify SHA-256-addressed objects beneath one lake root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def path_for(self, reference: ObjectRef) -> Path:
        """Return the canonical path for ``reference`` without reading it."""
        return (
            self.root
            / FABRIC_NAMESPACE
            / "objects"
            / reference.algorithm
            / reference.digest[:2]
            / reference.digest
        )

    def put_bytes(self, media_type: str, payload: bytes) -> ObjectRef:
        """Publish bytes once; an existing digest must contain identical bytes."""
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        if not isinstance(media_type, str) or not media_type.strip():
            raise ValueError("media_type must not be blank")
        digest = hashlib.sha256(payload).hexdigest()
        reference = ObjectRef(
            digest=digest,
            media_type=media_type,
            byte_length=len(payload),
        )
        target = self.path_for(reference)
        self._reject_symlink_components(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._reject_symlink_components(target)
        if target.exists():
            try:
                existing = self.get_bytes(reference)
            except ObjectIntegrityError as error:
                raise ObjectIntegrityError(
                    f"conflicting bytes already exist for sha256:{digest}"
                ) from error
            if existing != payload:
                raise ObjectIntegrityError(f"conflicting bytes already exist for sha256:{digest}")
            return reference

        descriptor, temp_name = tempfile.mkstemp(
            dir=target.parent,
            prefix=f".{digest}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp_name, target)
            except FileExistsError:
                try:
                    existing = self.get_bytes(reference)
                except ObjectIntegrityError as error:
                    raise ObjectIntegrityError(
                        f"conflicting bytes already exist for sha256:{digest}"
                    ) from error
                if existing != payload:
                    raise ObjectIntegrityError(
                        f"conflicting bytes already exist for sha256:{digest}"
                    )
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return reference

    def get_bytes(self, reference: ObjectRef) -> bytes:
        """Read an object only after verifying length and SHA-256 identity."""
        path = self.path_for(reference)
        self._reject_symlink_components(path)
        try:
            payload = path.read_bytes()
        except FileNotFoundError as error:
            raise ObjectIntegrityError(f"object sha256:{reference.digest} is missing") from error
        actual = hashlib.sha256(payload).hexdigest()
        if actual != reference.digest:
            raise ObjectIntegrityError(
                f"object hash mismatch: expected {reference.digest}, observed {actual}"
            )
        if len(payload) != reference.byte_length:
            raise ObjectIntegrityError(
                f"object length mismatch: expected {reference.byte_length}, observed {len(payload)}"
            )
        return payload

    def _reject_symlink_components(self, path: Path) -> None:
        try:
            relative = path.relative_to(self.root)
        except ValueError as error:
            raise ObjectIntegrityError(f"object path escapes store root: {path}") from error
        candidate = self.root
        if is_reparse_point(candidate):
            raise ObjectIntegrityError(
                f"object path contains a symlink or reparse point: {candidate}"
            )
        for part in relative.parts:
            candidate /= part
            if is_reparse_point(candidate):
                raise ObjectIntegrityError(
                    f"object path contains a symlink or reparse point: {candidate}"
                )
