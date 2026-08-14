# Trusted Data Fabric Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or the repository's equivalent
> main-writer/read-only-reviewer loop to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one immutable, idempotent, quality-gated read-only data chain
for Moomoo AAPL/NVDA and Hyperliquid BTC/ETH/SOL, then prove it from a clean
installation and a frozen seven-day evidence window.

**Architecture:** Evolve QuantMesh's owned provider/lake contracts with
capability resolution and a v2 content-addressed fabric. Preserve v1 reads
during migration; publish all new trusted data as immutable raw, normalized,
adjusted and feature artifacts linked by SHA-256 manifests. Use durable
collection checkpoints and versioned quality reports as the only route to the
read-only catalog and downstream research surfaces.

**Tech Stack:** Python 3.11+, Pydantic 2, DuckDB/Parquet, httpx, official
Moomoo OpenD SDK boundary, official Hyperliquid HTTP/WebSocket protocols,
`exchange-calendars==4.13.2`, FastAPI, React 19, TypeScript 5.9, TanStack Query,
Vitest and Playwright.

## Global Constraints

- Start from `origin/main` commit
  `d4aeed3d988378a9739ef6ce1a168cf326804294`.
- Treat `v0.1.1-rc1` at
  `b6b05b96f232366dad31177e2e8e13ab23c08b97` as immutable.
- Do not create or promote final `v0.1.1`.
- Keep Moomoo and Hyperliquid data access read-only; do not broaden any exchange,
  signing, wallet, broker or order transport.
- Keep paper mode as the only execution authority.
- Add no strategy, model, algorithm competition, AI workflow or order authority.
- Never insert fixture, demo or synthetic rows into a real dataset or count them
  as real-data evidence.
- The main thread is the only source writer. Planner, Quant Researcher,
  Reviewer and Verifier agents are read-only.
- Use one integration branch and one final milestone PR for issue #110.
- Stop for explicit operator authorization before credentials, paid services or
  a major architecture change.
- Every behavior change follows red/green/refactor and receives a fresh
  read-only review before the next task.
- Mirror each green task, review verdict and verification command into
  `docs/iterations/0021-trusted-data-fabric.md`.

---

## File map

New focused modules:

- `src/quantmesh/data/capabilities.py`: provider descriptors and resolution
  query contracts.
- `src/quantmesh/data/instruments.py`: canonical IDs and effective aliases.
- `src/quantmesh/data/calendars.py`: versioned XNYS and 24/7 session semantics.
- `src/quantmesh/data/objects.py`: SHA-256 object storage.
- `src/quantmesh/data/artifacts.py`: immutable v2 manifests and current-pointer
  compare-and-swap.
- `src/quantmesh/data/envelopes.py`: bitemporal raw envelope contract.
- `src/quantmesh/data/fabric.py`: raw-to-feature publication pipeline.
- `src/quantmesh/data/adjustments.py`: explicit equity and identity-adjustment
  transforms.
- `src/quantmesh/data/collection.py`: run identity, attempts and publication
  orchestration.
- `src/quantmesh/data/checkpoints.py`: durable single-writer checkpoint state.
- `src/quantmesh/data/quality.py`: SLA policies and immutable evaluations.
- `src/quantmesh/data/catalog.py`: read-only catalog query service.
- `src/quantmesh/hyperliquid/public_info.py`: public-mainnet data-only HTTP
  transport.
- `src/quantmesh/api/data_catalog.py`: typed catalog API router.
- `frontend/src/screens/DataCatalog.tsx`: operator catalog surface.
- `tools/trusted_data.py`: collect, replay, inspect and daily-evidence CLI.
- `tools/trusted_data_soak.py`: frozen-window observer and acceptance verifier.

Existing modules remain the compatibility and product integration points:

- `src/quantmesh/data/providers/base.py`, `registry.py`, `manifest.py`, `lake.py`
  and `ingestion.py`;
- `src/quantmesh/moomoo/opend.py`, `provider.py` and `market_data.py`;
- `src/quantmesh/live/contract.py`, `buffer.py`, `hyperliquid.py` and `feed.py`;
- `src/quantmesh/instruments/contracts.py`, `history.py`, `live_history.py` and
  `forecast.py`;
- `src/quantmesh/research/features.py`, `experiments.py` and `pipelines.py`;
- `src/quantmesh/api/workstation.py` and generated frontend OpenAPI types.

---

### Task 1: Capability-aware provider resolution

**Files:**

- Create: `src/quantmesh/data/capabilities.py`
- Modify: `src/quantmesh/data/providers/base.py`
- Modify: `src/quantmesh/data/providers/registry.py`
- Modify: `src/quantmesh/data/providers/__init__.py`
- Test: `tests/test_provider_capabilities.py`
- Test: `tests/test_providers.py`

**Interfaces:**

- Produces `ProviderAccess`, `DataKind`, `EntitlementState`,
  `ProviderCapability`, `ProviderDescriptor` and `ProviderRequest`.
- `ProviderRegistry.resolve(request: ProviderRequest) -> Provider` returns one
  exact allowed capability or raises a typed `ProviderResolutionError`.
- Existing `ProviderRegistry.get(Venue)` remains fixture-compatible until all
  v1 callers migrate.

- [x] **Step 1: Write failing capability tests**

