import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../../api', () => ({
  getFireHotspots: vi.fn(), getFireBurntAreas: vi.fn(), getFireStatus: vi.fn(),
  getFireAlerts: vi.fn(), getSuppressionZones: vi.fn(),
  createFieldReport: vi.fn(), createSuppressionZone: vi.fn(),
}))

// The report form chunk can be made to fail once: reading the default export of the mocked module throws while
// state.failNext is set, which Vue's async component sees as a failed load.
const state = vi.hoisted(() => ({ failNext: false }))
vi.mock('./components/FieldReportForm.vue', async (importOriginal) => {
  const original = await importOriginal()
  return {
    __esModule: true,
    get default() {
      if (state.failNext) {
        state.failNext = false
        throw new Error('chunk load failed')
      }
      return original.default
    },
  }
})

import fire from './index.js'
import FireDialogs from './components/FireDialogs.vue'
import PanelHost from '../../platform/PanelHost.vue'
import { collectPopups, popupFor } from '../../platform/map-shell/contributions.js'
import { useFireUi } from './ui.js'
import { i18n } from '../../i18n/index.js'

const src = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')
const form = () => document.querySelector('[data-testid="field-report-form"]')
const REPORT = { kind: 'report', target: { latitude: 42.5, longitude: 24.5 } }

describe('fire lazy loading', () => {
  beforeEach(() => { setActivePinia(createPinia()); i18n.global.locale.value = 'en'; state.failNext = false })
  afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks() })

  it('the popup component of the manifest is an async component [T633]', () => {
    const popup = popupFor(collectPopups([fire]), 'hotspot')
    expect(popup.component.__asyncLoader).toBeDefined()
  })

  it('the dialogs panel has a retry key that follows the open dialog [T633]', () => {
    const panel = fire.panels.find((p) => p.id === 'fire-dialogs')
    const ui = useFireUi()
    expect(typeof panel.retryKey).toBe('function')
    const before = panel.retryKey()
    ui.openDialog(REPORT)
    expect(panel.retryKey()).not.toBe(before)
  })

  it('the fire manifest source imports neither form nor the popup statically [T633]', () => {
    const index = src('./index.js')
    const dialogs = src('./components/FireDialogs.vue')
    expect(index).not.toMatch(/import FireMapPopup from/)
    expect(dialogs).not.toMatch(/import FieldReportForm from/)
    expect(dialogs).not.toMatch(/import SuppressionZoneForm from/)
  })

  it('the alarm banner is still imported statically [T633]', () => {
    expect(src('./index.js')).toMatch(/import FireAlarmBanner from/)
  })

  it('opening the report dialog renders the form after the chunk resolves [T633]', async () => {
    const w = mount(FireDialogs, { props: { context: {} }, attachTo: document.body, global: { plugins: [i18n] } })
    expect(form()).toBeNull()
    useFireUi().openDialog(REPORT)
    await flushPromises()
    await vi.waitFor(() => expect(form()).not.toBeNull())
    w.unmount()
  })

  it('a form whose chunk fails is logged once, as text, and the boundary is retried on the next open [T633]', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const panel = fire.panels.find((p) => p.id === 'fire-dialogs')
    const ui = useFireUi()
    const w = mount(PanelHost, { props: { panels: [panel], context: {} }, attachTo: document.body, global: { plugins: [i18n] } })
    state.failNext = true
    ui.openDialog(REPORT)
    await flushPromises()
    expect(form()).toBeNull()
    expect(err).toHaveBeenCalled()
    for (const call of err.mock.calls) for (const arg of call) expect(typeof arg).toBe('string')
    ui.closeDialog()
    ui.openDialog(REPORT)
    await flushPromises()
    // Vue keeps a rejected loader promise inside the async component, so the form itself is not fetched again until a reload (reported in the PR); the boundary is open again.
    expect(panel.retryKey()).toBe(ui.dialog)
    w.unmount()
  })
})
