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
    _read_snapshot_member,
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


def _snapshot(lock_raw=None):
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
    selection = (
        [
            line.split(" --hash")[0].split("==")
            for line in lock_raw.decode().splitlines()
            if line and not line.startswith("#")
        ]
        if lock_raw is not None
        else [("fixture" if index == 0 else f"dep{index:02d}", "1.0") for index in range(81)]
    )
    for index, (name, version) in enumerate(selection):
        dist_info = f"{name}-{version}.dist-info"
        directory = f"/usr/local/lib/python3.12/site-packages/{dist_info}"
        metadata = f"Name: {name}\r\nVersion: {version}\r\n\r\n".encode()
        record = f"{name} RECORD\r\n".encode()
        files[f"{directory}/METADATA"] = _sha(metadata)
        files[f"{directory}/RECORD"] = _sha(record)
        text_hashes = {
            "METADATA": _sha(f"Name: {name}\nVersion: {version}\n\n".encode()),
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
                "version": version,
                "metadata_directory": directory,
                "text_sha256": text_hashes,
                "raw_sha256": raw_hashes,
            }
        )
        lock_lines.append(f"{name}=={version} --hash=sha256:{index + 1:064x}")
    if lock_raw is None:
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


def _private_admission_snapshot(tmp_path):
    import quantmesh.research.worker_admission as admission

    root = tmp_path / "snapshot"
    root.mkdir(mode=0o700)
    (root / "metadata").mkdir(mode=0o700)
    (root / "empty-config").mkdir(mode=0o700)
    digests = {}
    for field, (filename, _) in admission._SNAPSHOTS.items():
        raw = f"private snapshot member: {filename}".encode()
        digests[field] = _sha(raw)
        (root / filename).write_bytes(raw)
        (root / filename).chmod(0o400)
    (root / "receipt.json").write_bytes(b"{}")
    (root / "receipt.json").chmod(0o600)
    digests["image_config_sha256"] = digests["oci_config_sha256"]
    digests["image_id"] = f"sha256:{digests['oci_manifest_sha256']}"
    provider = WorkerImageAdmission(_pins(**digests), root)
    return provider, root


def _simulate_snapshot_owner_uid(monkeypatch, uid=10001, *, foreign_inode=None):
    """Map only stat-result UIDs while preserving descriptor/name identity."""
    import quantmesh.research.worker_admission as admission

    real_stat = os.stat
    real_fstat = os.fstat

    def map_uid(info):
        mapped_uid = uid
        if foreign_inode == (info.st_dev, info.st_ino):
            mapped_uid = uid + 1
        return SimpleNamespace(
            st_dev=info.st_dev,
            st_ino=info.st_ino,
            st_mode=info.st_mode,
            st_nlink=info.st_nlink,
            st_size=info.st_size,
            st_mtime_ns=info.st_mtime_ns,
            st_ctime_ns=info.st_ctime_ns,
            st_uid=mapped_uid,
            st_gid=info.st_gid,
        )

    def mapped_stat(path, *args, **kwargs):
        return map_uid(real_stat(path, *args, **kwargs))

    def mapped_fstat(fd):
        return map_uid(real_fstat(fd))

    monkeypatch.setattr(admission.os, "getuid", lambda: uid)
    monkeypatch.setattr(admission.os, "geteuid", lambda: uid)
    monkeypatch.setattr(admission.os, "stat", mapped_stat)
    monkeypatch.setattr(admission.os, "fstat", mapped_fstat)


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