```python
def test_registry_never_upgrades_read_only_access() -> None:
    registry = ProviderRegistry([_provider(access=ProviderAccess.PUBLIC_LIVE)])
    request = ProviderRequest(
        venue=Venue.HYPERLIQUID,
        provider_id="hyperliquid-public",
        access=ProviderAccess.PAPER_BROKER,
        data_kind=DataKind.BARS,
        symbol="BTC",
        interval="1m",
    )
    with pytest.raises(ProviderResolutionError, match="paper-broker"):
        registry.resolve(request)


def test_registry_resolves_one_exact_data_capability() -> None:
    provider = _provider(access=ProviderAccess.AUTHENTICATED_READ_ONLY)
    registry = ProviderRegistry([provider])
    assert registry.resolve(_aapl_bars_request()) is provider
```

- [x] **Step 2: Verify RED**

Run:
`.\.venv\Scripts\python.exe -m pytest tests/test_provider_capabilities.py -q`

Expected: collection fails because `quantmesh.data.capabilities` does not exist.

- [x] **Step 3: Implement the minimal contracts and exact resolver**

```python
class ProviderAccess(StrEnum):
    FIXTURE = "fixture"
    PUBLIC_LIVE = "public-live"
    AUTHENTICATED_READ_ONLY = "authenticated-read-only"
    PAPER_BROKER = "paper-broker"


class DataKind(StrEnum):
    BARS = "bars"
    QUOTES = "quotes"
    BOOKS = "books"
    TRADES = "trades"
    ADJUSTMENT_FACTORS = "adjustment-factors"
    SPLITS = "splits"
    DIVIDENDS = "dividends"
```

Make provider ID plus capability the registry key. Reject duplicate provider
IDs, ambiguous matches, unsupported symbols/intervals and access-class
mismatches. Do not add execution methods to `Provider`.

- [x] **Step 4: Verify GREEN and regressions**

Run:
`.\.venv\Scripts\python.exe -m pytest tests/test_provider_capabilities.py tests/test_providers.py tests/test_ingestion.py -q`

Expected: all selected tests pass.

- [x] **Step 5: Record and review**

Update the iteration ledger with RED/GREEN commands, run Ruff on changed files,
commit `feat(data): add capability-aware provider resolution`, then dispatch a
read-only Reviewer over the task diff.

---

### Task 2: Canonical instruments and versioned calendars

**Files:**

- Create: `src/quantmesh/data/instruments.py`
- Create: `src/quantmesh/data/calendars.py`
- Modify: `pyproject.toml`
- Modify: `requirements-audit.txt`
- Modify: `docs/licenses.md`
- Modify: `docs/REUSE_MATRIX.md`
- Test: `tests/test_trusted_instruments.py`
- Test: `tests/test_market_calendars.py`
- Test: `tests/test_security.py`

**Interfaces:**

- `CanonicalInstrumentId` validates the five bounded identities from the design.
- `SymbolAlias` is effective-dated and maps provider symbol to canonical ID.
- `CalendarService.sessions(calendar_id, start, end)` returns immutable
  `SessionWindow` rows with UTC open/close and session date.
- Calendar version is `exchange-calendars:4.13.2:XNYS` or
  `quantmesh:1:24/7`.

- [x] **Step 1: Write failing calendar and alias tests**

```python
def test_xnys_skips_weekend_and_honors_early_close() -> None:
    sessions = CalendarService().sessions(
        "XNYS", date(2025, 11, 27), date(2025, 12, 1)
    )
    assert [row.session_date.isoformat() for row in sessions] == [
        "2025-11-28", "2025-12-01"
    ]
    assert sessions[0].close_at.hour == 18  # 13:00 New York, UTC in November


def test_alias_is_resolved_at_knowledge_date() -> None:
    catalog = InstrumentCatalog.bounded_default()
    assert catalog.resolve("moomoo", "US.AAPL", as_of=DATE).value == (
        "moomoo:US:AAPL:XNAS"
    )
```

- [x] **Step 2: Verify RED**

Run:
`.\.venv\Scripts\python.exe -m pytest tests/test_trusted_instruments.py tests/test_market_calendars.py -q`

Expected: imports fail because the modules are absent.

- [x] **Step 3: Add the pinned calendar dependency and implementations**

Add `exchange-calendars==4.13.2` to runtime dependencies. Record Apache-2.0
license evidence. Reject unknown calendars and dates outside the package's
supported range. Do not replace session calendars with weekday arithmetic.

- [x] **Step 4: Verify GREEN, dependency closure and license**

Run:
`.\.venv\Scripts\python.exe -m pytest tests/test_trusted_instruments.py tests/test_market_calendars.py tests/test_security.py -q`

Run:
`.\.venv\Scripts\python.exe tools/license_review.py`

Expected: tests and license closure pass.

- [x] **Step 5: Record and review**

Commit `feat(data): add canonical instruments and market calendars`; append
evidence and receive a clean read-only review.

---

### Task 3: Content-addressed objects and immutable manifests

**Files:**

- Create: `src/quantmesh/data/objects.py`
- Create: `src/quantmesh/data/artifacts.py`
- Modify: `src/quantmesh/data/manifest.py`
- Modify: `src/quantmesh/data/lake.py`
- Test: `tests/test_object_store.py`
- Test: `tests/test_artifact_manifests.py`
- Test: `tests/test_manifest.py`
- Test: `tests/test_lake.py`

