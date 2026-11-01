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
PRIVATE_STORAGE_NONCE = "c8f0d0de4ca641a491fca6df24c66ceb"
# Independent fixed historical event pins; current controls cannot choose another pair.
DIAGNOSTIC_HISTORY_SHA = "8247e05ca30e7118e9a1494b31f11292502f072a1b86f119e260b71707a71afb"
DIAGNOSTIC_MARKER_SHA = "544e4f73d22b061926d665f207265f2cf11fd9ce974f45bc62d9b4074fb6acae"


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
    runtime_deadline: float | None = None

    @property
    def is_diagnostic(self):
        return (
            self.claims.get("schema_version") == 5
            and self.claims.get("diagnostic_id") == "diagnostic-1"
        )

    @property
    def consumption_name(self):
        return self.nonce + (".diagnostic-1.recovery" if self.is_diagnostic else ".recovery")

    def _active_protocol(self):
        _require(
            self.ops,
            self.nonce != PRIVATE_STORAGE_NONCE or self.is_diagnostic,
            "duplicate_recovery",
        )

    def _shape(self):
        ops, c = self.ops, self.claims
        _require(ops, type(c) is dict)
        diagnostic = c.get("schema_version") == 5
        private_storage = c.get("schema_version") in (4, 5)
        fields = ops.FIELDS | EXTRA_FIELDS
        if private_storage:
            fields = fields | {"storage_profile_sha256"}
        if diagnostic:
            fields = fields | {"diagnostic_id", "spent_recovery"}
        _require(ops, set(c) == fields)
        _require(ops, _hex(self.nonce, 32))
        if private_storage:
            _require(ops, self.nonce == PRIVATE_STORAGE_NONCE and _hex(c["storage_profile_sha256"]))
        exact = dict(
            schema_version=5 if diagnostic else 4 if private_storage else 3,
            purpose="opend_fixed_diagnostic_recovery" if diagnostic else "opend_same_unit_recovery",
            nonce=self.nonce,
            unit="quantmesh-opend-console@" + self.nonce + ".service",
            tmux_version="3.4",
            machine_sha256=ops.MACHINE_SHA,
            tmux_sha256=ops.TMUX_SHA,
            vendor_sha256=ops.VENDOR_SHA,
            ci_conclusion="success",
            max_seconds=90 if diagnostic else 180,
            human_reviewers=["Operator"],
            safety_owner="Operator",
            session_lifetime="bounded_diagnostic" if diagnostic else "until_operator_stop",
            operator_window_approved=True,
            new_device_approved=True,
            market_right_transfer_approved=True,
        )
        if private_storage:
            exact.update(gateway_uid=997, gateway_gid=987)
        _require(ops, all(type(c[k]) is type(v) and c[k] == v for k, v in exact.items()))
        _require(ops, _hex(c["approved_build"], 40) and _hex(c["launcher_sha256"]))
        _require(
            ops, all(type(c[k]) is int and 0 < c[k] < 2**31 for k in ("gateway_uid", "gateway_gid"))
        )
        start, end = ops._utc(c["not_before"]), ops._utc(c["expires_at"])
        _require(ops, 0 < (end - start).total_seconds() <= (90 if diagnostic else 300))
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

        if diagnostic:
            _require(
                ops, c["diagnostic_id"] == "diagnostic-1" and self.file_identity["size"] <= 4096
            )
            spent = c["spent_recovery"]
            _require(ops, type(spent) is dict and set(spent) == {"control", "marker"})
            for key in ("control", "marker"):
                item = spent[key]
                _require(
                    ops,
                    type(item) is dict
                    and set(item) == {"identity", "sha256"}
                    and _hex(item["sha256"]),
                )
                _require(
                    ops,
                    item["sha256"]
                    == (DIAGNOSTIC_HISTORY_SHA if key == "control" else DIAGNOSTIC_MARKER_SHA),
                )
                _identity_shape(ops, item["identity"])
                stamp = item["identity"]
                _require(
                    ops,
                    stamp["uid"] == (0 if key == "control" else 997)
                    and stamp["gid"] == (0 if key == "control" else 987)
                    and stamp["mode"] == (0o444 if key == "control" else 0o600)
                    and 0 < stamp["size"] <= (32768 if key == "control" else 1024),
                )

    def validate(self, *, now, identity, hashes):
        self._shape()
        self._active_protocol()
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
    def release_lease(self, *, deadline=None):
        self._active_protocol()
        ops = self.ops
        if self.is_diagnostic:
            values = [self.runtime_deadline] + ([deadline] if deadline is not None else [])
            _require(
                ops,
                all(type(x) in (int, float) and ops.math.isfinite(x) for x in values),
                "deadline",
            )
            deadline = min(values)
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
            history = old_marker = None
            if self.is_diagnostic:
                history = stack.enter_context(ops._protected_fd(ops.RECOVERY_HISTORY))
                old_marker = ops.os.open(
                    self.nonce + ".recovery",
                    ops.os.O_RDONLY | ops.os.O_NOFOLLOW | ops.os.O_NONBLOCK,
                    dir_fd=directory,
                )
                stack.callback(ops.os.close, old_marker)
            lease = Lease(self, control, prior, directory, claim, history, old_marker, deadline)
            stack.callback(lease.close)
            lease.check()
            lease.require_unspent()
            yield lease

    def check_available(self):
        with self.release_lease():
            pass


