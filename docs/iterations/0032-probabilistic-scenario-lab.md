# Iteration 0032 — Probabilistic Scenario Lab

- Status: implemented and verified; [PR #137](https://github.com/ZP151/quantmesh/pull/137) open for architecture integration
- Started: 2026-09-11
- Issue: [#136](https://github.com/ZP151/quantmesh/issues/136)
- Branch: `codex/0032-probabilistic-scenario-lab`
- Baseline: `origin/main@a78ff0ad6ff4c98acff3135b1acccfcd43a1a590`
- Spec: `docs/superpowers/specs/2026-09-10-probabilistic-scenario-lab-design.md`
- Plan: `docs/superpowers/plans/2026-09-10-probabilistic-scenario-lab.md`

## User loop and acceptance

Open NVDA from a ticker entry, read daily observed candles and separated 7/30-session forecast evidence, save Watch within 120 seconds, and reopen identical chart/evidence/selection. AAPL demonstrates the same demo-labelled path. Benchmark/sample/coverage/stale/binding failures block Paper with explicit reasons while Reject/Watch remain usable. Existing risk and second confirmation remain authoritative.

- [x] Chart entry from Home/Markets/Watchlist/command; large first-viewport chart.
- [x] Same exact artifact across 7/30 switching and refresh.
- [x] Honest synthetic/real/missing/stale data states.
- [x] Deterministic evidence qualification, no fabricated probabilities.
- [x] Saved chart/horizon restart replay and legacy monitoring/review compatibility.
- [x] Bilingual 390px/keyboard/reduced-motion acceptance; bounded review (PR publication below).

## Scope and verification limits

Only Moomoo AAPL/NVDA daily bars and 7/30 sessions. No new model/provider, cloud/deployment/0021/0030/0031 operational work, trusted-root writes or notifications. Preserve old artifact/packet IDs. No full pytest/domain sweep/release gate/soak; each feedback command targets <=300s and one coherent verification selection <=600s. One final Standards/Spec review and desktop/mobile UI pass, one correction and confirmation maximum. Sidecar schema/staleness is recorded only.

## 2026-09-11 — Approved kickoff

- **Planner/Product:** operator approved option A, chart-first Workspace with progressive evidence/risk, and continuous goal-driven development. One integration branch/one final reviewable PR; no extra confirmation menu is needed for the approved implementation.
- **Quant Researcher:** read-only independent investigation identified legacy forecast recomputation and packet hash compatibility as load-bearing. Strict MAE improvement must not change legacy artifact eligibility. New forecast calendar config needs its own digest/legacy validator. Residual rows overlap; bands are empirical, not calibrated profit/scenario probabilities. New selected horizon must bind scope/save/scenario/monitor/review; legacy absent selection stays 30.
- **Implementer:** current isolated worktree is exactly on latest origin/main; no inherited changes or old product branch were used. Spec and plan written and self-reviewed before product code. Shared Python and existing npm modules located; no environment install or tests yet.
- **Reviewer:** final Standards/Spec review is pending at the demonstrable slice boundary. Spec self-review found no unresolved interaction; legacy bytes, exact IDs and selected horizon are explicit acceptance gates.
- **Verifier:** Git fetch and HEAD comparison show 0/0 divergence at a78ff0a; clean worktree before documentation. No product pass is claimed. Short scoped test protocol supersedes the historical full-suite templates for this iteration.
- **Ruling:** new packets follow their chosen 7/30 horizon through scenario/monitor/review; legacy packets keep 30 — avoids silent cross-horizon interpretation — requires targeted downstream compatibility tests.
- **Ruling:** this architecture PR is reviewable output, not covered by routine non-architectural automatic merge authority — preserve a concrete final integration boundary.

## 2026-09-11 — Implementation checkpoint

- **Implementer / entry:** shared supported-ticker form and chart routes now connect Home, Markets, Watchlist and command palette. Existing exact replay links remain separate. Home's RED reproduced its former order-ticket route; final affected entry selection passed 80 tests across four files in 6.07s.
- **Implementer / backend:** optional immutable snapshot and exact horizon/artifact transport, strict confidence, version-aware XNYS freshness, and selected monitor/review interpretation implemented. Legacy packet ID fixture remains `packet-d6709c5629b810b53bd23219`. Backend final targeted selection passed 69 tests in 7.36s (two pre-existing warnings); 10-file Ruff/check-format and diff whitespace passed.
- **Implementer / calendar:** legacy artifact/report/path/OOS hashes and default generator bytes pinned. New XNYS registry reconstructs holiday/DST dates and rejects tampered paths. Scoped 650-row demo generation for AAPL/NVDA opts in. Calendar/forecast selection passed 21 tests, 21 deselected in 8.48s; four-file Ruff checks passed.
- **Implementer / chart:** actual P10/P90 polygon and split separator now use the chart's scale coordinates behind the existing adapter. Localized legends, accessible rows and attribution retained. Chart primitive/adapter selection passed 16 tests; TypeScript and scoped Oxlint passed.
- **Implementer / workspace:** chart-first daily lab consumes frozen snapshot/evidence, pins an exact artifact in the URL, keeps selected-horizon controls focused while replacing evidence, and saves Watch through the existing packet service. Saved chart renders without current workspace data. Current risk absence blocks Paper while safe saved-draft actions remain available. Eight lab tests passed in 3.74s; the 27 legacy workspace tests passed after handling exact-read errors at the route boundary. OpenAPI regenerated.
- **Quant Researcher:** additive confidence cannot relax old artifact-wide gates. Zero samples retain path provenance but show unavailable metrics and suppress forecast-derived scenario targets. New XNYS holiday freshness aligns composer and proposal checks; old weekday behavior remains explicit. ADR 0021 records these choices.
- **Verifier:** shared Python imports use the current worktree; frontend modules reused only after matching both lockfile SHA256 values. No environment installed. Checks above are development evidence; the final combined selection, packaged bundle, one desktop/mobile pass and Standards/Spec review are still pending.

## 2026-09-11 — Final acceptance and bounded correction

- **Verifier / coherent selection:** 80 Python tests passed in 32.37s (scenario lab/calendar, packet store/monitoring, four named Workspace/API authority regressions); 153 Vitest tests passed across nine affected files in 13.14s. Fourteen-file Ruff lint/format, scoped Oxlint, actual TypeScript project build and OpenAPI freshness passed. Packaged frontend rebuilt and freshness checked; Vite reports its existing >500kB shell-chunk advisory. Vendor submodule pins were inspected, not initialized or changed.
- **Verifier / real user loop:** a temporary loopback-only harness assembled real HistoryService/Lake/PriceForecastRegistry/workspace/DecisionPacket/risk/HTTP with only AAPL/NVDA synthetic history. Packaged same-origin Home ticker `nvda` → 30-session chart → Watch saved in 52.865 seconds. Packet `packet-33c4b828a752ec8107c8a699` retained forecast `forecast-d024923789736023beaf08af`; reload returned identical accessible chart row text and selected 30. Switching to 7 retained the forecast ID. Chinese command search `aapl` opened daily AAPL with its own pinned artifact. No order was created; a real Paper request returned 409.
- **Verifier / UI:** one batched desktop and 390×844 inspection plus the correction confirmation. Actual mobile content width/scrollWidth both 375px (390px viewport minus scrollbar), no document overflow; observed/forecast separator, filled band, median, candles/volume/SMA and accessible data remain visible. Keyboard entry and active horizon focus passed. Chinese copy and externalized blocker text confirmed. Bundled reduced-motion media rule was inspected; no separate OS motion emulation was available. Browser captures remain in the task record.
- **Reviewer / Standards:** one P2 found: a qualified saved draft could enable Paper with current risk unavailable. Correction requires current workspace and complete lab valuation; the strengthened test uses a qualified, paper-capable snapshot. The sole confirmation marked this resolved.
- **Reviewer / Spec:** three P2 findings: safe actions on refused pin, zero-sample metrics in expanded evidence, and blockers hidden in the risk disclosure. The correction exposes abstaining snapshots without admitting a different available artifact, masks all unevaluated horizons and externalizes Paper blockers. The sole confirmation resolved the latter two and found the refused-pin save only partially fixed: the backend staging scope still compared the refused requested ID with null valid evidence.
- **Implementer / final correction closure:** retained the requested pin as process-local staged request metadata, separate from valid packet forecast evidence; wrong pin still fails. Missing/revision/byte mismatch save regressions reproduced all three 409 failures, then passed with real packet storage and Watch children. This completed the same uncommitted correction set; no second review/audit round was commissioned. Final changed-backend selection passed 35 tests in 11.10s; corrected frontend selection passed 77 tests across five files in 12.67s. The last stage-scope change is controller-verified, not a claimed second reviewer approval.
- **Implementer / visual correction:** compact lab axis labels emphasize P50 and observed price while preserving every quantile line/table row and SMA controls; legacy charts retain original labeling. The corrected Chinese 390px AAPL/NVDA captures show the forecast band without stacked quantile labels obscuring it.
- **Verifier / detector:** the single source detector invocation on ScenarioLab and the ticker entry returned `[]`; no sidecar/document repair or second detector.
- **Scope:** no broad pytest/domain/release/soak run, new dependency environment, provider/cloud/operational change, live order or notification. The first Vite-proxy save correctly failed the origin guard; acceptance then used the packaged same-origin app. Neither proxy configuration nor origin protection was weakened.
- **Plan refinement:** acceptance lives in the lightweight `test_scenario_lab.py` real-store/API tests plus an OS-temp real-service harness, rather than duplicating it in a new acceptance module. Draft staging retains refused request context only; immutable packet evidence never claims that unavailable artifact.
- **Final HTTP closure:** restarted only the owned temporary server, then missing canonical forecast ID + selected 7-session NVDA analysis → exact save with the same refused ID → Watch replay all passed in 2.32s. Paper returned 409 and orders remained empty. Harness evidence is in OS-temp `qm0032-ui-f832b22ac2dc4f1696b22902d75cfd09/http-evidence.json`; no operator roots were used.

## Integration handoff

- PR: [#137](https://github.com/ZP151/quantmesh/pull/137), open and reviewable; closes #136 on merge.
- Product commits: `1ac8204` and `ba8eb5e`; spec/plan checkpoint `18de45f`.
- At publication GitHub's automatic `python` check was in progress on `ba8eb5e`. No manual broad CI/release/soak run or architecture merge was requested. Local bounded acceptance is recorded above; remote CI success is not claimed.
- Authorized deliverable is complete. Next action is review/integration at the architecture boundary, not an unapproved follow-on product or operational iteration.

## 2026-09-11 — Resumed PR correction

- **Planner/Product:** operator requested continued goal-driven iteration. Resume the same #136 user loop by closing observed PR #137 failures; no new product slice or architecture merge. Remote run 34504822559 stopped at npm audit, before application checks. External review 3981553959 identified a current-capability gate missing when reopening qualified saved drafts.
- **Quant Researcher:** immutable saved qualification does not establish present execution readiness. The existing workspace proposal capability includes artifact freshness/availability, quote availability, service attachment and kill switches; current valuation and saved qualification remain additional requirements. No forecasting metric, calibration or execution authority changes.
- **Implementer:** four failing saved-draft scenarios reproduced enabled Paper despite current refusal. Scenario Lab now requires current proposal permission and displays current refusal reasons in the existing risk disclosure. Reject/Watch and archived chart evidence remain usable; legacy rail behavior is retained. A positive qualified/current-ready case prevents blanket disablement.
- **Implementer / dependency handoff:** independently scoped lockfile correction updates only `@redocly/openapi-core` 1.34.19 → 1.34.20 and its exact `js-yaml` 4.3.1 → 4.3.2 dependency. This closes [GHSA-2883-xcg3-v3hh](https://github.com/advisories/GHSA-2883-xcg3-v3hh). No direct dependency, framework, override or shared installation changed. npm-added unrelated bundled metadata was excluded from the final two-node diff.
- **Reviewer:** controller checked external feedback against backend capability construction and inspected both scoped diffs. This is correction of the newly observed PR finding, not a second general Standards/Spec audit. No upstream code copied; both updated packages retain MIT licenses and the existing deterministic server/second-confirmation authority.
- **Verifier:** RED: four refusal regressions failed because Paper remained enabled; the ready positive case passed. GREEN: ScenarioLab (17), DecisionRail (22) and legacy InstrumentWorkspace (27), 66 tests passed in 8.47s. Scoped Oxlint, TypeScript project build and OpenAPI freshness passed. Lockfile audit passed with zero high vulnerabilities (three pre-existing moderate findings remain out of this correction); offline license review passed for 646 locked packages.
- **Verification boundary:** local frontend tests/code generation use the existing shared installation, whose two development packages retain their previous versions. No environment installed or shared modules mutated. Automatic PR CI must verify a fresh installation from the corrected lock; packaged build and remote outcome will be recorded below. No manual full-suite/release/soak dispatch.
- **Verifier / packaged artifact:** rebuild and independent `tools/build_frontend.py --check` passed; the existing shell chunk-size advisory remains. Diff whitespace is clean. Push this correction to PR #137 and inspect its automatic CI before claiming remote success.
- **Remote checkpoint:** correction `517702f` pushed. [Automatic CI 34604897018](https://github.com/ZP151/quantmesh/actions/runs/34604897018) passed fresh dependency install, license/audit, generated OpenAPI, frontend type/lint/tests, committed bundle freshness and Python lint; Python tests remain in progress. Recent successful main runs 34267366745, 34251838651 and 34135799652 each took about 41–42 minutes. Full remote success is not yet claimed. This documentation-only checkpoint updates the resumable frontier; inspect the latest head's automatic checks on continuation without manually dispatching additional suites.
