// Characterisation of the map's clicks, pointer moves, modes, long press and context menu (T422).
// Written against the unchanged useMap.js and kept unedited through the map-shell refactor: it is
// the proof that the shell changed no behaviour. jsdom renders no frame, so the hit tests
// (forEachFeatureAtPixel, hasFeatureAtPixel) and the pixel/coordinate conversions are replaced by
// stubs that answer from a list of hits the test chooses.
import { describe, it, expect, vi, afterEach } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import Feature from 'ol/Feature'
import Point from 'ol/geom/Point'
import { fromLonLat } from 'ol/proj'
import { useMap } from './useMap'

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} }

const Z_TRACKERS = 10
const Z_HOTSPOTS = 3.5
const Z_BURNT = 3
const Z_ZONES = 3.4
const Z_REPEATERS = 14
const Z_HQ = 15
const Z_MEASURE = 20

const COORD = fromLonLat([25.1, 42.6])
const COORD_B = fromLonLat([25.4, 42.9])
const PIXEL = [5, 5]
const MENU_COORD = [1000, 2000]

let mounted = []
afterEach(() => {
  mounted.forEach(w => w.unmount())
  mounted = []
  document.body.innerHTML = ''
  vi.useRealTimers()
  vi.restoreAllMocks()
})

// Mounts a throwaway component around useMap with a real target element (the cursor lives on it).
// `before(api)` runs inside setup, i.e. before the map exists.
function setup({ before } = {}) {
  const el = document.createElement('div')
  document.body.append(el)
  const spies = { cursor: vi.fn(), measure: vi.fn(), hq: vi.fn(), repeater: vi.fn(), fire: vi.fn(), tracker: vi.fn(), menu: vi.fn() }
  let api
  const Comp = defineComponent({
    setup() {
      api = useMap(ref(el), ref([]), ref({}), spies.cursor, spies.measure, ref({}), spies.hq)
      before?.(api)
      return () => h('div')
    },
  })
  const w = mount(Comp)
  mounted.push(w)
  const map = api.map()
  const layerAt = (z) => map.getLayers().getArray().find(l => l.getZIndex?.() === z)

  // What is "under the pointer": [{ z, feature }], answered through the layerFilter the code passes.
  let hits = []
  const under = (...list) => { hits = list }
  map.forEachFeatureAtPixel = (_pixel, cb, opts) => {
    for (const { z, feature } of hits) {
      const layer = layerAt(z)
      if (opts?.layerFilter && !opts.layerFilter(layer)) continue
      const r = cb(feature, layer)
      if (r) return r
    }
    return undefined
  }
  map.hasFeatureAtPixel = (_pixel, opts) => hits.some(({ z }) => !opts?.layerFilter || opts.layerFilter(layerAt(z)))
  map.getEventPixel = () => PIXEL
  map.getCoordinateFromPixel = () => MENU_COORD

  const click = (coordinate = COORD) => map.dispatchEvent({ type: 'click', pixel: PIXEL, coordinate, originalEvent: {} })
  const move = (coordinate = COORD) => map.dispatchEvent({ type: 'pointermove', pixel: PIXEL, coordinate, dragging: false, originalEvent: {} })
  const rightClick = () => {
    const e = new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 5, clientY: 5 })
    map.getViewport().dispatchEvent(e)
    return e
  }
  const touch = (type) => {
    const e = new Event(type, { bubbles: true })
    Object.assign(e, { pointerType: 'touch', isPrimary: true, clientX: 5, clientY: 5 })
    map.getViewport().dispatchEvent(e)
  }
  const tooltip = () => map.getOverlays().getArray()[0].getElement()
  const cursor = () => el.style.cursor
  const source = (z) => layerAt(z).getSource()

  return { api, map, el, spies, layerAt, source, under, click, move, rightClick, touch, tooltip, cursor }
}

const trackerFeature = () => {
  const f = new Feature({ geometry: new Point(COORD) })
  f.setId('dev-1')
  f.set('pos', { device_id: 'dev-1', full_name: 'Ana', latitude: 42.6, longitude: 25.1, received_at: new Date().toISOString(), groups: [] })
  return f
}
const hotspotFeature = () => {
  const f = new Feature({ geometry: new Point(COORD_B), source: 'viirs', confidence: 'high' })
  f.setId('h1')
  return f
}
const burntFeature = () => new Feature({ geometry: new Point(COORD_B), area_ha: 12 })

