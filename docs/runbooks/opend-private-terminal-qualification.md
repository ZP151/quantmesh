# Owned local private-terminal qualification

Issue [#169](https://github.com/ZP151/quantmesh/issues/169), iteration0038,
Task2 prerequisite. Scope is **OWNED_LOCAL_PRIVATE_TERMINAL_FIXTURE** only.
This standard-library tool neither starts OpenD nor supplies a login channel.

## Commands and effects

From a native Linux checkout with CPython3.12x86_64 and pidfd support:

```sh
python3.12 -I -B tools/qualify_opend_private_terminal.py
python3.12 -I -B tools/qualify_opend_private_terminal.py --owned-fixture
python3.12 -B -m pytest tests/test_opend_private_terminal.py -q \
  --basetemp output/169-private-terminal/native-test-temp
```

The first command performs no terminal/process/filesystem inspection or creation.
It prints pending/PREFLIGHT_NO_EFFECT and exits2. Only `--owned-fixture` creates
a fresh `/var/tmp/quantmesh-private-terminal-*` root, mode0700, and new PTYs and
fixed synthetic children. No command, TTY path, target directory, credential,
profile or output path is accepted by the CLI. Redirect the whitelisted JSON
to ignored `output/169-private-terminal`; never archive terminal transcripts.
Native tests need the existing pytest tool environment, not a runtime dependency
change. Windows skips explicitly describe missing Linux evidence.

## Admission and actual observations

`inspect_private_terminal(stdin_fd, stdout_fd, stderr_fd, expected_uid=...)`
accepts inherited descriptors. It duplicates them, inspects fstat/isatty,
owner, exact0600 permissions, access direction and termios ECHO/ECHONL, then
rechecks original/duplicate identities and terminal settings. All three must
refer to the same character terminal. Booleans, invalid descriptors/UIDs,
non-TTYs, wrong owner/mode, echo, replacement or unavailable inspection refuse
with a fixed nonsecret code. It never reads terminal input or output, discovers
a terminal path, or returns terminal bytes.

Each synthetic child starts behind a two-second gate. The parent retains its
Popen, opens a Linux pidfd and reads only that owned child's `/proc/.../stat`
and directory metadata. PID, start ticks, UID and directory identity are
registered before release. SIGINT is blocked across Popen/registration and
restored inside the cleanup guard. Release rechecks the inherited terminal
and process identity; the fixed child independently checks its stdio and
claims its new controlling terminal before acknowledging readiness.

Only fixture code creates a random noncredential65-byte marker in memory,
writes it to its own PTY master and consumes a bounded ephemeral master buffer.
A separate control pipe supplies the child's accepted byte count and transient
digest; the digest comparison is emitted only as a boolean. The receipt records
that only the fixed ACK was observed with echo off. Marker, marker digest and
raw terminal bytes are never archived. This is fixture transport/confidentiality
evidence, not a real credential experiment.

Native cases exercise actual controlling-TTY master disconnect/SIGHUP, blocked
input, output growth capped at4096 observed bytes, gate expiry, kernel-rejected
pidfd flags and real SIGINT during registration. Retained pidfds authorize
termination, never a bare PID/PGID. An independently registered known sibling
must remain live after each case. Missing identity/handle closes the gate and
waits for independent child exit without releasing input. Cleanup verifies exit,
reaps owned direct children and closes exact retained descriptors. Incomplete
cleanup returns failed/exit2, never passed.

The common90-second budget includes setup/failure/cleanup: work admissions stop
at80seconds, cleanup waits share an89-second cutoff, and children independently
expire before that common cutoff (maximum85seconds each). Fixed helpers cannot
spawn descendants or accept arbitrary code. The synchronous Linux syscalls are
not an assurance against an indefinitely hung kernel; unknown cleanup fails
closed. No same-UID/root secrecy, OS-wide isolation, journaling configuration,
vendor state or malicious external mutation is certified by this local fixture.
Admission is a point-in-time check; a real launcher must retain/revalidate its
inherited descriptors under its separately reviewed authority.

## Evidence and next gates

Preserve RED/GREEN logs and exits, the exact reviewed commit/file hashes,
native platform/UID/fresh root, whitelisted JSON and the HANDOFF in ignored
`output/169-private-terminal`. The implementer changes only this runbook,
the qualifier and its tests. The coordinator independently checks and archives
evidence and updates shared iteration/qualification records.

Every receipt keeps production_release_qualified,
source_host_private_input_verified, authentication.private_input_verified,
SDK wire, server startup, operator authentication, installation and market
qualification false, even after local success. No shared profile flag is changed.

Actual source-host private input/lifecycle, the separately reviewed one-shot
staging authority/expiry, ClassC CI and two human reviews including the safety
owner, explicit operator authentication window, acknowledged original SDK
transport, source-time/minute/provider/browser acceptance and rollback remain
the gates in [the authentication review packet](opend-authentication-review.md).
This runbook authorizes no installation, SSH/network call, human login, vendor
state reading, service operation, quote-authority transfer or application switch.
