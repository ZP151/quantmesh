# SSE startup readiness without a competing bind

Issue #172 / PR #175, exact parent f5e38ea. CI38584253826 has4928 passing,
141 skipped and two SSE setup errors. Its full pytest stderr shows EADDRINUSE
on127.0.0.1:8644; the server thread exits3 while readiness repeatedly binds the
same port. This is a fixture startup race, not evidence of a production outage.

Planner: keep the existing real HTTP SSE user-loop assertions, initial occupied
port refusal and bounded shutdown. Replace only startup readiness with the
existing repository `server.started` pattern. No runtime, retention, dependency,
kernel or trading changes; no timeout increase or test skip. Execute inline,
one independent scoped review. Initial2MB diagnostic phase/cumulative57MB
reservation includes archive95,911B, extracted594,972B. Actual RED test root
adds800,815B, leaving insufficient headroom for the complete module GREEN.
Before that run, refine the same software phase ceiling to8MB/cumulative63MB
without resetting prior accounting. It includes both fresh WSL test roots,
source/docs/git reserve. Preserve failures/baselines and >=50GB free.

- [x] Add a real-server fixture regression which permits its initial port check
  but fails any readiness bind; run it on existing WSL Python to preserve RED.
- [x] Change `tests/test_live_router.py` helper to accept its actual server and
  poll `started`; leave initial port guard and join unchanged.
- [x] Run the entire live-router module including real SSE, bounded timeout150s,
  fresh native WSL basetemp, no cache/new environment/full-suite repeat.
- [ ] Ruff/format/diff, one bounded reviewer, resource receipt and mirrored
  CONTEXT/ACTIVE/iteration checkpoint; commit/push exact parent branch.
- [ ] Observe new exact-head CI; no failed-run rerun, merge/deploy before gates.

Actual RED1fail on second bind; GREEN36pass/15.13s including both SSE cases. Actual GREENroot58,316,685B exceeds8MB phase allocation: retain FAILED gate. Before checkpoint work reserve2MB/cumulative112MB, carry all prior bytes/failures/whole-C pending forward, no cleanup/reset/paid change.
