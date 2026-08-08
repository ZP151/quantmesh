"""Secret-store seam (M10 Phase A, issue #58; keyring backend Phase E,
issue #62).

``KeyStore`` is the protocol the audit-export signing key comes from.
Phase A ships ``KeyFileStore`` — a local, testable stand-in with
path-traversal refusal — so the export contract is exercised now;
Phase E swaps in the keyring-backed store behind the same protocol.
No real credential ever enters the codebase: the stores are only ever
populated by drills and fixtures.
"""

import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class KeyStore(Protocol):
    """Named byte keys (signing keys, drill credentials)."""

    def get(self, name: str) -> bytes | None: ...

    def put(self, name: str, value: bytes) -> None: ...

    def delete(self, name: str) -> None: ...


class KeyFileStore:
    """Local key files under one root; the Phase-A stand-in backend.

    Names are restricted to a safe filename pattern (path traversal
    refused), writes are atomic (temp + replace), and a missing key
    reads as ``None`` — never an error.
    """

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, name: str) -> Path:
        if not _NAME_PATTERN.match(name):
            raise ValueError(f"key name {name!r} is not a safe filename")
        return self.root / name

    def get(self, name: str) -> bytes | None:
        path = self._path(name)
        if not path.exists():
            return None
        if not path.is_file():
            raise ValueError(f"key path {path} is not a file")
        return path.read_bytes()

    def put(self, name: str, value: bytes) -> None:
        path = self._path(name)
        self.root.mkdir(parents=True, exist_ok=True)
        descriptor, temp_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(value)
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)
