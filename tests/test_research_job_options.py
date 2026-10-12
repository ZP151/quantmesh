"""Qualified fixture choices come only from the Worker input root."""

import json

import pytest

from quantmesh.research.job_options import job_options
from tests.research_fixtures import pinned_lake


def test_configured_fixture_options(tmp_path):
    pinned_lake(tmp_path)
    options = job_options(tmp_path, ("equities",))
    assert options.status == "configured"
    assert [s.strategy_id for s in options.strategies] == [
        "momentum",
        "mean_reversion",
        "risk_parity",
    ]
    assert options.datasets[0].minimum_available_bars == 60
    assert options.datasets[0].dataset.permission_class == "fixture"
    assert len(options.datasets[0].universe) == 3
    assert options.datasets[0].interval == "1h"


@pytest.mark.parametrize("ids", [(), ("absent",), ("../equities",)])
def test_wrong_root_or_no_configured_input_disables(tmp_path, ids):
    pinned_lake(tmp_path)
    result = job_options(tmp_path / "wrong", ids)
    assert result.status == "unavailable"
    assert result.datasets == []
    assert result.reason == "no_qualified_inputs"


@pytest.mark.parametrize("change", ["rights", "schema", "coverage", "few", "future"])
def test_unsupported_or_incomplete_fixture_disables(tmp_path, change):
    pinned_lake(tmp_path, n=2 if change == "few" else 60)
    path = tmp_path / "equities" / "manifest.json"
    manifest = json.loads(path.read_bytes())
    if change == "rights":
        manifest["license"] = "unknown"
    elif change == "schema":
        manifest["schema_version"] = 2
    elif change == "coverage":
        manifest["coverage"][0]["rows"] += 1
    elif change == "future":
        manifest["coverage"][0]["end"] = "2099-01-01T00:00:00Z"
    path.write_text(json.dumps(manifest))
    assert job_options(tmp_path, ("equities",)).datasets == []


def test_changed_pin_never_reuses_cached_options(tmp_path):
    pinned_lake(tmp_path)
    original = job_options(tmp_path, ("equities",)).datasets[0].dataset
    path = tmp_path / "equities" / "manifest.json"
    manifest = json.loads(path.read_bytes())
    manifest["revision"] += 1
    path.write_text(json.dumps(manifest))
    assert job_options(tmp_path, ("equities",)).datasets[0].dataset != original


def test_symlink_root_rejected_before_read(tmp_path):
    real = tmp_path / "real"
    pinned_lake(real)
    link = tmp_path / "link"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("native symlink privilege unavailable")
    assert job_options(link, ("equities",)).datasets == []
