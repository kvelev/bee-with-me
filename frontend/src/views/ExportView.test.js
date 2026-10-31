import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../api', () => ({
  getGroups: vi.fn(), getUsers: vi.fn(), exportCSV: vi.fn(), exportGeoJSON: vi.fn(), exportPDF: vi.fn(),
}))

import { getGroups, getUsers, exportCSV, exportGeoJSON } from '../api'
import ExportView from './ExportView.vue'
import { i18n } from '../i18n/index.js'
import en from '../i18n/en.js'

function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  return mount(ExportView, { global: { plugins: [pinia, i18n] } })
}

describe('ExportView', () => {
  let createObjectURL, revokeObjectURL, anchorClick
  beforeEach(() => {
    vi.clearAllMocks()
    i18n.global.locale.value = 'en'
    getGroups.mockResolvedValue({ items: [{ id: 'g1', name: 'Alpha' }, { id: 'g2', name: 'Bravo' }] })
    getUsers.mockResolvedValue({ items: [{ id: 'u1', full_name: 'Ivan Petrov' }] })
    createObjectURL = vi.fn(() => 'blob:x')
    revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL })
    anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })

  it('loads groups and users for the filters [T117]', async () => {
    const w = mountView()
    await flushPromises()
    const selects = w.findAll('select')
    expect(selects[0].findAll('option').map(o => o.text())).toEqual([en.export.allGroups, 'Alpha', 'Bravo'])
    expect(selects[1].findAll('option').map(o => o.text())).toEqual([en.export.allPersons, 'Ivan Petrov'])
    expect(getUsers).toHaveBeenCalledWith({ limit: 500 })
  })

  it('CSV export passes the filters and triggers a download [T117]', async () => {
    exportCSV.mockResolvedValue('a,b')
    const w = mountView()
    await flushPromises()
    const inputs = w.findAll('input[type=datetime-local]')
    await inputs[0].setValue('2026-10-01T08:00')
    await inputs[1].setValue('2026-10-02T09:30')
    await w.findAll('select')[0].setValue('g2')
    await w.findAll('select')[1].setValue('u1')
    await w.findAll('.export-btns button')[0].trigger('click')
    await flushPromises()
    expect(exportCSV).toHaveBeenCalledWith({
      from: '2026-10-01T08:00', to: '2026-10-02T09:30', group_id: 'g2', user_id: 'u1',
    })
    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(anchorClick).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:x')
    expect(w.find('.error').exists()).toBe(false)
  })

  it('omits unset filters from the export request [T117]', async () => {
    exportGeoJSON.mockResolvedValue('{}')
    const w = mountView()
    await flushPromises()
    await w.findAll('.export-btns button')[1].trigger('click')
    await flushPromises()
    expect(exportGeoJSON).toHaveBeenCalledWith({})
    expect(createObjectURL).toHaveBeenCalledTimes(1)
  })

  it('shows the error text when an export fails [T117]', async () => {
    exportCSV.mockRejectedValue('Server exploded')
    const w = mountView()
    await flushPromises()
    await w.findAll('.export-btns button')[0].trigger('click')
    await flushPromises()
    expect(w.find('.error').text()).toBe('Server exploded')
    expect(createObjectURL).not.toHaveBeenCalled()
    expect(w.findAll('.export-btns button')[0].attributes('disabled')).toBeUndefined()
  })
})
