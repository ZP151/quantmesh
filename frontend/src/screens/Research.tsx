import { Link } from 'react-router-dom'
import { Gauge, Rocket } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { Surface, useSurface } from '@/components/state'
import { api, type EvaluationRow, type ForecastReport } from '@/lib/api'
import { dateTime, shortHash, venueLabel } from '@/lib/format'

const paperOrderAction = (
  <Button variant="outline" size="sm" render={<Link to="/trading/order" />}>
    <Rocket className="size-3.5" aria-hidden /> Paper order
  </Button>
)

// --- Experiments ---------------------------------------------------------

export function ExperimentsScreen() {
  const query = useSurface(['experiments'], api.experiments)

  return (
    <Page
      title="Experiments"
      description="Seeded research registry — deterministic baseline experiments over the demo universe, with their out-of-sample metrics."
    >
      <Surface query={query} title="Experiments">
        {(data) => (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="py-2 pr-4 font-medium">Experiment</th>
                  <th className="py-2 pr-4 font-medium">Dataset</th>
                  <th className="py-2 pr-4 text-right font-medium">Revision</th>
                  <th className="py-2 pr-4 text-right font-medium">OOS RMSE</th>
                  <th className="py-2 pr-4 text-right font-medium">OOS MAE</th>
                  <th className="py-2 text-right font-medium">Created</th>
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
  return (
    <div>
      <p className="mb-1 text-xs font-medium text-muted-foreground">{title}</p>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border text-left text-muted-foreground">
            <th className="py-1 pr-3 font-medium">Strategy</th>
            <th className="py-1 pr-3 font-medium">Dataset</th>
            <th className="py-1 pr-3 text-right font-medium">Return</th>
            <th className="py-1 pr-3 text-right font-medium">Sharpe</th>
            <th className="py-1 pr-3 text-right font-medium">Max DD</th>
            <th className="py-1 text-right font-medium">OOS</th>
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
                  {row.windows_oos ? 'oos' : 'in-sample'}
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

  return (
    <Page
      title="Promotions"
      description="Promoted signals with benchmark/ablation evaluations — the strategy evidence side of the paper-order loop. Nothing here trades."
      actions={paperOrderAction}
    >
      <Surface query={query} title="Promotions">
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
                        signal kill-switched
                      </Badge>
                    )}
                  </CardTitle>
                  <CardDescription>Promoted {dateTime(promotion.promoted_at)}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <EvaluationTable rows={promotion.benchmarks} title="Benchmarks" />
                  <EvaluationTable rows={promotion.ablations} title="Ablations" />
                  <EvaluationTable rows={[promotion.oos]} title="Out-of-sample" />
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
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Gauge className="size-4" aria-hidden />
          <span className="font-mono text-sm">{shortHash(report.id)}</span>
          <Badge variant="outline" className="font-mono text-[10px]">
            {report.n_bins} bins
          </Badge>
          <Badge variant={report.artifacts_present ? 'default' : 'outline'} className="font-mono text-[10px]">
            {report.artifacts_present ? 'artifacts on disk' : 'no artifacts'}
          </Badge>
        </CardTitle>
        <CardDescription>
          {dateTime(report.created_at)} · commit {shortHash(report.commit)} · train/test/step{' '}
          {report.window_spec.train}/{report.window_spec.test}/{report.window_spec.step}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-4">
          <div>
            <p className="text-muted-foreground">Windows</p>
            <p className="font-mono tabular-nums">{report.metrics['n_windows_total'] ?? '—'}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Observations</p>
            <p className="font-mono tabular-nums">{report.metrics['n_observations'] ?? '—'}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Mean Brier</p>
            <p className="font-mono tabular-nums">{report.metrics['mean_brier'] ?? '—'}</p>
          </div>
          <div>
            <p className="text-muted-foreground">Resolved</p>
            <p className="font-mono tabular-nums">{report.metrics['n_resolved'] ?? '—'}</p>
          </div>
        </div>
        <div className="space-y-2">
          {report.markets.map((market) => (
            <div key={market.market_id} className="rounded-lg border border-border/70 px-3 py-2">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm">{market.title}</p>
                <Badge variant={market.resolved ? 'default' : 'outline'} className="shrink-0 font-mono text-[10px]">
                  {market.resolved ? 'resolved' : 'open'}
                </Badge>
              </div>
              <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                {market.market_id} · {venueLabel(market.venue)} · expires {dateTime(market.expiry_at)}
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

  return (
    <Page
      title="Forecasts"
      description="Calibration reports over the seeded prediction markets — the prediction evidence the paper-order loop reads. Prediction markets are read-only in this demo."
      actions={paperOrderAction}
    >
      <Surface query={query} title="Forecasts">
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
