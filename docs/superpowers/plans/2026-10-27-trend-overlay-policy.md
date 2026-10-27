# Fixed synthetic trend-overlay policy implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline; one fresh read-only whole-slice reviewer, at most two rounds. No implementer subagents.

**Goal:** Inspect a deterministic fixed-case CLI trace comparing overlay off/on, with every proposed share quantity and campaign transition explained.
**Architecture:** Standard-library immutable policy values and three explicit steps: on_close -> decision, size_at_open -> constrained research proposal, on_fill -> state update from a supplied fixture event. No generated fills, ledger, P&L, external data, execution authority or route registration.
**Tech stack:** Existing Python3.13 / pytest / Ruff; Decimal for exact budget and threshold boundaries; JSON/SHA256 for content identity.
**Spec:** [approved one-page](../specs/2026-10-27-trend-overlay-policy.md), [frozen contract](../specs/2026-10-27-trend-overlay-policy-contract.md). Approval SHA01313cc5d4563260ef85aba59b5b1446dfc91881176a4c151cbfa6e48ce6b066. Issue [236](https://github.com/ZP151/quantmesh/issues/236).

## Global constraints

- Worktree branch codex/0038-trend-overlay-policy from actual origin/main0e01442; original morning specification remains sealed.
- ACK2026-10-27T15:37:13Z /23:37:13SGT. First increment due17:37:13Z, reviewable due19:37:13Z; do not reset between tasks.
- Only new src/quantmesh/research/trend_overlay_candidate.py, tools/run_trend_overlay_candidate.py, tests/test_trend_overlay_candidate.py and own docs/iterations, specs, plan. No other source writer.
- Whole spy_replay_engine.py SHA6e8ad80f134b7c1f44bcb4cb7695e784009953aba9060326e8ecb2a54e624b8e unchanged. No API/DTO/Worker/locks/versions/generated/README/rc1 changes.
- No new packages, source imports from native vn.py, data/SDK/host/model/order calls, financial backtest, original suite, consumed-OOS run, Goal or timer. Public source research is already complete; no repeated browsing.
- Synthetic ordinal sessions model only ordering; no claim of calendar, vendor, PIT or actual fill qualification. No dividend-credit or returns calculation. Paper default/live disabled stay unchanged.

## Review focus

1. Stage10% on499 shares rounds49, not50; exact equality and fee-inclusive floor use Decimal.
2. A close/open/fill out of order or from another pending action is rejected, not silently accepted.
3. Cash0/receivable>0 and pre-fee75% boundary must not permit an unaffordable extra share.
4. Partial full exits persist across later hold; partial normal stages consume once; a zero-fill entry creates no anchor.
5. Fixed CLI rejects paths, unknown cases and malformed supplied events; canonical trace identifies inputs, implementation and outcomes without wall-clock noise.

## Task1 — bounded policy API and directed tests

Create source and test files named above. Interfaces: frozen Account(cash,shares,receivable), Close(session,closes,available,terminal,unsupported_action), Open(session,price,prior_volumes), Fill(session,quantity,price), Campaign, Action, SizedAction; module functions on_close(state,close,account,overlay=True), size_at_open(state,action,opening,account), on_fill(state,sized,fill), each returns new immutable state plus observable decision where applicable. Campaign quantities only, no cash ledger.

- [ ] Write tests for strict10/20, equality,100-prior warmup, next-open ordering, stale/unsupported data, cash/fee/cap constraints, independent signal vs sizing, stage/jump/priority/reset/full-exit latch and provided-fill validation.
- [ ] Run `python -m pytest tests/test_trend_overlay_candidate.py -q` using the existing root venv and save RED. Missing source initially fails collection; subsequent test batches must fail assertions on missing behavior, not a broken import.
- [ ] Implement exact pure policy. Entry budget50% including fee; post-fee concentration75%; prior20 median-volume cap1%; fees5bps (fixed demo) with optional10bps typed opening input for contract stress; dividends only supplied receivable. Positive finite numeric values, integral nonnegative shares, consistent campaign/account required.
- [ ] Run same targeted command and scoped Ruff/format; save GREEN. Do not run legacy financial suite.

## Task2 — actual fixed-case CLI and stable readable traces

Create tools/run_trend_overlay_candidate.py; extend the same test file. CLI `--case campaign|exit-cap|cash-cap`, `--format text|json`, defaults campaign/text. Only fixed case IDs; stdout read-only, no file or strategy path arguments. Fixtures specify account and fill snapshots explicitly, never derive cash from generated trades.

- [ ] Add failing CLI subprocess tests: unknown case/option refusal, same input byte-stable JSON identity, both overlay arms, synthetic labels/no-return fields and actual on_close/size_at_open/on_fill outputs.
- [ ] Run narrow selection to observe RED before implementing CLI/fixture presentation.
- [ ] Implement fixed fixture event stream and comparison renderer. Trace body pins case-input digest, policy/CLI source digests, per-step inputs/decisions/state, assumptions and evidence type; trace SHA256 covers canonical JSON body excluding its own digest. Human text uses the same trace objects, never a separate invented display.
- [ ] Run full new test file, actual three cases/text+JSON, validate identity and unchanged legacy file. Save raw outputs/commands/exit codes to own ignored output/0038-trend-overlay-implementation-20261027.

## Final boundary and handoff

- [ ] One fresh independent spec/quality review of the whole changed slice, maxR2. Fix only material delta with RED/GREEN and the targeted suite; no third structural patch cycle.
- [ ] Own iteration contains Planner/Quant/Implementer/Reviewer/Verifier outputs and actual user command/result plus limitations. Own usage describes fixed inputs, no actual fills, no profitability/cashbook/data admission.
- [ ] Before coherent final commit run new test file, scoped format/lint, repository Ruff once at slice boundary if applicable, git diff --check and submodule status. The sole publisher owns broad CI/final integration; do not independently rerun old full suites or tag rc1.
- [ ] Freeze tested reviewed commit/head/tree/file hashes, raw logs, CLI examples, approval and progress in immutable HANDOFF; no source changes after freeze. Deliver to root without creating PR/CI/release competing with sole publisher.

Self-review: all first-policy requirements map to tasks1/2; full ex/pay/marking/settlement accounting and real-data metrics are explicitly excluded. Thirteen research counterexamples are mapped by policy applicability, not mechanically turned into a second backtester. Operator already supplied native execution method and approved scope; no additional plan-approval pause.