describe('useMap clicks and modes', () => {
  it('a click in HQ placement mode reports lat and lon and nothing else, even over a tracker [T422]', () => {
    const t = setup()
    t.api.onFireFeatureClick(t.spies.fire)
    t.api.onTrackerClick(t.spies.tracker)
    t.api.setHQPlacementMode(true)
    t.under({ z: Z_TRACKERS, feature: trackerFeature() })
    t.click(COORD)
    expect(t.spies.hq).toHaveBeenCalledTimes(1)
    const { lat, lon } = t.spies.hq.mock.calls[0][0]
    expect(lat).toBeCloseTo(42.6, 4)
    expect(lon).toBeCloseTo(25.1, 4)
    expect(t.spies.fire).not.toHaveBeenCalled()
    expect(t.spies.tracker).not.toHaveBeenCalled()
    expect(t.source(Z_MEASURE).getFeatures()).toHaveLength(0)
    expect(t.spies.repeater).not.toHaveBeenCalled()
  })

  it('repeater placement reports to onRepeaterPlaced [T422]', () => {
    const t = setup()
    t.api.onRepeaterPlaced(t.spies.repeater)
    t.api.setRepeaterPlacementMode(true)
    t.click(COORD)
    expect(t.spies.repeater).toHaveBeenCalledTimes(1)
    expect(t.spies.repeater.mock.calls[0][0].lat).toBeCloseTo(42.6, 4)
    expect(t.spies.hq).not.toHaveBeenCalled()
  })

  it('HQ placement wins when HQ and repeater placement are both on [T422]', () => {
    const t = setup()
    t.api.onRepeaterPlaced(t.spies.repeater)
    t.api.setRepeaterPlacementMode(true)
    t.api.setHQPlacementMode(true)
    t.click(COORD)
    expect(t.spies.hq).toHaveBeenCalledTimes(1)
    expect(t.spies.repeater).not.toHaveBeenCalled()
  })

  it('with HQ placement and measure both on a click places HQ, and after measure is switched off HQ placement still works [T422]', () => {
    const t = setup()
    t.api.setHQPlacementMode(true)
    t.api.setMeasureMode(true)
    t.click(COORD)
    expect(t.spies.hq).toHaveBeenCalledTimes(1)
    expect(t.source(Z_MEASURE).getFeatures()).toHaveLength(0)
    t.api.setMeasureMode(false)
    t.click(COORD_B)
    expect(t.spies.hq).toHaveBeenCalledTimes(2)
    expect(t.source(Z_MEASURE).getFeatures()).toHaveLength(0)
  })

  it('switching a placement or measure mode on and off sets the cursor values today\'s code sets [T422]', () => {
    const t = setup()
    for (const set of [t.api.setHQPlacementMode, t.api.setRepeaterPlacementMode, t.api.setMeasureMode]) {
      expect(t.cursor()).toBe('')
      set(true)
      expect(t.cursor()).toBe('crosshair')
      set(false)
      expect(t.cursor()).toBe('')
    }
    // HQ on, measure on, measure off: the cursor is empty although HQ placement is still on.
    t.api.setHQPlacementMode(true)
    expect(t.cursor()).toBe('crosshair')
    t.api.setMeasureMode(true)
    expect(t.cursor()).toBe('crosshair')
    t.api.setMeasureMode(false)
    expect(t.cursor()).toBe('')
    // ...and HQ placement is in force all the same.
    t.click(COORD)
    expect(t.spies.hq).toHaveBeenCalledTimes(1)
  })

  it('a placement mode switched on before mount is in force after mount and sets no cursor [T422]', () => {
    const t = setup({ before: (api) => { api.setHQPlacementMode(true); api.setBasemap('dark') } })
    expect(t.cursor()).toBe('')
    t.click(COORD)
    expect(t.spies.hq).toHaveBeenCalledTimes(1)
    // setBasemap before mount did nothing: the basemap is still the default OSM layer.
    expect(t.map.getLayers().getArray()[0].getSource().constructor.name).toBe('OSM')
  })

  it('measure mode adds A, then B and reports distance and bearing, and a third click starts again [T422]', () => {
    const t = setup()
    t.api.setMeasureMode(true)
    t.click(COORD)
    expect(t.source(Z_MEASURE).getFeatures()).toHaveLength(1)
    expect(t.spies.measure).not.toHaveBeenCalled()
    t.click(COORD_B)
    expect(t.source(Z_MEASURE).getFeatures()).toHaveLength(3)   // A, B and the line
    expect(t.spies.measure).toHaveBeenCalledTimes(1)
    const r = t.spies.measure.mock.calls[0][0]
    expect(r.distKm).toBeGreaterThan(30)
    expect(r.distKm).toBeLessThan(60)
    expect(r.bearing).toBeGreaterThan(0)
    expect(r.bearing).toBeLessThan(90)
    t.click(COORD)
    expect(t.spies.measure).toHaveBeenLastCalledWith(null)       // the old result is cleared
    expect(t.source(Z_MEASURE).getFeatures()).toHaveLength(1)    // a new A
    t.api.setMeasureMode(false)
    expect(t.source(Z_MEASURE).getFeatures()).toHaveLength(0)
    expect(t.spies.measure).toHaveBeenLastCalledWith(null)
  })

  it('a tracker hit calls the fire callback with null, then the tracker callback with the id [T422]', () => {
    const t = setup()
    const order = []
    t.api.onFireFeatureClick((v) => order.push(['fire', v]))
    t.api.onTrackerClick((v) => order.push(['tracker', v]))
    t.under({ z: Z_TRACKERS, feature: trackerFeature() })
    t.click()
    expect(order).toEqual([['fire', null], ['tracker', 'dev-1']])
  })

  it('a tracker click does nothing when no fire callback is registered [T422]', () => {
    const t = setup()
    t.api.onTrackerClick(t.spies.tracker)
    t.under({ z: Z_TRACKERS, feature: trackerFeature() })
    t.click()
    expect(t.spies.tracker).not.toHaveBeenCalled()
  })

  it('a hotspot hit reports kind, properties and the feature coordinate [T422]', () => {
    const t = setup()
    t.api.onFireFeatureClick(t.spies.fire)
    t.api.onTrackerClick(t.spies.tracker)
    t.under({ z: Z_HOTSPOTS, feature: hotspotFeature() })
    t.click(COORD)
    expect(t.spies.fire).toHaveBeenCalledTimes(1)
    expect(t.spies.fire).toHaveBeenCalledWith({
      kind: 'hotspot',
      properties: { source: 'viirs', confidence: 'high' },
      coordinate: COORD_B,
    })
    expect(t.spies.tracker).not.toHaveBeenCalled()
  })

  it('a burnt-area hit reports kind, properties and the clicked coordinate [T422]', () => {
    const t = setup()
    t.api.onFireFeatureClick(t.spies.fire)
    t.under({ z: Z_BURNT, feature: burntFeature() })
    t.click(COORD)
    expect(t.spies.fire).toHaveBeenCalledWith({ kind: 'burnt_area', properties: { area_ha: 12 }, coordinate: COORD })
  })

  it('a bare click calls both callbacks with null [T422]', () => {
    const t = setup()
    t.api.onFireFeatureClick(t.spies.fire)
    t.api.onTrackerClick(t.spies.tracker)
    t.click()
    expect(t.spies.fire).toHaveBeenCalledWith(null)
    expect(t.spies.tracker).toHaveBeenCalledWith(null)
  })

  it('no tracker or fire callback runs in a placement or measure mode [T422]', () => {
    for (const mode of ['setHQPlacementMode', 'setRepeaterPlacementMode', 'setMeasureMode']) {
      const t = setup()
      t.api.onFireFeatureClick(t.spies.fire)
      t.api.onTrackerClick(t.spies.tracker)
      t.api[mode](true)
      t.under({ z: Z_TRACKERS, feature: trackerFeature() })
      t.click()
      t.under({ z: Z_HOTSPOTS, feature: hotspotFeature() })
      t.click()
      t.under()
      t.click()
      expect(t.spies.fire).not.toHaveBeenCalled()
      expect(t.spies.tracker).not.toHaveBeenCalled()
    }
  })
})

