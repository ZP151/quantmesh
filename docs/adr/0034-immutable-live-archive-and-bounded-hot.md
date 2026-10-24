# ADR0034 — Immutable live archive and bounded hot observations

Date2026-10-24. Status: approved design B, final independent software review PASS;
exact-head broad/native publication and production operator gates remain pending.
Issue218; extends ADR0014/0023/0024/0025, preserves manifest research authority.

## Decision and operator approval

The human selected “按照建议B” for the concrete lifecycle proposal SHA256
827b4f54415eea607c28c8a61e80607ac22e7145559378019aa455cbad5c1d77.
Existing canonical DB and WAL remain at the original path and are opened only
with DuckDB read_only=True. This branch does not call schema/prune/migration/
index DDL on that connection. A missing/incompatible archive or read failure
is explicit history unavailable; it cannot silently become hot-only or demo.
Read-only queries and bounded hot use128MiB/one thread/no disk spill. Those
limits may refuse a large retained query; they do not prove retained-scale cost.

The original instrument-history/workspace service keeps manifest history first.
Without manifest history, it reads bounded tails from archive and hot under
the existing receive/market UTC filters, then retains archive-before-hot append
order, scoped event identity/digest and disruption evidence, STATUS barriers
and the original interval/continuity gates. Per-store local_seq is not global.
An equal ID with conflicting content or continuity evidence is unavailable.
The combined replay is still observed, unqualified replay; UNKNOWN stays UNKNOWN.
Compare still requires manifest history. No route, response schema or UI added.

## Explicit opt-in and write admission

`QUANTMESH_LIVE_CACHE_ROOT` and `QUANTMESH_LIVE_CACHE_BUDGET_FILE` are paired
opt-ins on the existing --live entry. The original lake_root still supplies
the immutable archive and manifest datasets; the new hot directory may not
contain/alias that original root. The legacy default configuration is unchanged.
In B only the new hot uses retention0; it never prunes or rotates old/new data.

The bounded budget JSON has these required fields (schema1, no unknown fields):
root, ledger_sha256, peak_bound_sha256, leaf_remaining_bytes,
global_reserved_bytes, peak_operation_bytes, close_failure_reserve_bytes,
max_batch_bytes and expires_at_utc. Root must resolve exactly to the hot root;
hashes must be nonzero. Leaf allowance has a64MiB upper ceiling, **not a grant**.
The existing operator ledger must exclusively reserve global_reserved_bytes
after all other highwaters/future reserves and establish the referenced maximum
operation-growth bound for the exact runtime/batch limit. This includes startup,
DDL/index/WAL, scratch, intent/failure records and close costs. Unknown/unverified
peak bounds must not be supplied as approvals. Hashes are trusted external
receipt references, not independent capacity proofs; fixtures use synthetic ones.

Admission takes min(leaf_remaining, globally earmarked allowance), leaves the
close/failure reserve unused by normal operations, and checks actual current
free space minus next peak/reserve is >=50GB. Before constructor storage effects
and each accepted append attempt, it exclusively creates and fsyncs one numbered
intent consuming the **whole** peak reservation. POSIX fsyncs every ancestor
directory through the filesystem root, including entries created recursively;
syncing only the hot root and its immediate parent is insufficient.
Failure, duplicate delivery, small actual growth and restart never refund it.
An existing unaccounted hot root or altered/malformed accounting is refused.
This is conservative admission under an externally established bound, **not a
native DuckDB file-size quota or a derivation of WAL size from JSON lengths**.
This software has not established a production peak bound or allocated bytes.

At exhaustion/expiry/free-space refusal an immutable budget-stop record uses the
reserved failure space. No auto-rearm/root rotation or accounting reset exists.
The feed stops acquisition, closes admission, joins existing owned I/O and does
not apply failed rows/cursors/delivery. The last successful admitted commit is
applied/delivered before its capacity stop. Stored snapshots age normally. A
stopped hot reopens read-only and the HTTP history service remains attached.
If first-start allowance is zero/insufficient/expired or free headroom refuses,
there may be no hot DB at all. A stopped empty in-memory reader supplies zero
observations, with read-only guards/no spill and no provider start; the actual
canonical archive is still required and read by the original history service.
This does not create disk storage or substitute fake history. A safe capacity
warning is emitted; if no failure-storage allowance exists, no accounting files
are materialized. Malformed/unqualified configuration still refuses activation.
After a successful COMMIT, failure writing/fsyncing the proactive stop record
cannot revoke its receipts. Deliver that committed result, close acquisition,
retain a separate budget-stop-failure receipt if writable and surface a fixed
error code plus whether that receipt was actually recorded. If both writes fail,
the existing consumed intent stays and the service error log is the failure
surface; no second write attempt or refund is granted within the stopped feed.
Current source_status is not an archive of all failures; original STATUS,
quarantine, jobs/reports and existing output evidence are retained.

### Reduced durable-admission recovery contract

