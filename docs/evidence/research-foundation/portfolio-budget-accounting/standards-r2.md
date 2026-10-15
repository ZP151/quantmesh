# Portfolio budget standards review — round 2

Candidate: `b10762883edc1bbad164951d1a1adfb9f0f7457c`. Prior reviewed candidate: `8502eee7600de5edbcbc3e3b56e199b39def1ced`. Review scoped exclusively to the reverse completeness guard in accounting.py, its focused test, and adjacent malformed-history/rollback behavior. No third structural review or implementation edits.

**Round 1 P2 closed; no new actionable findings in this scoped review.** `services/research_agent/src/qm_research_agent/accounting.py:84` now rejects reservation rows with no matching model effect. The shared validate() path makes policy activation raise and existing-instance admission return False before the inner join can omit the row. The guard uses the complete job_id/digest identity and adds no transaction, schema, or frozen-store changes.

`services/research_agent/tests/test_portfolio_budgets.py:369` covers both activation and admission using the independently connected, foreign-keys-disabled incomplete-import reproduction from round 1. It verifies that the durable 0.6 reservation remains, no new effect is inserted, and service transactions still enable foreign keys.

Independent bounded verification on this exact head used the readonly ed95 service venv, disabled bytecode, and a fresh reviewer-owned basetemp under the coordinator output directory:

```text
pytest -c services/research_agent/pyproject.toml services/research_agent/tests/test_portfolio_budgets.py -q -k 'orphan_reservation or malformed_or_incomplete or duplicate_crash_reopen' --basetemp <fresh reviewer-owned directory>
10 passed, 37 deselected, 1 warning in 4.30s
exit 0
```

The ten cases cover the new two-boundary regression, existing malformed/incomplete accounting denial, and duplicate/crash/reopen/transaction rollback. The single warning is the existing exchange_calendars NumPy timedelta deprecation. The handed-off raw narrow RED (two failures) and GREEN focused (56 passes) evidence was also inspected. Existing Windows/offline receipts remain preparation only; real PostgreSQL/dump-restore qualification and actual model/provider activation remain pending.
