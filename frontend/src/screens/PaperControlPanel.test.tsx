import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import { beforeEach, expect, it, vi } from 'vitest'
import { PreferencesProvider } from '@/lib/preferences'
import { PaperControlPanel } from './PaperControlPanel'
import { KillSwitchScreen } from './Ops'

const mocks = vi.hoisted(() => ({ status: vi.fn(), preflight: vi.fn(), transition: vi.fn(), download: vi.fn(), killSwitch: vi.fn() }))
vi.mock('@/lib/paper-controls-api', () => ({ paperControlsApi: mocks }))
vi.mock('@/lib/api', () => ({ api: { killSwitch: mocks.killSwitch }, ApiError: Error }))
const state = { synthetic: true, paper: true, paused: true, blocked: false, pause_reason: 'cold_start', checks: [],
  revision: 'a'.repeat(64), limits: { max_order_quantity: 2, max_notional: 500, max_position_quantity: 4 },
  costs: { fee_bps: 10, min_fee: 0, slippage_bps: 0 }, venue_stops: { moomoo: true }, history: [], last_receipt: null }
const receipt = { id: 'b'.repeat(64), action: 'resume', key: 'first', reason: 'Reviewed', requested_revision: state.revision,
  confirmation: true, target: null, boot: 'boot', configuration: 'c'.repeat(64), account_binding: 'd'.repeat(64),
  recorded_at: '2026-10-20T01:00:00Z', outcome: 'completed' }
function mount(onAvailabilityChange = vi.fn()) {
  return render(<PreferencesProvider><PaperControlPanel onAvailabilityChange={onAvailabilityChange} /></PreferencesProvider>)
}
beforeEach(() => {
  localStorage.clear(); vi.clearAllMocks()
  window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })
  mocks.status.mockResolvedValue(state); mocks.preflight.mockResolvedValue(state)
  mocks.killSwitch.mockResolvedValue({ kill_switch: true, kill_switches: {} })
  mocks.transition.mockResolvedValue({ receipt, replay: false, status: { ...state, paused: false } })
})

it('requires preflight, reason and explicit confirmation then sends that exact revision', async () => {
  mount(); await screen.findByText('Synthetic paper rehearsal')
  expect(screen.getByRole('button', { name: 'Resume paper orders' })).toBeDisabled()
  await userEvent.click(screen.getByRole('button', { name: 'Check resume evidence' }))
  await userEvent.type(screen.getByLabelText('Operator reason'), 'Reviewed')
  await userEvent.click(screen.getByLabelText(/I reviewed the current synthetic evidence/))
  await userEvent.click(screen.getByRole('button', { name: 'Resume paper orders' }))
  expect(mocks.transition).toHaveBeenCalledWith('resume', expect.objectContaining({ revision: state.revision,
    reason: 'Reviewed', confirmation: true, target: null }))
  expect(await screen.findByText('Paper orders allowed')).toBeInTheDocument()
})

it('refresh invalidates staged evidence and preserves venue stops', async () => {
  mount(); await screen.findByText('Synthetic paper rehearsal')
  expect(screen.getByText(/moomoo.*paused/i)).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Check resume evidence' }))
  await userEvent.type(screen.getByLabelText('Operator reason'), 'Checked')
  await userEvent.click(screen.getByLabelText(/I reviewed/))
  await userEvent.click(screen.getByRole('button', { name: 'Refresh current state' }))
  expect(screen.getByRole('button', { name: 'Resume paper orders' })).toBeDisabled()
})

