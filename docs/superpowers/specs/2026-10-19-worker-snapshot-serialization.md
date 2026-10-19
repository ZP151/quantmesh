# Worker snapshot serialization (#185)

Operator approval: direct “全部批准，继续执行” to concentrated decision B on
2026-10-19; exact approved TASK-CONTRACT SHA
08854a7b6fe9693fe54afe93e53c2b029f20a8b42c0c54ed20c48a38905a83ac.
Execution receipt is preserved in the server closeout output directory.

One user action: submit two registered fixture research jobs to the permanent
two-slot Worker. Success: valid sibling preparation no longer changes an ancestor
ctime inside another protected snapshot; numerical children can still overlap.

Use one private process-local standard-library lock in job_runner, covering
attempt-directory creation through completion of _snapshot, including bundle
creation. Release before runtime measurement, heartbeat and child execution.
Keep all existing DirectoryHandles identity/ctime/no-follow checks unchanged.
Waiting consumes the original monotonic job timeout and observes cooperative
Worker stop; timeout must not create an attempt or launch a child. Exceptions
release the lock. No public signature/configuration, dependency or slot change.

This coordinates threads in one Worker process. Cross-process/external namespace
changes remain fail-closed; no distributed lock or ctime exemption is introduced.
No market strategy, data/cost semantics, report confidence, lease/publication
fence, OCI/resource/pin, credential, vendor or trading behavior changes.

Verification is software evidence with real local POSIX snapshot I/O and an
inert execution seam. Actual two-OCI-job/restart acceptance remains a later
merged-source deployment gate. New applicable human merge review and current CI
are required; approval of this design does not approve the future PR merge.
