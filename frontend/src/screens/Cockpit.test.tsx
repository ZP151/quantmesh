import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { LiveState, LiveStatus, LiveView, MarketUpdate } from '@/lib/api'
import { CockpitScreen } from './Cockpit'
import { CockpitDetailScreen } from './CockpitDetail'

// The watchlist renders against the snapshot endpoints and the stream
// hook. The api client is mocked for the two snapshot queries; the
// stream hook is mocked so the tests push deterministic updates — the
// hook's own fallback ladder is drilled separately in lib/live.test.ts.
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      liveState: vi.fn(),
      liveStatus: vi.fn(),
    },
  }
})

vi.mock('@/lib/live', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/live')>()
  return {
    ...actual,
    useLiveConnection: vi.fn(),
  }
})

import { api } from '@/lib/api'
import { useLiveConnection } from '@/lib/live'

const mocked = vi.mocked(api)
const mockedStream = vi.mocked(useLiveConnection)

const T0 = '2026-08-09T10:00:00+00:00'

function view(payload: Record<string, unknown>, overrides: Partial<LiveView> = {}): LiveView {
  return {
    kind: 'quote',
    provenance: 'real',
    data_time: T0,
    received_at: T0,
    age_ms: 500,
    sequence: 1,
    sequence_gap: false,
    label: 'real',
    payload,
    ...overrides,
  }
}

const STATE: LiveState = {
  generated_at: T0,
  instruments: {
    BTC: {
      venue: 'hyperliquid',
      label: 'real',
      kinds: { quote: view({ bid: 100, ask: 100.5 }) },
    },
    SOL: {
      venue: 'hyperliquid',
      label: 'stale',
      kinds: {
        quote: view({ bid: 30, ask: 30.2 }, { label: 'stale', age_ms: 95_000 }),
        trade: view({ price: 30.1, size: 2, side: 'buy' }, { kind: 'trade', label: 'stale', age_ms: 95_000 }),
      },
    },
  },
}

const STATUS: LiveStatus = {
  generated_at: T0,
  venues: [
    {
      venue: 'hyperliquid',
      connected: true,
      sources: [
        { instrument: 'BTC', state: 'connected', note: null, data_time: T0, received_at: T0, age_ms: 500 },
        { instrument: 'SOL', state: 'stale', note: null, data_time: T0, received_at: T0, age_ms: 95_000 },
        { instrument: 'HYPE', state: 'unavailable', note: null, data_time: null, received_at: null, age_ms: null },
      ],
    },
  ],
}

function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CockpitScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function renderDetail(symbol = 'SOL') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[`/cockpit/${symbol}`]}>
        <Routes>
          <Route path="/cockpit/:symbol" element={<CockpitDetailScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mocked.liveState.mockResolvedValue(STATE)
  mocked.liveStatus.mockResolvedValue(STATUS)
  mockedStream.mockReturnValue('live')
})

describe('CockpitScreen', () => {
  it('renders the watchlist with per-instrument labels', async () => {
    renderScreen()
    await waitFor(() => expect(screen.getByText('BTC')).toBeInTheDocument())
    expect(screen.getByText('Real')).toBeInTheDocument()
    expect(screen.getByText('Stale')).toBeInTheDocument()
    // SOL appears twice: the watchlist row and the connector panel chip.
    expect(screen.getAllByText('SOL').length).toBeGreaterThan(0)
  })

  it('shows quote numbers and spread bps', async () => {
    renderScreen()
    await waitFor(() => expect(screen.getByText('BTC')).toBeInTheDocument())
    expect(screen.getByText('$100.00')).toBeInTheDocument()
    expect(screen.getByText('$100.50')).toBeInTheDocument()
    expect(screen.getByText('49.9')).toBeInTheDocument()
  })

  it('links every symbol to its detail screen', async () => {
    renderScreen()
    await waitFor(() => expect(screen.getByText('BTC')).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'BTC' })).toHaveAttribute('href', '/cockpit/BTC')
    expect(screen.getByRole('link', { name: 'SOL' })).toHaveAttribute('href', '/cockpit/SOL')
  })

  it('renders the connector health panel with source states', async () => {
    renderScreen()
    await waitFor(() => expect(screen.getByText('Connector health')).toBeInTheDocument())
    // "connected" appears twice: the venue badge and the BTC source chip.
    expect(screen.getAllByText('connected', { exact: true }).length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('unavailable')).toBeInTheDocument()
    expect(screen.getByText('HYPE')).toBeInTheDocument()
  })

  it('merges streamed updates into the snapshot and shows the banner', async () => {
    let push: (update: MarketUpdate) => void = () => {}
    mockedStream.mockImplementation((onUpdate) => {
      push = onUpdate
      return 'live'
    })
    renderScreen()
    await waitFor(() => expect(screen.getByText('BTC')).toBeInTheDocument())
    push({
      venue: 'hyperliquid',
      instrument: 'HYPE',
      kind: 'quote',
      provenance: 'real',
      data_time: T0,
      received_at: T0,
      sequence: 7,
      sequence_gap: false,
      payload: { bid: 1.2, ask: 1.25 },
      state: null,
      state_note: null,
    })
    await waitFor(() => expect(screen.getByText('HYPE')).toBeInTheDocument())
    expect(screen.getByText(/Local stream connected over WebSocket/)).toBeInTheDocument()
  })

  it('shows the fallback banner when the stream is on SSE', async () => {
    mockedStream.mockReturnValue('fallback')
    renderScreen()
    await waitFor(() => expect(screen.getByText(/SSE fallback/)).toBeInTheDocument())
  })

  it('explains when no live feed is attached', async () => {
    mocked.liveState.mockRejectedValue(new Error('404: no live feed is attached'))
    renderScreen()
    await waitFor(() =>
      expect(screen.getByText(/no live feed is attached/)).toBeInTheDocument(),
    )
    expect(screen.getByText(/start the workstation with --live/)).toBeInTheDocument()
  })
})

describe('CockpitDetailScreen', () => {
  it('hydrates the latest quote and trade from the snapshot before a new frame arrives', async () => {
    renderDetail()

    await waitFor(() => expect(screen.getByText('$30.10')).toBeInTheDocument())
    expect(screen.getByText('Stale')).toBeInTheDocument()
    expect(screen.queryByText('Unavailable')).not.toBeInTheDocument()
    expect(screen.getByText(/mid \$30\.10/)).toBeInTheDocument()
    expect(screen.getByText('buy')).toBeInTheDocument()
    expect(screen.queryByText(/Waiting for the first update/)).not.toBeInTheDocument()
  })
})
