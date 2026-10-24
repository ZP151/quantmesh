# Iteration0038 — approved B history lifecycle

Issue218: https://github.com/ZP151/quantmesh/issues/218.
Plan: docs/superpowers/plans/2026-10-24-market-history-hot-cache.md.

Planner: human “按照建议B” approves proposal
827b4f54415eea607c28c8a61e80607ac22e7145559378019aa455cbad5c1d77.
One user outcome is existing history GET combining immutable archive and bounded
hot, manifest-first, continuing reads when acquisition stops at quota. Sole inline
writer, base97f8caf; no repeated approval or new Goal. Start10:44:54SGT2026-10-24.

Quant: operational observation lifecycle only; no invented continuity or source
rights, UNKNOWN upgrade, formalhistory qualification, research calculation or
paper/live authority. Actual capture0/financial0/Phase2NOT_STARTED maintained.
OldSTATUS/failure/report evidence and original DB/WAL remain untouched.

Implementer: own five runtime files settings/workstation/buffer/live_history/feed,
corresponding tests and necessary ADR/roadmap/own records. Existing DuckDB/public
models/replay/owned-I/O reused; no upstream source/dependencies copied. Issue208
is separate and explicitly excluded this lifecycle work; its code is reused.

Reviewer/Verifier: test-first tiny real DuckDB and API checks; final independent
review capped at2rounds with one aggregate correction. Exact-head CI/publishing
belongs to sole release owner; real host acceptance belongs to sole server owner.
Implementation and actual outcomes below remain pending until observed.

## First implementation checkpoint

Existing history baseline34passed/6warnings (01). Seven new actual tiny DuckDB/
API cases failed for missing behavior (02), then7passed (03). Original archive
bytes/mtime stay unchanged, including a genuine uncheckpointed tiny WAL fixture;
incompatible/missing archive refuses rather than creating/migrating/falling back.
Original history URL merges archive+hot despite independent local_seq values;
scoped identity/digest/continuity conflicts reject. Manifest-first and shared
workspace authority remain. Necessary first compatibility88passed/6warnings (04).

Budget RED4/GREEN4 (05/06): before-I/O full peak reservation, failure and restart
no-refund, unknown proof/wrong root/unaccounted store refusal, bounded hot cannot
enable retention. Stop/settings RED3 then all14passed (07/08). First affected
command09 ran no tests because a nonexistent test_settings.py path
was named; the corrected actual command10 passed268/6warnings. No failure erased.

Further real RED/GREEN pairs cover continuity metadata absent from content_digest
and durable stop/no rearm (11/12), last admitted commit delivered before proactive
stop (13/14), no unbudgeted spill (15/16), and bool-vs-int intent tamper (19/20).
POSIX parent-directory fsync proof is one explicit Windows skip; it remains a
native CI gate, not a claimed local PASS. Boundary/startup check18 passed25 with
that1skip/6upstream warnings. Final affected checkpoint/review still pending.

Ruling: retain existing DuckDB engine and storage. Admission consumes externally
verified peak reservations rather than inventing a physical size bound from
JSON bytes; exact original ledger/global earmark/peak proof remains required for
real activation. No byte allocation or real production bound established here.
See ADR0034 for explicit schema, limits and dangerous old-live rollback warning.

Frozen pre-review affected check21:280passed,1Windows-only POSIX fsync skip,
6upstream warnings in43.31s. Changed-file Ruff/format and diff checks pass.
One source writer; five runtime files and one new test file only. First code/TDD
checkpoint is inside the first60min; software is not final until independent
review and its necessary correction/reverification are complete. No real host,
archive, provider, capacity allocation or financial computation was used.

## Independent R1 and one aggregate correction

R1 on immutableb3dc479: CHANGES REQUIRED, two Important findings reproduced in
one independent run:26passed/1Windows skip plus2output-only repro failures.
Cold first-start capacity refusal attempted to open a nonexistent hot DB and
took history startup down; post-COMMIT stop-file I/O failure discarded successful
receipts. Review/raw repro file and log remain under output/market-history-hot-cache.

One aggregate batch promoted genuine4REDs (22), then4GREEN (23), plus zero-budget
RED/GREEN (24/25), and explicit first-start warning RED4/GREEN4 (27/28).
First-start expired/insufficient/zero/free-floor now uses an empty stopped
read-only in-memory reader, creates no hot disk DB and starts no provider, while
the original valid archive serves the same URL. This is zero synthetic history.
COMMIT receipts survive later stop-write/fsync failure: apply/ack/deliver final
row, retain separate failure receipt when possible, emit fixed error and actual
recorded flag, then stop/join. Both receipt writes failing is tested too; failure
is surfaced and no within-process rearm/refund occurs. Initial affected checks,
tests and old failures remain preserved. After aggregate correction, affected
check29 passes287/1explicit Windows skip/6warnings in42.90s; changed-file Ruff,
format and whitespace checks pass. Final independent R2 remains pending.
