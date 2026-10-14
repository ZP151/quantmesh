"""Software-contract tests; these never qualify a native Worker image."""

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from quantmesh.research.worker_admission import (
    WorkerAdmissionPins,
    WorkerAdmissionRejected,
    WorkerImageAdmission,
    _canonical,
    _metadata_text,
    _runtime_fingerprint,
    _verify_distribution_metadata,
)
from quantmesh.research.worker_build import parse_parent_binding
from quantmesh.research.worker_kernel import build_kernel_policy


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _pins(**changes):
    values = dict(
        engine_id="engine-id",
        image_id="sha256:" + "b" * 64,
        image_config_sha256="a" * 64,
        oci_manifest_sha256="b" * 64,
        oci_config_sha256="a" * 64,
        source_commit="c" * 40,
        manifest_sha256="d" * 64,
        inventory_sha256="e" * 64,
        runtime_metadata_sha256="f" * 64,
        dependency_lock_sha256="1" * 64,
        python_executable_sha256="2" * 64,
        entry_sha256="3" * 64,
        observer_sha256="4" * 64,
        expected_prefix="/usr/local",
        python_version="3.12.15 (frozen build) [GCC 12.2.0]",
        apparmor_name="qm-worker-9f7cdb6c9ce7b9c9516c",
        apparmor_sha256="5" * 64,
        seccomp_sha256="6" * 64,
        compiled_policy_sha256="7" * 64,
        docker_default_sha256="8" * 64,
        elf_map_sha256="9" * 64,
        kernel_profile_sha256="0" * 64,
    )
    values.update(changes)
    return WorkerAdmissionPins(**values)


def _snapshot():
    source = b"pinned source"
    rows = []
    files = {
        "/opt/quantmesh/quantmesh/research/fixture.py": _sha(source),
        "/usr/local/bin/python3.12": "2" * 64,
        "/usr/local/lib/libpython.so": "3" * 64,
        "/usr/share/doc/python/copyright": "4" * 64,
    }
    lock_lines = []
    raw_hashes = {}
    for index in range(81):
        name = "fixture" if index == 0 else f"dep{index:02d}"
        dist_info = f"{name}-1.0.dist-info"
        directory = f"/usr/local/lib/python3.12/site-packages/{dist_info}"
        metadata = f"Name: {name}\r\nVersion: 1.0\r\n\r\n".encode()
        record = f"{name} RECORD\r\n".encode()
        files[f"{directory}/METADATA"] = _sha(metadata)
        files[f"{directory}/RECORD"] = _sha(record)
        text_hashes = {
            "METADATA": _sha(f"Name: {name}\nVersion: 1.0\n\n".encode()),
            "RECORD": _sha(f"{name} RECORD\n".encode()),
            "direct_url.json": _sha(b""),
        }
        raw_hashes = {
            "METADATA": _sha(metadata),
            "RECORD": _sha(record),
            "direct_url.json": _sha(b""),
        }
        rows.append(
            {
                "name": name,
                "version": "1.0",
                "metadata_directory": directory,
                "text_sha256": text_hashes,
                "raw_sha256": raw_hashes,
            }
        )
        lock_lines.append(f"{name}==1.0 --hash=sha256:{index + 1:064x}")
    lock_raw = ("\n".join(lock_lines) + "\n").encode()
    files["/usr/local/requirements.lock"] = _sha(lock_raw)
    manifest = {
        "schema_version": 1,
        "source_commit": "c" * 40,
        "source_root": "/opt/quantmesh",
        "prefix": "/usr/local",
        "python_executable": "/usr/local/bin/python3",
        "lock_path": "/usr/local/requirements.lock",
        "inventory_path": "/opt/quantmesh/inventory.json",
        "inventory_sha256": "e" * 64,
        "source_files": {"quantmesh/research/fixture.py": _sha(source)},
        "library_paths": ["/usr/local/lib/libpython.so"],
        "notice_paths": ["/usr/share/doc/python/copyright"],
    }
    inventory = {
        "roots": [
            "/opt/quantmesh",
            "/usr/local",
            "/usr/lib/x86_64-linux-gnu",
            "/usr/share/doc",
        ],
        "files": files,
        "symlinks": {"/usr/local/bin/python3": "python3.12"},
    }
    runtime = {
        "schema_version": 1,
        "image_id": "sha256:" + "b" * 64,
        "python_version": "3.12.15 (frozen build) [GCC 12.2.0]",
        "python_executable_sha256": "2" * 64,
        "rows": rows,
    }
    return manifest, inventory, runtime, lock_raw


