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

// The map itself is replaced; the facade is a Proxy whose unknown members are no-op spies.
vi.mock('../composables/useMap', () => ({
  BASEMAPS: [],
  useMap: () => {
    const fakeMap = {
      addOverlay: vi.fn(), removeOverlay: vi.fn(), on: vi.fn(), un: vi.fn(),
      getView: () => ({ animate: vi.fn(), getCenter: () => [0, 0] }), updateSize: vi.fn(),
    }
    const own = { map: () => fakeMap, setHotspots: () => true, setBurntAreas: () => true }
    return new Proxy(own, { get: (t, k) => (k in t ? t[k] : vi.fn()) })
  },
}))
vi.mock('ol/Overlay', () => ({ default: class { setPosition() {} } }))
vi.mock('ol/proj', () => ({ fromLonLat: (c) => c, toLonLat: (c) => c }))

// One fixture manifest next to the real modules: a panel of host `map` and a layer toggle with the state pair.
const fx = vi.hoisted(() => ({ ctx: null, on: null, set: vi.fn(), hosts: {} }))
vi.mock('../modules', async (importOriginal) => {
  const real = await importOriginal()
  const { ref, h: hh } = await import('vue')
  fx.on = ref(false)
  fx.set.mockImplementation((v) => { fx.on.value = v })
  const panel = (id, host) => ({
    id,
    host,
    component: { props: ['context'], setup(p) { fx.hosts[host] = p.context; return () => hh('div', { class: `fx-panel fx-${host}` }) } },
  })
  const fixture = {
    name: 'fx', routes: [], nav: [], banners: [], liveHandlers: {}, depends: [], i18n: { en: {}, bg: {} },
    panels: [panel('fx-map', 'map'), panel('fx-root', 'map-root'), panel('fx-toolbar', 'map-toolbar')],
    mapLayers: [{ id: 'fx-layer', zIndex: 99, toggle: { labelKey: 'fx.label', order: 99, key: 'fx', isOn: () => fx.on.value, set: (v) => fx.set(v) } }],
  }
  return { ...real, MODULES: [...real.MODULES, fixture] }
})

import * as api from '../api'
import MapView from './MapView.vue'
import { useAuthStore } from '../stores/auth'
import { useLocationsStore } from '../stores/locations'
import { i18n } from '../i18n/index.js'

const SETTINGS = {
  hq_latitude: null, hq_longitude: null, is_hq_alarm_enabled: false, is_rescuer_alarm_enabled: true,
  hq_radius_m: 10000, rescuer_radius_m: 3000, alarm_max_age_hours: 24, repeat_minutes: 5, updated_at: 't0',
}

async function mountMap(role = 'admin') {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { role }
  const loc = useLocationsStore()
  loc.fetchLive = vi.fn(); loc.fetchSOS = vi.fn(); loc.fetchTrail = vi.fn()
  loc.positions = {}
  const w = mount(MapView, { attachTo: document.body, global: { plugins: [pinia, i18n], stubs: { SOSToast: true } } })
  await flushPromises()
  return w
}

describe('MapView: panel hosts and the toggle state hook', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    document.body.innerHTML = ''
    fx.on.value = false
    fx.hosts = {}
    fx.set.mockImplementation((v) => { fx.on.value = v })
    api.getSettings.mockResolvedValue({ ...SETTINGS })
    api.getGroupsWithMembers.mockResolvedValue({ items: [] })
    api.getSerialStatus.mockResolvedValue(null)
    api.getFireHotspots.mockResolvedValue({ type: 'FeatureCollection', features: [] })
    api.getFireBurntAreas.mockResolvedValue({ type: 'FeatureCollection', features: [] })
    api.getSuppressionZones.mockResolvedValue([])
  })

  it('a module panel of host map is rendered inside the map layout with the context [T504]', async () => {
    const w = await mountMap()
    expect(w.find('.map-layout .fx-map').exists()).toBe(true)
    expect(w.find('.basemap-switcher .fx-map-toolbar').exists()).toBe(true)
    expect(w.find('.fx-map-root').exists()).toBe(true)
    expect(w.find('.map-layout .fx-map-root').exists()).toBe(false)   // map-root is outside the layout
    const ctx = fx.hosts.map
    expect(typeof ctx.facade.setHotspots).toBe('function')
    expect(Object.keys(ctx.mapKit).sort()).toEqual(['Overlay', 'fromLonLat', 'toLonLat', 'unByKey'])
    for (const f of Object.values(ctx.mapKit)) expect(typeof f).toBe('function')
    expect(ctx.isAdmin.value).toBe(true)
    expect('value' in ctx.hostMap && 'value' in ctx.activeBasemap && 'value' in ctx.mapActive && 'value' in ctx.selectedDeviceId).toBe(true)
    expect(typeof ctx.closeContextMenu).toBe('function')
  })

  it('a toggle with a state pair is driven by it [T504]', async () => {
    const w = await mountMap()
    const btn = w.get('[data-layer="fx"]')
    expect(btn.classes()).not.toContain('active')
    expect(btn.attributes('aria-pressed')).toBe('false')
    await btn.trigger('click')
    expect(fx.set).toHaveBeenCalledWith(true)
    expect(w.get('[data-layer="fx"]').classes()).toContain('active')
    expect(w.get('[data-layer="fx"]').attributes('aria-pressed')).toBe('true')
    await w.get('[data-layer="fx"]').trigger('click')
    expect(fx.set).toHaveBeenLastCalledWith(false)
  })
})
