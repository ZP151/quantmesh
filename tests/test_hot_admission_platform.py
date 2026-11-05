"""Actual production platform refusal, without the protocol tests' Windows model."""

import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantmesh.live import buffer as buffer_module
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.feed import LiveFeed
from tests.hot_volume import ample_hot_space as ample_hot_space
from tests.hot_volume import modeled_hot_space
from tests.test_market_history_hot_cache import budget_spec, candles, history_client, seed


@pytest.mark.usefixtures("ample_hot_space")
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


@pytest.mark.parametrize("extra", [20_000_000_000, 0, -1], ids=["ample", "equal", "one_below"])
def test_hot_volume_reserves_needed_space_before_creating_header(tmp_path, extra):
    root = tmp_path / "hot"
    spec = budget_spec(root, operations=4)
    needed = spec["peak_operation_bytes"] + spec["close_failure_reserve_bytes"]
    original = buffer_module.shutil
    system_reader = shutil.disk_usage
    with modeled_hot_space(tmp_path, free=50_000_000_000 + needed + extra):
        assert shutil.disk_usage is system_reader
        with pytest.raises(AssertionError, match="escaped"):
            buffer_module.shutil.disk_usage(tmp_path.parent)
        if extra < 0:
            with pytest.raises(buffer_module.LiveCapacityExceeded):
                buffer_module.HotCacheBudget(root, spec)
            assert not root.exists()
        else:
            budget = buffer_module.HotCacheBudget(root, spec)
            assert (root / "budget-spec.json").read_bytes() == budget.header
            assert not list(root.glob("budget-intent-*.json"))
    assert buffer_module.shutil is original


def test_hot_volume_is_local_to_each_python_process(tmp_path):
    checkout = Path(__file__).resolve().parents[1]
    child = """
import shutil, sys
from pathlib import Path
from types import SimpleNamespace
checkout = Path(sys.argv[1])
sys.path[:0] = [str(checkout), str(checkout / "src")]
from quantmesh.live import buffer
from tests.hot_volume import modeled_hot_space
assert buffer.shutil is shutil
root = Path(sys.argv[2])
with modeled_hot_space(root):
    buffer.HotCacheBudget._headroom(SimpleNamespace(root=root), 9_000_000)
assert buffer.shutil is shutil
"""
    with modeled_hot_space(tmp_path, free=50_008_999_999):
        subprocess.run(
            [sys.executable, "-I", "-B", "-c", child, str(checkout), str(tmp_path)],
            check=True,
            timeout=20,
        )
        with pytest.raises(buffer_module.LiveCapacityExceeded):
            buffer_module.HotCacheBudget._headroom(SimpleNamespace(root=tmp_path), 9_000_000)
