# Lightsail 8 GB upgrade preparation

Status: capacity choice recorded on 2026-09-18; the operator created the 8 GB
instance and authorized setup on 2026-09-22. Setup and migration evidence
below supersedes the historical form-preparation status. Sustained capacity
acceptance and old-instance retirement remain separate gates.
Related work: [#135](https://github.com/ZP151/quantmesh/issues/135),
[#157](https://github.com/ZP151/quantmesh/issues/157) / [PR #158](https://github.com/ZP151/quantmesh/pull/158),
and [iteration 0036](../iterations/0036-staging-recovery.md).

## Selected next-stage capacity

Prepare an **8 GB RAM / 2 vCPU / 160 GB SSD Linux General Purpose Dual-stack
Lightsail instance in Singapore**. Dual-stack means IPv4 plus IPv6; it does
not mean two CPUs or public application access. Retain the private,
single-operator boundary.

The 2026-09-18 published price is **USD 44/month, USD 528/year** before tax,
credits, snapshots and transfer overage, versus USD 12/month for the existing
2 GB bundle: a USD 32/month (USD 384/year) base increase. The target includes
5 TB monthly transfer. Recheck the actual account offer and checkout price at
execution. A planning example of 20–100 GB of billable snapshots adds USD 1–5
per month; USD 45–49/month is an example budget, not a bill or spending cap.
[AWS pricing](https://aws.amazon.com/lightsail/pricing/)

RAM increases fourfold, but the two-vCPU sustained baseline rises only from
20% to 30% per vCPU: roughly 0.4 to 0.6 full-vCPU equivalents, or **50% more
sustained CPU budget**. This is not a throughput guarantee. The 4 GB bundle
has the same CPU baseline as 2 GB and is not the selected next-stage target.
[AWS CPU baseline](https://docs.aws.amazon.com/lightsail/latest/userguide/baseline-cpu-performance.html)

## Evidence and concepts to retain

- Historical read-only sample, **2026-09-17 21:01–21:05 SGT**, on `76203e0`:
  1906 MiB RAM, initially 357 MiB available, about 1 GiB swap occupied,
  a roughly 3.7 GiB live lake, and 47 GiB free on the root filesystem.
  Two loopback health requests timed out at 15.022 and 8.002 seconds.
- Kernel logs showed earlier QuantMesh OOM kills at 18:16:53, 18:17:21 and
  18:17:45 UTC on September 16, before the sampled service start. A later
  30-second sample had sustained swap-in, intermittent swap-out, 17–37%
  iowait and 48–66% steal. These are dated observations, not today's status.
- Swap occupancy alone is not proof of current memory pressure. Combine
  available RAM, `vmstat` si/so, pressure, OOM and latency. Memory pressure can
  increase disk traffic and response times; this sample does not isolate the
  full causal contribution. High steal alone does not prove exhausted burst
  capacity. Account metrics and the actual bill were unavailable because the
  AWS console session had expired.
- CPU, memory and I/O interact. More disk space or more swap does not replace
  RAM; more RAM does not remove unbounded query or maintenance work. A smoke
  pass establishes a bounded observation, not sustained capacity or an SLA.
- Size by ingestion rate, stream/depth count, retained volume, simultaneous
  chart queries, maintenance peaks and CPU/memory per research job. Do not
  promise a user count or multiply capacity by the RAM ratio.

## Dependencies and next-stage handoff

Earlier preparation check on 2026-09-18: retention [PR #155](https://github.com/ZP151/quantmesh/pull/155)
merged as `ab90f92`; [#157](https://github.com/ZP151/quantmesh/issues/157) reports
that this release still hit DuckDB OOM in `LiveBuffer.latest()` on the retained
lake. PR #158 was open for bounded latest-state startup. These are GitHub
records, not a fresh verification of the currently deployed build. An 8 GB
upgrade complements the fix and must not be used to close that defect by
masking its unbounded query.

- [ ] Re-read #157/#158, CI, current AWS build and retention settings; select
  one reviewed, merged exact SHA. Do not combine the migration with new feeds.
- [ ] Record current CPU burst balance/trend, memory/swap activity, disk/WAL,
  lake size, health and chart timings, actual billing and a migration window.
- [ ] Prepare the concrete infrastructure change, cost and rollback checklist
  under the [Class C policy](../agents/review-policy.md). The present choice
  authorizes preparation; it is not evidence that migration has been executed.
- [ ] Plan a writer-quiesced, recoverable snapshot/backup and restore check.
  Avoid treating an unverified copy of an actively written DuckDB file as a
  valid backup. Preserve data and rollback releases.
- [ ] Plan the new instance's independent Tailscale identity, canonical private
  origin and cutover. Do not boot a cloned active collector with a duplicated
  node identity. Check IPv4 and IPv6 firewall paths; keep loopback/Serve,
  paper mode and disabled live trading. Existing #135 firewall follow-up stays
  open and needs an explicit disposition in the migration review.
- [ ] After migration, verify exact build, private health and live smoke,
  BTC/ETH/SOL charts from both entry paths, advancing source times and reload
  retention. Exercise restart and a real expired-row sweep on representative
  lake volume, using a controlled isolated fixture if needed to avoid changing
  production timestamps or retention solely to manufacture expiry.
- [ ] Record at least 24 hours of comparable observations: no OOM, no repeated
  health timeout or prolonged swapping, and CPU burst capacity not trending
  toward exhaustion. Record maintenance duration/peak memory and graph
  latency/freshness; a short green smoke cannot close this gate.
- [ ] Demonstrate rollback before deciding when to retire the old instance.
  Budget for temporary overlap and snapshots: stopped ordinary Lightsail
  instances still accrue charges. Do not delete the rollback source as part
  of preparation.

The supported snapshot expansion path creates a new larger instance, and
cannot directly restore to a smaller bundle. References:
[AWS expansion](https://docs.aws.amazon.com/lightsail/latest/userguide/how-to-create-larger-instance-from-snapshot-using-console.html),
[billing](https://docs.aws.amazon.com/lightsail/latest/userguide/amazon-lightsail-frequently-asked-questions-faq-billing-and-account-management.html).
This is a preparation checklist, not an executable deployment authorization
or a replacement for the existing release runbook.

## Later expansion triggers

After capacity acceptance, resume [#156 AAPL/NVDA readiness](https://github.com/ZP151/quantmesh/issues/156)
with its existing entitlement/private-route gates. Keep heavy research jobs
separate from latency-sensitive ingestion and chart serving when measurements
justify a worker boundary. Consider partitioned Parquet/object storage for
long history, with an explicit retention and recovery policy.

If memory pressure is resolved but sustained CPU remains above the 8 GB
baseline and burst capacity repeatedly depletes, compare a worker split,
compute-oriented instances and the 16 GB / 4 vCPU bundle. Multi-user state,
queues, PostgreSQL/RDS, load balancing and high availability need separate
requirements and architecture decisions; none is adopted or purchased here.

## Creation form prepared — 2026-09-18, approximately 00:45 SGT

The operator asked to continue through the final purchase-confirmation screen.
The existing AWS Lightsail create form was filled and the enabled **Create
instance** button was left unclicked. No chargeable resource was created.

| Field | Prepared value |
| --- | --- |
| Name / quantity | `quantmesh-staging-8gb` / one |
| Region / zone | Singapore, `ap-southeast-1a` |
| Image | Linux operating system, Ubuntu 24.04 LTS (clean image) |
| Plan / network | General purpose / Dual-stack |
| Bundle | 8 GB RAM, 2 vCPU, 160 GB SSD, 5 TB transfer |
| Displayed price | USD 44/month before applicable tax and extras |
| SSH key | Existing regional Default SSH key; no new key created or exported |
| Tags | `Project=QuantMesh`, `Environment=staging` |
| Automatic snapshots | Disabled in this form; migration backup is a separate gate |
| Launch script | None; no unattended collector start or embedded credentials |

The clean-image route intentionally avoids cloning the existing Tailscale
identity and an automatically started collector. It replaces the earlier
snapshot-expansion option for this prepared order; validated application data
must be restored separately. The old instance and its data remain untouched.
If both instances are retained for a full month, their base total is USD 56
before tax/credits/extras, not USD 44. Merely stopping the old one does not
eliminate its instance charge.

### Runtime configuration handoff (prepared, not applied)

- Establish independent Tailscale device `quantmesh-staging-8gb` and derive
  its canonical private HTTPS origin from the new device's actual DNS name.
  Do not copy the old host's Tailscale state or assume a tailnet suffix.
- Inspect both Lightsail firewall families immediately after creation. The
  create form does not expose firewall configuration, and default public
  rules must not be described as hardened. Scope temporary bootstrap SSH,
  remove unnecessary public application access and complete private SSH/Serve
  verification before removing the bootstrap route. No Funnel or public
  application listener is part of the target.
- Use the repository's unprivileged `quantmesh` systemd profile, loopback
  `127.0.0.1:8765`, `/opt/quantmesh/releases/<exact SHA>` and writable
  `/var/lib/quantmesh`. Apply the actual new canonical origin; retain
  `paper_mode=true`, `live_trading=false`, and the reviewed seven-day retention
  default unless separately changed. No new symbols or OpenD exposure.
- Install and health-check the selected exact merged release before cutover.
  Quiesce the old writer during the agreed migration window; preserve a
  recoverable, verified copy of the complete application data set, including
  the live lake, paper/orders and decisions. Verify restore before allowing
  the new collector to become authoritative. Never claim that a raw copy of
  an actively written database proves consistency.
- Retain the old host and data for rollback; switch the private operator URL
  only after exact-build, source freshness, replay/reload and safety checks.
  Follow the representative sweep/restart and 24-hour gates above. No budget
  notifications, new backups or deletions were enabled by form preparation.

Latest dependency check: PR #158 merged as
`33aa0521da8305001e0bd62b377c53738c85e11d`, with its reported Python CI check
passing. At **2026-09-17 16:42:22 UTC**, the old host's release symlink pointed
to this SHA, systemd was active with `NRestarts=1`, but loopback TCP/8765 refused
the health request. Therefore this is a candidate release, not a freshly
accepted runtime or a proven rollback witness. No restart, repair or deployment
was attempted during order preparation; recheck before proceeding with data
migration. The form readiness does not close the Class C migration review gate.

## Operator-created instance checkpoint — 2026-09-22

The operator reported creating `quantmesh-staging-8gb`; the AWS console
confirmed Running, Ubuntu 24.04 LTS, Singapore Zone A and the selected 8 GB
bundle. Browser SSH confirmed cloud-init done, 7,816 MiB physical memory,
7,321 MiB available, no configured swap and 152 GiB free on the root volume.
These are idle-host measurements, not application capacity acceptance.

The default public HTTP rule was removed. The unrestricted IPv4 and IPv6
SSH sources were removed, leaving only AWS Lightsail browser SSH over IPv4
as a temporary bootstrap route. The console confirmed the rule update and
displayed only SSH/TCP 22 with "Lightsail browser SSH only". No public
application listener, static IP, snapshot or load balancer was added.

Official Tailscale installation completed with version 1.102.4. A fresh
device identity named `quantmesh-staging-8gb` awaits operator login and
authorization; no authentication URL or credential is retained here. The
canonical private origin, private SSH and Serve are not yet verified.
OS deployment prerequisites (CA certificates, curl, git, Python and venv)
completed successfully in a fresh browser SSH session after hardening.
No application was started or data migrated on the new host.

A fresh read-only old-host probe initially required Tailscale SSH's additional
authentication check, which subsequently passed. At 15:31:15 UTC the old
host reported exact build `33aa0521da8305001e0bd62b377c53738c85e11d`, healthy
live-data mode, paper true and live trading false. Systemd was running with
one restart, 797,884,416 bytes current service memory, 984 MiB available RAM
and 1,343 MiB swap used out of 2,047 MiB. A privileged directory-size check
reported 4.2 GiB live data; root had 46 GiB free. Serve remained tailnet-only
and proxied to loopback port 8765. This is a point-in-time health witness,
not chart freshness, restart or rollback acceptance. The old instance and
its data remain the migration source. This checkpoint records setup evidence and does
not close the Class C migration review or the 24-hour capacity gate.

## Private configuration and data restore — 2026-09-22

After the operator completed device authorization, private SSH verified the
new hostname and its actual canonical origin:
`https://quantmesh-staging-8gb.tail99d23c.ts.net`. The remaining temporary
AWS browser SSH rule was removed; the console showed **No firewall rules**,
and a new Tailscale SSH connection still succeeded.

The existing bootstrap installed exact merged build
`33aa0521da8305001e0bd62b377c53738c85e11d` as unprivileged `quantmesh`, with
systemd enabled and application TCP/8765 bound only to loopback. Initial demo
health passed with exact identity, paper true and live trading false. Private
Serve proxied to loopback. Its first HTTPS probe timed out while ACME was
issuing the new hostname's certificate; after issuance a verified HTTPS GET
returned 200 in 0.429 seconds. No certificate verification bypass was used.

The new demo service was stopped. Its canonical demo environment and seeded
data were preserved separately. The existing deployment helper generated
the canonical live-data profile for the same build and new origin, retaining
BTC/ETH/SOL, paper safety and default retention. This is an explicit profile
selection for the new host, not a changed application commit.

Old-host shutdown started at 15:39:43 UTC. Uvicorn waited for background tasks
past the configured 90-second stop limit, so systemd killed the process at
15:41:13; MainPID became zero. This is an unresolved graceful-shutdown defect,
not a clean exit witness. The complete stopped `/var/lib/quantmesh`, including
the live DuckDB WAL, demo state, orders and decisions, was archived and compared
byte-for-byte to the stopped source before restoration.

Archive size: **4,434,759,680 bytes**. Source and destination SHA-256:
`1e5b3c5e0acdd3539afd1825f82e744a45a66f02197a3e70cbc8fca9760adbcc`.
The initial laptop-relayed transfer was interrupted and its partial file was
not used. The complete copy was transferred directly between the existing
Tailscale devices after normal SSH session reauthentication. Backups are on
instance disks in root-only directories; no paid snapshot resource was created.

### Bounded acceptance completed — 2026-09-23, approximately 00:02 SGT

- Restore matched the verified archive before opening the database. WAL
  recovery and checkpoint succeeded; all 6,535,216 market records were readable,
  all payloads were valid JSON, and BTC/ETH/SOL were present. Verification took
  39.685 seconds. Full archives remain on both hosts, including expired rows.
- The archive's latest receipt was September 17 at 19:45:23 UTC (September 18
  at 03:45 SGT), despite the old process's healthy endpoint. Current observations
  resumed on September 22 at about 15:53 UTC. The intervening collection gap is
  preserved honestly; the application displays continuity-checked recent replay.
- New live startup completed in approximately 58 seconds on the representative
  lake. Normal startup retention reduced the live extent to about 2.84 million
  rows while preserving the complete pre-migration archive. Service memory peak
  was 3,311,214,592 bytes (3.08 GiB), with no swap and no automatic restart.
- The 13-check read-only smoke passed in 0.4 seconds. Sixty-three samples over
  324.56 seconds retained exact build, live-data mode, paper true and live
  trading false. Max health latency was 0.187 seconds, max state latency 0.209
  seconds, and max quote age 2,149 ms. All three current source timestamps
  advanced. Their recorded minute coverage grew from two rows to eight. This
  observation crossed the first scheduled five-minute sweep boundary with no
  service errors; it does not independently instrument sweep duration.
- Both Markets and Watchlist opened all three 1D/Line workspaces. Visible
  provenance was real, stream transport reached WebSocket, and current charts
  rendered. SOL reload retained its observed minutes. One browser accessibility
  read timed out; subsequent screenshot/navigation and the simultaneous API
  measurements succeeded. These are bounded checks, not the full prior paired
  ten-minute browser benchmark.
- After closing the browser's live connection, a controlled service restart
  exited gracefully and returned exact healthy live mode in 16 seconds. The
  post-restart smoke passed all 13 checks in 0.5 seconds, with zero automatic
  restarts. This does not establish the cause of the old shutdown timeout.
- The new unit is enabled. The old unit has MainPID zero and is disabled to
  avoid automatically restarting a second collector. The old AWS instance,
  release, source data and verified backup remain; no instance was deleted.
  The interrupted relay file on the new host is explicitly named
  `migration-20260922.partial.tar` and must not be used for recovery. The
  validated new-host archive is `migration-20260922.direct.tar` under
  `/var/backups/quantmesh`; the old host retains `migration-20260922.tar` there.

Local detailed evidence is in the task's ignored
`output/lightsail-8gb-migration/` directory: restore verification, archive
checkpoint, five-minute observations and final health. The durable facts above
are mirrored in iteration 0036. No application source or deployment helper was
changed by this setup. The evidence PR is not a substitute for formal Class C
review or operator acceptance of retirement.

### Remaining capacity and rollback boundaries

The short observation does not close the 24-hour stability/CPU-burst gate.
There has been no full old-host rollback drill after new ingestion began, and
no host reboot test; service enablement and a process restart are verified.
For rollback, stop the new collector first, preserve its later observations,
then re-enable/start the retained old service and verify exact health,
paper safety, current source times and the old private URL. Its retained data
ends before new-host ingestion, so a rollback cannot silently discard that
new interval. Do not delete either source merely because short smoke is green.

Base overlap remains USD 56/month (44 new plus 12 old), before tax, credits
and extras. Stopping the old application does not stop instance billing.
Old-host stale ingestion and the 90-second shutdown timeout remain follow-ups;
this migration does not claim to fix their underlying causes.
