# Fixed IVV recovery transaction — frozen Server/Product boundary

Issue [281](https://github.com/ZP151/quantmesh/issues/281). Actual human direction
`6db1254cdf428a17952ae764b10d597435067dc151219c39b3c4fc18c1853dfd`
supersedes the pending fixed-one-shot proposal and its 4.6GB question. It authorizes
necessary reasonable recorded capture/request/compute recovery, not new data,
mathematics, paid resources, credentials or trading. PR280 is delivered; do not
repeat its verification. Historical UNKNOWN/SPENT records remain immutable.

**User action/outcome:** resume the fixed IVV task; read committed originals or
make attributable bounded progress toward one accepted input and published result.
Local commits cannot make SDK effects exactly-once. Persist possible external
effects before the call; UNKNOWN is conservatively charged and never refunded.

| Boundary | Frozen contract |
| --- | --- |
| Identity | `logical_task_id=ivv-trend-staged-20261029`; identity exact five fields `logical_task_id,experiment_id,input_version,math_cost_spec,business_key`. Initial experiment `declared-trend-staged-v1`; business key is canonical SHA256 of the first four. Authorization/source/attempt IDs are excluded. Job is UUID5(NAMESPACE_URL, `urn:quantmesh:ivv-recovery:v1:` + business key). New semantic input/math requires an explicitly registered experiment revision, never overwrite a completed job. |
| Semantic input | Exact projection: candidate,inputs,instrument,source_id,source_use,currency,price_adjustment,volume_unit,historical_trade_venues,action_coverage,calendar_id,calendar_timezone,calendar_version,availability_assumption,pit_status,revision_note,window,sample_role. Inputs contain the three normalized bars/distributions/schedule ObjectRefs. Exclude authority/review/raw-envelope aliases; retain all original refs in the complete input manifest. |
| Coherence/publication | This version requires one actual capture_epoch for the complete package. The immutable manifest retains all raw responses, asof/PIT/provider-version evidence and normal closure. Provider-version evidence does not enable cross-epoch composition in this version; no semantic-hash shortcut or unimplemented cross-epoch path is accepted. Validate all originals before atomic input publication; Quant H1/H2/H3 acceptance before compute. Equivalent complete manifests reuse the original committed binding; never replace its evidence on cold read. |
| Mathematics | `math_cost_spec=7e0c785311bdae85828898bcc63b7a88d724da9bab4f844eb35673c923c34fea`, SHA256 of existing `_accounting_contract()` only. Fixed May8-Oct29,121=100+21 sessions,QuantityA,T/TO/B50/B100/C,5/10bps,100000USD; no service/sourcepack hash in semantic identity. Actual numeric source/runtime pins remain per-attempt checks. |
| Policy/proofs | One Server-owned `ivv_recovery.py`; family `.dev-transaction-recovery.v1`, mode `DEV_TRANSACTION_RECOVERY`; trusted proofs require `recovery_policy_ref`. Existing reference-only HTTP requests gain no arbitrary authority/path/qualified inputs. Existing issuer/held native admission is extended, not replaced by a second issuer. |
| Study binding | Study GO/acceptance carry `recovery_identity,input_manifest_ref`; study scope and existing scope-trial slot equal business key, research effect=SHA256(canonical({business_key,purpose:declared_ivv_research})); job UUID as above. Capture scope=SHA256(canonical({logical_task_id,purpose:readonly_ivv_capture})). Capture GO precedes inputs and never fabricates an unknown study job. |
| Attempts | Distinct connection/request/compute IDs. Durable intent, MAY_HAVE_SENT, observed response original, closed/UNKNOWN and checkpoint state precede successor effects. Current owner lease serializes effects; uncertain owned cleanup requires exact-owner recovery before another owned context. Same unrepaired structural refusal stops for a concrete repair, not blind retries. |
| Computation | Existing WriterLease+JsonlStore record running attempt before compute; ObjectStore report -> durable prepared_report pointer -> atomic committed job. Restart with validated prepared report commits without recomputation. Without a prepared result, bounded recorded recovery computation is allowed. Cumulative compute allowance counts the same logical task across all registered experiments/business keys and authority/batch versions; a validated prepared commit uses zero new computation. Committed report/decision stays immutable; lost acknowledgement reads the same originals. |
| First operating batch | 1800s,3 contexts,32 read-only business sends,1 business/s,Init<=3,KeepAlive<=288,initial cumulative compute allowance3; one simultaneous context. These are recorded expandable operating allowances, not permanent authorization caps. Honor actual provider quota/rate responses. Own context retains512MiB/swap0/CPU50%/Tasks32/480s and existing transport/close protections. |
| Capacity | Current caps12GiB global/6GiB parent/free50GiB. Old80MiB retained; recovery152MiB (software40,capture48local/48remote,review4,study8,close2local/2remote), total232MiB. Current P8 guardG10629509210/P4591436814/all-parent4648059918 fit. Software subsets Server7/Product16/commonGit-review-CI-catalog16/failureFS1 MiB; P1-P7 retained. Complete forecast, not runtime GO. |

Server exclusively owns shared policy/contracts/docs, capture/helper/issuer/runner,
operational adapters and actual host work. Product exclusively owns admission,
Windows runtime, native_daily_real, direct consumer tests and the minimum existing
UI guard if needed; no policy copy or competing CI. Exactly two source writers.
Quant independently reviews protocol/accounting now and actual inputs later.

One bounded two-axis independent review and at most one consolidated correction/
same-reader R2, then matching-head normal CI/merge/catalog. Apply the actual diff's
review policy without invented human reviews or admin bypass; ordinary approved
workflow choices do not reopen per-attempt human approval. Escalate only actual
paid/security/data/math/trading differences or real OTP/device challenges.

Server/Product field ACK recorded2026-11-04 before implementation. This is an
implementation contract, not a provider guarantee or financial qualification.

Operating supplement02: Product's full source/fixture forecast requires8MiB;
software becomes18MiB (Server5/Product8/commonGit-review-CI-catalog4/FS1), recovery
130MiB and all-old-plus-new210MiB. Net2MiB is registered under standing growth;
guardG10606440538/P4568368142/all-parent4624991246 fit current caps. Initial policy
P1 remains archived; P2 uses these current numbers without identity/count reset.

Operating supplements03/04 preserve all failures and old futures. P3 raises Product
to12MiB; P4 raises Server to7 and integration/common to6MiB. Software26MiB and
recovery138+old80=218MiB are registered under standing same-scope growth. Protected
operator P4 is1425B/SHA256d55242c0510cda04c775a5725f10c3974a5c7d0c6c92e1ef9b44fbfbf0f2ebfc.
The pure-module default is an initial convenience, not a permanent policy hash.
Capture policy/source/normal closure are archived per actual original; later
study policy may differ without relabeling inputs or resetting attempt debits.

Supplement05 adds6MiB only to integration/common (now12MiB) after discovering the
actual local Vite mismatch and the need to retain exact-lock CI artifacts plus
publication objects/catalog. Software32MiB, recovery144+old80=224MiB. Protected
P5 is1425B/SHA2560d817811c3fd1db015451f700ec5a2531ba6855ec07fee032c3e0d0d31a56bf5;
all initial policies remain historical without changing business or attempt counts.

Consolidated R1 supplement06 adds4MiB only to Product (now16MiB) for exact-owned
cleanup and scoped durable publication tests/failures. Software36MiB and
recovery148+old80=228MiB; P6 actual1425B/SHA25605abb057cc5e3b3fb82e3ec40979aca2dad193d259717ddea3d79d082a378671.
All old holds, originals and counts remain; study allowance still8MiB.

Consolidated R1 entry clarification: local transport submissions and remote
connection identities are distinct. Under the original claim lease, compare the
expected remote identity before INTENT mutation; replay a claimed connection from
its original startup/publication/policy pins, without another SDK invocation.
INTENT atomically includes exact pre-dispatch controller and held/named claim-lock
identity. DISPATCH_MAY is durable before Popen. A missing/uncertain dispatch binding
stays UNKNOWN. Predispatch recovery requires the old controller gone, the same
claim inode exclusively held, the fixed unit absent and no dispatch marker; this
is cleanup-only, never a normal SDK close or input publication.

Use the existing fixed systemd unit with a gated manager, original Invocation and
exact cgroup/process ownership. Retain terminal unit identity through both success
and failure until exact cleanup; the new command uses --remain-after-exit, without
--wait or --collect. Observe manager exit independently of the original client,
verify recursive emptiness, then stop the exact quiescent unit and reap that client.
Uncertain identity/cleanup blocks successors. This describes the software contract;
actual native lifecycle and resource admission remain execution gates.

The recovery-only decoded packet ceiling is1MiB in both builder and bounded
remote decompressor because the source/control/base64 envelope exceeds the old
512KiB representation ceiling. Compressed carrier remains256KiB; existing source,
capture, SDK-log, actor, deadline and per-connection disk limits are unchanged.
Legacy families retain their original limits and interpretation.

Standing supplement07 registers net4MiB only to common integration (12->16MiB)
for all retained CI evidence/trees, the necessary frontend consumer correction's
bundle/third current-head artifact and final catalog. A conservative full-index
census12,926,976B plus complete futures yields15,286,272B<16MiB. No old hold is
reduced or borrowed. The first protected P7 is retained as1426B/SHA25660025969eae837b0205128b9b9a5db2cb8acd8b63a35766ac8f7fe35135f999d;
source DEFAULT_POLICY remains historical convenience. Only storage forecast and
guard provenance change, never actor/data/math/batch/counts or business identity.

Before any carrier/host execution, the actual RecoveryProfile exposed one extra
newline in P7: raw policy SHA differed from the profile's canonical policy SHA.
Keep that record and pointer; canonical P8 has exactly the same dictionary,
1425B/SHA256b81fd83161f477dcd8c37c2b08ccc16f9075fc27760c359ec9bfc3694d7e5346,
and matches the real profile. Current selector points to P8. This serialization
correction registers net0 against capacity07, never another4MiB or counter reset.