**Interfaces:**

- `ObjectStore.put_bytes(media_type, payload) -> ObjectRef` writes once by
  SHA-256 and detects conflicting bytes.
- `ArtifactManifest.build(...) -> ArtifactManifest` computes its own
  `manifest_id` from canonical JSON excluding the ID field.
- `ManifestStore.publish(manifest, expected_current) -> None` writes immutable
  manifest then compare-and-swaps `current.json`.
- `ManifestStore.open(manifest_id) -> ArtifactDataset` binds exact object refs.
- Existing `Lake.dataset()` keeps reading v1 datasets.

- [x] **Step 1: Write failing immutability tests**

```python
def test_same_range_content_change_has_a_new_manifest_id(store) -> None:
    first = publish_bar_artifact(store, close=100.0)
    second = publish_bar_artifact(store, close=101.0, expected_current=first.manifest_id)
    assert first.coverage == second.coverage
    assert first.manifest_id != second.manifest_id
    assert store.open(first.manifest_id).read_bytes() != store.open(
        second.manifest_id
    ).read_bytes()


def test_open_reader_is_stable_after_new_publication(store) -> None:
    first = publish_bar_artifact(store, close=100.0)
    reader = store.open(first.manifest_id)
    publish_bar_artifact(store, close=101.0, expected_current=first.manifest_id)
    assert reader.read_bars()[0].close == 100.0


def test_current_pointer_rejects_rollback(store) -> None:
    first = publish_bar_artifact(store, close=100.0)
    second = publish_bar_artifact(store, close=101.0, expected_current=first.manifest_id)
    with pytest.raises(ManifestConflictError, match="rollback"):
        store.point_current(first.manifest_id, expected_current=second.manifest_id)
```

- [x] **Step 2: Verify RED**

Run:
`.\.venv\Scripts\python.exe -m pytest tests/test_object_store.py tests/test_artifact_manifests.py -q`

Expected: imports fail because v2 storage is absent.

- [x] **Step 3: Implement canonical object and manifest publication**

Use `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False)`
for canonical JSON. Store objects under
`.trusted-data-v2/objects/sha256/<first-two>/<digest>` and manifests under
`.trusted-data-v2/datasets/<dataset>/manifests/<manifest_id>.json`; the
leading-dot namespace cannot collide with a legal v1 dataset name. Validate
hashes on every read. Atomically replace only `current.json`; never replace an
object or manifest. Atomically activate the complete first dataset directory
from same-filesystem staging so genesis has no visible partial state.

- [x] **Step 4: Verify GREEN and v1 compatibility**

Run:
`.\.venv\Scripts\python.exe -m pytest tests/test_object_store.py tests/test_artifact_manifests.py tests/test_manifest.py tests/test_lake.py -q`

Expected: v2 immutability and all v1 regressions pass.

- [x] **Step 5: Record ADR and review**

Create `docs/adr/0016-trusted-data-fabric-and-immutable-manifests.md` with the
accepted v2 decision and v1 compatibility boundary. Commit
`feat(data): publish immutable data artifacts`; receive a clean review.

---

### Task 4: Bitemporal raw-to-feature AAPL tracer

**Files:**

- Create: `src/quantmesh/data/envelopes.py`
- Create: `src/quantmesh/data/adjustments.py`
- Create: `src/quantmesh/data/fabric.py`
- Test: `tests/test_raw_envelopes.py`
- Test: `tests/test_fabric_pipeline.py`
- Test: `tests/test_bitemporal_history.py`

**Interfaces:**

- `RawEnvelope` carries request, source identity, event/session, knowledge and
  ingestion times plus object/provider/schema metadata.
- `FabricPublisher.publish_bars(envelope, bars, adjustment_policy,
  feature_specs) -> Publication` returns four linked manifest IDs.
- `ArtifactDataset.read_bars(known_at=...)` selects the valid vintage by
  knowledge time.

- [x] **Step 1: Write failing lineage tests**

```python
def test_correction_does_not_leak_before_knowledge_time(fabric) -> None:
    original = fabric.publish(_aapl_envelope(known_at=T1), [_bar(close=100.0)])
    corrected = fabric.publish(_aapl_envelope(known_at=T2), [_bar(close=101.0)])
    assert fabric.history(original.normalized_id, known_at=T1)[0].close == 100.0
    assert fabric.history(corrected.normalized_id, known_at=T2)[0].close == 101.0


def test_raw_normalized_adjusted_feature_chain_is_complete(fabric) -> None:
    publication = fabric.publish(_aapl_fixture_envelope(), _aapl_bars())
    chain = fabric.lineage(publication.feature_id)
    assert [item.layer for item in chain] == [
        ArtifactLayer.RAW,
        ArtifactLayer.NORMALIZED,
        ArtifactLayer.ADJUSTED,
        ArtifactLayer.FEATURE,
    ]
```

- [x] **Step 2: Verify RED**

Run:
`.\.venv\Scripts\python.exe -m pytest tests/test_raw_envelopes.py tests/test_fabric_pipeline.py tests/test_bitemporal_history.py -q`

Expected: modules are absent.

- [x] **Step 3: Implement the narrow AAPL fixture tracer**