@pytest.mark.parametrize(
    "fault", [None, "parent_lock", "old_certifi", "other_version", "stale_record", "80", "82"]
)
def test_secure_child_metadata_requires_matching_parent_and_installed81(fault):
    secure = Path(__file__).parents[1] / "services/research_agent/requirements.linux-cp312.lock"
    raw = secure.read_bytes()
    assert _sha(raw) == "0de42c60394ad96a6a052b1e24a8cb88f14c87f0690b3b1e2467bf857afb7ea6"
    manifest, inventory, metadata, lock_raw = _snapshot(raw)
    pins = _pins(dependency_lock_sha256=_sha(raw))
    assert _runtime_fingerprint(manifest, inventory, metadata, lock_raw, pins)
    if fault is None:
        assert len(metadata["rows"]) == 81
        assert (
            next(row for row in metadata["rows"] if row["name"] == "certifi")["version"]
            == "2026.10.19"
        )
        return
    if fault == "parent_lock":
        pins = _pins(
            dependency_lock_sha256="07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a"
        )
    elif fault in {"old_certifi", "other_version"}:
        name = "certifi" if fault == "old_certifi" else "anyio"
        row = next(row for row in metadata["rows"] if row["name"] == name)
        row["version"] = "2026.7.22" if fault == "old_certifi" else "0.0.0"
    elif fault == "stale_record":
        row = next(row for row in metadata["rows"] if row["name"] == "certifi")
        inventory["files"][row["metadata_directory"] + "/RECORD"] = "0" * 64
    elif fault == "80":
        metadata["rows"].pop()
    else:
        import copy

        extra = copy.deepcopy(metadata["rows"][0])
        extra["name"] = "extra-fixed"
        metadata["rows"].append(extra)
    with pytest.raises(ValueError):
        _runtime_fingerprint(manifest, inventory, metadata, lock_raw, pins)


@pytest.mark.skipif(
    os.name != "posix" or os.getuid() == 0,
    reason="private metadata uses real nonroot POSIX ownership",
)
@pytest.mark.parametrize("fault", [None, "80", "82", "record_bytes"])
def test_secure81_physical_metadata_tree_refuses_missing_extra_or_stale_members(tmp_path, fault):
    secure = Path(__file__).parents[1] / "services/research_agent/requirements.linux-cp312.lock"
    raw = secure.read_bytes()
    assert _sha(raw) == "0de42c60394ad96a6a052b1e24a8cb88f14c87f0690b3b1e2467bf857afb7ea6"
    manifest, inventory, metadata, lock_raw = _snapshot(raw)
    pins = _pins(dependency_lock_sha256=_sha(raw))
    assert _runtime_fingerprint(manifest, inventory, metadata, lock_raw, pins)
    root = tmp_path / "secure-snapshot"
    root.mkdir(mode=0o700)
    directory = root / "metadata"
    directory.mkdir(mode=0o700)
    for row in metadata["rows"]:
        package = directory / Path(row["metadata_directory"]).name
        package.mkdir(mode=0o700)
        members = {
            "METADATA": f"Name: {row['name']}\r\nVersion: {row['version']}\r\n\r\n".encode(),
            "RECORD": f"{row['name']} RECORD\r\n".encode(),
        }
        for name, body in members.items():
            assert _sha(body) == row["raw_sha256"][name]
            path = package / name
            path.write_bytes(body)
            path.chmod(0o400)
    assert len(list(directory.iterdir())) == 81
    # The real metadata reader verifies actual bytes, names, versions and ownership.
    _verify_distribution_metadata(root, metadata, inventory["files"])
    if fault is None:
        return
    if fault == "80":
        package = directory / Path(metadata["rows"][0]["metadata_directory"]).name
        package.rename(root / "retained-missing.dist-info")
        assert len(list(directory.iterdir())) == 80
    elif fault == "82":
        package = directory / "extra-fixed-1.0.dist-info"
        package.mkdir(mode=0o700)
        for name, body in {
            "METADATA": b"Name: extra-fixed\r\nVersion: 1.0\r\n",
            "RECORD": b"extra-fixed RECORD\r\n",
        }.items():
            path = package / name
            path.write_bytes(body)
            path.chmod(0o400)
        assert len(list(directory.iterdir())) == 82
    else:
        row = next(row for row in metadata["rows"] if row["name"] == "certifi")
        record = directory / Path(row["metadata_directory"]).name / "RECORD"
        record.chmod(0o600)
        record.write_bytes(b"changed physical RECORD\r\n")
        record.chmod(0o400)
        assert len(list(directory.iterdir())) == 81
    with pytest.raises(WorkerAdmissionRejected, match="^worker_admission_failed$"):
        _verify_distribution_metadata(root, metadata, inventory["files"])


