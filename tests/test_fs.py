"""Regression tests for cross-platform filesystem reliability helpers."""

from pathlib import Path

import pytest

from quantmesh import _fs


def test_atomic_replace_outlasts_brief_windows_file_lock(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A scanner holding the target past the old six attempts must recover."""

    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    source.write_text("new", encoding="utf-8")
    target.write_text("old", encoding="utf-8")
    real_replace = _fs.os.replace
    calls = 0

    def intermittently_locked(source_path: str | Path, target_path: str | Path) -> None:
        nonlocal calls
        calls += 1
        if calls <= 7:
            raise PermissionError(32, "file is in use", str(target_path))
        real_replace(source_path, target_path)

    monkeypatch.setattr(_fs.os, "replace", intermittently_locked)
    monkeypatch.setattr(_fs.time, "sleep", lambda _seconds: None)

    _fs.atomic_replace(source, target)

    assert calls == 8
    assert target.read_text(encoding="utf-8") == "new"


def test_atomic_replace_fails_closed_after_retry_deadline(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.json"
    target = tmp_path / "target.json"
    source.write_text("new", encoding="utf-8")
    target.write_text("old", encoding="utf-8")

    def persistently_locked(_source_path: str | Path, target_path: str | Path) -> None:
        raise PermissionError(32, "file is in use", str(target_path))

    monotonic_values = iter((10.0, 10.0))
    monkeypatch.setattr(_fs.os, "replace", persistently_locked)
    monkeypatch.setattr(_fs.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(_fs, "ATOMIC_REPLACE_TIMEOUT_SECONDS", 0.0)

    with pytest.raises(PermissionError):
        _fs.atomic_replace(source, target)

    assert target.read_text(encoding="utf-8") == "old"
