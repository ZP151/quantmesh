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
