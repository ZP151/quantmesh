"""Bounded fixture metadata and byte copying; no Parquet content admission."""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import time
from pathlib import Path

from quantmesh.data.layout import DAY_PATTERN, SHARD_NAME, validate_dataset_name
from quantmesh.data.manifest import DatasetManifest
from quantmesh.research._fixture_handles import DirectoryHandles, require_snapshot_profile
from quantmesh.research.jobs import DatasetRejected, JobRecord

MAX_MANIFEST_BYTES = 256 * 1024
MAX_COVERAGE = 64
MAX_JSON_DEPTH = 16
MAX_JSON_NODES = 32_768
MAX_JSON_STRING = 512
MAX_DECLARED_ROWS = 1_000_000
MAX_UNIVERSE = 64
MAX_WALK_FORWARD_WINDOWS = 4096
MAX_SHARDS = 4096
MAX_SHARD_BYTES = 256 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 256 * 1024 * 1024
BUFFER_BYTES = 512 * 1024


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        getattr(info, "st_file_attributes", 0),
        info.st_uid,
        info.st_gid,
    )


def _invalid() -> None:
    raise DatasetRejected("fixture_snapshot_invalid")


class _Copy:
    def __init__(self, deadline: float, source: Path, target: Path):
        self.deadline = deadline
        self.written: dict[Path, tuple[int, ...]] = {}
        self.handles = DirectoryHandles({"source": source, "target": target}, self.check)

    def __enter__(self):
        return self

    def __exit__(self, *error):
        self.handles.__exit__(*error)

    def role(self, path: Path) -> str:
        return "target" if path.is_relative_to(self.handles.roots["target"]) else "source"

    def check(self) -> None:
        if time.monotonic() >= self.deadline:
            _invalid()

    def stream(
        self,
        path: Path,
        limit: int,
        *,
        collect: bool = False,
        target: Path | None = None,
        expected: tuple[int, ...] | None = None,
    ) -> tuple[str, tuple[int, ...], bytes]:
        role = self.role(path)
        fd = self.handles.open_file(
            path,
            os.O_RDONLY | os.O_NONBLOCK,
            role,
        )
        output = None
        try:
            before = os.fstat(fd)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or not 0 <= before.st_size <= limit
                or (expected is not None and _identity(before) != expected)
            ):
                _invalid()
            if target is not None:
                output = self.handles.open_file(
                    target,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    "target",
                )
            digest, chunks, remaining = hashlib.sha256(), [], before.st_size
            while remaining:
                self.check()
                chunk = os.read(fd, min(remaining, BUFFER_BYTES))
                if not chunk:
                    _invalid()
                remaining -= len(chunk)
                digest.update(chunk)
                if collect:
                    chunks.append(chunk)
                if output is not None:
                    view = memoryview(chunk)
                    while view:
                        self.check()
                        written = os.write(output, view)
                        if written <= 0:
                            _invalid()
                        view = view[written:]
            self.check()
            if os.read(fd, 1):
                _invalid()
            if _identity(before) != _identity(os.fstat(fd)) or _identity(before) != _identity(
                self.handles.file_stat(path, role)
            ):
                _invalid()
            if output is not None:
                copied = os.fstat(output)
                if (
                    not stat.S_ISREG(copied.st_mode)
                    or copied.st_nlink != 1
                    or copied.st_size != before.st_size
                    or _identity(copied) != _identity(self.handles.file_stat(target, "target"))
                ):
                    _invalid()
                self.written[target] = _identity(copied)
            if path in self.written and _identity(before) != self.written[path]:
                _invalid()
            return digest.hexdigest(), _identity(before), b"".join(chunks)
        finally:
            if output is not None:
                self.handles.close_file(output)
            self.handles.close_file(fd)

    def discover(self, dataset: Path, manifest: DatasetManifest) -> list[Path]:
        paths = []
        for coverage in manifest.coverage:
            partition = dataset / coverage.interval / coverage.venue.value / coverage.symbol
            role = self.role(partition)
            with self.handles.scan(partition, role) as entries:
                for entry in entries:
                    self.check()
                    if DAY_PATTERN.fullmatch(entry.name) is None:
                        continue
                    day = partition / entry.name
                    self.handles.directory(day, role)
                    shard = day / SHARD_NAME
                    try:
                        self.handles.file_stat(shard, role)
                    except FileNotFoundError:
                        continue
                    if len(paths) >= MAX_SHARDS:
                        _invalid()
                    paths.append(shard)
        return sorted(paths)

    def pin(
        self, dataset: Path, manifest: DatasetManifest, raw: bytes
    ) -> dict[Path, tuple[str, tuple[int, ...]]]:
        manifest_digest, manifest_identity, current = self.stream(
            dataset / "manifest.json", min(MAX_MANIFEST_BYTES, MAX_SNAPSHOT_BYTES), collect=True
        )
        if current != raw:
            _invalid()
        pinned = {Path("manifest.json"): (manifest_digest, manifest_identity)}
        total = len(raw)
        for path in self.discover(dataset, manifest):
            digest, identity, _ = self.stream(
                path, min(MAX_SHARD_BYTES, MAX_SNAPSHOT_BYTES - total)
            )
            total += identity[4]
            pinned[path.relative_to(dataset)] = digest, identity
        return pinned

    def finish(self) -> None:
        self.handles.verify()


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for name, value in pairs:
        if name in result:
            _invalid()
        result[name] = value
    return result


