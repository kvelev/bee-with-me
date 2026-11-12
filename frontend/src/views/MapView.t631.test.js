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

const hooks = vi.hoisted(() => ({ refresh: null, passed: null }))
vi.mock('../composables/useMap', () => ({
  BASEMAPS: [],
  useMap: (...args) => {
    hooks.passed = args
    const fakeMap = {
      addOverlay: vi.fn(), removeOverlay: vi.fn(), on: vi.fn(), un: vi.fn(),
      getView: () => ({ animate: vi.fn(), getCenter: () => [0, 0] }), updateSize: vi.fn(),
    }
    hooks.refresh = vi.fn(() => true)
    const own = { map: () => fakeMap, refreshMarkers: hooks.refresh, setHotspots: () => true, setBurntAreas: () => true }
    return new Proxy(own, { get: (t, k) => (k in t ? t[k] : vi.fn()) })
  },
}))
vi.mock('ol/Overlay', () => ({ default: class { setPosition() {} } }))
vi.mock('ol/proj', () => ({ fromLonLat: (c) => c, toLonLat: (c) => c }))

import * as api from '../api'
import MapView from './MapView.vue'
import { useAuthStore } from '../stores/auth'
import { useLocationsStore } from '../stores/locations'
import { useTrackerUi } from '../modules/tracking/index.js'
import { i18n } from '../i18n/index.js'

const SETTINGS = {
  hq_latitude: null, hq_longitude: null, is_hq_alarm_enabled: false, is_rescuer_alarm_enabled: true,
  hq_radius_m: 10000, rescuer_radius_m: 3000, alarm_max_age_hours: 24, repeat_minutes: 5, updated_at: 't0',
}
const IVAN = { device_id: 'dev-1', dev_sn: 1001, full_name: 'Ivan Petrov', mgrs: '35TLG1234567890', latitude: 42.5, longitude: 24.5, received_at: new Date().toISOString(), groups: [] }

// Two rows: with one there is nothing to sort, so the list would not read the clock.
const MARIA = { ...IVAN, device_id: 'dev-2', dev_sn: 1002, full_name: 'Maria Georgieva' }

async function mountMap(pinia = createPinia()) {
  setActivePinia(pinia)
  useAuthStore().user = { role: 'admin' }
  const loc = useLocationsStore()
  loc.fetchLive = vi.fn(); loc.fetchSOS = vi.fn(); loc.fetchTrail = vi.fn()
  loc.positions = { [IVAN.device_id]: IVAN, [MARIA.device_id]: MARIA }
  const w = mount(MapView, { attachTo: document.body, global: { plugins: [pinia, i18n] } })
  await flushPromises()
  return w
}

describe('MapView owns the tracker tick and state', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    document.body.innerHTML = ''
    i18n.global.locale.value = 'en'
    api.getSettings.mockResolvedValue({ ...SETTINGS })
    api.getGroupsWithMembers.mockResolvedValue({ items: [] })
    api.getSerialStatus.mockResolvedValue(null)
    api.getFireHotspots.mockResolvedValue({ type: 'FeatureCollection', features: [] })
    api.getFireBurntAreas.mockResolvedValue({ type: 'FeatureCollection', features: [] })
    api.getSuppressionZones.mockResolvedValue([])
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'Date'] })
  })
  afterEach(() => { vi.useRealTimers() })

  it('the view starts the tick on mount, clears it on unmount and resets the tracker state on mount [T631]', async () => {
    // State left by an earlier visit of the map in the same pinia is put back on mount.
    const pinia = createPinia()
    setActivePinia(pinia)
    const earlier = useTrackerUi()
    earlier.viewMode = 'groups'
    earlier.rankFilter = 'x'
    const w = await mountMap(pinia)
    const ui = useTrackerUi()
    expect(ui.viewMode).toBe('individuals')
    expect(ui.rankFilter).toBe('')
    const before = ui.nowTick
    vi.advanceTimersByTime(10_000)
    expect(ui.nowTick).toBeGreaterThan(before)
    w.unmount()
    const after = ui.nowTick
    vi.advanceTimersByTime(30_000)
    expect(ui.nowTick).toBe(after)
  })

  it('the markers are refreshed on a tick [T631]', async () => {
    const w = await mountMap()
    hooks.refresh.mockClear()
    await vi.advanceTimersByTimeAsync(10_000)
    expect(hooks.refresh).toHaveBeenCalled()
    w.unmount()
  })

  it('useMap gets the displayList ref of the store, not an array [T631]', async () => {
    const w = await mountMap()
    const list = hooks.passed[1]
    expect(Array.isArray(list)).toBe(false)
    expect(list.value.map((p) => p.device_id)).toEqual(['dev-1', 'dev-2'])
    w.unmount()
  })
})
