import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createHash, webcrypto } from 'node:crypto'
import { frozenExperimentsApi, MAX_FROZEN_BYTES } from './frozen-experiments-api'

const id = 'a'.repeat(64)
const fetchMock = vi.fn()
beforeEach(() => { vi.stubGlobal('fetch', fetchMock); vi.stubGlobal('crypto', webcrypto) })
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks() })

function fixture() {
  const numericKeys = 'sessions terminal_equity net_profit_usd total_return cagr max_drawdown max_underwater_sessions annualized_volatility naive_sharpe_rf_zero sortino_target_zero calmar worst_day historical_es_95 es_tail_observations fills long_entries friction_usd dividend_earned_usd dividend_paid_usd terminal_receivable gross_traded_notional_over_initial_capital capacity_clipped_sessions terminal_shares'.split(' ')
  const metrics = { start: '2025-01-02', end: '2026-10-16', ...Object.fromEntries(numericKeys.map(k => [k, null])) }
  return { schema_version: 1, package_id: id, experiment_id: 'QM-REAL-ETF-001-D-20261018', snapshot_id: 'b'.repeat(64), imported_at: '2026-10-19T00:00:00Z',
    verification: { identities: 'VERIFIED', economics: 'IMPORTED_NOT_RECOMPUTED', chronology: 'UNVERIFIED' },
    proxy_verdict: 'REJECT', formal_verdict: { R1: 'INSUFFICIENT', R2: 'INSUFFICIENT', R3: 'NOT_AUTHORIZED' },
    oos: { state: 'CONSUMED', pristine_blind: false }, trials: { current: 1, searched: 0, prior: null as number | null, source_exposure: true },
    protocol: { sha256: 'c'.repeat(64), frozen_at_claimed: '2026-10-18T00:00:00Z', created_before_results_claimed: true,
      symbol: 'SPY', lookback: 100, comparison: 'completed close > SMA100', execution: 'daily OPEN proxy', final_window: ['2025-01-02', '2026-10-16'], capital_usd: 100000,
      costs: { single_side_proxy_bps: 5, stress_bps: 10, gross_diagnostic_bps: 0, extra_delay_stress_sessions: 1, actual_nbbo_and_costs_verified: false, fee_spread_slippage_breakdown: 'unknown' } },
    data: { qualification: 'INSUFFICIENT', evidence_kind: 'fixture', rights: 'UNVERIFIED', pit: 'UNVERIFIED', execution: 'UNVERIFIED', dividend_conflict: { date: '2021-12-17', yahoo_usd: 1.633, issuer_usd: 1.636431, resolution: 'unresolved' } },
    missing_evidence: ['PIT'], cases: ['final-base5bps', 'final-stress10bps', 'final-delay1session5bps', 'final-gross0bps', 'development2020-base5bps', 'validation2022-base5bps', 'validation2023-base5bps', 'validation2024-base5bps'].map((case_id, i) => ({ case_id, primary: i === 0, strategy: { ...metrics }, benchmark: { ...metrics }, cash_benchmark_total_return: null, net_total_return_difference: null, inference: [] })),
    lineage: Array.from({ length: 46 }, (_, i) => ({ path: `member-${i}`, sha256: id, bytes: 12 })),
    downloads: ['archive', 'protocol', 'receipt', 'result', 'report', 'timeline', 'review', 'verification', 'manifest'].map(kind => ({ kind, sha256: kind === 'protocol' ? 'c'.repeat(64) : id, bytes: 12 })),
  }
}

it('accepts the coherent historical DTO without defaulting unknown metrics to zero', async () => {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(fixture())))
  const result = await frozenExperimentsApi.get(id)
  expect(result.cases[0].strategy.naive_sharpe_rf_zero).toBeNull()
  expect(result.trials.prior).toBeNull()
  expect(result.cases[0].case_id).toBe('final-base5bps')
})

it.each(['verdict', 'trials', 'primary', 'metric', 'oos', 'identity'])('refuses unsafe or malformed %s DTO claims', async change => {
  const value = fixture()
  if (change === 'verdict') value.formal_verdict.R1 = 'PASS'
  if (change === 'trials') value.trials.prior = 0
  if (change === 'primary') value.cases[2].primary = true
  if (change === 'metric') Object.assign(value.cases[0].strategy, { total_return: 'unknown' })
  if (change === 'oos') value.oos.pristine_blind = true
  if (change === 'identity') value.package_id = 'f'.repeat(64)
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(value)))
  await expect(frozenExperimentsApi.get(id)).rejects.toMatchObject({ code: 'invalid_response' })
})