Publish fixture provenance only as nonqualifying evidence. Use an explicit
`unadjusted-identity-v1` policy for this tracer and the existing
`log_return(window=2)` implementation for its feature artifact. Do not claim a
real equity adjustment before Task 6.

- [x] **Step 4: Verify GREEN and tamper probes**

Run focused tests plus one probe that changes the raw object after publication;
expected result is a hash-mismatch failure before normalization.

- [x] **Step 5: Record Slice 1 checkpoint and review**

Commit `feat(data): add bitemporal AAPL lineage tracer`, update Slice 1 evidence
and receive a clean review.

---

### Task 5: Complete Moomoo pagination and corporate-action transport

**Files:**

- Modify: `src/quantmesh/moomoo/opend.py`
- Modify: `src/quantmesh/moomoo/market_data.py`
- Modify: `src/quantmesh/moomoo/provider.py`
- Test: `tests/test_moomoo_opend.py`
- Test: `tests/test_moomoo_market_data.py`
- Test: `tests/test_moomoo_provider.py`

**Interfaces:**

- `MoomooOpenDClient.history_pages(...) -> list[dict]` follows every unique
  cursor and enforces `max_pages`, `max_rows` and requested date bounds.
- `adjustment_factors`, `stock_splits` and `dividends` return pandas-free raw
  payloads through the existing injected transport boundary.
- `MoomooOpenDProvider.fetch_raw_bundle(...)` returns bars and source action
  payloads without deriving adjusted values.

- [x] **Step 1: Write failing pagination/action tests**

```python
def test_history_follows_every_page_and_preserves_cursors() -> None:
    transport = PagingTransport(pages=[_page("next-1", 700), _page(None, 600)])
    result = MoomooOpenDClient(transport).history_pages(
        "US.AAPL", interval="1m", start="2026-08-01", end="2026-08-07"
    )
    assert sum(len(page["rows"]) for page in result) == 1300
    assert transport.requested_cursors == [None, b"next-1"]


def test_history_rejects_repeated_cursor() -> None:
    with pytest.raises(OpenDProtocolError, match="repeated page cursor"):
        MoomooOpenDClient(RepeatingCursorTransport()).history_pages(
            "US.AAPL", interval="1m"
        )
```

- [x] **Step 2: Verify RED**

Run the three focused test files. Expected: missing paginated/action methods.

- [x] **Step 3: Implement bounded complete pagination and action payloads**

Pass `page_req_key` back to the SDK until no cursor remains. Preserve each page
as a raw response. Add official `get_rehab`, split and dividend calls using
the same error classification and context lifetime as existing quote reads.
Never unlock a trade context.

- [x] **Step 4: Verify GREEN and no-secret boundary**

Run the focused tests and `tests/test_security.py`. Expected: 1,300-row case,
cursor-loop rejection and typed unavailable/auth states all pass.

- [x] **Step 5: Record and review**

Commit `fix(moomoo): collect complete read-only history evidence`; record the
official API versions and receive a clean review.

---

### Task 6: Real Moomoo AAPL/NVDA adjusted lineage

**Files:**

- Create: `src/quantmesh/data/moomoo_collection.py`
- Modify: `src/quantmesh/data/adjustments.py`
- Modify: `src/quantmesh/data/fabric.py`
- Modify: `src/quantmesh/instruments/history.py`
- Modify: `src/quantmesh/instruments/live_history.py`
- Test: `tests/test_moomoo_collection.py`
- Test: `tests/test_equity_adjustments.py`
- Test: `tests/test_instrument_history.py`

**Interfaces:**

- `MoomooCollectionPlan.bounded_default()` contains only AAPL/NVDA and approved
  intervals.
- `MoomooCollector.collect(plan, window) -> CollectionResult` publishes raw
  pages, canonical bars/actions and split-adjusted artifacts.
- `EquityAdjustmentPolicy` pins factor/action manifests and refuses ambiguous
  or future-known actions.

- [x] **Step 1: Write failing adjustment/session tests**

```python
def test_split_adjustment_changes_ohlc_and_inverse_volume() -> None:
    adjusted = adjust_split(_pre_split_bar(), factor=2.0)
    assert adjusted.close == 50.0
    assert adjusted.volume == 2000.0


def test_future_announced_action_is_not_used_for_earlier_as_of() -> None:
    with pytest.raises(AdjustmentUnavailableError, match="knowledge time"):
        build_adjusted_series(
            bars=_bars(), actions=[_split(published_at=T2)], known_at=T1
        )


def test_closed_xnys_session_is_not_a_gap() -> None:
    report = evaluate_equity_coverage(_thanksgiving_window(), _observed_sessions())
    assert report.missing == ()
```

- [x] **Step 2: Verify RED**

Run the three focused files. Expected: collection and adjustment contracts are
missing.

- [x] **Step 3: Implement bounded collection and fail-closed adjustment**

Keep raw OHLCV, factor, split and dividend manifests separate. Implement only
the evidenced split-adjusted policy. Record dividends but leave total return
unavailable until a later authorized design. Delete the current behavior that
copies raw close into `adjusted_close` based only on a binding label.
Run the synchronous OpenD worker under an enforceable collection-process
deadline; the SDK's in-process timeout settings alone do not qualify a run as
bounded. Real collection requires a Task 6-pinned and audited compatible SDK
closure and must report an older SDK without the official action methods as
incompatible.

