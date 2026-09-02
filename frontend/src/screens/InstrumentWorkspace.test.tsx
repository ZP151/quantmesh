import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { ApiError, api, type InstrumentWorkspace } from '@/lib/api'
import { useLiveConnection } from '@/lib/live'
import { PreferencesProvider } from '@/lib/preferences'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      applyDecisionPacketAction: vi.fn(),
      health: vi.fn(),
      instrumentWorkspace: vi.fn(),
      liveState: vi.fn(),
      markets: vi.fn(),
      saveDecisionPacket: vi.fn(),
    },
  }
})

vi.mock('@/lib/live', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/live')>()
  return { ...actual, useLiveConnection: vi.fn(() => 'live') }
})

vi.mock('@/components/charts/InstrumentChart', () => ({
  InstrumentChart: ({ primary }: { primary: InstrumentWorkspace['history'] }) => (
    <div data-testid="instrument-chart">{primary.instrument.symbol} chart</div>
  ),
}))

import { InstrumentWorkspaceScreen } from './InstrumentWorkspace'
import { retainSameInstrument } from './instrument/workspace-query'

const workspace: InstrumentWorkspace = {
  comparison: null,
  decision: {
    draft: {
      as_of: '2026-08-08T12:00:00Z',
      created_at: '2026-08-08T12:00:00Z',
      disposition: 'draft',
      evidence: {
        costs: { fee_bps: 1.5, half_spread_bps: null, slippage_bps: 2.5, spread_status: 'confirmation-quote-required' },
        forecast_artifact_id: null,
        forecast_blockers: ['No promoted artifact for this range.'],
        forecast_eligible: null,
        forecast_limitations: [],
        forecast_metrics: [],
        forecast_paths: [],
        forecast_synthetic: null,
        history_dataset_id: 'demo-history',
        history_dataset_revision: 1,
        history_duplicates: [],
        history_gaps: [],
        history_generated_at: '2026-08-08T12:00:00Z',
        history_limitations: ['Synthetic data'],
        history_source: 'demo-synthetic',
      },
      instrument: {
        currency: 'USD', instrument_type: 'equity', metadata: {}, symbol: 'NVDA', venue: 'moomoo',
      },
      market_state: {
        invalidation: 176,
        key_level_bar_times: ['2026-08-07T20:00:00Z'],
        latest_close: 184,
        observed_drawdown: -0.08,
        observed_volatility: 0.24,
        resistance: 195,
        sma20: 185,
        sma50: 180,
        support: 180,
        trend: 'bullish',
      },
      operator_reason: null,
      packet_id: 'packet-draft-000000000001',
      paper_capability: {
        allowed: false,
        blockers: [{ code: 'forecast-missing', evidence_ref: 'workspace', message: 'No promoted artifact for this range.' }],
      },
      parent_packet_id: null,
      proposal_id: null,
      risk_plan: {
        entry_price: 182,
        proposal_input_only: true,
        reward_per_unit: 18,
        reward_to_risk: 3,
        risk_per_unit: 6,
        stop_price: 176,
        suggested_notional: 1820,
        suggested_quantity: 10,
        target_price: 200,
      },
      scenarios: [
        { confidence: 'qualitative', confidence_reason: 'Not calibrated.', invalidation: 180, kind: 'bull', probability: null, target: 210, thesis: 'Bull thesis', trigger: 'Bull trigger' },
        { confidence: 'qualitative', confidence_reason: 'Not calibrated.', invalidation: 178, kind: 'base', probability: null, target: 200, thesis: 'Base thesis', trigger: 'Base trigger' },
        { confidence: 'qualitative', confidence_reason: 'Not calibrated.', invalidation: 176, kind: 'bear', probability: null, target: 165, thesis: 'Bear thesis', trigger: 'Bear trigger' },
      ],
      selected_range: '6m',
      version: 1,
    },
    latest: null,
  },
  forecast: null,
  forecast_unavailable_reason: 'No promoted artifact for this range.',
  generated_at: '2026-08-08T12:00:00Z',
  history: {
    adjustment: 'unadjusted',
    as_of: '2026-08-08T12:00:00Z',
    bars: [
      {
        adjusted_close: null,
        close: 184,
        high: 185,
        instrument: {
          currency: 'USD',
          instrument_type: 'equity',
          metadata: {},
          symbol: 'NVDA',
          venue: 'moomoo',
        },
        interval: '1d',
        is_live_tail: false,
        live_lineage: null,
        low: 180,
        open: 181,
        timestamp: '2026-08-07T20:00:00Z',
        volume: 1_200_000,
      },
    ],
    calendar: 'XNYS',
    coverage: {
      end: '2026-08-07T20:00:00Z',
      interval: '1d',
      rows: 1,
      start: '2026-08-07T20:00:00Z',
      symbol: 'NVDA',
      venue: 'moomoo',
    },
    coverage_scope: 'historical-only',
    dataset_id: 'demo-history',
    dataset_revision: 1,
    duplicates: [],
    gaps: [],
    generated_at: '2026-08-08T12:00:00Z',
    instrument: {
      currency: 'USD',
      instrument_type: 'equity',
      metadata: {},
      symbol: 'NVDA',
      venue: 'moomoo',
    },
    interval: '1d',
    license: 'demo-synthetic',
    limitations: ['Synthetic data'],
    range: '6m',
    resolution_fallback: null,
    source: 'demo-synthetic',
  },
  instrument: {
    currency: 'USD',
    instrument_type: 'equity',
    metadata: {},
    symbol: 'NVDA',
    venue: 'moomoo',
  },
  live: {
    age_ms: 95_000,
    ask: 184.2,
    bid: 183.8,
    data_time: '2026-08-08T11:58:25Z',
    label: 'stale',
    last: 184,
    provenance: 'demo-synthetic',
    reason: 'Quote age exceeds the paper-action fence.',
    received_at: '2026-08-08T11:58:25Z',
    sequence: 12,
    sequence_gap: false,
    source: 'demo-synthetic',
    status: 'degraded',
  },
  position: null,
  proposal: {
    allowed: false,
    blockers: ['Quote age exceeds the paper-action fence.'],
    proposals: [],
  },
  risk: {
    cash: 100_000,
    equity: 100_000,
    global_kill_switch: false,
    mark_available: true,
    valuation_complete: true,
    valuation_reason: null,
    max_notional: 50_000,
    max_order_quantity: 100,
    max_position_quantity: 1_000,
    starting_cash: 100_000,
    venue_kill_switch: false,
  },
}

