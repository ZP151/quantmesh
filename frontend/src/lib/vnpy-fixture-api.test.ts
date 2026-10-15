import { beforeEach, expect, it, vi } from 'vitest'
import { vnpyFixtureApi } from './vnpy-fixture-api'

const fetchMock = vi.fn()
const sha = 'a'.repeat(64)
const request = { schema_version: 1 as const, strategy_id: 'DoubleMaStrategy', parameters: { fast_window: 10, slow_window: 20 },
  costs: { fee_bps: 5, half_spread_price: 0.005, slippage_price: 0.005 } }
const job = { schema_version: 1, job_id: 'job1', request_digest: sha, request, state: 'running', stage: 'replaying',
  completed_bars: 100, total_bars: 1950, report_sha256: null, error_code: null }
function respond(value: unknown, status = 200) {
  fetchMock.mockResolvedValue({ ok: status === 200 || status === 202, status, json: async () => value })
}
beforeEach(() => { vi.stubGlobal('fetch', fetchMock); fetchMock.mockReset() })

it('uses the separate native protocol and retained idempotency key', async () => {
  respond(job, 202)
  expect(await vnpyFixtureApi.submit(request, 'retained-key')).toEqual(job)
  const [url, init] = fetchMock.mock.calls[0]
  expect(url).toBe('/api/research/vnpy-fixture/jobs')
  expect(init.headers['Idempotency-Key']).toBe('retained-key')
  expect(JSON.parse(init.body)).toEqual(request)
})

it.each([{ ...job, state: 'invented' }, { ...job, completed_bars: -1 }, { ...job, completed_bars: 1951 },
  { ...job, total_bars: 999 }, { ...job, request_digest: 'wrong' }, { ...job, report_sha256: 'wrong' }])(
  'refuses malformed status', async value => {
    respond(value)
    await expect(vnpyFixtureApi.get('job1')).rejects.toThrow('Invalid fixture job')
  })

it('sanitizes unavailable service errors', async () => {
  respond({ detail: 'private path or native traceback' }, 503)
  await expect(vnpyFixtureApi.options()).rejects.toThrow('Request failed (503)')
})

it('refuses malformed reports', async () => {
  respond({ schema_version: 1, sha256: 'wrong', request_digest: sha, text: '{}' })
  await expect(vnpyFixtureApi.report('job1')).rejects.toThrow('Invalid fixture report')
})

it('refuses unqualified options', async () => {
  respond({ schema_version: 1, fixture_sha256: sha, fixture_label: 'fixture', engine_versions: {}, strategies: [] })
  await expect(vnpyFixtureApi.options()).rejects.toThrow('Invalid fixture options')
})
