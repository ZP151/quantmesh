import { ScrollText } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Page } from '@/components/page'
import { Surface, useSurface } from '@/components/state'
import { api, type AuditEntry } from '@/lib/api'
import { dateTime, moneyPrecise, quantity } from '@/lib/format'

const KIND_VARIANT: Record<AuditEntry['kind'], 'default' | 'outline' | 'secondary'> = {
  order: 'default',
  mapping: 'outline',
  decision: 'secondary',
}

function EntryCard({ entry }: { entry: AuditEntry }) {
  let summary: string
  if (entry.kind === 'order' && entry.order) {
    summary = `${entry.order.instrument.venue}:${entry.order.instrument.symbol} · ${entry.order.side.toUpperCase()} ${quantity(entry.order.quantity)} · ${entry.order.status}${entry.order.average_fill_price !== null ? ` @ ${moneyPrecise(entry.order.average_fill_price)}` : ''}`
  } else if (entry.kind === 'mapping' && entry.mapping) {
    summary = `mapping ${entry.mapping['pair_key'] ?? ''} · ${entry.mapping['status'] ?? 'unknown'}`
  } else if (entry.kind === 'decision' && entry.decision) {
    const verdict = entry.decision['verdict'] ?? 'unknown'
    const role = entry.decision['role'] ?? 'unknown'
    summary = `${role} verdict: ${String(verdict)}`
  } else {
    summary = entry.anchor
  }
  const payload = entry.order ?? entry.mapping ?? entry.decision

  return (
    <div className="rounded-lg border border-border/70 px-3 py-2">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-sm">{summary}</p>
          <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
            {entry.anchor} · {dateTime(entry.at)}
          </p>
        </div>
        <Badge variant={KIND_VARIANT[entry.kind]} className="shrink-0 font-mono text-[10px]">
          {entry.kind}
        </Badge>
      </div>
      {payload && (
        <details className="mt-2">
          <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">
            Payload
          </summary>
          <pre className="mt-2 max-h-64 overflow-auto rounded-lg bg-muted/40 p-3 font-mono text-[10px] leading-relaxed">
            {JSON.stringify(payload, null, 2)}
          </pre>
        </details>
      )}
    </div>
  )
}

/** Audit: the ordered trail of orders, mappings and decisions — the
 * last link of the loop, showing exactly what the browser's paper
 * order wrote into the journal. */
export function AuditScreen() {
  const query = useSurface(['audit'], api.audit)

  return (
    <Page
      title="Audit"
      description="The journal, mapping and decision ledgers as one ordered trail. Every browser order appends here with its full event history."
    >
      <Surface query={query} title="Audit">
        {(audit) => (
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <ScrollText className="size-4" aria-hidden /> Trail
                {!audit.journal_bound && (
                  <Badge variant="outline" className="text-[10px]">
                    journal unbound
                  </Badge>
                )}
              </CardTitle>
              <CardDescription>
                {audit.entries.length} entries · journal {audit.journal_bound ? 'bound' : 'unbound'} · mappings{' '}
                {audit.mappings_bound ? 'bound' : 'unbound'} · decisions {audit.decisions_bound ? 'bound' : 'unbound'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {audit.entries.map((entry, index) => (
                <EntryCard key={`${entry.kind}:${entry.anchor}:${index}`} entry={entry} />
              ))}
            </CardContent>
          </Card>
        )}
      </Surface>
    </Page>
  )
}
