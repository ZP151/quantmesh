"""Shared ``JsonlStore`` seam (iteration 0022, issue #111).

One test seam for the ADR-0006 discipline every registry used to
reimplement: atomic temp+replace appends, fail-closed line-attributed
reads, duplicate identity refusal, hostile-path refusal and schema
validation. ``FixtureRecord`` is a domain-free model so the seam is
proven without depending on any registry.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import BaseModel

from quantmesh.persistence.jsonl import JsonlStore

FILENAME = "fixtures.jsonl"


class FixtureRecord(BaseModel):
    """Minimal record: a required identity and a nullable payload."""

    id: str
    value: int = 0


def make_store(root: Path, **overrides) -> JsonlStore[FixtureRecord]:
    kwargs = dict(
        root=root,
        filename=FILENAME,
        model=FixtureRecord,
        label="fixture store",
        id_label="fixture",
        key=lambda record: record.id,
    )
    kwargs.update(overrides)
    return JsonlStore(**kwargs)


def record(id_value: str, value: int = 0) -> FixtureRecord:
    return FixtureRecord(id=id_value, value=value)


def write_lines(path: Path, *lines: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


class KeyedRecord(BaseModel):
    """Record with an optional secondary identity (an idempotency key)."""

    id: str
    idempotency_key: str | None = None


def make_keyed_store(root: Path, **overrides) -> JsonlStore[KeyedRecord]:
    kwargs = dict(
        root=root,
        filename="keyed.jsonl",
        model=KeyedRecord,
        label="keyed store",
        id_label="order",
        article="an",
        key=lambda record: record.id,
        secondary_keys=[("idempotency key", lambda record: record.idempotency_key)],
    )
    kwargs.update(overrides)
    return JsonlStore(**kwargs)


# --- read / write / append round-trip ---------------------------------------


def test_round_trip_is_byte_identical(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.append(record("a", 1))
    store.append(record("b", 2))

    assert (tmp_path / FILENAME).read_text(encoding="utf-8") == (
        '{"id":"a","value":1}\n{"id":"b","value":2}\n'
    )
    assert store.read() == [record("a", 1), record("b", 2)]


def test_write_replaces_the_whole_store(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.write([record("a", 1), record("b", 2)])
    store.write([record("c", 3)])

    assert store.read() == [record("c", 3)]


def test_read_missing_root_or_file_is_empty(tmp_path: Path) -> None:
    store = make_store(tmp_path / "nested")
    assert store.read() == []

    tmp_path.mkdir(parents=True, exist_ok=True)
    assert store.read() == []


def test_blank_lines_are_ignored(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    write_lines(tmp_path / FILENAME, '{"id":"a","value":1}\n', "\n", '{"id":"b","value":2}\n')
    assert store.read() == [record("a", 1), record("b", 2)]


# --- corruption (fail-closed with line attribution) --------------------------


def test_read_fails_closed_on_corrupt_line(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    write_lines(tmp_path / FILENAME, "not json\n")
    with pytest.raises(ValueError, match="line 1"):
        store.read()


def test_read_fails_closed_on_schema_violation(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    write_lines(tmp_path / FILENAME, '{"value": 7}\n')  # missing required id
    with pytest.raises(ValueError, match="line 1"):
        store.read()


def test_read_attributes_the_offending_line_not_the_first(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    write_lines(tmp_path / FILENAME, '{"id":"a"}\n', "nope\n")
    with pytest.raises(ValueError, match="line 2"):
        store.read()


def test_read_fails_closed_on_unreadable_bytes(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    (tmp_path / FILENAME).write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ValueError, match="unreadable"):
        store.read()


# --- duplicate handling ------------------------------------------------------


def test_read_fails_closed_on_duplicate_ids(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    write_lines(tmp_path / FILENAME, '{"id":"a"}\n', '{"id":"a"}\n')
    with pytest.raises(ValueError, match="share a fixture id"):
        store.read()


def test_append_refuses_a_duplicate(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.append(record("a"))
    with pytest.raises(ValueError, match="already recorded"):
        store.append(record("a"))


def test_append_refuses_duplicate_without_touching_the_store(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.append(record("a", 1))
    with pytest.raises(ValueError):
        store.append(record("a", 2))
    assert store.read() == [record("a", 1)]


# --- hostile-path checks -----------------------------------------------------


def test_root_that_is_a_file_is_refused_on_read(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.write_text("not a directory", encoding="utf-8")
    store = make_store(root)
    with pytest.raises(ValueError, match="not a directory"):
        store.read()


def test_root_that_is_a_file_is_refused_on_write(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.write_text("not a directory", encoding="utf-8")
    store = make_store(root)
    with pytest.raises(ValueError, match="not a directory"):
        store.append(record("a"))


def test_store_path_that_is_a_directory_is_refused(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    (tmp_path / FILENAME).mkdir()
    with pytest.raises(ValueError, match="not a file"):
        store.read()


def test_write_refuses_a_directory_path(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / FILENAME).mkdir()
    with pytest.raises(ValueError, match="not a file"):
        store.write([record("a")])


def test_symlinked_store_file_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside.jsonl"
    outside.write_text('{"id":"a"}\n', encoding="utf-8")
    store = make_store(tmp_path)
    try:
        os.symlink(outside, tmp_path / FILENAME)
    except OSError:
        pytest.skip("cannot create symlinks on this machine")
    with pytest.raises(ValueError, match="symlink"):
        store.read()


def test_symlinked_root_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / FILENAME).write_text('{"id":"a"}\n', encoding="utf-8")
    link = tmp_path / "linked-root"
    try:
        os.symlink(outside, link)
    except OSError:
        pytest.skip("cannot create symlinks on this machine")
    store = make_store(link)
    with pytest.raises(ValueError, match="symlink"):
        store.read()


# --- scan (crash orphans and hostile entries) --------------------------------


def test_scan_reports_leftover_temp_file(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    orphan = tmp_path / ".fixtures.jsonl.crash.tmp"
    orphan.write_text('{"id":"a"}\n', encoding="utf-8")

    assert store.scan() == [orphan]


def test_scan_reports_a_symlinked_store_file(tmp_path: Path) -> None:
    outside = tmp_path / "outside.jsonl"
    outside.write_text('{"id":"a"}\n', encoding="utf-8")
    store = make_store(tmp_path)
    try:
        os.symlink(outside, tmp_path / FILENAME)
    except OSError:
        pytest.skip("cannot create symlinks on this machine")

    assert store.scan() == [tmp_path / FILENAME]


def test_scan_is_empty_on_a_clean_store(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.append(record("a"))
    assert store.scan() == []


def test_write_leaves_no_temp_file_behind(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.append(record("a"))
    assert list(tmp_path.glob("*.tmp")) == []


def test_failed_replace_leaves_target_unchanged_and_no_orphan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = make_store(tmp_path)
    store.append(record("a", 1))

    from quantmesh.persistence import jsonl

    def boom(source: str | Path, target: str | Path) -> None:
        raise OSError("simulated crash mid-replace")

    monkeypatch.setattr(jsonl, "atomic_replace", boom)
    with pytest.raises(OSError):
        store.append(record("b", 2))

    assert (tmp_path / FILENAME).read_text(encoding="utf-8") == '{"id":"a","value":1}\n'
    assert list(tmp_path.glob("*.tmp")) == []


# --- extra validation and error-type configuration ---------------------------


def test_extra_validate_is_applied_on_read(tmp_path: Path) -> None:
    def reject_odd(record_value: FixtureRecord) -> None:
        if record_value.value % 2 == 1:
            raise ValueError("odd values are forbidden")

    store = make_store(tmp_path, extra_validate=reject_odd)
    write_lines(tmp_path / FILENAME, '{"id":"a","value":1}\n')
    with pytest.raises(ValueError, match="line 1"):
        store.read()


def test_error_type_is_configurable(tmp_path: Path) -> None:
    class StoreError(ValueError):
        pass

    store = make_store(tmp_path, error_type=StoreError)
    write_lines(tmp_path / FILENAME, "not json\n")
    with pytest.raises(StoreError, match="line 1"):
        store.read()


# --- secondary identity keys -------------------------------------------------


def test_read_fails_closed_on_duplicate_secondary_key(tmp_path: Path) -> None:
    store = make_keyed_store(tmp_path)
    write_lines(
        tmp_path / "keyed.jsonl",
        '{"id":"a","idempotency_key":"k"}\n',
        '{"id":"b","idempotency_key":"k"}\n',
    )
    with pytest.raises(ValueError, match="share an idempotency key"):
        store.read()


def test_read_allows_none_secondary_keys(tmp_path: Path) -> None:
    store = make_keyed_store(tmp_path)
    write_lines(tmp_path / "keyed.jsonl", '{"id":"a"}\n', '{"id":"b"}\n')
    assert store.read() == [KeyedRecord(id="a"), KeyedRecord(id="b")]


def test_primary_duplicate_uses_configured_article(tmp_path: Path) -> None:
    store = make_keyed_store(tmp_path)
    write_lines(tmp_path / "keyed.jsonl", '{"id":"a"}\n', '{"id":"a"}\n')
    with pytest.raises(ValueError, match="share an order id"):
        store.read()


def test_append_refuses_only_primary_key_collision(tmp_path: Path) -> None:
    # A differing primary id with a None secondary key is appendable even
    # when the store carries a keyed record (secondary is a read-time gate).
    store = make_keyed_store(tmp_path)
    store.append(KeyedRecord(id="a", idempotency_key="k"))
    store.append(KeyedRecord(id="b", idempotency_key=None))
    assert [r.id for r in store.read()] == ["a", "b"]


# --- in-place update ---------------------------------------------------------


def test_update_replaces_the_matching_record(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.append(record("a", 1))
    store.append(record("b", 2))

    store.update(record("b", 3))

    assert store.read() == [record("a", 1), record("b", 3)]


def test_update_is_byte_identical(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.append(record("a", 1))
    store.append(record("b", 2))

    store.update(record("a", 9))

    assert (tmp_path / FILENAME).read_text(encoding="utf-8") == (
        '{"id":"a","value":9}\n{"id":"b","value":2}\n'
    )


def test_update_of_missing_record_is_refused(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    with pytest.raises(ValueError, match="not recorded"):
        store.update(record("a"))


def test_update_of_missing_record_does_not_touch_the_store(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.append(record("a", 1))
    with pytest.raises(ValueError):
        store.update(record("b", 2))
    assert store.read() == [record("a", 1)]
