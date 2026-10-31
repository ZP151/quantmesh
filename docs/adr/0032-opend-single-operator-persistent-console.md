# ADR-0032 — Explicit single-operator persistent OpenD console

Date:2026-10-19. Status: accepted for the explicitly requested implementation;
actual release, private login, authentication and SDK evidence remain separate.
Issue:[#192](https://github.com/ZP151/quantmesh/issues/192).

The human clarified that earlier operator/reviewer/SafetyOwner roles were one
person, assigned the alias Operator, and explicitly requested changing the flow
to single-person approval and keeping the login process running. Do not encode
one person as two independent reviewers. This request overrides the historical
OpenD two-person and expiring-window approval scope only, not the advisory key
boundary or trading authority.

Add an explicit schema2 persistent permit and separate console unit to the
existing guarded launcher. A fresh one-shot900second permit admits initial
release only. Once admitted, this process remains owned until controlled stop
or exit, with no900second vendor alarm. Preserve schema1 stage semantics and
the separate production/source qualification flags. Root protects the permit;
actual merged-source checks and independent technical review precede deployment.

Reuse the existing pinned tmux, terminal checks, guarded child registration,
pidfds, parent-death protection and control-group cleanup. Bound the persistent
unit to1GiB memory, swap0, CPU50% and128tasks. Disable automatic restart and
boot enablement so no stored password or automatic login becomes necessary.
The human alone operates the private terminal. Credential/vendor state and
terminal bytes are never observed by the assistant, logged or copied.

The consequence is an explicitly trusted single human, not two-person control.
A persistent process can survive SSH-client detach but cannot guarantee vendor
session validity or reauthentication after process/host exit. Keep exact host,
source/vendor/unit/config pins, loopback11112, original11111 rollback route and
paper/live invariants. A launched login pane grants no SDK/market qualification
and does not switch application endpoints.

## Same-unit recovery amendment — 2026-10-31

Issue [261](https://github.com/ZP151/quantmesh/issues/261) adds one separate,
short-lived schema3 recovery control for the existing persistent unit. Preserve
the spent initial claim and prior public permit; bind their actual identities
along with source/vendor/host/service identity. Fixed check/prepare/pane commands
select a present recovery control and fail closed if it is invalid. One private
O_EXCL marker is consumed at the final owned-child gate; checks do not consume,
and any failure after consumption remains spent. No automatic restart, nonce
reset, new unit, credential transport or market qualification follows.

The existing operator repair/start/login and standard agent-review/normal-merge
authorization selects this bounded implementation. It is not a new independent
human review fact or a global change to repository review policy. Actual merged
deployment, resource/native/source/provider gates and login remain separate.
See the [specification](../superpowers/specs/2026-10-31-opend-same-unit-recovery.md)
and [checkpoint](../iterations/0038-opend-same-unit-recovery.md).
