import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import type { InstrumentWorkspace } from '@/lib/api'
import { dateTime, moneyPrecise, number, percent, shortHash } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'

export type ForecastHorizon = 7 | 30 | 126
type ForecastInterval = 50 | 80 | 95

function intervalValues(
  point: NonNullable<InstrumentWorkspace['forecast']>['paths'][number]['points'][number] | undefined,
  interval: ForecastInterval,
): [number | null, number | null] {
  if (point === undefined) return [null, null]
  if (interval === 50) return [point.p25, point.p75]
  if (interval === 80) return [point.p10, point.p90]
  return [point.p025, point.p975]
}

export function ForecastEvidence({
  forecast,
  horizon,
  onHorizonChange,
  synthetic,
  unavailableReason,
}: {
  forecast: InstrumentWorkspace['forecast']
  horizon: ForecastHorizon
  onHorizonChange: (horizon: ForecastHorizon) => void
  synthetic: boolean
  unavailableReason: string | null | undefined
}) {
  const { t } = usePreferences()
  const [interval, setInterval] = useState<ForecastInterval>(80)

  if (forecast === null || forecast === undefined) {
    return (
      <section className="space-y-2 px-3" aria-label={t('screen.workspace.forecast')}>
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          {t('screen.workspace.forecast')}
        </h2>
        <p className="text-xs text-muted-foreground">
          {unavailableReason ?? t('screen.workspace.noForecast')}
        </p>
      </section>
    )
  }

  const path = forecast.paths.find((candidate) => candidate.sessions === horizon)
  const metrics = forecast.metrics.find((candidate) => candidate.sessions === horizon)
  const finalPoint = path?.points[path.points.length - 1]
  const [lower, upper] = intervalValues(finalPoint, interval)

  return (
    <section className="space-y-4 px-3" aria-label={t('screen.workspace.forecast')}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            {t('screen.workspace.forecast')}
          </h2>
          <p className="mt-1 text-sm font-medium">{forecast.model_name}</p>
        </div>
        <div className="flex flex-wrap gap-1">
          <Badge variant={forecast.eligible ? 'default' : 'destructive'}>
            {t(forecast.eligible ? 'screen.workspace.forecastPromoted' : 'screen.workspace.forecastNotPromoted')}
          </Badge>
          {synthetic && <Badge variant="outline">{t('screen.workspace.syntheticForecast')}</Badge>}
        </div>
      </div>

      <div className="flex flex-wrap gap-1" aria-label={t('screen.workspace.forecastHorizon')}>
        {([7, 30, 126] as const).map((sessions) => (
          <Button
            aria-pressed={horizon === sessions}
            className="h-7 px-2 font-mono text-[10px]"
            key={sessions}
            onClick={() => onHorizonChange(sessions)}
            type="button"
            variant={horizon === sessions ? 'secondary' : 'ghost'}
          >
            {t('screen.workspace.sessions', { count: String(sessions) })}
          </Button>
        ))}
      </div>

      <div className="border-y border-border py-3">
        <p className="font-mono text-sm tabular-nums">
          {t('screen.workspace.medianValue', { value: moneyPrecise(finalPoint?.p50) })}
        </p>
        <div className="mt-2 flex flex-wrap gap-1" aria-label={t('screen.workspace.forecastInterval')}>
          {([50, 80, 95] as const).map((candidate) => (
            <Button
              aria-pressed={interval === candidate}
              className="h-7 px-2 font-mono text-[10px]"
              key={candidate}
              onClick={() => setInterval(candidate)}
              type="button"
              variant={interval === candidate ? 'secondary' : 'ghost'}
            >
              {t('screen.workspace.interval', { count: String(candidate) })}
            </Button>
          ))}
        </div>
        <p className="mt-2 font-mono text-xs tabular-nums">
          {t('screen.workspace.intervalValue', {
            lower: moneyPrecise(lower),
            upper: moneyPrecise(upper),
          })}
        </p>
      </div>

      {metrics && (
        <dl className="space-y-1 text-xs">
          <Fact label={t('screen.workspace.oosMae')} value={number(metrics.mae)} />
          <Fact label={t('screen.workspace.oosRmse')} value={number(metrics.rmse)} />
          <Fact label={t('screen.workspace.benchmarkMae')} value={number(metrics.benchmark_mae)} />
          <Fact
            label={t('screen.workspace.coverage')}
            value={`${percent(metrics.coverage_50)} / ${percent(metrics.coverage_80)} / ${percent(metrics.coverage_95)}`}
          />
          <Fact label={t('screen.workspace.residualSamples')} value={number(metrics.residual_count)} />
          <Fact label={t('screen.workspace.intervalTests')} value={number(metrics.interval_test_count)} />
        </dl>
      )}

      <dl className="space-y-1 border-t border-border pt-3 text-xs">
        <Fact label={t('screen.workspace.datasetRevision')} value={`${forecast.dataset_id} · ${forecast.dataset_revision}`} />
        <Fact label={t('screen.workspace.modelVersion')} value={forecast.model_version} />
        <Fact label={t('screen.workspace.configDigest')} value={shortHash(forecast.config_digest)} />
        <Fact label={t('screen.workspace.historyDigest')} value={shortHash(forecast.history_digest)} />
        <Fact label={t('screen.workspace.trainCutoff')} value={dateTime(forecast.train_end)} />
        <Fact label={t('screen.workspace.generated')} value={dateTime(forecast.generated_at)} />
      </dl>

      {!forecast.eligible && forecast.blockers.length > 0 && (
        <ul className="space-y-1 text-xs text-destructive">
          {forecast.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}
        </ul>
      )}
      {forecast.limitations.length > 0 && (
        <ul className="space-y-1 text-[10px] text-muted-foreground">
          {forecast.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
        </ul>
      )}
    </section>
  )
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="max-w-44 text-right font-mono tabular-nums">{value}</dd>
    </div>
  )
}
