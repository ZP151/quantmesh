# Bounded wheel ZIP-reader pre-execution review

Actual reviewed SHA256: `C27D1CBA3276E8AB417562C4C38A6B447B4893EA3626670CFC3E8A3C1A42E235` (`output/inspect_aws_numeric_wheels.py`).

## Findings

1. **P2 — Validate the original ZIP member name before using its normalized alias** (line 55). CPython ZipInfo stores the original decoded name in `orig_filename` and truncates `filename` at the first NUL. Therefore `safe(info.filename)` cannot detect a raw name such as `LICENSE\0suffix`. Matching central/local raw names can still be opened, while the reader catalogs and compares RECORD using the truncated `LICENSE` alias. Validate `orig_filename` with the same strict path predicate and require exact equality with `filename` before member interpretation. This behavior is explicit in the [pinned CPython 3.12.15 ZIP implementation](https://raw.githubusercontent.com/python/cpython/v3.12.15/Lib/zipfile/__init__.py).

2. **P2 — Reject canonical file/directory conflicts and non-directory ancestors** (lines 53–59,67). Duplicate detection compares raw strings, so a regular member `a` and a directory member `a/` are distinct and accepted. A regular `a` and regular `a/b` are also accepted, with matching RECORD rows/hashes. Those entries cannot describe a coherent filesystem tree, but the emitted catalog treats them as successfully verified wheel files. Track canonical paths and explicit/implicit directory kinds; reject aliases with conflicting kinds and any regular-file ancestor. This is an interpretation defect, not a claim of host extraction or code execution.

## Other scoped conclusions and limits

The reviewed implementation opens owned regular inputs through nonblocking/no-follow descriptors, validates size/link count/UID, and checks wheel descriptor/named identity after its reads. Per-member streaming checks exact size, SHA256 RECORD entries and bounded totals; notices are retained under flat numeric host filenames. No tar/ZIP extraction to code paths, install/import, HTTP or Docker operation appears. The captured sole unreaped child is stopped through pidfd or the unreaped direct-child fallback, with bounded reap and explicit NOT_PROVEN if not reaped. No additional substantive P1/P2 found in those scoped ownership/resource/cleanup paths.

Static read-only review and primary CPython/wheel-format source inspection only. No remote command, download, test, extraction, wheel installation, Docker operation or native execution was performed. The script was unexecuted at review. Exact per-file RECORD verification does not itself qualify wheel compatibility, installation layout, license expressions, full ELF dependencies, source-to-binary equivalence, numerical/native admission or Option A completion.

## Path/tree correction closeout

Actual corrected source SHA256: `7BF195DFDC60E41C071CE747D6FE47F97069FAD9EFFEEB2362CC77FE0D74F783`.

Clear within the two requested path corrections: both original P2 findings closed; no new substantive P1/P2 found in these changed boundaries. `safe(info.orig_filename)` runs before exact comparison to `info.filename`, preventing NUL-truncated aliases. Path spelling accepts only the canonical form or one trailing slash. Canonical path uniqueness catches file/directory aliases; the completed tree check rejects any non-directory ancestor independently of archive order.

Inspected retained `0038-aws-numeric-wheel-tree-red.log/.exit` and `-green.log/.exit`: the NUL-name, file/directory-alias and non-directory-ancestor bad cases were accepted before the correction (three failed checks, exit 1), then refused after it (zero failed checks, exit 0). The normal positive case succeeds in both logs. The original source is preserved as `inspect_aws_numeric_wheels-before-tree-fix.py`. These are tiny synthetic ZIP interpreter fixtures with production pins bypassed only in the test harness; receipts explicitly deny native/container certification. This reviewer did not run the tests or any remote inventory/install operation. All original scope/certification limits remain.
