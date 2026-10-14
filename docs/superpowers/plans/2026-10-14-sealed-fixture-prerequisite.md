# Sealed fixture prerequisite implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Root executes this finite prerequisite within the previously approved Option A method; one new bounded review covers the replacement only.

**Goal:** Prove bounded canonical Parquet reads consume immutable kernel-sealed data through a live descriptor after the original pathname is replaced.

**Architecture:** The ordinary held-FD candidate FAILED because DuckDB1.5.5 canonicalizes its allowlist to the mutable filename. Keep both actual failed phases and stop that route. Copy bounded bytes from an independently held no-follow file into a non-executable sealed anonymous memfd, then hold it throughout a disarmed connection using its actual PID/FD alias. This finite observation is not full native/kernel/image/Worker admission.

**Tech Stack:** Existing AWS093b4734, CPython3.12.15, DuckDB1.5.5, Linux memfd/fcntl, fixed parent observer.

**Spec:** docs/superpowers/plans/2026-10-13-worker-lineage-root-ruling.md

## Global constraints

- Same Engine/image, no new environment/image/wheel/clone/paid resource, no production services/model/network/trading.
- Same450,000B G1 source/evidence/copies reservation and25,800,000B software ceiling from original8,876,772B baseline; AWS original5GB/free50GB. Preserve all failures.
- One new exclusive canonical-parquet-sealed-fd phase; bind prior actual schema e603a5cb and diagnostic failure0d741360.
- Fixed Docker512MiB/1CPU/32pids/16MiB noexec tmpfs, read-only rootfs/no hostmounts/no network/capabilities, CORE0/dumpable0, childCPU10s/FSIZE1MiB, parentdeadline30s.
- NO mutable ordinary-path fallback or broaddirectory allowlist. Unsupported MFD flags/seals/current settings refuse.
- Full executable mmap/mprotect/seccomp/native-load proof stays pending: NOEXEC_SEAL alone is not that proof.

## Review focus

- File replaced after source FD is opened: sealed bytes/hash and decoded original OHLCV stay exact.
- Descriptor reused or closed too early: hold descriptor throughout queries; exact identity/hash/seals before and after.
- Kernel ignores/does not support sealing or noexecute: read actual F_GET_SEALS/mode, require WRITE/GROW/SHRINK/EXEC/SEAL; nonempty pwrite/shrink-to-zero/grow-by-one/chmod-X refuse with EPERM.
- DuckDB resolves proc/self parent: use observed numeric PID alias; configuration readback exact, sibling FD and ordinary path refuse with unchanged settings.
- Any failure: retained bounded child output plus actual Docker timings and verified owned cleanup; no success-only authority or production certificate.

### Task1: finite operator/child and parent proof

**Files:** Create output/0038-held-fixture-reader/check_sealed_observer.py, sealed_child.py, probe_sealed_fd.py, execute_sealed_fd_ssh.py. Keep all prior files unchanged.

**Interfaces:** Retain existing validate_observation(d,o); add validate_sealed_observation(o) requiring actual kernel seals/identities/hashes and exact case set. Dispatcher transfers only exact frozen owned operator bytes and refuses pre-existing phase.

- [x] Write scripted failing observer examples for mutable paths, missing seals, executable mode, changed bytes/inode, absent/false/duplicate cases and source mismatch; run RED before implementing.
- [x] Generate two canonical two-row original/sibling fixtures with existing restricted writer, then no-follow bounded read into MFD_CLOEXEC|MFD_ALLOW_SEALING|MFD_NOEXEC_SEAL(0x8), mode0400. Add WRITE8|GROW4|SHRINK2|EXEC32|SEAL1 and verify required bits47 present before and after; record any additional FUTURE_WRITE bit.
- [x] Replace original pathname with sibling bytes. Hold original and sibling sealed FDs; use only canonical /proc/{actualPID}/fd/{fd} in fresh connection with externalfalse/locktrue/directoriesempty.
- [x] Run bounded metadata and primitive queries; require original schema/rows. Exercise actual nonempty pwrite/shrink/grow/chmod-X refusal, direct pathname/sibling FD refusal, bytehash and identity/seal stability.
- [x] Pass scripted observer examples, AST/source-bound review, resource preflight before executing the one fixed actual phase.
- [x] Recover/hash-check actual raw receipts; revalidate saved actual fields and cleanup. Only an actual PASS permits freezing the future job-wide reader.

References: DuckDB v1.5.5 config.cpp753-805 and local_file_system.cpp1342-1415; Linux docs.kernel.org/userspace-api/mfd_noexec.html. Source behavior is a hypothesis until the actual bounded phase passes.

Actual acceptance: source93da1b0e/child071fd24b,02:23:51–02:23:54UTC,
exit0/all9cases/seals47/noOOM/PID0/ownedCIDremoved. Raw receipt50334ba2 and
outputd1238efd are byte-exact and checked; see durable aws-parquet-reader
evidence. Transfer pin P2 resolved with RED3/GREEN4. This finite prerequisite
is complete; future job-wide reader and all full native/kernel/Worker admission
remain pending. Both actual failed ordinary-FD phases stay preserved.