def _constant(value: str) -> None:
    _invalid()


def _float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        _invalid()
    return result


def _parse_manifest(raw: bytes) -> DatasetManifest:
    """Bound declaration parsing only; actual Parquet row limits remain separate."""
    try:
        if type(raw) is not bytes or not 0 < len(raw) <= MAX_MANIFEST_BYTES:
            _invalid()
        text = raw.decode("utf-8")
        depth, quoted, escaped = 0, False, False
        for char in text:
            if quoted:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    quoted = False
            elif char == '"':
                quoted = True
            elif char in "[{":
                depth += 1
                if depth > MAX_JSON_DEPTH:
                    _invalid()
            elif char in "]}":
                depth -= 1
                if depth < 0:
                    _invalid()
        declared = json.loads(
            text, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float
        )
        pending, nodes = [declared], 0
        while pending:
            value = pending.pop()
            nodes += 1
            if nodes > MAX_JSON_NODES:
                _invalid()
            if type(value) is dict:
                pending.extend(value.keys())
                pending.extend(value.values())
            elif type(value) is list:
                pending.extend(value)
            elif type(value) is str and len(value) > MAX_JSON_STRING:
                _invalid()
        if (
            type(declared) is not dict
            or set(declared)
            - {
                "schema_version",
                "dataset",
                "source",
                "data_class",
                "timezone",
                "license",
                "revision",
                "generated_at",
                "coverage",
            }
            or type(declared.get("coverage")) is not list
            or len(declared["coverage"]) > MAX_COVERAGE
            or type(declared.get("schema_version", 1)) is not int
            or declared.get("schema_version", 1) != 1
            or type(declared.get("revision")) is not int
            or declared["revision"] < 1
        ):
            _invalid()
        for name in ("dataset", "source", "timezone", "license", "generated_at"):
            if name in declared and type(declared[name]) is not str:
                _invalid()
        if declared.get("data_class") is not None and type(declared["data_class"]) is not str:
            _invalid()
        total_rows = 0
        for entry in declared["coverage"]:
            if (
                type(entry) is not dict
                or set(entry) != {"interval", "venue", "symbol", "start", "end", "rows"}
                or type(entry["rows"]) is not int
                or entry["rows"] < 1
                or any(type(entry[name]) is not str for name in entry if name != "rows")
            ):
                _invalid()
            total_rows += entry["rows"]
            if total_rows > MAX_DECLARED_ROWS:
                _invalid()
        return DatasetManifest.model_validate(declared)
    except (ValueError, TypeError, RecursionError, OverflowError):
        raise DatasetRejected("fixture_snapshot_invalid") from None


