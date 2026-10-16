# Plan: Bind Private Snapshot Ownership to the Non-root Service UID

Status: software implementation and two bounded reviews complete; exact-head CI, Class C humans and separate merged-source native acceptance remain open. The original Planner evidence below is retained as the design record.

## Problem and evidence

The exact source is merged e2a commit `e2a69c537e7b2d6e173748162cb01b0dd0b4feb3`, tree `5ffa3eca867bd0a0df7e14e448732d7e7da40094`. Root's native RED is retained under `output/0038-pr178-merged-deployment/identity-snapshot-owner-native-red-20261016/` in the integration checkout. Its prepared systemd process used the actual non-root service identity UID/GID 10001, supplementary docker GID 988, no capabilities, `NoNewPrivileges=yes`, read-only source/runtime binds, and a writable private fixture. It created a synthetic private metadata file owned by UID 10001, mode 0400, single link, then called the actual merged-e2 `worker_admission._read_snapshot_member`. The helper rejected it with `WorkerAdmissionRejected`; the harness exited successfully after recording that expected-vs-actual observation. No SQL or provider call occurred.

This is a narrow native reproduction of the snapshot-member owner mismatch, not full OCI admission, Worker execution, or production recovery qualification. Keep it distinct from the independent live-OCI content-store read gate.

Static inspection of e2a `src/quantmesh/research/worker_admission.py` found seven service-snapshot checks pinned to `st_uid == 1000`: one in `_read_snapshot_member`; root, metadata directory, and per-package metadata directory checks in `_verify_distribution_metadata`; and snapshot root, `empty-config`, and `metadata` directory checks in `WorkerImageAdmission._snapshot`. These checks reject a correct private snapshot created by the approved UID 10001 service. Other UID literals belong to different boundaries: root ownership checks for kernel/AppArmor control files and the OCI image's fixed child user `10001:10001`. Leave those unchanged.

## Chosen correction

Define the accepted snapshot owner as the real UID of the current admission process, derived internally from `os.getuid()`. Reject UID 0 and fail closed when a usable POSIX UID is unavailable. Do not accept an owner from configuration, caller-supplied JSON, admission pins, a new public field, or a new dataclass constructor parameter. The worker admission service is non-root; its process identity is the authority that prepared and reads its private snapshot.

Use the derived non-root UID consistently for all seven checks and for every private snapshot member read. `WorkerImageAdmission._snapshot` must require that UID on its root, metadata and empty-config directories and snapshot files. `_verify_distribution_metadata` must require it on the root, metadata directory and each package metadata directory. `_read_snapshot_member` must accept a regular file only when its owner is the current non-root process UID. A same-UID non-root private 0400 member is accepted; root-owned, foreign-UID, or root-process snapshots are rejected.

Retain existing descriptor-based traversal, no-follow and held-FD identity checks, link-count and regular-file checks, size bounds, hashes, exact directory contents, and modes: private snapshot root/metadata/package/empty-config directories remain 0700, snapshot data members remain 0400, and the untrusted operational receipt remains 0600. Do not loosen mode, ownership, noexec, pin, protocol, or image-child constraints. Keep `WorkerAdmissionPins` at 22 fields, preserve public four-argument construction, and keep child UID/GID exactly 10001:10001.

The implementation should centralize the process-owner rule in one private helper so all three code paths reject root identically and no seventh check is missed. Internal plumbing may pass the derived UID through private helpers if needed to keep one snapshot validation bound to one owner; it must never expose a caller-controlled owner override. Do not replace every occurrence of `1000` in the module: root-owned kernel/AppArmor evidence remains root-owned, and image `Config.User` remains 10001:10001.

## Red-green implementation steps

