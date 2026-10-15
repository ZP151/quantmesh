from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantmesh.research import _fixture_reader as reader
from quantmesh.research.jobs import DatasetRejected


class Copy:
    raw = b"{}"
    pin_value = {Path("manifest.json"): ("a" * 64, (0, 1, 2, 1, 2, 3, 4, 0, 1000, 1000))}
    events = []

    def __init__(self, deadline, source, target):
        self.events.append(("copy", source, target))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.events.append(("copy-close",))

    def stream(self, path, limit, *, collect=False, **kwargs):
        self.events.append(("stream", path.name, limit, collect))
        return "a" * 64, self.pin_value[Path("manifest.json")][1], self.raw if collect else b""

    def pin(self, dataset, manifest, raw):
        self.events.append(("pin",))
        return self.pin_value

    def finish(self):
        self.events.append(("finish",))


class FakeConnection:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def execute(self, sql, params=None):
        self.events.append(("sql", sql, params))
        return self

    def fetchmany(self, count):
        return []

    def close(self):
        self.closed = True
        self.events.append(("conn-close",))


class ConfigConnection:
    def __init__(self, values):
        self.values = values
        self.events = []

    def execute(self, sql, params=None):
        self.events.append((sql, params))
        return self

    def fetchmany(self, count):
        return [self.values]


READER_CONFIG = {
    "threads": "1",
    "memory_limit": "32MB",
    "temp_directory": "",
    "autoload_known_extensions": "false",
    "autoinstall_known_extensions": "false",
    "allow_unsigned_extensions": "false",
    "allow_community_extensions": "false",
    "allow_persistent_secrets": "false",
}


@pytest.fixture
def setup_reader(monkeypatch, tmp_path):
    Copy.events = []
    Copy.pin_value = {Path("manifest.json"): ("a" * 64, (0, 1, 2, 1, 2, 3, 4, 0, 1000, 1000))}
    monkeypatch.setattr(reader, "_Copy", Copy)
    monkeypatch.setattr(reader, "require_snapshot_profile", lambda: None)
    monkeypatch.setattr("os.getuid", lambda: 1000, raising=False)
    manifest = SimpleNamespace(
        dataset="equities", revision=1, source="fixture", license="test", coverage=[]
    )
    monkeypatch.setattr(reader, "_parse_manifest", lambda raw: manifest)
    monkeypatch.setattr(reader, "_validate_request_shape", lambda job, parsed: None)
    job = SimpleNamespace(
        request=SimpleNamespace(
            dataset=SimpleNamespace(
                dataset_id="equities",
                revision=1,
                permission_class="fixture",
                manifest_digest="a" * 64,
                export_digest=reader._export(Copy.pin_value),
            ),
            universe=[],
            interval="1h",
            window_spec=None,
            budget=SimpleNamespace(timeout_seconds=8),
        )
    )
    return job, tmp_path


def test_reader_pins_manifest_before_decoder_and_closes_on_exit(setup_reader, monkeypatch):
    job, root = setup_reader
    conns = []

    class Duck:
        @staticmethod
        def connect(*args, **kwargs):
            con = FakeConnection(Copy.events)
            conns.append(con)
            return con

    monkeypatch.setattr(reader, "duckdb", Duck)
    with reader.FixtureReader(job, root, 9999999999):
        pass
    names = [item[0] for item in Copy.events]
    assert names.index("pin") < names.index("copy-close")
    assert all(con.closed for con in conns)


def test_reader_rejects_reference_mismatch_before_decoder(setup_reader, monkeypatch):
    job, root = setup_reader
    job.request.dataset.manifest_digest = "b" * 64
    decoded = []

    class Duck:
        @staticmethod
        def connect(*args, **kwargs):
            decoded.append(True)
            return FakeConnection([])

    monkeypatch.setattr(reader, "duckdb", Duck)
    with pytest.raises(DatasetRejected):
        with reader.FixtureReader(job, root, 9999999999):
            pass
    assert decoded == []
    assert ("copy-close",) in Copy.events


def test_reader_refuses_unsupported_snapshot_profile_before_copy(setup_reader, monkeypatch):
    from quantmesh.research._fixture_handles import UnsupportedSnapshotProfile

    job, root = setup_reader

    def forbidden_copy(*_args):
        raise AssertionError("filesystem copy must not start on unsupported profile")

    monkeypatch.setattr(reader, "_Copy", forbidden_copy)
    monkeypatch.setattr(
        reader,
        "require_snapshot_profile",
        lambda: (_ for _ in ()).throw(UnsupportedSnapshotProfile("unsupported")),
    )
    with pytest.raises(UnsupportedSnapshotProfile):
        reader.FixtureReader(job, root, 9999999999).__enter__()


