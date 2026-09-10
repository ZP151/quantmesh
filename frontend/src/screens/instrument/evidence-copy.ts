import type { MessageKey } from '@/lib/messages'
import type { Locale } from '@/lib/preferences'

type Translate = (key: MessageKey, vars?: Record<string, string>) => string

const EXACT: Record<string, MessageKey> = {
  'paper valuation or mark is incomplete': 'lab.reason.valuation',
  'a paper kill switch is enabled': 'lab.reason.kill',
  'no live feed is attached; kill switch enabled': 'lab.reason.noFeedKill',
  'observed trend and upper forecast quantile support continuation': 'lab.reason.bullThesis',
  'observed structure and median forecast path remain intact': 'lab.reason.baseThesis',
  'support failure invalidates the observed structure': 'lab.reason.bearThesis',
  'observed close holds above resistance': 'lab.reason.bullTrigger',
  'observed close holds above support': 'lab.reason.baseTrigger',
  'observed close falls below support': 'lab.reason.bearTrigger',
  'forecast quantiles are qualitative and not calibrated probabilities': 'lab.reason.qualitative',
  'daily history is unavailable or has quality limitations': 'lab.reason.dailyQuality',
  'history contains future knowledge or a live tail': 'lab.reason.futureHistory',
  'history generation violates as-of chronology': 'lab.reason.historyChronology',
  'history is missing exact manifest evidence': 'lab.reason.manifestMissing',
  'history evidence is stale': 'lab.reason.historyStale',
  'latest observed daily bar is stale': 'lab.reason.barStale',
  'selected forecast evidence is unavailable': 'lab.reason.forecastMissing',
  'history does not match the exact forecast dataset, manifest or as-of cut': 'lab.reason.bindingMismatch',
  'forecast evidence violates as-of chronology': 'lab.reason.forecastChronology',
  'forecast evidence is stale': 'lab.reason.forecastStale',
  'artifact-wide eligibility failed': 'lab.reason.artifactFailed',
  'selected horizon has no resolved residuals or evaluated intervals': 'lab.reason.noSamples',
  'at least 30 resolved residuals are required': 'lab.reason.residuals',
  'at least 30 evaluated intervals are required': 'lab.reason.intervals',
  'empirical 80% coverage is outside [0.60, 0.98]': 'lab.reason.coverageFailed',
  'MAE must be strictly below last-price random-walk MAE': 'lab.reason.maeFailed',
  'selected 7-session path or metrics are unavailable': 'lab.reason.sevenMissing',
  'selected 30-session path or metrics are unavailable': 'lab.reason.thirtyMissing',
  'Residual rows overlap and are not independent observations.': 'lab.reason.overlap',
  'Intermediate path bands use a square-root scaling approximation, not per-time calibration.': 'lab.reason.scaling',
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
