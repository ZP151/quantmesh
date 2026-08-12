"""Secret-store seam (M10 Phase A, issue #58; keyring backend Phase E,
issue #62).

``KeyStore`` is the protocol the audit-export signing key comes from.
Phase A ships ``KeyFileStore`` — a local, testable stand-in with
path-traversal refusal — so the export contract is exercised now;
Phase E adds the keyring-backed ``KeyringStore`` behind the same
protocol. No real credential ever enters the codebase: the stores are
only ever populated by drills and fixtures.
"""

import base64
import os
import re
import tempfile
from pathlib import Path
from typing import Protocol

from quantmesh._fs import atomic_replace

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
            atomic_replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    def delete(self, name: str) -> None:
        self._path(name).unlink(missing_ok=True)


class KeyringError(ValueError):
    """Base for the keyring-backed store's typed errors."""


class KeyringUnavailableError(KeyringError):
    """The real keyring backend cannot be loaded."""


class KeyringRefusalError(KeyringError):
    """A non-drill construction of the keyring-backed store."""


class KeyringBackend(Protocol):
    """The keyring backend surface the store needs (also what a fixture
    backend must provide)."""

    def get_password(self, service: str, user: str) -> str | None: ...

    def set_password(self, service: str, user: str, password: str) -> None: ...

    def delete_password(self, service: str, user: str) -> None: ...


class FixtureKeyringBackend:
    """In-memory keyring backend for tests and drills: never touches the
    OS keyring, never persists."""

    def __init__(self) -> None:
        self._values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, user: str) -> str | None:
        return self._values.get((service, user))

    def set_password(self, service: str, user: str, password: str) -> None:
        self._values[(service, user)] = password

    def delete_password(self, service: str, user: str) -> None:
        self._values.pop((service, user), None)


class _RealKeyringBackend:
    """Adapter over the ``keyring`` module — the OS-backed store. Only
    ever constructed inside an explicit drill; never exercised in
    tests."""

    def __init__(self) -> None:
        try:
            import keyring
        except ImportError as error:
            raise KeyringUnavailableError(
                "keyring is not installed (pip install keyring)"
            ) from error
        self._keyring = keyring

    def get_password(self, service: str, user: str) -> str | None:
        try:
            return self._keyring.get_password(service, user)
        except Exception as error:  # noqa: BLE001 — typed surface for the operator
            raise KeyringError(f"keyring read failed: {error}") from error

    def set_password(self, service: str, user: str, password: str) -> None:
        try:
            self._keyring.set_password(service, user, password)
        except Exception as error:  # noqa: BLE001 — typed surface for the operator
            raise KeyringError(f"keyring write failed: {error}") from error

    def delete_password(self, service: str, user: str) -> None:
        try:
            self._keyring.delete_password(service, user)
        except Exception as error:  # noqa: BLE001 — typed surface for the operator
            raise KeyringError(f"keyring delete failed: {error}") from error


class KeyringStore:
    """``KeyStore`` backend over the OS keyring (M10 Phase E, ADR-0012
    decision 5).

    The live gate governs this class: the OS keyring holds real
    credentials, so a non-drill construction is refused with a typed
    error before anything can be read or written — a store cannot exist
    outside an explicit operator drill. Tests and drills inject
    ``FixtureKeyringBackend`` and never touch the OS keyring; values
    are stored base64-encoded so arbitrary bytes round-trip.
    """

    def __init__(
        self,
        *,
        drill: bool = False,
        service: str = "quantmesh",
        backend: KeyringBackend | None = None,
    ) -> None:
        if not drill:
            raise KeyringRefusalError(
                "KeyringStore refuses construction outside a drill: the OS "
                "keyring holds real credentials, and the recorded live gate "
                "requires explicit human approval before any credential "
                "store is used"
            )
        self.service = service
        self._backend = backend if backend is not None else _RealKeyringBackend()

    def get(self, name: str) -> bytes | None:
        self._check_name(name)
        value = self._backend.get_password(self.service, name)
        if value is None:
            return None
        return base64.b64decode(value.encode("ascii"))

    def put(self, name: str, value: bytes) -> None:
        self._check_name(name)
        self._backend.set_password(
            self.service, name, base64.b64encode(value).decode("ascii")
        )

    def delete(self, name: str) -> None:
        self._check_name(name)
        self._backend.delete_password(self.service, name)

    @staticmethod
    def _check_name(name: str) -> None:
        if not _NAME_PATTERN.match(name):
            raise ValueError(f"key name {name!r} is not a safe name")
