import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from '@/App'
import { api, type PnL, type Position, type Watchlist } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'
import { MarketsScreen } from './Markets'
import { PnLScreen, PositionsScreen } from './Trading'
import { WatchlistScreen } from './Watchlist'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      demoStatus: vi.fn(),
      health: vi.fn(),
      killSwitch: vi.fn(),
      markets: vi.fn(),
      overview: vi.fn(),
      pnl: vi.fn(),
      positions: vi.fn(),
      watchlist: vi.fn(),
    },
  }
})

vi.mock('@/screens/InstrumentWorkspace', () => ({
  default: () => <main>Unified instrument workspace</main>,
}))

const mocked = vi.mocked(api)

const heldPosition: Position = {
  average_cost: 100,
  instrument: {
    currency: 'USD',
    instrument_type: 'perpetual',
    metadata: {},
    symbol: 'BTC-USD',
    venue: 'hyperliquid',
  },
  key: 'hyperliquid:BTC-USD',
  mark_status: {
    provenance: 'real',
    reason: null,
    received_at: '2026-08-12T10:00:00Z',
    status: 'available',
  },
  quantity: 2,
  realized_pnl: 5,
  unrealized_pnl: 20,
}

const completePnl: PnL = {
  equity: 100_020,
  mark_statuses: {
    'hyperliquid:BTC-USD': heldPosition.mark_status!,
  },
  marks: { 'hyperliquid:BTC-USD': 110 },
  missing_marks: [],
  realized_pnl: 5,
  starting_cash: 100_000,
  total_pnl: 20,
  unrealized_pnl: 15,
  valuation_complete: true,
  valuation_reason: null,
}

const unavailableWatchlist = {
  entries: [{ mark: null, symbol: 'BTC-USD', venue: null }],
} satisfies Watchlist

function Providers({ children, initialEntries = ['/'] }: {
  children: React.ReactNode
  initialEntries?: string[]
}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return (
    <QueryClientProvider client={client}>
      <PreferencesProvider>
        <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
      </PreferencesProvider>
    </QueryClientProvider>
  )
}

function LocationProbe() {
  return <output data-testid="location">{useLocation().pathname}</output>
}

beforeEach(() => {
  vi.clearAllMocks()
  window.localStorage.clear()
  mocked.health.mockResolvedValue({
    live_trading: false,
    paper_mode: true,
    project: 'QuantMesh',
    runtime_mode: 'operator',
    status: 'ok',
    version: '0.1.1rc1',
  })
  mocked.killSwitch.mockResolvedValue({ kill_switch: false, kill_switches: {} })
  mocked.demoStatus.mockRejectedValue(new Error('not a demo'))
  mocked.overview.mockResolvedValue({
    account: { cash: 100_000, equity: 100_000, kill_switch: false, starting_cash: 100_000 },
    marks: {},
    missing_marks: [],
    venues: [],
    watchlist: [],
  })
  mocked.positions.mockResolvedValue([heldPosition])
  mocked.pnl.mockResolvedValue(completePnl)
})

