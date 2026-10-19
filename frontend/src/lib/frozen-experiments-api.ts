/** One historical evidence adapter. Original Python/Markdown is download-only. */
export const MAX_FROZEN_BYTES = 8 * 1024 * 1024
const prefix = '/api/research/frozen-experiments'
const hash = /^[a-f0-9]{64}$/
export const CASE_IDS = ['final-base5bps', 'final-stress10bps', 'final-delay1session5bps', 'final-gross0bps',
  'development2020-base5bps', 'validation2022-base5bps', 'validation2023-base5bps', 'validation2024-base5bps'] as const
export const ARTIFACT_KINDS = ['archive', 'protocol', 'receipt', 'result', 'report', 'timeline', 'review', 'verification', 'manifest'] as const
export type ArtifactKind = typeof ARTIFACT_KINDS[number]
export type FrozenErrorCode = 'unavailable' | 'too_large' | 'invalid_archive' | 'snapshot_required' | 'not_found' | 'request_failed' | 'invalid_response' | 'integrity'
export class FrozenExperimentError extends Error {
  code: FrozenErrorCode
  status?: number
  constructor(code: FrozenErrorCode, status?: number) { super(code); this.code = code; this.status = status }
}
export type FrozenArtifact = { kind: ArtifactKind; sha256: string; bytes: number }
const metricKeys = ['sessions', 'terminal_equity', 'net_profit_usd', 'total_return', 'cagr', 'max_drawdown',
  'max_underwater_sessions', 'annualized_volatility', 'naive_sharpe_rf_zero', 'sortino_target_zero', 'calmar',
  'worst_day', 'historical_es_95', 'es_tail_observations', 'fills', 'long_entries', 'friction_usd',
  'dividend_earned_usd', 'dividend_paid_usd', 'terminal_receivable', 'gross_traded_notional_over_initial_capital',
  'capacity_clipped_sessions', 'terminal_shares'] as const
type MetricKey = typeof metricKeys[number]
export type FrozenMetrics = Record<MetricKey, number | null> & { start: string; end: string }
const inferenceKeys = ['block_sessions', 'resamples', 'seed', 'observations', 'mean_daily_difference',
  'one_sided_95_lower_daily', 'one_sided_95_upper_daily', 'annualized_arithmetic_difference'] as const
export type FrozenInference = Record<typeof inferenceKeys[number], number | null> & { method: string; not_a_probability_of_skill: true }
export type FrozenCase = { case_id: typeof CASE_IDS[number]; primary: boolean; strategy: FrozenMetrics;
  benchmark: FrozenMetrics; cash_benchmark_total_return: number | null; net_total_return_difference: number | null;
  inference: FrozenInference[] }
