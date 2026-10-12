# Owned PostgreSQL qualifier — Spec round 2 (final)

Scope: the three new qualifier files and fresh final proof against
`docs/superpowers/plans/2026-10-13-owned-postgresql-qualification.md`, baseline
`42fbfa510b8153c7a2b3b6fd3e5d4851eda850e8`. No production edits, database launch,
broad suite or repeat of the original #171 architecture review was performed.

**Actionable specification findings: 0. Readiness: ready for bounded handoff.**

The final admission changes preserve the approved scope: owned checkout/venv
paths reject symlinks; frozen-source admission precedes driver import, rejects
tracked changes and admits only the three new files; driver/schema dependency
paths remain inside the owned prefix. The helper checks actual core/store/driver
module paths and SHA256 before running the unchanged gate. These enforce the
plan's ownership and source identity requirements rather than adding a new
product capability.

The round-1 evidence freshness gap is closed. Fresh
`final-fixture/fixture.json` identifies a new owned cluster and postmaster,
PostgreSQL 18.6, Linux CPython 3.12, the frozen source commit and expected binary
digests, with `gate_exit: 0`, exact 30/0/0/0 counts and `stopped: true`.
Authenticated SQL data/listener/port/user/system identity agrees with the
fixture receipt. `imports.json` records the expected owned runtime/source paths
and hashes.

Independently inspected authoritative gate JSON and JUnit both report 30 tests,
zero failures/errors/skips, including all five required real PostgreSQL cases.
The gate preserves schema digest
`a645a8bde2b439587f736a6a6875e4ffae77265cdcc2900d0b2def43f5f0de18`
and protocol digest
`454cce6bd355465e48a59cb61fbbacb775776cb28c41826e54aff554cf2ccae1`, with
unchanged lock identity and passing license/dependency checks. The stop log
confirms server shutdown. Fresh `final-proof/unit.log` records 33 passed;
fixture, unit, lint, format and preflight exit receipts are all zero.

The runbook still limits acceptance to the local disposable fixture and leaves
the real Worker crash/recovery witness and container deployment to #172.

Reviewed SHA256:

- helper: `ee6f1f2306d7864f2b616aecadae5b4028bce05981ec3474a978b11a2bf9dbb3`
- tests: `18a02459ada1716c207de1d72b679d6c20156be9a0c4f28a84510b8343e66998`
- runbook: `5ad9a47d283c782e43ec5b0e78fcd11114b734d3efaf1f3570675cfbabb3b130`
