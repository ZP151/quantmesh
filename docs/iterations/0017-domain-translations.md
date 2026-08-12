# Iteration 0017 — Domain-Screen Translations

Status: completed (PR #99 squash-merged; verification recorded below)
Started: 2026-08-10
Baseline: `origin/main` / `v0.1.0-rc6` (`f97f04b`)
Branch: `0017-translations`

## Outcome

Extend the reviewed English / 简体中文 preference layer (iteration 0016)
to the domain screens so the workstation is fully usable in Chinese
without weakening any financial, provenance, stale-data, degraded-state
or safety wording. English remains the primary product language; the
Chinese dictionary is hand-reviewed per term, never machine-translated
inconsistently. Screens without a dictionary stay on the reviewed
English fallback.

## Scope (roadmap vertical slice 1)

Target screens with dictionaries (keys `screen.*`):
Overview, Live Cockpit (watchlist + instrument detail + freshness
labels), Markets, Watchlist, Forecasts (Research), Orders, Positions,
P&L (Trading), Risk, Connectors, Imports, Audit.

Explicitly out of scope for this slice (remain on the reviewed English
fallback, documented): Prediction markets comparison, Ops (kill switch /
enablement), legacy Jinja pages. The kill-switch screen stays on the
reviewed English fallback rather than being translated before its
safety-critical copy receives an explicit review.

## Constraints

- `MessageKey` stays `as const`-keyed; a missing zh-CN key is a TS
  error (never a runtime blank).
- Session banners, provenance lines, freshness/degraded badges and
  paper-safety statements are byte-exact in both locales.
- Financial terms keep their established zh-CN rendering from the
  shell/nav dictionary (订单/持仓/盈亏/风险/熔断开关/模拟下单/数据导入/
  审计/连接器/自选).
- Freshness labels (Real/Stale/Delayed/Synthetic/Unavailable) live in
  the message table so both locales render them; the underlying
  `LiveLabel` keys are unchanged (API-facing, never localized).

## Verification evidence

In-tree regression (branch head `c913df0`, 2026-08-10):

- `tsc -b` clean; `oxlint` exit 0 (4 pre-existing react(only-export-
  components) warnings in button/state/badge/preferences, unchanged).
- `vitest run` — 10 files, 57 tests passed, including the new
  `messages.test.ts` (en/zh-CN key parity, placeholder parity, no empty
  translations) and `Locale.test.tsx` (Overview renders English by
  default; renders 现金/权益/已解除/总览 under a stored zh-CN
  preference).
- `vite build` clean; committed SPA bundle rebuilt via
  `tools/build_frontend.py` (package-served, no node at serve time).
- `ruff check src tests tools` clean.
- Full backend `pytest -q` — 2116 passed in 786.9 s (includes the
  workstation/SPA/live Playwright E2E suites; 1 pre-existing
  StarletteDeprecationWarning).

Clean-checkout release gate on branch head `c913df0` — **15/15 PASS**:
version consistency, fresh venv + `.[dev,research,e2e]`, ruff, license
review, pip-audit, `npm ci`, bundle-freshness check, vitest, full pytest
(683.5 s), golden path, clean-checkout proof; clone clean at end.

CI on the integration PR (#99): `python` check pass (2 m 32 s).

## Checkpoints

- **Batch 1** (`35b9490`): message tables split out of preferences.tsx
  into `lib/messages.ts` (`MessageKey` re-exported); surface error/empty
  state extraction (`surface.unavailable/empty/emptyDetail/helper`);
  Overview/Markets/Watchlist screens wired. En strings byte-identical.
- **Batch 2** (`7860f44`): Trading (Orders/Positions/P&L), Order form,
  Risk wired — order status/side/alert kinds stay raw, paper-safety and
  kill-switch wording byte-exact.
- **Batch 3** (`db39d15`): Research (Experiments/Promotions/Forecasts
  incl. the ReportCard calibration wording), Connectors (kind keys,
  probe, public-fetch provenance), Imports (test expectations preserved
  byte-identical), Audit (mapping/decision summaries).
- **Batch 4** (`b9bcb80`): live freshness labels via
  `LABEL_TEXT: Record<LiveLabel, MessageKey>` (LiveLabel identity stays
  raw on the wire); Cockpit watchlist + instrument detail wired;
  Prediction screen badge protected from key regression (screen itself
  remains out of extraction scope).
- **Batch 5** (`fb51dd5`, `c913df0`): locale coverage tests + zh-CN
  render smoke; rebuilt committed SPA bundle.
- **Close-out**: in-tree regression green (57 vitest / 2116 pytest /
  tsc / oxlint / ruff / build), clean-checkout release gate 15/15 on
  the branch head, CI green, PR #99 squash-merged.

## Outcome

Iteration 0017 (roadmap vertical slice 1) complete: all 12 scoped
domain screens render from the reviewed en/zh-CN message table, every
English string byte-identical to before, zh-CN fully hand-reviewed, and
the locale contract is now pinned by both compile-time (`MessageKey`)
and runtime (coverage) tests. No version bump, no new RC — `v0.1.0-rc6`
remains the current immutable candidate and promotion to `v0.1.0` is
still gated on the recorded operator verdict.
