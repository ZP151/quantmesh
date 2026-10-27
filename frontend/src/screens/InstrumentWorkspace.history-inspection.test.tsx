// New UI contract uses labelled synthetic observations, not native market qualification.
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { ApiError, api, type HistoricalInspection, type InstrumentWorkspace } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'
import { workspace as base } from './instrument/scenario-lab-fixture'
import { InstrumentWorkspaceScreen } from './InstrumentWorkspace'

vi.mock('@/lib/api', async original => {
  const actual = await original<typeof import('@/lib/api')>()
  return { ...actual, api: { ...actual.api, health: vi.fn(), instrumentWorkspace: vi.fn(), historyInspection: vi.fn(), decisionPacket: vi.fn(), saveDecisionPacket: vi.fn() } }
})
vi.mock('@/lib/live', async original => ({ ...await original<typeof import('@/lib/live')>(), useLiveConnection: () => 'down' }))
vi.mock('@/components/charts/InstrumentChart', () => ({ InstrumentChart: ({ primary }: { primary: InstrumentWorkspace['history'] }) => <output data-testid="inspection-bars">{primary.bars.map(bar => `${bar.timestamp}:${bar.close}`).join('|')}</output> }))
const health = { status: 'ok', project: 'QuantMesh', version: 'test', paper_mode: true, live_trading: false, runtime_mode: 'live' as const, market_data_only: false }
const instrument = { ...base.instrument, symbol: 'BTC', venue: 'hyperliquid' as const, instrument_type: 'perpetual' as const }
const primary = { ...base.history, instrument, range: '1d' as const, interval: '1m', as_of: '2026-10-23T23:44:01Z', bars: [42, 43].map((minute, i) => ({ ...base.history.bars[0], instrument, interval: '1m', timestamp: `2026-10-23T23:${minute}:00Z`, close: 100 + i })), coverage: { ...base.history.coverage, venue: 'hyperliquid' as const, symbol: 'BTC', interval: '1m', start: '2026-10-23T23:42:00Z', end: '2026-10-23T23:43:00Z', rows: 2 }, limitations: ['SYNTHETIC ENGINEERING FIXTURE · not qualified history'] }
const sample: HistoricalInspection = { primary, observed_at: '2026-10-27T15:40:00Z', window_end: primary.as_of, source_time: '2026-10-23T23:43:00Z', source_received_at: '2026-10-23T23:44:00Z', stale: true, stale_after_seconds: 120 }

function mount(path = '/instruments/hyperliquid/BTC?range=1d&mode=line') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><PreferencesProvider><MemoryRouter initialEntries={[path]}><Routes><Route path="/instruments/:venue/:symbol" element={<InstrumentWorkspaceScreen />} /></Routes></MemoryRouter></PreferencesProvider></QueryClientProvider>)
}
async function open() {
  fireEvent.click(await screen.findByRole('button', { name: 'View saved history' }))
  return screen.getByRole('textbox', { name: 'Window end (timezone required)' })
}
function submit(input: HTMLElement, value = sample.window_end) {
  fireEvent.change(input, { target: { value } })
  fireEvent.click(screen.getByRole('button', { name: 'Show saved day' }))
}
beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(api.health).mockResolvedValue(health)
  vi.mocked(api.instrumentWorkspace).mockReturnValue(new Promise(() => {}))
  vi.mocked(api.historyInspection).mockResolvedValue(sample)
})

