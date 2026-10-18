import { Button } from '@/components/ui/button'
import { compareFixtureReports, type VerifiedFixtureReport } from '@/lib/vnpy-report-comparison'

function number(value: number | null, delta = false): string {
  if (value === null) return 'Unavailable'
  return `${delta && value > 0 ? '+' : ''}${value.toLocaleString('en-US', { maximumFractionDigits: 5 })}`
}
function download(report: VerifiedFixtureReport) {
  const url = URL.createObjectURL(new Blob([report.envelope.text], { type: 'application/json' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `vnpy-${report.envelope.sha256}.json`
  anchor.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}
function Setup({ title, report }: { title: 'Reference' | 'Candidate'; report: VerifiedFixtureReport }) {
  const request = report.value.request
  return <div className="min-w-0 space-y-2">
    <h4 className="text-sm font-medium">{title} · {request.strategy_id}</h4>
    <p className="break-words font-mono text-xs">{Object.entries(request.parameters).map(([key, value]) => `${key}: ${value}`).join(' · ')}</p>
    <p className="text-xs text-muted-foreground">Fee {request.costs.fee_bps} bps · Half spread {request.costs.half_spread_price} USD/unit/fill · Slippage {request.costs.slippage_price} USD/unit/fill</p>
    <dl className="space-y-1 text-xs"><dt className="text-muted-foreground">Artifact SHA256</dt>
      <dd className="break-all font-mono">{report.envelope.sha256}</dd></dl>
    <Button variant="outline" onClick={() => download(report)}>Download {title.toLowerCase()} JSON</Button>
  </div>
}
function Cells({ row }: { row: { reference: number | null; candidate: number | null; delta: number | null } }) {
  return <><td className="p-2 text-right font-mono tabular-nums">{number(row.reference)}</td>
    <td className="p-2 text-right font-mono tabular-nums">{number(row.candidate)}</td>
    <td className="p-2 text-right font-mono tabular-nums">{number(row.delta, true)}</td></>
}
function Columns({ first }: { first: string }) {
  return <tr><th scope="col" className="p-2">{first}</th>
    <th scope="col" className="p-2 text-right">Reference</th><th scope="col" className="p-2 text-right">Candidate</th>
    <th scope="col" className="p-2 text-right">Change</th></tr>
}
export function VnpyReportComparison({ reference, candidate, onClearReference }: {
  reference: VerifiedFixtureReport; candidate: VerifiedFixtureReport | null; onClearReference: () => void
}) {
  const comparison = candidate ? compareFixtureReports(reference, candidate) : null
  return <section aria-label="Native report comparison" className="min-w-0 space-y-4 border-y border-border py-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">Report comparison</h3>
      <Button variant="ghost" onClick={onClearReference}>Clear comparison reference</Button></div>
    <p className="text-xs text-muted-foreground">Reference retained for this browser session. Download the original JSON to keep it after leaving. Synthetic workflow evidence only.</p>
    <div className="grid gap-4 sm:grid-cols-2"><Setup title="Reference" report={reference} />
      {candidate ? <Setup title="Candidate" report={candidate} />
        : <p role="status" className="text-sm text-muted-foreground">Run a new fixture job and open its verified report to compare.</p>}</div>
    {comparison && comparison.compatible === false && <p role="status" className="text-sm">{comparison.reason}</p>}
    {comparison?.compatible && <>
      <p className="text-xs text-muted-foreground">Candidate − reference. Changes reflect the displayed parameters and costs under matching fixture and engine provenance.</p>
      <div className="overflow-x-auto"><table className="w-full text-left text-xs">
        <caption className="mb-2 text-left text-sm font-medium">Measured native results</caption>
        <thead><Columns first="Metric" /></thead><tbody>{comparison.metrics.map(row => <tr key={row.key} className="border-t border-border">
          <th scope="row" className="p-2 font-normal">{row.label}</th><Cells row={row} /></tr>)}</tbody>
      </table></div>
      <div className="overflow-x-auto"><table className="w-full text-left text-xs">
        <caption className="mb-2 text-left text-sm font-medium">Daily equity comparison</caption>
        <thead><Columns first="Session / balance (USD)" /></thead><tbody>{comparison.daily.map(row => <tr key={row.date} className="border-t border-border">
          <th scope="row" className="whitespace-nowrap p-2 font-normal">{row.date}</th><Cells row={row} /></tr>)}</tbody>
      </table></div>
    </>}
  </section>
}
