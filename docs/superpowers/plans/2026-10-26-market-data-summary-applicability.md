# Market-data summary applicability P2

> Implement inline with TDD, one narrow independent review(max2 known correction rounds), source freeze and root handoff. Root approved the exact presentation-only scope; no further design approval.

**Goal:** Explicit market-data-only pages say strategy evaluation has not been run and omit the misleading statistics/forecast summary, preserving observed history and ordinary chart behavior.
**Spec:** Root's approved P2 technical boundary,2026-10-26; issue[218](https://github.com/ZP151/quantmesh/issues/218). Before native UI receipt58007dd44f642f18cd66e4374c40751cdcdd7bd961c6752b6a76ff5a5c726b5f; HANDOFF4fc581508114bf47fa3e04fbf18ef8f670e98e09a53aac7ec465c1683e9c1ee0. Actual base198a9f8776ed6531c8ca206086f4a600e1969a65/tree006714ab12e841048162099ec9e06f36e3422154. ACK07:45:44Z; firstRED/GREEN08:00:44Z; hard08:30:44Z.
**Architecture:** MarketCanvas owns the internal IndicatorStrip. Add optional showStatistics presentation prop with default old behavior; only the restricted InstrumentWorkspace call passesfalse. Add one bilingual message. No data, math, threshold, freshness, provider or ordinary-mode changes.

## Files and tests

- Production: frontend/src/screens/InstrumentWorkspace.tsx restricted call/copy only; frontend/src/screens/instrument/MarketCanvas.tsx optional prop/render condition only; frontend/src/lib/messages.ts one bilingual key.
- Tests: new MarketCanvas.applicability.test.tsx and new cases in owned InstrumentWorkspace.market-data-only.test.tsx. Real components except Chart output spy/HTTP boundary fixtures. No old full-suite or native/browser/server/provider rerun.
- Owned plan/iteration only; no SPY files/schema/backend/IndicatorStrip/Chart/shared-root docs/generated/static/GitHub actions.

## Steps

- [x] RED:2-observation market-data-only page lacks strategy-not-run copy and still renders misleading summary. Pin original bars/source/partial/minute/age preservation. Test all explicit market-only inputs independent of row threshold.
- [x] RED/default counterexample: showStatistics=false hides whole IndicatorStrip, while omitted/true retains original ordinary summary and0% values for the same two fixture bars.
- [x] GREEN: implement exactly approved optional prop/restricted call/message, no calculation changes.
- [x] Run only named new applicability cases and own new canvas test; ownbuild/scopedlint/diff, one bounded review. Retain RED/GREEN and before evidence SHA.
- [x] Update owned iteration and freeze commit/tree/HANDOFF, stop for unique publisher. No new actual-data window is needed for this presentation correction.

## Harness resume and result

The original session observed4expectedRED/2ordinaryPASS, then6GREEN/17existing cases skipped at07:48:41Z. The app harness update interrupted before build/lint completion was proven. ResumeACK14:38:48Z; new first-missingGREEN deadline14:53:48Z and reviewed-packet hard15:23:48Z. Existing GREEN and WIP were verified and consumed without reset or rerunning RED/tests. Old exec sessions were absent; only unfinished ownbuild/lint and diff checks were completed. R1 independent narrow reviewREADY, no Important/Critical findings. Protected math/Chart/age/SPY/backend/generated files and all4before artifacts were independently hashed unchanged. See [owned iteration](../../iterations/0038-market-data-summary-applicability.md) and output/market-data-summary-applicability/HANDOFF.json. This is offline presentation evidence; no native/browser window was reopened.
