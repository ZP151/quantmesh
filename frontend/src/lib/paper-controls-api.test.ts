import { afterEach, describe, expect, it, vi } from 'vitest'
import { paperControlsApi, PaperControlError } from './paper-controls-api'

export const status = {
  synthetic: true, paper: true, paused: true, blocked: false, pause_reason: 'cold_start',
  checks: [], revision: 'a'.repeat(64), limits: { max_order_quantity: 2, max_notional: 500, max_position_quantity: 4 },
  costs: { fee_bps: 10, min_fee: 0, slippage_bps: 0 }, venue_stops: {}, last_receipt: null, history: [],
}
afterEach(() => vi.unstubAllGlobals())
describe('paper control transport', () => {
  it('requires synthetic paper flags and finite evidence', async () => {
    for (const payload of [{ ...status, synthetic: false }, { ...status, revision: 'bad' }, { ...status, costs: { fee_bps: null } }]) {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(payload))))
      await expect(paperControlsApi.status()).rejects.toMatchObject({ code: 'invalid_response' })
    }
  })
  it('uses bounded same-origin POST with exact confirmation revision', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify(status)))
    vi.stubGlobal('fetch', fetcher)
    await paperControlsApi.preflight(null)
    expect(fetcher).toHaveBeenCalledWith('/api/paper-controls/preflight', expect.objectContaining({
      method: 'POST', credentials: 'same-origin', mode: 'same-origin', redirect: 'error', body: '{"target":null}',
    }))
  })
  it('exposes fixed refusal codes without raw server messages', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"detail":"C:/private/account.json"}', { status: 409 })))
    await expect(paperControlsApi.status()).rejects.toMatchObject({ code: 'request_failed' })
    expect(new PaperControlError('stale_revision').message).toBe('stale_revision')
  })
  it('refuses downloads with missing digest', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('unsafe')))
    await expect(paperControlsApi.download('audit')).rejects.toMatchObject({ code: 'integrity' })
  })
  it('treats only the exact capability-off503 as unavailable', async () => {
    for (const [body, code] of [['{"detail":"paper_controls_unavailable"}', 'unavailable'],
      ['{"detail":"upstream failed"}', 'request_failed'], ['bad gateway', 'request_failed'],
      ['{"detail":"unavailable"}', 'request_failed']]) {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(body, { status: 503 })))
      await expect(paperControlsApi.status()).rejects.toMatchObject({ code })
    }
  })
})
