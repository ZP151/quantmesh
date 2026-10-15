# Task177 bounded implementation review

Scope: the current parent-snapshot plan and exactly four unstaged implementation/test files, not the old native architecture or whole branch. Actual reviewed SHA256:

- `src/quantmesh/research/fixture_snapshot.py`: `fa8fed3deaf4a1d4c20b71793d4620b8be658117802750da105371db18d01c72`.
- `src/quantmesh/research/job_runner.py`: `1a9503a81717831fc56de5bc3048b7be67a73b00e28968cb536ab2fe79eba36b`.
- `tests/test_fixture_snapshot.py`: `2a0be5604b687d20cc75bd5e20dbd33ac76b9ae06595642276c6e982cc621881`.
- `tests/test_research_job_runner.py`: `879cbed5aeb7510126f07f45010c6b0f998779b8d80766e48a9285c85e12291a`.

## Finding

**P2 — Anchor ancestor traversal and file creation against transient path replacement** (`fixture_snapshot.py:38–40,63–79,90–97,110–119,141–155`). The directory cache compares only dev/inode/mode; `os.open(path)` and `os.open(target)` resolve complete pathnames, while O_NOFOLLOW protects only the leaf. A checked ancestor can be renamed aside, replaced temporarily by a symlink to that moved directory for an open/read/write, then restored before the postchecks. File identities remain the same, and ancestor ctime changes are ignored, so the current checks can accept the operation despite following a link during I/O. For a destination ancestor moved outside the attempt, writes occur through that transient namespace outside the intended path before restoration. Anchor traversal/file opens and creation to held no-follow directory handles, with the intended directory associations checked, or supply an equivalent guaranteed primitive for the supported platform. Keep the bounded buffers, digest repins and sanitized refusal; this finding does not request native admission, shared Lake changes or a general kernel review. This is a static syscall-order counterexample, not a newly executed race test.

## Other scoped conclusions

No additional substantive P1/P2 found in the new metadata/digest/interface/order paths. `_snapshot` verifies queued request/implementation digests and delegates to byte copying; it no longer invokes Lake/content validation or pin_fixture_dataset. The helper bounds the initial manifest before reading, rejects duplicate JSON keys and nonfinite constants/overflow, validates DatasetManifest and walks typed coverage. Manifest/coverage/shard/aggregate/chunk limits precede large reads and allocations; deadline checks occur between discovery and bounded I/O. These checks do not preempt a filesystem syscall blocked in the kernel.

Export hashing matches the existing sorted relative-path/SHA JSON representation. Source prepin/expected descriptor identities, postcopy source repin, destination digest repin and exclusive target creation cover the persistent mutation/replacement cases exercised by the retained tests; the transient ancestor gap above remains. Parent does not parse Parquet or claim schema/cardinality/chronology validation. Child runtime fingerprint and bounded stable runtime receipt precede JobRecord decoding and `_verify`; actual content `_verify` remains both before and after numerical work. Four-argument run_next_job and report/store/window interfaces remain unchanged. O_BINARY is included for new byte reads/writes on Windows.

## Evidence and platform limits

Read four source hashes and existing handoff/source-hash receipt. Inspected final-targeted log/exit: 44 passed, one incumbent warning, exit 0. Affected log/exit: 91 passed, 21 existing Windows-only skips, one pilot deselection, exit 0; separate pilot: one passed/exit 0. Lint/format/diff-check exits are 0. These are retained executions, not tests run by this reviewer.

Current-source Windows Python 3.13.9 boundary evidence is **not fully green**: 26 passed, three skipped, four failed/exit 1. Three failures occur during symlink fixture setup without Windows symlink privilege; they do not demonstrate either refusal or acceptance of the security case and must be represented as unsupported fixture capability, not safety passes. The long-path destination_inode case refused before the mutation marker. The independently inspected short-owned-basetemp rerun reaches that case and passes/exit 0, so the first result alone is not evidence of a missed inode-replacement check. No Windows policy or privilege change is inferred.

No source edits, tests, AWS operation, native execution, integration, commit or broad structural review performed by this reviewer. G1/G3 physical-schema/cardinality/DuckDB policy and complete native/runtime/image/config/CID/kernel qualification remain unaccepted. This review does not certify numerical admission, recovery or full Option A completion.
