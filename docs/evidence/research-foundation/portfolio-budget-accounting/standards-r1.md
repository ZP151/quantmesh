# Portfolio budget standards review — round 1

Reviewed exact candidate `8502eee7600de5edbcbc3e3b56e199b39def1ced` against baseline `216b378192bbc0a1742a28b7a1fc75a86ae2fda9` in `C:/Users/15492/.codex-clean/worktrees/10c3/QuantMesh`. Scope was the ten changed Task 1 files, the coordinator Decisions/Task 1 requirements, and the Task 1 handoff. AGENTS.md was not applied. Implementation files were not modified.

## [P2] Reject reservations whose effect row is missing

**File and verified lines:** `services/research_agent/src/qm_research_agent/accounting.py:135-138` (related one-way completeness validation at lines 79-83).

`validate()` rejects model effects without matching portfolio reservations, but never checks the reverse relationship. `admit()` then uses an inner join, so a durable reservation whose effect row was omitted by an incomplete import is silently excluded from the charged total. Reopening the same policy also accepts this history. This defeats the explicit incomplete-history fail-closed boundary and can grant a fresh allowance while the durable reservation ledger already records exhaustion. Normal store foreign keys prevent this state through ordinary service transactions; this is an import/corruption case, not a normal last-slot race.

**Verified reproduction:** In an independently owned SQLite/scripted fixture, create two published jobs and a policy with operating cap `0.6`; reserve `0.6` for the first job; use a separate SQLite connection with its default foreign keys disabled to remove that job's `model_effects` row while retaining its portfolio reservation; reopen the identical policy; reserve `0.6` for the second job. Both reopening and the second reservation succeed, and the durable reservation prices are `0.6, 0.6`, total `1.2` against cap `0.6`.

The bounded probe reused the readonly `ed95` service Python environment with bytecode disabled and fixture directory `C:/Users/15492/.codex-clean/worktrees/0038-research-integration/QuantMesh/output/portfolio-standards-r1-b5jwqyes`. It exited 0 with:

```text
reopened_authority: True
new_effect_accepted: True
durable_reservation_prices: [('0.6',), ('0.6',)]
durable_total: '1.2'
cap: '0.6'
```

**Requested correction:** Validate the reservation-to-effect relationship as well as effect-to-reservation before activation/admission, rejecting an orphan instead of omitting it. Add a focused incomplete-import test that verifies reopening rejects and an existing ledger cannot insert a new effect after this mutation.

No other actionable standards finding was verified. Reviewed preparation receipts show 54 focused passes and the Windows service offline gate; these are not real PostgreSQL/dump-restore qualification. No full core suite, provider invocation, paid call, server, key operation, or shared-temp modification was performed.
