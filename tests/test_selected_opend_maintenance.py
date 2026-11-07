"""Inert maintenance state-machine checks; no provider, SDK or credential access."""

import hashlib
import importlib.util
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SOURCE = Path(__file__).parents[1] / "deploy/aws/opend/selected_maintenance.py"
NOW = datetime(2026, 11, 7, 4, 0, tzinfo=UTC)
BINDING = "a" * 64


def load_core():
    if not SOURCE.exists():
        pytest.fail("selected maintenance state machine is not implemented")
    spec = importlib.util.spec_from_file_location("selected_maintenance_test_core", SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def control_data():
    return {
        "schema": "qm.opend.selected-maintenance.v1",
        "purpose": "opend_selected_instance_maintenance",
        "maintenance_id": "d" * 32,
        "successor_nonce": "e" * 32,
        "binding_sha256": BINDING,
        "source_sha256": "b" * 64,
        "interruption_authority_sha256": "c" * 64,
        "not_before": "2026-11-07T04:00:00+00:00",
        "expires_at": "2026-11-07T04:05:00+00:00",
        "max_seconds": 300,
    }


def parsed(core, data=None):
    raw = encoded(control_data() if data is None else data)
    return core.MaintenanceControl.parse(raw, hashlib.sha256(raw).hexdigest(), NOW)


class InertOps:
    """Only exclusive local records are real; all process operations are inert."""

    def __init__(self, directory):
        self.directory = directory
        self.trace = []
        self.clock = NOW
        self.elapsed = 0.0
        self.closed = {
            "cohort_exited": True,
            "old_cgroup_closed": True,
            "manager_stopped": True,
            "no_replacement": True,
            "no_listener": True,
        }
        self.holding = False
        self.signals = 0

    def now(self):
        return self.clock

    def monotonic(self):
        return self.elapsed

    def prepare(self, control, binding):
        assert binding == BINDING
        self.trace.append("prepare")

    def acquire(self, binding):
        assert binding == BINDING
        self.holding = True
        self.trace.append("acquire")

    def revalidate(self, control, binding):
        assert self.holding and binding == BINDING
        self.trace.append("revalidate")

    def create_record(self, name, raw):
        with (self.directory / name).open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Directory durability is modeled on Windows; the native adapter owns it.
        self.trace.append(name + ":fsynced")

    def signal_main_sigterm(self):
        assert self.holding
        self.signals += 1
        self.trace.append("held-main-SIGTERM")

    def wait_closed(self, deadline):
        assert deadline == 30.0
        self.trace.append("wait-closed")
        return self.closed.copy()

    def cleanup(self):
        self.trace.append("cleanup")
        self.holding = False


def test_intent_fsync_precedes_only_held_main_pidfd_sigterm(tmp_path):
    core = load_core()
    control = parsed(core)
    ops = InertOps(tmp_path)

    receipt = core.retire_selected(control, BINDING, ops)

    assert ops.trace == [
        "prepare",
        "acquire",
        "revalidate",
        "STOP-INTENT.json:fsynced",
        "revalidate",
        "held-main-SIGTERM",
        "wait-closed",
        "cleanup",
        "STOP-CLOSED.json:fsynced",
    ]
    assert ops.signals == 1
    assert receipt["schema"] == "qm.opend.selected-maintenance-closed.v1"
    assert receipt["binding_sha256"] == BINDING
    assert receipt["successor_nonce"] == "e" * 32
    assert receipt["closure"] == {
        "cohort_exited": True,
        "old_cgroup_closed": True,
        "manager_stopped": True,
        "no_replacement": True,
        "no_listener": True,
    }
    assert receipt["owned_cleanup_proven"] is True
    assert json.loads((tmp_path / "STOP-CLOSED.json").read_bytes()) == receipt


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("extra", True),
        ("schema", "other"),
        ("purpose", "restart_anything"),
        ("maintenance_id", "d" * 31),
        ("successor_nonce", "d" * 32),
        ("binding_sha256", "a" * 63),
        ("source_sha256", "B" * 64),
        ("interruption_authority_sha256", None),
        ("max_seconds", True),
        ("max_seconds", 301),
        ("not_before", "2026-11-07T04:00:00"),
        ("not_before", "2026-11-07T04:00:01+00:00"),
        ("expires_at", "2026-11-07T04:05:01+00:00"),
        ("expires_at", "2026-11-07T04:00:00+00:00"),
    ],
)
def test_invalid_control_never_enters_operations(key, value):
    core = load_core()
    data = control_data()
    data[key] = value
    raw = encoded(data)
    with pytest.raises(core.MaintenanceRefused):
        core.MaintenanceControl.parse(raw, hashlib.sha256(raw).hexdigest(), NOW)


