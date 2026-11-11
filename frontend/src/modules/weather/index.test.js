import { describe, expect, it } from 'vitest'
import enFull, { core as coreEn } from '../../i18n/en.js'
import bgFull, { core as coreBg } from '../../i18n/bg.js'
import snapshot from '../../i18n/keys.snapshot.json'
import { recolorFor as legacyRecolorFor } from '../../lib/weatherTiles.js'
import { windPoint as legacyWindPoint } from '../../lib/wind.js'
import { checkModules } from '../../platform/registry.js'
import { MODULES } from '../index.js'
import { recolorFor } from './lib/weatherTiles.js'
import { windPoint } from './lib/wind.js'
import weather from './index.js'

function has(obj, dotted) {
  let cur = obj
  for (const part of dotted.split('.')) {
    if (cur == null || typeof cur !== 'object' || !(part in cur)) return false
    cur = cur[part]
  }
  return typeof cur === 'string'
}

const weatherKeys = (Array.isArray(snapshot) ? snapshot : snapshot.keys).filter((k) => k.startsWith('map.weather'))

describe('weather module (part 1)', () => {
  it('the weather manifest is valid and is in the module list [T521]', () => {
    expect(MODULES).toContain(weather)
    expect(weather.name).toBe('weather')
    expect(checkModules(MODULES)).toEqual([])
  })

  it('the weather texts keep their keys in both languages [T521]', () => {
    expect(weatherKeys.length).toBeGreaterThan(0)
    for (const key of weatherKeys) {
      expect(has(enFull, key), `en ${key}`).toBe(true)
      expect(has(bgFull, key), `bg ${key}`).toBe(true)
      expect(has(coreEn, key), `core en ${key}`).toBe(false)
      expect(has(coreBg, key), `core bg ${key}`).toBe(false)
    }
  })

  it('the old library paths are the moved libraries [T521]', () => {
    expect(legacyRecolorFor).toBe(recolorFor)
    expect(legacyWindPoint).toBe(windPoint)
  })
})
