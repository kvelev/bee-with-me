import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'

vi.mock('../../../api', () => ({
  getFireHotspots: vi.fn(), getFireBurntAreas: vi.fn(), getFireStatus: vi.fn(),
  getFireAlerts: vi.fn(), acknowledgeFireAlert: vi.fn(), acknowledgeAllFireAlerts: vi.fn(),
}))
vi.mock('../lib/fireTone', async (orig) => ({
  ...(await orig()),
  playFireTone: vi.fn(() => 'running'),
  toneState: vi.fn(() => 'running'),
  unlockFireTone: vi.fn(async () => 'running'),
}))

import { acknowledgeFireAlert } from '../../../api'
import { playFireTone, toneState, unlockFireTone } from '../lib/fireTone'
import FireAlarmBanner from './FireAlarmBanner.vue'
import { useFireStore } from '../store.js'
import { i18n } from '../../../i18n/index.js'
import en from '../../../i18n/en.js'
import bg from '../../../i18n/bg.js'

const alert = (id, extra = {}) => ({
  id, target_type: 'device', device_id: 'd1', full_name: 'Ivan Petrov', rank: 'Sergeant', distance_m: 1234,
  hotspot: { id: `h-${id}`, latitude: 42.5, longitude: 24.5, acquired_at: new Date(Date.now() - 12.5 * 60_000).toISOString(), source: 'viirs' },
  triggered_at: new Date().toISOString(), acknowledged_at: null, resolved_at: null, resolve_reason: null, ...extra,
})

// Mounted wrappers are attached to the document: jsdom 31 does not apply styles to detached
// elements, so isVisible() on a v-show element would otherwise always report true.
const mounted = []
afterEach(() => { while (mounted.length) { try { mounted.pop().unmount() } catch { /* already unmounted */ } } })

async function mountBanner() {
  const pinia = createPinia()
  setActivePinia(pinia)
  const page = { template: '<i />' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/map', component: page }, { path: '/', component: page }],
  })
  router.push('/'); await router.isReady()
  const w = mount(FireAlarmBanner, { attachTo: document.body, global: { plugins: [pinia, i18n, router] } })
  mounted.push(w)
  return { w, fire: useFireStore(), router }
}

