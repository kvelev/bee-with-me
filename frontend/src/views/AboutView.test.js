import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises } from '@vue/test-utils'

vi.mock('../api', () => ({}))

import AboutView from './AboutView.vue'
import { useAuthStore } from '../stores/auth'
import { i18n } from '../i18n/index.js'
import en from '../i18n/en.js'
import bg from '../i18n/bg.js'

async function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { role: 'viewer' }
  const w = mount(AboutView, { global: { plugins: [pinia, i18n] } })
  await flushPromises()
  return w
}

describe('AboutView contacts', () => {
  beforeEach(() => { i18n.global.locale.value = 'en' })

  it('each contact has a tel: link without spaces and a mailto: link [ABOUT]', async () => {
    const w = await mountView()
    const people = w.findAll('.contact')
    expect(people).toHaveLength(3)
    for (const p of people) {
      const tel = p.find('a[href^="tel:"]')
      expect(tel.attributes('href')).toMatch(/^tel:\+359\d{9}$/)
      expect(tel.text()).toMatch(/^\+359 \d{3} \d{3} \d{3}$/)
      expect(tel.text().replace(/\s/g, '')).toBe(tel.attributes('href').slice(4))
      expect(p.find('a[href^="mailto:"]').exists()).toBe(true)
    }
    expect(w.find('a[href="tel:+359877389417"]').attributes('aria-label')).toBe('Call Konstantin Velev, +359 877 389 417')
    expect(w.text()).toContain('Kiril Iliev')
    expect(w.text()).not.toContain('ILIEV')
  })

  it('labels come from i18n in en and bg [ABOUT]', async () => {
    const w = await mountView()
    expect(w.find('dt').text()).toBe(en.about.phone)
    expect(w.findAll('dt')[1].text()).toBe(en.about.email)
    i18n.global.locale.value = 'bg'
    await flushPromises()
    expect(w.find('dt').text()).toBe(bg.about.phone)
    expect(w.findAll('dt')[1].text()).toBe(bg.about.email)
    expect(bg.about.phone).not.toBe(en.about.phone)
    expect(w.find('a[href^="tel:"]').attributes('aria-label')).toContain('Обади се на')
  })
})

describe('AboutView download', () => {
  beforeEach(() => { i18n.global.locale.value = 'en' })

  it('offers stable (main) and latest (develop) straight from GitHub', async () => {
    const w = await mountView()
    const stable = w.get('[data-testid="download-stable"]')
    const latest = w.get('[data-testid="download-latest"]')
    expect(stable.attributes('href')).toBe('https://github.com/kvelev/bee-with-me/archive/refs/heads/main.zip')
    expect(latest.attributes('href')).toBe('https://github.com/kvelev/bee-with-me/archive/refs/heads/develop.zip')
    for (const a of [stable, latest]) {
      expect(a.attributes('target')).toBe('_blank')
      expect(a.attributes('rel')).toContain('noopener')
    }
    expect(stable.text()).toBe(en.about.download.stable)
    expect(w.get('[data-testid="download"] a[href$="/releases/latest"]').exists()).toBe(true)
  })

  it('shows the real app version, not a hardcoded one', async () => {
    const pkg = await import('../../package.json')
    const w = await mountView()
    expect(w.get('[data-testid="app-version"]').text()).toBe('v' + pkg.version)
  })

  it('has the download strings in both languages', () => {
    expect(Object.keys(bg.about.download).sort()).toEqual(Object.keys(en.about.download).sort())
  })
})
