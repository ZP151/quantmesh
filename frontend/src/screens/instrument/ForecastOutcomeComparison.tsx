import { useMemo } from 'react'

import { InstrumentChart, type ChartLine } from '@/components/charts/InstrumentChart'
import type { DecisionOutcomeReviewState } from '@/lib/api'
import { usePreferences } from '@/lib/preferences'

type Comparison = DecisionOutcomeReviewState['forecast_comparison']
type Outcome = DecisionOutcomeReviewState['outcome']

/** Separate series ensure a missing daily close is never connected across a gap. */
function actualSegments(rows: Comparison['rows'], label: string, color: string): ChartLine[] {
  const segments: ChartLine[] = []
  let current: ChartLine | null = null
  for (const row of rows) {
    if (row.actual_close === null || row.actual_close === undefined) {
      current = null
      continue
    }
    if (current === null) {
      current = { color, key: `actual-${row.session}`, label, pointMarkersVisible: true, points: [] }
      segments.push(current)
    }
    current.points = [...current.points, { timestamp: row.timestamp, value: row.actual_close }]
  }
  return segments
}

export function ForecastOutcomeComparison({ comparison, outcome, saved }: {
  comparison: Comparison
  outcome: Outcome
  saved: boolean
}) {
  const { locale, resolvedTheme, t } = usePreferences()
  const root = outcome.root_packet
  const forecast = root.evidence.forecast_paths.find((path) => path.sessions === comparison.horizon_sessions)
  const number = new Intl.NumberFormat(locale, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  const unavailable = t('screen.workspace.reviewUnavailableValue')
  const price = (value: number | null | undefined) => value == null ? unavailable : number.format(value)
  const money = (value: number | null | undefined) => value == null ? unavailable : `${price(value)} ${root.instrument.currency}`
  const complete = comparison.status === 'complete'
  const labels = useMemo(() => ({
    attribution: t('screen.workspace.chartAttribution'),
    caption: t('outcomeComparison.caution'),
    chart: t('outcomeComparison.title'),
    dataTable: t('outcomeComparison.table'),
    forecast: t('outcomeComparison.median'),
    forecastBoundary: t('outcomeComparison.boundary'),
    forecastMedianLine: t('outcomeComparison.medianLine'),
    observed: t('outcomeComparison.before'),
    observedClose: t('outcomeComparison.before'),
    timestamp: t('screen.workspace.timestamp'),
    series: t('screen.workspace.series'),
    value: t('screen.workspace.value'),
  }), [t])
  const indicators = useMemo(() => actualSegments(
    comparison.rows, t('outcomeComparison.actual'), resolvedTheme === 'dark' ? '#fbbf24' : '#92400e',
  ), [comparison.rows, resolvedTheme, t])
  const primary = useMemo(() => ({
    instrument: root.instrument,
    range: root.selected_range,
    bars: root.scenario_lab?.history.bars.slice(-10) ?? [],
  }), [root])

  return (
    <section className="min-w-0 space-y-3 border-y border-border py-4" aria-label={t('outcomeComparison.title')}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">{t('outcomeComparison.title')}</h3>
        <span className="text-xs text-muted-foreground">{t(saved ? 'outcomeComparison.frozen' : 'outcomeComparison.preview')}</span>
      </div>
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-xs">
        <span className="font-medium">{t(`outcomeComparison.status.${comparison.status}`)}</span>
        <span>{t('outcomeComparison.count', { actual: String(comparison.observed_sessions), total: String(comparison.horizon_sessions) })}</span>
        {root.evidence.forecast_synthetic && <span className="text-muted-foreground">{t('outcomeComparison.synthetic')}</span>}
      </div>
      {comparison.rows.length > 0 && forecast && (
        <>
          <p className="text-xs text-muted-foreground">{t('outcomeComparison.actualLegend')}</p>
          <InstrumentChart compactLabels appearance={resolvedTheme} forecast={forecast} indicators={indicators}
            labels={labels} locale={locale} mode="line" primary={primary} />
        </>
      )}
      {!complete && <p className="text-xs leading-relaxed text-muted-foreground" title={comparison.reason ?? undefined}>{t('outcomeComparison.incomplete')}</p>}
      <dl className="grid grid-cols-1 gap-3 border-y border-border py-3 sm:grid-cols-2">
        {([
          ['outcomeComparison.mae', money(complete ? comparison.mean_absolute_error : null)],
          ['outcomeComparison.baseline', money(complete ? comparison.benchmark_mae : null)],
          ['outcomeComparison.hits', complete && comparison.interval_hits != null ? `${comparison.interval_hits} / ${comparison.horizon_sessions}` : unavailable],
          ['outcomeComparison.terminal', money(complete ? comparison.terminal_error : null)],
        ] as const).map(([label, value]) => (
          <div className="min-w-0 space-y-1" key={label}>
            <dt className="text-xs text-muted-foreground">{t(label)}</dt>
            <dd className="font-mono text-sm tabular-nums [overflow-wrap:anywhere]">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-xs leading-relaxed text-muted-foreground">{t('outcomeComparison.caution')}</p>
      <details className="min-w-0">
        <summary className="cursor-pointer text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{t('outcomeComparison.details')}</summary>
        <div className="mt-3 overflow-x-auto focus-visible:ring-2 focus-visible:ring-ring" tabIndex={0} role="region" aria-label={t('outcomeComparison.table')}>
          <table className="w-full text-right text-xs" aria-label={t('outcomeComparison.table')}>
            <thead><tr className="border-b border-border">
              {[t('outcomeComparison.session'), t('outcomeComparison.date'), 'P10', 'P50', 'P90', t('outcomeComparison.actual'), t('outcomeComparison.error'), t('outcomeComparison.hit')].map((label) => <th className="whitespace-nowrap px-2 py-2 font-medium" key={label} scope="col">{label}</th>)}
            </tr></thead>
            <tbody>{comparison.rows.map((row) => <tr className="border-b border-border font-mono tabular-nums" key={row.timestamp}>
              <th className="px-2 py-2 font-normal" scope="row">{row.session}</th>
              <td className="whitespace-nowrap px-2 py-2"><time dateTime={row.timestamp} title={row.timestamp}>{row.timestamp.slice(0, 10)}</time></td>
              {[row.p10, row.p50, row.p90, row.actual_close, row.absolute_error].map((value, index) => <td className="whitespace-nowrap px-2 py-2" key={index}>{price(value)}</td>)}
              <td className="whitespace-nowrap px-2 py-2">{row.within_interval == null ? unavailable : t(row.within_interval ? 'outcomeComparison.inside' : 'outcomeComparison.outside')}</td>
            </tr>)}</tbody>
          </table>
        </div>
        <dl className="mt-3 space-y-2 text-xs">
          {([
            [t('screen.workspace.reviewOutcomeId'), comparison.outcome_id],
            [t('outcomeComparison.forecastId'), comparison.forecast_artifact_id ?? unavailable],
            [t('screen.workspace.reviewPolicy'), comparison.policy_version],
            [t('screen.workspace.reviewPathSource'), outcome.path.source ?? unavailable],
            [t('screen.workspace.reviewPathDataset'), outcome.path.dataset_id ? `${outcome.path.dataset_id} · r${outcome.path.dataset_revision}` : unavailable],
            [t('screen.workspace.reviewPathCutoff'), outcome.path.cutoff_at],
            [t('screen.workspace.reviewPathDigest'), outcome.path.path_digest ?? unavailable],
          ]).map(([label, value]) => <div className="min-w-0" key={label}><dt className="text-muted-foreground">{label}</dt><dd className="font-mono [overflow-wrap:anywhere]">{value}</dd></div>)}
        </dl>
      </details>
    </section>
  )
}
