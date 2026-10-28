# Native daily quantity v2 implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline. One implementation writer; fresh read-only source review, max two rounds.

**Goal:** One fixed synthetic candidate protocol executes T/TO/B50/B100/C at5/10bps through the sole native daily accounting loop, with original result reopening and legacy new-submit refusal.
**Architecture:** Refactor existing run_cashbook in place with an internal quantity-policy seam; retain existing cash/fees/ex-pay/marks/metrics/reconciliation. New native_daily_candidate validates its distinct closed engineering protocol, adapts the unchanged policy and binds immutable results. Legacy ReplayService only reopens existing IDs/objects; it cannot start old profiles under a new engine hash.
**Tech:** Existing Python3.13/pandas/NumPy/pytest/Ruff read-only; no installs. Decimal conservative view only, existing float ledger unchanged.
**Spec:** [approved decision](../specs/2026-10-28-native-quantity-v2.md), [scope](../specs/2026-10-28-native-quantity-v2-scope.md). Human answer call_b68f5a73da68424cb4dcc67945ff3868, approved SHA52be20ddd5511823980347bf127e697d4baa96f8efb4a6b3648758dfafd3a46e. Issue245.

## Constraints and locks

- ACK2026-10-28T15:35:39Z;20min plan due15:55:39Z, first increment17:35:39Z, reviewable19:35:39Z. Goal stays active until actual publisher CI/merge evidence; no phase reset.
- Base actual mainb985d23565de049d5717b4e96929bc21707a0e9a; native isolated WT0038-native-quantity-v2, branch codex/0038-native-quantity-v2.
- Modify research/spy_replay_engine.py and spy_replay.py; add research/native_daily_candidate.py, tools/research/run_native_daily_engineering.py, own tests/spec/plan/iteration. Legacy test fixtures/expectations requiring new old-profile execution must migrate to archived original engineering evidence/read-only or explicit rejection; never add a test-only execution bypass or weaken existing integrity/qualification/numeric checks. Record exact affected test locks before editing.
- Do not change UI trace_runner/wrapper/routes/API/entry/frontend/generated or frozen trend_overlay_candidate.py. No new provider/data/account/SDK/host/model, paid resource, trading/Paper/live, budget increase, old OOS/financial/native/51-case reruns, or original source/data artifact mutations.
- Same64MiB TREND-EVAL-GAP236 cohort. Checkout rounded58,298,368B + git WT metadata598,016B + old output40,685B, plus1MiB unknown shared metadata and2MiB tests/output reservation fit67,108,864B. Preserve unknowns/failures; no refunds. Hard caps are **8,000,000,000 /4,000,000,000B decimal**, not prior erroneous GiB values. Recheck bounded allocation at milestones; no npm/pip/venv copies.

## Review focus

1. One accounting loop only; all arms share costs/ex-pay/marks and no fee is charged by policy.
2. View rounding is downward1e-8 without changing ledger balances; actual cash/concentration numeric mismatch fails, never rounds an extra share.
3. Quantity cancellation vs persistent full-exit origin and terminal-open boundary remain distinct.
4. Legacy new-submit rejection happens after original-ID idempotent read and before claim/calculation; archived v1/v2/v3 proof checks stay intact.
5. Protocol/model/source/data/arm/cost identities and real/old-once input rejection happen before math/publication; reopen never recalculates.

## Task1 — kernel seam and legacy boundary (first milestone)

Interfaces in existing engine: frozen QuantityOrder(signed_quantity,requested_quantity,max_fraction,metadata); internal _quantity_policy optional hook in run_cashbook with propose/open-filled/closed notifications using readonly scalar/account snapshots. Only run_cashbook applies cash/share/receivable/cost/mark updates. Legacy control uses the same loop with old target selection. Metrics/_reconcile expressions retain their role; source SHA changes honestly.

