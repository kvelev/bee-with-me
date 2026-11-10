import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  getSettings: vi.fn(), putSettings: vi.fn(), putHQ: vi.fn(), putHQInitial: vi.fn(), getMe: vi.fn(),
  getFireStatus: vi.fn(), getSuppressionZones: vi.fn(), updateSuppressionZone: vi.fn(), disableSuppressionZone: vi.fn(),
}))

import { getSettings, putSettings, getFireStatus, getSuppressionZones } from '../../../api'
import SettingsView from './SettingsView.vue'
import { useSettingsStore } from '../store'
import { i18n } from '../../../i18n/index.js'
import en from '../../../i18n/en.js'
import bg from '../../../i18n/bg.js'

const BASE = {
  hq_latitude: null, hq_longitude: null, is_hq_alarm_enabled: false, is_rescuer_alarm_enabled: true,
  hq_radius_m: 10000, rescuer_radius_m: 3000, alarm_max_age_hours: 24, repeat_minutes: 5, updated_at: 't0',
}
let server

function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(SettingsView, { global: { plugins: [pinia, i18n] } })
}
const photoBox = (w) => w.find('input[aria-describedby="photo-hint"]')

describe('Map display section [F1]', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    server = { ...BASE, is_rescuer_photo_on_map_enabled: true }
    getFireStatus.mockResolvedValue({ targets: { hq: false, rescuers: 2 } })
    getSuppressionZones.mockResolvedValue([])
    getSettings.mockImplementation(async () => ({ ...server }))
    putSettings.mockImplementation(async (b) => {
      const { expected_updated_at, ...rest } = b
      server = { ...rest, updated_at: server.updated_at + 'x' }
      return { ...server }
    })
  })

  it('saves the photo flag inside the full body, switching it off [F1]', async () => {
    const w = mountView()
    await flushPromises()
    expect(w.text()).toContain('Show rescuer photos on the map')
    expect(photoBox(w).element.checked).toBe(true)
    await photoBox(w).setValue(false)
    await w.find('form').trigger('submit')
    await flushPromises()
    const body = putSettings.mock.calls.at(-1)[0]
    expect(body.is_rescuer_photo_on_map_enabled).toBe(false)
    expect(body).toMatchObject({ hq_radius_m: 10000, repeat_minutes: 5, expected_updated_at: 't0', is_rescuer_alarm_enabled: true })
    expect(useSettingsStore().photosOnMap).toBe(false)
  })

  it('an old server response without the field counts as on and is not dirty [F1]', async () => {
    server = { ...BASE }
    const w = mountView()
    await flushPromises()
    expect(photoBox(w).element.checked).toBe(true)
    expect(w.find('button[type=submit]').element.disabled).toBe(true)
    expect(useSettingsStore().photosOnMap).toBe(true)
  })

  it('both languages carry the section strings [F1]', () => {
    for (const k of ['mapDisplay', 'photosOnMap', 'photosOnMapHint']) {
      expect(en.settings[k]).toBeTruthy()
      expect(bg.settings[k]).toBeTruthy()
    }
  })
})
