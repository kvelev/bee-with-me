import { describe, expect, it } from 'vitest'
import source from './SelectOfflineMap.vue?raw'
import { i18n } from '../i18n/index.js'

describe('SelectOfflineMap i18n', () => {
  it('every key the view uses exists in both dictionaries [B102]', () => {
    const keys = [...source.matchAll(/\bt\('([^']+)'\)/g)].map((m) => m[1])
    expect(keys.length).toBeGreaterThan(4)
    const missing = []
    for (const locale of ['en', 'bg']) {
      for (const key of keys) if (!i18n.global.te(key, locale)) missing.push(`${locale}:${key}`)
    }
    expect(missing).toEqual([])
  })
})
