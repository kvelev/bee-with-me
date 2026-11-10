import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  getGroups: vi.fn(), getGroup: vi.fn(), createGroup: vi.fn(), updateGroup: vi.fn(), deleteGroup: vi.fn(),
  deactivateGroup: vi.fn(), reactivateGroup: vi.fn(), addMember: vi.fn(), removeMember: vi.fn(), getUsers: vi.fn(),
}))

import { getGroups, getGroup, getUsers, deactivateGroup, reactivateGroup, deleteGroup, removeMember } from '../../../api'
import { ApiError } from '../../../api/client'
import GroupsView from './GroupsView.vue'
import { i18n } from '../../../i18n/index.js'
import bg from '../../../i18n/bg.js'

const G1 = { id: 'g1', name: 'Alpha', color: '#ff0000', is_active: true, member_count: 2 }
const G2 = { id: 'g2', name: 'Bravo', color: '#00ff00', is_active: false, member_count: 0 }
const DETAIL = { ...G1, members: [{ id: 'm1', full_name: 'Ivan Petrov', rank: 'Sgt', is_leader: true }] }

function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(GroupsView, { global: { plugins: [pinia, i18n] } })
}

describe('GroupsView action errors', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getGroups.mockResolvedValue({ items: [G1, G2] })
    getUsers.mockResolvedValue({ items: [] })
    getGroup.mockResolvedValue(DETAIL)
    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  it('a rejected deleteGroup shows the error text [B70]', async () => {
    deleteGroup.mockRejectedValue(new ApiError('Group has devices', 409))
    const w = mountView()
    await flushPromises()
    await w.find('tr.clickable button.danger').trigger('click')
    await flushPromises()
    expect(w.find('.page-error').text()).toBe('Group has devices')
  })

  it('a rejected deactivateGroup and reactivateGroup show the error text [B70]', async () => {
    deactivateGroup.mockRejectedValue(new ApiError('Nope A', 403))
    reactivateGroup.mockRejectedValue(new ApiError('Nope B', 403))
    const w = mountView()
    await flushPromises()
    await w.findAll('tr.clickable')[0].find('button.warning').trigger('click')
    await flushPromises()
    expect(w.find('.page-error').text()).toBe('Nope A')
    const sec = w.findAll('tr.clickable')[1].findAll('button.secondary')
    await sec[sec.length - 1].trigger('click')
    await flushPromises()
    expect(w.find('.page-error').text()).toBe('Nope B')
  })

  it('a rejected removeMember (kick) shows the error text [B70]', async () => {
    removeMember.mockRejectedValue(new ApiError('Cannot remove', 403))
    const w = mountView()
    await flushPromises()
    await w.find('tr.clickable').trigger('click')
    await flushPromises()
    await w.findAll('.card')[1].find('tbody tr button.danger').trigger('click')
    await flushPromises()
    expect(w.find('.page-error').text()).toBe('Cannot remove')
  })

  it('the delete confirmation is the bg.js string under the bg locale [B70]', async () => {
    i18n.global.locale.value = 'bg'
    const w = mountView()
    await flushPromises()
    await w.find('tr.clickable button.danger').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledWith(bg.groups.confirmDelete.replace('{name}', 'Alpha'))
  })
})
