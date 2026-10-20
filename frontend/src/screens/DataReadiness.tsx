import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Download, RefreshCw, Upload } from 'lucide-react'
import { Page } from '@/components/page'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { usePreferences } from '@/lib/preferences'
import { realdataApi, MAX_SNAPSHOT_BYTES, type SnapshotCheck, type SnapshotErrorCode, type SnapshotReport } from '@/lib/realdata-api'

// Operate within the incumbent workstation: import and qualification first,
// original downloads beside allowed use, then non-passing checks before optional
// passing detail. The approved hierarchy never changes evidence or qualification.
const detailCopy = {
  en: { passed: 'Passed technical checks', allPassed: 'All reported technical checks passed. Research qualification above still applies.' },
  'zh-CN': { passed: '已通过的技术检查', allPassed: '报告中的技术检查均已通过，研究用途仍受上方资格结论限制。' },
}
// Page-local explanations preserve server codes in visible use labels or title
// metadata. Unknown codes remain verbatim; this is not a qualification adapter.
const evidenceTerms: Record<string, { en: string; 'zh-CN': string }> = {
  inspect_evidence_only: { en: 'Inspect evidence only', 'zh-CN': '仅可检查证据' },
  local_research_unverified: { en: 'Local research rights unverified', 'zh-CN': '本地研究使用权限未经核实' },
  historical_available_at_and_revision_history_unverified: { en: 'Historical availability and revisions unverified', 'zh-CN': '历史可获得时间与修订记录未经核实' },
  bar_values: { en: 'Price and volume bounds', 'zh-CN': '价格与成交量范围' },
  bar_time: { en: 'Session timestamps', 'zh-CN': '交易时段时间戳' },
  bar_order: { en: 'Unique chronological rows', 'zh-CN': '数据行去重与时间顺序' },
  session_coverage: { en: 'Daily session coverage', 'zh-CN': '日线交易时段覆盖' },
  unfinished_session: { en: 'Completed sessions only', 'zh-CN': '仅包含已结束的交易时段' },
  calendar_alignment: { en: 'Pinned calendar alignment', 'zh-CN': '固定交易日历对齐' },
  yahoo_alignment: { en: 'Retained Yahoo price alignment', 'zh-CN': '留存 Yahoo 价格对齐' },
  issuer_alignment: { en: 'Issuer-derived dividend alignment', 'zh-CN': '发行方派生分红数据对齐' },
  units: { en: 'Price and volume units', 'zh-CN': '价格与成交量单位' },
  corporate_actions: { en: 'Dividend source comparison', 'zh-CN': '分红来源比较' },
  source_rights: { en: 'Source usage rights', 'zh-CN': '数据来源使用权限' },
  point_in_time: { en: 'Historical availability and revisions', 'zh-CN': '历史可获得时间与修订记录' },
  source_session: { en: 'Vendor daily-session semantics', 'zh-CN': '供应商日线时段定义' },
  issuer_lineage: { en: 'Raw issuer lineage', 'zh-CN': '发行方原始文件来源链' },
}
type Busy = 'loading' | 'importing' | 'opening' | 'downloading' | null
const safeCodes: SnapshotErrorCode[] = ['unavailable', 'too_large', 'invalid_archive', 'not_found', 'request_failed', 'invalid_response', 'integrity']
function errorCode(error: unknown): SnapshotErrorCode {
  const code = error && typeof error === 'object' && 'code' in error ? error.code : null
  return safeCodes.includes(code as SnapshotErrorCode) ? code as SnapshotErrorCode : 'request_failed'
}

