"""Small opt-in beta registry; credentials are opaque and hashed at rest.

This separates application users, not hostile local filesystem owners. The
trusted constructor owns roots, the bootstrap token and input registrations.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import stat
import threading
import time
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from uuid import uuid4

from pydantic import SecretStr

from quantmesh.data.objects import is_reparse_point
from quantmesh.ops.paper_controls import PaperControlError, WriterLease

INVITATION_SECONDS = 24 * 3600
SESSION_SECONDS = 8 * 3600
MAX_TESTERS = 32
MAX_SESSIONS = 256
MAX_INVITATIONS = 256


class BetaError(ValueError):
    """Fixed public refusal, never a raw database/path/credential exception."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str
    session_digest: str | None = field(default=None, repr=False)


def _hash(kind, token):
    return hashlib.sha256(f"{kind}:{token}".encode()).hexdigest()


def _safe(path):
    for part in (path, *path.parents):
        if is_reparse_point(part):
            raise BetaError("auth_unavailable")
    if path.exists():
        meta = path.stat()
        if not stat.S_ISDIR(meta.st_mode) and (
            not stat.S_ISREG(meta.st_mode) or meta.st_nlink != 1
        ):
            raise BetaError("auth_unavailable")


def _store_errors(method):
    @wraps(method)
    def safe(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (OSError, sqlite3.Error, PaperControlError):
            raise BetaError("auth_unavailable") from None

    return safe


class BetaAccess:
    """One process lease, one registry lock and independent existing Native roots."""

    @_store_errors
    def __init__(self, root, *, operator_token: SecretStr, clock=time.time, native_factory=None):
        if not isinstance(operator_token, SecretStr) or len(operator_token.get_secret_value()) < 32:
            raise ValueError("beta_operator_token_requires_32_characters")
        self.root = Path(root).absolute()
        _safe(self.root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lock = threading.RLock()
        self._clock = clock
        self._bootstrap = operator_token
        self._native_factory = native_factory
        self._services = {}
        self._closed = False
        self._db_path = self.root / "accounts.sqlite"
        _safe(self._db_path)
        self._lease = WriterLease(self.root / ".writer.lock")
        self._db = None
        try:
            self._db = sqlite3.connect(self._db_path, check_same_thread=False)
            self._db.row_factory = sqlite3.Row
            self._db.execute("PRAGMA foreign_keys=ON")
            self._db.execute("PRAGMA journal_mode=DELETE")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY, display_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('operator','tester')),
                    state TEXT NOT NULL CHECK(state IN ('invited','active','revoked')),
                    created_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS invitations (
                    digest TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users,
                    expires_at INTEGER NOT NULL, consumed INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS sessions (
                    digest TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users,
                    expires_at INTEGER NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
            """)
            with self._db:
                self._db.execute(
                    "INSERT OR IGNORE INTO users VALUES (?,?,?,?,?)",
                    ("operator", "Operator", "operator", "active", int(clock())),
                )
            self._db_path.chmod(0o600)
            meta = self._db_path.stat()
            self._db_identity = (meta.st_dev, meta.st_ino)
        except BaseException:
            if self._db is not None:
                self._db.close()
            self._lease.close()
            raise

    def _ready(self):
        if self._closed:
            raise BetaError("auth_unavailable")
        self._lease.validate()
        _safe(self._db_path)
        meta = self._db_path.stat()
        if (meta.st_dev, meta.st_ino) != self._db_identity:
            raise BetaError("auth_unavailable")

    def _user(self, user_id):
        user = self._db.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if user is None:
            raise BetaError("not_found")
        return dict(user)

    def _check(self, principal, *, operator=False):
        self._ready()
        user = self._user(principal.user_id)
        if user["state"] != "active" or user["role"] != principal.role:
            raise BetaError("unauthorized")
        if principal.session_digest is not None:
            session = self._db.execute(
                "SELECT * FROM sessions WHERE digest=?", (principal.session_digest,)
            ).fetchone()
            if (
                session is None
                or session["user_id"] != principal.user_id
                or session["revoked"]
                or session["expires_at"] <= self._clock()
            ):
                raise BetaError("unauthorized")
        elif principal != Principal("operator", "operator"):
            raise BetaError("unauthorized")
        if operator and principal.role != "operator":
            raise BetaError("forbidden")
        return user

    @_store_errors
    def authenticate(self, authorization, cookie):
        with self._lock:
            self._ready()
            if authorization is not None:
                if not authorization.startswith("Bearer ") or len(authorization) > 512:
                    raise BetaError("unauthorized")
                token = authorization[7:]
                if secrets.compare_digest(
                    token.encode(), self._bootstrap.get_secret_value().encode()
                ):
                    return Principal("operator", "operator")
            else:
                token = cookie
            if not isinstance(token, str) or not 32 <= len(token) <= 128:
                raise BetaError("unauthorized")
            hashed = _hash("session", token)
            row = self._db.execute(
                "SELECT user_id FROM sessions WHERE digest=?", (hashed,)
            ).fetchone()
            if row is None:
                raise BetaError("unauthorized")
            principal = Principal(row["user_id"], self._user(row["user_id"])["role"], hashed)
            self._check(principal)
            return principal

    @_store_errors
    def guard(self, principal, operation):
        """Revoke waits for earlier guarded operations; later operations recheck."""
        with self._lock:
            self._check(principal)
            return operation()

    @_store_errors
    def me(self, principal):
        with self._lock:
            user = self._check(principal)
            expires = None
            if principal.session_digest is not None:
                expires = self._db.execute(
                    "SELECT expires_at FROM sessions WHERE digest=?", (principal.session_digest,)
                ).fetchone()[0]
            return {"user": user, "expires_at": expires}

    @_store_errors
    def create_user(self, principal, display_name):
        if not isinstance(display_name, str) or not display_name.strip() or len(display_name) > 80:
            raise BetaError("invalid_request")
        with self._lock, self._db:
            self._check(principal, operator=True)
            if (
                self._db.execute("SELECT count(*) FROM invitations").fetchone()[0]
                >= MAX_INVITATIONS
            ):
                raise BetaError("capacity_exceeded")
            if (
                self._db.execute("SELECT count(*) FROM users WHERE role='tester'").fetchone()[0]
                >= MAX_TESTERS
            ):
                raise BetaError("capacity_exceeded")
            user_id, token = str(uuid4()), secrets.token_urlsafe(32)
            expires = int(self._clock()) + INVITATION_SECONDS
            self._db.execute(
                "INSERT INTO users VALUES (?,?,?,?,?)",
                (user_id, display_name.strip(), "tester", "invited", int(self._clock())),
            )
            self._db.execute(
                "INSERT INTO invitations(digest,user_id,expires_at) VALUES (?,?,?)",
                (_hash("invitation", token), user_id, expires),
            )
            return {
                "user": self._user(user_id),
                "invitation": {"token": token, "expires_at": expires},
            }

    @_store_errors
    def users(self, principal):
        with self._lock:
            self._check(principal, operator=True)
            return {
                "users": [
                    dict(row)
                    for row in self._db.execute("SELECT * FROM users ORDER BY created_at,user_id")
                ]
            }

    @_store_errors
    def reinvite(self, principal, user_id):
        """Operator issues a fresh one-time code for the same owned archive."""
        with self._lock, self._db:
            self._check(principal, operator=True)
            user = self._user(user_id)
            if user["role"] != "tester" or user["state"] == "revoked":
                raise BetaError("forbidden")
            if (
                self._db.execute("SELECT count(*) FROM invitations").fetchone()[0]
                >= MAX_INVITATIONS
            ):
                raise BetaError("capacity_exceeded")
            token = secrets.token_urlsafe(32)
            expires = int(self._clock()) + INVITATION_SECONDS
            self._db.execute("UPDATE invitations SET consumed=1 WHERE user_id=?", (user_id,))
            self._db.execute(
                "INSERT INTO invitations(digest,user_id,expires_at) VALUES (?,?,?)",
                (_hash("invitation", token), user_id, expires),
            )
            return {"user": user, "invitation": {"token": token, "expires_at": expires}}

    def _session(self, user_id):
        if self._db.execute("SELECT count(*) FROM sessions").fetchone()[0] >= MAX_SESSIONS:
            raise BetaError("capacity_exceeded")
        token = secrets.token_urlsafe(32)
        expires = int(self._clock()) + SESSION_SECONDS
        self._db.execute(
            "INSERT INTO sessions(digest,user_id,expires_at) VALUES (?,?,?)",
            (_hash("session", token), user_id, expires),
        )
        return token, {"user": self._user(user_id), "expires_at": expires}

    @_store_errors
    def exchange(self, token):
        if not isinstance(token, str) or not 32 <= len(token) <= 128:
            raise BetaError("unauthorized")
        with self._lock, self._db:
            self._ready()
            invite = self._db.execute(
                "SELECT * FROM invitations WHERE digest=?", (_hash("invitation", token),)
            ).fetchone()
            if invite is None or invite["expires_at"] <= self._clock():
                raise BetaError("unauthorized")
            user = self._user(invite["user_id"])
            if user["state"] == "revoked":
                raise BetaError("unauthorized")
            if invite["consumed"]:
                raise BetaError("invitation_consumed")
            self._db.execute("UPDATE users SET state='active' WHERE user_id=?", (user["user_id"],))
            result = self._session(user["user_id"])
            self._db.execute(
                "UPDATE invitations SET consumed=1 WHERE digest=?", (invite["digest"],)
            )
            return result

    @_store_errors
    def operator_session(self, principal):
        with self._lock, self._db:
            self._check(principal, operator=True)
            if principal.session_digest is not None:
                raise BetaError("invalid_request")
            return self._session(principal.user_id)

    @_store_errors
    def revoke(self, principal, user_id):
        with self._lock, self._db:
            self._check(principal, operator=True)
            user = self._user(user_id)
            if user["role"] == "operator":
                raise BetaError("forbidden")
            self._db.execute("UPDATE users SET state='revoked' WHERE user_id=?", (user_id,))
            self._db.execute("UPDATE sessions SET revoked=1 WHERE user_id=?", (user_id,))
            self._db.execute("UPDATE invitations SET consumed=1 WHERE user_id=?", (user_id,))
            return self._user(user_id)

    @_store_errors
    def logout(self, principal):
        with self._lock, self._db:
            self._check(principal)
            if principal.session_digest is None:
                raise BetaError("invalid_request")
            self._db.execute(
                "UPDATE sessions SET revoked=1 WHERE digest=?", (principal.session_digest,)
            )

    def native_call(self, principal, original, method, *args):
        def operation():
            if principal.role == "operator":
                service = original
            else:
                service = self._services.get(principal.user_id)
                if service is None:
                    from quantmesh.research.native_daily_real import NativeDailyService

                    factory = self._native_factory or NativeDailyService
                    service = factory(self.root / "research" / principal.user_id)
                    self._services[principal.user_id] = service
            return getattr(service, method)(*args)

        return self.guard(principal, operation)

    def close(self):
        with self._lock:
            if not self._closed:
                # A failed service close retains registry/lease for explicit owned recovery.
                for service in self._services.values():
                    service.close()
                self._db.close()
                self._lease.close()
                self._closed = True
