// Dedicated five-operation contract frozen by the backend owner. No uploaded
// paths, user code, arbitrary parameters or fixture-authority flags are sent.
export type ReplayRequest = { snapshot_digest: string; protocol_digest: string }
export type ReplayObject = { algorithm: 'sha256'; digest: string; media_type: 'application/json'; byte_length: number }
export type ReplayInput = ReplayRequest & { symbol: 'SPY'; interval: '1d'; as_of_utc: string; frozen_at_utc: string;
  warmup_start: string; observation_start: string; observation_end: string;
  evidence_kind: 'reviewed_opend_freeze_v2' | 'engineering_fixture'; limitations: string[] }
export type ReplayOptions = { schema_version: 1; configured: boolean; unavailable_reason: string | null; input: ReplayInput | null;
  fixed: { strategy_id: 'SMA100-long-cash'; warmup_sessions: 100; observation_sessions: 21; capital_usd: 100000;
    base_one_way_bps: 5; stress_one_way_bps: 10; cash_interest: 0; fee_spread_slippage_components: null };
  limits: { max_jobs: 32; max_inflight: 1 }; financial_qualification: 'INSUFFICIENT'; paper_allowed: false }
export type ReplayDecision = { schema_version: 1; decision_key: string; job_id: string; request_digest: string;
  snapshot_digest: string; protocol_digest: string; report_digest: string; disposition: 'reject' | 'watch'; reason: string; created_at: string }
export type ReplayJob = { schema_version: 1; job_id: string; request_digest: string; request: ReplayRequest;
  state: 'running' | 'succeeded' | 'failed' | 'interrupted'; created_at: string; updated_at: string; completed_at: string | null;
  report: ReplayObject | null; decision: ReplayDecision | null; decision_ref: ReplayObject | null;
  error_code: string | null; financial_qualification: 'INSUFFICIENT'; paper_allowed: false }
