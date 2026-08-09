import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
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
      overview: vi.fn(),
    },
  }
})

import { api } from '@/lib/api'

const mocked = vi.mocked(api)

const OVERVIEW: Overview = {
  account: { cash: 100_000, starting_cash: 100_000, equity: 100_000, kill_switch: false },
  marks: { 'hyperliquid:BTC': 100 },
  missing_marks: [],
  venues: [{ venue: 'hyperliquid', instruments: [{ symbol: 'BTC', mark: 100 }] }],
  watchlist: [{ symbol: 'BTC', mark: 100 }],
}

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

/** zh-CN render smoke (iteration 0017): the same surface renders the
 * translated strings once the stored preference is zh-CN, while the
 * default stays English — the extracted screens are locale-driven. */
describe('locale rendering', () => {
  beforeEach(() => {
    window.localStorage.clear()
    mocked.overview.mockResolvedValue(OVERVIEW)
  })

  it('renders English by default', async () => {
    renderScreen()
    await waitFor(() => expect(screen.getByText('Cash')).toBeInTheDocument())
    expect(screen.getByText('Equity')).toBeInTheDocument()
    expect(screen.getAllByText('Overview').length).toBeGreaterThan(0)
  })

  it('renders the same surface in zh-CN when the preference is stored', async () => {
    window.localStorage.setItem(
      'quantmesh.preferences',
      JSON.stringify({ locale: 'zh-CN', theme: 'dark' }),
    )
    renderScreen()
    await waitFor(() => expect(screen.getByText('现金')).toBeInTheDocument())
    expect(screen.getByText('权益')).toBeInTheDocument()
    expect(screen.getByText('已解除')).toBeInTheDocument()
    expect(screen.getAllByText('总览').length).toBeGreaterThan(0)
  })
})
