// The tracking module's map entry: tracker, trail and checkpoint layers (T632). A shell as in
// settings/map/hqLayer.test.js; jsdom renders no frame, so the hit test is a stub the test controls.
import { describe, it, expect, vi, afterEach } from 'vitest'
import View from 'ol/View'
import { createMapShell } from '../../../platform/map-shell/createMapShell'
import { collectMapLayers } from '../../../platform/map-shell/contributions'
import { validateManifest } from '../../../platform/manifest.js'
import { Z } from '../../../platform/map-shell/zorder.js'
import tracking from '../index.js'
import trackingMap from './index.js'
import { TRACKING_MAP_LAYERS } from './layers.js'
import manifestSource from '../index.js?raw'
import layersSource from './layers.js?raw'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

afterEach(() => {
  document.body.innerHTML = ''
  vi.useRealTimers()
  vi.restoreAllMocks()
})

const NOW = () => new Date().toISOString()
const pos = (over = {}) => ({
  device_id: 'd1', dev_sn: 1, latitude: 42.5, longitude: 25, full_name: 'Ivan',
  received_at: NOW(), recorded_at: NOW(), groups: [], ...over,
})

function make(entry = trackingMap) {
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
  const api = shell.install(entry, tracking.mapLayers, ctx)
  const mount = () => {
    const el = document.createElement('div')
    document.body.append(el)
    shell.mount(el)
    return el
  }
  return { shell, api, ctx, mount }
}

const failing = () => ({ ...trackingMap, setup: () => { throw new Error('boom') } })