- [x] **Step 4: Verify GREEN and unavailable states**

Run focused tests with stub OpenD plus a real probe when OpenD is locally
available. A missing SDK/daemon/entitlement must return a typed unavailable
result and must not create a real manifest. Verify the optional Moomoo closure
and Apache-2.0 package evidence before admitting it to the operator environment.

- [x] **Step 5: Record Slice 2 checkpoint and review**

Commit `feat(moomoo): publish trusted equity data lineage`; record whether the
optional real probe ran and receive a clean review.

---

### Task 7: Public-mainnet Hyperliquid candle collection

**Files:**

- Create: `src/quantmesh/hyperliquid/public_info.py`
- Create: `src/quantmesh/data/hyperliquid_collection.py`
- Modify: `src/quantmesh/settings.py`
- Modify: `src/quantmesh/hyperliquid/market_data.py`
- Test: `tests/test_hyperliquid_public_info.py`
- Test: `tests/test_hyperliquid_collection.py`
- Test: `tests/test_hyperliquid_wallet_isolation.py`

**Interfaces:**

- `PublicInfoTransport` exposes only `candles` and `l2_book` against the pinned
  `https://api.hyperliquid.xyz/info` URL.
- It contains no exchange, signing, account, wallet or order method.
- `HyperliquidCollector.collect_candles(symbols, interval, window)` publishes
  the same four-layer lineage, using `identity-no-corporate-actions-v1`.

- [x] **Step 1: Write failing data-only boundary tests**

```python
def test_public_info_transport_has_no_execution_surface() -> None:
    transport = PublicInfoTransport(client=_client())
    for name in ("exchange", "order", "wallet", "sign", "cancel"):
        assert not hasattr(transport, name)


def test_candle_backfill_is_bounded_by_provider_limit() -> None:
    with pytest.raises(HyperliquidProtocolError, match="5000"):
        _collector().collect_candles(["BTC"], "1m", _window_with_5001_minutes())
```

- [x] **Step 2: Verify RED**

Run the focused files. Expected: `public_info` is absent.

- [x] **Step 3: Implement the HTTP info transport and BTC tracer**

Pin the mainnet data URL in code and settings. Validate response shapes before
writing a raw envelope. Split longer requested periods into bounded windows
only where the official endpoint can still supply them; otherwise mark the
unattainable horizon explicitly.

- [x] **Step 4: Verify GREEN, wallet isolation and optional live smoke**

Run focused tests and an opt-in one-window BTC fetch into a temporary root.
Verify raw bytes, manifest hashes, real provenance and deterministic replay.

- [x] **Step 5: Record Slice 3 checkpoint and review**

Commit `feat(hyperliquid): collect public candle lineage`; receive a clean
read-only review.

---

### Task 8: Hyperliquid microstructure identity and gap evidence

**Files:**

- Modify: `src/quantmesh/live/contract.py`
- Modify: `src/quantmesh/live/hyperliquid.py`
- Modify: `src/quantmesh/live/buffer.py`
- Modify: `src/quantmesh/data/hyperliquid_collection.py`
- Test: `tests/test_live_contract.py`
- Test: `tests/test_live_supervisor.py`
- Test: `tests/test_live_buffer.py`
- Test: `tests/test_hyperliquid_collection.py`

**Interfaces:**

- `ContinuityState` values are `complete`, `known-gap`,
  `unknown-after-disconnect`, `recovered` and `unrecoverable`.
- Hyperliquid trade key is SHA-256 over canonical
  `(block_time, coin, tid)`; `tid` is never incremented or gap-counted.
- Book records are snapshot epochs, not deltas with invented continuity.
- LiveBuffer enforces unique `(venue, instrument, kind, source_event_id,
  content_digest)` and quarantines identity/content conflicts.

- [x] **Step 1: Write the failing nonconsecutive-trade regression**

```python
def test_nonconsecutive_hyperliquid_tids_are_not_a_gap() -> None:
    updates = supervisor.dispatch(_trades(tids=[11, 998877665544]), NOW)
    assert [row.sequence_gap for row in updates] == [False, False]
    assert len({row.source_event_id for row in updates}) == 2


def test_redelivery_after_restart_is_a_noop(tmp_path: Path) -> None:
    first = LiveBuffer(tmp_path).append(_trade(source_event_id="trade-a"))
    reopened = LiveBuffer(tmp_path)
    second = reopened.append(_trade(source_event_id="trade-a"))
    assert second == first
    assert len(reopened.replay()) == 1
```

- [x] **Step 2: Verify RED**

Run the four focused files. Expected: the existing consecutive-ID assertion or
missing source identity fails.

- [x] **Step 3: Correct identity, persistence and disconnect semantics**

Remove `tid > last + 1`. Preserve block time and tid. Record unknown intervals
for disconnect/backpressure. Backfill candles from the durable checkpoint,
replace books with a new snapshot epoch and mark trades unrecoverable where no
official history endpoint exists.

- [x] **Step 4: Verify GREEN and long-outage drill**

Run focused tests including a scripted outage longer than five minutes,
redelivery and identity/content conflict quarantine.

- [x] **Step 5: Record Slice 4 checkpoint and review**

Commit `fix(hyperliquid): use provider-defined trade identity`; receive a clean
review.

---

### Task 9: Durable collection runs, checkpoints and crash recovery

