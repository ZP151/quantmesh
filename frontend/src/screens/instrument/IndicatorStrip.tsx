import { usePreferences } from '@/lib/preferences'

export interface IndicatorValues {
  drawdown: number | null
  realizedVolatility: number | null
}

function percent(value: number | null): string {
  return value === null
    ? '—'
    : new Intl.NumberFormat('en-US', { style: 'percent', maximumFractionDigits: 2 }).format(value)
}

export function IndicatorStrip({ values }: { values: IndicatorValues }) {
  const { t } = usePreferences()
  return (
    <dl className="grid grid-cols-2 border-y border-border sm:grid-cols-4">
      <div className="border-r border-border px-3 py-2">
        <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {t('screen.workspace.realizedVolatility')}
        </dt>
        <dd className="font-mono text-sm tabular-nums">{percent(values.realizedVolatility)}</dd>
      </div>
      <div className="border-r border-border px-3 py-2">
        <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {t('screen.workspace.drawdown')}
        </dt>
        <dd className="font-mono text-sm tabular-nums">{percent(values.drawdown)}</dd>
      </div>
      <div className="border-r border-border px-3 py-2">
        <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {t('screen.workspace.observed')}
        </dt>
        <dd className="text-xs text-emerald-600 dark:text-emerald-400">
          {t('screen.workspace.observedOnly')}
        </dd>
      </div>
      <div className="px-3 py-2">
        <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {t('screen.workspace.forecastDistribution')}
        </dt>
        <dd className="text-xs text-muted-foreground">{t('screen.workspace.separateLayer')}</dd>
      </div>
    </dl>
  )
}
