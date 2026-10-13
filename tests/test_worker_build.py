"""Byte-admission unit fixtures; these are not an OCI/native certificate."""

import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _api():
    assert importlib.util.find_spec("quantmesh.research.worker_build"), "byte verifier missing"
    return importlib.import_module("quantmesh.research.worker_build")


@pytest.fixture
def sealed(tmp_path):
    source, prefix, libraries, notices = (tmp_path / n for n in ("source", "prefix", "lib", "doc"))
    (source / "quantmesh").mkdir(parents=True)
    (prefix / "bin").mkdir(parents=True)
    libraries.mkdir()
    notices.mkdir()
    code = source / "quantmesh" / "engine.py"
    code.write_bytes(b"VALUE = 1\n")
    exe = prefix / "bin" / "python3"
    exe.write_bytes(b"unit-fixture interpreter bytes")
    library = libraries / "libpython.so"
    library.write_bytes(b"unit-fixture library bytes")
    notice = notices / "LICENSE"
    notice.write_bytes(b"unit-fixture notice")
    lock = prefix / "requirements.lock"
    lock.write_bytes(
        (
            Path(__file__).parents[1] / "services/research_agent/requirements.linux-cp312.lock"
        ).read_bytes()
    )
    metadata = prefix / "METADATA"
    record = prefix / "RECORD"
    metadata.write_bytes(b"Metadata-Version: 2.4\n")
    record.write_bytes(b"unit-fixture RECORD\n")
    roots = [source, prefix, libraries, notices]
    inventory = tmp_path / "inventory.json"
    inventory.write_text(
        json.dumps(
            dict(
                roots=[str(p) for p in roots],
                files={
                    str(p): _sha(p.read_bytes()) for r in roots for p in r.rglob("*") if p.is_file()
                },
                symlinks={},
            )
        )
    )
    data = dict(
        schema_version=1,
        source_commit="a" * 40,
        source_root=str(source),
        prefix=str(prefix),
        python_executable=str(exe),
        lock_path=str(lock),
        inventory_path=str(inventory),
        inventory_sha256=_sha(inventory.read_bytes()),
        source_files={"quantmesh/engine.py": _sha(code.read_bytes())},
        library_paths=[str(library)],
        notice_paths=[str(notice)],
    )
    manifest = tmp_path / "build.json"
    manifest.write_text(json.dumps(data))
    return SimpleNamespace(
        data=data,
        manifest=manifest,
        source=source,
        prefix=prefix,
        code=code,
        exe=exe,
        library=library,
        notice=notice,
        lock=lock,
        metadata=metadata,
        record=record,
        inventory=inventory,
    )


def _bind(sealed):
    sealed.manifest.write_text(json.dumps(sealed.data))
    return _sha(sealed.manifest.read_bytes())


def _runtime(api, sealed, monkeypatch):
    monkeypatch.setattr(
        api,
        "sys",
        SimpleNamespace(
            prefix=str(sealed.prefix),
            executable=str(sealed.exe),
            platform="linux",
            version="3.12.3 unit fixture",
            version_info=(3, 12, 3),
            dont_write_bytecode=True,
            modules={"quantmesh": SimpleNamespace(__file__=str(sealed.code))},
        ),
    )
    monkeypatch.setattr(api, "__file__", str(sealed.code))
    monkeypatch.setattr(api, "platform", SimpleNamespace(machine=lambda: "x86_64"))
    pins = [
        line.split(" --hash")[0].split("==")
        for line in sealed.lock.read_text().splitlines()
        if not line.startswith("#") and line.strip()
    ]

    class Dist:
        def __init__(self, name, version):
            self.metadata, self.version = {"Name": name}, version

        def read_text(self, name):
            path = sealed.prefix / name
            return path.read_text() if path.exists() else None

        @property
        def files(self):
            return [Path("METADATA"), Path("RECORD")]

        def locate_file(self, name):
            return sealed.prefix / name

    monkeypatch.setattr(api, "_distributions", lambda: [Dist(*pin) for pin in pins])


def test_actual_runtime_fields_without_git(sealed, monkeypatch):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    result = api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))
    assert set(result) == {
        "build_digest",
        "dependency_digest",
        "git_commit",
        "python_version",
        "python_executable_digest",
    }
    assert result["git_commit"] == "a" * 40
    assert result["python_version"] == "3.12.3 unit fixture"
    assert result["python_executable_digest"] == _sha(sealed.exe.read_bytes())
    assert not (sealed.source / ".git").exists()


