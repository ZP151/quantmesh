# ADR0039: Fixed candidate workstation admission and original-byte reopening

Status: accepted for offline implementation,2026-10-30; release and real-data qualification remain separate gates.
Issue: [253](https://github.com/ZP151/quantmesh/issues/253).
Spec: [approved short design](../superpowers/specs/2026-10-30-native-daily-real-workstation.md).
Plan: [implementation](../superpowers/plans/2026-10-30-native-daily-real-workstation.md).

Reuse the ordinary Research jobs surface and one candidate-specific service over
ObjectStore, JsonlStore and WriterLease. New requests carry immutable references,
not paths, data bytes or client authority flags. The server registers trusted
input/grant/scope/protocol identities. No configured package produces a durable
INSUFFICIENT admission, not_run task and null report; this neither computes nor
consumes a trial. A Reject/Watch decision may bind that admission without a report.

The admitted intent and its one-use grant reservation are persisted together
before computation. Identical UUID/request retries read the existing task;
changed requests conflict and a new UUID cannot reuse its consumed grant. An
interrupted admitted task remains spent and never auto-runs after restart.
Completed tasks remain complete. Decisions bind the original request, admission
and optional report digests and are immutable.

Extract only the existing internal ten-arm calculation from the closed candidate
adapter; do not change native-daily-v2, the candidate policy, quantities, fees,
ex/pay handling, marks, metrics or the sole cashbook. New envelopes are distinct
from the original engineering protocol.v1. The original fixture guard and cold
reader remain closed and legacy SMA/once submission is not reopened.

The reference-bound RealInput contract separately records raw USD price and share
volume units, declared historical venue coverage, complete supported cash ex/pay
actions, calendar/timezone/version, availability/PIT/revision limitations, source
and review references, exact window/sample role/exposure and trial-ledger identity.
Its candidate-specific bound grant and separately registered authority reference
must match those identities and the output root. Admission checks the full121
sessions and supported input structure, without requiring known PIT or all-market
coverage. Cold read uses stored facts, not regenerated calendars.

The adapter accepts independently authored offline substitutes beyond the fixed
v1 byte identities. Reviewed-real manifests can be represented and checked, but
actual real execution stays disabled and cannot consume a trial. Current positive
runs are clearly labeled engineering. Real packages, provider use, exact scope
and actual trials still need separate qualification. Old SPY/once grants cannot
migrate. The original engineering v1 reader remains supported separately. Costs remain
5/10bps uncalibrated proxies, financial qualification INSUFFICIENT, paper/live false.

Cold readers verify original object bytes, request/envelope identities and the
complete ten-arm matrix without invoking calculation, calendar generation or
providers. Current selectable input options cannot invalidate a saved task.
Browser storage retains the UUID before POST and uses GET after uncertain replies;
it never silently creates a replacement trial.

Generic protocol.v3 freezes Python, pandas, NumPy and calendar implementation/
contract versions alongside source identities. Execution rejects runtime drift
before a trial is reserved. Cold readers retain archived runtime values rather
than substituting the current environment. Unreleased v2 draft objects with no
runtime remain read-only evidence and cannot authorize fresh computation.

The local launcher uses an explicit persistent --native-daily-root outside any
resettable demo root. No storage means visibly unavailable; it does not claim an
ephemeral successful save. New generic workers, public import, strategy loading,
trading authority, dependencies and a second accounting loop remain out of scope.
