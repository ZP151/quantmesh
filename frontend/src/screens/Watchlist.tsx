import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Page } from '@/components/page'
import { InstrumentEntry } from '@/components/instrument-entry'
import { Surface, useSurface } from '@/components/state'
import { api, type DecisionInbox } from '@/lib/api'
import { chartEntryPath, decisionPacketPath, instrumentPath, supportedLabTicker } from '@/lib/instrument-route'
import { dateTime, money } from '@/lib/format'
import type { MessageKey } from '@/lib/messages'
import { usePreferences } from '@/lib/preferences'

/** The watchlist: venue-scoped favorites with their marks. Every action
 * consumes the identity carried by its own API row; symbols are never
 * resolved by a first-match lookup across venues. */
export function WatchlistScreen() {
  const query = useSurface(['decision-inbox'], api.decisionInbox)
  const { locale, t } = usePreferences()
  const [filter, setFilter] = useState<ActionFilter>('all')
  const queryClient = useQueryClient()
  const refreshButton = useRef<HTMLButtonElement>(null)
  const restoreRefreshFocus = useRef(false)
  const refresh = useMutation({
    mutationFn: api.refreshDecisionSession,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['decision-inbox'] })
    },
  })
  useEffect(() => {
    if (refresh.isPending || !restoreRefreshFocus.current) return
    restoreRefreshFocus.current = false
    refreshButton.current?.focus()
  }, [refresh.isPending])

  const refreshSession = () => {
    restoreRefreshFocus.current ||= document.activeElement === refreshButton.current
    refresh.mutate()
  }

  return (
    <Page
      title={t('screen.watchlist.title')}
      description={t('screen.watchlist.description')}
    >
      <InstrumentEntry />
      <div className="flex flex-wrap items-center gap-3">
        <button
          className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-foreground shadow-sm transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          disabled={refresh.isPending}
          onClick={refreshSession}
          onKeyDown={(event) => {
            if (
              (event.key === 'Enter' || event.key === ' ')
              && document.activeElement === event.currentTarget
            ) {
              restoreRefreshFocus.current = true
            }
          }}
          ref={refreshButton}
          type="button"
        >
          {refresh.isPending
            ? t('screen.watchlist.refreshingSession')
            : t('screen.watchlist.refreshSession')}
        </button>
        {refresh.data && <p aria-live="polite" className="text-sm text-muted-foreground">
          {refreshFeedback(refresh.data, t)}
        </p>}
        {refresh.data?.status === 'partial' && <RefreshFailures result={refresh.data} />}
        {refresh.isError && <p aria-live="polite" className="text-sm text-destructive">
          {t('screen.watchlist.refreshUnavailable')}
        </p>}
      </div>
      {query.data && !query.isError && (
        <section aria-label={t('screen.watchlist.sessionSummary')} className="flex min-w-0 flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <p>{t('screen.watchlist.sessionGenerated', { time: dateTime(query.data.generated_at, locale) })}</p>
          <p>{t('screen.watchlist.sessionLastChecked', {
            time: query.data.session.last_checked_at
              ? dateTime(query.data.session.last_checked_at, locale)
              : t('screen.watchlist.sessionNeverChecked'),
          })}</p>
          <p>{t('screen.watchlist.sessionCounts', {
            registered: String(query.data.session.registered_count),
            triggered: String(query.data.session.triggered_count),
            blocked: String(query.data.session.blocked_count),
          })}</p>
        </section>
      )}
      <Surface
        query={query}
        title={t('screen.watchlist.title')}
        empty={<p className="border-y border-border py-6 text-sm text-muted-foreground">{t('screen.watchlist.empty')}</p>}
      >
        {(inbox) => {
          const filters: { bucket: ActionFilter; label: MessageKey }[] = [
            { bucket: 'all', label: 'screen.watchlist.filter.all' },
            { bucket: 'triggered', label: 'screen.watchlist.filter.triggered' },
            { bucket: 'blocked', label: 'screen.watchlist.filter.blocked' },
            { bucket: 'review_due', label: 'screen.watchlist.filter.reviewDue' },
            { bucket: 'no_action', label: 'screen.watchlist.filter.noAction' },
          ]
          const counts = inbox.entries.reduce<Record<AttentionBucket, number>>(
            (current, entry) => {
              const entryBucket = attentionBucket(entry)
              return { ...current, [entryBucket]: current[entryBucket] + 1 }
            },
            { triggered: 0, blocked: 0, review_due: 0, no_action: 0 },
          )
          const visible = filter === 'all'
            ? inbox.entries
            : inbox.entries.filter(entry => attentionBucket(entry) === filter)
          return (
            <div className="min-w-0 space-y-3">
              <div
                aria-label={t('screen.watchlist.filter.label')}
                className="flex min-w-0 flex-wrap gap-2"
                role="group"
              >
                {filters.map(({ bucket, label }) => (
                  <button
                    aria-pressed={filter === bucket}
                    className="rounded-md border border-border bg-background px-2.5 py-1.5 text-xs font-medium text-foreground hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring aria-pressed:border-primary aria-pressed:bg-primary aria-pressed:text-primary-foreground"
                    key={bucket}
                    onClick={() => setFilter(bucket)}
                    type="button"
                  >
                    {t(label, { count: String(bucket === 'all' ? inbox.entries.length : counts[bucket]) })}
                  </button>
                ))}
              </div>
              <div className="min-w-0 border-y border-border">
                <table className="w-full text-sm">
                  <thead className="hidden sm:table-header-group">
                    <tr className="border-b border-border text-left text-xs text-muted-foreground">
                      <th className="px-4 py-2.5 font-medium">{t('table.symbol')}</th>
                      <th className="px-4 py-2.5 font-medium">{t('table.venue')}</th>
                      <th className="px-4 py-2.5 text-right font-medium">{t('table.mark')}</th>
                      <th className="px-4 py-2.5 font-medium">{t('screen.watchlist.decision')}</th>
                      <th className="px-4 py-2.5 font-medium">{t('table.action')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visible.map((entry) => {
                      const exactPath = entry.venue !== null
                        && entry.packet_id !== null
                        && entry.selected_range !== null
                        ? decisionPacketPath(entry.venue, entry.symbol, entry.selected_range, entry.packet_id)
                        : null
                      const recoveryPath = entry.venue === null
                        ? '/markets'
                        : instrumentPath(entry.venue, entry.symbol)
                      return (
                        <tr key={`${entry.venue ?? 'unknown'}:${entry.symbol}`} className="block border-b border-border/60 py-2 last:border-0 sm:table-row sm:py-0">
                          <td className="block px-4 py-1 font-mono font-medium sm:table-cell sm:py-2.5">
                            {entry.venue === 'moomoo' && supportedLabTicker(entry.symbol) !== null ? (
                              <Link
                                aria-label={`${t('lab.openChart')} ${entry.symbol}`}
                                className="underline-offset-4 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                to={chartEntryPath(entry.venue, entry.symbol)}
                              >{entry.symbol}</Link>
                            ) : entry.symbol}
                          </td>
                          <td className="block px-4 py-1 font-mono text-xs text-muted-foreground sm:table-cell sm:py-2.5">
                            {entry.venue ?? '—'}
                          </td>
                          <td className="block px-4 py-1 font-mono tabular-nums sm:table-cell sm:py-2.5 sm:text-right">
                            {money(entry.mark_context.value)}
                            <span className="ml-2 text-[10px] text-muted-foreground">
                              {markStatus(entry.mark_context.status, t)}
                            </span>
                          </td>
                          <td className="block px-4 py-1 sm:table-cell sm:py-2.5">
                            <p className="text-xs font-medium">{attentionState(entry.attention_state, t)}</p>
                            <p className="mt-0.5 max-w-sm text-xs text-muted-foreground">{entry.attention_reason}</p>
                            <ReadinessFacts entry={entry} locale={locale} />
                            <ShadowRecords entry={entry} />
                          </td>
                          <td className="block px-4 py-1 sm:table-cell sm:py-2.5">
                            {exactPath !== null ? (
                              <Link
                                className="font-mono text-xs underline-offset-4 hover:text-primary hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                to={exactPath}
                              >
                                {t('screen.watchlist.openExactPacket')}
                              </Link>
                            ) : (
                              <Link
                                className="font-mono text-xs underline-offset-4 hover:text-primary hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                to={recoveryPath}
                              >
                                {entry.venue === null
                                  ? t('screen.watchlist.chooseVenue')
                                  : t('screen.watchlist.openWorkspace')}
                              </Link>
                            )}
                          </td>
                        </tr>
                      )})}
                  </tbody>
                </table>
              </div>
            </div>
          )
        }}
      </Surface>
    </Page>
  )
}

