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
| Source | Foundation PR175 head370a745caeee0d5d60d41b4eb4716316cb44b935; kernel integration8c9093015f18e2905f42065baa0237e81dcb20b9. Current image application bytes are committed41214ff3d049677ae9b599f5bd77ae23b817144f. Freeze a new exact SHA if code changes; deploy only a reviewed merged tree. |
| Numerical runtime | Linuxamd64, actual CPython3.12.15 `/usr/local/bin/python3`, prefix/usr/local. Image7c3a8389dc95348125c10ea062bd3cbd2af2a645f1b66127ead7bad6c0c6097c, raw OCI configb5e9d3424e5915326235e869847fba670bb641d4f1321a4d83c884341cec3fdc.81-wheel lock07f4e7ec64805a375e0bdc707d0158fbdb08bd07d02aa569e2d119496b32592a. Source preparation passes; numerical admission remains pending. |
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
