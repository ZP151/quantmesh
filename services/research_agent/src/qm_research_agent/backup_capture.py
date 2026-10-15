"""Read-only snapshot manifest capture for the formal research Agent store.

This records a PostgreSQL MVCC cut and its referenced immutable artifacts. It is
not a database dump or a recoverable backup.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import selectors
import stat
import subprocess
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from pydantic import SecretStr

from qm_research_agent import accounting
from qm_research_agent.accounting import PortfolioBudgetPolicy
from qm_research_agent.store import _Connection, connect
from quantmesh.research.job_store import protocol_digest
from quantmesh.research.jobs import (
    AnalysisLease,
    AnalysisRecord,
    ArtifactRef,
    JobRecord,
    canonical_request_digest,
    schema_digest,
)

_SCHEMA = "qm_research"
_LEDGER_TABLES = (
    "model_effects",
    "qm_portfolio_schema",
    "qm_portfolio_policy",
    "qm_portfolio_reservations",
)
_MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_OBJECT_KEY = re.compile(r"^([A-Za-z0-9_-]{1,128})/([0-9a-f]{64})\.([a-z]+)$")
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_PG_DUMP_SHA256 = "137cf7c068b3459f5205f97f27cd206b537228e031d721f52535daf29c0ab6f8"
_MAX_PG_DUMP_BYTES = 32 * 1024 * 1024
_MAX_PG_DUMP_OUTPUT_BYTES = 2 * 1024 * 1024
_PG_DUMP_TIMEOUT_SECONDS = 60.0
_PG_DUMP_TERMINATE_SECONDS = 1.0
_PG_SERVICE_MAX_LINE_BYTES = 1022
_PG_SERVICE_KEYS = ("host", "port", "user", "password", "dbname", "sslmode")


class ManifestCaptureRefused(ValueError):
    """Fixed public refusal; database and filesystem details are not included."""


def _refuse() -> ManifestCaptureRefused:
    return ManifestCaptureRefused("research snapshot manifest refused")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _row_sha(row: tuple) -> str:
    return _sha(_canonical(list(row)))


def _fetchall(connection, query: str, params: tuple = ()) -> list[tuple]:
    cursor = connection.cursor()
    try:
        cursor.execute(query, params)
        return [tuple(row) for row in cursor.fetchall()]
    finally:
        close = getattr(cursor, "close", None)
        if close is not None:
            close()


def _execute(connection, query: str) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute(query)
    finally:
        close = getattr(cursor, "close", None)
        if close is not None:
            close()


def _fetchone(connection, query: str, params: tuple = ()):
    cursor = connection.cursor()
    try:
        cursor.execute(query, params)
        return cursor.fetchone()
    finally:
        close = getattr(cursor, "close", None)
        if close is not None:
            close()


def _table_exists(connection, name: str) -> bool:
    row = _fetchone(connection, "SELECT to_regclass(%s)", (f"{_SCHEMA}.{name}",))
    return bool(row and row[0])


def _validate_portfolio(
    connection, rows: dict[str, list[tuple]], policy: PortfolioBudgetPolicy | None
) -> tuple[str, str | None]:
    effects = rows["effects"]
    versions = rows["portfolio_schema"]
    policies = rows["portfolio_policy"]
    reservations = rows["reservations"]

    if versions != [(1,)]:
        raise _refuse()
    if not policies:
        if policy is not None or effects or reservations:
            raise _refuse()
        return "unconfigured", None
    if len(policies) != 1 or policy is None:
        raise _refuse()

    try:
        high_water = accounting.validate(_Connection(connection), policy)
        policy_row = policies[0]
        if policy_row[0] != 1:
            raise _refuse()
        effect_map = {}
        for row in effects:
            job_id, digest, price, status, response, checkpoint = row
            if (
                not isinstance(job_id, str)
                or not _SHA256.fullmatch(str(digest))
                or not isinstance(price, str)
                or accounting.canonical(Decimal(price)) != price
                or status not in {"reserved", "completed"}
                or (response is not None and not isinstance(response, str))
                or (checkpoint is not None and not isinstance(checkpoint, str))
            ):
                raise _refuse()
            key = (job_id, digest)
            if key in effect_map:
                raise _refuse()
            if status == "completed" and not response:
                raise _refuse()
            effect_map[key] = row

        seen = set()
        stamp_high = datetime.fromisoformat(high_water)
        for row in reservations:
            job_id, digest, category, period, price, reserved_at = row
            key = (job_id, digest)
            effect = effect_map.get(key)
            if (
                effect is None
                or key in seen
                or category not in {"operating", "development"}
                or not isinstance(price, str)
                or accounting.canonical(Decimal(price)) != price
                or price != effect[2]
                or not isinstance(reserved_at, str)
            ):
                raise _refuse()
            parsed = datetime.fromisoformat(reserved_at)
            if (
                accounting.utc_stamp(parsed) != reserved_at
                or period != reserved_at[:7]
                or parsed > stamp_high
            ):
                raise _refuse()
            seen.add(key)
        if seen != set(effect_map):
            raise _refuse()
        return "configured", high_water
    except ManifestCaptureRefused:
        raise
    except (ArithmeticError, TypeError, ValueError, OverflowError):
        raise _refuse() from None


def _read_snapshot_state(
    connection, schema: str, policy: PortfolioBudgetPolicy | None
) -> dict[str, Any]:
    if schema != _SCHEMA:
        raise _refuse()
    versions = _fetchall(connection, "SELECT version FROM qm_schema ORDER BY version")
    if versions != [(1,)]:
        raise _refuse()

    exists = {name: _table_exists(connection, name) for name in _LEDGER_TABLES}
    if any(exists.values()) and not all(exists.values()):
        raise _refuse()

    jobs = _fetchall(
        connection,
        "SELECT job_id,operator_id,idempotency_key,payload,sequence FROM jobs ORDER BY sequence",
    )
    outbox = _fetchall(
        connection, "SELECT job_id,lease,attempt,sequence FROM analysis_outbox ORDER BY sequence"
    )
    for rows in (jobs, outbox):
        for row in rows:
            if not isinstance(row[-1], int) or isinstance(row[-1], bool) or row[-1] < 1:
                raise _refuse()

    state: dict[str, Any] = {
        "service_version": 1,
        "jobs": jobs,
        "outbox": outbox,
        "effects": [],
        "portfolio_schema": [],
        "portfolio_policy": [],
        "reservations": [],
        "effect_ledger": "uninitialized",
    }
    if not any(exists.values()):
        state["tables"] = {
            "qm_schema": versions,
            "jobs": jobs,
            "analysis_outbox": outbox,
            **{name: None for name in _LEDGER_TABLES},
        }
        return state

    effects = _fetchall(
        connection,
        "SELECT job_id,digest,price,status,response,checkpoint "
        "FROM model_effects ORDER BY job_id,digest",
    )
    portfolio_schema = _fetchall(
        connection, "SELECT version FROM qm_portfolio_schema ORDER BY version"
    )
    portfolio_policy = _fetchall(
        connection,
        "SELECT slot,policy_id,operating_monthly_usd,development_total_usd,high_water "
        "FROM qm_portfolio_policy ORDER BY slot",
    )
    reservations = _fetchall(
        connection,
        "SELECT job_id,digest,category,period,price,reserved_at "
        "FROM qm_portfolio_reservations ORDER BY job_id,digest",
    )
    ledger_rows = {
        "effects": effects,
        "portfolio_schema": portfolio_schema,
        "portfolio_policy": portfolio_policy,
        "reservations": reservations,
    }
    ledger_state, high_water = _validate_portfolio(connection, ledger_rows, policy)
    state.update(ledger_rows)
    state["effect_ledger"] = ledger_state
    state["portfolio_high_water"] = high_water
    state["tables"] = {
        "qm_schema": versions,
        "jobs": jobs,
        "analysis_outbox": outbox,
        "model_effects": effects,
        "qm_portfolio_schema": portfolio_schema,
        "qm_portfolio_policy": portfolio_policy,
        "qm_portfolio_reservations": reservations,
    }
    return state


def _open_directory(path: Path, *, owner: int | None = None, private: bool = False) -> int:
    if not _NOFOLLOW or not _DIRECTORY:
        raise _refuse()
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise _refuse()
    flags = os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC
    fd = os.open("/", flags)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        info = os.fstat(fd)
        if (
            not stat.S_ISDIR(info.st_mode)
            or (owner is not None and info.st_uid != owner)
            or (private and stat.S_IMODE(info.st_mode) != 0o700)
            or (not private and info.st_mode & 0o022)
        ):
            raise _refuse()
        return fd
    except BaseException:
        os.close(fd)
        raise


def _verify_subdir(fd: int, *, private: bool) -> None:
    info = os.fstat(fd)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or (private and stat.S_IMODE(info.st_mode) != 0o700)
        or (not private and info.st_mode & 0o022)
    ):
        raise _refuse()


def _signature(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_uid,
        info.st_gid,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _source_bytes(root_fd: int, ref: ArtifactRef) -> bytes:
    match = _OBJECT_KEY.fullmatch(ref.object_key)
    if match is None or match.group(1) == "":
        raise _refuse()
    job_id, filename = match.group(1), match.group(2) + "." + match.group(3)
    if not ref.object_key.startswith(job_id + "/") or ref.byte_size > _MAX_ARTIFACT_BYTES:
        raise _refuse()
    job_fd = os.open(job_id, os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC, dir_fd=root_fd)
    file_fd = -1
    try:
        _verify_subdir(job_fd, private=False)
        file_fd = os.open(filename, os.O_RDONLY | _NOFOLLOW | _CLOEXEC, dir_fd=job_fd)
        before = os.fstat(file_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or before.st_mode & 0o077
            or before.st_size != ref.byte_size
            or before.st_size > _MAX_ARTIFACT_BYTES
        ):
            raise _refuse()
        chunks = []
        remaining = ref.byte_size
        while remaining:
            chunk = os.read(file_fd, min(65536, remaining))
            if not chunk:
                raise _refuse()
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(file_fd, 1):
            raise _refuse()
        raw = b"".join(chunks)
        after = os.fstat(file_fd)
        if _signature(before) != _signature(after) or _sha(raw) != ref.sha256:
            raise _refuse()
        return raw
    except (OSError, ValueError):
        raise _refuse() from None
    finally:
        if file_fd >= 0:
            os.close(file_fd)
        os.close(job_fd)


def _checked_references(state: dict, artifact_root_fd: int) -> tuple[list[dict], list[dict]]:
    references: dict[str, dict] = {}
    jobs = []
    records_by_id = {}
    for row in state["jobs"]:
        try:
            job_id, operator_id, idempotency_key, payload, sequence = row
            record = JobRecord.model_validate_json(payload)
            if (
                record.job_id != job_id
                or canonical_request_digest(record.request) != record.request_digest
                or not isinstance(operator_id, str)
                or not isinstance(idempotency_key, str)
                or record.operator_id != operator_id
                or record.idempotency_key != idempotency_key
            ):
                raise _refuse()
        except ManifestCaptureRefused:
            raise
        except (TypeError, ValueError):
            raise _refuse() from None

        refs = [ArtifactRef.model_validate(ref.model_dump()) for ref in record.artifacts]
        records_by_id[job_id] = record
        if record.state == "succeeded":
            if sum(ref.kind == "report" for ref in refs) != 1:
                raise _refuse()
        elif refs:
            raise _refuse()

        if record.analysis is not None:
            analysis = AnalysisRecord.model_validate(record.analysis.model_dump(mode="python"))
            if analysis.job_id != record.job_id:
                raise _refuse()
            if any(citation not in refs for citation in analysis.citations):
                raise _refuse()
            if analysis.output_artifact is not None:
                refs.append(ArtifactRef.model_validate(analysis.output_artifact.model_dump()))

        for ref in refs:
            match = _OBJECT_KEY.fullmatch(ref.object_key)
            if match is None or match.group(1) != job_id:
                raise _refuse()
            key = ref.object_key
            item = {
                "job_id": job_id,
                "object_key": key,
                "kind": ref.kind,
                "byte_size": ref.byte_size,
                "sha256": ref.sha256,
            }
            previous = references.get(key)
            if previous is not None and previous != item:
                raise _refuse()
            references[key] = item

        report_refs = [ref for ref in refs if ref.kind == "report"]
        if record.state == "succeeded":
            report = report_refs[0]
            raw = _source_bytes(artifact_root_fd, report)
            try:
                envelope = json.loads(raw)
                if (
                    not isinstance(envelope, dict)
                    or envelope.get("schema_version") != 1
                    or envelope.get("request_digest") != record.request_digest
                    or envelope.get("implementation_digest") != record.implementation_digest
                    or not isinstance(envelope.get("result"), dict)
                ):
                    raise _refuse()
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise _refuse() from None

        jobs.append(
            {
                "job_id": job_id,
                "operator_id_sha256": _sha(operator_id.encode("utf-8")),
                "idempotency_key_sha256": _sha(idempotency_key.encode("utf-8")),
                "request_digest": record.request_digest,
                "state": record.state,
                "analysis_state": record.analysis_state,
                "row_sha256": _row_sha(row),
                "row_sequence": sequence,
            }
        )

    job_by_id = {job["job_id"]: job for job in jobs}
    if any(effect[0] not in job_by_id for effect in state["effects"]):
        raise _refuse()
    outbox_jobs = set()
    outbox_leases = {}
    for job_id, lease_json, attempt, sequence in state["outbox"]:
        job = job_by_id.get(job_id)
        if (
            job is None
            or job_id in outbox_jobs
            or not isinstance(attempt, int)
            or isinstance(attempt, bool)
            or attempt < 0
        ):
            raise _refuse()
        outbox_jobs.add(job_id)
        outbox_leases[job_id] = lease_json
        job_record = records_by_id[job_id]
        if (
            not job_record.request.analysis_requested
            or job_record.state != "succeeded"
            or job_record.analysis_state not in {"pending", "running"}
        ):
            raise _refuse()
        if lease_json is None:
            if job_record.analysis_state == "running" or attempt != 0:
                raise _refuse()
        else:
            try:
                lease = AnalysisLease.model_validate_json(lease_json)
            except (TypeError, ValueError):
                raise _refuse() from None
            report_refs = [ref for ref in job_record.artifacts if ref.kind == "report"]
            if (
                lease.job_id != job_id
                or lease.attempt != attempt
                or job_record.analysis_state != "running"
                or not job_record.request.analysis_requested
                or len(report_refs) != 1
                or lease.report_digest != report_refs[0].sha256
            ):
                raise _refuse()
    for job_id, record in records_by_id.items():
        if record.analysis_state == "running" and record.state != "succeeded":
            raise _refuse()
        if not record.request.analysis_requested:
            if record.analysis_state != "not_requested" or job_id in outbox_jobs:
                raise _refuse()
            continue
        if record.state == "succeeded":
            if record.analysis_state == "not_requested":
                raise _refuse()
            if record.analysis_state == "pending":
                if job_id not in outbox_jobs or outbox_leases[job_id] is not None:
                    raise _refuse()
            elif record.analysis_state == "running":
                if job_id not in outbox_jobs or outbox_leases[job_id] is None:
                    raise _refuse()
            elif job_id in outbox_jobs:
                raise _refuse()
        elif record.analysis_state in {"succeeded", "failed", "unavailable", "cancelled"}:
            if job_id in outbox_jobs:
                raise _refuse()
    for item in references.values():
        ref = ArtifactRef(
            artifact_id=item["sha256"],
            kind=item["kind"],
            sha256=item["sha256"],
            byte_size=item["byte_size"],
            object_key=item["object_key"],
        )
        _source_bytes(artifact_root_fd, ref)
    return sorted(references.values(), key=lambda item: item["object_key"]), jobs


def _row_fingerprints(tables: dict[str, list[tuple] | None]) -> dict:
    fingerprints = {}
    for name, rows in tables.items():
        fingerprints[name] = (
            {"present": False, "row_count": 0, "rows_sha256": []}
            if rows is None
            else {
                "present": True,
                "row_count": len(rows),
                "rows_sha256": [_row_sha(tuple(row)) for row in rows],
            }
        )
    return fingerprints


def _effect_summaries(rows: list[tuple]) -> list[dict]:
    return [
        {
            "job_id": job_id,
            "digest": digest,
            "price": price,
            "status": status,
            "response_sha256": _sha(response.encode("utf-8")) if response is not None else None,
            "checkpoint_sha256": _sha(checkpoint.encode("utf-8"))
            if checkpoint is not None
            else None,
            "row_sha256": _row_sha(tuple(row)),
        }
        for row in rows
        for job_id, digest, price, status, response, checkpoint in (row,)
    ]


def _reservation_summaries(rows: list[tuple]) -> list[dict]:
    return [
        {
            "job_id": job_id,
            "digest": digest,
            "category": category,
            "period": period,
            "price": price,
            "reserved_at": reserved_at,
            "row_sha256": _row_sha(tuple(row)),
        }
        for row in rows
        for job_id, digest, category, period, price, reserved_at in (row,)
    ]


def _build_manifest(
    state: dict, references: list[dict], jobs: list[dict], *, snapshot_was_exported: bool
) -> dict:
    row_maxima = {
        "jobs": max((row["row_sequence"] for row in jobs), default=None),
        "analysis_outbox": max((row[3] for row in state["outbox"]), default=None),
    }
    policy_rows = state["portfolio_policy"]
    policy = None
    if policy_rows:
        slot, policy_id, operating, development, high_water = policy_rows[0]
        policy = {
            "slot": slot,
            "policy_id": policy_id,
            "operating_monthly_usd": operating,
            "development_total_usd": development,
            "high_water": high_water,
            "row_sha256": _row_sha(tuple(policy_rows[0])),
        }
    return {
        "manifest_version": 1,
        "schema": _SCHEMA,
        "service_schema_version": state["service_version"],
        "schema_digest": schema_digest(),
        "protocol_digest": protocol_digest(),
        "snapshot": {
            "isolation": "repeatable_read",
            "read_only": True,
            "exported": snapshot_was_exported,
            "token_persisted": False,
            "sequence_counters": "not_mvcc; row maxima only",
        },
        "effect_ledger": state["effect_ledger"],
        "portfolio_policy": policy,
        "portfolio_high_water": state.get("portfolio_high_water"),
        "jobs": jobs,
        "effects": _effect_summaries(state["effects"]),
        "reservations": _reservation_summaries(state["reservations"]),
        "tables": _row_fingerprints(state["tables"]),
        "row_sequence_maxima": row_maxima,
        "references": references,
    }


def _write_all(fd: int, raw: bytes) -> None:
    view = memoryview(raw)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise _refuse()
        view = view[written:]


def _mkdir_child(parent_fd: int, name: str, *, private: bool) -> int:
    try:
        os.mkdir(name, 0o700 if private else 0o755, dir_fd=parent_fd)
    except FileExistsError:
        pass
    fd = os.open(name, os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC, dir_fd=parent_fd)
    _verify_subdir(fd, private=private)
    return fd


def _remove_contents(directory_fd: int, *, preserve: frozenset[str] = frozenset()) -> None:
    for name in os.listdir(directory_fd):
        if name in preserve:
            continue
        info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            child_fd = os.open(
                name, os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC, dir_fd=directory_fd
            )
            try:
                opened = os.fstat(child_fd)
                if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                    raise _refuse()
                _remove_contents(child_fd)
            finally:
                os.close(child_fd)
            os.rmdir(name, dir_fd=directory_fd)
        else:
            os.unlink(name, dir_fd=directory_fd)


def _remove_output_root(
    parent_fd: int,
    root_fd: int,
    name: str,
    *,
    preserve: frozenset[str] = frozenset(),
) -> None:
    try:
        entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        root = os.fstat(root_fd)
        if not stat.S_ISDIR(entry.st_mode) or (entry.st_dev, entry.st_ino) != (
            root.st_dev,
            root.st_ino,
        ):
            return
        _remove_contents(root_fd, preserve=preserve)
        os.rmdir(name, dir_fd=parent_fd)
    except OSError:
        # Preserve the original capture refusal; a leftover private directory is
        # unusable as evidence and remains safe to inspect or remove manually.
        return


def _copy_one(source_root_fd: int, destination_root_fd: int, reference: dict) -> None:
    job_id, _, filename = reference["object_key"].partition("/")
    if not job_id or not filename or "/" in filename:
        raise _refuse()
    source_job_fd = os.open(
        job_id, os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC, dir_fd=source_root_fd
    )
    destination_artifacts_fd = os.open(
        "artifacts", os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC, dir_fd=destination_root_fd
    )
    destination_job_fd = -1
    source_fd = -1
    destination_fd = -1
    try:
        _verify_subdir(source_job_fd, private=False)
        destination_job_fd = _mkdir_child(destination_artifacts_fd, job_id, private=True)
        source_fd = os.open(filename, os.O_RDONLY | _NOFOLLOW | _CLOEXEC, dir_fd=source_job_fd)
        before = os.fstat(source_fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or before.st_mode & 0o077
            or before.st_size != reference["byte_size"]
            or before.st_size > _MAX_ARTIFACT_BYTES
        ):
            raise _refuse()
        destination_fd = os.open(
            filename,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _CLOEXEC,
            0o600,
            dir_fd=destination_job_fd,
        )
        digest = hashlib.sha256()
        copied = 0
        while copied < reference["byte_size"]:
            block = os.read(source_fd, min(65536, reference["byte_size"] - copied))
            if not block:
                raise _refuse()
            copied += len(block)
            digest.update(block)
            _write_all(destination_fd, block)
        if os.read(source_fd, 1):
            raise _refuse()
        after = os.fstat(source_fd)
        if (
            _signature(before) != _signature(after)
            or copied != reference["byte_size"]
            or digest.hexdigest() != reference["sha256"]
        ):
            raise _refuse()
        os.fsync(destination_fd)
        destination_info = os.fstat(destination_fd)
        if (
            not stat.S_ISREG(destination_info.st_mode)
            or destination_info.st_uid != os.geteuid()
            or destination_info.st_nlink != 1
            or destination_info.st_size != reference["byte_size"]
            or stat.S_IMODE(destination_info.st_mode) != 0o600
        ):
            raise _refuse()
    except (FileExistsError, OSError, ValueError):
        raise _refuse() from None
    finally:
        for fd in (source_fd, destination_fd, destination_job_fd, source_job_fd):
            if fd >= 0:
                os.close(fd)
        os.close(destination_artifacts_fd)


def _create_output_root(path: Path) -> tuple[int, int]:
    path = Path(path)
    if not path.is_absolute() or path.name in {"", ".", ".."}:
        raise _refuse()
    parent_fd = _open_directory(path.parent)
    root_fd = -1
    try:
        os.mkdir(path.name, 0o700, dir_fd=parent_fd)
        root_fd = os.open(
            path.name, os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC, dir_fd=parent_fd
        )
        _verify_subdir(root_fd, private=True)
        os.mkdir("artifacts", 0o700, dir_fd=root_fd)
        return parent_fd, root_fd
    except (FileExistsError, OSError, ValueError):
        try:
            if root_fd >= 0:
                try:
                    _remove_output_root(parent_fd, root_fd, path.name)
                except Exception:
                    pass
        finally:
            for fd in (root_fd, parent_fd):
                if fd >= 0:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
        raise _refuse() from None


def _write_manifest(root_fd: int, manifest: dict) -> str:
    raw = _canonical(manifest)
    fd = os.open(
        "manifest.json",
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _CLOEXEC,
        0o600,
        dir_fd=root_fd,
    )
    try:
        _write_all(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    return _sha(raw)


def _read_private_file(parent_fd: int, name: str, *, limit: int) -> bytes:
    fd = os.open(name, os.O_RDONLY | _NOFOLLOW | _CLOEXEC, dir_fd=parent_fd)
    try:
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or before.st_nlink != 1
            or before.st_mode & 0o077
            or before.st_size > limit
        ):
            raise _refuse()
        chunks = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(fd, min(65536, remaining))
            if not chunk:
                raise _refuse()
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(fd, 1) or _signature(before) != _signature(os.fstat(fd)):
            raise _refuse()
        return b"".join(chunks)
    except (OSError, ValueError):
        raise _refuse() from None
    finally:
        os.close(fd)


def _validate_artifact_tree(root_fd: int, references: list[dict]) -> None:
    if set(os.listdir(root_fd)) != {"manifest.json", "artifacts"}:
        raise _refuse()
    artifacts_fd = os.open(
        "artifacts", os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC, dir_fd=root_fd
    )
    try:
        _verify_subdir(artifacts_fd, private=True)
        by_job: dict[str, set[str]] = {}
        for item in references:
            key = item["object_key"]
            match = _OBJECT_KEY.fullmatch(key)
            if match is None or match.group(1) != item["job_id"]:
                raise _refuse()
            by_job.setdefault(item["job_id"], set()).add(match.group(2) + "." + match.group(3))
        if set(os.listdir(artifacts_fd)) != set(by_job):
            raise _refuse()
        for job_id, filenames in by_job.items():
            job_fd = os.open(
                job_id, os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC, dir_fd=artifacts_fd
            )
            try:
                _verify_subdir(job_fd, private=True)
                if set(os.listdir(job_fd)) != filenames:
                    raise _refuse()
                for item in references:
                    if item["job_id"] != job_id:
                        continue
                    raw = _read_private_file(
                        job_fd,
                        item["object_key"].split("/", 1)[1],
                        limit=_MAX_ARTIFACT_BYTES,
                    )
                    if len(raw) != item["byte_size"] or _sha(raw) != item["sha256"]:
                        raise _refuse()
            finally:
                os.close(job_fd)
    finally:
        os.close(artifacts_fd)


def _validate_bundle_inputs(dsn: SecretStr, schema: str, policy, pg_dump_path: Path):
    """Validate every caller-controlled value before opening a database connection."""
    if schema != _SCHEMA or not isinstance(dsn, SecretStr):
        raise _refuse()
    if policy is not None and not isinstance(policy, PortfolioBudgetPolicy):
        raise _refuse()
    raw_dsn = dsn.get_secret_value()
    parsed = urlsplit(raw_dsn)
    options = parse_qs(parsed.query, strict_parsing=True)
    service_values = {
        "host": parsed.hostname or "",
        "port": str(parsed.port or 5432),
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "dbname": unquote(parsed.path.lstrip("/")),
        "sslmode": options.get("sslmode", ["verify-full"])[0],
    }
    if (
        parsed.scheme not in ("postgres", "postgresql")
        or not parsed.username
        or not parsed.hostname
        or parsed.fragment
        or set(options) - {"sslmode"}
        or options.get("sslmode", ["verify-full"]) not in (["disable"], ["verify-full"])
        or any(ord(ch) < 32 for ch in raw_dsn)
        or any(any(ord(ch) < 32 for ch in value) for value in service_values.values())
    ):
        raise _refuse()
    sslmode = options.get("sslmode", ["verify-full"])[0]
    hostname = parsed.hostname
    if sslmode == "disable" and hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise _refuse()
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise _refuse()
    _service_file_bytes(service_values)
    pg_dump_path = Path(pg_dump_path)
    if (
        not pg_dump_path.is_absolute()
        or ".." in pg_dump_path.parts
        or pg_dump_path.name != "pg_dump"
    ):
        raise _refuse()

    parent_fd = _open_directory(pg_dump_path.parent, owner=os.geteuid())
    tool_fd = -1
    lib_fd = -1
    try:
        tool_fd = os.open(pg_dump_path.name, os.O_RDONLY | _NOFOLLOW | _CLOEXEC, dir_fd=parent_fd)
        tool_info = os.fstat(tool_fd)
        if (
            not stat.S_ISREG(tool_info.st_mode)
            or tool_info.st_uid != os.geteuid()
            or tool_info.st_nlink != 1
            or tool_info.st_mode & 0o022
            or not tool_info.st_mode & 0o100
            or _hash_fd(tool_fd) != _PG_DUMP_SHA256
        ):
            raise _refuse()
        lib_path = pg_dump_path.parent.parent / "lib"
        lib_fd = _open_directory(lib_path, owner=os.geteuid())
        return {
            "tool_fd": tool_fd,
            "tool_signature": _signature(tool_info),
            "lib_fd": lib_fd,
            "service_values": {
                **service_values,
            },
        }
    except BaseException:
        for fd in (tool_fd, lib_fd):
            if fd >= 0:
                os.close(fd)
        raise
    finally:
        os.close(parent_fd)


def _hash_fd(fd: int) -> str:
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        block = os.read(fd, 65536)
        if not block:
            break
        digest.update(block)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest()


def _service_file_bytes(values: dict[str, str]) -> bytes:
    if not isinstance(values, dict) or set(values) != set(_PG_SERVICE_KEYS):
        raise _refuse()
    lines = ["[quantmesh_bundle]"]
    for key in _PG_SERVICE_KEYS:
        value = values[key]
        if not isinstance(value, str):
            raise _refuse()
        try:
            value_bytes = value.encode("utf-8", errors="strict")
        except UnicodeError:
            raise _refuse() from None
        if any(byte < 32 or byte == 127 for byte in value_bytes):
            raise _refuse()
        if value_bytes and value_bytes[-1] in b" \t\n\r\v\f":
            raise _refuse()
        line = key.encode("ascii") + b"=" + value_bytes + b"\n"
        # libpq reads service files with a 1024-byte buffer and rejects a
        # line when fgets returns 1023 bytes or more.
        if len(line) > _PG_SERVICE_MAX_LINE_BYTES:
            raise _refuse()
        lines.append(line.decode("utf-8"))
    return (lines[0] + "\n" + "".join(lines[1:])).encode("utf-8")


def _identity_matches(parent_fd: int, name: str, expected: os.stat_result) -> bool:
    try:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        return False
    return stat.S_ISREG(current.st_mode) and (current.st_dev, current.st_ino) == (
        expected.st_dev,
        expected.st_ino,
    )


def _run_pg_dump(
    tool_fd: int, tool_signature: tuple, lib_fd: int, service_fd: int, snapshot: str, dump_fd: int
):
    tool_info = os.fstat(tool_fd)
    if _signature(tool_info) != tool_signature or _hash_fd(tool_fd) != _PG_DUMP_SHA256:
        raise _refuse()
    args = [
        "pg_dump",
        "--no-password",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--schema=qm_research",
        "--snapshot",
        snapshot,
        "--dbname=service=quantmesh_bundle",
    ]
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "PGSERVICEFILE": f"/proc/self/fd/{service_fd}",
        "LD_LIBRARY_PATH": f"/proc/self/fd/{lib_fd}",
    }
    process = None
    selector = selectors.DefaultSelector()
    stdout_bytes = stderr_bytes = 0
    digest = hashlib.sha256()
    deadline = time.monotonic() + _PG_DUMP_TIMEOUT_SECONDS
    try:
        process = subprocess.Popen(
            args,
            executable=f"/proc/self/fd/{tool_fd}",
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            close_fds=True,
            pass_fds=(tool_fd, lib_fd, service_fd),
            env=env,
        )
        assert process.stdout is not None and process.stderr is not None
        for stream, label in ((process.stdout, "stdout"), (process.stderr, "stderr")):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, label)
        open_streams = 2
        while open_streams:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _refuse()
            events = selector.select(min(remaining, 0.1))
            if not events and process.poll() is not None:
                # Pipes become readable at EOF; continue until both are unregistered.
                continue
            for key, _ in events:
                stream = key.fileobj
                label = key.data
                chunk = os.read(stream.fileno(), 65536)
                if not chunk:
                    selector.unregister(stream)
                    open_streams -= 1
                    continue
                if label == "stdout":
                    stdout_bytes += len(chunk)
                    if stdout_bytes > _MAX_PG_DUMP_BYTES:
                        raise _refuse()
                    digest.update(chunk)
                    _write_all(dump_fd, chunk)
                else:
                    stderr_bytes += len(chunk)
                    if stderr_bytes > _MAX_PG_DUMP_OUTPUT_BYTES:
                        raise _refuse()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise _refuse()
        if process.wait(timeout=remaining) != 0:
            raise _refuse()
        if stdout_bytes == 0:
            raise _refuse()
        os.fsync(dump_fd)
        info = os.fstat(dump_fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or info.st_nlink != 1
            or info.st_size != stdout_bytes
            or stdout_bytes > _MAX_PG_DUMP_BYTES
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise _refuse()
        return {"dump_size": stdout_bytes, "dump_sha256": digest.hexdigest()}
    except subprocess.TimeoutExpired:
        raise _refuse() from None
    finally:
        if process is not None:
            if process.poll() is None:
                try:
                    process.terminate()
                except OSError:
                    pass
                try:
                    process.wait(timeout=_PG_DUMP_TERMINATE_SECONDS)
                except subprocess.TimeoutExpired:
                    try:
                        process.kill()
                    except OSError:
                        pass
                    process.wait()
            # The exact Popen child has exited before caller can roll back the exporter.
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
        selector.close()


def capture_manifest(
    dsn: SecretStr,
    *,
    schema: str,
    lake_root: Path,
    artifact_root: Path,
    output_root: Path,
    policy: PortfolioBudgetPolicy | None,
) -> dict:
    if schema != _SCHEMA or not isinstance(dsn, SecretStr):
        raise _refuse()
    if policy is not None and not isinstance(policy, PortfolioBudgetPolicy):
        raise _refuse()

    connection = None
    artifact_root_fd = -1
    output_parent_fd = -1
    output_root_fd = -1
    output_complete = False
    output_name = Path(output_root).name
    try:
        artifact_root_fd = _open_directory(Path(artifact_root), owner=os.geteuid())
        # Keep the fixed lake root in the admission boundary without reading it.
        lake_fd = _open_directory(Path(lake_root), owner=os.geteuid())
        os.close(lake_fd)

        connection = connect(dsn)
        _execute(connection, "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        _execute(connection, "SET LOCAL statement_timeout='5s'")
        _execute(connection, 'SET LOCAL search_path TO "qm_research"')
        snapshot = _fetchone(connection, "SELECT pg_export_snapshot()")
        if not snapshot or not isinstance(snapshot[0], str) or not snapshot[0]:
            raise _refuse()

        state = _read_snapshot_state(connection, schema, policy)
        references, jobs = _checked_references(state, artifact_root_fd)
        manifest = _build_manifest(state, references, jobs, snapshot_was_exported=True)
        output_parent_fd, output_root_fd = _create_output_root(Path(output_root))
        for reference in references:
            _copy_one(artifact_root_fd, output_root_fd, reference)
        digest = _write_manifest(output_root_fd, manifest)
        _validate_artifact_tree(output_root_fd, references)
        output_complete = True
        return {
            "manifest_sha256": digest,
            "manifest": manifest,
            "snapshot_closed": True,
            "manifest_only": True,
        }
    except ManifestCaptureRefused:
        raise
    except (OSError, TypeError, ValueError, ArithmeticError):
        raise _refuse() from None
    finally:
        cleanup_failed = False
        if not output_complete and output_parent_fd >= 0 and output_root_fd >= 0:
            try:
                _remove_output_root(output_parent_fd, output_root_fd, output_name)
            except Exception:
                cleanup_failed = True
        if connection is not None:
            for close in (connection.rollback, connection.close):
                try:
                    close()
                except Exception:
                    cleanup_failed = True
        for fd in (output_root_fd, output_parent_fd, artifact_root_fd):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    cleanup_failed = True
        if cleanup_failed:
            raise _refuse() from None


def validate_manifest(root: Path, expected_digest: str) -> dict:
    if not isinstance(expected_digest, str) or not _SHA256.fullmatch(expected_digest):
        raise _refuse()
    root_fd = -1
    try:
        root_fd = _open_directory(Path(root), owner=os.geteuid(), private=True)
        raw = _read_private_file(root_fd, "manifest.json", limit=4 * 1024 * 1024)
        if _sha(raw) != expected_digest:
            raise _refuse()
        manifest = json.loads(raw)
        if (
            not isinstance(manifest, dict)
            or manifest.get("manifest_version") != 1
            or manifest.get("schema") != _SCHEMA
            or not isinstance(manifest.get("references"), list)
            or _canonical(manifest) != raw
        ):
            raise _refuse()
        _validate_artifact_tree(root_fd, manifest["references"])
        return manifest
    except ManifestCaptureRefused:
        raise
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        raise _refuse() from None
    finally:
        if root_fd >= 0:
            os.close(root_fd)


def capture_backup_bundle(
    dsn: SecretStr,
    *,
    schema: str,
    lake_root: Path,
    artifact_root: Path,
    output_root: Path,
    pg_dump_path: Path,
    policy: PortfolioBudgetPolicy | None,
) -> dict:
    """Capture a manifest and pg_dump archive from one exported MVCC snapshot."""
    connection = None
    artifact_root_fd = output_parent_fd = output_root_fd = -1
    capture_fd = service_fd = -1
    service_identity = None
    preserve_service_entry = False
    admission = None
    output_complete = False
    output_path = Path(output_root)
    output_name = output_path.name
    try:
        admission = _validate_bundle_inputs(dsn, schema, policy, Path(pg_dump_path))
        artifact_root_fd = _open_directory(Path(artifact_root), owner=os.geteuid())
        lake_fd = _open_directory(Path(lake_root), owner=os.geteuid())
        os.close(lake_fd)
        if not output_path.is_absolute() or output_name in {"", ".", ".."}:
            raise _refuse()
        output_parent_fd = _open_directory(output_path.parent, owner=os.geteuid())
        os.mkdir(output_name, 0o700, dir_fd=output_parent_fd)
        output_root_fd = os.open(
            output_name, os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC, dir_fd=output_parent_fd
        )
        _verify_subdir(output_root_fd, private=True)
        capture_fd = _mkdir_child(output_root_fd, "capture", private=True)
        os.mkdir("artifacts", 0o700, dir_fd=capture_fd)

        connection = connect(dsn)
        _execute(connection, "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        _execute(connection, "SET LOCAL statement_timeout='5s'")
        _execute(connection, 'SET LOCAL search_path TO "qm_research"')
        row = _fetchone(connection, "SELECT pg_export_snapshot()")
        if not row or not isinstance(row[0], str) or not row[0] or len(row[0]) > 256:
            raise _refuse()
        snapshot = row[0]
        state = _read_snapshot_state(connection, schema, policy)
        references, jobs = _checked_references(state, artifact_root_fd)
        manifest = _build_manifest(state, references, jobs, snapshot_was_exported=True)
        for reference in references:
            _copy_one(artifact_root_fd, capture_fd, reference)
        manifest_digest = _write_manifest(capture_fd, manifest)
        _validate_artifact_tree(capture_fd, references)

        service_raw = _service_file_bytes(admission["service_values"])
        service_fd = os.open(
            "pg-service.conf",
            os.O_RDWR | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _CLOEXEC,
            0o600,
            dir_fd=output_root_fd,
        )
        service_identity = os.fstat(service_fd)
        if (
            not stat.S_ISREG(service_identity.st_mode)
            or service_identity.st_uid != os.geteuid()
            or service_identity.st_nlink != 1
            or stat.S_IMODE(service_identity.st_mode) != 0o600
        ):
            raise _refuse()
        _write_all(service_fd, service_raw)
        os.fsync(service_fd)
        os.lseek(service_fd, 0, os.SEEK_SET)
        dump_fd = os.open(
            "research.dump",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _CLOEXEC,
            0o600,
            dir_fd=output_root_fd,
        )
        try:
            dump_info = _run_pg_dump(
                admission["tool_fd"],
                admission["tool_signature"],
                admission["lib_fd"],
                service_fd,
                snapshot,
                dump_fd,
            )
        finally:
            os.close(dump_fd)
        if _identity_matches(output_root_fd, "pg-service.conf", service_identity):
            os.unlink("pg-service.conf", dir_fd=output_root_fd)
        else:
            preserve_service_entry = True
            raise _refuse()
        os.close(service_fd)
        service_fd = -1

        bundle = {
            "bundle_version": 1,
            "schema": _SCHEMA,
            "manifest_sha256": manifest_digest,
            "dump_sha256": dump_info["dump_sha256"],
            "dump_size": dump_info["dump_size"],
        }
        bundle_raw = _canonical(bundle)
        bundle_fd = os.open(
            "bundle.json",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW | _CLOEXEC,
            0o600,
            dir_fd=output_root_fd,
        )
        try:
            _write_all(bundle_fd, bundle_raw)
            os.fsync(bundle_fd)
        finally:
            os.close(bundle_fd)
        if set(os.listdir(output_root_fd)) != {"capture", "research.dump", "bundle.json"}:
            raise _refuse()
        bundle_digest = _sha(bundle_raw)
        _validate_backup_bundle_fd(output_root_fd, bundle_digest)
        result = {
            "manifest_sha256": bundle["manifest_sha256"],
            "dump_sha256": bundle["dump_sha256"],
            "dump_size": bundle["dump_size"],
            "bundle_sha256": bundle_digest,
            "snapshot_closed": True,
            "manifest_only": False,
            "manifest": manifest,
        }
        output_complete = True
        return result
    except ManifestCaptureRefused:
        raise
    except Exception:
        raise _refuse() from None
    finally:
        cleanup_failed = False
        if service_fd >= 0:
            try:
                if service_identity is not None and _identity_matches(
                    output_root_fd, "pg-service.conf", service_identity
                ):
                    os.unlink("pg-service.conf", dir_fd=output_root_fd)
                elif service_identity is not None:
                    preserve_service_entry = True
            except Exception:
                cleanup_failed = True
            try:
                os.close(service_fd)
            except OSError:
                cleanup_failed = True
        if connection is not None:
            for close in (connection.rollback, connection.close):
                try:
                    close()
                except Exception:
                    cleanup_failed = True
        if not output_complete and output_parent_fd >= 0 and output_root_fd >= 0:
            try:
                _remove_output_root(
                    output_parent_fd,
                    output_root_fd,
                    output_name,
                    preserve=frozenset({"pg-service.conf"})
                    if preserve_service_entry
                    else frozenset(),
                )
            except Exception:
                cleanup_failed = True
        for fd in (
            capture_fd,
            output_root_fd,
            output_parent_fd,
            artifact_root_fd,
            admission["tool_fd"] if admission else -1,
            admission["lib_fd"] if admission else -1,
        ):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    cleanup_failed = True
        if cleanup_failed:
            raise _refuse() from None


def validate_backup_bundle(root: Path, expected_digest: str) -> dict:
    if not isinstance(expected_digest, str) or not _SHA256.fullmatch(expected_digest):
        raise _refuse()
    root_fd = capture_fd = -1
    try:
        root_fd = _open_directory(Path(root), owner=os.geteuid(), private=True)
        if set(os.listdir(root_fd)) != {"capture", "research.dump", "bundle.json"}:
            raise _refuse()
        raw = _read_private_file(root_fd, "bundle.json", limit=4096)
        if _sha(raw) != expected_digest:
            raise _refuse()
        bundle = json.loads(raw)
        required = {
            "bundle_version",
            "schema",
            "manifest_sha256",
            "dump_sha256",
            "dump_size",
        }
        if (
            not isinstance(bundle, dict)
            or set(bundle) != required
            or bundle.get("bundle_version") != 1
            or bundle.get("schema") != _SCHEMA
            or not isinstance(bundle.get("manifest_sha256"), str)
            or not _SHA256.fullmatch(bundle["manifest_sha256"])
            or not isinstance(bundle.get("dump_sha256"), str)
            or not _SHA256.fullmatch(bundle["dump_sha256"])
            or type(bundle.get("dump_size")) is not int
            or not 0 < bundle["dump_size"] <= _MAX_PG_DUMP_BYTES
            or _canonical(bundle) != raw
        ):
            raise _refuse()
        dump = _read_private_file(root_fd, "research.dump", limit=_MAX_PG_DUMP_BYTES)
        if len(dump) != bundle["dump_size"] or _sha(dump) != bundle["dump_sha256"]:
            raise _refuse()
        capture_fd = os.open(
            "capture", os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC, dir_fd=root_fd
        )
        _verify_subdir(capture_fd, private=True)
        manifest = _validate_manifest_fd(capture_fd, bundle["manifest_sha256"])
        return {**bundle, "bundle_sha256": expected_digest, "manifest": manifest}
    except ManifestCaptureRefused:
        raise
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        raise _refuse() from None
    finally:
        for fd in (capture_fd, root_fd):
            if fd >= 0:
                os.close(fd)


def _validate_manifest_fd(root_fd: int, expected_digest: str) -> dict:
    raw = _read_private_file(root_fd, "manifest.json", limit=4 * 1024 * 1024)
    if _sha(raw) != expected_digest:
        raise _refuse()
    manifest = json.loads(raw)
    if (
        not isinstance(manifest, dict)
        or manifest.get("manifest_version") != 1
        or manifest.get("schema") != _SCHEMA
        or not isinstance(manifest.get("references"), list)
        or _canonical(manifest) != raw
    ):
        raise _refuse()
    _validate_artifact_tree(root_fd, manifest["references"])
    return manifest


def _validate_backup_bundle_fd(root_fd: int, expected_digest: str) -> dict:
    if set(os.listdir(root_fd)) != {"capture", "research.dump", "bundle.json"}:
        raise _refuse()
    raw = _read_private_file(root_fd, "bundle.json", limit=4096)
    if _sha(raw) != expected_digest:
        raise _refuse()
    bundle = json.loads(raw)
    required = {"bundle_version", "schema", "manifest_sha256", "dump_sha256", "dump_size"}
    if (
        not isinstance(bundle, dict)
        or set(bundle) != required
        or bundle.get("bundle_version") != 1
        or bundle.get("schema") != _SCHEMA
        or not isinstance(bundle.get("manifest_sha256"), str)
        or not _SHA256.fullmatch(bundle["manifest_sha256"])
        or not isinstance(bundle.get("dump_sha256"), str)
        or not _SHA256.fullmatch(bundle["dump_sha256"])
        or type(bundle.get("dump_size")) is not int
        or not 0 < bundle["dump_size"] <= _MAX_PG_DUMP_BYTES
        or _canonical(bundle) != raw
    ):
        raise _refuse()
    dump = _read_private_file(root_fd, "research.dump", limit=_MAX_PG_DUMP_BYTES)
    if len(dump) != bundle["dump_size"] or _sha(dump) != bundle["dump_sha256"]:
        raise _refuse()
    capture_fd = os.open("capture", os.O_RDONLY | _DIRECTORY | _NOFOLLOW | _CLOEXEC, dir_fd=root_fd)
    try:
        _verify_subdir(capture_fd, private=True)
        manifest = _validate_manifest_fd(capture_fd, bundle["manifest_sha256"])
    finally:
        os.close(capture_fd)
    return {**bundle, "bundle_sha256": expected_digest, "manifest": manifest}
