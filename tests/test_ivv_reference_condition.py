"""Bounded real-ledger conditional transition; synthetic external evidence only."""

import copy
import importlib.util
import io
import os
import sys
import tempfile
import threading
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, BASE / path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


task = module("_condition_ledger", "tools/research/ivv_additional_task.py")
contract = module("_condition_contract", "src/quantmesh/research/ivv_recovery.py")


def pair(policy_sha):
    return dict(
        schema_id="qm.ivv.reference-pair.v1",
        nonce="a" * 32,
        reference_attempt="connection-000001",
        capture_attempt="connection-000002",
        reference_context="b" * 32,
        capture_context="c" * 32,
        reference_control_sha256="d" * 64,
        method_sha256="a" * 64,
        policy_sha256=policy_sha,
        provider_binding_sha256="e" * 64,
        sdk_pins_sha256="f" * 64,
        provider_config_sha256="1" * 64,
        provider_cohort_sha256="2" * 64,
    )


def dispatch(book, attempt):
    claim = book._read(f"connection-{int(attempt[-6:]) - 1:06d}.reference-claim.json")
    return dict(
        controller=claim["controller"],
        claim_inode=claim["claim_inode"],
        unit="qm-ivv-recovery-" + attempt + ".service",
    )


class ConditionLedger(unittest.TestCase):
    def test_same_source_requires_exact_once_transition_and_child_recheck(self):
        controlled = os.environ.get("QM_CONDITION_SCRATCH")
        if controlled:
            Path(controlled).mkdir(exist_ok=True)
        root = Path(tempfile.mkdtemp(prefix="ledger-", dir=controlled))
        book = task.RecoveryLedger(root, contract.DEFAULT_POLICY, contract)
        value = pair(book.policy_sha)
        first = book.begin("a" * 64, now=100, reference_pair=value)
        book.close(
            first,
            dict(
                child_reaped=True,
                recursive_populated=0,
                owned_fds_closed=True,
                resource_limit_event=False,
                active_owned_processes=0,
            ),
            failure="REFERENCE_INIT_OBSERVATION",
            method_sha256="a" * 64,
        )
        with self.assertRaisesRegex(ValueError, "unrepaired_structural_failure"):
            book.begin("a" * 64, now=101)
        book._claim_lease = NS(
            fd=88,
            controller=dict(pid=222, start_ticks=3, uid=0, cgroup="/parent"),
            origin=[1, 2, 16832, 0],
        )
        book._claim_lease.bind_reference_epoch = lambda offset: setattr(
            book._claim_lease, "reference_epoch", offset
        )
        book._reference_live_owner = lambda *args: (
            None
        )  # Storage-only test; actual owner is tested below.
        claim = book.claim_reference_condition(contract.digest(contract.canonical(value)))
        evidence = {"closed_originals": {"synthetic": "3" * 64}}
        fresh = dict(
            schema_id="qm.ivv.reference-fresh.v1",
            pair_sha256=claim["pair_sha256"],
            evidence_sha256=contract.digest(contract.canonical(evidence)),
            boot_id="12345678-1234-1234-1234-123456789abc",
            closes_observed=100.0,
            sample_started=100.1,
            sample_finished=100.2,
        )
        book._write(first + ".reference-evidence.json", evidence)
        book._write(first + ".reference-fresh.json", fresh)
        # These synthetic records test storage enforcement only; the actual trusted
        # producer/physical evidence seam is exercised separately, never implied here.
        outcome = dict(
            schema_id="qm.ivv.reference-condition.v1",
            state="POSITIVE",
            pair_sha256=claim["pair_sha256"],
            claim_sha256=contract.digest(contract.canonical(claim)),
            reference_attempt=first,
            capture_attempt=value["capture_attempt"],
            close_sha256=contract.digest(contract.canonical(book._read(first + ".close.json"))),
            evidence_sha256=contract.digest(contract.canonical(evidence)),
            fresh_sha256=contract.digest(contract.canonical(fresh)),
        )
        book._write(first + ".reference-condition.json", outcome)
        ref = dict(
            pair_sha256=claim["pair_sha256"],
            outcome_sha256=contract.digest(contract.canonical(outcome)),
        )
        clock = patch.object(task, "reference_clock", return_value=(fresh["boot_id"], 101.0))
        clock.start()
        self.addCleanup(clock.stop)
        second = book.begin(
            "a" * 64,
            now=101,
            reference_transition=ref,
            pre_dispatch=dispatch(book, value["capture_attempt"]),
            expected_connection=value["capture_attempt"],
        )
        self.assertEqual(second, value["capture_attempt"])
        self.assertEqual(book._read(second + ".intent.json")["reference_transition"], ref)
        book.enter(second, "a" * 64, "5" * 64)
        plan = dict(
            recovery={"connection_attempt_id": second},
            reference_pair_ref={"path": "/pair", "sha256": claim["pair_sha256"]},
            operation_context=value["capture_context"],
        )
        book.bind_reference_plan(second, plan, value, "5" * 64)
        book.may_connect(second)
        with self.assertRaises(FileExistsError):
            book.may_connect(second)
        with self.assertRaises(ValueError):
            book.claim_reference_condition(claim["pair_sha256"])


