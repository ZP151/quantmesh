import { expect, it } from 'vitest'
import { evidenceLabel, uiText } from './presentation-copy'
import { dateTime } from './format'
import { translate } from './messages'
import { nativeDailyCopy, spyReplayCopy, spyReplayFlow, readinessDetailCopy } from './messages/research'

it('keeps engineering qualification limits in both semantic status labels', () => {
  expect(evidenceLabel('ACCEPTED_ENGINEERING', 'en')).toMatch(/not financially qualified/)
  expect(evidenceLabel('ACCEPTED_ENGINEERING', 'zh-CN')).toContain('金融资格未通过')
  expect(evidenceLabel('ACCEPTED_DECLARED_RESEARCH', 'zh-CN')).toContain('金融证据仍不足')
  expect(evidenceLabel('UNKNOWN_VENDOR_STATUS', 'zh-CN')).toBe('UNKNOWN_VENDOR_STATUS')
  const raw = 'unknown 原始证据; 00.0001 / Z'
  expect(uiText(raw, 'zh-CN')).toBe(raw)
})

it('localizes known recovery text without losing interpolated response status', () => {
  const source = 'Submission refused ({{status}}). The original key and payload are retained.'
  expect(uiText(source, 'zh-CN', { status: '409' })).toBe('提交被拒绝（409），原请求键和内容已保留。')
  expect(translate('zh-CN', 'screen.workspace.sessions', { count: '30' })).toContain('30')
})

it('keeps centralized research catalogs complete in both languages', () => {
  expect(nativeDailyCopy['zh-CN'].safety).not.toContain('INSUFFICIENT')
  expect(nativeDailyCopy['zh-CN'].engineering).not.toContain('INSUFFICIENT')
  for (const catalog of [nativeDailyCopy, spyReplayCopy, spyReplayFlow, readinessDetailCopy]) {
    expect(Object.keys(catalog.en).sort()).toEqual(Object.keys(catalog['zh-CN']).sort())
    expect(Object.values(catalog['zh-CN']).every(value => value.trim().length > 0)).toBe(true)
  }
})

it('gives timestamps a year and explicit UTC context while retaining invalid originals', () => {
  for (const locale of ['en', 'zh-CN'] as const) {
    expect(dateTime('2026-11-11T23:59:00+08:00', locale)).toContain('2026')
    expect(dateTime('2026-11-11T23:59:00+08:00', locale)).toContain('UTC')
    expect(dateTime('unchanged invalid original', locale)).toBe('unchanged invalid original')
  }
})