type AttentionBucket = 'triggered' | 'blocked' | 'review_due' | 'no_action'
type ActionFilter = AttentionBucket | 'all'

function attentionBucket(entry: DecisionInbox['entries'][number]): AttentionBucket {
  if (entry.attention_state === 'not_started') return 'no_action'
  if (entry.attention_state === 'watch_triggered') return 'triggered'
  if (
    entry.readiness.status === 'blocked'
    || entry.readiness.status === 'unavailable'
    || entry.attention_state === 'blocked'
    || entry.attention_state === 'unavailable'
  ) return 'blocked'
  if (entry.attention_state === 'review_available') return 'review_due'
  return 'no_action'
}

function RefreshFailures({
  result,
}: {
  result: Awaited<ReturnType<typeof api.refreshDecisionSession>>
}) {
  const { t } = usePreferences()
  const failed = result.items.filter(item => item.status === 'failed')
  if (failed.length === 0) return null
  return <ul aria-label={t('screen.watchlist.refreshFailures')} className="w-full space-y-1 text-xs text-muted-foreground">
    {failed.map(item => <li key={item.packet_id} className="break-words">
      <span className="font-mono text-foreground">{item.packet_id}</span>{' '}
      <span title={item.reason ?? undefined}>
        {refreshFailureReason(item.reason_code, item.reason, t)}
      </span>
    </li>)}
  </ul>
}

