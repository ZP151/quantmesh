// Controlled UI fixtures only; no data qualification or financial execution.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { SpyReplayPanel } from './SpyReplayPanel'
import { spyReplayApi, type ReplayJob, type ReplayOptions } from '@/lib/spy-replay-api'
vi.mock('@/lib/preferences', () => ({ usePreferences: () => ({ locale: 'en' }) }))
vi.mock('@/lib/spy-replay-api', async original => ({ ...await original<typeof import('@/lib/spy-replay-api')>(), spyReplayApi: { options: vi.fn(), get: vi.fn(), submit: vi.fn(), artifact: vi.fn(), decide: vi.fn() } }))
const scope = 'ff2d3886c07504854a6ece89f4029177d51182eb7f99b33354b6268610b9b2c9'
const policy = '91cf0c560cadab5f80a3421604fa90b0ad5e7dc6b7ae5492058cb4013f2ccd36'
const proposal = 'aafd036f8e5402a14cb0c2a85421a27ab98cc69180e693c6ab8d4f8bbd7ead13'
const id = '890ab692-fbfc-5547-963a-9d53babce592'
const at = '2026-10-21T16:00:00Z'
const pins = { snapshot_digest: 'a'.repeat(64), protocol_digest: 'b'.repeat(64) }
const ref = (digest: string, media_type = 'application/json') => ({ algorithm: 'sha256', digest, media_type, byte_length: 100 })
function binding() { return { schema_version: 3, policy_status: 'POLICY_EXCEPTION_ONCE', internal_once_exception: 'HUMAN_APPROVED', provider_permission_verified: false, internal_decision: 'APPROVE_ONCE_PRIVATE_DIAGNOSTIC_EXCEPTION', external_api_storage_applicability: 'UNKNOWN', diagnostic_status: 'diagnostic_only_under_policy_exception', scope: 'US.SPY/1d/private_research', once_scope_id: scope, proposal_sha256: proposal, capture_intent_id: '11111111-1111-4111-8111-111111111111', job_idempotency_key: id, window_sha256: 'c'.repeat(64), output_root_sha256: 'd'.repeat(64), authority_root_sha256: 'e'.repeat(64), human_approval_ref: ref(scope), policy_document_ref: ref(policy, 'text/markdown') } }
const job: ReplayJob = { schema_version: 1, job_id: id, request_digest: 'c'.repeat(64), request: pins, state: 'succeeded', created_at: at, updated_at: at, completed_at: at, report: ref('d'.repeat(64)) as ReplayJob['report'], decision: null, decision_ref: null, error_code: null, financial_qualification: 'INSUFFICIENT', paper_allowed: false }
function report() {
  const unknown = { value: null, status: 'unknown', reason: 'not_established' }
  const recorded = (value: string) => ({ value, status: 'recorded', reason: null })
  const proofs = { 'human-approval.json': ref(scope), 'source-use-policy.md': ref(policy, 'text/markdown'), 'capture-intent.json': ref('3'.repeat(64)), 'capture-authorization.json': ref('4'.repeat(64)), 'post-review.json': ref('5'.repeat(64)), 'acceptance.json': ref('6'.repeat(64)), 'freeze.json': ref(pins.snapshot_digest), 'protocol.json': ref(pins.protocol_digest) }
  const sample = { schema_version: 2, ...pins, evidence_kind: 'reviewed_opend_policy_exception_once_v3', sample_id: 'SPY', sample_version: 'controlled-not-real', parent_version: null, purpose: 'historical_development_diagnostic', sample_role: 'historical_diagnostic', as_of_utc: at, frozen_at_utc: at, timestamp_basis: 'source_receipts', provider: 'opend', times: { requested_at_utc: recorded(at), received_at_utc: recorded(at), post_reviewed_at_utc: recorded(at), acceptance_reviewed_at_utc: recorded(at), available_at_utc: unknown }, refs: { freeze: proofs['freeze.json'], raw_capture: ref('7'.repeat(64)), authorization: proofs['capture-authorization.json'], post_review: proofs['post-review.json'], acceptance: proofs['acceptance.json'], normalized_bars: ref('8'.repeat(64), 'text/csv'), distributions: ref('9'.repeat(64)) }, source_facts: { source_use: recorded('POLICY_EXCEPTION_ONCE'), allowed_use: recorded('US.SPY/1d/private_research'), pit: unknown, revision_status: unknown, price_adjustment: recorded('raw'), currency: recorded('USD'), volume_unit: recorded('shares'), dividend_unit: recorded('USD/share'), action_coverage: recorded('complete_for_locked_window') }, review_hashes: { action_coverage_sha256: '1'.repeat(64), field_semantics_sha256: '2'.repeat(64), independent_input_review_sha256: '3'.repeat(64) }, quality: { rows: 121, warmup_sessions: 100, observation_sessions: 21, missing_sessions: 0, duplicate_sessions: 0, ordered_sessions_match: true, ohlcv_checked: true, structural_status: 'PASS' }, calendar: { calendar_id: 'XNYS', calendar_version: 'exchange-calendars:4.13.2:XNYS', source_grace_minutes: 30, last_session: '2026-10-20' }, exposure_status: 'historical_exposed_not_independent_oos', first_viewed_at_utc: unknown, trial_count: null, trial_count_reason: 'trial_history_unavailable', last_checked_at_utc: at, check_scope: 'structural_bytes_and_receipt_bindings', next_trigger: 'new_qualified_frozen_version', policy_exception: binding(), capture_intent_ref: proofs['capture-intent.json'], proof_refs: proofs }
  const metrics = { sessions: 21, terminal_equity: 100000, total_return: 0, max_drawdown: 0, friction_usd: 0, fills: 0, cagr: null, annualized_volatility: null, naive_sharpe_rf_zero: null, sortino_target_zero: null, calmar: null }
  const track = { metrics, daily: [], trades: [] }; const scenario = { strategy: track, buyhold: track, comparison: { terminal_equity_difference_usd: 0, total_return_difference: 0 } }
  return { schema_version: 3, job_id: id, request_digest: job.request_digest, ...pins, evidence_kind: sample.evidence_kind, sample_evidence: sample, window: { warmup_start: '2026-04-29', score_start: '2026-09-22', score_end: '2026-10-20', as_of_utc: at, calendar_version: sample.calendar.calendar_version, source_grace_minutes: 30 }, costs: { base_one_way_bps: 5, stress_one_way_bps: 10, fee_spread_slippage_components: null, reason: 'not_calibrated' }, calculation: { scenarios: { base5: { ...scenario, one_way_bps: 5 }, stress10: { ...scenario, one_way_bps: 10 } }, cash_benchmark: { capital_usd: 100000, terminal_equity: 100000, total_return: 0, max_drawdown: 0, interest_rate_assumed: 0, sessions: 21 } }, limitations: ['Controlled parser test only'], financial_qualification: 'INSUFFICIENT', paper_allowed: false }
}

