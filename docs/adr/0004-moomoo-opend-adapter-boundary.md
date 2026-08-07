# ADR-0004: Moomoo OpenD adapter boundary, error taxonomy, and credential boundary

Status: accepted (2026-08-08)

## Context

M4 (iteration 0006) reaches a local Moomoo OpenD instance for diagnostics,
market data, and simulated orders. The vendor SDK is a pinned Git submodule
(`vendor/components/py-moomoo-api`), synchronous/callback-oriented, with
version-varying error codes. M3 established fixture-first venues: adapters
must be fully testable without the real system, and provider payload shapes
must never leak into QuantMesh contracts. Trading through OpenD additionally
requires an unlocked trade session — a human-only action involving a
password QuantMesh must never see.

## Decision

1. **One boundary, injected transport.** All OpenD access goes through
   `MoomooOpenDClient` constructed with an `OpenDTransport`; nothing else in
   QuantMesh imports the vendored SDK. Tests inject stub transports; the
   default `SdkTransport` is the only SDK-touching code.
2. **Lazy SDK import.** `SdkTransport` imports `moomoo` inside `probe`, so
   constructing clients and all fixture paths work with the SDK absent; a
   missing SDK is a typed `OpenDSdkMissingError`, not an import crash.
3. **Typed error taxonomy** (base `OpenDError`, subclass of `RuntimeError`):
   - `OpenDUnavailableError` — down, unreachable, or timed out.
   - `OpenDAuthRequiredError` — the trade session is locked; unlocking is
     human-only.
   - `OpenDSdkMissingError` — the vendored SDK is not importable.
   - `OpenDProtocolError` — a probe payload cannot be trusted (fail closed).
4. **Auth is reportable state, not a crash.** A locked session appears in
   `OpenDCapabilities.auth_required` with `order`/`order_query` forced
   `False` — a locked account must never look tradable. `OpenDAuthRequiredError`
   is only raised when the probe itself cannot complete.
5. **Credential boundary.** The client never accepts, reads, stores, or logs
   a password; it never unlocks the trade session; its probe requests no
   account data, and any response that would contain account data is never
   persisted (the Phase A probe reports only capability booleans).
6. **Explicit operator reach.** A real local OpenD is reached only through
   the `quantmesh-moomoo probe` operator command (and later the Phase E
   simulated-account drill). Ingestion, backtesting, and default paths never
   construct the SDK transport.
7. **Probe payload contract.** Capabilities are the booleans
   `quote`, `history_kline`, `order`, `order_query`, `auth_required`;
   missing or mistyped keys are `OpenDProtocolError`; extra vendor keys are
   tolerated (the vendored SDK grows fields).

## Consequences

- Unit tests run with neither OpenD nor the SDK (26 Phase A tests).
- The SDK path's live behavior (context creation, error-code wording) is
  validated only at the Phase E operator gate with a human-provided
  simulated-account OpenD; the error classifier's keyword heuristics may be
  adjusted after that validation.
- Future Moomoo capabilities (market data, simulated orders) extend the
  transport protocol and client methods without touching the boundary rules
  above.
