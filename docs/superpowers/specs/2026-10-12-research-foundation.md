# Research foundation: operator review draft

Status: APPROVED Option A by operator2026-10-12. B is unselected. Separate
sessions are authorized in bounded batches; notify ahead of authentication,
payment and AI key configuration. No paid resource or call created yet.
Date: 2026-10-12, Asia/Singapore.

## Product decision

Build a recoverable, extensible research loop before evaluating new strategy
families. One user action is: choose a registered baseline and a pinned dataset,
submit a research job, and inspect its durable status and cost-aware report.
Optional Agent analysis attaches to the report without controlling execution.
Reuse the existing research engine, report registry, model gateway and risk
boundaries. Do not rebuild the trading engine.

The initial result is a private research workstation, not public SaaS or live
trading. Formal 168-hour soak is NOT REQUIRED, on-demand only. Historical soak
failures remain failures. Actual Windows login/outage, 24-hour capacity and
90-second shutdown drills remain later operational acceptance.

## Verified baseline and open work

| Item | Actual state on planning resume | Disposition |
| --- | --- | --- |
| Equity minutes, PR #163 | Deployed `69515b79d2bc67303bfef9dee660dbca9bef41e3`; Oct 8 regular-session revisions/appends/reload/provider OHLCV passed | Preserve; do not repeat implementation or deploy |
| Windows startup, PR #164 | Reviewed scripts installed; singleton and shortcut accepted; actual next login/outage unproved | Preserve active helper/source/tunnel |
| Release evidence, PR #165 | Merged; `origin/main` is `745a231715336844b26622ac1aa37350f891a011` | Planning baseline, not deployed application version |
| Probe containment, PR #166 | Candidate `da6e8c778c2e6c78ea863f39591ed9c9be8b2378`; CI `38248602251` SUCCESS13:15:58UTC; PR still OPEN; native 33 tests passed; installed helper not replaced | Finish exact-head gates; replacement needs a connection-preserving operator window |
| SSH authentication | Operator completed Oct 12 authentication; actual private readiness passed | Resolved; do not request old authentication again |
| #132 validation tiers | Open, ready-for-agent | First foundation batch; full final certification stays mandatory |
| #160 workflow Eval Harness | Open, 24 offline sourced cases requested | Baseline fixture/catalog early; integration evaluation after contract freeze |
| #156 readiness | Stock user loop accepted; probe closeout and later operator gates remain | Close only the proven scope; retain deferred gates |
| #135 private staging / PR #159 | Bounded migration accepted; firewall and operational evidence integration remain separate | No incidental merge or disruptive drill |
| #124 / #127 soak and connection witness | Retired schedules disabled; formal 168h not required | On demand, no session or spending now |
| Prediction venues and qualified history | Real end-to-end acceptance incomplete | Later dataset/venue slices; not absorbed into Agent infrastructure |

An isolated transient API timeout was followed by a successful request; it is
recorded, not promoted into a diagnosed backend defect. Current runtime uses
paper mode with live execution disabled. Existing baselines and AI boundaries
exist; persistent remote research orchestration does not yet exist.

## Architecture and deployment choices

QuantMesh owns validated requests, evidence presentation, dataset permission,
paper/risk authority and the user interface. A separate private Research Service
owns job storage and worker dispatch. Its Agent worker uses the existing typed
gateway behind an adapter. Workers read immutable input exports and publish
immutable artifacts; they never share a writable live DuckDB file across hosts.

Job domain contracts belong to `quantmesh.research`. A local SQLite JobStore
supports the local-first single-host mode. The remote Research Service uses
PostgreSQL, admitted only in its separately locked dependency environment.
There is one authoritative store per configured mode, never two independently
writable copies of a job. The workstation facade does not accept a job when
the authoritative store is unavailable: it returns a typed 503 and keeps market
and existing report views available.

Option A: one new 8 GB research host runs the service, workers and PostgreSQL;
off-host encrypted backups/artifacts provide recovery. It isolates research
failures from the workstation and is recoverable, but is not host-redundant HA.

Option B: two research hosts in separate availability zones use an encrypted
managed PostgreSQL HA plan and off-host artifacts. The workstation adapter has
two explicit private service endpoints and bounded failover. This provides
research-service/worker redundancy. The existing workstation entry host and
Windows OpenD are still single points; no whole-product uptime SLA is claimed.
Both options keep private access; public bundle IPv4 pricing does not imply
opening application, database or OpenD ports to the public internet.

