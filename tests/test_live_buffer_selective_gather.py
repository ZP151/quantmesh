"""Complete-row acquisition must bound work as well as selected-row memory."""

import hashlib
import json
import os
import threading
from datetime import UTC, datetime

import duckdb
import pytest

from quantmesh.live.buffer import _SCHEMA, _UPDATE_COLUMNS, LiveBuffer

N = 1048576
STRIDE = 8192


def key_query():
    return (
        "SELECT local_seq FROM market_updates WHERE venue='hyperliquid' "
        "AND instrument='BTC' AND kind IN ('candle','status') "
        "AND data_time BETWEEN TIMESTAMPTZ '2026-10-22 23:44:01+00' "
        "AND TIMESTAMPTZ '2026-10-23 23:44:01+00' "
        "AND received_at BETWEEN TIMESTAMPTZ '2026-10-22 23:44:01+00' "
        "AND TIMESTAMPTZ '2026-10-23 23:44:01+00' "
        "QUALIFY ROW_NUMBER() OVER(ORDER BY local_seq DESC)<=?"
    )


@pytest.fixture
def selective_archive(tmp_path):
    path = tmp_path / "selective.duckdb"
    with duckdb.connect(
        str(path),
        config={"memory_limit": "128MiB", "threads": 1, "max_temp_directory_size": "0B"},
    ) as connection:
        connection.execute(f"""CREATE VIEW market_updates AS SELECT i+1 local_seq,
          'hyperliquid' venue,CASE WHEN i%{STRIDE}=0 THEN 'BTC' ELSE 'OTHER' END instrument,
          CASE WHEN i%31=0 THEN 'status' ELSE 'candle' END kind,'synthetic' provenance,
          TIMESTAMPTZ '2026-10-23 23:43:00+00' data_time,
          TIMESTAMPTZ '2026-10-23 23:44:00+00' received_at,i AS sequence,
          false sequence_gap,'complete' continuity,'owned-'||i::VARCHAR source_event_id,
          NULL::VARCHAR content_digest,NULL::VARCHAR snapshot_epoch,
          NULL::VARCHAR continuity_evidence_json,
          CASE WHEN i%31=0 THEN 'disconnected' ELSE NULL END state,
          CASE WHEN i%31=0 THEN 'owned-'||i::VARCHAR ELSE NULL END state_note,
          CASE WHEN i%31=0 THEN '{{}}' ELSE
          '{{"open":100,"high":101,"low":99,"close":100,"interval":"1m","volume":1}}'
          END payload_json FROM range({N})r(i)""")
        connection.execute("CHECKPOINT")
    if os.name == "posix":
        path.chmod(0o444)
        tmp_path.chmod(0o555)
    return path


def expected_row(index):
    status = index % 31 == 0
    return (
        index + 1,
        "hyperliquid",
        "BTC",
        "status" if status else "candle",
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
        "disconnected" if status else None,
        f"owned-{index}" if status else None,
        "{}"
        if status
        else '{"open":100,"high":101,"low":99,"close":100,"interval":"1m","volume":1}',
    )


class Trace:
    def __init__(self, connection):
        self.connection = connection
        self.payload_calls = []

    def execute(self, query, parameters=None):
        if query.startswith(f"SELECT {_UPDATE_COLUMNS}"):
            self.payload_calls.append((query, parameters))
        if parameters is None:
            self.connection.execute(query)
        else:
            self.connection.execute(query, parameters)
        return self

    def __getattr__(self, name):
        return getattr(self.connection, name)


def nodes(node):
    yield node
    for child in node.get("children", []):
        yield from nodes(child)


def test_sparse_acquisition_does_not_scan_source_once_per_selected_key(selective_archive):
    before = hashlib.sha256(selective_archive.read_bytes()).hexdigest()
    connection = duckdb.connect(
        str(selective_archive),
        read_only=True,
        config={"memory_limit": "128MiB", "threads": 1, "max_temp_directory_size": "0B"},
    )
    connection.execute("SET TimeZone='UTC'")
    trace = Trace(connection)
    lake = LiveBuffer.__new__(LiveBuffer)
    lake._con, lake._connection_lock = trace, threading.RLock()
    lake.read_unavailable = False
    try:
        with lake._connection_lock:
            rows = lake._tail_rows(key_query(), [10000])
        assert rows == [expected_row(i) for i in range(0, N, STRIDE)]
        # Measure actual source work rather than assert a SQL spelling or time.
        scanned = 0
        for query, parameters in trace.payload_calls:
            profile = json.loads(
                connection.execute(
                    "EXPLAIN (ANALYZE, FORMAT JSON) " + query, parameters
                ).fetchone()[1]
            )
            scanned += sum(
                node.get("operator_rows_scanned", 0)
                for node in nodes(profile)
                if node.get("extra_info", {}).get("Function") == "RANGE"
            )
        assert scanned > 0  # A missing profiler field must not make this pass.
        assert scanned <= 4 * N
        assert len(trace.payload_calls) == 4
    finally:
        connection.close()
    assert hashlib.sha256(selective_archive.read_bytes()).hexdigest() == before


