# Iteration 0033 — Exact Forecast Outcome Scorecard

- Status: completed and merged through [PR #139](https://github.com/ZP151/quantmesh/pull/139) at `6ea9a13`; AWS deployment not updated by this merge
- Started: 2026-09-12
- Issue: [#138](https://github.com/ZP151/quantmesh/issues/138)
- Branch: `codex/0033-forecast-outcome-scorecard`
- Baseline: `origin/main@13743eabf4784603ed43300fd252a6c374cf5d41`
- Spec: `docs/superpowers/specs/2026-09-12-forecast-outcome-scorecard-design.md`
- Plan: `docs/superpowers/plans/2026-09-12-forecast-outcome-scorecard.md`

## User loop

Open a saved AAPL/NVDA action's review, compare frozen 7/30-session forecast
with exact actual daily closes, save a classification/note and reopen the same
review in <=120 seconds. Incomplete paths never receive complete-path scores.
Legacy selected horizon stays 30. Existing risk and confirmation are unchanged.

## 2026-09-12 — Kickoff

- **Planner/Product:** operator authorized #137 merge and the next important
  planned feature. #137 is merged at 13743ea. M14 calls for a learning loop;
  review exposes thresholds/R but no forecast-versus-actual view. Reuse that
  exact immutable evidence; no framework or data expansion.
- **Quant Researcher:** independent investigation confirmed the missing loop.
  Exact timestamps and saved outcome win; path points are correlated, not
  independent samples. Inclusive interval hit count is descriptive only;
  MAE is price error, not cost-adjusted performance. Incomplete scores remain
  null. Last-price baseline uses the saved close on the same target timestamps.
- **Implementer:** fresh branch from origin/main in the existing isolated
  worktree. Backend projection and frontend have disjoint ownership. Reuse
  existing review API/store and chart adapter; no dependency install or upstream
  copying. Plan self-reviewed before code.
- **Reviewer:** independent Standards/Spec review reserved for demonstrable slice.
- **Verifier:** merge and clean branch baseline checked; product checks pending.

## Scope limits

No provider, operational maintenance, cloud, new model/dependency, notifications,
order lifecycle or live execution. No persisted contract/ID migration. Each
command <=300s and coherent local targets <=600s; no full local pytest/domain,
release or soak. One final review and one batched desktop/mobile inspection,
at most one correction/confirmation.

## 2026-09-12 — Delivered user loop and verification

- **Implementer / backend:** `exact-close-v1` is a pure response projection.
  Computed `forecast_comparison` selects saved review outcome first; all original
  packet/outcome/review payloads retain their bytes and identities. Exact
  timestamps join to optional closes; complete paths alone receive MAE, fixed
  last-price benchmark MAE, inclusive interval hit count/fraction and signed
  terminal error. Ten RED tests failed on the missing module/property, then
  passed; agent's final backend selection passed 34 tests in 12.83s.
- **Implementer / interface:** added frozen forecast/actual plot, descriptive
  metrics and dated/provenance disclosure to the existing review panel. Separate
  actual-series segments never bridge a missing session; point markers expose
  singleton observations. The chart adapter consumes only instrument/range/bars,
  avoiding fabricated series provenance. Existing review save uses exact IDs.
  Initial chart-marker RED and absent-component RED were observed; 24 component
  tests passed after implementation.
- **Verifier / controller:** 77 Python tests passed in 17.65s across forecast
  outcomes, scenario lab, decision packets and monitoring (two existing warnings).
  105 frontend tests passed across seven affected files in 10.98s. Actual tsc -b,
  scoped Oxlint, three-file Ruff lint/format, generated OpenAPI freshness, packaged
  build/freshness and diff whitespace passed. An initial API generation omitted
  current-worktree PYTHONPATH and read the shared editable checkout; type checking
  caught it, and regeneration with explicit worktree imports corrected it.
- **Reviewer:** one independent Standards review and one independent Spec review
  found no actionable issues against baseline 13743ea. No unverified agent test
  report substitutes for controller commands above.
- **Verifier / browser:** real same-origin packaged UI at temporary loopback
  station with real registry, packet/review stores and service API; synthetic
  history supplied by a bounded local fixture adapter. Complete NVDA 7-session
  review saved as `review-13fdb6c6dd96888775ef061e` in 58.780s from opening the
  review disclosure. Corrected Chinese 30-session page reload → inspect dated
  rows → classification/note → saved review took 16.658s. The partial7 case
  showed unavailable aggregate scores. No order was placed; kill switch stayed on.
- **Verifier / frozen replay:** replaced only temporary outcome history with an
  empty series and reconstructed the review store. Current preview changed to
  `outcome-7746fa7bcc7dee212e3a6cc2`, while saved comparison remained byte-equal
  to `outcome-0c46a70d7617a5d154be3f5a`, complete with 7 observations. Browser
  reopened the frozen chart/count after this change. Proof remains in OS-temp
  `qm0033-ui-lvhx0otwrzr/replay-proof.json`; no operator roots were touched.
- **UI correction batch:** browser found unexpanded count placeholders and the
  historical hardcoded 30-session label on selected7; initial loading also briefly
  showed failure because both context keys were null. Four RED component tests
  reproduced these. Double-brace interpolation, neutral horizon-target copy and
  a non-null failed-context guard fixed them; 50 affected frontend tests passed
  in 3.30s. The sole Spec confirmation accepted all three fixes with no findings.
- **UI acceptance:** one desktop/390px EN/zh inspection and the correction
  confirmation. Chinese document client/scroll width both 375px; open row table
  scrolls locally (319px viewport, 534px content) without document overflow.
  Keyboard Enter opens details. Plot/metrics/counts and frozen status inspected;
  browser error log empty. Single mechanical detector returned `[]`. Viewport
  override reset, temporary tab and owned server closed; no sidecar repair.
- **Limits:** no new dependency/model/provider, live action, notification,
  cloud/maintenance work, local full suite/release/soak or environment install.
  Existing >500kB shell bundle advisory remains. GitHub main post-merge run
  34625627187 was still running at the local acceptance checkpoint.

## Operator acceptance

Open a saved AAPL/NVDA action in Instrument Workspace → Monitoring & review →
Forecast vs actual. Inspect selected session count, exact dated closes and
descriptive errors. Save the existing review classification/note and reopen;
the frozen comparison must not follow current prices. Partial/pending results
must keep aggregate scores unavailable and must not enable a stronger review
classification than the existing service allows.

中文：打开已保存的决策 →「监控与复盘」→「预测与实际对照」。检查交易日数、
逐日价格和误差，保存分类与备注后重新打开。已保存曲线不应随最新行情变化；
缺失或未完成周期的汇总评分保持不可用。默认模拟模式与二次确认不变。

## Publication checkpoint

Implementation `bb4d978` is pushed and published in non-draft PR #139, closing
issue #138 on integration. This final documentation checkpoint records the
reviewable deliverable; automatic final-head CI is pending, not claimed green.
Next resume inspects that exact head and any review feedback before routine
squash integration. #137 was already merged under explicit operator authority.

## 2026-09-12 — Integration closeout

- **Verifier:** final-head `090d85d100622cc1c250a6becc6f3e9687b235bd`
  [CI run 34628077408](https://github.com/ZP151/quantmesh/actions/runs/34628077408)
  succeeded: 3321 Python passed, 55 skipped, 9 warnings (2981.76s), and 325
  frontend passed. This supersedes the pending publication checkpoint above.
- **Reviewer:** the sole remote comment concerned the stale ACTIVE frontier;
  final-head documentation already corrected it. The resolved thread was
  closed after verification. No outstanding review request blocked integration.
- **Integrator:** PR #139 squash-merged at 2026-09-12 06:26:29 UTC as
  `6ea9a1305b2b3eea28795ccb0059d6ebba82b769`; issue #138 is closed.
- **Product handoff:** implementation/review/CI/integration are complete. AWS
  deployment and real-provider acceptance are separate, unclaimed outcomes.
  The operator's observed data gap is prioritized in iteration 0034 / #140.
