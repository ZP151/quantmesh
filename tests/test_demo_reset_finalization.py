"""Final reset-publication rollback regressions."""

import shutil
from pathlib import Path

import pytest

from quantmesh.demo import seeder as demo_seeder
from quantmesh.demo.manifest import DemoScenario
from quantmesh.demo.seeder import (
    OWNERSHIP_NAME,
    DemoRootError,
    build_demo_reset_archive,
    load_demo_root,
    reset_demo_root,
    seed_demo_root,
)

SCENARIO = DemoScenario(workspace_history=False)


def test_final_load_failure_restores_original_and_retains_published_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed final assembly cannot leave the replacement publicly served."""
    root = tmp_path / "demo"
    seed_demo_root(root, SCENARIO)
    original_identity = demo_seeder.filesystem_identity(root)
    trusted_ownership_text = (root / OWNERSHIP_NAME).read_text(encoding="utf-8")
    trusted_reset_archive = build_demo_reset_archive(root)

    replacement = tmp_path / "replacement"
    original_quarantine = tmp_path / "original-quarantine"
    retained_replacement = tmp_path / "retained-replacement"
    candidates = iter((replacement, original_quarantine, retained_replacement))
    original_load = demo_seeder.load_demo_root
    original_rmtree = shutil.rmtree
    recursive_deletions: list[Path] = []

    monkeypatch.setattr(demo_seeder, "_unused_reset_quarantine", lambda _root: next(candidates))

    def fail_only_final_public_load(candidate: Path, scenario: DemoScenario):
        if Path(candidate) == root:
            raise RuntimeError("injected final public load failure")
        return original_load(candidate, scenario)

    def forbid_runtime_recursive_delete(
        candidate: str | Path,
        *args: object,
        **kwargs: object,
    ) -> None:
        path = Path(candidate)
        if path.parent == tmp_path:
            recursive_deletions.append(path)
            raise AssertionError("reset must not recursively delete a runtime path")
        original_rmtree(candidate, *args, **kwargs)

    monkeypatch.setattr(demo_seeder, "load_demo_root", fail_only_final_public_load)
    monkeypatch.setattr(shutil, "rmtree", forbid_runtime_recursive_delete)

    with pytest.raises(DemoRootError, match="final load") as raised:
        reset_demo_root(
            root,
            SCENARIO,
            trusted_ownership_text=trusted_ownership_text,
            trusted_reset_archive=trusted_reset_archive,
        )

    assert recursive_deletions == []
    assert demo_seeder.filesystem_identity(root) == original_identity
    assert load_demo_root(root, SCENARIO).root == root
    assert not original_quarantine.exists()
    assert not replacement.exists()
    assert tuple(raised.value.retained_paths) == (retained_replacement,)
    assert load_demo_root(retained_replacement, SCENARIO).root == retained_replacement
