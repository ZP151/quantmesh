# #173 Spec review — round 2 (final)

**Clear: all three round-1 findings resolved; no actionable blocking regression found.** Reviewed `ed5c12ea78c4a0a43f65b9c6d4e55ba6610e2407..b9daa42830ac240dc8354e457485a6f0e87ca297` in the original Task 3 scope.

- Authoritative inputs: `LocalResearchClient` now rejects absent/different `store.lake_root` and derives options from that root. This satisfies Task 3's authoritative Worker input-root requirement; the mismatched-root regression fails before the fix and passes afterward.
- Cancellation/status: the status-read generation invalidates outstanding reads on cancellation, submission and clearing. `accept` additionally fences job/request/implementation identity, older update timestamps, terminal-state regression and lost cancellation flags. The reversed GET/cancel regression now retains the confirmed cancellation.
- Report identity: asynchronous cache restoration and report opening check the currently selected job after SHA verification. The delayed restoration/new-submission regression no longer displays A's report beneath B.

The additional definitive-refusal recovery retains the original key/payload and permits an explicit reconfiguration only after 409/422; an ambiguous retry first durably removes the old refusal affordance. Historical reports remain bound to their recorded implementation digest rather than today's engine build. These changes support the existing durable-reload/idempotency scope.

Reviewed saved evidence, without rerunning broad suites: targeted UI 14 passed and backend 2 passed; API boundary 223 passed/1 skipped; frontend 419 passed/33 files; schema/typecheck/lint/build exit 0. The exact-head `browser-reviewed-witness.json` and exit-0 log bind the Windows risk-parity receipt to candidate `b9daa428...`, 10 numerical windows, positive fees/spread/slippage, 3641-byte report and byte-equal download. The DOM snapshots show authoritative versus retained status/time and report continuity during research 503, with Markets 200. Agent output/usage/cost remain explicitly unavailable; this is labelled fixture evidence.

No scope creep found. This final #173 Spec review does not certify PostgreSQL/Linux deployment, real market charts/model calls, AWS operation or deferred operational acceptance. No third structural review is requested.