- [ ] Write new tests/test_native_daily_kernel.py: hand-derived legacy synthetic numeric control, one fixed quantity/ex-pay/cost ledger, volume partial/terminal failure, negative cash/concentration refusal, single-step hooks and causal close/open ordering. RED missing seam before implementation.
- [ ] Write tests/test_native_daily_legacy.py: new legacy submit refused with engine calculation spy untouched; genuine committed legacy_root original v1 report/decision bag reopens same ID/bytes/digests without calculation, with changed engine source; proof tamper still rejects. No old market bytes or old test suite execution.
- [ ] Run new files with existing root venv: `python -B -m pytest tests/test_native_daily_kernel.py tests/test_native_daily_legacy.py -q --basetemp=output/native-quantity-v2/t1 -p no:cacheprovider`; retain bounded RED/GREEN logs. Set PYTHONDONTWRITEBYTECODE=1.
- [ ] Refactor only existing loop; add guarded internal callbacks, exact original cost line, post-fee numeric checks. Retire legacy submit using existing input_not_qualified public code; preserve existing-ID branch and all read/proof verification. New options truthfully unconfigured/read-only.
- [ ] Prove GREEN and scoped Ruff/format, numeric control/cash/receivable and old bytes evidence; commit coherent milestone.

## Task2 — closed engineering protocol and actual matrix

New module interfaces: engineering_input(case='campaign-v1') -> trusted closed fixture; freeze_protocol(input) -> canonical bytes; evaluate(input,protocol_bytes) -> canonical result; save/read_result(ObjectStore,ref) -> original immutable bytes. No generic data paths/callables in public inputs; real input disabled. New internal arm adapter calls unchanged on_close/size_at_open/on_fill; cash snapshots floor exact float-to-Decimal to1e-8, raw decimal prices <=8dp; report preserves original unrounded ledger and conversion delta. Native guard refuses any actual numeric mismatch.

- [ ] Add failing tests/test_native_daily_candidate.py for fixed5arm×2cost matrix, generated OPEN fills, ex/pay, prior policy origin/cancellations/terminal and semantic buy_fill_count; source/protocol/input/role/old-profile identity tamper rejection and no math on refusal; content identity/reopen with calculator spy; future close cannot change earlier fills.
- [ ] Implement fixed engineering-only protocol with namespaced schema, candidate/policy/kernel/adapter/runtime/data/action/calendar/window/cost/arm/numeric-view identities. Retain source-use/OOS/trial unknowns; no real PASS. Reuse existing ObjectStore/calendar/fact models/metrics, not old ReplayInput as new authority.
- [ ] Implement tools/research/run_native_daily_engineering.py: fixed case selector, text/JSON result, original output optional owned directory only, no market-data/strategy upload option. Run actual fixture once per necessary milestone, retain original result and finite proof.
- [ ] Run affected new tests and necessary migrated legacy-contract tests only, without old financial/OOS/native/51 suite or broad Windows rerun. Source compatibility migrations must preserve archived read and negative-proof coverage.

## Final gate and handoff

- [ ] One fresh source review of full slice, maxR2; fix material issues with RED/GREEN. Third structural issue returns to planning with smaller scope.
- [ ] Scoped format, repository Ruff at coherent final boundary, diff/submodule checks; resource snapshot includes failed temp/logs, no cleanup/refund. No author push/CI/tag.
- [ ] Own iteration records Planner/Quant/Implementer/Reviewer/Verifier, user CLI and actual synthetic results, legacy old SHA and source migration identities. Freeze commit/tree/source/artifact hashes and bounded bundle/HANDOFF for sole publisher.
- [ ] Publisher performs applicable final CI and normal merge. Consume exact final receipt before completing Goal; source ready alone is not Goal completion.

Self-review: no second cashbook/matcher/cost/metric implementation; core changes, conservative view and retirement are explicit approved behavior.4h is an engineering review target, not real-data qualification. A genuine regression in old immutable records or arithmetic is a stop condition, not a reason to change expected values.
