"""Sparse complete-row lookup, without a new persistent data model."""

import hashlib
import json
import threading
from datetime import UTC, datetime, timedelta

import duckdb
import pytest
from test_live_buffer_batched_tail import RecordedConnection
from test_live_buffer_batched_tail import lake as lake

from quantmesh.live.buffer import _UPDATE_COLUMNS, LiveBuffer, _row_to_update


def sparse_view(connection):
    connection.execute("""CREATE VIEW market_updates AS SELECT i+1 local_seq,
      'hyperliquid' venue,
      CASE WHEN i%5=0 THEN 'ETH' ELSE 'BTC' END instrument,
      CASE WHEN i%31=0 THEN 'status' ELSE 'candle' END kind,'synthetic' provenance,
      TIMESTAMPTZ '2026-10-23 16:00:00+00'+i*INTERVAL '1 second' data_time,
      TIMESTAMPTZ '2026-10-23 16:00:00+00'+(i+i%5)*INTERVAL '1 second' received_at,
      i//2 AS "sequence",false sequence_gap,'complete' continuity,
      'owned-'||md5(i::VARCHAR) source_event_id,NULL::VARCHAR content_digest,
      NULL::VARCHAR snapshot_epoch,NULL::VARCHAR continuity_evidence_json,
      CASE WHEN i%31=0 THEN 'disconnected' ELSE NULL END state,
      CASE WHEN i%31=0 THEN repeat(md5(i::VARCHAR),256) ELSE NULL END state_note,
      CASE WHEN i%31=0 THEN '{}' ELSE
      json_object('open',100,'high',101,'low',99,'close',100,'interval','5m',
      'volume',42,'final',true,'padding',repeat(md5(i::VARCHAR),256)) END payload_json
      FROM range(16000) r(i)""")


def oracle_row(key):
    index = key - 1
    token = hashlib.md5(str(index).encode(), usedforsecurity=False).hexdigest()
    status = index % 31 == 0
    payload = (
        {}
        if status
        else {
            "open": 100,
            "high": 101,
            "low": 99,
            "close": 100,
            "interval": "5m",
            "volume": 42,
            "final": True,
            "padding": token * 256,
        }
    )
    start = datetime(2026, 10, 23, 16, tzinfo=UTC)
    return (
        key,
        "hyperliquid",
        "ETH" if index % 5 == 0 else "BTC",
        "status" if status else "candle",
        "synthetic",
        start + timedelta(seconds=index),
        start + timedelta(seconds=index + index % 5),
        index // 2,
        False,
        "complete",
        "owned-" + token,
        None,
        None,
        None,
        "disconnected" if status else None,
        token * 256 if status else None,
        json.dumps(payload, separators=(",", ":")),
    )


class Trace:
    def __init__(self, connection):
        self.connection = connection
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if params is None:
            self.connection.execute(query)
        else:
            self.connection.execute(query, params)
        return self

    def __getattr__(self, name):
        return getattr(self.connection, name)


def operators(plan):
    return {n["name"] for n in plan} | {op for n in plan for op in operators(n.get("children", []))}


