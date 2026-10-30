import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { ResearchJobsScreen } from './ResearchJobs'
import { SpyReplayPanel } from './SpyReplayPanel'
import { spyReplayApi, SpyReplayError, type ReplayJob, type ReplayOptions, type ReplayReport } from '@/lib/spy-replay-api'
vi.mock('@/lib/api', () => ({ api: { researchJobOptions: vi.fn().mockResolvedValue({ status: 'unavailable', datasets: [], strategies: [] }) } }))
const preferences = vi.hoisted(() => ({ locale: 'en' as 'en' | 'zh-CN' }))
vi.mock('@/lib/preferences', () => ({ usePreferences: () => preferences }))
vi.mock('@/lib/spy-replay-api', async original => ({ ...await original<typeof import('@/lib/spy-replay-api')>(), spyReplayApi: { options: vi.fn(), get: vi.fn(), submit: vi.fn(), artifact: vi.fn(), decide: vi.fn() } }))
const id = '11111111-1111-4111-8111-111111111111'
const second = '22222222-2222-4222-8222-222222222222'
const pins = { snapshot_digest: 'a'.repeat(64), protocol_digest: 'b'.repeat(64) }
const storage = 'quantmesh.spy-replay.v1'
const at = '2026-10-25T00:00:00Z'
function job(state: ReplayJob['state'] = 'running'): ReplayJob { return { schema_version: 1, job_id: id, request_digest: 'c'.repeat(64), request: pins, state, created_at: at, updated_at: at, completed_at: state === 'running' ? null : at, report: state === 'succeeded' ? { algorithm: 'sha256', digest: 'd'.repeat(64), media_type: 'application/json', byte_length: 10 } : null, decision: null, decision_ref: null, error_code: null, financial_qualification: 'INSUFFICIENT', paper_allowed: false } }
function options(): ReplayOptions { return { schema_version: 1, configured: true, unavailable_reason: null, input: { ...pins, symbol: 'SPY', interval: '1d', as_of_utc: at, frozen_at_utc: at, warmup_start: '2026-04-29', observation_start: '2026-09-22', observation_end: '2026-10-20', evidence_kind: 'engineering_fixture', limitations: [] }, fixed: { strategy_id: 'SMA100-long-cash', warmup_sessions: 100, observation_sessions: 21, capital_usd: 100000, base_one_way_bps: 5, stress_one_way_bps: 10, cash_interest: 0, fee_spread_slippage_components: null }, limits: { max_jobs: 32, max_inflight: 1 }, financial_qualification: 'INSUFFICIENT', paper_allowed: false } }
function report(): ReplayReport { const metrics = { sessions: 21 as const, terminal_equity: 99900, total_return: -0.001, max_drawdown: -0.001, friction_usd: 100, fills: 2, cagr: null, annualized_volatility: null, naive_sharpe_rf_zero: null, sortino_target_zero: null, calmar: null }; const track = { metrics, daily: [], trades: [] }; const scenario = { strategy: track, buyhold: track, comparison: { terminal_equity_difference_usd: -10, total_return_difference: -0.0001 } }; return { schema_version: 1, job_id: id, request_digest: 'c'.repeat(64), ...pins, evidence_kind: 'engineering_fixture', window: { warmup_start: '2026-04-29', score_start: '2026-09-22', score_end: '2026-10-20' }, costs: { base_one_way_bps: 5, stress_one_way_bps: 10, fee_spread_slippage_components: null, reason: 'not_calibrated' }, calculation: { scenarios: { base5: { ...scenario, one_way_bps: 5 }, stress10: { ...scenario, one_way_bps: 10 } }, cash_benchmark: { capital_usd: 100000, terminal_equity: 100000, total_return: 0, max_drawdown: 0, interest_rate_assumed: 0, sessions: 21 } }, limitations: ['Engineering evidence only'], financial_qualification: 'INSUFFICIENT', paper_allowed: false } }
function retain() { localStorage.setItem(storage, JSON.stringify({ key: id, request: pins })) }
async function decisionStep() { const step = await screen.findByRole('button', { name: 'Decision' }); await waitFor(() => expect(step).toBeEnabled()); fireEvent.click(step) }
beforeEach(() => {
  vi.restoreAllMocks(); vi.clearAllMocks(); localStorage.clear(); history.replaceState(null, '', '/app/research/jobs'); preferences.locale = 'en'
  vi.mocked(spyReplayApi.options).mockResolvedValue(options()); vi.mocked(spyReplayApi.get).mockResolvedValue(job())
  vi.mocked(spyReplayApi.submit).mockImplementation(async key => ({ ...job(), job_id: key }))
  vi.mocked(spyReplayApi.artifact).mockResolvedValue({ bytes: new Uint8Array(10), digest: 'd'.repeat(64), value: report() as unknown as Record<string, unknown> })
})
it('offers the dedicated fixed SPY historical replay alongside existing engines', () => {
  render(<ResearchJobsScreen />)
  expect(screen.getByRole('option', { name: 'SPY · SMA100 historical replay' })).toBeInTheDocument()
})
it('persists exact intent before POST, recovers a lost response with GET, and never auto-resubmits', async () => {
  let resolveOptions!: (value: ReplayOptions) => void
  vi.mocked(spyReplayApi.options).mockImplementation(() => new Promise(resolve => { resolveOptions = resolve }))
  vi.mocked(spyReplayApi.submit).mockImplementation(async (key, body) => {
    expect(JSON.parse(localStorage.getItem(storage)!)).toEqual({ key, request: body }); throw new SpyReplayError('request_failed')
  })
  const view = render(<SpyReplayPanel />)
  const start = await screen.findByRole('button', { name: 'Start fixed replay' })
  expect(start).toBeDisabled()
  resolveOptions(options())
  await waitFor(() => expect(start).toBeEnabled())
  fireEvent.click(start)
  await screen.findByRole('alert'); const saved = JSON.parse(localStorage.getItem(storage)!)
  expect(saved.request).toEqual(pins); expect(spyReplayApi.submit).toHaveBeenCalledTimes(1)
  view.unmount(); vi.mocked(spyReplayApi.get).mockResolvedValue({ ...job(), job_id: saved.key }); render(<SpyReplayPanel />)
  await waitFor(() => expect(spyReplayApi.get).toHaveBeenCalledWith(saved.key, pins))
  expect(await screen.findByText('Running', { exact: true })).toBeInTheDocument(); expect(spyReplayApi.submit).toHaveBeenCalledTimes(1)
})
it('refuses submission if the intent cannot be saved', async () => {
  render(<SpyReplayPanel />); const start = await screen.findByRole('button', { name: 'Start fixed replay' }); await waitFor(() => expect(start).toBeEnabled())
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') }); fireEvent.click(start)
  expect(await screen.findByRole('alert')).toHaveTextContent('No submission was sent'); expect(spyReplayApi.submit).not.toHaveBeenCalled()
})
it('cold opens the same ID from the URL even without current configured input', async () => {
  history.replaceState(null, '', `?engine=spy-replay&spy_job=${id}`)
  vi.mocked(spyReplayApi.options).mockResolvedValue({ ...options(), configured: false, input: null, unavailable_reason: 'not_configured' })
  render(<SpyReplayPanel />); expect(await screen.findByText('Running', { exact: true })).toBeInTheDocument()
  expect(spyReplayApi.get).toHaveBeenCalledWith(id, undefined); expect(spyReplayApi.submit).not.toHaveBeenCalled()
})
it('shows GET not-found without starting or recomputing a job', async () => {
  retain(); vi.mocked(spyReplayApi.get).mockRejectedValue(new SpyReplayError('not_found', 404)); render(<SpyReplayPanel />)
  expect(await screen.findByRole('alert')).toHaveTextContent('No new request was sent'); expect(spyReplayApi.submit).not.toHaveBeenCalled()
  fireEvent.click(screen.getByRole('button', { name: 'Retry the saved request with the same key' })); await waitFor(() => expect(spyReplayApi.submit).toHaveBeenCalledWith(id, pins))
})
it('renders percent once, negative drawdown and null metrics without granting Paper', async () => {
  retain(); vi.mocked(spyReplayApi.get).mockResolvedValue(job('succeeded')); render(<SpyReplayPanel />)
  await screen.findByRole('button', { name: 'Download original report' }); expect(screen.getAllByText('-0.1%').length).toBeGreaterThan(0)
  expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0); expect(screen.queryByRole('button', { name: /Paper/i })).not.toBeInTheDocument()
  expect(screen.getAllByText('Engineering fixture · not real-data qualification').length).toBeGreaterThan(0)
})
it('saves and retries one exact decision bound to request and original report', async () => {
  retain(); vi.mocked(spyReplayApi.get).mockResolvedValue(job('succeeded')); vi.mocked(spyReplayApi.decide).mockRejectedValue(new SpyReplayError('request_failed'))
  render(<SpyReplayPanel />); await decisionStep(); const reason = await screen.findByLabelText('Reason'); await waitFor(() => expect(reason).toBeEnabled())
  fireEvent.change(reason, { target: { value: '  Need more independent observations  ' } }); fireEvent.click(screen.getByRole('radio', { name: 'Reject' })); fireEvent.click(screen.getByRole('button', { name: 'Record final decision' }))
  await screen.findByRole('button', { name: 'Retry the saved decision' }); const saved = JSON.parse(localStorage.getItem(storage)!).decision
  expect(saved.body).toEqual({ request_digest: 'c'.repeat(64), report_digest: 'd'.repeat(64), disposition: 'reject', reason: 'Need more independent observations' })
  fireEvent.click(screen.getByRole('button', { name: 'Retry the saved decision' })); await waitFor(() => expect(spyReplayApi.decide).toHaveBeenCalledTimes(2))
  expect(vi.mocked(spyReplayApi.decide).mock.calls[1]?.slice(1)).toEqual(vi.mocked(spyReplayApi.decide).mock.calls[0]?.slice(1))
})
it('blocks decisions when original report verification fails', async () => {
  retain(); vi.mocked(spyReplayApi.get).mockResolvedValue(job('succeeded')); vi.mocked(spyReplayApi.artifact).mockRejectedValue(new SpyReplayError('artifact_invalid'))
  render(<SpyReplayPanel />); await screen.findByText('The original artifact could not be verified. Decision recording remains unavailable.')
  expect(screen.getByRole('button', { name: 'Decision' })).toBeDisabled(); expect(spyReplayApi.decide).not.toHaveBeenCalled()
})
it('ignores a delayed response from a previously opened ID', async () => {
  retain(); let finish!: (v: ReplayJob) => void; vi.mocked(spyReplayApi.get).mockImplementationOnce(() => new Promise(resolve => { finish = resolve })).mockResolvedValue({ ...job('interrupted'), job_id: second })
  render(<SpyReplayPanel />); fireEvent.change(screen.getByLabelText('Reopen by job ID'), { target: { value: second } }); fireEvent.click(screen.getByRole('button', { name: 'Open job' }))
  await screen.findByText('Interrupted · no automatic recomputation'); finish(job()); await waitFor(() => expect(screen.queryByText('Running', { exact: true })).not.toBeInTheDocument())
})
it('localizes the fixed loop in Chinese', async () => {
  preferences.locale = 'zh-CN'; render(<SpyReplayPanel />); expect(await screen.findByRole('heading', { name: 'SPY 历史回放' })).toBeInTheDocument()
  expect(await screen.findByRole('button', { name: '开始固定回放' })).toBeInTheDocument(); expect(screen.getByText('Paper 不可用 · 金融证据不足')).toBeInTheDocument()
})
it('can leave a definitively refused request for current pins while preserving its original intent', async () => {
  vi.mocked(spyReplayApi.submit).mockRejectedValue(new SpyReplayError('input_pin_mismatch', 422))
  const view = render(<SpyReplayPanel />); const start = await screen.findByRole('button', { name: 'Start fixed replay' }); await waitFor(() => expect(start).toBeEnabled()); fireEvent.click(start)
  await screen.findByRole('alert'); const original = JSON.parse(localStorage.getItem(storage)!)
  view.unmount(); const nextPins = { ...pins, snapshot_digest: 'e'.repeat(64) }
  vi.mocked(spyReplayApi.options).mockResolvedValue({ ...options(), input: { ...options().input!, ...nextPins } }); vi.mocked(spyReplayApi.get).mockRejectedValue(new SpyReplayError('not_found', 404))
  render(<SpyReplayPanel />); const replace = await screen.findByRole('button', { name: 'Start with current configured input' }); await waitFor(() => expect(replace).toBeEnabled()); fireEvent.click(replace)
  await waitFor(() => expect(spyReplayApi.submit).toHaveBeenLastCalledWith(expect.any(String), nextPins))
  expect(vi.mocked(spyReplayApi.submit).mock.calls.at(-1)?.[0]).not.toBe(original.key)
  expect(JSON.parse(localStorage.getItem(`${storage}.${original.key}`)!).request).toEqual(pins)
})
it('explicitly separates current configuration from the reopened job input', async () => {
  retain(); vi.mocked(spyReplayApi.get).mockResolvedValue(job('succeeded'))
  vi.mocked(spyReplayApi.options).mockResolvedValue({ ...options(), input: { ...options().input!, snapshot_digest: 'e'.repeat(64), evidence_kind: 'reviewed_opend_freeze_v2', observation_start: '2026-10-01' } })
  render(<SpyReplayPanel />); await screen.findByRole('button', { name: 'Download original report' })
  fireEvent.click(screen.getByRole('button', { name: 'Input' }))
  expect(screen.getByRole('heading', { name: 'Configuration for the next replay' })).toBeInTheDocument()
  expect(screen.getByText('The opened report keeps its original input and dates.')).toBeInTheDocument()
  expect(screen.getAllByText('Engineering fixture · not real-data qualification').length).toBeGreaterThan(0)
})
it('clears a previous refusal before a same-key retry whose acknowledgement may be lost', async () => {
  vi.mocked(spyReplayApi.submit).mockRejectedValueOnce(new SpyReplayError('input_pin_mismatch', 422)).mockRejectedValueOnce(new SpyReplayError('request_failed'))
  const view = render(<SpyReplayPanel />); const start = await screen.findByRole('button', { name: 'Start fixed replay' }); await waitFor(() => expect(start).toBeEnabled()); fireEvent.click(start)
  await screen.findByRole('button', { name: 'Start with current configured input' }); fireEvent.click(screen.getByRole('button', { name: 'Retry the saved request with the same key' }))
  await waitFor(() => expect(spyReplayApi.submit).toHaveBeenCalledTimes(2))
  expect(JSON.parse(localStorage.getItem(storage)!)).not.toHaveProperty('refused')
  view.unmount(); vi.mocked(spyReplayApi.get).mockRejectedValue(new SpyReplayError('not_found', 404)); render(<SpyReplayPanel />); await screen.findByRole('alert')
  expect(screen.queryByRole('button', { name: 'Start with current configured input' })).not.toBeInTheDocument()
})
it('keeps a conflicting decision pending until GET reveals the original immutable record', async () => {
  retain(); const ready = job('succeeded'); vi.mocked(spyReplayApi.get).mockResolvedValue(ready); vi.mocked(spyReplayApi.decide).mockRejectedValue(new SpyReplayError('decision_conflict', 409))
  render(<SpyReplayPanel />); await decisionStep(); const reason = await screen.findByLabelText('Reason'); await waitFor(() => expect(reason).toBeEnabled())
  fireEvent.change(reason, { target: { value: 'Pending choice' } }); fireEvent.click(screen.getByRole('button', { name: 'Record final decision' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('conflict'); expect(spyReplayApi.decide).toHaveBeenCalledTimes(1)
  const final = { ...ready, decision: { schema_version: 1 as const, decision_key: second, job_id: id, request_digest: ready.request_digest, ...pins, report_digest: ready.report!.digest, disposition: 'reject' as const, reason: 'Original immutable reason', created_at: at }, decision_ref: { ...ready.report!, digest: 'f'.repeat(64) } }
  vi.mocked(spyReplayApi.get).mockResolvedValue(final); fireEvent.click(screen.getByRole('button', { name: 'Read status with the same ID' }))
  await screen.findByText('Original immutable reason'); expect(screen.queryByRole('button', { name: 'Record final decision' })).not.toBeInTheDocument(); expect(screen.queryByRole('button', { name: 'Retry the saved decision' })).not.toBeInTheDocument()
})
it('focuses a completed replay on one report comparison and explicitly leads to its decision', async () => {
  retain(); vi.mocked(spyReplayApi.get).mockResolvedValue(job('succeeded')); render(<SpyReplayPanel />)
  await screen.findByRole('button', { name: 'Download original report' })
  expect(screen.getByRole('button', { name: 'Report' })).toHaveAttribute('aria-current', 'step')
  expect(screen.queryByRole('heading', { name: 'Configuration for the next replay' })).not.toBeInTheDocument()
  expect(screen.getAllByRole('table')).toHaveLength(1)
  expect(screen.queryByLabelText('Reason')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Continue to decision' }))
  expect(screen.getByLabelText('Reason')).toBeInTheDocument()
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: 'Review report' }))
  expect(screen.getByRole('table')).toBeInTheDocument(); expect(spyReplayApi.submit).not.toHaveBeenCalled()
})
it('changes only the visible cost scenario while retaining the same-cost comparator', async () => {
  retain(); const r = report(); r.calculation.scenarios.stress10 = { ...r.calculation.scenarios.stress10, strategy: { ...r.calculation.scenarios.stress10.strategy, metrics: { ...r.calculation.scenarios.stress10.strategy.metrics, total_return: -0.02 } } }
  vi.mocked(spyReplayApi.get).mockResolvedValue(job('succeeded')); vi.mocked(spyReplayApi.artifact).mockResolvedValue({ bytes: new Uint8Array(10), digest: 'd'.repeat(64), value: r as unknown as Record<string, unknown> }); render(<SpyReplayPanel />)
  await screen.findByRole('button', { name: 'Download original report' }); fireEvent.click(screen.getByRole('button', { name: 'Stress · 10 bps one way' }))
  expect(within(screen.getByRole('table')).getByText('-2%')).toBeInTheDocument(); expect(within(screen.getByRole('table')).getByText('Buy-and-hold')).toBeInTheDocument()
  expect(spyReplayApi.get).toHaveBeenCalledTimes(1); expect(spyReplayApi.submit).not.toHaveBeenCalled(); expect(spyReplayApi.decide).not.toHaveBeenCalled()
})
it('does not move an explicitly selected view when a status refresh completes', async () => {
  retain(); render(<SpyReplayPanel />); await screen.findByText('Running', { exact: true })
  fireEvent.click(screen.getByRole('button', { name: 'Input' })); vi.mocked(spyReplayApi.get).mockResolvedValue(job('succeeded'))
  fireEvent.click(screen.getByRole('button', { name: 'Read status with the same ID' })); await screen.findByText('Report ready', { exact: true })
  expect(screen.getByRole('button', { name: 'Input' })).toHaveAttribute('aria-current', 'step'); expect(screen.queryByRole('table')).not.toBeInTheDocument()
})
it.each(['failed', 'interrupted'] as const)('cold reopens %s without automatic recomputation', async state => {
  retain(); vi.mocked(spyReplayApi.get).mockResolvedValue(job(state)); render(<SpyReplayPanel />)
  await screen.findByText(state === 'failed' ? 'Failed' : 'Interrupted · no automatic recomputation', { exact: true })
  expect(spyReplayApi.submit).not.toHaveBeenCalled(); expect(screen.queryByRole('button', { name: 'Record final decision' })).not.toBeInTheDocument()
})
