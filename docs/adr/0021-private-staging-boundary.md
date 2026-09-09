# ADR-0021 — Private single-operator staging boundary

- Status: accepted
- Date: 2026-09-09
- Related: ADR-0011, ADR-0012, ADR-0013

## Context

QuantMesh is local-first and its workstation deliberately refuses non-loopback
binds. The operator now needs an always-available acceptance station reachable
from the current Windows computer without turning the unfinished product into
a public or multi-user service. A plain public Lightsail web port would bypass
the product's local threat model, while SSH port forwarding alone would make
routine testing unnecessarily fragile.

## Decision

Use one Ubuntu Lightsail instance as a private, demo-only staging host.
QuantMesh remains bound to `127.0.0.1:8765`; Tailscale runs outside the
application and exposes that loopback service to the operator's tailnet with
private HTTPS through Tailscale Serve. Tailscale Funnel and public application
ports are prohibited.

Every release is named by an exact lowercase 40-character Git commit and
installed in `/opt/quantmesh/releases/<commit>`. Staging startup requires both
that commit and one canonical `https://<device>.<tailnet>.ts.net` origin. The
origin extends the existing browser CSRF allowlist by exactly one private
value; loopback remains allowed and arbitrary origins remain denied.

The active release is an atomic `/opt/quantmesh/current` symlink. Activation
must restart systemd and verify the exact commit through loopback health. A
failed update restores the previous release; an explicit rollback uses the
same identity and health checks. Runtime data remains under
`/var/lib/quantmesh/demo` and is not versioned with releases.

Paper/demo mode is mandatory. This staging boundary grants no provider,
broker, wallet, model, Scheduler, testnet, mainnet or live-order authority.

## Consequences

- The operator can test the packaged SPA and bounded demo writes from Windows
  without exposing QuantMesh on the public Internet.
- Tailscale is a host adapter, not a Python or frontend dependency. Removing
  it leaves the application reachable only from the host itself.
- The service is single-instance and has no uptime, backup, multi-user or
  disaster-recovery claim.
- Lightsail remains paid-capable even during a trial. Resource creation,
  budget notification subscription and device authorization are explicit
  operator actions.
- A future public, shared or live-execution service requires a new ADR and
  threat model rather than an extension of this exception.

## Rollback

Deactivate Tailscale Serve, delete the Lightsail instance after preserving any
deliberately retained evidence, and remove the staging-only deployment files
from a future release. Local mode remains the default and carries no staging
identity or origin.
