import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../api', () => ({
  getSettings: vi.fn(), putSettings: vi.fn(), putHQ: vi.fn(), putHQInitial: vi.fn(), getMe: vi.fn(),
  getGroupsWithMembers: vi.fn(), getSerialStatus: vi.fn(),
  getDevices: vi.fn(async () => []), setDeviceLocation: vi.fn(),
  getFireHotspots: vi.fn(), getFireBurntAreas: vi.fn(),
  dismissFireHotspot: vi.fn(), createFieldReport: vi.fn(), extinguishFieldReport: vi.fn(),
  getSuppressionZones: vi.fn(), createSuppressionZone: vi.fn(),
}))
vi.mock('../composables/useWebSocket', () => ({ useWebSocket: () => ({ connect: vi.fn() }) }))

// Same seam as MapView.fire.test.js: useMap is replaced, what the view registers on it is captured.
// Every mount gets its own fake map, so overlays can be counted per mount.
const hooks = vi.hoisted(() => ({ fireClick: null, contextMenu: null, maps: [] }))
vi.mock('../composables/useMap', () => ({
  BASEMAPS: [],
  useMap: () => {
    const fakeMap = {
      addOverlay: vi.fn(), removeOverlay: vi.fn(), on: vi.fn(), un: vi.fn(),
      getView: () => ({ animate: vi.fn(), getCenter: () => [0, 0] }), updateSize: vi.fn(),
    }
    hooks.maps.push(fakeMap)
    const own = {
      map: () => fakeMap,
      onFireFeatureClick: (cb) => { hooks.fireClick = cb },
      onMapContextMenu: (cb) => { hooks.contextMenu = cb },
      setHotspots: () => true, setBurntAreas: () => true,
    }
    return new Proxy(own, { get: (t, k) => (k in t ? t[k] : vi.fn()) })
  },
}))
vi.mock('ol/Overlay', () => ({ default: class { setPosition() {} } }))
vi.mock('ol/proj', () => ({ fromLonLat: (c) => c, toLonLat: (c) => c }))

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
const NOW = new Date().toISOString()

async function mountMap() {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { role: 'admin' }
  const loc = useLocationsStore()
  loc.fetchLive = vi.fn(); loc.fetchSOS = vi.fn(); loc.fetchTrail = vi.fn()
  loc.positions = {}
  const w = mount(MapView, { attachTo: document.body, global: { plugins: [pinia, i18n], stubs: { SOSToast: true } } })
  await flushPromises()
  return w
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  document.body.innerHTML = ''
  i18n.global.locale.value = 'en'
  hooks.fireClick = hooks.contextMenu = null
  hooks.maps.length = 0
  api.getSettings.mockResolvedValue({ ...SETTINGS })
  api.getGroupsWithMembers.mockResolvedValue({ items: [] })
  api.getSerialStatus.mockResolvedValue(null)
  api.getFireHotspots.mockResolvedValue({ type: 'FeatureCollection', features: [] })
  api.getFireBurntAreas.mockResolvedValue({ type: 'FeatureCollection', features: [] })
  api.getSuppressionZones.mockResolvedValue([])
})
afterEach(() => { vi.restoreAllMocks() })

describe('MapView: popup closes with its layer', () => {
  const openPopup = async (kind) => {
    hooks.fireClick({
      kind, coordinate: [24.5, 42.5],
      properties: { id: 'p1', source: 'viirs', state: 'active', acquired_at: NOW },
    })
    await flushPromises()
  }

  it('turning the hotspots layer off closes an open hotspot popup [T425]', async () => {
    const w = await mountMap()
    useFireStore().layers = { burnt: false, hotspots: true, zones: false }
    await openPopup('hotspot')
    expect(w.find('[data-action="create-zone"]').exists()).toBe(true)
    await w.get('[data-layer="hotspots"]').trigger('click')
    await flushPromises()
    expect(useFireStore().layers.hotspots).toBe(false)
    expect(w.find('[data-action="create-zone"]').exists()).toBe(false)
    w.unmount()
  })

  it('turning another layer off leaves the hotspot popup open [T425]', async () => {
    const w = await mountMap()
    useFireStore().layers = { burnt: true, hotspots: true, zones: false }
    await openPopup('hotspot')
    await w.get('[data-layer="burnt"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-action="create-zone"]').exists()).toBe(true)
    w.unmount()
  })
})

describe('MapView: returning to the map does not double the context menu', () => {
  const docCalls = (spy, type) => spy.mock.calls.filter((c) => c[0] === type && c[2] === true).length

  it('mount, open, unmount, mount again: listeners balance, one menu, nothing left on the old map [T425]', async () => {
    const add = vi.spyOn(document, 'addEventListener')
    const remove = vi.spyOn(document, 'removeEventListener')

    const first = await mountMap()
    hooks.contextMenu({ coordinate: [24.5, 42.5], pixel: [20, 20] })
    await flushPromises()
    expect(first.findAll('.map-context')).toHaveLength(1)
    first.unmount()
    expect(hooks.contextMenu).toBeNull()                       // the view released the map hook
    expect(document.querySelector('.map-context')).toBeNull()
    expect(docCalls(remove, 'pointerdown')).toBe(docCalls(add, 'pointerdown'))
    expect(docCalls(remove, 'keydown')).toBe(docCalls(add, 'keydown'))
    expect(hooks.maps[0].removeOverlay).toHaveBeenCalled()     // popup overlay left the first map

    const second = await mountMap()
    const addedBefore = docCalls(add, 'pointerdown')
    hooks.contextMenu({ coordinate: [24.5, 42.5], pixel: [20, 20] })
    await flushPromises()
    expect(second.findAll('.map-context')).toHaveLength(1)
    expect(document.querySelectorAll('.map-context')).toHaveLength(1)
    expect(docCalls(add, 'pointerdown') - addedBefore).toBe(1)
    // overlays: each map got its own popup and focus-ring overlay, never a second pair
    expect(hooks.maps[1].addOverlay).toHaveBeenCalledTimes(2)
    second.unmount()
    expect(docCalls(remove, 'pointerdown')).toBe(docCalls(add, 'pointerdown'))
    expect(docCalls(remove, 'keydown')).toBe(docCalls(add, 'keydown'))
  })
})
