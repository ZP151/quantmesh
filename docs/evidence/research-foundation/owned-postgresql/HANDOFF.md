# #171 owned PostgreSQL qualification handoff

Readiness: **bounded local real-PostgreSQL acceptance complete**, ready for root
integration. Full approved A goal remains active. No whole-platform, Worker,
OCI, real model, server, TLS/HA/backup or financial-performance certification.

Commit: `f525d91065616d3c4f2cce9cd97cdc9fd53cbf5c`.
Branch: `codex/0038-owned-postgres`; normal origin push, no merge/deploy/force push.
Frozen integration/source baseline: `42fbfa510b8153c7a2b3b6fd3e5d4851eda850e8`.
The branch starts directly at that baseline; local main was not changed.

Only changed tracked files:

- `tools/qualify_owned_postgres.py`
- `tests/test_owned_postgres_fixture.py`
- `docs/runbooks/owned-postgres-fixture.md`

Root owns iteration/ACTIVE/ADR/REUSE_MATRIX and shared integration. Mirror this
evidence there; no shared file, service/store, gate, package lock or original
test assertion was changed by this slice. No production defect was exposed.

## Planner

One operator action: explicitly run a disposable owned PostgreSQL fixture and
the existing independent default service gate. Measurable result: 30 tests,
zero skips/errors/failures, exit0, plus actual ownership and safe shutdown.
Plan: `docs/superpowers/plans/2026-10-13-owned-postgresql-qualification.md`.
Issue: https://github.com/ZP151/quantmesh/issues/171.
No production/user data, paid resource, model call, global installation, daemon,
OS user, source/vendor/GUI/helper/tunnel/AWS/trading operation or third review.

## Quant researcher

Synthetic lake fixtures only; no new dataset, strategy, return claim or source
qualification. Fees/spread/slippage/model semantics were not changed. The real
SQL cases exercise idempotency, two shared active slots, fencing, reopen,
cancellation, actual-byte integrity, transactional rollback/version refusal and
concurrent effect reservations. Injected lease-clock tests do **not** establish
the separate real 90-second Worker crash/recovery witness under #172.

## Implementer

Privately built genuine PostgreSQL18.6 as WSL Ubuntu uid1000 on persistent native
Linux storage `/var/tmp/quantmesh-owned-pg-0ue7gicj` (0700). Fresh own source
checkout from Git bundle at the frozen baseline, and fresh CPython3.12.3 venv.
The original root native environment remained read-only; only its existing pip
bootstrap package was copied into the new empty --without-pip venv. Actual
81 wheels subsequently installed with unchanged Linux lock and --require-hashes;
raw install log is `prepare.log`. The existing Windows closure is untouched.

Official source URL:
https://ftp.postgresql.org/pub/source/v18.6/postgresql-18.6.tar.bz2
Published/actual source SHA256:
`555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f`.
Official COPYRIGHT SHA256:
`3d6af92ff8a4c2cdf69afb1cf44edea727922f5cd0cf8b5f72b11cdecac8fdfd`.
PG permissive license and copyright retained in `build-proof`/`runtime-binaries`.
No upstream code embedded in the tracked repository.

Build tools Bison2:3.8.2+dfsg-1build2/Flex2.6.4-8.2build1/m4 1.4.19-4build1
were dpkg-deb-extracted only into owned prefix. Official Ubuntu Noble Release
signature verified with existing Ubuntu archive keyring (signer
F6ECB3762474EDA9D21B7022871920D1991BC93C); index SHA256 checked against that
signed Release; each package SHA256 checked against index. Deb bytes, dependency
fields, compiler/make/Perl/tool versions, executable hashes and copyright
retained. GPL Bison/m4 remain external build tools, not service-runtime packages.
`build-proof/build.json` records all exact package hashes/configuration.

Build:
`./configure --prefix=/var/tmp/quantmesh-owned-pg-0ue7gicj/prefix
--without-readline --without-zlib --without-icu`, `make -j4`, `make install`.
PATH/BISON_PKGDATADIR/M4 select the privately extracted tools. GCC13.3.0,
GNU make4.3, existing Perl; no pkg-config required for disabled ICU.
SSL disabled by default; no ICU/readline/zlib. `ldd.log` records libc/libm
runtime links. This local C/UTF8 fixture profile does not certify production.

Installed binary SHA256 (also independently archived/rehashed):

