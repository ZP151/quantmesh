# Standards review — owned PostgreSQL qualifier, final round 2

Scope: final delta in the three owned qualifier/test/runbook files and supplied fresh proof. Baseline `42fbfa510b8153c7a2b3b6fd3e5d4851eda850e8`; no original #171 architecture review or broad suite. No edits except this report.

**Findings: none. Both round-1 P2 findings are resolved.**

- `validate_runtime_paths` (`tools/qualify_owned_postgres.py:103`) now fences checkout and venv through `owned_child` before runtime admission, rejecting symlinks including linked ancestors. Linux behavior tests cover both borrowed directory cases.
- `validate_source_contents` (`tools/qualify_owned_postgres.py:107`) now rejects tracked changes and untracked additions except the three explicitly owned files. It runs before SQL-driver imports (`:238`). Imported driver/Pydantic paths must belong to the owned environment, and the runtime probe verifies expected store/core/driver paths and byte hashes (`:386`). The behavioral source test covers admitted qualifier addition, rejected untracked shadow module, and rejected tracked modification. The runbook describes these boundaries.

Evidence read directly:

- `admission-red.log`: 3 new admission cases fail before implementation, 30 pass; `admission-green.log`: 33 pass.
- `final-proof/unit.log`: 33 pass; unit/Ruff check/Ruff format exit receipts all 0.
- `final-proof/fixture.exit`: 0. Fresh `final-fixture/gate/service-gate.json`, JUnit and original pytest log agree on 30 tests, zero failures/errors/skips. All five named real PostgreSQL cases appear in JUnit.
- Fresh `fixture.json` records PostgreSQL 18.6, private loopback SQL/system identity, strict counts, gate exit 0 and `stopped=true`; `stop.log` independently records successful shutdown.
- Fresh `imports.json` records owned native checkout/venv module paths and hashes. Published schema/protocol digests remain unchanged in the gate receipt.

**Readiness: ready for the bounded qualifier slice's integration, subject to root's normal iteration/checkpoint and commit-boundary gates.** Local fixture limitations and the separate #172 real Worker crash/recovery witness remain explicit; this review does not certify production deployment or OCI.
