"""Equivalent tail reads on small owned data, never the production archive."""

import json
from datetime import UTC, datetime, timedelta, timezone

import duckdb
import pytest

from quantmesh.live.buffer import _SCHEMA, _UPDATE_COLUMNS, LiveBuffer, _row_to_update
from quantmesh.live.contract import ContinuityEvidence, MarketUpdate

AS_OF = datetime(2026, 10, 24, 9, 52, 39, 402692, tzinfo=UTC)
START = AS_OF - timedelta(days=1)


def legacy_rows(connection, *, limit=1000, tail=True, **filters):
    """Frozen shipped SQL oracle; independent predicate construction."""
    clauses, params = [], []
    for column in ("venue", "instrument"):
        if filters.get(column) is not None:
            clauses.append(f"{column} = ?")
            params.append(filters[column])
    if filters.get("kinds"):
        kinds = sorted(filters["kinds"])
        clauses.append(f"kind IN ({','.join('?' for _ in kinds)})")
        params.extend(kinds)
    for name, column, comparison in (
        ("start", "received_at", ">="),
        ("end", "received_at", "<="),
        ("data_time_start", "data_time", ">="),
        ("data_time_end", "data_time", "<="),
        ("through_local_seq", "local_seq", "<="),
    ):
        if filters.get(name) is not None:
            clauses.append(f"{column} {comparison} ?")
            params.append(filters[name])
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    if tail:
        suffix = "QUALIFY ROW_NUMBER() OVER (ORDER BY local_seq DESC) <= ? ORDER BY local_seq"
    else:
        suffix = "ORDER BY local_seq LIMIT ?"
    return connection.execute(
        f"SELECT {_UPDATE_COLUMNS} FROM market_updates {where} {suffix}", [*params, limit]
    ).fetchall()


@pytest.fixture(scope="module")
def differential_archive(tmp_path_factory):
    root = tmp_path_factory.mktemp("tail-differential")
    evidence = ContinuityEvidence(
        channel="owned-candles",
        disconnected_at=START,
        first_recovered_source_event_id="owned-12",
        recovered_at=AS_OF,
        recovery_source="owned-test",
    )
    with LiveBuffer(root, retention_days=0) as lake:
        for index in range(24):
            kind = "status" if index % 4 == 0 else "candle"
            data_time = (
                START - timedelta(microseconds=1)
                if index == 20
                else AS_OF + timedelta(microseconds=1)
                if index == 21
                else START
                if index % 3 == 0
                else AS_OF
            )
            received = (
                START - timedelta(microseconds=1)
                if index == 22
                else AS_OF + timedelta(microseconds=1)
                if index == 23
                else AS_OF
                if index % 2
                else START
            )
            update = MarketUpdate(
                venue="hyperliquid" if index != 18 else "kalshi",
                instrument="BTC" if index != 19 else "ETH",
                kind=kind,
                provenance="synthetic",
                data_time=data_time,
                received_at=received,
                sequence=index // 2,  # Venue sequence/time ties are legal; local_seq is unique.
                continuity="recovered" if index == 12 else "complete",
                continuity_evidence=evidence if index == 12 else None,
                source_event_id=f"owned-{index}",
                state="disconnected" if kind == "status" else None,
                state_note=f"barrier-{index}" if kind == "status" else None,
                payload={}
                if kind == "status"
                else {
                    "open": 100 + index,
                    "high": 101 + index,
                    "low": 99 + index,
                    "close": 100 + index,
                    "interval": "5m",
                },
            )
            first = lake.append(update)
            assert lake.append(update) == first  # Same source identity is not another row.
        # Owned fixture only: sequence gaps need not indicate missing selected events.
        lake._con.execute("DELETE FROM market_updates WHERE local_seq IN (3,7)")
        with pytest.raises(duckdb.ConstraintException):
            lake._con.execute("INSERT INTO market_updates SELECT * FROM market_updates LIMIT 1")
    return root


FILTERS = [
    {},
    {"venue": "hyperliquid"},
    {"instrument": "BTC"},
    {"venue": "absent"},
    {"kinds": {"candle", "status"}},
    {"kinds": {"status"}},
    {"kinds": set()},
    {"start": START, "end": AS_OF},
    {"data_time_start": START, "data_time_end": AS_OF},
    {"through_local_seq": 14},
    {"start": AS_OF, "end": START},
    {
        "venue": "hyperliquid",
        "instrument": "BTC",
        "kinds": {"candle", "status"},
        "start": START.astimezone(timezone(timedelta(hours=8))),
        "end": AS_OF,
        "data_time_start": START,
        "data_time_end": AS_OF,
        "through_local_seq": 22,
    },
]


