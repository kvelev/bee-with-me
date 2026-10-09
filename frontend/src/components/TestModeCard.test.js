import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../api', () => ({ getSimulation: vi.fn(), startSimulation: vi.fn(), stopSimulation: vi.fn() }))

import { getSimulation, startSimulation, stopSimulation } from '../api'
import TestModeCard from './TestModeCard.vue'
import { i18n } from '../i18n/index.js'
import en from '../i18n/en.js'
import bg from '../i18n/bg.js'

const IDLE = { running: false, started_at: null, lat: 0, lon: 0, interval: 0, steps: 0, devices: 0, last_error: null }
const RUNNING = { ...IDLE, running: true, lat: 42.1, lon: 24.7, interval: 2, steps: 4, devices: 6 }

const mountCard = () => mount(TestModeCard, { global: { plugins: [i18n] } })

describe('TestModeCard', () => {
  beforeEach(() => { vi.clearAllMocks(); i18n.global.locale.value = 'en' })
  afterEach(() => vi.useRealTimers())

  it('renders nothing when the server has no test endpoints (404)', async () => {
    getSimulation.mockRejectedValue({ status: 404 })
    const w = mountCard()
    await flushPromises()
    expect(w.find('[data-testid="test-mode"]').exists()).toBe(false)
  })

  it('starts with the entered position and interval, then shows the running state', async () => {
    getSimulation.mockResolvedValue(IDLE)
    startSimulation.mockResolvedValue(RUNNING)
    const w = mountCard()
    await flushPromises()
    expect(w.get('[data-testid="test-mode-state"]').text()).toBe(en.settings.testMode.stopped)
    await w.get('#tm-lat').setValue('42.1')
    await w.get('#tm-lon').setValue('24.7')
    await w.get('#tm-interval').setValue('2')
    await w.get('[data-testid="test-mode-start"]').trigger('click')
    await flushPromises()
    expect(startSimulation).toHaveBeenCalledWith({ lat: 42.1, lon: 24.7, interval: 2 })
    expect(w.get('[data-testid="test-mode-state"]').text()).toContain('6 demo trackers')
    expect(w.find('#tm-lat').exists()).toBe(false)
    expect(w.find('[data-testid="test-mode-stop"]').exists()).toBe(true)
  })

  it('stops a running simulation', async () => {
    getSimulation.mockResolvedValue(RUNNING)
    stopSimulation.mockResolvedValue({ ...RUNNING, running: false })
    const w = mountCard()
    await flushPromises()
    await w.get('[data-testid="test-mode-stop"]').trigger('click')
    await flushPromises()
    expect(stopSimulation).toHaveBeenCalled()
    expect(w.find('[data-testid="test-mode-start"]').exists()).toBe(true)
  })

  it('shows the server message when starting fails (409 already running)', async () => {
    getSimulation.mockResolvedValue(IDLE)
    startSimulation.mockRejectedValue({ detail: 'Test mode is already running', status: 409 })
    const w = mountCard()
    await flushPromises()
    await w.get('[data-testid="test-mode-start"]').trigger('click')
    await flushPromises()
    expect(w.get('[role="alert"]').text()).toBe('Test mode is already running')
  })

  it('falls back to its own message for a 422 field-error list', async () => {
    getSimulation.mockResolvedValue(IDLE)
    startSimulation.mockRejectedValue({ detail: [{ loc: ['body', 'interval'] }], status: 422 })
    const w = mountCard()
    await flushPromises()
    await w.get('[data-testid="test-mode-start"]').trigger('click')
    await flushPromises()
    expect(w.get('[role="alert"]').text()).toBe(en.settings.testMode.startFailed)
  })

  it('has every string in both languages', () => {
    expect(Object.keys(bg.settings.testMode).sort()).toEqual(Object.keys(en.settings.testMode).sort())
  })
})
