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
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi.testclient import TestClient

from quantmesh.api.app import create_app
from quantmesh.demo import seeder as demo_seeder
from quantmesh.demo.manifest import ANCHOR, MARKER_NAME, SURFACE_COUNTS, DemoScenario
from quantmesh.demo.runtime import create_demo_app
from quantmesh.demo.seeder import (
    DEMO_COMMIT,
    OWNERSHIP_NAME,
    DemoRootError,
    _is_link_or_junction,
    build_demo_reset_archive,
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


def test_reset_reuses_one_independent_trusted_inventory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pre/post-quarantine checks share one independently built truth.

    Rebuilding the deterministic workspace for each identity check makes a
    full-history product reset exceed the browser's operator timeout without
    adding a distinct security assertion.
    """
    root = tmp_path / "demo"
    seed_demo_root(root, SCENARIO)
    calls = 0
    original = demo_seeder._trusted_ownership_text

    def counted_trusted_inventory(scenario: DemoScenario) -> str:
        nonlocal calls
        calls += 1
        return original(scenario)

    monkeypatch.setattr(
        demo_seeder,
        "_trusted_ownership_text",
        counted_trusted_inventory,
    )

    reset_demo_root(root, SCENARIO)

    assert calls == 1


def test_fresh_seed_supplies_trusted_inventory_for_fast_runtime_reset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "demo"
    seed_demo_root(root, SCENARIO)
    trusted_ownership_text = (root / OWNERSHIP_NAME).read_text(encoding="utf-8")
    trusted_reset_archive = build_demo_reset_archive(root)

    def unexpected_regeneration(_scenario: DemoScenario) -> str:
        raise AssertionError("fresh runtime reset regenerated its trusted inventory")

    monkeypatch.setattr(
        demo_seeder,
        "_trusted_ownership_text",
        unexpected_regeneration,
    )
    monkeypatch.setattr(
        demo_seeder,
        "seed_demo_root",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("runtime reset regenerated the deterministic workspace")
        ),
    )

    pristine = _digest(_tree(root))
    for _ in range(2):
        reset_demo_root(
            root,
            SCENARIO,
            trusted_ownership_text=trusted_ownership_text,
            trusted_reset_archive=trusted_reset_archive,
        )
        assert _digest(_tree(root)) == pristine


def test_reset_retains_quarantine_without_recursive_runtime_deletion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reset swaps trees atomically and retains the old tree for recovery."""
    root = tmp_path / "demo"
    seed_demo_root(root, SCENARIO)
    trusted_ownership_text = (root / OWNERSHIP_NAME).read_text(encoding="utf-8")
    trusted_reset_archive = build_demo_reset_archive(root)
    pristine = _digest(_tree(root))
    original_rmtree = shutil.rmtree
    product_deletions: list[Path] = []

    def forbidden_recursive_delete(path: str | Path, *args: object, **kwargs: object) -> None:
        candidate = Path(path)
        if candidate.parent == tmp_path:
            product_deletions.append(candidate)
            raise AssertionError("demo reset must not recursively delete a runtime path")
        original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", forbidden_recursive_delete)

    seeded = reset_demo_root(
        root,
        SCENARIO,
        trusted_ownership_text=trusted_ownership_text,
        trusted_reset_archive=trusted_reset_archive,
    )

    quarantines = list(tmp_path.glob(".demo.reset-quarantine-*"))
    assert seeded.root == root
    assert _digest(_tree(root)) == pristine
    assert product_deletions == []
    assert len(quarantines) == 1
    assert _digest(_tree(quarantines[0])) == pristine


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
    # A non-demo directory (no marker) must never be replaced.
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


def test_reset_revalidates_the_atomically_quarantined_root_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tampering after the first validation blocks replacement publication."""
    root = tmp_path / "demo"
    seed_demo_root(root, SCENARIO)
    original_replace = os.replace
    quarantined: list[Path] = []

    def replace_then_tamper(source: str | Path, target: str | Path) -> None:
        original_replace(source, target)
        if Path(source) == root and not quarantined:
            quarantine = Path(target)
            quarantined.append(quarantine)
            (quarantine / "operator-owned.txt").write_text("preserve me", encoding="utf-8")

    monkeypatch.setattr(os, "replace", replace_then_tamper)

    with pytest.raises(DemoRootError, match="changed after it was quarantined"):
        reset_demo_root(root, SCENARIO)

    assert root.is_dir()
    assert (root / "operator-owned.txt").read_text(encoding="utf-8") == "preserve me"
    assert quarantined and not quarantined[0].exists()


def test_reset_preserves_a_swapped_quarantine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A different directory moved onto the quarantine path is preserved."""
    root = tmp_path / "demo"
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "operator-owned.txt").write_text("preserve me", encoding="utf-8")
    seed_demo_root(root, SCENARIO)

    original_replace = demo_seeder.atomic_replace
    original_has_reset_structure = demo_seeder._has_reset_structure
    quarantine: Path | None = None
    parked_demo = tmp_path / "parked-demo"

    def observe_replace(source: str | Path, target: str | Path) -> None:
        nonlocal quarantine
        original_replace(source, target)
        if Path(source) == root:
            quarantine = Path(target)

    def validate_then_swap(
        candidate: Path,
        scenario: DemoScenario,
        *,
        trusted_ownership_text: str | None = None,
    ) -> bool:
        result = original_has_reset_structure(
            candidate,
            scenario,
            trusted_ownership_text=trusted_ownership_text,
        )
        if result and quarantine is not None and candidate == quarantine:
            os.replace(candidate, parked_demo)
            os.replace(unrelated, candidate)
        return result

    monkeypatch.setattr(demo_seeder, "atomic_replace", observe_replace)
    monkeypatch.setattr(demo_seeder, "_has_reset_structure", validate_then_swap)

    with pytest.raises(DemoRootError, match="identity"):
        reset_demo_root(root, SCENARIO)

    assert quarantine is not None
    assert (quarantine / "operator-owned.txt").read_text(encoding="utf-8") == "preserve me"
    assert parked_demo.is_dir()


