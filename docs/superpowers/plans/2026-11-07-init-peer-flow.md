# Passive Init same-connection causal vector implementation plan

> For agentic workers: use superpowers:subagent-driven-development or superpowers:executing-plans for this Parent-advanced tracked slice. Use TDD and independent whole-slice review. Implementation is authorized; this plan itself grants no SDK/host/provider action.

**Goal:** one separately qualified Init-only action records actual outbound-wire, client TCP and exact reverse-peer facts that locate the next transport/dispatch frontier without guessing a server cause or repeating the old method.

**Architecture:** preserve the complete query vector and add one explicit method, proposed init-peer-flow-v1. Inspect outgoing1001 bytes already held in RAM, read TCP_INFO on the same already-owned client socket, and add one narrow operation to the existing authenticated channel for read-only Parent procfs samples. Parent derives endpoints from the known owned child and bound provider, never caller PID/address claims. No socket descriptor transfer or peer I/O.

**Tech stack:** existing Python stdlib/protected SDK loader/OperatorReader/SCM-checked SOCK_SEQPACKET channel, pytest/Ruff and existing Linux test infrastructure. Public protobuf/functions are read-only test inputs. No new package, environment, SDK fork or platform.

**Spec:** [docs/superpowers/specs/2026-11-07-init-peer-flow.md](../specs/2026-11-07-init-peer-flow.md). Issue299 and the actual6db authorization govern this bounded software slice.

**Execution:** fresh codex/0038-init-peer-flow from origin/main6a0; existing isolated worktree and dependencies reused. Software80MiB central import4ec71e1b is complete. Private evidence is output/ivv-transaction-recovery-20261104-01/integration/reference-peer-flow-20261107-01 in the Server evidence worktree; Parent supplies verified existing Python313 and this path as scoped $peerPy/$peerEvidence variables. No environment/package installation.

## 1. Evidence and alternatives

Reference11 proves genuine Event False/Timeout20000ms before unpack, saved send OK/local TCP accepted84B/0 pending, and independently established owned normal close. Actual wire contents, ACK, historical peer accept/read/reply and exact context/external cumulative counts remain unestablished. Capture12 is unprepared/withheld; no accepted input/trial/report/decision/financial qualification exists.

The actual-function/protobuf local wire audit passed29 tests, Parent29/6.03s and independent READY; synthetic local pinned conformance only. Its synthetic QM-AUDIT client identity is not runtime PyNormal. The new actual at-rest screen proves two current ZERO listener queues within250ms, the same57 SLEEPING tasks, STOPPED0, current extra3 public dependencies MATCH, normal owned observer/transport closure. It reconstructs no reference11 history, API health or login. Current extra3 MATCH cannot retroactively authenticate their old runtime identity. No concrete repair is supported.

| Rank | Option | Information/cost and ruling |
| --- | --- | --- |
|1 selected|Complete passive wire/client/peer method|Adds missing same-attempt evidence with two Parent samples/two existing-FD client reads, in one source slice/normal qualification.|
|2 prerequisite|Native synthetic loopback plus frozen SDK query/Event controls|Cheapest deterministic sampling/dispatch check before new runtime; included as software qualification, not another operational release.|
|3 reject|Repeat wire audit/at-rest/unchanged query vector|Reproduces known construction/current-backlog facts or unexplained timeout without closing the same-connection gap; no blind repeat.|
|4 excluded|Signals/login/config/restart/packet logs/private ss or tcpdump sidecar/NETLINK/BPF/ptrace|No evidence-supported repair; larger authority/platform/privacy effect.|

Planner selects option1 with option2 qualification. This is a proposal, not a claimed user choice/new grant. If complete facts cannot fit unchanged caps and guards, return to Planner; no per-bit releases/retries.

## 2. Actual owning-source feasibility

All actual seven files match reviewed Source7 E13 before this proposal. Roles remain helper, runner, issuer, native, producer, additional task and recovery contract. Expected production changes: helper/runner plus Parent's issuer helper digest. Other four roles remain exact; tests are not runtime roles.

