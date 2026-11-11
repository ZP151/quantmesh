import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

/** Native disclosure keeps drafts/query ownership mounted and never runs actions. */
export function EvidenceDisclosure({ title, summary, children, defaultOpen = false, testId, className }: {
  title: string
  summary?: ReactNode
  children: ReactNode
  defaultOpen?: boolean
  testId?: string
  className?: string
}) {
  return <details open={defaultOpen} data-testid={testId} className={cn('min-w-0 border-y border-border py-3', className)}>
    <summary className="cursor-pointer px-3 py-1 text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring">
      {title}
      {summary && <span className="ml-3 inline-block text-xs font-normal text-muted-foreground">{summary}</span>}
    </summary>
    <div className="min-w-0 space-y-3 px-3 pt-3">{children}</div>
  </details>
}