@pytest.mark.parametrize("name", ["code", "exe", "library", "metadata", "record", "notice", "lock"])
def test_changed_actual_bytes_refuse(sealed, monkeypatch, name):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    binding = _bind(sealed)
    getattr(sealed, name).write_bytes(b"changed actual bytes")
    with pytest.raises(api.WorkerBuildRejected):
        api.measure_worker_runtime(sealed.manifest, manifest_sha256=binding)


@pytest.mark.parametrize("name", ["shadow.py", "shadow.so", "cache.pyc"])
def test_extra_executable_files_refuse(sealed, monkeypatch, name):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    (sealed.prefix / name).write_bytes(b"unadmitted")
    with pytest.raises(api.WorkerBuildRejected):
        api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))


@pytest.mark.parametrize(
    "change", ["runtime", "commit", "source", "prefix", "libraries", "notices"]
)
def test_bad_or_injected_manifest_refuses(sealed, monkeypatch, change):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    if change == "runtime":
        sealed.data["runtime"] = {"python_version": "saved host tuple"}
    elif change == "commit":
        sealed.data["source_commit"] = "invented HEAD"
    elif change == "source":
        sealed.data["source_files"] = {}
    elif change == "prefix":
        sealed.data["prefix"] = str(sealed.source)
    else:
        sealed.data[change[:-3] + "y_paths" if change == "libraries" else "notice_paths"] = []
    with pytest.raises(api.WorkerBuildRejected):
        api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))


def test_external_manifest_hash_required(sealed, monkeypatch):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    with pytest.raises(api.WorkerBuildRejected):
        api.measure_worker_runtime(sealed.manifest, manifest_sha256="0" * 64)


def test_json_duplicate_key_refuses(sealed, monkeypatch):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    raw = sealed.manifest.read_text().replace(
        '"schema_version": 1', '"schema_version": 1,"schema_version": 1'
    )
    sealed.manifest.write_text(raw)
    with pytest.raises(api.WorkerBuildRejected):
        api.measure_worker_runtime(
            sealed.manifest, manifest_sha256=_sha(sealed.manifest.read_bytes())
        )


def test_manifest_symlink_refuses(sealed, monkeypatch, tmp_path):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    link = tmp_path / "linked.json"
    try:
        link.symlink_to(sealed.manifest)
    except OSError:
        pytest.skip("OS does not permit fixture symlinks")
    with pytest.raises(api.WorkerBuildRejected):
        api.measure_worker_runtime(link, manifest_sha256=_bind(sealed))


def test_wrong_dependency_set_refuses(sealed, monkeypatch):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    monkeypatch.setattr(api, "_distributions", lambda: [])
    with pytest.raises(api.WorkerBuildRejected):
        api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))


def _reseal_inventory(sealed, *, links=None):
    data = json.loads(sealed.inventory.read_text())
    data["files"] = {
        str(p): _sha(p.read_bytes())
        for root in data["roots"]
        for p in Path(root).rglob("*")
        if p.is_file() and not p.is_symlink()
    }
    data["symlinks"] = links or {}
    sealed.inventory.write_text(json.dumps(data))
    sealed.data["inventory_sha256"] = _sha(sealed.inventory.read_bytes())


def test_empty_installer_inventory_file_is_valid(sealed, monkeypatch):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    (sealed.prefix / "REQUESTED").write_bytes(b"")
    _reseal_inventory(sealed)
    assert api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))


def test_source_alias_refuses_even_when_in_inventory(sealed, monkeypatch):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    alias = sealed.code.with_name("alias.py")
    try:
        alias.symlink_to(sealed.code.name)
    except OSError:
        pytest.skip("OS does not permit fixture symlinks")
    _reseal_inventory(sealed, links={str(alias): sealed.code.name})
    with pytest.raises(api.WorkerBuildRejected):
        api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))


def test_uninventoried_special_file_refuses(sealed, monkeypatch):
    import os

    if not hasattr(os, "mkfifo"):
        pytest.skip("POSIX special-file unit fixture")
    api = _api()
    _runtime(api, sealed, monkeypatch)
    os.mkfifo(sealed.prefix / "pipe")
    with pytest.raises(api.WorkerBuildRejected):
        api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))


def test_loaded_source_outside_admitted_tree_refuses(sealed, monkeypatch, tmp_path):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    api.sys.modules["quantmesh.other"] = SimpleNamespace(__file__=str(tmp_path / "other.py"))
    with pytest.raises(api.WorkerBuildRejected):
        api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))