export type FrozenExperiment = {
  schema_version: 1; package_id: string; experiment_id: 'QM-REAL-ETF-001-D-20261018'; snapshot_id: string; imported_at: string;
  verification: { identities: 'VERIFIED'; economics: 'IMPORTED_NOT_RECOMPUTED'; chronology: 'UNVERIFIED' };
  proxy_verdict: 'REJECT'; formal_verdict: { R1: 'INSUFFICIENT'; R2: 'INSUFFICIENT'; R3: 'NOT_AUTHORIZED' };
  oos: { state: 'CONSUMED'; pristine_blind: false };
  trials: { current: 1; searched: 0; prior: null; source_exposure: true };
  protocol: { sha256: string; frozen_at_claimed: string; created_before_results_claimed: boolean;
    symbol: 'SPY'; lookback: 100; comparison: string; execution: string; final_window: [string, string]; capital_usd: number;
    costs: { single_side_proxy_bps: 5; stress_bps: 10; gross_diagnostic_bps: 0; extra_delay_stress_sessions: 1;
      fee_spread_slippage_breakdown: string; actual_nbbo_and_costs_verified: false } };
  data: { qualification: 'INSUFFICIENT'; evidence_kind: 'real_snapshot' | 'fixture'; rights: 'UNVERIFIED'; pit: 'UNVERIFIED';
    execution: 'UNVERIFIED'; dividend_conflict: { date: string; yahoo_usd: number; issuer_usd: number; resolution: string } };
  missing_evidence: string[]; cases: FrozenCase[];
  lineage: { path: string; sha256: string; bytes: number }[]; downloads: FrozenArtifact[];
}
function object(v: unknown): v is Record<string, unknown> { return v !== null && typeof v === 'object' && !Array.isArray(v) }
function text(v: unknown): v is string { return typeof v === 'string' && v.length > 0 && v.length <= 4096 }
function digest(v: unknown): v is string { return typeof v === 'string' && hash.test(v) }
function count(v: unknown): v is number { return Number.isSafeInteger(v) && Number(v) >= 0 }
function number(v: unknown) { return v === null || typeof v === 'number' && Number.isFinite(v) }
function metrics(v: unknown) { return object(v) && text(v.start) && text(v.end) && metricKeys.every(k => number(v[k])) }
function report(value: unknown): FrozenExperiment {
  const bad = () => { throw new FrozenExperimentError('invalid_response') }
  if (!object(value)) return bad()
  const v = value
  const p = v.protocol, d = v.data, t = v.trials, check = v.verification, verdict = v.formal_verdict, oos = v.oos
  if (v.schema_version !== 1 || !digest(v.package_id) || !digest(v.snapshot_id) || !text(v.imported_at)
    || v.experiment_id !== 'QM-REAL-ETF-001-D-20261018' || v.proxy_verdict !== 'REJECT'
    || !object(check) || check.identities !== 'VERIFIED' || check.economics !== 'IMPORTED_NOT_RECOMPUTED' || check.chronology !== 'UNVERIFIED'
    || !object(verdict) || verdict.R1 !== 'INSUFFICIENT' || verdict.R2 !== 'INSUFFICIENT' || verdict.R3 !== 'NOT_AUTHORIZED'
    || !object(oos) || oos.state !== 'CONSUMED' || oos.pristine_blind !== false
    || !object(t) || t.current !== 1 || t.searched !== 0 || t.prior !== null || t.source_exposure !== true
    || !object(p) || !digest(p.sha256) || !text(p.frozen_at_claimed) || typeof p.created_before_results_claimed !== 'boolean'
    || p.symbol !== 'SPY' || p.lookback !== 100 || !text(p.comparison) || !text(p.execution) || p.capital_usd !== 100000
    || !Array.isArray(p.final_window) || p.final_window.join(',') !== '2025-01-02,2026-10-16'
    || !object(p.costs) || p.costs.single_side_proxy_bps !== 5 || p.costs.stress_bps !== 10
    || p.costs.gross_diagnostic_bps !== 0 || p.costs.extra_delay_stress_sessions !== 1
    || p.costs.actual_nbbo_and_costs_verified !== false || !text(p.costs.fee_spread_slippage_breakdown)
    || !object(d) || d.qualification !== 'INSUFFICIENT' || !['real_snapshot', 'fixture'].includes(String(d.evidence_kind))
    || d.rights !== 'UNVERIFIED' || d.pit !== 'UNVERIFIED' || d.execution !== 'UNVERIFIED'
    || !object(d.dividend_conflict) || d.dividend_conflict.date !== '2021-12-17'
    || d.dividend_conflict.yahoo_usd !== 1.633 || d.dividend_conflict.issuer_usd !== 1.636431 || !text(d.dividend_conflict.resolution)
    || !Array.isArray(v.missing_evidence) || v.missing_evidence.length > 100 || !v.missing_evidence.every(text)
    || !Array.isArray(v.cases) || v.cases.length !== 8 || !v.cases.every((c, i) => object(c)
      && c.case_id === CASE_IDS[i] && c.primary === (i === 0) && metrics(c.strategy) && metrics(c.benchmark)
      && number(c.cash_benchmark_total_return) && number(c.net_total_return_difference)
      && Array.isArray(c.inference) && c.inference.length <= 3 && c.inference.every(n => object(n)
        && text(n.method) && n.not_a_probability_of_skill === true && inferenceKeys.every(k => number(n[k]))))
    || !Array.isArray(v.lineage) || v.lineage.length !== 46 || !v.lineage.every(f => object(f) && text(f.path) && digest(f.sha256) && count(f.bytes))
    || !Array.isArray(v.downloads) || v.downloads.length !== ARTIFACT_KINDS.length
    || !v.downloads.every((a, i) => object(a) && a.kind === ARTIFACT_KINDS[i] && digest(a.sha256) && count(a.bytes))) return bad()
  const result = v as unknown as FrozenExperiment
  if (result.downloads[0].sha256 !== result.package_id || result.downloads.find(a => a.kind === 'protocol')?.sha256 !== result.protocol.sha256) return bad()
  return result
}
function identifier(id: string) { if (!hash.test(id)) throw new FrozenExperimentError('invalid_response') }
async function request(path: string, init?: RequestInit): Promise<Response> {
  try {
    const response = await fetch(prefix + path, { ...init, credentials: 'same-origin', mode: 'same-origin', redirect: 'error', signal: AbortSignal.timeout(15000) })
    if (!response.ok) {
      let code: FrozenErrorCode = ({ 503: 'unavailable', 413: 'too_large', 422: 'invalid_archive', 404: 'not_found', 409: 'integrity' } as Record<number, FrozenErrorCode>)[response.status] ?? 'request_failed'
      if (response.status === 422) {
        try { if ((await response.json())?.detail === 'frozen_experiment_snapshot_required') code = 'snapshot_required' } catch { /* fixed fallback */ }
      }
      throw new FrozenExperimentError(code, response.status)
    }
    return response
  } catch (error) {
    if (error instanceof FrozenExperimentError) throw error
    throw new FrozenExperimentError('request_failed')
  }
}
async function bytes(response: Response, limit: number): Promise<Uint8Array<ArrayBuffer>> {
  if (!response.body) throw new FrozenExperimentError('integrity')
  const reader = response.body.getReader()
  const chunks: Uint8Array[] = []; let size = 0
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      size += value.byteLength
      if (size > limit) { await reader.cancel(); throw new FrozenExperimentError('integrity') }
      chunks.push(value)
    }
    const output = new Uint8Array(size); let offset = 0
    for (const chunk of chunks) { output.set(chunk, offset); offset += chunk.byteLength }
    return output
  } finally { reader.releaseLock() }
}
async function json(response: Response): Promise<unknown> {
  try { return JSON.parse(new TextDecoder().decode(await bytes(response, 2 * 1024 * 1024))) }
  catch { throw new FrozenExperimentError('invalid_response') }
}
async function sha256(value: Uint8Array<ArrayBuffer> | ArrayBuffer) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', value)), byte => byte.toString(16).padStart(2, '0')).join('')
}
export const frozenExperimentsApi = {
  async list(): Promise<FrozenExperiment[]> {
    const value = await json(await request(''))
    if (!object(value) || value.schema_version !== 1 || !Array.isArray(value.experiments) || value.experiments.length > 1000) throw new FrozenExperimentError('invalid_response')
    return value.experiments.map(report)
  },
  async get(id: string): Promise<FrozenExperiment> {
    identifier(id)
    const result = report(await json(await request(`/${id}`)))
    if (result.package_id !== id) throw new FrozenExperimentError('integrity')
    return result
  },
  async import(payload: Blob): Promise<FrozenExperiment> {
    if (!payload.size) throw new FrozenExperimentError('invalid_archive')
    if (payload.size > MAX_FROZEN_BYTES) throw new FrozenExperimentError('too_large')
    const result = report(await json(await request('', { method: 'POST', body: payload, headers: { 'Content-Type': 'application/zip' } })))
    try {
      if (await sha256(await payload.arrayBuffer()) !== result.package_id) throw new FrozenExperimentError('integrity')
    } catch { throw new FrozenExperimentError('integrity') }
    return result
  },
  async download(id: string, artifact: FrozenArtifact): Promise<Blob> {
    identifier(id)
    if (!ARTIFACT_KINDS.includes(artifact.kind) || !digest(artifact.sha256) || !count(artifact.bytes)
      || artifact.bytes > (artifact.kind === 'archive' ? MAX_FROZEN_BYTES : 32 * 1024 * 1024)) throw new FrozenExperimentError('invalid_response')
    try {
      const response = await request(`/${id}/artifacts/${artifact.kind}`)
      if (response.headers.get('X-Content-SHA256') !== artifact.sha256) throw new FrozenExperimentError('integrity')
      const value = await bytes(response, artifact.bytes)
      if (value.byteLength !== artifact.bytes || await sha256(value) !== artifact.sha256) throw new FrozenExperimentError('integrity')
      return new Blob([value], { type: artifact.kind === 'archive' ? 'application/zip' : 'application/octet-stream' })
    } catch (error) {
      if (error instanceof FrozenExperimentError) throw error
      throw new FrozenExperimentError('integrity')
    }
  },
}