def test_fingerprint_is_recomputed_from_bound_source_and_metadata_bytes():
    pins = _pins()
    manifest, inventory, metadata, lock_raw = _snapshot()
    pins = _pins(dependency_lock_sha256=_sha(lock_raw))

    result = _runtime_fingerprint(manifest, inventory, metadata, lock_raw, pins)

    expected_build = _sha(_canonical(sorted(manifest["source_files"].items())))
    package_rows = [[row["name"], row["version"], row["text_sha256"]] for row in metadata["rows"]]
    expected_dependency = _sha(
        _canonical(
            {
                "packages": [
                    __import__("json").loads(value)
                    for value in sorted({_canonical(row) for row in package_rows})
                ],
                "python_version": pins.python_version,
                "python_executable_digest": pins.python_executable_sha256,
                "platform": "linux",
                "machine": "x86_64",
            }
        )
    )
    assert result == {
        "build_digest": expected_build,
        "dependency_digest": expected_dependency,
        "git_commit": pins.source_commit,
        "python_version": pins.python_version,
        "python_executable_digest": pins.python_executable_sha256,
    }


def test_fingerprint_refuses_raw_metadata_not_bound_by_image_inventory():
    manifest, inventory, metadata, lock_raw = _snapshot()
    pins = _pins(dependency_lock_sha256=_sha(lock_raw))
    metadata["rows"][0]["raw_sha256"]["METADATA"] = "b" * 64

    with pytest.raises(ValueError):
        _runtime_fingerprint(manifest, inventory, metadata, lock_raw, pins)


def test_fingerprint_refuses_source_association_outside_fixed_root():
    manifest, inventory, metadata, lock_raw = _snapshot()
    pins = _pins(dependency_lock_sha256=_sha(lock_raw))
    manifest["source_root"] = "/opt/quantmesh-untrusted"
    inventory["files"]["/opt/quantmesh-untrusted/quantmesh/research/fixture.py"] = inventory[
        "files"
    ].pop("/opt/quantmesh/quantmesh/research/fixture.py")

    with pytest.raises(ValueError):
        _runtime_fingerprint(manifest, inventory, metadata, lock_raw, pins)


def test_fingerprint_refuses_alternate_interpreter_symlink_target():
    manifest, inventory, metadata, lock_raw = _snapshot()
    pins = _pins(dependency_lock_sha256=_sha(lock_raw))
    inventory["symlinks"]["/usr/local/bin/python3"] = "python3.11"
    inventory["files"]["/usr/local/bin/python3.11"] = pins.python_executable_sha256

    with pytest.raises(ValueError):
        _runtime_fingerprint(manifest, inventory, metadata, lock_raw, pins)


def test_fingerprint_requires_lock_versions_to_match_installed_rows():
    manifest, inventory, metadata, lock_raw = _snapshot()
    pins = _pins(dependency_lock_sha256=_sha(lock_raw))
    metadata["rows"][0]["version"] = "2.0"

    with pytest.raises(ValueError):
        _runtime_fingerprint(manifest, inventory, metadata, lock_raw, pins)


def test_text_hash_uses_utf8_universal_newline_semantics():
    normalized, digest = _metadata_text(b"Name: fixture\r\nVersion: 1.0\r\n")

    assert normalized == "Name: fixture\nVersion: 1.0\n"
    assert digest == _sha(normalized.encode())


@pytest.mark.skipif(
    os.name != "posix" or os.getuid() != 1000, reason="private snapshot owner contract"
)
def test_metadata_snapshot_recomputes_hashes_from_actual_files(tmp_path):
    raw_metadata = b"Name: fixture\r\nVersion: 1.0\r\n"
    raw_record = b"fixture RECORD\r\n"
    directory = "/usr/local/lib/python3.12/site-packages/fixture-1.0.dist-info"
    root = tmp_path / "snapshot"
    metadata = root / "metadata"
    package = metadata / "fixture-1.0.dist-info"
    package.mkdir(parents=True, mode=0o700)
    metadata.chmod(0o700)
    root.chmod(0o700)
    (package / "METADATA").write_bytes(raw_metadata)
    (package / "RECORD").write_bytes(raw_record)
    (package / "METADATA").chmod(0o400)
    (package / "RECORD").chmod(0o400)
    _, text_metadata_hash = _metadata_text(raw_metadata)
    _, text_record_hash = _metadata_text(raw_record)
    row = {
        "name": "fixture",
        "version": "1.0",
        "metadata_directory": directory,
        "text_sha256": {
            "METADATA": text_metadata_hash,
            "RECORD": text_record_hash,
            "direct_url.json": _sha(b""),
        },
        "raw_sha256": {
            "METADATA": _sha(raw_metadata),
            "RECORD": _sha(raw_record),
            "direct_url.json": _sha(b""),
        },
    }

    _verify_distribution_metadata(
        root,
        {"rows": [row]},
        {
            f"{directory}/METADATA": _sha(raw_metadata),
            f"{directory}/RECORD": _sha(raw_record),
        },
    )

    row["text_sha256"]["METADATA"] = _sha(b"tampered")
    with pytest.raises(Exception):
        _verify_distribution_metadata(
            root,
            {"rows": [row]},
            {
                f"{directory}/METADATA": _sha(raw_metadata),
                f"{directory}/RECORD": _sha(raw_record),
            },
        )


