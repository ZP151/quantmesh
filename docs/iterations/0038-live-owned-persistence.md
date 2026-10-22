# Live owned persistence — functional delivery and preserved experiment evidence

Tracking: https://github.com/ZP151/quantmesh/issues/208, verified OPEN.
Issue201 is verified CLOSED and covers the already merged checkpoint query;
this leaf neither reopens nor closes it. No commit is made before binding a
real current task. The current leaf is bound to208. Base aa62faeddd84c31887e43bf0dae532e649a4ecbe; managed worktree
0038-live-owned-persistence, branch codex/0038-live-owned-persistence.

Planner: root assigns one bounded internal feed persistence owner: real tiny
DuckDB,32–64 synthetic updates, actual pump/drain and publish paths, finite160ms
append/COMMIT/lock seam, fixed50ms loop responsiveness gate. Only feed.py, the
new focused test and own records are writable. Constructor/history/query,
buffer.py, REST, chart, schema/retention/indexes/dependencies and host remain
excluded. The15min context/RED gate precedes all runtime implementation.

Quant researcher: this is a synthetic operational responsiveness fixture. It
cannot prove original-history cost, market recovery, retained-scale live,
provider entitlement, research validity or trading readiness. No market data,
provider, historical lake or original database was read or copied.

Implementer context: source caller search within live/api found no external
active owner-loop synchronous feed.ingest caller. Existing internal publish,
publish_many, publish_threadsafe, drain and tick still need the proposed common
ordering/owned-stop implementation proof. No compatibility claim is made.
Existing feed baseline passed49tests/5existing warnings in6.99s using the
existing WSL Python runtime; no package or environment was installed.

Verifier: one new test drives LiveFeed.run and the real Hyperliquid supervisor
through32 fixed synthetic bbo frames. It forwards all SQL to real DuckDB and
delays only the actual COMMIT call160ms. A2ms loop heartbeat samples maximum
gap. All32 quote delivery/persisted whole objects and distinct event IDs match
before the response assertions; actual commits are observed. No fake append
success or old control substitutes this new invocation.

STOP fact: no-delay control81.293757ms already exceeds the fixed50ms gate;
delayed path214.236843ms. The assertion fails FIRST at the control, so this is
INCONCLUSIVE, not the intended causal RED. Source feed.py is byte-identical to
base, SHA256f3f2bef90d6aa5315cda5f5af80a6f296f3190d2b0a5d3967ea52ab3d8e5c154.
Test SHA25651c3e39ae04a16da86d7900623869b34ed581f626fbd287749fd284530291055.
Raw invocation/output/hash receipt: output/0038-live-owned-persistence/
pump-red.{json,txt}; STOP.json records the disposition. All six Git redirection
variables are explicitly unset for pytest; no shared Git repair was attempted.

Reviewer/release: no runtime diff exists to review or release. Do not relax the
threshold, select a passing retry, call this RED, or implement the owner path
before Planner dispositions this control failure. The delay's contribution,
cold SQL cost and scheduling noise have not been separated. The source seat
and concrete STOP fact are returned to root within the initial timebox.
No further test, source implementation, push, CI, SSH/host mutation, new job
pair, dependency scan, full-root suite or production acceptance follows.

Planner calibration disposition,2026-10-22: one fixed paired phase calibration
is now authorized before any runtime change. Both sides complete exactly2
warmup quote updates through the same real pump/append/COMMIT path before
measurement. Then measure32 updates (total34), unchanged50ms maximum gate,
unchanged160ms measurement-only real COMMIT delay. No repeated warmup, filtering,
threshold change, platform/environment change or selected retry. The old raw
record lacks phase timestamps, so it cannot attribute81ms to cold SQL or any
particular stage. New markers cover append/COMMIT/phase timing only; a failed
new control returns another STOP. This narrows the claim to steady-state and
does not improve or qualify formal startup/history behavior.