const mockedWorkspace = vi.mocked(api.instrumentWorkspace)
const mockedHealth = vi.mocked(api.health)
const mockedLiveState = vi.mocked(api.liveState)
const mockedMarkets = vi.mocked(api.markets)
const mockedLiveConnection = vi.mocked(useLiveConnection)
let publishLiveUpdate: Parameters<typeof useLiveConnection>[0]

function renderWorkspace(path = '/instruments/moomoo/NVDA?range=6m') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PreferencesProvider>
        <MemoryRouter initialEntries={[path]}>
          <main data-testid="app-main">
            <Routes>
              <Route path="/instruments/:venue/:symbol" element={<InstrumentWorkspaceScreen />} />
            </Routes>
          </main>
        </MemoryRouter>
      </PreferencesProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedLiveConnection.mockImplementation((onUpdate) => {
    publishLiveUpdate = onUpdate
    return 'live'
  })
  mockedWorkspace.mockResolvedValue(workspace)
  mockedLiveState.mockResolvedValue({
    generated_at: '2026-08-08T12:00:00Z',
    instruments: {
      'hyperliquid:BTC': {
        instrument: 'BTC',
        kinds: {
          quote: {
            age_ms: 10,
            data_time: '2026-08-08T12:00:00Z',
            kind: 'quote',
            label: 'real',
            payload: { ask: 100.5, bid: 100 },
            provenance: 'real',
            received_at: '2026-08-08T12:00:00Z',
            sequence: 1,
            sequence_gap: false,
          },
        },
        label: 'real',
        venue: 'hyperliquid',
      },
    },
  })
  mockedMarkets.mockResolvedValue({
    instruments: [{ mark: null, symbol: 'BTC', venue: 'hyperliquid' }],
  })
  mockedHealth.mockResolvedValue({
    live_trading: false,
    paper_mode: true,
    project: 'QuantMesh',
    runtime_mode: 'demo',
    status: 'ok',
    version: '0.1.1rc1',
  })
})

