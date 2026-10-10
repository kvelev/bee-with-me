import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../api', () => ({ getTileStatus: vi.fn(), startTileDownload: vi.fn() }))

import { getTileStatus, startTileDownload } from '../api'
import OfflineMapsCard from './OfflineMapsCard.vue'
import { i18n } from '../i18n/index.js'
import en from '../i18n/en.js'
import bg from '../i18n/bg.js'

const IDLE = { running: false, total: 0, done: 0, skipped: 0, errors: 0, error_msg: null }
const mountCard = () => mount(OfflineMapsCard, { global: { plugins: [i18n] }, attachTo: document.body })

describe('OfflineMapsCard (Settings)', () => {
  beforeEach(() => { vi.clearAllMocks(); i18n.global.locale.value = 'en'; document.body.innerHTML = '' })

  it('says whether this server has downloaded tiles', async () => {
    getTileStatus.mockResolvedValue({ ...IDLE, available: false })
    const w = mountCard()
    await flushPromises()
    expect(w.get('[data-testid="tiles-available"]').text()).toBe(en.settings.offlineMaps.notAvailable)
    w.unmount()
  })

  it('switches BG Mountains between online and offline for this browser', async () => {
    getTileStatus.mockResolvedValue({ ...IDLE, available: true })
    const w = mountCard()
    await flushPromises()
    await w.get('input[value="offline"]').setValue(true)
    expect(localStorage.getItem('bgMountainsOffline')).toBe('true')
    await w.get('input[value="online"]').setValue(true)
    expect(localStorage.getItem('bgMountainsOffline')).toBe('false')
    w.unmount()
  })

  it('asks for the password, starts the download and shows the progress', async () => {
    getTileStatus.mockResolvedValueOnce({ ...IDLE, available: false })
      .mockResolvedValue({ ...IDLE, running: false, total: 100, done: 100, skipped: 7, available: true })
    startTileDownload.mockResolvedValue({ started: true })
    const w = mountCard()
    await flushPromises()
    await w.get('[data-testid="tiles-download"]').trigger('click')
    await w.get('input[type="password"]').setValue('secret')
    await w.get('.modal-actions button:last-child').trigger('click')
    await flushPromises()
    expect(startTileDownload).toHaveBeenCalledWith('secret')
    expect(w.text()).toContain(en.settings.offlineMaps.complete)
    w.unmount()
  })

  it('shows "wrong password" on a 403', async () => {
    getTileStatus.mockResolvedValue(IDLE)
    startTileDownload.mockRejectedValue({ status: 403 })
    const w = mountCard()
    await flushPromises()
    await w.get('[data-testid="tiles-download"]').trigger('click')
    await w.get('input[type="password"]').setValue('nope')
    await w.get('.modal-actions button:last-child').trigger('click')
    await flushPromises()
    expect(w.get('.modal-error').text()).toBe(en.settings.offlineMaps.passwordWrong)
    w.unmount()
  })

  it('has every string in both languages', () => {
    expect(Object.keys(bg.settings.offlineMaps).sort()).toEqual(Object.keys(en.settings.offlineMaps).sort())
  })
})
