# Report-bound SPY sample evidence UI

> Execute this independent slice inline with meaningful RED/GREEN checks, one bounded independent review (maximum two rounds), and verification before source freeze. Existing PR226 and its completed reviews/acceptance remain unchanged.

**Goal:** Opening one saved report identifies its own sample role, cutoff, structural facts and freshness applicability without a new numerical run or substituting the next configured sample.

**Base:**345470491e2f83b5c36409c13a16cb04c5357afc/treefd11f597f3c9bb986a1b507736b5c39e3bedc39b; branchcodex/spy-replay-sample-evidence in the reused independent UI worktree.

**Specification:** root-forwarded `QM-SPY-D1-EVAL-SAMPLES-v1`, SHA78873b12b9fb96c4bc396d6eb4a8aa45abf97faaeef217f427e9222354df580a. ACK2026-10-25T07:04:34Z; hard deadline09:04:34Z. Backend owner separately freezes exact metadata/reportv2/read-view contract; root forwards once. Do not guess field names or calculate session-age from calendar days.

**Architecture and layout:** Extend the existing Report step with one compact “This report's sample” evidence region. Show immutable role/cutoff/structural summary and a separately labelled read-time freshness line. Native disclosure holds sample ID/version/hash, freeze/receipt/review times and necessary source/PIT states; missing v1 facts remain unknown and synthetic source timestamps remain N/A. Preserve the three-step layout and incumbent styling; do not duplicate net-return, benchmark, drawdown or stress cards. Add just one line of existing long_entries and absolute-traded-notional/initial-capital ratio, explicitly nonannualized. Fills are not round trips or independent samples. Short-sample ratios remain folded with an applicability explanation.

## Ownership and constraints

Only SpyReplayPanel.tsx, typed spy-replay-api.ts, two new focused test files and this plan/owned iteration evidence. No backend, currentPR226, API generation, production static assets,8880/8878, market/server actions, new dependencies or public sample/qualification/upload controls. Original report bytes/digest/decision references never change. Real qualification and Paper remainfalse. Internal F0 generation/math belongs to backend; UI only tests zero/null semantics from its frozen contract.

## Steps

- [x] Add v1 sample-card REDs: its original snapshot/cutoff, unknown freeze/receipt/review/quality, never current options B; compact evidence disclosure; numeric zero versus unavailable; turnover labelled nonannualized and fills not round trips.
- [x] Implement the v1/unknown browsable structure before30min without waiting on backend math.
- [x] Consume exact frozen v2/read-view contract. Add API validation REDs for version/identity/freshness mismatch and legacy compatibility, then implement guarded optional read-time view and immutable evidence parsing.
- [x] Add v2 trusted facts, synthetic N/A and real unknown presentation tests; Friday→weekend completed-session semantics come from the backend view and are not recomputed in JavaScript. Never manufacture missing times or trial count.
- [x] Run only new focused metadata/old-report/disclosure/unit tests, own-dist build, changed-file lint, diff; inspect desktop+phone in one batch with at most one correction confirmation.
- [x] Independent review of this delta, at most two rounds; aggregate corrections. Update the owned iteration record; freeze clean commit/tree/handoff and stop for root/publisher integration. No old full-suite, market sample or previous acceptance reruns.

## Result and integration boundary

2026-10-25:32 new focused tests pass; own-dist build, scoped lint and whitespace checks exit0; detector returns[]. Two independent review rounds end READY. The first review's claimed original-v1 offset failure was a PowerShell timestamp-conversion mistake: raw original bytes store+00:00. A constructed valid-v1+08:00 compatibility case remains covered; it does not describe the actual original artifact. Freeze-ref binding was also tightened in the aggregate correction batch.

Four desktop/phone v1/v2 previews read the original v1 bytes and the backend's actual frozen F0 report/GET payload; downloaded report bytes remain identical. This is transport-mocked UI evidence, not combined live acceptance. Full evidence and role outputs: [iteration](../../iterations/0038-spy-report-sample-ui.md). Root/publisher owns source combination, release checks and final PR; current226/8880/8878 remain untouched.

## Acceptance boundary

The operator can distinguish a fixed engineering fixture from real research evidence and identify which source/timing facts are missing. Old jobA always displays A's report identity, never B's current input metadata. Freshness is independent read-time evidence with snapshot and report binding; unknown applicability cannot become a green data/strategy verdict. Engineering sample checks do not grant real-data, independentOOS, Paper or live authority.
