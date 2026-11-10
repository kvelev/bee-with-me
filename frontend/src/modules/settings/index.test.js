import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../../api', () => ({ getMe: vi.fn(), login: vi.fn() }))

import bgFull from '../../i18n/bg.js'
import enFull from '../../i18n/en.js'
import { NAV_ITEMS } from '../../nav-config.js'
import { validateManifest } from '../../platform/manifest.js'
import router, { guard } from '../../router/index.js'
import { useAuthStore } from '../../stores/auth'
import manifest from './index.js'

describe('settings module', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('token', 'x')
    setActivePinia(createPinia())
  })

  it('the settings manifest is valid and admin-only [T404]', () => {
    expect(validateManifest(manifest)).toEqual([])
    expect(manifest.name).toBe('settings')
    expect(manifest.routes).toHaveLength(1)
    expect(manifest.routes[0].name).toBe('settings')
    expect(manifest.routes[0].path).toBe('/settings')
    expect(manifest.routes[0].meta.adminOnly).toBe(true)
    expect(manifest.nav).toHaveLength(1)
    expect(manifest.nav[0].order).toBe(70)
    expect(manifest.nav[0].adminOnly).toBe(true)
  })

  it('the navigation shows settings once, admin-only, between the offline map and about [T404]', () => {
    const items = NAV_ITEMS.filter((i) => i.to === '/settings')
    expect(items).toHaveLength(1)
    expect(items[0].adminOnly).toBe(true)
    const order = NAV_ITEMS.map((i) => i.to)
    expect(order.indexOf('/settings')).toBe(order.indexOf('/selectofflinemap') + 1)
    expect(order.indexOf('/about')).toBe(order.indexOf('/settings') + 1)
  })

  it('the real router keeps /settings admin-only [T404]', async () => {
    const to = router.resolve('/settings')
    expect(to.matched.length).toBe(2)
    expect(to.name).toBe('settings')
    expect(to.meta.adminOnly).toBe(true)
    useAuthStore().user = { role: 'viewer' }
    expect(await guard(to)).toBe('/map')
    useAuthStore().user = { role: 'admin' }
    expect(await guard(to)).toBeUndefined()
  })

  it('the old store path is the same object as the module store [T404]', async () => {
    const old = await import('../../stores/settings.js')
    const now = await import('./store.js')
    expect(old.useSettingsStore).toBe(now.useSettingsStore)
    expect(old.isTransientFailure).toBe(now.isTransientFailure)
  })

  it('the settings texts are in the merged dictionaries [T404]', () => {
    for (const d of [enFull, bgFull]) expect(d.settings.title).toBeTruthy()
    expect(enFull.settings.title).not.toBe(bgFull.settings.title)
    expect(enFull.nav.settings).toBeTruthy()
    expect(bgFull.nav.settings).toBeTruthy()
  })
})
