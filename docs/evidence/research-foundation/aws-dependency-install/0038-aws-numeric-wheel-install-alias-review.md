# Narrow fixed base-pip alias review

Actual reviewed SHA256: `238C1BF14BB12E8B748B4E93DC23CEB0777F6B3A25D70D5089783A5AB14064CD` (`output/install_aws_numeric_wheels.py`). The new alias phase was unexecuted at review.

Disposition: clear within this exact bootstrap-alias correction; no substantive P1/P2 found in the changed boundary.

The removal block requires the fixed `/usr/local/bin/pip` path to be a symlink resolving to the fixed `/usr/local/bin/pip3` path. Both `pip3` and `pip3.12` must be regular non-symlink files with exact SHA256 `6d2cd44b1e30b4969035606e18bcbc4304d45aca49c693b8f2ae2fbca4fa5d87`. Both fixed pip/pip-25.0.1.dist-info directories must be directories without leaf symlinks. All checks precede every deletion. The alias is unlinked itself; its target is not passed to recursive deletion. Only the two named pip directories and two named scripts are then removed inside the already authorized disposable container layer. No generalized link acceptance, host deletion or native permission was added.

Inspected `0038-aws-numeric-base-pip-layout-diagnostic.json`: the pinned virtual base inventory reports the pip alias targeting pip3, two regular 230-byte scripts with that digest, and the two named directories; its scope is read-only path metadata, not execution qualification. This matches the new acceptance predicate.

Inspected `check_numeric_install_pip_alias.py` and existing alias RED/GREEN logs/exits: three real small Linux filesystem fixtures exercise the actual extracted removal block. Previously the expected alias was refused and an unexpected regular alias accepted (two failed checks/exit 1). The correction accepts the fixed alias and refuses wrong-target and regular-alias cases (zero failed checks/exit 0). The harness maps paths to fresh fixture roots and substitutes only the public test script hash in its extracted AST. This is explicitly a fixture substitution, not an operational production pin bypass; receipts state Engine/install not executed. It does not constitute a comprehensive adversarial filesystem or installed-image qualification.

Static review and reading retained receipts only; this reviewer ran no tests or remote installation. The A1 failed remove_pip receipt/source remains retained. The new phase retains the original baseline/resource and existing failed-output/exit/commit constraints; these old slices were not re-reviewed. No image/runtime/native certificate, source-to-binary equivalence or Option A completion is claimed.