class Lease:
    def __init__(
        self,
        control,
        control_fd,
        prior_fd,
        directory_fd,
        claim_fd,
        history_fd=None,
        old_marker_fd=None,
        deadline=None,
    ):
        self.control = control
        self.control_fd = control_fd
        self.prior_fd = prior_fd
        self.directory = directory_fd
        self.directory_identity = _directory_stamp(control.ops.os.fstat(directory_fd))
        self.claim = claim_fd
        self.history = history_fd
        self.old_marker = old_marker_fd
        self.deadline = deadline
        self.marker = None
        self.marker_identity = None

    def check(self):
        c, ops = self.control, self.control.ops
        c._shape()
        c._active_protocol()
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
            if c.is_diagnostic:
                self._check_spent(current_directory)
            if self.marker is not None:
                held = ops.os.fstat(self.marker)
                named = ops.os.stat(
                    c.consumption_name, dir_fd=current_directory, follow_symlinks=False
                )
                _require(
                    ops,
                    stat.S_ISREG(held.st_mode)
                    and stat.S_ISREG(named.st_mode)
                    and _stamp(held) == _stamp(named) == self.marker_identity,
                )

    def _check_spent(self, directory):
        c, ops = self.control, self.control.ops
        historical = None
        for key, fd, maximum in (
            ("control", self.history, 32768),
            ("marker", self.old_marker, 1024),
        ):
            raw, identity = _read(ops, fd, maximum)
            expected = c.claims["spent_recovery"][key]
            _require(
                ops,
                identity == expected["identity"]
                and hashlib.sha256(raw).hexdigest() == expected["sha256"],
            )
            if key == "control":
                with ops._protected_fd(ops.RECOVERY_HISTORY) as named:
                    _require(ops, _stamp(ops.os.fstat(named)) == identity)
                historical = ops._json(raw)
                old = Control(ops, historical, c.nonce, identity, expected["sha256"])
                old._shape()
                _require(ops, historical["schema_version"] == 4)
                _require(
                    ops,
                    all(
                        historical[k] == c.claims[k]
                        for k in (
                            "nonce",
                            "unit",
                            "machine_sha256",
                            "gateway_uid",
                            "gateway_gid",
                            "original_claim",
                            "prior_permit",
                            "storage_profile_sha256",
                        )
                    ),
                )
            else:
                named = ops.os.stat(c.nonce + ".recovery", dir_fd=directory, follow_symlinks=False)
                _require(ops, stat.S_ISREG(named.st_mode) and _stamp(named) == identity)
                _require(
                    ops,
                    ops._json(raw)
                    == dict(
                        schema_version=1,
                        state="ATTEMPTED",
                        purpose="opend_same_unit_recovery_consumed",
                        nonce=c.nonce,
                        control_sha256=c.claims["spent_recovery"]["control"]["sha256"],
                    ),
                )

    def require_unspent(self):
        ops = self.control.ops
        try:
            ops.os.stat(self.control.consumption_name, dir_fd=self.directory, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise ops.StageDenied("duplicate_recovery")

    def consume(self):
        """Irreversible attempted release, never a vendor-success receipt."""
        ops, c = self.control.ops, self.control
        _require(ops, self.marker is None, "duplicate_recovery")
        self.check()
        if c.is_diagnostic:
            # All potentially blocking evidence checks finish before this irreversible boundary.
            _require(
                ops,
                ops._utc(c.claims["not_before"])
                <= ops.datetime.now(ops.UTC)
                < ops._utc(c.claims["expires_at"])
                and ops.time.monotonic() < self.deadline,
                "deadline",
            )
        try:
            self.marker = ops.os.open(
                c.consumption_name,
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
    if result.is_diagnostic:
        anchor = ops.time.monotonic()
        remaining = min(
            90, (ops._utc(result.claims["expires_at"]) - ops.datetime.now(ops.UTC)).total_seconds()
        )
        result = Control(ops, result.claims, nonce, identity, result.digest, anchor + remaining)
    return result
