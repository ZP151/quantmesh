"""One separately consumed recovery of the fixed persistent OpenD instance.

Only the pinned stage launcher supplies ops. No CLI, credential, vendor-state,
SDK or arbitrary-path interface exists here.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass

STAMP_FIELDS = {
    "device",
    "inode",
    "uid",
    "gid",
    "mode",
    "nlink",
    "size",
    "mtime_ns",
    "ctime_ns",
}
EXTRA_FIELDS = {"unit", "vendor_sha256", "session_lifetime", "original_claim", "prior_permit"}


def _stamp(info):
    return dict(
        device=info.st_dev,
        inode=info.st_ino,
        uid=info.st_uid,
        gid=info.st_gid,
        mode=stat.S_IMODE(info.st_mode),
        nlink=info.st_nlink,
        size=info.st_size,
        mtime_ns=info.st_mtime_ns,
        ctime_ns=info.st_ctime_ns,
    )


def _directory_stamp(info):
    # Creating the regular consumption file changes directory size/timestamps.
    return {
        key: value
        for key, value in _stamp(info).items()
        if key not in {"size", "mtime_ns", "ctime_ns"}
    }


def _require(ops, condition, code="recovery_denied"):
    if not condition:
        raise ops.StageDenied(code)


def _hex(value, length=64):
    return type(value) is str and re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is not None


def _identity_shape(ops, value):
    _require(ops, type(value) is dict and set(value) == STAMP_FIELDS)
    _require(ops, all(type(v) is int and v >= 0 for v in value.values()))
    _require(ops, value["inode"] > 0 and value["nlink"] == 1 and value["mode"] <= 0o777)


def _read(ops, fd, maximum=32768):
    before = ops.os.fstat(fd)
    _require(ops, stat.S_ISREG(before.st_mode) and 0 < before.st_size <= maximum)
    ops.os.lseek(fd, 0, 0)
    parts = bytearray()
    while len(parts) <= maximum:
        chunk = ops.os.read(fd, min(65536, maximum + 1 - len(parts)))
        if not chunk:
            break
        parts.extend(chunk)
    _require(ops, len(parts) == before.st_size and _stamp(before) == _stamp(ops.os.fstat(fd)))
    return bytes(parts), _stamp(before)


@dataclass(frozen=True)
class Control:
    ops: object
    claims: dict
    nonce: str
    file_identity: dict
    digest: str

    def _shape(self):
        ops, c = self.ops, self.claims
        _require(ops, type(c) is dict and set(c) == ops.FIELDS | EXTRA_FIELDS)
        _require(ops, _hex(self.nonce, 32))
        exact = dict(
            schema_version=3,
            purpose="opend_same_unit_recovery",
            nonce=self.nonce,
            unit="quantmesh-opend-console@" + self.nonce + ".service",
            tmux_version="3.4",
            machine_sha256=ops.MACHINE_SHA,
            tmux_sha256=ops.TMUX_SHA,
            vendor_sha256=ops.VENDOR_SHA,
            ci_conclusion="success",
            max_seconds=180,
            human_reviewers=["Operator"],
            safety_owner="Operator",
            session_lifetime="until_operator_stop",
            operator_window_approved=True,
            new_device_approved=True,
            market_right_transfer_approved=True,
        )
        _require(ops, all(type(c[k]) is type(v) and c[k] == v for k, v in exact.items()))
        _require(ops, _hex(c["approved_build"], 40) and _hex(c["launcher_sha256"]))
        _require(
            ops, all(type(c[k]) is int and 0 < c[k] < 2**31 for k in ("gateway_uid", "gateway_gid"))
        )
        start, end = ops._utc(c["not_before"]), ops._utc(c["expires_at"])
        _require(ops, 0 < (end - start).total_seconds() <= 300)
        old = c["original_claim"]
        _identity_shape(ops, old)
        _require(
            ops,
            old["uid"] == c["gateway_uid"]
            and old["gid"] == c["gateway_gid"]
            and old["mode"] == 0o600
            and old["size"] == 0,
        )
        prior = c["prior_permit"]
        _require(
            ops,
            type(prior) is dict and set(prior) == {"identity", "sha256"} and _hex(prior["sha256"]),
        )
        _identity_shape(ops, prior["identity"])
        _require(
            ops,
            prior["identity"]["uid"] == 0
            and not prior["identity"]["mode"] & 0o022
            and 0 < prior["identity"]["size"] <= 32768,
        )

    def validate(self, *, now, identity, hashes):
        self._shape()
        ops, c = self.ops, self.claims
        _require(
            ops,
            now.tzinfo is not None and ops._utc(c["not_before"]) <= now < ops._utc(c["expires_at"]),
        )
        _require(
            ops,
            all(c[k] == identity.get(k) for k in ("machine_sha256", "gateway_uid", "gateway_gid")),
            "identity_denied",
        )
        _require(
            ops,
            all(c[k] == hashes.get(k) for k in ("launcher_sha256", "tmux_sha256", "vendor_sha256")),
            "pin_drift",
        )

    @contextmanager
    def release_lease(self):
        ops = self.ops
        with ExitStack() as stack:
            control = stack.enter_context(ops._protected_fd(ops.RECOVERY_PERMIT))
            prior = stack.enter_context(ops._protected_fd(ops.PERSISTENT_PERMIT))
            directory = stack.enter_context(ops._owned_dir(ops.STATE))
            claim = ops.os.open(
                self.nonce,
                ops.os.O_RDONLY | ops.os.O_NOFOLLOW | ops.os.O_NONBLOCK,
                dir_fd=directory,
            )
            stack.callback(ops.os.close, claim)
            lease = Lease(self, control, prior, directory, claim)
            stack.callback(lease.close)
            lease.check()
            lease.require_unspent()
            yield lease

    def check_available(self):
        with self.release_lease():
            pass


class Lease:
    def __init__(self, control, control_fd, prior_fd, directory_fd, claim_fd):
        self.control = control
        self.control_fd = control_fd
        self.prior_fd = prior_fd
        self.directory = directory_fd
        self.directory_identity = _directory_stamp(control.ops.os.fstat(directory_fd))
        self.claim = claim_fd
        self.marker = None
        self.marker_identity = None

    def check(self):
        c, ops = self.control, self.control.ops
        c._shape()
        _require(
            ops,
            ops._utc(c.claims["not_before"])
            <= ops.datetime.now(ops.UTC)
            < ops._utc(c.claims["expires_at"]),
        )
        raw, identity = _read(ops, self.control_fd)
        _require(
            ops,
            identity == c.file_identity
            and hashlib.sha256(raw).hexdigest() == c.digest
            and ops._json(raw) == c.claims,
        )
        _require(ops, identity["uid"] == 0 and identity["mode"] == 0o444 and identity["nlink"] == 1)
        with ops._protected_fd(ops.RECOVERY_PERMIT) as current:
            _require(ops, _stamp(ops.os.fstat(current)) == identity)
        prior, prior_identity = _read(ops, self.prior_fd)
        _require(
            ops,
            prior_identity == c.claims["prior_permit"]["identity"]
            and hashlib.sha256(prior).hexdigest() == c.claims["prior_permit"]["sha256"],
        )
        with ops._protected_fd(ops.PERSISTENT_PERMIT) as current:
            _require(ops, _stamp(ops.os.fstat(current)) == prior_identity)
        with ops._owned_dir(ops.STATE) as current_directory:
            held_directory = ops.os.fstat(self.directory)
            named_directory = ops.os.fstat(current_directory)
            _require(
                ops,
                stat.S_ISDIR(held_directory.st_mode)
                and stat.S_ISDIR(named_directory.st_mode)
                and _directory_stamp(held_directory)
                == _directory_stamp(named_directory)
                == self.directory_identity
                and held_directory.st_uid == c.claims["gateway_uid"]
                and held_directory.st_gid == c.claims["gateway_gid"]
                and stat.S_IMODE(held_directory.st_mode) == 0o700,
            )
            held = ops.os.fstat(self.claim)
            named = ops.os.stat(c.nonce, dir_fd=current_directory, follow_symlinks=False)
            _require(
                ops,
                stat.S_ISREG(held.st_mode)
                and stat.S_ISREG(named.st_mode)
                and _stamp(held) == _stamp(named) == c.claims["original_claim"],
                "claim_changed",
            )
            if self.marker is not None:
                held = ops.os.fstat(self.marker)
                named = ops.os.stat(
                    c.nonce + ".recovery", dir_fd=current_directory, follow_symlinks=False
                )
                _require(
                    ops,
                    stat.S_ISREG(held.st_mode)
                    and stat.S_ISREG(named.st_mode)
                    and _stamp(held) == _stamp(named) == self.marker_identity,
                )

    def require_unspent(self):
        ops = self.control.ops
        try:
            ops.os.stat(
                self.control.nonce + ".recovery", dir_fd=self.directory, follow_symlinks=False
            )
        except FileNotFoundError:
            return
        raise ops.StageDenied("duplicate_recovery")

    def consume(self):
        """Irreversible attempted release, never a vendor-success receipt."""
        ops, c = self.control.ops, self.control
        _require(ops, self.marker is None, "duplicate_recovery")
        self.check()
        try:
            self.marker = ops.os.open(
                c.nonce + ".recovery",
                ops.os.O_WRONLY | ops.os.O_CREAT | ops.os.O_EXCL | ops.os.O_NOFOLLOW,
                0o600,
                dir_fd=self.directory,
            )
        except FileExistsError:
            raise ops.StageDenied("duplicate_recovery") from None
        # A partially written/fsync-failed marker remains spent. Never unlink it.
        ops.os.fchmod(self.marker, 0o600)
        payload = (
            json.dumps(
                {
                    "schema_version": 1,
                    "state": "ATTEMPTED",
                    "purpose": "opend_same_unit_recovery_consumed",
                    "nonce": c.nonce,
                    "control_sha256": c.digest,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        _require(ops, len(payload) <= 1024)
        remaining = memoryview(payload)
        while remaining:
            written = ops.os.write(self.marker, remaining)
            _require(ops, written > 0)
            remaining = remaining[written:]
        ops.os.fsync(self.marker)
        ops.os.fsync(self.directory)
        info = ops.os.fstat(self.marker)
        self.marker_identity = _stamp(info)
        _require(
            ops,
            stat.S_ISREG(info.st_mode)
            and info.st_uid == c.claims["gateway_uid"]
            and info.st_gid == c.claims["gateway_gid"]
            and info.st_nlink == 1
            and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_size == len(payload),
        )
        self.check()

    def close(self):
        if self.marker is not None:
            fd, self.marker = self.marker, None
            self.control.ops.os.close(fd)


def load(ops, nonce):
    with ops._protected_fd(ops.RECOVERY_PERMIT) as fd:
        raw, identity = _read(ops, fd)
        _require(ops, identity["uid"] == 0 and identity["mode"] == 0o444 and identity["nlink"] == 1)
    result = Control(ops, ops._json(raw), nonce, identity, hashlib.sha256(raw).hexdigest())
    result._shape()
    return result
