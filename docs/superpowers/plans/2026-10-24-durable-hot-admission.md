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

Only live/buffer.py and live/feed.py runtime changes initially. Planner's R1
boundary ruling additionally authorizes the minimal existing live_history.py
replay-error adapter, within original B's five-file pool; no other wiring was
needed. Corresponding tiny tests and necessary ADR/iteration/plan records.
Existing DuckDB, budget, owner-loop and
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
- [x] Independent known-finding plus necessary whole-slice boundary inspection,
  at most2rounds; no narrow verdict misrepresented as whole READY. Exact
  head/tree/evidence once to root and sole publisher only if READY.

Final affected boundary310pass/2explicit Windows directory-fsync skips/6warnings,
46.12s; log41. Production refuses unsupported directory fsync before DB admission.
Windows protocol tests explicitly model that capability only; separate platform
tests exercise unmodeled production refusal and original archive GET200/bad404.
Native durability and actual production capacity are not established here.

## One aggregate R1 correction

Independent R1 report session-review-r1.md returns CHANGES REQUIRED: production
normal shutdown never calls actual close, and recursive mkdir ancestors were
not all synced. One independent invocation57pass/2native skips does not close
those call-graph/durability findings. Root also clarifies that controlled bad hot
must preserve HTTP/manifest-first while replay returns existing unavailable404,
without pretending previously admitted hot is empty.

Real aggregate RED43:5failed/1passed, covering actual TestClient lifespan,
specific ancestor-before-DuckDB ordering, corrupt/missing admitted hot and
manifest preference; GREEN44:6passed. Controlled corruption after healthy close
also RED46:2failed/2passed, then GREEN47:4passed. No outage is claimed for the
actual startup-crash reproduction, which independently passed. Candidate crash
tests now always mount HTTP, both before and after a real child COMMIT/os._exit;
never skip HTTP assertions on an exception. Persisted unreadability is explicit
404, otherwise actual hot rows must be retained. Both crash modes passed48.

The one aggregate changes buffer/feed and the authorized tiny existing-history
adapter only. Final R2 is the last round; any unresolved structural gap returns
to Planner without further source correction or a reset90min clock.

Final aggregate adds controlled partial-accounting RED51/GREEN52: the config
factory refuses acquisition without taking down readable persisted history or
altering the partial receipt. Hot missing after healthy close cannot be adopted
as a new empty DB; a failed charged constructor instead mounts stopped/unavailable.
Changed-source checks53 pass; the final corrected focused run54 is retained.

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

## FINAL R2 outcome

Final sourcefc4744fbad11ca71c0e8fd3a1f085318748fcd96, tree
feb38e01ec46b68e84587c666a4ae872953203e6. Independent FINAL R2 PASS closes both
Important findings and the authorized HTTP boundary, with no blocker in the
affected whole-slice software boundary. Single invocation66pass/2explicit native
skips/6warnings19.09s. Report session-review-r2.md SHA256
5151aafaeb0894864d04ab6799aa09fa1a07cfe9ca0b45b773db485e91d6c831;
log SHA256fd7cb7569ab96b08c86e9156d9c7a9a38dd34be771f2a0d0ce460cc7af2f979c.

Eligible for sole-publisher exact-head broad/native CI and normal merge under
standing authority; not deployment or production admission. No further source
patch/review cycle in this leaf. Source freezes; final evidence checkpoint is
documentation-only. No push/PR/CI/host/provider/actual DB/Goal action performed.
Operator evidence acquisition boundaries are retained at
output/market-history-hot-cache/operator-admission-boundary.md for root relay.