def test_pins_reject_noncanonical_image_and_unexpected_prefix():
    with pytest.raises(Exception):
        _pins(image_id="sha256:" + "f" * 64)
    with pytest.raises(Exception):
        _pins(expected_prefix="/usr")


def test_live_image_rebinds_current_raw_oci_and_refuses_engine_drift(monkeypatch):
    import quantmesh.research.worker_admission as admission

    config_raw = json.dumps(
        {
            "architecture": "amd64",
            "os": "linux",
            "config": {
                "User": "10001:10001",
                "Entrypoint": ["/usr/local/bin/python3"],
                "Cmd": ["-B", "-I", "-S", "/opt/quantmesh/worker_entry.py"],
            },
            "rootfs": {"type": "layers", "diff_ids": ["sha256:" + "d" * 64]},
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    config_digest = _sha(config_raw)
    manifest_raw = json.dumps(
        {
            "schemaVersion": 2,
            "config": {"digest": f"sha256:{config_digest}", "size": len(config_raw)},
            "layers": [{"digest": "sha256:" + "d" * 64, "size": 10}],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    manifest_digest = _sha(manifest_raw)
    pins = _pins(
        image_id=f"sha256:{manifest_digest}",
        image_config_sha256=config_digest,
        oci_config_sha256=config_digest,
        oci_manifest_sha256=manifest_digest,
    )
    content = {manifest_digest: manifest_raw, config_digest: config_raw}

    class Profile:
        def __init__(self, engine_id="engine-id"):
            self.engine_id = engine_id
            self.invoked = False

        def prerequisites(self):
            return {"engine_id": self.engine_id, "image_id": pins.image_id}

        def invoke(self, argv):
            self.invoked = True
            assert argv == ["image", "inspect", pins.image_id]
            return json.dumps(
                [
                    {
                        "Id": pins.image_id,
                        "Os": "linux",
                        "Config": {
                            "User": "10001:10001",
                            "Entrypoint": ["/usr/local/bin/python3"],
                            "Cmd": ["-B", "-I", "-S", "/opt/quantmesh/worker_entry.py"],
                        },
                        "RootFS": {"Layers": ["sha256:" + "d" * 64]},
                    }
                ]
            )

    monkeypatch.setattr(
        admission,
        "_read_absolute_regular",
        lambda path, _maximum: content[path.name],
    )
    provider = WorkerImageAdmission(pins, Path("/unused/software-test-only"))
    profile = Profile()
    provider._live_image(profile)
    assert profile.invoked

    wrong_engine = Profile(engine_id="different-engine")
    with pytest.raises(WorkerAdmissionRejected):
        provider._live_image(wrong_engine)
    assert not wrong_engine.invoked

    content[config_digest] = b'{"architecture":"arm64","os":"linux"}'
    with pytest.raises(WorkerAdmissionRejected):
        provider._live_image(profile)


def test_live_policy_recomputes_expected_bytes_and_refuses_policy_drift(monkeypatch, tmp_path):
    import quantmesh.research.worker_admission as admission

    elf_files = {
        "/usr/local/bin/python3": "a" * 64,
        "/usr/local/bin/python3.12": "a" * 64,
        "/usr/lib/x86_64-linux-gnu/libc.so.6": "b" * 64,
    }
    default = json.dumps(
        {
            "defaultAction": "SCMP_ACT_ERRNO",
            "defaultErrnoRet": 1,
            "syscalls": [{"names": ["read", "write"], "action": "SCMP_ACT_ALLOW"}],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    default_digest = _sha(default)
    expected = build_kernel_policy(
        elf_files, docker_default=default, docker_default_sha256=default_digest
    )
    compiled = b"compiled policy metadata"
    pins = _pins(
        apparmor_name=expected.name,
        apparmor_sha256=_sha(expected.apparmor),
        seccomp_sha256=_sha(expected.seccomp),
        compiled_policy_sha256=_sha(compiled),
        docker_default_sha256=default_digest,
        elf_map_sha256="9" * 64,
        kernel_profile_sha256=expected.sha256,
    )
    seccomp_path = tmp_path / "seccomp.json"
    seccomp_path.write_bytes(expected.seccomp)
    provider = WorkerImageAdmission(pins, tmp_path)
    profile = SimpleNamespace(apparmor_profile=expected.name, seccomp_path=seccomp_path)
    data = {
        "elf-map.json": _canonical(elf_files),
        "docker-default.json": default,
        "policy.apparmor": expected.apparmor,
        "policy.seccomp.json": expected.seccomp,
        "policy.compiled": compiled,
    }
    loaded = (compiled, "v5")
    monkeypatch.setattr(admission, "_read_loaded_apparmor", lambda _name: loaded)
    provider._live_policy(profile, data)
    data["policy.apparmor"] += b"# drift\n"
    with pytest.raises(WorkerAdmissionRejected):
        provider._live_policy(profile, data)
    data["policy.apparmor"] = expected.apparmor
    loaded = (compiled + b"drift", "v5")
    with pytest.raises(WorkerAdmissionRejected):
        provider._live_policy(profile, data)


def test_parent_binding_uses_exact_ready_and_current_process_identity(monkeypatch):
    import quantmesh.research.worker_admission as admission

    pins = _pins()
    runtime = {
        "build_digest": "a" * 64,
        "dependency_digest": "b" * 64,
        "git_commit": pins.source_commit,
        "python_version": pins.python_version,
        "python_executable_digest": pins.python_executable_sha256,
    }
    profile = SimpleNamespace(uid=10001, gid=10001)
    evidence = {
        "engine_id": pins.engine_id,
        "limits": {
            "memory.max": "805306368",
            "memory.swap.max": "0",
            "cpu.max": "100000 100000",
            "pids.max": "128",
        },
        "bootstrap_sha256": "c" * 64,
    }
    document = {"Id": "d" * 64, "State": {"Pid": 44, "Running": True}}

    class Process:
        def __init__(self):
            self.container_id = "d" * 64
            self.nonce = "e" * 32
            self.evidence = evidence
            self.profile = profile

        def _inspect(self, *, check_parent_binding=False):
            assert check_parent_binding is False
            return document

    process = Process()
    job = SimpleNamespace(request=SimpleNamespace(budget=SimpleNamespace(memory_mib=768)))
    ready = {"event": "ready", "limits": evidence["limits"], "bootstrap_sha256": "c" * 64}
    identity = {
        "identity": (44, "123"),
        "uids": (10001, 10001, 10001, 10001),
        "gids": (10001, 10001, 10001, 10001),
        "nnp": 1,
        "seccomp": 2,
        "cap_eff": 0,
        "cgroup": "0::/worker\n",
        "mountinfo": b"software-only mocked mount observation",
        "apparmor_current": f"{pins.apparmor_name} (enforce)",
    }
    monkeypatch.setattr(WorkerImageAdmission, "verify", lambda self, _profile: runtime)
    monkeypatch.setattr(admission, "_proc_identity", lambda _pid: identity)
    monkeypatch.setattr(admission, "_verify_cgroup", lambda _raw, _memory: None)
    monkeypatch.setattr(admission, "verify_mountinfo", lambda _raw: None)

    provider = WorkerImageAdmission(pins, Path("/unused/software-test-only"))
    raw, digest = provider.prepare_parent_binding(process, job, runtime, ready)
    parsed = parse_parent_binding(raw, expected_sha256=digest)
    assert parsed.container_id == process.container_id
    assert parsed.owner_nonce == process.nonce
    assert parsed.python_version == "3.12.15"

    forged = {**ready, "bootstrap_sha256": "f" * 64}
    with pytest.raises(WorkerAdmissionRejected):
        provider.prepare_parent_binding(process, job, runtime, forged)

    for bad_profile in (
        SimpleNamespace(uid=0, gid=10001),
        SimpleNamespace(uid=10001, gid=0),
    ):
        process.profile = bad_profile
        with pytest.raises(WorkerAdmissionRejected):
            provider.prepare_parent_binding(process, job, runtime, ready)
    process.profile = profile

    bad_label = {**identity, "apparmor_current": "unconfined"}
    monkeypatch.setattr(admission, "_proc_identity", lambda _pid: bad_label)
    with pytest.raises(WorkerAdmissionRejected):
        provider.prepare_parent_binding(process, job, runtime, ready)

    state_with_gids = identity
    changing = iter(
        [
            state_with_gids,
            {**state_with_gids, "nnp": 0},
        ]
    )
    monkeypatch.setattr(admission, "_proc_identity", lambda _pid: next(changing))
    with pytest.raises(WorkerAdmissionRejected):
        provider.prepare_parent_binding(process, job, runtime, ready)

    changing = iter(
        [
            state_with_gids,
            {**state_with_gids, "mountinfo": b"changed after read"},
        ]
    )
    monkeypatch.setattr(admission, "_proc_identity", lambda _pid: next(changing))
    with pytest.raises(WorkerAdmissionRejected):
        provider.prepare_parent_binding(process, job, runtime, ready)
