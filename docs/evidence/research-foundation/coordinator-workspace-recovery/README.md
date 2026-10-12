# Coordinator checkout recovery

Actual read-only witness captured2026-10-12T23:09:40UTC / Oct13Singapore.
Original6e1e has no Git metadata and is absent from the common repository's
registered worktrees. Its remaining ignored output still exists and was left
untouched. These observations establish missing registration/files, not who
removed them or why. No cause is inferred.

Native create_worktree returned calling-cwd-not-a-Git-repository; attempting to
attach the standard-Git fallback returned checkout-not-managed. The new
`0038-research-integration/QuantMesh` checkout is Git-registered and clean at
the observed integration headc800750, matching the pushed branch and containing
the frozen5788cf7. It is not app-managed. Future shell commands must explicitly
use the new root; app-tool calls that depend on the old caller cwd remain limited.
No registry metadata was fabricated to bypass that check.

The local mainc74ea03 and origin/main745a231 were observed separately and left
in place. No reset, old-folder deletion, operational deployment, authentication
or source request occurred. Existing ignored source/service/browser artifacts
remain at their original historical paths; tracked proof archives were restored
from Git. This is coordinator continuity evidence, not an application recovery
or production backup qualification.

`sha256.json` identifies the raw witness bytes; the current_clean field refers
to the inspection before adding this archive, not a claim about later edits.
