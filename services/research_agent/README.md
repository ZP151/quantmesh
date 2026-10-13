# Private research service — issue #171

Task 2 of the approved iteration0038 [plan](../../docs/superpowers/plans/2026-10-12-research-workers-workstation.md), based on exact
`0a7ae862f5a7e29bccf3b307c2507f424c81e092`. Advisory output cannot place orders.
The original scripted checkpoint is now accompanied by measured Linux
dependency/offline-service and genuine owned PostgreSQL acceptance. Final
local SQL gate:30 passed, zero skips/failures/errors, exit0 on frozen42fbfa5;
see [raw SQL proof](../../docs/evidence/research-foundation/owned-postgresql/README.md).
Production runtime/containment, private deployment, backup/restore and real
provider acceptance remain pending; no server was provisioned or deployed.

Subsequent explicit bootstrap is integrated from97f53d0 (new runtime/CLI/test/
runbook; existing health already root18ff2f1). On exact native97f53d0, genuine
HTTP/SQL37checks and independent fullservice/defaultgate85tests/0skip/exit0
pass. Actual auth/build/fixture replay/cancel/APIrestart/DB503/sibling and
owned cleanup are witnessed; no Worker/model runs. See
[bootstrap raw proof](../../docs/evidence/research-foundation/service-bootstrap/README.md)
and [startup runbook](../../docs/runbooks/research-service-bootstrap.md).
Use explicit reviewed configuration/0600named private files, measured source/
runtime/lock admission and `python -B -m qm_research_agent`; default preflight
has no SQL/listener/effects. Serving is fixed loopback8110/oneworker. This
local SQL/API proof is separate from production/Worker/model acceptance.

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

## Portfolio estimate authority — issue #171

New effects, including zero estimates and scripted fixtures, require an explicit
service-owned policy and category. This is additive accounting over the frozen
store/DTO contracts. Runtime defaults still have no model runner; health and
preflight continue to report model `unavailable`, paper mode and live disabled.

```python
from decimal import Decimal
from qm_research_agent.budgets import EffectLedger, PortfolioBudgetPolicy

policy = PortfolioBudgetPolicy("research-estimates-v1", Decimal("50"), Decimal("200"))
effects = EffectLedger(store, policy=policy, category="operating")
```

The frozen policy accepts a bounded ASCII identifier and finite nonnegative
Decimal caps, at most $50 operating per UTC calendar month and $200 development
over the authority's lifetime. Category is explicitly `operating` or
`development`; jobs and HTTP submissions cannot supply it. The optional private
runtime configuration uses paired `portfolio_policy` and `portfolio_category`:

```json
{
  "portfolio_policy": {
    "policy_id": "research-estimates-v1",
    "operating_monthly_usd": "50",
    "development_total_usd": "200"
  },
  "portfolio_category": "operating"
}
```

Amounts in JSON are decimal strings. Numeric coercion, unpaired fields, unknown
fields and expanded caps reject. Serving with this optional configuration binds
the policy in the authoritative store; it does not enable model execution or
external requests. Configuring a future model runner requires independent
provider/key/containment approval.

The additive version-1 tables are `qm_portfolio_schema`, singleton
`qm_portfolio_policy` (immutable identity/caps and a UTC high-water clock), and
`qm_portfolio_reservations` (effect identity, category, UTC month, canonical
Decimal price and reservation timestamp). `model_effects` retains its original
columns and read/response/checkpoint tuple. Admission validates the binding and
version, checks lease fencing and both per-job and portfolio limits, then inserts
the effect and attribution in the **same** store transaction. SQLite witnesses
use BEGIN IMMEDIATE; PostgreSQL uses the existing schema advisory transaction
lock. Provider invocation happens only after commit. Exact rational arithmetic
over validated Decimals avoids ambient Decimal-context rounding and float sums;
prices and caps persist as canonical Decimal strings.

