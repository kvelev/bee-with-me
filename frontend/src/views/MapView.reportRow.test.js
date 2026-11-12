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
import { useLocationsStore } from '../stores/locations'
import { i18n } from '../i18n/index.js'
import en from '../i18n/en.js'

// The form is an async chunk: load it once up front so one flush is enough under fake timers.
await import('../modules/fire/components/FieldReportForm.vue')

const SETTINGS = {
  hq_latitude: null, hq_longitude: null, is_hq_alarm_enabled: false, is_rescuer_alarm_enabled: true,
  hq_radius_m: 10000, rescuer_radius_m: 3000, alarm_max_age_hours: 24, repeat_minutes: 5, updated_at: 't0',
}

async function mountMap() {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { role: 'admin' }
  const loc = useLocationsStore()
  loc.fetchLive = vi.fn(); loc.fetchSOS = vi.fn(); loc.fetchTrail = vi.fn()
  loc.positions = {}
  const w = mount(MapView, { attachTo: document.body, global: { plugins: [pinia, i18n] } })
  await flushPromises()
  return w
}

// The report button of a tracker row: a position is reportable when it was RECEIVED (server clock) at most 24 h
// before the click. The limit itself is still reportable; recorded_at (device clock) plays no part.
describe('MapView: the report button of a tracker row follows the 24 h rule', () => {
  const T0 = Date.parse('2026-06-01T12:00:00.000Z')
  const H24 = 24 * 3_600_000

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
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(T0)
  })
  afterEach(() => { vi.useRealTimers() })

  const pos = (over = {}) => ({ device_id: 'dev-1', dev_sn: 1001, full_name: 'Ivan Petrov', mgrs: '35TLG1234567890', latitude: 42.5, longitude: 24.5, groups: [], ...over })
  const at = (msAgo) => new Date(T0 - msAgo).toISOString()

  async function openForm(position) {
    const w = await mountMap()
    useLocationsStore().positions = { 'dev-1': position }
    await flushPromises()
    await w.get('.tracker-row[data-device-id="dev-1"]').trigger('click')
    await w.get('[data-testid="report-fire-row"]').trigger('click')
    await flushPromises()
    return w
  }
  const reportable = (w) => w.find('[data-testid="fr-error"]').exists() === false && w.find('[data-testid="fr-mgrs"]').exists()

  it('a position received just under 24 h ago and exactly 24 h ago can be reported [T590]', async () => {
    for (const msAgo of [H24 - 1000, H24]) {
      const w = await openForm(pos({ received_at: at(msAgo) }))
      expect(reportable(w), `${msAgo} ms ago`).toBe(true)
      expect(w.get('[data-testid="fr-submit"]').attributes('disabled')).toBeUndefined()
      w.unmount()
      document.body.innerHTML = ''
    }
  })

  it('a position received just over 24 h ago cannot be reported and the form says so [T590]', async () => {
    const w = await openForm(pos({ received_at: at(H24 + 1000) }))
    expect(w.get('[data-testid="fr-error"]').text()).toBe(en.fire.errors.noRecentPosition)
    expect(w.get('[data-testid="fr-submit"]').attributes('disabled')).toBeDefined()
    expect(w.find('[data-testid="fr-mgrs"]').exists()).toBe(false)
    w.unmount()
  })

  it('the age is judged on received_at, not on recorded_at (device clock) [T590]', async () => {
    const stale = await openForm(pos({ received_at: at(H24 + 1000), recorded_at: at(1000) }))
    expect(stale.find('[data-testid="fr-error"]').exists()).toBe(true)
    stale.unmount()
    document.body.innerHTML = ''
    const fresh = await openForm(pos({ received_at: at(1000), recorded_at: at(H24 + 1000) }))
    expect(reportable(fresh)).toBe(true)
    fresh.unmount()
  })

  it('the age is taken at the click: a position that turns 24 h old before the click cannot be reported [T590]', async () => {
    const w = await mountMap()
    useLocationsStore().positions = { 'dev-1': pos({ received_at: at(H24 - 60_000) }) }
    await flushPromises()
    await w.get('.tracker-row[data-device-id="dev-1"]').trigger('click')
    vi.setSystemTime(T0 + 2 * 60_000)
    await w.get('[data-testid="report-fire-row"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="fr-error"]').text()).toBe(en.fire.errors.noRecentPosition)
    w.unmount()
  })
})
