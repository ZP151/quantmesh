"""Local runtime assembly seam (iteration 0026).

The ``build_workstation_stores`` factory lays the eleven ADR-0006 stores out
under one root (demo) or the operator's settings dirs (non-demo); this test
pins both layouts so a surface can never be bound to the wrong path.
"""

from __future__ import annotations

from pathlib import Path

from quantmesh.runtime import WorkstationStores, build_workstation_stores
from quantmesh.settings import settings


def test_build_stores_under_a_demo_root(tmp_path: Path) -> None:
    stores = build_workstation_stores(root=tmp_path)

    assert isinstance(stores, WorkstationStores)
    assert stores.watchlist.root == tmp_path / "watchlists"
    assert stores.experiments.root == tmp_path / "research" / "experiments"
    assert stores.experiments.lake_root == tmp_path / "market" / "lake"
    assert stores.reports.root == tmp_path / "research" / "reports"
    assert stores.forecasts.root == tmp_path / "research" / "reports"
    assert stores.promotions.root == tmp_path / "research" / "promotions"
    assert stores.alerts.root == tmp_path / "alerts"
    assert stores.journal.root == tmp_path / "orders"
    assert stores.mappings.root == tmp_path / "mappings"
    assert stores.decisions.root == tmp_path / "decisions"
    assert stores.decision_packets.root == tmp_path / "decisions" / "packets"
    assert stores.documents.root == tmp_path / "documents"
    assert stores.enablement.root == tmp_path / "enablement"


def test_build_stores_uses_settings_defaults_without_a_root() -> None:
    stores = build_workstation_stores()

    assert stores.watchlist.root == settings.watchlists_dir
    assert stores.experiments.root == settings.experiments_dir
    assert stores.reports.root == settings.reports_dir
    assert stores.journal.root == settings.orders_dir
    assert stores.decision_packets.root == settings.decisions_dir / "packets"
