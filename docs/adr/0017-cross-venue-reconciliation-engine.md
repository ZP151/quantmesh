# ADR-0017 — Cross-venue reconciliation engine

- Status: accepted
- Date: 2026-08-15
- Deciders: solo delivery (iteration 0024, issue #114)
- Related: ADR-0006 (broker/paper reconciliation policy), ADR-0016 (shared
  JSONL persistence — the stable layer this builds on)

## Context

Iteration 0013 Phase E ranked cross-venue reconciliation a "Strong" follow-up,
sequenced after durable JSONL persistence stabilized (iterations 0022/0023).
The Moomoo (`quantmesh.moomoo.reconciliation`) and Hyperliquid
(`quantmesh.hyperliquid.reconciliation`) bindings repeated the same pairing,
classification, tolerance comparison and adoption flow, differing only in wire
shapes, message nouns and status mapping. The shared `execution/reconciliation`
module held only the contract types; the comparison *engine* was copy-pasted.

## Decisions

### 1. A venue-neutral comparison engine, parameterized by noun and formatter

The shared module now owns the numeric comparison engine:

- `compare_quantities`, `compare_prices`, `compare_fees`, `compare_fill_ids`,
  `compare_positions` — the ADR-0006 tolerance math, in one place.
- `finding`, `dedupe_by_id`, `is_terminal` — the shared helpers.

Callers parameterize rather than subclass: each comparison takes the venue's
message `noun` ("broker" / "venue"), and quantities take a `fmt` formatter
(Moomoo prints `100.0`, Hyperliquid prints `100` via `:g`); fees and fill-ids
take a `row_noun` ("deals"/"fills"). Findings are byte-identical to the
pre-extraction bindings, except one reviewed message wording (Moomoo's
fee-missing-data message gained a definite article).

### 2. Venue-specific behavior stays in the adapters

Status mapping (Moomoo's explicit `BROKER_STATUS_TO_DOMAIN`, Hyperliquid's
derived `_surface_status`), Moomoo's timestamp compare and unhealthy-deal
check, the mapping channel (`_by_remark` vs `_by_cloid`) and adoption
(`_adopt_progress`) remain venue-local: they depend on wire shapes and are not
part of the shared numerics.

### 3. ADR-0006 conservative defaults preserved

The tolerance defaults stay exact; identity still comes only from the journal;
ambiguous or divergent pairs are never adopted; and the shared comparison never
cancels, modifies or reverses an order. The extraction changes no finding
*kind*, only (in one case) a message wording.

## Consequences

- Positive: drift, missing-data, revoked-fill and position behavior is now
  tested once at the seam and can no longer drift between bindings.
- Positive: a third venue adapter would reuse the engine and implement only its
  wire-shape mapping, status derivation and adoption specifics.
- Negative: the engine is not a full reconciliation orchestrator — pairing,
  classification and adoption remain per-venue, so a new venue still
  reimplements that control flow.
- Open: `is_progress` remains duplicated because Hyperliquid's "open" row
  semantics differ; a future slice could parameterize it if a third venue
  needs a third variant.
