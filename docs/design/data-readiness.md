# Data readiness — built P1 brief

Recorded 2026-10-19 after the final bounded design review. This describes the
implemented P1 surface; `PRODUCT.md` and `DESIGN.md` remain the incumbent product
and visual references.

## Purpose and reading order

The Research navigation entry opens `/research/data-readiness` (served under
`/app` in the packaged workstation). The one user action is to import an existing
local SPY historical snapshot ZIP and inspect the evidence that qualifies or
limits its use. Source and eligibility blockers precede any trust in performance.
This surface establishes historical evidence inspection, without granting paper
or live authority, promoting a strategy, or validating investment returns.

The built story is import → qualification and allowed use → source assertions →
coverage and located checks → corporate actions → downloads and lineage → local
history. The first viewport exposes the ZIP action, historical-use boundary and,
after import, the qualification result and concrete missing evidence. Its next
action is to inspect the reasons and their located comparisons.

## Incumbent visual language

The screen extends the neutral, flat, dark Operate research console. It reuses
`Page`, owned `Button` and `Badge` primitives, the native file input, Lucide
Upload/Download/Refresh icons, definition lists, separator-led sections and a
native lineage disclosure. There are no new assets or typographic system.

`frontend/src/index.css` owns the tokens: dark `--background` is
`oklch(0.145 0 0)`, `--foreground` is `oklch(0.985 0 0)`, muted foreground is
`oklch(0.708 0 0)`, and borders use white at 10%. Geist Variable carries compact
labels and headings; evidence values, dates, codes and digests use monospace and
tabular numerals. The base radius remains `0.625rem`, applied through incumbent
control variants. Separators and spacing establish hierarchy without decorative
card stacks. Insufficiency uses neutral outline badges; rejection uses the
destructive variant. Status remains explicit in text.

Qualification and source become two columns only at the `xl` breakpoint. Facts
wrap within their columns. Coverage expands its fact grid at `lg`. The dense
checks table retains a 640 px minimum width inside a focusable, named horizontal
scroll region; its overflow stays local. Mobile history controls wrap their date
and shortened identity at full content width, becoming automatic width from
`sm`. The final 375 px viewport measured 375 px body and scroll width.

## Evidence semantics

The accepted real snapshot contains 2,965 rows, with structural `PASS` but
qualification, R1 and R2 `INSUFFICIENT`; allowed use is
`inspect_evidence_only`. Its first reason is: “Issuer-derived JSON and Yahoo
events disagree on 2021-12-17 at 0.001 USD tolerance.” The located comparison
preserves expected `1.636431` and actual `1.633`. Passing structural or normalized
issuer comparisons does not verify raw issuer lineage.

Rights, historical available-at/revision evidence, vendor daily-session semantics
and raw issuer-to-derived-JSON lineage remain unverified. Source assertions stay
beside qualification: provider/feed, receipt time, license evidence, point-in-time
status, units, session semantics and URL. Null or empty facts render “Unknown /
unavailable”; absent session lists remain unknown rather than zero. Missing
reasons or checks are explicitly reported. Nothing in this acceptance establishes
`AVAILABLE` research evidence or trading/redistribution entitlement.

English and Chinese localize interface labels, status labels and bounded action
errors through `frontend/src/lib/messages.ts`. Server reasons, check messages,
conflicts and source values remain verbatim; reason/message/conflict text also
remains in `title` metadata. The shell banner and footer identify the seeded demo
account/data as synthetic while preserving imported research source labels. “Real
snapshot” describes imported evidence provenance, not research sufficiency.

## Interaction and persistence

The ZIP picker accepts the supported `qm.spy-daily.snapshot.v1` format up to
8 MiB. Empty/oversize selections and request failures produce visible alerts;
busy operations expose status text and disable competing controls. An empty
history gives a concrete choose-and-import next step. Unconfigured storage
explains how to enable the local snapshot root and refresh.

The narrow client in `frontend/src/lib/realdata-api.ts` validates report shape
and identities. Original ZIP and pinned initial-report downloads verify SHA-256
against the selected report before saving; verification failure prevents a saved
download. Immutable lineage discloses archive/report/normalized/checker digests,
calendar identity/version, import time and member hashes/byte counts.

Displayed recency is evaluated on reopen using completed XNYS regular sessions
and a 30-minute research grace. It can differ from the immutable initial report;
it makes no real-time feed or vendor SLA claim. History persists across a cold
restart, and reopening restores qualification and blockers. Identical archive
reimport deduplicates while preserving the original receipt and pinned report.

## Recorded evidence and limits

Implementation anchors are `frontend/src/screens/DataReadiness.tsx`,
`frontend/src/lib/realdata-api.ts`, `frontend/src/lib/nav.ts` and
`frontend/src/App.tsx`. Final captures are
`output/0038-realdata-workstation-product/parent/desktop-final.png` and
`mobile-final.png`; adjacent `viewports-final.json`, `api-acceptance-final.json`,
`browser-download-verified-final.json`, `cold-reopen-final.json` and
`browser-reopen-final.json` record acceptance receipts. The independent
`output/0038-realdata-workstation-product/review-round2.md` records READY/ship
with all three material fixes resolved. Parent-recorded checks were 58 backend
tests, 65 frontend tests and the package build. This brief adds no new validation
run or claim beyond that bounded evidence.
