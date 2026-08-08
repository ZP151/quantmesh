# Threat model — QuantMesh local-first workstation

M10 Phase D (issue #61). The threat model for the local-first
workstation as built through M10: every threat is named with the
control that addresses it and the test that pins it. A threat with no
pinned control does not belong in this document — either it gets a
control or it is recorded as an accepted residual risk (the two
residuals below are the only ones).

## Scope and trust boundaries

- **Trusted**: the loopback-bound operator's browser and the local
  filesystem the operator owns. The workstation binds loopback only
  (ADR-0011 decision 2), so the network trust boundary is the
  machine itself; nothing else can reach the server at all.
- **Untrusted**: everything off the machine (the LAN, the internet,
  the operator's own browser tabs), and the persisted files as a
  durable adversary — crash- and tamper-arbitrary files must never
  produce wrong-but-plausible state.
- **The standing gate governs the whole surface**: real-money
  trading, wallet signing, live broker orders, credentials, paid
  infrastructure and AI order authority require explicit human
  approval (ADR-0012, iteration 0012, ACTIVE.md). Nothing in this
  model defends against a *live* execution path, because no live
  execution path exists.

## Threat register

| ID | Threat | Control | Pinned by |
| --- | --- | --- | --- |
| T-01 | Any non-loopback host reaches the server | loopback-only bind refused at construction | `test_non_loopback_host_refused`, `test_main_refuses_non_loopback_before_uvicorn` |
| T-02 | Script injection via rendered content | Jinja2 autoescape on every template | `test_hostile_symbol_escaped_on_render` |
| T-03 | Unauthorized writes / order placement | data plane is GET-only; exactly two write surfaces, both validated | `test_api_is_read_only`, `test_order_placement_is_not_exposed`, `test_unbound_watchlist_refuses_writes_fail_closed` |
| T-04 | Kill-switch bypass | enforcement in the accounting risk gate every submission crosses | `TestKillSwitchEnforcement` (6), E2E `test_kill_switch_keyboard_only` |
| T-05 | Journal corruption / tampering produces wrong state | ADR-0006 discipline: atomic writes, fail-closed reads with line attribution | `test_reconcile_detects_*`, `test_invalid_transition_tamper_raises_store_corruption`, `test_corrupt_kill_switches_fails_closed` |
| T-06 | Crash-duplicated or replayed submissions | idempotency keys; key-first replay; duplicate keys refused on read | `tests/test_recovery.py` (25) |
| T-07 | Credentials leak into code, logs, prompts or exports | KeyStore protocol + safe filenames; prompt redaction; structured logs carry no secrets | key-store traversal/dir-refusal tests in `tests/test_ops.py`; KeyringStore drill-refusal tests in `tests/test_enablement.py`; `tests/test_ai_redact.py` |
| T-08 | Model/agent misuse — order authority, tool abuse, prompt injection | M8 tool permissions enforced at dispatch; execution surface refuses hostile tool calls; kill switch not settable from any AI surface | `test_permission_enforcement_holds_at_dispatch`, `test_hostile_tool_call_to_execution_surface_is_refused`, ADR-0012 decision 3 |
| T-09 | Vulnerable or incompatible dependencies | CI `security` job: pip-audit over the locked environment + deterministic license review | `requirements-audit.txt`; `tools/license_review.py`; `docs/licenses.md` |
| T-10 | Hostile files on disk (symlinks, traversal, non-directory roots) | symlink rejection, root-not-dir and safe-filename refusals on every store | lake `_reject_symlinks` tests; `MetricsStore` root-not-dir refusal; key-store dir refusal |
| T-11 | Real-money / live / credential misuse | the recorded external human gate; enablement state machine refuses transitions without approval records (Phase E) | ADR-0012 decision 5, `docs/iterations/0012-m10-guarded-live-execution-and-hardening.md`, `docs/goals/ACTIVE.md` |
| T-12 | Availability — disk exhaustion, crash loops | incident runbooks; JSONL atomic temp+replace (never half-written state) | `test_incident_runbooks_present_and_structured`, ADR-0006 |
| T-13 | A tampered audit export passes as genuine | HMAC-SHA256-signed bundles; verification refuses tampered / wrong-key / missing bundles | 4 tamper drills in `tests/test_ops.py` |
| T-14 | Cross-site request forgery on the write surfaces | loopback bind (T-01) + Origin guard: a present non-loopback Origin is refused on every POST | `TestWriteSurfaceOriginGuard` (5) |
| T-15 | Hostile web form input to the write surfaces | typed form contracts; unknown venue/symbol refused with state untouched | `test_kill_switch_hostile_posts_refused`, `test_hostile_venue_refused_without_touching_state`, `test_remove_unknown_renders_error_page` |

## Per-threat detail

### T-01 Non-loopback access

The workstation and the M8 gateway refuse any non-loopback bind at
construction (`_is_loopback`: `localhost`, `::1`, the whole
`127.0.0.0/8`; anything else is a construction error, and the CLI
refuses to start uvicorn on it). This is the ADR-0010 loopback
discipline applied to both server surfaces.

### T-02 Script injection

Every template is autoescaped (ADR-0011 decision 2). A hostile
symbol or venue name renders as inert text — pinned by
`test_hostile_symbol_escaped_on_render`, and venue names are never
free text at all (they are `Venue` enum values, T-15).

### T-03 Unauthorized writes

The M1 data plane is GET-only (`test_api_is_read_only` proves the
method set); order placement is not exposed at all
(`test_order_placement_is_not_exposed`, 405). The workstation's only
write surfaces are the watchlist form and the kill-switch form, both
validated, both on the loopback-only server, both Origin-guarded
(T-14). An unbound watchlist refuses writes fail-closed.

### T-04 Kill-switch bypass

The global bit and per-venue map live on the same account object the
control page flips, and enforcement sits in the accounting risk gate
every submission crosses — before sequence consumption. No page,
model or adapter cooperates; no AI surface can set or clear the
switch (ADR-0012 decision 3). A refused submission is journaled as a
rejected order and replays as a refusal. The keyboard-only E2E drill
proves an operator can flip both the global and a per-venue switch
without a mouse.

### T-05 Journal corruption and tampering

All journals and stores are on the ADR-0006 discipline: atomic
temp+replace writes, fail-closed reads with line attribution, and
identity refusal (duplicate ids, duplicate idempotency keys). A
tampered fill price, a deleted event, a rewritten order header or a
hostile `kill_switches` payload each fail the read closed or are
named by the reconciliation — never silently accepted. The recovery
drill (Phase B) exits 1 naming findings on any of them.

### T-06 Replay duplication

A keyed retry of a crash-mid-stream submission replays by key before
the sequence or risk gate — never duplicated, never re-gated
(ADR-0012 decision 2). The journal refuses a second record with the
same key on read, so even a hostile file cannot replay a duplicate.

### T-07 Credential exposure

Credentials never exist in the code path: the key store is a
protocol with a safe-filename-enforced file backend (Phase A), and
Phase E's keyring backend is fixture-only — a non-fixture store
refuses outside a drill flag. M8 prompt construction redacts
private keys, bearer tokens and API keys before any model sees text
(`tests/test_ai_redact.py`), and structured logs are JSON records
with a fixed field shape.

### T-08 Model misuse

The M8 layer has no order authority: tool permissions hold at
dispatch, and a hostile tool call aimed at an execution surface is
refused (acceptance drills, `tests/test_ai_acceptance.py`). The kill
switch is not settable from any AI surface by construction — the
gate is in the accounting path, which the AI layer cannot reach.

### T-09 Supply chain

CI runs a dedicated `security` job: `pip-audit` over
`requirements-audit.txt` (the frozen install closure — a new
advisory fails the job loudly) plus the deterministic license review.
The review already refused and removed the one non-OSI dependency it
found (vectorbt, Apache-2.0 WITH Commons Clause — ADR-0012
decision 4). The inventory and policy live in `docs/licenses.md`.

### T-10 Hostile files

Every store refuses hostile paths: the lake rejects symlinks on the
raw read/write surface, `MetricsStore` and the watchlist store refuse
a file root and non-directory paths, and the key store enforces safe
filenames. A hostile *content* payload is T-05's fail-closed read.

### T-11 The real-money gate

The standing gate is the model's boundary, not an enforcement
feature: nothing in M10 can place a live order, sign a wallet or
spend money. Phase E's enablement state machine refuses any
transition to `enabled` without a recorded human approval record,
and the gate text is recorded in ADR-0012, iteration 0012 and
ACTIVE.md — this threat is closed by *absence* of capability, which
the enablement drills verify against the paper surface.

### T-12 Availability

The four incident runbooks (disk exhaustion, journal corruption,
reconciliation mismatch, kill switch engaged) name symptoms, checks
and recovery; atomic writes mean a crash never leaves a
half-written record, so the failure mode is "journal refuses and
names the line", not "journal silently loses state".

### T-13 Export integrity

Audit bundles are HMAC-SHA256-signed over canonicalized content;
`quantmesh ops verify-export` refuses tampered values, tampered
digests, wrong keys and missing bundles — the four tamper drills in
`tests/test_ops.py` pin each.

### T-14 CSRF on the write surfaces

A malicious page in the operator's browser can reach the loopback
bind (the browser is trusted, its hostile tabs are not). Every write
POST therefore refuses a present Origin that does not name a
loopback host (browser CSRF always sends the attacker's Origin); an
absent Origin stays allowed — the CLI/drill path, which cannot be
distinguished from a same-origin send. Combined with T-01, a
cross-site send can neither reach the server nor pass its Origin
guard.

### T-15 Hostile form input

The two write surfaces have typed contracts: watchlist add/remove
take a symbol and surface store errors as typed pages; the
kill-switch POST requires the literal confirm field and a valid
`Venue` (per-venue options come from the account's engaged venues
and the bound markets — never a free-text injection surface). An
unknown venue or symbol refuses with state untouched.

## Accepted residuals

1. **Same-origin page bugs** — a vulnerability in the workstation's
   own rendered pages (T-02 defense failing) could drive the two
   write surfaces from the operator's own browser. Mitigated by
   autoescape + typed forms; accepted because the surfaces are
   limited, reversible and journaled.
2. **Physical access to the machine** — a local attacker with the
   operator's account can read or modify any local file, including
   journals and stores. Out of scope for a local-first workstation;
   the fail-closed read discipline means their edits are detected,
   not silently adopted.

## How this document is pinned

`tests/test_security.py` asserts this document exists, carries the
required register columns, and names only threats whose control tests
exist in the suite (each `Pinned by` cell is a real test or file).
`docs/licenses.md` is pinned the same way against
`tools/license_review.py`'s classification of the installed
environment.
