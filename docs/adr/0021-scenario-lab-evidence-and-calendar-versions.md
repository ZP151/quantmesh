# ADR 0021 — Scenario Lab evidence and calendar versions

- Status: accepted for implementation; architecture PR awaits operator integration
- Date: 2026-09-11
- Issue: #136
- Extends: ADR 0019 (packet identity), ADR 0020 (data-plane boundary)

## Context

The chart-first 7/30-session analysis must replay its observed bars, forecast and horizon after current market data changes. Existing packets omit chart snapshots and their canonical IDs must remain valid. Existing forecast artifacts recompute paths during validation using a weekday calendar, so changing the calendar in place would invalidate saved research.

## Decision

Add an optional versioned `scenario_lab` packet extension containing bounded daily history, selected horizon, qualification policy, confidence and reasons. Omit the extension entirely when absent. Include it in new canonical identities, root scope and immutable child evidence. Reuse existing forecast paths, metrics and provenance in DecisionEvidence. New selected horizons drive scenario targets, monitoring drift and outcome paths; absent legacy selection retains 30 sessions.

Resolve a URL-selected forecast ID through the exact registry and verify its dataset/revision/manifest/quality, as-of cut and chart bytes. Failure produces abstention and blocks Paper without substituting the latest artifact. Archive rendering uses only packet snapshots and does not depend on a current workspace request. Changing a saved horizon starts a fresh analysis of the same artifact. New analysis is explicit.

Add an admitted XNYS configuration digest backed by the existing pinned CalendarService, regular sessions and daily New York midnight timestamps. Dispatch recomputation and freshness by admitted configuration, preserving the legacy algorithm, bytes and IDs. Only the scoped AAPL/NVDA demo generator opts in. No provider or data-plane ownership changes.

Freshness dispatch also follows that admitted forecast configuration when a caller uses the legacy request shape without a selected horizon. Request shape controls the packet extension, not the time grid of a newly generated artifact; otherwise valid Friday daily bars would be rejected over weekends. Old forecast configurations retain their original elapsed-time composition rule.

Qualification is deterministic research evidence, never a probability: require at least 30 resolved residual rows and 30 evaluated intervals, strict MAE improvement over last-price random walk, valid chronology/binding and the existing coverage gate. Artifact-wide blockers remain additional constraints. Zero-sample metrics display unavailable. Overlapping residual rows and intermediate square-root band scaling remain disclosed limitations. Reuse existing risk, action freshness and second confirmation; safe Watch/Reject remain possible when Paper is blocked.

The chart uses an owned Lightweight Charts primitive for the empirical P10/P90 fill and observed/forecast separator. It uses actual scale coordinates and lifecycle detach, retaining quantile lines, accessible data and attribution. Evidence and risk are disclosures below the full-width canvas in the established workstation design system.

## Consequences and evidence

New packets are larger by a bounded historical snapshot; compatibility requires no migration. Two horizon analyses can coexist at one as-of. Existing artifacts remain valid; unrecognized configurations fail closed. The frontend uses explicit fresh-analysis URLs and caches a selected immutable artifact instead of periodic replacement. Other venues and legacy 126-session analysis remain on the existing workspace.

Tests pin legacy packet/artifact hashes, exercise registry and packet-store reconstruction, reject mutated lineage/bytes/selection and forecast dates, verify XNYS holidays/DST and downstream 7/30 versus legacy 30. Chart tests cover actual polygon geometry and lifecycle. The iteration ledger records runtime, browser and review evidence and its bounded scope.