def test_duckdb_policy_is_locked_and_read_back_before_file_queries():
    expected = [
        1,
        "30.5 MiB",
        "",
        False,
        False,
        False,
        False,
        False,
        [],
        ["/proc/7/fd/9"],
        False,
        True,
    ]
    con = ConfigConnection(expected)
    fixture = object.__new__(reader.FixtureReader)
    fixture.deadline = 9999999999
    fixture._configure(con, "/proc/7/fd/9")
    statements = [sql for sql, _ in con.events]
    assert statements[:5] == [
        "SET temp_directory=''",
        "SET allowed_directories=[]",
        "SET allowed_paths=['/proc/7/fd/9']",
        "SET enable_external_access=false",
        "SET lock_configuration=true",
    ]
    assert statements[5].startswith("SELECT current_setting(")


def test_duckdb_policy_rejects_foreign_setting_value():
    callbacks = []

    class ForeignMeta(type):
        def __eq__(cls, other):
            callbacks.append(other)
            return False

    class ForeignList(list, metaclass=ForeignMeta):
        pass

    class ForeignString(str):
        def __eq__(self, other):
            callbacks.append("string")
            return False

    expected = [
        1,
        "30.5 MiB",
        "",
        False,
        False,
        False,
        False,
        False,
        [],
        ["/proc/7/fd/9"],
        False,
        True,
    ]
    fixture = object.__new__(reader.FixtureReader)
    fixture.deadline = 9999999999
    malformed = list(expected)
    malformed[9] = [ForeignString("/proc/7/fd/9")]
    for rows in (ForeignList(expected), malformed):
        con = ConfigConnection(expected)
        con.fetchmany = lambda count, rows=rows: [rows]
        with pytest.raises(DatasetRejected):
            fixture._configure(con, "/proc/7/fd/9")
    assert callbacks == []


def test_cached_dataset_access_rechecks_all_pins(setup_reader):
    job, root = setup_reader
    with pytest.raises(DatasetRejected):
        with reader.FixtureReader(job, root, 9999999999) as fixture:
            Copy.pin_value = {
                Path("manifest.json"): ("b" * 64, (0, 1, 2, 1, 2, 3, 4, 0, 1000, 1000))
            }
            fixture.dataset()
    assert Copy.events[-1] == ("copy-close",)


def test_normal_exit_repins_and_surfaces_changed_source(setup_reader):
    job, root = setup_reader
    with pytest.raises(DatasetRejected):
        with reader.FixtureReader(job, root, 9999999999):
            Copy.pin_value = {
                Path("manifest.json"): ("b" * 64, (0, 1, 2, 1, 2, 3, 4, 0, 1000, 1000))
            }
    assert Copy.events[-1] == ("copy-close",)


def test_consumer_exception_survives_repin_and_close_failures(setup_reader):
    job, root = setup_reader
    with pytest.raises(RuntimeError, match="consumer failure"):
        with reader.FixtureReader(job, root, 9999999999) as fixture:
            Copy.pin_value = {
                Path("manifest.json"): ("b" * 64, (0, 1, 2, 1, 2, 3, 4, 0, 1000, 1000))
            }

            calls = []

            def failed_exit(*_args):
                calls.append("close")
                raise OSError("close failure")

            fixture._copy.__exit__ = failed_exit
            raise RuntimeError("consumer failure")
    assert calls == ["close"]


def test_normal_close_failure_propagates_once_after_repin(setup_reader):
    job, root = setup_reader
    calls = []
    with pytest.raises(OSError, match="close failure"):
        with reader.FixtureReader(job, root, 9999999999) as fixture:

            def failed_exit(*_args):
                calls.append("close")
                raise OSError("close failure")

            fixture._copy.__exit__ = failed_exit
    assert calls == ["close"]


def test_read_bars_rejects_custom_timezone_without_invoking_it():
    from datetime import tzinfo

    calls = []

    class CustomZone(tzinfo):
        def utcoffset(self, dt):
            calls.append("offset")
            raise AssertionError("custom timezone callback must not run")

    fixture = object.__new__(reader.FixtureReader)
    fixture.deadline = 9999999999
    fixture._check_pin = lambda: None
    fixture._cache = {("1h", reader.Venue.MOOMOO, "AAA"): []}
    custom = datetime(2026, 1, 5, tzinfo=CustomZone())
    with pytest.raises(DatasetRejected):
        fixture.read_bars(interval="1h", venue=reader.Venue.MOOMOO, symbol="AAA", start=custom)
    assert calls == []