def _export(pinned: dict[Path, tuple[str, tuple[int, ...]]]) -> str:
    entries = sorted(
        (path.as_posix(), digest)
        for path, (digest, _) in pinned.items()
        if path != Path("manifest.json")
    )
    return hashlib.sha256(
        json.dumps(entries, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _validate_request_shape(job: JobRecord, manifest: DatasetManifest) -> None:
    """Bound declared allocations; the child must still verify actual row grids."""
    request = job.request
    if not 0 < len(request.universe) <= MAX_UNIVERSE:
        _invalid()
    counts = {
        (entry.interval, entry.venue.value, entry.symbol): entry.rows for entry in manifest.coverage
    }
    selected = []
    for member in request.universe:
        key = request.interval, member.venue.value, member.symbol
        if key not in counts:
            _invalid()
        selected.append(counts[key])
    if len(set(selected)) != 1:
        _invalid()
    spec = request.window_spec
    train, test, step = spec.train_bars, spec.test_bars, spec.step_bars
    if (
        any(type(n) is not int for n in (train, test, step))
        or train < 2
        or test < 1
        or step < test
        or selected[0] < train + test
    ):
        _invalid()
    windows = (selected[0] - train - test) // step + 1
    if windows > MAX_WALK_FORWARD_WINDOWS:
        _invalid()


def copy_fixture_snapshot(job: JobRecord, source: Path, destination: Path) -> None:
    """Copy the pinned covered bytes; the isolated child must validate their content."""
    require_snapshot_profile()
    copy = None
    try:
        copy = _Copy(
            time.monotonic() + min(10, job.request.budget.timeout_seconds),
            source.absolute(),
            destination.absolute(),
        )
        ref = job.request.dataset
        validate_dataset_name(ref.dataset_id)
        dataset = source.absolute() / ref.dataset_id
        target = destination.absolute() / ref.dataset_id
        if target.is_relative_to(dataset) or dataset.is_relative_to(target):
            _invalid()
        digest, identity, raw = copy.stream(
            dataset / "manifest.json", min(MAX_MANIFEST_BYTES, MAX_SNAPSHOT_BYTES), collect=True
        )
        if not raw or digest != ref.manifest_digest or ref.permission_class != "fixture":
            _invalid()
        manifest = _parse_manifest(raw)
        if (
            manifest.dataset != ref.dataset_id
            or manifest.revision != ref.revision
            or manifest.source != "fixture"
            or manifest.license != "test"
        ):
            _invalid()
        _validate_request_shape(job, manifest)
        pinned = copy.pin(dataset, manifest, raw)
        if (
            pinned[Path("manifest.json")] != (digest, identity)
            or _export(pinned) != ref.export_digest
        ):
            _invalid()
        for relative, (expected_digest, expected_identity) in pinned.items():
            limit = MAX_MANIFEST_BYTES if relative == Path("manifest.json") else MAX_SHARD_BYTES
            observed, _, _ = copy.stream(
                dataset / relative, limit, target=target / relative, expected=expected_identity
            )
            if observed != expected_digest:
                _invalid()
        if copy.pin(dataset, manifest, raw) != pinned:
            _invalid()
        copied = copy.pin(target, manifest, raw)
        if {p: d for p, (d, _) in copied.items()} != {p: d for p, (d, _) in pinned.items()}:
            _invalid()
        copy.finish()
    except DatasetRejected:
        raise
    except (OSError, ValueError, TypeError, RecursionError, OverflowError):
        raise DatasetRejected("fixture_snapshot_invalid") from None
    finally:
        if copy is not None:
            copy.__exit__()
