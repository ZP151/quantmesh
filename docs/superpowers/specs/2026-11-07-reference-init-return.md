# Reference Init delegate return diagnostic

Issue: #293 (parent #281). This is the bounded software successor to the
closed reference9 NOT_READY result, not a proved root-cause repair.

One operator action runs the guarded reference. One additional finite fact
distinguishes an official synchronous Init failure from an OK return followed
by NOT_READY at the existing first sample. SDK10.10.7008's protected public
open_context_base.py395–415 already returns the needed integer; its successful
send path449–452 reaches the READY assignment675–685. The current override
discards that result. More specific packet/wait errors are not available in
this existing return object without new hooks or private message inspection.

Keep the existing override order and exactly one super delegate. Initialize
init_delegate_return=UNKNOWN; classify only exact int0 as OK and exact int-1
as NON_OK, all other objects/types/integers as UNKNOWN. Return the identical
object, propagate the identical exception, and inspect no message/response or
exception text. This scalar never participates in READY or admission.

New reference emission uses closed qm.ivv.reference-init-terminal.v2 and
qm.ivv.reference-init-observation.v2, adding only init_delegate_return.
Selectors retain strict historical v1 acceptance and reject version/field
mismatches or unknown enum strings. New runner/IPC/STOP and private Ops retain
the scalar; ordinary capture and every existing safety predicate remain intact.

No new SDK method override, hook, logger, callback, timer, socket, thread, guard,
dependency, environment or provider action. Do not change original capture,
READY comparison, exception/close, lease/once/MAY, sandbox/namespace, FD,
resource or normal manager1/client1 diagnostic rules. Old9/10 remain closed and
unreusable; external cumulative counts remain UNKNOWN. A new actual diagnostic
requires normal reviewed CI/merge/publication and separately registered new
immutable runtime data/capacity/once and fresh physical admission. No runtime
or capture follows merely from this specification or enum.
