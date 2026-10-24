import { useEffect, useState } from 'react'
import { ArrowLeft, Download } from 'lucide-react'
import { Page } from '@/components/page'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { usePreferences } from '@/lib/preferences'
import { explainCsvReason } from '@/lib/local-csv-copy'
import { localCsvApi, type LocalCsvReference, type LocalCsvReport } from '@/lib/local-csv-api'

// A selected uploaded reference gets its own planning context. It is never
// assigned to a fixture job request or silently replaced with a seeded dataset.
export function LocalCsvPlanning({ snapshotId }: { snapshotId: string }) {
  const { locale } = usePreferences(); const zh = locale === 'zh-CN'
  const [reference, setReference] = useState<LocalCsvReference | null>(null)
  const [selected, setSelected] = useState<LocalCsvReport | null>(null)
  const [error, setError] = useState(false)
  const [question, setQuestion] = useState('')
  const [costs, setCosts] = useState('')
  const [evaluationWindow, setEvaluationWindow] = useState('')
  useEffect(() => {
    let active = true
    setReference(null); setSelected(null); setError(false)
    setQuestion(''); setCosts(''); setEvaluationWindow('')
    Promise.all([localCsvApi.reference(snapshotId), localCsvApi.get(snapshotId)]).then(([value, report]) => {
      const left = value.dataset_ref; const right = report.dataset_ref
      if (report.snapshot_id !== value.snapshot_id || (!!left !== !!right) || (left && right
        && ['dataset_id', 'revision', 'manifest_digest', 'export_digest', 'permission_class'].some(key => left[key as keyof typeof left] !== right[key as keyof typeof right]))) throw new Error('reference_mismatch')
      if (active) { setReference(value); setSelected(report) }
    })
      .catch(() => { if (active) setError(true) })
    return () => { active = false }
  }, [snapshotId])
  function download() {
    if (!reference?.dataset_ref || !question.trim()) return
    const draft = { schema_version: 1, status: 'draft_not_submitted', intended_use: 'local_protocol_planning_only',
      snapshot_id: reference.snapshot_id, dataset_ref: reference.dataset_ref, eligibility: reference.eligibility,
      runner_status: reference.runner_status, research_question: question.trim(), planned_evaluation_window: evaluationWindow.trim() || null,
      costs_to_verify: costs.trim() || null, results: null }
    const url = URL.createObjectURL(new Blob([JSON.stringify(draft, null, 2) + '\n'], { type: 'application/json' }))
    const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'local-data-protocol-draft.json'
    document.body.append(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 0)
  }
  const fieldClass = 'min-h-11 w-full min-w-0 rounded-md border border-input bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
  return <Page title={zh ? '规划使用自有数据的实验' : 'Plan an experiment with your data'} description={zh ? '使用已保存的数据引用记录研究问题和待验证假设。草案不会提交执行。' : 'Use your saved data reference to record a research question and assumptions to verify. This draft is not submitted for execution.'}>
    <a href="/app/research/data-readiness?format=csv" className="inline-flex min-h-11 items-center gap-2 text-sm underline underline-offset-4 focus-visible:ring-2 focus-visible:ring-ring"><ArrowLeft className="size-4" aria-hidden="true" />{zh ? '返回我的 CSV 数据' : 'Return to my CSV data'}</a>
    {error ? <p role="alert" className="rounded-md border border-destructive/40 p-3 text-sm">{zh ? '无法验证数据引用。请返回并重新打开已保存的导入。' : 'The data reference could not be verified. Return to your data and reopen the saved import.'}</p>
      : !reference ? <p role="status" className="text-sm">{zh ? '正在核对已保存的数据引用…' : 'Checking the saved data reference…'}</p>
      : <div className="min-w-0 space-y-5">
        <section className="space-y-3 border-y border-border py-5" aria-label={zh ? '选定数据及资格' : 'Selected data and qualification'}>
          <h3 className="break-words text-lg font-semibold">{selected?.label ?? (zh ? '没有可用的数据引用' : 'No usable data reference')}</h3>
          <p className="text-sm text-muted-foreground">{selected?.symbol} · {selected?.venue} · {selected?.interval} · {selected?.coverage.first_date ?? (zh ? '未知' : 'Unknown')} — {selected?.coverage.last_date ?? (zh ? '未知' : 'Unknown')}</p>
          <Badge variant="outline">{zh ? '仅供规划 · 尚不具备研究资格' : 'Planning only · research qualification insufficient'}</Badge>
          <ul className="list-disc space-y-1 pl-5 text-sm">{reference.eligibility.reasons.map((reason, i) => <li key={i} className="break-words" title={reason}>{explainCsvReason(reason, locale)}</li>)}</ul>
          <p className="max-w-prose text-sm text-muted-foreground">{zh ? '当前执行入口仅支持已注册的示例数据。此引用不会替换示例数据，也不会自动启动真实数据回测。' : 'The current runner supports registered fixture inputs. This reference will not replace a fixture or automatically start a real-data backtest.'}</p>
          <a href={`/api/research/data-snapshots/local-csv/${reference.snapshot_id}/reference.json`} download className="inline-flex min-h-11 items-center text-sm underline underline-offset-4 focus-visible:ring-2 focus-visible:ring-ring">{zh ? '下载已保存的规划引用' : 'Download saved planning reference'}</a>
        </section>
        {reference.dataset_ref && <section className="min-w-0 space-y-4" aria-label={zh ? '协议草案' : 'Protocol draft'}>
          <h3 className="font-semibold">{zh ? '协议草案' : 'Protocol draft'}</h3>
          <label className="block space-y-2 text-sm">{zh ? '研究问题' : 'Research question'}<textarea className={fieldClass} rows={3} maxLength={2000} value={question} onChange={event => setQuestion(event.target.value)} /></label>
          <div className="grid min-w-0 gap-4 sm:grid-cols-2">
            <label className="block space-y-2 text-sm">{zh ? '计划评估时间范围' : 'Planned evaluation window'}<input className={fieldClass} maxLength={500} value={evaluationWindow} onChange={event => setEvaluationWindow(event.target.value)} placeholder={zh ? '未知；待确认训练与样本外范围' : 'Unknown; verify train and out-of-sample periods'} /></label>
            <label className="block space-y-2 text-sm">{zh ? '待验证的交易成本' : 'Costs to verify'}<input className={fieldClass} maxLength={500} value={costs} onChange={event => setCosts(event.target.value)} placeholder={zh ? '未知；手续费、价差、滑点' : 'Unknown; fees, spread and slippage'} /></label>
          </div>
          <Button className="max-sm:min-h-11" disabled={!question.trim()} onClick={download}><Download className="size-4" aria-hidden="true" />{zh ? '下载协议草案' : 'Download protocol draft'}</Button>
          <p className="text-xs text-muted-foreground">{zh ? '仅保留您输入的计划和原始数据引用。不含结果，未提交执行。未填写的假设保持未知。' : 'Contains your plan and the original data reference. No results and no submission. Unspecified assumptions remain unknown.'}</p>
        </section>}
        <details className="min-w-0 border-t border-border"><summary className="min-h-11 cursor-pointer py-3 text-sm focus-visible:ring-2 focus-visible:ring-ring">{zh ? '数据引用详情' : 'Data reference details'}</summary><pre className="whitespace-pre-wrap break-all text-xs">{JSON.stringify(reference.dataset_ref, null, 2)}</pre><ul className="mt-3 space-y-2 text-xs">{reference.eligibility.reasons.map((reason, i) => <li key={i} className="break-words">{reason}</li>)}</ul></details>
      </div>}
  </Page>
}