describe('FireAlarmBanner', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    i18n.global.locale.value = 'en'
    toneState.mockReturnValue('running')
    playFireTone.mockReturnValue('running')
  })

  it('renders nothing without alerts [T17]', async () => {
    const { w } = await mountBanner()
    expect(w.find('.fire-banner').exists()).toBe(false)
  })

  it('says who, how far and how old the detection is [T17]', async () => {
    const { w, fire } = await mountBanner()
    fire.applyFireAlert(alert('a1'))
    await flushPromises()
    const text = w.text()
    expect(text).toContain('Ivan Petrov')
    expect(text).toContain('Sergeant')
    expect(w.find('.fb-distance').text()).toBe('1.2 km')
    expect(text).toContain('12 min ago')
    expect(w.find('.fire-banner').attributes('role')).toBe('alert')
  })

  it('HQ alerts say HQ, and Bulgarian uses its own text and decimal comma [T17]', async () => {
    i18n.global.locale.value = 'bg'
    const { w, fire } = await mountBanner()
    fire.applyFireAlert(alert('a1', { target_type: 'hq', full_name: null, rank: null }))
    await flushPromises()
    expect(w.find('.fb-name').text()).toBe(bg.fireAlarm.hq)
    expect(w.find('.fb-distance').text()).toBe('1,2 км')
  })

  it('an acknowledged alert stays listed, quiet, and the banner leaves alarm state [T17]', async () => {
    const { w, fire } = await mountBanner()
    fire.applyFireAlert(alert('a1'))
    acknowledgeFireAlert.mockResolvedValue(alert('a1', { acknowledged_at: 'now' }))
    await flushPromises()
    await w.find('.fb-btn-main').trigger('click')
    await flushPromises()
    await w.find('.fb-toggle').trigger('click')       // acknowledged rows are collapsed by default
    expect(w.findAll('.fb-row')).toHaveLength(1)
    expect(w.find('.fb-row-acked').exists()).toBe(true)
    expect(w.find('.fire-banner-live').exists()).toBe(false)
    expect(w.find('.fire-banner').attributes('role')).toBe('region')
    expect(w.text()).toContain(en.fireAlarm.acknowledged)
  })

  it('acknowledge all only appears with more than one open alert [T17]', async () => {
    const { w, fire } = await mountBanner()
    fire.applyFireAlert(alert('a1'))
    await flushPromises()
    expect(w.text()).not.toContain(en.fireAlarm.acknowledgeAll)
    fire.applyFireAlert(alert('a2'))
    await flushPromises()
    expect(w.text()).toContain(en.fireAlarm.acknowledgeAll)
  })

  it('a failed acknowledge says so and keeps the alarm [T17]', async () => {
    const { w, fire } = await mountBanner()
    fire.applyFireAlert(alert('a1'))
    acknowledgeFireAlert.mockRejectedValue(new Error('Network Error'))
    await flushPromises()
    await w.find('.fb-btn-main').trigger('click')
    await flushPromises()
    expect(w.find('.fb-error').text()).toContain('Network Error')
    expect(w.find('.fire-banner-live').exists()).toBe(true)
  })

  it('plays one tone per ring and none for restored alerts [T17]', async () => {
    const { w, fire } = await mountBanner()
    fire.alerts = [alert('a1')]            // restored: no ring
    await flushPromises()
    expect(playFireTone).not.toHaveBeenCalled()
    fire.applyFireAlertRepeat({ alert_ids: ['a1'] })
    await flushPromises()
    expect(playFireTone).toHaveBeenCalledTimes(1)
    expect(w.find('.fb-sound').exists()).toBe(false)
  })

  it('shows "Sound blocked" visibly and plays the missed ring after the click [T17]', async () => {
    toneState.mockReturnValue('blocked')
    playFireTone.mockReturnValueOnce('blocked')
    const { w, fire } = await mountBanner()
    fire.applyFireAlert(alert('a1'))
    await flushPromises()
    expect(w.find('.fb-sound').text()).toBe(en.fireAlarm.soundBlocked)
    await w.find('.fb-sound').trigger('click')
    await flushPromises()
    expect(unlockFireTone).toHaveBeenCalled()
    expect(playFireTone).toHaveBeenCalledTimes(2)   // the blocked attempt, then once after the click
    expect(w.find('.fb-sound').exists()).toBe(false)
  })

  it('show on map requests focus on the hotspot and goes to the map [T17]', async () => {
    const { w, fire, router } = await mountBanner()
    fire.applyFireAlert(alert('a1'))
    await flushPromises()
    await w.findAll('.fb-btn').find(b => b.text() === en.fireAlarm.showOnMap).trigger('click')
    await flushPromises()
    expect(fire.focusRequest).toMatchObject({ latitude: 42.5, longitude: 24.5 })
    expect(router.currentRoute.value.path).toBe('/map')
  })

  it('shows a notice when the alarms could not be loaded [T17]', async () => {
    const { w, fire } = await mountBanner()
    fire.alertsFailed = true
    await flushPromises()
    expect(w.find('.fb-loadfail').text()).toBe(en.fireAlarm.loadFailed)
  })
  it('says how many alerts are not shown, in both languages, and does not ring on a reset [B43]', async () => {
    const { w, fire } = await mountBanner()
    fire.applyFireAlert(alert('a1'))
    fire.alertsHidden = 1
    await flushPromises()
    expect(w.find('.fb-hidden').text()).toBe(en.fireAlarm.moreHidden.split(' | ')[0])
    fire.alertsHidden = 7
    await flushPromises()
    expect(w.find('.fb-hidden').text()).toBe('7 more alerts are not shown')
    i18n.global.locale.value = 'bg'
    await flushPromises()
    expect(w.find('.fb-hidden').text()).toBe('още 7 аларми не са показани')
    expect(bg.fireAlarm.moreHidden).toContain('|')
    playFireTone.mockClear()
    fire.resetAlerts()
    await flushPromises()
    expect(playFireTone).not.toHaveBeenCalled()
    expect(w.find('.fb-hidden').exists()).toBe(false)
  })
})

