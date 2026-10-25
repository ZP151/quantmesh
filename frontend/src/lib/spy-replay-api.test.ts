import { afterEach, expect, it, vi } from 'vitest'
import { spyReplayApi, replayReport, type ReplayJob, type ReplayDecision } from './spy-replay-api'
const id = '11111111-1111-4111-8111-111111111111'
const key = '22222222-2222-4222-8222-222222222222'
const pins = { snapshot_digest: 'a'.repeat(64), protocol_digest: 'b'.repeat(64) }
const at = '2026-10-25T00:00:00Z'
function record(): ReplayJob { return { schema_version: 1, job_id: id, request_digest: 'c'.repeat(64), request: pins, state: 'running', created_at: at, updated_at: at, completed_at: null, report: null, decision: null, decision_ref: null, error_code: null, financial_qualification: 'INSUFFICIENT', paper_allowed: false } }
function report() { const metrics = { sessions: 21, terminal_equity: 99900, total_return: -0.001, max_drawdown: -0.001, friction_usd: 100, fills: 2, cagr: null, annualized_volatility: null, naive_sharpe_rf_zero: null, sortino_target_zero: null, calmar: null }; const track = { metrics, daily: [], trades: [] }; const scenario = { strategy: track, buyhold: track, comparison: { terminal_equity_difference_usd: 0, total_return_difference: 0 } }; return { schema_version: 1, job_id: id, request_digest: 'c'.repeat(64), ...pins, evidence_kind: 'engineering_fixture', window: { warmup_start: '2026-04-29', score_start: '2026-09-22', score_end: '2026-10-20' }, costs: { base_one_way_bps: 5, stress_one_way_bps: 10, fee_spread_slippage_components: null, reason: 'not_calibrated' }, calculation: { scenarios: { base5: { ...scenario, one_way_bps: 5 }, stress10: { ...scenario, one_way_bps: 10 } }, cash_benchmark: { capital_usd: 100000, terminal_equity: 100000, total_return: 0, max_drawdown: 0, interest_rate_assumed: 0, sessions: 21 } }, limitations: [], financial_qualification: 'INSUFFICIENT', paper_allowed: false } }
afterEach(() => vi.unstubAllGlobals())
it('sends only the frozen pins and uses the job ID as idempotency key', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json(record(), { status: 201 })); vi.stubGlobal('fetch', fetcher)
  await spyReplayApi.submit(id, { ...pins, path: '/private' } as typeof pins)
  expect(fetcher).toHaveBeenCalledWith('/api/research/spy-replay/jobs', expect.objectContaining({ method: 'POST', headers: expect.objectContaining({ 'Idempotency-Key': id }), body: JSON.stringify(pins), redirect: 'error' }))
})
it('rejects a substituted job or input rather than accepting a different run', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ ...record(), request: { ...pins, protocol_digest: 'd'.repeat(64) } })))
  await expect(spyReplayApi.get(id, pins)).rejects.toMatchObject({ code: 'invalid_response' })
})
it('does not put malformed IDs into paths and never exposes private error detail', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ detail: 'private /home/account/key' }, { status: 500 })); vi.stubGlobal('fetch', fetcher)
  await expect(spyReplayApi.get('../private')).rejects.toMatchObject({ code: 'invalid_request' }); expect(fetcher).not.toHaveBeenCalled()
  await expect(spyReplayApi.get(id)).rejects.toMatchObject({ code: 'request_failed', message: 'request_failed' })
})
it('verifies original artifact bytes, including length and digest', async () => {
  const bytes = new TextEncoder().encode(JSON.stringify(report()))
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('')
  const current = { ...record(), state: 'succeeded' as const, report: { algorithm: 'sha256' as const, digest, media_type: 'application/json' as const, byte_length: bytes.length } }
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Response(bytes, { headers: { 'X-Content-SHA256': digest } })))
  expect(Array.from((await spyReplayApi.artifact(current, 'report')).bytes)).toEqual(Array.from(bytes))
  await expect(spyReplayApi.artifact({ ...current, report: { ...current.report, byte_length: bytes.length - 1 } }, 'report')).rejects.toMatchObject({ code: 'artifact_invalid' })
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"original":false}', { headers: { 'X-Content-SHA256': digest } })))
  await expect(spyReplayApi.artifact(current, 'report')).rejects.toMatchObject({ code: 'artifact_invalid' })
})
it('keeps null metrics and negative drawdown, rejects report substitution or Paper authority', () => {
  expect(replayReport(report(), record()).calculation.scenarios.base5.strategy.metrics.cagr).toBeNull()
  expect(() => replayReport({ ...report(), job_id: key }, record())).toThrow('invalid_response')
  expect(() => replayReport({ ...report(), paper_allowed: true }, record())).toThrow('invalid_response')
})
it('checks decision bindings but accepts JSON object key order differences', async () => {
  const decision: ReplayDecision = { schema_version: 1, decision_key: key, job_id: id, request_digest: 'c'.repeat(64), ...pins, report_digest: 'd'.repeat(64), disposition: 'watch', reason: 'Review after more observations', created_at: at }
  const bytes = new TextEncoder().encode(JSON.stringify(Object.fromEntries(Object.entries(decision).reverse())))
  const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), b => b.toString(16).padStart(2, '0')).join('')
  const current: ReplayJob = { ...record(), state: 'succeeded', report: { algorithm: 'sha256', digest: 'd'.repeat(64), media_type: 'application/json', byte_length: 10 }, decision, decision_ref: { algorithm: 'sha256', digest, media_type: 'application/json', byte_length: bytes.length } }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(bytes, { headers: { 'X-Content-SHA256': digest } })))
  expect((await spyReplayApi.artifact(current, 'decision')).value.reason).toBe(decision.reason)
  await expect(spyReplayApi.decide(current, key, { request_digest: current.request_digest, report_digest: 'e'.repeat(64), disposition: 'reject', reason: 'Mismatch' })).rejects.toMatchObject({ code: 'invalid_request' })
})
it('does not treat a decision response without the exact saved final record as acknowledgement', async () => {
  const current: ReplayJob = { ...record(), state: 'succeeded', report: { algorithm: 'sha256', digest: 'd'.repeat(64), media_type: 'application/json', byte_length: 10 } }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json(current, { status: 201 })))
  await expect(spyReplayApi.decide(current, key, { request_digest: current.request_digest, report_digest: current.report!.digest, disposition: 'watch', reason: 'Observe more sessions' })).rejects.toMatchObject({ code: 'invalid_response' })
})
