"""Tests for bounded image metadata construction; fixtures are not image proof."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path

import pytest

# Same historical admission sample as the consumer tests; never install it.
LEGACY_LOCK = Path(__file__).parent / "fixtures/worker-admission/linux-cp312-legacy.lock"

MODULE = Path(__file__).parents[1] / "deploy/research_worker/seal_image.py"
SPEC = importlib.util.spec_from_file_location("seal_image_under_test", MODULE)
if SPEC and SPEC.loader and MODULE.exists():
    seal_image = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(seal_image)
else:
    seal_image = None


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def image(tmp_path, monkeypatch):
    source = tmp_path / "opt/quantmesh"
    prefix = tmp_path / "usr/local"
    lib = tmp_path / "usr/lib/x86_64-linux-gnu"
    docs = tmp_path / "usr/share/doc/sample"
    monkeypatch.setattr(seal_image, "SOURCE_ROOT", source)
    monkeypatch.setattr(seal_image, "PREFIX", prefix)
    monkeypatch.setattr(seal_image, "INVENTORY_ROOTS", (source, prefix, lib, docs), raising=False)
    monkeypatch.setattr(seal_image, "PYTHON_EXECUTABLE", prefix / "bin/python3")
    monkeypatch.setattr(seal_image, "LOCK_IMAGE_PATH", source / "requirements.linux-cp312.lock")
    monkeypatch.setattr(seal_image, "ENTRY_IMAGE_PATH", source / "worker_entry.py")
    monkeypatch.setattr(
        seal_image, "OBSERVER_IMAGE_PATH", source / "quantmesh/research/worker_provenance.py"
    )
    monkeypatch.setattr(seal_image, "BOOTSTRAP_IMAGE_PATH", source / "linux_bootstrap.py")
    monkeypatch.setattr(seal_image, "LICENSE_IMAGE_PATH", source / "LICENSE")
    monkeypatch.setattr(seal_image, "PACKAGE_ROOT", source / "quantmesh")
    monkeypatch.setattr(seal_image, "INVENTORY_PATH", source / "inventory.json")
    monkeypatch.setattr(seal_image, "MANIFEST_PATH", source / "manifest.json")
    for directory in (source / "quantmesh/research", prefix / "bin", lib, docs):
        directory.mkdir(parents=True)
    lock_bytes = LEGACY_LOCK.read_bytes()
    contents = {
        "deploy/research_worker/worker_entry.py": (
            source / "worker_entry.py",
            b"ENTRY = 1\n",
        ),
        "src/quantmesh/research/worker_provenance.py": (
            source / "quantmesh/research/worker_provenance.py",
            b"OBSERVER = 1\n",
        ),
        "src/quantmesh/research/linux_bootstrap.py": (
            source / "linux_bootstrap.py",
            b"BOOTSTRAP = 1\n",
        ),
        "src/quantmesh/research/linux_bootstrap.py:package-copy": (
            source / "quantmesh/research/linux_bootstrap.py",
            b"BOOTSTRAP = 1\n",
        ),
        "LICENSE": (source / "LICENSE", b"license fixture\n"),
        "services/research_agent/requirements.linux-cp312.lock": (
            source / "requirements.linux-cp312.lock",
            lock_bytes,
        ),
        "src/quantmesh/research/worker_kernel.py": (
            source / "quantmesh/research/worker_kernel.py",
            b"KERNEL = 1\n",
        ),
    }
    inputs = []
    for source_path, (destination, body) in contents.items():
        destination.write_bytes(body)
        repository_path = source_path.removesuffix(":package-copy")
        inputs.append(
            {
                "repository_path": repository_path,
                "image_path": str(destination),
                "bytes": len(body),
                "sha256": _sha(body),
            }
        )
    executable = prefix / "bin/python3"
    executable.write_bytes(b"interpreter fixture")
    library = lib / "libpython3.12.so.1.0"
    library.write_bytes(b"library fixture")
    notice = docs / "copyright"
    notice.write_bytes(b"notice fixture")
    catalog = {
        "source_commit": "a" * 40,
        "input_records": inputs,
        "roots": [str(source), str(prefix), str(lib), str(docs)],
        "library_paths": [str(library)],
        "notice_paths": [str(notice)],
    }
    return {
        "source": source,
        "prefix": prefix,
        "lib": lib,
        "docs": docs,
        "library": library,
        "notice": notice,
        "executable": executable,
        "spec": catalog,
        "contents": contents,
    }


def _produce(image, **kwargs):
    return seal_image.produce(image["spec"], **kwargs)


def test_produces_existing_canonical_metadata_schemas(image):
    assert seal_image is not None and callable(getattr(seal_image, "produce", None))
    result = _produce(image)
    assert set(result["inventory"]) == {"roots", "files", "symlinks"}
    assert set(result["manifest"]) == {
        "schema_version",
        "source_commit",
        "source_root",
        "prefix",
        "python_executable",
        "lock_path",
        "inventory_path",
        "inventory_sha256",
        "source_files",
        "library_paths",
        "notice_paths",
    }
    assert result["manifest"]["source_files"] == {
        "quantmesh/research/worker_provenance.py": _sha(
            image["contents"]["src/quantmesh/research/worker_provenance.py"][1]
        ),
        "quantmesh/research/linux_bootstrap.py": _sha(
            image["contents"]["src/quantmesh/research/linux_bootstrap.py"][1]
        ),
        "quantmesh/research/worker_kernel.py": _sha(
            image["contents"]["src/quantmesh/research/worker_kernel.py"][1]
        ),
    }
    assert result["manifest"]["python_executable"] == str(image["executable"])
    assert str(image["source"] / "manifest.json") not in result["inventory"]["files"]
    assert str(image["source"] / "inventory.json") not in result["inventory"]["files"]
    assert result["manifest_bytes"] == seal_image._canonical(result["manifest"])
    assert result["inventory_bytes"] == seal_image._canonical(result["inventory"])


def test_current_source_lock_refuses_even_with_matching_catalog(image):
    current = (
        Path(__file__).parents[1] / "services/research_agent/requirements.linux-cp312.lock"
    ).read_bytes()
    assert _sha(current) != seal_image.LINUX_LOCK_SHA256
    seal_image.LOCK_IMAGE_PATH.write_bytes(current)
    row = next(
        item
        for item in image["spec"]["input_records"]
        if item["repository_path"] == "services/research_agent/requirements.linux-cp312.lock"
    )
    row.update(bytes=len(current), sha256=_sha(current))
    assert row["sha256"] == _sha(seal_image.LOCK_IMAGE_PATH.read_bytes())
    with pytest.raises(seal_image.ImageSealRejected, match="^image metadata refused$"):
        _produce(image)
    assert not (image["source"] / "inventory.json").exists()
    assert not (image["source"] / "manifest.json").exists()


@pytest.mark.parametrize(
    "change",
    [
        "commit",
        "source_escape",
        "target_escape",
        "bad_digest",
        "duplicate_source",
        "duplicate_destination",
        "missing_license",
        "missing_entry",
        "missing_observer",
        "missing_bootstrap",
        "missing_lock",
        "bad_lock_digest",
        "metadata_dual_list",
    ],
)
def test_invalid_spec_refuses_without_publication(image, change):
    spec = json.loads(json.dumps(image["spec"]))
    if change == "commit":
        spec["source_commit"] = "abc"
    elif change == "source_escape":
        spec["input_records"][0]["repository_path"] = "../worker_entry.py"
    elif change == "target_escape":
        spec["input_records"][0]["image_path"] = str(image["source"].parent / "escape.py")
    elif change == "bad_digest":
        spec["input_records"][0]["sha256"] = "0" * 64
    elif change == "duplicate_source":
        spec["input_records"].append(
            dict(spec["input_records"][0], image_path=str(image["source"] / "copy.py"))
        )
    elif change == "duplicate_destination":
        spec["input_records"].append(dict(spec["input_records"][0], repository_path="src/copy.py"))
    elif change.startswith("missing_"):
        source_path = {
            "missing_license": "LICENSE",
            "missing_entry": "deploy/research_worker/worker_entry.py",
            "missing_observer": "src/quantmesh/research/worker_provenance.py",
            "missing_bootstrap": "src/quantmesh/research/linux_bootstrap.py",
            "missing_lock": "services/research_agent/requirements.linux-cp312.lock",
        }[change]
        spec["input_records"] = [
            item for item in spec["input_records"] if item["repository_path"] != source_path
        ]
    elif change == "bad_lock_digest":
        item = next(
            i
            for i in spec["input_records"]
            if i["repository_path"].endswith("requirements.linux-cp312.lock")
        )
        item["sha256"] = "0" * 64
    elif change == "metadata_dual_list":
        spec["input_records"].append(
            {
                "repository_path": "generated/inventory.json",
                "image_path": str(image["source"] / "inventory.json"),
                "bytes": 1,
                "sha256": "0" * 64,
            }
        )
    with pytest.raises(seal_image.ImageSealRejected):
        seal_image.produce(spec)
    assert not (image["source"] / "inventory.json").exists()
    assert not (image["source"] / "manifest.json").exists()


def test_unmapped_source_file_refuses_before_publication(image):
    (image["source"] / "unmapped-resource.json").write_text("{}")
    with pytest.raises(seal_image.ImageSealRejected):
        _produce(image)
    assert not (image["source"] / "inventory.json").exists()


def test_unreviewed_inventory_root_refuses_before_traversal_or_publication(
    image, tmp_path, monkeypatch
):
    extra = tmp_path / "home"
    extra.mkdir()
    image["spec"]["roots"].append(str(extra))
    traversed = False
    walk = seal_image._walk

    def record_walk(*args, **kwargs):
        nonlocal traversed
        traversed = True
        return walk(*args, **kwargs)

    monkeypatch.setattr(seal_image, "_walk", record_walk)
    with pytest.raises(seal_image.ImageSealRejected):
        _produce(image)
    assert not traversed
    assert not (image["source"] / "inventory.json").exists()
    assert not (image["source"] / "manifest.json").exists()


@pytest.mark.parametrize("kind", ["altered_bytes", "hardlink", "symlink", "fifo"])
def test_source_must_be_single_link_regular_bytes(image, kind):
    entry = image["source"] / "worker_entry.py"
    if kind == "altered_bytes":
        entry.write_bytes(b"changed\n")
    elif kind == "hardlink":
        alias = image["source"] / "alias.py"
        os.link(entry, alias)
    elif kind == "symlink":
        entry.unlink()
        entry.symlink_to(image["contents"]["deploy/research_worker/worker_entry.py"][1].decode())
    else:
        entry.unlink()
        os.mkfifo(entry)
    with pytest.raises(seal_image.ImageSealRejected):
        seal_image.produce(image["spec"])
    assert not (image["source"] / "inventory.json").exists()


def test_unsafe_symlink_closure_and_overlapping_roots_refuse(image):
    link = image["lib"] / "escape.so"
    link.symlink_to("../../../../etc/passwd")
    with pytest.raises(seal_image.ImageSealRejected):
        _produce(image)
    link.unlink()
    image["spec"]["roots"].append(str(image["source"] / "quantmesh"))
    with pytest.raises(seal_image.ImageSealRejected):
        _produce(image)


@pytest.mark.parametrize("limit", ["nodes", "bytes", "deadline"])
def test_shared_inventory_limits_refuse_before_publication(image, monkeypatch, limit):
    if limit == "nodes":
        monkeypatch.setattr(seal_image, "_NODE_LIMIT", 4)
    elif limit == "bytes":
        monkeypatch.setattr(seal_image, "_BYTE_LIMIT", 10)
    else:
        ticks = iter([0.0, 1000.0])
        monkeypatch.setattr(seal_image.time, "monotonic", lambda: next(ticks))
    with pytest.raises(seal_image.ImageSealRejected):
        _produce(image)
    assert not (image["source"] / "inventory.json").exists()
    assert not (image["source"] / "manifest.json").exists()


@pytest.mark.parametrize("name", ["manifest.json", "inventory.json"])
def test_preexisting_publication_collision_refuses(image, name):
    target = image["source"] / name
    target.write_bytes(b"preexisting")
    with pytest.raises(seal_image.ImageSealRejected):
        _produce(image)
    assert target.read_bytes() == b"preexisting"


def test_publication_race_removes_only_metadata_created_by_this_call(image, monkeypatch):
    publish = seal_image._publish

    def race(path, raw):
        if path == seal_image.MANIFEST_PATH:
            path.write_bytes(b"racing writer")
            raise FileExistsError(path)
        return publish(path, raw)

    monkeypatch.setattr(seal_image, "_publish", race)
    with pytest.raises(seal_image.ImageSealRejected):
        _produce(image)
    assert not (image["source"] / "inventory.json").exists()
    assert (image["source"] / "manifest.json").read_bytes() == b"racing writer"


def test_failed_metadata_write_removes_the_partial_file(image, monkeypatch):
    def fail_write(_fd, _data):
        raise OSError("simulated bounded fixture write failure")

    monkeypatch.setattr(seal_image.os, "write", fail_write)
    with pytest.raises(seal_image.ImageSealRejected):
        _produce(image)
    assert not (image["source"] / "inventory.json").exists()
    assert not (image["source"] / "manifest.json").exists()