@pytest.mark.parametrize(
    "raw", [b"", b"{}", b"[]", b"x" * 8193], ids=["empty", "object", "array", "oversized"]
)
def test_malformed_or_oversized_control_is_rejected(raw):
    core = load_core()
    with pytest.raises(core.MaintenanceRefused):
        core.MaintenanceControl.parse(raw, hashlib.sha256(raw).hexdigest(), NOW)


def test_control_requires_pinned_canonical_bytes():
    core = load_core()
    canonical = encoded(control_data())
    padded = canonical + b"\n"
    with pytest.raises(core.MaintenanceRefused):
        core.MaintenanceControl.parse(padded, hashlib.sha256(padded).hexdigest(), NOW)
    with pytest.raises(core.MaintenanceRefused):
        core.MaintenanceControl.parse(canonical, "f" * 64, NOW)
    with pytest.raises(core.MaintenanceRefused):
        core.MaintenanceControl.parse(
            canonical, hashlib.sha256(canonical).hexdigest(), NOW.replace(tzinfo=None)
        )


def test_expiry_at_boundary_rejects_before_stop(tmp_path):
    core = load_core()
    control = parsed(core)
    ops = InertOps(tmp_path)
    ops.clock = NOW + timedelta(seconds=300)
    with pytest.raises(core.MaintenanceRefused):
        core.retire_selected(control, BINDING, ops)
    assert ops.signals == 0
    assert not list(tmp_path.iterdir())


def test_wrong_binding_cannot_prepare_or_signal(tmp_path):
    core = load_core()
    ops = InertOps(tmp_path)
    with pytest.raises(core.MaintenanceRefused):
        core.retire_selected(parsed(core), "f" * 64, ops)
    assert ops.trace == ["cleanup"]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("clock", [float("nan"), float("inf"), True, "0"])
def test_invalid_monotonic_clock_refuses_before_signal(tmp_path, clock):
    core = load_core()
    ops = InertOps(tmp_path)
    ops.elapsed = clock
    with pytest.raises(core.MaintenanceRefused):
        core.retire_selected(parsed(core), BINDING, ops)
    assert ops.signals == 0
    assert not (tmp_path / "STOP-CLOSED.json").exists()


def test_successor_claim_binds_closed_receipt_and_only_one_start(tmp_path):
    core = load_core()
    control = parsed(core)
    ops = InertOps(tmp_path)
    core.retire_selected(control, BINDING, ops)
    closed = (tmp_path / "STOP-CLOSED.json").read_bytes()
    digest = hashlib.sha256(closed).hexdigest()

    claim = core.claim_successor(control, BINDING, closed, digest, ops)

    assert claim == {
        "schema": "qm.opend.selected-maintenance-successor-start.v1",
        "control_sha256": control.sha256,
        "maintenance_id": "d" * 32,
        "successor_nonce": "e" * 32,
        "binding_sha256": BINDING,
        "source_sha256": "b" * 64,
        "interruption_authority_sha256": "c" * 64,
        "closed_receipt_sha256": digest,
    }
    with pytest.raises(FileExistsError):
        core.claim_successor(control, BINDING, closed, digest, ops)
    assert json.loads((tmp_path / "SUCCESSOR-START-INTENT.json").read_bytes()) == claim