Verifier fixed calibration result: STOP. The one preregistered paired run used
exactly2 warmup quotes and32 measured quotes per side, unchanged50ms maximum
gate and160ms measurement-only COMMIT delay. Control59.721261ms, delayed
216.391458ms; the first assertion still fails at the control. After completed
warmup, measured control append enters at8.389565012, COMMIT enters8.440982302,
returns8.446155987, append returns8.446184413 (process-monotonic seconds).
Thus measured pre-COMMIT append work is51.417290ms, actual COMMIT5.173685ms,
whole append56.619401ms. Its maximum heartbeat gap spans8.386697647–8.446418908.
This places the new stall within measured append, but does not separate its
internal SQL/other costs or attribute the old81ms to cold initialization.

All34 delivered quote objects equal real persisted quote objects and have34
distinct event IDs before the failing responsiveness assertion. Original raw
and new calibrated-pair.{json,txt} are preserved. CALIBRATION-PREREGISTERED.json
predates execution and its source/test hashes match the executed receipt;
both raw-output hashes verify. New test SHA256
da1424f7e1de04258b206bc1e7e96b3166bf1a8d03248bfe82ba24736e12c0b7.
Source is still byte-identical toaa62 at f3f2bef9... . CALIBRATION-RESULT.json
records the single STOP fact. No second calibration/parameter search, further
test run, runtime edit, source commit, push, CI, host or old-data action follows.
This is not RED/GREEN, functional completion or formal startup/live acceptance.

## Accepted functional leaf —08:12SGT start,2026-10-22

Root accepted whole-append single-owned-I/O/order/cancel-drain functional
contract and allocated one source seat; no new latency calibration approved.
Plan: ../superpowers/plans/2026-10-22-live-owned-persistence.md. Actual freshly
fetched base and managed HEAD remain aa62; only owned prototype/record were dirty.

Both full historical test texts and raw receipts are frozen under ignored
output/0038-live-owned-persistence/history/. Recovered original full text SHA
matches51c3e39a...; calibrated full text matches da1424f7... . MANIFEST.json
records input generators and the missing realized old absolute timestamps;
those instances were not captured and are not invented. New functional input
is exact fixed2026-10-21UTC quote/wire data,33quotes total, no warmup/paired delay.

Verifier new actual RED before any runtime edit: lifecycle-red.{txt,json}.
Trace commit_enter→stop_intent→io_release→commit_return→stop_observed;
snapshot at stop is already the new wire event instead of owned-quote-0.
All33quotes really persisted; test fails at the intended loop/cache ordering
assertion, not a timeout/collection failure. Existing feed SHA f3f2bef9...;
new same-test SHA1ead62fa2b9451987e3fd5a55eefcaddfe1708e0f857b50dbb359e33001d0806.
No source green/compatibility/release claim yet.

Functional implementation checkpoint: the exact initial lifecycle test bytes
1ead62fa... pass after whole storage offload and joined/generation-fenced stop.
Trace now commit_enter→stop_intent→stop_observed→io_release→commit_return;
cache at stop remains owned-quote-0,33quotes persist, no late subscriber row.
This is lifecycle-green evidence, not a latency control or runtime qualification.

Incremental real controls passed: producer commit/cache/delivery order and pump
cursor position1; atomic second-book-insert failure via drain/tick/async3;
external thread actual COMMIT exception plus offline sync semantics1; entered
append/prune success/failure with stop join and waiting-producer cancellation4.
These check real DuckDB rollback/commit, not fake append outcomes.

A separate input ownership regression was observed on the new implementation:
caller clears a queued publish_many list while the first batch is pending;
only owned-quote-1 persisted instead of1+2. input-freeze-red records actual
failure. Moving deep copy before waiting on the sequence gate passes the exact
same test bytes (a2fea186...), input-freeze-green. No performance rerun occurred.

Source/test freeze for fresh complete-diff R1 at08:28SGT: feed SHA
5c0def6118e9a343c685bc86bee9675ccddd7dca37b83618dec860497d252c8b;
test SHA928f0816c3cf4176775ac47c00385b10f6e8cf17b9f5a69384d80dc22f36b0d2.
Initial Ruff found3 line-length errors; changed-file formatting resolved them,
then full src/tests/tools Ruff and whitespace passed. R1 is read-only, no
source delegates. Final affected checks are running; public synchronous caller
compatibility and complete shutdown ownership remain review gates, not assumed
from the passing controls. No push/CI/host/source admission or release claim.

