import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({ getMe: vi.fn(), login: vi.fn() }))

import { MODULES } from '../modules/index.js'
import { collectRoutes } from '../platform/registry.js'
import router from './index.js'

describe('module routes in the real router', () => {
  it('the real router serves every module route under the layout with its meta [T403]', () => {
    for (const route of collectRoutes(MODULES)) {
      const hit = router.resolve(route.path)
      expect(hit.matched.length, route.path).toBe(2)
      expect(hit.name, route.path).toBe(route.name)
      expect(!!hit.meta.adminOnly, route.path).toBe(!!route.meta?.adminOnly)
    }
  })

  it('the real router file spreads the module routes [T403]', () => {
    // vitest runs with the frontend folder as cwd
    const text = readFileSync(join(process.cwd(), 'src', 'router', 'index.js'), 'utf8')
    expect(text).toContain('...collectRoutes(MODULES)')
  })
})

describe('the router checks the module list when it is created', () => {
  const bad = (route) => ({
    name: 'bad', routes: [route], nav: [], mapLayers: [], panels: [], banners: [], liveHandlers: {}, depends: [],
    i18n: { en: {}, bg: {} },
  })
  const load = async (module) => {
    vi.resetModules()
    vi.doMock('../modules/index.js', () => ({ MODULES: [module] }))
    return import('./index.js')
  }
  const route = (extra) => ({ path: '/bad', name: 'bad', component: {}, ...extra })

  it('refuses a public module route [T404]', async () => {
    await expect(load(bad(route({ meta: { public: true } })))).rejects.toThrow(/meta\.public/)
  })

  it('refuses a module route that takes a core path [T404]', async () => {
    await expect(load(bad(route({ path: '/export' })))).rejects.toThrow(/core route/)
  })

  it('refuses a module route with an alias or a beforeEnter [B97]', async () => {
    await expect(load(bad(route({ alias: '/export' })))).rejects.toThrow(/alias is not allowed/)
    await expect(load(bad(route({ beforeEnter: () => true })))).rejects.toThrow(/beforeEnter is not allowed/)
  })

  it('starts with a valid module [T404]', async () => {
    const { default: r } = await load(bad(route()))
    expect(r.resolve('/bad').name).toBe('bad')
  })

  it('the real router file calls checkModules on the module list [T404]', () => {
    const text = readFileSync(join(process.cwd(), 'src', 'router', 'index.js'), 'utf8')
    expect(text).toMatch(/checkModules\(MODULES,/)
  })
})
