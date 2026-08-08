# Iteration 0010 — M8: Local AI research layer

- Status: active
- Started: 2026-08-08
- Completed:
- Owner: Claude
- GitHub issue: issues #45-#49 (Phases A-E, dependency-ordered: #46/#47/#48/#49 block on #45, #48/#49 block on #46, #48/#49 block on #47, #49 blocks on #48)
- Pull request: (opened after acceptance criteria complete; base = `feat/m7-unified-research-and-portfolio-engine`, stacked — merges after the M7 PR #44, which stacks behind the M6 PR #38, which awaits the M5 PR, which awaits the M5 operator drill)
- Roadmap milestone: M8 (`LATER` → `ACTIVE`)

## Outcome

Use AI to accelerate research while preserving deterministic execution
authority: a local-first model gateway, structured analyst/critic/risk/
portfolio research roles, retrieval over local documents, experiment
records and audit logs, enforced tool permissions and prompt-data
redaction, and content-addressed decision logs with citations and model
metadata. AI output is a *claim with evidence*, never an instruction
with authority — the M2 paper kernel remains the only execution surface,
and no role, tool, or schema in this milestone can reach it.

## Scope and boundaries

In scope:

- A fixture-first `quantmesh.ai.gateway` boundary: OpenAI-compatible
  chat completions with JSON-schema structured output, injected
  transports (`HttpModelTransport` + `ScriptedModelTransport`),
  loopback-only default, pydantic validation at the boundary.
- Structured research roles (analyst, critic, risk, portfolio) with
  pydantic output schemas and a deterministic pipeline with a critic
  gate; role outputs carry claims, citations and reviews — never
  orders.
- Retrieval over local documents (filings/news/notes), experiment
  registry records and audit logs, with resolvable citations.
- A tool registry with per-role permission sets enforced at call time;
  prompt-data redaction before anything leaves the boundary, with a
  redaction report; an append-only decision log on the ADR-0006
  discipline.
- Acceptance drills proving the roadmap exit criteria on scripted
  fixtures.

Out of scope (recorded, not deferred silently):

- **AI order authority**: no execution tool exists in the tool
  registry, no role schema can carry an order, and the M2 kernel and
  M5 execution adapters are unreachable from this package (structural,
  proven by test). Promotion/kill-switch *enforcement* remains M10;
  this milestone never changes what promotes.
- **Paid or remote model infrastructure**: the gateway refuses
  non-loopback endpoints unless explicitly constructed with
  `allow_remote=True` (an explicit construction-time decision, never
  env-driven), and `model_gateway_url` defaults to a local endpoint.
  No new dependency and no paid API is required for any test or
  acceptance drill — everything runs against `ScriptedModelTransport`.
- **Embeddings/vector search as a required path**: retrieval is
  lexical-first (deterministic token-overlap/IDF ranking, pure
  python). Local-embedding reranking is a documented lazy extension
  behind the same `RetrievalSource` protocol, not a dependency.
- **M10 scope**: secret store integration, live enablement, incident
  runbooks — all remain M10.
- **OpenBB/AGPL code embedding**: OpenBB is reference-only (AGPLv3;
  patterns at a process boundary, never copied into this tree).
  TradingAgents is Apache-2.0 and likewise pattern-only.

## Acceptance criteria

1. [x] A local/OpenAI-compatible model gateway serves structured
      outputs through schema validation: malformed or schema-violating
      model responses are refused with a typed error and no partial
      object escapes; the gateway defaults to loopback and refuses
      remote endpoints unless explicitly constructed; a scripted
      transport makes the whole surface deterministic and testable. —
      Phase A (issue #45).
2. [x] Analyst, critic, risk and portfolio roles produce
      schema-validated research outputs through a deterministic
      pipeline (analyst → critic gate → risk → portfolio); a critic
      flag blocks a claim downstream; no role output can carry
      order-shaped data (proven by test). — Phase B (issue #46).
3. [x] Retrieval over documents, experiment records and audit logs
      returns passages with resolvable citations; a citation that
      cannot be resolved to a source fails closed. — Phase C (issue
      #47).
4. [x] Tool calls are enforced per role against a registry that
      contains no execution surface; prompt data is redacted before it
      leaves the boundary with a redaction report; every research
      decision is recorded with model metadata and citations on the
      ADR-0006 ledger discipline. — Phase D (issue #48).
5. [ ] Acceptance drills prove the M8 exit criteria on fixture
      universes: hostile model output is schema-rejected and cannot
      bypass the risk APIs (exit criterion 1); research claims link to
      source data and reproducible experiments, and an unresolvable
      citation refuses the claim (exit criterion 2). — Phase E (issue
      #49).

## Plan and role assignments

- Planner: Claude
- Quant researcher: Claude
- Implementer: Claude
- Reviewer: Claude (adversarial self-review before every commit)
- Verifier: Claude (fixture drills, full suite, ruff, diff, submodules)

## Reuse survey (2026-08-08)

Vendored trees read at the file level; both remain reference-only
(patterns, never code — OpenBB is AGPLv3, TradingAgents Apache-2.0).

- **TradingAgents** (`vendor/reference/tradingagents`): the graph-based
  orchestration (langgraph nodes, checkpointer, reflection) is
  reference-only — QuantMesh's pipeline is deliberately linear and
  deterministic. What ports directly: (a) role factories returning
  node closures and per-role tool binding — TradingAgents gates tools
  by giving each role only its own `ToolNode`; M8's `ToolSpec`
  `allowed_roles` matrix is the finer-grained form of the same
  discipline, enforced at call time; (b) pydantic v2 output schemas
  whose field descriptions double as extraction instructions
  (`agents/schemas.py`) — M8 role schemas follow this, with one
  deliberate difference: TradingAgents' `invoke_structured_or_freetext`
  falls back to freetext, M8 refuses freetext (structured-only,
  fail-closed — an ADR decision); (c) the provider-agnostic
  OpenAI-compatible client factory and the canonical provider→env-var
  map (`llm_clients/factory.py`, `api_key_env.py`) — M8's gateway
  boundary mirrors the factory/client shape, minus the multi-provider
  surface (one OpenAI-compatible wire, loopback default).
- **OpenBB** (`vendor/reference/openbb`): the vendored copy contains
  NO LLM code — the OpenBB LLM/agents product lives in a separate
  repo; the roadmap's "AI/data boundaries" maps to the `mcp_server`
  extension (FastAPI MCP server exposing the command surface as
  tools — `ToolInfo`/`CategoryInfo`, `prompts.py`) and
  `core/openbb_core/app/command_runner.py`. Patterns only: MCP-style
  tool exposure for a future M9/10 surface, and the `CredentialsLoader`
  design (provider credentials as pydantic `SecretStr`, env-gathered) —
  M8 keeps the M5 discipline (env-injected, never serialized) and
  adopts `SecretStr` for the gateway key field. No RAG exists in
  either tree — M8's lexical-first retrieval is original, and
  embedding reranking stays a documented lazy extension.

### Phase A — model gateway (issue #45)

`quantmesh.ai.gateway`:

- `ChatMessage` (role system/user/assistant, content), `ModelRequest`
  (messages, temperature, max_tokens, response_format), `ModelResponse`
  (content, model metadata — name/version reported by the endpoint or
  pinned in settings, finish_reason, usage) — all pydantic, all
  fail-closed on construction (bounds on temperature/max_tokens).
- `ModelGateway` boundary: `complete(request)` and
  `complete_structured(request, schema)` — the structured path appends
  the JSON-schema `response_format` (or JSON-mode) request, parses the
  response text, validates with pydantic, and on any failure raises a
  typed `ModelOutputError` naming the failure (unparseable JSON,
  schema-violation fields, wrong shape) — **no partial object ever
  escapes**.
- Transports (injected, the M4/M5/M6 fixture-first pattern):
  `ScriptedModelTransport` (JSONL canned responses with per-line
  attribution, fail-closed on malformed lines, deterministic —
  everything except the optional live drill runs on this) and
  `HttpModelTransport` (httpx — already a core dependency from M6 —
  against `settings.model_gateway_url`, OpenAI-compatible
  `/chat/completions`, typed unavailable on HTTP/transport errors).
- Local-first posture: `model_gateway_url` defaults to
  `http://127.0.0.1:11434` (Ollama's local port; the reference local
  gateway, documented as a default not a hard requirement); a
  non-loopback host is refused at construction unless
  `allow_remote=True` is passed explicitly (construction-time decision,
  never env-driven — the Kalshi migration-host precedent).
  `QUANTMESH_MODEL_API_KEY` (if set) is injected per request and never
  serialized into logs, exceptions, or the request record (the M5
  signer redaction discipline).
- Settings: `model_gateway_url`, `model_name` (empty → structured
  refusals name the missing model), `model_request_timeout_s`,
  `model_max_tokens`.
- Tests: transport boundary, scripted-line attribution, structured
  parse/validation refusal paths (schema-violating JSON, truncated
  JSON, non-JSON), loopback/remote construction rules, key redaction
  (the M5 wallet-isolation test discipline: scan captured logs/exc
  strings for the key), settings defaults. No new dependency: httpx +
  pydantic are already core.

### Phase B — structured research roles (issue #46)

`quantmesh.ai.roles`:

- Role charters as data: `RoleCharter{role, system_prompt, tools,
  output_schema_id}` for `analyst` (research claims from sources, with
  citations), `critic` (adversarial review of the analyst's claims —
  refuses claims lacking support), `risk` (review risk surfaces; must
  reference the M5 risk-gate verdicts supplied in context), `portfolio`
  (portfolio suggestions; must reference the M7 constraint/optimizer
  outputs supplied in context). Charters are pinned constants with
  digests folded into the pipeline identity.
- Output schemas (pydantic): `AnalystReport` (claims: `Claim{
  statement, confidence, direction, evidence_citations[]}` — a claim
  without at least one citation is refused at validation), `CriticVerdict`
  (verdict pass|flag, flagged_claims with reasons),
  `RiskReview` (findings, posture relative to the supplied gate
  verdicts), `PortfolioReview` (suggestions referencing constraint
  outputs). **No order-shaped field exists in any schema** — proven by
  a shape test that walks the schemas for order fields
  (quantity/venue/order id/price) and by a hostile-script drill where
  an order-shaped JSON fails validation.
- `ResearchPipeline`: deterministic stage order (analyst → critic gate
  → risk → portfolio); each stage receives only (a) the redacted input
  context, (b) prior stages' validated outputs; a `flag` verdict blocks
  the flagged claims from the critic's report reaching later stages
  (the gate is in deterministic code, not in the model's cooperation).
- Identity: `run_id` setup-only over role set + charter digests + input
  digests (never model outputs — the M7 discipline); recorded in the
  decision log.
- Tests: charter/schema registries, claim-without-citation refusal,
  critic gate behavior on scripted verdicts, pipeline determinism on a
  scripted transport (same inputs → same run id, same stage order,
  identical decision records), the no-order-shape test, unknown-role
  refusal.

### Phase C — retrieval over filings, news, experiments, audit logs (issue #47)

`quantmesh.ai.retrieval`:

- `Document{id, kind: filing|news|note, source_path, ingested_at,
  content}` and `DocumentIndex` — a JSONL manifest under
  `settings.documents_dir` on the ADR-0006 discipline (atomic
  temp+replace appends, fail-closed reads with line attribution,
  duplicate id refusal); `ingest_file` from local text files
  (filings/news/notes), fail-closed on unreadable/non-UTF8/empty files
  and non-text kinds.
- `RetrievalSource` protocol: `search(query, top_k) ->
  list[RetrievedPassage]` with three registered sources — the document
  index, the experiment registry (`ExperimentRegistry` records, M3),
  and the audit log surface (M2 event store / registry JSONLs). Each
  passage carries `Citation{source_kind, source_id, span}` — a
  resolvable identity, never a blob.
- Ranker: deterministic lexical (casefold tokenization, IDF-weighted
  overlap — pure python, no new dependency); embedding rerank is a
  documented lazy extension registered through the same protocol, never
  required (ADR decision).
- `resolve_citation(citation) -> source record` fails closed when the
  source kind is unknown, the id is missing, or the span is out of
  range — the Phase E drill depends on this.
- Fail-closed surface: empty index, unknown kind, duplicate ids,
  missing files on resolve, zero-length queries, top_k bounds.
- Tests: tokenizer/ranker pinned arithmetic, per-source search over
  fixture registries/logs, citation resolution + every refusal path,
  manifest discipline (duplicate/corrupted line/root-not-dir).

### Phase D — tool permissions, prompt-data redaction, decision logs (issue #48)

`quantmesh.ai.tools` / `quantmesh.ai.redact` / `quantmesh.ai.decisions`:

- `ToolPolicy{name, description, allowed_roles}` pinned data plus a
  `ToolRegistry` over injected surface callables (fail-closed
  construction: missing/unknown surfaces, unknown tool policies,
  policies naming unknown roles), with read-only research tools only:
  `retrieve_documents`, `read_experiment`, `read_report`,
  `read_risk_context`, `read_portfolio_snapshot`. Enforcement at call
  time: a tool call is dispatched only when the calling role is in
  `allowed_roles`, with a typed `ToolRefusalError` naming the role and
  the tool; unknown tools are typed `UnknownToolError`s. **The registry
  contains no execution surface** — no order, no kernel entry, no
  adapter call exists as a tool; a hostile model that "calls" one gets
  the unknown-tool refusal. A structural test proves the tool dispatch
  module cannot import the execution adapters, and a consistency test
  pins `TOOL_POLICIES.allowed_roles` to the Phase B charter `tools`
  tuples.
- `redact_context(context, *, secrets=None) -> (redacted,
  RedactionReport)`: scrubs secret material BEFORE anything is sent to
  the gateway — known values (the `QUANTMESH_*KEY/SECRET/TOKEN`
  environment values or an explicit `secrets=` mapping, longest-first)
  and shape scans (0x-prefixed/bare 64-hex key runs, `Bearer`/`sk-`
  tokens, long opaque non-hex runs; pure 40-hex commits and 16-hex ids
  survive — over-redaction is the safe direction); the report counts
  and classifies redactions. Tests follow the M5 wallet-isolation
  discipline: the raw secret never appears in the redacted payload, and
  a secret smuggled inside *retrieved document text* is also scrubbed
  (prompt-injection containment).
- `DecisionLog` JSONL under `settings.decisions_dir` on ADR-0006:
  every pipeline stage records `DecisionRecord{run_id, role, model{
  name, version, endpoint_kind}, prompt_digest (sha256 of the redacted
  prompt), schema_id, verdict, citations[], output_digest, refusal?,
  recorded_at}`. Identity is **content-addressed**: `decision_id =
  sha256` over the record minus `recorded_at` (the FundingLedger
  precedent) — an identical replay is refused as a duplicate, any
  difference is a new audit entry. Reads fail closed with line
  attribution.
- Tests: permission matrix (every role × every tool), unknown-tool
  refusal, no-execution-import structural test, redaction arithmetic
  and the injection-containment test, decision identity
  (output change → new id, identical replay → duplicate refused),
  ledger discipline.

### Phase E — acceptance drills (issue #49)

Drills on fixture universes (scripted transports throughout):

- **Exit criterion 1 (schema-validated, cannot bypass risk APIs)**:
  a hostile scripted model answers the analyst stage with
  schema-violating JSON (refused, typed, no partial object), with an
  order-shaped payload (refused at validation — no order field exists),
  and with a tool call to a non-existent execution surface (refused as
  unknown tool, permission enforcement tested role × tool); the
  structural tests prove the ai package never imports the execution
  adapters and the risk surface is reachable only through the
  deterministic M5 gate.
- **Exit criterion 2 (claims link to sources and reproducible
  experiments)**: an end-to-end pipeline over a fixture experiment
  registry record + a fixture document + an audit-log slice — the
  analyst's claims carry citations; `resolve_citation` resolves every
  one (experiment id → `ExperimentRegistry.get`, document → span);
  a second drill injects a fabricated citation and the critic flags
  it, the decision log records the refusal, and the claim never
  reaches later stages.
- Cross-root acceptance: two independent `decisions_dir` roots replay
  the same drill → byte-identical decision JSONL (determinism
  evidence).

## Delivery protocol

Solo fast lane: one branch `feat/m8-local-ai-research-layer`, one
tested/reviewed/issue-linked commit per issue, push each checkpoint,
one final M8 PR after acceptance criteria complete, squash-merge under
the standing merge authority when CI is green, close #45-#49,
checkpoint ACTIVE.md/0010/ROADMAP.md. There is no human gate in M8:
every surface is fixture-driven local computation (the optional
live-local-model operator drill is recorded below, not a blocker).
The stacking constraint: the M8 PR merges after the M7 PR #44 (which
stacks behind the M6 PR #38, which stacks on the M5 PR, which awaits
the M5 operator drill).

## Durable decisions to record when reached

- ADR-0010 **recorded** (Phase A, issue #45, decision 1): the model
  gateway is a boundary with injected transports; the wire is
  OpenAI-compatible chat completions; loopback-only by default with
  an explicit construction-time `allow_remote=True` override (never
  env-driven); the API key is env-injected per request and never
  serialized; structured output is pydantic-validated at the boundary
  with no partial object escape. Decision 1 + consequences written
  into ADR-0010 on 2026-08-08.
- ADR-0010 **recorded** (Phase B, issue #46, decision 2): role
  outputs are pydantic schemas with `extra="forbid"` (order-shaped
  fields refused, never silently dropped — pydantic's default
  `extra="ignore"` is fail-open, caught by adversarial review); the
  pipeline order is fixed in code with the critic gate blocking in
  deterministic code (pass-with-flags/flag-without-flags/out-of-range
  indices are typed errors); risk/portfolio references are structural
  subsets of the supplied verdict/output ids (required at
  construction); `run_id` is setup-only over role set + charter
  digests + context digests, never model outputs; the roles module
  imports no execution surface. Decision 2 written into ADR-0010 on
  2026-08-08.
- ADR-0010 **recorded** (Phase C, issue #47, decision 3): retrieval is
  lexical-first (deterministic casefold/IDF ranker, pure python —
  embedding reranking is a documented lazy extension behind the
  `RetrievalSource` protocol, never a required path); one protocol,
  three sources (document index, experiment registry, order journal as
  the read-only audit surface); citations are resolvable identities
  that fail closed (`CitationResolutionError` on unknown kind, missing
  record, or out-of-range span); documents are ingested on the
  ADR-0006 manifest discipline under `settings.documents_dir`. Decision
  3 written into ADR-0010 on 2026-08-08.
- ADR-0010 **recorded** (Phase D, issue #48, decision 4): the tool
  registry is pinned policy data plus runtime enforcement over injected
  read-only surfaces — no execution surface (structural, proven by
  test), typed refusals naming role and tool, policy table pinned to
  the charter tools tuples; prompt data is redacted before the wire
  (known values + shape scans, over-redaction the safe direction,
  injection containment over retrieved text) with a deterministic
  report; decision records are content-addressed audit entries
  (16-hex sha256 over all content except recorded_at — identical
  replay refused as a duplicate, any difference a new entry) with
  `for_stage` digest building and a consistency validator, on the
  ADR-0006 discipline under `settings.decisions_dir`. Decision 4
  written into ADR-0010 on 2026-08-08.
- ADR-0010 extension **to record** (Phase E): acceptance evidence is
  scripted-fixture-based; a live local model (e.g. Ollama) is an
  optional operator drill with exact steps, never a merge gate.

## Work log

- 2026-08-08: M8 planned and opened — iteration 0010 recorded; issues
  #45-#49 created with the M8 label; branch
  `feat/m8-local-ai-research-layer` branched from the M7 tip `bcef32b`
  (stacked delivery: M8 PR base = the M7 branch, merging after the M7
  PR #44, which stacks behind the M6 PR #38, which awaits the M5 PR/
  operator drill). Reuse survey done at the file level: TradingAgents
  (Apache-2.0) ports three patterns — role factories with per-role
  tool binding (its per-role `ToolNode` gating is M8's `allowed_roles`
  matrix in coarser form), pydantic output schemas with field
  descriptions as extraction instructions, and the OpenAI-compatible
  client factory/provider-env map (M8 runs one wire, loopback by
  default); its `invoke_structured_or_freetext` freetext fallback is
  deliberately NOT replicated (structured-only, fail-closed). OpenBB
  (AGPLv3, reference-only) has NO LLM code in the vendored copy — the
  roadmap's "AI/data boundaries" maps to the `mcp_server` extension
  (command surface as MCP tools) and `CredentialsLoader`/`SecretStr`
  (env-gathered provider credentials); neither tree has any RAG, so
  the lexical-first retrieval is original. No new core dependency:
  httpx and pydantic already cover the gateway. No external gates:
  M8 is fixture-driven local computation end to end (a live
  local-model operator drill is recorded as optional, not a blocker);
  the stacked PR chain is the only dependency.
- 2026-08-08 (issue #45, Phase A): implemented `ai/` — `errors.py`
  (five typed errors), `wire.py` (`ChatMessage`/`ModelRequest`/
  `ModelResponse`, `build_chat_body` with the JSON-schema
  `response_format`, fail-closed `parse_completion`), `transport.py`
  (`ModelTransport` boundary, `ScriptedModelTransport` with JSONL
  line attribution + `payload` escape hatch + `seen_bodies`,
  `HttpModelTransport` loopback-by-default with explicit
  `allow_remote=True`, env-injected `QUANTMESH_MODEL_API_KEY` in the
  Authorization header, key-less reprs), `gateway.py` (`ModelGateway`
  with `complete`/`complete_structured` — parse + pydantic validation
  at the boundary, typed `ModelOutputError` naming the violation, no
  partial object escape, structured-only). Settings gained
  `model_gateway_url` (loopback default)/`model_name`/
  `model_request_timeout_s`; `model_max_tokens` deliberately dropped
  from settings (the request wire model owns max_tokens). ADR-0010
  decision 1 recorded. The first test run surfaced three test-side
  defects (pydantic `ge/le` → JSON-schema minimum/maximum, not
  exclusive; unbracketed IPv6 host in the fixture URL; fake httpx
  responses needed a `Response` wrapper) and adversarial review
  caught two real defects before commit (non-str `model_name`
  accepted silently; the redaction scan attempted a real connection
  to 127.0.0.1:1 — now faked). 66 gateway tests green; ruff clean
  across src and tests; full suite 1365 passed / 3 skipped; committed
  `a134d23` and pushed (first push on the M8 branch).
- 2026-08-08 (issue #46, Phase B): implemented `ai/roles.py` — role
  charters as pinned data (`RoleCharter` with setup-only digests,
  `tools` tuples pre-binding the Phase D registry names),
  `analyst`/`critic`/`risk`/`portfolio` charters with pinned system
  prompts, output schemas (`Claim` — ≥1 non-empty citation required at
  validation, confidence [0,1], direction literal; `AnalystReport`;
  `CriticVerdict`/`FlaggedClaim`; `RiskReview`/`RiskFinding` with
  severity literal; `PortfolioReview` — suggestions only, no
  quantity/price fields), `ResearchPipeline` (fixed analyst → critic
  gate → risk → portfolio stage order; `_apply_critic_gate` in code —
  pass-with-flags/flag-without-flags/out-of-range indices are typed
  `PipelineError`s; the blocked claim never reaches later stages,
  proven via `seen_bodies`), structural reference checks
  (`referenced_verdicts` ⊆ supplied M5 risk-gate verdict ids,
  `referenced_inputs` ⊆ supplied M7 constraint/optimizer output ids —
  both supplies required at construction), `run_id` = 16-hex
  setup-only over role set + charter digests + context digests (never
  model outputs — proven by two scripts with the same inputs sharing
  an id while differing in output). `errors.py` gained
  `UnknownRoleError`/`PipelineError`; `ai/__init__.py` exports the
  full roles surface. The first test run caught a real fail-open
  defect: pydantic's default `extra="ignore"` silently dropped
  order-shaped fields (an order-shaped JSON validated as an empty
  report) — every role schema now sets `extra="forbid"`, and the
  hostile drills (order-shaped top level, order-shaped claim inside a
  report, order-shaped pipeline output) all fail closed with
  `ModelOutputError` naming the field. 40 roles tests green (5
  charters + 10 schemas + 4 no-order-shape incl. the
  no-execution-import source scan + 5 gate + 16 pipeline); ruff clean
  across src and tests.
- 2026-08-08 (issue #47, Phase C): implemented `ai/retrieval.py` —
  `Document` (kind literal filing|news|note, tz-aware ingested_at,
  `extra="forbid"`) and `DocumentIndex` (JSONL manifest under the new
  `settings.documents_dir` on the ADR-0006 discipline: atomic
  temp+replace appends, fail-closed reads with line attribution,
  duplicate ids refused at read and before ingestion reads the file,
  root-not-dir refusal, ingestion fail-closed on unreadable/non-UTF8/
  empty files and unknown kinds); the deterministic lexical ranker
  (`tokenize` casefold `\w+` tokens, smoothed-IDF weights, sum over
  query-token overlap with query dedup and zero-overlap exclusion,
  ties by index — byte-deterministic, pure python, no new dependency);
  `Citation{source_kind literal, source_id, span}`/`RetrievedPassage`/
  `ResolvedSource` and the `RetrievalSource` protocol with three
  registered sources — `DocumentSource`, `ExperimentSource`
  (M3 registry records as canonical `model_dump_json()` text, hand-
  written fixture JSONL in tests since `record()` runs the lake pin
  gate), `AuditSource` (M2 `OrderJournal` as a read-only data surface);
  `resolve_citation` fail-closed (`CitationResolutionError` on unknown
  kind — defense in depth past the literal — missing record, or
  out-of-range span). `errors.py` gained `RetrievalError`/
  `CitationResolutionError`; `ai/__init__.py` exports the full
  retrieval surface. Test-side catch: `\w+` treats `btc_returns` as one
  token (underscore joins), so the experiment search fixture pins the
  underscored dataset name as the query. 52 retrieval tests green
  (tokenizer/IDF/ranker pinned arithmetic incl. the 2.9808 vs 1.2877
  doc0/doc1 pin, citation/passage/document model refusals, manifest
  discipline with line attribution, per-source search/resolve over
  fixture documents/experiments/orders, every citation-refusal path);
  ruff clean across src and tests.
- 2026-08-08 (issue #48, Phase D): implemented `ai/tools.py` —
  `ToolPolicy{name, description, allowed_roles}` pinned data
  (`TOOL_POLICIES`, five read-only research tools whose `allowed_roles`
  match the Phase B charter `tools` tuples exactly — pinned by a
  consistency test so the two tables cannot diverge),
  `bind_default_surfaces` (five injected reader callables — documents/
  experiments via `RetrievalSource`, reports/risk/portfolio via
  injected callables; every surface a reader, none can place or modify
  an order), `ToolRegistry` (fail-closed construction: missing/unknown
  surfaces, unknown tool policies → `UnknownToolError`, policies naming
  unknown roles → `UnknownRoleError`; `allowed()` fail-closed on
  unknown tools; `dispatch()` → typed `ToolRefusalError` naming role
  and tool, surfaces never touched on refusal). `ai/redact.py` —
  `redact_context` with known-value replacement (`QUANTMESH_*KEY/
  SECRET/TOKEN` env values or explicit `secrets=` mapping, longest-first
  so nested secrets leave no partial artifacts) then shape scans
  (0x-prefixed and bare 64-hex key runs, `Bearer`/`sk-` tokens, long
  opaque non-hex runs) — over-redaction the safe direction: pure 40-hex
  commits and 16-hex ids survive — plus a deterministic
  `RedactionReport`; non-string context/secret entries are typed
  `RedactionError`s; retrieved document text is scrubbed too
  (prompt-injection containment). `ai/decisions.py` —
  `DecisionRecord` content-addressed (16-hex sha256 over all content
  fields except `recorded_at` — identical replay refused as a
  duplicate, any difference a new audit entry), `for_stage` computes
  prompt/output digests from exactly the redacted prompt and validated
  output (verdict = output's `verdict`, else its `posture`, else
  canonical JSON), a consistency validator recomputes the id so a
  tampered id/digest is refused; `DecisionLog` on the ADR-0006
  discipline under the new `settings.decisions_dir`. `errors.py` gained
  `ToolError`/`UnknownToolError`/`ToolRefusalError`/`RedactionError`;
  `ai/__init__.py` exports the full Phase D surface. First test run
  caught three test-side defects (the `_record` helper collided with
  `for_stage`'s explicit kwargs, my redaction count arithmetic, and
  RiskReview/PortfolioReview carrying their verdict as `posture` —
  `for_stage` now extracts it) plus one dead-code residue (an unused
  `sources` map in `bind_default_surfaces`). 69 Phase D tests green
  (25 tools + 14 redact + 30 decisions); ruff clean across src and
  tests; full suite 1526 passed / 3 skipped (see Last verification in
  ACTIVE.md).

## Verification evidence

- Phase A slice (issue #45): `tests/test_ai_gateway.py` — 66 passed
  in 0.38s. Wire contract: role literal + empty-content refusals,
  request bounds (min 1 message, temperature [0, 2], max_tokens >
  0), canonical body shape with temperature/max_tokens passthrough,
  JSON-schema `response_format` (name/strict/min-max bounds) present
  only on the structured path; `parse_completion` fail-closed on
  every pinned shape violation (non-mapping payload, no/empty
  choices, non-mapping choice/message, non-str content/finish_reason/
  wire-model, non-int usage) with the wire-model-name fallback.
  Scripted transport: record replay in order, `seen_bodies` capture,
  JSONL round-trip with blank-line tolerance, line attribution on
  non-JSON/non-mapping lines, record-index attribution on missing/
  non-str content and payload-mixing, `payload` escape hatch,
  exhaustion refusal with count. HTTP transport (faked httpx — no
  network anywhere): loopback hosts accepted (127.0.0.1/localhost/
  ::1), remote refused naming the host + the explicit override,
  `allow_remote=True` acceptance, scheme/host refusals, settings-url
  default, key from env with explicit-key precedence, repr and
  construction-error key scans, Authorization header placement with
  the key absent from the body, HTTP refusal with server text,
  non-JSON body, wrapped transport errors, timeout plumbed. Gateway:
  complete/structured happy paths, canonical body via `seen_bodies`,
  settings-model-name resolution, missing-model refusal at call,
  non-str model refusal at construction, structured JSON/schema/
  empty refusal paths naming the violating fields, no partial object
  escape. Redaction scan (M5 wallet-isolation discipline): the key is
  absent from every failure surface (transport/gateway reprs and all
  raised exception strings) including a hostile wire shape exercised
  through the gateway. Adversarial review before commit fixed the
  non-str model-name hole and removed a real network attempt from
  the redaction scan (faked httpx raises the connect error instead).
  ADR-0010 decision 1 recorded. Full suite 1365 passed / 3 skipped
  after the issue #45 commit `a134d23` (2026-08-08); pushed.
- Phase B slice (issue #46): `tests/test_ai_roles.py` — 40 passed in
  0.24s. Charters: canonical role set/order, fully pinned charters,
  accessor, unknown-role refusals, digest determinism + sensitivity.
  Schemas at the gateway boundary: claim-without-citation,
  empty-citation, confidence out of [0,1], bad direction, bad critic
  verdict literal, empty flag reason, empty referenced_verdicts, bad
  severity, empty suggestion, bad posture — all typed
  `ModelOutputError` naming the field. No-order-shape: schema walk
  over every reachable model asserting no quantity/qty/size/venue/
  order_id/price/limit_price/side field, hostile order-shaped JSON at
  the top level and inside a claim refused without partial escape,
  and the roles module source contains no import of
  `quantmesh.paper`/`execution`/`hyperliquid.exchange`/`moomoo`.
  Critic gate: pass allows all, flag blocks the claim downstream
  (proven by the captured risk/portfolio request bodies), out-of-range
  index / flag-without-flags / pass-with-flags typed `PipelineError`s,
  empty analyst report flows through cleanly. Pipeline: full-run
  success, fixed stage order (system prompts + context markers in the
  four captured bodies), run_id stable + records byte-identical across
  runs, sensitive to context and to charter digests, independent of
  model outputs (two scripts, same id, different claims), construction
  fail-closed paths (empty context, non-str context value, empty
  verdict supply, empty output supply, missing charter, unknown role),
  unsupplied reference refusals, hostile analyst output refused with
  no result escaping. Adversarial review caught the fail-open
  `extra="ignore"` (order-shaped JSON validated as an empty report) —
  all role schemas now `extra="forbid"`. ADR-0010 decision 2 recorded;
  acceptance criterion 2 checked off.
- Phase C slice (issue #47): `tests/test_ai_retrieval.py` — 52 passed
  in ~1.4s. Tokenizer/ranker pinned arithmetic: `idf_weights` on
  `["aaa bbb ccc", "bbb ddd", "eee"]` gives aaa ≈ 1.6931 > bbb ≈ 1.2877
  > 1.0, and `rank_texts("aaa bbb", ..., top_k=2) == [0, 1]` (doc0 =
  aaa+bbb ≈ 2.9808, doc1 = bbb ≈ 1.2877, doc2 excluded as
  zero-overlap); ties break by index, repeated query tokens count once,
  tokenless queries and top_k < 1 are typed `RetrievalError`s. Models:
  `Citation` span shape (negative/reversed refused), source-kind
  literal, `extra="forbid"` on Citation/RetrievedPassage/Document
  (hostile extra fields refused), Document kind literal and naive-
  timestamp refusal. Manifest discipline: ingest round-trips through a
  fresh `DocumentIndex`, append order preserved, duplicate id refused
  *before* the file is read, unknown kind/empty id refused, unreadable/
  empty/non-UTF8 files refused with "cannot ingest", `get`/missing-
  record ValueErrors, missing-root → [], corrupted line attributed
  ("line 1 is invalid"), duplicate ids across lines attributed
  ("share a document id"), root-not-a-directory refusal. Sources:
  document search ranks by content over a fixture index, experiment
  search over hand-written registry JSONL (record() bypassed — it runs
  the lake pin gate; reading never does), audit search over a real
  `OrderJournal` fixture, each source's resolve returns the record plus
  the canonical span-indexable text, missing ids refused per source.
  Citation resolution: document/experiment/audit all resolve, span
  bounds checked against the canonical text, unknown kind refused
  (via `model_construct` — the literal is the first line of defense,
  the resolver the second), missing record refused, out-of-range span
  refused — every refusal path a typed `CitationResolutionError`.
  Full suite green after the issue #47 commit (see Last verification
  in ACTIVE.md).
- Phase D slice (issue #48): `tests/test_ai_tools.py` +
  `test_ai_redact.py` + `test_ai_decisions.py` — 69 passed in ~1.5s
  (161 AI tests total across gateway 66 + roles 40 + retrieval 52 +
  Phase D 69, minus the three pre-existing skips none of these are).
  Tools: canonical five-tool tuple, policy shape (description + roles,
  roles ⊆ ROLE_ORDER), **charter consistency** — for every role,
  `charter(role).tools` == the policy `allowed_roles` computed from
  `TOOL_POLICIES` (the two tables cannot diverge), no order/trade/
  cancel/position-shaped tool names. Construction fail-closed:
  missing surfaces ("missing tool surfaces"), unknown surface, unknown
  tool policy → `UnknownToolError`, policy naming unknown role →
  `UnknownRoleError`. Dispatch: allowed calls reach the surface with
  args intact; the permission matrix is asserted per role (analyst:
  retrieve/read_experiment/read_report, critic: retrieve only,
  risk: read_risk_context only, portfolio: read_portfolio_snapshot
  only); forbidden calls raise `ToolRefusalError` naming role *and*
  tool and never touch the surface (calls list stays empty); unknown
  tool and unknown role refusals. Default surfaces over a real
  `DocumentIndex` fixture: `[document:d-1] BTC rally momentum` render,
  "no passages matched" on zero overlap, read_tools delegate to the
  injected callables in order, non-str args typed ValueError. Structural:
  `inspect.getsource(tools_module)` contains none of
  `quantmesh.paper`/`execution`/`hyperliquid.exchange`/`moomoo`.
  Redaction: clean text untouched (report total 0), 0x-prefixed and
  bare 64-hex scrubbed as private_key, **pure 40-hex commit and 16-hex
  id survive** (safe-direction negatives), `Bearer ...` (incl. dots and
  base64 chars) and `sk-...` scrubbed as token, long opaque non-hex
  run scrubbed, occurrences counted per class (two occurrences → 2),
  input never mutated; env secrets: `QUANTMESH_MODEL_API_KEY` value
  scrubbed with env_secret count, unrelated `QUANTMESH_` vars and
  non-matching values ignored, explicit `secrets=` override wins over
  the environment, nested values replaced longest-first with no
  partial artifacts; refusals: non-str context content/name and
  non-str secret entries are typed `RedactionError`s; **injection
  containment** — a key embedded in retrieved document text is
  scrubbed, the raw secret is absent from the joined output, counts
  deterministic (private_key 3, env_secret 1). Decisions: `ModelMeta`
  extra/empty-name/bad-endpoint-kind refusals; `for_stage` digests
  equal sha256 of the redacted prompt and `output.model_dump_json()`
  respectively, critic `verdict="pass"` and risk/portfolio `posture`
  extracted as the verdict (AnalystReport falls back to canonical
  JSON), unknown role refused, refusal and citations recorded;
  content addressing: same content + different `recorded_at` → same
  id, any content difference (prompt/schema/refusal/role/output) →
  new id, ids are 16-hex, identical replay refused as "already
  recorded" with the log length unchanged; validation: tampered
  `decision_id` and tampered `output_digest` both refused ("does not
  match the record's content"), extra fields refused, shape refusals
  (non-hex run_id, unknown role literal, empty verdict/refusal, naive
  recorded_at), recorded_at normalized to UTC; ledger: round-trip,
  cross-instance persistence, `get`/missing refusal, missing root →
  [], corrupt line attributed ("line 1 is invalid"), duplicate ids
  across lines attributed ("share a decision id"), root-not-dir
  refusal, unreadable file refusal, append order preserved, file is
  one JSON record per line. Adversarial review before commit caught
  the RiskReview/PortfolioReview posture-verdict gap (extraction
  extended) and the unused `sources` map. ADR-0010 decision 4
  recorded; acceptance criterion 4 checked off.

## Risks and gates

- **LLM nondeterminism** — nothing downstream depends on exact model
  output: pipeline identity excludes outputs, decision records are
  content-addressed (so identical replays are refused, differences are
  audit entries), and every claim is a claim with citations, never an
  input to execution. The critic gate and all numeric uses validate
  bounds at the schema boundary.
- **Prompt injection from retrieved content** — retrieved text is
  data, not instructions: passages are quoted, tool selection is fixed
  by the registry, the critic reviews claims against sources, and the
  redaction pass scrubs secrets even when they arrive *inside*
  document text (tested). A hostile document cannot summon a tool the
  role does not hold.
- **Data egress** — loopback default, remote override explicit at
  construction, redaction report before the wire, no credentials in
  prompts; the optional live drill runs against a local model only.
- **Model/API key material** — `QUANTMESH_MODEL_API_KEY` is injected
  per request and excluded from logs, exceptions, and decision records
  (the M5 wallet-isolation test discipline).
- **AGPL boundary (OpenBB)** — reference-only; patterns at a process
  boundary; no code embedding in this tree. TradingAgents (Apache-2.0)
  is likewise pattern-only — see the reuse survey.
- **Dependency weight** — no new core dependency: httpx and pydantic
  are already core (M6/M0); retrieval is pure python; embedding
  reranking, if ever added, is a lazy extra behind the protocol.
- **Stacked PR chain** — the M8 PR merges after #44/#38/the M5 PR;
  the chain's only human gate is the M5 operator testnet drill
  (recorded, exact steps in iteration 0007 Phase E). No M8 work
  depends on it.