Completed operating estimates count only in their reservation month. Unresolved
effects from earlier months still count against the current month; cancellation,
timeouts and crashes never release them. Development estimates remain cumulative
after completion, month transitions and reopening. Backward store time denies new
reservations. The authoritative store clock supplies all timestamps and periods.
Changed policy IDs/caps, unknown accounting versions and existing unattributed
effects fail closed; no historical category/timestamp is invented. Missing policy
denies new effects but archived response/checkpoint replay remains usable.

There is one authority per deployment/schema. A restored backup preserves the
policy, clock and complete reservation history; it does not renew the allowance.
Cloned or restored stores cannot be simultaneously promoted as independent
authorities for one allowance. Production cutover remains operator-gated; an
older snapshot cannot serve as a fresh spending authority. External development
API tools must reserve through this same approved authority before future paid
activation or remain blocked. This service ledger does not certify a full-project
ceiling for tools or bake-offs that bypass it. Estimates differ from provider
invoices, and infrastructure spending is outside this ledger.

The new tests are explicitly local SQLite/scripted accounting witnesses. Real
PostgreSQL concurrency and dump/restore require the separate owned qualifier;
these tests do not certify real billing, model performance, production TLS,
off-host restore or deployment. No paid call is authorized by this change.

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

CI also runs an independent `research_service` job on Ubuntu24.04/CPython3.12.
Its fresh runner-temp venv installs only the81-package Linux lock with hashes
and wheels enforced, then runs the existing service gate with `--offline`.
The required `CI / python` aggregator requires this job to succeed. Source paths
come from the gate/pytest configuration; no core environment, editable installation,
unpinned build dependency, model secret or PostgreSQL daemon is supplied.
Retained receipts are explicitly `OFFLINE_SCRIPTED_ONLY`: dependency/license/
schema/protocol/API/scripted compatibility, with PostgreSQL pending. This does
not certify real SQL, aggregate model-process limits, paid model calls or a
deployed service. Existing genuine owned PostgreSQL/native acceptance and future
production/model/operator gates remain separate.

Core locks and dependencies are unchanged; existing core gate commands are
preserved. The service's own77-package
CPython3.13 Windows lock includes the existing core contract import closure.
Install it in a fresh service venv using hash enforcement:

```powershell
python -m venv services/research_agent/.venv
services/research_agent/.venv/Scripts/python -m pip install --require-hashes -r services/research_agent/requirements.lock
services/research_agent/.venv/Scripts/python -m pip install --no-deps --no-build-isolation -e . -e services/research_agent
services/research_agent/.venv/Scripts/python tools/research_service_gate.py --offline
```

Linux dependency/offline-service qualification (iteration0038):
`requirements.linux-cp312.lock` binds81 selected external wheels for CPython3.12
x86_64. Shared Windows versions are unchanged; Linux adds SecretStorage,
jeepney, cryptography, cffi, pycparser and uvloop, and omits colorama and
pywin32-ctypes. The gate selects a fixed lock using measured implementation,
OS, Python minor and architecture; an unsupported runtime exits1 before checks.
Use hash-enforced installation in a fresh owned Linux venv and the same two
`--no-deps --no-build-isolation` editable project installs. Actual clean
9d5b3fa native-filesystem WSL acceptance passes81 licenses/no unknowns,
8 runtime tests and25 scripted service tests/5 real-PG skips, offline exit0.
That historical default gate exits1 solely for the missing actual disposable
PostgreSQL proof. The subsequent owned PG18.6 native fixture at42fbfa5 executes
all30 service tests, including all5 genuine PG cases, zero skips/failures/errors,
exit0. Final qualifier33native tests and two-axis reviews pass; the owned cluster
stops safely. Original failed/default receipts stay archived, not overwritten.
This C/UTF8 local fixture without TLS/ICU/readline/zlib does not certify the
production database, HA/backup, Linux Worker or model containment.
Fresh Windows gate remains25pass/5skip/exit0. Retain the mounted-drive capture,
Git-pointer and300s-expiry attempts; none is a successful qualification.
Raw durable evidence and actual-import paths are in
`docs/evidence/research-foundation/linux-service-cp312`. This is not Linux
production certification: OCI/image/aggregate model caps, Linux Worker recovery,
real PostgreSQL/model calls and server acceptance remain unfinished.

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

