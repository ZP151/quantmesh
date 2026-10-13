# Bounded native effect diagnosis

Status: **cause unresolved; historical native gate remains failed**. No native GREEN claim and no qualified-environment claim follows from these diagnostic repeats.

Exact read-only service source: `b10762883edc1bbad164951d1a1adfb9f0f7457c` at `/var/tmp/quantmesh-portfolio-runtime-aihe1p21/service-b107-checkout`. The original `service-b107-evidence/service-gate-3.log` records 135 passed, 5 PostgreSQL skips, and one `test_secret_and_order_fields_reject[credentials]` failure because state was `unavailable` instead of `failed`. It does **not** preserve that invocation's child private-pipe receipt, stage, type, exit code, or parent exception type. The precise original failure category cannot be recovered from that log.

Five diagnostic attempts were run, each under a 30-second outer limit; child communication was capped at 20 seconds. Three invoked the exact fixture/runner flow directly, and two invoked only the exact parametrized pytest node. Each used fresh owned fixtures and home directories, scripted transport only, and the existing contaminated venv strictly for diagnosis. Both parent and actual `bounded_complete` child used `-B -X pycache_prefix=<fresh owned directory>`; the probe-only Popen wrapper preserved the child worker and real Linux containment/resource caps. Budget remained 2048 MiB address-space, one CPU affinity, and the original 900-second CPU limit; the diagnostic wall limit was stricter. No package installs, full suite, PostgreSQL, server, remote transport, model, key, product edits, or source edits occurred.

| Attempt | Mode | Child return code | Child stage/type | Child elapsed (s) | Runner result |
|---|---|---:|---|---:|---|
| 1 | fixture/runner | 0 | null/null | 2.551 | failed / analysis_failed |
| 2 | fixture/runner | 0 | null/null | 2.598 | failed / analysis_failed |
| 3 | fixture/runner | 0 | null/null | 2.472 | failed / analysis_failed |
| 4 | exact pytest node | 0 | null/null | 2.627 | failed / analysis_failed |
| 5 | exact pytest node | 0 | null/null | 2.486 | failed / analysis_failed |

All five actual child receipts were successful envelopes (352 bytes), so there were no error stage/type fields to capture. Every runner recorded one scripted call and no output digest. Both targeted pytest invocations exited 0; these are diagnostic observations, not replacement acceptance evidence. All diagnostic directories contain zero `.pyc` files, and source `git status --porcelain --untracked-files=normal` remained empty. Existing shared-environment bytecode was neither deleted nor trusted.

Source evidence narrows the boundary but does not identify the historical exception: `effect_worker.py` emits only sanitized `{error, stage, type}` on a child exception, then exits 1; `bounded.py` throws away that receipt when return code is nonzero; `orchestrator.py` catches any effect-path exception and returns `unavailable/unknown_effect`. The same catch also covers parent serialization or effect-ledger response errors. Thus the recorded state cannot distinguish configuration, containment, effect, transport receipt, or parent/ledger failure. No evidence supports calling the original failure transient, specifically blaming the injected field, or diagnosing memory/timeout without its receipt.

Next safe action: after the root-owned bytecode-isolation repair and a fresh audited runtime, keep sanitized stage/type/returncode plus parent exception-type observation on the next bounded verification that includes the failing node. If failure recurs, use its actual category to select a minimal fix. Preserve the existing failed native gate receipt until that fresh verification and required gate checks complete.

Raw diagnostic script and sanitized outputs, relative to coordinator root `C:/Users/15492/.codex-clean/worktrees/0038-research-integration/QuantMesh`:

- `output/0038_effect_linux_probe.py`
- `output/0038-effect-linux-probe-1.stdout` and `.stderr` (stderr empty)
- `output/0038-effect-linux-probe-2.stdout` and `.stderr` (stderr empty)
- `output/0038-effect-linux-probe-3.stdout` and `.stderr` (stderr empty)
- `output/0038-effect-linux-probe-4.stdout` and `.stderr` (stderr empty)
- `output/0038-effect-linux-probe-5.stdout` and `.stderr` (stderr empty)

Fresh owned native fixture roots, retained for review:

- `/var/tmp/quantmesh-effect-diagnosis-mOKYWzzb`
- `/var/tmp/quantmesh-effect-diagnosis-hweonmoH`
- `/var/tmp/quantmesh-effect-diagnosis-gDD0N97b`
- `/var/tmp/quantmesh-effect-diagnosis-uvL8oGI9`
- `/var/tmp/quantmesh-effect-diagnosis-BABF4FMT`

Private-pipe request/pickle/response contents and credential values were not saved or printed. Only sanitized categories and non-content metadata were retained.
