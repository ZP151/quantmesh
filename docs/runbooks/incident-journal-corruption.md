# Incident: journal corruption

## Symptoms

- A store read raises `ValueError` naming the file and line, e.g.
  `order journal ... line 17 is invalid: ...` (ADR-0006 fail-closed
  reads with line attribution).
- `export-audit` fails to load one of the four journals.
- Duplicate-id refusal at read time (`lines share a record id`).

## Checks

1. Identify the failing store and line from the error message.
2. Inspect the raw line: `sed -n '17p' <store>.jsonl` — look for a
   truncated tail, an external editor's partial write, or a
   non-UTF8 byte.
3. Confirm whether the corruption is a single line (external
   tamper / editor) or the file tail (a crash mid-append — the
   atomic discipline should make this impossible, so treat a
   tail truncation as a sign the discipline was bypassed).
4. Cross-check against the surviving surfaces: the audit bundle
   from the last verified export, the paper account state, and the
   other journals.

## Recovery

1. If the corrupt line is a tail fragment with no valid record in
   it, delete that line only (the record never completed an atomic
   write, so no acknowledged order is lost).
2. If a middle line is corrupt, reconstruct it from the last
   verified audit bundle (re-exported under the operator's key) and
   the surviving surfaces; never fabricate a record — an order that
   exists nowhere else is orphaned and must be reconciled, not
   invented.
3. Re-run `quantmesh ops export-audit` and `verify-export`; the
   bundle must verify.
4. If the paper account state disagrees with the repaired journal,
   run the recovery drill (`quantmesh ops recover`, M10 Phase B) and
   reconcile with the ADR-0006 tolerance.

## Prevent

- Every store write is atomic temp+replace by construction; a
  corrupt middle line implies out-of-band editing — restrict write
  access to the `~/.quantmesh` roots to the operator account.
