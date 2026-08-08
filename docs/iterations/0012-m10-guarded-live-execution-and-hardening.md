# Iteration 0012 — M10: Guarded live execution and hardening

- Status: active
- Started: 2026-08-08
- Completed:
- Owner: Claude
- GitHub issue: issues #58-#62 (Phases A-E, dependency-ordered: #59/#60/#61 block on #58, #62 blocks on #58-#61)
- Pull request: (opened after acceptance criteria complete; base = `feat/m9-local-frontend-workstation`, stacked — merges after the M9 PR #57, which stacks behind the M8 PR #50, which stacks behind the M7 PR #44, which stacks behind the M6 PR #38, which awaits the M5 PR, which awaits the M5 operator drill)
- Roadmap milestone: M10 (`LATER`)

## Outcome

Permit limited *paper* live simulation with explicit user control and
production-grade observability: per-venue enablement and an approval
workflow, idempotency and recovery drills, secret store integration
and signed audit exports, metrics/structured logs/alerts/runbooks, a
security threat model, dependency/license scanning and a release
process. Real-money enablement is a recorded external human gate, not
an M10 deliverable: every safe deliverable is implemented, verified
and wired to the paper surface, and the exact gate that unlocks real
live operation is recorded in this iteration and in ACTIVE.md.

## Scope and boundaries

In scope:

- Metrics and structured logs over paper operation (the existing
  registries and journals stay the system of record; metrics are
  derived records on the ADR-0006 JSONL discipline), defined
  reliability/drawdown limits, alert emission through the M7
  `AlertLedger`, incident runbooks, and signed audit exports (a local
  HMAC-SHA256 signature over the exported journal digest, key held by
  the local secret store — no external signing service).
- Idempotency keys on the paper-kernel submission path and recovery
  drills over journal replay proving no duplicate or orphaned orders,
  reusing the M4/ADR-0006 reconciliation identity and tolerance.
- Kill-switch enforcement: the M9 paper kill switch wired into the
  execution plane, extended to per-venue flags — live execution
  disableable globally and per venue without model cooperation.
- Security threat model for the local-first workstation, a CI
  dependency/license scanning job, and a documented release process.
- Per-venue live-enablement state machine (disabled/pending/enabled)
  with an approval workflow and local secret-store integration
  (keyring, OS-backed), built and tested against the paper surface.
  The state machine, approvals and secret-store plumbing are all
  fixture-tested; no real credential ever enters the codebase.

Out of scope (recorded, not deferred silently):

- **Real-money trading, wallet signing, live broker orders,
  credentials, paid infrastructure, and AI order authority**: all
  require explicit human approval (the long-running goal's external
  gate, verbatim). M10 implements every safe deliverable and records
  the exact gate; it does not flip it. Live enablement beyond the
  paper surface is refused structurally (the enablement state machine
  gates on approval records that only a human operator can create
  after the gate text is recorded).
- **New execution authority**: the M2 paper kernel remains the only
  order surface; M10 adds enforcement and enablement states around
  it, never a new order path.
- **Remote/cloud infrastructure**: metrics, alerts and logs are local
  files; the scanning job runs in the existing GitHub Actions CI (no
  new paid service).

## Acceptance criteria

1. [x] Reliability and drawdown limits are defined, measured over
      paper operation and alerted on breach (alerts via the M7
      `AlertLedger`), and incident runbooks exist and are tested for
      content. — Phases A/B (issues #58/#59).
2. [x] Global and per-venue kill switches disable the execution plane
      without model cooperation: an order submission is refused while
      the switch is engaged, per venue and globally, proven by
      enforcement tests over the paper kernel. — Phase C (issue #60).
3. [x] Recovery drills demonstrate no duplicate or orphaned orders:
      journal replay with an idempotency key replays to the same
      state, and the reconciliation identity/tolerance discipline
      (ADR-0006) verifies it. — Phase B (issue #59).
4. [x] Metrics, structured logs, alert emission and signed audit
      exports are implemented and drilled; the export signature
      verifies and a tampered export fails verification. — Phase A
      (issue #58).
5. [x] The threat model is recorded, the CI dependency/license
      scanning job is green (no incompatible licenses), and the
      release process is documented. — Phase D (issue #61).
6. [x] The per-venue enablement approval workflow and secret-store
      integration are implemented and fixture-tested against the
      paper surface; the real live-enablement gate is recorded in
      this iteration, ADR-0012 and ACTIVE.md, and every safe
      deliverable is complete and verified. — Phase E (issue #62).

## Plan and role assignments

Solo fast lane (Claude, one branch per milestone): one tested and
reviewed commit per issue, pushed every checkpoint, one final
milestone PR. Every phase is fixture-driven; there is no human gate
in M10 (the live-enablement gate is recorded and refused, not
approached).

## Reuse survey (2026-08-08)

- **keyring (MIT, Phase E, new dev-dependency choice)**: OS-backed
  credential store (`win32` DPAPI backend on Windows) — the local
  secret-store integration without storing anything in code or
  files. `keyring` is only exercised against a fixture backend in
  tests; the real backend is never populated with a real credential
  (the gate).
- **hmac + hashlib (stdlib, Phase A)**: signed audit exports with a
  local HMAC-SHA256 key held by the secret store — zero new
  dependencies for signing; `cryptography` noted and rejected (the
  export signature is not an identity assertion, and keeping the
  dependency surface minimal is part of the threat model).
- **pip-audit (Apache-2.0, Phase D, CI job)**: the canonical
  dependency vulnerability scanner; a license-review step documents
  the license inventory with the incompatible-license check. Runs
  only in the existing GitHub Actions CI.
- **M2 paper kernel + M7 AlertLedger + ADR-0006 discipline**: the
  existing enforcement, alert and persistence contracts — M10 wires
  them, it does not fork them.
- stdlib `logging` with a structured formatter (Phase A): rejected
  `structlog` (MIT) to keep runtime deps unchanged; the structured
  record shape is a plain dict on one line.

## Phase A — metrics, structured logs, alerts, incident runbooks,
signed audit exports (issue #58)

- `quantmesh.ops.metrics`: a `MetricsStore` on the ADR-0006 JSONL
  discipline (append-only, atomic temp+replace reads, fail-closed
  with line attribution) recording derived metrics over paper
  operation — order flow, fill rates, equity/drawdown snapshots,
  reconciliation deltas. Metric definitions live in one contract
  (`Metric` dataclass with name/kind/unit) pinned by test.
- Reliability/drawdown limits: defined constants in the ops surface
  (e.g. max drawdown fraction, max consecutive reconciliation
  mismatches), evaluated over recorded metrics; a breach emits an
  `AlertLedger` alert (the M7 surface, source `ops:`) — the M9 risk
  screen renders it with no further work.
- Structured logs: a `StructuredFormatter` for stdlib logging emitting
  one JSON object per line (ts, level, logger, message, fields);
  the workstation and the ops CLI route through it.
- Incident runbooks: `docs/runbooks/*.md` — local disk exhaustion,
  journal corruption, reconciliation mismatch, kill-switch engage;
  each names symptoms, checks, and recovery steps; presence and
  section structure pinned by a doc test.
- Signed audit exports: `quantmesh ops export-audit` serializes the
  journals (order journal, mapping ledger, decision log, metrics)
  into one signed bundle: content digest + HMAC-SHA256 tag keyed
  from the secret store. Verification refuses a tampered export.
- Tests: metric recording/attribution, limit-breach alert emission
  (source `ops:`), formatter round-trip, runbook doc test, export →
  verify → tamper → refuse drill.

## Phase B — idempotency, reconciliation and disaster recovery
(issue #59)

- Idempotency keys: the paper-kernel submission path (`PaperAccount.
  submit`) accepts a client-supplied idempotency key; a replay with
  the same key is refused with a typed result naming the original
  order, never duplicated. Keys are recorded in the order journal
  and participate in its identity.
- Recovery drills: `quantmesh ops recover --journal <path>` replays
  the journal to a fresh account and reconciles it against the
  surviving account with the ADR-0006 identity/tolerance
  discipline — no duplicate orders, no orphaned fills, mismatches
  attributed with tolerance. The drill is scripted evidence, run in
  tests over fixture journals (crash-mid-stream, partial append,
  truncated tail).
- Exit criterion 3 evidence: each drill asserts exact order/fill
  counts and reconciliation deltas of zero (within the recorded
  tolerance).

## Phase C — global and per-venue kill-switch enforcement (issue #60)

- The M2 paper kernel already refuses submissions while the global
  `kill_switch` flag is engaged (ADR-0011 consequence); Phase C
  extends the flag to per-venue enforcement: `kill_switch` becomes a
  map (venue → engaged) with a global bit that overrides, both on
  the same account object the M9 control flips — the JSON surface,
  the page context and the enforcement gate can never disagree.
- Enforcement tests: submissions refused globally and per venue
  without any model involvement (the refusal lives in the kernel's
  risk gate, not in any AI surface — "without model cooperation"
  proven by the gate being in the accounting path, not the M8 AI
  path); disengage restores submission; per-venue refusal leaves
  other venues open.
- The M9 kill-switch control page gains the per-venue state with no
  new write surface (same confirm-gated POST contract); the M10
  enforcement boundary line in its UI copy is removed (it is now
  true).

## Phase D — security threat model, dependency/license scanning,
release process (issue #61)

- `docs/threat-model.md`: the local-first threat model — loopback
  discipline (ADR-0010), no credentials in code, JSONL fail-closed
  reads, autoescaped UI, the two write surfaces, kill-switch
  enforceability, and the real-money gate. Each threat named with
  the control that addresses it and the test that pins it.
- CI job: `pip-audit` over the locked environment plus a license
  review step that fails on any incompatible license (the
  inventory documented in `docs/licenses.md`). Green on the M10
  branch.
- Release process: `docs/release-process.md` — branch/PR chain
  conventions, full-suite gate, drill evidence requirements,
  versioning, and the human gate checklist for any future live
  operation.

## Phase E — per-venue live enablement approval workflow + secret
store integration (issue #62)

- `quantmesh.ops.enablement`: a per-venue state machine
  (disabled/pending/enabled) persisted on the ADR-0006 JSONL
  discipline; transitions require an approval record (who, when,
  which gate text was presented) — the approval records are the
  only path to `enabled`, and in M10 they exist only in fixtures
  and drills.
- Secret store integration: `quantmesh.ops.secrets` wrapping keyring
  with a typed API (get/put/delete, fixture backend in tests,
  real backend never populated — a typed error refuses a
  non-fixture store outside a drill flag).
- The M9 workstation gains a read-only enablement screen (state per
  venue, "pending" transitions never permitted from the UI — the
  approval workflow is CLI/operator-owned, like promotion approval
  in M9 Phase C).
- **The external gate (recorded, verbatim in ACTIVE.md and
  ADR-0012)**: real-money trading, wallet signing, live broker
  orders, credentials, paid infrastructure, and AI order authority
  require explicit human approval. Phase E completes every safe
  deliverable — the state machine, approvals, secret-store plumbing,
  tests and drills — records the exact gate, and proceeds to any
  other safe unblocked roadmap work.

## Delivery protocol

- One tested and reviewed commit per issue, pushed every checkpoint.
- Full suite must stay green: every phase runs `pytest -q` (the suite
  is 1646 passed / 3 skipped at the M9 close), `ruff check src
  tests` and `git diff --check` clean, submodules clean.
- Issues close only when the final M10 PR merges.
- ADR-0012 records the durable decisions as they land (metrics/log
  shape, idempotency discipline, kill-switch enforcement, scanning
  gate, the live-enablement gate).

## Durable decisions to record when reached

- Decision 1 (Phase A): metrics and structured logs are local JSONL
  on the ADR-0006 discipline; alerts flow through the M7
  `AlertLedger`; audit exports are HMAC-signed locally.
- Decision 2 (Phase B): idempotency keys on the paper-kernel
  submission path; recovery is journal replay verified by the
  ADR-0006 reconciliation discipline.
- Decision 3 (Phase C): the kill switch is a global-bit + per-venue
  map on the account object; enforcement lives in the accounting
  risk gate, never in an AI surface.
- Decision 4 (Phase D): scanning is CI-only (pip-audit + license
  review); the threat model and release process are recorded docs.
- Decision 5 (Phase E): enablement is a recorded approval state
  machine; the secret store is keyring; the real live-enablement
  gate is a recorded external human gate.

## Risks and gates

- **Real-money / credentials / paid infrastructure (external human
  gate, THE gate of M10)**: no M10 deliverable touches them. The
  enablement state machine, secret-store wrapper and approval
  records are fixture-tested; the gate text is recorded in
  ACTIVE.md and ADR-0012; nothing in M10 can produce a live order,
  sign a wallet or spend money. If an M10 phase appears to need any
  of these, it is refused structurally and the gate is re-recorded.
- **Kill-switch bypass**: enforcement lives in the paper kernel's
  accounting path (executed on every submission) and is pinned by
  tests that prove no model cooperation is involved; a submission
  cannot route around it by construction.
- **Replay duplication**: idempotency keys participate in journal
  identity; the recovery drills replay crash-mid-stream fixtures and
  assert exact counts.
- **Secret-store drift**: only the fixture backend is exercised in
  tests; a non-fixture store refuses outside a drill flag, so no
  real credential can be created by accident.
- **Scanning flakiness**: pip-audit pins against the locked
  environment; a new advisory fails the job loudly, and the license
  review is a deterministic inventory check, not a network-dependent
  one.

## Work log

**Issue #58 (Phase A, operational hardening) complete — 2026-08-08.**

- Implemented `quantmesh.ops`: `metrics.py` (Metric id over
  name+measured_at, MetricsStore on the ADR-0006 discipline),
  `limits.py` (ReliabilityLimits; running-peak drawdown evaluation;
  breach → `reliability_limit`/`ops:limits` alert through the M7
  AlertLedger), `logging_fmt.py` (StructuredFormatter), `secrets.py`
  (KeyStore protocol + KeyFileStore), `export.py`
  (quantmesh-audit-bundle v1: canonicalized-content digest,
  HMAC-SHA256 tag, BundleVerificationError), `cli.py`
  (`quantmesh-ops` record-metric/export-audit/verify-export);
  `settings.metrics_dir`; `drift.ALERT_KIND` extended with
  `reliability_limit`.
- Debugging note: the running-worst drawdown tracker started at 0.0
  and used `min()`, so a real breach read as 0.0 (3 failures); fixed
  to track the max of per-step (peak − value)/peak. The MetricsStore
  read path missed the root-not-dir refusal (a file root read as
  empty); fixed with an explicit root check. The CLI tamper drill
  originally exported empty default surfaces (tamper was a no-op);
  the drill now populates real surfaces first.
- Tests: `tests/test_ops.py` — 37 passed (metric model, store
  discipline incl. attribution + duplicate refusal, drawdown/mismatch
  limits, breach alert emission + identical re-detection refused,
  formatter shape/fields/repr fallback, key store incl. traversal +
  dir refusal, export round-trip + 4 tamper drills, CLI round-trip +
  exit codes, runbook doc test). Ruff E/F/I/UP clean.
- ADR-0012 decision 1 recorded (metrics/logs on ADR-0006, alerts via
  the M7 ledger, local HMAC-signed exports).

**Issue #59 (Phase B, idempotency + recovery drills) complete —
2026-08-08.**

- `OrderRequest`/`Order` carry an `idempotency_key` (URL-safe shape,
  1-64 chars, `IDEMPOTENCY_KEY_PATTERN`); a keyed submission derives
  its order id as `paper-<key>` (when no `client_order_id` is given),
  and `PaperAccount.submit` detects the replay by key BEFORE the
  sequence is consumed or the risk gate runs, returning the original
  order in a typed `SubmissionResult.replay_of` — never duplicated,
  never re-gated, never consuming state (a rejected order replays as
  rejected; a filled order replays without re-applying fills).
- The order journal's read identity now includes idempotency keys:
  two records sharing a key are refused with line attribution,
  exactly like duplicate order ids — a duplicate in the file fails
  closed instead of replaying a duplicate.
- Implemented `quantmesh.ops.recover`: `read_journal_lines` (fail-
  closed, ALL refusals collected with line attribution — partial
  append/truncated tail named, nothing partially replayed; missing
  root/file reads empty), `replay_orders` (pure event fold into a
  fresh account — no risk gate, no matcher, no kill switch re-run;
  mid-lifecycle orders stay unacknowledged), `verify_event_history`
  (event history re-applied through `OrderStateMachine`, comparing
  status/filled_quantity/event count), `reconcile_recovered`
  (ADR-0006 discipline: identity match, qty/price/status tolerances,
  missing-internal, orphaned account orders → divergent, position
  surface with position_qty_bps), `recover` (report `clean` only with
  zero refusals, zero missing and zero ERROR findings); CLI
  `quantmesh ops recover --journal --cash [--against] [--*-bps]`
  exits 0 only when clean, 1 with findings named otherwise.
- Tests: `tests/test_recovery.py` — 24 passed: 8 idempotency (typed
  replay, rejected replayed without re-gate, fills never re-applied,
  key collision with an unkeyed `paper-2` order refused, invalid
  shape refused, journal duplicate-key refusal), 12 drills (replay
  == live account exactly; crash-mid-stream mid-lifecycle preserved;
  partial append/truncated tail/duplicate-key refusals all collected;
  event-history inconsistency named; unbookable SELL fill → "replay
  refused"; empty journal clean; missing snapshot order; orphaned
  account order; position divergence + tolerance), 4 CLI (round-trip
  exit 0; corrupt exit 1; divergent snapshot exit 1; qty tolerance
  0 vs 100 bps). Ruff E/F/I/UP clean (I001 auto-fixed in recover.py).
- ADR-0012 decision 2 recorded (idempotency keys on the submission
  path; recovery is journal replay verified by the ADR-0006
  reconciliation discipline).

**Issue #60 (Phase C, global + per-venue kill-switch enforcement)
complete — 2026-08-08.**

- `PaperAccount` gains `kill_switch: bool` and
  `kill_switches: dict[Venue, bool]` — the same account object the M9
  control flips is the single source of truth for the REST surface,
  the page context and the gate. The global bit overrides every
  venue; a venue absent from the map reads as disarmed (a disarm pops
  the entry). Enforcement is in the accounting risk gate
  (`_risk_reasons`), which every submission crosses before sequence
  consumption: engaged → typed rejection `"kill switch enabled"` /
  `"kill switch enabled for venue <v>"`, recorded as the rejected
  order (the journal replays the refusal; cash/positions untouched).
  The gate sits in the accounting path by construction, so "without
  model cooperation" is architectural — no model surface can set or
  clear the switch.
- `EventStore`: `account_meta.kill_switches` JSON column; a
  pre-Phase-C store is migrated additively on open (PRAGMA
  table_info + `ALTER TABLE ... ADD COLUMN ... DEFAULT '{}'` — never
  destructive); reads fail closed (`StoreCorruptionError` for
  non-JSON, non-dict, unknown-venue or non-bool payloads) so a
  corrupted meta row cannot silently disarm anything.
- API: `GET /kill-switch` reports `{"kill_switch", "kill_switches"}`
  with venue keys sorted. Workstation: the kill-switch page renders
  one confirm-gated form per venue (hidden `venue` field, radios
  "Block/Allow {venue} paper orders", venue-scoped confirm checkbox),
  options from the account's engaged venues ∪ bound markets (never a
  free-text injection surface); a POST naming an unknown venue is
  refused with a typed error page and leaves state untouched; global
  and per-venue engage/disarm all replace the account in state +
  page context (303). Promotions copy updated: the flag now records
  the posture at promotion time (the enforcement line "until M10
  enforces it" removed — it is now true).
- Tests: `TestKillSwitchEnforcement` (6: per-venue refuses only its
  venue, global overrides a disarmed venue, disarming restores,
  refusal records the rejection and nothing else, venue-not-in-map
  open, absent venue reads disarmed), store (map survives restart,
  legacy store migrates additively, 4 corrupt payloads fail closed),
  API (status observable with the map), workstation (per-venue rows,
  engage/disarm round trips, hostile-venue refusal with state
  untouched, account flags without markets), E2E keyboard-only drill
  extended with a per-venue engage→disarm round trip through the same
  confirm-gated POST (15 E2E passed). 17 new tests in Phase C; full
  suite 1725 passed / 3 skipped. Ruff E/F/I/UP clean.
- ADR-0012 decision 3 recorded (kill switch = global bit + per-venue
  map on the account object; enforcement in the accounting risk
  gate, never an AI surface).

**Issue #61 (Phase D, threat model + dependency/license scanning +
release process) complete — 2026-08-08.**

- `docs/threat-model.md`: 15 threats (T-01…T-15), each named with the
  control that addresses it and the test that pins it, plus the two
  accepted residuals (same-origin page bug, physical access). The
  register is a contract: `tests/test_security.py` verifies every
  citation resolves to a real test/file/ADR.
- The scanning gate found its first real finding: **vectorbt**
  (research extra) ships as Apache-2.0 **WITH the Commons Clause**
  (source-available, not OSI) — no code path imported it, so it was
  removed from the extra; ADR-0009's dependency-contract text
  updated. `tools/license_review.py` (stdlib-only, deterministic,
  no network) classifies every installed distribution from PEP
  639/345 metadata against the `docs/licenses.md` allowlist; the
  text classifier refuses the Commons Clause *before* the Apache
  appendix text can match, and the expression classifier refuses
  "WITH Commons-Clause" before the qualifier strip. 94 packages
  reviewed, all allowed.
- `requirements-audit.txt`: the frozen install closure of
  `.[dev,research]` (49 pins, generated via `pip install --dry-run
  --report`; no vectorbt, no quantmesh). CI `security` job:
  `pip-audit -r requirements-audit.txt --no-deps` (new advisory
  fails loudly) + `python tools/license_review.py` over the real
  install; CI Lint step now covers `tools`.
- `docs/release-process.md`: branch/PR conventions, the full-suite
  gate, drill-evidence requirements, the audit-lock regeneration
  procedure, versioning, and the human-gate checklist for any future
  live operation.
- CSRF hardening found while writing the threat model (T-14): the
  three write POSTs (`/watchlist/add`, `/watchlist/remove`,
  `/kill-switch`) refuse a present non-loopback Origin — browser
  CSRF always sends the attacker's Origin; absent Origin (CLI/drill)
  stays allowed. Pinned by `TestWriteSurfaceOriginGuard` (5 tests);
  the E2E keyboard drill still passes (same-origin loopback sends).
- Tests: `tests/test_security.py` — 14 passed (threat-model register
  + citation resolution, license classifier unit tests incl.
  Commons-Clause refusal and WITH-exception stripping, installed-
  env classification, licenses-doc ↔ script agreement, audit-lock
  parseability). Ruff E/F/I/UP clean incl. tools.
- ADR-0012 decision 4 recorded (CI-only scanning: pip-audit over the
  frozen closure + deterministic license review; the Origin guard;
  the vectorbt removal as the enforcement precedent).

**Issue #62 (Phase E, enablement approval workflow + secret store +
recorded live gate) complete — 2026-08-08.**

- `quantmesh.ops.enablement`: a per-venue state machine
  (disabled/pending/enabled) with fixed legal edges — request
  (disabled→pending), approval (pending→enabled), withdraw
  (pending→disabled), revoke (enabled→disabled) — persisted as
  append-only JSONL on the ADR-0006 discipline
  (`settings.enablement_dir`, default `~/.quantmesh/enablement`).
  State is *derived* from the ledger (the target state of the latest
  record per venue), so the ledger and the reported state can never
  disagree; an identical replay at the same instant is refused by
  record identity (sha256 over the canonical JSON of every field);
  records name who, when (timezone-aware, normalized to UTC) and —
  for approvals — which gate text was presented. **The only path to
  `enabled` is an approval record carrying `GATE_TEXT` verbatim**;
  a stale, watered-down or missing gate is refused by both the model
  validator and `ledger.approve` before anything is written.
  Debugging note: `_record` initially called `.astimezone(UTC)` on
  the raw argument, which silently interpreted a naive datetime as
  local time and bypassed the model's awareness refusal — an explicit
  `tzinfo` check now refuses naive timestamps at the ledger edge.
- `quantmesh.ops.secrets`: `KeyringStore` — typed get/put/delete over
  a `KeyringBackend` protocol (base64-encoded bytes, safe-name
  enforcement); `FixtureKeyringBackend` for tests; a lazy real
  backend that refuses construction outside an explicit drill flag
  (the OS keyring holds real credentials, and the recorded gate
  requires explicit human approval before any credential store is
  used), failing closed as `KeyringUnavailableError` when keyring
  cannot be imported.
- CLI: `quantmesh ops enable <venue> <kind> --actor <name>`
  [--at ISO] [--gate-text TEXT] [--root PATH] — prints the
  live-enablement gate to stderr on every approve and requires
  `--gate-text` to match verbatim (missing or wrong → exit 1, state
  untouched); illegal transitions exit 1 with the state the
  transition requires; unknown venue exits 2.
- Workstation: the M9 app gains a **read-only** `/enablement`
  screen (Page registry entry, nav reachable): per-venue states,
  the gate text rendered verbatim, a bound/unbound indicator — no
  form, no POST (a POST is refused 405), because transitions are
  CLI/operator-owned exactly like M9 promotion approval. E2E
  accessibility snapshots extended to the new screen.
- Dependency closure: keyring 25.7.0 (MIT) + 5 transitives added to
  the `dev` extra; the venv was upgraded to the fresh resolution;
  `requirements-audit.txt` regenerated to 55 pins; `docs/licenses.md`
  inventory regenerated — 100 packages reviewed, all allowed.
- `tests/test_security.py` `_token_resolves` tightened: an
  `ADR-00NN decision N` citation now resolves only against a real
  `### Decision N` header in exactly one matching `docs/adr/` file
  (this enforcement caught ADR-0012 decision 5 before it was
  recorded — the doc test is a living contract for Phase E too).
- ADR-0012 decision 5 recorded (enablement = recorded approval state
  machine; secrets = keyring behind a drill-gated store; the real
  live-enablement gate recorded verbatim; the workstation screen is
  read-only).

**CI advisory remediation — 2026-08-08.**

- GitHub Actions Security run `31258964613` found `pytest 8.4.2`
  affected by `PYSEC-2026-1845` (fixed in `9.0.3`). The dev extra now
  requires `pytest>=9.0.3,<10` and `pytest-asyncio>=1,<2`; the audit
  lock records `pytest 9.1.1` and `pytest-asyncio 1.4.0`.
- The Security workflow reviews the project environment before
  installing `pip-audit`, keeping the scanner's own CLI dependencies
  out of the application license inventory while still scanning the
  frozen project closure.
- The latest main CI run `31258964567` was green (1774 passed, 1
  skipped); local lock audit and the project-environment license review
  both pass with the updated constraints.

## Verification evidence

- `tests/test_ops.py`: 37 passed (2026-08-08).
- `tests/test_recovery.py`: 24 passed (2026-08-08) + 1 key-replay
  regression test (same key, regenerated client id — still a replay).
- `tests/test_accounting.py` `TestKillSwitchEnforcement`: 6 passed;
  `tests/test_store.py` kill-switch suite: 6 passed (map restart,
  legacy migration, 4 corrupt payloads); `tests/test_api.py`
  kill-switch status: 1 passed; `tests/test_workstation.py`
  `TestPhaseCPerVenueKillSwitch`: 5 passed (2026-08-08).
- `tests/test_workstation_e2e.py`: 15 passed (2026-08-08) — the
  keyboard-only drill covers the global engage/disarm round trip and
  a per-venue engage→disarm round trip through the confirm-gated POST;
  re-run green after the Phase D Origin guard (same-origin loopback
  sends pass).
- `tests/test_security.py`: 14 passed (2026-08-08) — threat-model
  register + citation resolution, license-classifier units
  (Commons-Clause refusal, WITH-exception stripping, permissive SPDX
  members, copyleft refusal), installed-environment classification,
  licenses-doc ↔ script agreement, audit-lock parseability.
- `tools/license_review.py`: 94 packages reviewed, all allowed
  (2026-08-08).
- `tests/test_enablement.py`: 37 passed (2026-08-08) — approval
  record model (gate text verbatim on approvals only, naive
  timestamps refused, forged ids refused), the full state machine
  (round-trip drill with who/when/gate-text assertions, 11 illegal
  transitions each leaving the ledger atomic, wrong-gate refusals,
  states derived from the ledger only, venue independence), ledger
  discipline (missing → empty, root-not-dir, corrupt-line and
  duplicate-id attribution, cross-instance persistence, replay
  refusal), keyring store (construction refusal outside a drill even
  with a fixture backend, fixture round-trip with arbitrary bytes,
  service separation, safe names, import-guard fails closed,
  drill-only real-backend construction — never read/write), and the
  CLI drill (full workflow exit 0, missing/wrong gate text exit 1
  with state untouched, illegal transition exit 1, unknown venue
  exit 2, gate text presented to the operator on stderr).
- `tests/test_workstation.py` `TestEnablementScreen`: 5 passed
  (2026-08-08) — unbound typed empty state, bound per-venue states,
  empty ledger, read-only (POST refused 405, no form in markup),
  nav reachable; the gate text renders verbatim on every state.
- `tests/test_workstation_e2e.py`: 16 passed (2026-08-08) — the
  accessibility-snapshot screen list extended to the enablement
  screen (13 screens).
- `tests/test_security.py`: 14 passed (2026-08-08) — the ADR
  decision-citation checker now resolves `ADR-00NN decision N`
  against a real `### Decision N` header in exactly one
  `docs/adr/` file (it caught ADR-0012 decision 5 before the
  decision was recorded).
- Full suite: `pytest -q` 1787 passed, 3 skipped (2026-08-08) —
  recorded in ACTIVE.md after the M10-5 commit.
- `ruff check src tests tools`, `git diff --check`, `git submodule
  status`: clean on the M10-5 surface.