@pytest.mark.parametrize("key", sorted(InertOps(Path()).closed))
@pytest.mark.parametrize("value", [False, None, 1, "UNKNOWN"])
def test_any_unproved_closure_blocks_closed_receipt(tmp_path, key, value):
    core = load_core()
    ops = InertOps(tmp_path)
    ops.closed[key] = value
    with pytest.raises(core.MaintenanceRefused):
        core.retire_selected(parsed(core), BINDING, ops)
    assert ops.signals == 1
    assert ops.trace[-1] == "cleanup"
    assert (tmp_path / "STOP-INTENT.json").exists()
    assert not (tmp_path / "STOP-CLOSED.json").exists()


@pytest.mark.parametrize("bad_shape", [{}, {"extra": True}, []])
def test_closure_shape_must_be_complete(tmp_path, bad_shape):
    core = load_core()
    ops = InertOps(tmp_path)
    ops.closed = bad_shape
    with pytest.raises(core.MaintenanceRefused):
        core.retire_selected(parsed(core), BINDING, ops)
    assert not (tmp_path / "STOP-CLOSED.json").exists()


@pytest.mark.parametrize("failure", [KeyboardInterrupt("synthetic"), OSError("synthetic")])
def test_primary_failure_survives_cleanup_failure(tmp_path, failure):
    core = load_core()

    class Failing(InertOps):
        def signal_main_sigterm(self):
            super().signal_main_sigterm()
            raise failure

        def cleanup(self):
            super().cleanup()
            raise OSError("synthetic cleanup")

    ops = Failing(tmp_path)
    with pytest.raises(type(failure)) as caught:
        core.retire_selected(parsed(core), BINDING, ops)
    assert caught.value is failure
    assert not ops.holding
    assert ops.trace[-1] == "cleanup"
    assert not (tmp_path / "STOP-CLOSED.json").exists()


def test_cleanup_failure_after_proved_closure_cannot_publish_closed(tmp_path):
    core = load_core()

    class Failing(InertOps):
        def cleanup(self):
            super().cleanup()
            raise OSError("synthetic cleanup")

    ops = Failing(tmp_path)
    with pytest.raises(OSError):
        core.retire_selected(parsed(core), BINDING, ops)
    assert (tmp_path / "STOP-INTENT.json").exists()
    assert not (tmp_path / "STOP-CLOSED.json").exists()


@pytest.mark.parametrize("reason", ["PID_REUSED", "HANDLE_EXITED", "INVOCATION_CHANGED"])
def test_revalidation_after_fsync_refuses_drift_before_signal(tmp_path, reason):
    core = load_core()

    class Drifting(InertOps):
        def revalidate(self, control, binding):
            super().revalidate(control, binding)
            if self.trace.count("revalidate") == 2:
                raise core.MaintenanceRefused(reason)

    ops = Drifting(tmp_path)
    with pytest.raises(core.MaintenanceRefused, match=reason):
        core.retire_selected(parsed(core), BINDING, ops)
    assert ops.signals == 0
    assert (tmp_path / "STOP-INTENT.json").exists()
    assert not ops.holding


def test_expiry_during_last_revalidation_cannot_signal(tmp_path):
    core = load_core()

    class Expiring(InertOps):
        def revalidate(self, control, binding):
            super().revalidate(control, binding)
            if self.trace.count("revalidate") == 2:
                self.clock += timedelta(seconds=300)

    ops = Expiring(tmp_path)
    with pytest.raises(core.MaintenanceRefused):
        core.retire_selected(parsed(core), BINDING, ops)
    assert ops.signals == 0
    assert (tmp_path / "STOP-INTENT.json").exists()


