# Option A private deployment review and recovery handoff

Current resource checkpoint: the operator explicitly approves the independent
$44/month quantmesh-research-8gb, retaining the existing8GB application and2GB
rollback. Actual Lightsail creation returns Running, Ubuntu24.04/SingaporeZoneA/
8GB/2vCPU/160GB. Default HTTP is removed; SSH limited to Lightsail browser only
for private onboarding. Compute subtotal is$100/month before taxes/model/backups/
overage. No snapshot/model/storage add-on is purchased. Tailnet and production
PG/Worker/Agent acceptance are separate; resource creation does not enable them.
The user completes new-host first Tailnet authentication. Own sanitized
Running/online status and fresh private SSH uname exit0/x86_64 verify onboarding;
official Tailscale1.104.1 uses accept-routes/accept-dns false. This permits actual
host preparation, not activation of unqualified Workers or research services.

Status2026-10-13 Singapore: the approved compute resource is created; runtime,
production service and recovery acceptance remain pending. This implements the review
preparation in [Task4](../superpowers/plans/2026-10-12-research-workers-workstation.md),
not production deployment acceptance. Finish actual runtime/image qualification
and the final milestone PR/human gates
before enabling any service. Formal168h stays not required/on-demand.

## Resources and bill

Proposed new host name: quantmesh-research-8gb, Singapore/ap-southeast-1,
Ubuntu24.04 x86_64, General Purpose8GB/2vCPU/160GB SSD. This is a new research
host separate from existing quantmesh-staging-8gb. The public-IPv4 bundle's
list price is $44/month; its address does not authorize public application
ingress. Price checked against [official Lightsail pricing](https://aws.amazon.com/lightsail/pricing/).

| Incremental allocation | Monthly ceiling inside Option A |
| --- | ---: |
| One research host | $44 |
| Dedicated PostgreSQL on that host | Included in compute |
| Encrypted off-host backups/small immutable artifacts | $10 estimate, not a provider quote |
| Approved model calls | $50 allowance, not committed spend |
| Total planned allocation | $104 |
| Unallocated operating headroom up to approved ceiling | $16 |

The $120/month ceiling and $200 development API allowance are the already
selected portfolio envelope, not permission to create unspecified resources.
Taxes, existing staging/retained rollback, paid data and overage stay separately
identified. No managed HA database, second research host, GPU, load balancer,
public SaaS, domain purchase or paid data entitlement is added here.

Actual read-only staging SSH intake at2026-10-12T21:31:06Z finds Linux/x86_64,
CPython3.12.3,2visible CPUs,8003864KiB total/3128128KiB available memory and
142649958400bytes free on the measured filesystem. Candidate OpenD/profile,
Docker CLI and pg_dump are absent at their checked paths. This single resource
snapshot is not a workload or uptime certificate. Preserve staging and its
historical rollback; do not absorb research jobs into it to bypass new-host review.

## Immutable release package before approval

The final release receipt must contain merged Git SHA/full tree, exact source
and imported module hashes, CPython/runtime fingerprints, the81-wheel Linux
lock07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a,
license closure and actual core/separate-service CI results. Host source and
container execution fingerprints remain distinct from the two-file strategy
implementation digest. The executing OCI image is not qualified yet; an image
tag, Windows result or the current local SQL receipt cannot fill that field.

Require native aggregate memory/CPU/PID/network/mount/owner-loss/sibling
proof and Linux Worker integration/two-job recovery before starting Workers.
Keep two shared active leases,60s lease/15s heartbeat and original job caps.
The API bootstrap is fixed loopback8110/one worker. Tailnet HTTPS ingress is
explicitly configured only on the new host; PostgreSQL is private local and
no database/control/OpenD port is opened publicly. Configure and measure host
API/DB/backup memory budgets alongside two2048MiB attempts; a2vCPU host does not
promise additional parallel capacity. Measure submission p95 at the declared
two-job load rather than deriving it from quota flags.

Production PostgreSQL18.6 needs a separately verified production build/package
and required TLS/backup configuration. The local owned C/UTF8 build without
TLS/ICU/readline/zlib proves SQL semantics only and is not its production image.
The server configuration fixes identity, source/build and owned roots; it
does not auto-discover local lakes, credentials, providers or model endpoints.

## Human setup, kept out of chat

Announce the exact new host/bucket/monthly allocation before resource creation.
The human approves the resource bill and private tailnet onboarding. Configure
the dedicated DB role, API bearer and0600 secret files through private server
setup; never return their contents in chat, logs, screenshots or release files.
Provider/base URL/model/price version and report-only data egress need explicit
approval before AI key installation; the human places that key directly in the
server secret mechanism. Missing metadata/key keeps analysis unavailable.

For the separate server market source, preserve reviewed Windows resources.
Use the pinned10.10.7008 OpenD candidate on staging loopback11112 only after
its profile/private input/lifecycle and human gates are accepted. The actual
host snapshot confirms it is not installed. [Vendor CLI documentation](https://openapi.moomoo.com/moomoo-api-doc/en/opend/opend-cmd.html)
describes interactive login from10.10 and a remember-password choice: select
no, keep AutoLogin/auto-grab off. [Vendor terminal-rights guidance](https://openapi.moomoo.com/moomoo-api-doc/en/qa/opend.html)
confirms concurrent sessions can compete for the highest quote authority.
Announce a human authentication/rights-transfer window after private terminal
privacy is qualified; no assistant terminal captures account/password input.
Only actual server process/socket/source/app/browser receipts permit cutover.

## Off-host consistency and restore requirement

Proposed removable backup tool: external restic0.19.1, BSD-2-Clause, not embedded
or installed. Its [official release](https://github.com/restic/restic/releases/tag/v0.19.1)
reports linux_amd64.bz2 size10107515/SHA256
f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c.
Actual binary download, signature/dependency audit and owned test still precede
admission. [Restic documentation](https://restic.readthedocs.io/en/stable/030_preparing_a_new_repo.html)
supports an S3 repository and a password file; the recovery password must also
be held in the human's separate private vault, outside this host/repository.
No repository/storage credentials or keys appear in backup command logs.

Use a new private Singapore S3 backup prefix with public access blocked,
client-encrypted payloads and the reviewed storage budget. First prove local
encrypted backup/restore on owned resources; actual off-host proof then uses
only the specifically approved new bucket/prefix. No global retention deletion
or removal of existing resources is implied. Retention/pruning waits until
at least one checked recovery exists and the exact snapshot scope is approved.

The coordinator's consistency rule: dump the dedicated research schema from
one database snapshot, then capture immutable artifact bytes referenced by
that snapshot plus their SHA/size manifest. Verify every reference exists
before publishing the encrypted backup receipt. A filesystem copy of the live
PostgreSQL data directory is not this backup. [Official pg_dump documentation](https://www.postgresql.org/docs/18/app-pgdump.html)
describes consistent exports; this cross-store manifest rule is our design,
not a claim that pg_dump snapshots the artifact filesystem.

Restore only to a fresh isolated DB/artifact target, with a new private role,
never overwriting production. Validate schema/protocol version, accepted
job/request/idempotency identity, every published report/analysis byte hash,
effect reservations and unknown-effect state. Run API reopen/cancel/replay and
the actual qualified Worker recovery check. Reopening an old analysis must
not recall a completed/ambiguous paid effect. Record restored snapshot, target
identity, observed durations and all failed attempts; retain the primary.

## Release and acceptance order

1. Finish independent bootstrap and source-tool reviews/integration; qualify
   native Engine/image/Worker and model boundaries without production changes.
2. Complete exact final-tree CI/clean-checkout and applicable human reviews.
   Record explicit runtime/image/DB/backup pins and operator resource approval.
3. Create only the approved research host/backup scope; configure private
   secrets/ingress; deploy exact merged code. Do not redeploy charts for docs.
4. Prove genuine submit/report/reload/cancel, actual two-job recovery≤90s,
   p95, timeout, Agent failure isolation/budget exhaustion and off-host restore.
   Scripted fixtures do not certify a real model/provider call.
5. Independently authenticate/qualify the server-owned gateway, preserve old
   endpoint as rollback, and witness real open-session stock/crypto/browser
   behavior before declaring PC independence. Closed latest-session coverage
   is normal, but does not replace minute-revision/two-boundary evidence.
6. Obtain operator foundation acceptance before strategy-family/custom-DSL
   trials. Record deployed/accepted/deferred states separately; no whole-product
   HA/live-money/168h claim or implicit production downgrade on a failed drill.
