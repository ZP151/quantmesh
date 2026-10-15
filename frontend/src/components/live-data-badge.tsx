import type { LiveLabel, SessionFreshness } from '@/lib/api'
import { LABEL_TEXT, labelTone } from '@/lib/live'
import type { MessageKey } from '@/lib/messages'
import { usePreferences } from '@/lib/preferences'
import { Badge } from '@/components/ui/badge'

/** Presentation only: raw age/labels and deterministic quote fences remain intact. */
export function liveDataPresentation(
  session: SessionFreshness | undefined,
  fallback: LiveLabel,
  nowMs = Date.now(),
  realEvidence = true,
): { key: MessageKey; tone: string } {
  const legacy = { key: LABEL_TEXT[fallback], tone: labelTone(fallback) }
  if (!session || !realEvidence || fallback === 'synthetic') return legacy
  const neutral = 'bg-muted text-muted-foreground'
  if (session.policy_version !== 'quantmesh:session-freshness:1') {
    return { key: 'live.session.unknown', tone: neutral }
  }
  if (session.market_state === 'closed') {
    const next = Date.parse(session.next_open_at ?? '')
    if (!Number.isFinite(next) || !Number.isFinite(nowMs) || nowMs >= next) {
      return { key: 'live.session.refresh', tone: neutral }
    }
    if (session.data_state === 'latest_session') return { key: 'live.session.closedLatest', tone: neutral }
    if (session.data_state === 'missing') return { key: 'live.session.closedMissing', tone: labelTone('delayed') }
    return { key: 'live.session.closedUnknown', tone: neutral }
  }
  if (session.data_state === 'missing') return { key: 'live.session.missing', tone: labelTone('delayed') }
  if (session.data_state === 'delayed') return { key: 'live.session.delayed', tone: labelTone('delayed') }
  if (session.data_state === 'unknown') return { key: 'live.session.unknown', tone: neutral }
  if (session.market_state === 'open' && session.data_state === 'fresh') {
    // Expire the server evaluation, never recompute exchange slots in the UI.
    const evaluated = Date.parse(session.evaluated_at ?? '')
    if (session.provider_delay_seconds == null || !Number.isFinite(evaluated)) {
      return { key: 'live.session.unknown', tone: neutral }
    }
    if (!Number.isFinite(nowMs) || nowMs < evaluated || nowMs - evaluated >= 30_000) {
      return { key: 'live.session.refresh', tone: neutral }
    }
    return { key: session.provider_delay_seconds && session.provider_delay_seconds > 0
      ? 'live.session.declaredDelay' : 'live.session.open', tone: labelTone('real') }
  }
  return { key: 'live.session.unknown', tone: neutral }
}

export function LiveDataBadge({ session, fallback, realEvidence = true, sourceUnavailable = false }: {
  session?: SessionFreshness; fallback: LiveLabel; realEvidence?: boolean; sourceUnavailable?: boolean
}) {
  const { t } = usePreferences()
  const presentation = liveDataPresentation(session, fallback, Date.now(), realEvidence)
  return <span className="inline-flex flex-wrap items-center gap-1">
    <Badge className={presentation.tone} title={session?.reason}>{t(presentation.key)}</Badge>
    {sourceUnavailable && presentation.key !== 'live.label.unavailable'
      && <Badge className={labelTone('unavailable')}>{t('live.session.sourceUnavailable')}</Badge>}
  </span>
}
