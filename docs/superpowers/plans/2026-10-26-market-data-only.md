# Bounded BTC market-data-only workstation plan

> Use superpowers:executing-plans and TDD; one independent bounded review at the
> demonstrable slice boundary, max two rounds. No repeated design approval.

**Goal:** Existing BTC chart shows advancing actual minute observations while
HTTP mutation/research/model/trading paths are unavailable; bounded owned cache
writes remain explicitly enabled under existing admission.

**Spec:** root-approved DESIGN.md SHA7962449c6050c14428a716bad3252a3c4a67184fd791584cebfa4eac9b1a013f
under output/btc-readonly-application-design-20261026/, plus root's explicit
default-off market_data_only/candle_only dispatch and subsequent intent-profile
constraints. Source64MiB/P4MiB/C4MiB permits at most13nonempty appends for normal
close after startup; full interim stream has no certified provider-rate bound.

**Base:** actual fetched origin/main7c49d341a40eb000ffd95cac0e4a56e06fc9d336;
codex/market-data-only in the already isolated clean worktree. Prior sample
branches/handoffs/outputs and PR227 stay untouched. ACK16:13:30Z,
interface16:28:30Z, first result17:13:30Z, hard18:13:30Z on2026-10-25 UTC.

**Architecture:** Default-off existing factory/CLI opt-in. Its early construction
path reuses base app, formal instrument/live routers, existing workspace service
and SPA serving without constructing unrelated account/decision/research/import/
model stores. Outer ASGI allowlist precedes body/handler dispatch, covers WS too.
One lifespan owns one feed task and the actual public replay_buffer handle.
Only two optional health fields in this mode; no new runtime_mode enum.

## Owned files and constraints

api/workstation.py, api/app.py, new api/market_data_only.py, live/hyperliquid.py,
new targeted tests and own iteration/plan. No frontend/static/generated/shared
root documents, PG/worker/keys/math, buffer.py or feed.py. Root rejected the
intermediate batching proposal: the final choice filters provisional WS candles
before normalization and persists post-close REST snapshot observations only.
No SDK/network/provider/host actions, new dependencies or new collector.
CLI construction must bypass account/journal/catalog/model/credential clients
before any effect. Default/ordinary --live health and subscription behavior stay.

## Single slice steps

- [x] Freeze final public interface/reason enum (INTERFACE.json at16:26:49Z).
- [x] New targeted RED: factory opt-in, HTTP/legacy/HEAD/OPTIONS/WS guards before
  receive/handler, exact BTC query allowlist, health isolation, no store setup.
- [x] Minimal helper/factory/health implementation, then GREEN targeted deltas.
- [x] New adapter RED/GREEN: default subscriptions unchanged, BTC candle-only,
  no book/trades/mids/account/recovery beyond finite1..5bars, safe error codes.
- [x] Implement root-selected post-close snapshot profile. Verify filtered interims,
  exact target windows and actual request/receipt clocks, finite reconnect and
  failed-slot attempt watermarks, same-cache persistence/close accounting. No early
  durable acknowledgement or manufactured provider finality/PIT.
- [x] Actual CLI opt-in/refusal/failed-launch cleanup tests plus only necessary
  existing default compatibility cases; targeted scoped Ruff/format/diff checks.
- [x] One independent reviewer; one aggregate correction and root-requested
  original-reviewer known-fix round2 READY (no further structural review),
  final immutable source/tree/hashes/lifecycle/interface handoff, stop.

Checks use process-local PYTHONPATH=this-worktree/src and Python313, selecting
only new market-data-only/candle-only tests and named existing compatibility
cases. Unique owned --basetemp under output/market-data-only/, preserve all logs.
Sole publisher later generates SPA/client/CI and server owner alone runs merged
native continuously advancing chart acceptance.90seconds is observational.

## Active rulings and limits

1. Root selected post-close public REST snapshots. First WS current slot starts
   the watermark without REST; advancing valid slots request one preceding full
   interval only. Interim WS frames update in-memory liveness, never durable rows.
   Reconnect requests exact1..5 completed targets; known over-limit gaps refuse
   rather than silently truncating. Failed targets are attempted once per process.
2. Source final=True is the existing completed-replay filter, annotated explicitly
   post_close_rest_snapshot with provider_finality/historical_pit unknown. It is
   not evidence of provider finality, historical PIT or research qualification.
3. Source64MiB/P4MiB/C4MiB bounds stay unchanged. Actual engineering normal-close
   example uses4 intents (startup, initial STATUS, two distinct minute data writes).
   Disconnect/error transitions consume additional budget; honest partial stop
   remains valid. No universal provider-rate or perpetual-acquisition promise.
4. Existing public REST is synchronous in the owned supervisor task. Shutdown
   joins it before cache close; it may occupy the event loop until request return.
   Existing per-phase timeout is not a proved total wall-clock shutdown bound.
5. Windows targeted tests model directory fsync only; real DuckDB, budget intents,
   COMMIT acknowledgement, API and close/cold-read execute. Native quota, provider,
   UI, licensing/PIT, out-of-sample/paper evidence and broad CI remain separate gates.
6. Root terminated Stooq cashbook qualification; no SPY research job or fixture
   substitute is introduced by this BTC engineering slice.
7. R1 identified two recovery bookkeeping defects. Five new cases failed against
   c9622c5, then passed after retaining the observed baseline across disconnects
   and screening the whole known horizon before attempted-slot suppression.
   Refused over-limit windows do not advance the attempt watermark. Ordinary
   future snapshots still run with KNOWN_GAP; no false healed cursor is created.
   Root requested original reviewer round2 on these known corrections only.
   Round2 verifies5954cd4822d8e8e541b86e55499bea829bf95798/tree
   624ec1bfd967b9ecdd764a091d854e985a20c229:both resolved; independent5PASS0.31s.
   Final source is released to sole publisher; declined native/research gates stay.
