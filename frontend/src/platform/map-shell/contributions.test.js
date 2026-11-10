// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { validateManifest } from '../manifest.js'
import {
  collectBanners,
  collectContextMenu,
  collectLayerToggles,
  collectMapLayers,
  collectPopups,
  contributionProblems,
  popupFor,
} from './contributions.js'
import { BANNER_PRIORITY, Z } from './zorder.js'

const C = { name: 'c' }
const mod = (name, parts = {}) => ({ name, ...parts })
const ids = (list) => list.map((x) => x.id)

describe('map-shell contributions', () => {
  it('banners come out by priority whatever the list order [T420]', () => {
    const fire = mod('fire', { banners: [{ id: 'fire-alarm', priority: 20, component: C }] })
    const sos = mod('tracking', { banners: [{ id: 'sos', priority: 10, component: C }] })
    expect(ids(collectBanners([fire, sos]))).toEqual(['sos', 'fire-alarm'])
    expect(ids(collectBanners([sos, fire]))).toEqual(['sos', 'fire-alarm'])
  })

  it('legacy entries and manifest entries are merged [T420]', () => {
    const m = mod('m', {
      banners: [{ id: 'b2', priority: 30, component: C }],
      mapLayers: [{ id: 'l2', zIndex: 9 }],
      popups: [{ id: 'p2', component: C, kinds: ['b'] }],
      contextMenu: [{ id: 'c2', order: 2, labelKey: 'k', onSelect() {} }],
    })
    const legacy = {
      banners: [{ id: 'b1', priority: 10, component: C }],
      mapLayers: [{ id: 'l1', zIndex: 1 }],
      popups: [{ id: 'p1', component: C, kinds: ['a'] }],
      contextMenu: [{ id: 'c1', order: 1, labelKey: 'k', onSelect() {} }],
    }
    expect(ids(collectBanners([m], legacy.banners))).toEqual(['b1', 'b2'])
    expect(ids(collectMapLayers([m], legacy.mapLayers))).toEqual(['l1', 'l2'])
    expect(ids(collectPopups([m], legacy.popups)).sort()).toEqual(['p1', 'p2'])
    expect(ids(collectContextMenu([m], legacy.contextMenu))).toEqual(['c1', 'c2'])
    expect(collectBanners([], [])).toEqual([])
    expect(collectBanners([mod('x')])).toEqual([])
  })

  it('map layers come out by zIndex [T420]', () => {
    const m = mod('m', {
      mapLayers: [
        { id: 'hotspots', zIndex: 3.5 },
        { id: 'burnt', zIndex: 3 },
        { id: 'zones', zIndex: 3.4 },
      ],
    })
    expect(ids(collectMapLayers([m]))).toEqual(['burnt', 'zones', 'hotspots'])
  })

  it('layer toggles come out by order and carry adminOnly [T420]', () => {
    const m = mod('m', {
      mapLayers: [
        { id: 'a', zIndex: 1, toggle: { labelKey: 'ka', order: 30 } },
        { id: 'nodraw', zIndex: 2 },
        { id: 'b', zIndex: 3, toggle: { labelKey: 'kb', order: 10, adminOnly: true } },
      ],
    })
    expect(collectLayerToggles([m])).toEqual([
      { id: 'b', labelKey: 'kb', order: 10, adminOnly: true },
      { id: 'a', labelKey: 'ka', order: 30, adminOnly: false },
    ])
  })

  it('popupFor picks by kind and returns null for an unknown kind [T420]', () => {
    const m = mod('m', {
      popups: [
        { id: 'fire', component: C, kinds: ['fire-hotspot', 'burnt-area'] },
        { id: 'zone', component: C, kinds: ['zone'] },
      ],
    })
    const popups = collectPopups([m])
    expect(popupFor(popups, 'burnt-area').id).toBe('fire')
    expect(popupFor(popups, 'zone').id).toBe('zone')
    expect(popupFor(popups, 'nope')).toBeNull()
    expect(popupFor([], 'zone')).toBeNull()
  })

  it('context menu items come out by order [T420]', () => {
    const m = mod('m', {
      contextMenu: [
        { id: 'z', order: 20, labelKey: 'k', onSelect() {} },
        { id: 'a', order: 10, labelKey: 'k', onSelect() {} },
      ],
    })
    expect(ids(collectContextMenu([m]))).toEqual(['a', 'z'])
  })

  it('contributionProblems names a duplicate id, a duplicate banner priority, a kind claimed twice and a banner placed above SOS [T420]', () => {
    const joined = (mods, legacy) => contributionProblems(mods, legacy).join('\n')

    expect(contributionProblems([mod('ok', { banners: [{ id: 'sos', priority: 10, component: C }] })])).toEqual([])

    const dupId = mod('m', { mapLayers: [{ id: 'dup', zIndex: 1 }, { id: 'dup', zIndex: 2 }] })
    expect(joined([dupId])).toContain('dup')
    // the same id across modules and legacy within one kind is a duplicate too
    expect(joined([mod('a', { mapLayers: [{ id: 'q', zIndex: 1 }] })], { mapLayers: [{ id: 'q', zIndex: 2 }] })).toContain('q')
    // the same id in two different kinds is fine
    expect(contributionProblems([mod('m', {
      mapLayers: [{ id: 'same', zIndex: 1 }],
      contextMenu: [{ id: 'same', order: 1, labelKey: 'k', onSelect() {} }],
    })])).toEqual([])

    const samePrio = mod('m', { banners: [{ id: 'one', priority: 30, component: C }, { id: 'two', priority: 30, component: C }] })
    expect(joined([samePrio])).toMatch(/priority 30/)

    const kinds = mod('m', {
      popups: [{ id: 'p1', component: C, kinds: ['zone'] }, { id: 'p2', component: C, kinds: ['zone'] }],
    })
    expect(joined([kinds])).toContain('zone')

    const above = mod('m', { banners: [{ id: 'x', priority: 5, component: C }] })
    expect(joined([above])).toContain('x')
    const atSos = mod('m', { banners: [{ id: 'x', priority: 10, component: C }] })
    expect(joined([atSos])).toContain('x')
    expect(contributionProblems([mod('m', { banners: [{ id: 'x', priority: 11, component: C }] })])).toEqual([])

    const sosLow = mod('m', { banners: [{ id: 'sos', priority: 1, component: C }] })
    expect(contributionProblems([sosLow]).length).toBe(1)
    expect(joined([sosLow])).toContain('sos')
  })

  it('contributionProblems sees legacy entries and rejects an array legacy [T420]', () => {
    const m = mod('m', {
      mapLayers: [{ id: 'q', zIndex: 1 }],
      banners: [{ id: 'f', priority: 20, component: C }],
    })
    const legacy = {
      mapLayers: [{ id: 'q', zIndex: 2 }],
      banners: [{ id: 'g', priority: 20, component: C }, { id: 'x', priority: 10, component: C }],
    }
    const text = contributionProblems([m], legacy).join('\n')
    expect(text).toContain('"q"')
    expect(text).toMatch(/share priority 20/)
    expect(text).toContain('"x"')
    expect(() => contributionProblems([m], [])).toThrow(TypeError)
    expect(() => contributionProblems([m], [{ id: 'a' }])).toThrow(/legacy must be/)
  })

  it('sorting is deterministic and total [T420]', () => {
    const m = mod('m', {
      banners: [
        { id: 'a', priority: 30, component: C },
        { id: 'n', priority: NaN, component: C },
        { id: 'b', priority: 20, component: C },
        { id: 'u', priority: undefined, component: C },
      ],
    })
    const want = ['b', 'a', 'n', 'u']
    expect(ids(collectBanners([m]))).toEqual(want)
    expect(ids(collectBanners([{ ...m, banners: [...m.banners].reverse() }]))).toEqual(want)
    const t = mod('t', { mapLayers: [{ id: 'é', zIndex: 1 }, { id: 'z', zIndex: 1 }, { id: 'a', zIndex: 1 }] })
    expect(ids(collectMapLayers([t]))).toEqual(['a', 'z', 'é'])
  })

  it('null items are skipped, not thrown on [T420]', () => {
    const m = mod('m', {
      banners: [null, { id: 'b', priority: 20, component: C }, undefined],
      mapLayers: [null, { id: 'l', zIndex: 1, toggle: { labelKey: 'k', order: 1 } }],
      popups: [null, { id: 'p', component: C, kinds: ['k'] }],
      contextMenu: [null, { id: 'c', order: 1, labelKey: 'k', onSelect() {} }],
    })
    expect(ids(collectBanners([m, null], [null]))).toEqual(['b'])
    expect(ids(collectMapLayers([m]))).toEqual(['l'])
    expect(collectLayerToggles([m]).length).toBe(1)
    expect(ids(collectContextMenu([m]))).toEqual(['c'])
    expect(popupFor([null, ...collectPopups([m])], 'k').id).toBe('p')
    expect(contributionProblems([m, null], { banners: [null] })).toEqual([])
  })

  it('validateManifest accepts the optional fields and names each malformed one [T420]', () => {
    const complete = () => ({
      name: 'demo',
      routes: [],
      nav: [],
      mapLayers: [{ id: 'l', zIndex: 3, toggle: { labelKey: 'k', order: 1 } }],
      panels: [],
      banners: [],
      liveHandlers: {},
      i18n: { en: {}, bg: {} },
      depends: [],
      popups: [{ id: 'p', component: C, kinds: ['zone'] }],
      contextMenu: [{ id: 'c', order: 1, labelKey: 'k', onSelect() {} }],
    })
    expect(validateManifest(complete())).toEqual([])

    const without = complete()
    delete without.popups
    delete without.contextMenu
    expect(validateManifest(without)).toEqual([])

    const check = (mutate, field) => {
      const m = complete()
      mutate(m)
      const msg = validateManifest(m).join('\n')
      expect(msg, field).toContain(field)
    }
    check((m) => { m.popups = [{ id: 'p', component: C }] }, 'kinds')
    check((m) => { m.popups = [{ id: 'p', component: C, kinds: [] }] }, 'kinds')
    check((m) => { m.popups = 'x' }, 'popups')
    check((m) => { m.contextMenu = [{ id: 'c', order: 1, labelKey: 'k' }] }, 'onSelect')
    check((m) => { m.mapLayers[0].toggle = { labelKey: 'k' } }, 'order')
    check((m) => { m.mapLayers[0].create = () => ({}) }, 'create')
    check((m) => { m.mapSetup = () => {} }, 'mapSetup')
    expect(validateManifest(Object.assign(complete(), { mapSetup: () => {} })).join('\n'))
      .toContain('map code belongs in map/index.js, not in the manifest')
  })

  it('Z and BANNER_PRIORITY hold today\'s values [T420]', () => {
    expect(Z).toEqual({
      weather: 2, burnt: 3, zones: 3.4, hotspots: 3.5, graticule: 4, trail: 5,
      checkpoints: 6, trackers: 10, repeaters: 14, hq: 15, measure: 20,
    })
    expect(BANNER_PRIORITY).toEqual({ sos: 10, fireAlarm: 20 })
    expect(Object.isFrozen(Z)).toBe(true)
    expect(Object.isFrozen(BANNER_PRIORITY)).toBe(true)
  })
})

