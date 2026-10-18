import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { VnpyReportComparison } from './VnpyReportComparison'
import type { VerifiedFixtureReport } from '@/lib/vnpy-report-comparison'

function report(sha: string, endBalance = 100010): VerifiedFixtureReport {
  const value = { schema_version: 1 as const, request_digest: 'c'.repeat(64),
    request: { schema_version: 1 as const, strategy_id: 'DoubleMaStrategy', parameters: { fast_window: 10 },
      costs: { fee_bps: 5, half_spread_price: 0.005, slippage_price: 0.005 } },
    identity: { fixture_sha256: 'd'.repeat(64), engine_sha256: 'e'.repeat(64), adapter_sha256: 'f'.repeat(64),
      runner_sha256: '1'.repeat(64), versions: { vnpy: '4.5.0' }, strategy_sources: { DoubleMaStrategy: '2'.repeat(64) },
      cost_units: { fee_bps: 'bps of turnover', half_spread_price: 'USD/unit/fill', slippage_price: 'USD/unit/fill' },
      capital_usd: 100000, contract_size: 1, tick: 0.01, annual_days: 252, fixture_only: true,
      replay_period: ['2013-10-07', '2013-10-11'], exchange_timezone: 'America/New_York' },
    statistics: { end_balance: endBalance, total_trade_count: 2, total_commission: 3, total_slippage: 4 },
    daily: [{ date: '2013-10-07', balance: endBalance, net_pnl: endBalance - 100000 }],
    trades: [], lifecycle: {}, semantics: 'Synthetic fixture only · 样本.' }
  return { value, envelope: { schema_version: 1, request_digest: value.request_digest,
    sha256: sha.repeat(64), text: JSON.stringify(value, null, 2) + '\n' } }
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers() })

it('retains the reference with a clear action while another report is pending', () => {
  const clear = vi.fn()
  render(<VnpyReportComparison reference={report('a')} candidate={null} onClearReference={clear} />)
  expect(screen.getByRole('region', { name: 'Native report comparison' })).toHaveTextContent(/this browser session/i)
  expect(screen.getByText('a'.repeat(64))).toBeVisible()
  expect(screen.getByRole('button', { name: 'Download reference JSON' })).toBeEnabled()
  expect(screen.queryByRole('button', { name: 'Download candidate JSON' })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: 'Clear comparison reference' }))
  expect(clear).toHaveBeenCalledOnce()
})

it('shows settings and candidate minus reference deltas without inventing unavailable values', () => {
  const candidate = report('b', 100025)
  candidate.value.statistics.total_commission = null as unknown as number
  candidate.value.request.parameters.fast_window = 12
  render(<VnpyReportComparison reference={report('a')} candidate={candidate} onClearReference={() => {}} />)
  const summary = screen.getByRole('table', { name: 'Measured native results' })
  const balance = within(summary).getByRole('row', { name: /End balance/ })
  expect(within(balance).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['100,010', '100,025', '+15'])
  const fees = within(summary).getByRole('row', { name: /Fees/ })
  expect(within(fees).getAllByRole('cell').map(cell => cell.textContent)).toEqual(['3', 'Unavailable', 'Unavailable'])
  expect(screen.getByText(/fast_window: 12/)).toBeVisible()
  expect(screen.getByText(/Candidate − reference/)).toBeVisible()
  expect(screen.getByRole('table', { name: 'Daily equity comparison' })).toBeVisible()
})

it('refuses incompatible reports while retaining both original downloads', () => {
  const candidate = report('b')
  candidate.value.identity.capital_usd = 200000
  render(<VnpyReportComparison reference={report('a')} candidate={candidate} onClearReference={() => {}} />)
  expect(screen.getByRole('status')).toHaveTextContent(/provenance/i)
  expect(screen.queryByRole('table', { name: 'Measured native results' })).toBeNull()
  expect(screen.getByRole('button', { name: 'Download candidate JSON' })).toBeEnabled()
})

it('downloads each original UTF-8 artifact with its hash filename and revokes its URL', async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  const blobs: Blob[] = [], clicked: { href: string; filename: string }[] = []
  vi.stubGlobal('URL', { createObjectURL: (blob: Blob) => { blobs.push(blob); return `blob:report-${blobs.length}` }, revokeObjectURL: vi.fn() })
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    clicked.push({ href: this.href, filename: this.download })
  })
  const reference = report('a'), candidate = report('b', 100025)
  render(<VnpyReportComparison reference={reference} candidate={candidate} onClearReference={() => {}} />)
  fireEvent.click(screen.getByRole('button', { name: 'Download reference JSON' }))
  fireEvent.click(screen.getByRole('button', { name: 'Download candidate JSON' }))
  const read = (blob: Blob) => new Promise<string>((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = reject; reader.readAsText(blob)
  })
  expect(await Promise.all(blobs.map(read))).toEqual([reference.envelope.text, candidate.envelope.text])
  expect(clicked).toEqual([
    { href: 'blob:report-1', filename: `vnpy-${'a'.repeat(64)}.json` },
    { href: 'blob:report-2', filename: `vnpy-${'b'.repeat(64)}.json` },
  ])
  vi.advanceTimersByTime(1000)
  expect(URL.revokeObjectURL).toHaveBeenNthCalledWith(1, 'blob:report-1')
  expect(URL.revokeObjectURL).toHaveBeenNthCalledWith(2, 'blob:report-2')
})
