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


def _export(pinned: dict[Path, tuple[str, tuple[int, ...]]]) -> str:
    entries = sorted(
        (path.as_posix(), digest)
        for path, (digest, _) in pinned.items()
        if path != Path("manifest.json")
    )
    return hashlib.sha256(
        json.dumps(entries, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


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
        declared = json.loads(
            raw, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float
        )
        if (
            type(declared) is not dict
            or type(declared.get("coverage")) is not list
            or len(declared["coverage"]) > MAX_COVERAGE
            or type(declared.get("schema_version", 1)) is not int
            or declared.get("schema_version", 1) != 1
        ):
            _invalid()
        manifest = DatasetManifest.model_validate(declared)
        if (
            manifest.dataset != ref.dataset_id
            or manifest.revision != ref.revision
            or manifest.source != "fixture"
            or manifest.license != "test"
        ):
            _invalid()
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
