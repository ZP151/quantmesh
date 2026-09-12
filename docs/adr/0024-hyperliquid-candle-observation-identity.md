# ADR-0024 — Hyperliquid observation identities

- Status: accepted design; implementation/acceptance tracked in iteration 0035
- Date: 2026-09-12
- Extends: ADR-0014 and ADR-0023; preserves immutable replay conflict enforcement

## Context

The AWS collector stopped when BTC's 14:22 UTC candle volume changed from
26.45105 to 26.45336 between receipts at 14:23:00.033701 and 14:23:00.538628.
Both observations were locally marked final and shared an ID that omitted OHLCV.
LiveBuffer correctly quarantined the conflicting content and rejected admission;
the feed task terminated. A deterministic real-pump reproduction confirms this.

The [official subscription schema](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions)
contains candle open/close timestamps and OHLCV, but no immutable-final event
flag or candle event ID. The captured AWS revision establishes that elapsed
interval close cannot be interpreted as immutable contents.

## Decision

Use one deterministic identity construction for normalized WebSocket and REST
candle observations: open timestamp, coin, interval, provisional/final state,
and normalized OHLCV. Receipt time is excluded. Existing provisional construction
is preserved; closed observations gain the same content qualification. `final`
continues to mean elapsed interval close, not an upstream immutability promise.
Keep source open-time sequence, continuity gates and persistence acknowledgements.

Do not weaken LiveBuffer's explicit ID/content conflict protection. Legitimate
revisions have distinct observation IDs; equal observations deduplicate. Replay
retains every accepted revision and the chart coalesces observations by bar open.
These observations do not acquire dataset-manifest or research-quality authority.

## Upgrade and limits

Legacy rows, identities, checkpoints and quarantine remain unchanged. The first
equal-content closed observation after upgrade may append once under its new
ID; later equal new-format deliveries deduplicate. This is an identity mapping
transition, not retroactive exactly-once delivery. Reopening retained data must
accept subsequent revisions without migration or aliasing based on process memory.

REST recovery retains its current fetch window and continuity checks. This
change does not guarantee discovery of older closed-minute corrections. The
nearby older-minute cursor policy remains separate from the captured same-minute
revision failure. No grace-period heuristic, watchdog redesign, exception
swallowing, new dependency, provider expansion or execution change is included.

## Verification

Exercise the captured pair through LiveFeed.run and durable LiveBuffer, then
subsequent quotes. Verify subscriber delivery, exact-repeat deduplication,
WebSocket/REST identity parity, legacy reopen, same-minute chart coalescing and
continued quarantine of actual explicit-ID/content conflicts. Final private AWS
acceptance must witness real active-candle updates and a next-minute append.

## Extension — local-clock metrics observations

Actual deployed acceptance exposed a separate collision in `activeAssetCtx`:
the ID used millisecond-truncated local observation time, while its normalized
content digest retained microseconds. `allMids` has the same mapping. A real
normalizer/feed/buffer reproduction of the captured timestamp and metrics
produced the exact AWS conflicting identity. Identical payloads separated by
one microsecond can conflict before either row is stored in a batch.

For these two channels, derive an explicitly versioned local-observation ID
from channel, coin, full-precision UTC observation time and canonical normalized
payload. Use exactly the time and payload that enter the normalized update.
Time precision alone cannot distinguish changed content at the same clock;
payload alone cannot distinguish equal content at different microseconds.
Exchange-timed BBO, books, trades and the candle decision above are unchanged.

These feeds have local observation clocks; the new ID does not establish an
exchange event timestamp or exactly-once upstream delivery. Same full clock
and normalized payload deduplicate even with a different transport receipt;
a new observation time or changed content identifies a distinct observation.
Canonical UTC conversion prevents equivalent timezone representations from
changing identity. Quarantine still rejects an explicitly reused identity with
different content.

Legacy rows, quarantine and opaque recovery checkpoint IDs remain untouched.
A repeated legacy observation may append once with its new mapping; no data
migration, legacy ID alias or retrospective deduplication is claimed. Verify
both channels through same-batch and sequential persistence, restart replay,
exact repeats, changed payload/time and subsequent real feed-pump delivery.
The actual acceptance baseline retains all four old quarantine entries and
requires no new false identity conflict after deployment.
