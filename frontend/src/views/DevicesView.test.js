import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../api', () => ({
  getDevices: vi.fn(), createDevice: vi.fn(), updateDevice: vi.fn(), deleteDevice: vi.fn(),
  reactivateDevice: vi.fn(), permanentDeleteDevice: vi.fn(), getUsers: vi.fn(),
}))

import { getDevices, getUsers, deleteDevice, reactivateDevice, permanentDeleteDevice } from '../api'
import DevicesView from './DevicesView.vue'
import { useLocationsStore } from '../stores/locations'
import { i18n } from '../i18n/index.js'
import en from '../i18n/en.js'

const D1 = { id: 'd1', dev_sn: 1001, name: 'Bee One', device_type: 'bee', is_active: true, user_name: 'Ivan Petrov', user_rank: 'Sgt' }
const D2 = { id: 'd2', dev_sn: 1002, name: null, device_type: 'repeater', is_active: false, user_name: null }

function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(DevicesView, { global: { plugins: [pinia, i18n] } })
}

describe('DevicesView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getDevices.mockResolvedValue([D1, D2])
    getUsers.mockResolvedValue({ items: [] })
    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  it('renders devices with their assigned user [T117]', async () => {
    const w = mountView()
    await flushPromises()
    const rows = w.findAll('tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('1001')
    expect(rows[0].text()).toContain('Bee One')
    expect(rows[0].text()).toContain('Ivan Petrov (Sgt)')
    expect(rows[0].text()).toContain(en.devices.active)
    expect(rows[1].text()).toContain('repeater')
    expect(rows[1].text()).toContain(en.devices.inactive)
    expect(getUsers).toHaveBeenCalledWith({ limit: 500 })
  })

  it('deactivate calls deleteDevice, reactivate calls reactivateDevice [T117]', async () => {
    const w = mountView()
    await flushPromises()
    const removePosition = vi.spyOn(useLocationsStore(), 'removePosition')

    await w.findAll('tbody tr')[0].find('button.warning').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(deleteDevice).toHaveBeenCalledWith('d1')
    expect(removePosition).toHaveBeenCalledWith('d1')
    expect(getDevices).toHaveBeenCalledTimes(2)

    const secondaries = w.findAll('tbody tr')[1].findAll('button.secondary')
    await secondaries[secondaries.length - 1].trigger('click')
    await flushPromises()
    expect(reactivateDevice).toHaveBeenCalledWith('d2')
    expect(getDevices).toHaveBeenCalledTimes(3)
  })

  it('permanent delete asks for confirmation first [T117]', async () => {
    const w = mountView()
    await flushPromises()
    confirm.mockReturnValue(false)
    await w.findAll('tbody tr')[0].find('button.danger').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(permanentDeleteDevice).not.toHaveBeenCalled()
    expect(getDevices).toHaveBeenCalledTimes(1)

    confirm.mockReturnValue(true)
    await w.findAll('tbody tr')[0].find('button.danger').trigger('click')
    await flushPromises()
    expect(permanentDeleteDevice).toHaveBeenCalledWith('d1')
    expect(getDevices).toHaveBeenCalledTimes(2)
  })
})
