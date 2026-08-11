import { TriangleAlert } from 'lucide-react'

import { ApiError } from '@/lib/api'
import { usePreferences } from '@/lib/preferences'

export function WorkspaceError({
  error,
  symbol,
  venue,
}: {
  error: unknown
  symbol: string
  venue: string
}) {
  const { t } = usePreferences()
  const detail = error instanceof Error ? error.message : String(error)
  const missing = error instanceof ApiError && error.status === 404
  return (
    <section className="space-y-4 border-y border-border py-8" role="alert">
      <p className="font-mono text-xs uppercase tracking-widest text-muted-foreground">
        {venue} / {symbol}
      </p>
      <div className="flex items-start gap-3">
        <TriangleAlert className="mt-0.5 size-5 text-destructive" aria-hidden />
        <div>
          <h1 className="text-lg font-semibold">
            {t(missing ? 'screen.workspace.historyMissing' : 'screen.workspace.unavailable')}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">{detail}</p>
        </div>
      </div>
    </section>
  )
}

export function WorkspaceDegraded({ reason }: { reason: string }) {
  const { t } = usePreferences()
  return (
    <div className="border-l-2 border-amber-500 bg-amber-500/5 px-3 py-2" role="status">
      <p className="text-xs font-semibold text-amber-700 dark:text-amber-300">
        {t('screen.workspace.stale')}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">{reason}</p>
    </div>
  )
}
