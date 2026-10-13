"""PROPOSED offline build-stage curation; not executed until root admission.

Copy immutable base bytes; never install/download/compile anything. Final image
has no shell/package manager/pip/GNU optional extension libraries. This is a
Task1 fixture interpreter, not a complete research runtime.
"""

import hashlib
import json
import os
import shutil
import struct
import sys
from pathlib import Path

ROOT = Path("/qm-rootfs")
MATERIAL = Path("/opt/qm-build")
EXTENSIONS = (
    "_posixsubprocess",
    "_socket",
    "select",
    "math",
    "_struct",
    "_json",
    "_hashlib",
    "_sha2",
    "_sha3",
    "_blake2",
    "_random",
    "_datetime",
    "_pickle",
    "fcntl",
    "resource",
    "unicodedata",
    "array",
    "_opcode",
    "_bisect",
    "_heapq",
    "_statistics",
    "_csv",
)
NEEDED = {"libpython3.12.so.1.0", "libc.musl-x86_64.so.1", "libcrypto.so.3"}
expected = json.loads((MATERIAL / "base-file-sha256.json").read_text())


def copy_file(source, target, *, immutable_cpython_extension=False):
    source, target = Path(source), ROOT / str(target).lstrip("/")
    resolved = source.resolve(strict=True)
    digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    if not str(source).startswith("/opt/qm-build/"):
        candidates = [str(resolved).lstrip("/"), str(source).lstrip("/")]
        if not any(expected.get(name) == digest for name in candidates):
            # Upstream SPDX omits CPython extension/pure-Python per-file hashes.
            # Complete immutable base layer digests pin these bytes; record their
            # selected per-file SHA256 after materialization in the inventory.
            if not immutable_cpython_extension or resolved.parent != Path(
                "/usr/local/lib/python3.12/lib-dynload"
            ):
                raise ValueError("base_file_hash_not_in_bound_sbom: " + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(resolved, target)
    target.chmod(source.stat().st_mode & 0o777)


def elf_needed(path):
    data = path.read_bytes()
    if not data.startswith(b"\x7fELF"):
        return set()
    if data[4:6] != b"\x02\x01":
        raise ValueError("not_linux_amd64_elf")
    header = struct.unpack_from("<16sHHIQQQIHHHHHH", data)
    if header[2] != 62:
        raise ValueError("not_x86_64")
    offset, size, count = header[5], header[9], header[10]
    segments = [struct.unpack_from("<IIQQQQQQ", data, offset + n * size) for n in range(count)]
    dynamic = next((p for p in segments if p[0] == 2), None)
    if dynamic is None:
        return set()
    entries = []
    for pos in range(dynamic[2], dynamic[2] + dynamic[5], 16):
        tag, value = struct.unpack_from("<qQ", data, pos)
        if tag == 0:
            break
        entries.append((tag, value))
    address = next(value for tag, value in entries if tag == 5)
    segment = next(p for p in segments if p[0] == 1 and p[3] <= address < p[3] + p[5])
    start = segment[2] + address - segment[3]
    result = set()
    for tag, value in entries:
        if tag == 1:
            begin = start + value
            result.add(data[begin : data.index(b"\0", begin)].decode("ascii"))
    return result


if sys.version_info[:3] != (3, 12, 15) or not sys.dont_write_bytecode:
    raise ValueError("unexpected_cpython_or_bytecode_policy")
ROOT.mkdir(exist_ok=False)
stdlib = Path("/usr/local/lib/python3.12")
# Pure standard-library files remain pinned by immutable base layer/diff IDs.
# Drop packaged wheels, optional UI/test/build trees and all original native
# extensions. Re-add only the native modules needed by the fixed witnesses.
shutil.copytree(
    stdlib,
    ROOT / "usr/local/lib/python3.12",
    ignore=shutil.ignore_patterns(
        "site-packages",
        "ensurepip",
        "idlelib",
        "tkinter",
        "turtledemo",
        "test",
        "tests",
        "__pycache__",
        "lib-dynload",
        "config-*",
        "*.pyc",
        "*.pyo",
        "*.so",
        "*.a",
        "*.whl",
        "*.exe",
    ),
)
copy_file("/usr/local/bin/python3.12", "/usr/local/bin/python3.12")
(ROOT / "usr/local/bin/python3").symlink_to("python3.12")
copy_file("/usr/local/lib/libpython3.12.so.1.0", "/usr/local/lib/libpython3.12.so.1.0")
copy_file("/lib/ld-musl-x86_64.so.1", "/lib/ld-musl-x86_64.so.1")
(ROOT / "usr/lib").mkdir(parents=True, exist_ok=True)
(ROOT / "usr/lib/libc.musl-x86_64.so.1").symlink_to("/lib/ld-musl-x86_64.so.1")
copy_file("/usr/lib/libcrypto.so.3", "/usr/lib/libcrypto.so.3")
for name in EXTENSIONS:
    files = list((stdlib / "lib-dynload").glob(name + ".*.so"))
    if len(files) != 1:
        raise ValueError("missing_or_ambiguous_extension: " + name)
    copy_file(
        files[0],
        "/usr/local/lib/python3.12/lib-dynload/" + files[0].name,
        immutable_cpython_extension=True,
    )
copy_file(MATERIAL / "linux_bootstrap.py", "/opt/quantmesh/linux_bootstrap.py")
for source in (MATERIAL / "licenses").iterdir():
    copy_file(source, "/opt/quantmesh/licenses/" + source.name)
(ROOT / "etc").mkdir()
(ROOT / "etc/ld-musl-x86_64.path").write_text("/usr/local/lib:/lib:/usr/lib\n")
for name in ("inputs", "output", "tmp"):
    (ROOT / name).mkdir()
dependencies = {}
for path in ROOT.rglob("*"):
    if path.is_file() and not path.is_symlink():
        needed = elf_needed(path)
        if not needed <= NEEDED:
            raise ValueError("unexpected_elf_dependency: " + str(path) + " " + repr(needed))
        if needed:
            dependencies[path.relative_to(ROOT).as_posix()] = sorted(needed)
inventory = []
for path in sorted(ROOT.rglob("*")):
    if path.is_symlink():
        inventory.append({"path": path.relative_to(ROOT).as_posix(), "symlink": os.readlink(path)})
    elif path.is_file():
        inventory.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
manifest = {
    "scope": "TASK1_STANDARD_LIBRARY_FIXTURE_ONLY",
    "python": sys.version,
    "files": inventory,
    "elf_dependencies": dependencies,
    "bootstrap_sha256": hashlib.sha256(
        (ROOT / "opt/quantmesh/linux_bootstrap.py").read_bytes()
    ).hexdigest(),
}
(ROOT / "opt/quantmesh/runtime-files.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
print(
    json.dumps(
        {
            "curated_bytes": sum(x.get("bytes", 0) for x in inventory),
            "file_count": len(inventory),
            "bootstrap_sha256": manifest["bootstrap_sha256"],
        }
    )
)