export function DataReadinessScreen() {
  const { t, locale } = usePreferences()
  const [history, setHistory] = useState<SnapshotReport[]>([])
  const [report, setReport] = useState<SnapshotReport | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [configured, setConfigured] = useState(false)
  const [busy, setBusy] = useState<Busy>('loading')
  const [error, setError] = useState<SnapshotErrorCode | null>(null)
  const mounted = useRef(true)

  useEffect(() => {
    mounted.current = true
    realdataApi.list().then(value => {
      if (mounted.current) { setHistory(value); setConfigured(true) }
    }).catch(cause => {
      if (mounted.current) setError(errorCode(cause))
    }).finally(() => { if (mounted.current) setBusy(null) })
    return () => { mounted.current = false }
  }, [])

  async function refresh() {
    setBusy('loading'); setError(null)
    try { setHistory(await realdataApi.list()); setConfigured(true) }
    catch (cause) { setError(errorCode(cause)); setConfigured(false) }
    finally { setBusy(null) }
  }
  async function open(id: string) {
    setBusy('opening'); setError(null)
    try { setReport(await realdataApi.get(id)) }
    catch (cause) { setError(errorCode(cause)) }
    finally { setBusy(null) }
  }
  async function importSnapshot() {
    if (!file || busy || !configured) return
    setBusy('importing'); setError(null)
    try {
      const result = await realdataApi.import(file)
      setReport(result)
      setHistory(current => [result, ...current.filter(item => item.snapshot_id !== result.snapshot_id)])
    } catch (cause) { setError(errorCode(cause)) }
    finally { setBusy(null) }
  }
  async function download(kind: 'archive' | 'report') {
    if (!report || busy) return
    setBusy('downloading'); setError(null)
    try {
      const blob = await realdataApi.download(report.snapshot_id, kind,
        kind === 'archive' ? report.lineage.archive_sha256 : report.report_digest)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `SPY-${report.snapshot_id}${kind === 'archive' ? '.zip' : '-report.json'}`
      document.body.append(anchor)
      anchor.click(); anchor.remove()
      setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch (cause) { setError(errorCode(cause)) }
    finally { setBusy(null) }
  }

  return <Page title={t('readiness.title')} description={t('readiness.description')}
    actions={<Button variant="outline" size="sm" className="max-sm:min-h-11" onClick={refresh} disabled={busy !== null}>
      <RefreshCw className="size-3.5" aria-hidden="true" />{t('readiness.refresh')}
    </Button>}>
    <section aria-labelledby="snapshot-import" className="space-y-3 border-y border-border py-4">
      <h3 id="snapshot-import" className="text-sm font-semibold">{t('readiness.importTitle')}</h3>
      <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-end">
        <div className="min-w-0 flex-1 space-y-1.5">
          <label htmlFor="snapshot-zip" className="block text-xs font-medium">{t('readiness.file')}</label>
          <input id="snapshot-zip" type="file" accept=".zip,application/zip" disabled={!configured || busy !== null}
            aria-describedby="snapshot-format" className="block w-full min-w-0 rounded-md border border-input bg-background p-2 text-sm file:mr-3 file:rounded file:border-0 file:bg-secondary file:px-3 file:py-1 file:text-secondary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            onChange={event => {
              const selected = event.target.files?.[0] ?? null
              setError(null)
              if (selected && selected.size > MAX_SNAPSHOT_BYTES) { setFile(null); setError('too_large') }
              else if (selected && selected.size === 0) { setFile(null); setError('invalid_archive') }
              else setFile(selected)
            }} />
        </div>
        <Button className="max-sm:min-h-11" onClick={importSnapshot} disabled={!file || !configured || busy !== null}>
          <Upload className="size-4" aria-hidden="true" />{t('readiness.import')}
        </Button>
      </div>
      <p id="snapshot-format" className="text-xs text-muted-foreground">{t('readiness.format')}</p>
      <p className="max-w-3xl text-xs text-muted-foreground">{t('readiness.boundary')}</p>
    </section>
    {busy && <p role="status" className="text-sm text-muted-foreground">{t(`readiness.${busy}`)}</p>}
    {error && <p role="alert" className="break-words border border-destructive/40 p-3 text-sm text-destructive">{t(`readiness.error.${error}`)}</p>}
    {report ? <SnapshotDetail report={report} busy={busy !== null} download={download} />
      : configured && <p className="text-sm text-muted-foreground">{t('readiness.select')}</p>}
    <section aria-labelledby="snapshot-history" className="space-y-3 border-t border-border pt-4">
      <h3 id="snapshot-history" className="text-sm font-semibold">{t('readiness.history')}</h3>
      {configured && history.length === 0 && busy !== 'loading' && <div className="space-y-1 py-2">
        <p className="text-sm">{t('readiness.empty')}</p>
        <p className="text-xs text-muted-foreground">{t('readiness.emptyDetail')}</p>
      </div>}
      {history.length > 0 && <ul className="divide-y divide-border">
        {history.map(item => <li key={item.snapshot_id} className="flex min-w-0 flex-wrap items-center gap-2 py-2">
          <Button variant="outline" size="sm" disabled={!configured || busy !== null} onClick={() => open(item.snapshot_id)}
            aria-pressed={report?.snapshot_id === item.snapshot_id} className="h-auto min-h-9 w-full min-w-0 max-w-full whitespace-normal break-all text-left max-sm:min-h-11 sm:w-auto">
            {t('readiness.reopen', { date: item.imported_at, id: item.snapshot_id.slice(0, 12) })}
          </Button>
          <Badge variant="outline">{t(`readiness.${item.evidence_kind}`)}</Badge>
        </li>)}
      </ul>}
    </section>
    <span className="sr-only">{locale === 'zh-CN' ? '服务端证据保持原文。' : 'Server evidence is preserved verbatim.'}</span>
  </Page>
}

