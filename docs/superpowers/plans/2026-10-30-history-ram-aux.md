# Guarded history RAM auxiliary profile implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline with TDD; one fresh focused branch review, known-fix R2 at most. No third structural review.

**Goal:** original saved-history API can use one explicitly admitted private RAM auxiliary area while its source and normal defaults remain readonly/unchanged.
**Architecture:** opaque private capability from a bounded root-owned readonly admission FD; strict records bind actor/snapshot/runtime/shared cgroup/tmpfs/guard. Source verifies actual OS facts before connect/replay, Server owns complete content/no-writer evidence and continuous monitoring. Existing factory receives the constructed history service; no public API/CLI change.
**Tech stack:** existing Python/DuckDB/FastAPI; no installs, new environment or upstream copied code.
**Spec:** [approved design](../specs/2026-10-30-history-ram-aux.md), SHA a2119e8331b869f33a94fbaf509ce3e5ea8dc51df29ea95cef67905feaacb746; human approval b737f446acfc4c5e1479ec05083c7c46467f30648057fda66f431253f0ea70e1; execution c8b1be862f4f8d939c007f42bc2a819811b9cfb567d45eca96ed395f376b4ab0. Issue [255](https://github.com/ZP151/quantmesh/issues/255).

## Global constraints / review focus

- Canonical DB/WAL OSRO, original SQL/batch32/111x17/NULL/rawJSON/dupmissing/sort/owned-caller TX/math unchanged; no7.42GB copy/provider/query/SSH from Source.
- Default128MiB/temp0/API/CLI unchanged. Private fixed1GiB engine/256MiB tmpfs/noexec/noswap/mode0700; all guard/API/reference/aux pages share2GiB, not extra RAM. Missing actual gate fails before data; no disk fallback.
- Source writer1 only tracked profile/tests/docs. Server writer2 only ignored controller/guard/admission. Only Publisher runs normal release CI/merge; protect existing workstation/SPA.
- Local32MiB fullhold includes Git/cache unknown/logs/all failures/test roots/close reserve; remote0, no old refunds/borrowing. Forecast in output/history-ram-aux-implementation-20261030.
- Root first increment03:56:50Z/reviewable05:56:50Z, actual ACK01:59:08Z. Historical Goal blocked label does not stop authorized work; no duplicate Goal.
- Focus regressions: forged FD/body; false tmpfs/noswap/unit; lost/reused guard PID/lock; stale or changed snapshot/runtime; default/profile isolation and cleanup after refusal.

## Task1 — strict admission and actual OS verifier

Create src/quantmesh/live/history_ram_aux.py, tests/test_history_ram_aux.py. Interface DRAFT is output/history-ram-aux-implementation-20261030/INTERFACE.json; freeze after alignment with Server. Accept FD/SHA only from trusted startup, no public request flags/callback returningTrue.

- [x] RED strict records reject malformed/extra/duplicate/nonfinite/stale/wrongactor/runtime/snapshot/guard/quota.
- [x] RED actual evidence verifier refuses missing POSIX lock, same PID, wrong cgroup/memory/swap, absent tmpfs/noswap or OSRO; no boolean receipt can substitute live checks.
- [x] Implement bounded FD/readback parsers and opaque one-use capability. Source does not repeat7GB hashes: authenticated Server admission binds full prehash/no-writer/generation receipts; source checks current file identity and guard/lifetime.
- [x] GREEN python -B -m pytest -q tests/test_history_ram_aux.py --basetemp=output/history-ram-aux-implementation-20261030/task1; record raw exit/import/source pins. Commit coherent green checkpoint.

## Task2 — private readonly opener and original factory

Modify only buffer private construction/read-boundary seam; no _tail_rows/query math changes. Keep ordinary ctor default. Add targeted tiny archive/factory cases; no old wide111MiB/hour suites.

- [x] RED no capability/no live evidence cannot open profile; valid controlled OS seam invokes real tiny DuckDB and complete original history API; default settings unchanged; lost guard refuses read and close remains possible.
- [x] Implement private LiveBuffer._open_history_ram_aux, one-use claim, original readonly connect config, current checks around replay. Reuse existing LiveHistoryService/LiveFeed/history injection.
- [x] GREEN targeted new/affected semantic cases, Ruff, changed Python format, whitespace and submodule pins. Tests using synthetic OS readback seams are explicitly not actual host/tmpfs qualification.

## Task3 — review, source freeze, publisher handoff

- [x] ADR/iteration/roadmap/reuse and approved spec/plan agree with observed code/tests; real admission remains UNMET.
- [x] Fresh focused independent R1 and necessary known-fix R2 only, no third whole audit; substantive corrections RED/GREEN.
- [x] Exact commit/tree/base/source-test/evidence hashes, full local hold/per-test footprint and source writer release. Normal Git commit; Source does not push/CIwatch/deploy.
- [x] Root hands frozen source to sole Publisher; Server only after actual merged CI/catalog plus all gates can attempt original API once and independent a355 full111x17/math/normal close. This is not Source test PASS or financial qualification.

## Source release boundary

Checked tasks denote Source completion and handoff, not actual release/admission.
Source0a8f14ad plus test correction4ef27811 received R1 NEEDS_FIX(one P2 coverage)
and final known-fix R2 READY. Actual APIs/OS111x17/math still require Publisher
merge/catalog and Server gates.41 new controls plus earlier affected default case
pass; no third audit/old broad tests. See iteration and frozen interface evidence.
