# Incident: reconciliation mismatch

## Symptoms

- A reconciliation run reports deltas beyond the recorded tolerance
  (ADR-0006) — extra orders, missing fills, or a cash/quantity
  divergence between a surface and the order journal.
- The `consecutive_reconciliation_mismatches` metric is at or above
  the `max_consecutive_mismatches` limit and the M7 alert ledger
  carries an `ops:limits` `reliability_limit` alert (source
  `ops:limits`) — visible on the workstation `/risk` screen.
- Structured logs show `reconciled` records with non-zero deltas.

## Checks

1. Read the alert's `observed` payload (limit, measured value,
   limit_value) to confirm which limit crossed.
2. Pull the reconciliation delta report and identify the identity
   mismatch: an order id present on one side only is the usual
   cause (an orphaned order or a dropped fill).
3. Cross-check the audit bundle: the last verified export is the
   integrity anchor for both sides.

## Recovery

1. Do not silently accept the delta: every mismatch is attributed
   with the ADR-0006 identity/tolerance discipline before anything
   is reconciled.
2. If the journal is the trusted side, re-apply the missing
   surface state from it (recovery drill, M10 Phase B) and
   re-run reconciliation to zero deltas.
3. If the journal itself is suspect, follow the journal-corruption
   runbook first.
4. Record the mismatch count metric honestly (the metric is the
   alert input; resetting it to hide a breach is an audit
   violation, not a fix).
5. Re-export and verify the audit bundle; the alert ledger entry
   remains as permanent evidence of the incident.

## Prevent

- The recovery drill runs on a schedule; a non-zero reconciliation
  on a healthy install is a structural bug — file it as an issue,
  do not patch around it.
