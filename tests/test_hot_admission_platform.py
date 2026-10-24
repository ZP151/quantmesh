"""Actual production platform refusal, without the protocol tests' Windows model."""

from quantmesh.live import buffer as buffer_module
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.feed import LiveFeed
from tests.test_market_history_hot_cache import budget_spec, candles, history_client, seed


def test_unavailable_directory_sync_never_enables_hot_storage(tmp_path, monkeypatch):
    root = tmp_path / "hot"
    archive = tmp_path / "archive"
    seed(archive, candles()[:2])
    original = (archive / "live/updates.duckdb").read_bytes()
    budget = buffer_module.HotCacheBudget(root, budget_spec(root, operations=4))
    monkeypatch.delattr(buffer_module.os, "O_DIRECTORY", raising=False)
    with LiveBuffer.open_bounded_hot(root, budget) as hot:
        assert hot.read_only
        feed = LiveFeed(lake=hot)
        with history_client(feed, archive) as client:
            response = client.get("/api/instruments/hyperliquid/BTC/history?range=1d")
        assert response.status_code == 200
        assert len(response.json()["primary"]["bars"]) == 2
        with history_client(feed, tmp_path / "bad-archive") as client:
            assert (
                client.get("/api/instruments/hyperliquid/BTC/history?range=1d").status_code == 404
            )
    assert not (root / "live").exists()
    assert not list(root.glob("budget-intent-*.json"))
    assert (archive / "live/updates.duckdb").read_bytes() == original
