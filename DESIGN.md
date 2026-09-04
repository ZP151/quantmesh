# QuantMesh Workstation Design System

## 1. Product character

QuantMesh is a local, evidence-first trading workstation rather than a
marketing dashboard. The interface should feel restrained, technical and
calm under load. It must make observed data, forecasts, synthetic fixtures,
paper authority and unavailable evidence visibly different without implying
that a model output is a fact or an order authorization.

## 2. Color and semantic states

The default palette is black, graphite and restrained green. Light mode uses
white and cool gray with dark, contrast-safe green and red. Green means a
positive or proven state only when text or shape communicates the same
meaning. Amber means degraded or stale; red means blocked, rejected or kill
switch engaged; neutral gray means unavailable. Down candles are hollow while
up candles are filled, volume is direction-neutral, and forecast quantiles use
distinct dash patterns so color is never the only signal.

## 3. Type and numbers

Geist is the interface face. Compact uppercase labels establish hierarchy;
prices, quantities, timestamps, identifiers and digests use the system
monospace stack with tabular numerals. Headings are short and functional. Provenance and risk
copy must remain readable at normal zoom and may wrap rather than truncate
material evidence such as licenses, blockers or limitations.

## 4. Layout and density

The desktop workspace is a separator-first three-column grid: market canvas,
evidence rail and decision rail. Avoid nested decorative cards. Use a 10 px
base radius only for interactive controls and status pills. At compact widths,
sections become one ordered column: context, market evidence, forecast
evidence, then paper action. No control or evidence may create horizontal
document overflow at 390 px.

Instrument Workspace is the complete DecisionPacket surface. The market canvas
shows as-of price structure and key levels; the evidence rail shows
Bull/Base/Bear scenarios, freshness, model/dataset/benchmark/cost evidence and
AI citations; the decision rail shows invalidation, entry zone, stop, target,
R multiple, proposed paper size, blockers and Reject/Watch/Paper actions. The
primary loop must not route the operator to Forecasts, Risk or Audit pages.
Details may open in-place through disclosures, drawers or linked evidence
previews while preserving ticker, time range and draft decision context.

## 5. Components and motion

Use the owned shadcn/Base UI primitives for buttons, fields and badges. Chart
library access stays behind `InstrumentChart`; API access stays outside chart
components. Range, horizon, interval and chart-mode controls expose real
pressed states. Background refresh preserves last-known evidence and focused
controls. Motion is limited to short state transitions and is disabled when
the operator requests reduced motion.

A DecisionPacket uses explicit phase labels: Draft analysis, Evidence blocked,
Ready to decide, Watching, Paper proposed, Paper confirmed and Reviewed. These
labels describe persisted workflow state, not market direction. Bull/Base/Bear
scenario emphasis never masquerades as BUY/SELL authority. When AI is absent,
loading or invalid, deterministic analysis remains in place and the AI panel
shows a neutral unavailable/degraded state with no layout collapse.

## 6. Accessibility and evidence rules

Every action is keyboard reachable with a visible focus indicator. The market
chart has a complete screen-reader table for observed OHLCV plus comparison,
indicator and forecast series. Light and dark palettes meet text and graphical
contrast requirements. Localized known evidence is paired with the original
server text in `title` metadata; unknown evidence remains verbatim. Forecasts
always expose vintage, dataset/model identity, uncertainty, benchmark and
limitations. Paper proposals require an explicit second confirmation, and
terminal success or refusal remains visible until the operator dismisses it
or authoritative reset removes it.

Evidence blockers are placed immediately above the action controls and identify
the failing freshness, quality, leakage or lineage condition in text. Reject
and Watch remain available when Paper proposal is blocked. Every saved action
exposes its DecisionPacket identity and provides an in-workspace replay path to
the evidence, risk decision, paper result and review that it references.
