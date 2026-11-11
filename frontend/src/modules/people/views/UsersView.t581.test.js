import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  getUsers: vi.fn(), createUser: vi.fn(), updateUser: vi.fn(), deleteUser: vi.fn(), deactivateUser: vi.fn(),
  reactivateUser: vi.fn(), setGroupLeader: vi.fn(), removeMember: vi.fn(), getDevices: vi.fn(),
  assignDevice: vi.fn(), importUsers: vi.fn(),
}))

import { getUsers, getDevices, reactivateUser } from '../../../api'
import UsersView from './UsersView.vue'
import { i18n } from '../../../i18n/index.js'

const user = (id, full_name, is_active = true) => ({ id, full_name, is_active, role: 'rescuer', groups: [] })

function deferred() {
  let resolve, reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(UsersView, { global: { plugins: [pinia, i18n] } })
}

describe('UsersView overlapping requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getDevices.mockResolvedValue([])
    getUsers.mockResolvedValue({ items: [user('n', 'NewPerson', false)], total: 1 })
  })

  it('an old load that fails late does not put an error over newer good rows [T581]', async () => {
    const w = mountView()
    await flushPromises()
    const slow = deferred()
    getUsers.mockReturnValueOnce(slow.promise)
    const first = w.vm.load()
    await w.vm.load()
    await flushPromises()
    slow.reject(new Error(''))
    await first
    await flushPromises()
    expect(w.find('.page-error').exists()).toBe(false)
  })

  it('page 2 then page 3 shows page 3 when page 2 answers last [T581]', async () => {
    getUsers.mockResolvedValue({ items: [user('p1', 'PageOnePerson')], total: 200 })
    const w = mountView()
    await flushPromises()
    const p2 = deferred()
    const p3 = deferred()
    getUsers.mockReturnValueOnce(p2.promise).mockReturnValueOnce(p3.promise)
    const a = w.vm.goToPage(50)
    const b = w.vm.goToPage(100)
    p3.resolve({ items: [user('p3', 'PageThreePerson')], total: 200 })
    await b
    p2.resolve({ items: [user('p2', 'PageTwoPerson')], total: 200 })
    await a
    await flushPromises()
    expect(w.text()).toContain('PageThreePerson')
    expect(w.text()).not.toContain('PageTwoPerson')
  })

  it('a slow load that succeeds does not erase a newer action error [T581]', async () => {
    const w = mountView()
    await flushPromises()
    const slow = deferred()
    getUsers.mockReturnValueOnce(slow.promise)
    const first = w.vm.load()
    reactivateUser.mockRejectedValueOnce(new Error('Cannot reactivate'))
    await w.findAll('tr button.secondary')[1].trigger('click')
    await flushPromises()
    slow.resolve({ items: [user('n', 'NewPerson', false)], total: 1 })
    await first
    await flushPromises()
    expect(reactivateUser).toHaveBeenCalled()
    expect(w.find('.page-error').text()).toBe('Cannot reactivate')
  })
})
