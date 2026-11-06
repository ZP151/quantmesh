"""Original, one-effect Linux IVV trusted-external-environment parent and capture child.

Invoke the protected release with its installed interpreter, -I -S -B, and the
independently pinned digest of the staged startup reference file. No arbitrary
PID, cgroup, control descriptor, executable, callback or shell command is input.
"""

import contextlib
import ctypes
import functools
import hashlib
import importlib.machinery
import importlib.util
import json
import os
import re
import select
import signal
import socket
import stat
import subprocess
import sys
import time
import types
from pathlib import Path, PosixPath, PurePosixPath, WindowsPath

BASE = Path("/var/lib/quantmesh/ivv-trusted-environment")
CONTROL = BASE / "parent"
CHILD = BASE / "child"
RECEIPT = CHILD / "capture"
LEDGER = Path("/var/lib/quantmesh/ivv-capture-once")
RELEASE = Path(__file__).parent
SDK = Path(
    "/opt/quantmesh/releases/69515b79d2bc67303bfef9dee660dbca9bef41e3/.venv/lib/python3.12/site-packages"
)
FAMILY = ".dev-trusted-environment.v1"
AUTH = "3fede456cf8fff2e4ee29748fa6037617fe250d382c8b09474e1f6be4fe7e452"
ASSURANCE = "UNVERIFIED_TRUSTED_EXTERNAL"
CG = Path("/sys/fs/cgroup")
LIMITS = {
    "memory.max": "536870912",
    "memory.swap.max": "0",
    "cpu.max": "50000 100000",
    "pids.max": "32",
}
SOURCES = {
    "capture_helper_sha256": "capture_opend_ivv_daily.py",
    "dev_issuer_sha256": "ivv_dev_diagnostic.py",
    "dev_native_sha256": "ivv_dev_native.py",
    "native_producer_sha256": "ivv_native_producer.py",
    "trusted_runner_sha256": "ivv_trusted_runner.py",
}


ADDITIONAL_ROOT = Path("/var/lib/quantmesh-ivv-additional")


def _recovery_mode(mode):
    return type(mode) is str and re.fullmatch(r"connection-[0-9]{6}", mode) is not None


def _task_mode(values):
    return values.get("_recovery_mode", values.get("_additional") is not None)


def _locations(additional):
    if _recovery_mode(additional):
        root = Path("/var/lib/quantmesh-ivv-recovery")
        base = root / "attempts" / additional
        return types.SimpleNamespace(
            control=base / "parent",
            child=base / "child",
            receipt=base / "child/capture",
            ledger=root / "ledger",
            release=base / "release",
        )
    if additional:
        base = ADDITIONAL_ROOT / "tasks/20261103-01"
        return types.SimpleNamespace(
            control=base / "parent",
            child=base / "child",
            receipt=base / "child/capture",
            ledger=ADDITIONAL_ROOT / "once",
            release=base / "release",
        )
    return types.SimpleNamespace(
        control=CONTROL, child=CHILD, receipt=RECEIPT, ledger=LEDGER, release=RELEASE
    )


def _sources(additional):
    if _recovery_mode(additional):
        return {
            **SOURCES,
            "additional_task_sha256": "ivv_additional_task.py",
            "recovery_contract_sha256": "ivv_recovery.py",
        }
    return (
        {**SOURCES, "additional_task_sha256": "ivv_additional_task.py"} if additional else SOURCES
    )


def _for_task(fn, additional):
    # Preserve the existing trusted entry and the shape of its syscall seams.
    return functools.partial(fn, additional=additional) if additional else fn


class Refused(ValueError):
    pass


class _Handles(contextlib.ExitStack):
    """Close every retained handle; never let a later close erase earlier facts."""

    def __init__(self):
        super().__init__()
        self.errors = []

    def callback(self, callback, *args, **kwargs):
        def close():
            try:
                callback(*args, **kwargs)
            except BaseException as error:
                self.errors.append("CLOSE_" + reason(error))

        return super().callback(close)


def need(ok, code, *, _origin=None):
    if not ok:
        if _origin is not None:
            _origin["outcome"] = "FIRST_FALSE"
        raise Refused(code)


def reason(e):
    if (
        isinstance(e, (ValueError, RuntimeError))
        and len(e.args) == 1
        and isinstance(e.args[0], str)
        and re.fullmatch(r"[A-Za-z0-9_+]{1,256}", e.args[0])
    ):
        return e.args[0]
    return type(e).__name__


def _public_executable_path(value):
    return (
        type(value) is str
        and len(value) <= 160
        and re.fullmatch(
            r"/usr/(?:bin|sbin|libexec|local/bin)/[A-Za-z0-9_+./-]+(?: \(deleted\))?", value
        )
        is not None
        and all(part not in ("", ".", "..") for part in value.split("/")[1:])
    )


def select_executable_path(value):
    need(
        type(value) is dict
        and set(value) == {"classification", "path"}
        and type(value["classification"]) is str,
        "EXECUTABLE_OBSERVATION_SHAPE",
    )
    kind, path = value["classification"], value["path"]
    fixed = {
        "EXPECTED": "/usr/bin/python3.12",
        "EXPECTED_DELETED": "/usr/bin/python3.12 (deleted)",
    }
    need(
        (kind in fixed and type(path) is str and path == fixed[kind])
        or (kind in ("PROC_EXE", "REDACTED") and path is None)
        or (
            kind == "OTHER_PUBLIC" and _public_executable_path(path) and path not in fixed.values()
        ),
        "EXECUTABLE_OBSERVATION_SHAPE",
    )
    return {"classification": kind, "path": path}


def select_executable_observation(value):
    need(
        type(value) is dict
        and set(value) == {"schema", "nonstrict", "readlink", "strict", "namespace"}
        and type(value["schema"]) is str
        and value["schema"] == "qm.ivv.executable-observation.v1"
        and type(value["namespace"]) is str
        and value["namespace"] in ("SAME", "CHANGED", "UNAVAILABLE"),
        "EXECUTABLE_OBSERVATION_SHAPE",
    )
    result = {
        "schema": value["schema"],
        "namespace": value["namespace"],
        "nonstrict": select_executable_path(value["nonstrict"]),
    }
    for name in ("readlink", "strict"):
        item = value[name]
        need(
            type(item) is dict
            and set(item) == {"status", "result"}
            and type(item["status"]) is str,
            "EXECUTABLE_OBSERVATION_SHAPE",
        )
        if item["status"] == "OK":
            selected = select_executable_path(item["result"])
        else:
            need(
                item["status"]
                in (
                    "EACCES",
                    "EPERM",
                    "ENOENT",
                    "ELOOP",
                    "ENOTDIR",
                    "OTHER_OSERROR",
                    "OTHER_EXCEPTION",
                )
                and item["result"] is None,
                "EXECUTABLE_OBSERVATION_SHAPE",
            )
            selected = None
        result[name] = {"status": item["status"], "result": selected}
    return result


def _executable_path(value):
    # Never call user-defined stringification. Only exact stdlib path/string values.
    if type(value) in (PosixPath, WindowsPath, PurePosixPath):
        value = str(value)
    kind, public = "REDACTED", None
    if type(value) is str:
        if value == "/usr/bin/python3.12":
            kind, public = "EXPECTED", value
        elif value == "/usr/bin/python3.12 (deleted)":
            kind, public = "EXPECTED_DELETED", value
        elif re.fullmatch(r"/proc/(?:self|[0-9]{1,20})/exe", value):
            kind = "PROC_EXE"
        elif _public_executable_path(value):
            kind, public = "OTHER_PUBLIC", value
    return {"classification": kind, "path": public}


def _observe_executable(resolved, namespace):
    def inode():
        try:
            value = os.stat("/proc/self/ns/mnt").st_ino
            return value if type(value) is int and value > 0 else None
        except BaseException:
            return None

    def lookup(operation):
        try:
            return {"status": "OK", "result": _executable_path(operation())}
        except BaseException as error:
            status = "OTHER_EXCEPTION"
            if isinstance(error, OSError):
                number = OSError.errno.__get__(error, OSError)
                known = {13: "EACCES", 1: "EPERM", 2: "ENOENT", 40: "ELOOP", 20: "ENOTDIR"}
                status = (
                    known.get(number, "OTHER_OSERROR") if type(number) is int else "OTHER_OSERROR"
                )
            return {"status": status, "result": None}

    before = inode()
    result = {
        "schema": "qm.ivv.executable-observation.v1",
        "nonstrict": _executable_path(resolved),
        "readlink": lookup(lambda: os.readlink("/proc/self/exe")),
        "strict": lookup(lambda: Path("/proc/self/exe").resolve(strict=True)),
    }
    after = inode()
    result["namespace"] = (
        "UNAVAILABLE"
        if before is None or after is None
        else "SAME"
        if before == after == namespace
        else "CHANGED"
    )
    return select_executable_observation(result)


def select_executable_identity_failure(value):
    need(
        type(value) is dict
        and set(value) == {"schema", "stage", "descriptor_close"}
        and value["schema"] == "qm.ivv.executable-identity-failure.v1"
        and type(value["stage"]) is str
        and value["stage"]
        in (
            "CATALOG",
            "NAMESPACE",
            "NAMED_PATH",
            "NAMED_OPEN",
            "NAMED_METADATA",
            "NAMED_READONLY",
            "NAMED_BINDING",
            "KERNEL_OPEN",
            "KERNEL_METADATA",
            "ROLE_BINDING",
            "NAMED_BYTES",
            "FINAL_BINDING",
            "DESCRIPTOR_CLOSE",
            "INTERNAL",
        )
        and type(value["descriptor_close"]) is str
        and value["descriptor_close"] in ("CLOSED", "UNKNOWN"),
        "EXECUTABLE_IDENTITY_SHAPE",
    )
    return dict(value)


def select_executable_origin(value):
    need(
        type(value) is dict
        and set(value)
        == {
            "schema",
            "method",
            "phase",
            "python_sha256",
            "namespace_inode",
            "kernel_mount_readonly",
        }
        and value["schema"] == "qm.ivv.executable-origin.v1"
        and type(value["method"]) is str
        and value["method"] in ("EXACT_PATH", "NAMED_OBJECT")
        and type(value["phase"]) is str
        and value["phase"] in ("INITIAL", "SESSION", "UNKNOWN")
        and type(value["python_sha256"]) is str
        and re.fullmatch("[0-9a-f]{64}", value["python_sha256"])
        and type(value["namespace_inode"]) is int
        and 0 < value["namespace_inode"] < 2**64
        and (
            type(value["kernel_mount_readonly"]) is bool
            or type(value["kernel_mount_readonly"]) is str
            and value["kernel_mount_readonly"] == "UNKNOWN"
        )
        and (value["method"] != "EXACT_PATH" or value["kernel_mount_readonly"] == "UNKNOWN"),
        "EXECUTABLE_ORIGIN_SHAPE",
    )
    return dict(value)


def _carry_executable_origin(error, value):
    try:
        storage = _exception_storage(error)
        if storage is not None:
            # A reused exception must not attribute another call's relationship.
            storage.pop("_qm_executable_owner", None)
            storage.pop("_qm_executable_origin", None)
            if value is not None:
                selected = select_executable_origin(value)
                storage["_qm_executable_origin"] = selected
                storage["_qm_executable_owner"] = _EXECUTABLE_MARKER
    except BaseException:
        pass
    return error


def _executable_from_error(error):
    try:
        storage = _exception_storage(error)
        if storage is not None and storage.get("_qm_executable_owner") is _EXECUTABLE_MARKER:
            return select_executable_origin(storage.get("_qm_executable_origin"))
    except BaseException:
        pass
    return None


