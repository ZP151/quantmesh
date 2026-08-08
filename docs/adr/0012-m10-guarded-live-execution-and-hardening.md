# ADR-0012 — M10: Guarded live execution and hardening

Status: accepted
Date: 2026-08-08
Milestone: M10 — Guarded live execution and hardening (iteration 0012)
Issues: #58-#62

## Context

M10 hardens the workstation for *paper* live simulation with explicit
operator control: metrics/structured logs/alerts/incident runbooks,
idempotency and recovery drills, global and per-venue kill-switch
enforcement, a threat model with CI dependency/license scanning and a
release process, and a per-venue live-enablement approval workflow
with local secret-store integration. The long-running goal binds this
milestone: **real-money trading, wallet signing, live broker orders,
credentials, paid infrastructure, and AI order authority require
explicit human approval** — M10 implements every safe deliverable,
verifies it against the paper surface, and records the exact gate
that unlocks real live operation (the enablement state machine in
Phase E refuses any transition not backed by a human approval record,
and the approval records only a human operator can create after the
gate text is recorded).

The M10 durability substrate already exists: the ADR-0006 JSONL
discipline (atomic temp+replace writes, fail-closed reads with line
attribution, duplicate-id refusal) used by the experiment, mapping and
decision journals, and the M7 `AlertLedger` (deterministic alert ids,
duplicate refusal) that the M9 risk screen already renders. M10 wires
these; it does not fork them.

