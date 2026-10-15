# Bounded data-reader review receipt

Reviewed file: `output/inspect_aws_numeric_layers.py`.

## Initial findings

Initial reviewed SHA256: `CEBA094909EEE195CF929B2BF42D0DCF40258968B4F83B89ED270A39063E9A54`.

- P2: inline whiteouts could remove same-layer additions; non-directory replacement retained descendants; regular ancestors were accepted; late hardlink pathname resolution could retarget content after source replacement.
- P2: manifest/config and ownership/receipt JSON were read before enforcing file identity, link, ownership and byte-size constraints.

## Correction disposition

Actual correction reviewed SHA256: `0AE26C000FA1969453F1902D78071C29D6FB4C035F6975B20B53BB5390B40767`.

Clear within the two corrections: both original P2 findings closed; no additional P1/P2 found in this bounded review. Whiteouts apply to lower nodes before staged entries. Non-directory replacement removes descendants; member and resolution ancestors must be directories. Hardlinks require an existing regular target and snapshot its original payload layer, TAR ordinal, name and hash. Final selected notice reads bind that payload instead of a subsequently replaced source pathname.

`bounded_read` checks canonical paths without links, regular-file type, UID, link count and size before reading. It enforces a strict byte bound and checks descriptor and named-file identity before/after reading. Manifest/config digest verification and JSON parsing use the same collected bytes.

Inspected retained evidence: `output/0038-aws-numeric-virtual-counterexamples.json` and `.exit` report 10 checks and exit 0, binding the exact correction hash above. Cases cover lower-only opaque whiteouts with new entries; non-directory replacement; hardlink snapshots, source replacement and later whiteout; regular/symlink member ancestors; forward hardlinks; regular resolution ancestors; cycles and root escape. Scope is synthetic data-overlay counterexamples exercising extracted merger/resolver AST, not execution of the complete reader. The initial AST-selector assertion failed before any case; the selector was corrected and the original script/exit retained. That harness error is not a production RED claim.

## Limits and later evidence

This was a static correction review plus inspection of retained synthetic receipts. The reviewer did not execute the reader remotely, download bytes, extract a rootfs, run Docker, or qualify an image, runtime or native numerical closure.

Root subsequently reported remote success for the first reader with 77 selected notices and for a later full-selection version with 91 files, including 14 common-license bodies. The later two-line phase/filter version has SHA256 `B33C6502B024082F19E6229F189E37F5833C963E46B59E70E7DEA9A9189E8FD8`; it was not the source hash reviewed above and is not newly reviewed by this persistence-only receipt. The originally reviewed source was preserved separately. These later reports do not turn this review into an image/runtime/native certificate.
