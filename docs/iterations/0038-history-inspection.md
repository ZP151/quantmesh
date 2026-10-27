# Iteration0038 — saved historical observations (#237)

Issue: https://github.com/ZP151/quantmesh/issues/237. Plan: ../superpowers/plans/2026-10-27-history-inspection.md.

Planner: actual human approved history design SHA356ee6e720b593b93de270b9234e72a9bf3aabd7f83349127c02644b25d1f937, recorded2026-10-27 by root. One user action selects a timezone-explicit historical window, sees preceding-day saved observations or explicit unavailable, and returns to unchanged current view within two minutes. Non-goals: multi-segment display/aggregation/new strategy/data/host/trading authority. Base fetched0e01442; independent codex/history-inspection worktree; original causal output and rc1 preserved. ACK15:37:11Z, first increment17:37:11Z/reviewed slice19:37:11Z.

Quant: inspection preserves source/receipt/window/current time separately, gaps and unknown qualification. No historical clock in decisions, Paper, forecasts or fences. Synthetic acceptance does not qualify actual SPY/native market data or close #218.

Implementer: sole full-stack source writer; bounded private receipt extraction, independent readonly GET, isolated chart child. No dependencies/upstream copying; existing replay/Pydantic/FastAPI/MarketCanvas reused. Root/publisher own release; source and generated locks disjoint from parallel trend.

Verifier: backend01 RED15 failed at the missing route;02 GREEN14pass/1fixture error (strict Pydantic Python-vs-JSON reconstruction); fixture corrected without weakening product validation,03 GREEN15pass/2upstream warnings. Ruff format/check on changed Python pass. UI04 RED6fail/1pass (missing button/client) retained; UI implementation and owned desktop/390px loop/review pending. Evidence output/history-inspection. Old10tiny/436frontend/native/SDK/SPY/fullWindows not rerun.

Ruling: keep the approved spec bytes unchanged (its historical NOT_APPROVED heading describes its drafting time); this iteration/plan and actual human approval receipt grant implementation. Independent inspection response uses actual datetime.now, never the configurable instrument clock. Display staleness is explicitly two selected bar intervals and grants no trading freshness. Original _replay_series signature/response preserved; new private helper additionally returns the final selected row receipt, not generated_at/max receipt.

## Verified full local user loop — before independent review

UI06 GREEN7pass, TypeScript07 failed only on test mock typing (corrected vi.mocked),09 TypeScript PASS.08 changed frontend lint PASS.10 targeted affected UI15pass/12 non-target skipped;11 backend17pass/2upstream warnings (new15 plus two original merge/refusal checks).12 mechanical UI detector reports no findings.13 RED1 exposed the new view's no-op Volume toggle;14 GREEN8 after wiring local volume/SMA state, with no extra history read. No third-party packages installed: existing node_modules junction reuses Vite8.2.1/Vitest3.2.7; publisher must run locked versions for release. Declared versions are not falsely reported as actual local versions.

Owned normal FastAPI factory on127.0.0.1:18765 and Vite dev15173 exercised the actual page /app/instruments/hyperliquid/BTC?range=1d&mode=line. Construction-time tiny synthetic saved archive/hot, with source/limitations visibly labeled SYNTHETIC ENGINEERING FIXTURE. Actual inspection200 returned14 Oct23T23:30–23:43 bars, last receipt23:44:00.08; observed_at stayed actualOct27. No provider/real archive/SSH/native market acceptance.

Browser acceptance15:52:31.968–15:52:34.401Z: current→historical result587ms, full operation including390px screenshot and return2432ms. At390px viewport document scrollWidth375 (no overflow), historical Paper actions0. Date edit immediately clears old graph; Oct22 empty window explicitly404/unavailable; returning current leaves original URL and current requests without anchor. Desktop/mobile full screenshots and unavailable/return screenshots plus browser-acceptance.json/actual-api.json retained in output/history-inspection. This is synthetic engineering proof, not financial qualification. Vite acceptance config needed .mts for ESM and positional root/cwd; original two startup errors preserved in session history, production config untouched.