| Binary | SHA256 |
|---|---|
| postgres | `4cd5ef0c0632e8da70fd6d7a62a9e02a6df00f3517b1b5720511db199d825d08` |
| initdb | `ec107de4c2da562b0001811e63b79793433c28267e35883a80fd55fba7d019e2` |
| pg_ctl | `4122dcb4375873bca2dcd2f83242614c21f28d4ebd872d06ab702a0ab26ae159` |
| pg_controldata | `a8352343c4773b7138e3c9547223e68252021fcde0ec696575f30c37d8bb06ff` |

Construction-time immutable profile refuses external DSNs/commands, nonofficial
source/license/binary identity, borrowed paths and unsupported runtime.
Default preflight starts no DB. Explicit fixture: new cluster, literal loopback,
fresh synthetic role/password; temporary0600 input, no secret argv/receipt.
Minimal subprocess environment contains no inherited account/model keys and
disables tracing. DSN/owned acknowledgment enter only the owned gate subprocess.
Actual PID/executable/hash/UID/data/start ticks, ownership nonce, pg_controldata
system ID and authenticated SQL identity fence SQL and cleanup. No port fallback.
Tracked source changes and untracked shadow modules are refused before driver
imports; checkout/venv linked paths refused. Actual store/contract/driver import
paths and hashes are recorded and checked. No schema/protocol change.

## Reviewer

Two independent Spec/Standards rounds on new qualifier only. Spec R1 clear;
Standards R1 two P2 admission gaps (linked checkout/venv and shadow source modules).
Both reproduced via behavior tests, corrected, then final Spec/Standards R2
clear. Reports: `spec-round1.md`, `standards-round1.md`, `spec-round2.md`,
`standards-round2.md`. No third original service architecture review.

## Verifier

Final native helper/tests match committed source bytes. Targeted qualifier
33pass/0skip/0failure in0.26s; Ruff check/format and Git diff checks exit0.
Final explicit fixture default gate **30pass/0skip/0failure/0error in14.41s**, exit0,
two upstream deprecation warnings. All five genuine PostgreSQL cases in JUnit.
81 licensed pinned distributions, failures[], five gate commands all exit0.
Frozen schema `a645a8bde2b439587f736a6a6875e4ffae77265cdcc2900d0b2def43f5f0de18`
and nine-method protocol `454cce6bd355465e48a59cb61fbbacb775776cb28c41826e54aff554cf2ccae1` unchanged.

Final server: PostgreSQL18.6, own PID672/startticks13643,
127.0.0.1:57067, own new `cluster-oczwtb3o`, system identifier
7695892359569789595. SQL driver pg8000 1.31.5 from own venv; raw imports/byte
hashes in `final-fixture/imports.json`. Final gate JUnit/JSON/logs agree.
Fast shutdown/child wait completed. Independent post-run audit confirms PID
file absent, owned port closed, password inputs absent and binary digests match.
Safe source/install/new data artifacts retained; no listener/system service remains.

Preserved earlier evidence: unsupported --without-ssl configure failure;
Bison initially tried system m4 before explicit private M4 binding; system venv
ensurepip absent; failed shell variable expansion; initial18-test helper trial;
first valid actual service gate30pass/14.10s before stricter receipt checks.
Windows native-permission test attempts remain as failed evidence, followed by
actual admitted Linux behavior checks. No failing production assertion was hidden.
Native strict-count RED6fail/24pass then GREEN30pass; final admission
RED3fail/30pass then GREEN33pass. Original build/test raw logs and exit files
are retained. The shell-expansion and ensurepip intake failures are recorded
in this task's tool transcript; prepare.log contains the successful replacement.
No broad core/all-suite/hour-long rerun.

Authoritative raw proof in this managed worktree's ignored
`output/171-owned-postgres/`:

- `build-proof/`: signed archive metadata, downloaded verified bytes, notices,
  configure failures/success, make failures/success, install and binary receipt.
- `runtime-binaries/`: actual four measured binaries plus COPYRIGHT.
- `prepare.log`: own exact-source/native lock installation.
- `final-proof/`: qualifier33pass, Ruff/format/preflight/fixture logs and exits.
- `final-preflight/preflight.json`: no database startup.
- `final-fixture/`: authoritative fixture/imports/control/initdb/server/stop,
  default gate logs/JSON/JUnit plus test artifacts.
- `cleanup-audit.json`, `measured-helper-hashes.json`, RED/GREEN and review files.
- `proof-sha256.json`: raw proof file inventory with actual SHA256 values.

Root follow-up: integrate this exact commit and archive selected immutable raw
proof into shared evidence; update REUSE_MATRIX/iteration/ACTIVE as owner.
Keep PR166/source recovery, Docker Engine/OCI, actual Worker/model caps and
private server/provider qualification pending. Do not reopen their human
questions or mark full A complete. This branch performs no PR/merge/deploy.
