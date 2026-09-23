import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { api, type MarketUpdate } from '@/lib/api'
import { useLiveConnection } from '@/lib/live'
import { PreferencesProvider } from '@/lib/preferences'
import { MarketsScreen } from './Markets'
import { WatchlistScreen } from './Watchlist'

vi.mock('@/lib/api', async (load) => {
  const actual = await load<typeof import('@/lib/api')>()
  return { ...actual, api: { ...actual.api, health: vi.fn(), markets: vi.fn(), overview: vi.fn(), liveState: vi.fn(), decisionInbox: vi.fn() } }
})
vi.mock('@/lib/live', async (load) => {
  const actual = await load<typeof import('@/lib/live')>()
  return { ...actual, useLiveConnection: vi.fn() }
})
let publish: (update: MarketUpdate) => void
const at = '2026-09-12T12:00:00Z'

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(useLiveConnection).mockImplementation(callback => { publish = callback; return 'live' })
  vi.mocked(api.health).mockResolvedValue({ status: 'ok', project: 'QuantMesh', version: 'test', runtime_mode: 'live', paper_mode: true, live_trading: false })
  vi.mocked(api.liveState).mockResolvedValue({ generated_at: at, instruments: Object.fromEntries(['BTC', 'ETH', 'SOL'].map(symbol => [`hyperliquid:${symbol}`, {
    venue: 'hyperliquid', instrument: symbol, label: 'real', kinds: { quote: { kind: 'quote', provenance: 'real', data_time: at, received_at: at, age_ms: 500, sequence: 1, sequence_gap: false, label: 'real', payload: { bid: 100, ask: 101 } } },
  }])) })
  vi.mocked(api.markets).mockResolvedValue({ instruments: ['BTC', 'ETH', 'SOL'].map(symbol => ({ venue: 'hyperliquid', symbol, mark: null })) })
  vi.mocked(api.overview).mockResolvedValue({ venues: [{ venue: 'hyperliquid', instruments: ['BTC', 'ETH', 'SOL'].map(symbol => ({ symbol, mark: null })) }] } as Awaited<ReturnType<typeof api.overview>>)
  vi.mocked(api.decisionInbox).mockResolvedValue({ generated_at: at, entries: [], session: { generated_at: at, last_checked_at: null, registered_count: 0, triggered_count: 0, blocked_count: 0 } } as Awaited<ReturnType<typeof api.decisionInbox>>)
})

