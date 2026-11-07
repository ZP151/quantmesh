"""Pure, finite selected-instance maintenance transaction; no native operations.

The fixed reviewed adapter owns root-file custody, source/authority validation,
credential metadata, pidfds, complete provider identity, native closure and IO.
This module never selects a process/service/path or opens a provider/credential.
Injected operations are an internal test/adapter seam, not a runtime caller API.

Required ops: now(), monotonic(), prepare(control, binding_sha256),
acquire(binding_sha256), revalidate(control, binding_sha256),
create_record(name, raw), signal_main_sigterm(), wait_closed(deadline), cleanup().
All action methods return None or raise, except wait_closed's exact predicates.
create_record owns its own handles and guarantees exclusive file+parent fsync.
acquire owns partial acquisitions; cleanup must attempt every owned resource.
"""

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

_CONTROL_KEYS = frozenset(
    (
        "schema",
        "purpose",
        "maintenance_id",
        "successor_nonce",
        "binding_sha256",
        "source_sha256",
        "interruption_authority_sha256",
        "not_before",
        "expires_at",
        "max_seconds",
    )
)
_CLOSURE_KEYS = frozenset(
    ("cohort_exited", "old_cgroup_closed", "manager_stopped", "no_replacement", "no_listener")
)


class MaintenanceRefused(ValueError):
    """Finite public refusal code; no provider or credential exception details."""


def _need(condition, code):
    if not condition:
        raise MaintenanceRefused(code)


def _hex(value, size=64):
    return type(value) is str and re.fullmatch("[0-9a-f]{" + str(size) + "}", value) is not None


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _utc(value):
    return type(value) is datetime and value.utcoffset() == timedelta(0)


def _timestamp(value):
    _need(type(value) is str, "CONTROL")
    stamp = datetime.fromisoformat(value)
    _need(_utc(stamp) and stamp.isoformat() == value, "CONTROL")
    return stamp


@dataclass(frozen=True)
class MaintenanceControl:
    """Validated immutable public bytes; the adapter separately proves root custody."""

    raw: bytes
    sha256: str
    maintenance_id: str
    successor_nonce: str
    binding_sha256: str
    source_sha256: str
    interruption_authority_sha256: str
    not_before: datetime
    expires_at: datetime

    @classmethod
    def parse(cls, raw, expected_sha256, now):
        try:
            _need(type(raw) is bytes and 0 < len(raw) <= 8192, "CONTROL")
            _need(_hex(expected_sha256), "CONTROL")
            _need(hashlib.sha256(raw).hexdigest() == expected_sha256, "CONTROL")
            value = json.loads(raw)
            _need(type(value) is dict and set(value) == _CONTROL_KEYS, "CONTROL")
            _need(_canonical(value) == raw, "CONTROL")
            _need(
                value["schema"] == "qm.opend.selected-maintenance.v1"
                and value["purpose"] == "opend_selected_instance_maintenance"
                and type(value["max_seconds"]) is int
                and value["max_seconds"] == 300,
                "CONTROL",
            )
            _need(
                all(_hex(value[key], 32) for key in ("maintenance_id", "successor_nonce"))
                and value["maintenance_id"] != value["successor_nonce"]
                and all(
                    _hex(value[key])
                    for key in (
                        "binding_sha256",
                        "source_sha256",
                        "interruption_authority_sha256",
                    )
                ),
                "CONTROL",
            )
            lower, upper = _timestamp(value["not_before"]), _timestamp(value["expires_at"])
            _need(_utc(now) and lower <= now < upper, "TIME")
            _need(timedelta(0) < upper - lower <= timedelta(seconds=300), "TIME")
            return cls(
                raw,
                expected_sha256,
                value["maintenance_id"],
                value["successor_nonce"],
                value["binding_sha256"],
                value["source_sha256"],
                value["interruption_authority_sha256"],
                lower,
                upper,
            )
        except MaintenanceRefused:
            raise
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            raise MaintenanceRefused("CONTROL") from None

    def check(self, now):
        _need(type(self) is MaintenanceControl, "CONTROL")
        _need(self == MaintenanceControl.parse(self.raw, self.sha256, now), "CONTROL")


