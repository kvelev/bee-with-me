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
const mapArgs = vi.hoisted(() => ({ onHQPlace: null, onRepeaterPlace: null }))
vi.mock('../composables/useMap', () => ({
  BASEMAPS: [],
  useMap: (...args) => {
    mapArgs.onHQPlace = args[6]
    return new Proxy({ map: () => null, onRepeaterPlaced: (cb) => { mapArgs.onRepeaterPlace = cb } }, {
      get: (t, k) => (k in t ? t[k] : vi.fn()),
    })
  },
}))
vi.mock('ol/Overlay', () => ({ default: class {} }))
vi.mock('ol/proj', () => ({ fromLonLat: (c) => c, toLonLat: (c) => c }))

import { getSettings, putHQ, getGroupsWithMembers, getSerialStatus, getDevices, setDeviceLocation } from '../api'
import MapView from './MapView.vue'
import { useAuthStore } from '../stores/auth'
import { useLocationsStore } from '../stores/locations'
import { useSettingsStore } from '../stores/settings'
import { i18n } from '../i18n/index.js'
import en from '../i18n/en.js'

const SETTINGS = {
  hq_latitude: 42.5, hq_longitude: 24.5, is_hq_alarm_enabled: true, is_rescuer_alarm_enabled: true,
  hq_radius_m: 10000, rescuer_radius_m: 3000, alarm_max_age_hours: 24, repeat_minutes: 5, updated_at: 't0',
}

async function mountMap(role) {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { role }
  const loc = useLocationsStore()
  loc.fetchLive = vi.fn(); loc.fetchSOS = vi.fn(); loc.fetchTrail = vi.fn()
  const w = mount(MapView, { global: { plugins: [pinia, i18n], stubs: { FirePopup: true } } })
  await flushPromises()
  return w
}
const texts = (w) => w.findAll('button').map(b => b.text())

describe('MapView HQ controls', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    i18n.global.locale.value = 'en'
    getSettings.mockResolvedValue({ ...SETTINGS })
    putHQ.mockImplementation(async (b) => ({ ...SETTINGS, ...b, updated_at: 't1' }))
    getGroupsWithMembers.mockResolvedValue({ items: [] })
    getSerialStatus.mockResolvedValue(null)
  })

  it('HQ buttons are hidden for non-admins [B38]', async () => {
    const w = await mountMap('viewer')
    expect(texts(w)).not.toContain(en.map.hqMove)
    expect(texts(w)).not.toContain(en.map.hqClear)
    expect(texts(w)).not.toContain(en.map.hqSet)
  })

  it('Clear HQ asks for confirmation before writing [B38]', async () => {
    const w = await mountMap('admin')
    const clear = w.findAll('button').find(b => b.text() === en.map.hqClear)
    await clear.trigger('click')
    expect(putHQ).not.toHaveBeenCalled()
    expect(w.text()).toContain('The HQ fire alarm cannot work without HQ')
    await w.findAll('button').find(b => b.text() === en.map.hqClearCancel).trigger('click')
    expect(putHQ).not.toHaveBeenCalled()
    await w.findAll('button').find(b => b.text() === en.map.hqClear).trigger('click')
    await w.findAll('button').find(b => b.text() === en.map.hqClearYes).trigger('click')
    await flushPromises()
    expect(putHQ).toHaveBeenCalledWith({ hq_latitude: null, hq_longitude: null })
    expect(useSettingsStore().hq).toBeNull()
  })

  it('a slow failing HQ click followed by a successful one leaves no error [B39]', async () => {
    const w = await mountMap('admin')
    let failFirst
    putHQ.mockImplementationOnce(() => new Promise((_, reject) => { failFirst = () => reject(new Error('Network Error')) }))
    mapArgs.onHQPlace({ lat: 1, lon: 1 })     // slow, will fail
    mapArgs.onHQPlace({ lat: 2, lon: 2 })     // queued behind it, will succeed
    await flushPromises()
    failFirst()
    await flushPromises()
    expect(putHQ).toHaveBeenCalledTimes(2)
    expect(w.text()).not.toContain(en.map.hqSaveFailed)
    expect(useSettingsStore().hq).toEqual({ lat: 2, lon: 2 })
  })

  it('the latest HQ click failing still shows the error [B39]', async () => {
    const w = await mountMap('admin')
    putHQ.mockRejectedValueOnce(new Error('Network Error'))
    mapArgs.onHQPlace({ lat: 3, lon: 3 })
    await flushPromises()
    expect(w.text()).toContain(en.map.hqSaveFailed)
  })

  it('a failed settings load shows an amber note, disables Set HQ, and Retry recovers [B38]', async () => {
    getSettings.mockRejectedValueOnce('Network Error')
    const w = await mountMap('admin')
    expect(w.text()).toContain('Settings unavailable: HQ not shown')
    const setBtn = w.findAll('button').find(b => b.text() === en.map.hqSet)
    expect(setBtn.attributes('disabled')).toBeDefined()
    await w.findAll('button').find(b => b.text() === en.map.settingsRetry).trigger('click')
    await flushPromises()
    expect(w.text()).not.toContain('Settings unavailable')
    const moveBtn = w.findAll('button').find(b => b.text() === en.map.hqMove)
    expect(moveBtn.attributes('disabled')).toBeUndefined()
  })
})

