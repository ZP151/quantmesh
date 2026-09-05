# Iteration 0028 — Decision Inbox & Bounded Paper Shadow Portfolio

- Status: in progress
- Started: 2026-09-05
- Tracking issue: [#129](https://github.com/ZP151/quantmesh/issues/129)
- Branch: `codex/0028-decision-inbox-shadow-portfolio` from `origin/main` at
  `324d51d82ab4eae5e6176f7f91ce0631c5e76c32`
- Design:
  `docs/superpowers/specs/2026-09-05-decision-inbox-shadow-portfolio-design.md`
- Executable plan:
  `docs/superpowers/plans/2026-09-05-decision-inbox-shadow-portfolio.md`
- Ledger: this file

## Product outcome

From the existing watchlist, the operator can see which instrument needs
attention, open the exact saved DecisionPacket without losing identity, and
understand the packet's deterministic evidence, paper proposal/order,
monitoring and review state. The loop remains local-first and paper-only.

## Approved route

Route A reuses Watchlist as the Decision Inbox entry point and Instrument
Workspace as the only detailed decision surface. It adds no broad portfolio
dashboard and no second order authority. NVDA and AAPL prove the complete
deterministic loop; BTC and SOL remain honest Watch/Reject-only cases whenever
their forecast/evidence closure is insufficient for Paper.

## Slice boundaries

1. **Decision Inbox:** one read-only, cross-watchlist attention model with an
   exact packet deep-link, integrated into Watchlist.
2. **AAPL extension:** demonstrate the same saved decision and pending Paper
   proposal path for AAPL without adding a provider, model or execution path.
3. **Honest crypto degradation:** make BTC and SOL support saved Reject and
   Watch decisions while Paper is explicitly blocked by missing evidence.
4. **Paper shadow summary:** derive exact packet → proposal → order → monitoring
   → review state from existing durable ledgers and prove clean-restart replay.

Each slice has one user action, one visible outcome and a 24–48 hour boundary.
Reviewer feedback is capped at two rounds; a third structural failure shrinks
the slice instead of expanding repair work.

## Acceptance criteria

- Watchlist exposes a useful next action without requiring CLI navigation.
- Every decision link carries an exact `packet_id`; a newer draft cannot
  silently replace the selected packet.
- NVDA and AAPL can save and reopen Reject, Watch and a pending Paper proposal;
  order creation remains a separate confirmation in the final slice.
- BTC and SOL can each save and reopen Reject and Watch on independent packet
  lineages, while Paper is explicitly blocked before proposal creation by
  missing or insufficient evidence.
- The summary never upgrades AI output, marks, positions or inferred P&L into
  execution evidence.
- Paper remains two-stage and passes the existing deterministic risk kernel.
- Packet, proposal, order, monitoring and review identities survive a clean
  restart and replay fail closed on invalid ledgers.
- Desktop and 390px flows remain keyboard accessible with no document-level
  horizontal overflow.

## Prohibited expansion

No Provider/OpenD, real market calls, real trading, external notifications,
new model frameworks, broad performance dashboards, social/mobile/extension
work, other instruments, or 0021 soak changes. Impeccable sidecar refresh and
the known license-closure maintenance item do not block slice development; the
license closure must pass at the final PR boundary.

## Progress

### 2026-09-05 — kickoff

- PR #128 and PR #119 merge state were read from GitHub and stale repository
  metadata was corrected.
- Issue #129, the isolated 0028 worktree and the active resumable Goal were
  created from exact `origin/main`.
- Existing stores confirm that the new Inbox can be a read-only composition of
  replay-validated DecisionPacket, watch, proposal/order and review records.
- Route A is approved. The written design is awaiting operator review before
  an executable implementation plan or product-code change.
- Planner/Product review split the overloaded multi-instrument slice into an
  AAPL action slice and a separate BTC/SOL degraded-state slice. Quant/Risk
  review required exact outcome-preview eligibility and neutral pending-Paper
  wording; both corrections are incorporated in the design.
- The second and final Planner/Product and Quant/Risk review round both returned
  `APPROVED`. No authority, attribution or scope blocker remains; operator
  review of the written design is the only gate before plan generation.
- The operator approved the written design on 2026-09-05. The design is now
  frozen for implementation planning; changes to authority, attention
  semantics, symbols or slice boundaries require a new explicit review.
- The executable plan maps six reviewed tasks across four visible slices, uses
  RED/GREEN cycles, keeps broad verification at coherent boundaries and retains
  one final exact-head release gate. Slice 1 Task 1 is the active frontier.