def _check(control, binding_sha256, now):
    _need(type(control) is MaintenanceControl, "CONTROL")
    control.check(now)
    _need(_hex(binding_sha256) and binding_sha256 == control.binding_sha256, "BINDING")


def _receipt(control, kind):
    return {
        "schema": "qm.opend.selected-maintenance-" + kind + ".v1",
        "control_sha256": control.sha256,
        "maintenance_id": control.maintenance_id,
        "successor_nonce": control.successor_nonce,
        "binding_sha256": control.binding_sha256,
        "source_sha256": control.source_sha256,
        "interruption_authority_sha256": control.interruption_authority_sha256,
    }


def _clock(ops):
    stamp = ops.monotonic()
    _need(type(stamp) in (int, float) and math.isfinite(stamp), "CLOCK")
    return stamp


def _closed_receipt(control):
    receipt = _receipt(control, "closed")
    receipt.update(closure=dict.fromkeys(sorted(_CLOSURE_KEYS), True), owned_cleanup_proven=True)
    return receipt


def retire_selected(control, binding_sha256, ops):
    """Retire once through fixed ops; CLOSED is persisted only after owned cleanup.

    prepare validates actual source/authority, PRESENT credential metadata and
    all successor dependencies. acquire holds the exact bound cohort/cgroup;
    revalidate proves their current full identity and all pidfds live. The only
    signal method targets the adapter's internally held exact MainPID pidfd.
    wait_closed must perform bounded native checks, including no new invocation.
    """
    primary = None
    try:
        _check(control, binding_sha256, ops.now())
        _need(ops.prepare(control, binding_sha256) is None, "PREPARE")
        _need(ops.acquire(binding_sha256) is None, "ACQUIRE")
        _need(ops.revalidate(control, binding_sha256) is None, "IDENTITY")
        intent = _receipt(control, "stop-intent")
        _need(ops.create_record("STOP-INTENT.json", _canonical(intent)) is None, "INTENT")
        _check(control, binding_sha256, ops.now())
        _need(ops.revalidate(control, binding_sha256) is None, "IDENTITY")
        now = ops.now()
        _check(control, binding_sha256, now)
        deadline = _clock(ops) + min(30, (control.expires_at - now).total_seconds())
        _need(ops.signal_main_sigterm() is None, "SIGNAL")
        closure = ops.wait_closed(deadline)
        _need(
            type(closure) is dict
            and set(closure) == _CLOSURE_KEYS
            and all(value is True for value in closure.values()),
            "CLOSURE",
        )
        _need(_clock(ops) <= deadline, "CLOSURE_TIMEOUT")
        _check(control, binding_sha256, ops.now())
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            _need(ops.cleanup() is None, "CLEANUP")
        except BaseException:
            if primary is None:
                raise
    _check(control, binding_sha256, ops.now())
    receipt = _closed_receipt(control)
    _need(ops.create_record("STOP-CLOSED.json", _canonical(receipt)) is None, "CLOSED_RECORD")
    return receipt


def claim_successor(control, binding_sha256, closed_raw, closed_sha256, ops):
    """Durably claim this control's sole successor before mature start delegation.

    The fixed adapter must read the immutable CLOSED file with authenticated
    root custody; a caller-picked JSON/digest is not closure evidence. The claim
    is exclusive and remains spent even if persistence, delegation or start
    fails. A returned receipt allows the adapter one mature start call only;
    this module does not start, log in, bind or retry any provider.
    """
    _check(control, binding_sha256, ops.now())
    _need(type(closed_raw) is bytes and 0 < len(closed_raw) <= 8192, "CLOSED")
    _need(_hex(closed_sha256), "CLOSED")
    _need(hashlib.sha256(closed_raw).hexdigest() == closed_sha256, "CLOSED")
    _need(closed_raw == _canonical(_closed_receipt(control)), "CLOSED")
    receipt = _receipt(control, "successor-start")
    receipt["closed_receipt_sha256"] = closed_sha256
    _need(
        ops.create_record("SUCCESSOR-START-INTENT.json", _canonical(receipt)) is None,
        "START_INTENT",
    )
    return receipt