def test_text_hash_uses_utf8_universal_newline_semantics():
    normalized, digest = _metadata_text(b"Name: fixture\r\nVersion: 1.0\r\n")

    assert normalized == "Name: fixture\nVersion: 1.0\n"
    assert digest == _sha(normalized.encode())


def test_kernel_namespace_link_rejects_ordinary_filesystem_targets():
    import stat
    from types import SimpleNamespace

    import quantmesh.research.worker_admission as admission

    kernel = SimpleNamespace(st_mode=stat.S_IFLNK | 0o444, st_uid=0, st_gid=0)
    assert admission._is_kernel_namespace_link(kernel, "apparmorfs:[152]")
    for target in ("/tmp/injected", "../policy", "apparmorfs:[152]/../other", "apparmorfs:[x]"):
        assert not admission._is_kernel_namespace_link(kernel, target)
    user = SimpleNamespace(st_mode=kernel.st_mode, st_uid=1000, st_gid=0)
    writable = SimpleNamespace(st_mode=stat.S_IFLNK | 0o777, st_uid=0, st_gid=0)
    assert not admission._is_kernel_namespace_link(user, "apparmorfs:[152]")
    assert not admission._is_kernel_namespace_link(writable, "apparmorfs:[152]")


def test_kernel_raw_policy_references_only_address_the_held_namespace():
    import stat
    from types import SimpleNamespace

    import quantmesh.research.worker_admission as admission

    info = SimpleNamespace(st_mode=stat.S_IFLNK | 0o444, st_uid=0, st_gid=0)
    for field, filename in {
        "raw_abi": "abi",
        "raw_data": "raw_data",
        "raw_sha256": "sha256",
    }.items():
        assert (
            admission._kernel_policy_revision(info, field, f"../../raw_data/124/{filename}")
            == "124"
        )
    for target in ("/tmp/abi", "../../raw_data/124/../abi", "../../raw_data/124/sha256"):
        with pytest.raises(WorkerAdmissionRejected):
            admission._kernel_policy_revision(info, "raw_abi", target)