it('opens before current data loads, reads independent GET and shows distinct times without decisions', async () => {
  mount(); const input = await open(); const currentCalls = vi.mocked(api.instrumentWorkspace).mock.calls.length
  submit(input); await screen.findByTestId('inspection-bars')
  expect(api.historyInspection).toHaveBeenCalledWith('hyperliquid', 'BTC', sample.window_end, expect.any(AbortSignal))
  expect(api.instrumentWorkspace).toHaveBeenCalledTimes(currentCalls)
  expect(screen.getByLabelText('Viewed at')).toHaveTextContent(sample.observed_at)
  expect(screen.getByLabelText('Last saved data time')).toHaveTextContent(sample.source_time)
  expect(screen.getByLabelText('Original receipt time')).toHaveTextContent(sample.source_received_at!)
  expect(screen.getByText('Stale at viewing time')).toBeInTheDocument()
  expect(screen.getByText('Historical observations · not a current quote')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: /Paper|Watch|Reject|Forecast/i })).not.toBeInTheDocument()
  expect(api.decisionPacket).not.toHaveBeenCalled(); expect(api.saveDecisionPacket).not.toHaveBeenCalled()
})
it('rejects unzoned/future input locally, keeps explicit offset and never adds a workspace anchor', async () => {
  mount(); const input = await open()
  for (const value of ['2026-10-23T23:44:01', '2999-01-01T00:00:00Z']) {
    submit(input, value)
    await screen.findByRole('alert'); expect(api.historyInspection).not.toHaveBeenCalled()
  }
  submit(input, '2026-10-24T07:44:01+08:00'); await screen.findByTestId('inspection-bars')
  expect(api.historyInspection).toHaveBeenLastCalledWith('hyperliquid', 'BTC', '2026-10-24T07:44:01+08:00', expect.any(AbortSignal))
  expect(vi.mocked(api.instrumentWorkspace).mock.calls.every(call => call.length === 4)).toBe(true)
})
it('clears the prior chart on edit and shows an honest unavailable result', async () => {
  mount(); const input = await open(); submit(input); await screen.findByTestId('inspection-bars')
  fireEvent.change(input, { target: { value: '2026-10-22T00:00:00Z' } })
  expect(screen.queryByTestId('inspection-bars')).not.toBeInTheDocument()
  vi.mocked(api.historyInspection).mockRejectedValue(new ApiError(404, 'historical inspection unavailable: no replay candles'))
  fireEvent.click(screen.getByRole('button', { name: 'Show saved day' }))
  await screen.findByRole('alert')
  expect(screen.getByText(/no replay candles/)).toBeInTheDocument()
  expect(screen.queryByTestId('inspection-bars')).not.toBeInTheDocument()
})
it('ignores a late response after changing the date and returning to current', async () => {
  let resolve!: (value: HistoricalInspection) => void
  vi.mocked(api.historyInspection).mockReturnValue(new Promise(done => { resolve = done }))
  mount(); const input = await open(); submit(input)
  await waitFor(() => expect(api.historyInspection).toHaveBeenCalledTimes(1))
  fireEvent.change(input, { target: { value: '2026-10-22T00:00:00Z' } })
  await act(async () => { resolve(sample) })
  expect(screen.queryByTestId('inspection-bars')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Return to current' }))
  await screen.findByRole('button', { name: 'View saved history' })
  expect(screen.queryByText('Historical observations · not a current quote')).not.toBeInTheDocument()
  expect(api.instrumentWorkspace).toHaveBeenLastCalledWith('hyperliquid', 'BTC', '1d', [])
})
it('does not offer inspection outside the approved private-minute scope', async () => {
  mount('/instruments/moomoo/SPY?range=1d')
  await waitFor(() => expect(api.health).toHaveBeenCalled())
  expect(screen.queryByRole('button', { name: 'View saved history' })).not.toBeInTheDocument()
  expect(api.historyInspection).not.toHaveBeenCalled()
})
it('keeps chart toggles local and functional without another saved-window read', async () => {
  mount(); const input = await open(); submit(input); await screen.findByTestId('inspection-bars')
  const volume = screen.getByRole('button', { name: 'Volume', exact: true })
  fireEvent.click(volume)
  expect(volume).toHaveAttribute('aria-pressed', 'true')
  fireEvent.click(screen.getByRole('button', { name: 'Candles', exact: true }))
  expect(screen.getByRole('button', { name: 'Candles', exact: true })).toHaveAttribute('aria-pressed', 'true')
  expect(api.historyInspection).toHaveBeenCalledTimes(1)
})