## Server sources and global session semantics

Real market connectivity must run server-side, independent of the personal PC.
Existing AWS Hyperliquid and Moomoo SDK registrations do not establish a
server-owned OpenD gateway; issue#169 owns the missing migration and actual proof.
Use the existing pinned CalendarService across monitoring, API/UI summaries and
acceptance helpers. Weekend, holidays, early close and DST use exchange calendars,
not wall-clock age or Monday-Friday heuristics. Closed latest-session data is
expected, never an integration failure solely for no new bars. Missing coverage
is distinct from expected closed inactivity; crypto retains 24/7 freshness.
Open-session latency accounts for declared provider delay and a versioned opening
grace. Unknown calendar/session/permission means unknown, not fabricated fresh.
Keep raw age/provenance and deterministic order fences; closed data is not an
executable current quote. Oct12 intake calendar proves13:30–20:00UTC open, but
stale app values remain a diagnosis candidate pending delay/lifecycle evidence.

## Frozen v1 contracts

- `StrategySpec`: `strategy_id`, `version`, `family`, `parameters_schema`,
  `supported_markets`, `supported_intervals`, `dataset_requirements`,
  `cost_policy_id`, `implementation_digest`. Initial allowlist: existing
  momentum, mean-reversion and risk-parity baselines only.
- `DatasetRef`: `dataset_id`, `revision`, `manifest_digest`, `permission_class`,
  `export_digest`. Manifest validation precedes remote export and execution.
- `RunBudget`: `timeout_seconds=900`, `memory_mib=2048`, `cpu_limit=1.0`,
  `max_model_calls=12`, `max_estimated_model_usd=1.00` by default.
- `ResearchJobRequest`: `schema_version=1`, `strategy_id`, `strategy_version`,
  `dataset: DatasetRef`, `interval`, `universe: list[UniverseMember]`,
  `parameters`, existing `CostModel` and
  `WalkForwardSpec`, `budget: RunBudget`, `analysis_requested: bool`.
- `JobRecord`: `job_id`, request/config digest, idempotency key, state,
  `attempt`, `lease_owner`, `lease_expires_at`, `cancel_requested`, timestamps,
  error code, artifact references and measured/unknown usage. Include
  `analysis_state`: `not_requested`, `pending`, `running`, `succeeded`,
  `failed`, `unavailable` or `cancelled`. Backtest states are exactly
  `queued`, `running`, `succeeded`, `failed`, `cancelled`.
- `AnalysisLease`: job ID, separate owner/attempt/expiry, bound report digest;
  advisory work never reclaims the backtest lease or overwrites its success.
- `ArtifactRef`: `artifact_id`, `kind`, `schema_version`, `sha256`, byte size,
  immutable relative object key. Paths, secrets and arbitrary URLs are not refs.
- `AnalysisRecord`: job/report digest, model/provider identity, prompt digest,
  output digest, citations, verdict, usage and estimated price version. It has
  no order, broker token or execution authority.

Idempotency is `(operator_id, idempotency_key)`: same digest returns the same
job, different digest returns 409. Leases last 60 seconds and heartbeat every
15 seconds. Conditional writes fence old attempts. Cancellation requests revoke
publication authority before terminating only a test/job-owned worker tree.
Duplicate computation may occur after failure; duplicate published results may
not. Agent side effects need idempotency too, not just a graph checkpoint.
Publishing a backtest result atomically creates an analysis-pending outbox row
if analysis was requested. Separate analysis leases and conditional finish
provide recovery; analysis failure leaves a valid backtest succeeded and an
explicit advisory status. An ambiguous model-response timeout is recorded as
unknown effect: no automatic duplicate paid call, require operator retry.

## Reliability, data and evaluation acceptance

1. Accepted jobs survive service process restart. Recover an expired worker job
   within 90 seconds in the declared two-job test load, excluding its computation
   time. Host/DB outages have separately measured restore time.
2. Store unavailable means explicit submission failure, not a success response
   followed by lost work. Existing charts/reports remain usable when Agent is down.
3. The same pinned data, strategy/config, cost policy and code produce the same
   canonical numerical backtest artifact. Wall-clock receipt timestamps belong
   to an envelope outside that digest; existing StrategyReport.created_at is
   not falsely claimed to be deterministic. Frozen Agent output replays from storage;
   fresh LLM calls are not claimed to be byte-reproducible.