def test_read_bars_uses_utc_for_builtin_timezone_filters():
    instant = datetime(2026, 1, 5, tzinfo=UTC)
    bar = SimpleNamespace(timestamp=instant)
    fixture = object.__new__(reader.FixtureReader)
    fixture.deadline = 9999999999
    fixture._check_pin = lambda: None
    fixture._cache = {("1h", reader.Venue.MOOMOO, "AAA"): [bar]}
    equivalent = datetime(2026, 1, 5, 8, tzinfo=timezone(timedelta(hours=8)))
    assert fixture.read_bars(
        interval="1h", venue=reader.Venue.MOOMOO, symbol="AAA", start=equivalent
    ) == [bar]


def test_deadline_is_checked_at_chunk_boundaries(monkeypatch):
    fixture = object.__new__(reader.FixtureReader)
    fixture.deadline = 1.0
    monkeypatch.setattr(reader.time, "monotonic", lambda: 2.0)
    with pytest.raises(DatasetRejected):
        fixture._deadline()


def test_reader_decodes_every_coverage_series_through_bounded_chunks(monkeypatch):
    from quantmesh.research import _fixture_parquet_guard as guard

    stamp = int(datetime(2026, 1, 5, tzinfo=UTC).timestamp() * 1_000_000)
    coverage = [
        SimpleNamespace(
            interval="1h",
            venue=reader.Venue.MOOMOO,
            symbol=symbol,
            rows=1,
            start=datetime(2026, 1, 5, tzinfo=UTC),
            end=datetime(2026, 1, 5, tzinfo=UTC),
        )
        for symbol in ("AAA", "BBB")
    ]
    shards = [
        Path(f"1h/moomoo/{symbol}/2026-01-05/shard-0000.parquet") for symbol in ("AAA", "BBB")
    ]
    identities = (0, 1, 2, 1, 512, 3, 4, 0, 1000, 1000)
    pins = {Path("manifest.json"): ("m" * 64, identities)}
    pins.update({path: ("s" * 64, identities) for path in shards})
    calls = []

    @contextmanager
    def sealed(handles, path, deadline, *, limit):
        calls.append(("sealed", path.parts[-3], limit))
        yield SimpleNamespace(alias=f"/proc/4/fd/{path.parts[-3]}", sha256="s" * 64, size=512)

    class Connection:
        def __init__(self):
            self.last = ""
            self.data_read = False
            self.closed = False

        def execute(self, sql, params=None):
            self.last = sql
            calls.append(("query", sql))
            return self

        def fetchmany(self, count):
            if "current_setting" in self.last:
                # Each file connection is configured with its own alias.
                alias = self.alias
                return [
                    [1, "30.5 MiB", "", False, False, False, False, False, [], [alias], False, True]
                ]
            if self.last.startswith("DESCRIBE"):
                return [tuple(row) + ("YES", None, None, None) for row in guard._LOGICAL]
            if self.last.startswith("SELECT name,type"):
                return list(guard._PHYSICAL)
            if self.last.startswith("SELECT num_rows"):
                return [(1, 1, 1)]
            if "epoch_us(timestamp)" in self.last:
                if self.data_read:
                    return []
                self.data_read = True
                return [(stamp, 10.0, 11.0, 9.0, 10.5, 1.0, "equity", "USD")]
            raise AssertionError(self.last)

        def close(self):
            self.closed = True
            calls.append(("closed",))

    connections = []

    class Duck:
        @staticmethod
        def connect(*, config):
            assert type(config) is dict
            assert config == READER_CONFIG
            calls.append(("connect-config", dict(config)))
            con = Connection()
            connections.append(con)
            return con

    original_configure = reader.FixtureReader._configure
    fixture = object.__new__(reader.FixtureReader)
    fixture.deadline = 9999999999

    def configure(con, alias):
        con.alias = alias
        original_configure(fixture, con, alias)

    monkeypatch.setattr(reader, "duckdb", Duck)
    monkeypatch.setattr(reader, "sealed_shard", sealed)
    monkeypatch.setattr(reader.FixtureReader, "_configure", staticmethod(configure))
    fixture.root = Path("/fixture")
    fixture.deadline = 9999999999
    fixture._copy = SimpleNamespace(handles=object())
    fixture._manifest = SimpleNamespace(dataset="equities", coverage=coverage)
    fixture._pinned = pins
    fixture._cache = {}
    fixture._load_all()
    assert set(fixture._cache) == {
        ("1h", reader.Venue.MOOMOO, "AAA"),
        ("1h", reader.Venue.MOOMOO, "BBB"),
    }
    assert [call for call in calls if call[0] == "sealed"] == [
        ("sealed", "AAA", 256 * 1024 * 1024),
        ("sealed", "BBB", 256 * 1024 * 1024 - 512),
    ]
    assert len(connections) == 2 and all(connection.closed for connection in connections)
    for call_index, call in enumerate(calls):
        if call[0] == "connect-config":
            first_query = next(
                index for index in range(call_index + 1, len(calls)) if calls[index][0] == "query"
            )
            assert call_index < first_query
            describe = next(
                index
                for index in range(first_query + 1, len(calls))
                if calls[index][0] == "query" and calls[index][1].startswith("DESCRIBE")
            )
            required_policy = (
                "SET temp_directory=''",
                "SET allowed_directories=[]",
                "SET allowed_paths=",
                "SET enable_external_access=false",
                "SET lock_configuration=true",
            )
            applied = [
                item[1]
                for item in calls[call_index + 1 : describe]
                if item[0] == "query" and item[1].startswith("SET ")
            ]
            assert len(applied) == len(required_policy)
            assert all(
                actual.startswith(wanted) for actual, wanted in zip(applied, required_policy)
            )


