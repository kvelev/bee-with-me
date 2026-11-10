import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('../api', () => ({ getMe: vi.fn(), login: vi.fn() }))

import bg from '../i18n/bg.js'
import en from '../i18n/en.js'
import { NAV_ITEMS } from '../nav-config.js'
import { validateManifest } from '../platform/manifest.js'
import router, { guard } from '../router/index.js'
import { useAuthStore } from '../stores/auth'
import { MODULES } from './index.js'
import devices from './devices/index.js'
import people from './people/index.js'
import teams from './teams/index.js'

const three = [people, teams, devices]

describe('people, teams and devices modules', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('token', 'x')
    setActivePinia(createPinia())
  })

  it('the three manifests are valid [T440]', () => {
    for (const m of three) expect(validateManifest(m)).toEqual([])
    expect(three.map((m) => m.name)).toEqual(['people', 'teams', 'devices'])
  })

  it('their routes are the old paths, named, not admin-only [T440]', () => {
    const expected = [[people, '/users', 'users'], [teams, '/groups', 'groups'], [devices, '/devices', 'devices']]
    for (const [m, path, name] of expected) {
      expect(m.routes).toHaveLength(1)
      expect(m.routes[0].path).toBe(path)
      expect(m.routes[0].name).toBe(name)
      expect(m.routes[0].meta?.adminOnly).toBeUndefined()
      expect(m.routes[0].meta?.public).toBeUndefined()
    }
  })

  it('their navigation items keep place and icon [T440]', () => {
    const expected = [[people, 20, '👤'], [teams, 30, '👥'], [devices, 40, '📡']]
    for (const [m, order, icon] of expected) {
      expect(m.nav).toHaveLength(1)
      expect(m.nav[0].order).toBe(order)
      expect(m.nav[0].icon).toBe(icon)
      expect(m.nav[0].adminOnly).toBeUndefined()
    }
    const orders = NAV_ITEMS.map((n) => n.order)
    expect(orders).toEqual([...orders].sort((a, b) => a - b))
    expect(new Set(orders).size).toBe(orders.length)
    expect(NAV_ITEMS.map((n) => n.to)).toEqual(
      ['/map', '/users', '/groups', '/devices', '/export', '/selectofflinemap', '/settings', '/about'])
  })

  it('teams and devices depend on people, and every dependency is a module in the list [T440]', () => {
    expect(people.depends).toEqual([])
    expect(teams.depends).toEqual(['people'])
    expect(devices.depends).toEqual(['people'])
    const names = MODULES.map((m) => m.name)
    for (const m of three) for (const d of m.depends) expect(names).toContain(d)
    expect(names).toEqual([...names].sort())
  })

  it('the texts are in the merged dictionaries in both languages [T440]', () => {
    for (const dict of [en, bg]) {
      for (const k of ['users', 'groups', 'devices']) {
        expect(dict[k]).toBeDefined()
        expect(dict.nav[k]).toBeDefined()
      }
    }
    expect(en.nav.users).not.toBe(bg.nav.users)
  })

  it('the router serves the three pages under the layout [T440]', async () => {
    useAuthStore().user = { role: 'viewer' }
    for (const [path, name] of [['/users', 'users'], ['/groups', 'groups'], ['/devices', 'devices']]) {
      const to = router.resolve(path)
      expect(to.matched).toHaveLength(2)
      expect(to.name).toBe(name)
      expect(to.meta.adminOnly).toBeUndefined()
      expect(await guard(to)).toBeUndefined()
    }
  })
})