@pytest.mark.parametrize(
    "reason", ["CREDENTIAL_MISSING", "SUCCESSOR_SOURCE_MISSING", "AUTHORITY", "SOURCE"]
)
def test_failed_preparation_never_acquires_or_creates_intent(tmp_path, reason):
    core = load_core()

    class Unprepared(InertOps):
        def prepare(self, control, binding):
            super().prepare(control, binding)
            raise core.MaintenanceRefused(reason)

    ops = Unprepared(tmp_path)
    with pytest.raises(core.MaintenanceRefused, match=reason):
        core.retire_selected(parsed(core), BINDING, ops)
    assert ops.trace == ["prepare", "cleanup"]
    assert not list(tmp_path.iterdir())


def test_partial_acquisition_failure_still_cleans_owned_handles(tmp_path):
    core = load_core()

    class Partial(InertOps):
        def acquire(self, binding):
            super().acquire(binding)
            raise OSError("synthetic partial acquisition")

    ops = Partial(tmp_path)
    with pytest.raises(OSError):
        core.retire_selected(parsed(core), BINDING, ops)
    assert not ops.holding
    assert ops.signals == 0
    assert not list(tmp_path.iterdir())


def test_uncertain_intent_fsync_is_spent_and_cannot_signal_on_reentry(tmp_path):
    core = load_core()
    control = parsed(core)

    class Uncertain(InertOps):
        def create_record(self, name, raw):
            super().create_record(name, raw)
            if name == "STOP-INTENT.json":
                raise OSError("synthetic parent fsync failure")

    first = Uncertain(tmp_path)
    with pytest.raises(OSError):
        core.retire_selected(control, BINDING, first)
    second = InertOps(tmp_path)
    with pytest.raises(FileExistsError):
        core.retire_selected(control, BINDING, second)
    assert first.signals == second.signals == 0
    assert not (tmp_path / "STOP-CLOSED.json").exists()


def test_closure_after_deadline_is_not_publishable(tmp_path):
    core = load_core()

    class Late(InertOps):
        def wait_closed(self, deadline):
            result = super().wait_closed(deadline)
            self.elapsed = 30.001
            return result

    with pytest.raises(core.MaintenanceRefused, match="CLOSURE_TIMEOUT"):
        core.retire_selected(parsed(core), BINDING, Late(tmp_path))
    assert not (tmp_path / "STOP-CLOSED.json").exists()


def test_remaining_control_lifetime_limits_closure_deadline(tmp_path):
    core = load_core()

    class NearExpiry(InertOps):
        def wait_closed(self, deadline):
            assert deadline == 5.0
            self.elapsed = 4.0
            self.clock += timedelta(seconds=4)
            return self.closed.copy()

    ops = NearExpiry(tmp_path)
    ops.clock += timedelta(seconds=295)
    core.retire_selected(parsed(core), BINDING, ops)
    assert (tmp_path / "STOP-CLOSED.json").exists()


def closed_input(core, tmp_path):
    control = parsed(core)
    ops = InertOps(tmp_path)
    core.retire_selected(control, BINDING, ops)
    raw = (tmp_path / "STOP-CLOSED.json").read_bytes()
    return control, ops, raw, hashlib.sha256(raw).hexdigest()


def test_successor_claim_concurrent_entry_delegates_at_most_once(tmp_path):
    core = load_core()
    control, ops, raw, digest = closed_input(core, tmp_path)

    def attempt():
        try:
            core.claim_successor(control, BINDING, raw, digest, ops)
            return "DELEGATE_START"
        except FileExistsError:
            return "SPENT"

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: attempt(), range(4)))
    assert results.count("DELEGATE_START") == 1
    assert results.count("SPENT") == 3


def test_successor_nonce_change_cannot_reuse_old_closure(tmp_path):
    core = load_core()
    control, ops, raw, digest = closed_input(core, tmp_path)
    changed = control_data()
    changed["successor_nonce"] = "f" * 32
    with pytest.raises(core.MaintenanceRefused):
        core.claim_successor(parsed(core, changed), BINDING, raw, digest, ops)
    assert not (tmp_path / "SUCCESSOR-START-INTENT.json").exists()
    assert control.successor_nonce == "e" * 32