def test_connection_closes_when_metadata_validation_fails(monkeypatch):
    class Broken:
        closed = False

        def execute(self, *_args):
            raise DatasetRejected("fixture_parquet_invalid")

        def close(self):
            self.closed = True

    connection = Broken()
    monkeypatch.setattr(reader, "duckdb", SimpleNamespace(connect=lambda *, config: connection))

    @contextmanager
    def sealed(*_args, **_kwargs):
        yield SimpleNamespace(alias="/proc/4/fd/9", sha256="s" * 64, size=512)

    monkeypatch.setattr(reader, "sealed_shard", sealed)
    fixture = object.__new__(reader.FixtureReader)
    fixture.root = Path("/fixture")
    fixture.deadline = 9999999999
    fixture._copy = SimpleNamespace(handles=object())
    fixture._manifest = SimpleNamespace(
        dataset="equities",
        coverage=[SimpleNamespace(interval="1h", venue=reader.Venue.MOOMOO, symbol="AAA", rows=1)],
    )
    fixture._pinned = {
        Path("1h/moomoo/AAA/2026-01-05/shard-0000.parquet"): (
            "s" * 64,
            (0, 1, 2, 1, 512, 3, 4, 0, 1000, 1000),
        )
    }
    fixture._cache = {}
    with pytest.raises(DatasetRejected):
        fixture._load_all()
    assert connection.closed


def test_oversized_footer_is_rejected_before_rows_are_converted(monkeypatch):
    from quantmesh.research import _fixture_parquet_guard as guard

    class FooterConnection:
        closed = False

        def execute(self, sql, _params=None):
            self.sql = sql
            return self

        def fetchmany(self, _count):
            if self.sql.startswith("DESCRIBE"):
                return list(guard._LOGICAL)
            if self.sql.startswith("SELECT name,type"):
                return list(guard._PHYSICAL)
            if self.sql.startswith("SELECT num_rows"):
                return [(2, 1, 1)]
            raise AssertionError("row decoding must follow the footer budget gate")

        def close(self):
            self.closed = True

    con = FooterConnection()
    monkeypatch.setattr(reader, "duckdb", SimpleNamespace(connect=lambda *, config: con))
    monkeypatch.setattr(reader.FixtureReader, "_configure", staticmethod(lambda *_: None))

    @contextmanager
    def sealed(*_args, **_kwargs):
        yield SimpleNamespace(alias="/proc/4/fd/9", sha256="s" * 64, size=512)

    monkeypatch.setattr(reader, "sealed_shard", sealed)
    converted = []
    monkeypatch.setattr(reader, "rows_to_bars", lambda *args, **kwargs: converted.append(True))
    fixture = object.__new__(reader.FixtureReader)
    fixture.root = Path("/fixture")
    fixture.deadline = 9999999999
    fixture._copy = SimpleNamespace(handles=object())
    fixture._manifest = SimpleNamespace(
        dataset="equities",
        coverage=[SimpleNamespace(interval="1h", venue=reader.Venue.MOOMOO, symbol="AAA", rows=1)],
    )
    fixture._pinned = {
        Path("1h/moomoo/AAA/2026-01-05/shard-0000.parquet"): (
            "s" * 64,
            (0, 1, 2, 1, 512, 3, 4, 0, 1000, 1000),
        )
    }
    fixture._cache = {}
    with pytest.raises(DatasetRejected):
        fixture._load_all()
    assert not converted
    assert con.closed


