# Owned PostgreSQL qualifier — Spec round 1

Scope: only the new qualifier, its behavior tests and runbook against
`docs/superpowers/plans/2026-10-13-owned-postgresql-qualification.md`, baseline
`42fbfa510b8153c7a2b3b6fd3e5d4851eda850e8`. No original #171 architecture review,
production edits, database launch or broad suite was performed.

**Actionable specification findings: 0.** No scope expansion found.

The implementation admits only the official source/license identities and
private native Linux root, verifies measured binary digests/version, defaults
to preflight, creates fresh credentials/cluster, fences SQL and cleanup using
actual process/data/system identity, and requires the default gate's exact
30/0/0/0 counts plus all five named PostgreSQL cases in authoritative JUnit.
Runtime import paths/hashes are now recorded. The runbook preserves fixture
limitations and keeps the simulated lease clock separate from #172's actual
Worker crash witness.

Evidence inspected: archived source and COPYRIGHT bytes match pinned SHA256;
Ubuntu archive signature receipt is good; build-tool versions/notices and
install proof are present. Archived service-gate JSON and JUnit agree on
30 tests, zero failures/errors/skips, exit 0; the owned receipt and stop log
record clean shutdown. The root-provided current unit receipt
`native-count-green.log` records 30 passed.

**Readiness: qualifier code is ready for final verification. Final acceptance
is pending a fresh actual fixture run of the reviewed version.** The first
`actual-fixture` receipt predates strict count/JUnit checks and `imports.json`,
and its original qualifier unit receipt reports 18 passed. It establishes the
real PostgreSQL gate result but must not certify the current helper. Root
confirmed a fresh final-v2 run is planned after review fixes; archive its
imports, strict counts, shutdown and raw gate proof before completion.

Reviewed SHA256:

- helper: `a5795a1ea293f9a77cd086cdc9d75a4b4b7dccd04116eec71735824aca2c5f90`
- tests: `568b4461f46e292bffa9e68516c391926bc0995224a7ba04cdcdfe388b1b4b85`
- runbook: `d6eb47ec05210f9413fdd4703bf85a64a52ee0f3b977ffc238b24321475047ff`
