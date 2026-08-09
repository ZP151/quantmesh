# Iteration 0017 — Domain-Screen Translations

Status: active
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

(filled at completion)

## Checkpoints

(recorded as they land)
