import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  getSettings: vi.fn(), putSettings: vi.fn(), putHQ: vi.fn(), putHQInitial: vi.fn(), getMe: vi.fn(),
  getFireStatus: vi.fn(), getSuppressionZones: vi.fn(), updateSuppressionZone: vi.fn(), disableSuppressionZone: vi.fn(),
  enableSuppressionZone: vi.fn(),
}))

import { getSettings, getFireStatus, getSuppressionZones, updateSuppressionZone } from '../../../api'
import SettingsView from './SettingsView.vue'
import { useAuthStore } from '../../../stores/auth'
import { useFireStore } from '../../../stores/fire'
import { i18n } from '../../../i18n/index.js'

const SETTINGS = { hq_latitude: 42.5, hq_longitude: 24.5, is_hq_alarm_enabled: true, is_rescuer_alarm_enabled: true,
  hq_radius_m: 10000, rescuer_radius_m: 3000, alarm_max_age_hours: 24, repeat_minutes: 5, is_rescuer_photo_on_map_enabled: true, updated_at: 't0' }
const V1 = { id: 'z1', label: 'Solar farm', latitude: 42.5, longitude: 24.5, radius_m: 1000, is_active: true, notes: 'v1 notes', updated_at: 'v1' }
const V2 = { ...V1, radius_m: 5000, notes: 'B changed radius', updated_at: 'v2' }

async function openEdit() {
  getSettings.mockResolvedValue({ ...SETTINGS })
  getFireStatus.mockResolvedValue({ targets: { hq: true, rescuers: 0 } })
  getSuppressionZones.mockResolvedValue([{ ...V1 }])
  updateSuppressionZone.mockImplementation(async (id, body) => ({ ...V1, ...body, updated_at: 'v3' }))
  const pinia = createPinia(); setActivePinia(pinia)
  useAuthStore().user = { role: 'admin', full_name: 'Admin' }
  const w = mount(SettingsView, { global: { plugins: [pinia, i18n] } })
  await flushPromises()
  await w.get('[data-testid="zone-edit"]').trigger('click')
  await flushPromises()
  return w
}

describe('zone edit keeps its opening version [B54]', () => {
  beforeEach(() => { vi.clearAllMocks(); i18n.global.locale.value = 'en' })

  it('a push during an open edit blocks the save and shows the stale notice [B54]', async () => {
    const w = await openEdit()
    await w.get('[data-testid="zone-label"]').setValue('Solar farm (A)')
    getSuppressionZones.mockResolvedValue([{ ...V2 }])
    await useFireStore().applyFireZonesUpdated()
    await flushPromises()
    expect(w.find('[data-testid="zone-form"]').exists()).toBe(true)
    expect(w.get('[data-testid="zone-stale"]').text()).toContain('changed elsewhere')
    expect(w.get('[data-testid="zone-submit"]').attributes('disabled')).toBeDefined()
    await w.get('[data-testid="zone-form"]').trigger('submit')
    await flushPromises()
    expect(updateSuppressionZone).not.toHaveBeenCalled()
  })

  it('reloading the values re-bases the form on the new version [B54]', async () => {
    const w = await openEdit()
    getSuppressionZones.mockResolvedValue([{ ...V2 }])
    await useFireStore().applyFireZonesUpdated()
    await flushPromises()
    await w.get('[data-testid="zone-reload"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="zone-stale"]').exists()).toBe(false)
    expect(w.get('[data-testid="zone-radius"]').element.value).toBe('5000')
    await w.get('[data-testid="zone-form"]').trigger('submit')
    await flushPromises()
    const body = updateSuppressionZone.mock.calls[0][1]
    expect(body.expected_updated_at).toBe('v2')
    expect(body.radius_m).toBe(5000)
  })

  it('without a push the save carries the version the form opened on [B54]', async () => {
    const w = await openEdit()
    await w.get('[data-testid="zone-label"]').setValue('Renamed')
    await w.get('[data-testid="zone-form"]').trigger('submit')
    await flushPromises()
    const body = updateSuppressionZone.mock.calls[0][1]
    expect(body.expected_updated_at).toBe('v1')
    expect(body.label).toBe('Renamed')
  })

  it('the reload button and notice exist in Bulgarian too [B54]', async () => {
    i18n.global.locale.value = 'bg'
    const w = await openEdit()
    getSuppressionZones.mockResolvedValue([{ ...V2 }])
    await useFireStore().applyFireZonesUpdated()
    await flushPromises()
    expect(w.get('[data-testid="zone-reload"]').text()).toBe('Зареди текущите стойности')
    expect(w.get('[data-testid="zone-stale"]').text()).toContain('променена')
  })
})

describe('stale notice keeps Cancel usable [B56]', () => {
  beforeEach(() => { vi.clearAllMocks(); i18n.global.locale.value = 'en' })

  it('stale: submit is locked with its normal label, Cancel works [B56]', async () => {
    const w = await openEdit()
    getSuppressionZones.mockResolvedValue([{ ...V2 }])
    await useFireStore().applyFireZonesUpdated()
    await flushPromises()
    const submit = w.get('[data-testid="zone-submit"]')
    expect(submit.attributes('disabled')).toBeDefined()
    expect(submit.text()).not.toContain('Saving')
    expect(w.get('[data-testid="zone-cancel"]').attributes('disabled')).toBeUndefined()
    await w.get('[data-testid="zone-form"]').trigger('submit')
    await flushPromises()
    expect(updateSuppressionZone).not.toHaveBeenCalled()   // the stale-save guard still holds
    await w.get('[data-testid="zone-cancel"]').trigger('click')
    await flushPromises()
    expect(w.find('[data-testid="zone-form"]').exists()).toBe(false)
  })
})
