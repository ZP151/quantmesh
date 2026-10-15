// Separate experimental protocol. Production research JobStore DTOs stay unchanged.
export type FixtureRequest = {
  schema_version: 1; strategy_id: string; parameters: Record<string, number>;
  costs: { fee_bps: number; half_spread_price: number; slippage_price: number };
}
export type FixtureOptions = {
  schema_version: 1; fixture_sha256: string; fixture_label: string;
  engine_versions: Record<string, string>;
  strategies: { strategy_id: string; source_sha256: string;
    parameters: { name: string; default: number; minimum: number; maximum: number; integer: boolean }[] }[];
}
export type FixtureJob = {
  schema_version: 1; job_id: string; request_digest: string; request: FixtureRequest;
  state: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'; stage: string;
  completed_bars: number; total_bars: number; error_code: string | null; report_sha256: string | null;
}
export type FixtureEnvelope = { schema_version: 1; sha256: string; request_digest: string; text: string }
export type FixtureReport = {
  schema_version: 1; request_digest: string; request: FixtureRequest;
  statistics: Record<string, number | string | null>;
  daily: { date: string; balance: number; net_pnl: number }[];
  trades: { datetime: string; direction: string; offset: string; price: number; volume: number }[];
  identity: Record<string, unknown>; lifecycle: Record<string, number>; semantics: string;
}
const prefix = '/api/research/vnpy-fixture'
const hash = /^[a-f0-9]{64}$/
function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
async function call(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(prefix + path, { ...init, signal: AbortSignal.timeout(12000),
    headers: { 'Content-Type': 'application/json', ...init?.headers } })
  if (!response.ok) throw Object.assign(
    new Error(`Request failed (${response.status}). Refresh or retry the retained submission.`),
    { status: response.status })
  return response.json()
}
function job(value: unknown): FixtureJob {
  if (!object(value) || value.schema_version !== 1 || typeof value.job_id !== 'string'
    || typeof value.request_digest !== 'string' || !hash.test(value.request_digest)
    || !['queued', 'running', 'succeeded', 'failed', 'cancelled'].includes(String(value.state))
    || typeof value.stage !== 'string' || !object(value.request)
    || !Number.isInteger(value.completed_bars) || value.total_bars !== 1950
    || Number(value.completed_bars) < 0 || Number(value.completed_bars) > 1950
    || (value.report_sha256 !== null && (typeof value.report_sha256 !== 'string' || !hash.test(value.report_sha256)))) {
    throw new Error('Invalid fixture job response')
  }
  return value as unknown as FixtureJob
}
export const vnpyFixtureApi = {
  async options(): Promise<FixtureOptions> {
    const value = await call('/options')
    if (!object(value) || value.schema_version !== 1 || !hash.test(String(value.fixture_sha256))
      || typeof value.fixture_label !== 'string' || !object(value.engine_versions)
      || !Array.isArray(value.strategies) || value.strategies.length !== 2
      || !value.strategies.every(s => object(s) && ['DoubleMaStrategy', 'AtrRsiStrategy'].includes(String(s.strategy_id))
        && hash.test(String(s.source_sha256)) && Array.isArray(s.parameters) && s.parameters.length > 0
        && s.parameters.every(p => object(p) && typeof p.name === 'string' && typeof p.integer === 'boolean'
          && [p.default, p.minimum, p.maximum].every(n => typeof n === 'number' && Number.isFinite(n))))) {
      throw new Error('Invalid fixture options')
    }
    return value as unknown as FixtureOptions
  },
  async submit(request: FixtureRequest, key: string): Promise<FixtureJob> {
    return job(await call('/jobs', { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify(request) }))
  },
  async get(id: string): Promise<FixtureJob> { return job(await call(`/jobs/${encodeURIComponent(id)}`)) },
  async cancel(id: string): Promise<FixtureJob> {
    return job(await call(`/jobs/${encodeURIComponent(id)}/cancel`, { method: 'POST' }))
  },
  async report(id: string): Promise<FixtureEnvelope> {
    const value = await call(`/jobs/${encodeURIComponent(id)}/report`)
    if (!object(value) || value.schema_version !== 1 || typeof value.text !== 'string'
      || value.text.length > 4000000 || !hash.test(String(value.sha256)) || !hash.test(String(value.request_digest))) {
      throw new Error('Invalid fixture report response')
    }
    return value as unknown as FixtureEnvelope
  },
}
