import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('../../api', () => ({
  getSettings:  vi.fn(),
  putSettings:  vi.fn(),
  putHQ:        vi.fn(),
  putHQInitial: vi.fn(),
  getMe:        vi.fn(),
}))

import { getSettings, putSettings, putHQ, putHQInitial, getMe } from '../../api'
import { useSettingsStore, isTransientFailure } from './store'
import { ApiError } from '../../api/client'
import { useAuthStore } from '../../stores/auth'

const DEFAULTS = {
  hq_latitude: null, hq_longitude: null, is_hq_alarm_enabled: true, is_rescuer_alarm_enabled: true,
  hq_radius_m: 10000, rescuer_radius_m: 3000, alarm_max_age_hours: 24, repeat_minutes: 5,
  updated_at: '2026-10-02T10:00:00+00:00',
}

describe('useSettingsStore', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    vi.clearAllMocks()
    useAuthStore().user = { role: 'admin' }
    getSettings.mockResolvedValue({ ...DEFAULTS })
    putSettings.mockImplementation(async (body) => {
      const { expected_updated_at, ...rest } = body
      return { ...rest, updated_at: 'later' }
    })
    putHQ.mockImplementation(async (body) => ({ ...DEFAULTS, ...body, updated_at: 'hq-later' }))
    getMe.mockResolvedValue({ role: 'admin' })
  })

  it('exposes HQ as {lat, lon} or null [T13]', async () => {
    const store = useSettingsStore()
    await store.fetchSettings()
    expect(store.hq).toBeNull()
    await store.setHQ(42.5, 24.5)
    expect(store.hq).toEqual({ lat: 42.5, lon: 24.5 })
  })

  it('saveSettings sends the full object with expected_updated_at [T13]', async () => {
    const store = useSettingsStore()
    await store.fetchSettings()
    await store.saveSettings({ hq_radius_m: 5000 })
    const sent = putSettings.mock.calls[0][0]
    expect(sent.hq_radius_m).toBe(5000)
    expect(sent.rescuer_radius_m).toBe(3000)
    expect(sent).not.toHaveProperty('updated_at')
    expect(sent.expected_updated_at).toBe(DEFAULTS.updated_at)
  })

  it('saveSettings sends the exact updated_at string it last received [B38]', async () => {
    getSettings.mockResolvedValue({ ...DEFAULTS, updated_at: '2026-10-02T10:00:00.123456+00:00' })
    const store = useSettingsStore()
    await store.fetchSettings()
    await store.saveSettings({ hq_radius_m: 5000 })
    expect(putSettings.mock.calls[0][0].expected_updated_at).toBe('2026-10-02T10:00:00.123456+00:00')
    await store.saveSettings({ hq_radius_m: 6000 })
    expect(putSettings.mock.calls[1][0].expected_updated_at).toBe('later')
  })

  it('a stale save refetches, rejects settings_stale and does not overwrite [B38]', async () => {
    const store = useSettingsStore()
    await store.fetchSettings()
    putSettings.mockRejectedValueOnce('settings_stale')
    getSettings.mockResolvedValue({ ...DEFAULTS, is_hq_alarm_enabled: false, updated_at: 'newer' })
    await expect(store.saveSettings({ hq_radius_m: 5000 })).rejects.toBe('settings_stale')
    expect(store.settings.updated_at).toBe('newer')
    expect(store.settings.is_hq_alarm_enabled).toBe(false)
    expect(store.settings.hq_radius_m).toBe(10000)
  })

  it('settings_missing surfaces as a rejection and is not swallowed [B38]', async () => {
    const store = useSettingsStore()
    await store.fetchSettings()
    putSettings.mockRejectedValueOnce('settings_missing')
    await expect(store.saveSettings({ hq_radius_m: 5000 })).rejects.toBe('settings_missing')
  })

  it('setHQ and clearHQ use PUT /settings/hq with only the coordinates [B38]', async () => {
    const store = useSettingsStore()
    await store.fetchSettings()
    await store.setHQ(42.5, 24.5)
    expect(putHQ).toHaveBeenLastCalledWith({ hq_latitude: 42.5, hq_longitude: 24.5 })
    expect(store.settings.updated_at).toBe('hq-later')
    await store.clearHQ()
    expect(putHQ).toHaveBeenLastCalledWith({ hq_latitude: null, hq_longitude: null })
    expect(putSettings).not.toHaveBeenCalled()
    expect(store.hq).toBeNull()
  })

  it('HQ writes run in click order and the store ends equal to the last write [B38]', async () => {
    const store = useSettingsStore()
    await store.fetchSettings()
    const order = []
    putHQ.mockImplementation(async (body) => {
      order.push(body.hq_latitude)
      // the first request is slow; unserialised, it would land last and win
      await new Promise(r => setTimeout(r, body.hq_latitude === 1 ? 30 : 0))
      return { ...DEFAULTS, ...body, updated_at: 'u' + body.hq_latitude }
    })
    await Promise.all([store.setHQ(1, 1), store.setHQ(2, 2)])
    expect(order).toEqual([1, 2])
    expect(store.hq).toEqual({ lat: 2, lon: 2 })
  })

  it('a failed HQ write does not block the next one [B38]', async () => {
    const store = useSettingsStore()
    await store.fetchSettings()
    putHQ.mockRejectedValueOnce('Network Error')
    await expect(store.setHQ(1, 1)).rejects.toBe('Network Error')
    await store.setHQ(3, 3)
    expect(store.hq).toEqual({ lat: 3, lon: 3 })
  })

  it('migrateLocalHQ drops the local copy for non-admins [B38]', async () => {
    localStorage.setItem('bwm.hq', JSON.stringify({ lat: 42.5, lon: 24.5 }))
    useAuthStore().user = { role: 'viewer' }
    expect(await useSettingsStore().migrateLocalHQ()).toBe('dropped')
    expect(putHQInitial).not.toHaveBeenCalled()
    expect(localStorage.getItem('bwm.hq')).toBeNull()
  })

  it('migrateLocalHQ loads the user first when not loaded yet [B38]', async () => {
    localStorage.setItem('bwm.hq', JSON.stringify({ lat: 42.5, lon: 24.5 }))
    useAuthStore().user = null
    getMe.mockResolvedValue({ role: 'viewer' })
    expect(await useSettingsStore().migrateLocalHQ()).toBe('dropped')
    expect(getMe).toHaveBeenCalledTimes(1)
    expect(putHQInitial).not.toHaveBeenCalled()

    localStorage.setItem('bwm.hq', JSON.stringify({ lat: 42.5, lon: 24.5 }))
    putHQInitial.mockResolvedValue({ ...DEFAULTS, hq_latitude: 42.5, hq_longitude: 24.5 })
    useAuthStore().user = null
    getMe.mockResolvedValue({ role: 'admin' })
    expect(await useSettingsStore().migrateLocalHQ()).toBe('uploaded')
  })

  it('migrateLocalHQ drops an invalid legacy value on a 422 and keeps it on a network error [B38]', async () => {
    localStorage.setItem('bwm.hq', JSON.stringify({ lat: 1e9, lon: 25 }))
    putHQInitial.mockRejectedValue(new ApiError([{ type: 'less_than_equal', msg: 'too big' }], 422))
    expect(await useSettingsStore().migrateLocalHQ()).toBe('dropped')
    expect(localStorage.getItem('bwm.hq')).toBeNull()

    localStorage.setItem('bwm.hq', JSON.stringify({ lat: 42, lon: 25 }))
    putHQInitial.mockRejectedValue('Network Error')
    expect(await useSettingsStore().migrateLocalHQ()).toBe('failed')
    expect(localStorage.getItem('bwm.hq')).not.toBeNull()
  })

  it('migrateLocalHQ uploads once and clears the local copy [T13]', async () => {
    localStorage.setItem('bwm.hq', JSON.stringify({ lat: 42.5, lon: 24.5 }))
    putHQInitial.mockResolvedValue({ ...DEFAULTS, hq_latitude: 42.5, hq_longitude: 24.5 })
    const store = useSettingsStore()
    expect(await store.migrateLocalHQ()).toBe('uploaded')
    expect(putHQInitial).toHaveBeenCalledWith({ hq_latitude: 42.5, hq_longitude: 24.5 })
    expect(store.hq).toEqual({ lat: 42.5, lon: 24.5 })
    expect(localStorage.getItem('bwm.hq')).toBeNull()
  })

  it('migrateLocalHQ: another admin already set HQ, local copy dropped [T13]', async () => {
    localStorage.setItem('bwm.hq', JSON.stringify({ lat: 42.5, lon: 24.5 }))
    putHQInitial.mockRejectedValue('hq_already_set')
    expect(await useSettingsStore().migrateLocalHQ()).toBe('exists')
    expect(localStorage.getItem('bwm.hq')).toBeNull()
  })

  it('migrateLocalHQ: network failure keeps the local copy for next time [T13]', async () => {
    localStorage.setItem('bwm.hq', JSON.stringify({ lat: 42.5, lon: 24.5 }))
    putHQInitial.mockRejectedValue('Network Error')
    expect(await useSettingsStore().migrateLocalHQ()).toBe('failed')
    expect(localStorage.getItem('bwm.hq')).not.toBeNull()
  })

  it('isTransientFailure judges by status, not by message text [B39]', () => {
    expect(isTransientFailure(new ApiError('Network Error', undefined))).toBe(true)   // no response
    expect(isTransientFailure(new ApiError('canceled', undefined))).toBe(true)        // aborted
    expect(isTransientFailure(new ApiError('Bad Gateway', 502))).toBe(true)
    expect(isTransientFailure(new ApiError('settings_missing', 503))).toBe(true)
    for (const status of [401, 403, 409, 422]) {
      expect(isTransientFailure(new ApiError('x', status))).toBe(false)
    }
    // a message that merely looks transient must not decide
    expect(isTransientFailure(new ApiError('timeout while parsing', 422))).toBe(false)
  })

  it('migrateLocalHQ drops the local copy on a 401 (failed refresh), keeps it on a 503 [B39]', async () => {
    localStorage.setItem('bwm.hq', JSON.stringify({ lat: 42, lon: 25 }))
    putHQInitial.mockRejectedValue(new ApiError('Not authenticated', 401))
    expect(await useSettingsStore().migrateLocalHQ()).toBe('dropped')
    expect(localStorage.getItem('bwm.hq')).toBeNull()

    localStorage.setItem('bwm.hq', JSON.stringify({ lat: 42, lon: 25 }))
    putHQInitial.mockRejectedValue(new ApiError('settings_missing', 503))
    expect(await useSettingsStore().migrateLocalHQ()).toBe('failed')
    expect(localStorage.getItem('bwm.hq')).not.toBeNull()
  })

  it('a stale save rejects with an ApiError whose detail is settings_stale [B39]', async () => {
    const store = useSettingsStore()
    await store.fetchSettings()
    putSettings.mockRejectedValueOnce(new ApiError('settings_stale', 409))
    const err = await store.saveSettings({ hq_radius_m: 5000 }).catch(e => e)
    expect(err).toBeInstanceOf(Error)
    expect(err.message).toBe('settings_stale')
    expect(err.detail).toBe('settings_stale')
    expect(err.status).toBe(409)
  })

  it('migrateLocalHQ ignores missing or malformed local values [T13]', async () => {
    expect(await useSettingsStore().migrateLocalHQ()).toBe('skipped')
    localStorage.setItem('bwm.hq', '{"lat":"x"}')
    expect(await useSettingsStore().migrateLocalHQ()).toBe('skipped')
    expect(putHQInitial).not.toHaveBeenCalled()
  })
})
