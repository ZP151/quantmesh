# iteration0038: first server report delivery contract

Issues [#172](https://github.com/ZP151/quantmesh/issues/172),
[#171](https://github.com/ZP151/quantmesh/issues/171), PR175. Integration owner:
root. Frozen on2026-10-15 Singapore; this contract changes delivery order, not
the full Option A goal, approved isolation or release authority.

## One-page contract

**User action/outcome:** choose registered momentum1 and the existing licensed
equities fixture in `/research/jobs`; submit once; obtain one cost-aware report;
restart the private research API/Worker supervisor and reopen the same job/ref.
Reuse existing fixture, engine, PostgresJobStore, artifact and page implementations.
**Current availability:** local fixture/page/recovery exists. No successful
research-server compute/report/reopen user loop is yet proven. This is a target
contract, not a claim that the commands below are deployed or currently pass.

| Boundary | Frozen value / actual readiness |
| --- | --- |
| Hosts | Existing research8GB at ubuntu@quantmesh-research-8gb.tail99d23c.ts.net; existing application8GB and rollback2GB retained. No new paid resource. |
| Source | Foundation PR175 head370a745caeee0d5d60d41b4eb4716316cb44b935; corrected image source e34d22f4576efdab06d11aec5ae04f135078fdc6. Old41214ff preparation retained. Freeze a new exact SHA if code changes; deploy only a reviewed merged tree. |
| Numerical runtime | Linuxamd64, actual CPython3.12.15 `/usr/local/bin/python3`, prefix/usr/local. Corrected imagea0abb2dc5cbdc53fe6422ea3cebb353e0784c235cce2e691bf516eb808a2db76, raw OCI config7c78d2608e9e9d425bae5aa41d81fa227cee6d9b57183b71ac668b7a593786c4.81-wheel lock07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a. Complete source-only preflight passes; numerical admission remains pending. |
| Services/identity | Private authenticated Research API loopback8110, Ubuntu UID/GID1000; PostgreSQL18.6 dedicated DB/role/schema qm_research with TLS/SCRAM. Registered Worker UID/GID10001 in private PID/IPC/cgroup namespaces. For the bounded operator qualification, trusted parent may use already authorized sudo; no general root daemon is installed. Persistent supervision requires its reviewed release checklist. |
| Configuration placement | Target `/home/ubuntu/qm-research/{config,credentials,lake,artifacts,attempts}`; directories0700. Named private files api_token/postgres_dsn0600, explicit runtime.json0600; no key/DSN in argv, reports, browser or prompts. These target files/services are not asserted installed. Model key/config is optional and separate. |
| Dataset/request | Existing tests.research_fixtures.pinned_lake: equities, AAA/BBB/CCC,60×1h bars each, source=fixture/license=test. First request momentum1/AAA, train10/test5/step5, fee1+halfspread2+slippage3bps. DatasetRef revision/manifest/export SHA measured on actual server bytes; never invent a pin or call it real market evidence. analysis_requested=false, model budgets0. |
| Control/entry | Full controller and child argv below; parent delivers expected binding SHA over owned ready/go channel after actual CID creation. Child stdin DEVNULL. Binding schema1/15fields, actual Engine/image/config/CID/nonce, source/lock/interpreter digests. Historical policy hashes do not constitute current kernel admission. |
| Mount/ownership | Separate RO /inputs and RW /output, both task-only/nonoverlapping; files0400, input nested directories0500, root0700; output0700. Fixed source/interpreter/library closure, readonly root, no network/caps/privilege, actual noexec task mounts and enforcing policy before numerical work. Parent metadata handoff must pass on actual different-UID target; no chmod-all fallback. |
| Job/fence | Frozen9-method JobStore/public4-argument run_next_job; attempt monotonic, lease60s, heartbeat15s, live fence/pulse1s, shared global concurrency2. First small job timeout90s/memory768MiB/CPU1/PID128; existing schema permits at most900s/2048MiB/CPU1. Cancelling, expired/stale/reclaimed owner cannot publish success. |
| Report | Version1 canonical request/result/envelope; exact implementation/source/runtime lineage and6bps costs. SHA-addressed ArtifactRef, byte_size<=16MiB, object_key job_id/SHA.json. created_at stays receipt metadata. One successful job owns one immutable report; reopen same bytes/ref after restart. |
| Interfaces | Service /v1/options, POST /v1/jobs with Idempotency-Key, GET job/artifact, cancel; workstation /api/research/* facade and existing /research/jobs page. Operator identity/token fixed by backend configuration, not submitted JSON. Cross-process examples below. |
| Failure | Same key/same request replays, changed request409; bad fixture422, artifact mismatch409, unavailable SQL/service503; timeout/cancel/worker_failure terminal and sanitized. Agent unavailable/failed never invalidates baseline success. |
| Acceptance | Actual server submit→PG→isolated Worker→stored report→page→API/Worker restart→same job/ref/SHA. Technical smoke is not release/native admission. Exact-head CI, Class C two human reviews including safety owner, paper regression and explicit acceptance remain. No admin merge or candidate deployment. |

## Real interface examples and acceptance commands

The following use existing interfaces, fixed target paths and a server-generated
private request; they do not imply those files or services currently exist.

```sh
# Explicit service preflight, then serve only after its own admission succeeds.
/home/ubuntu/qm-research/venv/bin/python -B -m qm_research_agent --config /home/ubuntu/qm-research/config/runtime.json
/home/ubuntu/qm-research/venv/bin/python -B -m qm_research_agent --config /home/ubuntu/qm-research/config/runtime.json --serve
# curl config supplies a PRIVATE bearer header; never put its value on argv.
curl --fail --silent --config /home/ubuntu/qm-research/credentials/curl-api.conf http://127.0.0.1:8110/v1/options
curl --fail --silent --config /home/ubuntu/qm-research/credentials/curl-api.conf -H 'Content-Type: application/json' -H 'Idempotency-Key: server-baseline-v1' --data-binary @/home/ubuntu/qm-research/config/request.json http://127.0.0.1:8110/v1/jobs
```

Actual returned job_id and report artifact_id determine subsequent GET paths;
the integration verifier reads them from JSON, re-fetches the exact API bytes,
checks SHA/ref/numerical contents and repeats after owned service restart.
Never manufacture IDs or mark queued/cancelled-only persistence as a report.
Workstation constructor is `create_workstation_app(account=PaperAccount(cash=100000), research_jobs_client=client)` for the isolated paper-only demo;
`client=ResearchServiceClient(endpoint=private_endpoint, allowed_endpoints=(private_endpoint,), operator_id="operator", token=private_secret)`.
The service's existing `PostgresJobStore(SecretStr(named_private_dsn),
lake_root=lake, artifact_root=artifacts)` is also the Worker owner store.
These construction values cannot come from a job body or arbitrary plugin.

```python
# One existing registered Worker call inside its independent admitted context.
runner = WorkerRunner(execution=LinuxWorkerExecution(profile, admission))
runner.run_next_job(store, "server-baseline-v1", inputs_root, artifacts_root)
```

`admission` is the missing concrete trusted provider; a saved receipt/boolean or
test mock cannot fill it. Its implementation is part of this slice, not a new
proof project. The exact current launch contract is:

```text
Entrypoint: /usr/local/bin/python3
Controller argv: -B -I /opt/quantmesh/linux_bootstrap.py 768 90 /usr/local/bin/python3 -B -I -S /opt/quantmesh/worker_entry.py --binding /inputs/parent-binding.json --manifest /opt/quantmesh/manifest.json --inventory /opt/quantmesh/inventory.json
Child argv after trusted go SHA: /usr/local/bin/python3 -B -I -S /opt/quantmesh/worker_entry.py --binding /inputs/parent-binding.json --manifest /opt/quantmesh/manifest.json --inventory /opt/quantmesh/inventory.json --binding-sha256 PARENT_DELIVERED_SHA256
```

The uppercase final token is protocol data produced from actual parent bytes,
not a literal accepted CLI placeholder. Existing construction interfaces remain
unchanged; verify actual command, UID/mounts and legal dependencies early.

## Priority, timebox and stop conditions

| Slice | Deliverable / root acceptance | Target / stop |
| --- | --- | --- |
| 1, current | Real research-server deterministic report and same job/ref after API/Worker restart; reuse local UI/math/fixture/PG components. |24–48h from this contract; first real thin-call attempt now. Stop and record precise architecture blockage after2 structural reviews or timebox without demo. |
| 2 | Existing60s lease/15s heartbeat/global2 crash exit23, cancellation/reclaim attempt2, report reopen<=90s; SQL/backup recovery. |Next24–48h slice after1; actual fencing/cancel proof required. |
| 3 | Server-owned OpenD + existing other provider, entitlement/session freshness, PC-independent route; preserve old route until acceptance. |Independent24–48h slice after frozen data contract; human vendor login only if actually required. |
| 4 | Optional real OpenAI advisory analysis and combined Eval over immutable published report, budget/citation/unknown-effect fences. |24–48h slice after report; missing key/Agent never blocks1–3. Confirm model/price and secret setup before paid calls. |

Parallel work only after interfaces freeze and files do not conflict. Root first
resolves the connected thin path; no repeated full reviews, broad local hourly
suite or CI restart. A new failure/change justifies its affected checks; run the
required broad gate at coherent slice/final PR boundaries with bounded waiting.

Risk is once explicit: trusted registered baseline plus fixed licensed fixture
is the current action. Arbitrary user Python/plugins/SQL and live orders are
excluded. Existing isolation, source, license, sealed Reader and publication
gates remain. Any NEW native/kernel/architecture prerequisite must state the
specific risk, why it blocks this action, added effort and acceptance impact,
then obtain its applicable architectural decision. No third proof alternative
or stopped object-graph WIP revival. Formal168h stays NOT_REQUIRED.

## Latest factual blocking evidence

On actual image7c3a/configb5e9 the finite source-only probe first refused legal
IpcMode=private before start. Root reproduced/fixed that enum and verified exact
never-started CID cleanup. The corrected probe then created/started its owned
container, but the first result did not arrive within40s: zero stdout/stderr,
no accepted cases. It exits1 and removes its owned CID; final4images/0containers.
Do not infer whether the pause is GO delivery or source measurement without
stage evidence. This is the primary next integration obstruction, not a passed
preflight. Missing concrete image/parent provider and current production
profile's rejection of inherited public GPG_KEY remain explicitly recorded
integration work; no source/cache/native gate is waived by this contract.

Evidence index: output/0038-worker-source-image/source-preflight*.json,
private-namespace-red/green.log/.exit, failed-preflight-cleanup.stdout,
source-preflight-failure-details.stdout. Prepared image/source successes stay
valid; this contract does not redo PR163/164/166, staging deployment or old CI.

Subsequent bounded evidence closes that diagnostic question: GO is received,
preflight enters within3.3s, and one10s stack lands in the repeated full-inventory
membership conversion. Root's minimal linear-work correction keeps identical
Path semantics and all full byte checks; RED3/GREEN3/affected104 and narrow
correctness review pass. Source correction allocation is now8MB within unchanged
cumulative129MB/original5GB, carrying old packets/failures and1,132,924B new
Linux fixtures; measure the new packet before dispatch. Rebuild only this
affected committed source against the frozen base/lock, then continue the same
thin call. No broader environment/kernel proof, extra fee or release approval.

Completed correction checkpoint: actual imagea0abb2dc/sourcee34d22f full public
source preflight passes all5cases6.913s and exact owned cleanup. Independent
saved request/bytes/OCI checker plus fresh Engine read confirm5images/0containers;
original emitted constant4 count is retained with erratum and reporterRED/GREEN.
Do not repeat this phase. Current primary path is concrete parent/Worker→private
PG→persistent report/page/reopen; no numerical/user-loop success is inferred.
Source accounting forecast7,843,566B<=8MB/cumulative122,022,633B<=129MB includes
all failures/new packet/native fixtures/reserves; future Worker allocation must
remain explicit within original approved resources. Whole-C attribution pending.

## Concrete parent wiring: next bounded implementation

This executes approved kernel-boundary Task2, not a new isolation architecture.
The existing LinuxExecutionProfile cannot currently request the already-built
AppArmor/seccomp policy, so a concrete parent cannot verify the required actual
security options. Add paired optional operator fields `apparmor_profile` and
`seccomp_path`; defaults preserve construction-only compatibility. New concrete
Worker admission must require both and verify current enforcing bytes/mounts;
their mere presence never grants native qualification. Profile rejects a partial
pair, unsafe profile name/path, missing/nonregular/linked seccomp file and any
unknown security option. The seccomp file is fixed private configuration, never
job JSON. Create retains NNP/caps/network/identity/budgets and appends only the
exact paired options; every inspect/recheck compares the complete requested list.

Implementer owns only linux_owned.py/test_linux_owned.py; root owns later
concrete admission/service/config/fixtures, so no parallel file conflict. RED:
configured policy options absent from create/inspect, partial/unsafe pair or
security drift must refuse. GREEN: targeted existing-env owned/execution tests.
Root verifies and one bounded correctness review, max2 rounds; no new native
proof family, source rebuild, full-suite rerun, default policy change or startup.
Software allocation4MB carries conservative123,931,604B, cumulative129MB stays;
native WSL fixture receipts, errors, source/Git/evidence/reserves remain counted.
Before actual service runtime preparation, measure reuse of the already cached
81 wheels and existing PG prefix; no download/version replacement or production
listener. One real baseline/PG/report/page/reopen remains the success criterion.

Parent-runtime preparation is necessary for that existing service contract;
the numerical child's /usr/local image is not the service's required non-root
venv. Actual fresh reuse intake verifies all81 cached wheel hashes (88,992,477B
compressed/285,093,456B expanded) and the existing PG18.6 binaries. Host CPython
3.12.3 has venv but no pip/ensurepip. Prepare one exclusive0700 runtime phase
under the existing owned numerical root: stdlib venv without pip; take public
pip25.0.1 source/metadata only from the frozen base2ed6491b via a never-started
fully identified container, then use it as transient install tooling outside
the venv. Offline `--no-index/--require-hashes/--only-binary/--no-deps/--no-compile`
installation reuses only the current hash-verified81 wheel cache and frozen lock.
No new wheel/version/download, runtime pip install, source image or daemon.
Retain bootstrap/archive/install receipts. Remove only exact never-started CID;
never delete a directory or restart on an unknown result. Verify actual installed
81 versions/RECORD bytes/license policy before any service admission.
Cloud allocation1GB forecasts this preparation including later exact checkout,
within the original whole-host5GB/free50GB floor (PG bytes remain carried);
software/evidence remains inside the current4MB/cumulative129MB. This is private
prepare-only material, not merged-tree service deployment or server-report proof.
One bounded operational recipe review precedes execution; no third structural
review of prior source/kernel work. Human release gates remain unchanged.

Actual parent preparation and candidate admission complete: private3.12.3venv
81fixedpackages, exact candidateeb880b2/treee7f6eb69 on native FS, all3,923blobs
and6,669RECORD files checked, existing _admit_runtime lock/license/source gate
exit0. No service/SQL/Worker activation. Shallow real Gitpack retained remotely;
three Git-attribute CRLF before-images and failed receipt retained, canonical
blob correction/resumption reuses same known failed phase, not another checkout.
Evidence output/0038-parent-integration/; original whole-host/parent budgets
remain carried. Root source78-pass tests/review close the paired-option leaf.

Concrete provider next boundary (existing Task2, no architecture expansion):
implement WorkerImageAdmission.verify(profile) exact five runtime fields and
prepare_parent_binding(process,job,runtime,ready) canonical15-field bytes/SHA.
Observe CURRENT actual Engine/image/raw OCI/source/lock/runtime and actual
loaded enforcing AppArmor/seccomp/noexec controls; historical policy093b receipt
alone refuses current a0abb2dc. Ready rebinds actual full CID/nonce/command/user/
mount/security options/bootstrap/cgroup before GO; expected binding SHA travels
existing trusted controller channel, never from child input. Existing exit
validation re-observes provider fingerprint/policy and stopped/noOOM/exit0.
Decisive refusals: image/config/runtime mismatch, ready CID/nonce/control drift,
and post-exit policy/runtime drift. One new bounded provider module plus tests
and frozen operator wiring, no saved-qualified Boolean/arbitrary Python.
Reuse actual unchanged ELF/runtime inputs only after rebinding current bytes;
do not launch another source proof family or re-review completed native design.
First registered numerical thin call either yields real report or a precise
architecture blocker; max2 structural reviews/timebox still governs the slice.

## Concrete admission implementation handoff

Root closes wire correction4b596e0: actual bare NNP/exact JSON payload, immutable
UTF8 capture,16KiB cap. Native tests/logs/source preserved, no Worker accepted.
Next software allocation1MB conservatively carries127,896,778B (including every
old peak/error/reserve), stays<=129MB; no new environment/full-suite or deletion.
AWS metadata/config preparation stays in the existing1GBparent/original5GB.

Implementer owns only src/quantmesh/research/worker_admission.py and
tests/test_worker_admission.py; root owns existing linux_owned/kernel activation,
operational collection/PG/report and tracked records. One provider, no additional
abstract observer/authority interface. Use existing WorkerImageAdmission methods.
Constructor takes frozen operator pins and a private source snapshot directory;
job requests cannot supply either. Snapshot is collected from a CURRENT exact
owned NEVER-started immutable-image CID: manifest/inventory plus exact installed
METADATA/RECORD/direct_url bytes needed to recompute five runtime fields. Root
binds snapshot hashes to independently expected image/OCI/manifest/inventory
pins; no saved receipt, qualified Boolean or borrowed parent-venv runtime tuple.
Full Python version is the independently measured frozen-image interpreter pin,
not the parent3.12.3 version. Current immutable interpreter/libraries/config must
rebind to it every verify; child subsequently independently measures the tuple.

Provider independently reads CURRENT actual Engine/image and raw containerd
OCI manifest/config blobs (bounded stable nofollow reads), checks their hash
relationships and exact expected source/runtime inventory. Recompute source and
dependency fingerprint from bound actual snapshot bytes using existing canonical
formula; do not accept a saved five-field tuple. Kernel authority comes from
CURRENT securityfs enforce mode/raw compiled bytes and exact configured policy
byte pins, not old actual-image-policy.json. Existing build_kernel_policy and
actual immutable ELF map/default pins remain the expected policy construction.
Before GO use exact process._inspect and ready/cgroup/bootstrap checks, actual
Engine CID/PID/start identity, host /proc/PID attr/status/mountinfo (differentUID,
NNP,seccomp,caps/noexec); encode existing15-field ParentBindingContract. Recheck
live process identity around host reads. Existing validate_exit re-runs provider
verify before publication, so policy/image/config/runtime drift refuses then.
Sanitized LinuxContainmentError only. No default activation/SQL/daemon/sudo
policy/secret/model/user-code capability; privileged operator qualification is
distinct from a persistent reviewed worker service.

TDD decisively covers real byte-hash relationships/fingerprint computation,
current Engine/OCI/policy drift, forged/changed ready CID/nonce/limits and
post-exit verifier drift. Software tests use existing WSL runtime and one fresh
named native fixture root capped80KB; root runs broader slice gates later.
No third completed native/source review, no generic cache object-graph retry.
Missing real current policy/noexec controls fail closed and remain the ONE
connected runtime task; first whole numerical call determines report or exact
architecture blockage under the existing24–48h/max2-round slice limit.

Snapshot frozen filenames: oci-manifest.json,oci-config.json,manifest.json,
inventory.json,runtime-metadata.json,requirements.lock,policy.apparmor,
policy.seccomp.json,policy.compiled,elf-map.json,docker-default.json. Raw lock is
copied from the actual manifest lock_path and bound to existing07f4e7ec digest;
parse it to check exactly81 metadata versions. No new lock/dependency. Runtime
metadata rows contain name/version/absolute metadata_directory and raw/text
SHA256 for METADATA/RECORD/direct_url.json (absent optional entry empty digest).
Full3.12.15 version is the frozen independently measured interpreter string,
current immutable interpreter/library bytes rebound, not a new process/version
measurement during passive collection. Actual tuple is independently checked by
the child before computation; no parent3.12.3 value substituted.

Actual metadata capture79cf75d4 exits0/15.246s, current image/runtime inputs
checked, never-started ownCID removed/Engine5/0. Snapshot also has fixed
receipt.json as operational nonauthority; actualELF map is plain path→SHA,
Engine29.9 imageID is OCI manifestSHA a0abb2dc, rawconfigSHA7c78d260 remains
separate; containerd content root /var/lib/containerd/io.containerd.content.v1.content/blobs/sha256.
Actual AppArmor securityfs uses exactly one name.revision directory and contains
the known auxiliary fields; require current name/enforce/v5/raw_data/raw_sha256
bindings, not a nonexistent unsuffixed path or assumed five-only directory.
Root existing Task2 opt-in kernel blueprint adds /dev noexec tmpfs and3 fixed
readonly/etc binds; default2binds/tmp unchanged. RED4/GREEN4/affected33 and5
driftrefusals, scopedreview clear.80KBaffected-root subcap FAILED453,924B stays
retained/no cleanup; overall1MBforecast884,223B/cumulative128,781,001B<=129MB.
Metadata/software alone grant no admission. Next actual loaded controls/noexec
backings and ONE whole registered numerical job, not another prerequisite family.

Root Planner connected-call decision: actual7a6f1e5a passes snapshot/dependency
fingerprint/EngineOCI then refuses the kernel path; exact owned profile removed,
no container/SQL/service. Metadata-only diagnosis proves /policy is the genuine
root-owned0444 kernel reference apparmorfs:[152]; O_NOFOLLOW returns ENOTDIR.
This is a broken reader for an already required/proven kernel API, not a new
native prerequisite or an input-file symlink waiver. Under standing narrow-fix
authorization, adapt only this fixed /sys/kernel/security/apparmor anchor:
no-follow ancestors, exact root-owned/non-writable namespace reference syntax,
held namespace/profile FDs, before/after reference identity, actual compiled
policy hash/enforce and worker attr/current still required. All snapshot/OCI/
task/member paths keep original no-follow rules. Added effort<=1hour/no fee;
acceptance stays actual current parent/whole numerical report, not test count.
RED missing known-kernel adapter→GREEN12/4.00s/Ruff; no third structural review,
old source/native proof family or arbitrary-path alternative. Same known failed
first nonce remains preserved; code change justifies one corrected connected
call after its completed owned-profile cleanup is independently checked.

Corrected9d4d3673 reaches loaded profile, then its raw_abi member refuses
O_NOFOLLOW. Actual read-only docker-default metadata proves the same kernel API
uses three root0444 references ../../raw_data/<revision>/{abi,raw_data,sha256}.
Resolve their identical numeric revision inside the already held namespace:
open raw_data bank/revision/files with no-follow FDs, never follow a relative
link, require root/non-writable directories and stable before/after references.
Existing compiled hash/name/enforce/v5/PID-label gates remain. This completes
the same kernel-reader mechanical correction, not a new native proof/design
review or ordinary-link waiver. RED missing reference-parser→GREEN13/3.63s,
Ruff/diff green; all failed receipts/owned cleanup retained. Next actual same
connected call with corrected committed bytes; full Worker/PG/report still open.

Actual corrected596d0b93/4.767s exits0: public current parent image/runtime/kernel
verify passes, exact temporary profile removed. Existing parentbaseeb880b2,
providercandidatefd29672 and childimagesourcee34d22f are explicitly distinct;
no production tree/deployment claim. No container/SQL/service started, livePID/
whole Worker/numerical/cache/PGreport/UI remain open. Independent saved checker
exit0; phase949,413B/cumulative128,846,191B within unchanged1MB/129MB, all original
failures/peaks retained. Next frozen privatePG→whole registered numerical job→
durable report→existing page/reopen, not another successful parent/source rerun.
