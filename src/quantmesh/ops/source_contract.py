"""Frozen clean-source and remote-reachability proof for a daily run."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import math
import platform
import re
import sys
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.artifacts import canonical_json_bytes
from quantmesh.ops.immutable_runs import (
    publish_create_once,
    read_safe_bytes,
    reject_reparse_chain,
)
from quantmesh.ops.processes import ProcessResult, run_process


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


PLATFORM_TOLERATED = frozenset(
    {
        "uvloop",
        "jeepney",
        "SecretStorage",
        "cryptography",
        "cffi",
        "pycparser",
        "colorama",
        "pywin32-ctypes",
    }
)

DEPENDENCY_FILES = (
    PurePosixPath("pyproject.toml"),
    PurePosixPath("requirements-audit.txt"),
    PurePosixPath("requirements-build.txt"),
)

PINNED_OPERATIONAL_SCRIPTS = (
    PurePosixPath("src/quantmesh/ops/connection_witness.py"),
    PurePosixPath("src/quantmesh/ops/soak_acceptance.py"),
    PurePosixPath("src/quantmesh/ops/soak_runner.py"),
    PurePosixPath("src/quantmesh/ops/source_contract.py"),
    PurePosixPath("src/quantmesh/ops/witness_outbox.py"),
    PurePosixPath("tools/connection_witness.ps1"),
    PurePosixPath("tools/connection_witness.py"),
    PurePosixPath("tools/soak_daily.py"),
    PurePosixPath("tools/trusted_data_soak_acceptance.py"),
    PurePosixPath("tools/soak_witness_outbox.py"),
)

_DIGEST_FIELDS = frozenset(
    {"dependency_digest", "script_digest", "config_digest", "source_contract_id"}
)


class RuntimeDigestsV1(_FrozenContract):
    contract: str = Field(
        default="quantmesh-runtime-digests-v1",
        pattern=r"^quantmesh-runtime-digests-v1$",
    )
    dependency_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    script_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_digest: str = Field(pattern=r"^[0-9a-f]{64}$")


class ScheduleContractV1(_FrozenContract):
    contract: str = Field(
        default="quantmesh-schedule-contract-v1",
        pattern=r"^quantmesh-schedule-contract-v1$",
    )
    config: dict[str, Any]
    config_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def digest_matches(self) -> Self:
        if self.config_digest != derive_config_digest(self.config):
            raise ValueError("schedule config digest disagrees with its normalized config")
        return self

    @classmethod
    def build(cls, config: Mapping[str, Any]) -> ScheduleContractV1:
        normalized = _normalize_config(config)
        return cls(config=normalized, config_digest=derive_config_digest(normalized))

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="json"))


def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _file_entry(repo: Path, relative: PurePosixPath) -> dict[str, str]:
    path = repo.joinpath(*relative.parts)
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"required runtime file is missing or unsafe: {relative.as_posix()}")
    resolved = path.resolve()
    if not resolved.is_relative_to(repo):
        raise ValueError(f"required runtime file escapes the repository: {relative.as_posix()}")
    return {
        "path": relative.as_posix(),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _read_pins(repo: Path) -> dict[str, tuple[str, str]]:
    path = repo / "requirements-audit.txt"
    pins: dict[str, tuple[str, str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, separator, version = line.partition("==")
        if not separator or not name.strip() or not version.strip():
            raise ValueError(f"malformed requirements-audit pin: {line!r}")
        canonical = _canonical_name(name.strip())
        if canonical in pins:
            raise ValueError(f"duplicate requirements-audit pin: {name.strip()}")
        pins[canonical] = (name.strip(), version.strip())
    if not pins:
        raise ValueError("requirements-audit.txt must contain at least one pin")
    return pins


def _editable_identity(distribution: Any) -> bool:
    reader = getattr(distribution, "read_text", None)
    if not callable(reader):
        return False
    try:
        raw = reader("direct_url.json")
        payload = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, OSError, TypeError):
        return False
    directory = payload.get("dir_info")
    return isinstance(directory, dict) and directory.get("editable") is True


def _installed_inventory(distributions: Iterable[Any]) -> tuple[dict[str, Any], ...]:
    inventory: dict[str, dict[str, Any]] = {}
    for distribution in distributions:
        raw_name = distribution.metadata["Name"]
        name = _canonical_name(str(raw_name))
        if name in inventory:
            if inventory[name]["version"] != str(distribution.version):
                raise ValueError(f"conflicting installed distribution identity: {name}")
            inventory[name]["editable"] = (
                inventory[name]["editable"] or _editable_identity(distribution)
            )
            continue
        inventory[name] = {
            "name": name,
            "version": str(distribution.version),
            "editable": _editable_identity(distribution),
        }
    return tuple(inventory[name] for name in sorted(inventory))


def _normalize_config(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value.resolve())
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_config(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _DIGEST_FIELDS
        }
    if isinstance(value, (tuple, list)):
        return [_normalize_config(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"runtime config contains unsupported {type(value).__name__}")


def derive_config_digest(runtime_config: Mapping[str, Any]) -> str:
    return _digest(
        {
            "contract": "quantmesh-runtime-config-v1",
            "config": _normalize_config(runtime_config),
        }
    )


def publish_schedule_manifest(root: Path, config: Mapping[str, Any]) -> Path:
    directory = Path(root).resolve()
    if not Path(root).is_absolute():
        raise ValueError("schedule manifest root must be absolute")
    reject_reparse_chain(directory.parent)
    directory.mkdir(parents=True, exist_ok=True)
    reject_reparse_chain(directory)
    manifest = ScheduleContractV1.build(config)
    path = directory / f"{manifest.config_digest}.json"
    publish_create_once(path, manifest.canonical_bytes(), label="schedule contract manifest")
    return path


def load_schedule_manifest(path: Path) -> ScheduleContractV1:
    manifest_path = Path(path)
    if not manifest_path.is_absolute():
        raise ValueError("schedule manifest path must be absolute")
    reject_reparse_chain(manifest_path.parent)
    try:
        manifest = ScheduleContractV1.model_validate_json(read_safe_bytes(manifest_path))
    except (OSError, ValueError) as error:
        raise ValueError("schedule contract manifest is unreadable or invalid") from error
    if manifest_path.stem != manifest.config_digest or manifest_path.suffix != ".json":
        raise ValueError("schedule manifest filename disagrees with its config digest")
    return manifest


def compute_runtime_digests(
    repo: Path,
    runtime_config: Mapping[str, Any],
    *,
    python_executable: Path | None = None,
    python_implementation: str | None = None,
    python_version: str | None = None,
    distributions: Iterable[Any] | None = None,
) -> RuntimeDigestsV1:
    """Derive the actual runtime identity from fixed repo and interpreter inputs."""
    checkout = Path(repo).resolve()
    if not checkout.is_dir():
        raise ValueError("runtime repository must be an existing directory")
    dependency_files = tuple(_file_entry(checkout, item) for item in DEPENDENCY_FILES)
    pins = _read_pins(checkout)
    installed = _installed_inventory(
        metadata.distributions() if distributions is None else distributions
    )
    installed_by_name = {item["name"]: item for item in installed}
    tolerated = {_canonical_name(item) for item in PLATFORM_TOLERATED}
    for canonical, (display, expected_version) in sorted(pins.items()):
        observed = installed_by_name.get(canonical)
        if observed is None:
            if canonical in tolerated:
                continue
            raise ValueError(f"{display}=={expected_version} is pinned but not installed")
        if observed["version"] != expected_version:
            raise ValueError(
                f"{display}=={expected_version} version drift: {observed['version']} installed"
            )
    interpreter = Path(python_executable or sys.executable).resolve()
    if interpreter.is_symlink() or not interpreter.is_file():
        raise ValueError("pinned Python interpreter is missing or unsafe")
    dependency_identity = {
        "contract": "quantmesh-dependency-identity-v1",
        "files": dependency_files,
        "python": {
            "implementation": python_implementation or platform.python_implementation(),
            "version": python_version or platform.python_version(),
            "executable_sha256": hashlib.sha256(interpreter.read_bytes()).hexdigest(),
        },
        "installed_distributions": installed,
    }
    script_identity = {
        "contract": "quantmesh-operational-scripts-v1",
        "files": tuple(_file_entry(checkout, item) for item in PINNED_OPERATIONAL_SCRIPTS),
    }
    return RuntimeDigestsV1(
        dependency_digest=_digest(dependency_identity),
        script_digest=_digest(script_identity),
        config_digest=derive_config_digest(runtime_config),
    )


class SourceContractV1(_FrozenContract):
    contract: str = Field(
        default="quantmesh-source-contract-v1",
        pattern=r"^quantmesh-source-contract-v1$",
    )
    remote_ref: str = Field(min_length=1)
    head_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    dependency_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    script_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    clean: Literal[True]
    reachable: Literal[True]
    source_contract_id: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("remote_ref")
    @classmethod
    def remote_ref_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("remote ref must not be blank")
        return value

    @model_validator(mode="after")
    def identity_matches(self) -> Self:
        body = self.model_dump(mode="json", exclude={"source_contract_id"})
        if self.source_contract_id != _digest(body):
            raise ValueError("source contract ID disagrees with its body")
        return self

    @classmethod
    def build(cls, **values: Any) -> SourceContractV1:
        probe = cls.model_construct(**values, source_contract_id="0" * 64)
        identity = _digest(
            probe.model_dump(mode="json", exclude={"source_contract_id"})
        )
        return cls(**values, source_contract_id=identity)


def verify_source_contract(
    repo: Path,
    remote_ref: str,
    dependency_digest: str,
    script_digest: str,
    config_digest: str,
    *,
    runtime_config: Mapping[str, Any],
    python_executable: Path | None = None,
    distributions: Iterable[Any] | None = None,
    timeout_seconds: float = 30.0,
) -> SourceContractV1:
    """Recompute runtime identity, then prove clean remote-reachable source."""
    actual = compute_runtime_digests(
        repo,
        runtime_config,
        python_executable=python_executable,
        distributions=distributions,
    )
    expected = {
        "dependency_digest": dependency_digest,
        "script_digest": script_digest,
        "config_digest": config_digest,
    }
    for field, claimed in expected.items():
        if getattr(actual, field) != claimed:
            label = field.replace("_", " ")
            raise ValueError(f"{label} drift: runtime does not match the frozen contract")
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError("source-contract timeout must be finite and positive")
    deadline = time.monotonic() + timeout_seconds

    def remaining() -> float:
        value = deadline - time.monotonic()
        if value <= 0:
            raise ValueError("Git source contract timed out")
        return value

    checkout = Path(repo).resolve()
    if not checkout.is_dir():
        raise ValueError("source repository must be an existing directory")

    top = _git(
        checkout,
        ("git", "-C", str(checkout), "rev-parse", "--show-toplevel"),
        timeout_seconds=remaining(),
        label="repository root",
    ).stdout.strip()
    if Path(top).resolve() != checkout:
        raise ValueError("configured repository is not the exact Git top level")
    head = _git(
        checkout,
        ("git", "-C", str(checkout), "rev-parse", "HEAD"),
        timeout_seconds=remaining(),
        label="HEAD",
    ).stdout.strip()
    if len(head) != 40 or any(character not in "0123456789abcdef" for character in head):
        raise ValueError("Git HEAD is not a lowercase 40-character commit")
    status = _git(
        checkout,
        (
            "git",
            "-C",
            str(checkout),
            "status",
            "--porcelain",
            "--untracked-files=all",
        ),
        timeout_seconds=remaining(),
        label="working tree status",
    )
    if status.stdout.strip():
        raise ValueError("daily run requires a clean Git checkout")
    ancestry = run_process(
        (
            "git",
            "-C",
            str(checkout),
            "merge-base",
            "--is-ancestor",
            "HEAD",
            remote_ref,
        ),
        timeout_seconds=remaining(),
        cwd=checkout,
    )
    _require_process(ancestry, "remote reachability", allow_nonzero=True)
    if ancestry.returncode != 0:
        raise ValueError("Git HEAD is not reachable from the configured remote ref")
    return SourceContractV1.build(
        remote_ref=remote_ref,
        head_commit=head,
        dependency_digest=dependency_digest,
        script_digest=script_digest,
        config_digest=config_digest,
        clean=True,
        reachable=True,
    )


def snapshot_source_contract(
    repo: Path,
    remote_ref: str,
    runtime_config: Mapping[str, Any],
    *,
    python_executable: Path | None = None,
    distributions: Iterable[Any] | None = None,
    timeout_seconds: float = 30.0,
) -> SourceContractV1:
    actual = compute_runtime_digests(
        repo,
        runtime_config,
        python_executable=python_executable,
        distributions=distributions,
    )
    return verify_source_contract(
        repo,
        remote_ref,
        actual.dependency_digest,
        actual.script_digest,
        actual.config_digest,
        runtime_config=runtime_config,
        python_executable=python_executable,
        distributions=distributions,
        timeout_seconds=timeout_seconds,
    )


def _git(
    repo: Path,
    argv: tuple[str, ...],
    *,
    timeout_seconds: float,
    label: str,
) -> ProcessResult:
    result = run_process(argv, timeout_seconds=timeout_seconds, cwd=repo)
    _require_process(result, label)
    return result


def _require_process(
    result: ProcessResult,
    label: str,
    *,
    allow_nonzero: bool = False,
) -> None:
    if result.timed_out:
        raise ValueError(f"Git {label} timed out")
    if result.returncode is None:
        raise ValueError(f"Git {label} did not terminate")
    if result.returncode != 0 and not allow_nonzero:
        raise ValueError(f"Git {label} failed: {result.stderr.strip()}")


def _runtime_config_file(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("runtime config file is unreadable or invalid") from error
    if not isinstance(value, dict):
        raise ValueError("runtime config file must contain one JSON object")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantmesh-source-contract")
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot")
    snapshot.add_argument("--repo", type=Path, required=True)
    snapshot.add_argument("--remote-ref", required=True)
    snapshot.add_argument("--runtime-config-file", type=Path, required=True)
    snapshot.add_argument("--python-executable", type=Path, required=True)
    snapshot.add_argument("--timeout-seconds", type=float, default=30.0)
    publish = commands.add_parser("publish-manifest")
    publish.add_argument("--manifest-root", type=Path, required=True)
    publish.add_argument("--runtime-config-file", type=Path, required=True)
    preflight = commands.add_parser("run-preflight")
    preflight.add_argument("--argv-file", type=Path, required=True)
    preflight.add_argument("--cwd", type=Path, required=True)
    preflight.add_argument("--timeout-seconds", type=float, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "run-preflight":
            try:
                raw_argv = json.loads(args.argv_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise ValueError("preflight argv file is unreadable or invalid") from error
            if (
                not isinstance(raw_argv, list)
                or not raw_argv
                or any(not isinstance(item, str) or not item for item in raw_argv)
            ):
                raise ValueError("preflight argv must be one non-empty string array")
            result = run_process(
                tuple(raw_argv), timeout_seconds=args.timeout_seconds, cwd=args.cwd
            )
            output = {
                "argv_digest": _digest(raw_argv),
                "returncode": result.returncode,
                "timed_out": result.timed_out,
                "tree_terminated": result.tree_terminated,
            }
            print(canonical_json_bytes(output).decode("utf-8"))
            return 0 if result.returncode == 0 and not result.timed_out else 1
        config = _runtime_config_file(args.runtime_config_file)
        if args.command == "publish-manifest":
            path = publish_schedule_manifest(args.manifest_root, config)
            manifest = load_schedule_manifest(path)
            output = {
                "config_digest": manifest.config_digest,
                "manifest_path": str(path),
            }
        else:
            contract = snapshot_source_contract(
                args.repo,
                args.remote_ref,
                config,
                python_executable=args.python_executable,
                timeout_seconds=args.timeout_seconds,
            )
            output = contract.model_dump(mode="json")
        print(canonical_json_bytes(output).decode("utf-8"))
        return 0
    except Exception as error:
        print(f"FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
