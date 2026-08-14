import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronDown, Database, GitBranch, ShieldCheck } from 'lucide-react'

import { Page } from '@/components/page'
import { EmptyState, ErrorState, LoadingState, Surface, useSurface } from '@/components/state'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Separator } from '@/components/ui/separator'
import { api, ApiError, type CatalogEntry, type CatalogLineage } from '@/lib/api'
import { dateTime, quantity } from '@/lib/format'
import type { MessageKey } from '@/lib/messages'
import { usePreferences } from '@/lib/preferences'
import { cn } from '@/lib/utils'

type CatalogState = 'ready' | 'passed' | 'failed' | 'not-due' | 'unavailable' | 'stale'

const STATE_KEY: Record<CatalogState, MessageKey> = {
  ready: 'screen.catalog.state.ready',
  passed: 'screen.catalog.state.passed',
  failed: 'screen.catalog.state.failed',
  'not-due': 'screen.catalog.state.notDue',
  unavailable: 'screen.catalog.state.unavailable',
  stale: 'screen.catalog.state.stale',
}

function catalogStates(entry: CatalogEntry): CatalogState[] {
  const stale = entry.quality?.issue_codes.includes('freshness-sla') || !entry.is_current
  if (entry.quality === null || entry.quality === undefined || entry.quality.status === 'unavailable') {
    return stale ? ['unavailable', 'stale'] : ['unavailable']
  }
  if (entry.quality.status === 'fail') return stale ? ['failed', 'stale'] : ['failed']
  if (entry.quality.status === 'not-due') return stale ? ['not-due', 'stale'] : ['not-due']
  return [entry.trusted_for_research ? 'ready' : 'passed']
}

function stateVariant(state: CatalogState): 'default' | 'outline' | 'destructive' | 'secondary' {
  if (state === 'ready') return 'default'
  if (state === 'failed') return 'destructive'
  if (state === 'stale' || state === 'unavailable') return 'outline'
  return 'secondary'
}

export function DataCatalogScreen() {
  const { t } = usePreferences()
  const catalog = useSurface(['data-catalog'], api.dataCatalog)

  return (
    <Page title={t('screen.catalog.title')} description={t('screen.catalog.description')}>
      <Surface
        query={catalog}
        title={t('screen.catalog.title')}
        empty={
          <EmptyState
            title={t('screen.catalog.empty')}
            detail={t('screen.catalog.emptyDetail')}
          />
        }
      >
        {(entries) => (
          <Card className="overflow-hidden">
            <CardContent className="p-0">
              <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)_auto] gap-4 border-b border-border bg-muted/35 px-4 py-2 text-[10px] font-medium tracking-wider text-muted-foreground uppercase max-md:hidden">
                <span>{t('screen.catalog.dataset')}</span>
                <span>{t('screen.catalog.coverage')}</span>
                <span>{t('screen.catalog.qualification')}</span>
              </div>
              {entries.map((entry) => (
                <CatalogRow key={entry.manifest_id} entry={entry} />
              ))}
            </CardContent>
          </Card>
        )}
      </Surface>
    </Page>
  )
}

