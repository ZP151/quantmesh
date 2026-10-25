import { afterEach, expect, it, vi } from 'vitest'
import { replayReport, spyReplayApi, type ReplayJob } from './spy-replay-api'

const pins = { snapshot_digest: 'a'.repeat(64), protocol_digest: 'b'.repeat(64) }
const id = '11111111-1111-4111-8111-111111111111'
const at = '2026-10-25T07:00:00Z'
const job: ReplayJob = { schema_version: 1, job_id: id, request_digest: 'c'.repeat(64), request: pins, state: 'succeeded', created_at: at, updated_at: at, completed_at: at, report: { algorithm: 'sha256', digest: 'd'.repeat(64), media_type: 'application/json', byte_length: 10 }, decision: null, decision_ref: null, error_code: null, financial_qualification: 'INSUFFICIENT', paper_allowed: false }
function report(metricsDelta: Record<string, unknown> = {}) {
  const metrics = { sessions: 21, terminal_equity: 100000, total_return: 0, max_drawdown: 0, friction_usd: 0, fills: 0, cagr: null, annualized_volatility: null, naive_sharpe_rf_zero: null, sortino_target_zero: null, calmar: null, ...metricsDelta }
  const track = { metrics, daily: [], trades: [] }; const scenario = { strategy: track, buyhold: track, comparison: { terminal_equity_difference_usd: 0, total_return_difference: 0 } }
  return { schema_version: 1, job_id: id, request_digest: 'c'.repeat(64), ...pins, evidence_kind: 'engineering_fixture', window: { warmup_start: '2026-04-29', score_start: '2026-09-22', score_end: '2026-10-20' }, costs: { base_one_way_bps: 5, stress_one_way_bps: 10, fee_spread_slippage_components: null, reason: 'not_calibrated' }, calculation: { scenarios: { base5: { ...scenario, one_way_bps: 5 }, stress10: { ...scenario, one_way_bps: 10 } }, cash_benchmark: { capital_usd: 100000, terminal_equity: 100000, total_return: 0, max_drawdown: 0, interest_rate_assumed: 0, sessions: 21 } }, limitations: [], financial_qualification: 'INSUFFICIENT', paper_allowed: false }
}
function sample() {
  const missing = { value: null, status: 'not_applicable', reason: 'synthetic_no_source_receipt' }
  return { schema_version: 1, ...pins, evidence_kind: 'engineering_fixture', sample_id: 'F0', sample_version: 'F0-v1', parent_version: null, purpose: 'fixed_engineering_regression', sample_role: 'fixed_golden', as_of_utc: at, frozen_at_utc: at, timestamp_basis: 'synthetic_declared', provider: 'synthetic', times: Object.fromEntries(['requested_at_utc','received_at_utc','post_reviewed_at_utc','acceptance_reviewed_at_utc','available_at_utc'].map(k => [k, missing])), refs: Object.fromEntries(['freeze','raw_capture','authorization','post_review','acceptance','normalized_bars','distributions'].map(k => [k, null])), source_facts: Object.fromEntries(['source_use','allowed_use','pit','revision_status','price_adjustment','currency','volume_unit','dividend_unit','action_coverage'].map(k => [k, missing])), review_hashes: { action_coverage_sha256: null, field_semantics_sha256: null, independent_input_review_sha256: null }, quality: { rows: 121, warmup_sessions: 100, observation_sessions: 21, missing_sessions: 0, duplicate_sessions: 0, ordered_sessions_match: true, ohlcv_checked: true, structural_status: 'PASS' }, calendar: { calendar_id: 'XNYS', calendar_version: 'exchange-calendars:4.13.2:XNYS', source_grace_minutes: 30, last_session: '2026-10-20' }, exposure_status: 'synthetic_not_oos', first_viewed_at_utc: { value: null, status: 'unknown', reason: 'first_view_not_recorded' }, trial_count: null, trial_count_reason: 'trial_history_unavailable', last_checked_at_utc: at, check_scope: 'structural_bytes_only', next_trigger: 'code_protocol_or_boundary_change' }
}
function v2() { return { ...report(), schema_version: 2, window: { ...report().window, as_of_utc: at, calendar_version: 'exchange-calendars:4.13.2:XNYS', source_grace_minutes: 30 }, sample_evidence: sample() } }
const freshness = { read_at_utc: at, evaluated_snapshot_digest: pins.snapshot_digest, calendar_version: 'exchange-calendars:4.13.2:XNYS', source_grace_minutes: 30, latest_complete_session: '2026-10-23', lag_complete_sessions: 3, applicability: 'fixed_regression_not_required', reason: 'fixed_sample_no_daily_refresh' }
afterEach(() => vi.unstubAllGlobals())
it('keeps legacy activity missing and defined zero distinct', () => {
  expect(replayReport(report(), job).calculation.scenarios.base5.strategy.metrics.long_entries).toBeUndefined()
  const zero = replayReport(report({ long_entries: 0, gross_traded_notional_over_initial_capital: 0 }), job)
  expect(zero.calculation.scenarios.base5.strategy.metrics.long_entries).toBe(0)
  expect(zero.calculation.scenarios.base5.strategy.metrics.gross_traded_notional_over_initial_capital).toBe(0)
})
it.each([{ long_entries: 0.5 }, { long_entries: -1 }, { long_entries: true }, { gross_traded_notional_over_initial_capital: -1 }, { gross_traded_notional_over_initial_capital: '0' }])('rejects malformed activity units %j before display', fields => {
  expect(() => replayReport(report(fields), job)).toThrow('invalid_response')
})
it('accepts bounded report-v2 evidence without replacing legacy v1 objects or hashes', () => {
  const legacy = report(); expect(replayReport(legacy, job)).toBe(legacy)
  expect(replayReport(v2(), job).sample_evidence?.sample_version).toBe('F0-v1')
})
it('preserves offset-bearing legacy as-of timestamps and the exact original report object', () => {
  const original = { ...report(), window: { ...report().window, as_of_utc: '2026-10-22T00:00:00+08:00' } }
  const bytesBefore = JSON.stringify(original)
  expect(replayReport(original, job)).toBe(original)
  expect(JSON.stringify(original)).toBe(bytesBefore)
})
it.each([
  { snapshot_digest: 'e'.repeat(64) }, { protocol_digest: 'e'.repeat(64) }, { evidence_kind: 'reviewed_opend_freeze_v2' },
  { frozen_at_utc: 'not-a-time' }, { sample_version: 'x'.repeat(81) }, { trial_count: 1 },
  { calendar: { ...sample().calendar, last_session: '2030-01-01' } },
  { refs: { ...sample().refs, raw_capture: { algorithm: 'sha256', digest: 'f'.repeat(64), media_type: 'application/json', byte_length: 8388609 } } },
  { refs: { ...sample().refs, freeze: { algorithm: 'sha256', digest: 'e'.repeat(64), media_type: 'application/json', byte_length: 100 } } },
  { quality: { ...sample().quality, missing_sessions: 1 } },
  { times: { ...sample().times, received_at_utc: { value: null, status: 'recorded', reason: null } } },
])('refuses v2 evidence that is not the original bound sample %j', delta => {
  expect(() => replayReport({ ...v2(), sample_evidence: { ...sample(), ...delta } }, job)).toThrow('invalid_response')
})
it('validates the GET-only view while leaving POST responses on the original job contract', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json({ ...job, sample_freshness_view: freshness })).mockResolvedValueOnce(Response.json(job, { status: 201 })); vi.stubGlobal('fetch', fetcher)
  expect((await spyReplayApi.get(id)).sample_freshness_view?.lag_complete_sessions).toBe(3)
  expect((await spyReplayApi.submit(id, pins)).job_id).toBe(id)
})
// Exact successful GET captured from the publisher's readonly8881 preview;
// missing legacy role does not erase a known lag from A's original window.
const actualLegacyRead = {"schema_version":1,"job_id":"37080fae-c01f-4ac3-988e-43c44ca0d8db","request_digest":"e8b0b2b72549aa916320b9897348e6253e681c8433c688ecfb22453bfe6d7558","request":{"snapshot_digest":"683ab1a12cef74aaf0dc34f6b90970fc7a9dba185ebed2c617a30c7091cb43e6","protocol_digest":"cb737650823a5fc1eed3b55e25c01a5d3e49f3ffe5ef000c669fcbac3345724e"},"state":"succeeded","created_at":"2026-10-25T06:29:23.260834Z","updated_at":"2026-10-25T06:29:24.201717Z","completed_at":"2026-10-25T06:29:23.381039Z","report":{"algorithm":"sha256","digest":"ee2445e78f8d67dfc30074a4c257387f881382fd8b56a8b63b19607dd858b472","media_type":"application/json","byte_length":54413},"decision":{"request_digest":"e8b0b2b72549aa916320b9897348e6253e681c8433c688ecfb22453bfe6d7558","report_digest":"ee2445e78f8d67dfc30074a4c257387f881382fd8b56a8b63b19607dd858b472","disposition":"watch","reason":"Engineering integration verified; independent real-data and financial qualification remain insufficient.","schema_version":1,"decision_key":"47b01e79-ef1d-4100-b61a-d334f1c3cfa4","job_id":"37080fae-c01f-4ac3-988e-43c44ca0d8db","snapshot_digest":"683ab1a12cef74aaf0dc34f6b90970fc7a9dba185ebed2c617a30c7091cb43e6","protocol_digest":"cb737650823a5fc1eed3b55e25c01a5d3e49f3ffe5ef000c669fcbac3345724e","created_at":"2026-10-25T06:29:24.196216Z"},"decision_ref":{"algorithm":"sha256","digest":"64014de96c909a5f9030f118660e0a47e42311eee7016da66bb654d0777b0d89","media_type":"application/json","byte_length":640},"error_code":null,"financial_qualification":"INSUFFICIENT","paper_allowed":false,"sample_freshness_view":{"read_at_utc":"2026-10-25T07:31:42.850703Z","evaluated_snapshot_digest":"683ab1a12cef74aaf0dc34f6b90970fc7a9dba185ebed2c617a30c7091cb43e6","calendar_version":"exchange-calendars:4.13.2:XNYS","source_grace_minutes":30,"latest_complete_session":"2026-10-23","lag_complete_sessions":3,"applicability":"unknown","reason":"legacy_sample_role_unknown"}}
it('reads the actual saved v1 job with unknown role and known original-window lag without losing its report or decision', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(actualLegacyRead)))
  const saved = await spyReplayApi.get(actualLegacyRead.job_id)
  expect(saved.state).toBe('succeeded')
  expect(saved.sample_freshness_view).toMatchObject({ evaluated_snapshot_digest: '683ab1a12cef74aaf0dc34f6b90970fc7a9dba185ebed2c617a30c7091cb43e6', lag_complete_sessions: 3, applicability: 'unknown', reason: 'legacy_sample_role_unknown' })
  expect(saved.report?.digest).toBe('ee2445e78f8d67dfc30074a4c257387f881382fd8b56a8b63b19607dd858b472')
  expect(saved.decision_ref?.digest).toBe('64014de96c909a5f9030f118660e0a47e42311eee7016da66bb654d0777b0d89')
  expect(saved.paper_allowed).toBe(false)
})
it.each([-1, 0.5, '3', true])('still rejects malformed lag %j on the actual unknown-role v1 GET', lag => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ ...actualLegacyRead, sample_freshness_view: { ...actualLegacyRead.sample_freshness_view, lag_complete_sessions: lag } })))
  return expect(spyReplayApi.get(actualLegacyRead.job_id)).rejects.toMatchObject({ code: 'invalid_response' })
})
it.each([
  { evaluated_snapshot_digest: 'e'.repeat(64) }, { lag_complete_sessions: -1 }, { lag_complete_sessions: 0.5 },
  { applicability: 'unknown', reason: 'current', lag_complete_sessions: 0 },
  { applicability: 'recent_diagnostic', reason: 'calendar_unavailable', lag_complete_sessions: 0 },
])('does not render an unbound or fabricated read-time age %j', delta => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ ...job, sample_freshness_view: { ...freshness, ...delta } })))
  return expect(spyReplayApi.get(id)).rejects.toMatchObject({ code: 'invalid_response' })
})
