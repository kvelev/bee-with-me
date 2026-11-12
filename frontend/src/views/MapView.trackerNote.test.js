import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../api', () => ({
  getSettings: vi.fn(), putSettings: vi.fn(), putHQ: vi.fn(), putHQInitial: vi.fn(), getMe: vi.fn(),
  getGroupsWithMembers: vi.fn(), getSerialStatus: vi.fn(),
  getDevices: vi.fn(async () => []), setDeviceLocation: vi.fn(),
  getLive: vi.fn(), getSOS: vi.fn(), getTrail: vi.fn(),
}))
vi.mock('../composables/useWebSocket', () => ({ useWebSocket: () => ({ connect: vi.fn() }) }))
// `result` is what the facade's refreshMarkers answers: false (the tracker layer failed) or true.
const tracker = vi.hoisted(() => ({ result: true, onCursor: null, onMeasure: null }))
vi.mock('../composables/useMap', () => ({
  BASEMAPS: [],
  useMap: (el, list, trails, onCursor, onMeasure) => new Proxy({
    // keep the callbacks so a test can show the readouts
    __capture: (tracker.onCursor = onCursor, tracker.onMeasure = onMeasure),
    map: () => null,
    refreshMarkers: () => tracker.result,
  }, {
    get: (t, k) => (k in t ? t[k] : vi.fn()),
  }),
}))
vi.mock('ol/Overlay', () => ({ default: class {} }))
vi.mock('ol/proj', () => ({ fromLonLat: (c) => c, toLonLat: (c) => c }))

import { getSettings, getGroupsWithMembers, getSerialStatus } from '../api'
import MapView from './MapView.vue'
import { useAuthStore } from '../stores/auth'
import { useLocationsStore } from '../stores/locations'
import { i18n } from '../i18n/index.js'
import en from '../i18n/en.js'
import bg from '../i18n/bg.js'

const SETTINGS = {
  hq_latitude: 42.5, hq_longitude: 24.5, is_hq_alarm_enabled: true, is_rescuer_alarm_enabled: true,
  hq_radius_m: 10000, rescuer_radius_m: 3000, alarm_max_age_hours: 24, repeat_minutes: 5, updated_at: 't0',
}

async function mountMap(wsConnected = true) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { role: 'admin' }
  const loc = useLocationsStore()
  loc.wsConnected = wsConnected
  loc.fetchLive = vi.fn(); loc.fetchSOS = vi.fn(); loc.fetchTrail = vi.fn()
  const w = mount(MapView, { global: { plugins: [pinia, i18n], stubs: { FirePopup: true } } })
  await flushPromises()
  return w
}
const note = (w, text) => w.findAll('[role="alert"]').find(e => e.text() === text)

describe('MapView tracker layer note', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getSettings.mockResolvedValue({ ...SETTINGS })
    getGroupsWithMembers.mockResolvedValue({ items: [] })
    getSerialStatus.mockResolvedValue(null)
  })

  it('the note is shown when refreshMarkers returns false [T632]', async () => {
    tracker.result = false
    const w = await mountMap()
    expect(en.map.trackerLayerFailed).toBeTruthy()
    expect(note(w, en.map.trackerLayerFailed)).toBeTruthy()
    i18n.global.locale.value = 'bg'
    await flushPromises()
    expect(bg.map.trackerLayerFailed).toBeTruthy()
    expect(note(w, bg.map.trackerLayerFailed)).toBeTruthy()
  })

  it('no note when refreshMarkers returns true [T632]', async () => {
    tracker.result = true
    const w = await mountMap()
    expect(en.map.trackerLayerFailed).toBeTruthy()
    expect(note(w, en.map.trackerLayerFailed)).toBeFalsy()
  })

  async function withReadouts(w) {
    await w.findAll('.bm-btn').find((b) => b.text() === en.map.latLon).trigger('click')
    tracker.onCursor({ mgrs: '35TNH1234', lat: 42.5, lon: 24.5 })
    tracker.onMeasure({ distKm: 1.5, bearing: 90 })
    await flushPromises()
  }

  it('with the note visible the coordinate and measure readouts sit below it, in order [B145]', async () => {
    tracker.result = false
    const w = await mountMap()
    await withReadouts(w)
    const n = w.get('.tracker-layer-note'), c = w.get('.mgrs-readout'), m = w.get('.measure-readout')
    expect(c.classes()).toContain('below-note')
    expect(m.classes()).toContain('below-note')
    expect(c.classes()).not.toContain('below-banner')
    const order = [...n.element.parentElement.children]
    expect(order.indexOf(n.element)).toBeLessThan(order.indexOf(c.element))
    expect(order.indexOf(c.element)).toBeLessThan(order.indexOf(m.element))
  })

  it('with the stale banner and the note both readouts also clear the banner [B145]', async () => {
    tracker.result = false
    const w = await mountMap(false)
    await withReadouts(w)
    expect(w.get('.tracker-layer-note').classes()).toContain('below-banner')
    expect(w.get('.mgrs-readout').classes()).toEqual(expect.arrayContaining(['below-note', 'below-banner']))
    expect(w.get('.measure-readout').classes()).toEqual(expect.arrayContaining(['below-note', 'below-banner']))
  })

  it('without the note nothing shifts [B145]', async () => {
    tracker.result = true
    const w = await mountMap(false)
    await withReadouts(w)
    expect(w.get('.mgrs-readout').classes()).not.toContain('below-note')
    expect(w.get('.mgrs-readout').classes()).not.toContain('below-banner')
    expect(w.get('.measure-readout').classes()).not.toContain('below-note')
    expect(w.get('.measure-readout').classes()).not.toContain('below-banner')
  })
})
