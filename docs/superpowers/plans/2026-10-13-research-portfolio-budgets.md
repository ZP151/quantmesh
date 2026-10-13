# Research Service Portfolio Budget Closure

Approved scope: Option A portfolio phase 4 and Workers Task 2, issue #171 under
#167. This is the missing cross-job reservation boundary required by the
approved $50/month model operating allowance and $200 development API ceiling.
It does not authorize a paid call, provider selection, purchase, deployment,
new trading authority or changes to frozen v1 contracts. Root coordinates two
bounded sessions: service implementation, then independent owned PostgreSQL
qualification. The verifier can prepare its owned harness in parallel, but
cannot certify an implementation before its exact candidate is supplied.

Baseline: `216b378192bbc0a1742a28b7a1fc75a86ae2fda9`, draft PR #175.
Current exact-head release CI must reach a real terminal state before root
pushes another coherent integration checkpoint. Do not cancel it for this plan.

## Decisions and limits

Ruling: operating periods are UTC calendar months, rather than rolling windows,
because they are reproducible across processes and align with a monthly budget.
Development reservations are lifetime cumulative. This is a conservative
implementation choice within the approved allowances; changing the semantics
later requires a reviewed migration, never an implicit accounting reset.

Ruling: unresolved reservations from earlier operating periods continue to
consume the current allowance. Completed previous-period estimates do not.
Unknown provider outcomes and cancellation never release a reservation.
Clock rollback rejects new reservations, without recalling existing effects.
Archived response/checkpoint replay remains usable without a new reservation.

One authoritative portfolio policy per store/schema. Immutable policy binding
and additive versioned accounting tables prevent a second policy ID, changed
limit, restart, month string supplied by a job, or backup restore from resetting
the authority. Caps may be lower than approved limits, never higher than $50
operating / $200 development. Existing unattributed effects cause activation
to fail closed; do not fabricate timestamps, categories or billing history.

Amounts use finite nonnegative Decimal values and persisted canonical strings,
never floating-point sum or SQL textual-number comparison. The policy period
uses only the authoritative store clock. Per-job $1/12-call limits and lease
fencing still apply in the SAME transaction as portfolio admission and effect
insertion. PostgreSQL's existing schema advisory transaction lock and SQLite's
owned BEGIN IMMEDIATE remain the concurrency boundary. No provider call occurs
inside a transaction. Every new reservation requires explicit policy/category,
including zero estimates and scripted offline tests. There is no fixture
exemption that ApprovedRemoteGateway could inherit.

Ruling: a restored or cloned database cannot simultaneously operate as a second
spending authority. This slice verifies durable single-authority accounting,
not cross-database distributed billing. Backup promotion and production cutover
still require fencing the previous authority; operator release remains gated.

Policy is service-owned, not supplied by submission DTO or HTTP user. Model
execution remains unavailable in runtime defaults. Health, backup restoration,
and script-only tests must not claim real provider billing, model performance,
production TLS, or a full-project ceiling for external bake-offs that bypass
this service. Estimates differ from provider invoices. Infrastructure spending
is outside this ledger. External development API tools must use the same
approved reservation authority before future paid activation or remain blocked.

## Task 1: service accounting implementation

Exclusive writes: `services/research_agent/src/qm_research_agent/budgets.py`,
new service-owned accounting module if needed, `orchestrator.py`, `runtime.py`,
service tests, and service README. No core contracts, dependency locks, shared
CI, source gateway, old native qualifier or global ledger edits.

- [x] RED proves independent jobs can currently each reserve beyond a shared
  allowance; keep old per-job test as a separate boundary.
- [x] Add a frozen `PortfolioBudgetPolicy` in budgets (or re-export there):
  `policy_id`, `operating_monthly_usd: Decimal`, `development_total_usd: Decimal`.
  IDs are bounded nonsecret identifiers; reject invalid/nonfinite/negative
  values and caps above approved ceilings. `EffectLedger(store, *, policy=None,
  category=None)` binds explicit `operating` or `development` category. Existing
  reserve_call signature and read/response/checkpoint tuple remain unchanged.
- [x] Implement the additive authoritative policy/high-water clock/reservation
  ledger with explicit version validation and atomic admission described above.
  Missing/mismatched policy and unattributed history deny new paid/remote effects.
- [x] Add optional validated runtime configuration for the policy/category only;
  this does NOT start a model runner or allow external requests. Keep unknown
  config rejected, credentials private, health model unavailable.
