import type { ReactNode } from 'react'
import { CircleAlert, TriangleAlert } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/lib/api'
import { usePreferences } from '@/lib/preferences'

// Every screen shares the same four states: loading (skeleton),
// error (typed failure with recovery hint), empty (kernel answered but
// no rows), and the bounded success body. Screens call `useSurface`
// for the query and render through `<Surface>`.

export function useSurface<T>(key: readonly unknown[], fetcher: () => Promise<T>) {
  return useQuery({ queryKey: key, queryFn: fetcher })
}

export function ErrorState({ title, detail }: { title: string; detail: string }) {
  const { t } = usePreferences()
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-destructive">
          <TriangleAlert className="size-4" aria-hidden />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <p className="text-muted-foreground">{detail}</p>
        <p className="text-xs text-muted-foreground">{t('surface.helper')}</p>
      </CardContent>
    </Card>
  )
}

export function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <Card className="border-dashed">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-muted-foreground">
          <CircleAlert className="size-4" aria-hidden />
          {title}
        </CardTitle>
        <CardDescription>{detail}</CardDescription>
      </CardHeader>
    </Card>
  )
}

export function LoadingState({ rows = 3 }: { rows?: number }) {
  const { t } = usePreferences()
  return (
    <div className="space-y-3" aria-busy="true" aria-label={t('state.loading')}>
      {Array.from({ length: rows }, (_, index) => (
        <Skeleton key={index} className="h-16 w-full" />
      ))}
    </div>
  )
}

/** True when the surface payload carries no rows (its first array is empty). */
function isSurfaceEmpty(data: unknown): boolean {
  if (Array.isArray(data)) return data.length === 0
  if (data !== null && typeof data === 'object') {
    for (const value of Object.values(data)) {
      if (Array.isArray(value)) return value.length === 0
    }
  }
  return false
}

export interface SurfaceQuery<T> {
  isPending: boolean
  isError: boolean
  error: unknown
  data: T | undefined
}

/**
 * The shared loading/error/empty scaffolding. Pass `empty` to render a
 * dedicated empty state when the kernel answered with zero rows;
 * otherwise the screen's own body handles it.
 */
export function Surface<T>({
  query,
  title,
  empty,
  loading,
  children,
}: {
  query: SurfaceQuery<T>
  title: string
  empty?: ReactNode
  loading?: ReactNode
  children: (data: T) => ReactNode
}) {
  const { t } = usePreferences()
  if (query.isPending) return <>{loading ?? <LoadingState />}</>
  if (query.isError) {
    const detail = query.error instanceof ApiError ? query.error.message : String(query.error)
    return <ErrorState title={t('surface.unavailable', { title })} detail={detail} />
  }
  const data = query.data
  if (data === undefined || (empty !== undefined && isSurfaceEmpty(data))) {
    return (
      <>
        {empty ?? (
          <EmptyState
            title={t('surface.empty', { title: title.toLowerCase() })}
            detail={t('surface.emptyDetail')}
          />
        )}
      </>
    )
  }
  return <>{children(data)}</>
}

export function Notice({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
      <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      <span>{children}</span>
    </p>
  )
}
