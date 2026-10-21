import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../api', () => ({
  getSettings: vi.fn(), putSettings: vi.fn(), putHQ: vi.fn(), putHQInitial: vi.fn(), getMe: vi.fn(),
  getGroupsWithMembers: vi.fn(), getSerialStatus: vi.fn(),
  getFireHotspots: vi.fn(), getFireBurntAreas: vi.fn(),
  dismissFireHotspot: vi.fn(), createFieldReport: vi.fn(), extinguishFieldReport: vi.fn(),
  getSuppressionZones: vi.fn(), createSuppressionZone: vi.fn(),
}))

// Most tests only look at how connect() is called; the last one uses the real composable.
const ws = vi.hoisted(() => ({ connect: vi.fn(), real: false }))
vi.mock('../composables/useWebSocket', async (orig) => {
  const actual = await orig()
  return { useWebSocket: () => (ws.real ? actual.useWebSocket() : { connect: ws.connect }) }
})

const hooks = vi.hoisted(() => ({ hotspots: [], moveend: 0 }))
vi.mock('../composables/useMap', () => ({
  BASEMAPS: [],
  useMap: () => {
    const fakeMap = {
      addOverlay: vi.fn(), removeOverlay: vi.fn(), un: vi.fn(),
      on: (ev) => { if (ev === 'moveend') hooks.moveend++ },
      getView: () => ({ animate: vi.fn(), getCenter: () => [0, 0] }), updateSize: vi.fn(),
    }
    const own = {
      map: () => fakeMap,
      setHotspots: (fc) => { hooks.hotspots.push(fc); return true }, setBurntAreas: () => true,
    }
    return new Proxy(own, { get: (t, k) => (k in t ? t[k] : vi.fn()) })
  },
}))
vi.mock('ol/Overlay', () => ({ default: class { setPosition() {} } }))

import * as api from '../api'
import MapView from './MapView.vue'
import { useAuthStore } from '../stores/auth'
import { useFireStore } from '../stores/fire'
import { useLocationsStore } from '../stores/locations'
import { i18n } from '../i18n/index.js'

const SETTINGS = {
  hq_latitude: null, hq_longitude: null, is_hq_alarm_enabled: false, is_rescuer_alarm_enabled: true,
  hq_radius_m: 10000, rescuer_radius_m: 3000, alarm_max_age_hours: 24, repeat_minutes: 5, updated_at: 't0',
}
const HOTSPOTS = {
  type: 'FeatureCollection', fetched_at: new Date().toISOString(), upstream_state: 'ok',
  features: [{ type: 'Feature', id: 'h1', geometry: { type: 'Point', coordinates: [24.5, 42.5] },
    properties: { id: 'h1', source: 'viirs', state: 'active', acquired_at: new Date().toISOString() } }],
}
const down = () => Object.assign(new Error('connect ECONNREFUSED'), { code: 'ECONNREFUSED' })

let loc
async function mountMap({ liveFails = false, hotspotsOn = false } = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { role: 'admin' }
  loc = useLocationsStore()
  const snapshot = () => (liveFails ? vi.fn().mockRejectedValue(down()) : vi.fn(async () => {}))
  loc.fetchLive = snapshot(); loc.fetchSOS = snapshot(); loc.fetchTrail = snapshot()
  if (hotspotsOn) useFireStore().layers = { ...useFireStore().layers, hotspots: true }
  const w = mount(MapView, { attachTo: document.body, global: { plugins: [pinia, i18n], stubs: { SOSToast: true } } })
  await flushPromises()
  return w
}

describe('MapView: B66 start before the backend is up', () => {
  let tick
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    document.body.innerHTML = ''
    hooks.hotspots = []; hooks.moveend = 0
    ws.real = false
    i18n.global.locale.value = 'en'
    api.getSettings.mockResolvedValue({ ...SETTINGS })
    api.getGroupsWithMembers.mockResolvedValue({ items: [] })
    api.getSerialStatus.mockResolvedValue(null)
    api.getFireHotspots.mockResolvedValue(HOTSPOTS)
    api.getFireBurntAreas.mockResolvedValue({ type: 'FeatureCollection', features: [] })
    api.getSuppressionZones.mockResolvedValue([])
    tick = vi.spyOn(globalThis, 'setInterval')
  })
  afterEach(() => { tick.mockRestore(); vi.unstubAllGlobals() })

  const tickStarted = () => tick.mock.calls.some(c => c[1] === 10_000)

  it('connects the socket even when the first snapshot fetch fails [B66]', async () => {
    const w = await mountMap({ liveFails: true })
    expect(ws.connect).toHaveBeenCalledTimes(1)
    expect(ws.connect).toHaveBeenCalledWith({ catchUp: true })
    // the later mount steps all still ran
    expect(api.getGroupsWithMembers).toHaveBeenCalledTimes(1)
    expect(api.getSerialStatus).toHaveBeenCalledTimes(1)
    expect(hooks.moveend).toBe(1)
    expect(api.getSettings).toHaveBeenCalled()
    expect(tickStarted()).toBe(true)
    w.unmount()
  })

  it('a successful first snapshot connects without catch-up [B66]', async () => {
    const w = await mountMap()
    expect(ws.connect).toHaveBeenCalledTimes(1)
    expect(ws.connect).toHaveBeenCalledWith({ catchUp: false })
    w.unmount()
  })

  it('a failing groups fetch does not stop serial status, moveend, settings or the tick [B66]', async () => {
    api.getGroupsWithMembers.mockRejectedValue(down())
    const w = await mountMap()
    expect(ws.connect).toHaveBeenCalledTimes(1)
    expect(api.getSerialStatus).toHaveBeenCalledTimes(1)
    expect(hooks.moveend).toBe(1)
    expect(api.getSettings).toHaveBeenCalled()
    expect(tickStarted()).toBe(true)
    w.unmount()
  })

  it('a failing settings fetch still starts the tick [B66]', async () => {
    api.getSettings.mockRejectedValue(down())
    const w = await mountMap()
    expect(tickStarted()).toBe(true)
    w.unmount()
  })

  it('a hotspots layer remembered ON whose first fetch failed is drawn after the socket opens, no toggle [B66]', async () => {
    ws.real = true
    const sockets = []
    vi.stubGlobal('WebSocket', vi.fn(function () { sockets.push(this); this.close = vi.fn() }))
    api.getFireHotspots.mockRejectedValueOnce(down())
    const w = await mountMap({ liveFails: true, hotspotsOn: true })
    const fireStore = useFireStore()
    expect(fireStore.fetchFailed).toBe(true)
    expect(hooks.hotspots.filter(fc => fc?.features?.length)).toHaveLength(0)
    expect(sockets).toHaveLength(1)           // connect() ran although the first fetches failed

    sockets[0].onopen()                       // backend is up
    await flushPromises()
    expect(fireStore.fetchFailed).toBe(false)
    expect(hooks.hotspots.at(-1)?.features).toHaveLength(1)
    w.unmount()
  })
})
