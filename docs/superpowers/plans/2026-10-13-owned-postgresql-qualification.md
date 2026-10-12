# Owned PostgreSQL Service Qualification

**Issue:** [#171](https://github.com/ZP151/quantmesh/issues/171), unfinished real
database acceptance in the operator-approved A foundation.

**Goal:** Execute the existing five PostgreSQL tests against a genuine owned
disposable database and make the default service gate pass without skipping,
mocking SQL, reading existing credentials or waiting for Docker Desktop.

**Architecture:** Reuse the measured Linux CPython3.12/81-wheel service profile.
Use a current stable official PostgreSQL18.6 source release, verify its published
SHA256 and preserve copyright/license in an isolated native Linux build prefix.
Missing build tools may be qualified/extracted into that prefix from official
sources; no apt/system installation or daemon configuration. An owned non-root
process hosts only its new cluster on loopback, with fresh fixture credentials.
This verifies DB transactions/protocol, not production DB TLS/backup/HA or OCI.

Intake: WSL UID1000, GCC/make present; postgres/initdb/pg_ctl and Bison/Flex/
pkg-config absent. Existing source/Worker/Windows/vendor resources are unrelated
and must remain untouched. Docker Engine stays pending for #172 container tests.

## Ownership and interfaces

A fresh bounded verifier session owns only new
`tools/qualify_owned_postgres.py`, `tests/test_owned_postgres_fixture.py` and
its new `docs/runbooks/owned-postgres-fixture.md`. Root owns shared gate,
service/store fixes, locks, REUSE_MATRIX, ADR and iteration/ACTIVE integration.
If actual PG exposes a production defect, return its exact isolated RED and
diagnosis to root; do not opportunistically refactor the already-reviewed store.

CLI: `python tools/qualify_owned_postgres.py --profile <owned-profile.json>
--output <fresh-owned-evidence-directory>`. Construction-time profile binds
exact official source/build/binary identities and an owned native prefix; no
arbitrary download/command/DSN, public bind or borrowed cluster is accepted.
Default preflight must not start a database. An explicit owned-fixture mode
starts only the qualified binary/new data directory and records ownership.

## Required acceptance

- [ ] Qualify source checksum, compiler/build tool versions/licenses and actual
  binary version/digests; preserve install receipt and license. No package/core
  dependency change. Build limitations (for example local-fixture TLS/collation
  options) are explicit and never certify a production deployment profile.
- [ ] TDD ownership/admission: reject public bind, borrowed paths/cluster, raw
  external DSNs, credential argv/output, wrong binary/source identity and
  cleanup target mismatch. Use actual helper behavior, no source-text tests.
- [ ] Create a unique owned cluster/user/password without displaying/saving the
  DSN in evidence or prompts. Private temporary credential input is0600; no
  password CLI arguments or account/environment discovery. Verify actual
  cluster identity/data path and server PID before running SQL. A port race
  must fail, never redirect testing into another database.
- [ ] Start the native service's default gate with explicit owned-disposable
  acknowledgment and an in-process SecretStr DSN. All30 service tests run,
  including five real PostgreSQL cases, zero skips/errors/failures, exit0.
  Archive SQL-driver/source/runtime/cluster identity and authoritative gate
  logs/JUnit. Same published schema/nine-method digests and license gate apply.
- [ ] Prove real concurrency/idempotency, shared slots, fencing, reopen,
  cancellation and effect-reservation behavior covered by the actual tests.
  Distinguish their simulated lease-clock checks from a real≤90s Worker crash
  recovery witness, which remains #172/private deployment acceptance.
- [ ] Stop only the verified owned server/cluster. Preserve evidence and safe
  source/install artifacts; no global processes/prune/temp cleanup. No system
  service or persistent public listener remains.
- [ ] Run targeted checks/Ruff/diff and at most two independent Spec/Standards
  rounds for the new qualifier; do not repeat the original #171 architecture
  review. Commit/push bounded files and hand off exact source/evidence to root.

## Stop and forbidden actions

Stop at actual qualifying receipt or a concrete dependency/test defect needing
root/operator action. No paid resource/model call, production/AWS/source/helper/
GUI/tunnel action, credential/XML/log read, trade context, OS user/global config,
daemon activation, core/shared lock edit, merge/deploy/force push, or arbitrary
user code. Do not manufacture success through SQLite mocks, skip changes,
weakened constraints, edited qualification booleans or stored target timings.
Use native Linux storage and archive raw bytes/import paths before process exit;
mounted-drive expiry and volatile /tmp evidence are already known failure modes.

Sources: [official release files](https://www.postgresql.org/ftp/source/v18.6/),
[source build](https://www.postgresql.org/docs/18/install-make.html),
[requirements](https://www.postgresql.org/docs/18/install-requirements.html),
[PostgreSQL license](https://www.postgresql.org/about/licence/).