def _chunk_reader(monkeypatch, rows, footer_count, declared_count, *, sealed_hash="s" * 64):
    from quantmesh.research import _fixture_parquet_guard as guard

    class Connection:
        closed = False

        def execute(self, sql, _params=None):
            self.sql = sql
            return self

        def fetchmany(self, _count):
            if self.sql.startswith("DESCRIBE"):
                return [tuple(row) + ("YES", None, None, None) for row in guard._LOGICAL]
            if self.sql.startswith("SELECT name,type"):
                return list(guard._PHYSICAL)
            if self.sql.startswith("SELECT num_rows"):
                return [(footer_count, 1, 1)]
            if "epoch_us(timestamp)" in self.sql:
                if self.sent:
                    return []
                self.sent = True
                return rows
            raise AssertionError(self.sql)

        def close(self):
            self.closed = True

    con = Connection()
    con.sent = False
    monkeypatch.setattr(reader, "duckdb", SimpleNamespace(connect=lambda *, config: con))
    monkeypatch.setattr(reader.FixtureReader, "_configure", staticmethod(lambda *_: None))

    @contextmanager
    def sealed(*_args, **_kwargs):
        yield SimpleNamespace(alias="/proc/4/fd/9", sha256=sealed_hash, size=512)

    monkeypatch.setattr(reader, "sealed_shard", sealed)
    start = datetime(2026, 1, 5, tzinfo=UTC)
    fixture = object.__new__(reader.FixtureReader)
    fixture.root = Path("/fixture")
    fixture.deadline = 9999999999
    fixture._copy = SimpleNamespace(handles=object())
    fixture._manifest = SimpleNamespace(
        dataset="equities",
        coverage=[
            SimpleNamespace(
                interval="1h",
                venue=reader.Venue.MOOMOO,
                symbol="AAA",
                rows=declared_count,
                start=start,
                end=start + timedelta(hours=declared_count - 1),
            )
        ],
    )
    fixture._pinned = {
        Path("1h/moomoo/AAA/2026-01-05/shard-0000.parquet"): (
            "s" * 64,
            (0, 1, 2, 1, 512, 3, 4, 0, 1000, 1000),
        )
    }
    fixture._cache = {}
    return fixture, con


def test_chunk_overrun_and_short_decode_refuse_and_close(monkeypatch):
    valid = (
        int(datetime(2026, 1, 5, tzinfo=UTC).timestamp() * 1_000_000),
        10.0,
        11.0,
        9.0,
        10.5,
        1.0,
        "equity",
        "USD",
    )
    for rows, footer, declared in (([valid, valid], 1, 1), ([], 1, 1)):
        fixture, con = _chunk_reader(monkeypatch, rows, footer, declared)
        with pytest.raises(DatasetRejected):
            fixture._load_all()
        assert con.closed


def test_late_invalid_row_and_sealed_hash_change_refuse(monkeypatch):
    stamp = int(datetime(2026, 1, 5, tzinfo=UTC).timestamp() * 1_000_000)
    valid = (stamp, 10.0, 11.0, 9.0, 10.5, 1.0, "equity", "USD")
    late_bad = ("invalid timestamp", 10.0, 11.0, 9.0, 10.5, 1.0, "equity", "USD")
    fixture, con = _chunk_reader(monkeypatch, [valid, late_bad], 2, 2)
    with pytest.raises(DatasetRejected):
        fixture._load_all()
    assert con.closed

    fixture, con = _chunk_reader(monkeypatch, [valid], 1, 1, sealed_hash="x" * 64)
    with pytest.raises(DatasetRejected):
        fixture._load_all()
    assert not con.closed  # Hash mismatch is rejected before connection creation.


def test_cached_read_repins_without_opening_another_decoder(setup_reader, monkeypatch):
    job, root = setup_reader
    opened = []

    class Duck:
        @staticmethod
        def connect(*, config):
            opened.append(config)
            return FakeConnection([])

    monkeypatch.setattr(reader, "duckdb", Duck)
    timestamp = datetime(2026, 1, 5, tzinfo=UTC)
    bar = SimpleNamespace(timestamp=timestamp)

    def load_cache(self):
        connection = reader.duckdb.connect(config=dict(READER_CONFIG))
        connection.close()
        self._cache = {("1h", reader.Venue.MOOMOO, "AAA"): [bar]}

    monkeypatch.setattr(reader.FixtureReader, "_load_all", load_cache)
    with reader.FixtureReader(job, root, 9999999999) as fixture:
        opened_after_load = len(opened)
        fixture.pin()
        fixture.dataset()
        assert fixture.read_bars(interval="1h", venue=reader.Venue.MOOMOO, symbol="AAA") == [bar]
        assert len(opened) == opened_after_load
