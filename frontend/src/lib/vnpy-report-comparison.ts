import type { FixtureEnvelope, FixtureReport } from './vnpy-fixture-api'
export type VerifiedFixtureReport = { envelope: FixtureEnvelope; value: FixtureReport }
type Row = { key: string; label: string; reference: number | null; candidate: number | null; delta: number | null }
type Daily = { date: string; reference: number | null; candidate: number | null; delta: number | null }
type Comparison = { compatible: true; metrics: Row[]; daily: Daily[] } | { compatible: false; reason: string }
const hash = /^[a-f0-9]{64}$/
function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}
function finite(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
function canonical(value: unknown): string {
  return JSON.stringify(value, (_key, item) => object(item)
    ? Object.fromEntries(Object.entries(item).sort(([a], [b]) => a.localeCompare(b))) : item)
}
function completeIdentity(identity: Record<string, unknown>, strategy: string): boolean {
  const sources = identity.strategy_sources
  const units = identity.cost_units
  return ['fixture_sha256', 'engine_sha256', 'adapter_sha256', 'runner_sha256']
    .every(key => typeof identity[key] === 'string' && hash.test(identity[key] as string))
    && object(identity.versions) && Object.keys(identity.versions).length > 0
    && Object.values(identity.versions).every(value => typeof value === 'string' && value.length > 0)
    && object(sources) && typeof sources[strategy] === 'string' && hash.test(sources[strategy])
    && Object.values(sources).every(value => typeof value === 'string' && hash.test(value))
    && object(units) && ['fee_bps', 'half_spread_price', 'slippage_price']
      .every(key => typeof units[key] === 'string' && units[key].length > 0)
    && ['capital_usd', 'contract_size', 'tick', 'annual_days'].every(key => (finite(identity[key]) ?? 0) > 0)
    && Array.isArray(identity.replay_period) && identity.replay_period.length === 2
    && identity.replay_period.every(value => typeof value === 'string' && validDate(value))
    && typeof identity.exchange_timezone === 'string' && identity.exchange_timezone.length > 0
    && identity.fixture_only === true
}
function validDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value))
    && new Date(value).toISOString().slice(0, 10) === value
}
function cells(reference: unknown, candidate: unknown) {
  const a = finite(reference), b = finite(candidate)
  return { reference: a, candidate: b, delta: a === null || b === null ? null : finite(b - a) }
}

export function compareFixtureReports(reference: VerifiedFixtureReport, candidate: VerifiedFixtureReport): Comparison {
  if (reference.envelope.sha256 === candidate.envelope.sha256) {
    return { compatible: false, reason: 'These reports are the same artifact. Run a different configuration to compare.' }
  }
  const a = reference.value, b = candidate.value
  if (a.schema_version !== 1 || b.schema_version !== 1
    || !object(a.identity) || !object(b.identity)
    || !completeIdentity(a.identity, a.request.strategy_id) || !completeIdentity(b.identity, b.request.strategy_id)
    || canonical(a.identity) !== canonical(b.identity)) {
    return { compatible: false, reason: 'Report provenance is missing or differs. Compare reports with the same fixture, source, engine, cost units, capital and replay period.' }
  }
  const daysA = new Map(a.daily.map(day => [day.date, day]))
  const daysB = new Map(b.daily.map(day => [day.date, day]))
  const dates = [...daysA.keys()].sort()
  if (!dates.length || daysA.size !== a.daily.length || daysB.size !== b.daily.length
    || daysA.size !== daysB.size || dates.some(date => !validDate(date) || !daysB.has(date))) {
    return { compatible: false, reason: 'Report sessions differ or are missing, invalid or repeated. Compare reports covering the same daily sessions.' }
  }
  const metrics = ([['end_balance', 'End balance (USD)'], ['total_trade_count', 'Fills'],
    ['total_commission', 'Fees (USD)'], ['total_slippage', 'Spread + slippage (USD)'],
    ['max_ddpercent', 'Max drawdown (%)']] as const)
    .map(([key, label]) => ({ key, label, ...cells(a.statistics[key], b.statistics[key]) }))
  return { compatible: true, metrics, daily: dates.map(date => ({ date,
    ...cells(daysA.get(date)?.balance, daysB.get(date)?.balance) })) }
}
