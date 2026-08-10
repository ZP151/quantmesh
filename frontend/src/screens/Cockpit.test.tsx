import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { LiveState, LiveStatus, LiveView, MarketUpdate } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'
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
      kinds: {
        quote: view({ bid: 100, ask: 100.5 }),
        metrics: view(
          { funding_rate: 0.0001, mark_price: 100.2, index_price: 100, open_interest: 4567 },
          { kind: 'metrics', sequence: 2 },
        ),
      },
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
      <PreferencesProvider>
        <MemoryRouter>
          <CockpitScreen />
        </MemoryRouter>
      </PreferencesProvider>
    </QueryClientProvider>,
  )
}

function renderDetail(symbol = 'SOL') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <PreferencesProvider>
        <MemoryRouter initialEntries={[`/cockpit/${symbol}`]}>
          <Routes>
            <Route path="/cockpit/:symbol" element={<CockpitDetailScreen />} />
          </Routes>
        </MemoryRouter>
      </PreferencesProvider>
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

  it('exposes the evidence boundary on every row: event time, received time and sequence', async () => {
    renderScreen()
    await waitFor(() => expect(screen.getByText('BTC')).toBeInTheDocument())
    // Column headers carry the evidence contract.
    expect(screen.getByText('Event')).toBeInTheDocument()
    expect(screen.getByText('Received')).toBeInTheDocument()
    expect(screen.getByText('Seq')).toBeInTheDocument()
    // The views carry data_time/received_at at T0 → the same clock time
    // (rendered in the host timezone, so match the shape, not a literal).
    expect(screen.getAllByText(/\d{2}:\d{2}:\d{2}/).length).toBeGreaterThanOrEqual(4)
    expect(screen.getAllByText('1').length).toBeGreaterThan(0) // BTC quote sequence
  })

  it('marks a sequence gap on the row that carries it', async () => {
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
      sequence_gap: true,
      payload: { bid: 1.2, ask: 1.25 },
      state: null,
      state_note: null,
    })
    await waitFor(() => expect(screen.getByText('HYPE')).toBeInTheDocument())
    expect(screen.getByText(/7 ⚠ gap/)).toBeInTheDocument()
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
  it('renders venue metrics with their evidence boundary', async () => {
    renderDetail('BTC')

    await waitFor(() => expect(screen.getByText('Funding rate')).toBeInTheDocument())
    expect(screen.getByText('Market context')).toBeInTheDocument()
    expect(screen.getByText('0.01%')).toBeInTheDocument()
    expect(screen.getByText('Mark price')).toBeInTheDocument()
    expect(screen.getByText('$100.20')).toBeInTheDocument()
    expect(screen.getByText('Open interest')).toBeInTheDocument()
    expect(screen.getByText('4,567')).toBeInTheDocument()
    expect(screen.getByText('Market evidence')).toBeInTheDocument()
    expect(screen.getByText('Event time')).toBeInTheDocument()
    expect(screen.getByText('Received')).toBeInTheDocument()
    expect(screen.getByText('Sequence')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('hydrates the latest quote and trade from the snapshot before a new frame arrives', async () => {
    renderDetail()

    await waitFor(() => expect(screen.getByText('$30.10')).toBeInTheDocument())
    expect(screen.getAllByText('Stale').length).toBeGreaterThan(0)
    expect(screen.queryByText('Unavailable')).not.toBeInTheDocument()
    expect(screen.getByText(/mid \$30\.10/)).toBeInTheDocument()
    expect(screen.getByText('buy')).toBeInTheDocument()
    expect(screen.queryByText(/Waiting for the first update/)).not.toBeInTheDocument()
  })

  it('renders derived research metrics from venue-provided frames', async () => {
    const closes = Array.from({ length: 20 }, (_, index) => 100 + index * 0.5)
    const candle = view(
      { open: 100, high: 110, low: 99, close: closes[19], volume: 12_345 },
      { kind: 'candle', sequence: 3 },
    )
    const trade = view({ price: 30.1, size: 2, side: 'buy' }, { kind: 'trade', sequence: 4 })
    const l2Bid = view(
      { side: 'bid', levels: [[30.0, 1.0], [29.5, 2.0]] },
      { kind: 'l2_snapshot', sequence: 6 },
    )
    mocked.liveState.mockResolvedValue({
      generated_at: T0,
      instruments: {
        SOL: {
          venue: 'hyperliquid',
          label: 'real',
          kinds: {
            quote: view({ bid: 30, ask: 30.2 }),
            candle,
            trade,
            l2_snapshot: l2Bid,
            metrics: view(
              { funding_rate: 0.0001, mark_price: 100.2, index_price: 100, open_interest: 4567 },
              { kind: 'metrics', sequence: 2 },
            ),
          },
        },
      },
    })
    let push: (update: MarketUpdate) => void = () => {}
    mockedStream.mockImplementation((onUpdate) => {
      push = onUpdate
      return 'live'
    })
    renderDetail()
    await waitFor(() => expect(screen.getByText('Derived metrics')).toBeInTheDocument())
    // A single candle cannot carry a return — the rows appear only once
    // a second candle close arrives on the stream.
    expect(screen.queryByText('1-candle return')).not.toBeInTheDocument()
    push({
      venue: 'hyperliquid',
      instrument: 'SOL',
      kind: 'candle',
      provenance: 'real',
      data_time: T0,
      received_at: T0,
      sequence: 5,
      sequence_gap: false,
      payload: { open: 109, high: 110, low: 108, close: 109.5, volume: 12_345 },
      state: null,
      state_note: null,
    })
    await waitFor(() => expect(screen.getByText('1-candle return')).toBeInTheDocument())
    expect(screen.getByText('Realized vol (per candle)')).toBeInTheDocument()
    expect(screen.getByText('Last trade size')).toBeInTheDocument()
    expect(screen.getByText('Candle volume')).toBeInTheDocument()
    expect(screen.getByText('Mark–index divergence')).toBeInTheDocument()
    expect(screen.getByText('12,345')).toBeInTheDocument()
    // The trade-size value sits in the dd of the "Last trade size" row.
    const tradeSizeRow = screen.getByText('Last trade size').closest('div')
    expect(tradeSizeRow?.querySelector('dd')).toHaveTextContent('2')
    // The book depth chart needs both sides: the bid side seeded, the
    // ask side streamed — until then it stays absent (never a guess).
    expect(screen.queryByRole('img', { name: /Book depth chart/ })).not.toBeInTheDocument()
    push({
      venue: 'hyperliquid',
      instrument: 'SOL',
      kind: 'l2_snapshot',
      provenance: 'real',
      data_time: T0,
      received_at: T0,
      sequence: 8,
      sequence_gap: false,
      payload: { side: 'ask', levels: [[30.2, 0.5], [30.7, 1.5]] },
      state: null,
      state_note: null,
    })
    await waitFor(() =>
      expect(screen.getByRole('img', { name: /Book depth chart/ })).toBeInTheDocument(),
    )
  })
})
