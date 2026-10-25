# Iteration0038 — BTC market-data-only frontend wiring

Issue[218](https://github.com/ZP151/quantmesh/issues/218); root-directed frontend part of the existing bounded-history application slice. Date2026-10-26 Singapore. Base7c49d341a40eb000ffd95cac0e4a56e06fc9d336, independent managed worktree btc-market-data-ui, branchcodex/btc-market-data-ui. Previous sample-card leaves and outputs are retained.
Plan:[BTC UI wiring](../superpowers/plans/2026-10-26-btc-market-data-ui.md). Root released the second implementation writer slot after the publisher's separate gate-fix freeze; only backend+UI write source. Actual ACK2026-10-25T16:30:26Z; first-testable target17:15:26Z, hard18:00:26Z. First24green DOM tests were reported16:39:11Z.

## Planner/Product

One action: open /app/instruments/hyperliquid/BTC?range=1d&mode=line. The operator sees the original observed chart, source/time/partial coverage and acquisition state, without unsupported research or trading controls. Source delivery succeeds when exact new-mode queries and restrictions are tested while ordinary mode remains compatible. Actual new completed-minute progress is a separate merged/native witness by the sole server owner.

The existing restrained operator UI is preserved: one chart-first column, current source/observed time facts, named native disclosure for coverage/license/limitations, and existing local chart controls. No new dashboard, sidebars of model output or paper balances. Root's final interface QM-BTC-MARKET-DATA-ONLY-v1 SHA f7278698f20f676801058395044bdea4ca7f8e4ce855d9d0c7543ccd4ce628c0 supersedes proposed62fb93de. Only explicitly true market_data_only activates restriction; both added Health fields remain optional for ordinary servers. Acquisition state/reason keys inside the supplied new view are required, with exact frozen enum/null values.

## Quant Researcher

The new source semantics are minute-end public REST snapshot observations triggered at a WS minute boundary after actual close. Interim WS candles are not archived. Provider finality, historical PIT, global sequence/manifest qualification and full24h are not established. Fixed source limitations are consumed alongside the formal history response; no frontend numerical algorithm or provider definition changes.

Running means acquisition control state only. The chart displays observed bar timestamps and age based on that timestamp, actual lineage receipt only when supplied, and separately labelled history as-of. Health receipt/polling and workspace read time cannot mint a new observation or renew its age. Stopped/capacity_stopped/failed are shown independently of the update channel and retain last observed bars; refetch failure does not replace them with mock/zero data. No quote/depth stream is present in the candle-only contract, and no executable quote is derived from candle close. No trading/Paper/source qualification is granted by this UI.

## Implementer

Owned runtime delta is only frontend/src/lib/api.ts Health, components/shell/AppShell.tsx, screens/InstrumentWorkspace.tsx and lib/messages.ts. New focused tests and owned docs accompany them. No backend, Chart/MarketCanvas/live algorithm, generated client, production static, dependency manifest or service change.

AppShell waits for health before mounting its outlet, shows a health-error boundary without mounting unrelated screens, and limits the explicit mode to the exact BTC/range1d/mode=line entry. All other route/query keys and duplicates are unavailable with a return link. Search/palette includingCtrlK, settings, reset and kill-switch mutation navigation disappear in this mode; ordinary fields-absent/false retains full navigation. Existing read-only kill-switch request is allowed by the backend contract. Mode health refreshes every5seconds to observe stop/failure; it is not a price-freshness clock.

The instrument entry also waits for health before scenario/packet queries and refuses restricted deep links directly. Its existing workspace request remains api.instrumentWorkspace('hyperliquid','BTC','1d',[]) with no horizon/forecast/packet/compare extras. The restricted render returns before decision composition or secondary consumers. A404 stays in a collecting state and never mounts the ordinary CockpitDetail fallback. Incumbent WS→SSE invalidation, completion-spaced5second reads, retained query data and MarketCanvas/InstrumentChart are reused. Chart mode/volume/SMA controls modify only component display state and cannot append forbidden URL/API parameters; range choices use existing chartFirst hiding. The page never renders the compatibility draft's account, proposal, scenario, model or decision panels.

## Reviewer

Independent readonly R1 by review_btc_market_data_ui:READY, no Important/Critical findings against the frozen interface. Reviewer checked health/deep-link gates, exact API parameters, restricted consumers, terminal acquisition/source timestamps, partial coverage and retained-bar behavior. No source edits, test reruns or provider/native checks by reviewer; second round not required. Subsequent changes only strengthened test cases and evidence; reviewed production files remain unchanged.

## Verifier

TDD evidence: workspace baseline11behavioral failures, shell baseline8failures, and original-observed-minute age RED retained under output/market-data-ui. Initial build also exposed test fixture/type mistakes (invalid invented coverage_scope, state literal widening, readonly fixture mutation and Playwright-only exact option); only the tests were corrected to the actual generated API shape. One aggregate run required awaiting TanStack notification in the stop-state assertion; no extra runtime workaround.

Final new tests:28passed/2files, including5second health refetch without child remount, fieldsabsent/false ordinary mode, pending health/unsupported symbols/parameters without packet reads,404no-fallback, stop/failure/refetch-error retention, quote absence and partial semantics, unchanged bars on identical refresh and actual supplied next timestamp entering chart data. The preceding directly affected run passed61tests(24new+37existing InstrumentWorkspace cases) on the same production code. Own-dist build/scopedoxlint/diff pass; AppShell and InstrumentWorkspace detectors both[]. Existing Vite native-loader/chunk-size warnings remain, with no broad old numerical/backend suite rerun.

These are labelled synthetic component transport fixtures with an InstrumentChart output spy. They do not prove native data, two actual completed minutes, provider finality or browser rendering at390/1440. No preview/server/browser was started, no market-data request or job/math/order/decision was issued. The responsive incumbent structure and native keyboard affordances are reused; actual phone/desktop screenshot evidence remains for root-provided exact combined source/PID/URL. Root/publisher owns combined generation, final release gates and the sole native source witness.

## Handoff and stop

output/market-data-ui/HANDOFF.json records full head/tree/base, exact file/contract/log hashes, independent review and pending native boundary. UI author stops after source freeze. Publisher alone integrates both backend/UI leaves and generates production static/client as needed; existing8880/8881/8878 instances and all previous artifacts remain untouched by this writer. Remaining acceptance must observe distinct new completed-minute timestamps in the actual merged application, not two refreshes of the same bars.