- Helper _install_wire1747-1789 retains actual raw bytes immediately before saved net.send, after existing mandatory before_send/MAY. Bound ReqInfo1001/serial/thread already matches; original delegate runs once. SDK NetworkManager.send331-337 enqueues; do_send300-329 supplies local socket progress only.
- _InstrumentedReferenceBackend2501-2951 retains exact connection/socket/FD/fstat(dev,ino,mode) before saved send. Request finally2699-2723 restores hooks/unpack. Existing wait wrapper observes actual Event boolean and err snapshot; do not rewrite it or infer unpack from err.
- New private _PeerFlowReferenceBackend can subclass it using the existing exact _InstrumentedReferenceObserver instance. Base constructor requires exact observer type; do not relax or casually subclass it. Add only new-mode private send/outer-query/freeze seams, preserving pure classes/default capture and preferably existing instrumented AST exactly. Report a seam conflict before duplicating or rewriting SDK/query logic.
- _ChildSession3932-3983 owns a request/reply lock; _Channel3121-3166 checks descriptor, credentials/sender PID and8192B cap. _supervise4521-4569 accepts only strict observe shape today: a new strict operation is needed, not hidden fields/bare mode flag.
- _Provider.peer3583-3594, verify_network3596-3630 and OperatorReader already hold provider/PID/start/ns/listener identities and metadata descriptors. Parent can derive scope.pid/child proc directory/client FD and reverse TCP row without producer API changes.
- _owned_peer3768-3801 is mandatory admission proof: established child row requires exactly one vendor-owned reverse established row. KEEP IT UNCHANGED. Auxiliary NOT_OBSERVED cannot relax this guard or swallow its refusal as UNKNOWN. Do not retroclaim its nonvacuous execution at reference11 from guardNONE/source alone; actual call-phase evidence would be needed.

**Timing ruling:** end TCP_INFO AND second Parent RPC run only after original query returns and its existing request finally restores hooks. Name this boundary POST_QUERY. No new getsockopt/callback/RPC inside Event.wait/ReqInfo.wait, before Timeout assignment, or between wait return and SDK PacketErr/unpack decision. getsockopt may release the GIL: silently adding it there changes late-notify scheduling. Baseline is before saved send/before Event.wait. Record post-query delay from existing wait-end; no identical-scheduling/simultaneous-wait-end claim. Original20s delegate calls/args/returns/exceptions remain exact; observation overhead is an explicit new-method effect.

## 3. Proposed selection and closed interfaces

New held control.v3 uses exact existing common fields and fixed method init-peer-flow-v1. Old control.v1/v2 accepted sets/method stay strict. New terminal.v4/runner observation.v4 carry existing query_vector unchanged plus peer_flow. Derive selection exclusively from authenticated held control/hash, recheck agreement at use. Keep historical terminal/observation v1/v2/v3 and plain/framed standalone codecs compatible. Public ABI/default capture unchanged. Parent adopted exact literals in the tracked spec; no historical schema reinterpretation.

Private design signatures:

- Helper _public_init_wire(raw, serial: int) -> dict: independent header/closed public body proof; no SDK call/persistence.
- Helper _owned_tcp_info(binding, phase: str) -> dict: retained socket/object/FD/stamp only.
- New backend _peer_before_send(raw, serial), _peer_post_query(): original saved-send boundary and post-original-query/finally only; no new wait hook.
- Runner _ChildSession.peer_flow(phase: str, fd: int, inode: int) -> dict: same lock/check/channel, no caller PID/address.
- Runner _Provider.peer_flow(scope, request: dict) -> dict: scope/provider from trusted state.
- Runner _select_peer_flow(value, require) -> dict: self-contained finite closure for existing standalone extraction.

IPC request exact keys {op,phase,fd,inode,executable_origin}; op literal init_peer_flow; phase BEFORE_SEND/POST_QUERY; fd exact int0..1048575/notbool, inode exact positive bounded int. Origin is existing checked witness. No PID/address/port/path/method override/payload/nonce/SCM_RIGHTS. Parent verifies sender==scope.pid, held new control/method, granted/nonterminal phase, source/kernel/lease/provider/resources; binds first FD/inode to actual child socket and second to same stamp. At most one ordered request per phase; early failure can leave UNOBSERVED. Old mode/extra keys/type confusion/replay/reorder/spoof are real protocol refusal.

