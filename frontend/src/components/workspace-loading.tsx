import { usePreferences } from '@/lib/preferences'

const GRID = 'grid gap-4 xl:grid-cols-[minmax(0,1fr)_18rem_22rem]'

/** Route-level and query-level fallback for the integrated workspace.
 * Keeping one shell prevents a generic card flash while the lazy chunk loads. */
export function WorkspaceLoading() {
  const { t } = usePreferences()
  return (
    <div className={GRID} aria-busy="true" aria-label={t('screen.workspace.loading')}>
      <div className="h-[34rem] animate-pulse rounded-lg bg-muted" />
      <div className="h-64 animate-pulse rounded-lg bg-muted" />
      <div className="h-80 animate-pulse rounded-lg bg-muted" />
    </div>
  )
}