describe('tracking module: map entry', () => {
  it('the three layers are registered with the z-indices of the z-order table [T632]', () => {
    expect(collectMapLayers([tracking]).map((l) => [l.id, l.zIndex])).toEqual([
      ['tracking-trail', Z.trail], ['tracking-checkpoints', Z.checkpoints], ['tracking-trackers', Z.trackers],
    ])
    expect(TRACKING_MAP_LAYERS).toHaveLength(3)
    expect(Object.keys(trackingMap.layers).sort()).toEqual(TRACKING_MAP_LAYERS.map((l) => l.id).sort())
    expect(validateManifest(tracking)).toEqual([])
    expect(manifestSource).not.toMatch(/from\s+['"]ol/)
    expect(layersSource).not.toMatch(/from\s+['"]ol/)
    const { shell } = make()
    for (const l of TRACKING_MAP_LAYERS) expect(shell.layer(l.id).getZIndex()).toBe(l.zIndex)
  })

  it('positions set before mount are drawn after mount [T632]', () => {
    const { shell, api, mount } = make()
    api.setPositions([pos(), pos({ device_id: 'd2' })])
    mount()
    expect(shell.layer('tracking-trackers').getSource().getFeatures()).toHaveLength(2)
    api.setPositions([pos()])
    expect(shell.layer('tracking-trackers').getSource().getFeatures()).toHaveLength(1)
  })

  it('a position that goes stale is restyled by the timer without a new message [T632]', () => {
    vi.useFakeTimers()
    const t0 = new Date('2026-11-12T10:00:00Z')
    vi.setSystemTime(t0)
    const { shell, api, mount } = make()
    api.setPositions([pos({ received_at: t0.toISOString(), recorded_at: t0.toISOString() })])
    mount()
    const feature = shell.layer('tracking-trackers').getSource().getFeatureById('d1')
    const before = feature.getStyle()
    vi.setSystemTime(new Date(t0.getTime() + 20 * 60_000))
    vi.advanceTimersByTime(60_000)
    expect(feature.getStyle()).not.toBe(before)
    expect(feature.getStyle().getImage().getFill().getColor()).toMatch(/^rgba\(156,163,175/)
  })

  it('dispose stops the timer and removes the tooltip overlay [T632]', () => {
    const set = vi.spyOn(globalThis, 'setInterval')
    const clear = vi.spyOn(globalThis, 'clearInterval')
    const { shell, mount } = make()
    mount()
    expect(shell.map.getOverlays().getLength()).toBe(1)
    expect(set).toHaveBeenCalledTimes(1)
    expect(set.mock.calls[0][1]).toBe(60_000)
    const map = shell.map
    shell.dispose()
    expect(clear).toHaveBeenCalledWith(set.mock.results[0].value)
    expect(map.getOverlays().getLength()).toBe(0)
  })

  it('a tracker under the pointer shows the tooltip in every mode [T632]', () => {
    const { shell, api, mount } = make()
    api.setPositions([pos()])
    mount()
    const map = shell.map
    const layer = shell.layer('tracking-trackers')
    const feature = layer.getSource().getFeatureById('d1')
    map.forEachFeatureAtPixel = (_p, cb, opts) => (opts?.layerFilter?.(layer) ? cb(feature, layer) : undefined)
    const tip = map.getOverlays().getArray()[0].getElement()
    const move = () => map.dispatchEvent({ type: 'pointermove', pixel: [5, 5], coordinate: [10, 10], dragging: false, originalEvent: {} })
    for (const mode of [null, 'measure', 'hq-place', 'repeater-place']) {
      if (mode) shell.setMode(mode, true)
      tip.style.display = 'none'
      move()
      expect(tip.style.display, `mode ${mode}`).toBe('block')
      if (mode) shell.setMode(mode, false)
    }
    map.forEachFeatureAtPixel = () => undefined
    move()
    expect(tip.style.display).toBe('none')
  })

  it('a failed install makes refreshMarkers return false [T632]', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const { api } = make(failing())
    expect(api.refreshMarkers).toBeUndefined()
  })

  it('a failed install leaves no timer behind [T632]', () => {
    const set = vi.spyOn(globalThis, 'setInterval')
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const { shell, mount } = make(failing())
    mount()
    shell.dispose()
    expect(set).not.toHaveBeenCalled()
  })

  it('a setup that fails after its timer hook was registered starts no timer [T632]', () => {
    const set = vi.spyOn(globalThis, 'setInterval')
    vi.spyOn(console, 'error').mockImplementation(() => {})
    const late = { ...trackingMap, setup: (shell, ctx) => {
      const original = shell.onMounted
      shell.onMounted = (fn) => { original(fn); throw new Error('late') }   // the hook is registered, then the setup fails
      try { return trackingMap.setup(shell, ctx) } finally { shell.onMounted = original }
    } }
    const { shell, mount } = make(late)
    mount()
    shell.dispose()
    expect(set).not.toHaveBeenCalled()
  })

  it('trails and checkpoints are drawn, hidden until switched on [T632]', () => {
    const { shell, api, mount } = make()
    api.setPositions([pos()])
    mount()
    api.setTrails({ d1: [{ lat: 42.5, lon: 25 }, { lat: 42.6, lon: 25.1 }] })
    expect(shell.layer('tracking-trail').getSource().getFeatures()).toHaveLength(1)
    expect(shell.layer('tracking-checkpoints').getSource().getFeatures()).toHaveLength(2)
    expect(shell.layer('tracking-trail').getVisible()).toBe(false)
    api.setTrailVisible(true)
    expect(shell.layer('tracking-trail').getVisible()).toBe(true)
    expect(shell.layer('tracking-checkpoints').getVisible()).toBe(true)
    api.setTrails({})
    expect(shell.layer('tracking-trail').getSource().getFeatures()).toHaveLength(0)
    expect(shell.layer('tracking-checkpoints').getSource().getFeatures()).toHaveLength(0)
  })

  it('a click on a tracker reports its id and clears the fire popup [T632]', () => {
    const { shell, api, ctx, mount } = make()
    ctx.fireClickRegistered = () => true
    api.setPositions([pos()])
    mount()
    const layer = shell.layer('tracking-trackers')
    const feature = layer.getSource().getFeatureById('d1')
    shell.map.hasFeatureAtPixel = (_p, o) => !!o.layerFilter(layer)
    shell.map.forEachFeatureAtPixel = (_p, cb, o) => (o.layerFilter(layer) ? cb(feature, layer) : undefined)
    shell.map.dispatchEvent({ type: 'click', pixel: [5, 5], coordinate: [1, 1], originalEvent: {} })
    expect(ctx.reportFireClick).toHaveBeenCalledWith(null)
    expect(ctx.reportTrackerClick).toHaveBeenCalledWith('d1')
  })
})
