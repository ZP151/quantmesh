import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Download, RefreshCw, Upload } from 'lucide-react'
import { Page } from '@/components/page'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { usePreferences } from '@/lib/preferences'
import { frozenCopy } from '@/lib/frozen-experiments-copy'
import { frozenExperimentsApi, MAX_FROZEN_BYTES, type FrozenArtifact, type FrozenErrorCode, type FrozenExperiment } from '@/lib/frozen-experiments-api'

// Extend the incumbent Operate console: recorded authority first, then assumptions,
// imported metrics and fixed diagnostics, with original bytes behind disclosures.
type Busy = 'loading' | 'importing' | 'opening' | 'downloading' | null
const codes: FrozenErrorCode[] = ['unavailable', 'too_large', 'invalid_archive', 'snapshot_required', 'not_found', 'request_failed', 'invalid_response', 'integrity']
function safeError(error: unknown): FrozenErrorCode {
  const code = error && typeof error === 'object' && 'code' in error ? error.code : null
  return codes.includes(code as FrozenErrorCode) ? code as FrozenErrorCode : 'request_failed'
}
function Datum({ label, children, mono = false }: { label: string; children: ReactNode; mono?: boolean }) {
  return <div className="min-w-0 space-y-1"><dt className="text-xs text-muted-foreground">{label}</dt>
    <dd className={mono ? 'break-all font-mono text-xs tabular-nums' : 'break-words text-sm'}>{children}</dd></div>
}
function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section aria-label={title} className="min-w-0 space-y-3 border-t border-border py-5">
    <h3 className="text-base font-semibold">{title}</h3>{children}</section>
}

