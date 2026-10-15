# Portfolio budget SPEC review — scoped round 2

Verdict: PASS. No actionable new finding. The Standards R1 P2 orphan-reservation omission is closed by this narrow correction. SPEC review is complete at the approved two-round boundary; native PostgreSQL qualification remains pending.

Reviewed workspace: `C:/Users/15492/.codex-clean/worktrees/10c3/QuantMesh`. Reviewed delta: `8502eee7600de5edbcbc3e3b56e199b39def1ced` to independently verified HEAD `b10762883edc1bbad164951d1a1adfb9f0f7457c`. The actual diff changes only `services/research_agent/src/qm_research_agent/accounting.py` and `services/research_agent/tests/test_portfolio_budgets.py`, 29 added lines. This review did not reopen the original architecture or repeat the full focused/service suites.

## Closure evidence

`accounting.py:84` now checks reservations against effects with a reverse LEFT JOIN before validation returns, and `:88` raises ValueError on any orphan. The existing forward check continues to reject effects without attribution. The same validate function is reached during policy activation at `:127` and before admission/accounting at `:135`. Therefore an incomplete import cannot silently omit durable charged reservations through the later inner join. Activation fails transactionally; existing-instance admission catches the validation failure and returns denial before the high-water update or either effect insertion.

`test_portfolio_budgets.py:369` parameterizes both activation and existing-instance admission. It creates an actual orphan by deleting an existing effect through a separate fixture-only SQLite import connection (`:374`), verifies that import connection has FKs off (`:376`), and verifies that service transactions retain FKs on (`:386`). It asserts the original $0.60 reservation survives and there are zero model effects after denial. The supplied RED log shows both boundaries failing behaviorally before the fix, rather than failing for missing symbols.

The correction adds validation only. It changes no schema/FK definition, transaction/lock code, policy binding, amount arithmetic, UTC period/high-water behavior, category/lifetime treatment, lease fences, public signature, archived replay path, runtime default, provider gateway, frozen contract, or dependency lock. The fixture corruption connection is confined to tests and does not weaken the service connection.

## Verification and limits

Independently verified the two changed source hashes and all 13 correction/preserved-original-handoff evidence hashes selected from the updated handoff; no mismatch. Read the new raw RED/GREEN logs. Reported broader evidence is 56 focused passes and 90 service-offline passes/51 skips, and remains Windows/SQLite/scripted evidence.

Fresh bounded regression-only probe used the existing read-only service interpreter and candidate-only PYTHONPATH:

```text
python.exe -B -m pytest -c services/research_agent/pyproject.toml services/research_agent/tests/test_portfolio_budgets.py -q -k orphan_reservation --basetemp=output/portfolio-budgets/spec-r2-owned-20261013-1
```

Observed exit 0: `2 passed, 45 deselected, 1 warning in 0.77s`. The warning is the existing exchange_calendars/NumPy deprecation. Basetemp is fresh and workspace-owned. `git diff --check` on the exact correction exited 0; tracked worktree remained clean. No source edits, subagents, server/secret/paid/native-PG actions or full suite were performed.

No additional Task 1 correction is requested. Coordinator can supply `b10762883edc1bbad164951d1a1adfb9f0f7457c` to the independent Task 2 owner once its review axes close. The 51 skips still include Linux admission and opt-in PostgreSQL coverage; no real PG process race, pg_dump/restore, real model/billing, production TLS, off-host restore, deployment or clone-promotion authority is qualified by these receipts.
