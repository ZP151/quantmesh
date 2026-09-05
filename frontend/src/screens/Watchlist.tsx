import { Link } from 'react-router-dom'
import { Page } from '@/components/page'
import { Surface, useSurface } from '@/components/state'
import { api, type DecisionInbox } from '@/lib/api'
import { decisionPacketPath, instrumentPath } from '@/lib/instrument-route'
import { money } from '@/lib/format'
import { usePreferences } from '@/lib/preferences'

/** The watchlist: venue-scoped favorites with their marks. Every action
 * consumes the identity carried by its own API row; symbols are never
 * resolved by a first-match lookup across venues. */
export function WatchlistScreen() {
  const query = useSurface(['decision-inbox'], api.decisionInbox)
  const { t } = usePreferences()

  return (
    <Page
      title={t('screen.watchlist.title')}
      description={t('screen.watchlist.description')}
    >
      <Surface
        query={query}
        title={t('screen.watchlist.title')}
        empty={<p className="border-y border-border py-6 text-sm text-muted-foreground">{t('screen.watchlist.empty')}</p>}
      >
        {(inbox) => (
          <div className="border-y border-border">
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
                    {inbox.entries.map((entry) => {
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
                            {entry.symbol}
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
        )}
      </Surface>
    </Page>
  )
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
