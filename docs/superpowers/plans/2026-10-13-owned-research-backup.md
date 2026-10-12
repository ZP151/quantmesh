# Owned Research Backup Qualification Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans, test-driven-development and verification-before-completion. Follow the new backup slice's bounded two-axis review, not the completed service architecture review.

**Goal:** Prove consistent encrypted PostgreSQL/artifact backup and fresh-target restoration on newly owned local fixtures before any paid/off-host deployment.

**Architecture:** Reuse official restic0.19.1 as an external CLI and the verified PG18.6 toolchain. Source and restore clusters, roles, secrets and local backup repository are NEW under one owned native root; no supplied existing DSN, cloud repository or arbitrary command is admitted. Dump the research schema from one snapshot, then capture exactly referenced immutable artifact bytes and a checked manifest. Restore to a distinct fresh cluster and revalidate the frozen store/record/byte contracts.

**Tech Stack:** Existing separately locked LinuxCPython3.12/81-wheel service environment, genuine owned PG18.6, SHA-pinned external restic, standard library verifier. No new core/service dependency or handwritten encryption.

**Spec:** docs/superpowers/specs/2026-10-12-research-foundation.md; Task4 in2026-10-12-research-workers-workstation.md; docs/runbooks/research-service.md review/consistency rule. Issue#171, iteration0038; paid/off-host/production acceptance remains separate.

## Global Constraints

- Two sessions maximum: this backup plus the new LinuxSDK69d3 verifier; completed source/service/PG/Eval/Worker stay idle. Root owns shared app/store/gate/locks/REUSE/ADR/ACTIVE/iteration and integration.
- No operational AWS/S3/billing/account/auth/vendor/source/Windows/helper/tunnel/global package/user/daemon/Docker/production operation. Runtime network is local loopback only; official public artifact/signing/licence downloads for build qualification are allowed. This CLI cannot target an existing or remote repository/database. No real model, strategy or Worker execution; no retired168h.
- Official restic compressed asset size10107515/SHAf415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c; verify downloaded bytes plus official checksum/signature/signing-key provenance and licences before execution. Do not silently drop signature/audit on failure. No upstream source/binary is committed.
- Read-only verified PG binaries/source build/notice may be reused from /var/tmp/quantmesh-owned-pg-0ue7gicj, but never its old cluster/env/state. Measure pg_dump/pg_restore against that known build before copying to new owned prefix. No system package install or weaker DB version.
- Only new files: tools/qualify_research_backup.py, tests/test_research_backup_qualification.py, docs/runbooks/owned-research-backup.md. Scripts/raw proof/notices in ignored output/171-owned-backup. Do not modify other tracked paths.
- Default preflight has no DB/repository/side effects. Explicit --owned-fixture creates only fresh roots/roles/clusters and synthetic key material through0600private files. Bare subprocess env, fixed commands, no secret argv/raw exceptions/output/credential/archive. Profile rejects URL/DSN/password/arbitrary command and borrowed paths.
- Seed real SQL jobs and referenced reports using the existing service contract-fixture publisher, explicitly result.fixture=true. This is byte/storage/crypto/replay verification, not a contained numerical Worker or strategy/model/report-performance success. Require nonempty references; no empty DB/artifact-set substitute. Production acceptance needs actual Worker-produced reports and off-host recovery later.

## Review Focus

1. A dump paired with incomplete/mutable/mismatched artifact bytes cannot publish a backup receipt.
2. Restoring while source advances must retain the captured state; silently recopying live data is not recovery.
3. Wrong password, corrupted encrypted objects or substituted manifest must fail and leave source untouched.
4. Borrowed cluster/repository/path/symlink/owner/nonce or unverified PID cannot authorize any restore/stop/prune.
5. Synthetic artifacts/local encryption cannot certify off-host storage, native Worker recovery or production release.

## One bounded executable qualifier

- [x] TDD refusal/consistency tests: profile rejects external DSN/repository/credential/commands, borrowed/symlink/unsafe roots, existing restore target; absent/mismatched/non-job-owned artifacts, changed manifest, wrong schema/protocol, missing actual tool/pin and partial receipt never pass. Preserve RED/GREEN with new owned basetemps. Use existing frozen methods and validators, not a new state machine.
- [x] Qualify official restic bytes/signature/licence in a fresh owned prefix. Inspect existing Go licence/dependency provenance as external-tool evidence; no runtime embedding. Retain notices/version/actual executable digest and use --pull/no-auto-update equivalent fixed local binary behavior. Missing trusted signing identity or licence stops before tool execution.
- [x] Build a fresh own native checkout/env matching exact committed candidate and the81wheel lock. Rehash copied PG toolchain/notices, start only a new loopback cluster/role through private temporary input, and verify PID/start/executable/data/SQL system identity before use. Unknown identity is pending/failure, no borrowed DB fallback.
- [x] Implement real pg_dump schema snapshot → nonempty referenced immutable artifacts/SHA-size manifest → restic local encrypted repository snapshot. No live datadir copy, opaque provider URLs, user commands or backup of credentials/vendor state. Check all references before receipt publication. Password recovery mechanism for production is human vault, never inferred from an own test key.
- [x] Actual native run must create at least one labelled fixture success with nonempty report ref plus queued/cancelled records, capture snapshot, then change source state AFTER snapshot. Recover from encrypted data into a new distinct cluster/artifact target; compare captured job/request/idempotency/schema/refs/bytes/effect state using actual SQL and existing store. No production overwrite/down migration. Source mutation after capture must not appear as restored snapshot state.
- [x] Actual negative witnesses: wrong repository key, corrupted copy of a newly owned encrypted object, missing/substituted artifact/manifest and incompatible restored schema fail without changing source. Do not prune or delete global/old repositories; only mutate explicitly newly owned corrupt-copy fixtures. Record original clean success and all failures separately.
- [x] Close only new owned source/restore/helper/sibling resources after kernel/process/data/nonce identity checks; known sibling survives individual source/restore shutdown. Preserve receipt and raw tool exits without passwords, DB credentials or private logs. Overall witness has bounded time/output; no unbounded waits or global cleanup.
- [x] Relevant focused tests/Ruff/format/diff and new backup Spec/Standards max2rounds, including actual evidence. Final freshly committed native proof after fixes; no third completed service/PG/source architecture review, no whole core/hourly suite.
- [x] Commit only3ownedfiles, HANDOFF exactSHA/changedfiles/audit/rawcounts/checks/exits/limits and stop. Root archives/integrates. Final status must state OWNED_LOCAL_FIXTURE_ONLY and production_release_qualified=false; off-host/paid production backup, actual report execution/recovery, p95/human/CI/deployment remain pending.

Planner: one recoverable encrypted snapshot with observable hash/state continuity.
Researcher: synthetic contract artifacts only, no returns or model effects.
Reviewer: consistency, secret/ownership/recovery boundaries and external-tool
licences. Verifier: real PostgreSQL/restic crypto/restore and negative refusal,
not fake saved booleans; no off-host or whole A qualification claimed.

Root local acceptance:4fceaf2 integratedsixleafcommits, root2dd5f4a testplatformclassification only; native45/0skip, service85/0skip, actualSQL/crypto/report recovery and198rawstreams verified. Production/offhost/actualWorker gates remain open.
