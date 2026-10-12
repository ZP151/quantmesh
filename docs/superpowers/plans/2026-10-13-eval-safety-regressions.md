# Eval-discovered safety regressions implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans or superpowers:subagent-driven-development task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Refuse hostile browser origins, unresolved advisory claims and stale source quotes at their deterministic production boundaries.

**Architecture:** Repair three measured guard gaps using existing origin, critic and QuoteFence code. Preserve the original three Eval assertions and raw failed baseline; no scoring workaround, new authority, framework or data-source change.

**Tech Stack:** Existing Python standard library IP parsing, Pydantic AI contracts, FastAPI Origin guards and paper engine.

**Spec:** [#174](https://github.com/ZP151/quantmesh/issues/174); approved A research safety invariants in `docs/superpowers/specs/2026-10-12-research-foundation.md`, ADR-0010 and ADR-0014. Operator already authorized current high-blocker repairs.

Status: queued ahead of workstation#173 after Eval#160 or Linux#172 stops.
Root may implement when one slot is free; no third implementer. Original RED:
e549 `output/eval-160/legacy-assertions-audit.log/.exit=1`,3failed/3.78s on
integration2f424d0. Traced code confirms all three causes. This is a repair
refinement within existing authority, not an extension to live trading.

## Global constraints

- Keep paper=true/live=false, existing exact staging origin and legitimate local binds.
- No DNS queries, public ingress, secrets/vendor logs, broker/model calls or source/helper/global runtime mutation.
- No JobStore/request schema, baseline math, locks, workflow or new strategy changes.
- Unknown/closed display coverage remains separate from executable quote freshness.
- Preserve raw analyst/critic evidence and explicit blocked/refusal records; AI never grants order or evidence authority.
- Changes to positive test fixtures must actually supply their claimed source, not weaken an assertion. Existing Eval catalogs/runs remain immutable; changed fixture/verifier bytes require a new catalog identity.
- Two fresh Spec/Standards review rounds maximum for this new bounded repair. Applicable human trading/auth reviews and exact-head CI precede release; no bypass or speculative deploy.

## Review focus

1. A DNS name that merely resembles127/8 must not pass either bind or browser-origin checks.
2. URL parser success does not make a canonical browser Origin; unsupported scheme/userinfo/path/query/fragment/invalid port are refused.
3. A cooperative critic must not elevate a claim whose source is missing, malformed or only mentioned inside another source's text.
4. Any unsupported citation blocks the entire mixed claim; valid claims and original indices remain auditable through duplicate/model-block cases.
5. Receipt freshness cannot renew stale source evidence, while legitimate fresh quotes and no-fence demo submissions keep working.

## Task1 — Literal local Origin admission

Files: root owns `src/quantmesh/api/workstation.py`; focused new
`tests/test_browser_origin_safety.py`, existing origin-route tests as relevant.

Interfaces: retain `_is_loopback(host: str) -> bool` and
`_is_allowed_browser_origin(origin: str) -> bool`.

- [ ] RED `test_dns_127_prefix_is_not_loopback` with127.attacker.example;
  `test_noncanonical_browser_origins_refused` covers schemes, userinfo,
  invalid ports, path/query/fragment and malformed/bracketed hosts.
  Run focused pytest with a new workspace-owned basetemp and retain exit1.
- [ ] Use exact localhost/::1 and parsed IPv4 literal loopback127/8, no DNS
  prefix/resolution or shorthand numerical hosts. Browser origins require
  HTTP(S), authority only and a valid port; exact configured private staging
  origin is still admitted by its existing configuration boundary.
- [ ] GREEN literal localhost/::1/127/8 and private staging cases. Verify a
  real TestClient write surface returns the existing refusal for a hostile
  Origin, without changing absent-Origin CLI policy or enabling staging by default.

## Task2 — Deterministic supplied citation membership

Files: `src/quantmesh/ai/roles.py`, `tests/test_ai_roles.py`,
`tests/test_ai_acceptance.py`, focused `tests/test_ai_citation_safety.py`.

Interfaces: retain public ResearchPipeline construction/run/result. Extend
its private critic gate to combine model-block indices with deterministic
unsupported-source indices before building risk/portfolio prompts.
Eligible citation IDs are exact supplied context keys of the supported
`document:id`, `experiment:id`, `audit:id` forms with nonempty IDs.

- [ ] RED `test_critic_pass_cannot_allow_unknown_citation`,
  `test_mixed_or_malformed_claim_sources_block`,
  `test_text_mentions_do_not_register_citation_authority`,
  `test_duplicate_claims_preserve_indexed_critic_blocks` and
  `test_unknown_claim_excluded_downstream_and_refusal_archived`.
  Four scripted calls remain four; raw analyst/critic results are retained.
- [ ] Implement pure index-based intersection with the supplied typed-key
  set. Never regex-extract source IDs from arbitrary context content or from
  the model's own claims. A model may block additional claims, not register a
  source. One unresolvable citation blocks that claim. Preserve original
  malformed critic rejection and empty-report behavior.
- [ ] Migrate older positive fixtures to explicitly supply their existing
  document/experiment/audit data under the exact citation keys. Keep original
  raw evidence text and downstream assertions; fabricated fixture IDs remain
  rejected. This does not establish factual truth or report publication rights.
- [ ] GREEN focused cases plus AI roles/acceptance and relevant citation/audit
  regressions. Explicitly distinguish raw model pass from deterministic blocked
  claims in the archived refusal and resulting gate.

## Task3 — Source and receipt clocks for paper quote consumption

Files: `src/quantmesh/live/fence.py`, `tests/test_live_fence.py`,
focused `tests/test_quote_source_time_safety.py`; `PaperAccount` math unchanged.

Interfaces: retain QuoteFence.evaluate/resolve and FenceDecision. `resolve`
passes snapshot.data_time along with received_at. The blessed Quote timestamp
is validated source time, not the local delivery time.

- [ ] RED `test_old_source_new_receipt_is_rejected_without_fills` retains
  the original one-hour-old fixture. Parameterize missing/malformed/naive/future
  source and receipt clocks, source-age30s boundary and stale receipt/new source.
- [ ] Validate timezone-aware source and receipt clocks against explicit now
  and the existing max_age (default30s). Missing/invalid/future clocks refuse
  with a fixed reason; no naive-aware TypeError escapes. Both clocks must be
  within the horizon. Pass source time to the existing matcher Quote.
- [ ] GREEN actual PaperAccount zero fills for old source and a fresh-source
  valid fill, exact instrument/kind/continuity/depth regression and no-fence demo.
  Closed latest-session chart/metrics state never changes this order boundary.

## Slice verification, review and integration

- [ ] Run all three original desired Eval assertions against the repaired
  candidate, without editing/xfailing them. Archive exact imported source bytes
  and RED/GREEN; preserve the old failed run. Do not rerun all24 cases until
  the Eval implementer freezes a compatible post-fix catalog deliberately.
- [ ] Run focused origin/roles/acceptance/quote/paper and related workstation
  boundary checks, Ruff, formatting/diff. Broad relevant gate runs once at the
  coherent slice boundary; no hourly full suite or existing native owner-crash rerun.
- [ ] Two-axis fresh review, at most two rounds. Record any residual issue
  without absorbing unrelated feature or architecture changes.
- [ ] One reviewed coherent commit and iteration/ACTIVE checkpoint, push the
  integration branch. Final milestone PR/clean-checkout/required CI/human
  reviews/private deployment stay open. No failed baseline is overwritten.
