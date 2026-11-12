import { describe, it, expect, vi, afterEach } from 'vitest'
import View from 'ol/View'
import { createMapShell } from '../../../platform/map-shell/createMapShell'
import { collectLayerToggles } from '../../../platform/map-shell/contributions'
import { MODULES } from '../../index'
import { MAP_MODULES } from '../../mapEntries'
import fireManifest from '../index'
import { FIRE_MAP_LAYERS } from './layers'
import fireMap from './index'
import listSource from './layers.js?raw'
import facadeSource from '../../../composables/useMap.js?raw'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

const PIXEL = [5, 5]
const COORD = [100, 200]

afterEach(() => {
  document.body.innerHTML = ''
  vi.useRealTimers()
  vi.restoreAllMocks()
})

const hotspotFC = (n) => ({
  type: 'FeatureCollection',
  features: Array.from({ length: n }, (_, i) => ({
    type: 'Feature', id: `h${i}`, properties: { source: 'viirs' },
    geometry: { type: 'Point', coordinates: [25 + i * 0.01, 42.5] },
  })),
})

// A shell as in useMap: created at set-up, the fire entry installed, mounted later.
function make({ ctx = {} } = {}) {
  const shell = createMapShell({
    view: new View({ center: [0, 0], zoom: 3 }),
    controls: [], overlays: [],
    createLongPress: () => ({ down() {}, move() {}, end() {}, shouldSwallowClick: () => false }),
    modes: ['hq-place', 'repeater-place', 'measure'],
  })
  const full = {
    trackerHit: () => false,
    reportTrackerClick: vi.fn(),
    fireClickRegistered: () => true,
    reportFireClick: vi.fn(),
    onHQPlaced: vi.fn(),
    ...ctx,
  }
  const api = shell.install(fireMap, FIRE_MAP_LAYERS, full)
  const mount = () => {
    const el = document.createElement('div')
    document.body.append(el)
    shell.mount(el)
    return el
  }
  const click = () => shell.map.dispatchEvent({ type: 'click', pixel: PIXEL, coordinate: COORD, originalEvent: {} })
  const move = () => shell.map.dispatchEvent({ type: 'pointermove', pixel: PIXEL, coordinate: COORD, dragging: false, originalEvent: {} })
  return { shell, api, ctx: full, mount, click, move }
}

