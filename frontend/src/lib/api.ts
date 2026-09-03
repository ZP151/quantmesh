import createClient from 'openapi-fetch'

import type { components, paths } from '@/api/client'

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
  mark: number | null
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
  account: { cash: number; starting_cash: number; equity: number | null; kill_switch: boolean }
  marks: Record<string, number>
  missing_marks: string[]
  valuation_complete?: boolean
  valuation_reason?: string | null
  venues: { venue: string; instruments: { symbol: string; mark: number | null }[] }[]
  watchlist: { symbol: string; mark: number | null }[]
}

export interface Markets {
  instruments: InstrumentMark[]
}

export interface Watchlist {
  entries: { venue: string | null; symbol: string; mark: number | null }[]
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

export interface MarkStatus {
  status: 'available' | 'stale' | 'unavailable'
  provenance: string
  received_at?: string | null
  reason?: string | null
}

export interface Position {
  key: string
  instrument: Instrument
  quantity: number
  average_cost: number
  realized_pnl: number
  unrealized_pnl: number | null
  mark_status?: MarkStatus | null
}

export interface PnL {
  starting_cash: number
  realized_pnl: number
  unrealized_pnl: number | null
  equity: number | null
  total_pnl: number | null
  marks: Record<string, number>
  mark_statuses?: Record<string, MarkStatus>
  missing_marks: string[]
  valuation_complete?: boolean
  valuation_reason?: string | null
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
  retained_resets: { path: string; acknowledged: boolean; exists: boolean }[]
  retained_reset_cleanup: {
    mode: 'manual-only'
    automatic_deletion_supported: false
    instructions: string
  }
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
export type LiveContinuityState =
  | 'complete'
  | 'known-gap'
  | 'unknown-after-disconnect'
  | 'recovered'
  | 'unrecoverable'

export interface LiveContinuityEvidence {
  channel: string
  disconnected_at: string
  last_durable_source_event_id: string | null
  first_recovered_source_event_id: string
  recovered_at: string
  recovery_source: string
}

export interface LiveView {
  kind: LiveKind
  provenance: string
  data_time: string
  received_at: string
  age_ms: number
  sequence: number | null
  sequence_gap: boolean
  continuity?: LiveContinuityState
  source_event_id?: string
  content_digest?: string
  snapshot_epoch?: string | null
  continuity_evidence?: LiveContinuityEvidence | null
  label: LiveLabel
  payload: Record<string, unknown>
}

export interface LiveInstrumentState {
  venue: string
  instrument: string
  label: LiveLabel
  kinds: Record<string, LiveView>
  book_sides?: Partial<Record<'bid' | 'ask', LiveView>>
}

export type LiveInstrumentKey = `${string}:${string}`

export interface LiveState {
  generated_at: string
  instruments: Record<LiveInstrumentKey, LiveInstrumentState>
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
  continuity?: LiveContinuityState
  source_event_id?: string
  content_digest?: string
  snapshot_epoch?: string | null
  continuity_evidence?: LiveContinuityEvidence | null
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

// --- Integrated instrument history (iteration 0020 Task 6) -----------------

type DeepReadonly<T> = T extends (...args: never[]) => unknown
  ? T
  : T extends readonly (infer Item)[]
    ? readonly DeepReadonly<Item>[]
    : T extends object
      ? { readonly [Key in keyof T]: DeepReadonly<T[Key]> }
      : T

export type HistoryRange = components['schemas']['HistoryRange']
export type HistoricalVenue = components['schemas']['Venue']
export type HistoricalInstrument = DeepReadonly<components['schemas']['InstrumentSnapshot']>
export type HistoricalBar = DeepReadonly<components['schemas']['HistoricalBar']>
export type HistoricalCoverage = DeepReadonly<components['schemas']['CoverageSnapshot']>
export type HistoricalSeries = DeepReadonly<components['schemas']['HistoricalSeries']>
export type ComparisonPoint = DeepReadonly<components['schemas']['ComparisonPoint']>
export type ComparisonSeries = DeepReadonly<components['schemas']['ComparisonSeries']>
export type ForecastPath = DeepReadonly<components['schemas']['ForecastPath']>
export type HistoricalPayload = DeepReadonly<components['schemas']['HistoricalPayload']>
type GeneratedInstrumentWorkspace = components['schemas']['InstrumentWorkspace']
type WorkspaceValuation = {
  valuation_complete?: boolean
  valuation_reason?: string | null
}
type WorkspacePositionEvidence = Omit<
  NonNullable<GeneratedInstrumentWorkspace['position']>,
  'mark_status'
> & { mark_status?: MarkStatus | null }
export type InstrumentWorkspace = DeepReadonly<
  Omit<GeneratedInstrumentWorkspace, 'position' | 'risk'> & {
    position?: WorkspacePositionEvidence | null
    risk: GeneratedInstrumentWorkspace['risk'] & WorkspaceValuation
  }
>
export type PaperProposal = DeepReadonly<components['schemas']['PaperProposal']>
export type ProposalConfirmation = DeepReadonly<components['schemas']['ProposalConfirmation']>
export type ProposalCreateInput = components['schemas']['ProposalCreateBody']
export type DecisionPacket = DeepReadonly<components['schemas']['DecisionPacket']>
export type DecisionPacketActionResult = DeepReadonly<
  components['schemas']['DecisionPacketActionResult']
>
export type DecisionPacketSaveInput = components['schemas']['DecisionPacketSaveBody']
export type DecisionPacketActionInput = components['schemas']['DecisionPacketActionBody']
export type PacketCopilotState = DeepReadonly<components['schemas']['PacketCopilotState']>
// Local monitoring is a generated, packet-bound contract.  The browser can
// select only the fixed condition kinds; observations are constructed by the
// local runtime from its workspace and registry snapshots.
export type WatchConditionKind = components['schemas']['WatchConditionKind']
export type DecisionOutcomeReviewState = DeepReadonly<
  components['schemas']['DecisionOutcomeReviewState']
>
export type DecisionOutcomeReviewInput = components['schemas']['DecisionOutcomeReviewBody']

// --- Trusted data catalog (iteration 0021 Slice 6) -----------------------

export type CatalogEntry = DeepReadonly<components['schemas']['CatalogEntry']>
export type CatalogLineage = DeepReadonly<components['schemas']['CatalogLineage']>

// --- Client --------------------------------------------------------------

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export class ProposalRefusalError extends ApiError {
  readonly result: ProposalConfirmation

  constructor(result: ProposalConfirmation) {
    super(409, result.blocker ?? 'Paper proposal confirmation was refused')
    this.name = 'ProposalRefusalError'
    this.result = result
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

const generatedApi = createClient<paths>()

function generatedApiError(response: Response, error: unknown): ApiError {
  let detail = `${response.status} ${response.statusText}`
  if (
    typeof error === 'object'
    && error !== null
    && 'detail' in error
    && typeof error.detail === 'string'
  ) {
    detail = error.detail
  }
  return new ApiError(response.status, detail)
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

  async dataCatalog(): Promise<readonly CatalogEntry[]> {
    const { data, error, response } = await generatedApi.GET('/api/data/catalog')
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

  async dataCatalogLineage(manifestId: string): Promise<CatalogLineage> {
    const { data, error, response } = await generatedApi.GET('/api/data/catalog/{manifest_id}', {
      params: { path: { manifest_id: manifestId } },
    })
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

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

  async history(
    venue: HistoricalVenue,
    symbol: string,
    range: HistoryRange,
    compare: readonly string[] = [],
  ): Promise<HistoricalPayload> {
    const { data, error, response } = await generatedApi.GET(
      '/api/instruments/{venue}/{symbol}/history',
      {
        params: {
          path: { venue, symbol },
          query: {
            range,
            compare: compare.length > 0 ? [...compare] : undefined,
          },
        },
      },
    )
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

  async instrumentWorkspace(
    venue: HistoricalVenue,
    symbol: string,
    range: HistoryRange,
    compare: readonly string[] = [],
  ): Promise<InstrumentWorkspace> {
    const { data, error, response } = await generatedApi.GET(
      '/api/instruments/{venue}/{symbol}/workspace',
      {
        params: {
          path: { venue, symbol },
          query: {
            range,
            compare: compare.length > 0 ? [...compare] : undefined,
          },
        },
      },
    )
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

  async saveDecisionPacket(input: DecisionPacketSaveInput): Promise<DecisionPacket> {
    const { data, error, response } = await generatedApi.POST('/api/decision-packets', {
      body: input,
    })
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

  async decisionPacket(packetId: string): Promise<DecisionPacket> {
    const { data, error, response } = await generatedApi.GET(
      '/api/decision-packets/{packet_id}',
      { params: { path: { packet_id: packetId } } },
    )
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

  async applyDecisionPacketAction(
    packetId: string,
    input: DecisionPacketActionInput,
  ): Promise<DecisionPacketActionResult> {
    const { data, error, response } = await generatedApi.POST(
      '/api/decision-packets/{packet_id}/actions',
      {
        params: { path: { packet_id: packetId } },
        body: input,
      },
    )
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

  async packetCopilot(packetId: string): Promise<PacketCopilotState> {
    const { data, error, response } = await generatedApi.GET(
      '/api/decision-packets/{packet_id}/copilot',
      { params: { path: { packet_id: packetId } } },
    )
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

  async requestPacketCopilot(packetId: string): Promise<PacketCopilotState> {
    const { data, error, response } = await generatedApi.POST(
      '/api/decision-packets/{packet_id}/copilot',
      { params: { path: { packet_id: packetId } } },
    )
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

  async packetMonitoring(packetId: string): Promise<components['schemas']['DecisionWatchState']> {
    const { data, error, response } = await generatedApi.GET(
      '/api/decision-packets/{packet_id}/watch-conditions',
      { params: { path: { packet_id: packetId } } },
    )
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

  async checkPacketMonitoring(
    packetId: string,
    kinds: readonly WatchConditionKind[],
  ): Promise<components['schemas']['DecisionWatchState']> {
    const { data, error, response } = await generatedApi.POST(
      '/api/decision-packets/{packet_id}/watch-conditions',
      {
        body: { kinds: [...kinds] },
        params: { path: { packet_id: packetId } },
      },
    )
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

  async packetOutcomeReview(packetId: string): Promise<DecisionOutcomeReviewState> {
    const { data, error, response } = await generatedApi.GET(
      '/api/decision-packets/{packet_id}/outcome-review',
      { params: { path: { packet_id: packetId } } },
    )
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

  async savePacketOutcomeReview(
    packetId: string,
    input: DecisionOutcomeReviewInput,
  ): Promise<DecisionOutcomeReviewState> {
    const { data, error, response } = await generatedApi.POST(
      '/api/decision-packets/{packet_id}/outcome-review',
      {
        body: input,
        params: { path: { packet_id: packetId } },
      },
    )
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

  async createPaperProposal(input: ProposalCreateInput): Promise<PaperProposal> {
    const { data, error, response } = await generatedApi.POST('/api/paper/proposals', {
      body: input,
    })
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

  async confirmPaperProposal(
    proposalId: string,
    confirmationToken: string,
  ): Promise<ProposalConfirmation> {
    const { data, error, response } = await generatedApi.POST(
      '/api/paper/proposals/{proposal_id}/confirm',
      {
        params: { path: { proposal_id: proposalId } },
        body: { confirmation_token: confirmationToken },
      },
    )
    if (response.status === 409 && error !== undefined) {
      throw new ProposalRefusalError(error as ProposalConfirmation)
    }
    if (!response.ok || data === undefined) throw generatedApiError(response, error)
    return data
  },

  // Slice 4 — the recorded replay surface over the local lake.
  replayExtent: () => request<ReplayExtent>('/api/live/replay/windows'),
  priceTrail: (params: { identities: string; limit?: number }) =>
    request<{ trail: Record<LiveInstrumentKey, number[]> }>(
      `/api/live/price-trail?identities=${encodeURIComponent(params.identities)}&limit=${params.limit ?? 20}`,
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
