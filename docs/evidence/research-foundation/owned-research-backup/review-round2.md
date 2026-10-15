# Owned research backup review — round 2

Candidate: `3b3c2b72eb301ce5ebeaaa1a14d2736b09250c0f`. Compared `0503d49a51fdd20b08c809f4289092fbac01ebf9...3b3c2b72eb301ce5ebeaaa1a14d2736b09250c0f`; exactly the three permitted additions. Current file blobs equal candidate blobs. Read-only review against the binding owned-backup plan and repository contracts; no native/resource/database/restic execution, downloads, agents or tracked edits.

## Spec

- **P2 — A startup interruption can leave a newly spawned process outside cleanup** (`tools/qualify_research_backup.py:599–618`; analogous command window at `438–449`). After `Popen` returns, `process_ticks(process.pid)` executes before the cluster assignment and registration. The new fixture-wide SIGALRM can raise during that window; a tick-read failure has the same effect. Then `cluster` is still `None`, startup cleanup skips stopping it, and the outer cleanup list never contains the newly spawned postmaster. An owned server can keep running beyond the wall bound without a pending-resource entry in the witness. Similarly, fixed commands acquire ticks before entering their cleanup `try`. This conflicts with “Close only new owned ... resources” and the bounded overall witness. Make spawning/handle registration interruption-safe, then acquire identity inside guarded cleanup; retain explicit pending evidence if identity cannot be established, without granting unverified stop authority. Add a failure-path test where tick acquisition raises immediately after successful spawning. This is a static failure-path finding; the retained successful run does not exhibit a leak.

Round-one attribution and log/deadline fixes otherwise hold: only dedicated attributed refusals qualify; actual crypto exits/messages are checked; SIGALRM covers SQL/file stages; final deadline admission and capped PG pipe draining are present. Generated pgpass removal now runs independently of stop authorization.

Independently rehashed captured/recovered manifests, 14,781-byte dumps and the 257-byte labelled report: all match their anchors. Full captured/restored SQL agrees, including completed/reserved effects and outbox lease. Advanced source has four jobs versus three captured/restored and changes the queued job to cancelled. Raw restic logs show wrong-password exit12 and ciphertext-verification exit1. Code performs actual incompatible-schema SQL mutation/store refusal and separate missing/substituted byte/manifest refusals, checking source state after each.

## Standards

No separate actionable P1/P2 documented-standard violation. The change reuses fixed external tools and frozen publisher/store validators, introduces no shared contract/runtime dependency changes, and retains explicit fixture/production boundaries. The lifecycle finding above is also relevant to the ownership contract, without counting it twice.

## Evidence and minor notes

RED records 7 failures/32 passes; GREEN and exact-candidate native tests record 40 passes/exit0. Original service JUnit records85 tests/zero failures/errors/skips with all five PostgreSQL cases;81 licences remain unchanged. Raw logs show four distinct PG18.6 cluster starts and completed shutdowns. Independent final cleanup reports all five backup/gate PIDs absent, private inputs removed and six original/copied PG hashes unchanged. Formatting, Ruff and diff checks pass.

Minor: the tool-admission unit case exercises missing evidence rather than distinct signature/notice/pin tampering; retain as future test strengthening. Actual qualification remains `OWNED_LOCAL_FIXTURE_ONLY`, `production_release_qualified=false`; off-host/paid production recovery, actual Worker reports/recovery, p95/human/CI/deployment remain pending. This closes round2; no third structural review.

Totals: Spec1 P2; Standards0 P1/P2; no P1 findings.


## Scoped disposition at 349d9695fd80258fcf45eb1e6d7c21ebbfaacf0e

**P2 partially closed.** The cluster branch now defers SIGALRM, registers its handle before kernel-tick acquisition, checks deferred expiry immediately, preserves unknown-tick cleanup evidence without stop authority, and removes private inputs. Registration RED shows2 failures/40 passes; GREEN shows42 passes, including both reported cluster transitions.

The explicitly reported analogous `bounded_process` branch remains unchanged: `Popen` and `process_ticks` precede its cleanup `try`, and `Commands.run` does not defer deadline delivery during that window. A timer/tick exception can still bypass cleanup for an owned fixed-command child. The original P2 therefore remains open for that branch. This is disposition of the existing finding only, with no third structural review. Fresh final-native qualification remains pending.


## Final scoped disposition at 4fceaf21af3fbe513fc1b02b210d2305112bfca7

**Remaining P2 closed.** Fixed commands now defer deadline delivery before spawning, register CommandProcess before tick acquisition, guard acquisition with cleanup, and retain unknown identity as pending without signal authority. Fixture cleanup reports every handle. The genuine-child RED reproduces the old leak; the native regression uses real Popen/SIGALRM/cleanup and records terminal exit-15. Exact native45 tests pass. Final proof records17 stopped command handles, four stopped clusters, no cleanup failures and exit0; raw crypto errors retain exits12/1. This completes disposition of the original finding only: no outstanding P1/P2 from round2 and no third structural review. Scope remains OWNED_LOCAL_FIXTURE_ONLY; production_release_qualified=false.