def test_reset_retains_a_swapped_archive_replacement_without_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed swap retains every replacement path occupant for recovery."""
    root = tmp_path / "demo"
    seed_demo_root(root, SCENARIO)
    trusted_ownership_text = (root / OWNERSHIP_NAME).read_text(encoding="utf-8")
    trusted_reset_archive = build_demo_reset_archive(root)

    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    (unrelated / "operator-owned.txt").write_text("preserve me", encoding="utf-8")
    replacement = tmp_path / "replacement"
    quarantine = tmp_path / "quarantine"
    parked_replacement = tmp_path / "parked-replacement"
    candidates = iter((replacement, quarantine))
    original_replace = demo_seeder.atomic_replace

    monkeypatch.setattr(demo_seeder, "_unused_reset_quarantine", lambda _root: next(candidates))

    def swap_replacement_then_fail(source: str | Path, target: str | Path) -> None:
        if Path(source) == root:
            os.replace(replacement, parked_replacement)
            os.replace(unrelated, replacement)
            raise OSError("injected rename failure")
        original_replace(source, target)

    monkeypatch.setattr(demo_seeder, "atomic_replace", swap_replacement_then_fail)

    with pytest.raises(OSError, match="injected rename failure"):
        reset_demo_root(
            root,
            SCENARIO,
            trusted_ownership_text=trusted_ownership_text,
            trusted_reset_archive=trusted_reset_archive,
        )

    assert (replacement / "operator-owned.txt").read_text(encoding="utf-8") == "preserve me"
    assert parked_replacement.is_dir()
    assert root.is_dir()


def test_reset_restores_demo_when_validated_replacement_is_swapped_before_publish(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A post-validation replacement swap never leaves operator data at root."""
    root = tmp_path / "demo"
    seed_demo_root(root, SCENARIO)
    trusted_ownership_text = (root / OWNERSHIP_NAME).read_text(encoding="utf-8")
    trusted_reset_archive = build_demo_reset_archive(root)
    pristine = _digest(_tree(root))

    operator = tmp_path / "operator"
    operator.mkdir()
    (operator / "operator-owned.txt").write_text("preserve me", encoding="utf-8")
    operator_identity = demo_seeder.filesystem_identity(operator)
    replacement = tmp_path / "replacement"
    original_quarantine = tmp_path / "original-quarantine"
    unexpected_public = tmp_path / "unexpected-public"
    parked_replacement = tmp_path / "parked-replacement"
    candidates = iter((replacement, original_quarantine, unexpected_public))
    original_atomic_replace = demo_seeder.atomic_replace
    swapped = False

    monkeypatch.setattr(demo_seeder, "_unused_reset_quarantine", lambda _root: next(candidates))

    def swap_after_original_is_quarantined(source: str | Path, target: str | Path) -> None:
        nonlocal swapped
        original_atomic_replace(source, target)
        if Path(source) == root and not swapped:
            swapped = True
            os.replace(replacement, parked_replacement)
            os.replace(operator, replacement)

    monkeypatch.setattr(demo_seeder, "atomic_replace", swap_after_original_is_quarantined)

    with pytest.raises(DemoRootError, match="published replacement identity") as raised:
        reset_demo_root(
            root,
            SCENARIO,
            trusted_ownership_text=trusted_ownership_text,
            trusted_reset_archive=trusted_reset_archive,
        )

    restored = load_demo_root(root, SCENARIO)
    assert restored.root == root
    assert _digest(_tree(root)) == pristine
    assert not original_quarantine.exists()
    assert not operator.exists()
    assert demo_seeder.filesystem_identity(unexpected_public) == operator_identity
    assert (unexpected_public / "operator-owned.txt").read_text(encoding="utf-8") == "preserve me"
    assert tuple(raised.value.retained_paths) == (unexpected_public,)
    assert load_demo_root(parked_replacement, SCENARIO).root == parked_replacement


