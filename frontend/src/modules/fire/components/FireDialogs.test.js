import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { ApiError } from '../../../api/client'

vi.mock('../../../api', () => ({
  getFireHotspots: vi.fn(), getFireBurntAreas: vi.fn(), getFireStatus: vi.fn(),
  getFireAlerts: vi.fn(), getSuppressionZones: vi.fn(),
  createFieldReport: vi.fn(), createSuppressionZone: vi.fn(),
}))

import FireDialogs from './FireDialogs.vue'
import { useFireStore } from '../store.js'
import { useFireUi } from '../ui.js'
import { i18n } from '../../../i18n/index.js'

function setup() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useFireStore()
  store.setLayer = vi.fn(async (name, on) => { store.layers = { ...store.layers, [name]: on } })
  const context = { closeContextMenu: vi.fn() }
  const w = mount(FireDialogs, { props: { context }, attachTo: document.body, global: { plugins: [pinia, i18n] } })
  return { w, store, ui: useFireUi(), context }
}

const REPORT = (latitude = 42.5, longitude = 24.5) => ({ kind: 'report', target: { latitude, longitude } })
const form = () => document.querySelector('[data-testid="field-report-form"]')
const submit = (el) => el.dispatchEvent(new Event('submit', { cancelable: true }))

describe('FireDialogs', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    i18n.global.locale.value = 'en'
  })
  afterEach(() => { document.body.innerHTML = '' })

  it('a report dialog submits through the store and shows the hotspots layer [T508]', async () => {
    const { w, store, ui } = setup()
    store.reportFire = vi.fn(async () => {})
    expect(form()).toBeNull()
    ui.openDialog(REPORT())
    await flushPromises()
    expect(form()).not.toBeNull()
    submit(form())
    await flushPromises()
    expect(store.reportFire).toHaveBeenCalledWith({ latitude: 42.5, longitude: 24.5, notes: null })
    expect(ui.dialog).toBeNull()
    expect(store.setLayer).toHaveBeenCalledWith('hotspots', true)
    w.unmount()
  })

  it('a position-less report cannot be sent [T508]', async () => {
    const { w, store, ui } = setup()
    store.reportFire = vi.fn()
    ui.openDialog({ kind: 'report', target: { name: 'Ivan', noPosition: true } })
    await flushPromises()
    submit(form())
    await flushPromises()
    expect(store.reportFire).not.toHaveBeenCalled()
    w.unmount()
  })

  it('a stale answer of an earlier dialog does not close the present one [T508]', async () => {
    const { w, store, ui } = setup()
    let rejectFirst
    store.reportFire = vi.fn(() => new Promise((_, reject) => { rejectFirst = reject }))
    ui.openDialog(REPORT(1, 2))
    await flushPromises()
    submit(form())
    await flushPromises()
    expect(store.reportFire).toHaveBeenCalledTimes(1)
    // The operator opens another dialog while the first request is in flight.
    const second = REPORT(3, 4)
    ui.openDialog(second)
    await flushPromises()
    rejectFirst(new ApiError('boom', 500))
    await flushPromises()
    expect(ui.dialog).toEqual(second)
    expect(document.querySelector('[data-testid="fr-error"]')).toBeNull()   // the old error is not shown
    expect(document.querySelector('[data-testid="fr-submit"]').disabled).toBe(false)   // and the new one is not busy
    w.unmount()
  })

  it('a failed report keeps the dialog open and shows the error [T508]', async () => {
    const { w, store, ui } = setup()
    store.reportFire = vi.fn(async () => { throw new ApiError('nope', 500) })
    ui.openDialog(REPORT())
    await flushPromises()
    submit(form())
    await flushPromises()
    expect(ui.dialog).not.toBeNull()
    expect(document.querySelector('[data-testid="fr-error"]')).not.toBeNull()
    w.unmount()
  })

  it('a zone dialog creates the zone at its target and shows the zones layer [T508]', async () => {
    const { w, store, ui } = setup()
    store.createZone = vi.fn(async () => {})
    ui.openDialog({ kind: 'zone', target: { latitude: 42.5, longitude: 24.5 } })
    await flushPromises()
    const z = document.querySelector('[data-testid="zone-form"]')
    expect(z.querySelector('[data-testid="zone-point"]').textContent).toBe('42.50000, 24.50000')
    const label = z.querySelector('[data-testid="zone-label"]')
    label.value = 'Solar farm'
    label.dispatchEvent(new Event('input'))
    submit(z)
    await flushPromises()
    expect(store.createZone).toHaveBeenCalledWith(expect.objectContaining({ label: 'Solar farm', latitude: 42.5, longitude: 24.5 }))
    expect(ui.dialog).toBeNull()
    expect(store.setLayer).toHaveBeenCalledWith('zones', true)
    w.unmount()
  })

  it('opening a dialog closes the context menu [T508]', async () => {
    const { w, ui, context } = setup()
    expect(context.closeContextMenu).not.toHaveBeenCalled()
    ui.openDialog(REPORT())
    await flushPromises()
    expect(context.closeContextMenu).toHaveBeenCalledTimes(1)
    w.unmount()
  })
})