function CatalogRow({ entry }: { entry: CatalogEntry }) {
  const { locale, t } = usePreferences()
  const [expanded, setExpanded] = useState(false)
  const states = catalogStates(entry)
  const lineage = useQuery({
    queryKey: ['data-catalog-lineage', entry.manifest_id],
    queryFn: () => api.dataCatalogLineage(entry.manifest_id),
    enabled: expanded,
  })

  return (
    <article className="border-b border-border last:border-b-0">
      <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)_auto] items-start gap-4 px-4 py-4 max-md:grid-cols-1 max-md:gap-3">
        <div className="min-w-0 space-y-2">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <Database className="size-4 shrink-0 text-muted-foreground" aria-hidden />
            <h3 className="truncate font-mono text-sm font-semibold" title={entry.dataset_id}>
              {entry.dataset_id}
            </h3>
            <Badge variant="outline" className="font-mono text-[10px]">{entry.layer}</Badge>
          </div>
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{entry.canonical_instrument}</span>
            {' · '}{entry.provider_id}{' · '}{entry.provider_access}
          </p>
          <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
            <dt>{t('screen.catalog.manifest')}</dt>
            <dd className="break-all font-mono text-foreground">{entry.manifest_id}</dd>
            <dt>{t('screen.catalog.rights')}</dt>
            <dd className="break-all font-mono">{entry.source_rights_id}</dd>
            <dt>{t('screen.catalog.entitlement')}</dt>
            <dd className="font-mono">{entry.entitlement}</dd>
          </dl>
        </div>

        <dl className="grid grid-cols-[max-content_minmax(0,1fr)] gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
          <dt>{t('screen.catalog.eventTime')}</dt>
          <dd className="text-right font-mono max-md:text-left">
            {dateTime(entry.event_start, locale)} → {dateTime(entry.event_end, locale)}
          </dd>
          <dt>{t('screen.catalog.knowledgeTime')}</dt>
          <dd className="text-right font-mono max-md:text-left">
            {dateTime(entry.knowledge_start, locale)} → {dateTime(entry.knowledge_end, locale)}
          </dd>
          <dt>{t('screen.catalog.rows')}</dt>
          <dd className="text-right font-mono tabular-nums max-md:text-left">{quantity(entry.row_count, locale)}</dd>
          <dt>{t('screen.catalog.interval')}</dt>
          <dd className="text-right font-mono max-md:text-left">{entry.interval ?? t('screen.catalog.notApplicable')}</dd>
          <dt>{t('screen.catalog.checkpoint')}</dt>
          <dd className="min-w-0 break-all text-right font-mono max-md:text-left">
            {entry.latest_checkpoint
              ? t('screen.catalog.checkpointState', {
                  generation: String(entry.latest_checkpoint.generation),
                  run: entry.latest_checkpoint.run_id,
                  updated: dateTime(entry.latest_checkpoint.updated_at, locale),
                })
              : t('screen.catalog.noCheckpoint')}
          </dd>
        </dl>

        <div className="flex min-w-32 flex-col items-end gap-2 max-md:items-start">
          <div className="flex flex-wrap justify-end gap-1.5 max-md:justify-start">
            {states.map((state) => (
              <Badge
                key={state}
                variant={stateVariant(state)}
                className={cn(
                  'font-mono text-[10px]',
                  state === 'stale' && 'border-amber-500/60 bg-amber-500/10 text-amber-800 dark:text-amber-300',
                )}
              >
                {t(STATE_KEY[state])}
              </Badge>
            ))}
          </div>
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={expanded}
            aria-controls={`catalog-lineage-${entry.manifest_id}`}
            onClick={() => setExpanded((current) => !current)}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            <GitBranch className="size-3.5" aria-hidden />
            {expanded ? t('screen.catalog.hideLineage') : t('screen.catalog.showLineage')}
            <ChevronDown className={cn('size-3.5 transition-transform', expanded && 'rotate-180')} aria-hidden />
          </Button>
        </div>
      </div>

      {expanded && (
        <div
          id={`catalog-lineage-${entry.manifest_id}`}
          data-testid={`catalog-lineage-${entry.manifest_id}`}
          className="border-t border-border bg-muted/20 px-4 py-4"
        >
          {lineage.isPending && <LoadingState rows={2} />}
          {lineage.isError && (
            <ErrorState
              title={t('screen.catalog.lineageUnavailable')}
              detail={lineage.error instanceof ApiError ? lineage.error.message : String(lineage.error)}
            />
          )}
          {lineage.data && <LineageDetail lineage={lineage.data} />}
        </div>
      )}
    </article>
  )
}

