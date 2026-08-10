// The JSON surface contract (iteration 0014 Phase C, ADR-0013).
// One route per screen; every route renders through the exact page
// providers the RC1 templates use (src/quantmesh/api/workstation.py),
// so the browser and the legacy screens can never disagree. The types
// mirror the wire shape captured from a live demo runtime — nothing
// here is inferred from a mock.

export type InstrumentType = 'equity' | 'perpetual' | 'prediction'

export interface Instrument {
  symbol: string
  venue: string
  instrument_type: InstrumentType
  currency: string
  metadata: Record<string, unknown>
}

export interface InstrumentMark {
  venue: string
  symbol: string
  mark: number
}

export interface AccountSummary {
  cash: number
  starting_cash: number
  total_fees: number
  kill_switch: boolean
  order_sequence: number
}

export type OrderSide = 'buy' | 'sell'
export type OrderType = 'market' | 'limit'
export type OrderStatus = 'pending' | 'accepted' | 'filled' | 'rejected' | 'cancelled'

export interface OrderEvent {
  sequence: number
  timestamp: string
  event_type: string
  status: OrderStatus
  quantity: number | null
  price: number | null
  reason: string | null
}

export interface OrderSummary {
  order_id: string
  client_order_id: string | null
  instrument: Instrument
  side: OrderSide
  quantity: number
  order_type: OrderType
  limit_price: number | null
  status: OrderStatus
  filled_quantity: number
  average_fill_price: number | null
  created_at: string
  events: OrderEvent[]
}

// --- Per-surface payloads (the page providers, verbatim) ----------------

export interface Overview {
  account: { cash: number; starting_cash: number; equity: number; kill_switch: boolean }
  marks: Record<string, number>
  missing_marks: string[]
  venues: { venue: string; instruments: { symbol: string; mark: number }[] }[]
  watchlist: { symbol: string; mark: number }[]
}

export interface Markets {
  instruments: InstrumentMark[]
}

export interface Watchlist {
  entries: { symbol: string; mark: number }[]
}

export interface Experiment {
  id: string
  dataset: string
  revision: number
  commit: string
  created_at: string
  parameters: Record<string, string>
  metrics: Record<string, string>
}

export interface Experiments {
  experiments: Experiment[]
  registry_bound: boolean
}

export interface EvaluationRow {
  id: string
  resolved: boolean
  strategy: string
  dataset: string
  revision: number
  interval: string
  metrics: Record<string, string>
  windows_oos: boolean
}

export interface Promotion {
  id: string
  signal_name: string
  promoted_at: string
  kill_switch: boolean
  benchmarks: EvaluationRow[]
  ablations: EvaluationRow[]
  oos: EvaluationRow
}

export interface Promotions {
  promotions: Promotion[]
  registry_bound: boolean
}

export interface ForecastWindow {
  index: number
  train_end: string
  test_start: string
  test_end: string
  brier: number | null
  liquidity_weighted_brier: number | null
  n_observations: number
  n_resolved: number
  calibration_bins: unknown[]
}

export interface ForecastMarket {
  market_id: string
  title: string
  event_ticker: string
  venue: string
  venue_market_id: string
  expiry_at: string
  resolved: boolean
  latest_probability: number | null
  latest_probability_at: string | null
  latest_liquidity_confidence: number | null
  n_evaluated_windows: number
  windows: ForecastWindow[]
}

export interface ForecastReport {
  id: string
  commit: string
  created_at: string
  window_spec: { train: number; test: number; step: number }
  n_bins: number
  metrics: Record<string, string>
  markets: ForecastMarket[]
  artifacts_present: boolean
  artifacts: Record<string, boolean>
}

export interface Forecasts {
  reports: ForecastReport[]
  registry_bound: boolean
}

export interface RiskAlert {
  id: string
  kind: string
  source: string
  detected_at: string
  message: string
  observed: Record<string, string>
}

export interface Risk {
  paper_limits: {
    kill_switch: boolean
    max_order_quantity: number | null
    max_notional: number | null
    max_position_quantity: number | null
  }
  hl_posture: unknown
  alerts: RiskAlert[]
  alerts_bound: boolean
}

export interface AuditEntry {
  kind: 'order' | 'mapping' | 'decision'
  at: string
  anchor: string
  order?: OrderSummary
  mapping?: Record<string, unknown>
  decision?: Record<string, unknown>
}

export interface Audit {
  entries: AuditEntry[]
  journal_bound: boolean
  mappings_bound: boolean
  decisions_bound: boolean
}

export interface Enablement {
  states: { venue: string; state: string }[]
  bound: boolean
  gate_text: string
}

export interface KillSwitch {
  kill_switch: boolean
  kill_switches: Record<string, boolean>
}

export interface Position {
  key: string
  instrument: Instrument
  quantity: number
  average_cost: number
  realized_pnl: number
  unrealized_pnl: number | null
}

export interface PnL {
  starting_cash: number
  realized_pnl: number
  unrealized_pnl: number
  equity: number
  total_pnl: number
  marks: Record<string, number>
  missing_marks: string[]
}

