import { describe, it, expect, vi, beforeEach } from 'vitest'
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

// The map itself is replaced; what the view hands to useMap and registers on it is captured.
const hooks = vi.hoisted(() => ({ fireClick: null, trackerClick: null, contextMenu: null, zones: null, layerVisible: [] }))
vi.mock('../composables/useMap', () => ({
  BASEMAPS: [],
  useMap: () => {
    const fakeMap = {
      addOverlay: vi.fn(), removeOverlay: vi.fn(), on: vi.fn(), un: vi.fn(),
      getView: () => ({ animate: vi.fn(), getCenter: () => [0, 0] }), updateSize: vi.fn(),
    }
    const own = {
      map: () => fakeMap,
      onFireFeatureClick: (cb) => { hooks.fireClick = cb },
      onTrackerClick: (cb) => { hooks.trackerClick = cb },
      onMapContextMenu: (cb) => { hooks.contextMenu = cb },
      setZones: (z) => { hooks.zones = z },
      setFireLayerVisible: (name, on) => { hooks.layerVisible.push([name, on]) },
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
import en from '../i18n/en.js'
import bg from '../i18n/bg.js'

const SETTINGS = {
  hq_latitude: null, hq_longitude: null, is_hq_alarm_enabled: false, is_rescuer_alarm_enabled: true,
  hq_radius_m: 10000, rescuer_radius_m: 3000, alarm_max_age_hours: 24, repeat_minutes: 5, updated_at: 't0',
}
const NOW = new Date().toISOString()
const IVAN = { device_id: 'dev-1', dev_sn: 1001, full_name: 'Ivan Petrov', mgrs: '35TLG1234567890', latitude: 42.5, longitude: 24.5, received_at: NOW, groups: [] }
const MARIA = { device_id: 'dev-2', dev_sn: 1002, full_name: 'Maria Georgieva', mgrs: '35TLG2222233333', latitude: 42.6, longitude: 24.6, received_at: NOW, groups: [] }


async function mountMap(role = 'admin', preset = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { role }
  Object.assign(useFireStore().layers, preset)
  const loc = useLocationsStore()
  loc.fetchLive = vi.fn(); loc.fetchSOS = vi.fn(); loc.fetchTrail = vi.fn()
  const w = mount(MapView, {
    attachTo: document.body,
    global: { plugins: [pinia, i18n] },
  })
  await flushPromises()
  return w
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  document.body.innerHTML = ''
  i18n.global.locale.value = 'en'
  hooks.layerVisible = []
  api.getSettings.mockResolvedValue({ ...SETTINGS })
  api.getGroupsWithMembers.mockResolvedValue({ items: [] })
  api.getSerialStatus.mockResolvedValue(null)
  api.getFireHotspots.mockResolvedValue({ type: 'FeatureCollection', features: [] })
  api.getFireBurntAreas.mockResolvedValue({ type: 'FeatureCollection', features: [] })
  api.getSuppressionZones.mockResolvedValue([])
})

const layersOf = (w) => w.findAll('[data-layer]').map((b) => b.attributes('data-layer'))

describe('MapView: layer toggle buttons', () => {
  it('an admin sees burnt, hotspots, zones in that order and a viewer does not see zones [T426]', async () => {
    const admin = await mountMap('admin')
    expect(layersOf(admin)).toEqual(['burnt', 'hotspots', 'zones'])
    admin.unmount()
    const viewer = await mountMap('viewer')
    expect(layersOf(viewer)).toEqual(['burnt', 'hotspots'])
  })

  it('a click toggles the store flag and tells the map [T426]', async () => {
    const w = await mountMap('admin')
    const fire = useFireStore()
    const before = !!fire.layers.hotspots
    hooks.layerVisible = []
    await w.get('[data-layer="hotspots"]').trigger('click')
    await flushPromises()
    expect(fire.layers.hotspots).toBe(!before)
    expect(hooks.layerVisible.at(-1)).toEqual(['hotspots', !before])
    expect(w.get('[data-layer="hotspots"]').attributes('aria-pressed')).toBe(String(!before))
    expect(w.get('[data-layer="hotspots"]').text()).toBe(en.fire.layers.hotspots)
  })

  it('layers remembered from the last session are shown on mount, zones only for an admin [T426]', async () => {
    const admin = await mountMap('admin', { burnt: true, hotspots: true, zones: true })
    expect(hooks.layerVisible).toEqual(expect.arrayContaining([['burnt', true], ['hotspots', true], ['zones', true]]))
    admin.unmount()
    hooks.layerVisible = []
    const viewer = await mountMap('viewer', { burnt: true, hotspots: false, zones: true })
    expect(hooks.layerVisible).toEqual(expect.arrayContaining([['burnt', true], ['hotspots', false], ['zones', false]]))
  })
})