describe('map-shell contributions, legacy popups and context menu', () => {
  const P = (id, kinds) => ({ id, component: C, kinds })
  it('collectPopups and popupFor see legacy popups [T421]', () => {
    const m = mod('m', { popups: [P('mp', ['zone'])] })
    const legacy = [P('lp', ['hotspot'])]
    expect(ids(collectPopups([m], legacy))).toEqual(['mp', 'lp'])
    expect(popupFor(collectPopups([m], legacy), 'hotspot').id).toBe('lp')
    expect(popupFor(collectPopups([m], legacy), 'zone').id).toBe('mp')
    expect(popupFor(collectPopups([m], legacy), 'none')).toBeNull()
  })

  it('collectContextMenu merges legacy items and sorts by order [T421]', () => {
    const m = mod('m', { contextMenu: [{ id: 'b', order: 20, labelKey: 'k', onSelect() {} }] })
    const legacy = [{ id: 'a', order: 10, labelKey: 'k', onSelect() {} }]
    expect(ids(collectContextMenu([m], legacy))).toEqual(['a', 'b'])
  })

  it('contributionProblems flags a duplicate id across module and legacy popups and context menu [T421]', () => {
    const m = mod('m', {
      popups: [P('p', ['zone'])],
      contextMenu: [{ id: 'c', order: 1, labelKey: 'k', onSelect() {} }],
    })
    const text = contributionProblems([m], {
      popups: [P('p', ['other'])],
      contextMenu: [{ id: 'c', order: 2, labelKey: 'k', onSelect() {} }],
    }).join('\n')
    expect(text).toContain('popups: id "p"')
    expect(text).toContain('contextMenu: id "c"')
  })

  it('contributionProblems flags a kind claimed by a module popup and a legacy popup [T421]', () => {
    const m = mod('m', { popups: [P('mp', ['zone'])] })
    const text = contributionProblems([m], { popups: [P('lp', ['zone'])] }).join('\n')
    expect(text).toContain('kind "zone" is claimed by "mp" and "lp"')
  })
})
