# Equivalent read-only history tail — issue218 B2 follow-up

Planner: one action is original default BTC ONE_DAY archive+hot history, all
original predicates and10000 events. Root authorized a bounded60min leaf from
actualACK09:54:21Z through10:54:21Z; plan is
docs/superpowers/plans/2026-10-24-readonly-tail-query.md. Branch
codex/readonly-tail-query from actualorigin/main7a1fa218. OldPR219/220 and B2
failure stay valid; no old CI/review or host query repeated.

Quant researcher: observation read path only. STATUS/gaps, event identity,
inclusive receive/market/asof boundaries, append order and UNKNOWN are semantic
requirements. No market/provider/source qualification or financial authority.
Original Goal remains blocked/capture0/financial0/Phase2_NOT_STARTED/PRECISE_UNKNOWN.

Investigation: operator's formal service RED09:52:39.402692Z/2.027s is reused,
rawSHA1de9843615a1d305e67ea2b520c17bf5c9397e45dab3ebcb8a52a5ce608d5784.
Read-only constructor PASS and unmodified DB/WAL are independent observations.
Do not blame probe256M cgroup: no OOM or controlled cause evidence exists.
Local72 failed only Windows plan-output encoding; retained.73 initial3column
model did not discriminate,74fullschema old/new both passed32/128MiB.75 trial
removed final order from old too and is exploratory, not exact old evidence.
76correct exact old/full17column60000row512B model at16MiB/no spill: old OOM,
key-only selection/no wide SQL sort + bounded Python order PASS10000 rows. All
pass128MiB. EXPLAIN disproves an unconditional full-payload WINDOW theory: old
DuckDB1.5.5 optimizes selection to rowid arg_max. Its final wide SQL ORDER_BY
remains; candidate removes that operator and explicitly isolates sequence-only
selection. Profiles/model are not a guarantee for the actual7GB archive or RSS;
DuckDB reported peak can exceed its memory_limit. No realhost diagnosis claimed.

Implementer/Verifier/Reviewer: targeted RED/GREEN and exact freeze review pending.
Runtime scope buffer.py tail only; no environment, config, settings/feed/history,
DB migration, index, dependency, actual host/mount/earmark/Goal or provider change.

TDD:77collection syntax failure and78fixture channel/JSON construction errors
were retained and corrected before counting valid evidence.79/80valid RED2 with
73pass: exact old query's constrained-memory refusal and the true-empty limit1
NULL-row decoder failure.80's oracle independently counts the empty relation;
no exception handler changes failed reads into empty history. Minimal runtime
delta9insertions/3deletions isolates original scalar-key rank then membership,
removes final SQL payload sort and orders returned rows in Python under lock.
81GREEN75pass4.94s. Differential rows include every field and original filters,
nonpositive/default1000/service10000 limits, boundary times with timezone offset,
STATUS recovery evidence/gaps, legal venue-sequence ties/noncontiguous local_seq,
PK duplicate refusal/source-event dedup, and corrupt selected/excluded records.
The memory case returns10000 complete validated events including STATUS, equal
to the old128MiB oracle, using a test-only tighter16MiB/no-spill connection;
actual read-only file bytes/mtime stay unchanged, no WAL/temp directory created.
Initial Ruff import/format issues are retained;82fixes only test layout.

Verifier freeze:83affected invocation220passed/2explicit Windows native-directory-
fsync skips/6existing warnings56.28s exit0, covering new tail queries, all legacy
buffer/lookup and existing live-history/archive+hot API boundaries.84changed Ruff,
format and whitespace pass exit0. No full repository suite/native/CI. Source
freezes for one independent known-query plus affected-boundary review, at most
two rounds/one aggregate correction. Local commits bypass hooks after explicit
checks; sole publisher owns exact-head CI/normal merge and immutable root/operator
receipt. This is candidate software evidence, not actual B2 recovery/host READY.
