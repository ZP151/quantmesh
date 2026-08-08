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
2. [ ] Global and per-venue kill switches disable the execution plane
      without model cooperation: an order submission is refused while
      the switch is engaged, per venue and globally, proven by
      enforcement tests over the paper kernel. — Phase C (issue #60).
3. [ ] Recovery drills demonstrate no duplicate or orphaned orders:
      journal replay with an idempotency key replays to the same
      state, and the reconciliation identity/tolerance discipline
      (ADR-0006) verifies it. — Phase B (issue #59).
4. [x] Metrics, structured logs, alert emission and signed audit
      exports are implemented and drilled; the export signature
      verifies and a tampered export fails verification. — Phase A
      (issue #58).
5. [ ] The threat model is recorded, the CI dependency/license
      scanning job is green (no incompatible licenses), and the
      release process is documented. — Phase D (issue #61).
6. [ ] The per-venue enablement approval workflow and secret-store
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

## Verification evidence

- `tests/test_ops.py`: 37 passed (2026-08-08).
- `ruff check src tests`: clean on the Phase A surface.
- Full-suite run recorded in ACTIVE.md after the M10-1 commit.
