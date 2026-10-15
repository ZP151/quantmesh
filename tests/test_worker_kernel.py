"""Behavioral policy tests; no test here certifies native kernel enforcement."""

import hashlib
import json

import pytest

from quantmesh.research.worker_kernel import (
    KernelPolicyRejected,
    build_kernel_policy,
    verify_mountinfo,
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


BASE = {
    "defaultAction": "SCMP_ACT_ERRNO",
    "defaultErrnoRet": 1,
    "archMap": [{"architecture": "SCMP_ARCH_X86_64", "subArchitectures": ["SCMP_ARCH_X86"]}],
    "syscalls": [
        {
            "names": [
                "read",
                "write",
                "mmap",
                "mprotect",
                "pkey_mprotect",
                "shmat",
                "memfd_create",
            ],
            "action": "SCMP_ACT_ALLOW",
        }
    ],
}
ELF = {
    "/usr/local/bin/python3": "a" * 64,
    "/usr/local/bin/python3.12": "a" * 64,
    "/usr/lib/x86_64-linux-gnu/libc.so.6": "b" * 64,
}


def build(elf=None, base=None):
    raw = canonical(BASE if base is None else base)
    return build_kernel_policy(
        ELF if elf is None else elf,
        docker_default=raw,
        docker_default_sha256=hashlib.sha256(raw).hexdigest(),
    )


def tightened(rule, syscall, args):
    """Independent evaluation of libseccomp's MASKED_EQ argument semantics."""
    if syscall not in rule["names"]:
        return False
    return all(
        (args[arg["index"]] & arg["value"]) == arg["valueTwo"] for arg in rule.get("args", [])
    )


@pytest.mark.parametrize(
    ("syscall", "args", "refused"),
    [
        ("mmap", [0, 4096, 5, 2, 3, 0], False),  # measured file RX
        ("mmap", [0, 4096, 5, 34, -1, 0], True),  # anonymous RX
        ("mmap", [0, 4096, 7, 2, 3, 0], True),  # file W+X
        ("mmap", [0, 4096, 3, 34, -1, 0], False),
        ("mprotect", [0, 4096, 5], True),
        ("mprotect", [0, 4096, 3], False),
        ("pkey_mprotect", [0, 4096, 4, 0], True),
        ("shmat", [1, 0, 4096], False),  # SHM_RDONLY
        ("shmat", [1, 0, 32768], True),  # SHM_EXEC
        ("shmat", [1, 0, 36864], True),  # SHM_EXEC | SHM_RDONLY
        ("shmat", [1, 0, 0], False),
        ("memfd_create", [0, 11], False),  # CLOEXEC|ALLOW_SEALING|NOEXEC_SEAL
        ("memfd_create", [0, 3], True),
        ("memfd_create", [0, 27], True),  # contradictory MFD_EXEC
    ],
)
def test_executable_routes_are_denied_without_rejecting_data_memory(syscall, args, refused):
    rules = json.loads(build().seccomp)["syscalls"]
    allowed = any(
        rule["action"] == "SCMP_ACT_ALLOW" and tightened(rule, syscall, args) for rule in rules
    )
    assert allowed is not refused


def test_baseline_refusals_and_rules_are_preserved_with_architecture_narrowed():
    policy = build()
    parsed = json.loads(policy.seccomp)
    assert parsed["defaultAction"] == BASE["defaultAction"]
    assert parsed["defaultErrnoRet"] == BASE["defaultErrnoRet"]
    assert {
        name for rule in parsed["syscalls"] for name in rule["names"] if not rule.get("args")
    } == {"read", "write"}
    assert parsed["architectures"] == ["SCMP_ARCH_X86_64"]
    assert "archMap" not in parsed


def test_default_denied_protected_syscall_is_never_newly_allowed():
    base = {**BASE, "syscalls": [{"names": ["read", "write"], "action": "SCMP_ACT_ALLOW"}]}
    assert json.loads(build(base=base).seccomp)["syscalls"] == base["syscalls"]


def test_existing_masked_argument_and_capability_conditions_stay_stricter():
    base = {
        **BASE,
        "syscalls": [
            {
                "names": ["mmap"],
                "action": "SCMP_ACT_ALLOW",
                "includes": {"caps": ["CAP_SYS_ADMIN"]},
                "args": [{"index": 2, "op": "SCMP_CMP_MASKED_EQ", "value": 64, "valueTwo": 0}],
            }
        ],
    }
    rules = json.loads(build(base=base).seccomp)["syscalls"]
    assert rules and all(rule["includes"] == base["syscalls"][0]["includes"] for rule in rules)
    for rule in rules:
        indexes = [arg["index"] for arg in rule["args"]]
        assert len(indexes) == len(set(indexes))
        assert not tightened(rule, "mmap", [0, 4096, 64 | 1, 2, 3, 0])


@pytest.mark.parametrize("action", ["SCMP_ACT_ALLOW", "SCMP_ACT_LOG", None])
def test_permissive_default_profile_refuses(action):
    with pytest.raises(KernelPolicyRejected):
        build(base={**BASE, "defaultAction": action})


def test_baseline_digest_and_duplicate_fields_refuse():
    with pytest.raises(KernelPolicyRejected):
        build_kernel_policy(ELF, docker_default=canonical(BASE), docker_default_sha256="c" * 64)
    raw = b'{"defaultAction":"SCMP_ACT_ERRNO","defaultAction":"SCMP_ACT_ALLOW","syscalls":[]}'
    with pytest.raises(KernelPolicyRejected):
        build_kernel_policy(
            ELF, docker_default=raw, docker_default_sha256=hashlib.sha256(raw).hexdigest()
        )


@pytest.mark.parametrize(
    "path",
    [
        "/inputs/payload.so",
        "/output/x.so",
        "/usr/local/../inputs/x",
        "/usr/lib/*",
        '/usr/lib/"x",',
        "/usr/lib/x\n/** mrwx,",
    ],
)
def test_untrusted_paths_and_policy_grammar_injection_refuse(path):
    with pytest.raises(KernelPolicyRejected):
        build({**ELF, path: "c" * 64})


def test_apparmor_executable_permissions_bind_only_measured_paths():
    text = build().apparmor.decode()
    mappings = [
        line.strip().removesuffix(" mr,")
        for line in text.splitlines()
        if line.strip().endswith(" mr,")
    ]
    assert set(mappings) == set(ELF)
    assert "/** m" not in text
    assert "/inputs/** r," in text and "/output/** rwk," in text
    assert "complain" not in text and "unconfined" not in text


def test_policy_identity_changes_with_source_or_default_policy():
    first = build()
    assert first == build(dict(reversed(list(ELF.items()))))
    second = build({**ELF, "/usr/lib/x86_64-linux-gnu/libc.so.6": "d" * 64})
    third = build(base={**BASE, "defaultErrnoRet": 13})
    assert len({p.sha256 for p in (first, second, third)}) == 3
    assert len({p.name for p in (first, second, third)}) == 3


def mountinfo(
    extra="", *, input_options="ro,noexec", root_options="ro", output_options="rw,noexec"
):
    return (
        f"1 0 0:1 / / {root_options} - overlay overlay ro\n"
        f"2 1 0:2 / /inputs {input_options} - ext4 /dev/vda1 rw\n"
        f"3 1 0:2 / /output {output_options} - ext4 /dev/vda1 rw\n"
        "4 1 0:3 / /tmp rw,noexec,nosuid - tmpfs tmpfs rw\n" + extra
    ).encode()


def test_actual_noexec_mount_semantics_pass():
    verify_mountinfo(mountinfo("5 1 0:4 / /dev rw,noexec,nosuid - tmpfs tmpfs rw\n"))


@pytest.mark.parametrize(
    "change",
    [
        {"input_options": "ro"},
        {"input_options": "rw,noexec"},
        {"root_options": "rw"},
        {"output_options": "ro,noexec"},
        {"output_options": "rw"},
        {"extra": "5 3 0:5 / /output/nested rw - tmpfs tmpfs rw\n"},
        {"extra": "5 1 0:5 / /dev rw - tmpfs tmpfs rw\n"},
        {"extra": "5 1 0:5 / /output rw,noexec - tmpfs tmpfs rw\n"},
        {"extra": "5 1 0:5 / /inputs/nested ro - ext4 /dev/vda1 ro\n"},
    ],
)
def test_actual_mount_changes_fail_closed(change):
    with pytest.raises(KernelPolicyRejected):
        verify_mountinfo(mountinfo(**change))


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"garbage",
        mountinfo().replace(b"/tmp", b"/other"),
        mountinfo() + b"\x00",
        b"x" * 1_048_577,
    ],
    ids=["empty", "malformed", "missing-tmp", "nul", "oversized"],
)
def test_missing_malformed_or_oversized_mountinfo_refuses(raw):
    with pytest.raises(KernelPolicyRejected):
        verify_mountinfo(raw)
