import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  getDevices: vi.fn(), createDevice: vi.fn(), updateDevice: vi.fn(), deleteDevice: vi.fn(),
  reactivateDevice: vi.fn(), permanentDeleteDevice: vi.fn(), getUsers: vi.fn(),
}))

import { getDevices, getUsers, reactivateDevice } from '../../../api'
import DevicesView from './DevicesView.vue'
import { i18n } from '../../../i18n/index.js'

const OLD = { id: 'old', dev_sn: 1111, name: 'OldDevice', device_type: 'bee', is_active: false, user_name: null }
const NEW = { id: 'new', dev_sn: 2222, name: 'NewDevice', device_type: 'bee', is_active: false, user_name: null }

function deferred() {
  let resolve, reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(DevicesView, { global: { plugins: [pinia, i18n] } })
}

describe('DevicesView overlapping requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getDevices.mockResolvedValue([NEW])
    getUsers.mockResolvedValue({ items: [] })
  })

  it('an old load that fails late does not put an error over newer good rows [T581]', async () => {
    const w = mountView()
    await flushPromises()
    const slow = deferred()
    getDevices.mockReturnValueOnce(slow.promise)
    const first = w.vm.load()
    await w.vm.load()
    await flushPromises()
    slow.reject(new Error(''))
    await first
    await flushPromises()
    expect(w.find('.page-error').exists()).toBe(false)
  })

  it('an old load that resolves late does not replace newer rows [T581]', async () => {
    const w = mountView()
    await flushPromises()
    const slow = deferred()
    getDevices.mockReturnValueOnce(slow.promise)
    const first = w.vm.load()
    await w.vm.load()
    await flushPromises()
    expect(w.text()).toContain('NewDevice')
    slow.resolve([OLD])
    await first
    await flushPromises()
    expect(w.text()).toContain('NewDevice')
    expect(w.text()).not.toContain('OldDevice')
  })

  it('a slow load that succeeds does not erase a newer action error [T581]', async () => {
    const w = mountView()
    await flushPromises()
    const slow = deferred()
    getDevices.mockReturnValueOnce(slow.promise)
    const first = w.vm.load()
    reactivateDevice.mockRejectedValueOnce(new Error('Cannot reactivate'))
    await w.findAll('tr button.secondary')[1].trigger('click')
    await flushPromises()
    expect(w.find('.page-error').text()).toBe('Cannot reactivate')
    slow.resolve([NEW])
    await first
    await flushPromises()
    expect(w.find('.page-error').text()).toBe('Cannot reactivate')
  })
})
