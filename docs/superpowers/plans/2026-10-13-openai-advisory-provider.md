# OpenAI advisory provider implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Make the independent advisory service compatible with the operator-selected current OpenAI model, without enabling paid effects before server qualification.

**Architecture:** Add a service-owned Responses transport under the existing typed ModelGateway and ApprovedRemoteGateway boundary. Preserve the durable one-effect-per-report ledger, frozen contracts, and independent backtest success. Offline protocol tests qualify compatibility; real provider and aggregate Linux execution require separate measured acceptance.

**Tech Stack:** Existing pinned httpx/Pydantic and standard library; no OpenAI SDK or dependency/lock changes.

**Spec:** `docs/superpowers/specs/2026-10-12-research-foundation.md`, Workers Task2 in `2026-10-12-research-workers-workstation.md`, portfolio budget plan `2026-10-13-research-portfolio-budgets.md`.

Status: bounded refinement of approved Option A/#171. The operator selected the latest OpenAI model and authorized existing independent implementation sessions. Current default is `gpt-6.1-sol`, verified against official API documentation on October13. This does not establish account access, authorize data egress, install a key, or activate a paid call. Coordinator head `c545c02093b5f7e3d8dedb5ccc79b128c9dc014f` is the software baseline; its complete release CI is still running.

Subsequent Task1 software checkpoint: c545 CI38352153020 completes SUCCESS;
the provider's new source still needs its combined final-head gate. Two bounded
Spec/Standards rounds finish; R1 DNS executor-shutdown P2 is corrected through
an owned resolver and R2 Linux-only test markers are applied. Two implementation
turns end from harness model capacity, not test failure. Root takes over remaining
closeout, reproduces caller-module shadow RED1, adds isolated resolver `-I`,
then final affected131tests/48.60s/JUnit and Ruff/format pass. This last narrow
fix is author-verified after R2, not a third structural review. Runtime after
admission81licenses/6669RECORD/zero.pyc and schema/protocol/locks remain intact.
No model activation, real DNS/TCP/TLS/API call/key or new image/environment.
Task2/production/aggregate qualification and full Option A stay pending.

## Global constraints

- Keep paper=true/live=false, advisory only, one immutable report citation and no order authority.
- Preserve the nine-method JobStore, v1 request/schema digests, existing core wire/gateway, numerical engine, portfolio schema and both locks.
- Existing defaults remain 2 global slots, 60-second lease/15-second heartbeat, 900 seconds/2048 MiB/1 CPU/12 calls/$1 estimate per job. Operating allowance is $50 per UTC month and development allowance $200 total. Unknown effects retain reservations and are never automatically recalled.
- Fixed construction-time origin `https://api.openai.com`, endpoint `/v1/responses`, explicit SecretStr and remote consent; no environment key/proxy/account discovery or user-request endpoint.
- Text-only approved report/context. No uploaded programs, external tools, web search, images, files, conversations, previous response, streaming or background mode.
- No server provisioning, real API requests, paid calls, credentials, OpenD/helper/tunnel changes or broad local release run in this task.
- Current runtime bootstrap stays model-unavailable until qualified aggregate Linux containment, explicit server secret and data-egress acceptance. A process-group/RLIMIT-only test is not server containment certification.

## Review focus

1. Old `temperature`/`max_tokens` fields or unsupported tools silently reaching the provider: encode only the frozen Responses fields and reject unrecognized input.
2. Nested usage, booleans or incomplete/refused/tool output becoming successful advisory evidence: strictly normalize supported integers and fail closed before publication.
3. Redirects, inherited proxies, exception bodies or oversized responses leaking configuration: disable redirects and trust_env, bound request/response bytes, use fixed error categories.
4. Alias/pricing changes permitting an unbudgeted call or invented version: exact model/price table match; reserve the explicit conservative amount before any effect; account/model access remains unverified offline.
5. Configuration/restart/timeout repeating an external effect: same existing report identity, response replay and retained ambiguous reservation; valid backtest remains succeeded.

## Task1 — Service-owned Responses compatibility and offline advisory loop

**Files:**
- Create `services/research_agent/src/qm_research_agent/openai_responses.py`.
- Create `services/research_agent/tests/test_openai_responses.py`.
- Modify only the provider section of `services/research_agent/README.md`.
- Shared orchestrator/runtime/bounded/core/CI/locks are coordinator-owned and unchanged; propose a patch if a demonstrated necessary dependency appears.