function refreshFeedback(
  result: Awaited<ReturnType<typeof api.refreshDecisionSession>>,
  t: ReturnType<typeof usePreferences>['t'],
): string {
  if (result.status === 'no_registered_watches') {
    return t('screen.watchlist.refreshNoRegistered')
  }
  const triggered = result.items.filter(item => item.triggered).length
  if (result.status === 'partial') {
    return t('screen.watchlist.refreshPartial', {
      evaluated: String(result.evaluated_count),
      registered: String(result.registered_count),
    })
  }
  return t('screen.watchlist.refreshComplete', {
    count: String(result.evaluated_count),
    triggered: String(triggered),
  })
}

function refreshFailureReason(
  code: string | null,
  fallback: string | null,
  t: ReturnType<typeof usePreferences>['t'],
): string {
  const keys = {
    packet_unavailable: 'screen.watchlist.refreshReason.packetUnavailable',
    local_workspace_unavailable: 'screen.watchlist.refreshReason.workspaceUnavailable',
    local_evaluation_unavailable: 'screen.watchlist.refreshReason.evaluationUnavailable',
  } as const
  return code !== null && hasOwnKey(keys, code) ? t(keys[code]) : fallback ?? code ?? ''
}

function ReadinessFacts({
  entry,
  locale,
}: {
  entry: DecisionInbox['entries'][number]
  locale: ReturnType<typeof usePreferences>['locale']
}) {
  const { t } = usePreferences()
  const readiness = entry.readiness
  return (
    <div className="mt-2 min-w-0 space-y-0.5 text-xs text-muted-foreground">
      <p className="font-medium text-foreground">{readinessState(readiness.status, t)}</p>
      <p className="max-w-sm break-words" title={readiness.reason}>{readinessReason(readiness.reason_code, readiness.reason, t)}</p>
      {readiness.limiting_evidence_at && (
        <p>{t('screen.watchlist.evidenceAt', { time: dateTime(readiness.limiting_evidence_at, locale) })}</p>
      )}
      <p>{t('screen.watchlist.readinessEvaluated', { time: dateTime(readiness.checked_at, locale) })}</p>
      {entry.monitoring?.last_checked_at && <>
        <p>{t('screen.watchlist.lastLocalCheck', { time: dateTime(entry.monitoring.last_checked_at, locale) })}</p>
        {entry.monitoring.latest_status && <p title={entry.monitoring.latest_status}>{monitoringStatus(entry.monitoring.latest_status, t)}</p>}
        {entry.monitoring.latest_reason && <p title={entry.monitoring.latest_reason}>{monitoringReason(entry.monitoring.latest_reason, t)}</p>}
      </>}
      {entry.mark_context.received_at && (
        <p>{t('screen.watchlist.markReceived', { time: dateTime(entry.mark_context.received_at, locale) })}</p>
      )}
      {entry.mark_context.reason && <p className="max-w-sm break-words">{entry.mark_context.reason}</p>}
    </div>
  )
}

