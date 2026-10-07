# ADR 0025 — Private Moomoo observed minute replay

Status: accepted for iteration 0037 / issue #156, 2026-10-08.

## Decision

Use the admitted quote-only SDK boundary's subscribed `get_cur_kline` for
US.AAPL and US.NVDA only: K_1M, AuType.NONE, explicit regular session and at
most 390 rows. Keep daily and historical adapters unchanged. Current-minute
observations on September 23 and October 8 Singapore support end-labelled
Eastern minutes; preserve the raw label and UTC end, and map the canonical UTC
start to end minus one minute. This empirical rule is limited to this surface,
not a claim about every vendor interval or market. Validate OHLCV, ordering and
the pinned XNYS schedule including holidays, DST and early closes.

Polls admit only a changed latest minute or subsequent intervals after the
initial bounded window. Unchanged cached reads do not produce events.
Last-source fingerprints survive transient disconnects; the existing status
barrier breaks continuity without replaying an unchanged provider window.
This deduplication lasts for the supervisor's lifetime, not across process restarts.
Older late corrections do not rewind the current stream; full historical correction
ingestion remains a separate qualified-history capability. Sequences describe
local observation order and are explicitly labelled as such. Exact interval
adjacency proves a displayed segment; missing minutes, disconnects and session
boundaries reset it without inventing bars or exchange sequence continuity.

Scoped Moomoo 1m candle freshness uses min(provider end, receipt), validated against the
canonical start. Receiving a closed or cached old window cannot rejuvenate it.
The optional live-tail lineage records this clock and raw vendor labels; other
venues and existing nonminute Moomoo intervals retain their receipt-based candle rules. History uses the
bounded AAPL/NVDA 1D 5m->1m replay exception with exact observed coverage, XNYS,
unadjusted prices and `moomoo-private-market-data` license. This coverage is not
a public redistributable dataset or qualified forecast training history.

Show metrics.last when no QUOTE exists, with source clock/age and degraded,
non-executable evidence. QUOTE-or-METRICS and the request clock are detached
under the same feed lock, before account/history work or another ingest.
Bid/ask depth remains absent and the existing paper
confirmation and live execution fences remain closed. Fresh data with depth
limitations is not labelled stale merely because execution is blocked.

The setting defaults off (moomoo_candle_num=0); the reviewed private AAPL/NVDA
deployment profile enables 390. Preserve the exact previous profile for
retained-release activation/rollback. Other configured symbols continue their
existing quote/ticker polling without calling the scoped minute interface.

## Acceptance and limits

Local real OpenD/replay evidence spans two minute boundaries and checks OHLCV
against source rows. Final release still needs complete CI, reviewed merge,
precise private deployment and four actual Markets/Watchlist chart entry paths,
minute revisions/appends, reload retention and crypto regression. Windows
OpenD/SSH persistence and the capacity/shutdown observation remain subsequent
operational tasks. No credentials, order calls, paid rights or public ingress
are added.