it('shows blocked evidence and neutral missing configured thresholds', async () => {
  mocks.status.mockResolvedValue({ ...state, blocked: true, limits: null, checks: ['rehearsal_limits_missing_or_invalid'] })
  mount(); expect(await screen.findByText(/Configure all three positive rehearsal thresholds/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Resume paper orders' })).toBeDisabled()
})

it('replayed first resume receipt displays the current paused state', async () => {
  mocks.transition.mockResolvedValue({ receipt, replay: true, status: state })
  mount(); await screen.findByText('Synthetic paper rehearsal')
  await userEvent.type(screen.getByLabelText('Operator reason'), 'Pause now')
  await userEvent.click(screen.getByRole('button', { name: 'Pause paper orders' }))
  expect(await screen.findByText(/Original receipt replayed/)).toBeInTheDocument()
  expect(screen.getByText('Paper orders paused')).toBeInTheDocument()
})

it('busy actions prevent overlap and stale refusal invalidates confirmation', async () => {
  let reject!: (error: unknown) => void
  mocks.preflight.mockReturnValue(new Promise((_, fail) => { reject = fail }))
  mount(); await screen.findByText('Synthetic paper rehearsal')
  await userEvent.click(screen.getByRole('button', { name: 'Check resume evidence' }))
  expect(screen.getByRole('status')).toHaveTextContent('Checking current evidence')
  expect(screen.getByRole('button', { name: 'Refresh current state' })).toBeDisabled()
  await act(async () => reject({ code: 'stale_revision' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('State changed')
})

it('unavailable enables old-page fallback; other failures keep shortcuts hidden', async () => {
  const callback = vi.fn(); mocks.status.mockRejectedValue({ code: 'unavailable' })
  mount(callback); expect(await screen.findByText(/Paper controls are not configured/)).toBeInTheDocument()
  expect(callback).toHaveBeenCalledWith('unavailable')
})

it('keeps Chinese copy and reason field local to this panel', async () => {
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN' }))
  mount(); expect(await screen.findByText('合成纸面演练')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('操作原因'), { target: { value: '核对证据' } })
  expect(screen.getByRole('button', { name: '暂停纸面订单' })).toBeEnabled()
})

function mountPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(<QueryClientProvider client={client}><PreferencesProvider><KillSwitchScreen /></PreferencesProvider></QueryClientProvider>)
  return client
}

it.each(['configured', 'missing-caps', 'loading', 'error'])('uses verified-resume page copy in %s mode', async mode => {
  if (mode === 'missing-caps') mocks.status.mockResolvedValue({ ...state, limits: null, blocked: true, checks: ['rehearsal_limits_missing_or_invalid'] })
  if (mode === 'loading') mocks.status.mockReturnValue(new Promise(() => {}))
  if (mode === 'error') mocks.status.mockRejectedValue({ code: 'request_failed' })
  mountPage()
  expect(screen.getByText('Local synthetic paper controls. Pause new orders, check current evidence, and explicitly confirm a verified resume.')).toBeInTheDocument()
  if (mode === 'error') await screen.findByRole('alert')
  if (mode === 'configured') await screen.findByText('Paper orders paused')
  if (mode === 'missing-caps') await screen.findByRole('heading', { name: 'Paper orders blocked' })
  expect(screen.queryByText(/disarm always works/)).not.toBeInTheDocument()
})

it('uses local Chinese page copy', async () => {
  localStorage.setItem('quantmesh.preferences', JSON.stringify({ locale: 'zh-CN' }))
  const view = mountPage()
  expect(screen.getByText('本地合成纸面控制。暂停新订单、检查当前证据，并明确确认通过核验的恢复。')).toBeInTheDocument()
  await screen.findByText('纸面订单已暂停')
  view.clear()
})

it('retains the old page description after verified capability off', async () => {
  mocks.status.mockRejectedValue({ code: 'unavailable' }); mountPage()
  await screen.findByText(/Paper controls are not configured/)
  expect(screen.getByText(/disarm always works/)).toBeInTheDocument()
})

it('resumed but blocked evidence overrides the allowed headline and shows the separate pause bit', async () => {
  mocks.status.mockResolvedValue({ ...state, paused: false, blocked: true, checks: ['account_or_journal_invalid'] })
  mount()
  expect(await screen.findByRole('heading', { name: 'Paper orders blocked' })).toBeInTheDocument()
  expect(screen.queryByText('Paper orders allowed')).not.toBeInTheDocument()
  expect(screen.getByText('Global stop: disengaged')).toBeInTheDocument()
  expect(screen.getByText(/Account or order journal is missing/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Resume paper orders' })).toBeDisabled()
})

it('mirrors verified pause and resume state into the existing shell query cache', async () => {
  const client = mountPage()
  await screen.findByText('Paper orders paused')
  client.setQueryData(['kill-switch'], (previous: Record<string, unknown> | undefined) => ({
    ...previous, retained_marker: 'existing DTO field',
  }))
  await userEvent.click(screen.getByRole('button', { name: 'Check resume evidence' }))
  await userEvent.type(screen.getByLabelText('Operator reason'), 'Reviewed')
  await userEvent.click(screen.getByLabelText(/I reviewed/))
  await userEvent.click(screen.getByRole('button', { name: 'Resume paper orders' }))
  await screen.findByText('Paper orders allowed')
  await waitFor(() => expect(client.getQueryData(['kill-switch'])).toMatchObject({
    kill_switch: false, retained_marker: 'existing DTO field',
  }))
})
