import { Link } from 'react-router-dom'
import { Gauge, Rocket } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { Surface, useSurface } from '@/components/state'
import { api, type EvaluationRow, type ForecastReport } from '@/lib/api'
import { dateTime, percent, shortHash, venueLabel } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'

function PaperOrderAction() {
  const { t } = usePreferences()
  return (
    <Button variant="outline" size="sm" render={<Link to="/trading/order" />}>
      <Rocket className="size-3.5" aria-hidden /> {t('nav.paperOrder')}
    </Button>
  )
}

// --- Experiments ---------------------------------------------------------

export function ExperimentsScreen() {
  const query = useSurface(['experiments'], api.experiments)
  const { t } = usePreferences()

  return (
    <Page
      title={t('screen.experiments.title')}
      description={t('screen.experiments.description')}
    >
      <Surface query={query} title={t('screen.experiments.title')}>
        {(data) => (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">{t('screen.experiments.col.experiment')}</th>
                  <th className="py-2 pr-4 font-medium">{t('screen.experiments.col.dataset')}</th>
                  <th className="py-2 pr-4 text-right font-medium">{t('screen.experiments.col.revision')}</th>
                  <th className="py-2 pr-4 text-right font-medium">{t('screen.experiments.col.oosRmse')}</th>
                  <th className="py-2 pr-4 text-right font-medium">{t('screen.experiments.col.oosMae')}</th>
                  <th className="py-2 text-right font-medium">{t('screen.experiments.col.created')}</th>
                </tr>
              </thead>
              <tbody>
                {data.experiments.map((experiment) => (
                  <tr key={experiment.id} className="border-b border-border/60 last:border-0">
                    <td className="py-2 pr-4">
                      <p className="font-mono font-medium">{shortHash(experiment.id)}</p>
                      <p className="text-xs text-muted-foreground">{experiment.commit.slice(0, 8)}</p>
                    </td>
                    <td className="py-2 pr-4 font-mono text-xs">{experiment.dataset}</td>
                    <td className="py-2 pr-4 text-right font-mono tabular-nums">{experiment.revision}</td>
                    <td className="py-2 pr-4 text-right font-mono tabular-nums">{experiment.metrics['oos_rmse'] ?? '—'}</td>
                    <td className="py-2 pr-4 text-right font-mono tabular-nums">{experiment.metrics['oos_mae'] ?? '—'}</td>
                    <td className="py-2 text-right text-xs text-muted-foreground">{dateTime(experiment.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Surface>
    </Page>
  )
}

// --- Promotions ----------------------------------------------------------

function EvaluationTable({ rows, title }: { rows: EvaluationRow[]; title: string }) {
  const { t } = usePreferences()
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-muted-foreground">{title}</p>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            <th className="py-1 pr-3 font-medium">{t('screen.promotions.col.strategy')}</th>
            <th className="py-1 pr-3 font-medium">{t('screen.promotions.col.dataset')}</th>
            <th className="py-1 pr-3 text-right font-medium">{t('screen.promotions.col.return')}</th>
            <th className="py-1 pr-3 text-right font-medium">{t('screen.promotions.col.sharpe')}</th>
            <th className="py-1 pr-3 text-right font-medium">{t('screen.promotions.col.maxDd')}</th>
            <th className="py-1 text-right font-medium">{t('screen.promotions.col.oos')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-b border-border/60 last:border-0">
              <td className="py-1 pr-3 font-mono">{row.strategy}</td>
              <td className="py-1 pr-3 font-mono">{row.dataset}</td>
              <td className="py-1 pr-3 text-right font-mono tabular-nums">{row.metrics['total_return'] ?? '—'}</td>
              <td className="py-1 pr-3 text-right font-mono tabular-nums">{row.metrics['sharpe'] ?? '—'}</td>
              <td className="py-1 pr-3 text-right font-mono tabular-nums">{row.metrics['max_drawdown'] ?? '—'}</td>
              <td className="py-1 text-right">
                <Badge variant={row.windows_oos ? 'default' : 'outline'} className="font-mono text-[10px]">
                  {row.windows_oos ? t('screen.promotions.badge.oos') : t('screen.promotions.badge.inSample')}
                </Badge>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Promotions: the promoted signals, their benchmarks, ablations and
 * the out-of-sample row. This is the strategy evidence (策略/预测) the
 * paper-order loop reads before submitting. */
export function PromotionsScreen() {
  const query = useSurface(['promotions'], api.promotions)
  const { t } = usePreferences()

  return (
    <Page
      title={t('screen.promotions.title')}
      description={t('screen.promotions.description')}
      actions={<PaperOrderAction />}
    >
      <Surface query={query} title={t('screen.promotions.title')}>
        {(data) => (
          <div className="space-y-4">
            {data.promotions.map((promotion) => (
              <Card key={promotion.id}>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <Rocket className="size-4" aria-hidden />
                    <span className="font-mono">{promotion.signal_name}</span>
                    <Badge variant="outline" className="font-mono text-[10px]">
                      {shortHash(promotion.id)}
                    </Badge>
                    {promotion.kill_switch && (
                      <Badge variant="destructive" className="text-[10px]">
                        {t('screen.promotions.killSwitched')}
                      </Badge>
                    )}
                  </CardTitle>
                  <CardDescription>{t('screen.promotions.promoted', { time: dateTime(promotion.promoted_at) })}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <EvaluationTable rows={promotion.benchmarks} title={t('screen.promotions.eval.benchmarks')} />
                  <EvaluationTable rows={promotion.ablations} title={t('screen.promotions.eval.ablations')} />
                  <EvaluationTable rows={[promotion.oos]} title={t('screen.promotions.eval.oos')} />
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </Surface>
    </Page>
  )
}

// --- Forecasts -----------------------------------------------------------

function ReportCard({ report }: { report: ForecastReport }) {
  const { t } = usePreferences()
  const calibrationSummary = (market: ForecastReport['markets'][number]) => {
    if (market.n_evaluated_windows > 0) {
      return market.n_evaluated_windows === 1
        ? t('screen.forecasts.calibration.measuredOne')
        : t('screen.forecasts.calibration.measuredMany', { count: String(market.n_evaluated_windows) })
    }
    if (market.resolved) {
      return t('screen.forecasts.calibration.pendingNoObs')
    }
    return t('screen.forecasts.calibration.pendingOpen')
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Gauge className="size-4" aria-hidden />
          <span className="font-mono text-sm">{shortHash(report.id)}</span>
          <Badge variant="outline" className="font-mono text-[10px]">
            {t('screen.forecasts.bins', { count: String(report.n_bins) })}
          </Badge>
          <Badge variant={report.artifacts_present ? 'default' : 'outline'} className="font-mono text-[10px]">
            {report.artifacts_present ? t('screen.forecasts.artifactsOnDisk') : t('screen.forecasts.noArtifacts')}
          </Badge>
        </CardTitle>
        <CardDescription>
          {t('screen.forecasts.meta', {
            time: dateTime(report.created_at),
            hash: shortHash(report.commit),
            train: String(report.window_spec.train),
            test: String(report.window_spec.test),
            step: String(report.window_spec.step),
          })}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <div>
            <p className="text-muted-foreground">{t('screen.forecasts.metric.windows')}</p>
            <p className="font-mono tabular-nums">{report.metrics['n_windows_total'] ?? '—'}</p>
          </div>
          <div>
            <p className="text-muted-foreground">{t('screen.forecasts.metric.observations')}</p>
            <p className="font-mono tabular-nums">{report.metrics['n_observations'] ?? '—'}</p>
          </div>
          <div>
            <p className="text-muted-foreground">{t('screen.forecasts.metric.meanBrier')}</p>
            <p className="font-mono tabular-nums">{report.metrics['mean_brier'] ?? '—'}</p>
          </div>
          <div>
            <p className="text-muted-foreground">{t('screen.forecasts.metric.resolved')}</p>
            <p className="font-mono tabular-nums">{report.metrics['n_resolved'] ?? '—'}</p>
          </div>
        </div>
        <div className="space-y-2">
          {report.markets.map((market) => (
            <div key={market.market_id} className="rounded-lg border border-border/70 px-3 py-2">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm">{market.title}</p>
                <Badge variant={market.resolved ? 'default' : 'outline'} className="shrink-0 font-mono text-[10px]">
                  {market.resolved ? t('screen.forecasts.market.resolved') : t('screen.forecasts.market.open')}
                </Badge>
              </div>
              <div className="mt-3 grid grid-cols-2 gap-3 rounded-lg bg-muted/30 px-3 py-2 text-xs sm:grid-cols-3">
                <div>
                  <p className="text-muted-foreground">{t('screen.forecasts.market.probability')}</p>
                  <p className="font-mono text-base font-semibold tabular-nums">
                    {percent(market.latest_probability)}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">{t('screen.forecasts.market.observed')}</p>
                  <p className="font-mono tabular-nums">
                    {market.latest_probability_at ? dateTime(market.latest_probability_at) : '—'}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">{t('screen.forecasts.market.liquidity')}</p>
                  <p className="font-mono tabular-nums">
                    {percent(market.latest_liquidity_confidence)}
                  </p>
                </div>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                <span className="font-medium text-foreground">{t('screen.forecasts.calibration.label')}</span>{' '}
                {calibrationSummary(market)}
              </p>
              <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                {market.market_id} · {venueLabel(market.venue)} · {t('screen.forecasts.expires', { date: dateTime(market.expiry_at) })}
              </p>
              <p className="mt-1 text-[10px] text-muted-foreground">
                {t('screen.forecasts.source', { venue: venueLabel(market.venue) })}
              </p>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

/** Forecast reports: the prediction evidence (预测) — calibration
 * reports over prediction markets, windows, bins, artifacts. */
export function ForecastsScreen() {
  const query = useSurface(['forecasts'], api.forecasts)
  const { t } = usePreferences()

  return (
    <Page
      title={t('screen.forecasts.title')}
      description={t('screen.forecasts.description')}
      actions={<PaperOrderAction />}
    >
      <Surface query={query} title={t('screen.forecasts.title')}>
        {(data) => (
          <div className="space-y-4">
            {data.reports.map((report) => (
              <ReportCard key={report.id} report={report} />
            ))}
          </div>
        )}
      </Surface>
    </Page>
  )
}
