# Explicit private Research Service bootstrap

Issue [#171](https://github.com/ZP151/quantmesh/issues/171), narrow refinement of
the approved recoverable foundation. One operator action starts the existing
authenticated API and durable PostgreSQL adapter. The bootstrap starts no
Worker, model, source gateway or trading process. Queued/cancelled fixture jobs
prove persistence; they do not constitute a completed report.

## Admission and private configuration

Use a clean committed native persistent Linux checkout, non-root CPython 3.12
x86_64, and an independent venv installed with the unchanged 81-wheel
`services/research_agent/requirements.linux-cp312.lock` using `--require-hashes`.
Retain its existing license qualification. Start from the checkout root with
only explicit root/core/service source paths on `PYTHONPATH`, using `python -B`.
An editable Windows/mounted checkout, wrong HEAD, changed tracked runtime bytes,
untracked executable shadows (including ignored bytecode), dependency/import
mismatch or unqualified filesystem fails before PostgreSQL creation or binding.
Git checks also measure executable/configuration blobs despite skip-worktree.
This is measured local source admission, not a signed or hostile-host certificate.

Create separate existing owned lake, artifact and credential directories,
mode 0700, with absolute paths and no linked/writable ancestor. A root-owned
sticky `/var/tmp` is allowed. These roots cannot overlap. Bootstrap never creates
or discovers fixture inputs. Empty configured IDs leave submission unavailable.
Configured IDs use the existing dataset-name grammar; a missing or unqualified
configured fixture leaves options unavailable under the existing API contract.
This preserves retrieval of durable jobs if input files later disappear.

Write an explicit UTF-8 JSON config, regular single-link mode 0600 in an owned
0700 directory, maximum 64 KiB. The complete interface is:

```json
{
  "schema_version": 1,
  "operator_id": "operator",
  "expected_build": "<coordinator-approved full lowercase 40-character Git SHA>",
  "lake_root": "/var/tmp/quantmesh-bootstrap-OWNED/lake",
  "artifact_root": "/var/tmp/quantmesh-bootstrap-OWNED/artifacts",
  "configured_dataset_ids": [],
  "credential_directory": "/var/tmp/quantmesh-bootstrap-OWNED/credentials",
  "host": "127.0.0.1",
  "port": 8110
}
```

The SHA placeholder must be replaced by the reviewed committed candidate and
must equal measured HEAD/import bytes. Unknown or duplicated JSON keys, extra
model/order/request configuration, duplicate dataset IDs and alternate bind
fail closed. No CLI secret flags, environment credential fallback or `.env`
discovery are provided.

Only named `api_token` (16–4096 ASCII token characters) and `postgres_dsn`
(maximum 8192 ASCII bytes) are read from that credential directory. Supply them
through private files, without a trailing newline, never through argv or logs.
Each file must be owned mode 0600, regular and single-link; links, FIFO/device,
oversize, wrong permissions and replacement during reads are rejected through
descriptor-relative no-follow access and before/after metadata checks.
Secrets remain `SecretStr` and the runtime has a fixed redacted representation.
Errors expose fixed categories; configuration paths/content are never printed.

DSNs are explicit PostgreSQL URIs with username/password, database and optional
port. TLS defaults to verify-full. The only accepted query is one `sslmode` of
`verify-full` or `disable`; `disable` requires literal `127.0.0.1` or `::1` for
the new owned local fixture. Hostname aliases, duplicate/blank/unknown options,
fragments and ambiguous DSNs are refused. This local fixture does not qualify
production TLS, certificate management, HA or backups.

## Preflight, then explicit serving

From the clean checkout, with the explicit source path described above:

```sh
"$OWNED_ROOT/venv/bin/python" -B -m qm_research_agent --config "$OWNED_CONFIG"
"$OWNED_ROOT/venv/bin/python" -B -m qm_research_agent --config "$OWNED_CONFIG" --serve
```

Default preflight validates source/runtime/private configuration and emits only
redacted measured build/lock/runtime/capability metadata. It performs no SQL,
listener, Worker/model operation or fixture creation. Invalid admission exits
nonzero. `--serve` rechecks admission before constructing PostgresJobStore,
then starts fixed `127.0.0.1:8110`, one uvicorn worker, no reload, proxy-header
trust or access logs. Use a private supervising process for lifecycle ownership;
the bootstrap has no daemon install or endpoint override.

All routes require bearer authentication. Authenticated `/health` exercises a
real database transaction and reports measured `actual_build`, advisory-only,
Worker `pending_containment` and model `unavailable`. Unauthenticated health
returns 401; unavailable SQL returns scrubbed 503. `/v1/options` uses only
explicit configured fixture IDs. Existing submit/idempotent replay/get/cancel
contracts are preserved across an API restart with the same owned database.

## Native acceptance evidence

Run all independent service tests with a unique owned `--basetemp` and a fresh
genuine PostgreSQL cluster. The five existing PostgreSQL tests require the
explicit test-owned DSN/ack subprocess environment; those opt-in test settings
are never runtime credential authority. Read actual JUnit/counts and retain
zero-skip SQL evidence; do not assume the historical frozen 30-test count.
The historical `42fbfa5` qualifier stays unchanged and cannot admit this new tree.

New evidence lives in ignored `output/171-service-bootstrap`, including TDD,
native import/lock/source receipts, binary/COPYRIGHT rehash, raw HTTP/SQL receipt,
service tests, review and handoff. Reuse the previous PG18.6 four binaries only
read-only after full hash checks, copying to a new native prefix and preserving
COPYRIGHT. Create a new cluster and new private disposable credentials. Never
borrow an old cluster/DSN or modify its checkout, environment or profile.

The bounded witness must record auth/health/options/submit/replay/get/cancel,
API-process restart durability and DB-outage 503 without printing token/DSN.
Before stop, verify owned PID, Linux start ticks, executable hash/path, argv,
data path and nonce identity. An unrelated known sibling must survive. Preserve
failed attempts as failures and rerun native proof after admitted code changes.

Remaining gates: qualified aggregate Worker containment/Engine/image, actual
Linux report execution and recovery, approved real provider/model/price/egress,
private production deployment, TLS, encrypted off-host restore, capacity/p95,
HA and operator release acceptance. This preparation authorizes none of them.


## Explicit advisory runner (candidate software, not activated)

The HTTP API bootstrap above continues to start no model runner. A separately
managed process may use `python -B -m qm_research_agent.advisory_runtime
--config /home/ubuntu/.config/quantmesh/research/advisory.json`. Without `--run`
this performs the existing source/runtime preflight only; it starts no child,
SQL connection or model-key read. `--once` is valid only together with `--run`.
The same native clean-checkout, locked-runtime and private-file requirements
apply. Service configuration may contain the existing explicit portfolio policy
and category; operating monthly allowance cannot exceed50USD and development
lifetime allowance cannot exceed200USD. Job budget/ledger admission still applies.

The advisory JSON has exactly eight fields. All paths must be absolute, every
report digest unique lowercase SHA256, schema_version exact integer1, and
remote_consent exactlytrue. The values below describe the candidate interface;
no configuration has been installed by this document:

```json
{
  "schema_version": 1,
  "service_config": "/home/ubuntu/.config/quantmesh/research/service.json",
  "unit": "quantmesh-research-advisory.service",
  "model": "gpt-6.1-sol",
  "price_version": "openai-gpt-6.1-sol-standard-2026-10-13",
  "remote_consent": true,
  "key_file": "/home/ubuntu/.config/quantmesh/research/openai_api_key",
  "allowed_report_digests": ["173f770ee5d2b25ea6042b3a46fe240a92068b6911498abc47a737db143c5beb"]
}
```

The example digest identifies the already accepted synthetic fixed-fixture
report only. A later regenerated report has a different digest and does not
inherit this allowance. Additional data egress requires explicit approval.
The existing privately configured model key must never be printed, hashed or
copied into unit arguments, environment, logs or container mounts.

Only explicit `--run` admits source/runtime, runs a scripted child through the
actual cgroup/write-guard boundary, re-admits current bytes, binds PostgreSQL and
budget authority, then privately reads the key and constructs the fixed OpenAI
Responses runner. Digest refusal precedes reservation/effect lookup. The poll
loop is sequential; `--run --once` attempts at most one analysis/replay/idle
cycle. SIGTERM cooperatively prevents later startup stages when observed and
stops polling; systemd KillMode=control-group owns whole-tree termination.
Fatal containment refusal exits the manager, preserving uncertain reservations.

Offline config/ordering/cancellation tests and prior isolated Task2a native
proof are separate evidence. The new full bootstrap/canary, permanent unit,
real PostgreSQL setup and paid provider flow remain unqualified until their
actual release checks. New source is Class C: current-source CI and applicable
human/operator acceptance precede permanent installation and real-key use.
PR175 approval does not approve later source. No trading authority is added.
