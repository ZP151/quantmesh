# Iteration0038 — fixed synthetic trend-overlay policy trace

Issue [236](https://github.com/ZP151/quantmesh/issues/236). Approved2026-10-27 by direct human reply recorded in output/0038-orchestration/parallel-slices-human-approval-20261027.json in the research-integration worktree. One-page SHA01313cc5d4563260ef85aba59b5b1446dfc91881176a4c151cbfa6e48ce6b066.

## Planner

One action: run a fixed case and inspect independent trend/overlay decisions, allowable quantities and campaign transitions following explicitly supplied fills. Success: reproducible explained policy trace; no financial performance or generated-fill evidence. Exact [plan](../superpowers/plans/2026-10-27-trend-overlay-policy.md) and [approved design](../superpowers/specs/2026-10-27-trend-overlay-policy.md). ACK15:37:13UTC/23:37:13SGT;2h/4h targets start here, not at the sealed morning research.

## Quant researcher

Reuse strict public DoubleMA10/20 concept and prior disambiguated overlay, not native execution or a named trader's system. Cash and receivable are supplied snapshots; no market sample, P&L, company-action engine, cost calibration or unseen OOS produced. Current legacy volume/venue facts remain unknown; no real capture or once-budget use. Whole old SPY engine remains byte-identical. Source reuse/license constraints remain ADR0005/0015/0029; no copied upstream code or dependencies.

## Implementer

Sole bounded writer in isolated native worktree; branch from actual main0e01442. TDD results and rulings will be appended at green checkpoints. No API, persistence, Worker, generated UI, order or release-version changes.

First actual increment15:46:31UTC (23:46:31SGT),9m18s after ACK:37 pure-policy tests plus4 CLI tests GREEN, actual campaign command exit0. Initial RED40failed/1passed; the CLI-invalid-case test initially passed because a missing script also exits2, so it was strengthened to require argparse usage before CLI implementation; then4CLI tests failed. Both logs retained.

Subsequent boundary test exposed ambient Decimal precision changing fixture friction/trace identity. One failing test fixed by explicit40-digit local context, then46PASS. A test requiring hand-computed moving averages in the decision failed before implementation; explanation now exposes F/S/priorF/priorS, then47PASS. Pre-format long-line/format failures were retained and corrected; scoped Ruff now passes. No financial runner or existing financial suite ran.

Rulings: synthetic session numbers are ordering ordinals, not dates/calendar certification. `terminal=True` on a close precommits the **following** open as the final liquidation boundary; it does not look at a final close. Full ex/pay/settlement/marking is outside this pure-policy slice, so C9 and accounting parts of C4/C10/C11 remain future integration oracles. Exact provided-fill fees are displayed as a proxy, never written to a cash ledger. Numeric fixture inputs use finite nonnegative Decimal values, not binary floats.

## Operator usage and visible result

From the repository root with the existing Python environment:

```powershell
python tools/run_trend_overlay_candidate.py --case campaign
python tools/run_trend_overlay_candidate.py --case exit-cap
python tools/run_trend_overlay_candidate.py --case cash-cap --format json
```

Only the three fixed IDs and text/json formats are accepted; no input path, uploaded code or market-data option. The JSON trace contains full supplied fixture observations/account/fill values, source/fixture/content SHA256s and both overlay arms. Text is rendered directly from the same computed trace.

Campaign: both arms request/permit333 shares from the50%-inclusive budget at supplied open150. At the next close125, overlay_on requests/allows33 additional shares while overlay_off holds. Close190 proposes a33-share reduction only with overlay; scheduled terminal open200 exits the remaining333 in both authored fixture arms. These are policy decisions followed by **provided** fills, not generated executions or a profit comparison. Cash snapshots are preauthored per arm, not computed after trades.

Exit-cap: strict exit25 shares permits10; later hold closes still request remaining15 then5 until supplied fills flatten the campaign. Cash-cap: receivable100 with cash0 permits0; the post-fee75% boundary also permits0. Threshold stage requests are one-shot, including zero/partial supplied fills. Actual accounting/promotion/data qualification remains absent; old SPY once/OOS evidence is untouched.

## Reviewer

Fresh read-only code review at the demonstrable CLI boundary, at most two rounds; prior morning document review is historical and not reused as source approval.

Source R1 reviewed92bd488 and independently ran47 new tests (exit0). Two P2s: flat terminal close could enter; partial full exits lost original decision identity. Both reproduced with failing regressions before correction. Terminal now suppresses entry in both arms and retains a terminal-session fence after flat/supplied exit, preventing window extension; the additional fence regression first failed. Full exits retain the original immutable Action through partial/zero/unavailable continuations and terminal priority, clearing it only when actually flat. A terminal action can enforce final liquidation without relabeling the original trend-exit cause/identity. R2 is limited to this material delta and affected regressions.

## Verifier

Targeted new tests and actual fixed-case CLI outputs required. Sole publisher owns final applicable CI/integration; historical financial suites will not be rerun by this owner. Final raw logs, trace, source hashes and commit will accompany the handoff.

Final source candidate b9daeb77463ba3c4b97d6ed7a1bc160f0f8318d5: author51PASS in7.17s; independent R2 also51PASS, READY, both R1 P2s closed and no remaining blocking finding. Existing engine SHA remains6e8ad80f134b7c1f44bcb4cb7695e784009953aba9060326e8ecb2a54e624b8e. Repository Ruff, scoped formatting, whitespace and submodule status are recorded in the handoff checks. No legacy full pytest, market/financial run or CI/tag/deploy by this owner; the sole publisher handles final applicable CI/merge separately from the rc1 frozen candidate.

Actual three CLI cases in both formats exited0 on that source. Final campaign content SHA24c9985fb8c772dc77f0deca5f04f6e07a1bc7ed1c935c9fe0f5b16bd8318b07; exit-cap9fafb122365bec13403904ad099a8a1a749832a02f71717b14bf36b61e1f6467; cash-capa760869be025e47b5a53d5ee21ccf830d2c6571369fbd40110ffd4f66f259edf. Source identity is pinned in each trace; fixture hashes remain distinct from result identity. Stable identity across repeated CLI invocations and across ambient Decimal precision is covered by new tests. No GUI/platform or strategy-returns chart was created; readable text is actual computed CLI output, not a mock screenshot.

Source and reviewer raw evidence, usage, three text/JSON examples, progress and immutable HANDOFF are in `output/0038-trend-overlay-implementation-20261027/`. Morning research output remains sealed and separate. Final documentation-only checkpoint follows the reviewed source without changing policy/CLI/test bytes. Remaining work is publisher integration plus any later separately approved cashbook/profile design; no real-data gate or OOS claim is upgraded by this engineering delivery.
