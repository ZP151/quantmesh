import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { ApiError, type PredictionRow } from '@/lib/api'
import { PredictionScreen } from './Prediction'

// The prediction comparison board renders the server's fold of the
// live state — the api client is mocked with the exact wire shape the
// backend emits (per pair, per venue, plus the diff), so the drills
// pin the screen's math, its distinct states (real / stale /
// unavailable) and the calibration link.

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      prediction: vi.fn(),
    },
  }
})

import { api } from '@/lib/api'

const mocked = vi.mocked(api)

const ROWS: PredictionRow[] = [
  {
    event_key: 'btc-100k',
    title: 'BTC above $100k on 2026-06-26',
    expiry: '2026-06-26T00:00:00+00:00',
    venues: [
      {
        venue: 'polymarket',
        symbol: '0xasset-btc-100k',
        label: 'real',
        probability: 62.5,
        bid: 0.6,
        ask: 0.65,
        spread_bps: 800.0,
        depth: 175.0,
        liquidity: 150.0,
      },
      {
        venue: 'kalshi',
        symbol: 'KXBTD-26JUN26-1000-C',
        label: 'real',
        probability: 65.0,
        bid: 0.62,
        ask: 0.68,
        spread_bps: 92.3,
        depth: 100.0,
        liquidity: 220.0,
      },
    ],
    diff: -2.5,
  },
  {
    event_key: 'eth-5k',
    title: 'ETH above $5,000 on 2026-09-30',
    expiry: null,
    venues: [
      {
        venue: 'polymarket',
        symbol: '0xasset-eth-5k',
        label: 'stale',
        probability: 52.0,
        bid: 0.5,
        ask: 0.54,
        spread_bps: 76.9,
        depth: 20.0,
        liquidity: 40.0,
      },
      {
        venue: 'kalshi',
        symbol: 'KXETHD-30SEP26-5000-C',
        label: 'unavailable',
        probability: null,
        bid: null,
        ask: null,
        spread_bps: null,
        depth: null,
        liquidity: null,
      },
    ],
    diff: null,
  },
]

function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PredictionScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  mocked.prediction.mockResolvedValue(ROWS)
})

describe('PredictionScreen', () => {
  it('renders the cross-venue comparison with the diff', async () => {
    renderScreen()
    await waitFor(() => expect(screen.getByText('BTC above $100k on 2026-06-26')).toBeInTheDocument())
    // the per-venue implied probabilities and the signed diff
    expect(screen.getByText('62.5%')).toBeInTheDocument()
    expect(screen.getByText('65.0%')).toBeInTheDocument()
    expect(screen.getByText('-2.5 pp')).toBeInTheDocument()
    // both pair cards carry the comparison caption
    expect(screen.getAllByText('Polymarket − Kalshi').length).toBe(2)
    // quote, spread, depth and liquidity per venue
    expect(screen.getByText('$0.60 / $0.65')).toBeInTheDocument()
    expect(screen.getByText('$0.62 / $0.68')).toBeInTheDocument()
    expect(screen.getByText('800.0 bps')).toBeInTheDocument()
    expect(screen.getByText('175')).toBeInTheDocument()
    expect(screen.getByText('220')).toBeInTheDocument()
    // the expiry renders as the operator-supplied date
    expect(screen.getByText('Expires 2026-06-26')).toBeInTheDocument()
  })

  it('renders distinct states: stale and honest unavailable', async () => {
    renderScreen()
    await waitFor(() => expect(screen.getByText('BTC above $100k on 2026-06-26')).toBeInTheDocument())
    // the quiet pair's venue is stale, the unconfigured venue is
    // unavailable — with a real probability on the stale venue and an
    // honest dash (never a fabricated number) on the absent one.
    expect(screen.getByText('Stale')).toBeInTheDocument()
    expect(screen.getByText('52.0%')).toBeInTheDocument()
    expect(screen.getByText('Unavailable')).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    expect(screen.getByText('No expiry listed')).toBeInTheDocument()
  })

  it('links calibration to the forecast surface, never fabricating it', async () => {
    renderScreen()
    await waitFor(() => expect(screen.getByText('BTC above $100k on 2026-06-26')).toBeInTheDocument())
    const link = screen.getByRole('link', { name: 'Calibration & forecast history' })
    expect(link).toHaveAttribute('href', '/research/forecasts')
  })

  it('renders the typed error state when no board is attached', async () => {
    mocked.prediction.mockRejectedValue(new ApiError(404, 'no prediction board is attached'))
    renderScreen()
    await waitFor(() => expect(screen.getByText('Prediction board unavailable')).toBeInTheDocument())
    expect(
      screen.getByText(
        /no prediction board is attached — start the workstation with --live and a QUANTMESH_PREDICTION_WATCHLIST\./,
      ),
    ).toBeInTheDocument()
  })
})