function ShadowRecords({ entry }: { entry: DecisionInbox['entries'][number] }) {
  const { t } = usePreferences()
  if (!entry.packet_id) return null
  const records = [
    [t('screen.watchlist.record.packet'), entry.packet_id],
    [t('screen.watchlist.record.proposal'), entry.paper?.proposal_id],
    [t('screen.watchlist.record.order'), entry.paper?.order_id],
    [t('screen.watchlist.record.registration'), entry.monitoring?.registration_id],
    [t('screen.watchlist.record.evaluation'), entry.monitoring?.latest_evaluation_id],
    ...(entry.monitoring?.event_ids ?? []).map(id => [t('screen.watchlist.record.event'), id]),
    [t('screen.watchlist.record.outcome'), entry.outcome_id],
    [t('screen.watchlist.record.review'), entry.review?.review_id],
    ...(entry.review && entry.review.outcome_id !== entry.outcome_id
      ? [[t('screen.watchlist.record.reviewOutcome'), entry.review.outcome_id]] : []),
  ].filter((record): record is [string, string] => typeof record[1] === 'string')
  return (
    <details className="mt-2 max-w-sm text-xs">
      <summary className="cursor-pointer py-1 underline-offset-4 hover:underline focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {t('screen.watchlist.records')}
      </summary>
      <dl className="mt-2 space-y-2 border-t border-border pt-2">
        {entry.paper && <div>
          <dt className="text-muted-foreground">{t('screen.watchlist.record.proposalStatus')}</dt>
          <dd>{recordStatus(entry.paper.status, t)}</dd>
        </div>}
        {entry.paper?.order_status && <div>
          <dt className="text-muted-foreground">{t('screen.watchlist.record.orderStatus')}</dt>
          <dd>{recordStatus(entry.paper.order_status, t)}</dd>
        </div>}
        {entry.paper?.filled_quantity != null && <div>
          <dt className="text-muted-foreground">{t('screen.watchlist.record.filledQuantity')}</dt>
          <dd className="font-mono tabular-nums">{entry.paper.filled_quantity}</dd>
        </div>}
        {entry.monitoring && <div>
          <dt className="text-muted-foreground">{t('screen.watchlist.record.watchStatus')}</dt>
          <dd>{entry.monitoring.triggered
            ? t('screen.workspace.monitoringTriggered')
            : t('screen.watchlist.record.coverageIncomplete')}</dd>
        </div>}
        {entry.review && <div>
          <dt className="text-muted-foreground">{t('screen.workspace.reviewClassification')}</dt>
          <dd>{recordStatus(entry.review.state, t)}</dd>
        </div>}
        {records.map(([label, id]) => <div key={`${label}:${id}`}>
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="font-mono break-all">{id}</dd>
        </div>)}
      </dl>
      <p className="mt-3 text-muted-foreground">{t('screen.watchlist.positionContext')}</p>
    </details>
  )
}

function recordStatus(state: string, t: ReturnType<typeof usePreferences>['t']): string {
  const keys = {
    pending: 'screen.watchlist.record.pending',
    confirmed: 'screen.watchlist.record.confirmed',
    blocked: 'screen.watchlist.record.blocked',
    rejected: 'screen.watchlist.record.rejected',
    accepted: 'screen.watchlist.record.accepted',
    filled: 'screen.watchlist.record.filled',
    partially_filled: 'screen.watchlist.record.partiallyFilled',
    canceled: 'screen.watchlist.record.cancelled',
    supported: 'screen.workspace.reviewSupported',
    challenged: 'screen.workspace.reviewChallenged',
    mixed: 'screen.workspace.reviewMixed',
    inconclusive: 'screen.workspace.reviewInconclusive',
  } as const
  return state in keys ? t(keys[state as keyof typeof keys]) : state
}

function attentionState(
  state: DecisionInbox['entries'][number]['attention_state'],
  t: ReturnType<typeof usePreferences>['t'],
): string {
  const keys = {
    blocked: 'screen.watchlist.state.blocked',
    draft: 'screen.watchlist.state.draft',
    not_started: 'screen.watchlist.state.notStarted',
    paper_open: 'screen.watchlist.state.paperOpen',
    paper_pending_confirmation: 'screen.watchlist.state.pendingConfirmation',
    rejected: 'screen.watchlist.state.rejected',
    review_available: 'screen.watchlist.state.reviewAvailable',
    reviewed: 'screen.watchlist.state.reviewed',
    unavailable: 'screen.watchlist.state.unavailable',
    watch_triggered: 'screen.watchlist.state.watchTriggered',
    watching: 'screen.watchlist.state.watching',
  } as const
  return t(keys[state as keyof typeof keys])
}

function readinessState(
  state: DecisionInbox['entries'][number]['readiness']['status'],
  t: ReturnType<typeof usePreferences>['t'],
): string {
  const keys = {
    blocked: 'screen.watchlist.readiness.blocked',
    demo: 'screen.watchlist.readiness.demo',
    ready: 'screen.watchlist.readiness.ready',
    unavailable: 'screen.watchlist.readiness.unavailable',
  } as const
  return t(keys[state])
}