def test_sparse_default_tail_complete_raw_rows_avoid_in_materialization():
    # This declared20MiB generated model is deliberately tighter than128MiB
    # production. It is not the native POSIX archive or the failed C++ operator.
    connection = duckdb.connect(
        ":memory:",
        config={
            "memory_limit": "20MiB",
            "threads": 1,
            "max_temp_directory_size": "0B",
        },
    )
    sparse_view(connection)
    keys = [index + 1 for index in range(16000) if index % 5 != 0][-10000:]
    first = keys[:128]
    frozen = (
        f"SELECT {_UPDATE_COLUMNS} FROM market_updates WHERE local_seq IN ("
        + ",".join("?" for _ in first)
        + ")"
    )
    old_plan = json.loads(
        connection.execute(
            "EXPLAIN (FORMAT JSON) " + frozen,
            first,
        ).fetchone()[1]
    )
    assert "HASH_JOIN" in operators(old_plan)
    with pytest.raises(duckdb.OutOfMemoryException):
        connection.execute(frozen, first).fetchall()
    trace = Trace(connection)
    lake = LiveBuffer.__new__(LiveBuffer)
    lake._con = trace
    lake._connection_lock = threading.RLock()
    lake.read_unavailable = False
    key_query = (
        "SELECT local_seq FROM market_updates WHERE instrument='BTC' "
        "QUALIFY ROW_NUMBER() OVER (ORDER BY local_seq DESC) <= ?"
    )
    try:
        with lake._connection_lock:
            rows = lake._tail_rows(key_query, [10000])
        assert len(rows) == 10000
        assert [row[0] for row in rows] == keys
        for row in rows:
            assert len(row) == 17
            assert row == oracle_row(row[0])
        payload_calls = [
            (q, p) for q, p in trace.calls if q.startswith(f"SELECT {_UPDATE_COLUMNS}")
        ]
        assert len(payload_calls) == 79
        assert len(trace.calls) == 84
        query, params = payload_calls[0]
        plan = json.loads(
            connection.execute(
                "EXPLAIN (FORMAT JSON) " + query,
                params,
            ).fetchone()[1]
        )
        assert "HASH_JOIN" not in operators(plan)
        assert all(0 < len(p[2:]) <= 128 for _, p in payload_calls)
        assert all(p[:2] == [min(p[2:]), max(p[2:])] for _, p in payload_calls)
    finally:
        connection.close()


@pytest.mark.parametrize("limit", [0, -1, 1, 137])
def test_sparse_payload_exact_keys_limits_and_public_decoding(limit):
    connection = duckdb.connect(
        ":memory:",
        config={
            "memory_limit": "128MiB",
            "threads": 1,
            "max_temp_directory_size": "0B",
        },
    )
    sparse_view(connection)
    lake = LiveBuffer.__new__(LiveBuffer)
    trace = Trace(connection)
    lake._con, lake._connection_lock = trace, threading.RLock()
    lake.read_unavailable = False
    try:
        result = lake.replay(instrument="BTC", kinds={"candle", "status"}, tail=True, limit=limit)
        keys = [i + 1 for i in range(16000) if i % 5 != 0][-limit:] if limit > 0 else []
        assert len(result) == len(keys)
        assert [row.source_event_id for row in result] == [oracle_row(k)[10] for k in keys]
        for query, params in trace.calls:
            if query.startswith(f"SELECT {_UPDATE_COLUMNS}"):
                assert " BETWEEN ? AND ? AND (" in query
                assert 0 < len(params[2:]) <= 128
                assert params[:2] == [min(params[2:]), max(params[2:])]
    finally:
        connection.close()


@pytest.mark.parametrize("caller_owned", [False, True])
def test_sparse_batches_keep_snapshot_and_transaction_owner(lake, caller_owned):
    value, connection = lake
    connection.execute("DELETE FROM market_updates WHERE local_seq%5=0")
    other = connection.cursor()
    if caller_owned:
        connection.execute("BEGIN TRANSACTION")
        connection.execute("UPDATE market_updates SET state_note='caller' WHERE local_seq=1")
    before = connection.execute("SELECT txid_current()").fetchone()[0]
    expected = [
        _row_to_update(row)
        for row in connection.execute(
            f"SELECT {_UPDATE_COLUMNS} FROM market_updates ORDER BY local_seq"
        ).fetchall()
    ]

    def mutate(rows, count):
        if count == 1:
            other.execute("DELETE FROM market_updates WHERE local_seq=299")
            other.execute("UPDATE market_updates SET source_event_id='changed' WHERE local_seq=298")
        return rows

    trace = RecordedConnection(connection, mutate=mutate)
    value._con = trace
    try:
        assert value.replay(tail=True, limit=10000) == expected
        assert trace.wide_count == 2
        if caller_owned:
            assert connection.execute("SELECT txid_current()").fetchone()[0] == before
            assert not any(
                sql in {"BEGIN TRANSACTION", "COMMIT", "ROLLBACK"} for sql, _ in trace.calls
            )
        else:
            assert other.execute("SELECT count(*) FROM market_updates").fetchone()[0] == 239
    finally:
        if caller_owned:
            connection.execute("ROLLBACK")
        other.close()