4. No report publication until artifact digest and input lineage validate;
   crash between object upload and state update may leave an orphan, not a
   falsely successful job. Cleanup considers only this service's owned objects.
5. Backtests model fees, spread, slippage and chronology using existing engine
   contracts. Missing history, future data or insufficient permissions reject
   the job; a few live minutes do not become years of qualified history.
6. Proposed submission p95 is at most 2 seconds under two concurrent baseline
   jobs on the approved profile. Test and publish the actual latency; don't
   represent this target as current evidence.
7. Initial worker concurrency is 2 globally. Each job has CPU/memory/time caps.
   Model spending is reserved before calls, unknown price blocks paid execution,
   and exhausted budget produces an explicit partial/unavailable analysis.
   The $1 limit is admission/estimate control, not a guaranteed provider invoice.
8. #160's 24 cases cover happy path, boundaries, recovery, security, complexity
   and regressions with its seven-way failure taxonomy. Scripted fixtures are
   offline workflow evidence, not measured real-model investment skill.
9. Restore an encrypted backup into an isolated instance and verify job/report
   digests. Stop only new test-owned workers for failure tests; do not kill the
   existing OpenD, GUI, helper or tunnel, reboot Windows, or enable live trading.
10. Option B additionally proves loss of either test research host, private
    endpoint failover, DB recovery, fenced publication and no missing accepted
    jobs. Provider upstream failures remain explicitly unavailable.

## Agent harness decision

Use the OSS LangGraph library as the first orchestration candidate, with durable
checkpointing and QuantMesh-owned typed boundaries. Do not assume its commercial
Agent Server is a free OSS deployment. Freeze a qualified version, audit its full
dependency/license closure, and document remote-model and data-egress consent.

RD-Agent/Qlib are isolated optional research-worker candidates, evaluated on five
fixed tasks with a maximum $25 API budget and no broker access. They are not a
mandatory production dependency or a reason to rebuild accepted baselines.
TradingAgents may inform analyst workflows later. Do not import whole upstream
stacks into the core environment. Current ADR-0010 and ADR-0015 remain binding.

Sources: [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence),
[RD-Agent](https://github.com/microsoft/RD-Agent),
[Qlib](https://github.com/microsoft/qlib).
Framework admission is conditional on a pinned bake-off, not established by these links.

## Strategy and custom-strategy expansion after foundation

The screenshot is a proposed price-threshold position-management rule:
scaling in / averaging down, and scaling out / staged profit-taking. It is not
a verified reproduction of a named trader's proprietary algorithm. Define the
reference price, base capital, tranche percentages, cash reserve, repeat/reset
rule and corporate-action behavior before evaluating it. Selling percentages
may refer to original or remaining position; no ambiguous default is silently used.

Trend research and this position overlay are the first proposed experiment.
Statistical cross-sectional alpha is an implementable research direction, not
a reproduction of Renaissance/Simons proprietary systems. Macro and value
families require point-in-time releases/fundamentals. Liquidity/flow trend
neutral portfolios require PIT universes, delisted instruments, realistic
shorting/funding/borrow costs, gross/net/beta constraints and turnover.
Dollar neutrality alone is not beta neutrality.

Custom strategy support has three tiers: (1) configure registered templates,
(2) declare factors/portfolio rules in a validated DSL, (3) run uploaded Python
in a separate sandbox later. V1 reserves strategy/version/parameters and input
capabilities. V1 does not execute uploads, generated code, imports or shell
commands. An ordinary container is not sufficient evidence of safe arbitrary
untrusted-code isolation.

## Scope exclusions and operator decisions

No Kubernetes, Redis, GPU, public multi-user SaaS, autonomous unlimited search,
new paid market-data subscriptions, broker promotion or live trading in the
foundation. Missing provider/API metadata does not block offline development;
paid calls wait for explicit provider/model/price and data-egress approval.

The operator reviews Option A versus B, incremental monthly cap, one-off
development API cap, and the foundation-before-strategy ordering. Secrets are
configured on the target server, never pasted in chat. A connection-preserving
Windows helper update and disruptive operational drills get their own concrete
operator window. This design is not a paid deployment approval by itself.