describe('useMap pointer moves', () => {
  it('a hotspot under the pointer sets the pointer cursor and a bare move resets it [T422]', () => {
    const t = setup()
    t.under({ z: Z_HOTSPOTS, feature: hotspotFeature() })
    t.move()
    expect(t.cursor()).toBe('pointer')
    t.under()
    t.move()
    expect(t.cursor()).toBe('')
  })

  it('a burnt area under the pointer also sets the pointer cursor [T422]', () => {
    const t = setup()
    t.under({ z: Z_BURNT, feature: burntFeature() })
    t.move()
    expect(t.cursor()).toBe('pointer')
  })

  it('a hotspot under the pointer does not change the cursor in measure or placement mode [T422]', () => {
    for (const mode of ['setHQPlacementMode', 'setRepeaterPlacementMode', 'setMeasureMode']) {
      const t = setup()
      t.api[mode](true)
      t.under({ z: Z_HOTSPOTS, feature: hotspotFeature() })
      t.move()
      // Today's tooltip handler resets the cursor on every move without a tracker, in every mode,
      // and the fire cursor handler does not run in a mode: the result is empty, never "pointer".
      expect(t.cursor()).toBe('')
    }
  })

  it('a tracker under the pointer wins over a hotspot at the same pixel [T422]', () => {
    const t = setup()
    t.api.onFireFeatureClick(t.spies.fire)
    t.api.onTrackerClick(t.spies.tracker)
    t.under({ z: Z_TRACKERS, feature: trackerFeature() }, { z: Z_HOTSPOTS, feature: hotspotFeature() })
    t.move()
    expect(t.tooltip().style.display).toBe('block')
    expect(t.tooltip().textContent).toContain('Ana')
    expect(t.cursor()).toBe('pointer')
    t.click()
    expect(t.spies.tracker).toHaveBeenCalledWith('dev-1')
    expect(t.spies.fire).toHaveBeenCalledTimes(1)
    expect(t.spies.fire).toHaveBeenCalledWith(null)
  })

  it('the tooltip hides when the pointer leaves the tracker [T422]', () => {
    const t = setup()
    t.under({ z: Z_TRACKERS, feature: trackerFeature() })
    t.move()
    expect(t.tooltip().style.display).toBe('block')
    t.under()
    t.move()
    expect(t.tooltip().style.display).toBe('none')
  })

  it('the coordinate read-out callback runs on a pointer move in every mode [T422]', () => {
    for (const mode of [null, 'setHQPlacementMode', 'setRepeaterPlacementMode', 'setMeasureMode']) {
      const t = setup()
      if (mode) t.api[mode](true)
      t.move(COORD)
      expect(t.spies.cursor).toHaveBeenCalledTimes(1)
      const r = t.spies.cursor.mock.calls[0][0]
      expect(r.lat).toBeCloseTo(42.6, 4)
      expect(r.lon).toBeCloseTo(25.1, 4)
      expect(typeof r.mgrs).toBe('string')
      expect(r.mgrs.length).toBeGreaterThan(5)
    }
  })

  it('a drag move reaches no pointer handler [T422]', () => {
    const t = setup()
    t.under({ z: Z_HOTSPOTS, feature: hotspotFeature() })
    t.map.dispatchEvent({ type: 'pointermove', pixel: PIXEL, coordinate: COORD, dragging: true, originalEvent: {} })
    expect(t.spies.cursor).not.toHaveBeenCalled()
    expect(t.cursor()).toBe('')
  })
})

