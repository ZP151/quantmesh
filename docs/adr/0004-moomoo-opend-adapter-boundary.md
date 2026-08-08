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

## Extension (2026-08-08, issue #26 Phase B): market-data payload contract

Phase B adds historical klines, real-time tickers and stock quotes through
the same boundary. The rules above are unchanged; this extension fixes the
wire contract between transport and adapter.

8. **Pandas stops at the transport.** The vendored SDK returns DataFrames;
   `SdkTransport` converts them to plain dict payloads, so no DataFrame
   (and no SDK type) appears anywhere else in QuantMesh. The wire contract
   is: a top-level mapping with ``code`` (market-qualified, e.g.
   ``"US.AAPL"``) and ``rows`` (a list of row mappings), plus contract keys
   per request. Extra vendor keys are tolerated; missing or mistyped keys
   fail closed with ``OpenDProtocolError``.
9. **Kline payload** carries ``interval`` (canonical, e.g. ``"1d"``, ``"5m"``)
   and ``autype`` (``"None"`` raw / ``"qfq"`` / ``"hfq"``); each row has
   ``time_key``, ``open``, ``high``, ``low``, ``close``, ``volume``.
   ``SdkTransport`` maps the canonical interval to the SDK ``KLType``
   (1m/3m/5m/15m/30m/60m/1d/1w); month/quarter/year klines have no
   canonical representation and are refused.
10. **Ticker payload** rows carry ``time``, ``price``, ``volume`` and
    optionally ``sequence`` and ``direction`` (``"BUY"``/``"SELL"``/
    ``"NEUTRAL"``/``"N/A"``); quote payload rows carry ``data_date``,
    ``data_time`` and ``last_price`` (plus optional volume/turnover/OHLC).
    Quote mapping targets the canonical ``Quote`` (last/volume; bid/ask are
    not in the stock-quote payload and stay ``None``).
11. **Venue-local wall-clock strings are provider metadata.** The SDK
    reports times in the venue's local zone (US = Eastern, HK/CN = Beijing)
    with no zone marker. The adapter converts them to UTC via the market
    prefix of the payload code: ``US`` → ``America/New_York``, ``HK`` →
    ``Asia/Hong_Kong``, ``CN`` → ``Asia/Shanghai`` (DST-aware via
    ``zoneinfo``/``tzdata``). An unknown market prefix, an unparseable time,
    or a payload code whose symbol does not match the requested instrument
    is an ``OpenDProtocolError`` — never a guessed timestamp.
12. **Raw prices are the default.** ``autype`` defaults to ``"None"``
    (unadjusted). An adjustment type is explicit at the request; the
    payload echoes it back and the adapter validates it, so bars from an
    unknown adjustment are never trusted.
13. **The OpenD ingestion path is explicit construction only.**
    ``MoomooOpenDProvider`` (``ProviderMode.LIVE``) wraps client + adapter
    into the canonical ``Provider`` surface (bars, trades) and is
    constructed by hand with an injected transport — tests inject wire
    fixtures, an operator injects ``SdkTransport``. The fixture-only
    ``ProviderRegistry`` still refuses it, so no default or registered
    path can reach OpenD. The lake persists bars; trades and quotes are
    canonical models without a lake path in Phase B.

## Consequences

- Unit tests run with neither OpenD nor the SDK (26 Phase A tests).
- The SDK path's live behavior (context creation, error-code wording) is
  validated only at the Phase E operator gate with a human-provided
  simulated-account OpenD; the error classifier's keyword heuristics may be
  adjusted after that validation.
- Future Moomoo capabilities (market data, simulated orders) extend the
  transport protocol and client methods without touching the boundary rules
  above.
- The market-data transport methods default to ``NotImplementedError`` in
  the protocol, so a probe-only transport is still a valid
  ``OpenDTransport``; the client surfaces the failure at call time.
- Time-format drift (the SDK's venue-local strings) is the likeliest
  Phase E adjustment; the adapter's parse formats are centralized in one
  module.