export type ReplayDecisionRequest = Pick<ReplayDecision, 'request_digest' | 'report_digest' | 'disposition' | 'reason'>
export type ReplayArtifact = { bytes: Uint8Array<ArrayBuffer>; value: Record<string, unknown>; digest: string }
export type ReplayMetrics = { sessions: 21; terminal_equity: number; total_return: number; max_drawdown: number; friction_usd: number; fills: number; cagr: number | null; annualized_volatility: number | null; naive_sharpe_rf_zero: number | null; sortino_target_zero: number | null; calmar: number | null }
export type ReplayScenario = { one_way_bps: 5 | 10; strategy: { metrics: ReplayMetrics; daily: Record<string, unknown>[]; trades: Record<string, unknown>[] }; buyhold: { metrics: ReplayMetrics; daily: Record<string, unknown>[]; trades: Record<string, unknown>[] }; comparison: { terminal_equity_difference_usd: number; total_return_difference: number } }
export type ReplayReport = { schema_version: 1; job_id: string; request_digest: string; snapshot_digest: string; protocol_digest: string; evidence_kind: ReplayInput['evidence_kind']; window: { warmup_start: string; score_start: string; score_end: string }; costs: { base_one_way_bps: 5; stress_one_way_bps: 10; fee_spread_slippage_components: null; reason: 'not_calibrated' }; calculation: { scenarios: { base5: ReplayScenario; stress10: ReplayScenario }; cash_benchmark: { capital_usd: 100000; terminal_equity: 100000; total_return: 0; max_drawdown: 0; interest_rate_assumed: 0; sessions: 21 } }; limitations: string[]; financial_qualification: 'INSUFFICIENT'; paper_allowed: false }
const prefix = '/api/research/spy-replay'
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v)
export const replayUuid = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(v)
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v)
const text = (v: unknown): v is string => typeof v === 'string'
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(text)
const date = (v: unknown): v is string => text(v) && Number.isFinite(Date.parse(v))
const same = (a: ReplayRequest, b: ReplayRequest) => a.snapshot_digest === b.snapshot_digest && a.protocol_digest === b.protocol_digest
export class SpyReplayError extends Error { status: number; code: string; constructor(code: string, status = 0) { super(code); this.status = status; this.code = code } }
function invalid(): never { throw new SpyReplayError('invalid_response') }
function pin(v: unknown): v is ReplayRequest { return object(v) && hash(v.snapshot_digest) && hash(v.protocol_digest) }
function ref(v: unknown): v is ReplayObject { return object(v) && v.algorithm === 'sha256' && hash(v.digest) && v.media_type === 'application/json' && Number.isSafeInteger(v.byte_length) && Number(v.byte_length) > 0 && Number(v.byte_length) <= 16 * 1024 * 1024 }
function decision(v: unknown, job: ReplayJob): v is ReplayDecision {
  return object(v) && v.schema_version === 1 && replayUuid(v.decision_key) && v.job_id === job.job_id && v.request_digest === job.request_digest
    && v.snapshot_digest === job.request.snapshot_digest && v.protocol_digest === job.request.protocol_digest && v.report_digest === job.report?.digest
    && ['reject', 'watch'].includes(String(v.disposition)) && text(v.reason) && v.reason.trim().length > 0 && v.reason.length <= 1000 && date(v.created_at)
}
function job(value: unknown, id: string, expected?: ReplayRequest): ReplayJob {
  if (!object(value) || value.schema_version !== 1 || value.job_id !== id || !hash(value.request_digest) || !pin(value.request)
    || (expected && !same(value.request, expected)) || !['running', 'succeeded', 'failed', 'interrupted'].includes(String(value.state))
    || !date(value.created_at) || !date(value.updated_at) || !(value.completed_at === null || date(value.completed_at))
    || !(value.report === null || ref(value.report)) || !(value.decision_ref === null || ref(value.decision_ref))
    || !(value.error_code === null || text(value.error_code)) || value.financial_qualification !== 'INSUFFICIENT' || value.paper_allowed !== false
    || (value.state === 'succeeded' && !ref(value.report)) || (!!value.decision_ref !== !!value.decision)) return invalid()
  const parsed = value as unknown as ReplayJob
  if (parsed.decision && !decision(parsed.decision, parsed)) return invalid()
  return parsed
}
function options(v: unknown): ReplayOptions {
  if (!object(v) || v.schema_version !== 1 || typeof v.configured !== 'boolean' || !(v.unavailable_reason === null || text(v.unavailable_reason))
    || !object(v.fixed) || v.fixed.strategy_id !== 'SMA100-long-cash' || v.fixed.warmup_sessions !== 100 || v.fixed.observation_sessions !== 21
    || v.fixed.capital_usd !== 100000 || v.fixed.base_one_way_bps !== 5 || v.fixed.stress_one_way_bps !== 10 || v.fixed.cash_interest !== 0
    || v.fixed.fee_spread_slippage_components !== null || !object(v.limits) || v.limits.max_jobs !== 32 || v.limits.max_inflight !== 1
    || v.financial_qualification !== 'INSUFFICIENT' || v.paper_allowed !== false) return invalid()
  const input = v.input
  if (input !== null && (!object(input) || input.symbol !== 'SPY' || input.interval !== '1d'
    || !date(input.as_of_utc) || !date(input.frozen_at_utc) || !date(input.warmup_start) || !date(input.observation_start) || !date(input.observation_end)
    || !['reviewed_opend_freeze_v2', 'engineering_fixture'].includes(String(input.evidence_kind)) || !strings(input.limitations) || !pin(input))) return invalid()
  if (v.configured && input === null) return invalid()
  return v as unknown as ReplayOptions
}
const errors = ['not_found','idempotency_conflict','decision_conflict','capacity_exceeded','job_not_succeeded','artifact_invalid','service_closed','invalid_request','input_not_qualified','input_pin_mismatch','paper_not_authorized','service_unavailable']
async function request(path: string, init?: RequestInit) {
  try {
    const response = await fetch(prefix + path, { ...init, mode: 'same-origin', credentials: 'same-origin', redirect: 'error', signal: AbortSignal.timeout(15000) })
    if (!response.ok) {
      let code = 'request_failed'
      try { const value: unknown = await response.json(); if (object(value) && errors.includes(String(value.detail))) code = String(value.detail) } catch { /* fixed fallback */ }
      throw new SpyReplayError(code, response.status)
    }
    return response
  } catch (cause) { if (cause instanceof SpyReplayError) throw cause; throw new SpyReplayError('request_failed') }
}
async function json(response: Response): Promise<unknown> { try { return await response.json() } catch { return invalid() } }
function requireId(id: string) { if (!replayUuid(id)) throw new SpyReplayError('invalid_request') }
export function replayReport(value: unknown, current: ReplayJob): ReplayReport {
  const finite = (v: unknown) => typeof v === 'number' && Number.isFinite(v)
  const metrics = (v: unknown) => object(v) && v.sessions === 21 && ['terminal_equity','total_return','max_drawdown','friction_usd','fills'].every(k => finite(v[k])) && Number(v.max_drawdown) <= 0
    && ['cagr','annualized_volatility','naive_sharpe_rf_zero','sortino_target_zero','calmar'].every(k => v[k] === null || finite(v[k]))
  const track = (v: unknown) => object(v) && metrics(v.metrics) && Array.isArray(v.daily) && v.daily.every(object) && Array.isArray(v.trades) && v.trades.every(object)
  const scenario = (v: unknown, bps: number) => object(v) && v.one_way_bps === bps && track(v.strategy) && track(v.buyhold) && object(v.comparison) && finite(v.comparison.terminal_equity_difference_usd) && finite(v.comparison.total_return_difference)
  if (!object(value) || value.schema_version !== 1 || value.job_id !== current.job_id || value.request_digest !== current.request_digest || value.snapshot_digest !== current.request.snapshot_digest || value.protocol_digest !== current.request.protocol_digest
    || !['engineering_fixture','reviewed_opend_freeze_v2'].includes(String(value.evidence_kind)) || value.financial_qualification !== 'INSUFFICIENT' || value.paper_allowed !== false || !strings(value.limitations)
    || !object(value.window) || !['warmup_start','score_start','score_end'].every(k => date((value.window as Record<string, unknown>)[k])) || !object(value.costs) || value.costs.base_one_way_bps !== 5 || value.costs.stress_one_way_bps !== 10 || value.costs.fee_spread_slippage_components !== null || value.costs.reason !== 'not_calibrated'
    || !object(value.calculation) || !object(value.calculation.scenarios) || !scenario(value.calculation.scenarios.base5, 5) || !scenario(value.calculation.scenarios.stress10, 10)
    || !object(value.calculation.cash_benchmark) || value.calculation.cash_benchmark.capital_usd !== 100000 || value.calculation.cash_benchmark.terminal_equity !== 100000 || value.calculation.cash_benchmark.total_return !== 0 || value.calculation.cash_benchmark.max_drawdown !== 0 || value.calculation.cash_benchmark.interest_rate_assumed !== 0 || value.calculation.cash_benchmark.sessions !== 21) return invalid()
  return value as unknown as ReplayReport
}
export const spyReplayApi = {
  async options(): Promise<ReplayOptions> { return options(await json(await request(''))) },
  async submit(id: string, body: ReplayRequest): Promise<ReplayJob> {
    requireId(id); if (!pin(body)) throw new SpyReplayError('invalid_request')
    return job(await json(await request('/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': id }, body: JSON.stringify({ snapshot_digest: body.snapshot_digest, protocol_digest: body.protocol_digest }) })), id, body)
  },
  async get(id: string, expected?: ReplayRequest): Promise<ReplayJob> { requireId(id); return job(await json(await request(`/jobs/${id}`)), id, expected) },
  async decide(current: ReplayJob, key: string, body: ReplayDecisionRequest): Promise<ReplayJob> {
    requireId(current.job_id); requireId(key)
    if (current.state !== 'succeeded' || !current.report || body.request_digest !== current.request_digest || body.report_digest !== current.report.digest
      || !['reject','watch'].includes(body.disposition) || !body.reason.trim() || body.reason.length > 1000) throw new SpyReplayError('invalid_request')
    const result = job(await json(await request(`/jobs/${current.job_id}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': key }, body: JSON.stringify({ request_digest: body.request_digest, report_digest: body.report_digest, disposition: body.disposition, reason: body.reason }) })), current.job_id, current.request)
    if (!result.decision || result.decision.decision_key !== key || result.decision.disposition !== body.disposition || result.decision.reason !== body.reason || result.decision.report_digest !== body.report_digest || result.request_digest !== body.request_digest) return invalid()
    return result
  },
  async artifact(current: ReplayJob, kind: 'report' | 'decision'): Promise<ReplayArtifact> {
    requireId(current.job_id); const expected = kind === 'report' ? current.report : current.decision_ref
    if (!expected) throw new SpyReplayError('artifact_invalid')
    const response = await request(`/jobs/${current.job_id}/artifact?kind=${kind}`)
    if (response.headers.get('X-Content-SHA256') !== expected.digest) throw new SpyReplayError('artifact_invalid')
    const reader = response.body?.getReader(); if (!reader) throw new SpyReplayError('artifact_invalid')
    const chunks: Uint8Array<ArrayBuffer>[] = []; let length = 0
    try {
      for (;;) { const { done, value } = await reader.read(); if (done) break; length += value.byteLength
        if (length > expected.byte_length) { await reader.cancel(); throw new SpyReplayError('artifact_invalid') }
        chunks.push(new Uint8Array(value)) }
      if (length !== expected.byte_length) throw new SpyReplayError('artifact_invalid')
      const bytes = new Uint8Array(length); let offset = 0; for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength }
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)), byte => byte.toString(16).padStart(2,'0')).join('')
      if (digest !== expected.digest) throw new SpyReplayError('artifact_invalid')
      const value: unknown = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); if (!object(value)) throw new SpyReplayError('artifact_invalid')
      if (kind === 'report') replayReport(value, current)
      if (kind === 'decision' && (!decision(value, current) || !current.decision || Object.keys(current.decision).some(key => value[key] !== current.decision?.[key as keyof ReplayDecision]))) throw new SpyReplayError('artifact_invalid')
      return { bytes, value, digest }
    } catch (cause) { if (cause instanceof SpyReplayError) throw cause; throw new SpyReplayError('artifact_invalid') }
    finally { reader.releaseLock() }
  },
}
