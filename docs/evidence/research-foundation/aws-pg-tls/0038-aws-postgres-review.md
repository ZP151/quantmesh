# New cloud PG protocol recipe — bounded automated review

Scope: output/qualify_aws_postgres_tls.py only, final SHA256
66668da480d767a40809b5eaf58692cd31aa6027dbae954bd401670b14682aea.
Reviewer /root/unexpected_poll_failure_review; static only, not human release
approval or production-service qualification. Prior PG/backup/construction
architecture and completed tests were not reviewed again.

Initial findings: P2 stop validation depended on ready/log/resource acceptance,
leaving an owned postmaster after startup/acceptance failure. P2 finally wrote
a receipt whenever a rejected existing/symlink fixture existed. Root separates
ownership-only stop and gates writes on newly-created canonical UID0700 fixture.

Correction review confirms both, then identifies remaining P2 capture window:
Popen succeeds before pidfd/proc identity capture; capture failure leaves a live
child. Root binds original Popen/parent/fixed rehashed argv under single-thread/
SIGCHLD-default/no-other-reaper constraint, before any SQL. Its un-reaped direct
child cannot have its PID reused; fallback signals/waits only that owned child.
After complete capture the normal path remains pidfd/start/exe/data/system-ID.

Final reviewer: remaining P2 closed under those constraints; fixed capture-failure
fixture fails before SQL and preserves failed exit/cleanup. No new concrete P1/P2.
Actual subsequent evidence independently verifies rejected-link RED/GREEN,
forced capture failure exit1/stopped/portreleased, all15protocol checks0 and
log-limit refusal followed by verified own stop0. Tests are disposable protocol
fixtures, not jobs/reports. See hashed receipts for actual host and source bytes.