describe('MapView repeater placement', () => {
  const R1 = { id: 'r1', dev_sn: 10, name: 'Ridge', device_type: 'repeater', is_active: true, site_latitude: 42.1, site_longitude: 24.1 }
  const R2 = { id: 'r2', dev_sn: 11, name: null,    device_type: 'repeater', is_active: true, site_latitude: null, site_longitude: null }
  const BEE = { id: 'b1', dev_sn: 10, name: 'Bee', device_type: 'bee', is_active: true }

  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getSettings.mockResolvedValue({ ...SETTINGS })
    getGroupsWithMembers.mockResolvedValue({ items: [] })
    getSerialStatus.mockResolvedValue(null)
    getDevices.mockResolvedValue([R1, R2, BEE])
    setDeviceLocation.mockImplementation(async (id, lat, lon) => ({ id, site_latitude: lat, site_longitude: lon }))
  })

  it('is hidden for non-admins', async () => {
    const w = await mountMap('viewer')
    expect(texts(w)).not.toContain(en.map.repeaterSet)
  })

  it('lists only repeaters and preselects the first unplaced one', async () => {
    const w = await mountMap('admin')
    await w.findAll('button').find(b => b.text() === en.map.repeaterSet).trigger('click')
    const options = w.findAll('select.bm-select option')
    expect(options.map(o => o.attributes('value'))).toEqual(['r1', 'r2'])
    expect(w.find('select.bm-select').element.value).toBe('r2')
  })

  it('a map click saves the selected repeater and leaves placement mode', async () => {
    const w = await mountMap('admin')
    await w.findAll('button').find(b => b.text() === en.map.repeaterSet).trigger('click')
    mapArgs.onRepeaterPlace({ lat: 42.7, lon: 23.3 })
    await flushPromises()
    expect(setDeviceLocation).toHaveBeenCalledWith('r2', 42.7, 23.3)
    expect(w.find('select.bm-select').exists()).toBe(false)
  })

  it('a failed save shows an error', async () => {
    setDeviceLocation.mockRejectedValueOnce(new Error('Network Error'))
    const w = await mountMap('admin')
    await w.findAll('button').find(b => b.text() === en.map.repeaterSet).trigger('click')
    mapArgs.onRepeaterPlace({ lat: 1, lon: 1 })
    await flushPromises()
    expect(w.text()).toContain(en.map.repeaterSaveFailed)
  })

  it('Clear location is offered for a placed repeater and clears it', async () => {
    const w = await mountMap('admin')
    await w.findAll('button').find(b => b.text() === en.map.repeaterSet).trigger('click')
    await w.find('select.bm-select').setValue('r1')
    await w.findAll('button').find(b => b.text() === en.map.repeaterClear).trigger('click')
    await flushPromises()
    expect(setDeviceLocation).toHaveBeenCalledWith('r1', null, null)
  })
})