**Interfaces:**
- `OpenAIResponsesTransport(ModelTransport)`: explicitly configured, pickle-safe before invocation, lazily creates and closes httpx client per bounded effect. Consumes the existing `build_chat_body` representation and produces the existing validated chat-shaped payload for `parse_completion`; no core DTO changes.
- `OpenAIResponsesGateway(ApprovedRemoteGateway)`: consumes `key: SecretStr`, `allowed_origins: frozenset[str]`, `remote_consent: bool`, exact configured model and known price version. Preserves the existing construction-time origin validation and instance admission boundary.
- `OpenAIPriceTable`: frozen versioned Decimal input/cached-input/cache-write/output rates and supported model/tier/context identity; no mutable environment prices. Default source version `openai-gpt-6.1-sol-standard-2026-10-13`, rates per million $2/$0.10/$2.50/$10. Rates are source metadata, not actual invoice reconciliation.
- `make_openai_advisory(store, effects, *, key, allowed_origins, remote_consent, model, price_version) -> tuple[AdvisoryRunner, OpenAIResponsesGateway]`: constructs provider `openai`, known version and conservative `Decimal('1.00')` reservation. The ledger and per-job/portfolio caps remain the sole admission authority. Do not refund reservations from token estimates.

- [ ] Write protocol/admission RED fixtures. Assert explicit origin/consent/key required; hostile env cannot redirect a request; default model is gpt-6.1-sol; unknown model/version rejects before client creation; repr/error output never includes key, prompt, raw error or configured account data.
- [ ] Run focused RED in the existing audited service environment using `python -B -m pytest -p no:cacheprovider services/research_agent/tests/test_openai_responses.py -q --basetemp <new-owned-root>`; preserve actual assertions. No real key/network is used.
- [ ] Implement the transport/gateway/factory. Request uses model, input messages, `reasoning.effort='low'`, `max_output_tokens` from the positive request cap (at most1024), `store=false`, `background=false`, `stream=false`, `service_tier='default'`; omit old temperature/max_tokens. Encode JSON with allow_nan=false and maximum65536 UTF-8 bytes. Optional existing JSON-schema response_format maps to Responses text.format only; no freetext trading fallback. Inputs outside this envelope reject rather than truncate reports.
- [ ] Add HTTP mock RED/GREEN for fixed URL, no redirects/proxies/retries, TLS verification, 30-second deadline and maximum65536 response bytes, including dishonest Content-Length and streamed excess. Close every response/client. Non-2xx, network errors, non-JSON, malformed object, missing/unknown usage and unexpected model identity return sanitized failure.
- [ ] Normalize only a completed response with one assistant message/output_text, allowing non-published reasoning metadata. Refusal, tool output, incomplete status/details or error rejects. Usage input/output/total and nested cached/reasoning counts must be exact nonnegative integers (bool rejected), consistent and bounded by totals. Preserve exact returned model; never manufacture a dated snapshot or call usage a provider bill.
- [ ] Add actual runner/ledger integration fixtures with an in-memory mocked HTTP transport and valid immutable report: reserve before effect; one succeeded advisory archive with correct citation and explicit openai model/price metadata; repeat after service reconstruction replays the saved response without another transport call. Exhausted per-job/portfolio caps and unknown price have zero calls. Ambiguous timeout retains its reservation and returns unknown_effect while the backtest remains succeeded. Mocking an HTTP effect is not a real provider/native containment witness.
- [ ] GREEN focused protocol and existing affected Agent/budget/service tests; run Ruff and whitespace check. Recheck schema/protocol/locks and borrowed runtime admission/bytecode state. At most two fresh bounded Spec/Standards rounds for this new provider slice; do not repeat completed foundation reviews.
- [ ] Commit/push a coherent isolated checkpoint and immutable RED/GREEN/review handoff; root integrates sequentially after the live current-head CI checkpoint. Stop before runtime activation and real provider requests.

## Task2 — Server activation boundary (coordinator, gated)

Task1 software compatibility is insufficient for this step. After qualified aggregate Linux model execution and the private AWS service deployment packet, supply concrete operator configuration for the server-only key, approved report egress, exact model availability, current price source and small paid test cap. Keep required human release reviews and exact merged bytes.

- [ ] Configure a named owner-only server secret file through the approved server mechanism; never ask for a key in chat or copy workstation secrets. An unset or unavailable model stays explicitly unavailable.
- [ ] Verify account access and exact returned model with one explicitly authorized bounded advisory report, then restart/replay/cancellation/timeout/budget behavior using real server evidence. Avoid changing one-effect identity to force repeat charges on an old report.
- [ ] Measure aggregate resource containment, sanitized usage, private workstation advisory/report/reload flow and actual provider availability. Retain unknown effects rather than fake success. Actual provider invoices/external activity remain outside ledger authority.

No real-provider claim, investment-quality claim or full Option A completion comes from Task1. Numerical Worker/Linux image, real server-source cutover, private host/PG/TLS/offhost restore/p95 and end-user acceptance remain separate deliverables.

## Official sources and data boundary

[GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) documents the selected alias, supported reasoning levels and prices. [Responses migration](https://developers.openai.com/api/docs/guides/migrate-to-responses) supports the endpoint choice and explicit store=false. [Data controls](https://developers.openai.com/api/docs/guides/your-data) distinguish application state from abuse monitoring: store=false does not establish Zero Data Retention; abuse monitoring can retain data for up to30 days, and special controls require provider approval. Only specifically approved report/context can leave the private server. Provider choice alone is not broad data-egress approval.
