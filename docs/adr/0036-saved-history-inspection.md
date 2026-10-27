# ADR0036 — Saved-day inspection without historical execution authority

Date2026-10-27. Status: approved scope, implementation pending independent review.
Issue237; extends ADR0034 without changing its current-window or continuity policy.

## Decision

The human approved the concrete history design SHA256
356ee6e720b593b93de270b9234e72a9bf3aabd7f83349127c02644b25d1f937.
Provide one independent readonly history-inspection GET accepting only a single
timezone-aware ISO at, fixed1d, for Hyperliquid and existing Moomoo AAPL/NVDA.
Reject future/naive/extra/duplicate inputs before storage reads. Use actual UTC
now for observed_at; never the configurable instrument/workspace/Paper clock.
The original history URL and its response are unchanged.

Reuse manifest-first HistoryService and the original bounded archive/hot replay.
A private helper returns the selected series plus its final selected row's
original receipt. Existing _replay_series remains a signature-compatible wrapper.
Manifest receipts are unknown/null rather than inferred from generated_at.
Inspection never calls join_live_tail. No STATUS/gap/resolution/identity/conflict
filter, per-store10000 tail/final10000/128-key batch/128MiB/one-thread/0spill guard
is widened. Native refusal propagates as explicit unavailable. Bounded rows are
not a claim of arbitrary-payload total RSS or production-scale success.

Inspection also narrows a successfully validated manifest series to its last
exactly contiguous segment, requiring2..10000 bars. It preserves source manifest
coverage and gap evidence in the primary object; the UI derives returned extent
and count from the actual returned bars. Original manifest history remains
unchanged, including its existing one-bar/multiple-segment response behavior.

The new immutable wrapper carries primary, observed_at, window_end, source_time,
source_received_at, stale and stale_after_seconds. Source time is the last returned
bar time; its separate receipt remains original. Staleness is display metadata:
actual observed_at minus source_time exceeds two bar intervals, with that threshold
explicit. It is not trading freshness, venue finality, qualification or a fresh
quote. The returned primary remains observed unqualified replay when manifest is
absent. Missing periods are not filled; replay returns its last eligible segment.

## UI and authority

The existing chart gains a saved-history entry. A focused child uses MarketCanvas
with separate source, window, actual viewing and receipt labels, and a historical
observation notice. It unmounts current workspace/decision consumers. Editing the
date clears the selection immediately; request keys include instrument and window,
requests have cancellation signals, and return-to-current unmounts inspection and
uses the original current request. Empty/error/invalid input never retains a prior
chart under a new date. Existing chart controls stay local and functional.

No historical anchor enters workspace, Paper, forecast, POST or fence contracts.
UI has no historical decision buttons; server-side current freshness, risk/token
and confirmation gates remain unchanged and authoritative. No API accepts a file
path or starts collection. Fixtures are selected only at service construction.

## Consequences

Users can inspect retained past observations instead of altering a clock to make
them appear current. No multi-segment DTO, aggregation engine, arbitrary resolution,
provider call, dependency, host permission or original archive mutation is needed.
This new visibility does not make Oct23 and Oct26 one continuous series, close218,
qualify financial inputs or complete the original research Goal.
Actual loopback synthetic UI proof, RED/GREEN and review are recorded in
../iterations/0038-history-inspection.md; sole publisher owns final locked-runtime
OpenAPI generation/build/CI/normal merge. Local existing frontend tools can differ
from the current lock and are reported as a limitation, never a pinned release gate.
