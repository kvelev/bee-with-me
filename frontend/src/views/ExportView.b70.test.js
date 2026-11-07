import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../api', () => ({
  getGroups: vi.fn(), getUsers: vi.fn(), exportCSV: vi.fn(), exportGeoJSON: vi.fn(), exportPDF: vi.fn(),
}))

import { getGroups, getUsers, exportCSV } from '../api'
import ExportView from './ExportView.vue'
import { i18n } from '../i18n/index.js'
import bg from '../i18n/bg.js'

describe('ExportView failure fallback', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'bg'
    getGroups.mockResolvedValue({ items: [] })
    getUsers.mockResolvedValue({ items: [] })
  })

  it('shows the bg.js fallback when the export rejects without a message [B70]', async () => {
    exportCSV.mockRejectedValue(new Error(''))
    const pinia = createPinia()
    setActivePinia(pinia)
    const w = mount(ExportView, { global: { plugins: [pinia, i18n] } })
    await flushPromises()
    await w.findAll('button').find(b => b.text() === bg.export.csv).trigger('click')
    await flushPromises()
    expect(w.find('p.error').text()).toBe(bg.export.failed)
  })
})
