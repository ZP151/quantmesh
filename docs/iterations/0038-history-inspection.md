# Iteration0038 — saved historical observations (#237)

Issue: https://github.com/ZP151/quantmesh/issues/237. Plan: ../superpowers/plans/2026-10-27-history-inspection.md.

Planner: actual human approved history design SHA356ee6e720b593b93de270b9234e72a9bf3aabd7f83349127c02644b25d1f937, recorded2026-10-27 by root. One user action selects a timezone-explicit historical window, sees preceding-day saved observations or explicit unavailable, and returns to unchanged current view within two minutes. Non-goals: multi-segment display/aggregation/new strategy/data/host/trading authority. Base fetched0e01442; independent codex/history-inspection worktree; original causal output and rc1 preserved. ACK15:37:11Z, first increment17:37:11Z/reviewed slice19:37:11Z.

Quant: inspection preserves source/receipt/window/current time separately, gaps and unknown qualification. No historical clock in decisions, Paper, forecasts or fences. Synthetic acceptance does not qualify actual SPY/native market data or close #218.

Implementer: sole full-stack source writer; bounded private receipt extraction, independent readonly GET, isolated chart child. No dependencies/upstream copying; existing replay/Pydantic/FastAPI/MarketCanvas reused. Root/publisher own release; source and generated locks disjoint from parallel trend.

Verifier: backend01 RED15 failed at the missing route;02 GREEN14pass/1fixture error (strict Pydantic Python-vs-JSON reconstruction); fixture corrected without weakening product validation,03 GREEN15pass/2upstream warnings. Ruff format/check on changed Python pass. UI04 RED6fail/1pass (missing button/client) retained; UI implementation and owned desktop/390px loop/review pending. Evidence output/history-inspection. Old10tiny/436frontend/native/SDK/SPY/fullWindows not rerun.

Ruling: keep the approved spec bytes unchanged (its historical NOT_APPROVED heading describes its drafting time); this iteration/plan and actual human approval receipt grant implementation. Independent inspection response uses actual datetime.now, never the configurable instrument clock. Display staleness is explicitly two selected bar intervals and grants no trading freshness. Original _replay_series signature/response preserved; new private helper additionally returns the final selected row receipt, not generated_at/max receipt.
