import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { SpyReplayPanel } from './SpyReplayPanel'
import { spyReplayApi, type ReplayJob, type ReplayOptions } from '@/lib/spy-replay-api'

vi.mock('@/lib/preferences', () => ({ usePreferences: () => ({ locale: 'en' }) }))
vi.mock('@/lib/spy-replay-api', async original => ({ ...await original<typeof import('@/lib/spy-replay-api')>(), spyReplayApi: { options: vi.fn(), get: vi.fn(), submit: vi.fn(), artifact: vi.fn(), decide: vi.fn() } }))
const id = '11111111-1111-4111-8111-111111111111'
const pins = { snapshot_digest: 'a'.repeat(64), protocol_digest: 'b'.repeat(64) }
const at = '2026-10-25T07:00:00Z'
function report() {
  const metrics = { sessions: 21, terminal_equity: 100000, total_return: 0, max_drawdown: 0, friction_usd: 0, fills: 0, long_entries: 0, gross_traded_notional_over_initial_capital: 0, cagr: null, annualized_volatility: null, naive_sharpe_rf_zero: null, sortino_target_zero: null, calmar: null }
  const track = { metrics, daily: [], trades: [] }
  const buyhold = { ...track, metrics: { ...metrics, terminal_equity: 99900, total_return: -0.001, max_drawdown: -0.001, friction_usd: 100, fills: 2, long_entries: 1, gross_traded_notional_over_initial_capital: 1.998 } }
  const scenario = { strategy: track, buyhold, comparison: { terminal_equity_difference_usd: 100, total_return_difference: 0.001 } }
  return { schema_version: 1, job_id: id, request_digest: 'c'.repeat(64), ...pins, evidence_kind: 'engineering_fixture', window: { warmup_start: '2026-04-29', score_start: '2026-09-22', score_end: '2026-10-20' }, costs: { base_one_way_bps: 5, stress_one_way_bps: 10, fee_spread_slippage_components: null, reason: 'not_calibrated' }, calculation: { scenarios: { base5: { ...scenario, one_way_bps: 5 }, stress10: { ...scenario, one_way_bps: 10 } }, cash_benchmark: { capital_usd: 100000, terminal_equity: 100000, total_return: 0, max_drawdown: 0, interest_rate_assumed: 0, sessions: 21 } }, limitations: ['Synthetic engineering only'], financial_qualification: 'INSUFFICIENT', paper_allowed: false }
}
const job: ReplayJob = { schema_version: 1, job_id: id, request_digest: 'c'.repeat(64), request: pins, state: 'succeeded', created_at: at, updated_at: at, completed_at: at, report: { algorithm: 'sha256', digest: 'd'.repeat(64), media_type: 'application/json', byte_length: 10 }, decision: null, decision_ref: null, error_code: null, financial_qualification: 'INSUFFICIENT', paper_allowed: false }
function evidence() {
  const na = { value: null, status: 'not_applicable', reason: 'synthetic_no_source_receipt' }
  return { schema_version: 1, ...pins, evidence_kind: 'engineering_fixture', sample_id: 'F0', sample_version: 'F0-v1', parent_version: null, purpose: 'fixed_engineering_regression', sample_role: 'fixed_golden', as_of_utc: at, frozen_at_utc: '2026-10-24T01:00:00Z', timestamp_basis: 'synthetic_declared', provider: 'synthetic', times: Object.fromEntries(['requested_at_utc','received_at_utc','post_reviewed_at_utc','acceptance_reviewed_at_utc','available_at_utc'].map(k => [k, na])), refs: Object.fromEntries(['freeze','raw_capture','authorization','post_review','acceptance','normalized_bars','distributions'].map(k => [k, null])), source_facts: Object.fromEntries(['source_use','allowed_use','pit','revision_status','price_adjustment','currency','volume_unit','dividend_unit','action_coverage'].map(k => [k, na])), review_hashes: { action_coverage_sha256: null, field_semantics_sha256: null, independent_input_review_sha256: null }, quality: { rows: 121, warmup_sessions: 100, observation_sessions: 21, missing_sessions: 0, duplicate_sessions: 0, ordered_sessions_match: true, ohlcv_checked: true, structural_status: 'PASS' }, calendar: { calendar_id: 'XNYS', calendar_version: 'exchange-calendars:4.13.2:XNYS', source_grace_minutes: 30, last_session: '2026-10-20' }, exposure_status: 'synthetic_not_oos', first_viewed_at_utc: { value: null, status: 'unknown', reason: 'first_view_not_recorded' }, trial_count: null, trial_count_reason: 'trial_history_unavailable', last_checked_at_utc: at, check_scope: 'structural_bytes_only', next_trigger: 'code_protocol_or_boundary_change' }
}
function v2() { const sample = { ...evidence(), as_of_utc: '2026-10-21T16:00:00Z' }; return { ...report(), schema_version: 2, window: { ...report().window, as_of_utc: sample.as_of_utc, calendar_version: 'exchange-calendars:4.13.2:XNYS', source_grace_minutes: 30 }, sample_evidence: sample } }
const readView = { read_at_utc: at, evaluated_snapshot_digest: pins.snapshot_digest, calendar_version: 'exchange-calendars:4.13.2:XNYS', source_grace_minutes: 30 as const, latest_complete_session: '2026-10-23', lag_complete_sessions: 3, applicability: 'fixed_regression_not_required' as const, reason: 'fixed_sample_no_daily_refresh' as const }
beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear(); history.replaceState(null, '', `?engine=spy-replay&spy_job=${id}`)
  vi.mocked(spyReplayApi.get).mockResolvedValue(job)
  vi.mocked(spyReplayApi.options).mockResolvedValue({ schema_version: 1, configured: true, input: { ...pins, snapshot_digest: 'e'.repeat(64), evidence_kind: 'reviewed_opend_freeze_v2', observation_end: '2030-01-01', frozen_at_utc: '2030-01-02T00:00:00Z' } } as ReplayOptions)
  vi.mocked(spyReplayApi.artifact).mockResolvedValue({ bytes: new Uint8Array(10), digest: 'd'.repeat(64), value: report() })
})
it('shows the old report sample identity and unknown evidence without substituting current input B', async () => {
  vi.mocked(spyReplayApi.get).mockResolvedValue({ ...job, sample_freshness_view: { ...readView, applicability: 'unknown', reason: 'legacy_sample_role_unknown' } })
  vi.mocked(spyReplayApi.artifact).mockResolvedValue({ bytes: new Uint8Array(10), digest: 'd'.repeat(64), value: { ...report(), window: { ...report().window, as_of_utc: '2026-10-21T16:00:00+00:00', calendar_version: 'exchange-calendars:4.13.2:XNYS', source_grace_minutes: 30 } } })
  render(<SpyReplayPanel />)
  const card = await screen.findByRole('region', { name: "This report's sample" })
  expect(within(card).getByText('2026-10-20')).toBeInTheDocument()
  expect(card).not.toHaveTextContent('2030-01-01'); expect(card).not.toHaveTextContent('2030-01-02')
  expect(card).toHaveTextContent('Legacy report · missing facts remain unknown')
  expect(card).toHaveTextContent('Unknown · legacy sample role not recorded')
  expect(card).toHaveTextContent('Latest completed session: 2026-10-23')
  expect(card).not.toHaveTextContent('3 completed sessions behind')
  fireEvent.click(within(card).getByText('Sample identity and evidence'))
  expect(card).toHaveTextContent(pins.snapshot_digest); expect(card).not.toHaveTextContent('e'.repeat(64))
  expect(within(card).getByText('Freeze time').nextElementSibling).toHaveTextContent('Unknown')
  expect(within(card).getByText('Structural checks').nextElementSibling).toHaveTextContent('Unknown')
  expect(spyReplayApi.submit).not.toHaveBeenCalled()
})
it('distinguishes no entries and zero nonannualized traded-notional ratio from undefined annualized ratios', async () => {
  render(<SpyReplayPanel />); await screen.findByRole('button', { name: 'Download original report' })
  const activity = screen.getByText(/Long entries: 0/)
  expect(activity).toHaveTextContent('Traded notional / initial capital: 0× (not annualized)')
  expect(screen.getByText(/Fills are not round trips or independent opportunities/)).toBeInTheDocument()
  const disclosure = screen.getByText('Annualized metrics and limitations')
  expect(disclosure.closest('details')).not.toHaveAttribute('open')
  fireEvent.click(disclosure)
  await waitFor(() => expect(screen.getAllByText('Unavailable').length).toBeGreaterThan(0))
})
it('separates immutable declared fixture evidence from its read-time no-refresh view', async () => {
  vi.mocked(spyReplayApi.get).mockResolvedValue({ ...job, sample_freshness_view: readView })
  vi.mocked(spyReplayApi.artifact).mockResolvedValue({ bytes: new Uint8Array(10), digest: 'd'.repeat(64), value: v2() })
  render(<SpyReplayPanel />); const card = await screen.findByRole('region', { name: "This report's sample" })
  expect(card).toHaveTextContent('Fixed engineering regression'); expect(card).toHaveTextContent('No daily refresh required')
  expect(card).not.toHaveTextContent('3 calendar days'); expect(card).not.toHaveTextContent('2030-01-02')
  fireEvent.click(within(card).getByText('Sample identity and evidence'))
  expect(card).toHaveTextContent('F0-v1'); expect(within(card).getByText('Freeze time · synthetic declaration').nextElementSibling).toHaveTextContent('2026-10-24T01:00:00Z')
  expect(within(card).getByText('Actual received time').nextElementSibling).toHaveTextContent('N/A · synthetic')
  expect(within(card).getByText('Structural checks').nextElementSibling).toHaveTextContent('121 rows')
  expect(within(card).getByText('Trial count').nextElementSibling).toHaveTextContent('Unknown')
})
it.each(['2026-10-24T18:00:00Z','2026-10-25T18:00:00Z'])('uses completed-session freshness from %s without a weekend calendar-day alarm', async readAt => {
  const real = v2(); real.evidence_kind = 'reviewed_opend_freeze_v2'; real.window.score_end = '2026-10-23'
  const unknown = { value: null, status: 'unknown', reason: 'not_recorded' }
  real.sample_evidence = { ...real.sample_evidence, sample_id: 'R0-test', sample_version: 'R0-test-v1', evidence_kind: 'reviewed_opend_freeze_v2', provider: 'opend', purpose: 'historical_development_diagnostic', sample_role: 'rolling_diagnostic', timestamp_basis: 'source_receipts', exposure_status: 'historical_exposed_not_independent_oos', calendar: { ...real.sample_evidence.calendar, last_session: '2026-10-23' }, times: Object.fromEntries(Object.keys(real.sample_evidence.times).map(k => [k, unknown])), source_facts: Object.fromEntries(Object.keys(real.sample_evidence.source_facts).map(k => [k, unknown])) }
  vi.mocked(spyReplayApi.get).mockResolvedValue({ ...job, sample_freshness_view: { ...readView, read_at_utc: readAt, lag_complete_sessions: 0, applicability: 'recent_diagnostic', reason: 'current' } })
  vi.mocked(spyReplayApi.artifact).mockResolvedValue({ bytes: new Uint8Array(10), digest: 'd'.repeat(64), value: real })
  render(<SpyReplayPanel />); const card = await screen.findByRole('region', { name: "This report's sample" })
  expect(card).toHaveTextContent('Latest completed session: 2026-10-23'); expect(card).not.toHaveTextContent('calendar days')
  expect(card).toHaveTextContent('Current for its recent-sample target')
})
it('ignores a freshness view tied to a different calendar instead of blending it into the original sample', async () => {
  vi.mocked(spyReplayApi.get).mockResolvedValue({ ...job, sample_freshness_view: { ...readView, calendar_version: 'foreign-calendar' } })
  vi.mocked(spyReplayApi.artifact).mockResolvedValue({ bytes: new Uint8Array(10), digest: 'd'.repeat(64), value: v2() })
  render(<SpyReplayPanel />); const card = await screen.findByRole('region', { name: "This report's sample" })
  expect(card).toHaveTextContent('Unknown · no bound read-time view'); expect(card).not.toHaveTextContent('No daily refresh required')
})
it('keeps missing calendar freshness unknown, rather than displaying zero age or replacing report metadata', async () => {
  vi.mocked(spyReplayApi.get).mockResolvedValue({ ...job, sample_freshness_view: { ...readView, calendar_version: null, latest_complete_session: null, lag_complete_sessions: null, applicability: 'unknown', reason: 'calendar_unavailable' } })
  vi.mocked(spyReplayApi.artifact).mockResolvedValue({ bytes: new Uint8Array(10), digest: 'd'.repeat(64), value: v2() })
  render(<SpyReplayPanel />); const card = await screen.findByRole('region', { name: "This report's sample" })
  expect(card).toHaveTextContent('Unknown · original calendar unavailable'); expect(card).not.toHaveTextContent('0 completed sessions')
})
