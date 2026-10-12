# Owned PostgreSQL service fixture

Issue [#171](https://github.com/ZP151/quantmesh/issues/171), bounded verifier
refinement of the approved A foundation. This fixture runs the independent
default service gate against a genuine private PostgreSQL process. It neither
installs a system service nor qualifies a production deployment.

## Qualification prerequisites

Use a fresh non-root Linux `/var/tmp/quantmesh-owned-pg-*` directory, mode 0700,
containing its own `checkout`, CPython 3.12 `venv`, `prefix` and `build-proof`.
The checkout must be at frozen integration commit
`42fbfa510b8153c7a2b3b6fd3e5d4851eda850e8`; service/core/gate code stays unchanged.
Install the existing 81-wheel `requirements.linux-cp312.lock` with
`pip install --require-hashes`. Never inspect existing database credentials.
Admission rejects linked checkout/venv paths and any tracked change or untracked
addition except the qualifier, its tests and this runbook. It checks actual
driver/contract/store import paths and bytes in the owned environment/checkout.

Download only the [official PostgreSQL 18.6 release](https://www.postgresql.org/ftp/source/v18.6/)
and its published SHA256 file. Archive SHA256:
`555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f`.
Preserve its `COPYRIGHT` as `build-proof/POSTGRESQL-COPYRIGHT`, SHA256
`3d6af92ff8a4c2cdf69afb1cf44edea727922f5cd0cf8b5f72b11cdecac8fdfd`.
Keep upstream source/install artifacts outside the repository.

Missing build tools can be extracted into this private prefix from the official
Ubuntu archive. Verify `Release.gpg` with the installed Ubuntu archive keyring,
the compressed package index against signed Release SHA256, then every `.deb`
against the package index. The measured Ubuntu Noble tools were Bison
`2:3.8.2+dfsg-1build2`, Flex `2.6.4-8.2build1`, and m4 `1.4.19-4build1`.
Retain package bytes, hashes, dependency fields and copyright files. These are
external build tools: Bison/m4 GPL notices do not enter the service runtime.
No apt/global installation is required or authorized by this runbook.

Follow [upstream build instructions](https://www.postgresql.org/docs/18/install-make.html):

```sh
export PATH="$OWNED_ROOT/prefix/usr/bin:/usr/bin:/bin"
export BISON_PKGDATADIR="$OWNED_ROOT/prefix/usr/share/bison"
export M4="$OWNED_ROOT/prefix/usr/bin/m4"
./configure --prefix="$OWNED_ROOT/prefix" --without-readline --without-zlib --without-icu
make -j4
make install
```

SSL is disabled by default in this build. `--without-ssl` is not supported by
the measured configure script. Local C/UTF8 collation, no ICU, no readline and
no zlib are fixture limitations; this build does not certify TLS, HA, backup or
production collation/compression. Preserve compiler/make/Perl versions,
copyright, configure/build/install logs and installed binary digests.

Write `build-proof/build.json` with exactly `root`, `source_url`,
`source_sha256`, `binaries`, `license_sha256`, `configure`, `packages`.
`binaries` maps `postgres`, `initdb`, `pg_ctl`, `pg_controldata` to measured
SHA256 values; `configure` is the exact argv above. This is a construction-time
receipt of the owned build, not an arbitrary command, download or external DSN.

## Preflight and explicit fixture run

From the own native checkout, using its own locked interpreter:

```sh
"$OWNED_ROOT/venv/bin/python" tools/qualify_owned_postgres.py \
  --profile "$OWNED_ROOT/build-proof/build.json" --output "$OWNED_ROOT/preflight"
"$OWNED_ROOT/venv/bin/python" tools/qualify_owned_postgres.py \
  --profile "$OWNED_ROOT/build-proof/build.json" --output "$OWNED_ROOT/actual-fixture" \
  --owned-fixture
```

Every output path must be fresh and contained in the owned root. Preflight
checks source/license/binary identities and version without starting a cluster.
The explicit run creates a new data directory, synthetic role/password, and
literal `127.0.0.1` listener. A port collision fails without redirecting to a
borrowed database. The password enters initdb via a temporary 0600 input file
that is removed. No password is supplied on argv or recorded in receipts.

Before SQL, the helper checks `/proc` executable/hash/UID/argv, data directory,
postmaster PID and Linux process start ticks. Authenticated SQL then verifies
the data path, literal listener, port, synthetic role and system identifier
against `pg_controldata`. Only the owned gate subprocess receives the disposable
DSN and `QM_TEST_DISPOSABLE_POSTGRES_ACK=owned-disposable`; service tests wrap
the DSN in `SecretStr`. Model credentials are absent, tracing disabled.

Read `fixture.json`, `gate/service-gate.json`, JUnit and the original logs.
Acceptance requires the unchanged gate's 30 tests and all five real PostgreSQL
cases, with zero failures/errors/skips and exit 0. A receipt flag alone is not
acceptance. Cleanup verifies process/data/nonce identity again, fast-stops only
that postmaster, waits for exit and records `stopped`. There is no prune/global
cleanup. Retain the private source/install artifacts and archive redacted raw
proof into the managed Windows worktree before ending the WSL invocation.

The five cases prove idempotent concurrency, shared slots, stale lease fencing,
reopen, cancellation, actual manifest/artifact bytes, rollback/version rejection
and concurrent effect reservations. Their lease-clock injection does not prove
a real 90-second Worker crash/recovery witness; that remains #172/private
deployment acceptance. No OCI/model/server/financial-performance certification
is inferred from this local database gate.
