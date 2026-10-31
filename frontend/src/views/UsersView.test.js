import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../api', () => ({
  getUsers: vi.fn(), createUser: vi.fn(), updateUser: vi.fn(), deleteUser: vi.fn(), deactivateUser: vi.fn(),
  reactivateUser: vi.fn(), setGroupLeader: vi.fn(), removeMember: vi.fn(), getDevices: vi.fn(),
  assignDevice: vi.fn(), importUsers: vi.fn(),
}))

import { getUsers, getDevices, deactivateUser, importUsers } from '../api'
import UsersView from './UsersView.vue'
import { i18n } from '../i18n/index.js'
import en from '../i18n/en.js'

const U1 = { id: 'u1', full_name: 'Ivan Petrov', is_active: true, role: 'rescuer', groups: [] }
const U2 = { id: 'u2', full_name: 'Maria Georgieva', is_active: true, role: 'viewer', groups: '[]' }

function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(UsersView, { global: { plugins: [pinia, i18n] } })
}

describe('UsersView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getUsers.mockResolvedValue({ items: [U1, U2], total: 2 })
    getDevices.mockResolvedValue([])
    vi.stubGlobal('confirm', vi.fn(() => true))
  })

  it('renders one row per user and loads devices alongside [T117]', async () => {
    const w = mountView()
    await flushPromises()
    expect(w.findAll('tbody tr')).toHaveLength(2)
    expect(w.text()).toContain('Ivan Petrov')
    expect(w.text()).toContain('Maria Georgieva')
    expect(getUsers).toHaveBeenCalledWith({ limit: 50, offset: 0 })
    expect(getDevices).toHaveBeenCalledTimes(1)
  })

  it('deactivate asks for confirmation, calls the API and reloads [T117]', async () => {
    const w = mountView()
    await flushPromises()
    await w.find('tbody tr button.warning').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledTimes(1)
    expect(deactivateUser).toHaveBeenCalledWith('u1')
    expect(getUsers).toHaveBeenCalledTimes(2)

    confirm.mockReturnValue(false)
    await w.find('tbody tr button.warning').trigger('click')
    await flushPromises()
    expect(deactivateUser).toHaveBeenCalledTimes(1)
    expect(getUsers).toHaveBeenCalledTimes(2)
  })

  it('import posts the file and shows created and skipped counts [T117]', async () => {
    importUsers.mockResolvedValue({ created: 4, skipped: [{ row: 7, reason: 'duplicate phone' }] })
    const w = mountView()
    await flushPromises()
    const file = new File(['x'], 'people.xlsx')
    const input = w.find('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [file] })
    await input.trigger('change')
    await flushPromises()
    expect(importUsers).toHaveBeenCalledWith(file)
    const result = w.find('.import-result')
    expect(result.text()).toContain(`4 ${en.users.importCreated}`)
    expect(result.text()).toContain(`1 ${en.users.importSkipped}`)
    expect(result.text()).toContain('row 7: duplicate phone')
    expect(getUsers).toHaveBeenCalledTimes(2)
  })

  it('shows the import error text when the import is rejected [T117]', async () => {
    importUsers.mockRejectedValue('Bad spreadsheet')
    const w = mountView()
    await flushPromises()
    const input = w.find('input[type=file]')
    Object.defineProperty(input.element, 'files', { value: [new File(['x'], 'p.xlsx')] })
    await input.trigger('change')
    await flushPromises()
    expect(w.find('.page-error').text()).toBe('Bad spreadsheet')
    expect(w.find('.import-result').exists()).toBe(false)
  })
})
