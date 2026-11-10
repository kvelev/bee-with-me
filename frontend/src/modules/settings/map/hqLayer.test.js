import { describe, it, expect, vi, afterEach } from 'vitest'
import View from 'ol/View'
import { createMapShell } from '../../../platform/map-shell/createMapShell'
import { collectMapLayers } from '../../../platform/map-shell/contributions'
import { validateManifest } from '../../../platform/manifest.js'
import settings from '../index.js'
import settingsMap from './index.js'
import { HQ_LAYER } from './layers.js'
import { MAP_MODULES } from '../../mapEntries.js'
import { MODULES } from '../../index.js'
import manifestSource from '../index.js?raw'
import layersSource from './layers.js?raw'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

const PIXEL = [5, 5]
const COORD = [2800000, 5200000]

afterEach(() => {
  document.body.innerHTML = ''
  vi.restoreAllMocks()
})

// A shell as in useMap: created at set-up, the settings entry installed, mounted later.
function make() {
  const shell = createMapShell({
    view: new View({ center: [0, 0], zoom: 3 }),
    controls: [], overlays: [],
    createLongPress: () => ({ down() {}, move() {}, end() {}, shouldSwallowClick: () => false }),
    modes: ['hq-place', 'repeater-place', 'measure'],
  })
  const ctx = {
    trackerHit: () => false,
    reportTrackerClick: vi.fn(),
    fireClickRegistered: () => false,
    reportFireClick: vi.fn(),
    onHQPlaced: vi.fn(),
  }
  const api = shell.install(settingsMap, settings.mapLayers, ctx)
  const mount = () => {
    const el = document.createElement('div')
    document.body.append(el)
    shell.mount(el)
    return el
  }
  const click = () => shell.map.dispatchEvent({ type: 'click', pixel: PIXEL, coordinate: COORD, originalEvent: {} })
  return { shell, api, ctx, mount, click }
}

describe('settings module: HQ map layer', () => {
  it('the settings manifest declares one layer at z-index 15 and imports no OpenLayers [T427]', () => {
    const layers = collectMapLayers([settings])
    expect(layers.map((l) => l.id)).toEqual(['settings-hq'])
    expect(HQ_LAYER.zIndex).toBe(15)
    expect(validateManifest(settings)).toEqual([])
    expect(manifestSource).not.toMatch(/from\s+['"]ol/)
    expect(layersSource).not.toMatch(/from\s+['"]ol/)
  })

  it('every declared layer has a factory and the reverse [T427]', () => {
    expect(MAP_MODULES.length).toBeGreaterThan(0)
    for (const entry of MAP_MODULES) {
      const manifest = MODULES.find((m) => m.name === entry.name)
      expect(manifest, `manifest ${entry.name}`).toBeTruthy()
      expect(Object.keys(entry.layers).sort()).toEqual(manifest.mapLayers.map((l) => l.id).sort())
    }
  })

  it('setHQ before mount draws one feature after mount and null clears it [T427]', () => {
    const { shell, api, mount } = make()
    api.setHQ({ lat: 42.5, lon: 25 }, 'Base')
    mount()
    const source = shell.layer('settings-hq').getSource()
    expect(source.getFeatures()).toHaveLength(1)
    api.setHQ({ lat: 42.6, lon: 25.1 })
    expect(source.getFeatures()).toHaveLength(1)
    expect(source.getFeatures()[0].getStyle().getText().getText()).toBe('Base')   // the label is kept
    api.setHQ(null)
    expect(source.getFeatures()).toHaveLength(0)
  })

  it('the default label is ЩАБ [T427]', () => {
    const { shell, api } = make()
    api.setHQ({ lat: 42.5, lon: 25 })
    expect(shell.layer('settings-hq').getSource().getFeatures()[0].getStyle().getText().getText()).toBe('ЩАБ')
  })

  it('a click in placement mode reports lat and lon and nothing else handles it [T427]', () => {
    const { shell, api, ctx, mount, click } = make()
    mount()
    const normal = vi.fn()
    shell.onClick(normal)
    api.setHQPlacementMode(true)
    click()
    expect(ctx.onHQPlaced).toHaveBeenCalledTimes(1)
    const arg = ctx.onHQPlaced.mock.calls[0][0]
    expect(Object.keys(arg).sort()).toEqual(['lat', 'lon'])
    expect(normal).not.toHaveBeenCalled()
  })

  it('leaving placement mode restores normal clicks [T427]', () => {
    const { shell, api, ctx, mount, click } = make()
    mount()
    const normal = vi.fn()
    shell.onClick(normal)
    api.setHQPlacementMode(true)
    api.setHQPlacementMode(false)
    click()
    expect(ctx.onHQPlaced).not.toHaveBeenCalled()
    expect(normal).toHaveBeenCalledTimes(1)
  })
})
