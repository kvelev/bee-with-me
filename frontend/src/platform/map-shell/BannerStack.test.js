import { describe, it, expect, vi, afterEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { createRouter, createMemoryHistory } from 'vue-router'
import { h } from 'vue'

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
