// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { validateManifest } from './manifest.js'

const base = (toggle) => ({
  name: 'demo', routes: [], nav: [], panels: [], banners: [], liveHandlers: {}, depends: [],
  i18n: { en: {}, bg: {} },
  mapLayers: [{ id: 'l', zIndex: 3, toggle }],
})

describe('live field', () => {
  const withLive = (live) => ({ ...base(undefined), live })
  it('validateManifest accepts a live field and names a malformed one [T543]', () => {
    expect(validateManifest(withLive({ setup: () => {}, onTick: () => {}, onReconnect: () => {} }))).toEqual([])
    expect(validateManifest(withLive(undefined))).toEqual([])
    expect(validateManifest(withLive({ onTick: 1 })).join('\n')).toContain('live.onTick: must be a function')
    expect(validateManifest(withLive({ later: () => {} })).join('\n')).toContain('live.later: unknown hook')
    expect(validateManifest(withLive([])).join('\n')).toContain('live: must be an object')
  })
})

describe('toggle.adminOnly', () => {
  it('accepts true, false and absent [T421]', () => {
    expect(validateManifest(base({ labelKey: 'k', order: 1, adminOnly: true }))).toEqual([])
    expect(validateManifest(base({ labelKey: 'k', order: 1, adminOnly: false }))).toEqual([])
    expect(validateManifest(base({ labelKey: 'k', order: 1 }))).toEqual([])
  })
  it('names the field when it is not a boolean [T421]', () => {
    const msg = validateManifest(base({ labelKey: 'k', order: 1, adminOnly: 'yes' })).join('\n')
    expect(msg).toContain('toggle.adminOnly must be a boolean')
  })
})

describe('panels and the toggle state hook', () => {
  const withPanel = (panel) => ({ ...base(undefined), panels: [panel] })
  const C = { render: () => null }

  it('validateManifest accepts host, order and the toggle pair and names each malformed one [T504]', () => {
    expect(validateManifest(withPanel({ id: 'p', component: C, host: 'map', order: 3 }))).toEqual([])
    expect(validateManifest(withPanel({ id: 'p', component: C }))).toEqual([])
    expect(validateManifest(withPanel({ id: 'p', component: C, retryKey: () => 1 }))).toEqual([])
    expect(validateManifest(withPanel({ id: 'p', component: C, host: 'nowhere' })).join('\n')).toContain('host must be one of')
    expect(validateManifest(withPanel({ id: 'p', component: C, order: '1' })).join('\n')).toContain('order must be a finite number')
    expect(validateManifest(withPanel({ id: 'p', component: C, retryKey: 'x' })).join('\n')).toContain('retryKey must be a function')

    const t = { labelKey: 'k', order: 1 }
    expect(validateManifest(base({ ...t, key: 'fire-burnt', isOn: () => true, set: () => {} }))).toEqual([])
    expect(validateManifest(base({ ...t, isOn: () => true })).join('\n')).toContain('toggle.isOn and toggle.set must be given together')
    expect(validateManifest(base({ ...t, set: () => {} })).join('\n')).toContain('toggle.isOn and toggle.set must be given together')
    expect(validateManifest(base({ ...t, isOn: 1, set: () => {} })).join('\n')).toContain('toggle.isOn must be a function')
    expect(validateManifest(base({ ...t, key: 5 })).join('\n')).toContain('toggle.key must be a non-empty string')
  })
})
