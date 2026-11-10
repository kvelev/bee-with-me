import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  getDevices: vi.fn(), createDevice: vi.fn(), updateDevice: vi.fn(), deleteDevice: vi.fn(),
  reactivateDevice: vi.fn(), permanentDeleteDevice: vi.fn(), getUsers: vi.fn(),
}))

import { getDevices, getUsers, reactivateDevice } from '../../../api'
import { ApiError } from '../../../api/client'
import DevicesView from './DevicesView.vue'
import { i18n } from '../../../i18n/index.js'
import en from '../../../i18n/en.js'
import bg from '../../../i18n/bg.js'

const D2 = { id: 'd2', dev_sn: 1002, name: null, device_type: 'repeater', is_active: false, user_name: null }

function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(DevicesView, { global: { plugins: [pinia, i18n] } })
}

describe('DevicesView unguarded load', () => {
  let unhandled
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getDevices.mockResolvedValue([D2])
    getUsers.mockResolvedValue({ items: [] })
    unhandled = vi.fn()
    process.on('unhandledRejection', unhandled)
  })
  afterEach(() => { process.off('unhandledRejection', unhandled) })

  it('a rejected getDevices shows the i18n load error, no unhandled rejection [B77]', async () => {
    getDevices.mockRejectedValue(new Error(''))
    const w = mountView()
    await flushPromises()
    await new Promise(r => setTimeout(r, 0))
    expect(w.find('.page-error').text()).toBe(en.devices.loadError)
    expect(unhandled).not.toHaveBeenCalled()
  })

  it('a rejected getUsers shows the server message when there is one [B77]', async () => {
    getUsers.mockRejectedValue(new ApiError('Not allowed', 403))
    const w = mountView()
    await flushPromises()
    await new Promise(r => setTimeout(r, 0))
    expect(w.find('.page-error').text()).toBe('Not allowed')
    expect(unhandled).not.toHaveBeenCalled()
  })

  it('the load error is Bulgarian under the bg locale [B77]', async () => {
    i18n.global.locale.value = 'bg'
    getDevices.mockRejectedValue(new Error(''))
    const w = mountView()
    await flushPromises()
    expect(w.find('.page-error').text()).toBe(bg.devices.loadError)
    expect(bg.devices.loadError).not.toBe(en.devices.loadError)
  })

  it('a failed reload keeps the rows, then a good reload clears the error [B77]', async () => {
    reactivateDevice.mockResolvedValue({})
    const w = mountView()
    await flushPromises()
    expect(w.findAll('tbody tr')).toHaveLength(1)
    getDevices.mockRejectedValueOnce(new Error(''))
    await w.findAll('tbody tr button.secondary')[1].trigger('click')
    await flushPromises()
    expect(w.find('.page-error').text()).toBe(en.devices.loadError)
    expect(w.findAll('tbody tr')).toHaveLength(1)
    await w.findAll('tbody tr button.secondary')[1].trigger('click')
    await flushPromises()
    expect(w.find('.page-error').exists()).toBe(false)
  })
})
