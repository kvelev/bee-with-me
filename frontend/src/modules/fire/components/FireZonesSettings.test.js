import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { ApiError } from '../../../api/client'

vi.mock('../../../api', () => ({
  getSuppressionZones: vi.fn(), updateSuppressionZone: vi.fn(), disableSuppressionZone: vi.fn(),
  enableSuppressionZone: vi.fn(),
}))

import * as api from '../../../api'
import FireZonesSettings from './FireZonesSettings.vue'
import { i18n } from '../../../i18n/index.js'
import en from '../../../i18n/en.js'

const ZONES = [
  { id: 'z1', label: 'Solar farm', latitude: 42.5, longitude: 24.5, radius_m: 1000, is_active: true, notes: null, updated_at: 'u1' },
  { id: 'z2', label: 'Old quarry', latitude: 42.6, longitude: 24.6, radius_m: 500, is_active: false, notes: null, updated_at: 'u2' },
]

async function mountPanel(isAdmin = true) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const w = mount(FireZonesSettings, { props: { context: { isAdmin } }, global: { plugins: [pinia, i18n] } })
  await flushPromises()
  return w
}

describe('FireZonesSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    api.getSuppressionZones.mockResolvedValue(ZONES.map(z => ({ ...z })))
  })

  it('lists the zones with disabled ones and offers enable and disable [T509]', async () => {
    const w = await mountPanel()
    expect(api.getSuppressionZones).toHaveBeenCalledWith({ include_disabled: true })
    const items = w.findAll('[data-testid="zone-item"]')
    expect(items).toHaveLength(2)
    expect(items[0].text()).toContain('Solar farm')
    expect(items[1].text()).toContain(en.settings.zones.disabled)
    expect(items[0].find('[data-testid="zone-disable"]').exists()).toBe(true)
    expect(items[1].find('[data-testid="zone-enable"]').exists()).toBe(true)
    expect(w.get('[data-testid="zones-disabled-note"]').text()).toContain('48 hours')
  })

  it('a stale zone shows the conflict text and reloads the list [T509]', async () => {
    api.disableSuppressionZone.mockRejectedValue(new ApiError('zone_stale', 409))
    const w = await mountPanel()
    api.getSuppressionZones.mockResolvedValue([{ ...ZONES[0], label: 'Solar farm 2', updated_at: 'u9' }, { ...ZONES[1] }])
    await w.get('[data-testid="zone-disable"]').trigger('click')
    await flushPromises()
    expect(api.getSuppressionZones).toHaveBeenCalledTimes(2)
    expect(w.text()).toContain(en.fire.errors.zoneStale)
    expect(w.text()).toContain('Solar farm 2')
  })

  it('a viewer sees no zone form [T509]', async () => {
    const w = await mountPanel(false)
    expect(w.findAll('[data-testid="zone-item"]')).toHaveLength(2)
    expect(w.find('[data-testid="zone-edit"]').exists()).toBe(false)
    expect(w.find('[data-testid="zone-disable"]').exists()).toBe(false)
    expect(w.find('[data-testid="zone-enable"]').exists()).toBe(false)
    expect(w.find('[data-testid="zone-form"]').exists()).toBe(false)
  })
})