describe('fire map layers', () => {
  it('the three fire layers are registered with z-index 3, 3.4 and 3.5 and start hidden [T423]', () => {
    const { shell } = make()
    expect(shell.layer('fire-burnt').getZIndex()).toBe(3)
    expect(shell.layer('fire-zones').getZIndex()).toBe(3.4)
    expect(shell.layer('fire-hotspots').getZIndex()).toBe(3.5)
    for (const id of ['fire-burnt', 'fire-zones', 'fire-hotspots']) expect(shell.layer(id).getVisible()).toBe(false)
  })

  it('the layers keep the order burnt, zones, hotspots on the map [T423]', () => {
    const { shell, mount } = make()
    mount()
    const layers = shell.map.getLayers().getArray()
    expect(layers.map((l) => l.getZIndex())).toEqual([3, 3.4, 3.5])
  })

  it('setHotspots before mount returns true and the features are on the layer after mount [T423]', () => {
    const { shell, api, mount } = make()
    expect(api.setHotspots(hotspotFC(2))).toBe(true)
    expect(api.setBurntAreas({ type: 'FeatureCollection', features: [] })).toBe(true)
    expect(api.setZones([{ id: 'z1', label: 'Z', latitude: 42.5, longitude: 25, radius_m: 500 }])).toBe(1)
    mount()
    expect(shell.layer('fire-hotspots').getSource().getFeatures()).toHaveLength(2)
    expect(shell.layer('fire-zones').getSource().getFeatures()).toHaveLength(1)
  })

  it('setHotspots keeps the previous features and returns false for unreadable GeoJSON [T423]', () => {
    const { shell, api } = make()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    expect(api.setHotspots(hotspotFC(3))).toBe(true)
    expect(api.setHotspots({ type: 'FeatureCollection', features: 'not-an-array' })).toBe(false)
    expect(shell.layer('fire-hotspots').getSource().getFeatures()).toHaveLength(3)
    expect(warn).toHaveBeenCalledWith('fire layer: unreadable %s GeoJSON, keeping previous features', 'hotspot')
  })

  it('setFireLayerVisible shows one layer by name [T423]', () => {
    const { shell, api } = make()
    api.setFireLayerVisible('hotspots', true)
    expect(shell.layer('fire-hotspots').getVisible()).toBe(true)
    expect(shell.layer('fire-burnt').getVisible()).toBe(false)
    expect(shell.layer('fire-zones').getVisible()).toBe(false)
    api.setFireLayerVisible('burnt', true)
    api.setFireLayerVisible('zones', true)
    api.setFireLayerVisible('hotspots', false)
    expect(shell.layer('fire-burnt').getVisible()).toBe(true)
    expect(shell.layer('fire-zones').getVisible()).toBe(true)
    expect(shell.layer('fire-hotspots').getVisible()).toBe(false)
  })

  it('setFireLabels repaints the hotspots [T423]', () => {
    const { shell, api } = make()
    const changed = vi.spyOn(shell.layer('fire-hotspots'), 'changed')
    api.setFireLabels({ fieldReport: 'Field report' })
    expect(changed).toHaveBeenCalledTimes(1)
  })

  it('the layer list carries the toggle of each button and imports no OpenLayers [T423]', () => {
    const toggles = collectLayerToggles([], FIRE_MAP_LAYERS)
    expect(toggles.map((t) => t.id)).toEqual(['fire-burnt', 'fire-hotspots', 'fire-zones'])
    expect(toggles.map((t) => t.labelKey)).toEqual(['fire.layers.burnt', 'fire.layers.hotspots', 'fire.layers.zones'])
    expect(toggles.filter((t) => t.adminOnly).map((t) => t.id)).toEqual(['fire-zones'])
    expect(listSource).not.toMatch(/from\s+['"]ol/)
  })

  it('dispose stops the repaint timer [T423]', () => {
    vi.useFakeTimers()
    const { shell, api, mount } = make()
    mount()
    const hotspots = shell.layer('fire-hotspots')
    const changed = vi.spyOn(hotspots, 'changed')
    api.setFireLayerVisible('hotspots', true)
    vi.advanceTimersByTime(60_000)
    expect(changed).toHaveBeenCalledTimes(1)
    shell.dispose()
    vi.advanceTimersByTime(180_000)
    expect(changed).toHaveBeenCalledTimes(1)
  })

  it('the repaint timer skips a hidden hotspot layer [T423]', () => {
    vi.useFakeTimers()
    const { shell, mount } = make()
    mount()
    const changed = vi.spyOn(shell.layer('fire-hotspots'), 'changed')
    vi.advanceTimersByTime(120_000)
    expect(changed).not.toHaveBeenCalled()
  })
})

describe('fire map click and cursor', () => {
  // jsdom renders no frame: report the feature of a chosen layer under the pixel.
  function hit(shell, layerId, feature) {
    shell.map.forEachFeatureAtPixel = (_p, cb, opts) => (opts?.layerFilter?.(shell.layer(layerId)) ? cb(feature) : undefined)
  }

  it('a click on a hotspot reports kind hotspot, its properties and its own coordinate [T423]', () => {
    const t = make()
    t.api.setHotspots(hotspotFC(1))
    t.mount()
    const feature = t.shell.layer('fire-hotspots').getSource().getFeatures()[0]
    hit(t.shell, 'fire-hotspots', feature)
    t.click()
    const sel = t.ctx.reportFireClick.mock.calls[0][0]
    expect(sel.kind).toBe('hotspot')
    expect(sel.properties.source).toBe('viirs')
    expect(sel.properties.geometry).toBeUndefined()
    expect(sel.coordinate).toEqual(feature.getGeometry().getCoordinates())
  })

  it('a click on a burnt area reports kind burnt_area at the click coordinate [T423]', () => {
    const t = make()
    t.api.setBurntAreas({
      type: 'FeatureCollection',
      features: [{ type: 'Feature', properties: { area_ha: 3 }, geometry: { type: 'Polygon', coordinates: [[[25, 42], [25.1, 42], [25.1, 42.1], [25, 42]]] } }],
    })
    t.mount()
    hit(t.shell, 'fire-burnt', t.shell.layer('fire-burnt').getSource().getFeatures()[0])
    t.click()
    const sel = t.ctx.reportFireClick.mock.calls[0][0]
    expect(sel.kind).toBe('burnt_area')
    expect(sel.coordinate).toEqual(COORD)
  })

  it('a click on bare map reports null to the fire and the tracker callbacks [T423]', () => {
    const t = make()
    t.mount()
    t.click()
    expect(t.ctx.reportFireClick).toHaveBeenCalledWith(null)
    expect(t.ctx.reportTrackerClick).toHaveBeenCalledWith(null)
  })

  it('a click does nothing when no fire callback is registered [T423]', () => {
    const t = make({ ctx: { fireClickRegistered: () => false } })
    t.mount()
    t.click()
    expect(t.ctx.reportFireClick).not.toHaveBeenCalled()
    expect(t.ctx.reportTrackerClick).not.toHaveBeenCalled()
  })

  it('a tracker under the pointer keeps the cursor off the fire layers [T423]', () => {
    const t = make({ ctx: { trackerHit: () => true } })
    t.mount()
    const el = t.shell.map.getTargetElement()
    t.shell.map.forEachFeatureAtPixel = () => ({})
    t.move()
    expect(el.style.cursor).toBe('')
  })

  it('a fire feature under the pointer sets the pointer cursor [T423]', () => {
    const t = make()
    t.api.setHotspots(hotspotFC(1))
    t.mount()
    hit(t.shell, 'fire-hotspots', t.shell.layer('fire-hotspots').getSource().getFeatures()[0])
    t.move()
    expect(t.shell.map.getTargetElement().style.cursor).toBe('pointer')
  })

  it('a fire handler that throws is logged and does not stop the click [T423]', () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const t = make({ ctx: { reportFireClick: () => { throw new Error('boom') } } })
    t.mount()
    expect(() => t.click()).not.toThrow()
    expect(err).toHaveBeenCalled()
  })
})

describe('fire map install failure', () => {
  it('an entry whose setup throws gives an empty api, so the facade falls back [T423]', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const shell = createMapShell({ view: new View({ center: [0, 0], zoom: 3 }), createLongPress: () => ({ down() {}, move() {}, end() {}, shouldSwallowClick: () => false }), modes: [] })
    const api = shell.install({ ...fireMap, setup: () => { throw new Error('x') } }, FIRE_MAP_LAYERS, {})
    expect(api).toEqual({})
  })
})

