"""Deterministic demo runtime (iteration 0014 Phase B).

The demo contract under test:

- *Replay*: two seeds of the same scenario — and a reset of a seeded
  root — produce byte-identical trees; no wall clock or process-random
  value may leak into a demo root.
- *Isolation*: the marker is the contract; reset refuses a root without
  it and never touches a non-demo root, and every injected surface is
  bound under the demo root.
- *Provenance*: the status surface and provenance.json expose
  source/synthetic/updated_at/rows consistently, and every response
  carries the demo label.
- *Assembly*: load_demo_root rebuilds the identical in-memory state and
  is a read, never a rewrite; the runtime app serves the demo through
  the read-only M1 API with the demo control surface on top.
"""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi.testclient import TestClient

from quantmesh.api.app import create_app
from quantmesh.demo.manifest import ANCHOR, MARKER_NAME, SURFACE_COUNTS, DemoScenario
from quantmesh.demo.runtime import create_demo_app
from quantmesh.demo.seeder import (
    DEMO_COMMIT,
    OWNERSHIP_NAME,
    DemoRootError,
    _is_link_or_junction,
    is_demo_root,
    load_demo_root,
    reset_demo_root,
    seed_demo_root,
)
from quantmesh.domain.models import Venue

SCENARIO = DemoScenario(workspace_history=False)


