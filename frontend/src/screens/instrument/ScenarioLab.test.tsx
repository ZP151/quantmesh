import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { api, type DecisionPacket } from '@/lib/api'
import { PreferencesProvider } from '@/lib/preferences'
import { workspace } from './scenario-lab-fixture'
import { ScenarioLabWorkspace } from './ScenarioLab'

vi.mock('@/lib/api', async (original) => {
  const actual = await original<typeof import('@/lib/api')>()
  return { ...actual, api: { ...actual.api, instrumentWorkspace: vi.fn(), decisionPacket: vi.fn(), saveDecisionPacket: vi.fn(), applyDecisionPacketAction: vi.fn() } }
})
vi.mock('@/components/charts/InstrumentChart', () => ({
  InstrumentChart: ({ primary, forecast }: { primary: typeof workspace.history; forecast: { sessions: number } | null }) => (
    <div data-testid="chart">{primary.bars[0].close} observed / {forecast?.sessions ?? 'none'} forecast</div>
  ),
}))

function packet(horizon: 7 | 30 = 30): DecisionPacket {
  return {
    ...workspace.decision.draft,
    packet_id: `packet-${String(horizon).padStart(24, '0')}`,
    scenario_lab: { format_version: '1', selected_horizon: horizon, history: workspace.history,
      confidence: 'abstain', reasons: ['No calibrated forecast.'], policy_version: 'scenario-lab-v1' },
  }
}
function Location() { const location = useLocation(); return <output data-testid="location">{location.search}</output> }
function show(query = 'horizon=30&analysis=fresh') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}><PreferencesProvider><MemoryRouter initialEntries={[`/instruments/moomoo/NVDA?${query}`]}>
    <Location /><Routes><Route path="/instruments/:venue/:symbol" element={<ScenarioLabWorkspace />} /></Routes>
  </MemoryRouter></PreferencesProvider></QueryClientProvider>)
}
beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  vi.mocked(api.instrumentWorkspace).mockImplementation(async (_v, _s, _r, _c, horizon) => ({ ...workspace, decision: { draft: packet(horizon), latest: null } }))
})
it('puts the observed chart before evidence and collapsed decision controls', async () => {
  show()
  const chart = await screen.findByTestId('chart')
  expect(chart).toHaveTextContent('184 observed')
  expect(screen.getByText('Risk & decision').closest('details')).not.toHaveAttribute('open')
  expect(chart.compareDocumentPosition(screen.getByText('Risk & decision')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  expect(screen.getByRole('button', { name: '30 sessions' })).toHaveAttribute('aria-pressed', 'true')
  expect(api.instrumentWorkspace).toHaveBeenCalledWith('moomoo', 'NVDA', '6m', [], 30, undefined)
})
it('loads a saved chart snapshot without asking for current workspace data', async () => {
  const saved = packet(7)
  vi.mocked(api.decisionPacket).mockResolvedValue(saved)
  show(`packet=${saved.packet_id}&horizon=30`)
  expect(await screen.findByTestId('chart')).toHaveTextContent('184 observed')
  expect(screen.getByRole('button', { name: '7 sessions' })).toHaveAttribute('aria-pressed', 'true')
  expect(api.instrumentWorkspace).not.toHaveBeenCalled()
  expect(screen.getByText('Saved evidence')).toBeInTheDocument()
})
it('changes horizon without leaving old evidence actionable during the request', async () => {
  const user = userEvent.setup()
  show()
  await screen.findByTestId('chart')
  vi.mocked(api.instrumentWorkspace).mockImplementation(() => new Promise(() => {}))
  await user.click(screen.getByRole('button', { name: '7 sessions' }))
  await waitFor(() => expect(screen.queryByTestId('chart')).not.toBeInTheDocument())
  expect(screen.queryByText('Risk & decision')).not.toBeInTheDocument()
  expect(screen.getByTestId('location')).toHaveTextContent('horizon=7')
  expect(screen.getByRole('button', { name: '7 sessions' })).toHaveFocus()
})

it('pins an artifact in the URL and selects only that horizon from its evidence', async () => {
  const draft = packet(30)
  const evidence = { ...draft.evidence, forecast_artifact_id: 'forecast-exact', forecast_paths: ([7, 30] as const).map((sessions) => ({ sessions,
    points: [{ session: sessions, timestamp: '2026-10-12T04:00:00Z', p025: 10, p10: 20, p25: 30, p50: sessions === 30 ? 777 : 111, p75: 800, p90: 900, p975: 1000 }],
  })) }
  vi.mocked(api.instrumentWorkspace).mockResolvedValue({ ...workspace, decision: { draft: { ...draft, evidence }, latest: null } })
  show()
  expect(await screen.findByTestId('chart')).toHaveTextContent('30 forecast')
  expect(screen.getByText('$777.0000')).toBeInTheDocument()
  expect(screen.queryByText('$111.0000')).not.toBeInTheDocument()
  await waitFor(() => expect(screen.getByTestId('location')).toHaveTextContent('forecast=forecast-exact'))
  expect(api.instrumentWorkspace).toHaveBeenCalledTimes(1)
})

it('saves Watch with the displayed horizon and then replays the child snapshot', async () => {
  const user = userEvent.setup()
  const draft = packet(7)
  const child = { ...draft, packet_id: `packet-${'c'.repeat(24)}`, parent_packet_id: draft.packet_id, disposition: 'watch' as const, version: 2, operator_reason: 'Wait for evidence' }
  vi.mocked(api.saveDecisionPacket).mockResolvedValue(draft)
  vi.mocked(api.applyDecisionPacketAction).mockResolvedValue({ packet: child, proposal: null })
  show('horizon=7&analysis=fresh')
  await screen.findByTestId('chart')
  await user.click(screen.getByText('Risk & decision'))
  await user.type(await screen.findByLabelText('Decision reason'), 'Wait for evidence')
  await user.click(screen.getByRole('button', { name: 'Watch decision' }))
  await waitFor(() => expect(api.saveDecisionPacket).toHaveBeenCalledWith({ expected_packet_id: draft.packet_id, horizon: 7, forecast_id: undefined, selected_range: '6m', symbol: 'NVDA', venue: 'moomoo' }))
  expect(await screen.findByText('Saved evidence')).toBeInTheDocument()
  expect(screen.getByTestId('chart')).toHaveTextContent('184 observed')
  expect(screen.getByTestId('location')).toHaveTextContent(`packet=${child.packet_id}`)
})

it('keeps safe Watch available on saved evidence when current risk data is unavailable', async () => {
  const user = userEvent.setup()
  const base = packet(7)
  const saved = { ...base, scenario_lab: { ...base.scenario_lab!, confidence: 'qualified' as const, reasons: [] }, paper_capability: { allowed: true, blockers: [] } }
  vi.mocked(api.decisionPacket).mockResolvedValue(saved)
  vi.mocked(api.instrumentWorkspace).mockRejectedValue(new Error('offline'))
  show(`packet=${saved.packet_id}`)
  await screen.findByTestId('chart')
  await user.click(screen.getByText('Risk & decision'))
  await user.type(await screen.findByLabelText('Decision reason'), 'Wait for evidence')
  expect(screen.getByRole('button', { name: 'Watch decision' })).toBeEnabled()
  expect(screen.getByRole('button', { name: 'Create paper proposal' })).toBeDisabled()
  expect(screen.getByTestId('chart')).toHaveTextContent('184 observed')
})

it('retains the abstaining chart and safe actions when the pinned artifact is unavailable', async () => {
  const user = userEvent.setup()
  const draft = packet(30)
  vi.mocked(api.saveDecisionPacket).mockResolvedValue(draft)
  vi.mocked(api.applyDecisionPacketAction).mockResolvedValue({ packet: { ...draft, packet_id: `packet-${'e'.repeat(24)}`, parent_packet_id: draft.packet_id, disposition: 'watch', version: 2 }, proposal: null })
  show('horizon=30&analysis=fresh&forecast=forecast-missing')
  expect(await screen.findByTestId('chart')).toHaveTextContent('none forecast')
  await user.click(screen.getByText('Risk & decision'))
  await user.type(await screen.findByLabelText('Decision reason'), 'Await exact evidence')
  expect(screen.getByRole('button', { name: 'Watch decision' })).toBeEnabled()
  await user.click(screen.getByRole('button', { name: 'Watch decision' }))
  await waitFor(() => expect(api.saveDecisionPacket).toHaveBeenCalledWith(expect.objectContaining({ forecast_id: 'forecast-missing', horizon: 30 })))
})

it('continues to reject substitution with a different available artifact', async () => {
  const draft = packet(30)
  vi.mocked(api.instrumentWorkspace).mockResolvedValue({ ...workspace, decision: { draft: { ...draft, evidence: { ...draft.evidence, forecast_artifact_id: 'forecast-other' } }, latest: null } })
  show('horizon=30&analysis=fresh&forecast=forecast-exact')
  expect(await screen.findByRole('alert')).toHaveTextContent('does not match')
  expect(screen.queryByTestId('chart')).not.toBeInTheDocument()
})

it('shows material Paper blockers before opening risk details', async () => {
  show()
  await screen.findByTestId('chart')
  expect(screen.getByText('No promoted artifact for this range.')).toBeVisible()
})

it('shows unavailable metrics in all zero-sample disclosure rows', async () => {
  const user = userEvent.setup()
  const draft = packet(7)
  const metrics = ([7, 30] as const).map((sessions) => ({ sessions, mae: 12345, rmse: 23456, benchmark_mae: 34567,
    coverage_50: 0.5, coverage_80: 0.8, coverage_95: 0.95, residual_count: 0, interval_test_count: 0,
    validation_start: null, validation_end: null, test_start: null, test_end: null }))
  vi.mocked(api.instrumentWorkspace).mockResolvedValue({ ...workspace, decision: { draft: { ...draft, evidence: { ...draft.evidence, forecast_metrics: metrics } }, latest: null } })
  show('horizon=7&analysis=fresh')
  await screen.findByTestId('chart')
  await user.click(screen.getByText('Model & evidence details'))
  expect(screen.queryByText('12,345')).not.toBeInTheDocument()
  expect(screen.queryByText('23,456')).not.toBeInTheDocument()
  expect(screen.queryByText('34,567')).not.toBeInTheDocument()
  expect(screen.queryByText('50% / 80% / 95%')).not.toBeInTheDocument()
})

it('renders Chinese horizon controls and confidence semantics', async () => {
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN', theme: 'dark' }))
  show()
  await screen.findByTestId('chart')
  expect(screen.getByRole('button', { name: '30 个交易日' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByText('风险与决策')).toBeInTheDocument()
  expect(screen.getByText(/经验区间不是盈利概率/)).toBeInTheDocument()
})
it('refuses a saved packet for a different instrument instead of showing another chart', async () => {
  const saved = { ...packet(), instrument: { ...workspace.instrument, symbol: 'AAPL' } }
  vi.mocked(api.decisionPacket).mockResolvedValue(saved)
  show(`packet=${saved.packet_id}`)
  expect(await screen.findByRole('alert')).toHaveTextContent('This saved evidence does not match the instrument.')
  expect(screen.queryByTestId('chart')).not.toBeInTheDocument()
  expect(api.instrumentWorkspace).not.toHaveBeenCalled()
})