Reply exact {peer_flow:sample}; no generic proc RPC. Parent stats/readlinks the child FD under known scope.pid, locates one same-namespace client TCP row by inode and fixed127.0.0.1:11112 endpoint, derives exact reverse four-tuple, and searches the same bounded table. Recheck child PID/start/named FD stamp, vendor PID/start/ns/listener/provider controls, row uniqueness and vendor FD membership before/after. Export finite predicates only, no PID/tuple/address/kernel pointer. Never open/dup a peer socket FD; metadata files/directories close via existing lifecycle.

Proposed peer_flow exact fields, compact JSON<=1100B:

| Field | Closed content |
| --- | --- |
|schema|qm.ivv.init-peer-flow.v1|
|wire|state UNOBSERVED/PUBLIC_CONFORMANT/NONCONFORMANT/UNKNOWN; reason NONE/HEADER/BODY/UNSUPPORTED/OBSERVATION; packet_sha256 lowerhex64/null; six bool-or-null predicates ft,p1001,fmt0ver0,size_sha,reserved0,public_c2s|
|client|identity UNOBSERVED/VERIFIED/DRIFT/UNKNOWN; abi SUPPORTED/UNSUPPORTED/UNKNOWN; state_before/state_end ESTABLISHED/OTHER/UNKNOWN; acked_delta/received_delta nonnegative exact int<=2^63-1/null; unacked_before/unacked_end exact uint32/null; relation VALID/RACE_OR_UNKNOWN/UNOBSERVED|
|peer_before,peer_after|each identity VERIFIED/DRIFT/UNKNOWN/UNOBSERVED; row MATCH/NOT_OBSERVED/AMBIGUOUS/UNKNOWN; state ESTABLISHED/CLOSING/OTHER/UNKNOWN; vendor_fd PRESENT/NOT_OBSERVED/UNKNOWN; rx/tx ZERO/LE_1K/LE_64K/GT_64K/UNKNOWN; offset_ms exact int0..480000/null|
|timing|sequential true; wait_to_post_ms exact int0..480000/null|

Null is not zero; reject bool/subclass confusion. Raw baseline/end counters stay RAM-only except bounded unacked samples; export deltas. Peer offsets use existing plan monotonic origin, wait_to_post_ms is local post-query TCP delay from wait-end. Interpret cross-process offsets only with established existing clock-domain binding, else UNKNOWN. Client/peer are sequential intervals, not atomic endpoints. No vendor-failure/READY classifier; optional UNKNOWN cannot become a send/admission/data gate.

## 4. Actual outgoing privacy proof before digest

Inspect only bytes/bytearray already passed to saved net.send, bounded RAM copy<=1024B. Larger/unexpected data=>UNKNOWN and no retained bytes/hash. Existing mandatory guard/MAY order remains independent; conformance never suppresses/substitutes the original send.

Independently verify44B little-endian FT header/protocol1001/format0/version0/bound serial/exact length/body SHA1/reserved8 zero. Require exact canonical closed public Init Request/C2S: clientVer300, clientID PyNormal, recvNotify true, packetEncAlgo -1, pushProtoFmt0, programmingLanguage Python, aiType0, and only known public tags/wire types. Actual pinned pack_req/_send_init_connect_sync/defaults/descriptors supply this contract; not audit QM-AUDIT.

Cheapest closure proof: assemble exact expected canonical public C2S in RAM from fixed public literals/tags with a purpose-limited varint/length encoder, compare entire body. This is an independent validator expectation, NEVER replacement SDK serializer. Positive tests use actual pinned pack_req/pack_pb_req/_joint_head AST and real protobuf. Equality excludes unknown fields/duplicates/alternative encodings/appended credentials or future text; ListFields or parse-success alone cannot.