export interface Health {
  status: string
  project: string
  version: string
  paper_mode: boolean
  live_trading: boolean
  runtime_mode: 'demo' | 'live' | 'operator'
}

export interface DemoSurfaceRow {
  source: string
  synthetic: boolean
  updated_at: string
  rows: number
}

export interface DemoStatus {
  mode: 'demo'
  root: string
  marker: string
  source: 'demo'
  synthetic: true
  scenario: { seed: number; anchor: string; open: string; commit: string }
  surfaces: Record<string, DemoSurfaceRow>
  last_update: string
  health: { status: string; seed: number }
}

export interface DemoOrderResult {
  order: OrderSummary
  account: { cash: number; equity: number }
}

// --- Phase D: connectors, public data and imports -----------------------

export interface ConnectorState {
  venue: string
  kind: 'fixture' | 'public-data' | 'execution-sim' | 'unwired'
  mode: string
  credentials_required: boolean
  read_only: boolean
  wired: boolean
  state: 'ok' | 'degraded' | 'unavailable' | 'unwired' | 'unprobed'
  detail: string
  last_checked_at: string | null
  latency_ms: number | null
}

export interface FetchRow {
  symbol: string
  coin: string
  source: 'hyperliquid-public' | 'fixture-fallback'
  synthetic: boolean
  fallback_of?: string
  degraded?: 'missing-software' | 'network' | 'rate-limited'
  best_bid: number | null
  best_ask: number | null
  levels: number
  fetched_at: string
  cache: string | null
  reason: string | null
}

export interface FetchReport {
  venue: 'hyperliquid'
  read_only: boolean
  synthetic: boolean
  rows: FetchRow[]
  cached_entries: { coin: string; symbol: string; source: string; synthetic: boolean; fetched_at: string; cache: string }[]
  fetched_at: string
}

export interface ImportColumn {
  name: string
  inferred: string
  samples: (string | number | boolean | null)[]
}

export interface ImportPreview {
  session_id: string
  filename: string
  format: string
  rows: number
  columns: ImportColumn[]
  preview: Record<string, string | number | boolean | null>[]
  suggested_mapping: Record<string, string>
}

export interface ImportCommitResult {
  dataset: string
  source: string
  license: string
  revision: number
  generated_at: string
  accepted: number
  rejected: number
  rejections: { row: number; reason: string }[]
  coverage: {
    interval: string
    venue: string
    symbol: string
    rows: number
    start: string
    end: string
  }[]
}

export interface ImportedDataset {
  dataset: string
  source: string
  license: string
  revision: number
  generated_at: string
  series: number
  rows: number
  start: string | null
  end: string | null
}

// --- Phase C (iteration 0015): the live feed surface ----------------------

export type LiveLabel = 'real' | 'delayed' | 'stale' | 'synthetic' | 'unavailable'
export type LiveKind =
  | 'quote'
  | 'trade'
  | 'candle'
  | 'l2_snapshot'
  | 'l2_delta'
  | 'metrics'
  | 'status'
export type LiveSourceState =
  | 'connected'
  | 'lagging'
  | 'stale'
  | 'disconnected'
  | 'unavailable'

export interface LiveView {
  kind: LiveKind
  provenance: string
  data_time: string
  received_at: string
  age_ms: number
  sequence: number | null
  sequence_gap: boolean
  label: LiveLabel
  payload: Record<string, unknown>
}

export interface LiveInstrumentState {
  venue: string
  label: LiveLabel
  kinds: Record<string, LiveView>
}

export interface LiveState {
  generated_at: string
  instruments: Record<string, LiveInstrumentState>
}

export interface LiveSource {
  instrument: string
  state: LiveSourceState
  note: string | null
  data_time: string | null
  received_at: string | null
  age_ms: number | null
}

export interface LiveVenueStatus {
  venue: string
  connected: boolean
  sources: LiveSource[]
}

export interface LiveStatus {
  generated_at: string
  venues: LiveVenueStatus[]
}

// --- Phase E (iteration 0015): the prediction comparison surface --------

/** One venue row on the prediction comparison board. The probability is
 * the venue's own implied mid in percent, or null while no real quote
 * has arrived — an unconfigured or quiet venue renders "—", never a
 * fabricated number. */
export interface PredictionVenueRow {
  venue: string
  symbol: string | null
  label: LiveLabel
  probability: number | null
  bid: number | null
  ask: number | null
  spread_bps: number | null
  depth: number | null
  liquidity: number | null
}

/** One event pair across the prediction venues, with the cross-venue
 * probability difference in percentage points (null unless both venues
 * carry a probability). */
export interface PredictionRow {
  event_key: string
  title: string
  expiry: string | null
  venues: PredictionVenueRow[]
  diff: number | null
}

/** One normalized update pushed on the stream (WS or SSE fallback). */
export interface MarketUpdate {
  venue: string
  instrument: string
  kind: LiveKind
  provenance: string
  data_time: string
  received_at: string
  sequence: number | null
  sequence_gap: boolean
  payload: Record<string, unknown>
  state: LiveSourceState | null
  state_note: string | null
}

