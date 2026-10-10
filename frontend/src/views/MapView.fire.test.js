import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { ApiError } from '../api/client'

vi.mock('../api', () => ({
  getSettings: vi.fn(), putSettings: vi.fn(), putHQ: vi.fn(), putHQInitial: vi.fn(), getMe: vi.fn(),
  getGroupsWithMembers: vi.fn(), getSerialStatus: vi.fn(),
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
    global: { plugins: [pinia, i18n], stubs: { SOSToast: true } },
  })
  await flushPromises()
  return w
}

describe('MapView: report fire from a selected volunteer', () => {
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

  const rowOf = (w, id) => w.find(`.tracker-row[data-device-id="${id}"]`)

  it('the action appears only under the selected volunteer [T19]', async () => {
    const w = await mountMap()
    expect(w.find('[data-testid="report-fire-row"]').exists()).toBe(false)
    await rowOf(w, 'dev-1').trigger('click')
    const buttons = w.findAll('[data-testid="report-fire-row"]')
    expect(buttons).toHaveLength(1)
    expect(buttons[0].text()).toBe(en.fire.report.atPosition)
    expect(rowOf(w, 'dev-1').classes()).toContain('tracker-selected')
    await rowOf(w, 'dev-2').trigger('click')
    expect(w.findAll('[data-testid="report-fire-row"]')).toHaveLength(1)
    expect(rowOf(w, 'dev-1').classes()).not.toContain('tracker-selected')
  })

  it('the row is keyboard reachable: Enter selects it [T19]', async () => {
    const w = await mountMap()
    expect(rowOf(w, 'dev-1').attributes('tabindex')).toBe('0')
    await rowOf(w, 'dev-1').trigger('keydown', { key: 'Enter' })
    expect(w.find('[data-testid="report-fire-row"]').exists()).toBe(true)
  })

  it('clicking the volunteer marker selects the row [T19]', async () => {
    const w = await mountMap()
    hooks.trackerClick('dev-2')
    await flushPromises()
    expect(rowOf(w, 'dev-2').classes()).toContain('tracker-selected')
    hooks.trackerClick(null)
    await flushPromises()
    expect(w.find('[data-testid="report-fire-row"]').exists()).toBe(false)
  })

  it('files the report with the frozen coordinates, then shows the hotspots layer [T19]', async () => {
    api.createFieldReport.mockResolvedValue(feature('r1', { source: 'field_report' }))
    const w = await mountMap()
    await rowOf(w, 'dev-1').trigger('click')
    await w.get('[data-testid="report-fire-row"]').trigger('click')
    const form = w.get('[data-testid="field-report-form"]')
    expect(form.get('[data-testid="fr-rescuer"]').text()).toBe('Ivan Petrov')
    expect(form.get('[data-testid="fr-mgrs"]').text()).toBe('35TLG1234567890')
    await form.get('[data-testid="fr-notes"]').setValue('smoke over the ridge')
    await form.trigger('submit')
    await flushPromises()
    expect(api.createFieldReport).toHaveBeenCalledWith({ latitude: 42.5, longitude: 24.5, notes: 'smoke over the ridge' })
    expect(w.find('[data-testid="field-report-form"]').exists()).toBe(false)
    expect(useFireStore().layers.hotspots).toBe(true)
  })

  it('the position is frozen when the form opens, whatever the volunteer does next [T19]', async () => {
    api.createFieldReport.mockResolvedValue(feature('r1', { source: 'field_report' }))
    const w = await mountMap()
    await rowOf(w, 'dev-1').trigger('click')
    await w.get('[data-testid="report-fire-row"]').trigger('click')
    const form = w.get('[data-testid="field-report-form"]')
    expect(form.get('[data-testid="fr-latlon"]').text()).toBe('42.50000, 24.50000')
    expect(form.get('[data-testid="fr-time"]').text()).toMatch(/\d{2}:\d{2}:\d{2}/)
    // the volunteer moves while the operator types
    useLocationsStore().positions = { ...useLocationsStore().positions, 'dev-1': { ...IVAN, latitude: 42.9, longitude: 24.9, mgrs: '35TLG9999999999' } }
    await flushPromises()
    expect(w.get('[data-testid="fr-latlon"]').text()).toBe('42.50000, 24.50000')
    await w.get('[data-testid="fr-notes"]').setValue('smoke')
    await w.get('[data-testid="field-report-form"]').trigger('submit')
    await flushPromises()
    expect(api.createFieldReport).toHaveBeenCalledTimes(1)
    expect(api.createFieldReport).toHaveBeenCalledWith({ latitude: 42.5, longitude: 24.5, notes: 'smoke' })
  })

  it('a volunteer without a position cannot be reported and the API is not called [T19]', async () => {
    const w = await mountMap()
    const loc = useLocationsStore()
    loc.positions = { 'dev-1': { ...IVAN, latitude: null, longitude: null } }
    await flushPromises()
    await rowOf(w, 'dev-1').trigger('click')
    await w.get('[data-testid="report-fire-row"]').trigger('click')
    expect(w.get('[data-testid="fr-error"]').text()).toBe('This rescuer has no position in the last 24 h')
    expect(w.get('[data-testid="fr-submit"]').attributes('disabled')).toBeDefined()
    await w.get('[data-testid="field-report-form"]').trigger('submit')
    await flushPromises()
    expect(api.createFieldReport).not.toHaveBeenCalled()
    expect(bg.fire.errors.noRecentPosition).toBe('Този спасител няма позиция през последните 24 ч')
  })

  it('a position older than 24 h by received_at cannot be reported [T19]', async () => {
    const w = await mountMap()
    const old = new Date(Date.now() - 25 * 3_600_000).toISOString()
    useLocationsStore().positions = { 'dev-1': { ...IVAN, received_at: old } }
    await flushPromises()
    await rowOf(w, 'dev-1').trigger('click')
    await w.get('[data-testid="report-fire-row"]').trigger('click')
    expect(w.get('[data-testid="fr-submit"]').attributes('disabled')).toBeDefined()
    expect(w.get('[data-testid="fr-error"]').text()).toBe(en.fire.errors.noRecentPosition)
    expect(api.createFieldReport).not.toHaveBeenCalled()
  })

  it('a 404 on submit says the backend lacks the endpoint, not a missing item [T19]', async () => {
    api.createFieldReport.mockRejectedValue(new ApiError('Not Found', 404))
    const w = await mountMap()
    await rowOf(w, 'dev-1').trigger('click')
    await w.get('[data-testid="report-fire-row"]').trigger('click')
    await w.get('[data-testid="field-report-form"]').trigger('submit')
    await flushPromises()
    expect(w.get('[data-testid="fr-error"]').text()).toBe(en.fire.errors.reportEndpoint)
    expect(w.find('[data-testid="field-report-form"]').exists()).toBe(true)
  })

  it('Cancel closes the form without a request [T19]', async () => {
    const w = await mountMap()
    await rowOf(w, 'dev-1').trigger('click')
    await w.get('[data-testid="report-fire-row"]').trigger('click')
    await w.get('[data-testid="fr-cancel"]').trigger('click')
    expect(w.find('[data-testid="field-report-form"]').exists()).toBe(false)
    expect(api.createFieldReport).not.toHaveBeenCalled()
  })

  it('the action works for a non-admin too (field reports are open to every user) [T19]', async () => {
    api.createFieldReport.mockResolvedValue(feature('r1', { source: 'field_report' }))
    const w = await mountMap('viewer')
    await rowOf(w, 'dev-2').trigger('click')
    await w.get('[data-testid="report-fire-row"]').trigger('click')
    await w.get('[data-testid="field-report-form"]').trigger('submit')
    await flushPromises()
    expect(api.createFieldReport).toHaveBeenCalledWith({ latitude: 42.6, longitude: 24.6, notes: null })
  })
})