function options() { return { schema_version: 1, configured: true, unavailable_reason: null, input: { ...pins, symbol: 'SPY', interval: '1d', as_of_utc: at, frozen_at_utc: at, warmup_start: '2026-04-29', observation_start: '2026-09-22', observation_end: '2026-10-20', evidence_kind: 'reviewed_opend_policy_exception_once_v3', policy_exception: binding(), limitations: ['Controlled UI fixture only'] }, fixed: { strategy_id: 'SMA100-long-cash', warmup_sessions: 100, observation_sessions: 21, capital_usd: 100000, base_one_way_bps: 5, stress_one_way_bps: 10, cash_interest: 0, fee_spread_slippage_components: null }, limits: { max_jobs: 32, max_inflight: 1 }, financial_qualification: 'INSUFFICIENT', paper_allowed: false } as ReplayOptions }
beforeEach(() => {
  vi.clearAllMocks(); localStorage.clear(); history.replaceState(null, '', '?engine=spy-replay')
  vi.mocked(spyReplayApi.options).mockResolvedValue(options())
  vi.mocked(spyReplayApi.get).mockResolvedValue(job)
  vi.mocked(spyReplayApi.artifact).mockResolvedValue({ bytes: new Uint8Array(10), digest: 'd'.repeat(64), value: report() })
})
it('labels the saved v3 report as an internal exception and external applicability unknown', async () => {
  history.replaceState(null, '', `?engine=spy-replay&spy_job=${id}`)
  render(<SpyReplayPanel />)
  const card = await screen.findByRole('region', { name: "This report's sample" })
  expect(card).toHaveTextContent('Single-use internal policy exception')
  expect(card).toHaveTextContent('External API storage applicability: Unknown')
  expect(card).toHaveTextContent(scope)
  expect(card).not.toHaveTextContent('Provider permission verified')
  expect(spyReplayApi.submit).not.toHaveBeenCalled()
})
it('uses the one trusted job key and offers reopen instead of another opportunity', async () => {
  const failed: ReplayJob = { ...job, state: 'failed', report: null, error_code: 'computation_failed' }
  vi.mocked(spyReplayApi.submit).mockResolvedValue(failed); vi.mocked(spyReplayApi.get).mockResolvedValue(failed)
  render(<SpyReplayPanel />)
  fireEvent.click(await screen.findByRole('button', { name: 'Start or reopen this diagnostic' }))
  await waitFor(() => expect(spyReplayApi.submit).toHaveBeenCalledWith(id, pins))
  expect(screen.queryByRole('button', { name: 'Start another fixed replay' })).not.toBeInTheDocument()
  expect(await screen.findByRole('button', { name: 'Reopen this diagnostic' })).toBeInTheDocument()
})
it('never backfills an old saved report from current exception options', async () => {
  history.replaceState(null, '', `?engine=spy-replay&spy_job=${id}`)
  const original: Record<string, unknown> = { ...report(), schema_version: 1, evidence_kind: 'engineering_fixture' }
  delete original.sample_evidence
  vi.mocked(spyReplayApi.artifact).mockResolvedValue({ bytes: new Uint8Array(10), digest: 'd'.repeat(64), value: original })
  render(<SpyReplayPanel />)
  const card = await screen.findByRole('region', { name: "This report's sample" })
  expect(within(card).getByText('Legacy report · missing facts remain unknown')).toBeInTheDocument()
  expect(card).not.toHaveTextContent('Single-use internal policy exception')
  expect(card).not.toHaveTextContent(scope)
  expect(spyReplayApi.submit).not.toHaveBeenCalled()
})
