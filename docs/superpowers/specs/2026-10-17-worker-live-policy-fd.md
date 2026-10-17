# Worker live AppArmor policy FD

Approved by the operator on 2026-10-17 through question item
`call_6ab1860457684097b71f21d845eb8ba3`, answer: 批准此窄设计，继续实现与验证.

## Goal and evidence

Allow the existing UID 10001, capability-free Worker to verify actual loaded
AppArmor policy when opening its kernel `raw_data` node returns EACCES. Native
systemd OpenFile evidence established that a read-only FD 3 references the same
live kernel inode and supports concurrent positional reads without changing its
offset. This is a software correction prerequisite, not completed Worker runtime
acceptance. PR180 is already merged as 6aa231315cf710bfed287337c4a08977665d3731.

## Contract

Preserve ordinary reads. Only EACCES from opening the fixed revision's raw_data
may use inherited FD 3. No caller, environment, request, configuration, or public
constructor can select an alternative descriptor, path, or digest.

Before and after reading, require FD 3 to be a root-owned regular file, opened
O_RDONLY and not O_PATH, with complete fstat identity equal to a no-follow stat
of raw_data in the already-held kernel revision directory. Use bounded pread
with a local offset, handle partial reads until EOF, and reject overflow or read
errors. Virtual st_size zero is valid and is not the stream length. Never close,
seek, or consume the inherited descriptor. Two callers must read independently.

Retain namespace anchoring, revision-link checks before and after the read,
profile identity, enforce mode, ABI and SHA checks, compiled policy pin, all 22
admission pins and existing public interfaces. Stale or replaced descriptors,
changed revisions, and identity changes fail closed. This does not authorize
snapshots as live policy, runtime source patches, host ACL/mode changes, or new
capabilities. The approved root-owned regular-file requirement takes precedence
over the planner's less restrictive type-comparison wording.

## Scope and release

Only worker_admission.py and its admission tests need behavior changes. Reuse
the existing runtime and isolated integration worktree. No dependency changes,
SSH, SQL, model call, deployment, or old acceptance reruns are part of this leaf.
TDD evidence and at most two independent review rounds precede a new exact-head
CI run. Merge requires the new diff's Class C approval by two humans including
SafetyOwner. Earlier PR180 and operator approvals are already consumed.
