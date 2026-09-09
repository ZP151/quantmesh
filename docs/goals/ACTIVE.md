# Active Goal

Iteration 0031 is active under
[issue #135](https://github.com/ZP151/quantmesh/issues/135).

Goal: deliver a privately reachable, exact-commit AWS Lightsail demo/paper
staging workstation for the solo operator without public application ingress
or new execution authority.

Resume from:

- branch `codex/0031-aws-private-staging` based on `origin/main@a78ff0a`;
- ledger `docs/iterations/0031-private-aws-staging-workstation.md`;
- approved design
  `docs/superpowers/specs/2026-09-09-aws-private-staging-design.md`;
- executable plan `docs/superpowers/plans/2026-09-09-aws-private-staging.md`.

Repository implementation and bounded verification precede the external
handoff. Stop for operator confirmation before creating the Lightsail
instance, subscribing a budget email, installing/authorizing Windows
Tailscale, or approving the server device. Never run the full pytest, domain,
browser E2E or release gates for this iteration.