describe('useMap context menu and long press', () => {
  it('the browser context menu is always prevented, also in a mode [T422]', () => {
    const t = setup()
    expect(t.rightClick().defaultPrevented).toBe(true)
    t.api.setMeasureMode(true)
    expect(t.rightClick().defaultPrevented).toBe(true)
    t.api.setMeasureMode(false)
    t.api.setHQPlacementMode(true)
    expect(t.rightClick().defaultPrevented).toBe(true)
  })

  it('a right click reports coordinate and pixel once, a second within 800 ms is dropped, and none is reported in a mode [T422]', () => {
    vi.useFakeTimers()
    const t = setup()
    t.api.onMapContextMenu(t.spies.menu)
    t.rightClick()
    expect(t.spies.menu).toHaveBeenCalledTimes(1)
    expect(t.spies.menu).toHaveBeenCalledWith({ coordinate: MENU_COORD, pixel: PIXEL })
    vi.advanceTimersByTime(500)
    t.rightClick()
    expect(t.spies.menu).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(400)                 // 900 ms after the first
    t.rightClick()
    expect(t.spies.menu).toHaveBeenCalledTimes(2)

    // In a mode nothing is reported, but the attempt still starts the 800 ms window.
    vi.advanceTimersByTime(900)
    t.api.setMeasureMode(true)
    t.rightClick()
    expect(t.spies.menu).toHaveBeenCalledTimes(2)
    t.api.setMeasureMode(false)
    vi.advanceTimersByTime(300)
    t.rightClick()
    expect(t.spies.menu).toHaveBeenCalledTimes(2)
    vi.advanceTimersByTime(600)
    t.rightClick()
    expect(t.spies.menu).toHaveBeenCalledTimes(3)
  })

  it('a long press reports the menu once, and the click after it reaches nobody [T422]', () => {
    vi.useFakeTimers()
    const t = setup()
    t.api.onMapContextMenu(t.spies.menu)
    t.api.onFireFeatureClick(t.spies.fire)
    t.api.onTrackerClick(t.spies.tracker)
    t.touch('pointerdown')
    vi.advanceTimersByTime(599)
    expect(t.spies.menu).not.toHaveBeenCalled()
    vi.advanceTimersByTime(2)
    expect(t.spies.menu).toHaveBeenCalledTimes(1)
    t.touch('pointerup')
    t.click()                                    // the click the release raises
    expect(t.spies.fire).not.toHaveBeenCalled()
    expect(t.spies.tracker).not.toHaveBeenCalled()
    t.touch('pointerdown')                       // the next touch clears the swallow
    t.touch('pointerup')
    t.click()
    expect(t.spies.fire).toHaveBeenCalledWith(null)
  })

  it('a long press in a placement mode does not place anything with the swallowed click [T422]', () => {
    vi.useFakeTimers()
    const t = setup()
    t.api.onMapContextMenu(t.spies.menu)
    t.api.setHQPlacementMode(true)
    t.touch('pointerdown')
    vi.advanceTimersByTime(700)
    t.touch('pointerup')
    t.click()
    expect(t.spies.menu).not.toHaveBeenCalled()
    expect(t.spies.hq).not.toHaveBeenCalled()
  })
})

