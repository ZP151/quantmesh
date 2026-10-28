# ADR 0038: Version the native daily quantity loop and candidate protocol

Status: accepted for the closed synthetic engineering slice, 2026-10-29.
Issue: [#245](https://github.com/ZP151/quantmesh/issues/245).
Decision: [approved scheme A](../superpowers/specs/2026-10-28-native-quantity-v2.md).
Implementation: [native quantity plan](../superpowers/plans/2026-10-28-native-quantity-v2.md).

The existing daily replay cashbook is the sole writer of shares, cash, dividend
receivables, fees and marks. Version it in place with a trusted internal quantity
policy seam. At the next original OPEN, that seam can request a signed whole-share
quantity from the frozen close action and a read-only account view. The kernel
checks the request, applies any fill and charges the established cost formula once.
Policy callbacks may advance campaign state but may not update the cashbook.
The existing metrics and reconciliation remain based on this same ledger.

Use a distinct `qm.native-daily.candidate.protocol.v1` identity for the fixed
engineering candidate. It binds kernel, adapter and policy source; data and
action identities; window, calendar, timing and cost assumptions; and every
T/TO/B50/B100/C arm at 5 and 10 bps. Its first entry point accepts only the
closed synthetic case. The result is saved as original content-bound bytes and
can be reopened without recalculation. The Decimal account view is conservative
and read-only; it cannot authorize an extra share or silently replace the
existing float ledger. Ex-date entitlements become spendable only on pay date.

Retire new submissions under the legacy SMA100 replay profile before execution.
Previously saved IDs, original report and decision bytes, downloads and proof
checks remain readable with their historical source identities. Do not run an
old profile against the new source hash or migrate a consumed once/OOS marker
into the candidate protocol. The kernel change, legacy submit fence and new
candidate identity are one release unit.

The native daily candidate is an offline engineering path. Its synthetic numbers
are not out-of-sample evidence, a real-data permission, paper qualification or
live order authority. Existing paper-default and deterministic live approval
boundaries remain in force. Rollback disables new candidate execution while
preserving its original artifacts and legacy read access; it never reopens old
profile submission or refunds a consumed marker.

This decision reuses the existing cashbook and immutable object store. The
installed vn.py fixture adapter described in ADR 0029 remains available for its
own supported work; its current wiring does not establish equivalence for this
candidate's ex/pay receivable, next-OPEN and whole-share cash semantics.
