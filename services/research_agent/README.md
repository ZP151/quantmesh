# Private research service — issue #171

Task 2 of the approved iteration0038 [plan](../../docs/superpowers/plans/2026-10-12-research-workers-workstation.md), based on exact
`0a7ae862f5a7e29bccf3b307c2507f424c81e092`. Advisory output cannot place orders.
This checkpoint is **offline scripted acceptance only**. Real PostgreSQL and
Linux runtime acceptance are pending; no server was provisioned or deployed.

## Scope and integration

The authenticated API admits a frozen registered-baseline request and exposes
durable status, cancellation and verified artifacts. Authentication token and
operator identity are mandatory construction arguments; no body-supplied
identity, endpoint, artifact path, order or credential fields are admitted.
All routes, including `/health`, require `Authorization: Bearer <server token>`.
`GET /v1/options` returns registered choices from the store's authoritative
Worker lake and only explicitly configured dataset IDs. No configured/qualified
fixture means `unavailable/no_qualified_inputs`; it never falls back to a
workstation-local lake. New submissions outside that configured list reject.
Keep the accepted dataset ID configured while its jobs need same-key replay:
accepted requests still replay if their input files disappear, but removing an
ID from the construction-time list rejects submissions/replays for that ID.
Previously accepted jobs remain readable/cancellable by their job ID. This
version does not add an idempotency-key lookup or a second admission ledger.
POST `/v1/jobs` additionally requires `Idempotency-Key`. Rejected bodies return
fixed error codes without echoing validation inputs. A missing store returns503.

```python
# Values are injected by the operator's server secret/configuration mechanism.
# This module never searches for existing DSNs, keys or account credentials.
store = PostgresJobStore(dsn_secret, lake_root=approved_exports,
                         artifact_root=owned_artifacts)
app = create_app(store, operator_id=configured_identity, token=auth_secret,
                 configured_dataset_ids=approved_fixture_ids)
```

`PostgresJobStore` reuses the reviewed `SQLiteJobStore` state machine with a
PostgreSQL DB-API connection facade. PostgreSQL is the sole remote authority;
this adapter does not open a SQLite file. Schema-scoped transaction advisory
locking serializes admission, two **shared backtest/analysis** slots, owner/
attempt/expiry fences and effect reservations across processes. Transactions
contain no model/network calls. Version1 tables and their creation are atomic;
unknown versions fail closed. No destructive down migration is exposed.
Only v1 permission-checked fixture exports are admitted at this stage. Real
history needs the subsequent qualified adapter; fixtures are never real-data
backtest evidence. Report publication checks actual owned bytes, envelope
schema, request/implementation digests and exactly one report. Numerical
validation remains the deterministic Worker's responsibility.

`AdvisoryRunner.run_next(owner, operator_id, gateway)` claims the independent
analysis outbox and finishes only its current lease. `run_analysis` separately
supports crash/replay tests before final JobStore publication. LangGraph OSS
routes effect → validation/artifact → checkpoint. The authoritative DB ledger
is the durable checkpoint, rather than an in-memory LangGraph saver.

One effect identity per immutable published report prevents configuration
changes from recalling completed or ambiguous effects. The reservation commits
before external work. The response archives original provider/model/prompt/
price-table version and estimate before checkpoint advancement; replay preserves
those values even after configuration changes. An unresolved reservation or
ambiguous timeout is terminal `unavailable/unknown_effect`, with unknown usage
and no fabricated output hash. There is no automatic operator retry endpoint
in this slice. Price must be explicitly known, finite and nonnegative; call
count and USD reservations cannot exceed the request budget. Dollar limits are
estimate admission controls, not provider invoice guarantees.

Model input is the verified published report only. Credential/endpoint/order
fields and recognized secret text reject; schema-valid outputs must cite the
exact published report and produce digest/size-verified job-owned analysis
bytes. Scripted outputs include `scripted_fixture=true` and provider=`scripted`.
Unavailable before a call has nullable provider/model/prompt/output metadata.
Advisory failure or cancellation preserves deterministic backtest success.

The configured gateway runs in an owned process with a bounded wall deadline.
Private server configuration crosses a local pipe, never an artifact/log.
Its environment is restricted and its home/cwd is a service-owned empty home.
Windows uses a parent-owned kill-on-close Job before child resume and a nested
Job for memory/CPU limits. Linux uses a process group, parent-death signal,
address-space/CPU-time limits and one-core affinity. Linux fractional CPU
budgets are rejected before reservation until a quota profile is qualified.
Linux limits, parent-death behavior and the complete Linux dependency closure
still require an actual Linux witness; Windows results do not certify them.
The bootstrap reuses QuantMesh-owned `tools/framework_bakeoff/process.py`
containment primitives and requires the complete source checkout at runtime.

## Independent environment and OSS decision

Core locks, dependencies and CI are unchanged. The service's own77-package
CPython3.13 Windows lock includes the existing core contract import closure.
Install it in a fresh service venv using hash enforcement:

