import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'

vi.mock('../api', () => ({ resolveSOS: vi.fn() }))

import SOSBanner from './SOSBanner.vue'
import { useLocationsStore } from '../stores/locations'
import { i18n } from '../i18n/index.js'
import bg from '../i18n/bg.js'

describe('SOSBanner unknown-name fallback', () => {
  beforeEach(() => { i18n.global.locale.value = 'bg' })

  it('uses the bg.js fallback when the alert has no name [B70]', () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useLocationsStore().sosAlerts = [{ id: 'a2', device_id: 'd2', full_name: null, dev_sn: 1002 }]
    const w = mount(SOSBanner, { global: { plugins: [pinia, i18n] } })
    expect(w.find('.sos-entry').text()).toContain(`${bg.sos.unknown} (1002)`)
  })
})
