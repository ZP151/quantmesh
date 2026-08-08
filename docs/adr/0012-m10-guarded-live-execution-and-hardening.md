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

### Decision 4 — Dependency scanning is CI-only: pip-audit over a
frozen install closure plus a deterministic license review; the
workstation's write surfaces refuse a non-loopback Origin
(Phase D, issue #61)

The supply-chain and browser-vector threat surfaces get CI gates, not
runtime features:

- **`requirements-audit.txt`** pins the frozen install closure of
  `.[dev,research]` (generated by `pip install --dry-run --report`;
  the regeneration procedure is in `docs/release-process.md`). CI's
  `security` job runs `pip-audit -r requirements-audit.txt --no-deps`
  — a newly published advisory fails the job loudly, and the frozen
  file means the scan never re-resolves a moving dependency set.
- **`tools/license_review.py`** classifies every installed
  distribution from its PEP 639/345 metadata against the allowlist in
  `docs/licenses.md` (MIT, BSD-2/3-Clause, Apache-2.0, PSF-2.0, ISC,
  MPL-2.0, 0BSD, Zlib, CC0-1.0, CNRI-Python, MIT-CMU); SPDX
  `WITH <exception>` qualifiers are stripped (they relax), and a
  Commons-Clause expression or text is refused *before* any Apache
  pattern can match. The first real finding: **vectorbt** (research
  extra) ships as Apache-2.0 **WITH Commons Clause** — source-
  available, not OSI — and no code path imported it, so it was
  removed from the extra (ADR-0009's dependency contract updated)
  rather than excepted. A kept non-OSI dependency would need an
  ADR-level decision; removal is the default.
- **Threat model**: `docs/threat-model.md` names 15 threats, each
  with the control and the test that pins it (a doc test refuses
  citations that do not resolve to real tests/files/ADRs), plus the
  two accepted residuals. **`docs/release-process.md`** records the
  branch/PR conventions, the full-suite gate, drill-evidence
  requirements, the audit-lock regeneration procedure, versioning,
  and the human-gate checklist that governs any future live
  operation.
- **CSRF hardening** (the threat model's T-14, found while writing
  it): the three write POSTs (`/watchlist/add`, `/watchlist/remove`,
  `/kill-switch`) refuse a present Origin that does not name a
  loopback host — browser CSRF always sends the attacker's Origin,
  and the workstation only ever binds loopback (Decision 2 of
  ADR-0011). An absent Origin stays allowed (the CLI/drill path).

### Decision 5 — Live enablement is a recorded approval state
machine; secrets live in the OS keyring behind a drill-gated store;
the workstation's enablement screen is read-only (Phase E, issue #62)

The long-running goal's gate — **"real-money trading, wallet signing,
live broker orders, credentials, paid infrastructure, and AI order
authority all require explicit human approval"** — is enforced as a
recorded process, not a flag:

- **`quantmesh.ops.enablement`** is a per-venue state machine
  (disabled → pending → enabled, with withdraw and revoke) persisted
  as append-only JSONL on the ADR-0006 discipline
  (`~/.quantmesh/enablement/` by default). State is *derived* from
  the ledger (the target state of the latest record per venue), so
  the ledger and the reported state can never disagree. The only
  legal edges are fixed (`request`, `approval`, `withdraw`,
  `revoke`); anything else is a typed refusal before anything is
  written, and an identical replay at the same instant is refused by
  record identity.
- **The only path to `enabled` is an approval record** carrying the
  recorded gate text verbatim (`GATE_TEXT` above). The record names
  who approved, when (timezone-aware, normalized to UTC), and which
  gate text was presented; a stale, watered-down or missing gate is
  refused by both the model and the ledger before anything is
  written. In M10 the approvals exist only in fixtures and drills —
  no live execution surface exists, and nothing in the code path can
  fabricate a real approval.
- **Transitions are CLI/operator-owned** (`quantmesh ops enable
  <venue> <kind> --actor <name>`): the CLI prints the live-enablement
  gate to stderr on every `approve` and requires `--gate-text` to
  match verbatim. The M9 workstation gains a **read-only enablement
  screen** (`/enablement`): per-venue state, the gate text, and a
  bound-ledger indicator — no form, no POST (a POST is refused
  405), because the state machine refuses any transition not backed
  by a recorded approval record and no UI transition exists.
- **`quantmesh.ops.secrets`** wraps the OS keyring behind a typed
  `KeyringStore` (base64-encoded bytes, safe-name enforcement) with a
  fixture backend for tests. Construction **refuses without an
  explicit drill flag**: the OS keyring holds real credentials, and
  the recorded gate requires explicit human approval before any
  credential store is used — so the suite never touches the OS
  keyring, and the real backend constructs only under `drill=True`
  (construction only; a missing keyring fails closed as
  `KeyringUnavailableError`).

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
- The supply chain is gated in CI, not at runtime: the audit lock is
  a frozen closure (a new advisory fails the job), and the license
  review is deterministic over installed metadata — the vectorbt
  removal is the first enforcement of "no non-OSI dependencies" and
  the review's Commons-Clause refusal keeps it that way. The threat
  model is a living contract: its doc test refuses any citation that
  does not resolve, so a control that loses its test or a threat that
  gains no control fails the suite.
- The write surfaces now refuse cross-origin sends, closing the
  browser-vector hole on the loopback bind without disturbing the
  CLI/drill path (absent Origin stays allowed) — pinned by the
  five-test `TestWriteSurfaceOriginGuard`.
- Enablement is a recorded process, not a flag: every transition is
  an audit entry naming who, when and (for approvals) which gate text
  was presented, state is derived from the ledger so ledger and state
  cannot disagree, and the gate text itself is pinned verbatim by a
  test. The read-only screen makes enablement visible without making
  it UI-ownable — the same pattern as the M9 promotion screen, and
  the write surface is absent by construction (405).
- Secrets stay behind the recorded gate: the keyring backend refuses
  construction outside a drill flag, so no code path can reach real
  credentials without a human approval record first, and the suite
  pins the refusal (T-07). This is the documented path any future
  live operation must walk: the release process's human-gate
  checklist and this decision together record the exact gate.
