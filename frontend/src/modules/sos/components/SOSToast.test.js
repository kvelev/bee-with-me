import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent, h, nextTick } from 'vue'

vi.mock('../../../api', () => ({
  getLivePositions: vi.fn(), getTrail: vi.fn(), getOpenSOS: vi.fn(), resolveSOS: vi.fn(async () => ({})),
}))

import { i18n } from '../../../i18n/index.js'
import PanelHost from '../../../platform/PanelHost.vue'
import sos from '../index.js'
import { useSosStore } from '../store.js'
import SOSToast from './SOSToast.vue'

let pinia
let wrapper

const notify = (store, id, name) => store.sosNotifications.push({ id, device_id: `d${id}`, name, timestamp: new Date().toISOString() })
const toasts = () => [...document.body.querySelectorAll('.sos-toast')]

beforeEach(() => {
  pinia = createPinia()
  setActivePinia(pinia)
  document.body.innerHTML = ''
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('SOSToast', () => {
  it('shows the newest notification with its name and removes it after 10 s [T545]', async () => {
    vi.useFakeTimers()
    const store = useSosStore()
    wrapper = mount(SOSToast, { global: { plugins: [pinia, i18n] } })
    notify(store, 1, 'Ivan Petrov')
    await nextTick()
    expect(toasts()).toHaveLength(1)
    expect(toasts()[0].querySelector('.sos-toast-name').textContent).toBe('Ivan Petrov')

    vi.advanceTimersByTime(9999)
    expect(store.sosNotifications).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(store.sosNotifications).toHaveLength(0)

    notify(store, 2, 'Maria')
    await nextTick()
    expect(toasts().at(-1).querySelector('.sos-toast-name').textContent).toBe('Maria')
  })

  it('the root element carries no context attribute [T545]', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const store = useSosStore()
    notify(store, 1, 'Ivan')
    wrapper = mount(SOSToast, { props: { context: { who: 'map' } }, global: { plugins: [pinia, i18n] } })
    await nextTick()
    expect(wrapper.vm.$attrs.context).toBeUndefined()
    expect(document.body.querySelector('[context]')).toBeNull()
    expect(warn.mock.calls.flat().join(' ')).not.toContain('Extraneous non-props')
  })

  it('after a render error the next notification is shown again [T545]', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    let thrown = false
    const Flaky = defineComponent({
      props: ['context'],
      render() {
        if (!thrown) { thrown = true; throw new Error('boom') }
        return h(SOSToast, { context: this.context })
      },
    })
    const panel = sos.panels.find((p) => p.id === 'sos-toast')
    const store = useSosStore()
    wrapper = mount(PanelHost, {
      props: { panels: [{ ...panel, component: Flaky }], context: {} },
      global: { plugins: [pinia, i18n] },
    })
    await flushPromises()
    expect(toasts()).toHaveLength(0)

    notify(store, 1, 'Ivan')
    await flushPromises()
    expect(toasts()).toHaveLength(1)
    expect(toasts()[0].querySelector('.sos-toast-name').textContent).toBe('Ivan')
  })

  describe('alarm and auto-dismiss on mount [B107]', () => {
    let audioCount
    const stubAudio = () => {
      audioCount = 0
      vi.stubGlobal('AudioContext', class {
        constructor() { audioCount += 1; this.currentTime = 0; this.destination = {} }
        createGain() { return { connect() {}, gain: { setValueAtTime() {}, exponentialRampToValueAtTime() {} } } }
        createOscillator() { return { connect() {}, frequency: { setValueAtTime() {} }, start() {}, stop() {} } }
      })
    }
    afterEach(() => { vi.unstubAllGlobals() })

    it('a toast mounted after a render retry sounds the alarm and auto-dismisses [B107]', async () => {
      vi.useFakeTimers()
      stubAudio()
      vi.spyOn(console, 'error').mockImplementation(() => {})
      let thrown = false
      const Flaky = defineComponent({
        props: ['context'],
        render() {
          if (!thrown) { thrown = true; throw new Error('boom') }
          return h(SOSToast, { context: this.context })
        },
      })
      const panel = sos.panels.find((p) => p.id === 'sos-toast')
      const store = useSosStore()
      wrapper = mount(PanelHost, {
        props: { panels: [{ ...panel, component: Flaky }], context: {} },
        global: { plugins: [pinia, i18n] },
      })
      await flushPromises()

      notify(store, 1, 'Ivan')
      await flushPromises()
      expect(toasts()).toHaveLength(1)
      expect(audioCount).toBe(1)

      vi.advanceTimersByTime(10000)
      expect(store.sosNotifications).toHaveLength(0)
    })

    it('a notification already announced is not announced again after unmount and mount [B107]', async () => {
      vi.useFakeTimers()
      stubAudio()
      const store = useSosStore()
      notify(store, 1, 'Ivan')
      const first = mount(SOSToast, { global: { plugins: [pinia, i18n] } })
      await nextTick()
      expect(audioCount).toBe(1)
      first.unmount()

      wrapper = mount(SOSToast, { global: { plugins: [pinia, i18n] } })
      await nextTick()
      expect(audioCount).toBe(1)
    })
  })
})
