import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../../api', () => ({
  getGroups: vi.fn(), getGroup: vi.fn(), createGroup: vi.fn(), updateGroup: vi.fn(), deleteGroup: vi.fn(),
  deactivateGroup: vi.fn(), reactivateGroup: vi.fn(), addMember: vi.fn(), removeMember: vi.fn(), getUsers: vi.fn(),
}))

import { getGroups, getGroup, getUsers, deactivateGroup } from '../../../api'
import { ApiError } from '../../../api/client'
import GroupsView from './GroupsView.vue'
import { i18n } from '../../../i18n/index.js'
import en from '../../../i18n/en.js'
import bg from '../../../i18n/bg.js'

const G1 = { id: 'g1', name: 'Alpha', color: '#ff0000', is_active: true, member_count: 2 }
const DETAIL = { ...G1, members: [{ id: 'm1', full_name: 'Ivan Petrov', rank: 'Sgt', is_leader: true }] }

function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(GroupsView, { global: { plugins: [pinia, i18n] } })
}

describe('GroupsView unguarded loads', () => {
  let unhandled
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getGroups.mockResolvedValue({ items: [G1] })
    getUsers.mockResolvedValue({ items: [] })
    getGroup.mockResolvedValue(DETAIL)
    unhandled = vi.fn()
    process.on('unhandledRejection', unhandled)
  })
  afterEach(() => { process.off('unhandledRejection', unhandled) })

  it('a rejected getGroups shows the i18n load error, no unhandled rejection [B77]', async () => {
    getGroups.mockRejectedValue(new Error(''))
    const w = mountView()
    await flushPromises()
    await new Promise(r => setTimeout(r, 0))
    expect(w.find('.page-error').text()).toBe(en.groups.loadError)
    expect(unhandled).not.toHaveBeenCalled()
  })

  it('a rejected getUsers shows the server message when there is one [B77]', async () => {
    getUsers.mockRejectedValue(new ApiError('Not allowed', 403))
    const w = mountView()
    await flushPromises()
    await new Promise(r => setTimeout(r, 0))
    expect(w.find('.page-error').text()).toBe('Not allowed')
    expect(unhandled).not.toHaveBeenCalled()
  })

  it('the load error is Bulgarian under the bg locale [B77]', async () => {
    i18n.global.locale.value = 'bg'
    getGroups.mockRejectedValue(new Error(''))
    const w = mountView()
    await flushPromises()
    expect(w.find('.page-error').text()).toBe(bg.groups.loadError)
    expect(bg.groups.loadError).not.toBe(en.groups.loadError)
  })

  it('a failed reload keeps the rows, then a good reload clears the error [B77]', async () => {
    deactivateGroup.mockResolvedValue({})
    const w = mountView()
    await flushPromises()
    expect(w.findAll('tr.clickable')).toHaveLength(1)
    getGroups.mockRejectedValueOnce(new Error(''))
    await w.find('tr.clickable button.warning').trigger('click')
    await flushPromises()
    expect(w.find('.page-error').text()).toBe(en.groups.loadError)
    expect(w.findAll('tr.clickable')).toHaveLength(1)
    await w.find('tr.clickable button.warning').trigger('click')
    await flushPromises()
    expect(w.find('.page-error').exists()).toBe(false)
  })

  it('a rejected getGroup on row click shows the error, no unhandled rejection [B77]', async () => {
    const w = mountView()
    await flushPromises()
    getGroup.mockRejectedValue(new ApiError('Group gone', 404))
    await w.find('tr.clickable').trigger('click')
    await flushPromises()
    await new Promise(r => setTimeout(r, 0))
    expect(w.find('.page-error').text()).toBe('Group gone')
    expect(unhandled).not.toHaveBeenCalled()
  })

  it('a rejected getGroup when opening the edit form shows the error and keeps the form closed [B77]', async () => {
    const w = mountView()
    await flushPromises()
    getGroup.mockRejectedValue(new ApiError('Group gone', 404))
    await w.find('tr.clickable button.secondary').trigger('click')
    await flushPromises()
    await new Promise(r => setTimeout(r, 0))
    expect(w.find('.page-error').text()).toBe('Group gone')
    expect(w.find('.modal').exists()).toBe(false)
    expect(unhandled).not.toHaveBeenCalled()
  })
})
