# Single-operator persistent OpenD console implementation plan

> Execute inline with executing-plans/TDD; one fresh independent branch review.
> The actual human explicitly approved this adjustment and direct launch after
> necessary checks; do not ask for the same approval again.

**Goal:** One Operator logs in privately and keeps the same OpenD process after SSH detaches (#192).

**Architecture:** Add an explicit schema2 single-operator persistent session to the
existing pinned console guard, with a separate fixed permit and service template.
Permit freshness still bounds initial release to900s; it does not terminate a
released persistent session. Original schema1 expiring stage stays unchanged.

**Tech stack:** Existing stdlib Python3.12, audited tmux3.4, systemd and pidfds.
No new dependency or paid resource. The direct user messages and concrete
proposal are retained under server-closeout output as the binding specification.

## Constraints and scope

Only deploy/aws/opend/stage_console.py, a new persistent template, new targeted
tests, one runbook and this plan/own iteration checkpoint. No other runtime,
product UI, PR186 code, credentials, qualification flags or original11111 route.
One source writer; root owns remote mutation. User is Operator/reviewer/SafetyOwner,
actual person count1. Never claim independent two-human review. Paper/live rules
unchanged. Credential/state/terminal bytes never enter assistant tools or logs.

## Review focus

Expired/replaced/unknown permit denies initial release; single-role authority is
explicit rather than fabricated. Persistent mode must not leak into schema1.
No independent vendor alarm remains after persistent release. Parent death,
pidfd cleanup, manager identity, exact unit/source/vendor pins, echo-off PTY,
resource caps and null manager streams remain enforced. SSH detach preserves
backend/pane/vendor; controlled service stop kills the exact owned cgroup.

- [ ] New permit/unit/lifecycle regressions RED on current source.
- [ ] Minimal schema2/CLI/fixed-path/manager and persistent child changes GREEN.
- [ ] Targeted actual Linux process tests, affected prior stage tests, Ruff,
  formatting and whitespace; no unrelated broad local suite.
- [ ] Independent review <=2 rounds, coherent commit/PR/current CI, normal merge
  and actual full-tree verification; no unmerged deployment.
- [ ] Fresh installed-source synthetic persistent manager/pane/detach/stop proof;
  exact host/resource readiness and permit, then actual vendor launch.
- [ ] Open visible private Windows SSH attach client with no assistant observation;
  retain real unit/nonce/PID metadata. Human supplies login only in that window.
