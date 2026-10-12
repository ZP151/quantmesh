# QuantMesh offline contract evaluation

Dataset: `2.0.0` / `1e82d31bd42c3cb751ea88b00abff2487e5c5d5767e183e2a8362c414bf3921d`
Code: `d6cefb8f91e22f29898e1fd0f1d9deab4bb39463`; status: **complete**

Scripted model responses; no real-model quality or investment-return claim.

| Bucket | n | Success | First pass | Verifier pass | p95 seconds |
|---|---:|---:|---:|---:|---:|
| all | 24 | 100.0% | 100.0% | 100.0% | 4.049 |
| scenario/boundary | 4 | 100.0% | 100.0% | 100.0% | 2.046 |
| scenario/happy-path | 4 | 100.0% | 100.0% | 100.0% | 3.038 |
| scenario/high-complexity | 2 | 100.0% | 100.0% | 100.0% | 2.038 |
| scenario/historical-regression | 3 | 100.0% | 100.0% | 100.0% | 6.046 |
| scenario/recovery | 4 | 100.0% | 100.0% | 100.0% | 4.049 |
| scenario/security | 7 | 100.0% | 100.0% | 100.0% | 2.046 |
| difficulty/easy | 2 | 100.0% | 100.0% | 100.0% | 2.042 |
| difficulty/hard | 11 | 100.0% | 100.0% | 100.0% | 6.046 |
| difficulty/medium | 11 | 100.0% | 100.0% | 100.0% | 3.038 |
| task_type/retrieval-contract | 2 | 100.0% | 100.0% | 100.0% | 2.045 |
| task_type/scripted-ai-contract | 5 | 100.0% | 100.0% | 100.0% | 3.038 |
| task_type/workflow-contract | 17 | 100.0% | 100.0% | 100.0% | 6.046 |

Model calls (scripted): 18; ToolRegistry calls: 6; tool error rate: 66.7% (includes expected refusals).
Declared human intervention rate: 0.0%.
Tokens/cost: N/A (scripted transport usage is not real provider usage).
Regression rate: N/A in a single run; use the compare command.

| Task | Status | Category (observed boundary, not proven root cause) | Acceptance |
|---|---|---|---|
| QM-001 | passed | — | Copilot is ready; analyst and critic each execute once and produce two decision records; repeated request and reopening without gateways return the identical accepted record. |
| QM-002 | passed | — | All five invalid citation variants fail with the matching validation error: missing pointer, container value, escaped segment, invalid array index and incorrect value digest. |
| QM-003 | passed | — | Cross-packet draft identity and unauthorized direction/approval fields are rejected by packet binding or schema validation. |
| QM-004 | passed | — | All nine gateway, timeout, JSON, authority, packet, citation and critic faults produce degraded advisory state, no accepted record and no decision log; packet bytes and parsed packet remain unchanged. |
| QM-005 | passed | — | Both captured model request bodies exclude the synthetic environment secret and include a redaction marker; the scripted result still becomes ready. |
| QM-006 | passed | — | Preview is pending and pins forecast, dataset, revision, instrument and confirmation token; account orders and journal remain empty. |
| QM-007 | passed | — | An empty confirmation token produces no order; the exact token produces one journal order with proposal-bound idempotency key and the requested position quantity. |
| QM-008 | passed | — | Two service instances confirming concurrently return identical results, create exactly one journal order and two ledger events, and each account view recovers a position quantity of one. |
| QM-009 | passed | — | After a journaled order and failed proposal transition, a later retry with unavailable forecast recovers the original confirmation and timestamp without a second journal order or duplicate position. |
| QM-010 | passed | — | Recovering the initial snapshot from the submitted journal order exactly reproduces post-submit cash, positions, orders and order sequence. |
| QM-011 | passed | — | Confirmation five days after preview is blocked with the forecast freshness reason; neither account nor journal contains an order. |
| QM-012 | passed | — | Seven point errors match the hand calculation, MAE is 39/7, random-walk benchmark MAE is 52/7, coverage is 5/7 and terminal error is -3; interval boundary equality counts as a hit. |
| QM-013 | passed | — | A missing third session plus an unscheduled bar yields partial status and six observations; the missing row stays null, the fourth row retains its exact timestamp match and aggregate scores remain null. |
| QM-014 | passed | — | All pending, empty and unavailable variants preserve the expected status and observation count, provide a reason and expose null aggregate scores rather than fabricated zero error. |
| QM-015 | passed | — | After saving the exact forecast comparison, replacing history and reopening the review store must return the frozen saved comparison and leave review JSONL bytes unchanged. |
| QM-016 | passed | — | Both metrics channels, batch/sequential persistence and five time/content variants retain distinct observations, deduplicate exact repeats, produce no false quarantine and replay exactly the admitted rows. |
| QM-017 | passed | — | The recorded closed-candle revision retains both volume observations, deduplicates identical redelivery and keeps the actual local async pump alive; BTC, ETH and SOL quotes arrive with no quarantine. |
| QM-018 | passed | — | With 4096 retained rows, both actual append hit and miss query plans contain Index Scan and no Sequential Scan; duplicate sequence is retained, the new sequence advances once and quarantine stays empty. |
| QM-019 | passed | — | With 100000 retained rows and DuckDB memory_limit=32MB, latest completes and returns exactly BTC/ETH times quote/trade/metrics: six scopes. This does not claim total process RSS or a latency SLA. |
| QM-020 | passed | — | All eight dispatch tests pass: the analyst/critic/risk/portfolio permission matrix matches policy, permitted dispatch reaches the expected surface, forbidden and unknown roles/tools raise typed errors, and a forbidden dispatch never touches its surface. |
| QM-021 | passed | — | Ingesting document d-1 with BTC rally momentum and dispatching analyst retrieve_documents(query=btc, top_k=2) through the real DocumentSource produces exactly [document:d-1] BTC rally momentum. |
| QM-022 | passed | — | The workstation browser-origin predicate refuses an attacker-controlled hostname beginning with 127. rather than treating a textual prefix as a loopback IP address. |
| QM-023 | passed | — | The generic research pipeline refuses a scripted analyst citation that is absent from supplied evidence even if its scripted critic returns pass; it must not accept the fabricated evidence as a successful research result. |
| QM-024 | passed | — | A continuous real-provenance quote whose source time is stale but whose receipt time is fresh cannot produce a filled paper order through the live quote fence; recent delivery must not erase source age. |
