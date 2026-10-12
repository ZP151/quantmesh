# Spec review — witness ROUND1

Reviewed `9ff1f22b...abe77d0` (three witness files), plus the current working diff fixing the native enumerator's own directory fd. Read the witness plan, relevant research-foundation specification, AGENTS/CONTEXT, profile validator, adapter/session/contracts, ADR0025 and progress ruling. No tracked edits, network/vendor/account operations or suite reruns.

## Findings

1. **P2 — Parent-side reads escape the collection deadline.** `tools/verify_server_market_source.py:703–705` (also native identity calls at714/722). The plan requires an “overall owned deadline240seconds.” Once a profile qualifies, `read_bytes()` and proc enumeration/executable hashing execute synchronously in the parent; the first deadline check happens only after they return. Trigger: the admitted configuration path is a FIFO with no writer, or an identity filesystem read stalls. Collection hangs indefinitely; the SDK child deadline cannot stop it. Reject nonregular/oversized configuration inputs and bound native/config collection as well as SDK/API work under the overall deadline. This is a static control-flow finding; no actual configuration was accessed.

2. **P2 — Stale candle receipt lineage can pass as fresh.** `tools/verify_server_market_source.py:535–558`. The plan requires “actual source clocks”; ADR0025 specifies candle freshness as `min(provider end, receipt)` and says old windows cannot rejuvenate it. The witness checks only `lineage.received_at <= app_at`, then evaluates coverage from completed canonical bar ends. Trigger reproduced offline: for every latest live-tail bar, retain progressing/matching OHLCV and sequences, set `received_at=2020-01-01T00:00:00Z`, remove `freshness_time`, and set `age_ms` consistently with the history `as_of`. The real `_application`/HistoricalSeries validation accepts these rows, and `evaluate_samples` returns `provider_application=passed`, `coverage=fresh`. Require the scoped candle freshness lineage and validate its clock ordering/coverage before assigning a fresh provider comparison. Overall status remains pending, so this does not grant operational acceptance, but its passed subgate is inaccurate.

## Scope conclusions

The self-scan fd defect is addressed by the supplied working diff (reported GREEN64 inspected). Process replacement/public/IPv6/forwarder admission remains fail-closed. The documented health/state/history-only ruling correctly leaves workspace/proposal proof unverified. Routing, PC independence, browser and recovery remain separate pending gates; blocked CLI exit2 is honestly preparation evidence. The reported focused63/related231 are software evidence, not live acceptance.

**Result:** two P2 findings; no scope expansion or request to perform forbidden account/host operations.
