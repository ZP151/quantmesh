# Live checkpoint query implementation plan

> **For agentic workers:** Use superpowers:executing-plans and TDD for this single task. Root owns independent review, commit and integration.

**Goal:** Remove the wide-row checkpoint WINDOW while returning the identical ordered durable events.
**Architecture:** One SQL statement aggregates an explicit complete row struct by maximum local_seq per unchanged checkpoint stream. Keep the existing connection lock, schema, row mapper and synchronous interface.
**Tech stack:** Existing Python and DuckDB1.5.5, pytest, Ruff; no new dependencies.
**Spec:** [Issue201](https://github.com/ZP151/quantmesh/issues/201), acceptance supplied in the root-owned checkpoint issue packet.

## Constraints and review focus

- Only recovery_checkpoints in src/quantmesh/live/buffer.py; focused tests and this iteration/plan.
- No latest/retention/cache/index/schema/ingest/threading/cursor changes; no remote/provider/deployment.
- Filter before aggregation: excluded provisional/disrupted candles must not hide eligible older rows.
- Full winner struct: nullable fields, timestamps, identity/digest, evidence and payload must come from one row.
- Preserve venue/instrument/kind and separate L2 sides/metrics channels, sparse local_seq ordering, empty input and non-Hyperliquid behavior.
- No production-root-cause, index-access, speed or live-recovery claim.

## Task1: Query-only checkpoint optimization

Files: modify src/quantmesh/live/buffer.py; create tests/test_live_checkpoint_query.py and docs/iterations/0038-live-checkpoint-query.md.
Interface: recovery_checkpoints(*, venue: str, instruments: list[str]) -> list[MarketUpdate], unchanged.

- [x] Capture baseline source bytes with Windows git and base28221e1; record existing isolated branch and source import path.
- [x] Add a real DuckDB boundary probe around the production method, asserting no wide-row WINDOW or second scan; run against old source and retain actual RED.
- [x] Add small real-DuckDB fixtures covering unchanged filtering, channels, scopes, quarantine, sparse sequence, nullable/full-row winner and ordering; compare frozen legacy query outputs and independently expected events.
- [x] Replace only the checkpoint WINDOW with arg_max(explicit17-field struct,local_seq) grouped by the unchanged channel expression; keep params, lock and mapper.
- [x] Run new focused tests and relevant existing buffer/feed/supervisor checkpoint tests; changed-file Ruff, scoped format and git diff --check.
- [x] Update this checklist and iteration with exact phase/RED/GREEN evidence and limitations; stop at reviewable uncommitted diff for root.

Pre-flight: one task, no shared interfaces. No migration/ADR needed for the query-only algorithm. Broad repository checks run at root's commit/PR boundary, not repeated during this targeted leaf. Root already authorized inline implementation; no additional approval or delegation is requested.

Ruling: existing buffer formatting outside recovery_checkpoints differs under
available Ruff0.16.6. Only the changed method range was formatted; full-file
format is not claimed. Baseline and current text outside that method match.
Evidence and root-owned remaining gates are in the iteration checkpoint.