describe('the fire map entry belongs to the fire module', () => {
  it('the fire manifest declares the three layers and the entry has a factory for each [T506]', () => {
    expect(fireManifest.mapLayers.map((l) => l.id)).toEqual(['fire-burnt', 'fire-zones', 'fire-hotspots'])
    expect(fireManifest.mapLayers).toBe(FIRE_MAP_LAYERS)
    expect(Object.keys(fireMap.layers)).toEqual(fireManifest.mapLayers.map((l) => l.id))
    expect(fireMap.name).toBe('fire')
    expect(typeof fireMap.setup).toBe('function')
  })

  it('the facade has no fire install of its own [T506]', () => {
    expect(facadeSource).not.toMatch(/fireLayers/)
    expect(facadeSource).not.toMatch(/fireLayerList/)
  })

  it('MAP_MODULES lists fire, settings and tracking [T506]', () => {
    expect(MAP_MODULES.map((e) => e.name)).toEqual(['fire', 'settings', 'tracking'])
    expect(MAP_MODULES[0]).toBe(fireMap)
  })

  it('the fire toggles come from the manifest alone [T506]', () => {
    expect(collectLayerToggles(MODULES).map((t) => t.id)).toEqual(['fire-burnt', 'fire-hotspots', 'fire-zones'])
  })
})
