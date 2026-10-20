# ADR0031 — Frozen historical experiment inspection

Status: accepted for the verified local P2 slice; source merge pending in
[Draft PR195](https://github.com/ZP151/quantmesh/pull/195). No economic,
production or trading admission is implied.
Date: 2026-10-19. Issue: [191](https://github.com/ZP151/quantmesh/issues/191).

## Context

The retained SMA100/SPY evidence must be inspectable beside its P1 snapshot.
The forecast ExperimentRegistry measures RMSE/MAE and is not an appropriate
container for this historical strategy verdict. Replaying a consumed holdout
would create new research evidence beyond the approved inspection action.

## Decision

Reuse ObjectStore and the P1 SnapshotCatalog through a narrow opt-in local
frozen-experiment adapter. Preserve exact original package members, bind their
SHA256 associations and expose recorded results and original downloads. Store
immutable references with dedup and verified reopen. Never execute retained
Python or treat imported text as HTML. No external engine or strategy source is
copied into executable QuantMesh code; retained source is inert evidence.

Separate association verification from independent economic recomputation,
timestamp proof and data qualification. Preserve historical REJECT, formal
INSUFFICIENT and consumed-OOS state. Missing prior trial history stays unknown.
No import admits trusted data, promotes a strategy or grants order authority.

## Consequences

One fixed 46-member schema is deliberately specific to this case; another
experiment format needs an explicit adapter. No new package/dependency or
provider access is introduced. Market data remains local and uncommitted with
unknown entitlement unchanged. Existing vn.py runtime/license limits still
apply. A future paper/shadow action needs a separate concrete design.