1. Add focused regression tests before changing implementation. On POSIX under any non-root UID, assert `_read_snapshot_member` accepts a same-UID regular single-link 0400 file and rejects a foreign-UID file; separately assert root admission fails closed. Extend the metadata snapshot test to accept the actual test-process UID instead of assuming UID 1000, while retaining all existing tamper/hash/mode/link checks.
2. Add focused coverage for `_verify_distribution_metadata` and `_snapshot` at a simulated/current non-root UID such as 10001: root, metadata, package, empty-config directories, and files owned by that process UID are accepted; foreign-UID and root-owned variants are rejected. Exercise every former hard-coded comparison, including snapshot receipt mode 0600. Prefer a temporary snapshot fixture and narrow mocks around external image/Engine checks rather than a new service or broader integration framework.
3. Run the targeted tests and confirm the new regression fails against unmodified e2a and passes with the correction. Do not change unrelated constants in kernel/AppArmor or image-child validation to make these tests pass.
4. Run the repository's required platform CI. On POSIX, cover a normal unprivileged runner UID that is not 1000 and the explicit root-rejection case. Keep Windows CI behavior intact: no module-import-time `os.getuid()` call, no unguarded POSIX-only call on Windows, and POSIX snapshot-owner tests must skip cleanly where descriptor/UID semantics are unavailable. Windows tests must not fabricate acceptance of a privileged owner; Linux remains the authority for native snapshot admission.
5. Review the exact source diff to verify no `WorkerAdmissionPins` field, constructor, profile identity, mode, FD/no-follow invariant, source protocol, image child user, noexec policy, or public API changed. Keep any unrelated findings out of this patch.

## Review and completion gates

Limit review to two rounds. Round one checks scope, same-process UID binding, root/foreign-owner rejection, FD and mode preservation, and test coverage. If it requests a correction, make only that bounded correction. Round two verifies the revised diff and targeted evidence. A second structural failure returns the change to Planner for scope reduction; do not start a third review cycle.

Before merge or deployment, require green CI for the exact implementation head and tree, with the target commit recorded in the result. Require a human review of that exact diff and CI result. A later authorized native admission must use the exact reviewed head and show a same-owner private snapshot accepted under UID 10001, while root/foreign-owner controls remain rejected. This native check does not substitute for independent live-OCI read qualification, full Worker job acceptance, or production recovery evidence. Do not activate a worker or alter the independent `/var/lib/containerd` read boundary as part of this correction.

## Acceptance criteria

- One private process-owner rule governs all seven service-snapshot UID checks.
- The actual non-root admission UID is accepted; root and foreign UIDs are rejected.
- All private modes, file types, link counts, hash checks, no-follow/FD checks, 22 pins, public construction, source protocol, and child UID/GID 10001:10001 remain unchanged.
- Tests cover the former seven sites and run correctly on POSIX and Windows CI.
- Exact-head CI and human review pass before merge; any later native admission is separately authorized and does not claim full Worker qualification.

No implementation, tests, native rerun, service action, permission change, or shared-document edit was performed while preparing this plan.

## Root execution binding

Actual base5661033c254700f66e4126ea8782ae2902f4b81d includes merged PR179.
Implementation owns only worker_admission.py and its tests; root owns this plan
and shared records. This security ownership boundary is Class C under the
repository review policy: two independent human reviewers including Safety
Owner, exact-head required CI, and explicit operator acceptance before normal
match-head merge. The approved10001 operational scope is already consumed; it
does not waive new source review. The correction must reject a privileged or
mixed real/effective UID as well as UID0, foreign-owner files and unavailable
POSIX identity. It must not introduce caller-controlled UID fields.

Stages: targeted tests RED, smallest same-owner correction GREEN, relevant
affected checks and static checks; at most two fresh code-review rounds; exact
head CI/human gates; then separate merged-source native gates. No current e2
Worker activation or obsolete-image qualification while the source gate is red.

## Software execution checkpoint

Implemented against actual main5661033c. Runtime source SHA256
3a942a2c1e7e79e975d3cba5fb675d532a274cfcff038c1e506a2964243ff01f;
final tests SHA256865ec3adf61fb2a0eb6b0c000852e4f152040551f545a28c1ce9354bb3a4e977.
The final targeted set passes8tests; all28admission tests pass. Seven isolated
old-comparison mutants each fail the UID10001 positive. Root independently
checks bytes, raw outputs and all seven single-comparison deltas. Round1 P2/P3
test findings are corrected without changing production source; round2 PASS.
All failure artifacts are retained in output/0038-snapshot-owner-fix/.
Full repo Ruff, affected format, whitespace and submodule metadata checks pass.
Existing NumPy warning remains. CI/full Windows/post-fix server-native and
full Worker/recovery are not certified by these software results.
