import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../api', () => ({
  getGroups: vi.fn(), getGroup: vi.fn(), createGroup: vi.fn(), updateGroup: vi.fn(), deleteGroup: vi.fn(),
  deactivateGroup: vi.fn(), reactivateGroup: vi.fn(), addMember: vi.fn(), removeMember: vi.fn(), getUsers: vi.fn(),
}))

import { getGroups, getGroup, getUsers, deactivateGroup, reactivateGroup, deleteGroup, removeMember } from '../api'
import GroupsView from './GroupsView.vue'
import { i18n } from '../i18n/index.js'

const G1 = { id: 'g1', name: 'Alpha', color: '#ff0000', is_active: true, member_count: 2 }
const G2 = { id: 'g2', name: 'Bravo', color: '#00ff00', is_active: false, member_count: 0 }
const DETAIL = { ...G1, members: [
  { id: 'm1', full_name: 'Ivan Petrov', rank: 'Sgt', is_leader: true },
  { id: 'm2', full_name: 'Maria Georgieva', rank: null, is_leader: false },
] }

function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(GroupsView, { global: { plugins: [pinia, i18n] } })
}

describe('GroupsView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getGroups.mockResolvedValue({ items: [G1, G2] })
    getUsers.mockResolvedValue({ items: [] })
    getGroup.mockResolvedValue(DETAIL)
    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  it('lists groups and opens the detail on row click [T117]', async () => {
    const w = mountView()
    await flushPromises()
    const rows = w.findAll('tr.clickable')
    expect(rows).toHaveLength(2)
    expect(rows[1].classes()).toContain('row-inactive')
    expect(getUsers).toHaveBeenCalledWith({ limit: 500 })

    await rows[0].trigger('click')
    await flushPromises()
    expect(getGroup).toHaveBeenCalledWith('g1')
    const text = w.text()
    expect(text).toContain('Ivan Petrov')
    expect(text).toContain('Maria Georgieva')
    expect(text).toContain('★')
  })

  it('deactivate, reactivate and delete call the API and reload [T117]', async () => {
    const w = mountView()
    await flushPromises()
    const rows = w.findAll('tr.clickable')

    await rows[0].find('button.warning').trigger('click')
    await flushPromises()
    expect(deactivateGroup).toHaveBeenCalledWith('g1')
    expect(getGroups).toHaveBeenCalledTimes(2)

    // the inactive group shows the reactivate button: the last .secondary, after Edit
    const secondaries = w.findAll('tr.clickable')[1].findAll('button.secondary')
    await secondaries[secondaries.length - 1].trigger('click')
    await flushPromises()
    expect(reactivateGroup).toHaveBeenCalledWith('g2')
    expect(getGroups).toHaveBeenCalledTimes(3)

    await w.findAll('tr.clickable')[0].find('button.danger').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(deleteGroup).toHaveBeenCalledWith('g1')
    expect(getGroups).toHaveBeenCalledTimes(4)
  })

  it('delete does nothing when the confirmation is declined [T117]', async () => {
    confirm.mockReturnValue(false)
    const w = mountView()
    await flushPromises()
    await w.find('tr.clickable button.danger').trigger('click')
    await flushPromises()
    expect(deleteGroup).not.toHaveBeenCalled()
    expect(getGroups).toHaveBeenCalledTimes(1)
  })

  it('kicking a member calls removeMember and refetches the group [T117]', async () => {
    const w = mountView()
    await flushPromises()
    await w.find('tr.clickable').trigger('click')
    await flushPromises()
    getGroup.mockClear()
    getGroup.mockResolvedValue({ ...DETAIL, members: [DETAIL.members[1]] })

    const memberRows = w.findAll('.card')[1].findAll('tbody tr')
    expect(memberRows).toHaveLength(2)
    await memberRows[0].find('button.danger').trigger('click')
    await flushPromises()
    expect(removeMember).toHaveBeenCalledWith('g1', 'm1')
    expect(getGroup).toHaveBeenCalledWith('g1')
    expect(w.findAll('.card')[1].findAll('tbody tr')).toHaveLength(1)
  })
})
