# Lightsail 8 GB upgrade preparation

Status: next-stage capacity choice recorded on 2026-09-18 at the operator's
request. Preparation only; no instance purchase, migration or deployment has
been performed by this documentation task. Related work: [#135](https://github.com/ZP151/quantmesh/issues/135),
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
