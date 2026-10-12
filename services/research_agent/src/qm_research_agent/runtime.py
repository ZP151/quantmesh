"""Explicit, fail-closed private bootstrap; preflight performs no SQL or serving."""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib
import importlib.metadata as metadata
import json
import os
import platform
import re
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator


class RuntimeRejected(ValueError):
    """Only fixed categories cross the operator boundary."""

    def __init__(self, category: str):
        if category not in {
            "configuration_invalid",
            "credential_invalid",
            "runtime_unqualified",
            "source_unqualified",
            "service_unavailable",
        }:
            category = "configuration_invalid"
        super().__init__(category)


def _directory(path: Path) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise RuntimeRejected("configuration_invalid")
    # Root-owned sticky /tmp is allowed; linked or writable intermediate paths are not.
    for component in (path, *path.parents):
        info = component.lstat()
        if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
            raise RuntimeRejected("configuration_invalid")
        if info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX):
            raise RuntimeRejected("configuration_invalid")
    info = path.stat()
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeRejected("configuration_invalid")
    return path


class ServiceRuntimeConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    schema_version: Literal[1] = 1
    operator_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
    expected_build: str = Field(pattern=r"^[0-9a-f]{40}$")
    lake_root: Path = Field(repr=False)
    artifact_root: Path = Field(repr=False)
    configured_dataset_ids: tuple[str, ...] = Field(default=(), max_length=128)
    credential_directory: Path = Field(repr=False)
    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: Literal[8110] = 8110

    @model_validator(mode="before")
    @classmethod
    def reject_coercion(cls, values):
        if isinstance(values, dict):
            if "port" in values and type(values["port"]) is not int:
                raise RuntimeRejected("configuration_invalid")
            if "schema_version" in values and type(values["schema_version"]) is not int:
                raise RuntimeRejected("configuration_invalid")
        return values

    @model_validator(mode="after")
    def qualified_paths_and_ids(self):
        from quantmesh.data.layout import validate_dataset_name

        try:
            if len(set(self.configured_dataset_ids)) != len(self.configured_dataset_ids):
                raise ValueError
            for name in self.configured_dataset_ids:
                validate_dataset_name(name)
            roots = [self.lake_root, self.artifact_root, self.credential_directory]
            for root in roots:
                _directory(root)
            if (
                any(a.is_relative_to(b) for a in roots for b in roots if a != b)
                or len(set(roots)) != 3
            ):
                raise ValueError
        except (ValueError, OSError):
            raise RuntimeRejected("configuration_invalid") from None
        return self


def _read_private(path: Path, limit: int) -> bytes:
    """Descriptor-relative no-follow walk and post-read identity/metadata checks."""
    directory_fd = fd = None
    try:
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError
        directory_fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        for part in path.parent.parts[1:]:
            next_fd = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd
            )
            os.close(directory_fd)
            directory_fd = next_fd
            info = os.fstat(directory_fd)
            if info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX):
                raise ValueError
        parent_info = os.fstat(directory_fd)
        if parent_info.st_uid != os.getuid() or stat.S_IMODE(parent_info.st_mode) != 0o700:
            raise ValueError
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory_fd)
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or not 0 < before.st_size <= limit
        ):
            raise ValueError
        chunks = []
        remaining = limit + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        after = os.fstat(fd)
        named = os.stat(path.name, dir_fd=directory_fd, follow_symlinks=False)

        def identity(info):
            return (
                info.st_dev,
                info.st_ino,
                info.st_mode,
                info.st_uid,
                info.st_nlink,
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
            )

        if (
            identity(before) != identity(after)
            or identity(after) != identity(named)
            or len(raw) != before.st_size
        ):
            raise ValueError
        # Also detect directory rename/replacement after opening it.
        parent = path.parent.stat(follow_symlinks=False)
        if (parent.st_dev, parent.st_ino) != (parent_info.st_dev, parent_info.st_ino):
            raise ValueError
        return raw
    except (OSError, ValueError):
        raise RuntimeRejected("credential_invalid") from None
    finally:
        if fd is not None:
            os.close(fd)
        if directory_fd is not None:
            os.close(directory_fd)


def _validate_dsn(raw: str) -> SecretStr:
    try:
        parsed = urlsplit(raw)
        pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
        if (
            parsed.scheme not in {"postgres", "postgresql"}
            or not parsed.username
            or not parsed.password
            or not parsed.hostname
            or parsed.fragment
            or not parsed.path.startswith("/")
            or len(parsed.path) < 2
            or "/" in parsed.path[1:]
            or any(ord(c) < 33 or ord(c) > 126 for c in raw)
            or (parsed.port is not None and not 1 <= parsed.port <= 65535)
        ):
            raise ValueError
        if pairs not in ([], [("sslmode", "verify-full")], [("sslmode", "disable")]):
            raise ValueError
        if pairs == [("sslmode", "disable")] and parsed.hostname not in {"127.0.0.1", "::1"}:
            raise ValueError
        return SecretStr(raw)
    except (ValueError, UnicodeError):
        raise RuntimeRejected("credential_invalid") from None


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        [
            "/usr/bin/git",
            "--no-replace-objects",
            "--no-optional-locks",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.hooksPath=/dev/null",
            "-C",
            str(root),
            *args,
        ],
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": "/nonexistent",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=20,
        check=True,
    )
    return result.stdout


