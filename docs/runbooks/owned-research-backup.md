# Owned local encrypted research snapshot qualification

Issue [#171](https://github.com/ZP151/quantmesh/issues/171), bounded continuation
of [Task4](../superpowers/plans/2026-10-12-research-workers-workstation.md).
Scope is `OWNED_LOCAL_FIXTURE_ONLY`, `production_release_qualified=false`.
This qualifies local PostgreSQL/restic storage and replay, with explicitly
labelled contract-fixture reports. Actual numerical Worker execution/recovery,
off-host backup, production TLS/HA, capacity/p95, human acceptance, final CI and
private deployment remain pending.

## Exact source and native prerequisites

Start at frozen `0503d49a51fdd20b08c809f4289092fbac01ebf9`, preserving main.
The clean committed candidate must add exactly this runbook,
`tools/qualify_research_backup.py` and its dedicated test file. No shared
store/service/gate/lock changes are admitted. Use an independent native Linux
ext4/xfs/btrfs root `/var/tmp/quantmesh-backup-*`, non-root, mode0700, containing
`checkout`, a fresh `venv`, `prefix`, `home`, `tmp` and audited tool receipts.
CPython3.12 x86_64 and the unchanged 81-wheel service lock are required. Install
with `--require-hashes --no-compile`; retain wheel hashes and licence inventory.
No executable bytecode or untracked source shadows are admitted. The existing
bootstrap source/dependency admission functions are reused without modification.

Read the [PG fixture runbook](owned-postgres-fixture.md). Read-only reuse of
`/var/tmp/quantmesh-owned-pg-0ue7gicj/prefix` is confined to measuring and copying
its PG18.6 toolchain into the NEW root, including `pg_dump`/`pg_restore` and
`COPYRIGHT`. Rehash all six binary pins and the complete copied prefix. Runtime
uses its own `LD_LIBRARY_PATH` for the copied libpq. Never reuse the old cluster,
role, environment, data directory or credentials. This PG build's C/UTF8 and
no TLS/ICU/readline/zlib limitations remain unchanged.

## External-tool admission before execution

Download actual [official restic0.19.1 release bytes](https://github.com/restic/restic/releases/tag/v0.19.1).
The linux_amd64.bz2 asset is10107515bytes, SHA256
`f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c`.
The decompressed executable SHA256 is
`20d4142678d0d95ec11a4759def1b73fd9190abc9ca19e4b62d067c0b387e639`.
No self-update, PATH fallback or runtime download is supported.

Validate official `SHA256SUMS.asc` with a private GPG keyring, against the
fingerprint `CF8F18F2844575973F79D4E191A6868BD3F7A907` published by
[upstream installation documentation](https://restic.readthedocs.io/en/stable/020_installation.html).
Download the key only from `https://restic.net/gpg-key-alex.asc`; retain actual
key, documentation, checksum, signature, release metadata, and verification
output. Verify the official source archive's separate signature too. HTTP403
or unavailable signatures are failures; an official GitHub asset API download
may be used, with original failures retained and final bytes checked.

Retain restic's BSD-2-Clause LICENSE, Go1.26.4 LICENSE and exact static build
info. The qualified executable contains79 Go modules; fetch their exact public
module archives, verify the Go h1 directory hashes against binary build info
and signed-source `go.sum`, and preserve98 licence/notice files. The measured
external CLI closure contains Apache-2.0, MIT, BSD and MPL-2.0 notices. MPL
module source is retained outside Git with the other unmodified module source.
No dependency is embedded in the core or service runtime. Public audit/build
downloads are distinct from the strictly loopback/local-filesystem runtime.

The audit manifest `tool-admission.json` at the new root has SHA256
`04f5852137b8e35503a1f12c8d431cf747cf258371f8ec7b7eb77c3dd41b8826`.
It binds950 actual tool/source/notice/prefix entries. The qualifier rechecks
every file/link and verifies the checksum signature with read-only `gpgv` before
any restic execution. A caller cannot replace qualification with a passing
boolean or an arbitrary binary hash. Construction scripts, full audit manifest,
public notices and raw failures are retained in ignored `output/171-owned-backup`;
upstream source/binaries stay outside Git. A newly rebuilt audit requires a
separate reviewed admission update, never silent pin replacement.

## Read-only preflight and explicit fresh fixture

Write an explicit private profile with exactly three fields:

```json
{"schema_version":1,"root":"/var/tmp/quantmesh-backup-OWNED","expected_build":"<clean committed candidate full SHA>"}
```

From the native checkout, using its own interpreter:

```sh
"$OWNED_ROOT/venv/bin/python" -B tools/qualify_research_backup.py \
  --profile "$OWNED_ROOT/profile.json" --output "$OWNED_ROOT/proof-NEW"
"$OWNED_ROOT/venv/bin/python" -B tools/qualify_research_backup.py \
  --profile "$OWNED_ROOT/profile.json" --output "$OWNED_ROOT/proof-NEW" --owned-fixture
```

Replace the placeholders with measured owned paths and SHA. Default preflight
validates source/runtime/tool/notice identity and prints scrubbed metadata; it
creates no output, DB, repository, job or effect. The explicit option requires
a fresh output path and creates all clusters, roles, artifact roots, repository
and synthetic passwords itself. Existing targets, paths with links/traversal,
DSNs, cloud URLs, credentials, alternate commands and ambient configuration
are refused. Passwords enter fixed tools through0600 files and never argv;
all subprocesses receive a bare environment. Secret input files are removed.

The whole fixture has an owned process wall timer of240seconds, including
SQL and filesystem stages, plus bounded ownership-checked cleanup. External
commands each have≤40seconds and≤2MiB output; independent pipe collectors drain
PG logs while saving at most2MiB per server. WAL/data writes are not capped by
the log limit. SQL and startup have shorter deadlines. No global package/user/daemon/Docker operations,
production overwrites, repository pruning, cloud account or old service stops
are performed.

## Consistency, restore and negative evidence

The original frozen fixture publisher seeds one real SQL succeeded job with
`result.fixture=true` and a nonempty report reference, plus queued/cancelled jobs
and completed/reserved effect records. These synthetic bytes are not a
contained numerical Worker result, performance score or strategy/ROI claim.

A repeatable-read read-only transaction exports one PostgreSQL snapshot.
`pg_dump --snapshot` captures only the research schema. Captured SQL records
determine the exact report/analysis artifact set; every job/request/idempotency
identity, byte SHA/size and job-owned relative reference is checked before a
manifest is written. Never copy the live PostgreSQL data directory. Restic
backs up only the dump, manifest and referenced immutable bytes into a NEW
local encrypted repository. `check --read-data` and a second bundle validation
precede the separately anchored backup receipt.

Only after capture, mutate the actual source: cancel its queued record and add
a new job. Restore the encrypted snapshot into a NEW filesystem and independent
PG cluster/role. Compare full captured SQL tables (including outbox, sequence,
effect state), schema/protocol and all bytes, then exercise idempotent reopen
and cancel. Completed/reserved effects must refuse another reservation without
calling any model. Restoration must preserve the old queued state and exclude
the new source job.

Require real wrong-key refusal (actual exit12 and matching JSON error),
corrupt encrypted-object refusal (actual exit1 plus ciphertext-verification
error) in a newly
owned repository COPY, missing/substituted artifact and manifest refusal, and
actual incompatible restored SQL schema rejection. Each negative witness checks
the advanced source SQL is unchanged. Infrastructure/admission/ownership/timer
failures propagate as failures; they cannot qualify as expected negatives.
Retain the clean success and failures
separately. Before cleanup, verify kernel PID/start ticks, executable path/hash,
UID, argv/data path and private nonce handle. Generated private inputs are
removed even on failed spawn or refused process cleanup; unknown process
identity still grants no stop authority. A known sibling PG process must
survive individual restore/source shutdown; close only these NEW owned processes.
During the small spawn/handle-registration window, deadline delivery is deferred
until the owned child is recorded; an expired deadline then fails immediately.
Unavailable kernel start identity remains registered as pending and grants no
stop authority. It cannot disappear from cleanup evidence or qualify as success.

Read `witness.json`, `backup-receipt.json`, captured/restored payloads,
`source-state-after.json`, `restore-state-before-replay.json` and raw command
exits, not just flags.
Successful qualification requires all six negatives, actual decrypted-byte and
SQL continuity, zero cleanup failures and exit0. The final clean candidate gets
fresh native evidence after review fixes. Root independently verifies and
integrates the handoff; production release stays false. Production recovery
password custody in a human vault is separate from these disposable fixture
keys, which are never exported in the proof archive.
