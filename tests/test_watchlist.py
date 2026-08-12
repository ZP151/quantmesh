"""Watchlist store discipline (M9, issue #52, Phase B).

The watchlist is the one UI-owned write surface in the workstation, stored as
JSONL on the ADR-0006 discipline: atomic temp+replace appends, fail-closed reads
with line attribution, duplicate venue/symbol refusal, legacy symbol-only
compatibility, and root-not-dir refusal. Reading a missing store is an empty
list, never an error.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from quantmesh.api.watchlist import (
    WATCHLIST_FILE,
    WatchlistError,
    WatchlistRecord,
    WatchlistStore,
)
from quantmesh.domain.models import Venue

NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)


def store(tmp_path) -> WatchlistStore:
    return WatchlistStore(root=tmp_path / "watchlists")


class TestWatchlistRecord:
    def test_shape(self) -> None:
        record = WatchlistRecord(symbol="BTC", venue=Venue.HYPERLIQUID, added_at=NOW)
        assert record.symbol == "BTC"
        assert record.venue is Venue.HYPERLIQUID
        assert record.added_at == NOW

    def test_symbol_stripped_and_refused_when_empty(self) -> None:
        assert WatchlistRecord(symbol="  BTC  ", added_at=NOW).symbol == "BTC"
        for bad in ("", "   "):
            with pytest.raises(ValidationError):
                WatchlistRecord(symbol=bad, added_at=NOW)

    def test_symbol_refuses_whitespace(self) -> None:
        with pytest.raises(ValidationError, match="whitespace"):
            WatchlistRecord(symbol="BTC USD", added_at=NOW)

    def test_added_at_must_be_aware(self) -> None:
        with pytest.raises(ValidationError, match="timezone"):
            WatchlistRecord(symbol="BTC", added_at=datetime(2026, 8, 8, 12, 0))

    def test_extra_fields_refused(self) -> None:
        with pytest.raises(ValidationError):
            WatchlistRecord(symbol="BTC", added_at=NOW, unexpected=True)


class TestWatchlistStore:
    def test_missing_store_reads_empty(self, tmp_path) -> None:
        assert store(tmp_path).all() == []

    def test_add_remove_round_trip(self, tmp_path) -> None:
        watched = store(tmp_path)
        record = watched.add("BTC", now=NOW)
        assert record.symbol == "BTC"
        assert [item.symbol for item in watched.all()] == ["BTC"]
        watched.remove("BTC")
        assert watched.all() == []

    def test_duplicate_refused(self, tmp_path) -> None:
        watched = store(tmp_path)
        watched.add("BTC", now=NOW)
        with pytest.raises(WatchlistError, match="already on the watchlist"):
            watched.add("BTC", now=NOW)

    def test_same_symbol_on_two_venues_has_two_exact_identities(self, tmp_path) -> None:
        watched = store(tmp_path)
        watched.add("BTC-USD", venue=Venue.HYPERLIQUID, now=NOW)
        watched.add("BTC-USD", venue=Venue.MOOMOO, now=NOW)

        assert [(item.venue, item.symbol) for item in watched.all()] == [
            (Venue.HYPERLIQUID, "BTC-USD"),
            (Venue.MOOMOO, "BTC-USD"),
        ]
        with pytest.raises(WatchlistError, match="already on the watchlist"):
            watched.add("BTC-USD", venue=Venue.MOOMOO, now=NOW)
        with pytest.raises(WatchlistError, match="ambiguous"):
            watched.remove("BTC-USD")
        watched.remove("BTC-USD", venue=Venue.MOOMOO)
        assert [(item.venue, item.symbol) for item in watched.all()] == [
            (Venue.HYPERLIQUID, "BTC-USD")
        ]

    def test_remove_unknown_refused(self, tmp_path) -> None:
        watched = store(tmp_path)
        watched.add("BTC", now=NOW)
        with pytest.raises(WatchlistError, match="not on the watchlist"):
            watched.remove("ETH")

    def test_malformed_symbol_refused_and_nothing_written(self, tmp_path) -> None:
        watched = store(tmp_path)
        with pytest.raises(WatchlistError):
            watched.add("  ", now=NOW)
        assert watched.all() == []
        assert not (tmp_path / "watchlists" / WATCHLIST_FILE).exists()

    def test_order_preserved(self, tmp_path) -> None:
        watched = store(tmp_path)
        watched.add("BTC", now=NOW)
        watched.add("ETH", now=NOW)
        watched.add("AAPL", now=NOW)
        assert [item.symbol for item in watched.all()] == ["BTC", "ETH", "AAPL"]

    def test_cross_instance_persistence(self, tmp_path) -> None:
        first = store(tmp_path)
        first.add("BTC", now=NOW)
        second = store(tmp_path)
        assert [item.symbol for item in second.all()] == ["BTC"]

    def test_root_not_a_directory_refused(self, tmp_path) -> None:
        file_root = tmp_path / "not-a-dir"
        file_root.write_text("x", encoding="utf-8")
        watched = WatchlistStore(root=file_root)
        with pytest.raises(WatchlistError, match="not a directory"):
            watched.all()
        with pytest.raises(WatchlistError, match="not a directory"):
            watched.add("BTC", now=NOW)

    def test_unreadable_file_refused(self, tmp_path) -> None:
        watched = store(tmp_path)
        watched.add("BTC", now=NOW)
        (tmp_path / "watchlists" / WATCHLIST_FILE).write_bytes(b"\xff\xfe")
        with pytest.raises(WatchlistError, match="unreadable"):
            watched.all()

    def test_corrupt_line_refused_with_attribution(self, tmp_path) -> None:
        watched = store(tmp_path)
        watched.add("BTC", now=NOW)
        path = tmp_path / "watchlists" / WATCHLIST_FILE
        path.write_text(
            '{"symbol": "BTC", "added_at": "2026-08-08T12:00:00Z"}\nnot json\n',
            encoding="utf-8",
        )
        with pytest.raises(WatchlistError, match="line 2 is invalid"):
            watched.all()

    def test_duplicate_symbols_in_file_refused_with_attribution(self, tmp_path) -> None:
        watched = store(tmp_path)
        watched.add("BTC", now=NOW)
        path = tmp_path / "watchlists" / WATCHLIST_FILE
        path.write_text(
            '{"symbol": "BTC", "added_at": "2026-08-08T12:00:00Z"}\n'
            '{"symbol": "BTC", "added_at": "2026-08-08T12:00:00Z"}\n',
            encoding="utf-8",
        )
        with pytest.raises(WatchlistError, match="line 2 repeats symbol"):
            watched.all()

    def test_journal_shape(self, tmp_path) -> None:
        watched = store(tmp_path)
        watched.add("BTC", now=NOW)
        lines = (tmp_path / "watchlists" / WATCHLIST_FILE).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = WatchlistRecord.model_validate_json(lines[0])
        assert record.symbol == "BTC"
        assert record.added_at == NOW