def _admit_source(root: Path, expected: str) -> str:
    try:
        if (
            not root.is_absolute()
            or root.resolve() != root
            or not re.fullmatch(r"[0-9a-f]{40}", expected)
        ):
            raise ValueError
        actual = _git(root, "rev-parse", "HEAD").decode().strip()
        if actual != expected or _git(root, "diff", "--no-ext-diff", "HEAD", "--"):
            raise ValueError
        tracked = set(_git(root, "ls-files", "-z").decode().split("\0"))
        # Deliberately include ignored shadows/bytecode. Use -B in a clean checkout.
        others = _git(root, "ls-files", "--others", "-z").decode().split("\0")
        for name in others:
            path = Path(name)
            if path.name == ".env" or path.suffix in {".py", ".pth", ".so", ".pyd", ".pyc"}:
                raise ValueError
        for name in tracked - {""}:
            path = root / name
            if path.is_symlink():
                raise ValueError
        # Git diff can hide assume-unchanged/skip-worktree files. Measure actual
        # executable and runtime configuration bytes against HEAD blob identities.
        entries = _git(root, "ls-tree", "-r", "-z", "HEAD").decode().split("\0")
        for entry in filter(None, entries):
            header, name = entry.split("\t", 1)
            mode, kind, expected_blob = header.split()
            path = root / name
            if kind == "blob" and (
                mode == "100755" or path.suffix in {".py", ".toml", ".lock", ".pth", ".so", ".pyd"}
            ):
                raw = path.read_bytes()
                actual_blob = hashlib.sha1(
                    b"blob " + str(len(raw)).encode() + b"\0" + raw
                ).hexdigest()
                if actual_blob != expected_blob:
                    raise ValueError
        return actual
    except (ValueError, OSError, subprocess.SubprocessError):
        raise RuntimeRejected("source_unqualified") from None


def _native_filesystem(path: Path) -> bool:
    """Only measured persistent native Linux filesystem types, not /mnt/drvfs."""
    candidates = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        left, right = line.split(" - ", 1)
        mount = Path(left.split()[4].replace("\\040", " "))
        if path.is_relative_to(mount):
            candidates.append((len(mount.parts), right.split()[0]))
    return bool(candidates) and max(candidates)[1] in {"ext4", "xfs", "btrfs"}


def _admit_dependencies(prefix: Path, pins: dict[str, str]) -> dict:
    """Measure the entire executable closure before lazy server imports or SQL."""
    site = prefix / "lib/python3.12/site-packages"
    records = {}
    try:
        for name, version in pins.items():
            dist = metadata.distribution(name)
            if dist.version != version or not dist.files:
                raise ValueError
            for item in dist.files:
                path = Path(os.path.abspath(dist.locate_file(item)))
                if path.suffix == ".pyc" and not path.exists():
                    continue  # Removed pip-generated cache entries are not executable.
                if path.resolve() != path or not path.is_relative_to(prefix):
                    raise ValueError
                if item.hash:
                    if item.hash.mode != "sha256":
                        raise ValueError
                    digest = (
                        base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest())
                        .decode()
                        .rstrip("=")
                    )
                    if digest != item.hash.value:
                        raise ValueError
                    records[path] = item.hash
                elif path.suffix in {".py", ".so", ".pyd", ".pth", ".pyc"}:
                    raise ValueError
        for path in site.rglob("*"):
            if path.suffix == ".pyc":
                raise ValueError
            if path.suffix in {".py", ".so", ".pyd", ".pth"} and path not in records:
                raise ValueError
        return records
    except (ValueError, OSError, metadata.PackageNotFoundError):
        raise RuntimeRejected("runtime_unqualified") from None


