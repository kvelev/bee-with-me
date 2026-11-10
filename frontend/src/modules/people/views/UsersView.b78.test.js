import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  getUsers: vi.fn(), createUser: vi.fn(), updateUser: vi.fn(), deleteUser: vi.fn(), deactivateUser: vi.fn(),
  reactivateUser: vi.fn(), setGroupLeader: vi.fn(), removeMember: vi.fn(), getDevices: vi.fn(),
  assignDevice: vi.fn(), importUsers: vi.fn(),
}))

import { getUsers, getDevices } from '../../../api'
import UsersView from './UsersView.vue'
import { i18n } from '../../../i18n/index.js'
import en from '../../../i18n/en.js'

function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(UsersView, { global: { plugins: [pinia, i18n] } })
}

describe('UsersView reload after a load error', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getDevices.mockResolvedValue([])
  })

  it('a successful reload removes the old load error [B78]', async () => {
    getUsers.mockRejectedValueOnce(new Error(''))
    getUsers.mockResolvedValueOnce({ items: [], total: 0 })
    const w = mountView()
    await flushPromises()
    expect(w.find('.page-error').exists()).toBe(true)

    await w.vm.goToPage(0)
    await flushPromises()
    expect(w.find('.page-error').exists()).toBe(false)
  })

  it('a failed reload keeps the rows and shows the error [B78]', async () => {
    getUsers.mockResolvedValueOnce({
      items: [{ id: 'u1', full_name: 'Ivan Petrov', is_active: true, role: 'rescuer', groups: [] }], total: 1,
    })
    getUsers.mockRejectedValueOnce(new Error(''))
    const w = mountView()
    await flushPromises()
    expect(w.text()).toContain('Ivan Petrov')

    await w.vm.goToPage(0)
    await flushPromises()
    expect(w.text()).toContain('Ivan Petrov')
    expect(w.find('.page-error').text()).toBe(en.users.loadError)
  })
})
