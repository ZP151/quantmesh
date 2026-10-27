import { afterEach, expect, it, vi } from 'vitest'
import { api, ApiError } from './api'
afterEach(() => vi.unstubAllGlobals())
it('encodes the timezone and instrument in the independent readonly route', async () => {
  const fetch = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
  vi.stubGlobal('fetch', fetch)
  await api.historyInspection('moomoo', 'AAPL', '2026-10-24T07:44:01+08:00')
  const [path, init] = fetch.mock.calls[0]
  expect(path).toBe('/api/instruments/moomoo/AAPL/history-inspection?at=2026-10-24T07%3A44%3A01%2B08%3A00')
  expect(init?.method).toBeUndefined()
})
it('preserves explicit unavailable errors instead of substituting a current query', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'history unavailable' }), { status: 404 })))
  await expect(api.historyInspection('hyperliquid', 'BTC', '2026-10-23T23:44:01Z')).rejects.toBeInstanceOf(ApiError)
})