for (const [name, Component] of [['Markets', MarketsScreen], ['Watchlist', WatchlistScreen]] as const) {
  function renderSurface() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><PreferencesProvider><MemoryRouter><Component /></MemoryRouter></PreferencesProvider></QueryClientProvider>)
  }

  it(`${name} displays metrics-only equity last prices with their source clock and follows updates`, async () => {
    vi.mocked(api.markets).mockResolvedValue({ instruments: ['AAPL', 'NVDA'].map(symbol => ({ venue: 'moomoo', symbol, mark: null })) })
    vi.mocked(api.liveState).mockResolvedValue({ generated_at: at, instruments: Object.fromEntries(['AAPL', 'NVDA'].map(symbol => [`moomoo:${symbol}`, {
      venue: 'moomoo', instrument: symbol, label: 'real', kinds: { metrics: { kind: 'metrics', provenance: 'real', data_time: at, received_at: at, age_ms: 500, sequence: null, sequence_gap: false, label: 'real', payload: { last: symbol === 'AAPL' ? 336.81 : 224.67, volume: 1000 } } },
    }])) })
    renderSurface()
    const link = await screen.findByRole('link', { name: 'AAPL' })
    expect(link).toHaveAttribute('href', '/instruments/moomoo/AAPL?range=1d&mode=line')
    const row = link.closest('tr')!
    await waitFor(() => expect(within(row).getByText('Real')).toBeInTheDocument())
    expect(within(row).getByText('$336.81')).toBeInTheDocument()
    expect(screen.getByText('$224.67')).toBeInTheDocument()
    expect(within(row).getByText('Last trade')).toBeInTheDocument()
    expect(within(row).getAllByRole('cell')[5]).toHaveTextContent(/^\d+ (ms|s)$/)
    expect(row.querySelector('time')).toHaveAttribute('datetime', at)
    const next = '2026-09-12T12:00:06Z'
    act(() => publish({ venue: 'moomoo', instrument: 'AAPL', kind: 'metrics', provenance: 'real', data_time: next, received_at: next, sequence: null, sequence_gap: false, payload: { last: 337.25, volume: 1020 }, state: null, state_note: null }))
    await waitFor(() => expect(within(row).getByText('$337.25')).toBeInTheDocument())
    expect(row.querySelector('time')).toHaveAttribute('datetime', next)
    act(() => publish({ venue: 'moomoo', instrument: 'AAPL', kind: 'status', provenance: 'unavailable', data_time: next, received_at: next, sequence: null, sequence_gap: false, payload: {}, state: 'disconnected', state_note: 'connection lost' }))
    await waitFor(() => expect(within(row).getByText('Unavailable')).toBeInTheDocument())
    expect(within(row).getByText('$337.25')).toBeInTheDocument()
  })

  it.each([null, '336.81', Number.NaN, Number.POSITIVE_INFINITY, 0, -1])(`${name} never formats invalid metrics last %s as a price`, async last => {
    vi.mocked(api.markets).mockResolvedValue({ instruments: [{ venue: 'moomoo', symbol: 'AAPL', mark: null }] })
    vi.mocked(api.liveState).mockResolvedValue({ generated_at: at, instruments: { 'moomoo:AAPL': {
      venue: 'moomoo', instrument: 'AAPL', label: 'stale', kinds: { metrics: { kind: 'metrics', provenance: 'real', data_time: at, received_at: at, age_ms: 100_000, sequence: null, sequence_gap: false, label: 'stale', payload: { last } } },
    } } })
    renderSurface()
    const row = (await screen.findByRole('link', { name: 'AAPL' })).closest('tr')!
    await waitFor(() => expect(within(row).getByText('Stale')).toBeInTheDocument())
    expect(within(row).queryByText(/\$/)).not.toBeInTheDocument()
  })

  it(`${name} keeps configured chart links before any source observation`, async () => {
    vi.mocked(api.liveState).mockResolvedValue({ generated_at: at, instruments: {} })
    renderSurface()
    for (const symbol of ['BTC', 'ETH', 'SOL']) {
      expect(await screen.findByRole('link', { name: symbol })).toHaveAttribute('href', `/instruments/hyperliquid/${symbol}?range=1d&mode=line`)
    }
    expect(screen.getAllByText('Unavailable')).toHaveLength(3)
    expect(screen.queryByText('Real')).not.toBeInTheDocument()
  })

  it(`${name} retains unavailable configured links when source snapshots fail`, async () => {
    vi.mocked(api.liveState).mockRejectedValue(new Error('source offline'))
    renderSurface()
    expect(await screen.findByRole('link', { name: 'SOL' })).toBeInTheDocument()
    expect(await screen.findByRole('status')).toBeInTheDocument()
    expect(screen.getAllByText('Unavailable')).toHaveLength(3)
  })

  it(`${name} waits for runtime identity without rendering demo content`, async () => {
    vi.mocked(api.health).mockReturnValue(new Promise(() => {}))
    renderSurface()
    expect(screen.getByLabelText('Loading')).toBeInTheDocument()
    expect(screen.queryByText(/synthetic marks|nothing here is live|seeded favorites/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'BTC' })).not.toBeInTheDocument()
  })

  it(`${name} explains failed runtime identity instead of showing demo content`, async () => {
    vi.mocked(api.health).mockRejectedValue(new Error('runtime identity offline'))
    renderSurface()
    expect(await screen.findByText('Runtime identity unavailable')).toBeInTheDocument()
    expect(screen.getByText('runtime identity offline')).toBeInTheDocument()
    expect(screen.queryByText(/synthetic marks|nothing here is live|seeded favorites/i)).not.toBeInTheDocument()
  })

  it(`${name} opens real charts even without a saved decision watch and follows source quotes`, async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={client}><PreferencesProvider><MemoryRouter><Component /></MemoryRouter></PreferencesProvider></QueryClientProvider>)
    for (const symbol of ['BTC', 'ETH', 'SOL']) {
      expect(await screen.findByRole('link', { name: symbol })).toHaveAttribute('href', `/instruments/hyperliquid/${symbol}?range=1d&mode=line`)
    }
    expect(screen.getAllByText('$100.50')).toHaveLength(3)
    expect(screen.queryByText(/synthetic marks|nothing here is live|seeded favorites/i)).not.toBeInTheDocument()
    expect(screen.getAllByText('Real')).toHaveLength(3)
    act(() => publish({ venue: 'hyperliquid', instrument: 'BTC', kind: 'quote', provenance: 'real', data_time: at, received_at: at, sequence: 2, sequence_gap: false, payload: { bid: 104, ask: 105 }, state: null, state_note: null }))
    await waitFor(() => expect(screen.getByText('$104.50')).toBeInTheDocument())
    act(() => publish({ venue: 'hyperliquid', instrument: 'BTC', kind: 'status', provenance: 'unavailable', data_time: at, received_at: at, sequence: null, sequence_gap: false, payload: {}, state: 'disconnected', state_note: 'connection lost' }))
    await waitFor(() => expect(screen.getByText('Unavailable')).toBeInTheDocument())
  })
}