describe('canonical instrument workspace navigation', () => {
  it('keeps retained reset directories visible to the operator in the shell', async () => {
    mocked.health.mockResolvedValue({
      live_trading: false,
      paper_mode: true,
      project: 'QuantMesh',
      runtime_mode: 'demo',
      status: 'ok',
      version: '0.1.1rc1',
    })
    mocked.demoStatus.mockResolvedValue({
      health: { seed: 20260809, status: 'ok' },
      last_update: '2026-08-08T12:00:00Z',
      marker: '.quantmesh-demo.json',
      mode: 'demo',
      retained_reset_cleanup: {
        automatic_deletion_supported: false,
        instructions: 'Stop QuantMesh, inspect the retained path, then remove it manually.',
        mode: 'manual-only',
      },
      retained_resets: [{
        acknowledged: false,
        exists: true,
        path: 'C:/demo/.session.reset-quarantine-1',
      }],
      root: 'C:/demo/session',
      scenario: {
        anchor: '2026-08-08T12:00:00Z',
        commit: 'fixture',
        open: '2026-08-08T09:30:00Z',
        seed: 20260809,
      },
      source: 'demo',
      surfaces: {},
      synthetic: true,
    })

    render(<App />, { wrapper: Providers })

    const warning = await screen.findByRole('status', {
      name: '1 retained reset · manual cleanup',
    })
    expect(warning).toHaveAttribute(
      'title',
      expect.stringContaining('C:/demo/.session.reset-quarantine-1'),
    )
  })

  it('links each Markets instrument directly to its venue-scoped workspace', async () => {
    mocked.markets.mockResolvedValue({
      instruments: [{ mark: 110, symbol: 'BTC-USD', venue: 'hyperliquid' }],
    })
    mocked.overview.mockResolvedValue({
      account: { cash: 100_000, equity: 100_000, kill_switch: false, starting_cash: 100_000 },
      marks: {},
      missing_marks: [],
      venues: [{
        instruments: [{ mark: 110, symbol: 'BTC-USD' }],
        venue: 'hyperliquid',
      }],
      watchlist: [],
    })

    render(<MarketsScreen />, { wrapper: Providers })

    expect(await screen.findByRole('link', { name: 'BTC-USD' })).toHaveAttribute(
      'href',
      '/instruments/hyperliquid/BTC-USD',
    )
  })

  it('uses each Watchlist entry venue instead of resolving the first symbol match', async () => {
    mocked.watchlist.mockResolvedValue({
      entries: [
        { mark: 201, symbol: 'BTC-USD', venue: 'moomoo' },
        { mark: 110, symbol: 'BTC-USD', venue: 'hyperliquid' },
      ],
    })
    mocked.overview.mockResolvedValue({
      account: { cash: 100_000, equity: 100_000, kill_switch: false, starting_cash: 100_000 },
      marks: {},
      missing_marks: [],
      venues: [
        { instruments: [{ mark: 110, symbol: 'BTC-USD' }], venue: 'hyperliquid' },
        { instruments: [{ mark: 201, symbol: 'BTC-USD' }], venue: 'moomoo' },
      ],
      watchlist: [],
    })

    render(<WatchlistScreen />, { wrapper: Providers })

    const links = await screen.findAllByRole('link', { name: 'BTC-USD' })
    expect(links.map((link) => link.getAttribute('href'))).toEqual([
      '/instruments/moomoo/BTC-USD',
      '/instruments/hyperliquid/BTC-USD',
    ])
  })

  it('fails closed when a legacy Watchlist row has no venue identity', async () => {
    mocked.watchlist.mockResolvedValue(unavailableWatchlist)
    mocked.overview.mockResolvedValue({
      account: { cash: 100_000, equity: 100_000, kill_switch: false, starting_cash: 100_000 },
      marks: {},
      missing_marks: [],
      venues: [{ instruments: [{ mark: 110, symbol: 'BTC-USD' }], venue: 'hyperliquid' }],
      watchlist: [],
    })

    render(<WatchlistScreen />, { wrapper: Providers })

    expect(await screen.findByText('Identity unavailable')).toBeInTheDocument()
    expect(screen.getAllByText('—')).toHaveLength(2)
    expect(screen.queryByRole('link', { name: 'BTC-USD' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Trade' })).not.toBeInTheDocument()
  })

  it('links a held position directly to its exact venue-scoped workspace', async () => {
    render(<PositionsScreen />, { wrapper: Providers })

    expect(await screen.findByRole('link', { name: 'BTC-USD' })).toHaveAttribute(
      'href',
      '/instruments/hyperliquid/BTC-USD',
    )
  })
})

describe('legacy symbol-only cockpit routes', () => {
  function renderApp(path: string) {
    render(
      <Providers initialEntries={[path]}>
        <App />
        <LocationProbe />
      </Providers>,
    )
  }

  it('redirects only when the symbol belongs to exactly one venue', async () => {
    mocked.markets.mockResolvedValue({
      instruments: [
        { mark: 110, symbol: 'BTC-USD', venue: 'hyperliquid' },
        { mark: 180, symbol: 'NVDA', venue: 'moomoo' },
      ],
    })

    renderApp('/cockpit/BTC-USD')

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(
      '/instruments/hyperliquid/BTC-USD',
    ))
  })

  it('redirects a venue-scoped legacy cockpit URL to the unified workspace', async () => {
    renderApp('/cockpit/hyperliquid/BTC-USD')

    await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent(
      '/instruments/hyperliquid/BTC-USD',
    ))
  })

  it('fails closed when the symbol exists on multiple venues', async () => {
    mocked.markets.mockResolvedValue({
      instruments: [
        { mark: 110, symbol: 'BTC-USD', venue: 'hyperliquid' },
        { mark: 201, symbol: 'BTC-USD', venue: 'moomoo' },
      ],
    })

    renderApp('/cockpit/BTC-USD')

    expect(await screen.findByText('Multiple venues carry BTC-USD. Choose a venue-specific link.')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/cockpit/BTC-USD')
  })

  it('fails closed when the symbol is absent from the market directory', async () => {
    mocked.markets.mockResolvedValue({ instruments: [] })

    renderApp('/cockpit/UNKNOWN')

    expect(await screen.findByText('UNKNOWN is not present in the market directory.')).toBeInTheDocument()
    expect(screen.getByTestId('location')).toHaveTextContent('/cockpit/UNKNOWN')
  })
})

describe('valuation honesty', () => {
  it('shows a held position mark status and reason instead of an unqualified value', async () => {
    mocked.positions.mockResolvedValue([{
      ...heldPosition,
      mark_status: {
        provenance: 'real',
        reason: 'Quote is older than the valuation fence.',
        received_at: '2026-08-12T09:50:00Z',
        status: 'stale',
      },
      unrealized_pnl: null,
    }])
    mocked.pnl.mockResolvedValue({
      ...completePnl,
      marks: {},
      missing_marks: ['hyperliquid:BTC-USD'],
      valuation_complete: false,
      valuation_reason: 'One held position has no current mark.',
    })

    render(<PositionsScreen />, { wrapper: Providers })

    const row = (await screen.findByRole('link', { name: 'BTC-USD' })).closest('tr')!
    expect(within(row).getByText('Stale')).toBeInTheDocument()
    expect(within(row).getByText('Quote is older than the valuation fence.')).toBeInTheDocument()
    expect(within(row).getAllByText('—').length).toBeGreaterThanOrEqual(2)
  })

  it('does not present incomplete equity, total, or unrealized P&L as exact', async () => {
    mocked.pnl.mockResolvedValue({
      ...completePnl,
      missing_marks: ['hyperliquid:BTC-USD'],
      valuation_complete: false,
      valuation_reason: 'One held position has no current mark.',
    })

    render(<PnLScreen />, { wrapper: Providers })

    expect(await screen.findByText('Incomplete valuation')).toBeInTheDocument()
    expect(screen.getByText('One held position has no current mark.')).toBeInTheDocument()
    expect(screen.getByText('Equity').closest('[data-slot="card"]')).toHaveTextContent('Unavailable')
    expect(screen.getByText('Total P&L').closest('[data-slot="card"]')).toHaveTextContent('Unavailable')
    expect(screen.getByText('Unrealized').closest('[data-slot="card"]')).toHaveTextContent('Unavailable')
    expect(screen.getByText('Realized').closest('[data-slot="card"]')).toHaveTextContent('$5.00')
  })

  it('treats a legacy valuation response as incomplete while a position is held', async () => {
    const legacy = { ...completePnl }
    delete legacy.valuation_complete
    delete legacy.valuation_reason
    mocked.pnl.mockResolvedValue(legacy)

    render(<PnLScreen />, { wrapper: Providers })

    expect(await screen.findByText('Incomplete valuation')).toBeInTheDocument()
    expect(screen.getByText('Valuation evidence is missing from this response.')).toBeInTheDocument()
    expect(screen.getByText('Equity').closest('[data-slot="card"]')).toHaveTextContent('Unavailable')
  })

  it('rejects an asserted-complete valuation when the held mark is absent', async () => {
    mocked.pnl.mockResolvedValue({
      ...completePnl,
      marks: {},
      missing_marks: ['hyperliquid:BTC-USD'],
      valuation_complete: true,
    })

    render(<PnLScreen />, { wrapper: Providers })

    expect(await screen.findByText('Incomplete valuation')).toBeInTheDocument()
    expect(screen.getByText('A held position has no finite available mark.')).toBeInTheDocument()
    expect(screen.getByText('Equity').closest('[data-slot="card"]')).toHaveTextContent('Unavailable')
  })
})
