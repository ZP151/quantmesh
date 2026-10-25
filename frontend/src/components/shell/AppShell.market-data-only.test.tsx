import { useEffect } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { PreferencesProvider } from '@/lib/preferences'
import { AppShell } from './AppShell'

const mocks = vi.hoisted(() => ({ health: vi.fn(), kill: vi.fn(), demo: vi.fn(), reset: vi.fn(), child: vi.fn() }))
vi.mock('@/lib/api', async original => ({ ...await original<typeof import('@/lib/api')>(), api: { health: mocks.health, killSwitch: mocks.kill, demoStatus: mocks.demo, demoReset: mocks.reset } }))
const restricted = { status: 'ok', project: 'QuantMesh', version: 'test', paper_mode: true, live_trading: false, runtime_mode: 'live', market_data_only: true, market_data_acquisition: { state: 'running', reason: null } }
function Child() { useEffect(() => { mocks.child() }, []); return <p>Child mounted</p> }
function mount(path = '/instruments/hyperliquid/BTC?range=1d&mode=line') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><PreferencesProvider><MemoryRouter initialEntries={[path]}><Routes><Route element={<AppShell />}><Route path="*" element={<Child />} /></Route></Routes></MemoryRouter></PreferencesProvider></QueryClientProvider>)
}
beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear()
  mocks.health.mockResolvedValue(restricted); mocks.kill.mockResolvedValue({ kill_switch: false, kill_switches: {} })
})
it('waits for health before mounting a potentially forbidden child', () => {
  mocks.health.mockReturnValue(new Promise(() => {})); mount('/research/jobs')
  expect(mocks.child).not.toHaveBeenCalled(); expect(screen.queryByText('Child mounted')).not.toBeInTheDocument()
})
it('limits navigation and hotkeys to the BTC chart while clearly disabling trading', async () => {
  mount(); await screen.findByText('Child mounted')
  expect(screen.getAllByText('Market data acquisition · Trading disabled').length).toBeGreaterThan(0)
  expect(screen.queryByRole('button', { name: /Search|command palette|kill switch|Reset demo/i })).not.toBeInTheDocument()
  expect(screen.queryByRole('link', { name: /Settings|Research jobs|Watchlist|Paper order/i })).not.toBeInTheDocument()
  const links = screen.getAllByRole('link'); expect(links.length).toBeGreaterThan(0)
  links.forEach(link => expect(link).toHaveAttribute('href', '/instruments/hyperliquid/BTC?range=1d&mode=line'))
  fireEvent.keyDown(window, { ctrlKey: true, key: 'k' })
  expect(screen.queryByRole('dialog', { name: /Command/i })).not.toBeInTheDocument()
  expect(mocks.demo).not.toHaveBeenCalled(); expect(mocks.reset).not.toHaveBeenCalled()
})
it.each(['/research/jobs', '/ops/kill-switch', '/instruments/hyperliquid/ETH?range=1d&mode=line', '/instruments/hyperliquid/BTC?range=5d&mode=line', '/instruments/hyperliquid/BTC?range=1d&mode=line&packet=packet-aaaaaaaaaaaaaaaaaaaaaaaa', '/instruments/hyperliquid/BTC?range=1d&range=1d&mode=line'])('does not mount a forbidden route or query: %s', async path => {
  mount(path); await screen.findByText('This view is unavailable in market-data-only mode.')
  expect(mocks.child).not.toHaveBeenCalled(); expect(screen.queryByText('Child mounted')).not.toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Open BTC chart' })).toHaveAttribute('href', '/instruments/hyperliquid/BTC?range=1d&mode=line')
})
it.each(['absent', 'false'])('preserves ordinary mode when optional fields are %s', async mode => {
  const { market_data_only: _mode, market_data_acquisition: _state, ...ordinary } = restricted
  mocks.health.mockResolvedValue(mode === 'false' ? { ...ordinary, market_data_only: false } : ordinary); mount('/research/jobs')
  await screen.findByText('Child mounted'); expect(mocks.child).toHaveBeenCalledOnce()
  expect(screen.getAllByRole('link', { name: /Research jobs/i }).length).toBeGreaterThan(0)
})
it('refreshes acquisition health after five seconds without remounting the workflow', async () => {
  vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
  const view = mount()
  try {
    await screen.findByText('Child mounted')
    expect(mocks.health).toHaveBeenCalledOnce()
    await act(async () => { await vi.advanceTimersByTimeAsync(5_001) })
    await waitFor(() => expect(mocks.health).toHaveBeenCalledTimes(2))
    expect(mocks.child).toHaveBeenCalledOnce()
  } finally { view.unmount(); vi.useRealTimers() }
})