**Files:**

- Create: `src/quantmesh/data/checkpoints.py`
- Create: `src/quantmesh/data/collection.py`
- Modify: `src/quantmesh/data/ingestion.py`
- Test: `tests/test_collection_identity.py`
- Test: `tests/test_collection_checkpoints.py`
- Test: `tests/test_collection_recovery.py`
- Test: `tests/test_ingestion.py`

**Interfaces:**

- `CollectionJob.job_id` hashes provider, endpoint, canonical instrument, kind,
  interval/session, window, adjustment and schema versions.
- `CollectionRun.run_id` is deterministic for the job; `attempt` is monotonic.
- `CheckpointStore.commit(previous, next_checkpoint, advances, commit_id)` is a
  DuckDB graph transaction with compare-and-swap and a one-writer lease.
- `CollectionCoordinator.run(job, ..., crash_after: PublicationStage | None =
  None)` exposes deterministic crash injection only to tests.

- [x] **Step 1: Write failing crash-boundary tests**

```python
@pytest.mark.parametrize("stage", list(PublicationStage))
def test_retry_after_every_crash_boundary_is_idempotent(tmp_path, stage) -> None:
    collector = _collector(tmp_path)
    with pytest.raises(InjectedCrash):
        collector.run(_job(), crash_after=stage)
    recovered = collector.run(_job())
    replayed = collector.replay(recovered.manifest_id)
    assert len({row.source_event_id for row in replayed}) == len(replayed)
    assert collector.checkpoint(_job().job_id).manifest_id == recovered.manifest_id
```

- [x] **Step 2: Verify RED**

Run the three new files. Expected: checkpoint contracts are absent.

- [x] **Step 3: Implement the five-stage publication transaction**

Persist raw, derived objects, manifest and quality report before advancing the
checkpoint/current pointer. If retrying identical data, return the same
manifest. If source identity has changed content, quarantine it and fail the
checkpoint. Refuse a concurrent writer instead of racing.

- [x] **Step 4: Verify GREEN, restart and concurrency**

Run focused tests, eight concurrent attempts and a process reopen. Expected:
one logical publication, stable IDs and no orphaned current pointer.

- [x] **Step 5: Record Slice 5 checkpoint and review**

Commit `feat(data): add idempotent collection checkpoints`; receive a clean
review.

---

### Task 10: Versioned quality SLA and immutable daily evidence

**Files:**

- Create: `src/quantmesh/data/quality.py`
- Modify: `src/quantmesh/data/artifacts.py`
- Modify: `src/quantmesh/data/calendars.py`
- Modify: `src/quantmesh/data/checkpoints.py`
- Modify: `src/quantmesh/data/collection.py`
- Modify: `tests/test_collection_recovery.py`
- Modify: `tests/test_moomoo_collection.py`
- Modify: `tests/test_hyperliquid_collection.py`
- Test: `tests/test_quality_policies.py`
- Test: `tests/test_quality_evidence.py`
- Test: `tests/test_quality_publication.py`
- Test: `tests/test_market_calendars.py`
- Create: `docs/adr/0018-derived-quality-evidence-and-checkpoint-binding.md`

**Interfaces:**

- `QualityStatus`: `pass`, `fail`, `not-due`, `unavailable`.
- `QualityPolicy.policy_id` hashes venue/layer/kind/interval/calendar/thresholds.
- `QualityEvaluation.evaluation_id` hashes policy, manifest, window and exact
  numerators/denominators.
- `QualityEvaluator.evaluate(...)` fails hard integrity rules and represents
  weekends/holidays as `not-due`; measurements are derived from immutable
  manifest, object and raw-envelope evidence.
- `QualityReport` binds every graph member to one exact evaluation and hashes
  the candidate checkpoint projection before the checkpoint records its ID.

- [x] **Step 1: Write failing SLA tests**

```python
def test_real_dataset_rejects_synthetic_parent() -> None:
    with pytest.raises(QualityFailure, match="synthetic"):
        evaluator.evaluate(_real_manifest(parents=[_synthetic_manifest()]))


def test_equity_holiday_is_not_due() -> None:
    result = evaluator.evaluate(_xnys_daily_window("2026-12-25"))
    assert result.status is QualityStatus.NOT_DUE


def test_original_failure_remains_after_amended_pass(store) -> None:
    failed = store.record(_failed_evaluation())
    passed = store.record(_passing_amendment(failed.evaluation_id))
    assert store.load(failed.evaluation_id).status is QualityStatus.FAIL
    assert passed.amends == failed.evaluation_id
```

- [x] **Step 2: Verify RED**

Run the two new files. Expected: quality module absent.

- [x] **Step 3: Implement immutable policy/evaluation objects**

Record expected/observed values, grace periods, entitlement and rights states,
duplicate/gap/hash/schema/overlap checks. Bind every committed real graph to
one exact report and one evaluation per manifest through its checkpoint.

- [x] **Step 4: Verify GREEN and adversarial probes**

Run focused tests for missing page, duplicate source ID, hidden candle gap,
unknown entitlement and synthetic contamination.

- [x] **Step 5: Record and review**

Commit `feat(data): add immutable quality SLA evidence`; receive a clean
review.

---

### Task 11: Catalog API and downstream manifest lineage

**Files:**