Affected-r1 on frozen bytes:122passed/3failed/6warnings in28.16s, raw receipt
preserved. Existing TestLifespan expects `_loop is not None` after shutdown;
the candidate currently clears it. Existing candle-revision and metric-burst
pump tests wait for3durable quote rows via buffer.replay then immediately inspect
subscriber; they observed no quote delivery in the newly exposed commit-to-
loop-application interval. These failures are not waived and existing tests
remain unmodified. Fresh R1 is assessing lifecycle/public-call compatibility
and this contract difference before any next source decision. No green-suite
or release readiness claim; source/test freeze is maintained during review.

R1 returned NOT READY with two P2 findings: an individually cancelled entered
publisher could commit but never apply, and the affected boundary was failing.
The review's source deduction was reproduced using actual DuckDB: publication
commit succeeded while the active feed snapshot remained None. Raw
publisher-cancel-red and publisher-cancel-green retain identical new test bytes
2b72cd7c..., with original frozen source5c0def61... RED and sourceba65cfb0... GREEN.
Accepted work now runs independently of its caller's cancellation once physical
I/O starts; that caller joins commit/cache/delivery before observing cancellation.
Cancellation while still queued cancels the queued request without starting I/O.
Stop continues to cancel owned requests after invalidating the generation, joins
physical work, and suppresses late cache/delivery. A further queued-cancellation
control and explicit cancelled-caller/no-orphan assertions were then added.

Planner concrete scope disposition: additionally own ONLY the completion waits
in tests/test_live_candle_revisions.py and test_live_observation_identity.py.
Both still run their original real pumps, streams and finite3second wait; the
final condition now collects actual subscriber delivery until all3quotes arrive.
The durable3quote count and every original identity/revision/dedup/content/order
assertion remain. This acknowledges the observable COMMIT-before-loop-application
interval; the original122PASS/3FAIL receipt and its hash are preserved, not waived.
No router test edits: feed retains its legacy `_loop` marker after stop, with
explicit stopped admission checks before async or foreign-thread submission.
The marker is not an acceptance or live-generation flag.

R2 source/test freeze: feedba65cfb0cf20e9ec802aa5fabc2c53ae80007075bdec3f837ca79f300ef34c0e;
focused testde5cd5d549b92b1e644b84429721cbed63e73745c06d7a865ee9051891ebe234;
candle testfe8a245b3f12ffd27abe426440a9d9c7e5251b832af88c39153019be45bb21eb;
identity test24a668e1c495184b2d48c0d907646e4bbe2f1a74abe905957c237889650c0320.
Changed-file format, full src/tests/tools Ruff and whitespace pass. Submodule
status lists only unchanged uninitialized pinned entries; none initialized.
One final affected refresh is in progress on these bytes; R2 and immutable
checkpoint remain pending. No broader suite retry, push, CI, host or latency run.

Final affected refresh `affected-final-r2` completed on the four hashes above:
127passed/6existing warnings in25.41s, exit0; raw output SHA256
e56e0517ab870d63269c3231729c043f6f7e0afcaff420b704686c41b2f38fce.
This is13focused owned-persistence cases plus114affected existing cases, including
the three previously failing checks after their explicit narrow resolution.
R2 remains the independent review gate; neither this run nor old tiny-fixture
evidence qualifies production retained-scale performance or formal live startup.

Reviewer final R2: READY for this bounded functional source checkpoint; both
R1 P2 findings closed, zero remaining P1/P2 findings. The independent reviewer
read the narrow delta, verified all four frozen hashes and hash-matched actual
127PASS evidence, and wrote REVIEW-R2.md without rerunning tests or editing
source. No third review round was used. Final changed-file format check and
whitespace pass on the same source/test bytes. This checkpoint contains only
the six authorized source/test/record paths, on branch
codex/0038-live-owned-persistence with baseaa62faeddd84c31887e43bf0dae532e649a4ecbe.
The source seat is now frozen for local immutable handoff; release owner must
consume its exact commit and normal release gates before any deployment.
No push, CI, merge, host changes, new recovery pair, old-history read, third
latency calibration or dependency changes were performed in this functional
leaf. The accepted observable result is ordered persisted-to-subscriber
publication with owned cancellation/stop, not a production responsiveness claim.
