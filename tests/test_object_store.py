from pathlib import Path

import pytest

from quantmesh.data.objects import ObjectIntegrityError, ObjectStore


def test_object_store_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    payload = b'{"close":100.0}'

    first = store.put_bytes("application/json", payload)
    second = store.put_bytes("application/json", payload)

    assert first == second
    assert first.digest == "2f3f2fb48dd358b6b1b3b605277802675869ab47ce80ba7bb59c4a452d6b9c2b"
    assert store.path_for(first) == (
        tmp_path / ".trusted-data-v2" / "objects" / "sha256" / first.digest[:2] / first.digest
    )
    assert store.get_bytes(first) == payload


def test_object_store_detects_existing_object_corruption(tmp_path: Path) -> None:
    store = ObjectStore(tmp_path)
    payload = b"trusted bytes"
    reference = store.put_bytes("application/octet-stream", payload)
    store.path_for(reference).write_bytes(b"tampered")

    with pytest.raises(ObjectIntegrityError, match="hash mismatch"):
        store.get_bytes(reference)
    with pytest.raises(ObjectIntegrityError, match="conflicting bytes"):
        store.put_bytes("application/octet-stream", payload)


def test_object_store_rejects_blank_media_type(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="media_type"):
        ObjectStore(tmp_path).put_bytes("  ", b"payload")


def test_v2_namespace_does_not_collide_with_legal_v1_dataset_names(
    tmp_path: Path,
) -> None:
    legacy_objects = tmp_path / "objects" / "legacy-marker"
    legacy_datasets = tmp_path / "datasets" / "legacy-marker"
    legacy_objects.parent.mkdir()
    legacy_datasets.parent.mkdir()
    legacy_objects.write_bytes(b"v1 objects dataset")
    legacy_datasets.write_bytes(b"v1 datasets dataset")

    reference = ObjectStore(tmp_path).put_bytes("application/octet-stream", b"v2")

    assert reference.digest
    assert legacy_objects.read_bytes() == b"v1 objects dataset"
    assert legacy_datasets.read_bytes() == b"v1 datasets dataset"


def test_object_store_rejects_a_windows_junction_component(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Path.is_junction

    def report_objects_as_junction(path: Path) -> bool:
        return path.name == "objects" or original(path)

    monkeypatch.setattr(Path, "is_junction", report_objects_as_junction)

    with pytest.raises(ObjectIntegrityError, match="reparse point"):
        ObjectStore(tmp_path).put_bytes("application/octet-stream", b"payload")
