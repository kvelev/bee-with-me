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

const BASE = {
  hq_latitude: null, hq_longitude: null, is_hq_alarm_enabled: false, is_rescuer_alarm_enabled: true,
  hq_radius_m: 10000, rescuer_radius_m: 3000, alarm_max_age_hours: 24, repeat_minutes: 5, updated_at: 't0',
}
let server

function mountView(preload) {
  const pinia = createPinia()
  setActivePinia(pinia)
  if (preload) useSettingsStore().settings = { ...preload }
  return mount(SettingsView, { global: { plugins: [pinia, i18n] } })
}

describe('SettingsView against a changing server', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    server = { ...BASE }
    getFireStatus.mockResolvedValue({ targets: { hq: false, rescuers: 2 } })
    getSuppressionZones.mockResolvedValue([])
    getSettings.mockImplementation(async () => ({ ...server }))
    putSettings.mockImplementation(async (b) => {
      if (b.expected_updated_at !== server.updated_at) throw 'settings_stale'
      const { expected_updated_at, ...rest } = b
      server = { ...rest, updated_at: server.updated_at + 'x' }
      return { ...server }
    })
  })

  it('a stale page cannot overwrite an alarm another admin enabled [B38]', async () => {
    const w = mountView()
    await flushPromises()
    server = { ...server, is_hq_alarm_enabled: true, updated_at: 't1' }   // another admin enabled it
    await w.find('#hq-radius').setValue('5')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(server.is_hq_alarm_enabled).toBe(true)
    expect(server.hq_radius_m).toBe(5000)
  })

  it('turning an alarm off needs the confirmation, decided on fresh server state [B38]', async () => {
    const w = mountView()
    await flushPromises()
    // the page loaded with the rescuer alarm ON; the user unticks it
    await w.findAll('input[type=checkbox]')[1].setValue(false)
    // the server meanwhile turned the HQ alarm on: the page still shows it OFF and never touched it
    server = { ...server, is_hq_alarm_enabled: true, updated_at: 't1' }
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.find('.confirm-off').exists()).toBe(true)
    expect(w.find('.confirm-off').text()).toContain(en.settings.rescuerOffNotice)
    expect(w.find('.confirm-off').text()).not.toContain(en.settings.hqOffNotice)
    expect(putSettings).not.toHaveBeenCalled()
    // confirming writes the fresh version and keeps the HQ alarm on
    await w.find('.confirm-off button.warn').trigger('click')
    await flushPromises()
    expect(server.is_rescuer_alarm_enabled).toBe(false)
    expect(server.is_hq_alarm_enabled).toBe(true)
  })

  it('a load finishing after the user typed does not wipe the typed value [B38]', async () => {
    let release
    getSettings.mockImplementationOnce(() => new Promise((r) => { release = () => r({ ...server }) }))
    const w = mountView(BASE)   // cached state: the form is usable while the refetch is in flight
    await flushPromises()
    await w.find('#hq-radius').setValue('7')
    server = { ...server, repeat_minutes: 9, updated_at: 't1' }
    release()
    await flushPromises()
    expect(w.find('#hq-radius').element.value).toBe('7')
    expect(w.find('#repeat').element.value).toBe('9')   // an untouched field takes the fresh value
  })

  it('a stale save says so, keeps the edit and does not overwrite [B38]', async () => {
    const w = mountView()
    await flushPromises()
    await w.find('#hq-radius').setValue('5')
    putSettings.mockRejectedValueOnce('settings_stale')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain(en.settings.saveStale)
    expect(w.find('#hq-radius').element.value).toBe('5')
    expect(server.hq_radius_m).toBe(10000)
  })

  it('a failed pre-save refetch says nothing was saved, not save failed [B39]', async () => {
    const w = mountView()
    await flushPromises()
    await w.find('#hq-radius').setValue('5')
    getSettings.mockRejectedValueOnce(new Error('Network Error'))
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain(en.settings.checkFailed)
    expect(w.text()).not.toContain(en.settings.saveFailed)
    expect(putSettings).not.toHaveBeenCalled()
  })

  it('a fresh state that already matches the form says nothing to save [B39]', async () => {
    const w = mountView()
    await flushPromises()
    await w.find('#hq-radius').setValue('5')
    server = { ...server, hq_radius_m: 5000, updated_at: 't1' }   // another admin saved the same value
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain(en.settings.nothingToSave)
    expect(putSettings).not.toHaveBeenCalled()
  })

  it('a failed save reads "Could not confirm the save" [B38]', async () => {
    const w = mountView()
    await flushPromises()
    await w.find('#hq-radius').setValue('5')
    putSettings.mockRejectedValueOnce('Network Error')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(w.text()).toContain('Could not confirm the save. Reload to check.')
  })
})

describe('logout in Settings', () => {
  it('Settings has a Log out button that signs out and returns to the login page [LOGOUT]', async () => {
    const { createRouter, createMemoryHistory } = await import('vue-router')
    const { useAuthStore } = await import('../../../stores/auth')
    const pinia = createPinia()
    setActivePinia(pinia)
    localStorage.setItem('token', 't'); localStorage.setItem('refresh_token', 'r')
    const auth = useAuthStore()
    auth.token = 't'; auth.user = { role: 'admin', full_name: 'Test Admin' }
    getSettings.mockResolvedValue({ ...BASE })
    const page = { template: '<i />' }
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/settings', component: page }, { path: '/login', component: page }] })
    router.push('/settings'); await router.isReady()
    const w = mount(SettingsView, { global: { plugins: [pinia, i18n, router] } })
    await flushPromises()
    const btn = w.find('[data-test=logout]')
    expect(btn.text()).toBe(en.settings.logout)
    expect(btn.classes()).not.toContain('danger')   // not destructive: no red
    expect(w.text()).toContain('Test Admin')
    await btn.trigger('click')
    await flushPromises()
    expect(auth.token).toBe('')
    expect(localStorage.getItem('token')).toBeNull()
    expect(router.currentRoute.value.path).toBe('/login')
  })

  it('the Log out button is there even when the settings failed to load [LOGOUT]', async () => {
    getSettings.mockRejectedValue(new Error('down'))
    const w = mountView()
    await flushPromises()
    expect(w.find('.msg-warn').exists()).toBe(true)
    expect(w.find('[data-test=logout]').exists()).toBe(true)
  })
})
