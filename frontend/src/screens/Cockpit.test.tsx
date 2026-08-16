import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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
      markets: vi.fn(),
      replayExtent: vi.fn(),
      replayWindow: vi.fn(),
      priceTrail: vi.fn(),
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
import {
  latestCompleteBookSides,
  reconcileInstrumentState,
  reconcileUpdates,
  useLiveConnection,
} from '@/lib/live'

const mocked = vi.mocked(api)
const mockedStream = vi.mocked(useLiveConnection)

const T0 = '2026-08-09T10:00:00+00:00'

function marketUpdate(
  kind: MarketUpdate['kind'],
  source_event_id: string,
  received_at: string,
  payload: Record<string, unknown>,
  snapshot_epoch?: string,
): MarketUpdate {
  return {
    venue: 'hyperliquid',
    instrument: 'BTC',
    kind,
    provenance: 'real',
    data_time: received_at,
    received_at,
    sequence: null,
    sequence_gap: false,
    source_event_id,
    snapshot_epoch,
    payload,
    state: null,
    state_note: null,
  }
}

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
    'hyperliquid:BTC': {
      venue: 'hyperliquid',
      instrument: 'BTC',
      label: 'real',
      kinds: {
        quote: view({ bid: 100, ask: 100.5 }),
        metrics: view(
          { funding_rate: 0.0001, mark_price: 100.2, index_price: 100, open_interest: 4567 },
          { kind: 'metrics', sequence: 2 },
        ),
      },
    },
    'hyperliquid:SOL': {
      venue: 'hyperliquid',
      instrument: 'SOL',
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

function renderDetail(symbol = 'SOL', venue = 'hyperliquid') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <PreferencesProvider>
        <MemoryRouter initialEntries={[`/cockpit/${venue}/${symbol}`]}>
          <Routes>
            <Route path="/cockpit/:venue/:symbol" element={<CockpitDetailScreen />} />
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
  mocked.markets.mockResolvedValue({
    instruments: [
      { venue: 'hyperliquid', symbol: 'BTC', mark: 100.2 },
      { venue: 'hyperliquid', symbol: 'SOL', mark: 30.1 },
    ],
  })
  mocked.replayExtent.mockRejectedValue(new Error('no replay lake attached'))
  mocked.priceTrail.mockResolvedValue({ trail: {} })
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

  it('links every symbol directly to its unified instrument workspace', async () => {
    renderScreen()
    await waitFor(() => expect(screen.getByText('BTC')).toBeInTheDocument())
    expect(screen.getByRole('link', { name: 'BTC' })).toHaveAttribute('href', '/instruments/hyperliquid/BTC')
    expect(screen.getByRole('link', { name: 'SOL' })).toHaveAttribute('href', '/instruments/hyperliquid/SOL')
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
    act(() => push({
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
    }))
    await waitFor(() => expect(screen.getByRole('link', { name: 'HYPE' })).toBeInTheDocument())
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
    act(() => push({
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
    }))
    await waitFor(() => expect(screen.getByRole('link', { name: 'HYPE' })).toBeInTheDocument())
    expect(screen.getByText(/Local stream connected over WebSocket/)).toBeInTheDocument()
  })

  it('keeps same-symbol quotes isolated by venue', async () => {
    let push: (update: MarketUpdate) => void = () => {}
    mockedStream.mockImplementation((onUpdate) => {
      push = onUpdate
      return 'live'
    })
    renderScreen()
    await waitFor(() => expect(screen.getByRole('link', { name: 'BTC' })).toBeInTheDocument())

    act(() => {
      push({
        venue: 'moomoo',
        instrument: 'BTC',
        kind: 'quote',
        provenance: 'real',
        data_time: T0,
        received_at: T0,
        sequence: 8,
        sequence_gap: false,
        payload: { bid: 200, ask: 201 },
        state: null,
        state_note: null,
      })
    })

    await waitFor(() => expect(screen.getAllByRole('link', { name: 'BTC' })).toHaveLength(2))
    const links = screen.getAllByRole('link', { name: 'BTC' })
    const hyperliquidLink = links.find(
      (link) => link.getAttribute('href') === '/instruments/hyperliquid/BTC',
    )
    const moomooLink = links.find(
      (link) => link.getAttribute('href') === '/instruments/moomoo/BTC',
    )
    expect(hyperliquidLink).toBeDefined()
    expect(moomooLink).toBeDefined()
    expect(hyperliquidLink.closest('tr')).toHaveTextContent('$100.00')
    expect(hyperliquidLink.closest('tr')).not.toHaveTextContent('$200.00')
    expect(moomooLink.closest('tr')).toHaveTextContent('$200.00')
    expect(moomooLink.closest('tr')).not.toHaveTextContent('$100.00')
  })

  it('shows the fallback banner when the stream is on SSE', async () => {
    mockedStream.mockReturnValue('fallback')
    renderScreen()
    await waitFor(() => expect(screen.getByText(/SSE fallback/)).toBeInTheDocument())
  })

  it('replays a recorded window from the lake under a visible banner', async () => {
    const user = userEvent.setup()
    mocked.replayExtent.mockResolvedValue({
      source: 'lake',
      count: 3,
      earliest: T0,
      latest: T0,
      venues: ['hyperliquid'],
    })
    mocked.replayWindow.mockResolvedValue({
      source: 'lake',
      window: { start: T0, end: T0, count: 1 },
      updates: [
        {
          venue: 'hyperliquid',
          instrument: 'BTC',
          kind: 'quote',
          provenance: 'real',
          data_time: T0,
          received_at: T0,
          sequence: 5,
          sequence_gap: false,
          payload: { bid: 100, ask: 100.5 },
          state: null,
          state_note: null,
        },
      ],
    })
    renderScreen()
    await waitFor(() => expect(screen.getByText('Recorded replay')).toBeInTheDocument())
    await waitFor(() =>
      expect(screen.getByText(/Recorded extent: 3 updates/)).toBeInTheDocument(),
    )
    await user.click(screen.getByRole('button', { name: 'Replay all' }))
    await waitFor(() => expect(screen.getByText('Replay mode')).toBeInTheDocument())
    expect(
      screen.getByText(
        (_, el) =>
          el?.tagName === 'SPAN' && (el?.textContent?.includes('updates · source: lake') ?? false),
      ),
    ).toBeInTheDocument()
    expect(screen.getAllByText('BTC').length).toBeGreaterThan(0)
    expect(screen.getAllByText('real').length).toBeGreaterThan(0)
    expect(screen.getByText('$100.00 / $100.50')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Clear replay' }))
    expect(screen.queryByText('Replay mode')).not.toBeInTheDocument()
  })

  it('explains honestly when no replay lake is attached', async () => {
    mocked.replayExtent.mockRejectedValue(new Error('404: no replay lake is attached'))
    renderScreen()
    await waitFor(() =>
      expect(screen.getByText(/No replay lake attached/)).toBeInTheDocument(),
    )
  })

  it('requests and renders price trails by exact venue and symbol identity', async () => {
    mocked.priceTrail.mockResolvedValue({
      trail: {
        'hyperliquid:BTC': [100.0, 100.5, 101.0],
        'hyperliquid:SOL': [30.0, 30.2],
        'moomoo:BTC': [200.0, 190.0],
      },
    })
    mocked.replayExtent.mockRejectedValue(new Error('no lake'))
    renderScreen()
    await waitFor(() => expect(screen.getByText('BTC')).toBeInTheDocument())
    await waitFor(() =>
      expect(mocked.priceTrail).toHaveBeenCalledWith({
        identities: 'hyperliquid:BTC,hyperliquid:SOL',
        limit: 20,
      }),
    )
    await waitFor(() =>
      expect(
        screen.getByRole('img', { name: 'Price trend: 3 data points' }),
      ).toBeInTheDocument(),
    )
  })

  it('filters the watchlist by symbol or venue text', async () => {
    renderScreen()
    await waitFor(() => expect(
      screen.getByRole('link', { name: 'BTC' }),
    ).toBeInTheDocument())
    const input = screen.getByRole('searchbox', { name: 'Filter the watchlist by symbol or venue' })
    fireEvent.change(input, { target: { value: 'zzz' } })
    await waitFor(() => {
      expect(screen.queryByRole('link', { name: 'BTC' })).not.toBeInTheDocument()
    })
    expect(screen.getByText('No instruments match the filter.')).toBeInTheDocument()
    fireEvent.change(input, { target: { value: '' } })
    await waitFor(() => expect(
      screen.getByRole('link', { name: 'BTC' }),
    ).toBeInTheDocument())
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

describe('live timeline reconciliation', () => {
  it('keeps a delayed HTTP row before the newer streamed row', () => {
    const older = marketUpdate('quote', 'quote-old', T0, { bid: 99, ask: 100 })
    const newer = marketUpdate(
      'quote',
      'quote-new',
      '2026-08-09T10:00:02+00:00',
      { bid: 101, ask: 102 },
    )

    const reconciled = reconcileUpdates([newer], [older])

    expect(reconciled.map((update) => update.source_event_id)).toEqual([
      'quote-old',
      'quote-new',
    ])
  })

  it('scopes provider identity by venue, instrument and kind', () => {
    const quote = marketUpdate('quote', 'provider-id', T0, { bid: 99, ask: 100 })
    const trade = marketUpdate('trade', 'provider-id', T0, { price: 100, size: 1 })

    expect(reconcileUpdates([quote], [trade])).toHaveLength(2)
  })

  it('does not let a delayed snapshot regress streamed instrument state', () => {
    const newer = view(
      { bid: 101, ask: 102 },
      {
        received_at: '2026-08-09T10:00:02+00:00',
        source_event_id: 'quote-new',
        label: 'real',
      },
    )
    const older = view(
      { bid: 99, ask: 100 },
      { received_at: T0, source_event_id: 'quote-old', label: 'stale' },
    )
    const reconciled = reconcileInstrumentState(
      { venue: 'hyperliquid', instrument: 'BTC', label: 'real', kinds: { quote: newer } },
      { venue: 'hyperliquid', instrument: 'BTC', label: 'stale', kinds: { quote: older } },
    )

    expect(reconciled.kinds.quote.source_event_id).toBe('quote-new')
    expect(reconciled.label).toBe('real')
  })

  it('selects the newest complete book epoch independent of arrival order', () => {
    const oldBid = marketUpdate(
      'l2_snapshot', 'old:bid', T0, { side: 'bid', levels: [[99, 1]] }, 'old',
    )
    const oldAsk = marketUpdate(
      'l2_snapshot', 'old:ask', T0, { side: 'ask', levels: [[100, 1]] }, 'old',
    )
    const newerAt = '2026-08-09T10:00:02+00:00'
    const newBid = marketUpdate(
      'l2_snapshot', 'new:bid', newerAt, { side: 'bid', levels: [[101, 1]] }, 'new',
    )
    const newAsk = marketUpdate(
      'l2_snapshot', 'new:ask', newerAt, { side: 'ask', levels: [[102, 1]] }, 'new',
    )

    const selected = latestCompleteBookSides([newBid, newAsk, oldBid, oldAsk])

    expect(selected.bid?.snapshot_epoch).toBe('new')
    expect(selected.ask?.snapshot_epoch).toBe('new')
  })
})

describe('CockpitDetailScreen', () => {
  it('ignores same-symbol updates from another venue', async () => {
    let push: (update: MarketUpdate) => void = () => {}
    mockedStream.mockImplementation((onUpdate) => {
      push = onUpdate
      return 'live'
    })
    renderDetail('BTC', 'hyperliquid')
    await waitFor(() => expect(screen.getByText(/mid \$100\.25/)).toBeInTheDocument())

    act(() => {
      push({
        venue: 'moomoo',
        instrument: 'BTC',
        kind: 'quote',
        provenance: 'real',
        data_time: T0,
        received_at: T0,
        sequence: 8,
        sequence_gap: false,
        payload: { bid: 200, ask: 201 },
        state: null,
        state_note: null,
      })
    })

    expect(screen.queryByText('$200.50')).not.toBeInTheDocument()
    expect(screen.getByText(/mid \$100\.25/)).toBeInTheDocument()
  })
  it('keeps the canonical workspace link when the live snapshot is unavailable', async () => {
    mocked.liveState.mockRejectedValue(new Error('live feed unavailable'))
    mocked.markets.mockResolvedValue({
      instruments: [{ venue: 'moomoo', symbol: 'NVDA', mark: 184 }],
    })
    renderDetail('NVDA', 'moomoo')

    await waitFor(() => expect(
      screen.getByRole('link', { name: 'Open integrated workspace' }),
    ).toHaveAttribute('href', '/instruments/moomoo/NVDA'))
  })

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
    expect(screen.getByRole('link', { name: 'Open integrated workspace' })).toHaveAttribute(
      'href',
      '/instruments/hyperliquid/BTC',
    )
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
      {
        kind: 'l2_snapshot',
        sequence: 6,
        source_event_id: 'epoch-1:bid',
        snapshot_epoch: 'epoch-1',
      },
    )
    mocked.liveState.mockResolvedValue({
      generated_at: T0,
      instruments: {
        'hyperliquid:SOL': {
          venue: 'hyperliquid',
          instrument: 'SOL',
          label: 'real',
          kinds: {
            quote: view({ bid: 30, ask: 30.2 }),
            candle,
            trade,
            metrics: view(
              { funding_rate: 0.0001, mark_price: 100.2, index_price: 100, open_interest: 4567 },
              { kind: 'metrics', sequence: 2 },
            ),
          },
          book_sides: { bid: l2Bid },
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
    act(() => push({
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
    }))
    await waitFor(() => expect(screen.getByText('1-candle return')).toBeInTheDocument())
    expect(screen.getByText('Realized vol (per candle)')).toBeInTheDocument()
    expect(screen.getByText('Last trade size')).toBeInTheDocument()
    expect(screen.getByText('Candle volume')).toBeInTheDocument()
    expect(screen.getByText('Mark–index divergence')).toBeInTheDocument()
    expect(screen.getByText('12,345')).toBeInTheDocument()
    // The trade-size value sits in the dd of the "Last trade size" row.
    const tradeSizeRow = screen.getByText('Last trade size').closest('div')
    expect(tradeSizeRow?.querySelector('dd')).toHaveTextContent('2')
    // The book depth chart needs both sides from one epoch. A newer ask
    // invalidates the seeded bid until its matching bid arrives.
    expect(screen.queryByRole('img', { name: /Book depth chart/ })).not.toBeInTheDocument()
    act(() => push({
      venue: 'hyperliquid',
      instrument: 'SOL',
      kind: 'l2_snapshot',
      provenance: 'real',
      data_time: T0,
      received_at: T0,
      sequence: 7,
      sequence_gap: false,
      source_event_id: 'epoch-2:ask',
      snapshot_epoch: 'epoch-2',
      payload: { side: 'ask', levels: [[30.2, 0.5]] },
      state: null,
      state_note: null,
    }))
    expect(screen.queryByRole('img', { name: /Book depth chart/ })).not.toBeInTheDocument()
    act(() => push({
      venue: 'hyperliquid',
      instrument: 'SOL',
      kind: 'l2_snapshot',
      provenance: 'real',
      data_time: T0,
      received_at: T0,
      sequence: 8,
      sequence_gap: false,
      source_event_id: 'epoch-2:bid',
      snapshot_epoch: 'epoch-2',
      payload: { side: 'bid', levels: [[30.0, 1.0], [29.5, 2.0]] },
      state: null,
      state_note: null,
    }))
    await waitFor(() =>
      expect(screen.getByRole('img', { name: /Book depth chart/ })).toBeInTheDocument(),
    )
  })
})
