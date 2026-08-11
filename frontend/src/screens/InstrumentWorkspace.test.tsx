import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import { ApiError, api, type InstrumentWorkspace } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: { ...actual.api, instrumentWorkspace: vi.fn() },
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

const workspace: InstrumentWorkspace = {
  comparison: null,
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
    max_notional: 50_000,
    max_order_quantity: 100,
    max_position_quantity: 1_000,
    starting_cash: 100_000,
    venue_kill_switch: false,
  },
}

const mockedWorkspace = vi.mocked(api.instrumentWorkspace)

function renderWorkspace(path = '/instruments/moomoo/NVDA?range=6m') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <PreferencesProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/instruments/:venue/:symbol" element={<InstrumentWorkspaceScreen />} />
          </Routes>
        </MemoryRouter>
      </PreferencesProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mockedWorkspace.mockResolvedValue(workspace)
})

describe('InstrumentWorkspaceScreen', () => {
  it('loads the venue-aware instrument and renders the workspace hierarchy', async () => {
    renderWorkspace()

    await waitFor(() => expect(screen.getByRole('heading', { name: 'NVDA' })).toBeInTheDocument())
    expect(mockedWorkspace).toHaveBeenCalledWith('moomoo', 'NVDA', '6m', [])
    expect(screen.getByTestId('workspace-grid')).toHaveClass('xl:grid-cols-[minmax(0,1fr)_18rem_22rem]')
    expect(screen.getByTestId('instrument-chart')).toHaveTextContent('NVDA chart')
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

  it('keeps stale evidence visible and blocks the paper action', async () => {
    renderWorkspace()

    await waitFor(() => expect(screen.getByText('Stale market evidence')).toBeInTheDocument())
    expect(screen.getAllByText('Quote age exceeds the paper-action fence.')).toHaveLength(2)
    expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeDisabled()
  })
})
