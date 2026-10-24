# Approved B: immutable archive and bounded hot observations

Issue: https://github.com/ZP151/quantmesh/issues/218.
Approval: human “按照建议B”, relayed by root on2026-10-24; approved proposal
SHA827b4f54415eea607c28c8a61e80607ac22e7145559378019aa455cbad5c1d77.
This is execution, not another design approval. Inline sole implementation writer.
Base97f8caf3702f1164f3b1c013f8b82bc30e1e9869; managed worktree
market-history-hot-cache, branch codex/market-history-hot-cache.
ACK10:44:54SGT; first60min code/TDD checkpoint due11:44:54SGT.

## User action and invariants

Open the original instrument history URL: manifest-qualified history remains
first; otherwise immutable canonical archive and persisted hot replay share the
existing response/continuity policy. Quota stops acquisition/writes while reads
remain available and freshness ages. No original DB/WAL write, checkpoint,
migration, pruning, move or copy; no demo/hot-only fallback on archive failure.
No provider/host/actual database, SPY/financial/Phase2, dependency, service, UI or
new API operations. Existing current source UNKNOWN and research gates remain.

## Execute in one slice

- [x] RED then GREEN actual tiny DuckDB read-only reopen, no DDL/DML/bytes changed,
  explicit missing/schema refusal; implement read_only constructor branch in
  live/buffer.py, guarding writes and reusing original replay/row decoding.
- [x] RED then GREEN existing history URL merging archive+hot, duplicate identity
  with digest equality/conflict, local_seq collisions, STATUS barriers, both
  time filters, unknown/gapped provenance and manifest precedence. Extend
  LiveHistoryService with optional archive_root and wire shared service in
  api/workstation.py; no endpoint/response type changes.
- [x] RED then GREEN explicit bounded hot budget and restart accounting, no
  automatic deletion, upfront headroom/close/failure reserve, no admission if
  original cumulative/global/free constraints cannot fit. Settings default off;
  64MiB is no automatic grant. Reuse buffer/feed owned-I/O admission and stop;
  in-flight commit joins, no failed cache/cursor/delivery, reads survive stop.
- [ ] Necessary focused compatibility, Ruff/format/diff and independent review
  <=2rounds. One aggregate Important correction, third structural problem STOP.
  Add necessary ADR/iteration/roadmap evidence. Commit green checkpoints;
  sole publisher01a130b3 owns exact-head CI/PR/normal merge, no duplicate GH/CI.

Commands use existing Python313, PYTHONPATH=src, unique output/market-history-hot-cache
basetemps: pytest -q tests/test_market_history_hot_cache.py followed by affected
buffer/feed/history/workstation/settings tests. Broad release checks belong to
slice/final CI boundary, not repeated during each task. No packages installed.
Verifier records real outputs in iteration; synthetic operational fixtures never
prove actual 7GB performance or source qualification.

## Review focus / limits

Archive read failures must not become hot-only success. Cross-store sequence is
not globally comparable; retain archive-before-hot append order, scoped event
identity/digest conflicts and disconnect barriers. Restart may not replenish
consumed growth budget. File stat+JSON size is not a proof of DuckDB peak growth;
admission must reserve bounded transaction/WAL/scratch/close/evidence costs, or
refuse. Failure stops providers without stopping history HTTP service. Rollback
must preserve both stores and must never run the old default writer on archive.

Server sole operator01a14f1e owns real URL/host acceptance. This writer hands exact
head/tree/logs to publisher and root; no deployment. Source slot releases only
after reviewed handoff or a concrete out-of-scope archive-write requirement.

Ruling: DuckDB has no native maximum DB size; normal JSON payload length cannot
prove physical peak. Keep the approved existing DuckDB storage and require an
existing-ledger earmark and explicit verified peak-bound receipt. Debit that full
peak before every attempt, reserve close/failure costs, disable spill, stop if
unknown/insufficient, and make no production-growth claim. This avoids a new
storage format/platform and does not allocate the proposed64MiB. Server owner
must provide actual evidence under existing technical authority before activation.

## Final disposition — blocked at R2, return to Planner

Source e47c889870fdc7f809fd1c358c5090f90f889ee4 is DO_NOT_RELEASE. The one
aggregate correction closed both R1 failures. Final R2 (35passed/1Windows skip)
found terminal stop can be lost across restart if both stop receipts fail and
temporary free-floor refusal later clears with allowance remaining. See the
active iteration for exact counterexample and immutable report/log hashes.

The final acceptance checkbox remains incomplete. Two rounds are exhausted:
no third source correction or review, no publisher READY. Release the sole
writer slot to Planner/Product for a bounded restart recovery contract. A
pre-I/O durable admission-session marker with read-only recovery of unfinished
sessions is a proposed scope reduction only; it is not implemented here.
