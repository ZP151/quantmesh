import { usePreferences, type Locale } from '@/lib/preferences'
import { Button } from '@/components/ui/button'
import { compareFixtureReports, type VerifiedFixtureReport } from '@/lib/vnpy-report-comparison'

const chinese = {
  "Reference": "参考",
  "Candidate": "候选",
  "Change": "变化",
  "Fee": "费用",
  "Half spread": "半价差",
  "Slippage": "滑点",
  "Artifact SHA256": "原件 SHA256",
  "Download reference JSON": "下载参考 JSON",
  "Download candidate JSON": "下载候选 JSON",
  "Native report comparison": "原生报告比较",
  "Report comparison": "报告比较",
  "Clear comparison reference": "清除比较参考",
  "Reference retained for this browser session. Download the original JSON to keep it after leaving. Synthetic workflow evidence only.": "参考报告仅在当前页面会话内保留。离开前请下载原始 JSON。仅为合成样本流程证据。",
  "Run a new fixture job and open its verified report to compare.": "请运行新的工程样本任务，并打开其已校验报告以进行比较。",
  "Candidate − reference. Changes reflect the displayed parameters and costs under matching fixture and engine provenance.": "候选 − 参考。变化反映所示参数与成本的差异，工程样本与引擎来源保持一致。",
  "Measured native results": "原生结果指标",
  "Daily equity comparison": "每日权益比较",
  "Metric": "指标",
  "Session / balance (USD)": "交易日 / 余额（USD）"
} as const
function useCopy() {
  const { locale } = usePreferences()
  return { locale, text: (value: keyof typeof chinese) => locale === 'zh-CN' ? chinese[value] : value }
}

function number(value: number | null, locale: Locale, delta = false): string {
  if (value === null) return locale === 'zh-CN' ? '不可用' : 'Unavailable'
  return `${delta && value > 0 ? '+' : ''}${value.toLocaleString(locale === 'en' ? 'en-US' : locale, { maximumFractionDigits: 5 })}`
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
  const { text } = useCopy()
  const request = report.value.request
  return <div className="min-w-0 space-y-2">
    <h4 className="text-sm font-medium">{text(title)} · {request.strategy_id}</h4>
    <p className="break-words font-mono text-xs">{Object.entries(request.parameters).map(([key, value]) => `${key}: ${value}`).join(' · ')}</p>
    <p className="text-xs text-muted-foreground">{text("Fee")} {request.costs.fee_bps} bps · {text("Half spread")} {request.costs.half_spread_price} USD/unit/fill · {text("Slippage")} {request.costs.slippage_price} USD/unit/fill</p>
    <dl className="space-y-1 text-xs"><dt className="text-muted-foreground">{text("Artifact SHA256")}</dt>
      <dd className="break-all font-mono">{report.envelope.sha256}</dd></dl>
    <Button variant="outline" onClick={() => download(report)}>{text(title === 'Reference' ? 'Download reference JSON' : 'Download candidate JSON')}</Button>
  </div>
}
function Cells({ row }: { row: { reference: number | null; candidate: number | null; delta: number | null } }) {
  const { locale } = useCopy()
  return <><td className="p-2 text-right font-mono tabular-nums">{number(row.reference, locale)}</td>
    <td className="p-2 text-right font-mono tabular-nums">{number(row.candidate, locale)}</td>
    <td className="p-2 text-right font-mono tabular-nums">{number(row.delta, locale, true)}</td></>
}
function Columns({ first }: { first: string }) {
  const { text } = useCopy()
  return <tr><th scope="col" className="p-2">{first}</th>
    <th scope="col" className="p-2 text-right">{text("Reference")}</th><th scope="col" className="p-2 text-right">{text("Candidate")}</th>
    <th scope="col" className="p-2 text-right">{text("Change")}</th></tr>
}
export function VnpyReportComparison({ reference, candidate, onClearReference }: {
  reference: VerifiedFixtureReport; candidate: VerifiedFixtureReport | null; onClearReference: () => void
}) {
  const { locale, text } = useCopy()
  const metrics: Record<string, string> = { end_balance: '期末余额（USD）', total_trade_count: '成交次数', total_commission: '费用（USD）', total_slippage: '价差 + 滑点（USD）', max_ddpercent: '最大回撤（%）' }
  const comparison = candidate ? compareFixtureReports(reference, candidate) : null
  return <section aria-label={text("Native report comparison")} className="min-w-0 space-y-4 border-y border-border py-4">
    <div className="flex flex-wrap items-center justify-between gap-2"><h3 className="font-semibold">{text("Report comparison")}</h3>
      <Button variant="ghost" onClick={onClearReference}>{text("Clear comparison reference")}</Button></div>
    <p className="text-xs text-muted-foreground">{text("Reference retained for this browser session. Download the original JSON to keep it after leaving. Synthetic workflow evidence only.")}</p>
    <div className="grid gap-4 sm:grid-cols-2"><Setup title="Reference" report={reference} />
      {candidate ? <Setup title="Candidate" report={candidate} />
        : <p role="status" className="text-sm text-muted-foreground">{text("Run a new fixture job and open its verified report to compare.")}</p>}</div>
    {comparison && comparison.compatible === false && <p role="status" className="text-sm">{locale === 'zh-CN' && '无法比较。原始原因：'}{comparison.reason}</p>}
    {comparison?.compatible && <>
      <p className="text-xs text-muted-foreground">{text("Candidate − reference. Changes reflect the displayed parameters and costs under matching fixture and engine provenance.")}</p>
      <div className="overflow-x-auto"><table className="w-full text-left text-xs">
        <caption className="mb-2 text-left text-sm font-medium">{text("Measured native results")}</caption>
        <thead><Columns first={text("Metric")} /></thead><tbody>{comparison.metrics.map(row => <tr key={row.key} className="border-t border-border">
          <th scope="row" className="p-2 font-normal">{locale === 'zh-CN' ? metrics[row.key] ?? row.label : row.label}</th><Cells row={row} /></tr>)}</tbody>
      </table></div>
      <div className="overflow-x-auto"><table className="w-full text-left text-xs">
        <caption className="mb-2 text-left text-sm font-medium">{text("Daily equity comparison")}</caption>
        <thead><Columns first={text("Session / balance (USD)")} /></thead><tbody>{comparison.daily.map(row => <tr key={row.date} className="border-t border-border">
          <th scope="row" className="whitespace-nowrap p-2 font-normal">{row.date}</th><Cells row={row} /></tr>)}</tbody>
      </table></div>
    </>}
  </section>
}
