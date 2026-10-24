# Durable hot admission recovery leaf

Issue218. Planner authorization: root handoff2026-10-24 after FINAL R2 STOP.
Prior sourcee47c889 and documentation98bec9e remain DO_NOT_RELEASE; their STOP
and all evidence are retained. This reduced leaf is not another old-slice round.

Goal: an unfinished admission session cannot automatically reacquire after
restart, even if both terminal writes failed and free space recovered. The same
archive/history GET remains readable. No source qualification or trading change.

ACK2026-10-24T03:29:54Z (11:29:54SGT); deadline12:59:54SGT,90minutes.
Before20minutes obtain genuine operations4 double-write/free-recovery RED;
freeze minimal implementation near60minutes, bounded independent review <=2rounds.

## Architecture / files / limits

Only live/buffer.py and live/feed.py runtime changes, corresponding tiny tests
and necessary ADR/iteration/plan records. Existing DuckDB, budget, owner-loop and
history service reused. No dependency, host, original DB, provider, Goal, real
allocation/peak proof, SPY, paid resource, new API/service/format/rotation/reset.

Before constructor DB I/O, consume the full startup intent then create+fsync an
immutable numbered session-open record bound to that intent and exact budget.
Failed marker attempts retain the charged intent. Verify previous
sessions' exact close records against consumed intents; absent/partial/foreign/
malformed closure grants no writes. Unknown legacy sessions cannot be adopted.
Any stop/storage failure poisons this session in memory before failure-prone
terminal evidence. Crash leaves the preexisting open record. Only successful
DB close after all feed-owned accepted I/O joins and no stop/failure may create
and fsync the exact close record. Failed close never earns restart authority.
Prepare/fsync a close-ready record first, then atomically publish its exclusive
hard link as closed with no fallible operation afterwards. Lost publication
after crash refuses restart; visible publication proves an actual normal close.
Successful normal restart must still reserve a full startup peak under all
original cumulative/expiry/free constraints; no intent refunds.

## Single bounded task

- [x] Real RED: operations4 startup+append consume16MB, proactive free-floor
  fails, both terminal writes fail before file creation, restore availability,
  reopen fresh instance. Actual failure at reopened.read_only in30-session-red.log.
- [x] Add RED/GREEN marker creation and fsync refusal before DB creation,
  unclean/crashed session, malformed/foreign/partial evidence, failed and normal
  clean-close, accepted pending I/O, original GET and incompatible archive404.
- [x] Implement minimal HotCacheBudget session admission/failure/close methods;
  LiveBuffer owns constructor/append/close guarding; LiveFeed owns pump lifecycle
  and releases its owner only after joined work, with failures poisoning session.
- [x] Focused tiny tests, changed Ruff/format/diff; preserve every RED/log.
- [x] One final affected compatibility boundary using original29 command's
  file set, no whole-repository/native repetition. Commit coherent checkpoint.
- [ ] Independent known-finding plus necessary whole-slice boundary inspection,
  at most2rounds; no narrow verdict misrepresented as whole READY. Exact
  head/tree/evidence once to root and sole publisher only if READY.

Final affected boundary310pass/2explicit Windows directory-fsync skips/6warnings,
46.12s; log41. Production refuses unsupported directory fsync before DB admission.
Windows protocol tests explicitly model that capability only; separate platform
tests exercise unmodeled production refusal and original archive GET200/bad404.
Native durability and actual production capacity are not established here.

## Operator boundary

No automatic reset/reopening of an unfinished session. Any controlled new
admission requires a separately verified operator budget and retained prior
accounting/evidence, not deletion/rotation within this leaf. Physical peak and
exclusive global earmark remain unproved production prerequisites. Sole host
operator can establish peak in a separately authorized finite synthetic runtime
measurement using disjoint tiny hot storage, with original DB untouched; count
all retained startup/WAL/scratch/close/metadata/failure peaks in the existing
global ledger before signing exact-runtime/batch proof. No such run authorized
or performed by this software leaf, and a tiny observation is not a hard bound.
