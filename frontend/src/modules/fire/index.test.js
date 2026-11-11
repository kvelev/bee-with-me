import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it } from 'vitest'
import enFull from '../../i18n/en.js'
import bgFull from '../../i18n/bg.js'
import {
  collectBanners, collectContextMenu, collectPanels, collectPopups, contributionProblems, popupFor,
} from '../../platform/map-shell/contributions.js'
import { checkModules } from '../../platform/registry.js'
import { useFireStore as legacyUseFireStore } from '../../stores/fire.js'
import { MODULES } from '../index.js'
import mapViewSource from '../../views/MapView.vue?raw'
import fire, { useFireStore, useFireUi } from './index.js'

describe('fire module manifest', () => {
  it('the fire manifest is valid and is in the module list [T505]', () => {
    expect(MODULES).toContain(fire)
    expect(fire.name).toBe('fire')
    expect(checkModules(MODULES)).toEqual([])
  })

  it('the fire banner is a manifest contribution below SOS [T505]', () => {
    expect(collectBanners(MODULES).map((b) => b.id)).toEqual(['sos', 'fire-alarm'])
    expect(contributionProblems(MODULES)).toEqual([])
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

describe('fire module manifest: popup, menu item and dialogs', () => {
  it('the popup, the menu item and the panels are manifest contributions and MapView has no legacy entry [T508]', () => {
    expect(collectPopups(MODULES).map((p) => p.id)).toEqual(['fire'])
    expect(popupFor(collectPopups(MODULES), 'hotspot')?.id).toBe('fire')
    expect(popupFor(collectPopups(MODULES), 'burnt_area')?.id).toBe('fire')
    const item = collectContextMenu(MODULES).find((i) => i.id === 'fire-report-here')
    expect(item).toMatchObject({ order: 10, labelKey: 'fire.report.here', testId: 'report-fire-here' })
    expect(collectPanels(MODULES, 'map').map((p) => p.id)).toContain('fire-dialogs')
    expect(contributionProblems(MODULES)).toEqual([])
    expect(checkModules(MODULES)).toEqual([])
    expect(mapViewSource).not.toContain('until step 2')
  })

  it('the report menu item opens the report dialog at the pointer [T508]', () => {
    setActivePinia(createPinia())
    const item = fire.contextMenu.find((i) => i.id === 'fire-report-here')
    item.onSelect({ lonLat: [24.5, 42.5] })
    expect(useFireUi().dialog).toEqual({ kind: 'report', target: { latitude: 42.5, longitude: 24.5 } })
  })
})
