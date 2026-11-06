# Preserve original owned-leader output during terminal transition

Issue: https://github.com/ZP151/quantmesh/issues/281

Planner authorized this independent direct CI-blocker slice after PR291/run
42164094257 failed its existing Linux nonzero-output qualification case. Its
tool/test bytes matched base0b61. Init E2E runtime and its R1/R2 reports remain
frozen; this is not another Init structural patch round.

User action: run the normal exact-head release gate. Success: an original
registered leader that exits with7 retains both exact streams and its actual
exit, while live/unknown/foreign members still refuse signal authority.

The existing empty-environ branch already retires only the exact original
Popen leader, matching start ticks and an admitted member's terminal pidfd.
Its zero-time readiness sample can precede terminal readiness during teardown.
Permit one bounded100ms pidfd event wait in that same branch. Apply the same
retirement observation to an unreadable /proc environment only after the
existing scan re-reads matching leader start ticks and finds its retained
member. An unavailable live identity still propagates PermissionError. Other readiness
calls retain their zero-time default. No ownership error is caught/relabelled;
nonempty wrong nonce, live empty environment, unknown identity and generation
changes retain their refusal. No new admission or signalling authority follows.

Evidence: a local owned synthetic sample produced the same ValueError while
exe/argv/generation matched and the retained pidfd was not yet ready. A native
child/pidfd regression with a controlled empty-read/exit boundary reproduces
the exact CI message and naturally exits7. CI's original missing internal
trace is not invented. Full-zombie image probes and their exploratory failures
are retained separately; they do not justify broader image-identity changes.

Non-goals: database/business acceptance, Init/provider/OpenD changes, new
environment/dependencies, production host tests, retries/sleeps to obtain green,
unknown-member signals, data/math/financial/trading changes. Reuse existing
owned tooling and the fixed existing local WSL Python/pytest environment.

New full capacity registration retains all prior538MiB and adds local7MiB
once: Source1/Common6 including next CI2, scratch streams2, failure1 and
review/coordination1. P31 is capacity-only with spent batch02; futureP32 does
not activate batch03/connection8. No new runtime GO.
