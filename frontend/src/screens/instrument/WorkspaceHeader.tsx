import { Badge } from '@/components/ui/badge'
import type { InstrumentWorkspace } from '@/lib/api'
import { moneyPrecise } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'

function liveTone(status: InstrumentWorkspace['live']['status']): string {
  if (status === 'available') return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
  if (status === 'degraded') return 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
  return 'bg-muted text-muted-foreground'
}

const LIVE_MESSAGE = {
  available: 'screen.workspace.live.available',
  degraded: 'screen.workspace.live.degraded',
  unavailable: 'screen.workspace.live.unavailable',
} as const

const STREAM_MESSAGE = {
  connecting: 'screen.workspace.stream.connecting',
  fallback: 'screen.workspace.stream.fallback',
  live: 'screen.workspace.stream.live',
  down: 'screen.workspace.stream.down',
} as const

export function WorkspaceHeader({
  stream,
  workspace,
}: {
  stream: 'connecting' | 'live' | 'fallback' | 'down'
  workspace: InstrumentWorkspace
}) {
  const { t } = usePreferences()
  const live = workspace.live
  const mark = live.last ?? (
    live.bid !== null && live.bid !== undefined && live.ask !== null && live.ask !== undefined
      ? (live.bid + live.ask) / 2
      : null
  )

  return (
    <header className="sticky top-14 z-20 -mx-4 border-y border-border/80 bg-background/95 px-4 py-3 backdrop-blur md:-mx-6 md:px-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-center gap-3">
          <div>
            <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-muted-foreground">
              {workspace.instrument.venue} / {workspace.instrument.instrument_type}
            </p>
            <h1 className="truncate text-2xl font-semibold tracking-tight">
              {workspace.instrument.symbol}
            </h1>
          </div>
          <Badge className={liveTone(live.status)}>{t(LIVE_MESSAGE[live.status])}</Badge>
        </div>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-right sm:grid-cols-3">
          <div>
            <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {t('screen.workspace.mark')}
            </dt>
            <dd className="font-mono text-sm tabular-nums">{moneyPrecise(mark)}</dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {t('screen.workspace.source')}
            </dt>
            <dd className="max-w-32 truncate font-mono text-xs">{live.source ?? workspace.history.source}</dd>
          </div>
          <div>
            <dt className="text-[10px] uppercase tracking-wider text-muted-foreground">
              {t('screen.workspace.stream')}
            </dt>
            <dd className="font-mono text-xs">{t(STREAM_MESSAGE[stream])}</dd>
          </div>
        </dl>
      </div>
    </header>
  )
}