describe('MapView: right-click / long-press "Report fire here"', () => {
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
  })

  it('offers the item, opens the form on the clicked point and submits latitude and longitude [T19]', async () => {
    api.createFieldReport.mockResolvedValue(feature('r2', { source: 'field_report' }))
    const w = await mountMap()
    hooks.contextMenu({ coordinate: [24.51234, 42.51234], pixel: [200, 150] })
    await flushPromises()
    const item = w.get('[data-testid="report-fire-here"]')
    expect(item.text()).toBe(en.fire.report.here)
    await item.trigger('click')
    expect(w.find('[role="menu"]').exists()).toBe(false)
    const form = w.get('[data-testid="field-report-form"]')
    expect(form.get('[data-testid="fr-latlon"]').text()).toBe('42.51234, 24.51234')
    await form.trigger('submit')
    await flushPromises()
    expect(api.createFieldReport).toHaveBeenCalledWith({ latitude: 42.51234, longitude: 24.51234, notes: null })
  })

  it('Escape closes the menu without opening a form [T19]', async () => {
    const w = await mountMap()
    hooks.contextMenu({ coordinate: [24.5, 42.5], pixel: [10, 10] })
    await flushPromises()
    expect(w.find('[role="menu"]').exists()).toBe(true)
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(w.find('[role="menu"]').exists()).toBe(false)
    expect(w.find('[data-testid="field-report-form"]').exists()).toBe(false)
  })

  it('a pointer press outside the menu closes it [T19]', async () => {
    const w = await mountMap()
    hooks.contextMenu({ coordinate: [24.5, 42.5], pixel: [10, 10] })
    await flushPromises()
    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await flushPromises()
    expect(w.find('[role="menu"]').exists()).toBe(false)
  })
})