Source state ready for first whole-slice review; review/cleanup/final handoff pending. Source hooks bypassed for checkpoint after explicit targeted checks; final applicable CI remains publisher-owned.

## Independent R1 and one aggregate correction

R1 on31c199de556f982bb18b8940bcfb06f3b7cde69e:2Important/0Critical. A real in-memory DatasetManifest+HistoryService discriminator returns disjoint segments/single bars and manifest-wide coverage; parent verifies these conflict with this inspection's promised last-segment/min2 and UI returned-coverage labels. R1/report/repro including initial missing-revision fixture error retained.

18 genuine RED4 across plain/wrapped actual HistoryService and multi/single-bar windows;19 UI RED1 for wider manifest row count/extent. One aggregate correction adds inspection-only narrowing (2..10000 contiguous returned bars), preserves original manifest coverage/gap evidence and existing history responses, and derives UI returned extent/count from actual bars. No new DTO/aggregation or relaxed policy.21 GREEN19backend;22 GREEN9newUI;23 TypeScript PASS. Known test-only getByRole exact options corrected in this batch;16 prior TS error retained. Ruff/format and changed UI lint pass. Three original current Paper/token/future-quote/time-regression checks15 PASS3; they remain independent of display staleness.

Second/final independent review pending; no third structural patch cycle permitted. Final current-source browser/checkpoint and owned-service cleanup still to be recorded.

## Final R2 READY and verified source handoff

Final independent R2 on af4dd7bba9362520a29839ccdde6c338f6f5df9c/tree24eb12bb3067ee373db93ee6ea858175cad0663a: READY/0remainingImportant/0Critical. Fresh discriminator closes both R1 findings; review-r2.md and actual repro retained.24 final affected backend PASS24/2upstream warnings (19new,2originalhistory,3currentPaper/fence);25 final affected UI PASS17/12non-target skipped (9new,8selectedmarket-data-only).23 TypeScript PASS; changed Python Ruff/format, frontend lint and whitespace PASS. No old full Windows/release suite was repeated. Publisher still owns locked-runtime CI/OpenAPI/client/static generation/build/normal merge.

Restarted only the owned local synthetic backend against final sourceaf4; final-server-source.json pins actual imported file hashes and tree. Browser00:01SGT2026-10-28 corresponds16:01UTC2026-10-27. Actual final flow16:01:55.003–16:01:57.773Z: past result705ms/full historical→missing window→return plus390px capture2770ms. At390px: scrollWidth375, historical Paper actions0, sourceTimeOct23T23:43, receipt23:44:00.08, observedAtOct27T16:01:55.490001Z, returned coverage23:30–23:43. Final screenshots desktop-history-final.png/mobile-history-final.png and browser-acceptance-final.json retained. Final API200 plus synthetic archive hash+mtime unchanged verified in final-readonly-proof.json. No claim of actual canonical/native market data, finance or #218 acceptance.

Owned backend and Vite identity-checked and stopped16:02:58Z, no remaining listener on18765/15173; original synthetic files retained. Verified URL was http://127.0.0.1:15173/app/instruments/hyperliquid/BTC?range=1d&mode=line and is now stopped, not a deployed URL. Runtime/compiler startup mistakes, invalid test fixtures, all REDs and prior review remain retained; no fresh native storage/clean-close proof is inferred from synthetic cleanup.

This final checkpoint is documentation only; runtime/tests byte-identical to independently reviewedaf4. Source hooks bypassed after explicit targeted gates, as earlier checkpoints. Source writer releases to root/sole publisher with immutableHANDOFF/progress/file manifest in output/history-inspection. No README/version/locks/generated/static, real host, prefix, provider, actual archive, Goal or timer change. Original research Goal and #218 remain open; actual source qualification and future merged/native acceptance are separate.