it('binds a successful import response to the selected original bytes', async () => {
  const data = new TextEncoder().encode('synthetic original ZIP')
  const packageId = createHash('sha256').update(data).digest('hex')
  const payload = new Blob([data])
  Object.defineProperty(payload, 'arrayBuffer', { value: async () => data.buffer })
  const value = fixture(); value.package_id = packageId; value.downloads[0].sha256 = packageId
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(value)))
  expect((await frozenExperimentsApi.import(payload)).package_id).toBe(packageId)
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(fixture())))
  await expect(frozenExperimentsApi.import(payload)).rejects.toMatchObject({ code: 'integrity' })
})

it('lists only the supported schema over same-origin transport', async () => {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ schema_version: 1, experiments: [] })))
  expect(await frozenExperimentsApi.list()).toEqual([])
  expect(fetchMock.mock.calls[0][0]).toBe('/api/research/frozen-experiments')
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: 'same-origin', mode: 'same-origin', redirect: 'error' })
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ schema_version: 2, experiments: [] })))
  await expect(frozenExperimentsApi.list()).rejects.toMatchObject({ code: 'invalid_response' })
})

it('blocks empty or oversized imports before sending any request', async () => {
  await expect(frozenExperimentsApi.import(new Blob([]))).rejects.toMatchObject({ code: 'invalid_archive' })
  await expect(frozenExperimentsApi.import(new Blob([new Uint8Array(MAX_FROZEN_BYTES + 1)]))).rejects.toMatchObject({ code: 'too_large' })
  expect(fetchMock).not.toHaveBeenCalled()
})

it('sends exact original ZIP bytes and recognizes the missing P1 prerequisite', async () => {
  const blob = new Blob(['original ZIP'])
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ detail: 'frozen_experiment_snapshot_required' }), { status: 422 }))
  await expect(frozenExperimentsApi.import(blob)).rejects.toMatchObject({ code: 'snapshot_required' })
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST', body: blob, headers: { 'Content-Type': 'application/zip' } })
})

it.each([[503, 'unavailable'], [409, 'integrity'], [404, 'not_found'], [413, 'too_large'], [500, 'request_failed']])(
  'uses fixed error %s without exposing response payloads', async (status, code) => {
    fetchMock.mockResolvedValue(new Response('private traceback', { status }))
    await expect(frozenExperimentsApi.list()).rejects.toMatchObject({ code })
    await expect(frozenExperimentsApi.list()).rejects.not.toThrow('private')
  })

it('refuses paths and malformed reports instead of inventing safe evidence', async () => {
  await expect(frozenExperimentsApi.get('../secret')).rejects.toMatchObject({ code: 'invalid_response' })
  expect(fetchMock).not.toHaveBeenCalled()
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ schema_version: 1, package_id: id, proxy_verdict: 'PASS' })))
  await expect(frozenExperimentsApi.get(id)).rejects.toMatchObject({ code: 'invalid_response' })
})

it('verifies selected identity, byte count and SHA before returning a download', async () => {
  const bytes = new TextEncoder().encode('retained original')
  const sha256 = createHash('sha256').update(bytes).digest('hex')
  const artifact = { kind: 'report' as const, sha256, bytes: bytes.byteLength }
  fetchMock.mockResolvedValueOnce(new Response(bytes, { headers: { 'X-Content-SHA256': sha256 } }))
  expect((await frozenExperimentsApi.download(id, artifact)).size).toBe(bytes.byteLength)
  expect(fetchMock.mock.calls[0][0]).toBe(`/api/research/frozen-experiments/${id}/artifacts/report`)
  fetchMock.mockResolvedValueOnce(new Response(bytes, { headers: { 'X-Content-SHA256': sha256 } }))
  await expect(frozenExperimentsApi.download(id, { ...artifact, sha256: id })).rejects.toMatchObject({ code: 'integrity' })
  fetchMock.mockResolvedValueOnce(new Response(bytes))
  await expect(frozenExperimentsApi.download(id, artifact)).rejects.toMatchObject({ code: 'integrity' })
})
