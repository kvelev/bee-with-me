import { describe, expect, it } from 'vitest'
import enFull from '../../i18n/en.js'
import bgFull from '../../i18n/bg.js'
import { LEGACY_BANNERS } from '../../components/legacyBanners.js'
import { collectBanners, contributionProblems } from '../../platform/map-shell/contributions.js'
import { checkModules } from '../../platform/registry.js'
import { useFireStore as legacyUseFireStore } from '../../stores/fire.js'
import { MODULES } from '../index.js'
import fire, { useFireStore } from './index.js'

describe('fire module manifest', () => {
  it('the fire manifest is valid and is in the module list [T505]', () => {
    expect(MODULES).toContain(fire)
    expect(fire.name).toBe('fire')
    expect(checkModules(MODULES)).toEqual([])
  })

  it('the fire banner is a manifest contribution below SOS [T505]', () => {
    expect(collectBanners(MODULES, LEGACY_BANNERS).map((b) => b.id)).toEqual(['sos', 'fire-alarm'])
    expect(contributionProblems(MODULES, { banners: LEGACY_BANNERS })).toEqual([])
    const item = fire.banners.find((b) => b.id === 'fire-alarm')
    expect(typeof item.component).not.toBe('function')
    expect(item.component).toBeTruthy()
  })

  it('the old store path is the same store [T505]', () => {
    expect(legacyUseFireStore).toBe(useFireStore)
  })

  it('the fire texts are in the merged dictionaries in both languages [T505]', () => {
    for (const d of [enFull, bgFull]) {
      expect(d.fire.asOf).toBeTruthy()
      expect(Object.keys(d.fireAlarm).length).toBeGreaterThan(10)
    }
  })
})
