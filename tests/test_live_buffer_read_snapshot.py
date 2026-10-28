"""Read snapshots must preserve results without emitting accepted-write commits."""

import hashlib

import duckdb
import pytest

from quantmesh.live.buffer import LiveBuffer, _row_to_update
from tests.test_live_buffer_latest_bootstrap import Observe, raw_row, stored


class Statements(Observe):
    """Observe actual SQL; do not replace transaction or query execution."""

    def __init__(self, connection, *, close_fault=None):
        super().__init__(connection)
        self.calls = []
        self.close_fault = close_fault

    def execute(self, query, params=None):
        self.calls.append(query)
        if query == "ROLLBACK" and self.close_fault is not None:
            fault, self.close_fault = self.close_fault, None
            raise fault
        return super().execute(query, params)


@pytest.fixture
def snapshot_rows():
    rows = [raw_row(i + 1, symbol=f"S{i}", identity=f"event-{i}") for i in range(300)]
    return [(*row[:11], _row_to_update(row).content_digest, *row[12:]) for row in rows]


def read(lake, method):
    return lake.latest() if method == "latest" else lake.replay(tail=True, limit=300)


@pytest.mark.parametrize("method", ["latest", "tail"])
@pytest.mark.parametrize("empty", [False, True])
@pytest.mark.parametrize("read_only", [False, True])
def test_owned_read_has_no_write_commit_and_preserves_complete_results(
    tmp_path, snapshot_rows, method, empty, read_only
):
    path = stored(tmp_path, snapshot_rows)
    if empty:
        with duckdb.connect(str(path)) as connection:
            connection.execute("DELETE FROM market_updates")
            connection.execute("CHECKPOINT")
    before = hashlib.sha256(path.read_bytes()).hexdigest() if read_only else None
    with LiveBuffer(tmp_path, read_only=read_only, retention_days=0) as lake:
        connection = lake._con
        recorder = Statements(connection)
        lake._con = recorder
        expected = [] if empty else [_row_to_update(row) for row in snapshot_rows]
        assert read(lake, method) == expected
        assert "COMMIT" not in recorder.calls
        assert recorder.calls.count("ROLLBACK") == 1
        # Both public callers supply read statements throughout their owned snapshot.
        assert all(
            sql.startswith("SELECT ") or sql in {"BEGIN TRANSACTION", "ROLLBACK"}
            for sql in recorder.calls
        )
        # Successful closure leaves no hidden transaction or pending writes.
        connection.execute("BEGIN TRANSACTION")
        connection.execute("ROLLBACK")
    if read_only:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("method", ["latest", "tail"])
@pytest.mark.parametrize("finish", ["COMMIT", "ROLLBACK"])
def test_caller_alone_decides_whether_pending_writes_are_committed(
    tmp_path, snapshot_rows, method, finish
):
    path = stored(tmp_path, snapshot_rows)
    with LiveBuffer(tmp_path, retention_days=0) as lake, duckdb.connect(str(path)) as other:
        connection = lake._con
        connection.execute("BEGIN TRANSACTION")
        connection.execute("UPDATE market_updates SET source_event_id='pending' WHERE local_seq=1")
        transaction = connection.execute("SELECT txid_current()").fetchone()[0]
        recorder = Statements(connection)
        lake._con = recorder
        changed = [(*snapshot_rows[0][:10], "pending", *snapshot_rows[0][11:]), *snapshot_rows[1:]]
        assert read(lake, method) == [_row_to_update(row) for row in changed]
        assert not any(sql in {"BEGIN TRANSACTION", "COMMIT", "ROLLBACK"} for sql in recorder.calls)
        assert connection.execute("SELECT txid_current()").fetchone()[0] == transaction
        query = "SELECT source_event_id FROM market_updates WHERE local_seq=1"
        assert other.execute(query).fetchone()[0] == "event-0"
        connection.execute(finish)
        assert other.execute(query).fetchone()[0] == (
            "pending" if finish == "COMMIT" else "event-0"
        )


@pytest.mark.parametrize("method", ["latest", "tail"])
@pytest.mark.parametrize("failure", [duckdb.IOException, KeyboardInterrupt])
def test_owned_snapshot_close_failure_never_returns_partial_success(
    tmp_path, snapshot_rows, method, failure
):
    stored(tmp_path, snapshot_rows)
    with LiveBuffer(tmp_path, read_only=True) as lake:
        connection = lake._con
        recorder = Statements(connection, close_fault=failure("owned snapshot close refusal"))
        lake._con = recorder
        with pytest.raises(failure, match="owned snapshot close refusal"):
            read(lake, method)
        assert "COMMIT" not in recorder.calls
        # A one-shot close failure is retried by existing owned exception cleanup.
        # The original error/cancellation remains visible; gathered rows are not returned.
        connection.execute("BEGIN TRANSACTION")
        connection.execute("ROLLBACK")
