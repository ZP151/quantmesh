import { expect, it } from 'vitest'
import { compareFixtureReports, type VerifiedFixtureReport } from './vnpy-report-comparison'

function report(sha = 'a'.repeat(64)): VerifiedFixtureReport {
  return { envelope: { schema_version: 1, sha256: sha, request_digest: 'c'.repeat(64), text: '{}' }, value: {
    schema_version: 1, request_digest: 'c'.repeat(64),
    request: { schema_version: 1, strategy_id: 'DoubleMaStrategy', parameters: { fast_window: 10 },
      costs: { fee_bps: 5, half_spread_price: 0.005, slippage_price: 0.005 } },
    identity: { fixture_sha256: 'd'.repeat(64), engine_sha256: 'e'.repeat(64), adapter_sha256: 'f'.repeat(64),
      runner_sha256: '1'.repeat(64), versions: { vnpy: '4.5.0' },
      strategy_sources: { DoubleMaStrategy: '2'.repeat(64), AtrRsiStrategy: '3'.repeat(64) },
      cost_units: { fee_bps: 'bps of turnover', half_spread_price: 'USD/unit/fill', slippage_price: 'USD/unit/fill' },
      capital_usd: 100000, contract_size: 1, tick: 0.01, annual_days: 252,
      replay_period: ['2013-10-07', '2013-10-11'], exchange_timezone: 'America/New_York', fixture_only: true },
    statistics: { end_balance: 100010, total_trade_count: 2, total_commission: 3, total_slippage: 4 },
    daily: [{ date: '2013-10-07', balance: 100010, net_pnl: 10 }, { date: '2013-10-08', balance: 100020, net_pnl: 10 }],
    trades: [], lifecycle: {}, semantics: 'Synthetic fixture only.' } }
}

it('compares changed parameters and costs, matching daily balances by session', () => {
  const reference = report(), candidate = report('b'.repeat(64))
  candidate.value.request.strategy_id = 'AtrRsiStrategy'
  candidate.value.request.parameters = { rsi_length: 15 }
  candidate.value.request.costs.fee_bps = 6
  candidate.value.statistics.end_balance = 100025
  candidate.value.daily = [{ date: '2013-10-08', balance: 100030, net_pnl: 15 }, { date: '2013-10-07', balance: 100015, net_pnl: 15 }]
  const result = compareFixtureReports(reference, candidate)
  expect(result.compatible).toBe(true)
  if (result.compatible === false) throw new Error(result.reason)
  expect(result.metrics.find(row => row.key === 'end_balance')).toMatchObject({ reference: 100010, candidate: 100025, delta: 15 })
  expect(result.daily).toEqual([
    { date: '2013-10-07', reference: 100010, candidate: 100015, delta: 5 },
    { date: '2013-10-08', reference: 100020, candidate: 100030, delta: 10 },
  ])
})

it.each([
  ['fixture_sha256', '9'.repeat(64)], ['engine_sha256', '9'.repeat(64)], ['runner_sha256', '9'.repeat(64)],
  ['capital_usd', 200000], ['replay_period', ['2013-10-07', '2013-10-10']],
  ['cost_units', { fee_bps: 'different' }], ['versions', { vnpy: 'different' }],
])('refuses incompatible provenance field %s', (field, value) => {
  const candidate = report('b'.repeat(64))
  candidate.value.identity[field] = value
  expect(compareFixtureReports(report(), candidate)).toMatchObject({ compatible: false, reason: expect.stringMatching(/provenance/i) })
})

it.each(['fixture_sha256', 'strategy_sources', 'cost_units', 'capital_usd', 'runner_sha256'])('refuses absent provenance %s', field => {
  const reference = report(), candidate = report('b'.repeat(64))
  delete reference.value.identity[field]
  delete candidate.value.identity[field]
  expect(compareFixtureReports(reference, candidate)).toMatchObject({ compatible: false, reason: expect.stringMatching(/provenance/i) })
})

it('refuses the same artifact and mismatched or repeated sessions', () => {
  expect(compareFixtureReports(report(), report())).toMatchObject({ compatible: false, reason: expect.stringMatching(/same artifact/i) })
  const candidate = report('b'.repeat(64))
  candidate.value.daily[0].date = '2013-10-09'
  expect(compareFixtureReports(report(), candidate)).toMatchObject({ compatible: false, reason: expect.stringMatching(/sessions/i) })
  candidate.value.daily[0].date = '2013-10-08'
  expect(compareFixtureReports(report(), candidate)).toMatchObject({ compatible: false, reason: expect.stringMatching(/sessions/i) })
})

it.each([null, '5', Infinity, NaN])('leaves unavailable metric %s and its delta unavailable', value => {
  const candidate = report('b'.repeat(64))
  candidate.value.statistics.end_balance = value
  const result = compareFixtureReports(report(), candidate)
  expect(result.compatible).toBe(true)
  if (result.compatible === false) throw new Error(result.reason)
  expect(result.metrics.find(row => row.key === 'end_balance')).toMatchObject({ reference: 100010, candidate: null, delta: null })
})

it('compares native maximum drawdown percentages and preserves an unavailable drawdown', () => {
  const reference = report(), candidate = report('b'.repeat(64))
  reference.value.statistics.max_ddpercent = -2
  candidate.value.statistics.max_ddpercent = -3.5
  const result = compareFixtureReports(reference, candidate)
  expect(result.compatible).toBe(true)
  if (result.compatible === false) throw new Error(result.reason)
  expect(result.metrics.find(row => row.key === 'max_ddpercent')).toEqual({
    key: 'max_ddpercent', label: 'Max drawdown (%)', reference: -2, candidate: -3.5, delta: -1.5,
  })
  candidate.value.statistics.max_ddpercent = null
  const unavailable = compareFixtureReports(reference, candidate)
  if (unavailable.compatible === false) throw new Error(unavailable.reason)
  expect(unavailable.metrics.find(row => row.key === 'max_ddpercent')).toMatchObject({ reference: -2, candidate: null, delta: null })
})
