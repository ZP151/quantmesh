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
| Capacity | Current caps12GiB global/6GiB parent/free50GiB. Old80MiB retained; recovery138MiB (software26,capture48local/48remote,review4,study8,close2local/2remote), total218MiB. Current P4 guardG10614829146/P4576756750/all-parent4633379854 fit. Software subsets Server7/Product12/commonGit-review-CI-catalog6/failureFS1 MiB; P1/P2/P3 retained. This is a complete forecast, not runtime GO. |

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