Compute/export SHA256(actual packet) ONLY after full header/closed-body proof. Unknown/extra/malformed/noncanonical/custom clientID/encrypted body=>null digest. Never hash unproved bytes/response/account/login/retMsg/exception text; never persist raw bytes/body/tuple/offending values/str/repr/args. Fixed predicate failure is optional metadata, not vendor error or proven repair. Preserve original args/object/return/exception and single call.

## 5. Primary kernel semantics and limitations

Primary sources below were actually browsed. Version6.1 is a semantic/layout reference, NOT actual host kernel build/ABI proof. No host query here. Qualify admitted ABI/native behavior; unsupported=>UNKNOWN.

- [tcp_info UAPI](https://raw.githubusercontent.com/torvalds/linux/v6.1/include/uapi/linux/tcp.h): candidate native prefix state byte0; unacked uint32 offset24; bytes_acked uint64 offset120; bytes_received uint64 offset128. Require supported native layout/endianness, returned length>=136, request<=256B. Never pad or decode as network endian. Independently derive/check layout/public types and native positive controls.
- [tcp_get_info/TCP_INFO](https://raw.githubusercontent.com/torvalds/linux/v6.1/net/ipv4/tcp.c): kernel limits returned length; established unacked is packets_out, not bytes. Exclude listener aliases. Socket locking does not make client/peer snapshots atomic.
- [tcp_input counters](https://raw.githubusercontent.com/torvalds/linux/v6.1/net/ipv4/tcp_input.c) and [RFC4898](https://www.rfc-editor.org/rfc/rfc4898.html): cumulative sequence progress, not application consumption. ACK is not API acceptance; received progression is not notify/unpack. SYN/FIN/state changes/prebaseline traffic/other sends/regression/wrap/drift prevent request-specific attribution. Preserve RACE_OR_UNKNOWN, no wrap guess.
- [get_tcp4_sock](https://raw.githubusercontent.com/torvalds/linux/v6.1/net/ipv4/tcp_ipv4.c) and [proc TCP docs](https://www.kernel.org/doc/html/v6.1/networking/proc_net_tcp.html): ordinary TX is write_seq-snd_una, RX clamped rcv_nxt-copied_seq. These are queue samples, not cumulative peer transmit/read counters. Listener/open-request/TIME_WAIT meanings differ; do not apply established semantics there. Reuse deprecated-but-existing proc interface rather than add NETLINK.

Client baseline after exact bind/before saved send; end after original query/finally, before Parent POST_QUERY RPC, with same object/FD/stamp checks. No new code inside Event/ReqInfo.wait or original Timeout/late-notify decision. Original20s semantics remain; exported offset admits GIL/syscall delay and late state races.

Parent bound262144B/4096 rows/256 FDs, <=2s metadata deadline and existing total480s. Optional overflow/truncation/budget exhaustion=>UNKNOWN. OperatorReader.read currently raises mandatory READ_BOUND: do not call then blanket-catch CaptureRejected. Reuse protected dirs/keep/release with explicit new optional bounded-return reader. Ordinary OSError/API absence may yield UNKNOWN; real source/PID/ns/lease/provider/FD refusal, cleanup error, KeyboardInterrupt/SystemExit or missing/corrupt authenticated reply stay fail-closed. Preserve primary delegate exception identity/sticky poison/always close; recording cannot mask it.

## 6. Causal interpretation

| Same-attempt facts | Supported narrowing | Not proved |
| --- | --- | --- |
|Public wire; clean established baseline/end; ACK delta equals sole request length|Request sequence reaches cumulative ACK frontier|Handler read/API acceptance/login|
|ACK plus exact reverse row/vendor FD PRESENT, RX nonzero|Matched endpoint queued receive data at sample|Never read/permanent stall/exclusive holder|
|Peer RX ZERO at either/both samples|No queued unread sequence bytes then|Handler read request/API health|
|Reverse row/FD NOT_OBSERVED|Scan did not witness membership|Unaccepted/no delivery/no peer; pending accept/outside holder/race UNKNOWN|
|Peer TX nonzero, no client receive progression|Outstanding matched-peer send sequence at sample|Response contents/exact loss cause|
|Client receive progression/unread, no SDK on_recv/notify|Kernel-to-SDK dispatch becomes concrete frontier|Target response/decoder error/vendor failure|
|Identity/state/counter/order/unsupported race|RACE_OR_UNKNOWN, other known facts retained|Cause/repair/new permission|

Journal false is not absence proof: no Init-response writer. TX ZERO cannot exclude already-ACKed response. Two sequential samples cannot reconstruct intermediate queues/full peer transmit history; additional instrumentation/authority is outside this cheapest method. No inference changes timeout/login/configuration/READY/conditional capture.

## 7. Future one-slice TDD and release

### Task1: complete helper/Parent method and frozen source/tests

Files: helper/runner, new tests/test_ivv_init_peer_flow.py. Parent owns issuer digest, the new module's early contract selection in tools/quality_gate.py, tracked spec/plan/iteration, private Ops/capacity/Git/CI/publication/actual actions. No same-file writers; four other roles exact; default/pure/public ABI preserved. Deliver every causal group plus source/test/RED/GREEN/AST/pins together.

- [x] Parent accounted new phase common64MiB+one normal CI16MiB, net80MiB; reuse/retain Source64, no clone/refund/paid resource. No source/fixture write before accounting. Current proposal256KiB is within existing common64; internal accounting is not another ordinary human approval.
- [x] RED first test test_real_sdk_timeout_keeps_public_wire_and_post_query_flow_without_peer_read_claim: actual frozen ReqInfo.wait/_query_sync/send_init/pack/header and real protobuf, external I/O/scheduling model. Genuine False/20s semantics before unpack, privacy-gated digest, exact deltas, post-query offsets/owned close; RAM RXZERO=>handlerread mutant fails. Missing method/facts is intended RED, not import/fixture failure.
- [x] Run existing Python ($peerPy) -I -B -X utf8 -m pytest -q -p no:cacheprovider tests/test_ivv_init_peer_flow.py::test_real_sdk_timeout_keeps_public_wire_and_post_query_flow_without_peer_read_claim --basetemp=$peerEvidence/core/red-01; retain actual argv/sourcepins/stdout/stderr/exit/count/wall. No real SDK package/context.
- [x] Implement held mode/new backend/finite wire/client/Parent sampling/terminal/codec as one bounded task. Original query/finally remain, both end reads/RPC after restoration. Metadata never gates sends/READY; guards/restore failures preserve original exceptions/sticky refusal/always close.
- [x] GREEN first node/new basetemp. Cover full enums/legacy schemas/standalone codecs; wrong held method/bare flag; raw/serial/default-vs-QM-AUDIT/custom/credential-bearing body; extra/unknown/duplicate/noncanonical protobuf; header/fmt/size/SHA/RSA; short/endian/listener/SYN/FIN/unsupported TCP_INFO; bool/negative/overflow/regression; socket close/reuse/drift; wrong/multiple/missing reverse tuple/vendorFD/permission/bounds; FD/PID/address spoof/phase replay/SCM faults; optional metadata under original send/wait/unpack/guard/close/restore exceptions.
- [x] RAM mutants rejected: digest before closure; unacked0=>ACK; packets-as-bytes; RXZERO=>read; absent vendorFD=>unaccepted; trust child PID/address/port-only tuple; end read inside Event wrapper; RPC before original SDK err branch. Never modify installed SDK/frozen originals.
- [x] Native existing Linux positives: real ephemeral loopback sockets/TCP_INFO layout+delta/proc reverse row+inode+FD/queued-unread/delayed-consume/synthetic response dispatch. Exercise low-level production sampler on separately known test-owned endpoint; fixed runtime11112 guard separately strict-tested, no runtime flag selects ephemeral seam. Use frozen SDK receive/Event bodies where applicable; bounded waits and finally-close every test socket/thread/process. No vendor context/import/connection. Windows unsupported explicit; normal Linux runs causal positives, not skipped.
- [x] Existing true/false/late-notify/unpack/exception-identity/restoration controls; assert no new code inside original waits and no trace/global patch leak. Normal send never means ACK.
- [x] New/affected legacy/bootstrap/standalone targets, changed Ruff/format, exact pure/default/old-instrumented AST/public ABI proof and source/FD/call census. Freeze handoff; Parent reads actual receipts and updates issuer digest after bytes freeze. Broad checks only coherent-slice boundary.

### Task2: Parent review/release and distinct method pair only after qualification

- [x] Adopt exact schema/interface in tracked spec. Independent complete Spec/Standards review, maxR1/R2; third structural failure returns Planner reduction. Review privacy/ABI/authority/deadline/lifecycle/causal claims.
- [x] Mature new private Ops after source freeze; strict new control/method/Source7 bindings, reverse proof, entropy/failure/UNKNOWN geometry. Caps IPC/status8192, carrier327680, packed262144, body1MiB, all prior header/frame/resources unchanged. Actual current carrier310076 leaves17604B, status6958 leaves1234B. Compact schema arithmetic is not real carrier qualification; enforce peer_flow<=1100 and whole envelopes<=8192. Source compression uncertain. No cap increase/dropped facts: fail=>Planner reduction.
- [ ] One matching-head normal fullCI/exact-lock artifact, expected-head normal merge/full-tree/reviewed Source7 equality and exact actual publication/catalog/release. No per-bit CI/healthy rerun/cancel/stale-base qualification. Seven roles and diagnostic manager1/client1/capture0/0 unchanged.
- [ ] Only after software/review/CI/merge/publication/full future accounting may Parent prepare distinct immutable method namespace/intent/context/request/provider/actor/source budgets. No replay of11, nonce/once revival or capture12 reuse. Actual Fresh/SDK identity/FD/sandbox/resources/held/lease/normal-close mandatory. This proposal creates none.
- [ ] One separately qualified invocation; original fixed capture only real READY/allnormalclose/original claim+manager rules/new Fresh. UNKNOWN cannot set READY. Diagnostic hash/queue never FRAME/STORED/input/seal/research. Quant data/window/math/cost/OOS/H1/H2/H3 unchanged, paper default/live disabled.
- [ ] Record actual distinctions at legitimate iteration/goal/roadmap/ADR checkpoint; retain all failures/futures. Parent alone executes actual operations under existing authority.

## 8. Cost, uncertainty and handoff

Estimate one coherent24–48h software slice, not promised server diagnosis. Added runtime: two existing-FD TCP_INFO reads, two <=2s metadata RPC/scans outside original wait/query decision, <=1KiB RAM wire comparison. No new socket/peerFD/dependency/worker/logger/platform/paid resource. Reads still perturb scheduling; record overhead, no counterfactual equivalence claim.

Qualification uncertainties: actual admitted ABI/return size; Linux CI/sandbox permissions/native behavior; whether two peer snapshots discriminate; control-sequence/counter attribution; source compression/status headroom. More proc authority/new roles/platform/relaxed guards/larger caps/dropped causal groups requires concrete Planner scope review before expansion. Empty queues/sleeping tasks/synthetic positives prove no repair.

Self-review: all requested groups in one method, named privacy/ABI/race/authority/cleanup/cap controls. Old mandatory peer proof remains, auxiliary metadata separate; no historical peeraccept inference. Post-query timing honestly named. No tests/source implementation/runtime actions in this Planner task. Two read-only inspection attempts used wrong public path/line range before corrected reads; one oversized shell command rejected before process creation and one draft tool expression rejected by parser, no file/runtime effects. None is TDD or SDK failure.

Historical proposal handoff is retained under the prior evidence namespace. Parent advanced this tracked software plan after actual issue299 and central80MiB import. Reference kernel URLs do not authenticate the admitted host build. Implementation follows the binding spec; operational invocation remains separately gated.



## Parent execution rulings and coherent checkpoints

The spec's scope/tuple/timing/privacy rulings override the earlier proposal wording where needed. Task1's core writer does not edit issuer, quality_gate, docs, private Ops, Git or CI. Parent adds only the new test module to the existing complete contract selection, after core freeze; no gate assertion or workflow change. Parent applies the prepared docs02 evidence prefix at the legitimate integration checkpoint and adds current issue299 scope. Broad required checks run only at slice commit/final PR boundaries: complete local contract, global Ruff, changed formatting, whitespace and untouched nine Gitlinks; known platform limitations are retained and matching Linux CI remains required.

No full-payload or SDK/provider call occurs in software tests. Native controls use only ephemeral synthetic loopback endpoints and existing Linux infrastructure; a pass is not production/vendor proof. Before Source freeze, qualify the whole diagnostic privacy/ABI/peer/source/codec geometry together. No partial-field runtime or per-field CI.

Core checkpoint: helper4a3ecaa3/runnerb71b76b3/test8d5f47be frozen after genuine
causal RED/GREEN,109 Linux focused passes/no skips,107 Windows passes/2 native
skips and354 affected legacy passes/31 subtests. Parent issuer0003c0c5 and
contract selectionbdf6ae00 are synchronized; bootstrap5PASS/1 platform skip and
global Ruff/changed formatting/whitespace pass. See the iteration for exact
receipts, dependency/fixture failures and limitations. Reviews/geometry/CI/
normal merge/publication remain pending; no runtime pair or action exists.

Ruling: the complete local contract checks actual HEAD source bytes. Its first
real run correctly refused the focused-tested but uncommitted candidate.
Commit this coherent candidate without pushing or qualifying it, then run the
unchanged complete contract against that HEAD. Preserve both the isolated
command import failure and exact-source refusal; no gate assertion is relaxed.

R1 correction checkpoint: both independent axes reported one identical P2 in
the two new metadata-reader finally blocks. One consolidated TDD fix preserves
primary identity/all cleanup/sticky close state:13FAIL->18PASS, final complete
Windows module125PASS/2 native skips, Linux changed/native controls21PASS and
legacy cleanup17PASS. Parent18PASS and global Ruff/format/whitespace pass at
runner465ec1ea/testb69be869; helper/issuer/gate/four roles remain unchanged.
Same-reader R2 is next, with no third structural patch round. The non-Linux
POSIX test-predicate minor is deferred. Exact-head prior contract744PASS18SKIP
plus the unchanged Windows path assertion and same-node Linux1PASS remain
retained; never label the complete contract or future CI green from that.

Planner continuation: both sole Source R2 axes are READY at dfdbb827. Private
Ops01 then correctly refused default carrier329923>327680; no reference/96-case
qualification ran. Source7 stays frozen. Remaining Task2 implementation follows
the bounded docs/superpowers/{specs,plans}/2026-11-07-init-peer-carrier-encoding.md
with new immutable Ops02, explicit outer Base85 tag/canonicality and every old
compressed/body/role/resource cap. Old Ops01 and negative evidence are retained;
this is Planner reduction, not a third Source patch loop or runtime approval.

Issue/software capacity/current main were actually checked. Actual evidence snapshots, code checks and completion evidence belong in the active iteration and private PLAN-PROGRESS; no self-certified runtime GO. All previous immutable evidence remains, and only final actual source/review/CI/merge/publication can enter a later runtime binding.

Final software checkpoint supersedes pending intermediate statuses above:
Source R2 both READY at dfdbb827; Ops02 encoding completed full geometry.
One private R1 role-binding P2 was corrected in immutable Ops03 with genuine
RED9/GREEN14; complete39 tests/70 subtests,96 synthetic cases and both sole R2
axes READY. Carrier maximum312424<327680; every original cap unchanged.
Canonical Source manifest02 c08a5dbc preserves Source7; canonical Ops03 manifest
e40f62a2 binds the four final bodies. Old failures remain. Task2 CI/merge/actual
publication and any distinct fully accounted runtime pair remain pending.

CI581 fast exposed stale contract-selection test count12 vsactual13. The
bounded test-only correction keeps exact uniqueness and adds explicit peer
module membership; actual RED1 -> complete gate-module39PASS/2SKIP, independent
integration review READY. Source7 and gate code remain frozen. Preserve failed
CI581 and wait for its release terminal before corrected-head normal CI; no
healthy cancellation/rerun or old artifact qualification.
