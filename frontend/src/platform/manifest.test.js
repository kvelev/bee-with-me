// @vitest-environment node
import { describe, expect, it } from 'vitest'
import { validateManifest } from './manifest.js'

const base = (toggle) => ({
  name: 'demo', routes: [], nav: [], panels: [], banners: [], liveHandlers: {}, depends: [],
  i18n: { en: {}, bg: {} },
  mapLayers: [{ id: 'l', zIndex: 3, toggle }],
})

describe('toggle.adminOnly', () => {
  it('accepts true, false and absent [T421]', () => {
    expect(validateManifest(base({ labelKey: 'k', order: 1, adminOnly: true }))).toEqual([])
    expect(validateManifest(base({ labelKey: 'k', order: 1, adminOnly: false }))).toEqual([])
    expect(validateManifest(base({ labelKey: 'k', order: 1 }))).toEqual([])
  })
  it('names the field when it is not a boolean [T421]', () => {
    const msg = validateManifest(base({ labelKey: 'k', order: 1, adminOnly: 'yes' })).join('\n')
    expect(msg).toContain('toggle.adminOnly must be a boolean')
  })
})
