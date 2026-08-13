# ADR-0004: Moomoo OpenD adapter boundary, error taxonomy, and credential boundary

Status: accepted (2026-08-08)

## Context

M4 (iteration 0006) reaches a local Moomoo OpenD instance for diagnostics,
market data, and simulated orders. The SDK audit source is a pinned Git
submodule (`vendor/components/py-moomoo-api`); an admitted runtime is a
separately installed compatible package. The boundary is synchronous/callback-
oriented, with version-varying error codes. M3 established fixture-first venues: adapters
must be fully testable without the real system, and provider payload shapes
must never leak into QuantMesh contracts. Trading through OpenD additionally
requires an unlocked trade session — a human-only action involving a
password QuantMesh must never see.

## Decision

1. **One boundary, injected transport.** All OpenD access goes through
   `MoomooOpenDClient` constructed with an `OpenDTransport`; nothing else in
   QuantMesh imports the compatible SDK runtime. Tests inject stub transports; the
   default `SdkTransport` is the only SDK-touching code.
2. **Lazy SDK import.** `SdkTransport` imports `moomoo` inside `probe`, so
   constructing clients and all fixture paths work with the SDK absent; a
   missing SDK is a typed `OpenDSdkMissingError`, not an import crash.
3. **Typed error taxonomy** (base `OpenDError`, subclass of `RuntimeError`):
   - `OpenDUnavailableError` — down, unreachable, or timed out.
   - `OpenDAuthRequiredError` — the trade session is locked; unlocking is
     human-only.
   - `OpenDSdkMissingError` — a compatible SDK runtime is not importable.
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
   tolerated (compatible SDK versions may grow fields).

## Extension (2026-08-08, issue #26 Phase B): market-data payload contract

Phase B adds historical klines, real-time tickers and stock quotes through
the same boundary. The rules above are unchanged; this extension fixes the
wire contract between transport and adapter.

8. **Pandas stops at the transport.** The compatible SDK returns DataFrames;
   `SdkTransport` converts them to plain dict payloads, so no DataFrame
   (and no SDK type) appears anywhere else in QuantMesh. The wire contract
   is: a top-level mapping with ``code`` (market-qualified, e.g.
   ``"US.AAPL"``) and ``rows`` (a list of row mappings), plus contract keys
   per request. Extra vendor keys are tolerated; missing or mistyped keys
   fail closed with ``OpenDProtocolError``.
9. **Kline payload** carries ``interval`` (canonical, e.g. ``"1d"``, ``"5m"``)
    and ``autype`` (``"None"`` raw / ``"qfq"`` / ``"hfq"``); each row has
    ``code``, ``time_key``, ``open``, ``high``, ``low``, ``close``, ``volume``.
    Every row code must equal the requested market-qualified top-level code;
    a synthesized envelope can never relabel a mismatched source row. Intraday
    intervals require a venue wall-clock timestamp; date-only source values are
    accepted only for daily and weekly bars.
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

## Extension (2026-08-14, issue #110 Task 5): complete read-only evidence

14. **A history request is one bounded context lifetime.**
    `MoomooOpenDClient.history_pages` follows the opaque `page_req_key` until
    the SDK returns `None`, while enforcing cumulative page and row limits.
    The real SDK transport keeps one `OpenQuoteContext` open for the complete
    chain; it does not assume that an opaque cursor is portable across
    contexts. Repeated cursors and empty nonterminal pages fail closed. Every
    SDK result must have its documented tuple arity and an exact integer
    status; booleans, floats and malformed envelopes are protocol failures.
15. **Pagination evidence is canonical-JSON-safe.** The transport retains SDK
    cursor bytes while requesting the next page. Returned evidence encodes
    each non-null cursor as `base64:<payload>`, preserving every byte without
    leaking a Python `bytes` value into an immutable artifact. SDK scalar
    values are normalized to strict JSON types; `NaN`, `NaT` and `NA` source
    missing values become JSON `null`, while infinities and unsupported values
    fail closed.
16. **Requested dates and event instants remain separate boundaries.** The
    client validates ISO venue-date bounds and forwards them unchanged. The
    provider first rejects reversed UTC instants, converts accepted bounds to
    venue dates for the SDK, rejects a
    paginated source row outside those venue-date bounds, preserves the
    complete accepted response, then applies the narrower UTC event filter to
    canonical bars. The one-page legacy fixture compatibility wrapper is
    explicitly marked and remains date-validated, but a marked response can
    serve only compatibility reads: `fetch_raw_bundle` rejects it because one
    page cannot prove complete pagination.
17. **Corporate actions are source evidence, not derived prices.** Read-only
    adjustment factors use `get_rehab`; split pages use
    `get_corporate_actions_stock_splits` until the documented `"-1"` terminal
    key; dividends use `get_corporate_actions_dividends`. Missing list/cursor
    keys, malformed rows, empty nonterminal split pages and cursor loops are
    protocol failures. Task 5 does not infer an adjustment policy.
18. **A compatible SDK is a gated runtime prerequisite.** The repository audit
    submodule is pinned at commit
    `dfb09498bdd34bdeb37c12b3cfec6d55908450d9` (`10.02.6208`), which does not
    expose the split or dividend methods. The Apache-2.0
    `moomoo-api==10.10.7008` source distribution was inspected and does expose
    the documented methods, but it is not admitted as a project dependency in
    Task 5. Task 6 must pin and audit its complete optional closure before an
    operator runtime can use it. An older installed SDK receives a typed
    `OpenDProtocolError`; QuantMesh never reports empty action data in its
    place.
19. **Collection remains quote-only.** History, adjustment, split and dividend
    calls create only `OpenQuoteContext`. They never construct a trade
    context, call `unlock_trade`, request credentials or acquire execution
    authority. The older general capability probe remains outside this
    collection path and is not evidence that a dataset was collected.
20. **Timeout enforcement remains a collection-process gate.** The synchronous
    vendor context does not expose a per-call cancellation primitive. The
    existing timeout settings therefore must not be presented as an enforced
    hard deadline by this transport. Task 6 must execute real collection under
    the bounded job/process deadline before any Moomoo result can qualify as
    complete trusted evidence.

Official surfaces rechecked for this extension:

- [Historical klines](https://openapi.moomoo.com/moomoo-api-doc/en/quote/request-history-kline.html)
- [Adjustment factors](https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-rehab.html)
- [Stock splits](https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-corporate-actions-stock-splits.html)
- [Dividends](https://openapi.moomoo.com/moomoo-api-doc/en/quote/get-corporate-actions-dividends.html)

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