describe('useMap basemap and calls before mount', () => {
  it('switching the basemap keeps the basemap as the first layer and the other layers in place [T422]', () => {
    const t = setup()
    const before = t.map.getLayers().getArray().slice()
    t.api.setBasemap('satellite')
    const after = t.map.getLayers().getArray()
    expect(after).toHaveLength(before.length)
    expect(after[0]).not.toBe(before[0])
    expect(after.slice(1)).toEqual(before.slice(1))
    expect(after[0].getZIndex()).toBeUndefined()
  })

  it('setHotspots, setZones, setHQ and setRepeaters called before mount draw after mount [T422]', () => {
    let hotspotsOk
    let zoneCount
    const t = setup({
      before: (api) => {
        hotspotsOk = api.setHotspots({
          type: 'FeatureCollection',
          features: [{ type: 'Feature', id: 'h0', properties: { source: 'viirs' }, geometry: { type: 'Point', coordinates: [25, 42.5] } }],
        })
        zoneCount = api.setZones([{ id: 'z1', label: 'Z', latitude: 42.5, longitude: 25, radius_m: 500 }])
        api.setHQ({ lat: 42.5, lon: 25 }, 'HQ')
        api.setRepeaters([{ id: 7, name: 'R7', dev_sn: 7, site_latitude: 42.4, site_longitude: 25.2, is_active: true }])
      },
    })
    expect(hotspotsOk).toBe(true)
    expect(zoneCount).toBe(1)
    expect(t.source(Z_HOTSPOTS).getFeatures().map(f => f.getId())).toEqual(['h0'])
    expect(t.source(Z_ZONES).getFeatures().map(f => f.getId())).toEqual(['z1'])
    expect(t.source(Z_HQ).getFeatures().map(f => f.getId())).toEqual(['hq'])
    expect(t.source(Z_REPEATERS).getFeatures().map(f => f.getId())).toEqual(['repeater:7'])
  })

  it('the map has the eleven layers of today in today\'s z-order [T422]', () => {
    const t = setup()
    const zs = t.map.getLayers().getArray().map(l => l.getZIndex?.()).filter(z => z != null)
    expect(zs.slice().sort((a, b) => a - b)).toEqual([3, 3.4, 3.5, 4, 5, 6, 10, 14, 15, 20])
    expect(t.map.getLayers().getArray()).toHaveLength(11)
  })
})