describe('MapView: popup actions and zones', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    document.body.innerHTML = ''
    i18n.global.locale.value = 'en'
    hooks.zones = null
    hooks.layerVisible = []
    api.getSettings.mockResolvedValue({ ...SETTINGS })
    api.getGroupsWithMembers.mockResolvedValue({ items: [] })
    api.getSerialStatus.mockResolvedValue(null)
    api.getFireHotspots.mockResolvedValue({ type: 'FeatureCollection', features: [] })
    api.getFireBurntAreas.mockResolvedValue({ type: 'FeatureCollection', features: [] })
    api.getSuppressionZones.mockResolvedValue([])
  })

  async function openPopup(w, props = {}) {
    useFireStore().hotspots = { type: 'FeatureCollection', features: [feature('h1', props)] }
    hooks.fireClick({ kind: 'hotspot', properties: { id: 'h1', source: 'viirs', state: 'active', acquired_at: NOW, ...props }, coordinate: [24.5, 42.5] })
    await flushPromises()
  }

  it('Dismiss sends the id and note, then the popup shows the server copy [T19]', async () => {
    api.dismissFireHotspot.mockResolvedValue(feature('h1', { state: 'dismissed', dismiss_notes: 'solar' }))
    const w = await mountMap()
    await openPopup(w)
    await w.get('[data-action="toggle-note"]').trigger('click')
    await w.get('[data-testid="fp-note"]').setValue('solar')
    await w.get('[data-action="dismiss"]').trigger('click')
    await flushPromises()
    expect(api.dismissFireHotspot).toHaveBeenCalledWith('h1', 'solar')
    expect(w.text()).toContain(en.fire.state.dismissed)
    expect(w.find('[data-action="dismiss"]').exists()).toBe(false)
  })

  it('a failed Dismiss says so inside the popup and leaves it open [T19]', async () => {
    api.dismissFireHotspot.mockRejectedValue(new ApiError('Hotspot not found', 404))
    const w = await mountMap()
    await openPopup(w)
    await w.get('[data-action="dismiss"]').trigger('click')
    await flushPromises()
    expect(w.get('[data-testid="fp-error"]').text()).toBe(en.fire.errors.notFound)
    expect(w.find('[data-action="dismiss"]').exists()).toBe(true)
  })

  it('Create zone opens the form at the detection and creates the zone, then shows the zones layer [T19]', async () => {
    const zone = { id: 'z1', label: 'Solar farm', latitude: 42.5, longitude: 24.5, radius_m: 1500, is_active: true }
    api.createSuppressionZone.mockResolvedValue(zone)
    api.getSuppressionZones.mockResolvedValue([zone])   // what the server lists once the layer loads
    const w = await mountMap()
    await openPopup(w)
    await w.get('[data-action="create-zone"]').trigger('click')
    const form = w.get('[data-testid="zone-form"]')
    expect(form.get('[data-testid="zone-point"]').text()).toBe('42.50000, 24.50000')
    expect(form.get('[data-testid="zone-radius"]').element.value).toBe('1000')
    // label is required
    await form.trigger('submit')
    expect(api.createSuppressionZone).not.toHaveBeenCalled()
    await form.get('[data-testid="zone-label"]').setValue('Solar farm')
    await form.get('[data-testid="zone-radius"]').setValue('1500')
    await form.trigger('submit')
    await flushPromises()
    expect(api.createSuppressionZone).toHaveBeenCalledWith({
      label: 'Solar farm', radius_m: 1500, notes: null, latitude: 42.5, longitude: 24.5,
    })
    expect(useFireStore().layers.zones).toBe(true)
    expect(hooks.zones.map(z => z.id)).toEqual(['z1'])
  })

  it('the zone radius is limited to 50 to 20000 m [T19]', async () => {
    const w = await mountMap()
    await openPopup(w)
    await w.get('[data-action="create-zone"]').trigger('click')
    const form = w.get('[data-testid="zone-form"]')
    await form.get('[data-testid="zone-label"]').setValue('x')
    for (const bad of ['49', '20001', '10.5', '']) {
      await form.get('[data-testid="zone-radius"]').setValue(bad)
      await form.trigger('submit')
    }
    expect(api.createSuppressionZone).not.toHaveBeenCalled()
  })

  it('the Suppression zones toggle is admin-only [T19]', async () => {
    const admin = await mountMap('admin')
    expect(admin.find('[data-layer="zones"]').exists()).toBe(true)
    admin.unmount()
    const viewer = await mountMap('viewer')
    expect(viewer.find('[data-layer="zones"]').exists()).toBe(false)
  })

  it('only active zones are drawn [T19]', async () => {
    const w = await mountMap()
    const fire = useFireStore()
    fire.zones = [
      { id: 'a', label: 'on', latitude: 1, longitude: 2, radius_m: 100, is_active: true },
      { id: 'b', label: 'off', latitude: 1, longitude: 2, radius_m: 100, is_active: false },
    ]
    await flushPromises()
    expect(hooks.zones.map(z => z.id)).toEqual(['a'])
    expect(w.exists()).toBe(true)
  })

  it('the freshness pill is not shown for the zones layer alone [T19]', async () => {
    const w = await mountMap()
    useFireStore().layers = { burnt: false, hotspots: false, zones: true }
    await flushPromises()
    expect(w.find('.fire-pill').exists()).toBe(false)
  })
})

