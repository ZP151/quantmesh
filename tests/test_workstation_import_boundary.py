"""Fresh-process missing-driver boundaries; no server/provider/dependency changes."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COMMON = r"""
import importlib.abc
import json
import sys
from pathlib import Path

driver_attempts, effects = [], []

class MissingDriver(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "pg8000" or fullname.startswith("pg8000."):
            driver_attempts.append(fullname)
            raise ModuleNotFoundError("controlled absent pg8000", name="pg8000")
        return None

sys.meta_path.insert(0, MissingDriver())
from quantmesh.api import workstation as ws
from quantmesh.execution.accounting import PaperAccount
from quantmesh.live.buffer import LiveBuffer
from quantmesh.live.feed import LiveFeed

assert Path(ws.__file__).resolve() == Path.cwd() / "src/quantmesh/api/workstation.py"
owned = Path(sys.argv[1])
ws.settings.workstation_host = "127.0.0.1"
ws.settings.default_paper_mode = True
ws.settings.allow_live_trading = False
ws.settings.legacy_ui = False
ws.settings.live_cache_root = None
ws.settings.live_cache_budget_file = None
ws.settings.lake_root = owned / "unused-lake"

def forbidden(*args, **kwargs):
    effects.append("forbidden_constructor_or_external_effect")
    raise AssertionError("unrelated constructor, bind or provider called")

for name in (
    "TrustedDataCatalog", "PaperAccountFile", "PaperAccountStore", "OrderJournal",
    "WatchlistStore", "HttpModelTransport", "ModelGateway", "PaperAccount",
    "DecisionInboxService", "DecisionSessionService", "SnapshotCatalog", "ReplayService",
):
    setattr(ws, name, forbidden)

import uvicorn
uvicorn.run = forbidden

def assert_no_research_imports():
    assert driver_attempts == []
    for name in (
        "quantmesh.api.frozen_experiments", "quantmesh.api.realdata_snapshots",
        "quantmesh.api.research_jobs", "quantmesh.research.service_client",
        "quantmesh.research.job_store",
    ):
        assert name not in sys.modules, name

def read_health(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200 and health.json()["market_data_only"] is True
        assert health.json()["paper_mode"] is True and health.json()["live_trading"] is False
        assert client.post("/api/research/jobs", json={}).status_code == 403
    assert effects == []
    assert_no_research_imports()
"""

CASES = {
    "market_factory": r"""
        lake = LiveBuffer._stopped_reader(owned / "never-admitted")
        app = ws.create_workstation_app(account=PaperAccount(cash=0),
            live_feed=LiveFeed(lake=lake), market_data_only=True)
        read_health(app)
        assert lake._closed
    """,
    "ordinary_factory": r"""
        try:
            ws.create_workstation_app(account=PaperAccount(cash=0))
        except ModuleNotFoundError as error:
            assert error.name == "pg8000"
        else:
            raise AssertionError("ordinary factory hid missing declared dependency")
        assert driver_attempts and effects == []
    """,
    "ordinary_cli": r"""
        try:
            ws.main([])
        except ModuleNotFoundError as error:
            assert error.name == "pg8000"
        else:
            raise AssertionError("ordinary CLI hid missing declared dependency")
        assert driver_attempts and effects == []
    """,
    "market_cli": r"""
        ws._research_router_factories = forbidden
        from quantmesh.hyperliquid import public_info
        from quantmesh.live import hyperliquid
        public_info.PublicInfoTransport = forbidden
        hyperliquid.LiveHyperliquidTransport = forbidden
        lake = LiveBuffer._stopped_reader(owned / "never-admitted")
        roots, served = [], []
        ws.settings.live_cache_root = owned / "never-admitted"
        ws.settings.live_cache_budget_file = owned / "unused-budget.json"
        def bounded_reader(cls, root, budget):
            roots.append((root, budget))
            return lake
        LiveBuffer.from_bounded_config = classmethod(bounded_reader)
        def serve(app, **kwargs):
            served.append(kwargs)
            read_health(app)
        uvicorn.run = serve
        ws.main(["--live", "--market-data-only", "--port", "8878"])
        assert roots == [(ws.settings.live_cache_root, ws.settings.live_cache_budget_file)]
        assert served == [{"host": "127.0.0.1", "port": 8878}]
        assert lake._closed and effects == []
        assert_no_research_imports()
    """,
}


@pytest.mark.parametrize("case", CASES)
def test_missing_postgres_driver_respects_mode_boundary(case, tmp_path):
    script = COMMON + "\n" + textwrap.dedent(CASES[case])
    script += f"\nprint(json.dumps({{'case': {case!r}, 'pass': True}}))\n"
    env = dict(os.environ, PYTHONPATH=str(ROOT / "src"), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout.strip()) == {"case": case, "pass": True}
