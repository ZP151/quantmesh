import type { MessageKey } from '@/lib/messages'
import type { Locale } from '@/lib/preferences'

type Translate = (key: MessageKey, vars?: Record<string, string>) => string

const EXACT: Record<string, MessageKey> = {
  'Deterministic demo-synthetic analytical history.': 'screen.workspace.evidence.demoHistory',
  'Intervals are empirical and do not imply a probability of profit or execution outcome.': 'screen.workspace.evidence.empiricalIntervals',
  'Prototype baseline uses weekday sessions for equities and does not model exchange holidays.': 'screen.workspace.evidence.weekdayCalendar',
  'Synthetic data': 'screen.workspace.evidence.syntheticData',
  'The artifact is research evidence; the paper kernel remains the only order authority.': 'screen.workspace.evidence.paperAuthority',
  'no live feed is attached': 'screen.workspace.evidence.noLiveFeed',
  'no live quote is available for this venue and symbol': 'screen.workspace.evidence.noLiveQuote',
  'quote has no usable bid/ask depth': 'screen.workspace.evidence.noDepth',
  'quote receipt time is in the future': 'screen.workspace.evidence.futureQuote',
  'quote sequence has a gap (discontinuous)': 'screen.workspace.evidence.sequenceGap',
}

function localizedSegment(value: string, t: Translate): string {
  const exact = EXACT[value]
  if (exact !== undefined) return t(exact)
  if (value.startsWith('quote provenance is ')) {
    return t('screen.workspace.evidence.quoteProvenance', { value: value.slice(20) })
  }
  if (value.startsWith('quote freshness is ')) {
    return t('screen.workspace.evidence.quoteFreshness', { value: value.slice(19) })
  }
  return value
}

/** Localize known server evidence while preserving unknown authoritative text verbatim. */
export function evidenceText(value: string, locale: Locale, t: Translate): string {
  if (locale !== 'zh-CN') return value
  const exact = EXACT[value]
  if (exact !== undefined) return t(exact)
  return value.split('; ').map((segment) => localizedSegment(segment, t)).join('；')
}
