import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  getUsers: vi.fn(), createUser: vi.fn(), updateUser: vi.fn(), deleteUser: vi.fn(), deactivateUser: vi.fn(),
  reactivateUser: vi.fn(), setGroupLeader: vi.fn(), removeMember: vi.fn(), getDevices: vi.fn(),
  assignDevice: vi.fn(), importUsers: vi.fn(),
}))

import { getUsers, getDevices, deactivateUser } from '../../../api'
import UsersView from './UsersView.vue'
import { i18n } from '../../../i18n/index.js'

const U1 = { id: 'u1', full_name: 'Ivan Petrov', is_active: true, role: 'rescuer', groups: [] }

describe('UsersView action errors', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getDevices.mockResolvedValue([])
    getUsers.mockResolvedValue({ items: [U1], total: 1 })
    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  it('a rejection without a message never shows "[object Object]" [B104]', async () => {
    deactivateUser.mockRejectedValue({ status: 500 })
    const pinia = createPinia(); setActivePinia(pinia)
    const w = mount(UsersView, { global: { plugins: [pinia, i18n] } })
    await flushPromises()
    await w.find('button.warning').trigger('click')
    await flushPromises()
    expect(w.find('.page-error').text()).not.toContain('object Object')
  })

  it('a string rejection is shown as it is [T590]', async () => {
    deactivateUser.mockRejectedValue('Not allowed')
    const pinia = createPinia(); setActivePinia(pinia)
    const w = mount(UsersView, { global: { plugins: [pinia, i18n] } })
    await flushPromises()
    await w.find('button.warning').trigger('click')
    await flushPromises()
    expect(w.find('.page-error').text()).toBe('Not allowed')
  })
})

