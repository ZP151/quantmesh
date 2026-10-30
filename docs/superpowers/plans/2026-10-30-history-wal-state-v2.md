# History WAL-state v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:executing-plans inline; one independent whole-slice review plus Quant review, maximum R1/known-fix R2.

**Goal:** Open a genuinely checkpointed tiny owned DB with WAL absent through the existing private ordinary API loop while preserving strict v1 PRESENT support.
**Architecture:** Add explicit v2 models/typed receipts behind the private capability, authenticated evidence FDs and a permanently revocable absence epoch. Existing LiveBuffer SQL/opener/data semantics remain fixed. Pure offline producer serialization validates lineage, never issues actual proof.
**Tech Stack:** Existing Python/Pydantic/DuckDB1.5.5/pytest, no dependency/environment changes.
**Spec:** ../specs/2026-10-30-history-wal-state-v2.md (original approved bytes e46450c6; approval1462eae7/execution281575d1); issue https://github.com/ZP151/quantmesh/issues/257.

## Global Constraints

Original SQL/_tail_rows/cut2026-10-23T23:44:01Z/111keys/full17/rawJSON/NULL/math unchanged. Original inputs OSRO; no fake WAL. Aux256MiB/aggregate2GiB/reader1GiB/UTC/thread1 and public defaults unchanged. No host, real source data, service, environment or public/frontend edits. Source only tracked writer, Server only offline ACK, Publisher owns final CI/release. D/E and bounded maintenance/restore remain UNMET. All output within new32MiB; old holds retained.

## Files owned

- Runtime: src/quantmesh/live/history_ram_aux.py (v2 dispatch/evidence ownership); new src/quantmesh/live/history_wal_state.py (strict v2/receipt models, OS negative witness and pure producer bundle validation).
- Tests: new tests/test_history_wal_state.py; existing tests/test_history_ram_aux.py only if a bounded reusable-fixture adaptation is needed.
- Docs: this plan, its spec, docs/iterations/0038-history-wal-state-v2.md, new ADR0041; no shared topdocs. buffer.py is protected unless a necessary private-only adapter is demonstrated by RED.

## Review Focus

Version downgrade; false checkpoint/absence lineage; appearing-then-disappearing WAL/epoch; parent namespace replacement/permission errors; FD ownership/revocation without returned payload. Each belongs to the tests below.

### Task1: strict schema/producer interface

- [x] Write tests for v2 PRESENT/ABSENT serialization, v1 preservation, incorrect receipts/branches/manifest/approval; run targeted pytest -> RED.
- [x] Implement _AdmissionV2, checkpoint/absence/epoch receipt schemas, strict cross-lineage validation and pure encode bundle adapter; run same tests -> GREEN.
- [x] Freeze schema/interface and send one exact-hash field-feasibility ACK to Server by06:58:36Z. ACK is not host proof.

### Task2: private reader lifecycle

- [x] RED genuine checkpoint fixture has no WAL, private capability/API returns three hand-checked bars, DB unchanged/no WAL created/callerFD owned.
- [x] Add read-only held parent/receipt/epoch FD validation with only ENOENT accepted; exact current boot/generation/nonce/runtime and no-writer/namespace receipt linkage. Reuse existing capability/opener; GREEN.
- [x] RED query/decode-time epoch revocation, WAL appearance/disappearance/replacement, parent errors and payload suppression; implement permanent invalidation and normal owned close; GREEN.
- [x] Preserve raw failures/close and run bounded postcheck mutants; no synthetic vectors called real OS proof.

### Task3: bounded review and handoff

- [x] Targeted new+affected v1 controls, Ruff changed/runtime appropriate check, format/diff/submodule metadata and original SQL/AST comparison. No unrelated old full suite (execution authority overrides generic full-suite skill).
- [x] Independent Reviewer + Quant semantics; fix only concrete findings with RED/GREEN, one known-fix R2 maximum.
- [x] Update iteration/ADR/plan; commit green checkpoints, preserve all evidence and exact HEAD/tree/source/test hashes in HANDOFF<=16KiB; stop tracked edits and transfer to unique Publisher. Software completion is not original111x17/financial/host acceptance.


Ruling: keep all runtime v2 validation/models/OS helpers in history_ram_aux.py so the existing actual profile_source_sha256 covers the complete admission guard. history_wal_state.py is only an offline producer export; runtime never imports it. This avoids a new unbound guard module or changing frozen runtime field semantics/schema after Server ACK. Cost: larger private profile file, no new behavior. Four exported schema JSON objects must remain identical.

Ruling: RED close-green tests demonstrated a necessary one-line private buffer opener binding. Only ABSENT capability ownership closes its bound reader on revocation; v1/PRESENT remain unchanged and all original SQL methods stay protected.


Task1 complete: schema/producer RED3 then GREEN9/10, one frozen Server final ACK, no new schema round. Task2 complete: genuine checkpointed tiny API+FD lifecycle and concurrency RED/GREEN, exact-runtime bounded mutants. Task3 Source complete: affected79/2 existing warnings, Ruff/format/diff/submodule metadata, independent R1 + known-fix R2 READY; actual release belongs to Publisher. No Source push or third review.

Final rulings: the five declined actual OS/provenance/continuous exclusion/D-E-restore/original111x17/publication classes stay outside this approved software slice, explicitly UNMET; accepting this Source handoff cannot certify them. Cost of that scope limit is a separate real admission decision, not a software waiver. No deferred software minors remain.
