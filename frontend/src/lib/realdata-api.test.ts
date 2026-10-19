import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { createHash, webcrypto } from 'node:crypto'
import { realdataApi, MAX_SNAPSHOT_BYTES } from './realdata-api'

const id = 'a'.repeat(64)
const fetchMock = vi.fn()
beforeEach(() => { vi.stubGlobal('fetch', fetchMock); vi.stubGlobal('crypto', webcrypto) })
afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks() })

it('uses the same-origin snapshot list and refuses an unsupported schema', async () => {
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ schema_version: 1, snapshots: [] })))
  expect(await realdataApi.list()).toEqual([])
  expect(fetchMock.mock.calls[0][0]).toBe('/api/research/data-snapshots')
  fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ schema_version: 2, snapshots: [] })))
  await expect(realdataApi.list()).rejects.toMatchObject({ code: 'invalid_response' })
})

it('rejects oversized and empty archives before sending bytes', async () => {
  await expect(realdataApi.import(new Blob(['']))).rejects.toMatchObject({ code: 'invalid_archive' })
  await expect(realdataApi.import(new Blob([new Uint8Array(MAX_SNAPSHOT_BYTES + 1)])))
    .rejects.toMatchObject({ code: 'too_large' })
  expect(fetchMock).not.toHaveBeenCalled()
})

it('uploads the original binary body with application/zip and no caller path', async () => {
  fetchMock.mockResolvedValue(new Response('{}', { status: 422 }))
  const archive = new Blob(['synthetic-test-archive'])
  await expect(realdataApi.import(archive)).rejects.toMatchObject({ code: 'invalid_archive', status: 422 })
  expect(fetchMock.mock.calls[0][0]).toBe('/api/research/data-snapshots')
  expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST', body: archive,
    headers: { 'Content-Type': 'application/zip' }, credentials: 'same-origin' })
})

it.each([['../private', 'a'.repeat(65), 'A'.repeat(64), 'https://foreign.invalid']])(
  'refuses unbounded or noncanonical identifiers before fetching', async (...ids) => {
    for (const value of ids) await expect(realdataApi.get(value)).rejects.toMatchObject({ code: 'invalid_response' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

it.each([[503, 'unavailable'], [413, 'too_large'], [404, 'not_found'], [500, 'request_failed']])(
  'maps HTTP %s to a fixed safe error', async (status, code) => {
    fetchMock.mockResolvedValue(new Response('secret traceback raw payload', { status }))
    await expect(realdataApi.list()).rejects.toMatchObject({ code, status })
    await expect(realdataApi.list()).rejects.not.toThrow('secret')
  })

it('checks original downloaded bytes against the selected immutable digest', async () => {
  const bytes = new TextEncoder().encode('synthetic retained archive')
  const digest = createHash('sha256').update(bytes).digest('hex')
  fetchMock.mockResolvedValueOnce(new Response(bytes))
  const download = await realdataApi.download(digest, 'archive', digest)
  expect(download.size).toBe(bytes.byteLength)
  expect(fetchMock.mock.calls[0][0]).toBe(`/api/research/data-snapshots/${digest}/archive`)
  fetchMock.mockResolvedValueOnce(new Response(bytes))
  await expect(realdataApi.download(id, 'report', id)).rejects.toMatchObject({ code: 'integrity' })
})

it('refuses a malformed report instead of presenting a fabricated qualification', async () => {
  fetchMock.mockResolvedValue(new Response(JSON.stringify({ schema_version: 1, snapshot_id: id,
    symbol: 'SPY', qualification: { status: 'AVAILABLE' } })))
  await expect(realdataApi.get(id)).rejects.toMatchObject({ code: 'invalid_response' })
})