describe('InstrumentWorkspaceScreen', () => {
  it('keeps a persisted decision visible when a background refresh returns a fresh draft', async () => {
    const persisted = {
      ...workspace.decision.draft,
      disposition: 'watch' as const,
      operator_reason: 'Wait for entry',
      packet_id: 'packet-watch-persisted-0001',
      parent_packet_id: workspace.decision.draft.packet_id,
      version: 2,
    }
    const first = { ...workspace, decision: { draft: workspace.decision.draft, latest: persisted } }
    const refreshed = {
      ...workspace,
      generated_at: '2026-08-08T12:01:00Z',
      decision: {
        draft: {
          ...workspace.decision.draft,
          as_of: '2026-08-08T12:01:00Z',
          packet_id: 'packet-fresh-background-0001',
        },
        latest: persisted,
      },
    }
    mockedWorkspace.mockResolvedValueOnce(first).mockResolvedValue(refreshed)
    renderWorkspace()

    expect(await screen.findByText('packet-watch-persisted-0001')).toBeInTheDocument()
    expect(screen.getByText('Watching')).toBeInTheDocument()

    await act(async () => publishLiveUpdate({
      data_time: '2026-08-08T12:00:30Z',
      instrument: 'NVDA',
      kind: 'quote',
      payload: { ask: 185, bid: 184 },
      provenance: 'demo-synthetic',
      received_at: '2026-08-08T12:00:30Z',
      sequence: 13,
      venue: 'moomoo',
    }))
    await waitFor(() => expect(mockedWorkspace).toHaveBeenCalledTimes(2))

    expect(screen.getByText('packet-watch-persisted-0001')).toBeInTheDocument()
    expect(screen.queryByText('packet-fresh-background-0001')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'New analysis' })).toBeInTheDocument()
  })

  it('reuses placeholder evidence only for the same venue and symbol', () => {
    expect(retainSameInstrument(
      workspace,
      ['instrument-workspace', 'moomoo', 'NVDA', '6m', []],
      'moomoo',
      'NVDA',
    )).toBe(workspace)
    expect(retainSameInstrument(
      workspace,
      ['instrument-workspace', 'moomoo', 'AAPL', '6m', []],
      'moomoo',
      'NVDA',
    )).toBeUndefined()
  })

  it('loads the venue-aware instrument and renders the workspace hierarchy', async () => {
    renderWorkspace()

    await waitFor(() => expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument())
    expect(mockedWorkspace).toHaveBeenCalledWith('moomoo', 'NVDA', '6m', [])
    expect(mockedLiveConnection).toHaveBeenLastCalledWith(expect.any(Function), false)
    expect(screen.getByTestId('workspace-grid')).toHaveClass('xl:grid-cols-[minmax(0,1fr)_18rem_22rem]')
    expect(screen.getByTestId('instrument-chart')).toHaveTextContent('NVDA chart')
    expect(screen.getByTestId('app-main').querySelector('main')).not.toBeInTheDocument()
    expect(screen.getByText('Historical source').closest('div')).toHaveTextContent('demo-synthetic')
    expect(screen.getByText('Live source').closest('div')).toHaveTextContent('demo-synthetic')
    expect(screen.getByText('Live classification').closest('div')).toHaveTextContent(
      'stale · demo-synthetic',
    )
    expect(screen.getByText('Data time').closest('div')).toHaveTextContent('Aug 8')
    expect(screen.getByText('Received').closest('div')).toHaveTextContent('Aug 8')
    expect(screen.getByText('Age').closest('div')).toHaveTextContent('1 m 35 s')
  })

  it('uses a three-column matching skeleton while the workspace is loading', () => {
    mockedWorkspace.mockReturnValue(new Promise(() => {}))
    renderWorkspace()

    expect(screen.getByLabelText('Loading instrument workspace')).toHaveClass(
      'xl:grid-cols-[minmax(0,1fr)_18rem_22rem]',
    )
  })

  it('explains a missing historical instrument without hiding the route context', async () => {
    mockedWorkspace.mockRejectedValue(new ApiError(404, 'No trusted history for moomoo:UNKNOWN'))
    renderWorkspace('/instruments/moomoo/UNKNOWN')

    await waitFor(() => expect(screen.getByText('History unavailable')).toBeInTheDocument())
    expect(screen.getByText('No trusted history for moomoo:UNKNOWN')).toBeInTheDocument()
    expect(screen.getByText('moomoo / UNKNOWN')).toBeInTheDocument()
  })

  it('keeps the live detail usable when replay history is not ready', async () => {
    mockedHealth.mockResolvedValue({
      live_trading: false,
      paper_mode: true,
      project: 'QuantMesh',
      runtime_mode: 'live',
      status: 'ok',
      version: '0.1.1rc1',
    })
    mockedWorkspace.mockRejectedValue(new ApiError(404, 'live replay continuity is not proven'))

    renderWorkspace('/instruments/hyperliquid/BTC')

    expect(await screen.findByRole('heading', { name: 'BTC' })).toBeInTheDocument()
    expect(screen.getByText('Order book')).toBeInTheDocument()
    expect(screen.getByText('Trade tape')).toBeInTheDocument()
    expect(screen.queryByText('History unavailable')).not.toBeInTheDocument()
  })

  it('keeps stale evidence visible and blocks the paper action', async () => {
    renderWorkspace()

    await waitFor(() => expect(screen.getByText('Stale market evidence')).toBeInTheDocument())
    expect(screen.getByText('Quote age exceeds the paper-action fence.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeDisabled()
  })

  it('refetches history for URL-backed range and comparison controls', async () => {
    const user = userEvent.setup()
    renderWorkspace()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument())

    await user.click(screen.getByRole('button', { name: '1M' }))
    await waitFor(() =>
      expect(mockedWorkspace).toHaveBeenCalledWith('moomoo', 'NVDA', '1m', []),
    )
    await user.type(screen.getByRole('textbox', { name: 'Comparison instrument' }), 'moomoo:AAPL')
    await user.click(screen.getByRole('button', { name: 'Add comparison' }))
    await waitFor(() =>
      expect(mockedWorkspace).toHaveBeenCalledWith('moomoo', 'NVDA', '1m', ['moomoo:AAPL']),
    )
  })

  it('keeps the active range control mounted and focused while its data refetches', async () => {
    let resolveNext!: (value: InstrumentWorkspace) => void
    mockedWorkspace
      .mockResolvedValueOnce(workspace)
      .mockReturnValueOnce(new Promise((resolve) => { resolveNext = resolve }))
    const user = userEvent.setup()
    renderWorkspace()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument())

    const oneMonth = screen.getByRole('button', { name: '1M' })
    await user.click(oneMonth)
    await waitFor(() => expect(mockedWorkspace).toHaveBeenCalledWith('moomoo', 'NVDA', '1m', []))

    expect(screen.queryByLabelText('Loading instrument workspace')).not.toBeInTheDocument()
    expect(screen.getByText(/Updating the selected evidence/)).toBeInTheDocument()
    expect(oneMonth).toHaveFocus()
    expect(oneMonth).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '6M' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument()

    await act(async () => resolveNext({
      ...workspace,
      history: { ...workspace.history, range: '1m' },
    }))
    await waitFor(() => expect(oneMonth).toHaveAttribute('aria-pressed', 'true'))
    expect(screen.queryByText(/Updating the selected evidence/)).not.toBeInTheDocument()
  })

  it('shows the complete history license instead of permanently truncating it', async () => {
    mockedWorkspace.mockResolvedValue({
      ...workspace,
      history: { ...workspace.history, license: 'A complete operator-supplied license notice' },
    })
    renderWorkspace()

    const license = await screen.findByText('A complete operator-supplied license notice')
    expect(license).toHaveAttribute('title', 'A complete operator-supplied license notice')
    expect(license).not.toHaveClass('truncate')
  })

  it('surfaces resolution fallback, history quality findings and a live sequence gap', async () => {
    mockedWorkspace.mockResolvedValue({
      ...workspace,
      history: {
        ...workspace.history,
        duplicates: ['2026-08-06T20:00:00Z'],
        gaps: ['2026-08-05T20:00:00Z'],
        resolution_fallback: 'Requested 1h; serving trusted 1d bars.',
        limitations: ['XNYS holiday gap detection was not run.'],
      },
      comparison: {
        as_of: workspace.generated_at,
        keys: ['moomoo:NVDA', 'moomoo:AAPL'],
        limitations: ['Comparison uses a shared 1d resolution fallback.'],
        points: [],
        range: '6m',
      },
      live: { ...workspace.live, sequence_gap: true },
    })
    renderWorkspace()

    await waitFor(() => expect(screen.getByText(/Requested 1h; serving trusted 1d bars/)).toBeInTheDocument())
    expect(screen.getByText(/Historical gaps: 1/)).toBeInTheDocument()
    expect(screen.getByText(/Historical duplicates: 1/)).toBeInTheDocument()
    expect(screen.getByText('Live sequence gap detected')).toBeInTheDocument()
    expect(screen.getByText(/History limitation: XNYS holiday gap detection was not run/)).toBeInTheDocument()
    expect(screen.getByText(/Comparison limitation: Comparison uses a shared 1d resolution fallback/)).toBeInTheDocument()
  })

  it('refreshes authoritative quote, position and risk truth for matching live updates', async () => {
    mockedWorkspace
      .mockResolvedValueOnce(workspace)
      .mockResolvedValue({
        ...workspace,
        live: {
          ...workspace.live,
          age_ms: 25,
          data_time: '2026-08-08T12:00:01Z',
          last: 190,
          received_at: '2026-08-08T12:00:01Z',
        },
        position: {
          average_cost: 180,
          mark: 190,
          mark_status: {
            provenance: 'real',
            reason: null,
            received_at: '2026-08-08T12:00:01Z',
            status: 'available',
          },
          quantity: 5,
          realized_pnl: 12,
          unrealized_pnl: 50,
        },
        risk: { ...workspace.risk, equity: 100_050 },
      })
    renderWorkspace()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument())

    act(() => publishLiveUpdate({
      data_time: '2026-08-08T12:00:01Z',
      instrument: 'NVDA',
      kind: 'quote',
      payload: { last: 190 },
      provenance: 'real',
      received_at: '2026-08-08T12:00:01Z',
      sequence: 13,
      sequence_gap: false,
      state: 'connected',
      state_note: null,
      venue: 'moomoo',
    }))

    await waitFor(() => expect(screen.getByText('Mark').closest('div')).toHaveTextContent('190'))
    expect(mockedWorkspace).toHaveBeenCalledTimes(2)
    expect(screen.getByText('Account equity').closest('div')).toHaveTextContent('100,050')
    expect(screen.getByText('Unrealized P&L').closest('div')).toHaveTextContent('50')
  })

  it('retains last-known workspace truth when a background refresh fails', async () => {
    mockedWorkspace
      .mockResolvedValueOnce(workspace)
      .mockRejectedValueOnce(new Error('refresh transport offline'))
    renderWorkspace()
    await waitFor(() => expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument())

    act(() => publishLiveUpdate({
      data_time: '2026-08-08T12:00:01Z',
      instrument: 'NVDA',
      kind: 'quote',
      payload: { last: 190 },
      provenance: 'real',
      received_at: '2026-08-08T12:00:01Z',
      sequence: 13,
      sequence_gap: false,
      state: 'connected',
      state_note: null,
      venue: 'moomoo',
    }))

    expect(await screen.findByText('Background refresh failed — showing last known workspace')).toBeInTheDocument()
    expect(screen.getByText('refresh transport offline')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument()
  })
})