// --- Replay surface (iteration 0019 slice 4) -------------------------------

/** The recorded extent of the local replay lake. */
export interface ReplayExtent {
  source: 'lake'
  count: number
  earliest: string | null
  latest: string | null
  venues: string[]
}

/** One replayed window from the lake, with its own provenance boundary. */
export interface ReplayWindow {
  source: 'lake'
  window: {
    start: string | null
    end: string | null
    count: number
  }
  updates: MarketUpdate[]
}

// --- Client --------------------------------------------------------------

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let detail = `${response.status} ${response.statusText}`
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') detail = body.detail
  } catch {
    // Non-JSON error body; keep the status text.
  }
  return new ApiError(response.status, detail)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) throw await parseError(response)
  return (await response.json()) as T
}

export interface DemoOrderInput {
  venue: string
  symbol: string
  side: 'BUY' | 'SELL'
  quantity: number
  limit_price?: number
  idempotency_key?: string
}

export const api = {
  health: () => request<Health>('/api/health'),
  account: () => request<AccountSummary>('/api/account'),
  positions: () => request<Position[]>('/api/positions'),
  orders: () => request<OrderSummary[]>('/api/orders'),
  pnl: () => request<PnL>('/api/pnl'),
  overview: () => request<Overview>('/api/overview'),
  markets: () => request<Markets>('/api/markets'),
  watchlist: () => request<Watchlist>('/api/watchlist'),
  experiments: () => request<Experiments>('/api/experiments'),
  promotions: () => request<Promotions>('/api/promotions'),
  forecasts: () => request<Forecasts>('/api/forecasts'),
  risk: () => request<Risk>('/api/risk'),
  audit: () => request<Audit>('/api/audit'),
  enablement: () => request<Enablement>('/api/enablement'),
  killSwitch: () => request<KillSwitch>('/api/kill-switch'),
  demoStatus: () => request<DemoStatus>('/api/demo/status'),

  // Writes — every one is gated by the kernel (origin guard, kill
  // switch, risk limits); the browser only calls what the UI shows.
  async engageKillSwitch(venue?: string): Promise<KillSwitch> {
    return request('/api/kill-switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'engage', venue: venue ?? null }),
    })
  },
  async disarmKillSwitch(venue?: string): Promise<KillSwitch> {
    return request('/api/kill-switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'disarm', venue: venue ?? null }),
    })
  },
  async demoOrder(input: DemoOrderInput): Promise<DemoOrderResult> {
    return request('/api/demo/order', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    })
  },
  async demoReset(): Promise<DemoStatus> {
    return request('/api/demo/reset', { method: 'POST' })
  },

  // Phase D — connector panel, public data, imports (all read-only
  // against the seeded tree; fetches land in the .datalink cache).
  connectors: () => request<ConnectorState[]>('/api/demo/connectors'),
  probeConnectors: () =>
    request<ConnectorState[]>('/api/demo/connectors/probe', { method: 'POST' }),
  datalinkFetch: (symbols: string[]) =>
    request<FetchReport>('/api/demo/datalink/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ symbols }),
    }),
  datalinkCache: () => request<FetchReport['cached_entries']>('/api/demo/datalink/cache'),
  importUpload: (file: File) =>
    request<ImportPreview>('/api/demo/import', {
      method: 'POST',
      // No Content-Type: the browser sets the multipart boundary.
      body: (() => {
        const form = new FormData()
        form.append('file', file)
        return form
      })(),
    }),
  importCommit: (body: {
    session_id: string
    dataset: string
    interval: string
    venue: string
    symbol: string
    instrument_type?: string
    license?: string
    mapping: Record<string, string>
  }): Promise<ImportCommitResult> =>
    request('/api/demo/import/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  imports: () => request<ImportedDataset[]>('/api/demo/imports'),

  // Phase C — the live feed surface (WS/SSE stream + snapshots).
  liveState: () => request<LiveState>('/api/live/state'),
  liveStatus: () => request<LiveStatus>('/api/live/status'),
  prediction: () => request<PredictionRow[]>('/api/live/prediction'),

  // Slice 4 — the recorded replay surface over the local lake.
  replayExtent: () => request<ReplayExtent>('/api/live/replay/windows'),
  priceTrail: (params: { symbols: string; limit?: number }) =>
    request<{ trail: Record<string, number[]> }>(
      `/api/live/price-trail?symbols=${encodeURIComponent(params.symbols)}&limit=${params.limit ?? 20}`,
    ),
  replayWindow: (params: { start?: string; end?: string; limit?: number }) =>
    request<ReplayWindow>(
      `/api/live/replay?${new URLSearchParams(
        Object.fromEntries(
          Object.entries({ start: params.start ?? '', end: params.end ?? '', limit: String(params.limit ?? 5000) }).filter(
            ([, value]) => value !== '',
          ),
        ),
      )}`,
    ),
}
