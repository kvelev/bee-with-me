import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../api', () => ({
  getUsers: vi.fn(), createUser: vi.fn(), updateUser: vi.fn(), deleteUser: vi.fn(), deactivateUser: vi.fn(),
  reactivateUser: vi.fn(), setGroupLeader: vi.fn(), removeMember: vi.fn(), getDevices: vi.fn(),
  assignDevice: vi.fn(), importUsers: vi.fn(),
}))

import { getUsers, getDevices } from '../api'
import { ApiError } from '../api/client'
import UsersView from './UsersView.vue'
import { i18n } from '../i18n/index.js'
import en from '../i18n/en.js'
import bg from '../i18n/bg.js'

function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(UsersView, { global: { plugins: [pinia, i18n] } })
}

describe('UsersView load errors', () => {
  let unhandled
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getUsers.mockResolvedValue({ items: [], total: 0 })
    getDevices.mockResolvedValue([])
    unhandled = vi.fn()
    process.on('unhandledRejection', unhandled)
  })
  afterEach(() => { process.off('unhandledRejection', unhandled) })

  it('a rejected getUsers shows the i18n load error, no unhandled rejection [B69]', async () => {
    getUsers.mockRejectedValue(new Error(''))
    const w = mountView()
    await flushPromises()
    await new Promise(r => setTimeout(r, 0))
    expect(w.find('.page-error').text()).toBe(en.users.loadError)
    expect(unhandled).not.toHaveBeenCalled()
  })

  it('a rejected getDevices shows the server message when there is one [B69]', async () => {
    getDevices.mockRejectedValue(new ApiError('Not allowed', 403))
    const w = mountView()
    await flushPromises()
    expect(w.find('.page-error').text()).toBe('Not allowed')
  })

  it('the load error is Bulgarian under the bg locale [B69]', async () => {
    i18n.global.locale.value = 'bg'
    getUsers.mockRejectedValue(new Error(''))
    const w = mountView()
    await flushPromises()
    expect(w.find('.page-error').text()).toBe(bg.users.loadError)
    expect(bg.users.loadError).not.toBe(en.users.loadError)
  })
})