FINAL R2 rejected the prior process-only assurance: both terminal writes can
fail with allowance remaining, so consumed intents alone do not prevent restart.
That whole-slice STOP is retained. Planner separately authorized the minimal
recovery leaf on issue218; it does not withdraw durable-stop/no-auto-rearm.

Each startup first proves all prior sessions normally closed, then consumes a
full startup intent and exclusively writes/fsyncs budget-session-NNNNNN.json
before opening DuckDB or enabling acquisition. The session binds the exact spec
SHA and startup-intent number. No previous session, malformed/partial/foreign
evidence, unmatched closure, or an unaccounted DB grants restart. Failed marker
creation/fsync leaves its attempted intent charged; no storage is enabled.
An open marker exists before the failure that would otherwise need a new stop
receipt. Any admission/storage/capacity/failure stop permanently poisons this
session; a process crash simply leaves it open. Neither restored free space nor
failure to create either terminal receipt can close it.

Only successful actual DB close, after all feed-owned accepted I/O has joined
and with no session failure, may close the session. First exclusively write and
fsync budget-close-ready-NNNNNN.json, including parent directories, containing
the same spec/start and final consumed-intent number. Finally atomically create
the exclusive budget-closed-NNNNNN.json hard link to that prepared receipt.
No fallible storage operation follows publication; no evidence is removed.
Failure before publication leaves an open session. Publication itself is not
acknowledged as directory-durable: if a crash loses the link, restart refuses;
if it survives, its fully prepared content proves the already completed normal
DB close. An exception/stop/crash before normal close never prepares authority.
The production feed's application-shutdown cancellation joins accepted work,
releases its session owner, then calls the actual bounded buffer close. Failure
poisons before closure. A capacity stop alone does not close that connection,
so the still-running HTTP service retains its persisted reads.
Normal restart still validates all cumulative intents, expiry, physical free
space and original allowance, then charges another startup peak. It refunds
nothing and cannot reset, rotate or adopt an unfinished session.

Directory fsync support is mandatory for session admission. On platforms where
the existing OS adapter lacks O_DIRECTORY (including this Windows runtime),
production hot admission refuses and history uses the stopped read-only path.
The Windows protocol tests explicitly model only that directory-durability gate;
they still use real tiny DBs, files, I/O and a real child-process crash, but are
not native durability qualification. A separate unmodeled production test proves
unsupported-directory-sync refusal. POSIX directory-fsync/native CI remains a
release gate; neither passing unit tests nor a platform skip grants activation.

The external peak proof must include all retained session/open/prepared/closed
metadata and close/failure costs, as well as every numbered intent. No physical
peak proof or exclusive global earmark has been established by this leaf.
Unfinished-session controlled re-admission, if required, needs a separately
verified operator budget/recovery decision with all old receipts retained; no
automatic reset, extra approval UI or recovery framework is introduced here.

Planner clarified the inherited hot-read failure boundary during the reduced
leaf's R1: unreadable hot must not prevent the workstation HTTP service mounting.
An admitted hot file that is missing, incompatible or unreadable becomes an
explicit stopped unavailable reader, with no substitute DB or empty replay.
Persisted reads raise a fixed error; the existing history adapter converts that
failure to HistoryUnavailable/404. No archive-only success can silently discard
unknown hot observations. Feed initialization/attachment does not invent cached
updates or recovery cursors, providers stay stopped and source state unavailable.
Manifest-backed history still wins and can be read without that replay. A never
admitted root with no DB/storage/session evidence retains the separate verified
empty stopped reader. Controlled bad-hot tests prove this boundary; they are
not a claim that the successful actual startup-crash test reproduced an outage.
Malformed/partial budget accounting on the production config factory also
refuses acquisition without resetting evidence: existing readable observations
may still be read, while unknown/unreadable data remains explicitly unavailable.
This does not accept that accounting as a write approval or refund any attempt.

## Consequences, deployment and rollback

No original-row copy/move/delete/checkpoint, new service, engine, dependency,
provider authority or paid resource. Existing staging~9.5GB is protected baseline;
new cumulative5GB/free50GB accounting remains separate. No SPY capture/financial/
Phase2 or legal/market-data qualification is added. No actual host acceptance here.

The sole server operator must first bind a real existing-ledger reservation and
verified peak proof, exact source/runtime and disjoint hot path, then perform the
existing bounded formal-URL acceptance. Missing budget/proof is a concrete
activation refusal, not permission to invent numbers or silently use legacy live.
Tiny software evidence cannot establish the7GB archive's schema/WAL/read cost.

Rollback retains both archive and hot/accounting/evidence. Use the accepted
oldDemo profile or stop acquisition; **do not restore an old --live release on
canonical lake_root**: old software ignores the new settings and may invoke its
default7day prune/migration. Do not clear budget-stop/intents, remove failed data,
checkpoint the archive or rotate a fresh hot root to obtain more allowance.
Any future capacity extension/rolling retention requires a separate concrete
ledger/policy decision; this slice provides no infinite live-growth guarantee.
