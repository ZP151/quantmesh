# Spec review ROUND1 — f99b020

Base: 5788cf7057b7d9670982a16cc9bd3aaae01b83c2. Candidate: f99b020153a31d7d8a5265c9795edbd5a7884ddb. Scope: the three assigned files only.

No actionable spec findings. No missing, incorrectly implemented, or out-of-scope requirement identified in this bounded review.

The binding plan requires “Validate inherited terminal descriptors without reading input” and “every child held behind admission until handle/identity registered.” Admission checks descriptor types/access, native character-terminal identity, owner, exact 0600 mode, ECHO/ECHONL and replacement; retained duplicates and final rechecks precede release. Process registration retains Popen/pidfd and owned proc identity; SIGINT is masked across creation/registration and restored within the failure-cleanup guard. Missing identity/handle closes admission and waits for independent gated exit without bare-PID signalling.

The plan requires “Total owned fixture deadline90seconds including startup/failure/cleanup” and “a known sibling survives each individual termination.” Shared 80/89-second work/cleanup cutoffs, independent child expiry, bounded pipe/master observations and retained pidfd cleanup implement that boundary. Native receipts show disconnect/SIGHUP, blocked child, output growth, admission timeout and registration/handle failure terminating with sibling survival. The documented indefinitely hung-kernel exclusion does not promote unknown cleanup to success.

The requirement “production_release_qualified=false and source_host_private_input_verified=false even on a genuine local fixture pass” is preserved in code and runbook. Subsequent one-shot staging authority, actual-host proof, human authentication and SDK/source acceptance remain explicit gates; no installation or broader qualification is claimed.

Evidence inspected, not rerun: green4 native context and test log (38 passed), fixture JSON (Linux CPython 3.12.3 x86_64, UID 1000, 2.181258 seconds, all owned children terminal, 65 accepted bytes, four observed ACK bytes, no echoed marker), and clean candidate HEAD. Deadline-exhaustion branches were reviewed statically; the receipt demonstrates normal execution and named fault cases, not arbitrary scheduler/kernel failure.
