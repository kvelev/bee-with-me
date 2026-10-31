import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../api', () => ({ resolveSOS: vi.fn() }))

import SOSBanner from './SOSBanner.vue'
import { useLocationsStore } from '../stores/locations'
import { i18n } from '../i18n/index.js'
import en from '../i18n/en.js'

const A1 = { id: 'a1', device_id: 'd1', full_name: 'Ivan Petrov', dev_sn: 1001 }
const A2 = { id: 'a2', device_id: 'd2', full_name: null, dev_sn: 1002 }

function mountBanner(alerts) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useLocationsStore()
  store.sosAlerts = alerts
  store.resolveSOS = vi.fn()
  return { w: mount(SOSBanner, { global: { plugins: [pinia, i18n] } }), store }
}

describe('SOSBanner', () => {
  beforeEach(() => { vi.clearAllMocks(); i18n.global.locale.value = 'en' })

  it('renders nothing without alerts [T117]', () => {
    const { w } = mountBanner([])
    expect(w.find('.sos-banner').exists()).toBe(false)
  })

  it('renders one entry per open alert and resolves on click [T117]', async () => {
    const { w, store } = mountBanner([A1, A2])
    const entries = w.findAll('.sos-entry')
    expect(entries).toHaveLength(2)
    expect(entries[0].text()).toContain('Ivan Petrov (1001)')
    expect(entries[1].text()).toContain('Unknown (1002)')
    await w.findAll('.resolve-btn')[0].trigger('click')
    await flushPromises()
    expect(store.resolveSOS).toHaveBeenCalledTimes(1)
    expect(store.resolveSOS).toHaveBeenCalledWith('a1')
  })

  it('shows the resolve error and re-enables the button [T117]', async () => {
    const { w, store } = mountBanner([A1])
    store.resolveSOS.mockRejectedValue('Not allowed')
    const btn = w.find('.resolve-btn')
    await btn.trigger('click')
    await flushPromises()
    expect(w.find('.sos-error').text()).toBe('Not allowed')
    expect(btn.attributes('disabled')).toBeUndefined()
    expect(btn.text()).toBe(en.sos.resolve)
  })

  it('disables the button and shows the resolving label while pending [T117]', async () => {
    const { w, store } = mountBanner([A1])
    let release
    store.resolveSOS.mockReturnValue(new Promise(r => { release = r }))
    const btn = w.find('.resolve-btn')
    await btn.trigger('click')
    expect(btn.attributes('disabled')).toBeDefined()
    expect(btn.text()).toBe(en.sos.resolving)
    release()
    await flushPromises()
    expect(btn.attributes('disabled')).toBeUndefined()
  })
})
