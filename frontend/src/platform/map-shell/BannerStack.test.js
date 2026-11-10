import { describe, it, expect, vi, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { h, ref, nextTick } from 'vue'

vi.mock('../../api', () => ({ getMe: vi.fn(), login: vi.fn(), getFireAlerts: vi.fn().mockResolvedValue([]) }))

import BannerStack from './BannerStack.vue'
import AppLayout from '../../components/AppLayout.vue'
import { LEGACY_BANNERS } from '../../components/legacyBanners.js'
import { collectBanners, contributionProblems } from './contributions.js'
import { MODULES } from '../../modules/index.js'
import { useAuthStore } from '../../stores/auth'
import { i18n } from '../../i18n/index.js'

const stub = (cls) => ({ render: () => h('div', { class: cls }) })

afterEach(() => { vi.restoreAllMocks() })

describe('BannerStack', () => {
  it('renders banners in the given order without a wrapper [T421]', () => {
    const host = document.createElement('div')
    const w = mount(BannerStack, {
      attachTo: host,
      props: { banners: [{ id: 'a', priority: 10, component: stub('a') }, { id: 'b', priority: 20, component: stub('b') }] },
    })
    const html = w.html()
    expect([...host.firstElementChild.children].map((e) => e.className)).toEqual(['a', 'b'])
    expect(html.indexOf('class="a"')).toBeGreaterThan(-1)
    expect(html.indexOf('class="a"')).toBeLessThan(html.indexOf('class="b"'))
  })

  it('the legacy list puts SOS above fire and has no problem [T421]', () => {
    expect(collectBanners([], LEGACY_BANNERS).map((b) => b.id)).toEqual(['sos', 'fire-alarm'])
    expect(contributionProblems(MODULES, { banners: LEGACY_BANNERS })).toEqual([])
  })

  it('a module banner with priority 15 lands between them [T421]', () => {
    const m = { name: 'x', banners: [{ id: 'x', priority: 15, component: stub('x') }] }
    expect(collectBanners([m], LEGACY_BANNERS).map((b) => b.id)).toEqual(['sos', 'x', 'fire-alarm'])
  })

  it('a banner that throws while rendering is skipped and logged, and SOS stays [T421]', async () => {
    const err = vi.spyOn(console, 'error').mockImplementation(() => {})
    const boom = { render() { throw new Error('boom') } }
    const banners = [
      { id: 'sos', priority: 10, component: stub('sos') },
      { id: 'x', priority: 15, component: boom },
      { id: 'fire-alarm', priority: 20, component: stub('fire') },
    ]
    const w = mount(BannerStack, { props: { banners } })
    await w.vm.$nextTick()
    expect(w.html()).toContain('class="sos"')
    expect(w.html()).toContain('class="fire"')
    expect(w.html()).not.toContain('boom')
    const calls = err.mock.calls.filter((c) => String(c[0]).includes('x'))
    expect(calls.length).toBe(1)
    expect(String(calls[0][0])).toContain('banner x failed')

    await w.setProps({ banners: [...banners] })
    await w.vm.$forceUpdate()
    await w.vm.$nextTick()
    expect(err.mock.calls.filter((c) => String(c[0]).includes('x')).length).toBe(1)
    expect(w.html()).toContain('class="sos"')
  })

  describe('error recovery [T421]', () => {
    // A banner whose render fails while `n` is below `okAt`, so changing its own reactive data heals it.
    const flaky = (n, okAt, msg = 'boom') => ({
      render() {
        if (n.value < okAt) throw new Error(msg)
        return h('div', { class: 'ok' })
      },
    })

    it('a non-SOS banner that fails on first render recovers when its reactive data changes [T421]', async () => {
      const err = vi.spyOn(console, 'error').mockImplementation(() => {})
      const n = ref(0)
      const banners = [{ id: 'sos', priority: 10, component: stub('sos') }, { id: 'x', priority: 15, component: flaky(n, 1) }]
      const w = mount(BannerStack, { props: { banners } })
      await nextTick()
      expect(w.html()).not.toContain('class="ok"')
      expect(w.html()).toContain('class="sos"')
      n.value = 1
      await nextTick()
      expect(w.html()).toContain('class="ok"')
      expect(err.mock.calls.filter((c) => String(c[0]) === 'banner x failed').length).toBe(1)
    })

    it('an error raised during an update (not first render) is caught and later healed [T421]', async () => {
      const err = vi.spyOn(console, 'error').mockImplementation(() => {})
      const n = ref(1)
      const comp = { render() { if (n.value === 2) throw new Error('late'); return h('div', { class: 'ok' }) } }
      const w = mount(BannerStack, { props: { banners: [{ id: 'x', priority: 1, component: comp }, { id: 'y', priority: 2, component: stub('y') }] } })
      expect(w.html()).toContain('class="ok"')
      n.value = 2
      await nextTick()
      expect(w.html()).not.toContain('class="ok"')
      expect(w.html()).toContain('class="y"')
      expect(err.mock.calls.length).toBe(1)
      n.value = 3
      await nextTick()
      expect(w.html()).toContain('class="ok"')
    })

    it('SOS is never latched: a single failure is followed by a normal render on the next update [T421]', async () => {
      const err = vi.spyOn(console, 'error').mockImplementation(() => {})
      const n = ref(0)
      const w = mount(BannerStack, { props: { banners: [{ id: 'sos', priority: 10, component: flaky(n, 1, 'bad alert') }] } })
      await nextTick()
      expect(w.html()).not.toContain('class="ok"')
      n.value = 1
      await nextTick()
      expect(w.html()).toContain('class="ok"')
      expect(err.mock.calls.filter((c) => String(c[0]) === 'banner sos failed').length).toBe(1)
    })

    it('the same error is logged once per window, a different error is logged at once [T421]', async () => {
      const err = vi.spyOn(console, 'error').mockImplementation(() => {})
      const n = ref(0)
      const msg = ref('same')
      const comp = { render() { n.value; throw new Error(msg.value) } }
      mount(BannerStack, { props: { banners: [{ id: 'x', priority: 1, component: comp }, { id: 'y', priority: 2, component: stub('y') }] } })
      await nextTick()
      for (let i = 1; i <= 3; i++) { n.value = i; await nextTick() }
      expect(err.mock.calls.length).toBe(1)
      msg.value = 'other'
      n.value = 10
      await nextTick()
      expect(err.mock.calls.length).toBe(2)
    })

    it('a banner that always throws is retried every 5 s, logged once per retry, and never takes the page down [T421]', async () => {
      vi.useFakeTimers()
      try {
        const err = vi.spyOn(console, 'error').mockImplementation(() => {})
        const comp = { render() { throw new Error('always') } }
        const w = mount(BannerStack, { props: { banners: [{ id: 'x', priority: 1, component: comp }, { id: 'y', priority: 2, component: stub('y') }] } })
        await nextTick()
        expect(err.mock.calls.length).toBe(1)
        await vi.advanceTimersByTimeAsync(4900)
        expect(err.mock.calls.length).toBe(1)
        await vi.advanceTimersByTimeAsync(200)
        expect(err.mock.calls.length).toBe(2)
        await vi.advanceTimersByTimeAsync(5100)
        expect(err.mock.calls.length).toBe(3)
        expect(w.html()).toContain('class="y"')
        w.unmount()
        await vi.advanceTimersByTimeAsync(20000)
        expect(err.mock.calls.length).toBe(3)
      } finally { vi.useRealTimers() }
    })

    it('a banner that failed once is remounted by the retry timer even without reactive data [T421]', async () => {
      vi.useFakeTimers()
      try {
        vi.spyOn(console, 'error').mockImplementation(() => {})
        let fail = true
        const comp = { render() { if (fail) throw new Error('once'); return h('div', { class: 'ok' }) } }
        const w = mount(BannerStack, { props: { banners: [{ id: 'x', priority: 1, component: comp }] } })
        await nextTick()
        expect(w.html()).not.toContain('class="ok"')
        fail = false
        await vi.advanceTimersByTimeAsync(5100)
        expect(w.html()).toContain('class="ok"')
      } finally { vi.useRealTimers() }
    })
  })

  it('the layout shows SOS above the fire alarm [T421]', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    useAuthStore().user = { role: 'admin', full_name: 'Test' }
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<i />' } }] })
    router.push('/')
    await router.isReady()
    const w = mount(AppLayout, {
      global: { plugins: [pinia, i18n, router], stubs: { SOSBanner: true, FireAlarmBanner: true, RouterView: true } },
    })
    const main = w.find('.main-content')
    const html = main.html()
    expect(html).toContain('s-o-s-banner-stub')
    expect(html.indexOf('s-o-s-banner-stub')).toBeLessThan(html.indexOf('fire-alarm-banner-stub'))
  })
})
