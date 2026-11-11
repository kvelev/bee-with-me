import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  getGroups: vi.fn(), getGroup: vi.fn(), createGroup: vi.fn(), updateGroup: vi.fn(), deleteGroup: vi.fn(),
  deactivateGroup: vi.fn(), reactivateGroup: vi.fn(), addMember: vi.fn(), removeMember: vi.fn(), getUsers: vi.fn(),
}))

import { getGroups, getGroup, getUsers, deactivateGroup } from '../../../api'
import GroupsView from './GroupsView.vue'
import { i18n } from '../../../i18n/index.js'
import en from '../../../i18n/en.js'

const G1 = { id: 'g1', name: 'Alpha', color: '#ff0000', is_active: true, member_count: 0 }
const G2 = { id: 'g2', name: 'Bravo', color: '#00ff00', is_active: true, member_count: 0 }
const OLD = { id: 'old', name: 'OldRow', color: '#111111', is_active: true, member_count: 0 }
const NEW = { id: 'new', name: 'NewRow', color: '#222222', is_active: true, member_count: 0 }

function deferred() {
  let resolve, reject
  const promise = new Promise((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(GroupsView, { global: { plugins: [pinia, i18n] } })
}

describe('GroupsView overlapping requests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getGroups.mockResolvedValue({ items: [G1] })
    getUsers.mockResolvedValue({ items: [] })
    getGroup.mockResolvedValue({ ...G1, members: [] })
  })

  it('an old load that fails late does not put an error over newer good rows [T581]', async () => {
    const w = mountView()
    await flushPromises()
    const slow = deferred()
    getGroups.mockReturnValueOnce(slow.promise)          // load #1, stays pending
    const first = w.vm.load()
    getGroups.mockResolvedValueOnce({ items: [G1] })     // load #2 succeeds
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
    getGroups.mockReturnValueOnce(slow.promise)
    const first = w.vm.load()
    getGroups.mockResolvedValueOnce({ items: [NEW] })
    getUsers.mockResolvedValueOnce({ items: [] })
    await w.vm.load()
    await flushPromises()
    expect(w.text()).toContain('NewRow')
    slow.resolve({ items: [OLD] })
    await first
    await flushPromises()
    expect(w.text()).toContain('NewRow')
    expect(w.text()).not.toContain('OldRow')
  })

  it('selecting A then B shows B when A answers last [T581]', async () => {
    getGroups.mockResolvedValue({ items: [G1, G2] })
    const w = mountView()
    await flushPromises()
    const a = deferred()
    const b = deferred()
    getGroup.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise)
    const rows = w.findAll('tr.clickable')
    await rows[0].trigger('click')
    await rows[1].trigger('click')
    b.resolve({ ...G2, members: [] })
    await flushPromises()
    a.resolve({ ...G1, members: [] })
    await flushPromises()
    expect(w.text()).toContain('Bravo — ')
    expect(w.text()).not.toContain('Alpha — ')
  })

  it('a failed selectGroup with an empty message still shows the load error text [T581]', async () => {
    const w = mountView()
    await flushPromises()
    getGroup.mockRejectedValueOnce(new Error(''))
    await w.find('tr.clickable').trigger('click')
    await flushPromises()
    expect(w.find('.page-error').exists()).toBe(true)
    expect(w.find('.page-error').text()).toBe(en.groups.loadError)
  })

  it('a failed edit-form getGroup with an empty message still shows the load error text [T581]', async () => {
    const w = mountView()
    await flushPromises()
    getGroup.mockRejectedValueOnce(new Error(''))
    await w.find('tr.clickable button.secondary').trigger('click')
    await flushPromises()
    expect(w.find('.page-error').exists()).toBe(true)
    expect(w.find('.page-error').text()).toBe(en.groups.loadError)
    expect(w.find('.modal').exists()).toBe(false)
  })

  it('a slow load that succeeds does not erase a newer action error [T581]', async () => {
    const w = mountView()
    await flushPromises()
    const slow = deferred()
    getGroups.mockReturnValueOnce(slow.promise)
    const first = w.vm.load()                            // started before the action
    deactivateGroup.mockRejectedValueOnce(new Error('Cannot deactivate'))
    await w.find('tr.clickable button.warning').trigger('click')
    await flushPromises()
    expect(w.find('.page-error').text()).toBe('Cannot deactivate')
    slow.resolve({ items: [G1] })
    await first
    await flushPromises()
    expect(w.find('.page-error').text()).toBe('Cannot deactivate')
  })
})
