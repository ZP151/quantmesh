# Bounded offline dependency-install recipe review

Actual reviewed SHA256: `E641A408AC5CA67B3CC1E21757D04509EAC009AB43479AEC838E74DBCEE1C6A1` (`output/install_aws_numeric_wheels.py`). Recipe unexecuted at review.

## Finding

**P2 — Track a validated commit acknowledgement, not nonempty CLI output** (lines 130,151). `derived` receives stripped commit stdout before full sha256-ID validation. Unexpected nonempty output therefore causes refusal but prevents the final `if image_commit_requested and not derived` condition from recording `image_commit_completion=NOT_PROVEN`. No immutable candidate ID was acknowledged in that case, and a CLI result cannot establish daemon completion. Use a separate validated acknowledgement flag, or assign `derived` only after validation; retain NOT_PROVEN whenever the commit was requested without a validated/observed candidate. Keep any image/partial state and do not retry or globally remove it.

## Other scoped conclusions

No additional substantive P1/P2 found in the reviewed ownership, staged inputs, mount, finite installation and exact-CID cleanup paths. Host metadata/catalog/wheel/notice inputs use bounded owned regular-file reads with descriptor/named identity checks and exact approved hashes. Stage directories are explicitly 0755 and files 0644 under a fresh 0700 phase. The three inspected bind destinations/sources are exact and readonly; tmpfs is requested separately. The container requests no network or pull, cap-drop ALL, no-new-privileges, nonprivileged execution, finite pids/cpu/memory/swap/log settings, and a writable disposable layer for this installation only.

The canonical /usr/local Python command uses -B -I -S. Its pip invocation is isolated/offline, wheel-only, hash-required, no-deps/no-compile/no-cache. Frozen wheel bytes are checked before pip. Base bootstrap pip deletion is confined to the named paths within this disposable container layer; the child checks exact 81 distribution metadata and absence of site-package .pyc/.pth files afterward. Supplemental and bundled notices are copied as data. No Worker/WIP/job/model/vendor API import appears.

The recipe inspects owned CID/image/nonce before start, observes process exit/Pid/OOM before commit, and verifies the candidate label/base layer ancestry and one added layer. It stops only the re-inspected exact owned CID if needed, checks stopped/Pid=0, and removes without force. Unknown create completion preserves NOT_PROVEN; the commit acknowledgement finding above remains open. CLI timeouts are not daemon cancellation authority. Final resource accounting uses the original source baseline, whole 5 GB gate and 50 GB free floor; this is observation/gating rather than a kernel storage quota.

## Limits

Static read-only review only: no remote command, test, container creation/start, pip installation, commit, download or native probe was performed. The official base and exact frozen wheels are the explicitly authorized TCB for this finite materialization, not source-to-binary equivalence. Candidate metadata and dependency installation do not establish full file/ELF/native closure, loaded-code admission, effective kernel-profile qualification, numerical permission or Option A completion. Existing failures/partials and the original image remain retained.

## Commit-observer correction closeout

Actual corrected source SHA256: `86F7D65299F3776999657338F872152BE4792C2489A7444DBF3150D55CCC9295`.

Clear within this correction: the P2 is closed; no new substantive P1/P2 found in this changed boundary. `commit_observed` starts false and becomes true only after full candidate-ID validation plus actual image ID, base-layer ancestry, one new layer and exact nonce-label inspection checks succeed. Any requested commit without those observations retains `image_commit_completion=NOT_PROVEN`, including malformed nonempty stdout and a full ID followed by observer failure. No retry or broad image cleanup was added.

Inspected retained `0038-aws-numeric-install-commit-red.log/.exit` and `-green.log/.exit`: malformed nonempty ID and full-ID/failed-observer cases changed from two failed checks/exit 1 to both expected NOT_PROVEN outcomes, with all three cases matched/exit 0. The normal observed case remains matched. Receipts explicitly state software control-flow only and `install_executed=false`; the original E641 source is preserved as `install_aws_numeric_wheels-before-commit-observer.py`. The reviewer ran no tests or remote installation. All original certification limits remain.