```powershell
python -m venv services/research_agent/.venv
services/research_agent/.venv/Scripts/python -m pip install --require-hashes -r services/research_agent/requirements.lock
services/research_agent/.venv/Scripts/python -m pip install --no-deps --no-build-isolation -e . -e services/research_agent
services/research_agent/.venv/Scripts/python tools/research_service_gate.py --offline
```

Linux qualification candidate (iteration0038):
`requirements.linux-cp312.lock` binds81 selected external wheels for CPython3.12
x86_64. Shared Windows versions are unchanged; Linux adds SecretStorage,
jeepney, cryptography, cffi, pycparser and uvloop, and omits colorama and
pywin32-ctypes. The gate selects a fixed lock using measured implementation,
OS, Python minor and architecture; an unsupported runtime exits1 before checks.
Use hash-enforced installation in a fresh owned Linux venv and the same two
`--no-deps --no-build-isolation` editable project installs. This is a candidate,
not Linux production certification: the WSL mounted-drive trial installed all
81 wheels and passed8 runtime checks, but its service suite expired at the
owned300-second driver deadline. Preserve that failed/incomplete receipt.
A native Linux filesystem checkout is the next qualification target; no test
assertion, package constraint or real-PG requirement is relaxed. WSL results
cannot certify the OCI image, aggregate process caps or actual PostgreSQL/server.

Pydantic2.13.5 reproduces the frozen schema/protocol hashes. LangGraph1.2.12 and
its OSS closure are MIT; no LangSmith hosted service, CLI/platform/server or
telemetry client is initialized. Official qualification sources:
[upstream package](https://github.com/langchain-ai/langgraph/blob/main/libs/langgraph/pyproject.toml),
[LangGraph release](https://pypi.org/project/langgraph/1.2.12/), and
[pg8000](https://pypi.org/project/pg8000/1.31.5/).
pg8000 replaces the initially inspected LGPL psycopg candidate under the
repository permissive-license policy. No upstream source was copied.
Existing package copyright/license files remain in their wheels.

Service-owned exact exceptions cover scramp1.4.17's MIT-0 license bytes and
orjson3.13.0's `MPL-2.0 AND (Apache-2.0 OR MIT)` expression, selecting the
policy-allowed MPL-2.0+Apache-2.0 branch. The gate inventories every locked
installed package and refuses extras/version drift/unknown licenses. The
independent constraint snapshot differs from root only by omitting websockets:
LangGraph SDK requires <17. The root audited lock remains untouched.

`lock_service.py` adds official PyPI release SHA256 values to pip-tools pins
without downloading every platform's large wheel. To regenerate, bootstrap
pip-tools in an isolated tooling venv, compile root/service pyprojects with
`--extra dev --constraint services/research_agent/audit-constraints.txt
--output-file services/research_agent/requirements.pins`, then run
`lock_service.py`. Build tooling is not part of the admitted runtime closure.
Linux resolution requires its own qualification before installation/deployment.
RD-Agent and Qlib were not introduced or evaluated.

## Real database acceptance prerequisite

Do not point tests at an existing application database. Supply a new owned
disposable PostgreSQL database and a test role able to create/drop only its
test schemas. Tests create random `qm_test_<uuid>` schemas and drop those exact
schemas on completion. DSN is an explicitly supplied `postgresql://` URI;
TLS verification is default. `?sslmode=disable` is only for a disposable local
fixture. The schema is validated before any SQL identifier interpolation.
Do not place the DSN value in chat, shell history or committed evidence.

Inject `QM_TEST_DISPOSABLE_POSTGRES_DSN` through an approved local secret
mechanism, and set `QM_TEST_DISPOSABLE_POSTGRES_ACK=owned-disposable`, then run:

```powershell
services/research_agent/.venv/Scripts/python tools/research_service_gate.py
```

The default gate returns **nonzero** without real PostgreSQL evidence. `--offline`
may return0 while recording `postgres=pending`; it is never full acceptance.
PostgreSQL tests cover competing same-key submission/claims, shared slots,
expired-owner fencing, reopen/recovery, cancellation, manifest/artifact bytes,
concurrent reservations and migration transaction rollback/unknown version.
There was no running Docker Linux engine or discovered PostgreSQL service at
intake. No Docker/WSL daemon, global dependency, existing DSN or user state was
changed. Current store tests are skipped, not mocked PostgreSQL passes.

## Coordinator handoff

Root owns shared iteration/ADR/locks/CI/client/deploy changes and the one final
combined core release gate. This branch owns only this subtree and
`tools/research_service_gate.py`. The worker #170 must publish the frozen report
envelope under the configured shared owned artifact root. No Market/OpenD/
helper/tunnel/trading configuration was changed. No PR, merge or deployment.
Actual operator provider/model/egress/pricing approval and server-secret setup
are required before any gated real-model run. `ApprovedRemoteGateway` accepts
only explicit HTTPS origins from its construction allowlist and remote consent;
requests cannot change it. No paid model call occurred in this checkpoint.

See `evidence/checkpoint.json` for role outputs, RED/GREEN commands, current
verification, review dispositions and residual acceptance. Coordinator should
mirror that evidence into the shared iteration before integration.