def _prove_executable_identity(expected_sha256, namespace):
    # Only the named public role supplies bytes. O_PATH follows the one fixed
    # kernel magic link without granting a read or relying on its pathname.
    named = Path("/usr/bin/python3.12")
    held = []
    stage, failed, closed, kernel_ro = "CATALOG", None, True, "UNKNOWN"
    try:
        need(
            type(expected_sha256) is str and re.fullmatch("[0-9a-f]{64}", expected_sha256),
            "IDENTITY",
        )
        stage = "NAMESPACE"
        need(
            type(namespace) is int
            and namespace > 0
            and os.stat("/proc/self/ns/mnt").st_ino == namespace,
            "IDENTITY",
        )
        stage = "NAMED_PATH"
        protected(named)
        stage = "NAMED_OPEN"
        named_fd = os.open(named, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        held.append(named_fd)
        stage = "NAMED_METADATA"
        first = os.fstat(named_fd)
        need(
            stat.S_ISREG(first.st_mode)
            and first.st_uid == 0
            and first.st_nlink == 1
            and not first.st_mode & 0o022
            and 0 < first.st_size <= 32 * 1024 * 1024,
            "IDENTITY",
        )
        stage = "NAMED_READONLY"
        need(os.fstatvfs(named_fd).f_flag & os.ST_RDONLY, "IDENTITY")
        stage = "NAMED_BINDING"
        need(_file_stamp(first) == _file_stamp(os.stat(named, follow_symlinks=False)), "IDENTITY")
        stage = "KERNEL_OPEN"
        kernel_fd = os.open("/proc/self/exe", os.O_PATH | os.O_CLOEXEC)
        held.append(kernel_fd)
        stage = "KERNEL_METADATA"
        kernel = os.fstat(kernel_fd)
        need(
            stat.S_ISREG(kernel.st_mode)
            and kernel.st_uid == 0
            and kernel.st_nlink == 1
            and not kernel.st_mode & 0o022
            and 0 < kernel.st_size <= 32 * 1024 * 1024,
            "IDENTITY",
        )
        stage = "ROLE_BINDING"
        need(
            _file_stamp(first)
            == _file_stamp(kernel)
            == _file_stamp(os.fstat(named_fd))
            == _file_stamp(os.stat(named, follow_symlinks=False)),
            "IDENTITY",
        )
        need(os.stat("/proc/self/ns/mnt").st_ino == namespace, "IDENTITY")
        try:
            kernel_ro = bool(os.fstatvfs(kernel_fd).f_flag & os.ST_RDONLY)
        except BaseException:
            pass  # Direct FD_MOUNT_RO observation only; never infer a current-tree mount.
        stage = "NAMED_BYTES"
        raw = os.pread(named_fd, first.st_size + 1, 0)
        need(
            type(raw) is bytes and len(raw) == first.st_size and digest(raw) == expected_sha256,
            "IDENTITY",
        )
        stage = "FINAL_BINDING"
        need(
            _file_stamp(first)
            == _file_stamp(os.fstat(named_fd))
            == _file_stamp(os.fstat(kernel_fd))
            == _file_stamp(os.stat(named, follow_symlinks=False))
            and os.fstatvfs(named_fd).f_flag & os.ST_RDONLY
            and os.stat("/proc/self/ns/mnt").st_ino == namespace,
            "IDENTITY",
        )
    except BaseException:
        failed = stage
    finally:
        for fd in reversed(held):
            try:
                _close_fd(fd)
            except BaseException:
                closed = False  # Never retry/probe a possibly reused numeric descriptor.
    return {
        "stage": failed or ("VERIFIED" if closed else "DESCRIPTOR_CLOSE"),
        "descriptor_close": "CLOSED" if closed else "UNKNOWN",
        "kernel_mount_readonly": kernel_ro,
    }


def select_origin_failure(value):
    """Select only finite origin facts; absent legacy evidence remains absent."""
    if value is None:
        return None
    need(
        type(value) is dict
        and all(type(key) is str for key in value)
        and {"schema", "phase", "predicate", "outcome"}
        <= set(value)
        <= {
            "schema",
            "phase",
            "predicate",
            "outcome",
            "executable_observation",
            "executable_identity",
        }
        and all(type(value[key]) is str for key in ("schema", "phase", "predicate", "outcome"))
        and value["schema"] == "qm.ivv.runtime-origin-failure.v1"
        and value["phase"] in ("INITIAL", "SESSION", "UNKNOWN")
        and value["predicate"] in ("SDK_ROOT", "PYTHON_VERSION", "EXECUTABLE", "UNKNOWN")
        and value["outcome"] in ("FIRST_FALSE", "EXCEPTION", "UNKNOWN")
        and ((value["predicate"] == "UNKNOWN") == (value["outcome"] == "UNKNOWN")),
        "ORIGIN_FAILURE_SHAPE",
    )
    result = {key: value[key] for key in ("schema", "phase", "predicate", "outcome")}
    if "executable_observation" in value:
        need(
            value["predicate"] == "EXECUTABLE" and value["outcome"] == "FIRST_FALSE",
            "EXECUTABLE_OBSERVATION_SHAPE",
        )
        result["executable_observation"] = select_executable_observation(
            value["executable_observation"]
        )
    if "executable_identity" in value:
        need(
            value["predicate"] == "EXECUTABLE" and value["outcome"] == "FIRST_FALSE",
            "EXECUTABLE_IDENTITY_SHAPE",
        )
        result["executable_identity"] = select_executable_identity_failure(
            value["executable_identity"]
        )
    return result


_ORIGIN_MARKER = object()
_EXECUTABLE_MARKER = object()
_EXCEPTION_DICT = BaseException.__dict__.get("__dict__")


def _exception_storage(error):
    # Invoke the built-in descriptor directly, never a subclass hook/property.
    try:
        value = _EXCEPTION_DICT.__get__(error, BaseException)
        return value if type(value) is dict and all(type(key) is str for key in value) else None
    except BaseException:
        return None


def _origin_from_error(error):
    try:
        storage = _exception_storage(error)
        if storage is None or storage.get("_qm_origin_owner") is not _ORIGIN_MARKER:
            return None
        return select_origin_failure(storage.get("_qm_origin_failure"))
    except BaseException:
        return None


def _carry_origin(error, value, code=None):
    # Optional diagnostics must never replace the original exception object.
    try:
        storage = _exception_storage(error)
        selected = select_origin_failure(value)
        if storage is not None and selected is not None:
            storage["_qm_origin_owner"] = None
            storage["_qm_origin_failure"] = selected
            storage["_qm_origin_code"] = code
            storage["_qm_origin_owner"] = _ORIGIN_MARKER
    except BaseException:
        pass
    return error


def _failure_code(error):
    origin = _origin_from_error(error)
    if origin is None or origin["outcome"] != "EXCEPTION":
        return reason(error)
    storage = _exception_storage(error)
    forwarded = storage.get("_qm_origin_code") if storage is not None else None
    if type(forwarded) is str and re.fullmatch("[A-Za-z0-9_+]{1,256}", forwarded):
        return forwarded
    if type(error) is Refused and error.args == ("RUNTIME_ORIGIN",):
        return "RUNTIME_ORIGIN"
    kinds = (
        KeyError,
        IndexError,
        AttributeError,
        TypeError,
        ValueError,
        RuntimeError,
        OSError,
        PermissionError,
        FileNotFoundError,
        OverflowError,
    )
    for kind in kinds:
        if type(error) is kind:
            return kind.__name__
    return "ORIGIN_EVALUATION_EXCEPTION"


def _capture_refusal_codes():
    # Frozen literals from owning runtime/channel and capture/held/provider guards.
    return {
        "Refused": (
            "CHILD_WRITE_MOUNTS",
            "CONTROL_DIGEST",
            "CONTROL_EOF",
            "CONTROL_FD_SWAPPED",
            "CONTROL_METADATA",
            "CONTROL_OWNERSHIP",
            "CONTROL_PATH_ALIAS",
            "CONTROL_RACE",
            "CONTROL_REF",
            "CONTROL_SEND",
            "CONTROL_SENDER",
            "EXECUTABLE_IDENTITY_SHAPE",
            "EXECUTABLE_OBSERVATION_SHAPE",
            "EXECUTABLE_ORIGIN_SHAPE",
            "HOME_LOG_PREREQUISITE",
            "HOME_NOT_READY",
            "IDENTITY",
            "ORIGIN_FAILURE_SHAPE",
            "OWN_NAMESPACE_DRIFT",
            "PROTO_AND_QUOTE_ORIGIN",
            "PYTHON_EXECUTABLE",
            "PYTHON_SEARCH_PATH",
            "PYTHON_SEARCH_WRITABLE",
            "RUNTIME_ORIGIN",
            "SDK_IMPORT_ORIGIN",
            "SDK_PINS_COUNT",
            "SDK_PIN_DRIFT",
            "SDK_PIN_ROLE",
            "SESSION_OWNER",
            "SOURCE_WRITABLE",
        ),
        "CaptureRejected": (
            "second_context",
            "second_initialization",
            "request_budget_or_order",
            "fixed_request_parameters",
            "request_wire_binding",
            "control_wire_budget",
            "unregistered_or_duplicate_send",
            "data_asof_stale",
            "absolute_deadline",
            "action_coverage_not_proven_before_price",
            "action_flag_missing",
            "additional_provenance",
            "ambiguous_or_unmatched_cash",
            "ambiguous_rehab_event",
            "capture_dates",
            "capture_incomplete",
            "cash_amount_or_pay_conflict",
            "cash_currency_conflict",
            "cash_currency_missing",
            "cash_currency_or_amount_ambiguous",
            "cash_statement_missing",
            "cash_sum_nonfinite",
            "clock_binding",
            "daily_timestamp_unsupported",
            "date_invalid",
            "date_missing",
            "dev_monitor_stale",
            "dev_monitor_threshold",
            "dev_native_binding",
            "dev_native_session_binding",
            "dev_provenance",
            "dev_provider_resources",
            "duplicate_json_key",
            "effect_id_invalid",
            "encrypted_transport_not_prepared_no_downgrade",
            "field_presence_mismatch",
            "fixed_scope_or_authority",
            "foreign_sdk_connection",
            "fresh_capture_capacity",
            "history_page_incomplete",
            "history_quota_unproved",
            "instrument_metadata",
            "init_observation_binding",
            "invalid_json",
            "json_object_required",
            "metadata_clock_age",
            "native_actor_lifetime",
            "native_cgroup_v2",
            "native_cpu",
            "native_memory_swap",
            "native_tasks",
            "native_unit_binding",
            "noncanonical_input",
            "nonfinite_json",
            "normal_close_deadline",
            "normal_close_not_proven",
            "numeric_missing_or_nonfinite",
            "numeric_out_of_range",
            "original_endpoint_binding",
            "protobuf_not_initialized",
            "protobuf_scalar_type",
            "provider_original_bound",
            "provider_ret_error",
            "provider_rows_shape",
            "provider_version_metadata",
            "quota_metadata_shape",
            "quota_shape",
            "quote_not_logged_in",
            "raw_fields_missing",
            "receipt_byte_bound",
            "receipt_name",
            "receipt_parent_alias",
            "receipt_short_write",
            "recovery_provenance",
            "release_source_binding",
            "response_asset_mismatch",
            "response_request_binding",
            "root_control_file",
            "root_control_sha_or_lifetime",
            "root_permit_fd_required",
            "root_ref_alias",
            "root_ref_file",
            "root_ref_sha_or_lifetime",
            "root_ref_shape",
            "sdk_import_origin",
            "sdk_initial_connection_failed",
            "sdk_log_directory_not_ready",
            "sdk_pack_failed",
            "sdk_preloaded_before_intent",
            "second_network_manager",
            "single_instrument_metadata",
            "spent_capture_root",
            "split_terminal_presence",
            "trusted_external_boundary",
            "unapproved_endpoint",
            "unapproved_query_processor",
            "unregistered_or_duplicate_send",
            "unsupported_action",
            "unsupported_split",
            "wire_header",
        ),
    }


def _capture_lifecycle_contract():
    returns = {"UNOBSERVED", "OK", "NON_OK", "RAISED", "UNKNOWN"}
    return {
        "init": {
            "send": returns,
            "packet_err": {
                "UNOBSERVED",
                "Ok",
                "Timeout",
                "Invalid",
                "Disconnect",
                "SendFail",
                "UNKNOWN",
            },
            "unpack": returns,
            "constructor_status": {
                "UNOBSERVED",
                "START",
                "CONNECTING",
                "CONNECTED",
                "READY",
                "CLOSING",
                "CLOSED",
                "WAIT_RECONNECT",
                "UNKNOWN",
            },
        },
        "phase": {
            "UNKNOWN",
            "ENTRY_GUARD",
            "MAY_CONNECT",
            "SDK_LOAD",
            "CONTEXT_RESERVE_GUARD",
            "BASE_LOOKUP",
            "SUBCLASS",
            "CONFIG",
            "ALLOCATE",
            "CTOR_ARGUMENTS",
            "CONSTRUCTOR",
            "INIT_CONNECT",
            "READY_CHECK",
            "BUSINESS",
            "FINAL_GUARD",
            "SDK_CLOSE",
            "STATUS_WAIT",
            "CALLBACK_JOIN",
            "CONNECTION_CHECK",
            "WIRE_RESTORE",
            "LOG_CLOSE",
            "EVIDENCE",
        },
        "guard": {
            "NOT_APPLICABLE",
            "HELD_STAMP",
            "HELD_JSON",
            "PLAN",
            "NATIVE_ACTOR",
            "CGROUP",
            "SPACE",
            "CONTROL_REFS",
            "PROVIDER_SESSION",
        },
        "type": {
            "UNKNOWN",
            "OTHER",
            "CaptureRejected",
            "Refused",
            "Exception",
            "ValueError",
            "TypeError",
            "AttributeError",
            "KeyError",
            "RuntimeError",
            "OSError",
            "PermissionError",
            "FileNotFoundError",
            "TimeoutError",
            "MemoryError",
            "KeyboardInterrupt",
            "AssertionError",
            "BlockingIOError",
            "BrokenPipeError",
            "ConnectionAbortedError",
            "ConnectionRefusedError",
            "ConnectionResetError",
            "InterruptedError",
        },
        "code": {
            "UNKNOWN",
            *_capture_refusal_codes()["Refused"],
            *_capture_refusal_codes()["CaptureRejected"],
        },
        "errno": {1, 2, 4, 5, 9, 11, 12, 13, 22, 24, 28, 32, 103, 104, 110, 111},
    }


def classify_capture_exception(error, helper_refusal):
    """Only exact built-ins and authenticated owning refusal classes; no user hooks."""
    contract = _capture_lifecycle_contract()
    classes = (
        Exception,
        ValueError,
        TypeError,
        AttributeError,
        KeyError,
        RuntimeError,
        OSError,
        PermissionError,
        FileNotFoundError,
        TimeoutError,
        MemoryError,
        KeyboardInterrupt,
        AssertionError,
        BlockingIOError,
        BrokenPipeError,
        ConnectionAbortedError,
        ConnectionRefusedError,
        ConnectionResetError,
        InterruptedError,
    )
    cls = type(error)
    kind = next((item.__name__ for item in classes if cls is item), "OTHER")
    code, number = "UNKNOWN", None
    if cls is Refused or cls is helper_refusal:
        kind = "Refused" if cls is Refused else "CaptureRejected"
        args = BaseException.args.__get__(error, BaseException)
        if len(args) == 1 and type(args[0]) is str and args[0] in _capture_refusal_codes()[kind]:
            code = args[0]
    if any(
        cls is item
        for item in (
            OSError,
            PermissionError,
            FileNotFoundError,
            TimeoutError,
            BlockingIOError,
            BrokenPipeError,
            ConnectionAbortedError,
            ConnectionRefusedError,
            ConnectionResetError,
            InterruptedError,
        )
    ):
        candidate = OSError.errno.__get__(error, OSError)
        if type(candidate) is int and candidate in contract["errno"]:
            number = candidate
    return {"type": kind, "code": code, "errno": number}


def select_capture_lifecycle(value):
    contract = _capture_lifecycle_contract()
    need(
        type(value) is dict
        and set(value) - {"init_observation", "receive_trace"}
        == {
            "schema",
            "primary",
            "close",
            "ctx_assigned",
            "constructor_returned",
            "evidence_kind",
            "normal_close",
        },
        "CAPTURE_LIFECYCLE_SHAPE",
    )
    need(
        value["schema"] == "qm.ivv.capture-lifecycle.v1"
        and type(value["ctx_assigned"]) is bool
        and type(value["constructor_returned"]) is bool
        and value["evidence_kind"] in ("DEFAULT", "OBSERVED"),
        "CAPTURE_LIFECYCLE_SHAPE",
    )
    result = {
        k: value[k] for k in ("schema", "ctx_assigned", "constructor_returned", "evidence_kind")
    }
    for role in ("primary", "close"):
        item = value[role]
        if item is not None:
            need(
                type(item) is dict and set(item) == {"phase", "guard", "type", "code", "errno"},
                "CAPTURE_LIFECYCLE_SHAPE",
            )
            for key in ("phase", "guard", "type", "code"):
                need(
                    type(item[key]) is str and item[key] in contract[key], "CAPTURE_LIFECYCLE_SHAPE"
                )
            need(
                item["errno"] is None
                or type(item["errno"]) is int
                and item["errno"] in contract["errno"],
                "CAPTURE_LIFECYCLE_SHAPE",
            )
            owner_codes = _capture_refusal_codes().get(item["type"], ())
            need(
                item["code"] == "UNKNOWN" or item["code"] in owner_codes, "CAPTURE_LIFECYCLE_SHAPE"
            )
            need(
                item["errno"] is None
                or item["type"]
                in {
                    "OSError",
                    "PermissionError",
                    "FileNotFoundError",
                    "TimeoutError",
                    "BlockingIOError",
                    "BrokenPipeError",
                    "ConnectionAbortedError",
                    "ConnectionRefusedError",
                    "ConnectionResetError",
                    "InterruptedError",
                },
                "CAPTURE_LIFECYCLE_SHAPE",
            )
        result[role] = None if item is None else dict(item)
    normal = value["normal_close"]
    need(
        type(normal) is dict
        and set(normal) == {"context_closed", "callbacks_stopped", "data_socket_closed"}
        and all(type(v) is bool for v in normal.values()),
        "CAPTURE_LIFECYCLE_SHAPE",
    )
    result["normal_close"] = dict(normal)
    if "init_observation" in value:
        init = value["init_observation"]
        fields = contract["init"]
        need(
            type(init) is dict
            and value["ctx_assigned"]
            and set(init) == {*fields, "ever_ready"}
            and type(init["ever_ready"]) is bool
            and all(type(init[k]) is str and init[k] in allowed for k, allowed in fields.items())
            and (init["packet_err"] == "UNOBSERVED" or init["send"] in ("OK", "UNKNOWN"))
            and (init["unpack"] == "UNOBSERVED" or init["packet_err"] == "Ok")
            and (not init["ever_ready"] or init["unpack"] in ("OK", "UNKNOWN")),
            "CAPTURE_LIFECYCLE_SHAPE",
        )
        result["init_observation"] = dict(init)
    if "receive_trace" in value:
        trace = value["receive_trace"]
        enums = {
            "tcp_progress": {"UNOBSERVED", "NONE", "PARTIAL", "FULL", "UNKNOWN"},
            "target_notify_err": contract["init"]["packet_err"],
            "notify_when": {"UNOBSERVED", "BEFORE_WAIT_END", "AFTER_WAIT_END", "UNKNOWN"},
            "network_thread": {"ALIVE", "DEAD", "UNKNOWN"},
        }
        errors = {
            "NONE",
            "OS_ERROR",
            "VALUE_ERROR",
            "TYPE_ERROR",
            "RUNTIME_ERROR",
            "MEMORY_ERROR",
            "OTHER",
            "UNKNOWN",
        }
        for field in ("callback_error", "loop_error", "read_error"):
            enums[field] = errors
        booleans = {
            "complete_candidate_seen",
            "target_candidate_seen",
            "scan_unknown",
            "wait_ended",
            "overflow",
            "recorder_error",
        }
        counts = {"polls", "dequeues", "read_events", "read_callbacks"}
        byte_fields = {"tcp_accepted", "tcp_pending", "read_bytes"}
        need(
            "init_observation" in result
            and type(trace) is dict
            and set(trace)
            == {"schema", "first_ms", "last_ms", *enums, *booleans, *counts, *byte_fields}
            and type(trace["schema"]) is str
            and trace["schema"] == "qm.ivv.init-receive-trace.v1"
            and all(type(trace[k]) is bool for k in booleans)
            and all(type(trace[k]) is int and 0 <= trace[k] <= 4096 for k in counts)
            and all(type(trace[k]) is str and trace[k] in allowed for k, allowed in enums.items())
            and type(trace["read_bytes"]) is int
            and 0 <= trace["read_bytes"] <= 2147483647
            and all(
                trace[k] is None or type(trace[k]) is int and 0 <= trace[k] <= 2147483647
                for k in ("tcp_accepted", "tcp_pending")
            ),
            "CAPTURE_LIFECYCLE_SHAPE",
        )
        phases = {"poll", "dequeue", "write", "read", "frame", "notify", "wait", "unpack"}
        for field in ("first_ms", "last_ms"):
            times = trace[field]
            need(
                type(times) is dict
                and set(times) == phases
                and all(t is None or type(t) is int and 0 <= t <= 480000 for t in times.values()),
                "CAPTURE_LIFECYCLE_SHAPE",
            )
        need(
            all(
                (trace["first_ms"][k] is None and trace["last_ms"][k] is None)
                or (
                    type(trace["first_ms"][k]) is int
                    and type(trace["last_ms"][k]) is int
                    and trace["first_ms"][k] <= trace["last_ms"][k]
                )
                for k in phases
            ),
            "CAPTURE_LIFECYCLE_SHAPE",
        )
        accepted, pending = trace["tcp_accepted"], trace["tcp_pending"]
        progress = trace["tcp_progress"]
        need(
            (
                (progress in ("UNKNOWN", "UNOBSERVED") and accepted is None and pending is None)
                or (progress == "NONE" and accepted == 0 and type(pending) is int and pending > 0)
                or (
                    progress == "PARTIAL"
                    and type(accepted) is int
                    and accepted > 0
                    and type(pending) is int
                    and pending > 0
                )
                or (progress == "FULL" and type(accepted) is int and accepted > 0 and pending == 0)
            )
            and (not trace["target_candidate_seen"] or trace["complete_candidate_seen"])
            and (trace["target_notify_err"] != "UNOBSERVED" or trace["notify_when"] == "UNOBSERVED")
            and (trace["target_notify_err"] == "UNOBSERVED" or trace["notify_when"] != "UNOBSERVED")
            and (trace["notify_when"] != "AFTER_WAIT_END" or trace["wait_ended"])
            and len(json.dumps(trace, sort_keys=True, separators=(",", ":")).encode()) <= 2048,
            "CAPTURE_LIFECYCLE_SHAPE",
        )
        result["receive_trace"] = {
            **trace,
            "first_ms": dict(trace["first_ms"]),
            "last_ms": dict(trace["last_ms"]),
        }
    return result


_CAPTURE_LIFECYCLE_MARK = object()


def _carry_capture_lifecycle(error, value):
    store = _exception_storage(error)
    if store is not None:
        store.pop("_qm_capture_lifecycle", None)
    if value is not None:
        try:
            selected = select_capture_lifecycle(value)
        except BaseException:
            return error  # Optional diagnostics never replace the original primary.
        store = _exception_storage(error)
        if store is not None:
            store["_qm_capture_lifecycle"] = (_CAPTURE_LIFECYCLE_MARK, selected)
    return error


def _capture_lifecycle_from_error(error):
    store = _exception_storage(error)
    item = store.get("_qm_capture_lifecycle") if store is not None else None
    if type(item) is tuple and len(item) == 2 and item[0] is _CAPTURE_LIFECYCLE_MARK:
        try:
            return select_capture_lifecycle(item[1])
        except BaseException:
            pass
    return None


def select_reference_observation(value):
    """Closed non-data STOP observation; parent closure never comes from child IPC."""
    need(
        type(value) is dict
        and set(value)
        == {
            "schema_id",
            "reference_control_sha256",
            "constructor_status",
            "operation_failed",
            "close_failed",
            "normal_close",
            "parent_closed",
        },
        "REFERENCE_OBSERVATION_SHAPE",
    )
    need(
        value["schema_id"] == "qm.ivv.reference-init-observation.v1"
        and type(value["reference_control_sha256"]) is str
        and re.fullmatch("[0-9a-f]{64}", value["reference_control_sha256"])
        and value["constructor_status"] in {"READY", "NOT_READY", "NOT_RETURNED"}
        and all(
            type(value[k]) is bool for k in ("operation_failed", "close_failed", "parent_closed")
        ),
        "REFERENCE_OBSERVATION_VALUE",
    )
    normal = value["normal_close"]
    need(
        type(normal) is dict
        and set(normal) == {"context_closed", "callbacks_stopped", "data_socket_closed"}
        and all(type(v) is bool for v in normal.values()),
        "REFERENCE_OBSERVATION_CLOSE",
    )
    need(
        not value["parent_closed"]
        or (
            not value["operation_failed"]
            and not value["close_failed"]
            and all(normal.values())
            and value["constructor_status"] != "NOT_RETURNED"
        ),
        "REFERENCE_OBSERVATION_PARENT",
    )
    return {**value, "normal_close": dict(normal)}


_REFERENCE_OBSERVATION_MARK = object()


def _carry_reference_observation(error, value):
    store = _exception_storage(error)
    if store is not None:
        store.pop("_qm_reference_observation", None)
    if value is not None:
        selected = select_reference_observation(value)
        if store is not None:
            store["_qm_reference_observation"] = (_REFERENCE_OBSERVATION_MARK, selected)
    return error


def _reference_from_error(error):
    store = _exception_storage(error)
    item = store.get("_qm_reference_observation") if store is not None else None
    if type(item) is tuple and len(item) == 2 and item[0] is _REFERENCE_OBSERVATION_MARK:
        return select_reference_observation(item[1])
    return None


def _failure_record(error):
    value = {"state": "STOP", "reason": _failure_code(error)}
    origin = _origin_from_error(error)
    if origin is not None:
        value["origin_failure"] = origin
    executable = _executable_from_error(error)
    if executable is not None:
        value["executable_origin"] = executable
    capture = _capture_lifecycle_from_error(error)
    if capture is not None:
        value["capture_lifecycle"] = capture
    reference = _reference_from_error(error)
    if reference is not None:
        value["reference_init_observation"] = reference
    return value


def _failed_packet(error):
    value = _failure_record(error)
    return {
        "op": "failed",
        "code": value["reason"],
        **{
            key: value[key]
            for key in (
                "origin_failure",
                "executable_origin",
                "capture_lifecycle",
                "reference_init_observation",
            )
            if key in value
        },
    }


def _child_failure(packet):
    if (
        type(packet) is not dict
        or packet.get("op") != "failed"
        or not {"op", "code"}
        <= set(packet)
        <= {
            "op",
            "code",
            "origin_failure",
            "executable_origin",
            "capture_lifecycle",
            "reference_init_observation",
        }
        or type(packet.get("code")) is not str
        or re.fullmatch("[A-Za-z0-9_+]{1,256}", packet["code"]) is None
    ):
        return Refused("CHILD_PROTOCOL")
    if "origin_failure" in packet:
        need(packet["origin_failure"] is not None, "ORIGIN_FAILURE_SHAPE")
    origin = select_origin_failure(packet.get("origin_failure"))
    error = _carry_origin(Refused(packet["code"]), origin, packet["code"])
    if "executable_origin" in packet:
        _carry_executable_origin(error, select_executable_origin(packet["executable_origin"]))
    if "capture_lifecycle" in packet:
        _carry_capture_lifecycle(error, select_capture_lifecycle(packet["capture_lifecycle"]))
    if "reference_init_observation" in packet:
        reference = select_reference_observation(packet["reference_init_observation"])
        need(reference["parent_closed"] is False, "REFERENCE_CHILD_OWNER")
        _carry_reference_observation(error, reference)
    return error


def read_runner_failure(control, read_owned):
    """Read the existing protected failure file with the caller's held reader."""
    path = control / "runner-failure.json"
    if not path.exists():
        return None
    data = read_owned(path, 4096)
    need(type(data) is bytes and 0 < len(data) <= 4096, "FAILURE_BOUND")

    def unique(pairs):
        value = {}
        for key, item in pairs:
            need(key not in value, "FAILURE_SHAPE")
            value[key] = item
        return value

    value = json.loads(data, object_pairs_hook=unique)
    need(
        type(value) is dict
        and {"state", "reason"}
        <= set(value)
        <= {
            "state",
            "reason",
            "origin_failure",
            "executable_origin",
            "capture_lifecycle",
            "reference_init_observation",
        }
        and value["state"] == "STOP"
        and type(value["reason"]) is str
        and re.fullmatch("[A-Za-z0-9_+]{1,256}", value["reason"]),
        "FAILURE_SHAPE",
    )
    result = {"state": "STOP", "reason": value["reason"]}
    if "origin_failure" in value:
        need(value["origin_failure"] is not None, "ORIGIN_FAILURE_SHAPE")
        result["origin_failure"] = select_origin_failure(value["origin_failure"])
    if "executable_origin" in value:
        result["executable_origin"] = select_executable_origin(value["executable_origin"])
    if "capture_lifecycle" in value:
        result["capture_lifecycle"] = select_capture_lifecycle(value["capture_lifecycle"])
    if "reference_init_observation" in value:
        result["reference_init_observation"] = select_reference_observation(
            value["reference_init_observation"]
        )
        need(
            not result["reference_init_observation"]["parent_closed"]
            or value["reason"] == "REFERENCE_INIT_OBSERVATION",
            "REFERENCE_STOP_BINDING",
        )
    return result


def select_failure_status(status, publication_sha256):
    """Select finite STOP facts, never infer usage from the origin phase."""
    need(
        type(status) is dict
        and status.get("state") == "STOP"
        and status.get("publication_sha256") == publication_sha256
        and status.get("stage")
        in (
            "PACKET",
            "STAGE_OWNED_ONLY",
            "RELEASED_ADDITIONAL_RUNNER_ONCE",
            "RELEASED_RECOVERY_ATTEMPT",
        )
        and status.get("automatic_retry") is False
        and status.get("provider_mutation") is False
        and "unit_returncode" in status
        and "reason" in status,
        "NATIVE_STOP_NOT_PROVEN",
    )
    stage, rc, code = status["stage"], status["unit_returncode"], status["reason"]
    need(rc is None or type(rc) is int and -255 <= rc <= 255, "NATIVE_STOP_NOT_PROVEN")
    if code is None and rc is not None:
        code = "UNIT_RETURN_" + str(rc).replace("-", "NEG_") if rc else "UNIT_NORMAL_SEAL_MISSING"
    need(type(code) is str and re.fullmatch("[A-Za-z0-9_+]{1,256}", code), "NATIVE_STOP_NOT_PROVEN")
    contexts = status.get("actual_contexts")
    if stage in ("RELEASED_ADDITIONAL_RUNNER_ONCE", "RELEASED_RECOVERY_ATTEMPT"):
        contexts = "UNKNOWN"
    else:
        need(rc is None and type(contexts) is int and contexts == 0, "NATIVE_STOP_NOT_PROVEN")
    result = {
        "state": "STOP",
        "reason": code,
        "stage": stage,
        "unit_returncode": rc,
        "actual_contexts": contexts,
        "publication_sha256": publication_sha256,
    }
    if "origin_failure" in status:
        need(status["origin_failure"] is not None, "ORIGIN_FAILURE_SHAPE")
        result["origin_failure"] = select_origin_failure(status["origin_failure"])
    if "executable_origin" in status:
        result["executable_origin"] = select_executable_origin(status["executable_origin"])
    if "capture_lifecycle" in status:
        result["capture_lifecycle"] = select_capture_lifecycle(status["capture_lifecycle"])
    if "reference_init_observation" in status:
        result["reference_init_observation"] = select_reference_observation(
            status["reference_init_observation"]
        )
        need(
            not result["reference_init_observation"]["parent_closed"]
            or (
                code == "REFERENCE_INIT_OBSERVATION"
                and rc == 1
                and stage == "RELEASED_RECOVERY_ATTEMPT"
            ),
            "REFERENCE_STOP_BINDING",
        )
    if "recovery_connection" in status:
        item = status["recovery_connection"]
        need(
            type(item) is dict
            and set(item) == {"requested", "next", "state"}
            and all(
                type(item[k]) is str and re.fullmatch(r"connection-[0-9]{6}", item[k])
                for k in ("requested", "next")
            )
            and item["state"] in ("UNCLAIMED", "CLAIMED", "COMPLETE"),
            "RECOVERY_RECONCILIATION",
        )
        result["recovery_connection"] = dict(item)
    return result


def raw_json(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return info.st_dev, info.st_ino, info.st_mode, info.st_uid


def _file_stamp(info):
    return (*identity(info), info.st_nlink, info.st_size, info.st_ctime_ns, info.st_mtime_ns)


def _close_fd(fd):
    primary = sys.exc_info()[1]
    try:
        os.close(fd)
    except BaseException as error:
        raise Refused(
            (reason(primary) + "+" if primary else "") + "FD_CLOSE_" + reason(error)
        ) from None


def protected(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve(strict=True) == path, "CONTROL_PATH_ALIAS")
    for parent in (path, *path.parents):
        s = parent.lstat()
        need(s.st_uid == 0 and not s.st_mode & 0o022, "CONTROL_OWNERSHIP")


def read_ref(ref, path, maximum=32768, readonly=False):
    need(
        type(ref) is dict
        and set(ref) == {"path", "sha256"}
        and ref["path"] == str(path)
        and isinstance(ref["sha256"], str)
        and re.fullmatch("[0-9a-f]{64}", ref["sha256"]),
        "CONTROL_REF",
    )
    protected(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        s = os.fstat(fd)
        need(
            stat.S_ISREG(s.st_mode)
            and s.st_nlink == 1
            and s.st_uid == 0
            and (not (s.st_mode & 0o022) if readonly else stat.S_IMODE(s.st_mode) == 0o444)
            and 0 < s.st_size <= maximum,
            "CONTROL_METADATA",
        )
        if readonly:
            need(os.fstatvfs(fd).f_flag & os.ST_RDONLY, "SOURCE_WRITABLE")
        raw = os.pread(fd, s.st_size + 1, 0)
        need(len(raw) == s.st_size and _file_stamp(s) == _file_stamp(os.fstat(fd)), "CONTROL_RACE")
        need(
            _file_stamp(s) == _file_stamp(os.stat(path, follow_symlinks=False))
            and digest(raw) == ref["sha256"],
            "CONTROL_DIGEST",
        )
        return raw
    finally:
        _close_fd(fd)


def put(path, obj):
    raw = raw_json(obj)
    need(0 < len(raw) <= 32768, "CONTROL_SIZE")
    protected(path.parent)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as out:
            out.write(raw)
            out.flush()
        os.fchmod(fd, 0o444)
        os.fsync(fd)
    finally:
        _close_fd(fd)
    _sync_dir(path.parent)
    return {"path": str(path), "sha256": digest(raw)}


def _sync_dir(path):
    d = os.open(path, os.O_DIRECTORY | os.O_RDONLY | os.O_NOFOLLOW)
    try:
        os.fsync(d)
    finally:
        _close_fd(d)


def _libcall(name, *args):
    libc = ctypes.CDLL(None, use_errno=True)
    if getattr(libc, name)(*args) != 0:
        raise OSError(ctypes.get_errno(), name)


def _private_mounts():
    protected(RELEASE)
    old = os.stat("/proc/self/ns/mnt").st_ino
    _libcall("unshare", 0x00020000)
    _libcall("mount", None, b"/", None, ctypes.c_ulong(0x40000 | 0x4000), None)
    new = os.stat("/proc/self/ns/mnt").st_ino
    need(new != old, "NAMESPACE_NOT_PRIVATE")
    return new


class _MountAttr(ctypes.Structure):
    _fields_ = [(k, ctypes.c_uint64) for k in ("set", "clear", "propagation", "userns")]


def _attr(path, readonly, recursive):
    need(os.uname().machine in ("x86_64", "aarch64"), "MOUNT_ABI")
    a = _MountAttr(int(readonly), int(not readonly), 0, 0)
    _libcall(
        "syscall",
        442,
        -100,
        os.fsencode(path),
        0x8000 if recursive else 0,
        ctypes.byref(a),
        ctypes.sizeof(a),
    )


def _bind(path):
    protected(path)
    _libcall(
        "mount", os.fsencode(path), os.fsencode(path), None, ctypes.c_ulong(4096 | 16384), None
    )


def _bootstrap(startup_ref, *, additional=False):
    loc = _locations(additional)
    need(sys.platform == "linux" and os.getuid() == os.geteuid() == 0, "LINUX_ROOT")
    need(
        sys.flags.isolated
        and sys.flags.no_site
        and sys.dont_write_bytecode
        and not any(k == "moomoo" or k.startswith("moomoo.") for k in sys.modules),
        "ISOLATED_INTERPRETER",
    )
    startup = json.loads(read_ref(startup_ref, loc.control / "startup.json", 8192))
    names = {
        "catalog_ref": "release-catalog.json",
        "seed_ref": "plan-seed.json",
        "budget_ref": "budget.json",
        "authorization_ref": "authorization.json",
        "go_fields_ref": "windows-go-fields.json",
    }
    if _recovery_mode(additional):
        names.pop("go_fields_ref")
        names["capture_policy_ref"] = "policy.json"
        need(
            Path(__file__).resolve(strict=True) == loc.release / "ivv_trusted_runner.py",
            "RECOVERY_RUNNER_ORIGIN",
        )
    elif additional:
        names.update(
            descriptor_ref="descriptor.json",
            windows_policy_ref="windows-policy.json",
            capture_policy_ref="policy.json",
        )
        need(
            Path(__file__).resolve(strict=True) == loc.release / "ivv_trusted_runner.py",
            "ADDITIONAL_RUNNER_ORIGIN",
        )
    need(set(startup) == set(names), "STARTUP_REFS")
    _private_mounts()
    for path in (loc.release, SDK, Path("/usr/lib"), Path("/usr/bin")):
        _bind(path)
        _attr(path, True, True)
    originals = {
        k: read_ref(startup[k], (loc.release if k == "catalog_ref" else loc.control) / v)
        for k, v in names.items()
    }
    values = {key: json.loads(raw) for key, raw in originals.items()}
    if not additional:
        need(startup["authorization_ref"]["sha256"] == AUTH, "AUTHORIZATION_PIN")
    catalog = values["catalog_ref"]
    need(set(_sources(additional)) <= set(catalog), "CATALOG_SOURCES")
    for key, filename in _sources(additional).items():
        path = loc.release / filename
        raw = read_ref({"path": str(path), "sha256": catalog[key]}, path, 262144, True)
        if key == "dev_issuer_sha256":
            issuer = types.ModuleType("_qm_trusted_issuer")
            issuer.__file__ = str(path)
            exec(compile(raw, str(path), "exec"), issuer.__dict__)
    if _recovery_mode(additional):
        need(
            startup["authorization_ref"]["sha256"]
            == "6db1254cdf428a17952ae764b10d597435067dc151219c39b3c4fc18c1853dfd",
            "RECOVERY_AUTHORIZATION_PIN",
        )
        task = issuer._released_module("ivv_additional_task.py", catalog["additional_task_sha256"])
        contract = issuer._released_module("ivv_recovery.py", catalog["recovery_contract_sha256"])
        extra = task.RecoveryProfile(contract, values["capture_policy_ref"], additional)
        need(extra.policy_sha == startup["capture_policy_ref"]["sha256"], "RECOVERY_POLICY_PIN")
        values["_additional"] = extra
        values["_recovery_mode"] = additional
        values["_recovery_task"] = task
    elif additional:
        extra = issuer._released_module("ivv_additional_task.py", catalog["additional_task_sha256"])
        extra.authenticate(
            *(
                originals[k]
                for k in (
                    "authorization_ref",
                    "descriptor_ref",
                    "capture_policy_ref",
                    "windows_policy_ref",
                )
            )
        )
        values["_additional"] = extra
    helper = issuer._capture()
    native, producer = issuer._native_sources(helper, catalog)
    need(
        helper._CAPTURE_HELPER_SHA256 == catalog["capture_helper_sha256"]
        if hasattr(helper, "_CAPTURE_HELPER_SHA256")
        else issuer._CAPTURE_HELPER_SHA256 == catalog["capture_helper_sha256"],
        "HELPER_CATALOG",
    )
    return startup, values, issuer, helper, native, producer


def _kread(fd, name, bound=8192):
    f = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
    try:
        return _fdread(f, bound)
    finally:
        _close_fd(f)


def _fdread(fd, bound=8192):
    data = os.pread(fd, bound + 1, 0)
    need(len(data) <= bound, "KERNEL_BOUND")
    return data.decode("ascii").strip()


def _events(fd):
    pairs = [line.split() for line in _fdread(fd).splitlines()]
    need(all(len(row) == 2 and row[1].isdigit() for row in pairs), "RESOURCE_EVENT_SHAPE")
    out = {k: int(v) for k, v in pairs}
    need(bool(out) and len(out) == len(pairs), "RESOURCE_EVENT_SHAPE")
    return out


def _process(pid):
    p = Path("/proc") / str(pid)
    raw = (p / "stat").read_bytes()
    head, sep, tail = raw.rpartition(b") ")
    fields = tail.split()
    need(sep and head.startswith(str(pid).encode() + b" (") and len(fields) >= 20, "PID_STAT")
    group = (p / "cgroup").read_text().strip()
    need(
        re.fullmatch(r"0::/system\.slice/[A-Za-z0-9_@.:-]+\.service/[A-Za-z0-9_-]+", group),
        "OWNED_CGROUP_PATH",
    )
    return (
        {"pid": pid, "start_ticks": int(fields[19]), "uid": p.stat().st_uid, "cgroup": group[3:]},
        int(fields[1]),
    )


def _cgroup_mount():
    lines = Path("/proc/self/mountinfo").read_text().splitlines()
    visible = [line.split() for line in lines if line.split()[4] == str(CG)]
    need(len(visible) == 1, "CGROUP_MOUNT")
    row = visible[0]
    need(row[3] == "/" and row[row.index("-") + 1] == "cgroup2", "CGROUP2_MOUNT")
    return int(row[0])


def _mount_id(fd):
    raw = Path(f"/proc/self/fdinfo/{fd}").read_text().splitlines()
    return int(next(line.split()[1] for line in raw if line.startswith("mnt_id:")))


def _manager_fields(unit, *, terminal=False):
    fields = (
        "Id",
        "MainPID",
        "InvocationID",
        "ControlGroup",
        "KillMode",
        "SendSIGKILL",
        "Delegate",
        "DelegateSubgroup",
        "ActiveState",
        "SubState",
    )
    if terminal:
        fields += ("ExecMainCode", "ExecMainStatus")
    child = subprocess.Popen(
        ["/usr/bin/systemctl", "show", "--no-pager", "--property=" + ",".join(fields), "--", unit],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        close_fds=True,
    )
    data = bytearray()
    deadline = time.monotonic() + 2
    try:
        os.set_blocking(child.stdout.fileno(), False)
        while True:
            left = deadline - time.monotonic()
            need(left > 0, "OWN_MANAGER_TIMEOUT")
            ready, _, _ = select.select([child.stdout], [], [], left)
            need(ready, "OWN_MANAGER_TIMEOUT")
            part = os.read(child.stdout.fileno(), 8193 - len(data))
            if not part:
                break
            data.extend(part)
            need(len(data) <= 8192, "OWN_MANAGER_BOUND")
        need(child.wait(timeout=max(0.001, deadline - time.monotonic())) == 0, "OWN_MANAGER_QUERY")
        rows = [line.partition("=") for line in data.decode("ascii").splitlines()]
        result = {k: v for k, sep, v in rows if sep}
        need(len(result) == len(rows) and set(result) == set(fields), "OWN_MANAGER_SHAPE")
        return result
    finally:
        primary = sys.exc_info()[1]
        errors = []
        try:
            if child.poll() is None:
                child.kill()  # this Popen-created query child only
                child.wait(timeout=2)
        except BaseException as error:
            errors.append("OWN_MANAGER_REAP_" + reason(error))
        try:
            child.stdout.close()
        except BaseException as error:
            errors.append("OWN_MANAGER_CLOSE_" + reason(error))
        if errors:
            raise Refused("+".join(([reason(primary)] if primary else []) + errors)) from None


def _manager_contract(parent):
    path = PurePosixPath(parent["cgroup"])
    unit = path.parent.name
    fields = _manager_fields(unit)
    need(
        fields.get("Id") == unit
        and fields.get("MainPID") == str(parent["pid"])
        and fields.get("ControlGroup") == str(path.parent)
        and re.fullmatch("[0-9a-f]{32}", fields.get("InvocationID", ""))
        and fields.get("KillMode") == "process"
        and fields.get("SendSIGKILL") == "no"
        and fields.get("Delegate") == "yes"
        and fields.get("DelegateSubgroup") == path.name
        and fields.get("ActiveState") == "active"
        and fields.get("SubState") == "running",
        "OWN_MANAGER_CONTRACT",
    )
    return fields


class _Scope:
    """Handles are created internally and retained until the final resource observation."""

    def __init__(self, stack, *, additional=False):
        self.stack = stack
        self.pid = None
        self.pidfd = None
        self.child = None
        self.reaped = False
        self.moved = False
        self.leaf = None
        self.mount = _cgroup_mount()
        self.parent, _ = _process(os.getpid())
        if additional:
            need(
                self.parent["uid"] == 0
                and self.parent["pid"] == os.getpid()
                and self.parent["cgroup"]
                == (
                    "/system.slice/qm-ivv-recovery-" + additional + ".service/manager"
                    if _recovery_mode(additional)
                    else "/system.slice/qm-ivv-additional-20261103-01.service/manager"
                ),
                "ADDITIONAL_OWNED_UNIT",
            )
        self.manager_contract = _manager_contract(self.parent)
        self.manager = Path(self.parent["cgroup"]).name
        self.unitpath = CG / self.parent["cgroup"].strip("/")
        self.unitpath = self.unitpath.parent
        self.group = self.open_dir(self.unitpath)
        self.man = self.open_dir(self.manager, self.group)
        need(
            _kread(self.man, "cgroup.procs") == str(os.getpid())
            and _kread(self.group, "cgroup.procs") == ""
            and self.dirs(self.group) == {self.manager},
            "UNIT_NOT_EXCLUSIVE",
        )
        self.controls(self.group)
        if additional:
            self.enable_controllers()
        self.total_events = self.event_files(self.group)
        self.name = "ivv-owned-" + str(os.getpid()) + "-" + str(self.parent["start_ticks"])
        # mkdir must win exclusively before any cleanup or write is registered.
        self.verify_unit()
        os.mkdir(self.name, 0o700, dir_fd=self.group)
        self.leaf = self.open_dir(self.name, self.group)
        self.check_leaf()
        for k, v in LIMITS.items():
            self.write(k, v)
        self.controls(self.leaf)
        self.leaf_events = self.event_files(self.leaf)
        self.pop = self.open_file("cgroup.events", self.leaf)
        self.events = [*self.total_events, *self.leaf_events]
        self.initial = [_events(fd) for fd in self.events]

    def enable_controllers(self):
        started = time.monotonic()
        required = {"memory", "cpu", "pids"}
        protected(self.unitpath)
        self.verify_manager()
        self.verify_unit()
        need(
            not self.dirs(self.man)
            and required <= set(_kread(self.group, "cgroup.controllers").split()),
            "ADDITIONAL_CONTROLLERS_UNAVAILABLE",
        )
        before = set(_kread(self.group, "cgroup.subtree_control").split())
        fd = self.open_file("cgroup.subtree_control", self.group, os.O_WRONLY)
        info = os.fstat(fd)
        need(
            stat.S_ISREG(info.st_mode)
            and info.st_uid == 0
            and not info.st_mode & 0o022
            and info.st_dev == os.fstat(self.group).st_dev,
            "ADDITIONAL_CONTROLLER_FD",
        )
        msg = b"+cpu +memory +pids"
        need(os.write(fd, msg) == len(msg), "ADDITIONAL_CONTROLLER_WRITE")
        need(
            set(_kread(self.group, "cgroup.subtree_control").split()) == before | required,
            "ADDITIONAL_CONTROLLER_READBACK",
        )
        self.verify_manager()
        self.verify_unit()
        need(
            _kread(self.group, "cgroup.procs") == ""
            and _kread(self.man, "cgroup.procs") == str(os.getpid())
            and self.dirs(self.group) == {self.manager}
            and not self.dirs(self.man)
            and time.monotonic() - started <= 5,
            "ADDITIONAL_UNIT_DRIFT",
        )

    def open_file(self, name, where, flags=None):
        fd = os.open(
            name,
            (os.O_RDONLY if flags is None else flags) | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=where,
        )
        self.stack.callback(os.close, fd)
        need(_mount_id(fd) == self.mount, "CGROUP_FD_MOUNT")
        return fd

    def open_dir(self, name, where=None):
        return self.open_file(name, where, os.O_RDONLY | os.O_DIRECTORY)

    @staticmethod
    def dirs(fd):
        with os.scandir(fd) as stream:
            return {e.name for e in stream if e.is_dir(follow_symlinks=False)}

    def event_files(self, fd):
        return [
            self.open_file(name, fd)
            for name in ("memory.events", "pids.events", "memory.swap.events")
        ]

    @staticmethod
    def controls(fd):
        need({k: _kread(fd, k, 128) for k in LIMITS} == LIMITS, "TOTAL_OR_CHILD_LIMIT")

    def verify_unit(self):
        need(
            _cgroup_mount() == self.mount
            and identity(os.stat(self.unitpath, follow_symlinks=False))
            == identity(os.fstat(self.group))
            and _process(os.getpid())[0] == self.parent
            and identity(os.stat(self.manager, dir_fd=self.group, follow_symlinks=False))
            == identity(os.fstat(self.man)),
            "UNIT_CHANGED",
        )
        self.controls(self.group)

    def verify_manager(self):
        need(_manager_contract(self.parent) == self.manager_contract, "OWN_MANAGER_DRIFT")

    def check_leaf(self):
        self.verify_unit()
        need(
            self.leaf is not None
            and identity(os.stat(self.name, dir_fd=self.group, follow_symlinks=False))
            == identity(os.fstat(self.leaf))
            and self.dirs(self.group) == {self.manager, self.name}
            and not self.dirs(self.man)
            and not self.dirs(self.leaf),
            "CGROUP_REPLACED",
        )

    def write(self, name, value):
        self.check_leaf()
        fd = os.open(name, os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=self.leaf)
        try:
            need(
                _mount_id(fd) == self.mount and os.write(fd, value.encode()) == len(value),
                "CGROUP_WRITE",
            )
        finally:
            _close_fd(fd)

    def bind(self, pid):
        self.pid = pid
        self.pidfd = os.pidfd_open(pid)
        self.stack.callback(os.close, self.pidfd)
        actor, ppid = _process(pid)
        need(
            ppid == os.getpid() and actor["uid"] == 0 and actor["cgroup"] == self.parent["cgroup"],
            "FORK_BIND",
        )
        self.child = actor
        self.check_pid()
        self.write("cgroup.procs", str(pid))
        self.moved = True
        self.child = {
            **actor,
            "cgroup": str(PurePosixPath(self.parent["cgroup"]).parent / self.name),
        }
        self.check_pid()

    def check_pid(self):
        need(
            self.pid and self.pid > 0 and not self.reaped and self.pidfd is not None, "NO_OWNED_PID"
        )
        info = Path(f"/proc/self/fdinfo/{self.pidfd}").read_text().splitlines()
        need(
            [line.split()[1] for line in info if line.startswith("Pid:")] == [str(self.pid)],
            "PIDFD_SWAPPED",
        )
        actual, ppid = _process(self.pid)
        need(actual == self.child and ppid == os.getpid(), "CHILD_PID_CHANGED")

    def check_resources(self):
        self.check_leaf()
        self.controls(self.leaf)
        need([_events(fd) for fd in self.events] == self.initial, "RESOURCE_LIMIT_EVENT")

    def check_final_resources(self):
        # The empty removed leaf cannot accrue events. Its FDs stay retained;
        # the enclosing TOTAL counters still cover all final parent work.
        need(self.reaped and self.leaf is None, "FINAL_CHILD_NOT_REMOVED")
        self.verify_unit()
        need(
            self.dirs(self.group) == {self.manager}
            and not self.dirs(self.man)
            and _kread(self.man, "cgroup.procs") == str(os.getpid()),
            "FINAL_UNIT_NOT_EMPTY",
        )
        need(
            [_events(fd) for fd in self.total_events] == self.initial[: len(self.total_events)],
            "RESOURCE_LIMIT_EVENT",
        )

    def reap(self):
        self.check_pid()
        info = os.waitid(os.P_PIDFD, self.pidfd, os.WEXITED | os.WNOHANG)
        if info is None:
            return None
        self.reaped = True
        need(info.si_pid == self.pid and info.si_code == os.CLD_EXITED, "ABNORMAL_CHILD_EXIT")
        return info.si_status

    def empty(self):
        self.check_leaf()
        need(
            _events(self.pop).get("populated") == 0 and not _kread(self.leaf, "cgroup.procs"),
            "CGROUP_NOT_EMPTY",
        )

    def remove(self):
        self.empty()
        os.rmdir(self.name, dir_fd=self.group)

    def abort(self):
        errors = []
        try:
            if self.pid and not self.reaped:
                self.check_pid()
                signal.pidfd_send_signal(self.pidfd, signal.SIGKILL)
                poll = select.poll()
                poll.register(self.pidfd, select.POLLIN)
                need(poll.poll(2000), "FORCED_WAIT_UNKNOWN")
                status = os.waitid(os.P_PIDFD, self.pidfd, os.WEXITED | os.WNOHANG)
                need(status and status.si_pid == self.pid, "FORCED_REAP_UNKNOWN")
                self.reaped = True
        except BaseException as e:
            errors.append(reason(e))
        try:
            if self.leaf is not None:
                self.check_leaf()
                # Only the fork-derived, start/PPID/pidfd-bound child is signal
                # authority. A leaf inode does not prove that every process
                # subsequently placed there is ours. Unknown members stay
                # untouched and make recursive empty/removal fail closed.
                self.remove()
        except BaseException as e:
            errors.append(reason(e))
        return errors


def _persist_recovery_owner(book, attempt, scope):
    # The child is still blocked on the authenticated enter message here.
    scope.check_pid()
    scope.check_leaf()
    binding = {
        "connection_attempt_id": attempt,
        "manager": scope.parent,
        "child": scope.child,
        "mount": {"id": scope.mount, "namespace": list(identity(os.stat("/proc/self/ns/mnt")))},
        "group": list(identity(os.fstat(scope.group))),
        "manager_dir": list(identity(os.fstat(scope.man))),
        "leaf": list(identity(os.fstat(scope.leaf))),
    }
    book._write(attempt + ".owner.json", binding)
    scope.check_pid()
    scope.check_leaf()


def _recover_bound_owner(binding):
    """Recover only the recorded orphan after its original manager has exited.

    This never certifies normal SDK close, original wait status or data admission.
    The exact cgroup and pidfd primitives are the same as the live owner path.
    """
    need(
        type(binding) is dict
        and set(binding)
        == {"connection_attempt_id", "manager", "child", "mount", "group", "manager_dir", "leaf"},
        "RECOVERY_OWNER_BINDING",
    )
    attempt, manager, child = (binding[k] for k in ("connection_attempt_id", "manager", "child"))
    need(_recovery_mode(attempt), "RECOVERY_ATTEMPT")
    unit = "/system.slice/qm-ivv-recovery-" + attempt + ".service"
    for actor in (manager, child):
        need(
            type(actor) is dict
            and set(actor) == {"pid", "start_ticks", "uid", "cgroup"}
            and type(actor["pid"]) is int
            and actor["pid"] > 1
            and type(actor["start_ticks"]) is int
            and actor["start_ticks"] > 0
            and type(actor["uid"]) is int
            and actor["uid"] == 0,
            "RECOVERY_OWNER_ACTOR",
        )
    leaf = "ivv-owned-" + str(manager["pid"]) + "-" + str(manager["start_ticks"])
    need(
        manager["pid"] != child["pid"]
        and manager["cgroup"] == unit + "/manager"
        and child["cgroup"] == unit + "/" + leaf,
        "RECOVERY_OWNER_SCOPE",
    )
    for key in ("group", "manager_dir", "leaf"):
        need(
            type(binding[key]) is list
            and len(binding[key]) == 4
            and all(type(v) is int for v in binding[key])
            and stat.S_ISDIR(binding[key][2])
            and binding[key][3] == 0,
            "RECOVERY_OWNER_INODE",
        )

    def actor_now(actor):
        try:
            actual, ppid = _process(actor["pid"])
        except FileNotFoundError:
            # A partial /proc read is not absence; require the process directory gone.
            need(not (Path("/proc") / str(actor["pid"])).exists(), "RECOVERY_PROCESS_UNCERTAIN")
            return None
        need(actual == actor, "RECOVERY_PID_CHANGED")
        return ppid

    need(actor_now(manager) is None, "RECOVERY_MANAGER_ACTIVE")
    child_parent = actor_now(child)
    need(child_parent in (None, 1), "RECOVERY_CHILD_PARENT")
    old_mount = binding["mount"]
    need(
        type(old_mount) is dict
        and set(old_mount) == {"id", "namespace"}
        and type(old_mount["id"]) is int
        and old_mount["id"] > 0
        and type(old_mount["namespace"]) is list
        and len(old_mount["namespace"]) == 4
        and all(type(v) is int for v in old_mount["namespace"]),
        "RECOVERY_MOUNT_PROVENANCE",
    )
    # Mount IDs identify mounts in a namespace, not the backing cgroup inode.
    # _cgroup_mount requires the current cgroup2 mount at CG with mount root '/'.
    # Keep the original namespace/id above; match every current held FD to this
    # current mount and every backing dev/ino/mode/UID to the original binding.
    current_mount = _cgroup_mount()
    root = CG / unit.lstrip("/")
    descriptors, paths = {}, {}
    errors = []
    try:
        for name, path in (
            ("group", root),
            ("manager_dir", root / "manager"),
            ("leaf", root / leaf),
        ):
            try:
                protected(path)
                fd = os.open(
                    path,
                    os.O_RDONLY
                    | getattr(os, "O_DIRECTORY", 0)
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                )
            except FileNotFoundError:
                need(child_parent is None or name == "manager_dir", "RECOVERY_CGROUP_MISSING")
                continue
            descriptors[name], paths[name] = fd, path
            need(
                list(identity(os.fstat(fd))) == binding[name]
                and identity(os.stat(path, follow_symlinks=False)) == identity(os.fstat(fd))
                and _mount_id(fd) == current_mount,
                "RECOVERY_CGROUP_CHANGED",
            )
        need("group" in descriptors or not descriptors, "RECOVERY_CGROUP_PARTIAL")

        def check_members():
            for name, fd in descriptors.items():
                need(
                    list(identity(os.fstat(fd))) == binding[name]
                    and identity(os.stat(paths[name], follow_symlinks=False))
                    == identity(os.fstat(fd))
                    and _mount_id(fd) == current_mount,
                    "RECOVERY_CGROUP_CHANGED",
                )
                allowed_dirs = (
                    ({"manager"} if "manager_dir" in descriptors else set())
                    | ({leaf} if "leaf" in descriptors else set())
                    if name == "group"
                    else set()
                )
                need(_Scope.dirs(fd) == allowed_dirs, "RECOVERY_FOREIGN_CGROUP")
                members = _kread(fd, "cgroup.procs").split()
                allowed = {str(child["pid"])} if name == "leaf" else set()
                need(set(members) <= allowed, "RECOVERY_FOREIGN_MEMBER")

        check_members()
        if child_parent is not None:
            fd = os.pidfd_open(child["pid"])
            descriptors["pidfd"] = fd
            need(actor_now(manager) is None and actor_now(child) == 1, "RECOVERY_OWNER_CHANGED")
            # pidfd is acquired between two exact start/UID/cgroup observations.
            held_pidfd = descriptors.pop("pidfd")
            try:
                check_members()
                until = time.monotonic() + 2
                signal.pidfd_send_signal(held_pidfd, signal.SIGKILL)
                need(
                    select.select([held_pidfd], [], [], max(0, until - time.monotonic()))[0]
                    == [held_pidfd],
                    "RECOVERY_WAIT_UNKNOWN",
                )
                while actor_now(child) is not None and time.monotonic() < until:
                    time.sleep(0.01)
                need(actor_now(child) is None, "RECOVERY_REAP_UNKNOWN")
            finally:
                descriptors["pidfd"] = held_pidfd
        need(actor_now(manager) is None and actor_now(child) is None, "RECOVERY_OWNER_ACTIVE")
        for name, fd in descriptors.items():
            if name == "pidfd":
                continue
            need(
                not _kread(fd, "cgroup.procs")
                and "populated 0" in _kread(fd, "cgroup.events").splitlines(),
                "RECOVERY_NOT_EMPTY",
            )
        # No namespace-expiry assumption, no old normal-close upgrade.
    finally:
        for fd in reversed(list(descriptors.values())):
            try:
                _close_fd(fd)
            except BaseException:
                errors.append("RECOVERY_FD_CLOSE")
        need(not errors, "RECOVERY_FD_CLOSE")
    return {"owned_cleanup_proven": True, "external_effects": "UNKNOWN", "input_publishable": False}


@contextlib.contextmanager
def recovery_claim_lease(book):
    with _recovery_lease(book.root / "connection-000000.claim-lock.json") as lease:
        lease.controller, _ = _controller_actor(os.getpid())
        lease.origin = list(identity(os.fstat(lease.fd)))
        book._claim_lease = lease
        try:
            yield lease
        finally:
            book._claim_lease = None


class _RecoveryLease:
    def __init__(self, fd):
        self.fd = fd

    def bind_reference_epoch(self, offset):
        need(
            self.fd is not None and type(offset) is int and 0 < offset <= 2**60,
            "REFERENCE_CLAIM_EPOCH",
        )
        need(os.lseek(self.fd, offset, os.SEEK_SET) == offset, "REFERENCE_CLAIM_EPOCH")
        self.reference_epoch = offset

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            _close_fd(fd)


@contextlib.contextmanager
def _recovery_lease(path):
    import fcntl

    try:
        put(path, {})
    except FileExistsError:
        pass
    read_ref({"path": str(path), "sha256": digest(raw_json({}))}, path)
    lease = _RecoveryLease(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC))
    try:
        need(identity(os.fstat(lease.fd)) == identity(path.lstat()), "RECOVERY_LEASE_CHANGED")
        fcntl.flock(lease.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield lease
    finally:
        lease.close()


def _controller_actor(pid):
    need(type(pid) is int and pid > 1, "RECOVERY_CONTROLLER_PID")
    path = Path("/proc") / str(pid)
    raw = (path / "stat").read_bytes()
    group = (path / "cgroup").read_bytes()
    need(len(raw) <= 8192 and len(group) <= 8192, "RECOVERY_CONTROLLER_METADATA")
    fields = raw[raw.rindex(b")") + 2 :].split()
    need(
        int(raw.split(b" ", 1)[0]) == pid
        and len(fields) > 19
        and group.startswith(b"0::/")
        and group.count(b"\n") == 1,
        "RECOVERY_CONTROLLER_METADATA",
    )
    return {
        "pid": pid,
        "start_ticks": int(fields[19]),
        "uid": path.stat().st_uid,
        "cgroup": group[3:].decode("ascii").strip(),
    }, int(fields[1])


def _recover_predispatch(book, intent):
    binding = intent.get("pre_dispatch")
    attempt = intent["connection_attempt_id"]
    need(
        _recovery_mode(attempt)
        and type(binding) is dict
        and set(binding) == {"controller", "claim_inode", "unit"},
        "RECOVERY_PRE_DISPATCH_MISSING",
    )
    actor = binding["controller"]
    unit = "qm-ivv-recovery-" + attempt + ".service"
    need(
        type(actor) is dict
        and set(actor) == {"pid", "start_ticks", "uid", "cgroup"}
        and type(actor["pid"]) is int
        and actor["pid"] > 1
        and type(actor["start_ticks"]) is int
        and actor["start_ticks"] > 0
        and type(actor["uid"]) is int
        and actor["uid"] == 0
        and binding["unit"] == unit,
        "RECOVERY_CONTROLLER_BINDING",
    )
    lease = getattr(book, "_claim_lease", None)
    need(
        type(lease) is _RecoveryLease
        and lease.fd is not None
        and lease.controller["pid"] == os.getpid()
        and _controller_actor(os.getpid())[0] == lease.controller
        and list(identity(os.fstat(lease.fd))) == binding["claim_inode"]
        and identity(os.fstat(lease.fd))
        == identity((book.root / "connection-000000.claim-lock.json").lstat()),
        "RECOVERY_CLAIM_LEASE_REQUIRED",
    )
    need(not (book.root / (attempt + ".dispatch.json")).exists(), "RECOVERY_DISPATCH_UNKNOWN")
    try:
        actual, _ = _controller_actor(actor["pid"])
    except FileNotFoundError:
        need(not (Path("/proc") / str(actor["pid"])).exists(), "RECOVERY_CONTROLLER_UNCERTAIN")
    else:
        need(actual == actor, "RECOVERY_CONTROLLER_CHANGED")
        raise Refused("RECOVERY_CONTROLLER_ACTIVE")
    fields = _manager_fields(unit)
    need(
        fields["Id"] == unit
        and fields["MainPID"] == "0"
        and fields["InvocationID"] == ""
        and fields["ActiveState"] == "inactive"
        and not (CG / "system.slice" / unit).exists(),
        "RECOVERY_UNEXPECTED_UNIT",
    )
    return {"owned_cleanup_proven": True, "external_effects": "UNKNOWN", "input_publishable": False}


def _preowner_binding(attempt, startup):
    loc = _locations(attempt)
    actor, _ = _process(os.getpid())
    fields = _manager_contract(actor)
    unit = "qm-ivv-recovery-" + attempt + ".service"
    need(
        fields["Id"] == unit and actor["cgroup"] == "/system.slice/" + unit + "/manager",
        "RECOVERY_MANAGER_SCOPE",
    )
    dispatch = read_ref(
        {
            "path": str(loc.ledger / (attempt + ".dispatch.json")),
            "sha256": digest(raw_json({"unit": unit, "startup_sha256": startup})),
        },
        loc.ledger / (attempt + ".dispatch.json"),
    )
    need(json.loads(dispatch) == {"unit": unit, "startup_sha256": startup}, "RECOVERY_DISPATCH")
    group = CG / "system.slice" / unit
    mount = _cgroup_mount()
    fd = os.open(group, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        origin = list(identity(os.fstat(fd)))
        need(
            origin == list(identity(group.lstat())) and _mount_id(fd) == mount,
            "RECOVERY_CGROUP_CHANGED",
        )
    finally:
        _close_fd(fd)
    need(
        _process(actor["pid"])[0] == actor and _manager_contract(actor) == fields,
        "RECOVERY_MANAGER_CHANGED",
    )
    return {
        "connection_attempt_id": attempt,
        "startup_sha256": startup,
        "manager": actor,
        "unit": fields,
        "group": origin,
        "mount": {"id": mount, "namespace": list(identity(Path("/proc/self/ns/mnt").stat()))},
    }


@contextlib.contextmanager
def _recovery_lifecycle(startup, attempt):
    loc = _locations(attempt)
    with _recovery_lease(loc.ledger / (attempt + ".lifecycle-lock.json")) as lease:
        binding = _preowner_binding(attempt, startup["sha256"])
        ref = put(loc.ledger / (attempt + ".preowner.json"), binding)
        # systemd --pipe supplies a bounded controller gate, then original null stdio.
        need(select.select([0], [], [], 8)[0] == [0], "RECOVERY_GATE_TIMEOUT")
        token = os.read(0, 66)
        need(token == (ref["sha256"] + "\n").encode("ascii"), "RECOVERY_GATE_TOKEN")
        need(_preowner_binding(attempt, startup["sha256"]) == binding, "RECOVERY_MANAGER_CHANGED")
        null = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
        try:
            os.dup2(null, 0)
        finally:
            _close_fd(null)
        yield lease


def _recover_preowner(binding, book):
    """Cleanup-only proof for a durably bound manager, never SDK-zero or normal close."""
    need(
        type(binding) is dict
        and set(binding)
        == {"connection_attempt_id", "startup_sha256", "manager", "unit", "group", "mount"},
        "RECOVERY_PREOWNER_SHAPE",
    )
    attempt, actor, fields = (binding[k] for k in ("connection_attempt_id", "manager", "unit"))
    need(_recovery_mode(attempt), "RECOVERY_ATTEMPT")
    unit = "qm-ivv-recovery-" + attempt + ".service"
    need(
        type(actor) is dict
        and set(actor) == {"pid", "start_ticks", "uid", "cgroup"}
        and type(actor["pid"]) is int
        and actor["pid"] > 1
        and type(actor["start_ticks"]) is int
        and actor["start_ticks"] > 0
        and actor["uid"] == 0
        and actor["cgroup"] == "/system.slice/" + unit + "/manager"
        and fields["Id"] == unit
        and fields["MainPID"] == str(actor["pid"])
        and re.fullmatch("[0-9a-f]{32}", fields["InvocationID"]),
        "RECOVERY_PREOWNER_ACTOR",
    )
    try:
        actual, _ = _process(actor["pid"])
    except FileNotFoundError:
        need(not (Path("/proc") / str(actor["pid"])).exists(), "RECOVERY_PROCESS_UNCERTAIN")
    else:
        need(actual == actor, "RECOVERY_PID_CHANGED")
        raise Refused("RECOVERY_MANAGER_ACTIVE")
    observed = _manager_fields(unit, terminal=True)
    name = attempt + ".terminal.json"
    saved = book._read(name) if (book.root / name).exists() else None
    terminal = observed
    if observed["InvocationID"] != fields["InvocationID"]:
        need(
            saved is not None
            and saved["preowner_sha256"] == digest(raw_json(binding))
            and observed["Id"] == unit
            and observed["InvocationID"] == ""
            and observed["MainPID"] == "0"
            and observed["ActiveState"] == "inactive",
            "RECOVERY_UNIT_NOT_TERMINAL",
        )
        terminal = saved["terminal"]
    need(
        terminal["Id"] == unit
        and terminal["InvocationID"] == fields["InvocationID"]
        and terminal["MainPID"] == "0"
        and (terminal["ActiveState"], terminal["SubState"])
        in (("inactive", "dead"), ("failed", "failed"), ("active", "exited")),
        "RECOVERY_UNIT_NOT_TERMINAL",
    )
    mount = _cgroup_mount()
    group = CG / "system.slice" / unit
    try:
        fd = os.open(group, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        need(not group.exists(), "RECOVERY_CGROUP_UNCERTAIN")
    else:
        try:
            need(
                list(identity(os.fstat(fd))) == binding["group"]
                and identity(os.fstat(fd)) == identity(group.lstat())
                and _mount_id(fd) == mount,
                "RECOVERY_CGROUP_CHANGED",
            )
            need(
                _Scope.dirs(fd)
                <= {"manager", "ivv-owned-" + str(actor["pid"]) + "-" + str(actor["start_ticks"])},
                "RECOVERY_FOREIGN_CGROUP",
            )
            # cgroup.events populated is recursive, so a post-fork unbound child blocks recovery.
            need(
                not _kread(fd, "cgroup.procs")
                and "populated 0" in _kread(fd, "cgroup.events").splitlines(),
                "RECOVERY_NOT_EMPTY",
            )
        finally:
            _close_fd(fd)
    need(_manager_fields(unit, terminal=True) == observed, "RECOVERY_UNIT_CHANGED")
    record = {"preowner_sha256": digest(raw_json(binding)), "terminal": terminal}
    if saved is None:
        book._write(name, record)  # proof before stop can erase the unit's Invocation metadata
    else:
        need(saved == record, "RECOVERY_TERMINAL_CHANGED")
    if observed["ActiveState"] == "active":
        _stop_quiescent_unit(unit, observed)
    proof = {
        "owned_cleanup_proven": True,
        "external_effects": "UNKNOWN",
        "input_publishable": False,
    }
    final = {"preowner_sha256": digest(raw_json(binding)), **proof}
    name = attempt + ".unit-cleanup.json"
    if (book.root / name).exists():
        need(book._read(name) == final, "RECOVERY_UNIT_RECEIPT")
    else:
        book._write(name, final)
    return proof


def _stop_quiescent_unit(unit, expected):
    need(
        _manager_fields(unit, terminal=True) == expected
        and expected["MainPID"] == "0"
        and expected["SubState"] == "exited",
        "RECOVERY_UNIT_CHANGED",
    )
    child = subprocess.Popen(
        ["/usr/bin/systemctl", "stop", "--", unit],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
        env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
    )
    try:
        need(child.wait(timeout=2) == 0, "RECOVERY_UNIT_STOP")
    finally:
        if child.poll() is None:
            try:
                child.kill()
                child.wait(timeout=2)
            except BaseException:
                # Retain this exact helper until terminal proof or the carrier's
                # existing outer deadline, never continue with normal authority.
                while True:
                    try:
                        child.wait(timeout=0.1)
                        break
                    except BaseException:
                        time.sleep(0.01)
    fields = _manager_fields(unit)
    need(
        fields["Id"] == unit
        and fields["MainPID"] == "0"
        and fields["ActiveState"] in ("inactive", "failed")
        and fields["InvocationID"] in (expected["InvocationID"], ""),
        "RECOVERY_UNIT_STOP",
    )


def stop_bound_recovery_manager(book, attempt):
    """Carrier timeout: stop only the recorded unit manager, never its client as proxy."""
    binding = book._read(attempt + ".preowner.json")
    actor = binding["manager"]
    unit = "qm-ivv-recovery-" + attempt + ".service"
    fields = _manager_fields(unit)
    need(fields["InvocationID"] == binding["unit"]["InvocationID"], "RECOVERY_UNIT_CHANGED")
    try:
        actual, _ = _process(actor["pid"])
    except FileNotFoundError:
        need(not (Path("/proc") / str(actor["pid"])).exists(), "RECOVERY_PROCESS_UNCERTAIN")
        return
    need(actual == actor and fields["MainPID"] == str(actor["pid"]), "RECOVERY_PID_CHANGED")
    fd = os.pidfd_open(actor["pid"])
    try:
        need(
            _process(actor["pid"])[0] == actor and _manager_fields(unit) == fields,
            "RECOVERY_PID_CHANGED",
        )
        signal.pidfd_send_signal(fd, signal.SIGKILL)
        need(select.select([fd], [], [], 2)[0] == [fd], "RECOVERY_MANAGER_STOP_UNKNOWN")
    finally:
        _close_fd(fd)


def recover_previous_attempt(book, read_owned):
    """Fixed carrier entry, before any new context intent or SDK opportunity."""
    import fcntl

    rows = book._intents()
    if not rows:
        return
    attempt = rows[-1]["connection_attempt_id"]
    need(
        _recovery_mode(attempt) and book.root == _locations(attempt).ledger, "RECOVERY_LEDGER_SCOPE"
    )
    protected(book.root)
    close_path = book.root / (attempt + ".close.json")
    closed = book._read(close_path.name) if close_path.exists() else None
    if closed is not None and closed["owner_state"] == "CLOSED":
        # Parent closure is written before that manager exits. A successor must
        # independently close the retained unit as well, under the lifecycle lease.
        if (book.root / (attempt + ".preowner.json")).exists():
            with _recovery_lease(book.root / (attempt + ".lifecycle-lock.json")):
                _recover_preowner(book._read(attempt + ".preowner.json"), book)
        return
    owner = (book.root / (attempt + ".owner.json")).exists()
    preowner = (book.root / (attempt + ".preowner.json")).exists()
    binding = book._read(
        attempt + (".owner.json" if owner else (".preowner.json" if preowner else ".intent.json"))
    )
    previous_failure = read_runner_failure(_locations(attempt).control, read_owned)
    ref = digest(raw_json(binding))
    receipt = {
        "owner_binding_sha256": ref,
        "owned_cleanup_proven": True,
        "external_effects": "UNKNOWN",
        "input_publishable": False,
    }
    done = attempt + ".recovered.json"
    if (book.root / done).exists():
        need(book._read(done) == receipt, "RECOVERY_RECEIPT")
        return
    lockname = attempt + ".recovery-lock.json"
    try:
        book._write(lockname, {})
    except FileExistsError:
        pass
    need(book._read(lockname) == {}, "RECOVERY_LEASE_FILE")
    protected(book.root / lockname)
    lock = os.open(book.root / lockname, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        need(
            os.path.samestat(os.fstat(lock), (book.root / lockname).lstat()),
            "RECOVERY_LEASE_CHANGED",
        )
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        need(not (book.root / done).exists(), "RECOVERY_ALREADY_COMMITTED")
        with _recovery_lease(book.root / (attempt + ".lifecycle-lock.json")):
            proof = (
                _recover_bound_owner(binding)
                if owner
                else (
                    _recover_preowner(binding, book)
                    if preowner
                    else _recover_predispatch(book, binding)
                )
            )
            if owner and (book.root / (attempt + ".preowner.json")).exists():
                need(
                    _recover_preowner(book._read(attempt + ".preowner.json"), book) == proof,
                    "RECOVERY_UNIT_CLOSURE",
                )
        need(proof == {k: receipt[k] for k in proof} and len(proof) == 3, "RECOVERY_PROOF")
    finally:
        _close_fd(lock)
    # All recovery descriptors, including the lease, closed before publication.
    if closed is None:
        # A crashed parent cannot supply a normal close. Record only interruption;
        # an existing finite structural refusal still requires a changed method.
        failure = (
            "CAPTURE_INTERRUPTED"
            if previous_failure is None
            else (
                previous_failure["reason"]
                if previous_failure["reason"] in ("SDK_CLOSE_UNKNOWN", "CAPTURE_TIMEOUT")
                else "RECORDED_PRIOR_FAILURE"
            )
        )
        book.close(attempt, {}, failure=failure, method_sha256=rows[-1]["method_sha256"])
    book._write(done, receipt)


def _reference_condition_lease(book):
    lease = getattr(book, "_claim_lease", None)
    need(
        type(lease) is _RecoveryLease
        and lease.fd is not None
        and lease.controller == _controller_actor(os.getpid())[0]
        and lease.origin
        == list(identity(os.fstat(lease.fd)))
        == list(identity((book.root / "connection-000000.claim-lock.json").lstat())),
        "REFERENCE_CONDITION_LEASE",
    )


def _reference_claim_lock(claim):
    """Read bounded kernel facts for the original controller's exact held flock FD."""
    pid, fd = claim["controller"]["pid"], claim["claim_fd"]
    need(type(fd) is int and 0 <= fd < 1048576, "REFERENCE_CLAIM_FD")
    descriptor = Path(f"/proc/{pid}/fd/{fd}")
    before = descriptor.stat()
    need(list(identity(before)) == claim["claim_inode"], "REFERENCE_CLAIM_FD")
    with Path(f"/proc/{pid}/fdinfo/{fd}").open("rb") as stream:
        raw = stream.read(4097)
    need(len(raw) <= 4096, "REFERENCE_CLAIM_LOCK_BOUND")
    positions = [line for line in raw.splitlines() if line.startswith(b"pos:")]
    need(
        type(claim["claim_offset"]) is int
        and 0 < claim["claim_offset"] <= 2**60
        and len(positions) == 1
        and re.fullmatch(rb"pos:\s+" + str(claim["claim_offset"]).encode(), positions[0]),
        "REFERENCE_CLAIM_EPOCH",
    )
    locks = [line for line in raw.splitlines() if line.startswith(b"lock:")]
    need(len(locks) == 1, "REFERENCE_CLAIM_LOCK")
    match = re.fullmatch(
        rb"lock:\s+\d+:\s+FLOCK\s+ADVISORY\s+WRITE\s+(\d+)\s+([0-9a-fA-F]+):([0-9a-fA-F]+):(\d+)\s+0\s+EOF",
        locks[0],
    )
    need(match is not None, "REFERENCE_CLAIM_LOCK")
    need(
        int(match[1]) == pid
        and int(match[2], 16) == os.major(before.st_dev)
        and int(match[3], 16) == os.minor(before.st_dev)
        and int(match[4]) == before.st_ino
        and identity(descriptor.stat()) == identity(before),
        "REFERENCE_CLAIM_LOCK",
    )


def _reference_transition_owner(book, attempt, claim, require_owner):
    try:
        actual, _ = _controller_actor(claim["controller"]["pid"])
    except FileNotFoundError:
        raise Refused("REFERENCE_CONTROLLER_GONE") from None
    need(
        actual == claim["controller"]
        and list(identity((book.root / "connection-000000.claim-lock.json").lstat()))
        == claim["claim_inode"],
        "REFERENCE_CONTROLLER_CHANGED",
    )
    _reference_claim_lock(claim)
    need(
        _controller_actor(claim["controller"]["pid"])[0] == actual
        and list(identity((book.root / "connection-000000.claim-lock.json").lstat()))
        == claim["claim_inode"],
        "REFERENCE_CONTROLLER_CHANGED",
    )
    if require_owner:
        _reference_condition_lease(book)
    else:
        intent = book._read(attempt + ".intent.json")
        need(
            intent.get("pre_dispatch")
            == {
                "controller": claim["controller"],
                "claim_inode": claim["claim_inode"],
                "unit": "qm-ivv-recovery-" + attempt + ".service",
            },
            "REFERENCE_CONTROLLER_BINDING",
        )


def reference_capture_condition(book, pair_sha256, read_owned, native, producer):
    """Owning carrier's single consumed condition; never a diagnostic success seal."""
    _reference_condition_lease(book)
    book._reference_live_owner = lambda attempt, claim, owner: _reference_transition_owner(
        book, attempt, claim, owner
    )
    claim = book.claim_reference_condition(pair_sha256)  # uncertainty remains spent
    first = claim["reference_attempt"]
    try:
        pair = book._read(first + ".reference-pair.json")
        loc = _locations(first)
        need(book.root == loc.ledger, "REFERENCE_LEDGER_SCOPE")
        observed = {}

        def original(path, maximum=32768):
            data = read_owned(path, maximum)
            need(type(data) is bytes and 0 < len(data) <= maximum, "REFERENCE_ORIGINAL_BOUND")
            observed[str(path)] = (maximum, digest(data))
            return data

        names = (
            "intent",
            "entry",
            "context-binding",
            "close",
            "preowner",
            "terminal",
            "manager-exit",
            "unit-result",
            "unit-cleanup",
        )
        rows = {name: book._read(first + "." + name + ".json") for name in names}
        closed, preowner = rows["close"], rows["preowner"]
        need(
            closed["owner_state"] == "CLOSED"
            and closed["failure"] == "REFERENCE_INIT_OBSERVATION"
            and closed["connection_attempt_id"] == first
            and closed["method_sha256"] == pair["method_sha256"],
            "REFERENCE_NORMAL_PARENT",
        )
        failure = read_runner_failure(loc.control, original)
        need(
            failure is not None and failure["reason"] == "REFERENCE_INIT_OBSERVATION",
            "REFERENCE_NORMAL_STOP",
        )
        observation = failure.get("reference_init_observation")
        need(
            observation is not None
            and observation["parent_closed"]
            and observation["constructor_status"] == "READY"
            and observation["reference_control_sha256"] == pair["reference_control_sha256"],
            "REFERENCE_READY_REQUIRED",
        )
        startup = digest(original(loc.control / "startup.json"))
        invocation = preowner["unit"]["InvocationID"]
        need(
            preowner["connection_attempt_id"] == first and preowner["startup_sha256"] == startup,
            "REFERENCE_MANAGER_BINDING",
        )
        expected_exit = dict(manager_returncode=1, invocation_id=invocation, startup_sha256=startup)
        need(
            type(rows["manager-exit"].get("manager_returncode")) is int
            and type(rows["unit-result"].get("manager_returncode")) is int
            and type(rows["unit-result"].get("client_returncode")) is int
            and rows["manager-exit"] == expected_exit
            and rows["unit-result"] == dict(expected_exit, client_returncode=1),
            "REFERENCE_NORMAL_MANAGER",
        )
        terminal = rows["terminal"]
        preowner_sha = digest(raw_json(preowner))
        need(
            terminal["preowner_sha256"] == preowner_sha
            and terminal["terminal"]["InvocationID"] == invocation
            and terminal["terminal"]["ExecMainCode"] == "1"
            and terminal["terminal"]["ExecMainStatus"] == "1",
            "REFERENCE_NORMAL_MANAGER",
        )
        need(
            rows["unit-cleanup"]
            == dict(
                preowner_sha256=preowner_sha,
                owned_cleanup_proven=True,
                external_effects="UNKNOWN",
                input_publishable=False,
            ),
            "REFERENCE_UNIT_CLEANUP",
        )
        # The persisted receipt alone is insufficient: independently check the current
        # manager absence, retained invocation and recursive empty original group.
        _recover_preowner(preowner, book)
        catalog_raw = original(loc.release / "release-catalog.json")
        catalog = json.loads(catalog_raw)
        sources = {key: catalog[key] for key in _sources(first)}
        need(digest(raw_json(sources)) == pair["method_sha256"], "REFERENCE_SOURCE_BINDING")
        for key, name in _sources(first).items():
            need(
                digest(original(loc.release / name, 262144)) == sources[key],
                "REFERENCE_SOURCE_DRIFT",
            )
        need(
            digest(original(loc.control / "policy.json"))
            == pair["policy_sha256"]
            == book.policy_sha,
            "REFERENCE_POLICY_BINDING",
        )
        control = original(loc.control / "reference-control.json", 4096)
        need(digest(control) == pair["reference_control_sha256"], "REFERENCE_CONTROL_BINDING")
        expected_control = {
            "schema_id": "qm.ivv.reference-control.v1",
            **{
                key: pair[key]
                for key in (
                    "nonce",
                    "reference_attempt",
                    "capture_attempt",
                    "reference_context",
                    "capture_context",
                )
            },
            "catalog_sha256": digest(catalog_raw),
            "sdk_pins_sha256": pair["sdk_pins_sha256"],
            "policy_sha256": pair["policy_sha256"],
        }
        need(json.loads(control) == expected_control, "REFERENCE_CONTROL_BINDING")
        plan = json.loads(original(loc.control / "plan.json"))
        need(
            digest(original(loc.control / "reference-pair.json", 4096)) == pair_sha256,
            "REFERENCE_PAIR_ORIGINAL",
        )
        book.require_reference_plan(first, plan, pair)
        need(
            rows["entry"]["startup_sha256"] == startup
            and rows["context-binding"]["startup_sha256"] == startup,
            "REFERENCE_CONTEXT_STARTUP",
        )
        need(
            plan["reference_init_ref"]
            == {
                "path": str(loc.control / "reference-control.json"),
                "sha256": pair["reference_control_sha256"],
            },
            "REFERENCE_PLAN_BINDING",
        )
        binding = producer.validate_provider_binding(
            raw_json(catalog["provider_binding"]), pair["provider_binding_sha256"]
        )
        configuration = dict(
            control=binding.control_sha,
            launcher=binding.launcher_sha,
            profile=producer.RESTORE_PROFILE,
            template=producer.RESTORE_TEMPLATE,
        )
        cohort = dict(
            unit=binding.unit,
            invocation=binding.invocation,
            cgroup=binding.cgroup,
            cohort=binding.cohort,
            mnt=binding.mnt,
            net=binding.net,
        )
        need(
            digest(raw_json(configuration)) == pair["provider_config_sha256"]
            and digest(raw_json(cohort)) == pair["provider_cohort_sha256"],
            "REFERENCE_PROVIDER_BINDING",
        )
        boot, closes_observed = book.reference_clock()
        sample_boot, sample_started = book.reference_clock()
        need(sample_boot == boot and closes_observed <= sample_started, "REFERENCE_FRESH_CLOCK")
        native.verified_provider_snapshot(producer, binding)
        sdk_raw = original(loc.control / "sdk-pins.json")
        need(
            digest(sdk_raw) == pair["sdk_pins_sha256"]
            and plan["sdk_pins_ref"]
            == {"path": str(loc.control / "sdk-pins.json"), "sha256": pair["sdk_pins_sha256"]},
            "REFERENCE_SDK_BINDING",
        )
        sdk_rows = json.loads(sdk_raw)["pins"]
        need(type(sdk_rows) is list and 12 <= len(sdk_rows) <= 128, "SDK_PINS_COUNT")
        paths = set()
        for row in sdk_rows:
            rel = row["relative_path"]
            need(
                type(rel) is str
                and re.fullmatch(
                    r"(?:moomoo|google/protobuf|google/_upb)/[A-Za-z0-9_./-]+\.(?:py|so)", rel
                )
                and ".." not in Path(rel).parts
                and rel not in paths,
                "SDK_PIN_ROLE",
            )
            paths.add(rel)
            body = native._protected_bytes(str(SDK / rel), 1048576)
            need(digest(body.replace(b"\r\n", b"\n")) == row["LF_sha256"], "SDK_PIN_DRIFT")
        end_boot, sample_finished = book.reference_clock()
        need(
            end_boot == boot and sample_started <= sample_finished <= sample_started + 2,
            "REFERENCE_FRESH_CLOCK",
        )
        for path, (maximum, pin) in observed.items():
            need(digest(read_owned(Path(path), maximum)) == pin, "REFERENCE_ORIGINAL_DRIFT")
        need(
            all(book._read(first + "." + name + ".json") == body for name, body in rows.items()),
            "REFERENCE_LEDGER_DRIFT",
        )
        _reference_condition_lease(book)
        evidence = {
            "closed_originals": {name: digest(raw_json(body)) for name, body in rows.items()},
            "files": {path: pin for path, (_, pin) in observed.items()},
            "pair_sha256": pair_sha256,
        }
        evidence_sha = digest(raw_json(evidence))
        fresh = dict(
            schema_id="qm.ivv.reference-fresh.v1",
            pair_sha256=pair_sha256,
            evidence_sha256=evidence_sha,
            boot_id=boot,
            closes_observed=closes_observed,
            sample_started=sample_started,
            sample_finished=sample_finished,
        )
        book._write(first + ".reference-evidence.json", evidence)
        book._write(first + ".reference-fresh.json", fresh)
        outcome = dict(
            schema_id="qm.ivv.reference-condition.v1",
            state="POSITIVE",
            pair_sha256=pair_sha256,
            claim_sha256=digest(raw_json(claim)),
            reference_attempt=first,
            capture_attempt=pair["capture_attempt"],
            close_sha256=digest(raw_json(closed)),
            evidence_sha256=evidence_sha,
            fresh_sha256=digest(raw_json(fresh)),
        )
        book._write(first + ".reference-condition.json", outcome)
        return {"pair_sha256": pair_sha256, "outcome_sha256": digest(raw_json(outcome))}
    except BaseException as error:
        # Even failed result persistence leaves the exclusive claim permanently occupied.
        book._write(
            first + ".reference-condition.json",
            {
                "schema_id": "qm.ivv.reference-condition.v1",
                "state": "NEGATIVE",
                "pair_sha256": pair_sha256,
                "claim_sha256": digest(raw_json(claim)),
                "reason": reason(error),
            },
        )
        raise


class _Channel:
    def __init__(self, s):
        self.s = s
        self.origin = identity(os.fstat(s.fileno()))
        self.s.setsockopt(socket.SOL_SOCKET, socket.SO_PASSCRED, 1)
        self.s.settimeout(20)

    def check(self):
        need(
            identity(os.fstat(self.s.fileno())) == self.origin
            and self.s.type == socket.SOCK_SEQPACKET,
            "CONTROL_FD_SWAPPED",
        )

    def send(self, obj):
        self.check()
        raw = raw_json(obj)
        need(0 < len(raw) <= 8192 and self.s.send(raw) == len(raw), "CONTROL_SEND")

    def recv(self, sender, *, nonblocking=False):
        import struct

        self.check()
        if nonblocking:
            previous = self.s.gettimeout()
            try:
                self.s.settimeout(0)
                data, anc, flags, _ = self.s.recvmsg(
                    8192, socket.CMSG_SPACE(12), socket.MSG_DONTWAIT
                )
            finally:
                self.s.settimeout(previous)
        else:
            data, anc, flags, _ = self.s.recvmsg(8192, socket.CMSG_SPACE(12))
        if not data and not anc and flags == 0:
            raise Refused("CONTROL_EOF")
        need(
            data
            and flags == 0
            and len(anc) == 1
            and anc[0][:2] == (socket.SOL_SOCKET, socket.SCM_CREDENTIALS)
            and len(anc[0][2]) == 12
            and struct.unpack("3i", anc[0][2]) == (sender, 0, 0),
            "CONTROL_SENDER",
        )
        return json.loads(data)


def _fds():
    # The listdir implementation opens a transient descriptor itself.
    result = set()
    for n in os.listdir("/proc/self/fd"):
        try:
            os.fstat(int(n))
        except OSError as e:
            if e.errno == 9:
                continue
            raise
        result.add(int(n))
    return result


def _stdio():
    for fd in (0, 1, 2):
        s = os.fstat(fd)
        need(stat.S_ISCHR(s.st_mode) and s.st_rdev == os.makedev(1, 3), "UNEXPECTED_STDIO")


def _landlock(*, additional=False):
    loc = _locations(additional)
    """Restrict reads, writes and exec, including access through proc magic links."""
    libc = ctypes.CDLL(None, use_errno=True)

    def call(number, *args):
        ret = libc.syscall(number, *args)
        if ret < 0:
            raise OSError(ctypes.get_errno(), "landlock")
        return ret

    need(call(444, None, 0, 1) >= 5, "LANDLOCK_ABI")
    # ABI5 covers every file modification right including IOCTL_DEV. Deny
    # new exec entirely, and expose only public runtime/source/control bytes;
    # readonly host mounts alone would still expose HOME/key/env payloads.
    rights = (1 << 16) - 1
    attr = ctypes.c_uint64(rights)
    rules = call(444, ctypes.byref(attr), 8, 0)
    try:
        read = (1 << 2) | (1 << 3)
        actor, _ = _process(os.getpid())
        need(PurePosixPath(actor["cgroup"]).name.startswith("ivv-owned-"), "LANDLOCK_OWNED_CGROUP")
        paths = [
            (Path("/usr"), read),
            (loc.release, read),
            (SDK, read),
            (loc.control, read),
            (loc.child, read | (1 << 1) | (1 << 7) | (1 << 8) | (1 << 14)),
            (loc.ledger, read | (1 << 1) | (1 << 8)),
            (CG / actor["cgroup"].lstrip("/"), read),
        ]
        paths.extend(
            (Path("/proc") / str(os.getpid()) / name, 1 << 2)
            for name in ("stat", "status", "cgroup", "mountinfo")
        )
        paths.extend(
            (Path(name), 1 << 2)
            for name in ("/proc/sys/kernel/cap_last_cap", "/etc/ld.so.cache", "/etc/localtime")
        )
        for path, bits in paths:
            path = Path(path).resolve(strict=True)
            directory = stat.S_ISDIR(path.stat().st_mode)
            need(directory or not bits & (1 << 3), "LANDLOCK_READ_ORIGIN")
            fd = os.open(
                path,
                os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW | (os.O_DIRECTORY if directory else 0),
            )
            try:

                class Rule(ctypes.Structure):
                    _pack_ = 1
                    _fields_ = [("access", ctypes.c_uint64), ("fd", ctypes.c_int32)]

                rule = Rule(bits, fd)
                call(445, rules, 1, ctypes.byref(rule), 0)
            finally:
                _close_fd(fd)
        _libcall("prctl", 38, 1, 0, 0, 0)
        call(446, rules, 0)
    finally:
        _close_fd(rules)


def _drop_caps():
    _libcall("prctl", 28, 0xF, 0, 0, 0)  # lock NOROOT and NO_SETUID_FIXUP
    for cap in range(int(Path("/proc/sys/kernel/cap_last_cap").read_text()) + 1):
        _libcall("prctl", 24, cap, 0, 0, 0)
    header = (ctypes.c_uint32 * 2)(0x20080522, 0)
    data = (ctypes.c_uint32 * 6)()
    _libcall("capset", ctypes.byref(header), ctypes.byref(data))
    fields = dict(
        row.split(":", 1)
        for row in Path("/proc/self/status").read_text().splitlines()
        if ":" in row
    )
    need(
        all(int(fields[k], 16) == 0 for k in ("CapEff", "CapPrm", "CapInh", "CapBnd", "CapAmb"))
        and fields["NoNewPrivs"].strip() == "1",
        "CHILD_PRIVILEGES",
    )


def _writable_mounts(producer, *, additional=False):
    loc = _locations(additional)
    raw = Path("/proc/self/mountinfo").read_bytes()
    mounts = producer._visible_mounts(producer.parse_mountinfo(raw))
    need(
        {m.target for m in mounts.values() if "rw" in m.options}
        == {str(loc.child), str(loc.ledger)},
        "CHILD_WRITE_MOUNTS",
    )


def _child_namespace(channel, producer, *, additional=False):
    loc = _locations(additional)
    for fd in _fds() - {channel.s.fileno(), 0, 1, 2}:
        os.close(fd)
    null = os.open("/dev/null", os.O_RDWR | os.O_NOFOLLOW)
    try:
        for fd in (0, 1, 2):
            os.dup2(null, fd, inheritable=False)
    finally:
        _close_fd(null)
    _stdio()
    channel.check()
    need(_fds() == {0, 1, 2, channel.s.fileno()}, "INHERITED_FD")
    ns = _private_mounts()
    for path in (loc.child, loc.ledger):
        _bind(path)
    _attr(Path("/"), True, True)
    for path in (loc.child, loc.ledger):
        _attr(path, False, False)
    _for_task(_writable_mounts, additional)(producer)
    _for_task(_landlock, additional)()
    _drop_caps()
    return ns


# Release-observed raw bytes of the fixed SDK protobuf package initializer.
_SDK_PB_INITIALIZER_SHA256 = "49f94f30ceac89078d784ddcad041e637100bd1e61f6e238b1347c8256d26907"


def _session_pb_directory(initial_path, current):
    need(all(type(entry) is str for entry in current), "PYTHON_SEARCH_PATH")
    if current == initial_path:
        return None

    package = SDK / "moomoo/common/pb"
    directory = str(package)
    need(
        directory not in initial_path and current == (*initial_path, directory),
        "PYTHON_SEARCH_PATH",
    )
    protected(package)
    need(stat.S_ISDIR(package.stat().st_mode), "PYTHON_SEARCH_PATH")
    need(os.statvfs(package).f_flag & os.ST_RDONLY, "PYTHON_SEARCH_WRITABLE")

    name = "moomoo.common.pb"
    initializer = package / "__init__.py"
    source = str(initializer)
    module = sys.modules.get(name)
    need(type(module) is types.ModuleType, "PYTHON_SEARCH_PATH")
    fields = vars(module)
    spec = fields.get("__spec__")
    loader = fields.get("__loader__")
    need(
        type(spec) is importlib.machinery.ModuleSpec
        and type(loader) is importlib.machinery.SourceFileLoader
        and vars(spec).get("loader") is loader,
        "PYTHON_SEARCH_PATH",
    )
    names = (fields.get("__name__"), vars(spec).get("name"), vars(loader).get("name"))
    origins = (fields.get("__file__"), vars(spec).get("origin"), vars(loader).get("path"))
    locations = (fields.get("__path__"), vars(spec).get("submodule_search_locations"))
    need(
        all(type(item) is str and item == name for item in names)
        and all(type(item) is str and item == source for item in origins)
        and all(
            type(paths) is list
            and len(paths) == 1
            and type(paths[0]) is str
            and paths[0] == directory
            for paths in locations
        ),
        "PYTHON_SEARCH_PATH",
    )
    read_ref({"path": source, "sha256": _SDK_PB_INITIALIZER_SHA256}, initializer, 64, True)
    return package


def _runtime(
    plan,
    helper,
    ns,
    catalog,
    producer,
    *,
    additional=False,
    origin_phase="UNKNOWN",
    initial_path=None,
):
    loc = _locations(additional)
    need(os.stat("/proc/self/ns/mnt").st_ino == ns, "OWN_NAMESPACE_DRIFT")
    _for_task(_writable_mounts, additional)(producer)
    origin = {
        "schema": "qm.ivv.runtime-origin-failure.v1",
        "phase": origin_phase
        if type(origin_phase) is str and origin_phase in ("INITIAL", "SESSION")
        else "UNKNOWN",
        "predicate": "UNKNOWN",
        "outcome": "EXCEPTION",
    }

    def evaluated(predicate, expression):
        origin["predicate"] = predicate
        return expression()

    resolved_executable = None
    executable_origin = None

    def executable():
        nonlocal resolved_executable
        resolved_executable = Path("/proc/self/exe").resolve()
        return resolved_executable == Path("/usr/bin/python3.12")

    try:
        need(
            evaluated("SDK_ROOT", lambda: plan["sdk_root"] == str(SDK))
            and evaluated("PYTHON_VERSION", lambda: sys.version_info[:2] == (3, 12))
            and evaluated("EXECUTABLE", executable),
            "RUNTIME_ORIGIN",
            _origin=origin,
        )
    except BaseException as error:
        _carry_executable_origin(error, None)
        if (
            _recovery_mode(additional)
            and origin["predicate"] == "EXECUTABLE"
            and origin["outcome"] == "FIRST_FALSE"
        ):
            try:
                proof = _prove_executable_identity(catalog.get("python_sha256"), ns)
                if proof["stage"] == "VERIFIED" and proof["descriptor_close"] == "CLOSED":
                    executable_origin = select_executable_origin(
                        {
                            "schema": "qm.ivv.executable-origin.v1",
                            "method": "NAMED_OBJECT",
                            "phase": origin["phase"],
                            "namespace_inode": ns,
                            "python_sha256": catalog["python_sha256"],
                            "kernel_mount_readonly": proof["kernel_mount_readonly"],
                        }
                    )
                else:
                    origin["executable_identity"] = {
                        "schema": "qm.ivv.executable-identity-failure.v1",
                        "stage": proof["stage"],
                        "descriptor_close": proof["descriptor_close"],
                    }
            except BaseException:
                executable_origin = None
                origin["executable_identity"] = {
                    "schema": "qm.ivv.executable-identity-failure.v1",
                    "stage": "INTERNAL",
                    "descriptor_close": "UNKNOWN",
                }
            if executable_origin is None:
                try:
                    origin["executable_observation"] = _observe_executable(resolved_executable, ns)
                except BaseException:
                    pass  # Optional evidence cannot replace the original refusal or ownership.
        if executable_origin is None:
            _carry_origin(error, origin)
            raise
    try:
        home = os.environ.get("HOME")
        need(home and Path(home).is_absolute(), "HOME_NOT_READY")
        log = Path(home) / ".com.moomoo.OpenD" / "Log"
        need(
            log.resolve(strict=True) == log
            and stat.S_ISDIR(log.stat().st_mode)
            and os.statvfs(log).f_flag & os.ST_RDONLY,
            "HOME_LOG_PREREQUISITE",
        )
        for key, name in _sources(additional).items():
            path = loc.release / name
            read_ref({"path": str(path), "sha256": catalog[key]}, path, 262144, True)
        checked_session = (
            _recovery_mode(additional) and origin_phase == "SESSION" and initial_path is not None
        )
        search_path = tuple(sys.path) if checked_session else sys.path
        pb = _session_pb_directory(initial_path, search_path) if checked_session else None
        for path in search_path:
            if Path(path).exists():
                resolved = Path(path).resolve(strict=True)
                need(
                    resolved.is_relative_to("/usr/lib/python3.12")
                    or resolved == SDK
                    or (pb is not None and resolved == pb),
                    "PYTHON_SEARCH_PATH",
                )
                protected(resolved)
                need(os.statvfs(resolved).f_flag & os.ST_RDONLY, "PYTHON_SEARCH_WRITABLE")
        need(Path(sys.executable).resolve() == Path("/usr/bin/python3.12"), "PYTHON_EXECUTABLE")
        exe = Path("/usr/bin/python3.12")
        read_ref(
            {"path": str(exe), "sha256": catalog["python_sha256"]}, exe, 32 * 1024 * 1024, True
        )
        source_pins = json.loads(read_ref(plan["sdk_pins_ref"], loc.control / "sdk-pins.json"))
        rows = source_pins["pins"]
        need(type(rows) is list and 12 <= len(rows) <= 128, "SDK_PINS_COUNT")
        names = set()
        for r in rows:
            rel = (
                r.get("relative_path")
                or str(r.get("path", "")).replace(chr(92), "/").split("/site-packages/")[-1]
            )
            need(
                re.fullmatch(
                    r"(?:moomoo|google/protobuf|google/_upb)/[A-Za-z0-9_./-]+\.(?:py|so)", rel
                )
                and ".." not in Path(rel).parts
                and rel not in names,
                "SDK_PIN_ROLE",
            )
            names.add(rel)
            path = SDK / rel
            protected(path)
            need(
                path.resolve(strict=True) == path
                and os.statvfs(path).f_flag & os.ST_RDONLY
                and digest(path.read_bytes().replace(b"\r\n", b"\n")) == r["LF_sha256"],
                "SDK_PIN_DRIFT",
            )
        need(
            any("/pb/" in n or "_pb2.py" in n for n in names)
            and "moomoo/quote/open_quote_context.py" in names,
            "PROTO_AND_QUOTE_ORIGIN",
        )
        # PathFinder performs no package import. Production imports only after once.
        spec = importlib.machinery.PathFinder.find_spec("moomoo", search_path)
        need(spec and Path(spec.origin) == SDK / "moomoo/__init__.py", "SDK_IMPORT_ORIGIN")
        if checked_session:
            current = tuple(sys.path)
            need(
                all(type(entry) is str for entry in current) and current == search_path,
                "PYTHON_SEARCH_PATH",
            )
        if _recovery_mode(additional) and executable_origin is None:
            executable_origin = select_executable_origin(
                {
                    "schema": "qm.ivv.executable-origin.v1",
                    "method": "EXACT_PATH",
                    "phase": origin["phase"],
                    "namespace_inode": ns,
                    "python_sha256": catalog["python_sha256"],
                    "kernel_mount_readonly": "UNKNOWN",
                }
            )
        return {
            **({"executable_origin": executable_origin} if executable_origin is not None else {}),
            "namespace_inode": ns,
            "sdk_pins_sha256": plan["sdk_pins_sha256"],
            "python_sha256": catalog["python_sha256"],
        }

    except BaseException as error:
        _carry_executable_origin(error, executable_origin)
        raise


def _environment():
    # HOME is our own public path prerequisite. Do not enumerate, copy, hash or
    # export any other inherited environment value before discarding it.
    home = os.environ.get("HOME")
    need(isinstance(home, str) and Path(home).is_absolute(), "HOME_NOT_READY")
    log = Path(home) / ".com.moomoo.OpenD" / "Log"
    protected(log)
    need(
        log.resolve(strict=True) == log
        and stat.S_ISDIR(log.stat().st_mode)
        and os.statvfs(log).f_flag & os.ST_RDONLY,
        "HOME_LOG_PREREQUISITE",
    )
    os.environ.clear()
    os.environ.update({"HOME": home, "PATH": "/usr/bin:/bin", "LC_ALL": "C"})


class _Provider:
    """Single independently sampled provider, with monotonic per-inode growth."""

    def __init__(
        self, native, producer, helper, plan, budget_ref, *, additional=False, binding=None
    ):
        self.locations = _locations(additional)
        self.recovery = _recovery_mode(additional)
        self.native = native
        self.producer = producer
        self.helper = helper
        self.plan = plan
        self.budget_ref = budget_ref
        self.binding = None
        if self.recovery:
            self.binding = producer.ProviderExecution.verified_record(binding)
        self.series = (
            native.RestoredRoleGrowth(producer, self.binding)
            if self.binding is not None
            else native.RoleGrowth()
        )
        self.first = None
        self.last = None
        self.next = 0
        self.peak = 0

    def peer(self, pid):
        reader = self.producer.OperatorReader(self.binding)
        reader.deadline = min(time.monotonic() + 2, self.plan["started_monotonic"] + 480)
        try:
            self.native._operator_identity(self.producer, self.binding, self.gateway_gid, reader)
            fd = reader.processes[self.binding.cohort[2][0]][0]
            sockets = reader.socket_inodes(fd)
            pair = _owned_peer(pid, vendor_sockets=sockets)
            need(sockets == reader.socket_inodes(fd) and not reader.finish(), "PROVIDER_DRIFT")
            return pair
        finally:
            reader.close()

    def verify_network(self, scope):
        """Immediate pre-GO proof, independent of periodic growth and resource sampling."""
        deadline = min(time.monotonic() + 2, self.plan["started_monotonic"] + 480)
        gid = self.native._operator_sources(self.producer, self.binding)
        reader = self.producer.OperatorReader(self.binding)
        reader.deadline = deadline
        try:
            self.native._operator_identity(self.producer, self.binding, gid, reader)
            need(
                digest(raw_json([reader.listener_inode])) == self.first["listener_binding_sha256"],
                "PROVIDER_DRIFT",
            )
            scope.check_pid()
            vendor = reader.processes[self.binding.cohort[2][0]][0]
            child = reader.directory(str(scope.pid), reader.directory("/proc"))
            held = [
                reader.keep(os.open("ns/net", os.O_RDONLY | os.O_CLOEXEC, dir_fd=process))
                for process in (vendor, child)
            ]
            identities = []
            for process, fd in zip((vendor, child), held, strict=True):
                named = os.stat("ns/net", dir_fd=process)
                current = os.fstat(fd)
                identity = (current.st_dev, current.st_ino)
                need(
                    current.st_ino == self.binding.net and identity == (named.st_dev, named.st_ino),
                    "PROVIDER_IDENTITY",
                )
                identities.append(identity)
            need(identities[0] == identities[1], "PROVIDER_IDENTITY")
            need(not reader.finish(), "PROVIDER_DRIFT")
            scope.check_pid()
        finally:
            reader.close()
        need(time.monotonic() < deadline, "PROVIDER_SAMPLE_DEADLINE")

    def sample(self):
        start = time.monotonic()
        if self.binding is not None:
            self.gateway_gid = self.native._operator_sources(self.producer, self.binding)
        reader = (
            self.producer.OperatorReader(self.binding)
            if self.binding is not None
            else self.producer.PosixReader()
        )
        reader.deadline = min(start + 2, self.plan["started_monotonic"] + 480)
        try:
            if self.binding is not None:
                identity_doc = self.native._operator_identity(
                    self.producer, self.binding, self.gateway_gid, reader
                )
            else:
                identity_doc = reader.identity()
                self.producer._check_identity(identity_doc)
            vendor_pid = self.binding.cohort[2][0] if self.binding is not None else 705711
            vendor = reader.processes[vendor_pid][0]

            def listeners():
                inodes = reader.socket_inodes(vendor)
                rows = reader.read(vendor, "net/tcp", 262144).splitlines()[1:]
                return sorted(
                    int(row.split()[9])
                    for row in rows
                    if len(row.split()) >= 10
                    and row.split()[1] == b"0100007F:2B68"
                    and row.split()[3] == b"0A"
                    and int(row.split()[9]) in inodes
                )

            listener = listeners()
            need(len(listener) == 1, "OWNED_LISTENER")
            endpoint, configuration = self.native.trusted_quote_configuration(self.plan)
            increment = self.series.sample(reader)
            resources = self.native._provider_controls(reader)
            budget = json.loads(read_ref(self.budget_ref, self.locations.control / "budget.json"))
            need(
                set(budget) == {"G", "P"}
                and all(type(v) is int and v > 0 for v in budget.values()),
                "BUDGET_SHAPE",
            )
            fs = os.statvfs(self.locations.child)
            sample = {
                "incremental_bytes": increment,
                "G": budget["G"] + increment,
                "P": budget["P"] + increment,
                "free": fs.f_bavail * fs.f_frsize,
            }
            need(
                sample["G"] <= (12884901888 if self.recovery else 10500000000)
                and sample["P"] <= (6442450944 if self.recovery else 4500000000)
                and sample["free"] >= 53687091200,
                "MONITOR_THRESHOLD",
            )
            need(not reader.finish() and listener == listeners(), "PROVIDER_DRIFT")
            row = reader.processes[vendor_pid][2]
            actual = {
                "provider_actor": {
                    "pid": row["pid"],
                    "uid": row["uids"][0],
                    "start_ticks": row["start"],
                    "exe_sha256": (
                        "e05b901dbe9107061b954a7fe3c059916c4a1e580d8f0a57277d402438898601"
                    ),
                    "machine_identity_sha256": identity_doc["machine"],
                },
                "endpoint": endpoint,
                "identity_binding_sha256": digest(raw_json(identity_doc)),
                "configuration_binding_sha256": configuration,
                "listener_binding_sha256": digest(raw_json(listener)),
            }
            need(self.first is None or self.first == actual, "PROVIDER_DRIFT")
            self.first = actual
            self.last = {
                **actual,
                "resource_values": resources,
                "sample": sample,
                "sampled_monotonic": time.monotonic(),
            }
            self.peak = max(self.peak, increment)
        finally:
            primary = sys.exc_info()[1]
            try:
                reader.close()
            except BaseException as e:
                raise Refused((reason(primary) + "+" if primary else "") + reason(e)) from None
        need(time.monotonic() - start < 2, "PROVIDER_SAMPLE_DEADLINE")
        self.next = (self.next or start) + 5
        return self.last


def _child_kernel(scope, producer, endpoint, initial, *, additional=False):
    loc = _locations(additional)
    scope.check_pid()
    path = Path("/proc") / str(scope.pid)
    ns = (path / "ns/mnt").stat().st_ino
    need(ns != os.stat("/proc/self/ns/mnt").st_ino, "CHILD_NAMESPACE_SHARED")
    raw = (path / "mountinfo").read_bytes()
    visible = producer._visible_mounts(producer.parse_mountinfo(raw))
    need(
        {m.target for m in visible.values() if "rw" in m.options}
        == {str(loc.child), str(loc.ledger)},
        "CHILD_WRITE_MOUNTS",
    )
    status = (path / "status").read_text().splitlines()
    fields = dict(line.split(":", 1) for line in status if ":" in line)
    need(
        fields["NoNewPrivs"].strip() == "1"
        and all(
            int(fields[k], 16) == 0 for k in ("CapEff", "CapBnd", "CapAmb", "CapInh", "CapPrm")
        ),
        "CHILD_PRIVILEGES",
    )
    need(
        identity((path / "exe").stat()) == identity(Path("/proc/self/exe").stat()),
        "CHILD_EXECUTABLE",
    )
    if initial:
        fdpath = path / "fd"
        objects = {int(e.name): e.stat() for e in fdpath.iterdir()}
        need(
            len(objects) == 4
            and all(
                stat.S_ISCHR(objects[k].st_mode) and objects[k].st_rdev == os.makedev(1, 3)
                for k in (0, 1, 2)
            )
            and [s.st_ino for s in objects.values() if stat.S_ISSOCK(s.st_mode)] == [endpoint],
            "CHILD_FD_CLOSURE",
        )
    scope.check_pid()
    return {"namespace_inode": ns, "mountinfo_sha256": digest(raw), "capture_actor": scope.child}


def _owned_peer(pid, *, vendor_sockets=None):
    def sockets(path):
        out = set()
        for entry in path.iterdir():
            try:
                s = entry.stat()
            except FileNotFoundError:
                continue
            if stat.S_ISSOCK(s.st_mode):
                out.add(s.st_ino)
        return out

    rows = (Path("/proc") / str(pid) / "net/tcp").read_bytes().splitlines()
    need(len(rows) <= 4096, "PEER_TABLE_BOUND")
    child = sockets(Path("/proc") / str(pid) / "fd")
    vendor = sockets(Path("/proc/705711/fd")) if vendor_sockets is None else vendor_sockets
    table = [line.split() for line in rows[1:]]
    pairs = []
    for row in table:
        need(len(row) >= 10 and row[9].isdigit(), "PEER_TABLE")
        if int(row[9]) in child and row[3] == b"01":
            need(
                row[2] == b"0100007F:2B68" and row[1].startswith(b"0100007F:"),
                "FOREIGN_CAPTURE_PEER",
            )
            peers = [
                r
                for r in table
                if r[1:3] == [row[2], row[1]] and r[3] == b"01" and int(r[9]) in vendor
            ]
            need(len(peers) == 1, "CAPTURE_PEER_NOT_PROVIDER_OWNED")
            pairs.append((int(row[9]), int(peers[0][9])))
    need(len(pairs) <= 1, "SECOND_CAPTURE_PEER")
    return pairs[0] if pairs else None


def _validate_windows_fields(fields, extra):
    additional = extra is not None
    need(
        set(fields)
        == ({"numeric_runtime_sha256"} if additional else set())
        | {
            "job_id",
            "windows_policy_sha256",
            "output_root_digest",
            "code",
            "adapter_sha256",
            "gate_sha256",
            "runtime",
        },
        "WINDOWS_GO_FIELDS",
    )
    if additional:
        need(
            fields["job_id"] == extra.APPROVED.job_id
            and fields["windows_policy_sha256"] == extra.WINDOWS
            and all(
                _digest_pin(fields[k])
                for k in (
                    "numeric_runtime_sha256",
                    "adapter_sha256",
                    "gate_sha256",
                    "output_root_digest",
                )
            ),
            "ADDITIONAL_WINDOWS_BINDING",
        )

        code, runtime = fields["code"], fields["runtime"]
        need(
            type(code) is dict
            and set(code)
            == {
                "kernel_version",
                "kernel_sha256",
                "policy_sha256",
                "adapter_sha256",
                "legacy_packaged_ancestor",
            }
            and code["kernel_version"] == "native-daily-v2"
            and all(_digest_pin(v) for k, v in code.items() if k != "kernel_version")
            and type(runtime) is dict
            and set(runtime) == {"python", "calendar", "numpy", "pandas"}
            and all(type(v) is str and 0 < len(v) <= 256 for v in runtime.values()),
            "ADDITIONAL_WINDOWS_RUNTIME",
        )


def _digest_pin(value):
    return type(value) is str and re.fullmatch("[0-9a-f]{64}", value) and value != "0" * 64


def _seed(values, startup, helper, issuer, *, started=None):
    extra = values.get("_additional")
    additional = _task_mode(values)
    loc = _locations(additional)
    family = extra.FAMILY if additional else FAMILY
    plan = dict(values["seed_ref"])
    helper._validate_production_plan_keys(plan, schema="qm.ivv.capture-plan" + family)
    plan["started_monotonic"] = time.monotonic() if started is None else started
    helper._validate_fixed_plan(plan, schema="qm.ivv.capture-plan" + family)
    if "reference_init_ref" in plan:
        need(_recovery_mode(additional), "REFERENCE_RECOVERY_ONLY")
        helper._read_reference_control(plan)
    if "reference_pair_ref" in plan:
        need(_recovery_mode(additional), "REFERENCE_RECOVERY_ONLY")
        helper._read_reference_pair(plan)
    need(
        plan["sdk_root"] == str(SDK)
        and plan["receipt_root"] == str(loc.receipt)
        and plan["catalog_sha256"] == startup["catalog_ref"]["sha256"]
        and plan["capture_helper_sha256"] == values["catalog_ref"]["capture_helper_sha256"],
        "FIXED_PLAN_PATH",
    )
    need(
        plan["provider_evidence_ref"]
        == {"path": str(loc.control / "provider.json"), "sha256": "0" * 64},
        "PROVIDER_PENDING",
    )
    for key, name in (
        ("dates_ref", "dates.txt"),
        ("input_window_ref", "input-window.json"),
        ("window_ref", "window.json"),
        ("schedule_ref", "schedule.json"),
        ("sdk_pins_ref", "sdk-pins.json"),
        ("policy_ref", "policy.json"),
    ):
        read_ref(plan[key], loc.control / name)
    policy = json.loads(read_ref(plan["policy_ref"], loc.control / "policy.json"))
    if _recovery_mode(additional):
        need(
            plan["policy_ref"] == startup["capture_policy_ref"]
            and digest(raw_json(policy)) == extra.policy_sha
            and plan["recovery"] == extra.binding(),
            "RECOVERY_POLICY_BINDING",
        )
    elif additional:
        need(
            plan["policy_ref"] == startup["capture_policy_ref"]
            and digest(raw_json(policy)) == extra.POLICY,
            "ADDITIONAL_POLICY_PIN",
        )
    else:
        issuer.validate_trusted_policy(helper, policy, plan, AUTH)
    if not _recovery_mode(additional):
        _validate_windows_fields(values["go_fields_ref"], extra)
    if additional:
        home = loc.child.parent / "home"
        need(os.environ.get("HOME") == str(home), "ADDITIONAL_HOME")
        protected(home)
        root = (
            Path("/var/lib/quantmesh-ivv-recovery")
            if _recovery_mode(additional)
            else ADDITIONAL_ROOT
        )
        protected(root)
        need(stat.S_IMODE(root.stat().st_mode) == 0o700, "ADDITIONAL_PRIVATE_ROOT")
    for path in (loc.control, loc.child, loc.ledger):
        protected(path)
        need(stat.S_IMODE(path.stat().st_mode) == 0o700, "PRIVATE_CONTROL_DIRECTORY")
    need(not any(loc.child.iterdir()), "OUTPUT_ALREADY_USED")
    return plan


class _ChildSession:
    def __init__(self, channel, parent, check):
        import threading

        self.channel = channel
        self.parent = parent
        self.owner = os.getpid()
        self.check = check
        self.lock = threading.Lock()

    def snapshot(self, reference_transition=None):
        need(os.getpid() == self.owner, "SESSION_OWNER")
        with self.lock:
            checked = self.check()
            witness = (
                select_executable_origin(checked["executable_origin"])
                if type(checked) is dict and "executable_origin" in checked
                else None
            )
            self.channel.send(
                {
                    "op": "observe",
                    **({"executable_origin": witness} if witness is not None else {}),
                    **(
                        {"reference_transition": reference_transition}
                        if reference_transition is not None
                        else {}
                    ),
                }
            )
            answer = self.channel.recv(self.parent)
            if reference_transition is not None:
                need(set(answer) == {"snapshot", "reference_transition"}, "REFERENCE_PARENT_REPLY")
                observed = answer["reference_transition"]
                need(
                    type(observed) is dict
                    and set(observed)
                    == {"pair_sha256", "outcome_sha256", "boot_id", "observed_monotonic"}
                    and {k: observed[k] for k in reference_transition} == reference_transition,
                    "REFERENCE_PARENT_REPLY",
                )
                return observed["boot_id"], observed["observed_monotonic"]
            return answer["snapshot"]

    def reference_owner(self, book, attempt, claim, require_owner):
        need(not require_owner, "REFERENCE_CHILD_OWNER")
        ref = book._read(attempt + ".intent.json")["reference_transition"]
        need(ref["pair_sha256"] == claim["pair_sha256"], "REFERENCE_CHILD_PAIR")
        return self.snapshot(ref)

    def before_effect(self):
        self.snapshot()


def _reference_observation(values, attempt, requested):
    """Owned parent rechecks physical lease and immutable transition for child MAY."""
    need(_recovery_mode(attempt), "REFERENCE_PARENT_MODE")
    book = values["_recovery_ledger"]
    intent = book._read(attempt + ".intent.json")
    need(
        requested == intent.get("reference_transition") and type(requested) is dict,
        "REFERENCE_PARENT_BINDING",
    )
    book._reference_transition(attempt, values["_recovery_method"], requested)
    boot, now = book.reference_clock()
    return {**requested, "boot_id": boot, "observed_monotonic": now}


def _check_capture_result(result, *, recovery):
    if result["state"] == "CAPTURED_UNREVIEWED":
        return
    code = "CHILD_CAPTURE_FAILED"
    if recovery:
        if result.get("close_failure"):
            code = "SDK_CLOSE_UNKNOWN"
        elif (result.get("primary_failure") or {}).get("code") == "absolute_deadline":
            code = "CAPTURE_TIMEOUT"
    error = Refused(code)
    if recovery:
        _carry_capture_lifecycle(error, result.get("capture_lifecycle"))
    raise error


def _reference_result(result):
    primary = result["primary_failure"]
    not_ready = (
        result["constructor_returned"] is True
        and result["constructor_status"] == "NOT_READY"
        and primary
        == {
            "stage": "initialize",
            "class": "CaptureRejected",
            "code": "sdk_initial_connection_failed",
        }
    )
    value = select_reference_observation(
        {
            "schema_id": "qm.ivv.reference-init-observation.v1",
            "reference_control_sha256": result["reference_control_sha256"],
            "constructor_status": result["constructor_status"],
            "operation_failed": primary is not None and not not_ready,
            "close_failed": result["close_failure"] is not None,
            "normal_close": result["normal_close"],
            "parent_closed": False,
        }
    )
    code = (
        "SDK_CLOSE_UNKNOWN"
        if value["close_failed"] or not all(value["normal_close"].values())
        else "REFERENCE_INIT_FAILED"
        if value["operation_failed"]
        else "REFERENCE_INIT_OBSERVATION"
    )
    return _carry_reference_observation(Refused(code), value)


def _child(channel, parent, context, plan):
    startup, values, issuer, m, native, producer = context
    extra = values.get("_additional")
    additional = _task_mode(values)
    loc = _locations(additional)
    _bind_parent(parent)
    need(channel.recv(parent) == {"op": "enter"}, "CHILD_GATE")
    ns = _for_task(_child_namespace, additional)(channel, producer)
    _environment()
    if str(SDK) not in sys.path:
        sys.path.append(str(SDK))

    initial_path = None

    def runtime(phase):
        checked = _for_task(_runtime, additional)(
            plan,
            m,
            ns,
            values["catalog_ref"],
            producer,
            origin_phase=phase,
            **({"initial_path": initial_path} if initial_path is not None else {}),
        )
        if _recovery_mode(additional):
            values["_executable_origin"] = select_executable_origin(checked["executable_origin"])
        return checked

    runtime("INITIAL")
    if _recovery_mode(additional):
        initial_path = tuple(sys.path)
    # Validate all immutable material, actor limits and available space before parent GO.
    actor = m._native_actor()
    m._admit_material(
        plan,
        None,
        loc.receipt,
        {**plan, "actor": actor, "budget": values["budget_ref"]},
        None,
        None,
    )
    channel.send(
        {
            "op": "ready",
            **(
                {"executable_origin": values["_executable_origin"]}
                if _recovery_mode(additional)
                else {}
            ),
        }
    )
    grant = channel.recv(parent)
    need(set(grant) == {"op", "plan_ref", "go_ref"} and grant["op"] == "go", "CHILD_GO_GATE")
    final = m._strict_json(read_ref(grant["plan_ref"], loc.control / "plan.json"))
    need(
        {k: v for k, v in final.items() if k != "provider_evidence_ref"}
        == {k: v for k, v in plan.items() if k != "provider_evidence_ref"},
        "PARENT_PLAN_CHANGED",
    )
    evidence = m._strict_json(
        read_ref(final["provider_evidence_ref"], loc.control / "provider.json")
    )
    state = types.ModuleType("_qm_live_ivv_native_" + str(os.getpid()))
    state.session = _ChildSession(channel, parent, lambda: runtime("SESSION"))
    state.helper = m
    state.trusted_issuer = issuer
    state.additional_task = extra
    if _recovery_mode(additional):
        state.capture_classifier = lambda error: classify_capture_exception(
            error, m.CaptureRejected
        )
        state.recovery_profile = extra
        state.recovery_ledger = values["_recovery_ledger"]
        state.recovery_ledger._reference_live_owner = lambda attempt, claim, owner: (
            state.session.reference_owner(state.recovery_ledger, attempt, claim, owner)
        )
        state.recovery_attempt = additional
    state.plan = m._canonical({k: v for k, v in final.items() if k != "provider_evidence_ref"})
    state.evidence = m._canonical(evidence)
    need(state.__name__ not in sys.modules, "NATIVE_BUSY")
    sys.modules[state.__name__] = state
    try:
        pins = {
            "expected_policy_sha256": final["policy_ref"]["sha256"],
            "expected_authorization_sha256": extra.contract.AUTHORITY
            if _recovery_mode(additional)
            else extra.APPROVED.authorization_sha256
            if additional
            else AUTH,
            "expected_go_sha256": grant["go_ref"]["sha256"],
        }
        go = m._strict_json(read_ref(grant["go_ref"], loc.control / "go.json"))
        need(
            go["capture_actor"] == actor
            and go["trusted_runner_sha256"] == values["catalog_ref"]["trusted_runner_sha256"],
            "CHILD_GO_ACTOR",
        )
        fd, sha = issuer._issue_family(
            m,
            extra.FAMILY if additional else FAMILY,
            grant["plan_ref"],
            loc.receipt,
            go_ref=grant["go_ref"],
            authorization_ref=startup["authorization_ref"],
            catalog_ref=startup["catalog_ref"],
            permit_path=loc.child / "permit.json",
            **pins,
        )
        try:
            capture = (
                (
                    m.reference_recovery_attempt
                    if "reference_init_ref" in final
                    else m.capture_recovery_attempt
                )
                if _recovery_mode(additional)
                else m.capture_additional_once
                if additional
                else m.capture_trusted_once
            )
            result = capture(
                grant["plan_ref"]["path"], loc.receipt, permit_fd=fd, expected_sha256=sha, **pins
            )
        finally:
            _close_fd(fd)
        if "reference_init_ref" in final:
            observation = _reference_result(m._select_reference_terminal(result))
            if reason(observation) != "REFERENCE_INIT_OBSERVATION":
                raise observation
            channel.send(_failed_packet(observation))
            return  # Normal child exit; the parent still must observe wait/EOF/closure.
        _check_capture_result(result, recovery=_recovery_mode(additional))
        channel.send(
            {
                "op": "terminal",
                "permit_sha256": sha,
                "manifest_sha256": digest((loc.receipt / "capture-manifest.json").read_bytes()),
            }
        )
    finally:
        del sys.modules[state.__name__]


def _bind_parent(parent):
    # The death signal is attached to the actual forking thread, not an input
    # PID to be signalled. Recheck PPID after installing it to close the fork /
    # parent-exit race. It remains installed through capability drop and exit.
    _libcall("prctl", 1, signal.SIGKILL, 0, 0, 0)
    need(os.getppid() == parent, "PARENT_LOST")


def _authorize(context, plan, scope, monitor):
    startup, values, issuer, m, native, producer = context
    extra = values.get("_additional")
    additional = _task_mode(values)
    loc = _locations(additional)
    family = extra.FAMILY if additional else FAMILY
    prov = (
        extra.provenance()
        if additional
        else {
            "policy_sha256": plan["policy_ref"]["sha256"],
            "authorization_sha256": AUTH,
            "diagnostic_mode": "DEV_TRUSTED_ENVIRONMENT",
            "channel_assurance": ASSURANCE,
            "provider_tail_max": "UNKNOWN",
            "hard_limit_enforced": False,
        }
    )
    actual = monitor.first
    evidence = {
        "schema_id": "qm.ivv.provider-evidence" + family,
        "state": prov["diagnostic_mode"],
        **{k: plan[k] for k in ("scope_id", "execution_sha256", "effect_id")},
        **prov,
        **actual,
    }
    plan = {**plan, "provider_evidence_ref": put(loc.control / "provider.json", evidence)}
    plan_ref = put(loc.control / "plan.json", plan)
    go = {
        "schema_id": "qm.ivv.root-go" + family,
        "decision": "GO_BOUNDED_CAPTURE_RECOVERY"
        if _recovery_mode(additional)
        else "GO_ONCE_AFTER_INPUT_ACCEPTANCE",
        **prov,
        **({} if _recovery_mode(additional) else values["go_fields_ref"]),
        "scope_id": plan["scope_id"],
        "execution_sha256": plan["execution_sha256"],
        "approval_sha256": plan["approval_sha256"],
        "capture_effect_id": plan["effect_id"],
        "max_capture_intents": 1,
        "max_trials": 1,
        "capture_actor": scope.child,
        "budget": values["budget_ref"],
        "plan_sha256": plan_ref["sha256"],
        "provider_evidence_sha256": plan["provider_evidence_ref"]["sha256"],
        "catalog_sha256": plan["catalog_sha256"],
        "input_window_digest": plan["input_window_digest"],
        "full_window_sha256": plan["full_window_sha256"],
        "controls": {"released": True, "resource_bounds": True, "provider_log_cache_bounds": False},
        **{k: values["catalog_ref"][k] for k in _sources(additional)},
    }
    if _recovery_mode(additional):
        go.pop("max_capture_intents")
        go.pop("max_trials")
        go.update(
            recovery=extra.binding(),
            capture_scope_id=plan["scope_id"],
            actor=scope.child,
            catalog=startup.get("catalog_ref"),
            source={k: values["catalog_ref"][k] for k in _sources(additional)},
            native_controls=go["controls"],
        )
    return plan_ref, put(loc.control / "go.json", go), plan, prov


def _manifest(ref, path):
    # Capture originals are private 0600, different from readonly Root controls.
    protected(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        s = os.fstat(fd)
        need(
            stat.S_ISREG(s.st_mode)
            and s.st_uid == 0
            and s.st_nlink == 1
            and stat.S_IMODE(s.st_mode) == 0o600
            and 0 < s.st_size <= 1024 * 1024,
            "CAPTURE_RECEIPT_METADATA",
        )
        raw = os.pread(fd, s.st_size + 1, 0)
        need(
            len(raw) == s.st_size
            and digest(raw) == ref
            and _file_stamp(s) == _file_stamp(os.fstat(fd)) == _file_stamp(path.stat()),
            "CAPTURE_RECEIPT_DIGEST",
        )
        return json.loads(raw)
    finally:
        _close_fd(fd)


def _seal(context, grant, scope, monitor, kernel, terminal, peer, elapsed):
    startup, values, issuer, m, native, producer = context
    extra = values.get("_additional")
    additional = _task_mode(values)
    loc = _locations(additional)
    family = extra.FAMILY if additional else FAMILY
    plan_ref, go_ref, plan, prov = grant
    raw = _manifest(terminal["manifest_sha256"], loc.receipt / "capture-manifest.json")
    binding = raw["source_binding"]
    need(
        raw["schema_id"] == "qm.ivv.capture" + family
        and raw["state"] == "CAPTURED_UNREVIEWED"
        and raw["synthetic"] is False
        and raw["primary_failure"] is None
        and raw["close_failure"] is None
        and raw["normal_close"]
        == {"data_socket_closed": True, "context_closed": True, "callbacks_stopped": True}
        and all(v is True for v in raw["normal_close"].values())
        and raw["counts"]["application_sends"] == 7
        and binding["actor"] == scope.child
        and binding["root_go_sha256"] == go_ref["sha256"]
        and binding["root_permit_sha256"] == terminal["permit_sha256"]
        and binding["plan_sha256"] == plan_ref["sha256"]
        and m._dev_provenance(raw, family) == prov
        and peer is not None,
        "CAPTURE_TERMINAL_EVIDENCE",
    )
    if additional:
        need(
            raw.get("scope_id") == plan["scope_id"]
            and raw.get("approval_sha256") == plan["approval_sha256"]
            and raw.get("execution_sha256") == plan["execution_sha256"]
            and raw["counts"]["contexts"] == 1,
            "ADDITIONAL_TERMINAL_BINDING",
        )
    intent = _manifest(raw["intent_ref"]["sha256"], loc.receipt / "capture-intent.json")
    need(
        intent["schema_id"] == "qm.ivv.capture-intent" + family
        and intent["state"] == "ATTEMPTED"
        and m._dev_provenance(intent, family) == prov,
        "CAPTURE_INTENT",
    )
    permit_ref = {"path": str(loc.child / "permit.json"), "sha256": terminal["permit_sha256"]}
    permit = json.loads(read_ref(permit_ref, loc.child / "permit.json"))
    need(
        permit["actor"] == scope.child and permit["root_go_sha256"] == go_ref["sha256"],
        "SEAL_PERMIT_BINDING",
    )
    config_ref = put(
        loc.control / "configuration.json",
        {
            "endpoint": monitor.first["endpoint"],
            "configuration_binding_sha256": monitor.first["configuration_binding_sha256"],
            "channel_assurance": ASSURANCE,
        },
    )
    monitor_ref = put(
        loc.control / "monitor.json",
        {
            "samples": monitor.series.samples,
            "growth_highwater": monitor.peak,
            "last": monitor.last["sample"],
            "peer_inode_pair": list(peer),
            "provider_tail_max": "UNKNOWN",
        },
    )
    close_ref = put(
        loc.control / "kernel-close.json",
        {
            **kernel,
            "child_reaped": True,
            "recursive_populated": 0,
            "resource_events": scope.initial,
            "control_eof": True,
            "parent_actor": scope.parent,
        },
    )
    refs = [
        plan_ref,
        permit_ref,
        plan["provider_evidence_ref"],
        startup["catalog_ref"],
        plan["sdk_pins_ref"],
        config_ref,
        monitor_ref,
        close_ref,
    ]
    for ref in refs:
        m._read_root_ref(ref, maximum=32768, exact_mode=True)
    return {
        "schema_id": "qm.ivv.capture-parent-close" + family,
        **prov,
        **(
            {
                "approval_sha256": plan["approval_sha256"],
                "execution_sha256": plan["execution_sha256"],
            }
            if additional
            else {}
        ),
        "state": "NORMAL_EXIT",
        "termination": "NORMAL",
        "scope_id": plan["scope_id"],
        "effect_id": plan["effect_id"],
        "capture_manifest_sha256": terminal["manifest_sha256"],
        "intent_sha256": raw["intent_ref"]["sha256"],
        "catalog_sha256": binding["catalog_sha256"],
        "helper_sha256": binding["capture_helper_sha256"],
        "root_permit_sha256": terminal["permit_sha256"],
        "capture_actor": scope.child,
        "executor_actor": scope.parent,
        "helper_exit_code": 0,
        "active_owned_processes": 0,
        "owned_fds_closed": True,
        "resource_limit_event": False,
        "force_killed": False,
        "elapsed_seconds": elapsed,
        "evidence_refs": refs,
        "configuration_sha256": config_ref["sha256"],
        "monitor_sha256": monitor_ref["sha256"],
        "kernel_close_sha256": close_ref["sha256"],
    }


def _accept_executable_origin(value, values, *, phase=None, namespace=None):
    selected = select_executable_origin(value)
    need(
        selected["python_sha256"] == values["catalog_ref"]["python_sha256"]
        and (phase is None or selected["phase"] == phase)
        and (namespace is None or selected["namespace_inode"] == namespace),
        "EXECUTABLE_ORIGIN_BINDING",
    )
    return selected


def _reference_packet(packet, plan):
    need(
        "reference_init_ref" in plan
        and type(packet) is dict
        and set(packet) == {"op", "code", "reference_init_observation"}
        and packet["op"] == "failed"
        and packet["code"] == "REFERENCE_INIT_OBSERVATION",
        "REFERENCE_TERMINAL_PROTOCOL",
    )
    error = _child_failure(packet)
    observation = _reference_from_error(error)
    need(
        observation is not None
        and observation["reference_control_sha256"] == plan["reference_init_ref"]["sha256"]
        and observation["constructor_status"] in {"READY", "NOT_READY"}
        and observation["operation_failed"] is False
        and observation["close_failed"] is False
        and all(observation["normal_close"].values()),
        "REFERENCE_TERMINAL_FAILED",
    )
    return packet


def _supervise(scope, channel, endpoint, context, plan):
    startup, values, issuer, m, native, producer = context
    additional = _task_mode(values)
    binding = values["catalog_ref"].get("provider_binding") if _recovery_mode(additional) else None
    reference = "reference_init_ref" in plan
    need(not reference or _recovery_mode(additional), "REFERENCE_RECOVERY_ONLY")
    monitor = _for_task(_Provider, additional)(
        native,
        producer,
        m,
        plan,
        startup["budget_ref"],
        **({"binding": binding} if binding is not None else {}),
    )
    start = plan["started_monotonic"]
    kernel = grant = terminal = peer = None
    origin_initial = origin_last = None
    origin_checks = 0
    scope.check_pid()
    channel.send({"op": "enter"})
    while True:
        now = time.monotonic()
        # The shared capture enforces context close <=390. Receipt fsync and
        # terminal IPC may follow it; actual child exit has its own420 limit.
        deadline = start + (420 if grant is not None else 180)
        need(now < deadline, "OWNED_CHILD_DEADLINE")
        scope.check_resources()
        if now >= monitor.next:
            scope.verify_manager()
            monitor.sample()
        until = min(deadline, monitor.next)
        ready, _, _ = select.select(
            [channel.s, scope.pidfd], [], [], max(0, until - time.monotonic())
        )
        exit_observed = time.monotonic() - start if scope.pidfd in ready else None
        if channel.s in ready:
            try:
                packet = channel.recv(scope.pid)
            except Refused as error:
                if not terminal or reason(error) != "CONTROL_EOF":
                    raise
                # EOF is verified again after actual wait/recursive empty below.
                packet = None
            if packet and packet.get("op") == "ready" and grant is None:
                need(
                    set(packet)
                    == ({"op", "executable_origin"} if _recovery_mode(additional) else {"op"}),
                    "CHILD_PROTOCOL",
                )
                kernel = _for_task(_child_kernel, additional)(scope, producer, endpoint, True)
                if _recovery_mode(additional):
                    origin_initial = origin_last = _accept_executable_origin(
                        packet["executable_origin"],
                        values,
                        phase="INITIAL",
                        namespace=kernel["namespace_inode"],
                    )
                    origin_checks = 1
                    values["_executable_origin"] = origin_last
                if binding is not None:
                    monitor.verify_network(scope)
                need(time.monotonic() - start < 180, "ROOT_GO_EXPIRED")
                grant = _authorize(context, plan, scope, monitor)
                scope.check_pid()
                channel.send({"op": "go", "plan_ref": grant[0], "go_ref": grant[1]})
            elif packet and packet.get("op") == "observe" and grant and not terminal:
                requested = packet.get("reference_transition")
                need(
                    set(packet)
                    == (
                        ({"op", "executable_origin"} if _recovery_mode(additional) else {"op"})
                        | ({"reference_transition"} if requested is not None else set())
                    )
                    and (
                        requested is None
                        or (
                            _recovery_mode(additional)
                            and not reference
                            and "reference_pair_ref" in plan
                        )
                    ),
                    "CHILD_PROTOCOL",
                )
                if _recovery_mode(additional):
                    origin_last = _accept_executable_origin(
                        packet["executable_origin"],
                        values,
                        phase="SESSION",
                        namespace=kernel["namespace_inode"],
                    )
                    origin_checks += 1
                    values["_executable_origin"] = origin_last
                need(
                    _for_task(_child_kernel, additional)(scope, producer, endpoint, False)
                    == kernel,
                    "CHILD_NAMESPACE_DRIFT",
                )
                pair = monitor.peer(scope.pid) if binding is not None else _owned_peer(scope.pid)
                if pair:
                    need(peer is None or pair == peer, "CAPTURE_PEER_CHANGED")
                    peer = pair
                observation = None
                if requested is not None:
                    need(binding is not None, "REFERENCE_PROVIDER_BINDING")
                    monitor.verify_network(scope)
                    observation = _reference_observation(values, additional, requested)
                channel.send(
                    {
                        "snapshot": monitor.last,
                        **(
                            {"reference_transition": observation} if observation is not None else {}
                        ),
                    }
                )
            elif (
                reference
                and packet
                and packet.get("code") == "REFERENCE_INIT_OBSERVATION"
                and grant
                and not terminal
            ):
                terminal = _reference_packet(packet, plan)
            elif packet and packet.get("op") == "terminal" and grant and not terminal:
                need(
                    not reference
                    and set(packet) == {"op", "permit_sha256", "manifest_sha256"}
                    and all(m._digest(packet[k]) for k in ("permit_sha256", "manifest_sha256")),
                    "TERMINAL_PACKET",
                )
                terminal = packet
            elif packet is not None:
                if _recovery_mode(additional) and "executable_origin" in packet:
                    _accept_executable_origin(
                        packet["executable_origin"],
                        values,
                        namespace=kernel["namespace_inode"] if kernel else None,
                    )
                raise _child_failure(packet)
        if scope.pidfd in ready:
            rc = scope.reap()
            exited = exit_observed
            need(exited <= 420, "CHILD_EXIT_DEADLINE")
            if rc != 0:
                # Exit readiness can precede the queued authenticated failed IPC.
                # This is one already-owned nonblocking read, never a success gate.
                try:
                    failed = channel.recv(scope.pid, nonblocking=True)
                except (BlockingIOError, TimeoutError):
                    pass
                except Refused as error:
                    if reason(error) != "CONTROL_EOF":
                        raise
                else:
                    if _recovery_mode(additional) and "executable_origin" in failed:
                        _accept_executable_origin(
                            failed["executable_origin"],
                            values,
                            namespace=kernel["namespace_inode"] if kernel else None,
                        )
                    raise _child_failure(failed)
            need(rc == 0 and grant and kernel, "CHILD_TERMINAL_MISSING")
            # select may have checked the channel before the child's final
            # send and the pidfd after its exit. Authenticate queued terminal
            # and EOF after the actual wait, independent of readiness order.
            for _ in range(3):
                need(time.monotonic() - start <= 480, "FINAL_SEAL_DEADLINE")
                try:
                    packet = channel.recv(scope.pid)
                except Refused as error:
                    if reason(error) != "CONTROL_EOF":
                        raise
                    break
                need(terminal is None, "CHILD_TERMINAL_PROTOCOL")
                if reference:
                    _reference_packet(packet, plan)
                else:
                    need(
                        type(packet) is dict
                        and set(packet) == {"op", "permit_sha256", "manifest_sha256"}
                        and packet["op"] == "terminal"
                        and all(m._digest(packet[k]) for k in ("permit_sha256", "manifest_sha256")),
                        "CHILD_TERMINAL_PROTOCOL",
                    )
                terminal = packet
            else:
                raise Refused("CONTROL_NOT_CLOSED")
            need(terminal, "CHILD_TERMINAL_MISSING")
            scope.empty()
            scope.check_resources()
            scope.verify_manager()
            monitor.sample()
            channel.check()
            break
    elapsed = time.monotonic() - start
    need(elapsed <= 480, "FINAL_SEAL_DEADLINE")
    if reference:
        return {"reference_init_observation": terminal["reference_init_observation"]}
    return _seal(
        context,
        grant,
        scope,
        monitor,
        {
            **kernel,
            "child_exit_observed_seconds": exited,
            **(
                {
                    "executable_origin": {
                        "initial": origin_initial,
                        "last": origin_last,
                        "checks": origin_checks,
                    }
                }
                if _recovery_mode(additional)
                else {}
            ),
        },
        terminal,
        peer,
        elapsed,
    )


def _commit_close(ref, *, additional=False):
    loc = _locations(additional)
    source = loc.control / "parent-close.pending.json"
    read_ref(ref, source)
    _libcall(
        "renameat2",
        -100,
        os.fsencode(source),
        -100,
        os.fsencode(loc.control / "parent-close.json"),
        1,
    )
    _sync_dir(loc.control)


def _reject_close(ref, committed, *, additional=False):
    loc = _locations(additional)
    source = loc.control / ("parent-close.json" if committed else "parent-close.pending.json")
    try:
        read_ref({"path": str(source), "sha256": ref["sha256"]}, source)
    except FileNotFoundError:
        source = loc.control / ("parent-close.pending.json" if committed else "parent-close.json")
        read_ref({"path": str(source), "sha256": ref["sha256"]}, source)
    _libcall(
        "renameat2",
        -100,
        os.fsencode(source),
        -100,
        os.fsencode(loc.control / "parent-close.rejected.json"),
        1,
    )
    _sync_dir(loc.control)


def run_once(startup_ref):
    return _run(startup_ref, additional=False)


def run_additional_once(startup_ref):
    return _run(startup_ref, additional=True)


def run_recovery_attempt(startup_ref, connection_attempt_id):
    need(_recovery_mode(connection_attempt_id), "RECOVERY_ATTEMPT")
    with _recovery_lifecycle(startup_ref, connection_attempt_id) as lifecycle:
        return _run(startup_ref, additional=connection_attempt_id, lifecycle=lifecycle)


def _run(startup_ref, *, additional, lifecycle=None):
    loc = _locations(additional)
    started = time.monotonic() if additional else None
    context = _for_task(_bootstrap, additional)(startup_ref)
    startup, values, issuer, helper, native, producer = context
    plan = (
        _seed(values, startup, helper, issuer, started=started)
        if additional
        else _seed(values, startup, helper, issuer)
    )
    if _recovery_mode(additional):
        task = values["_recovery_task"]
        book = task.RecoveryLedger(
            loc.ledger, values["_additional"].policy, values["_additional"].contract
        )
        method = digest(raw_json({k: values["catalog_ref"][k] for k in _sources(additional)}))
        values["_recovery_method"] = method
        book.enter(additional, method, startup_ref["sha256"])
        values["_recovery_ledger"] = book
        book._reference_live_owner = lambda attempt, claim, owner: _reference_transition_owner(
            book, attempt, claim, owner
        )
        book.bind_reference_plan(
            additional,
            plan,
            helper._read_reference_pair(plan) if "reference_pair_ref" in plan else None,
            startup_ref["sha256"],
        )
    _stdio()
    need(
        _fds() == ({0, 1, 2} | ({lifecycle.fd} if lifecycle is not None else set()))
        and len(list(Path("/proc/self/task").iterdir())) == 1,
        "PARENT_FD_THREAD_CLOSURE",
    )
    os.umask(0o077)
    primary = None
    primary_origin = None
    primary_executable = None
    primary_capture = None
    reference = None
    cleanup_failures = None
    pending = None
    committed = False
    with _Handles() as stack:
        scope = _Scope.__new__(_Scope)
        try:
            _for_task(scope.__init__, additional)(stack)
            a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC)
            stack.callback(a.close)
            stack.callback(b.close)
            parent_side, child_side = _Channel(a), _Channel(b)
            endpoint = child_side.origin[1]
            parent = os.getpid()
            if _recovery_mode(additional):
                book._write(
                    additional + ".fork-may.json", {"phase": "FORK_MAY", "manager": scope.parent}
                )
            pid = os.fork()
            if pid == 0:
                rc = 1
                try:
                    a.close()
                    _child(child_side, parent, context, plan)
                    rc = 0
                except BaseException as error:
                    _carry_executable_origin(
                        error, _executable_from_error(error) or values.get("_executable_origin")
                    )
                    with contextlib.suppress(OSError, ValueError):
                        child_side.send(_failed_packet(error))
                finally:
                    os._exit(rc)
            b.close()
            scope.bind(pid)
            if _recovery_mode(additional):
                _persist_recovery_owner(book, additional, scope)
            result = _supervise(scope, parent_side, endpoint, context, plan)
            if "reference_init_ref" in plan:
                need(set(result) == {"reference_init_observation"}, "REFERENCE_PARENT_RESULT")
                reference = select_reference_observation(result["reference_init_observation"])
                need(reference["parent_closed"] is False, "REFERENCE_CHILD_OWNER")
            scope.check_resources()
            scope.remove()
            scope.leaf = None
            elapsed = time.monotonic() - plan["started_monotonic"]
            need(elapsed <= 480, "FINAL_SEAL_DEADLINE")
            if reference is None:
                result["elapsed_seconds"] = elapsed
            # Keep all resource/event handles through JSON/file+directory
            # fsync and normal publication. No partial file is normal authority.
            if reference is None:
                pending = put(loc.control / "parent-close.pending.json", result)
            scope.check_final_resources()
            need(time.monotonic() - plan["started_monotonic"] <= 480, "FINAL_SEAL_DEADLINE")
            if reference is None:
                committed = True
                _for_task(_commit_close, additional)(pending)
            scope.check_final_resources()
            need(time.monotonic() - plan["started_monotonic"] <= 480, "FINAL_SEAL_DEADLINE")
        except BaseException as error:
            primary_capture = _capture_lifecycle_from_error(error)
            reference = _reference_from_error(error) or reference
            primary_origin = _origin_from_error(error)
            primary_executable = _executable_from_error(error) or values.get("_executable_origin")
            failures = scope.abort()
            cleanup_failures = failures
            primary = [_failure_code(error), *failures]
    if lifecycle is not None:
        try:
            lifecycle.close()
        except BaseException:
            stack.errors.append("RECOVERY_LEASE_CLOSE")
    if time.monotonic() - plan["started_monotonic"] > 480:
        primary = [*(primary or []), "FINAL_SEAL_DEADLINE"]
    if _recovery_mode(additional):
        # A failed capture remains unpublishable. Independently completed exact
        # owner abort/reap/empty/removal can nevertheless enable a new attempt.
        closed = (
            not stack.errors
            and scope.reaped
            and (cleanup_failures == [] or (primary is None and scope.leaf is None))
        )
        proof = dict(
            child_reaped=scope.reaped,
            recursive_populated=0 if closed else 1,
            owned_fds_closed=not stack.errors,
            resource_limit_event=False,
            active_owned_processes=0 if closed else 1,
        )
        failure = primary[0] if primary else "REFERENCE_INIT_OBSERVATION" if reference else None
        if failure is not None and re.fullmatch(r"[A-Z0-9_+]{1,512}", failure) is None:
            failure = "CAPTURE_FAILED"
        try:
            values["_recovery_ledger"].close(
                additional, proof, failure=failure, method_sha256=values["_recovery_method"]
            )
        except BaseException:
            primary = [*(primary or []), "RECOVERY_CLOSURE_PERSISTENCE"]
    if primary or stack.errors:
        failures = [*(primary or []), *stack.errors]
        if pending is not None:
            try:
                _for_task(_reject_close, additional)(pending, committed)
            except BaseException as error:
                failures.append("SEAL_RETIRE_" + reason(error))
        code = "+".join(failures)
        failure = _carry_origin(Refused(code), primary_origin, code)
        _carry_capture_lifecycle(failure, primary_capture)
        _carry_reference_observation(failure, reference)
        raise _carry_executable_origin(
            failure, primary_executable or values.get("_executable_origin")
        ) from None
    if reference is not None:
        raise _carry_reference_observation(
            Refused("REFERENCE_INIT_OBSERVATION"), {**reference, "parent_closed": True}
        )
    return result


def main(argv):
    recovery = bool(argv) and argv[0] == "--recovery-attempt"
    additional = (
        argv[1] if recovery and len(argv) == 3 else bool(argv) and argv[0] == "--additional-task"
    )
    control = _locations(additional).control
    try:
        if recovery:
            need(len(argv) == 3 and _recovery_mode(additional), "RECOVERY_ARGUMENTS")
            argv = argv[2:]
        elif additional:
            argv = argv[1:]
        need(len(argv) == 1, "STARTUP_DIGEST_REQUIRED")
        entry = (
            functools.partial(run_recovery_attempt, connection_attempt_id=additional)
            if recovery
            else (run_additional_once if additional else run_once)
        )
        entry({"path": str(control / "startup.json"), "sha256": argv[0]})
        return 0
    except BaseException as e:
        # Even when preflight failed, never overwrite an earlier attempt.
        with contextlib.suppress(OSError, ValueError):
            put(control / "runner-failure.json", _failure_record(e))
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