export function FrozenExperimentsScreen() {
  const { locale } = usePreferences()
  const c = frozenCopy[locale]
  const [history, setHistory] = useState<FrozenExperiment[]>([])
  const [record, setRecord] = useState<FrozenExperiment | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [configured, setConfigured] = useState(false)
  const [busy, setBusy] = useState<Busy>('loading')
  const [error, setError] = useState<FrozenErrorCode | null>(null)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    frozenExperimentsApi.list().then(value => {
      if (mounted.current) { setHistory(value); setConfigured(true) }
    }).catch(cause => { if (mounted.current) setError(safeError(cause)) })
      .finally(() => { if (mounted.current) setBusy(null) })
    return () => { mounted.current = false }
  }, [])
  async function refresh() {
    setBusy('loading'); setError(null)
    try { setHistory(await frozenExperimentsApi.list()); setConfigured(true) }
    catch (cause) { setError(safeError(cause)); setConfigured(false) }
    finally { setBusy(null) }
  }
  async function open(id: string) {
    setBusy('opening'); setError(null)
    try { setRecord(await frozenExperimentsApi.get(id)) }
    catch (cause) { setError(safeError(cause)) }
    finally { setBusy(null) }
  }
  async function importExperiment() {
    if (!file || busy || !configured) return
    setBusy('importing'); setError(null)
    try {
      const value = await frozenExperimentsApi.import(file)
      setRecord(value)
      setHistory(current => [value, ...current.filter(item => item.package_id !== value.package_id)])
    } catch (cause) { setError(safeError(cause)) }
    finally { setBusy(null) }
  }
  async function download(artifact: FrozenArtifact) {
    if (!record || busy) return
    setBusy('downloading'); setError(null)
    try {
      const blob = await frozenExperimentsApi.download(record.package_id, artifact)
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      const extension = artifact.kind === 'archive' ? 'zip' : ['report', 'review'].includes(artifact.kind) ? 'md' : 'json'
      anchor.download = `${record.package_id}-${artifact.kind}.${extension}`
      document.body.append(anchor); anchor.click(); anchor.remove()
      setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch (cause) { setError(safeError(cause)) }
    finally { setBusy(null) }
  }
  const numeric = (value: number | null, percent = false) => value === null ? c.unknown : new Intl.NumberFormat(locale, percent
    ? { style: 'percent', minimumFractionDigits: 2, maximumFractionDigits: 2 }
    : { maximumFractionDigits: 2 }).format(value)
  const primary = record?.cases[0]
  const downloadNames = { archive: c.archive, protocol: c.protocolDownload, receipt: c.receipt, result: c.result,
    report: c.report, timeline: c.timeline, review: c.review, verification: c.verification, manifest: c.manifest }
  const dataLink = <Link to="/research/data-readiness" className="text-sm underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{c.dataLink}</Link>

  return <Page title={c.title} description={c.description} actions={<Button variant="outline" size="sm" onClick={refresh} disabled={busy !== null}>
    <RefreshCw className="size-3.5" aria-hidden="true" />{c.refresh}</Button>}>
    {busy && <p role="status" className="text-sm text-muted-foreground">{c[busy]}</p>}
    {error && <div role="alert" className="space-y-2 rounded-md border border-border bg-muted/40 p-3 text-sm">
      <p>{c[error]}</p>{error === 'snapshot_required' && dataLink}</div>}
    {record && <Section title={c.verdict}>
      <div className="flex flex-wrap items-center gap-3"><h4 className="font-mono text-sm">{record.experiment_id}</h4>
        <Badge variant="destructive">{c.reject}</Badge><Badge variant="outline">{c.consumed}</Badge></div>
      <dl className="grid gap-4 sm:grid-cols-2"><Datum label={c.proxy}>{c.reject}</Datum>
        <Datum label={c.formal}>R1 {c.insufficient} · R2 {c.insufficient} · R3 {c.unauthorized}</Datum></dl>
      <p className="max-w-prose text-sm">{c.reason}</p><p className="max-w-prose text-sm">{c.notBlind}</p>
      <p className="max-w-prose text-sm text-muted-foreground">{c.next}</p>
    </Section>}

    <Section title={c.importTitle}>
      <div className="flex flex-wrap items-end gap-3"><div className="min-w-0 flex-1 space-y-1.5">
        <label htmlFor="frozen-experiment-zip" className="block text-xs font-medium">{c.file}</label>
        <input id="frozen-experiment-zip" type="file" accept=".zip,application/zip" disabled={!configured || busy !== null}
          aria-describedby="frozen-format" className="block w-full min-w-0 rounded-md border border-input bg-background p-2 text-sm file:mr-3 file:rounded file:border-0 file:bg-secondary file:px-3 file:py-1 file:text-secondary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          onChange={event => {
            const selected = event.target.files?.[0] ?? null
            setError(null)
            if (selected && selected.size > MAX_FROZEN_BYTES) { setFile(null); setError('too_large') }
            else setFile(selected)
          }} /></div>
        <Button onClick={importExperiment} disabled={!file || !configured || busy !== null}><Upload className="size-4" aria-hidden="true" />{c.import}</Button>
      </div><p id="frozen-format" className="text-xs text-muted-foreground">{c.format}</p>
    </Section>
    {!busy && !history.length && configured && <div className="space-y-2 py-4"><h3 className="font-medium">{c.empty}</h3>
      <p className="max-w-prose text-sm text-muted-foreground">{c.emptyHint}</p>{dataLink}</div>}
    {history.length > 0 && <details open={!record} className="min-w-0 border-t border-border py-3">
      <summary className="cursor-pointer text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{c.history} ({history.length})</summary>
      <ul className="mt-3 divide-y divide-border">{history.map(item => <li key={item.package_id} className="flex flex-wrap items-center justify-between gap-3 py-3">
        <div className="min-w-0 space-y-1"><p className="break-all font-mono text-xs">{item.experiment_id}</p>
          <p className="text-xs text-muted-foreground">{c.imported}: {item.imported_at}</p><p className="font-mono text-xs text-muted-foreground">{item.package_id.slice(0, 16)}…</p></div>
        <Button variant="outline" size="sm" disabled={busy !== null} onClick={() => open(item.package_id)} aria-label={`${c.reopen} ${item.experiment_id} ${item.package_id.slice(0, 12)}`}>{c.reopen}</Button>
      </li>)}</ul></details>}

    {record && primary && <>
      <div className="grid min-w-0 gap-x-8 lg:grid-cols-2">
        <Section title={c.protocol}><dl className="grid gap-4 sm:grid-cols-2">
          <Datum label={c.strategy}>SMA100 / SPY · long / cash</Datum><Datum label={c.window} mono>{record.protocol.final_window.join(' → ')}</Datum>
          <Datum label={c.capital}>USD {numeric(record.protocol.capital_usd)}</Datum><Datum label={c.cost}>5 bps</Datum>
          <Datum label={c.stress}>10 bps</Datum><Datum label={c.gross}>0 bps</Datum><Datum label={c.delay}>+1 {c.session}</Datum>
        </dl><p className="text-xs text-muted-foreground">{c.costUnknown}</p>
          <dl className="space-y-3"><Datum label={c.comparison}>{record.protocol.comparison}</Datum><Datum label={c.execution}>{record.protocol.execution}</Datum></dl>
        </Section>
        <Section title={c.trials}><dl className="grid gap-4 sm:grid-cols-2">
          <Datum label={c.current}>{record.trials.current}</Datum><Datum label={c.searched}>{record.trials.searched}</Datum>
          <Datum label={c.prior}>{c.unknown}</Datum><Datum label={c.chronology}>{c.unverified}</Datum>
          <Datum label={c.frozen} mono>{record.protocol.frozen_at_claimed}</Datum>
          <Datum label={c.claimedBefore}>{record.protocol.created_before_results_claimed ? c.yes : c.no}</Datum>
        </dl><p className="text-sm">{c.exposure}</p><p className="max-w-prose text-xs text-muted-foreground">{c.chronologyHint}</p></Section>
      </div>
      <Section title={c.primary}><Badge variant="outline">{c.primaryLabel}</Badge><p className="text-sm text-muted-foreground">{c.importedMetrics}</p>
        <dl className="grid gap-x-6 gap-y-5 sm:grid-cols-3 xl:grid-cols-4">
          <Datum label={c.net}>{numeric(primary.strategy.total_return, true)}</Datum><Datum label={c.benchmark}>{numeric(primary.benchmark.total_return, true)}</Datum>
          <Datum label={c.delta}>{numeric(primary.net_total_return_difference, true)}</Datum><Datum label={c.profit}>{numeric(primary.strategy.net_profit_usd)}</Datum>
          <Datum label={c.cagr}>{numeric(primary.strategy.cagr, true)}</Datum><Datum label={c.drawdown}>{numeric(primary.strategy.max_drawdown, true)}</Datum>
          <Datum label={c.underwater}>{numeric(primary.strategy.max_underwater_sessions)}</Datum><Datum label={c.es}>{numeric(primary.strategy.historical_es_95, true)}</Datum>
          <Datum label={c.friction}>{numeric(primary.strategy.friction_usd)}</Datum><Datum label={c.turnover}>{numeric(primary.strategy.gross_traded_notional_over_initial_capital)}</Datum>
          <Datum label={c.sharpe}>{numeric(primary.strategy.naive_sharpe_rf_zero)}</Datum>
        </dl><p className="max-w-prose text-xs text-muted-foreground">{c.interpretation}</p>
        <details className="pt-2"><summary className="cursor-pointer text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{c.inference}</summary>
          <p className="mt-3 max-w-prose text-xs text-muted-foreground">{c.confidence}</p>
          {primary.inference.length ? <div className="mt-3 overflow-x-auto"><table className="w-full text-left text-xs" aria-label={c.inference}>
            <thead><tr>{[c.block, c.mean, c.lower, c.upper].map(title => <th key={title} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">{title}</th>)}</tr></thead>
            <tbody>{primary.inference.map((item, i) => <tr key={i} className="border-t border-border font-mono tabular-nums">
              <td className="px-3 py-2">{numeric(item.block_sessions)}</td><td className="px-3 py-2">{numeric(item.mean_daily_difference, true)}</td>
              <td className="px-3 py-2">{numeric(item.one_sided_95_lower_daily, true)}</td><td className="px-3 py-2">{numeric(item.one_sided_95_upper_daily, true)}</td>
            </tr>)}</tbody></table></div> : <p className="mt-3 text-sm">{c.noInference}</p>}
        </details>
      </Section>
      <Section title={c.diagnostics}><p className="max-w-prose text-sm text-muted-foreground">{c.diagnosticHint}</p>
        <div className="overflow-x-auto"><table className="w-full text-left text-xs" aria-label={c.diagnostics}>
          <thead><tr>{[c.case, c.net, c.benchmark, c.delta, c.drawdown].map(title => <th key={title} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">{title}</th>)}</tr></thead>
          <tbody>{record.cases.map(item => <tr key={item.case_id} className={item.primary ? 'border-t border-border bg-muted/50' : 'border-t border-border'}>
            <th scope="row" className="whitespace-nowrap px-3 py-3 text-left font-mono font-normal">{item.case_id}{item.primary && <span className="sr-only"> · {c.primaryLabel}</span>}</th>
            {[item.strategy.total_return, item.benchmark.total_return, item.net_total_return_difference, item.strategy.max_drawdown].map((value, i) => <td key={i} className="whitespace-nowrap px-3 py-3 font-mono tabular-nums">{numeric(value, true)}</td>)}
          </tr>)}</tbody></table></div>
      </Section>
      <Section title={c.source}><div className="flex flex-wrap items-center gap-3"><Badge variant="outline">{record.data.evidence_kind === 'fixture' ? c.fixture : c.real}</Badge>{dataLink}</div>
        <dl className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"><Datum label={c.qualification}>{c.insufficient}</Datum><Datum label={c.rights}>{c.unverified}</Datum>
          <Datum label={c.pit}>{c.unverified}</Datum><Datum label={c.executable}>{c.unverified}</Datum></dl>
        <div className="space-y-2"><h4 className="text-sm font-medium">{c.conflict} · {record.data.dividend_conflict.date}</h4>
          <p className="font-mono text-xs">{c.issuer}: {record.data.dividend_conflict.issuer_usd} · {c.yahoo}: {record.data.dividend_conflict.yahoo_usd}</p></div>
        <details><summary className="cursor-pointer text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{c.missing}</summary>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-muted-foreground">{record.missing_evidence.map(text => <li key={text}>{text}</li>)}</ul></details>
      </Section>
      <Section title={c.evidence}><p className="max-w-prose text-sm text-muted-foreground">{c.downloadHint}</p>
        <div className="flex flex-wrap gap-2">{record.downloads.map(artifact => <Button key={artifact.kind} variant="outline" size="sm" disabled={busy !== null} onClick={() => download(artifact)}>
          <Download className="size-3.5" aria-hidden="true" />{downloadNames[artifact.kind]}</Button>)}</div>
        <details className="pt-2"><summary className="cursor-pointer text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{c.lineage}</summary>
          <dl className="my-4 space-y-3"><Datum label={c.packageId} mono>{record.package_id}</Datum><Datum label={c.snapshotId} mono>{record.snapshot_id}</Datum>
            <Datum label={c.protocolId} mono>{record.protocol.sha256}</Datum><Datum label={c.imported} mono>{record.imported_at}</Datum></dl>
          <div className="overflow-x-auto"><table className="w-full text-left text-xs" aria-label={c.lineage}><thead><tr>
            {[c.path, c.digest, c.bytes].map(title => <th key={title} scope="col" className="px-3 py-2 font-medium">{title}</th>)}</tr></thead>
            <tbody>{record.lineage.map(item => <tr key={item.path} className="border-t border-border font-mono"><th scope="row" className="px-3 py-2 text-left font-normal">{item.path}</th>
              <td className="break-all px-3 py-2">{item.sha256}</td><td className="px-3 py-2 tabular-nums">{item.bytes}</td></tr>)}</tbody></table></div>
        </details>
      </Section>
    </>}
  </Page>
}
