# Incident: kill switch engaged

## Symptoms

- The workstation header shows the kill-switch state as ENGAGED
  (every page; `/kill-switch/control` is the control surface).
- Order submissions are refused with a typed risk-gate error naming
  the kill switch — globally (all venues) or for one venue.
- The M2 paper kernel refuses even paper submissions while engaged
  (M10 Phase C enforcement: the accounting risk gate, no model
  cooperation involved).

## Checks

1. Determine scope from the refusal message: global bit or a
   specific venue's flag.
2. Inspect the audit trail: the kill-switch flip is an in-memory
   account change in M9/M10 — confirm who engaged it from the
   operator context and the session where `/kill-switch/control`
   was used (the confirm-gated POST is the only path).
3. Check the alert ledger for a preceding `ops:limits` alert or a
   drift/staleness alert that may have prompted the engagement.

## Recovery

1. Investigate the triggering condition (drawdown breach, drift,
   operator decision) before disarming — the switch is the safety
   surface, not a state to clear casually.
2. Disarm through the same confirm-gated control
   (`/kill-switch/control`, or the CLI in a future phase); the
   account object, the JSON surface and the page context flip
   together (dataclasses.replace — they cannot disagree).
3. Verify submission resumes per venue: one small paper order
   round trip.
4. Record the incident: an `ops:limits`-style note or an alert
   ledger entry with source `ops:kill-switch` is permanent
   evidence; the audit export captures it.

## Prevent

- Enforcement lives in the accounting path — every submission goes
  through the gate, so an engaged switch cannot be routed around
  by any higher layer (proven by the Phase C enforcement tests).
- Keep the global bit for emergencies and per-venue flags for
  targeted halts; the per-venue state is visible on the
  workstation risk/control screens.
