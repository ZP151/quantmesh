# One official-class compatibility implementation — issue301

Goal: a single informative, ordinarily closed official-client observation on the
unchanged logged-in provider. This plan follows offline preparation de2dd872 and
sole preparation R2 7403c1f4; neither qualifies runtime. The original preparation
clock20:01:50Z/15669s remains. The separate35–50min implementation estimate is not
a service-success promise. Original Server is author and sole remote executor.

Reuse the existing isolated worktree/branch and SourceM de245. New private files
only in E3/operator-official-client-01 and this plan's SDD directory; tracked
changes are docs. Never alter the installed SDK or Source7. No generic transport,
observer, provider/login/restart, data/capture/trading or historical-replay work.
One final fresh reviewer, at most R1 plus one correction/R2; structural failure
then returns to Planner. Existing status01/02 stay SPENT and fully charged.

## Binding interfaces and ruling

Actor.run_once(helper,plan,writer,clock,may,observe) retains the existing callable
interface. It returns qm.opend.official-result.v1 with the old bounded status/
reservation/log/close fields plus diagnostic, policy_clear and joined Init-worker
proof. Entry strictly validates this new result on both REFUSED and STATUS;
old health-result.v1 remains unchanged in its original package. Existing outer
entry/packet source/kernel/once/owned-peer/resource/transport controls are reused.
New fixed purpose/root/unit/local runtime and receipt05167978 replace only old
identity constants. Parent and durable consumer retain the SAME diagnostic.

Ruling: the actual class remains sdk.OpenQuoteContext with per-instance guarded
official-method delegates; no Health subclass. Holding its existing RLock around
the original _wait_reconnect(0) retains the actual initial Timer before its
callback can take that lock/clear the field. Original class/method provenance is
verified before installing wrappers. The initial Timer is allowed exactly once;
_auto_reconnect=False before first original Init; all later entry/connect/send
attempts sticky-refuse. Keep raw protocol guards shared across both threads.
Because state pack can precede Init pack, use two protocol-keyed expected packet
identities, never one shared pending packet slot. Other protocols0.

Ruling: preserve async constructor, timeout10 and one state call semantics, with
no added wait/retry. Ordinary close may interrupt a still-running Init after
connection-eligibility timeout. Diagnostic must mark Init-return-before-close vs
own close interruption; interrupted Init cannot imply provider no-response cause.
The retained actual Timer, callback and socket must close/join under120s total/
30s close, otherwise CLOSE_UNKNOWN. First finite failure, codes and fixed flags
survive the same terminal even when later close changes the Init outcome.

## Steps and acceptance

- [x] RED: actual new actor absent/old actor cannot produce strict new diagnostic,
  original-class identity, async packet-order/worker-close tests. Preserve logs.
- [x] Implement one bounded actor, using authenticated SDK loader, typed pack/
  send/query delegates, fixed finite exception/guard projection, unchanged MAY
  order and sticky reservations. Keep source/import inert and default unarmed.
- [x] RED strict terminal and real consumer: reject old/wrong/extra schema,
  policy contradictions and missing worker proof; retain valid REFUSED and STATUS
  diagnostic through pending/local terminal. Implement minimal entry/packet delta.
- [x] Run actual pinned SDK only against a fresh local synthetic provider under
  process audit fence. Cover success, Init error/no response, async state-before-
  Init pack, implicit forbidden send/retry, close race, close failure, private
  payload suppression. Assert <=1 connect/Init/state; actual thread/socket joins.
- [x] Current qualification: changed tests, Ruff/format, inert imports and exact
  SourceM/reverse outer delta; full96 real carrier vectors fit unchanged caps.
  Census retained artifacts plus full future under existing128MiB; stop before
  exceeding, no borrowing from runtime or deletion. One independent whole delta
  review and at most one consolidated correction, freeze complete candidate.
- [x] Bind all layers to receipt051679781684a5a9fa1a69e4b40424b6806ed726b7c191d1ba6ddb5c4adf7262
  (3916B), new officialcompat33f-01 root/unit/local as registered. No second32MiB.
- [x] Sole executor checks current source/review/freeze/true physical identity/
  native5s and immutable issued-capacity210s/once/close. Consume the one new
  purpose only after all real guards pass; retain complete result and ordinary
  transport close. Any failure is SPENT; return one informative route ruling,
  no nonce change/replay/capture. No ordinary permission or login repeat.

Runtime caps remain512MiB/swap0/CPU50/Tasks32/runtime180/transport210/stdout8192,
carrier327680/encoded262144/decompressed1MiB. Registered newruntimeL8/R24MiB;
all-parent guarded stress6306907150<6442450944, Gguard12288356442<12884901888,
real free>=50GiB. Ledger commitments are not physical samples.

Validation commands: existing .venv python -I -B -m pytest -q <new targeted files>
-p no:cacheprovider; existing Ruff check/format --no-cache <new python>; current
inert/geometry/census scripts with -I -S -B. Broad old suites/CI are not rerun for
this private implementation; no tracked production source changes are planned.
Record actual targeted evidence, review, resource provenance and result in the
active iteration; branch docs checkpoint normally committed/pushed.

Completion evidence: actual purpose STOP/SPENT with finite STATE SDK_NON_OK/-1,
policy-clear/Init-queued/no-receive observations and ordinary SDK4ms/all owned
closure. Result1582B/ad9dba9b, public readback6904B/78f83a6c, closeout6411B/
196587a7. This completes the engineering/one-observation plan, not SDK usability,
provider/root-cause, data or financial qualification. No retries or new scope
were started. See the active iteration and checkpoint20261108T013650Z/d070134a.
