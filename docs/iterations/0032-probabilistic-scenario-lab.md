# Iteration 0032 — Probabilistic Scenario Lab

- Status: active; approved design and implementation planning
- Started: 2026-09-11
- Issue: [#136](https://github.com/ZP151/quantmesh/issues/136)
- Branch: `codex/0032-probabilistic-scenario-lab`
- Baseline: `origin/main@a78ff0ad6ff4c98acff3135b1acccfcd43a1a590`
- Spec: `docs/superpowers/specs/2026-09-10-probabilistic-scenario-lab-design.md`
- Plan: `docs/superpowers/plans/2026-09-10-probabilistic-scenario-lab.md`

## User loop and acceptance

Open NVDA from a ticker entry, read daily observed candles and separated 7/30-session forecast evidence, save Watch within 120 seconds, and reopen identical chart/evidence/selection. AAPL demonstrates the same demo-labelled path. Benchmark/sample/coverage/stale/binding failures block Paper with explicit reasons while Reject/Watch remain usable. Existing risk and second confirmation remain authoritative.

- [ ] Chart entry from Home/Markets/Watchlist/command; large first-viewport chart.
- [ ] Same exact artifact across 7/30 switching and refresh.
- [ ] Honest synthetic/real/missing/stale data states.
- [ ] Deterministic evidence qualification, no fabricated probabilities.
- [ ] Saved chart/horizon restart replay and legacy monitoring/review compatibility.
- [ ] Bilingual 390px/keyboard/reduced-motion acceptance; bounded review/PR.

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
