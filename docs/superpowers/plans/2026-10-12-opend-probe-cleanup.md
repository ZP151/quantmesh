# Windows OpenD probe descendant cleanup

Issue: [#156](https://github.com/ZP151/quantmesh/issues/156), continuing the
operator's October 12 instruction to repair high-priority blockers.

## Scope and acceptance

One operator action: run the existing read-only recovery observation when SSH
requires authentication. One outcome: the observation finishes within its
deadline and leaves no processes from its own probe, while the existing GUI,
helper and external tunnel remain untouched.

The actual October 12 SSH check requests Tailscale check-mode authentication.
This is a human authentication gate, not permission to alter SSH policy.
Separately, the old bounded probe kills only the Tailscale wrapper; native SSH
and proxy descendants can survive, or hold output pipes open after wrapper exit.

Only `deploy/windows/opend_recovery.ps1` and its native tests change. An
anonymous Windows Job Object owns a gated probe bootstrap and descendants.
The bootstrap cannot invoke Tailscale before job assignment succeeds. Closing
the job terminates only that probe tree on timeout, exception or normal exit.
Output draining is bounded. Assignment failure fails closed before CLI launch.
Do not change tunnel lifecycle, probe protocol, authentication, credentials,
public ingress, vendor configuration, trading or AWS runtime.

## Implementer and verifier

- [x] Add native fake-wrapper tests for a hanging wrapper and an early-exiting
  wrapper with a surviving child, alongside an unrelated live sibling.
- [x] Observe RED: both cases fail on the old implementation; one leaks the
  child, the other exceeds the outer 25-second deadline. Preserve red2.log.
- [x] Implement gated job ownership and bounded output draining.
- [x] Three focused probe checks pass / 19.50s; preserve green.log/.exit.
- [x] Complete native affected file:33 passed/54.05s, native2.log/.exit0.
  Ruff and whitespace checks pass. The first full run32/1 reveals an existing
  fixture observing the user's installed helper mutex; isolate only the fake
  installation's helper-absence boundary. Active-helper uninstall still has
  its separate real-policy regression. Independent Spec and Standards round1
  both have no actionable P1/P2; these reviews do not certify installation.
- [ ] Push one tested checkpoint and PR; exact-head CI and applicable review
  policy must pass before merge. No repeated tests for earlier PRs.
- [ ] Install only merged reviewed bytes. Replacing a running helper requires
  a concrete operator handoff that preserves any active owned/external tunnel;
  do not stop it implicitly. Existing installation stays untouched meanwhile.
- [ ] After human SSH authentication, prove remote loopback/source reachability
  and exact AWS build69515b7/paper=true/live=false. No AWS redeployment.

Evidence: `output/0037-probe-cleanup/`. The initial RED invocation had a missing
basetemp parent; the first fixture revision hit a C# constant-branch compiler
warning. Neither is runtime evidence. Corrected red2 records actual failures.

## Other blockers remain separate

Soak audit finds disabled tasks pointing to a missing runner. The independent
maintenance plan requires fresh v5 roots, a source-contract preflight, one
fully verified real daily cycle and only then scheduler admission. Preserve
old negative witnesses. No 168-hour clock has started; do not enable old tasks
or reuse past elapsed time. The old capacity observer contains only 51 samples
over 4h10m on build33aa0521, not 24h. Capacity/recovery/firewall acceptance cannot
be claimed complete from this probe repair. Never manufacture an outage/reboot.
