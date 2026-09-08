import { describe, expect, it } from 'vitest'
import { messages, type MessageKey } from './messages'

function placeholders(text: string): string[] {
  return (text.match(/\{\{(\w+)\}\}/g) ?? []).sort()
}

/** Locale coverage (iteration 0017): the type system already forbids a
 * missing zh-CN key at compile time (indexing messages['zh-CN'] with a
 * MessageKey), but these runtime checks also pin key-for-key parity,
 * identical {{var}} placeholders, and non-empty translations — the
 * contract the extracted screens depend on. */
describe('message table locale coverage', () => {
  it('covers every en key in zh-CN with no extra or missing keys', () => {
    expect(Object.keys(messages['zh-CN']).sort()).toEqual(Object.keys(messages.en).sort())
  })

  it('keeps the {{var}} placeholders identical between locales for every key', () => {
    for (const key of Object.keys(messages.en) as MessageKey[]) {
      expect(placeholders(messages['zh-CN'][key]), `zh-CN placeholder mismatch for ${key}`).toEqual(
        placeholders(messages.en[key]),
      )
    }
  })

  it('has no empty zh-CN translations', () => {
    for (const key of Object.keys(messages.en) as MessageKey[]) {
      expect(messages['zh-CN'][key].trim(), `empty zh-CN translation for ${key}`).not.toBe('')
    }
  })

  it.each([
    ['readiness reason', 'demo_evidence', 'screen.watchlist.reason.demoEvidence', 'This packet uses demo-synthetic evidence.', '此决策包使用演示合成证据。'],
    ['readiness reason', 'catalog_unavailable', 'screen.watchlist.reason.catalogUnavailable', 'Trusted evidence catalog is unavailable.', '可信证据目录不可用。'],
    ['readiness reason', 'missing_history_binding', 'screen.watchlist.reason.missingHistoryBinding', 'Exact history manifest and quality evaluation are required.', '需要精确的历史清单和质量评估。'],
    ['readiness reason', 'trusted_evidence', 'screen.watchlist.reason.trustedEvidence', 'Exact packet evidence is trusted for research.', '精确决策包证据可用于研究。'],
    ['readiness reason', 'missing_forecast_binding', 'screen.watchlist.reason.missingForecastBinding', 'Exact forecast manifest and quality evaluation are required.', '需要精确的预测清单和质量评估。'],
    ['readiness reason', 'history_manifest_unavailable', 'screen.watchlist.reason.historyManifestUnavailable', 'Exact history manifest is unavailable.', '精确历史清单不可用。'],
    ['readiness reason', 'history_catalog_unavailable', 'screen.watchlist.reason.historyCatalogUnavailable', 'Exact history catalog closure is unavailable.', '精确历史目录闭包不可用。'],
    ['readiness reason', 'history_manifest_mismatch', 'screen.watchlist.reason.historyManifestMismatch', 'Exact history manifest identity does not match this packet.', '精确历史清单身份与此决策包不匹配。'],
    ['readiness reason', 'history_quality_unavailable', 'screen.watchlist.reason.historyQualityUnavailable', 'Exact history quality evidence is unavailable.', '精确历史质量证据不可用。'],
    ['readiness reason', 'history_evaluation_mismatch', 'screen.watchlist.reason.historyEvaluationMismatch', 'Exact quality evaluation does not match this packet.', '精确质量评估与此决策包不匹配。'],
    ['readiness reason', 'history_checkpoint_mismatch', 'screen.watchlist.reason.historyCheckpointMismatch', 'Exact history quality report does not match its checkpoint.', '精确历史质量报告与其检查点不匹配。'],
    ['readiness reason', 'history_rights_unknown', 'screen.watchlist.reason.historyRightsUnknown', 'Exact history source rights are unknown.', '精确历史来源权利未知。'],
    ['readiness reason', 'history_not_trusted', 'screen.watchlist.reason.historyNotTrusted', 'Exact history evidence is not trusted for research.', '精确历史证据不受研究信任。'],
    ['readiness reason', 'forecast_manifest_unavailable', 'screen.watchlist.reason.forecastManifestUnavailable', 'Exact forecast manifest is unavailable.', '精确预测清单不可用。'],
    ['readiness reason', 'forecast_catalog_unavailable', 'screen.watchlist.reason.forecastCatalogUnavailable', 'Exact forecast catalog closure is unavailable.', '精确预测目录闭包不可用。'],
    ['readiness reason', 'forecast_manifest_mismatch', 'screen.watchlist.reason.forecastManifestMismatch', 'Exact forecast manifest identity does not match this packet.', '精确预测清单身份与此决策包不匹配。'],
    ['readiness reason', 'forecast_quality_unavailable', 'screen.watchlist.reason.forecastQualityUnavailable', 'Exact forecast quality evidence is unavailable.', '精确预测质量证据不可用。'],
    ['readiness reason', 'forecast_evaluation_mismatch', 'screen.watchlist.reason.forecastEvaluationMismatch', 'Exact quality evaluation does not match this packet.', '精确质量评估与此决策包不匹配。'],
    ['readiness reason', 'forecast_checkpoint_mismatch', 'screen.watchlist.reason.forecastCheckpointMismatch', 'Exact forecast quality report does not match its checkpoint.', '精确预测质量报告与其检查点不匹配。'],
    ['readiness reason', 'forecast_rights_unknown', 'screen.watchlist.reason.forecastRightsUnknown', 'Exact forecast source rights are unknown.', '精确预测来源权利未知。'],
    ['readiness reason', 'forecast_not_trusted', 'screen.watchlist.reason.forecastNotTrusted', 'Exact forecast evidence is not trusted for research.', '精确预测证据不受研究信任。'],
    ['Inbox readiness reason', 'no_saved_packet', 'screen.watchlist.reason.noSavedPacket', 'No saved DecisionPacket exists yet.', '尚无已保存的决策包。'],
    ['Inbox readiness reason', 'venue_unavailable', 'screen.watchlist.reason.venueUnavailable', 'A venue is required to resolve exact packet evidence.', '解析精确决策包证据需要市场。'],
    ['monitoring status', 'armed', 'screen.watchlist.monitoring.armed', 'Armed', '已布防'],
    ['monitoring status', 'not_triggered', 'screen.watchlist.monitoring.notTriggered', 'Not triggered', '未触发'],
    ['monitoring status', 'triggered', 'screen.workspace.monitoringTriggered', 'Triggered', '已触发'],
    ['monitoring status', 'not_comparable', 'screen.watchlist.monitoring.notComparable', 'Not comparable', '无法比较'],
    ['monitoring reason', 'unusable_price_evidence', 'screen.watchlist.reason.unusablePriceEvidence', 'Price evidence cannot be used for this watch.', '价格证据不能用于此观察。'],
    ['monitoring reason', 'future_reference', 'screen.watchlist.reason.futureReference', 'Watch reference time is in the future.', '观察参考时间在未来。'],
    ['monitoring reason', 'calendar_unavailable', 'screen.watchlist.reason.calendarUnavailable', 'Watch calendar is unavailable.', '观察日历不可用。'],
    ['monitoring reason', 'missing_forecast', 'screen.watchlist.reason.missingForecast', 'Required forecast is unavailable.', '所需预测不可用。'],
    ['monitoring reason', 'candidate_not_comparable', 'screen.watchlist.reason.candidateNotComparable', 'Candidate forecast cannot be compared.', '候选预测无法比较。'],
    ['monitoring reason', 'candidate_incompatible', 'screen.watchlist.reason.candidateIncompatible', 'Candidate forecast is incompatible.', '候选预测不兼容。'],
  ])('provides reviewed %s copy for %s', (_family, _code, key, english, chinese) => {
    const englishMessages = messages.en as Record<string, string>
    const chineseMessages = messages['zh-CN'] as Record<string, string>
    expect(englishMessages[key]).toBe(english)
    expect(chineseMessages[key]).toBe(chinese)
  })
})
