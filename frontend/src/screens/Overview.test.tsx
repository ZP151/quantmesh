import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { Overview } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'
import { OverviewScreen } from './Overview'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    api: {
      ...actual.api,
      health: vi.fn(),
      overview: vi.fn(),
    },
  }
})

import { api } from '@/lib/api'

const mocked = vi.mocked(api)

function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <PreferencesProvider>
          <OverviewScreen />
        </PreferencesProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('overview valuation honesty', () => {
  beforeEach(() => {
    window.localStorage.clear()
    mocked.health.mockResolvedValue({
      live_trading: false,
      paper_mode: true,
      project: 'QuantMesh',
      runtime_mode: 'operator',
      status: 'ok',
      version: '0.1.1rc1',
    })
  })

  it('renders unavailable instead of cash-equivalent equity when a held mark is missing', async () => {
    mocked.overview.mockResolvedValue({
      account: {
        cash: 9_438.56,
        equity: null,
        kill_switch: false,
        starting_cash: 10_000,
      },
      marks: {},
      missing_marks: ['internal:AAPL'],
      valuation_complete: false,
      valuation_reason: 'missing valid marks for held positions: internal:AAPL',
      venues: [],
      watchlist: [],
    } satisfies Overview)

    renderScreen()

    const equity = (await screen.findByText('Equity')).parentElement!
    expect(equity).toHaveTextContent('Unavailable')
    expect(equity).not.toHaveTextContent('$9,438.56')
    expect(
      screen.getByText('missing valid marks for held positions: internal:AAPL'),
    ).toBeInTheDocument()
  })

  it('renders cash as equity when no held position requires a mark', async () => {
    mocked.overview.mockResolvedValue({
      account: {
        cash: 10_000,
        equity: 10_000,
        kill_switch: false,
        starting_cash: 10_000,
      },
      marks: {},
      missing_marks: [],
      valuation_complete: true,
      valuation_reason: null,
      venues: [],
      watchlist: [],
    } satisfies Overview)

    renderScreen()

    const equity = (await screen.findByText('Equity')).parentElement!
    expect(equity).toHaveTextContent('$10,000.00')
    expect(equity).not.toHaveTextContent('Unavailable')
  })
})