@pytest.mark.parametrize("filters", FILTERS)
@pytest.mark.parametrize("limit", [-2, 0, 1, 3, 1000, 10_000])
def test_tail_matches_all_legacy_fields_and_predicates(differential_archive, filters, limit):
    with LiveBuffer(differential_archive, read_only=True) as lake:
        raw = legacy_rows(lake._con, limit=limit, **filters)
        if filters == {"venue": "absent"}:
            assert lake._con.execute(
                "SELECT count(*) FROM market_updates WHERE venue='absent'"
            ).fetchone() == (0,)
            # DuckDB1.5.5's old window rewrite can produce one all-NULL row at
            # limit1 on a truly empty filtered relation. Membership must not
            # synthesize that row; this is not catching a read/query failure.
            assert raw == [] or raw == [(None,) * 17]
            expected = []
        else:
            expected = [_row_to_update(row) for row in raw]
        assert lake.replay(tail=True, limit=limit, **filters) == expected
        if limit >= 0:
            forward = [
                _row_to_update(row)
                for row in legacy_rows(lake._con, tail=False, limit=limit, **filters)
            ]
            assert lake.replay(tail=False, limit=limit, **filters) == forward


def test_tail_status_barrier_and_gap_are_not_trimmed_before_limit(differential_archive):
    with LiveBuffer(differential_archive, read_only=True) as lake:
        rows = lake.replay(
            tail=True,
            limit=5,
            venue="hyperliquid",
            instrument="BTC",
            kinds={"candle", "status"},
            start=START,
            end=AS_OF,
            data_time_start=START,
            data_time_end=AS_OF,
            through_local_seq=14,
        )
        assert [row.source_event_id for row in rows] == [f"owned-{i}" for i in range(9, 14)]
        assert rows[3].kind == "status"
        assert rows[3].state == "disconnected"
        assert rows[3].continuity == "recovered"
        assert rows[3].sequence_gap
        assert rows[3].continuity_evidence.recovery_source == "owned-test"
        with pytest.raises(ValueError, match="positive"):
            lake.replay(tail=True, through_local_seq=0)


def test_selected_corruption_still_raises_and_excluded_corruption_is_not_decoded(tmp_path):
    with LiveBuffer(tmp_path, retention_days=0) as lake:
        for index in range(3):
            lake.append(
                MarketUpdate(
                    venue="hyperliquid",
                    instrument="BTC",
                    kind="quote",
                    provenance="synthetic",
                    data_time=AS_OF,
                    received_at=AS_OF,
                    sequence=index,
                    payload={"bid": 100, "ask": 101},
                )
            )
        lake._con.execute("UPDATE market_updates SET payload_json='broken' WHERE local_seq=3")
        assert len(lake.replay(tail=True, through_local_seq=2)) == 2
        with pytest.raises(json.JSONDecodeError):
            lake.replay(tail=True, limit=1)


def test_owned_default_tail_under_tighter_memory_without_sql_payload_sort(tmp_path):
    """A scaled memory model, not an RSS bound or native 7GB archive proof."""
    path = tmp_path / "live" / "updates.duckdb"
    path.parent.mkdir()
    with duckdb.connect(str(path)) as connection:
        connection.execute(_SCHEMA)
        connection.execute(
            "INSERT INTO market_updates SELECT i,'hyperliquid','BTC',"
            "CASE WHEN i%13=0 THEN 'status' ELSE 'candle' END,'synthetic',"
            "TIMESTAMPTZ '2026-10-24 09:00:00Z',TIMESTAMPTZ '2026-10-24 09:00:00Z',"
            "i,false,'complete','owned:'||i,NULL,NULL,NULL,"
            "CASE WHEN i%13=0 THEN 'disconnected' END,NULL,"
            "CASE WHEN i%13=0 THEN '{}' ELSE json_object("
            "'open',100,'high',101,'low',99,'close',100,'interval','5m',"
            "'padding',repeat(md5(i::VARCHAR),16)) END "
            "FROM range(1,60001)t(i)"
        )
    before = path.read_bytes(), path.stat().st_mtime_ns
    filters = dict(
        venue="hyperliquid",
        instrument="BTC",
        kinds={"candle", "status"},
        start=START,
        end=AS_OF,
        data_time_start=START,
        data_time_end=AS_OF,
    )
    # Oracle equivalence at the unchanged production SQL setting, not only counts.
    with LiveBuffer(tmp_path, read_only=True) as lake:
        oracle = [_row_to_update(row) for row in legacy_rows(lake._con, limit=10_000, **filters)]
    # The weaker historical SQL sometimes fits 16MiB, so its OOM is not a
    # reliable gate. The larger, width-checked negative model is in
    # test_live_buffer_batched_tail.py; this model checks the positive reader.
    with LiveBuffer(tmp_path, read_only=True) as lake:
        lake._con.execute("SET memory_limit='16MiB'")  # Test-only, never runtime.
        assert lake._con.execute("SELECT current_setting('threads')").fetchone()[0] == 1
        assert (
            lake._con.execute("SELECT current_setting('max_temp_directory_size')").fetchone()[0]
            == "0 bytes"
        )
        rows = lake.replay(tail=True, limit=10_000, **filters)
        assert rows == oracle
        assert len(rows) == 10_000
        assert rows[0].sequence == 50_001 and rows[-1].sequence == 60_000
        assert any(row.kind == "status" for row in rows)
        assert len(lake.replay(tail=True, **filters)) == 1000  # Existing API default.
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert not path.with_suffix(".duckdb.wal").exists()
    assert not list(path.parent.glob("*.tmp"))