- Create: `src/quantmesh/data/catalog.py`
- Create: `src/quantmesh/api/data_catalog.py`
- Modify: `src/quantmesh/api/workstation.py`
- Modify: `src/quantmesh/instruments/contracts.py`
- Modify: `src/quantmesh/instruments/history.py`
- Modify: `src/quantmesh/research/features.py`
- Modify: `src/quantmesh/research/experiments.py`
- Modify: `src/quantmesh/instruments/forecast.py`
- Test: `tests/test_data_catalog.py`
- Test: `tests/test_data_catalog_api.py`
- Test: `tests/test_instrument_history.py`
- Test: `tests/test_research_features.py`
- Test: `tests/test_experiments.py`
- Test: `tests/test_price_forecast.py`

**Interfaces:**

- `CatalogEntry` exposes provider capability, canonical identity, layer,
  current manifest, parents, coverage, quality, rights, entitlement and latest
  checkpoint.
- `GET /api/data/catalog` lists entries; `GET
  /api/data/catalog/{manifest_id}` returns immutable lineage.
- `HistoricalSeries`, `FeatureSpec`, experiment and forecast evidence add
  `manifest_id` and `quality_evaluation_id` while retaining integer revision
  compatibility.

- [x] **Step 1: Write failing fail-closed downstream tests**

```python
def test_history_rejects_failed_quality_manifest() -> None:
    with pytest.raises(HistoryUnavailableError, match="quality"):
        _history_service(_failed_quality_dataset()).history(
            Venue.MOOMOO, "AAPL", HistoryRange.ONE_MONTH
        )


def test_forecast_resolves_exact_manifest_and_quality() -> None:
    artifact = _forecast_from_trusted_history()
    assert artifact.manifest_id == MANIFEST_ID
    assert artifact.quality_evaluation_id == QUALITY_ID
```

- [x] **Step 2: Verify RED**

Run the listed focused files. Expected: new fields/API are absent.

- [x] **Step 3: Implement catalog and compatibility fields**

Allow v1 demo artifacts to remain explicitly legacy. Only v2 manifest IDs with
passing quality may qualify as trusted real data. Do not rewrite historical
research records.

- [x] **Step 4: Generate OpenAPI and verify GREEN**

Run focused tests, generate the OpenAPI client and run the API freshness check.

- [x] **Step 5: Record backend Slice 6 checkpoint and review**

Commit `feat(data): expose trusted lineage catalog`; receive a clean review.

---

### Task 12: Operator data-catalog screen

**Files:**

- Create: `frontend/src/screens/DataCatalog.tsx`
- Create: `frontend/src/screens/DataCatalog.test.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/lib/messages.ts`
- Modify: `frontend/src/lib/nav.ts`
- Test: `tests/test_spa_api.py`
- Test: `tests/test_spa_e2e.py`

**Interfaces:**

- `/app/ops/data` displays provider/access, instrument, layer, coverage,
  manifest, quality, rights, entitlement and checkpoint state.
- Manifest detail expands parent lineage and exact quality checks.
- Empty, unavailable, not-due, failed and stale states remain explicit in
  English and Simplified Chinese.

- [x] **Step 1: Write the failing component test**

```tsx
it('shows failed quality and lineage without presenting data as usable', async () => {
  renderCatalog({ quality: 'fail', manifest_id: MANIFEST_ID })
  expect(await screen.findByText('Failed')).toBeVisible()
  expect(screen.getByText(MANIFEST_ID)).toBeVisible()
  expect(screen.queryByText('Ready for research')).not.toBeInTheDocument()
})
```

- [x] **Step 2: Verify RED**

Run: `npm exec vitest run -- src/screens/DataCatalog.test.tsx`

Expected: screen/module is missing.

- [x] **Step 3: Implement the bounded screen using existing components**

Reuse the workstation's Card, Badge, table, query-state and disclosure
components. Add no new frontend dependency and no unrelated navigation change.

- [x] **Step 4: Verify GREEN, accessibility and responsive behavior**

Run component tests, TypeScript, Oxlint and Playwright at desktop and 390 px.
Verify keyboard expansion and no horizontal page overflow.

- [x] **Step 5: Record frontend Slice 6 checkpoint and review**

Build and commit the packaged frontend as
`feat(frontend): add trusted data catalog`; receive a clean review.

---

### Task 13: Clean-install collector, replay and daily evidence tooling

**Files:**

- Create: `tools/trusted_data.py`
- Create: `tools/trusted_data_soak.py`
- Create: `tests/test_trusted_data_tool.py`
- Create: `tests/test_trusted_data_soak.py`
- Create: `docs/runbooks/trusted-data-operator.md`
- Modify: `pyproject.toml`
- Modify: `tools/release_gate.py`
- Test: `tests/test_release_gate.py`

**Interfaces:**

- `quantmesh-data collect --root PATH --provider ... --window ...` is bounded
  and read-only.
- `quantmesh-data replay --manifest ID` verifies hashes before output.
- `quantmesh-data inspect` prints catalog/quality/checkpoint state.
- `trusted_data_soak.py observe` writes one immutable UTC daily report.
- `trusted_data_soak.py verify --minimum-hours 168 --minimum-xnys-sessions 4`
  rejects fabricated, late, changed-baseline or incomplete evidence.

- [ ] **Step 1: Write failing CLI/evidence tests**