describe('FireAlarmBanner acknowledged section', () => {
  const KEY = 'bwm.fireAlarm.ackCollapsed'
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    vi.restoreAllMocks()
    i18n.global.locale.value = 'en'
    toneState.mockReturnValue('running')
    playFireTone.mockReturnValue('running')
  })
  const acked = (id, extra = {}) => alert(id, { acknowledged_at: new Date().toISOString(), ...extra })

  it('unacknowledged alerts have no collapse control and always show in full [COLLAPSE]', async () => {
    const { w, fire } = await mountBanner()
    fire.applyFireAlert(alert('a1'))
    fire.applyFireAlert(alert('a2'))
    await flushPromises()
    expect(w.find('.fb-toggle').exists()).toBe(false)
    expect(w.findAll('.fb-row').every(r => r.isVisible())).toBe(true)
    expect(w.text()).toContain(en.fireAlarm.acknowledgeAll)
    expect(w.findAll('.fb-btn-main').length).toBeGreaterThan(2)
    expect(w.find('.fire-banner-live').exists()).toBe(true)
  })

  it('acknowledged alerts are collapsed by default with the right count, plural in both languages [COLLAPSE]', async () => {
    const { w, fire } = await mountBanner()
    fire.alerts = [acked('a1'), acked('a2'), acked('a3')]
    await flushPromises()
    const toggle = w.find('.fb-toggle')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(toggle.attributes('aria-controls')).toBe('fb-ack-list')
    expect(w.find('#fb-ack-list').exists()).toBe(true)
    expect(w.find('#fb-ack-list').isVisible()).toBe(false)
    expect(toggle.text()).toContain('3 acknowledged fire alerts')
    expect(toggle.text()).toContain(en.fireAlarm.ackedShow)
    expect(toggle.element.tagName).toBe('BUTTON')
    // quiet: no live styling, no stripe, no alert role, no unack controls
    expect(w.find('.fire-banner-live').exists()).toBe(false)
    expect(w.find('.fb-stripe').exists()).toBe(false)
    expect(w.find('.fire-banner').attributes('role')).toBe('region')
    fire.alerts = [acked('a1')]
    await flushPromises()
    expect(w.find('.fb-toggle').text()).toContain('1 acknowledged fire alert')
    expect(w.find('.fb-toggle').text()).not.toContain('alerts')
    i18n.global.locale.value = 'bg'
    fire.alerts = [acked('a1'), acked('a2')]
    await flushPromises()
    expect(w.find('.fb-toggle').text()).toContain('2 потвърдени пожарни аларми')
    expect(bg.fireAlarm.ackedShow).toBeTruthy()
    expect(bg.fireAlarm.ackedHide).toBeTruthy()
  })

  it('the toggle expands and collapses the list and the choice persists [COLLAPSE]', async () => {
    const first = await mountBanner()
    first.fire.alerts = [acked('a1'), acked('a2')]
    await flushPromises()
    await first.w.find('.fb-toggle').trigger('click')
    expect(first.w.find('.fb-toggle').attributes('aria-expanded')).toBe('true')
    expect(first.w.find('#fb-ack-list').isVisible()).toBe(true)
    expect(first.w.findAll('.fb-row-acked')).toHaveLength(2)
    expect(first.w.find('.fb-toggle').text()).toContain(en.fireAlarm.ackedHide)
    expect(localStorage.getItem(KEY)).toBe('0')
    first.w.unmount()

    const second = await mountBanner()               // a new page load remembers it
    second.fire.alerts = [acked('a1')]
    await flushPromises()
    expect(second.w.find('.fb-toggle').attributes('aria-expanded')).toBe('true')
    await second.w.find('.fb-toggle').trigger('click')
    expect(second.w.find('#fb-ack-list').isVisible()).toBe(false)
    expect(localStorage.getItem(KEY)).toBe('1')
  })

  it('works when storage is blocked [COLLAPSE]', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    const { w, fire } = await mountBanner()
    fire.alerts = [acked('a1')]
    await flushPromises()
    expect(w.find('.fb-toggle').attributes('aria-expanded')).toBe('false')
    await w.find('.fb-toggle').trigger('click')
    expect(w.find('.fb-toggle').attributes('aria-expanded')).toBe('true')
    expect(w.find('#fb-ack-list').isVisible()).toBe(true)
  })

  it('a new unacknowledged alert shows in full while acknowledged ones stay collapsed [COLLAPSE]', async () => {
    const { w, fire } = await mountBanner()
    fire.alerts = [acked('a1'), acked('a2')]
    await flushPromises()
    expect(w.find('.fire-banner-live').exists()).toBe(false)
    fire.applyFireAlert(alert('n1', { full_name: 'Maria Georgieva' }))
    await flushPromises()
    expect(w.find('.fire-banner-live').exists()).toBe(true)
    expect(w.find('.fire-banner').attributes('role')).toBe('alert')
    const live = w.findAll('.fb-row').filter(r => !r.classes('fb-row-acked'))
    expect(live).toHaveLength(1)
    expect(live[0].isVisible()).toBe(true)
    expect(live[0].text()).toContain('Maria Georgieva')
    expect(live[0].text()).toContain(en.fireAlarm.acknowledge)
    expect(w.find('.fb-toggle').attributes('aria-expanded')).toBe('false')
    expect(w.find('#fb-ack-list').isVisible()).toBe(false)
  })

  it('the sound-blocked button shows only while something is unacknowledged [COLLAPSE]', async () => {
    toneState.mockReturnValue('blocked')
    playFireTone.mockReturnValueOnce('blocked')
    const { w, fire } = await mountBanner()
    fire.alerts = [acked('a1')]
    await flushPromises()
    expect(w.find('.fb-sound').exists()).toBe(false)
    fire.applyFireAlert(alert('n1'))
    await flushPromises()
    expect(w.find('.fb-sound').exists()).toBe(true)
  })
})
