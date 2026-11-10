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
