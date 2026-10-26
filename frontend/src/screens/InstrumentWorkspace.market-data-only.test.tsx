// Component contract tests use labelled synthetic payloads; no native/provider evidence.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { ApiError, api, type InstrumentWorkspace, type MarketUpdate } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'
import { workspace as base } from './instrument/scenario-lab-fixture'
import { InstrumentWorkspaceScreen } from './InstrumentWorkspace'

vi.mock('@/lib/api', async original => {
  const actual = await original<typeof import('@/lib/api')>()
  return { ...actual, api: { ...actual.api, health: vi.fn(), instrumentWorkspace: vi.fn(), decisionPacket: vi.fn(), markets: vi.fn(), liveState: vi.fn(), packetCopilot: vi.fn(), packetMonitoring: vi.fn(), saveDecisionPacket: vi.fn() } }
})
let publish: (update: MarketUpdate) => void
vi.mock('@/lib/live', async original => ({ ...await original<typeof import('@/lib/live')>(), useLiveConnection: (callback: typeof publish) => { publish = callback; return 'live' } }))
vi.mock('@/components/charts/InstrumentChart', () => ({ InstrumentChart: ({ primary }: { primary: InstrumentWorkspace['history'] }) => <output data-testid="observed-bars">{primary.bars.map(bar => `${bar.timestamp}:${bar.close}`).join('|')}</output> }))
const health = { status: 'ok', project: 'QuantMesh', version: 'test', paper_mode: true, live_trading: false, runtime_mode: 'live' as const, market_data_only: true, market_data_acquisition: { state: 'running' as const, reason: null } }
function sample(): InstrumentWorkspace {
  const instrument = { ...base.instrument, symbol: 'BTC', venue: 'hyperliquid' as const, instrument_type: 'perpetual' as const }
  return { ...base, instrument, history: { ...base.history, instrument, range: '1d', interval: '1m', as_of: '2026-10-25T16:31:00Z', source: 'hyperliquid-live-replay', license: 'Public observations', calendar: '24/7', coverage: { ...base.history.coverage, symbol: 'BTC', venue: 'hyperliquid', interval: '1m', rows: 1, start: '2026-10-25T16:30:00Z', end: '2026-10-25T16:30:00Z' }, bars: [{ ...base.history.bars[0], instrument, interval: '1m', timestamp: '2026-10-25T16:30:00Z', close: 70000 }], limitations: ['TEST FIXTURE: Minute-end public REST snapshot observations only; provider finality/PIT unknown; coverage partial.'] }, live: { ...base.live, bid: null, ask: null, last: null, data_time: null, received_at: null, age_ms: null, status: 'unavailable', label: 'unavailable', source: null, provenance: null } }
}
function mount(path = '/instruments/hyperliquid/BTC?range=1d&mode=line') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><PreferencesProvider><MemoryRouter initialEntries={[path]}><Routes><Route path="/instruments/:venue/:symbol" element={<InstrumentWorkspaceScreen />} /></Routes></MemoryRouter></PreferencesProvider></QueryClientProvider>)
  return client
}
beforeEach(() => { vi.clearAllMocks(); localStorage.clear(); vi.mocked(api.health).mockResolvedValue(health); vi.mocked(api.instrumentWorkspace).mockResolvedValue(sample()) })
it.each([1, 2, 60])('summary applicability marks market-only evaluation as not run and hides summary for %s observed bars', async count => {
  const original = sample()
  const bars = Array.from({ length: count }, (_, index) => ({ ...original.history.bars[0], timestamp: new Date(Date.UTC(2026, 9, 26, 7, 39 - count + index)).toISOString().replace('.000Z', 'Z'), close: index === 0 ? 79966 : 80002 }))
  vi.mocked(api.instrumentWorkspace).mockResolvedValue({ ...original, history: { ...original.history, bars, coverage: { ...original.history.coverage, rows: count } } })
  mount(); await screen.findByTestId('observed-bars')
  expect(screen.getByText('Market data acquisition · Strategy evaluation has not been run.')).toBeInTheDocument()
  expect(screen.queryByText('Realized volatility')).not.toBeInTheDocument()
  expect(screen.queryByText('Drawdown')).not.toBeInTheDocument()
  expect(screen.queryByText('Forecast distribution')).not.toBeInTheDocument()
  expect(screen.getByText('hyperliquid-live-replay')).toBeInTheDocument()
  expect(screen.getByText('Partial observed coverage · not qualified 24-hour history')).toBeInTheDocument()
  expect(screen.getByLabelText('Last observed minute (UTC)')).toHaveTextContent(bars.at(-1)!.timestamp)
  expect(screen.getByLabelText('Time since last observed minute')).not.toBeEmptyDOMElement()
  expect(screen.getByTestId('observed-bars')).toHaveTextContent(`${bars[0].timestamp}:79966`)
})
it('uses only the fixed BTC1d formal API and renders observed bars without research or trading consumers', async () => {
  mount(); await screen.findByTestId('observed-bars')
  expect(api.instrumentWorkspace).toHaveBeenCalledWith('hyperliquid', 'BTC', '1d', [])
  expect(screen.getByText('Market data acquisition · Trading disabled')).toBeInTheDocument()
  expect(screen.getByText('Quote / depth unavailable · candle close is not an executable quote.')).toBeInTheDocument()
  expect(screen.queryByRole('region', { name: /Decision|Evidence/i })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Paper|Watch|Reject|Forecast|1Y|5D/i })).not.toBeInTheDocument()
  expect(api.decisionPacket).not.toHaveBeenCalled(); expect(api.packetCopilot).not.toHaveBeenCalled(); expect(api.packetMonitoring).not.toHaveBeenCalled(); expect(api.saveDecisionPacket).not.toHaveBeenCalled()
  expect(screen.getByTestId('observed-bars')).toHaveTextContent('2026-10-25T16:30:00Z:70000')
  expect(screen.getByText(/provider finality\/PIT unknown/)).toBeInTheDocument()
})
it.each(['range=5d&mode=line','range=1d&mode=line&compare=moomoo:NVDA','range=1d&mode=line&packet=packet-aaaaaaaaaaaaaaaaaaaaaaaa','range=1d&mode=line&horizon=30','range=1d&mode=line&forecast_id=x','range=1d&range=1d&mode=line'])('rejects unsupported query before any workspace or packet read: %s', async query => {
  mount(`/instruments/hyperliquid/BTC?${query}`)
  await screen.findByText('This view is unavailable in market-data-only mode.')
  expect(api.instrumentWorkspace).not.toHaveBeenCalled(); expect(api.decisionPacket).not.toHaveBeenCalled()
})
it('does not request another symbol or launch the ordinary404 cockpit fallback', async () => {
  vi.mocked(api.instrumentWorkspace).mockRejectedValue(new ApiError(404, 'No observed history'))
  mount(); await screen.findByText('Waiting for the first completed-minute REST observation.')
  expect(api.liveState).not.toHaveBeenCalled(); expect(api.markets).not.toHaveBeenCalled(); expect(api.decisionPacket).not.toHaveBeenCalled()
})
it('blocks another symbol and a packet request while the mode is still unknown', async () => {
  vi.mocked(api.health).mockReturnValue(new Promise(() => {}))
  mount('/instruments/moomoo/NVDA?range=1d&packet=packet-aaaaaaaaaaaaaaaaaaaaaaaa')
  expect(api.instrumentWorkspace).not.toHaveBeenCalled(); expect(api.decisionPacket).not.toHaveBeenCalled()
})
it('refuses another symbol after the restricted mode resolves', async () => {
  mount('/instruments/hyperliquid/ETH?range=1d&mode=line')
  await screen.findByText('This view is unavailable in market-data-only mode.')
  expect(api.instrumentWorkspace).not.toHaveBeenCalled(); expect(api.decisionPacket).not.toHaveBeenCalled()
})
it('retains last observed bars after a read failure without mounting fallback consumers', async () => {
  const client = mount(); await screen.findByTestId('observed-bars'); const before = screen.getByTestId('observed-bars').textContent
  vi.mocked(api.instrumentWorkspace).mockRejectedValue(new ApiError(503, 'Observed history temporarily unavailable'))
  await act(async () => { await client.invalidateQueries({ queryKey: ['instrument-workspace'] }) })
  await waitFor(() => expect(api.instrumentWorkspace).toHaveBeenCalledTimes(2))
  expect(screen.getByTestId('observed-bars').textContent).toBe(before)
  expect(api.liveState).not.toHaveBeenCalled(); expect(api.markets).not.toHaveBeenCalled()
})
it.each(['capacity_stopped','stopped','failed'])('keeps last real bars while %s overrides connected status and health never renews their time', async state => {
  const client = mount(); await screen.findByTestId('observed-bars')
  const before = screen.getByTestId('observed-bars').textContent
  act(() => client.setQueryData(['health'], { ...health, market_data_acquisition: { state, reason: state === 'capacity_stopped' ? 'capacity_exhausted' : 'shutdown' } }))
  expect(screen.getByTestId('observed-bars').textContent).toBe(before)
  await waitFor(() => expect(screen.queryByText('Acquiring observations')).not.toBeInTheDocument())
  expect(screen.getByText(/Last observations remain readable/)).toBeInTheDocument()
  expect(screen.getByText(/2026.*16:31/)).toBeInTheDocument()
})
it('ages the original observed minute rather than renewing it from health or workspace read time', async () => {
  const clock = vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-25T16:32:00Z'))
  try {
    const client = mount(); await screen.findByTestId('observed-bars')
    expect(screen.getByLabelText('Time since last observed minute')).toHaveTextContent(/2\s*m/)
    clock.mockReturnValue(Date.parse('2026-10-25T16:33:00Z'))
    act(() => client.setQueryData(['health'], { ...health, market_data_acquisition: { state: 'capacity_stopped', reason: 'capacity_exhausted' } }))
    await waitFor(() => expect(screen.getByLabelText('Time since last observed minute')).toHaveTextContent(/3\s*m/))
    expect(screen.getByLabelText('Last observed minute (UTC)')).toHaveTextContent('2026-10-25T16:30:00Z')
  } finally { clock.mockRestore() }
})
it('changes chart data only for a new supplied observation, not identical refresh or health state', async () => {
  const client = mount(); await screen.findByTestId('observed-bars'); const before = screen.getByTestId('observed-bars').textContent
  act(() => client.setQueryData(['instrument-workspace','hyperliquid','BTC','1d',[]], sample()))
  expect(screen.getByTestId('observed-bars').textContent).toBe(before)
  const original = sample(); const next = { ...original, history: { ...original.history, bars: [...original.history.bars, { ...original.history.bars[0], timestamp: '2026-10-25T16:31:00Z', close: 70001 }] } }
  act(() => client.setQueryData(['instrument-workspace','hyperliquid','BTC','1d',[]], next))
  await waitFor(() => expect(screen.getByTestId('observed-bars')).toHaveTextContent('2026-10-25T16:31:00Z:70001'))
  expect(api.saveDecisionPacket).not.toHaveBeenCalled()
})
it('keeps chart controls local instead of adding forbidden server query parameters', async () => {
  mount(); await screen.findByTestId('observed-bars')
  fireEvent.click(screen.getByRole('button', { name: 'Candles' }))
  expect(api.instrumentWorkspace).toHaveBeenCalledTimes(1)
  expect(screen.getByRole('button', { name: 'Candles' })).toHaveAttribute('aria-pressed', 'true')
})