## OpenAI Responses provider — offline Task1 only

`openai_responses.py` adds a typed, service-owned transport and an
`ApprovedRemoteGateway` subclass using the existing httpx dependency. It does
not activate the runtime/bootstrap. An explicit `SecretStr`, allowed origin and
remote consent are required. The sole URL is
`https://api.openai.com/v1/responses`; no key, proxy, account or endpoint is
discovered from environment or request data. Unknown model/price versions
reject at construction. Configuration stays pickle-safe, with a fresh closed
AsyncClient per effect and no automatic retry.

The selected alias is `gpt-6.1-sol`; no dated snapshot or account access is
inferred. The immutable price source version is
`openai-gpt-6.1-sol-standard-2026-10-13`, standard rates per million input/
cached input/cache write/output tokens $2/$0.10/$2.50/$10, for input at most
272000 tokens. Other tiers, regional pricing and long contexts are unqualified.
Source: [official model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol).

`make_openai_advisory` constructs the existing runner with provider=`openai`
and a conservative `Decimal('1.00')` reservation. The existing per-job
$1/12-call caps and configured $50 UTC-month operating/$200 lifetime development
policy remain authoritative. This uses a default job's full estimate allowance;
it is an admission estimate, not a provider bill or spending guarantee. Token
metadata never refunds a reservation. Missing portfolio authority remains denied.

The adapter maps the existing text messages and optional strict JSON schema
to Responses `input` and `text.format`, with low reasoning, output at most1024,
`service_tier=default` and explicit `store=false/background=false/stream=false`.
Legacy temperature is validated but omitted, because reasoning effort is fixed.
There are no tools, conversations, previous response, images/files or fallback
trading text. Request/response UTF-8 payloads are capped at65536 bytes; an
aggregate asyncio30-second exchange deadline supplements HTTP timeouts. TLS
verification is on, redirects/proxy discovery are off and clients/responses close
on errors or cancellation. Only one completed assistant/output_text is accepted,
with non-published reasoning metadata. Refusal/tool/incomplete/error/unknown
model or tier rejects. Usage and cached/cache-write/reasoning counts require
exact nonnegative integers and consistent totals; unknown details fail closed.

The pinned httpx0.28.1 transport installs a guarded network-backend adapter for
Linux DNS. A fresh owned stdlib subprocess resolves only the fixed public
hostname; it receives no key/report and is killed/reaped on cancellation. The
existing backend connects to a numeric public address while httpcore retains
the original HTTPS origin/TLS SNI. This avoids uncancellable resolver-executor
shutdown extending the synchronous call's deadline. An unexpected dependency
shape or unsupported platform fails closed rather than using that fallback.
This is a narrow resolver/process witness, not aggregate model containment.

The resolver interpreter uses `-B -I`: it cannot load Python modules from the
caller's working directory or user site. A real owned-child module-shadow
negative failed before `-I` and passes afterward, without DNS/TCP/API access.
The final affected suite is131passed/48.60s; no aggregate Linux, real TLS/SNI,
account/model or provider-billing acceptance is inferred from it.

Offline tests use in-memory mocked HTTP and real gateway/graph/local-store/
ledger/artifact validation. The subprocess invocation boundary is replaced for
that mock to stay in-process; these tests do **not** witness native aggregate
containment, actual API availability, TLS handshake, paid usage or model quality.
Completed archived responses replay original metadata without another effect;
ambiguous timeouts keep their reservations and backtest success. Exhausted
portfolio/job budgets make zero HTTP calls. See the new
[Task1 plan/evidence](../../docs/superpowers/plans/2026-10-13-openai-advisory-provider.md).

Real activation waits for qualified aggregate Linux execution, reviewed private
server deployment, model/account/price verification and explicit report-egress
and server-secret approval. No real request or key was used for this checkpoint.
`store=false` is not Zero Data Retention; standard abuse monitoring can retain
data up to30 days. [Official data controls](https://developers.openai.com/api/docs/guides/your-data)
govern that separate acceptance. Only specifically approved report/context may
leave the server after those gates.
