from pathlib import Path

import pytest

from quantmesh.dev.iterations import APPEND_MARKER, create_iteration, slugify


def prepare_iteration_docs(root: Path) -> None:
    iterations = root / "docs" / "iterations"
    iterations.mkdir(parents=True)
    (iterations / "ITERATION_TEMPLATE.md").write_text(
        "# {{ID}} {{TITLE}} {{STATUS}} {{STARTED}} {{OWNER}}\n",
        encoding="utf-8",
    )
    (iterations / "INDEX.md").write_text(f"# Index\n\n{APPEND_MARKER}\n", encoding="utf-8")


def test_create_iteration_writes_record_and_index(tmp_path: Path) -> None:
    prepare_iteration_docs(tmp_path)

    result = create_iteration(
        tmp_path,
        title="Paper Trading Kernel",
        owner="agent-team",
        status="active",
        started="2026-08-08",
    )

    assert result.name == "0001-paper-trading-kernel.md"
    assert "0001 Paper Trading Kernel active 2026-08-08 agent-team" in result.read_text(
        encoding="utf-8"
    )
    assert "| 0001 | active | 2026-08-08" in (
        tmp_path / "docs" / "iterations" / "INDEX.md"
    ).read_text(encoding="utf-8")


def test_slugify_rejects_non_ascii_only_title() -> None:
    with pytest.raises(ValueError):
        slugify("模拟盘")