function LineageDetail({ lineage }: { lineage: CatalogLineage }) {
  const { locale, t } = usePreferences()
  const quality = lineage.entry.quality

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
      <section aria-labelledby={`quality-${lineage.entry.manifest_id}`} className="min-w-0 space-y-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="size-4 text-muted-foreground" aria-hidden />
          <h4 id={`quality-${lineage.entry.manifest_id}`} className="text-sm font-semibold">
            {t('screen.catalog.exactQuality')}
          </h4>
        </div>
        {quality ? (
          <>
            <dl className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-x-4 gap-y-1.5 text-xs">
              <dt className="text-muted-foreground">{t('screen.catalog.evaluationId')}</dt>
              <dd className="break-all text-right font-mono">{quality.evaluation_id}</dd>
              <dt className="text-muted-foreground">{t('screen.catalog.reportId')}</dt>
              <dd className="break-all text-right font-mono">{quality.report_id}</dd>
              <dt className="text-muted-foreground">{t('screen.catalog.policyId')}</dt>
              <dd className="break-all text-right font-mono">{quality.policy_id}</dd>
              <dt className="text-muted-foreground">{t('screen.catalog.observedExpected')}</dt>
              <dd className="text-right font-mono tabular-nums">{quality.observed_count} / {quality.expected_count}</dd>
              <dt className="text-muted-foreground">{t('screen.catalog.gaps')}</dt>
              <dd className="text-right font-mono tabular-nums">{quality.gap_count}</dd>
              <dt className="text-muted-foreground">{t('screen.catalog.duplicates')}</dt>
              <dd className="text-right font-mono tabular-nums">{quality.duplicate_count}</dd>
              <dt className="text-muted-foreground">{t('screen.catalog.schemaMismatches')}</dt>
              <dd className="text-right font-mono tabular-nums">{quality.schema_mismatch_count}</dd>
              <dt className="text-muted-foreground">{t('screen.catalog.hashMismatches')}</dt>
              <dd className="text-right font-mono tabular-nums">{quality.hash_mismatch_count}</dd>
              <dt className="text-muted-foreground">{t('screen.catalog.orderViolations')}</dt>
              <dd className="text-right font-mono tabular-nums">{quality.order_violation_count}</dd>
              <dt className="text-muted-foreground">{t('screen.catalog.overlapConflicts')}</dt>
              <dd className="text-right font-mono tabular-nums">{quality.overlap_conflict_count}</dd>
              <dt className="text-muted-foreground">{t('screen.catalog.syntheticRows')}</dt>
              <dd className="text-right font-mono tabular-nums">{quality.synthetic_row_count}</dd>
              <dt className="text-muted-foreground">{t('screen.catalog.freshness')}</dt>
              <dd className="text-right font-mono tabular-nums">
                {quality.freshness_seconds === null || quality.freshness_seconds === undefined
                  ? t('screen.catalog.notApplicable')
                  : t('screen.catalog.seconds', { value: String(quality.freshness_seconds) })}
              </dd>
              <dt className="text-muted-foreground">{t('screen.catalog.latency')}</dt>
              <dd className="text-right font-mono tabular-nums">
                {quality.latency_seconds === null || quality.latency_seconds === undefined
                  ? t('screen.catalog.notApplicable')
                  : t('screen.catalog.seconds', { value: String(quality.latency_seconds) })}
              </dd>
              <dt className="text-muted-foreground">{t('screen.catalog.paginationTerminal')}</dt>
              <dd className="text-right font-mono">
                {quality.pagination_terminal === null
                  ? t('screen.catalog.notApplicable')
                  : quality.pagination_terminal ? t('screen.catalog.yes') : t('screen.catalog.no')}
              </dd>
              <dt className="text-muted-foreground">{t('screen.catalog.sourceRightsKnown')}</dt>
              <dd className="text-right font-mono">
                {quality.source_rights_known ? t('screen.catalog.yes') : t('screen.catalog.no')}
              </dd>
              <dt className="text-muted-foreground">{t('screen.catalog.unavailableReason')}</dt>
              <dd className="break-words text-right font-mono">
                {quality.unavailable_reason ?? t('screen.catalog.notApplicable')}
              </dd>
              <dt className="text-muted-foreground">{t('screen.catalog.evaluated')}</dt>
              <dd className="text-right font-mono">{dateTime(quality.evaluated_at, locale)}</dd>
            </dl>
            <Separator />
            <div className="flex flex-wrap gap-1.5">
              {quality.issue_codes.length > 0
                ? quality.issue_codes.map((code) => (
                    <Badge
                      key={code}
                      variant={quality.status === 'fail' ? 'destructive' : quality.status === 'not-due' ? 'secondary' : 'outline'}
                      className="font-mono text-[10px]"
                    >
                      {code}
                    </Badge>
                  ))
                : <span className="text-xs text-muted-foreground">{t('screen.catalog.noIssues')}</span>}
            </div>
            <Separator />
            <CheckpointDetail entry={lineage.entry} />
          </>
        ) : (
          <p className="text-xs text-muted-foreground">{t('screen.catalog.qualityUnavailable')}</p>
        )}
      </section>

      <section aria-labelledby={`parents-${lineage.entry.manifest_id}`} className="min-w-0 space-y-3">
        <h4 id={`parents-${lineage.entry.manifest_id}`} className="text-sm font-semibold">
          {t('screen.catalog.parentLineage')}
        </h4>
        {lineage.ancestors.length === 0 ? (
          <p className="text-xs text-muted-foreground">{t('screen.catalog.lineageRoot')}</p>
        ) : (
          <ol className="space-y-2">
            {lineage.ancestors.map((ancestor) => (
              <li key={ancestor.manifest_id} className="border-l-2 border-border pl-3">
                <div className="flex flex-wrap items-center gap-2">
                  <code className="break-all text-[11px]">{ancestor.manifest_id}</code>
                  <Badge variant="outline" className="font-mono text-[10px]">{ancestor.layer}</Badge>
                </div>
                <p className="mt-1 text-[11px] text-muted-foreground">
                  {ancestor.dataset_id} · {quantity(ancestor.row_count, locale)} {t('screen.catalog.rows').toLowerCase()}
                </p>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  )
}

function CheckpointDetail({ entry }: { entry: CatalogEntry }) {
  const { locale, t } = usePreferences()
  const checkpoint = entry.latest_checkpoint
  return (
    <div className="space-y-2">
      <h5 className="text-xs font-semibold">{t('screen.catalog.exactCheckpoint')}</h5>
      {checkpoint ? (
        <dl className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-x-4 gap-y-1.5 text-xs">
          <dt className="text-muted-foreground">{t('screen.catalog.checkpointJobId')}</dt>
          <dd className="break-all text-right font-mono">{checkpoint.job_id}</dd>
          <dt className="text-muted-foreground">{t('screen.catalog.checkpointRunId')}</dt>
          <dd className="break-all text-right font-mono">{checkpoint.run_id}</dd>
          <dt className="text-muted-foreground">{t('screen.catalog.attemptGeneration')}</dt>
          <dd className="text-right font-mono">{checkpoint.attempt} / {checkpoint.generation}</dd>
          <dt className="text-muted-foreground">{t('screen.catalog.providerCursor')}</dt>
          <dd className="break-all text-right font-mono">{checkpoint.provider_cursor}</dd>
          <dt className="text-muted-foreground">{t('screen.catalog.lastCompleteEvent')}</dt>
          <dd className="break-all text-right font-mono">{checkpoint.last_complete_source_event}</dd>
          <dt className="text-muted-foreground">{t('screen.catalog.boundQualityReport')}</dt>
          <dd className="break-all text-right font-mono">
            {checkpoint.quality_report_id ?? t('screen.catalog.notApplicable')}
          </dd>
          <dt className="text-muted-foreground">{t('screen.catalog.updated')}</dt>
          <dd className="text-right font-mono">{dateTime(checkpoint.updated_at, locale)}</dd>
        </dl>
      ) : (
        <p className="text-xs text-muted-foreground">{t('screen.catalog.noCheckpoint')}</p>
      )}
    </div>
  )
}
