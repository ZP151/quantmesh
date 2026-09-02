# Iteration 0027 — Evidence-backed Decision Copilot

- Status: active (design approved; Slice 1 execution)
- Started: 2026-09-02
- Tracking issue: [#122](https://github.com/ZP151/quantmesh/issues/122)
- Branch: `codex/0027-evidence-backed-decision-copilot` from
  `origin/main` at `f77b565`
- Design:
  `docs/superpowers/specs/2026-09-02-evidence-backed-decision-copilot-design.md`
- Executable plan:
  `docs/superpowers/plans/2026-09-02-decision-packet-foundation.md`
- Ledger: this file

## Product wedge

For a research-minded individual active trader, turn one ticker into a
verifiable, risk-first decision package in no more than two minutes, make it
executable only as a guarded paper proposal, and preserve it for monitoring,
outcome attribution and replayable review.

The product lesson from [KairoTrend](https://kairotrend.com/) is the value of a
short path from chart context through risk and review. QuantMesh does not copy
its AI signal or pattern-recognition proposition. QuantMesh compresses the same
journey around owned evidence, deterministic risk, paper authority and replay.
The current public Chrome-extension footprint is not treated as evidence that
feature-count parity is a useful target.

## Primary user flow

```text
Ticker / Watchlist
        ↓
Market state and key levels
        ↓
Bull / Base / Bear scenarios
        ↓
Entry zone, invalidation, stop, target and paper size
        ↓
Reject / Watch / Paper proposal
        ↓
Monitoring, outcome attribution and review
```

The flow stays inside Instrument Workspace. Evidence details use in-place
disclosure or drawers and preserve the selected instrument, time range and
draft action.

## Core artifact

`DecisionPacket` is a versioned, replayable composition rather than a BUY/SELL
label. Its deterministic foundation records:

- venue/instrument identity, horizon, as-of time and data freshness;
- market structure, trend state, support/resistance and invalidation levels;
- Bull/Base/Bear scenarios with calibrated probabilities or explicitly labeled
  confidence semantics;
- entry zone, stop, target, R multiple and suggested paper size;
- exact data, manifest, quality, forecast/model, benchmark, out-of-sample,
  leakage and cost evidence references;
- AI explanation/critique with resolvable citations, or an explicit unavailable
  reason when no valid model result exists;
- operator disposition: Reject, Watch or Paper proposal;
- immutable references to risk verdict, confirmed paper order/result and later
  review records.

The analysis snapshot is never rewritten. Later disposition, paper and review
events append a new version or immutable referenced record so the original
as-of decision remains reproducible.

## Vertical slices

### Slice 1 — DecisionPacket foundation

**User action:** select NVDA, inspect one composed decision view and save Reject,
Watch or Paper proposal without leaving Instrument Workspace.

**Observable value:** one deterministic NVDA DecisionPacket survives restart
and reopens with the same evidence and disposition.

**Reuse:** existing instrument history/workspace services, price forecast
artifact and registry, paper proposal ledger/service, risk kernel, audit and
demo acceptance station. Do not add another model framework.

**Stop condition:** NVDA happy path, stale-data block and risk-refusal browser
states pass; the measured ticker-to-save interaction is at most two minutes.

### Slice 2 — Structured Copilot

**User action:** request an explanation or challenge of the deterministic
packet and inspect its citations in place.

**Observable value:** schema-valid AI commentary identifies the exact packet
facts it explains or challenges. Missing service, timeout, invalid schema or
unresolvable citation degrades only the AI panel.

**Reuse:** the existing structured model gateway, analyst/critic boundaries,
redaction, citation resolver and DecisionLog. AI cannot alter scenarios,
evidence gates, size, risk verdict or action authority.

**Stop condition:** both valid cited output and model-unavailable paths preserve
the deterministic packet and action semantics.

### Slice 3 — Local monitoring

**User action:** save one or more local conditions from the packet: enters entry
zone, crosses invalidation, data becomes stale or forecast drifts.

**Observable value:** watch conditions are visible in Instrument Workspace,
survive restart and emit typed local events without provider or order authority.

**Stop condition:** deterministic trigger and non-trigger replay are proven for
NVDA, including stale evidence; no external notification service is required.

### Slice 4 — Outcome and review

**User action:** reopen a past packet and compare its scenarios with the actual
path, paper result and risk execution, then save a review.

**Observable value:** a replayable decision journal connects the original
as-of evidence, operator action, paper outcome, attribution and review without
mutating history.

**Stop condition:** clean-restart NVDA E2E replays the complete packet-to-paper-
to-review lineage and explains both accepted and rejected paths.

## Acceptance criteria

- [ ] On the deterministic NVDA acceptance station, timing starts when the
      operator submits the ticker or selects its watchlist row and stops when
      Reject, Watch or Paper proposal is durably saved; elapsed time is at most
      two minutes. Application installation/startup and optional AI latency are
      outside the timer.
- [ ] The primary loop remains in Instrument Workspace and requires no CLI,
      database access or route hopping.
- [ ] One desktop view makes market state, scenarios, risk, evidence, blockers
      and actions scannable; compact layout preserves the same ordered flow.
- [ ] No model service, model timeout or invalid AI result prevents the
      deterministic packet from rendering or being saved as Reject/Watch.
- [ ] Stale, low-quality, leakage-affected or missing evidence blocks Paper
      proposal with an actionable reason.
- [ ] Every Paper proposal passes the existing deterministic risk kernel and
      an explicit second confirmation before any paper order is created.
- [ ] DecisionPacket, evidence references, operator disposition, paper result
      and review recover from a clean restart and replay without identity drift.
- [ ] NVDA E2E covers the happy path, stale-data block and risk-refusal state.
- [ ] English and Simplified-Chinese safety semantics, keyboard operation,
      reduced motion and 390 px no-overflow remain intact.

## Non-goals

- Qlib, Darts or any three-framework comparison as an iteration exit criterion.
- Model leaderboard, broad algorithm platform or unrelated research registry
  expansion.
- TradingView/browser extensions, mobile apps or external notification clients.
- Real trading, broker credentials, mainnet signing or autonomous execution.
- Social/community features or a large pattern-recognition catalog.
- More instruments or models before the NVDA loop demonstrates the wedge.

## Safety and evidence invariants

- External venues remain read-only and execution remains paper-only.
- AI output is research input and never direct order authority.
- Synthetic/demo evidence is labeled and cannot qualify real evidence.
- Backtest/forecast claims retain chronological, out-of-sample, cost and
  leakage evidence. Confidence without calibrated semantics is labeled as
  qualitative and cannot masquerade as probability.
- Paper sizing is a suggestion until the existing risk service accepts it; the
  operator's second confirmation remains mandatory.

## Agent delivery contract

- At most two tracks run: this product track and the independent 0021 soak
  maintenance track. Neither edits the other's files or state.
- Every slice starts with Planner/Product's one action, success measure and
  forbidden expansions, followed by Quant Researcher's bounded review of
  leakage, costs, metrics and confidence semantics.
- Implementer owns one API/page/state/test vertical loop. Reviewer evaluates
  the demonstrable boundary in at most two rounds; a third structural failure
  returns the slice for scope reduction.
- Verifier runs targeted checks during development and full gates at slice
  commit/final PR boundaries.
- Each prompt names one deliverable, one stop condition and forbidden actions.
  Side defects and other unrelated findings are recorded without expanding the
  task unless they block its user action or safety acceptance.
- Daily checkpoints state which user loop became possible or more trustworthy;
  test counts and ledger length are supporting evidence, not progress metrics.

## Non-blocking maintenance

- Evaluate the Impeccable v4.1.2 update in a separate maintenance task.
- Regenerate or reconcile the design sidecar with `DESIGN.md` in a separate
  maintenance task. Neither blocks product-direction approval or Slice 1.

## Role evidence — Slice 1 start, 2026-09-02

- **Planner/Product:** selected the two-minute ticker-to-saved-decision wedge,
  one-page constraint, four vertical slices and explicit exclusions.
- **Quant Researcher:** retained exact data/model/benchmark/out-of-sample/cost/
  leakage bindings; forbids converting price quantiles or empirical coverage
  into scenario probabilities; requires trusted manifest/quality pairs and
  separately named promotion/proposal freshness. Account fee and matcher
  slippage are pinned while half-spread is explicitly resolved by the existing
  confirmation quote rather than fabricated as zero.
- **Implementer:** Task 1 completed ADR-0019, strict packet/domain contracts,
  the deterministic composer and fail-closed JSONL lineage store through
  `4409bcf9d630`. Task 2 now owns only the Workspace/API/runtime/demo binding.
- **Reviewer:** Task 1 used its two permitted corrective rounds. The final
  verdict was APPROVED with no Critical, Important or Minor finding; notably,
  contract-level validation now rejects real forecast evidence without paired
  manifest and quality IDs even when callers bypass the composer.
- **Verifier:** isolated worktree bootstrap is complete. Before behavior
  changes, the adjacent Python baseline passed `122` tests with `3` skips in
  `365.09s` using a worktree-local basetemp; the adjacent frontend baseline
  passed `35` tests in `4.50s` under Node `22.12.0`.
  Task 1 final verification passed `76` tests with `3` expected skips; focused
  Ruff and `git diff --check` passed.

## Current frontier

Execute Task 2 of
`docs/superpowers/plans/2026-09-02-decision-packet-foundation.md`: bind the
reviewed DecisionPacket domain to Instrument Workspace, durable same-origin
APIs, production/demo roots and the existing paper proposal authority. Stop at
the Task 2 review boundary; do not implement frontend UI or Slices 2–4.
