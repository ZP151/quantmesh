"""Pure construction of the Worker kernel boundary, never an admission authority.

ELF bytes, the baseline profile, loaded enforcing AppArmor state and actual
container/mount identities must be independently admitted by the parent.
Generating these documents installs nothing and does not qualify a Worker.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath

_DEFAULT_LIMIT = 256 * 1024
_MOUNT_LIMIT = 1024 * 1024
_ELF_LIMIT = 2048
_PYTHON = "/usr/local/bin/python3"
_PYTHON_TARGET = "/usr/local/bin/python3.12"


class KernelPolicyRejected(ValueError):
    """Fixed, sanitized refusal of a construction or mount observation."""


@dataclass(frozen=True, slots=True)
class KernelPolicy:
    name: str
    apparmor: bytes
    seccomp: bytes
    sha256: str


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(value: object) -> bool:
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _pairs(items: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _elf_path(value: object) -> bool:
    if (
        type(value) is not str
        or len(value) > 512
        or not re.fullmatch(r"/[A-Za-z0-9_./+\-]+", value)
    ):
        return False
    path = PurePosixPath(value)
    return (
        str(path) == value
        and ".." not in path.parts
        and any(value.startswith(root) for root in ("/usr/local/", "/usr/lib/", "/lib/"))
        and (
            value in {_PYTHON, _PYTHON_TARGET}
            or re.search(r"\.so(?:\.[0-9]+)*$", value) is not None
        )
    )


def _baseline(raw: bytes, digest: str) -> dict:
    if (
        type(raw) is not bytes
        or not 0 < len(raw) <= _DEFAULT_LIMIT
        or not _sha(digest)
        or hashlib.sha256(raw).hexdigest() != digest
    ):
        raise ValueError
    value = json.loads(raw, object_pairs_hook=_pairs)
    if (
        type(value) is not dict
        or value.get("defaultAction") != "SCMP_ACT_ERRNO"
        or type(value.get("syscalls")) is not list
        or not 0 < len(value["syscalls"]) <= 1024
        or "listenerPath" in value
        or "listenerMetadata" in value
    ):
        raise ValueError
    for rule in value["syscalls"]:
        if (
            type(rule) is not dict
            or type(rule.get("names")) is not list
            or not 0 < len(rule["names"]) <= 512
            or any(
                type(name) is not str or not re.fullmatch(r"[a-z0-9_]{1,64}", name)
                for name in rule["names"]
            )
            or rule.get("action")
            not in {
                "SCMP_ACT_ALLOW",
                "SCMP_ACT_ERRNO",
                "SCMP_ACT_KILL_PROCESS",
                "SCMP_ACT_KILL_THREAD",
                "SCMP_ACT_TRAP",
            }
        ):
            raise ValueError
    return value


_SAFE_ARGUMENTS = {
    "mmap": (((2, 4, 0),), ((2, 6, 4), (3, 32, 0))),
    "mprotect": (((2, 4, 0),),),
    "pkey_mprotect": (((2, 4, 0),),),
    "shmat": (((2, 0o100000, 0),),),  # SHM_EXEC from Linux UAPI shm.h
    "memfd_create": (((1, 24, 8),),),
}


def _intersect_arguments(existing: list, guards: tuple) -> list | None:
    """Intersect conditions without duplicate indices (runc may split those as OR)."""
    if type(existing) is not list or len(existing) > 6:
        raise ValueError
    conditions = {}
    for argument in existing:
        if (
            type(argument) is not dict
            or not {"index", "op", "value"} <= set(argument) <= {"index", "op", "value", "valueTwo"}
            or type(argument["index"]) is not int
            or not 0 <= argument["index"] <= 5
            or argument["index"] in conditions
            or type(argument["value"]) is not int
            or not 0 <= argument["value"] < 2**64
        ):
            raise ValueError
        conditions[argument["index"]] = dict(argument)
    for index, mask, expected in guards:
        previous = conditions.get(index)
        if previous:
            if previous["op"] == "SCMP_CMP_EQ":
                if previous["value"] & mask != expected:
                    return None
                continue  # An exact equality is already stricter than this guard.
            if previous["op"] != "SCMP_CMP_MASKED_EQ":
                raise ValueError  # No unsafe repeated-index approximation.
            old_mask, old_expected = previous["value"], previous.get("valueTwo")
            if (
                type(old_expected) is not int
                or not 0 <= old_expected < 2**64
                or old_expected & ~old_mask
            ):
                raise ValueError
            if (old_expected ^ expected) & (old_mask & mask):
                return None
            mask |= old_mask
            expected |= old_expected
        conditions[index] = {
            "index": index,
            "value": mask,
            "valueTwo": expected,
            "op": "SCMP_CMP_MASKED_EQ",
        }
    return [conditions[index] for index in sorted(conditions)]


def _restrict_syscalls(rules: list[dict]) -> list[dict]:
    """Narrow existing ALLOWs; never rely on ERRNO overriding an unconditional ALLOW."""
    result = []
    for rule in rules:
        if rule["action"] != "SCMP_ACT_ALLOW":
            result.append(rule)
            continue
        remaining = [name for name in rule["names"] if name not in _SAFE_ARGUMENTS]
        if remaining:
            result.append({**rule, "names": remaining})
        for name in rule["names"]:
            for guards in _SAFE_ARGUMENTS.get(name, ()):
                arguments = _intersect_arguments(rule.get("args", []), guards)
                if arguments is not None:
                    result.append({**rule, "names": [name], "args": arguments})
    return result


def build_kernel_policy(
    elf_files: dict[str, str], *, docker_default: bytes, docker_default_sha256: str
) -> KernelPolicy:
    """Bind pure policy bytes to externally measured ELF/default-profile pins.

    Preserves baseline refusals and narrows protected syscall ALLOW conditions,
    retaining other conditions/capability gates and narrowing to x86_64.
    The provided default digest must come from independently
    reviewed Engine tooling; passing a self-selected digest is not admission.
    """
    try:
        if (
            type(elf_files) is not dict
            or not 2 <= len(elf_files) <= _ELF_LIMIT
            or any(not _elf_path(path) or not _sha(digest) for path, digest in elf_files.items())
            or _PYTHON not in elf_files
            or _PYTHON_TARGET not in elf_files
            or elf_files[_PYTHON] != elf_files[_PYTHON_TARGET]
        ):
            raise ValueError
        baseline = _baseline(docker_default, docker_default_sha256)
        baseline.pop("archMap", None)
        baseline["architectures"] = ["SCMP_ARCH_X86_64"]
        baseline["syscalls"] = _restrict_syscalls(baseline["syscalls"])
        seccomp = _canonical(baseline)
        name = (
            "qm-worker-"
            + hashlib.sha256(
                _canonical(
                    {
                        "schema": 1,
                        "elf_files": elf_files,
                        "seccomp_sha256": hashlib.sha256(seccomp).hexdigest(),
                    }
                )
            ).hexdigest()[:20]
        )
        rules = [
            f"profile {name} flags=(attach_disconnected,mediate_deleted) {{",
            "  /** r,",
            "  /inputs/** r,",
            "  /output/** rwk,",
            "  /tmp/** rwk,",
            "  /dev/null rw,",
            "  /dev/zero rw,",
            "  /memfd:quantmesh-fixture-shard rwk,",
            "  signal,",
            *[f"  {path} mr," for path in sorted(elf_files)],
            f"  {_PYTHON} ix,",
            f"  {_PYTHON_TARGET} ix,",
            "}",
            "",
        ]
        apparmor = "\n".join(rules).encode("ascii")
        combined = hashlib.sha256(
            _canonical(
                {
                    "schema": 1,
                    "name": name,
                    "docker_default_sha256": docker_default_sha256,
                    "elf_files": elf_files,
                    "apparmor_sha256": hashlib.sha256(apparmor).hexdigest(),
                    "seccomp_sha256": hashlib.sha256(seccomp).hexdigest(),
                }
            )
        ).hexdigest()
        return KernelPolicy(name, apparmor, seccomp, combined)
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        raise KernelPolicyRejected("worker kernel policy rejected") from None


def _mount_path(raw: str) -> str:
    path = re.sub(r"\\(040|011|012|134)", lambda m: chr(int(m[1], 8)), raw)
    if (
        not path.startswith("/")
        or str(PurePosixPath(path)) != path
        or ".." in PurePosixPath(path).parts
        or any(ord(char) < 32 or ord(char) == 127 for char in path)
        or "\\" in path
    ):
        raise ValueError
    return path


def verify_mountinfo(raw: bytes) -> None:
    """Validate actual mountinfo bytes; a saved observation alone grants no authority.

    Kernel effective per-mount flags precede the separator; superblock flags
    cannot substitute for them. Any nested writable/executable mount refuses.
    Ambiguous stacked mount points are intentionally unsupported.
    """
    try:
        if type(raw) is not bytes or not 0 < len(raw) <= _MOUNT_LIMIT or b"\x00" in raw:
            raise ValueError
        lines = raw.decode("ascii").splitlines()
        if not 0 < len(lines) <= 1024:
            raise ValueError
        mounts, identities = {}, set()
        for line in lines:
            fields = line.split()
            separator = fields.index("-")
            if separator < 6 or len(fields) != separator + 4:
                raise ValueError
            identity, parent = fields[:2]
            if (
                not identity.isdecimal()
                or int(identity) <= 0
                or not parent.isdecimal()
                or identity in identities
            ):
                raise ValueError
            if not re.fullmatch(r"[0-9]+:[0-9]+", fields[2]):
                raise ValueError
            _mount_path(fields[3])
            point = _mount_path(fields[4])
            options = set(fields[5].split(","))
            if point in mounts or (options & {"ro", "rw"}) not in ({"ro"}, {"rw"}):
                raise ValueError
            if "rw" in options and "noexec" not in options:
                raise ValueError
            if any(
                point == root or point.startswith(root + "/")
                for root in ("/inputs", "/output", "/tmp")
            ):
                if "noexec" not in options or (point.startswith("/inputs") and "ro" not in options):
                    raise ValueError
            mounts[point] = options
            identities.add(identity)
        if (
            "ro" not in mounts["/"]
            or not {"ro", "noexec"} <= mounts["/inputs"]
            or not {"rw", "noexec"} <= mounts["/output"]
            or not {"rw", "noexec"} <= mounts["/tmp"]
        ):
            raise ValueError
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise KernelPolicyRejected("worker kernel mounts rejected") from None