class MemoryLedger(task.RecoveryLedger):
    """External durable-storage model; real ledger transition code is inherited."""

    def __init__(self, root):
        self.root = root
        self.contract = contract
        self.policy = contract.validate_policy(contract.DEFAULT_POLICY)
        self.policy_sha = contract.digest(contract.canonical(self.policy))
        self._lock = threading.RLock()
        self.rows = {}

    def _read(self, name):
        if name not in self.rows:
            raise FileNotFoundError(name)
        return copy.deepcopy(self.rows[name])

    def _write(self, name, value):
        if name in self.rows:
            raise FileExistsError(name)
        self.rows[name] = copy.deepcopy(value)
        return value

    def _intents(self):
        return [self._read(k) for k in sorted(self.rows) if k.endswith(".intent.json")]


class ConditionOwner(unittest.TestCase):
    def fixture(self, fault=None):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.fixture_stack = stack
        r = module("_condition_runner", "tools/research/ivv_trusted_runner.py")
        native = module("_condition_native", "tools/research/ivv_dev_native.py")
        producer = module("_condition_producer", "tools/research/ivv_native_producer.py")
        first = "connection-000001"
        loc = r._locations(first)
        book = MemoryLedger(loc.ledger)
        value = pair(book.policy_sha)
        sources = {
            role: (
                BASE
                / ("src/quantmesh/research/" if name == "ivv_recovery.py" else "tools/research/")
                / name
            ).read_bytes()
            for role, name in r._sources(first).items()
        }
        pins = {role: r.digest(body) for role, body in sources.items()}
        value["method_sha256"] = r.digest(r.raw_json(pins))
        # Literal synthetic provider record, validated by the real closed producer parser.
        nonce = "5" * 32
        unit = "quantmesh-opend-console@" + nonce + ".service"
        record = dict(
            schema="qm.opend.provider-binding.v2",
            machine_sha256=producer.MACHINE,
            template_sha256=producer.RESTORE_TEMPLATE,
            vendor_sha256=producer.VENDOR_SHA,
            profile_sha256=producer.RESTORE_PROFILE,
            launch=dict(
                schema="qm.opend.attributed-launch.v2",
                nonce=nonce,
                authority_sha256=producer.RESTORE_AUTHORITY,
                control_sha256="6" * 64,
                launcher_sha256="7" * 64,
                unit=unit,
                invocation="8" * 32,
                cgroup="/system.slice/" + unit,
                main_pid=11,
                pane_pid=12,
                vendor_pid=13,
                vendor_start=103,
                claim_dev=1,
                claim_ino=9,
            ),
            processes={
                role: dict(pid=pid, start=100 + pid - 10, ppid=parent, mnt=101, net=102)
                for role, pid, parent in (("TMUX", 11, 1), ("PYTHON", 12, 11), ("VENDOR", 13, 12))
            },
        )
        raw_provider = r.raw_json(record)
        binding = producer.validate_provider_binding(raw_provider, r.digest(raw_provider))
        value["provider_binding_sha256"] = binding.receipt_sha
        value["provider_config_sha256"] = r.digest(
            r.raw_json(
                dict(
                    control=binding.control_sha,
                    launcher=binding.launcher_sha,
                    profile=producer.RESTORE_PROFILE,
                    template=producer.RESTORE_TEMPLATE,
                )
            )
        )
        value["provider_cohort_sha256"] = r.digest(
            r.raw_json(
                dict(
                    unit=binding.unit,
                    invocation=binding.invocation,
                    cgroup=binding.cgroup,
                    cohort=binding.cohort,
                    mnt=binding.mnt,
                    net=binding.net,
                )
            )
        )
        sdk = {
            "pins": [
                {"relative_path": "moomoo/" + str(i) + ".py", "LF_sha256": r.digest(b"sdk")}
                for i in range(17)
            ]
        }
        sdkraw = r.raw_json(sdk)
        value["sdk_pins_sha256"] = r.digest(sdkraw)
        reference_control = dict(
            schema_id="qm.ivv.reference-control.v1",
            **{
                key: value[key]
                for key in (
                    "nonce",
                    "reference_attempt",
                    "capture_attempt",
                    "reference_context",
                    "capture_context",
                )
            },
            catalog_sha256="0" * 64,
            sdk_pins_sha256=value["sdk_pins_sha256"],
            policy_sha256=book.policy_sha,
        )
        catalog = dict(pins, provider_binding=record)
        catraw = r.raw_json(catalog)
        reference_control["catalog_sha256"] = r.digest(catraw)
        controlraw = r.raw_json(reference_control)
        value["reference_control_sha256"] = r.digest(controlraw)
        pair_sha = r.digest(r.raw_json(value))
        book._write(first + ".reference-pair.json", value)
        book._write(
            first + ".intent.json",
            dict(
                connection_attempt_id=first,
                reference_pair_sha256=pair_sha,
                method_sha256=value["method_sha256"],
                policy_sha256=book.policy_sha,
                batch_id=book.policy["batch"]["batch_id"],
                started=90.0,
            ),
        )
        book.close(
            first,
            dict(
                child_reaped=True,
                recursive_populated=0,
                owned_fds_closed=True,
                resource_limit_event=False,
                active_owned_processes=0,
            ),
            failure="REFERENCE_INIT_OBSERVATION",
            method_sha256=value["method_sha256"],
        )
        manager_unit = "qm-ivv-recovery-" + first + ".service"
        actor = dict(
            pid=111, start_ticks=12, uid=0, cgroup="/system.slice/" + manager_unit + "/manager"
        )
        startup = b"{}"
        book._write(
            first + ".entry.json",
            dict(state="ENTERED", startup_sha256=r.digest(startup), connection_attempt_id=first),
        )
        book._write(
            first + ".context-binding.json",
            dict(
                schema_id="qm.ivv.reference-context-binding.v1",
                connection_attempt_id=first,
                operation="reference",
                operation_context=value["reference_context"],
                pair_sha256=pair_sha,
                startup_sha256=r.digest(startup),
            ),
        )
        fields = dict(Id=manager_unit, MainPID="111", InvocationID="9" * 32)
        preowner = dict(
            connection_attempt_id=first,
            startup_sha256=r.digest(startup),
            manager=actor,
            unit=fields,
            group=[1, 2, 16832, 0],
            mount={"id": 17},
        )
        terminal = dict(
            fields,
            MainPID="0",
            ActiveState="inactive",
            SubState="dead",
            ExecMainCode="1",
            ExecMainStatus="1",
        )
        for name, body in {
            "preowner": preowner,
            "terminal": dict(preowner_sha256=r.digest(r.raw_json(preowner)), terminal=terminal),
            "unit-cleanup": dict(
                preowner_sha256=r.digest(r.raw_json(preowner)),
                owned_cleanup_proven=True,
                external_effects="UNKNOWN",
                input_publishable=False,
            ),
            "manager-exit": dict(
                manager_returncode=1,
                invocation_id=fields["InvocationID"],
                startup_sha256=r.digest(startup),
            ),
            "unit-result": dict(
                manager_returncode=1,
                client_returncode=1,
                invocation_id=fields["InvocationID"],
                startup_sha256=r.digest(startup),
            ),
        }.items():
            book._write(first + "." + name + ".json", body)
        obs = dict(
            schema_id="qm.ivv.reference-init-observation.v1",
            reference_control_sha256=value["reference_control_sha256"],
            constructor_status="READY",
            operation_failed=False,
            close_failed=False,
            parent_closed=True,
            normal_close=dict(context_closed=True, callbacks_stopped=True, data_socket_closed=True),
        )
        plan = dict(
            reference_init_ref=dict(
                path=str(loc.control / "reference-control.json"),
                sha256=value["reference_control_sha256"],
            ),
            reference_pair_ref=dict(path=str(loc.control / "reference-pair.json"), sha256=pair_sha),
            operation_context=value["reference_context"],
            recovery={"connection_attempt_id": first},
            sdk_pins_ref=dict(
                path=str(loc.control / "sdk-pins.json"), sha256=value["sdk_pins_sha256"]
            ),
        )
        files = {
            str(loc.control / name): body
            for name, body in {
                "runner-failure.json": r.raw_json(
                    dict(
                        state="STOP",
                        reason="REFERENCE_INIT_OBSERVATION",
                        reference_init_observation=obs,
                    )
                ),
                "reference-control.json": controlraw,
                "startup.json": startup,
                "plan.json": r.raw_json(plan),
                "reference-pair.json": r.raw_json(value),
                "sdk-pins.json": sdkraw,
                "policy.json": contract.canonical(book.policy),
            }.items()
        }
        files[str(loc.release / "release-catalog.json")] = catraw
        files.update(
            {str(loc.release / name): sources[role] for role, name in r._sources(first).items()}
        )
        if fault == "not_ready":
            obs["constructor_status"] = "NOT_READY"
        if fault == "not_returned":
            obs["constructor_status"] = "NOT_RETURNED"
        if fault == "sdk_close":
            obs["normal_close"]["data_socket_closed"] = False
        files[str(loc.control / "runner-failure.json")] = r.raw_json(
            dict(state="STOP", reason="REFERENCE_INIT_OBSERVATION", reference_init_observation=obs)
        )
        if fault == "manager":
            book.rows[first + ".manager-exit.json"]["manager_returncode"] = -1
        if fault == "client":
            book.rows[first + ".unit-result.json"]["client_returncode"] = 0
        if fault == "terminal":
            book.rows[first + ".terminal.json"]["terminal"]["ExecMainCode"] = "2"
        if fault == "cleanup":
            del book.rows[first + ".unit-cleanup.json"]
        if fault == "unknown_close":
            book.rows[first + ".close.json"]["owner_state"] = "UNKNOWN"
        if fault == "first_context":
            book.rows[first + ".context-binding.json"]["operation_context"] = "0" * 32
        if fault == "first_startup":
            book.rows[first + ".context-binding.json"]["startup_sha256"] = "0" * 64
        if fault == "invocation":
            book.rows[first + ".unit-result.json"]["invocation_id"] = "0" * 32
        if fault == "source":
            files[str(loc.release / "ivv_dev_native.py")] += b"\n"

        def read(path, maximum):
            data = files[str(path)]
            if len(data) > maximum:
                raise ValueError("BOUND")
            return data

        controller = dict(pid=222, start_ticks=3, uid=0, cgroup="/parent")
        book._claim_lease = r._RecoveryLease(88)
        book._claim_lease.controller = controller
        book._claim_lease.origin = [1, 2, 16832, 0]
        stack.enter_context(
            patch.object(r.os, "lseek", side_effect=lambda fd, offset, whence: offset)
        )
        stack.enter_context(patch.object(r, "_controller_actor", return_value=(controller, 1)))
        stack.enter_context(
            patch.object(
                r.os, "fstat", return_value=NS(st_dev=1, st_ino=2, st_mode=16832, st_uid=0)
            )
        )
        stack.enter_context(
            patch.object(
                r.Path, "lstat", return_value=NS(st_dev=1, st_ino=2, st_mode=16832, st_uid=0)
            )
        )
        stack.enter_context(
            patch.object(
                r.Path, "stat", return_value=NS(st_dev=1, st_ino=2, st_mode=16832, st_uid=0)
            )
        )
        stack.enter_context(patch.object(r.os, "major", return_value=0, create=True))
        stack.enter_context(patch.object(r.os, "minor", return_value=1, create=True))
        stack.enter_context(
            patch.object(
                r.Path,
                "open",
                side_effect=lambda *a, **k: io.BytesIO(
                    (
                        f"pos:\t{getattr(book._claim_lease, 'reference_epoch', 0)}\n"
                        "lock:\t1: FLOCK  ADVISORY  WRITE 222 00:01:2 0 EOF\n"
                    ).encode()
                ),
            )
        )
        stack.enter_context(
            patch.object(
                r.Path, "exists", lambda path: str(path) in files or path.name in book.rows
            )
        )
        stack.enter_context(
            patch.object(
                r,
                "_process",
                side_effect=None if fault == "unit_active" else FileNotFoundError,
                return_value=(actor, 1),
            )
        )
        stack.enter_context(patch.object(r, "_manager_fields", return_value=terminal))
        stack.enter_context(patch.object(r, "_cgroup_mount", return_value=17))
        for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC"):
            stack.enter_context(patch.object(r.os, flag, 0, create=True))
        stack.enter_context(patch.object(r.os, "open", side_effect=FileNotFoundError))
        # Reuse the actual native snapshot acquisition/validation/close sequence with
        # a scripted procfs/resource reader, never replace verified_provider_snapshot.
        # Cryptographic upstream control/source checks run in separate baseline guard tests;
        # this model cannot invent matching preimages, so source acquisition is bounded here.
        stack.enter_context(patch.object(native, "_operator_sources", return_value=987))

        class Reader:
            def __init__(self, bound):
                self.binding = bound
                self.manager_fields = {"ControlGroup": bound.cgroup}

            def identity(self):
                return dict(
                    machine=producer.MACHINE,
                    unit=binding.unit,
                    invocation=binding.invocation,
                    active="active",
                    substate="running",
                    main_pid=11,
                    vendor_loopback11112=True,
                    processes=[
                        dict(
                            pid=p,
                            start=s,
                            ppid=pp,
                            role=role,
                            uids=[997] * 4,
                            gids=[987] * 4,
                            groups=[987],
                            exe_verified=True,
                            mnt=0 if fault == "provider_namespace" else 101,
                            net=102,
                            cgroup_unit=binding.unit,
                            caps=0,
                            nnp=1,
                        )
                        for p, s, pp, role in binding.cohort
                    ],
                )

            def directory(self, name):
                return 77

            def read(self, fd, name, bound):
                return {
                    "memory.high": b"805306368",
                    "memory.max": b"1073741824",
                    "memory.swap.max": b"0",
                    "cpu.max": b"50000 100000",
                    "pids.max": b"128",
                }[name]

            def release(self, fd):
                pass

            def finish(self):
                return fault == "provider"

            def close(self):
                if fault == "provider_close":
                    raise OSError("scripted close")

        stack.enter_context(patch.object(producer, "OperatorReader", Reader))
        stack.enter_context(
            patch.object(
                native, "_protected_bytes", return_value=b"sdk" if fault != "sdk" else b"changed"
            )
        )
        stack.enter_context(patch.object(r.time, "monotonic", return_value=100.0))
        boot = "12345678-1234-1234-1234-123456789abc"
        clock = stack.enter_context(
            patch.object(task, "reference_clock", return_value=(boot, 100.0))
        )
        if fault == "fresh_boot":
            clock.side_effect = [(boot, 100.0), ("87654321-1234-1234-1234-123456789abc", 100.0)]
        if fault == "fresh_back":
            clock.side_effect = [(boot, 100.0), (boot, 99.0)]
        if fault == "fresh_slow":
            clock.side_effect = [(boot, 100.0), (boot, 100.0), (boot, 103.0)]
        return r, book, value, pair_sha, native, producer, read

    def test_actual_owner_closes_then_fresh_then_exact_transition(self):
        r, book, value, pair_sha, native, producer, read = self.fixture()
        ref = r.reference_capture_condition(book, pair_sha, read, native, producer)
        attempt = book.begin(
            value["method_sha256"],
            now=101,
            reference_transition=ref,
            pre_dispatch=dispatch(book, value["capture_attempt"]),
            expected_connection=value["capture_attempt"],
        )
        self.assertEqual(attempt, value["capture_attempt"])
        book.enter(attempt, value["method_sha256"], "5" * 64)
        plan = dict(
            recovery={"connection_attempt_id": attempt},
            reference_pair_ref={"path": "/pair", "sha256": pair_sha},
            operation_context=value["capture_context"],
        )
        book.bind_reference_plan(attempt, plan, value, "5" * 64)
        book.may_connect(attempt)

    def test_transition_entry_context_and_missing_child_binding_refuse(self):
        r, book, value, pair_sha, native, producer, read = self.fixture()
        ref = r.reference_capture_condition(book, pair_sha, read, native, producer)
        attempt = book.begin(
            value["method_sha256"],
            now=101,
            reference_transition=ref,
            pre_dispatch=dispatch(book, value["capture_attempt"]),
            expected_connection=value["capture_attempt"],
        )
        startup = "5" * 64
        book.enter(attempt, value["method_sha256"], startup)
        plan = dict(
            recovery={"connection_attempt_id": attempt},
            reference_pair_ref={"path": "/pair", "sha256": pair_sha},
            operation_context=value["capture_context"],
        )
        with self.assertRaises(ValueError):
            book.may_connect(attempt)
        book.bind_reference_plan(attempt, plan, value, startup)
        for field in ("operation_context", "reference_pair_ref"):
            changed = copy.deepcopy(plan)
            changed[field] = "wrong"
            with self.subTest(field=field), self.assertRaises((ValueError, TypeError)):
                book.require_reference_plan(attempt, changed, value)
        book.require_reference_plan(attempt, plan, value)
        book.may_connect(attempt)

    def test_positive_after_controller_crash_cannot_be_replayed(self):
        r, book, value, pair_sha, native, producer, read = self.fixture()
        ref = r.reference_capture_condition(book, pair_sha, read, native, producer)
        book._claim_lease = None
        with self.assertRaisesRegex(ValueError, "reference_transition_owner"):
            book.begin(
                value["method_sha256"],
                now=101,
                reference_transition=ref,
                pre_dispatch=dispatch(book, value["capture_attempt"]),
                expected_connection=value["capture_attempt"],
            )
        self.assertNotIn(value["capture_attempt"] + ".intent.json", book.rows)

    def test_positive_same_controller_new_claim_lease_cannot_replay(self):
        r, book, value, pair_sha, native, producer, read = self.fixture()
        ref = r.reference_capture_condition(book, pair_sha, read, native, producer)
        prior = book._claim_lease
        book._claim_lease = r._RecoveryLease(prior.fd)
        book._claim_lease.controller = prior.controller
        book._claim_lease.origin = prior.origin
        with self.assertRaises(FileExistsError):
            book.claim_reference_condition(pair_sha)
        with self.assertRaisesRegex(ValueError, "reference_transition_owner"):
            book.begin(
                value["method_sha256"],
                now=101,
                reference_transition=ref,
                pre_dispatch=dispatch(book, value["capture_attempt"]),
                expected_connection=value["capture_attempt"],
            )

    def test_missing_pair_original_consumes_condition(self):
        r, book, value, pair_sha, native, producer, read = self.fixture()
        del book.rows[value["reference_attempt"] + ".reference-pair.json"]
        with self.assertRaises(FileNotFoundError):
            r.reference_capture_condition(book, pair_sha, read, native, producer)
        self.assertIn(value["reference_attempt"] + ".reference-claim.json", book.rows)
        with self.assertRaises(FileExistsError):
            r.reference_capture_condition(book, pair_sha, read, native, producer)

    def test_child_may_requires_original_carrier_identity(self):
        r, book, value, pair_sha, native, producer, read = self.fixture()
        ref = r.reference_capture_condition(book, pair_sha, read, native, producer)
        attempt = book.begin(
            value["method_sha256"],
            now=101,
            reference_transition=ref,
            pre_dispatch=dispatch(book, value["capture_attempt"]),
            expected_connection=value["capture_attempt"],
        )
        book.enter(attempt, value["method_sha256"], "5" * 64)
        plan = dict(
            recovery={"connection_attempt_id": attempt},
            reference_pair_ref={"path": "/pair", "sha256": pair_sha},
            operation_context=value["capture_context"],
        )
        book.bind_reference_plan(attempt, plan, value, "5" * 64)
        with patch.object(r, "_controller_actor", side_effect=FileNotFoundError):
            with self.assertRaises(ValueError):
                book.may_connect(attempt)
        self.assertNotIn(attempt + ".may.json", book.rows)

    def test_child_may_requires_original_fd_lock_with_unchanged_controller(self):
        r, book, value, pair_sha, native, producer, read = self.fixture()
        ref = r.reference_capture_condition(book, pair_sha, read, native, producer)
        attempt = book.begin(
            value["method_sha256"],
            now=101,
            reference_transition=ref,
            pre_dispatch=dispatch(book, value["capture_attempt"]),
            expected_connection=value["capture_attempt"],
        )
        book.enter(attempt, value["method_sha256"], "5" * 64)
        plan = dict(
            recovery={"connection_attempt_id": attempt},
            reference_pair_ref={"path": "/pair", "sha256": pair_sha},
            operation_context=value["capture_context"],
        )
        book.bind_reference_plan(attempt, plan, value, "5" * 64)
        for raw in (
            b"pos:\t0\n",
            b"x" * 4097,
            b"lock:\t1: POSIX ADVISORY WRITE 222 00:01:2 0 EOF\n",
            b"lock:\t1: FLOCK ADVISORY WRITE 333 00:01:2 0 EOF\n",
            b"lock:\t1: FLOCK ADVISORY WRITE 222 00:01:3 0 EOF\n",
        ):
            with (
                self.subTest(fdinfo=raw[:70]),
                patch.object(r.Path, "open", side_effect=lambda *a, **k: io.BytesIO(raw)),
            ):
                with self.assertRaises(ValueError):
                    book.may_connect(attempt)
                self.assertNotIn(attempt + ".may.json", book.rows)

    def test_sandbox_child_rechecks_transition_through_existing_authenticated_session(self):
        r, book, value, pair_sha, native, producer, read = self.fixture()
        ref = r.reference_capture_condition(book, pair_sha, read, native, producer)
        attempt = book.begin(
            value["method_sha256"],
            now=101,
            reference_transition=ref,
            pre_dispatch=dispatch(book, value["capture_attempt"]),
            expected_connection=value["capture_attempt"],
        )
        book.enter(attempt, value["method_sha256"], "5" * 64)
        plan = dict(
            recovery={"connection_attempt_id": attempt},
            reference_pair_ref={"path": "/pair", "sha256": pair_sha},
            operation_context=value["capture_context"],
        )
        book.bind_reference_plan(attempt, plan, value, "5" * 64)
        parent_book = book
        child = MemoryLedger(book.root)
        child.rows = book.rows
        calls = []

        class Channel:
            def send(self, packet):
                calls.append(packet)

            def recv(self, parent):
                self_case.assertEqual(parent, 444)
                reply = r._reference_observation(
                    dict(_recovery_ledger=parent_book, _recovery_method=value["method_sha256"]),
                    attempt,
                    calls[-1]["reference_transition"],
                )
                return dict(snapshot={}, reference_transition=reply)

        self_case = self
        session = r._ChildSession(Channel(), 444, lambda: {})
        child._reference_live_owner = lambda attempted, claim, owner: session.reference_owner(
            child, attempted, claim, owner
        )
        # Actual parent's clock is accessible; the sandbox child must not call
        # the ledger's local procfs clock. The owner hook is the only IPC seam.
        with patch.object(
            task,
            "reference_clock",
            side_effect=[("12345678-1234-1234-1234-123456789abc", 100.0)] * 4,
        ):
            child.may_connect(attempt)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["reference_transition"], ref)
        self.assertIn(attempt + ".may.json", book.rows)

    def test_fresh_boot_age_and_child_outcome_drift_refuse(self):
        for fault in ("boot", "age", "outcome", "missing_ref"):
            with self.subTest(fault=fault):
                r, book, value, pair_sha, native, producer, read = self.fixture()
                ref = r.reference_capture_condition(book, pair_sha, read, native, producer)
                attempt = book.begin(
                    value["method_sha256"],
                    now=101,
                    reference_transition=ref,
                    pre_dispatch=dispatch(book, value["capture_attempt"]),
                    expected_connection=value["capture_attempt"],
                )
                book.enter(attempt, value["method_sha256"], "5" * 64)
                plan = dict(
                    recovery={"connection_attempt_id": attempt},
                    reference_pair_ref={"path": "/pair", "sha256": pair_sha},
                    operation_context=value["capture_context"],
                )
                book.bind_reference_plan(attempt, plan, value, "5" * 64)
                if fault == "boot":
                    task.reference_clock.return_value = (
                        "87654321-1234-1234-1234-123456789abc",
                        100.0,
                    )
                if fault == "age":
                    task.reference_clock.return_value = (
                        "12345678-1234-1234-1234-123456789abc",
                        281.0,
                    )
                if fault == "outcome":
                    book.rows[value["reference_attempt"] + ".reference-condition.json"]["state"] = (
                        "NEGATIVE"
                    )
                if fault == "missing_ref":
                    del book.rows[attempt + ".intent.json"]["reference_transition"]
                with self.assertRaises(ValueError):
                    book.may_connect(attempt)
                self.assertNotIn(attempt + ".may.json", book.rows)
                self.fixture_stack.close()

    def test_actual_owner_negative_is_spent_without_second_intent(self):
        for fault in (
            "not_ready",
            "not_returned",
            "sdk_close",
            "manager",
            "client",
            "terminal",
            "cleanup",
            "unknown_close",
            "source",
            "provider",
            "provider_close",
            "sdk",
            "first_context",
            "first_startup",
            "invocation",
            "unit_active",
            "provider_namespace",
            "fresh_boot",
            "fresh_back",
            "fresh_slow",
        ):
            with self.subTest(fault=fault):
                r, book, value, pair_sha, native, producer, read = self.fixture(fault)
                with self.assertRaises(Exception):
                    r.reference_capture_condition(book, pair_sha, read, native, producer)
                self.assertIn(value["reference_attempt"] + ".reference-claim.json", book.rows)
                self.assertNotIn(value["capture_attempt"] + ".intent.json", book.rows)
                with self.assertRaises(FileExistsError):
                    r.reference_capture_condition(book, pair_sha, read, native, producer)
                self.fixture_stack.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
