# ADR0033 — Evidence-bound local paper controls

Status: implemented, locally verified and independently reviewed READY.
Date: 2026-10-20. Issue: [196](https://github.com/ZP151/quantmesh/issues/196).

## Context

The current paper account, persisted snapshot, journal recovery, order risk
kernel and manual kill-switch page already exist. The new user action needs
inspectable pause reasons and guarded resume of their current consistent state.
A UI-only checklist or a check outside the account transaction could race a
later account change. Live enablement approvals describe a different authority.

## Decision

Keep this explicitly opted-in, demo-only and synthetic. Reuse account/journal
persistence and matching rather than adding a strategy scheduler or execution
engine. Add an optional transaction validation callback to PaperAccountStore,
unset in all existing/default/live uses. The rehearsal validates current local
evidence before matching or journal effects, and confirms resume against an
evidence/version association under the same account authority lock.

Existing proposal confirmation normally journals kernel rejections. To preserve
that default audit behavior while meeting the explicit rehearsal's zero-effect
pause contract, bind an optional default-unset fresh-submission guard only in
P3 demo assembly. It runs under the existing account transaction after historical
replay and before fresh matching/persistence, checking current evidence and
global/venue stops. This is separate from the transaction integrity validator;
historical replay does not become another order.

Use explicit positive finite rehearsal caps, independent control/account writer
leases and durable intent/outcome/first-receipt discipline. Repeated requests
return original receipts with current state; old resume replays never undo a
later pause. A valid cold startup is always paused. Invalid/corrupt cold account
construction may retain the existing startup refusal; no account repair UI is
introduced. Keep corrupt original evidence, and fail closed during attachment.

In this mode, legacy JSON/HTML disarm cannot bypass verified resume. Demo reset
is refused instead of adding a reset migration. The dedicated panel extends the
current Ops kill-switch route. Default behavior remains unchanged without opt-in.
Configured/loading/error page descriptions and blocked-order headlines use local
copy, and verified status mirrors the existing shared switch query. Only the
exact capability-off503 response enables legacy controls; generic failures do not.

## Consequences

This proves local synthetic execution controls, not strategy suitability,
historical data quality, real-market costs or an investment risk budget. It adds
no dependency/provider/broker, live permission, paid resource or deployment.
The existing live ApprovalLedger and consumed historical REJECT experiment
remain separate. Future strategy sessions, real forward data and production
operations require their own evidence and design.
