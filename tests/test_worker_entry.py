"""Fixed Worker entry contract tests; source checks do not qualify an image."""

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from quantmesh.research import worker_provenance as provenance
from quantmesh.research.linux_bootstrap import _bound_command
from quantmesh.research.worker_provenance import (
    SourcePreflightRejected,
    _assert_source_associations,
    _read,
)


def _entry_module():
    path = Path(__file__).parents[1] / "deploy" / "research_worker" / "worker_entry.py"
    spec = importlib.util.spec_from_file_location("worker_entry_test_module", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bootstrap_produced_fixed_argv_is_accepted_by_entry_parser():
    command = [
        "/usr/local/bin/python3",
        "-B",
        "-I",
        "-S",
        "/opt/quantmesh/worker_entry.py",
        "--binding",
        "/inputs/parent-binding.json",
        "--manifest",
        "/opt/quantmesh/manifest.json",
        "--inventory",
        "/opt/quantmesh/inventory.json",
    ]
    bound = _bound_command(command, "a" * 64)

    assert _entry_module()._arguments(bound[5:])


@pytest.mark.parametrize(
    "mutation",
    [
        lambda argv: argv.__setitem__(0, "--wrong-binding"),
        lambda argv: argv.__setitem__(2, "/tmp/parent-binding.json"),
        lambda argv: argv.__setitem__(4, "/tmp/manifest.json"),
        lambda argv: argv.__setitem__(6, "g" * 64),
        lambda argv: argv.append("--binding-sha256"),
    ],
)
def test_entry_parser_rejects_noncanonical_bootstrap_argv(mutation):
    command = [
        "/usr/local/bin/python3",
        "-B",
        "-I",
        "-S",
        "/opt/quantmesh/worker_entry.py",
        "--binding",
        "/inputs/parent-binding.json",
        "--manifest",
        "/opt/quantmesh/manifest.json",
        "--inventory",
        "/opt/quantmesh/inventory.json",
    ]
    argv = _bound_command(command, "a" * 64)[5:]
    mutation(argv)

    assert not _entry_module()._arguments(argv)


def _canonical_binding_bytes():
    digest = "a" * 64
    value = {
        "schema": 1,
        "engine_id": "engine-123",
        "image_id": "sha256:" + "b" * 64,
        "image_config_sha256": digest,
        "container_id": "c" * 64,
        "owner_nonce": "d" * 32,
        "manifest_sha256": digest,
        "inventory_sha256": digest,
        "dependency_lock_sha256": digest,
        "python_executable_sha256": digest,
        "entry_sha256": digest,
        "observer_sha256": digest,
        "expected_prefix": "/usr/local",
        "python_version": "3.12.15",
        "kernel_profile_sha256": digest,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def test_binding_decoder_requires_independent_sha_and_canonical_unique_fields():
    entry = _entry_module()
    raw = _canonical_binding_bytes()
    expected = hashlib.sha256(raw).hexdigest()

    assert entry._decode_binding(raw, expected)["engine_id"] == "engine-123"

    duplicate = raw[:-1] + b',"schema":1}'
    for candidate, candidate_sha in (
        (raw, "0" * 64),
        (duplicate, hashlib.sha256(duplicate).hexdigest()),
        (raw + b" ", hashlib.sha256(raw + b" ").hexdigest()),
    ):
        with pytest.raises(ValueError):
            entry._decode_binding(candidate, candidate_sha)


@pytest.mark.parametrize("failure", ["wrong_sha", "duplicate_field"])
def test_invalid_binding_is_refused_before_entry_observer_or_project_reads(monkeypatch, failure):
    entry = _entry_module()
    raw = _canonical_binding_bytes()
    if failure == "duplicate_field":
        raw = raw[:-1] + b',"schema":1}'
    sha = hashlib.sha256(raw).hexdigest()
    if failure == "wrong_sha":
        sha = "0" * 64
    reads = []

    monkeypatch.setattr(entry, "_runtime_supported", lambda: True)
    monkeypatch.setattr(
        entry,
        "_read",
        lambda path, _limit: reads.append(path) or raw,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "/opt/quantmesh/worker_entry.py",
            "--binding",
            "/inputs/parent-binding.json",
            "--manifest",
            "/opt/quantmesh/manifest.json",
            "--inventory",
            "/opt/quantmesh/inventory.json",
            "--binding-sha256",
            sha,
        ],
    )

    with pytest.raises(ValueError):
        entry._run()
    assert reads == [entry._BINDING]


def test_real_wsl_python_refuses_unsupported_prefix_before_project_imports():
    entry = Path(__file__).parents[1] / "deploy" / "research_worker" / "worker_entry.py"
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-I",
            "-S",
            str(entry),
            "--binding",
            "/inputs/parent-binding.json",
            "--manifest",
            "/opt/quantmesh/manifest.json",
            "--inventory",
            "/opt/quantmesh/inventory.json",
            "--binding-sha256",
            "0" * 64,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr == "worker entry rejected\n"


def test_synthetic_package_sources_require_exact_manifest_and_inventory_bytes(tmp_path):
    package = tmp_path / "source" / "quantmesh" / "research"
    package.mkdir(parents=True)
    source = package / "signal.py"
    source.write_bytes(b"SIGNAL = 7\n")
    root = tmp_path / "source"
    digest = hashlib.sha256(b"SIGNAL = 7\n").hexdigest()
    expected = {"quantmesh/research/signal.py": digest}
    inventory = {str(source): digest}

    assert _assert_source_associations(root, expected, inventory) == expected


def test_synthetic_package_sources_reject_unsealed_new_python_file(tmp_path):
    package = tmp_path / "source" / "quantmesh"
    package.mkdir(parents=True)
    source = package / "signal.py"
    source.write_bytes(b"SIGNAL = 7\n")
    root = tmp_path / "source"
    digest = hashlib.sha256(b"SIGNAL = 7\n").hexdigest()
    declared = {"quantmesh/signal.py": digest}
    inventory = {str(source): digest}
    (package / "shadow.py").write_bytes(b"SHADOW = True\n")

    with pytest.raises(SourcePreflightRejected, match="^worker entry rejected$"):
        _assert_source_associations(root, declared, inventory)


@pytest.mark.parametrize("missing", [None, "library_paths", "notice_paths"])
def test_preflight_large_inventory_membership_has_linear_work(tmp_path, monkeypatch, missing):
    """Count membership work, not wall-clock time or native/image admission."""
    root = tmp_path / "source"
    package = root / "quantmesh" / "research"
    package.mkdir(parents=True)
    entry = root / "worker_entry.py"
    observer = package / "worker_provenance.py"
    build = package / "worker_build.py"
    source_raw = b"VALUE = 1\n"
    source_sha = hashlib.sha256(source_raw).hexdigest()
    for path in (entry, observer, build):
        path.write_bytes(source_raw)
    sources = {str(path.relative_to(root)): source_sha for path in (observer, build)}
    files = {str(path): source_sha for path in (entry, observer, build)}
    files.update({f"/usr/local/closure/{index}.so": source_sha for index in range(500)})
    names = list(files)[3:]
    inventory_path = root / "inventory.json"
    manifest_path = root / "manifest.json"
    inventory = {"roots": [str(root), "/usr/local"], "files": files, "symlinks": {}}
    inventory_raw = json.dumps(inventory).encode()
    inventory_path.write_bytes(inventory_raw)
    manifest = {
        "schema_version": 1,
        "source_commit": "a" * 40,
        "source_root": str(root),
        "prefix": "/usr/local",
        "python_executable": "/usr/local/bin/python3",
        "lock_path": names[0],
        "inventory_path": str(inventory_path),
        "inventory_sha256": hashlib.sha256(inventory_raw).hexdigest(),
        "source_files": sources,
        "library_paths": names[:40],
        "notice_paths": names[40:60],
    }
    if missing:
        manifest[missing][-1] = "/usr/local/not-in-inventory"
    manifest_raw = json.dumps(manifest).encode()
    manifest_path.write_bytes(manifest_raw)
    binding = json.loads(_canonical_binding_bytes())
    binding.update(
        manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
        inventory_sha256=manifest["inventory_sha256"],
        entry_sha256=source_sha,
        observer_sha256=source_sha,
    )
    raw = json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
    calls = 0
    inventory_calls = []

    def counted_path(name):
        nonlocal calls
        calls += 1
        return Path(name)

    @contextmanager
    def verified_builder(*_args):
        # Only isolate the later builder scan; real source/metadata byte checks
        # and this public preflight's membership validation still run.
        yield SimpleNamespace(
            parse_parent_binding=lambda *_a, **_kw: SimpleNamespace(**binding),
            _path=Path,
            _inventory=lambda *_a, **_kw: inventory_calls.append(True) or files,
        )

    monkeypatch.setattr(provenance, "Path", counted_path)
    monkeypatch.setattr(provenance, "_verified_builder", verified_builder)
    monkeypatch.setattr(provenance, "_directory_exists", lambda _path: True)
    arguments = dict(
        binding_raw=raw,
        expected_binding_sha256=hashlib.sha256(raw).hexdigest(),
        entry_raw=source_raw,
        observer_raw=source_raw,
        source_root=root,
        entry_path=entry,
        observer_path=observer,
        build_path=build,
        manifest_path=manifest_path,
        inventory_path=inventory_path,
    )
    if missing:
        with pytest.raises(SourcePreflightRejected):
            provenance._preflight(**arguments)
        assert not inventory_calls
    else:
        assert provenance._preflight(**arguments).source_root == str(root)
        assert inventory_calls == [True]
    # Increasing the number of required members cannot repeatedly convert the
    # entire inventory. Bound the work by inventory size, not lists×inventory.
    assert calls <= len(files) + 10


def test_source_bytes_changed_after_sealing_are_rejected(tmp_path):
    package = tmp_path / "source" / "quantmesh"
    package.mkdir(parents=True)
    source = package / "signal.py"
    source.write_bytes(b"SIGNAL = 7\n")
    root = tmp_path / "source"
    digest = hashlib.sha256(b"SIGNAL = 7\n").hexdigest()
    declared = {"quantmesh/signal.py": digest}
    inventory = {str(source): digest}
    source.write_bytes(b"SIGNAL = 8\n")

    with pytest.raises(SourcePreflightRejected, match="^worker entry rejected$"):
        _assert_source_associations(root, declared, inventory)


def test_source_walk_stops_at_shared_node_limit_without_materializing_directory(
    tmp_path, monkeypatch
):
    package = tmp_path / "source" / "quantmesh"
    package.mkdir(parents=True)
    for index in range(40):
        directory = package / f"d{index:02d}"
        directory.mkdir()
        (directory / "note.txt").write_text("tiny\n")
    for index in range(40):
        (package / f"note{index:02d}.txt").write_text("tiny\n")

    yielded = 0
    real_scandir = provenance.os.scandir

    class CountingScandir:
        def __init__(self, path):
            self._iterator = real_scandir(path)

        def __iter__(self):
            return self

        def __next__(self):
            nonlocal yielded
            item = next(self._iterator)
            yielded += 1
            return item

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            self._iterator.close()

        def close(self):
            self._iterator.close()

    monkeypatch.setattr(provenance.os, "scandir", CountingScandir)
    monkeypatch.setattr(provenance, "MAX_SOURCE_NODES", 6, raising=False)

    with pytest.raises(SourcePreflightRejected, match="^worker entry rejected$"):
        provenance._source_set(tmp_path / "source")

    assert yielded <= 6


def test_source_walk_stops_when_its_deadline_expires(tmp_path, monkeypatch):
    package = tmp_path / "source" / "quantmesh"
    package.mkdir(parents=True)
    (package / "source.py").write_text("SOURCE = True\n")
    for index in range(10):
        (package / f"note{index}.txt").write_text("tiny\n")

    path_checks = len((tmp_path / "source" / "quantmesh").parts) - 1
    calls = 0

    def clock():
        nonlocal calls
        calls += 1
        if calls <= path_checks + 1:
            return 10.0
        if calls == path_checks + 2:
            return 10.5
        return 11.1

    monkeypatch.setattr(
        provenance,
        "time",
        SimpleNamespace(monotonic=clock),
        raising=False,
    )
    monkeypatch.setattr(provenance, "MAX_SOURCE_WALK_SECONDS", 1.0, raising=False)

    with pytest.raises(SourcePreflightRejected, match="^worker entry rejected$"):
        provenance._source_set(tmp_path / "source")


@pytest.mark.parametrize("link_kind", ["symlink", "hardlink", "ancestor"])
def test_secure_source_read_refuses_links(tmp_path, link_kind):
    original = tmp_path / "original.py"
    original.write_bytes(b"VALUE = 1\n")
    if link_kind == "symlink":
        target = tmp_path / "source.py"
        target.symlink_to(original)
    elif link_kind == "hardlink":
        target = tmp_path / "source.py"
        target.hardlink_to(original)
    else:
        directory = tmp_path / "real"
        directory.mkdir()
        nested = directory / "source.py"
        nested.write_bytes(b"VALUE = 1\n")
        alias = tmp_path / "alias"
        alias.symlink_to(directory, target_is_directory=True)
        target = alias / "source.py"

    with pytest.raises(SourcePreflightRejected, match="^worker entry rejected$"):
        _read(target, 1024)


@pytest.mark.parametrize("reader_name", ["_read", "_directory_exists"])
def test_open_directory_descriptor_closes_on_ancestor_identity_mismatch(
    tmp_path, monkeypatch, reader_name
):
    path = tmp_path / "nested" / "source.py"
    path.parent.mkdir()
    path.write_bytes(b"VALUE = 1\n")
    opened = []
    real_open = provenance.os.open
    real_signature = provenance._signature
    calls = 0

    def tracked_open(name, flags, *args, **kwargs):
        fd = real_open(name, flags, *args, **kwargs)
        if kwargs.get("dir_fd") is not None:
            opened.append(fd)
        return fd

    def mismatch_once(info):
        nonlocal calls
        calls += 1
        signature = real_signature(info)
        return (*signature[:-1], signature[-1] + 1) if calls == 2 else signature

    monkeypatch.setattr(provenance.os, "open", tracked_open)
    monkeypatch.setattr(provenance, "_signature", mismatch_once)
    reader = getattr(provenance, reader_name)
    if reader_name == "_read":
        with pytest.raises(SourcePreflightRejected, match="^worker entry rejected$"):
            reader(path, 1024)
    else:
        assert reader(path.parent) is False
    assert opened
    for fd in opened:
        with pytest.raises(OSError):
            provenance.os.fstat(fd)


def test_verified_builder_is_fresh_and_removed_after_each_use(tmp_path):
    path = tmp_path / "worker_build.py"
    path.write_text("VALUE = object()\n")
    raw = path.read_bytes()
    name = "test_fresh_pinned_builder"
    identities = []

    for _ in range(2):
        with provenance._verified_builder(path, raw, name) as builder:
            identities.append(builder)
            assert sys.modules[name] is builder
        assert name not in sys.modules

    assert identities[0] is not identities[1]


def test_verified_builder_refuses_foreign_collision_without_removing_it(tmp_path):
    path = tmp_path / "worker_build.py"
    path.write_text("VALUE = 1\n")
    name = "test_foreign_pinned_builder"
    foreign = ModuleType(name)
    sys.modules[name] = foreign
    try:
        with pytest.raises(SourcePreflightRejected, match="^worker entry rejected$"):
            with provenance._verified_builder(path, path.read_bytes(), name):
                pytest.fail("foreign module collision must refuse")
        assert sys.modules[name] is foreign
    finally:
        sys.modules.pop(name, None)


def test_verified_builder_refuses_bytes_that_changed_before_compilation(tmp_path):
    path = tmp_path / "worker_build.py"
    path.write_text("VALUE = 1\n")
    stale = path.read_bytes()
    path.write_text("VALUE = 2\n")
    name = "test_stale_pinned_builder"

    with pytest.raises(SourcePreflightRejected, match="^worker entry rejected$"):
        with provenance._verified_builder(path, stale, name):
            pytest.fail("stale verified bytes must not be compiled")
    assert name not in sys.modules


def test_verified_builder_removes_itself_but_preserves_a_substitution(tmp_path):
    path = tmp_path / "worker_build.py"
    path.write_text("VALUE = 1\n")
    name = "test_substituted_pinned_builder"
    foreign = ModuleType(name)

    with pytest.raises(SourcePreflightRejected, match="^worker entry rejected$"):
        with provenance._verified_builder(path, path.read_bytes(), name):
            sys.modules[name] = foreign
    assert sys.modules[name] is foreign
    sys.modules.pop(name, None)


def test_verified_builder_cleans_up_after_execution_error(tmp_path):
    path = tmp_path / "worker_build.py"
    path.write_text("raise RuntimeError('fixture error')\n")
    name = "test_error_pinned_builder"

    with pytest.raises(RuntimeError, match="fixture error"):
        with provenance._verified_builder(path, path.read_bytes(), name):
            pass
    assert name not in sys.modules


def test_entry_revalidates_before_and_after_child_callback(tmp_path):
    entry = _entry_module()
    source = tmp_path / "source.py"
    source.write_bytes(b"PINNED\n")
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    calls = []

    def verify():
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise SourcePreflightRejected("worker entry rejected")

    def child():
        calls.append("child")
        source.write_bytes(b"CHANGED\n")

    with pytest.raises(SourcePreflightRejected, match="^worker entry rejected$"):
        entry._execute_child_after_preflight(verify, child)
    assert calls == ["child"]


def test_entry_refuses_pre_call_source_change_before_child_callback(tmp_path):
    entry = _entry_module()
    source = tmp_path / "source.py"
    source.write_bytes(b"PINNED\n")
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    source.write_bytes(b"CHANGED\n")
    calls = []

    def verify():
        if hashlib.sha256(source.read_bytes()).hexdigest() != expected:
            raise SourcePreflightRejected("worker entry rejected")

    with pytest.raises(SourcePreflightRejected, match="^worker entry rejected$"):
        entry._execute_child_after_preflight(verify, lambda: calls.append("child"))
    assert calls == []


@pytest.mark.skipif(sys.platform != "linux", reason="actual Linux descriptor accounting")
@pytest.mark.parametrize("refuse", [False, True])
def test_streaming_source_walk_does_not_leak_directory_descriptors(tmp_path, monkeypatch, refuse):
    package = tmp_path / "quantmesh"
    (package / "research").mkdir(parents=True)
    (package / "research" / "engine.py").write_bytes(b"VALUE = 1\n")
    before = set(os.listdir("/proc/self/fd"))
    if refuse:
        monkeypatch.setattr(provenance, "MAX_SOURCE_NODES", 1)
        with pytest.raises(SourcePreflightRejected):
            provenance._source_set(tmp_path)
    else:
        assert provenance._source_set(tmp_path) == {
            "quantmesh/research/engine.py": hashlib.sha256(b"VALUE = 1\n").hexdigest()
        }
    assert set(os.listdir("/proc/self/fd")) == before
