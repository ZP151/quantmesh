"""Frozen clean-source and remote-reachability proof for a daily run."""

from __future__ import annotations

import hashlib
import math
import time
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from quantmesh.data.artifacts import canonical_json_bytes
from quantmesh.ops.processes import ProcessResult, run_process


class _FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


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
    timeout_seconds: float = 30.0,
) -> SourceContractV1:
    """Prove a clean checkout whose HEAD is already on the configured remote ref."""
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
