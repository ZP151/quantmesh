# ADR-0010 — M8: Local AI research layer

Status: accepted
Date: 2026-08-08
Milestone: M8 — Local AI research layer (iteration 0010)
Issues: #45-#49

## Context

M8 adds an AI research layer: accelerate research with language models
while preserving deterministic execution authority. The roadmap
contract is a local/OpenAI-compatible model gateway, structured
analyst/critic/risk/portfolio research roles, retrieval over local
filings/news/experiments/audit logs, tool permissions and prompt-data
redaction, and decision logs with citations and model metadata. The
long-running goal binds this milestone: no AI order authority without
explicit human approval (enforcement is M10), no paid infrastructure,
local-first data and credentials.

The reuse survey (iteration 0010) found: TradingAgents (Apache-2.0)
ports role-factory/per-role-tool-binding, pydantic extraction schemas,
and an OpenAI-compatible client factory — but its freetext fallback is
deliberately not replicated; the vendored OpenBB copy (AGPLv3,
reference-only) contains no LLM code — its `mcp_server` extension
(command surface as MCP tools) and `CredentialsLoader`/`SecretStr`
(env-gathered provider credentials) are the only patterns; neither
tree contains any RAG, so lexical-first retrieval is original.

## Decision 1 — The model gateway is a boundary with injected
transports, loopback by default, structured-only (Phase A, issue #45)

`quantmesh.ai.gateway`/`transport`/`wire`/`errors`:

- The wire is OpenAI-compatible chat completions
  (`/v1/chat/completions`), owned as a contract: pydantic
  `ChatMessage`/`ModelRequest`/`ModelResponse`, a canonical
  `build_chat_body` (with the JSON-schema `response_format` on the
  structured path), and a fail-closed `parse_completion` decoder —
  a wire payload violating the pinned shape is a typed
  `ModelProtocolError`, and no partial response ever escapes.
- Transports are injected: `ScriptedModelTransport` (JSONL records
  with line attribution and a `payload` escape hatch for hostile wire
  shapes) makes every test and acceptance drill deterministic;
  `HttpModelTransport` is the live path over httpx (already core),
  with the lazy-import guard so tests never touch the network.
- Structured output is pydantic-validated at the boundary
  (`complete_structured`): any parse or schema failure is a typed
  `ModelOutputError` naming the violation; the gateway is
  structured-only — freetext is refused (deliberately unlike
  TradingAgents' `invoke_structured_or_freetext` fallback). A model
  that cannot produce schema-valid JSON contributes no research
  artifact.
- Local-first posture: `model_gateway_url` defaults to
  `http://127.0.0.1:11434` (a loopback endpoint — the documented
  reference, not a hard requirement); a non-loopback host is refused
  at construction unless `allow_remote=True` is passed explicitly —
  a construction-time decision, never env-driven (the M6
  migration-host precedent, strengthened). `QUANTMESH_MODEL_API_KEY`
  (if set) is injected as the Authorization header per request and
  never serialized: it appears in no repr, no exception, and no log
  line (the M5 signer-redaction discipline; proven by the
  redaction-scan test).

### Decision 2 — Role outputs are schemas without execution-shaped
fields; the pipeline order is deterministic and the critic gate blocks
in code (Phase B, issue #46)

(Recorded when Phase B lands.)

### Decision 3 — Retrieval is lexical-first; citations are resolvable
identities (Phase C, issue #47)

(Recorded when Phase C lands.)

### Decision 4 — The tool registry contains no execution surface;
prompt data is redacted before the wire; decision records are
content-addressed (Phase D, issue #48)

(Recorded when Phase D lands.)

### Decision 5 — Acceptance evidence is scripted-fixture-based; a live
local model is an optional operator drill, never a merge gate
(Phase E, issue #49)

(Recorded when Phase E lands.)

## Consequences

- The ai package adds no new dependency: httpx and pydantic are
  already core; retrieval is pure python; embedding reranking, if
  ever added, is a lazy extra behind the `RetrievalSource` protocol.
- A remote model endpoint requires explicit code-level construction
  (`allow_remote=True`); environment configuration can point the
  gateway at any loopback server but cannot escalate to remote.
- Model nondeterminism is contained by construction: pipeline
  identity never includes model outputs (Phase B), and structured
  validation refuses anything the model cannot express exactly.
- The M2 paper kernel and M5 execution adapters remain unreachable
  from this package: no tool exists for them, no role schema can
  carry an order, and the dispatch module cannot import them
  (structural, proven by test in Phases B/D).
- A hostile model cannot exfiltrate secrets the redaction pass did
  not already remove, and retrieved documents cannot summon tools
  the calling role does not hold (Phases C/D tests).
