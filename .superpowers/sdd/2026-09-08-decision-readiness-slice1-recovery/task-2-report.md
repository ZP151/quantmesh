# Recovery Task 2 report — Inbox and restart recovery proof

## Status

DONE_WITH_CONCERNS — the focused backend evidence is complete and production
code was unchanged; the prescribed scoped Spec review remains pending.

## Commit

`test(decisions): prove inbox readiness recovery` (created after the final
focused verification and whitespace check).

## Scope

- Modified `tests/test_decision_inbox.py`, the active Iteration 0029 ledger,
  `docs/goals/ACTIVE.md` and this task report only.
- Used the real `DecisionInboxService`, `DecisionPacketStore`,
  `DecisionWatchStore` and `DecisionWatchService`; the catalog is the existing
  exact-ID fake that rejects catalog enumeration.
- No production code, readiness module, UI, Provider/network, Scheduler, 0021
  data-plane, refresh, trading or unrelated file changed.

## Evidence

- Focused new-proof selection:

  ```text
  python -m pytest tests/test_decision_inbox.py -q -k "projects_exact_real or sanitizes_corrupt_or_mismatched or snapshot_and_get_leave_packet_mark or reconstructed_inbox_preserves" --basetemp %TEMP%\quantmesh-0029-slice1-recovery-b-new-3
  exit 0; 6 passed, 23 deselected, 1 warning in 188.97s (0:03:08)
  ```

- Required full target:

  ```text
  python -m pytest tests/test_decision_inbox.py -q --basetemp %TEMP%\quantmesh-0029-slice1-recovery-b-full-20260908
  exit 0; 29 passed, 1 warning in 985.24s (0:16:25)
  ```

- The only warning in both selections was the inherited
  `StarletteDeprecationWarning` from the shared FastAPI TestClient dependency;
  it is not a product failure.

## Mutation rationale

The recovery ruling permits initially passing tests because they cover
behavior that already exists. Each assertion group is tied to a realistic
production mutation:

| Proof assertion group | Named mutation caught |
| --- | --- |
| Exact selected packet ID, ready status and requested exact manifest | `fallback-to-current-catalog-head`: Inbox replaces the packet-bound manifest with a newer catalog entry. |
| Manifest, evaluation, report and evaluated-at projection | `drop-qualified-closure-fields`: Inbox omits or substitutes the qualified evaluation/report details. |
| Registration/evaluation IDs and persisted monitoring timestamp/status/reason | `recompute-monitoring-from-memory`: Inbox drops durable evaluation facts or invents a current status. |
| Session maximum last check, registered and triggered counts | `session-summary-from-transient-view`: summary ignores durable registrations/evaluations. |
| Mismatched manifest and corrupt closure unavailable output with no evidence reference | `identity-mismatch-fallback`: readiness accepts another manifest or exposes fabricated evidence after a bad exact closure. |
| Untrusted exact closure blocked output retaining only its exact reference | `quality-failure-promotes-ready`: a failed exact quality result becomes usable or is replaced. |
| Exact catalog request list | `catalog-enumeration-retry`: failure causes a catalog-wide or alternate-ID lookup. |
| Snapshot and GET bytes for packet, canonical mark map, registration and evaluation inputs | `read-path-appends-state`: projection writes a packet/evaluation/registration or mutates configured marks. Marks are an injected in-memory map, so their canonical JSON bytes are compared; the other three are durable JSONL stores. |
| Restarted row and `DecisionSessionSummary` equality | `in-memory-session-recovery`: post-restart Inbox loses exact readiness or durable monitoring/session facts. |
| Reconstructed `last_checked_at`, `latest_status` and `latest_reason` | `monitoring-fields-not-replayed`: restart rebuilds the row without the persisted latest evaluation observation/results. |

## Concern / next step

One scoped Spec review must find no open Critical or Important issue before
this recovery task is accepted. Task 3 and the one slow Slice 1 integration
selection remain outside this task.
