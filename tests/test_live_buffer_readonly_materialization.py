"""Stored sparse payloads must not inflate a complete-row batch scan."""

import hashlib
import json
import os
import threading
from datetime import UTC, datetime

import duckdb
import pytest

from quantmesh.live.buffer import _SCHEMA, _UPDATE_COLUMNS, LiveBuffer


@pytest.fixture
def compressed_archive(tmp_path, monkeypatch):
    path = tmp_path / "updates.duckdb"
    connection = duckdb.connect(
        str(path),
        config={
            "memory_limit": "256MiB",
            "threads": 1,
            "max_temp_directory_size": "0B",
            "storage_compatibility_version": "v1.5.0",
        },
    )
    try:
        connection.execute(
            _SCHEMA.replace(
                "payload_json  VARCHAR NOT NULL",
                "payload_json  VARCHAR USING COMPRESSION zstd NOT NULL",
            )
        )
        for first in range(0, 1776, 32):
            connection.execute(f"""INSERT INTO market_updates SELECT i+1,'hyperliquid',
              CASE WHEN i%16=0 THEN 'BTC' ELSE 'OTHER' END,'candle','synthetic',
              TIMESTAMPTZ '2026-10-23 23:43:00+00',TIMESTAMPTZ '2026-10-23 23:44:00+00',
              i,false,'complete','owned-'||i::VARCHAR,NULL,NULL,NULL,NULL,NULL,
              json_object('open',100,'high',101,'low',99,'close',100,'volume',1,
              'interval','1m','padding',repeat(md5(i::VARCHAR),2048))
              FROM range({first},{min(first + 32, 1776)})r(i)""")
            connection.execute("CHECKPOINT")
    finally:
        connection.close()
    if os.name == "posix":
        home = tmp_path / "private-home"
        home.mkdir(mode=0o555)
        path.chmod(0o444)
        tmp_path.chmod(0o555)
        monkeypatch.setenv("HOME", str(home))
    return path


def expected_row(index):
    token = hashlib.md5(str(index).encode(), usedforsecurity=False).hexdigest()
    return (
        index + 1,
        "hyperliquid",
        "BTC",
        "candle",
        "synthetic",
        datetime(2026, 10, 23, 23, 43, tzinfo=UTC),
        datetime(2026, 10, 23, 23, 44, tzinfo=UTC),
        index,
        False,
        "complete",
        f"owned-{index}",
        None,
        None,
        None,
        None,
        None,
        json.dumps(
            {
                "open": 100,
                "high": 101,
                "low": 99,
                "close": 100,
                "volume": 1,
                "interval": "1m",
                "padding": token * 2048,
            },
            separators=(",", ":"),
        ),
    )


def test_sparse_complete_batch_avoids_unselected_wide_scan(compressed_archive):
    # Compression keeps the stored fixture small; the full sparse range expands
    # to111MiB. This is an engineering OOM discriminator, not a native I/O claim.
    with compressed_archive.open("rb") as source:
        before = hashlib.file_digest(source, "sha256").hexdigest()
    connection = duckdb.connect(
        str(compressed_archive),
        read_only=True,
        config={"memory_limit": "128MiB", "threads": 1, "max_temp_directory_size": "0B"},
    )
    connection.execute("SET TimeZone='UTC'")
    lake = LiveBuffer.__new__(LiveBuffer)
    lake._con = connection
    lake._connection_lock = threading.RLock()
    lake.read_unavailable = False
    try:
        with lake._connection_lock:
            rows = lake._tail_rows(
                "SELECT local_seq FROM market_updates WHERE venue='hyperliquid' "
                "AND instrument='BTC' AND kind IN ('candle','status') "
                "AND data_time BETWEEN TIMESTAMPTZ '2026-10-22 23:44:01+00' "
                "AND TIMESTAMPTZ '2026-10-23 23:44:01+00' "
                "AND received_at BETWEEN TIMESTAMPTZ '2026-10-22 23:44:01+00' "
                "AND TIMESTAMPTZ '2026-10-23 23:44:01+00' "
                "QUALIFY ROW_NUMBER() OVER (ORDER BY local_seq DESC)<=?",
                [10000],
            )
        assert len(rows) == 111
        for row, index in zip(rows, range(0, 1776, 16), strict=True):
            assert len(row) == 17
            assert row == expected_row(index)
    finally:
        connection.close()
    with compressed_archive.open("rb") as source:
        assert hashlib.file_digest(source, "sha256").hexdigest() == before


def test_normal_default_tail_keeps_all10000_rows_and128_key_statement_bound():
    connection = duckdb.connect(
        ":memory:",
        config={"memory_limit": "128MiB", "threads": 1, "max_temp_directory_size": "0B"},
    )
    connection.execute(_SCHEMA)
    connection.execute("""INSERT INTO market_updates SELECT i+1,'hyperliquid','BTC',
      CASE WHEN i%31=0 THEN 'status' ELSE 'candle' END,'synthetic',
      TIMESTAMPTZ '2026-10-23 16:00:00+00',TIMESTAMPTZ '2026-10-23 16:00:01+00',
      i,false,'complete','owned-'||i::VARCHAR,NULL,NULL,NULL,
      CASE WHEN i%31=0 THEN 'disconnected' ELSE NULL END,
      CASE WHEN i%31=0 THEN 'owned barrier '||i::VARCHAR ELSE NULL END,
      CASE WHEN i%31=0 THEN '{}' ELSE
      json_object('open',100,'high',101,'low',99,'close',100,'interval','1m') END
      FROM range(10037)r(i)""")
    expected = connection.execute(
        f"SELECT {_UPDATE_COLUMNS} FROM market_updates ORDER BY local_seq"
    ).fetchall()[-10000:]

    class Trace:
        def __init__(self):
            self.key_counts = []

        def execute(self, query, parameters=None):
            if query.startswith(f"SELECT {_UPDATE_COLUMNS}"):
                self.key_counts.append(len(parameters) // 3)
            connection.execute(query, parameters) if parameters is not None else connection.execute(
                query
            )
            return self

        def __getattr__(self, name):
            return getattr(connection, name)

    trace = Trace()
    lake = LiveBuffer.__new__(LiveBuffer)
    lake._con, lake._connection_lock = trace, threading.RLock()
    lake.read_unavailable = False
    try:
        with lake._connection_lock:
            actual = lake._tail_rows(
                "SELECT local_seq FROM market_updates WHERE venue='hyperliquid' "
                "AND instrument='BTC' AND kind IN ('candle','status') "
                "AND data_time BETWEEN TIMESTAMPTZ '2026-10-23 00:00:00+00' "
                "AND TIMESTAMPTZ '2026-10-24 00:00:00+00' "
                "AND received_at BETWEEN TIMESTAMPTZ '2026-10-23 00:00:00+00' "
                "AND TIMESTAMPTZ '2026-10-24 00:00:00+00' "
                "QUALIFY ROW_NUMBER() OVER (ORDER BY local_seq DESC)<=?",
                [10000],
            )
        assert actual == expected
        assert [row[0] for row in actual] == list(range(38, 10038))
        assert trace.key_counts == [128] * 78 + [16]
    finally:
        connection.close()
