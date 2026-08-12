"""Tests for release intent discovery across compatible patch releases."""

from pathlib import Path

import pytest

from tools import check_release_version


def test_release_notes_select_highest_pep440_version(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    for name in (
        "v0.1.0.md",
        "v0.1.0-rc8.md",
        "v0.1.1-rc1.md",
        "v0.1.1-rc1.zh-CN.md",
    ):
        (tmp_path / name).write_text("release", encoding="utf-8")
    monkeypatch.setattr(check_release_version, "NOTES_DIR", tmp_path)

    assert check_release_version._release_note_version() == "0.1.1rc1"


def test_version_tags_cover_compatible_patch_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        check_release_version,
        "_git",
        lambda *_args: "v0.1.1-rc1\nunrelated-tag\n",
    )

    assert check_release_version._head_version_tags() == ["v0.1.1-rc1"]