def test_reset_restores_original_when_published_replacement_is_tampered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post-publish structure failure cannot leave an invalid public demo."""
    root = tmp_path / "demo"
    seed_demo_root(root, SCENARIO)
    original_identity = demo_seeder.filesystem_identity(root)
    original_atomic_replace = demo_seeder.atomic_replace
    tampered = False

    def publish_then_tamper(source: str | Path, target: str | Path) -> None:
        nonlocal tampered
        original_atomic_replace(source, target)
        if Path(target) == root and Path(source) != root and not tampered:
            tampered = True
            (root / "operator-owned.txt").write_text("preserve me", encoding="utf-8")

    monkeypatch.setattr(demo_seeder, "atomic_replace", publish_then_tamper)

    with pytest.raises(DemoRootError, match="failed trusted structure validation") as raised:
        reset_demo_root(root, SCENARIO)

    assert demo_seeder.filesystem_identity(root) == original_identity
    load_demo_root(root, SCENARIO)
    retained = tuple(raised.value.retained_paths)
    assert len(retained) == 1
    assert (retained[0] / "operator-owned.txt").read_text(encoding="utf-8") == "preserve me"


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
        | {
            "orders",
            "history",
            "price_forecasts",
            "paper_proposals",
            "decision_packets",
        }
    )
    for name, surface in surfaces.items():
        assert surface["source"] == "demo"
        assert surface["synthetic"] is True
        assert surface["updated_at"] == ANCHOR.isoformat()
        assert isinstance(surface["rows"], int)
        if name in {"paper_proposals", "price_forecasts", "decision_packets"}:
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
    assert payload["retained_resets"] == []
    assert payload["retained_reset_cleanup"]["mode"] == "manual-only"
    assert payload["retained_reset_cleanup"]["automatic_deletion_supported"] is False
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
    after = response.json()
    assert {key: value for key, value in after.items() if not key.startswith("retained_")} == {
        key: value for key, value in before.items() if not key.startswith("retained_")
    }
    assert client.get("/api/positions").json() == positions_before
    assert client.get("/api/account").json() == account_before


def test_reset_status_lists_and_acknowledges_retained_tree_without_deleting(
    demo_client,
) -> None:
    client, _app = demo_client

    reset = client.post("/api/demo/reset")

    assert reset.status_code == 200
    retained = reset.json()["retained_resets"]
    assert len(retained) == 1
    retained_path = Path(retained[0]["path"])
    assert retained[0] == {
        "path": str(retained_path),
        "acknowledged": False,
        "exists": True,
    }
    assert retained_path.is_dir()

    acknowledged = client.post(
        "/api/demo/retained-reset/acknowledge",
        json={
            "path": str(retained_path),
            "confirmation": "ACKNOWLEDGE_MANUAL_CLEANUP",
        },
    )

    assert acknowledged.status_code == 200
    assert acknowledged.json()["retained_resets"] == [
        {
            "path": str(retained_path),
            "acknowledged": True,
            "exists": True,
        }
    ]
    assert retained_path.is_dir()


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
