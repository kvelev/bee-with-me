import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { checkModules, collectNav, collectRoutes, corePathsOf, leafKeys, mergeMessages, messageCollisions } from './registry.js'

const comp = () => null
const mod = (name, extra = {}) => ({
  name,
  routes: [],
  nav: [],
  mapLayers: [],
  panels: [],
  banners: [],
  liveHandlers: {},
  i18n: { en: {}, bg: {} },
  depends: [],
  ...extra,
})

describe('module registry', () => {
  it('collectRoutes keeps list order [T403]', () => {
    const a = mod('a', { routes: [{ path: '/a', name: 'a', component: comp }, { path: '/a2', name: 'a2', component: comp }] })
    const b = mod('b', { routes: [{ path: '/b', name: 'b', component: comp }] })
    expect(collectRoutes([a, b]).map((r) => r.name)).toEqual(['a', 'a2', 'b'])
    expect(collectRoutes([])).toEqual([])
  })

  it('collectNav sorts static and module items by order [T403]', () => {
    const staticItems = [{ to: '/s1', labelKey: 'x', order: 10 }, { to: '/s3', labelKey: 'x', order: 30 }]
    const m = mod('m', { nav: [{ to: '/m2', labelKey: 'x', order: 20 }] })
    expect(collectNav(staticItems, [m]).map((i) => i.to)).toEqual(['/s1', '/m2', '/s3'])
  })

  it('collectNav is stable for equal order [T403]', () => {
    const staticItems = [{ to: '/s', labelKey: 'x', order: 10 }]
    const m = mod('m', { nav: [{ to: '/m', labelKey: 'x', order: 10 }] })
    expect(collectNav(staticItems, [m]).map((i) => i.to)).toEqual(['/s', '/m'])
  })

  it('checkModules names an invalid manifest, a duplicate name, a duplicate route path, a duplicate nav target and a nav item without order [T403]', () => {
    expect(checkModules([mod('ok', { nav: [{ to: '/ok', labelKey: 'k', order: 5 }] })])).toEqual([])

    expect(checkModules([{ name: 'broken' }]).join('\n')).toMatch(/^broken: /m)
    expect(checkModules([mod('dup'), mod('dup')]).join('\n')).toContain('duplicate module name: dup')

    const r = (name, path) => ({ path, name, component: comp })
    const paths = checkModules([mod('a', { routes: [r('a', '/same')] }), mod('b', { routes: [r('b', '/same')] })])
    expect(paths.join('\n')).toContain('duplicate route path: /same')
    const names = checkModules([mod('a', { routes: [r('same', '/a')] }), mod('b', { routes: [r('same', '/b')] })])
    expect(names.join('\n')).toContain('duplicate route name: same')

    const n = (to, order) => ({ to, labelKey: 'k', order })
    const navs = checkModules([mod('a', { nav: [n('/x', 1)] }), mod('b', { nav: [n('/x', 2)] })])
    expect(navs.join('\n')).toContain('duplicate navigation target: /x')

    const noOrder = checkModules([mod('a', { nav: [{ to: '/y', labelKey: 'k' }] })])
    expect(noOrder.join('\n')).toContain('order')
    const nanOrder = checkModules([mod('a', { nav: [n('/y', Number.NaN)] })])
    expect(nanOrder.join('\n')).toContain('order')
  })

  it('mergeMessages merges nested namespaces and keeps the first value on a collision without throwing [T403]', () => {
    const core = { nav: { map: 'Map' } }
    const merged = mergeMessages(core, [{ nav: { settings: 'Settings', map: 'X' }, settings: { title: 'T' } }])
    expect(merged.nav.map).toBe('Map')
    expect(merged.nav.settings).toBe('Settings')
    expect(merged.settings.title).toBe('T')
  })

  it('mergeMessages does not change its inputs [T403]', () => {
    const core = { nav: { map: 'Map' } }
    const dict = { nav: { settings: 'Settings' }, x: { y: 'z' } }
    const coreCopy = structuredClone(core)
    const dictCopy = structuredClone(dict)
    mergeMessages(core, [dict])
    expect(core).toEqual(coreCopy)
    expect(dict).toEqual(dictCopy)
  })

  it('messageCollisions reports nav.map for that input [T403]', () => {
    const core = { nav: { map: 'Map' } }
    expect(messageCollisions(core, [{ nav: { settings: 'S', map: 'X' } }])).toEqual(['nav.map'])
    expect(messageCollisions(core, [{ nav: { settings: 'S' } }])).toEqual([])
  })

  it('leafKeys lists dotted keys [T403]', () => {
    expect(leafKeys({ b: 'x', a: { d: 'y', c: 'z' } })).toEqual(['a.c', 'a.d', 'b'])
  })

  it('a module route is reachable under the layout and keeps its meta [T403]', () => {
    const m = mod('x', { routes: [{ path: '/x', name: 'x', component: comp, meta: { adminOnly: true } }] })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: comp, children: [{ path: 'map', component: comp }, ...collectRoutes([m])] }],
    })
    const hit = router.resolve('/x')
    expect(hit.matched.length).toBe(2)
    expect(hit.meta.adminOnly).toBe(true)
  })
})

describe('module route rules', () => {
  const route = (extra = {}) => ({ path: '/x', name: 'x', component: comp, ...extra })
  const problems = (r, corePaths = ['/map']) => checkModules([mod('m', { routes: [r] })], corePaths).join('\n')

  it('a plain module route passes [T404]', () => {
    expect(problems(route({ meta: { adminOnly: true } }))).toBe('')
  })

  it('a module route cannot be public [T404]', () => {
    expect(problems(route({ meta: { public: true } }))).toContain('meta.public')
  })

  it('a module route cannot redirect [T404]', () => {
    expect(problems(route({ redirect: '/map' }))).toContain('redirect')
  })

  it('a module route cannot have children [T404]', () => {
    expect(problems(route({ children: [] }))).toContain('children')
  })

  it('a module route cannot take the path of a core route, whatever the case or a trailing slash [T404]', () => {
    expect(problems(route({ path: '/map' }))).toContain('core route')
    expect(problems(route({ path: '/Map/' }))).toContain('core route')
    expect(problems(route({ path: '/' }), ['/'])).toContain('core route')
  })

  it('corePathsOf lists the absolute paths of the top routes and their children [T404]', () => {
    const routes = [
      { path: '/login' },
      { path: '/', children: [{ path: '' }, { path: 'map' }, { path: 'users' }] },
    ]
    expect(corePathsOf(routes)).toEqual(['/login', '/', '/map', '/users'])
  })
})
