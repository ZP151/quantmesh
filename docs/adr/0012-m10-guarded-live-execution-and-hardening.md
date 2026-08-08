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
- Later M10 decisions (idempotency/recovery discipline, kill-switch
  enforcement, scanning gate, live-enablement gate) append to this
  ADR as their phases land.
