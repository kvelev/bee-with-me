import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  getGroups: vi.fn(), getGroup: vi.fn(), createGroup: vi.fn(), updateGroup: vi.fn(), deleteGroup: vi.fn(),
  deactivateGroup: vi.fn(), reactivateGroup: vi.fn(), addMember: vi.fn(), removeMember: vi.fn(), getUsers: vi.fn(),
}))

import { getGroups, getGroup, getUsers, deleteGroup, removeMember } from '../../../api'
import GroupsView from './GroupsView.vue'
import { i18n } from '../../../i18n/index.js'

const A = { id: 'gA', name: 'Alpha', color: '#ff0000', is_active: true, member_count: 1 }
const B = { id: 'gB', name: 'Bravo', color: '#00ff00', is_active: true, member_count: 0 }
const DA = { ...A, members: [{ id: 'm1', full_name: 'Ivan Petrov', rank: 'Sgt', is_leader: true }] }
const DB = { ...B, members: [] }

const deferred = () => { let resolve; const promise = new Promise((r) => { resolve = r }); return { promise, resolve } }
const rows = (w) => w.findAll('tr.clickable')

function mountView() {
  const pinia = createPinia(); setActivePinia(pinia)
  return mount(GroupsView, { global: { plugins: [pinia, i18n] } })
}

describe('GroupsView selection races', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getGroups.mockResolvedValue({ items: [A, B] })
    getUsers.mockResolvedValue({ items: [] })
    getGroup.mockImplementation(async (id) => (id === 'gA' ? DA : DB))
    deleteGroup.mockResolvedValue({})
    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  it('deleting group B does not drop the pending selection of group A [B103]', async () => {
    const w = mountView()
    await flushPromises()
    const d = deferred()
    getGroup.mockImplementationOnce(() => d.promise)
    await rows(w)[0].trigger('click')                         // select A, answer pending
    await rows(w)[1].find('button.danger').trigger('click')   // confirmed delete of B
    await flushPromises()
    d.resolve(DA)
    await flushPromises()
    expect(w.text()).toContain('Alpha — ')
  })

  it('removing a member of A does not overwrite the group the operator selected meanwhile [T590]', async () => {
    const w = mountView()
    await flushPromises()
    await rows(w)[0].trigger('click')
    await flushPromises()
    const d = deferred()
    removeMember.mockImplementationOnce(() => d.promise)
    await w.findAll('.card')[1].find('button.danger').trigger('click')      // kick m1 from A, request pending
    await rows(w)[1].trigger('click')                         // operator selects B
    await flushPromises()
    d.resolve({})
    await flushPromises()
    expect(w.text()).toContain('Bravo — ')
    expect(w.text()).not.toContain('Alpha — ')
  })

  it('a member kick after the selection was cleared does not throw [B105]', async () => {
    const w = mountView()
    await flushPromises()
    await rows(w)[0].trigger('click')
    await flushPromises()
    const d = deferred()
    removeMember.mockImplementationOnce(() => d.promise)
    await w.findAll('.card')[1].find('button.danger').trigger('click')
    await rows(w)[0].find('button.danger').trigger('click')   // delete A while the kick is pending
    await flushPromises()
    d.resolve({})
    await flushPromises()
    expect(w.find('.page-error').exists()).toBe(false)
    expect(w.text()).not.toContain('Alpha — ')
  })
})