def test_crash_after_successor_claim_fsync_does_not_delegate_or_retry(tmp_path):
    core = load_core()
    control, _, raw, digest = closed_input(core, tmp_path)
    interruption = KeyboardInterrupt("synthetic post-fsync interruption")

    class Interrupted(InertOps):
        def create_record(self, name, raw):
            super().create_record(name, raw)
            if name == "SUCCESSOR-START-INTENT.json":
                raise interruption

    with pytest.raises(KeyboardInterrupt) as caught:
        core.claim_successor(control, BINDING, raw, digest, Interrupted(tmp_path))
    assert caught.value is interruption
    with pytest.raises(FileExistsError):
        core.claim_successor(control, BINDING, raw, digest, InertOps(tmp_path))


@pytest.mark.parametrize("mutation", ["extra", "false", "cleanup", "source", "binding", "schema"])
def test_forged_or_incomplete_closed_receipt_never_claims_start(tmp_path, mutation):
    core = load_core()
    control, ops, raw, _ = closed_input(core, tmp_path)
    value = json.loads(raw)
    if mutation == "extra":
        value["extra"] = True
    elif mutation == "false":
        value["closure"]["old_cgroup_closed"] = False
    elif mutation == "cleanup":
        value["owned_cleanup_proven"] = False
    elif mutation == "source":
        value["source_sha256"] = "f" * 64
    elif mutation == "binding":
        value["binding_sha256"] = "f" * 64
    else:
        value["schema"] = "qm.opend.selected-maintenance-stop-intent.v1"
    bad = encoded(value)
    with pytest.raises(core.MaintenanceRefused):
        core.claim_successor(control, BINDING, bad, hashlib.sha256(bad).hexdigest(), ops)
    assert not (tmp_path / "SUCCESSOR-START-INTENT.json").exists()


def test_non_none_cleanup_result_cannot_publish_closed(tmp_path):
    core = load_core()

    class UnprovedCleanup(InertOps):
        def cleanup(self):
            super().cleanup()
            return False

    with pytest.raises(core.MaintenanceRefused, match="CLEANUP"):
        core.retire_selected(parsed(core), BINDING, UnprovedCleanup(tmp_path))
    assert not (tmp_path / "STOP-CLOSED.json").exists()


def test_control_fields_cannot_be_replaced_independently_of_pinned_bytes(tmp_path):
    core = load_core()
    control = replace(parsed(core), source_sha256="f" * 64)
    ops = InertOps(tmp_path)
    with pytest.raises(core.MaintenanceRefused):
        core.retire_selected(control, BINDING, ops)
    assert ops.signals == 0
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("malformation", ["padding", "wrong_sha", "missing", "oversized"])
def test_closed_input_must_be_exact_pinned_original(tmp_path, malformation):
    core = load_core()
    control, ops, raw, digest = closed_input(core, tmp_path)
    if malformation == "padding":
        raw += b"\n"
        digest = hashlib.sha256(raw).hexdigest()
    elif malformation == "wrong_sha":
        digest = "f" * 64
    elif malformation == "missing":
        raw = b""
        digest = hashlib.sha256(raw).hexdigest()
    else:
        raw = b"x" * 8193
        digest = hashlib.sha256(raw).hexdigest()
    with pytest.raises(core.MaintenanceRefused):
        core.claim_successor(control, BINDING, raw, digest, ops)
    assert not (tmp_path / "SUCCESSOR-START-INTENT.json").exists()


def test_expired_control_cannot_claim_successor(tmp_path):
    core = load_core()
    control, ops, raw, digest = closed_input(core, tmp_path)
    ops.clock += timedelta(seconds=300)
    with pytest.raises(core.MaintenanceRefused):
        core.claim_successor(control, BINDING, raw, digest, ops)
    assert not (tmp_path / "SUCCESSOR-START-INTENT.json").exists()
