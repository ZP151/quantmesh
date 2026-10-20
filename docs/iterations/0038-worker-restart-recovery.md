# Worker restart recovery — issue198

Issue: https://github.com/ZP151/quantmesh/issues/198

Planner: controlled restart during two fixture jobs must recover the same job IDs
within the existing90-second recovery bound. Original failed jobs, requests,
terminal states and accounting remain immutable. This checkpoint initially covers
only redundant inventory path traversal; no lease lifecycle change is implemented.

Quant researcher: synthetic fixture and operational latency evidence only. Neither
an inventory benchmark nor retained result bytes prove published recovery or
strategy validity. No new data, paid access, model invocation or trading authority.

Diagnosis: the original pair reclaimed attempt2 after approximately49/55seconds of
lease wait; receipt creation consumed approximately81/88seconds of each complete
90-second attempt. Postcompute verification was still mandatory. Actual exact-image
diagnostic measured9222files and18534 `_path` calls; profiling and unprofiled times
are separate. All old failures remain in the private server-closeout evidence.

Implementer scope: in `worker_build._inventory`, avoid the duplicate ancestor walk
for each regular file within one pass. Check original canonical name before Path
normalization, retain `_read` ancestor/no-follow/held-inode/before-after checks,
all byte hashes, exact membership, links and metadata checks. No cross-pass cache,
no omitted scan, no changed22pins or deadline. Reuse existing Path/_read machinery;
no upstream code, package or license change.

Verifier: add a deterministic filesystem-work bound and cross-pass byte-drift
regression, observe RED before implementation, then run affected security tests.
Record exact commands/results before the coherent commit and final PR.

Actual WSL Python3.12 evidence: the two new tests first produced1failed/1passed,
with the intended filesystem-work failure `{2} != {1}`. After the minimal source
change, all58tests in `tests/test_worker_build.py` passed (one existing calendar
deprecation warning). Full Ruff passed; changed-file formatting was corrected and
then passed. The independent Reviewer returned READY with noP1/P2. Their separate
Windows probe failed in unchanged `_read` inode checks; it is a platform limitation,
not substituted for the Linux result. The broader native suite is separately
recorded under `output/0038-worker-inventory/`; completion is not yet claimed.

Reproduction record (WSL, Python3.12, external venv):

```text
RED: on base a2d95980fb214ddb4715225fe347680f0e29d4cf, with the two candidate
regression tests copied into tests/test_worker_build.py:
cd /mnt/c/Users/15492/.codex-clean/worktrees/pr199-red-check && PYTHONPATH="$PWD/src:$PWD:$PWD/src/quantmesh/research" /var/tmp/quantmesh-backup-final-xvcv1u9k/venv/bin/python -m pytest tests/test_worker_build.py -k "inventory_walks_each_regular_file_ancestors_once_per_pass or inventory_rehashes_file_bytes_on_every_pass"
Result: 1 failed, 1 passed, 56 deselected; the bound failed as {2} != {1}.

GREEN: against the synchronized PR source tree from repository root:
Command: cd /mnt/c/Users/15492/.codex-clean/worktrees/pr199-final-sync/QuantMesh && PYTHONPATH="$PWD/src:$PWD:$PWD/src/quantmesh/research" /var/tmp/quantmesh-backup-final-xvcv1u9k/venv/bin/python -m pytest tests/test_worker_build.py
Result: 58 passed, 1 warning in 5.26s (existing NumPy timedelta deprecation).

Broad-run record: the exact shell command and absolute PYTHONPATH values were not
retained in the session artifacts, so they cannot be reproduced verbatim from this
checkpoint. The first broad invocation exited 2 after 614.83s with 11 failed,
557 passed, 6 skipped; child interpreters reported `No module named quantmesh`.
The corrected invocation supplied explicit absolute source/root/service PYTHONPATH
entries and exited 2 after a deliberate KeyboardInterrupt at 665.96s with 568
passed, 6 skipped, 6 warnings. This was bounded/incomplete and is not a full-suite
pass. Output files in `output/0038-worker-inventory/` are local ignored artifacts,
not committed evidence; the counts above are transcribed from those saved outputs.
```

The first broad WSL invocation was interrupted after614.83seconds with11failed,
557passed and6skipped; subprocess traces include `No module named quantmesh`.
The existing external venv does not install this checkout as an editable package;
pytest's own pythonpath does not propagate to those child interpreters. A second
invocation supplies explicit absolute source/root/service PYTHONPATH to the same
existing venv, without installation or source changes. Its final result and CI
remain required; the interrupted run is retained, never counted as a full pass.

Merge classB: new exact-diff independent human review and required CI green;
existing PR186 or scoped OpenD/Advisory approvals are not reused for this source
change. No unmerged deployment or new production pair occurs from this branch.

Reviewer: independent review is required at the completed bounded diff. This
checkpoint cannot certify a new production pair, which requires normal merge and
new exact merged-image/native admission first.

Pending separate lifecycle design: only explicit controlled first-stop reason and
proven child cleanup could permit fenced early lease expiry. Generic stop Event,
constructor interruption, unknown/failed cleanup, stale owner or terminal state
must not qualify. No such source or operational override exists in this slice.