@pytest.mark.skipif(os.name != "posix", reason="inherited policy descriptors are POSIX-only")
@pytest.mark.parametrize(
    "case",
    [
        "success",
        "ordinary_success",
        "non_eacces",
        "foreign_matching",
        "wrong_inode",
        "writable",
        "postread_writable",
        "nonregular",
        "missing",
        "o_path",
        "abi_eacces",
        "pread_error",
        "overflow",
        "changed_identity",
        "changed_revision",
    ],
)
def test_kernel_policy_fd_fallback_is_bounded_and_fails_closed(tmp_path, monkeypatch, case):
    import concurrent.futures
    import errno
    import fcntl
    import stat

    import quantmesh.research.worker_admission as admission

    raw = (
        b"x" * (admission._MAX_POLICY + 1)
        if case == "overflow"
        else b"kernel policy bytes from the live descriptor" * 97
    )
    wrong_path = tmp_path / "other-policy"
    if case == "wrong_inode":
        wrong_path.write_bytes(raw)
    revision = tmp_path / "namespace" / "raw_data" / "124"
    profile = tmp_path / "profile"
    revision.mkdir(parents=True)
    profile.mkdir()
    (revision / "raw_data").write_bytes(raw)
    (revision / "abi").write_text("v5\n", encoding="ascii")
    (revision / "sha256").write_text(_sha(raw) + "\n", encoding="ascii")
    for member, target in (
        ("raw_data", "../../raw_data/124/raw_data"),
        ("raw_abi", "../../raw_data/124/abi"),
        ("raw_sha256", "../../raw_data/124/sha256"),
    ):
        (profile / member).symlink_to(target)

    real_open = os.open
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    namespace_fd = real_open(tmp_path / "namespace", flags)
    profile_fd = real_open(profile, flags)
    revision_fd = real_open(revision, flags)
    source_fd = real_open(revision / "raw_data", os.O_RDONLY)
    extra_fds = []
    try:
        try:
            saved_fd3 = os.dup(3)
        except OSError:
            saved_fd3 = None
        os.dup2(source_fd, 3)
        raw_identity = os.stat(revision / "raw_data")
        fixture_paths = [
            tmp_path / "namespace",
            tmp_path / "namespace" / "raw_data",
            revision,
            revision / "raw_data",
            revision / "abi",
            revision / "sha256",
            profile,
            profile / "raw_data",
            profile / "raw_abi",
            profile / "raw_sha256",
        ]
        if case == "wrong_inode":
            fixture_paths.append(wrong_path)
        fixture_inodes = {
            (info.st_dev, info.st_ino)
            for path in fixture_paths
            for info in (os.stat(path, follow_symlinks=False),)
        }
        raw_inode = (raw_identity.st_dev, raw_identity.st_ino)
        revision_identity = os.fstat(revision_fd)
        revision_inode = (revision_identity.st_dev, revision_identity.st_ino)
        real_stat = os.stat
        real_fstat = os.fstat
        real_pread = os.pread
        pread_calls = []

        def mapped(info):
            if (info.st_dev, info.st_ino) not in fixture_inodes:
                return info
            mode = info.st_mode
            if stat.S_ISLNK(mode):
                mode = stat.S_IFLNK | 0o444
            return type(
                "KernelStat",
                (),
                {
                    key: (
                        1000
                        if key == "st_uid"
                        and case == "foreign_matching"
                        and (info.st_dev, info.st_ino) == raw_inode
                        else 0
                        if key in {"st_uid", "st_gid"}
                        else 0
                        if key == "st_size" and (info.st_dev, info.st_ino) == raw_inode
                        else mode
                        if key == "st_mode"
                        else getattr(info, key)
                    )
                    for key in (
                        "st_dev",
                        "st_ino",
                        "st_mode",
                        "st_nlink",
                        "st_size",
                        "st_mtime_ns",
                        "st_ctime_ns",
                        "st_uid",
                        "st_gid",
                    )
                },
            )()

        def mapped_stat(path, *args, **kwargs):
            return mapped(real_stat(path, *args, **kwargs))

        def mapped_fstat(fd):
            return mapped(real_fstat(fd))

        def denied_raw_open(path, open_flags, *args, **kwargs):
            if (
                path == "raw_data" or (case == "abi_eacces" and path == "abi")
            ) and "dir_fd" in kwargs:
                parent = real_fstat(kwargs["dir_fd"])
                if (parent.st_dev, parent.st_ino) == revision_inode:
                    if case == "ordinary_success" and path == "raw_data":
                        return real_open(path, open_flags, *args, **kwargs)
                    if case == "abi_eacces" and path == "abi":
                        raise PermissionError(errno.EACCES, "permission denied")
                    number = errno.EPERM if case == "non_eacces" else errno.EACCES
                    raise PermissionError(number, "permission denied")
            return real_open(path, open_flags, *args, **kwargs)

        def partial_pread(fd, count, offset):
            pread_calls.append(offset)
            if case == "pread_error":
                raise OSError(errno.EIO, "read failed")
            if case == "changed_identity" and len(pread_calls) == 1:
                (revision / "raw_data").rename(revision / "raw_data.old")
                (revision / "raw_data").write_bytes(raw)
            if case == "changed_revision" and len(pread_calls) == 1:
                (profile / "raw_data").unlink()
                (profile / "raw_data").symlink_to("../../raw_data/125/raw_data")
            if case == "postread_writable" and len(pread_calls) == 1:
                os.dup2(extra_fds[-1], 3)
            return real_pread(fd, count if case == "overflow" else min(count, 13), offset)

        monkeypatch.setattr(admission.os, "open", denied_raw_open)
        monkeypatch.setattr(admission.os, "stat", mapped_stat)
        monkeypatch.setattr(admission.os, "fstat", mapped_fstat)
        monkeypatch.setattr(admission.os, "pread", partial_pread)

        if case == "wrong_inode":
            extra_fds.append(real_open(wrong_path, os.O_RDONLY))
            os.dup2(extra_fds[-1], 3)
        elif case == "writable":
            extra_fds.append(real_open(revision / "raw_data", os.O_RDWR))
            os.dup2(extra_fds[-1], 3)
        elif case == "postread_writable":
            extra_fds.append(real_open(revision / "raw_data", os.O_RDWR))
        elif case == "nonregular":
            read_end, write_end = os.pipe()
            extra_fds.extend((read_end, write_end))
            os.dup2(read_end, 3)
        elif case == "missing":
            os.close(3)
        elif case == "o_path":
            if not hasattr(os, "O_PATH"):
                pytest.skip("O_PATH is Linux-specific")
            extra_fds.append(real_open(revision / "raw_data", os.O_PATH))
            os.dup2(extra_fds[-1], 3)

        if case == "abi_eacces":
            assert fcntl.fcntl(3, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
            assert stat.S_ISREG(real_fstat(3).st_mode)
            assert mapped(real_fstat(3)).st_uid == 0
            with pytest.raises(WorkerAdmissionRejected):
                admission._read_kernel_member(revision_fd, "abi", 32)
            assert not pread_calls
        elif case in {"success", "ordinary_success"}:
            if case == "success":
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(
                        pool.map(
                            lambda _: admission._read_kernel_policy_bytes(profile_fd, namespace_fd),
                            range(2),
                        )
                    )
            else:
                results = [admission._read_kernel_policy_bytes(profile_fd, namespace_fd)]
            assert all(result == (raw, "v5", _sha(raw)) for result in results)
            if case == "success":
                assert len(results) == 2
                assert pread_calls
            else:
                assert not pread_calls
            assert fcntl.fcntl(3, fcntl.F_GETFL) & os.O_ACCMODE == os.O_RDONLY
            assert os.lseek(3, 0, os.SEEK_CUR) == 0
            assert stat.S_ISREG(real_fstat(3).st_mode)
        else:
            with pytest.raises(WorkerAdmissionRejected):
                admission._read_kernel_policy_bytes(profile_fd, namespace_fd)
            if case in {
                "non_eacces",
                "foreign_matching",
                "wrong_inode",
                "writable",
                "nonregular",
                "missing",
                "o_path",
                "abi_eacces",
            }:
                assert not pread_calls
            elif case == "pread_error":
                assert len(pread_calls) == 1
            elif case == "overflow":
                assert pread_calls
                assert pread_calls[-1] == admission._MAX_POLICY
            elif case in {"changed_identity", "changed_revision", "postread_writable"}:
                assert pread_calls
        for descriptor in extra_fds:
            os.close(descriptor)
        extra_fds.clear()
    finally:
        for descriptor in extra_fds:
            os.close(descriptor)
        os.close(source_fd)
        os.close(revision_fd)
        os.close(profile_fd)
        os.close(namespace_fd)
        try:
            os.close(3)
        except OSError:
            pass
        if saved_fd3 is not None:
            os.dup2(saved_fd3, 3)
            os.close(saved_fd3)


@pytest.mark.skipif(
    os.name != "posix" or os.getuid() == 0, reason="private snapshot owner contract"
)
def test_metadata_snapshot_recomputes_hashes_from_actual_files(tmp_path, monkeypatch):
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

    owner_uid = root.stat().st_uid
    monkeypatch.setattr(os, "getuid", lambda: owner_uid + 1)
    monkeypatch.setattr(os, "geteuid", lambda: owner_uid + 1)
    with pytest.raises(WorkerAdmissionRejected):
        _verify_distribution_metadata(
            root,
            {"rows": [row]},
            {
                f"{directory}/METADATA": _sha(raw_metadata),
                f"{directory}/RECORD": _sha(raw_record),
            },
        )
    monkeypatch.setattr(os, "getuid", lambda: owner_uid)
    monkeypatch.setattr(os, "geteuid", lambda: owner_uid)

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


@pytest.mark.skipif(
    os.name != "posix" or os.getuid() == 0,
    reason="snapshot members require POSIX descriptor semantics",
)
def test_snapshot_member_accepts_current_nonroot_process_uid(tmp_path):
    root = tmp_path / "snapshot-member"
    root.mkdir(mode=0o700)
    member = root / "metadata.json"
    member.write_bytes(b"private metadata")
    member.chmod(0o400)
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        assert _read_snapshot_member(directory_fd, member.name, 4096) == b"private metadata"
    finally:
        os.close(directory_fd)


@pytest.mark.skipif(os.name != "posix", reason="POSIX snapshot descriptor semantics")
def test_snapshot_and_distribution_metadata_accept_simulated_uid_10001(tmp_path, monkeypatch):
    import quantmesh.research.worker_admission as admission

    provider, root = _private_admission_snapshot(tmp_path)
    raw_metadata = b"Name: fixture\r\nVersion: 1.0\r\n"
    raw_record = b"fixture RECORD\r\n"
    package = root / "metadata" / "fixture-1.0.dist-info"
    package.mkdir(mode=0o700)
    (package / "METADATA").write_bytes(raw_metadata)
    (package / "RECORD").write_bytes(raw_record)
    for member in package.iterdir():
        member.chmod(0o400)
    _, text_metadata_hash = _metadata_text(raw_metadata)
    _, text_record_hash = _metadata_text(raw_record)
    directory = "/usr/local/lib/python3.12/site-packages/fixture-1.0.dist-info"
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
    files = {
        f"{directory}/METADATA": _sha(raw_metadata),
        f"{directory}/RECORD": _sha(raw_record),
    }

    _simulate_snapshot_owner_uid(monkeypatch)

    assert provider._snapshot()
    admission._verify_distribution_metadata(root, {"rows": [row]}, files)


@pytest.mark.parametrize("process_uid", [0, "foreign"])
@pytest.mark.skipif(
    os.name != "posix", reason="snapshot members require POSIX descriptor semantics"
)
def test_snapshot_member_rejects_root_and_foreign_process_uids(tmp_path, monkeypatch, process_uid):
    import quantmesh.research.worker_admission as admission

    root = tmp_path / "snapshot-member"
    root.mkdir(mode=0o700)
    member = root / "metadata.json"
    member.write_bytes(b"private metadata")
    member.chmod(0o400)
    owner_uid = member.stat().st_uid
    actual_process_uid = 0 if process_uid == 0 else owner_uid + 1
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        monkeypatch.setattr(admission.os, "getuid", lambda: actual_process_uid)
        monkeypatch.setattr(admission.os, "geteuid", lambda: actual_process_uid)
        with pytest.raises(WorkerAdmissionRejected):
            _read_snapshot_member(directory_fd, member.name, 4096)
    finally:
        os.close(directory_fd)


@pytest.mark.skipif(
    os.name != "posix" or os.getuid() == 0,
    reason="private snapshot owner contract is POSIX-only",
)
def test_snapshot_accepts_current_nonroot_process_uid(tmp_path):
    provider, _ = _private_admission_snapshot(tmp_path)
    assert provider._snapshot()


@pytest.mark.parametrize("process_uid", [0, "foreign"])
@pytest.mark.skipif(os.name != "posix", reason="private snapshot owner contract is POSIX-only")
def test_snapshot_rejects_root_or_foreign_process_uid(tmp_path, monkeypatch, process_uid):
    import quantmesh.research.worker_admission as admission

    provider, root = _private_admission_snapshot(tmp_path)
    owner_uid = root.stat().st_uid

    process_uid = 0 if process_uid == 0 else owner_uid + 1
    monkeypatch.setattr(admission.os, "getuid", lambda: process_uid)
    monkeypatch.setattr(admission.os, "geteuid", lambda: process_uid)
    with pytest.raises(WorkerAdmissionRejected):
        provider._snapshot()


@pytest.mark.parametrize(
    "component", ["root", "empty-config", "metadata", "package", "snapshot-member"]
)
@pytest.mark.skipif(os.name != "posix", reason="POSIX snapshot descriptor semantics")
def test_snapshot_rejects_a_single_foreign_component_owner(tmp_path, monkeypatch, component):
    import quantmesh.research.worker_admission as admission

    provider, root = _private_admission_snapshot(tmp_path)
    package = root / "metadata" / "fixture-1.0.dist-info"
    package.mkdir(mode=0o700)
    (package / "METADATA").write_bytes(b"Name: fixture\nVersion: 1.0\n")
    (package / "RECORD").write_bytes(b"fixture RECORD\n")
    for member in package.iterdir():
        member.chmod(0o400)
    target = {
        "root": root,
        "empty-config": root / "empty-config",
        "metadata": root / "metadata",
        "package": package,
        "snapshot-member": root / "oci-manifest.json",
    }[component]
    info = os.stat(target, follow_symlinks=False)
    _simulate_snapshot_owner_uid(monkeypatch, foreign_inode=(info.st_dev, info.st_ino))

    if component == "package":
        raw_metadata = b"Name: fixture\nVersion: 1.0\n"
        raw_record = b"fixture RECORD\n"
        directory = "/usr/local/lib/python3.12/site-packages/fixture-1.0.dist-info"
        _, metadata_hash = _metadata_text(raw_metadata)
        _, record_hash = _metadata_text(raw_record)
        row = {
            "name": "fixture",
            "version": "1.0",
            "metadata_directory": directory,
            "text_sha256": {
                "METADATA": metadata_hash,
                "RECORD": record_hash,
                "direct_url.json": _sha(b""),
            },
            "raw_sha256": {
                "METADATA": _sha(raw_metadata),
                "RECORD": _sha(raw_record),
                "direct_url.json": _sha(b""),
            },
        }
        with pytest.raises(WorkerAdmissionRejected):
            admission._verify_distribution_metadata(
                root,
                {"rows": [row]},
                {
                    f"{directory}/METADATA": _sha(raw_metadata),
                    f"{directory}/RECORD": _sha(raw_record),
                },
            )
    else:
        with pytest.raises(WorkerAdmissionRejected):
            provider._snapshot()


@pytest.mark.skipif(os.name != "posix", reason="POSIX snapshot descriptor semantics")
def test_snapshot_member_rejects_different_real_and_effective_uids(tmp_path, monkeypatch):
    import quantmesh.research.worker_admission as admission

    root = tmp_path / "snapshot-member"
    root.mkdir(mode=0o700)
    member = root / "metadata.json"
    member.write_bytes(b"private metadata")
    member.chmod(0o400)
    owner_uid = member.stat().st_uid
    directory_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        monkeypatch.setattr(admission.os, "getuid", lambda: owner_uid)
        monkeypatch.setattr(admission.os, "geteuid", lambda: owner_uid + 1)
        with pytest.raises(WorkerAdmissionRejected):
            _read_snapshot_member(directory_fd, member.name, 4096)
    finally:
        os.close(directory_fd)


def test_snapshot_member_fails_closed_without_posix_uid(monkeypatch):
    import quantmesh.research.worker_admission as admission

    def unexpected_open(*_args, **_kwargs):
        raise AssertionError("non-POSIX owner validation must fail before opening a member")

    monkeypatch.setattr(admission.os, "name", "nt")
    monkeypatch.setattr(admission.os, "open", unexpected_open)
    with pytest.raises(WorkerAdmissionRejected):
        _read_snapshot_member(-1, "metadata.json", 4096)


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


def test_cgroup_virtual_limit_has_kernel_bytes_despite_zero_stat_size():
    import os
    import sys

    import quantmesh.research.worker_admission as admission

    if sys.platform != "linux":
        pytest.skip("real Linux cgroup filesystem required")
    groups = Path("/proc/self/cgroup").read_text().splitlines()
    group = next(line[3:] for line in groups if line.startswith("0::"))
    directory = Path("/sys/fs/cgroup").joinpath(*Path(group).parts[1:])
    if not (directory / "memory.max").exists():
        pytest.skip("current cgroup has no memory controller")
    fd, descriptors = admission._open_absolute_directory(directory)
    try:
        assert (directory / "memory.max").stat().st_size == 0
        raw = admission._read_proc_member(fd, "memory.max", 4096, cgroup=True)
        assert raw and raw == (directory / "memory.max").read_bytes()
        with pytest.raises(WorkerAdmissionRejected):
            admission._read_proc_member(fd, "memory.max", 4096)
        with pytest.raises(WorkerAdmissionRejected):
            admission._read_proc_member(fd, "status", 4096, cgroup=True)
        with pytest.raises(WorkerAdmissionRejected):
            admission._read_proc_member(fd, "memory.max", 1, cgroup=True)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
