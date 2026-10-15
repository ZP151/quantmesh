"""Job-scoped, bounded reader for a pinned fixture lake."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime, timezone
from pathlib import Path

import duckdb

from quantmesh.data.lake import Dataset, Lake
from quantmesh.data.layout import validate_dataset_name
from quantmesh.domain.market_data import Bar
from quantmesh.domain.models import Venue
from quantmesh.research._fixture_handles import UnsupportedSnapshotProfile, require_snapshot_profile
from quantmesh.research._fixture_parquet_guard import validate_metadata
from quantmesh.research._fixture_rows import rows_to_bars
from quantmesh.research._fixture_sealed import sealed_shard
from quantmesh.research.fixture_snapshot import (
    MAX_MANIFEST_BYTES,
    MAX_SHARD_BYTES,
    MAX_SNAPSHOT_BYTES,
    _Copy,
    _export,
    _parse_manifest,
    _validate_request_shape,
)
from quantmesh.research.jobs import DatasetRef, DatasetRejected, JobRecord

_MAX_ACTUAL_ROWS = 1_000_000
_CHUNK = 1024
_PATH_TYPE = type(Path("."))
_DUCKDB_CONFIG = {
    "threads": "1",
    "memory_limit": "32MB",
    "temp_directory": "",
    "autoload_known_extensions": "false",
    "autoinstall_known_extensions": "false",
    "allow_unsigned_extensions": "false",
    "allow_community_extensions": "false",
    "allow_persistent_secrets": "false",
}


def _invalid() -> None:
    raise DatasetRejected("fixture_reader_invalid")


def _valid_pins(value: object) -> bool:
    if type(value) is not dict:
        return False
    for path, item in value.items():
        if type(path) is not _PATH_TYPE or type(item) is not tuple or len(item) != 2:
            return False
        digest, identity = item
        if (
            type(digest) is not str
            or len(digest) != 64
            or type(identity) is not tuple
            or len(identity) != 10
            or any(type(cell) is not int for cell in identity)
        ):
            return False
    return True


def _same_pins(left: object, right: object) -> bool:
    if not _valid_pins(left) or not _valid_pins(right) or len(left) != len(right):
        return False
    for path, (digest, identity) in left.items():
        if path not in right:
            return False
        other_digest, other_identity = right[path]
        if digest != other_digest or identity != other_identity:
            return False
    return True


def _logical_projection(value: object) -> list[tuple[str, str]]:
    if type(value) is not list or len(value) > 9:
        _invalid()
    projected = []
    for row in value:
        if (type(row) is not tuple and type(row) is not list) or len(row) != 6:
            _invalid()
        if type(row[0]) is not str or type(row[1]) is not str:
            _invalid()
        projected.append((row[0], row[1]))
    return projected


def _setting_matches(actual: object, expected: object) -> bool:
    if type(expected) is list:
        if type(actual) is not list or len(actual) != len(expected):
            return False
        if any(type(item) is not str for item in actual):
            return False
        return all(a == b for a, b in zip(actual, expected, strict=True))
    if type(expected) is str:
        return type(actual) is str and actual == expected
    if type(expected) is int:
        return type(actual) is int and actual == expected
    if type(expected) is bool:
        return type(actual) is bool and actual == expected
    return False


def _rows(value: object, limit: int) -> list:
    if type(value) is not list or len(value) > limit:
        _invalid()
    return value


class FixtureReader:
    """One live, pinned fixture view whose decoded rows are privately cached.

    DuckDB configuration here is a read prerequisite; it is not a full kernel
    profile qualification or admission decision.
    """

    def __init__(self, job: JobRecord, root: Path, deadline: float):
        self.job = job
        self.root = Path(root).absolute()
        self.deadline = deadline
        self._copy = None
        self._pinned = None
        self._manifest = None
        self._dataset = None
        self._cache: dict[tuple[str, Venue, str], list[Bar]] = {}
        self._closed = True

    def __enter__(self) -> FixtureReader:
        if not self._closed:
            _invalid()
        require_snapshot_profile()
        self._copy = _Copy(self.deadline, self.root, self.root)
        try:
            self._copy.__enter__()
            self._closed = False
            ref = self.job.request.dataset
            validate_dataset_name(ref.dataset_id)
            if ref.permission_class != "fixture":
                _invalid()
            base = self.root / ref.dataset_id
            digest, identity, raw = self._copy.stream(
                base / "manifest.json", min(MAX_MANIFEST_BYTES, MAX_SNAPSHOT_BYTES), collect=True
            )
            if not raw or digest != ref.manifest_digest or identity[8] != os.getuid():
                _invalid()
            manifest = _parse_manifest(raw)
            if (
                manifest.dataset != ref.dataset_id
                or manifest.revision != ref.revision
                or manifest.source != "fixture"
                or manifest.license != "test"
            ):
                _invalid()
            _validate_request_shape(self.job, manifest)
            pinned = self._copy.pin(base, manifest, raw)
            if not _valid_pins(pinned):
                _invalid()
            if (
                pinned.get(Path("manifest.json")) != (digest, identity)
                or _export(pinned) != ref.export_digest
            ):
                _invalid()
            total = sum(item[1][4] for item in pinned.values())
            if not 0 < total <= MAX_SNAPSHOT_BYTES:
                _invalid()
            uid = os.getuid()
            if any(type(entry) is not tuple or entry[1][8] != uid for entry in pinned.values()):
                _invalid()
            self._copy.finish()
            self._pinned, self._manifest = pinned, manifest
            self._dataset = Dataset(Lake(self.root), ref.dataset_id, manifest)
            self._load_all()
            self._check_pin()
            return self
        except BaseException as error:
            self.close()
            if isinstance(error, (DatasetRejected, UnsupportedSnapshotProfile)):
                raise
            if isinstance(error, Exception):
                _invalid()
            raise

    def __exit__(self, *error) -> None:
        if self._closed:
            return False
        if error and error[0] is not None:
            try:
                self._check_pin()
            except BaseException:
                pass
            try:
                self.close()
            except BaseException:
                pass
            return False
        try:
            self._check_pin()
        except BaseException:
            try:
                self.close()
            except BaseException:
                pass
            raise
        self.close()
        return False

    def close(self) -> None:
        self._closed = True
        self._cache.clear()
        copy, self._copy = self._copy, None
        if copy is not None:
            copy.__exit__()

    def _live(self) -> None:
        if self._closed or self._copy is None:
            _invalid()
        self._deadline()

    def _deadline(self) -> None:
        if time.monotonic() >= self.deadline:
            _invalid()

    def _check_pin(self) -> None:
        self._live()
        try:
            ref = self.job.request.dataset
            base = self.root / ref.dataset_id
            digest, identity, raw = self._copy.stream(
                base / "manifest.json", min(MAX_MANIFEST_BYTES, MAX_SNAPSHOT_BYTES), collect=True
            )
            current = self._copy.pin(base, self._manifest, raw)
            if digest != ref.manifest_digest or identity[8] != os.getuid():
                _invalid()
            if not _same_pins(current, self._pinned):
                _invalid()
            if _export(current) != ref.export_digest:
                _invalid()
            self._copy.finish()
        except (DatasetRejected, UnsupportedSnapshotProfile):
            raise
        except Exception:
            _invalid()

    def pin(self) -> tuple[DatasetRef, Dataset]:
        self._check_pin()
        return self.job.request.dataset, self._dataset

    def dataset(self) -> Dataset:
        return self.pin()[1]

    def _load_all(self) -> None:
        self._deadline()
        declared = {(c.interval, c.venue, c.symbol): c for c in self._manifest.coverage}
        observed: dict[tuple[str, Venue, str], list[Bar]] = {key: [] for key in declared}
        total_rows = 0
        base = self.root / self._manifest.dataset
        shards = [path for path in self._pinned if path != Path("manifest.json")]
        if len(shards) > 4096:
            _invalid()
        sealed_total = 0
        for relative in sorted(shards):
            self._deadline()
            parts = relative.parts
            if len(parts) != 5:
                _invalid()
            interval, venue_text, symbol, day, filename = parts
            if filename != "shard-0000.parquet":
                _invalid()
            try:
                venue = Venue(venue_text)
            except ValueError:
                _invalid()
            key = interval, venue, symbol
            if key not in declared:
                _invalid()
            coverage = declared[key]
            remaining_series = coverage.rows - len(observed[key])
            remaining_global = _MAX_ACTUAL_ROWS - total_rows
            if min(remaining_series, remaining_global) < 1:
                _invalid()
            expected_hash, identity = self._pinned[relative]
            limit = min(MAX_SHARD_BYTES, MAX_SNAPSHOT_BYTES - sealed_total)
            if limit < 1:
                _invalid()
            with sealed_shard(
                self._copy.handles, base / relative, self.deadline, limit=limit
            ) as sealed:
                self._deadline()
                if sealed.sha256 != expected_hash or sealed.size != identity[4]:
                    _invalid()
                sealed_total += sealed.size
                if sealed_total > MAX_SNAPSHOT_BYTES:
                    _invalid()
                con = None
                try:
                    con = duckdb.connect(config=dict(_DUCKDB_CONFIG))
                    self._configure(con, sealed.alias)
                    logical = self._query(
                        con, "DESCRIBE SELECT * FROM read_parquet(?)", [sealed.alias], 9
                    )
                    logical_rows = _logical_projection(logical)
                    physical = self._query(
                        con,
                        "SELECT name,type,repetition_type,num_children,converted_type,logical_type "
                        "FROM parquet_schema(?)",
                        [sealed.alias],
                        10,
                    )
                    physical_rows = _rows(physical, 10)
                    footer = self._query(
                        con,
                        "SELECT num_rows,num_row_groups,format_version "
                        "FROM parquet_file_metadata(?)",
                        [sealed.alias],
                        2,
                    )
                    actual = validate_metadata(
                        logical_rows, physical_rows, footer, min(remaining_series, remaining_global)
                    )
                    read = con.execute(
                        "SELECT epoch_us(timestamp),open,high,low,close,volume,instrument_type,"
                        "currency "
                        "FROM read_parquet(?)",
                        [sealed.alias],
                    )
                    file_rows = 0
                    while True:
                        self._deadline()
                        chunk = _rows(read.fetchmany(_CHUNK), min(_CHUNK, actual - file_rows))
                        self._deadline()
                        if not chunk:
                            break
                        if (
                            file_rows + len(chunk) > actual
                            or total_rows + len(chunk) > _MAX_ACTUAL_ROWS
                        ):
                            _invalid()
                        bars = rows_to_bars(
                            chunk, interval=interval, venue=venue, symbol=symbol, day=day
                        )
                        observed[key].extend(bars)
                        file_rows += len(chunk)
                        total_rows += len(chunk)
                    if file_rows != actual:
                        _invalid()
                finally:
                    if con is not None:
                        con.close()
        for key, coverage in declared.items():
            self._deadline()
            bars = observed[key]
            if (
                len(bars) != coverage.rows
                or not bars
                or bars[0].timestamp != coverage.start
                or bars[-1].timestamp != coverage.end
            ):
                _invalid()
            for index in range(1, len(bars)):
                if index % _CHUNK == 0:
                    self._deadline()
                if bars[index - 1].timestamp >= bars[index].timestamp:
                    _invalid()
        self._cache = observed

    def _query(self, con, sql: str, params: list, maximum: int) -> object:
        self._deadline()
        cursor = con.execute(sql, params)
        self._deadline()
        result = cursor.fetchmany(maximum + 1)
        self._deadline()
        if type(result) is not list or len(result) > maximum:
            _invalid()
        return result

    def _configure(self, con, alias: str) -> None:
        for name, value in (
            ("temp_directory", "''"),
            ("allowed_directories", "[]"),
            ("allowed_paths", f"['{alias}']"),
            ("enable_external_access", "false"),
            ("lock_configuration", "true"),
        ):
            self._deadline()
            con.execute(f"SET {name}={value}")
        self._deadline()
        names = [
            "threads",
            "memory_limit",
            "temp_directory",
            "autoload_known_extensions",
            "autoinstall_known_extensions",
            "allow_unsigned_extensions",
            "allow_community_extensions",
            "allow_persistent_secrets",
            "allowed_directories",
            "allowed_paths",
            "enable_external_access",
            "lock_configuration",
        ]
        cursor = con.execute("SELECT " + ",".join(f"current_setting('{name}')" for name in names))
        self._deadline()
        values = cursor.fetchmany(2)
        self._deadline()
        if type(values) is not list or len(values) != 1:
            _invalid()
        row = values[0]
        if (type(row) is not tuple and type(row) is not list) or len(row) != len(names):
            _invalid()
        expected = [1, "30.5 MiB", "", False, False, False, False, False, [], [alias], False, True]
        if any(not _setting_matches(a, b) for a, b in zip(row, expected, strict=True)):
            _invalid()

    def read_bars(
        self,
        *,
        interval: str,
        venue: Venue,
        symbol: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Bar]:
        self._check_pin()
        if type(interval) is not str or type(venue) is not Venue or type(symbol) is not str:
            _invalid()
        if len(interval) > 512 or len(symbol) > 512:
            _invalid()
        key = interval, venue, symbol
        if key not in self._cache:
            _invalid()
        bounds = []
        for value in (start, end):
            if value is None:
                bounds.append(None)
                continue
            if type(value) is not datetime:
                _invalid()
            if value.tzinfo is None or type(value.tzinfo) is not timezone:
                _invalid()
            if value.utcoffset() is None:
                _invalid()
            bounds.append(value.astimezone(UTC))
        start, end = bounds
        selected = []
        for index, bar in enumerate(self._cache[key]):
            if index % _CHUNK == 0:
                self._deadline()
            if (start is None or bar.timestamp >= start) and (end is None or bar.timestamp <= end):
                selected.append(bar)
        return selected
