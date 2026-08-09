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
})
