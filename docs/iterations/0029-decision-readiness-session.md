# Iteration 0029 — Decision Readiness Session

- Status: design review
- Started: 2026-09-07
- Tracking issue: [#131](https://github.com/ZP151/quantmesh/issues/131)
- Integration branch: `codex/0029-decision-readiness-session`
- Baseline: `origin/main@4fb810e1268f5f0e13599d7198aee4fa78cc4717`
- Design:
  `docs/superpowers/specs/2026-09-07-decision-readiness-session-design.md`
- Executable plan: pending written-spec approval

## Outcome

Give a research-minded individual active trader one explicit session in the
existing Decision Inbox that shows whether watched decisions have usable data,
refreshes all registered local conditions, and opens the exact triggered,
blocked or review-due DecisionPacket within two minutes.

## Product boundary

Iteration 0029 unifies the user experience but does not merge iteration 0021's
data-plane authority. It may consume exact trusted-data readiness through a
read-only adapter. It cannot operate Scheduler, Provider/OpenD, trusted-data
roots, soak evidence, outbox or GitHub witness state.

## Success criteria

- [ ] Decision Inbox shows exact readiness, evidence time, mark time/reason and
  last local check for every scoped identity.
- [ ] Real readiness is qualified only through the packet's exact manifest and
  evaluation bindings; demo remains explicitly labelled.
- [ ] One explicit action evaluates all and only registered local watches from
  server-owned facts without provider or order calls.
- [ ] Complete, partial and no-registration refresh outcomes are honest and
  deterministic.
- [ ] Triggered, blocked and review-due entries open the exact packet.
- [ ] Refreshed evaluations and exact links survive clean application restart.
- [ ] NVDA/AAPL complete the session in under two minutes; BTC/SOL remain
  evidence-blocked where required.
- [ ] Targeted, browser, restart, final release and CI checks pass.

## Delivery slices

1. Readiness truth in Decision Inbox.
2. Explicit local session refresh.
3. Action queue and exact navigation.
4. Restart and two-minute acceptance.

Each slice must produce visible user value within 24–48 hours, has one bounded
deliverable and stop condition, and receives at most two review rounds.
Targeted verification is normal; broad gates occur at meaningful slice and
final PR boundaries rather than after every micro-change.

## Prohibited expansion

- Provider/OpenD or real market calls
- Scheduler, automation, external notifications or GitHub witness changes
- trusted-data writes, new roots, overlap resolution or soak migration
- proposal confirmation, new order authority, testnet or real trading
- AI priority/readiness authority
- symbols beyond NVDA, AAPL, BTC and SOL
- Qlib/Darts/model-ranking work
- 0021 source, evidence or operational-state modification
- unrelated cleanup or frontend sidecar maintenance

## Checkpoints

### 2026-09-07 — Activation and architecture approval

- Operator approved the Decision Readiness Session boundary: one unified
  product entry with separate 0021 and 0029 engines.
- Issue #131 records the user outcome, acceptance criteria and prohibitions.
- A fresh worktree and branch were created from merged
  `origin/main@4fb810e1268f5f0e13599d7198aee4fa78cc4717`.
- The written design is pending operator review. No implementation plan or
  product code has started, and no 0021, Provider/OpenD, Scheduler, evidence,
  trading or external-notification state changed.