```python
def test_soak_rejects_seven_reports_generated_after_the_fact(tmp_path) -> None:
    _write_backfilled_reports(tmp_path, count=7)
    result = verify_soak(tmp_path, minimum_hours=168, minimum_xnys_sessions=4)
    assert not result.accepted
    assert "continuous observation" in result.reasons


def test_replay_refuses_tampered_object(tmp_path) -> None:
    manifest = _publish(tmp_path)
    _tamper_with_first_object(tmp_path, manifest)
    assert cli(["replay", "--manifest", manifest.manifest_id]) == 1
```

- [ ] **Step 2: Verify RED**

Run the two new test files. Expected: tooling imports/entry point are absent.

- [ ] **Step 3: Implement the CLI, observer and runbook**

Pin each report to code commit, config digest, policy/calendar/schema versions,
manifests, quality evaluations and checkpoints. Require original timestamps and
append-only report IDs. Retain evidence beyond the soak window.

- [ ] **Step 4: Verify GREEN and clean installation**

Create a fresh clone and venv, install `.[dev,research,e2e]`, collect a bounded
real Hyperliquid window, replay it, restart the process and rerun. Run Moomoo
only if the local OpenD probe is available; otherwise verify the exact typed
unavailable state and record that real Moomoo acceptance remains pending.

- [ ] **Step 5: Freeze the soak candidate and review**

Commit `feat(ops): add trusted data acceptance tooling`; run full pre-soak
review and record the exact candidate commit/config digest. No code or policy
change may enter its evidence directory.

---

### Task 14: Seven-day evidence, final verification and milestone PR

**Files:**

- Update: `docs/iterations/0021-trusted-data-fabric.md`
- Update: `docs/goals/ACTIVE.md`
- Update: `docs/roadmap/ROADMAP.md`
- Create: `docs/releases/v0.1.1-trusted-data-acceptance.md`
- Create: `docs/releases/v0.1.1-trusted-data-acceptance.zh-CN.md`

**Interfaces:**

- Consumes the frozen Task 13 candidate and daily evidence only.
- Produces issue #110 completion evidence and one final milestone PR.
- Produces no release tag and no execution-authority change.

- [ ] **Step 1: Run the frozen evidence window**

Observe at least 168 continuous hours, seven UTC crypto reports and at least
four completed XNYS sessions. Include one controlled restart and one controlled
reconnect drill. Any disqualifying failure starts a new window after the defect
is fixed and reviewed.

- [ ] **Step 2: Verify the evidence bundle**

Run:
`.\.venv\Scripts\python.exe tools/trusted_data_soak.py verify --minimum-hours 168 --minimum-xnys-sessions 4`

Expected: exit 0, exact candidate/config match, seven daily reports, no
unexplained critical SLA failure, duplicate, hidden gap or synthetic lineage.

- [ ] **Step 3: Run complete verification**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check src tests tools
Set-Location frontend
npm ci
npm exec vitest run
npm run typecheck
npm run lint
npm run build
Set-Location ..
.\.venv\Scripts\python.exe tools/golden_path.py
.\.venv\Scripts\python.exe tools/release_gate.py
git diff --check
git status --short
```

Expected: all checks pass and the clean-checkout proof reports no mutation.

- [ ] **Step 4: Dispatch final Reviewer and Verifier**

The Reviewer checks specification compliance, architecture, data correctness,
licensing and trading safety over the full branch. The Verifier independently
reruns the clean-install, replay, restart/disconnect and soak-evidence checks.
Resolve every Critical/Important finding before proceeding.

- [ ] **Step 5: Publish one final PR and merge**

Push `0021-trusted-data-fabric`, open one PR linked to issue #110, wait for
protected-branch CI, squash-merge under the standing solo fast-lane authority
and delete the remote branch. Reconcile local main by fast-forward only.

- [ ] **Step 6: Close the iteration without promoting a release**

Update the iteration index, roadmap and active goal with the merged commit,
exact tests and evidence IDs. Close issue #110 with PR/CI/soak links. Confirm
that `v0.1.1-rc1` is unchanged and no final `v0.1.1` tag exists.

---

## Requirements traceability

| Requirement | Tasks |
| --- | --- |
| Capability-aware provider registry | 1 |
| Canonical instruments and calendars | 2 |
| Immutable manifests and old-revision reads | 3 |
| Raw → normalized → adjusted → feature lineage | 4, 6, 7 |
| Moomoo AAPL/NVDA real read-only path | 5, 6 |
| Hyperliquid BTC/ETH/SOL real read-only path | 7, 8 |
| Idempotent collection/backfill/recovery | 9 |
| Quality SLA and immutable evidence | 10 |
| Data catalog and downstream traceability | 11, 12 |
| Clean installation and replay | 13 |
| Seven consecutive days of evidence | 14 |
| No synthetic repair, release promotion, AI, algorithms or live orders | all |

## Plan self-review

- Every design requirement maps to at least one task.
- Every behavior task starts with a specific failing test and RED command.
- v1 compatibility is explicit; v2 is the only trusted-data write path.
- Hyperliquid public data is structurally separate from execution transports.
- Equity adjustment is action/factor-driven and never inferred from a label.
- The seven-day gate is 168 continuous hours, not seven replayed files.
- No placeholder, unspecified implementation step or unowned interface remains.
