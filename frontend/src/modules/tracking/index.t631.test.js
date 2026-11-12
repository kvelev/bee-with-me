import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { collectActions, collectPanels, contributionProblems } from '../../platform/map-shell/contributions.js'
import { checkModules } from '../../platform/registry.js'
import { MODULES } from '../index.js'
import fire, { useFireUi } from '../fire/index.js'
import tracking, { useTrackerUi } from './index.js'

beforeEach(() => { setActivePinia(createPinia()) })

describe('the tracker panel as a contribution', () => {
  it('the tracker panel is a tracking panel in the map host, ahead of the gateway pill [T631]', () => {
    expect(useTrackerUi).toBeTypeOf('function')
    expect(checkModules(MODULES)).toEqual([])
    expect(contributionProblems(MODULES)).toEqual([])
    expect(tracking.panels.map((p) => p.id)).toEqual(['tracker-panel'])
    const ids = collectPanels(MODULES, 'map').map((p) => p.id)
    expect(ids.indexOf('tracker-panel')).toBeGreaterThanOrEqual(0)
    expect(ids.indexOf('tracker-panel')).toBeLessThan(ids.indexOf('gateway-status'))
    expect(ids.indexOf('tracker-panel')).toBeLessThan(ids.indexOf('fire-map'))
  })

  it('fire contributes the report-at-position action of the tracker row [T631]', () => {
    const [action] = collectActions(MODULES, 'tracker-row')
    expect(action).toMatchObject({ id: 'fire-report-at-position', labelKey: 'fire.report.atPosition', testId: 'report-fire-row' })
    expect(fire.actions).toContain(action)
  })

  it('the fire action applies the 24 hour rule on the received time [T631]', () => {
    const [action] = collectActions(MODULES, 'tracker-row')
    const open = vi.spyOn(useFireUi(), 'openDialog').mockImplementation(() => {})
    const position = { latitude: 42.5, longitude: 24.5, mgrs: 'M', gnss_valid: true }
    const H24 = 24 * 3_600_000
    action.onSelect({ name: 'Ivan', position, ageMs: H24, receivedAt: 5 })
    expect(open.mock.calls[0][0].target).toMatchObject({ name: 'Ivan', latitude: 42.5, longitude: 24.5, mgrs: 'M', receivedAt: 5, gnssValid: true })
    action.onSelect({ name: 'Ivan', position, ageMs: H24 + 1, receivedAt: 5 })
    expect(open.mock.calls[1][0].target).toEqual({ name: 'Ivan', noPosition: true })
    action.onSelect({ name: 'Ivan', position: null, ageMs: null, receivedAt: null })
    expect(open.mock.calls[2][0].target).toEqual({ name: 'Ivan', noPosition: true })
  })
})