@pytest.mark.parametrize("outside", ["metadata_root", "record_file"])
def test_dependency_origin_outside_inventory_refuses(sealed, monkeypatch, tmp_path, outside):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    distributions = list(api._distributions())
    original = distributions[0].locate_file
    distributions[0].locate_file = lambda name: (
        tmp_path / "outside"
        if (outside == "metadata_root" or str(name) == "RECORD")
        else original(name)
    )
    monkeypatch.setattr(api, "_distributions", lambda: distributions)
    with pytest.raises(api.WorkerBuildRejected):
        api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))


def test_symlink_loop_has_sanitized_rejection(sealed, monkeypatch):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    a, b = sealed.library.with_name("a"), sealed.library.with_name("b")
    try:
        a.symlink_to(b.name)
        b.symlink_to(a.name)
    except OSError:
        pytest.skip("OS does not permit fixture symlinks")
    _reseal_inventory(sealed, links={str(a): b.name, str(b): a.name})
    with pytest.raises(api.WorkerBuildRejected, match="^worker build rejected$"):
        api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))


def test_job_runner_manifest_branch_never_calls_git(sealed, monkeypatch):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    from quantmesh.research import job_runner

    def forbidden(*args, **kwargs):
        raise AssertionError("image fingerprint invoked Git")

    monkeypatch.setattr(job_runner.subprocess, "run", forbidden)
    result = job_runner.runtime_fingerprint(
        manifest_path=sealed.manifest,
        manifest_sha256=_bind(sealed),
    )
    assert result["git_commit"] == sealed.data["source_commit"]


@pytest.mark.parametrize("kind", ["python", "extension", "namespace", "package", "spec"])
def test_loaded_dependency_shadow_refuses(sealed, monkeypatch, tmp_path, kind):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    admitted = sealed.prefix / "numpy.py"
    admitted.write_bytes(b"ADMITTED = True\n")
    _reseal_inventory(sealed)
    external = tmp_path / "external"
    external.mkdir()
    shadow = external / ("numpy.so" if kind == "extension" else "numpy.py")
    shadow.write_bytes(b"EXTERNAL = True\n")
    module = SimpleNamespace(__file__=str(shadow))
    if kind == "namespace":
        module = SimpleNamespace(__path__=[str(external)])
    elif kind == "package":
        module = SimpleNamespace(__file__=str(admitted), __path__=[str(external)])
    elif kind == "spec":
        module = SimpleNamespace(
            __file__=str(admitted), __spec__=SimpleNamespace(origin=str(shadow))
        )
    api.sys.modules["numpy"] = module
    # Legitimate distribution metadata remains admitted throughout.
    with pytest.raises(api.WorkerBuildRejected, match="^worker build rejected$"):
        api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))


def test_loaded_admitted_dependency_and_builtin_pass(sealed, monkeypatch):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    package = sealed.prefix / "numpy"
    package.mkdir()
    code = package / "__init__.py"
    code.write_bytes(b"ADMITTED = True\n")
    _reseal_inventory(sealed)
    api.sys.modules["numpy"] = SimpleNamespace(
        __file__=str(code), __path__=[str(package)], __spec__=SimpleNamespace(origin=str(code))
    )
    api.sys.modules["sys"] = SimpleNamespace(__spec__=SimpleNamespace(origin="built-in"))
    api.sys.modules["not_imported"] = None
    assert api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))


def test_measured_source_main_entry_passes(sealed, monkeypatch):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    api.sys.modules["__main__"] = SimpleNamespace(
        __file__=str(sealed.code), __spec__=SimpleNamespace(origin=str(sealed.code))
    )
    assert api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))


def test_unmeasured_inline_main_refuses(sealed, monkeypatch):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    api.sys.modules["__main__"] = SimpleNamespace(__spec__=None)
    with pytest.raises(api.WorkerBuildRejected):
        api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))


def test_measured_base_stdlib_outside_venv_prefix_passes(sealed, monkeypatch):
    api = _api()
    _runtime(api, sealed, monkeypatch)
    package = sealed.library.parent / "stdlib_package"
    package.mkdir()
    code = package / "__init__.py"
    code.write_bytes(b"MEASURED_STDLIB = True\n")
    _reseal_inventory(sealed)
    api.sys.modules["stdlib_package"] = SimpleNamespace(
        __file__=str(code), __path__=[str(package)], __spec__=SimpleNamespace(origin=str(code))
    )
    assert api.measure_worker_runtime(sealed.manifest, manifest_sha256=_bind(sealed))
