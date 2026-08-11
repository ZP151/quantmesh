# Iteration 0018 — Global Localization Completion

Status: completed (PR #100 squash-merged at `5069d1b`; replacement release
candidate and final acceptance continued through iterations 0019 and release)
Started: 2026-08-10
Baseline: `origin/main` / `v0.1.0-rc6` (`7ceba59`)
Branch: `0018-global-localization`

## Finding

The operator screenshot at `http://127.0.0.1:8766/app/markets` was truthful
for the station that was running, but it was not the current source tree. The
station reported package version `0.1.0rc6` and served the pre-0017 bundle
`index-B_zBIo_l.js`. RC6's acceptance checklist explicitly said domain pages
such as Markets remained on the English fallback. The current `origin/main`
already contains PR #99 / iteration 0017, where Markets and eleven other
scoped screens were translated.

The remaining product gap was real as well: Prediction, Kill switch,
Enablement, NotFound, Loading and several shell accessibility/tool-tip strings
were still hardcoded in English. Therefore replacing the stale station alone
would not satisfy a truly global language setting.

## Delivered in this slice

- Extended the shared `messages.ts` dictionary to Prediction markets,
  Prediction error/empty states, Kill switch, Enablement, shared Loading and
  NotFound surfaces.
- Localized mobile navigation labels, command-palette access labels, demo
  provenance tooltip/badge and loopback footer copy.
- Kept API-facing values and safety-critical server verdicts raw where their
  identity matters; localized their surrounding labels and controls.
- Rebuilt the package-served SPA bundle. A source-tree demo station on port
  `8768` now serves the new bundle `index-DmG9NXTb.js`; the old RC6 station on
  `8766` remains untouched and immutable for historical acceptance evidence.

## Verification

- Message-table parity and placeholder coverage: passed.
- Frontend Vitest: 58/58 passed, including the zh-CN Prediction smoke test.
- SPA browser E2E: 5/5 passed with a clean repository-local basetemp.
- TypeScript/Vite build: passed.
- `npm run lint`: passed with the repository's existing Fast Refresh warnings.
- `python tools/build_frontend.py --check`: passed.
- Existing backend/workstation code is unchanged; no order, risk, connector,
  market-data or AI authority semantics changed.

## Acceptance criteria

- [x] Stored `zh-CN` preference renders Markets and the previously scoped
  domain screens in Chinese.
- [x] Stored `zh-CN` preference renders Prediction, Kill switch and
  Enablement controls in Chinese.
- [x] Loading, NotFound, mobile navigation and shell provenance copy follow
  the selected locale.
- [x] English remains the byte-stable fallback.
- [x] RC6 is not rewritten or silently replaced.
- [x] Merge the integration PR; PR #100 squash-merged at `5069d1b`.
- [x] Run the later tagged-tree release gate and operator acceptance checklist;
  the accepted combined tree was promoted to `v0.1.0` at `5a7f660`.

## Release handoff

The currently running `8766` station must not be used to verify this fix. After
the integration PR is green, publish the next replacement candidate (RC7 or
the repository's next assigned candidate), regenerate the isolated acceptance
environment, and verify locale switching on every SPA route before asking for
operator sign-off. Formal `v0.1.0` promotion remains a separate explicit gate.

## Safety

All external venues remain read-only; no credentials, wallet signing, mainnet
orders, real-money trading or autonomous AI execution are introduced.
