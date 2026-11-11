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
// `result` is what the facade's setHQPlacementMode answers: false (failed layer) or undefined (old mock).
const hq = vi.hoisted(() => ({ result: undefined, calls: [] }))
vi.mock('../composables/useMap', () => ({
  BASEMAPS: [],
  useMap: () => new Proxy({
    map: () => null,
    setHQPlacementMode: (on) => { hq.calls.push(['hq', on]); return hq.result },
    setMeasureMode: (on) => { hq.calls.push(['measure', on]) },
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

async function mountMap() {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { role: 'admin' }
  const loc = useLocationsStore()
  loc.fetchLive = vi.fn(); loc.fetchSOS = vi.fn(); loc.fetchTrail = vi.fn()
  const w = mount(MapView, { global: { plugins: [pinia, i18n], stubs: { SOSToast: true, FirePopup: true } } })
  await flushPromises()
  return w
}
const hqButton = (w) => w.findAll('button').find(b => b.text() === en.map.hqMove)

describe('MapView HQ placement signal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    hq.calls.length = 0
    i18n.global.locale.value = 'en'
    getSettings.mockResolvedValue({ ...SETTINGS })
    getGroupsWithMembers.mockResolvedValue({ items: [] })
    getSerialStatus.mockResolvedValue(null)
  })

  it('the HQ button does not stay pressed and an alert says the layer failed [T580]', async () => {
    hq.result = false
    const w = await mountMap()
    await hqButton(w).trigger('click')
    expect(hqButton(w).classes()).not.toContain('active')
    const alert = w.find('.bm-hq-error[role="alert"]')
    expect(alert.exists()).toBe(true)
    expect(alert.text()).toBe('The HQ layer could not be loaded. Reload the page.')
    expect(bg.map.hqLayerFailed).toBe('Слоят на щаба не се зареди. Презаредете страницата.')
  })

  it('with a facade that returns nothing the button works as today [T580]', async () => {
    hq.result = undefined
    const w = await mountMap()
    await hqButton(w).trigger('click')
    expect(hqButton(w).classes()).toContain('active')
    expect(w.text()).not.toContain(en.map.hqLayerFailed)
    await hqButton(w).trigger('click')
    expect(hqButton(w).classes()).not.toContain('active')
  })

  it('a failed HQ layer leaves measure mode running [T580]', async () => {
    hq.result = false
    const w = await mountMap()
    await w.findAll('button').find(b => b.text() === en.map.measure).trigger('click')
    hq.calls.length = 0
    await hqButton(w).trigger('click')
    expect(hq.calls).not.toContainEqual(['measure', false])
    expect(w.text()).toContain(en.map.hqLayerFailed)
  })

  it('switching from measure to HQ ends with HQ placement on, so the crosshair stays [T580]', async () => {
    hq.result = undefined
    const w = await mountMap()
    await w.findAll('button').find(b => b.text() === en.map.measure).trigger('click')
    hq.calls.length = 0
    await hqButton(w).trigger('click')
    const last = hq.calls[hq.calls.length - 1]
    expect(last).toEqual(['hq', true])
    expect(hq.calls).toContainEqual(['measure', false])
  })
})