describe('MapView: "Show on map" from a fire alarm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    document.body.innerHTML = ''
    hooks.layerVisible = []
    api.getSettings.mockResolvedValue(SETTINGS)
    api.getGroupsWithMembers.mockResolvedValue({ items: [] })
    api.getSerialStatus.mockResolvedValue({})
    api.getFireHotspots.mockResolvedValue({ type: 'FeatureCollection', features: [], meta: {} })
    api.getFireBurntAreas.mockResolvedValue({ type: 'FeatureCollection', features: [], meta: {} })
    api.getSuppressionZones.mockResolvedValue([])
  })

  // The real app keeps MapView alive (AppLayout); onActivated, which consumes the request, only runs there.
  async function mountAlive() {
    const { KeepAlive, h, defineComponent } = await import('vue')
    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().user = { role: 'admin' }
    const loc = useLocationsStore()
    loc.fetchLive = vi.fn(); loc.fetchSOS = vi.fn(); loc.fetchTrail = vi.fn()
    const Host = defineComponent({ render: () => h(KeepAlive, null, [h(MapView)]) })
    const w = mount(Host, { attachTo: document.body, global: { plugins: [pinia, i18n], stubs: { SOSToast: true } } })
    await flushPromises()
    return w
  }

  it('turns the hotspots layer on and marks the spot, so the fire is not an empty map', async () => {
    const w = await mountAlive()
    const fire = useFireStore()
    expect(fire.layers.hotspots).toBeFalsy()
    fire.requestFocus(42.7, 24.17)
    await flushPromises()
    expect(fire.focusRequest).toBeNull()                       // consumed
    expect(fire.layers.hotspots).toBe(true)
    expect(hooks.layerVisible).toContainEqual(['hotspots', true])
    expect(w.find('[data-testid="fire-focus-ring"]').exists()).toBe(true)
    w.unmount()
  })

  it('leaves an already visible hotspots layer on', async () => {
    const w = await mountAlive()
    const fire = useFireStore()
    fire.layers.hotspots = true
    hooks.layerVisible = []                                     // forget the sync done at mount
    fire.requestFocus(42.7, 24.17)
    await flushPromises()
    expect(fire.layers.hotspots).toBe(true)
    expect(hooks.layerVisible).toEqual([])                     // not toggled (which would hide it)
    w.unmount()
  })
})
