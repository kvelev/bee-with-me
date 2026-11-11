import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { collectBanners, contributionProblems } from '../../platform/map-shell/contributions.js'
import { BANNER_PRIORITY } from '../../platform/map-shell/zorder.js'
import { checkModules } from '../../platform/registry.js'
import { MODULES } from '../index.js'
import sos from './index.js'

describe('sos module manifest', () => {
  it('SOS is a manifest banner at priority 10 and comes before the fire alarm [T544]', () => {
    expect(MODULES).toContain(sos)
    expect(BANNER_PRIORITY.sos).toBe(10)
    expect(sos.banners).toHaveLength(1)
    expect(sos.banners[0]).toMatchObject({ id: 'sos', priority: 10 })
    expect(collectBanners(MODULES).map((b) => b.id)).toEqual(['sos', 'fire-alarm'])
    expect(contributionProblems(MODULES)).toEqual([])
    expect(checkModules(MODULES)).toEqual([])
  })

  it('sos depends on tracking and imports it only through its index [T544]', () => {
    expect(sos.depends).toEqual(['tracking'])
    const dir = path.dirname(fileURLToPath(import.meta.url))
    const files = []
    const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).forEach((e) => {
      const p = path.join(d, e.name)
      if (e.isDirectory()) walk(p)
      else if (/\.(js|vue)$/.test(e.name) && !e.name.includes('.test.')) files.push(p)
    })
    walk(dir)
    const imports = files.flatMap((f) => [...fs.readFileSync(f, 'utf8').matchAll(/from '([^']*tracking[^']*)'/g)].map((m) => m[1]))
    expect(imports.length).toBeGreaterThan(0)
    expect(imports.every((i) => i === '../tracking/index.js')).toBe(true)
  })
})