def _tree(root: Path) -> dict[str, bytes]:
    """Every file's bytes, keyed by its root-relative path."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _digest(tree: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(tree):
        digest.update(name.encode("utf-8"))
        digest.update(tree[name])
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Byte-identical replay
# ---------------------------------------------------------------------------


def test_two_seeds_of_the_same_scenario_are_byte_identical(tmp_path: Path) -> None:
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    seed_demo_root(root_a, SCENARIO)
    seed_demo_root(root_b, SCENARIO)
    tree_a, tree_b = _tree(root_a), _tree(root_b)
    assert set(tree_a) == set(tree_b)
    differing = {name for name in tree_a if tree_a[name] != tree_b[name]}
    assert differing == set(), f"byte-non-identical files: {sorted(differing)}"


def test_reset_reproduces_the_identical_root(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    seed_demo_root(root, SCENARIO)
    before = _digest(_tree(root))
    reset_demo_root(root, SCENARIO)
    after = _digest(_tree(root))
    assert before == after


def test_different_seed_produces_different_root(tmp_path: Path) -> None:
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    seed_demo_root(root_a, SCENARIO)
    seed_demo_root(
        root_b,
        DemoScenario(seed=SCENARIO.seed + 1, workspace_history=False),
    )
    assert _digest(_tree(root_a)) != _digest(_tree(root_b))


# ---------------------------------------------------------------------------
# Isolation: the marker is the contract
# ---------------------------------------------------------------------------


def test_re_seed_refuses_a_marked_root(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    seed_demo_root(root, SCENARIO)
    with pytest.raises(DemoRootError, match="already seeded"):
        seed_demo_root(root, SCENARIO)
    # The first seed is untouched by the refused re-seed.
    assert is_demo_root(root)


def test_reset_refuses_a_root_without_the_marker(tmp_path: Path) -> None:
    # A non-demo directory (no marker) must never be wiped.
    root = tmp_path / "not-a-demo-root"
    root.mkdir()
    sentinel = root / "precious-file.json"
    sentinel.write_text('{"operator": "data"}', encoding="utf-8")
    with pytest.raises(DemoRootError, match="no QUANTMESH_DEMO_ROOT marker"):
        reset_demo_root(root, SCENARIO)
    assert sentinel.read_text(encoding="utf-8") == '{"operator": "data"}'


def test_seed_refuses_to_claim_a_nonempty_unmarked_root(tmp_path: Path) -> None:
    root = tmp_path / "operator-data"
    root.mkdir()
    sentinel = root / "precious-file.json"
    sentinel.write_text('{"operator": "data"}', encoding="utf-8")

    with pytest.raises(DemoRootError, match="non-empty"):
        seed_demo_root(root, SCENARIO)

    assert not is_demo_root(root)
    assert sentinel.read_text(encoding="utf-8") == '{"operator": "data"}'


def test_reset_refuses_a_forged_marker_without_demo_identity(tmp_path: Path) -> None:
    root = tmp_path / "operator-data"
    root.mkdir()
    sentinel = root / "precious-file.json"
    sentinel.write_text('{"operator": "data"}', encoding="utf-8")
    (root / MARKER_NAME).write_text(
        "deterministic demo root — reset deletes only this tree\n",
        encoding="utf-8",
    )

    with pytest.raises(DemoRootError, match="valid demo ownership record"):
        reset_demo_root(root, SCENARIO)

    assert sentinel.read_text(encoding="utf-8") == '{"operator": "data"}'


def _write_v2_ownership(root: Path, entries: list[dict[str, str]]) -> None:
    ownership_text = (
        json.dumps(
            {
                "commit": DEMO_COMMIT,
                "entries": entries,
                "format": "quantmesh-demo-ownership",
                "version": 1,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    (root / OWNERSHIP_NAME).write_text(ownership_text, encoding="utf-8")
    ownership_sha256 = hashlib.sha256(ownership_text.encode("utf-8")).hexdigest()
    marker_text = (
        json.dumps(
            {
                "commit": DEMO_COMMIT,
                "format": "quantmesh-demo-root",
                "ownership_sha256": ownership_sha256,
                "version": 2,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    (root / MARKER_NAME).write_text(marker_text, encoding="utf-8")


def test_reset_refuses_a_self_signed_v2_inventory(tmp_path: Path) -> None:
    root = tmp_path / "self-signed-user-data"
    root.mkdir()
    sentinel = root / "precious-user-file.json"
    sentinel.write_text('{"operator":"data"}', encoding="utf-8")
    provenance = root / "provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "scenario": {"commit": DEMO_COMMIT},
                "surfaces": {"orders": {"rows": 0}},
            }
        ),
        encoding="utf-8",
    )
    _write_v2_ownership(
        root,
        [
            {
                "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "type": "file",
            }
            for path in sorted((sentinel, provenance), key=lambda item: item.name)
        ],
    )

    with pytest.raises(DemoRootError, match="complete seeded structure"):
        reset_demo_root(root, SCENARIO)

    assert sentinel.read_text(encoding="utf-8") == '{"operator":"data"}'


def test_reset_requires_hashes_for_every_immutable_owned_file(tmp_path: Path) -> None:
    root = tmp_path / "demo-with-weakened-inventory"
    seed_demo_root(root, SCENARIO)
    ownership_path = root / OWNERSHIP_NAME
    ownership = json.loads(ownership_path.read_text(encoding="utf-8"))
    provenance_entry = next(
        entry for entry in ownership["entries"] if entry["path"] == "provenance.json"
    )
    provenance_entry.pop("sha256")
    _write_v2_ownership(root, ownership["entries"])

    with pytest.raises(DemoRootError, match="complete seeded structure"):
        reset_demo_root(root, SCENARIO)

    assert (root / "provenance.json").is_file()


def test_windows_reparse_file_attribute_is_always_unsafe() -> None:
    class ReparseNode:
        def is_symlink(self) -> bool:
            return False

        def is_junction(self) -> bool:
            return False

        def lstat(self) -> SimpleNamespace:
            return SimpleNamespace(st_file_attributes=0x0400)

    assert _is_link_or_junction(cast(Path, ReparseNode())) is True


def test_reset_refuses_unknown_files_even_inside_a_genuine_seeded_root(
    tmp_path: Path,
) -> None:
    root = tmp_path / "demo-with-user-data"
    seed_demo_root(root, SCENARIO)
    sentinel = root / "precious-user-file.json"
    sentinel.write_text('{"operator": "data"}', encoding="utf-8")

    with pytest.raises(DemoRootError, match="complete seeded structure"):
        reset_demo_root(root, SCENARIO)

    assert sentinel.read_text(encoding="utf-8") == '{"operator": "data"}'
    assert (root / "QUANTMESH_DEMO_OWNERSHIP.json").is_file()


def test_reset_refuses_a_link_added_below_a_genuine_seeded_root(tmp_path: Path) -> None:
    root = tmp_path / "demo-with-link"
    seed_demo_root(root, SCENARIO)
    outside = tmp_path / "outside.txt"
    outside.write_text("operator data", encoding="utf-8")
    link = root / "documents" / "operator-link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("this environment cannot create symlinks")

    with pytest.raises(DemoRootError, match="complete seeded structure"):
        reset_demo_root(root, SCENARIO)

    assert outside.read_text(encoding="utf-8") == "operator data"
    assert link.is_symlink()


def test_load_refuses_a_root_without_the_marker(tmp_path: Path) -> None:
    root = tmp_path / "plain"
    root.mkdir()
    with pytest.raises(DemoRootError, match="marker"):
        load_demo_root(root, SCENARIO)


# ---------------------------------------------------------------------------
# Provenance surface
# ---------------------------------------------------------------------------


def test_provenance_contract(tmp_path: Path) -> None:
    seeded = seed_demo_root(tmp_path / "demo", SCENARIO)
    provenance = json.loads((seeded.root / "provenance.json").read_text(encoding="utf-8"))
    scenario = provenance["scenario"]
    assert scenario["seed"] == SCENARIO.seed
    assert scenario["anchor"] == ANCHOR.isoformat()
    assert scenario["commit"] == DEMO_COMMIT
    surfaces = provenance["surfaces"]
    universe = [*SCENARIO.equities, *SCENARIO.crypto]
    market_keys = set()
    for spec in universe:
        files = (
            ("moomoo_bars.json", "moomoo_books.json", "moomoo_trades.json")
            if spec.kind == "equity"
            else ("hyperliquid_bars.json", "hyperliquid_books.json", "hyperliquid_trades.json")
        )
        market_keys.update(f"market:{spec.venue}:{spec.symbol}:{name}" for name in files)
    assert set(surfaces) == (
        set(SURFACE_COUNTS)
        | market_keys
        | {f"lake:demo-{spec.venue}-{spec.symbol.lower()}" for spec in universe}
        | {"orders", "history", "price_forecasts", "paper_proposals"}
    )
    for name, surface in surfaces.items():
        assert surface["source"] == "demo"
        assert surface["synthetic"] is True
        assert surface["updated_at"] == ANCHOR.isoformat()
        assert isinstance(surface["rows"], int)
        if name in {"paper_proposals", "price_forecasts"}:
            assert surface["rows"] == 0
        else:
            assert surface["rows"] >= 1
    # The marker is the isolation contract.
    assert (seeded.root / MARKER_NAME).is_file()
    # The account snapshot round-trips.
    account = json.loads((seeded.root / "account.json").read_text(encoding="utf-8"))
    assert account["cash"] == seeded.account.cash


def test_every_surface_has_rows(tmp_path: Path) -> None:
    seeded = seed_demo_root(tmp_path / "demo", SCENARIO)
    assert len(seeded.account.orders) == 8
    assert len(seeded.account.positions) == 5
    assert len(seeded.experiments.all()) == SCENARIO.surface_counts["experiments"]
    assert len(seeded.promotions.all()) == SCENARIO.surface_counts["promotions"]
    assert len(seeded.reports.all()) == SCENARIO.surface_counts["reports"]
    assert len(seeded.forecasts.all()) == SCENARIO.surface_counts["forecasts"]
    assert len(seeded.alerts.all()) == SCENARIO.surface_counts["alerts"]
    assert len(seeded.mappings.all()) == SCENARIO.surface_counts["mappings"]
    assert len(seeded.decisions.all()) == SCENARIO.surface_counts["decisions"]
    assert len(seeded.documents.all()) == SCENARIO.surface_counts["documents"]
    assert len(seeded.journal.all()) == 8
    assert seeded.price_forecasts.all() == []
    assert seeded.proposal_ledger.all() == ()
    assert len(seeded.watchlist.all()) == 4
    # moomoo enablement was requested (pending); the hyperliquid
    # request was withdrawn (disabled) — the ledger drives both.
    states = seeded.enablement.states()
    assert set(states) == {Venue.MOOMOO, Venue.HYPERLIQUID}
    assert states[Venue.MOOMOO].value == "pending"
    assert states[Venue.HYPERLIQUID].value == "disabled"


# ---------------------------------------------------------------------------
# Load is a read; the rebuilt assembly is identical
# ---------------------------------------------------------------------------


def test_load_is_a_read_and_rebuilds_identical_state(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    seeded = seed_demo_root(root, SCENARIO)
    before = _tree(root)
    loaded = load_demo_root(root, SCENARIO)
    # A load never rewrites a byte (restart is a read, not a re-seed).
    assert _tree(root) == before
    # In-memory state is identical by construction.
    assert loaded.account.cash == seeded.account.cash
    assert loaded.account.positions == seeded.account.positions
    assert loaded.marks == seeded.marks
    assert loaded.markets == seeded.markets
    assert loaded.provenance == seeded.provenance
    assert loaded.scenario == seeded.scenario
    assert [order.order_id for order in loaded.journal.all()] == [
        order.order_id for order in seeded.journal.all()
    ]


def test_load_recovers_the_seeded_scenario(tmp_path: Path) -> None:
    # A default-scenario load of a differently-seeded root must read the
    # root's own scenario from provenance, not the caller's default.
    root = tmp_path / "demo"
    seed_demo_root(root, DemoScenario(seed=7, workspace_history=False))
    loaded = load_demo_root(root, SCENARIO)
    assert loaded.scenario.seed == 7


# ---------------------------------------------------------------------------
# Providers serve the demo universe through the real pipeline
# ---------------------------------------------------------------------------


def test_providers_serve_the_full_demo_universe(tmp_path: Path) -> None:
    seeded = seed_demo_root(tmp_path / "demo", SCENARIO)
    for spec in (*SCENARIO.equities, *SCENARIO.crypto):
        series = seeded.providers.series(spec.venue, spec.symbol)
        assert len(series) == 5, f"{spec.venue}:{spec.symbol} has no seeded series"
        closes = [row.close for row in series]
        # The last seeded close is the mark the account board serves.
        assert seeded.markets[spec.venue][spec.symbol] == round(closes[-1], 4)
        # Books and trades flow through the same real adapters.
        assert len(seeded.providers.order_books(spec.venue, spec.symbol)) == 1
        assert len(seeded.providers.trades(spec.venue, spec.symbol)) == 3
    assert seeded.providers.universe() == {
        (spec.venue, spec.symbol) for spec in (*SCENARIO.equities, *SCENARIO.crypto)
    }
    with pytest.raises(ValueError, match="outside the seeded universe"):
        seeded.providers.series("moomoo", "DOES-NOT-EXIST")


# ---------------------------------------------------------------------------
# The runtime app: status, reset, provenance headers, read-only API
# ---------------------------------------------------------------------------


@pytest.fixture()
def demo_client(tmp_path: Path):
    app = create_demo_app(
        root=tmp_path / "runtime",
        seed=SCENARIO.seed,
        workspace_history=False,
        host="127.0.0.1",
    )
    with TestClient(app) as client:
        yield client, app


def test_status_exposes_the_provenance_contract(demo_client) -> None:
    client, _app = demo_client
    response = client.get("/api/demo/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "demo"
    assert payload["marker"] == MARKER_NAME
    assert payload["source"] == "demo"
    assert payload["synthetic"] is True
    assert payload["scenario"]["seed"] == SCENARIO.seed
    assert payload["scenario"]["anchor"] == ANCHOR.isoformat()
    assert payload["last_update"] == ANCHOR.isoformat()
    assert payload["health"]["status"] == "ok"
    for name, surface in payload["surfaces"].items():
        assert surface["source"] == "demo"
        assert surface["synthetic"] is True
        assert surface["updated_at"] == ANCHOR.isoformat()
    # The root-prefixed mount serves the same handlers.
    root_status = client.get("/demo/status")
    assert root_status.status_code == 200
    assert root_status.json() == payload


def test_every_response_carries_the_demo_label(demo_client) -> None:
    client, _app = demo_client
    response = client.get("/api/health")
    assert response.json()["runtime_mode"] == "demo"
    assert response.headers["X-QuantMesh-Source"] == "demo"
    assert response.headers["X-QuantMesh-Synthetic"] == "true"
    assert response.headers["X-QuantMesh-Anchor"] == ANCHOR.isoformat()


def test_reset_returns_the_identical_status_and_state(demo_client) -> None:
    client, _app = demo_client
    before = client.get("/api/demo/status").json()
    positions_before = client.get("/api/positions").json()
    account_before = client.get("/api/account").json()
    response = client.post("/api/demo/reset")
    assert response.status_code == 200
    assert response.json() == before  # byte-identical replay
    assert client.get("/api/positions").json() == positions_before
    assert client.get("/api/account").json() == account_before


def test_reset_restores_state_after_writes(demo_client) -> None:
    client, app = demo_client
    # The kill-switch POST flips the demo account (the two write
    # surfaces coexist); reset restores the pristine scenario.
    flipped = client.post(
        "/kill-switch",
        data={"action": "engage", "confirm": "confirm"},
        follow_redirects=False,
    )
    assert flipped.status_code == 303
    assert client.get("/api/kill-switch").json()["kill_switch"] is True
    response = client.post("/api/demo/reset")
    assert response.status_code == 200
    assert client.get("/api/kill-switch").json()["kill_switch"] is False
    assert app.state.account.kill_switch is False


def test_cross_origin_reset_is_refused(demo_client) -> None:
    client, _app = demo_client
    response = client.post("/api/demo/reset", headers={"Origin": "https://evil.example"})
    assert response.status_code == 403


def test_read_only_api_serves_the_demo_state(demo_client) -> None:
    client, _app = demo_client
    assert client.get("/api/health").json()["status"] == "ok"
    positions = client.get("/api/positions").json()
    assert len(positions) == 5
    orders = client.get("/api/orders").json()
    assert len(orders) == 8
    account = client.get("/api/account").json()
    assert account["cash"] == pytest.approx(60_610.44)
    pnl = client.get("/api/pnl").json()
    assert pnl["missing_marks"] == []


def test_no_demo_runtime_on_a_plain_app() -> None:
    account_factory_app = create_app(account=None)  # type: ignore[arg-type]
    with TestClient(account_factory_app) as client:
        assert client.get("/api/demo/status").status_code == 404
        assert client.post("/api/demo/reset").status_code == 404
        assert "X-QuantMesh-Source" not in client.get("/api/health").headers
