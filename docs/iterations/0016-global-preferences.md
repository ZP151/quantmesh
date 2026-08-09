# Iteration 0016 — Global Preferences and Workstation Continuity

Status: active
Started: 2026-08-10
Baseline: `origin/main` / `v0.1.0-rc5` (`cc8bde8`)
Branch: `0016-global-preferences`

## Outcome

Give the local QuantMesh workstation a persistent global language and UI theme
layer without changing market-data, paper-trading, connector, risk or order
semantics. English remains the primary product language and Simplified Chinese
is the companion locale. The preference boundary is local to the browser and
must never be sent to a venue or broker.

## Delivered in this slice

- Added a `PreferencesProvider` with `en` / `zh-CN` locale support.
- Added `system` / `light` / `dark` theme modes with system-theme updates.
- Persisted preferences under `quantmesh.preferences` in browser local storage.
- Added an early inline theme bootstrap in `index.html` to reduce first-paint
  theme flash, and synchronized the document `lang` and `color-scheme`.
- Localized the global shell, navigation groups, navigation items, session
  banners, footer, kill-switch/reset controls and command palette.
- Added a responsive Settings route and navigation entry using existing
  shadcn-style tokens and native accessible selects.
- Kept domain-screen copy on the English fallback until each market/research/
  trading surface receives a reviewed translation dictionary; this avoids
  silently translating financial terminology inconsistently.
- Rebuilt the packaged FastAPI SPA bundle.

## Verification evidence

- Frontend Vitest baseline: 48/48 existing tests passed.
- New preference/settings tests: 4/4 passed.
- TypeScript/Vite production build: passed.
- `npm run lint`: passed with the repository's existing Fast Refresh warnings;
  the new provider adds the same known warning because it exports both a
  provider and hook.
- `python tools/build_frontend.py --check`: passed after rebuilding.
- Browser persistence is local-only; no API or connector code was changed.
- Build environment warning: local Node is `22.11.0`; Vite recommends
  `22.12+`. Upgrade the workstation runtime before the next clean release
  gate, but this did not prevent the current build or tests.

## Acceptance checklist

- [x] Fresh browser defaults to English and dark workstation styling.
- [x] Language changes update shell/navigation/settings without a reload.
- [x] Theme changes update the document class, metadata and persisted state.
- [x] System theme changes are observed when `system` is selected.
- [x] Reload restores locale and theme from local storage.
- [x] Settings remains usable at compact widths and with keyboard focus.
- [x] Demo/live safety boundaries and order authority are unchanged.
- [ ] Run the full release gate from a clean checkout after integration.
- [ ] Operator acceptance of the resulting RC.

## Checkpoint H1 — integration and the rc6 cycle (2026-08-10)

- PR #97 (the preference slice above) went through CI green, was reviewed
  (type-safe i18n, local-only persistence, anti-flash bootstrap, accessible
  Settings, safety copy preserved verbatim) and squash-merged at
  `3514c18`. `v0.1.0-rc5` stays immutable; the merged tree changes the
  packaged SPA, so the next candidate is cut from `origin/main`.
- rc5 tagged-tree gate: run 4 on the exact `v0.1.0-rc5` tree
  (`cc8bde8`) **FAILED 15/15 on a timing flake** — 13 steps PASS, then
  pytest FAIL at 892.2 s with 2 failed / 2114 passed: both failures
  were live-E2E 30 s locator timeouts for the "Real" freshness badge at
  port 8645, because the venue's ~40 s freshness window was consumed by
  module setup under full-suite load. A standalone re-run on the
  identical tree passed 5/5, ruling out a product defect. The fix
  (20-min keep-alive window + test-triggered quiet event) lands in this
  branch; full diagnosis in iteration 0015 Checkpoint H3. rc5 stays
  immutable.
- rc6 cycle (this branch): version metadata/tests pinned `0.1.0rc6`,
  release notes (EN + zh-CN) written, then branch-head gate, one PR, tag
  `v0.1.0-rc6`, tagged-tree gate, isolated acceptance environment
  regeneration (superseding the rc4 build) and the operator checklist.

## Next slices

1. Add reviewed translation dictionaries for the highest-value domain screens:
   Overview, Live Cockpit, Markets, Forecasts, Orders and Risk.
2. Add browser-level acceptance for locale persistence, theme persistence,
   system-theme switching, keyboard navigation and 390 px layout.
3. Add a compact chart/data-density pass for the live cockpit, with explicit
   stale/degraded/source labels preserved in both locales.
4. Continue the real-time data prototype: Hyperliquid read-only ticks/books,
   Polymarket/Kalshi event probabilities, Moomoo OpenD when available, replay
   lake persistence and unified freshness/sequence contracts.
5. Keep AI advisory-only: local analysis may summarize, compare and challenge
   signals, but the paper kernel remains the only order authority.

## Role handoff

- Planner/Tech Lead: keep the preference layer frontend-only and avoid a
  backend schema migration for browser presentation settings.
- Implementer: finish localization slices and visual polish on the existing
  token system; reuse existing UI primitives.
- Reviewer: check terminology, accessibility, responsive behavior and that
  no translation weakens provenance, stale-data or paper-safety copy.
- Verifier: run Vitest, build, bundle freshness, browser checks and the clean
  release gate from a fresh checkout.

## Safety

All external venues remain read-only; no credentials, wallet signing, mainnet
orders, real-money trading or autonomous AI execution are introduced by this
iteration. Demo and live data remain labeled and isolated.
