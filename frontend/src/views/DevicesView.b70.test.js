import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../api', () => ({
  getDevices: vi.fn(), createDevice: vi.fn(), updateDevice: vi.fn(), deleteDevice: vi.fn(),
  reactivateDevice: vi.fn(), permanentDeleteDevice: vi.fn(), getUsers: vi.fn(),
}))

import { getDevices, getUsers, deleteDevice, reactivateDevice, permanentDeleteDevice } from '../api'
import { ApiError } from '../api/client'
import DevicesView from './DevicesView.vue'
import { i18n } from '../i18n/index.js'
import bg from '../i18n/bg.js'

const D1 = { id: 'd1', dev_sn: 1001, name: 'Bee One', device_type: 'bee', is_active: true, user_name: 'Ivan Petrov', user_rank: 'Sgt' }
const D2 = { id: 'd2', dev_sn: 1002, name: null, device_type: 'repeater', is_active: false, user_name: null }

function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(DevicesView, { global: { plugins: [pinia, i18n] } })
}

describe('DevicesView action errors', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getDevices.mockResolvedValue([D1, D2])
    getUsers.mockResolvedValue({ items: [] })
    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  it('a rejected deactivate shows the error text [B70]', async () => {
    deleteDevice.mockRejectedValue(new ApiError('Forbidden A', 403))
    const w = mountView()
    await flushPromises()
    await w.findAll('tbody tr')[0].find('button.warning').trigger('click')
    await flushPromises()
    expect(w.find('.page-error').text()).toBe('Forbidden A')
  })

  it('a rejected reactivate shows the error text [B70]', async () => {
    reactivateDevice.mockRejectedValue(new ApiError('Forbidden B', 403))
    const w = mountView()
    await flushPromises()
    const sec = w.findAll('tbody tr')[1].findAll('button.secondary')
    await sec[sec.length - 1].trigger('click')
    await flushPromises()
    expect(w.find('.page-error').text()).toBe('Forbidden B')
  })

  it('a rejected permanent delete shows the error text [B70]', async () => {
    permanentDeleteDevice.mockRejectedValue(new ApiError('Forbidden C', 403))
    const w = mountView()
    await flushPromises()
    await w.findAll('tbody tr')[0].find('button.danger').trigger('click')
    await flushPromises()
    expect(w.find('.page-error').text()).toBe('Forbidden C')
  })

  it('confirm texts are the bg.js strings under the bg locale [B70]', async () => {
    i18n.global.locale.value = 'bg'
    const w = mountView()
    await flushPromises()
    await w.findAll('tbody tr')[0].find('button.warning').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenLastCalledWith(bg.devices.confirmDeactivate.replace('{sn}', '1001'))
    await w.findAll('tbody tr')[0].find('button.danger').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenLastCalledWith(bg.devices.confirmDelete.replace('{sn}', '1001'))
  })
})