### Decision 1 — Metrics, structured logs, limits, runbooks and signed
audit exports are local JSONL on the ADR-0006 discipline; alerts flow
through the M7 `AlertLedger`; audit exports are HMAC-SHA256-signed
locally (Phase A, issue #58)

`quantmesh.ops` (issue #58) defines the observability surface:

- **`ops.metrics`**: `Metric` (deterministic 16-hex id over
  `(name, measured_at)` — identical replay refused, later sample
  appends; snake_case name; finite value; aware-UTC timestamp
  normalized to UTC) and `MetricsStore` on the ADR-0006 discipline
  exactly: atomic temp+replace appends, fail-closed reads with line
  attribution (`metrics <path> line N is invalid`, shared-id refusal
  within the file), duplicate-id refusal before any write, root-not-dir
  refusal, and a missing store reading as an empty list — never an
  error. Records persist as `metrics.jsonl` under
  `settings.metrics_dir` (default `~/.quantmesh/metrics`).
- **`ops.limits`**: the pinned `ReliabilityLimits` contract
  (`max_drawdown_fraction` default 0.25, `max_consecutive_mismatches`
  default 5) evaluated purely over the recorded window — running-peak
  drawdown over the `equity` gauge series, and the worst
  `consecutive_reconciliation_mismatches` sample. A breach emits one
  `AlertRecord` on the M7 ledger with kind `reliability_limit`, source
  `ops:limits` and the measured/limit values in `observed`; the
  ledger's duplicate refusal makes an identical re-detection (same
  `detected_at`) a no-op, never a repeat. The M9 risk screen renders
  the alert with no further work.
- **`ops.logging_fmt`**: `StructuredFormatter` for stdlib logging —
  one JSON object per line (`ts, level, logger, message, fields`,
  sorted keys, `repr` fallback for non-serializable field values).
  `structlog` was surveyed and rejected (MIT): the structured record
  shape is a plain dict, and the runtime dependency surface stays
  unchanged (a stated goal of the M10 threat model).
- **Incident runbooks**: `docs/runbooks/*.md` (disk exhaustion,
  journal corruption, reconciliation mismatch, kill-switch engaged),
  each naming symptoms, checks and recovery; presence and section
  structure pinned by a doc test.
- **`ops.export`**: `export_audit_bundle` serializes the four
  system-of-record surfaces — M2 `OrderJournal`, M6 `MappingLedger`,
  M8 `DecisionLog`, M10 `MetricsStore` — into one
  `quantmesh-audit-bundle` (v1) JSON bundle whose content digest is
  HMAC-SHA256-signed (`hmac` + `hashlib`, stdlib) with a key held by
  the `KeyStore`. Integrity is semantic, not byte-level:
  verification re-canonicalizes the parsed content (JSON with sorted
  keys), so any change to a value fails the digest while
  whitespace-only reformatting still verifies. Any tamper, wrong key
  or malformed bundle is refused with a typed
  `BundleVerificationError` naming the failure. `cryptography` was
  surveyed and rejected: the export signature is a local integrity
  tag, not an identity assertion, and a smaller dependency surface is
  part of the threat model.
- **`ops.secrets`**: the `KeyStore` protocol (get/put/delete) with
  `KeyFileStore` as the Phase A stand-in — a plain key file under an
  explicit operator-named path (safe-filename enforced), missing key
  reading as `None`. The OS-backed keyring backend lands in Phase E
  behind the same protocol; no credential is ever stored in code.
- **`ops.cli`**: the `quantmesh-ops` console script —
  `record-metric`, `export-audit`, `verify-export` — all local
  computation; missing key file exits 2, verification failure exits 1.

### Decision 2 — Idempotency keys on the paper-kernel submission
path; recovery is journal replay verified by the ADR-0006
reconciliation discipline (Phase B, issue #59)

- `OrderRequest` and `Order` carry an `idempotency_key`
  (URL-safe shape, 1-64 chars). A keyed submission derives its order
  id from the key (`paper-<key>` when no `client_order_id` is given),
  and `PaperAccount.submit` detects a replay by key BEFORE the
  sequence is consumed or the risk gate runs: the replay returns the
  original order in a typed `SubmissionResult` with `replay_of`
  naming it — never duplicated, never re-gated, never consuming state.
  A keyed order that was originally rejected replays as that rejected
  order; a filled order replays without re-applying its fills. The
  account is unchanged by a replay.
- Keys are recorded in the order journal and participate in its
  identity: the journal read refuses two records sharing a key with
  line attribution, exactly like two order ids — a duplicate key in
  the file fails closed instead of replaying a duplicate.
- `quantmesh.ops.recover` (CLI: `quantmesh ops recover --journal <root>
  --cash <amount> [--against <account.json>] [--*-bps tolerances]`)
  is the recovery drill: it reads the journal with the fail-closed
  discipline (all refusals collected with line attribution — a partial
  append or truncated tail exits 1 and nothing is replayed), replays
  the valid records into a fresh account by pure event application
  (no risk gate, no matcher, no kill switch — the executed history
  re-books exactly as it ran; a mid-lifecycle order stays
  unacknowledged, never fabricated), verifies each order's event
  history re-applies cleanly through the state machine (no orphaned
  fills, no fabricated state), and reconciles the result against the
  surviving account snapshot with the ADR-0006 vocabulary: order
  identity (missing / orphaned-divergent), filled quantity and average
  fill price and status under the declared qty/price tolerances, and
  the position surface under the position_qty tolerance. The report is
  `clean` only with zero refusals, zero missing orders and zero ERROR
  findings; any divergence exits 1 with the findings named.
- The drill's evidence: replay with the same declared configuration
  produces the account state that ran live (equality proven by test
  across cash, fees, realized P&L, positions and every order's event
  history), and the reconciliation against a replay is all-matched
  with zero findings.

### Decision 3 — The kill switch is a global bit plus a per-venue map
on the account object; enforcement lives in the accounting risk gate
(Phase C, issue #60)

The kill switch is **not** a page flag, a model instruction or a
surface-local state: `PaperAccount` carries `kill_switch: bool` and
`kill_switches: dict[Venue, bool]`, and that one object is the single
source of truth the M9 control flips, the REST surface reports and
the enforcement gate reads — the JSON surface, the page context and
the kernel gate cannot disagree.

- **Semantics**: the global bit overrides every venue; a venue map
  entry engages a switch for exactly that venue; a venue absent from
  the map reads as disarmed (a disarm pops the entry rather than
  storing `False`, so "no entry" and "disarmed" are the same fact).
- **Enforcement lives in the accounting risk gate** (`_risk_reasons`),
  which every submission crosses before sequence consumption: while
  engaged, the submission returns a typed rejection
  (`"kill switch enabled"` / `"kill switch enabled for venue <v>"`),
  recorded as the rejected order — the journal replays the refusal.
  No model, page or adapter cooperation is required, and no AI
  surface can set or clear the switch: the gate is in the accounting
  path by construction, so "without model cooperation" is a property
  of the architecture, not a behavioral test promise.
- **Persistence**: `kill_switches` joins `account_meta` as a JSON
  column; an existing (pre-Phase-C) store is migrated additively
  (`ALTER TABLE ... ADD COLUMN`, default `'{}'`) on open — never a
  destructive migration. Reads are fail-closed like every other
  ADR-0006 surface: non-JSON, non-dict, unknown-venue or non-bool
  payloads raise `StoreCorruptionError`, so a hostile or corrupted
  meta row cannot silently disarm the switch.
- **Control surface**: the M9 kill-switch page renders the per-venue
  switches on the same confirm-gated POST contract (the `confirm`
  field the operator checkboxes), each venue form carrying a hidden
  `venue` field; a POST naming an unknown venue is refused with a
  typed error and leaves state untouched. The venue options come from
  the union of the account's engaged venues and the bound markets —
  never a free-text injection surface.

## Consequences

- Metrics, alerts and logs are local files on the same discipline as
  the existing journals: a corrupted or hostile store fails closed
  with attribution, and the export surface cannot silently diverge
  from the journals it signs.
- The M7 ledger is the single alert surface: `ops:limits` breaches
  render on the M9 risk screen with source attribution, and duplicate
  re-detection is refused by ledger identity.
- The audit export verifies locally under the operator-named key:
  `quantmesh ops verify-export` is the drill for bundle integrity,
  and the fixture suite pins round-trip, tamper-refusal (value,
  digest, signature), wrong-key refusal and missing-bundle refusal.
- Real credentials never enter the M10 code path: Phase A operates on
  an operator-named key file behind the `KeyStore` protocol, and
  Phase E's keyring backend is only exercised against a fixture.
- The submission surface is now idempotent: retrying a keyed request
  returns the original order typed as a replay and consumes nothing,
  so a client crash between kernel commit and journal write cannot
  duplicate an order, and a replayed rejected order cannot slip past
  the risk gate a second time.
- The journal's identity is keyed twice (order id and idempotency
  key): a duplicate key in the file is refused on read like a
  duplicate id, so recovery can never replay a duplicate.
- Recovery is a verification drill, not a re-execution: the replay
  re-books the recorded history without re-gating or re-matching it,
  and the exit status is 0 only for a fully clean read, replay and
  reconciliation — a corrupt journal or a divergent snapshot names its
  findings and exits 1.
- The kill switch is enforced where submissions actually cross — the
  accounting risk gate — so it cannot be bypassed by any route that
  cannot bypass the risk gate itself; a refused submission is
  journaled as a rejected order and replays as a refusal, never as a
  silent drop. The single account object keeps the REST status, the
  page controls and the gate provably in agreement (pinned by the
  status/round-trip API tests and the keyboard-only E2E drill), and
  a corrupt persisted payload fails the read closed instead of
  disarming anything.
- Later M10 decisions (scanning gate, live-enablement gate) append to
  this ADR as their phases land.