function SnapshotDetail({ report, busy, download }: {
  report: SnapshotReport; busy: boolean; download: (kind: 'archive' | 'report') => Promise<void>;
}) {
  const { t, locale } = usePreferences()
  const unknown = t('readiness.unknown')
  const text = (value: string | null | undefined) => value == null || value === '' ? unknown : value
  const number = (value: number | null | undefined) => value == null ? unknown : value.toLocaleString(locale)
  const source = report.source
  const copy = detailCopy[locale]
  const explain = (value: string) => evidenceTerms[value]?.[locale] ?? value
  const nonPassing = report.checks.filter(check => check.status !== 'PASS')
  const passing = report.checks.filter(check => check.status === 'PASS')
  return <div className="min-w-0 space-y-6">
    <div className="grid min-w-0 gap-6 xl:grid-cols-2">
      <section aria-labelledby="snapshot-qualification" className="min-w-0 space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <h3 id="snapshot-qualification" className="text-base font-semibold">{t('readiness.qualification')}</h3>
          <Badge variant={report.qualification.status === 'REJECT' ? 'destructive' : 'outline'}>
            {t(`readiness.${report.qualification.status}`)}
          </Badge>
          <Badge variant="outline">{t(`readiness.${report.evidence_kind}`)}</Badge>
        </div>
        <div className="space-y-1">
          <h4 className="text-xs font-medium text-muted-foreground">{t('readiness.allowed')}</h4>
          {report.qualification.allowed_use.length ? <ul className="space-y-1 text-sm">
            {report.qualification.allowed_use.map((use, index) => <li key={index} className="break-words">
              <span title={use}>{explain(use)}</span>
              {explain(use) !== use && <code className="block text-xs text-muted-foreground">{use}</code>}
            </li>)}
          </ul> : <p className="text-sm">{t('readiness.noAllowed')}</p>}
        </div>
        <div className="space-y-2">
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" className="max-sm:min-h-11" onClick={() => download('archive')} disabled={busy}><Download className="size-3.5" aria-hidden="true" />{t('readiness.original')}</Button>
            <Button variant="outline" size="sm" className="max-sm:min-h-11" onClick={() => download('report')} disabled={busy}><Download className="size-3.5" aria-hidden="true" />{t('readiness.report')}</Button>
          </div>
          <p className="max-w-3xl text-xs text-muted-foreground">{t('readiness.pinned')}</p>
        </div>
        <div className="space-y-1">
          <h4 className="text-xs font-medium text-muted-foreground">{t('readiness.reasons')}</h4>
          {report.qualification.reasons.length ? <ul className="list-disc space-y-1 pl-4 text-sm">
            {report.qualification.reasons.map((reason, index) => <li key={index} className="break-words" title={reason}>{reason}</li>)}
          </ul> : <p className="text-sm">{t('readiness.noReasons')}</p>}
        </div>
        <dl className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)] gap-x-4 gap-y-2 text-xs">
          <Fact label={t('readiness.structural')}>{t(`readiness.${report.qualification.structural_status}`)}</Fact>
          <Fact label="R1">{text(report.qualification.R1)}</Fact>
          <Fact label="R2">{text(report.qualification.R2)}</Fact>
          <Fact label={t('readiness.rights')}>{text(source.license_scope)} / {text(source.license_evidence)}</Fact>
        </dl>
      </section>
      <section aria-labelledby="snapshot-source" className="min-w-0 space-y-3">
        <h3 id="snapshot-source" className="text-sm font-semibold">{t('readiness.source')}</h3>
        <dl className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.7fr)] gap-x-4 gap-y-2 text-xs">
          <Fact label={t('readiness.provider')}>{text(source.provider)} / {text(source.feed)}</Fact>
          <Fact label={t('readiness.received')}>{text(source.received_at)}</Fact>
          <Fact label={t('readiness.pit')}><span title={source.pit_status ?? undefined}>{explain(text(source.pit_status))}</span></Fact>
          <Fact label={t('readiness.sessions')}>{text(source.session_semantics)}</Fact>
          <Fact label={t('readiness.units')}>{text(source.price_unit)} / {text(source.volume_unit)}</Fact>
          <Fact label="URL">{text(source.url)}</Fact>
        </dl>
        <p className="max-w-prose text-xs text-muted-foreground">{t('readiness.assertions')}</p>
      </section>
    </div>
    <section aria-labelledby="snapshot-coverage" className="min-w-0 space-y-3 border-t border-border pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 id="snapshot-coverage" className="text-sm font-semibold">{t('readiness.coverage')}</h3>
        <Badge variant="outline">{t(`readiness.${report.freshness.status}`)}</Badge>
      </div>
      <dl className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] gap-x-4 gap-y-2 text-xs lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1.3fr)]">
        <Fact label={t('readiness.rows')}>{number(report.coverage.rows)}</Fact>
        <Fact label={t('readiness.expected')}>{number(report.coverage.expected_sessions)}</Fact>
        <Fact label={t('readiness.range')}>{text(report.coverage.first_date)} — {text(report.coverage.last_date)}</Fact>
        <Fact label={t('readiness.age')}>{number(report.freshness.age_sessions)}</Fact>
        <Fact label={t('readiness.latest')}>{text(report.freshness.latest_complete_session)}</Fact>
        <Fact label={t('readiness.last')}>{text(report.freshness.last_session)}</Fact>
        <Fact label={t('readiness.asOf')}>{text(report.freshness.as_of)}</Fact>
      </dl>
      <div className="grid gap-3 text-xs md:grid-cols-2">
        {(['missing_sessions', 'unexpected_sessions'] as const).map(key => <div key={key} className="min-w-0 space-y-1">
          <h4 className="font-medium text-muted-foreground">{t(key === 'missing_sessions' ? 'readiness.missing' : 'readiness.unexpected')}</h4>
          <p className="break-words font-mono">{report.coverage[key] === null ? unknown : `${number(report.coverage[key].length)}${report.coverage[key].length ? ` · ${report.coverage[key].join(', ')}` : ''}`}</p>
        </div>)}
      </div>
      <p className="max-w-3xl text-xs text-muted-foreground">{t('readiness.recencyNote')}</p>
    </section>
    <section aria-labelledby="snapshot-checks" className="min-w-0 space-y-3 border-t border-border pt-4">
      <h3 id="snapshot-checks" className="text-sm font-semibold">{t('readiness.checks')}</h3>
      {nonPassing.length > 0 && <CheckTable checks={nonPassing} label={t('readiness.checks')} />}
      {report.checks.length === 0 && <p className="text-xs text-muted-foreground">{t('readiness.noChecks')}</p>}
      {passing.length > 0 && <details key={report.snapshot_id} className="min-w-0">
        <summary className="cursor-pointer text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring max-sm:min-h-11 max-sm:py-3">
          {locale === 'zh-CN' ? `${copy.passed}（${passing.length}）` : `${copy.passed} (${passing.length})`}
        </summary>
        <div className="mt-3"><CheckTable checks={passing} label={copy.passed} /></div>
      </details>}
      {passing.length > 0 && nonPassing.length === 0 && <p className="text-xs text-muted-foreground">{copy.allPassed}</p>}
    </section>
    <section aria-labelledby="snapshot-actions" className="space-y-3 border-t border-border pt-4">
      <h3 id="snapshot-actions" className="text-sm font-semibold">{t('readiness.actions')}</h3>
      <dl className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-x-4 gap-y-2 text-xs">
        <Fact label={t('readiness.issuer')}>{number(report.corporate_actions.issuer_events)}</Fact>
        <Fact label={t('readiness.yahoo')}>{number(report.corporate_actions.yahoo_events)}</Fact>
      </dl>
      {report.corporate_actions.conflicts.length ? <ul className="list-disc space-y-1 pl-4 text-sm">
        {report.corporate_actions.conflicts.map((conflict, index) => <li key={index} className="break-words" title={conflict}>{conflict}</li>)}
      </ul> : <p className="text-xs text-muted-foreground">{t('readiness.noConflicts')}</p>}
    </section>
    <section className="min-w-0 space-y-3 border-t border-border pt-4">
      <details className="min-w-0">
        <summary className="cursor-pointer text-sm font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring max-sm:min-h-11 max-sm:py-3">{t('readiness.lineage')}</summary>
        <dl className="mt-3 grid grid-cols-[minmax(0,1fr)_minmax(0,2fr)] gap-x-4 gap-y-2 text-xs">
          <Fact label={t('readiness.snapshotId')}>{report.snapshot_id}</Fact>
          <Fact label={t('readiness.reportDigest')}>{report.report_digest}</Fact>
          <Fact label={t('readiness.normalized')}>{report.lineage.normalized_sha256}</Fact>
          <Fact label={t('readiness.checker')}>{report.lineage.checker_sha256}</Fact>
          <Fact label={t('readiness.calendar')}>{report.lineage.calendar_id} · {report.lineage.calendar_version}</Fact>
          <Fact label={t('readiness.imported')}>{report.imported_at}</Fact>
        </dl>
        <h4 className="mt-4 text-xs font-medium text-muted-foreground">{t('readiness.member')}</h4>
        <ul className="mt-2 divide-y divide-border text-xs">{report.lineage.files.map(file => <li key={file.path} className="space-y-1 py-2 font-mono">
          <p className="break-all">{file.path}</p><p className="break-all text-muted-foreground">{file.sha256} · {number(file.bytes)}</p>
        </li>)}</ul>
      </details>
    </section>
  </div>
}
function CheckTable({ checks, label }: { checks: SnapshotCheck[]; label: string }) {
  const { t, locale } = usePreferences()
  const unknown = t('readiness.unknown')
  const text = (value: string | null | undefined) => value == null || value === '' ? unknown : value
  const number = (value: number | null | undefined) => value == null ? unknown : value.toLocaleString(locale)
  return <div className="max-w-full overflow-x-auto" tabIndex={0} role="region" aria-label={label}>
    <table aria-label={label} className="w-full min-w-[640px] table-fixed text-left text-xs">
      <thead className="border-b border-border text-muted-foreground"><tr>
        <th className="w-[38%] py-2 pr-3 font-medium">{t('readiness.check')}</th>
        <th className="w-[9%] py-2 pr-3 font-medium">{t('readiness.count')}</th>
        <th className="w-[23%] py-2 pr-3 font-medium">{t('readiness.location')}</th>
        <th className="w-[30%] py-2 font-medium">{t('readiness.comparison')}</th>
      </tr></thead>
      <tbody className="divide-y divide-border">{checks.map((check, index) => <tr key={`${check.code}-${index}`} className="align-top">
        <td className="space-y-1 break-words py-3 pr-3">
          <div><Badge variant={check.status === 'REJECT' ? 'destructive' : 'outline'}>{t(`readiness.${check.status}`)}</Badge></div>
          <p className="font-medium" title={check.code}>{evidenceTerms[check.code]?.[locale] ?? check.code}</p><p title={check.message}>{check.message}</p>
        </td>
        <td className="py-3 pr-3 font-mono tabular-nums">{number(check.count)}</td>
        <td colSpan={2} className="py-3">{check.locations.length ? <ul className="space-y-3">
          {check.locations.map((location, index) => <li key={index} className="grid grid-cols-[minmax(0,23fr)_minmax(0,30fr)] gap-3">
            <div className="min-w-0 break-words font-mono">{text(location.date)}<br />{t('readiness.row')} {number(location.row)} · {location.field}</div>
            <div className="min-w-0 break-words"><p>{t('readiness.expectedValue')}: <span className="font-mono">{text(location.expected)}</span></p>
              <p>{t('readiness.actualValue')}: <span className="font-mono">{text(location.actual)}</span></p></div>
          </li>)}
        </ul> : <span className="text-muted-foreground">{unknown}</span>}</td>
      </tr>)}</tbody>
    </table>
  </div>
}
function Fact({ label, children }: { label: string; children: ReactNode }) {
  return <><dt className="min-w-0 text-muted-foreground">{label}</dt><dd className="min-w-0 break-words font-mono tabular-nums [overflow-wrap:anywhere]">{children}</dd></>
}