function readinessReason(code: string, fallback: string, t: ReturnType<typeof usePreferences>['t']): string {
  const keys = {
    demo_evidence: 'screen.watchlist.reason.demoEvidence',
    catalog_unavailable: 'screen.watchlist.reason.catalogUnavailable',
    missing_history_binding: 'screen.watchlist.reason.missingHistoryBinding',
    trusted_evidence: 'screen.watchlist.reason.trustedEvidence',
    missing_forecast_binding: 'screen.watchlist.reason.missingForecastBinding',
    history_manifest_unavailable: 'screen.watchlist.reason.historyManifestUnavailable',
    history_catalog_unavailable: 'screen.watchlist.reason.historyCatalogUnavailable',
    history_manifest_mismatch: 'screen.watchlist.reason.historyManifestMismatch',
    history_quality_unavailable: 'screen.watchlist.reason.historyQualityUnavailable',
    history_evaluation_mismatch: 'screen.watchlist.reason.historyEvaluationMismatch',
    history_checkpoint_mismatch: 'screen.watchlist.reason.historyCheckpointMismatch',
    history_rights_unknown: 'screen.watchlist.reason.historyRightsUnknown',
    history_not_trusted: 'screen.watchlist.reason.historyNotTrusted',
    forecast_manifest_unavailable: 'screen.watchlist.reason.forecastManifestUnavailable',
    forecast_catalog_unavailable: 'screen.watchlist.reason.forecastCatalogUnavailable',
    forecast_manifest_mismatch: 'screen.watchlist.reason.forecastManifestMismatch',
    forecast_quality_unavailable: 'screen.watchlist.reason.forecastQualityUnavailable',
    forecast_evaluation_mismatch: 'screen.watchlist.reason.forecastEvaluationMismatch',
    forecast_checkpoint_mismatch: 'screen.watchlist.reason.forecastCheckpointMismatch',
    forecast_rights_unknown: 'screen.watchlist.reason.forecastRightsUnknown',
    forecast_not_trusted: 'screen.watchlist.reason.forecastNotTrusted',
    no_saved_packet: 'screen.watchlist.reason.noSavedPacket',
    venue_unavailable: 'screen.watchlist.reason.venueUnavailable',
  } as const
  return hasOwnKey(keys, code) ? t(keys[code]) : fallback
}

function monitoringStatus(state: string, t: ReturnType<typeof usePreferences>['t']): string {
  const keys = {
    armed: 'screen.watchlist.monitoring.armed',
    not_triggered: 'screen.watchlist.monitoring.notTriggered',
    triggered: 'screen.workspace.monitoringTriggered',
    not_comparable: 'screen.watchlist.monitoring.notComparable',
  } as const
  return localizeKnownCodes(state, keys, t, ', ')
}

function monitoringReason(code: string, t: ReturnType<typeof usePreferences>['t']): string {
  const keys = {
    unusable_price_evidence: 'screen.watchlist.reason.unusablePriceEvidence',
    future_reference: 'screen.watchlist.reason.futureReference',
    calendar_unavailable: 'screen.watchlist.reason.calendarUnavailable',
    missing_forecast: 'screen.watchlist.reason.missingForecast',
    candidate_not_comparable: 'screen.watchlist.reason.candidateNotComparable',
    candidate_incompatible: 'screen.watchlist.reason.candidateIncompatible',
    quote_missing: 'screen.watchlist.reason.quoteMissing',
  } as const
  return localizeKnownCodes(code, keys, t, '; ')
}

function localizeKnownCodes(
  value: string,
  keys: Record<string, MessageKey>,
  t: ReturnType<typeof usePreferences>['t'],
  separator: string,
): string {
  return value.split(separator).map(code => hasOwnKey(keys, code) ? t(keys[code]) : code).join(separator)
}

function hasOwnKey(keys: Record<string, MessageKey>, code: string): code is keyof typeof keys {
  return Object.prototype.hasOwnProperty.call(keys, code)
}

function markStatus(
  state: 'available' | 'stale' | 'unavailable',
  t: ReturnType<typeof usePreferences>['t'],
): string {
  const keys = {
    available: 'screen.watchlist.mark.available',
    stale: 'screen.watchlist.mark.stale',
    unavailable: 'screen.watchlist.mark.unavailable',
  } as const
  return t(keys[state])
}