@pytest.fixture
def wide_archive(tmp_path):
    path = tmp_path / "wide.duckdb"
    with duckdb.connect(
        str(path),
        config={
            "memory_limit": "128MiB",
            "threads": 1,
            "max_temp_directory_size": "0B",
            "storage_compatibility_version": "v1.5.0",
        },
    ) as connection:
        connection.execute(
            _SCHEMA.replace(
                "payload_json  VARCHAR NOT NULL",
                "payload_json  VARCHAR USING COMPRESSION zstd NOT NULL",
            )
        )
        print("OWNED_WIDE_BUILD_ENTER rows=8192 selected=128", flush=True)
        for first in range(0, 8192, 128):
            connection.execute("BEGIN TRANSACTION")
            for chunk in range(first, first + 128, 32):
                connection.execute(f"""INSERT INTO market_updates SELECT i+1,'hyperliquid',
              CASE WHEN i%64=0 THEN 'BTC' ELSE 'OTHER' END,
              CASE WHEN i%31=0 THEN 'status' ELSE 'candle' END,'synthetic',
              TIMESTAMPTZ '2026-10-23 23:43:00+00',TIMESTAMPTZ '2026-10-23 23:44:00+00',
              i,false,'complete','owned-'||i::VARCHAR,NULL,NULL,NULL,
              CASE WHEN i%31=0 THEN 'disconnected' ELSE NULL END,
              CASE WHEN i%31=0 THEN 'owned-'||i::VARCHAR ELSE NULL END,
              CASE WHEN i%31=0 THEN '{{}}' ELSE
              json_object('open',100,'high',101,'low',99,'close',100,'interval','1m',
              'volume',1,'padding',repeat(md5(i::VARCHAR),2048)) END
              FROM range({chunk},{chunk + 32})r(i)""")
            connection.execute("COMMIT")
            connection.execute("CHECKPOINT")
            if (first + 128) % 1024 == 0:
                print(f"OWNED_WIDE_BUILD_ROWS {first + 128}", flush=True)
        print("OWNED_WIDE_BUILD_COMPLETE", flush=True)
    if os.name == "posix":
        path.chmod(0o444)
        tmp_path.chmod(0o555)
    return path


def test_selective_gather_retains_wide_unmatched_row_memory_protection(wide_archive):
    before = hashlib.sha256(wide_archive.read_bytes()).hexdigest()
    connection = duckdb.connect(
        str(wide_archive),
        read_only=True,
        config={"memory_limit": "128MiB", "threads": 1, "max_temp_directory_size": "0B"},
    )
    connection.execute("SET TimeZone='UTC'")
    lake = LiveBuffer.__new__(LiveBuffer)
    lake._con, lake._connection_lock = connection, threading.RLock()
    lake.read_unavailable = False
    try:
        print("OWNED_WIDE_QUERY_ENTER", flush=True)
        with lake._connection_lock:
            rows = lake._tail_rows(key_query(), [10000])
        print(f"OWNED_WIDE_QUERY_RETURN rows={len(rows)}", flush=True)
        assert len(rows) == 128
        for row, index in zip(rows, range(0, 8192, 64), strict=True):
            expected = list(expected_row(index))
            if index % 31 != 0:
                payload = json.loads(expected[-1])
                token = hashlib.md5(str(index).encode(), usedforsecurity=False).hexdigest()
                payload["padding"] = token * 2048
                expected[-1] = json.dumps(payload, separators=(",", ":"))
            assert len(row) == 17
            assert row == tuple(expected)
    finally:
        connection.close()
    assert hashlib.sha256(wide_archive.read_bytes()).hexdigest() == before
