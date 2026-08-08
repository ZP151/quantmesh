import type { ReactNode } from 'react'

/** Every screen's consistent header: title, one-line description, and
 * optional action slot (e.g. the paper-order entry points). */
export function Page({
  title,
  description,
  children,
  actions,
}: {
  title: string
  description: string
  children: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="space-y-1">
          <h2 className="text-xl font-semibold tracking-tight">{title}</h2>
          <p className="max-w-2xl text-sm text-muted-foreground">{description}</p>
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
      {children}
    </div>
  )
}
