import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { ApiError } from '../api/client'

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
// ol/proj is NOT mocked here: the context-menu coordinate is EPSG:3857 metres, as on the real map.

import * as api from '../api'
import MapView from './MapView.vue'
import { useAuthStore } from '../stores/auth'
import { useFireStore } from '../stores/fire'
import { useLocationsStore } from '../stores/locations'
import { fromLonLat } from 'ol/proj'
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

const feature = (id, props = {}) => ({
  type: 'Feature', id, geometry: { type: 'Point', coordinates: [24.5, 42.5] },
  properties: { id, source: 'viirs', state: 'active', acquired_at: NOW, ...props },
})

async function mountMap(role = 'admin') {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { role }
  const loc = useLocationsStore()
  loc.fetchLive = vi.fn(); loc.fetchSOS = vi.fn(); loc.fetchTrail = vi.fn()
  loc.positions = { [IVAN.device_id]: IVAN, [MARIA.device_id]: MARIA }
  const w = mount(MapView, {
    attachTo: document.body,
    global: { plugins: [pinia, i18n] },
  })
  await flushPromises()
  return w
}

describe('MapView: B52 report position', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    document.body.innerHTML = ''
    i18n.global.locale.value = 'en'
    hooks.fireClick = hooks.trackerClick = hooks.contextMenu = hooks.zones = null
    hooks.layerVisible = []
    api.getSettings.mockResolvedValue({ ...SETTINGS })
    api.getGroupsWithMembers.mockResolvedValue({ items: [] })
    api.getSerialStatus.mockResolvedValue(null)
    api.getFireHotspots.mockResolvedValue({ type: 'FeatureCollection', features: [] })
    api.getFireBurntAreas.mockResolvedValue({ type: 'FeatureCollection', features: [] })
    api.getSuppressionZones.mockResolvedValue([])
  })

  it('the context menu converts the map coordinate with the real toLonLat: degrees, not metres [B52]', async () => {
    api.createFieldReport.mockResolvedValue(feature('r9', { source: 'field_report' }))
    const w = await mountMap()
    const metres = fromLonLat([24.51234, 42.51234])
    expect(Math.abs(metres[0])).toBeGreaterThan(1_000_000)   // guard: the input really is EPSG:3857
    hooks.contextMenu({ coordinate: metres, pixel: [200, 150] })
    await flushPromises()
    await w.get('[data-testid="report-fire-here"]').trigger('click')
    await vi.waitFor(() => expect(w.find('[data-testid="field-report-form"]').exists()).toBe(true))
    const form = w.get('[data-testid="field-report-form"]')
    expect(form.get('[data-testid="fr-latlon"]').text()).toBe('42.51234, 24.51234')
    await form.trigger('submit')
    await flushPromises()
    const body = api.createFieldReport.mock.calls[0][0]
    expect(body.latitude).toBeCloseTo(42.51234, 5)
    expect(body.longitude).toBeCloseTo(24.51234, 5)
    expect(Math.abs(body.latitude)).toBeLessThanOrEqual(90)
    expect(Math.abs(body.longitude)).toBeLessThanOrEqual(180)
  })

  it('a rescuer position without a GNSS fix shows the amber notice and still submits [B52]', async () => {
    api.createFieldReport.mockResolvedValue(feature('r10', { source: 'field_report' }))
    const w = await mountMap()
    useLocationsStore().positions = { 'dev-1': { ...IVAN, gnss_valid: false }, 'dev-2': MARIA }
    await w.find('.tracker-row[data-device-id="dev-1"]').trigger('click')
    await w.get('[data-testid="report-fire-row"]').trigger('click')
    await vi.waitFor(() => expect(w.find('[data-testid="field-report-form"]').exists()).toBe(true))
    const warn = w.get('[data-testid="fr-nofix"]')
    expect(warn.text()).toBe(en.fire.report.noFix)
    expect(warn.classes()).toContain('md-warn')
    expect(w.get('[data-testid="fr-submit"]').attributes('disabled')).toBeUndefined()
    await w.get('[data-testid="field-report-form"]').trigger('submit')
    await flushPromises()
    expect(api.createFieldReport).toHaveBeenCalledTimes(1)
  })

  it('a position with a fix, or a map point, shows no notice [B52]', async () => {
    const w = await mountMap()
    await w.find('.tracker-row[data-device-id="dev-2"]').trigger('click')
    await w.get('[data-testid="report-fire-row"]').trigger('click')
    await vi.waitFor(() => expect(w.find('[data-testid="field-report-form"]').exists()).toBe(true))
    expect(w.find('[data-testid="fr-nofix"]').exists()).toBe(false)
    await w.get('[data-testid="fr-cancel"]').trigger('click')
    hooks.contextMenu({ coordinate: fromLonLat([24.5, 42.5]), pixel: [10, 10] })
    await flushPromises()
    await w.get('[data-testid="report-fire-here"]').trigger('click')
    await vi.waitFor(() => expect(w.find('[data-testid="field-report-form"]').exists()).toBe(true))
    expect(w.find('[data-testid="fr-nofix"]').exists()).toBe(false)
  })

  it('the no-fix notice is in both languages [B52]', () => {
    expect(en.fire.report.noFix).toBe('No GNSS fix: this is the last known position')
    expect(bg.fire.report.noFix.length).toBeGreaterThan(10)
    expect(bg.fire.errors.zoneStale.length).toBeGreaterThan(10)
  })
})