- [x] Prove cross-job exact-boundary, last-slot race, separate categories,
  lifetime exhaustion, month transition, unresolved carry, backward time,
  duplicate/crash/reopen/rollback, malformed/mismatched policy and legacy history
  fail-closed cases. Remote missing-policy denial must demonstrate zero external
  invocations; scripted boundary labelled explicitly. No real paid call.
- [x] Run focused new tests plus the complete relevant service offline boundary,
  Ruff/format/diff. Preserve raw RED/GREEN and exact commit handoff. Stop before
  merge, PR creation or deployment. Root supplies bounded two-axis review.

## Task 2: independent real PostgreSQL / restore witness

Exclusive writes: NEW `tools/qualify_portfolio_budgets.py`, NEW
`tests/test_portfolio_budget_qualification.py`, NEW dedicated runbook. Prepare
against the frozen public accounting API above; root sends the reviewed exact
Task 1 commit before execution. Do not change old PG/backup qualifiers or their
baseline checks to make a newer tree look previously certified.

- [x] Design an owned-only default blocked preflight and bounded admission
  comparable to existing qualifiers. Reuse independently audited readonly PG18.6
  binaries and service environment, never existing clusters or global packages.
- [x] Create disposable private loopback PostgreSQL resources with attributable
  process identity/cleanup, bounded subprocess output/timeouts, and no ambient
  credential ingestion. Nonowned resources survive all success/failure cleanup.
- [x] Real independent processes, different jobs, shared schema: race for last
  allowance; count durable reservations with an independent SQL observer before
  scripted provider invocation. Exactly one winning invocation; denied call zero.
- [x] Verify exhausted operating/development policies persist through close,
  reopen and a real pg_dump/pg_restore to a separately owned database. Compare
  complete additive accounting tables and immutable effect rows; do not reset
  clock/policy to pass. Source and restored stores both reject another effect.
- [x] Prove version/mismatch/rollback and failure cleanup with meaningful tests;
  distinguish real DB/dump/restore from scripted provider and synthetic fixture
  numerical report. No encrypted off-host claim; the previous restic proof stays
  independently limited to its frozen baseline.
- [x] Save actual source/build/lock/binary hashes, stdout/stderr/exit streams,
  independent observer proof and known PID terminal cleanup. Stop at bounded
  review-ready commit and actual local evidence; all production flags false.

## Task 3: root integration and publication boundary

- [x] Independent Spec and Standards checks at most two rounds per slice; root
  independently verifies targeted evidence rather than repeating unchanged
  historical qualification/full local suites.
- [x] Preserve frozen schema/protocol/lock digests; archive raw bytes and hashes.
- [x] At the real CI terminal boundary, also narrow research_service upload to
  top-level gate JSON/log/JUnit receipts, avoiding recursive test fixture files.
- [ ] Integrate coherent reviewed candidate into draft #175; mirror local versus
  scripted versus production state in ACTIVE/iteration/plan and ignored handoff.
  New exact-head required CI follows actual code changes; never replay old runs.
- [ ] Remain ACTIVE for Linux numerical Worker/Engine, provider/key, protected
  source-host, production PG/TLS/off-host restore, p95 and human release gates.

Preflight review: Task 1 produces the accounting API consumed by Task 2; verifier
waits for its exact reviewed candidate before runtime. Task 1 and Task 2 writable
files are disjoint. Root alone owns shared docs/CI/integration. Additive accounting
does not alter nine store methods or v1 DTOs. Historical native qualifiers remain
untouched. No paid resource/model/server operation is part of this slice.

Local acceptance2026-10-13: Task1b107 accounting closesR1/R2; root maps it to
b5aba03/4a7fff9 and actualcurrentbf64883 Linuxservice137pass5PGskip (142total).
Task2exact084 closesfinalSpec/StandardsR2 afterrealinitdb descendantRED/GREEN;
37native/0skip20.45s,687/687rawhashes match, all281nativefiles retained among364
trackedrawstreams. Unknownfamily members remain preserved and unqualified;
normal ownedfamilies are kernel-terminal before rescue. Source bytes/frozen
contracts/locks retained. Historical journal/hash mismatch is preserved and
originalbytes recovered. This accepts only ownedlocalSQL/scripted accounting.
Publicationcheckbox remains pending until newheadCI is genuinelyterminal and
the draft/human/release gates are satisfied. FullA remains ACTIVE.