def _admit_runtime(expected: str) -> tuple[str, str]:
    try:
        if (
            platform.system() != "Linux"
            or platform.python_implementation() != "CPython"
            or sys.version_info[:2] != (3, 12)
            or platform.machine() != "x86_64"
            or os.getuid() == 0
            or sys.prefix == sys.base_prefix
        ):
            raise ValueError
        root = Path(__file__).absolute().parents[4]
        prefix = Path(sys.prefix)
        if (
            prefix.resolve() != prefix
            or not _native_filesystem(root)
            or not _native_filesystem(prefix)
        ):
            raise ValueError
        actual = _admit_source(root, expected)
        from tools.research_service_gate import license_inventory, read_lock

        lock = root / "services/research_agent/requirements.linux-cp312.lock"
        if (
            hashlib.sha256(lock.read_bytes()).hexdigest()
            != "07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a"
        ):
            raise ValueError
        pins = read_lock(lock)
        if len(pins) != 81:
            raise ValueError
        _, failures = license_inventory(pins)
        if failures:
            raise ValueError
        site = prefix / "lib/python3.12/site-packages"
        records = _admit_dependencies(prefix, pins)
        for name in (
            "fastapi",
            "uvicorn",
            "pg8000",
            "qm_research_agent.app",
            "qm_research_agent.store",
        ):
            importlib.import_module(name)
        for name, module in tuple(sys.modules.items()):
            location = getattr(module, "__file__", None)
            if not location or name == "__main__":
                continue
            path = Path(location).absolute()
            if path.is_relative_to(root) or name.startswith(
                (
                    "quantmesh",
                    "qm_research_agent",
                    "tools.research_service_gate",
                    "tools.license_review",
                )
            ):
                if not path.is_relative_to(root) or path.resolve() != path:
                    raise ValueError
                relative = path.relative_to(root).as_posix()
                if path.read_bytes() != _git(root, "show", "HEAD:" + relative):
                    raise ValueError
            elif path.is_relative_to(site):
                record = records.get(path)
                if record is None or record.mode != "sha256" or path.resolve() != path:
                    raise ValueError
                digest = (
                    base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest())
                    .decode()
                    .rstrip("=")
                )
                if digest != record.value:
                    raise ValueError
            elif path.is_relative_to(Path(sys.base_prefix) / "lib/python3.12"):
                continue
            else:
                raise ValueError
        # Prevent subsequent imports from an unmeasured path, including cwd/PYTHONPATH.
        permitted = {root, root / "src", root / "services/research_agent/src", site}
        for entry in sys.path:
            path = Path(entry or os.getcwd()).absolute()
            if (
                path not in permitted
                and not path.is_relative_to(Path(sys.base_prefix) / "lib/python3.12")
                and path != Path(sys.base_prefix) / "lib/python312.zip"
            ):
                raise ValueError
        return actual, hashlib.sha256(lock.read_bytes()).hexdigest()
    except RuntimeRejected:
        raise
    except (ValueError, OSError, ImportError, subprocess.SubprocessError):
        raise RuntimeRejected("runtime_unqualified") from None


@dataclass(frozen=True, repr=False)
class ServiceRuntime:
    config: ServiceRuntimeConfig = field(repr=False)
    api_token: SecretStr = field(repr=False)
    postgres_dsn: SecretStr = field(repr=False)
    actual_build: str
    lock_sha256: str

    def __repr__(self):
        return "<ServiceRuntime private>"

    def preflight(self) -> dict:
        return {
            "schema_version": 1,
            "mode": "preflight",
            "actual_build": self.actual_build,
            "runtime": "linux-cp312-x86_64",
            "lock_sha256": self.lock_sha256,
            "advisory_only": True,
            "paper": True,
            "live": False,
            "capabilities": {"worker": "pending_containment", "model": "unavailable"},
        }


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeRejected("configuration_invalid")
        result[key] = value
    return result


def load_runtime(config_path: Path) -> ServiceRuntime:
    try:
        # Parse only explicit bounded config. No getenv, secret search or .env loading.
        data = json.loads(_read_private(config_path, 65536), object_pairs_hook=_unique_object)
        config = ServiceRuntimeConfig.model_validate(data)
        actual, lock = _admit_runtime(config.expected_build)
        directory = config.credential_directory
        token = _read_private(directory / "api_token", 4096).decode("ascii")
        dsn = _read_private(directory / "postgres_dsn", 8192).decode("ascii")
        if not 16 <= len(token) <= 4096 or not re.fullmatch(r"[A-Za-z0-9._~-]+", token):
            raise RuntimeRejected("credential_invalid")
        return ServiceRuntime(config, SecretStr(token), _validate_dsn(dsn), actual, lock)
    except RuntimeRejected:
        raise
    except (ValueError, OSError, UnicodeError):
        raise RuntimeRejected("configuration_invalid") from None


def build_app(runtime: ServiceRuntime):
    from qm_research_agent.app import create_app
    from qm_research_agent.store import PostgresJobStore

    config = runtime.config
    # Re-admit immediately before the first database effect.
    if _admit_runtime(config.expected_build) != (runtime.actual_build, runtime.lock_sha256):
        raise RuntimeRejected("source_unqualified")
    store = PostgresJobStore(
        runtime.postgres_dsn, lake_root=config.lake_root, artifact_root=config.artifact_root
    )
    return create_app(
        store,
        operator_id=config.operator_id,
        token=runtime.api_token,
        configured_dataset_ids=config.configured_dataset_ids,
        actual_build=runtime.actual_build,
    )


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise RuntimeRejected("configuration_invalid")


def main(argv=None) -> int:
    parser = _Parser(description="Private Research Service: explicit config, preflight by default.")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--serve", action="store_true")
    try:
        args = parser.parse_args(argv)
        runtime = load_runtime(args.config)
        if not args.serve:
            print(json.dumps(runtime.preflight(), sort_keys=True))
            return 0
        import uvicorn

        app = build_app(runtime)
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=8110,
            workers=1,
            reload=False,
            proxy_headers=False,
            access_log=False,
            log_level="critical",
            log_config=None,
        )
        return 0
    except RuntimeRejected as error:
        print(str(error), file=sys.stderr)
        return 2
    except Exception:
        print("service_unavailable", file=sys.stderr)
        return 3
